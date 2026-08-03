# Event Dossier Validator

`validate_event_dossier.py` is a deterministic, network-free checker for Event Dossier Protocol fixture directories. It implements the gates in `VALIDATION_CHECKLIST_v0.1_DRAFT.md` and the rules in `EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md`.

**2026-08-03 hardening pass**: this is a substantial rewrite over the original 5-gate version. Every documented required/conditional field, enum, numeric/integer/date/timestamp type is now mechanically enforced; foreign-key validation is complete (including a new `event_label_cross_company_implications.csv` child table and `corroborates_claim_source_id`); freeze-manifest validation is a full executable contract (artifact existence, path containment, exactly-once inventory, no Layer-B/C leakage, manifest/label cross-consistency); blinding-language scanning covers every Layer-A free-text field; reveal/freeze timestamp ordering is strict `>` with fail-closed handling of naive/mixed-timezone values; and EPS/revenue surprise percentages require explicit actual+consensus claim-ID linkage with independent recomputation. See `../CHANGELOG.md` for the full list.

## Usage

```
python validate_event_dossier.py <fixture_dir> [<fixture_dir> ...]
```

Exit code `0` if every supplied fixture directory passes; `1` if any has at least one `FAIL`-severity finding. Findings print as human-readable lines, one per violation, with the specific gate name, the offending row/field, and (for text leakage) the exact matched snippet — nothing is silently auto-corrected.

Run the test suite: `python test_validate_event_dossier.py`

## What it operates on

A **fixture directory** — never the real, operational artifacts. The validator:
- Reads only files inside the single directory passed to it, plus the protocol's own canonical schema files (`../A_Blinded_Event_Core/schemas/*.csv`, `../B_Market_Response_Addendum/schemas/*.csv`), `../schemas/freeze_manifest.schema.json`, and `../locked_universe_v0.1.json`.
- Makes no network calls.
- Never opens `Live Signal Engine/Phase2_Wikipedia_Cache.csv` or any other operational cache.
- Never imports or executes `GST_Phase2_DailyPanel.py` or any part of the Phase 2 panel.
- Never reads real Layer B/C feature data — the 48 required fixtures are small, synthetic, hand-built scenarios (see `fixtures/`), not real captured events.

`test_validate_event_dossier.py::test_validator_never_touches_network_or_operational_paths` statically greps the validator's own source for forbidden imports/references as a regression guard on this property.

## Recognized fixture files

