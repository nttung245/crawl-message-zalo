## Context

The apartment agent pipeline (`app/modules/apartment_agent/pipeline.py`) currently calls `extract_batch()` which iterates a flat list of Zalo messages and runs one LLM call per message. The list is built in `router.py` by querying `zalo_messages` ordered by `created_at` (no explicit ORDER BY, so DB order), each row joined with its `zalo_message_assets`. The problem: Vietnamese Zalo real-estate groups split a single listing across multiple consecutive messages from the same sender (text-only → image-only, or image-only → text-only). Today's per-message extraction either drops the listing (image-only message has no text) or splits it (text-only message has no images).

The fix is a **pre-LLM grouping step** that runs in the pipeline. The grouper is a pure function `group_messages(messages, window_minutes) -> list[MessageGroup]` so it can be unit-tested without the LLM. Existing tests in `tests/test_apartment_agent_pipeline.py` already mock the LLM at the `extract_listing` boundary, so the integration test can be added there.

## Goals / Non-Goals

**Goals:**
- Detect that consecutive same-sender messages within a time window belong to the same listing.
- Merge their text bodies and image URL sets into a single extraction record.
- Preserve the ability to trace back to every contributing `source_message_id` (for dedup, preview, FE display).
- Be tunable via `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` env without code change.
- Be deterministic (same input → same groups) and side-effect-free (pure function, no DB calls).

