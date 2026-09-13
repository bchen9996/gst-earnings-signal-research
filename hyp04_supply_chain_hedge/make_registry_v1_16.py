#!/usr/bin/env python3
"""Generate hypothesis-registry v1.16 from v1.15. Registers HYP-06.

=== WHAT v1.16 SETTLES ===

One thing: a wholly NEW hypothesis entry, HYP-06, is ADDED to
`hypotheses`. HYP-04's and HYP-05's own entries are untouched -- every
field, byte-identical to v1.15. Mirrors exactly how v1.14 first added
HYP-05 without touching HYP-04.

=== WHY HYP-06 REGISTERS WITH ALL FOUR DECISIONS ALREADY RESOLVED ===

HYP-05 registered light (v1.14): no anchor/peer universe chosen, no
target/outcome definition, no threshold, no clustering choice -- all four
`PENDING_SEPARATE_ANALYSIS_LOCK`. HYP-06 is different: it reuses HYP-05's
OWN already-locked target/outcome definition and clustering choice
verbatim (not re-decided -- these are method choices, not universe-
contingent), and its anchor/peer universe is exactly the output of
`HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json`'s real, fail-closed
PS-1..PS-4 derivation, already committed before this registration. See
`HYP06_ScaledSupplyChainRelationshipLag_MODEL_PLAN_2026-09-13.md` for the
full reasoning. All four decisions are `RESOLVED`, not `PENDING`, and the
resolution is dated BEFORE this registry version and cites its source
artifact rather than restating a number that could drift from it.

=== HYP-04's AND HYP-05's ENTRIES MOVE NOTHING ===

`IMMOVABLE_ENTRY_FIELDS` is enforced, unweakened, against BOTH HYP-04's
AND HYP-05's entries (v1.15 already established the pattern of checking
it against more than one hypothesis's entry). `SPECIFICATION_FIELDS_
THIS_VERSION_MAY_MOVE` is empty, and the guard raises if that is not
literally true after the build. `results`/`results_note` are also
compared byte-identical.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_16 --write

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

from hyp04_supply_chain_hedge.make_hyp06_sample_size_gate import (
    UNIVERSE_ARTIFACT,
    naive_single_test_n,
    provisional_operative_floor,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (
    IMMOVABLE_HYP04_FIELDS as IMMOVABLE_ENTRY_FIELDS,
    LSE,
    RefusedError,
    _load,
    _sha256,
)

HYP04_ID = "HYP-04"
HYP05_ID = "HYP-05"
HYP06_ID = "HYP-06"

V1_15 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.15.json"
V1_16 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.16.json"

AUTHORED_AT = "2026-09-13"

#: The written basis. A new hypothesis with no dated plan behind it is
#: exactly what "registration is a governed act" forbids.
FINDINGS = (
    "Live Signal Engine/HYP06_ScaledSupplyChainRelationshipLag_MODEL_PLAN_"
    "2026-09-13.md",
    "Live Signal Engine/HYP06_SAMPLE_SIZE_GATE_2026-09-13.md",
    "Live Signal Engine/HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json",
)

#: HYP-04's and HYP-05's entries move nothing in v1.16 -- empty, enforced.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = ()


def check_preconditions(*, v1_15: Path = V1_15, v1_16: Path = V1_16,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_15.is_file():
        refusals.append(f"registry v1.15 not found at {v1_15.name}")
    if v1_16.exists():
        refusals.append(
            f"{v1_16.name} already exists. Refusing to overwrite a "
            "governance artifact -- delete it deliberately first if that "
            "is really intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. Registering a "
                "hypothesis with no written plan behind it is exactly what "
                "this project forbids.")
    doc = _load(v1_15) if v1_15.is_file() else {}
    if any(h.get("hypothesis_id") == HYP06_ID
           for h in doc.get("hypotheses", [])):
        refusals.append(f"{HYP06_ID} is already registered in {v1_15.name}")
    return refusals


def _hyp06_entry() -> dict[str, Any]:
    prov = provisional_operative_floor()
    naive = round(naive_single_test_n())
    universe = json.loads(UNIVERSE_ARTIFACT.read_text(encoding="utf-8"))
    n_qualifying = sum(1 for q in universe["qualifications"] if q["qualifies"])
    n_peer_tickers = len({q["ticker"] for q in universe["qualifications"]
                          if q["qualifies"]})
    return {
        "hypothesis_id": HYP06_ID,
        "title": "Scaled supply-chain relationship-lag among lower-coverage "
                 "peers",
        "question": (
            "The SAME question HYP-05 asked: does delayed earnings-"
            "information transmission appear specifically in clearly "
            "signed supplier/customer relationships among lower-coverage "
            "or less-liquid peers? HYP-05's own Phase 3 tested this on an "
            "8-event, 1-peer exploratory pilot and reported NOT_"
            "SIGNIFICANT (EXPLORATORY_PILOT_TESTED_NULL, holdout spent, "
            "never re-run). HYP-06 asks the identical question against a "
            "systematically-discovered universe two orders of magnitude "
            "larger -- see the model plan for why this is a fresh "
            "hypothesis with its own holdout, not a reopening of HYP-05's."),
        "classification": "preregistered_exploratory",
        "is_primary_confirmatory": False,
        "minimum_eligible_events": prov["operative_provisional_floor"],
        "minimum_eligible_events_unit": "eligible (peer, anchor_event) pairs",
        "minimum_eligible_events_basis": {
            "governance_character": (
                "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as "
                "every prior hypothesis's own floor -- NOT a claim of "
                "guaranteed statistical power and NOT an estimate of "
                "detectable effect size."),
            "provisional": True,
            "why_provisional": prov["why_still_provisional"],
            "must_be_superseded_by": prov["must_be_superseded_by"],
            "derivation_inputs": {
                "assumed_effect_size_cohens_d": 0.5,
                "assumed_effect_size_character": (
                    "hypothetical, externally chosen, NOT derived from any "
                    "observed project result -- same discipline as every "
                    "prior hypothesis's floor"),
                "alpha_family_wise": 0.05,
                "power": 0.8,
                "multiplicity_correction": (
                    "Sidak, formula reused UNCHANGED from HYP-05's own "
                    "gate. k is BORROWED from HYP-04's own measured range "
                    f"{prov['k_range_borrowed_from_hyp04_phase0']}, the "
                    "same provisional planning assumption HYP-05's own "
                    "registration used, reused here rather than re-derived "
                    "-- see must_be_superseded_by."),
                "naive_single_test_baseline": naive,
            },
            "why_this_does_not_violate_the_power_statement": (
                "The power_statement forbids a power calculation performed "
                "USING OBSERVED PROJECT RESULTS. Both k values entering "
                "this derivation are HYP-04's own Phase 0 SYNTHETIC-fixture "
                "measurement, not any observed result or real collected "
                "data of any kind."),
            "derivation_reference": (
                "Live Signal Engine/HYP06_SAMPLE_SIZE_GATE_2026-09-13.md"),
            "revisable": (
                "This floor may be revised only by a further dated "
                "registry version written BEFORE the results that would "
                "motivate the revision are seen -- the same discipline "
                "every prior hypothesis's floor is held to."),
        },
        "required_eligibility_class": "core_attention_vs_equity_response",
        "options_benchmark_required": False,
        "status": "PREREGISTERED_UNIVERSE_RESOLVED_NOT_LOCKED",
        "status_basis": (
            f"All four of HYP-05's own unresolved_analysis_decisions are "
            f"RESOLVED for HYP-06 (reused, not re-decided -- see "
            f"unresolved_analysis_decisions below), and a real, "
            f"fail-closed peer-universe derivation already exists on disk "
            f"({n_qualifying} qualifying (peer, event) pairs, "
            f"{n_peer_tickers} distinct peer tickers). No Phase 2 analysis "
            "lock has been signed and no computation of any kind has been "
            "performed against any pair in this universe. This status is "
            "deliberately new and distinct from HYP-05's own "
            "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED -- a reader must "
            "not mistake 'the universe is resolved' for 'a result exists' "
            "or 'a lock has been signed'."),
        "required_external_measurement": {
            "measurement": (
                "supply-chain customer/supplier linkage map, per anchor "
                "ticker, with a structured relationship direction and a "
                "point-in-time as_of_date"),
            "required_columns": [
                "anchor_ticker", "peer_ticker", "relationship_type",
                "as_of_date", "source",
            ],
            "availability": "exists",
            "availability_source": str(UNIVERSE_ARTIFACT).replace("\\", "/"),
            "as_of_date_requirement": (
                "Same discipline as HYP-04/HYP-05: enforced mechanically "
                "by peer_selection.py's PS-4 (as_of_date strictly precedes "
                "anchor_event_date), not merely required by policy."),
        },
        "forbidden_substitutions": [
            "sector membership as a stand-in for a supply-chain "
            "relationship",
            "return or volatility correlation as a stand-in for an "
            "established business relationship",
            "any linkage map lacking a first-known/established-as-of date, "
            "applied to historical events",
            "selecting the peer universe by which candidates already look "
            "promising in this or any other hypothesis's data -- moot for "
            "HYP-06 since the universe was fixed by the round-6 discovery "
            "run before any HYP-06 outcome existed to select on",
        ],
        "forbidden_substitution_rule": (
            "If the linkage for an anchor-peer pair is unavailable or "
            "undated, that pair does not count toward HYP-06."),
        "unresolved_analysis_decisions": [
            {"decision": "the liquidity/coverage cutoff for peer selection",
             "state": "RESOLVED",
             "resolution": "$2,000,000,000, reused verbatim from HYP-05's "
                           "own RATIFIED peer_selection.MARKET_CAP_"
                           "THRESHOLD_USD (2026-09-12), not re-chosen."},
            {"decision": "the target anchor/peer universe",
             "state": "RESOLVED",
             "resolution": f"Exactly the qualifying set in "
                           f"{str(UNIVERSE_ARTIFACT).replace(chr(92), '/')}"
                           f" -- {n_qualifying} (peer, event) pairs, "
                           f"{n_peer_tickers} distinct peer tickers, "
                           "derived by derive_peer_universe()'s real, "
                           "fail-closed PS-1..PS-4 run, not hand-selected."},
            {"decision": "the target/outcome definition",
             "state": "RESOLVED",
             "resolution": "target.py's residualized log realized-"
                           "variance ratio, reused verbatim from HYP-05's "
                           "own locked model_spec (target_py_sha256-pinned "
                           "in HYP05_PHASE2_LOCK_2026-09-12.json)."},
            {"decision": "clustering",
             "state": "RESOLVED",
             "resolution": "event_id primary (mirrors clustered_se.HYP05_"
                           "TWO_WAY_LIMITATION_NOTE), calendar_period as a "
                           "one-way robustness lens reported alongside it, "
                           "reused verbatim from HYP-05's own re-decision "
                           "away from HYP-04's D1-locked calendar_period-"
                           "only choice."},
        ],
        "options_tension_note": {
            "statement": "HYP-06 makes no options-related claim of any "
                         "kind at this stage.",
            "formal_options_eligibility": (
                "OUT OF SCOPE FOR THIS ENTRY."),
            "deferred_to": "not applicable unless a later stage introduces "
                           "one, which would need its own dated decision.",
            "why_recorded_now": "For the same reason every prior "
                                "hypothesis's entry records it: visible at "
                                "registration, not silently assumed.",
        },
        "display_rule": (
            f"No result, direction, effect estimate, plot, p-value or "
            f"confidence interval may be displayed before "
            f"{prov['operative_provisional_floor']} eligible pairs "
            "(PROVISIONAL floor -- see minimum_eligible_events_basis). No "
            "Phase 2 analysis lock exists yet, and no computation has been "
            "performed against this universe -- this registration alone "
            "licenses nothing beyond stating that the universe and method "
            "are both resolved. Reaching the floor licenses looking, not "
            "concluding, same as every prior hypothesis in this registry."),
    }


def build_v1_16(*, v1_15: Path = V1_15, authored_at: Optional[str] = None,
               ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_15))
    src = _load(v1_15)
    changes: list[str] = []

    doc["registry_version"] = "v1.16"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_15.name
    doc["supersedes_sha256"] = _sha256(v1_15)
    changes.append(f"registry_version: v1.15 -> v1.16 (supersedes {v1_15.name})")

    doc["hypotheses"].append(_hyp06_entry())
    changes.append(f"hypotheses: adds {HYP06_ID}")

    # --- HYP-04's and HYP-05's entries move nothing, guard unweakened -----
    if SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.16 registers a NEW hypothesis and must move nothing about "
            "HYP-04 or HYP-05; SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE "
            "must stay empty.")
    for hid in (HYP04_ID, HYP05_ID):
        old = next(h for h in src["hypotheses"] if h["hypothesis_id"] == hid)
        new = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)
        for f in IMMOVABLE_ENTRY_FIELDS:
            if new.get(f) != old.get(f):
                raise RefusedError(
                    f"{hid}.{f} changed. v1.16 registers HYP-06 and moves "
                    "NOTHING about HYP-04 or HYP-05.")
        if new != old:
            raise RefusedError(f"{hid}'s entry is not byte-identical to "
                               f"{v1_15.name}'s.")
        changes.append(f"guard: {hid}'s entire entry is byte-identical to "
                       f"{v1_15.name}")

    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.16 reports nothing new "
                           "about any prior hypothesis")
    if doc.get("results_note") != src.get("results_note"):
        raise RefusedError("results_note changed; v1.16 reports nothing "
                           "new about any prior hypothesis")
    changes.append("guard: results/results_note untouched")

    if doc.get("hypotheses_carried_forward_unchanged") != src.get(
            "hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged changed; "
                           "HYP-01/02/03 stay exactly as v1.0 defines them")
    changes.append("guard: hypotheses_carried_forward_unchanged untouched")

    doc.setdefault("findings_responded_to", {})["v1.16"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.16 from v1.15, "
                    "registering HYP-06.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.16 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print("  -", r)
        return 1

    doc, changes = build_v1_16(authored_at=a.authored_at)
    print("Changes:")
    for c in changes:
        print("  -", c)

    if not a.write:
        print("\nDRY RUN. Re-run with --write to create v1.16.")
        return 0

    if V1_16.exists():
        print(f"REFUSED -- {V1_16.name} already exists.")
        return 1
    V1_16.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\nWrote {V1_16}")
    print(f"  sha256 {_sha256(V1_16)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
