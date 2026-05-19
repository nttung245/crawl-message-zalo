"""Playwright Chromium pool — nhiều worker thread, mỗi thread một browser (Sync API / greenlet-safe)."""

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

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_state_path_locks_guard = threading.Lock()
_state_path_locks: dict[str, threading.Lock] = {}


class _ThreadPlaywright:
    playwright: Playwright | None = None
    browser: Browser | None = None


_thread_local = threading.local()


def _pool_size() -> int:
    return settings.playwright_pool_size


def _thread_slot() -> _ThreadPlaywright:
    slot = getattr(_thread_local, "slot", None)
    if slot is None:
        slot = _ThreadPlaywright()
        _thread_local.slot = slot
    return slot


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            size = _pool_size()
            _executor = ThreadPoolExecutor(
                max_workers=size,
                thread_name_prefix="playwright",
            )
            logger.info("Playwright thread pool started (max_workers=%s)", size)
        return _executor


def _lock_for_state_path(state_path: Path) -> threading.Lock:
    key = str(state_path.resolve())
    with _state_path_locks_guard:
        lock = _state_path_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _state_path_locks[key] = lock
        return lock


def _is_pool_worker_thread() -> bool:
    return threading.current_thread().name.startswith("playwright_")


def _ensure_browser_on_worker() -> Browser:
    slot = _thread_slot()
    if slot.browser is not None:
        return slot.browser
    logger.info(
        "Starting Playwright Chromium on %s (headless=%s)",
        threading.current_thread().name,
        settings.headless,
    )
    slot.playwright = sync_playwright().start()
    slot.browser = slot.playwright.chromium.launch(
        headless=settings.headless,
        args=list(CHROMIUM_LAUNCH_ARGS),
    )
    return slot.browser


def _stop_browser_on_worker() -> None:
    slot = _thread_slot()
    if slot.browser is not None:
        try:
            slot.browser.close()
        except Exception:
            logger.warning("Error closing browser on worker", exc_info=True)
        slot.browser = None
    if slot.playwright is not None:
        try:
            slot.playwright.stop()
        except Exception:
            logger.warning("Error stopping Playwright on worker", exc_info=True)
        slot.playwright = None


def run_playwright_sync(func: Callable[[], T]) -> T:
    """Run ``func`` on a pool worker thread and return its result."""

    if _is_pool_worker_thread():
        return func()
    return _get_executor().submit(func).result()


def _warmup_worker() -> None:
    _ensure_browser_on_worker()


def warmup_playwright_pool() -> None:
    """Pre-launch one browser per pool worker (background / lifespan)."""

    size = _pool_size()
    ex = _get_executor()
    for idx in range(size):
        ex.submit(_warmup_worker).result()
    logger.info("Playwright pool warmup finished (%s workers)", size)


def shutdown_playwright_pool() -> None:
    """Stop browsers on all workers and shut down the executor."""

    global _executor
    ex: ThreadPoolExecutor | None
    with _executor_lock:
        ex = _executor
    if ex is None:
        return

    size = _pool_size()
    for _ in range(size):
        try:
            ex.submit(_stop_browser_on_worker).result(timeout=90)
        except Exception:
            logger.warning("Playwright worker shutdown issue", exc_info=True)

    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=True, cancel_futures=False)
            _executor = None
    logger.info("Playwright pool shut down")


@contextmanager
def _linkedin_session_page_impl(
    *,
    state_path: Path,
    persist_state: bool = True,
) -> Generator[Page, None, None]:
    lock = _lock_for_state_path(state_path)
    lock.acquire()
    try:
        browser = _ensure_browser_on_worker()
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
    finally:
        lock.release()


def run_with_linkedin_session_page(
    *,
    state_path: Path,
    persist_state: bool = True,
    action: Callable[[Page], T],
) -> T:
    """Run Playwright work on a pool worker (safe from FastAPI request threads)."""

    def _inner() -> T:
        with _linkedin_session_page_impl(
            state_path=state_path,
            persist_state=persist_state,
        ) as page:
            return action(page)

    return run_playwright_sync(_inner)


def pool_status() -> dict[str, int | bool]:
    """Snapshot for /status — số worker cấu hình và headless."""

    return {
        "playwright_pool_size": _pool_size(),
        "headless": settings.headless,
    }
