## Why

The Zalo broadcast panel has 3 critical bugs that can send messages to wrong recipients or silently skip selected targets, plus dead code in the worker selector, soft warnings blocking image-only campaigns, and UX glitches. These were found by a max-effort code review and need to be fixed before they cause data loss in production.

## What Changes

- **Fix `savedToLiveConversation` group_id**: Stop using display name as `group_id`; use null for crawled groups without real Zalo IDs.
- **Fix mergeConversations selection loss**: Update `selectedConversationIds` when `group_id` changes during merge.
- **Fix race condition in merge ordering**: Prevent `loadSavedTargets` from overwriting live data.
- **Fix manual textarea overwriting crawled targets**: Merge manual entries with existing targets.
- **Fix diacritic-stripping name collisions**: Use composite key (normalized name + group_id) for dedup.
- **Expose worker selector**: Remove `{false ? ... : null}` guard.
- **Fix soft warnings blocking campaigns**: Only reject on hard errors.
- **Fix userId-change wiping selected messages**: Preserve selected message IDs.
- **Fix maxMessagesPerGroup input jumping to 50**: Allow empty string in state.

## Capabilities

### New Capabilities

- `zalo-broadcast-target-fixes`: Correct group_id handling, merge race conditions, and selection persistence.
- `zalo-worker-selector-fix`: Restore worker switching UI and fix dead code.
- `zalo-campaign-soft-warnings`: Allow campaigns with soft warnings to proceed.

### Modified Capabilities

(none)

## Impact

- `ZaloBroadcastPanel.tsx`, `ZaloCrawlerConfigCard.tsx`, `ZaloSupabaseLibraryPanel.tsx`, `broadcasts.py`
- No breaking API changes
- No new dependencies
