# Deterministic Validation Checklist — v0.1 DRAFT

Pre-freeze gate. Every item must pass before an `event_labels.csv` row may move from `ai_proposed` to `human_frozen`. **Implemented** as `validator/validate_event_dossier.py` (run: `python validator/validate_event_dossier.py <fixture_dir>`); this document is the human-readable specification the validator's gates were built from, kept in sync with it. See `validator/README.md` for gate-by-gate implementation detail and `validator/test_validate_event_dossier.py` for the 48-fixture regression suite proving each item below.

## 1. Stable IDs
- [x] `event_id` matches `EVT-{TICKER}-{FISCAL_PERIOD_COMPACT}-{EVENT_TYPE}` and is unique across `events.csv`
- [x] Every `claim_id`, `claim_source_id`, `qna_id`, `label_id`, `capex_effect_id`, `implication_id`, `addendum_id` is unique within its table and correctly prefixed with its parent `event_id`/`label_id`
- [x] No ID has been reused or renumbered after being referenced by another row (append-only discipline; see item 10)

## 2. Required and conditional fields (2026-08-03: mechanically enforced, not just documented)
- [x] Every row in every present schema has all fields marked `required` in the field dictionaries non-blank
- [x] Conditional requirements are enforced: `value_type=numeric` → `numeric_value` required; `claim_category=pre_event_consensus_estimate` → `consensus_provider`/`consensus_asof_date`/`gaap_basis` required; `label_status=human_frozen` → `frozen_by`/`frozen_at_utc`/`freeze_manifest_path` required; `amendment_of_label_id` set → `amendment_reason` required; `eps_surprise_pct`/`revenue_surprise_pct` non-null → the matching actual+consensus claim-ID linkage fields required (item 12)
- [x] `event_labels.csv` rows have non-null `primary_positive_catalyst_claim_id` and `primary_negative_catalyst_claim_id`, both resolving to real `claims.csv` rows belonging to the SAME event

## 3. Allowed enums (2026-08-03: every enum column checked, not a subset)
- [x] `management_qna.classification ∈ {fully_answered, partially_answered, not_answered, not_classifiable}` — no free text, no legacy "Unresolved"-style label
- [x] `event_labels.guidance_direction` uses the 8-value taxonomy (protocol §15.2) — never a bare `raised`/`lowered` without distinguishing first-guide-vs-consensus from raised/lowered-prior-guide
- [x] `event_labels.capex_operational_direction` and the child table `event_label_capex_effects.capex_accounting_presentation_effect` are both populated and are never merged into a single free-text `capex_direction`
- [x] `claims.claim_category ∈ {reported_fact, management_claim, pre_event_consensus_estimate, analyst_interpretation, ai_proposed_classification, human_frozen_label}` for every claim
- [x] `claims.value_type`, `gaap_basis`, `currency_basis`, `comparison_period`, `novelty_eval_basis`, `verification_status`, `layer` are all enum-checked
- [x] `claim_sources.retrieval_method ∈ {direct_fetch, search_snippet, blocked, not_attempted}` and `source_tier ∈ {0,1,2,3,4,5}` for every source row
- [x] `events.event_disposition ∈ {development_pilot, confirmatory, compromised}` and never transitions from `confirmatory` back to itself after leaving it (via optional `disposition_history.csv`)
- [x] `events.niche ∈ {fixed_24_ticker_earnings_panel}` — the superseded `large_cap_earnings` value is rejected (see protocol §1)

## 4. Numeric, integer, date, and timezone-aware timestamp parsing (new 2026-08-03)
- [x] Every declared numeric field (`numeric_value`, `eps_surprise_pct`, `revenue_surprise_pct`) parses as a real number when non-blank
- [x] `information_novelty_score_1_to_5` and `uncertainty_remaining_score_1_to_5` parse as genuine INTEGERS (not `3.5`, not `"three"`) and fall within `[1,5]`
- [x] `earnings_date` and `consensus_asof_date` parse as real ISO dates
- [x] Every declared timestamp field parses as a timezone-AWARE ISO-8601 timestamp (`Z` or an explicit `+HH:MM`/`-HH:MM` offset) — a naive timestamp is a validation FAILURE, never silently treated as UTC, and never raises a Python exception during comparison (see item 13)

