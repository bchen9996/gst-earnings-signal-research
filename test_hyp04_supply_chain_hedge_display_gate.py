#!/usr/bin/env python3
"""Result-display GATE tests -- HYP-04. The load-bearing test in this build.

This file tests the LOCK, not the dashboard around it. A dashboard that
renders beautifully but leaks a lag estimate through a closed gate is a
governance failure; a dashboard that renders badly through a correct gate is
a cosmetic bug. These tests are written accordingly.

The pattern mirrors Phase 0's split negative-control fixtures, which asserted
in BOTH directions because a one-directional test can be satisfied by a
degenerate implementation:

  * A gate hardcoded to CLOSED would pass every "must stay locked" test and
    is useless. So there is a fixture where ALL conditions hold and the gate
    MUST open (test_9).
  * A gate hardcoded to OPEN would pass that one. So every condition is
    falsified INDIVIDUALLY, with all others held true, and each must deny on
    its own (tests 3-7).

Neither direction alone proves anything. Both together pin the gate.

Also tested: unknown/absent inputs deny rather than default (test_2, test_8),
tampered freeze records deny (test_10), and unclassified panels are treated
as findings rather than as progress (test_11).

Offline. No network. Synthetic gate inputs only -- no real event data exists.

Run directly: python test_hyp04_supply_chain_hedge_display_gate.py
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline gate test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    FINDINGS_PANELS,
    PROGRESS_PANELS,
    REGISTRY_V1_1,
    FreezeRecord,
    GateError,
    assert_display_allowed,
    current_decision,
    evaluate_gate,
    is_findings_panel,
    locked_panel_placeholder,
)

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


# --------------------------------------------------------------------------
# Fixtures. To test C1 and C4 we need a registry where HYP-04 is
# ACTIVE_COLLECTING with no pending decisions -- a hypothetical FUTURE state
# that does not exist today. It is synthesised in a temp file rather than
# written to the real registry, because the point is to test the gate, not to
# advance the hypothesis.
# --------------------------------------------------------------------------
_REAL = json.loads(REGISTRY_V1_1.read_text(encoding="utf-8-sig"))


def _registry_variant(tmpdir: Path, *, status: str, pending: bool,
                      threshold: int = 193) -> Path:
    doc = json.loads(json.dumps(_REAL))
    for h in doc["hypotheses"]:
        if h["hypothesis_id"] == "HYP-04":
            h["status"] = status
            h["minimum_eligible_events"] = threshold
            h["unresolved_analysis_decisions"] = (
                h["unresolved_analysis_decisions"] if pending else []
            )
    p = tmpdir / "registry_variant.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _good_freeze(n: int = 193) -> FreezeRecord:
    """A fully valid freeze over a REAL (non-placeholder) linkage."""
    return FreezeRecord(
        frozen=True,
        eligible_event_ids=tuple(f"EVT-SYNTH-{i:04d}" for i in range(n)),
        analysis_commit_sha="0" * 40,
        analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
        frozen_before_any_result_computed=True,
        uses_placeholder_linkage=False,
    )


# ===================== 1. today's real gate is CLOSED =====================
def test_1_the_live_gate_is_closed_right_now() -> None:
    d = current_decision()
    check("1a. the live gate is CLOSED", d.open is False)
    check("1b. it denies on more than one independent ground",
          len(d.denials) >= 2, f"denials={len(d.denials)}")
    check("1c. C1 fails: status is not ACTIVE_COLLECTING",
          d.conditions["C1_status"] is False)
    check("1d. C2 fails: zero real eligible events against a 193 threshold",
          d.conditions["C2_threshold"] is False)
    check("1e. C3 fails: no freeze record exists",
          d.conditions["C3_frozen"] is False)
    check("1f. C4 fails: analysis decisions are still PENDING",
          d.conditions["C4_decisions_resolved"] is False)
    check("1g. C5 fails: the linkage is the Phase 0 placeholder",
          d.conditions["C5_not_placeholder"] is False)
    check("1h. the registry threshold it read is 193",
          d.evidence["registered_threshold"] == 193)


def test_2_unknown_inputs_deny_rather_than_default() -> None:
    """Section 4: 'Eligible count unknown or not mechanically derivable' -> DENY."""
    d = evaluate_gate(eligible_event_count=None, freeze=_good_freeze())
    check("2a. an unknown eligible count denies", d.open is False)
    check("2b. and says so explicitly",
          any("unknown" in x.lower() for x in d.denials))

    d2 = evaluate_gate(eligible_event_count=193, freeze=None)
    check("2c. an absent freeze record denies", d2.open is False)
    check("2d. and says so explicitly",
          any("no freeze record" in x.lower() for x in d2.denials))

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "not_json.json"
        bad.write_text("{ this is not json", encoding="utf-8")
        d3 = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(),
                           registry_path=bad)
        check("2e. an unparseable registry denies", d3.open is False)
        missing = Path(td) / "absent.json"
        d4 = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(),
                           registry_path=missing)
        check("2f. a missing registry denies", d4.open is False)


# ===================== 3-7. each condition falsified ALONE =================
def test_3_c1_alone_closes_the_gate() -> None:
    """Everything true EXCEPT status."""
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
                                pending=False)
        d = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(), registry_path=reg)
        check("3a. wrong status alone closes the gate", d.open is False)
        check("3b. C1 is the failing condition", d.conditions["C1_status"] is False)
        check("3c. and the other four conditions are satisfied",
              all(d.conditions[c] for c in ("C2_threshold", "C3_frozen",
                                            "C4_decisions_resolved", "C5_not_placeholder")),
              "if these are not all true, this test is not isolating C1")


def test_4_c2_alone_closes_the_gate() -> None:
    """Everything true EXCEPT the count -- 192 against a 193 threshold."""
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=False)
        d = evaluate_gate(eligible_event_count=192, freeze=_good_freeze(192), registry_path=reg)
        check("4a. one event short alone closes the gate", d.open is False)
        check("4b. C2 is the failing condition", d.conditions["C2_threshold"] is False)
        check("4c. and the other four conditions are satisfied",
              all(d.conditions[c] for c in ("C1_status", "C3_frozen",
                                            "C4_decisions_resolved", "C5_not_placeholder")))
        check("4d. the denial names both numbers",
              any("192" in x and "193" in x for x in d.denials))


def test_5_c3_alone_closes_the_gate() -> None:
    """Everything true EXCEPT the freeze -- tested one defect at a time."""
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=False)

        variants = {
            "flag not set": FreezeRecord(
                frozen=False, eligible_event_ids=tuple(f"E{i}" for i in range(193)),
                analysis_commit_sha="0" * 40, analysis_lock_document="lock.json",
                frozen_before_any_result_computed=True, uses_placeholder_linkage=False),
            "no commit SHA": FreezeRecord(
                frozen=True, eligible_event_ids=tuple(f"E{i}" for i in range(193)),
                analysis_commit_sha=None, analysis_lock_document="lock.json",
                frozen_before_any_result_computed=True, uses_placeholder_linkage=False),
            "no analysis lock": FreezeRecord(
                frozen=True, eligible_event_ids=tuple(f"E{i}" for i in range(193)),
                analysis_commit_sha="0" * 40, analysis_lock_document=None,
                frozen_before_any_result_computed=True, uses_placeholder_linkage=False),
            "frozen AFTER results computed": FreezeRecord(
                frozen=True, eligible_event_ids=tuple(f"E{i}" for i in range(193)),
                analysis_commit_sha="0" * 40, analysis_lock_document="lock.json",
                frozen_before_any_result_computed=False, uses_placeholder_linkage=False),
            "empty event-id set": FreezeRecord(
                frozen=True, eligible_event_ids=(),
                analysis_commit_sha="0" * 40, analysis_lock_document="lock.json",
                frozen_before_any_result_computed=True, uses_placeholder_linkage=False),
        }
        for label, fz in variants.items():
            d = evaluate_gate(eligible_event_count=193, freeze=fz, registry_path=reg)
            check(f"5. a freeze with '{label}' closes the gate",
                  d.open is False and d.conditions["C3_frozen"] is False)


def test_6_c4_alone_closes_the_gate() -> None:
    """Everything true EXCEPT that analysis decisions remain PENDING.

    This is the condition the dashboard request did not include, and it is the
    reason a two-condition gate would have been weaker than HYP-01's: a frozen
    193-event sample measured through an unresolved estimator is not a
    licensed result.
    """
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=True)
        d = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(), registry_path=reg)
        check("6a. unresolved PENDING decisions alone close the gate", d.open is False)
        check("6b. C4 is the failing condition",
              d.conditions["C4_decisions_resolved"] is False)
        check("6c. and the other four conditions are satisfied",
              all(d.conditions[c] for c in ("C1_status", "C2_threshold",
                                            "C3_frozen", "C5_not_placeholder")))
        check("6d. the denial counts the outstanding decisions",
              d.evidence["pending_analysis_decisions"] >= 1)


def test_7_c5_alone_closes_the_gate() -> None:
    """Everything true EXCEPT that the linkage is the placeholder."""
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=False)
        fz = _good_freeze()
        fz.uses_placeholder_linkage = True
        d = evaluate_gate(eligible_event_count=193, freeze=fz, registry_path=reg)
        check("7a. placeholder linkage alone closes the gate", d.open is False)
        check("7b. C5 is the failing condition",
              d.conditions["C5_not_placeholder"] is False)
        check("7c. and the other four conditions are satisfied",
              all(d.conditions[c] for c in ("C1_status", "C2_threshold",
                                            "C3_frozen", "C4_decisions_resolved")))
        check("7d. the denial cites 'at any event count'",
              any("any event count" in x.lower() for x in d.denials),
              "placeholder results are barred regardless of n")


def test_8_partial_combinations_never_open() -> None:
    """Any proper subset of conditions leaves the gate CLOSED.

    Sweeps every combination of the two conditions the request named (count,
    freeze) against the two it did not (status, pending) and asserts that
    nothing short of ALL of them opens the gate.
    """
    with tempfile.TemporaryDirectory() as td:
        opened_early = []
        for status in ("ACTIVE_COLLECTING", "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED"):
            for pending in (True, False):
                for count in (0, 192, 193):
                    for fz in (None, _good_freeze(), _good_freeze(192)):
                        reg = _registry_variant(Path(td), status=status, pending=pending)
                        d = evaluate_gate(eligible_event_count=count, freeze=fz,
                                          registry_path=reg)
                        all_hold = (
                            status == "ACTIVE_COLLECTING"
                            and not pending
                            and count >= 193
                            and fz is not None
                            and len(fz.eligible_event_ids) == count
                            and not fz.uses_placeholder_linkage
                        )
                        if d.open and not all_hold:
                            opened_early.append((status, pending, count,
                                                 None if fz is None
                                                 else len(fz.eligible_event_ids)))
        check(f"8a. no partial combination opens the gate (leaks={opened_early[:3]})",
              not opened_early)


# ===================== 9. the gate CAN open ===============================
def test_9_all_conditions_true_opens_the_gate() -> None:
    """The other direction. Without this, a hardcoded-CLOSED gate would pass.

    This uses a synthesised future registry state and a synthetic freeze. It
    asserts the MECHANISM can open -- it does not assert anything about the
    real hypothesis, which remains closed on five independent grounds.
    """
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=False)
        d = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(), registry_path=reg)
        check("9a. with ALL conditions true the gate OPENS", d.open is True,
              f"denials={d.denials}")
        check("9b. and it records no denials", d.denials == [])
        check("9c. every condition is individually true",
              all(d.conditions.values()), str(d.conditions))
        # and a findings panel is then permitted
        try:
            assert_display_allowed("onset_horizon", d)
            check("9d. a findings panel is permitted through an OPEN gate", True)
        except GateError:
            check("9d. a findings panel is permitted through an OPEN gate", False)
        # exceeding the threshold is also fine
        d2 = evaluate_gate(eligible_event_count=500, freeze=_good_freeze(500),
                           registry_path=reg)
        check("9e. exceeding the threshold also opens", d2.open is True)


# ===================== 10. tampering =====================================
def test_10_tampered_freeze_records_are_rejected() -> None:
    """A freeze whose contents contradict the reported count is not derivable."""
    with tempfile.TemporaryDirectory() as td:
        reg = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=False)

        # claims 193 eligible, but the frozen set holds 5 ids
        forged = FreezeRecord(
            frozen=True, eligible_event_ids=tuple(f"E{i}" for i in range(5)),
            analysis_commit_sha="0" * 40, analysis_lock_document="lock.json",
            frozen_before_any_result_computed=True, uses_placeholder_linkage=False)
        d = evaluate_gate(eligible_event_count=193, freeze=forged, registry_path=reg)
        check("10a. a frozen set smaller than the claimed count is rejected",
              d.open is False and d.conditions["C3_frozen"] is False)
        check("10b. and the mismatch is named in the denial",
              any("must agree" in x for x in d.denials))

        # a lowered threshold in a doctored registry must not smuggle the gate open
        low = _registry_variant(Path(td), status="ACTIVE_COLLECTING", pending=False,
                                threshold=1)
        d2 = evaluate_gate(eligible_event_count=1, freeze=_good_freeze(1), registry_path=low)
        check("10c. the gate reads its threshold from the registry, not a constant",
              d2.evidence["registered_threshold"] == 1,
              "documents that registry integrity is enforced by the registry's own "
              "governance tests, not by this gate")

        # negative / non-integer counts
        for bad in (-1, "193", 193.0):
            db = evaluate_gate(eligible_event_count=bad, freeze=_good_freeze(),
                               registry_path=reg)
            check(f"10d. a non-negative-integer count {bad!r} is rejected",
                  db.open is False)


# ===================== 11. panel classification ==========================
def test_11_panel_classification_fails_closed() -> None:
    closed = current_decision()

    for p in FINDINGS_PANELS:
        check(f"11a. {p} is classified as a findings panel", is_findings_panel(p))
        try:
            assert_display_allowed(p, closed)
            check(f"11b. {p} is DENIED through the closed gate", False,
                  "it rendered anyway")
        except GateError:
            check(f"11b. {p} is DENIED through the closed gate", True)

    for p in PROGRESS_PANELS:
        check(f"11c. {p} is classified as progress, not a finding",
              not is_findings_panel(p))
        try:
            assert_display_allowed(p, closed)
            check(f"11d. {p} is permitted even through a closed gate", True)
        except GateError:
            check(f"11d. {p} is permitted even through a closed gate", False)

    # An unclassified panel must be treated as a FINDING and denied.
    check("11e. an unknown panel id is treated as a finding (fails closed)",
          is_findings_panel("some_panel_nobody_classified"))
    try:
        assert_display_allowed("some_panel_nobody_classified", closed)
        check("11f. and is denied through a closed gate", False)
    except GateError:
        check("11f. and is denied through a closed gate", True)

    check("11g. the two panel lists are disjoint",
          not (set(FINDINGS_PANELS) & set(PROGRESS_PANELS)))


def test_12_locked_placeholder_leaks_no_finding() -> None:
    """A locked panel must not leak magnitude, direction, or a value."""
    closed = current_decision()
    for p in FINDINGS_PANELS:
        ph = locked_panel_placeholder(p, closed)
        check(f"12a. {p} placeholder is marked LOCKED", ph["state"] == "LOCKED")

        # Scan the CONTENT, not the identifier. A panel called
        # `beta_h_coefficients` necessarily contains "beta" in its own name;
        # naming a locked panel is not leaking a value, and an earlier version
        # of this check flagged exactly that -- a matcher defect that would
        # have failed against a correct implementation.
        content = {k: v for k, v in ph.items() if k != "panel_id"}
        blob = json.dumps(content).lower()
        for leak in ("beta =", "beta=", "coefficient of", "horizon=",
                     "estimate is", "is significant", "p-value", "p_value",
                     "correlation of", "increases", "decreases"):
            check(f"12b. {p} placeholder does not leak '{leak}'", leak not in blob)

        # The stronger guarantee: no numeric MEASUREMENT leaks. A leaked
        # finding is a number with a magnitude.
        #
        # Document version identifiers are stripped first -- the denial text
        # legitimately cites "registry v1.1" and "GATES_v1.0", and a naive
        # decimal scan flags those. A version string is not a measurement, and
        # failing on one would be a matcher defect rather than a real leak.
        import re as _re
        scrubbed = _re.sub(r"\bv\d+\.\d+", "vX", blob)
        scrubbed = _re.sub(r"_v\d+\.\d+", "_vX", scrubbed)
        numbers = {n for n in _re.findall(r"-?\d+\.\d+", scrubbed)}
        check(f"12b2. {p} placeholder contains no numeric measurement",
              not numbers, f"found {sorted(numbers)[:3]}")
        check(f"12c. {p} placeholder explains what would unlock it",
              "what_unlocks_it" in ph and "193" in ph["what_unlocks_it"])
        check(f"12d. {p} placeholder states looking != concluding",
              "licenses LOOKING, not CONCLUDING" in ph["note"])


def test_13_the_dashboard_cannot_bypass_the_gate() -> None:
    """A correct gate that the renderer can route around is not a control.

    Tests the CONSUMER, not just the gate. Each probe feeds deliberately
    finding-shaped content into the renderer and asserts it does not come out.
    """
    import re as _re

    from hyp04_supply_chain_hedge import dashboard as D

    closed = current_decision()
    poisoned = "<p>onset_horizon = 5, beta_h = 0.5500, t = 22.96, p = 0.0033</p>"

    out = D._panel("onset_horizon", "Onset Horizon", poisoned, closed)
    check("13a. finding content passed to a LOCKED panel is NOT rendered",
          not any(t in out for t in ("0.5500", "22.96", "0.0033")))
    check("13b. the panel renders as locked instead", "GATE CLOSED" in out)

    # Control: without this, 13a could pass simply because _panel drops all
    # content unconditionally, which would prove nothing about the gate.
    out2 = D._panel("build_test_status", "Build", poisoned, closed)
    check("13c. CONTROL -- the same content DOES render through a progress panel",
          "0.5500" in out2,
          "if this fails, 13a is vacuous")

    out3 = D._panel("brand_new_unclassified_panel", "New", poisoned, closed)
    check("13d. an unclassified panel is locked, not shown",
          "GATE CLOSED" in out3 and "0.5500" not in out3)

    src = (Path(__file__).resolve().parent
           / "hyp04_supply_chain_hedge" / "dashboard.py").read_text(encoding="utf-8")
    check("13e. the dashboard never constructs its own GateDecision",
          not _re.findall(r"GateDecision\s*\(", src),
          "minting a decision would let the renderer declare itself open")
    check("13f. the dashboard calls the shared enforcement function",
          "assert_display_allowed" in src)
    check("13g. and does not reimplement gate logic locally",
          "def assert_display_allowed" not in src
          and "def evaluate_gate" not in src)


def test_14_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("14a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("14a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_the_live_gate_is_closed_right_now()
    test_2_unknown_inputs_deny_rather_than_default()
    test_3_c1_alone_closes_the_gate()
    test_4_c2_alone_closes_the_gate()
    test_5_c3_alone_closes_the_gate()
    test_6_c4_alone_closes_the_gate()
    test_7_c5_alone_closes_the_gate()
    test_8_partial_combinations_never_open()
    test_9_all_conditions_true_opens_the_gate()
    test_10_tampered_freeze_records_are_rejected()
    test_11_panel_classification_fails_closed()
    test_12_locked_placeholder_leaks_no_finding()
    test_13_the_dashboard_cannot_bypass_the_gate()
    test_14_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 DISPLAY-GATE TESTS PASSED")
    sys.exit(0)
