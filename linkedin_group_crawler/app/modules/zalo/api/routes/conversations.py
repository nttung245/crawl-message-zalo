import asyncio
import os
import tempfile
import shutil
from typing import List, Optional
import re
from loguru import logger

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.schemas.library import (
    ZaloConversationListResponse,
    ZaloConversationSummary,
    ZaloLibraryListResponse,
    ZaloLibraryMessage,
)
from app.modules.zalo.services.supabase_service import (
    SupabaseNotConfigured,
    list_conversation_messages,
    list_conversations,
    save_listener_messages,
    save_global_listener_messages,
    upsert_groups,
    mark_conversation_as_read,
)
from app.modules.zalo.services.zca_auth_store import load_zca_auth
from app.modules.zalo.services.zca_api_bridge import (
    ZcaAuthExpiredError,
    get_zca_group_history,
    list_zca_groups,
    list_zca_friends,
    send_zca_message,
    send_zca_images,
    sync_zca_group_old_messages,
    remove_zca_unread_mark,
)

router = APIRouter(
    prefix="/api/zalo/conversations",
    tags=["zalo-conversations"],
    dependencies=[Depends(verify_zalo_api_key)],
)

# Thông báo chuẩn khi phiên Zalo hết hạn — FE dựa vào status 401 + code này để hiện CTA login lại.
ZCA_SESSION_EXPIRED_DETAIL = {
    "code": "zca_session_expired",
    "message": "Phiên đăng nhập Zalo đã hết hạn. Vui lòng đăng nhập lại bằng mã QR.",
}


def _normalize_user_id(value: Optional[str]) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


class SyncRecentRequest(BaseModel):
    account_id: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)
    messages_per_conversation: int = Field(default=50, ge=1, le=200)


class SyncRecentGroupResult(BaseModel):
    group_id: str
    group_name: str
    messages_saved: int = 0
    status: str
    error: Optional[str] = None


class SyncRecentResponse(BaseModel):
    account_id: str
    scanned: int = 0
    groups_with_messages: int = 0
    messages_saved: int = 0
    errors: int = 0
    results: List[SyncRecentGroupResult] = Field(default_factory=list)


@router.get("", response_model=ZaloConversationListResponse)
async def get_conversations(
    account_id: Optional[str] = Query(None),
    x_user_id: str = Header("default", alias="X-User-ID"),
    limit: int = Query(500, ge=1, le=2000),
):
    user_id = _normalize_user_id(account_id or x_user_id)
    try:
        rows = await list_conversations(user_id, limit=limit)
        return {
            "account_id": user_id,
            "conversations": [ZaloConversationSummary(**row) for row in rows],
            "total": len(rows),
        }
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể tải danh sách hội thoại Zalo: {exc}")


