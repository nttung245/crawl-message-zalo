## Context

The Agent tab in the Zalo crawler is the bridge between raw Zalo group
chats and the GoDaNang website. Today the pipeline looks like this:

```
Zalo group chat
  → POST /api/zalo/crawl  (writes zalo_messages rows; messages_collected,
                            images_found tracked in job.progress)
  → POST /api/apartment-agent/test-extract  (LLM only; no dedup/sync;
                                              currently fails with
                                              opaque 500 "Internal
                                              Server Error" when env
                                              config is wrong)
  → POST /api/zalo/villa-sync  (LLM extract + dedup + POST/PUT to
                                GoDaNang villas table; irreversible
                                from the operator's perspective)
```

Three problems block production use of this flow:

1. **Errors are opaque.** When `/test-extract` fails, the FE shows
   `API 500: Internal Server Error: <Type>: <msg>`. The user cannot
   tell whether `LLM_API_KEY` is missing, whether the OpenAI-compatible
   provider returned an HTML error page, or whether the GoDaNang
   Supabase REST call 500'd. There is no `request_id` to grep for in
   logs, and the global exception handler in `app/main.py:234-247`
   only logs the message string, not the full traceback.
2. **There is no preview.** Going from "see what the LLM extracted"
   to "row appears on GoDaNang" requires no human review. A bad
   extraction becomes a public listing in one click.
3. **The crawl finishes silently.** The Crawl tab's `InlineBanner` only
   shows "Đã tạo N job" — the per-job "Tin nhắn: N / Ảnh: M" counters
   are computed in `useZaloCrawlerFlow.ts:1476-1497` but never rendered.
   `ZaloCrawlProgressPanel` is built and correctly wired to the hook's
   `summary` / `jobs` fields; it is simply not mounted.
4. **The villas column mapping is undocumented and unverified.** Two
   in-flight OpenSpec changes (`zalo-apartment-filter-pipeline`,
   `zalo-to-godanang-villa-sync`) describe columns
   (`selling_price`, `owner_name`, `zalo_link`) that the
   implementation in `app/modules/apartment_agent/sync.py:47-84` does
   not actually write. The implementation is the source of truth, but
   the implementation has never been verified against the live
   `villas` table in the GoDaNang project.

## Goals / Non-Goals

**Goals:**

- Make every failure in the Agent flow surface a typed cause the
  operator can act on (missing env var, LLM auth, LLM schema
  mismatch, GoDaNang REST 4xx/5xx).
- Give the operator a preview-and-approve workflow between
  extraction and write. Nothing reaches GoDaNang without an
  explicit "Gửi N cái đã chọn" click.
- Add a cheap classifier step so non-listing messages (chat,
  stickers, reactions, off-topic) never consume the LLM extraction
  budget and never reach preview.
- Surface message/image counts on the Crawl tab so the operator
  sees the crawl actually completed.
- Verify the `villas` column mapping against the live GoDaNang
  project, document it as the canonical spec, and supersede the
  stale `zalo-apartment-filter-pipeline` delta.

**Non-Goals:**

- No changes to GoDaNang's frontend or its realtime subscription.
- No schema changes to GoDaNang's `villas` table. We only write to
  columns that already exist.
- No changes to the LinkedIn or Facebook modules.
- No new npm/pip dependencies. The classifier reuses the existing
  OpenAI-compatible LLM client (`app/modules/apartment_agent/extractor.py:53`).
- No push-to-remote, no PR creation, no auto-archive of the
  superseded OpenSpec changes (the user will archive them after
  this change ships).
- No removal of the existing `villa_sync` endpoint. The new
  `listing_ids` parameter is additive and optional.

## Decisions

### 1. Classifier runs before extraction, in the same LLM client

**Decision:** `app/modules/apartment_agent/classifier.py::is_apartment_listing(text) -> ClassificationResult` is a small function that uses the same `_get_client()` (OpenAI structured output) as `extractor.py`. The system prompt is a tight "yes/no" with `is_listing`, `reason`, `confidence`. No new LLM provider, no new dependency.

**Why:** The proposal text already commits to a classifier-first flow. Reusing the existing client means no new env vars, no new failure modes, and the same `batch_concurrency` semaphore gates both stages.

**Alternative considered:** Use a regex/keyword pre-filter (no LLM) for the classifier. Rejected because Vietnamese real-estate language is irregular ("phòng trống", "còn 1 căn", "giá thương lượng") and a regex misses too much. The LLM cost is bounded by the same `batch_concurrency` (5) and a `gpt-4o-mini` call is cheap.

