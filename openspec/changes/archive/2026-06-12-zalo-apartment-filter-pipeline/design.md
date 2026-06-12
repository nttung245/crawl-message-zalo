## Context

The Zalo crawler (`linkedin_group_crawler`) currently captures messages and images from Zalo web groups via Playwright. The pipeline today:

1. `message_parser.py` extracts text + image URLs from Zalo DOM
2. `supabase_service.save_message_assets()` downloads **all** images and uploads to Supabase Storage
3. `apartment_agent/extractor.py` processes text-only messages via LLM to extract `ApartmentListing` data
4. Results stored in crawler's Supabase — never reach GoDaNang

**Problems:**
- Storage grows unbounded (every sticker, avatar, reaction image gets stored)
- Agent only sees text, never receives image URLs
- Extracted listings stay in the crawler DB — no path to GoDaNang's `villas` table

**GoDaNang context:**
- Separate Supabase project (`qpenyftllbvwdstcjdkw.supabase.co`)
- `villas` table with `type` column supporting `'apartment'` value
- Already has business fields: `import_price`, `selling_price`, `owner_name`, `zalo_link`, etc.
- Frontend already subscribes to realtime `villas` changes
- Crawler `.env` already has `GODANANG_SUPABASE_URL` and `GODANANG_SUPABASE_KEY`

## Goals / Non-Goals

**Goals:**
- Filter messages by text **before** downloading images — only apartment listings get images stored
- Extract structured apartment data from confirmed listing messages
- Upsert to GoDaNang `villas` table with consistent schema mapping
- Support both auto-trigger (after crawl) and manual/API trigger
- Reduce Supabase Storage usage by ~80-90%

**Non-Goals:**
- Image recognition / computer vision (we filter by text, not image content)
- Real-time streaming processing (batch is fine)
- Modifying GoDaNang's `villas` schema (we write to existing columns)
- Handling video or non-image media from Zalo
- Multi-language extraction (Vietnamese only for now)

## Decisions

### D1: Text-first filtering (not image-first)

**Decision**: Classify message text FIRST, then download images only for confirmed listings.

**Why**: LLM text classification is cheap (~100 tokens) vs downloading + uploading images (bandwidth + storage). Most messages are not apartment listings, so we skip 90%+ of image downloads entirely.

**Alternative considered**: Download all images, then filter by image analysis. Rejected — defeats the purpose of reducing storage.

### D2: Two-phase LLM approach (classify → extract)

**Decision**: Separate the LLM call into two phases:
1. **Classifier**: Binary yes/no — "Is this message about an apartment for sale/rent?"
2. **Extractor**: Full structured extraction of apartment fields

**Why**: Classifier is a cheap, fast call (~50 tokens). We only pay for the expensive extraction call on confirmed listings. This also makes the classifier reusable as a standalone filter.

**Alternative considered**: Single combined prompt. Rejected — wastes tokens on extraction for non-listing messages.

### D3: Write to GoDaNang villas table (not a new table)

**Decision**: Use the existing `villas` table with `type='apartment'`.

**Why**: GoDaNang frontend already reads from `villas`, admin panel already manages villas, realtime subscriptions already exist. Zero frontend changes needed.

**Alternative considered**: New `apartments` table. Rejected — would require frontend changes, duplicate admin UI, separate realtime subscriptions.

### D4: Upsert by slug (dedup strategy)

**Decision**: Generate a deterministic slug from apartment name + area + price. Use `ON CONFLICT (slug) DO UPDATE` for upserts.

**Why**: Same apartment may be posted multiple times in different groups. Slug-based dedup prevents duplicates while allowing price updates.

**Alternative considered**: Dedup by message_id. Rejected — same apartment can have different message IDs across groups.

### D5: Image URLs from Supabase assets table (not re-download from Zalo)

**Decision**: After classification passes, read image URLs from `zalo_message_assets` table (already stored by the existing crawl pipeline). Download from there for GoDaNang storage.

**Why**: The existing crawl pipeline already downloads and stores images. We just need to filter which ones to copy to GoDaNang storage. This avoids re-crawling Zalo pages.

**Alternative considered**: Re-extract images from Zalo DOM. Rejected — wasteful, the crawler already captured them.

### D6: GoDaNang Supabase client as a separate service

**Decision**: Create a `godanang_service.py` module that wraps the GoDaNang Supabase client, separate from the existing `supabase_service.py`.

**Why**: Clean separation of concerns. The crawler's Supabase is for message storage; GoDaNang's Supabase is for user-facing data. Different URLs, different auth, different schemas.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| LLM classifier false negatives (misses real listings) | Log low-confidence results for manual review; tune prompt over time |
| LLM classifier false positives (non-listings get through) | Acceptable — worst case is a few extra images stored; extractor will produce incomplete data and can be filtered |
| GoDaNang schema changes break our mapping | Pin to known columns; `mapVillaToDb` function centralizes mapping |
| GoDaNang Supabase downtime | Retry with exponential backoff; failed upserts logged for retry |
| Slug collisions (different apartments, same slug) | Include price in slug generation; collision probability is negligible |
| Token cost for LLM calls | Classifier is ~50 tokens; extractor ~200 tokens. At 1000 messages/day, cost is negligible |

## Migration Plan

1. **Phase 1**: Add `godanang_service.py` with Supabase client + upsert logic (no pipeline change)
2. **Phase 2**: Add classifier + image filter to apartment_agent module
3. **Phase 3**: Wire into crawler auto-trigger (after existing crawl completes)
4. **Phase 4**: Add manual API endpoint for testing
5. **Rollback**: Feature flag — if disabled, falls back to current "store everything" behavior
