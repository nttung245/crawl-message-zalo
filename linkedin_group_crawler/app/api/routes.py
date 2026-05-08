"""API routes for LinkedIn group crawler."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import random
import re
import time
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.config import BASE_DIR, settings
from app.schemas.request_models import (
    AddListGroupRequest,
    CrawlGroupRequest,
    FilterDataRequest,
    GetAllPostsRequest,
    LinkedinAppCrawlBatchRequest,
    LinkedinAppFilterPostsSheetRequest,
    LinkedinAppGetAllPostsSheetRequest,
    LoginRequest,
    ProfileCommentsRequest,
    N8nAddGroupRequest,
    N8nCredentialWebhookRequest,
    N8nGetAllGroupsRequest,
    N8nGetSheetLinkRequest,
    N8nRemoveGroupRequest,
    N8nUpdateGroupRequest,
    N8nWebhookPassthroughRequest,
    StartWorkflowRequest,
    VerifyLoginRequest,
)
from app.schemas.response_models import (
    BaseResponse,
    BulkGroupImportData,
    BulkGroupImportResponse,
    BulkGroupImportScrapedItem,
    CrawlDataResponse,
    CrawlResponse,
    FilterDataResponse,
    GetAllPostsResponse,
    LinkedinAppCrawlBatchData,
    LinkedinAppCrawlBatchResponse,
    LinkedinAppCrawlGroupResult,
    LinkedinSheetFilterPostsResponse,
    LinkedinSheetGroupsData,
    LinkedinSheetGroupsResponse,
    LinkedinSheetTopPostsData,
    LinkedinSheetTopPostsResponse,
    LoginResponse,
    N8nWebhookNotifyData,
    N8nWebhookNotifyResponse,
    SheetLinkFromN8nData,
    SheetLinkFromN8nResponse,
    StatusDataResponse,
    StatusResponse,
    TopPostResponse,
    VerifyLoginResponse,
)
from app.services.auth_service import (
    PendingLoginSessionNotFoundError,
    login_and_save_session,
    verify_pending_login_otp,
)
from app.services.crawler_service import open_group_and_collect_posts
from app.services.group_bulk_import_service import bulk_scrape_groups, normalize_group_url
from app.services.profile_comments_service import LinkedinLoginRequiredError, crawl_profile_comments
from app.services.n8n_webhook_service import (
    extract_sheet_link_from_n8n_response_body,
    fetch_sheet_link_via_n8n_webhook,
    post_json_to_n8n_webhook,
    push_credentials_to_n8n_webhook,
    push_start_to_n8n_webhook,
)
from app.services import google_sheet_service as gsheet
from app.services.n8n_post_filter_service import (
    build_crawl_sessions_from_posts,
    filter_posts_by_inclusive_date_range,
    normalize_n8n_posts,
    posts_from_n8n_payload,
)
from app.services.ranking_service import (
    enrich_and_filter_posts,
    pick_top_post,
    select_most_recent_posts,
)
from app.utils.logger import get_logger


router = APIRouter()
logger = get_logger(__name__)


def _state_path_for_response(state_path) -> str:
    """Return a user-friendly state path for API responses."""

    try:
        return state_path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(state_path)


def _compute_filter_date_window(payload: FilterDataRequest) -> tuple[date | None, date | None]:
    """Trả về (start, end) inclusive theo payload; cả hai None = không lọc ngày."""

    today = datetime.now().date()
    if payload.preset == "last_7_days":
        return today - timedelta(days=7), today
    if payload.preset == "last_30_days":
        return today - timedelta(days=30), today

    if payload.date_from or payload.date_to:
        start_d = date.fromisoformat(payload.date_from) if payload.date_from else None
        end_d = date.fromisoformat(payload.date_to) if payload.date_to else None
        if start_d is None and end_d is not None:
            start_d = end_d
        elif end_d is None and start_d is not None:
            end_d = today
        if start_d is not None and end_d is not None and start_d > end_d:
            raise ValueError("date_from phải nhỏ hơn hoặc bằng date_to")
        return start_d, end_d

    if payload.date:
        d = date.fromisoformat(payload.date)
        return d, d

    return None, None


def _crawl_id_session_prefix(email: str | None, session_id: str | None, resolved_linkedin_session_id: str) -> str:
    """Phần trước dấu `_` của id_session_crawl (POST /start): ưu tiên local-part email LinkedIn."""

    raw_email = (email or "").strip().lower()
    if raw_email and "@" in raw_email:
        local = raw_email.split("@", 1)[0]
        local = re.sub(r"[^a-z0-9._-]", "", local).strip("._-")
        return local or "user"

    fallback = (raw_email or (session_id or "").strip().lower() or (resolved_linkedin_session_id or "").strip().lower())
    if fallback:
        slug = re.sub(r"[^a-z0-9_-]+", "-", fallback).strip("-")[:80]
        return slug or "session"
    return "session"


def _extract_webhook_message_and_payload(raw_preview: str) -> tuple[str | None, Any]:
    """Parse preview text thành message/payload để frontend hiển thị dễ hơn."""

    text = (raw_preview or "").strip()
    if not text:
        return None, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, None

    if isinstance(parsed, dict):
        for key in ("message", "msg", "detail", "status", "result"):
            value = parsed.get(key)
            if isinstance(value, str):
                message = value.strip()
                if message:
                    return message, parsed
        return text, parsed
    if isinstance(parsed, str):
        parsed_text = parsed.strip()
        return (parsed_text or text), parsed
    return text, parsed


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optionally protect endpoints with an API key."""

    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@router.get("/health", response_model=BaseResponse)
def health_check() -> BaseResponse:
    """Health check endpoint."""

    return BaseResponse(success=True, message="Service is healthy")


