#!/usr/bin/env python3
"""Governance tests for the hypothesis-registry v1.2 ARTIFACT -- HYP-04.

Distinct from test_hyp04_supply_chain_hedge_registry_v1_2.py, which tests the
GENERATOR (that it refuses without a signed lock, and builds correctly with
one). This file governs the artifact itself: the document that ends up on disk,
however it got there. A generator that is correct today does not constrain a
file someone hand-edits tomorrow, so the artifact needs its own tests.

=== WHY THIS FILE IS NOT DEAD CODE WHILE v1.2 DOES NOT EXIST ===

The obvious way to write this -- skip everything until v1.2 appears -- produces
a file that reports SKIP for months and is never known to work. The first time
it runs for real is the moment it is trusted, which is the worst moment to
discover a broken matcher. (The v1.1 suite records exactly that failure mode in
its own test_11: a matcher that would have failed a correct document and passed
a reworded one, undetected because nothing exercised it.)

So every assertion runs twice:

  * PART A -- against a SYNTHETIC v1.2, generated in a temp directory from a
    synthetic signed lock. Always runs. Proves the checks are live.
  * PART B -- against the REAL v1.2 on disk, when it exists. Skips, explicitly
    and visibly, while it does not.

The checks are one shared function, so Part B cannot drift away from the
version that was actually exercised.

Offline. No network. The real registries are read, never written.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_2_artifact.py
"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline governance test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    DECISION_STATES,
    HYPOTHESIS_ID,
    PENDING_TOKEN,
    RESOLVED_BY_FIELD,
    RESOLVED_TOKEN,
    FreezeRecord,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.make_registry_v1_2 import (  # noqa: E402
    V1_1,
    V1_2,
    build_v1_2,
)

HERE = Path(__file__).resolve().parent
LSE = HERE / "Live Signal Engine"
V1_0 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json"

NOT_IMPL = "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED"

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("PASS: " if cond else "FAIL: ") + label
          + ("" if cond or not detail else f"   {detail}"))
    if not cond:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


SYNTHETIC_LOCK = {
    "status": "IN_FORCE",
    "in_force": True,
    "authorizer": "SYNTHETIC test authorizer -- not a real authorization",
    "operative_date": "2026-01-01",
    "no_outcome_inspected_before_signing_attested": True,
}


def _hyp(doc: dict, hid: str = HYPOTHESIS_ID) -> dict:
    return next(h for h in doc["hypotheses"] if h["hypothesis_id"] == hid)


# ======================================================================
# The shared assertions. Run against synthetic AND real v1.2.
# ======================================================================
def artifact_checks(doc: dict, n: str, *, src: dict, src_sha: str,
                    lock_dir: Optional[Path]) -> None:
    """Every property the v1.2 artifact must have, whoever authored it.

    `n` prefixes each label so synthetic and real runs are distinguishable in
    the output. `lock_dir` is where the lock named by resolved_by_lock should
    be found, or None to skip that check.
    """
    # --- version and supersession ------------------------------------
    check(f"{n} registry_version is 1.2", doc.get("registry_version") == "1.2",
          str(doc.get("registry_version")))
    check(f"{n} it supersedes v1.1 by name", doc.get("supersedes") == V1_1.name,
          str(doc.get("supersedes")))
    check(f"{n} it records v1.1's sha256, so drift is detectable",
          doc.get("supersedes_sha256") == src_sha,
          f"got {str(doc.get('supersedes_sha256'))[:16]}..., "
          f"v1.1 is {src_sha[:16]}...")
    check(f"{n} the supersession rule states v1.1 is NOT edited in place",
          "NOT edited in place" in str(doc.get("supersession_rule", "")))

    # --- the decision ledger -----------------------------------------
    entry = _hyp(doc)
    ledger = entry.get("unresolved_analysis_decisions")
    src_ledger = _hyp(src)["unresolved_analysis_decisions"]

    check(f"{n} the ledger is a non-empty list",
          isinstance(ledger, list) and bool(ledger))
    check(f"{n} no decision was added or removed",
          isinstance(ledger, list) and len(ledger) == len(src_ledger),
          f"v1.1 has {len(src_ledger)}, v1.2 has "
          f"{len(ledger) if isinstance(ledger, list) else 'n/a'}")

    if isinstance(ledger, list) and ledger:
        check(f"{n} every decision is explicitly {RESOLVED_TOKEN}",
              all(isinstance(d, dict) and d.get("state") == RESOLVED_TOKEN
                  for d in ledger))
        check(f"{n} no decision is still {PENDING_TOKEN}",
              not any(isinstance(d, dict) and d.get("state") == PENDING_TOKEN
                      for d in ledger))
        check(f"{n} no decision carries a state outside the closed vocabulary",
              all(isinstance(d, dict) and d.get("state") in DECISION_STATES
                  for d in ledger),
              f"permitted: {sorted(DECISION_STATES)}")
        check(f"{n} every decision cites a lock in {RESOLVED_BY_FIELD!r}",
              all(isinstance(d, dict)
                  and str(d.get(RESOLVED_BY_FIELD, "") or "").strip()
                  for d in ledger))
        check(f"{n} no decision TEXT was altered",
              [d.get("decision") for d in ledger]
              == [d.get("decision") for d in src_ledger])

        # A resolution that names a lock nobody can find has not shown the
        # lock exists. Checked against disk, not against the string alone.
        if lock_dir is not None:
            names = {str(d.get(RESOLVED_BY_FIELD, "")) for d in ledger
                     if isinstance(d, dict)}
            missing = [x for x in names if not (lock_dir / x).is_file()]
            check(f"{n} every cited lock actually exists on disk",
                  not missing, f"missing: {missing}")
            not_forced = []
            for x in names - set(missing):
                try:
                    lk = _load(lock_dir / x)
                except json.JSONDecodeError:
                    not_forced.append(f"{x} (unreadable)")
                    continue
                if lk.get("in_force") is not True:
                    not_forced.append(f"{x} (in_force is not true)")
            check(f"{n} every cited lock is in_force", not not_forced,
                  str(not_forced))

    # --- resolution is not activation --------------------------------
    check(f"{n} HYP-04's status is unchanged -- C4 is not C1",
          entry.get("status") == _hyp(src).get("status") == NOT_IMPL,
          str(entry.get("status")))
    check(f"{n} the event threshold is unchanged",
          entry.get("minimum_eligible_events")
          == _hyp(src).get("minimum_eligible_events"))
    check(f"{n} HYP-04 is still not primary/confirmatory",
          entry.get("is_primary_confirmatory") is False)

    # --- nothing else moved ------------------------------------------
    # v1.1's `hypotheses` list carries ONLY HYP-04. HYP-01/02/03 are defined in
    # v1.0 and incorporated by reference, precisely so there are never two
    # mutable copies of the same governed text. So "the other three are
    # unchanged" cannot be checked by diffing this list -- an earlier draft of
    # this file did exactly that and compared [] to [], a dead assertion that
    # passed against any document. The guarantee lives in two other places, and
    # that is where it is checked: the reference block, and v1.0's byte
    # identity (Part C).
    check(f"{n} the hypotheses list still carries ONLY {HYPOTHESIS_ID}",
          [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
          == [HYPOTHESIS_ID],
          "restating HYP-01/02/03 here would create a second mutable copy")
    check(f"{n} the carried-forward reference block is unchanged",
          doc.get("hypotheses_carried_forward_unchanged")
          == src.get("hypotheses_carried_forward_unchanged"))
    check(f"{n} it still requires v1.0 to remain byte-identical",
          doc.get("hypotheses_carried_forward_unchanged", {})
          .get("v1_0_must_remain_byte_identical") is True)
    check(f"{n} the options-eligibility position is unchanged",
          doc.get("options_related_classes") == src.get("options_related_classes"))
    check(f"{n} the status vocabulary was not widened",
          doc.get("statuses") == src.get("statuses"))
    check(f"{n} no top-level key was dropped",
          set(src).issubset(set(doc)),
          f"missing: {sorted(set(src) - set(doc))}")

    # --- no result leaked in -----------------------------------------
    counts = doc.get("eligible_event_counts", {})
    check(f"{n} every eligible-event count is still zero",
          all(v == 0 for k, v in counts.items() if k != "note"), str(counts))
    check(f"{n} results are still null", doc.get("results") is None,
          str(doc.get("results")))
    blob = json.dumps(doc).lower()
    for phrase in ("hedging edge", "profitable", "outperform",
                   "we find that", "results show", "demonstrates that"):
        check(f"{n} it never asserts '{phrase}'", phrase not in blob)


# ======================================================================
# PART A -- synthetic v1.2. Always runs.
# ======================================================================
def test_a_synthetic_artifact() -> None:
    print("\n--- PART A: synthetic v1.2 (proves the checks above are live) ---")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        lock = td / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
        lock.write_text(json.dumps(SYNTHETIC_LOCK), encoding="utf-8")
        doc, _ = build_v1_2(v1_1=V1_1, signed_lock=lock)
        artifact_checks(doc, "A.", src=_load(V1_1), src_sha=_sha256(V1_1),
                        lock_dir=td)


# ======================================================================
# PART A2 -- negative controls. The checks must CATCH a bad artifact.
# ======================================================================
# Part A proves the checks run. It does not prove they can fail: a function
# that checked nothing at all would pass Part A completely. This project's
# standing lesson is the hardcoded-open/hardcoded-closed split -- a
# one-directional test is satisfiable by a degenerate implementation -- so
# every tamper below must be caught, individually.
def _failures_against(doc: dict, lock_dir: Optional[Path]) -> list[str]:
    """Run artifact_checks against `doc` silently; return what it flagged."""
    import contextlib
    import io

    global FAILURES
    saved, FAILURES = FAILURES, []
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            artifact_checks(doc, "neg.", src=_load(V1_1),
                            src_sha=_sha256(V1_1), lock_dir=lock_dir)
        return FAILURES
    finally:
        FAILURES = saved


def test_a2_negative_controls() -> None:
    print("\n--- PART A2: negative controls (each tamper must be caught) ---")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        lock = td / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
        lock.write_text(json.dumps(SYNTHETIC_LOCK), encoding="utf-8")
        good, _ = build_v1_2(v1_1=V1_1, signed_lock=lock)

        # Baseline: the untampered document must be clean, or every negative
        # below would "pass" for the wrong reason.
        base = _failures_against(good, td)
        check("A2. baseline -- the untampered synthetic artifact is clean",
              base == [], str(base))

        def tamper(label: str, mutate) -> None:
            import copy as _copy
            d = _copy.deepcopy(good)
            mutate(d)
            found = _failures_against(d, td)
            check(f"A2. caught: {label}", bool(found),
                  "the tamper went undetected")

        def _led(d: dict) -> list:
            return _hyp(d)["unresolved_analysis_decisions"]

        tamper("a decision flipped back to PENDING",
               lambda d: _led(d)[0].__setitem__("state", PENDING_TOKEN))
        tamper("a decision's state removed",
               lambda d: _led(d)[1].pop("state"))
        tamper("a decision's state typo'd",
               lambda d: _led(d)[0].__setitem__("state", "RESOLVED_IN_DATED_LOK"))
        tamper(f"{RESOLVED_BY_FIELD} dropped",
               lambda d: _led(d)[2].pop(RESOLVED_BY_FIELD))
        tamper(f"{RESOLVED_BY_FIELD} blanked",
               lambda d: _led(d)[2].__setitem__(RESOLVED_BY_FIELD, "   "))
        tamper("the cited lock does not exist on disk",
               lambda d: [x.__setitem__(RESOLVED_BY_FIELD, "NO_SUCH_LOCK.json")
                          for x in _led(d)])
        tamper("a decision deleted from the ledger",
               lambda d: _led(d).pop())
        tamper("the ledger emptied",
               lambda d: _hyp(d).__setitem__("unresolved_analysis_decisions", []))
        tamper("a decision's TEXT rewritten",
               lambda d: _led(d)[0].__setitem__("decision", "something else"))
        tamper("HYP-04 promoted to ACTIVE_COLLECTING",
               lambda d: _hyp(d).__setitem__("status", "ACTIVE_COLLECTING"))
        tamper("HYP-04 made primary/confirmatory",
               lambda d: _hyp(d).__setitem__("is_primary_confirmatory", True))
        tamper("the event threshold lowered",
               lambda d: _hyp(d).__setitem__("minimum_eligible_events", 1))
        tamper("supersedes_sha256 corrupted",
               lambda d: d.__setitem__("supersedes_sha256", "0" * 64))
        tamper("registry_version left at 1.1",
               lambda d: d.__setitem__("registry_version", "1.1"))
        tamper("a top-level key dropped",
               lambda d: d.pop("statistical_governance"))
        tamper("the status vocabulary widened",
               lambda d: d["statuses"].__setitem__("INVENTED", "a new status"))
        tamper("HYP-01 restated into the hypotheses list",
               lambda d: d["hypotheses"].append(
                   {"hypothesis_id": "HYP-01", "status": "ACTIVE_COLLECTING"}))
        tamper("the carried-forward reference block edited",
               lambda d: d["hypotheses_carried_forward_unchanged"]
               .__setitem__("unchanged_hypothesis_ids", ["HYP-01"]))
        tamper("v1.0's byte-identity requirement revoked",
               lambda d: d["hypotheses_carried_forward_unchanged"]
               .__setitem__("v1_0_must_remain_byte_identical", False))
        tamper("the options position opened",
               lambda d: d["options_related_classes"].__setitem__(
                   "result_display_status", "ALLOW"))
        tamper("a nonzero eligible-event count",
               lambda d: d["eligible_event_counts"].__setitem__("HYP-04", 193))
        tamper("a result attached",
               lambda d: d.__setitem__("results", {"beta": 0.4}))
        tamper("an edge claim injected",
               lambda d: d.__setitem__("change_summary", "demonstrates that "
                                       "a hedging edge exists"))


# ======================================================================
# PART B -- the real artifact, when it exists.
# ======================================================================
def test_b_real_artifact() -> None:
    print("\n--- PART B: the real v1.2 on disk ---")
    if not V1_2.is_file():
        skip("B. real registry v1.2 governance",
             f"{V1_2.name} does not exist yet -- the analysis lock is unsigned. "
             "Part A still exercised every assertion.")
        return
    artifact_checks(_load(V1_2), "B.", src=_load(V1_1), src_sha=_sha256(V1_1),
                    lock_dir=LSE)


# ======================================================================
# Predecessors are never edited in place. Always runs.
# ======================================================================
def test_c_predecessors_untouched() -> None:
    print("\n--- PART C: predecessors ---")
    for p, want in ((V1_0, "1.0"), (V1_1, "1.1")):
        if not p.is_file():
            skip(f"C. {p.name} present", "file not found")
            continue
        d = _load(p)
        check(f"C. {p.name} still reports registry_version {want}",
              str(d.get("registry_version")) == want)
        led = _hyp(d)["unresolved_analysis_decisions"] if any(
            h["hypothesis_id"] == HYPOTHESIS_ID for h in d["hypotheses"]) else None
        if p is V1_1:
            check("C. v1.1's own ledger is still entirely PENDING",
                  led is not None
                  and all(x.get("state") == PENDING_TOKEN for x in led),
                  "v1.1 must not be edited in place when v1.2 is authored")


# ======================================================================
# The gate agrees with the artifact. Always runs (synthetic), plus real.
# ======================================================================
GOOD_FREEZE = FreezeRecord(
    frozen=True,
    eligible_event_ids=tuple(f"E{i}" for i in range(193)),
    analysis_commit_sha="0" * 40,
    analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
    frozen_before_any_result_computed=True,
    uses_placeholder_linkage=False,
)


def _gate_checks(path: Path, n: str) -> None:
    d = evaluate_gate(eligible_event_count=193, freeze=GOOD_FREEZE,
                      registry_path=path)
    check(f"{n} C4 CLEARS against this artifact",
          d.conditions["C4_decisions_resolved"] is True, str(d.denials))
    check(f"{n} zero decisions remain pending",
          d.evidence["pending_analysis_decisions"] == 0)
    check(f"{n} the ledger still reports its entries",
          d.evidence["decision_ledger_entries"] == 4,
          str(d.evidence.get("decision_ledger_entries")))
    check(f"{n} C1 still FAILS -- resolution is not activation",
          d.conditions["C1_status"] is False)
    check(f"{n} the gate is still CLOSED", d.open is False)


def test_d_gate_agreement() -> None:
    print("\n--- PART D: the display gate agrees ---")
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        lock = td / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
        lock.write_text(json.dumps(SYNTHETIC_LOCK), encoding="utf-8")
        doc, _ = build_v1_2(v1_1=V1_1, signed_lock=lock)
        p = td / "synthetic_v1_2.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        _gate_checks(p, "D.A")

    if V1_2.is_file():
        _gate_checks(V1_2, "D.B")
    else:
        skip("D.B gate against the real v1.2", f"{V1_2.name} does not exist yet")

    # Control: C4 must still FAIL against v1.1. Without this, every check
    # above would pass if C4 broke open again.
    d = evaluate_gate(eligible_event_count=193, freeze=GOOD_FREEZE,
                      registry_path=V1_1)
    check("D. CONTROL -- C4 still FAILS against the unmodified v1.1",
          d.conditions["C4_decisions_resolved"] is False)


def test_e_real_files_not_written() -> None:
    before = _sha256(V1_1)
    with tempfile.TemporaryDirectory() as t:
        lock = Path(t) / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
        lock.write_text(json.dumps(SYNTHETIC_LOCK), encoding="utf-8")
        build_v1_2(v1_1=V1_1, signed_lock=lock)
    check("E. this suite never modifies registry v1.1", _sha256(V1_1) == before)


def test_f_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("F. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("F. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_a_synthetic_artifact()
    test_a2_negative_controls()
    test_b_real_artifact()
    test_c_predecessors_untouched()
    test_d_gate_agreement()
    test_e_real_files_not_written()
    test_f_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.2 ARTIFACT TESTS PASSED")
    sys.exit(0)
