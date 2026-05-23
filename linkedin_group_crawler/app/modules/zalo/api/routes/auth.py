import asyncio
import re
import uuid
from datetime import datetime

import json

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from playwright.async_api import Error as PlaywrightError

from app.modules.zalo.crawler.browser import clear_user_profile_data, create_browser
from app.modules.zalo.config import settings
from app.modules.zalo.crawler.qr_login import (
    check_login_status,
    ZaloAlreadyLoggedInError,
    navigate_and_get_qr,
    qr_signature,
    refresh_qr_with_previous,
)
from app.modules.zalo.schemas.session import SessionData
from app.modules.zalo.services.session_store import (
    delete_sessions_for_user,
    get_latest_session_for_user,
    get_latest_waiting_session,
    get_profile_lock,
    get_session,
    save_session,
)

router = APIRouter(prefix="/api/zalo/auth", tags=["zalo-auth"])

_QR_REFRESH_TASKS: dict[str, asyncio.Task[None]] = {}
_QR_AUTO_REFRESH_SECONDS = 60


def _cancel_qr_refresh_task(session_id: str) -> None:
    task = _QR_REFRESH_TASKS.pop(session_id, None)
    if task and not task.done():
        task.cancel()


def _track_qr_refresh_task(session_id: str, task: asyncio.Task[None]) -> None:
    _QR_REFRESH_TASKS[session_id] = task

    def _cleanup(done_task: asyncio.Task[None]) -> None:
        current = _QR_REFRESH_TASKS.get(session_id)
        if current is done_task:
            _QR_REFRESH_TASKS.pop(session_id, None)

    task.add_done_callback(_cleanup)