**Non-Goals:**
- Cross-sender grouping (a conversation between two posters is two listings).
- Re-grouping already-grouped outputs.
- Persisting groups back to `zalo_messages` (groups are ephemeral pipeline state).
- Changing the LLM schema or prompt.
- Streaming the grouper (it's a single quick pass; even 200 messages is microseconds).
- The `/preview` 500 / SSE-streaming concern — that's a separate follow-up change.

## Decisions

### D1: Pure-function grouper in a new module
**Choice:** `app/modules/apartment_agent/grouping.py` with `group_messages(messages, window_minutes) -> list[MessageGroup]`. No DB, no I/O, no async.
**Rationale:** testable in isolation, no risk of breaking the LLM path. Other pipelines (LinkedIn, Facebook) can reuse it later.
**Alternatives considered:** inline in `pipeline.py` — rejected because it mixes concerns and is harder to test. Pydantic `validator` on a messages list — rejected because we want the grouper to be optional/configurable, not declarative.

### D2: Sort by `timestamp_text` first, fall back to `created_at`, then `time_text`
**Choice:** Try `timestamp_text` (parsed Zalo date+time). If unparseable, use `created_at`. If both missing, treat as a singleton (no group).
**Rationale:** `timestamp_text` is human-readable Zalo format ("12/06/2026 14:35"). `created_at` is a DB timestamptz. `time_text` alone ("14:35") has no date and is unreliable for cross-day or late-night messages. Without a usable timestamp, grouping is unsafe — singletons are the safe default.
**Alternatives considered:** use `created_at` everywhere — rejected because it can drift from message time (crawl latency, replay jobs).

### D3: Group key is `(sender_id or sender_name)`, both lowercased + trimmed
**Choice:** `sender_id` when present, else normalized `sender_name`. Missing both → singleton.
**Rationale:** Zalo sometimes assigns a new per-message `qid` so `sender_id` may not be stable. `sender_name` is the human-typed display name and is the practical identity in the chat.
**Alternatives considered:** require `sender_id` — rejected for the same instability. Hash both — over-engineering.

### D4: Default 3-minute window, env-configurable
**Choice:** `ApartmentAgentSettings.message_group_window_minutes: int = 3`. Override via `AGENT_MESSAGE_GROUP_WINDOW_MINUTES`.
**Rationale:** the observed Zalo pattern is "post text, then upload images from gallery, then optionally a price clarification" — usually <2 min total. 3 min gives slack for slow uploaders. Anything wider risks merging two distinct listings from power users.
**Alternatives considered:** 5 min (industry-default in some scrapers) — too wide for a one-poster-per-listing culture. 1 min — too tight, misses users who take a coffee break mid-post. Configurable env makes it tunable per-deployment.

### D5: Skip `is_deleted=True`, `type in {sticker, system}` messages; treat them as group boundaries
**Choice:** when walking the sorted list, if the current message is deleted/system/sticker, **close the current group** and start a new one (the message itself is dropped).
**Rationale:** a deleted message between two text messages means the user retracted something; safer to start a new listing. Stickers are noise. System messages ("X joined the group") are never listings.
**Alternatives considered:** silently include them in the group — rejected because they would corrupt the merged `text` and confuse the LLM.

### D6: Merged record shape
**Choice:** A `MessageGroup` Pydantic model with:
- `id: str` — first contributing message id (becomes the downstream "group id" / `raw_message_id`)
- `source_message_ids: list[str]` — all contributing ids, in chronological order
- `text: str` — `\n\n`-joined bodies, dropping empty/None
- `image_urls: list[str]` — first-seen-order deduped union
- `sender_id, sender_name` — from first message
- `timestamp_text, time_text, created_at` — from first message (earliest)
- `group_name` — from any message (same for all in a group)
**Rationale:** `raw_message_id` stays the first id (preserves the existing `TestExtractResult.raw_message_id` contract). `source_message_ids` is a new additive field — the FE uses it to display "Grouped from N" when N > 1.

### D7: Grouper activates only on the Supabase path
**Choice:** When `req.texts` is set (free-form input from the FE textbox), do **not** group. When `req.group_name` is set (Supabase fetch), group. Same for `/preview` and `/process`.
**Rationale:** `texts=[...]` is a deliberately curated list of full listings, not raw chat messages. Grouping would only confuse the user. The grouper is a pipeline-level concern, not an LLM concern.

### D8: Single log line per pipeline run with group-size distribution
**Choice:** After grouping, log `count=NN, groups=GG, max_group=MM, multi_groups=CC` (groups with >1 source message).
**Rationale:** cheap observability for detecting over-grouping in production. If `multi_groups` is high and users complain about merged listings, we know to lower the window.

## Risks / Trade-offs

- **Over-grouping two distinct listings** posted 2-3 min apart by the same power user → Mitigation: default 3 min is conservative; window is env-tunable; per-run group-size stats in the log.
- **Timezone bugs in `timestamp_text` parsing** → Mitigation: parse as local Zalo time (already what Zalo displays), treat as naive datetime, use `created_at` as authoritative fallback when parse fails.
- **`sender_name` collisions** (two different users with the same display name) → accepted risk; in real estate groups this is rare and the cost of splitting wrongly is the same as the cost of merging wrongly; same-sender posts within 3 min are overwhelmingly one listing.
- **Mid-conversation interruption** (a 5-min phone call breaks the window) → Mitigation: window is configurable; the next message becomes a new group, which the LLM may then fail to extract (no text/images together) — same as today's behavior, no regression.
- **Extra memory for the merged text** → negligible; 60 messages × ~500 chars = 30 KB, well under any threshold.

## Migration Plan

- Add `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` to `.env.example` (commented out). New env var has a default, so existing deployments work without changes.
- Deploy backend; no DB migration; no schema migration.
- Observe group-size logs for 1 week; tune window if needed.
- Rollback: set `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=0` (treated as "no grouping") or revert the PR.

## Open Questions

- Should the grouper also be applied in the auto-process trigger (`ApartmentAgentSettings.auto_process`)? — *Decision: yes, same code path. No change needed.*
- Should the FE allow toggling grouping on/off? — *Decision: no, server-side only. Tuning is a deployment concern, not a per-run concern.*
- Should we surface grouping in the SSE progress events (`source_message_ids`) so the FE can show a real-time "N messages merged" badge during streaming? — *Defer: nice-to-have, not required for correctness. Add in a follow-up if users ask.*
