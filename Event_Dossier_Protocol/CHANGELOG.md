# Event Dossier Protocol — Changelog

## 2026-08-03 — CI, MSFT pilot structured migration, end-to-end tests

**Why this changed.** Closing out the infrastructure phase: a narrow CI gate so the deterministic validator suite runs automatically on every PR touching this protocol, and a genuine end-to-end exercise of the full validation sequence (draft → proposed → human-review readiness → freeze → immutable bundle) against real, imperfect, pre-protocol data rather than only hand-built fixtures.

### 1. GitHub Actions CI

`.github/workflows/event-dossier-validator-tests.yml` (new): runs `validator/test_validate_event_dossier.py` on `pull_request` (scoped to `Event_Dossier_Protocol/**` changes) and `workflow_dispatch`. Pinned Python 3.12, dependencies installed from `validator/requirements.txt`, `permissions: contents: read` (least privilege — no write access anywhere), no other step. Never touches live market data, GST, Wikipedia, SEC, or news sources — there is no network access in the job beyond checkout/dependency installation, and the validator itself is statically guarded against ever importing one.

### 2. MSFT FY2026 Q4 pilot: structured migration and full validation-sequence exercise

`Event_Dossier_Protocol/migrations/MSFT_FY2026Q4_pilot_migration/` (new): a separate, structured migration of the existing MSFT pilot into the current schema (`events.csv`/`claims.csv`/`claim_sources.csv`/`management_qna.csv`/`event_labels.csv`/`event_label_capex_effects.csv`/`narrative_text.txt`), built by hand-transcribing every value from `dossier.md`/`dossier_table.csv` and `MSFT_PILOT_QC_AND_DISPOSITION.md` — the raw original dossier files were not read programmatically and remain byte-for-byte unchanged (hashes verified before and after). Permanent classification unchanged and reaffirmed: `event_disposition=development_pilot`, `blinding_compromised_for_confirmatory_use=true` — this event can never become confirmatory, under any remediation.

