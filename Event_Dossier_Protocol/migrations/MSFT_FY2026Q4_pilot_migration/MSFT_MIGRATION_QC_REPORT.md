# MSFT FY2026 Q4 Pilot — Structured Migration QC Report

**Migration date:** 2026-08-03
**Source documents (unmodified, read-only):** `Live Signal Engine/Phase2_Event_Dossiers/MSFT_FY2026Q4_POST_EVENT_D2/{dossier.md,dossier_table.csv,dossier_table.json}`; `../../MSFT_PILOT_QC_AND_DISPOSITION.md`
**This directory:** a *separate* structured migration into the current `Event_Dossier_Protocol` schema (`events.csv`, `claims.csv`, `claim_sources.csv`, `management_qna.csv`, `event_labels.csv`, `event_label_capex_effects.csv`, `narrative_text.txt`). The original raw dossier files were not read programmatically and were not modified — every value below was transcribed by hand from those documents, cross-checked against them, and is preserved byte-for-byte in its original location (hashes below).

## 0. Permanent classification (unchanged from `MSFT_PILOT_QC_AND_DISPOSITION.md`)

```
event_disposition = development_pilot
blinding_compromised_for_confirmatory_use = true
```

MSFT FY2026 Q4 was researched before this protocol existed. **It can never become a confirmatory event, under any remediation, past or future.** This migration does not attempt to make it confirmatory — it exercises the current validator/protocol machinery against real, imperfect, pre-protocol data, which is exactly what a development-pilot artifact is for.

## 1. Raw dossier integrity (unchanged by this migration)

| File | SHA-256 |
|---|---|
| `dossier.md` | `30ec8a74d0af874e6b67233e9bb76e8f92ac254a0b18b0c6fda88246dd2bae5c` |
| `dossier_table.csv` | `ef49b9ca6480b2119a6a0cf70861038580754e3e03a8c16337cd3608626453b2` |
| `dossier_table.json` | `38ced6174d6142b8176c0c9b2a988927b29b4d8f79a3230c8ae78cbc603f6b81` |

Confirmed unchanged before and after this migration.

## 2. Draft-mode validation

```
python validate_event_dossier.py --mode draft Event_Dossier_Protocol/migrations/MSFT_FY2026Q4_pilot_migration
```

**Result: FAIL — 10 findings**, all genuine (none fabricated, none suppressed):

- `field_types` × 2: `claims.csv[...CLM-0002]` and `claims.csv[...CLM-0005]` — `claim_category=pre_event_consensus_estimate` requires a non-blank `consensus_asof_date`. **Neither the original dossier nor the QC document ever states an as-of date for either consensus figure** (`MSFT_PILOT_QC_AND_DISPOSITION.md` §4 lists this explicitly under "Unsupported / search-snippet-only"). No date was invented to make this pass.
- `blinding` × 6: `claim_sources.csv[...SRC-014/015/017/018/019/020/021].source_name` — every claim sourced to the Investing.com transcript carries its title *verbatim*, **"Microsoft Q4 2026 beats forecasts, stock jumps 8%"**, which contains market-reaction language. This is the exact same breach documented in `MSFT_PILOT_QC_AND_DISPOSITION.md` §3 (bullet 3), reproduced here as a structured field rather than sanitized or paraphrased.
- `blinding` × 2: `narrative_text.txt` — the two excerpts from the original dossier's Sections 11 and 13 (the "+8-9% after-hours magnitude" phrasing and the three-figure stock-reaction reconciliation), migrated verbatim into a Layer-A narrative field.

## 3. Proposed-mode validation

Same command with `--mode proposed`. **Result: FAIL — identical 10 findings.** Proposed mode's required-table floor (`events`, `claims`, `claim_sources`, `management_qna`, `event_labels`, all present) is satisfied; every finding above is a content-level failure, not a missing-table one.

## 4. Human-review readiness report

**Not ready for human review toward a freeze, for two independent, structural reasons — either alone is sufficient to block freeze regardless of the event's disposition:**

1. **Evidentiary gap on both surprise-linkage consensus claims.** `CLM-0002` (EPS consensus, $4.24 LSEG) and `CLM-0005` (revenue consensus, ~$87.61B LSEG) were never directly fetched (search-snippet/tier 4 sourcing only, per the original QC pass) and carry no as-of date. Per `EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md` §5 and the validator's `surprise_linkage` gate, a claim in this state cannot back ANY human-frozen surprise percentage, in any event's disposition — this is a sourcing-quality gate, not a disposition gate.
2. **A live, structural blinding breach in the migrated narrative and source-citation fields.** Layer A must never contain market-reaction language, full stop — `development_pilot`/`compromised` disposition does not exempt Layer A content from the blinding scan; the scan exists to keep the pipeline's OWN mechanical guarantees uniform across every event, not to police only events that might become confirmatory.

