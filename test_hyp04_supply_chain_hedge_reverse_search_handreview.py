#!/usr/bin/env python3
"""run_hyp05_reverse_search_handreview.py tests -- offline, hermetic, no
network.

  THE DECISION LIST COVERS EXACTLY THE REAL RAW FILE'S CONFIRMED SET
  (test_1, a control) -- proves HAND_REVIEW_DECISIONS against the actual
  committed HYP05_REVERSE_SEARCH_RAW_HITS_2026-09-12.json, not a
  synthetic fixture, since a decision list reviewed against the wrong
  data is worse than no review at all.

  apply_review REFUSES ON ANY MISMATCH (test_2) -- a confirmed lead with
  no decision, or a decision naming a lead that doesn't exist, both
  refuse rather than silently reviewing (or skipping) the wrong thing.

  THE FOUR FALSE POSITIVES AND THE ONE WRONG-SCHEMA ENTRY ARE DROPPED,
  BY NAME (test_3). DIRECTIONS ARE CORRECTED, NOT LEFT AS THE RAW
  MODULE'S HARDCODED "customer" (test_4).

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_reverse_search_handreview.py
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
    run_hyp05_reverse_search_handreview as H,
)

LSE = Path(__file__).resolve().parent / "Live Signal Engine"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_decisions_cover_exactly_the_real_confirmed_set() -> None:
    p = LSE / "HYP05_REVERSE_SEARCH_RAW_HITS_2026-09-12.json"
    if not p.is_file():
        check("1a. the real raw hits artifact is present on disk", False,
              str(p))
        return
    raw = json.loads(p.read_text(encoding="utf-8"))
    confirmed_ciks = {l["peer_cik"] for l in raw["leads"]
                      if l.get("filed_mention_confirmed")}
    decided_ciks = {d.peer_cik for d in H.HAND_REVIEW_DECISIONS}
    check("1a. every confirmed lead has exactly one decision, no more, "
          "no fewer", confirmed_ciks == decided_ciks,
          str((confirmed_ciks ^ decided_ciks)))
    check("1b. no duplicate peer_cik in the decision list",
          len(H.HAND_REVIEW_DECISIONS) == len(decided_ciks))


def _synthetic_raw_leads() -> list[dict]:
    return [
        {"peer_cik": "0000000001", "filed_mention_confirmed": True,
         "anchor_ticker": "X", "peer_registrant_name": "KEPT CO",
         "file_date": "2020-01-01", "context": "ctx"},
        {"peer_cik": "0000000002", "filed_mention_confirmed": True,
         "anchor_ticker": "X", "peer_registrant_name": "REJECTED CO",
         "file_date": "2020-01-01", "context": "ctx"},
        {"peer_cik": "0000000003", "filed_mention_confirmed": False,
         "anchor_ticker": "X", "peer_registrant_name": "NEVER CONFIRMED CO",
         "file_date": "2020-01-01", "context": "ctx"},
    ]


def test_2_apply_review_refuses_on_any_mismatch() -> None:
    leads = _synthetic_raw_leads()

    # No decision at all for a confirmed lead.
    try:
        H.apply_review(leads, decisions=())
        check("2a. a confirmed lead with no decision refuses", False)
    except H.HandReviewError as e:
        check("2a. a confirmed lead with no decision refuses", True)
        check("2a-detail. names the missing CIK(s)",
              "0000000001" in str(e) and "0000000002" in str(e), str(e))

    # A decision naming a lead that was never confirmed (or doesn't exist).
    orphan = (H.Decision("0000000001", True, "supplier", "r"),
             H.Decision("0000000002", True, "supplier", "r"),
             H.Decision("0000009999", False, None, "r"))
    try:
        H.apply_review(leads, decisions=orphan)
        check("2b. a decision naming a nonexistent lead refuses", False)
    except H.HandReviewError as e:
        check("2b. a decision naming a nonexistent lead refuses", True)
        check("2b-detail. names the orphan CIK", "0000009999" in str(e), str(e))


def test_3_kept_and_rejected_leads_are_exactly_right() -> None:
    leads = _synthetic_raw_leads()
    decisions = (
        H.Decision("0000000001", True, "supplier", "keep this one"),
        H.Decision("0000000002", False, None, "reject this one"),
    )
    kept = H.apply_review(leads, decisions=decisions)
    check("3a. exactly one lead survives", len(kept) == 1, str(kept))
    check("3b. it is the KEPT one, not the REJECTED one",
          kept[0]["peer_cik"] == "0000000001", str(kept))


def test_4_directions_are_actually_corrected() -> None:
    leads = [{"peer_cik": "0000000001", "filed_mention_confirmed": True,
             "anchor_ticker": "X", "peer_registrant_name": "CO",
             "file_date": "2020-01-01", "context": "ctx"}]
    decisions = (H.Decision("0000000001", True, "supplier", "r"),)
    kept = H.apply_review(leads, decisions=decisions)
    check("4a. corrected_direction is carried onto the kept lead",
          kept[0]["corrected_direction"] == "supplier", str(kept))
    check("4b. the hand_review_reason is carried too, for the audit trail",
          kept[0]["hand_review_reason"] == "r", str(kept))


def test_5_the_real_review_drops_exactly_the_five_named_entries() -> None:
    """Control, against the real decision list: the 4 false positives +
    1 wrong-schema entry this module's own docstring names are the ones
    that actually get dropped, by CIK, not by count alone."""
    dropped = {d.peer_cik for d in H.HAND_REVIEW_DECISIONS if not d.keep}
    expected = {
        "0000882104",  # PDL Biopharma -- bond coupon rate false positive
        "0000925178",  # Movie Gallery -- market share false positive
        "0000933020",  # Global Payment Technologies -- name collision
        "0000723125",  # Micron -- real relationship, wrong schema
        "0001125259",  # Carnival PLC -- market share false positive
    }
    check("5a. exactly the five named entries are dropped, no others",
          dropped == expected, str(dropped ^ expected))


def test_6_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("6a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("6a. network blocked", True)


if __name__ == "__main__":
    test_1_decisions_cover_exactly_the_real_confirmed_set()
    test_2_apply_review_refuses_on_any_mismatch()
    test_3_kept_and_rejected_leads_are_exactly_right()
    test_4_directions_are_actually_corrected()
    test_5_the_real_review_drops_exactly_the_five_named_entries()
    test_6_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_REVERSE_SEARCH_HANDREVIEW TESTS PASSED")
    sys.exit(0)
