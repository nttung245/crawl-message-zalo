from typing import Any, Dict, Optional
import json
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import Page

from app.modules.zalo.config import settings


def _artifact_dir() -> Path:
    path = Path(settings.debug_artifacts_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _artifact_base(name: str) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return _artifact_dir() / f"{timestamp}-{name}"


async def save_page_artifacts(page: Page, name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    base = _artifact_base(name)
    html_path = base.with_suffix(".html")
    png_path = base.with_suffix(".png")
    json_path = base.with_suffix(".json")

    try:
        html_path.write_text(await page.content(), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Could not save page HTML to {html_path}: {exc}")

    try:
        await page.screenshot(path=str(png_path), full_page=True)
    except Exception as exc:
        logger.warning(f"Could not save screenshot to {png_path}: {exc}")

    if metadata is not None:
        try:
            json_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Could not save metadata to {json_path}: {exc}")

    return {
        "html": str(html_path.resolve()),
        "screenshot": str(png_path.resolve()),
        "metadata": str(json_path.resolve()),
    }

