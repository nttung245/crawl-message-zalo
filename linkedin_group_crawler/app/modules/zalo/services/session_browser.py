from loguru import logger

from app.modules.zalo.crawler.browser import create_browser
from app.modules.zalo.crawler.qr_login import check_login_status
from app.modules.zalo.crawler.scroll_handler import wait_for_message_sync
from app.modules.zalo.schemas.session import SessionData
from app.modules.zalo.services.session_store import save_session
from app.modules.zalo.services.zca_auth_store import ensure_session_zca_auth
from app.modules.zalo.services.zca_qr_bridge import import_zca_auth_to_context


async def ensure_session_browser_ready(session: SessionData) -> str:
    if session.page:
        live_status = await check_login_status(session.page)
        session.status = live_status
        await save_session(session)
        return live_status

    zca_auth = await ensure_session_zca_auth(session)
    if not zca_auth:
        session.status = "waiting_scan"
        await save_session(session)
        return session.status

    browser = context = None
    try:
        browser, context, page = await create_browser(user_id=session.user_id)
        await import_zca_auth_to_context(context, zca_auth)
        await page.goto("https://chat.zalo.me/", wait_until="domcontentloaded", timeout=60000)

        # After importing ZCA auth, wait for the browser to reflect a confirmed login.
        # Increase the total wait time and poll periodically to account for slow loads.
        live_status = await check_login_status(page)
        logger.info(f"Initial browser login status after import: {live_status}")
        total_wait_ms = 30_000
        interval_ms = 1500
        waited = 0
        while waited < total_wait_ms:
            if live_status == "confirmed":
                break
            await page.wait_for_timeout(interval_ms)
            waited += interval_ms
            live_status = await check_login_status(page)

        if live_status != "confirmed":
            logger.warning(
                f"ZCA auth imported but browser is not crawl-ready "
                f"(session={session.session_id}, status={live_status})"
            )
            try:
                await context.close()
            except Exception:
                pass
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            return live_status

        await wait_for_message_sync(page, timeout_ms=90000)
        session.browser = browser
        session.context = context
        session.page = page
        session.status = "confirmed"
        await save_session(session)
        logger.info(f"ZCA session attached to browser for crawl: {session.session_id}")
        return "confirmed"
    except Exception:
        try:
            if context:
                await context.close()
        except Exception:
            pass
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        raise
