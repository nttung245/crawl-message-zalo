import asyncio
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.modules.zalo.config import settings
from app.modules.zalo.crawler.qr_login import check_login_status
from app.modules.zalo.crawler.scroll_handler import scroll_and_collect
from app.modules.zalo.schemas.job import JobData, JobProgress
from app.modules.zalo.services.gsheet_service import write_messages
from app.modules.zalo.services.job_store import get_job, save_job
from app.modules.zalo.services.session_store import (
    get_latest_session_for_user,
    get_session,
    get_session_lock,
    save_session,
)

router = APIRouter(prefix="/api/zalo/crawl", tags=["zalo-crawl"])


class CrawlRequest(BaseModel):
    group_name: str
    sheet_tab: Optional[str] = None


@router.post("")
async def start_crawl(
    body: CrawlRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = (x_user_id or "default").strip() or "default"
    session = get_session(x_session_id) if x_session_id else None
    if not session:
        session = get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed session found, please login first")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    live_status = await check_login_status(session.page)
    session.status = live_status
    save_session(session)
    if live_status != "confirmed":
        raise HTTPException(
            status_code=403,
            detail=f"Login not completed yet (status={live_status})",
        )

    resolved_sheet_id = settings.default_sheet_id.strip()
    if not resolved_sheet_id:
        raise HTTPException(
            status_code=500,
            detail="ZALO_DEFAULT_SHEET_ID is missing in backend env",
        )

    job_id = str(uuid.uuid4())
    sheet_tab = body.sheet_tab or body.group_name
    sheet_url = f"https://docs.google.com/spreadsheets/d/{resolved_sheet_id}"

    job = JobData(
        job_id=job_id,
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

    asyncio.create_task(_run_crawl(job_id, session.session_id, body))
    logger.info(
        f"Created crawl job {job_id} for group_name={body.group_name!r} using session={session.session_id}"
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "sheet_url": sheet_url,
    }


async def _run_crawl(job_id: str, session_id: str, body: CrawlRequest) -> None:
    job = get_job(job_id)
    if not job:
        return

    resolved_sheet_id = settings.default_sheet_id.strip()

    session = get_session(session_id)
    if not session:
        job.status = "failed"
        job.error = "Session expired during crawl"
        job.completed_at = datetime.utcnow()
        save_job(job)
        return

    session_lock = get_session_lock(session_id)
    if session_lock.locked():
        logger.info(
            f"Job {job_id} waiting in queue for session {session_id} (group={body.group_name!r})"
        )

    try:
        async with session_lock:
            job = get_job(job_id)
            if job and job.status == "queued":
                job.status = "running"
                save_job(job)

            live_status = await check_login_status(session.page)
            session.status = live_status
            save_session(session)
            if live_status != "confirmed":
                raise RuntimeError(f"Login not completed yet (status={live_status})")

            resolved_group_id, messages = await scroll_and_collect(
                session.page,
                None,
                body.group_name,
                job_id,
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

            await write_messages(
                credentials_path=settings.google_credentials_path,
                sheet_id=resolved_sheet_id,
                group_name=body.group_name,
                sheet_tab=job.sheet_tab if job else body.group_name,
                messages=messages,
            )

        job = get_job(job_id)
        if job:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            save_job(job)

        logger.info(f"Job {job_id} completed: {len(messages)} messages")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job = get_job(job_id)
        if job:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            save_job(job)
