from typing import Dict, Optional
import asyncio
import base64
import re
import uuid
from datetime import datetime
import time

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
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
    qr_element_screenshot_bytes,
    refresh_qr_with_previous,
)
from app.modules.zalo.schemas.session import SessionData
from app.modules.zalo.services.session_store import (
    delete_session,
    delete_sessions_for_user,
    get_latest_session_for_user,
    get_latest_waiting_session,
    get_profile_lock,
    get_session,
    save_session,
)
from app.modules.zalo.services.supabase_service import upsert_zalo_user
from app.modules.zalo.services.zca_auth_store import (
    delete_zca_auth,
    ensure_session_zca_auth,
    load_zca_auth,
    save_zca_auth,
)
from app.modules.zalo.services.zca_persistent_listener import (
    get_listener_status,
    start_listener,
    stop_listener,
)
from app.modules.zalo.services.zca_qr_bridge import (
    import_zca_auth_to_context,
    read_zca_event,
    start_zca_qr_process,
)
from app.modules.zalo.api.security import verify_zalo_api_key

router = APIRouter(
    prefix="/api/zalo/auth",
    tags=["zalo-auth"],
    dependencies=[Depends(verify_zalo_api_key)],
)

_QR_REFRESH_TASKS: Dict[str, asyncio.Task] = {}
_QR_AUTO_REFRESH_SECONDS = 110
_PROFILE_RESUME_MISS_AT: Dict[str, float] = {}
_PROFILE_RESUME_MISS_COOLDOWN_SECONDS = 30
_QR_INIT_TIMEOUT_SECONDS = 90


def _cancel_qr_refresh_task(session_id: str) -> None:
    task = _QR_REFRESH_TASKS.pop(session_id, None)
    if task and not task.done():
        task.cancel()


def _track_qr_refresh_task(session_id: str, task: asyncio.Task) -> None:
    _QR_REFRESH_TASKS[session_id] = task

    def _cleanup(done_task: asyncio.Task) -> None:
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

        session = await get_session(session_id)
        if not session:
            _cancel_qr_refresh_task(session_id)
            return

        if not session.page:
            if session.status in {"confirmed", "qr_expired"}:
                _cancel_qr_refresh_task(session_id)
                return
            continue

        status = await check_login_status(session.page)
        session.status = status
        session.last_used = datetime.utcnow()
        await save_session(session)

        if status == "confirmed":
            _cancel_qr_refresh_task(session_id)
            return

        if status != "qr_expired":
            continue

        try:
            profile_lock = await get_profile_lock(session.user_id)
            async with profile_lock:
                qr_base64 = await refresh_qr_with_previous(
                    session.page,
                    previous_signature=session.qr_signature,
                )
            session.status = "waiting_scan"
            session.qr_base64 = qr_base64
            session.qr_signature = qr_signature(qr_base64)
            session.last_used = datetime.utcnow()
            await save_session(session)
            logger.info(f"Auto-refreshed QR for session {session_id}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Auto QR refresh failed for session {session_id}: {exc}")
            try:
                await delete_session(session_id)
                await _create_or_reuse_waiting_session(session.user_id, force_new=True)
                logger.info(f"Recreated QR session after auto-refresh failure for user={session.user_id}")
            except Exception as recreate_exc:
                logger.warning(
                    f"Could not recreate QR session after auto-refresh failure for user={session.user_id}: "
                    f"{recreate_exc}"
                )
            _cancel_qr_refresh_task(session_id)
            return

