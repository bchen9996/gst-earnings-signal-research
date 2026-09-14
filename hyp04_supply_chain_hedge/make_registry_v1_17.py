#!/usr/bin/env python3
"""Generate hypothesis-registry v1.17 from v1.16. Registers HYP-07.

=== WHAT v1.17 SETTLES ===

One thing: a wholly NEW hypothesis entry, HYP-07, is ADDED to
`hypotheses`. HYP-04's, HYP-05's, and HYP-06's own entries are untouched
-- every field, byte-identical to v1.16. Mirrors exactly how v1.16 first
added HYP-06 without touching HYP-04 or HYP-05.

=== WHY HYP-07 IS NOT THE SAME PATTERN AS HYP-06's REGISTRATION ===

HYP-06 reused HYP-05's OWN already-locked target/outcome definition and
clustering choice verbatim -- it was the identical scientific question,
tested on a bigger universe. HYP-07 is a genuinely different mechanism
(competitor relationships, an OPPOSITE-sign prediction) with a genuinely
new target (`target_signed.py`, a signed cumulative abnormal return --
first use of a signed target in this project). Two of the four decisions
a fresh hypothesis owes are therefore new, not reused: the target/outcome
definition and the anchor/peer universe itself. Two are reused unchanged
because they are project-wide conventions, not mechanism-specific: the
liquidity/coverage cutoff and the clustering choice. See
`HYP07_CompetitorRelationshipSignedReaction_MODEL_PLAN_2026-09-13.md` for
the full reasoning.

All four decisions are `RESOLVED`, not `PENDING` -- but "RESOLVED" here
means "decided, written, and offline-tested before any outcome value was
computed for any real HYP-07 pair," NOT "Phase-2-locked." No Phase 2 lock
has been signed for HYP-07's target spec; that is a separate, later,
separately authorized step, same as every prior hypothesis.

=== THE SAMPLE-SIZE FLOOR IS CLEARED EXACTLY, NOT COMFORTABLY ===

Unlike HYP-06 (778 pairs vs a 195 floor, nearly 4x), HYP-07's real
universe clears the SAME borrowed provisional floor (195, borrowed from
HYP-04's own measured k range) at EXACTLY 195 of 625 evaluated candidates.
This registration does not round that away -- see
`minimum_eligible_events_basis` below and
`HYP07_SAMPLE_SIZE_GATE_2026-09-13.md` for the full disclosure, including
why this is an even weaker borrow than HYP-06's own reuse of the same
numbers (HYP-07's target is a different formula, not merely a different
universe under the same one).

=== HYP-04's, HYP-05's AND HYP-06's ENTRIES MOVE NOTHING ===

`IMMOVABLE_ENTRY_FIELDS` is enforced, unweakened, against HYP-04's,
HYP-05's, AND HYP-06's entries (v1.16 already established the pattern of
checking it against more than one hypothesis's entry).
`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` is empty, and the guard
raises if that is not literally true after the build. `results`/
`results_note` are also compared byte-identical.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_17 --write

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

from hyp04_supply_chain_hedge.make_hyp07_sample_size_gate import (
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
HYP07_ID = "HYP-07"

V1_16 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.16.json"
V1_17 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.17.json"

AUTHORED_AT = "2026-09-13"

#: The written basis. A new hypothesis with no dated plan behind it is
#: exactly what "registration is a governed act" forbids.
FINDINGS = (
    "Live Signal Engine/HYP07_CompetitorRelationshipSignedReaction_"
    "MODEL_PLAN_2026-09-13.md",
    "Live Signal Engine/HYP07_SAMPLE_SIZE_GATE_2026-09-13.md",
    "Live Signal Engine/HYP07_DISCOVERY_AND_TARGET_METHODOLOGY_2026-09-13.md",
    "Live Signal Engine/HYP07_PEER_UNIVERSE_REVERSE_SEARCH_SCALED_2026-09-13.json",
)

#: HYP-04's, HYP-05's, and HYP-06's entries move nothing in v1.17 --
#: empty, enforced.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = ()


def check_preconditions(*, v1_16: Path = V1_16, v1_17: Path = V1_17,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_16.is_file():
        refusals.append(f"registry v1.16 not found at {v1_16.name}")
    if v1_17.exists():
        refusals.append(
            f"{v1_17.name} already exists. Refusing to overwrite a "
            "governance artifact -- delete it deliberately first if that "
            "is really intended.")
    for f in FINDINGS:
        if not Path(f).is_file():
            refusals.append(
                f"the dated finding {f} is not on disk. Registering a "
                "hypothesis with no written plan behind it is exactly what "
                "this project forbids.")
    doc = _load(v1_16) if v1_16.is_file() else {}
    if any(h.get("hypothesis_id") == HYP07_ID
           for h in doc.get("hypotheses", [])):
        refusals.append(f"{HYP07_ID} is already registered in {v1_16.name}")
    return refusals


def _hyp07_entry() -> dict[str, Any]:
    prov = provisional_operative_floor()
    naive = round(naive_single_test_n())
    universe = json.loads(UNIVERSE_ARTIFACT.read_text(encoding="utf-8"))
    n_qualifying = sum(1 for q in universe["qualifications"] if q["qualifies"])
    n_peer_tickers = len({q["ticker"] for q in universe["qualifications"]
                          if q["qualifies"]})
    n_candidates_evaluated = universe.get("candidates_evaluated")
    return {
        "hypothesis_id": HYP07_ID,
        "title": "Competitor-relationship signed reaction to anchor "
                 "earnings surprises",
        "question": (
            "Does a company's stock move in the OPPOSITE direction from a "
            "verified competitor's earnings surprise -- a directional "
            "prediction HYP-04/05/06's customer/supplier relationships "
            "cannot make, since those predict same-direction elevated "
            "volatility, not a signed reaction. Tested here for the first "
            "time in this project via a new signed cumulative-abnormal-"
            "return target (target_signed.py), against a systematically-"
            "discovered (reverse-EDGAR-search, not hand-guessed or "
            "forward-self-reported) competitor-relationship universe -- "
            "see the model plan for why forward extraction (a filer's own "
            "10-K naming its most prominent rivals) was tried first and "
            "diagnosed as structurally biased toward large, ineligible "
            "names."),
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
                    "same provisional planning assumption HYP-05's and "
                    "HYP-06's own registrations used -- an even WEAKER "
                    "borrow here than for HYP-06, since HYP-07's target "
                    "is a different formula (a plateauing cumulative sum), "
                    "not merely a different universe under the same "
                    "formula HYP-04's k was measured against."),
                "naive_single_test_baseline": naive,
            },
            "why_this_does_not_violate_the_power_statement": (
                "The power_statement forbids a power calculation performed "
                "USING OBSERVED PROJECT RESULTS. Both k values entering "
                "this derivation are HYP-04's own Phase 0 SYNTHETIC-fixture "
                "measurement, not any observed result or real collected "
                "data of any kind."),
            "derivation_reference": (
                "Live Signal Engine/HYP07_SAMPLE_SIZE_GATE_2026-09-13.md"),
            "real_universe_clears_floor_exactly_not_comfortably": (
                f"{n_qualifying} of {n_candidates_evaluated} evaluated "
                f"candidates qualify -- numerically EQUAL to the "
                f"{prov['operative_provisional_floor']}-pair floor, not "
                "comfortably above it the way HYP-06's 778 cleared the "
                "identical floor by nearly 4x. Disclosed deliberately, not "
                "rounded away -- see HYP07_SAMPLE_SIZE_GATE_2026-09-13.md."),
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
            f"HYP-07 -- two reused unchanged from prior hypotheses "
            f"(liquidity cutoff, clustering), two genuinely new and "
            f"decided here for the first time (the signed target, the "
            f"reverse-search-discovered universe) -- see "
            f"unresolved_analysis_decisions below. A real, fail-closed "
            f"peer-universe derivation already exists on disk "
            f"({n_qualifying} qualifying (peer, event) pairs of "
            f"{n_candidates_evaluated} evaluated, {n_peer_tickers} "
            f"distinct peer tickers). No Phase 2 analysis lock has been "
            "signed and no computation of any kind has been performed "
            "against any pair in this universe. This status is "
            "deliberately the same label HYP-06's entry used -- 'the "
            "universe is resolved' is not 'a result exists' or 'a lock "
            "has been signed,' in either entry."),
        "required_external_measurement": {
            "measurement": (
                "competitor-relationship linkage map, per anchor ticker, "
                "with a structured relationship direction (symmetric "
                "competitor, not directional customer/supplier) and a "
                "point-in-time as_of_date, discovered via reverse EDGAR "
                "full-text search rather than hand-curation or forward "
                "self-report"),
            "required_columns": [
                "anchor_ticker", "peer_ticker", "relationship_type",
                "as_of_date", "source",
            ],
            "availability": "exists",
            "availability_source": str(UNIVERSE_ARTIFACT).replace("\\", "/"),
            "as_of_date_requirement": (
                "Same discipline as HYP-04/05/06: enforced mechanically "
                "by peer_selection.py's PS-4 (as_of_date strictly precedes "
                "anchor_event_date), not merely required by policy."),
        },
        "forbidden_substitutions": [
            "sector membership as a stand-in for a verified competitor "
            "relationship",
            "return or volatility correlation as a stand-in for an "
            "established, EDGAR-verified competitor claim",
            "any linkage map lacking a first-known/established-as-of date, "
            "applied to historical events",
            "forward self-reported 'most prominent rival' naming as a "
            "stand-in for genuine reciprocal competitor disclosure -- this "
            "project's own Step 0 tried exactly that first and diagnosed "
            "it as structurally biased toward large, ineligible names",
            "selecting the peer universe by which candidates already look "
            "promising in this or any other hypothesis's data -- moot for "
            "HYP-07 since the universe was fixed by the round-7 discovery "
            "run before any HYP-07 outcome existed to select on",
        ],
        "forbidden_substitution_rule": (
            "If the linkage for an anchor-peer pair is unavailable or "
            "undated, that pair does not count toward HYP-07."),
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
                           f" -- {n_qualifying} (peer, event) pairs of "
                           f"{n_candidates_evaluated} evaluated, "
                           f"{n_peer_tickers} distinct peer tickers, "
                           "derived by derive_peer_universe()'s real, "
                           "fail-closed PS-1..PS-4 run against a reverse-"
                           "EDGAR-search discovered, hand-reviewed set of "
                           "371 confirmed leads (370 kept), not "
                           "hand-selected or forward-extracted."},
            {"decision": "the target/outcome definition",
             "state": "RESOLVED",
             "resolution": "target_signed.py's new signed cumulative "
                           "abnormal-return formula -- first use of a "
                           "SIGNED target in this project (HYP-04/05/06 "
                           "all used the magnitude-only residualized log "
                           "realized-variance ratio). Written and "
                           "offline-tested "
                           "(test_hyp04_supply_chain_hedge_target_signed.py"
                           ") before any outcome value was computed for "
                           "any real HYP-07 pair. NOT yet Phase-2-locked "
                           "-- to be pinned by sha256 at HYP-07's own "
                           "Phase 2 lock, the same step every prior "
                           "hypothesis's spec was pinned at."},
            {"decision": "clustering",
             "state": "RESOLVED",
             "resolution": "event_id primary (mirrors clustered_se.HYP05_"
                           "TWO_WAY_LIMITATION_NOTE), calendar_period as a "
                           "one-way robustness lens reported alongside it, "
                           "reused verbatim from HYP-05's/HYP-06's own "
                           "convention, not re-decided."},
        ],
        "options_tension_note": {
            "statement": "HYP-07 makes no options-related claim of any "
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
            f"No result, direction (competitive displacement vs "
            f"comovement), effect estimate, plot, p-value or confidence "
            f"interval may be displayed before "
            f"{prov['operative_provisional_floor']} eligible pairs "
            "(PROVISIONAL floor -- see minimum_eligible_events_basis, "
            "including the note that the real universe clears this floor "
            "EXACTLY, not comfortably). No Phase 2 analysis lock exists "
            "yet, and no computation has been performed against this "
            "universe -- this registration alone licenses nothing beyond "
            "stating that the universe and method are both resolved. "
            "Reaching the floor licenses looking, not concluding, same as "
            "every prior hypothesis in this registry."),
    }


def build_v1_17(*, v1_16: Path = V1_16, authored_at: Optional[str] = None,
               ) -> tuple[dict[str, Any], list[str]]:
    doc = copy.deepcopy(_load(v1_16))
    src = _load(v1_16)
    changes: list[str] = []

    doc["registry_version"] = "v1.17"
    doc["authored_at"] = authored_at or AUTHORED_AT
    doc["supersedes"] = v1_16.name
    doc["supersedes_sha256"] = _sha256(v1_16)
    changes.append(f"registry_version: v1.16 -> v1.17 (supersedes {v1_16.name})")

    doc["hypotheses"].append(_hyp07_entry())
    changes.append(f"hypotheses: adds {HYP07_ID}")

    # --- HYP-04's, HYP-05's, and HYP-06's entries move nothing, guard
    # unweakened -------------------------------------------------------
    if SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.17 registers a NEW hypothesis and must move nothing about "
            "HYP-04, HYP-05, or HYP-06; SPECIFICATION_FIELDS_THIS_VERSION_"
            "MAY_MOVE must stay empty.")
    for hid in (HYP04_ID, HYP05_ID, HYP06_ID):
        old = next(h for h in src["hypotheses"] if h["hypothesis_id"] == hid)
        new = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)
        for f in IMMOVABLE_ENTRY_FIELDS:
            if new.get(f) != old.get(f):
                raise RefusedError(
                    f"{hid}.{f} changed. v1.17 registers HYP-07 and moves "
                    "NOTHING about HYP-04, HYP-05, or HYP-06.")
        if new != old:
            raise RefusedError(f"{hid}'s entry is not byte-identical to "
                               f"{v1_16.name}'s.")
        changes.append(f"guard: {hid}'s entire entry is byte-identical to "
                       f"{v1_16.name}")

    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.17 reports nothing new "
                           "about any prior hypothesis")
    if doc.get("results_note") != src.get("results_note"):
        raise RefusedError("results_note changed; v1.17 reports nothing "
                           "new about any prior hypothesis")
    changes.append("guard: results/results_note untouched")

    if doc.get("hypotheses_carried_forward_unchanged") != src.get(
            "hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged changed; "
                           "HYP-01/02/03 stay exactly as v1.0 defines them")
    changes.append("guard: hypotheses_carried_forward_unchanged untouched")

    doc.setdefault("findings_responded_to", {})["v1.17"] = list(FINDINGS)
    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.17 from v1.16, "
                    "registering HYP-07.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.17 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print("  -", r)
        return 1

    doc, changes = build_v1_17(authored_at=a.authored_at)
    print("Changes:")
    for c in changes:
        print("  -", c)

    if not a.write:
        print("\nDRY RUN. Re-run with --write to create v1.17.")
        return 0

    if V1_17.exists():
        print(f"REFUSED -- {V1_17.name} already exists.")
        return 1
    V1_17.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\nWrote {V1_17}")
    print(f"  sha256 {_sha256(V1_17)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
