from typing import Dict, List, Optional

from app.modules.zalo.schemas.job import JobData


job_store: Dict[str, JobData] = {}


def get_job(job_id: str) -> Optional[JobData]:
    return job_store.get(job_id)


def save_job(job: JobData) -> None:
    job_store[job.job_id] = job


def list_jobs() -> List[JobData]:
    return list(job_store.values())

