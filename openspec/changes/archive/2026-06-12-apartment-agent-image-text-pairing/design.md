## Context

The apartment agent pipeline (`app/modules/apartment_agent/pipeline.py`) groups crawled Zalo messages into "logical listings" before sending each to the LLM. The grouping happens in `app/modules/apartment_agent/grouping.py::group_messages` and is a pure function of the input list — no DB, no I/O, no async.

The current rule is **time-window + same-sender**: a new message is appended to the current group if it is from the same sender AND its timestamp is within `window_minutes` of the **first** message in the group (default 3 minutes, env-configurable). The rule is documented in the still-active `apartment-agent-group-messages-by-sender-time` change.

The empirical failure on the `Elite24 Apartment` crawl (50 messages, same sender, posted back-to-back over a few minutes) showed `max_group=20` — 20 messages from one sender, all within the 3-min window, merged into a single group. The LLM then received a 20-message prompt and could not separate the listings, so image URLs from listing A leaked into the listing B output.

The Zalo pattern that the rule was originally written for — `text → 1..N images` from one poster, in any order, posted within minutes — is what we still need to capture. The over-grouping comes from the fact that a *power-user* broker posts **multiple listings** in the same 3-min stretch, and the rule cannot tell them apart. The boundary signal that is *visible* in the message stream is the **content type transition** (text vs image), not the clock.

This change replaces the time-only walk with a content-type walk and adds a hard size cap.

## Goals / Non-Goals

**Goals:**
- Group consecutive messages from the same sender into **listing-shaped units** (typically `1 text + 0..N images` in either order), not time-shaped units.
- Detect listing boundaries using content-type transitions: text-after-text, text-after-image-group, sender change, deleted/system/sticker messages, hard size cap, and a time-gap fallback.
- Preserve the existing 33 grouping tests; add ~9 new ones for the boundary conditions.
- Keep the grouper a pure function: same input → same groups, no DB, no LLM, no async.
- Add observability: log per-group content type pair (`text+3img`, `2img`, `text`, …) so production over/under-grouping is visible.
- Stay backward compatible on the API surface: `MessageGroup`, `source_message_ids`, `raw_message_id` keep the same shape.
- Default cap of 4 (covers the 90th percentile of "1 text + 3 photos" Zalo listings); env-tunable.

