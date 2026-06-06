from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import DefaultDict

from app.modules.zalo.schemas.job import JobData


_subscribers: DefaultDict[str, set[asyncio.Queue[str]]] = defaultdict(set)


def _normalize_user_id(user_id: str | None) -> str:
    return (user_id or "default").strip().lower() or "default"


def _job_payload(job: JobData) -> str:
    if hasattr(job, "model_dump"):
        payload = job.model_dump(mode="json")
    else:
        payload = job.dict()
    return json.dumps(payload, ensure_ascii=False)


async def publish_job_event(job: JobData) -> None:
    user_id = _normalize_user_id(job.user_id)
    payload = _job_payload(job)
    stale: list[asyncio.Queue[str]] = []
    for queue in list(_subscribers[user_id]):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            stale.append(queue)

    for queue in stale:
        _subscribers[user_id].discard(queue)


async def subscribe_job_events(user_id: str):
    normalized_user_id = _normalize_user_id(user_id)
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    _subscribers[normalized_user_id].add(queue)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=20)
                yield f"event: job-status\ndata: {payload}\n\n"
            except asyncio.TimeoutError:
                yield "event: heartbeat\ndata: {}\n\n"
    finally:
        _subscribers[normalized_user_id].discard(queue)
