#!/usr/bin/env python3
"""Tests for registry v1.9 -- HYP-04's anchor side, stated in its own terms.

v1.9 is a DIFFERENT KIND of version from v1.6/v1.7/v1.8. Those corrected the
corpus reading and froze the hypothesis specification. This one changes the
specification, and the risk profile inverts with it.

=== THE RISK THAT DEFINES THIS SUITE ===

A version permitted to move a specification field is a version that could move
others. So the exception is asserted to be EXACTLY ONE FIELD, named:

  * `required_eligibility_class` moved, and nothing else in
    IMMOVABLE_HYP04_FIELDS did (test_c)
  * membership is byte-identical to v1.8 -- this version is not about the
    universe, and if it moved one the guard failed (test_c)
  * the threshold is still 193 anchor events, and every eligible-event counter
    is still zero (test_e)

=== AND THE RISK THAT THE REGISTRY DESCRIBES A REPOSITORY THAT DOES NOT EXIST ===

v1.7's docstring records that failure: code implementing one thing, an
authoritative registry describing another, no test able to see it. v1.9's
generator refuses to run while `pair_eligibility` still enforces the attention
class. test_f asserts that refusal FIRES -- a guard nobody has seen fail is not
known to work.

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_9.py
"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
from pathlib import Path
from unittest import mock


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge import anchor_shock as ashock  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    REGISTRY_CURRENT,
    current_decision,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    IMMOVABLE_HYP04_FIELDS,
    LSE,
)
from hyp04_supply_chain_hedge.make_registry_v1_9 import (  # noqa: E402
    SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE,
    V1_8,
    V1_9,
    RefusedError,
    build_v1_9,
    check_preconditions,
    code_disagreements,
)

V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
HYPOTHESIS_ID = "HYP-04"

# Pinned when v1.9 was authored. Every predecessor is append-only.
V1_8_SHA256 = "574baa5dc4b86b73b4f76ea4b265f40ef77b10765947c8ac028e38f4ce0a75d5"

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


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _hyp(doc: dict) -> dict:
    return next(h for h in doc["hypotheses"]
                if h["hypothesis_id"] == HYPOTHESIS_ID)


def test_a_the_published_artifact() -> None:
    print("\n--- PART A: the artifact exists and supersedes v1.8 ---")
    if not V1_9.is_file():
        skip("A. v1.9", "artifact absent")
        return
    doc = _load(V1_9)
    check("A1. it declares version 1.9", doc.get("registry_version") == "1.9",
          str(doc.get("registry_version")))
    check("A2. it supersedes v1.8 by name", doc.get("supersedes") == V1_8.name,
          str(doc.get("supersedes")))
    check("A3. and by the hash v1.8 actually has",
          doc.get("supersedes_sha256") == _sha256(V1_8),
          str(doc.get("supersedes_sha256")))
    check("A4. results are still null -- v1.9 reports nothing",
          doc.get("results") is None, str(doc.get("results"))[:80])


def test_b_the_shock_is_declared_not_paraphrased() -> None:
    print("\n--- PART B: the shock rule is declared from the rule ---")
    if not V1_9.is_file():
        skip("B. shock block", "artifact absent")
        return
    blk = _hyp(_load(V1_9)).get("anchor_shock")
    check("B1. the block exists", isinstance(blk, dict))
    if not isinstance(blk, dict):
        return
    again = ashock.rule_description()
    check("B2. every declared field re-derives from the rule itself",
          {k: blk.get(k) for k in again} == again,
          str([k for k in again if blk.get(k) != again[k]]))
    check("B3. it names the rule", blk.get("rule_id") == ashock.ANCHOR_SHOCK_RULE_ID)
    check("B4. the formula is stated in full",
          blk.get("shock_definition")
          == "abs(anchor_return - beta * benchmark_return)",
          str(blk.get("shock_definition")))
    check("B5. beta is declared NOT estimated -- an estimation window chosen "
          "after seeing results is the tuning this project forbids",
          blk.get("beta_is_estimated") is False)
    check("B6. AS-1..AS-6 are carried, not summarised",
          [c["id"] for c in blk.get("conditions", [])]
          == [c for c, _ in ashock.RULE_CONDITIONS])
    check("B7. it records the owner's decision and its dated basis",
          "INFORMATION TRANSMISSION" in str(blk.get("decided_by", ""))
          and str(blk.get("decision_basis", "")).endswith("2026-08-29.md"),
          str(blk.get("decision_basis")))
    check("B8. and what it replaced, including the cost of the old class",
          "two attention series and an option chain"
          in str(blk.get("what_it_replaced", "")))
    check("B9. it states NOTHING has been computed",
          "not computed data" in str(blk.get("measurement_status", "")))
    check("B10. the day-0 reference-window issue is carried as OPEN, not "
          "silently inherited",
          any("anchor_day + 1" in str(l) and "NOT RESOLVED" in str(l)
              for l in blk.get("known_limitations", [])),
          str(blk.get("known_limitations"))[:120])


def test_c_exactly_one_field_moved() -> None:
    """THE LOAD-BEARING TEST. A version allowed to move a specification field
    is a version that could move others."""
    print("\n--- PART C: the exception is exactly one field, by name ---")
    if not V1_9.is_file() or not V1_8.is_file():
        skip("C. immovability", "artifact absent")
        return
    new, old = _hyp(_load(V1_9)), _hyp(_load(V1_8))

    check("C1. the permitted exception is a single named field",
          SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE
          == ("required_eligibility_class",),
          str(SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE))
    check("C2. it DID move",
          new.get("required_eligibility_class")
          != old.get("required_eligibility_class"),
          str(new.get("required_eligibility_class")))
    check("C3. and now names HYP-04's own rule, not a gst_market_response class",
          new.get("required_eligibility_class") == ashock.ANCHOR_SHOCK_RULE_ID,
          str(new.get("required_eligibility_class")))
    for f in IMMOVABLE_HYP04_FIELDS:
        if f in SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
            continue
        check(f"C4. still immovable: {f}", new.get(f) == old.get(f),
              f"{old.get(f)!r} -> {new.get(f)!r}"[:120])
    check("C5. MEMBERSHIP is byte-identical -- v1.9 is not about the universe",
          new.get("anchor_universe") == old.get("anchor_universe"))
    check("C6. the four analysis decisions are untouched, so C4 is not "
          "disturbed by a specification change",
          new.get("unresolved_analysis_decisions")
          == old.get("unresolved_analysis_decisions"))


def test_d_the_peer_side_is_unchanged() -> None:
    print("\n--- PART D: only the ANCHOR side moved ---")
    if not V1_9.is_file() or not V1_8.is_file():
        skip("D. peer side", "artifact absent")
        return
    new, old = _load(V1_9), _load(V1_8)
    check("D1. peer_price_data_policy unchanged",
          new.get("peer_price_data_policy") == old.get("peer_price_data_policy"))
    check("D2. required_external_measurement (the linkage map) unchanged",
          _hyp(new).get("required_external_measurement")
          == _hyp(old).get("required_external_measurement"))
    check("D3. the note still records that the PEER side has no class anywhere",
          "PEER side still has no eligibility class"
          in str(_hyp(new).get("required_eligibility_class_note", "")))


def test_e_the_gate_did_not_move() -> None:
    print("\n--- PART E: the display gate ---")
    check("E1. the gate reads the v1.9 artifact",
          REGISTRY_CURRENT.name.endswith("v1.9.json"), REGISTRY_CURRENT.name)
    d = current_decision()
    check("E2. it is CLOSED", d.open is False, str(d.conditions))
    check("E3. with exactly 4 denials", len(d.denials) == 4, str(d.denials))
    check("E4. and C4 MET", d.conditions["C4_decisions_resolved"] is True)
    check("E5. C2 still FAILS -- defining a shock creates no eligible event",
          d.conditions["C2_threshold"] is False)
    if V1_9.is_file():
        doc = _load(V1_9)
        counts = doc.get("eligible_event_counts") or {}
        nums = {k: v for k, v in counts.items() if isinstance(v, int)}
        check("E6. every eligible-event counter is still zero",
              bool(nums) and all(v == 0 for v in nums.values()), str(nums))
        e = _hyp(doc)
        check("E7. HYP-04's status is unchanged",
              e.get("status") == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
              str(e.get("status")))
        check("E8. the threshold is still 193 ANCHOR EVENTS",
              e.get("minimum_eligible_events") == 193
              and e.get("minimum_eligible_events_unit") == "eligible anchor events",
              f"{e.get('minimum_eligible_events')} "
              f"{e.get('minimum_eligible_events_unit')}")
    if V1_1.is_file():
        g1 = evaluate_gate(eligible_event_count=193, registry_path=V1_1)
        check("E9. CONTROL -- C4 still FAILS against the unmodified v1.1",
              g1.conditions["C4_decisions_resolved"] is False)


def test_f_the_code_agreement_guard_actually_fires() -> None:
    """A guard nobody has seen fail is not known to work.

    v1.9 refuses to describe a repository that does not implement it. This
    forces each disagreement and asserts the refusal.
    """
    print("\n--- PART F: the generator refuses to outrun the code ---")
    check("F1. with the real repository, there is no disagreement",
          code_disagreements() == [], str(code_disagreements()))
    check("F2. it refuses to overwrite the published v1.9",
          any("already exists" in r for r in check_preconditions()),
          str(check_preconditions()))

    # HARDCODED-OPEN CONTROL 1: the pair module still takes the old parameter.
    def _old_sig(edge, *, event_id=None, event_date=None,
                 event_anchor_ticker=None, anchor_eligibility=None,
                 peer_history_available=None, from_placeholder_linkage=False):
        raise AssertionError("not called")

    with mock.patch("hyp04_supply_chain_hedge.pair_eligibility.evaluate_pair",
                    _old_sig):
        probs = code_disagreements()
        check("F3. a pair module still taking `anchor_eligibility` is caught",
              any("anchor_eligibility" in p for p in probs), str(probs)[:140])
        try:
            build_v1_9()
            check("F4. and the build REFUSES", False, "it built")
        except RefusedError as e:
            check("F4. and the build REFUSES",
                  "does not implement" in str(e), str(e)[:120])

    # HARDCODED-OPEN CONTROL 2: an estimated beta must be refused outright.
    with mock.patch.object(ashock, "BENCHMARK_BETA", 1.23):
        probs = code_disagreements()
        check("F5. an estimated/altered beta is caught",
              any("estimated beta" in p for p in probs), str(probs)[:140])

    check("F6. and the guards are clean again afterwards",
          code_disagreements() == [], str(code_disagreements()))


def test_g_no_side_effects() -> None:
    print("\n--- PART G: no side effects ---")
    check("G1. v1.8 is unchanged -- including the inherited eligibility class "
          "v1.9 replaces",
          _sha256(V1_8) == V1_8_SHA256, _sha256(V1_8))
    if V1_9.is_file() and V1_8.is_file():
        new, old = _load(V1_9), _load(V1_8)
        check("G2. v1.9 still parses and reports 1.9",
              new.get("registry_version") == "1.9")
        check("G3. statistical_governance unchanged",
              new.get("statistical_governance")
              == old.get("statistical_governance"))
        check("G4. the hypothesis list is unchanged",
              [h["hypothesis_id"] for h in new["hypotheses"]]
              == [h["hypothesis_id"] for h in old["hypotheses"]])


def test_h_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("H1. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("H1. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_a_the_published_artifact()
    test_b_the_shock_is_declared_not_paraphrased()
    test_c_exactly_one_field_moved()
    test_d_the_peer_side_is_unchanged()
    test_e_the_gate_did_not_move()
    test_f_the_code_agreement_guard_actually_fires()
    test_g_no_side_effects()
    test_h_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.9 TESTS PASSED")
