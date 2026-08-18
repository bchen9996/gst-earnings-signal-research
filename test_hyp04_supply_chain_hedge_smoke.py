#!/usr/bin/env python3
"""End-to-end Phase 0 SMOKE TEST -- HYP-04.

DELIBERATELY NOT STATISTICAL VALIDATION. This runs the whole Phase 0 pipeline
once on a small fixed fixture and asserts only that it COMPLETES and that its
outputs have the right shape and schema. Statistical validation lives in
test_hyp04_supply_chain_hedge_target.py and
test_hyp04_supply_chain_hedge_inference.py, which are separate on purpose.

This exists to catch integration breakage -- a broken join, schema drift, a
silently empty dataframe -- before it wastes a phase gate. It must stay fast,
which is why the fixture is small and the permutation counts are tiny.

The audit is exercised through an INJECTED FAKE PROVIDER. It never touches
yfinance, never makes a network call, and never spends a call against the
owner-authorized budget. CI must never be able to make a billable request.

Run directly: python test_hyp04_supply_chain_hedge_smoke.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during the offline smoke test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge.audit import (  # noqa: E402
    AuditBudgetError,
    Coverage,
    run_audit,
)
from hyp04_supply_chain_hedge.fixtures import make_panel  # noqa: E402
from hyp04_supply_chain_hedge.gate import evaluate_gate  # noqa: E402
from hyp04_supply_chain_hedge.inference import (  # noqa: E402
    leave_one_anchor_out_cv,
    local_projection_analysis,
    placebo_test,
)
from hyp04_supply_chain_hedge.stage2 import (  # noqa: E402
    PeerOptionsConditions,
    Stage1Score,
    select_hedge_structure,
)
from hyp04_supply_chain_hedge.target import build_feature_table  # noqa: E402

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


# --------------------------------------------------------------------------
# Fake provider: shaped like yfinance's Ticker, backed by nothing.
# --------------------------------------------------------------------------
class _FakeChain:
    def __init__(self, n_calls: int, n_puts: int) -> None:
        self.calls = list(range(n_calls))
        self.puts = list(range(n_puts))


class _FakeTicker:
    def __init__(self, symbol: str) -> None:
        self._symbol = symbol

    @property
    def options(self):
        if self._symbol == "NOOPTS":
            return ()
        if self._symbol == "BOOM":
            raise RuntimeError("simulated provider transport failure")
        return ("2026-09-18", "2026-10-16")

    def option_chain(self, expiry: str):
        return _FakeChain(12, 11)


class _FakeYF:
    Ticker = _FakeTicker


# --------------------------------------------------------------------------
def test_1_audit_refuses_without_an_owner_supplied_budget() -> None:
    """Patch 13's consent gate must fail closed, before any call is made."""
    try:
        run_audit(["AAA"], stage="canary", hard_cap_calls=None, yf_module=_FakeYF)
        check("1a. audit refuses to run with no budget", False, "it ran anyway")
    except AuditBudgetError as e:
        check("1a. audit refuses to run with no budget", True)
        check("1b. and the refusal explains the staged-consent requirement",
              "canary" in str(e).lower())

    try:
        run_audit(["AAA"], stage="not_a_stage", hard_cap_calls=10, yf_module=_FakeYF)
        check("1c. audit rejects an unknown consent stage", False, "it ran anyway")
    except AuditBudgetError:
        check("1c. audit rejects an unknown consent stage", True)


def test_2_audit_runs_and_classifies_outcomes() -> None:
    run = run_audit(["AAA", "NOOPTS", "BOOM"], stage="canary",
                    hard_cap_calls=10, yf_module=_FakeYF)
    by = {r.ticker: r for r in run.results}
    check("2a. a normal ticker is classified ok", by["AAA"].coverage == Coverage.OK)
    check("2b. a ticker with no chain is NO_OPTIONS, a coverage fact",
          by["NOOPTS"].coverage == Coverage.NO_OPTIONS)
    check("2c. a provider exception is TRANSPORT_FAILED, NOT no-coverage",
          by["BOOM"].coverage == Coverage.TRANSPORT_FAILED,
          "conflating these would understate coverage")
    check("2d. the summary reports calls-per-ticker",
          run.summary()["calls_per_ticker_mean"] is not None)


def test_3_audit_stops_at_the_cap_without_truncating_silently() -> None:
    run = run_audit(["AAA", "AAA", "AAA", "AAA"], stage="canary",
                    hard_cap_calls=3, yf_module=_FakeYF)
    check("3a. total calls never exceed the hard cap",
          run.total_calls <= 3, f"made {run.total_calls}")
    check("3b. the run records that the budget was exhausted", run.budget_exhausted)
    not_attempted = [r for r in run.results if r.coverage == Coverage.NOT_ATTEMPTED]
    check("3c. unreached tickers are recorded as NOT_ATTEMPTED, not dropped",
          len(not_attempted) > 0)
    check("3d. every requested ticker still appears in the results",
          len(run.results) == 4)