def _normalize_user_id(x_user_id: Optional[str]) -> str:
    raw = (x_user_id or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


def _build_session_id(user_id: str) -> str:
    return f"{user_id}--{uuid.uuid4().hex}"


async def _remember_zalo_user(user_id: str, status: str, worker_id: Optional[str] = None) -> None:
    try:
        await upsert_zalo_user(user_id, status=status, assigned_worker_id=worker_id)
    except Exception as exc:
        logger.warning(f"Could not upsert Zalo user metadata for user={user_id}: {exc}")


def _serialize_login_state(request: Request, user_id: str, session: Optional[SessionData], status: str) -> dict:
    manual_viewer_url = (settings.browser_remote_viewer_url or "").strip() or None
    qr_base64 = session.qr_base64 if session and status == "waiting_scan" else None
    return {
        "user_id": user_id,
        "session_id": session.session_id if session else None,
        "status": status,
        "is_logged_in": status == "confirmed",
        "can_crawl": status == "confirmed",
        "session_expired": status == "session_expired",
        "login_url": None,
        "manual_viewer_url": manual_viewer_url,
        "qr_base64": qr_base64,
    }


async def _resume_confirmed_profile_session(user_id: str) -> Optional[SessionData]:
    """Re-open a persistent Chromium profile when the in-memory session was lost."""
    if not settings.browser_persistent_profile:
        return None
    last_miss_at = _PROFILE_RESUME_MISS_AT.get(user_id, 0)
    if time.monotonic() - last_miss_at < _PROFILE_RESUME_MISS_COOLDOWN_SECONDS:
        return None

    profile_lock = await get_profile_lock(user_id)
    browser = None
    context = None
    page = None
    async with profile_lock:
        existing = await get_latest_session_for_user(user_id)
        if existing:
            return existing

        try:
            browser, context, page = await create_browser(user_id=user_id)
            await _open_manual_login_page(page)
            status = await check_login_status(page)
            if status != "confirmed":
                await _close_browser_resources(browser, context)
                _PROFILE_RESUME_MISS_AT[user_id] = time.monotonic()
                return None

            session = SessionData(
                session_id=_build_session_id(user_id),
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
            await save_session(session)
            _PROFILE_RESUME_MISS_AT.pop(user_id, None)
            logger.info(f"Resumed confirmed Zalo profile session for user={user_id}")
            return session
        except Exception as exc:
            await _close_browser_resources(browser, context)
            _PROFILE_RESUME_MISS_AT[user_id] = time.monotonic()
            logger.warning(f"Could not resume Zalo profile session for user={user_id}: {exc}")
            return None


async def _build_current_status_payload(request: Request, user_id: str) -> dict:
    session = await get_latest_session_for_user(user_id)
    if settings.qr_login_mode.strip().lower() == "zca":
        if session:
            await ensure_session_zca_auth(session)
        else:
            auth = await load_zca_auth(user_id)
            if auth:
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
                logger.info(f"Restored confirmed ZCA session from auth store for user={user_id}")

    if not session and settings.qr_login_mode.strip().lower() != "zca":
        session = await _resume_confirmed_profile_session(user_id)
    if not session:
        return _serialize_login_state(request, user_id, None, "not_logged_in")

    if await ensure_session_zca_auth(session):
        # Trong zca mode, file auth vẫn tồn tại kể cả khi cookie đã chết.
        # Nếu persistent listener báo phiên hết hạn => yêu cầu đăng nhập lại bằng QR.
        if settings.qr_login_mode.strip().lower() == "zca":
            listener = get_listener_status(user_id)
            if listener.get("auth_expired"):
                logger.warning(f"ZCA session expired for user={user_id} — cleaning up ZCA auth and prompting re-login")
                await delete_zca_auth(user_id)
                session.status = "session_expired"
                session.zca_auth = None
                await save_session(session)
                return _serialize_login_state(request, user_id, session, "session_expired")
        if session.status != "confirmed":
            session.status = "confirmed"
            session.qr_base64 = None
            session.qr_signature = None
            session.last_used = datetime.utcnow()
            await save_session(session)
        logger.info(f"Returning confirmed ZCA status for user={user_id}, session={session.session_id}")
        return _serialize_login_state(request, user_id, session, "confirmed")

    if not session.page:
        return _serialize_login_state(request, user_id, session, session.status)

    status = await check_login_status(session.page)
    session.status = status
    session.last_used = datetime.utcnow()
    if status == "qr_expired":
        session.qr_base64 = None
        session.qr_signature = None
    await save_session(session)
    if status == "confirmed":
        _cancel_qr_refresh_task(session.session_id)
    await _remember_zalo_user(
        user_id,
        status,
        worker_id=request.headers.get("X-Zalo-Worker-ID"),
    )
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


async def _open_confirmed_browser_from_zca_auth(user_id: str, auth: dict):
    browser, context, page = await create_browser(user_id=user_id)
    await import_zca_auth_to_context(context, auth)
    await _open_manual_login_page(page)
    await page.wait_for_timeout(1500)
    status = await check_login_status(page)
    if status != "confirmed":
        logger.warning(f"Imported ZCA cookies but Playwright status is {status} for user={user_id}")
    return browser, context, page, status


async def _handle_zca_qr_events(session_id: str) -> None:
    while True:
        session = await get_session(session_id)
        if not session or not session.qr_process:
            return

        event = await read_zca_event(session.qr_process)
        if not event:
            if session.qr_process.returncode is not None:
                if session.status not in {"confirmed", "qr_expired"}:
                    session.status = "qr_expired"
                    session.qr_base64 = None
                    session.qr_signature = None
                    session.last_used = datetime.utcnow()
                    await save_session(session)
                return
            await asyncio.sleep(0.2)
            continue

        event_type = event.get("type")
        if event_type == "qr":
            qr_base64 = event.get("qr_base64") or ""
            if qr_base64:
                session.status = "waiting_scan"
                session.qr_base64 = qr_base64
                session.qr_signature = qr_signature(qr_base64)
                session.last_used = datetime.utcnow()
                await save_session(session)
                logger.info(f"ZCA QR updated for session {session_id}")
            continue

        if event_type == "status":
            status = event.get("status")
            if status in {"qr_expired", "declined"}:
                session.status = "qr_expired"
                session.qr_base64 = None
                session.qr_signature = None
                session.last_used = datetime.utcnow()
                await save_session(session)
                logger.info(f"ZCA QR session {session_id} status={status}")
                return
            if status == "scanned":
                session.qr_base64 = None
                session.qr_signature = None
                session.last_used = datetime.utcnow()
                await save_session(session)
            logger.info(f"ZCA QR session {session_id} status={status}")
            continue

        if event_type == "success":
            auth = event.get("auth") or {}
            session.status = "confirmed"
            session.browser = None
            session.context = None
            session.page = None
            session.qr_base64 = None
            session.qr_signature = None
            session.zca_auth = auth
            session.last_used = datetime.utcnow()
            await save_session(session)
            await save_zca_auth(session.user_id, auth)
            try:
                await start_listener(session.user_id, auth, force_restart=True)
            except Exception as exc:
                logger.warning(f"Could not start ZCA persistent listener for user={session.user_id}: {exc}")
            await _remember_zalo_user(session.user_id, "confirmed")
            logger.info(f"ZCA QR login success for session {session_id}")
            return

        if event_type == "error":
            session.status = "qr_expired"
            session.qr_base64 = None
            session.qr_signature = None
            session.last_used = datetime.utcnow()
            await save_session(session)
            logger.warning(f"ZCA QR login error for session {session_id}: {event.get('message')}")
            return


async def _create_zca_waiting_session(user_id: str) -> dict:
    session_id = _build_session_id(user_id)
    proc = await start_zca_qr_process(session_id)

    session = SessionData(
        session_id=session_id,
        user_id=user_id,
        browser=None,
        context=None,
        page=None,
        status="waiting_scan",
        qr_base64=None,
        qr_signature=None,
        qr_process=proc,
        created_at=datetime.utcnow(),
        last_used=datetime.utcnow(),
    )
    await save_session(session)

    first_qr: Optional[str] = None
    for _ in range(30):
        event = await read_zca_event(proc, timeout_seconds=1)
        if not event:
            if proc.returncode is not None:
                stderr = ""
                if proc.stderr:
                    try:
                        stderr = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
                    except Exception:
                        stderr = ""
                if stderr:
                    raise RuntimeError(f"ZCA QR helper exited: {stderr[:500]}")
                break
            continue
        if event.get("type") == "qr" and event.get("qr_base64"):
            first_qr = event["qr_base64"]
            session.qr_base64 = first_qr
            session.qr_signature = qr_signature(first_qr)
            session.last_used = datetime.utcnow()
            await save_session(session)
            break
        if event.get("type") == "error":
            raise RuntimeError(event.get("message") or "ZCA QR helper failed")

    if not first_qr:
        await delete_session(session_id)
        raise RuntimeError("ZCA QR helper did not return a QR code")

    _track_qr_refresh_task(session_id, asyncio.create_task(_handle_zca_qr_events(session_id)))
    return {
        "user_id": user_id,
        "session_id": session_id,
        "qr_base64": first_qr,
        "status": "waiting_scan",
        "expires_in": 120,
    }


async def _create_or_reuse_manual_session(user_id: str) -> dict:
    manual_viewer_url = (settings.browser_remote_viewer_url or "").strip() or None
    profile_lock = await get_profile_lock(user_id)

    try:
        async with profile_lock:
            existing = await get_latest_session_for_user(user_id)
            if existing:
                status = await check_login_status(existing.page)
                existing.status = status
                existing.last_used = datetime.utcnow()
                await save_session(existing)
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
            await save_session(session)
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


async def _create_or_reuse_waiting_session(user_id: str, force_new: bool = False) -> dict:
    profile_lock = await get_profile_lock(user_id)
    # FIX C-1 & C-2: Khai báo tất cả biến trước try block để tránh NameError
    # trong ZaloAlreadyLoggedInError handler và tránh dùng locals() không tin cậy.
    session_id: str = _build_session_id(user_id)
    browser = None
    context = None
    page = None
    try:
        async with profile_lock:
            if settings.qr_login_mode.strip().lower() == "zca":
                listener = get_listener_status(user_id)
                if listener.get("auth_expired"):
                    logger.info(f"Persistent listener reported auth expired for user={user_id}. Cleaning up ZCA credentials.")
                    await delete_zca_auth(user_id)
                    await delete_sessions_for_user(user_id)
                    confirmed = None
                else:
                    confirmed = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})

                if confirmed and await ensure_session_zca_auth(confirmed):
                    logger.info(f"ZCA session already confirmed for user={user_id}: {confirmed.session_id}")
                    return {
                        "user_id": user_id,
                        "session_id": confirmed.session_id,
                        "qr_base64": "",
                        "status": "confirmed",
                        "expires_in": 120,
                    }

                if not force_new and not listener.get("auth_expired"):
                    auth = await load_zca_auth(user_id)
                    if auth:
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
                        logger.info(f"Reused persisted ZCA auth for user={user_id}: {session.session_id}")
                        return {
                            "user_id": user_id,
                            "session_id": session.session_id,
                            "qr_base64": "",
                            "status": "confirmed",
                            "expires_in": 120,
                        }

                existing = None if force_new else await get_latest_waiting_session(user_id=user_id, max_age_seconds=120)
                if existing and existing.qr_base64 and existing.status == "waiting_scan":
                    logger.info(f"Reused active ZCA waiting QR: {existing.session_id} for user={user_id}")
                    return {
                        "user_id": user_id,
                        "session_id": existing.session_id,
                        "qr_base64": existing.qr_base64,
                        "status": "waiting_scan",
                        "expires_in": 120,
                    }
                if existing:
                    await delete_session(existing.session_id)
                await delete_sessions_for_user(user_id)
                return await _create_zca_waiting_session(user_id)

            existing = None if force_new else await get_latest_waiting_session(user_id=user_id, max_age_seconds=120)
            if existing:
                try:
                    live_status = await check_login_status(existing.page)
                    existing.status = live_status
                    existing.last_used = datetime.utcnow()
                    if live_status == "confirmed":
                        existing.qr_base64 = None
                        existing.qr_signature = None
                        await save_session(existing)
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
                    if live_status == "qr_expired" or not existing.qr_base64:
                        qr_base64 = await refresh_qr_with_previous(
                            existing.page,
                            previous_signature=existing.qr_signature,
                        )
                        existing.status = "waiting_scan"
                        existing.qr_base64 = qr_base64
                        existing.qr_signature = qr_signature(qr_base64)
                        existing.last_used = datetime.utcnow()
                        logger.info(f"Refreshed expired waiting session QR: {existing.session_id} for user={user_id}")
                    else:
                        qr_base64 = existing.qr_base64
                        logger.info(f"Reused active waiting QR without refresh: {existing.session_id} for user={user_id}")
                    await save_session(existing)
                    _ensure_qr_refresh_task(existing.session_id)
                    return {
                        "user_id": user_id,
                        "session_id": existing.session_id,
                        "qr_base64": qr_base64,
                        "status": "waiting_scan",
                        "expires_in": 120,
                    }
                except Exception as exc:
                    logger.warning(f"Could not reuse waiting session {existing.session_id} for user={user_id}: {exc}")
                    await delete_session(existing.session_id)

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
                await save_session(session)
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
            await save_session(session)
            _ensure_qr_refresh_task(session_id)

            return {
                "user_id": user_id,
                "session_id": session_id,
                "qr_base64": qr_base64,
                "status": "waiting_scan",
                "expires_in": 120,
            }
    except ZaloAlreadyLoggedInError:
        # FIX C-1: session_id/browser/context/page đã được khai báo ở trên,
        # không còn bị NameError dù exception xảy ra sớm.
        if browser and context and page:
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
            await save_session(session)
            logger.info(f"Auth init detected confirmed Zalo session after wait for user={user_id}")
            return {
                "user_id": user_id,
                "session_id": session_id,
                "qr_base64": "",
                "status": "confirmed",
                "expires_in": 120,
            }
        # browser chưa được khởi tạo khi exception xảy ra
        raise HTTPException(status_code=503, detail="Zalo session init failed unexpectedly")
    except PlaywrightError as exc:
        # FIX C-2: Dùng biến trực tiếp thay vì locals() không đáng tin cậy
        await _close_browser_resources(browser, context)
        message = str(exc).strip()
        logger.exception(f"Auth init failed: {type(exc).__name__}: {message}")
        raise HTTPException(
            status_code=503,
            detail=f"Zalo page load failed: {message or type(exc).__name__}",
        )
    except Exception as exc:
        # FIX C-2: Dùng biến trực tiếp thay vì locals()
        await _close_browser_resources(browser, context)
        logger.exception(f"Auth init failed: {type(exc).__name__}: {exc!r}")
        raise HTTPException(
            status_code=503,
            detail=f"Zalo page load failed: {type(exc).__name__}",
        )


