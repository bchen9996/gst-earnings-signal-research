#!/usr/bin/env python3
"""Tests for the registry v1.2 generator -- HYP-04.

The generator writes a governance artifact, so the load-bearing property is
that it REFUSES far more often than it runs. Tests are written accordingly, and
in both directions, because a generator hardcoded to refuse would pass every
refusal test and be useless:

  * every precondition is falsified individually and must refuse on its own
    (test_2)
  * a fully signed lock must actually produce a correct v1.2 (test_3)

The end-to-end property that matters most is test_4: the generated v1.2, fed to
the real display gate, actually CLEARS C4 -- and clears nothing else. Without
that, the generator and the gate could each be internally consistent while
disagreeing about the schema.

Offline. No network. Synthetic locks in temp directories; the real registry is
read but never written.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_2.py
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
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    PENDING_TOKEN,
    RESOLVED_BY_FIELD,
    RESOLVED_TOKEN,
    FreezeRecord,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.make_registry_v1_2 import (  # noqa: E402
    SIGNED_LOCK,
    V1_1,
    V1_2,
    build_v1_2,
    check_preconditions,
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


SIGNED = {
    "status": "IN_FORCE",
    "in_force": True,
    "authorizer": "SYNTHETIC test authorizer -- not a real authorization",
    "operative_date": "2026-01-01",
    "no_outcome_inspected_before_signing_attested": True,
}


def _write_lock(td: Path, **overrides) -> Path:
    doc = dict(SIGNED)
    doc.update(overrides)
    p = td / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _absent(td: Path) -> Path:
    return td / "GST_HYP04_ANALYSIS_LOCK_v1.0.json"


# ================= 1. the live repo state ================================
def test_1_live_repo_state() -> None:
    """What the REAL repo permits right now, and why.

    This test used to assert "no signed lock exists, so generation is refused".
    That was true when written and became false on 2026-08-20 when the lock was
    signed -- a legitimate change in the world, not a regression. Asserting a
    transient state was the defect: the test had to be rewritten the moment the
    thing it described stopped being true.

    It now asserts invariants that survive the transition. Generation is
    permitted exactly while a signed lock exists AND v1.2 does not; once v1.2
    is authored the only remaining refusal must be the no-overwrite guard. Both
    sides are checked, so this test does not need rewriting again after the
    registry is bumped.
    """
    refusals = check_preconditions()

    check("1a. a signed lock exists (not the _DRAFT)", SIGNED_LOCK.is_file(),
          f"expected {SIGNED_LOCK.name}")
    if not SIGNED_LOCK.is_file():
        skip("1b-1f. signed-lock content", "no signed lock to inspect")
        return

    lock = json.loads(SIGNED_LOCK.read_text(encoding="utf-8-sig"))
    check("1b. it declares in_force", lock.get("in_force") is True)
    check("1c. its status is not a draft status",
          str(lock.get("status", "")).upper() not in
          {"DRAFT", "DRAFT_UNSIGNED", "UNSIGNED", "PROPOSED"},
          str(lock.get("status")))
    check("1d. it names an authorizer and an operative date",
          bool(str(lock.get("authorizer") or "").strip())
          and bool(str(lock.get("operative_date") or "").strip()))
    check("1e. it attests no outcome was inspected before signing",
          lock.get("no_outcome_inspected_before_signing_attested") is True)

    # The permitted/refused state is a function of whether v1.2 exists yet.
    if V1_2.exists():
        check("1f. with v1.2 present, the ONLY refusal is the no-overwrite guard",
              bool(refusals) and all("already exists" in r for r in refusals),
              str(refusals))
    else:
        check("1f. with v1.2 absent and the lock signed, generation is permitted",
              refusals == [], str(refusals))


# ================= 2. each precondition falsified ALONE ====================
def test_2_each_precondition_refuses_on_its_own() -> None:
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        absent_v12 = td / "no_such_v1_2.json"

        # Precondition: a fully signed lock is clear to run. Without this the
        # falsifications below could refuse for an unrelated reason.
        ok = check_preconditions(signed_lock=_write_lock(td), v1_1=V1_1,
                                 v1_2=absent_v12)
        check("2a. precondition -- a fully signed lock is clear to run",
              ok == [], str(ok))

        cases = {
            "status still DRAFT_UNSIGNED": {"status": "DRAFT_UNSIGNED"},
            "status missing": {"status": ""},
            "in_force not true": {"in_force": False},
            "in_force absent": {"in_force": None},
            "no authorizer": {"authorizer": ""},
            "no operative_date": {"operative_date": ""},
            "no no-outcome attestation": {
                "no_outcome_inspected_before_signing_attested": False},
        }
        for label, override in cases.items():
            lock = _write_lock(td, **override)
            refusals = check_preconditions(signed_lock=lock, v1_1=V1_1,
                                           v1_2=absent_v12)
            check(f"2b. '{label}' alone refuses", bool(refusals))

        # An existing v1.2 is never silently overwritten.
        existing = td / "already_there.json"
        existing.write_text("{}", encoding="utf-8")
        refusals = check_preconditions(signed_lock=_write_lock(td), v1_1=V1_1,
                                       v1_2=existing)
        check("2c. an existing v1.2 refuses rather than being overwritten",
              any("already exists" in r for r in refusals), str(refusals))

        # A missing signed lock refuses.
        refusals = check_preconditions(signed_lock=_absent(td / "nope"),
                                       v1_1=V1_1, v1_2=absent_v12)
        check("2d. an absent signed lock refuses", bool(refusals))


# ================= 3. the other direction: it CAN build ====================
def test_3_a_signed_lock_produces_a_correct_v1_2() -> None:
    """Without this, a generator hardcoded to refuse would pass everything."""
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        lock = _write_lock(td)
        doc, changes = build_v1_2(v1_1=V1_1, signed_lock=lock)

        check("3a. it builds", isinstance(doc, dict))
        check("3b. version is bumped to 1.2", doc["registry_version"] == "1.2")
        check("3c. it supersedes v1.1 by name",
              doc["supersedes"] == V1_1.name)
        check("3d. it records v1.1's hash so drift is detectable",
              len(str(doc.get("supersedes_sha256", ""))) == 64)
        check("3e. the supersession rule says v1.1 is NOT edited in place",
              "NOT edited in place" in doc["supersession_rule"])

        entry = next(h for h in doc["hypotheses"] if h["hypothesis_id"] == "HYP-04")
        ledger = entry["unresolved_analysis_decisions"]

        check("3f. all four decisions are present after resolution",
              len(ledger) == 4, f"got {len(ledger)}")
        check("3g. every decision is explicitly RESOLVED",
              all(d["state"] == RESOLVED_TOKEN for d in ledger))
        check("3h. every decision cites the lock",
              all(d.get(RESOLVED_BY_FIELD) == lock.name for d in ledger))
        check("3i. no decision text was altered",
              [d["decision"] for d in ledger]
              == [d["decision"] for d in
                  next(h for h in json.loads(V1_1.read_text(encoding="utf-8-sig"))
                       ["hypotheses"] if h["hypothesis_id"] == "HYP-04")
                  ["unresolved_analysis_decisions"]])
        check("3j. four resolutions are reported",
              sum(1 for c in changes if c.startswith("resolved:")) == 4)

        # Nothing else moves.
        src = json.loads(V1_1.read_text(encoding="utf-8-sig"))
        check("3k. HYP-04's status is unchanged -- C4 is not C1",
              entry["status"] == next(
                  h for h in src["hypotheses"]
                  if h["hypothesis_id"] == "HYP-04")["status"])
        # v1.1's `hypotheses` list carries ONLY HYP-04 -- HYP-01/02/03 live in
        # v1.0 and are incorporated by reference so there are never two mutable
        # copies of the same governed text. This check used to diff the list
        # filtered to "not HYP-04", which compares [] to [] and passes against
        # any document whatsoever. It is checked where the guarantee actually
        # lives instead.
        check("3l. the hypotheses list still carries ONLY HYP-04",
              [h.get("hypothesis_id") for h in doc["hypotheses"]] == ["HYP-04"])
        check("3m. the carried-forward reference block is untouched",
              doc.get("hypotheses_carried_forward_unchanged")
              == src.get("hypotheses_carried_forward_unchanged"))
        check("3n. options-eligibility position is unchanged",
              doc["options_related_classes"] == src["options_related_classes"])
        check("3o. no top-level key was dropped",
              set(src).issubset(set(doc)),
              f"missing: {sorted(set(src) - set(doc))}")


# ================= 4. end-to-end: it clears C4, and only C4 ================
def test_4_generated_v1_2_clears_c4_in_the_real_gate() -> None:
    """The generator and the gate must agree on the schema, not just severally.

    Feeds the generated document to the real evaluate_gate and checks that C4
    flips -- and that nothing else does.
    """
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        doc, _ = build_v1_2(v1_1=V1_1, signed_lock=_write_lock(td))
        p = td / "generated_v1_2.json"
        p.write_text(json.dumps(doc), encoding="utf-8")

        good_freeze = FreezeRecord(
            frozen=True,
            eligible_event_ids=tuple(f"E{i}" for i in range(193)),
            analysis_commit_sha="0" * 40,
            analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
            frozen_before_any_result_computed=True,
            uses_placeholder_linkage=False,
        )

        d = evaluate_gate(eligible_event_count=193, freeze=good_freeze,
                          registry_path=p)
        check("4a. C4 CLEARS against the generated v1.2",
              d.conditions["C4_decisions_resolved"] is True, str(d.denials))
        check("4b. C1 still fails -- resolution is not activation",
              d.conditions["C1_status"] is False)
        check("4c. the gate is still CLOSED", d.open is False)
        check("4d. the ledger still reports four entries",
              d.evidence["decision_ledger_entries"] == 4)
        check("4e. zero decisions remain pending",
              d.evidence["pending_analysis_decisions"] == 0)

        # Control: against the REAL v1.1, C4 must still fail. Without this, 4a
        # could pass because C4 is broken open again.
        d2 = evaluate_gate(eligible_event_count=193, freeze=good_freeze,
                           registry_path=V1_1)
        check("4f. CONTROL -- C4 still FAILS against the unmodified v1.1",
              d2.conditions["C4_decisions_resolved"] is False)
        check("4g. and v1.1 still reports four pending decisions",
              d2.evidence["pending_analysis_decisions"] == 4)


# ================= 5. the real registries are never written ================
def test_5_real_registry_files_are_not_touched() -> None:
    """build_v1_2() is PURE -- it returns a document and writes nothing.

    5b used to assert `not V1_2.exists()`. That was the right intent expressed
    the wrong way: "v1.2 does not exist" was equivalent to "build wrote nothing"
    only while v1.2 had not been authored yet. Once it was authored on
    2026-08-20 the check failed for a reason with nothing to do with purity.
    It now compares bytes before and after, exactly as 5a does for v1.1, and
    holds whether or not v1.2 exists on disk.
    """
    before_v1_1 = V1_1.read_bytes()
    before_v1_2 = V1_2.read_bytes() if V1_2.exists() else None

    with tempfile.TemporaryDirectory() as t:
        build_v1_2(v1_1=V1_1, signed_lock=_write_lock(Path(t)))

    check("5a. building does not modify registry v1.1 on disk",
          V1_1.read_bytes() == before_v1_1)
    after_v1_2 = V1_2.read_bytes() if V1_2.exists() else None
    check("5b. building neither creates nor modifies registry v1.2 on disk",
          after_v1_2 == before_v1_2,
          "build_v1_2 must be pure; only main(--write) may write")

    v1_0 = V1_1.parent / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json"
    if v1_0.is_file():
        doc = json.loads(v1_0.read_text(encoding="utf-8-sig"))
        check("5c. registry v1.0 still reports itself as version 1.0",
              str(doc.get("registry_version")) == "1.0")
    else:
        skip("5c. registry v1.0 present", "file not found")


def test_6_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("6a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("6a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_live_repo_state()
    test_2_each_precondition_refuses_on_its_own()
    test_3_a_signed_lock_produces_a_correct_v1_2()
    test_4_generated_v1_2_clears_c4_in_the_real_gate()
    test_5_real_registry_files_are_not_touched()
    test_6_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.2 GENERATOR TESTS PASSED")
    sys.exit(0)
