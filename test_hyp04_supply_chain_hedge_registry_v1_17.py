#!/usr/bin/env python3
"""make_registry_v1_17.py tests -- offline, reads the real on-disk
findings (model plan, sample-size gate, universe artifact) and the real
v1.16 registry. Makes no network call, writes nothing to the real
Live Signal Engine directory (build_v1_17() is pure; only main(--write)
writes, never called here).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_17.py
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

from hyp04_supply_chain_hedge import make_registry_v1_17 as M  # noqa: E402
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

    # v1.17 is meant to be write-once and is already real, on disk (this
    # suite runs after it was written) -- check the FINDINGS-existence
    # part of the precondition in isolation, against a v1_17 path that
    # does NOT exist, rather than the full default check (which correctly
    # refuses for a different, expected reason -- see test 1b).
    refusals = M.check_preconditions(
        v1_17=Path("this_specific_version_never_exists_for_this_check.json"))
    check("1a. the real, committed findings (model plan, sample-size gate, "
          "discovery methodology, universe artifact) all satisfy the "
          "precondition on their own",
          refusals == [], str(refusals))

    real_refusals = M.check_preconditions()
    check("1b. the REAL default check correctly refuses -- v1.17 already "
          "exists on disk, and dated artifacts are never silently "
          "overwritten", any("already exists" in r for r in real_refusals),
          str(real_refusals))


def test_2_no_immovable_field_exception_is_claimed() -> None:
    check("2a. SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE is empty -- v1.17 "
          "moves nothing about HYP-04, HYP-05, or HYP-06",
          M.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE == ())


def test_3_prior_three_entries_are_byte_identical_hyp07_is_added() -> None:
    doc, changes = M.build_v1_17()
    src = M._load(M.V1_16)

    for hid in ("HYP-04", "HYP-05", "HYP-06"):
        old = next(h for h in src["hypotheses"] if h["hypothesis_id"] == hid)
        new = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)
        check(f"3.{hid}. entry is byte-identical to v1.16's", new == old)

    check("3e. HYP-07 is present, newly added",
          any(h["hypothesis_id"] == "HYP-07" for h in doc["hypotheses"])
          and not any(h["hypothesis_id"] == "HYP-07" for h in src["hypotheses"]))
    check("3f. registry_version moved to v1.17",
          doc["registry_version"] == "v1.17")
    check("3g. results/results_note untouched",
          doc.get("results") == src.get("results")
          and doc.get("results_note") == src.get("results_note"))


def test_4_hyp07_entry_shape_is_sane() -> None:
    doc, _ = M.build_v1_17()
    h7 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-07")

    check("4a. status matches HYP-06's own label -- 'universe resolved' is "
          "not 'a result exists' or 'a lock has been signed', in either "
          "entry",
          h7["status"] == "PREREGISTERED_UNIVERSE_RESOLVED_NOT_LOCKED")
    check("4b. classification is exploratory, not confirmatory",
          h7["classification"] == "preregistered_exploratory"
          and h7["is_primary_confirmatory"] is False)

    decisions = h7["unresolved_analysis_decisions"]
    check("4c. all four decisions are RESOLVED, none PENDING",
          len(decisions) == 4
          and all(d["state"] == "RESOLVED" for d in decisions),
          str([d["state"] for d in decisions]))
    check("4d. every resolved decision cites a source, not just a bare claim",
          all(len(d.get("resolution", "")) > 20 for d in decisions))

    target_decision = next(d for d in decisions
                           if d["decision"] == "the target/outcome definition")
    check("4e. the target/outcome decision names target_signed.py and "
          "says it is NOT yet locked -- the genuinely new piece, unlike "
          "HYP-06 which reused an already-locked spec",
          "target_signed.py" in target_decision["resolution"]
          and "not yet" in target_decision["resolution"].lower())

    check("4f. minimum_eligible_events is a real, positive int",
          isinstance(h7["minimum_eligible_events"], int)
          and h7["minimum_eligible_events"] > 0)
    check("4g. the floor is explicitly labelled provisional",
          h7["minimum_eligible_events_basis"]["provisional"] is True)
    check("4h. the exactly-at-the-floor disclosure is present, not omitted",
          "EQUAL" in h7["minimum_eligible_events_basis"][
              "real_universe_clears_floor_exactly_not_comfortably"])

    check("4i. required_columns includes as_of_date, same discipline as "
          "every prior hypothesis",
          "as_of_date" in h7["required_external_measurement"]["required_columns"])

    check("4j. display_rule forbids showing any result before the floor "
          "AND before a lock exists",
          "floor" in h7["display_rule"].lower()
          and "lock" in h7["display_rule"].lower())

    check("4k. forward self-reported rival naming is an explicit forbidden "
          "substitution -- this project's own Step 0 found exactly that "
          "bias",
          any("forward self-reported" in s
              for s in h7["forbidden_substitutions"]))


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
    """v1.17 was real, on disk, and was what display_gate.py/dashboard.py
    read as of 2026-09-13/14. v1.18 (registering HYP-08) now supersedes
    it -- see test_hyp04_supply_chain_hedge_registry_v1_18.py's own
    test_7 for the live-gate claim, narrowed here the same way v1.16's
    own test_7 was narrowed when THIS version superseded it."""
    check("7a. v1.17 exists on disk",
          (M.LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.17.json").is_file())


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_preconditions_require_the_real_findings_on_disk()
    test_2_no_immovable_field_exception_is_claimed()
    test_3_prior_three_entries_are_byte_identical_hyp07_is_added()
    test_4_hyp07_entry_shape_is_sane()
    test_5_immovable_fields_are_the_same_frozen_schema()
    test_6_check_preconditions_refuses_on_a_missing_finding()
    test_7_this_version_has_moved_past()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL REGISTRY_V1_17 TESTS PASSED")
    sys.exit(0)
