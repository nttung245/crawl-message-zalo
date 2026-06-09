from typing import Dict, List
import asyncio
import time

import gspread
from google.oauth2.service_account import Credentials
from loguru import logger

from app.modules.zalo.schemas.message import Message

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MESSAGES_HEADERS = ["#", "sender", "timestamp", "time_text", "is_sent", "type", "content", "image_urls"]
LEGACY_MESSAGES_HEADERS = ["#", "sender", "time_text", "is_sent", "content"]

BATCH_SIZE = 50
MAX_RETRIES = 3
RETRY_BASE_DELAY = 10
# FIX: Thêm 500/503 vào danh sách retry (trước đây chỉ retry 429)
RETRYABLE_STATUS_CODES = {429, 500, 503}


def _build_client(credentials_path: str) -> gspread.Client:
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _normalize_content(value: str) -> str:
    lines = [" ".join(line.split()) for line in (value or "").splitlines()]
    lines = [line for line in lines if line]
    deduped: List[str] = []
    for line in lines:
        if deduped[-1:] != [line]:
            deduped.append(line)
    return "\n".join(deduped).strip()


def _sheet_content(msg: Message) -> str:
    # Keep text-like content in this column; image URLs are persisted separately.
    return _normalize_content(msg.content or "")


def _get_api_error_status(e: gspread.exceptions.APIError) -> int:
    """Lấy HTTP status code từ gspread APIError một cách an toàn."""
    try:
        return e.response.status_code
    except Exception:
        # Fallback: kiểm tra string (backward compat)
        s = str(e)
        for code in RETRYABLE_STATUS_CODES:
            if str(code) in s:
                return code
        return 0


def _append_rows_with_retry(ws: gspread.Worksheet, rows: List[list]) -> None:
    """Ghi rows vào worksheet với retry theo exponential backoff.
    FIX: Hàm này là SYNC — phải được gọi qua asyncio.to_thread().
    FIX: Retry cả 429, 500, 503 (không chỉ 429 như trước).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ws.append_rows(rows, value_input_option="RAW")
            return
        except gspread.exceptions.APIError as e:
            status_code = _get_api_error_status(e)
            if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * attempt  # exponential backoff
                logger.warning(
                    f"Google Sheets API {status_code}, retrying in {delay}s (attempt {attempt}/{MAX_RETRIES})"
                )
                time.sleep(delay)
            else:
                raise


def _sync_write_all(
    credentials_path: str,
    sheet_id: str,
    tab_name: str,
    rows: List[list],
) -> None:
    """Toàn bộ logic ghi Google Sheet chạy trong thread riêng (blocking I/O).

    FIX C-3: Tạo client + worksheet MỘT LẦN, reuse cho tất cả batch.
             Trước đây tạo lại client mỗi batch → N+1 OAuth calls không cần thiết.
    FIX H-5: Atomic write — ghi vào tab tạm rồi rename để tránh mất data nếu crash.
             Trước đây ws.clear() ngay lập tức → mất data nếu ghi bị lỗi giữa chừng.
    """
    try:
        client = _build_client(credentials_path)
    except Exception as exc:
        raise RuntimeError(
            f"Google credentials configuration error: {type(exc).__name__}"
        ) from exc

    try:
        spreadsheet = client.open_by_key(sheet_id)
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise RuntimeError(
            "Google Sheet not found or service account has no access. "
            f"sheet_id={sheet_id}. "
            "Hay share file Google Sheet cho service account."
        ) from exc
    except gspread.exceptions.APIError as exc:
        raise RuntimeError(
            f"Google Sheets API error while opening sheet {sheet_id}: {exc}"
        ) from exc

    # FIX H-5: Atomic write pattern
    # 1. Ghi vào tab tạm thời (không xóa tab gốc trước)
    # 2. Chỉ sau khi ghi thành công mới xóa tab gốc và rename
    temp_tab_name = f"__temp_{tab_name}_{int(time.time())}"
    temp_ws = None
    try:
        # Tạo tab tạm để ghi
        temp_ws = spreadsheet.add_worksheet(
            title=temp_tab_name,
            rows=max(len(rows) + 10, 100),
            cols=len(MESSAGES_HEADERS),
        )
        temp_ws.append_row(MESSAGES_HEADERS)

        # Ghi từng batch (reuse cùng client + worksheet)
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i: i + BATCH_SIZE]
            _append_rows_with_retry(temp_ws, batch)
            logger.info(
                f"Wrote batch {i // BATCH_SIZE + 1} to temp tab {temp_tab_name!r} ({len(batch)} rows)"
            )

        # Ghi thành công → xóa tab gốc (nếu có) rồi rename temp → tab_name
        try:
            old_ws = spreadsheet.worksheet(tab_name)
            spreadsheet.del_worksheet(old_ws)
        except gspread.exceptions.WorksheetNotFound:
            pass  # Tab gốc chưa tồn tại — bình thường khi crawl lần đầu

        temp_ws.update_title(tab_name)
        logger.info(f"Google Sheets write complete: {len(rows)} rows to tab {tab_name!r}")

    except Exception:
        # Nếu có lỗi → xóa tab tạm để dọn dẹp
        if temp_ws:
            try:
                spreadsheet.del_worksheet(temp_ws)
            except Exception:
                pass
        raise


async def write_messages(
    credentials_path: str,
    sheet_id: str,
    group_name: str,
    sheet_tab: str,
    messages: List[Message],
) -> None:
    """Ghi danh sách tin nhắn vào Google Sheet.
    FIX C-3: Dùng asyncio.to_thread() thay vì get_event_loop().run_in_executor()
             (deprecated trong Python 3.10+).
    FIX C-3b: Toàn bộ I/O blocking chạy trong thread riêng, không block event loop.
    """
    tab_name = (sheet_tab or group_name).strip()[:100]  # GSheet tab limit 100 chars

    rows = []
    for idx, msg in enumerate(messages, start=1):
        rows.append([
            idx,
            "Tôi" if msg.is_sent or msg.sender_name == "__me__" else (msg.sender_name or ""),
            msg.timestamp or "",
            msg.time_text or "",
            "true" if msg.is_sent else "false",
            msg.type or "",
            _sheet_content(msg),
            "\n".join(msg.image_urls or []),
        ])

    # FIX C-3: asyncio.to_thread() đúng chuẩn cho Python 3.9+
    await asyncio.to_thread(_sync_write_all, credentials_path, sheet_id, tab_name, rows)


def list_crawled_groups(
    credentials_path: str,
    sheet_id: str,
) -> List[Dict]:
    client = _build_client(credentials_path)
    spreadsheet = client.open_by_key(sheet_id)
    groups: List[Dict] = []

    for ws in spreadsheet.worksheets():
        # Bỏ qua các tab tạm thời từ atomic write
        if ws.title.startswith("__temp_"):
            continue
        try:
            header = ws.row_values(1)
        except Exception:
            continue

        normalized = [h.strip().lower() for h in header]
        expected = [h.lower() for h in MESSAGES_HEADERS]
        legacy_expected = [h.lower() for h in LEGACY_MESSAGES_HEADERS]
        if normalized[: len(expected)] != expected and normalized[: len(legacy_expected)] != legacy_expected:
            continue

        try:
            col_a_values = ws.col_values(1)
            message_count = max(len(col_a_values) - 1, 0)
        except Exception:
            message_count = 0

        groups.append(
            {
                "group_name": ws.title,
                "sheet_tab": ws.title,
                "message_count": message_count,
            }
        )

    groups.sort(key=lambda x: x["group_name"].lower())
    return groups
