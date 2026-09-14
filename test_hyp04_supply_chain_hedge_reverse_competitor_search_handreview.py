#!/usr/bin/env python3
"""run_hyp07_reverse_competitor_search_handreview.py tests -- offline,
hermetic, no network.

  THE DECISION LIST COVERS EXACTLY THE REAL RAW FILE'S CONFIRMED SET
  (test_1, a control) -- proves HAND_REVIEW_DECISIONS against the actual
  committed HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_2026-09-13.json, not
  a synthetic fixture.

  apply_review REFUSES ON ANY MISMATCH (test_2) -- a confirmed lead with
  no decision, or a decision naming a (anchor_ticker, peer_cik) pair that
  doesn't exist, both refuse.

  THE (anchor_ticker, peer_cik) KEY NEVER COLLAPSES TWO DISTINCT ANCHOR-
  PAIRS SHARING ONE peer_cik (test_3) -- the real bug this module's own
  design fixes relative to round 4's peer_cik-only key (FISERV INC
  genuinely recurs under AAPL/GOOGL/SBUX in the real data).

  KEPT LEADS ARE EXACTLY RIGHT (test_4).

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_reverse_competitor_search_handreview.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import (  # noqa: E402
    run_hyp07_reverse_competitor_search_handreview as H,
)

LSE = Path(__file__).resolve().parent / "Live Signal Engine"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_decisions_cover_exactly_the_real_confirmed_set() -> None:
    p = LSE / "HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_2026-09-13.json"
    if not p.is_file():
        check("1a. the real raw hits artifact is present on disk", False,
              str(p))
        return
    raw = json.loads(p.read_text(encoding="utf-8"))
    confirmed_keys = {(l["anchor_ticker"], l["peer_cik"]) for l in raw["leads"]
                      if l.get("filed_mention_confirmed")}
    decided_keys = {(d.anchor_ticker, d.peer_cik)
                    for d in H.HAND_REVIEW_DECISIONS}
    check("1a. every confirmed lead has exactly one decision, no more, "
          "no fewer", confirmed_keys == decided_keys,
          str(confirmed_keys ^ decided_keys))
    check("1b. no duplicate (anchor_ticker, peer_cik) in the decision list",
          len(H.HAND_REVIEW_DECISIONS) == len(decided_keys))
    check("1c. 33 real confirmed leads, all kept (none rejected -- see "
          "module docstring)", len(confirmed_keys) == 33, str(len(confirmed_keys)))


def _synthetic_raw_leads() -> list[dict]:
    return [
        {"peer_cik": "0000000001", "anchor_ticker": "X",
         "filed_mention_confirmed": True, "peer_registrant_name": "KEPT CO",
         "file_date": "2020-01-01", "context": "ctx"},
        {"peer_cik": "0000000002", "anchor_ticker": "X",
         "filed_mention_confirmed": True,
         "peer_registrant_name": "REJECTED CO", "file_date": "2020-01-01",
         "context": "ctx"},
        {"peer_cik": "0000000003", "anchor_ticker": "X",
         "filed_mention_confirmed": False,
         "peer_registrant_name": "NEVER CONFIRMED CO",
         "file_date": "2020-01-01", "context": "ctx"},
    ]


def test_2_apply_review_refuses_on_any_mismatch() -> None:
    leads = _synthetic_raw_leads()

    try:
        H.apply_review(leads, decisions=())
        check("2a. a confirmed lead with no decision refuses", False)
    except H.HandReviewError as e:
        check("2a. a confirmed lead with no decision refuses", True)
        check("2a-detail. names the missing key(s)",
              "0000000001" in str(e) and "0000000002" in str(e), str(e))

    orphan = (H.Decision("X", "0000000001", True, "r"),
             H.Decision("X", "0000000002", True, "r"),
             H.Decision("X", "0000009999", False, "r"))
    try:
        H.apply_review(leads, decisions=orphan)
        check("2b. a decision naming a nonexistent (anchor, cik) pair "
              "refuses", False)
    except H.HandReviewError as e:
        check("2b. a decision naming a nonexistent (anchor, cik) pair "
              "refuses", True)
        check("2b-detail. names the orphan CIK", "0000009999" in str(e), str(e))


def test_3_anchor_peer_key_never_collapses_two_distinct_pairs() -> None:
    """The real bug this module's design fixes relative to round 4's
    peer_cik-only Decision key: the SAME peer_cik confirmed under TWO
    different anchors must produce TWO independent decisions, neither
    silently dropped or merged."""
    leads = [
        {"peer_cik": "0000798354", "anchor_ticker": "AAPL",
         "filed_mention_confirmed": True, "peer_registrant_name": "FISERV",
         "file_date": "2016-02-19", "context": "ctx-aapl"},
        {"peer_cik": "0000798354", "anchor_ticker": "GOOGL",
         "filed_mention_confirmed": True, "peer_registrant_name": "FISERV",
         "file_date": "2017-02-23", "context": "ctx-googl"},
    ]
    decisions = (
        H.Decision("AAPL", "0000798354", True, "kept under AAPL"),
        H.Decision("GOOGL", "0000798354", True, "kept under GOOGL"),
    )
    kept = H.apply_review(leads, decisions=decisions)
    check("3a. BOTH anchor-pairs survive, not collapsed to one",
          len(kept) == 2, str(kept))
    by_anchor = {k["anchor_ticker"]: k for k in kept}
    check("3b. the AAPL entry keeps its OWN file_date",
          by_anchor["AAPL"]["file_date"] == "2016-02-19", str(by_anchor))
    check("3c. the GOOGL entry keeps its OWN, DIFFERENT file_date",
          by_anchor["GOOGL"]["file_date"] == "2017-02-23", str(by_anchor))

    # One kept, the other rejected -- independently, same peer_cik.
    mixed = (
        H.Decision("AAPL", "0000798354", True, "kept under AAPL"),
        H.Decision("GOOGL", "0000798354", False, "rejected under GOOGL"),
    )
    kept2 = H.apply_review(leads, decisions=mixed)
    check("3d. one anchor's decision does not leak into the other's",
          len(kept2) == 1 and kept2[0]["anchor_ticker"] == "AAPL", str(kept2))


def test_4_kept_and_rejected_leads_are_exactly_right() -> None:
    leads = _synthetic_raw_leads()
    decisions = (
        H.Decision("X", "0000000001", True, "keep this one"),
        H.Decision("X", "0000000002", False, "reject this one"),
    )
    kept = H.apply_review(leads, decisions=decisions)
    check("4a. exactly one lead survives", len(kept) == 1, str(kept))
    check("4b. it is the KEPT one, not the REJECTED one",
          kept[0]["peer_cik"] == "0000000001", str(kept))
    check("4c. hand_review_reason is carried, for the audit trail",
          kept[0]["hand_review_reason"] == "keep this one", str(kept))


def test_5_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("5a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("5a. network blocked", True)


if __name__ == "__main__":
    test_1_decisions_cover_exactly_the_real_confirmed_set()
    test_2_apply_review_refuses_on_any_mismatch()
    test_3_anchor_peer_key_never_collapses_two_distinct_pairs()
    test_4_kept_and_rejected_leads_are_exactly_right()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_REVERSE_COMPETITOR_SEARCH_HANDREVIEW TESTS PASSED")
    sys.exit(0)
