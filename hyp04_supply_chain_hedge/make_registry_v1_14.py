#!/usr/bin/env python3
"""Generate hypothesis-registry v1.14 from v1.13. Registers HYP-05.

=== WHAT v1.14 SETTLES ===

One thing: a wholly NEW hypothesis entry, HYP-05, is ADDED to `hypotheses`.
HYP-04's own entry is untouched -- every field, byte-identical to v1.13.
This mirrors exactly how HYP-04 itself was first added in v1.1: light
weight, no universe-shaped fields, `status:
PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`, because no curation exists yet.

=== WHY THE SAMPLE-SIZE FLOOR IS EXPLICITLY PROVISIONAL ===

HYP-04's own 193-event floor was already a REAL measurement by the time
v1.1 registered it (the Phase 0 diagnostic that produced it is dated
2026-08-18, the same day as v1.1 itself). HYP-05 has no design yet for a
max-T permutation run to measure -- see
`make_hyp05_sample_size_gate.py` and `HYP05_SAMPLE_SIZE_GATE_2026-09-11.md`.
So HYP-05 is registered slightly EARLIER in its own lifecycle than HYP-04's
v1.1 was: with a PROVISIONAL floor (195, borrowed from HYP-04's own measured
k range as a planning assumption only), explicitly labelled as such, and
revisable the same way every other floor in this registry already is --
"only by a further dated registry version written BEFORE the results that
would motivate the revision are seen."

=== HYP-04's ENTRY MOVES NOTHING ===

Unlike v1.13 (which closed HYP-04), v1.14 touches HYP-04 not at all.
`IMMOVABLE_HYP04_FIELDS` is enforced unweakened, with NO exception claimed
-- `SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` is empty, and the guard
raises if that is not literally true after the build. `results`/
`results_note` are also compared byte-identical, since this version reports
nothing new about HYP-04 either.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_14 --write

Named off the `test_*` pattern deliberately: this writes a governance
artifact and must only ever run when a human decides it should.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hyp04_supply_chain_hedge.make_hyp05_sample_size_gate import (
    naive_single_test_n,
    provisional_operative_floor,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (
    HYPOTHESIS_ID as HYP04_ID,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RefusedError,
    _load,
    _sha256,
)

HYP05_ID = "HYP-05"

V1_13 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.13.json"
V1_14 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.14.json"

AUTHORED_AT = "2026-09-11"

#: The written basis. A new hypothesis with no dated plan behind it is
#: exactly what "registration is a governed act" forbids.
FINDINGS = (
    "Live Signal Engine/HYP05_SupplyChainRelationshipLag_MODEL_PLAN_v0.1_"
    "DRAFT.md",
    "Live Signal Engine/HYP05_SAMPLE_SIZE_GATE_2026-09-11.md",
)

#: HYP-04's entry moves nothing in v1.14 -- empty, and the guard enforces it.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = ()


def check_preconditions(*, v1_13: Path = V1_13, v1_14: Path = V1_14,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_13.is_file():
        refusals.append(f"registry v1.13 not found at {v1_13.name}")
    if v1_14.exists():
        refusals.append(
            f"{v1_14.name} already exists. Refusing to overwrite a "
            "governance artifact -- delete it deliberately first if that "
            "is really intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. Registering a "
                "hypothesis with no written plan behind it is exactly what "
                "this project forbids.")
    doc = _load(v1_13) if v1_13.is_file() else {}
    if any(h.get("hypothesis_id") == HYP05_ID
           for h in doc.get("hypotheses", [])):
        refusals.append(f"{HYP05_ID} is already registered in {v1_13.name}")
    return refusals


def _hyp05_entry() -> dict[str, Any]:
    prov = provisional_operative_floor()
    naive = round(naive_single_test_n())
    return {
        "hypothesis_id": HYP05_ID,
        "title": "Supply-chain relationship-lag among lower-coverage peers",
        "question": (
            "Does delayed earnings-information transmission appear "
            "specifically in clearly signed supplier/customer/competitor "
            "relationships among lower-coverage or less-liquid peers? "
            "HYP-04 tested the large-cap, heavily-covered, single-"
            "relationship-type case and reported NOT_SIGNIFICANT; this asks "
            "whether the same mechanism is detectable where slow diffusion "
            "is a priori more plausible."),
        "classification": "preregistered_exploratory",
        "is_primary_confirmatory": False,
        "minimum_eligible_events": prov["operative_provisional_floor"],
        "minimum_eligible_events_unit": "eligible anchor events",
        "minimum_eligible_events_basis": {
            "governance_character": (
                "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as "
                "HYP-01/02/03's 60/60/40 and HYP-04's 193 -- NOT a claim of "
                "guaranteed statistical power and NOT an estimate of "
                "detectable effect size."),
            "provisional": True,
            "why_provisional": prov["why_borrowed_not_measured"],
            "must_be_superseded_by": prov["must_be_superseded_by"],
            "derivation_inputs": {
                "assumed_effect_size_cohens_d": 0.5,
                "assumed_effect_size_character": (
                    "hypothetical, externally chosen, NOT derived from any "
                    "observed project result -- same discipline as HYP-04's"),
                "alpha_family_wise": 0.05,
                "power": 0.8,
                "multiplicity_correction": (
                    "Sidak, formula verified against HYP-04's own published "
                    "table. k is BORROWED from HYP-04's own measured range "
                    f"{prov['k_range_borrowed_from_hyp04_phase0']} as a "
                    "planning assumption, not measured for HYP-05's own "
                    "(not-yet-fixed) design."),
                "naive_single_test_baseline": naive,
                "naive_single_test_baseline_note": (
                    "LABELLED BASELINE ONLY. Never the operative floor. "
                    "Not design-dependent -- this one number IS real today."),
            },
            "why_this_does_not_violate_the_power_statement": (
                "The power_statement forbids a power calculation performed "
                "USING OBSERVED PROJECT RESULTS. Both k values entering "
                "this derivation are HYP-04's own Phase 0 SYNTHETIC-fixture "
                "measurement, not any observed result or real collected "
                "data of any kind."),
            "derivation_reference": (
                "Live Signal Engine/HYP05_SAMPLE_SIZE_GATE_2026-09-11.md"),
            "revisable": (
                "This floor may be revised only by a further dated "
                "registry version written BEFORE the results that would "
                "motivate the revision are seen -- the same discipline "
                "HYP-04's own floor is held to."),
        },
        "required_eligibility_class": "core_attention_vs_equity_response",
        "required_eligibility_class_note": (
            "The ANCHOR-side requirement only, same class HYP-04 uses: an "
            "anchor event must itself be core-eligible for its earnings "
            "shock to be usable. No anchor ticker has been chosen for "
            "HYP-05, so this is a requirement on whatever gets chosen, not "
            "a statement that any candidate currently satisfies it."),
        "options_benchmark_required": False,
        "status": "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
        "status_basis": (
            "No anchor or peer ticker has been selected. No relationship "
            "has been curated -- the schema now supports real "
            "relationship-type variation and a structured "
            "concentration_pct field (this session's plumbing), and "
            "edgar_linkage.py gained an UNCALIBRATED competitor/supplier "
            "extractor, but nothing has been pointed at real filings. No "
            "ex-ante liquidity/coverage cutoff has been chosen. No capture "
            "path, production or otherwise, exists for any of this "
            "hypothesis's required measurements."),
        "required_external_measurement": {
            "measurement": (
                "supply-chain / competitor / customer linkage map, per "
                "anchor ticker, WITH a structured linkage-strength proxy "
                "and real relationship-type variation"),
            "required_columns": [
                "anchor_ticker",
                "peer_ticker",
                "relationship_type",
                "confidence",
                "first_known_or_established_as_of_date",
            ],
            "availability": "does_not_exist",
            "as_of_date_requirement": (
                "Same discipline as HYP-04: the first-known/established-"
                "as-of date per pair is REQUIRED, not optional, for the "
                "same look-ahead-bias reason."),
            "placeholder_used_in_phase_0": "none -- Phase 0 has not started",
            "placeholder_is_never_evidence": (
                "No result computed on any placeholder or provisional "
                "input is evidence about relationship-lag transmission, "
                "and none may be reported as such."),
        },
        "forbidden_substitutions": [
            "sector membership as a stand-in for a supply-chain "
            "relationship",
            "return or volatility correlation as a stand-in for an "
            "established business relationship, or as the linkage-strength "
            "proxy -- the proxy must be defined BEFORE any outcome is "
            "examined",
            "any linkage map lacking a first-known/established-as-of date, "
            "applied to historical events",
            "selecting the peer universe by which candidates already look "
            "promising in HYP-04's or any other hypothesis's data",
        ],
        "forbidden_substitution_rule": (
            "If the linkage for an anchor-peer pair is unavailable or "
            "undated, that pair does not count toward HYP-05. If a "
            "candidate peer's liquidity/coverage cutoff was chosen after "
            "looking at its returns, the cutoff is void and must be "
            "re-chosen blind."),
        "unresolved_analysis_decisions": [
            {"decision": "the exact liquidity/coverage percentile cutoff "
                         "for peer selection", "state": "PENDING_SEPARATE_ANALYSIS_LOCK"},
            {"decision": "the target anchor/peer universe",
             "state": "PENDING_SEPARATE_ANALYSIS_LOCK"},
            {"decision": "the target/outcome definition",
             "state": "PENDING_SEPARATE_ANALYSIS_LOCK"},
            {"decision": "two-way clustering (anchor event x calendar "
                         "period) -- re-decided on HYP-05's own terms, not "
                         "inherited from HYP-04's resolution",
             "state": "PENDING_SEPARATE_ANALYSIS_LOCK"},
        ],
        "options_tension_note": {
            "statement": "HYP-05 makes no options-related claim of any "
                         "kind at this stage.",
            "formal_options_eligibility": (
                "OUT OF SCOPE FOR THIS ENTRY. This registry version does "
                "NOT register HYP-05 against options_implied_move or "
                "joint_attention_plus_options."),
            "deferred_to": "not applicable unless a later stage introduces "
                           "one, which would need its own dated decision.",
            "why_recorded_now": "For the same reason HYP-04's entry records "
                                "it: visible at registration, not silently "
                                "assumed.",
        },
        "display_rule": (
            f"No result, direction, effect estimate, plot, p-value or "
            f"confidence interval may be displayed before "
            f"{prov['operative_provisional_floor']} eligible events "
            "(PROVISIONAL floor -- see minimum_eligible_events_basis). The "
            "hypothesis accrues no eligible events at all while its status "
            "is PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED. No result "
            "computed on any placeholder or provisional input may be "
            "displayed as a HYP-05 result under any circumstances, at any "
            "event count."),
    }


def build_v1_14(*, v1_13: Path = V1_13, authored_at: Optional[str] = None,
               ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_13))
    src = _load(v1_13)
    changes: list[str] = []

    doc["registry_version"] = "v1.14"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_13.name
    doc["supersedes_sha256"] = _sha256(v1_13)
    changes.append(f"registry_version: v1.13 -> v1.14 (supersedes {v1_13.name})")

    doc["hypotheses"].append(_hyp05_entry())
    changes.append(f"hypotheses: adds {HYP05_ID} (was just {HYP04_ID})")

    # --- HYP-04's entry moves nothing, and the guard is unweakened --------
    old_h4 = next(h for h in src["hypotheses"] if h["hypothesis_id"] == HYP04_ID)
    new_h4 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == HYP04_ID)
    if SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.14 registers a NEW hypothesis and must move nothing about "
            "HYP-04; SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE must stay "
            "empty.")
    for f in IMMOVABLE_HYP04_FIELDS:
        if new_h4.get(f) != old_h4.get(f):
            raise RefusedError(
                f"{HYP04_ID}.{f} changed. v1.14 registers HYP-05 and moves "
                "NOTHING about HYP-04.")
    if new_h4 != old_h4:
        raise RefusedError(
            f"{HYP04_ID}'s entry is not byte-identical to v1.13's.")
    changes.append(f"guard: {HYP04_ID}'s entire entry is byte-identical to v1.13")

    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.14 reports nothing new "
                           "about HYP-04")
    if doc.get("results_note") != src.get("results_note"):
        raise RefusedError("results_note changed; v1.14 reports nothing "
                           "new about HYP-04")
    changes.append("guard: results/results_note untouched")

    if doc.get("hypotheses_carried_forward_unchanged") != src.get(
            "hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged changed; "
                           "HYP-01/02/03 stay exactly as v1.0 defines them")
    changes.append("guard: hypotheses_carried_forward_unchanged untouched")

    doc.setdefault("findings_responded_to", {})["v1.14"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.14 from v1.13, "
                    "registering HYP-05.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.14 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes = build_v1_14(authored_at=a.authored_at)
    print("Changes v1.13 -> v1.14:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_14.name}.")
        return 0

    before = _sha256(V1_13)
    V1_14.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    if _sha256(V1_13) != before:
        raise RefusedError("v1.13 changed on disk during generation")

    print(f"\nWrote {V1_14.name}")
    print(f"v1.13 unchanged, sha256 {before[:16]}...")
    print("\nHYP-05 is now registered, PREREGISTERED_MEASUREMENT_NOT_"
          "IMPLEMENTED. No curation has happened. Nothing about HYP-04 or "
          "the gate moved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
