from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.modules.zalo.schemas.job import JobData
from app.modules.zalo.services.job_store import get_job, list_jobs
from app.modules.zalo.api.security import verify_zalo_api_key

router = APIRouter(
    prefix="/api/zalo/jobs",
    tags=["zalo-jobs"],
    dependencies=[Depends(verify_zalo_api_key)],
)


@router.get("", response_model=List[JobData])
async def get_all_jobs():
    return list_jobs()


@router.get("/{job_id}", response_model=JobData)
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job

