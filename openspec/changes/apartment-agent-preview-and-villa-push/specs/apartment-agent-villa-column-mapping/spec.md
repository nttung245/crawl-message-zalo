# apartment-agent-villa-column-mapping Specification

## Purpose
Documents the canonical mapping from the apartment-agent's internal
`ApartmentListing` Pydantic model to the columns of GoDaNang's
public.villas table, and supersedes the stale delta spec in
`openspec/changes/zalo-apartment-filter-pipeline/specs/godanang-villas-sync/spec.md`.

## Requirements

### Requirement: Column mapping is verified against the live GoDaNang table
The canonical column list MUST be derived from a one-off read against `information_schema.columns` on the GoDaNang Supabase project, run before this spec is finalized. The result MUST be recorded inline in this spec under "## Verified Columns".

#### Scenario: SQL query runs and result is recorded
- **WHEN** a developer runs the verification query against the GoDaNang project
- **THEN** the column list is pasted into the "Verified Columns" section and the spec is committed

## Verified Columns

The following was obtained by querying `information_schema.columns` against
the GoDaNang Supabase project on 2026-06-11:

```
id, slug, name, type, area, capacity, price, price_label,
rating, stars, distance_to_center, quick_filters, amenities, tag,
images, tags, description, status, created_at, updated_at,
name_en, name_ko, description_en, description_ko,
quick_filters_en, quick_filters_ko, price_per_night, price_unit,
import_price, selling_price, commission_percent, profit,
main_image, sub_images, owner_name, zalo_link, booking_notes,
available_from, available_until, is_sold_out
```

**Assertion**: Every key written by `_build_insert_payload` (`slug`, `name`,
`type`, `area`, `capacity`, `price`, `price_label`, `description`,
`amenities`, `images`, `status`) exists in this list.

### Requirement: _build_insert_payload keys are a subset of verified columns
Every key in the dict returned by `sync._build_insert_payload` MUST exist in the "Verified Columns" list. The pytest smoke test MUST assert this subset relationship and MUST fail loudly if a key is missing or has a different data type than the implementation writes.

#### Scenario: Implementation writes a missing column
- **WHEN** a developer adds `"new_field": "x"` to `_build_insert_payload` without first adding the column to the GoDaNang `villas` table
- **THEN** `pytest tests/test_apartment_agent_e2e.py` fails with a clear "column new_field missing from verified-columns list" error

### Requirement: Canonical column mapping
The system MUST use the following mapping from `ApartmentListing` (LLM output) to GoDaNang `villas` (table column):

| ApartmentListing field | villas column | Type | Notes |
|---|---|---|---|
| `title` | `name` | text | Required, used for slug + display |
| (hard-coded) | `type` | text | Always `"apartment"` |
| `district` | `area` | text | Field name is a misnomer kept for back-compat |
| `bedrooms` | `capacity` | int | `bedrooms * 2` (rough estimate) |
| `price` | `price` | bigint | `int(price)`, 0 if None |
| (computed) | `price_label` | text | E.g. `"12.000.000đ/tháng"` |
| (assembled) | `description` | text | Multi-line: title + area + beds + contact |
| `amenities` | `amenities` | text[] | Default `[]` |
| `images` | `images` | text[] | Default `[]` |
| `is_rented` | `status` | text | `"inactive"` if rented, else `"active"` |
| (computed) | `slug` | text | Unicode-NFD-stripped, lowercased, hash-suffix |

The columns `selling_price`, `owner_name`, `zalo_link` documented in the
stale `zalo-apartment-filter-pipeline/specs/godanang-villas-sync/spec.md`
are NOT written by the implementation. This spec supersedes that delta.

#### Scenario: Listing is inserted
- **WHEN** a new listing passes the classifier and is sent to GoDaNang
- **THEN** the inserted row has `type="apartment"`, `area=<district>`, `capacity=<bedrooms*2>`, `status="active"`, and a non-empty `slug` and `price_label`

#### Scenario: Listing is rented
- **WHEN** `is_rented=True` on the LLM output
- **THEN** the upserted row has `status="inactive"` and a `description` line "Đã cho thuê"

### Requirement: Stale spec is superseded, not deleted
The file `openspec/changes/zalo-apartment-filter-pipeline/specs/godanang-villas-sync/spec.md` MUST have a banner at the top reading "SUPERSEDED by apartment-agent-villa-column-mapping (see openspec/changes/apartment-agent-preview-and-villa-push/specs/apartment-agent-villa-column-mapping/spec.md)". The stale spec MUST NOT be deleted; archive is the user's call after this change ships.

#### Scenario: Reader finds the supersession banner
- **WHEN** a developer opens the stale godanang-villas-sync spec
- **THEN** the first line of the file is the supersession banner with a relative link to the new spec
