# Event Dossier Validator

`validate_event_dossier.py` is a deterministic, network-free checker for Event Dossier Protocol fixture directories. It implements the gates in `VALIDATION_CHECKLIST_v0.1_DRAFT.md` and the rules in `EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md`.

## Usage

```
python validate_event_dossier.py <fixture_dir> [<fixture_dir> ...]
```

Exit code `0` if every supplied fixture directory passes; `1` if any has at least one `FAIL`-severity finding. Findings print as human-readable lines, one per violation, with the specific gate name, the offending row/field, and (for text leakage) the exact matched snippet — nothing is silently auto-corrected.

Run the test suite: `python test_validate_event_dossier.py`

## What it operates on

A **fixture directory** — never the real, operational artifacts. The validator:
- Reads only files inside the single directory passed to it, plus the protocol's own canonical schema files (`../A_Blinded_Event_Core/schemas/*.csv`, `../B_Market_Response_Addendum/schemas/*.csv`) and `../locked_universe_v0.1.json`, to know the expected columns and the confirmatory ticker universe.
- Makes no network calls.
- Never opens `Live Signal Engine/Phase2_Wikipedia_Cache.csv` or any other operational cache.
- Never imports or executes `GST_Phase2_DailyPanel.py` or any part of the Phase 2 panel.
- Never reads real Layer B/C feature data — the 20 required fixtures are small, synthetic, hand-built scenarios (see `fixtures/`), not real captured events.

`test_validate_event_dossier.py::test_validator_never_touches_network_or_operational_paths` statically greps the validator's own source for forbidden imports/references as a regression guard on this property.

## Recognized fixture files