@router.post("/sync-recent", response_model=SyncRecentResponse)
async def sync_recent_conversations(
    body: SyncRecentRequest,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = _normalize_user_id(body.account_id or x_user_id)
    auth = await load_zca_auth(user_id)
    if not auth:
        raise HTTPException(status_code=401, detail="No persisted ZCA auth found for this account")

    try:
        # 1. Fetch all groups and friends and upsert them to zalo_groups
        groups = await list_zca_groups(auth)
        friends = await list_zca_friends(auth)
        all_chats = groups + friends
        await upsert_groups(user_id, [chat.model_dump() for chat in all_chats])
    except ZcaAuthExpiredError:
        raise HTTPException(status_code=401, detail=ZCA_SESSION_EXPIRED_DETAIL)
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể tải danh sách hội thoại Zalo: {exc}")

    results: List[SyncRecentGroupResult] = []
    total_saved = 0
    groups_with_messages = 0
    errors = 0

    # Lấy lịch sử từng group bằng getGroupChatHistory (đáng tin hơn listener.requestOldMessages
    # vốn hay trả rỗng). Concurrency thấp (4) để tránh rate-limit của Zalo.
    per_group_count = max(20, min(body.messages_per_conversation, 200))
    semaphore = asyncio.Semaphore(4)

    async def _sync_one_group(group) -> SyncRecentGroupResult:
        async with semaphore:
            try:
                messages = await get_zca_group_history(
                    auth,
                    group.group_id,
                    count=per_group_count,
                )
                if not messages:
                    return SyncRecentGroupResult(
                        group_id=group.group_id,
                        group_name=group.name,
                        messages_saved=0,
                        status="empty",
                    )
                saved = await save_listener_messages(
                    user_id,
                    group.group_id,
                    group.name,
                    messages,
                    increment_unread=False,
                )
                return SyncRecentGroupResult(
                    group_id=group.group_id,
                    group_name=group.name,
                    messages_saved=saved,
                    status="has_messages" if saved else "empty",
                )
            except Exception as exc:
                logger.warning(f"sync-recent failed for group={group.group_id}: {exc}")
                return SyncRecentGroupResult(
                    group_id=group.group_id,
                    group_name=group.name,
                    messages_saved=0,
                    status="error",
                    error=str(exc),
                )

    results = await asyncio.gather(*[_sync_one_group(group) for group in groups])

    for item in results:
        total_saved += item.messages_saved
        if item.messages_saved > 0:
            groups_with_messages += 1
        if item.status == "error":
            errors += 1

    return SyncRecentResponse(
        account_id=user_id,
        scanned=len(groups),
        groups_with_messages=groups_with_messages,
        messages_saved=total_saved,
        errors=errors,
        results=list(results),
    )


@router.get("/{conversation_id}/messages", response_model=ZaloLibraryListResponse)
async def get_conversation_messages(
    conversation_id: str,
    account_id: Optional[str] = Query(None),
    x_user_id: str = Header("default", alias="X-User-ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user_id = _normalize_user_id(account_id or x_user_id)
    try:
        rows, total = await list_conversation_messages(
            user_id,
            conversation_id,
            limit=limit,
            offset=offset,
        )
        return {
            "messages": [ZaloLibraryMessage(**row) for row in rows],
            "groups": [],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
        }
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể tải tin nhắn hội thoại Zalo: {exc}")


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Nội dung tin nhắn văn bản")
    thread_type: Optional[int] = Field(
        None,
        description="0 = cá nhân, 1 = nhóm. Nếu để trống, tự suy ra từ conversation_id.",
    )


class SendMessageResponse(BaseModel):
    ok: bool
    conversation_id: str
    message: str = ""


@router.post("/{conversation_id}/send", response_model=SendMessageResponse)
async def send_message_to_conversation(
    conversation_id: str,
    body: SendMessageRequest,
    account_id: Optional[str] = Query(None),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    """Gửi tin nhắn văn bản trực tiếp vào một hội thoại Zalo qua ZCA API.

    - ``conversation_id`` là ID group hoặc thread cá nhân trong Supabase.
    - Nếu ``thread_type`` không được chỉ định, endpoint tự suy ra:
      số nguyên thuần túy → nhóm (type=1), còn lại → cá nhân (type=0).
    """
    user_id = _normalize_user_id(account_id or x_user_id)
    auth = await load_zca_auth(user_id)
    if not auth:
        raise HTTPException(
            status_code=401,
            detail="Chưa có phiên ZCA hợp lệ. Hãy đăng nhập Zalo bằng QR trước.",
        )

    # Infer thread_type from conversation_id when not explicitly provided
    if body.thread_type is not None:
        thread_type = body.thread_type
    else:
        thread_type = 1 if conversation_id.strip().startswith("g") else 0

    try:
        result = await send_zca_message(
            auth,
            conversation_id.strip(),
            body.text.strip(),
            thread_type=thread_type,
        )
        return SendMessageResponse(
            ok=True,
            conversation_id=conversation_id,
            message=result.get("message") or "Đã gửi tin nhắn thành công",
        )
    except ZcaAuthExpiredError:
        raise HTTPException(status_code=401, detail=ZCA_SESSION_EXPIRED_DETAIL)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể gửi tin nhắn: {exc}")


@router.post("/{conversation_id}/send-media", response_model=SendMessageResponse)
async def send_media_to_conversation(
    conversation_id: str,
    text: Optional[str] = Form(None),
    thread_type: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
    account_id: Optional[str] = Query(None),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    """Gửi hình ảnh hoặc tài liệu kèm chữ vào một hội thoại Zalo qua ZCA API."""
    user_id = _normalize_user_id(account_id or x_user_id)
    auth = await load_zca_auth(user_id)
    if not auth:
        raise HTTPException(
            status_code=401,
            detail="Chưa có phiên ZCA hợp lệ. Hãy đăng nhập Zalo bằng QR trước.",
        )

    if thread_type is not None:
        ttype = thread_type
    else:
        ttype = 1 if conversation_id.strip().startswith("g") else 0

    temp_paths: List[str] = []
    try:
        for file in files:
            orig_ext = os.path.splitext(file.filename or "")[1] or ".jpg"
            fd, path = tempfile.mkstemp(prefix="zalo-zca-upload-", suffix=orig_ext)
            content = await file.read()
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(content)
            temp_paths.append(path)

        result = await send_zca_images(
            auth,
            conversation_id.strip(),
            temp_paths,
            text=text.strip() if text else "",
            thread_type=ttype,
        )
        return SendMessageResponse(
            ok=True,
            conversation_id=conversation_id,
            message=result.get("message") or "Đã gửi file thành công",
        )
    except ZcaAuthExpiredError:
        raise HTTPException(status_code=401, detail=ZCA_SESSION_EXPIRED_DETAIL)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Không thể gửi file: {exc}")
    finally:
        for path in temp_paths:
            try:
                os.remove(path)
            except OSError:
                pass


class MarkReadResponse(BaseModel):
    ok: bool
    conversation_id: str
    message: str = ""


@router.post("/{conversation_id}/read", response_model=MarkReadResponse)
async def mark_conversation_read(
    conversation_id: str,
    account_id: Optional[str] = Query(None),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    """Đánh dấu hội thoại là đã đọc. Cập nhật trong Supabase và thông báo ZCA (nếu đăng nhập)."""
    user_id = _normalize_user_id(account_id or x_user_id)
    
    # 1. Update in Supabase
    try:
        await mark_conversation_as_read(user_id, conversation_id.strip())
    except Exception as exc:
        logger.warning(f"Could not update unread count in Supabase for user={user_id} conversation={conversation_id}: {exc}")

    # 2. Inform Zalo via ZCA if auth is available
    auth = await load_zca_auth(user_id)
    if auth:
        thread_type = 1 if conversation_id.strip().startswith("g") else 0
        try:
            await remove_zca_unread_mark(auth, conversation_id.strip(), thread_type=thread_type)
        except Exception as exc:
            logger.warning(f"Could not remove unread mark on Zalo for user={user_id} conversation={conversation_id}: {exc}")

    return MarkReadResponse(
        ok=True,
        conversation_id=conversation_id,
        message="Hội thoại đã được đánh dấu là đã đọc"
    )
