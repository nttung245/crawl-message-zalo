from typing import List, Optional
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.schemas.job import JobData
from app.modules.zalo.services.job_events import subscribe_job_events
from app.modules.zalo.services.job_store import get_job, list_jobs_for_user

router = APIRouter(
    prefix="/api/zalo/jobs",
    tags=["zalo-jobs"],
    dependencies=[Depends(verify_zalo_api_key)],
)


def _normalize_user_id(value: Optional[str]) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


@router.get("", response_model=List[JobData])
async def get_all_jobs(x_user_id: str = Header("default", alias="X-User-ID")):
    return list_jobs_for_user(_normalize_user_id(x_user_id))


@router.get("/events")
async def stream_job_events(
    x_user_id: str = Header("default", alias="X-User-ID"),
    user_id: Optional[str] = None,
):
    event_user_id = _normalize_user_id(user_id or x_user_id)
    return StreamingResponse(
        subscribe_job_events(event_user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}", response_model=JobData)
async def get_job_status(job_id: str, x_user_id: str = Header("default", alias="X-User-ID")):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if (job.user_id or "default") != _normalize_user_id(x_user_id):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job
