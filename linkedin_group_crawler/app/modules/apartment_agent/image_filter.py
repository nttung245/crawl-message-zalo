"""Image-URL extraction and filtering for apartment agent messages.

The Zalo crawler downloads each image CDN URL into the `zalo_message_assets`
table during the crawl (see `app.modules.zalo.services.supabase_service`).
Each row in that table has the original `source_url` and the
locally-mirrored `storage_url` (a Supabase Storage public URL).

For the apartment agent we want a small, ordered list of usable image
URLs that the LLM can reason about (unit count, decor, view cues,
etc.) — and that the sync layer can later attach to the GoDaNang
villa row.

Two public helpers:

- `filter_image_urls(urls)` — accept a flat list of strings, drop
  blanks, drop anything that does not look like an http(s) URL, and
  return at most N (the user requested "pass all", so the cap is set
  to 200 to guard against pathological crawls).
- `extract_image_urls_from_assets(assets)` — accept the raw value
  returned by PostgREST for the `assets:zalo_message_assets(*)` join
  (either `None`, a single dict, or a list of dicts), filter rows by
  `status` and URL shape, prefer `storage_url` over `source_url`, and
  return a flat list of strings.

We deliberately do NOT inspect the URL bytes here — the LLM is a
text-only model. We just give it a list of URLs as additional
context, and the sync layer copies them into the GoDaNang villas
table verbatim.
"""

from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlparse

# Cap is generous — user explicitly asked for "all URLs per message".
# 200 is the defensive ceiling to keep LLM prompt size bounded if a
# single Zalo message somehow accumulated hundreds of attachments.
MAX_IMAGE_URLS_PER_MESSAGE = 200

# Asset rows in `zalo_message_assets` are inserted with one of these
# statuses by the crawl pipeline. Only "uploaded" rows are safe to
# point GoDaNang at; everything else is partial / failed.
_ASSET_OK_STATUSES = frozenset({"uploaded", "ready", "ok", "done"})

# Whitelist of URL path extensions we treat as image-shaped. We do
# not download bytes — we just filter obvious non-image rows out
# of the prompt to keep token count sane.
_IMAGE_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".heic",
    ".heif",
)


def _looks_like_http_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return True


def _has_image_suffix(value: str) -> bool:
    """Return True if the URL path ends with a known image extension.

    The check is case-insensitive and ignores query strings. URLs
    without a recognised extension are still kept — many CDNs
    serve images at extensionless paths (e.g. signed Supabase
    Storage URLs). We only filter out URLs that *clearly* point
    to non-image content.
    """
    path = urlparse(value).path.lower().split("?", 1)[0]
    if not path:
        return True  # ambiguous — keep
    if any(path.endswith(suffix) for suffix in _IMAGE_SUFFIXES):
        return True
    # Common non-image extensions we want to drop.
    bad_suffixes = (
        ".mp4",
        ".mov",
        ".webm",
        ".mp3",
        ".wav",
        ".pdf",
        ".zip",
        ".doc",
        ".docx",
    )
    if any(path.endswith(suffix) for suffix in bad_suffixes):
        return False
    return True


def filter_image_urls(urls: Optional[Iterable[str]]) -> list[str]:
    """Return a deduped, ordered list of usable image URLs.

    Drops:
    - empty / non-string values
    - non-http(s) URLs
    - obvious non-image extensions (.mp4, .pdf, ...)

    Preserves the input order and de-duplicates while iterating.
    Caps the result at MAX_IMAGE_URLS_PER_MESSAGE.
    """
    if not urls:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        if not isinstance(raw, str):
            continue
        if not _looks_like_http_url(raw):
            continue
        if not _has_image_suffix(raw):
            continue
        if raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
        if len(out) >= MAX_IMAGE_URLS_PER_MESSAGE:
            break
    return out


def _coerce_asset_row(asset: object) -> Optional[dict]:
    """PostgREST may return the joined `assets` as None, a dict, or a list.

    We accept any of those and yield zero or one dict per call.
    """
    if asset is None:
        return None
    if isinstance(asset, dict):
        return asset
    if isinstance(asset, list):
        # Flatten one level — the join shape is always list-of-dicts, but
        # if a single dict leaks in (e.g. via mocks) we accept it.
        for item in asset:
            if isinstance(item, dict):
                return item
        return None
    return None


def extract_image_urls_from_assets(
    assets: object,
) -> list[str]:
    """Pull image URLs from a PostgREST `assets:zalo_message_assets(*)` value.

    Strategy:
    - For each asset row, prefer `storage_url` (locally mirrored on
      Supabase Storage) and fall back to `source_url` if missing.
    - Drop rows whose `status` is not in `_ASSET_OK_STATUSES`.
    - Run the resulting list through `filter_image_urls` for the final
      de-dupe / shape check / cap.
    """
    if assets is None:
        return []
    raw_urls: list[str] = []
    if isinstance(assets, list):
        for entry in assets:
            row = _coerce_asset_row(entry)
            if not row:
                continue
            status = (row.get("status") or "").lower()
            if status and status not in _ASSET_OK_STATUSES:
                continue
            url = row.get("storage_url") or row.get("source_url") or ""
            if isinstance(url, str) and url:
                raw_urls.append(url)
    else:
        # Single dict (rare; some PostgREST joins flatten for 0..1 rels).
        row = _coerce_asset_row(assets)
        if row:
            status = (row.get("status") or "").lower()
            if not status or status in _ASSET_OK_STATUSES:
                url = row.get("storage_url") or row.get("source_url") or ""
                if isinstance(url, str) and url:
                    raw_urls.append(url)
    return filter_image_urls(raw_urls)
