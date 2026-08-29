#!/usr/bin/env python3
"""Tests for registry v1.8 -- the HYP-04 anchor universe after the scoped-list fix.

v1.8 keeps v1.6's point-in-time evaluation basis and the same rule. What it
corrects is one level below v1.7's correction: every anchor required the
percentage and its denominator to be ADJACENT, so a list of parties governed by
a scope clause that states the denominator ONCE was unreadable -- in prose and
as a table alike.

=== THE RISK THAT DEFINES THIS SUITE ===

v1.7's suite says it outright: a version that only ever ADDS members is
indistinguishable from a loosened threshold. **v1.8 removes nobody.** It adds
ADBE and JBL and extends INTC. So this suite has to carry the burden v1.7
discharged by pointing at a removal, and it does so with three independent
checks that a loosening could not pass:

  * THE RULE IS BYTE-IDENTICAL to v1.7 -- threshold, denominator, AU-1..AU-6
    and the point-in-time basis (test_c). A loosened threshold would show here.
  * THE CORRECTION PRODUCES NEW EXITS, not just entries. INTC's membership
    ends 2025-01-31 and JBL's 2025-10-17, because in those filings Intel and
    Jabil ANONYMISED their customers to "Customer A / B / C". A loosened
    threshold pushes members toward the present; it does not evict them.
  * INTC'S INTERVAL IS BOUNDED AT BOTH ENDS and its old end is explicable:
    2017-02-17 is the filing in which Intel moved the disclosure out of Item 1
    prose, not the year Dell fell below 10%.

=== WHAT WAS ACTUALLY WRONG ===

All three membership errors were the same error -- DATA AVAILABILITY DECIDING
MEMBERSHIP, which AU-1..AU-6 forbid:

  * INTC closed at 2017-02-17 on a change of prose style. Dell is disclosed at
    15-21% of net revenue in every filing through 2024-01-26.
  * ADBE was in no registry version, with Ingram Micro at 11-21% of net
    revenue across 2008-2015.
  * JBL was in no registry version, though its 10-Ks carry an explicit
    "customers who accounted for 10% or more of the Company's net revenues"
    table across twenty-four years.

test_b re-derives the intervals from the history the artifact pins by hash. A
registry that merely SAYS its universe is derived is worth nothing.

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_8.py
"""
from __future__ import annotations

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
    V1_7,
)
from hyp04_supply_chain_hedge.make_registry_v1_8 import (  # noqa: E402
    HISTORY,
    V1_8,
    RefusedError,
    build_v1_8,
    check_preconditions,
)

V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
V1_4 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json"
V1_5 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json"
HYPOTHESIS_ID = "HYP-04"

# Pinned when v1.8 was authored. Every predecessor is append-only.
V1_4_SHA256 = "b7900bcd5c6676da1221dcdcf5287f3d1dca44d831ab9955a3f057a9c8bf4419"
V1_5_SHA256 = "731ee4f2228477ee6e9200452430eb41b45fe0e0ed3a0c5af995b4b9e7439bdc"
V1_6_SHA256 = "1cce4dcb926640a497337bfaf86b8ca5f275140dcc389640fea37bd3d3c75f5f"
V1_7_SHA256 = "abe45f4d6ff2a78b0343970903d36bf57743c5a9c38a8d5303d020f89898f82a"

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
    print("\n--- PART A: the artifact exists and supersedes v1.7 ---")
    if not V1_8.is_file():
        skip("A. v1.8", "artifact absent")
        return
    doc = _load(V1_8)
    check("A1. it declares version 1.8", doc.get("registry_version") == "1.8",
          str(doc.get("registry_version")))
    check("A2. it supersedes v1.7 by name", doc.get("supersedes") == V1_7.name,
          str(doc.get("supersedes")))
    check("A3. and by the hash v1.7 actually has",
          doc.get("supersedes_sha256") == _sha256(V1_7),
          str(doc.get("supersedes_sha256")))
    check("A4. results are still null -- v1.8 reports nothing",
          doc.get("results") is None, str(doc.get("results"))[:80])


def test_b_the_intervals_are_rederived() -> None:
    """The claim v1.8 makes is that its universe FOLLOWS from the corpus."""
    print("\n--- PART B: the intervals are derived, not typed ---")
    if not V1_8.is_file() or not HISTORY.is_file():
        skip("B. re-derivation", "artifact or history absent")
        return
    u = _hyp(_load(V1_8))["anchor_universe"]

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
    check("B5. the corpus is still complete -- 1,250 filings, no failures",
          again.evidence.get("filings_evaluated") == 1250
          and not again.incomplete,
          f"{again.evidence.get('filings_evaluated')} {again.incomplete}")


