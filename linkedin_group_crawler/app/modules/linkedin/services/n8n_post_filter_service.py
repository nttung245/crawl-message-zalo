"""Trích danh sách bài từ JSON webhook n8n và lọc theo khoảng ngày (backend)."""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from app.core.logger import get_logger


logger = get_logger(__name__)


UNKNOWN_SESSION_ID = "unknown"

_SESSION_ID_KEYS_EXACT = (
    "id_session_crawl",
    "ID_session_crawl",
    "idSessionCrawl",
    "session_crawl_id",
    "id_session",
    "idSession",
)

_GROUP_URL_KEYS_EXACT = (
    "URL_Nhóm",
    "URL_nhom",
    "url_nhom",
    "group_url",
    "groupUrl",
    "URLnhom",
)

_GROUP_NAME_KEYS_EXACT = (
    "Tên nhóm",
    "Ten nhom",
    "ten_nhom",
    "group_name",
    "groupName",
)

_EMAIL_CRAWL_KEYS_EXACT = (
    "Email_crawl",
    "email_crawl",
    "emailCrawl",
)


_DATE_KEY_CANDIDATES = (
    "Ngày",
    "ngay",
    "date",
    "posted_at",
    "Đăng vào",
    "dang_vao",
    "created_at",
    "crawl_date",
    "timestamp",
)


def posts_from_n8n_payload(body: Any) -> list[dict[str, Any]]:
    """Trích list bài: array thuần; hoặc ``posts`` / ``data`` (chuẩn n8n ``{ success, data: [...] }``)."""

    if body is None:
        return []
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        inner = body.get("posts")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        inner = body.get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        if isinstance(inner, dict) and isinstance(inner.get("posts"), list):
            return [x for x in inner["posts"] if isinstance(x, dict)]
        # Không coi envelope webhook là một dòng bài
        if any(k in body for k in ("success", "message", "total")):
            return []
        return [body]
    return []


def normalize_n8n_sheet_post(post: dict[str, Any]) -> dict[str, Any]:
    """Gán ``id_session_crawl`` chuẩn nếu webhook dùng alias (vd. ``ID_session_crawl``)."""

    out = dict(post)
    if _non_empty_str(out.get("id_session_crawl")):
        return out
    for key in _SESSION_ID_KEYS_EXACT:
        if key == "id_session_crawl":
            continue
        val = _non_empty_str(out.get(key))
        if val:
            out["id_session_crawl"] = val
            break
    return out


def normalize_n8n_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_n8n_sheet_post(p) for p in posts]


def _parse_iso_date_fragment(text: str) -> date | None:
    text = (text or "").strip()
    if len(text) < 10:
        return None
    head = text[:10]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        pass
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def parse_post_record_date(record: dict[str, Any]) -> date | None:
    """Lấy một ngày lịch (date) từ một bản ghi post kiểu sheet/webhook."""

    for key in _DATE_KEY_CANDIDATES:
        if key not in record:
            continue
        raw = record.get(key)
        if raw is None:
            continue
        parsed = _parse_iso_date_fragment(str(raw))
        if parsed:
            return parsed

    for key, raw in record.items():
        lk = str(key).lower()
        if "ngày" in lk or "date" in lk or "time" in lk:
            parsed = _parse_iso_date_fragment(str(raw))
            if parsed:
                return parsed
    return None


