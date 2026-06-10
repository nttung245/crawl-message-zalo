# zalo-campaign-soft-warnings Specification

## Purpose
TBD - created by archiving change fix-zalo-broadcast-bugs. Update Purpose after archive.
## Requirements
### Requirement: Soft warnings must not block campaign creation
The `create_broadcast` endpoint SHALL distinguish hard errors from soft warnings. Campaigns with only soft warnings SHALL be created successfully.

#### Scenario: Image-only messages with content_mode='both'
- **WHEN** a user creates a campaign with image-only messages
- **THEN** soft warnings like "Tin này không có nội dung text" SHALL NOT block creation

#### Scenario: Hard errors still block
- **WHEN** a preview returns hard errors
- **THEN** the campaign SHALL be rejected with 400

### Requirement: userId change must preserve selected messages
When the Zalo user ID changes, the system SHALL preserve selected messages.

#### Scenario: userId changes while messages are selected
- **WHEN** a user has selected 20 messages and the zaloUserId changes
- **THEN** the selected message IDs SHALL be preserved

