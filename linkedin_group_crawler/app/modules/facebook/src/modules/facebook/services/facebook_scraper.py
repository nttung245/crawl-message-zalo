import os
import time
import random
from dataclasses import dataclass
from typing import List, Optional
import sys

from playwright.sync_api import sync_playwright

from src.modules.crawl_fb.models.post import Post
from src.modules.facebook.services.facebook_auth import FacebookAuth
from src.modules.facebook.services.post_extractor import PostExtractor
from src.core.utils.facebook_parsers import classify_timestamp
from src.core.utils.logger import setup_logger

from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from .human_behavior import HumanBehavior

logger = setup_logger(__name__)

cancel_registry = {}

@dataclass
class GroupTarget:
    """Entity để truyền dữ liệu đầu vào cho các Group cần cào"""
    name: str
    url: str
    Intent:str

class FacebookScraper:
    def __init__(self, config):
        self.config = config
        self.auth = FacebookAuth(config)
       
    def scrape_groups(
        self, 
        groups: List[GroupTarget], 
        custom_email: Optional[str] = None, 
        custom_pass: Optional[str] = None,
        client_id: Optional[str] = None,
        custom_2fa: Optional[str] = None,
    ) -> List[GroupSummary]:
        
        results: List[GroupSummary] = []
        
        with sync_playwright() as p:
            # ── CẤU HÌNH HEADLESS TỐI ƯU CHO VPS PRODUCTION ────────────────────
            # Đổi headless=True tiết kiệm RAM, thêm các cờ chống dội tài nguyên
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox', 
                    '--window-size=1920,1080',
                    '--disable-gpu',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding'
                ]
            )
            
            # ── 1. LOGIC QUẢN LÝ CONTEXT ───────────────────────────────────────
            context_args = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "locale": "vi-VN",
                "timezone_id": "Asia/Ho_Chi_Minh"
            }
            # Lấy đường dẫn file cookie tương ứng (Nếu có custom_email thì lấy file riêng, không thì lấy mặc định)
            cookie_path = self.auth.get_cookie_path(custom_email) 
            if not os.path.exists(cookie_path):
                if custom_email:
                    # [CHẶN CUSTOM ACCOUNT]: Bắn thẳng câu thông báo thân thiện để FE hiển thị toast lỗi
                    #logger.error(f"🛑 Tài khoản custom {custom_email} chưa có Cookie.")
                    browser.close()
                    raise ValueError("Tài khoản chưa đăng nhập hoặc không tìm thấy phiên làm việc. Vui lòng đăng nhập tài khoản này trước!")
                else:
                    # [CHỈ TÀI KHOẢN MẶC ĐỊNH]: Mở context trắng để đi tiếp xuống Bước 2 login tự động
                    #logger.warning("⚠️ Không tìm thấy Cookie mặc định. Mở trình duyệt trắng để Login lại...")
                    context = browser.new_context(**context_args)
            else:
                #logger.info(f"🚀 Mở phiên làm việc từ file Cookie: {cookie_path}")
                context = browser.new_context(storage_state=cookie_path, **context_args)

            
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = context.new_page()
            
            

            # ── 2. KIỂM TRA VÀ ĐĂNG NHẬP ──────────────────────────────────────
            #logger.info("Khởi động trình duyệt và kiểm tra trạng thái đăng nhập...")
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30_000)
            
            if self.auth._is_bot_check_screen(page):
                #logger.error("🛑 Phát hiện bị chặn Bot/Captcha ngay sau khi load Cookie!")
                if os.path.exists(cookie_path):
                    try:
                        os.remove(cookie_path)
                        #logger.warning(f"🗑️ Đã XÓA FILE COOKIE bị đánh dấu lỗi: {cookie_path}")
                    except Exception as file_err:
                        #logger.error(f"⚠️ Lỗi khi xóa file cookie vật lý: {file_err}")
                        pass
                else:
                    #logger.debug("File Cookie không tồn tại để xóa.")
                    pass
                browser.close()
                raise ValueError("LOGIN_FAILED")
            HumanBehavior.act_like_reading(page) 
            # ── [THÊM MỚI] XỬ LÝ MÀN HÌNH CHỌN TÀI KHOẢN (ACCOUNT CHOOSER) ──────
            try:
                # Sử dụng Regex để bắt text tiếng Việt hoặc tiếng Anh
                # Facebook đôi khi dùng thẻ <div> hoặc <a> cho nút này
                another_acc_btn = page.locator("text=/Đăng nhập bằng tài khoản khác|Log Into Another Account|Log in to another account/i").first
                
                if another_acc_btn.count() > 0 and another_acc_btn.is_visible():
                    # logger.info("Phát hiện màn hình One-Tap Login, đang click 'Đăng nhập bằng tài khoản khác'...")
                    another_acc_btn.click(timeout=5000)
                    # Chờ 1 chút để form email/pass truyền thống xuất hiện lại trên DOM
                    page.wait_for_timeout(2000)
            except Exception as e:
                # Nếu không tìm thấy nút này hoặc có lỗi thì cứ bỏ qua và đi tiếp
                # logger.debug(f"Không có màn hình chọn tài khoản: {e}")
                pass
            is_logged_in = False
            try:
                page.wait_for_selector('div[role="navigation"]', timeout=5000)
                if page.locator(self.config.AUTH_SELECTORS["email"]).count() == 0:
                    is_logged_in = True
            except:
                is_logged_in = False

            if not is_logged_in:
                if custom_email:
                    # Nếu có email FE mà cookie hết hạn (không vào được feed) -> Thử login lại bằng thông tin FE gửi
                    #logger.info(f"⚠️ Cookie của {custom_email} hết hạn. Đang thử login lại...")
                    login_success = self.auth.login(
                        page=page, context=context, 
                        custom_email=custom_email, custom_pass=custom_pass, custom_2fa=custom_2fa
                    )
                else:
                    # Nếu không có email FE -> Gọi hàm LOGIN MẶC ĐỊNH
                    #logger.info("⚠️ Chưa đăng nhập tài khoản hệ thống. Đang login mặc định...")
                    login_success = self.auth.default_login(page=page, context=context)
                
                if not login_success:
                    #logger.error("🛑 Đăng nhập thất bại. Kết thúc.")
                    browser.close()
                    raise ValueError("LOGIN_FAILED")
            else:
                #logger.info("✅ Đã đăng nhập sẵn (Cookie còn hiệu lực).")
                pass
            try:
                        context.storage_state(path=str(cookie_path))
                        #logger.info(f"🔄 Đã cập nhật/gia hạn Cookie thành công vào: {cookie_path}")
            except Exception as e:
                        #logger.error(f"⚠️ Lỗi khi cập nhật cookie: {e}")
                        pass
            # ── 3. LẶP QUA MẢNG CÁC GROUP (SỐ LƯỢNG NGẪU NHIÊN) ───────────────
            for index, group in enumerate(groups):
                if client_id and cancel_registry.get(client_id):
                    #logger.info(f"🛑 Đã nhận lệnh hủy cào dữ liệu cho client {client_id}.")
                    
                    break
                if index > 0:
                    # Nghỉ ngẫu nhiên từ 30 giây đến 60 giây (1-3 phút)
                    macro_delay = random.uniform(10, 20)
                    #logger.info(f"⏳ Giãn cách an toàn: Đang nghỉ ngơi {macro_delay:.0f} giây trước khi vào {group.name}...")
                    
                    # Chia nhỏ thời gian sleep để vẫn có thể nhận lệnh hủy (cancel_registry) giữa chừng
                    for _ in range(int(macro_delay)):
                        if client_id and cancel_registry.get(client_id):
                            break
                        time.sleep(1)
                #logger.info(f"🚀 Bắt đầu cào group: {group.name}")
                try:
                    url = group.url
                    if 'sorting_setting=CHRONOLOGICAL' not in url:
                        url += ('&' if '?' in url else '?') + 'sorting_setting=CHRONOLOGICAL'
                    
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    
                    time.sleep(random.uniform(3, 5))
                    
                    all_valid_posts: List[Post] = []
                    seen_urls = set()
                    consecutive_old = 0
                    should_stop = False
                    
                    last_scroll_height = 0
                    scroll_stuck_count = 0
                    MAX_STUCK_LIMIT = 3
                    safe_limit = self.config.SAFE_LIMIT

                    while not should_stop:
                        if client_id and cancel_registry.get(client_id):
                            should_stop = True
                            break

                        try:
                            page.wait_for_selector(self.config.FB_POST_CONTAINER, timeout=5_000)
                        except:
                            pass
                        
                        blocks = page.locator(self.config.FB_POST_CONTAINER).all()
                        
                        for block in blocks:
                            try:
                                # block.scroll_into_view_if_needed()
                                
                                
                                post_url, post_date = PostExtractor.get_info(block)
                                
                                if not post_url or post_url in seen_urls:
                                    continue
                                page.wait_for_timeout(random.randint(50, 100))
                                age = classify_timestamp(post_date)
                                if age == 'old':
                                    consecutive_old += 1
                                    if consecutive_old >= self.config.MAX_OLD_POSTS_LIMIT:
                                        should_stop = True
                                        break
                                    seen_urls.add(post_url)
                                    continue
                                else:
                                    consecutive_old = 0
                                #logger.info(f"👉 Đang bóc bài: URL={post_url} | DATE={post_date} | Lịch sử Seen={len(seen_urls)}")
                                seen_urls.add(post_url)
                                
                                stats = PostExtractor.get_stats(block)
                                score = stats['comments']*2 + stats["reactions"] + stats["shares"]*3
                                media_url = PostExtractor.get_media(block, post_url)
                                image_urls = PostExtractor.get_images(block)
                                content = PostExtractor.get_content(block)

                                post = Post(
                                    url=post_url, date=post_date,
                                    reactions=stats['reactions'], comments=stats['comments'],
                                    shares=stats['shares'], score=score, content=content,
                                    media_url=media_url, images=image_urls,
                                )
                                all_valid_posts.append(post)

                                if len(seen_urls) >= safe_limit:
                                    should_stop = True
                                    break
                            except Exception as e:
                                #logger.debug(f"[block error] {e}")
                                continue

                        if should_stop: break

                        last_scroll_height = page.evaluate("document.documentElement.scrollHeight")
                        
                        for _ in range(random.randint(1, 2)):
                            HumanBehavior.random_scroll(page, max_distance=self.config.SCROLL_DISTANCE)
                        
                        HumanBehavior.gamma_delay(mean=self.config.SCROLL_SLEEP_MIN, shape=2)
                        
                        new_scroll_height = page.evaluate("document.documentElement.scrollHeight")
                        if new_scroll_height == last_scroll_height:
                            scroll_stuck_count += 1
                            if scroll_stuck_count >= MAX_STUCK_LIMIT:
                                break
                        else:
                            scroll_stuck_count = 0

                    # 4. Tổng hợp Group hiện tại
                    sorted_posts = sorted(all_valid_posts, key=lambda x: x.score, reverse=True)
                    summary = GroupSummary(
                        group_name=group.name,
                        link_group=group.url,
                        total_posts_24h=len(all_valid_posts),
                        Intent=group.Intent,
                        hot_post=sorted_posts[0] if sorted_posts else None
                    )
                    results.append(summary)
                    
                   

                except Exception as e:
                    #logger.error(f"❌ Lỗi group {group.name}: {e}")
                    results.append(GroupSummary(group_name=group.name, total_posts_24h=0,Intent=group.Intent, hot_post=None))

            browser.close()
            return results