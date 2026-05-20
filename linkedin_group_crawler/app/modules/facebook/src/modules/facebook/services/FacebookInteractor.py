import os
import time
import random
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright, Page

from src.modules.facebook.services.facebook_auth import FacebookAuth
from src.core.utils.logger import setup_logger
from .human_behavior import HumanBehavior

logger = setup_logger(__name__)

# ─── ĐỊNH NGHĨA DỮ LIỆU ĐẦU VÀO VÀ ĐẦU RA ─────────────────────────

@dataclass
class InteractionTarget:
    id: str
    url: str
    reaction_type: str
    comment_content: str

@dataclass
class InteractionResult:
    id: str
    success: bool
    status_code: str
    message: str

class FacebookInteractor:
    def __init__(self, config):
        self.config = config
        self.auth = FacebookAuth(config)
        self.reaction_map = {
            'LIKE': 'Thích', 'LOVE': 'Yêu thích', 'CARE': 'Thương thương',
            'HAHA': 'Haha', 'WOW': 'Wow', 'SAD': 'Buồn', 'ANGRY': 'Phẫn nộ'
        }

    # ==========================================
    # CÁC HÀM GIẢ LẬP HÀNH VI NGƯỜI THẬT
    # ==========================================
    def _human_scroll_and_read(self, page: Page):
        """Giả lập hành vi cuộn lên xuống đọc bài trước khi tương tác"""
        for _ in range(random.randint(1, 3)):
            scroll_amount = random.randint(300, 800)
            direction = random.choice([1, -1]) if _ > 0 else 1
            page.mouse.wheel(0, scroll_amount * direction)
            page.wait_for_timeout(random.randint(1000, 2500))

    def _human_mouse_move_to_element(self, page: Page, locator):
        """Giả lập việc rê chuột từ từ tới mục tiêu thay vì teleport"""
        try:
            box = locator.bounding_box()
            if box:
                # Tính toán tọa độ ngẫu nhiên bên trong nút đó
                target_x = box["x"] + (box["width"] / 2) + random.uniform(-5, 5)
                target_y = box["y"] + (box["height"] / 2) + random.uniform(-2, 2)
                # Di chuyển chuột thành nhiều bước (steps) để tạo đường đi mượt
                page.mouse.move(target_x, target_y, steps=random.randint(10, 25))
                page.wait_for_timeout(random.randint(200, 600))
        except Exception:
            pass # Bỏ qua nếu không lấy được box

    def _human_typing(self, page: Page, text: str):
        """Giả lập việc gõ phím: Gõ từng chữ tốc độ không đều, dừng lại suy nghĩ ở dấu câu"""
        for char in text:
            # Tốc độ gõ 1 phím ngẫu nhiên từ nhanh đến hơi chậm
            page.keyboard.type(char, delay=random.randint(30, 120))
            
            # Nếu gặp khoảng trắng, phẩy, chấm -> Dừng lại "suy nghĩ" 1 chút
            if char in [' ', ',', '.', '?', '!']:
                page.wait_for_timeout(random.randint(100, 400))
            
            # Xác suất 3% người dùng bỗng nhiên khựng lại giữa chừng (vài giây)
            if random.random() < 0.03:
                page.wait_for_timeout(random.randint(500, 1500))
    # ==========================================

    def interact_with_post(
        self, 
        target: InteractionTarget, 
        custom_email: Optional[str] = None, 
        custom_pass: Optional[str] = None,
        custom_2fa: Optional[str] = None
    ) -> InteractionResult:
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox', 
                    '--window-size=1920,1080',
                    '--disable-gpu',
                    '--disable-background-timer-throttling',
                ]
            )
            
            context_args = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "locale": "vi-VN",
                "timezone_id": "Asia/Ho_Chi_Minh",
                # Bật permissions để tự nhiên hơn
                "permissions": ["geolocation"]
            }

            cookie_path = self.auth.get_cookie_path(custom_email) 
            default_cookie_path = self.auth.get_cookie_path(None)
            used_cookie_path = None

            if custom_email and os.path.exists(cookie_path):
                used_cookie_path = cookie_path
                context = browser.new_context(storage_state=used_cookie_path, **context_args)
            elif os.path.exists(default_cookie_path):
                used_cookie_path = default_cookie_path
                context = browser.new_context(storage_state=used_cookie_path, **context_args)
            else:
                context = browser.new_context(**context_args)

            # Xóa dấu vết bot căn bản
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.navigator.chrome = { runtime: {} };
            """)

            page = context.new_page()

            try:
                # ── 1. VÀO TRANG CHỦ & CHECK LOGIN ──────────────────────────────────
                page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30_000)
                
                if self.auth._is_bot_check_screen(page):
                    if used_cookie_path and os.path.exists(used_cookie_path):
                        os.remove(used_cookie_path)
                    browser.close()
                    return InteractionResult(target.id, False, "BOT_DETECTED", "Phát hiện bị chặn Bot/Captcha.")

                # Mô phỏng nán lại trang chủ một chút
                self._human_scroll_and_read(page)

                is_logged_in = False
                try:
                    page.wait_for_selector('div[role="navigation"]', timeout=5000)
                    if page.locator('input[name="email"]').count() == 0:
                        is_logged_in = True
                except:
                    pass

                if not is_logged_in:
                    if custom_email and custom_pass:
                        login_success = self.auth.login(
                            page=page, context=context, 
                            custom_email=custom_email, custom_pass=custom_pass, custom_2fa=custom_2fa
                        )
                    else:
                        login_success = self.auth.default_login(page=page, context=context)
                    
                    if not login_success:
                        browser.close()
                        return InteractionResult(target.id, False, "LOGIN_FAILED", "Đăng nhập thất bại.")
                
                if custom_email:
                    context.storage_state(path=str(cookie_path))

                # ── 2. TRUY CẬP BÀI VIẾT ──────────────────────────────────────────
                page.goto(target.url, wait_until="domcontentloaded", timeout=30_000)
                
                # NGƯỜI THẬT: Cuộn lên xuống đọc bài viết trước khi like/comment
                self._human_scroll_and_read(page)

                if page.locator('text="Nội dung này hiện không hiển thị"').count() > 0 or \
                   page.locator('text="This content isn\'t available right now"').count() > 0:
                    browser.close()
                    return InteractionResult(target.id, False, "POST_NOT_FOUND", "Bài viết đã bị xóa hoặc private.")

                # ── 3. THỰC HIỆN CẢM XÚC (KẾT HỢP GHOST CURSOR + JS) ───────────────
                try:
                    target_reaction = target.reaction_type.upper()
                    if target_reaction in self.reaction_map:
                        reaction_vi = self.reaction_map[target_reaction]
                        
                        like_btn = page.locator('div[role="button"]:has-text("Thích"), div[role="button"]:has-text("Like"), div[aria-label="Thích"][role="button"], div[aria-label="Like"][role="button"]').first
                        if like_btn.count() > 0:
                            like_btn.scroll_into_view_if_needed()
                            page.wait_for_timeout(random.randint(500, 1000))
                            
                            # Rê con trỏ chuột thật tới nút Thích để track lưu vết của Facebook
                            self._human_mouse_move_to_element(page, like_btn)
                            
                            if target_reaction == 'LIKE':
                                page.wait_for_timeout(random.randint(300, 800))
                                like_btn.evaluate("node => node.click()")
                            else:
                                # Kích hoạt JS để mở bảng cảm xúc
                                like_btn.evaluate("node => node.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, cancelable: true}))")
                                like_btn.evaluate("node => node.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, cancelable: true}))")
                                
                                # Chờ người dùng "nhìn" bảng cảm xúc
                                page.wait_for_timeout(random.randint(1200, 2000))
                                
                                specific_reaction = page.locator(f'div[aria-label="{reaction_vi}"][role="button"]').first
                                if specific_reaction.count() > 0:
                                    # Di chuột qua icon cảm xúc trước khi bấm
                                    self._human_mouse_move_to_element(page, specific_reaction)
                                    specific_reaction.evaluate("node => node.click()")
                                else:
                                    like_btn.evaluate("node => node.click()")
                                    
                            # Sau khi bấm xong, người thật thường lia chuột ra chỗ khác
                            page.mouse.move(random.randint(100, 800), random.randint(100, 800), steps=10)
                            page.wait_for_timeout(random.randint(1000, 2000))

                except Exception as e:
                    logger.warning(f"Lỗi khi thả cảm xúc: {e}")

                # ── 4. THỰC HIỆN BÌNH LUẬN GIỐNG NGƯỜI NHẤT ────────────────────────
                try:
                    if target.comment_content:
                        comment_box = page.locator('div[role="textbox"][aria-label*="Viết bình luận"]').first
                        if comment_box.count() == 0:
                            comment_box = page.locator('div[role="textbox"][contenteditable="true"]').first

                        if comment_box.count() > 0:
                            comment_box.scroll_into_view_if_needed()
                            page.wait_for_timeout(random.randint(500, 1500))
                            
                            # Di chuột tới khung comment và click
                            self._human_mouse_move_to_element(page, comment_box)
                            comment_box.click(force=True)
                            
                            # Nghỉ 1 nhịp chuẩn bị gõ phím
                            page.wait_for_timeout(random.randint(800, 1500))
                            
                            # Gọi hàm gõ phím giống người thật
                            self._human_typing(page, target.comment_content)
                            
                            # Chần chừ trước khi ấn Enter (như đang đọc lại cmt)
                            page.wait_for_timeout(random.randint(1000, 3000))
                            page.keyboard.press("Enter")
                            
                            # Đợi bình luận post lên
                            page.wait_for_timeout(random.randint(3000, 5000))
                        else:
                            browser.close()
                            return InteractionResult(target.id, False, "ACTION_FAILED", "Không tìm thấy ô nhập bình luận.")
                except Exception as e:
                    browser.close()
                    return InteractionResult(target.id, False, "ACTION_FAILED", f"Lỗi lúc comment: {str(e)}")

                # ── 5. KẾT THÚC VÀ ĐÓNG TAB NHƯ NGƯỜI THẬT ─────────────────────────
                # Lướt thêm một tý trước khi thoát
                page.mouse.wheel(0, random.randint(300, 600))
                page.wait_for_timeout(random.randint(1500, 3000))
                
                browser.close()
                return InteractionResult(target.id, True, "SUCCESS", "Tương tác thành công.")

            except Exception as e:
                browser.close()
                return InteractionResult(target.id, False, "SYSTEM_ERROR", str(e))