### 2. Preview endpoint is a pure read, no side effects

**Decision:** `POST /api/apartment-agent/preview` accepts either `{texts: string[]}` or `{group_name: string, limit?: int}` and returns:

```json
{
  "classifications": [{"message_id": "...", "text": "...", "is_listing": true, "reason": "...", "confidence": 0.97}],
  "listings": [{
    "raw_message_id": "...",
    "is_listing": true,
    "payload": { /* exact body that sync.insert_apartment would POST to GoDaNang */ },
    "operation": "insert" | "update" | "skip",
    "existing_villa_id": "uuid-or-null"
  }],
  "summary": {"messages_seen": N, "classified_listing": K, "extracted_ok": K, "would_insert": A, "would_update": B, "would_skip": C}
}
```

The `payload` field is the literal output of `sync._build_insert_payload` (or `_build_update_payload` if a dedup match is found). The endpoint does NOT call `httpx` against GoDaNang. The "operation" field is computed by calling `sync.find_existing_villa` against the GoDaNang REST endpoint (a read), so the operator sees "this is an update, not an insert" before clicking Send.

**Why:** Operators need to see the exact JSON that will be sent. Rendering the payload as text in a `<pre>` block is a "no surprises" guarantee. Computing the dedup decision in preview means "Gửi N cái đã chọn" can be a single `villaSync({listing_ids: [...]})` call with no race between preview and write.

**Alternative considered:** Have preview return only the `ApartmentListing` and let the FE compose the payload. Rejected because the payload contains fields computed in Python (slug, price_label, the multi-line description that folds in contact info). The FE cannot reproduce this without copy-pasting `sync.py` logic into TypeScript.

### 3. Typed error envelope, not exception strings

**Decision:** Add a small set of typed Pydantic errors in
`app/modules/apartment_agent/schemas.py`:

```python
class ApartmentAgentError(BaseModel):
    kind: Literal["missing_config", "llm_auth", "llm_schema", "llm_rate_limit", "godanang_rest", "validation"]
    message: str
    missing: list[str] = []        # for kind=missing_config
    status: int | None = None      # upstream status for godanang_rest
    request_id: str                # uuid4 set at request entry, used in logs
```

The `/test-extract` and `/preview` routes call `validate_settings()` and return this envelope on 400/500 instead of letting an SDK exception bubble into the global handler. The global handler in `app/main.py` is extended (not replaced) with a small `ApartmentAgentError` branch that returns `{success: false, error: <envelope>}`.

**Why:** The user said the error reads `API 500: Internal Server Error: <Type>: <msg>`. That is exactly the failure mode: the message string is unhelpful and there is no `request_id` to grep for. A typed envelope with `kind=missing_config` + `missing=["LLM_API_KEY"]` lets the FE render "Thiếu LLM_API_KEY trong `.env`" with a link to `.env.example`.

**Alternative considered:** Stick with `HTTPException(detail=...)` and have the FE parse the detail string. Rejected because the global handler already wraps `Exception` and string parsing is fragile across LLM SDK versions.

### 4. FE: preview cards + per-listing toggle, no global "Send all"

**Decision:** The Agent tab's preview section renders one card per
classified listing. Each card has:

- Title, district, area, price, `price_label` (read-only summary).
- `<pre>{JSON.stringify(payload, null, 2)}</pre>` (read-only payload).
- Operation badge: `INSERT` (green) / `UPDATE` (blue) / `SKIP` (gray,
  with reason).
- Per-card toggle: "Gửi" (default on for INSERT, off for UPDATE,
  off for SKIP).

A footer "Gửi N cái đã chọn" button calls the existing
`villaSync({listing_ids})` helper. While sending, the per-card
toggle is disabled and a progress bar shows "N / total". On
completion, the card flips to "Đã gửi" with a link to the GoDaNang
admin (out of scope to build — we just render the URL with the
`villa_id`).

**Why:** The user explicitly asked for "1 hướng tiếp cận thông minh hơn" (a smarter approach) — a per-listing review with an explicit "send" is the human-in-the-loop they want. The operation badge is critical: the operator sees "this is an UPDATE" before clicking, so a duplicate "Insert" is impossible by construction.

**Alternative considered:** Auto-push everything to GoDaNang and rely on dedup. Rejected because the user's complaint is exactly that they cannot see what the Agent is doing.