**Neither gap can be closed without either (a) re-sourcing the consensus figures against a genuinely direct-fetched provider+date — a new sourcing action this migration is not authorized to perform (no live research was run for this task), or (b) removing/rewriting the narrative and source-title content that constitutes the actual historical breach — which the task instructions explicitly forbid ("do not rewrite its history or pretend it was prospectively blinded").** Both gaps are therefore left exactly as they are, and the failure is reported honestly rather than engineered away.

A human reviewer COULD, in principle, still review and sign off on this label as an explicitly `ai_proposed`→`human_frozen` **development-pilot** artifact once (1) is resolved by a genuinely new, direct-fetch consensus re-sourcing pass and (2) the narrative/source-title breach content is moved out of any Layer-A field entirely (e.g., retained only in this QC report, never in `claims.csv`/`claim_sources.csv`/`narrative_text.txt`). Freezing is orthogonal to confirmatory eligibility — a `development_pilot` label can be legitimately frozen. But **that is future remediation work this migration does not perform**, and even if performed, it would freeze a `development_pilot` artifact, never converting this event to `confirmatory`.

## 5. Freeze-mode validation

Same command with `--mode freeze`. **Result: FAIL — 11 findings**: the same 10 content findings above, plus:

- `required_tables`: `mode='freeze' requires at least one event_labels.csv row with label_status=human_frozen (a complete, freeze-ready event) -- none found`.

This is correct and expected — no human reviewer has reviewed this migration, `frozen_by`/`frozen_at_utc`/`freeze_manifest_path` are all genuinely blank on the one `event_labels.csv` row, and `label_status=ai_proposed` throughout. No reviewer identity, decision, or timestamp was fabricated to manufacture a passing freeze.

## 6. Immutable freeze bundle / manifest validation

**Not attempted.** There is no legitimate frozen label to bundle — building a `frozen/{event_id}/{label_id}/` bundle and a `freeze_manifest.json` for a label that (a) is not `human_frozen` and (b) fails ten independent content gates would itself be a fabrication (a manifest asserting a freeze that never legitimately happened). Per the task instructions, the validator gates above are the authoritative record of why this event cannot reach freeze; no downstream artifact papers over that.

## 7. What a future, prospectively-collected MSFT (or any) dossier must contain to pass freeze-mode validation

Derived directly from the exact failing gates above, not from a general checklist:

1. **Every `pre_event_consensus_estimate` claim needs a real, named `consensus_provider` AND a real `consensus_asof_date`**, sourced to a genuinely direct-fetched (or otherwise Tier 0-3) document — not a search-engine-indexed summary of a page that returned HTTP 403 on direct fetch.
2. **No Layer-A field — `claim_text`, `claim_sources.source_name`/`notes`, `management_qna` fields, `event_labels` notes/management_tone/source_completeness, or `narrative_text.txt` — may ever contain market-reaction language**, including a source's own title if that title itself states a price-reaction figure; such a source must be cited by a paraphrased description instead (see `A_Blinded_Event_Core/README.md`'s own documented anti-pattern, motivated by this exact pilot).
3. **No stock-price, volume, options/IV, GST, or Wikipedia observation may be viewed, queried, or referenced at any point during Layer-A assembly** — the original pilot's own blinding notice already asserts this was honored structurally; the breach here is that the narrative nonetheless *recorded* reaction figures the assembler had apparently seen reported elsewhere, which is exactly why the protocol's Layer A/B separation (captured content is embargoed from the labeling process, not merely "not directly looked up") exists.
4. **A genuine human review and freeze act** — a real reviewer identity, a real timestamp, and a real `freeze_manifest.json` referencing a real, populated `frozen/{event_id}/{label_id}/` bundle — none of which this migration fabricates.

## 8. Summary

| Stage | Result |
|---|---|
| Draft validation | FAIL — 10 genuine findings |
| Proposed validation | FAIL — same 10 findings |
| Human-review readiness | NOT READY — two independent structural blockers, neither closable within this task's scope |
| Freeze-mode validation | FAIL — same 10 findings + missing human_frozen row |
| Immutable freeze bundle | Not attempted (no legitimate frozen label to bundle) |
| Manifest validation | Not applicable |
| Disposition | `development_pilot` / `blinding_compromised_for_confirmatory_use=true` — **permanent, one-directional** |

This migration is preserved as **negative development evidence**: a concrete, mechanically-verified demonstration that the current validator correctly rejects a real, pre-protocol dossier for the exact reasons that dossier is disqualified, without any gate having been weakened, bypassed, or worked around to force a pass.
