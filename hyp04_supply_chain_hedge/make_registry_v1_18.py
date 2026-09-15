#!/usr/bin/env python3
"""Generate hypothesis-registry v1.18 from v1.17. Registers HYP-08.

=== WHAT v1.18 SETTLES ===

One thing: a wholly NEW hypothesis entry, HYP-08, is ADDED to
`hypotheses`. HYP-04's, HYP-05's, HYP-06's, and HYP-07's own entries are
untouched -- every field, byte-identical to v1.17. Mirrors exactly how
v1.17 first added HYP-07 without touching HYP-04, HYP-05, or HYP-06.

=== WHY HYP-08 IS NOT THE SAME PATTERN AS HYP-06's OR HYP-07's REGISTRATION ===

HYP-06 reused HYP-05's own already-locked target/outcome definition
verbatim. HYP-07 built a genuinely new signed target but kept the same
delayed 1-20 day HORIZON_GRID structure every prior hypothesis used.
HYP-08 is the first hypothesis in this project with NO horizon grid at
all -- its target (`target_same_session.py`) is a single same-session
value, and its statistical design is two preregistered tests (a plain
pooled coefficient and a shock:is_competitor heterogeneity interaction),
Sidak-corrected over an EXACT k=2, not a max-T permutation over a
20-horizon search. It is also the first hypothesis whose peer universe is
not newly discovered at all -- it pools two ALREADY-SIGNED prior locks
(HYP-06's 778 customer/supplier pairs, HYP-07's 195 competitor pairs)
rather than deriving a fresh universe from a raw discovery artifact. See
`HYP08_SameSessionReactionHeterogeneity_MODEL_PLAN_2026-09-14.md` for the
full reasoning.

All four decisions a fresh hypothesis owes are RESOLVED, not PENDING --
"RESOLVED" here means "decided, written, and offline-tested before any
outcome value was computed for any real HYP-08 pair," NOT "Phase-2-locked."
No Phase 2 lock has been signed for HYP-08 as of this registration.

=== THE SAMPLE-SIZE FLOOR IS EXACT, NOT PROVISIONAL, AND CLEARED COMFORTABLY ===

Unlike HYP-05/06/07 (which all borrow HYP-04's own measured k range,
6.05-6.34, itself measured against a 20-horizon max-T design), HYP-08's
family size (k=2) is fixed by its own design -- there is no horizon grid
whose correlation structure needs measuring. The floor is therefore
EXACT (152 pairs), not provisional, and the real pooled universe (973
pairs) clears it by 6.4x -- see
`HYP08_SAMPLE_SIZE_GATE_2026-09-14.md`.

=== HYP-04's, HYP-05's, HYP-06's, AND HYP-07's ENTRIES MOVE NOTHING ===

`IMMOVABLE_ENTRY_FIELDS` is enforced, unweakened, against all four prior
entries. `SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` is empty, and the
guard raises if that is not literally true after the build. `results`/
`results_note` are also compared byte-identical.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_18 --write

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

from hyp04_supply_chain_hedge.make_hyp08_phase2_lock import (
    ANCHOR_SHOCKS_CSVS,
    HYP06_PHASE2_LOCK_JSON,
    HYP07_PHASE2_LOCK_JSON,
    _locked_events,
)
from hyp04_supply_chain_hedge.make_hyp08_sample_size_gate import (
    ALPHA_FAMILY_WISE,
    ASSUMED_EFFECT_SIZE_COHENS_D,
    FAMILY_SIZE_K,
    POWER,
    naive_single_test_n,
    operative_floor,
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
HYP07_ID = "HYP-07"
HYP08_ID = "HYP-08"

V1_17 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.17.json"
V1_18 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.18.json"

AUTHORED_AT = "2026-09-14"

FINDINGS = (
    "Live Signal Engine/HYP08_SameSessionReactionHeterogeneity_"
    "MODEL_PLAN_2026-09-14.md",
    "Live Signal Engine/HYP08_SAMPLE_SIZE_GATE_2026-09-14.md",
)

#: HYP-04's, HYP-05's, HYP-06's, and HYP-07's entries move nothing in
#: v1.18 -- empty, enforced.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = ()


def check_preconditions(*, v1_17: Path = V1_17, v1_18: Path = V1_18,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_17.is_file():
        refusals.append(f"registry v1.17 not found at {v1_17.name}")
    if v1_18.exists():
        refusals.append(
            f"{v1_18.name} already exists. Refusing to overwrite a "
            "governance artifact -- delete it deliberately first if that "
            "is really intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. Registering a "
                "hypothesis with no written plan behind it is exactly what "
                "this project forbids.")
    for label, p in (("HYP-06 Phase 2 lock", HYP06_PHASE2_LOCK_JSON),
                     ("HYP-07 Phase 2 lock", HYP07_PHASE2_LOCK_JSON),
                     *[(f"anchor shocks ({p.name})", p) for p in ANCHOR_SHOCKS_CSVS]):
        if not p.is_file():
            refusals.append(f"no {label} at {p} -- HYP-08's pooled universe "
                            "cannot be derived without it")
    doc = _load(v1_17) if v1_17.is_file() else {}
    if any(h.get("hypothesis_id") == HYP08_ID
           for h in doc.get("hypotheses", [])):
        refusals.append(f"{HYP08_ID} is already registered in {v1_17.name}")
    return refusals


def _hyp08_entry() -> dict[str, Any]:
    floor = operative_floor()
    naive = round(naive_single_test_n())
    events = _locked_events(HYP06_PHASE2_LOCK_JSON, HYP07_PHASE2_LOCK_JSON,
                            ANCHOR_SHOCKS_CSVS)
    n_pooled = len(events)
    n_cs = sum(1 for e in events if e["source_hypothesis"] == "HYP-06")
    n_comp = sum(1 for e in events if e["source_hypothesis"] == "HYP-07")
    n_peer_tickers = len({e["peer_ticker"] for e in events})
    n_anchor_tickers = len({e["anchor_ticker"] for e in events})
    return {
        "hypothesis_id": HYP08_ID,
        "title": "Same-session peer reaction and reaction heterogeneity "
                 "to anchor earnings surprises",
        "question": (
            "Does EDGAR-identified economic exposure predict a same-"
            "session peer reaction to an anchor's earnings surprise, and "
            "does that reaction differ between customer/supplier and "
            "competitor relationships? Tested here for the first time in "
            "this project via a no-horizon-grid same-session target "
            "(target_same_session.py) against a POOLED, already-"
            "discovered universe -- HYP-06's own 778 customer/supplier "
            "pairs plus HYP-07's own 195 competitor pairs, both already "
            "EDGAR-verified and reused, not re-discovered. Genuinely "
            "distinct from HYP-04/05/06/07: no delayed-horizon grid of "
            "any kind, and the first hypothesis in this project to test "
            "reaction heterogeneity BETWEEN relationship types directly, "
            "via a single interaction coefficient, rather than testing "
            "each type in isolation."),
        "classification": "preregistered_exploratory",
        "is_primary_confirmatory": False,
        "minimum_eligible_events": floor["operative_floor"],
        "minimum_eligible_events_unit": "pooled (peer, anchor_event) pairs",
        "minimum_eligible_events_basis": {
            "governance_character": (
                "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as "
                "every prior hypothesis's own floor -- NOT a claim of "
                "guaranteed statistical power and NOT an estimate of "
                "detectable effect size."),
            "provisional": False,
            "why_not_provisional": floor["why_not_provisional"],
            "derivation_inputs": {
                "assumed_effect_size_cohens_d": ASSUMED_EFFECT_SIZE_COHENS_D,
                "assumed_effect_size_character": (
                    "hypothetical, externally chosen, NOT derived from any "
                    "observed project result -- same discipline as every "
                    "prior hypothesis's floor"),
                "alpha_family_wise": ALPHA_FAMILY_WISE,
                "power": POWER,
                "multiplicity_correction": (
                    f"Sidak, formula reused UNCHANGED from HYP-05's own "
                    f"gate, called with k={FAMILY_SIZE_K} EXACT -- HYP-08's "
                    "own two-test design, not a borrowed range from a "
                    "horizon-grid design that does not exist here."),
                "naive_single_test_baseline": naive,
            },
            "why_this_does_not_violate_the_power_statement": (
                "d=0.5, alpha=0.05, and power=0.80 are the same "
                "hypothetical, externally chosen inputs every prior gate "
                "in this project used -- not derived from any observed "
                "project result, real or synthetic-and-specific-to-HYP-08."),
            "derivation_reference": (
                "Live Signal Engine/HYP08_SAMPLE_SIZE_GATE_2026-09-14.md"),
            "real_universe_clears_floor_comfortably": (
                f"{n_pooled} pooled (peer, event) pairs ({n_cs} customer/"
                f"supplier + {n_comp} competitor) clears the "
                f"{floor['operative_floor']}-pair floor by "
                f"{n_pooled / floor['operative_floor']:.1f}x -- a more "
                "comfortable margin than HYP-07's own exact-at-the-floor "
                "clearance, both because the floor itself is smaller "
                "(k=2, not the borrowed k~6 range) and because the pooled "
                "universe is larger than either source universe alone."),
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
            f"All four of a fresh hypothesis's decisions are RESOLVED for "
            f"HYP-08 -- two reused unchanged from prior hypotheses "
            f"(liquidity cutoff, clustering), two genuinely new and "
            f"decided here for the first time (the same-session target, "
            f"the two-test Sidak-corrected design) -- see "
            f"unresolved_analysis_decisions below. A real, pooled universe "
            f"derivation already exists on disk ({n_pooled} pairs, "
            f"{n_peer_tickers} distinct peer tickers, {n_anchor_tickers} "
            "distinct anchor tickers, zero peer-ticker overlap between "
            "the two source sides). No Phase 2 analysis lock has been "
            "signed and no computation of any kind has been performed "
            "against any pair in this universe. This status is "
            "deliberately the same label every prior hypothesis's entry "
            "used at this stage."),
        "required_external_measurement": {
            "measurement": (
                "pooled customer/supplier and competitor relationship "
                "linkage, per anchor ticker, with a structured "
                "relationship_type and a point-in-time as_of_date -- "
                "reused wholesale from HYP-06's and HYP-07's own already-"
                "signed Phase 2 locks, not newly discovered"),
            "required_columns": [
                "anchor_ticker", "peer_ticker", "relationship_type",
                "as_of_date", "source_hypothesis",
            ],
            "availability": "exists",
            "availability_source": (
                "HYP06_PHASE2_LOCK_2026-09-13.json + "
                "HYP07_PHASE2_LOCK_2026-09-14.json, pooled by "
                "make_hyp08_phase2_lock.py"),
            "as_of_date_requirement": (
                "Same discipline as every prior hypothesis: enforced "
                "mechanically by peer_selection.py's PS-4 at the time "
                "each source universe was originally derived, inherited "
                "here rather than re-applied."),
        },
        "forbidden_substitutions": [
            "sector membership as a stand-in for a verified customer/"
            "supplier or competitor relationship",
            "return or volatility correlation as a stand-in for an "
            "established, EDGAR-verified relationship claim",
            "any linkage lacking a first-known/established-as-of date, "
            "applied to historical events",
            "a newly-extracted continuous concentration-intensity measure "
            "as the heterogeneity axis -- considered and explicitly "
            "deferred (see the model plan S5): not machine-extracted for "
            "the reverse-search-discovered universe, and building one now "
            "would be exactly the kind of new filter external review's "
            "own feedback warned against. relationship_type (already "
            "assigned on both source universes) is used instead.",
            "treating the implied customer/supplier-only or implied "
            "competitor-only slope from the interaction fit as a third or "
            "fourth preregistered, corrected test -- see make_hyp08_"
            "phase3_run.py's own explicit 'descriptive_context_not_"
            "verdicted' labeling of those two numbers.",
        ],
        "forbidden_substitution_rule": (
            "If the linkage for an anchor-peer pair is unavailable or "
            "undated, that pair does not count toward HYP-08 -- moot in "
            "practice since both source universes already enforce this."),
        "unresolved_analysis_decisions": [
            {"decision": "the liquidity/coverage cutoff for peer selection",
             "state": "RESOLVED",
             "resolution": "Inherited unchanged through both source "
                           "universes ($2,000,000,000, originally "
                           "RATIFIED in peer_selection.py 2026-09-12), "
                           "not re-applied or re-chosen here."},
            {"decision": "the target anchor/peer universe",
             "state": "RESOLVED",
             "resolution": f"The pooled union of HYP-06's own 778 "
                           f"customer/supplier pairs and HYP-07's own 195 "
                           f"competitor pairs, both already-signed locks "
                           f"-- {n_pooled} total pairs, {n_peer_tickers} "
                           "distinct peer tickers, confirmed zero peer-"
                           "ticker overlap. No new EDGAR discovery of any "
                           "kind performed for HYP-08."},
            {"decision": "the target/outcome definition",
             "state": "RESOLVED",
             "resolution": "target_same_session.py's new same-session "
                           "excess-return formula -- first use of a NO-"
                           "HORIZON-GRID target in this project. Written "
                           "and offline-tested "
                           "(test_hyp04_supply_chain_hedge_target_same_"
                           "session.py) before any outcome value was "
                           "computed for any real HYP-08 pair. NOT yet "
                           "Phase-2-locked."},
            {"decision": "clustering and statistical design",
             "state": "RESOLVED",
             "resolution": f"event_id primary clustering, reused "
                           "unchanged from HYP-05's own re-decision. "
                           f"Significance judged via a closed-form Sidak-"
                           f"corrected critical t-value at k={FAMILY_SIZE_K} "
                           "EXACT preregistered tests, not a max-T "
                           "permutation null -- see make_hyp08_sample_"
                           "size_gate.py's own docstring for why this is "
                           "the correct tool given no horizon grid exists "
                           "to search over."},
        ],
        "options_tension_note": {
            "statement": "HYP-08 makes no options-related claim of any "
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
            f"No result, direction, heterogeneity finding, effect "
            f"estimate, plot, p-value or confidence interval may be "
            f"displayed before {floor['operative_floor']} eligible pairs "
            "(EXACT floor -- see minimum_eligible_events_basis). No "
            "Phase 2 analysis lock exists yet, and no computation has "
            "been performed against this universe -- this registration "
            "alone licenses nothing beyond stating that the universe and "
            "method are both resolved. Reaching the floor licenses "
            "looking, not concluding, same as every prior hypothesis in "
            "this registry."),
    }


def build_v1_18(*, v1_17: Path = V1_17, authored_at: Optional[str] = None,
               ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_17))
    src = _load(v1_17)
    changes: list[str] = []

    doc["registry_version"] = "v1.18"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_17.name
    doc["supersedes_sha256"] = _sha256(v1_17)
    changes.append(f"registry_version: v1.17 -> v1.18 (supersedes {v1_17.name})")

    doc["hypotheses"].append(_hyp08_entry())
    changes.append(f"hypotheses: adds {HYP08_ID}")

    if SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.18 registers a NEW hypothesis and must move nothing about "
            "HYP-04, HYP-05, HYP-06, or HYP-07; SPECIFICATION_FIELDS_THIS_"
            "VERSION_MAY_MOVE must stay empty.")
    for hid in (HYP04_ID, HYP05_ID, HYP06_ID, HYP07_ID):
        old = next(h for h in src["hypotheses"] if h["hypothesis_id"] == hid)
        new = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)
        for f in IMMOVABLE_ENTRY_FIELDS:
            if new.get(f) != old.get(f):
                raise RefusedError(
                    f"{hid}.{f} changed. v1.18 registers HYP-08 and moves "
                    "NOTHING about HYP-04, HYP-05, HYP-06, or HYP-07.")
        if new != old:
            raise RefusedError(f"{hid}'s entry is not byte-identical to "
                               f"{v1_17.name}'s.")
        changes.append(f"guard: {hid}'s entire entry is byte-identical to "
                       f"{v1_17.name}")

    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.18 reports nothing new "
                           "about any prior hypothesis")
    if doc.get("results_note") != src.get("results_note"):
        raise RefusedError("results_note changed; v1.18 reports nothing "
                           "new about any prior hypothesis")
    changes.append("guard: results/results_note untouched")

    if doc.get("hypotheses_carried_forward_unchanged") != src.get(
            "hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged changed; "
                           "HYP-01/02/03 stay exactly as v1.0 defines them")
    changes.append("guard: hypotheses_carried_forward_unchanged untouched")

    doc.setdefault("findings_responded_to", {})["v1.18"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.18 from v1.17, "
                    "registering HYP-08.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.18 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print("  -", r)
        return 1

    doc, changes = build_v1_18(authored_at=a.authored_at)
    print("Changes:")
    for c in changes:
        print("  -", c)

    if not a.write:
        print("\nDRY RUN. Re-run with --write to create v1.18.")
        return 0

    if V1_18.exists():
        print(f"REFUSED -- {V1_18.name} already exists.")
        return 1
    V1_18.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\nWrote {V1_18}")
    print(f"  sha256 {_sha256(V1_18)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
