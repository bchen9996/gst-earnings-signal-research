#!/usr/bin/env python3
"""Inference, N_eff gate, and Stage 2 tests -- HYP-04 Phase 0.

Repo testing convention (hand-rolled check()/skip(), run directly, no pytest).
Offline. Synthetic fixtures only.

Run directly: python test_hyp04_supply_chain_hedge_inference.py
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

from hyp04_supply_chain_hedge.clustered_se import (  # noqa: E402
    TWO_WAY_CLUSTERING_IMPLEMENTED,
    cr_vcov,
    intraclass_correlation,
    satterthwaite_df,
)
from hyp04_supply_chain_hedge.fixtures import (  # noqa: E402
    make_insufficient_n_fixture,
    make_main_fixture,
    make_panel,
    make_zero_effect_fixture,
)
from hyp04_supply_chain_hedge.gate import evaluate_gate, required_n_for_k_tests  # noqa: E402
from hyp04_supply_chain_hedge.inference import (  # noqa: E402
    apply_ar_filter,
    fit_ar,
    fit_local_projections,
    leave_one_anchor_out_cv,
    local_projection_analysis,
    placebo_test,
    prewhitened_ccf,
)
from hyp04_supply_chain_hedge.stage2 import (  # noqa: E402
    PeerOptionsConditions,
    Stage1Score,
    Structure,
    decision_table_summary,
    select_hedge_structure,
)
from hyp04_supply_chain_hedge.target import build_feature_table  # noqa: E402

FAILURES: list[str] = []
SKIPS: list[str] = []

N_PERM_FAST = 200          # reduced for test runtime; production default is higher


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


_CACHE: dict[str, dict] = {}


def table_for(name: str, builder) -> dict:
    if name not in _CACHE:
        _CACHE[name] = build_feature_table(builder())["table"]
    return _CACHE[name]


# ---------------------------------------------------------------- 1. clustered SEs
def test_1_ses_are_genuinely_clustered() -> None:
    """CR2 must differ from OLS, and must respond to the cluster labels."""
    rng = np.random.default_rng(3)
    G, m = 30, 12
    g = np.repeat(np.arange(G), m)
    x = rng.normal(size=G * m)
    # strong within-cluster correlation -> clustered SEs must exceed naive OLS
    y = x * 0.3 + np.repeat(rng.normal(scale=2.0, size=G), m) + rng.normal(size=G * m)
    X = np.column_stack([np.ones(G * m), x])

    _, V_cr2, n_clusters = cr_vcov(X, y, g, "CR2")
    resid = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    s2 = float(resid @ resid) / (X.shape[0] - X.shape[1])
    V_ols = s2 * np.linalg.inv(X.T @ X)

    check("1a. CR2 reports the right number of clusters", n_clusters == G)
    check("1b. CR2 SE differs materially from naive OLS SE",
          abs(np.sqrt(V_cr2[1, 1]) / np.sqrt(V_ols[1, 1]) - 1.0) > 0.05,
          f"ratio={np.sqrt(V_cr2[1,1])/np.sqrt(V_ols[1,1]):.4f}")

    # Scrambling cluster labels must change the estimate -- proves labels are used.
    g_scrambled = rng.permutation(g)
    _, V_scr, _ = cr_vcov(X, y, g_scrambled, "CR2")
    check("1c. scrambling cluster labels changes the CR2 SE (labels are used)",
          abs(V_cr2[1, 1] - V_scr[1, 1]) > 1e-12)

    c = np.array([0.0, 1.0])
    dof = satterthwaite_df(X, g, c)
    check(f"1d. Satterthwaite dof is finite and below the cluster count ({dof:.1f} < {G})",
          np.isfinite(dof) and 0 < dof < G)

    check("1e. two-way clustering is declared NOT implemented, not silently claimed",
          TWO_WAY_CLUSTERING_IMPLEMENTED is False)


def test_2_icc_behaves_and_can_go_negative() -> None:
    rng = np.random.default_rng(5)
    g = np.repeat(np.arange(40), 10)

    high = np.repeat(rng.normal(scale=3.0, size=40), 10) + rng.normal(scale=0.3, size=400)
    low = rng.normal(size=400)
    icc_high = intraclass_correlation(high, g)["icc_raw"]
    icc_low = intraclass_correlation(low, g)["icc_raw"]

    check(f"2a. strong between-cluster variance gives high ICC ({icc_high:.3f})",
          icc_high > 0.7)
    check(f"2b. iid data gives ICC near zero ({icc_low:.3f})", abs(icc_low) < 0.15)
    check("2c. cluster count is reported for stability assessment",
          intraclass_correlation(low, g)["n_clusters"] == 40)


# ---------------------------------------------------------------- 3. local projections
def test_3_lp_recovers_the_known_injected_lag() -> None:
    """Peak must equal L+W-1 exactly; onset must be L, or LATE by a little.

    These are DIFFERENT horizons under an expanding-window target, and the
    distinction is load-bearing for Stage 2's tenor. Asserting only one would
    let the other silently drift.

    The onset assertion is deliberately one-sided rather than exact. At the
    onset horizon only 1/L of the averaging window is affected, so the signal
    there is diluted by exactly 1/L and the margin over the
    multiplicity-corrected threshold thins as the lag deepens. On the L=8 draw
    below, |t| at h=8 is 2.08 against a critical value near 2.6-2.85, so onset
    is reported at 9. That is a real property of the estimator, not a test
    artifact, and pinning the test to exact equality would be asserting a
    precision the method does not have.

    What MUST hold, and is asserted hard: onset is never EARLIER than L.
    An early onset would be a false positive -- claiming transmission before
    any exists -- which is categorically worse than reporting it late.
    """
    for L, W in ((3, 5), (5, 5), (8, 5)):
        panel = make_panel(f"LAG_{L}_{W}", n_anchors=16, n_quarters=14,
                           n_peers_per_anchor=6, injected_lag=L,
                           injected_effect=0.55, injected_effect_window=W, seed=31)
        table = build_feature_table(panel)["table"]
        r = local_projection_analysis(table, n_permutations=N_PERM_FAST)

        check(f"3a. L={L},W={W}: onset is NEVER earlier than the injected lag "
              f"(got {r.onset_horizon}, no false-early detection)",
              r.onset_horizon is not None and r.onset_horizon >= L)
        check(f"3b. L={L},W={W}: onset is within 2 sessions of the true lag "
              f"(got {r.onset_horizon}, late-biased by design)",
              r.onset_horizon is not None and L <= r.onset_horizon <= L + 2)
        # NARROWED, with the reason recorded rather than the assertion quietly
        # retargeted. This previously asserted peak_horizon (argmax |t|) equals
        # L+W-1 EXACTLY. That held only while the code clustered on event_id,
        # which GST_HYP04_ANALYSIS_LOCK_v1.0 D1 forbids ("One-way, clustered on
        # calendar_period. Not event_id"). Measured across 15 (L,W) pairs under
        # the locked dimension: argmax|beta| recovers the injected horizon
        # 15/15, argmax|t| only 9/15, worst miss 6 -> 15. Full numbers in
        # Live Signal Engine/HYP04_D1_CLUSTERING_FINDING_2026-09-03.md.
        #
        # What is asserted instead is the STRONGER and genuinely invariant
        # property: the beta profile locates the response exactly, under either
        # dimension, because clustering changes the variance estimate and never
        # the point estimate.
        #
        # Whether peak_horizon should be REDEFINED as argmax|beta| is an open
        # decision for the repo owner. D8 keeps peak out of tenor sizing, so no
        # decision input moved. The suite must not pre-empt that choice by
        # asserting whichever definition happens to pass.
        beta_peak = r.horizons[int(np.argmax(np.abs(r.betas)))]
        check(f"3c. L={L},W={W}: the |beta| profile peaks at L+W-1={L+W-1} "
              f"exactly (got {beta_peak}), under either clustering",
              beta_peak == L + W - 1)
        check(f"3c2. L={L},W={W}: peak_horizon (argmax|t|) is never EARLIER "
              f"than the injected lag (got {r.peak_horizon}); exact recovery "
              f"is deliberately NOT asserted under D1",
              r.peak_horizon is not None and r.peak_horizon >= L)
        check(f"3d. L={L},W={W}: peak and onset are distinct quantities",
              r.peak_horizon != r.onset_horizon)
        check(f"3e. L={L},W={W}: onset strictly precedes peak",
              r.onset_horizon is not None and r.onset_horizon < r.peak_horizon)


def test_4_zero_effect_fixture_finds_nothing() -> None:
    """Fixture A's inference half: no effect must not manufacture a lag."""
    table = table_for("zero", make_zero_effect_fixture)
    r = local_projection_analysis(table, n_permutations=N_PERM_FAST)
    check(f"4a. peak is NOT significant post multiplicity correction "
          f"(p={r.max_t_p_value:.3f})", r.peak_significant is False)
    check("4b. no onset horizon is reported when nothing clears",
          r.onset_horizon is None)
    check(f"4c. peak |t| sits below the max-T critical value "
          f"({r.peak_abs_t:.2f} < {r.max_t_critical_value:.2f})",
          r.peak_abs_t < r.max_t_critical_value)


