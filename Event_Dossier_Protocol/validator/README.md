# Event Dossier Validator

`validate_event_dossier.py` is a deterministic, network-free checker for Event Dossier Protocol fixture directories. It implements the gates in `VALIDATION_CHECKLIST_v0.1_DRAFT.md` and the rules in `EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md`.

**2026-08-03 SECOND correction pass**: on top of the first hardening pass (niche rename, mechanical field/enum/type enforcement, complete FK validation, freeze-manifest hardening, expanded blinding scan, strict timestamp ordering, surprise-percentage linkage), this pass adds: validation **modes** (`draft`/`proposed`/`freeze`) with an explicit required-table floor per mode — an empty directory, or one missing whatever its mode structurally depends on, now fails instead of silently producing zero findings; header-only (0-row) CSVs are now column-checked, not skipped; `claims.metric_name` and mechanically-enforced surprise-linkage correctness (both claims genuinely numeric, unit AND gaap_basis present on both sides, consensus nonzero, metric_name matching eps↔eps/revenue↔revenue); explicit, enum-controlled null-surprise reasons (an unexplained blank surprise percentage now fails); child-table (capex-effects, cross-company-implications) evidence claims are checked for event/layer/category consistency, as are `market_response_addendum` rows against their linked label and Layer-B target-change claims; freeze manifests now reference an **immutable, per-label-version bundle** under `frozen/{event_id}/{label_id}/` instead of the mutable working tables, with component-aware (`Path.is_relative_to`) containment instead of string-prefix matching; and freeze-manifest structural validation now runs against the actual `freeze_manifest.schema.json` via the pinned `jsonschema` library (see `requirements.txt`), including nested array items that the old hand-rolled top-level-only check never inspected. See `../CHANGELOG.md` for the full list of both passes.

## Usage

```
pip install -r requirements.txt
python validate_event_dossier.py [--mode draft|proposed|freeze] <fixture_dir> [<fixture_dir> ...]
```

`--mode` defaults to `freeze` (the strictest mode). Exit code `0` if every supplied fixture directory passes; `1` if any has at least one `FAIL`-severity finding. Findings print as human-readable lines, one per violation, with the specific gate name, the offending row/field, and (for text leakage) the exact matched snippet — nothing is silently auto-corrected.

Run the test suite: `python test_validate_event_dossier.py`

## Validation modes

| Mode | Required tables | Additional requirement |
|---|---|---|
| `draft` | `events` | — |
| `proposed` | `events`, `claims`, `claim_sources`, `management_qna`, `event_labels` | — |
| `freeze` | same as `proposed` | at least one `event_labels.csv` row with `label_status=human_frozen` |

Every OTHER gate (field types, cross-row consistency, source integrity, surprise linkage, blinding, foreign keys, label integrity, freeze manifest, layer separation) runs **unconditionally regardless of mode** — mode only gates the required-table floor, never weakens any other check. This is why the 48 fixtures carried over from the first hardening pass validate cleanly under `mode=draft`: draft's minimal floor ("events" present) was already implicitly true for every one of those small, single-gate-scoped fixtures, and every other gate still runs in full against them.

An **empty fixture directory** fails in every mode, since even `draft` requires `events` to be present.

## What it operates on

A **fixture directory** — never the real, operational artifacts. The validator:
- Reads only files inside the single directory passed to it (including its own `frozen/` subdirectory, where present), plus the protocol's own canonical schema files (`../A_Blinded_Event_Core/schemas/*.csv`, `../B_Market_Response_Addendum/schemas/*.csv`), `../schemas/freeze_manifest.schema.json`, and `../locked_universe_v0.1.json`.
- Makes no network calls.
- Never opens `Live Signal Engine/Phase2_Wikipedia_Cache.csv` or any other operational cache.
- Never imports or executes `GST_Phase2_DailyPanel.py` or any part of the Phase 2 panel.
- Never reads real Layer B/C feature data — the 66 required fixtures are small, synthetic, hand-built scenarios (see `fixtures/`), not real captured events.

`test_validate_event_dossier.py::test_validator_never_touches_network_or_operational_paths` statically greps the validator's own source for forbidden imports/references as a regression guard on this property.

## Recognized fixture files

