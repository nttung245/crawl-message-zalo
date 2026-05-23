from pydantic import BaseModel
from typing import Optional


class Group(BaseModel):
    group_id: str
    name: str
    avatar_url: Optional[str] = None
    last_message: Optional[str] = None
    unread_count: int = 0