@router.post("/init")
async def init_session(
    x_user_id: str = Header("default", alias="X-User-ID"),
    x_zalo_worker_id: Optional[str] = Header(None, alias="X-Zalo-Worker-ID"),
):
    user_id = _normalize_user_id(x_user_id)
    try:
        payload = await asyncio.wait_for(
            _create_or_reuse_waiting_session(user_id),
            timeout=_QR_INIT_TIMEOUT_SECONDS,
        )
        await _remember_zalo_user(user_id, str(payload.get("status") or "unknown"), x_zalo_worker_id)
        return payload
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Zalo QR init timed out. Close stale Zalo/Chrome sessions and try again.",
        )


@router.post("/qr/refresh")
async def refresh_login_qr(
    x_user_id: str = Header("default", alias="X-User-ID"),
    x_zalo_worker_id: Optional[str] = Header(None, alias="X-Zalo-Worker-ID"),
):
    user_id = _normalize_user_id(x_user_id)
    profile_lock = await get_profile_lock(user_id)
    async with profile_lock:
        existing = await get_latest_session_for_user(user_id)
    if not existing:
        try:
            payload = await asyncio.wait_for(
                _create_or_reuse_waiting_session(user_id),
                timeout=_QR_INIT_TIMEOUT_SECONDS,
            )
            await _remember_zalo_user(user_id, str(payload.get("status") or "unknown"), x_zalo_worker_id)
            return payload
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Zalo QR init timed out. Close stale Zalo/Chrome sessions and try again.",
            )

    if settings.qr_login_mode.strip().lower() == "zca":
        if await ensure_session_zca_auth(existing):
            existing.status = "confirmed"
            existing.qr_base64 = None
            existing.qr_signature = None
            existing.last_used = datetime.utcnow()
            await save_session(existing)
            await _remember_zalo_user(user_id, "confirmed", x_zalo_worker_id)
            return {
                "user_id": user_id,
                "session_id": existing.session_id,
                "qr_base64": "",
                "status": "confirmed",
                "expires_in": 120,
            }
        if existing:
            await delete_session(existing.session_id)
        try:
            payload = await asyncio.wait_for(
                _create_or_reuse_waiting_session(user_id, force_new=True),
                timeout=_QR_INIT_TIMEOUT_SECONDS,
            )
            await _remember_zalo_user(user_id, str(payload.get("status") or "unknown"), x_zalo_worker_id)
            return payload
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Zalo QR refresh timed out while creating a ZCA QR session.",
            )

    async with profile_lock:
        status = await check_login_status(existing.page)
        existing.status = status
        existing.last_used = datetime.utcnow()
        if status == "confirmed":
            existing.qr_base64 = None
            existing.qr_signature = None
            await save_session(existing)
            _cancel_qr_refresh_task(existing.session_id)
            await _remember_zalo_user(user_id, "confirmed", x_zalo_worker_id)
            return {
                "user_id": user_id,
                "session_id": existing.session_id,
                "qr_base64": "",
                "status": "confirmed",
                "expires_in": 120,
            }

        try:
            qr_base64 = await refresh_qr_with_previous(
                existing.page,
                previous_signature=existing.qr_signature,
            )
            new_signature = qr_signature(qr_base64)
            if existing.qr_signature and new_signature == existing.qr_signature:
                raise RuntimeError("QR refresh returned the same signature")
            existing.status = "waiting_scan"
            existing.qr_base64 = qr_base64
            existing.qr_signature = new_signature
            existing.last_used = datetime.utcnow()
            await save_session(existing)
            await _remember_zalo_user(user_id, "waiting_scan", x_zalo_worker_id)
            _ensure_qr_refresh_task(existing.session_id)
            return {
                "user_id": user_id,
                "session_id": existing.session_id,
                "qr_base64": qr_base64,
                "status": "waiting_scan",
                "expires_in": 120,
            }
        except Exception as exc:
            logger.warning(
                f"QR refresh failed for session {existing.session_id}; recreating session for user={user_id}: {exc}"
            )
            await delete_session(existing.session_id)

    try:
        payload = await asyncio.wait_for(
            _create_or_reuse_waiting_session(user_id, force_new=True),
            timeout=_QR_INIT_TIMEOUT_SECONDS,
        )
        await _remember_zalo_user(user_id, str(payload.get("status") or "unknown"), x_zalo_worker_id)
        return payload
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Zalo QR refresh timed out while recreating the browser session.",
        )


