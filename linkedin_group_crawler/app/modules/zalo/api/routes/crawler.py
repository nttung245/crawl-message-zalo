from typing import List, Optional, Tuple
import asyncio
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from app.modules.zalo.config import settings
from app.modules.zalo.crawler.scroll_handler import scroll_and_collect, verify_group_for_crawl
from app.modules.zalo.schemas.job import JobData, JobProgress
from app.modules.zalo.schemas.session import SessionData
from app.modules.zalo.services.gsheet_service import write_messages
from app.modules.zalo.services.job_store import get_job, save_job
from app.modules.zalo.services.supabase_service import (
    is_supabase_configured,
    list_recent_messages_for_group,
    save_crawl_messages,
    upsert_crawl_job,
)
from app.modules.zalo.services.session_store import (
    get_latest_session_for_user,
    get_latest_browser_session_for_user,
    get_session,
    get_session_lock,
    save_session,
)
from app.modules.zalo.services.session_browser import ensure_session_browser_ready
from app.modules.zalo.services.browser_operation_lock import zalo_browser_operation_lock
from app.modules.zalo.services.zca_auth_store import ensure_session_zca_auth, load_zca_auth
from app.modules.zalo.services.zca_api_bridge import (
    get_zca_group_related_ids,
    get_zca_group_history,
    list_zca_groups,
    sync_zca_group_old_messages,
)
from app.modules.zalo.services.zca_persistent_listener import get_cached_messages, start_listener, stop_listener
from app.modules.zalo.api.security import verify_zalo_api_key

router = APIRouter(
    prefix="/api/zalo/crawl",
    tags=["zalo-crawl"],
    dependencies=[Depends(verify_zalo_api_key)],
)

_CRAWL_WORKER_LOCK = zalo_browser_operation_lock
_CRAWL_JOB_TIMEOUT_SECONDS = 15 * 60
_CRAWL_QUEUE: "asyncio.Queue" = asyncio.Queue()
_CRAWL_QUEUE_WORKER_TASK: Optional[asyncio.Task] = None


def _normalize_user_id(value: Optional[str]) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


def _build_session_id(user_id: str) -> str:
    return f"{user_id}--{uuid.uuid4().hex}"


