"""API routes for LinkedIn group crawler."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta, timezone
import json
import random
import re
import time
from typing_extensions import Annotated

import httpx
from playwright.sync_api import sync_playwright
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, status

from app.core.config import BASE_DIR, Settings, settings
from app.modules.linkedin.schemas.request_models import (
    AddMemberRequest,
    AddListGroupRequest,
    AssignKpiRequest,
    CheckPermissionRequest,
    CrawlGroupRequest,
    EnsureProfileSlugRequest,
    FilterDataRequest,
    GetAllKpiRequest,
    GetAllPostsRequest,
    GetKpiByEmailRequest,
    GetMyProfileSlugRequest,
    GetProfilesRequest,
    LinkedinAppCrawlBatchRequest,
    LinkedinAppFilterPostsSheetRequest,
    LinkedinAppGetAllPostsSheetRequest,
    LinkedinAppStatsRequest,
    LoginRequest,
    N8nAddGroupRequest,
    N8nCredentialWebhookRequest,
    N8nGetAllGroupsRequest,
    N8nGetSheetLinkRequest,
    N8nRemoveGroupRequest,
    N8nUpdateGroupRequest,
    N8nWebhookPassthroughRequest,
    ProfileSlugSheetCheckRequest,
    StartWorkflowRequest,
    SyncAllProgressRequest,
    SyncPostProgressRequest,
    UpdateProfileSlugRequest,
    VerifyLeaderCodeRequest,
    VerifyLoginRequest,
)
from app.modules.linkedin.schemas.response_models import (
    BaseResponse,
    AddMemberResponse,
    BulkGroupImportData,
    BulkGroupImportResponse,
    BulkGroupImportScrapedItem,
    CheckPermissionResponse,
    CheckPermissionData,
    CrawlDataResponse,
    CrawlResponse,
    EnsureProfileSlugData,
    EnsureProfileSlugResponse,
    FilterDataResponse,
    GetAllKpiResponse,
    KpiMemberData,
    GetAllPostsResponse,
    GetKpiByEmailResponse,
    LinkedinAppCrawlBatchData,
    LinkedinAppCrawlBatchResponse,
    LinkedinAppCrawlGroupResult,
    LinkedinAppStatsData,
    LinkedinAppStatsResponse,
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
    ProfileSlugData,
    ProfileSlugResponse,
    ProfileSlugSheetCheckData,
    ProfileSlugSheetCheckResponse,
    TopPostResponse,
    SyncAllProgressData,
    SyncAllProgressResponse,
    SyncPostProgressData,
    SyncPostProgressResponse,
    VerifyLoginResponse,
)
from app.modules.linkedin.services.auth_service import (
    PendingLoginSessionNotFoundError,
    build_session_state_path,
    login_and_save_session,
    verify_pending_login_otp,
)
from app.modules.linkedin.services.linkedin_engagement_session import ensure_linkedin_session_for_engagement
from app.modules.linkedin.services.crawler_service import open_group_and_collect_posts
from app.modules.linkedin.services.group_bulk_import_service import bulk_scrape_groups
from app.modules.linkedin.services.profile_slug_sheet_service import (
    check_email_in_profile_slug_sheet,
    extract_profile_slug_hint,
    fetch_sheet_rows_via_webhook,
    register_profile_slug_via_webhook,
)
from app.modules.linkedin.services.profile_slug_service import get_my_profile_slug
from app.modules.linkedin.services.post_comment_sync_service import (
    apply_comments_to_sheet_rows,
    build_comment_action_record,
)
from app.modules.linkedin.services.post_reaction_sync_service import (
    apply_reaction_to_sheet_rows,
    build_reaction_action_record,
    fetch_posts_for_email_via_n8n,
    send_sheet_rows_overwrite_webhook,
)
from app.shared.services.n8n_webhook_service import (
    _post_with_retry,
    extract_sheet_link_from_n8n_response_body,
    fetch_sheet_link_via_n8n_webhook,
    post_json_to_n8n_webhook,
    push_credentials_to_n8n_webhook,
    push_start_to_n8n_webhook,
)
from app.modules.linkedin.services.sync_progress_service import (
    sync_post_engagement,
    sync_post_engagement_on_page,
)

from app.shared.services import google_sheet_service as gsheet
from app.modules.linkedin.services.n8n_post_filter_service import (
    build_crawl_sessions_from_posts,
    filter_posts_by_inclusive_date_range,
    normalize_n8n_posts,
    posts_from_n8n_payload,
)
from app.modules.linkedin.services.ranking_service import (
    enrich_and_filter_posts,
    pick_top_post,
    select_most_recent_posts,
)
from app.core.logger import get_logger
from app.modules.linkedin.utils.webhook_payload_keys import (
    enrich_webhook_sheet_metrics,
    merge_sheet_row_into_webhook_body,
    sync_webhook_body_row_number_aliases,
    update_metrics_from_sync,
)
from app.modules.linkedin.utils.post_reaction_webhook_ack import evaluate_post_reaction_webhook_response
from app.modules.linkedin.utils.webhook_payload_sanitize import sanitize_webhook_payload


router = APIRouter(
    prefix="/api/linkedin",
    tags=["LinkedIn"],
)
logger = get_logger(__name__)


def _state_path_for_response(state_path) -> str:
    """Return a user-friendly state path for API responses."""

    try:
        return state_path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(state_path)


def _compute_filter_date_window(payload: FilterDataRequest) -> Tuple[Optional[date], Optional[date]]:
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


def _crawl_id_session_prefix(email: Optional[str], session_id: Optional[str], resolved_linkedin_session_id: str) -> str:
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


def _extract_webhook_message_and_payload(raw_preview: str) -> Tuple[Optional[str], Any]:
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


def get_settings() -> Settings:
    """Dependency to get application settings."""
    return settings


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
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
            playwright_pool_size=settings.playwright_pool_size,
            playwright_persist_session_on_use=settings.playwright_persist_session_on_use,
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
            n8n_webhook_get_profile_slugs_configured=bool(
                (settings.n8n_webhook_get_profile_slugs_url or "").strip(),
            ),
            n8n_webhook_add_profile_slug_configured=bool(
                (settings.n8n_webhook_add_profile_slug_url or "").strip(),
            ),
            n8n_webhook_post_reaction_configured=bool(
                (settings.n8n_webhook_post_reaction_url or "").strip(),
            ),
            n8n_webhook_post_comment_configured=bool(
                (settings.n8n_webhook_post_comment_url or "").strip(),
            ),
            n8n_webhook_assign_kpi_configured=bool(
                (settings.n8n_webhook_assign_kpi_url or "").strip(),
            ),
            n8n_webhook_check_permission_configured=bool(
                (settings.n8n_webhook_check_permission_url or "").strip(),
            ),
            google_sheet_configured=gsheet.spreadsheet_configured(),
        ),
    )


def _pool_prime_fields(pool_prime: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    if not pool_prime:
        return {
            "playwright_pool_primed_workers": None,
            "playwright_pool_workers": None,
        }
    return {
        "playwright_pool_primed_workers": int(pool_prime.get("primed_workers", 0)),
        "playwright_pool_workers": int(pool_prime.get("total_workers", 0)),
    }


def _login_success_message(
    base: str,
    pool_prime: Optional[Dict[str, Any]],
) -> str:
    if not pool_prime:
        return base
    primed = int(pool_prime.get("primed_workers", 0))
    total = int(pool_prime.get("total_workers", 0))
    if total <= 0:
        return base
    if primed >= total:
        return (
            f"{base} Đã nạp session lên {primed}/{total} browser pool — "
            "react/comment không cần đăng nhập lại trên từng worker."
        )
    if primed > 0:
        return (
            f"{base} Nạp session pool một phần ({primed}/{total} worker). "
            "Xem log backend; có thể gọi lại POST /login với force_relogin=false."
        )
    return (
        f"{base} Không nạp được session lên pool Playwright — "
        "thử POST /login lại hoặc kiểm tra file storage/session."
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
            prime_pool=payload.prime_pool,
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
        prime_fields = _pool_prime_fields(result.pool_prime)
        return LoginResponse(
            success=True,
            message=_login_success_message(
                "LinkedIn session saved successfully.",
                result.pool_prime,
            ),
            session_id=result.session_id,
            state_path=_state_path_for_response(result.state_path) if result.state_path else None,
            email=result.email,
            login_step="success",
            need_otp=False,
            checkpoint_url=None,
            **prime_fields,
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
        session_id, state_path, email, pool_prime = verify_pending_login_otp(
            pending_session_id=payload.session_id,
            otp_code=payload.otp,
            checkpoint_url=payload.checkpoint_url,
            prime_pool=payload.prime_pool,
        )
        prime_fields = _pool_prime_fields(pool_prime)
        return VerifyLoginResponse(
            success=True,
            message=_login_success_message(
                "Xác minh OTP thành công. Session LinkedIn đã được lưu.",
                pool_prime,
            ),
            session_id=session_id,
            state_path=_state_path_for_response(state_path),
            email=email,
            login_step="success",
            need_otp=False,
            checkpoint_url=None,
            **prime_fields,
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


@router.post(
    "/me/profile-slug",
    response_model=ProfileSlugResponse,
    dependencies=[Depends(verify_api_key)],
)
def linkedin_me_profile_slug(payload: GetMyProfileSlugRequest) -> ProfileSlugResponse:
    """Vào feed → nút Me/Tôi → link View profile → trả slug ``/in/<slug>``."""

    try:
        normalized_session_id, slug, profile_url = get_my_profile_slug(
            session_id=payload.session_id,
            email=payload.email,
        )
        return ProfileSlugResponse(
            success=True,
            message="Đã lấy profile slug.",
            data=ProfileSlugData(
                profile_slug=slug,
                profile_url=profile_url,
                session_id=normalized_session_id,
            ),
        )
    except FileNotFoundError as exc:
        return ProfileSlugResponse(success=False, message=str(exc), data=None)
    except RuntimeError as exc:
        return ProfileSlugResponse(success=False, message=str(exc), data=None)
    except ValueError as exc:
        return ProfileSlugResponse(success=False, message=str(exc), data=None)
    except Exception as exc:
        logger.exception("linkedin/me/profile-slug failed")
        return ProfileSlugResponse(success=False, message=str(exc), data=None)



@router.post(
    "/me/profile-slug-sheet-check",
    response_model=ProfileSlugSheetCheckResponse,
    dependencies=[Depends(verify_api_key)],
)
def linkedin_me_profile_slug_sheet_check(
    payload: ProfileSlugSheetCheckRequest,
) -> ProfileSlugSheetCheckResponse:
    """POST webhook ``N8N_WEBHOOK_GET_PROFILE_SLUGS`` và kiểm tra email đã có trong ``data`` chưa."""

    url = (settings.n8n_webhook_get_profile_slugs_url or "").strip()
    if not url:
        return ProfileSlugSheetCheckResponse(
            success=False,
            message="N8N_WEBHOOK_GET_PROFILE_SLUGS chưa được cấu hình trong .env.",
            data=None,
        )

    try:
        outcome = check_email_in_profile_slug_sheet(payload.email)
    except httpx.RequestError as exc:
        logger.warning("profile-slug-sheet-check webhook lỗi mạng: %s", type(exc).__name__)
        return ProfileSlugSheetCheckResponse(
            success=False,
            message="Không kết nối được tới webhook GET_PROFILE_SLUGS.",
            data=None,
        )
    except Exception as exc:
        logger.exception("profile-slug-sheet-check failed")
        return ProfileSlugSheetCheckResponse(success=False, message=str(exc), data=None)

    ok_http = outcome.http_status < 400
    matched_slug = extract_profile_slug_hint(outcome.matched_row)
    return ProfileSlugSheetCheckResponse(
        success=ok_http,
        message="Đã kiểm tra sheet profile slug."
        if ok_http
        else f"Webhook GET_PROFILE_SLUGS trả HTTP {outcome.http_status}",
        data=ProfileSlugSheetCheckData(
            email_found_in_sheet=outcome.email_found_in_sheet,
            webhook_http_status=outcome.http_status,
            row_count=len(outcome.rows),
            matched_profile_slug=matched_slug,
        ),
    )


@router.post(
    "/me/ensure-profile-slug",
    response_model=EnsureProfileSlugResponse,
    dependencies=[Depends(verify_api_key)],
)
def linkedin_me_ensure_profile_slug(payload: EnsureProfileSlugRequest) -> EnsureProfileSlugResponse:
    """Sheet có email → bỏ qua; không có → cào slug trên feed + POST ``N8N_WEBHOOK_ADD_PROFILE_SLUG``."""

    owner_email = payload.email.strip()
    sheet_url_configured = bool((settings.n8n_webhook_get_profile_slugs_url or "").strip())

    if sheet_url_configured:
        try:
            outcome = check_email_in_profile_slug_sheet(owner_email)
        except httpx.RequestError:
            return EnsureProfileSlugResponse(
                success=False,
                message="Không kết nối được tới webhook GET_PROFILE_SLUGS.",
                data=None,
            )
        except Exception as exc:
            logger.exception("ensure-profile-slug sheet check failed")
            return EnsureProfileSlugResponse(success=False, message=str(exc), data=None)

        if outcome.http_status >= 400:
            return EnsureProfileSlugResponse(
                success=False,
                message=f"Webhook GET_PROFILE_SLUGS trả HTTP {outcome.http_status}",
                data=EnsureProfileSlugData(
                    sheet_webhook_http_status=outcome.http_status,
                ),
            )

        if outcome.email_found_in_sheet:
            return EnsureProfileSlugResponse(
                success=True,
                message="Email đã có trong sheet — không lấy slug và không gọi add profile slug.",
                data=EnsureProfileSlugData(
                    email_found_in_sheet=True,
                    skipped_playwright=True,
                    skipped_register_webhook=True,
                    sheet_webhook_http_status=outcome.http_status,
                ),
            )

    try:
        _, slug, profile_url = get_my_profile_slug(
            session_id=payload.session_id,
            email=owner_email,
        )
    except FileNotFoundError as exc:
        return EnsureProfileSlugResponse(success=False, message=str(exc), data=None)
    except RuntimeError as exc:
        return EnsureProfileSlugResponse(success=False, message=str(exc), data=None)
    except ValueError as exc:
        return EnsureProfileSlugResponse(success=False, message=str(exc), data=None)
    except Exception as exc:
        logger.exception("ensure-profile-slug playwright failed")
        return EnsureProfileSlugResponse(success=False, message=str(exc), data=None)

    add_url = (settings.n8n_webhook_add_profile_slug_url or "").strip()
    if not add_url:
        return EnsureProfileSlugResponse(
            success=True,
            message="Đã lấy profile slug (Playwright). Chưa cấu hình N8N_WEBHOOK_ADD_PROFILE_SLUG — bỏ qua ghi sheet.",
            data=EnsureProfileSlugData(
                email_found_in_sheet=False,
                skipped_register_webhook=True,
                sheet_check_skipped_no_webhook=not sheet_url_configured,
                profile_slug=slug,
                profile_url=profile_url,
            ),
        )

    try:
        reg_status, _parsed, _preview = register_profile_slug_via_webhook(
            webhook_url=add_url,
            email=owner_email,
            profile_slug=slug,
            profile_url=profile_url,
            timeout_sec=float(settings.n8n_webhook_add_profile_slug_timeout_sec),
        )
    except httpx.RequestError:
        return EnsureProfileSlugResponse(
            success=False,
            message="Không kết nối được tới webhook ADD_PROFILE_SLUG.",
            data=EnsureProfileSlugData(
                profile_slug=slug,
                profile_url=profile_url,
                sheet_check_skipped_no_webhook=not sheet_url_configured,
            ),
        )
    except Exception as exc:
        logger.exception("ensure-profile-slug register webhook failed")
        return EnsureProfileSlugResponse(
            success=False,
            message=str(exc),
            data=EnsureProfileSlugData(
                profile_slug=slug,
                profile_url=profile_url,
                sheet_check_skipped_no_webhook=not sheet_url_configured,
            ),
        )

    register_ok = reg_status < 400
    return EnsureProfileSlugResponse(
        success=register_ok,
        message="Đã đăng ký profile slug qua webhook."
        if register_ok
        else f"Webhook ADD_PROFILE_SLUG trả HTTP {reg_status}",
        data=EnsureProfileSlugData(
            email_found_in_sheet=False,
            profile_slug=slug,
            profile_url=profile_url,
            register_webhook_called=True,
            register_webhook_http_status=reg_status,
            sheet_check_skipped_no_webhook=not sheet_url_configured,
        ),
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


def _truncate_webhook_preview(raw: str, limit: int = 512) -> str:
    text = (raw or "").strip()
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def _resolve_crawler_email_for_n8n_groups(
    *,
    body_email: Optional[str],
    email_crawl: Optional[str] = None,
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


def _pick_n8n_message(parsed: Any) -> Optional[str]:
    """Lấy message từ JSON trả về của node Respond to Webhook (nếu có)."""

    if isinstance(parsed, dict):
        for key in ("message", "msg", "detail"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _resolve_bulk_add_group_email(
    *,
    body_email: Optional[str],
    email_crawl: Optional[str] = None,
) -> Optional[str]:
    """Ưu tiên cookie ``email_crawl``; fallback ``body.email``; thiếu cả hai vẫn cho phép."""

    merged = ((email_crawl or "").strip() or (body_email or "").strip())
    return merged or None


def _bulk_add_group_webhook_email_payload(email: str) -> Dict[str, str]:
    """Giữ alias email nhất quán với các route n8n nhóm khác."""

    e = email.strip()
    return {
        "email": e,
        "Email_crawl": e,
        "userEmail": e,
    }


def _n8n_get_all_groups_webhook_body(email: str) -> Dict[str, Any]:
    """Payload gửi n8n: một email thống nhất (alias) để workflow lọc **tất cả nhóm** theo owner."""

    e = email.strip()
    return {
        "email": e,
        "Email_crawl": e,
        "userEmail": e,
    }


def _pick_group_rows(parsed: Any) -> List[Dict[str, Any]]:
    """Trích mảng dòng nhóm từ JSON n8n.

    Khớp các dạng hay gặp (cùng ``linkedin-crawler-ui/lib/n8n-groups-normalize.ts``):
    mảng thuần; hoặc object có một trong các key ``data`` / ``groups`` / ``rows`` / … là list.
    Nếu ``data`` là object (không phải list), thử đệ quy một lớp (vd. envelope lồng nhau).
    """

    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if not isinstance(parsed, dict):
        return []
    for key in ("data", "groups", "rows", "items", "results", "records"):
        inner = parsed.get(key)
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    nested = parsed.get("data")
    if isinstance(nested, dict) and nested is not parsed:
        return _pick_group_rows(nested)
    return []


def _pick_group_field(item: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if key in item:
            return item.get(key)
    return None


def _normalize_n8n_groups(parsed: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in _pick_group_rows(parsed):
        raw_row = _pick_group_field(item, ("row_number", "rowNumber", "stt", "STT"))
        row_number: Optional[int] = None
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
        raw_type = _pick_group_field(item, ("type", "Loại nhóm", "loai_nhom", "intent"))

        url_group = str(raw_url or "").strip()
        if not url_group:
            continue
        name_group = str(raw_name or "").strip()
        email = str(raw_email or "").strip()
        try:
            member = int(raw_member) if raw_member is not None and str(raw_member).strip() else 0
        except (TypeError, ValueError):
            member = 0

        group_type = str(raw_type or "").strip()

        out.append(
            {
                "row_number": row_number,
                "url_group": url_group,
                "name_group": name_group,
                "email": email,
                "member": max(0, member),
                "type": group_type,
            },
        )
    return out


def _forward_n8n_group_webhook(*, url: str, env_hint: str, json_body: Dict[str, Any]) -> BaseResponse:
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
    email_crawl: Annotated[Optional[str], Cookie()] = None,
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
    email_crawl: Annotated[Optional[str], Cookie()] = None,
) -> BaseResponse:
    """POST ``url_group``, ``name_group``, ``member``, ``email`` tới ``N8N_WEBHOOK_ADD_GROUP``."""

    email = _resolve_crawler_email_for_n8n_groups(
        body_email=payload.email,
        email_crawl=email_crawl,
    )
    return _forward_n8n_group_webhook(
        url=settings.n8n_webhook_add_group_url,
        env_hint="N8N_WEBHOOK_ADD_GROUP",
        json_body=payload.to_webhook_payload(email),
    )


@router.post(
    "/groups/remove",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def n8n_groups_remove(
    payload: N8nRemoveGroupRequest,
    email_crawl: Annotated[Optional[str], Cookie()] = None,
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
    email_crawl: Annotated[Optional[str], Cookie()] = None,
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


@router.post(
    "/groups/add-list-group",
    response_model=BulkGroupImportResponse,
    dependencies=[Depends(verify_api_key)],
)
def add_list_group(
    payload: AddListGroupRequest,
    email_crawl: Annotated[Optional[str], Cookie()] = None,
) -> BulkGroupImportResponse:
    """Cào hàng loạt URL nhóm, sau đó (tuỳ chọn) POST batch sang ``N8N_WEBHOOK_ADD_LIST_GROUP``."""

    owner_email = _resolve_bulk_add_group_email(
        body_email=payload.email,
        email_crawl=email_crawl,
    )

    try:
        scraped_items = bulk_scrape_groups(
            group_urls=payload.group_urls,
            session_id=payload.session_id,
            email=owner_email,
            delay_min_sec=payload.delay_min_sec,
            delay_max_sec=payload.delay_max_sec,
        )
    except Exception as exc:
        logger.exception("add-list-group scrape failed")
        return BulkGroupImportResponse(
            success=False,
            message=f"Cào nhóm thất bại: {exc}",
            data=None,
        )

    response_items = [BulkGroupImportScrapedItem(**item) for item in scraped_items]

    if not payload.post_to_webhook:
        return BulkGroupImportResponse(
            success=True,
            message="Đã cào danh sách nhóm (bỏ qua gửi webhook theo post_to_webhook=false).",
            data=BulkGroupImportData(
                items=response_items,
                webhook_skipped=True,
                webhook_http_status=None,
                webhook_response_preview=None,
                webhook_response=None,
            ),
        )

    if not owner_email:
        return BulkGroupImportResponse(
            success=False,
            message="Thiếu email để gửi webhook add-list-group.",
            data=BulkGroupImportData(
                items=response_items,
                webhook_skipped=True,
            ),
        )

    webhook_url = (settings.n8n_webhook_add_list_group_url or "").strip()
    if not webhook_url:
        return BulkGroupImportResponse(
            success=False,
            message=(
                "N8N_WEBHOOK_ADD_LIST_GROUP chưa được cấu hình trong .env "
                "(hoặc fallback N8N_WEBHOOK_BULK_IMPORT_GROUPS)."
            ),
            data=BulkGroupImportData(
                items=response_items,
                webhook_skipped=True,
            ),
        )

    webhook_timeout = payload.webhook_timeout_sec or float(
        settings.n8n_webhook_add_list_group_timeout_sec,
    )
    items_for_webhook = [
        {
            **item,
            "email": owner_email,
            "Email_crawl": owner_email,
            "userEmail": owner_email,
            "type": payload.type.strip(),
        }
        for item in scraped_items
    ]
    webhook_payload: Dict[str, Any] = {
        **_bulk_add_group_webhook_email_payload(owner_email),
        "items": items_for_webhook,
        "total": len(items_for_webhook),
    }

    try:
        webhook_resp = _post_with_retry(
            url=webhook_url,
            json_body=webhook_payload,
            timeout=max(1.0, float(webhook_timeout)),
        )
        text = (webhook_resp.text or "").strip()
        preview = _truncate_webhook_preview(text)
        parsed: Any = None
        try:
            parsed = webhook_resp.json()
        except Exception:
            parsed = preview

        ok = webhook_resp.status_code < 400
        return BulkGroupImportResponse(
            success=ok,
            message=(
                "Đã cào nhóm và gửi webhook add-list-group thành công."
                if ok
                else f"Webhook add-list-group trả về HTTP {webhook_resp.status_code}"
            ),
            data=BulkGroupImportData(
                items=response_items,
                webhook_http_status=webhook_resp.status_code,
                webhook_response_preview=preview,
                webhook_response=parsed,
                webhook_skipped=False,
            ),
        )
    except httpx.RequestError as exc:
        logger.warning("add-list-group webhook request failed: %s", type(exc).__name__)
        return BulkGroupImportResponse(
            success=False,
            message="Không kết nối được tới webhook add-list-group.",
            data=BulkGroupImportData(
                items=response_items,
                webhook_skipped=False,
            ),
        )
    except Exception as exc:
        logger.exception("add-list-group webhook failed")
        return BulkGroupImportResponse(
            success=False,
            message=f"Gửi webhook add-list-group thất bại: {exc}",
            data=BulkGroupImportData(
                items=response_items,
                webhook_skipped=False,
            ),
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

        webhook_payload: Dict[str, Any] = {"email": payload.email}

        timeout = max(1.0, float(settings.n8n_webhook_timeout_sec))

        response = _post_with_retry(url=url, json_body=webhook_payload, timeout=timeout)

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

        response = _post_with_retry(url=url, json_body=webhook_payload, timeout=timeout)

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


linkedin_app_router = APIRouter(
    prefix="/api/linkedin/app",
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


@linkedin_app_router.post("/stats", response_model=LinkedinAppStatsResponse)
def linkedin_app_stats(payload: LinkedinAppStatsRequest) -> LinkedinAppStatsResponse:
    """Calculate engagement stats for a user based on all posts in sheet."""

    try:
        if not gsheet.spreadsheet_configured():
            return LinkedinAppStatsResponse(
                success=False,
                message="Google Sheet chưa cấu hình.",
                data=None,
            )

        _, rows = gsheet.read_top_posts_as_dicts()
        filtered = gsheet.filter_sheet_top_posts_for_owner(
            rows,
            owner_email_token=payload.email,
        )

        total_comments = 0
        total_interactions = 0
        total_posts = len(filtered)

        for row in filtered:
            # Simple count from row
            comm_count = 0
            for k in ["comment", "Comment", "Da_comment", "Đã bình luận"]:
                if k in row and row[k] and str(row[k]).strip() and str(row[k]).strip().lower() not in ["null", "0", "false", "no"]:
                    # Try to parse as JSON array
                    try:
                        val = row[k]
                        if isinstance(val, str) and val.strip().startswith("["):
                            comm_count = len(json.loads(val))
                        else:
                            comm_count = 1
                    except (json.JSONDecodeError, TypeError, ValueError):
                        comm_count = 1
                    break
            total_comments += comm_count

            # Count interactions
            for k in ["reaction", "Reaction", "tuong_tac", "Tuong_tac"]:
                if k in row and row[k] and str(row[k]).strip() and str(row[k]).strip().lower() not in ["null", "0", "false", "no"]:
                    total_interactions += 1
                    break

        return LinkedinAppStatsResponse(
            success=True,
            message="Đã lấy thông số thống kê.",
            data=LinkedinAppStatsData(
                total_comments=total_comments,
                total_interactions=total_interactions,
                total_posts_crawled=total_posts,
            ),
        )
    except Exception as exc:
        logger.exception("linkedin-app stats failed")
        return LinkedinAppStatsResponse(
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

    results: List[LinkedinAppCrawlGroupResult] = []

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
@router.post(
    "/post/sync-progress",
    response_model=SyncPostProgressResponse,
    dependencies=[Depends(verify_api_key)],
)
def linkedin_post_sync_progress(payload: SyncPostProgressRequest) -> SyncPostProgressResponse:
    """Sync engagement for ONE post."""

    webhook_url = (settings.n8n_webhook_post_reaction_url or "").strip()
    if payload.post_to_webhook and not webhook_url:
        return SyncPostProgressResponse(
            success=False,
            message="post_to_webhook=true nhưng N8N_WEBHOOK_POST_REACTION chưa được cấu hình.",
            data=None,
        )

    pw_email = payload.playwright_resolve_email()
    owner_email = payload.Email_crawl.strip()
    
    try:
        res = sync_post_engagement(
            post_url=payload.post_url,
            profile_slug=payload.profile_slug,
            session_id=payload.session_id,
            email=pw_email,
            timeout_ms=payload.timeout_ms,
            password=payload.password,
            auto_login=payload.auto_login,
        )
    except Exception as exc:
        logger.exception("Sync progress failed")
        return SyncPostProgressResponse(success=False, message=str(exc), data=None)

    # Prepare data for response
    sync_data = SyncPostProgressData(
        post_url=payload.post_url,
        reaction=res.get("reaction"),
        comments=res.get("comments", []),
        total_reactions=res.get("total_reactions", 0),
        total_comments=res.get("total_comments", 0),
        row_number=payload.row_number,
        webhook_called=False,
    )

    if not payload.post_to_webhook:
        return SyncPostProgressResponse(
            success=True,
            message="Đã đọc xong tiến độ trên LinkedIn (bỏ qua webhook).",
            data=sync_data,
        )

    # Send to n8n
    try:
        # Fetch all posts to merge
        all_posts = fetch_posts_for_email_via_n8n(owner_email)
        if not all_posts and payload.sheet_row:
            all_posts = [dict(payload.sheet_row)]

        triggered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Apply reaction
        reaction_kind = res.get("reaction")
        reaction_action = build_reaction_action_record(
            owner_email=owner_email,
            post_url=payload.post_url,
            reaction=reaction_kind or "",
            id_session_crawl=payload.ID_session_crawl,
            row_number=payload.row_number,
            sheet_row=payload.sheet_row,
            clear_reaction=not reaction_kind,
        )
        updated_posts, _ = apply_reaction_to_sheet_rows(
            all_posts,
            action=reaction_action,
            final_url=payload.post_url,
            resolved_playwright_session_id=res.get("session_id", ""),
            playwright_executed=True,
            triggered_at=triggered_at,
        )

        # Apply comments
        comment_action = build_comment_action_record(
            owner_email=owner_email,
            post_url=payload.post_url,
            comments_cell=res.get("comments", []),
            id_session_crawl=payload.ID_session_crawl,
            row_number=payload.row_number,
            sheet_row=payload.sheet_row,
        )
        
        final_posts, matched_count = apply_comments_to_sheet_rows(
            updated_posts,
            action=comment_action,
            final_url=payload.post_url,
            resolved_playwright_session_id=res.get("session_id", ""),
            playwright_executed=True,
        )

        # Update metrics from sync for exact counts
        for row in final_posts:
            update_metrics_from_sync(
                row, 
                res.get("total_reactions", 0), 
                res.get("total_comments", 0)
            )

        # POST to webhook
        synced_count, success_count, http_status, preview = send_sheet_rows_overwrite_webhook(
            webhook_url=webhook_url,
            rows=final_posts,
            matched_row_count=matched_count,
        )
        
        sync_data.webhook_called = True
        sync_data.webhook_http_status = http_status
        sync_data.webhook_response_preview = preview
        
        return SyncPostProgressResponse(
            success=True,
            message=f"Đã làm mới tiến độ cho bài viết ({success_count} dòng Sheet được cập nhật).",
            data=sync_data,
        )
    except Exception as exc:
        logger.exception("Webhook sync failed")
        return SyncPostProgressResponse(
            success=False,
            message=f"Lỗi khi gửi webhook đồng bộ: {exc}",
            data=sync_data,
        )


@router.post(
    "/sync-all-progress",
    response_model=SyncAllProgressResponse,
    dependencies=[Depends(verify_api_key)],
)
def linkedin_sync_all_progress(payload: SyncAllProgressRequest) -> SyncAllProgressResponse:
    """Sync engagement for ALL posts of a user."""

    webhook_url = (settings.n8n_webhook_post_reaction_url or "").strip()
    if not webhook_url:
        return SyncAllProgressResponse(
            success=False,
            message="N8N_WEBHOOK_POST_REACTION chưa được cấu hình.",
            data=None,
        )

    owner_email = payload.email_crawl.strip()
    pw_email = payload.playwright_resolve_email()
    
    # 1. Fetch all posts
    try:
        all_posts = fetch_posts_for_email_via_n8n(owner_email)
    except Exception as exc:
        return SyncAllProgressResponse(success=False, message=f"Không thể lấy danh sách bài viết: {exc}", data=None)

    if not all_posts:
        return SyncAllProgressResponse(success=True, message="Không có bài viết nào để đồng bộ.", data=SyncAllProgressData(posts_attempted=0, posts_succeeded=0, details=[]))

    # 2. Filter posts with URLs
    posts_to_sync = []
    for row in all_posts:
        url = (row.get("URL_Bài_Viết") or row.get("post_url") or row.get("postUrl") or "").strip()
        if url:
            posts_to_sync.append(row)
    
    if payload.limit_posts:
        posts_to_sync = posts_to_sync[:payload.limit_posts]

    if not posts_to_sync:
        return SyncAllProgressResponse(success=True, message="Không tìm thấy bài viết có URL để đồng bộ.", data=SyncAllProgressData(posts_attempted=0, posts_succeeded=0, details=[]))

    # 3. Resolve session
    try:
        if payload.auto_login:
            resolved_sid, state_path = ensure_linkedin_session_for_engagement(
                email=pw_email,
                session_id=payload.session_id,
                password=payload.password,
            )
        else:
            resolved_sid, state_path = build_session_state_path(
                session_id=payload.session_id,
                email=pw_email,
            )
            if not state_path.is_file():
                raise FileNotFoundError(f"Session not found at {state_path}")
    except Exception as exc:
        return SyncAllProgressResponse(success=False, message=f"Lỗi session: {exc}", data=None)

    results_details = []
    success_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless, args=["--no-sandbox"])
        try:
            context = browser.new_context(storage_state=str(state_path))
            page = context.new_page()
            page.set_default_timeout(payload.timeout_ms_per_post)
            
            for row in posts_to_sync:
                url = (row.get("URL_Bài_Viết") or row.get("post_url") or row.get("postUrl") or "").strip()
                row_num = row.get("row_number") or row.get("rowNumber")
                id_session = row.get("ID_session_crawl") or row.get("id_session_crawl")
                
                # Sync logic
                res = sync_post_engagement_on_page(page, url, payload.profile_slug, payload.timeout_ms_per_post)
                
                detail = SyncPostProgressData(
                    post_url=url,
                    reaction=res.get("reaction"),
                    comments=res.get("comments", []),
                    total_reactions=res.get("total_reactions", 0),
                    total_comments=res.get("total_comments", 0),
                    row_number=row_num,
                    webhook_called=False,
                )
                
                if res.get("error"):
                    results_details.append(detail)
                    continue

                # Apply to all_posts (stateful update)
                triggered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                
                # Apply reaction
                reaction_kind = res.get("reaction")
                reaction_action = build_reaction_action_record(
                    owner_email=owner_email,
                    post_url=url,
                    reaction=reaction_kind or "",
                    id_session_crawl=id_session or "",
                    row_number=row_num or 0,
                    sheet_row=row,
                    clear_reaction=not reaction_kind,
                )
                all_posts, _ = apply_reaction_to_sheet_rows(
                    all_posts,
                    action=reaction_action,
                    final_url=url,
                    resolved_playwright_session_id=resolved_sid,
                    playwright_executed=True,
                    triggered_at=triggered_at,
                )

                # Apply comments
                comment_action = build_comment_action_record(
                    owner_email=owner_email,
                    post_url=url,
                    comments_cell=res.get("comments", []),
                    id_session_crawl=id_session or "",
                    row_number=row_num or 0,
                    sheet_row=row,
                )
                
                all_posts, _ = apply_comments_to_sheet_rows(
                    all_posts,
                    action=comment_action,
                    final_url=url,
                    resolved_playwright_session_id=resolved_sid,
                    playwright_executed=True,
                )
                
                # Update metrics for current post in all_posts
                for row_item in all_posts:
                    row_url = (row_item.get("URL_Bài_Viết") or row_item.get("post_url") or row_item.get("postUrl") or "").strip()
                    if row_url == url:
                        update_metrics_from_sync(
                            row_item,
                            res.get("total_reactions", 0),
                            res.get("total_comments", 0)
                        )
                
                detail.webhook_called = True
                results_details.append(detail)
                success_count += 1
            
            # 4. Final webhook call to update sheet for ALL synced posts
            if success_count > 0:
                _, _, status_code, preview = send_sheet_rows_overwrite_webhook(
                    webhook_url=webhook_url,
                    rows=all_posts,
                    matched_row_count=success_count,
                )
                for d in results_details:
                    if d.webhook_called:
                        d.webhook_http_status = status_code
                        d.webhook_response_preview = preview

            return SyncAllProgressResponse(
                success=True,
                message=f"Đã hoàn thành làm mới tiến độ ({success_count}/{len(posts_to_sync)} bài viết).",
                data=SyncAllProgressData(
                    posts_attempted=len(posts_to_sync),
                    posts_succeeded=success_count,
                    details=results_details
                )
            )
        finally:
            browser.close()

@router.post(
    "/kpi/assign",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def linkedin_assign_kpi(payload: AssignKpiRequest) -> BaseResponse:
    """Leader gán KPI cho member — Forward JSON tới ``N8N_WEBHOOK_ASSIGN_KPI``."""

    if payload.leader_role != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ leader mới có quyền gán KPI.",
        )

    webhook_url = settings.n8n_webhook_assign_kpi_url
    if not webhook_url:
        return BaseResponse(
            success=False,
            message="N8N_WEBHOOK_ASSIGN_KPI chưa được cấu hình trong .env.",
        )

    try:
        # Chuyển đổi sang dict, sử dụng alias để khớp key frontend/n8n mong đợi
        json_body = payload.model_dump(mode="json", by_alias=True)
        
        status_code, response_text = post_json_to_n8n_webhook(
            url=webhook_url,
            json_body=json_body,
        )
        
        return BaseResponse(
            success=True,
            message=f"Đã gán KPI và gửi tới n8n thành công (Status: {status_code}).",
            data={
                "webhook_status": status_code,
                "response_preview": response_text[:200]
            }
        )
    except Exception as exc:
        logger.exception("KPI assignment webhook failed")
        return BaseResponse(
            success=False,
            message=f"Lỗi khi gửi KPI tới n8n: {exc}",
        )


@router.post(
    "/auth/check-permission",
    response_model=CheckPermissionResponse,
    dependencies=[Depends(verify_api_key)],
)
def check_permission(payload: CheckPermissionRequest) -> CheckPermissionResponse:
    """Kiểm tra quyền leader/member qua webhook n8n."""

    webhook_url = settings.n8n_webhook_check_permission_url
    if not webhook_url:
        return CheckPermissionResponse(
            success=False,
            message="N8N_CHECK_PERMISSION chưa được cấu hình trong .env.",
            data=CheckPermissionData(permission=False),
        )

    try:
        status_code, response_text = post_json_to_n8n_webhook(
            url=webhook_url,
            json_body={"email": payload.email},
        )

        permission = False
        try:
            resp_data = json.loads(response_text)
            if isinstance(resp_data, dict):
                permission = bool(resp_data.get("permission", False))
            elif isinstance(resp_data, list) and len(resp_data) > 0:
                # Trường hợp n8n trả về mảng
                first = resp_data[0]
                if isinstance(first, dict):
                    permission = bool(first.get("permission", False))
        except json.JSONDecodeError:
            pass

        return CheckPermissionResponse(
            success=True,
            message="Checked permission successfully",
            data=CheckPermissionData(permission=permission),
        )
    except Exception as exc:
        logger.exception("Check permission webhook failed")
        return CheckPermissionResponse(
            success=False,
            message=f"Lỗi khi kiểm tra quyền: {exc}",
            data=CheckPermissionData(permission=False),
        )


def _norm_header_key(key: str) -> str:
    """Chuẩn hóa key sheet/n8n để lookup không phân biệt hoa thường, khoảng trắng, BOM."""
    s = str(key).replace("\ufeff", "").strip().lower()
    return "".join(ch for ch in s if ch not in " \t\n\r-_")


def _row_get_ci(row: Dict[str, Any], *logical_names: str) -> Any:
    """Lấy giá trị theo tên cột tương đương (Google Sheet / n8n đổi tên cột)."""
    idx: Dict[str, Any] = {}
    for k, v in row.items():
        nk = _norm_header_key(str(k))
        if nk not in idx:
            idx[nk] = v
    for name in logical_names:
        nk = _norm_header_key(name)
        if nk in idx:
            return idx[nk]
    return None


def _unwrap_n8n_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """Một item n8n thường là ``{ \"json\": { ...dòng sheet... } }``."""
    inner = item.get("json")
    if isinstance(inner, dict):
        return inner
    return item


def _row_looks_like_profile(row: Dict[str, Any]) -> bool:
    email = str(_row_get_ci(row, "email", "Email", "Email_crawl", "email_crawl", "userEmail", "mail") or "").strip()
    return bool(email and "@" in email)


def _coerce_payload_to_row_dicts(parsed: Any) -> List[Dict[str, Any]]:
    """Đệ quy / đa dạng format: list, ``{data:[]}``, n8n ``[{json:{}}]``, dict index→row."""
    if parsed is None:
        return []
    if isinstance(parsed, str) and parsed.strip():
        try:
            return _coerce_payload_to_row_dicts(json.loads(parsed))
        except Exception:
            return []
    if isinstance(parsed, list):
        out: List[Dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            row = _unwrap_n8n_row(item)
            if isinstance(row, dict) and _row_looks_like_profile(row):
                out.append(row)
        return out
    if isinstance(parsed, dict):
        # n8n đôi khi trả một object bọc json
        inner_json = parsed.get("json")
        if isinstance(inner_json, dict) and _row_looks_like_profile(inner_json):
            return [inner_json]
        for key in ("data", "rows", "records", "items", "results", "output"):
            inner = parsed.get(key)
            if inner is not None:
                got = _coerce_payload_to_row_dicts(inner)
                if got:
                    return got
        if _row_looks_like_profile(parsed):
            return [parsed]
        # { "0": {...}, "1": {...} }
        dict_rows = [
            v
            for v in parsed.values()
            if isinstance(v, dict) and _row_looks_like_profile(v)
        ]
        if dict_rows:
            return dict_rows
    return []


def _parse_get_all_kpi_rows(response_text: str) -> List[Dict[str, Any]]:
    """Chuẩn hóa n8n / Google Sheet → list dict dòng profile."""
    try:
        parsed = json.loads(response_text)
    except Exception:
        return []
    return _coerce_payload_to_row_dicts(parsed)


def _normalize_kpi_member_row(
    row: Dict[str, Any],
    leader_email: str,
    *,
    require_leader_match: bool = True,
) -> Optional[KpiMemberData]:
    """Map dòng sheet → ``KpiMemberData``.

    ``require_leader_match=True`` (get-all): lọc theo ``email_leader`` trùng leader gọi API.
    ``require_leader_match=False`` (get-by-email): giữ nguyên dòng n8n, không lọc leader.
    """
    email = str(
        _row_get_ci(row, "email", "Email", "Email_crawl", "email_crawl", "userEmail", "mail", "EMAIL")
        or "",
    ).strip()
    if not email:
        return None

    row_leader = str(
        _row_get_ci(
            row,
            "email_leader",
            "emailLeader",
            "leader_email",
            "Leader_email",
            "email_leader_crawl",
            "Leader",
            "leaderEmail",
            "Email_leader",
            "EMAIL_LEADER",
        )
        or "",
    ).strip().lower()

    if require_leader_match:
        leader_norm = leader_email.strip().lower()
        if not leader_norm:
            return None
        if row_leader and row_leader != leader_norm:
            return None
        effective_leader: Optional[str] = row_leader or leader_norm
    else:
        leader_norm = ""
        effective_leader = row_leader or None

    role = str(_row_get_ci(row, "role", "Role", "member_role", "memberRole") or "member").strip() or "member"
    if require_leader_match and role.lower() == "leader" and email.strip().lower() == leader_norm:
        return None

    slug_raw = _row_get_ci(row, "profile_slug", "profileSlug", "slug", "Profile_slug")
    slug_s = str(slug_raw).strip() if slug_raw is not None else ""

    kpi_raw = _row_get_ci(row, "kpi", "KPI", "Kpi")
    kpi_list = _parse_kpi_field_to_dict_list(kpi_raw)

    return KpiMemberData(
        email=email,
        role=role,
        profile_slug=slug_s or None,
        email_leader=effective_leader,
        kpi=kpi_list,
    )


def _parse_kpi_field_to_dict_list(raw: Any) -> List[Dict[str, Any]]:
    """Sheet/n8n hay trả ``kpi`` là JSON string hoặc một object — ép về ``List[dict]`` cho Pydantic."""
    out: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for el in raw:
            if isinstance(el, dict):
                out.append(el)
        return out
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            return []
        if isinstance(loaded, list):
            for el in loaded:
                if isinstance(el, dict):
                    out.append(el)
        elif isinstance(loaded, dict):
            out = [loaded]
    return out


@router.post(
    "/kpi/get-all",
    response_model=GetAllKpiResponse,
    dependencies=[Depends(verify_api_key)],
)
def get_all_kpi(payload: GetAllKpiRequest) -> GetAllKpiResponse:
    """Lấy toàn bộ KPI cho leader qua n8n; chuẩn hóa alias cột và lọc theo ``email_leader``."""
    webhook_url = settings.n8n_webhook_get_all_kpi_url
    if not webhook_url:
        return GetAllKpiResponse(success=False, message="Webhook get-all-kpi chưa cấu hình.")

    leader = payload.email_leader.strip()
    if not leader:
        return GetAllKpiResponse(success=False, message="email_leader không hợp lệ.")

    try:
        _status_code, response_text = post_json_to_n8n_webhook(
            url=webhook_url,
            json_body={"email_leader": leader},
        )
        raw_rows = _parse_get_all_kpi_rows(response_text)
        normalized: List[KpiMemberData] = []
        for item in raw_rows:
            mem = _normalize_kpi_member_row(item, leader)
            if mem is not None:
                normalized.append(mem)

        return GetAllKpiResponse(
            success=True,
            message="Success",
            total=len(normalized),
            data=normalized,
        )
    except Exception as exc:
        logger.exception("get_all_kpi failed")
        return GetAllKpiResponse(success=False, message=str(exc))


@router.post(
    "/kpi/get-by-email",
    response_model=GetKpiByEmailResponse,
    dependencies=[Depends(verify_api_key)],
)
def get_kpi_by_email(payload: GetKpiByEmailRequest) -> GetKpiByEmailResponse:
    """Lấy KPI cho member qua n8n."""
    webhook_url = settings.n8n_webhook_get_kpi_by_email_url
    if not webhook_url:
        return GetKpiByEmailResponse(success=False, message="Webhook get-kpi-by-email chưa cấu hình.")

    try:
        _status_code, response_text = post_json_to_n8n_webhook(
            url=webhook_url,
            json_body={"email": payload.email},
        )
        parsed = json.loads(response_text)
        raw_rows = _coerce_payload_to_row_dicts(parsed)
        normalized: List[KpiMemberData] = []
        for item in raw_rows:
            mem = _normalize_kpi_member_row(
                item,
                "",
                require_leader_match=False,
            )
            if mem is not None:
                normalized.append(mem)

        return GetKpiByEmailResponse(
            success=True,
            message="Success",
            total=len(normalized),
            data=normalized,
        )
    except Exception as exc:
        return GetKpiByEmailResponse(success=False, message=str(exc))


@router.post(
    "/team/add-member",
    response_model=AddMemberResponse,
    dependencies=[Depends(verify_api_key)],
)
def add_member(payload: AddMemberRequest) -> AddMemberResponse:
    """Thêm member mới qua n8n."""
    webhook_url = settings.n8n_webhook_add_member_url
    if not webhook_url:
        return AddMemberResponse(
            success=False,
            allowAdd=False,
            code="CONFIG_ERROR",
            message="Webhook add-member chưa cấu hình.",
        )

    try:
        status_code, response_text = post_json_to_n8n_webhook(
            url=webhook_url,
            json_body={
                "email": payload.email_member,
                "email_leader": payload.email_leader
            },
        )
        
        # Parse the JSON response returned from the n8n webhook
        res_json = {}
        if response_text and response_text.strip():
            try:
                res_json = json.loads(response_text)
            except Exception:
                pass

        if isinstance(res_json, dict):
            # Parse structure matching the n8n webhook success/failed schema
            success = res_json.get("success", status_code < 400)
            allow_add = res_json.get("allowAdd", success)
            code = res_json.get("code", "ADD_MEMBER_SUCCESS" if success else "ADD_MEMBER_FAILED")
            message = res_json.get("message", "Thêm thành viên thành công." if success else "Thêm thành viên thất bại.")
            data = res_json.get("data", None)

            return AddMemberResponse(
                success=success,
                allowAdd=allow_add,
                code=code,
                message=message,
                data=data
            )
        
        # Fallback if webhook returned non-JSON payload
        success_status = status_code < 400
        return AddMemberResponse(
            success=success_status,
            allowAdd=success_status,
            code="ADD_MEMBER_SUCCESS" if success_status else "ADD_MEMBER_FAILED",
            message=f"Đã gửi yêu cầu thêm member (Status: {status_code}). Response: {response_text}",
            data={
                "email": payload.email_member,
                "email_leader": payload.email_leader
            }
        )
    except Exception as exc:
        return AddMemberResponse(
            success=False,
            allowAdd=False,
            code="EXCEPTION_ERROR",
            message=str(exc),
        )


@router.post(
    "/auth/verify-leader-code",
    response_model=BaseResponse,
    dependencies=[Depends(verify_api_key)],
)
def verify_leader_code(payload: VerifyLeaderCodeRequest) -> BaseResponse:
    """Xác nhận mã code leader."""
    if payload.code == settings.leader_code:
        return BaseResponse(success=True, message="Mã code chính xác.")
    return BaseResponse(success=False, message="Mã code không đúng.")
@router.post("/all-profiles")
def get_all_profiles(
    payload: GetProfilesRequest,
    settings: Settings = Depends(get_settings),
    api_key: str = Depends(verify_api_key),
):
    """Lấy danh sách toàn bộ profile slug từ sheet qua n8n."""
    try:
        status_code, rows, parsed, preview = fetch_sheet_rows_via_webhook(
            webhook_url=settings.n8n_webhook_get_profile_slugs_url,
            email=payload.email,
            timeout_sec=settings.n8n_webhook_get_profile_slugs_timeout_sec,
        )
        if status_code != 200:
            return {"success": False, "message": f"N8N trả về lỗi: {status_code}", "data": None}
        
        return {"success": True, "message": "Lấy danh sách profile thành công", "data": rows}
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}

@router.post("/me/profile-slug-update")
def update_profile_slug_endpoint(
    payload: UpdateProfileSlugRequest,
    settings: Settings = Depends(get_settings),
    api_key: str = Depends(verify_api_key),
):
    """Ghi đè/Thêm mới profile slug vào sheet kèm KPI và Role."""
    try:
        # Prepare body for n8n
        webhook_body = {
            "email": payload.email_crawl,
            "Email_crawl": payload.email_crawl,
            "profile_slug": payload.profile_slug,
            "profile_url": payload.profile_url,
            "role": payload.role,
            "kpi": payload.kpi,
            "email_leader": payload.email_leader or "",
        }

        resp = httpx.post(
            settings.n8n_webhook_add_profile_slug_url,
            json=webhook_body,
            timeout=settings.n8n_webhook_add_profile_slug_timeout_sec,
        )
        
        if resp.status_code != 200:
            return {"success": False, "message": f"N8N trả về lỗi: {resp.status_code}"}
        return {"success": True, "message": "Cập nhật profile slug thành công."}
    except Exception as e:
        return {"success": False, "message": str(e)}
