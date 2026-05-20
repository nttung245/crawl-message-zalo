# src/modules/facebook/services/session_manager.py
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

@dataclass
class AuthSession:
    session_id: str
    email: str
    status: str = "PROCESSING"  # PROCESSING, NEED_PHONE_APPROVAL, NEED_OTP, SUCCESS, ERROR, ERROR_BOT_BLOCKED
    message: str = ""
    otp_code: Optional[str] = None
    # Dùng Event để "đánh thức" thread ngầm khi có OTP từ Frontend gửi lên
    otp_event: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.time)

class SessionManager:
    _sessions: Dict[str, AuthSession] = {}
    _lock = threading.Lock()

    @classmethod
    def create_session(cls, email: str) -> AuthSession:
        with cls._lock:
            # Dọn dẹp session cũ quá 10 phút tránh tràn RAM
            current_time = time.time()
            expired = [sid for sid, s in cls._sessions.items() if current_time - s.created_at > 600]
            for sid in expired:
                del cls._sessions[sid]

            session_id = str(uuid.uuid4())
            session = AuthSession(session_id=session_id, email=email)
            cls._sessions[session_id] = session
            return session

    @classmethod
    def get_session(cls, session_id: str) -> Optional[AuthSession]:
        with cls._lock:
            return cls._sessions.get(session_id)

    @classmethod
    def remove_session(cls, session_id: str):
        with cls._lock:
            if session_id in cls._sessions:
                del cls._sessions[session_id]