A fixture directory may contain any subset of:
- `events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, `event_labels.csv`, `event_label_capex_effects.csv`, `market_response_addendum.csv` — validated against the canonical schema headers when present; a missing file is treated as an empty table (0 rows), not an error, so each fixture can stay minimal and targeted at one gate.
- `freeze_manifest*.json` (one or more) — validated against the shape described in `../schemas/freeze_manifest.schema.json` (checked by hand in Python, not via a `jsonschema` library dependency, to keep the validator dependency-free).
- `narrative_text.txt` — optional freeform prose, scanned by the blinding gate exactly like `claim_text`/`response_text`/`source_name` fields. Useful for testing dossier-style narrative content directly, as opposed to only structured claim rows.
- `disposition_history.csv` (optional, not one of the six normalized tables) — `event_id, event_disposition, recorded_at_utc, reason`, one row per historical disposition change. Used only to check the one-directional confirmatory→pilot/compromised rule (fixture case 13); real production usage of this audit trail is a design decision the protocol has not yet formally adopted (see open items).

## Gates implemented

1. **Identity and schema** (`gate_identity_and_schema`): event ID format, ticker-in-locked-universe, allowed capture horizons (`POST_EVENT_D1`/`POST_EVENT_D5`, plus the documented `POST_EVENT_D2` pilot exception), exact schema column match, ID uniqueness per table, all foreign keys, fiscal-period format.
2. **Source integrity** (`gate_source_integrity`): every material claim has a linked source; claims backing a `human_frozen` label need a `direct_fetch` Tier 0–3 source; `pre_event_consensus_estimate` claims need provider + as-of date + GAAP basis and must not blend multiple providers into one value; a non-null surprise percentage requires a valid consensus claim for the same event.
3. **Blinding** (`gate_blinding`): regex-based scan of `claim_text`, `question_text`/`response_text`, `source_name` (for sources linked to Layer-A claims), and optional `narrative_text.txt`, for market-reaction language (`REACTION_PATTERNS`) and forbidden Layer B/C feature terms (`FORBIDDEN_FEATURE_PATTERNS`), scoped to `layer = A_blinded_core` content.
4. **Label integrity** (`gate_label_integrity`): AI labels stay `ai_proposed`/`draft` (no `frozen_by`/`frozen_at_utc`); `human_frozen` labels need a real reviewer identity, a parseable freeze timestamp, and a matching `freeze_manifest.json` with well-formed artifact hashes — **and, when the hashed artifact file is actually present in the fixture, the validator recomputes its SHA-256 and compares it to the recorded value**, catching post-freeze tampering; amendments require a reason; the one-directional disposition rule is checked against `disposition_history.csv` when supplied.
5. **Layer separation** (`gate_layer_separation`): every `reveal_events[].revealed_at_utc` in a freeze manifest must be ≥ that label's `freeze_timestamp_utc`; a `reviewer_capture_exposure_log` entry naming the same reviewer as `frozen_by`, timestamped before freeze, is a disqualifying finding; `market_response_addendum.csv` rows may exist regardless of freeze state (capture ≠ reveal) but must reference a real label if one is provided.

## Required fixture cases (all 20 pass with the expected verdict)

See `fixtures/case_01_fully_valid/` through `fixtures/case_20_consensus_unavailable_null_surprise/` and `test_validate_event_dossier.py::CASES` for the authoritative list and one-line description of each. Two are worth calling out specifically:

- **Case 17 vs. Case 18** is the core proof that leakage detection is context-aware rather than a blunt keyword filter: `"Azure and other cloud services revenue grew 43% year over year."` passes (an operating-metric statement), while `"Microsoft shares rose 8% in after-hours trading."` fails (a reaction statement) — same sentence *shape*, different subject/verb pairing.
- **Case 19** proves the freeze-manifest hash check is real, not cosmetic: the manifest records a deliberately wrong SHA-256 for `events.csv` (an artifact that genuinely exists in that fixture), and the validator recomputes the actual hash and flags the mismatch.

## Known false-positive / false-negative risks (documented, not resolved)

This validator is a **guardrail, not proof of perfect blinding** — it still requires human review. Specifically:

- **Regex-based leakage detection is inherently incomplete.** `REACTION_PATTERNS` and `FORBIDDEN_FEATURE_PATTERNS` are a curated but finite list. A sufficiently indirect or creatively worded reaction statement (e.g., "the market received the news enthusiastically" with no percentage or reaction verb from the list) would **false-negative** — pass when it shouldn't. Conversely, a legitimate operating statement using an unlucky verb (e.g., a hypothetical "shares outstanding rose 2% due to a buyback pause") could **false-positive** on the `shares...rose` pattern; the current pattern list was checked against this specific case and does not match it (subject-verb-object shape differs enough), but the risk class is real and not eliminated for all future phrasing.
- **Surprise-percentage-to-consensus linkage is metric-blind.** `gate_source_integrity`'s check that a non-null `eps_surprise_pct`/`revenue_surprise_pct` has a backing consensus claim does not verify that the consensus claim is actually an *EPS* (vs. revenue, vs. some other metric) estimate — any valid `pre_event_consensus_estimate` claim for the event currently "covers" both fields. A more precise implementation would tag claims with the specific metric they estimate and require an exact match.
- **The blended-provider detector is a regex heuristic** (`[,;/]| and | cluster| blended| mixed` in `consensus_provider`) — a genuinely single-provider name that happens to contain "and" (e.g., a fictitious firm literally named "Smith and Jones Research") would false-positive; a blended value using unanticipated phrasing (e.g., "multi-source estimate") would false-negative.
- **Hash verification only checks artifacts that exist in the fixture directory at the recorded `artifact_path`.** If a manifest references an artifact that was never captured into the fixture (or, in production, was moved/renamed without updating the manifest), the check silently passes on format alone. This mirrors a real operational risk: the manifest's hash list is only as trustworthy as the freeze process's discipline in recording *every* artifact that actually fed the label.
- **The one-directional disposition check depends on an optional, not-yet-formally-adopted `disposition_history.csv` file.** Nothing in `events.csv` itself prevents a single row's `event_disposition` from being edited from `development_pilot` back to `confirmatory` in place — the protection currently depends on treating `events.csv` as append-only/versioned in the same way `event_labels.csv` is, which is asserted in the protocol document but not yet mechanically enforced the same way frozen labels are.

None of these gaps were hidden — they're the reason Section 18 of the protocol document states the validator "cannot verify that a human reviewer's judgment... was uninfluenced by something they read outside these files." Human review remains required regardless of validator pass/fail.

## Regenerating fixtures

The 20 fixture directories were built by a one-off generator script (not committed, per the task's scope — only the validator, its tests, this README, and the resulting fixture files are deliverables). If fixtures need to be regenerated after a schema change, rebuild them by hand or with an equivalent throwaway script that writes rows matching the current `../A_Blinded_Event_Core/schemas/*.csv` / `../B_Market_Response_Addendum/schemas/*.csv` headers exactly — the validator's `identity_and_schema` gate rejects any fixture CSV whose columns don't exactly match its canonical schema file, by design, so drift is caught immediately rather than silently tolerated.
