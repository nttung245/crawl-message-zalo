## ADDED Requirements

### Requirement: Incremental message fetching
The system SHALL fetch only Zalo messages newer than the latest `created_at` timestamp from the godanang `villas` table. If no villas exist, the system SHALL fetch the most recent 100 messages.

#### Scenario: First sync with empty villas table
- **WHEN** the sync runs and the villas table has 0 rows
- **THEN** the system fetches the 100 most recent Zalo messages and processes them

#### Scenario: Incremental sync with existing villas
- **WHEN** the sync runs and the latest villa has `created_at = 2026-06-10T17:00:00Z`
- **THEN** the system fetches only Zalo messages with `timestamp > 2026-06-10T17:00:00Z`

### Requirement: Deduplication by address and room identifier
The system SHALL match existing villas by searching for entries where the `description` contains the same address AND the `name` contains the same room/floor identifier. Same address with different room or floor numbers SHALL be treated as separate villas.

#### Scenario: Same address, same room — update
- **WHEN** Agent extracts a listing at "123 Nguyen Van Linh, Phong 502" and a villa with matching address and room already exists
- **THEN** the system updates the existing villa (PUT) instead of creating a new one

#### Scenario: Same address, different room — create
- **WHEN** Agent extracts a listing at "123 Nguyen Van Linh, Phong 503" and no villa with room 503 exists (but room 502 does)
- **THEN** the system creates a new villa (POST) with the room 503 data

#### Scenario: No match found — create
- **WHEN** Agent extracts a listing and no villa matches the address + room combination
- **THEN** the system creates a new villa (POST)

### Requirement: Image handling on POST vs PUT
The system SHALL include image URLs in the payload only when creating a new villa (POST). When updating an existing villa (PUT), the system SHALL omit the `images` field entirely to preserve existing images and avoid costly re-processing.

#### Scenario: New villa creation includes images
- **WHEN** a new villa is being created via POST
- **THEN** the `images` JSONB field is populated with extracted image URLs from the Zalo message

#### Scenario: Villa update skips images
- **WHEN** an existing villa is being updated via PUT
- **THEN** the `images` field is NOT included in the update payload, preserving the existing images

### Requirement: Rented status detection
The system SHALL set `status = 'inactive'` for a villa when the Agent detects the room is rented or occupied. The system SHALL set `status = 'active'` when the Agent detects the room is available for rent.

#### Scenario: Room detected as rented
- **WHEN** Agent processes a message containing "da cho thue" or "co nguoi o"
- **THEN** the villa's `status` is set to `'inactive'`

#### Scenario: Room detected as available
- **WHEN** Agent processes a message containing "can thue", "cho thue", "con trong"
- **THEN** the villa's `status` is set to `'active'`

### Requirement: Sync API endpoint
The system SHALL expose a `POST /api/zalo/villa-sync` endpoint that triggers the full sync pipeline. The endpoint SHALL accept an optional `dry_run` parameter. When `dry_run` is true, the system SHALL return the planned changes without executing them.

#### Scenario: Trigger sync
- **WHEN** a POST request is sent to `/api/zalo/villa-sync`
- **THEN** the system runs the full pipeline: fetch messages, Agent extraction, dedup, POST/PUT to villas table, and returns a summary of changes

#### Scenario: Dry run
- **WHEN** a POST request is sent to `/api/zalo/villa-sync` with `dry_run: true`
- **THEN** the system returns the planned POST/PUT operations without executing them

### Requirement: Sync summary response
The system SHALL return a JSON summary after each sync run containing: `total_messages_processed`, `apartments_found`, `new_villas_created`, `villas_updated`, `villas_marked_rented`, `errors`.

#### Scenario: Successful sync summary
- **WHEN** sync completes processing 50 messages, finds 10 apartments, creates 3 new villas, updates 5, marks 2 as rented
- **THEN** response contains `{"total_messages_processed": 50, "apartments_found": 10, "new_villas_created": 3, "villas_updated": 5, "villas_marked_rented": 2, "errors": []}`
