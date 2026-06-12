## ADDED Requirements

### Requirement: Per-message image count is always present on the response

Every `TestExtractResult` in the `TestExtractResponse.results`
array MUST have a non-null `listing` field when `status ==
"extracted"`, and the `listing.image_count` field MUST equal
`len(listing.images)`. The model still only sees URLs as text —
this requirement is purely about the response shape so the FE
can render an obvious "this message had N images attached"
indicator.

#### Scenario: Message with 3 images
- **WHEN** a message has 3 storage_url rows in `zalo_message_assets` for the same `message_id`
- **THEN** the response row's `listing.image_count == 3`
- **AND** `listing.images` is a list of 3 string URLs
- **AND** the FE's ResultCard renders the 3 thumbnails

#### Scenario: Message with 0 images
- **WHEN** a message has zero `storage_url` rows
- **THEN** the response row's `listing.image_count == 0`
- **AND** `listing.images` is an empty list
- **AND** the FE's ResultCard renders the "(không có ảnh đính kèm)" placeholder

#### Scenario: Message with a non-image attachment
- **WHEN** a message has 2 `storage_url` rows but one ends in `.bin` (a known mis-crawl case)
- **THEN** the response row's `listing.image_count == 1` (the `.bin` URL is filtered out)
- **AND** `listing.images` is a list of 1 string URL
- **AND** the dropped `.bin` URL is logged at DEBUG level with the message id

### Requirement: Non-image suffixes are dropped from the URL list

The `app/modules/apartment_agent/image_filter.py::_has_image_suffix`
helper MUST drop URLs whose path ends in any of the following
non-image suffixes: `.mp4`, `.mov`, `.webm`, `.mp3`, `.wav`,
`.pdf`, `.zip`, `.doc`, `.docx`, `.bin`, `.rar`. The denylist is
additive to the existing allowlist of image suffixes (`.jpg`,
`.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.heic`, `.heif`).
URLs whose path ends in an *unknown* suffix (e.g. the Supabase
Storage signed-URL style `…/storage/v1/object/sign/...`) are
kept as before.

#### Scenario: Mixed attachments
- **WHEN** a message has 4 URLs ending in `.jpg`, 1 ending in `.bin`, 1 ending in `.pdf`, and 2 with no suffix
- **THEN** the LLM call receives exactly 6 URLs (4 `.jpg` + 2 unsuffixed)
- **AND** the `.bin` and `.pdf` URLs are dropped silently
- **AND** `listing.image_count == 6`

#### Scenario: 50+ URLs after filtering
- **WHEN** a message has 60 unique URLs that all pass the suffix filter
- **THEN** the LLM call receives exactly 50 URLs (the existing cap at `image_filter.py:39`)
- **AND** a DEBUG log line records the truncation with the dropped count and the message id

### Requirement: FE renders the no-images case explicitly

The `ZaloAgentTestPanel.tsx::ResultCard` component MUST render a
visible "không có ảnh đính kèm" placeholder when
`item.listing.image_count === 0`. Today the absence of a
thumbnail strip is silent and can be misread as "the model forgot
to show me the images" when in fact there were no images to show.
The placeholder is a single line of muted text, not a card or
modal.

#### Scenario: Message with 0 images
- **WHEN** the result row has `listing.image_count == 0`
- **THEN** the ResultCard renders a `<p class="text-body-xs text-on-surface-variant mt-xs italic">không có ảnh đính kèm</p>` under the field grid
- **AND** no thumbnail strip is rendered
- **AND** the field labeled "Ảnh" still renders the value "0" (it does, today)

#### Scenario: Message with 1+ images
- **WHEN** the result row has `listing.image_count >= 1`
- **THEN** the "không có ảnh đính kèm" placeholder is NOT rendered
- **AND** the existing thumbnail strip is rendered as today
