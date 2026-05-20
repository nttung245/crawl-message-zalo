# src/modules/crawl/route/crawl_route.py
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, status, BackgroundTasks, WebSocket, WebSocketDisconnect
from typing import List, Optional, Dict
from pydantic import BaseModel
import uuid
# Imports từ project của bạn
from app.modules.facebook.src.modules.facebook.services.facebook_auth import FacebookAuth
from app.modules.facebook.src.modules.crawl_fb.schemas.crawl_schema import CrawlPayload
from app.modules.facebook.src.modules.crawl_fb.services.index import CrawlService
from app.modules.facebook.src.modules.facebook.services.facebook_scraper import FacebookScraper, cancel_registry
from app.modules.facebook.src.modules.telegram.services.telegram_service import TelegramService
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets import GoogleApiService
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_groups_service import GroupManagementSheetService
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_posts import GoogleSheetServicePosts
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_groups_24h import TargetGroupSheet24HService
from app.modules.facebook.src.modules.gg_sheet.services.google_sheets_intent_service import IntentSheetService
from app.modules.facebook.src.core.config.env import Config

from fastapi.encoders import jsonable_encoder
import traceback

crawl_fb_router = APIRouter(tags=["Crawler Management FB"])

# ── QUẢN LÝ THƯ MỤC OTP ────────────────────────────────

# Đảm bảo thư mục lưu cache OTP luôn tồn tại
OTP_DIRECTORY = Path("temp_otp")
OTP_DIRECTORY.mkdir(parents=True, exist_ok=True)

# ĐÃ GỠ BỎ TOÀN BỘ SEMAPHORE VÀ LOCK ĐỂ CHẠY SONG SONG KHÔNG GIỚI HẠN
# login_semaphore = asyncio.Semaphore(3)
# ws_crawl_lock = asyncio.Lock()

# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    email: str
    password: str
    secret_2fa: Optional[str] = None

class CheckPhonePayload(BaseModel):
    session_id: str

class SubmitOTPPayload(BaseModel):
    session_id: str
    otp_code: str
# ── WEBSOCKET MANAGER ─────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, email: str):
        await websocket.accept()
        self.active_connections[email] = websocket

    def disconnect(self, email: str):
        if email in self.active_connections:
            del self.active_connections[email]

    async def send_json(self, message: dict, email: str):
        if email in self.active_connections:
            try:
                safe_message = jsonable_encoder(message)
                await self.active_connections[email].send_json(safe_message)
            except Exception:
                traceback.print_exc()
                self.disconnect(email)

manager = ConnectionManager()

# ── ĐỊNH NGHĨA DEPENDENCY ─────────────────────────────────────────────────────

def get_crawl_service():
    """
    Hàm này chịu trách nhiệm khởi tạo class CrawlService.
    FastAPI sẽ tự động tạo một phiên bản Service mỗi khi có Request tới.
    """
    scraper = FacebookScraper(config=Config)
    telegram = TelegramService()
    group_sheet: GroupManagementSheetService = GroupManagementSheetService()
    post_sheet: GoogleSheetServicePosts = GoogleSheetServicePosts()
    group_24h_sheet: TargetGroupSheet24HService = TargetGroupSheet24HService()
    intent_sheet: IntentSheetService = IntentSheetService()

    return CrawlService(scraper=scraper, telegram=telegram, group_sheet=group_sheet, post_sheet=post_sheet, intent_sheet=intent_sheet, group_24h_sheet=group_24h_sheet)

# ── ROUTER CÀO DỮ LIỆU (CŨ) ───────────────────────────────────────────────────

# Route POST để kích hoạt cào dữ liệu ngầm
@crawl_fb_router.post("/CrawlDataGroupFB", status_code=status.HTTP_200_OK)
async def trigger_crawl_fb_api(
    payload: CrawlPayload, 
    background_tasks: BackgroundTasks,
    service: CrawlService = Depends(get_crawl_service)
):
    """
    API kích hoạt tiến trình cào dữ liệu Facebook thủ công chạy ngầm.
    """
    background_tasks.add_task(service.CrawlDataGroupFB, payload)
    
    return {
        "status": "success",
        "message": "Đã nhận lệnh! Bot đang tiến hành cào dữ liệu ngầm trên server."
    }

# ROUTER FE YÊU CẦU CÀO VÀ TRẢ DỮ LIỆU TRỰC TIẾP
@crawl_fb_router.post("/CrawlFbForFE", status_code=status.HTTP_200_OK)
async def fetch_data_direct_for_fe(
    payload: CrawlPayload, 
    service: CrawlService = Depends(get_crawl_service)
):
    """
    API dành cho Frontend: 
    Nhận tài khoản FB + danh sách group -> Cào dữ liệu -> Trả thẳng kết quả về cho FE.
    """
    return await service.FetchDataDirectly(payload)