## 5. Cross-row consistency (new 2026-08-03)
- [x] `events.earnings_date` matches the date portion of `events.event_datetime_utc` for the same row
- [x] `claims.consensus_asof_date` is strictly BEFORE the referenced event's `earnings_date` for every `pre_event_consensus_estimate` claim
- [x] `protocol_version` agrees across `events.csv`, `event_labels.csv`, and any linked `freeze_manifest.json` for the same event/label

## 6. Complete foreign-key validation (2026-08-03: every FK, no semicolon-delimited ID silently trusted)
- [x] `claims.event_id`, `management_qna.event_id`, `market_response_addendum.event_id`/`linked_label_id` all resolve
- [x] `event_labels.event_id`, `primary_positive_catalyst_claim_id`, `primary_negative_catalyst_claim_id`, `eps_actual_claim_id`, `eps_consensus_claim_id`, `revenue_actual_claim_id`, `revenue_consensus_claim_id`, `amendment_of_label_id` all resolve, and no linked claim belongs to a DIFFERENT event than the label (claim/event consistency)
- [x] `claim_sources.claim_id` resolves; `corroborates_claim_source_id` resolves, does not self-reference, and belongs to the SAME `claim_id` as the referencing row
- [x] `event_label_capex_effects.label_id`/`evidence_claim_id` resolve
- [x] `event_label_cross_company_implications.label_id`/`claim_id` resolve — this new normalized child table replaces the old semicolon-delimited `event_labels.cross_company_implications_claim_id` column, whose individual IDs were never validated
- [x] Any remaining semicolon-delimited reference field (`market_response_addendum.post_event_analyst_target_change_claim_ids`) is split and every individual ID validated, not trusted as an opaque string

## 7. Direct-source requirement
- [x] Every numeric claim feeding a to-be-frozen label has ≥1 linked `claim_sources.csv` row with `retrieval_method = direct_fetch` and `source_tier ≤ 3` — including, specifically, the EPS/revenue actual and consensus claims linked via item 12
- [x] No claim with `retrieval_method = search_snippet` as its *only* source is used in a computed surprise percentage or a frozen categorical label — it is flagged `verification_status = unverifiable` instead
- [x] No consensus figure from a different provider is blended with another provider's figure into one value

## 8. Consensus provider/timestamp requirement
- [x] Every `claims.csv` row with `claim_category = pre_event_consensus_estimate` has both `consensus_provider` and `consensus_asof_date` populated
- [x] `consensus_asof_date` strictly predates `events.earnings_date` (see item 5)

## 9. No forbidden feature fields
- [x] No column in any Layer-A schema contains a price, return, volume, options/IV, GST, or Wikipedia value for any row where the linked event's label is not yet `human_frozen`
- [x] No `market_response_addendum.csv` row is REVEALED before its linked label is `human_frozen`; a `captured_at_utc` row may exist earlier (capture ≠ reveal — protocol §8)

## 10. No forbidden reaction language in narrative text (2026-08-03: every Layer-A free-text location, not a subset)
- [x] Scanned locations: `claims.claim_text`; `management_qna.question_text`/`response_text`/`classification_basis`; `claim_sources.source_name`/`notes` (for Layer-A-linked claims); `event_labels.notes`/`management_tone`/`source_completeness`/`amendment_reason`; `event_label_capex_effects.notes`; `event_label_cross_company_implications.notes`; and any `narrative_text.txt`
- [x] Detection is context-aware: `"Azure grew 43%"` passes; `"shares gained 8%"`, `"the stock was up 9%"`, `"market value added..."`, and other reaction phrasings fail, regardless of which of the fields above they appear in
- [x] This check specifically fails the MSFT pilot's Section 11 and Section 13 text — the checklist's own regression case (`test_msft_pilot_artifacts_fail_validation_as_expected`)

## 11. No source titles containing price-reaction information in the blinded packet
- [x] Every `claim_sources.source_name` used within Layer A is checked against the same reaction-language pattern list as item 10 — a source may be *cited* (by URL/paraphrased description) even if its own title contains such language, but the title string itself must not be reproduced verbatim in a Layer-A field
- [x] This check specifically fails the MSFT pilot's source-inventory table (S5 title quoted verbatim) — used as a second regression case

