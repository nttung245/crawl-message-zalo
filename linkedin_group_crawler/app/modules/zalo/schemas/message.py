from pydantic import BaseModel
from typing import Optional, List


class Message(BaseModel):
    message_id: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    timestamp: Optional[str] = None
    time_text: Optional[str] = None
    type: str = "text"  # "text" | "image" | "sticker" | "file" | "system"
    content: Optional[str] = None
    image_urls: List[str] = []
    reply_to_id: Optional[str] = None
    is_deleted: bool = False
    is_sent: bool = False

