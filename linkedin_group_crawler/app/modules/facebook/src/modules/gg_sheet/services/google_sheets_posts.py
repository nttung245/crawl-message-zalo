from typing import Any, Dict, List, Optional
import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Giả định import từ project của bạn
from app.modules.facebook.src.core.config.env import Config
from app.modules.facebook.src.modules.crawl_fb.models.GroupSummary import GroupSummary

logger = logging.getLogger(__name__)

class GoogleSheetServicePosts:
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
            self.sheets_client = gspread.authorize(self.creds)
            logger.info("Khởi tạo GoogleSheetService thành công.")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo Google API Service: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str, sheet_name: Optional[str] =Config.GOOGLE_SHEET_NAME_POST):
        """Hàm helper để lấy worksheet."""
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        
        return sheet.worksheet(sheet_name)
        

    # ==========================================
    # 1. CREATE / APPEND (THÊM DỮ LIỆU)
    # ==========================================
    def append_data(self, data: List[GroupSummary], spreadsheet_id: str = Config.SPREADSHEET_ID, sheet_name: str = Config.GOOGLE_SHEET_NAME_POST) -> bool:
        """Thêm danh sách các bài viết mới vào dòng cuối cùng của Sheet."""
        if not data:
            logger.warning("Không có dữ liệu để insert.")
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id, sheet_name)
            headers = worksheet.row_values(1)
            
            if not headers:
                logger.error("Sheet chưa có tiêu đề ở dòng 1. Không thể map dữ liệu.")
                return False

            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows_to_insert = []

            for item in data:
                post = item.hot_post
                if not post:
                    continue

                image_links = ",\n".join(post.images) if post.images else "Không có hình ảnh"
                
                # Ánh xạ dữ liệu dựa trên tên biến cấu hình cột từ ENV
                row_dict = {
                    Config.CRAWL_DATE_GG_SHEET_POST: current_datetime,
                    Config.NAME_GROUP_GG_SHEET_POST: item.group_name,
                    Config.LINK_GROUP_GG_SHEET_POST: item.link_group,
                    Config.INTENT_GG_SHEET_POST: item.Intent,
                    Config.TOTAL_POSTS_GG_SHEET_POST: item.total_posts_24h,
                    Config.LINK_POST_GG_SHEET_POST: post.url,
                    Config.POST_TIME_GG_SHEET_POST: post.date,
                    Config.CONTENT_GG_SHEET_POST: post.content if post.content else "Không có nội dung",
                    Config.SCORE_GG_SHEET_POST: post.score,
                    Config.LIKES_GG_SHEET_POST: post.reactions,
                    Config.COMMENTS_GG_SHEET_POST: post.comments,
                    Config.SHARES_GG_SHEET_POST: post.shares,
                    Config.LINK_VIDEO_GG_SHEET_POST: post.media_url if post.media_url else "Không có video",
                    Config.LINK_IMAGE_GG_SHEET_POST: image_links
                }

                # Tạo mảng theo đúng thứ tự headers trên Sheet
                row = [row_dict.get(header, "") for header in headers]
                rows_to_insert.append(row)

            worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
            logger.info(f"Đã chèn thành công {len(rows_to_insert)} dòng.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi insert dữ liệu vào Sheet: {e}", exc_info=True)
            return False
    
    # ==========================================
    # 2. READ (LẤY DỮ LIỆU)
    # ==========================================
    def get_all_posts(self, spreadsheet_id: str = Config.SPREADSHEET_ID, sheet_name: Optional[str] = Config.GOOGLE_SHEET_NAME_POST) -> List[Dict[str, Any]]:
        """Đọc toàn bộ dữ liệu từ Sheet và chuẩn hóa format cho FE."""
        try:
            worksheet = self._get_worksheet(spreadsheet_id, sheet_name)
            records = worksheet.get_all_records()
            formatted_data = []

            def parse_int(val):
                try:
                    return int(str(val).replace(",", "")) if val else 0
                except ValueError:
                    return 0

            for row in records:
                # Xử lý hình ảnh
                img_col = Config.LINK_IMAGE_GG_SHEET_POST
                images_raw = str(row.get(img_col, "")).strip()
                if not images_raw or images_raw == "Không có hình ảnh":
                    images_list = []
                else:
                    images_list = [img.strip() for img in images_raw.split(",") if img.strip()]

                # Xử lý video
                vid_col = Config.LINK_VIDEO_GG_SHEET_POST
                raw_video = str(row.get(vid_col, "")).strip()
                media_url_value = None if (not raw_video or raw_video == "Không có video") else raw_video

                post_item = {
                    "group_name": str(row.get(Config.NAME_GROUP_GG_SHEET_POST, "")),
                    "link_group": str(row.get(Config.LINK_GROUP_GG_SHEET_POST, "")),
                    "intent": str(row.get(Config.INTENT_GG_SHEET_POST, "")),
                    "total_posts_24h": parse_int(row.get(Config.TOTAL_POSTS_GG_SHEET_POST, 0)),
                    "url": str(row.get(Config.LINK_POST_GG_SHEET_POST, "")),
                    "date": str(row.get(Config.POST_TIME_GG_SHEET_POST, "")),
                    "dateCrawl": str(row.get(Config.CRAWL_DATE_GG_SHEET_POST, "")),
                    "reactions": parse_int(row.get(Config.LIKES_GG_SHEET_POST, 0)),
                    "comments": parse_int(row.get(Config.COMMENTS_GG_SHEET_POST, 0)),
                    "shares": parse_int(row.get(Config.SHARES_GG_SHEET_POST, 0)),
                    "score": parse_int(row.get(Config.SCORE_GG_SHEET_POST, 0)),
                    "content": str(row.get(Config.CONTENT_GG_SHEET_POST, "")),
                    "media_url": media_url_value,
                    "images": images_list
                }
                formatted_data.append(post_item)

            return formatted_data

        except Exception as e:
            logger.error(f"Lỗi khi đọc Google Sheet: {e}", exc_info=True)
            return []

    # ==========================================
    # 3. UPDATE (SỬA DỮ LIỆU)
    # ==========================================
    def update_post_by_url(self, post_url: str, update_data: Dict[str, Any], spreadsheet_id: str = Config.SPREADSHEET_ID, sheet_name: Optional[str] = Config.GOOGLE_SHEET_NAME_POST) -> bool:
        """
        Cập nhật dòng dữ liệu dựa vào URL bài viết.
        update_data là dict chứa key là TÊN CỘT (theo ENV) và value mới.
        """
        try:
            worksheet = self._get_worksheet(spreadsheet_id, sheet_name)
            
            # Tìm ô chứa URL bài viết
            cell = worksheet.find(post_url)
            if not cell:
                logger.warning(f"Không tìm thấy bài viết với URL: {post_url} để cập nhật.")
                return False

            row_index = cell.row
            headers = worksheet.row_values(1)

            # Cập nhật từng cột được chỉ định
            for col_name, new_value in update_data.items():
                if col_name in headers:
                    col_index = headers.index(col_name) + 1  # gspread index bắt đầu từ 1
                    worksheet.update_cell(row_index, col_index, new_value)
                else:
                    logger.warning(f"Cột '{col_name}' không tồn tại trong sheet.")

            logger.info(f"Đã cập nhật thành công dòng {row_index} cho URL: {post_url}")
            return True

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy URL: {post_url} trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật dữ liệu: {e}", exc_info=True)
            return False

    # ==========================================
    # 4. DELETE (XÓA DỮ LIỆU)
    # ==========================================
    def delete_post_by_url(self, post_url: str, spreadsheet_id: str = Config.SPREADSHEET_ID, sheet_name: Optional[str] = Config.GOOGLE_SHEET_NAME_POST) -> bool:
        """Xóa dòng dữ liệu dựa vào URL bài viết."""
        try:
            worksheet = self._get_worksheet(spreadsheet_id, sheet_name)
            
            # Tìm ô chứa URL bài viết
            cell = worksheet.find(post_url)
            if not cell:
                logger.warning(f"Không tìm thấy bài viết với URL: {post_url} để xóa.")
                return False

            row_index = cell.row
            worksheet.delete_rows(row_index)
            logger.info(f"Đã xóa thành công dòng {row_index} (URL: {post_url}).")
            return True

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy URL: {post_url} trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi xóa dữ liệu: {e}", exc_info=True)
            return False
    def delete_multiple_posts_by_urls(self, post_urls: List[str], spreadsheet_id: str = Config.SPREADSHEET_ID, sheet_name: Optional[str] = Config.GOOGLE_SHEET_NAME_POST) -> bool:
        """
        Xóa HÀNG LOẠT nhiều bài viết cùng lúc dựa trên danh sách URL.
        Kỹ thuật: Tìm toàn bộ các dòng khớp URL, sau đó xóa từ dưới lên trên (Reverse order)
        để không làm xô lệch Index của các dòng chưa xóa.
        """
        if not post_urls:
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id, sheet_name)
            headers = worksheet.row_values(1)
            url_col_name = Config.LINK_POST_GG_SHEET_POST

            if url_col_name not in headers:
                logger.error(f"Không tìm thấy cột '{url_col_name}' để xác định bài viết cần xóa.")
                return False

            url_col_idx = headers.index(url_col_name) + 1
            # Lấy danh sách URL hiện tại trên Sheet (Index mảng Python bắt đầu từ 0, Row Google Sheet bắt đầu từ 1)
            current_urls = worksheet.col_values(url_col_idx) 

            # Tạo Mapping giữa URL và Số dòng (Row Index) của nó trên Sheet
            # Ví dụ: {"https://fb.com/...": 5, "https://fb.com/...": 12}
            url_to_row_map = {}
            for idx, url in enumerate(current_urls):
                if idx == 0: continue # Bỏ qua dòng Header (dòng 1)
                url_to_row_map[url.strip()] = idx + 1 # +1 vì gspread row bắt đầu từ 1

            # Lọc ra các dòng cần xóa dựa vào input gửi lên
            rows_to_delete = []
            target_urls_set = {u.strip() for u in post_urls if u.strip()}

            for t_url in target_urls_set:
                if t_url in url_to_row_map:
                    rows_to_delete.append(url_to_row_map[t_url])
                else:
                    logger.debug(f"Không tìm thấy bài viết '{t_url}' trên Sheet để xóa.")

            if not rows_to_delete:
                logger.warning("Không có URL nào trong danh sách khớp với dữ liệu trên Sheet.")
                return False

            # --- QUAN TRỌNG: Sắp xếp danh sách dòng cần xóa theo thứ tự GIẢM DẦN ---
            # Nếu xóa dòng số 3 trước, dòng số 4 gốc sẽ bị đẩy lên thành dòng 3, làm các thao tác xóa phía sau bị sai ô.
            rows_to_delete.sort(reverse=True)

            # Thực thi xóa
            for row_idx in rows_to_delete:
                worksheet.delete_rows(row_idx)

            logger.info(f"Đã xóa hàng loạt thành công {len(rows_to_delete)} bài viết khỏi Sheet.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi thực thi xóa hàng loạt bài viết: {e}", exc_info=True)
            return False