A fixture directory may contain any subset of:
- `events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, `event_labels.csv`, `event_label_capex_effects.csv`, `event_label_cross_company_implications.csv`, `market_response_addendum.csv` — validated against the canonical schema headers when present (including header-only, 0-row files); a missing file is treated as an empty table (0 rows), not an error (except where the active validation mode's required-table floor demands it), so each fixture can stay minimal and targeted at one gate.
- `freeze_manifest*.json` (one or more) — validated against `../schemas/freeze_manifest.schema.json`'s full JSON Schema (required/additionalProperties/enum/pattern/type, including nested array items) via the pinned `jsonschema` library, plus hand-written semantic checks (artifact existence/containment/inventory/hash/cross-consistency) that JSON Schema alone cannot express.
- `frozen/{event_id}/{label_id}/` — the immutable freeze bundle a `freeze_manifest*.json` for that `label_id` references. Contains exactly seven artifact files, each present exactly once: `events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, the singular `event_label.csv` (the ONE frozen label-version row — deliberately distinct from the plural, mutable working `event_labels.csv` at the fixture root), `event_label_capex_effects.csv`, `event_label_cross_company_implications.csv` (the last two present header-only when empty).
- `narrative_text.txt` — optional freeform prose, scanned by the blinding gate exactly like the other Layer-A text fields.
- `disposition_history.csv` (optional, not one of the eight normalized tables) — `event_id, event_disposition, recorded_at_utc, reason`, one row per historical disposition change. Used only to check the one-directional confirmatory→pilot/compromised rule; real production usage of this audit trail is a design decision the protocol has not yet formally adopted (see open items).

## Gates implemented

