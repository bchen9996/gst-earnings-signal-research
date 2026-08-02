# Layer B Schema Field Dictionary

**Revision 2 (2026-08-02)**: `revealed_at_utc`/`revealed_by` moved out of this CSV. Capture and reveal are now distinct events — capture is recorded here (`captured_at_utc`), reveal is recorded in the linked label's `freeze_manifest.json` (`reveal_events[]`), so that a row can exist here (captured) well before any reveal has happened, without implying reveal.

## market_response_addendum.csv

| Field | Type | Required | Notes |
|---|---|---|---|
| addendum_id | string | yes | `{event_id}-ADD-{seq:02d}` |
| event_id | string | yes | FK → events.csv |
| linked_label_id | string | yes | FK → event_labels.csv. **Row may be created regardless of the linked label's status** — capture is not gated on freeze. Reveal is gated (enforced in the freeze manifest, not here). |
| captured_at_utc | timestamp | yes | When this evidence was fetched/recorded — may be before, during, or after the linked label's freeze |
| captured_by | string | yes | `ai` or process identity performing capture |
| price_reaction_pct | number | no | |
| price_reaction_window | enum | conditional | `after_hours` \| `next_session_close` \| `multi_session` \| other documented window — required if `price_reaction_pct` set, given the MSFT pilot's unresolved 8%/9%/14.68% window-conflation issue |
| volume_reaction | string | no | |
| iv_reaction | string | no | |
| options_reaction_notes | string | no | |
| post_event_analyst_target_change_claim_ids | string | no | Semicolon-delimited FK list → claims.csv rows tagged `layer = B_market_response` |
| post_event_media_sentiment_notes | string | no | |
| notes | string | no | |

Reveal timestamps, reveal actor, and the reviewer-exposure-before-freeze check all live in `event_labels`'s linked `freeze_manifest.json` (`schemas/freeze_manifest.schema.json`), not in this file — this file only ever records what was captured and when, never who has seen it or when they saw it.
