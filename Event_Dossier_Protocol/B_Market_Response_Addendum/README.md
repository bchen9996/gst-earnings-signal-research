# Layer B — Market Response Addendum

## Corrected capture-vs-reveal rule (2026-08-02)

An earlier draft said this layer could not be *created* until Layer A froze. That was wrong — it risks losing transient evidence (a price quote, a media reaction) that cannot be reconstructed later. The corrected rule:

- **Capture** of this layer's content may happen automatically and contemporaneously with Layer A — as soon as the underlying source (a price feed, an analyst note, a media article) is available.
- **Capture and storage do not constitute reveal.**
- This layer's content must remain **embargoed** from anyone performing the Layer A review for the same event, until that event's Layer A label is `human_frozen`.
- **A reviewer exposed to this layer's content before the event's Layer A label is frozen is permanently disqualified from signing that event's blinded label.**
- Every row here records `captured_at_utc`. Reveal to a reviewer/process is a separate, later-recorded event (`revealed_at_utc` in the freeze manifest's `reveal_events`, not in this CSV itself) and must postdate the linked label's `frozen_at_utc`.

## Content

- Analyst estimate revisions (post-event)
- Price-target revisions
- Media interpretation
- Price and volume response
- Options and volatility response

## Schema

See `schemas/market_response_addendum.csv` and `SCHEMA_FIELD_DICTIONARY.md`. Header only — no populated data in this draft. Claims sourced into this layer are tagged `layer = B_market_response` in `claims.csv` and are never merged into a frozen Layer A label.
