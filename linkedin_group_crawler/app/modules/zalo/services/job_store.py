from typing import Dict, List, Optional

from app.modules.zalo.schemas.job import JobData
from app.modules.zalo.services.job_events import publish_job_event


job_store: Dict[str, JobData] = {}


def get_job(job_id: str) -> Optional[JobData]:
    return job_store.get(job_id)


def save_job(job: JobData) -> None:
    job_store[job.job_id] = job
    try:
        import asyncio

        asyncio.get_running_loop().create_task(publish_job_event(job))
    except RuntimeError:
        pass


def list_jobs() -> List[JobData]:
    return list(job_store.values())


def list_jobs_for_user(user_id: str) -> List[JobData]:
    normalized_user_id = (user_id or "default").strip().lower() or "default"
    return [
        job
        for job in job_store.values()
        if (job.user_id or "default").strip().lower() == normalized_user_id
    ]

