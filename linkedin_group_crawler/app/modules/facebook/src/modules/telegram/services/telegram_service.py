import logging
import time # Dùng time.sleep thay vì asyncio.sleep
import requests # Dùng requests thay vì httpx
import html
from datetime import datetime
from typing import List

from src.core.config.env import Config
from src.modules.crawl_fb.models.GroupSummary import GroupSummary

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.token = getattr(Config, "TELEGRAM_TOKEN", None)
        self.chat_id = getattr(Config, "TELEGRAM_CHAT_ID", None)
        self.topic_id = getattr(Config, "TELEGRAM_TOPIC_ID", None)
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.max_len = 4000 # Đưa hằng số lên đây để dễ quản lý

    # Đổi thành def bình thường (bỏ async)
    def send_message(self, text: str):
        if not self.token or not self.chat_id:
            logger.warning("⚠️ Chưa cấu hình Telegram Token hoặc Chat ID.")
            return

        if len(text) <= self.max_len:
            self._send_chunk(text)
            logger.info("✅ Đã gửi báo cáo qua Telegram.")
        else:
            logger.info("Tin nhắn quá dài, đang tiến hành chia nhỏ để gửi...")
            lines = text.split('\n')
            current_chunk = ""
            
            for line in lines:
                if len(current_chunk) + len(line) + 1 > self.max_len:
                    self._send_chunk(current_chunk)
                    time.sleep(1) # Dùng time.sleep (đồng bộ)
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            
            # Gửi nốt phần còn lại
            if current_chunk.strip():
                self._send_chunk(current_chunk)
            
            logger.info("✅ Đã gửi xong toàn bộ báo cáo siêu dài qua Telegram.")

    # Đổi thành def bình thường (bỏ async)
    def _send_chunk(self, text: str):
        """Hàm helper để gửi 1 đoạn tin nhắn"""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        # Nếu có topic id thì mới thêm vào payload
        if self.topic_id:
            payload["message_thread_id"] = self.topic_id

        try:
            # Dùng thư viện requests (đồng bộ)
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status() 
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Lỗi Telegram (Status: {e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Không thể kết nối tới Telegram API: {e}")

    # (Hàm format_daily_telegram_report này hoàn toàn giống nguyên bản của bạn, không đổi gì)
    def format_daily_telegram_report(self, summaries: List[GroupSummary]) -> str:
        if not summaries:
            return "ℹ️ <b>Tổng hợp báo cáo CRAWL FB</b>\nHôm nay không có dữ liệu bài viết nào được thu thập."

        today_str = datetime.now().strftime("%d/%m/%Y")
        
        msg = f"🏆 <b>Tổng hợp báo cáo CRAWL FB - {today_str}</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"

        for idx, summary in enumerate(summaries, 1):
            safe_group_name = html.escape(summary.group_name)
            
            msg += f" <b>{idx}. Tên group {safe_group_name}</b>\n"
            msg += f"🔗 <b>Link group:</b> <a href='{summary.link_group}'>Truy cập tại đây</a>\n"
            msg += f"🎯 <b>Mục tiêu (Intent):</b> <code>{summary.Intent}</code>\n"
            msg += f"📊 Tổng bài viết (dưới 24h): <code>{summary.total_posts_24h}</code> bài\n"
            
            hot = summary.hot_post
            if not hot:
               msg += "🔥 <b>BÀI VIẾT HOT NHẤT:</b> Không có bài viết nào đủ điều kiện hoặc group trống.\n"
               msg += "─────────────────────\n\n"
               continue
               
            msg += f"🔥 <b>BÀI VIẾT HOT NHẤT ({hot.score} điểm)</b>\n"
            msg += f"🔗 Link: {hot.url}\n"
            msg += "-------------------------------\n"
            msg += f" Đăng lúc: {hot.date}\n"
            msg += f" Tương tác: 👍 {hot.reactions} | 💬 {hot.comments} | 🔄 {hot.shares}\n"
            msg += f"link bài viết: <a href='{hot.url}'>Xem bài viết gốc</a>\n"
            
            if hot.media_url:
                msg += f"link video: <a href='{hot.media_url}'>Xem Video đính kèm</a>\n"
            
            if hot.images:
                msg += f"🖼 <b>Hình ảnh đính kèm ({len(hot.images)} tấm):</b>\n"
                max_images_to_show = 5 
                
                for img_idx, img_url in enumerate(hot.images[:max_images_to_show], 1):
                    msg += f"   ├─ <a href='{img_url}'>Ảnh số {img_idx}</a>\n"
                
                if len(hot.images) > max_images_to_show:
                    msg += f"   └─ <i>... và {len(hot.images) - max_images_to_show} ảnh khác.</i>\n"
                
            content_snippet = hot.content[:100] + "..." if len(hot.content) > 100 else hot.content
            content_snippet = html.escape(content_snippet)
            
            if content_snippet.strip():
                msg += f"nội dung: <i>\"{content_snippet}\"</i>\n"
                
            msg += "─────────────────────\n\n"

        msg += "🤖 <i>Báo cáo được gửi tự động từ hệ thống Crawl.</i>"
        return msg
    def send_completion_notification(self, message: str = ""):
        """
        Gửi thông báo hoàn tất kèm link Google Sheet vào Topic ID = 1.
        """
        topic_id = Config.TELEGRAM_TOPIC_CHAT_ID
        sheet_link = Config.LINK_GGSHEET
        today_str = datetime.now().strftime("%d/%m/%Y")
        # Build nội dung bằng HTML tag cho đồng bộ với _send_chunk
        text_content = (
            f"✅ <b>ĐÃ HOÀN TẤT TIẾN TRÌNH CÀO DỮ LIỆU - {today_str}</b>\n\n"
            f"{message}\n\n"
            f"📊 <a href='{sheet_link}'>Bấm vào đây để xem toàn bộ dữ liệu trên Google Sheet</a>"
        )

        payload = {
            "chat_id": self.chat_id,
           
            "text": text_content,
            "parse_mode": "HTML",
            "disable_web_page_preview": True # Ẩn cái preview link cho gọn form
        }

        try:
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status()
            logger.info(f"✅ Đã gửi thông báo hoàn tất kèm link vào Topic {topic_id}.")
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Lỗi Telegram khi gửi thông báo Topic (Status: {e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Không thể kết nối tới Telegram API để gửi thông báo Topic: {e}")
    # ─────────────────────────────────────────────────────────────────