@crawl_fb_router.get("/Posts", status_code=status.HTTP_200_OK)
async def get_all_facebook_posts(
    service: CrawlService = Depends(get_crawl_service)
):
    """
    API dành cho Frontend: 
    Lấy toàn bộ dữ liệu bài viết đã được cào và lưu trong Database.
    """
    posts = await service.get_all_posts_from_sheet()
    return posts

# ROUTER WEBSOCKET XẾP HÀNG YÊU CẦU CÀO DỮ LIỆU
@crawl_fb_router.websocket("/ws/CrawlFbForFE/{email}")
async def websocket_crawl_endpoint(
    websocket: WebSocket, email: str, service: CrawlService = Depends(get_crawl_service)
):
    """WebSocket API: Quản lý tiến trình cào dữ liệu ngầm dài hạn (hàng giờ).

    Hỗ trợ cơ chế Heartbeat chống Proxy Drop và bảo toàn tiến trình khi mất mạng.
    """
    await manager.connect(websocket, email)
    # Khởi tạo trạng thái cho chu kỳ cào mới
    cancel_registry[email] = False

    try:
        # 1. NHẬN & PARSE PAYLOAD (Chỉ thực thi 1 lần đầu tiên)
        data = await websocket.receive_text()
        payload_dict = json.loads(data)
        payload = CrawlPayload(**payload_dict)

        await manager.send_json(
            {
                "status": "processing",
                "message": f"Hệ thống đang tiến hành cào dữ liệu cho {email}...",
            },
            email,
        )

        # 2. ✅ CHUẨN SENIOR: TẠO BACKGROUND TASK ĐỘC LẬP
        # Đẩy luồng I/O nặng sang Async Task để giải phóng hoàn toàn Event Loop
        crawl_task = asyncio.create_task(
            service.FetchDataDirectly(payload, client_id=email)
        )

        # 3. ✅ VÒNG LẶP DUY TRÌ KẾT NỐI (POLLING & HEARTBEAT LOOP)
        elapsed_seconds = 0

        while not crawl_task.done():
            # A. KIỂM TRA LỆNH HỦY TỪ USER
            # Chỉ hủy khi cờ cancel_registry thực sự được Admin/User bật sang True
            if cancel_registry.get(email):
                crawl_task.cancel()  # Gửi tín hiệu ngắt ngay lập tức vào Task ngầm
                await manager.send_json(
                    {"status": "canceled", "message": "Đã hủy tiến trình cào dữ liệu."},
                    email,
                )
                await websocket.close()
                manager.disconnect(email)
                return

            # B. CƠ CHẾ HEARTBEAT (Bơm tín hiệu mỗi 30 giây)
            # Ngăn chặn các bộ định tuyến mạng (Nginx, Cloudflare) ngắt Socket do rỗi (Idle)
            if elapsed_seconds % 30 == 0 and elapsed_seconds > 0:
                try:
                    await manager.send_json(
                        {
                            "status": "heartbeat",
                            "message": f"Tiến trình vẫn đang thu thập dữ liệu ngầm... ({elapsed_seconds // 60} phút)",
                        },
                        email,
                    )
                except Exception:
                    # Rớt mạng Client -> Bỏ qua lỗi gửi tin để Task ngầm tiếp tục sống
                    pass

            # C. NHƯỜNG LUỒNG (1 giây) để hệ điều hành phản hồi các gói tin TCP/Ping ngầm
            await asyncio.sleep(1)
            elapsed_seconds += 1

        # 4. ✅ TRÍCH XUẤT KẾT QUẢ KHI TIẾN TRÌNH HOÀN TẤT
        try:
            raw_result = crawl_task.result()

            # Chuẩn hóa dữ liệu đầu ra
            actual_data_list = (
                raw_result["data"]
                if isinstance(raw_result, dict) and "data" in raw_result
                else raw_result
            )

            # --- NƠI ĐÂY LÀ LOGIC ĐƯA VÀO GOOGLE SHEET CỦA BẠN ---
            # ...

            # Gửi kết quả cuối cùng cho Client (Nếu họ vẫn còn đang mở kết nối)
            if not cancel_registry.get(email):
                standardized_response = {
                    "status": "success",
                    "message": "Cào dữ liệu thành công!",
                    "data": actual_data_list,
                }
                await manager.send_json(standardized_response, email)

        except asyncio.CancelledError:
            # Luồng Task bị ngắt do lệnh Cancel -> Thoát êm ái
            pass
        except Exception as task_error:
            # Bắt trọn vẹn lỗi từ Scraper (lỗi parse, rớt mạng HĐH ngầm...)
            if not cancel_registry.get(email):
                await manager.send_json(
                    {"status": "error", "message": f"Lỗi Scraper: {str(task_error)}"},
                    email,
                )

        # Chủ động đóng socket khi toàn bộ quy trình kết thúc trọn vẹn
        await websocket.close()
        manager.disconnect(email)

    except WebSocketDisconnect:
        # ✅ CHUẨN SENIOR: CHỈ NGẮT GIAO TIẾP, KHÔNG KILL TASK
        # User rớt mạng hoặc đóng Tab, ta giải phóng Socket nhưng tuyệt đối bảo lưu tiến trình ngầm
        print(f"\n[CLIENT NGẮT MẠNG / ĐÓNG TAB] - {email} (Tiến trình ngầm vẫn tiếp tục)")
        manager.disconnect(email)
        # BỎ HOÀN TOÀN dòng gán cancel_registry = True ở đây

    except Exception as general_error:
        print(f"\n[CRASH NGOẠI LỆ WEBSOCKET - {email}] Chi tiết: {general_error}")
        manager.disconnect(email)
        # Tránh văng lỗi HĐH, ngắt giao tiếp nội bộ
