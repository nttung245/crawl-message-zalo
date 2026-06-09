
from typing import List, Optional
from pydantic import BaseModel, Field


class ZaloMessageAsset(BaseModel):
    id: Optional[str] = None
    message_id: Optional[str] = None
    source_url: Optional[str] = None
    storage_path: Optional[str] = None
    storage_url: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None


class ZaloLibraryMessage(BaseModel):
    id: Optional[str] = None
    user_id: str = "default"
    job_id: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    source_message_id: Optional[str] = None
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    timestamp_text: Optional[str] = None
    time_text: Optional[str] = None
    type: str = "text"
    content: Optional[str] = None
    is_sent: bool = False
    is_deleted: bool = False
    assets: List[ZaloMessageAsset] = Field(default_factory=list)


class ZaloLibraryMessageCreate(BaseModel):
    group_name: Optional[str] = None
    sender_name: Optional[str] = None
    time_text: Optional[str] = None
    type: str = "text"
    content: Optional[str] = None
    asset_urls: List[str] = Field(default_factory=list)


class ZaloLibraryMessageUpdate(BaseModel):
    group_name: Optional[str] = None
    sender_name: Optional[str] = None
    time_text: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    is_deleted: Optional[bool] = None


class ZaloLibraryBulkDeleteRequest(BaseModel):
    message_ids: List[str] = Field(default_factory=list)
    group_name: Optional[str] = None
    delete_all_matching: bool = False


class ZaloLibraryBulkDeleteResponse(BaseModel):
    deleted_count: int = 0


class ZaloLibraryGroupSummary(BaseModel):
    group_name: str
    sheet_tab: Optional[str] = None
    message_count: int = 0
    image_count: int = 0
    latest_message_at: Optional[str] = None


class ZaloLibraryListResponse(BaseModel):
    messages: List[ZaloLibraryMessage]
    groups: List[ZaloLibraryGroupSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 200
    offset: int = 0
    has_more: bool = False


class ZaloConversationSummary(BaseModel):
    conversation_id: str
    conversation_name: str
    account_id: str
    message_count: int = 0
    image_count: int = 0
    sent_count: int = 0
    received_count: int = 0
    latest_message_at: Optional[str] = None
    latest_content: Optional[str] = None
    latest_sender_name: Optional[str] = None
    has_messages: bool = True
    sync_status: str = "has_messages"
    avatar_url: Optional[str] = None
    unread_count: int = 0
    is_pinned: bool = False


class ZaloConversationListResponse(BaseModel):
    account_id: str
    conversations: List[ZaloConversationSummary] = Field(default_factory=list)
    total: int = 0
