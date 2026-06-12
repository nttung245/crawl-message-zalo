## ADDED Requirements

### Requirement: Content-Type Classification

The grouper SHALL classify every input message into exactly one of three content types: `text_only`, `image_only`, or `mixed`. The classification is derived from the existing `text` (or `content`) and `image_urls` fields and SHALL NOT require any new schema, new I/O, or new dependencies.

- A message with non-empty `text` after `.strip()` and empty `image_urls` SHALL be classified as `text_only`.
- A message with empty/whitespace `text` and non-empty `image_urls` SHALL be classified as `image_only`.
- A message with both non-empty `text` and non-empty `image_urls` SHALL be classified as `mixed`.

#### Scenario: Text-only message

- **WHEN** the grouper receives a message with `"text": "Sunshine Riverside 2PN 8tr"` and `"image_urls": []`
- **THEN** the message is classified as `text_only`

#### Scenario: Image-only message

- **WHEN** the grouper receives a message with `"text": ""` and `"image_urls": ["https://…/photo1.jpg"]`
- **THEN** the message is classified as `image_only`

#### Scenario: Mixed content message

- **WHEN** the grouper receives a message with `"text": "Căn 2PN full nội thất"` and `"image_urls": ["https://…/p.jpg"]`
- **THEN** the message is classified as `mixed`

### Requirement: Content-Type Boundary Detection

The grouper SHALL close the current group and start a new one at every content-type boundary, where a boundary is any of: skip-trigger message, sender change, missing identity, text-after-text, text-after-image-only, hard size cap reached, or time-gap fallback exceeded.

- A `text_only` message following a group whose only messages are `text_only` SHALL start a new group.
- A `text_only` message following a group whose last appended message is `image_only` SHALL start a new group.
- A `text_only` message following a group whose last appended message is `text_only` (or `mixed`) SHALL append to the current group.
- An `image_only` or `mixed` message following any group SHALL append to the current group until a different boundary condition fires.
- `mixed` content type SHALL be treated as `text_only` for boundary-decision purposes.

#### Scenario: Text after text starts a new listing

- **WHEN** the current group contains one `text_only` message and the next message is also `text_only` from the same sender
- **THEN** the current group is closed and a new group is started with the new message as its first

#### Scenario: Text after image-only group starts a new listing

- **WHEN** the current group ends in an `image_only` message (its only message) and the next message from the same sender is `text_only`
- **THEN** the current group is closed and a new group is started (the text is the description for the *next* listing, not the photos)

#### Scenario: Image after text continues the listing

- **WHEN** the current group contains one `text_only` message and the next message from the same sender is `image_only`
- **THEN** the image message is appended to the current group

#### Scenario: Image after image continues the album until the cap

- **WHEN** the current group contains one `text_only` and one `image_only` message, the cap is 4, and the next message is `image_only`
- **THEN** the image is appended (group now has 3 messages, below the cap)

### Requirement: Hard Size Cap

The grouper SHALL enforce a configurable per-group message cap. When the current group already contains `max_messages_per_group` messages, the next message that would otherwise append SHALL start a new group instead.

- `max_messages_per_group` SHALL default to 4.
- `max_messages_per_group` SHALL be settable per call (`group_messages(messages, ..., max_messages_per_group=N)`).
- `max_messages_per_group` SHALL be settable via the `ApartmentAgentSettings.message_group_max_size` config field and the `AGENT_MESSAGE_GROUP_MAX_SIZE` environment variable.
- The cap SHALL apply after the content-type and time-gap checks; the cap is the last-resort boundary.

#### Scenario: Cap closes an over-large group

- **WHEN** the current group already contains 4 messages and the next message from the same sender is `image_only`
- **THEN** the current group is closed and a new group is started with the image message as its first

#### Scenario: Cap prevents a 5-photo merge

- **WHEN** a seller posts `1 text + 5 images` from the same sender within the time fallback, with `max_messages_per_group=4`
- **THEN** the grouper produces 2 groups: `text + 3 images` and `2 images` (the 5th and 6th images)

#### Scenario: Cap is configurable per call

- **WHEN** a test calls `group_messages(messages, max_messages_per_group=2, time_fallback_minutes=0)`
- **THEN** the walk closes any group at 2 messages regardless of content type