def _ensure_qr_refresh_task(session_id: str) -> None:
    existing = _QR_REFRESH_TASKS.get(session_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(_auto_refresh_qr_loop(session_id))
    _track_qr_refresh_task(session_id, task)


async def _auto_refresh_qr_loop(session_id: str) -> None:
    while True:
        await asyncio.sleep(_QR_AUTO_REFRESH_SECONDS)

        session = get_session(session_id)
        if not session:
            _cancel_qr_refresh_task(session_id)
            return

        status = await check_login_status(session.page)
        session.status = status
        session.last_used = datetime.utcnow()
        save_session(session)

        if status == "confirmed":
            _cancel_qr_refresh_task(session_id)
            return

        if status not in {"waiting_scan", "qr_expired"}:
            continue

        try:
            profile_lock = get_profile_lock(session.user_id)
            async with profile_lock:
                qr_base64 = await refresh_qr_with_previous(
                    session.page,
                    previous_signature=session.qr_signature,
                )
            session.status = "waiting_scan"
            session.qr_base64 = qr_base64
            session.qr_signature = qr_signature(qr_base64)
            session.last_used = datetime.utcnow()
            save_session(session)
            logger.info(f"Auto-refreshed QR for session {session_id}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Auto QR refresh failed for session {session_id}: {exc}")

def _normalize_user_id(x_user_id: str | None) -> str:
    raw = (x_user_id or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


def _build_session_id(user_id: str) -> str:
    return f"{user_id}--{uuid.uuid4().hex}"


def _serialize_login_state(request: Request, user_id: str, session: SessionData | None, status: str) -> dict:
    manual_viewer_url = (settings.browser_remote_viewer_url or "").strip() or None
    return {
        "user_id": user_id,
        "session_id": session.session_id if session else None,
        "status": status,
        "is_logged_in": status == "confirmed",
        "can_crawl": status == "confirmed",
        "login_url": None,
        "manual_viewer_url": manual_viewer_url,
        "qr_base64": session.qr_base64 if session else None,
    }


async def _build_current_status_payload(request: Request, user_id: str) -> dict:
    session = get_latest_session_for_user(user_id)
    if not session:
        return _serialize_login_state(request, user_id, None, "not_logged_in")

    status = await check_login_status(session.page)
    session.status = status
    session.last_used = datetime.utcnow()
    save_session(session)
    if status == "confirmed":
        _cancel_qr_refresh_task(session.session_id)
    return _serialize_login_state(request, user_id, session, status)


async def _open_manual_login_page(page) -> None:
    await page.goto("https://chat.zalo.me/", wait_until="domcontentloaded")
    try:
        await page.bring_to_front()
    except Exception:
        pass


async def _close_browser_resources(browser, context) -> None:
    if context:
        try:
            await context.close()
        except Exception:
            pass
    if browser:
        try:
            await browser.close()
        except Exception:
            pass


async def _create_or_reuse_manual_session(user_id: str) -> dict:
    manual_viewer_url = (settings.browser_remote_viewer_url or "").strip() or None
    profile_lock = get_profile_lock(user_id)

    try:
        async with profile_lock:
            existing = get_latest_session_for_user(user_id)
            if existing:
                status = await check_login_status(existing.page)
                existing.status = status
                existing.last_used = datetime.utcnow()
                save_session(existing)
                return {
                    "user_id": user_id,
                    "session_id": existing.session_id,
                    "status": status,
                    "can_crawl": status == "confirmed",
                    "manual_viewer_url": manual_viewer_url,
                }

            session_id = _build_session_id(user_id)
            browser, context, page = await create_browser(user_id=user_id)
            await _open_manual_login_page(page)
            status = await check_login_status(page)

            session = SessionData(
                session_id=session_id,
                user_id=user_id,
                browser=browser,
                context=context,
                page=page,
                status=status,
                qr_base64=None,
                qr_signature=None,
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow(),
            )
            save_session(session)
            return {
                "user_id": user_id,
                "session_id": session_id,
                "status": status,
                "can_crawl": status == "confirmed",
                "manual_viewer_url": manual_viewer_url,
            }
    except Exception as exc:
        await _close_browser_resources(locals().get("browser"), locals().get("context"))
        logger.exception(f"Manual login init failed: {type(exc).__name__}: {exc!r}")
        raise HTTPException(
            status_code=503,
            detail=f"Manual login init failed: {type(exc).__name__}",
        )


async def _create_or_reuse_waiting_session(user_id: str) -> dict:
    profile_lock = get_profile_lock(user_id)
    try:
        async with profile_lock:
            existing = get_latest_waiting_session(user_id=user_id, max_age_seconds=120)
            if existing:
                try:
                    live_status = await check_login_status(existing.page)
                    existing.status = live_status
                    existing.last_used = datetime.utcnow()
                    if live_status == "confirmed":
                        existing.qr_base64 = None
                        existing.qr_signature = None
                        save_session(existing)
                        _cancel_qr_refresh_task(existing.session_id)
                        logger.info(
                            f"Reused active waiting session already confirmed: {existing.session_id} for user={user_id}"
                        )
                        return {
                            "user_id": user_id,
                            "session_id": existing.session_id,
                            "qr_base64": "",
                            "status": "confirmed",
                            "expires_in": 120,
                        }
                    qr_base64 = await refresh_qr_with_previous(
                        existing.page,
                        previous_signature=existing.qr_signature,
                    )
                    existing.status = "waiting_scan"
                    existing.qr_base64 = qr_base64
                    existing.qr_signature = qr_signature(qr_base64)
                    existing.last_used = datetime.utcnow()
                    save_session(existing)
                    _ensure_qr_refresh_task(existing.session_id)
                    logger.info(f"Reused active waiting session: {existing.session_id} for user={user_id}")
                    return {
                        "user_id": user_id,
                        "session_id": existing.session_id,
                        "qr_base64": qr_base64,
                        "status": "waiting_scan",
                        "expires_in": 120,
                    }
                except Exception as exc:
                    logger.warning(f"Could not reuse waiting session {existing.session_id} for user={user_id}: {exc}")

            session_id = _build_session_id(user_id)
            browser = None
            context = None
            browser, context, page = await create_browser(user_id=user_id)
            live_status = await check_login_status(page)
            if live_status == "confirmed":
                session = SessionData(
                    session_id=session_id,
                    user_id=user_id,
                    browser=browser,
                    context=context,
                    page=page,
                    status="confirmed",
                    qr_base64=None,
                    qr_signature=None,
                    created_at=datetime.utcnow(),
                    last_used=datetime.utcnow(),
                )
                save_session(session)
                logger.info(f"Auth init found existing logged-in Zalo session for user={user_id}")
                return {
                    "user_id": user_id,
                    "session_id": session_id,
                    "qr_base64": "",
                    "status": "confirmed",
                    "expires_in": 120,
                }
            qr_base64 = await navigate_and_get_qr(page)

            session = SessionData(
                session_id=session_id,
                user_id=user_id,
                browser=browser,
                context=context,
                page=page,
                status="waiting_scan",
                qr_base64=qr_base64,
                qr_signature=qr_signature(qr_base64),
                created_at=datetime.utcnow(),
                last_used=datetime.utcnow(),
            )
            save_session(session)
            _ensure_qr_refresh_task(session_id)

            return {
                "user_id": user_id,
                "session_id": session_id,
                "qr_base64": qr_base64,
                "status": "waiting_scan",
                "expires_in": 120,
            }
    except ZaloAlreadyLoggedInError:
        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            browser=browser,
            context=context,
            page=page,
            status="confirmed",
            qr_base64=None,
            qr_signature=None,
            created_at=datetime.utcnow(),
            last_used=datetime.utcnow(),
        )
        save_session(session)
        logger.info(f"Auth init detected confirmed Zalo session after wait for user={user_id}")
        return {
            "user_id": user_id,
            "session_id": session_id,
            "qr_base64": "",
            "status": "confirmed",
            "expires_in": 120,
        }
    except PlaywrightError as exc:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        message = str(exc).strip()
        logger.exception(f"Auth init failed: {type(exc).__name__}: {message}")
        raise HTTPException(
            status_code=503,
            detail=f"Zalo page load failed: {message or type(exc).__name__}",
        )
    except Exception as exc:
        await _close_browser_resources(locals().get("browser"), locals().get("context"))
        logger.exception(f"Auth init failed: {type(exc).__name__}: {exc!r}")
        raise HTTPException(
            status_code=503,
            detail=f"Zalo page load failed: {type(exc).__name__}",
        )


@router.post("/init")
async def init_session(x_user_id: str = Header("default", alias="X-User-ID")):
    return await _create_or_reuse_waiting_session(_normalize_user_id(x_user_id))


@router.post("/manual-login/start")
async def start_manual_login(x_user_id: str = Header("default", alias="X-User-ID")):
    return await _create_or_reuse_manual_session(_normalize_user_id(x_user_id))


@router.post("/manual-login/resume")
async def resume_manual_login(x_user_id: str = Header("default", alias="X-User-ID")):
    user_id = _normalize_user_id(x_user_id)
    session = get_latest_session_for_user(user_id)
    if not session:
        raise HTTPException(status_code=401, detail="No active session found for manual login")

    status = await check_login_status(session.page)
    session.status = status
    session.last_used = datetime.utcnow()
    save_session(session)
    if status == "confirmed":
        _cancel_qr_refresh_task(session.session_id)

    return {
        "user_id": user_id,
        "session_id": session.session_id,
        "status": status,
        "can_crawl": status == "confirmed",
        "manual_viewer_url": (settings.browser_remote_viewer_url or "").strip() or None,
    }


@router.get("/current-status")
async def get_current_status(
    request: Request,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = _normalize_user_id(x_user_id)
    return await _build_current_status_payload(request, user_id)


@router.get("/events")
async def auth_status_events(
    request: Request,
    user_id: str = Query("default"),
):
    normalized_user_id = _normalize_user_id(user_id)

    async def _event_stream():
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await _build_current_status_payload(request, normalized_user_id)
                payload_json = json.dumps(payload, ensure_ascii=False)
                if payload_json != last_payload:
                    last_payload = payload_json
                    yield f"event: auth-status\ndata: {payload_json}\n\n"
                else:
                    yield "event: heartbeat\ndata: {}\n\n"
            except Exception as exc:
                logger.warning(f"SSE auth status stream error for user={normalized_user_id}: {exc}")
                yield "event: error\ndata: {\"message\":\"status_stream_error\"}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/qr-image/{session_id}")
async def qr_image(session_id: str, x_user_id: str = Header("default", alias="X-User-ID")):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found")
    if session.user_id != _normalize_user_id(x_user_id):
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    screenshot_bytes = await session.page.screenshot(full_page=False)
    return Response(content=screenshot_bytes, media_type="image/png")


@router.get("/status/{session_id}")
async def get_status(session_id: str, x_user_id: str = Header("default", alias="X-User-ID")):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found, please login")
    if session.user_id != _normalize_user_id(x_user_id):
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    status = await check_login_status(session.page)
    session.status = status
    save_session(session)
    if status == "confirmed":
        _cancel_qr_refresh_task(session_id)
    return {"user_id": _normalize_user_id(x_user_id), "session_id": session_id, "status": status}


@router.delete("/session/{session_id}")
async def logout(session_id: str, x_user_id: str = Header("default", alias="X-User-ID")):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found")
    if session.user_id != _normalize_user_id(x_user_id):
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    user_id = _normalize_user_id(x_user_id)
    _cancel_qr_refresh_task(session_id)
    removed = await delete_sessions_for_user(user_id)

    profile_cleared = False
    try:
        profile_lock = get_profile_lock(user_id)
        async with profile_lock:
            profile_cleared = clear_user_profile_data(user_id)
    except Exception as exc:
        logger.warning(f"Failed to clear profile data for user={user_id} after logout: {exc}")

    return {
        "user_id": user_id,
        "message": "Logged out and cleared login data",
        "removed": removed,
        "profile_cleared": profile_cleared,
    }


@router.delete("/sessions")
async def logout_all_sessions(x_user_id: str = Header("default", alias="X-User-ID")):
    user_id = _normalize_user_id(x_user_id)
    removed = await delete_sessions_for_user(user_id)
    profile_cleared = False
    try:
        profile_lock = get_profile_lock(user_id)
        async with profile_lock:
            profile_cleared = clear_user_profile_data(user_id)
    except Exception as exc:
        logger.warning(f"Failed to clear profile data for user={user_id}: {exc}")

    return {
        "user_id": user_id,
        "message": f"Closed {removed} session(s) and cleared login data",
        "removed": removed,
        "profile_cleared": profile_cleared,
    }
