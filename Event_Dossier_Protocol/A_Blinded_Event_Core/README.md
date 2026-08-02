# Layer A — Blinded Event Core

The only layer the **labeling process** (AI proposal + human review/freeze) may read before an event's label is frozen. See `../EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md` Sections 8–11 and 17 for the full process, including the corrected capture-vs-reveal rule.

## Allowed content

- Earnings release and SEC filing facts (Tier 0–1 sourced)
- Segment-level results
- Company guidance, as stated by the company
- Management explanations and direct quotes
- Full transcript and Q&A content
- **Pre-release** consensus estimates, each with a named provider and an as-of date/timestamp
- Competitor/supplier implications, provided they are derived only from the event facts above (not from any post-event market reaction)

## Forbidden content — enforced by the validator before freeze

- Stock-price or return reaction (any window, any magnitude, any phrasing)
- Options prices, implied volatility, or implied move
- Trading-volume reaction
- GST or Wikipedia values
- Analyst upgrades or downgrades
- Post-event estimate revisions
- Analyst price targets
- Market-sentiment language
- Headlines or source titles revealing market reaction — if a source's own title contains forbidden reaction language (e.g., an article titled "...stock jumps 8%"), it must be cited by a paraphrased description in this layer, not quoted verbatim. The MSFT pilot's source table quoted such a title directly; this is now a documented anti-pattern (see `../MSFT_PILOT_QC_AND_DISPOSITION.md`) and a validator fixture case.

Leakage detection is context-aware: an operating statement like "Azure grew 43%" is allowed; a reaction statement like "the stock jumped 8%" is not. See `../validator/README.md`.

## Capture vs. reveal — this layer specifically

Layer A is the layer that is both captured **and** revealed to the labeling process from the start — there is no embargo on Layer A content for its own reviewer. The embargo applies to Layer B/C content being shown to a Layer A reviewer, not to Layer A content itself.

## Schemas

See `schemas/`: `events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, `event_labels.csv`, `event_label_capex_effects.csv`. Headers only — no populated data in this draft. Field-level detail in `SCHEMA_FIELD_DICTIONARY.md`.
