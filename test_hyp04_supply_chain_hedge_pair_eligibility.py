#!/usr/bin/env python3
"""Tests for HYP-04 peer-side (anchor event x peer) pair eligibility.

Both directions, always. A rule that only ever denies is satisfied by a
function that returns False and is worthless, so the positive case in test_2
carries the same weight as the seven falsifications in test_3.

The load-bearing cases are the point-in-time boundary tests (test_4). P3 is the
reason this module exists: an edge curated from a document that exists NOW says
nothing about what an observer knew THEN, and this project already carries one
failed point-in-time validity check. An off-by-one there -- accepting an edge
established ON the event date -- would import exactly the hindsight the rule is
meant to exclude, and would do it silently.

Offline. No network. Synthetic edges only; no curated data exists.

Run directly: python test_hyp04_supply_chain_hedge_pair_eligibility.py
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from gst_market_response.completeness import (  # noqa: E402
    OptionBenchmarkDisposition,
    PRE_EVENT_TIER_CORE_ONLY,
    ModuleEligibility,
)
from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    CuratedEdge,
    load_curated_linkage,
)
from hyp04_supply_chain_hedge.pair_eligibility import (  # noqa: E402
    UNKNOWN_AS_OF_BASIS,
    PairEligibility,
    eligible_pairs,
    evaluate_pair,
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


EVENT_ID = "EVT-SYNTH-ANCHOR-0001"
EVENT_DATE = "2026-05-14"
ANCHOR = "NVDA"


def _edge(**over) -> CuratedEdge:
    """A fully valid SYNTHETIC edge. Not data."""
    base = dict(
        anchor_ticker="NVDA",
        peer_ticker="COHR",
        relationship_type="direct_supplier",
        direction="supplier",
        confidence="high",
        source_type="10-K Customer Concentration Note",
        source_citation="SYNTHETIC citation -- not a real filing",
        source_url="https://example.invalid/a",
        as_of_date="2026-02-25",
        as_of_date_basis="filing date of source",
        date_confidence="high",
        curated_by="test_fixture",
        curated_date="2026-08-20",
        review_status="reviewed",
        relationship_direction_notes="SYNTHETIC TEST ROW",
        notes_caveats="SYNTHETIC TEST FIXTURE - not real data",
        row_number=1,
    )
    base.update(over)
    return CuratedEdge(**base)


def _anchor_ok() -> ModuleEligibility:
    """A core-eligible anchor. Core-only is deliberate: options must not gate."""
    return ModuleEligibility(
        core_pre_event_eligible=True,
        option_benchmark_eligible=False,
        joint_full_eligible=False,
        pre_event_completeness_tier=PRE_EVENT_TIER_CORE_ONLY,
        option_benchmark_status=OptionBenchmarkDisposition.UNAVAILABLE_NO_VERIFIED_SOURCE,
        option_benchmark_unavailable_reason="no OPRA-entitled source")


def _anchor_bad() -> ModuleEligibility:
    return ModuleEligibility(
        core_pre_event_eligible=False,
        option_benchmark_eligible=False,
        joint_full_eligible=False,
        pre_event_completeness_tier=PRE_EVENT_TIER_CORE_ONLY,
        option_benchmark_status=OptionBenchmarkDisposition.UNAVAILABLE_NO_VERIFIED_SOURCE,
        option_benchmark_unavailable_reason="no OPRA-entitled source")


def _eval(edge=None, **over):
    kw = dict(
        event_id=EVENT_ID,
        event_date=EVENT_DATE,
        event_anchor_ticker=ANCHOR,
        anchor_eligibility=_anchor_ok(),
        peer_history_available=True,
    )
    kw.update(over)
    return evaluate_pair(edge or _edge(), **kw)


# ============ 1. shape ====================================================
def test_1_shape() -> None:
    r = _eval()
    check("1a. returns a PairEligibility", isinstance(r, PairEligibility))
    check("1b. it is frozen", type(r).__dataclass_params__.frozen)
    check("1c. eligible is True only when denials is empty",
          r.eligible == (not r.denials))
    check("1d. status reads ELIGIBLE", r.status == "ELIGIBLE")
    check("1e. it carries the pair and the event",
          r.anchor_ticker == "NVDA" and r.peer_ticker == "COHR"
          and r.event_id == EVENT_ID)
    check("1f. as_dict round-trips the denials as a list",
          isinstance(r.as_dict()["denials"], list))


# ============ 2. THE POSITIVE CASE ========================================
def test_2_a_fully_valid_pair_is_eligible() -> None:
    """Without this, a function hardcoded to deny would pass every other test."""
    r = _eval()
    check("2a. a fully valid pair IS eligible", r.eligible is True,
          str(r.denials))
    check("2b. with zero denials", r.denials == ())
    check("2c. the anchor was checked, not assumed",
          r.evidence["anchor_core_eligible"] is True)
    check("2d. the point-in-time comparison was actually made",
          r.evidence["as_of_strictly_before_event"] is True)
    check("2e. direction came from the closed lookup",
          r.evidence["direction"] == "supplier")

    # Options must NOT gate: the anchor above is core-only, and D9 makes IV a
    # conditional secondary target. If this ever fails, someone has added an
    # options requirement that would exclude the thin peers this hypothesis
    # exists to study.
    check("2f. a core-ONLY anchor (no option benchmark) is still eligible",
          _eval(anchor_eligibility=_anchor_ok()).eligible is True)


# ============ 3. each condition falsified ALONE ===========================
def test_3_each_condition_denies_on_its_own() -> None:
    cases = [
        ("P1 anchor not core-eligible", dict(anchor_eligibility=_anchor_bad()), "P1"),
        ("P1 anchor eligibility not supplied", dict(anchor_eligibility=None), "P1"),
        ("P2 edge belongs to another anchor",
         dict(edge=_edge(anchor_ticker="AAPL")), "P2"),
        ("P2 peer blank", dict(edge=_edge(peer_ticker="")), "P2"),
        ("P2 peer equals anchor", dict(edge=_edge(peer_ticker="NVDA")), "P2"),
        ("P3 as_of_date after the event",
         dict(edge=_edge(as_of_date="2026-09-01")), "P3"),
        ("P3 as_of_date malformed",
         dict(edge=_edge(as_of_date="25/02/2026")), "P3"),
        ("P3 event_date malformed", dict(event_date="not a date"), "P3"),
        ("P4 as_of basis unknown/uncertain",
         dict(edge=_edge(as_of_date_basis=UNKNOWN_AS_OF_BASIS)), "P4"),
        ("P4 as_of basis outside the vocabulary",
         dict(edge=_edge(as_of_date_basis="I reckon")), "P4"),
        ("P5 peer history explicitly absent",
         dict(peer_history_available=False), "P5"),
        ("P6 relationship_type outside the vocabulary",
         dict(edge=_edge(relationship_type="supplier")), "P6"),
        ("P7 derived from placeholder linkage",
         dict(from_placeholder_linkage=True), "P7"),
    ]
    for label, over, code in cases:
        edge = over.pop("edge", None)
        r = _eval(edge, **over)
        check(f"3a. '{label}' denies", r.eligible is False)
        check(f"3b. '{label}' names {code}",
              any(d.startswith(code) for d in r.denials), str(r.denials))

    # P5's unknown is a THIRD state, distinct from False, and also denies.
    r = evaluate_pair(_edge(), event_id=EVENT_ID, event_date=EVENT_DATE,
                      event_anchor_ticker=ANCHOR,
                      anchor_eligibility=_anchor_ok())
    check("3c. P5 unsupplied peer history denies (unknown is not available)",
          r.eligible is False and any(d.startswith("P5") for d in r.denials))
    check("3d. and records it as None, not False",
          r.evidence["peer_history_available"] is None)


# ============ 4. the point-in-time boundary ===============================
def test_4_point_in_time_boundary_is_strict() -> None:
    """STRICTLY before. An edge established ON the event day does not count."""
    day_before = _eval(_edge(as_of_date="2026-05-13"))
    check("4a. as_of_date one day BEFORE the event is eligible",
          day_before.eligible is True, str(day_before.denials))

    same_day = _eval(_edge(as_of_date=EVENT_DATE))
    check("4b. as_of_date EQUAL to the event date is INELIGIBLE",
          same_day.eligible is False)
    check("4c. and it is P3 that refuses it",
          any(d.startswith("P3") for d in same_day.denials), str(same_day.denials))

    day_after = _eval(_edge(as_of_date="2026-05-15"))
    check("4d. as_of_date one day AFTER the event is ineligible",
          day_after.eligible is False)

    # An unknown basis is refused even when the DATE is comfortably valid --
    # the two conditions are independent, and a good-looking date does not
    # rescue a date nobody can source.
    unknown_basis = _eval(_edge(as_of_date="2020-01-01",
                                as_of_date_basis=UNKNOWN_AS_OF_BASIS))
    check("4e. a well-formed early date does NOT rescue an unknown basis",
          unknown_basis.eligible is False
          and any(d.startswith("P4") for d in unknown_basis.denials))


# ============ 5. the batch splitter =======================================
def test_5_eligible_pairs_splits_and_denies_unknown_peers() -> None:
    edges = [_edge(peer_ticker="COHR"), _edge(peer_ticker="JBL"),
             _edge(peer_ticker="AAPL", as_of_date="2026-09-01")]
    ok, no = eligible_pairs(
        edges, event_id=EVENT_ID, event_date=EVENT_DATE,
        event_anchor_ticker=ANCHOR, anchor_eligibility=_anchor_ok(),
        peer_history={"COHR": True, "JBL": False})

    check("5a. the valid pair is eligible",
          [p.peer_ticker for p in ok] == ["COHR"], str([p.peer_ticker for p in ok]))
    check("5b. every other pair is ineligible", len(no) == 2)
    check("5c. counts reconcile", len(ok) + len(no) == len(edges))
    check("5d. a peer ABSENT from the history map denies as unknown",
          any(p.peer_ticker == "AAPL"
              and p.evidence["peer_history_available"] is None for p in no))
    check("5e. an explicit False also denies",
          any(p.peer_ticker == "JBL"
              and p.evidence["peer_history_available"] is False for p in no))

    # No history map at all: every peer is unknown, so nothing is eligible.
    ok2, no2 = eligible_pairs(
        edges, event_id=EVENT_ID, event_date=EVENT_DATE,
        event_anchor_ticker=ANCHOR, anchor_eligibility=_anchor_ok())
    check("5f. with no history map supplied, nothing is eligible",
          ok2 == [] and len(no2) == len(edges))


# ============ 6. the live repo ============================================
def test_6_no_pair_is_eligible_today() -> None:
    """Zero rows are curated, so no pair can be eligible in the real repo."""
    lse = Path(__file__).resolve().parent / "Live Signal Engine"
    found = sorted(lse.glob("HYP04_Linkage_Map*.csv")) if lse.is_dir() else []
    if not found:
        check("6a. no curated linkage file exists, so zero pairs are eligible",
              True)
        skip("6b. live curated file evaluated", "no HYP04_Linkage_Map*.csv exists")
        return
    res = load_curated_linkage(found[0])
    ok, _ = eligible_pairs(
        res.edges, event_id=EVENT_ID, event_date=EVENT_DATE,
        event_anchor_ticker=ANCHOR, anchor_eligibility=_anchor_ok())
    check("6b. a live curated file yields no eligible pair without peer history",
          ok == [])


def test_7_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("7a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("7a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_shape()
    test_2_a_fully_valid_pair_is_eligible()
    test_3_each_condition_denies_on_its_own()
    test_4_point_in_time_boundary_is_strict()
    test_5_eligible_pairs_splits_and_denies_unknown_peers()
    test_6_no_pair_is_eligible_today()
    test_7_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PAIR-ELIGIBILITY TESTS PASSED")
    sys.exit(0)
