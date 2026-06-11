# apartment-agent-preview Specification

## Purpose
Defines the `POST /api/apartment-agent/preview` endpoint and the Agent
tab "Bản xem trước (chưa gửi GoDaNang)" UI that lets the operator review
the exact JSON payload that will be POSTed to GoDaNang's `villas` table
before any write happens.

## Requirements

### Requirement: Preview endpoint runs classifier + extractor without writing
The system SHALL expose `POST /api/apartment-agent/preview` accepting `{texts: string[]}` or `{group_name: string, limit?: int <= 200}`. The endpoint MUST run the classifier + extractor over the input and return the per-listing payload that `sync._build_insert_payload` (or `_build_update_payload` on dedup hit) would produce, WITHOUT calling any write method on the GoDaNang REST client.

#### Scenario: Preview with pasted texts
- **WHEN** a client posts `{texts: ["Căn hộ 2PN ...", "Sticker good morning"]}`
- **THEN** the response has `classifications.length == 2`, `listings` contains the first message (classified as listing), and zero GoDaNang rows are touched

#### Scenario: Preview with group name
- **WHEN** a client posts `{group_name: "Nhóm cho thuê Đà Nẵng", limit: 50}`
- **THEN** the endpoint fetches up to 50 rows from `zalo_messages` with `group_name=eq.Nhóm cho thuê Đà Nẵng`, runs the classifier + extractor, and returns the per-listing payloads

#### Scenario: Preview with empty input
- **WHEN** a client posts `{texts: []}` or `{group_name: "Không tồn tại"}` and the lookup returns 0 rows
- **THEN** the response has `classifications: []`, `listings: []`, `summary.messages_seen=0`, HTTP 200

### Requirement: Preview dedup-read shows operation
For each classified listing, the preview MUST call `find_existing_villa` (a read) against the GoDaNang REST endpoint and set `operation` to `insert` (no match), `update` (slug match), or `skip` (manual `is_rented=true` on existing row).

#### Scenario: New listing (no dedup hit)
- **WHEN** the GoDaNang `villas` table has no row matching the listing's slug
- **THEN** `operation="insert"` and `existing_villa_id=null`

#### Scenario: Existing listing dedup hit
- **WHEN** the GoDaNang `villas` table has a row matching the listing's slug
- **THEN** `operation="update"` and `existing_villa_id=<uuid>`

### Requirement: Preview payload matches what `villa-sync` would write
The `payload` field in each listing MUST be byte-identical to what `sync.insert_apartment` / `sync.update_apartment` would POST/PUT. The pytest e2e suite MUST assert this identity.

#### Scenario: Preview then send produces same body
- **WHEN** the operator clicks "Gửi cái này" on a preview card with `operation="insert"`
- **THEN** the resulting POST to `https://<godanang>/rest/v1/villas` has the exact same body as `payload` (verified by a mocked httpx assertion in the test suite)

### Requirement: Agent tab renders preview cards with per-listing toggle
The frontend `ZaloAgentTestPanel` MUST render, after the test result, a "Bản xem trước" section. Each classified listing MUST render as a card showing: title, district, area, price, `price_label`, the literal JSON payload in a `<pre>` block, an operation badge (`INSERT` / `UPDATE` / `SKIP`), and a per-card toggle defaulting to `on` for `INSERT` and `off` for `UPDATE`/`SKIP`.

#### Scenario: Preview shows operation badge
- **WHEN** the preview response contains a listing with `operation="update"`
- **THEN** the card displays a blue "UPDATE" badge and the per-card toggle defaults to off

#### Scenario: Operator toggles a card off
- **WHEN** the operator clicks the per-card toggle to "Bỏ qua"
- **THEN** the footer count decrements from `N cái đã chọn` to `N-1 cái đã chọn` and the card is visually de-emphasized

### Requirement: Footer "Gửi N cái đã chọn" button
The preview section MUST have a footer with a button "Gửi N cái đã chọn" that calls `villaSync({listing_ids: [selected_ids]})`. The button MUST be disabled when N=0 and MUST show a progress bar while sending. On completion, each card flips to "Đã gửi" with the GoDaNang `villa_id` rendered.

#### Scenario: Operator sends 2 of 5 listings
- **WHEN** the operator selects 2 of 5 listing toggles and clicks "Gửi 2 cái đã chọn"
- **THEN** the FE calls `villaSync({listing_ids: ["id1", "id2"]})`, the 2 cards flip to "Đã gửi", the remaining 3 stay in preview state, and the toast reads "Đã gửi 2 căn lên GoDaNang"

### Requirement: Preview is read-only
The preview endpoint MUST NOT mutate any table in either Supabase project (the Zalo project's `zalo_messages` is read; GoDaNang's `villas` is read via `find_existing_villa` only). The pytest suite MUST assert zero `POST` / `PUT` / `PATCH` / `DELETE` calls during a preview request, by mocking `httpx.AsyncClient`.

#### Scenario: Preview makes no writes
- **WHEN** a preview request runs end-to-end with mocked httpx
- **THEN** the mock recorded only `GET` calls (to `zalo_messages` and to GoDaNang's `villas`) and zero write-method calls