def filter_posts_by_inclusive_date_range(
    posts: list[dict[str, Any]],
    start: date | None,
    end: date | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lọc inclusive ``start``..``end``. Nếu cả hai None → không lọc."""

    meta: dict[str, Any] = {"mode": "none", "start": None, "end": None}
    if start is None and end is None:
        return list(posts), meta

    meta["mode"] = "range"
    meta["start"] = start.isoformat() if start else None
    meta["end"] = end.isoformat() if end else None

    kept: list[dict[str, Any]] = []
    skipped_no_date = 0
    for item in posts:
        d = parse_post_record_date(item)
        if d is None:
            skipped_no_date += 1
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        kept.append(item)

    meta["skipped_missing_date"] = skipped_no_date
    meta["total_input"] = len(posts)
    meta["total_output"] = len(kept)
    return kept, meta


def _non_empty_str(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    return s


def session_id_from_post(post: dict[str, Any]) -> str:
    """Chuẩn hoá id phiên cào để gom nhóm (khớp output /crawl-linkedin-group)."""

    for key in _SESSION_ID_KEYS_EXACT:
        val = _non_empty_str(post.get(key))
        if val:
            return val

    for key, raw in post.items():
        lk = str(key).lower().replace(" ", "").replace("-", "_")
        if lk in {"idsessioncrawl", "sessioncrawlid", "idcrawlsession"}:
            val = _non_empty_str(raw)
            if val:
                return val
    return UNKNOWN_SESSION_ID


def group_url_from_post(post: dict[str, Any]) -> str:
    for key in _GROUP_URL_KEYS_EXACT:
        val = _non_empty_str(post.get(key))
        if val:
            return val
    for key, raw in post.items():
        lk = str(key).lower()
        if "url" in lk and ("nhom" in lk or "group" in lk):
            val = _non_empty_str(raw)
            if val:
                return val
    return ""


def group_name_from_post(post: dict[str, Any]) -> str:
    for key in _GROUP_NAME_KEYS_EXACT:
        val = _non_empty_str(post.get(key))
        if val:
            return val
    for key, raw in post.items():
        lk = str(key).lower()
        if "nhom" in lk or "group" in lk:
            if "url" in lk:
                continue
            val = _non_empty_str(raw)
            if val:
                return val
    return ""


def email_crawl_from_post(post: dict[str, Any]) -> str:
    for key in _EMAIL_CRAWL_KEYS_EXACT:
        val = _non_empty_str(post.get(key))
        if val:
            return val
    return ""


def _session_sort_latest_post_date(posts: list[dict[str, Any]]) -> date:
    dates = [parse_post_record_date(p) for p in posts]
    ok = [d for d in dates if d is not None]
    return max(ok) if ok else date.min


def _int_field(post: dict[str, Any], keys: tuple[str, ...]) -> int:
    for k in keys:
        if k not in post:
            continue
        raw = post.get(k)
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return 0


def post_rank_key(post: dict[str, Any]) -> tuple[int, int, int]:
    """So sánh bài “hot” nhất: Điểm → like → comment (sheet / webhook)."""

    score = _int_field(post, ("Điểm", "score", "Score"))
    likes = _int_field(post, ("Số like", "likes", "Số Like"))
    comments = _int_field(post, ("Số comment", "comments"))
    return (score, likes, comments)


def group_key_from_post(post: dict[str, Any]) -> str:
    """Khóa nhóm LinkedIn để mỗi nhóm chỉ giữ một bài trong phiên."""

    u = group_url_from_post(post).strip()
    if u:
        return u
    n = group_name_from_post(post).strip()
    return f"name:{n}" if n else "__unknown__"


_ROW_NUMBER_KEYS_EXACT = (
    "row_number",
    "rowNumber",
    "STT",
    "stt",
)


def _post_has_meaningful_row_number(post: dict[str, Any]) -> bool:
    """Ô STT / row_number có số nguyên > 0 (không trống / 0)."""

    for key in _ROW_NUMBER_KEYS_EXACT:
        if key not in post:
            continue
        raw = post.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (int, float)):
                n = int(raw)
            else:
                s = str(raw).strip()
                if not s:
                    continue
                n = int(s)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return True
    return False


def enrich_post_row_number_if_missing(post: dict[str, Any], ordinal: int) -> dict[str, Any]:
    """Gán ``row_number`` / ``rowNumber`` = thứ tự trong phiên (1…n) khi sheet/n8n không có."""

    if _post_has_meaningful_row_number(post):
        return post
    out = dict(post)
    out["row_number"] = ordinal
    out["rowNumber"] = ordinal
    out["STT"] = ordinal
    out["stt"] = ordinal
    return out


def pick_top_post_per_group(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trong một phiên cào: mỗi nhóm một bài — chọn bài rank cao nhất; thứ tự nhóm = lần đầu gặp."""

    buckets: dict[str, list[dict[str, Any]]] = {}
    order_keys: list[str] = []
    for p in posts:
        key = group_key_from_post(p)
        if key not in buckets:
            buckets[key] = []
            order_keys.append(key)
        buckets[key].append(p)
    return [max(buckets[k], key=post_rank_key) for k in order_keys]


def build_crawl_sessions_from_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gom theo ``id_session_crawl``; trong mỗi phiên mỗi nhóm chỉ 1 bài (điểm cao nhất); sort phiên mới nhất trước."""

    bucket_posts: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []

    for item in posts:
        sid = session_id_from_post(item)
        if sid not in bucket_posts:
            bucket_posts[sid] = []
            order.append(sid)
        bucket_posts[sid].append(item)

    sessions: list[dict[str, Any]] = []
    for sid in order:
        plist_raw = pick_top_post_per_group(bucket_posts[sid])
        plist = [
            enrich_post_row_number_if_missing(p, idx + 1)
            for idx, p in enumerate(plist_raw)
        ]
        gu = ""
        gn = ""
        ec = ""
        for p in plist:
            if not gu:
                gu = group_url_from_post(p)
            if not gn:
                gn = group_name_from_post(p)
            if not ec:
                ec = email_crawl_from_post(p)

        sessions.append(
            {
                "id_session_crawl": sid,
                "group_name": gn,
                "group_url": gu,
                "email_crawl": ec,
                "posts_count": len(plist),
                "posts": plist,
            },
        )

    sessions.sort(
        key=lambda s: (_session_sort_latest_post_date(s["posts"]), s["id_session_crawl"]),
        reverse=True,
    )
    return sessions


def flatten_crawl_sessions_posts(crawl_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nối ``posts`` của từng phiên theo đúng thứ tự ``crawl_sessions`` (đã sort lần cào)."""

    ordered: list[dict[str, Any]] = []
    for s in crawl_sessions:
        inner = s.get("posts")
        if isinstance(inner, list):
            ordered.extend(x for x in inner if isinstance(x, dict))
    return ordered
