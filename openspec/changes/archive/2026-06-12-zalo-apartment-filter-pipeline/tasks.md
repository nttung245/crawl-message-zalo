## 1. GoDaNang Supabase Client

- [ ] 1.1 Create `linkedin_group_crawler/app/modules/apartment_agent/godanang_service.py` with GoDaNang Supabase client (uses `GODANANG_SUPABASE_URL` + `GODANANG_SUPABASE_KEY` from env)
- [ ] 1.2 Implement `upsert_villa(data: dict)` function — upserts to `villas` table with `ON CONFLICT (slug) DO UPDATE`
- [ ] 1.3 Implement `upload_image_to_godanang(image_bytes, slug, filename)` — uploads to GoDaNang Supabase Storage under `apartments/{slug}/` path
- [ ] 1.4 Add `map_apartment_to_villa(extracted, images)` mapping function — converts extracted apartment data to villas schema columns (type, status, price_label, etc.)

## 2. Text Classifier

- [ ] 2.1 Create `linkedin_group_crawler/app/modules/apartment_agent/classifier.py` with `is_apartment_listing(text: str) -> ClassificationResult` function
- [ ] 2.2 Write classifier LLM prompt (binary yes/no, Vietnamese apartment sale/rent detection, confidence score)
- [ ] 2.3 Define `ClassificationResult` schema in `schemas.py` — fields: `is_listing: bool`, `confidence: float`, `reason: str`
- [ ] 2.4 Add logging for classification results (message_id, is_listing, confidence, timestamp)

## 3. Image Filter

- [ ] 3.1 Create `linkedin_group_crawler/app/modules/apartment_agent/image_filter.py` with `filter_image_urls(urls: list[str]) -> list[str]` — keeps only .jpeg, .jpg, .png
- [ ] 3.2 Implement `download_images_from_assets(supabase, message_id) -> list[bytes]` — reads `storage_url` from `zalo_message_assets` table and downloads image bytes
- [ ] 3.3 Implement `transfer_images_to_godanang(images, slug, godanang_service)` — re-uploads filtered images to GoDaNang storage, returns GoDaNang URLs

## 4. Pipeline Integration

- [ ] 4.1 Update `linkedin_group_crawler/app/modules/apartment_agent/extractor.py` — add `images: list[str]` parameter to `extract_listing()` so LLM can reference image URLs in extraction
- [ ] 4.2 Update `linkedin_group_crawler/app/modules/apartment_agent/pipeline.py` — add `process_messages_filtered(messages, godanang_service)` function implementing the full flow: classify → extract → filter images → upload → upsert
- [ ] 4.3 Update `pipeline.py` message data flow — pass `{"id", "text", "image_urls"}` dicts instead of just `{"id", "text"}`
- [ ] 4.4 Add feature flag `APARTMENT_AGENT_GODANANG_SYNC` env var — when disabled, pipeline falls back to existing text-only behavior

## 5. Crawler Integration

- [ ] 5.1 Update `linkedin_group_crawler/app/modules/zalo/api/routes/crawler.py` auto-trigger hook (line ~677) — pass `m.image_urls` alongside `m.content` to the agent pipeline
- [ ] 5.2 Update `linkedin_group_crawler/app/modules/apartment_agent/router.py` — fetch messages with `assets` relation from Supabase (include image URLs in query)
- [ ] 5.3 Add `POST /api/apartment-agent/sync-godanang` endpoint in `router.py` — manual trigger for a group_name, returns `{processed, listings_found, upserted, skipped}` summary

## 6. Testing

- [ ] 6.1 Add unit tests for `classifier.py` — test apartment for sale, apartment for rent, casual chat, empty text, ambiguous question
- [ ] 6.2 Add unit tests for `image_filter.py` — test mixed extensions, data URLs, empty list, all-filtered-out
- [ ] 6.3 Add unit tests for `godanang_service.py` — test upsert mapping, slug generation, dedup behavior
- [ ] 6.4 Add integration test for full pipeline — mock LLM + mock Supabase clients, verify end-to-end flow from messages to villas upsert
