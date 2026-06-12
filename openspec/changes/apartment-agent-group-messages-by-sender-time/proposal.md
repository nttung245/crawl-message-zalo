## Why

The apartment agent currently treats every crawled Zalo message as an independent listing: each row from `zalo_messages` is fed to the LLM in its own `extract_listing` call. In practice, Vietnamese Zalo real-estate groups post listings across **multiple consecutive messages from the same sender**:

- Pattern A: text-only introduction → 1-N follow-up messages with images only
- Pattern B: image-only album first → text-only description after

Today both patterns produce broken output. The text-only message extracts the listing but `images=[]`; the image-only message gets `is_apartment_listing=false` (no text to extract from) and is dropped. **The listing is lost or split in two.** This is a correctness gap, not a UX bug — it directly reduces the number of apartments synced to GoDaNang.

## What Changes

- Add a **message-grouping preprocessor** in the apartment agent pipeline that sorts messages by timestamp and groups consecutive messages from the same sender within a sliding time window (default 3 minutes, configurable via env).
- The grouping step runs **before** the existing classifier + extractor. Each group yields one logical "listing" record whose `text` is the concatenation of all non-empty bodies and whose `image_urls` is the union of all attached URLs.
- The grouped record keeps a list of contributing `raw_message_ids` so dedup/preview output can still trace back to every source row.
- Grouping is **additive**: existing per-message callers (`/test-extract` with `texts=...`) bypass the grouper and continue to work unchanged. The grouper activates only when messages carry a sender + timestamp (i.e., the Supabase path used by `/test-extract?group_name=...`, `/preview`, and `/process`).
- Add a `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` env (default 3) so we can tune without a code change.
- No breaking changes to response shapes; `TestExtractResult.raw_message_id` becomes the **group id** (first message id) when grouping is active, and a new `source_message_ids: list[str]` field carries the full contribution.

## Capabilities

### New Capabilities
- `apartment-agent-message-grouping`: pre-LLM grouping of consecutive same-sender messages within a configurable time window, merging text and image URLs into a single logical listing record. Covers the ordering, windowing, edge cases (singleton groups, no-sender messages), and the new response field.

### Modified Capabilities
- *(none)* — existing specs (`zalo-broadcast-target-fixes`, `zalo-campaign-soft-warnings`, `zalo-worker-selector-fix`) are unrelated to apartment-agent extraction.

## Impact

**Backend (Python):**
- `app/modules/apartment_agent/grouping.py` — new module: `group_messages(messages, window_minutes) -> list[MessageGroup]`
- `app/modules/apartment_agent/pipeline.py` — `extract_only`, `extract_only_streaming`, `process_messages`, `preview_only` all call the grouper before extraction
- `app/modules/apartment_agent/extractor.py` — `extract_listing` signature stays the same; takes a `MessageGroup` via dict
- `app/modules/apartment_agent/router.py` — `/test-extract`, `/preview`, `/process` add `source_message_ids: list[str]` to `TestExtractListing` and `PreviewListing`
- `app/modules/apartment_agent/config.py` — new `message_group_window_minutes: int = 3`
- `app/modules/apartment_agent/schemas.py` — new `MessageGroup` schema
- `.env.example` — document `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3`

**Frontend (Next.js):**
- `types/zalo-api.ts` — add `source_message_ids: string[]` to `AgentTestListing` and `AgentPreviewListing`
- `components/features/zalo/dashboard/ZaloAgentTestPanel.tsx` — display "Grouped from N messages" badge on listings where `source_message_ids.length > 1`

**Tests (pytest):**
- `tests/test_apartment_agent_grouping.py` — new file: empty input, single message, all-text, all-image, mixed text+image, time-gap split, sender-gap split, timestamp parse failures, image dedup across messages
- `tests/test_apartment_agent_pipeline.py` (existing) — add one test verifying that a text+image pair produces one listing (not two) end-to-end

**Migration / data:** none — `zalo_messages` already has `sender_id`, `sender_name`, `created_at`, and `timestamp_text`.

**Risk:** if the window is too wide, two distinct listings posted 2-3 minutes apart by the same seller get merged. Mitigation: default 3 min is the industry-standard Zalo listing pattern; configurable; we log `group_size` so we can spot over-grouping in production.
