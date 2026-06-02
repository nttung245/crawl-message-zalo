import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.services.worker_pool import (
    get_zalo_browser_workers,
    resolve_zalo_browser_worker,
)


router = APIRouter(
    prefix="/api/zalo",
    tags=["zalo-proxy"],
    dependencies=[Depends(verify_zalo_api_key)],
)

legacy_groups_router = APIRouter(
    prefix="/api/groups",
    tags=["zalo-proxy"],
    dependencies=[Depends(verify_zalo_api_key)],
)


async def _proxy_request(request: Request, upstream_path: str) -> Response:
    worker = resolve_zalo_browser_worker(request)
    target = worker.base_url

    url = httpx.URL(f"{target}{upstream_path}").copy_with(query=request.url.query.encode("utf-8"))
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    headers["X-Zalo-Worker-ID"] = worker.worker_id

    client = httpx.AsyncClient(timeout=None)
    try:
        proxy_request = client.build_request(
            request.method,
            url,
            content=request.stream(),
            headers=headers,
        )
        upstream = await client.send(proxy_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Zalo worker '{worker.worker_id}' is not reachable: {exc}",
        ) from exc

    excluded_headers = {
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    }
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in excluded_headers
    }
    response_headers["X-Zalo-Worker-ID"] = worker.worker_id

    async def _stream_body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        _stream_body(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


@router.get("/workers")
async def list_zalo_workers(request: Request) -> dict:
    # This route still sits behind the router-level API key dependency.
    workers = get_zalo_browser_workers()
    selected_worker = resolve_zalo_browser_worker(request) if workers else None
    return {
        "workers": [
            {"id": worker.worker_id, "url": worker.base_url}
            for worker in workers
        ],
        "selected_worker_id": selected_worker.worker_id if selected_worker else None,
    }


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_zalo(request: Request, path: str) -> Response:
    return await _proxy_request(request, f"/api/zalo/{path}")


@legacy_groups_router.api_route("", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@legacy_groups_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_legacy_groups(request: Request, path: str = "") -> Response:
    suffix = f"/{path}" if path else ""
    return await _proxy_request(request, f"/api/groups{suffix}")
