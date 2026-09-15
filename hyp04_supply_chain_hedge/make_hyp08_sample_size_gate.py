#!/usr/bin/env python3
"""HYP-08's sample-size gate -- MEASURED, not provisional, and for a
genuinely different reason than HYP-05/06/07's borrowed k range.

=== WHY k=2 IS KNOWN BY CONSTRUCTION, NOT MEASURED FROM A SYNTHETIC FIXTURE ===

HYP-04/05/06/07's k (`PROVISIONAL_K_RANGE=6.05-6.34`, borrowed from HYP-04's
own measurement) exists because a max-T permutation null over a 20-horizon
grid needs its EFFECTIVE number of independent tests measured empirically --
adjacent horizons are correlated by construction and the correlation
structure depends on the target's own geometry (diluting mean vs. plateauing
sum), which is why HYP-07's own gate flagged that borrow as even weaker than
HYP-06's.

HYP-08 has no horizon grid at all (see `target_same_session.py` -- every
row's `horizon` field is a constant 0). Its family is exactly TWO
preregistered tests, fixed by the design, not discovered by measurement:

  1. the plain pooled same-session coefficient
     (`inference.fit_local_projections(table, horizons=(0,), ...)`)
  2. the shock:is_competitor heterogeneity coefficient
     (`inference.fit_interaction_model(table, ...)`)

k=2 is therefore EXACT, not an estimate with its own uncertainty -- there is
nothing left to measure once the design (this document) is written, unlike
every prior hypothesis's borrowed range.

=== WHAT THIS FILE GIVES YOU ===

1. `naive_single_test_n()` -- the k=1 baseline, reused unchanged from
   `make_hyp05_sample_size_gate` (not re-derived; same formula, same
   inputs).
2. `sidak_corrected_n(2)` -- HYP-08's actual operative floor, called with
   the EXACT k this design has, not a borrowed range's conservative end.
3. `sidak_critical_t(dof, k=2)` -- the SIGNIFICANCE-side counterpart to
   (2): the Sidak-corrected two-sided critical t-value a real fit's
   |t_stat| must clear, at the SAME k=2 family this floor was sized for.
   HYP-04/05/06/07 judge significance via `inference.max_t_permutation`'s
   empirical null (needed because max_h|t_h| over correlated horizons has
   no closed form); HYP-08 has no such max-selection problem -- a
   closed-form Sidak-corrected t-critical-value is the CORRECT tool for a
   small, fixed-size, non-searched test family, not a departure from
   rigor. Used by `make_hyp08_phase3_run.py` to judge both the primary
   and the heterogeneity fit.

Run:  python -m hyp04_supply_chain_hedge.make_hyp08_sample_size_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from scipy import stats

from .make_hyp05_sample_size_gate import (
    ALPHA_FAMILY_WISE,
    ASSUMED_EFFECT_SIZE_COHENS_D,
    POWER,
    naive_single_test_n,
    sidak_corrected_n,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AUTHORED_AT = "2026-09-14"
OUT_PATH = LSE / f"HYP08_SAMPLE_SIZE_GATE_{AUTHORED_AT}.md"

#: Exact, not provisional -- see module docstring. Two preregistered
#: tests, fixed by this design, not discovered by measuring a synthetic
#: fixture's horizon-correlation structure (there is no horizon grid to
#: measure).
FAMILY_SIZE_K = 2


def sidak_critical_t(dof: float, *, k: int = FAMILY_SIZE_K,
                     alpha: float = ALPHA_FAMILY_WISE) -> float:
    """The Sidak-corrected two-sided critical t-value, at k effective
    tests and Satterthwaite dof, a real fit's |t_stat| must clear.

    Same alpha_sidak = 1-(1-alpha)^(1/k) transform `sidak_corrected_n`
    uses for POWER; this applies it to a t-distribution CRITICAL VALUE
    instead, for SIGNIFICANCE judgment on an already-observed fit. Falls
    back to the normal quantile (dof -> infinity behaviour) if dof is
    non-finite or absurdly large, mirroring how a Satterthwaite dof is
    already used elsewhere in this package.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1 (got {k!r})")
    alpha_sidak = 1.0 - (1.0 - alpha) ** (1.0 / k)
    if not (dof and dof == dof) or dof > 1e6:   # NaN or absurd dof
        return float(stats.norm.ppf(1.0 - alpha_sidak / 2.0))
    return float(stats.t.ppf(1.0 - alpha_sidak / 2.0, dof))


