## ADDED Requirements

### Requirement: Group consecutive same-sender messages within a time window

The system SHALL group consecutive Zalo messages from the same sender into a single logical listing record when the time gap between the first message in the group and any subsequent message in the group is less than or equal to `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` (default 3).

A message MAY be added to the current group when **all** of the following hold:
- its sender identity matches the current group's sender identity (same `sender_id` after trim+lowercase, or — when `sender_id` is missing — same `sender_name` after trim+lowercase);
- its timestamp is parseable and within the configured window of the first message in the group;
- it is not deleted, not a system message, and not a sticker.

Messages that fail any of those checks SHALL close the current group and start a new one.

#### Scenario: Two text-only messages, same sender, within window
- **WHEN** the pipeline receives message A (sender "Anh Tuấn", text "Sunshine Riverside 2PN 8tr", timestamp T0) and message B (sender "Anh Tuấn", text "Liên hệ 0905xxx", timestamp T0+90s)
- **THEN** the system groups them into one record whose `text` is `"Sunshine Riverside 2PN 8tr\n\nLiên hệ 0905xxx"` and whose `source_message_ids` contains both ids

#### Scenario: Text message followed by image-only message, same sender, within window
- **WHEN** message A is text-only (sender "Chị Mai", text "Cho thuê Monarchy 70m2", timestamp T0) and message B is image-only (sender "Chị Mai", 5 image URLs, timestamp T0+45s)
- **THEN** the system groups them into one record whose `text` is `"Cho thuê Monarchy 70m2"` and whose `image_urls` contains all 5 URLs from B

#### Scenario: Image-only message followed by text message, same sender, within window
- **WHEN** message A is image-only (sender "Anh Hùng", 3 image URLs, timestamp T0) and message B is text-only (sender "Anh Hùng", text "FPT City 2PN view biển 9tr/tháng", timestamp T0+30s)
- **THEN** the system groups them into one record whose `text` is `"FPT City 2PN view biển 9tr/tháng"` and whose `image_urls` contains all 3 URLs from A

#### Scenario: Same sender, gap larger than window
- **WHEN** messages A and B share sender identity but B's timestamp is more than `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` after A's timestamp
- **THEN** the system produces two separate group records (A as one group, B as another)

#### Scenario: Different senders, within window
- **WHEN** message A is from sender X and message B is from sender Y but B's timestamp is within the window of A
- **THEN** the system produces two separate group records (one per sender)

### Requirement: Singleton group for messages without sender or timestamp

When a message has neither a usable sender identity nor a parseable timestamp, the system SHALL place it in a singleton group (a group with exactly one source message). The downstream extraction behavior SHALL be identical to today's per-message behavior for these messages.

A sender identity is usable if `sender_id` is non-empty OR `sender_name` is non-empty after trim. A timestamp is parseable if `timestamp_text` parses successfully OR `created_at` is a valid ISO-8601 string.

#### Scenario: Message with no sender name or id
- **WHEN** the pipeline receives a single message with `sender_id=None` and `sender_name=None` and `sender_name=""` (empty)
- **THEN** the system places it in a singleton group and the LLM receives it as a single listing

#### Scenario: Message with unparseable timestamp_text and missing created_at
- **WHEN** a message has `timestamp_text="invalid"` and `created_at=None`
- **THEN** the system places it in a singleton group (no grouping) regardless of its sender

### Requirement: Skip deleted, system, and sticker messages from groups

When the next message in the sorted list has `is_deleted=True`, `type="system"`, or `type="sticker"`, the system SHALL close the current group and start a new one; the skipped message itself is not added to either group.

#### Scenario: Deleted message between two valid messages
- **WHEN** message A (sender X, text "Listing 1") is followed by message D (sender X, `is_deleted=True`) which is followed by message B (sender X, text "Listing 2")
- **THEN** the system produces two groups: A as one group, B as a new group; D is dropped

#### Scenario: Sticker between two valid messages
- **WHEN** a sticker message appears between two messages from the same sender
- **THEN** the system closes the first group at the sticker and starts a new group at the next valid message

### Requirement: Group window is configurable via env

The system MUST read the time window from `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` (integer minutes, default 3). Setting it to `0` MUST disable grouping entirely (every message becomes a singleton). Values above `60` MUST be capped at `60` with a one-time startup warning.

#### Scenario: Custom window via env
- **WHEN** `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=5` is set
- **THEN** messages from the same sender up to 5 minutes apart are grouped

#### Scenario: Disabling grouping
- **WHEN** `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=0` is set
- **THEN** the system behaves identically to today's per-message extraction (no grouping)

### Requirement: Text-only API path bypasses grouping

When the request payload contains `texts` (a list of free-form strings typed by the user in the FE textbox) and does NOT contain a `group_name` (no Supabase fetch), the system MUST NOT invoke the grouper. Each text is treated as a singleton listing record.

#### Scenario: test-extract with texts array
- **WHEN** the request body is `{"texts": ["Listing A", "Listing B"]}`
- **THEN** the system creates two singleton groups and the response contains two results, one per input text; the grouper is not invoked

### Requirement: Grouped record carries source_message_ids

The merged group record MUST include a `source_message_ids: list[str]` field that contains every contributing message id in chronological order. The first contributing id MUST be exposed as the existing `id` / `raw_message_id` field so that downstream tracing and dedup continue to work without changes.

The downstream `TestExtractListing` and `PreviewListing` response shapes MUST be extended with a `source_message_ids: list[str]` field (default `[]`) so the FE can detect grouped listings and display a "Grouped from N messages" badge when `len(source_message_ids) > 1`.

#### Scenario: Singleton group populates source_message_ids with one id
- **WHEN** the input is a single message with id "m1"
- **THEN** the merged record has `source_message_ids=["m1"]` and the response's `source_message_ids` is `["m1"]`

#### Scenario: Multi-message group populates source_message_ids with all ids in order
- **WHEN** three messages (ids "m1", "m2", "m3") are grouped
- **THEN** the merged record has `source_message_ids=["m1", "m2", "m3"]` and the response's `source_message_ids` is `["m1", "m2", "m3"]`

### Requirement: Deterministic and side-effect-free grouper

`group_messages(messages, window_minutes)` MUST be a pure function: same input MUST produce same output. It MUST NOT perform any I/O, network calls, DB queries, or LLM calls. It MUST be safe to call from a synchronous context and MUST complete in under 50ms for 200 messages.

#### Scenario: Repeated calls return identical output
- **WHEN** `group_messages(messages, 3)` is called twice with the same input list
- **THEN** both calls return groups with identical content and identical order

#### Scenario: Grouper makes no external calls
- **WHEN** the grouper is invoked
- **THEN** no HTTP requests, no DB queries, no LLM calls are made (verifiable by mocking all three)
