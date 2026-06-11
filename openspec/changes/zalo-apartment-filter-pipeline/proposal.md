> **Status: SUPERSEDED** — This change has been superseded by
> `apartment-agent-preview-and-villa-push`. See
> `openspec/changes/apartment-agent-preview-and-villa-push/`.
> The parent will archive this change after the new change ships.

## Why

The Zalo crawler currently stores **all** images from every message into Supabase Storage, causing unbounded DB and storage growth. Most messages are irrelevant (casual chat, stickers, reactions). Meanwhile, the GoDaNang website needs a steady feed of apartment listings with images. By filtering **before** downloading images — only processing messages that are apartment sale/rental listings — we keep storage lean, reduce costs, and automatically populate the GoDaNang `villas` table with fresh apartment data in realtime.

## What Changes

- **Text classifier**: New LLM-based step that determines if a Zalo message is about an apartment for sale/rental before any image download occurs
- **Structured extractor**: Extracts apartment fields (name, area, price, owner, description, zalo_link) from confirmed listing messages
- **Image filter**: Only downloads `.jpeg` / `.png` images for confirmed apartment listings (skip stickers, avatars, irrelevant media)
- **GoDaNang upsert**: Maps extracted data to the existing `villas` table schema (`type='apartment'`) and upserts via GoDaNang Supabase client
- **Storage flow change**: Images are downloaded **after** text classification passes, not before — inverting the current "store everything" approach
- **Realtime delivery**: GoDaNang frontend already subscribes to `villas` table changes, so new apartments appear automatically

## Capabilities

### New Capabilities
- `apartment-text-classifier`: LLM-based binary classifier that determines if a Zalo message text describes an apartment listing (sale/rent)
- `apartment-image-filter`: Filters image URLs by extension (.jpeg, .png, .jpg) and downloads only confirmed listing images
- `godanang-villas-sync`: Extracts structured apartment data and upserts to GoDaNang's `villas` table with consistent schema mapping

### Modified Capabilities
<!-- No existing spec-level behavior changes required -->

## Impact

- **Code**: `apartment_agent/` module (extractor, pipeline, router, schemas), `zalo/services/supabase_service.py`, `zalo/api/routes/crawler.py`
- **New dependency**: GoDaNang Supabase client connection (env var `GODANANG_SUPABASE_URL` + `GODANANG_SUPABASE_KEY` already in `.env.example`)
- **APIs**: New endpoint for manual trigger / testing of the filter pipeline
- **Storage**: Significant reduction in Supabase Storage usage (only apartment images stored)
- **Cross-repo**: Writes to GoDaNang's `villas` table — schema must remain compatible
