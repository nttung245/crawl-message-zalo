import asyncio
from typing import List

import gspread
from fastapi import APIRouter, Header, HTTPException
from loguru import logger

from app.modules.zalo.config import settings
from app.modules.zalo.crawler.group_parser import collect_group_debug_info, parse_groups, wait_for_group_list_ready
from app.modules.zalo.crawler.qr_login import check_login_status
from app.modules.zalo.schemas.group import Group
from app.modules.zalo.services.debug_artifacts import save_page_artifacts
from app.modules.zalo.services.gsheet_service import list_crawled_groups
from app.modules.zalo.services.session_store import get_latest_session_for_user, get_session, save_session

router = APIRouter(prefix="/api/groups", tags=["groups"])
zalo_groups_router = APIRouter(prefix="/api/zalo/groups", tags=["zalo-groups"])


@router.get("", response_model=List[Group])
async def list_groups(
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = (x_user_id or "default").strip() or "default"
    session = get_session(x_session_id) if x_session_id else None
    if not session:
        session = get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed session found, please login first")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    live_status = await check_login_status(session.page)
    session.status = live_status
    save_session(session)
    if live_status != "confirmed":
        raise HTTPException(
            status_code=403,
            detail=f"Login not completed yet (status={live_status})",
        )

    try:
        selector_counts = await wait_for_group_list_ready(session.page)
        groups = await parse_groups(session.page)
        if not groups:
            debug_info = await collect_group_debug_info(session.page)
            debug_info["session_id"] = session.session_id
            debug_info["wait_selector_counts"] = selector_counts

            artifacts = await save_page_artifacts(
                session.page,
                f"groups-{session.session_id}",
                metadata=debug_info,
            )

            logger.error(
                "Group list is empty for session {}. url={} title={} artifacts={}",
                session.session_id,
                debug_info["url"],
                debug_info["title"],
                artifacts,
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Khong tim thay danh sach group tren giao dien Zalo sau khi dang nhap",
                    "url": debug_info["url"],
                    "title": debug_info["title"],
                    "selector_counts": debug_info["selector_counts"],
                    "artifacts": artifacts,
                },
            )
        return groups
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse groups for session {session.session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch groups: {e}")


@zalo_groups_router.get("/crawled")
async def list_crawled_groups_from_sheet():
    sheet_id = settings.default_sheet_id.strip()
    if not sheet_id:
        raise HTTPException(
            status_code=500,
            detail="ZALO_DEFAULT_SHEET_ID is missing in backend env",
        )

    loop = asyncio.get_event_loop()
    try:
        groups = await loop.run_in_executor(
            None,
            lambda: list_crawled_groups(
                credentials_path=settings.google_credentials_path,
                sheet_id=sheet_id,
            ),
        )
        return {
            "sheet_id": sheet_id,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}",
            "total_groups": len(groups),
            "groups": groups,
        }
    except gspread.exceptions.SpreadsheetNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Google Sheet {sheet_id} not found or service account has no access. "
                "Hay share file Google Sheet cho service account."
            ),
        )
    except Exception as e:
        logger.error(f"Failed to list crawled groups from sheet {sheet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list crawled groups: {e}")
