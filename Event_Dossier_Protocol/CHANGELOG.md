# Event Dossier Protocol — Changelog

## 2026-08-03 — Validator hardening pass

**Why this changed.** The v0.1 draft (committed `1d8d496`, PR #2) established the three-layer architecture, schemas, and a first-pass deterministic validator (5 gates, 20 fixtures). A follow-up review found the niche label was factually wrong, and that several documented rules (required fields, complete FK validation, freeze-manifest artifact existence, strict timestamp ordering, exact surprise-claim linkage) were either unenforced or only partially enforced. This pass closes those gaps, entirely within `Event_Dossier_Protocol/` — no change to the raw MSFT pilot dossier, PR #1, the Wikipedia reliability worktree, or any operational artifact.

### 1. Niche rename

`niche` renamed from `large_cap_earnings` to **`fixed_24_ticker_earnings_panel`** everywhere (protocol doc, field dictionary, schema enum, validator, all fixtures). The locked v0.1 universe includes `GME` and `NCLH`, which are not large-cap by any conventional definition — the old label was materially inaccurate. The locked 24 tickers themselves are unchanged.

### 2. Mechanical required/conditional/enum/type enforcement

Added a declarative `FIELD_RULES` table (`validate_event_dossier.py`) mechanically enforcing, across every schema table: required (non-blank) fields; enum membership for every declared enum column (not a subset); boolean parsing; ISO date parsing; **timezone-aware** ISO-8601 timestamp parsing (a naive timestamp is now a hard failure); numeric parsing; genuine-integer 1–5 score bounds. Added conditional-requirement checks that don't fit a pure per-field table: `value_type=numeric`→`numeric_value`; `pre_event_consensus_estimate`→provider/as-of/GAAP basis; `human_frozen`→frozen_by/frozen_at_utc/manifest path; amendment→reason; non-null surprise percentage→claim linkage (see below). Added cross-row consistency checks: `earnings_date` vs. `event_datetime_utc` date agreement; `consensus_asof_date` strictly before `earnings_date`; `protocol_version` agreement across `events.csv`/`event_labels.csv`/freeze manifest.

### 3. Complete foreign-key validation

Every FK is now validated, including `corroborates_claim_source_id` (must exist, must not self-reference, must belong to the same `claim_id` as the referencing row) and claim/event consistency (a label's linked claim must belong to the label's own event, not merely exist somewhere). The semicolon-delimited `event_labels.cross_company_implications_claim_id` column — whose individual IDs were never validated — is **removed** and replaced by a normalized child table, `event_label_cross_company_implications.csv`, mirroring the earlier `event_label_capex_effects.csv` precedent. The one remaining legitimately-multi-valued field (`market_response_addendum.post_event_analyst_target_change_claim_ids`) is split and every individual ID validated rather than trusted as an opaque string.

### 4. Freeze-manifest hardening

`freeze_manifest.schema.json` is now an executable contract, not just a shape reference: required/`additionalProperties:false` violations fail; every `layer_a_artifact_hashes[].artifact_path` must resolve to a file that **actually exists** in the fixture (previously silently skipped when absent — a real gap, since "every referenced artifact exists" was always the intent); path traversal (`..`, absolute paths) is rejected; the four required Layer-A artifacts (`events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`) must each appear exactly once; no Layer-B/C path may be referenced; and the manifest's own `event_id`/`frozen_by`/freeze timestamp must agree with the matching `event_labels.csv` row.

### 5. Expanded blinding scan

The reaction-language and forbidden-feature-term scan now covers every Layer-A free-text location: `event_labels.notes`/`management_tone`/`source_completeness`/`amendment_reason`, `management_qna.classification_basis`, `claim_sources.notes`, `event_label_capex_effects.notes`, `event_label_cross_company_implications.notes` — not just `claim_text`/`question_text`/`response_text`/`source_name`. New reaction-language patterns added: "shares gained/climbed", "the stock was up", "market value/cap added". The operating-vs-reaction distinction ("Azure grew 43%" passes, "shares gained 8%" fails) is preserved and re-proven on the new locations.

### 6. Corrected timestamp ordering

`reveal_timestamp > freeze_timestamp` is now **strict** — an equal timestamp fails as ambiguous (the prior `>=` was wrong: simultaneity does not prove reveal happened after freeze). A reviewer exposed at or before freeze (not just strictly before) is disqualified. Naive or otherwise non-timezone-aware timestamps anywhere in a freeze manifest now fail validation explicitly via `_parse_ts_strict()`, instead of risking an unhandled comparison exception when mixed with an aware timestamp.

### 7. Explicit surprise-percentage evidence linkage

`event_labels.csv` gains four new columns: `eps_actual_claim_id`, `eps_consensus_claim_id`, `revenue_actual_claim_id`, `revenue_consensus_claim_id`. A non-null `eps_surprise_pct`/`revenue_surprise_pct` now requires these to be populated and to resolve to real claims of the correct category, compatible unit, and the SAME GAAP basis. For a `human_frozen` label, both linked claims must independently satisfy direct-source/provider/as-of requirements, and the stored surprise percentage is **independently recomputed** from the linked claims' `numeric_value`s and compared to the stored value within `SURPRISE_PCT_TOLERANCE = 0.05` percentage points — disagreement fails. A null surprise percentage remains valid without linkage when consensus is unverifiable; the validator never infers a missing value.

### 8. Tests and fixtures

All 20 original fixture outcomes preserved. 28 new fixtures added (48 total) covering: empty required fields, malformed numerics, out-of-range scores, naive timestamps, every newly-enforced FK (`corroborates_claim_source_id` invalid/cross-claim, capex-effect/cross-company-implications evidence claims, claim/event mismatch), freeze-manifest hardening (missing required artifact, nonexistent artifact file, path traversal, duplicate entry, Layer-B/C leak, missing required JSON field, additionalProperties violation, manifest/label disagreement), equal reveal/freeze timestamps, mismatched GAAP bases, incorrect vs. correct surprise arithmetic, null/unverifiable consensus linkage, every new reaction-language location, and the niche rename (old value rejected, new value accepted). Full suite: `python validator/test_validate_event_dossier.py` — 10 test methods, all fixture cases verified via `subTest`.

Only deterministic dossier-validator tests were run. No live research, no Public Equity Investing work, no market-data joins, no Phase 2 panel execution, no GST/Wikipedia operation was performed from this worktree.