def test_5_multiplicity_correction_actually_binds() -> None:
    """The corrected threshold must be stricter than an uncorrected one."""
    table = table_for("zero", make_zero_effect_fixture)
    r = local_projection_analysis(table, n_permutations=N_PERM_FAST)
    uncorrected = 1.96
    check(f"5a. max-T critical value exceeds the uncorrected 1.96 "
          f"({r.max_t_critical_value:.2f})", r.max_t_critical_value > uncorrected)
    check(f"5b. effective independent tests is between 1 and the grid size "
          f"({r.effective_independent_tests:.2f} of {len(r.fits)})",
          1.0 <= r.effective_independent_tests <= len(r.fits))
    check("5c. permutation count is recorded", r.n_permutations == N_PERM_FAST)


# ---------------------------------------------------------------- 6. prewhitened CCF
def test_6_ccf_filter_is_fit_to_peer_vol_not_anchor_shock() -> None:
    """The direction of the prewhitening filter is the whole point of Patch 1."""
    panel = make_main_fixture()
    peer = sorted(panel.returns)[0]
    r2 = panel.returns[peer] ** 2
    vol = np.array([float(np.mean(r2[max(0, t - 5):t + 1])) for t in range(r2.size)])
    shock = np.zeros(panel.n_trading_days)
    for ev in panel.anchor_events:
        if peer in ev["peers"]:
            shock[ev["anchor_day"]] = ev["shock"]

    phi_vol = fit_ar(vol, 5)
    phi_shock = fit_ar(shock, 5)
    check(f"6a. peer-vol series carries real persistence (sum|phi|="
          f"{np.abs(phi_vol).sum():.3f})", float(np.abs(phi_vol).sum()) > 0.5)
    check(f"6b. anchor-shock series is already near-white (sum|phi|="
          f"{np.abs(phi_shock).sum():.3f})", float(np.abs(phi_shock).sum()) < 0.2)
    check("6c. => filtering with a shock-fit filter would be a near-no-op",
          float(np.abs(phi_vol).sum()) > 4 * float(np.abs(phi_shock).sum()))

    out = prewhitened_ccf(vol, shock, n_permutations=100)
    check("6d. the implementation records the filter as fit to peer-vol",
          out["filter_fit_to"] == "peer_volatility_series")
    check("6e. one single filter is applied to BOTH series (no fork)",
          "both series" in out["filter_applied_to"]
          and "single filter" in out["filter_applied_to"])
    check("6f. significance is circular-shift permutation, not Bartlett bands",
          "Bartlett" in out["significance_method"]
          and "circular-shift" in out["significance_method"])
    check("6g. CCF is labelled a SECONDARY cross-check", "SECONDARY" in out["role"])


