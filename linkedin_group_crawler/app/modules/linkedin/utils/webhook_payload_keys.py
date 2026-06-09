"""Chuẩn hoá tên field JSON gửi webhook (slug tiếng Việt không dấu, viết liền)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import re
import unicodedata


_VI_TRANS = str.maketrans(
    {
        "đ": "d",
        "Đ": "d",
    },
)


def needs_webhook_slug_alias(key: str) -> bool:
    """True nếu key có ký tự non-ASCII hoặc khoảng trắng — thường là tiêu đề sheet tiếng Việt."""

    if not isinstance(key, str) or not key.strip():
        return False
    if any(ch.isspace() for ch in key):
        return True
    try:
        key.encode("ascii")
    except UnicodeEncodeError:
        return True
    return False


def vietnamese_slug_key(key: str) -> str:
    """Bỏ dấu, chữ thường, chỉ giữ [a-z0-9] viết liền (vd. ``Tên nhóm`` → ``tennhom``)."""

    if not isinstance(key, str):
        return ""
    s = key.strip().translate(_VI_TRANS)
    nfkd = unicodedata.normalize("NFD", s)
    no_marks = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")
    lower = no_marks.lower()
    return re.sub(r"[^a-z0-9]+", "", lower)


_ROW_NUMBER_WEBHOOK_ALIAS_KEYS: Tuple[str, ...] = (
    "row_number",
    "rownumber",
    "rowNumber",
    "STT",
    "stt",
    "Stt",
)


def sync_webhook_body_row_number_aliases(body: Dict[str, Any], row_number: int) -> None:
    """Sau merge ``sheet_row``: ép các alias STT / ``row_number`` khớp số dòng từ API (ưu tiên UI phiên)."""

    for k in _ROW_NUMBER_WEBHOOK_ALIAS_KEYS:
        body[k] = row_number


def merge_sheet_row_into_webhook_body(
    body: Dict[str, Any],
    sheet_row: Dict[str, Any],
) -> None:
    """Merge ``sheet_row`` vào ``body``; với key tiếng Việt có dấu / có space thêm alias slug."""

    for raw_key, value in sheet_row.items():
        if not isinstance(raw_key, str):
            continue
        body[raw_key] = value
        if needs_webhook_slug_alias(raw_key):
            slug = vietnamese_slug_key(raw_key)
            if slug and slug != raw_key:
                body[slug] = value


def _coerce_non_negative_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, float):
        if raw != raw:  # NaN
            return None
        return max(0, int(raw))
    if isinstance(raw, str):
        s = raw.strip().replace(",", "").replace(" ", "")
        if not s:
            return None
        try:
            return max(0, int(float(s)))
        except ValueError:
            return None
    return None


def _first_metric_int(body: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
    """Lấy số đầu tiên khớp một trong các key (đã merge vào ``body``, kể cả slug kiểu ``solike``)."""

    for k in keys:
        if k not in body:
            continue
        n = _coerce_non_negative_int(body.get(k))
        if n is not None:
            return n
    return None


def enrich_webhook_sheet_metrics(body: Dict[str, Any]) -> None:
    """Thêm key cố định tiếng Anh cho like / comment / báo cáo / điểm — đọc từ các cột sheet đã có trong ``body``.

    Không xoá key gốc (``Số like``, …); chỉ bổ sung để n8n luôn có chỗ map.
    """

    lk = _first_metric_int(
        body,
        (
            "Số like",
            "likes",
            "Số Like",
            "solike",
            "linkedin_like_count",
        ),
    )
    if lk is not None:
        body["linkedin_like_count"] = lk

    cm = _first_metric_int(
        body,
        (
            "Số comment",
            "comments",
            "Số Comment",
            "socomment",
            "linkedin_comment_count",
        ),
    )
    if cm is not None:
        body["linkedin_comment_count"] = cm

    rp = _first_metric_int(body, _REPORT_METRIC_KEYS)
    if rp is not None:
        _propagate_report_metric_aliases(body, rp)

    sc = _first_metric_int(
        body,
        (
            "Điểm",
            "score",
            "Score",
            "diem",
            "post_score",
            "linkedin_post_score",
        ),
    )
    if sc is not None:
        body["post_score"] = sc
        body["linkedin_post_score"] = sc

    sess_n = _first_metric_int(
        body,
        (
            "posts_count",
            "Tổng số bài lấy được mỗi lần cào",
            "tongsobailayduocmoilancao",
            "session_posts_count",
            "total_posts_per_scrape",
        ),
    )
    if sess_n is not None:
        body["session_posts_count"] = sess_n
        body["total_posts_per_scrape"] = sess_n


_LIKE_METRIC_KEYS: Tuple[str, ...] = (
    "Số like",
    "likes",
    "Số Like",
    "solike",
    "linkedin_like_count",
)


_COMMENT_METRIC_KEYS: Tuple[str, ...] = (
    "Số comment",
    "comments",
    "Số Comment",
    "socomment",
    "linkedin_comment_count",
)


_REPORT_METRIC_KEYS: Tuple[str, ...] = (
    "Số báo cáo",
    "Số bao cao",
    "Lượng báo sao",
    "Luong bao sao",
    "reports",
    "Reports",
    "reposts",
    "Reposts",
    "shares",
    "Shares",
    "report_count",
    "reports_count",
    "sobaocao",
    "luongbaosao",
    "linkedin_report_count",
)


def _propagate_report_metric_aliases(body: Dict[str, Any], value: int) -> None:
    """Đồng bộ số report/repost lên mọi key sheet + canonical mà n8n hay map."""

    body["linkedin_report_count"] = value
    for k in _REPORT_METRIC_KEYS:
        if k in body:
            body[k] = value
    for label in ("Số báo cáo", "Lượng báo sao"):
        slug = vietnamese_slug_key(label)
        if slug:
            body[slug] = value
        if label not in body:
            body[label] = value
    if "reposts" not in body:
        body["reposts"] = value


def bump_comment_metrics_after_app_comment(body: Dict[str, Any]) -> None:
    """Sau khi gửi comment qua app: cộng 1 vào các key số comment trên payload webhook."""

    base = _first_metric_int(body, _COMMENT_METRIC_KEYS)
    new_val = (base if base is not None else 0) + 1
    body["linkedin_comment_count"] = new_val
    for k in _COMMENT_METRIC_KEYS:
        if k in body:
            body[k] = new_val
    slug = vietnamese_slug_key("Số comment")
    if slug:
        body[slug] = new_val
    if "Số comment" not in body:
        body["Số comment"] = new_val


def bump_like_metrics_after_like_reaction(body: Dict[str, Any]) -> None:
    """Sau reaction ``like``: cộng 1 vào số like trên payload gửi n8n (cột sheet + canonical + slug)."""

    base = _first_metric_int(body, _LIKE_METRIC_KEYS)
    new_val = (base if base is not None else 0) + 1
    body["linkedin_like_count"] = new_val
    for k in _LIKE_METRIC_KEYS:
        if k in body:
            body[k] = new_val
    slug = vietnamese_slug_key("Số like")
    if slug:
        body[slug] = new_val
    if "Số like" not in body:
        body["Số like"] = new_val


def decrement_like_metrics_after_clear_reaction(body: Dict[str, Any]) -> None:
    """Sau khi gỡ reaction (clear): trừ 1 số like trên payload — tối thiểu 0."""

    base = _first_metric_int(body, _LIKE_METRIC_KEYS)
    new_val = max(0, (base if base is not None else 1) - 1)
    body["linkedin_like_count"] = new_val
    for k in _LIKE_METRIC_KEYS:
        if k in body:
            body[k] = new_val
    slug = vietnamese_slug_key("Số like")
    if slug:
        body[slug] = new_val
    if "Số like" not in body:
        body["Số like"] = new_val


def decrement_comment_metrics_after_delete_comment(body: Dict[str, Any]) -> None:
    """Sau khi xóa comment qua app: trừ 1 số comment trên payload — tối thiểu 0."""

    base = _first_metric_int(body, _COMMENT_METRIC_KEYS)
    new_val = max(0, (base if base is not None else 1) - 1)
    body["linkedin_comment_count"] = new_val
    for k in _COMMENT_METRIC_KEYS:
        if k in body:
            body[k] = new_val
    slug = vietnamese_slug_key("Số comment")
    if slug:
        body[slug] = new_val
    if "Số comment" not in body:
        body["Số comment"] = new_val

def update_metrics_from_sync(body: Dict[str, Any], total_reactions: int, total_comments: int) -> None:
    """Updates the webhook body with exact metrics fetched during sync."""
    
    # Update reactions/likes
    body["linkedin_like_count"] = total_reactions
    for k in _LIKE_METRIC_KEYS:
        if k in body:
            body[k] = total_reactions
    
    # Update comments
    body["linkedin_comment_count"] = total_comments
    for k in _COMMENT_METRIC_KEYS:
        if k in body:
            body[k] = total_comments
            
    # Also update Vietnamese slugs
    like_slug = vietnamese_slug_key("Số like")
    if like_slug:
        body[like_slug] = total_reactions
    if "Số like" not in body:
        body["Số like"] = total_reactions
        
    comment_slug = vietnamese_slug_key("Số comment")
    if comment_slug:
        body[comment_slug] = total_comments
    if "Số comment" not in body:
        body["Số comment"] = total_comments