def test_c_the_rule_did_not_move() -> None:
    """THE LOAD-BEARING TEST OF THIS SUITE.

    v1.8 adds members and removes none, so it cannot point at a removal to
    prove it is a correction rather than a loosening. What it can do is pin
    the rule byte-identical: if the threshold or the denominator had been
    relaxed to admit ADBE and JBL, it would fail here.
    """
    print("\n--- PART C: the rule is byte-identical to v1.7 ---")
    if not V1_8.is_file() or not V1_7.is_file():
        skip("C. rule immovability", "artifact absent")
        return
    new = _hyp(_load(V1_8))["anchor_universe"]
    old = _hyp(_load(V1_7))["anchor_universe"]

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
    check("C6. the frame is still the same 51 tickers",
          new.get("tickers_walked") == old.get("tickers_walked"),
          f"{old.get('tickers_walked')} -> {new.get('tickers_walked')}")


def test_d_what_the_correction_did() -> None:
    """v1.8 REMOVES NOBODY, which v1.7's suite names as the dangerous shape.

    The compensating evidence is that the correction produces new EXITS. A
    loosened threshold pushes members toward the present; it does not evict
    two of them in 2025 because the filer stopped printing customer names.
    """
    print("\n--- PART D: what the correction actually did ---")
    if not V1_8.is_file() or not V1_7.is_file():
        skip("D. membership", "artifact absent")
        return
    new = _hyp(_load(V1_8))["anchor_universe"]
    old = _hyp(_load(V1_7))["anchor_universe"]
    before, after = set(old["members_ever"]), set(new["members_ever"])

    check("D1. ADBE was ADDED -- Ingram Micro at 11-21% of net revenue",
          "ADBE" not in before and "ADBE" in after,
          f"before={sorted(before)} after={sorted(after)}")
    check("D2. JBL was ADDED -- an explicit 10%-or-more customer table",
          "JBL" not in before and "JBL" in after,
          f"before={sorted(before)} after={sorted(after)}")
    check("D3. nobody was removed, and that is stated rather than hidden",
          before - after == set(), f"removed={sorted(before - after)}")

    ivs = new["membership_intervals"]

    intc = [i for i in ivs if i["ticker"] == "INTC"]
    check("D4. INTC still has exactly one interval", len(intc) == 1,
          str(len(intc)))
    if intc:
        i = intc[0]
        check("D5. INTC still opens where v1.7 opened it",
              i["start_date"] == "2005-02-22", str(i["start_date"]))
        check("D6. and now closes 2025-01-31, not 2017-02-17 -- the old end "
              "was a change of prose style, not of relationship",
              i["end_date"] == "2025-01-31", str(i["end_date"]))

    jbl = [i for i in ivs if i["ticker"] == "JBL"]
    check("D7. JBL has exactly one interval", len(jbl) == 1, str(len(jbl)))
    if jbl:
        i = jbl[0]
        check("D8. opening 2001-11-28 on Dell Computer Corporation",
              i["start_date"] == "2001-11-28", str(i["start_date"]))
        ev = (i.get("evidence", {}).get("qualifying_disclosures") or [{}])[0]
        check("D9. the opener is a real company, not a bare legal suffix",
              str(ev.get("counterparty")) == "Dell Computer Corporation",
              str(ev.get("counterparty")))
        check("D10. closing 2025-10-17, when Jabil ANONYMISED its customers",
              i["end_date"] == "2025-10-17", str(i["end_date"]))

    adbe = [i for i in ivs if i["ticker"] == "ADBE"]
    check("D11. ADBE has exactly one interval", len(adbe) == 1, str(len(adbe)))
    if adbe:
        ev = (adbe[0].get("evidence", {}).get("qualifying_disclosures") or [{}])[0]
        check("D12. opened by Ingram Micro at 21% of net revenue",
              str(ev.get("counterparty")) == "Ingram Micro"
              and ev.get("concentration_pct") == 21.0,
              f"{ev.get('counterparty')} {ev.get('concentration_pct')}")
        check("D13. against a CONSOLIDATED denominator",
              ev.get("concentration_basis") == au.REQUIRED_BASIS,
              str(ev.get("concentration_basis")))

    # THE ANTI-LOOSENING EVIDENCE. Two members exit in 2025 because the filer
    # stopped naming its customers. A relaxed threshold produces no exits.
    ends = {i["ticker"]: i.get("end_date") for i in ivs}
    check("D14. INTC and JBL both EXIT in 2025 -- a loosened threshold would "
          "have carried them to the present instead",
          str(ends.get("INTC", "")).startswith("2025")
          and str(ends.get("JBL", "")).startswith("2025"),
          f"INTC={ends.get('INTC')} JBL={ends.get('JBL')}")

    corr = json.dumps(new.get("corpus_correction_2026_08_29", {}))
    check("D15. the correction is recorded in the artifact", bool(corr) and
          "ADBE" in corr and "JBL" in corr and "INTC" in corr)
    check("D16. and so is the reason both exits are the rule working",
          "Customer A" in corr, corr[:80])
    check("D17. the refused block table is recorded as a MEASURED cost, "
          "naming the member it excludes",
          any("Reyes" in str(l) and "STZ" in str(l)
              for l in new.get("known_limitations", [])),
          str(new.get("known_limitations"))[:120])