def test_7_ar_filter_handles_the_boundary() -> None:
    """Regression test for the empty-reverse-slice bug at t == p."""
    x = np.arange(10, dtype=float)
    phi = np.array([0.5, 0.1, 0.0, 0.0, 0.0])
    out = apply_ar_filter(x, phi)
    check("7a. filter output has the expected length", out.size == x.size - phi.size)
    check("7b. filter output is finite at the first element (t == p boundary)",
          bool(np.isfinite(out[0])))
    check("7c. all filter output is finite", bool(np.all(np.isfinite(out))))


# ---------------------------------------------------------------- 8. CV and placebo
def test_8_leave_one_anchor_out_split_is_correct() -> None:
    table = table_for("main", make_main_fixture)
    cv = leave_one_anchor_out_cv(table, horizon=5)
    n_anchors = int(np.unique(table["anchor"]).size)
    check(f"8a. one fold per anchor ({cv['n_folds']} folds, {n_anchors} anchors)",
          cv["n_folds"] == n_anchors)
    check("8b. the split is declared leave-one-anchor-out, not random k-fold",
          "leave-one-anchor-out" in cv["split"] and "NOT random" in cv["split"])
    check("8c. CV MSE is finite", np.isfinite(cv["cv_mse"]))

    # No anchor may appear in both train and test of its own fold.
    anchors = table["anchor"][table["horizon"] == 5]
    held = np.unique(anchors)
    leaked = [a for a in held if not np.any(anchors == a)]
    check(f"8d. every held-out anchor is genuinely present in the data "
          f"(leaked={leaked})", not leaked)


