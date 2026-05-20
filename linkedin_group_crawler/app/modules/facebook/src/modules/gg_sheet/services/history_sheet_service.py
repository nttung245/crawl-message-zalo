import logging
from typing import List, Dict, Optional
import gspread
from google.oauth2.service_account import Credentials

# Giả định import cấu hình từ project của bạn
from app.modules.facebook.src.core.config.env import Config

logger = logging.getLogger(__name__)

class HistorySheetService:
    """
    Service quản lý danh sách Lịch sử điểm hàng tuần (Weekly History) trên Google Sheet.
    Cấu trúc: id, name, score/week, date per week.
    """
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path = credentials_path
        self.sheet_name = Config.GOOGLE_SHEET_NAME_HISTORY
        
        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client = gspread.authorize(self.creds)
            logger.info(f"Khởi tạo HistorySheetService cho sheet '{self.sheet_name}' thành công.")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo HistorySheetService: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str) -> gspread.Worksheet:
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        return sheet.worksheet(self.sheet_name)

    # ===================================================
    # 1. CREATE
    # ===================================================
    def add_history_record(self, record_id: str, name: str, score: str, date: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Thêm một bản ghi lịch sử mới."""
        record_id, name = str(record_id).strip(), str(name).strip()
        
        if not record_id or not name:
            logger.warning("ID hoặc Name không được để trống.")
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)

            if not headers:
                logger.error(f"Sheet '{self.sheet_name}' chưa có tiêu đề dòng 1.")
                return False

            row_dict = {
                Config.HISTORY_HEADER_ID: record_id,
                Config.HISTORY_HEADER_NAME: name,
                Config.HISTORY_HEADER_SCORE_WEEK: str(score),
                Config.HISTORY_HEADER_DATE_PER_WEEK: str(date)
            }

            row_to_insert = [row_dict.get(header, "") for header in headers]
            worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
            logger.info(f"Đã thêm lịch sử cho '{name}' thành công.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi thêm lịch sử: {e}", exc_info=True)
            return False

    def add_multiple_histories(self, records: List[Dict[str, str]], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Thêm hàng loạt bản ghi lịch sử."""
        if not records: return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)
            
            if not headers: return False

            rows_to_insert = []
            for item in records:
                row_dict = {
                    Config.HISTORY_HEADER_ID: str(item.get("id", "")).strip(),
                    Config.HISTORY_HEADER_NAME: str(item.get("name", "")).strip(),
                    Config.HISTORY_HEADER_SCORE_WEEK: str(item.get("score", "")).strip(),
                    Config.HISTORY_HEADER_DATE_PER_WEEK: str(item.get("date", "")).strip()
                }
                rows_to_insert.append([row_dict.get(h, "") for h in headers])

            if rows_to_insert:
                worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"Đã thêm {len(rows_to_insert)} bản ghi lịch sử.")
                return True
            return False
        except Exception as e:
            logger.error(f"Lỗi khi thêm nhiều lịch sử: {e}", exc_info=True)
            return False

    # ===================================================
    # 2. READ
    # ===================================================
    def get_all_histories(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> List[Dict[str, str]]:
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            records = worksheet.get_all_records()
            return records
        except Exception as e:
            logger.error(f"Lỗi khi đọc lịch sử: {e}", exc_info=True)
            return []