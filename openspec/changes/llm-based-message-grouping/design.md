## Context

The apartment agent currently uses a heuristic content-type boundary walk (`grouping.py`, 412 lines) to split raw Zalo messages into listing groups before handing them to the LLM extractor. This heuristic has known failure modes:

- Follow-up messages ("Liên hệ 0905...") split from their listing because text-after-text triggers a boundary
- Image albums truncated at the hard `max_messages_per_group=4` cap
- Zero understanding of message semantics — a status update ("căn trên bán rồi") is treated as a new listing

The LLM extractor (`extractor.py`) already processes each group independently. By moving grouping into the LLM itself, we eliminate heuristic bugs and let the model understand the full conversation context.

## Goals / Non-Goals

**Goals:**
- Replace 412 lines of heuristic grouping code with a single LLM prompt (~60 lines)
- LLM understands natural message flow: text continuations, image albums, multi-listing posts, status updates
- Two-stage pipeline: Stage 1 groups messages into listings, Stage 2 extracts structured data per listing
- Stage 2 enriches listings with default villa config (commission, amenities)
- Detect listing lifecycle states: available, sold, deposited, on_hold, withdrawn

**Non-Goals:**
- Vision model integration (out of scope — image URLs are text-only context for now)
- Real-time streaming detection (still batch-based, triggered post-crawl)
- Multi-language support (Vietnamese-only, same as current)

## Decisions

### D1: Two-stage LLM pipeline

```
INPUT: 50-100 raw Zalo messages (30-min time window)
        │
        ▼
  ┌─────────────────────────────────────────┐
  │ STAGE 1: llm_group_messages()           │
  │                                         │
  │ Prompt: "You are analyzing Zalo group   │
  │ messages about apartment listings.      │
  │ Group them into listings..."            │
  │                                         │
  │ Output: List[ListingGroup] where        │
  │   ListingGroup = {                      │
  │     source_message_ids: [id, ...]       │
  │     text: "merged text\\n\\n..."        │
  │     image_urls: [url, ...]              │
  │     status_hint: "available" |          │
  │       "sold" | "deposited" | "on_hold" |│
  │       "withdrawn" | null                │
  │   }                                     │
  └──────────────┬──────────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────────┐
  │ STAGE 2: extract_listing() per group    │
  │                                         │
  │ Prompt: "Fill this villa record from    │
  │ the listing text. Use defaults where    │
  │ missing..."                             │
  │                                         │
  │ Concurrent: up to 5 parallel calls      │
  │ Output: VillaRecord (GoDaNang schema)   │
  └──────────────┬──────────────────────────┘
                 │
                 ▼
            dedup → sync → GoDaNang villas
```

**Rationale:** Two stages separate concerns. Stage 1 is "understand what happened" (cheap, 1 call per batch). Stage 2 is "fill the form" (expensive, N calls but parallelizable). This keeps tokens/cost controlled and lets each prompt be specialized and shorter.

**Alternative considered:** Single-stage (one prompt does both grouping and extraction). Rejected because: (a) combined prompt is too long and LLMs lose focus on long outputs, (b) can't parallelize extraction, (c) harder to debug which stage failed.

### D2: Batch window = 30 minutes, max 100 messages

Messages from the same Zalo group within a 30-minute window form one batch. Batches are created by sorting messages by timestamp and partitioning on 30-minute gaps. If a batch exceeds 100 messages, it's further split at the nearest message boundary.

**Rationale:** 30-minute windows naturally align with how users post (one listing session = a few messages within minutes, then nothing for hours). 100-message cap stays under GPT-4o-mini's 8K context comfortably (~1500 tokens for 100 messages).

### D3: Structured output via `response_format`

Stage 1 uses `client.beta.chat.completions.parse(response_format=StageOneOutput)` with a Pydantic model to guarantee valid JSON. Stage 2 uses the same mechanism with a GoDaNang villa schema.

**Rationale:** The existing `extractor.py` already uses `response_format=ApartmentListing`. This is proven and avoids JSON parsing errors entirely.

### D4: Default villa config as Python dict, not in prompt

```python
# default_config.py
DEFAULT_VILLA = {
    "commission_percent": 12,
    "amenities": ["bếp ga", "phòng tắm riêng", "wifi", "máy lạnh"],
    "type": "apartment",
    "listing_status": "available",
}
```

Stage 2 receives these defaults merged with LLM output — LLM-only fills fields it can determine, defaults fill the rest.

**Rationale:** Defaults live in code, not in the prompt. Changing defaults doesn't invalidate LLM output cache. The LLM only extracts what it can see; the rest is filled programmatically.

### D5: Status updates instead of new records

When Stage 1 detects `status_hint != "available"` (e.g., `sold`, `deposited`), the pipeline searches GoDaNang for the existing listing (by title or district+area fuzzy match) and updates its `listing_status` field. No new record is created. A `status_update_confirmed` boolean tracks whether the update succeeded.

**Rationale:** Prevents duplicate records when a user says "căn trên bán rồi". The existing listing gets marked instead of creating a ghost record.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| LLM hallucinates grouping — merges unrelated listings | Stage 1 output includes `source_message_ids` for traceability; log warnings when groups span >10 messages or >15 min |
| Token limit exceeded (very chatty group) | Hard cap at 100 messages/batch; split by time window |
| Stage 1 cost (1 extra LLM call per batch) | GPT-4o-mini is $0.15/1M input tokens; 100 messages ≈ 1500 tokens ≈ $0.0002 per batch |
| Status detection false positive | Only update status, never create; `status_hint` field is advisory — Stage 2 validates with more context |
| Old `grouping.py` consumers break | Delete `grouping.py` and all imports in one commit; pipeline.py is the only call site |
| Existing tests for `grouping.py` fail | Remove `test_apartment_agent_grouping.py`; add new tests mocking LLM responses |

## Migration Plan

1. Add `group_via_llm.py` and `default_config.py` (new files, no breakage)
2. Add Stage 1 prompt and Pydantic output schema to `schemas.py`
3. Update `pipeline.py` call sites to use `llm_group_messages()` instead of `group_messages()`
4. Update `extractor.py` Stage 2 prompt to accept listing objects with defaults
5. Remove `grouping.py` and related config fields
6. Remove `test_apartment_agent_grouping.py`; add new mocked LLM tests
7. Deploy with feature flag `APARTMENT_AGENT_LLM_GROUPING=true` for rollback safety

**Rollback:** Set flag to `false` → revert to heuristic grouper (code stays in git history of the archived `apartment-agent-image-text-pairing` change).

## Open Questions

- Should Stage 1 batch be pre-grouped by Zalo group_id (multi-group crawls)? Currently yes — each Zalo group gets its own batch.
- Status update: should we notify someone (n8n webhook) when a listing is marked sold? Out of scope for now, but the hook point exists in sync.py.