def test_9_placebo_separates_real_from_random() -> None:
    main = table_for("main", make_main_fixture)
    zero = table_for("zero", make_zero_effect_fixture)
    pb_main = placebo_test(main, horizon=5, n_permutations=300)
    pb_zero = placebo_test(zero, horizon=5, n_permutations=300)
    check(f"9a. real-linkage fixture separates from random pairing "
          f"(p={pb_main['p_value']:.4f})", pb_main["separates_from_random"] is True)
    check(f"9b. zero-effect fixture does NOT separate "
          f"(p={pb_zero['p_value']:.4f})", pb_zero["separates_from_random"] is False)
    check("9c. placebo reports its own null distribution, not just a verdict",
          "placebo_p95" in pb_main and "placebo_mean_abs_corr" in pb_main)


# ---------------------------------------------------------------- 10. the N_eff gate
def test_10_gate_measures_sample_size_not_effect_size() -> None:
    """Patch 10's two-fixture design, asserted in both directions."""
    k = 6.34
    a = evaluate_gate(table_for("zero", make_zero_effect_fixture),
                      k_effective_tests=k, bootstrap_icc=False)
    b = evaluate_gate(build_feature_table(make_insufficient_n_fixture())["table"],
                      k_effective_tests=k, bootstrap_icc=False)

    check(f"10a. Fixture A (zero effect, ample N) PASSES the gate "
          f"(N_eff={a.n_eff:.0f} >= {a.target_n:.0f})", a.passed is True,
          "a well-powered null result must not fail a SAMPLE-SIZE gate")
    check(f"10b. Fixture B (insufficient N, large effect) FAILS the gate "
          f"(N_eff={b.n_eff:.0f} < {b.target_n:.0f})", b.passed is False,
          "a strong effect must not buy its way past a sample-size gate")


