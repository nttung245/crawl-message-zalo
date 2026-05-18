"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import linkedin_app_router, router
from app.config import settings
from app.services.playwright_browser_pool import (
    shutdown_playwright_pool,
    warmup_playwright_pool,
)
from app.utils.file_utils import ensure_directory
from app.utils.logger import get_logger, setup_logging


setup_logging()
logger = get_logger(__name__)

ensure_directory(settings.raw_data_dir)
ensure_directory(settings.output_data_dir)
ensure_directory(settings.state_path.parent)
ensure_directory(settings.session_storage_dir)


@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_task: asyncio.Task[None] | None = None

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

    try:
        yield
    finally:
        if warmup_task is not None and not warmup_task.done():
            warmup_task.cancel()
            try:
                await warmup_task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(shutdown_playwright_pool)


app = FastAPI(
    title="LinkedIn Group Crawler API",
    version="1.0.0",
    description="FastAPI service to login, crawl LinkedIn groups, and expose top daily posts for n8n.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
