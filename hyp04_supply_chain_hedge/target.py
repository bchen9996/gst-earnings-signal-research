#!/usr/bin/env python3
"""Target-variable computation -- HYP-04 Phase 0, build step 2.

This is the one place a previous revision of the build spec carried a real
bug, so the corrected definition is stated here in full and asserted by
test_hyp04_supply_chain_hedge_target.py rather than merely documented.

THE TARGET (Patch 9, Round 3 correction):

    RVar(h)   = (1/h) * sum_{i=1..h} r_i^2       over [t+1, t+h]
    RVar_ref  = (1/20) * sum r_i^2               over the trailing 20 sessions
                                                  ending at the anchor's
                                                  earnings date (t=0)
    raw       = log(RVar(h)) - log(RVar_ref)
    target    = raw - earnings_cycle_baseline(peer, days_to_own_earnings)

Three properties of that definition matter, and each is load-bearing:

  1. RVar is a MEAN squared return, not a sum. The 1/h normalization is what
     makes horizons comparable. The rejected definition, RV(h) = sqrt(sum
     r_i^2), grows as sigma*sqrt(h) under constant volatility, so
     "RV(h) - reference" carried a deterministic sqrt(h)-shaped trend with
     no volatility content at all -- roughly -2.24*sigma at h=5 and ~0 at
     h=20. That is exactly the shape a lag profile exists to detect, so the
     unnormalized version manufactures a fake signal.

  2. It is a VARIANCE, not a volatility -- no square root. (1/h)*sum r^2 is
     unbiased for sigma^2 at every h. Square-rooting reintroduces a
     Jensen's-inequality downward bias that itself shrinks with h (worst at
     h=1, where E|r| ~ 0.80*sigma), which is a smaller version of the same
     h-indexed artifact.

  3. The comparison is a LOG RATIO, not a difference. This stabilizes
     variance across the grid and matches standard realized-volatility
     practice.

Residualization is applied on top of the log-ratio, not in place of it. Its
job is the OTHER confound: every company's volatility rises into its own
earnings regardless of any anchor, so without it the pipeline would
rediscover the earnings calendar and call it supply-chain transmission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .constants import (
    ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
    HORIZON_GRID,
    MIN_BUCKET_COUNT,
    MIN_RETAINED_HISTORY_FRACTION,
    REFERENCE_WINDOW_TRADING_DAYS,
    RVAR_LOG_FLOOR,
)
from .fixtures import SyntheticPanel, _days_to_next_earnings


def realized_variance(returns: np.ndarray) -> float:
    """RVar over a window = mean squared log return. Unbiased for sigma^2.

    Deliberately NOT sqrt(sum(r^2)) and NOT sum(r^2): see module docstring.
    """
    if returns.size == 0:
        return float("nan")
    return float(np.mean(np.square(returns)))


def log_rvar(returns: np.ndarray) -> float:
    """log(RVar), floored so an all-zero-return window cannot yield -inf.

    A day with an exact zero return (halted trading, stale or bad data) makes
    RVar exactly 0 at h=1 without this floor. The same floor is applied in
    the fixture path and the real-data path so behaviour matches.
    """
    rv = realized_variance(returns)
    if not np.isfinite(rv):
        return float("nan")
    return float(np.log(max(rv, RVAR_LOG_FLOOR)))


def raw_log_ratio_target(
    peer_returns: np.ndarray,
    anchor_day: int,
    horizon: int,
    *,
    reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
) -> float:
    """log(RVar(h)) - log(RVar_ref) for one (anchor event, peer, horizon).

    Post-event window is [anchor_day+1, anchor_day+h]; the reference window
    is the `reference_window` sessions ending AT the anchor day, so the two
    never overlap.
    """
    n = peer_returns.size
    start, stop = anchor_day + 1, anchor_day + 1 + horizon
    if stop > n:
        return float("nan")
    ref_start = max(0, anchor_day - reference_window + 1)
    if anchor_day + 1 - ref_start < reference_window:
        return float("nan")

    post = peer_returns[start:stop]
    ref = peer_returns[ref_start:anchor_day + 1]
    lp, lr = log_rvar(post), log_rvar(ref)
    if not (np.isfinite(lp) and np.isfinite(lr)):
        return float("nan")
    return lp - lr


@dataclass
class EarningsCycleBaseline:
    """Per-peer expected log-ratio as a function of days-to-own-earnings.

    Estimated on that peer's own history EXCLUDING anchor-adjacent windows,
    so the baseline is not contaminated by the very effect being measured.
    `retained_fraction` is the share of candidate pseudo-events that survived
    that exclusion -- a peer linked to several quarterly-reporting anchors can
    have most of its history excluded, which makes its baseline unreliable.
    That is a universe constraint in the same category as the options-coverage
    audit and is reported, never silently absorbed.
    """

    peer: str
    horizon: int
    bucket_means: dict[int, float]
    bucket_counts: dict[int, int]
    global_mean: float
    n_used: int
    n_candidates: int
    excluded_days: int

    @property
    def retained_fraction(self) -> float:
        if self.n_candidates == 0:
            return 0.0
        return self.n_used / self.n_candidates

    @property
    def min_bucket_count(self) -> int:
        return min(self.bucket_counts.values()) if self.bucket_counts else 0

    @property
    def retention_ok(self) -> bool:
        """Whether enough anchor-free history survived to estimate anything.

        Distinct from bucket population -- Patch 12 keeps these two numbers
        separate on purpose, and the status doc reports them separately.
        """
        return self.retained_fraction >= MIN_RETAINED_HISTORY_FRACTION

    def bucket_is_populated(self, days_to_own_earnings: float) -> bool:
        """Patch 12: is THIS observation's bucket populated enough to trust?

        Checked per observation rather than per peer. A peer can hold a
        well-populated far-from-earnings bucket and a nearly empty
        near-earnings one; excluding the whole peer would discard usable
        observations, and keeping the whole peer would silently fall back to
        the global mean exactly where the earnings ramp is steepest.
        """
        b = _dte_bucket(days_to_own_earnings)
        return self.bucket_counts.get(b, 0) >= MIN_BUCKET_COUNT

    def predict(self, days_to_own_earnings: float) -> float:
        return self.bucket_means.get(_dte_bucket(days_to_own_earnings), self.global_mean)


def _dte_bucket(days_to_own_earnings: float) -> int:
    """Coarse buckets over days-to-own-earnings.

    Buckets rather than a fitted curve: with a handful of quarters per peer,
    a flexible functional form would fit noise, which is the failure mode
    this project's history is most exposed to.
    """
    d = float(days_to_own_earnings)
    if d <= 2:
        return 0
    if d <= 5:
        return 1
    if d <= 10:
        return 2
    if d <= 21:
        return 3
    return 4


def estimate_earnings_cycle_baseline(
    peer: str,
    peer_returns: np.ndarray,
    peer_earnings_days: list[int],
    anchor_days: list[int],
    horizon: int,
    *,
    exclusion: int = ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
) -> EarningsCycleBaseline:
    """Estimate one peer's unconditional log-ratio vs. days-to-own-earnings.

    Sweeps pseudo-anchor days across the peer's history, drops any within
    `exclusion` sessions of a REAL anchor event, and averages the resulting
    raw log-ratios within days-to-own-earnings buckets.
    """
    n = peer_returns.size
    dte = _days_to_next_earnings(n, peer_earnings_days)
    excluded = np.zeros(n, dtype=bool)
    for a in anchor_days:
        lo, hi = max(0, a - exclusion), min(n, a + exclusion + 1)
        excluded[lo:hi] = True

    lo_day = REFERENCE_WINDOW_TRADING_DAYS
    hi_day = n - horizon - 1
    buckets: dict[int, list[float]] = {}
    n_used = n_candidates = 0

    for day in range(lo_day, max(lo_day, hi_day)):
        n_candidates += 1
        if excluded[day]:
            continue
        val = raw_log_ratio_target(peer_returns, day, horizon)
        if not np.isfinite(val):
            continue
        buckets.setdefault(_dte_bucket(dte[day]), []).append(val)
        n_used += 1

    bucket_means = {b: float(np.mean(v)) for b, v in buckets.items() if v}
    bucket_counts = {b: len(v) for b, v in buckets.items() if v}
    all_vals = [v for vals in buckets.values() for v in vals]
    global_mean = float(np.mean(all_vals)) if all_vals else 0.0

    return EarningsCycleBaseline(
        peer=peer,
        horizon=horizon,
        bucket_means=bucket_means,
        bucket_counts=bucket_counts,
        global_mean=global_mean,
        n_used=n_used,
        n_candidates=n_candidates,
        excluded_days=int(excluded.sum()),
    )


def build_feature_table(
    panel: SyntheticPanel,
    *,
    horizons: tuple[int, ...] = HORIZON_GRID,
    residualize: bool = True,
) -> dict[str, Any]:
    """Assemble the (anchor event x peer x horizon) panel Phase 0 analyses.

    Returns a dict of parallel numpy arrays rather than a DataFrame so the
    inference layer never has to guess at column dtypes, plus the per-peer
    baseline objects for retained-history reporting.

    `residualize=False` exists so a test can demonstrate that residualization
    is doing real work -- a pipeline that produced identical output with and
    without it would not actually be removing the earnings-cycle confound.
    """
    anchor_days_by_peer: dict[str, list[int]] = {}
    for ev in panel.anchor_events:
        for p in ev["peers"]:
            anchor_days_by_peer.setdefault(p, []).append(ev["anchor_day"])

    baselines: dict[tuple[str, int], EarningsCycleBaseline] = {}
    if residualize:
        for peer, returns in panel.returns.items():
            for h in horizons:
                baselines[(peer, h)] = estimate_earnings_cycle_baseline(
                    peer, returns, panel.peer_earnings_days[peer],
                    anchor_days_by_peer.get(peer, []), h,
                )

    dte_cache = {
        p: _days_to_next_earnings(panel.n_trading_days, panel.peer_earnings_days[p])
        for p in panel.returns
    }

    rows: dict[str, list] = {
        "event_id": [], "anchor": [], "peer": [], "horizon": [],
        "shock": [], "calendar_period": [], "anchor_day": [],
        "days_to_peer_earnings": [], "raw_target": [], "target": [],
    }

    n_candidate_obs = 0
    n_excluded_underpopulated_bucket = 0

    for ev_i, ev in enumerate(panel.anchor_events):
        for peer in ev["peers"]:
            returns = panel.returns[peer]
            for h in horizons:
                raw = raw_log_ratio_target(returns, ev["anchor_day"], h)
                if not np.isfinite(raw):
                    continue
                n_candidate_obs += 1
                dte_val = float(dte_cache[peer][ev["anchor_day"]])
                if residualize:
                    baseline = baselines[(peer, h)]
                    # Patch 12, accept-and-report: an observation whose
                    # days-to-own-earnings bucket is under-populated is treated
                    # as MISSING and dropped from the regression sample. Never
                    # imputed, never rescued by widening the bucket or lowering
                    # the threshold after seeing the surviving count.
                    if not baseline.bucket_is_populated(dte_val):
                        n_excluded_underpopulated_bucket += 1
                        continue
                    target = raw - baseline.predict(dte_val)
                else:
                    target = raw
                rows["event_id"].append(ev_i)
                rows["anchor"].append(ev["anchor"])
                rows["peer"].append(peer)
                rows["horizon"].append(h)
                rows["shock"].append(ev["shock"])
                rows["calendar_period"].append(ev["calendar_period"])
                rows["anchor_day"].append(ev["anchor_day"])
                rows["days_to_peer_earnings"].append(dte_val)
                rows["raw_target"].append(raw)
                rows["target"].append(target)

    table = {
        "event_id": np.asarray(rows["event_id"], dtype=int),
        "anchor": np.asarray(rows["anchor"], dtype=object),
        "peer": np.asarray(rows["peer"], dtype=object),
        "horizon": np.asarray(rows["horizon"], dtype=int),
        "shock": np.asarray(rows["shock"], dtype=float),
        "calendar_period": np.asarray(rows["calendar_period"], dtype=int),
        "anchor_day": np.asarray(rows["anchor_day"], dtype=int),
        "days_to_peer_earnings": np.asarray(rows["days_to_peer_earnings"], dtype=float),
        "raw_target": np.asarray(rows["raw_target"], dtype=float),
        "target": np.asarray(rows["target"], dtype=float),
    }

    low_retention = sorted({b.peer for b in baselines.values() if not b.retention_ok})
    retained = [b.retained_fraction for b in baselines.values()]
    bucket_mins = [b.min_bucket_count for b in baselines.values()]

    excluded_fraction = (
        n_excluded_underpopulated_bucket / n_candidate_obs if n_candidate_obs else 0.0
    )

    return {
        "table": table,
        "baselines": baselines,
        "residualized": residualize,
        # Patch 12 keeps these two numbers SEPARATE and the status doc reports
        # them separately. They measure different things and conflating them
        # would hide whichever is the binding constraint.
        "retained_history": {
            "what_it_measures": (
                "anchor-adjacent history removed from baseline ESTIMATION"
            ),
            "min": float(np.min(retained)) if retained else None,
            "mean": float(np.mean(retained)) if retained else None,
            "threshold": MIN_RETAINED_HISTORY_FRACTION,
            "peers_below_threshold": low_retention,
            "n_peers_below_threshold": len(low_retention),
            "n_peers": len(panel.returns),
            "structural_ceiling_note": (
                "Excluding +/-%d sessions around each anchor removes roughly "
                "(2*%d+1)/63 of a peer's calendar when anchors report quarterly, "
                "so retention has a structural ceiling near 0.20-0.30. The "
                "threshold is set below that ceiling by arithmetic, not tuned to "
                "the observed value."
                % (ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS,
                   ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS)
            ),
        },
        "bucket_population": {
            "what_it_measures": (
                "observations dropped because their days-to-own-earnings bucket "
                "was under-populated once that history was in hand"
            ),
            "min_bucket_count_threshold": MIN_BUCKET_COUNT,
            "min_bucket_count_observed": int(np.min(bucket_mins)) if bucket_mins else None,
            "n_candidate_observations": n_candidate_obs,
            "n_excluded": n_excluded_underpopulated_bucket,
            "excluded_fraction": excluded_fraction,
            "policy": (
                "accept-and-report (Patch 12 option c): excluded from the Stage 1 "
                "regression sample, not imputed. Buckets are NOT widened and the "
                "threshold is NOT lowered to recover sample size."
            ),
        },
    }


def horizon_trend_diagnostic(table: dict[str, np.ndarray]) -> dict[int, float]:
    """Mean target at each horizon.

    Under constant volatility with zero injected effect this must show no
    systematic trend across h. It is the direct regression diagnostic for the
    RV-normalization bug: the rejected sqrt(sum r^2) definition produces a
    monotone sqrt(h)-shaped ramp here even though nothing in the data varies
    with horizon.
    """
    out: dict[int, float] = {}
    for h in sorted(set(table["horizon"].tolist())):
        mask = table["horizon"] == h
        out[int(h)] = float(np.mean(table["target"][mask]))
    return out