@router.get("/status", response_model=StatusResponse)
def system_status() -> StatusResponse:
    """Return runtime configuration needed by the frontend."""

    return StatusResponse(
        success=True,
        message="Service status loaded",
        data=StatusDataResponse(
            api_key_enabled=bool(settings.api_key),
            headless=settings.headless,
            default_max_items=settings.default_max_items,
            default_scroll_times=settings.default_scroll_times,
            cors_origins=settings.cors_origins or [],
            n8n_webhook_configured=bool((settings.n8n_webhook_url or "").strip()),
            n8n_get_link_webhook_configured=bool(
                (settings.n8n_webhook_get_link_url or "").strip(),
            ),
            n8n_webhook_get_post_crawled_configured=bool(
                (settings.n8n_webhook_get_post_crawled_url or "").strip(),
            ),
            n8n_webhook_get_url_group_crawled_configured=bool(
                (settings.n8n_webhook_get_url_group_crawled_url or "").strip(),
            ),
            n8n_webhook_get_result_crawl_by_id_configured=bool(
                (settings.n8n_webhook_get_result_crawl_by_id_url or "").strip(),
            ),
            n8n_webhook_filter_data_configured=bool(
                (settings.n8n_webhook_get_all_posts_url or "").strip(),
            ),
            n8n_webhook_get_all_posts_configured=bool(
                (settings.n8n_webhook_get_all_posts_url or "").strip(),
            ),
            n8n_webhook_start_configured=bool(
                (settings.n8n_webhook_start_url or "").strip(),
            ),
            n8n_webhook_get_group_configured=bool(
                (settings.n8n_webhook_get_group_url or "").strip(),
            ),
            n8n_webhook_add_group_configured=bool(
                (settings.n8n_webhook_add_group_url or "").strip(),
            ),
            n8n_webhook_remove_group_configured=bool(
                (settings.n8n_webhook_remove_group_url or "").strip(),
            ),
            n8n_webhook_update_group_configured=bool(
                (settings.n8n_webhook_update_group_url or "").strip(),
            ),
            n8n_webhook_add_list_group_configured=bool(
                (settings.n8n_webhook_add_list_group_url or "").strip(),
            ),
            n8n_webhook_bulk_import_groups_configured=bool(
                (settings.n8n_webhook_add_list_group_url or "").strip(),
            ),
            google_sheet_configured=gsheet.spreadsheet_configured(),
        ),
    )


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(verify_api_key)])
def login(payload: LoginRequest) -> LoginResponse:
    """Login to LinkedIn. Returns need_otp when email challenge is required."""

    try:
        result = login_and_save_session(
            email=payload.email,
            password=payload.password,
            session_id=payload.session_id,
            force_relogin=payload.force_relogin,
        )
        if result.status == "need_otp":
            return LoginResponse(
                success=True,
                message="LinkedIn yêu cầu mã xác minh. Gọi POST /verify với mã OTP.",
                session_id=result.session_id,
                state_path=None,
                email=result.email,
                login_step="need_otp",
                need_otp=True,
                checkpoint_url=result.checkpoint_url,
            )
        return LoginResponse(
            success=True,
            message="LinkedIn session saved successfully",
            session_id=result.session_id,
            state_path=_state_path_for_response(result.state_path) if result.state_path else None,
            email=result.email,
            login_step="success",
            need_otp=False,
            checkpoint_url=None,
        )
    except Exception as exc:
        logger.exception("Login endpoint failed")
        return LoginResponse(
            success=False,
            message=str(exc),
            session_id=None,
            state_path=None,
            login_step="error",
            need_otp=False,
            checkpoint_url=None,
        )


@router.post("/verify", response_model=VerifyLoginResponse, dependencies=[Depends(verify_api_key)])
def verify_login(payload: VerifyLoginRequest) -> VerifyLoginResponse:
    """Complete LinkedIn OTP verification using pending session from POST /login."""

    try:
        session_id, state_path, email = verify_pending_login_otp(
            pending_session_id=payload.session_id,
            otp_code=payload.otp,
            checkpoint_url=payload.checkpoint_url,
        )
        return VerifyLoginResponse(
            success=True,
            message="Xác minh OTP thành công. Session LinkedIn đã được lưu.",
            session_id=session_id,
            state_path=_state_path_for_response(state_path),
            email=email,
            login_step="success",
            need_otp=False,
            checkpoint_url=None,
        )
    except PendingLoginSessionNotFoundError as exc:
        return VerifyLoginResponse(
            success=False,
            message=str(exc),
            session_id=None,
            state_path=None,
            email=None,
            login_step="error",
            need_otp=False,
            checkpoint_url=None,
        )
    except Exception as exc:
        logger.exception("Verify endpoint failed")
        return VerifyLoginResponse(
            success=False,
            message=str(exc),
            session_id=None,
            state_path=None,
            email=None,
            login_step="error",
            need_otp=False,
            checkpoint_url=None,
        )


@router.post("/crawl-linkedin-group", response_model=CrawlResponse, dependencies=[Depends(verify_api_key)])
def crawl_linkedin_group(payload: CrawlGroupRequest) -> CrawlResponse:
    """Crawl một nhóm: trả **toàn bộ** bài đúng ngày mục tiêu; không có thì **N** bài gần nhất (cho n8n)."""

    try:
        if not payload.session_id and not payload.email:
            return CrawlResponse(
                success=False,
                message="Provide either session_id or email so the API can resolve the saved LinkedIn session.",
                data=None,
            )

        crawl_result = open_group_and_collect_posts(
            session_id=payload.session_id,
            email=payload.email,
            group_url=payload.group_url,
            max_items=payload.max_items,
        )
        filtered_posts, target_day = enrich_and_filter_posts(
            posts=crawl_result["posts"],
            target_date=payload.target_date,
            crawl_time=crawl_result["crawl_time"],
        )

        if crawl_result["total_posts_scraped"] == 0:
            return CrawlResponse(success=False, message="No posts found on the LinkedIn group page", data=None)

        if filtered_posts:
            posts_out = filtered_posts
            selection_mode = "target_day"
            top_post = pick_top_post(filtered_posts)
            msg = f"Crawl OK — {len(posts_out)} bài trong ngày {target_day.isoformat()}"
        else:
            posts_out = select_most_recent_posts(
                list(crawl_result["posts"]),
                limit=payload.fallback_recent_count,
            )
            selection_mode = "fallback_recent"
            top_post = pick_top_post(posts_out) if posts_out else None
            msg = (
                f"Không có bài trong ngày {target_day.isoformat()}, "
                f"trả {len(posts_out)} bài gần nhất"
            )

        response_data = CrawlDataResponse(
            session_id=crawl_result["session_id"],
            group_url=payload.group_url,
            group_name=crawl_result.get("group_name", ""),
            target_date=target_day.isoformat(),
            email=payload.email,
            total_posts_scraped=crawl_result["total_posts_scraped"],
            total_posts_in_target_date=len(filtered_posts),
            top_post=TopPostResponse.from_post_dict(top_post) if top_post else None,
            posts=[TopPostResponse.from_post_dict(p) for p in posts_out],
            selection_mode=selection_mode,
        )
        return CrawlResponse(success=True, message=msg, data=response_data)
    except Exception as exc:
        logger.exception("Crawl endpoint failed")
        return CrawlResponse(success=False, message=str(exc), data=None)


def _webhook_response_for_api(full_text: str, *, max_raw_chars: int = 100_000) -> Any:
    """Parse body webhook thành JSON nếu được; không thì trả chuỗi (cắt nếu quá dài)."""

    text = (full_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if len(text) > max_raw_chars:
            return f"{text[:max_raw_chars]}…"
        return text


def _add_list_group_envelope_from_webhook(*, http_status: int, response_body: Any) -> tuple[bool, str]:
    """HTTP < 400; nếu body JSON có ``success`` / ``message`` (hoặc ``error``) thì đồng bộ envelope API với n8n."""

    http_ok = 100 <= http_status < 400
    api_ok = http_ok
    api_message = (
        "Đã cào xong; n8n đã trả HTTP response (chi tiết trong data.webhook_response)."
        if http_ok
        else f"Webhook trả HTTP {http_status}"
    )
    if isinstance(response_body, dict):
        w_msg = response_body.get("message")
        if isinstance(w_msg, str) and w_msg.strip():
            api_message = w_msg.strip()
        else:
            err_msg = response_body.get("error") or response_body.get("detail")
            if isinstance(err_msg, str) and err_msg.strip():
                api_message = err_msg.strip()
        if "success" in response_body and isinstance(response_body["success"], bool):
            api_ok = bool(response_body["success"]) and api_ok
    return api_ok, api_message


def _truncate_webhook_preview(raw: str, limit: int = 512) -> str:
    text = (raw or "").strip()
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def _resolve_crawler_email_for_n8n_groups(
    *,
    body_email: str | None,
    email_crawl: str | None = None,
) -> str:
    """Ưu tiên cookie ``email_crawl`` (frontend), sau đó ``body.email``."""

    merged = ((email_crawl or "").strip() or (body_email or "").strip())
    if not merged:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Thiếu email — cần cookie `email_crawl` hoặc trường `email` trong JSON "
                "để lấy **tất cả nhóm** theo đúng tài khoản crawl."
            ),
        )
    return merged