@router.post("/manual-login/start")
async def start_manual_login(
    x_user_id: str = Header("default", alias="X-User-ID"),
    x_zalo_worker_id: Optional[str] = Header(None, alias="X-Zalo-Worker-ID"),
):
    user_id = _normalize_user_id(x_user_id)
    payload = await _create_or_reuse_manual_session(user_id)
    await _remember_zalo_user(user_id, str(payload.get("status") or "unknown"), x_zalo_worker_id)
    return payload


@router.post("/manual-login/resume")
async def resume_manual_login(
    x_user_id: str = Header("default", alias="X-User-ID"),
    x_zalo_worker_id: Optional[str] = Header(None, alias="X-Zalo-Worker-ID"),
):
    user_id = _normalize_user_id(x_user_id)
    session = await get_latest_session_for_user(user_id)
    if not session:
        raise HTTPException(status_code=401, detail="No active session found for manual login")

    status = await check_login_status(session.page)
    session.status = status
    session.last_used = datetime.utcnow()
    await save_session(session)
    if status == "confirmed":
        _cancel_qr_refresh_task(session.session_id)
    await _remember_zalo_user(user_id, status, x_zalo_worker_id)

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
    # FIX H-2: Đặt deadline 10 phút để tránh SSE stream chạy vĩnh viễn
    # sau khi client ngắt kết nối hoặc sau khi đã xác nhận đăng nhập.
    _SSE_MAX_SECONDS = 600

    async def _event_stream():
        last_payload = ""
        deadline = asyncio.get_event_loop().time() + _SSE_MAX_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            if await request.is_disconnected():
                logger.info(f"SSE client disconnected for user={normalized_user_id}")
                break
            try:
                payload = await _build_current_status_payload(request, normalized_user_id)
                payload_json = json.dumps(payload, ensure_ascii=False)
                if payload_json != last_payload:
                    last_payload = payload_json
                    yield f"event: auth-status\ndata: {payload_json}\n\n"
                    # FIX H-2: Dừng stream ngay khi đã xác nhận đăng nhập
                    if payload.get("is_logged_in"):
                        logger.info(f"SSE stream closing — user={normalized_user_id} confirmed login")
                        yield "event: close\ndata: {}\n\n"
                        return
                else:
                    yield "event: heartbeat\ndata: {}\n\n"
            except Exception as exc:
                logger.warning(f"SSE auth status stream error for user={normalized_user_id}: {exc}")
                yield "event: error\ndata: {\"message\":\"status_stream_error\"}\n\n"
            await asyncio.sleep(2)
        # Hết deadline hoặc thoát vòng lặp
        yield "event: close\ndata: {\"reason\":\"timeout\"}\n\n"

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
async def qr_image(
    session_id: str,
    x_user_id: str = Header("default", alias="X-User-ID"),
    user_id: Optional[str] = Query(default=None),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found")
    normalized_user_id = _normalize_user_id(user_id or x_user_id)
    if session.user_id != normalized_user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    if await ensure_session_zca_auth(session) or session.status != "waiting_scan":
        raise HTTPException(status_code=404, detail="QR image is not available for this session status")

    if session.qr_base64:
        try:
            _, encoded = session.qr_base64.split(",", 1)
            return Response(content=base64.b64decode(encoded), media_type="image/png")
        except Exception as exc:
            logger.warning(f"Could not decode cached QR for session {session_id}: {exc}")

    if not session.page:
        raise HTTPException(status_code=404, detail="QR image is not ready")

    screenshot_bytes = await qr_element_screenshot_bytes(session.page)
    if not screenshot_bytes:
        raise HTTPException(status_code=404, detail="QR image is not ready")
    return Response(content=screenshot_bytes, media_type="image/png")


@router.get("/status/{session_id}")
async def get_status(
    session_id: str,
    x_user_id: str = Header("default", alias="X-User-ID"),
    x_zalo_worker_id: Optional[str] = Header(None, alias="X-Zalo-Worker-ID"),
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found, please login")
    if session.user_id != _normalize_user_id(x_user_id):
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    if await ensure_session_zca_auth(session):
        if session.status != "confirmed":
            session.status = "confirmed"
            session.qr_base64 = None
            session.qr_signature = None
            await save_session(session)
        await _remember_zalo_user(_normalize_user_id(x_user_id), "confirmed", x_zalo_worker_id)
        return {"user_id": _normalize_user_id(x_user_id), "session_id": session_id, "status": "confirmed"}

    if not session.page:
        await _remember_zalo_user(_normalize_user_id(x_user_id), session.status, x_zalo_worker_id)
        return {"user_id": _normalize_user_id(x_user_id), "session_id": session_id, "status": session.status}

    status = await check_login_status(session.page)
    session.status = status
    await save_session(session)
    if status == "confirmed":
        _cancel_qr_refresh_task(session_id)
    await _remember_zalo_user(_normalize_user_id(x_user_id), status, x_zalo_worker_id)
    return {"user_id": _normalize_user_id(x_user_id), "session_id": session_id, "status": status}


@router.delete("/session/{session_id}")
async def logout(session_id: str, x_user_id: str = Header("default", alias="X-User-ID")):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session not found")
    if session.user_id != _normalize_user_id(x_user_id):
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    user_id = _normalize_user_id(x_user_id)
    _cancel_qr_refresh_task(session_id)
    await stop_listener(user_id)
    removed = await delete_sessions_for_user(user_id)
    zca_auth_removed = await delete_zca_auth(user_id)

    profile_cleared = False
    try:
        profile_lock = await get_profile_lock(user_id)
        async with profile_lock:
            profile_cleared = clear_user_profile_data(user_id)
    except Exception as exc:
        logger.warning(f"Failed to clear profile data for user={user_id} after logout: {exc}")

    return {
        "user_id": user_id,
        "message": "Logged out and cleared login data",
        "removed": removed,
        "zca_auth_removed": zca_auth_removed,
        "profile_cleared": profile_cleared,
    }


@router.delete("/sessions")
async def logout_all_sessions(x_user_id: str = Header("default", alias="X-User-ID")):
    user_id = _normalize_user_id(x_user_id)
    await stop_listener(user_id)
    removed = await delete_sessions_for_user(user_id)
    zca_auth_removed = await delete_zca_auth(user_id)
    profile_cleared = False
    try:
        profile_lock = await get_profile_lock(user_id)
        async with profile_lock:
            profile_cleared = clear_user_profile_data(user_id)
    except Exception as exc:
        logger.warning(f"Failed to clear profile data for user={user_id}: {exc}")

    return {
        "user_id": user_id,
        "message": f"Closed {removed} session(s) and cleared login data",
        "removed": removed,
        "zca_auth_removed": zca_auth_removed,
        "profile_cleared": profile_cleared,
    }
