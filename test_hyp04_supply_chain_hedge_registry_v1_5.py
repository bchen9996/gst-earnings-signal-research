#!/usr/bin/env python3
"""Tests for registry v1.5 -- the declared HYP-04 anchor universe.

v1.5 registers a RULE for who may be a HYP-04 anchor, so that MCK does not
become the universe by being the ticker that happened to work. The risk this
suite exists to catch is that the rule becomes decorative -- a document
asserting a member list that no longer follows from the rule it cites.

=== THE PUBLISHED DOCUMENT IS CHECKED AGAINST THE RULE, EVERY RUN ===

test_B re-derives the universe from the screen the artifact pins, by hash, and
requires the published `derived_members` to match. If someone edits the member
list in the JSON, or changes a threshold in `anchor_universe.py`, or swaps the
screen, this fails. A registry that merely SAYS its universe is derived is
worth nothing; this is what makes the claim checkable.

=== AND THE GATE MUST NOT HAVE MOVED ===

Declaring who MAY be an anchor creates no eligible anchor event. test_D
requires the gate to read CLOSED with C4 MET and exactly four denials against
v1.5, and keeps the v1.1 control that C4 still FAILS there -- without which
every C4 assertion would pass if C4 broke open.

Offline. No network. Nothing in the repo is written by this suite.

Run directly: python test_hyp04_supply_chain_hedge_registry_v1_5.py
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
    FreezeRecord,
    current_decision,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.make_registry_v1_5 import (  # noqa: E402
    CUTOFF_DATE,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    SCREEN,
    V1_4,
    V1_5,
    RefusedError,
    build_v1_5,
    check_preconditions,
)

V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
HYPOTHESIS_ID = "HYP-04"

# Pinned when v1.5 was authored. v1.4 is append-only and must never move again.
V1_4_SHA256 = "b7900bcd5c6676da1221dcdcf5287f3d1dca44d831ab9955a3f057a9c8bf4419"

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


# ======================================================================
def test_a_the_published_artifact() -> None:
    print("\n--- PART A: the published v1.5 ---")
    if not V1_5.is_file():
        skip("A. registry v1.5 present", f"{V1_5.name} not on disk")
        return
    doc = _load(V1_5)
    check("A1. it reports registry_version 1.5",
          str(doc.get("registry_version")) == "1.5", str(doc.get("registry_version")))
    check("A2. it supersedes v1.4 by name", doc.get("supersedes") == V1_4.name,
          str(doc.get("supersedes")))
    check("A3. and pins v1.4 by hash",
          doc.get("supersedes_sha256") == _sha256(V1_4),
          str(doc.get("supersedes_sha256")))
    check("A4. the companion markdown it names exists",
          (LSE.parent / doc.get("companion_markdown", "")).is_file(),
          str(doc.get("companion_markdown")))

    u = _hyp(doc).get("anchor_universe")
    check("A5. HYP-04 declares an anchor_universe", isinstance(u, dict))
    if not isinstance(u, dict):
        return
    check("A6. naming the rule that produced it", u.get("rule_id") == au.RULE_ID,
          str(u.get("rule_id")))
    check("A7. and the module that implements it",
          u.get("implemented_by") == "hyp04_supply_chain_hedge/anchor_universe.py")
    check("A8. the conditions match the code, in order",
          [c["id"] for c in u.get("conditions", [])] == [c for c, _ in au.CONDITIONS],
          str([c.get("id") for c in u.get("conditions", [])]))
    check("A9. the rejected conditions match the code",
          [c["condition"] for c in u.get("conditions_deliberately_rejected", [])]
          == [n for n, _ in au.NEVER_CONDITIONS])
    check("A10. the threshold is the standard's, not a tuned one",
          u.get("threshold_pct") == 10.0, str(u.get("threshold_pct")))
    check("A11. the denominator is the entity-wide one",
          u.get("required_denominator") == au.REQUIRED_BASIS,
          str(u.get("required_denominator")))

    screen = LSE.parent / u.get("screen_artifact", "")
    check("A12. the pinned screen artifact exists", screen.is_file(), str(screen))
    if screen.is_file():
        check("A13. and its hash matches what the registry pinned",
              u.get("screen_artifact_sha256") == _sha256(screen))

    check("A14. the frame is bigger than the universe it produced",
          u["screening_frame"]["size"] > u["derived_members_count"],
          f"{u['screening_frame']['size']} vs {u['derived_members_count']}")
    check("A15. every member is inside the frame",
          set(u["derived_members"]) <= set(u["screening_frame"]["tickers"]))
    check("A16. every member carries its qualifying disclosure",
          all(u["derived_members_provenance"].get(t)
              for t in u["derived_members"]),
          str(list(u["derived_members_provenance"])))
    for t in u["derived_members"]:
        for e in u["derived_members_provenance"][t]:
            check(f"A17. {t}'s evidence names an accession",
                  bool(e.get("accession")), str(e))
            check(f"A18. {t}'s evidence is against {au.REQUIRED_BASIS}",
                  e.get("concentration_basis") == au.REQUIRED_BASIS,
                  str(e.get("concentration_basis")))
            check(f"A19. {t}'s evidence meets the threshold",
                  float(e.get("concentration_pct", 0)) >= 10.0,
                  str(e.get("concentration_pct")))


def test_b_the_member_list_still_follows_from_the_rule() -> None:
    """The load-bearing check: re-derive, and compare with what was published."""
    print("\n--- PART B: the universe, re-derived ---")
    if not V1_5.is_file() or not SCREEN.is_file():
        skip("B. re-derivation", "v1.5 or the pinned screen is absent")
        return
    u = _hyp(_load(V1_5))["anchor_universe"]
    d = au.derive_universe(_load(SCREEN), cutoff_date=u["cutoff_date"])
    check("B1. the pinned screen is still evaluable by the rule", d.derived,
          str(d.refusals))
    check("B2. the published member list equals a fresh derivation",
          list(d.members) == u["derived_members"],
          f"derived {list(d.members)} vs published {u['derived_members']}")
    check("B3. the published count agrees with the list",
          u["derived_members_count"] == len(u["derived_members"]))
    check("B4. the cutoff the artifact records is the one the generator uses",
          u["cutoff_date"] == CUTOFF_DATE, u["cutoff_date"])
    check("B5. the frame recorded is the frame the code computes",
          set(u["screening_frame"]["tickers"]) == set(au.screening_frame()))


def test_c_pkg_is_excluded_and_the_reason_is_recorded() -> None:
    """The rule costs a ticker. That is the evidence it was not fitted."""
    print("\n--- PART C: what the rule excluded ---")
    if not V1_5.is_file():
        skip("C. exclusions", "v1.5 absent")
        return
    u = _hyp(_load(V1_5))["anchor_universe"]
    rejected = u.get("screened_but_not_qualifying", [])
    pkg = [r for r in rejected if r.get("ticker") == "PKG"]
    check("C1. PKG appears in the screened-but-not-qualifying record",
          len(pkg) == 1, str([r.get("ticker") for r in rejected]))
    if pkg:
        check("C2. with its counterparty named", pkg[0].get("counterparty") == "ODP",
              str(pkg[0].get("counterparty")))
        check("C3. and the denominator that excluded it",
              pkg[0].get("concentration_basis") == "segment_revenue",
              str(pkg[0].get("concentration_basis")))
        check("C4. and an explicit denial citing AU-4",
              any("AU-4" in w for w in pkg[0].get("denials", [])),
              str(pkg[0].get("denials")))
    check("C5. PKG is NOT a member", "PKG" not in u["derived_members"],
          str(u["derived_members"]))

    seen = u["the_rule_was_written_after_the_screen_was_seen"]
    check("C6. the artifact admits the rule postdates the screen",
          seen.get("acknowledged") is True)
    check("C7. and says what protects it instead of ignorance",
          "ASC 280" in seen.get("what_actually_protects_it", ""))
    alt = seen["alternative_considered_and_rejected"]
    check("C8. the PKG-retaining alternative is recorded as considered",
          "segment" in alt.get("alternative", "").lower())
    check("C9. with the filing's own entity-level figure",
          "4% of our consolidated sales revenue" in alt.get("why_rejected", ""),
          alt.get("why_rejected", "")[:120])
    check("C10. and a route to reverse it that requires a dated version",
          "dated registry version" in alt.get("how_to_reverse_it", ""))


def test_d_the_gate_did_not_move() -> None:
    print("\n--- PART D: the display gate ---")
    # v1.5 was the current artifact when this suite was written; v1.6
    # superseded it on 2026-08-27. "Is current" is not v1.5's claim to make
    # any more -- each version's own suite asserts that, and the v1.6 suite
    # now does (A2/A3 pin the supersession by name and hash, and v1.4 AND
    # v1.5 are both pinned byte-identical there). Asserting the chain from
    # here as well would duplicate it and would break on a v1.7, because
    # v1.5 is only the CURRENT registry's predecessor until it is not.
    # What stays true forever is the direction: v1.5 was superseded.
    check("D1. v1.5 is no longer the current artifact -- v1.6 superseded it",
          not REGISTRY_CURRENT.name.endswith("v1.5.json"), REGISTRY_CURRENT.name)
    d = current_decision()
    # NARROWED again: D2/D3/D5 asserted the gate was OPEN with zero denials
    # and a live registry_status of ACTIVE_COLLECTING, true from 2026-09-09
    # (freeze + v1.12 moved C1) until v1.13 closed HYP-04 on 2026-09-11 and
    # C1 denied again under a NEW status, HOLDOUT_TESTED_NULL. v1.5 declared
    # a universe, which is neither activation nor an eligible event, so it
    # needs no live open/closed or status opinion at all, only on what it
    # itself moved (D4, D6 below, both unaffected by any later status change).
    check("D4. and C4 MET", d.conditions["C4_decisions_resolved"] is True,
          str(d.conditions))
    check("D6. C2 counts DERIVED events (214), which declaring a universe "
          "still does not create",
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
    g5 = evaluate_gate(eligible_event_count=193, freeze=good,
                       registry_path=V1_5)
    check("D7. C4 CLEARS against v1.5",
          g5.conditions["C4_decisions_resolved"] is True, str(g5.denials))
    check("D8. and the gate is STILL closed -- C1 alone keeps it shut",
          g5.open is False, str(g5.denials))

    if V1_1.is_file():
        g1 = evaluate_gate(eligible_event_count=193, freeze=good,
                           registry_path=V1_1)
        check("D9. CONTROL -- C4 still FAILS against the unmodified v1.1",
              g1.conditions["C4_decisions_resolved"] is False, str(g1.denials))
    else:
        skip("D9. v1.1 control", "v1.1 not on disk")


def test_e_immovables() -> None:
    print("\n--- PART E: what v1.5 was not allowed to touch ---")
    check("E1. v1.4 is byte-identical to when v1.5 was authored",
          _sha256(V1_4) == V1_4_SHA256, _sha256(V1_4))
    if not V1_5.is_file():
        skip("E. field-level immovables", "v1.5 absent")
        return
    new, old = _load(V1_5), _load(V1_4)
    n, o = _hyp(new), _hyp(old)
    for f in IMMOVABLE_HYP04_FIELDS:
        check(f"E2. HYP-04.{f} is unchanged from v1.4", n.get(f) == o.get(f))
    check("E3. results are still null", new.get("results") is None)
    check("E4. every eligible-event counter is still zero",
          all(v == 0 for k, v in new["eligible_event_counts"].items()
              if k.startswith("HYP-")),
          str(new["eligible_event_counts"]))
    check("E5. statistical_governance is untouched",
          new.get("statistical_governance") == old.get("statistical_governance"))
    check("E6. the hypothesis list is unchanged",
          [h["hypothesis_id"] for h in new["hypotheses"]]
          == [h["hypothesis_id"] for h in old["hypotheses"]])
    check("E7. required_eligibility_class is still the anchor-side core class",
          n["required_eligibility_class"] == "core_attention_vs_equity_response")
    check("E8. and the artifact says membership is not eligibility",
          "creates no eligible anchor event"
          in n["anchor_universe"]["membership_is_not_eligibility"])


def test_f_the_generator_refuses() -> None:
    print("\n--- PART F: the generator's refusals ---")
    refusals = check_preconditions()
    check("F1. it refuses to overwrite the published v1.5",
          any("already exists" in r for r in refusals), str(refusals))

    frame = sorted(au.screening_frame())

    def _edge(t):
        return {"reporting_company": t, "reporting_cik": "0", "form": "10-K",
                "named_counterparty": "Acme Holdings Inc.",
                "counterparty_is_named": True, "direction": "customer",
                "concentration_pct": 24.0,
                "concentration_basis": au.REQUIRED_BASIS,
                "concentration_basis_text": "our total consolidated revenues",
                "as_of_date": "2026-05-08", "accession": "0-26-1"}

    with tempfile.TemporaryDirectory() as t:
        td = Path(t)

        # A screen where EVERY frame member qualifies. A universe equal to its
        # own frame means the rule selected nothing.
        whole = td / "whole.json"
        whole.write_text(json.dumps({
            "generated_at_utc": "2026-08-27T00:00:00+00:00",
            "coverage": {"companies_attempted": len(frame)},
            "edges": [_edge(x) for x in frame]}), encoding="utf-8")
        raised = ""
        try:
            build_v1_5(screen=whole)
        except RefusedError as e:
            raised = str(e)
        check("F2. a universe equal to the whole frame is refused",
              "decorative" in raised, raised or "no refusal")

        # A screen predating the denominator field.
        stale = td / "stale.json"
        stale.write_text(json.dumps({
            "generated_at_utc": "2026-08-26T00:00:00+00:00",
            "coverage": {"companies_attempted": len(frame)},
            "edges": [{k: v for k, v in _edge(frame[0]).items()
                       if k != "concentration_basis"}]}), encoding="utf-8")
        raised = ""
        try:
            build_v1_5(screen=stale)
        except RefusedError as e:
            raised = str(e)
        check("F3. a screen the rule cannot evaluate is refused",
              "cannot be evaluated" in raised, raised or "no refusal")

        # HARDCODED-CLOSED CONTROL: a well-formed screen builds. Without this,
        # F2 and F3 would pass if build_v1_5 refused everything.
        ok = td / "ok.json"
        ok.write_text(json.dumps({
            "generated_at_utc": "2026-08-27T00:00:00+00:00",
            "coverage": {"companies_attempted": len(frame)},
            "edges": [_edge(frame[0])]}), encoding="utf-8")
        doc, changes, deriv = build_v1_5(screen=ok)
        check("F4. a well-formed screen builds", bool(changes))
        check("F5. and the built document carries THAT screen's member",
              _hyp(doc)["anchor_universe"]["derived_members"] == [frame[0]],
              str(_hyp(doc)["anchor_universe"]["derived_members"]))
        check("F6. which is not what the published artifact says -- the "
              "generator follows its input",
              deriv.members == (frame[0],), str(deriv.members))


def test_g_this_suite_writes_nothing() -> None:
    print("\n--- PART G: no side effects ---")
    check("G1. v1.4 unchanged by this suite", _sha256(V1_4) == V1_4_SHA256)
    if V1_5.is_file():
        doc = _load(V1_5)
        check("G2. v1.5 still parses and reports 1.5",
              str(doc.get("registry_version")) == "1.5")


def test_h_offline() -> None:
    try:
        socket.getaddrinfo("www.sec.gov", 443)
        check("H1. network blocked", False, "a lookup succeeded")
    except NetworkBlocked:
        check("H1. network blocked", True)


if __name__ == "__main__":
    test_a_the_published_artifact()
    test_b_the_member_list_still_follows_from_the_rule()
    test_c_pkg_is_excluded_and_the_reason_is_recorded()
    test_d_the_gate_did_not_move()
    test_e_immovables()
    test_f_the_generator_refuses()
    test_g_this_suite_writes_nothing()
    test_h_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 REGISTRY v1.5 TESTS PASSED")
    sys.exit(0)