## 12. Explicit surprise-percentage evidence linkage (new 2026-08-03)
- [x] A non-null `eps_surprise_pct`/`revenue_surprise_pct` requires its own `*_actual_claim_id` and `*_consensus_claim_id`, not merely "any" consensus claim for the event
- [x] The actual claim's `claim_category ∈ {reported_fact, management_claim}`; the consensus claim's `claim_category = pre_event_consensus_estimate`
- [x] Actual and consensus claims must share a compatible `unit` and the SAME `gaap_basis` — a GAAP-actual paired with a non-GAAP-consensus fails
- [x] For a `human_frozen` label, both linked claims independently satisfy the direct-source and provider/as-of requirements (items 7–8), and the stored surprise percentage is INDEPENDENTLY RECOMPUTED from the linked claims' `numeric_value`s and compared to the stored value within a documented tolerance (`SURPRISE_PCT_TOLERANCE = 0.05` percentage points) — disagreement fails
- [x] A null surprise percentage remains valid (no linkage required) when consensus is unverifiable or was never computed — never inferred or filled in by the validator

## 13. Freeze-manifest hardening (2026-08-03: `freeze_manifest.schema.json` as an executable contract)
- [x] Every `layer_a_artifact_hashes[].artifact_path` resolves to a file that ACTUALLY EXISTS within that event's fixture (Layer-A) directory — a referenced-but-missing artifact fails, it is never treated as a soft/optional check
- [x] The resolved path stays strictly within the fixture directory — no path traversal (`..`, absolute paths) is accepted
- [x] Every required Layer-A artifact basename (`events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`) appears in the inventory EXACTLY ONCE — missing or duplicated entries both fail
- [x] No artifact_path referencing a Layer-B/C location (`market_response_addendum.csv`, `B_Market_Response_Addendum`, `C_Attention_Feature_Join`) is accepted in a Layer-A manifest
- [x] Recorded `sha256` values match the artifact's actual current hash — a changed Layer-A artifact after freeze fails (unchanged from Revision 2)
- [x] The manifest's own `event_id`, `label_id`, `frozen_by`, and `freeze_timestamp_utc` must agree with the matching `event_labels.csv` row — any disagreement fails
- [x] The manifest is validated against `freeze_manifest.schema.json`'s own `required`/`additionalProperties: false` contract: a missing required top-level field, or an undeclared extra field, fails
- [x] Malformed JSON fails outright, not silently skipped

## 14. Timestamp ordering (2026-08-03 correction)
- [x] `reveal_timestamp > freeze_timestamp` STRICTLY — an EQUAL timestamp fails as ambiguous (Revision 2 incorrectly allowed `>=`)
- [x] A reviewer exposed to Layer B/C AT OR BEFORE freeze (not just strictly before) is disqualified from signing that label
- [x] A naive or otherwise non-timezone-aware timestamp anywhere in a freeze manifest's timestamp fields fails validation explicitly — the validator never raises a comparison exception on mixed naive/aware values

## 15. All labels pending until human review
- [x] Every newly created `event_labels.csv` row starts at `label_status = ai_proposed` (or `draft`), never `human_frozen`, until a recorded `frozen_by`/`frozen_at_utc` exists, and `frozen_by` must be a human identity (not `ai`/`system`)
- [x] `human_verification_status = pending` is the required default for any dossier/table artifact produced outside this formal pipeline (e.g., the MSFT pilot's own table) and must not be silently changed by anything other than a recorded human action

## 16. Confirmatory events cannot be relabeled after feature reveal without an amendment record
- [x] No `event_labels.csv` row is edited in place; every correction is a new row with `amendment_of_label_id` set and `amendment_reason` populated
- [x] `events.event_disposition` cannot move back to `confirmatory` after being `development_pilot`/`compromised` (via optional `disposition_history.csv`)

---

**Status:** all 16 sections above are implemented in `validator/validate_event_dossier.py` and proven by the 48-fixture regression suite in `validator/test_validate_event_dossier.py` (`python validator/test_validate_event_dossier.py`). The validator remains a **guardrail, not proof of perfect blinding** (protocol §18) — regex-based text scanning and the other mechanical checks here catch a large, well-tested class of violations, but human review is still required for every label before freeze.
