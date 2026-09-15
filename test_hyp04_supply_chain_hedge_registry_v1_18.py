#!/usr/bin/env python3
"""make_registry_v1_18.py tests -- offline, reads the real on-disk
findings (model plan, sample-size gate, both source locks, anchor-shocks
CSVs) and the real v1.17 registry. Makes no network call, writes nothing
to the real Live Signal Engine directory (build_v1_18() is pure; only
main(--write) writes, never called here).

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_18.py
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

from hyp04_supply_chain_hedge import make_registry_v1_18 as M  # noqa: E402
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

    refusals = M.check_preconditions(
        v1_18=Path("this_specific_version_never_exists_for_this_check.json"))
    check("1a. the real, committed findings (model plan, sample-size gate, "
          "both source locks, anchor-shocks CSVs) all satisfy the "
          "precondition on their own",
          refusals == [], str(refusals))


def test_2_no_immovable_field_exception_is_claimed() -> None:
    check("2a. SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE is empty -- v1.18 "
          "moves nothing about HYP-04, HYP-05, HYP-06, or HYP-07",
          M.SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE == ())


def test_3_prior_four_entries_are_byte_identical_hyp08_is_added() -> None:
    doc, changes = M.build_v1_18()
    src = M._load(M.V1_17)

    for hid in ("HYP-04", "HYP-05", "HYP-06", "HYP-07"):
        old = next(h for h in src["hypotheses"] if h["hypothesis_id"] == hid)
        new = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)
        check(f"3.{hid}. entry is byte-identical to v1.17's", new == old)

    check("3e. HYP-08 is present, newly added",
          any(h["hypothesis_id"] == "HYP-08" for h in doc["hypotheses"])
          and not any(h["hypothesis_id"] == "HYP-08" for h in src["hypotheses"]))
    check("3f. registry_version moved to v1.18",
          doc["registry_version"] == "v1.18")
    check("3g. results/results_note untouched",
          doc.get("results") == src.get("results")
          and doc.get("results_note") == src.get("results_note"))


def test_4_hyp08_entry_shape_is_sane() -> None:
    doc, _ = M.build_v1_18()
    h8 = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-08")

    check("4a. status matches every prior hypothesis's own label at this "
          "stage",
          h8["status"] == "PREREGISTERED_UNIVERSE_RESOLVED_NOT_LOCKED")
    check("4b. classification is exploratory, not confirmatory",
          h8["classification"] == "preregistered_exploratory"
          and h8["is_primary_confirmatory"] is False)

    decisions = h8["unresolved_analysis_decisions"]
    check("4c. all four decisions are RESOLVED, none PENDING",
          len(decisions) == 4
          and all(d["state"] == "RESOLVED" for d in decisions),
          str([d["state"] for d in decisions]))
    check("4d. every resolved decision cites a source, not just a bare claim",
          all(len(d.get("resolution", "")) > 20 for d in decisions))

    target_decision = next(d for d in decisions
                           if d["decision"] == "the target/outcome definition")
    check("4e. the target/outcome decision names target_same_session.py "
          "and says it is NOT yet locked",
          "target_same_session.py" in target_decision["resolution"]
          and "not yet" in target_decision["resolution"].lower())

    universe_decision = next(d for d in decisions
                             if d["decision"] == "the target anchor/peer universe")
    check("4e2. the universe decision states no new EDGAR discovery was "
          "performed",
          "No new EDGAR discovery" in universe_decision["resolution"])

    check("4f. minimum_eligible_events is a real, positive int",
          isinstance(h8["minimum_eligible_events"], int)
          and h8["minimum_eligible_events"] > 0)
    check("4g. the floor is explicitly labelled NOT provisional -- unlike "
          "every prior hypothesis's own floor",
          h8["minimum_eligible_events_basis"]["provisional"] is False)
    check("4h. the real universe comfortably clears the floor, disclosed "
          "with a real multiple",
          "x" in h8["minimum_eligible_events_basis"][
              "real_universe_clears_floor_comfortably"])

    check("4i. required_columns includes as_of_date, same discipline as "
          "every prior hypothesis",
          "as_of_date" in h8["required_external_measurement"]["required_columns"])

    check("4j. display_rule forbids showing any result before the floor "
          "AND before a lock exists",
          "floor" in h8["display_rule"].lower()
          and "lock" in h8["display_rule"].lower())

    check("4k. a newly-extracted concentration-intensity axis is an "
          "explicit forbidden substitution -- the specific 'do not add a "
          "filter' discipline this hypothesis was built under",
          any("concentration-intensity" in s
              for s in h8["forbidden_substitutions"]))
    check("4l. treating the interaction fit's descriptive-only implied "
          "slopes as extra tests is an explicit forbidden substitution",
          any("third or fourth preregistered" in s
              for s in h8["forbidden_substitutions"]))


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


def test_7_the_live_gate_is_now_closed() -> None:
    """v1.18 is real, on disk, and is what display_gate.py/dashboard.py
    read as of 2026-09-14. This version's suite holds the live "gate
    reads X" claim -- see test_hyp04_supply_chain_hedge_registry_v1_17.py's
    own test_7, narrowed now that this version supersedes it."""
    from hyp04_supply_chain_hedge.display_gate import (
        REGISTRY_CURRENT,
        current_decision,
    )

    check("7a. v1.18 was written by this session's generator, not this suite",
          (M.LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.18.json").is_file())
    check("7b. the gate now reads v1.18",
          REGISTRY_CURRENT.name.endswith("v1.18.json"))
    live = current_decision()
    check("7c. the REAL gate is CLOSED, denying on C1 alone -- unchanged "
          "since v1.13, since v1.14 through v1.18 all touch nothing "
          "about HYP-04's own entry",
          live.open is False and len(live.denials) == 1
          and live.denials[0].startswith("C1"), str(live.denials))


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_preconditions_require_the_real_findings_on_disk()
    test_2_no_immovable_field_exception_is_claimed()
    test_3_prior_four_entries_are_byte_identical_hyp08_is_added()
    test_4_hyp08_entry_shape_is_sane()
    test_5_immovable_fields_are_the_same_frozen_schema()
    test_6_check_preconditions_refuses_on_a_missing_finding()
    test_7_the_live_gate_is_now_closed()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL REGISTRY_V1_18 TESTS PASSED")
    sys.exit(0)
