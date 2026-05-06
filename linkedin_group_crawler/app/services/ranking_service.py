"""Ranking and post filtering logic."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils.datetime_utils import is_same_day, normalize_relative_time, parse_target_date


def compute_score(post: dict[str, Any]) -> int:
    """Compute post score from engagement values."""

    return int(post.get("likes", 0)) + int(post.get("comments", 0)) + int(post.get("reposts", 0))


def enrich_and_filter_posts(
    posts: list[dict[str, Any]],
    target_date: str | None,
    crawl_time: datetime,
) -> tuple[list[dict[str, Any]], datetime.date]:
    """Normalize timestamps, compute score, and keep posts matching the target day."""

    target_day = parse_target_date(target_date, crawl_time)
    filtered_posts: list[dict[str, Any]] = []

    for post in posts:
        normalized_dt = normalize_relative_time(post.get("posted_at_raw", ""), crawl_time)
        post["posted_at"] = normalized_dt.isoformat() if normalized_dt else None
        post["score"] = compute_score(post)
        if normalized_dt and is_same_day(normalized_dt, target_day):
            filtered_posts.append(post)

    return filtered_posts, target_day


def pick_top_post(posts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the top post using score, then likes as tie-breaker."""

    if not posts:
        return None
    return max(posts, key=lambda post: (post.get("score", 0), post.get("likes", 0)))


def _parse_posted_at_datetime(post: dict[str, Any]) -> datetime | None:
    raw = post.get("posted_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def select_most_recent_posts(posts: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Chọn các bài có ``posted_at`` mới nhất; không suy được thời gian thì xếp cuối, giữ thứ tự crawl."""

    if limit <= 0 or not posts:
        return []

    annotated: list[tuple[datetime | None, int, dict[str, Any]]] = []
    for index, post in enumerate(posts):
        annotated.append((_parse_posted_at_datetime(post), index, post))

    with_dt = [(dt, ix, post) for dt, ix, post in annotated if dt is not None]
    without_dt = [post for dt, ix, post in annotated if dt is None]

    with_dt.sort(key=lambda item: item[0], reverse=True)

    picked: list[dict[str, Any]] = [post for _, _, post in with_dt[:limit]]
    remaining = limit - len(picked)
    if remaining > 0:
        picked.extend(without_dt[:remaining])
    return picked
