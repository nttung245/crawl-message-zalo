"""Shared Playwright Chromium on a single dedicated thread (Sync API / greenlet-safe)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, TypeVar

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

CHROMIUM_LAUNCH_ARGS: tuple[str, ...] = (
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--disable-crash-reporter",
    "--disable-web-resources",
)

T = TypeVar("T")

_playwright: Playwright | None = None
_browser: Browser | None = None
_playwright_worker_id: int | None = None

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")


def _is_playwright_worker_thread() -> bool:
    return (
        _playwright_worker_id is not None
        and threading.current_thread().ident == _playwright_worker_id
    )


def run_playwright_sync(func: Callable[[], T]) -> T:
    """Run ``func`` on the dedicated Playwright thread and return its result."""

    if _is_playwright_worker_thread():
        return func()
    return _executor.submit(func).result()


def start_playwright_browser() -> None:
    """Launch Chromium once — must run on the Playwright worker thread."""

    global _playwright, _browser
    if _browser is not None:
        return
    if not _is_playwright_worker_thread():
        run_playwright_sync(start_playwright_browser)
        return
    logger.info("Starting shared Playwright Chromium browser")
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=settings.headless,
        args=list(CHROMIUM_LAUNCH_ARGS),
    )


def stop_playwright_browser() -> None:
    """Tear down browser and driver — must run on the Playwright worker thread."""

    global _playwright, _browser
    if not _is_playwright_worker_thread():
        run_playwright_sync(stop_playwright_browser)
        return
    if _browser is None and _playwright is None:
        return
    if _browser is not None:
        try:
            _browser.close()
        except Exception:
            logger.warning("Error closing shared browser", exc_info=True)
        _browser = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            logger.warning("Error stopping Playwright driver", exc_info=True)
        _playwright = None
    logger.info("Stopped shared Playwright Chromium browser")


def _register_worker_and_start() -> int:
    global _playwright_worker_id
    _playwright_worker_id = threading.current_thread().ident
    start_playwright_browser()
    return _playwright_worker_id or 0


def warmup_playwright_pool() -> None:
    """Pre-launch browser on the worker thread (FastAPI lifespan)."""

    global _playwright_worker_id
    _playwright_worker_id = _executor.submit(_register_worker_and_start).result()


def shutdown_playwright_pool() -> None:
    """Stop browser and shut down the worker executor."""

    global _playwright_worker_id

    if _playwright_worker_id is not None:
        run_playwright_sync(stop_playwright_browser)
    _executor.shutdown(wait=True, cancel_futures=False)
    _playwright_worker_id = None


def _require_browser() -> Browser:
    start_playwright_browser()
    assert _browser is not None
    return _browser


@contextmanager
def _linkedin_session_page_impl(
    *,
    state_path: Path,
    persist_state: bool = True,
) -> Generator[Page, None, None]:
    browser = _require_browser()
    context: BrowserContext = browser.new_context(storage_state=str(state_path))
    page = context.new_page()
    try:
        yield page
    finally:
        if persist_state:
            try:
                context.storage_state(path=str(state_path))
            except Exception:
                logger.warning("Could not persist storage_state", exc_info=True)
        context.close()


def run_with_linkedin_session_page(
    *,
    state_path: Path,
    persist_state: bool = True,
    action: Callable[[Page], T],
) -> T:
    """Run Playwright work on the dedicated thread (safe from FastAPI workers)."""

    def _inner() -> T:
        with _linkedin_session_page_impl(
            state_path=state_path,
            persist_state=persist_state,
        ) as page:
            return action(page)

    return run_playwright_sync(_inner)