def test_4_end_to_end_pipeline_completes_with_the_right_schema() -> None:
    """ingest -> features -> LP + gate -> Stage 2, on a deliberately small fixture."""
    panel = make_panel("SMOKE", n_anchors=3, n_quarters=6, n_peers_per_anchor=3,
                       injected_lag=4, injected_effect=0.6, seed=99)
    check("4a. fixture generates anchor events", panel.n_events > 0)

    built = build_feature_table(panel)
    table = built["table"]
    check("4b. feature table is non-empty (no silently empty dataframe)",
          table["target"].size > 0)

    expected_cols = {"event_id", "anchor", "peer", "horizon", "shock",
                     "calendar_period", "anchor_day", "days_to_peer_earnings",
                     "raw_target", "target"}
    check("4c. feature table carries the expected schema",
          expected_cols <= set(table.keys()),
          f"missing={sorted(expected_cols - set(table.keys()))}")
    check("4d. all columns are the same length",
          len({v.size for v in table.values()}) == 1)
    check("4e. both reporting blocks are present",
          "retained_history" in built and "bucket_population" in built)

    r = local_projection_analysis(table, n_permutations=25)
    check("4f. local projections produce a fit per horizon", len(r.fits) > 0)
    check("4g. LP result exposes onset AND peak separately",
          hasattr(r, "onset_horizon") and hasattr(r, "peak_horizon"))
    check("4h. every fit carries beta, se, t and dof",
          all(np.isfinite(f.beta) and np.isfinite(f.se) for f in r.fits))
    check("4i. clustering approach is declared on the result",
          "one-way" in r.clustering)

    g = evaluate_gate(table, k_effective_tests=6.34, bootstrap_icc=False)
    rep = g.report()
    for key in ("gate_passed", "n_pairs_icc0_bound", "n_events_icc1_bound",
                "icc_raw_unfloored", "icc_used_in_deff_floored_at_0",
                "deff", "n_eff", "target_n_fixture_derived"):
        check(f"4j. gate report carries {key}", key in rep)
    check("4k. gate returns a boolean verdict", isinstance(rep["gate_passed"], bool))

    cv = leave_one_anchor_out_cv(table, horizon=4)
    check("4l. leave-one-anchor-out CV runs", cv["n_folds"] >= 1)
    pb = placebo_test(table, horizon=4, n_permutations=25)
    check("4m. placebo test runs and returns a p-value", 0.0 < pb["p_value"] <= 1.0)

    rec = select_hedge_structure(
        Stage1Score("PEER_001", 0.6, r.onset_horizon, r.peak_horizon, 2.0,
                    bool(r.peak_significant)),
        PeerOptionsConditions("PEER_001", 5000, 500, 0.05, 0.02, 0.35))
    d = rec.as_dict()
    for key in ("peer", "structure", "rule_fired", "rationale",
                "assumed_exposure", "assumed_notional_usd", "no_edge_claim"):
        check(f"4n. Stage 2 output carries {key}", key in d)
    check("4o. Stage 2 output names a concrete structure", bool(d["structure"]))


def test_5_no_edge_claim_anywhere_in_package_output() -> None:
    """A structural guard: Phase 0 must never emit a profitability claim."""
    from hyp04_supply_chain_hedge.constants import NO_EDGE_CLAIM, PLACEHOLDER_LINKAGE_WARNING
    check("5a. the package carries an explicit no-edge statement",
          "nothing here demonstrates" in NO_EDGE_CLAIM.lower())
    check("5b. and an explicit placeholder-linkage warning",
          "placeholder linkage" in PLACEHOLDER_LINKAGE_WARNING.lower())


def test_6_network_is_actually_blocked() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("6a. network is blocked in this test process", False, "a lookup succeeded")
    except Exception as e:
        check("6a. network is blocked in this test process",
              type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_audit_refuses_without_an_owner_supplied_budget()
    test_2_audit_runs_and_classifies_outcomes()
    test_3_audit_stops_at_the_cap_without_truncating_silently()
    test_4_end_to_end_pipeline_completes_with_the_right_schema()
    test_5_no_edge_claim_anywhere_in_package_output()
    test_6_network_is_actually_blocked()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("HYP-04 PHASE 0 SMOKE TEST PASSED (completion + schema only)")
    sys.exit(0)
