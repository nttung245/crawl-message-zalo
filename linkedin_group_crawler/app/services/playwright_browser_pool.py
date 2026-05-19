"""
Playwright - Luồng đơn, stateless, an toàn nhất.

Nguyên tắc:
- Mỗi hành động (sync, react, comment) = 1 Chromium riêng biệt.
- Đọc cookie từ file JSON (state_path) trước khi mở bài viết.
- Sau khi hoàn thành, ghi cookie mới về file (nếu vẫn còn li_at).
- Đóng browser hoàn toàn sau mỗi hành động — không dùng pool, không thread ngầm.
- Lock theo state_path để tránh 2 tác vụ cùng ghi đè cookie song song.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from playwright.sync_api import BrowserContext, Page, sync_playwright

from app.config import settings
from app.services.auth_service import safe_persist_session_state
from app.services.linkedin_session_nav import (
    ensure_context_loaded_session,
    linkedin_browser_context_options,
    validate_storage_state_file,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ── Chromium flags ────────────────────────────────────────────────────────────
_CHROMIUM_ARGS: tuple[str, ...] = (
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--disable-crash-reporter",
    "--disable-web-resources",
)

# ── Per-file lock (tránh 2 tác vụ cùng ghi đè cookie của 1 tài khoản) ────────
_locks_guard = threading.Lock()
_file_locks: dict[str, threading.Lock] = {}


def _lock_for(state_path: Path) -> threading.Lock:
    key = str(state_path.resolve())
    with _locks_guard:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


# ── Stub cho các hàm pool cũ — không còn làm gì cả ──────────────────────────
def warmup_playwright_pool() -> None:
    logger.info("[playwright] warmup skipped — single-browser stateless mode")


def shutdown_playwright_pool() -> None:
    logger.info("[playwright] shutdown skipped — no persistent browser to stop")


def prime_linkedin_session_on_pool(state_path: Path | str) -> dict[str, Any]:
    """Không dùng pool → trả về kết quả dummy thành công ngay lập tức."""
    logger.info("[playwright] prime skipped (stateless mode) for %s", Path(state_path).name)
    return {"total_workers": 1, "primed_workers": 1, "outcomes": [{"worker": "stateless", "ok": True}]}


# ── Core: chạy action trong 1 browser sạch ───────────────────────────────────
@contextmanager
def _open_browser_with_session(
    state_path: Path,
    *,
    persist_after: bool = True,
) -> Generator[Page, None, None]:
    """
    Context manager: mở browser mới, nạp cookie từ file, yield một Page.
    Khi thoát: lưu cookie lại (nếu persist_after=True và li_at còn hợp lệ), rồi đóng browser.
    """
    validate_storage_state_file(state_path)

    logger.info("[playwright] Khởi động browser cho %s", state_path.name)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=settings.headless,
            args=list(_CHROMIUM_ARGS),
        )
        try:
            context: BrowserContext = browser.new_context(
                storage_state=str(state_path),
                **linkedin_browser_context_options(),
            )
            # Xác minh cookie li_at đã được nạp vào context
            ensure_context_loaded_session(context, state_path)

            page = context.new_page()
            try:
                yield page
            finally:
                if persist_after:
                    # Chỉ ghi cookie về file nếu li_at vẫn còn trong context
                    safe_persist_session_state(context, state_path)
                context.close()
        finally:
            browser.close()
            logger.info("[playwright] Browser đã đóng (%s)", state_path.name)


def run_with_linkedin_session_page(
    *,
    state_path: Path,
    persist_state: bool | None = None,
    action: Callable[[Page], T],
) -> T:
    """
    API chính: chạy `action(page)` trong 1 browser sạch với session từ `state_path`.

    Luồng:
      1. Đọc cookie từ file JSON.
      2. Mở Chromium mới, nạp cookie vào context.
      3. Gọi action(page).
      4. Ghi cookie mới về file (nếu li_at còn hợp lệ).
      5. Đóng browser hoàn toàn.

    Lock theo state_path để tránh 2 request cùng ghi đè cookie của 1 tài khoản.
    """
    path = Path(state_path).resolve()
    should_persist = settings.playwright_persist_session_on_use if persist_state is None else persist_state

    lock = _lock_for(path)
    with lock:
        with _open_browser_with_session(path, persist_after=should_persist) as page:
            return action(page)
