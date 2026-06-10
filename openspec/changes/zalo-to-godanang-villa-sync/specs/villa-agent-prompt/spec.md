## ADDED Requirements

### Requirement: Single-pass filter and extract
The Agent prompt SHALL instruct the LLM to both filter non-apartment messages AND extract structured data from apartment messages in a single pass. Each message in the batch MUST be classified as either apartment listing or not.

#### Scenario: Mixed batch of messages
- **WHEN** Agent receives a batch of 20 messages containing 5 apartment listings, 10 casual conversations, and 5 spam messages
- **THEN** Agent returns 20 results, each with `is_apartment_listing: true/false`, and only the 5 apartment listings have extracted fields populated

#### Scenario: All non-apartment messages
- **WHEN** Agent receives a batch of 10 messages with no apartment listings
- **THEN** Agent returns 10 results all with `is_apartment_listing: false` and empty extracted fields

### Requirement: Structured output matching villas schema
The Agent prompt SHALL enforce a JSON output format that maps directly to the godanang `villas` table columns. Required output fields: `is_apartment_listing`, `name`, `type`, `area`, `price`, `price_label`, `capacity`, `description`, `amenities`, `is_rented`, `images`, `contact_phone`, `contact_zalo`.

#### Scenario: Complete apartment listing extraction
- **WHEN** Agent processes a message: "Cho thue can ho 2PN tang 5, 123 Nguyen Van Linh, 8tr/thang, lien he 0901234567"
- **THEN** Agent returns `{"is_apartment_listing": true, "name": "Can ho 2PN 123 Nguyen Van Linh", "type": "apartment", "area": "Quan Hai Chau", "price": 8000000, "price_label": "8tr/thang", "capacity": 4, "description": "123 Nguyen Van Linh, Tang 5. 2PN, ...", "amenities": [], "is_rented": false, "images": [], "contact_phone": "0901234567", "contact_zalo": "0901234567"}`

#### Scenario: Missing fields default to safe values
- **WHEN** Agent processes a message with incomplete info (no price, no contact)
- **THEN** missing fields default to: `price: 0`, `price_label: ""`, `capacity: 2`, `contact_phone: ""`, `contact_zalo: ""`

### Requirement: Description field as dedup fingerprint
The Agent prompt SHALL generate a `description` field that contains a canonical representation of: address, floor number, room number, number of bedrooms, and key amenities. This description MUST be consistent for the same physical unit across different Zalo messages.

#### Scenario: Same room posted by different people
- **WHEN** two different Zalo messages describe the same room at "123 Nguyen Van Linh, Tang 5, Phong 502, 2PN"
- **THEN** Agent generates the same canonical description for both, enabling dedup matching

#### Scenario: Different rooms at same address
- **WHEN** two messages describe rooms at "123 Nguyen Van Linh" but one is Phong 502 and the other is Phong 303
- **THEN** Agent generates different descriptions with different room numbers

### Requirement: Rented status detection from language cues
The Agent prompt SHALL detect rental status from Vietnamese language cues. Messages containing phrases like "da cho thue", "co nguoi o", "da co khach" SHALL set `is_rented: true`. Messages containing "cho thue", "can thue", "con trong", "chua co nguoi" SHALL set `is_rented: false`.

#### Scenario: Explicitly rented message
- **WHEN** message contains "Phong 502 da cho thue roi nhe"
- **THEN** Agent returns `is_rented: true`

#### Scenario: Available for rent message
- **WHEN** message contains "Can ho 2PN cho thue, con trong"
- **THEN** Agent returns `is_rented: false`

#### Scenario: Ambiguous rental status
- **WHEN** message contains apartment info but no rental status cues
- **THEN** Agent defaults to `is_rented: false`

### Requirement: Batch processing with size limits
The Agent prompt SHALL accept batches of up to 20 messages per call. Messages MUST be processed in order. Each message in the batch MUST have an index for tracking.

#### Scenario: Batch of 20 messages
- **WHEN** Agent receives 20 messages
- **THEN** Agent returns exactly 20 results in the same order, each with a `message_index` field (0-19)

#### Scenario: Empty batch
- **WHEN** Agent receives 0 messages
- **THEN** Agent returns an empty array without calling the LLM
