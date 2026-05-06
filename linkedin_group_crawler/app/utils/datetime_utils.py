"""Date and time utility helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import re


def normalize_relative_time(raw: str, crawl_time: datetime) -> datetime | None:
    """Convert LinkedIn relative time like 5m, 2h, 1d into an absolute datetime."""

    if not raw:
        return None

    text = raw.strip().lower()
    match = re.search(r"(\d+)\s*([mhd])", text)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return crawl_time - timedelta(minutes=value)
    if unit == "h":
        return crawl_time - timedelta(hours=value)
    if unit == "d":
        return crawl_time - timedelta(days=value)
    return None


def parse_target_date(target_date: str | None, crawl_time: datetime) -> date:
    """Parse target date or fallback to crawl date."""

    if not target_date:
        return crawl_time.date()
    return datetime.strptime(target_date, "%Y-%m-%d").date()


def is_same_day(dt: datetime, target_date: date) -> bool:
    """Check whether datetime belongs to the target date."""

    return dt.date() == target_date
