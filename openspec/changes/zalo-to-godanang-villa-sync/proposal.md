## Why

The Zalo crawler extracts apartment/room listings from Zalo group chats but currently only stores them in a generic `zalo_messages` table. There's no pipeline to push this data into the godanang project's `villas` table, which is what end users actually see. Manual data entry is slow and error-prone. We need an automated flow: **Crawl → Filter/Extract → Sync to villas table** — so new listings appear on the godanang site automatically.

## What Changes

- **New backend pipeline** in `crawl-message-zalo` that reads crawled Zalo messages, uses an LLM Agent to extract structured apartment data (name, address, floor, room number, price, amenities, status), and syncs to the godanang `villas` Supabase table.
- **Deduplication logic**: match existing villas by description fingerprint (address + floor + room). Same address with different room/floor = separate villa. If a villa already exists, PUT (update) instead of POST (create).
- **Image handling**: images are only POSTed on first creation. On updates, all other fields are updated but images are skipped (API cost saving).
- **Rented status detection**: if the Agent determines a room is rented/occupied, set `status = 'inactive'` so it appears grayed out on the godanang main page.
- **Timestamp-based incremental sync**: track the latest `created_at` in the villas table and only process Zalo messages newer than that timestamp to avoid re-processing old data.
- **Agent prompt engineering**: a carefully crafted prompt that both filters relevant apartment messages AND outputs structured JSON matching the villas table schema.

## Capabilities

### New Capabilities

- `villa-sync-pipeline`: End-to-end pipeline that syncs extracted Zalo apartment data to the godanang villas table — includes dedup, POST/PUT logic, image handling, and rented status detection.
- `villa-agent-prompt`: LLM Agent prompt that filters apartment-related messages and extracts structured data matching the villas table schema (name, type, area, price, description with address/floor/room info, amenities, status).

### Modified Capabilities

(none — this is a new integration)

## Impact

- **crawl-message-zalo backend**: new module `app/modules/zalo/services/villa_sync_service.py` (or similar) + new API endpoint for triggering sync
- **crawl-message-zalo Agent**: new/updated apartment agent with enhanced prompt for villa extraction
- **godanang Supabase**: writes to existing `villas` table (no schema changes needed — all columns already exist)
- **godanang frontend**: `VillaCard` component should visually indicate `is_sold_out` or `status = 'inactive'` villas (grayed out) — currently these fields exist but aren't rendered on the public page
- **Dependencies**: both projects share the same Supabase instance (or the crawl project needs write access to godanang's Supabase)
