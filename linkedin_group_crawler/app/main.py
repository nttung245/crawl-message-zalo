"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.modules.linkedin.router import linkedin_app_router, router
from app.modules.linkedin.schemas.response_models import BaseResponse
from app.core.config import settings
from app.modules.zalo.api.routes.auth import router as zalo_auth_router
from app.modules.zalo.api.routes.crawler import router as zalo_crawl_router
from app.modules.zalo.api.routes.groups import router as zalo_groups_router
from app.modules.zalo.api.routes.groups import zalo_groups_router as zalo_groups_sheet_router
from app.modules.zalo.api.routes.jobs import router as zalo_jobs_router
from app.modules.zalo.api.routes.library import router as zalo_library_router
from app.modules.zalo.api.routes.broadcasts import router as zalo_broadcasts_router
from app.modules.zalo.api.routes.maintenance import router as zalo_maintenance_router
from app.modules.zalo.api.proxy import legacy_groups_router as zalo_proxy_legacy_groups_router
from app.modules.zalo.api.proxy import router as zalo_proxy_router
from app.modules.zalo.config import settings as zalo_settings
from app.modules.apartment_agent.router import router as apartment_agent_router
from app.modules.zalo.services.worker_pool import is_zalo_browser_proxy_configured
from app.modules.zalo.services.session_store import (
    start_cleanup_scheduler,
    initialize_session_store,
    shutdown_session_store,
)
from app.core.playwright_browser_pool import (
    shutdown_playwright_pool,
    warmup_playwright_pool,
)
from app.core.utils.file_utils import ensure_directory
from app.core.logger import get_logger, setup_logging

# FIX C-5: Guard Facebook module import — nếu FB module lỗi không crash toàn server
try:
    from app.modules.facebook.src.jobs.daily_crawl_job import setup_and_start_jobs as _fb_setup
    from app.modules.facebook.src.modules.api_router.index import api_router as _fb_api_router
    _FACEBOOK_ENABLED = True
except Exception as _fb_import_err:
    logger_temp = get_logger(__name__) if False else None  # defer
    _FACEBOOK_ENABLED = False
    _fb_api_router = None
    def _fb_setup(): pass  # noqa


setup_logging()
logger = get_logger(__name__)

ensure_directory(settings.raw_data_dir)
ensure_directory(settings.output_data_dir)
ensure_directory(settings.state_path.parent)
ensure_directory(settings.session_storage_dir)


@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_task: asyncio.Task[None] | None = None
    cleanup_task: asyncio.Task[None] | None = None

    # Initialize session store (memory or Redis based on config)
    try:
        await initialize_session_store()
    except Exception as exc:
        logger.error(f"Failed to initialize session store: {exc}")
        raise

    # Facebook module (optional, guarded import)
    try:
        _fb_setup()
        if not _FACEBOOK_ENABLED:
            logger.warning("Facebook module is disabled (import failed at startup)")
    except Exception as exc:
        logger.warning(f"Facebook setup_and_start_jobs failed: {exc}")

    async def _warmup_background() -> None:
        try:
            await asyncio.to_thread(warmup_playwright_pool)
            logger.info("Playwright pool warmup finished")
        except Exception:
            logger.exception(
                "Playwright warmup failed — /health vẫn OK; sẽ thử lại khi có request",
            )

    if settings.playwright_warmup_on_startup:
        warmup_task = asyncio.create_task(_warmup_background())

    # FIX L-6: Khởi động cleanup scheduler định kỳ dọn Chromium processes rò rỉ
    cleanup_task = asyncio.create_task(
        start_cleanup_scheduler(ttl_hours=zalo_settings.session_ttl_hours)
    )

    try:
        yield
    finally:
        if warmup_task is not None and not warmup_task.done():
            warmup_task.cancel()
            try:
                await warmup_task
            except asyncio.CancelledError:
                pass
        if cleanup_task is not None and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(shutdown_playwright_pool)
        await shutdown_session_store()


app = FastAPI(
    title="LinkedIn Group Crawler API",
    version="1.0.0",
    description="FastAPI service to login, crawl LinkedIn groups, and expose top daily posts for n8n.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # FIX M-1: settings.cors_origins là string, CORSMiddleware cần List[str]
    # Trước đây truyền string thẳng vào → CORS so sánh với từng ký tự!
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/health", response_model=BaseResponse)
def root_health() -> BaseResponse:
    """Root health check for DevOps/Docker infrastructure."""
    return BaseResponse(success=True, message="Service is healthy")



@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors in the app's common response envelope."""

    error_messages: list[str] = []
    for item in exc.errors():
        location = " -> ".join(str(part) for part in item.get("loc", []))
        message = item.get("msg", "Invalid request")
        error_messages.append(f"{location}: {message}")

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Invalid request body",
            "data": {"errors": error_messages},
        },
    )


app.include_router(router)
app.include_router(linkedin_app_router)
if is_zalo_browser_proxy_configured():
    app.include_router(zalo_proxy_router)
    app.include_router(zalo_proxy_legacy_groups_router)
else:
    app.include_router(zalo_auth_router)
    app.include_router(zalo_crawl_router)
    app.include_router(zalo_groups_router)
    app.include_router(zalo_groups_sheet_router)
    app.include_router(zalo_jobs_router)
    app.include_router(zalo_library_router)
    app.include_router(zalo_broadcasts_router)
    app.include_router(zalo_maintenance_router)
# FIX C-5: Chỉ đăng ký Facebook router nếu module import thành công
if _FACEBOOK_ENABLED and _fb_api_router is not None:
    app.include_router(_fb_api_router, prefix="/facebook/api/v1")

# Apartment Agent — LLM-based apartment extraction pipeline
app.include_router(apartment_agent_router)