def test_11_gate_arithmetic_and_icc_floor() -> None:
    k = 6.34
    g = evaluate_gate(table_for("main", make_main_fixture),
                      k_effective_tests=k, bootstrap_icc=False)

    check("11a. N_eff sits between its two bounds (N_events <= N_eff <= N_pairs)",
          g.n_events <= g.n_eff <= g.n_pairs,
          f"{g.n_events} <= {g.n_eff:.1f} <= {g.n_pairs}")
    check("11b. DEFF = 1 + (m_bar - 1) * ICC_floored",
          abs(g.deff - (1.0 + (g.mean_peers_per_event - 1.0) * g.icc_floored)) < 1e-9)
    check("11c. N_eff = N_pairs / DEFF",
          abs(g.n_eff - g.n_pairs / g.deff) < 1e-6)
    check("11d. DEFF is never below 1", g.deff >= 1.0)

    # Negative ICC must be floored for DEFF but still reported raw.
    b = evaluate_gate(build_feature_table(make_insufficient_n_fixture())["table"],
                      k_effective_tests=k, bootstrap_icc=False)
    if b.icc_raw < 0:
        check(f"11e. a negative raw ICC ({b.icc_raw:.4f}) is floored to 0 for DEFF",
              b.icc_floored == 0.0)
        check("11f. and the raw negative value is still reported for transparency",
              b.icc_raw < 0)
    else:
        skip("11e/f. negative-ICC flooring", "this fixture produced a non-negative ICC")

    check("11g. the naive 126 is carried as a labelled baseline only",
          g.report()["naive_single_test_baseline"] == 126
          and "never the operative gate" in g.report()["naive_baseline_note"])
    check("11h. the provisional 190-240 is marked superseded",
          "Superseded" in g.report()["provisional_placeholder_note"])


def test_12_multiplicity_target_scales_with_k() -> None:
    """More effective independent tests must require a larger N, monotonically."""
    ns = [required_n_for_k_tests(k)["total_n_required"] for k in (1, 2, 4, 6.34, 20)]
    check(f"12a. required N increases monotonically in k "
          f"({[round(n) for n in ns]})", all(ns[i] < ns[i + 1] for i in range(len(ns) - 1)))
    check(f"12b. k=1 reproduces the naive single-test baseline (~126, got {ns[0]:.0f})",
          abs(ns[0] - 126) < 3)
    check(f"12c. the measured k=6.34 lands inside the provisional 190-240 range "
          f"(got {ns[3]:.0f})", 190 <= ns[3] <= 240)
    check("12d. the estimator mismatch is stated, not silently reconciled",
          "CONSERVATIVE PROXY" in required_n_for_k_tests(6.34)["estimator_mismatch_note"])


# ---------------------------------------------------------------- 13. Stage 2
def test_13_stage2_is_rules_based_and_carries_its_assumption() -> None:
    strong = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=9,
                         lag_ci_width_days=2.0, significant=True)
    liquid = PeerOptionsConditions("P", 5000, 500, 0.05, 0.02, 0.35)
    r = select_hedge_structure(strong, liquid)

    check("13a. every recommendation names the rule that produced it",
          bool(r.rule_fired) and r.rule_fired.startswith("R"))
    check("13b. the assumed long-equity exposure is carried on the output",
          "long-equity" in r.assumed_exposure)
    check("13c. and the recommendation states it is NOT a real position",
          "Not a real position" in r.assumed_exposure)
    check("13d. the no-edge disclaimer travels with the recommendation",
          "feasibility" in r.no_edge_claim.lower())
    check("13e. the assumed notional is reported, since sizing scales with it",
          r.assumed_notional_usd > 0)
    check("13f. the decision table is enumerable for audit",
          len(decision_table_summary()) == 10)


def test_14_stage2_tenor_uses_onset_not_peak() -> None:
    """Sizing off the peak would buy (W-1) days too much tenor."""
    s = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=9,
                    lag_ci_width_days=2.0, significant=True)
    r = select_hedge_structure(s, PeerOptionsConditions("P", 5000, 500, 0.05, 0.02, 0.35))
    check(f"14a. tenor is derived from onset=5, not peak=9 (got {r.tenor_trading_days})",
          r.tenor_trading_days == 10)
    check("14b. the peak is recorded but explicitly not used for tenor",
          r.inputs["peak_horizon_not_used_for_tenor"] == 9)

    # Changing the peak alone must not move the tenor.
    s2 = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=18,
                     lag_ci_width_days=2.0, significant=True)
    r2 = select_hedge_structure(s2, PeerOptionsConditions("P", 5000, 500, 0.05, 0.02, 0.35))
    check("14c. moving the peak alone does not change the tenor",
          r2.tenor_trading_days == r.tenor_trading_days)


