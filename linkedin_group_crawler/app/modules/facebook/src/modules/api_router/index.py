"""
src/api/routes/api_router.py
Nơi gom nhóm tất cả các endpoint của ứng dụng.
"""

from fastapi import APIRouter

# Import các file route con
from src.modules.crawl_fb.router.index import crawl_fb_router
from src.modules.crawl_fb.router.sheet_management import sheet_management_router
# Ví dụ khi dự án mở rộng, bạn sẽ import thêm:
# from src.api.routes import user_route
# from src.api.routes import auth_route

# Khởi tạo một Router tổng
api_router = APIRouter()

# ── ĐĂNG KÝ CÁC ROUTE CON VÀO ROUTER TỔNG ─────────────────────────────────────

# Gắn route của tính năng Crawler
# Lưu ý: Việc đặt prefix="/crawl" và tags ở đây hoặc bên trong file crawl_route đều được, 
# nhưng đặt ở file crawl_route (như hướng dẫn trước) sẽ giúp file này ngắn gọn hơn.
api_router.include_router(crawl_fb_router)
api_router.include_router(sheet_management_router)
# Ví dụ cho tương lai:
# api_router.include_router(user_route.router)
# api_router.include_router(auth_route.router)