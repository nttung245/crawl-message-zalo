import os
import gspread
from google.oauth2.service_account import Credentials
from app.modules.facebook.src.core.config.env import Config
from app.modules.facebook.src.core.utils.logger import setup_logger

logger = setup_logger(__name__)

class GoogleSheetAccountService:
    def __init__(self, credentials_path: str=Config.GOOGLE_CREDENTIALS_PATH):
        """
        Khởi tạo kết nối tới Google Sheet chứa thông tin tài khoản.
        """
        self.spreadsheet_id =  Config.SPREADSHEET_ID
        
        # 🟢 Lấy tên tab (trang tính) trực tiếp từ cấu hình .env
        self.sheet_name = Config.GOOGLE_SHEET_NAME_DEFAULT
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        try:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"Không tìm thấy file credentials tại: {credentials_path}")
                
            credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
            self.client = gspread.authorize(credentials)
            self.sheet = self.client.open_by_key(self.spreadsheet_id)
            
            # 🟢 Trỏ chính xác vào tab có tên là "Account Default"
            self.worksheet = self.sheet.worksheet(self.sheet_name)
            
            #logger.info(f"✅ Kết nối thành công tới tab tài khoản: {self.sheet_name}")
            
        except gspread.exceptions.WorksheetNotFound:
            #logger.error(f"❌ Không tìm thấy trang tính nào có tên '{self.sheet_name}' trong file Google Sheet.")
            raise
        except Exception as e:
            #logger.error(f"❌ Lỗi khởi tạo GoogleSheetAccountService: {e}")
            raise e

    def get_default_account(self) -> dict:
        """
        Đọc dữ liệu tài khoản từ trang tính.
        Hàm này dùng get_all_records() -> tự động lấy dòng 1 làm Tiêu đề cột (Key), các dòng sau làm Value.
        """
        try:
            records = self.worksheet.get_all_records()
            
            if not records:
                #logger.warning(f"⚠️ Trang tính '{self.sheet_name}' đang trống.")
                return None
                
            # Lấy tài khoản đầu tiên ở dòng số 2 (vì dòng 1 là tiêu đề)
            first_account = records[0]
            
            # Lấy value bằng key linh hoạt (đề phòng bạn gõ hoa/thường trên Sheet)
            email = first_account.get(Config.GOOGLE_SHEET_EMAIL_DEFAULT) or first_account.get(Config.GOOGLE_SHEET_EMAIL_DEFAULT.lower()) or first_account.get("Email")
            password = first_account.get(Config.GOOGLE_SHEET_PASSWORD_DEFAULT) or first_account.get(Config.GOOGLE_SHEET_PASSWORD_DEFAULT.lower()) or first_account.get("Password")
            two_fa = first_account.get(Config.GOOGLE_SHEET_2FA_DEFAULT) or first_account.get(Config.GOOGLE_SHEET_2FA_DEFAULT.lower()) or first_account.get("2FA")
            
            if not email or not password:
                #logger.error(f"❌ Không tìm thấy cột 'Email' hoặc 'Password' trong tab {self.sheet_name}.")
                return None
                
            #logger.info(f"🔑 Đã load thành công tài khoản: {email} từ Sheet.")
            
            return {
                "email": email,
                "password": password,
                "2fa": two_fa # Tích hợp lấy luôn mã 2FA nếu bạn có cột này
            }

        except Exception as e:
            #logger.error(f"❌ Lỗi khi đọc dữ liệu tài khoản từ Google Sheet: {e}")
            return None