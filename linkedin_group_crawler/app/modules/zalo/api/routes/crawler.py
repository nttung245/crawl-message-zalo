import asyncio
import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from app.modules.zalo.config import settings
from app.modules.zalo.crawler.qr_login import check_login_status
from app.modules.zalo.crawler.scroll_handler import scroll_and_collect, verify_group_for_crawl
from app.modules.zalo.schemas.job import JobData, JobProgress
from app.modules.zalo.services.gsheet_service import write_messages
from app.modules.zalo.services.job_store import get_job, save_job
from app.modules.zalo.services.supabase_service import is_supabase_configured, save_crawl_messages, upsert_crawl_job
from app.modules.zalo.services.session_store import (
    get_latest_session_for_user,
    get_session,
    get_session_lock,
    save_session,
)
from app.modules.zalo.services.browser_operation_lock import zalo_browser_operation_lock
from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.apartment_agent.config import settings as agent_settings

router = APIRouter(
    prefix="/api/zalo/crawl",
    tags=["zalo-crawl"],
    dependencies=[Depends(verify_zalo_api_key)],
)

_CRAWL_WORKER_LOCK = zalo_browser_operation_lock
_CRAWL_JOB_TIMEOUT_SECONDS = 15 * 60


def _normalize_user_id(value: str | None) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


class CrawlRequest(BaseModel):
    group_name: str
    group_id: Optional[str] = None
    sheet_tab: Optional[str] = None
    max_messages: int = Field(default=50, ge=1, le=500)


@router.post("")
async def start_crawl(
    body: CrawlRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = _normalize_user_id(x_user_id)
    session = await get_session(x_session_id) if x_session_id else None
    if not session:
        session = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed session found, please login first")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    live_status = await check_login_status(session.page)
    session.status = live_status
    await save_session(session)
    if live_status != "confirmed":
        raise HTTPException(
            status_code=403,
            detail=f"Login not completed yet (status={live_status})",
        )

    resolved_sheet_id = settings.default_sheet_id.strip() if settings.write_google_sheet else ""
    if settings.write_google_sheet and not resolved_sheet_id:
        raise HTTPException(
            status_code=500,
            detail="ZALO_DEFAULT_SHEET_ID is missing in backend env",
        )
    if settings.save_to_supabase and not is_supabase_configured():
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when ZALO_SAVE_TO_SUPABASE=true",
        )

    job_id = str(uuid.uuid4())
    sheet_tab = body.sheet_tab or body.group_name
    sheet_url = f"https://docs.google.com/spreadsheets/d/{resolved_sheet_id}" if resolved_sheet_id else None

    job = JobData(
        job_id=job_id,
        user_id=user_id,
        group_id=body.group_name,
        group_name=body.group_name,
        sheet_id=resolved_sheet_id,
        sheet_tab=sheet_tab,
        status="queued",
        progress=JobProgress(),
        started_at=datetime.utcnow(),
        sheet_url=sheet_url,
    )
    save_job(job)
    if settings.save_to_supabase and is_supabase_configured():
        try:
            await upsert_crawl_job(user_id, job)
        except Exception as supabase_exc:
            logger.warning(f"Could not persist queued job {job_id} to Supabase: {supabase_exc}")

    _schedule_crawl_job(job_id, session.session_id, user_id, body)
    logger.info(
        f"Created crawl job {job_id} for group_name={body.group_name!r} using session={session.session_id}"
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "sheet_url": sheet_url,
    }


def _schedule_crawl_job(job_id: str, session_id: str, user_id: str, body: CrawlRequest) -> None:
    task = asyncio.create_task(_run_crawl_with_timeout(job_id, session_id, user_id, body))

    def _log_task_result(done_task: asyncio.Task[None]) -> None:
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.warning(f"Crawl background task cancelled: job={job_id}")
        except Exception as exc:
            logger.exception(f"Crawl background task crashed: job={job_id}: {exc}")
            job = get_job(job_id)
            if job and job.status in {"queued", "running"}:
                job.status = "failed"
                job.error = f"background_task_crashed:{type(exc).__name__}: {exc}"
                job.completed_at = datetime.utcnow()
                save_job(job)

    task.add_done_callback(_log_task_result)