def _normalize_group_name(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _compact_group_name(value: Optional[str]) -> str:
    normalized = _normalize_group_name(value)
    normalized = re.sub(r"^\s*tab\s+sheets?\s*:\s*", "", normalized)
    normalized = re.sub(r"[\[\](){}/\\|:_\-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _group_match_score(group_name: str, candidate_name: str) -> int:
    wanted = _compact_group_name(group_name)
    candidate = _compact_group_name(candidate_name)
    if not wanted or not candidate:
        return 0
    if wanted == candidate:
        return 100
    if wanted in candidate or candidate in wanted:
        return 85

    wanted_tokens = {token for token in wanted.split(" ") if len(token) >= 2}
    candidate_tokens = {token for token in candidate.split(" ") if len(token) >= 2}
    if not wanted_tokens or not candidate_tokens:
        return 0
    overlap = len(wanted_tokens & candidate_tokens)
    if overlap == 0:
        return 0
    coverage = overlap / max(len(wanted_tokens), len(candidate_tokens))
    if coverage >= 0.85:
        return 80
    if coverage >= 0.65:
        return 65
    if coverage >= 0.45:
        return 45
    return 0


def _is_zca_history_group_id(value: Optional[str]) -> bool:
    text = (value or "").strip()
    return bool(re.fullmatch(r"\d{6,}", text))


async def _restore_zca_session_from_store(user_id: str) -> Optional[SessionData]:
    auth = await load_zca_auth(user_id)
    if not auth:
        return None
    session = SessionData(
        session_id=_build_session_id(user_id),
        user_id=user_id,
        browser=None,
        context=None,
        page=None,
        status="confirmed",
        qr_base64=None,
        qr_signature=None,
        zca_auth=auth,
        created_at=datetime.utcnow(),
        last_used=datetime.utcnow(),
    )
    await save_session(session)
    logger.info(f"Restored ZCA session for crawl from auth store: user={user_id} session={session.session_id}")
    return session


async def _get_confirmed_or_zca_session(user_id: str, session_id: Optional[str]) -> Optional[SessionData]:
    session = await get_session(session_id) if session_id else None
    if not session:
        session = await get_latest_browser_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        session = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        session = await _restore_zca_session_from_store(user_id)
    if session:
        await ensure_session_zca_auth(session)
    return session


async def _resolve_zca_group_id(auth: dict, requested_group_id: Optional[str], group_name: str) -> str:
    requested = (requested_group_id or "").strip()
    if requested and requested != group_name:
        return requested

    groups = await list_zca_groups(auth)
    wanted_name = _normalize_group_name(group_name)
    for group in groups:
        if _normalize_group_name(group.name) == wanted_name:
            return group.group_id
    for group in groups:
        normalized = _normalize_group_name(group.name)
        if wanted_name and (wanted_name in normalized or normalized in wanted_name):
            return group.group_id

    raise RuntimeError(
        f"zca_group_not_found: Không tìm thấy group {group_name!r} trong danh sách ZCA. "
        "Bấm tải nhóm từ Zalo lại rồi chọn đúng group."
    )


async def _resolve_zca_group_candidates(
    auth: dict,
    requested_group_id: Optional[str],
    group_name: str,
    *,
    limit: int = 8,
) -> List[str]:
    requested = (requested_group_id or "").strip()
    candidates: List[str] = []

    def add(group_id: Optional[str]) -> None:
        value = (group_id or "").strip()
        if value and _is_zca_history_group_id(value) and value not in candidates:
            candidates.append(value)

    if requested and requested != group_name:
        add(requested)

    groups = await list_zca_groups(auth)
    scored = []
    requested_compact = _compact_group_name(requested)
    wanted_compact = _compact_group_name(group_name)
    for group in groups:
        score = _group_match_score(group_name, group.name)
        if requested_compact and requested_compact == _compact_group_name(group.name):
            score = max(score, 95)
        if wanted_compact and group.group_id == requested:
            score = max(score, 90)
        if score > 0:
            scored.append((score, group.group_id, group.name))

    for score, group_id, name in sorted(scored, key=lambda item: item[0], reverse=True):
        add(group_id)
        try:
            for related_id in await get_zca_group_related_ids(auth, group_id):
                add(related_id)
        except Exception as exc:
            logger.warning(f"Could not load related ZCA group ids for {group_id!r}: {exc}")
        logger.info(
            f"ZCA group candidate score={score} requested_id={requested!r} "
            f"group_name={group_name!r} candidate_id={group_id!r} candidate_name={name!r}"
        )
        if len(candidates) >= limit:
            break

    if not candidates:
        raise RuntimeError(
            f"zca_group_not_found: Could not resolve Zalo group_id for {group_name!r}. "
            "Reload groups from Zalo and choose the live group item, not a manually typed name."
        )
    return candidates


async def _crawl_zca_messages_with_best_group_id(
    user_id: str,
    auth: dict,
    requested_group_id: Optional[str],
    group_name: str,
    *,
    count: int,
) -> Tuple[str, list]:
    candidates = await _resolve_zca_group_candidates(auth, requested_group_id, group_name)
    errors: List[str] = []

    for candidate_id in candidates:
        try:
            cached_messages = get_cached_messages(user_id, candidate_id, limit=count)
            if cached_messages:
                logger.info(
                    f"ZCA selected group_id={candidate_id!r} for group={group_name!r} "
                    f"via persistent listener cache messages={len(cached_messages)} candidates={candidates}"
                )
                return candidate_id, cached_messages[:count]

            if settings.save_to_supabase and is_supabase_configured():
                stored_messages = await list_recent_messages_for_group(user_id, candidate_id, limit=count)
                if stored_messages:
                    logger.info(
                        f"ZCA selected group_id={candidate_id!r} for group={group_name!r} "
                        f"via Supabase listener store messages={len(stored_messages)} candidates={candidates}"
                    )
                    return candidate_id, stored_messages[:count]

            history_counts = []
            for value in (count, 200, 100, 50, 20, 10, 5):
                safe_count = max(1, min(int(value), max(count, 500)))
                if safe_count not in history_counts:
                    history_counts.append(safe_count)

            for history_count in history_counts:
                messages = await get_zca_group_history(auth, candidate_id, count=history_count)
                if messages:
                    logger.info(
                        f"ZCA selected group_id={candidate_id!r} for group={group_name!r} "
                        f"via getGroupChatHistory count={history_count} messages={len(messages)} candidates={candidates}"
                    )
                    return candidate_id, messages[:count]

            try:
                related_ids = await get_zca_group_related_ids(auth, candidate_id)
                for related_id in related_ids:
                    if related_id and related_id not in candidates:
                        candidates.append(related_id)
                        logger.info(
                            f"ZCA added related candidate_id={related_id!r} from getGroupInfo "
                            f"for group={group_name!r} original={candidate_id!r}"
                        )
            except Exception as exc:
                logger.warning(
                    f"Could not append related ZCA ids during crawl for candidate_id={candidate_id!r}: {exc}"
                )

            logger.warning(
                f"ZCA history returned no messages for candidate_id={candidate_id!r} "
                f"group={group_name!r}; trying listener sync"
            )
            messages = await sync_zca_group_old_messages(
                auth,
                candidate_id,
                count=count,
                timeout_ms=35000,
            )
            if messages:
                logger.info(
                    f"ZCA selected group_id={candidate_id!r} for group={group_name!r} "
                    f"via listener sync messages={len(messages)} candidates={candidates}"
                )
                return candidate_id, messages
            errors.append(f"{candidate_id}:empty")
        except Exception as exc:
            errors.append(f"{candidate_id}:{type(exc).__name__}:{exc}")
            logger.warning(
                f"ZCA candidate failed for group={group_name!r} candidate_id={candidate_id!r}: {exc}"
            )

    raise RuntimeError(
        "listener_cache_empty_and_zca_history_empty: Persistent listener cache/Supabase and ZCA history returned no messages. "
        f"group={group_name!r}; requested_group_id={requested_group_id!r}; candidates={candidates}; errors={errors}"
    )


async def _crawl_with_browser_fallback(session: SessionData, job_id: str, body: "CrawlRequest"):
    browser_session = await get_latest_browser_session_for_user(
        session.user_id,
        preferred_statuses={"confirmed"},
    )
    if browser_session:
        logger.info(
            f"Using existing browser session for UI fallback: "
            f"job={job_id} zca_session={session.session_id} browser_session={browser_session.session_id}"
        )
        session = browser_session

    session_lock = await get_session_lock(session.session_id)
    async with _CRAWL_WORKER_LOCK:
        async with session_lock:
            live_status = await ensure_session_browser_ready(session)
            if live_status != "confirmed":
                raise RuntimeError(
                    f"browser_fallback_login_not_ready:{live_status}. "
                    "ZCA auth không mở được Zalo Web. Hãy bấm 'Mở màn hình Zalo', đăng nhập trong cửa sổ đó, "
                    "rồi chạy lại group này để crawl bằng UI fallback."
                )

            verification = await verify_group_for_crawl(
                session.page,
                group_name=body.group_name,
                group_id=body.group_id,
            )
            if not verification.get("ok"):
                raise RuntimeError(
                    f"browser_fallback_group_verify_failed:{verification.get('reason')}: "
                    f"{verification.get('detail')}"
                )

            try:
                return await asyncio.wait_for(
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
                raise RuntimeError(f"browser_fallback_timeout_after_{_CRAWL_JOB_TIMEOUT_SECONDS}s") from exc


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
    session = await _get_confirmed_or_zca_session(user_id, x_session_id)
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed session found, please login first")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    zca_auth = await ensure_session_zca_auth(session)
    if not zca_auth:
        live_status = await ensure_session_browser_ready(session)
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

    resolved_group_id = body.group_id or body.group_name
    job = JobData(
        job_id=job_id,
        user_id=user_id,
        group_id=resolved_group_id,
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
    _CRAWL_QUEUE.put_nowait((job_id, session_id, user_id, body))
    _ensure_crawl_queue_worker()


def _ensure_crawl_queue_worker() -> None:
    global _CRAWL_QUEUE_WORKER_TASK
    if _CRAWL_QUEUE_WORKER_TASK and not _CRAWL_QUEUE_WORKER_TASK.done():
        return
    _CRAWL_QUEUE_WORKER_TASK = asyncio.create_task(_crawl_queue_worker())


async def _crawl_queue_worker() -> None:
    while True:
        job_id, session_id, user_id, body = await _CRAWL_QUEUE.get()
        try:
            await _run_crawl_with_timeout(job_id, session_id, user_id, body)
        except asyncio.CancelledError:
            logger.warning(f"Crawl queue worker cancelled while running job={job_id}")
            raise
        except Exception as exc:
            logger.exception(f"Crawl queue worker caught unhandled crash: job={job_id}: {exc}")
            job = get_job(job_id)
            if job and job.status in {"queued", "running"}:
                job.status = "failed"
                job.error = f"background_task_crashed:{type(exc).__name__}: {exc}"
                job.completed_at = datetime.utcnow()
                save_job(job)
        finally:
            _CRAWL_QUEUE.task_done()


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
        session = await _get_confirmed_or_zca_session(user_id, None)
    if not session:
        raise RuntimeError("Session expired during crawl")

    session_lock = await get_session_lock(session.session_id)
    if session_lock.locked() or _CRAWL_WORKER_LOCK.locked():
        logger.info(
            f"Job {job_id} waiting in queue for Zalo worker/session {session.session_id} (group={body.group_name!r})"
        )

    try:
        zca_auth = await ensure_session_zca_auth(session)
        if zca_auth:
            job = get_job(job_id)
            if job and job.status == "queued":
                job.status = "running"
                save_job(job)

            try:
                resolved_group_id, messages = await _crawl_zca_messages_with_best_group_id(
                    user_id,
                    zca_auth,
                    body.group_id,
                    body.group_name,
                    count=body.max_messages,
                )
            except RuntimeError as zca_exc:
                error_text = str(zca_exc)
                if (
                    "listener_cache_empty_and_zca_history_empty" not in error_text
                    and "no_messages_returned_from_zca_api" not in error_text
                ):
                    raise
                logger.warning(
                    f"ZCA returned no crawlable messages for group={body.group_name!r}; "
                    f"switching to Playwright UI fallback. detail={error_text[:500]}"
                )
                try:
                    await stop_listener(user_id)
                    resolved_group_id, messages = await _crawl_with_browser_fallback(session, job_id, body)
                finally:
                    try:
                        if session.context:
                            await session.context.close()
                    except Exception:
                        pass
                    try:
                        if session.browser:
                            await session.browser.close()
                    except Exception:
                        pass
                    session.browser = None
                    session.context = None
                    session.page = None
                    await save_session(session)
                    try:
                        await start_listener(user_id, zca_auth, force_restart=True)
                    except Exception as listener_exc:
                        logger.warning(f"Could not restart ZCA listener after UI fallback: {listener_exc}")
            if not messages:
                logger.warning(
                    f"ZCA returned no messages for group={resolved_group_id} job={job_id}; "
                    "trying ZCA listener old-message sync"
                )
                try:
                    messages = await sync_zca_group_old_messages(
                        zca_auth,
                        resolved_group_id,
                        count=body.max_messages,
                    )
                except Exception as fallback_exc:
                    raise RuntimeError(
                        "no_messages_returned_from_zca_api: ZCA lấy được group nhưng không trả tin nhắn; "
                        f"listener sync also failed: {fallback_exc}"
                    ) from fallback_exc
                if not messages:
                    raise RuntimeError(
                        "no_messages_returned_from_zca_api: ZCA group history and listener sync returned no messages. "
                        "Kiểm tra group có tin nhắn mới, đúng group_id, hoặc đăng nhập lại Zalo."
                    )

            job = get_job(job_id)
            if job:
                # Sắp xếp tin nhắn từ mới nhất xuống cũ nhất
                messages.sort(
                    key=lambda m: int(m.timestamp) if m.timestamp and m.timestamp.isdigit() else 0,
                    reverse=True
                )
                
                job.group_id = resolved_group_id
                job.progress.messages_collected = len(messages)
                job.progress.images_found = sum(len(m.image_urls) for m in messages)
                dates = [m.timestamp for m in messages if m.timestamp]
                if dates:
                    job.progress.oldest_message_date = min(dates)
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                save_job(job)
                if settings.save_to_supabase:
                    saved_count = await save_crawl_messages(user_id, job, resolved_group_id, messages)
                    logger.info(f"Saved {saved_count} ZCA Zalo messages to Supabase for job {job_id}")

            if settings.write_google_sheet and resolved_sheet_id:
                await write_messages(
                    credentials_path=settings.google_credentials_path,
                    sheet_id=resolved_sheet_id,
                    group_name=body.group_name,
                    sheet_tab=job.sheet_tab if job and job.sheet_tab else body.group_name,
                    messages=messages,
                )
            logger.info(f"ZCA job {job_id} completed: group={resolved_group_id} messages={len(messages)}")
            return
        async with _CRAWL_WORKER_LOCK:
            async with session_lock:
                job = get_job(job_id)
                if job and job.status == "queued":
                    job.status = "running"
                    save_job(job)

                live_status = await ensure_session_browser_ready(session)
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
                    # Sắp xếp tin nhắn từ mới nhất xuống cũ nhất
                    messages.sort(
                        key=lambda m: int(m.timestamp) if m.timestamp and m.timestamp.isdigit() else 0,
                        reverse=True
                    )
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
