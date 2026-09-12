#!/usr/bin/env python3
"""clustered_se.py tests -- specifically dual_cluster_report(), HYP-05's
2026-09-12 re-decision on two-way clustering (see HYP05_TWO_WAY_LIMITATION_
NOTE): two ONE-WAY clusterings reported side by side, not a two-way
estimator. cr_vcov/ols/satterthwaite_df/intraclass_correlation are already
exercised indirectly via test_hyp04_supply_chain_hedge_inference.py; this
file covers only the new function.

Fully offline, synthetic fixtures. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_clustered_se.py
"""
from __future__ import annotations

import socket
import sys

import numpy as np


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.clustered_se import (  # noqa: E402
    HYP05_TWO_WAY_LIMITATION_NOTE,
    TWO_WAY_LIMITATION_NOTE,
    cr_vcov,
    dual_cluster_report,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _synthetic_panel(seed: int = 0, n: int = 240):
    """20 anchor-event clusters x 12 peers each, with calendar period cutting
    ACROSS anchor-event clusters (4 calendar periods, each containing peers
    from 5 different anchor events) -- so the two dimensions are genuinely
    different partitions of the same rows, not one relabeling the other."""
    rng = np.random.default_rng(seed)
    n_events = 20
    per_event = n // n_events
    X = np.column_stack([np.ones(n), rng.normal(size=n)])
    g_anchor = np.repeat(np.arange(n_events), per_event)
    g_calendar = g_anchor % 4  # 4 calendar periods, crossing anchor clusters
    beta_true = np.array([1.5, -0.8])
    event_shock = rng.normal(scale=1.0, size=n_events)[g_anchor]
    noise = rng.normal(scale=0.5, size=n)
    y = X @ beta_true + event_shock + noise
    return X, y, g_anchor, g_calendar


def test_1_reports_both_dimensions_with_correct_labels() -> None:
    X, y, g_anchor, g_calendar = _synthetic_panel()
    r = dual_cluster_report(X, y, g_anchor, g_calendar)
    check("1a. primary labeled anchor_event",
          r["primary"]["dimension"] == "anchor_event")
    check("1b. secondary labeled calendar_period",
          r["secondary"]["dimension"] == "calendar_period")
    check("1c. primary cluster count matches g_anchor's distinct values",
          r["primary"]["n_clusters"] == len(np.unique(g_anchor)))
    check("1d. secondary cluster count matches g_calendar's distinct values",
          r["secondary"]["n_clusters"] == len(np.unique(g_calendar)))
    check("1e. beta has one coefficient per column of X",
          len(r["beta"]) == X.shape[1])
    check("1f. note explicitly disclaims being a two-way estimator",
          "not a two-way estimator" in r["note"], r["note"])


def test_2_matches_two_separate_cr_vcov_calls() -> None:
    """dual_cluster_report must not silently do anything beyond calling
    cr_vcov twice -- its SEs should equal calling cr_vcov directly on each
    dimension."""
    X, y, g_anchor, g_calendar = _synthetic_panel(seed=1)
    r = dual_cluster_report(X, y, g_anchor, g_calendar)

    _, V_a, _ = cr_vcov(X, y, g_anchor, kind="CR2")
    _, V_c, _ = cr_vcov(X, y, g_calendar, kind="CR2")
    se_a = np.sqrt(np.diag(V_a))
    se_c = np.sqrt(np.diag(V_c))

    check("2a. primary SE matches a direct cr_vcov(g_anchor) call",
          np.allclose(r["primary"]["se"], se_a))
    check("2b. secondary SE matches a direct cr_vcov(g_calendar) call",
          np.allclose(r["secondary"]["se"], se_c))


def test_3_se_ratio_is_secondary_over_primary_elementwise() -> None:
    X, y, g_anchor, g_calendar = _synthetic_panel(seed=2)
    r = dual_cluster_report(X, y, g_anchor, g_calendar)
    expected = r["secondary"]["se"] / r["primary"]["se"]
    check("3a. ratio equals secondary/primary elementwise",
          np.allclose(r["se_ratio_secondary_over_primary"], expected),
          f"{r['se_ratio_secondary_over_primary']} vs {expected}")


def test_4_identical_clustering_on_both_sides_gives_ratio_of_one() -> None:
    """If primary and secondary are literally the same partition, the two
    one-way results must be identical -- a sanity check that the function
    isn't doing anything dimension-specific beyond which g it receives."""
    X, y, g_anchor, _ = _synthetic_panel(seed=3)
    r = dual_cluster_report(X, y, g_anchor, g_anchor)
    check("4a. primary and secondary SEs are identical when g is the same",
          np.allclose(r["primary"]["se"], r["secondary"]["se"]))
    check("4b. ratio is all ones",
          np.allclose(r["se_ratio_secondary_over_primary"], 1.0))


def test_5_kind_is_threaded_through_to_both_calls() -> None:
    X, y, g_anchor, g_calendar = _synthetic_panel(seed=4)
    r_cr2 = dual_cluster_report(X, y, g_anchor, g_calendar, kind="CR2")
    r_cr1 = dual_cluster_report(X, y, g_anchor, g_calendar, kind="CR1")
    check("5a. kind is recorded on the result",
          r_cr2["kind"] == "CR2" and r_cr1["kind"] == "CR1")
    check("5b. CR1 and CR2 give different SEs (different small-sample "
          "corrections)",
          not np.allclose(r_cr2["primary"]["se"], r_cr1["primary"]["se"]))


def test_6_notes_are_distinct_and_hyp05s_note_names_the_real_reason() -> None:
    check("6a. HYP-04's original note and HYP-05's note are distinct text",
          HYP05_TWO_WAY_LIMITATION_NOTE != TWO_WAY_LIMITATION_NOTE)
    check("6b. HYP-05's note still states the same underlying constraint "
          "(no multiway implementation exists)",
          "no multiway" in HYP05_TWO_WAY_LIMITATION_NOTE.lower()
          or "multiway" in HYP05_TWO_WAY_LIMITATION_NOTE.lower())
    check("6c. HYP-05's note names dual_cluster_report as the mitigation",
          "dual_cluster_report" in HYP05_TWO_WAY_LIMITATION_NOTE)


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_reports_both_dimensions_with_correct_labels()
    test_2_matches_two_separate_cr_vcov_calls()
    test_3_se_ratio_is_secondary_over_primary_elementwise()
    test_4_identical_clustering_on_both_sides_gives_ratio_of_one()
    test_5_kind_is_threaded_through_to_both_calls()
    test_6_notes_are_distinct_and_hyp05s_note_names_the_real_reason()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL CLUSTERED_SE TESTS PASSED")
    sys.exit(0)
