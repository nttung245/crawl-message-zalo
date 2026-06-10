## Context

Two separate projects need to be connected:
- **crawl-message-zalo** (`/home/hostserver/Work/crawl-message-zalo`): Zalo crawler that collects messages from Zalo groups, stores them in Supabase `zalo_messages` table. Has an existing apartment agent that extracts structured data from messages.
- **godanang** (`/home/hostserver/Work/godanang`): Next.js tourism/accommodation site with a `villas` table in Supabase (32 columns: id, slug, name, type, area, capacity, price, description, status, images, amenities, etc.). Has POST/PUT/GET API endpoints at `/api/villas`.

Current state: the crawl project extracts apartment data but doesn't push it anywhere useful. The godanang project has the villas table but relies on manual data entry. The `villas` table already has all needed columns including `status` (active/inactive), `is_sold_out`, `description`, `images`, `amenities`, etc.

## Goals / Non-Goals

**Goals:**
- Automated pipeline: Zalo messages → LLM extraction → Supabase villas table
- Deduplication: same address + same room/floor = update; same address + different room/floor = new entry
- Incremental sync: only process messages newer than the latest villa `created_at`
- Image cost control: images only on initial POST, never updated
- Rented detection: mark villas as `status = 'inactive'` when Agent detects they're rented
- Strong Agent prompt that filters AND extracts in one pass

**Non-Goals:**
- Real-time sync (this is batch/on-demand, not webhook-triggered)
- Modifying the godanang villas table schema (all columns already exist)
- Image recognition/analysis (images are passed as URLs, not analyzed)
- Multi-language translation (godanang already has a background translation job)
- Modifying the existing apartment agent in crawl-message-zalo (we create a new specialized prompt)

## Decisions

### 1. Where to put the sync logic

**Decision**: New module in `crawl-message-zalo` backend (`app/modules/zalo/services/villa_sync_service.py`), not in godanang.

**Rationale**: The crawl project already has access to Zalo messages, the Agent extraction pipeline, and Supabase. Adding the sync logic here keeps the data flow in one place. Godanang only needs to expose its Supabase table (or API) — it doesn't need to know about Zalo.

**Alternative considered**: Add a webhook endpoint in godanang that receives extracted data. Rejected because it adds network complexity and godanang doesn't need to initiate the sync.

### 2. Dedup strategy: description fingerprint

**Decision**: Use a normalized `description` field as the dedup key. The Agent will generate a canonical description string like `"123 Nguyen Van Linh, Tang 5, Phong 502"` from the crawled data. Before inserting, query the villas table for existing entries with matching description patterns.

**Rationale**: The user explicitly wants to support "same address, different room/floor". A simple address match won't work. The description field captures address + floor + room + amenities, making it a natural fingerprint.

**Alternative considered**: Add a dedicated `fingerprint` column to villas. Rejected because it requires schema migration in godanang and the `description` field already serves this purpose.

### 3. POST vs PUT decision flow

```
For each extracted listing:
  1. Query villas table: SELECT id, images FROM villas WHERE description LIKE '%<address>%' AND name LIKE '%<room_identifier>%'
  2. If no match → POST (create new villa, include images)
  3. If match found → PUT (update existing villa by id, SKIP images field)
  4. If Agent says "rented" → PUT with status = 'inactive'
```

### 4. Image handling

**Decision**: On POST, include extracted image URLs in the `images` JSONB array. On PUT, completely omit the `images` field from the update payload — Supabase will preserve the existing value.

**Rationale**: Image extraction via API is expensive. Once images are stored, they should not be re-fetched or re-processed.

### 5. Timestamp-based incremental sync

**Decision**: Before running the sync, query `SELECT MAX(created_at) FROM villas` to get the latest villa timestamp. Then only fetch Zalo messages with `timestamp > latest_villa_created_at` from the `zalo_messages` table.

**Rationale**: Avoids re-processing thousands of old messages. The user explicitly requested this: "phong duoc them gan nhat tren supabase la vao 5h chieu => tap trung vao cac tin nhan sau 5h chieu hom do".

### 6. Agent prompt design

**Decision**: Single prompt that does both filtering AND extraction. The prompt will:
1. Receive a batch of Zalo messages (text only, no images)
2. Filter out non-apartment messages (greetings, spam, unrelated)
3. For apartment messages, extract structured JSON matching the villas table schema
4. Detect rented/occupied status from language cues ("da cho thue", "co nguoi o", etc.)

**Output format** (per message):
```json
{
  "is_apartment_listing": true,
  "name": "Can ho 2PN Nguyen Van Linh",
  "type": "apartment",
  "area": "Quan Hai Chau",
  "price": 8000000,
  "price_label": "8tr/thang",
  "capacity": 4,
  "description": "123 Nguyen Van Linh, Tang 5, Phong 502. 2PN, 1WC, co ban cong, may lanh, wifi.",
  "amenities": ["wifi", "may lanh", "ban cong"],
  "is_rented": false,
  "images": ["https://..."],
  "contact_phone": "0901234567",
  "contact_zalo": "0901234567"
}
```

## Risks / Trade-offs

- **[Risk] LLM extraction accuracy** → Mitigation: Use structured output (JSON mode) with strict schema validation. Add retry logic for malformed responses. Log failed extractions for manual review.

- **[Risk] Dedup false positives** (different rooms matched as same) → Mitigation: Use both address AND room identifier in the match query. If ambiguous, prefer POST (create new) over accidental overwrite.

- **[Risk] Supabase cross-project access** → Mitigation: The crawl project needs the godanang Supabase URL and service role key. Store as env vars (`GODANANG_SUPABASE_URL`, `GODANANG_SUPABASE_SERVICE_KEY`).

- **[Risk] Rate limits on Supabase/LLM API** → Mitigation: Process messages in batches of 10-20. Add delays between batches.

- **[Trade-off] Description-based dedup vs dedicated column** → Description-based is simpler but less precise. Acceptable for v1; can add a fingerprint column later if dedup accuracy is insufficient.

- **[Trade-off] Single prompt for filter+extract vs two-pass** → Single prompt is faster and cheaper but may be less accurate. Acceptable because the existing apartment agent already does this successfully.
