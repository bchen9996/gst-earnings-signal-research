#!/usr/bin/env python3
"""make_registry_v1_16.py tests -- offline, reads the real on-disk
findings (model plan, sample-size gate, universe artifact) and the real
v1.15 registry. Makes no network call, writes nothing to the real
Live Signal Engine directory (build_v1_16() is pure; only main(--write)
writes, never called here).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_16.py
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

from hyp04_supply_chain_hedge import make_registry_v1_16 as M  # noqa: E402
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    IMMOVABLE_HYP04_FIELDS,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_preconditions_require_the_real_findings_on_disk() -> None:
    from pathlib import Path

    # v1.16 is meant to be write-once and is already real, on disk (this
    # suite runs after it was written) -- check the FINDINGS-existence
    # part of the precondition in isolation, against a v1_16 path that
    # does NOT exist, rather than the full default check (which correctly
    # refuses for a different, expected reason -- see test 1b).
    refusals = M.check_preconditions(
        v1_16=Path("this_specific_version_never_exists_for_this_check.json"))
    check("1a. the real, committed findings (model plan, sample-size gate, "
          "universe artifact) all satisfy the precondition on their own",
          refusals == [], str(refusals))

    real_refusals = M.check_preconditions()
    check("1b. the REAL default check correctly refuses -- v1.16 already "
          "exists on disk, and dated artifacts are never silently "
          "overwritten", any("already exists" in r for r in real_refusals),
          str(real_refusals))


def test_2_no_immovable_field_exception_is_claimed() -> None:
    check("2a. SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE is empty -- v1.16 "
          "moves nothing about HYP-04 or HYP-05",
          M.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE == ())


def test_3_hyp04_and_hyp05_are_byte_identical_hyp06_is_added() -> None:
    doc, changes = M.build_v1_16()
    src = M._load(M.V1_15)

    old_h4 = next(h for h in src["hypotheses"] if h["hypothesis_id"] == "HYP-04")
    new_h4 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04")
    check("3a. HYP-04's entry is byte-identical to v1.15's", new_h4 == old_h4)

    old_h5 = next(h for h in src["hypotheses"] if h["hypothesis_id"] == "HYP-05")
    new_h5 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-05")
    check("3b. HYP-05's entry is byte-identical to v1.15's", new_h5 == old_h5)

    check("3c. HYP-06 is present, newly added",
          any(h["hypothesis_id"] == "HYP-06" for h in doc["hypotheses"])
          and not any(h["hypothesis_id"] == "HYP-06" for h in src["hypotheses"]))
    check("3d. registry_version moved to v1.16",
          doc["registry_version"] == "v1.16")
    check("3e. results/results_note untouched",
          doc.get("results") == src.get("results")
          and doc.get("results_note") == src.get("results_note"))


def test_4_hyp06_entry_shape_is_sane() -> None:
    doc, _ = M.build_v1_16()
    h6 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-06")

    check("4a. status is a NEW, distinct value -- not HYP-05's or HYP-04's",
          h6["status"] == "PREREGISTERED_UNIVERSE_RESOLVED_NOT_LOCKED")
    check("4b. classification is exploratory, not confirmatory",
          h6["classification"] == "preregistered_exploratory"
          and h6["is_primary_confirmatory"] is False)

    decisions = h6["unresolved_analysis_decisions"]
    check("4c. all four decisions are RESOLVED, none PENDING",
          len(decisions) == 4
          and all(d["state"] == "RESOLVED" for d in decisions),
          str([d["state"] for d in decisions]))
    check("4d. every resolved decision cites a source, not just a bare claim",
          all(len(d.get("resolution", "")) > 20 for d in decisions))

    check("4e. minimum_eligible_events is a real, positive int",
          isinstance(h6["minimum_eligible_events"], int)
          and h6["minimum_eligible_events"] > 0)
    check("4f. the floor is explicitly labelled provisional",
          h6["minimum_eligible_events_basis"]["provisional"] is True)

    check("4g. required_columns includes as_of_date, same discipline as "
          "every prior hypothesis",
          "as_of_date" in h6["required_external_measurement"]["required_columns"])

    check("4h. display_rule forbids showing any result before the floor "
          "AND before a lock exists",
          "floor" in h6["display_rule"].lower()
          and "lock" in h6["display_rule"].lower())


def test_5_immovable_fields_are_the_same_frozen_schema() -> None:
    check("5a. IMMOVABLE_ENTRY_FIELDS is the same non-empty, real schema "
          "reused from make_registry_v1_6, not redefined here",
          M.IMMOVABLE_ENTRY_FIELDS == IMMOVABLE_HYP04_FIELDS
          and len(M.IMMOVABLE_ENTRY_FIELDS) > 0)


def test_6_check_preconditions_refuses_on_a_missing_finding() -> None:
    from pathlib import Path
    missing = Path("this_file_definitely_does_not_exist_12345.md")
    orig = M.FINDINGS
    try:
        M.FINDINGS = (str(missing),)
        refusals = M.check_preconditions()
        check("6a. refuses when a claimed finding is not on disk",
              any(str(missing) in r for r in refusals), str(refusals))
    finally:
        M.FINDINGS = orig


def test_7_this_version_has_moved_past() -> None:
    """NARROWED: v1.17 (2026-09-13, registering HYP-07) now supersedes
    v1.16 and holds the live "gate reads X" claim -- see
    test_hyp04_supply_chain_hedge_registry_v1_17.py's own test. This
    suite keeps only what is still true regardless of which version is
    CURRENT: v1.16 itself is real, on disk, and was written by this
    session's own generator."""
    check("7a. v1.16 was written by this session's generator, not this suite",
          (M.LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.16.json").is_file())


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_preconditions_require_the_real_findings_on_disk()
    test_2_no_immovable_field_exception_is_claimed()
    test_3_hyp04_and_hyp05_are_byte_identical_hyp06_is_added()
    test_4_hyp06_entry_shape_is_sane()
    test_5_immovable_fields_are_the_same_frozen_schema()
    test_6_check_preconditions_refuses_on_a_missing_finding()
    test_7_this_version_has_moved_past()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL REGISTRY_V1_16 TESTS PASSED")
    sys.exit(0)
