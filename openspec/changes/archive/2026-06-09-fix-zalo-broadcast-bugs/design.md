## Context

The Zalo broadcast panel (`ZaloBroadcastPanel.tsx`) lets users select Zalo conversations and send messages. It merges two data sources: live groups from the Zalo API and crawled/saved groups from Supabase. The code review found 3 critical bugs, plus dead code and UX issues.

## Goals / Non-Goals

**Goals:**
- Fix all 9 verified defects from the code review
- Ensure broadcast targets always have valid Zalo group IDs when sending
- Ensure selection state survives data merges
- Remove dead code and fix UX glitches

**Non-Goals:**
- Refactoring the entire Zalo crawler architecture
- Adding new features
- Fixing efficiency issues

## Decisions

### D1: Fix group_id in savedToLiveConversation
Set `group_id: null` for crawled groups without real IDs. Add UI indicator. Add validation in handleSend.

### D2: Fix mergeConversations selection loss
After merge, remap selectedConversationIds when group_id changes.

### D3: Fix race condition
Add `hasLiveTargets` flag. Skip loadSavedTargets merge when live data already loaded.

### D4: Fix diacritic collisions
Use composite key `normalizeSearchText(name) + "|" + group_id` for dedup.

### D5: Fix manual textarea overwrite
Merge manual entries with existing targets instead of overwriting.

### D6: Expose worker selector
Remove `{false}` guard, render conditionally.

### D7: Fix soft warnings
Only reject on hard errors in create_broadcast.

### D8: Preserve selected messages
Don't clear messageCache on userId change.

### D9: Fix maxMessagesPerGroup input
Allow empty string in state, validate on blur.

## Risks / Trade-offs

- **[Risk]** Fixing group_id may break name-based ID workflows. **→ Mitigation:** Name-based IDs were always broken.
- **[Risk]** hasLiveTargets flag adds sync state. **→ Mitigation:** Simple boolean.