Ran the full validation sequence against this migration and recorded the REAL results, without weakening any gate to force a pass: draft and proposed modes both fail with 10 genuine findings (two consensus claims missing a `consensus_asof_date` that was never stated anywhere in the source material; eight blinding-gate hits from the original dossier's own verbatim reaction-language source title and narrative excerpts, migrated as-is rather than sanitized). Freeze mode fails with those same 10 findings plus the expected missing-`human_frozen`-row requirement. No immutable bundle or manifest was built, since there is no legitimate frozen label to bundle. `MSFT_MIGRATION_QC_REPORT.md` records the exact failing gates, a human-review-readiness assessment, and what a future prospectively-collected dossier must contain to pass — preserved as negative development evidence, per the protocol's own stated purpose for retaining this pilot.

### 3. End-to-end tests

`validator/test_event_dossier_e2e.py` (new, 26 assertions): a legitimate development-pilot freeze succeeding; a freeze blocked by inadequate (non-direct-fetch) sources; a freeze blocked by outcome-leakage (blinding breach); an amendment producing a new immutable bundle without modifying the prior one; a later, unrelated event's rows added to the same shared mutable working tables not invalidating an earlier event's frozen bundle; and the CI workflow itself statically verified to be scoped to the deterministic validator suite only, with no live market/GST/Wikipedia/SEC/news reference anywhere in it.

Only deterministic tests were run. No live research, no market-data joins, no Phase 2 panel execution, no GST/Wikipedia operation was performed from this worktree.

## 2026-08-03 — Validator SECOND correction pass

**Why this changed.** A follow-up review of the first hardening pass (commit `401c94c`) found six further gaps: an empty or under-populated fixture directory could pass simply because every gate's loop had nothing to iterate over; a header-only (0-row) CSV's own column header was never checked; surprise-percentage linkage didn't verify both claims were genuinely numeric, didn't require unit/GAAP basis on both sides (only checked mismatch when both happened to be present), didn't check consensus was nonzero, and had no way to confirm an EPS claim wasn't accidentally paired with a revenue claim; child-table evidence claims (capex effects, cross-company implications) and market-response addendum rows were never checked for event/layer consistency; freeze manifests hashed the fixture's own MUTABLE working tables directly, which are exactly what a later amendment or an unrelated event would go on to edit; and the freeze-manifest structural check was a hand-rolled, top-level-only required/additionalProperties comparison using string-prefix path containment, missing nested array-item violations and vulnerable to a sibling-directory or symlink path escape. This pass closes all six gaps, entirely within `Event_Dossier_Protocol/` — no change to the raw MSFT pilot dossier, PR #1/#2, the Wikipedia reliability worktree, or any operational artifact.

### 1. Required tables and validation modes

Added three validation modes (`draft`/`proposed`/`freeze`, `--mode` CLI flag, default `freeze`), each with an explicit required-table floor checked by a new `gate_required_tables` that runs first. `draft` requires only `events.csv`; `proposed` additionally requires `claims.csv`/`claim_sources.csv`/`management_qna.csv`/`event_labels.csv`; `freeze` requires the same as `proposed` plus at least one genuinely `human_frozen` `event_labels.csv` row. An empty fixture directory now fails in every mode. Every other gate still runs unconditionally regardless of mode.

### 2. Header-only CSV column validation

`load_fixture()` now captures each present table's actual CSV header line regardless of row count, and `gate_identity_and_schema` compares against it directly — a header-only (0-row) file with a missing/extra/misspelled column now fails, where the old `if rows:`-guarded check silently skipped it.

### 3. Surprise-linkage correctness and `metric_name`

Added `claims.metric_name` (`eps`/`revenue`/`guidance_revenue`/`cloud_growth`/`margin`/`capex`/`other`). `gate_surprise_linkage` now additionally requires: both linked claims `value_type=numeric` with a parseable `numeric_value`; both claims carry a non-blank, matching `unit` and `gaap_basis` (previously a blank on either side silently skipped the mismatch check instead of failing); both claims carry the SAME `metric_name` matching the field being computed (an EPS surprise must link `eps`↔`eps`, never `eps`↔`revenue`); and the consensus claim's `numeric_value` is nonzero (previously a zero consensus silently skipped recomputation with no failure raised).

Added `event_labels.eps_surprise_null_reason`/`revenue_surprise_null_reason` (`consensus_unavailable`/`consensus_unverifiable`/`not_applicable`). A blank surprise percentage now REQUIRES its matching null_reason to be set — an unexplained null fails — and a populated percentage cannot also carry a null_reason.

### 4. Child-table and market-response event/layer consistency

`event_label_capex_effects.evidence_claim_id` and `event_label_cross_company_implications.claim_id` must now belong to the SAME event as the label they support, must be `layer=A_blinded_core`, and must have an appropriate `claim_category`; a cross-company-implication claim must additionally carry a non-blank `metric_name`. `market_response_addendum.event_id` must match its `linked_label_id`'s own event, and every claim in `post_event_analyst_target_change_claim_ids` must belong to that same event and be `layer=B_market_response`.

### 5. Immutable freeze-bundle architecture

Freeze manifests now reference an immutable, per-label-version bundle under `frozen/{event_id}/{label_id}/`, containing seven artifact types exactly once — the four original Layer-A tables, the new singular `event_label.csv` (one frozen label-version row, distinct from the mutable working `event_labels.csv`), and the two child tables (header-only when empty). The manifest hashes these frozen copies, never the mutable working tables — editing the working table after freeze no longer invalidates the bundle, and a later amendment creates its own separate bundle without touching the prior label's. `FROZEN_BUNDLE_REQUIRED_BASENAMES` (7 items) replaces the old 4-item `REQUIRED_LAYER_A_ARTIFACT_BASENAMES` for this inventory check. The manifest's own filename is now also checked against `event_labels.csv`'s declared `freeze_manifest_path`.

### 6. Real JSON Schema validation and component-aware path containment

`gate_freeze_manifest`'s structural checks now run against the actual `freeze_manifest.schema.json` via the pinned `jsonschema` library (`validator/requirements.txt`, `jsonschema==4.26.0`) with `FormatChecker()` enabled, replacing the hand-rolled top-level-only required/additionalProperties comparison — this now recurses into nested array items (`reveal_events[]`, `reviewer_capture_exposure_log[]`), which the old check never inspected, and enforces `date-time` format (rejecting naive timestamps) at the schema level too. Path containment for every `artifact_path` now uses `Path.is_relative_to()` against the bundle's own resolved directory instead of `str.startswith()` — a sibling directory whose name is a string-prefix superset of the real bundle (e.g. `LBL-01_evil/` vs. `LBL-01/`), or a symlink planted inside the bundle that resolves outside it, is now correctly rejected; the old string-prefix check would have wrongly accepted the former.

### 7. Tests and fixtures

All 48 fixture outcomes from the first hardening pass preserved (rebuilt against the updated schema, validated under `mode=draft` — a strict subset of what was already implicitly enforced, since every other gate still runs in full). 18 new fixtures added (66 total) covering: empty directory, mode-specific missing required tables (`proposed` and `freeze`), malformed header-only CSV, unexplained vs. legitimate null surprise, nonnumeric linked claim, missing unit, missing GAAP basis, zero consensus, EPS-linked-to-revenue-claim, wrong-event and Layer-B child claims, a working file changed after freeze (still passes), a prior bundle valid after a later amendment (still passes), manifest filename/path disagreement, a sibling-directory path-escape, and a nested JSON Schema violation. Full suite: `python validator/test_validate_event_dossier.py` — 21 test methods, all passing.

Only deterministic validator tests were run. No live research, no market-data joins, no Phase 2 panel execution, no GST/Wikipedia operation was performed from this worktree.

## 2026-08-03 — Validator hardening pass (first pass)

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
