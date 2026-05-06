"""Google Sheets (service account) — đọc/ghi tab top_posts và danh sách URL nhóm."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings
from app.utils.logger import get_logger


logger = get_logger(__name__)

_SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

# Map header (trimmed) → giá trị ô (theo ngữ nghĩa khi append bài mới)
_TOP_POST_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "email_crawl": ("email_crawl", "email crawl"),
    "ngày": ("ngay", "ngày", "date"),
    "tên nhóm": ("ten nhom", "tên nhóm", "group_name", "group name"),
    "url_nhóm": ("url_nhom", "url_nhóm", "url nhóm", "group_url", "group url"),
    "url_bài_viết": ("url_bai_viet", "url_bài_viết", "url bài viết", "post_url", "post url"),
    "tác giả": ("tac gia", "tác giả", "author"),
    "nội dung": ("noi dung", "nội dung", "content"),
    "số like": ("so like", "số like", "likes"),
    "số comment": ("so comment", "số comment", "comments"),
    "lượng báo sao": ("luong bao sao", "lượng báo sao", "reposts", "shares"),
    "điểm": ("diem", "điểm", "score"),
    "đăng vào": ("dang vao", "đăng vào", "posted_at"),
    "tổng số bài lấy được mỗi lần sao": (
        "tong so bai lay duoc moi lan sao",
        "tổng số bài lấy được mỗi lần sao",
        "total_posts",
    ),
}


def _normalize_header_cell(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _credential_path() -> Path:
    path = Path(settings.google_service_account_json_path)
    if path.exists():
        return path
    raise FileNotFoundError(
        f"Không thấy file service account GOOGLE_SERVICE_ACCOUNT_JSON: {path.as_posix()}",
    )


def _build_credentials():
    path = _credential_path()
    return service_account.Credentials.from_service_account_file(
        path.as_posix(),
        scopes=_SHEETS_SCOPES,
    )


def get_sheets_service():
    credentials = _build_credentials()
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


_spreadsheet_sheet_titles_cache: dict[str, list[str]] = {}


def _fetch_spreadsheet_sheet_titles(spreadsheet_id: str) -> list[str]:
    service = get_sheets_service()
    body = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title))")
        .execute()
    )
    titles: list[str] = []
    for sheet in body.get("sheets", []):
        props = sheet.get("properties") or {}
        title = props.get("title")
        if isinstance(title, str) and title.strip():
            titles.append(title)
    return titles


def get_spreadsheet_sheet_titles(spreadsheet_id: str) -> list[str]:
    """Danh sách tên tab đúng như trên Google Sheets (cache theo process)."""

    sid = (spreadsheet_id or "").strip()
    if not sid:
        return []
    if sid not in _spreadsheet_sheet_titles_cache:
        _spreadsheet_sheet_titles_cache[sid] = _fetch_spreadsheet_sheet_titles(sid)
    return _spreadsheet_sheet_titles_cache[sid]


def _normalize_tab_token(name: str) -> str:
    text = (name or "").strip().lower().replace("_", " ")
    return re.sub(r"\s+", " ", text)


def _match_configured_tab_title(titles: list[str], preferred: str) -> str | None:
    pref = (preferred or "").strip()
    if not pref:
        return None
    if pref in titles:
        return pref
    lower_map = {t.lower(): t for t in titles}
    if pref.lower() in lower_map:
        return lower_map[pref.lower()]
    pn = _normalize_tab_token(pref)
    for t in titles:
        if _normalize_tab_token(t) == pn:
            return t
    return None


def resolve_top_posts_tab_title(spreadsheet_id: str) -> str:
    """Khớp tab ``top_posts`` với tên thật trên file (không phân biệt hoa thường / underscore)."""

    titles = get_spreadsheet_sheet_titles(spreadsheet_id)
    if not titles:
        raise ValueError(
            "Google Sheet không có tab nào hoặc không đọc được metadata (kiểm tra spreadsheetId và quyền service account).",
        )
    cfg = settings.google_sheet_top_posts_tab.strip()
    hit = _match_configured_tab_title(titles, cfg)
    if hit:
        return hit
    for t in titles:
        n = _normalize_tab_token(t).replace(" ", "")
        if "top" in n and "post" in n:
            logger.info("Đã map GOOGLE_SHEET_TOP_POSTS_TAB -> tab thật '%s'", t)
            return t
    logger.warning("Không khớp tên tab top_posts, dùng tab đầu tiên: %s", titles[0])
    return titles[0]


def resolve_group_urls_tab_title(spreadsheet_id: str, top_posts_tab: str) -> str | None:
    """Tab danh sách URL nhóm: ưu tiên env, sau đó heuristics (URL + nhóm) hoặc tab duy nhất còn lại."""

    titles = get_spreadsheet_sheet_titles(spreadsheet_id)
    others = [t for t in titles if t != top_posts_tab]
    cfg = settings.google_sheet_group_urls_tab.strip()
    if cfg:
        hit = _match_configured_tab_title(titles, cfg)
        if hit and hit != top_posts_tab:
            return hit
        if hit == top_posts_tab:
            logger.warning(
                "GOOGLE_SHEET_GROUP_URLS_TAB trùng tab top_posts (%s); bỏ qua và tự tìm tab URL nhóm.",
                top_posts_tab,
            )
    for t in others:
        compact = _normalize_tab_token(t).replace(" ", "")
        if "url" in compact and "nhom" in compact:
            logger.info("Đã map tab URL nhóm -> '%s'", t)
            return t
    if len(others) == 1:
        logger.info("Chỉ còn một tab ngoài top_posts — dùng '%s' cho URL nhóm", others[0])
        return others[0]
    if len(others) > 1:
        logger.warning(
            "Nhiều tab có thể là URL nhóm %s — set GOOGLE_SHEET_GROUP_URLS_TAB trong .env (tên tab chính xác).",
            others,
        )
    return None


def _a1_quote_sheet_title(title: str) -> str:
    """Quote tên tab cho A1 notation (escape dấu nháy đơn)."""

    return "'" + str(title).replace("'", "''") + "'"


def _sheet_a1(spreadsheet_id: str, tab_title: str, cell_range: str) -> str:
    return f"{_a1_quote_sheet_title(tab_title)}!{cell_range}"


def spreadsheet_configured() -> bool:
    spreadsheet_id_ok = bool((settings.google_spreadsheet_id or "").strip())
    json_path = Path(settings.google_service_account_json_path)
    return spreadsheet_id_ok and json_path.is_file()


def _read_values(*, spreadsheet_id: str, range_a1: str) -> list[list[Any]]:
    service = get_sheets_service()
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1, majorDimension="ROWS")
        .execute()
    )
    return list(resp.get("values") or [])


def _headers_to_unique_keys(headers: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    keys: list[str] = []
    for index, raw in enumerate(headers):
        label = (raw or "").strip()
        if not label:
            label = f"Column_{index + 1}"
        base = label
        counts[base] = counts.get(base, 0) + 1
        if counts[base] == 1:
            keys.append(base)
        else:
            keys.append(f"{base}__{counts[base]}")
    return keys


def read_top_post_header_row() -> list[str]:
    """Chỉ đọc dòng tiêu đề tab top_posts (để map cột khi append)."""

    sid = settings.google_spreadsheet_id
    tab = resolve_top_posts_tab_title(sid)
    raw = _read_values(spreadsheet_id=sid, range_a1=_sheet_a1(sid, tab, "1:1"))
    if not raw or not raw[0]:
        raise ValueError(f"Tab '{tab}' trống hoặc thiếu dòng tiêu đề.")
    return [str(c or "") for c in raw[0]]


def read_top_posts_as_dicts() -> tuple[list[str], list[dict[str, Any]]]:
    """Đọc toàn bộ tab top_posts: trả về (header_keys, rows)."""

    sid = settings.google_spreadsheet_id
    tab = resolve_top_posts_tab_title(sid)
    raw = _read_values(spreadsheet_id=sid, range_a1=_sheet_a1(sid, tab, "A:ZZ"))
    if not raw:
        return [], []

    headers = raw[0]
    keys = _headers_to_unique_keys([str(cell) if cell is not None else "" for cell in headers])
    rows: list[dict[str, Any]] = []
    for line in raw[1:]:
        padded = list(line) + [""] * (len(keys) - len(line))
        row_obj: dict[str, Any] = {}
        for key, cell in zip(keys, padded[: len(keys)]):
            row_obj[key] = cell
        rows.append(row_obj)
    return keys, rows


def _normalize_owner_email_token(value: str) -> str:
    return (value or "").strip().lower()


def _header_key_base(header_key: str) -> str:
    """Bỏ hậu tố ``__2`` (cột trùng tên) để map semantic."""

    return re.sub(r"__\d+$", "", str(header_key).strip())


def _get_row_email_crawl_cell(row: dict[str, Any]) -> str:
    for header_key, raw in row.items():
        base = _header_key_base(header_key)
        if _header_semantic_key(base) == "email_crawl":
            return str(raw or "").strip()
    return ""


def _parse_cell_date_maybe(value: str) -> date | None:
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _collect_sheet_row_ngay_dates(row: dict[str, Any]) -> list[date]:
    parsed: list[date] = []
    for header_key, raw in row.items():
        base = _header_key_base(header_key)
        if _header_semantic_key(base) != "ngày":
            continue
        dcell = _parse_cell_date_maybe(str(raw or ""))
        if dcell:
            parsed.append(dcell)
    return parsed


def filter_sheet_top_posts_for_owner(
    rows: list[dict[str, Any]],
    *,
    owner_email_token: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Chỉ trả các dòng có ``Email_crawl`` đúng owner; lọc theo khoảng các cột ``Ngày`` (YYYYMMDD trên ô)."""

    owner = _normalize_owner_email_token(owner_email_token)
    if not owner:
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        cell_owner = _normalize_owner_email_token(_get_row_email_crawl_cell(row))
        if cell_owner != owner:
            continue

        if date_from is None and date_to is None:
            out.append(row)
            continue

        row_dates = _collect_sheet_row_ngay_dates(row)
        if not row_dates:
            continue

        for rd in row_dates:
            ok = True
            if date_from is not None and rd < date_from:
                ok = False
            if date_to is not None and rd > date_to:
                ok = False
            if ok:
                out.append(row)
                break

    return out


