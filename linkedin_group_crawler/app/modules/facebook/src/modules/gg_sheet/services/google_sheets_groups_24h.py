from typing import Any, Dict, List, Optional
import logging
import gspread
from google.oauth2.service_account import Credentials

# Giả định import từ project của bạn
from app.modules.facebook.src.core.config.env import Config
logger = logging.getLogger(__name__)

class TargetGroupSheet24HService:
    """
    Service chuyên dụng để quản lý danh sách các Group mục tiêu (Sheet 24h)
    Hỗ trợ đầy đủ CRUD: Thêm, Đọc, Sửa, Xóa.
    """
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path = credentials_path
        self.sheet_name = Config.GOOGLE_SHEET_NAME_24H
        
        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client = gspread.authorize(self.creds)
            #logger.info(f"Khởi tạo TargetGroupSheetService cho sheet '{self.sheet_name}' thành công.")
        except Exception as e:
            #logger.error(f"Lỗi khởi tạo TargetGroupSheetService: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str) -> gspread.Worksheet:
        """Hàm helper để lấy worksheet 24h."""
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        return sheet.worksheet(self.sheet_name)

    # ==========================================
    # 1. CREATE (THÊM GROUP MỚI)
    # ==========================================
    def add_target_group(
        self, group: Dict[str, Any], spreadsheet_id: str = Config.SPREADSHEET_ID
    ) -> bool:
        """Thêm một thực thể GroupSummary vào dòng cuối cùng của Sheet 24h."""
        return self.add_multiple_target_groups([group], spreadsheet_id)

    def add_multiple_target_groups(
        self, targets: List[Dict[str, Any]], spreadsheet_id: str = Config.SPREADSHEET_ID
    ) -> bool:
        """Thêm HÀNG LOẠT thực thể GroupSummary vào trang tính.

        Tự động tra cứu và loại bỏ các URL (link_group) đã tồn tại.
        Chỉ gửi lên 3 trường: Tên Group, URL và Intent.
        """
        if not targets:
            #logger.warning(
            #    "Danh sách đầu vào trống. Không có Group mục tiêu nào được chèn."
            #)
            return False

        try:
            worksheet: gspread.Worksheet = self._get_worksheet(spreadsheet_id)
            headers: List[str] = worksheet.row_values(1)

            if not headers:
                # #logger.error(
                #     f"Sheet '{self.sheet_name}' chưa có tiêu đề ở dòng 1. Vui lòng thiết lập Header trước."
                # )
                return False

            # --- Tối ưu hóa: Tải danh sách URL hiện tại để tra cứu nhanh O(1) ---
            url_col_name: str = Config.NAME_URL_GG_SHEET_24H
            existing_urls: set = set()
            
            if url_col_name in headers:
                url_col_idx: int = headers.index(url_col_name) + 1
                col_values: List[str] = worksheet.col_values(url_col_idx)
                # URL trong GroupSummary là trường 'link_group'
                existing_urls = {
                    url.strip() for url in col_values[1:] if url.strip()
                }
            # ------------------------------------------------------------------

            rows_to_insert: List[List[Any]] = []
            skipped_count: int = 0

            for item in targets:
                # ✅ HỖ TRỢ CẢ DICT VÀ OBJECT ENTITY
                # Ưu tiên lấy từ key 'link_group', fallback sang 'url' nếu entity map trực tiếp
                if isinstance(item, dict):
                    url = str(item.get("link_group", item.get("url", ""))).strip()
                    group_name = str(item.get("group_name", "")).strip()
                    intent = str(item.get("intent", item.get("Intent", ""))).strip()
                else:
                    url = str(getattr(item, "link_group", getattr(item, "url", ""))).strip()
                    group_name = str(getattr(item, "group_name", "")).strip()
                    intent = str(getattr(item, "intent", getattr(item, "Intent", ""))).strip()

                if not url:
                    continue

                # Bỏ qua nếu URL đã có trên Sheet
                if url in existing_urls:
                    skipped_count += 1
                    continue

                # ✅ CHỈ CHUẨN BỊ ĐÚNG 3 TRƯỜNG DỮ LIỆU CẦN THIẾT
                row_dict: Dict[str, Any] = {
                    Config.NAME_GROUP_GG_SHEET_24H: group_name,
                    Config.NAME_URL_GG_SHEET_24H: url,
                    Config.INTENT_GG_SHEET_24H: intent,
                }

                # Ánh xạ mảng theo đúng thứ tự tiêu đề cột trên trang tính
                # Các cột khác trên sheet (nếu có) sẽ tự động nhận giá trị rỗng ""
                row: List[Any] = [
                    row_dict.get(header, "") for header in headers
                ]
                rows_to_insert.append(row)

                # Cập nhật set để tránh trùng lặp các item xuất hiện nhiều lần ngay trong batch này
                existing_urls.add(url)

            if rows_to_insert:
                worksheet.append_rows(
                    rows_to_insert, value_input_option="USER_ENTERED"
                )
                # logger.info(
                #     f"Đã chèn {len(rows_to_insert)} Group vào Sheet (Bỏ qua {skipped_count} URL trùng)."
                # )
                return True
            else:
                # logger.info("Không có dữ liệu Group mới nào để chèn vào Sheet.")
                return False

        except Exception as e:
            # logger.error(
            #     f"Lỗi khi thêm GroupSummary vào Sheet 24h: {e}", exc_info=True
            # )
            return False

    # ==========================================
    # 2. READ (ĐỌC DANH SÁCH GROUP)
    # ==========================================
    def get_all_target_groups(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> List[Dict[str, str]]:
        """Lấy toàn bộ danh sách Group cần cào từ Sheet 24h."""
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            records = worksheet.get_all_records()
            target_groups = []

            for row in records:
                url = str(row.get(Config.NAME_URL_GG_SHEET_24H, "")).strip()
                if not url:
                    continue # Bỏ qua dòng trống không có link

                target_groups.append({
                    "group_name": str(row.get(Config.NAME_GROUP_GG_SHEET_24H, "")).strip(),
                    "url": url,
                    "intent": str(row.get(Config.INTENT_GG_SHEET_24H, "")).strip()
                })

            logger.info(f"Đã tải {len(target_groups)} target groups.")
            return target_groups

        except Exception as e:
            logger.error(f"Lỗi khi đọc danh sách Group Sheet 24h: {e}", exc_info=True)
            return []

    # ==========================================
    # 3. UPDATE (SỬA THÔNG TIN GROUP)
    # ==========================================
    def update_target_group(self, target_url: str, update_data: Dict[str, str], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Cập nhật thông tin group dựa vào URL cũ.
        update_data là dict chứa Tên cột (theo ENV) và Giá trị mới.
        """
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            
            # Tìm dòng chứa URL cần sửa
            cell = worksheet.find(target_url)
            if not cell:
                logger.warning(f"Không tìm thấy Group có URL: {target_url} để cập nhật.")
                return False

            row_index = cell.row
            headers = worksheet.row_values(1)

            # Cập nhật từng ô tương ứng với cột gửi lên
            for col_name, new_value in update_data.items():
                if col_name in headers:
                    col_index = headers.index(col_name) + 1 # gspread đếm từ 1
                    worksheet.update_cell(row_index, col_index, new_value)
                else:
                    logger.warning(f"Cột '{col_name}' không tồn tại.")

            logger.info(f"Đã cập nhật thành công dòng {row_index} cho Group URL: {target_url}")
            return True

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy URL: {target_url} trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Group: {e}", exc_info=True)
            return False

    # ==========================================
    # 4. DELETE (XÓA GROUP)
    # ==========================================
    def delete_target_group(self, target_url: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Xóa Group khỏi danh sách cào dựa vào URL."""
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            
            # Tìm dòng chứa URL
            cell = worksheet.find(target_url)
            if not cell:
                logger.warning(f"Không tìm thấy Group có URL: {target_url} để xóa.")
                return False

            row_index = cell.row
            worksheet.delete_rows(row_index)
            logger.info(f"Đã xóa thành công Group dòng {row_index} (URL: {target_url}).")
            return True

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy URL: {target_url} trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi xóa Group: {e}", exc_info=True)
            return False