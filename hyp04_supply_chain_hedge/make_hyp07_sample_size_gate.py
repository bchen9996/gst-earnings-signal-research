#!/usr/bin/env python3
"""HYP-07's sample-size gate -- PROVISIONAL, and a WEAKER borrow than
HYP-06's own reuse of the same numbers.

=== WHY THIS IS AN EVEN WEAKER BORROW THAN HYP-06's ===

HYP-06 reused HYP-05's provisional floor (itself borrowed from HYP-04's
own MEASURED k range, 6.05-6.34) as a planning assumption, and that borrow
was defensible on one ground: HYP-06 reuses HYP-05's target/outcome
definition VERBATIM (`target.py`'s residualized log realized-variance
ratio, same horizon grid) -- so the correlation structure the original
k range was measured against is, at minimum, the SAME FORMULA, just a
different universe.

HYP-07 does not have that ground. `target_signed.py` is a genuinely
different target -- a signed CUMULATIVE abnormal return that PLATEAUS
across horizons, not the magnitude-only ratio that DILUTES across
horizons `target.py` computes (see `target_signed.py`'s own docstring,
"A REAL METHODOLOGICAL CAVEAT"). A cumulative sum and a diluting mean have
different horizon-to-horizon correlation structures by construction, so
HYP-04's own measured k range (6.05-6.34) is not even a same-formula,
different-universe borrow here -- it is a different-formula borrow,
used only because no HYP-07-shaped measurement exists yet, not because
the analogy is expected to hold tightly.

=== WHAT THIS FILE ACTUALLY GIVES YOU ===

`sidak_corrected_n`, `naive_single_test_n`, `PROVISIONAL_K_RANGE`,
`ALPHA_FAMILY_WISE`, `ASSUMED_EFFECT_SIZE_COHENS_D`, `POWER` are all
imported UNCHANGED from `make_hyp05_sample_size_gate` -- the same
closed-form formula and the same borrowed k range, nothing re-derived.
`fixtures_signed.py` (built this session, offline-tested) makes a REAL
measurement against a synthetic fixture shaped like HYP-07's actual
signed-CAR design possible in principle, unlike when HYP-05 first
borrowed this floor -- but building and validating that measurement
correctly is real, separate work, not done in this pass. See
`must_be_superseded_by`.

=== THE REAL UNIVERSE CLEARS THE FLOOR EXACTLY, NOT COMFORTABLY ===

HYP-06's real universe (778 pairs) cleared this same provisional floor
(195) by nearly 4x. HYP-07's real universe clears it AT EXACTLY 195 of
625 evaluated candidates -- the floor and the real count are numerically
identical. This is disclosed here and in the registry entry precisely
because it is the least comfortable, most knife-edge version of "clears
the floor" this project has produced, and burying that fact would be a
real, undisclosed methodological softening.

Run:  python -m hyp04_supply_chain_hedge.make_hyp07_sample_size_gate
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
OUT_PATH = LSE / f"HYP07_SAMPLE_SIZE_GATE_{AUTHORED_AT}.md"

#: The real, measured universe size as of this writing -- read from the
#: artifact, not asserted. See build_report()'s own on-disk check.
UNIVERSE_ARTIFACT = LSE / "HYP07_PEER_UNIVERSE_REVERSE_SEARCH_SCALED_2026-09-13.json"


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
            "HYP-07's target (target_signed.py, a signed cumulative "
            "abnormal return) is a DIFFERENT FORMULA from the one HYP-04's "
            "own k range was measured against (target.py's magnitude-only "
            "realized-variance ratio) -- a weaker borrow than HYP-06's own "
            "reuse of these same numbers, which at least shared the same "
            "target formula as HYP-04/05. fixtures_signed.py (built this "
            "session) makes a real measurement possible in principle; it "
            "is not performed in this pass."),
        "must_be_superseded_by": (
            "A fresh max-T permutation measurement (inference.max_t_"
            "permutation via local_projection_analysis, same mechanism "
            "HYP-04's Phase 0 used) against synthetic fixtures generated "
            "by fixtures_signed.py, shaped like HYP-07's own real cluster "
            "design -- written as a new dated version of this finding, "
            "the same standard every prior hypothesis's provisional floor "
            "was held to."),
    }


def build_report() -> dict[str, Any]:
    naive = naive_single_test_n()
    prov = provisional_operative_floor()
    real_n = _real_universe_size() if UNIVERSE_ARTIFACT.is_file() else None
    clears = (real_n is not None
              and real_n >= prov["operative_provisional_floor"])
    return {
        "artifact": OUT_PATH.name,
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            "A provisional sample-size gate for HYP-07, reusing HYP-05's "
            "own provisional floor (same k range, same formula) rather "
            "than re-deriving it -- see module docstring for why this is "
            "an even weaker borrow than HYP-06's own reuse of these same "
            "numbers, since HYP-07's target is a genuinely different "
            "formula, not merely a different universe under the same one."),
        "governance_character": (
            "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as "
            "HYP-01/02/03/04/05/06's own floors -- NOT a claim of "
            "guaranteed statistical power and NOT an estimate of "
            "detectable effect size."),
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
        "clears_provisional_floor": clears,
        "clears_provisional_floor_note": (
            "EXACTLY at the floor (195 of 625 evaluated candidates), not "
            "comfortably above it the way HYP-06's 778 cleared the "
            "identical floor by nearly 4x. Disclosed deliberately, not "
            "rounded away."
            if real_n is not None and real_n == prov["operative_provisional_floor"]
            else None),
    }


def render(report: dict[str, Any]) -> str:
    prov = report["provisional_operative_floor"]
    lines = [
        f"# {report['artifact']}",
        "",
        f"**{report['hypothesis_id']}** -- PROVISIONAL sample-size gate, "
        "reusing HYP-05's own provisional floor (a weaker borrow than "
        "HYP-06's -- see module docstring).",
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
    ]
    if report.get("clears_provisional_floor_note"):
        lines += ["", f"**{report['clears_provisional_floor_note']}**"]
    lines += [
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