def operative_floor() -> dict[str, Any]:
    n = sidak_corrected_n(float(FAMILY_SIZE_K))
    return {
        "family_size_k": FAMILY_SIZE_K,
        "family_size_k_character": (
            "EXACT, not provisional and not borrowed -- two preregistered "
            "tests fixed by this design (the plain pooled same-session "
            "coefficient and the shock:is_competitor heterogeneity "
            "coefficient), not an empirically measured effective count "
            "over a correlated horizon grid, which does not exist here."),
        "operative_floor": round(n),
        "operative_floor_unit": "(peer, anchor-event) pairs, pooled across "
                                "both relationship types",
        "provisional": False,
        "why_not_provisional": (
            "Every prior hypothesis's k required measuring how adjacent "
            "horizons in a 20-point grid correlate under that specific "
            "target's geometry -- a real empirical question with its own "
            "uncertainty, which is why HYP-05/06/07 all borrowed a range "
            "rather than a point value. HYP-08's family size is fixed by "
            "its OWN design (exactly 2 tests, no horizon search), so k=2 "
            "is exact the moment this document is written, not an "
            "estimate awaiting its own measurement."),
    }


def build_report() -> dict[str, Any]:
    naive = naive_single_test_n()
    floor = operative_floor()
    return {
        "artifact": OUT_PATH.name,
        "hypothesis_id": "HYP-08",
        "what_this_is": (
            "HYP-08's sample-size gate. Unlike HYP-05/06/07's borrowed, "
            "explicitly provisional k range, this floor is exact for the "
            "reason given in operative_floor.why_not_provisional -- see "
            "the module's own docstring for the full derivation."),
        "governance_character": (
            "A GOVERNANCE ELIGIBILITY FLOOR, in the same sense as every "
            "prior hypothesis's own floor -- NOT a claim of guaranteed "
            "statistical power and NOT an estimate of detectable effect "
            "size."),
        "derivation_inputs": {
            "assumed_effect_size_cohens_d": ASSUMED_EFFECT_SIZE_COHENS_D,
            "assumed_effect_size_character": (
                "hypothetical, externally chosen, NOT derived from any "
                "observed project result -- reused unchanged from "
                "make_hyp05_sample_size_gate, same as every prior "
                "hypothesis's own gate."),
            "alpha_family_wise": ALPHA_FAMILY_WISE,
            "power": POWER,
            "multiplicity_correction": (
                "Sidak over k=2 EXACT preregistered tests -- same closed "
                "form every prior gate used, called with the true k for "
                "this design rather than a borrowed range."),
        },
        "naive_single_test_baseline": round(naive),
        "naive_single_test_baseline_note": (
            "LABELLED BASELINE ONLY. Never the operative floor."),
        "operative_floor": floor,
        "why_this_does_not_violate_the_power_statement": (
            "d=0.5, alpha=0.05, and power=0.80 are the same hypothetical, "
            "externally chosen inputs every prior gate in this project "
            "used -- not derived from any observed project result, real "
            "or synthetic-and-specific-to-HYP-08."),
    }


def render(report: dict[str, Any]) -> str:
    floor = report["operative_floor"]
    lines = [
        f"# {report['artifact']}",
        "",
        f"**{report['hypothesis_id']}** -- sample-size gate (k EXACT, not "
        "provisional -- see below).",
        "",
        report["what_this_is"],
        "",
        f"Naive single-test baseline (k=1, never the operative floor): "
        f"**{report['naive_single_test_baseline']}**.",
        "",
        f"Operative floor (k={floor['family_size_k']}, exact): "
        f"**{floor['operative_floor']} (peer, anchor-event) pairs**.",
        "",
        f"**Why k is exact, not provisional:** {floor['why_not_provisional']}",
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
