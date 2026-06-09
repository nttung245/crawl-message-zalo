from typing import Optional
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
from playwright.async_api import Browser, BrowserContext, Page


@dataclass
class SessionData:
    session_id: str
    user_id: str
    browser: Optional[Browser]
    context: Optional[BrowserContext]
    page: Optional[Page]
    status: str  # "waiting_scan" | "confirmed" | "qr_expired"
    qr_base64: Optional[str] = None
    qr_signature: Optional[str] = None
    qr_process: Optional[Any] = None
    zca_auth: Optional[dict] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime = field(default_factory=datetime.utcnow)