def _hyperlink_formula(url: str, label: str | None = None) -> str:
    if not (url or "").strip():
        return ""
    escaped_url = url.replace('"', '""')
    lab = (label or url).replace('"', '""')
    return f'=HYPERLINK("{escaped_url}","{lab}")'


def _header_semantic_key(header: str) -> str | None:
    norm = _normalize_header_cell(header)
    for canonical, aliases in _TOP_POST_HEADER_ALIASES.items():
        if norm == _normalize_header_cell(canonical):
            return canonical
        for alias in aliases:
            if norm == _normalize_header_cell(alias):
                return canonical
    return None


def build_top_post_row_values(
    headers: list[str],
    *,
    email_crawl: str,
    crawl_date: str,
    group_name: str,
    group_url: str,
    total_posts_in_run: int,
    post: dict[str, Any],
) -> list[str]:
    """Tạo một dòng theo đúng thứ tự cột của header dòng 1 trong Sheet."""

    row: list[str] = []
    for header in headers:
        sem = _header_semantic_key(header)
        if sem == "email_crawl":
            row.append(email_crawl)
        elif sem == "ngày":
            row.append(crawl_date)
        elif sem == "tên nhóm":
            row.append(group_name)
        elif sem == "url_nhóm":
            row.append(_hyperlink_formula(group_url, group_url) if group_url else "")
        elif sem == "url_bài_viết":
            pu = str(post.get("post_url") or "")
            row.append(_hyperlink_formula(pu, pu) if pu else "")
        elif sem == "tác giả":
            row.append(str(post.get("author") or ""))
        elif sem == "nội dung":
            row.append(str(post.get("content") or ""))
        elif sem == "số like":
            row.append(str(int(post.get("likes") or 0)))
        elif sem == "số comment":
            row.append(str(int(post.get("comments") or 0)))
        elif sem == "lượng báo sao":
            row.append(str(int(post.get("reposts") or 0)))
        elif sem == "điểm":
            row.append(str(int(post.get("score") or 0)))
        elif sem == "đăng vào":
            row.append(str(post.get("posted_at") or ""))
        elif sem == "tổng số bài lấy được mỗi lần sao":
            row.append(str(int(total_posts_in_run)))
        else:
            row.append("")
    return row


