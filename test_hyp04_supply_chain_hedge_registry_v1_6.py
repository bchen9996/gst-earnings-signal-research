#!/usr/bin/env python3
"""Tests for registry v1.6 -- point-in-time HYP-04 anchor-universe membership.

v1.6 replaces v1.5's single as-of-cutoff snapshot with membership INTERVALS,
because the snapshot was derived from each filer's newest 10-K only and
therefore let persistence of the relationship to the present day decide
membership -- the survivorship selection v1.5's own peer_price_data_policy
forbids on the peer side.

=== THE RISK IS THAT THE RULE QUIETLY CHANGES WITH THE CORPUS ===

v1.6 is allowed to change WHEN the rule is evaluated. It is not allowed to
change WHAT the rule says. test_c pins every rule-describing field in the
universe block to v1.5's, byte for byte: the conditions, the rejected
conditions, the 10% threshold, the consolidated-revenue denominator, and the
statement that those parameters are ASC 280's rather than chosen. If a future
corpus ever tempts someone to loosen the rule so that more tickers qualify,
that test fails rather than the universe quietly growing.

=== AND THAT THE PUBLISHED INTERVALS STOP FOLLOWING FROM THE HISTORY ===

test_b re-derives the intervals from the history the artifact pins by hash and
requires them to match exactly. A registry that merely SAYS its universe is
derived is worth nothing.

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_6.py
"""
from __future__ import annotations

import copy
import hashlib
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

from hyp04_supply_chain_hedge import anchor_universe as au  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    REGISTRY_CURRENT,
    FreezeRecord,
    current_decision,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (  # noqa: E402
    HISTORY,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RULE_FIELDS_THAT_MUST_NOT_MOVE,
    V1_5,
    V1_6,
    RefusedError,
    build_v1_6,
    check_preconditions,
)

V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
V1_4 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json"
HYPOTHESIS_ID = "HYP-04"

# Pinned when v1.6 was authored. Both predecessors are append-only.
V1_4_SHA256 = "b7900bcd5c6676da1221dcdcf5287f3d1dca44d831ab9955a3f057a9c8bf4419"
V1_5_SHA256 = "731ee4f2228477ee6e9200452430eb41b45fe0e0ed3a0c5af995b4b9e7439bdc"

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
    print("\n--- PART A: the published v1.6 ---")
    if not V1_6.is_file():
        skip("A. registry v1.6 present", f"{V1_6.name} not on disk")
        return
    doc = _load(V1_6)
    check("A1. it reports registry_version 1.6",
          str(doc.get("registry_version")) == "1.6")
    check("A2. it supersedes v1.5 by name", doc.get("supersedes") == V1_5.name)
    check("A3. and pins v1.5 by hash",
          doc.get("supersedes_sha256") == _sha256(V1_5))
    check("A4. the companion markdown it names exists",
          (LSE.parent / doc.get("companion_markdown", "")).is_file(),
          str(doc.get("companion_markdown")))

    u = _hyp(doc)["anchor_universe"]
    check("A5. the evaluation basis is point-in-time",
          u.get("evaluation_basis") == "point_in_time",
          str(u.get("evaluation_basis")))
    check("A6. membership is declared as intervals",
          isinstance(u.get("membership_intervals"), list)
          and len(u["membership_intervals"]) > 0)
    check("A7. every interval names a ticker and a start date",
          all(i.get("ticker") and i.get("start_date")
              for i in u["membership_intervals"]))
    check("A8. and carries the accession that opened it",
          all(i.get("start_accession") for i in u["membership_intervals"]))
    check("A9. members_ever agrees with the intervals",
          set(u["members_ever"])
          == {i["ticker"] for i in u["membership_intervals"]},
          str(u["members_ever"]))
    check("A10. the count agrees with the list",
          u["members_ever_count"] == len(u["members_ever"]))

    hist = LSE.parent / u.get("history_artifact", "")
    check("A11. the pinned history artifact exists", hist.is_file(), str(hist))
    if hist.is_file():
        check("A12. and its hash matches what the registry pinned",
              u.get("history_artifact_sha256") == _sha256(hist))
    check("A13. every qualifying disclosure is entity-wide and over the bar",
          all(d.get("concentration_basis") == au.REQUIRED_BASIS
              and float(d.get("concentration_pct", 0)) >= 10.0
              for i in u["membership_intervals"]
              for d in i["evidence"]["qualifying_disclosures"]))


def test_b_the_intervals_still_follow_from_the_history() -> None:
    print("\n--- PART B: the intervals, re-derived ---")
    if not V1_6.is_file() or not HISTORY.is_file():
        skip("B. re-derivation", "v1.6 or the pinned history is absent")
        return
    u = _hyp(_load(V1_6))["anchor_universe"]
    d = au.derive_universe_point_in_time(_load(HISTORY))
    check("B1. the pinned history is still evaluable", d.derived, str(d.refusals))
    check("B2. and still COMPLETE -- no unread filings", d.complete,
          str(d.incomplete))
    check("B3. and registry-grade", d.registry_grade)
    check("B4. the published intervals equal a fresh derivation",
          [i.as_dict() for i in d.intervals] == u["membership_intervals"],
          f"derived {len(d.intervals)} vs published "
          f"{len(u['membership_intervals'])}")
    check("B5. members_ever matches too",
          list(d.members_ever) == u["members_ever"], str(d.members_ever))


