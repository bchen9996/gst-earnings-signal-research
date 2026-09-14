#!/usr/bin/env python3
"""make_hyp07_sample_size_gate.py tests -- offline (reads the real, already-
committed universe artifact from disk, makes no network call).

Run directly: python test_hyp04_supply_chain_hedge_hyp07_sample_size_gate.py
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

from hyp04_supply_chain_hedge import make_hyp07_sample_size_gate as M  # noqa: E402
from hyp04_supply_chain_hedge.make_hyp05_sample_size_gate import (  # noqa: E402
    sidak_corrected_n,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_reuses_hyp05s_formula_and_k_range_exactly() -> None:
    prov = M.provisional_operative_floor()
    expected = round(max(sidak_corrected_n(6.05), sidak_corrected_n(6.34)))
    check("1a. operative floor matches HYP-05's own formula/k-range exactly "
          "-- HYP-07 borrows the same numbers HYP-06 did, even though its "
          "target is a different formula",
          prov["operative_provisional_floor"] == expected,
          f"{prov['operative_provisional_floor']} vs {expected}")
    check("1b. same k range as HYP-05's/HYP-06's gate",
          prov["k_range_borrowed_from_hyp04_phase0"] == [6.05, 6.34])


def test_2_real_universe_size_read_from_the_real_artifact() -> None:
    if not M.UNIVERSE_ARTIFACT.is_file():
        check("2a. the real universe artifact is present on disk", False,
              str(M.UNIVERSE_ARTIFACT))
        return
    n = M._real_universe_size()
    check("2a. real universe size is a positive int", isinstance(n, int) and n > 0,
          str(n))
    floor = M.provisional_operative_floor()["operative_provisional_floor"]
    check("2b. real universe size clears the provisional floor",
          n >= floor, str(n))
    check("2c. real universe size clears the floor EXACTLY, not "
          "comfortably -- the knife-edge case this gate exists to disclose "
          "rather than round away",
          n == floor, f"n={n}, floor={floor}")


def test_3_build_report_and_render_do_not_crash_and_are_consistent() -> None:
    report = M.build_report()
    text = M.render(report)
    check("3a. report names HYP-07", report["hypothesis_id"] == "HYP-07")
    check("3b. rendered text contains the real universe size",
          str(report["real_universe_size"]) in text)
    check("3c. clears_provisional_floor is True given the real numbers",
          report["clears_provisional_floor"] is True, str(report))
    check("3d. the exactly-at-the-floor note is present and rendered, not "
          "silently dropped",
          report.get("clears_provisional_floor_note") is not None
          and "EXACTLY" in report["clears_provisional_floor_note"]
          and report["clears_provisional_floor_note"] in text)


def test_4_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("4a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("4a. network blocked", True)


if __name__ == "__main__":
    test_1_reuses_hyp05s_formula_and_k_range_exactly()
    test_2_real_universe_size_read_from_the_real_artifact()
    test_3_build_report_and_render_do_not_crash_and_are_consistent()
    test_4_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_SAMPLE_SIZE_GATE TESTS PASSED")
    sys.exit(0)
