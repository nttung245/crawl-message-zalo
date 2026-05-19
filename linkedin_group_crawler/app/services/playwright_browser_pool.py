"""Playwright Chromium pool — nhiều worker thread, mỗi thread một browser (Sync API / greenlet-safe)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from app.config import settings
from app.services.auth_service import safe_persist_session_state
from app.services.linkedin_session_nav import (
    goto_linkedin_url,
    linkedin_browser_context_options,
    validate_storage_state_file,
)
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
    for _ in range(size):
        ex.submit(_warmup_worker).result()
    logger.info("Playwright pool warmup finished (%s workers)", size)


def _prime_session_on_current_worker(state_path: Path) -> dict[str, Any]:
    """Tải storage_state và mở LinkedIn feed trên worker hiện tại (đã có browser)."""

    worker = threading.current_thread().name
    try:
        with _linkedin_session_page_impl(
            state_path=state_path,
            persist_state=True,
        ) as page:
            active = goto_linkedin_url(
                page.context,
                page,
                settings.linkedin_session_prime_url,
                timeout_ms=settings.linkedin_session_prime_timeout_ms,
                post_load_wait_ms=max(800, settings.reaction_post_goto_settle_ms // 2),
            )
            return {
                "worker": worker,
                "ok": True,
                "final_url": active.url,
            }
    except Exception as exc:
        logger.warning("Pool session prime failed on %s: %s", worker, exc, exc_info=True)
        return {"worker": worker, "ok": False, "error": str(exc)}


def prime_linkedin_session_on_pool(state_path: Path | str) -> dict[str, Any]:
    """Nạp session vào **từng** browser trong pool — gọi sau POST /login hoặc /verify thành công."""

    path = Path(state_path).resolve()
    validate_storage_state_file(path)
    size = _pool_size()
    ex = _get_executor()
    futures = [ex.submit(_prime_session_on_current_worker, path) for _ in range(size)]
    outcomes: list[dict[str, Any]] = []
    per_worker_timeout_sec = max(60.0, settings.linkedin_session_prime_timeout_ms / 1000.0 + 30.0)
    for future in futures:
        try:
            outcomes.append(future.result(timeout=per_worker_timeout_sec))
        except FuturesTimeoutError:
            outcomes.append(
                {"worker": "unknown", "ok": False, "error": "prime timeout"},
            )
        except Exception as exc:
            outcomes.append({"worker": "unknown", "ok": False, "error": str(exc)})

    primed = sum(1 for item in outcomes if item.get("ok"))
    if primed < size:
        logger.warning(
            "LinkedIn pool prime partial for %s: %s/%s workers OK",
            path.name,
            primed,
            size,
        )
    else:
        logger.info(
            "LinkedIn pool primed on all %s workers for %s",
            size,
            path.name,
        )

    return {
        "total_workers": size,
        "primed_workers": primed,
        "outcomes": outcomes,
    }


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
        validate_storage_state_file(state_path)
        browser = _ensure_browser_on_worker()
        context: BrowserContext = browser.new_context(
            storage_state=str(state_path),
            **linkedin_browser_context_options(),
        )
        page = context.new_page()
        try:
            yield page
        finally:
            if persist_state:
                safe_persist_session_state(context, state_path)
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
