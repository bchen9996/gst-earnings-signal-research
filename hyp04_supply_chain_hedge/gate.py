#!/usr/bin/env python3
"""Phase 0 sample-size gate -- HYP-04, build step 3b.

THE GATE MEASURES SAMPLE SIZE. IT DOES NOT MEASURE EFFECT SIZE.

That distinction is the whole point of Patch 10's two-fixture design, and the
tests enforce it in both directions:

  * Fixture A -- zero injected effect, ample N -> gate PASSES. A zero-effect
    sample with plenty of observations is a well-powered study that found
    nothing, which is a legitimate and informative outcome. A gate that failed
    here would be wired to the wrong quantity.
  * Fixture B -- insufficient N, large injected effect -> gate FAILS. A strong
    effect cannot buy its way past a sample-size gate.

FORMULA (Patch 2, Round 2 + Round 3 corrections):

    DEFF  = 1 + (m_bar - 1) * ICC          ICC floored at 0 HERE ONLY
    N_eff = N_pairs / DEFF

N_pairs and N_events are the two bounds -- N_pairs assumes ICC = 0, N_events
assumes ICC = 1 -- and neither is gated on directly. Only N_eff is.

An earlier revision of the plan stated the gate in anchor events AND asked for
a separate design-effect adjustment, which applies the clustering correction
twice and leaves the ICC estimate decorative. This formulation uses the ICC
exactly once, to move N_eff between its two bounds.

ICC FLOORING. ICC estimates come out negative with few clusters -- a known
small-sample artifact. An unfloored negative ICC pushes DEFF below 1 and makes
N_eff EXCEED N_pairs, which is backwards for what a design effect represents.
The floor applies only inside the DEFF arithmetic; the raw estimate is always
reported alongside, so a gate riding on a noisy ICC is visible rather than
implicit.

MULTIPLICITY TARGET. Not hardcoded. Derived from the effective number of
independent horizon tests that step 3b's max-T permutation actually measured
(`inference.max_t_permutation` -> `effective_independent_tests`). The naive
single-test 126 appears only as a labelled baseline; 190-240 is a provisional
placeholder that the measured number supersedes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from scipy import stats

from .clustered_se import intraclass_correlation
from .constants import (
    ALPHA,
    ASSUMED_COHENS_D,
    ICC_FLOOR,
    NAIVE_SINGLE_TEST_N,
    PROVISIONAL_MULTIPLICITY_TARGET_N,
    Z_POWER,
)


def required_n_for_k_tests(
    k_effective_tests: float,
    *,
    d: float = ASSUMED_COHENS_D,
    alpha: float = ALPHA,
    z_power: float = Z_POWER,
) -> dict[str, Any]:
    """Total N needed at effect size d, controlling family-wise error over k tests.

    Sidak rather than Bonferroni: alpha_per_test = 1 - (1 - alpha)^(1/k). The
    horizons are heavily correlated by construction (RVar(h) is a mean over an
    expanding window), so Bonferroni would be badly over-conservative -- and k
    here is already the EFFECTIVE number of independent tests measured by the
    permutation, not the raw horizon count.

    ESTIMATOR MISMATCH, stated rather than papered over: this is a two-sample
    Cohen's-d calculation, while the analysis actually run is a continuous LP
    regression. Dichotomizing a continuous predictor costs efficiency, so this
    is a deliberately CONSERVATIVE proxy, not an exact match. Recorded here and
    in the status doc rather than silently reconciled.
    """
    if not np.isfinite(k_effective_tests) or k_effective_tests < 1.0:
        k_effective_tests = 1.0
    alpha_per_test = 1.0 - (1.0 - alpha) ** (1.0 / k_effective_tests)
    z = float(stats.norm.ppf(1.0 - alpha_per_test / 2.0))
    n_per_group = 2.0 * (z + z_power) ** 2 / (d ** 2)
    return {
        "k_effective_tests": float(k_effective_tests),
        "alpha_family_wise": alpha,
        "alpha_per_test_sidak": float(alpha_per_test),
        "z_critical": z,
        "assumed_cohens_d": d,
        "n_per_group": float(n_per_group),
        "total_n_required": float(2.0 * n_per_group),
        "estimator_mismatch_note": (
            "Two-sample Cohen's-d power calc used as a stated CONSERVATIVE "
            "PROXY for the continuous LP regression actually run. Not "
            "reconciled into an exact match."
        ),
    }


@dataclass
class GateResult:
    n_pairs: int
    n_events: int
    mean_peers_per_event: float
    icc_raw: float
    icc_floored: float
    icc_n_clusters: int
    icc_bootstrap_ci: Optional[tuple[float, float]]
    deff: float
    n_eff: float
    target_n: float
    passed: bool
    k_effective_tests: float
    satterthwaite_dof: Optional[float] = None
    naive_single_test_baseline: int = NAIVE_SINGLE_TEST_N
    provisional_placeholder: tuple[int, int] = PROVISIONAL_MULTIPLICITY_TARGET_N
    detail: dict[str, Any] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        return {
            "gate_passed": self.passed,
            "gated_on": "N_eff (never N_pairs or N_events directly)",
            "n_pairs_icc0_bound": self.n_pairs,
            "n_events_icc1_bound": self.n_events,
            "mean_peers_per_event": round(self.mean_peers_per_event, 4),
            "icc_raw_unfloored": self.icc_raw,
            "icc_used_in_deff_floored_at_0": self.icc_floored,
            "icc_n_clusters": self.icc_n_clusters,
            "icc_bootstrap_ci_95": self.icc_bootstrap_ci,
            "deff": round(self.deff, 4),
            "n_eff": round(self.n_eff, 2),
            "target_n_fixture_derived": round(self.target_n, 1),
            "k_effective_independent_tests": round(self.k_effective_tests, 3),
            "satterthwaite_dof": self.satterthwaite_dof,
            "naive_single_test_baseline": self.naive_single_test_baseline,
            "naive_baseline_note": "LABELLED BASELINE ONLY -- never the operative gate.",
            "provisional_placeholder_range": list(self.provisional_placeholder),
            "provisional_placeholder_note": (
                "Superseded by target_n_fixture_derived, which comes from the "
                "measured effective-independent-test count."
            ),
            **self.detail,
        }


def _bootstrap_icc_ci(
    values: np.ndarray,
    cluster: np.ndarray,
    *,
    n_boot: int = 300,
    seed: int = 42,
) -> Optional[tuple[float, float]]:
    """Cluster bootstrap around the ICC.

    Resamples WHOLE CLUSTERS with replacement, not individual rows -- an
    observation-level bootstrap would break the very clustering the ICC is
    measuring and report a spuriously tight interval.
    """
    clusters = np.unique(cluster)
    if clusters.size < 4:
        return None
    rng = np.random.default_rng(seed)
    idx_by_cluster = {int(c): np.flatnonzero(cluster == c) for c in clusters}
    out: list[float] = []
    for _ in range(n_boot):
        drawn = rng.choice(clusters, size=clusters.size, replace=True)
        rows, labels = [], []
        for j, c in enumerate(drawn):
            ix = idx_by_cluster[int(c)]
            rows.append(ix)
            labels.append(np.full(ix.size, j))
        rows = np.concatenate(rows)
        labels = np.concatenate(labels)
        est = intraclass_correlation(values[rows], labels)["icc_raw"]
        if np.isfinite(est):
            out.append(est)
    if len(out) < 20:
        return None
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def evaluate_gate(
    table: dict[str, np.ndarray],
    *,
    k_effective_tests: float,
    reference_horizon: int = 5,
    satterthwaite_dof: Optional[float] = None,
    bootstrap_icc: bool = True,
    seed: int = 42,
) -> GateResult:
    """Evaluate the N_eff gate on a built feature table.

    N_pairs is counted at ONE horizon, not summed across the grid. Each
    (anchor event, peer) contributes a single observation; counting every
    horizon row would inflate N_pairs ~20x and turn the gate into a
    formality that any dataset clears.
    """
    mask = table["horizon"] == reference_horizon
    if mask.sum() == 0:
        horizons = np.unique(table["horizon"])
        reference_horizon = int(horizons[0])
        mask = table["horizon"] == reference_horizon

    y = table["target"][mask]
    events = table["event_id"][mask]

    n_pairs = int(mask.sum())
    n_events = int(np.unique(events).size)
    m_bar = (n_pairs / n_events) if n_events else 0.0

    icc_info = intraclass_correlation(y, events)
    icc_raw = float(icc_info["icc_raw"])
    icc_floored = max(ICC_FLOOR, icc_raw) if np.isfinite(icc_raw) else ICC_FLOOR

    deff = 1.0 + (m_bar - 1.0) * icc_floored
    deff = max(deff, 1.0)          # cannot fall below 1 by construction
    n_eff = n_pairs / deff if deff > 0 else float("nan")

    power = required_n_for_k_tests(k_effective_tests)
    target = power["total_n_required"]

    ci = None
    if bootstrap_icc:
        ci = _bootstrap_icc_ci(y, events, seed=seed)

    return GateResult(
        n_pairs=n_pairs,
        n_events=n_events,
        mean_peers_per_event=m_bar,
        icc_raw=icc_raw,
        icc_floored=float(icc_floored),
        icc_n_clusters=int(icc_info["n_clusters"]),
        icc_bootstrap_ci=ci,
        deff=float(deff),
        n_eff=float(n_eff),
        target_n=float(target),
        passed=bool(np.isfinite(n_eff) and n_eff >= target),
        k_effective_tests=float(k_effective_tests),
        satterthwaite_dof=satterthwaite_dof,
        detail={
            "reference_horizon": int(reference_horizon),
            "n_pairs_counted_at": "a single horizon (not summed across the grid)",
            "power_calculation": power,
            "satterthwaite_vs_neff_note": (
                "Where Satterthwaite dof and N_eff diverge, the Satterthwaite "
                "dof is the more honest number: it reflects the clustering "
                "structure inference actually used, which DEFF's single "
                "clustering dimension does not capture."
            ),
        },
    )
