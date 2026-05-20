import json
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional
from playwright_stealth import Stealth
import pyotp
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser, TimeoutError as PlaywrightTimeoutError
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_account import GoogleSheetAccountService
from .human_behavior import HumanBehavior
from app.modules.facebook.src.core.config.env import Config
from app.modules.facebook.src.core.utils.logger import setup_logger

logger = setup_logger(__name__)


class FacebookAuthError(Exception):
    """Custom exception cho các lỗi xác thực Facebook."""
    pass


class FacebookAuth:
    # --- CONSTANTS ---
    DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    TIMEOUT_SHORT = 5_000
    TIMEOUT_MEDIUM = 15_000
    MAX_CHECKPOINT_RETRIES = 60  # Tăng lên để đủ thời gian cover 60s chờ điện thoại + xử lý OTP

    def __init__(self, config: Config, human: Optional[HumanBehavior] = None):
        self.config = config
        self.human = human or HumanBehavior()
        self.google_sheet_account = GoogleSheetAccountService()
        # Setup directories
        self.sessions_dir = Path(config.COOKIE_DIR or "sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.default_state_path = self.sessions_dir / "default_account_cookie.json"
        
        self.otp_dir = Path("temp_otp")
        self.otp_dir.mkdir(parents=True, exist_ok=True)

    def get_cookie_path(self, email: Optional[str]) -> Path:
        if not email or email == getattr(self.config, 'DEFAULT_FB_EMAIL', ''):
            return self.default_state_path
        return self.sessions_dir / f"{self._safe_email(email)}_cookie.json"

    def login(
        self, 
        page: Page, 
        context: BrowserContext, 
        custom_email: str, 
        custom_pass: str, 
        custom_2fa: Optional[str] = None
    ) -> bool:
        """Hàm login dùng cho luồng scraper trực tiếp (Giữ nguyên)."""
        safe_email = self._safe_email(custom_email)
        otp_cache_file = self.otp_dir / f"temp_otp_{safe_email}.json"
        self._reset_otp_cache(otp_cache_file)
        #logger.info(f"🚀 [Scraper Auth Direct] Bắt đầu đăng nhập cho: {custom_email}")

        try:
            self._login_with_credentials(page, custom_email, custom_pass)
            is_success = self._handle_checkpoint_loop(page, custom_2fa, otp_cache_file)

            if is_success:
                cookie_file = self.get_cookie_path(custom_email) if custom_email != self.config.DEFAULT_FB_EMAIL else self.default_state_path
                self._save_session(context, page, cookie_file)
                #logger.info("✅ Đăng nhập trực tiếp thành công.")
                return True
            else:
                #logger.error("❌ Đăng nhập trực tiếp thất bại do kẹt Checkpoint/OTP.")
                return False
        except Exception as e:
            #logger.error(f"❌ Lỗi khi login trực tiếp: {str(e)}", exc_info=True)
            return False
        finally:
            otp_cache_file.unlink(missing_ok=True)

    def default_login(self, page: Page, context: BrowserContext) -> bool:
        """
        Hàm login dành RIÊNG cho tài khoản mặc định cấu hình trong hệ thống (.env).
        Tự động bóc tách email, password và 2FA mặc định cực kỳ an toàn.
        """
        default_email =  getattr(self.config, 'DEFAULT_FB_EMAIL', '')
        default_pass =  getattr(self.config, 'DEFAULT_FB_PASSWORD', '')
        default_2fa = getattr(self.config, 'DEFAULT_FB_2FA', None)
        if not default_email or not default_pass:
            #logger.error("❌ Hệ thống chưa cấu hình DEFAULT_FB_EMAIL hoặc DEFAULT_FB_PASSWORD!")
            return False
        
        safe_email = self._safe_email(default_email)
        otp_cache_file = self.otp_dir / f"temp_otp_default_{safe_email}.json"
        self._reset_otp_cache(otp_cache_file)
        
        #logger.info(f"🚀 [Default Auth] Bắt đầu đăng nhập tự động cho tài khoản hệ thống: {default_email}")

        try:
            self._login_with_credentials(page, default_email, default_pass)
            is_success = self._handle_checkpoint_loop(page, default_2fa, otp_cache_file)

            if is_success:
                self._save_session(context, page, self.default_state_path)
                #logger.info("✅ Đăng nhập tài khoản mặc định thành công!")
                return True
            else:
                #logger.error("❌ Đăng nhập tài khoản mặc định thất bại do kẹt Checkpoint/OTP.")
                return False
        except Exception as e:
            #logger.error(f"❌ Lỗi khi login tài khoản mặc định: {str(e)}", exc_info=True)
            return False
        finally:
            otp_cache_file.unlink(missing_ok=True)

    def standalone_login(self, custom_email: str, custom_pass: str, session_id: str, custom_2fa: Optional[str] = None) -> Dict[str, str]:
        """
        Main entry point cho quá trình đăng nhập ngầm từ FE.
        Sử dụng session_id để định danh chính xác phiên làm việc.
        """
        cookie_file = self.get_cookie_path(custom_email)
        # Sử dụng session_id làm tên file giao tiếp trạng thái
        otp_cache_file = self.otp_dir / f"session_{session_id}.json"
        
        self._reset_otp_cache(otp_cache_file)
        #logger.info(f"🚀 [Standalone Auth] Bắt đầu đăng nhập: {custom_email} | Session: {session_id}")

        with sync_playwright() as p:
            browser = None
            try:
                browser, context, page = self._init_browser(p)

                # 1. Thử đăng nhập bằng Cookie
                if self._try_login_with_cookie(context, page, cookie_file):
                    self._update_cache_status(otp_cache_file, "SUCCESS", "Đăng nhập sẵn qua cookie.")
                    return {"status": "success", "message": "Đăng nhập sẵn qua cookie."}

                # 2. Đăng nhập bằng Credentials
                self._login_with_credentials(page, custom_email, custom_pass)

                # 3. Xử lý Checkpoint / 2FA / Phone Approval
                is_success = self._handle_checkpoint_loop(page, custom_2fa, otp_cache_file)

                if is_success:
                    self._save_session(context, page, cookie_file)
                    self._update_cache_status(otp_cache_file, "SUCCESS", "Đăng nhập thành công.")
                    return {"status": "success", "message": "Đăng nhập thành công."}
                else:
                    # Nếu thất bại mà chưa có status lỗi cụ thể, gán lỗi chung
                    status_data = json.loads(otp_cache_file.read_text(encoding="utf-8"))
                    if status_data.get("status") not in ["ERROR_WRONG_PASS", "ERROR_BOT_BLOCKED"]:
                        self._update_cache_status(otp_cache_file, "ERROR", "Kẹt Checkpoint quá thời gian.")
                    return {"status": "error", "message": "Kẹt Checkpoint quá thời gian."}

            except FacebookAuthError as fe:
                #logger.warning(f"⚠️ Dừng đăng nhập: {str(fe)}")
                return {"status": "error", "message": str(fe)}
            except Exception as e:
                #logger.error(f"❌ Lỗi hệ thống đăng nhập: {str(e)}", exc_info=True)
                self._update_cache_status(otp_cache_file, "ERROR", f"Lỗi hệ thống: {str(e)}")
                return {"status": "error", "message": str(e)}
            finally:
                # Treo giữ file cache thêm 10s để BE HTTP kịp đọc trạng thái cuối trước khi dọn dẹp
                time.sleep(10)
                if browser:
                    browser.close()
                otp_cache_file.unlink(missing_ok=True)

    # ─────────────────────────────────────────────────────────────────────────────
    # PRIVATE METHODS - CORE LOGIC
    # ─────────────────────────────────────────────────────────────────────────────

    def _init_browser(self, p: Any) -> tuple[Browser, BrowserContext, Page]:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome", 
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--window-size=1920,1080',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-features=IsolateOrigins,site-per-process',
                '--lang=vi-VN',
                '--disable-web-security',
                '--disable-xss-auditor',
            ]
        )
        context = browser.new_context(
            viewport=self.DEFAULT_VIEWPORT,
            user_agent=self.USER_AGENT,
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
            window.chrome = { runtime: { onConnect: null, onMessage: null } };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
            window.PublicKeyCredential = undefined;
            if (navigator.credentials) {
                navigator.credentials.get = () => Promise.reject(new Error("NotSupportedError"));
                navigator.credentials.create = () => Promise.reject(new Error("NotSupportedError"));
            }
        """)
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        return browser, context, page

    def _try_login_with_cookie(self, context: BrowserContext, page: Page, cookie_file: Path) -> bool:
        if not cookie_file.exists():
            return False
        try:
            state = json.loads(cookie_file.read_text(encoding="utf-8"))
            if "cookies" in state:
                context.add_cookies(state["cookies"])
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            try:
                page.wait_for_selector('div[role="navigation"]', timeout=self.TIMEOUT_SHORT)
                #logger.info("✅ Cookie cũ hợp lệ, đã vào feed!")
                return True
            except PlaywrightTimeoutError:
                #logger.warning("⚠️ Cookie hết hạn, tiến hành đăng nhập lại...")
                cookie_file.unlink(missing_ok=True)
                return False
        except Exception as e:
            #logger.warning(f"⚠️ Lỗi đọc cookie: {e}")
            cookie_file.unlink(missing_ok=True)
            return False

    def _login_with_credentials(self, page: Page, email: str, password: str):
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        try:
            another_acc_btn = page.locator("text=/Dùng trang cá nhân khác|Log Into Another Account|Log in to another account/i").first
            if another_acc_btn.count() > 0 and another_acc_btn.is_visible(timeout=3000):
                # logger.info("Phát hiện màn hình chọn tài khoản, đang click để hiện form...")
                another_acc_btn.click()
                page.wait_for_timeout(2000) # Chờ form Email/Pass trượt ra
        except Exception:
            pass
        email_input = page.locator(self.config.AUTH_SELECTORS["email"])
        email_input.wait_for(state="visible")
        self._type_like_human(email_input, email)

        pass_input = page.locator(self.config.AUTH_SELECTORS["password"])
        self._type_like_human(pass_input, password)
        page.keyboard.press("Enter")
        
        try:
            page.wait_for_url(re.compile(r"^(?!.*\/login).*$"), timeout=self.TIMEOUT_MEDIUM)
            page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_MEDIUM)
        except PlaywrightTimeoutError:
            pass 

    def _handle_checkpoint_loop(self, page: Page, custom_2fa: Optional[str], otp_cache_file: Path) -> bool:
        #logger.info("⏳ Bắt đầu xử lý Checkpoint/State Machine...")
        otp_filled = False
        phone_approval_waited = False  
        bot_check_notified = False
        # page.wait_for_timeout(30000) 
        for step in range(self.MAX_CHECKPOINT_RETRIES):
            page.wait_for_timeout(3000) 
            current_url = page.url

            # Trạng thái 1: Thành công vào Feed
            if self._is_feed_loaded(page, current_url):
                return True

            # Trạng thái 2: Sai mật khẩu / Email
            if page.locator("text=/Mật khẩu bạn đã nhập không chính xác|The password you’ve entered is incorrect|Invalid username/i").count() > 0:
                self._update_cache_status(otp_cache_file, "ERROR_WRONG_PASS", "Sai email hoặc mật khẩu đăng nhập.")
                raise FacebookAuthError("Sai email hoặc mật khẩu đăng nhập.")

            # Trạng thái 3: Bị chặn Bot / CAPTCHA
            if self._is_bot_check_screen(page):
                if not bot_check_notified:
                    #logger.warning(f"[Step {step}] 🤖 Phát hiện Bot/CAPTCHA.")
                    self._update_cache_status(otp_cache_file, "ERROR_BOT_BLOCKED", "Bị chặn bởi Bot/CAPTCHA. Vui lòng giải quyết trên trình duyệt.")
                    bot_check_notified = True
                # Bắn lỗi out ngay cho FE theo đúng yêu cầu
                raise FacebookAuthError("Bị Facebook chặn bởi xác minh Bot/CAPTCHA.")

            # Trạng thái 4: Phê duyệt qua điện thoại / Passkey
            if self._is_passkey_screen(page):
                is_phone_screen = page.locator("text=/Kiểm tra thông báo trên thiết bị khác|Check notifications on another device/i").count() > 0
                
                # KỊCH BẢN: Treo ngầm chờ điện thoại tối đa 60 giây
                if is_phone_screen and not phone_approval_waited:
                    logger.info(f"[Step {step}] 📱 Yêu cầu Phê duyệt thiết bị. Bắt đầu treo ngầm 60 giây...")
                    self._update_cache_status(otp_cache_file, "WAITING_FOR_PHONE_APPROVAL", "Vui lòng xác nhận trên điện thoại.")

                    approval_success = False
                    # Lặp 20 chu kỳ * 3s = 60 giây chờ đợi
                    for wait_sec in range(20):
                        page.wait_for_timeout(3000)
                        if self._is_feed_loaded(page, page.url):
                            approval_success = True
                            break
                        if not self._is_passkey_screen(page):
                            # Đã thoát khỏi màn hình phone approval (có thể nhảy sang form khác)
                            break
                    
                    if approval_success:
                        continue 
                    else:
                        #logger.warning("⚠️ Quá 1 phút không phê duyệt điện thoại! Tự động chuyển sang hỏi mã OTP 60s...")
                        phone_approval_waited = True  # Đánh dấu đã hết cơ hội chờ điện thoại
                        self._bypass_passkey(page, step)  # Bấm "Thử cách khác"
                        # Cập nhật trạng thái ngay để FE hiển thị form OTP
                        self._update_cache_status(otp_cache_file, "WAITING_FOR_OTP", "Chuyển sang xác thực OTP.")
                        continue

                # Nếu là Passkey thường HOẶC đã quá 1 phút chờ điện thoại
                else:
                    self._bypass_passkey(page, step)
                    otp_filled = False
                    continue

            # Trạng thái 5: Chọn phương thức xác thực (nếu bị hỏi)
            if self._handle_auth_method_selection(page, step, bool(custom_2fa)):
                continue

            # Trạng thái 6: Điền OTP (Khi giao diện đã ở form nhập mã 6 số)
            if not otp_filled and self._handle_otp_input(page, step, custom_2fa, otp_cache_file):
                otp_filled = True
                continue

            # Trạng thái 7: Bypass các bước lưu trình duyệt an toàn
            self._handle_save_browser_prompts(page)

        return False

    # ─────────────────────────────────────────────────────────────────────────────
    # PRIVATE METHODS - DOM INTERACTION HELPERS
    # ─────────────────────────────────────────────────────────────────────────────

    def _update_cache_status(self, file_path: Path, status: str, message: str = "", otp_code: Any = None):
        """Hàm ghi trạng thái chuẩn hóa ra file giao tiếp."""
        if file_path.parent.exists():
            try:
                data = {"status": status, "message": message, "otp_code": otp_code}
                file_path.write_text(json.dumps(data), encoding="utf-8")
            except Exception as e:
                #logger.error(f"Lỗi ghi file trạng thái {status}: {e}")
                pass

    def _is_feed_loaded(self, page: Page, url: str) -> bool:
        return (
            page.locator('div[role="navigation"]').count() > 0 or
            page.locator('svg[aria-label="Facebook"]').count() > 0 or
            ("checkpoint" not in url and ("facebook.com/?sk=h_chr" in url or url == "https://www.facebook.com/"))
        )

    def _is_passkey_screen(self, page: Page) -> bool:
        if (
            page.locator("text=/mở khóa thiết bị/i").count() > 0 or
            page.locator("text=/Passkey/i").count() > 0 or
            page.locator("text=/Xác nhận đó là bạn theo cách/i").count() > 0 or
            page.locator("text=/Kiểm tra thông báo trên thiết bị khác/i").count() > 0 or
            page.locator("text=/Check notifications on another device/i").count() > 0
        ):
            return True

        btn_try_other = page.locator('text=/Thử cách khác|Try another way/i')
        if btn_try_other.count() > 0 and btn_try_other.first.is_visible():
            return True
        return False

    def _bypass_passkey(self, page: Page, step: int):
        #logger.info(f"[Step {step}] 🔒 Bấm Thử cách khác / Bỏ qua Passkey...")
        btn_try_other = page.locator('text=/Thử cách khác|Try another way/i')
        clicked = False
        try:
            btn_try_other.first.wait_for(state="attached", timeout=self.TIMEOUT_SHORT)
            for i in range(btn_try_other.count()):
                element = btn_try_other.nth(i)
                if element.is_visible():
                    element.click(force=True)
                    clicked = True
                    break
            if not clicked:
                raise Exception("Nút bị ẩn.")
        except Exception:
            page.evaluate("""
                () => {
                    const xpath = "//*[contains(text(), 'Thử cách khác')] | //*[contains(text(), 'Try another way')]";
                    const iter = document.evaluate(xpath, document, null, XPathResult.UNORDERED_NODE_ITERATOR_TYPE, null);
                    let node = iter.iterateNext();
                    while (node) {
                        const style = window.getComputedStyle(node);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                            node.click();
                            break;
                        }
                        node = iter.iterateNext();
                    }
                }
            """)
        page.wait_for_timeout(3000)

    def _handle_auth_method_selection(self, page: Page, step: int, has_2fa: bool) -> bool:
        btn_more = page.locator('text=/Xem thêm lựa chọn|See more options/i')
        if btn_more.count() > 0 and btn_more.first.is_visible():
            btn_more.first.click(force=True)
            page.wait_for_timeout(1500) 

        if has_2fa:
            selectors = ['text=/Ứng dụng xác thực/i', 'text=/Authentication app/i', 'text=/Dùng ứng dụng xác thực/i']
        else:
            selectors = ['text=/WhatsApp/i', 'text=/Tin nhắn SMS/i', 'text=/SMS/i', 'text=/Email/i', 'text=/Gửi email/i']

        for selector in selectors:
            loc = page.locator(selector)
            if loc.count() > 0:
                for i in range(loc.count()):
                    element = loc.nth(i)
                    if element.is_visible():
                        element.click(force=True)
                        page.wait_for_timeout(1000)
                        self._click_continue_btn(page)
                        return True
        return False

    def _handle_otp_input(self, page: Page, step: int, custom_2fa: Optional[str], otp_cache_file: Path) -> bool:
        otp_input = page.locator('input[id*="approvals_code"], input[type="text"][placeholder*="mã"], input[autocomplete="one-time-code"]')
        
        if otp_input.count() > 0 and otp_input.first.is_visible():
            code = self._get_otp_code(custom_2fa, otp_cache_file)
            if code:
                #logger.info(f"[Step {step}] 🔑 Phát hiện mã OTP mới: {code}. Tiến hành điền...")
                otp_input.first.triple_click()
                self._type_like_human(otp_input.first, code)
                page.wait_for_timeout(1000)
                
                if self._click_continue_btn(page, submit_texts=["Gửi", "Tiếp tục", "Submit", "Continue"]):
                    logger.info("✅ Đã submit OTP, chờ xác nhận...")
                    page.wait_for_timeout(4000)
                return True
            else:
                # Đang ở form OTP nhưng chưa có mã -> Ghi trạng thái báo FE
                self._update_cache_status(otp_cache_file, "WAITING_FOR_OTP", "Vui lòng nhập mã OTP 6 số.")
        return False

    def _handle_save_browser_prompts(self, page: Page):
        save_radio = page.locator('input[type="radio"][value="save_device"]')
        if save_radio.count() > 0 and save_radio.first.is_visible():
            save_radio.first.click(force=True)
            page.wait_for_timeout(1000)

        for btn_text in ["Lưu trình duyệt", "Save Browser", "Đây là tôi", "Tiếp tục", "Continue"]:
            btn = page.locator(f'button:has-text("{btn_text}"), div[role="button"]:has-text("{btn_text}")')
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(force=True)
                page.wait_for_timeout(2000)
                break

    def _click_continue_btn(self, page: Page, submit_texts: list = ["Tiếp tục", "Continue"]) -> bool:
        for text in submit_texts:
            btn = page.locator(f'button:has-text("{text}"), div[role="button"]:has-text("{text}")')
            if btn.count() > 0:
                for i in range(btn.count()):
                    element = btn.nth(i)
                    if element.is_visible():
                        element.click(force=True)
                        return True
        return False

    # ─────────────────────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────────────────────

    def _get_otp_code(self, custom_2fa: Optional[str], otp_cache_file: Path) -> Optional[str]:
        if custom_2fa:
            totp = pyotp.TOTP(custom_2fa.replace(" ", "").upper())
            return totp.now()

        if otp_cache_file.exists():
            try:
                data = json.loads(otp_cache_file.read_text(encoding="utf-8"))
                code = data.get("otp_code")
                # Nếu đã nhận được mã OTP từ FE truyền lên
                if code and data.get("status") == "RECEIVED_OTP":
                    # Đọc xong thì đổi trạng thái sang PROCESSING để tránh điền lặp lại
                    self._update_cache_status(otp_cache_file, "PROCESSING", "Đang xử lý mã OTP...")
                    return str(code).strip()
            except Exception as e:
                #logger.error(f"Lỗi đọc file OTP: {e}")
                pass
        return None

    def _reset_otp_cache(self, otp_cache_file: Path):
        otp_cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._update_cache_status(otp_cache_file, "INIT", "Khởi tạo trình duyệt...")

    def _save_session(self, context: BrowserContext, page: Page, cookie_file: Path):
        try:
            page.wait_for_load_state("networkidle", timeout=self.TIMEOUT_SHORT)
        except PlaywrightTimeoutError:
            pass
        context.storage_state(path=str(cookie_file))
        #logger.info("✅ Đã lưu phiên đăng nhập (Storage State) thành công!")

    def _is_bot_check_screen(self, page: Page) -> bool:
        try:
            bot_texts = [
                "text=/Xác nhận bạn không phải là robot/i",
                "text=/Confirm you are not a robot/i",
                "text=/Vui lòng hoàn thành kiểm tra bảo mật/i",
                "text=/Security Check/i",
                "text=/Kiểm tra bảo mật/i"
            ]
            for selector in bot_texts:
                if page.locator(selector).count() > 0 and page.locator(selector).first.is_visible():
                    return True

            for frame in page.frames:
                src = frame.url.lower()
                if any(domain in src for domain in ["recaptcha", "arkoselabs", "hcaptcha"]):
                    return True
            return False
        except Exception:
            return False

    def _type_like_human(self, element, text: str):
        element.click()
        element.clear()
        element.page.wait_for_timeout(200)
        element.press_sequentially(text, delay=150)

    @staticmethod
    def _safe_email(email: str) -> str:
        return email.replace("@", "_at_").replace(".", "_dot_")