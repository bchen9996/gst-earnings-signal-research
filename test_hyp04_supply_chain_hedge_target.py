#!/usr/bin/env python3
"""Target-variable and residualization tests -- HYP-04 Phase 0.

Follows this repository's established testing convention: a hand-rolled
check()/skip() harness run directly as `python test_hyp04_*.py`, matching
test_market_response_*.py. This repo uses no pytest anywhere -- CI globs test
files and executes them directly -- so a pytest-based suite would not run.

Offline. Synthetic fixtures only. No provider, no network, no research
artifact is read.

Run directly: python test_hyp04_supply_chain_hedge_target.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge.constants import (  # noqa: E402
    MIN_BUCKET_COUNT,
    RVAR_LOG_FLOOR,
)
from hyp04_supply_chain_hedge.fixtures import (  # noqa: E402
    make_constant_vol_fixture,
    make_main_fixture,
    make_panel,
)
from hyp04_supply_chain_hedge.target import (  # noqa: E402
    _dte_bucket,
    build_feature_table,
    estimate_earnings_cycle_baseline,
    horizon_trend_diagnostic,
    log_rvar,
    raw_log_ratio_target,
    realized_variance,
)

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


# ---------------------------------------------------------------- 1. RVar definition
def test_1_rvar_is_a_normalized_variance() -> None:
    """RVar(h) = (1/h)*sum(r^2): a MEAN squared return, not a sum, no sqrt."""
    rng = np.random.default_rng(0)
    sigma = 0.02
    r = rng.normal(0.0, sigma, size=200_000)

    # Unbiased for sigma^2 at every h -- the property the sqrt version lacks.
    worst = 0.0
    for h in (1, 5, 20):
        est = float(np.mean([realized_variance(r[i:i + h])
                             for i in range(0, 100_000, h)]))
        worst = max(worst, abs(est / sigma ** 2 - 1.0))
    check("1a. RVar is unbiased for sigma^2 across h (max rel err "
          f"{worst:.4f})", worst < 0.02)

    # It is explicitly the mean, not the sum.
    x = np.array([0.1, 0.2, 0.3])
    check("1b. RVar is the MEAN squared return, not the sum",
          abs(realized_variance(x) - float(np.mean(x ** 2))) < 1e-15
          and abs(realized_variance(x) - float(np.sum(x ** 2))) > 1e-9)

    # No square root anywhere: RVar of a constant-|r| series equals r^2.
    y = np.full(10, 0.05)
    check("1c. RVar returns a variance, not a volatility",
          abs(realized_variance(y) - 0.05 ** 2) < 1e-15)


def test_2_log_floor_prevents_negative_infinity() -> None:
    """A halted/stale session with an exact zero return must not yield -inf."""
    z = np.zeros(5)
    check("2a. log_rvar of an all-zero window is finite", np.isfinite(log_rvar(z)))
    check("2b. and it equals log(floor)",
          abs(log_rvar(z) - float(np.log(RVAR_LOG_FLOOR))) < 1e-12)
    single_zero = np.array([0.0])
    check("2c. h=1 with a single zero return is finite too",
          np.isfinite(log_rvar(single_zero)))


# ---------------------------------------------------------------- 3. the h-trend regression test
def test_3_no_systematic_h_trend_under_constant_vol() -> None:
    """THE regression test for the RV-normalization bug.

    Asserted as a CONTRAST that shrinks with sample size, not as an absolute
    tolerance. The rejected definition RV(h)=sqrt(sum r^2) carries a
    DETERMINISTIC sqrt(h) trend that no amount of data removes; the corrected
    log(RVar) definition's residual trend is sampling noise and shrinks like
    1/sqrt(N). An absolute threshold could be satisfied by tuning; this
    contrast cannot.
    """
    def corrected_range(n_anchors, n_quarters, n_peers):
        panel = make_panel(
            f"CV_{n_anchors}_{n_quarters}_{n_peers}",
            n_anchors=n_anchors, n_quarters=n_quarters,
            n_peers_per_anchor=n_peers, injected_lag=None, injected_effect=0.0,
            earnings_ramp_amplitude=0.0, base_vol_range=(0.02, 0.02), seed=7)
        tr = horizon_trend_diagnostic(build_feature_table(panel)["table"])
        hs = np.array(sorted(tr), dtype=float)
        vals = np.array([tr[h] for h in sorted(tr)])
        m = hs >= 3          # h=1,2 are log-chi2 pathological; excluded by design
        return float(vals[m].max() - vals[m].min()), panel

    def rejected_range(panel):
        from hyp04_supply_chain_hedge.constants import REFERENCE_WINDOW_TRADING_DAYS
        means = {}
        for h in range(3, 21):
            acc = []
            for ev in panel.anchor_events:
                for p in ev["peers"]:
                    ret = panel.returns[p]
                    d = ev["anchor_day"]
                    if d + 1 + h > ret.size:
                        continue
                    rs = max(0, d - REFERENCE_WINDOW_TRADING_DAYS + 1)
                    acc.append(float(np.sqrt(np.sum(ret[d + 1:d + 1 + h] ** 2))
                                     - np.sqrt(np.sum(ret[rs:d + 1] ** 2))))
            if acc:
                means[h] = float(np.mean(acc)) / 0.02   # in vol units
        vals = np.array(list(means.values()))
        return float(vals.max() - vals.min())

    small_rng, small_panel = corrected_range(6, 6, 4)
    large_rng, large_panel = corrected_range(24, 20, 8)
    rej_small = rejected_range(small_panel)
    rej_large = rejected_range(large_panel)

    check(f"3a. corrected target's h-trend SHRINKS with N "
          f"({small_rng:.4f} -> {large_rng:.4f})", large_rng < small_rng * 0.6,
          "if this fails the target has an N-independent (deterministic) trend")
    check(f"3b. rejected sqrt(sum r^2) trend does NOT shrink "
          f"({rej_small:.3f} -> {rej_large:.3f})",
          abs(rej_large - rej_small) < 0.25 * rej_small,
          "the rejected definition must stay biased, or this test proves nothing")
    check(f"3c. rejected trend is far larger than corrected at the same N "
          f"({rej_large:.3f} vs {large_rng:.4f})", rej_large > 10 * large_rng)


# ---------------------------------------------------------------- 4. window construction
def test_4_windows_do_not_overlap_and_respect_bounds() -> None:
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.02, size=200)
    val = raw_log_ratio_target(r, anchor_day=100, horizon=5)
    check("4a. a well-formed window returns a finite target", np.isfinite(val))

    # CHANGED BY REGISTRY v1.10, and the flip is the point. The post window is
    # [t+1, t+h]; the reference window now ends at t-1, so session t -- the
    # session the anchor's earnings news is attributed to -- is in NEITHER. It
    # used to end AT t, which put the peer's own response session inside the
    # baseline that response is measured against.
    post_expected = log_rvar(r[101:106])
    ref_expected = log_rvar(r[80:100])
    check("4b. target equals log(RVar_post) - log(RVar_ref), day 0 in NEITHER",
          abs(val - (post_expected - ref_expected)) < 1e-12)
    check("4b2. the reference window ends the session BEFORE the anchor day",
          abs(val - (post_expected - log_rvar(r[81:101]))) > 1e-9,
          "it still ends AT the anchor day -- the v1.10 change is not in force")
    check("4b3. and it is still exactly 20 sessions long, not 19",
          r[80:100].size == 20, str(r[80:100].size))

    # The ROBUSTNESS variant reproduces the pre-v1.10 arithmetic exactly, which
    # is what keeps the superseded specification reportable rather than lost.
    old_val = raw_log_ratio_target(r, anchor_day=100, horizon=5,
                                   reference_offset=0)
    check("4b4. reference_offset=0 reproduces the superseded window",
          abs(old_val - (post_expected - log_rvar(r[81:101]))) < 1e-12)

    check("4c. refuses when the post window runs off the end",
          not np.isfinite(raw_log_ratio_target(r, anchor_day=198, horizon=10)))
    check("4d. refuses when the reference window is short",
          not np.isfinite(raw_log_ratio_target(r, anchor_day=3, horizon=5)))
    # The new window needs exactly ONE more session of history at the left edge.
    check("4e. day 19 is short under the new window but was usable under the old",
          not np.isfinite(raw_log_ratio_target(r, anchor_day=19, horizon=1))
          and np.isfinite(raw_log_ratio_target(r, anchor_day=19, horizon=1,
                                               reference_offset=0)))
    check("4f. day 20 is the earliest usable anchor day now",
          np.isfinite(raw_log_ratio_target(r, anchor_day=20, horizon=1)))


# ---------------------------------------------------------------- 5. residualization leakage
def test_5_residualization_excludes_anchor_adjacent_windows() -> None:
    """Assert exclusion HAPPENS, not merely that it is documented."""
    panel = make_panel("LEAK", n_anchors=4, n_quarters=8, n_peers_per_anchor=3,
                       injected_lag=5, injected_effect=0.6, seed=13)
    anchor_days_by_peer: dict[str, list[int]] = {}
    for ev in panel.anchor_events:
        for p in ev["peers"]:
            anchor_days_by_peer.setdefault(p, []).append(ev["anchor_day"])

    peer = sorted(panel.returns)[0]
    anchors = anchor_days_by_peer[peer]
    excl = 25
    b = estimate_earnings_cycle_baseline(
        peer, panel.returns[peer], panel.peer_earnings_days[peer],
        anchors, horizon=10, exclusion=excl)

    check("5a. some history is actually excluded", b.excluded_days > 0)
    check("5b. retained fraction is strictly below 1", b.retained_fraction < 1.0)

    # A wider exclusion must retain strictly less -- proves the parameter binds.
    wide = estimate_earnings_cycle_baseline(
        peer, panel.returns[peer], panel.peer_earnings_days[peer],
        anchors, horizon=10, exclusion=excl * 2)
    check("5c. a wider exclusion window retains strictly less history",
          wide.retained_fraction < b.retained_fraction,
          f"{wide.retained_fraction:.3f} vs {b.retained_fraction:.3f}")

    # And with no anchors at all, nothing is excluded.
    none_excluded = estimate_earnings_cycle_baseline(
        peer, panel.returns[peer], panel.peer_earnings_days[peer],
        [], horizon=10, exclusion=excl)
    check("5d. with zero anchors, zero history is excluded",
          none_excluded.excluded_days == 0
          and none_excluded.retained_fraction == 1.0)


def test_6_retained_history_and_bucket_population_reported_separately() -> None:
    """Patch 12 keeps these two numbers distinct; conflating them hides which binds."""
    built = build_feature_table(make_constant_vol_fixture())
    rh = built["retained_history"]
    bp = built["bucket_population"]

    check("6a. retained-history block is present with its own threshold",
          "min" in rh and "threshold" in rh)
    check("6b. bucket-population block is present and separate",
          "excluded_fraction" in bp and "min_bucket_count_threshold" in bp)
    check("6c. the two blocks describe different things",
          rh["what_it_measures"] != bp["what_it_measures"])
    check("6d. bucket exclusions are counted, not silently dropped",
          bp["n_excluded"] >= 0 and bp["n_candidate_observations"] > 0)
    check("6e. excluded_fraction is consistent with its own counts",
          abs(bp["excluded_fraction"]
              - bp["n_excluded"] / bp["n_candidate_observations"]) < 1e-12)


def test_7_underpopulated_buckets_are_excluded_not_imputed() -> None:
    """Patch 12 option (c): drop the observation, never impute a value."""
    built = build_feature_table(make_main_fixture())
    table = built["table"]
    baselines = built["baselines"]

    # Every surviving row's bucket must have cleared MIN_BUCKET_COUNT.
    violations = 0
    for i in range(min(3000, table["target"].size)):
        b = baselines[(table["peer"][i], int(table["horizon"][i]))]
        if not b.bucket_is_populated(float(table["days_to_peer_earnings"][i])):
            violations += 1
    check(f"7a. no surviving row relies on an under-populated bucket "
          f"(violations={violations})", violations == 0)

    check("7b. some rows were in fact excluded on this fixture",
          built["bucket_population"]["n_excluded"] > 0,
          "if zero, the check is not being exercised at all")
    check("7c. threshold is the preregistered constant, not a local literal",
          built["bucket_population"]["min_bucket_count_threshold"] == MIN_BUCKET_COUNT)

    check("7d. no NaN survives into the regression sample",
          bool(np.all(np.isfinite(table["target"]))))


def test_8_residualization_actually_changes_the_target() -> None:
    """A pipeline that produced identical output with and without
    residualization would not be removing the earnings-cycle confound."""
    panel = make_panel("RESID", n_anchors=8, n_quarters=10, n_peers_per_anchor=4,
                       injected_lag=None, injected_effect=0.0,
                       earnings_ramp_amplitude=0.8, seed=17)
    with_r = build_feature_table(panel, residualize=True)["table"]
    without = build_feature_table(panel, residualize=False)["table"]

    check("8a. residualization is not a no-op",
          abs(float(np.mean(with_r["target"])) - float(np.mean(without["target"]))) > 1e-6)

    # The raw target still carries the earnings ramp; the residualized one
    # should be closer to zero mean at the horizons where the ramp bites.
    check("8b. residualized target has smaller mean magnitude than raw",
          abs(float(np.mean(with_r["target"]))) < abs(float(np.mean(without["target"]))),
          f"{np.mean(with_r['target']):+.5f} vs {np.mean(without['target']):+.5f}")

    check("8c. raw_target is preserved alongside the residualized target",
          "raw_target" in with_r and with_r["raw_target"].size == with_r["target"].size)


def test_9_dte_buckets_are_fixed_and_monotone() -> None:
    """Bucket boundaries are preregistered; Patch 12 forbids widening them later."""
    check("9a. bucket index is non-decreasing in days-to-earnings",
          all(_dte_bucket(d) <= _dte_bucket(d + 1) for d in range(0, 60)))
    check("9b. near-earnings days occupy their own narrow buckets",
          _dte_bucket(0) == 0 and _dte_bucket(2) == 0 and _dte_bucket(4) == 1)
    check("9c. far-from-earnings collapses into a single tail bucket",
          _dte_bucket(30) == _dte_bucket(60) == 4)


if __name__ == "__main__":
    test_1_rvar_is_a_normalized_variance()
    test_2_log_floor_prevents_negative_infinity()
    test_3_no_systematic_h_trend_under_constant_vol()
    test_4_windows_do_not_overlap_and_respect_bounds()
    test_5_residualization_excludes_anchor_adjacent_windows()
    test_6_retained_history_and_bucket_population_reported_separately()
    test_7_underpopulated_buckets_are_excluded_not_imputed()
    test_8_residualization_actually_changes_the_target()
    test_9_dte_buckets_are_fixed_and_monotone()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 TARGET TESTS PASSED")
    sys.exit(0)