def append_top_post_rows(rows_2d: list[list[Any]]) -> None:
    sid = settings.google_spreadsheet_id
    tab = resolve_top_posts_tab_title(sid)
    if not rows_2d:
        return
    service = get_sheets_service()
    service.spreadsheets().values().append(
        spreadsheetId=sid,
        range=_sheet_a1(sid, tab, "A:A"),
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows_2d},
    ).execute()


def read_group_url_rows() -> list[dict[str, Any]]:
    """Đọc tab URL nhóm: cột URL_Nhóm, email, Trạng thái."""

    sid = settings.google_spreadsheet_id
    top_tab = resolve_top_posts_tab_title(sid)
    tab = resolve_group_urls_tab_title(sid, top_tab)
    if not tab:
        logger.warning(
            "Không xác định được tab danh sách URL nhóm. Thêm GOOGLE_SHEET_GROUP_URLS_TAB=<tên tab> vào .env.",
        )
        return []
    raw = _read_values(spreadsheet_id=sid, range_a1=_sheet_a1(sid, tab, "A:Z"))
    if not raw:
        return []
    headers = [str(c or "").strip() for c in raw[0]]
    keys = _headers_to_unique_keys(headers)
    out: list[dict[str, Any]] = []
    for line in raw[1:]:
        padded = list(line) + [""] * (len(keys) - len(line))
        item: dict[str, Any] = {}
        for key, cell in zip(keys, padded[: len(keys)]):
            item[key] = cell
        out.append(item)
    return out