def test_e_the_gate_did_not_move() -> None:
    print("\n--- PART E: the display gate ---")
    check("E1. the gate reads the v1.8 artifact",
          REGISTRY_CURRENT.name.endswith("v1.8.json"), REGISTRY_CURRENT.name)
    d = current_decision()
    check("E2. it is CLOSED", d.open is False, str(d.conditions))
    check("E3. with exactly 4 denials", len(d.denials) == 4, str(d.denials))
    check("E4. and C4 MET", d.conditions["C4_decisions_resolved"] is True)
    check("E5. C2 still FAILS -- correcting a universe creates no eligible "
          "anchor event", d.conditions["C2_threshold"] is False)
    if V1_8.is_file():
        doc = _load(V1_8)
        counts = doc.get("eligible_event_counts") or {}
        # The block carries an explanatory "note" beside the integers.
        nums = {k: v for k, v in counts.items() if isinstance(v, int)}
        check("E6. every eligible-event counter is still zero",
              bool(nums) and all(v == 0 for v in nums.values()), str(nums))
        entry = _hyp(doc)
        check("E7. HYP-04's status is unchanged",
              entry.get("status") == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
              str(entry.get("status")))
    if V1_1.is_file():
        g1 = evaluate_gate(eligible_event_count=193, registry_path=V1_1)
        check("E8. CONTROL -- C4 still FAILS against the unmodified v1.1",
              g1.conditions["C4_decisions_resolved"] is False)


def test_f_the_generator_refuses() -> None:
    print("\n--- PART F: the generator's refusals ---")
    check("F1. it refuses to overwrite the published v1.8",
          any("already exists" in r for r in check_preconditions()),
          str(check_preconditions()))

    # A version whose derivation equals its source's intervals is refused:
    # a registry version that changes nothing is noise in the chain.
    if not V1_8.is_file():
        skip("F2. no-op refusal", "v1.8 absent")
    else:
        with tempfile.TemporaryDirectory() as td:
            same = Path(td) / "same.json"
            same.write_text(HISTORY.read_text(encoding="utf-8"),
                            encoding="utf-8")
            try:
                build_v1_8(v1_7=V1_8, history=same)
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
    check("G3. v1.6 unchanged", _sha256(V1_6) == V1_6_SHA256, _sha256(V1_6))
    check("G4. v1.7 unchanged -- including the INTC interval v1.8 extends "
          "and the absence of ADBE and JBL that v1.8 corrects",
          _sha256(V1_7) == V1_7_SHA256, _sha256(V1_7))
    if V1_8.is_file():
        doc = _load(V1_8)
        check("G5. v1.8 still parses and reports 1.8",
              doc.get("registry_version") == "1.8")
        check("G6. eligible_event_counts unchanged from v1.7",
              doc.get("eligible_event_counts") == _load(V1_7).get(
                  "eligible_event_counts"))
        check("G7. peer_price_data_policy unchanged -- v1.8 applies it, "
              "it does not amend it",
              doc.get("peer_price_data_policy")
              == _load(V1_7).get("peer_price_data_policy"))
        for f in IMMOVABLE_HYP04_FIELDS:
            check(f"G8. HYP-04.{f} is unchanged from v1.7",
                  _hyp(doc).get(f) == _hyp(_load(V1_7)).get(f))


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
    test_d_what_the_correction_did()
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
    print("ALL HYP-04 REGISTRY v1.8 TESTS PASSED")
