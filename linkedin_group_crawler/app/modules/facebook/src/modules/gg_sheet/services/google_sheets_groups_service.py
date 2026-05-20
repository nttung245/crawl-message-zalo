import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from app.modules.facebook.src.modules.crawl_fb.models.GroupSummary import GroupSummary
# Giả định import cấu hình từ project của bạn
from app.modules.facebook.src.core.config.env import Config

logger = logging.getLogger(__name__)

class GroupManagementSheetService:
    """
    Service quản lý danh sách Group tổng hợp với đầy đủ các chỉ số chất lượng.
    Hỗ trợ thao tác đơn lẻ và thao tác hàng loạt (Bulk Add / Bulk Delete) nhằm tối ưu hiệu năng API.
    """
    DEFAULT_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH) -> None:
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path: str = credentials_path
        self.sheet_name: str = Config.GOOGLE_SHEET_NAME_GROUPS
        
        try:
            self.creds: Credentials = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client: gspread.Client = gspread.authorize(self.creds)
            logger.info(f"Khởi tạo GroupManagementSheetService cho sheet '{self.sheet_name}' thành công.")
        except Exception as e:
            #logger.error(f"Lỗi khởi tạo GroupManagementSheetService: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str) -> gspread.Worksheet:
        """Hàm helper để lấy trực tiếp worksheet."""
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        return sheet.worksheet(self.sheet_name)

    # ===================================================
    # 1. CREATE (THÊM ĐƠN LẺ & THÊM HÀNG LOẠT)
    # ===================================================
    def add_group(self, 
                  group_name: str, 
                  group_url: str, 
                  intent: str, 
                  members: int = 0, 
                  posts_per_week: int = 0, 
                  health_score: float = 0.0,
                  chay_24h: Optional[bool] = False,
                  spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Thêm một Group mới vào dòng cuối cùng của Sheet."""
        # Chuyển tiếp sang hàm xử lý hàng loạt để tái sử dụng logic kiểm tra trùng lặp
        group_data: List[Dict[str, Any]] = [{
            "group_name": group_name,
            "url": group_url,
            "intent": intent,
            "members": members,
            "posts_per_week": posts_per_week,
            "health_score": health_score,
            "chay_24h": chay_24h
        }]
        return self.add_multiple_groups(group_data, spreadsheet_id)

    def add_multiple_groups(self, groups: List[GroupSummary], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Thêm HÀNG LOẠT nhiều Group cùng lúc (Bulk Insert).
        Tự động kiểm tra và bỏ qua các URL đã tồn tại trên trang tính.
        Dữ liệu được lấy chuẩn xác từ model GroupSummary và Post.
        """
        if not groups:
            logger.warning("Danh sách đầu vào trống. Không có Group nào được chèn.")
            return False

        try:
            worksheet: gspread.Worksheet = self._get_worksheet(spreadsheet_id)
            headers: List[str] = worksheet.row_values(1)

            if not headers:
                logger.error(f"Sheet '{self.sheet_name}' chưa có tiêu đề ở dòng 1.")
                return False

            # --- Tải danh sách URL hiện tại để tra cứu O(1) ---
            url_col_name: str = Config.NAME_URL_GG_SHEET
            existing_urls: set = set()
            if url_col_name in headers:
                url_col_idx: int = headers.index(url_col_name) + 1
                col_values: List[str] = worksheet.col_values(url_col_idx)
                existing_urls = {url.strip() for url in col_values[1:] if url.strip()}
            # ---------------------------------------------------------------

            current_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows_to_insert: List[List[Any]] = []
            skipped_count: int = 0

            for group in groups:
                url: str = str(getattr(group, "link_group", "")).strip()
                if not url:
                    continue

                if url in existing_urls:
                    skipped_count += 1
                    continue

                # Xử lý an toàn cho hot_post (nếu sau này cần bóc thông tin bài hot)
                hot_post = getattr(group, "hot_post", None)

                # Mapping dữ liệu chuẩn theo thực tế của model GroupSummary
                row_dict: Dict[str, Any] = {
                    Config.NAME_GROUP_GG_SHEET: str(getattr(group, "group_name", "")).strip(),
                    Config.NAME_URL_GG_SHEET: url,
                    Config.INTENT_GG_SHEET: str(getattr(group, "intent", "")).strip(),
                    Config.LAST_CRAWL_GG_SHEET: current_time,
                    Config.POSTS_PER_WEEK_GG_SHEET: int(getattr(group, "total_posts_24h", 0)), 
                    Config.MEMBERS_GG_SHEET: 0, 
                    Config.HEALTH_SCORE_GG_SHEET: 0.0,
                    Config.CHAY_24H_GG_SHEET_POST: "TRUE" if getattr(group, "chay_24h", False) else "FALSE" 
                }

                # Ánh xạ thành mảng 2D theo đúng thứ tự tiêu đề sheet
                row: List[Any] = [row_dict.get(header, "") for header in headers]
                rows_to_insert.append(row)
                existing_urls.add(url)

            if rows_to_insert:
                worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"Đã chèn thành công {len(rows_to_insert)} Group mới (Bỏ qua {skipped_count} Group trùng URL).")
                return True
            else:
                logger.info(f"Không có Group mới nào được chèn (Toàn bộ {skipped_count} Group đều đã tồn tại).")
                return False

        except Exception as e:
            logger.error(f"Lỗi khi thêm hàng loạt Group: {e}", exc_info=True)
            return False
    def add_multiple_groups_from_dicts(self, groups: List[Dict[str, Any]], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        [DÀNH RIÊNG CHO ROUTER]
        Thêm HÀNG LOẠT Group từ dữ liệu dạng List[Dict].
        """
        if not groups:
            logger.warning("Danh sách đầu vào trống. Không có Group nào được chèn.")
            return False

        try:
            worksheet: gspread.Worksheet = self._get_worksheet(spreadsheet_id)
            headers: List[str] = worksheet.row_values(1)

            if not headers:
                logger.error(f"Sheet '{self.sheet_name}' chưa có tiêu đề ở dòng 1.")
                return False

            # --- Tải danh sách URL hiện tại để tra cứu O(1) ---
            url_col_name: str = Config.NAME_URL_GG_SHEET
            existing_urls: set = set()
            if url_col_name in headers:
                url_col_idx: int = headers.index(url_col_name) + 1
                col_values: List[str] = worksheet.col_values(url_col_idx)
                existing_urls = {url.strip() for url in col_values[1:] if url.strip()}
            # ---------------------------------------------------------------

            current_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows_to_insert: List[List[Any]] = []
            skipped_count: int = 0

            for group in groups:
                # DÙNG .get() VÌ ĐÂY LÀ DICTIONARY
                url: str = str(group.get("link_group", "")).strip()
                if not url:
                    continue

                if url in existing_urls:
                    skipped_count += 1
                    continue

                # Mapping dữ liệu từ Dictionary
                row_dict: Dict[str, Any] = {
                    Config.NAME_GROUP_GG_SHEET: str(group.get("group_name", "")).strip(),
                    Config.NAME_URL_GG_SHEET: url,
                    Config.INTENT_GG_SHEET: str(group.get("intent", group.get("Intent", ""))).strip(),
                    Config.LAST_CRAWL_GG_SHEET: current_time,
                    Config.POSTS_PER_WEEK_GG_SHEET: int(group.get("posts_per_week", 0)), 
                    Config.MEMBERS_GG_SHEET: int(group.get("members", 0)), 
                    Config.HEALTH_SCORE_GG_SHEET: float(group.get("health_score", 0.0)),
                    Config.CHAY_24H_GG_SHEET_POST: "TRUE" if group.get("chay_24h", False) else "FALSE" 
                }

                # Ánh xạ thành mảng 2D theo đúng thứ tự tiêu đề sheet
                row: List[Any] = [row_dict.get(header, "") for header in headers]
                rows_to_insert.append(row)
                existing_urls.add(url)

            if rows_to_insert:
                worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"Đã chèn thành công {len(rows_to_insert)} Group mới (Bỏ qua {skipped_count} Group trùng URL).")
                return True
            else:
                logger.info(f"Không có Group mới nào được chèn (Toàn bộ {skipped_count} Group đều đã tồn tại).")
                return False

        except Exception as e:
            logger.error(f"Lỗi khi thêm hàng loạt Group từ Dict: {e}", exc_info=True)
            return False
    # ===================================================
    # 2. READ (ĐỌC DANH SÁCH GROUP)
    # ===================================================
    def get_all_groups(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh sách Group và ép kiểu dữ liệu an toàn."""
        try:
            worksheet: gspread.Worksheet = self._get_worksheet(spreadsheet_id)
            records: List[Dict[str, Any]] = worksheet.get_all_records()
            groups: List[Dict[str, Any]] = []

            def parse_int(val: Any) -> int:
                try: return int(str(val).replace(",", "").strip())
                except (ValueError, TypeError): return 0

            def parse_float(val: Any) -> float:
                try: return float(str(val).replace(",", "").strip())
                except (ValueError, TypeError): return 0.0

            def parse_bool(val: Any) -> Optional[bool]:
                val_str = str(val).strip().upper()
                if val_str in ("TRUE", "1"): return True
                if val_str in ("FALSE", "0"): return False
                return None

            for row in records:
      
                url: str = str(row.get(Config.NAME_URL_GG_SHEET, "")).strip()
                if not url:
                    continue

                groups.append({
                    "group_name": str(row.get(Config.NAME_GROUP_GG_SHEET, "")).strip(),
                    "url": url,
                    "intent": str(row.get(Config.INTENT_GG_SHEET, "")).strip(),
                    "members": parse_int(row.get(Config.MEMBERS_GG_SHEET, 0)),
                    "posts_per_week": parse_int(row.get(Config.POSTS_PER_WEEK_GG_SHEET, 0)),
                    "last_crawl": str(row.get(Config.LAST_CRAWL_GG_SHEET, "")).strip(),
                    "health_score": parse_float(row.get(Config.HEALTH_SCORE_GG_SHEET, 0.0)),
                    "chay_24h": parse_bool(row.get(Config.CHAY_24H_GG_SHEET_POST, None))
                })

            logger.info(f"Đã tải {len(groups)} groups từ Sheet '{self.sheet_name}'.")
             # Debug intent của group đầu tiên

            return groups
        except Exception as e:
            logger.error(f"Lỗi khi đọc danh sách Group: {e}", exc_info=True)
            return []

    # ===================================================
    # 3. UPDATE (SỬA/CẬP NHẬT CHỈ SỐ GROUP)
    # ===================================================
    def update_group_metrics(self, group_url: str, update_data: Dict[str, Any], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Cập nhật thông tin/chỉ số của một Group cụ thể dựa vào URL."""
        try:
            worksheet: gspread.Worksheet = self._get_worksheet(spreadsheet_id)
            cell: Optional[gspread.cell.Cell] = worksheet.find(group_url)
            
            if not cell:
                logger.warning(f"Không tìm thấy Group URL: {group_url} để cập nhật.")
                return False

            row_index: int = cell.row
            headers: List[str] = worksheet.row_values(1)

            # Tự động gán Last Crawl nếu tác vụ không có chỉ định
            if Config.LAST_CRAWL_GG_SHEET in headers and Config.LAST_CRAWL_GG_SHEET not in update_data:
                update_data[Config.LAST_CRAWL_GG_SHEET] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Nếu có update trường chay_24h, tự động parse sang dạng text để Sheet hiển thị đúng định dạng
            if Config.CHAY_24H_GG_SHEET_POST in update_data:
                raw_val = update_data[Config.CHAY_24H_GG_SHEET_POST]
                if isinstance(raw_val, bool):
                    update_data[Config.CHAY_24H_GG_SHEET_POST] = "TRUE" if raw_val else "FALSE"

            for col_name, new_value in update_data.items():
                if col_name in headers:
                    col_index: int = headers.index(col_name) + 1
                    worksheet.update_cell(row_index, col_index, new_value)
                else:
                    logger.warning(f"Cột '{col_name}' không tồn tại trên Sheet.")

            logger.info(f"Đã cập nhật chỉ số thành công cho URL: {group_url}")
            return True

        except gspread.exceptions.CellNotFound:
            logger.warning(f"Không tìm thấy URL: {group_url} trong Sheet.")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Group: {e}", exc_info=True)
            return False

    # ===================================================
    # 4. DELETE (XÓA ĐƠN LẺ & XÓA HÀNG LOẠT)
    # ===================================================
    def delete_group(self, group_url: str, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """Xóa một dòng Group dựa vào URL."""
        return self.delete_multiple_groups([group_url], spreadsheet_id)

    def delete_multiple_groups(self, target_urls: List[str], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Xóa HÀNG LOẠT nhiều Group cùng lúc dựa trên danh sách URL.
        Áp dụng cơ chế Reverse-Delete (xóa ngược từ dưới lên) để bảo toàn cấu trúc chỉ số index.
        """
        if not target_urls:
            return False

        try:
            worksheet: gspread.Worksheet = self._get_worksheet(spreadsheet_id)
            headers: List[str] = worksheet.row_values(1)
            url_col_name: str = Config.NAME_URL_GG_SHEET

            if url_col_name not in headers:
                logger.error(f"Không tìm thấy cột '{url_col_name}' để định vị dòng cần xóa.")
                return False

            # Tải toàn bộ URL hiện tại và tạo Mapping: {URL: Row_Index}
            url_col_idx: int = headers.index(url_col_name) + 1
            current_urls: List[str] = worksheet.col_values(url_col_idx)

            url_to_row_map: Dict[str, int] = {}
            for idx, url in enumerate(current_urls):
                if idx == 0: continue # Bỏ qua header
                url_to_row_map[url.strip()] = idx + 1

            # Lọc ra các dòng cần xóa
            rows_to_delete: List[int] = []
            unique_targets: set = {u.strip() for u in target_urls if u.strip()}

            for t_url in unique_targets:
                if t_url in url_to_row_map:
                    rows_to_delete.append(url_to_row_map[t_url])
                else:
                    logger.debug(f"Bỏ qua URL không tồn tại trên Sheet: '{t_url}'")

            if not rows_to_delete:
                logger.warning("Không có URL nào khớp với dữ liệu trên trang tính để xóa.")
                return False

            # --- QUAN TRỌNG: Sắp xếp danh sách dòng cần xóa theo thứ tự GIẢM DẦN ---
            rows_to_delete.sort(reverse=True)

            # Thực thi xóa dòng
            for row_idx in rows_to_delete:
                worksheet.delete_rows(row_idx)

            logger.info(f"Đã xóa hàng loạt thành công {len(rows_to_delete)} Group khỏi Sheet.")
            return True

        except Exception as e:
            logger.error(f"Lỗi khi thực thi xóa hàng loạt Group: {e}", exc_info=True)
            return False