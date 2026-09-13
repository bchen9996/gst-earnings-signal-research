#!/usr/bin/env python3
"""HYP-06's sample-size gate -- PROVISIONAL, for the same reason HYP-05's
own gate was, reused rather than re-derived.

=== WHY STILL PROVISIONAL, EVEN THOUGH HYP-06's DESIGN IS FULLY FIXED ===

Unlike HYP-05 at its own registration (no design existed yet to measure a
real k for), HYP-06's design IS fully fixed -- it reuses HYP-05's own
locked target/outcome definition and clustering choice verbatim (see
`HYP06_ScaledSupplyChainRelationshipLag_MODEL_PLAN_2026-09-13.md` S2). A
real max-T permutation measurement against a synthetic fixture shaped
like HYP-06's actual 776-cluster design is therefore POSSIBLE in
principle, unlike HYP-05's own attempt (discarded, k_eff=47.4,
methodologically premature against a design that did not exist).

It is not done in this pass anyway: building and validating that
synthetic-fixture generator correctly for a 776-cluster, 25-peer,
29-anchor shape is real, separate work, and HYP-06's actual universe
(778 qualifying pairs) clears even the conservative end of HYP-05's own
provisional floor (195) by nearly 4x. Reusing the provisional floor is
therefore a conservative, correct-in-direction eligibility check today;
it is not claimed to be the number that will eventually govern power
calculations, and it is explicitly flagged for the same real
measurement HYP-05's own gate flagged and never completed.

`sidak_corrected_n` is imported UNCHANGED from `make_hyp05_sample_size_
gate` -- the same closed-form formula, verified there against HYP-04's
own published table. Nothing about the math is re-derived here.

Run:  python -m hyp04_supply_chain_hedge.make_hyp06_sample_size_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .make_hyp05_sample_size_gate import (
    ALPHA_FAMILY_WISE,
    ASSUMED_EFFECT_SIZE_COHENS_D,
    POWER,
    PROVISIONAL_K_RANGE,
    naive_single_test_n,
    sidak_corrected_n,
)

LSE = Path("Live Signal Engine")

AUTHORED_AT = "2026-09-13"
OUT_PATH = LSE / f"HYP06_SAMPLE_SIZE_GATE_{AUTHORED_AT}.md"

#: The real, measured universe size as of this writing -- read from the
#: artifact, not asserted. See build_report()'s own on-disk check.
UNIVERSE_ARTIFACT = LSE / "HYP05_PEER_UNIVERSE_SCALED_2026-09-13.json"


def _real_universe_size(path: Path = UNIVERSE_ARTIFACT) -> int:
    import json
    d = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for q in d["qualifications"] if q["qualifies"])


def provisional_operative_floor() -> dict[str, Any]:
    lo, hi = PROVISIONAL_K_RANGE
    n_lo, n_hi = sidak_corrected_n(lo), sidak_corrected_n(hi)
    operative = float(max(n_lo, n_hi))
    return {
        "k_range_borrowed_from_hyp04_phase0": list(PROVISIONAL_K_RANGE),
        "implied_n_range": [round(float(n_lo), 1), round(float(n_hi), 1)],
        "operative_provisional_floor": round(operative),
        "operative_provisional_floor_unit": "(peer, anchor_event) pairs",
        "provisional": True,
        "why_still_provisional": (
            "HYP-06's design IS fully fixed (reused from HYP-05's own "
            "locked target/outcome/clustering), unlike HYP-05 at its own "
            "registration -- so a real measurement is possible in "
            "principle. It is not done in this pass: building and "
            "validating a synthetic-fixture generator shaped like the "
            "real 776-cluster design is real, separate work, and is not "
            "needed to clear a floor the real universe already clears "
            "several times over."),
        "must_be_superseded_by": (
            "A fresh max-T permutation measurement against synthetic "
            "fixtures shaped like HYP-06's own 776-cluster design, "
            "written as a new dated version of this finding -- same "
            "mechanism HYP-04's Phase 0 used, same standard HYP-05's own "
            "gate document left unmet."),
    }


def build_report() -> dict[str, Any]:
    naive = naive_single_test_n()
    prov = provisional_operative_floor()
    real_n = _real_universe_size() if UNIVERSE_ARTIFACT.is_file() else None
    return {
        "artifact": OUT_PATH.name,
        "hypothesis_id": "HYP-06",
        "what_this_is": (
            "A provisional sample-size gate for HYP-06, reusing HYP-05's "
            "own provisional floor (same k range, same formula) rather "
            "than re-deriving it -- see module docstring for why this "
            "stays provisional despite HYP-06's design being fully fixed."),
        "governance_character": (
            "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as "
            "HYP-01/02/03/04/05's own floors -- NOT a claim of guaranteed "
            "statistical power and NOT an estimate of detectable effect "
            "size."),
        "derivation_inputs": {
            "assumed_effect_size_cohens_d": ASSUMED_EFFECT_SIZE_COHENS_D,
            "alpha_family_wise": ALPHA_FAMILY_WISE,
            "power": POWER,
            "multiplicity_correction": "Sidak over k effective independent "
                                       "tests, reused from HYP-05's own gate.",
        },
        "naive_single_test_baseline": round(naive),
        "provisional_operative_floor": prov,
        "real_universe_size": real_n,
        "real_universe_source": (str(UNIVERSE_ARTIFACT) if real_n is not None
                                 else None),
        "clears_provisional_floor": (
            real_n is not None
            and real_n >= prov["operative_provisional_floor"]),
    }


def render(report: dict[str, Any]) -> str:
    prov = report["provisional_operative_floor"]
    lines = [
        f"# {report['artifact']}",
        "",
        f"**{report['hypothesis_id']}** -- PROVISIONAL sample-size gate, "
        "reusing HYP-05's own provisional floor.",
        "",
        report["what_this_is"],
        "",
        f"Naive single-test baseline (k=1, never the operative floor): "
        f"**{report['naive_single_test_baseline']}**.",
        "",
        f"Provisional operative floor (borrowed k range "
        f"{prov['k_range_borrowed_from_hyp04_phase0']}, conservative end): "
        f"**{prov['operative_provisional_floor']} (peer, anchor_event) "
        f"pairs** (implied N range {prov['implied_n_range']}).",
        "",
        f"**Real universe size as of {AUTHORED_AT}:** "
        f"**{report['real_universe_size']}** qualifying pairs "
        f"(`{report['real_universe_source']}`). "
        f"**Clears the provisional floor: {report['clears_provisional_floor']}** "
        f"({report['real_universe_size']} vs "
        f"{prov['operative_provisional_floor']}).",
        "",
        f"**Why still provisional:** {prov['why_still_provisional']}",
        "",
        f"**Must be superseded by:** {prov['must_be_superseded_by']}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="write the dated finding (default: print only)")
    a = ap.parse_args(argv)

    report = build_report()
    text = render(report)
    print(text)

    if not a.write:
        print(f"DRY RUN. Re-run with --write to create {OUT_PATH.name}.")
        return 0

    if OUT_PATH.exists():
        print(f"REFUSED -- {OUT_PATH.name} already exists. Dated artifacts "
              "are never overwritten.")
        return 1
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
