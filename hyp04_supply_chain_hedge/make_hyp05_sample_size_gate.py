#!/usr/bin/env python3
"""HYP-05's sample-size gate -- PROVISIONAL. Read this before citing a number.

=== WHY THIS IS PROVISIONAL, NOT MEASURED ===

HYP-04's own floor (193 anchor events) came from a real measurement: a
max-T permutation run against SYNTHETIC fixtures shaped like HYP-04's own
LOCKED horizon-grid design (`inference.max_t_permutation`, called through
`local_projection_analysis`, whose `effective_independent_tests` output is
the k that feeds the Sidak correction below). That measurement is only
meaningful once the design being measured is fixed -- k depends on how
adjacent horizons correlate under THAT specific design.

HYP-05 has not fixed a design. Its plan document (Step 2 of the same build
this file belongs to) explicitly leaves the target/outcome definition,
model spec and anchor/peer universe open. An attempt was made this session
to measure k anyway, against a guessed-at synthetic panel (24 anchors, 16
quarters, 6 peers/anchor, zero injected effect) -- it returned k_eff =
47.4, which is not a plausible measurement: k cannot exceed the 20 actual
horizons tested, and the fully-independent upper bound in HYP-04's own
table is 20 for exactly that reason. The measurement was methodologically
premature (there is no HYP-05 design yet to measure the correlation
structure OF), not merely unlucky, and its number is discarded rather than
reported.

=== WHAT THIS FILE ACTUALLY GIVES YOU ===

1. `naive_single_test_n()` -- the k=1 baseline. This is NOT design-dependent
   at all (no horizon grid, no correlation structure enters it), so it is a
   real, correct floor today: N=126 for d=0.5, alpha=0.05, power=0.80,
   labelled-only, never the operative gate, same as HYP-04's own naive 126.
2. `sidak_corrected_n(k)` -- the same closed-form HYP-04 used. Verified
   against HYP-04's own published table (`HYP04_PHASE0_FEASIBILITY_STATUS_
   2026-08-18.md` section 5): k=1->125.6, k=2->151.6, k=4->177.7,
   k=6.05->193.3, k=6.34->195.0, k=20->238.1 -- every value reproduces to
   within rounding. This function is correct; what is provisional is which
   k to feed it for HYP-05.
3. A PROVISIONAL operative floor, borrowing HYP-04's own MEASURED k range
   (6.05-6.34) as a planning assumption -- not a claim about HYP-05's
   design, which does not exist yet to measure. This is not a use of any
   OBSERVED PROJECT RESULT (the power_statement's actual prohibition): both
   numbers come from HYP-04's Phase 0 SYNTHETIC-fixture diagnostic, not from
   any real collected data, exactly as it was when HYP-04's own plan quoted
   a provisional "190-240" before ITS measurement existed. The conservative
   (higher-N) end of that range is used, matching this project's stated
   preference for floors that demand MORE evidence, not less.

=== WHAT MUST HAPPEN BEFORE THIS FLOOR GOVERNS ANYTHING ===

Once HYP-05's horizon grid and model spec are fixed (a decision this file
does not make), re-run a max-T permutation measurement against SYNTHETIC
fixtures shaped like THAT design -- the same call this file's docstring
describes above -- and write a NEW dated version of this finding super-
seding the provisional number with a measured one, exactly mirroring how
HYP-04's own "190-240" placeholder was superseded by its measured 193.

Run:  python -m hyp04_supply_chain_hedge.make_hyp05_sample_size_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from scipy import stats

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AUTHORED_AT = "2026-09-11"
OUT_PATH = LSE / f"HYP05_SAMPLE_SIZE_GATE_{AUTHORED_AT}.md"

# Same three inputs HYP-04 used, verbatim. d=0.5 is hypothetical and chosen
# before any data, same as HYP-04's; it is NOT re-derived here from anything
# this project has observed.
ASSUMED_EFFECT_SIZE_COHENS_D = 0.5
ALPHA_FAMILY_WISE = 0.05
POWER = 0.80

# HYP-04's own measured range, borrowed as a PROVISIONAL planning assumption
# only -- see the module docstring. NOT a measurement of HYP-05's design.
PROVISIONAL_K_RANGE = (6.05, 6.34)


def sidak_corrected_n(k: float, *, d: float = ASSUMED_EFFECT_SIZE_COHENS_D,
                      alpha: float = ALPHA_FAMILY_WISE,
                      power: float = POWER) -> float:
    """Total N for a two-sample Cohen's-d test, Sidak-corrected over k
    effective independent tests. The exact closed form HYP-04's own 193
    floor came from -- verified to reproduce its published table."""
    if k < 1:
        raise ValueError(f"k must be >= 1 (got {k!r})")
    alpha_sidak = 1.0 - (1.0 - alpha) ** (1.0 / k)
    z_alpha = stats.norm.ppf(1.0 - alpha_sidak / 2.0)
    z_power = stats.norm.ppf(power)
    n_per_group = 2.0 * ((z_alpha + z_power) / d) ** 2
    return 2.0 * n_per_group


def naive_single_test_n(**kwargs: Any) -> float:
    """k=1: the labelled-only baseline, never the operative gate."""
    return sidak_corrected_n(1.0, **kwargs)


def provisional_operative_floor() -> dict[str, Any]:
    lo, hi = PROVISIONAL_K_RANGE
    n_lo, n_hi = sidak_corrected_n(lo), sidak_corrected_n(hi)
    # The conservative (higher-N) end, matching this project's stated
    # preference for floors that demand MORE evidence, not less.
    operative = float(max(n_lo, n_hi))
    return {
        "k_range_borrowed_from_hyp04_phase0": list(PROVISIONAL_K_RANGE),
        "implied_n_range": [round(float(n_lo), 1), round(float(n_hi), 1)],
        "operative_provisional_floor": round(operative),
        "operative_provisional_floor_unit": "anchor events (unit TBD once "
                                             "HYP-05's design is fixed)",
        "provisional": True,
        "why_borrowed_not_measured": (
            "HYP-05 has not fixed a horizon grid or model spec, so there is "
            "no design yet whose correlation structure a max-T permutation "
            "run could honestly measure. A measurement attempted against a "
            "guessed-at synthetic panel this session returned k_eff=47.4, "
            "exceeding the 20-horizon upper bound, and was discarded as "
            "methodologically premature rather than reported."),
        "must_be_superseded_by": (
            "A fresh max-T permutation measurement (inference.max_t_"
            "permutation via local_projection_analysis, same mechanism "
            "HYP-04's Phase 0 used) against synthetic fixtures shaped like "
            "HYP-05's OWN locked design, once that design exists -- written "
            "as a new dated version of this finding, exactly mirroring how "
            "HYP-04's own provisional '190-240' was superseded by its "
            "measured 193."),
    }


def build_report() -> dict[str, Any]:
    naive = naive_single_test_n()
    prov = provisional_operative_floor()
    return {
        "artifact": OUT_PATH.name,
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "A provisional sample-size gate for HYP-05, modelled on HYP-04's "
            "own (Live Signal Engine/HYP04_PHASE0_FEASIBILITY_STATUS_2026-08"
            "-18.md section 5). The naive baseline is a real number; the "
            "operative floor is PROVISIONAL, borrowed from HYP-04's own "
            "measurement as a planning assumption, and requires its own "
            "dedicated remeasurement before it may govern anything -- see "
            "provisional_operative_floor.must_be_superseded_by."),
        "governance_character": (
            "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as HYP-01/02/"
            "03's 60/60/40 and HYP-04's 193 -- NOT a claim of guaranteed "
            "statistical power and NOT an estimate of detectable effect "
            "size."),
        "derivation_inputs": {
            "assumed_effect_size_cohens_d": ASSUMED_EFFECT_SIZE_COHENS_D,
            "assumed_effect_size_character": (
                "hypothetical, externally chosen, NOT derived from any "
                "observed project result -- same as HYP-04's."),
            "alpha_family_wise": ALPHA_FAMILY_WISE,
            "power": POWER,
            "multiplicity_correction": (
                "Sidak over k effective independent tests -- formula "
                "verified against HYP-04's own published table."),
        },
        "naive_single_test_baseline": round(naive),
        "naive_single_test_baseline_note": (
            "LABELLED BASELINE ONLY. Never the operative floor. Not "
            "design-dependent -- correct today, unlike the provisional "
            "floor below."),
        "provisional_operative_floor": prov,
        "why_this_does_not_violate_the_power_statement": (
            "Both k values entering this derivation (HYP-04's measured "
            "6.05-6.34) came from HYP-04's OWN Phase 0 SYNTHETIC-fixture "
            "diagnostic with known injected ground truth, not from any "
            "observed project result or real collected data. No HYP-05 "
            "data, real or synthetic-and-specific-to-HYP-05, entered this "
            "calculation."),
    }


def render(report: dict[str, Any]) -> str:
    prov = report["provisional_operative_floor"]
    lines = [
        f"# {report['artifact']}",
        "",
        f"**{report['hypothesis_id']}** -- PROVISIONAL sample-size gate.",
        "",
        report["what_this_is"],
        "",
        f"Naive single-test baseline (k=1, never the operative floor): "
        f"**{report['naive_single_test_baseline']}**.",
        "",
        f"Provisional operative floor (borrowed k range "
        f"{prov['k_range_borrowed_from_hyp04_phase0']}, conservative end): "
        f"**{prov['operative_provisional_floor']} anchor events** "
        f"(implied N range {prov['implied_n_range']}).",
        "",
        f"**Why borrowed, not measured:** {prov['why_borrowed_not_measured']}",
        "",
        f"**Must be superseded by:** {prov['must_be_superseded_by']}",
        "",
        f"**Does not violate the power statement:** "
        f"{report['why_this_does_not_violate_the_power_statement']}",
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
