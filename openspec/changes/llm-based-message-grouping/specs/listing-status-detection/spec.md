## ADDED Requirements

### Requirement: Listing status detection from text

The system SHALL detect apartment listing lifecycle states from message text and update existing GoDaNang villa records instead of creating new ones.

- Stage 1 grouping SHALL output a `status_hint` field for each listing, with one of: `null` (unknown), `"available"`, `"sold"`, `"deposited"`, `"on_hold"`, `"withdrawn"`.
- When `status_hint` is not `null` and not `"available"`, the pipeline SHALL attempt to find the existing listing in GoDaNang by fuzzy matching on title or district+area.
- If an existing record is found, its `listing_status` SHALL be updated to match `status_hint`. No new record SHALL be created.
- If no existing record is found, the pipeline SHALL log a warning and skip (no upsert, no new record).
- A `status_update_confirmed` boolean SHALL be set to `true` when the update succeeds, `false` when the existing listing cannot be found.

#### Scenario: Listing marked as sold

- **WHEN** a message "Căn Sunshine A1205 bán rồi" is processed and Stage 1 returns `status_hint: "sold"`
- **AND** an existing record with title matching "Sunshine A1205" exists in GoDaNang
- **THEN** the existing record's `listing_status` is updated to `"sold"` and no new record is created

#### Scenario: Listing marked as deposited

- **WHEN** a message "Căn Monarchy đã cọc rồi nhé" is processed with `status_hint: "deposited"`
- **AND** an existing record matching is found in GoDaNang
- **THEN** the existing record's `listing_status` is updated to `"deposited"`

#### Scenario: Status update but listing not found

- **WHEN** a message "Căn trên bán rồi" is processed with `status_hint: "sold"`
- **AND** no existing record matches in GoDaNang
- **THEN** a warning is logged with `status_update_confirmed: false` and no record is created or modified

#### Scenario: Normal listing with no status hint

- **WHEN** a message "Cho thuê FPT City 2PN 9tr" is processed and Stage 1 returns `status_hint: null` or `"available"`
- **THEN** the pipeline proceeds with normal extraction → dedup → insert flow

#### Scenario: Multiple status updates in one batch

- **WHEN** a batch contains both "Căn 1201 bán rồi" and "Căn 502 cọc rồi"
- **THEN** each listing is processed independently — one updates status to "sold", the other to "deposited"