def test_c_the_rule_did_not_change() -> None:
    """v1.6 may change WHEN the rule is asked, never WHAT it asks."""
    print("\n--- PART C: the rule is immovable ---")
    if not V1_6.is_file():
        skip("C. rule immovability", "v1.6 absent")
        return
    new = _hyp(_load(V1_6))["anchor_universe"]
    old = _hyp(_load(V1_5))["anchor_universe"]
    for f in RULE_FIELDS_THAT_MUST_NOT_MOVE:
        check(f"C1. anchor_universe.{f} is byte-identical to v1.5",
              new.get(f) == old.get(f))
    check("C2. the conditions still match the code",
          [c["id"] for c in new["conditions"]] == [c for c, _ in au.CONDITIONS])
    check("C3. the threshold is still ASC 280's 10%",
          new["threshold_pct"] == 10.0)
    check("C4. the denominator is still consolidated revenue",
          new["required_denominator"] == au.REQUIRED_BASIS)
    check("C5. the rejected conditions still match the code",
          [c["condition"] for c in new["conditions_deliberately_rejected"]]
          == [n for n, _ in au.NEVER_CONDITIONS])


def test_d_the_supersession_is_recorded() -> None:
    print("\n--- PART D: what was superseded, and why ---")
    if not V1_6.is_file():
        skip("D. supersession", "v1.6 absent")
        return
    u = _hyp(_load(V1_6))["anchor_universe"]
    s = u.get("superseded_snapshot")
    check("D1. the superseded snapshot is recorded", isinstance(s, dict))
    if not isinstance(s, dict):
        return
    old_members = _hyp(_load(V1_5))["anchor_universe"]["derived_members"]
    check("D2. carrying v1.5's actual answer",
          s.get("v1_5_derived_members") == old_members,
          str(s.get("v1_5_derived_members")))
    check("D3. the reason names the newest-filing screen",
          "latest_10k" in s.get("why_superseded", ""))
    check("D4. and names the survivorship mechanism",
          "not missing at random" in s.get("why_superseded", ""))
    check("D5. it does not claim the superseded member was false",
          "correct application"
          in s.get("the_snapshot_member_was_not_wrong", ""))
    check("D6. and states that both answers are NOT carried",
          "REPLACE" in s.get("both_answers_are_not_carried", "").upper())

    # The snapshot's own fields must be GONE, not left beside the intervals.
    # Two universes in one document is the v1.3/v1.4 contradiction again.
    for gone in ("derived_members", "derived_members_provenance",
                 "screen_artifact", "cutoff_date"):
        check(f"D7. the snapshot field {gone} is removed, not duplicated",
              gone not in u, f"{gone} still present")

    c = u.get("corpus_correction")
    check("D8. the corpus correction is recorded", isinstance(c, dict))
    if isinstance(c, dict):
        check("D9. with the count of fabrications rejected",
              c.get("fabrications_found_and_rejected") == 8)
        check("D10. and why the gates are structural rather than lists",
              "never be complete" in c.get("why_the_gates_are_structural", ""))
        check("D11. and that under-inclusion was measured too",
              "SEGMENT"
              in c.get("under_inclusion_was_measured_too", "").upper())
        check("D12. and how the corpus was completed",
              "full-submission" in c.get("retrieval_completeness", ""))


def test_e_the_gate_did_not_move() -> None:
    print("\n--- PART E: the display gate ---")
    # v1.6 was current when this suite was written; v1.7 superseded it on
    # 2026-08-28. "Is current" is each version's own suite to assert, and the
    # v1.7 suite does. What stays true for v1.6 forever is the direction --
    # it was superseded -- so that is what is checked here. Asserting the
    # chain from this side as well would duplicate the v1.7 suite and break on
    # a v1.8, because v1.6 is only the current registry's predecessor until it
    # is not. Same reasoning as the v1.5 suite's D1.
    check("E1. v1.6 is no longer the current artifact -- v1.7 superseded it",
          not REGISTRY_CURRENT.name.endswith("v1.6.json"), REGISTRY_CURRENT.name)
    d = current_decision()
    check("E2. it is CLOSED", d.open is False, str(d.conditions))
    check("E3. with exactly 4 denials", len(d.denials) == 4, str(d.denials))
    check("E4. and C4 MET", d.conditions["C4_decisions_resolved"] is True)
    check("E5. C2 still FAILS -- widening a universe creates no eligible event",
          d.conditions["C2_threshold"] is False)

    good = FreezeRecord(
        frozen=True,
        eligible_event_ids=tuple(f"E{i}" for i in range(193)),
        analysis_commit_sha="0" * 40,
        analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
        frozen_before_any_result_computed=True,
        uses_placeholder_linkage=False,
    )
    if V1_6.is_file():
        g = evaluate_gate(eligible_event_count=193, freeze=good,
                          registry_path=V1_6)
        check("E6. C4 CLEARS against v1.6",
              g.conditions["C4_decisions_resolved"] is True, str(g.denials))
        check("E7. and the gate is STILL closed", g.open is False)
    if V1_1.is_file():
        g1 = evaluate_gate(eligible_event_count=193, freeze=good,
                           registry_path=V1_1)
        check("E8. CONTROL -- C4 still FAILS against the unmodified v1.1",
              g1.conditions["C4_decisions_resolved"] is False)
    else:
        skip("E8. v1.1 control", "v1.1 not on disk")


