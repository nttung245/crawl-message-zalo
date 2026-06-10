# zalo-broadcast-target-fixes Specification

## Purpose
TBD - created by archiving change fix-zalo-broadcast-bugs. Update Purpose after archive.
## Requirements
### Requirement: Crawled groups must not use display name as group_id
The `savedToLiveConversation` function SHALL set `group_id` to `null` when no real Zalo group identifier is available. The broadcast panel SHALL display a clear indicator and SHALL prevent sending to groups with null group_id.

#### Scenario: Crawled group loaded without live targets
- **WHEN** the component mounts and `loadSavedTargets` completes
- **THEN** crawled groups without real Zalo IDs SHALL have `group_id: null` and display "Cần tải danh sách live"

#### Scenario: User attempts broadcast to name-only group
- **WHEN** a user selects a group with `group_id: null` and clicks "Gửi"
- **THEN** the system SHALL show an error message

### Requirement: Merge should preserve selection state
The `mergeConversations` function SHALL update `selectedConversationIds` when a conversation's `group_id` changes during merge.

#### Scenario: Live targets loaded after selecting crawled groups
- **WHEN** a user selects crawled groups then loads live targets
- **THEN** `selectedConversationIds` SHALL be updated to use the new real `group_id` values

### Requirement: Live data must not be overwritten by crawled data
The merge system SHALL ensure live Zalo API data takes precedence over crawled/saved data.

#### Scenario: loadSavedTargets completes after loadTargets
- **WHEN** `loadTargets` completes first, then `loadSavedTargets` completes later
- **THEN** the `last_message` from live data SHALL NOT be overwritten

### Requirement: Manual entries must not overwrite crawled targets
The `normalizeTargets` function SHALL merge manual entries with existing targets.

#### Scenario: User types name matching a crawled group
- **WHEN** a user selects crawled group "Nhóm A" and also types "Nhóm A" in manual textarea
- **THEN** the target SHALL retain the `group_id` from the crawled entry

### Requirement: Dedup key must prevent diacritic collisions
The dedup system SHALL use a composite key including both normalized name and group identifier.

#### Scenario: Two groups with similar Vietnamese names
- **WHEN** "Cầu Rồng VIP" (g1) and "Cau Rong VIP" (g2) are both present
- **THEN** both SHALL appear as separate targets