### 5. Mount the existing `ZaloCrawlProgressPanel`, don't build a new one

**Decision:** Render `<ZaloCrawlProgressPanel jobs={flow.jobs} summary={flow.summary} />` inside `ZaloCrawlerConfigCard.tsx` after the group list. Add a `toast.success("Đã tạo N job crawl")` in `useZaloCrawlerFlow.ts:launchRows` immediately after the success count is computed. Add a `toast.info("Job ${id}: ${messages} tin nhắn, ${images} ảnh")` inside the existing SSE handler that already updates `job.progress`.

**Why:** The component is built (`components/features/zalo/dashboard/ZaloCrawlProgressPanel.tsx`), correctly wired to the hook, and currently dead code. The toast calls are the smallest possible change to give the operator the "I clicked, something happened" feedback that the user complained was missing.

**Alternative considered:** Build a new "Crawl Results" tab. Rejected because the data is already in memory — switching tabs hides it. The user wants to see the counts where the action happened.

### 6. Column mapping is verified, not assumed

**Decision:** Before writing any spec, run a one-off read-only query against the GoDaNang Supabase project:

```sql
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'villas'
order by ordinal_position;
```

The result is recorded in the `apartment-agent-villa-column-mapping` spec as the canonical column list. The `apartment-agent-villa-push` pytest suite asserts that every key in `_build_insert_payload` exists in the column list. If a column is missing, the test fails and the implementation is updated to either (a) drop the field or (b) add a schema migration to GoDaNang (out of scope — we'd surface the error and ask the user).

**Why:** The user said the spec drifted from the code. Trusting the code without verifying against the live table is a recipe for the same drift to happen again. A one-time SQL query locks the mapping.

**Alternative considered:** Read the GoDaNang frontend's `VillaCard` props and reverse-engineer the columns. Rejected because the FE may render a subset of the columns — `select *` is the only safe assumption.

### 7. Supersede, don't archive

**Decision:** Edit `openspec/changes/zalo-apartment-filter-pipeline/proposal.md` and `openspec/changes/zalo-to-godanang-villa-sync/proposal.md` to add a "**Status: SUPERSEDED by `apartment-agent-preview-and-villa-push`**" banner at the top. Do not move them to `archive/`. The user will archive after this change ships and the e2e smoke test passes.

**Why:** OpenSpec's `archive` workflow requires a separate decision. A banner makes the relationship explicit without losing the historical context of the in-flight specs.

## Risks / Trade-offs

- **Classifier cost and latency**: A second LLM call per message roughly
  doubles the latency and the API cost. Mitigation: `batch_concurrency=5`
  already gates both stages; the classifier prompt is small
  (~150 tokens); and the classifier is the gate, so extraction is
  skipped entirely for non-listing messages. Net effect is usually a
  *reduction* in cost, not an increase.

- **Preview endpoint is a read but performs an HTTP call to GoDaNang**
  (`find_existing_villa`). If GoDaNang Supabase is down, preview 500s
  even though it didn't write anything. Mitigation: the typed error
  envelope with `kind=godanang_rest, status=...` tells the operator
  "GoDaNang is down, try again" — which is exactly the right message.

- **The "Send N" button calls the existing `villaSync` endpoint with
  `listing_ids`**. If the user clicks Send twice quickly, the dedup
  in `villa_sync_service` should prevent double-writes, but the UI
  disables the button on click and the per-card toggle on completion.
  Mitigation: the e2e test in subunit 6 asserts dedup is idempotent.

- **Toast spam**: If a crawl produces 20 jobs and each completion
  fires a toast, the operator's screen is buried. Mitigation: cap
  toasts at one per job, with a 3s `toast.dismiss()` for older ones;
  the big-number cards in `ZaloCrawlProgressPanel` are the canonical
  surface for cumulative counts.

- **Column-mapping drift**: The GoDaNang team could add/rename/remove
  `villas` columns at any time. Mitigation: the pytest smoke test in
  subunit 6 re-runs the `information_schema.columns` query (or, more
  pragmatically, a `select` against each column we write to) and
  fails loudly if the columns are missing. This becomes part of the
  CI suite.

- **The classifier may misclassify real listings as non-listings**,
  causing them to be silently dropped. Mitigation: log every
  `is_listing=false` decision with the `reason` field so the operator
  can audit; expose a "show non-listings" toggle in the Agent tab
  preview so misclassified messages are visible (and can be
  manually pushed via the existing `villa_sync` flow with
  `listing_ids=[]`).
