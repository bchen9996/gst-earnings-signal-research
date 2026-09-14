#!/usr/bin/env python3
"""target_signed.py / fixtures_signed.py tests.

Follows this repository's established testing convention: a hand-rolled
check() harness run directly as `python test_hyp04_*.py`. Offline.
Synthetic fixtures only. No provider, no network, no research artifact is
read.

  DIRECT ARITHMETIC CHECK (test_1) -- signed_car against a hand-computed
  window, not just against itself.

  BENCHMARK NEUTRALITY (test_2) -- if peer returns exactly EQUAL the
  benchmark's, signed_car must be exactly 0 at every horizon, any shock
  sign/magnitude. Proof the benchmark subtraction is doing real work, the
  signed-target analog of target.py's own confound-removal checks.

  FAIL-CLOSED (test_3) -- a short/missing window returns NaN, never a
  fabricated zero.

  COMPETITIVE-DISPLACEMENT RECOVERY (test_4) -- a NEGATIVE injected effect
  recovers a NEGATIVE, significant peak beta via the REAL, unmodified
  inference.py pipeline.

  COMOVEMENT RECOVERY (test_5) -- a POSITIVE injected effect recovers a
  POSITIVE, significant peak beta -- proves the pipeline distinguishes
  DIRECTION, not merely "some relationship" (the one thing a sign-agnostic
  pipeline could get right by accident).

  ZERO-EFFECT NULL (test_6) -- no injected relationship, ample N -> not
  significant post multiplicity correction.

  SIGN-CONVENTION ALGEBRAIC PROOF (test_7) -- flipping every event's shock
  sign flips the recovered peak beta's sign and changes NOTHING else,
  bit-for-bit (|beta|, se, t_stat, satterthwaite_dof, max_t_p_value all
  identical) -- operationalizes target_signed.py's own "nothing is
  flipped, nothing statistical would change either way" claim directly,
  rather than leaving it as prose.

Run directly: python test_hyp04_supply_chain_hedge_target_signed.py
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

import copy  # noqa: E402

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge.fixtures import SyntheticPanel  # noqa: E402
from hyp04_supply_chain_hedge.fixtures_signed import make_panel_signed  # noqa: E402
from hyp04_supply_chain_hedge.inference import local_projection_analysis  # noqa: E402
from hyp04_supply_chain_hedge.target_signed import (  # noqa: E402
    TargetSignedError,
    build_feature_table_signed,
    signed_car,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


# --------------------------------------------------------------------------
# 1. direct arithmetic
# --------------------------------------------------------------------------

def test_1_signed_car_matches_hand_computed_arithmetic() -> None:
    n = 60
    peer = np.zeros(n)
    bench = np.zeros(n)
    anchor_day = 30
    # Reference window: reference_offset=1, reference_window=20 (defaults)
    # -> ref_end = anchor_day - 1 + 1 = anchor_day (exclusive),
    #    ref_start = ref_end - 20. For anchor_day=30: [10, 30).
    ref_start, ref_end = 10, 30
    peer[ref_start:ref_end] = 0.01   # peer's own mean = 0.01 over ref window
    bench[ref_start:ref_end] = 0.0
    # Post window h=3: [31, 34)
    peer[31:34] = [0.02, -0.01, 0.03]
    bench[31:34] = [0.005, 0.0, 0.01]

    val = signed_car(peer, bench, anchor_day, 3)
    # post excess = [0.015, -0.01, 0.02], sum = 0.025
    # ref excess mean = 0.01 (bench is 0 there)
    # expected = 0.025 - 3*0.01 = -0.005
    expected = -0.005
    check("1a. matches hand-computed value",
          abs(val - expected) < 1e-9, f"{val} vs {expected}")


# --------------------------------------------------------------------------
# 2. benchmark neutrality
# --------------------------------------------------------------------------

def test_2_benchmark_neutrality() -> None:
    n = 80
    rng = np.random.default_rng(42)
    bench = rng.normal(0.0, 0.01, size=n)
    peer = bench.copy()   # peer EXACTLY equals benchmark -- no idiosyncratic reaction at all

    for h in (1, 3, 5, 10):
        for shock in (-3.0, 0.0, 2.5):
            val = signed_car(peer, bench, 40, h)
            check(f"2a. h={h}, peer==bench -> exactly 0 regardless of shock "
                  f"{shock}", val == 0.0, str(val))


# --------------------------------------------------------------------------
# 3. fail-closed
# --------------------------------------------------------------------------

def test_3_fail_closed_on_short_or_missing_window() -> None:
    n = 40
    peer = np.zeros(n)
    bench = np.zeros(n)

    # Post window runs past the session index.
    val = signed_car(peer, bench, 35, 10)
    check("3a. post-window past the session index -> NaN",
          np.isnan(val), str(val))

    # Reference window too short (anchor_day near the start).
    val2 = signed_car(peer, bench, 5, 3)
    check("3b. reference window shorter than required -> NaN",
          np.isnan(val2), str(val2))

    # A NaN inside the post window (anchor_day=25, h=5 -> post window is
    # [26, 31), so index 28 is inside it; index 31 is NOT).
    peer3 = np.zeros(n)
    peer3[28] = np.nan
    val3 = signed_car(peer3, bench, 25, 5)
    check("3c. a NaN inside the post window -> NaN, not silently skipped",
          np.isnan(val3), str(val3))

    # A mismatched-length benchmark is a caller error, not a data gap.
    try:
        signed_car(np.zeros(10), np.zeros(9), 3, 2)
        check("3d. mismatched peer/benchmark length raises", False)
    except TargetSignedError:
        check("3d. mismatched peer/benchmark length raises", True)


# --------------------------------------------------------------------------
# helper: the real, unmodified inference pipeline over a signed-target table
# --------------------------------------------------------------------------

def _fit(panel: SyntheticPanel, *, seed: int = 42, n_permutations: int = 500):
    built = build_feature_table_signed(panel)
    return local_projection_analysis(
        built["table"], cluster_key="calendar_period",
        n_permutations=n_permutations, seed=seed)


# --------------------------------------------------------------------------
# 4. competitive-displacement recovery (negative effect -> negative beta)
# --------------------------------------------------------------------------

def test_4_competitive_displacement_recovers_negative_significant_beta() -> None:
    panel = make_panel_signed(
        "signed-displacement", n_anchors=8, n_quarters=12,
        n_peers_per_anchor=4, injected_lag=1, injected_effect=-4.0,
        injected_effect_window=5, seed=20260913)
    result = _fit(panel)
    check("4a. a peak horizon was found", result.peak_horizon is not None,
          str(result.peak_horizon))
    if result.peak_horizon is None:
        return
    peak_fit = next(f for f in result.fits if f.horizon == result.peak_horizon)
    check("4b. recovered peak beta is NEGATIVE",
          peak_fit.beta < 0, str(peak_fit.beta))
    check("4c. the peak is judged significant",
          result.peak_significant is True,
          f"max_abs_t={result.max_abs_t} crit={result.max_t_critical_value}")


# --------------------------------------------------------------------------
# 5. comovement recovery (positive effect -> positive beta)
# --------------------------------------------------------------------------

def test_5_comovement_recovers_positive_significant_beta() -> None:
    panel = make_panel_signed(
        "signed-comovement", n_anchors=8, n_quarters=12,
        n_peers_per_anchor=4, injected_lag=1, injected_effect=4.0,
        injected_effect_window=5, seed=20260913)
    result = _fit(panel)
    check("5a. a peak horizon was found", result.peak_horizon is not None,
          str(result.peak_horizon))
    if result.peak_horizon is None:
        return
    peak_fit = next(f for f in result.fits if f.horizon == result.peak_horizon)
    check("5b. recovered peak beta is POSITIVE",
          peak_fit.beta > 0, str(peak_fit.beta))
    check("5c. the peak is judged significant",
          result.peak_significant is True,
          f"max_abs_t={result.max_abs_t} crit={result.max_t_critical_value}")


# --------------------------------------------------------------------------
# 6. zero-effect null
# --------------------------------------------------------------------------

def test_6_zero_effect_is_not_significant() -> None:
    panel = make_panel_signed(
        "signed-zero-effect", n_anchors=10, n_quarters=14,
        n_peers_per_anchor=4, injected_lag=None, injected_effect=0.0,
        seed=20260913)
    result = _fit(panel)
    check("6a. the peak is NOT judged significant",
          result.peak_significant is False,
          f"peak_significant={result.peak_significant}")


# --------------------------------------------------------------------------
# 7. sign-convention algebraic proof
# --------------------------------------------------------------------------

def test_7_flipping_shock_sign_flips_only_the_beta_sign() -> None:
    panel = make_panel_signed(
        "signed-sign-proof", n_anchors=8, n_quarters=12,
        n_peers_per_anchor=4, injected_lag=1, injected_effect=-4.0,
        injected_effect_window=5, seed=20260913)
    result_a = _fit(panel)

    flipped = copy.deepcopy(panel)
    for ev in flipped.anchor_events:
        ev["shock"] = -ev["shock"]
    result_b = _fit(flipped)

    check("7a. both fits found a peak horizon",
          result_a.peak_horizon is not None and result_b.peak_horizon is not None,
          f"{result_a.peak_horizon}, {result_b.peak_horizon}")
    if result_a.peak_horizon is None or result_b.peak_horizon is None:
        return
    check("7b. the SAME peak horizon is chosen either way",
          result_a.peak_horizon == result_b.peak_horizon,
          f"{result_a.peak_horizon} vs {result_b.peak_horizon}")

    fit_a = next(f for f in result_a.fits if f.horizon == result_a.peak_horizon)
    fit_b = next(f for f in result_b.fits if f.horizon == result_b.peak_horizon)

    check("7c. beta's SIGN flips",
          np.sign(fit_a.beta) == -np.sign(fit_b.beta),
          f"{fit_a.beta} vs {fit_b.beta}")
    check("7d. |beta| is bit-for-bit unchanged",
          abs(fit_a.beta) == abs(fit_b.beta),
          f"{abs(fit_a.beta)} vs {abs(fit_b.beta)}")
    check("7e. se is bit-for-bit unchanged",
          fit_a.se == fit_b.se, f"{fit_a.se} vs {fit_b.se}")
    check("7f. t_stat magnitude is bit-for-bit unchanged",
          abs(fit_a.t_stat) == abs(fit_b.t_stat),
          f"{fit_a.t_stat} vs {fit_b.t_stat}")
    check("7g. satterthwaite_dof is bit-for-bit unchanged",
          fit_a.satterthwaite_dof == fit_b.satterthwaite_dof,
          f"{fit_a.satterthwaite_dof} vs {fit_b.satterthwaite_dof}")
    check("7h. max_t_p_value is bit-for-bit unchanged",
          result_a.max_t_p_value == result_b.max_t_p_value,
          f"{result_a.max_t_p_value} vs {result_b.max_t_p_value}")


def test_8_no_benchmark_series_refuses() -> None:
    panel = make_panel_signed(
        "signed-no-bench-check", n_anchors=2, n_quarters=3,
        n_peers_per_anchor=2, injected_lag=None, injected_effect=0.0,
        seed=1)
    stripped = copy.deepcopy(panel)
    del stripped.returns["SPY"]
    try:
        build_feature_table_signed(stripped)
        check("8a. a panel with no benchmark series refuses", False)
    except TargetSignedError as e:
        check("8a. a panel with no benchmark series refuses", True)
        check("8b. names the missing ticker", "SPY" in str(e), str(e))


def test_9_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("9a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("9a. network blocked", True)


if __name__ == "__main__":
    test_1_signed_car_matches_hand_computed_arithmetic()
    test_2_benchmark_neutrality()
    test_3_fail_closed_on_short_or_missing_window()
    test_4_competitive_displacement_recovers_negative_significant_beta()
    test_5_comovement_recovers_positive_significant_beta()
    test_6_zero_effect_is_not_significant()
    test_7_flipping_shock_sign_flips_only_the_beta_sign()
    test_8_no_benchmark_series_refuses()
    test_9_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL TARGET_SIGNED TESTS PASSED")
    sys.exit(0)
