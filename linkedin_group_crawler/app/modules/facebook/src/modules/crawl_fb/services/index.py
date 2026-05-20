import logging
import asyncio
from typing import List, Optional
from fastapi import HTTPException, status 
from fastapi.concurrency import run_in_threadpool
from src.modules.crawl_fb.schemas.crawl_schema import CrawlPayload
from src.modules.crawl_fb.models.GroupSummary import GroupSummary
from src.modules.facebook.services.facebook_scraper import FacebookScraper
from src.modules.telegram.services.telegram_service import TelegramService
from src.modules.gg_sheet.services.google_sheets_groups_service import GroupManagementSheetService
from src.modules.gg_sheet.services.google_sheets_posts import GoogleSheetServicePosts
from src.modules.gg_sheet.services.google_sheets_groups_24h import TargetGroupSheet24HService
from src.modules.gg_sheet.services.google_sheets_intent_service import IntentSheetService


logger = logging.getLogger(__name__)

# ĐÃ XÓA Ổ KHÓA TOÀN CỤC (crawl_lock) ĐỂ CHẠY SONG SONG KHÔNG GIỚI HẠN

class CrawlService:
    def __init__(
        self, 
        scraper: FacebookScraper, 
        telegram: TelegramService, 
        group_sheet: GroupManagementSheetService,
        post_sheet: GoogleSheetServicePosts,
        group_24h_sheet:TargetGroupSheet24HService,
        intent_sheet:IntentSheetService
    ):
        self.scraper = scraper
        self.telegram = telegram
        self.group_sheet = group_sheet
        self.post_sheet = post_sheet
        self.group_24h_sheet = group_24h_sheet
        self.intent_sheet = intent_sheet


    async def _execute_scraping(self, payload: CrawlPayload, client_id: Optional[str] = None) -> List[GroupSummary]:
     
        # THAY VÌ: return await self.scraper.scrape_groups(...)
        # HÃY DÙNG:
        return await run_in_threadpool(
            self.scraper.scrape_groups, 
            groups=payload.groups,
            custom_email=getattr(payload.tkFB, 'useName', None), 
            custom_pass=getattr(payload.tkFB, 'password', None),
            client_id=client_id
        )

    # DÙNG CHO CRONJOB / SCHEDULER (Chạy ngầm theo lịch)
    async def CrawlDataGroupFB(self, payload: CrawlPayload):
        try:
            # ĐÃ BỎ async with crawl_lock, CHẠY TRỰC TIẾP
            daily_summary_report = await self._execute_scraping(payload)
             
            if daily_summary_report:
                self.post_sheet.append_data(data=daily_summary_report)
                self.telegram.send_completion_notification()
                mes = self.telegram.format_daily_telegram_report(summaries=daily_summary_report)
                self.telegram.send_message(mes)
                return {"status": "success", "message": "Cào dữ liệu hoàn tất."}
            else:
                self.telegram.send_message("ℹ️ *Báo cáo Crawler*\nKhông có bài viết mới.")
                return {"status": "success", "message": "Hoàn tất nhưng không có dữ liệu."}
                
        except ValueError as e:
            if str(e) == "LOGIN_FAILED":
                self.telegram.send_message("🚨 *LỖI ĐĂNG NHẬP*\nSai tài khoản hoặc Checkpoint!")
                return {"status": "error", "message": "Đăng nhập thất bại."}
            raise e 
        
        except Exception as e:
            logger.error(f"Lỗi hệ thống bất ngờ: {e}")
            self.telegram.send_message(f"❌ *Lỗi hệ thống Crawler*\n{str(e)[:100]}...")
            return {"status": "error", "message": "Lỗi hệ thống."}

    # DÙNG CHO FRONTEND GỌI API (Có trả Data về FE)
    async def FetchDataDirectly(self, payload: CrawlPayload, client_id: Optional[str] = None):
        try:
            # ĐÃ BỎ async with crawl_lock, CHẠY TRỰC TIẾP
            scraped_data = await self._execute_scraping(payload, client_id=client_id)
            
            if scraped_data:
                await asyncio.gather(
                    asyncio.to_thread(self.post_sheet.append_data, scraped_data),
                    asyncio.to_thread(self.group_sheet.add_multiple_groups, scraped_data)
                )
                return {"status": "success", "message": "Cào thành công.", "data": scraped_data}
            else:
                return {"status": "success", "message": "Không có bài viết mới.", "data": []}

        except ValueError as e:
            if str(e) == "LOGIN_FAILED":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Sai tài khoản, mật khẩu hoặc dính Checkpoint."
                )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        except Exception as e:
            logger.error(f"Lỗi hệ thống: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Hệ thống Crawler gặp sự cố: {str(e)}"
            )
            
    async def get_all_posts_from_sheet(self):
        try:
            records = await run_in_threadpool(self.post_sheet.get_all_posts)  # Giả sử có hàm get_all_posts() trong GoogleSheetServicePosts
            return {
                "status": "success", 
                "message": "Lấy dữ liệu thành công.", 
                "data": records
            }
            
        except Exception as e:
            logger.error(f"Lỗi khi đọc Google Sheet: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Không thể đọc dữ liệu từ Google Sheets: {str(e)}"
            )
        