A fixture directory may contain any subset of:
- `events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, `event_labels.csv`, `event_label_capex_effects.csv`, `event_label_cross_company_implications.csv`, `market_response_addendum.csv` — validated against the canonical schema headers when present; a missing file is treated as an empty table (0 rows), not an error, so each fixture can stay minimal and targeted at one gate.
- `freeze_manifest*.json` (one or more) — validated against `../schemas/freeze_manifest.schema.json`'s `required`/`additionalProperties: false` contract (checked by hand in Python, not via a `jsonschema` library dependency, to keep the validator dependency-free), plus artifact existence/path-containment/inventory/hash checks.
- `narrative_text.txt` — optional freeform prose, scanned by the blinding gate exactly like the other Layer-A text fields.
- `disposition_history.csv` (optional, not one of the eight normalized tables) — `event_id, event_disposition, recorded_at_utc, reason`, one row per historical disposition change. Used only to check the one-directional confirmatory→pilot/compromised rule; real production usage of this audit trail is a design decision the protocol has not yet formally adopted (see open items).

## Gates implemented

1. **Identity and schema** (`gate_identity_and_schema`): event ID format, ticker-in-locked-universe, exact schema column match, ID uniqueness per table, `fiscal_period` format.
2. **Field types** (`gate_field_types`, new): mechanically applies the declarative `FIELD_RULES` table — required/blank, enum membership, boolean parsing, date/timestamp parseability and timezone-awareness, numeric parsing, integer 1–5 score bounds — across every present table, plus the handful of conditional requirements that don't fit a pure per-field table (`value_type=numeric`→`numeric_value`, `pre_event_consensus_estimate`→provider/as-of/GAAP, `human_frozen`→frozen_by/frozen_at_utc/manifest path, amendment→reason, non-null surprise→claim linkage).
3. **Cross-row consistency** (`gate_cross_row_consistency`, new): `earnings_date` vs. the date portion of `event_datetime_utc`; `consensus_asof_date` strictly before `earnings_date`; `protocol_version` agreement across `events.csv`/`event_labels.csv`/freeze manifest.
4. **Source integrity** (`gate_source_integrity`): every material claim has a linked source; claims backing a `human_frozen` label need a `direct_fetch` Tier 0–3 source; `pre_event_consensus_estimate` claims must not blend multiple providers into one value.
5. **Surprise linkage** (`gate_surprise_linkage`, new): a non-null `eps_surprise_pct`/`revenue_surprise_pct` must link to the EXACT actual and consensus claim IDs it was computed from; validates category, unit compatibility, matching GAAP basis, direct-source/provider/as-of requirements for frozen labels, and independently recomputes the surprise percentage against `SURPRISE_PCT_TOLERANCE` (0.05 points).
6. **Blinding** (`gate_blinding`): regex-based scan, now covering every Layer-A free-text location (claims, Q&A including `classification_basis`, claim-source names/notes, label notes/management_tone/source_completeness/amendment_reason, capex-effect notes, cross-company-implication notes, narrative text) for market-reaction language (`REACTION_PATTERNS`) and forbidden Layer B/C feature terms (`FORBIDDEN_FEATURE_PATTERNS`).
7. **Foreign keys** (`gate_foreign_keys`, new/expanded): every FK across every table, including `corroborates_claim_source_id` (must exist, no self-reference, must belong to the same `claim_id`), `event_label_capex_effects`/`event_label_cross_company_implications` evidence claims, and claim/event consistency (a label's linked claim must belong to the label's own event).
8. **Label integrity** (`gate_label_integrity`): AI labels stay `ai_proposed`/`draft` (no `frozen_by`/`frozen_at_utc`); `human_frozen` labels need a real (non-`ai`) reviewer identity; the one-directional disposition rule is checked against `disposition_history.csv` when supplied.
9. **Freeze manifest** (`gate_freeze_manifest`, rewritten): treats `freeze_manifest.schema.json` as an executable contract — required/`additionalProperties` checks, artifact EXISTENCE (no longer skipped when the file is merely absent), path containment/no traversal, exactly-once required Layer-A inventory (`events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`), no Layer-B/C path leakage, hash match, and manifest↔`event_labels.csv` cross-consistency (`event_id`, `frozen_by`, freeze timestamp).
10. **Layer separation** (`gate_layer_separation`, corrected): every `reveal_events[].revealed_at_utc` must be STRICTLY greater than the label's `freeze_timestamp_utc` — an equal timestamp now fails as ambiguous; a `reviewer_capture_exposure_log` entry naming the same reviewer as `frozen_by`, timestamped AT OR BEFORE freeze, is disqualifying; naive/unparseable timestamps fail closed rather than raising a comparison exception.

## Required fixture cases (all 48 pass with the expected verdict)

See `fixtures/case_01_fully_valid/` through `fixtures/case_48_fixed_24_niche_value_accepted/` and `test_validate_event_dossier.py::CASES` for the authoritative list and one-line description of each. A few worth calling out specifically:

- **Case 17 vs. Case 18** is the core proof that leakage detection is context-aware rather than a blunt keyword filter: `"Azure and other cloud services revenue grew 43% year over year."` passes, while `"Microsoft shares rose 8% in after-hours trading."` fails — same sentence *shape*, different subject/verb pairing.
- **Case 19** proves the freeze-manifest hash check is real: a deliberately wrong SHA-256 for an artifact that genuinely exists is recomputed and flagged.
- **Case 31** proves artifact existence is now a hard requirement: a manifest referencing a file that was never written fails, where the pre-hardening validator silently skipped the check.
- **Case 32** proves path traversal is rejected even when the referenced hash is well-formed.
- **Case 38** proves the corrected strict-`>` timestamp rule: a reveal event timestamped EXACTLY equal to the freeze timestamp fails.
- **Case 40 vs. Case 41** is the core proof for surprise-linkage recomputation: identical claim data, but case 40's stored `eps_surprise_pct` disagrees with the recomputed value (fails) while case 41's agrees within tolerance on a fully-sourced, fully-frozen label (passes).
- **Case 47 vs. Case 48** proves the niche rename is enforced both ways: the superseded `large_cap_earnings` value fails, `fixed_24_ticker_earnings_panel` passes.

## Known false-positive / false-negative risks (documented, not resolved)

This validator is a **guardrail, not proof of perfect blinding** — it still requires human review. Specifically:

- **Regex-based leakage detection is inherently incomplete.** `REACTION_PATTERNS` and `FORBIDDEN_FEATURE_PATTERNS` are a curated but finite list. A sufficiently indirect or creatively worded reaction statement (e.g., "the market received the news enthusiastically" with no percentage or reaction verb from the list) would **false-negative**. Conversely, a legitimate operating statement using an unlucky verb could in principle **false-positive**; the current pattern list was checked against known cases and does not, but the risk class is not eliminated for all future phrasing.
- **The blended-provider detector is a regex heuristic** (`[,;/]| and | cluster| blended| mixed` in `consensus_provider`) — a genuinely single-provider name that happens to contain "and" would false-positive; an unanticipated blending phrase would false-negative.
- **Hash verification (and now existence checking) only covers artifacts referenced by `layer_a_artifact_hashes`.** A freeze process that simply omits an artifact from the manifest's inventory list entirely (rather than referencing a nonexistent one) is only caught by the exactly-once REQUIRED-basename check (item 13 of the checklist) — which covers the four core Layer-A tables by name, not an arbitrary additional artifact a real dossier might also want to hash.
- **The one-directional disposition check depends on an optional, not-yet-formally-adopted `disposition_history.csv` file.** Nothing in `events.csv` itself prevents a single row's `event_disposition` from being edited from `development_pilot` back to `confirmatory` in place — this protection is not yet mechanically enforced the same way frozen labels are.
- **Surprise-linkage unit compatibility is a string-equality check**, not a unit-conversion-aware one — `"USD_billions"` vs. `"USD billions"` (a formatting difference, not a real mismatch) would false-positive; this is an intentional simplicity trade-off, not an oversight, but worth knowing.

None of these gaps were hidden — they're the reason Section 18 of the protocol document states the validator "cannot verify that a human reviewer's judgment... was uninfluenced by something they read outside these files." Human review remains required regardless of validator pass/fail.

## Regenerating fixtures

The 48 fixture directories were built by a one-off generator script (not committed, per the task's scope — only the validator, its tests, this README, and the resulting fixture files are deliverables). If fixtures need to be regenerated after a schema change, rebuild them by hand or with an equivalent throwaway script that writes rows matching the current `../A_Blinded_Event_Core/schemas/*.csv` / `../B_Market_Response_Addendum/schemas/*.csv` headers exactly, and — since the 2026-08-03 hardening pass — ensure every fixture referencing a `freeze_manifest*.json` actually writes real `events.csv`/`claims.csv`/`claim_sources.csv`/`management_qna.csv` bytes matching the manifest's recorded hashes, since artifact existence is now a hard requirement, not a soft check. The validator's `identity_and_schema` gate rejects any fixture CSV whose columns don't exactly match its canonical schema file, by design, so schema drift is caught immediately rather than silently tolerated.
