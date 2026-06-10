from typing import Optional
from pydantic import BaseModel


class Group(BaseModel):
    group_id: str
    name: str
    avatar_url: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None
    last_sender_id: Optional[str] = None
    last_sender_name: Optional[str] = None
    last_message_type: Optional[str] = None
    unread_count: int = 0
    is_pinned: bool = False

