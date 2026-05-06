"""Authentication service for LinkedIn session management."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from playwright.sync_api import BrowserContext, Error, Locator, Page, TimeoutError, sync_playwright

from app.config import settings
from app.utils.file_utils import ensure_directory, save_json_file_overwrite
from app.utils.logger import get_logger


logger = get_logger(__name__)

EMAIL_SELECTORS = [
    'input[name="session_key"]',
    'input#username',
    'input[name="username"]',
    'input[autocomplete="username"]',
    'input[type="email"]',
    'input[aria-describedby*="info"][type="text"]',
]
PASSWORD_SELECTORS = [
    'input[name="session_password"]',
    'input#password',
    'input[name="password"]',
    'input[autocomplete="current-password"]',
    'input[type="password"]',
]
SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'button[data-litms-control-urn="login-submit"]',
    'button._0290c384:has-text("Sign in")',
    'button:has-text("Sign in")',
    'button:has-text("Log in")',
]


def normalize_session_id(session_id: str | None) -> str:
    """Normalize a user-supplied session ID into a filesystem-safe value."""

    raw_value = (session_id or "").strip().lower()
    if not raw_value:
        raw_value = uuid4().hex

    normalized = re.sub(r"[^a-z0-9_-]+", "-", raw_value).strip("-_")
    if not normalized:
        normalized = uuid4().hex
    return normalized


def email_to_session_basename(email: str) -> str:
    """Chuyển email thành tên file an toàn (stem .json) — mỗi user một file session riêng.

    Ví dụ: ``user.name@gmail.com`` → ``user_name_gmail_com`` → file ``user_name_gmail_com.json``.
    """

    normalized = (email or "").strip().lower()
    if not normalized:
        return f"session_{uuid4().hex[:12]}"

    try:
        ascii_like = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    except Exception:
        ascii_like = normalized

    slug = re.sub(r"[^a-z0-9]+", "_", ascii_like).strip("_")
    if not slug:
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
        return f"user_{digest}"

    if len(slug) > 200:
        slug = slug[:200].rstrip("_")

    return slug


def default_session_id_for_email(email: str) -> str:
    """Tên session (stem file) ổn định theo email — khớp với file ``{stem}.json`` sau khi login."""

    return email_to_session_basename(email)


def resolve_session_id(session_id: str | None, email: str | None = None) -> str:
    """Resolve a stable session ID from explicit input or email fallback."""

    if session_id and session_id.strip():
        return normalize_session_id(session_id)
    if email and email.strip():
        return default_session_id_for_email(email)
    return normalize_session_id(None)


def build_session_state_path(session_id: str | None, email: str | None = None) -> tuple[str, Path]:
    """Build a resolved session ID and the matching storage-state path."""

    normalized_session_id = resolve_session_id(session_id=session_id, email=email)
    ensure_directory(settings.session_storage_dir)
    return normalized_session_id, settings.session_storage_dir / f"{normalized_session_id}.json"


def _is_authwall_url(current_url: str) -> bool:
    """Return True when URL points to a LinkedIn auth gate."""

    parsed = urlparse((current_url or "").strip())
    path = (parsed.path or "").lower()
    return any(path.startswith(prefix) for prefix in ["/login", "/checkpoint", "/authwall"])


def _has_li_at_cookie(storage_state: dict) -> bool:
    """Check whether storage state contains LinkedIn auth cookie li_at."""

    cookies = storage_state.get("cookies") if isinstance(storage_state, dict) else None
    if not isinstance(cookies, list):
        return False

    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        if str(cookie.get("name", "")).strip() == "li_at" and str(cookie.get("value", "")).strip():
            return True
    return False


def _capture_login_artifacts(page: Page, filename_prefix: str) -> None:
    """Save screenshot and HTML to help debug login failures."""

    ensure_directory(settings.raw_data_dir)
    screenshot_path = settings.raw_data_dir / f"{filename_prefix}.png"
    html_path = settings.raw_data_dir / f"{filename_prefix}.html"

    try:
        if page.is_closed():
            html_path.write_text(
                "<html><body><p>Playwright page was already closed before debug artifacts could be captured.</p></body></html>",
                encoding="utf-8",
            )
            logger.warning("Skipped login screenshot because the page was already closed")
            return
    except Error:
        logger.debug("Could not determine whether login page is closed", exc_info=True)

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Error:
        logger.warning("Could not capture login screenshot because page/context/browser was already closed")

    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Error:
        html_path.write_text(
            "<html><body><p>Could not capture page HTML because page/context/browser was already closed.</p></body></html>",
            encoding="utf-8",
        )
        logger.warning("Could not capture login HTML because page/context/browser was already closed")


def _first_visible_locator(page: Page, selectors: list[str], timeout_ms: int = 4000) -> Locator | None:
    """Return the first selector whose element becomes visible."""

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except TimeoutError:
            continue
        except Error:
            logger.debug("Selector lookup failed for %s", selector, exc_info=True)
    return None


def _first_visible_descendant(container: Locator | Page, selectors: list[str], timeout_ms: int = 3000) -> Locator | None:
    """Return the first visible matching descendant across all selector candidates."""

    for selector in selectors:
        try:
            locator = container.locator(selector)
            count = locator.count()
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    candidate.wait_for(state="visible", timeout=timeout_ms)
                    if candidate.is_visible():
                        return candidate
                except (TimeoutError, Error):
                    continue
        except Error:
            logger.debug("Descendant selector lookup failed for %s", selector, exc_info=True)
    return None


def _find_email_input(page: Page) -> Locator | None:
    """Find the email field using selectors and accessible labels."""

    login_root = page.locator('[data-sdui-screen="com.linkedin.sdui.flagshipnav.login.Login"]')

    candidate = _first_visible_descendant(
        login_root,
        ['input[id^=":r"][type="text"]', 'input[aria-describedby*="info"][type="text"]', 'input[type="text"]'],
    )
    if candidate is not None:
        return candidate

    locator = _first_visible_locator(page, EMAIL_SELECTORS, timeout_ms=5000)
    if locator is not None:
        return locator

    for label_text in ["Email or phone", "Email", "Phone"]:
        try:
            label_locator = page.get_by_label(label_text, exact=False)
            for index in range(label_locator.count()):
                candidate = label_locator.nth(index)
                try:
                    candidate.wait_for(state="visible", timeout=3000)
                    if candidate.is_visible():
                        return candidate
                except (TimeoutError, Error):
                    continue
        except (TimeoutError, Error):
            logger.debug("Could not find email field by label %s", label_text, exc_info=True)
    return None


def _find_password_input(page: Page) -> Locator | None:
    """Find the password field using selectors and accessible labels."""

    login_root = page.locator('[data-sdui-screen="com.linkedin.sdui.flagshipnav.login.Login"]')

    candidate = _first_visible_descendant(
        login_root,
        ['input[id^=":r"][type="password"]', 'input[autocomplete="current-password"]', 'input[type="password"]'],
    )
    if candidate is not None:
        return candidate

    locator = _first_visible_locator(page, PASSWORD_SELECTORS, timeout_ms=5000)
    if locator is not None:
        return locator

    try:
        label_locator = page.get_by_label("Password", exact=False)
        for index in range(label_locator.count()):
            candidate = label_locator.nth(index)
            try:
                candidate.wait_for(state="visible", timeout=3000)
                if candidate.is_visible():
                    return candidate
            except (TimeoutError, Error):
                continue
    except (TimeoutError, Error):
        logger.debug("Could not find password field by label", exc_info=True)
        return None
    return None


def _find_submit_button(page: Page) -> Locator | None:
    """Find the sign-in button using selectors and accessible names."""

    login_root = page.locator('[data-sdui-screen="com.linkedin.sdui.flagshipnav.login.Login"]')

    for selector in SUBMIT_SELECTORS:
        try:
            buttons = login_root.locator(selector)
            for index in range(buttons.count()):
                candidate = buttons.nth(index)
                try:
                    candidate.wait_for(state="visible", timeout=3000)
                    text = candidate.inner_text(timeout=1000).strip().lower()
                    if text in {"sign in", "log in"}:
                        return candidate
                except (TimeoutError, Error):
                    continue
        except Error:
            logger.debug("Could not find submit button in login root via %s", selector, exc_info=True)

    locator = _first_visible_locator(page, SUBMIT_SELECTORS, timeout_ms=3000)
    if locator is not None:
        try:
            text = locator.inner_text(timeout=1000).strip().lower()
            if text == "sign in" or text == "log in":
                return locator
        except Error:
            logger.debug("Could not read candidate submit button text", exc_info=True)

    for button_text in ["Sign in", "Log in"]:
        try:
            buttons = page.get_by_role("button", name=button_text, exact=True)
            for index in range(buttons.count()):
                candidate = buttons.nth(index)
                try:
                    candidate.wait_for(state="visible", timeout=3000)
                    if candidate.is_visible():
                        return candidate
                except (TimeoutError, Error):
                    continue
        except Error:
            logger.debug("Could not find submit button by role %s", button_text, exc_info=True)
    return None


def _set_input_value(locator: Locator, value: str) -> None:
    """Set input value and dispatch events so LinkedIn's React form picks it up."""

    locator.click(force=True)
    locator.fill("")
    locator.evaluate(
        """(element, nextValue) => {
            element.focus();
            const prototype = Object.getPrototypeOf(element);
            const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value');
            if (descriptor && descriptor.set) {
                descriptor.set.call(element, nextValue);
            } else {
                element.value = nextValue;
            }
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )


def _fill_login_form(page: Page, email: str, password: str) -> None:
    """Find and fill the LinkedIn login form using resilient fallbacks."""

    email_input = _find_email_input(page)
    password_input = _find_password_input(page)

    if email_input is None or password_input is None:
        _capture_login_artifacts(page, "login_form_not_found")
        raise RuntimeError(
            "Could not find LinkedIn login form fields. Check data/raw/login_form_not_found.html and .png."
        )

    _set_input_value(email_input, email)
    _set_input_value(password_input, password)

    submit_button = _find_submit_button(page)
    if submit_button is not None:
        submit_button.click(force=True)
        return

    password_input.press("Enter")


def _verify_state_file_contains_auth_cookie(state_path: Path) -> None:
    """Validate saved storage state contains the main LinkedIn auth cookie."""

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not _has_li_at_cookie(payload):
        raise RuntimeError(
            "Saved session is missing LinkedIn auth cookie (li_at). Relogin and complete verification steps."
        )


def _context_has_li_at_cookie(context: BrowserContext) -> bool:
    """Return True if the current browser context has li_at in storage state."""

    try:
        state = context.storage_state()
    except Error:
        logger.debug("Could not inspect context storage state", exc_info=True)
        return False
    return _has_li_at_cookie(state)


def _wait_for_login_session(page: Page, context: BrowserContext, timeout_ms: int = 45000) -> None:
    """Wait until LinkedIn session is established after submitting login form."""

    end_time = time.time() + (timeout_ms / 1000)

    while time.time() < end_time:
        if _context_has_li_at_cookie(context) and not _is_authwall_url(page.url):
            return

        try:
            page.wait_for_timeout(1000)
        except Error:
            logger.debug("Waiting for login session encountered a transient error", exc_info=True)

    _capture_login_artifacts(page, "login_session_not_ready")
    raise RuntimeError(
        "LinkedIn login did not produce a reusable session in time. "
        "Check data/raw/login_session_not_ready.html and .png."
    )


def _existing_state_is_reusable(state_path: Path) -> bool:
    """Return True when existing state file contains a reusable auth cookie."""

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not parse existing state file at %s; forcing relogin", state_path, exc_info=True)
        return False

    if not _has_li_at_cookie(payload):
        logger.warning("Existing state file at %s is missing li_at cookie; forcing relogin", state_path)
        return False

    return True


def login_and_save_session(
    email: str,
    password: str,
    session_id: str | None = None,
    force_relogin: bool = True,
) -> tuple[str, Path]:
    """Login to LinkedIn và lưu storage state vào đúng một file session (theo email / session_id).

    Sau khi đăng nhập trình duyệt thành công, luôn **ghi đè** file tại ``state_path`` — không tạo thêm
    file tên khác. Nếu ``force_relogin=False`` và file cũ còn dùng được thì trả về luôn (không chạy
    login lại, không ghi đè).
    """

    if not email.strip() or not password:
        raise ValueError("email and password are required in the request body")

    normalized_session_id, state_path = build_session_state_path(session_id=session_id, email=email)
    ensure_directory(state_path.parent)

    if state_path.exists() and not force_relogin:
        if _existing_state_is_reusable(state_path):
            logger.info("Reusing existing LinkedIn state file at %s", state_path)
            return normalized_session_id, state_path
        logger.info("Existing LinkedIn state file is invalid; continuing with fresh login")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=settings.headless,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-crash-reporter",
                "--disable-web-resources",
            ],
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            logger.info("Opening LinkedIn login page")
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(3000)
            _fill_login_form(page, email=email, password=password)

            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except TimeoutError:
                logger.warning("Initial page transition after login click timed out; continuing to wait for session")

            try:
                _wait_for_login_session(page, context, timeout_ms=45000)
            except RuntimeError:
                if settings.headless:
                    raise RuntimeError(
                        "LinkedIn requires extra verification before session is ready, possibly app approval / 2-step verification. "
                        "Set HEADLESS=false and call POST /login again."
                    )

                logger.info("Opening Playwright inspector for manual checkpoint/captcha/2FA handling")
                page.pause()
                _wait_for_login_session(page, context, timeout_ms=120000)

            if _is_authwall_url(page.url):
                _capture_login_artifacts(page, "login_blocked")
                raise RuntimeError(
                    "LinkedIn login is still on login/checkpoint/authwall. This can happen during 2-step verification "
                    "or account security checks. Complete verification manually and retry."
                )

            if state_path.exists():
                logger.info("Ghi đè session tại %s (file đã tồn tại)", state_path)
            save_json_file_overwrite(state_path, context.storage_state())
            _verify_state_file_contains_auth_cookie(state_path)
            logger.info("Saved LinkedIn storage state to %s", state_path)
            return normalized_session_id, state_path
        except Error as exc:
            logger.exception("LinkedIn login failed")
            raise RuntimeError(f"LinkedIn login failed: {exc}") from exc
        except Exception:
            logger.exception("LinkedIn login failed")
            raise
        finally:
            context.close()
            browser.close()
