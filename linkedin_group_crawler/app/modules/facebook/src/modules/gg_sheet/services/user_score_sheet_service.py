from typing import Dict, List, Optional
import logging
import gspread
from google.oauth2.service_account import Credentials

# Giả định import cấu hình từ project của bạn
from app.modules.facebook.src.core.config.env import Config

logger = logging.getLogger(__name__)

class UserScoreSheetService:
    """
    Service quản lý trang tính User_Scores hiện tại (Trang tính chính đang chạy).
    Cấu trúc gồm: id, name, score/week.
    Hỗ trợ đọc dữ liệu, cập nhật điểm và reset điểm về 0 vào cuối tuần.
    """
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive" 
    ]

    def __init__(self, credentials_path: str = Config.GOOGLE_CREDENTIALS_PATH):
        if not credentials_path:
            raise ValueError("Đường dẫn credentials_path không được để trống.")
        
        self.credentials_path = credentials_path
        self.sheet_name = Config.GOOGLE_SHEET_NAME_USERS
        
        try:
            self.creds = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=self.DEFAULT_SCOPES
            )
            self.sheets_client = gspread.authorize(self.creds)
            logger.info(f"Khởi tạo UserScoreSheetService cho sheet '{self.sheet_name}' thành công.")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo UserScoreSheetService: {e}", exc_info=True)
            raise

    def _get_worksheet(self, spreadsheet_id: str) -> gspread.Worksheet:
        """Hàm helper lấy worksheet User_Scores."""
        sheet = self.sheets_client.open_by_key(spreadsheet_id)
        return sheet.worksheet(self.sheet_name)

    # ===================================================
    # 1. READ (Đọc dữ liệu để chuẩn bị backup sang History)
    # ===================================================
    def get_all_user_scores(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> List[Dict]:
        """Lấy toàn bộ danh sách thành viên và điểm số tuần này."""
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            return worksheet.get_all_records()
        except Exception as e:
            logger.error(f"Lỗi khi đọc bảng điểm User_Scores: {e}", exc_info=True)
            return []

    # ===================================================
    # 2. UPDATE (Cập nhật điểm trong tuần)
    # ===================================================
    # ===================================================
    # 2. UPDATE (Cập nhật điểm trong tuần - Hỗ trợ Upsert)
    # ===================================================
    def update_user_score(self, user_id: str, user_name: str = "", score_to_add: int = 1, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Cập nhật điểm cho user. 
        - Nếu ID đã tồn tại: Lấy điểm cũ cộng thêm 'score_to_add' (mặc định là 1).
        - Nếu ID chưa tồn tại: Tạo dòng mới với ID, Name và điểm khởi tạo là 'score_to_add'.
        """
        user_id = str(user_id).strip()
        
        if not user_id:
            logger.warning("User ID không được để trống khi cập nhật điểm.")
            return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)
            
            score_col_name = Config.USER_COMMENT_HEADER_SCORE_WEEK
            id_col_name = Config.USER_COMMENT_HEADER_ID
            name_col_name = Config.USER_COMMENT_HEADER_NAME
            
            if score_col_name not in headers:
                logger.error(f"Không tìm thấy cột '{score_col_name}' trên Sheet.")
                return False
                
            score_col_idx = headers.index(score_col_name) + 1

            try:
                # TRƯỜNG HỢP 1: TÌM THẤY ID -> CỘNG THÊM ĐIỂM
                cell = worksheet.find(user_id)
                
                # Lấy giá trị điểm cũ hiện tại
                current_score_str = worksheet.cell(cell.row, score_col_idx).value
                
                try:
                    # Ép kiểu về số nguyên, nếu ô trống thì mặc định là 0
                    current_score = int(current_score_str) if current_score_str else 0
                except ValueError:
                    current_score = 0  # Xử lý ngoại lệ nếu cell chứa chữ bị lỗi
                
                new_score = current_score + score_to_add
                worksheet.update_cell(cell.row, score_col_idx, new_score)
                logger.info(f"Đã cộng điểm cho User ID '{user_id}': {current_score} -> {new_score}.")
                return True

            except gspread.exceptions.CellNotFound:
                # TRƯỜNG HỢP 2: KHÔNG TÌM THẤY ID -> TẠO MỚI (NEW USER)
                row_dict = {
                    id_col_name: user_id,
                    name_col_name: user_name,
                    score_col_name: score_to_add
                }
                
                # Map dữ liệu theo đúng thứ tự cột trên Google Sheet
                row_to_insert = [row_dict.get(header, "") for header in headers]
                worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
                
                logger.info(f"Đã tạo mới User ID '{user_id}' với điểm khởi tạo là {score_to_add}.")
                return True

        except Exception as e:
            logger.error(f"Lỗi khi cập nhật/thêm mới điểm thành viên: {e}", exc_info=True)
            return False

    # ===================================================
    # 3. RESET (Đưa toàn bộ cột điểm về 0 sau khi lưu lịch sử)
    # ===================================================
    def reset_all_scores_to_zero(self, spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Giữ nguyên ID và Name, chỉ reset toàn bộ giá trị trong cột 'score/week' về 0.
        Sử dụng update_cells để tối ưu API (chỉ gọi 1 lần).
        """
        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            
            # Lấy header để tìm đúng cột chứa điểm
            headers = worksheet.row_values(1)
            score_col_name = Config.USER_COMMENT_HEADER_SCORE_WEEK
            
            if score_col_name not in headers:
                logger.error(f"Không tìm thấy cột '{score_col_name}' để reset.")
                return False
                
            col_idx = headers.index(score_col_name) + 1
            
            # Đếm số lượng dòng hiện có dựa vào cột 1 (giả định cột 1 luôn chứa ID)
            # Dùng len(col_values) thay vì worksheet.row_count để tránh quét các dòng trắng dư thừa ở cuối sheet
            num_rows = len(worksheet.col_values(1))
            
            if num_rows > 1:
                # Chọn vùng dữ liệu từ dòng 2 đến dòng cuối cùng của cột điểm
                cell_list = worksheet.range(2, col_idx, num_rows, col_idx)
                
                # Cập nhật giá trị nội bộ trong Python
                for cell in cell_list:
                    cell.value = 0
                    
                # Gửi lệnh update hàng loạt lên Google Sheet (1 request duy nhất)
                worksheet.update_cells(cell_list)
                
                logger.info(f"Đã reset thành công cột '{score_col_name}' về 0 cho {num_rows - 1} user.")
                return True
            else:
                logger.info("Sheet chưa có user nào để reset điểm.")
                return True
                
        except Exception as e:
            logger.error(f"Lỗi khi thực hiện reset điểm về 0: {e}", exc_info=True)
            return False
        
    def bulk_update_scores(self, users_data: List[Dict], spreadsheet_id: str = Config.SPREADSHEET_ID) -> bool:
        """
        Xử lý mảng dữ liệu user: Cập nhật người cũ bằng update_cells (1 request) 
        và thêm mới người chưa tồn tại bằng append_rows (1 request).
        """
        if not users_data: return False

        try:
            worksheet = self._get_worksheet(spreadsheet_id)
            headers = worksheet.row_values(1)
            
            id_col_name = Config.USER_COMMENT_HEADER_ID
            name_col_name = Config.USER_COMMENT_HEADER_NAME
            score_col_name = Config.USER_COMMENT_HEADER_SCORE_WEEK

            if score_col_name not in headers or id_col_name not in headers:
                logger.error("Thiếu cột ID hoặc Score trên sheet.")
                return False

            id_col_idx = headers.index(id_col_name) + 1
            score_col_idx = headers.index(score_col_name) + 1

            # Lấy toàn bộ ID hiện có trên sheet (tránh fetch toàn bộ data cho nhẹ)
            existing_ids_list = worksheet.col_values(id_col_idx)
            
            cells_to_update = []
            rows_to_insert = []
            
            # Gộp điểm nếu users_data có các id trùng nhau (cộng dồn nội bộ trước)
            merged_users = {}
            for u in users_data:
                uid = str(u.get("id", "")).strip()
                if not uid: continue
                if uid in merged_users:
                    merged_users[uid]["score_to_add"] += int(u.get("score_to_add", 1))
                else:
                    merged_users[uid] = {
                        "name": str(u.get("name", "")),
                        "score_to_add": int(u.get("score_to_add", 1))
                    }

            # Lấy toàn bộ giá trị điểm hiện tại trên sheet để xử lý cộng dồn
            existing_scores_list = worksheet.col_values(score_col_idx)

            for uid, data in merged_users.items():
                if uid in existing_ids_list:
                    # User đã có -> Chuẩn bị cập nhật (row_index = index + 1, do list bắt đầu từ 0)
                    row_idx = existing_ids_list.index(uid) + 1
                    
                    # Lấy điểm cũ
                    try:
                        old_score = int(existing_scores_List[row_idx - 1]) if row_idx - 1 < len(existing_scores_list) and existing_scores_List[row_idx - 1] else 0
                    except ValueError:
                        old_score = 0
                        
                    new_score = old_score + data["score_to_add"]
                    
                    # Tạo đối tượng Cell của gspread để chuẩn bị bulk update
                    cell = gspread.Cell(row=row_idx, col=score_col_idx, value=new_score)
                    cells_to_update.append(cell)
                else:
                    # User mới -> Chuẩn bị thêm dòng
                    row_dict = {
                        id_col_name: uid,
                        name_col_name: data["name"],
                        score_col_name: data["score_to_add"]
                    }
                    rows_to_insert.append([row_dict.get(h, "") for h in headers])

            # Thực thi API
            if cells_to_update:
                worksheet.update_cells(cells_to_update)
                logger.info(f"Đã cập nhật điểm hàng loạt cho {len(cells_to_update)} user cũ.")
            
            if rows_to_insert:
                worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                logger.info(f"Đã thêm mới {len(rows_to_insert)} user vào sheet.")

            return True

        except Exception as e:
            logger.error(f"Lỗi khi bulk update điểm: {e}", exc_info=True)
            return False