0. **Required tables / mode** (`gate_required_tables`, new): the mode-specific required-table floor (see table above), run first.
1. **Identity and schema** (`gate_identity_and_schema`): event ID format, ticker-in-locked-universe, exact schema column match (now checked from the actual CSV header even when the file has zero data rows), ID uniqueness per table, `fiscal_period` format.
2. **Field types** (`gate_field_types`): mechanically applies the declarative `FIELD_RULES` table — required/blank, enum membership (including `claims.metric_name`, `event_labels.eps_surprise_null_reason`/`revenue_surprise_null_reason`), boolean parsing, date/timestamp parseability and timezone-awareness, numeric parsing, integer 1–5 score bounds — across every present table, plus conditional requirements (`value_type=numeric`→`numeric_value`, `pre_event_consensus_estimate`→provider/as-of/GAAP, `human_frozen`→frozen_by/frozen_at_utc/manifest path, amendment→reason, non-null surprise→claim linkage, **null surprise→explicit null_reason, and a populated surprise cannot also carry a null_reason**).
3. **Cross-row consistency** (`gate_cross_row_consistency`): `earnings_date` vs. the date portion of `event_datetime_utc`; `consensus_asof_date` strictly before `earnings_date`; `protocol_version` agreement across `events.csv`/`event_labels.csv`/freeze manifest.
4. **Source integrity** (`gate_source_integrity`): every material claim has a linked source; claims backing a `human_frozen` label need a `direct_fetch` Tier 0–3 source; `pre_event_consensus_estimate` claims must not blend multiple providers into one value.
5. **Surprise linkage** (`gate_surprise_linkage`): a non-null `eps_surprise_pct`/`revenue_surprise_pct` must link to the EXACT actual and consensus claim IDs it was computed from; validates category, **value_type=numeric on both claims**, unit **presence AND** compatibility, GAAP-basis **presence AND** compatibility, **metric_name matching the field being computed (eps↔eps, revenue↔revenue)**, **consensus nonzero**, direct-source/provider/as-of requirements for frozen labels, and independently recomputes the surprise percentage against `SURPRISE_PCT_TOLERANCE` (0.05 points).
6. **Blinding** (`gate_blinding`): regex-based scan covering every Layer-A free-text location (claims, Q&A including `classification_basis`, claim-source names/notes, label notes/management_tone/source_completeness/amendment_reason, capex-effect notes, cross-company-implication notes, narrative text) for market-reaction language (`REACTION_PATTERNS`) and forbidden Layer B/C feature terms (`FORBIDDEN_FEATURE_PATTERNS`).
7. **Foreign keys** (`gate_foreign_keys`): every FK across every table, including `corroborates_claim_source_id`, claim/event consistency for `event_labels.csv`'s own linked-claim fields, **child-table evidence-claim event/layer/category consistency** (`event_label_capex_effects.evidence_claim_id` and `event_label_cross_company_implications.claim_id` must belong to the SAME event as their label, must be `layer=A_blinded_core`, and must have an appropriate `claim_category`), and **market-response addendum event consistency** (`market_response_addendum.event_id` must match its `linked_label_id`'s own event; every `post_event_analyst_target_change_claim_ids` entry must belong to that same event and be `layer=B_market_response`).
8. **Label integrity** (`gate_label_integrity`): AI labels stay `ai_proposed`/`draft` (no `frozen_by`/`frozen_at_utc`); `human_frozen` labels need a real (non-`ai`) reviewer identity; the one-directional disposition rule is checked against `disposition_history.csv` when supplied.
9. **Freeze manifest / immutable bundle** (`gate_freeze_manifest`, second-pass rewrite): structural validation (required/additionalProperties/enum/pattern/type, **including nested array items** like `reveal_events[]`/`reviewer_capture_exposure_log[]`) now runs against the real `freeze_manifest.schema.json` via `jsonschema.Draft7Validator` with `FormatChecker()` (catches naive `date-time` values too). Semantic checks (hand-written, since JSON Schema can't do file I/O or cross-file consistency): every referenced artifact must exist and resolve, via `Path.is_relative_to()` (never a string-prefix comparison), **inside this label's own `frozen/{event_id}/{label_id}/` bundle directory** — `.resolve()` follows symlinks first, so a symlink planted inside the bundle pointing outside it is caught by the same check; no path traversal; all seven `FROZEN_BUNDLE_REQUIRED_BASENAMES` present exactly once; no Layer-B/C path leakage; hash match against the frozen copies (never the mutable working tables); the manifest's own **filename must match** `event_labels.csv`'s declared `freeze_manifest_path`; and manifest↔`event_labels.csv` cross-consistency (`event_id`, `frozen_by`, freeze timestamp).
10. **Layer separation** (`gate_layer_separation`): every `reveal_events[].revealed_at_utc` must be STRICTLY greater than the label's `freeze_timestamp_utc` — an equal timestamp fails as ambiguous; a `reviewer_capture_exposure_log` entry naming the same reviewer as `frozen_by`, timestamped AT OR BEFORE freeze, is disqualifying; naive/unparseable timestamps fail closed rather than raising a comparison exception.

## Required fixture cases (all 66 pass with the expected verdict)

See `fixtures/case_01_fully_valid/` through `fixtures/case_66_nested_json_schema_violation/` and `test_validate_event_dossier.py::CASES` for the authoritative list, mode, and one-line description of each. A few worth calling out specifically:

- **Case 17 vs. Case 18** proves leakage detection is context-aware: `"Azure and other cloud services revenue grew 43% year over year."` passes, `"Microsoft shares rose 8% in after-hours trading."` fails.
- **Case 19** proves the frozen-bundle hash check is real: a deliberately wrong SHA-256 for a bundle artifact that genuinely exists is recomputed and flagged.
- **Case 31** proves artifact existence is a hard requirement inside the bundle.
- **Case 32 / 65** prove path-escape rejection: `32` via `..` traversal, `65` via a sibling directory (`LBL-01_evil/`) whose NAME is a string-prefix superset of the real bundle directory — `Path.is_relative_to()` correctly rejects it where a naive `str.startswith()` containment check would have wrongly accepted it (the same defense also covers a symlink planted inside the bundle that resolves outside it).
- **Case 38** proves the strict-`>` timestamp rule: a reveal event timestamped EXACTLY equal to the freeze timestamp fails.
- **Case 40 vs. 41** is the core proof for surprise-linkage recomputation: identical claim data, but 40's stored value disagrees with the recomputed value (fails) while 41's agrees within tolerance on a fully-sourced, fully-frozen label (passes, `mode=freeze`).
- **Case 47 vs. 48** proves the niche rename is enforced both ways.
- **Case 49** proves an empty directory fails in every mode.
- **Case 50 / 52** prove mode-specific required-table enforcement: `50` under `mode=proposed` (missing `claim_sources.csv`), `52` under `mode=freeze` (missing `management_qna.csv` AND no `human_frozen` row — either alone would fail).
- **Case 51** proves header-only (0-row) CSVs are column-checked: `claims.csv` has zero data rows, but its header is missing `metric_name`.
- **Case 53 vs. 54** is the core proof for explicit null-surprise reasons: an unexplained blank `eps_surprise_pct` fails; the same blank with `eps_surprise_null_reason=consensus_unverifiable` passes.
- **Case 55–58** prove each surprise-linkage correctness rule individually: non-numeric linked claim, missing unit, missing GAAP basis, zero consensus.
- **Case 59** proves metric-name matching: `eps_actual_claim_id` pointed at a claim with `metric_name=revenue` fails.
- **Case 60 / 61** prove child-table event/layer consistency: a capex-effect evidence claim from a different event, and a cross-company-implication claim tagged Layer B.
- **Case 62** is the core proof of the immutable-bundle design: the WORKING `events.csv` is edited after the frozen bundle snapshot is taken, and the fixture still PASSES (`mode=freeze`) because the manifest hashes the frozen copy, never the mutable working table.
- **Case 63** proves a prior frozen bundle remains independently valid after a later amendment creates its own separate bundle.
- **Case 64** proves manifest filename/path agreement is checked.
- **Case 66** proves nested JSON Schema validation: `reveal_events[0]` missing its required `revealed_by` field is only caught because validation now recurses into array items, unlike the old top-level-only hand-rolled check.

## Known false-positive / false-negative risks (documented, not resolved)

This validator is a **guardrail, not proof of perfect blinding** — it still requires human review. Specifically:

- **Regex-based leakage detection is inherently incomplete.** `REACTION_PATTERNS` and `FORBIDDEN_FEATURE_PATTERNS` are a curated but finite list. A sufficiently indirect or creatively worded reaction statement would **false-negative**; an unlucky legitimate operating-metric phrasing could in principle **false-positive** (not observed in the current fixture set, but the risk class isn't eliminated).
- **The blended-provider detector is a regex heuristic** — a genuinely single-provider name containing "and" would false-positive; an unanticipated blending phrase would false-negative.
- **`corroborates_claim_source_id` and child-table claim-category checks assume good-faith metadata.** A claim mislabeled with the wrong `claim_category`/`layer`/`metric_name` on entry (rather than at the point a child row references it) is caught by the FK/consistency checks described above, but the validator cannot detect a claim whose OWN category/layer/metric tag was simply chosen incorrectly with no other row to cross-check it against.
- **The one-directional disposition check depends on an optional, not-yet-formally-adopted `disposition_history.csv` file.**
- **Surprise-linkage unit compatibility is a string-equality check**, not a unit-conversion-aware one — `"USD_billions"` vs. `"USD billions"` would false-positive; an intentional simplicity trade-off.
- **`jsonschema`'s `FormatChecker` handles `date-time` format checking**, but "format" assertions are, per the JSON Schema spec itself, annotations rather than hard assertions in every draft/implementation combination; this validator explicitly enables `FormatChecker()` so `date-time` IS enforced here, but this is a validator-side choice layered on top of the schema, not an inherent guarantee of `additionalProperties`-style structural checks.

None of these gaps were hidden — they're the reason Section 18 of the protocol document states the validator "cannot verify that a human reviewer's judgment... was uninfluenced by something they read outside these files." Human review remains required regardless of validator pass/fail.

## Regenerating fixtures

The 66 fixture directories were built by a one-off generator script (not committed, per the task's scope — only the validator, its tests, this README, `requirements.txt`, and the resulting fixture files are deliverables). If fixtures need to be regenerated after a schema change, rebuild them by hand or with an equivalent throwaway script that writes rows matching the current `../A_Blinded_Event_Core/schemas/*.csv` / `../B_Market_Response_Addendum/schemas/*.csv` headers exactly, and — since the freeze-bundle architecture change — ensure every fixture referencing a `freeze_manifest*.json` actually writes a real seven-artifact bundle under `frozen/{event_id}/{label_id}/` with the manifest's hashes computed against THOSE files, never the fixture-root working tables. The validator's `identity_and_schema` gate rejects any fixture CSV whose columns don't exactly match its canonical schema file — including header-only files — by design, so schema drift is caught immediately rather than silently tolerated.
