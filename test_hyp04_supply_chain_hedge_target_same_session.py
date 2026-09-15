#!/usr/bin/env python3
"""target_same_session.py / fixtures_same_session.py /
inference.fit_interaction_model tests.

Follows this repository's established testing convention: a hand-rolled
check() harness run directly as `python test_hyp04_*.py`. Offline.
Synthetic fixtures only. No provider, no network, no research artifact is
read.

  DIRECT ARITHMETIC CHECK (test_1) -- same_session_excess_return against a
  hand-computed value, not just against itself.

  BENCHMARK NEUTRALITY (test_2) -- if peer returns exactly EQUAL the
  benchmark's, the same-session excess return must be exactly 0, any
  shock sign/magnitude.

  FAIL-CLOSED (test_3) -- an out-of-range anchor_day or a NaN input
  session returns NaN, never a fabricated zero; a mismatched-length
  benchmark raises (caller error, not a data gap).

  RELATIONSHIP-TYPE VALIDATION (test_4) -- an unrecognized
  relationship_type refuses rather than silently defaulting to a side of
  the heterogeneity split; is_competitor is derived correctly for both
  recognized families.

  PLAIN POOLED RECOVERY (test_5) -- both relationship types given the
  SAME-SIGN injected effect (so pooling cannot cancel it out) recovers a
  significant, correctly-signed coefficient via
  inference.fit_local_projections(table, horizons=(0,)).

  HETEROGENEITY RECOVERY (test_6) -- customer/supplier given a POSITIVE
  injected effect, competitor given a NEGATIVE one (the a priori
  prediction) -- inference.fit_interaction_model recovers a positive,
  significant customer/supplier coefficient, a significant (negative)
  interaction term, and a negative implied competitor coefficient.

  ZERO-EFFECT NULL (test_7) -- neither the plain pooled fit nor the
  interaction fit is significant.

  SIGN-CONVENTION ALGEBRAIC PROOF (test_8) -- flipping every event's
  shock sign flips the recovered coefficients' signs and changes nothing
  else, bit-for-bit, for both fits.

Run directly: python test_hyp04_supply_chain_hedge_target_same_session.py
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
from scipy import stats  # noqa: E402

from hyp04_supply_chain_hedge.fixtures_same_session import (  # noqa: E402
    COMPETITOR_TYPE,
    CUSTOMER_SUPPLIER_TYPE,
    make_panel_same_session,
)
from hyp04_supply_chain_hedge.inference import (  # noqa: E402
    fit_interaction_model,
    fit_local_projections,
)
from hyp04_supply_chain_hedge.make_hyp08_sample_size_gate import (  # noqa: E402
    sidak_critical_t,
)
from hyp04_supply_chain_hedge.target_same_session import (  # noqa: E402
    TargetSameSessionError,
    build_feature_table_same_session,
    same_session_excess_return,
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

def test_1_matches_hand_computed_arithmetic() -> None:
    n = 40
    peer = np.zeros(n)
    bench = np.zeros(n)
    anchor_day = 20
    peer[anchor_day] = 0.03
    bench[anchor_day] = 0.01
    val = same_session_excess_return(peer, bench, anchor_day)
    expected = 0.03 - 1.0 * 0.01   # BENCHMARK_BETA default is 1.0
    check("1a. matches hand-computed value",
          abs(val - expected) < 1e-9, f"{val} vs {expected}")

    val2 = same_session_excess_return(peer, bench, anchor_day, benchmark_beta=0.0)
    check("1b. benchmark_beta=0 reduces to the raw peer return",
          abs(val2 - 0.03) < 1e-9, str(val2))


# --------------------------------------------------------------------------
# 2. benchmark neutrality
# --------------------------------------------------------------------------

def test_2_benchmark_neutrality() -> None:
    n = 80
    rng = np.random.default_rng(42)
    bench = rng.normal(0.0, 0.01, size=n)
    peer = bench.copy()
    for day in (10, 40, 70):
        val = same_session_excess_return(peer, bench, day)
        check(f"2a. day={day}, peer==bench -> exactly 0",
              val == 0.0, str(val))


# --------------------------------------------------------------------------
# 3. fail-closed
# --------------------------------------------------------------------------

def test_3_fail_closed() -> None:
    n = 40
    peer = np.zeros(n)
    bench = np.zeros(n)

    val = same_session_excess_return(peer, bench, 45)
    check("3a. anchor_day past the session index -> NaN",
          np.isnan(val), str(val))

    val2 = same_session_excess_return(peer, bench, -1)
    check("3b. negative anchor_day -> NaN",
          np.isnan(val2), str(val2))

    peer3 = np.zeros(n)
    peer3[15] = np.nan
    val3 = same_session_excess_return(peer3, bench, 15)
    check("3c. a NaN on the same-session return -> NaN, not silently skipped",
          np.isnan(val3), str(val3))

    try:
        same_session_excess_return(np.zeros(10), np.zeros(9), 3)
        check("3d. mismatched peer/benchmark length raises", False)
    except TargetSameSessionError:
        check("3d. mismatched peer/benchmark length raises", True)


# --------------------------------------------------------------------------
# 4. relationship-type validation
# --------------------------------------------------------------------------

def test_4_relationship_type_validation() -> None:
    panel = make_panel_same_session(
        "rel-type-check", n_anchors=4, n_quarters=6, n_peers_per_anchor=3,
        injected_effect_customer_supplier=0.0, injected_effect_competitor=0.0,
        seed=1)
    built = build_feature_table_same_session(panel)
    table = built["table"]
    check("4a. relationship_type column present",
          "relationship_type" in table)
    types = set(table["relationship_type"].tolist())
    check("4b. both real types appear",
          types == {CUSTOMER_SUPPLIER_TYPE, COMPETITOR_TYPE}, str(types))
    is_comp_for_comp_rows = table["is_competitor"][
        table["relationship_type"] == COMPETITOR_TYPE]
    is_comp_for_cs_rows = table["is_competitor"][
        table["relationship_type"] == CUSTOMER_SUPPLIER_TYPE]
    check("4c. is_competitor is 1.0 for every competitor row",
          bool(np.all(is_comp_for_comp_rows == 1.0)))
    check("4d. is_competitor is 0.0 for every customer/supplier row",
          bool(np.all(is_comp_for_cs_rows == 0.0)))

    bad_panel = copy.deepcopy(panel)
    bad_panel.anchor_events[0]["relationship_type"] = "joint_venture"
    try:
        build_feature_table_same_session(bad_panel)
        check("4e. an unrecognized relationship_type refuses", False)
    except TargetSameSessionError:
        check("4e. an unrecognized relationship_type refuses", True)


# --------------------------------------------------------------------------
# 5. plain pooled recovery (same-sign effect on both types)
# --------------------------------------------------------------------------

def test_5_plain_pooled_recovery() -> None:
    panel = make_panel_same_session(
        "pooled-recovery", n_anchors=16, n_quarters=16, n_peers_per_anchor=5,
        injected_effect_customer_supplier=6.0, injected_effect_competitor=6.0,
        seed=20260914)
    built = build_feature_table_same_session(panel)
    fits = fit_local_projections(built["table"], horizons=(0,),
                                 cluster_key="event_id")
    check("5a. exactly one fit is produced", len(fits) == 1, str(len(fits)))
    if not fits:
        return
    fit = fits[0]
    check("5b. recovered coefficient is POSITIVE", fit.beta > 0, str(fit.beta))
    crit = sidak_critical_t(fit.satterthwaite_dof)
    check("5c. clears the Sidak-corrected critical value",
          abs(fit.t_stat) > crit, f"|t|={abs(fit.t_stat)} crit={crit}")


# --------------------------------------------------------------------------
# 6. heterogeneity recovery (opposite-sign effect by type)
# --------------------------------------------------------------------------

def test_6_heterogeneity_recovery() -> None:
    panel = make_panel_same_session(
        "heterogeneity-recovery", n_anchors=16, n_quarters=16,
        n_peers_per_anchor=5, injected_effect_customer_supplier=6.0,
        injected_effect_competitor=-6.0, seed=20260914)
    built = build_feature_table_same_session(panel)
    fit = fit_interaction_model(built["table"], cluster_key="event_id")
    check("6a. a fit is produced", fit is not None)
    if fit is None:
        return
    check("6b. customer/supplier coefficient is POSITIVE",
          fit.beta_customer_supplier > 0, str(fit.beta_customer_supplier))
    crit_cs = sidak_critical_t(fit.dof_customer_supplier)
    check("6c. customer/supplier coefficient clears the critical value",
          abs(fit.t_customer_supplier) > crit_cs,
          f"|t|={abs(fit.t_customer_supplier)} crit={crit_cs}")
    crit_int = sidak_critical_t(fit.dof_interaction)
    check("6d. interaction (heterogeneity) term clears the critical value",
          abs(fit.t_interaction) > crit_int,
          f"|t|={abs(fit.t_interaction)} crit={crit_int}")
    check("6e. interaction term is NEGATIVE (competitor pulls away from "
          "customer/supplier, downward)",
          fit.beta_interaction < 0, str(fit.beta_interaction))
    check("6f. implied competitor coefficient is NEGATIVE",
          fit.beta_competitor_implied < 0, str(fit.beta_competitor_implied))
    check("6g. n splits correctly across both types",
          fit.n_customer_supplier > 0 and fit.n_competitor > 0
          and fit.n_customer_supplier + fit.n_competitor == fit.n_obs,
          f"{fit.n_customer_supplier} + {fit.n_competitor} vs {fit.n_obs}")


# --------------------------------------------------------------------------
# 7. zero-effect null
# --------------------------------------------------------------------------

def test_7_zero_effect_is_not_significant() -> None:
    panel = make_panel_same_session(
        "zero-effect", n_anchors=16, n_quarters=16, n_peers_per_anchor=5,
        injected_effect_customer_supplier=0.0, injected_effect_competitor=0.0,
        seed=20260914)
    built = build_feature_table_same_session(panel)

    fits = fit_local_projections(built["table"], horizons=(0,),
                                 cluster_key="event_id")
    check("7a. a plain fit is produced", len(fits) == 1, str(len(fits)))
    if fits:
        crit = sidak_critical_t(fits[0].satterthwaite_dof)
        check("7b. plain pooled fit is NOT significant",
              abs(fits[0].t_stat) <= crit,
              f"|t|={abs(fits[0].t_stat)} crit={crit}")

    ifit = fit_interaction_model(built["table"], cluster_key="event_id")
    check("7c. an interaction fit is produced", ifit is not None)
    if ifit is not None:
        crit_int = sidak_critical_t(ifit.dof_interaction)
        check("7d. interaction term is NOT significant",
              abs(ifit.t_interaction) <= crit_int,
              f"|t|={abs(ifit.t_interaction)} crit={crit_int}")


# --------------------------------------------------------------------------
# 8. sign-convention algebraic proof
# --------------------------------------------------------------------------

def test_8_flipping_shock_sign_flips_only_the_beta_signs() -> None:
    panel = make_panel_same_session(
        "sign-proof", n_anchors=16, n_quarters=16, n_peers_per_anchor=5,
        injected_effect_customer_supplier=6.0,
        injected_effect_competitor=-6.0, seed=20260914)
    built_a = build_feature_table_same_session(panel)

    flipped = copy.deepcopy(panel)
    for ev in flipped.anchor_events:
        ev["shock"] = -ev["shock"]
    built_b = build_feature_table_same_session(flipped)

    fits_a = fit_local_projections(built_a["table"], horizons=(0,),
                                   cluster_key="event_id")
    fits_b = fit_local_projections(built_b["table"], horizons=(0,),
                                   cluster_key="event_id")
    check("8a. both plain fits produced",
          len(fits_a) == 1 and len(fits_b) == 1)
    if fits_a and fits_b:
        fa, fb = fits_a[0], fits_b[0]
        check("8b. plain fit beta sign flips",
              np.sign(fa.beta) == -np.sign(fb.beta), f"{fa.beta} vs {fb.beta}")
        check("8c. plain fit |beta| unchanged",
              abs(fa.beta) == abs(fb.beta))
        check("8d. plain fit se unchanged", fa.se == fb.se)
        check("8e. plain fit satterthwaite_dof unchanged",
              fa.satterthwaite_dof == fb.satterthwaite_dof)

    ifit_a = fit_interaction_model(built_a["table"], cluster_key="event_id")
    ifit_b = fit_interaction_model(built_b["table"], cluster_key="event_id")
    check("8f. both interaction fits produced",
          ifit_a is not None and ifit_b is not None)
    if ifit_a is not None and ifit_b is not None:
        check("8g. customer/supplier coefficient sign flips",
              np.sign(ifit_a.beta_customer_supplier)
              == -np.sign(ifit_b.beta_customer_supplier))
        check("8h. interaction coefficient sign flips",
              np.sign(ifit_a.beta_interaction) == -np.sign(ifit_b.beta_interaction))
        check("8i. customer/supplier se unchanged",
              ifit_a.se_customer_supplier == ifit_b.se_customer_supplier)
        check("8j. interaction se unchanged",
              ifit_a.se_interaction == ifit_b.se_interaction)
        check("8k. n_obs/n_clusters unchanged",
              ifit_a.n_obs == ifit_b.n_obs
              and ifit_a.n_clusters == ifit_b.n_clusters)


def test_9_no_benchmark_series_refuses() -> None:
    panel = make_panel_same_session(
        "no-bench-check", n_anchors=2, n_quarters=3, n_peers_per_anchor=2,
        injected_effect_customer_supplier=0.0, injected_effect_competitor=0.0,
        seed=1)
    stripped = copy.deepcopy(panel)
    del stripped.returns["SPY"]
    try:
        build_feature_table_same_session(stripped)
        check("9a. a panel with no benchmark series refuses", False)
    except TargetSameSessionError as e:
        check("9a. a panel with no benchmark series refuses", True)
        check("9b. names the missing ticker", "SPY" in str(e), str(e))


def test_10_every_row_horizon_is_the_constant_zero() -> None:
    panel = make_panel_same_session(
        "horizon-constant", n_anchors=4, n_quarters=6, n_peers_per_anchor=3,
        injected_effect_customer_supplier=0.0, injected_effect_competitor=0.0,
        seed=2)
    built = build_feature_table_same_session(panel)
    check("10a. every row's horizon field is 0",
          bool(np.all(built["table"]["horizon"] == 0)))


def test_11_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("11a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("11a. network blocked", True)


if __name__ == "__main__":
    test_1_matches_hand_computed_arithmetic()
    test_2_benchmark_neutrality()
    test_3_fail_closed()
    test_4_relationship_type_validation()
    test_5_plain_pooled_recovery()
    test_6_heterogeneity_recovery()
    test_7_zero_effect_is_not_significant()
    test_8_flipping_shock_sign_flips_only_the_beta_signs()
    test_9_no_benchmark_series_refuses()
    test_10_every_row_horizon_is_the_constant_zero()
    test_11_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL TARGET_SAME_SESSION TESTS PASSED")
    sys.exit(0)
