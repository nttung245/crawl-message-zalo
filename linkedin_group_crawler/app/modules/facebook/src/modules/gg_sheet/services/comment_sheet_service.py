import logging
from typing import List, Dict, Optional
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime,timedelta
# Giả định import cấu hình từ project của bạn
from src.core.config.env import Config

logger = logging.getLogger(__name__)

class CommentSheetService:
    """
    Service quản lý danh sách Comments lấy từ các bài viết trên Google Sheet.
    Cấu trúc: id, url_post, name, like, comment, date comment.
    """
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path = credentials_path
        self.sheet_name = Config.GOOGLE_SHEET_NAME_COMMENTS
        
        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client = gspread.authorize(self.creds)
            logger.info(f"Khởi tạo CommentSheetService cho sheet '{self.sheet_name}' thành công.")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo CommentSheetService: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str) -> gspread.Worksheet:
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        return sheet.worksheet(self.sheet_name)

    # ===================================================
    # 1. CREATE
    # ===================================================
    def add_multiple_comments(self, comments: List[Dict[str, str]], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Thêm hàng loạt Comments (rất phù hợp khi cào dữ liệu trả về 1 list)."""
        if not comments: return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)
            
            if not headers:
                logger.error("Sheet Comments chưa có header.")
                return False

            # Lấy danh sách ID đã có để chống trùng lặp
            existing_records = worksheet.get_all_records()
            id_col = Config.COMMENT_HEADER_ID
            existing_ids = {str(r.get(id_col, "")).strip() for r in existing_records}

            rows_to_insert = []
            count_added = 0
            current_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in comments:
                cmt_id = str(item.get("id", "")).strip()
                
                # Bỏ qua nếu không có ID hoặc ID đã tồn tại
                if not cmt_id or cmt_id in existing_ids:
                    continue

                row_dict = {
                    Config.COMMENT_HEADER_ID: cmt_id,
                    Config.COMMENT_HEADER_URL_POST: str(item.get("url_post", "")),
                    Config.COMMENT_HEADER_NAME: str(item.get("name", "")),
                    Config.COMMENT_HEADER_LIKE: str(item.get("like", "0")),
                    Config.COMMENT_HEADER_COMMENT: str(item.get("comment", "")),
                    Config.COMMENT_HEADER_DATE_COMMENT: current_time
                }
                
                rows_to_insert.append([row_dict.get(h, "") for h in headers])
                existing_ids.add(cmt_id)
                count_added += 1

            if rows_to_insert:
                worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"Đã thêm hàng loạt {count_added} Comments mới.")
                return True
            else:
                logger.info("Không có Comment nào mới để thêm.")
                return False

        except Exception as e:
            logger.error(f"Lỗi khi thêm nhiều Comments: {e}", exc_info=True)
            return False

    # ===================================================
    # 2. READ & DELETE
    # ===================================================
    def get_all_comments(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> List[Dict]:
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            return worksheet.get_all_records()
        except Exception as e:
            logger.error(f"Lỗi khi đọc Comments: {e}", exc_info=True)
            return []

    def delete_comment_by_id(self, comment_id: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Xóa một comment dựa trên ID."""
        comment_id = str(comment_id).strip()
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            cell = worksheet.find(comment_id)
            
            if not cell: return False

            worksheet.delete_rows(cell.row)
            logger.info(f"Đã xóa comment ID '{comment_id}'.")
            return True
        except gspread.exceptions.CellNotFound:
            return False
        except Exception as e:
            logger.error(f"Lỗi khi xóa comment: {e}", exc_info=True)
            return False
        
    def check_comment_new_within_24h(self, url_post: str, comment_id: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Kiểm tra xem comment (theo url_post và id) đã tồn tại trong vòng 24h qua hay chưa.
        - Trả về True: Nếu CHƯA tồn tại, hoặc đã tồn tại nhưng CŨ HƠN 24h.
        - Trả về False: Nếu ĐÃ tồn tại TRONG VÒNG 24h qua.
        """
        url_post = str(url_post).strip()
        comment_id = str(comment_id).strip()

        if not url_post or not comment_id:
            logger.warning("url_post hoặc comment_id truyền vào bị trống.")
            return False

        try:
            records = self.get_all_comments(spreadsheet_id)
            if not records:
                return True  # Sheet trống, nên chắc chắn là mới

            now = datetime.now()

            for record in records:
                r_id = str(record.get(Config.COMMENT_HEADER_ID, "")).strip()
                r_url = str(record.get(Config.COMMENT_HEADER_URL_POST, "")).strip()

                # Kiểm tra khớp ID và URL Post
                if r_id == comment_id and r_url == url_post:
                    date_str = str(record.get(Config.COMMENT_HEADER_DATE_COMMENT, "")).strip()
                    
                    if date_str:
                        try:
                            # Chuyển đổi string ngày tháng từ sheet thành datetime object
                            record_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                            
                            # Tính khoảng thời gian chênh lệch
                            time_difference = now - record_date
                            
                            # Nếu khoảng thời gian <= 24 giờ
                            if time_difference <= timedelta(hours=24):
                                return False  # Đã tồn tại trong 24h -> Trả về False
                                
                        except ValueError:
                            logger.warning(f"Lỗi parse định dạng thời gian '{date_str}' tại ID: {comment_id}")
                            # Nếu format thời gian trong sheet bị lỗi, tiếp tục vòng lặp
                            continue 
                            
            # Nếu chạy hết vòng lặp mà không bị return False, nghĩa là an toàn
            return True

        except Exception as e:
            logger.error(f"Lỗi trong quá trình kiểm tra thời gian tồn tại của comment: {e}", exc_info=True)
            # Trả về True (hoặc False tùy logic business của bạn khi gặp lỗi kết nối/đọc)
            return False