> **SUPERSEDED** by [apartment-agent-villa-column-mapping](../../../apartment-agent-preview-and-villa-push/specs/apartment-agent-villa-column-mapping/spec.md) — see the canonical spec for the current column mapping.

## ADDED Requirements

### Requirement: Extract structured apartment data from message text

The system SHALL extract the following fields from confirmed apartment listing messages using LLM extraction:
- `name`: Apartment name or title
- `area`: Area/district (e.g., "Mỹ Khê", "Sơn Trà")
- `selling_price`: Price in VND (numeric)
- `price_label`: Formatted price string
- `capacity`: Number of bedrooms
- `description`: Full description text
- `owner_name`: Contact person name
- `zalo_link`: Zalo contact link or phone number
- `amenities`: List of amenities

#### Scenario: Complete listing message
- **WHEN** message text is "Cần bán căn hộ 2PN, 70m², view biển Mỹ Khê, giá 2.5 tỷ. LH Anh Minh 0905xxx"
- **THEN** extractor returns: `name="Căn hộ 2PN view biển Mỹ Khê"`, `area="Mỹ Khê"`, `selling_price=2500000000`, `capacity=2`, `owner_name="Anh Minh"`

#### Scenario: Incomplete listing message
- **WHEN** message text is "Bán căn hộ giá rẻ"
- **THEN** extractor returns partial data with empty strings for missing fields (no error thrown)

### Requirement: Generate deterministic slug for dedup

The system SHALL generate a slug from `name + area + selling_price` using a deterministic hash. The slug MUST be URL-safe and unique per distinct apartment.

#### Scenario: Same apartment posted twice
- **WHEN** two messages describe the same apartment with identical name, area, and price
- **THEN** both produce the same slug and the second upsert updates the existing row (no duplicate)

#### Scenario: Different apartments
- **WHEN** two messages describe different apartments
- **THEN** they produce different slugs and both are inserted as separate rows

### Requirement: Upsert to GoDaNang villas table

The system SHALL upsert apartment data to the GoDaNang `villas` table with `type='apartment'`. On conflict (same slug), the system MUST update the existing row with new data.

#### Scenario: New apartment listing
- **WHEN** extracted data has a slug not present in `villas` table
- **THEN** a new row is inserted with `type='apartment'`, `status='active'`, and all extracted fields

#### Scenario: Existing apartment with updated price
- **WHEN** extracted data has a slug already in `villas` table but with different `selling_price`
- **THEN** the existing row is updated with new price, new images, and updated `description`

#### Scenario: Apartment with images
- **WHEN** extracted data includes image URLs that were uploaded to GoDaNang storage
- **THEN** the `images` JSONB column contains the GoDaNang storage URLs (not Zalo CDN URLs)

### Requirement: Map extracted fields to villas schema

The system SHALL map extracted apartment fields to the GoDaNang `villas` table columns using the following mapping:

| Extracted field | villas column | Notes |
|----------------|---------------|-------|
| name | name | Required, fallback to "Căn hộ" |
| slug | slug | Generated deterministically |
| area | area | District/neighborhood |
| selling_price | selling_price | VND, numeric |
| selling_price | price | Same as selling_price |
| price_label | price_label | Formatted string |
| capacity | capacity | Bedrooms count, default 2 |
| description | description | Full text |
| owner_name | owner_name | Contact name |
| zalo_link | zalo_link | Contact info |
| amenities | amenities | JSONB array |
| (computed) | type | Always "apartment" |
| (computed) | status | Always "active" |
| images | images | GoDaNang storage URLs |

#### Scenario: Field mapping applied correctly
- **WHEN** extractor returns `{name: "Căn hộ ABC", selling_price: 2500000000, area: "Sơn Trà"}`
- **THEN** upsert payload contains `name="Căn hộ ABC"`, `selling_price=2500000000`, `area="Sơn Trà"`, `type="apartment"`, `status="active"`

### Requirement: Expose API endpoint for manual trigger

The system SHALL provide an API endpoint `POST /api/apartment-agent/sync-godanang` that manually triggers the filter-and-sync pipeline for a specific group or message batch.

#### Scenario: Manual trigger for a group
- **WHEN** API receives `POST /api/apartment-agent/sync-godanang` with `{"group_name": "Nhóm BĐS Đà Nẵng"}`
- **THEN** system fetches recent messages from that group, runs classifier + extractor + upsert pipeline
- **AND** returns summary: `{processed: 50, listings_found: 8, upserted: 7, skipped: 42}`
