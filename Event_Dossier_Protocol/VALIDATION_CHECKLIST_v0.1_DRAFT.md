# Deterministic Validation Checklist — v0.1 DRAFT

Intended as a pre-freeze gate (eventually a script; not implemented in this draft — see "unresolved design choices" in the accompanying chat report). Every item must pass before an `event_labels.csv` row may move from `ai_proposed` to `human_frozen`.

## 1. Stable IDs
- [ ] `event_id` matches `EVT-{TICKER}-{FISCAL_PERIOD_COMPACT}-{EVENT_TYPE}` and is unique across `events.csv`
- [ ] Every `claim_id`, `claim_source_id`, `qna_id`, `label_id`, `addendum_id` is unique within its table and correctly prefixed with its parent `event_id`
- [ ] No ID has been reused or renumbered after being referenced by another row

## 2. Required fields
- [ ] Every row in every schema has all fields marked `required` in the field dictionaries populated, or explicitly `null` with a corresponding `verification_status`/reason
- [ ] `event_labels.csv` rows have non-null `primary_positive_catalyst_claim_id` and `primary_negative_catalyst_claim_id`, both resolving to real `claims.csv` rows

## 3. Allowed enums
- [ ] `management_qna.classification ∈ {fully_answered, partially_answered, not_answered, not_classifiable}` — no free text, no legacy "Unresolved"-style label
- [ ] `event_labels.guidance_direction` uses the 8-value taxonomy (protocol §15.2) — never a bare `raised`/`lowered` without distinguishing first-guide-vs-consensus from raised/lowered-prior-guide
- [ ] `event_labels.capex_operational_direction` and `capex_accounting_presentation_effect` are both populated and are never merged into a single free-text `capex_direction`
- [ ] `claims.claim_category ∈ {reported_fact, management_claim, consensus_estimate, analyst_interpretation, ai_proposed_classification, human_frozen_label}` for every claim
- [ ] `claim_sources.retrieval_method ∈ {direct_fetch, search_snippet, blocked, not_attempted}` and `source_tier ∈ {0,1,2,3,4,5}` for every source row
- [ ] `events.event_disposition ∈ {development_pilot, confirmatory, compromised}` and never transitions from `confirmatory` back to itself after leaving it

## 4. Direct-source requirement
- [ ] Every numeric claim feeding a to-be-frozen label has ≥1 linked `claim_sources.csv` row with `retrieval_method = direct_fetch` and `source_tier ≤ 3`
- [ ] No claim with `retrieval_method = search_snippet` as its *only* source is used in a computed surprise percentage or a frozen categorical label — it is flagged `verification_status = unverifiable` instead
- [ ] No consensus figure from a different provider is blended with another provider's figure into one value

## 5. Consensus timestamp requirement
- [ ] Every `claims.csv` row with `claim_category = consensus_estimate` has both `consensus_provider` and `consensus_asof_date` populated
- [ ] `consensus_asof_date` predates `events.earnings_date`

## 6. No forbidden feature fields
- [ ] No column in any Layer-A schema (`events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, `event_labels.csv`) contains a price, return, volume, options/IV, GST, or Wikipedia value for any row where the linked event's label is not yet `human_frozen`
- [ ] No `market_response_addendum.csv` row exists for an event whose linked `event_labels.csv` row is not `human_frozen`, and `revealed_at_utc` postdates `frozen_at_utc`

## 7. No forbidden reaction language in narrative text
- [ ] Any free-text field (`claim_text`, `question_text`, `response_text`, `notes`, or an accompanying `dossier.md`-equivalent narrative) is scanned for stock-price/return-percentage patterns, volume-reaction phrasing, options/IV reaction phrasing, and analyst-reaction phrasing (upgrade/downgrade, price-target language) — any match blocks freeze until removed or moved to Layer B
- [ ] This check specifically would have failed the MSFT pilot's Section 11 and Section 13 text — used as the checklist's own regression case

## 8. No source titles containing price-reaction information in the blinded packet
- [ ] Every `claim_sources.source_name` used within Layer A is checked against the same reaction-language pattern list as item 7 — a source may be *cited* (by URL/paraphrased description) even if its own title contains such language, but the title string itself must not be reproduced verbatim in a Layer-A field
- [ ] This check specifically would have failed the MSFT pilot's source-inventory table (S5 title quoted verbatim) — used as a second regression case

## 9. All labels pending until human review
- [ ] Every newly created `event_labels.csv` row starts at `label_status = ai_proposed` (or `draft`), never `human_frozen`, until a recorded `frozen_by`/`frozen_at_utc` exists
- [ ] `human_verification_status = pending` is the required default for any dossier/table artifact produced outside this formal pipeline (e.g., the MSFT pilot's own table) and must not be silently changed by anything other than a recorded human action

## 10. Confirmatory events cannot be relabeled after feature reveal without an amendment record
- [ ] No `event_labels.csv` row is edited in place; every correction is a new row with `amendment_of_label_id` set and `amendment_reason` populated
- [ ] If an amendment is requested for an event that already has a Layer C (Attention Feature Join) record, the event is instead set to `event_disposition = compromised` and excluded — the checklist blocks a same-label amendment in this case rather than allowing it

---

**Regression cases:** items 7 and 8 are written specifically so that running this checklist against the preserved MSFT pilot artifacts (`Live Signal Engine/Phase2_Event_Dossiers/MSFT_FY2026Q4_POST_EVENT_D2/dossier.md`) should **fail** — that failure is the checklist's own proof of correctness once it is implemented as executable validation. This has not yet been implemented or run (see unresolved design choices).
