from typing import Dict, List, Optional
import logging
import gspread
from google.oauth2.service_account import Credentials

# Giả định import cấu hình từ project của bạn
from app.modules.facebook.src.core.config.env import Config

logger = logging.getLogger(__name__)

class IntentSheetService:
    """
    Service quản lý danh sách các Intents (Mục tiêu cào dữ liệu) trên Google Sheet.
    Cấu trúc mỗi Intent gồm: Value (Giá trị/Mã) và Name (Tên hiển thị).
    Hỗ trợ CRUD đơn lẻ và các thao tác hàng loạt (Bulk Add/Delete).
    """
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path = credentials_path
        self.sheet_name = Config.GOOGLE_SHEET_NAME_INTENTS
        
        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client = gspread.authorize(self.creds)
            logger.info(f"Khởi tạo IntentSheetService cho sheet '{self.sheet_name}' thành công.")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo IntentSheetService: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str) -> gspread.Worksheet:
        """Hàm helper để lấy trực tiếp worksheet Intents."""
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        return sheet.worksheet(self.sheet_name)

    # ===================================================
    # 1. CREATE (THÊM ĐƠN LẺ & THÊM NHIỀU)
    # ===================================================
    def add_intent(self, intent_value: str, intent_name: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Thêm một Intent mới vào dòng cuối cùng của Sheet."""
        intent_value = intent_value.strip()
        intent_name = intent_name.strip()
        
        if not intent_value or not intent_name:
            logger.warning("Value hoặc Name của Intent không được để trống.")
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)

            if not headers:
                logger.error(f"Sheet '{self.sheet_name}' chưa có tiêu đề dòng 1.")
                return False

            # Kiểm tra tránh trùng lặp Value (Key định danh)
            try:
                cell = worksheet.find(intent_value)
                if cell:
                    logger.warning(f"Intent Value '{intent_value}' đã tồn tại ở dòng {cell.row}. Bỏ qua.")
                    return False
            except gspread.exceptions.CellNotFound:
                pass # Hợp lệ để thêm

            # Map dữ liệu với cấu hình cột từ ENV
            row_dict = {
                Config.VALUE_GG_SHEET_INTENTS: intent_value,
                Config.NAME_GG_SHEET_INTENTS: intent_name
            }

            row_to_insert = [row_dict.get(header, "") for header in headers]
            worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
            logger.info(f"Đã thêm Intent '{intent_name}' thành công.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi thêm Intent: {e}", exc_info=True)
            return False

    def add_multiple_intents(self, intents: List[Dict[str, str]], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Thêm nhiều Intents cùng lúc (Bulk Insert) để tối ưu hiệu năng API.
        Format đầu vào: [{"value": "sale", "name": "Bán hàng"}, {"value": "recruit", "name": "Tuyển dụng"}]
        """
        if not intents:
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)
            
            if not headers:
                logger.error("Sheet chưa có header.")
                return False

            # Lấy danh sách các Value đã có để tránh chèn trùng lặp
            existing_records = worksheet.get_all_records()
            val_col = Config.VALUE_GG_SHEET_INTENTS
            existing_values = {str(r.get(val_col, "")).strip() for r in existing_records}

            rows_to_insert = []
            count_added = 0

            for item in intents:
                val = item.get("value", "").strip()
                name = item.get("name", "").strip()

                if not val or not name or val in existing_values:
                    continue # Bỏ qua nếu thiếu dữ liệu hoặc đã tồn tại

                row_dict = {
                    Config.VALUE_GG_SHEET_INTENTS: val,
                    Config.NAME_GG_SHEET_INTENTS: name
                }
                rows_to_insert.append([row_dict.get(h, "") for h in headers])
                existing_values.add(val) # Thêm vào set local để tránh trùng lặp ngay trong mảng input
                count_added += 1

            if rows_to_insert:
                worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"Đã thêm hàng loạt {count_added} Intents mới thành công.")
                return True
            else:
                logger.info("Không có Intent mới nào hợp lệ để thêm (hoặc tất cả đã tồn tại).")
                return False

        except Exception as e:
            logger.error(f"Lỗi khi thêm nhiều Intents: {e}", exc_info=True)
            return False

    # ===================================================
    # 2. READ (ĐỌC DANH SÁCH INTENTS)
    # ===================================================
    def get_all_intents(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> List[Dict[str, str]]:
        """Lấy toàn bộ danh sách Intent dưới dạng mảng Dictionary."""
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            records = worksheet.get_all_records()
            intents = []

            for row in records:
                val = str(row.get(Config.VALUE_GG_SHEET_INTENTS, "")).strip()
                name = str(row.get(Config.NAME_GG_SHEET_INTENTS, "")).strip()
                
                if val:
                    intents.append({"value": val, "name": name})

            logger.info(f"Đã tải {len(intents)} intents.")
            return intents

        except Exception as e:
            logger.error(f"Lỗi khi đọc danh sách Intent: {e}", exc_info=True)
            return []

    # ===================================================
    # 3. UPDATE (SỬA THÔNG TIN INTENT)
    # ===================================================
    def update_intent(self, target_value: str, new_name: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Cập nhật Tên hiển thị (Name) của một Intent dựa vào Key (Value)."""
        target_value = target_value.strip()
        new_name = new_name.strip()
        
        if not target_value or not new_name:
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            cell = worksheet.find(target_value)
            
            if not cell:
                logger.warning(f"Không tìm thấy Intent Value '{target_value}' để sửa.")
                return False

            headers = worksheet.row_values(1)
            name_col_name = Config.NAME_GG_SHEET_INTENTS
            
            if name_col_name in headers:
                col_idx = headers.index(name_col_name) + 1
                worksheet.update_cell(cell.row, col_idx, new_name)
                logger.info(f"Đã cập nhật Name của '{target_value}' thành '{new_name}'.")
                return True
            else:
                logger.error(f"Cột '{name_col_name}' không tồn tại trên Sheet.")
                return False

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy Intent Value '{target_value}' trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Intent: {e}", exc_info=True)
            return False

    # ===================================================
    # 4. DELETE (XÓA ĐƠN LẺ & XÓA NHIỀU)
    # ===================================================
    def delete_intent(self, target_value: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Xóa một Intent dựa vào Value định danh."""
        target_value = target_value.strip()
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            cell = worksheet.find(target_value)
            
            if not cell:
                logger.warning(f"Không tìm thấy Intent Value '{target_value}' để xóa.")
                return False

            worksheet.delete_rows(cell.row)
            logger.info(f"Đã xóa thành công Intent '{target_value}' ở dòng {cell.row}.")
            return True

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy Intent Value '{target_value}' trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi xóa Intent: {e}", exc_info=True)
            return False

    def delete_multiple_intents(self, target_values: List[str], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Xóa nhiều Intents cùng lúc dựa trên danh sách các Value.
        Thực hiện xóa từ dưới lên trên để không làm sai lệch chỉ số dòng (row index).
        """
        if not target_values:
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            
            # Quét tìm tất cả các cell khớp với danh sách Value cần xóa
            rows_to_delete = []
            for val in set(target_values): # Dùng set lọc trùng input
                val = val.strip()
                if not val: continue
                try:
                    cell = worksheet.find(val)
                    if cell:
                        rows_to_delete.append(cell.row)
                except gspread.exceptions.CellNotFound:
                    logger.debug(f"Không tìm thấy '{val}' để xóa bỏ hàng loạt.")

            if not rows_to_delete:
                logger.warning("Không tìm thấy dòng nào khớp với danh sách Value cần xóa.")
                return False

            # QUAN TRỌNG: Sắp xếp danh sách dòng giảm dần (từ dưới lên trên)
            # Nếu xóa từ trên xuống, các dòng bên dưới sẽ bị đẩy index lên làm tác vụ xóa sau bị sai vị trí.
            rows_to_delete.sort(reverse=True)

            for row_idx in rows_to_delete:
                worksheet.delete_rows(row_idx)

            logger.info(f"Đã xóa thành công {len(rows_to_delete)} dòng Intent.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi xóa hàng loạt Intents: {e}", exc_info=True)
            return False