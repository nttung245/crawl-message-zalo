from typing import Any, Dict, List, Optional
import logging
from dataclasses import dataclass
from datetime import datetime

import gspread  # Dùng gspread đồng bộ nguyên bản
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.modules.facebook.src.core.config.env import Config
from app.modules.facebook.src.modules.crawl_fb.models.GroupSummary import GroupSummary

logger = logging.getLogger(__name__)

@dataclass
class GoogleSheetRow:
    ngay_crawl: str
    name_group: str
    tong_bai_viet: int
    link_post: str
    gio_dang: str
    noi_dung: str
    diem: float
    like: int
    binh_luan: int
    chia_se: int
    link_video: str
    link_anh: str

    def to_sheet_dict(self) -> Dict[str, Any]:
        return {
            "Ngày Crawl": self.ngay_crawl,
            "Name Group": self.name_group,
            "tổng bài viết": self.tong_bai_viet,
            "Link post": self.link_post,
            "Giờ đăng": self.gio_dang,
            "Nội dung": self.noi_dung,
            "Điểm": self.diem,
            "Like": self.like,
            "Bình luận": self.binh_luan,
            "Chia sẽ": self.chia_se,
            "Link video": self.link_video,
            "Link ảnh": self.link_anh
        }

class GoogleApiService:
    SHEET_MIME_TYPE = 'application/vnd.google-apps.spreadsheet'
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path = credentials_path
        
        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.drive_service = build("drive", "v3", credentials=self.creds)
            
            # Khởi tạo client gspread đồng bộ
            self.sheets_client = gspread.authorize(self.creds)
            logger.info("Khởi tạo GoogleApiService (Đồng bộ) thành công.")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo Google API Service: {e}", exc_info=True)
            raise

    # Đổi thành def bình thường (bỏ async)
    def find_sheets_in_folder(self, folder_id: str) -> List[Dict[str, str]]:
        query = f"'{folder_id}' in parents and mimeType = '{self.SHEET_MIME_TYPE}'"
        try:
            # Chạy đồng bộ trực tiếp, không cần asyncio.to_thread
            results = self.drive_service.files().list(
                q=query, 
                fields="files(id, name)"
            ).execute()
            
            files = results.get("files", [])
            logger.info(f"Tìm thấy {len(files)} file Sheets trong thư mục {folder_id}.")
            return files
        except HttpError as e:
            logger.error(f"Lỗi API khi tìm file trong Drive: {e}")
            return []
        except Exception as e:
            logger.error(f"Lỗi hệ thống khi tìm file: {e}")
            return []

    # Đổi thành def bình thường (bỏ async)
    def get_sheet_data(self, spreadsheet_id: str, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            sheet = self.sheets_client.open_by_key(spreadsheet_id)
            worksheet = sheet.worksheet(sheet_name) if sheet_name else sheet.get_worksheet(0)
            
            # Hàm chạy đồng bộ
            data = worksheet.get_all_records()
            logger.info(f"Đã tải {len(data)} bản ghi từ Sheet ID: {spreadsheet_id[:10]}...")
            return data
            
        except Exception as e:
            logger.error(f"Lỗi khi tải dữ liệu Sheet: {e}", exc_info=True)
            return []

    def transform_to_sheet_format(self, scraped_data: List[GroupSummary]) -> List[Dict[str, Any]]:
        formatted_data = []
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for item in scraped_data:
            post = item.hot_post
            if not post:
                continue
            
            post_time = post.date 
            image_links = ",\n".join(post.images) if post.images else "Không có hình ảnh"

            row = {
                "Ngày Crawl": current_datetime,
                "Name Group": item.group_name,
                "tổng bài viết": item.total_posts_24h,
                "Link post": post.url,
                "Giờ đăng": post_time,
                "Nội dung": post.content if post.content else "Không có nội dung",
                "Điểm": post.score,
                "Like": post.reactions,
                "Bình luận": post.comments,
                "Chia sẽ": post.shares, 
                "Link video": post.media_url if post.media_url else "Không có video", 
                "Link ảnh": image_links
            }
            formatted_data.append(row)
            
        return formatted_data
    
    # Đổi thành def bình thường (bỏ async)
    def append_data_to_sheet(self, data: List[GroupSummary], spreadsheet_id: str=Config.SPREADSHEET_ID, sheet_name: Optional[str] = Config.GOOGLE_SHEET_NAME_APPEND) -> bool:
        if not data:
            logger.warning("Không có dữ liệu để insert.")
            return False

        try:
            formatted_data = self.transform_to_sheet_format(data)

            sheet = self.sheets_client.open_by_key(spreadsheet_id)
            worksheet = sheet.worksheet(sheet_name) if sheet_name else sheet.get_worksheet(0)
            
            # Hàm chạy đồng bộ
            headers = worksheet.row_values(1)
            
            if not headers:
                logger.error("Sheet chưa có tiêu đề ở dòng 1. Không thể map dữ liệu.")
                return False

            rows_to_insert = []
            for item in formatted_data: 
                row = [item.get(header, "") for header in headers]
                rows_to_insert.append(row)
            
            # Hàm chạy đồng bộ
            worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
            
            logger.info(f"Đã chèn thành công {len(rows_to_insert)} dòng vào Sheet ID: {spreadsheet_id[:10]}...")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi insert dữ liệu vào Sheet: {e}", exc_info=True)
            return False
        

    def get_all_posts_from_sheet(self, sheet_url_or_id: str=Config.SPREADSHEET_ID, sheet_name: str = Config.GOOGLE_SHEET_NAME_APPEND):
        """
        Đọc dữ liệu từ Sheet và format lại cho FE
        """
        try:
            # Mở file Google Sheet (có thể mở bằng URL hoặc ID)
            spreadsheet = self.sheets_client.open_by_key(sheet_url_or_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            # get_all_records() tự động lấy dòng đầu tiên (Header) làm Key cho Dictionary
            records = worksheet.get_all_records()
            
            formatted_data = []
            
            for row in records:
                # Xử lý mảng link ảnh
                images_raw = str(row.get("Link ảnh", "")).strip()

                 # Kiểm tra nếu chuỗi rỗng hoặc chứa văn bản báo không có ảnh
                if not images_raw or images_raw == "Không có hình ảnh":
                     images_list = [] # Hoặc [] nếu bạn muốn FE vẫn nhận được một mảng
                else:
                       # Nếu có dữ liệu, tiến hành split như cũ
                     images_list = [img.strip() for img in images_raw.split(",") if img.strip()]
                # Hàm ép kiểu số an toàn
                def parse_int(val):
                    try:
                        return int(str(val).replace(",", "")) if val else 0
                    except ValueError:
                        return 0

                # Lấy Ngày Crawl từ sheet
                raw_video = str(row.get("Link video", "")).strip()
                raw_date_crawl = str(row.get("Ngày Crawl", ""))
                if not raw_video or raw_video == "Không có video":
                         media_url_value = None
                else:
                        media_url_value = raw_video
                # Format lại dữ liệu chuẩn với Interface của FE
                post_item = {
                    "group_name": str(row.get("Name Group", "")),
                    "total_posts_24h": parse_int(row.get("tổng bài viết", 0)),
                    "url": str(row.get("Link post", "")),
                    
                    # date bây giờ chỉ chứa Giờ/Ngày đăng thực tế của bài viết
                    "date": str(row.get("Giờ đăng", "")), 
                    
                    # dateCrawl lấy từ cột Ngày Crawl
                    "dateCrawl": raw_date_crawl, 
                    
                    "reactions": parse_int(row.get("Like", 0)),
                    "comments": parse_int(row.get("Bình luận", 0)),
                    "shares": parse_int(row.get("Chia sẽ", 0)),
                    "score": parse_int(row.get("Điểm", 0)),
                    "content": str(row.get("Nội dung", "")),
                    "media_url": media_url_value,
                    "images": images_list
                }
                
                formatted_data.append(post_item)
                
            return formatted_data
            
        except Exception as e:
            print(f"Lỗi khi đọc Google Sheet: {e}")
            return []  