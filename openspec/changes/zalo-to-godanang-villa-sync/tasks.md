## 1. Environment & Configuration

- [x] 1.1 Add `GODANANG_SUPABASE_URL` and `GODANANG_SUPABASE_SERVICE_KEY` env vars to backend config (`app/core/config.py` or `app/modules/zalo/config.py`)
- [x] 1.2 Create a Supabase client helper for godanang DB access (separate from the existing crawl project's Supabase client)

## 2. Villa Sync Service

- [x] 2.1 Create `app/modules/zalo/services/villa_sync_service.py` with the main `sync_villas()` function
- [x] 2.2 Implement incremental message fetching: query `MAX(created_at)` from godanang villas, then fetch Zalo messages newer than that timestamp
- [x] 2.3 Implement dedup logic: query godanang villas by description pattern + name pattern to find matches
- [x] 2.4 Implement POST logic: create new villas with all fields including images
- [x] 2.5 Implement PUT logic: update existing villas with all fields EXCEPT images
- [x] 2.6 Implement rented status handling: set `status = 'inactive'` when `is_rented = true` from Agent output
- [x] 2.7 Add batch processing: process messages in batches of 20, with delays between batches
- [x] 2.8 Add dry-run mode: when `dry_run = true`, return planned operations without executing

## 3. Agent Prompt

- [x] 3.1 Create the villa extraction prompt in `app/modules/apartment_agent/` (new file `villa_prompt.py` or similar)
- [x] 3.2 Define the output JSON schema matching the villas table columns (name, type, area, price, price_label, capacity, description, amenities, is_rented, images, contact_phone, contact_zalo)
- [x] 3.3 Include Vietnamese rental status cues in the prompt (da cho thue, co nguoi o, cho thue, con trong, etc.)
- [x] 3.4 Include instructions for canonical description generation (address + floor + room + bedrooms + amenities)
- [x] 3.5 Wire up structured output (JSON mode) with schema validation and retry logic

## 4. API Endpoint

- [x] 4.1 Create `POST /api/zalo/villa-sync` endpoint in `app/modules/zalo/api/routes/`
- [x] 4.2 Accept optional `dry_run` boolean parameter
- [x] 4.3 Return sync summary JSON (total_messages_processed, apartments_found, new_villas_created, villas_updated, villas_marked_rented, errors)

## 5. Testing & Verification

- [ ] 5.1 Test incremental sync: verify only new messages are processed
- [ ] 5.2 Test dedup: same address + same room updates, same address + different room creates
- [ ] 5.3 Test image handling: POST includes images, PUT skips images
- [ ] 5.4 Test rented status: verify status = 'inactive' when Agent detects rented
- [ ] 5.5 Test dry-run mode: verify no DB changes are made
- [ ] 5.6 End-to-end test: crawl data -> Agent extraction -> villas table populated

## 6. Godanang Frontend (Optional Enhancement)

- [ ] 6.1 Update `VillaCard.tsx` to visually indicate `is_sold_out` or `status = 'inactive'` villas (grayed out style)