### Requirement: Time-Gap Fallback

The grouper SHALL close the current group when the next message's timestamp exceeds `time_fallback_minutes` after the **first** message in the current group.

- `time_fallback_minutes` SHALL default to 1.
- `time_fallback_minutes` SHALL be settable per call.
- `time_fallback_minutes` SHALL be settable via the `ApartmentAgentSettings.message_group_time_fallback_minutes` config field and the `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES` environment variable.
- The legacy `ApartmentAgentSettings.message_group_window_minutes` field and `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` env var SHALL be accepted as a fallback for the new field for one release, with a deprecation warning logged on first use per process.

#### Scenario: Time gap splits a listing

- **WHEN** the current group contains a message at `08:00:00` and the next message from the same sender is at `08:02:00`, with `time_fallback_minutes=1`
- **THEN** the current group is closed and a new group is started

#### Scenario: Time gap is measured from the first message

- **WHEN** the current group contains messages at `08:00:00` and `08:00:45` and the next message is at `08:00:55`, with `time_fallback_minutes=1`
- **THEN** the next message is appended (the gap is 55s, measured from `08:00:00`)

#### Scenario: Legacy env var still works

- **WHEN** the environment has `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` set and `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES` is not set
- **THEN** the grouper uses 3 minutes as the time fallback and logs a deprecation warning on the first grouping call

### Requirement: Existing Skip / Singleton Rules Preserved

The grouper SHALL preserve the existing skip-and-close and singleton rules from the prior implementation.

- A message with `is_deleted=True` SHALL close the current group and be dropped.
- A message with `type` in `{"system", "sticker"}` (case-insensitive) SHALL close the current group and be dropped.
- A message with no `sender_id` and no `sender_name` SHALL be a singleton (its own group of one).
- A message with no parseable timestamp (`timestamp_text` and `created_at` both unparseable) SHALL be a singleton.
- `window_minutes == 0` (legacy escape hatch) SHALL return one group per message.

#### Scenario: Deleted message splits groups

- **WHEN** the current group contains one `text_only` message and the next message has `is_deleted=True`
- **THEN** the current group is closed, the deleted message is dropped, and the message after (if any) starts a new group

#### Scenario: No-sender message is a singleton

- **WHEN** a message has empty `sender_id` and empty `sender_name`
- **THEN** the grouper emits that message as its own group regardless of neighbors

### Requirement: Observability Log Shape

The grouper SHALL emit a single INFO log line per pipeline run with: total input message count, group count, max group size, multi-group count (groups with >1 source message), and a per-pair histogram of the content type composition of each group.

- The histogram SHALL use the form `text+3img: 2, 2img: 1, text: 0` where the key is `text_only` + N×`image_only` for a group that started with text, or N×`image_only` / `text` for image-only and text-only singletons.
- The histogram SHALL be ordered by key for stable grep across runs.

#### Scenario: 50 messages, 3 listings, log line shape

- **WHEN** the grouper processes 50 messages from one sender and produces 3 groups
- **THEN** the log line includes `count=50, groups=3, max_group=N, multi_groups=3, pairs={text+3img: 2, 2img: 1}` for some N ≤ 4

#### Scenario: 20 messages from one sender do not all merge

- **WHEN** the previous (legacy) grouper would have produced one group of 20
- **THEN** the new grouper produces at least 4 groups (assuming the messages are posted as `text → images → text → images → …`)

### Requirement: Backward-Compatible Response Shape

The grouper's `MessageGroup` model and downstream response fields SHALL remain unchanged. The `id`, `source_message_ids`, `text`, `image_urls`, `sender_id`, `sender_name`, `timestamp_text`, `time_text`, `created_at`, `group_name` fields SHALL keep their existing shapes and semantics.

- `raw_message_id` in `TestExtractResult` SHALL continue to be the first contributing message id of the group.
- `source_message_ids` SHALL continue to be the chronological list of contributing message ids.

#### Scenario: Existing API consumer still works

- **WHEN** a caller iterates `result.results` and reads `r.source_message_ids`
- **THEN** the list contains the same message ids it did under the previous grouper (just smaller groups, never a group of 20)
