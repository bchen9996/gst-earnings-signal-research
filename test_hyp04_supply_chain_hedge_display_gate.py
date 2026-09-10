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
    DECISION_STATES,
    FINDINGS_PANELS,
    PENDING_TOKEN,
    PROGRESS_PANELS,
    REGISTRY_CURRENT,
    RESOLVED_BY_FIELD,
    RESOLVED_TOKEN,
    FreezeRecord,
    GateError,
    assert_display_allowed,
    current_decision,
    evaluate_gate,
    is_findings_panel,
    locked_panel_placeholder,
)
from hyp04_supply_chain_hedge.quantum_provenance import (  # noqa: E402
    CLASSICAL_INTERNAL,
    ProvenanceError,
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
_REAL = json.loads(REGISTRY_CURRENT.read_text(encoding="utf-8-sig"))


def _registry_variant(tmpdir: Path, *, status: str, pending: bool,
                      threshold: int = 193) -> Path:
    """A hypothetical FUTURE registry state, synthesised in a temp file.

    `pending=False` models a REAL resolution: every decision stays in the
    ledger, marked RESOLVED and citing the dated lock that resolved it. It used
    to model resolution by emptying the ledger, which is a deletion rather than
    a resolution -- and which C4 now correctly denies. Resolution is recorded by
    marking, never by removing, mirroring the registry's own append-only rule.

    BOTH branches set the state explicitly. The `pending=True` branch used to
    set nothing at all, silently inheriting whatever the real registry happened
    to carry. That worked only while the source was v1.1, where every decision
    was PENDING. When the gate was repointed at v1.2 -- where every decision is
    RESOLVED -- the "pending" fixture would have quietly produced a resolved
    ledger, and every C4-denial test would have been asserting against a
    registry that no longer denied. A fixture whose meaning depends on ambient
    state is not a fixture.
    """
    doc = json.loads(json.dumps(_REAL))
    for h in doc["hypotheses"]:
        if h["hypothesis_id"] == "HYP-04":
            h["status"] = status
            h["minimum_eligible_events"] = threshold
            for d in h["unresolved_analysis_decisions"]:
                if pending:
                    d["state"] = PENDING_TOKEN
                    d.pop(RESOLVED_BY_FIELD, None)
                else:
                    d["state"] = RESOLVED_TOKEN
                    d[RESOLVED_BY_FIELD] = "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
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


# ===================== 1. today's real gate is OPEN =======================
def test_1_the_live_gate_is_open_and_why() -> None:
    """The gate OPENED on 2026-09-09. Every condition is pinned to its cause.

    It was CLOSED with four denials from the beginning of this project until
    then, and this test asserted exactly that. The conditions cleared one at a
    time, each for a stated reason, and the ORDER was enforced in code: C4 in
    registry v1.2 (2026-08-20), then C2 when `make_event_panel` first derived a
    count, then C3 and C5 together when a freeze was attested over the ratified
    map, and C1 LAST in registry v1.12 -- `make_registry_v1_12` refuses to move
    it while the map is unratified or the freeze invalid.

    What an open gate means is unchanged and is asserted at the end: it
    licenses REPORTING a measurement. It is not a finding, and this test does
    not assert one exists. At the moment it opened, none did.
    """
    d = current_decision()
    check("1a. the live gate is OPEN", d.open is True, str(d.denials))
    check("1b. with no denials at all", len(d.denials) == 0, str(d.denials))
    check("1c. C1 passes: the registry status is ACTIVE_COLLECTING (v1.12)",
          d.conditions["C1_status"] is True
          and d.evidence["registry_status"] == "ACTIVE_COLLECTING")
    check("1d. C2 passes: 214 derived eligible events against a 193 threshold",
          d.conditions["C2_threshold"] is True
          and d.evidence["eligible_event_count"] == 214,
          str(d.evidence["eligible_event_count"]))
    check("1e. C3 passes: an attested freeze record exists",
          d.conditions["C3_frozen"] is True
          and d.evidence["frozen_event_id_count"] == 214)
    check("1f. C4 passes: the decisions are resolved in a signed dated lock",
          d.conditions["C4_decisions_resolved"] is True, str(d.denials))
    check("1f2. and no decision remains pending",
          d.evidence["pending_analysis_decisions"] == 0)
    check("1f3. while the ledger still carries all four entries -- resolution "
          "is recorded by marking, never by removing",
          d.evidence["decision_ledger_entries"] == 4)
    check("1g. C5 passes: the linkage is DERIVED non-placeholder, not asserted",
          d.conditions["C5_not_placeholder"] is True
          and d.evidence["uses_placeholder_linkage"] is False)
    check("1h. the registry threshold it read is still 193 -- opening the gate "
          "moved no threshold",
          d.evidence["registered_threshold"] == 193)
    check("1i. the frozen count and the eligible count are the SAME number -- "
          "C2 is measured against the frozen set, not a live recount",
          d.evidence["frozen_event_id_count"]
          == d.evidence["eligible_event_count"] == 214)


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


def test_6b_c4_requires_explicit_resolution_not_merely_absent_pending() -> None:
    """C4 must ask "is every decision RESOLVED?", never "is any PENDING?".

    A not-PENDING test passes on a deleted ledger, a missing state field, an
    unrecognised token and a one-character typo. All five were verified to OPEN
    this gate before C4 was rewritten -- a fail-OPEN hole in a fail-closed
    control, and the exact structure a registry edit touches by hand.

    Both directions are asserted, because a C4 hardcoded to deny would pass
    every case below and be useless: the final block builds a properly resolved
    ledger and requires the gate to OPEN through it.
    """
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        def _mutated(mutate, name: str) -> Path:
            doc = json.loads(json.dumps(_REAL))
            for h in doc["hypotheses"]:
                if h["hypothesis_id"] == "HYP-04":
                    h["status"] = "ACTIVE_COLLECTING"
                    mutate(h)
            p = tdp / f"{name}.json"
            p.write_text(json.dumps(doc), encoding="utf-8")
            return p

        tampers = {
            "ledger key deleted":
                lambda h: h.pop("unresolved_analysis_decisions", None),
            "ledger emptied":
                lambda h: h.__setitem__("unresolved_analysis_decisions", []),
            "ledger is not a list":
                lambda h: h.__setitem__("unresolved_analysis_decisions", {}),
            "state field removed":
                lambda h: [d.pop("state", None)
                           for d in h["unresolved_analysis_decisions"]],
            "state token typo'd":
                lambda h: [d.__setitem__("state", "PENDING_SEPARATE_ANALYSIS_LOK")
                           for d in h["unresolved_analysis_decisions"]],
            "state set to a made-up token":
                lambda h: [d.__setitem__("state", "probably_fine")
                           for d in h["unresolved_analysis_decisions"]],
            "entry is not an object":
                lambda h: h.__setitem__("unresolved_analysis_decisions",
                                        ["just a string"]),
            # The pop is load-bearing. This tamper used to only set the state,
            # relying on the source registry carrying no resolved_by_lock --
            # true of v1.1, false of v1.2, where every decision cites the
            # signed lock. Repointing the gate at v1.2 therefore turned this
            # case into a LEGITIMATELY resolved ledger, and it silently stopped
            # testing the thing its own name describes. The sibling case below
            # always set its field explicitly and was never affected.
            "resolved but cites no lock":
                lambda h: [(d.__setitem__("state", RESOLVED_TOKEN),
                            d.pop(RESOLVED_BY_FIELD, None))
                           for d in h["unresolved_analysis_decisions"]],
            "resolved but the cited lock is blank":
                lambda h: [(d.__setitem__("state", RESOLVED_TOKEN),
                            d.__setitem__(RESOLVED_BY_FIELD, "   "))
                           for d in h["unresolved_analysis_decisions"]],
        }
        for label, mut in tampers.items():
            reg = _mutated(mut, label.replace(" ", "_").replace("'", ""))
            d = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(),
                              registry_path=reg)
            check(f"6b. '{label}' denies C4",
                  d.conditions["C4_decisions_resolved"] is False)
            check(f"6b2. '{label}' leaves the gate CLOSED", d.open is False)

        # THE OTHER DIRECTION. Without this a C4 hardcoded to deny would pass
        # every case above.
        good = _mutated(
            lambda h: [(d.__setitem__("state", RESOLVED_TOKEN),
                        d.__setitem__(RESOLVED_BY_FIELD,
                                      "GST_HYP04_ANALYSIS_LOCK_v1.0.json"))
                       for d in h["unresolved_analysis_decisions"]],
            "properly_resolved")
        d = evaluate_gate(eligible_event_count=193, freeze=_good_freeze(),
                          registry_path=good)
        check("6b3. a properly resolved ledger CLEARS C4",
              d.conditions["C4_decisions_resolved"] is True, str(d.denials))
        check("6b4. and with all else true the gate OPENS", d.open is True,
              "if this fails, C4 is hardcoded closed and the cases above prove nothing")
        check("6b5. the decision ledger is still fully populated after resolution",
              d.evidence["decision_ledger_entries"] == 4,
              "resolution marks decisions; it never removes them")

    check("6b6. the state vocabulary is closed and holds exactly two tokens",
          DECISION_STATES == frozenset({PENDING_TOKEN, RESOLVED_TOKEN}))


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
        # and a findings panel is then permitted -- with its method provenance
        # declared. Through an OPEN gate a declaration is required: see
        # test_hyp04_supply_chain_hedge_quantum_provenance.py, which owns that
        # rule and asserts both directions of it.
        try:
            assert_display_allowed("onset_horizon", d, CLASSICAL_INTERNAL)
            check("9d. a findings panel is permitted through an OPEN gate", True)
        except (GateError, ProvenanceError):
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

        # negative / non-integer counts. True and False are included because
        # isinstance(True, int) is True in Python: without an explicit bool
        # check, a count of True would be read as 1 and a threshold of True as
        # a threshold of 1. Neither is a count, and on a fail-closed control an
        # input that means nothing must deny rather than be coerced into the
        # smallest passing value.
        for bad in (-1, "193", 193.0, True, False):
            db = evaluate_gate(eligible_event_count=bad, freeze=_good_freeze(),
                               registry_path=reg)
            check(f"10d. a non-negative-integer count {bad!r} is rejected",
                  db.open is False)
            check(f"10d2. ... and C2 is the condition that rejects {bad!r}",
                  db.conditions["C2_threshold"] is False)

        # The same coercion on the THRESHOLD side: a doctored registry whose
        # minimum_eligible_events is True must not become a threshold of 1.
        bool_thr = _registry_variant(Path(td), status="ACTIVE_COLLECTING",
                                     pending=False, threshold=True)
        dbt = evaluate_gate(eligible_event_count=1, freeze=_good_freeze(1),
                            registry_path=bool_thr)
        check("10e. a boolean registry threshold is rejected, not read as 1",
              dbt.open is False and dbt.conditions["C2_threshold"] is False)