# ── WRAPPER KIỂM SOÁT LUỒNG ĐĂNG NHẬP ─────────────────────────────────────────

async def controlled_login_task(auth_service: FacebookAuth, email: str, password: str, secret_2fa: Optional[str], cache_file: Path):
    """
    Hàm gọi Playwright ngầm không bị giới hạn bởi Semaphore nữa.
    """
    # Khi tiến trình ngầm được chạy, cập nhật trạng thái file
    if cache_file.exists():
        try:
            status_data = {"status": "PROCESSING", "otp_code": None}
            cache_file.write_text(json.dumps(status_data), encoding="utf-8")
        except Exception:
            pass
    
    # Chạy tác vụ Playwright đồng bộ (sync) vào ThreadPool ngầm
    await asyncio.to_thread(
        auth_service.standalone_login,
        custom_email=email,
        custom_pass=password,
        custom_2fa=secret_2fa
    )

# ── ROUTER ĐĂNG NHẬP (STANDALONE LOGIN) ───────────────────────────────────────

async def controlled_login_task(auth_service: FacebookAuth, email: str, password: str, session_id: str, secret_2fa: Optional[str]):
    """Tiến trình ngầm bọc Playwright."""
    await asyncio.to_thread(
        auth_service.standalone_login,
        custom_email=email,
        custom_pass=password,
        session_id=session_id,
        custom_2fa=secret_2fa
    )

@crawl_fb_router.post("/auth/login", status_code=status.HTTP_200_OK)
async def standalone_login_api(payload: LoginPayload):
    """
    BƯỚC 1: Khởi tạo phiên login ngầm. Tăng thời gian chờ ban đầu và sửa lại trạng thái mặc định.
    """
    auth_service = FacebookAuth(config=Config)
    
    if auth_service.get_cookie_path(payload.email).exists():
        return {"status": "success", "message": "Đăng nhập thành công (Đã có cookie)!"}

    session_id = uuid.uuid4().hex
    otp_cache_file = OTP_DIRECTORY / f"session_{session_id}.json"
    
    status_data = {"status": "INIT", "message": "Khởi tạo trình duyệt ngầm...", "otp_code": None}
    otp_cache_file.write_text(json.dumps(status_data), encoding="utf-8")

    asyncio.create_task(
        controlled_login_task(
            auth_service=auth_service,
            email=payload.email,
            password=payload.password,
            session_id=session_id,
            secret_2fa=payload.secret_2fa
        )
    )

    # TĂNG THỜI GIAN CHỜ BAN ĐẦU LÊN 20 GIÂY để Playwright có đủ thời gian gõ và nhận diện lỗi sai pass
    for _ in range(20):
        await asyncio.sleep(1)
        if otp_cache_file.exists():
            try:
                current = json.loads(otp_cache_file.read_text(encoding="utf-8"))
                st = current.get("status")
                
                if st == "SUCCESS":
                    return {"status": "success", "message": "Đăng nhập thành công!"}
                elif st == "ERROR_WRONG_PASS":
                    # Trả về lỗi Out ngay lập tức
                    return {"status": "error", "message": current.get("message", "Sai email hoặc mật khẩu.")}
                elif st == "ERROR_BOT_BLOCKED":
                    return {"status": "error_bot_blocked", "message": current.get("message", "Bị chặn bởi Bot/CAPTCHA.")}
                elif st == "WAITING_FOR_PHONE_APPROVAL":
                    return {
                        "status": "need_phone_approval", 
                        "session_id": session_id,
                        "message": "Bị chặn xác nhận thiết bị. Vui lòng mở điện thoại phê duyệt."
                    }
                elif st == "WAITING_FOR_OTP":
                    return {
                        "status": "need_otp", 
                        "session_id": session_id,
                        "message": "Yêu cầu nhập mã OTP."
                    }
            except Exception:
                pass

    # SỬA LỖI 2 TẠI ĐÂY: Nếu quá 20s mà mạng chậm Playwright chưa load xong, 
    # TRẢ VỀ TRẠNG THÁI "PROCESSING" (Không báo nhầm là đợi điện thoại nữa)
    return {
        "status": "processing", 
        "session_id": session_id, 
        "message": "Hệ thống đang xử lý đăng nhập, vui lòng đợi thêm giây lát..."
    }

