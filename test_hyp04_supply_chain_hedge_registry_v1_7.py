#!/usr/bin/env python3
"""Tests for registry v1.7 -- the corrected HYP-04 anchor universe.

v1.7 keeps v1.6's point-in-time evaluation basis and the same rule. What it
corrects is the CORPUS READING: five extractor defects, measured against the
full cached corpus, moved membership in BOTH directions.

=== THE RISK THAT DEFINES THIS SUITE ===

A version that only ever ADDS members is indistinguishable from a loosened
threshold. v1.7 removes one and adds one, and both directions are asserted
here against the filings' own words:

  * MCHP is OUT. Both filings behind its v1.6 interval disclose a
    concentration for a year OTHER than the one they report on -- fiscal 2012
    and 2011 figures in fiscal 2013 and 2014 reports. v1.6's companion called
    the fiscal-period imprecision harmless. It was not; it manufactured a
    member.
  * NKE is IN. NIKE disclosed Foot Locker at 10.9% of consolidated revenues
    for FY2002, in a multi-year "respectively" construction the anchor could
    not read.

=== AND THE RISK THAT THE RULE MOVES WITH IT ===

test_c pins every rule-describing field byte-identical to v1.6, and the
point-in-time basis with it. v1.7 may change what the extractor can SEE. It
may never change what the rule ASKS. If a future corpus tempts someone to
loosen the rule so more tickers qualify, that test fails rather than the
universe quietly growing.

test_b re-derives the intervals from the history the artifact pins by hash. A
registry that merely SAYS its universe is derived is worth nothing.

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_7.py
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
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RULE_FIELDS_THAT_MUST_NOT_MOVE,
    V1_6,
)
from hyp04_supply_chain_hedge.make_registry_v1_7 import (  # noqa: E402
    EVALUATION_FIELDS_THAT_MUST_NOT_MOVE,
    HISTORY,
    V1_7,
    RefusedError,
    build_v1_7,
    check_preconditions,
)

V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
V1_4 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json"
V1_5 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json"
HYPOTHESIS_ID = "HYP-04"

# Pinned when v1.7 was authored. Every predecessor is append-only.
V1_4_SHA256 = "b7900bcd5c6676da1221dcdcf5287f3d1dca44d831ab9955a3f057a9c8bf4419"
V1_5_SHA256 = "731ee4f2228477ee6e9200452430eb41b45fe0e0ed3a0c5af995b4b9e7439bdc"
V1_6_SHA256 = "1cce4dcb926640a497337bfaf86b8ca5f275140dcc389640fea37bd3d3c75f5f"

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
    print("\n--- PART A: the artifact exists and supersedes v1.6 ---")
    if not V1_7.is_file():
        skip("A. v1.7", "artifact absent")
        return
    doc = _load(V1_7)
    check("A1. it declares version 1.7", doc.get("registry_version") == "1.7",
          str(doc.get("registry_version")))
    check("A2. it supersedes v1.6 by name", doc.get("supersedes") == V1_6.name,
          str(doc.get("supersedes")))
    check("A3. and by the hash v1.6 actually has",
          doc.get("supersedes_sha256") == _sha256(V1_6),
          str(doc.get("supersedes_sha256")))
    check("A4. results are still null -- v1.7 reports nothing",
          doc.get("results") is None, str(doc.get("results"))[:80])


def test_b_the_intervals_are_rederived() -> None:
    """The claim v1.7 makes is that its universe FOLLOWS from the corpus."""
    print("\n--- PART B: the intervals are derived, not typed ---")
    if not V1_7.is_file() or not HISTORY.is_file():
        skip("B. re-derivation", "artifact or history absent")
        return
    u = _hyp(_load(V1_7))["anchor_universe"]

    check("B1. the history it pins is on disk and matches by hash",
          u.get("history_artifact_sha256") == _sha256(HISTORY),
          str(u.get("history_artifact_sha256")))

    again = au.derive_universe_point_in_time(_load(HISTORY))
    check("B2. the derivation is registry-grade", again.registry_grade,
          f"derived={again.derived} complete={again.complete}")
    check("B3. the published intervals re-derive EXACTLY",
          [i.as_dict() for i in again.intervals] == u["membership_intervals"],
          f"{len(again.intervals)} derived vs "
          f"{len(u['membership_intervals'])} published")
    check("B4. and so does the member list",
          sorted(again.members_ever) == sorted(u["members_ever"]),
          str(u.get("members_ever")))


def test_c_the_rule_did_not_move() -> None:
    """v1.7 changes what the extractor READS, never what the rule ASKS."""
    print("\n--- PART C: the rule is byte-identical to v1.6 ---")
    if not V1_7.is_file() or not V1_6.is_file():
        skip("C. rule immovability", "artifact absent")
        return
    new = _hyp(_load(V1_7))["anchor_universe"]
    old = _hyp(_load(V1_6))["anchor_universe"]

    for f in RULE_FIELDS_THAT_MUST_NOT_MOVE:
        check(f"C1. rule field unchanged: {f}", new.get(f) == old.get(f),
              f"{old.get(f)!r} -> {new.get(f)!r}"[:140])
    for f in EVALUATION_FIELDS_THAT_MUST_NOT_MOVE:
        check(f"C2. evaluation basis unchanged: {f}", new.get(f) == old.get(f),
              f"{old.get(f)!r} -> {new.get(f)!r}"[:140])
    check("C3. the written conditions still match the code's",
          [c["id"] for c in new.get("conditions", [])]
          == [c for c, _ in au.CONDITIONS])
    check("C4. the threshold is still ASC 280's 10%",
          new.get("threshold_pct") == au.CONCENTRATION_THRESHOLD_PCT,
          str(new.get("threshold_pct")))
    check("C5. and the denominator still consolidated revenue",
          new.get("required_denominator") == au.REQUIRED_BASIS,
          str(new.get("required_denominator")))


def test_d_membership_moved_in_both_directions() -> None:
    """A version that only ADDS members looks like a loosened threshold."""
    print("\n--- PART D: what the correction actually did ---")
    if not V1_7.is_file() or not V1_6.is_file():
        skip("D. membership", "artifact absent")
        return
    new = _hyp(_load(V1_7))["anchor_universe"]
    old = _hyp(_load(V1_6))["anchor_universe"]
    before, after = set(old["members_ever"]), set(new["members_ever"])

    check("D1. MCHP was REMOVED -- its interval was a stale comparative",
          "MCHP" in before and "MCHP" not in after,
          f"before={sorted(before)} after={sorted(after)}")
    check("D2. NKE was ADDED -- Foot Locker at 10.9% of consolidated revenues",
          "NKE" not in before and "NKE" in after,
          f"before={sorted(before)} after={sorted(after)}")
    check("D3. membership moved in BOTH directions, which is what makes this "
          "a correction rather than a widening",
          bool(before - after) and bool(after - before),
          f"removed={sorted(before-after)} added={sorted(after-before)}")

    nke = [i for i in new["membership_intervals"] if i["ticker"] == "NKE"]
    check("D4. NKE has exactly one interval", len(nke) == 1, str(len(nke)))
    if nke:
        i = nke[0]
        check("D5. opening on the filing that disclosed it",
              i["start_date"] == "2002-08-14", str(i["start_date"]))
        check("D6. and closing when NIKE said there was no such customer",
              i["end_date"] == "2004-07-30", str(i["end_date"]))
        ev = (i.get("evidence", {}).get("qualifying_disclosures") or [{}])[0]
        check("D7. the counterparty is Foot Locker, not the bare suffix 'Inc'",
              str(ev.get("counterparty")).startswith("Foot Locker"),
              str(ev.get("counterparty")))
        check("D8. at the REPORTING year's figure, not a prior year's",
              ev.get("concentration_pct") == 10.9,
              str(ev.get("concentration_pct")))

    check("D9. the correction is recorded in the artifact, both directions",
          "MCHP" in json.dumps(new.get("corpus_correction_2026_08_28", {}))
          and "NKE" in json.dumps(new.get("corpus_correction_2026_08_28", {})))


def test_e_the_gate_did_not_move() -> None:
    print("\n--- PART E: the display gate ---")
    check("E1. v1.7 is no longer the current artifact -- v1.8 superseded it",
          not REGISTRY_CURRENT.name.endswith("v1.7.json"),
          REGISTRY_CURRENT.name)
    d = current_decision()
    # NARROWED again: E2/E3/E6 asserted the gate was OPEN with zero denials
    # and a live registry_status of ACTIVE_COLLECTING, true from 2026-09-09
    # (freeze + v1.12 moved C1) until v1.13 closed HYP-04 on 2026-09-11 and
    # C1 denied again under a NEW status, HOLDOUT_TESTED_NULL. v1.7 opened
    # nothing and closed nothing -- correcting a universe is neither an
    # eligible event nor activation -- so it needs no live open/closed or
    # status opinion at all, only on what it itself moved (E4, E5 below,
    # both unaffected by any later status change).
    check("E4. and C4 MET", d.conditions["C4_decisions_resolved"] is True)
    check("E5. C2 counts DERIVED events (214); correcting a universe still "
          "creates none",
          d.conditions["C2_threshold"] is True
          and d.evidence["eligible_event_count"] == 214)

    good = FreezeRecord(
        frozen=True,
        eligible_event_ids=tuple(f"E{i}" for i in range(193)),
        analysis_commit_sha="0" * 40,
        analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
        frozen_before_any_result_computed=True,
        uses_placeholder_linkage=False,
    )
    g7 = evaluate_gate(eligible_event_count=193, freeze=good, registry_path=V1_7)
    check("E7. C4 CLEARS against v1.7",
          g7.conditions["C4_decisions_resolved"] is True, str(g7.denials))
    check("E8. and the gate is STILL closed -- C1 alone keeps it shut",
          g7.open is False, str(g7.denials))

    if V1_1.is_file():
        g1 = evaluate_gate(eligible_event_count=193, freeze=good,
                           registry_path=V1_1)
        check("E9. CONTROL -- C4 still FAILS against the unmodified v1.1",
              g1.conditions["C4_decisions_resolved"] is False)


def test_f_the_generator_refuses() -> None:
    print("\n--- PART F: the generator's refusals ---")
    check("F1. it refuses to overwrite the published v1.7",
          any("already exists" in r for r in check_preconditions()),
          str(check_preconditions()))

    # A history that re-derives to v1.6's own intervals must be refused: a
    # version that changes nothing is noise in the chain.
    if not V1_6.is_file():
        skip("F2. no-op refusal", "v1.6 absent")
    else:
        with tempfile.TemporaryDirectory() as td:
            same = Path(td) / "same.json"
            same.write_text(HISTORY.read_text(encoding="utf-8"),
                            encoding="utf-8")
            # build against v1.7 as the source: its intervals already equal
            # the derivation, so the "membership actually moved" guard fires.
            try:
                build_v1_7(v1_6=V1_7, history=same)
                check("F2. a no-op version is refused", False, "it built")
            except RefusedError as e:
                check("F2. a no-op version is refused",
                      "changes nothing" in str(e) or "identical" in str(e),
                      str(e)[:120])
            except Exception as e:
                check("F2. a no-op version is refused", False,
                      f"{type(e).__name__}: {e}"[:120])


def test_g_no_side_effects() -> None:
    print("\n--- PART G: no side effects ---")
    check("G1. v1.4 unchanged", _sha256(V1_4) == V1_4_SHA256, _sha256(V1_4))
    check("G2. v1.5 unchanged", _sha256(V1_5) == V1_5_SHA256, _sha256(V1_5))
    check("G3. v1.6 unchanged -- including the MCHP interval v1.7 removes",
          _sha256(V1_6) == V1_6_SHA256, _sha256(V1_6))
    if V1_7.is_file():
        doc = _load(V1_7)
        check("G4. v1.7 still parses and reports 1.7",
              doc.get("registry_version") == "1.7")
        check("G5. eligible_event_counts unchanged from v1.6",
              doc.get("eligible_event_counts") == _load(V1_6).get(
                  "eligible_event_counts"))
        check("G6. peer_price_data_policy unchanged -- v1.7 applies it, "
              "it does not amend it",
              doc.get("peer_price_data_policy")
              == _load(V1_6).get("peer_price_data_policy"))


def test_h_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("H1. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("H1. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_a_the_published_artifact()
    test_b_the_intervals_are_rederived()
    test_c_the_rule_did_not_move()
    test_d_membership_moved_in_both_directions()
    test_e_the_gate_did_not_move()
    test_f_the_generator_refuses()
    test_g_no_side_effects()
    test_h_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.7 TESTS PASSED")
    sys.exit(0)
