## 1. Fix ZaloBroadcastPanel critical bugs

- [x] 1.1 Change `savedToLiveConversation` to set `group_id: null` instead of display name; add UI indicator for groups without real IDs
- [x] 1.2 Add `hasLiveTargets` flag; skip `loadSavedTargets` merge when live data already loaded
- [x] 1.3 Update `mergeConversations` to remap `selectedConversationIds` when group_id changes
- [x] 1.4 Change `normalizeTargets` to merge manual entries with existing targets instead of overwriting by key
- [x] 1.5 Change dedup key to composite `normalizeSearchText(name) + "|" + group_id` in both `normalizeTargets` and `mergeConversations`
- [x] 1.6 Add validation in `handleSend` to reject targets with null group_id

## 2. Fix ZaloCrawlerConfigCard dead code

- [x] 2.1 Remove `{false ? ... : null}` guard on worker selector; render conditionally based on worker availability
- [x] 2.2 Fix worker status IIFE: use `||` instead of `??` for fallback, remove unreachable `if (!worker)` check

## 3. Fix campaign creation and library panel

- [x] 3.1 In `broadcasts.py`, change `create_broadcast` to only reject on hard errors, not soft warnings
- [x] 3.2 In `ZaloSupabaseLibraryPanel`, preserve selected message IDs when userId changes (don't clear messageCache on userId change)

## 4. Fix UX glitches

- [x] 4.1 Fix maxMessagesPerGroup input: allow empty string in state, validate on blur