async def _run_crawl_with_timeout(job_id: str, session_id: str, user_id: str, body: CrawlRequest) -> None:
    try:
        await _run_crawl(job_id, session_id, user_id, body)
    except asyncio.TimeoutError:
        logger.error(f"Job {job_id} timed out after {_CRAWL_JOB_TIMEOUT_SECONDS}s")
        job = get_job(job_id)
        if job:
            job.status = "failed"
            job.error = f"crawl_timeout_after_{_CRAWL_JOB_TIMEOUT_SECONDS}s"
            job.completed_at = datetime.utcnow()
            save_job(job)


async def _run_crawl(job_id: str, session_id: str, user_id: str, body: CrawlRequest) -> None:
    job = get_job(job_id)
    if not job:
        return

    resolved_sheet_id = settings.default_sheet_id.strip() if settings.write_google_sheet else ""

    session = await get_session(session_id)
    if not session:
        job.status = "failed"
        job.error = "Session expired during crawl"
        job.completed_at = datetime.utcnow()
        save_job(job)
        return

    session_lock = await get_session_lock(session_id)
    if session_lock.locked() or _CRAWL_WORKER_LOCK.locked():
        logger.info(
            f"Job {job_id} waiting in queue for Zalo worker/session {session_id} (group={body.group_name!r})"
        )

    try:
        async with _CRAWL_WORKER_LOCK:
            async with session_lock:
                job = get_job(job_id)
                if job and job.status == "queued":
                    job.status = "running"
                    save_job(job)

                live_status = await check_login_status(session.page)
                session.status = live_status
                await save_session(session)
                if live_status != "confirmed":
                    raise RuntimeError(f"Login not completed yet (status={live_status})")

                verification = await verify_group_for_crawl(
                    session.page,
                    group_name=body.group_name,
                    group_id=body.group_id,
                )
                if not verification.get("ok"):
                    raise RuntimeError(
                        f"group_verify_failed:{verification.get('reason')}: "
                        f"{verification.get('detail')}"
                    )

                try:
                    resolved_group_id, messages = await asyncio.wait_for(
                        scroll_and_collect(
                            session.page,
                            body.group_id,
                            body.group_name,
                            job_id,
                            max_messages=body.max_messages,
                        ),
                        timeout=_CRAWL_JOB_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError as exc:
                    raise RuntimeError(f"crawl_timeout_after_{_CRAWL_JOB_TIMEOUT_SECONDS}s") from exc
                if not messages:
                    raise RuntimeError(
                        "no_messages_synced: Không thấy tin nhắn sau khi mở nhóm. "
                        "Hãy mở Zalo, chờ nhóm đồng bộ tin nhắn rồi chạy lại."
                    )

                job = get_job(job_id)
                if job:
                    job.group_id = resolved_group_id
                    job.progress.messages_collected = len(messages)
                    job.progress.images_found = sum(len(m.image_urls) for m in messages)
                    if messages:
                        dates = [m.timestamp for m in messages if m.timestamp]
                        if dates:
                            job.progress.oldest_message_date = min(dates)
                    save_job(job)
        job = get_job(job_id)
        if job:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            save_job(job)
            if settings.save_to_supabase:
                saved_count = await save_crawl_messages(user_id, job, job.group_id, messages)
                logger.info(f"Saved {saved_count} Zalo messages to Supabase for job {job_id}")

        if settings.write_google_sheet and resolved_sheet_id:
            await write_messages(
                credentials_path=settings.google_credentials_path,
                sheet_id=resolved_sheet_id,
                group_name=body.group_name,
                sheet_tab=job.sheet_tab if job and job.sheet_tab else body.group_name,
                messages=messages,
            )

        logger.info(f"Job {job_id} completed: {len(messages)} messages")

        # Post-crawl hook: auto-trigger apartment agent if enabled
        if agent_settings.auto_process:
            try:
                from app.modules.apartment_agent.pipeline import process_messages
                agent_messages = [
                    {"id": str(m.message_id or ""), "text": m.content or ""}
                    for m in messages
                    if m.content
                ]
                if agent_messages:
                    logger.info(f"Auto-triggering apartment agent for {len(agent_messages)} messages")
                    asyncio.create_task(process_messages(agent_messages))
            except Exception as agent_exc:
                logger.warning(f"Apartment agent auto-trigger failed: {agent_exc}")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job = get_job(job_id)
        if job:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            save_job(job)
            if settings.save_to_supabase and is_supabase_configured():
                try:
                    await upsert_crawl_job(user_id, job)
                except Exception as supabase_exc:
                    logger.warning(f"Could not persist failed job {job_id} to Supabase: {supabase_exc}")

