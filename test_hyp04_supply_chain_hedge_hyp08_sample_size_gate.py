#!/usr/bin/env python3
"""make_hyp08_sample_size_gate.py tests -- offline, no network, no real
artifact reads (unlike every prior hypothesis's own gate, HYP-08's k is
exact by design, not read off a real discovered universe -- see the
module's own docstring).

Run directly: python test_hyp04_supply_chain_hedge_hyp08_sample_size_gate.py
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

from scipy import stats  # noqa: E402

from hyp04_supply_chain_hedge import make_hyp08_sample_size_gate as M  # noqa: E402
from hyp04_supply_chain_hedge.make_hyp05_sample_size_gate import (  # noqa: E402
    sidak_corrected_n,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_operative_floor_uses_the_true_k_not_a_borrowed_range() -> None:
    floor = M.operative_floor()
    expected = round(sidak_corrected_n(2.0))
    check("1a. operative floor matches sidak_corrected_n(k=2) exactly",
          floor["operative_floor"] == expected,
          f"{floor['operative_floor']} vs {expected}")
    check("1b. k is reported as EXACT, not provisional",
          floor["provisional"] is False)
    check("1c. family_size_k is exactly 2", floor["family_size_k"] == 2)


def test_2_sidak_critical_t_matches_a_hand_computation() -> None:
    dof = 50.0
    crit = M.sidak_critical_t(dof, k=2)
    alpha_sidak = 1.0 - (1.0 - M.ALPHA_FAMILY_WISE) ** (1.0 / 2)
    expected = float(stats.t.ppf(1.0 - alpha_sidak / 2.0, dof))
    check("2a. matches a hand-derived Sidak-corrected t critical value",
          abs(crit - expected) < 1e-9, f"{crit} vs {expected}")

    check("2b. k=1 is looser (smaller) than k=2 at the same dof",
          M.sidak_critical_t(dof, k=1) < M.sidak_critical_t(dof, k=2))

    crit_nan = M.sidak_critical_t(float("nan"), k=2)
    crit_huge = M.sidak_critical_t(1e9, k=2)
    check("2c. a NaN dof falls back to the normal quantile, not a crash",
          crit_nan == crit_nan and crit_nan > 0, str(crit_nan))
    check("2d. an absurdly large dof matches the NaN/normal fallback",
          abs(crit_nan - crit_huge) < 1e-6, f"{crit_nan} vs {crit_huge}")

    try:
        M.sidak_critical_t(10.0, k=0)
        check("2e. k < 1 raises", False)
    except ValueError:
        check("2e. k < 1 raises", True)


def test_3_build_report_and_render_do_not_crash_and_are_consistent() -> None:
    report = M.build_report()
    text = M.render(report)
    check("3a. report names HYP-08", report["hypothesis_id"] == "HYP-08")
    check("3b. rendered text contains the operative floor",
          str(report["operative_floor"]["operative_floor"]) in text)
    check("3c. why_not_provisional is present and rendered",
          bool(report["operative_floor"]["why_not_provisional"])
          and report["operative_floor"]["why_not_provisional"] in text)
    check("3d. naive single-test baseline matches HYP-05's own k=1 formula",
          report["naive_single_test_baseline"] == round(sidak_corrected_n(1.0)))


def test_4_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("4a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("4a. network blocked", True)


if __name__ == "__main__":
    test_1_operative_floor_uses_the_true_k_not_a_borrowed_range()
    test_2_sidak_critical_t_matches_a_hand_computation()
    test_3_build_report_and_render_do_not_crash_and_are_consistent()
    test_4_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP08_SAMPLE_SIZE_GATE TESTS PASSED")
    sys.exit(0)
