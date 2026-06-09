from typing import Optional
from fastapi import Header, HTTPException, Query, status

from app.core.config import settings


def verify_zalo_api_key(
    x_api_key: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> None:
    if not settings.api_key:
        return

    provided_key = x_api_key or api_key
    if provided_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
