import asyncio
from typing import Dict, List

import gspread
from google.oauth2.service_account import Credentials
from loguru import logger

from app.modules.zalo.schemas.message import Message

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MESSAGES_HEADERS = ["#", "sender", "time_text", "is_sent", "content"]

BATCH_SIZE = 50
MAX_RETRIES = 3
RETRY_DELAY = 10


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
    # Intentionally keep only message text content in Sheet.
    # Image URLs are not persisted.
    return _normalize_content(msg.content or "")


def _ensure_worksheet(spreadsheet, tab_name: str, headers: List[str]) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(tab_name)
        ws.clear()
        ws.append_row(headers)
        return ws
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        return ws


async def _append_with_retry(ws: gspread.Worksheet, rows: List[list]) -> None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ws.append_rows(rows, value_input_option="RAW")
            return
        except gspread.exceptions.APIError as e:
            if "429" in str(e) and attempt < MAX_RETRIES:
                logger.warning(f"Google Sheets 429, retrying in {RETRY_DELAY}s (attempt {attempt})")
                await asyncio.sleep(RETRY_DELAY)
            else:
                raise


async def write_messages(
    credentials_path: str,
    sheet_id: str,
    group_name: str,
    sheet_tab: str,
    messages: List[Message],
) -> None:
    loop = asyncio.get_event_loop()

    def _sync_prepare():
        try:
            client = _build_client(credentials_path)
        except Exception as exc:
            raise RuntimeError(
                f"Google credentials error at {credentials_path}: {type(exc).__name__}: {exc}"
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

        tab_name = sheet_tab or group_name
        _ensure_worksheet(spreadsheet, tab_name, MESSAGES_HEADERS)

        rows = []
        for idx, msg in enumerate(messages, start=1):
            rows.append([
                idx,
                "Tôi" if msg.is_sent or msg.sender_name == "__me__" else (msg.sender_name or ""),
                msg.time_text or "",
                "true" if msg.is_sent else "false",
                _sheet_content(msg),
            ])
        return tab_name, rows

    tab_name, rows = await loop.run_in_executor(None, _sync_prepare)

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            client = _build_client(credentials_path)
            spreadsheet = client.open_by_key(sheet_id)
            ws = spreadsheet.worksheet(tab_name)
        except gspread.exceptions.SpreadsheetNotFound as exc:
            raise RuntimeError(
                "Google Sheet not found or service account has no access during messages write. "
                f"sheet_id={sheet_id}"
            ) from exc
        except gspread.exceptions.WorksheetNotFound as exc:
            raise RuntimeError(f"Worksheet {tab_name!r} not found after creation step") from exc
        await _append_with_retry(ws, batch)
        logger.info(f"Wrote batch {i // BATCH_SIZE + 1} to tab {tab_name} ({len(batch)} rows)")

    logger.info(f"Google Sheets write complete: {len(rows)} rows to tab {tab_name}")


def list_crawled_groups(
    credentials_path: str,
    sheet_id: str,
) -> List[Dict]:
    client = _build_client(credentials_path)
    spreadsheet = client.open_by_key(sheet_id)
    groups: List[Dict] = []

    for ws in spreadsheet.worksheets():
        try:
            header = ws.row_values(1)
        except Exception:
            continue

        normalized = [h.strip().lower() for h in header[: len(MESSAGES_HEADERS)]]
        expected = [h.lower() for h in MESSAGES_HEADERS]
        if normalized != expected:
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