def test_f_immovables() -> None:
    print("\n--- PART F: what v1.6 was not allowed to touch ---")
    check("F1. v1.4 is byte-identical to when v1.6 was authored",
          _sha256(V1_4) == V1_4_SHA256, _sha256(V1_4))
    check("F2. v1.5 is byte-identical to when v1.6 was authored",
          _sha256(V1_5) == V1_5_SHA256, _sha256(V1_5))
    if not V1_6.is_file():
        skip("F. field-level immovables", "v1.6 absent")
        return
    new, old = _load(V1_6), _load(V1_5)
    n, o = _hyp(new), _hyp(old)
    for f in IMMOVABLE_HYP04_FIELDS:
        check(f"F3. HYP-04.{f} is unchanged from v1.5", n.get(f) == o.get(f))
    check("F4. results are still null", new.get("results") is None)
    check("F5. every eligible-event counter is still zero",
          all(v == 0 for k, v in new["eligible_event_counts"].items()
              if k.startswith("HYP-")))
    check("F6. statistical_governance is untouched",
          new.get("statistical_governance") == old.get("statistical_governance"))
    check("F7. the peer-data policy is APPLIED, not amended",
          new.get("peer_price_data_policy") == old.get("peer_price_data_policy"))
    check("F8. required_eligibility_class is still the anchor-side core class",
          n["required_eligibility_class"] == "core_attention_vs_equity_response")
    check("F9. and the artifact still says membership is not eligibility",
          "creates no eligible anchor event"
          in n["anchor_universe"]["membership_is_not_eligibility"])


def test_g_the_generator_refuses() -> None:
    print("\n--- PART G: the generator's refusals ---")
    refusals = check_preconditions()
    check("G1. it refuses to overwrite the published v1.6",
          any("already exists" in r for r in refusals), str(refusals))

    if not HISTORY.is_file():
        skip("G2. incompleteness refusal", "history absent")
        return
    hist = _load(HISTORY)

    with tempfile.TemporaryDirectory() as t:
        # An INCOMPLETE history is refused outright rather than declared with
        # a caveat: unread filings understate membership invisibly, and a
        # universe is a preregistration artifact.
        holed = copy.deepcopy(hist)
        holed["tickers"][0].setdefault("filings_failed", []).append(
            {"filing_date": "2001-01-01", "accession": "x",
             "error": "HTTPError: 404"})
        p = Path(t) / "holed.json"
        p.write_text(json.dumps(holed), encoding="utf-8")
        raised = ""
        try:
            build_v1_6(history=p)
        except RefusedError as e:
            raised = str(e)
        check("G2. an incomplete history is refused",
              "registry-grade" in raised, raised[:140] or "no refusal")

        # A history without denominators cannot be scored at all.
        stale = copy.deepcopy(hist)
        for rec in stale["tickers"]:
            for f in rec["per_filing"]:
                f.pop("disclosures", None)
        p2 = Path(t) / "stale.json"
        p2.write_text(json.dumps(stale), encoding="utf-8")
        raised2 = ""
        try:
            build_v1_6(history=p2)
        except RefusedError as e:
            raised2 = str(e)
        check("G3. a history without denominators is refused",
              "registry-grade" in raised2, raised2[:140] or "no refusal")

    # HARDCODED-CLOSED CONTROL: the real history builds. Without this, G2 and
    # G3 would both pass if build_v1_6 simply refused everything.
    doc, changes, u = build_v1_6()
    check("G4. the real history builds", bool(changes))
    check("G5. and yields exactly the intervals a direct derivation gives",
          [i.as_dict() for i in u.intervals]
          == _hyp(doc)["anchor_universe"]["membership_intervals"])


def test_h_offline() -> None:
    try:
        socket.getaddrinfo("www.sec.gov", 443)
        check("H1. network blocked", False, "a lookup succeeded")
    except NetworkBlocked:
        check("H1. network blocked", True)


if __name__ == "__main__":
    test_a_the_published_artifact()
    test_b_the_intervals_still_follow_from_the_history()
    test_c_the_rule_did_not_change()
    test_d_the_supersession_is_recorded()
    test_e_the_gate_did_not_move()
    test_f_immovables()
    test_g_the_generator_refuses()
    test_h_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.6 TESTS PASSED")
    sys.exit(0)