def _closed_decision():
    """A CLOSED decision, synthesised rather than borrowed from the live gate.

    These tests are about panel CLASSIFICATION -- which ids are findings and
    which are progress -- and that question is independent of whether the real
    gate happens to be open. They used `current_decision()`, so when the gate
    opened on 2026-09-09 they stopped testing classification and started
    raising ProvenanceError from the quantum control instead.

    That is the same defect `_registry_variant` documents above: a fixture
    whose meaning depends on ambient state is not a fixture. Withholding the
    freeze denies on C2/C3/C5 regardless of what the registry says.
    """
    return evaluate_gate(eligible_event_count=0, freeze=None)


# ===================== 11. panel classification ==========================
def test_11_panel_classification_fails_closed() -> None:
    closed = _closed_decision()
    check("11z. the fixture really is closed", closed.open is False,
          str(closed.denials))

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

    # The two controls COMPOSE, and the live gate being open is what makes this
    # checkable for the first time. Opening the gate does not clear the quantum
    # control: a findings panel with no declared method provenance is still
    # refused, now by ProvenanceError rather than GateError.
    live = current_decision()
    if live.open:
        try:
            assert_display_allowed(FINDINGS_PANELS[0], live)
            check("11h. an OPEN gate still refuses undeclared provenance",
                  False, "it rendered through an open gate")
        except ProvenanceError:
            check("11h. an OPEN gate still refuses undeclared provenance", True)
        except GateError:
            check("11h. an OPEN gate still refuses undeclared provenance",
                  False, "denied by the gate, not by the provenance control")
        try:
            assert_display_allowed(FINDINGS_PANELS[0], live,
                                   provenance=CLASSICAL_INTERNAL)
            check("11i. and PERMITS a declared classical result -- the gate is "
                  "genuinely open, not merely differently locked", True)
        except Exception as exc:                   # noqa: BLE001 -- reported
            check("11i. and PERMITS a declared classical result", False,
                  f"{type(exc).__name__}: {exc}")
    else:
        skip("11h. open-gate provenance composition", "the live gate is closed")


def test_12_locked_placeholder_leaks_no_finding() -> None:
    """A locked panel must not leak magnitude, direction, or a value.

    Synthesised closed decision, not the live one: what a LOCKED panel renders
    has to be checkable whether or not the real gate is open.
    """
    closed = _closed_decision()
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
    test_1_the_live_gate_is_open_and_why()
    test_2_unknown_inputs_deny_rather_than_default()
    test_3_c1_alone_closes_the_gate()
    test_4_c2_alone_closes_the_gate()
    test_5_c3_alone_closes_the_gate()
    test_6_c4_alone_closes_the_gate()
    test_6b_c4_requires_explicit_resolution_not_merely_absent_pending()
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
