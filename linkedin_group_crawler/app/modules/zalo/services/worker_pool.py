from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class ZaloBrowserWorker:
    worker_id: str
    base_url: str

    @property
    def label(self) -> str:
        if self.worker_id == "default":
            return "Default"
        return self.worker_id.replace("-", " ").title()


def _normalize_worker_id(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    return "".join(ch for ch in normalized if ch.isalnum() or ch in {"-", "."})


def _parse_worker_entries(raw: str) -> list[ZaloBrowserWorker]:
    workers: list[ZaloBrowserWorker] = []
    seen: set[str] = set()

    for index, entry in enumerate(part.strip() for part in raw.split(",") if part.strip()):
        if "=" in entry:
            worker_id_raw, url_raw = entry.split("=", 1)
            worker_id = _normalize_worker_id(worker_id_raw)
            url = url_raw.strip().rstrip("/")
        else:
            worker_id = f"worker-{index + 1}"
            url = entry.rstrip("/")

        if not worker_id or not url:
            continue
        if worker_id in seen:
            raise HTTPException(
                status_code=500,
                detail=f"Duplicate Zalo browser worker id: {worker_id}",
            )
        seen.add(worker_id)
        workers.append(ZaloBrowserWorker(worker_id=worker_id, base_url=url))

    return workers


def get_zalo_browser_workers() -> list[ZaloBrowserWorker]:
    multi_worker_urls = (os.getenv("ZALO_BROWSER_SERVICE_URLS") or "").strip()
    if multi_worker_urls:
        workers = _parse_worker_entries(multi_worker_urls)
        if workers:
            return workers

    single_worker_url = (os.getenv("ZALO_BROWSER_SERVICE_URL") or "").strip().rstrip("/")
    if single_worker_url:
        return [ZaloBrowserWorker(worker_id="default", base_url=single_worker_url)]

    return []


def is_zalo_browser_proxy_configured() -> bool:
    return bool(get_zalo_browser_workers())


def _normalize_user_id(value: str) -> str:
    normalized = value.strip().lower()
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "@"} else "-" for ch in normalized)
    normalized = normalized.strip("-_.")
    return normalized or "default"


def _user_id_from_request(request: Request) -> str:
    return _normalize_user_id(
        request.headers.get("X-User-ID")
        or request.query_params.get("user_id")
        or "default"
    )


def _select_worker_for_user(workers: list[ZaloBrowserWorker], user_id: str) -> ZaloBrowserWorker:
    if len(workers) == 1:
        return workers[0]

    digest = hashlib.sha256(user_id.encode("utf-8")).digest()
    worker_index = int.from_bytes(digest[:8], "big") % len(workers)
    return workers[worker_index]


def resolve_zalo_browser_worker(request: Request) -> ZaloBrowserWorker:
    workers = get_zalo_browser_workers()
    if not workers:
        raise HTTPException(
            status_code=503,
            detail="ZALO_BROWSER_SERVICE_URL or ZALO_BROWSER_SERVICE_URLS is not configured",
        )

    workers_by_id = {worker.worker_id: worker for worker in workers}
    requested_worker_id = _normalize_worker_id(
        request.headers.get("X-Zalo-Worker-ID")
        or request.query_params.get("worker_id")
        or ""
    )
    if requested_worker_id:
        worker = workers_by_id.get(requested_worker_id)
        if worker:
            return worker
        if len(workers) == 1:
            return workers[0]
        if not worker:
            valid_workers = ", ".join(sorted(workers_by_id))
            raise HTTPException(
                status_code=400,
                detail=f"Unknown Zalo worker '{requested_worker_id}'. Valid workers: {valid_workers}",
            )

    return _select_worker_for_user(workers, _user_id_from_request(request))
