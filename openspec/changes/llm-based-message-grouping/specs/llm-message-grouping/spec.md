## ADDED Requirements

### Requirement: LLM-based message grouping

The system SHALL use a single LLM call to partition a batch of raw Zalo messages into logical apartment listings, replacing the heuristic content-type boundary walk in `grouping.py`.

- The LLM input SHALL be a chronologically ordered list of messages with fields: `id`, `text`, `sender_name`, `timestamp_text`, `image_urls`, `type`.
- The LLM SHALL return a JSON array where each element represents one apartment listing with `source_message_ids`, `text`, `image_urls`, and `status_hint`.
- Messages that do not belong to any listing (chat, stickers, system) SHALL be excluded from the output.
- A single message describing multiple apartments SHALL be split into multiple listing entries, each with the same `source_message_ids`.
- Image-only messages following a text message SHALL be grouped with the preceding text listing.
- The `source_message_ids` field SHALL preserve traceability to original messages.

#### Scenario: Text + follow-up phone number merged

- **WHEN** a user posts "Cho thuê căn hộ Sunshine 2PN 8tr" followed by "Liên hệ 0905123456" within 5 minutes
- **THEN** the LLM returns one listing with `source_message_ids` containing both message IDs and `text` containing both message bodies joined

#### Scenario: Text + image album merged

- **WHEN** a user posts "Căn hộ Monarchy 70m2 view biển" followed by 10 image-only messages within 2 minutes
- **THEN** the LLM returns one listing with all 11 `source_message_ids` and all 10 `image_urls`

#### Scenario: Two separate listings in one message

- **WHEN** a user posts "Bán: 2PN 8tr, 3PN 12tr — cả hai view sông Hàn"
- **THEN** the LLM returns two listing entries, each with the same `source_message_ids` but separate `text` values

#### Scenario: Non-listing messages excluded

- **WHEN** a batch contains apartment listings mixed with casual chat ("ăn cơm chưa mọi người")
- **THEN** the LLM output excludes the casual chat messages entirely

#### Scenario: Status update detected

- **WHEN** a user posts "căn trên bán rồi nhé" after posting a listing
- **THEN** the LLM returns a listing entry with `status_hint: "sold"` and the message's `source_message_ids`

#### Scenario: Empty batch

- **WHEN** a batch contains zero messages or only skipped-type messages
- **THEN** the LLM returns an empty array

#### Scenario: Batch size limit

- **WHEN** a batch exceeds 100 messages
- **THEN** the system SHALL split the batch at the nearest 30-minute time boundary before sending to the LLM

#### Scenario: Single message with no listing content

- **WHEN** a batch contains only a sticker message
- **THEN** the LLM returns an empty array