@crawl_fb_router.post("/auth/check-phone-approval", status_code=status.HTTP_200_OK)
async def check_phone_approval_api(payload: CheckPhonePayload):
    """
    BƯỚC 2: API này giờ đây đóng vai trò là "Polling endpoint" dùng chung.
    Nó vừa dùng để chờ khách bấm điện thoại (60s), vừa dùng để theo dõi tiếp 
    nếu Bước 1 bị delay trả về trạng thái "processing".
    """
    otp_cache_file = OTP_DIRECTORY / f"session_{payload.session_id}.json"
    
    if not otp_cache_file.exists():
        return {"status": "error", "message": "Phiên làm việc ngầm đã kết thúc hoặc không tồn tại."}

    # Theo dõi tiến trình ngầm tối đa 60 giây
    for _ in range(60):
        await asyncio.sleep(1)
        if not otp_cache_file.exists():
            return {"status": "success", "message": "Xử lý hoàn tất."}

        try:
            current = json.loads(otp_cache_file.read_text(encoding="utf-8"))
            st = current.get("status")

            if st == "SUCCESS":
                return {"status": "success", "message": "Đăng nhập thành công!"}
            elif st == "ERROR_WRONG_PASS":
                # Bắt bồi thêm lỗi sai pass nếu trước đó bị delay
                return {"status": "error", "message": current.get("message", "Sai email hoặc mật khẩu.")}
            elif st == "ERROR_BOT_BLOCKED":
                return {"status": "error_bot_blocked", "message": current.get("message", "Bị chặn bởi Bot/CAPTCHA.")}
            elif st == "WAITING_FOR_PHONE_APPROVAL":
                # Nếu tiến trình ngầm mới chuyển sang đợi điện thoại, tiếp tục giữ vòng lặp không làm gì cả
                pass
            elif st == "WAITING_FOR_OTP":
                return {
                    "status": "need_otp", 
                    "session_id": payload.session_id,
                    "message": "Yêu cầu nhập mã OTP."
                }
            elif st == "ERROR":
                return {"status": "error", "message": current.get("message", "Đăng nhập thất bại.")}
        except Exception:
            pass

    return {"status": "error", "message": "Hết thời gian chờ phản hồi từ Facebook."}
@crawl_fb_router.post("/auth/submit-otp", status_code=status.HTTP_200_OK)
async def submit_auth_otp_api(payload: SubmitOTPPayload):
    """
    BƯỚC 3: Nạp mã OTP vào phiên ngầm đang đứng đợi.
    """
    otp_cache_file = OTP_DIRECTORY / f"session_{payload.session_id}.json"
    
    if not otp_cache_file.exists():
        return {"status": "error", "message": "Phiên nhập OTP đã hết hạn (Quá thời gian chờ)."}
    
    try:
        # Ghi mã OTP vào file, đổi state thành RECEIVED_OTP để Playwright ngầm nhận diện
        current = json.loads(otp_cache_file.read_text(encoding="utf-8"))
        current["status"] = "RECEIVED_OTP"
        current["otp_code"] = payload.otp_code
        otp_cache_file.write_text(json.dumps(current), encoding="utf-8")

        # Đứng giữ HTTP tối đa 15 giây để chờ Playwright gõ mã và chốt thành công
        for _ in range(15):
            await asyncio.sleep(1)
            if not otp_cache_file.exists():
                return {"status": "success", "message": "Xác thực thành công!"}
            
            try:
                check = json.loads(otp_cache_file.read_text(encoding="utf-8"))
                if check.get("status") == "SUCCESS":
                    return {"status": "success", "message": "Xác thực OTP thành công!"}
                elif check.get("status") in ["ERROR", "ERROR_WRONG_PASS"]:
                    return {"status": "error", "message": check.get("message", "Mã OTP sai hoặc hết hạn.")}
            except Exception:
                pass

        return {"status": "success", "message": "Đã nạp mã OTP, hệ thống đang hoàn tất..."}

    except Exception as e:
        return {"status": "error", "message": f"Lỗi xử lý nạp OTP: {str(e)}"}