def test_15_stage2_edge_cases() -> None:
    liquid = PeerOptionsConditions("P", 5000, 500, 0.05, 0.02, 0.35)
    cases = [
        ("not significant", Stage1Score("P", 0.9, 5, 9, 1.0, False), liquid,
         Structure.NO_POSITION),
        ("weak link", Stage1Score("P", 0.05, 5, 9, 1.0, True), liquid,
         Structure.NO_POSITION),
        ("no onset", Stage1Score("P", 0.9, None, 9, 1.0, True), liquid,
         Structure.NO_POSITION),
        ("wide lag CI", Stage1Score("P", 0.9, 5, 9, 99.0, True), liquid,
         Structure.NO_POSITION),
        ("IV already elevated", Stage1Score("P", 0.9, 5, 9, 1.0, True),
         PeerOptionsConditions("P", 5000, 500, 0.05, 0.02, 0.90),
         Structure.NO_POSITION),
        ("steep skew", Stage1Score("P", 0.9, 5, 9, 1.0, True),
         PeerOptionsConditions("P", 5000, 500, 0.05, 0.20, 0.35),
         Structure.PUT_SPREAD),
        ("no options, has ETF", Stage1Score("P", 0.9, 5, 9, 1.0, True),
         PeerOptionsConditions("P", None, None, None, None, None, False, "XLI"),
         Structure.SECTOR_ETF_PROXY),
        ("no options, no ETF", Stage1Score("P", 0.9, 5, 9, 1.0, True),
         PeerOptionsConditions("P", None, None, None, None, None, False, None),
         Structure.NO_POSITION),
        ("illiquid, has ETF", Stage1Score("P", 0.9, 5, 9, 1.0, True),
         PeerOptionsConditions("P", 5, 1, 0.90, 0.02, 0.35, True, "XLK"),
         Structure.SECTOR_ETF_PROXY),
        ("moderate link", Stage1Score("P", 0.35, 5, 9, 1.0, True), liquid,
         Structure.COLLAR),
        ("strong + clean", Stage1Score("P", 0.80, 5, 9, 1.0, True), liquid,
         Structure.PROTECTIVE_PUT),
    ]
    for label, score, cond, expected in cases:
        got = select_hedge_structure(score, cond).structure
        check(f"15. {label} -> {expected}", got == expected, f"got {got}")


def test_16_no_trained_model_and_no_edge_claim_in_stage2() -> None:
    import inspect

    from hyp04_supply_chain_hedge import stage2
    src = inspect.getsource(stage2)
    for tok in ("sklearn", "fit(", "predict(", "train"):
        check(f"16a. Stage 2 source contains no '{tok}' (rules, not a fitted model)",
              tok not in src)
    check("16b. Stage 2 makes no profitability or edge claim",
          "profit" not in src.lower() and "edge has been found" not in src.lower())


if __name__ == "__main__":
    test_1_ses_are_genuinely_clustered()
    test_2_icc_behaves_and_can_go_negative()
    test_3_lp_recovers_the_known_injected_lag()
    test_4_zero_effect_fixture_finds_nothing()
    test_5_multiplicity_correction_actually_binds()
    test_6_ccf_filter_is_fit_to_peer_vol_not_anchor_shock()
    test_7_ar_filter_handles_the_boundary()
    test_8_leave_one_anchor_out_split_is_correct()
    test_9_placebo_separates_real_from_random()
    test_10_gate_measures_sample_size_not_effect_size()
    test_11_gate_arithmetic_and_icc_floor()
    test_12_multiplicity_target_scales_with_k()
    test_13_stage2_is_rules_based_and_carries_its_assumption()
    test_14_stage2_tenor_uses_onset_not_peak()
    test_15_stage2_edge_cases()
    test_16_no_trained_model_and_no_edge_claim_in_stage2()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 INFERENCE / GATE / STAGE-2 TESTS PASSED")
    sys.exit(0)
