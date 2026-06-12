## ADDED Requirements

### Requirement: Classify Zalo message as apartment listing

The system SHALL classify a Zalo message text as either an apartment listing (sale or rental) or not, returning a boolean result with a confidence score.

#### Scenario: Message is an apartment for sale
- **WHEN** message text contains "Cần bán căn hộ 2PN, 70m², giá 2.5 tỷ, liên hệ Anh Minh"
- **THEN** classifier returns `is_listing: true` with confidence >= 0.8

#### Scenario: Message is an apartment for rent
- **WHEN** message text contains "Cho thuê căn hộ studio, fully furnished, 8tr/tháng"
- **THEN** classifier returns `is_listing: true` with confidence >= 0.8

#### Scenario: Message is casual chat
- **WHEN** message text contains "Mọi người ơi, hôm nay trời đẹp quá"
- **THEN** classifier returns `is_listing: false` with confidence >= 0.8

#### Scenario: Message is a sticker or reaction
- **WHEN** message text is empty or contains only emoji/sticker references
- **THEN** classifier returns `is_listing: false` with confidence 1.0

#### Scenario: Ambiguous message
- **WHEN** message text is "Ai biết căn hộ nào cho thuê không?"
- **THEN** classifier returns `is_listing: false` with confidence < 0.7 (it's a question, not a listing)

### Requirement: Classifier operates before image download

The system SHALL invoke the text classifier BEFORE any image download occurs for the message. If classification is `false`, the pipeline MUST skip image processing entirely.

#### Scenario: Non-listing message skips image download
- **WHEN** classifier returns `is_listing: false`
- **THEN** no images are downloaded and no Supabase Storage writes occur for this message

#### Scenario: Listing message proceeds to image download
- **WHEN** classifier returns `is_listing: true`
- **THEN** pipeline proceeds to image filtering and download phase

### Requirement: Classifier logs results for monitoring

The system SHALL log classification results (message_id, is_listing, confidence) for monitoring and prompt tuning.

#### Scenario: Classification result is logged
- **WHEN** a message is classified
- **THEN** a log entry is written with message_id, is_listing boolean, confidence score, and timestamp