def _parse_n8n_json_body_optional(full_text: str) -> Any:
    text = (full_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:4096]}


def _pick_n8n_message(parsed: Any) -> str | None:
    """Lấy message từ JSON trả về của node Respond to Webhook (nếu có)."""

    if isinstance(parsed, dict):
        for key in ("message", "msg", "detail"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _n8n_get_all_groups_webhook_body(email: str) -> dict[str, Any]:
    """Payload gửi n8n: một email thống nhất (alias) để workflow lọc **tất cả nhóm** theo owner."""

    e = email.strip()
    return {
        "email": e,
        "Email_crawl": e,
        "userEmail": e,
    }


def _pick_group_rows(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    return []


def _pick_group_field(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item:
            return item.get(key)
    return None


def _normalize_n8n_groups(parsed: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _pick_group_rows(parsed):
        raw_row = _pick_group_field(item, ("row_number", "rowNumber", "stt", "STT"))
        row_number: int | None = None
        try:
            if raw_row is not None and str(raw_row).strip():
                row_number = int(raw_row)
        except (TypeError, ValueError):
            row_number = None

        raw_url = _pick_group_field(
            item,
            ("url_group", "URL_Nhóm", "group_url", "groupUrl", "URL_nhom", "url"),
        )
        raw_name = _pick_group_field(
            item,
            ("name_group", "Tên nhóm", "group_name", "groupName", "name"),
        )
        raw_email = _pick_group_field(item, ("email", "Email_crawl", "email_crawl"))
        raw_member = _pick_group_field(item, ("member", "members", "Thành viên", "thanh_vien"))

        url_group = str(raw_url or "").strip()
        if not url_group:
            continue
        name_group = str(raw_name or "").strip()
        email = str(raw_email or "").strip()
        try:
            member = int(raw_member) if raw_member is not None and str(raw_member).strip() else 0
        except (TypeError, ValueError):
            member = 0

        out.append(
            {
                "row_number": row_number,
                "url_group": url_group,
                "name_group": name_group,
                "email": email,
                "member": max(0, member),
            },
        )
    return out


def _group_url_match_key(url: str) -> str:
    """Chuẩn hóa URL nhóm để so trùng (khớp normalize_group_url + không phân biệt hoa thường)."""

    return normalize_group_url(url).lower().rstrip("/")


def _list_managed_groups_for_duplicate_check(email: str) -> tuple[list[dict[str, Any]], str | None]:
    """Gọi ``N8N_WEBHOOK_GET_GROUP`` giống n8n-get-all; trả (danh_sách, lỗi). ``lỗi`` != None → không kiểm tra được."""

    target = (settings.n8n_webhook_get_group_url or "").strip()
    if not target:
        return [], "N8N_WEBHOOK_GET_GROUP chưa được cấu hình — không kiểm tra trùng URL nhóm."
    res = _forward_n8n_group_webhook(
        url=target,
        env_hint="N8N_WEBHOOK_GET_GROUP",
        json_body=_n8n_get_all_groups_webhook_body(email),
    )
    if not res.success:
        return [], res.message or "Không lấy được danh sách nhóm để kiểm tra trùng."
    data = res.data if isinstance(res.data, dict) else {}
    parsed = data.get("parsed")
    return _normalize_n8n_groups(parsed), None


def _find_managed_group_duplicate(
    managed: list[dict[str, Any]],
    url_candidate: str,
    owner_email: str,
) -> dict[str, Any] | None:
    """Trùng chỉ khi URL nhóm và email owner (crawl) đều khớp với một dòng đã quản lý."""

    owner = (owner_email or "").strip().lower()
    if not owner:
        return None
    key = _group_url_match_key(url_candidate)
    for row in managed:
        u = _group_url_match_key(str(row.get("url_group", "")))
        if not u or u != key:
            continue
        row_email = str(row.get("email") or "").strip().lower()
        if row_email == owner:
            return row
    return None


def _duplicate_group_message(row: dict[str, Any]) -> str:
    name = str(row.get("name_group") or "").strip() or "—"
    url = str(row.get("url_group") or "").strip() or "—"
    return f"Nhóm: {name} url:{url} đã có trong danh sách!"


def _forward_n8n_group_webhook(*, url: str, env_hint: str, json_body: dict[str, Any]) -> BaseResponse:
    target = (url or "").strip()
    if not target:
        return BaseResponse(
            success=False,
            message=f"{env_hint} chưa được cấu hình trong .env.",
            data=None,
        )
    try:
        http_status, full_text = post_json_to_n8n_webhook(url=target, json_body=json_body)
    except RuntimeError as exc:
        return BaseResponse(success=False, message=str(exc), data=None)
    except httpx.RequestError as exc:
        logger.warning("Webhook %s không kết nối được: %s", env_hint, type(exc).__name__)
        return BaseResponse(
            success=False,
            message="Không kết nối được tới webhook n8n.",
            data=None,
        )
    except Exception as exc:
        logger.exception("Gọi webhook %s thất bại", env_hint)
        return BaseResponse(success=False, message=str(exc), data=None)

    preview = _truncate_webhook_preview(full_text)
    parsed = _parse_n8n_json_body_optional(full_text)
    ok = http_status < 400
    parsed_message = _pick_n8n_message(parsed)
    return BaseResponse(
        success=ok,
        message=(
            parsed_message
            if parsed_message
            else ("Đã gọi webhook n8n" if ok else f"n8n webhook trả về HTTP {http_status}")
        ),
        data={
            "http_status": http_status,
            "response_preview": preview,
            "parsed": parsed,
        },
    )


@router.post(
    "/n8n/webhook-credentials",
    response_model=N8nWebhookNotifyResponse,
    dependencies=[Depends(verify_api_key)],
)
def forward_credentials_to_n8n(payload: N8nCredentialWebhookRequest) -> N8nWebhookNotifyResponse:
    """Gửi email/tài khoản, mật khẩu và max_post tới webhook n8n (URL trong N8N_WEBHOOK_URL)."""

    try:
        http_status, preview = push_credentials_to_n8n_webhook(
            email=payload.email,
            password=payload.password,
            max_post=payload.max_post,
        )
        return N8nWebhookNotifyResponse(
            success=True,
            message="Đã gửi payload tới n8n webhook",
            data=N8nWebhookNotifyData(http_status=http_status, response_preview=preview),
        )
    except RuntimeError as exc:
        logger.warning("n8n webhook chưa cấu hình hoặc từ chối yêu cầu")
        return N8nWebhookNotifyResponse(success=False, message=str(exc), data=None)
    except httpx.HTTPStatusError as exc:
        preview = _truncate_webhook_preview(exc.response.text or "")
        status_code = exc.response.status_code
        logger.warning(
            "n8n webhook trả về HTTP lỗi status=%s (payload không ghi log)",
            status_code,
        )
        return N8nWebhookNotifyResponse(
            success=False,
            message=f"n8n webhook trả về HTTP {status_code}",
            data=N8nWebhookNotifyData(http_status=status_code, response_preview=preview),
        )
    except httpx.RequestError as exc:
        logger.warning(
            "Không kết nối được tới webhook n8n: %s",
            type(exc).__name__,
        )
        return N8nWebhookNotifyResponse(
            success=False,
            message="Không kết nối được tới webhook n8n. Kiểm tra URL và mạng.",
            data=None,
        )
    except Exception as exc:
        logger.exception("Gửi tới webhook n8n thất bại")
        return N8nWebhookNotifyResponse(success=False, message=str(exc), data=None)


@router.post("/start", response_model=N8nWebhookNotifyResponse, dependencies=[Depends(verify_api_key)])
def start_n8n_workflow(payload: StartWorkflowRequest) -> N8nWebhookNotifyResponse:
    """Gửi payload start đầy đủ (email/password + config + group_urls) tới webhook ``N8N_WEBHOOK_START``."""

    try:
        id_prefix = _crawl_id_session_prefix(payload.email, None, "")
        id_session_crawl = f"{id_prefix}_{random.randint(1_000_000_000, 9_999_999_999_999)}"
        http_status, preview = push_start_to_n8n_webhook(
            email=payload.email,
            password=payload.password,
            force_relogin=payload.force_relogin,
            id_session_crawl=id_session_crawl,
            max_posts=payload.max_posts,
            target_date=payload.target_date,
            mode=payload.mode,
            delay_sec=payload.delay_sec,
            group_urls=payload.group_urls,
        )
        response_message, response_payload = _extract_webhook_message_and_payload(preview)
        return N8nWebhookNotifyResponse(
            success=True,
            message="Đang tiến hành cào....",
            data=N8nWebhookNotifyData(
                http_status=http_status,
                response_preview=preview,
                response_message=response_message,
                response_payload=response_payload,
                id_session_crawl=id_session_crawl,
            ),
        )
    except RuntimeError as exc:
        logger.warning("n8n start webhook chưa cấu hình hoặc lỗi cấu hình")
        return N8nWebhookNotifyResponse(success=False, message=str(exc), data=None)
    except httpx.HTTPStatusError as exc:
        preview = _truncate_webhook_preview(exc.response.text or "")
        status_code = exc.response.status_code
        response_message, response_payload = _extract_webhook_message_and_payload(preview)
        logger.warning(
            "n8n start webhook trả về HTTP lỗi status=%s (payload không ghi log)",
            status_code,
        )
        return N8nWebhookNotifyResponse(
            success=False,
            message=f"n8n start webhook trả về HTTP {status_code}",
            data=N8nWebhookNotifyData(
                http_status=status_code,
                response_preview=preview,
                response_message=response_message,
                response_payload=response_payload,
            ),
        )
    except httpx.ReadTimeout:
        logger.warning("n8n start webhook read timeout (chưa nhận response trong thời gian chờ)")
        return N8nWebhookNotifyResponse(
            success=False,
            message=(
                "n8n start webhook bị timeout khi chờ response. "
                "Khả năng cao workflow/proxy chưa trả response kịp (Respond to Webhook đến quá muộn)."
            ),
            data=None,
        )
    except httpx.RequestError as exc:
        logger.warning(
            "Không kết nối được tới n8n start webhook: %s",
            type(exc).__name__,
        )
        return N8nWebhookNotifyResponse(
            success=False,
            message="Không kết nối được tới n8n start webhook. Kiểm tra URL và mạng.",
            data=None,
        )
    except Exception as exc:
        logger.exception("Gửi start tới webhook n8n thất bại")
        return N8nWebhookNotifyResponse(success=False, message=str(exc), data=None)


@router.post(
    "/n8n/get-sheet-link",
    response_model=SheetLinkFromN8nResponse,
    dependencies=[Depends(verify_api_key)],
)
def get_sheet_link_via_n8n(payload: N8nGetSheetLinkRequest) -> SheetLinkFromN8nResponse:
    """Gọi webhook n8n thứ hai (N8n_WEBHOOK_GET_LINK) để lấy link trang tính / Google Sheet."""

    body = payload.webhook_payload

    try:
        http_status, full_text = fetch_sheet_link_via_n8n_webhook(body=body)
    except RuntimeError as exc:
        return SheetLinkFromN8nResponse(success=False, message=str(exc), data=None)
    except httpx.RequestError as exc:
        logger.warning(
            "Không kết nối được tới webhook lấy link sheet: %s",
            type(exc).__name__,
        )
        return SheetLinkFromN8nResponse(
            success=False,
            message="Không kết nối được tới webhook lấy link sheet. Kiểm tra URL và mạng.",
            data=None,
        )
    except Exception as exc:
        logger.exception("Gọi webhook lấy link sheet thất bại")
        return SheetLinkFromN8nResponse(success=False, message=str(exc), data=None)

    preview = _truncate_webhook_preview(full_text)

    if http_status >= 400:
        return SheetLinkFromN8nResponse(
            success=False,
            message=f"Webhook lấy link sheet trả về HTTP {http_status}",
            data=SheetLinkFromN8nData(
                sheet_link=None,
                http_status=http_status,
                response_preview=preview,
            ),
        )

    sheet_link = extract_sheet_link_from_n8n_response_body(full_text)
    if not sheet_link:
        return SheetLinkFromN8nResponse(
            success=False,
            message="Webhook phản hồi nhưng không trích xuất được link sheet từ nội dung trả về.",
            data=SheetLinkFromN8nData(
                sheet_link=None,
                http_status=http_status,
                response_preview=preview,
            ),
        )

    return SheetLinkFromN8nResponse(
        success=True,
        message="Đã lấy link sheet từ n8n webhook",
        data=SheetLinkFromN8nData(
            sheet_link=sheet_link,
            http_status=http_status,
            response_preview=preview,
        ),
    )


def _forward_json_to_n8n_env_webhook(
    *,
    webhook_url: str,
    env_var_hint: str,
    payload: N8nWebhookPassthroughRequest,
) -> N8nWebhookNotifyResponse:
    """POST ``webhook_payload`` tới URL trong cấu hình; envelope giống webhook-credentials."""

    url = (webhook_url or "").strip()
    if not url:
        return N8nWebhookNotifyResponse(
            success=False,
            message=f"{env_var_hint} chưa được cấu hình trong .env.",
            data=None,
        )

    try:
        http_status, full_text = post_json_to_n8n_webhook(
            url=url,
            json_body=payload.webhook_payload,
        )
    except RuntimeError as exc:
        return N8nWebhookNotifyResponse(success=False, message=str(exc), data=None)
    except httpx.RequestError as exc:
        logger.warning(
            "Không kết nối được tới webhook n8n (%s): %s",
            env_var_hint,
            type(exc).__name__,
        )
        return N8nWebhookNotifyResponse(
            success=False,
            message="Không kết nối được tới webhook n8n. Kiểm tra URL và mạng.",
            data=None,
        )
    except Exception as exc:
        logger.exception("Gọi webhook n8n (%s) thất bại", env_var_hint)
        return N8nWebhookNotifyResponse(success=False, message=str(exc), data=None)

    preview = _truncate_webhook_preview(full_text)
    ok = http_status < 400
    return N8nWebhookNotifyResponse(
        success=ok,
        message="Đã POST tới n8n webhook" if ok else f"n8n webhook trả về HTTP {http_status}",
        data=N8nWebhookNotifyData(http_status=http_status, response_preview=preview),
    )


@router.post(
    "/n8n/webhook-get-post-crawled",
    response_model=N8nWebhookNotifyResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_webhook_get_post_crawled(
    payload: N8nWebhookPassthroughRequest = N8nWebhookPassthroughRequest(),
) -> N8nWebhookNotifyResponse:
    """POST body JSON tới URL trong ``N8N_WEBHOOK_GET_POST_CRAWLED``."""

    return _forward_json_to_n8n_env_webhook(
        webhook_url=settings.n8n_webhook_get_post_crawled_url,
        env_var_hint="N8N_WEBHOOK_GET_POST_CRAWLED",
        payload=payload,
    )


@router.post(
    "/n8n/webhook-get-url-group-crawled",
    response_model=N8nWebhookNotifyResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_webhook_get_url_group_crawled(
    payload: N8nWebhookPassthroughRequest = N8nWebhookPassthroughRequest(),
) -> N8nWebhookNotifyResponse:
    """POST body JSON tới URL trong ``N8N_WEBHOOK_GET_URL_GROUP_CRAWLED``."""

    return _forward_json_to_n8n_env_webhook(
        webhook_url=settings.n8n_webhook_get_url_group_crawled_url,
        env_var_hint="N8N_WEBHOOK_GET_URL_GROUP_CRAWLED",
        payload=payload,
    )


@router.post(
    "/n8n/webhook-get-result-crawl-by-id",
    response_model=N8nWebhookNotifyResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_webhook_get_result_crawl_by_id(
    payload: N8nWebhookPassthroughRequest = N8nWebhookPassthroughRequest(),
) -> N8nWebhookNotifyResponse:
    """POST body JSON tới URL trong ``N8n_WEBHOOK_GET_RESULT_CRAWL_BY_ID`` (hoặc ``N8N_...``)."""

    return _forward_json_to_n8n_env_webhook(
        webhook_url=settings.n8n_webhook_get_result_crawl_by_id_url,
        env_var_hint="N8n_WEBHOOK_GET_RESULT_CRAWL_BY_ID",
        payload=payload,
    )


@router.post(
    "/groups/n8n-get-all",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_groups_get_all(
    payload: N8nGetAllGroupsRequest,
    email_crawl: Annotated[str | None, Cookie()] = None,
) -> BaseResponse:
    """Lấy **tất cả nhóm** theo email: POST tới ``N8N_WEBHOOK_GET_GROUP`` với ``email`` / ``Email_crawl`` / ``userEmail`` (cùng một giá trị sau khi resolve).

    Ưu tiên cookie ``email_crawl``, không có thì dùng ``body.email``.
    """

    email = _resolve_crawler_email_for_n8n_groups(
        body_email=payload.email,
        email_crawl=email_crawl,
    )
    base = _forward_n8n_group_webhook(
        url=settings.n8n_webhook_get_group_url,
        env_hint="N8N_WEBHOOK_GET_GROUP",
        json_body=_n8n_get_all_groups_webhook_body(email),
    )
    if not base.success:
        return base
    data = base.data if isinstance(base.data, dict) else {}
    parsed = data.get("parsed")
    groups = _normalize_n8n_groups(parsed)
    parsed_total = None
    if isinstance(parsed, dict):
        t = parsed.get("total")
        try:
            parsed_total = int(t) if t is not None else None
        except (TypeError, ValueError):
            parsed_total = None
    base.data = {
        "http_status": data.get("http_status"),
        "total": parsed_total if parsed_total is not None else len(groups),
        "groups": groups,
    }
    return base


@router.post(
    "/groups/add",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_groups_add(
    payload: N8nAddGroupRequest,
    email_crawl: Annotated[str | None, Cookie()] = None,
) -> BaseResponse:
    """POST ``url_group``, ``name_group``, ``member``, ``email`` tới ``N8N_WEBHOOK_ADD_GROUP``."""

    email = _resolve_crawler_email_for_n8n_groups(
        body_email=payload.email,
        email_crawl=email_crawl,
    )
    managed, err = _list_managed_groups_for_duplicate_check(email)
    if err:
        return BaseResponse(success=False, message=err, data=None)
    dup = _find_managed_group_duplicate(managed, payload.url_group, email)
    if dup is not None:
        return BaseResponse(success=False, message=_duplicate_group_message(dup), data=None)
    return _forward_n8n_group_webhook(
        url=settings.n8n_webhook_add_group_url,
        env_hint="N8N_WEBHOOK_ADD_GROUP",
        json_body=payload.to_webhook_payload(email),
    )


@router.post(
    "/groups/add-list-group",
    response_model=BulkGroupImportResponse,
    dependencies=[Depends(verify_api_key)],
)
def groups_add_list_group(
    payload: AddListGroupRequest,
    email_crawl: Annotated[str | None, Cookie()] = None,
) -> BulkGroupImportResponse:
    """Cào danh sách nhóm, POST batch lên ``N8N_WEBHOOK_ADD_LIST_GROUP`` và **chờ** HTTP response của n8n (đồng bộ).

    API chỉ trả về sau khi webhook đã trả body (workflow cần node *Respond to Webhook* / tương đương). Mặc định chờ tối đa ~5 phút
    (``N8N_WEBHOOK_ADD_LIST_GROUP_TIMEOUT_SEC`` hoặc ``webhook_timeout_sec`` trong body).

    Nếu body JSON từ n8n có ``success`` / ``message`` (hoặc ``error``), envelope ``success`` / ``message`` của API được đồng bộ;
    kết quả cào vẫn nằm trong ``data.items``; body đầy đủ trong ``data.webhook_response``.
    """

    owner_email = _resolve_crawler_email_for_n8n_groups(
        body_email=payload.email,
        email_crawl=email_crawl,
    )
    managed, list_err = _list_managed_groups_for_duplicate_check(owner_email)
    if list_err:
        return BulkGroupImportResponse(
            success=False,
            message=list_err,
            data=BulkGroupImportData(items=[], webhook_skipped=True),
        )
    dup_messages: list[str] = []
    seen_dup_msg: set[str] = set()
    for raw_u in payload.group_urls:
        dup = _find_managed_group_duplicate(managed, raw_u, owner_email)
        if dup is not None:
            msg = _duplicate_group_message(dup)
            if msg not in seen_dup_msg:
                seen_dup_msg.add(msg)
                dup_messages.append(msg)
    if dup_messages:
        combined = (
            dup_messages[0]
            if len(dup_messages) == 1
            else "Các nhóm sau đã có trong danh sách: " + " ".join(dup_messages)
        )
        return BulkGroupImportResponse(
            success=False,
            message=combined,
            data=BulkGroupImportData(items=[], webhook_skipped=True),
        )

    raw_rows = bulk_scrape_groups(
        group_urls=payload.group_urls,
        session_id=payload.session_id,
        email=owner_email,
        delay_min_sec=payload.delay_min_sec,
        delay_max_sec=payload.delay_max_sec,
    )
    items = [BulkGroupImportScrapedItem(**row) for row in raw_rows]

    if not payload.post_to_webhook:
        return BulkGroupImportResponse(
            success=True,
            message="Đã cào xong (không gửi webhook vì post_to_webhook=false). Để gửi: true hoặc bỏ hẳn trường này.",
            data=BulkGroupImportData(items=items, webhook_skipped=True),
        )

    webhook_url = (settings.n8n_webhook_add_list_group_url or "").strip()
    if not webhook_url:
        return BulkGroupImportResponse(
            success=False,
            message="N8N_WEBHOOK_ADD_LIST_GROUP chưa được cấu hình trong .env (có thể dùng tạm N8N_WEBHOOK_BULK_IMPORT_GROUPS).",
            data=BulkGroupImportData(items=items, webhook_skipped=True),
        )

    groups_payload = [
        {
            "url_group": row["url_group"],
            "name_group": row["name_group"],
            "member": int(row["member"]),
            "memberCount": row["memberCount"],
        }
        for row in raw_rows
        if row.get("success")
    ]
    failed_payload = [
        {"url_group": row["url_group"], "error": row.get("error") or "unknown"}
        for row in raw_rows
        if not row.get("success")
    ]
    json_body: dict[str, Any] = {
        "email": owner_email,
        "Email_crawl": owner_email,
        "userEmail": owner_email,
        "groups": groups_payload,
        "failed": failed_payload,
    }

    webhook_timeout = float(
        payload.webhook_timeout_sec
        if payload.webhook_timeout_sec is not None
        else settings.n8n_webhook_add_list_group_timeout_sec
    )

    try:
        http_status, full_text = post_json_to_n8n_webhook(
            url=webhook_url,
            json_body=json_body,
            timeout_sec=webhook_timeout,
        )
    except RuntimeError as exc:
        return BulkGroupImportResponse(
            success=False,
            message=str(exc),
            data=BulkGroupImportData(items=items, webhook_skipped=True),
        )
    except httpx.TimeoutException:
        logger.warning("Add-list-group webhook timeout sau %ss", int(webhook_timeout))
        return BulkGroupImportResponse(
            success=False,
            message=(
                f"Hết thời gian chờ webhook ({int(webhook_timeout)}s) — n8n chưa trả HTTP response. "
                "Tăng N8N_WEBHOOK_ADD_LIST_GROUP_TIMEOUT_SEC hoặc webhook_timeout_sec; kiểm tra workflow có trả response đúng lúc."
            ),
            data=BulkGroupImportData(items=items, webhook_skipped=True),
        )
    except httpx.RequestError as exc:
        logger.warning("Add-list-group webhook không kết nối được: %s", type(exc).__name__)
        return BulkGroupImportResponse(
            success=False,
            message="Không kết nối được tới webhook add-list-group.",
            data=BulkGroupImportData(items=items, webhook_skipped=True),
        )
    except Exception as exc:
        logger.exception("Gọi webhook add-list-group thất bại")
        return BulkGroupImportResponse(success=False, message=str(exc), data=BulkGroupImportData(items=items, webhook_skipped=True))

    preview = _truncate_webhook_preview(full_text)
    response_body = _webhook_response_for_api(full_text)
    api_ok, api_message = _add_list_group_envelope_from_webhook(
        http_status=http_status,
        response_body=response_body,
    )
    return BulkGroupImportResponse(
        success=api_ok,
        message=api_message,
        data=BulkGroupImportData(
            items=items,
            webhook_http_status=http_status,
            webhook_response_preview=preview,
            webhook_response=response_body,
            webhook_skipped=False,
        ),
    )


@router.post(
    "/groups/remove",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_groups_remove(
    payload: N8nRemoveGroupRequest,
    email_crawl: Annotated[str | None, Cookie()] = None,
) -> BaseResponse:
    """POST ``url_group``, ``email`` tới ``N8N_WEBHOOK_REMOVE_GROUP``."""

    email = _resolve_crawler_email_for_n8n_groups(
        body_email=payload.email,
        email_crawl=email_crawl,
    )
    return _forward_n8n_group_webhook(
        url=settings.n8n_webhook_remove_group_url,
        env_hint="N8N_WEBHOOK_REMOVE_GROUP",
        json_body=payload.to_webhook_payload(email),
    )


@router.post(
    "/groups/update",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_groups_update(
    payload: N8nUpdateGroupRequest,
    email_crawl: Annotated[str | None, Cookie()] = None,
) -> BaseResponse:
    """POST payload cập nhật nhóm tới ``N8N_WEBHOOK_UPDATE_GROUP``; trường ``new_*`` trống → giữ giá trị cũ."""

    email = _resolve_crawler_email_for_n8n_groups(
        body_email=payload.email,
        email_crawl=email_crawl,
    )
    return _forward_n8n_group_webhook(
        url=settings.n8n_webhook_update_group_url,
        env_hint="N8N_WEBHOOK_UPDATE_GROUP",
        json_body=payload.to_webhook_payload(email),
    )


@router.post("/filter-data", response_model=FilterDataResponse, dependencies=[Depends(verify_api_key)])
def filter_data(payload: FilterDataRequest) -> FilterDataResponse:
    """Webhook → lọc theo điều kiện ngày → trả ``data`` chỉ là mảng phiên cào (trong phiên là ``posts``)."""

    try:
        url = (settings.n8n_webhook_get_all_posts_url or "").strip()
        if not url:
            return FilterDataResponse(
                success=False,
                message="N8N_WEBHOOK_GET_ALL_POSTS chưa được cấu hình (.env) — filter-data dùng chung webhook này.",
                data=None,
            )

        try:
            window_start, window_end = _compute_filter_date_window(payload)
        except ValueError as ve:
            return FilterDataResponse(success=False, message=str(ve), data=None)

        webhook_payload: dict[str, Any] = {"email": payload.email}

        timeout = max(1.0, float(settings.n8n_webhook_timeout_sec))

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=webhook_payload)

        text = (response.text or "").strip()

        logger.info(
            "filter-data -> get-all-posts webhook status=%s (body length=%s)",
            response.status_code,
            len(response.text or ""),
        )

        if response.status_code >= 400:
            return FilterDataResponse(
                success=False,
                message=f"Webhook get-all-posts trả về HTTP {response.status_code}",
                data=None,
            )

        result_data: Any = None
        try:
            result_data = response.json()
        except Exception as parse_exc:
            logger.warning("Không parse JSON từ n8n: %s", parse_exc)
            result_data = {"raw_text": text}

        response.raise_for_status()

        if isinstance(result_data, dict) and result_data.get("success") is False:
            return FilterDataResponse(
                success=False,
                message=str(result_data.get("message") or "Webhook n8n trả success=false"),
                data=None,
            )

        raw_posts = normalize_n8n_posts(posts_from_n8n_payload(result_data))
        filtered, _meta = filter_posts_by_inclusive_date_range(raw_posts, window_start, window_end)
        crawl_sessions = build_crawl_sessions_from_posts(filtered)

        return FilterDataResponse(
            success=True,
            message="Đã lọc và gom theo phiên cào",
            data=crawl_sessions,
        )
    except Exception as exc:
        logger.exception("Filter data endpoint failed")
        return FilterDataResponse(success=False, message=str(exc), data=None)


@router.post("/get-all-posts", response_model=GetAllPostsResponse, dependencies=[Depends(verify_api_key)])
def get_all_posts(payload: GetAllPostsRequest) -> GetAllPostsResponse:
    """Webhook → gom theo phiên cào; ``data`` chỉ là mảng phiên (mỗi phiên có ``posts``)."""

    try:
        url = (settings.n8n_webhook_get_all_posts_url or "").strip()
        if not url:
            return GetAllPostsResponse(
                success=False,
                message="N8N_WEBHOOK_GET_ALL_POSTS chưa được cấu hình trong .env.",
                data=None,
            )

        # Build payload for webhook with email and filters
        webhook_payload = {
            "email": payload.email,
        }
        
        # Add additional filters if provided
        if payload.filters:
            webhook_payload.update(payload.filters)

        timeout = max(1.0, float(settings.n8n_webhook_timeout_sec))

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=webhook_payload)

        logger.info(
            "n8n get all posts webhook responded status=%s (body length=%s)",
            response.status_code,
            len(response.text or ""),
        )

        # Check for HTTP errors
        if response.status_code >= 400:
            return GetAllPostsResponse(
                success=False,
                message=f"Webhook trả về HTTP {response.status_code}",
                data=None,
            )

        # Try to parse response as JSON
        result_data = None
        try:
            result_data = response.json()
        except Exception as parse_exc:
            logger.warning("Cannot parse n8n response as JSON: %s", parse_exc)
            result_data = {}

        response.raise_for_status()

        if isinstance(result_data, dict) and result_data.get("success") is False:
            return GetAllPostsResponse(
                success=False,
                message=str(result_data.get("message") or "Webhook n8n trả success=false"),
                data=None,
            )

        posts_raw = normalize_n8n_posts(posts_from_n8n_payload(result_data))
        crawl_sessions = build_crawl_sessions_from_posts(posts_raw)

        return GetAllPostsResponse(
            success=True,
            message="Đã gom posts theo phiên cào (phiên mới nhất trước)",
            data=crawl_sessions,
        )
    except Exception as exc:
        logger.exception("Get all posts endpoint failed")
        return GetAllPostsResponse(success=False, message=str(exc), data=None)


@router.post(
    "/linkedin/profile-comments",
    dependencies=[Depends(verify_api_key)],
    summary="Cào comment activity của profile theo public_id",
)
def linkedin_profile_comments(payload: ProfileCommentsRequest):
    """Mở ``/in/{public_id}/recent-activity/comments/``, scroll, parse ``a[href*='dashCommentUrn']``.

    Cần session đã login (``email`` hoặc ``session_id`` giống các endpoint crawl khác).
    """

    try:
        result = crawl_profile_comments(
            public_id=payload.public_id,
            max_items=payload.max_items,
            target_post_id=payload.target_post_id,
            session_id=payload.session_id,
            email=payload.email,
        )
        return result
    except LinkedinLoginRequiredError:
        return JSONResponse(
            status_code=200,
            content={"success": False, "code": "LINKEDIN_LOGIN_REQUIRED"},
        )
    except Exception as exc:
        logger.exception("linkedin/profile-comments failed")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(exc)},
        )


linkedin_app_router = APIRouter(
    prefix="/linkedin-app",
    tags=["linkedin-app"],
    dependencies=[Depends(verify_api_key)],
)


@linkedin_app_router.get("/get-all-posts", response_model=LinkedinSheetTopPostsResponse)
def linkedin_app_sheet_get_all_posts_get(
    email: Annotated[str, Query(..., min_length=1)],
) -> LinkedinSheetTopPostsResponse:
    """Đọc mọi bài của user (ô ``Email_crawl`` trùng ``email``), không lộ dữ liệu account khác."""

    return _linkedin_app_sheet_get_posts_for_owner(email)


@linkedin_app_router.post("/get-all-posts", response_model=LinkedinSheetTopPostsResponse)
def linkedin_app_sheet_get_all_posts_post(
    payload: LinkedinAppGetAllPostsSheetRequest,
) -> LinkedinSheetTopPostsResponse:
    """POST body: ``{ \"email\": \"...\" }``."""

    return _linkedin_app_sheet_get_posts_for_owner(payload.email)


def _linkedin_app_sheet_get_posts_for_owner(owner_email: str) -> LinkedinSheetTopPostsResponse:
    try:
        if not gsheet.spreadsheet_configured():
            return LinkedinSheetTopPostsResponse(
                success=False,
                message="Google Sheet chưa cấu hình hoặc thiếu file GOOGLE_SERVICE_ACCOUNT_JSON.",
                data=None,
            )

        headers, rows = gsheet.read_top_posts_as_dicts()
        filtered = gsheet.filter_sheet_top_posts_for_owner(
            rows,
            owner_email_token=owner_email,
            date_from=None,
            date_to=None,
        )
        return LinkedinSheetTopPostsResponse(
            success=True,
            message="Đã đọc dữ liệu của bạn từ Sheet",
            data=LinkedinSheetTopPostsData(headers=headers, rows=filtered, row_count=len(filtered)),
        )
    except Exception as exc:
        logger.exception("linkedin-app get-all-posts failed")
        return LinkedinSheetTopPostsResponse(
            success=False,
            message=gsheet.safe_http_message(exc),
            data=None,
        )


@linkedin_app_router.post("/filter-post", response_model=LinkedinSheetFilterPostsResponse)
def linkedin_app_sheet_filter_posts(payload: LinkedinAppFilterPostsSheetRequest) -> LinkedinSheetFilterPostsResponse:
    """Lọc theo ``email`` (bắt buộc) và khoảng ``date_from`` / ``date_to`` trên cột ``Ngày``."""

    try:
        if not gsheet.spreadsheet_configured():
            return LinkedinSheetFilterPostsResponse(
                success=False,
                message="Google Sheet chưa cấu hình hoặc thiếu file GOOGLE_SERVICE_ACCOUNT_JSON.",
                data=None,
            )
        headers, rows = gsheet.read_top_posts_as_dicts()
        d_from = date.fromisoformat(payload.date_from) if payload.date_from else None
        d_to = date.fromisoformat(payload.date_to) if payload.date_to else None
        filtered = gsheet.filter_sheet_top_posts_for_owner(
            rows,
            owner_email_token=payload.email,
            date_from=d_from,
            date_to=d_to,
        )
        return LinkedinSheetFilterPostsResponse(
            success=True,
            message="Đã lọc posts từ Sheet",
            data=LinkedinSheetTopPostsData(headers=headers, rows=filtered, row_count=len(filtered)),
        )
    except Exception as exc:
        logger.exception("linkedin-app filter-post failed")
        return LinkedinSheetFilterPostsResponse(
            success=False,
            message=gsheet.safe_http_message(exc),
            data=None,
        )


@linkedin_app_router.get("/get-all-groups", response_model=LinkedinSheetGroupsResponse)
def linkedin_app_sheet_get_all_groups() -> LinkedinSheetGroupsResponse:
    """Đọc tab danh sách URL nhóm (URL_Nhóm, email, Trạng thái,...)."""

    try:
        if not gsheet.spreadsheet_configured():
            return LinkedinSheetGroupsResponse(
                success=False,
                message="Google Sheet chưa cấu hình hoặc thiếu file GOOGLE_SERVICE_ACCOUNT_JSON.",
                data=None,
            )
        rows = gsheet.read_group_url_rows()
        return LinkedinSheetGroupsResponse(
            success=True,
            message="Đã đọc danh sách nhóm",
            data=LinkedinSheetGroupsData(rows=rows, row_count=len(rows)),
        )
    except Exception as exc:
        logger.exception("linkedin-app get-all-groups failed")
        return LinkedinSheetGroupsResponse(
            success=False,
            message=gsheet.safe_http_message(exc),
            data=None,
        )


@linkedin_app_router.post("/crawl-linkedin-app", response_model=LinkedinAppCrawlBatchResponse)
def linkedin_app_crawl_batch(payload: LinkedinAppCrawlBatchRequest) -> LinkedinAppCrawlBatchResponse:
    """Lặp crawl nhiều nhóm LinkedIn và append bài vào tab ``top_posts``; có nghỉ ngẫu nhiên giữa các nhóm."""

    if not payload.session_id and not payload.email:
        return LinkedinAppCrawlBatchResponse(
            success=False,
            message="Cần ``email`` hoặc ``session_id`` để dùng session LinkedIn đã lưu (POST /login).",
            data=None,
        )

    if not gsheet.spreadsheet_configured():
        return LinkedinAppCrawlBatchResponse(
            success=False,
            message="Google Sheet chưa cấu hình hoặc thiếu file GOOGLE_SERVICE_ACCOUNT_JSON.",
            data=None,
        )

    try:
        headers = gsheet.read_top_post_header_row()
    except Exception as exc:
        logger.warning("Không đọc được tiêu đề top_posts: %s", exc)
        return LinkedinAppCrawlBatchResponse(
            success=False,
            message=gsheet.safe_http_message(exc),
            data=None,
        )

    gmin = payload.group_delay_min_sec
    gmax = payload.group_delay_max_sec
    if gmin is None:
        gmin = settings.crawl_batch_group_delay_min_sec
    if gmax is None:
        gmax = settings.crawl_batch_group_delay_max_sec
    gmin_f = float(min(gmin, gmax))
    gmax_f = float(max(gmin, gmax))

    scroll_min_ms = (
        int(payload.scroll_delay_min_sec * 1000) if payload.scroll_delay_min_sec is not None else None
    )
    scroll_max_ms = (
        int(payload.scroll_delay_max_sec * 1000) if payload.scroll_delay_max_sec is not None else None
    )

    results: list[LinkedinAppCrawlGroupResult] = []

    for index, url in enumerate(payload.group_urls):
        if index > 0 and gmax_f > 0:
            delay_sec = random.uniform(gmin_f, gmax_f)
            logger.info("linkedin-app crawl: chờ %.2fs trước khi sang nhóm tiếp theo", delay_sec)
            time.sleep(delay_sec)

        try:
            crawl_result = open_group_and_collect_posts(
                session_id=payload.session_id,
                email=payload.email,
                group_url=url,
                max_items=payload.max_items,
                scroll_times_override=payload.scroll_times,
                scroll_delay_min_ms=scroll_min_ms,
                scroll_delay_max_ms=scroll_max_ms,
            )

            filtered_posts, target_day_resolved = enrich_and_filter_posts(
                posts=list(crawl_result["posts"]),
                target_date=payload.target_date,
                crawl_time=crawl_result["crawl_time"],
            )

            crawl_day_label = crawl_result["crawl_time"].strftime("%Y-%m-%d")

            if filtered_posts:
                top_one = pick_top_post(filtered_posts)
                posts_to_write = [] if top_one is None else [top_one]
                detail_msg = (
                    f"Đã ghi top 1 bài của ngày {target_day_resolved.isoformat()}"
                    if posts_to_write
                    else "Không chọn được bài top trong tập lọc theo ngày"
                )
            else:
                posts_to_write = select_most_recent_posts(
                    list(crawl_result["posts"]),
                    limit=payload.fallback_recent_count,
                )
                detail_msg = (
                    f"Không có bài nào thuộc ngày {target_day_resolved.isoformat()}, "
                    f"ghi {len(posts_to_write)} bài gần nhất trong feed đã scrape"
                )

            batch_rows = [
                gsheet.build_top_post_row_values(
                    headers,
                    email_crawl=payload.email_crawl,
                    crawl_date=crawl_day_label,
                    group_name=str(crawl_result.get("group_name") or ""),
                    group_url=str(crawl_result.get("group_url") or url),
                    total_posts_in_run=int(crawl_result.get("total_posts_scraped") or 0),
                    post=post_item,
                )
                for post_item in posts_to_write
            ]

            if batch_rows:
                gsheet.append_top_post_rows(batch_rows)

            if payload.mark_group_done:
                try:
                    updated = gsheet.update_group_status_by_url(url, "done")
                    if not updated:
                        detail_msg = f"{detail_msg} (chưa ghi Trạng thái=done — kiểm tra tab URL nhóm / GOOGLE_SHEET_GROUP_URLS_TAB)."
                except Exception as status_exc:
                    logger.warning("Cập nhật Trạng thái sheet thất bại: %s", status_exc)
                    detail_msg = f"{detail_msg} (lỗi cập nhật Trạng thái: {gsheet.safe_http_message(status_exc)})"

            results.append(
                LinkedinAppCrawlGroupResult(
                    group_url=url,
                    success=True,
                    message=detail_msg,
                    posts_appended=len(batch_rows),
                ),
            )
        except Exception as exc:
            logger.exception("linkedin-app crawl thất bại cho %s", url)
            results.append(
                LinkedinAppCrawlGroupResult(
                    group_url=url,
                    success=False,
                    message=gsheet.safe_http_message(exc),
                    posts_appended=0,
                ),
            )

    all_ok = all(item.success for item in results)
    return LinkedinAppCrawlBatchResponse(
        success=all_ok,
        message="Hoàn thành batch crawl" if all_ok else "Một hoặc nhiều nhóm crawl lỗi",
        data=LinkedinAppCrawlBatchData(
            results=results,
            spreadsheet_id=settings.google_spreadsheet_id,
        ),
    )
