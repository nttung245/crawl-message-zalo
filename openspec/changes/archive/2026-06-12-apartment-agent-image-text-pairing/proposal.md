## Why

The apartment agent grouper (`app/modules/apartment_agent/grouping.py`) currently groups Zalo messages using a **time-window + same-sender** rule (default 3 min). On the most recent test run against the `Elite24 Apartment` group, **50 messages collapsed into 3 groups with `max_group=20`** — 20 same-sender messages within minutes were merged into a single "listing", all text bodies concatenated and all image URLs unioned, then shipped to the LLM as one prompt. The LLM cannot untangle which text is the description and which images belong to which apartment, so **images from one listing leak into another** in the GoDaNang sync output. This is a correctness gap, not a UX bug: it silently corrupts data sent to the downstream villa table.

The real boundary between two listings is **content type** (text vs image), not time. A broker posts `1 text + N images` per listing, then starts a new listing with a new text message. We should use that structural signal instead of (or in front of) the time fallback.

## What Changes

- Replace the time-only grouping walk with a **content-type-driven** walk. A group is **closed** at the first `text` after a `text`, the first `text` after an `image-only` group, on every sender change, on every deleted/sticker/system message, on a hard size cap, and on a time-gap fallback.
- Add a per-message **content type classifier** (`text_only` / `image_only` / `mixed`) derived from the existing `text` and `image_urls` fields — no new schema, no new I/O.
- Add a **hard cap on group size** (default 4 messages) so a runaway power-user post cannot merge 20 messages into one group.
- Add two new env vars `AGENT_MESSAGE_GROUP_MAX_SIZE` and `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES` (defaults 4 and 1). The old `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` continues to work as the time fallback for one release.
- Enrich the existing observability log with the per-group **content type pair** (`text+3img`, `2img`, `text`, …) so we can spot over- and under-grouping in production.
- Add new test cases for the boundary conditions and the cap, leave the existing 33 grouping tests passing.
- **No frontend changes.** The existing `source_message_ids` field already exposes the group composition.

## Capabilities

### New Capabilities

- `apartment-agent-image-text-pairing`: pre-LLM grouping of consecutive same-sender Zalo messages into apartment-listing-shaped groups. Each group is bounded by content-type boundaries (text-text, text-after-images), a hard size cap, and a time-gap fallback. The grouper remains a pure function over the existing message dict shape — no DB, no LLM, no async.

### Modified Capabilities

- *(none)* — the existing in-flight `apartment-agent-group-messages-by-sender-time` change is still active in the changes folder (manual verification tasks 6.3/6.4 pending). This new change is a follow-up that *replaces the grouping rule*; once implemented, the older change's grouping section becomes obsolete and should be archived. No existing `openspec/specs/` capability changes — those three specs (`zalo-broadcast-target-fixes`, `zalo-campaign-soft-warnings`, `zalo-worker-selector-fix`) are unrelated.

## Impact

**Backend (Python):**
- `app/modules/apartment_agent/grouping.py` — replace the walk in `group_messages` with the content-type-driven version; add `_classify_content_type(msg)`. Add `max_messages_per_group: int = 4` and `time_fallback_minutes: int = 1` parameters. Enrich the observability log with per-group content type pair.
- `app/modules/apartment_agent/config.py` — add `message_group_max_size: int = 4` and `message_group_time_fallback_minutes: int = 1` to `ApartmentAgentSettings`. Alias the old `message_group_window_minutes` to the new `time_fallback_minutes` for one release.
- `.env.example` — document `AGENT_MESSAGE_GROUP_MAX_SIZE=4` and `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES=1`. Mark `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` as legacy.
- `app/modules/apartment_agent/pipeline.py` — pass the new params into `group_messages` in all 4 call sites (`extract_only`, `extract_only_streaming`, `process_messages`, `preview_only`).
- `app/modules/apartment_agent/router.py` — read the new settings in `/test-extract`, `/preview`, `/process` and thread them through to the pipeline helpers.

**Tests (pytest):**
- `tests/test_apartment_agent_grouping.py` — add ~9 cases for the new boundary conditions (text-text, text-after-images, cap, time fallback, image album) and assert the enriched log shape. Existing 33 cases must continue to pass — any that fail because they relied on a 4+ message time-only group get an explicit cap override.

**Frontend (Next.js):** none. The `source_message_ids` field already shows group composition in the Agent tab; smaller groups just render smaller N.

**Migration / data:** none. `zalo_messages` schema is unchanged.

**Risk:** under-grouping — a single listing with 5 photos can be split into 2 groups (text+first-3-images, then 2 more images). Both groups go to the LLM, the dedup layer catches the duplicate villa, but LLM cost roughly doubles for the affected run. The cap is env-tunable so we can raise it if we see this in production. Mitigation: start with `AGENT_MESSAGE_GROUP_MAX_SIZE=4` (covers 1-text + 3-photos which is the 90th percentile of real Zalo listings in our crawls).
