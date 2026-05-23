import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Error as PlaywrightError, Page, async_playwright

from app.modules.zalo.config import settings

# Script injected before every page to hide common automation fingerprints.
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
"""


def _cleanup_profile_lock_files(user_data_dir: str) -> None:
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = os.path.join(user_data_dir, name)
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.warning(f"Removed stale Chromium profile lock file: {path}")
        except Exception as exc:
            logger.warning(f"Could not remove profile lock file {path}: {exc}")


def profile_dir_for_user(user_id: str) -> str:
    safe_user = re.sub(r"[^a-zA-Z0-9._-]+", "_", (user_id or "default")).strip("._")
    if not safe_user:
        safe_user = "default"
    return os.path.join(os.path.abspath(settings.browser_user_data_dir), safe_user)


def clear_user_profile_data(user_id: str) -> bool:
    """Delete persistent browser profile directory for a user."""
    target_dir = profile_dir_for_user(user_id)
    if not os.path.exists(target_dir):
        return False
    shutil.rmtree(target_dir, ignore_errors=False)
    logger.info(f"Cleared browser profile for user={user_id}: {target_dir}")
    return True


def _kill_stale_chromium_processes() -> None:
    try:
        # In Docker, stale chrome processes may hold persistent profile locks across retries.
        subprocess.run(["pkill", "-f", "chrome-linux/chrome"], check=False)
    except Exception as exc:
        logger.warning(f"Could not kill stale chromium processes: {exc}")


def _resolve_browser_executable() -> str | None:
    configured_path = (settings.browser_executable_path or "").strip()
    if configured_path:
        return configured_path

    candidate_paths = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return str(candidate_path)
    return None


def _should_force_headless() -> bool:
    """Force headless mode when the runtime has no GUI display, such as Docker."""

    if os.path.exists("/.dockerenv"):
        return True
    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if os.name != "nt":
        return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return False


async def create_browser(user_id: str = "default") -> tuple[Optional[Browser], BrowserContext, Page]:
    playwright = await async_playwright().start()
    launch_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        "--lang=vi-VN",
    ]

    headless = settings.browser_headless
    if not headless and _should_force_headless():
        logger.warning(
            "Running headed browser in a headless runtime. "
            "Ensure Xvfb/noVNC (or equivalent display server) is available."
        )
    launch_kwargs: dict = {
        "headless": headless,
        "args": launch_args,
    }
    executable_path = _resolve_browser_executable()
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
        logger.info(f"Using browser executable: {executable_path}")
    if settings.browser_stealth:
        # Remove Playwright automation flag to reduce bot detection signals.
        launch_kwargs["ignore_default_args"] = ["--enable-automation"]

    context_kwargs = {
        "viewport": {"width": 1280, "height": 900},
        "device_scale_factor": 1,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "locale": "vi-VN",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "extra_http_headers": {"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"},
    }

    if settings.browser_persistent_profile:
        user_data_dir = profile_dir_for_user(user_id)
        os.makedirs(user_data_dir, exist_ok=True)
        if settings.browser_kill_stale_processes:
            _kill_stale_chromium_processes()
        _cleanup_profile_lock_files(user_data_dir)
        try:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                **launch_kwargs,
                **context_kwargs,
            )
        except PlaywrightError as exc:
            text = str(exc).lower()
            if "profile appears to be in use" in text or "process_singleton" in text:
                logger.warning("Chromium profile lock detected, cleaning stale lock files and retrying")
                _cleanup_profile_lock_files(user_data_dir)
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    **launch_kwargs,
                    **context_kwargs,
                )
            else:
                raise
        browser = context.browser
    else:
        browser = await playwright.chromium.launch(**launch_kwargs)
        context = await browser.new_context(**context_kwargs)

    if settings.browser_stealth:
        await context.add_init_script(_STEALTH_SCRIPT)

    page = context.pages[0] if context.pages else await context.new_page()
    profile_mode = "persistent" if settings.browser_persistent_profile else "ephemeral"
    logger.info(
        "Browser created "
        f"(mode={profile_mode}, headless={headless}, "
        f"stealth={settings.browser_stealth}, profile={settings.browser_user_data_dir}, user={user_id})"
    )
    return browser, context, page
