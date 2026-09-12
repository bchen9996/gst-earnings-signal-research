#!/usr/bin/env python3
"""HYP-05 provisional sample-size gate tests.

Fully offline -- this is a closed-form calculation, no data of any kind.

Run directly: python test_hyp04_supply_chain_hedge_hyp05_sample_size_gate.py
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

from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge.make_hyp05_sample_size_gate import (  # noqa: E402
    OUT_PATH,
    build_report,
    naive_single_test_n,
    provisional_operative_floor,
    sidak_corrected_n,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


# =========== 1. the closed form reproduces HYP-04's own published table ===
def test_1_formula_reproduces_hyp04_table() -> None:
    """Live Signal Engine/HYP04_PHASE0_FEASIBILITY_STATUS_2026-08-18.md
    section 5's table, verbatim: k -> implied total N."""
    for k, expected in ((1, 126), (2, 152), (4, 178), (6.05, 193), (6.34, 195),
                       (20, 238)):
        n = sidak_corrected_n(k)
        check(f"1a. k={k} -> N~{expected}", abs(round(n) - expected) <= 1,
              f"got {n:.1f}")


def test_2_naive_baseline_is_the_k1_case() -> None:
    check("2a. naive_single_test_n() is exactly sidak_corrected_n(1)",
          naive_single_test_n() == sidak_corrected_n(1.0))
    check("2b. and rounds to 126, same as HYP-04's own naive baseline",
          round(naive_single_test_n()) == 126)


def test_3_sidak_corrected_n_refuses_a_sub_one_k() -> None:
    for bad in (0.0, -1.0, 0.999):
        try:
            sidak_corrected_n(bad)
        except ValueError:
            continue
        check(f"3a. k={bad} refuses", False, "did not raise")
    check("3a. every k < 1 refuses", True)


# =========== 4. the provisional floor is honestly labelled ================
def test_4_the_provisional_floor_is_labelled_as_borrowed() -> None:
    prov = provisional_operative_floor()
    check("4a. provisional is True", prov["provisional"] is True)
    check("4b. the borrowed k range is HYP-04's own measured range",
          prov["k_range_borrowed_from_hyp04_phase0"] == [6.05, 6.34])
    check("4c. the operative floor takes the conservative (higher-N) end",
          prov["operative_provisional_floor"]
          == round(max(sidak_corrected_n(6.05), sidak_corrected_n(6.34))))
    check("4d. it states why this is borrowed, not measured",
          "has not fixed" in prov["why_borrowed_not_measured"])
    check("4e. and what would supersede it",
          "max-T permutation" in prov["must_be_superseded_by"]
          and "HYP-05's OWN locked design" in prov["must_be_superseded_by"])
    check("4f. the implied N range is plain floats, not numpy scalars "
          "(a rendering bug caught while building this)",
          all(type(x) is float for x in prov["implied_n_range"]))


def test_5_the_report_never_claims_a_measurement() -> None:
    report = build_report()
    check("5a. the naive baseline is reported and labelled never-operative",
          report["naive_single_test_baseline"] == 126
          and "never" in report["naive_single_test_baseline_note"].lower())
    check("5b. the report explains why this does not violate the "
          "power_statement -- both borrowed k values are HYP-04's own "
          "SYNTHETIC-fixture measurement, not any observed result",
          "SYNTHETIC-fixture" in
          report["why_this_does_not_violate_the_power_statement"]
          and "not from any observed project result" in
          report["why_this_does_not_violate_the_power_statement"])
    check("5c. the effect size is stated as hypothetical, same discipline "
          "as HYP-04's own",
          report["derivation_inputs"]["assumed_effect_size_character"]
          .startswith("hypothetical"))


def test_6_written_artifact_matches_and_is_never_overwritten() -> None:
    if not OUT_PATH.is_file():
        check("6a. the dated finding was written for real this session",
              False, f"{OUT_PATH} not found")
        return
    text = OUT_PATH.read_text(encoding="utf-8")
    check("6a. the dated finding was written for real this session", True)
    check("6b. it states the provisional floor",
          "195" in text and "PROVISIONAL" in text)
    check("6c. it names what would supersede it",
          "HYP-05's OWN locked design" in text)

    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m",
         "hyp04_supply_chain_hedge.make_hyp05_sample_size_gate", "--write"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent))
    check("6d. re-running --write refuses rather than overwriting",
          proc.returncode != 0 and "already exists" in proc.stdout,
          proc.stdout[-200:])


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_formula_reproduces_hyp04_table()
    test_2_naive_baseline_is_the_k1_case()
    test_3_sidak_corrected_n_refuses_a_sub_one_k()
    test_4_the_provisional_floor_is_labelled_as_borrowed()
    test_5_the_report_never_claims_a_measurement()
    test_6_written_artifact_matches_and_is_never_overwritten()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-05 SAMPLE-SIZE-GATE TESTS PASSED")
    sys.exit(0)