**Non-Goals:**
- Cross-sender grouping (two different posters = two listings; unchanged).
- Re-grouping already-grouped outputs.
- Persisting groups back to `zalo_messages` (groups remain ephemeral pipeline state).
- Changing the LLM schema or the LLM prompt.
- Adding vision to the LLM (image URLs are still text-only context, unchanged).
- Detecting listing boundaries inside a single multi-listing text message (the LLM still has to do that; not a grouper problem).
- Auto-classifying image-only messages as listings (no text → still dropped by the LLM `is_apartment_listing=false` path; that's a separate problem).

## Decisions

### D1: Content type classification is per-message, from existing fields

**Choice:** A `_classify_content_type(msg) -> "text_only" | "image_only" | "mixed"` helper derives the type from the existing `text` (or `content`) and `image_urls` fields:

- `text_only` = non-empty `text` AND empty `image_urls`
- `image_only` = empty/whitespace `text` AND non-empty `image_urls`
- `mixed` = both non-empty (rare; treated as `text_only` to bias toward splitting)

**Rationale:** the LLM was already receiving the same `(text, image_urls)` tuple, and the existing `image_filter.py` does the URL-shape filtering. We just need a boolean "is there any text?" / "is there any image?" split.

**Alternatives considered:** add a new `content_type` column on `zalo_messages` — rejected: requires a Supabase migration and a crawler change, and the type is trivially derivable from existing fields. Send both fields to the LLM unchanged — accepted (no schema change), but the type is computed in the grouper, not the LLM.

### D2: Boundary conditions (in order of precedence)

The walk closes the current group and starts a new one if **any** of the following is true:

1. **Skip-trigger messages** (`is_deleted=True`, `type in {sticker, system}`) → close group, drop the message. Unchanged from the current rule.
2. **Sender change** → close group, start new. Unchanged.
3. **No-sender / no-timestamp message** → singleton (the LLM gets a single message as its own group). Unchanged.
4. **Text-text boundary** → a `text_only` message after a group whose only messages are `text_only` (i.e. the previous listing was text-only) → close group, start new.
5. **Text-after-images boundary** → a `text_only` message after a group whose last message is `image_only` (i.e. the previous group has photos, this text is the start of the *next* listing) → close group, start new.
6. **Hard size cap** → a group already at `max_messages_per_group` cannot accept more → close group, start new.
7. **Time-gap fallback** → a message whose timestamp is more than `time_fallback_minutes` after the **first** message in the group → close group, start new. Default 1 min.

Otherwise: append to the current group.

**Rationale:** boundary 4 captures the "next text starts a new listing" case the user described. Boundary 5 captures "this text describes the *next* listing, not the previous images" — Vietnamese Zalo real-estate groups post photos first and the description after, but the description is the *next* listing's, not the photos' (the photos are the *previous* listing's, with no text). Boundary 6 is the safety net for power users; boundary 7 is the safety net for the 5-min phone-call case.

**Alternatives considered:** make every text-after-image a boundary, period (always split) — rejected: would split legitimate "text intro then 5 photos" listings. Use a learned boundary detector (LLM or classifier) — rejected: doubles LLM cost, no offline path. Use image-content hashing to pair images back to their text — rejected: image download + perceptual hash adds 1-2 s per group and a new dependency.

### D3: Hard cap is per-group, default 4

**Choice:** `max_messages_per_group: int = 4`. A group that hits 4 messages closes on the next same-pattern message. The next message starts a new group.

**Rationale:** in our crawls, the modal Zalo apartment listing is 1 text + 1..3 images. A 4-message cap covers that with room to spare (1 text + 3 images). Listings with 5+ photos split — the LLM dedup layer (`app/modules/apartment_agent/dedup.py`) catches the duplicate villa, so the only cost is a second LLM call. The cap is env-tunable: lower to 2 if you want strict "always 2 messages" behavior; raise to 6 if you see under-grouping.

**Alternatives considered:** dynamic cap based on sender's prior posting pattern — rejected: cold-start problem, no data yet. Per-group soft cap with an "if last message is image, allow more" rule — over-engineering for the current scale.

### D4: Time fallback is 1 minute (down from 3)

**Choice:** `time_fallback_minutes: int = 1`. Same semantics as the current `window_minutes` (gap from the **first** message in the group), but tighter.

**Rationale:** the 3-minute default was a guess; the 1-minute value is a *fallback* now, not the primary signal, so a tighter default is safer. If a user pauses 5 min to grab coffee mid-post, the next message becomes a new group — the LLM may then fail to extract (no text/images together) which is the same behavior as today, not a regression.

**Alternatives considered:** keep the 3-min fallback — rejected: defeats the point of this change. 30 seconds — too tight, breaks the "grab coffee" case. No time fallback at all (pure content-type) — too aggressive: a user who posts text, then 4 minutes later posts the photos, gets them as separate groups.

### D5: Backward compatibility on the env var name

**Choice:** the old `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` env var is read as the new `time_fallback_minutes` for one release. A deprecation warning is logged if the old name is set but the new name is not. The old name is removed in the release after that.

**Rationale:** the previous `apartment-agent-group-messages-by-sender-time` change shipped `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` as the primary env var. Renaming silently would break any deployment that set the old name. Aliasing for one release gives operators a clear migration path.

**Alternatives considered:** break the env var name immediately — rejected: silent failure mode (operator thinks the grouper is grouping, but it's not). Keep the old name forever — rejected: the semantics *are* changing (fallback vs primary), so the name should change too.

### D6: Observability — log the content type pair

**Choice:** the existing `Message grouping: 50 messages → 3 groups, max_group=20, multi_groups=3` log line gains a third field: `pairs={text+3img: 2, 2img: 1, text: 0}`. The pair is the count of `text_only` + N×`image_only` messages in the group, in `text→image` order. Singletons are `text`, `image`, or `mixed`.

**Rationale:** the previous log told you *how many* over-groupings happened; the new log tells you *what kind* of group was over-sized. If `pairs.text+3img` is the dominant over-grouped pair, raise the cap to 5. If `pairs.4img` shows up, the broker posted a 4-photo listing that got merged with the next text — lower the cap to 3.

**Alternatives considered:** log the full message-id list per group — too noisy at 50 messages. Log a JSON object with per-group `id → pair` — same data, harder to grep.

## Risks / Trade-offs

- **Under-grouping a 5-photo listing** → Mitigation: cap is env-tunable. Document `AGENT_MESSAGE_GROUP_MAX_SIZE=5` as a known good alternative for power users with many photos. Dedup catches the duplicate villa in the LLM output.
- **Existing 33 grouping tests may break** if any rely on a 4+ message time-only group → Mitigation: audit the existing test file (`tests/test_apartment_agent_grouping.py`) before changing the walk; tests that break get an explicit `max_messages_per_group=99` override to preserve their original intent.
- **Text-after-image boundary may split legitimate "text intro then 5 photos" listings** → if the photos are split off into their own group, the LLM gets the photos with no text and returns `is_apartment_listing=false`. The current grouper never caused this because time was the only signal. Mitigation: order matters — the rule says "text after image group" is a boundary, not "any text after any image" — so a `text_only → 5×image_only` sequence still stays together (the text is *first*, not after). The boundary fires when the *new* message is text and the *current* group's last message is image — which means the previous group is "all images" and this text starts a new listing.
- **Mixed-content messages** (text + images in the same row) → treated as `text_only` for boundary purposes. This biases toward splitting, which is the safer failure mode (dedup catches the split case; over-merge corrupts the data).
- **The 1-min time fallback may be too tight for slow uploaders** → Mitigation: env-tunable; document the knob.
- **Log volume increase** from the per-group `pairs` field → negligible (one log line per pipeline run, 200 chars max).
- **The earlier `apartment-agent-group-messages-by-sender-time` change becomes obsolete** once this ships. Mitigation: archive the older change via `openspec archive` after this one is merged; the older change's design.md notes that the window is "configurable" so the env-var migration is the only artifact loss.

## Migration Plan

1. Land this change behind the existing endpoints. The response shape (`MessageGroup` with `source_message_ids`) is unchanged — no FE work.
2. Default values: `AGENT_MESSAGE_GROUP_MAX_SIZE=4`, `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES=1`. Existing deployments that set `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` continue to work via the alias; a deprecation warning is logged once per process.
3. Observe the new `pairs` log field for one week. If `pairs.text+3img` dominates, raise the cap to 5. If `pairs.4img` shows up, lower to 3.
4. Remove the old env var name in the release after the one shipping this change. Update `.env.example` to drop the legacy line.
5. Archive the older `apartment-agent-group-messages-by-sender-time` change (its grouping section is now superseded).
6. Rollback: set `AGENT_MESSAGE_GROUP_MAX_SIZE=999` and `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES=3` to restore the old behavior, or revert the PR.

## Open Questions

- Should the `text-after-images` boundary also fire when the current group has *any* image (not just image-only), to handle the rare `mixed`-then-text case? — *Default: no, only image-only last message fires the boundary. Mixed is treated as `text_only` per D1, so the current group ends in a "text" from the boundary's point of view, and the next text is a `text→text` boundary, which already fires.*
- Should the LLM prompt be updated to tell the model "you may receive up to N photos that belong to the same listing" so the model is calibrated? — *Defer: no data yet on whether the model is failing on multi-photo groups.*
- Should the `pairs` log line include the `group_id` so we can correlate with the LLM call's output? — *Defer: LLM call correlation is not in scope for this change; the existing `test-extract` response shape already gives us `raw_message_id` for that.*
