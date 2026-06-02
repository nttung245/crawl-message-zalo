from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class JobProgress(BaseModel):
    messages_collected: int = 0
    images_found: int = 0
    oldest_message_date: Optional[str] = None


class JobData(BaseModel):
    job_id: str
    group_id: str
    group_name: str
    sheet_id: Optional[str] = None
    sheet_tab: Optional[str] = None
    status: str = "running"  # "queued" | "running" | "completed" | "failed"
    progress: JobProgress = JobProgress()
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    sheet_url: Optional[str] = None

