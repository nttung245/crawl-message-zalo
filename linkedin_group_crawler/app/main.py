"""FastAPI application entrypoint."""

from __future__ import annotations

from typing import List, Optional
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from functools import partial

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if not hasattr(asyncio, "to_thread"):
    async def _asyncio_to_thread(func, /, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    asyncio.to_thread = _asyncio_to_thread

from fastapi import Depends, FastAPI, HTTPException
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
from app.modules.zalo.api.routes.listener import router as zalo_listener_router
from app.modules.zalo.api.routes.accounts import router as zalo_accounts_router
from app.modules.zalo.api.routes.conversations import router as zalo_conversations_router
from app.modules.zalo.api.proxy import legacy_groups_router as zalo_proxy_legacy_groups_router
from app.modules.zalo.api.proxy import router as zalo_proxy_router
from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.config import settings as zalo_settings
from app.modules.apartment_agent.router import router as apartment_agent_router
from app.modules.zalo.api.routes.villa_sync import router as villa_sync_router
from app.modules.zalo.services.worker_pool import is_zalo_browser_proxy_configured
from app.modules.zalo.services.session_store import (
    start_cleanup_scheduler,
    initialize_session_store,
    shutdown_session_store,
)
from app.modules.zalo.services.asset_cleanup_scheduler import start_asset_cleanup_scheduler
from app.modules.zalo.services.zca_persistent_listener import (
    shutdown_persistent_listeners,
    start_persisted_listeners,
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


def _cors_origins() -> List[str]:
    origins: List[str] = []

    def add(value: Optional[str]) -> None:
        if not value:
            return
        for item in value.split(","):
            origin = item.strip().rstrip("/")
            if origin and origin not in origins:
                origins.append(origin)

    for origin in settings.cors_origins or []:
        add(origin)
    add(zalo_settings.cors_origins)
    add(os.getenv("CORS_ORIGINS"))
    add(os.getenv("ZALO_CORS_ORIGINS"))

    for origin in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3111",
        "http://127.0.0.1:3111",
        "http://10.30.50.29:3111",
        "http://10.30.50.29:8111",
    ):
        add(origin)
    return origins or ["*"]


async def _run_blocking(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)


@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_task: Optional[asyncio.Task] = None
    cleanup_task: Optional[asyncio.Task] = None
    asset_cleanup_task: Optional[asyncio.Task] = None

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
            await _run_blocking(warmup_playwright_pool)
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
    asset_cleanup_task = asyncio.create_task(start_asset_cleanup_scheduler())
    try:
        await start_persisted_listeners()
    except Exception as exc:
        logger.warning(f"Could not start persisted ZCA listeners: {exc}")

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
        if asset_cleanup_task is not None and not asset_cleanup_task.done():
            asset_cleanup_task.cancel()
            try:
                await asset_cleanup_task
            except asyncio.CancelledError:
                pass
        await shutdown_persistent_listeners()
        await _run_blocking(shutdown_playwright_pool)
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
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
@app.get("/health", response_model=BaseResponse)
def root_health() -> BaseResponse:
    """Root health check for DevOps/Docker infrastructure."""
    return BaseResponse(success=True, message="Service is healthy")



@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors in the app's common response envelope."""

    error_messages: List[str] = []
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


@app.exception_handler(Exception)
async def generic_exception_handler(_, exc: Exception) -> JSONResponse:
    """Catch-all exception handler — return JSON instead of plain text 500."""
    from uuid import uuid4
    from loguru import logger as _logger

    request_id = str(uuid4())
    _logger.exception("[request_id={}] Unhandled exception: {}", request_id, exc)

    # If the exception detail is already an ApartmentAgentError envelope, pass it through
    try:
        from app.modules.apartment_agent.schemas import ApartmentAgentError
        if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) and exc.detail.get("kind") in ("missing_config", "llm_auth", "llm_schema", "llm_rate_limit", "godanang_rest", "validation"):
            return JSONResponse(
                status_code=exc.status_code,
                content={"success": False, "error": exc.detail},
            )
    except ImportError:
        pass

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Internal Server Error: {type(exc).__name__}: {exc}",
            "data": None,
            "request_id": request_id,
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
    app.include_router(zalo_listener_router)
    app.include_router(zalo_accounts_router)
    app.include_router(zalo_conversations_router)

    @app.get("/api/zalo/workers", dependencies=[Depends(verify_zalo_api_key)])
    async def list_direct_zalo_workers() -> dict:
        return {
            "workers": [
                {
                    "id": "default",
                    "label": "Default",
                    "status": "online",
                    "is_default": True,
                    "queue_state": "local",
                },
            ],
            "selected_worker_id": "default",
            "routing_mode": "direct",
        }
# FIX C-5: Chỉ đăng ký Facebook router nếu module import thành công
if _FACEBOOK_ENABLED and _fb_api_router is not None:
    app.include_router(_fb_api_router, prefix="/facebook/api/v1")

# Apartment Agent — LLM-based apartment extraction pipeline
app.include_router(apartment_agent_router)
try:
    _aa_routes = ", ".join(
        f"{','.join(sorted(r.methods or {}))} {r.path}"
        for r in apartment_agent_router.routes
        if hasattr(r, "methods")
    )
except Exception:  # pragma: no cover — defensive
    _aa_routes = "<introspection failed>"
logger.info(f"Apartment-agent routes mounted: {_aa_routes}")

# Villa Sync — sync Zalo crawl data to GoDaNang villas table
app.include_router(villa_sync_router)
try:
    _vs_routes = ", ".join(
        f"{','.join(sorted(r.methods or {}))} {r.path}"
        for r in villa_sync_router.routes
        if hasattr(r, "methods")
    )
except Exception:  # pragma: no cover — defensive
    _vs_routes = "<introspection failed>"
logger.info(f"Villa-sync routes mounted: {_vs_routes}")