def _normalize_group_url(url: str) -> str:
    p = urlparse((url or "").strip())
    path = (p.path or "").rstrip("/")
    return f"{p.scheme}://{p.netloc}{path}".lower()


def update_group_status_by_url(target_url: str, status: str = "done") -> bool:
    """Tìm dòng trùng URL_Nhóm (cột A) và ghi Trạng thái (cột C nếu đúng layout)."""

    sid = settings.google_spreadsheet_id
    top_tab = resolve_top_posts_tab_title(sid)
    tab = resolve_group_urls_tab_title(sid, top_tab)
    if not tab:
        logger.warning("Không có tab URL nhóm — bỏ qua cập nhật trạng thái cho %s", target_url)
        return False
    raw = _read_values(spreadsheet_id=sid, range_a1=_sheet_a1(sid, tab, "A:Z"))
    if len(raw) < 2:
        return False

    headers = [str(c or "").strip() for c in raw[0]]
    try:
        url_col_index = next(
            i
            for i, h in enumerate(headers)
            if _normalize_header_cell(h) in {_normalize_header_cell("URL_Nhóm"), _normalize_header_cell("url_nhom")}
        )
    except StopIteration:
        url_col_index = 0

    try:
        status_col_index = next(
            i
            for i, h in enumerate(headers)
            if _normalize_header_cell(h) in {_normalize_header_cell("Trạng thái"), _normalize_header_cell("trang thai")}
        )
    except StopIteration:
        status_col_index = 2

    want = _normalize_group_url(target_url)
    row_number: int | None = None
    for offset, line in enumerate(raw[1:], start=2):
        cells = list(line) + [""] * (url_col_index + 1 - len(line))
        cell = cells[url_col_index] if url_col_index < len(cells) else ""
        if _normalize_group_url(str(cell)) == want:
            row_number = offset
            break

    if row_number is None:
        logger.warning("Không tìm thấy URL nhóm trong sheet để cập nhật trạng thái: %s", target_url)
        return False

    col_letter = chr(ord("A") + status_col_index)
    range_a1 = _sheet_a1(sid, tab, f"{col_letter}{row_number}")
    service = get_sheets_service()
    service.spreadsheets().values().update(
        spreadsheetId=sid,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        body={"values": [[status]]},
    ).execute()
    return True


def safe_http_message(exc: Exception) -> str:
    if isinstance(exc, HttpError):
        try:
            return str(exc.error_details or exc.reason or exc)
        except Exception:
            return str(exc)
    return str(exc)
