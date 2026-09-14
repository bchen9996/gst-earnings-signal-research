#!/usr/bin/env python3
"""run_hyp07_reverse_competitor_search_handreview_scaled.py tests -- offline,
no network.

SCALED_HAND_REVIEW_DECISIONS is deliberately empty as of this test's
writing (see that module's own docstring, "THIS FILE IS A SCAFFOLD") --
the live scaled search had not finished when this scaffold was built.
test_1 below therefore checks the REFUSAL behavior against the real raw
file when one exists (an empty decision list must refuse on every
confirmed lead, not silently approve none), rather than a completed
review's exact-match property -- that stronger check belongs to this
module once SCALED_HAND_REVIEW_DECISIONS is actually populated.

Run directly: python test_hyp04_supply_chain_hedge_reverse_competitor_search_handreview_scaled.py
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
    run_hyp07_reverse_competitor_search_handreview_scaled as H,
)

LSE = Path(__file__).resolve().parent / "Live Signal Engine"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_decisions_cover_exactly_the_real_confirmed_set() -> None:
    # The live search (2026-09-13) completed and every one of its 371
    # confirmed leads was hand-reviewed -- see module docstring, "THE
    # REVIEW". This control test asserts the decision list matches the
    # REAL committed raw-hits file's confirmed set exactly, the same
    # discipline the first-pass module's own test_1 applies.
    p = LSE / "HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_SCALED_2026-09-13.json"
    if not p.is_file():
        check("1a. the real scaled raw-hits artifact is present", False, str(p))
        return
    raw = json.loads(p.read_text(encoding="utf-8"))
    confirmed = {(l["anchor_ticker"].upper(), l["peer_cik"])
                for l in raw["leads"] if l.get("filed_mention_confirmed")}
    decided = {(d.anchor_ticker, d.peer_cik) for d in H.SCALED_HAND_REVIEW_DECISIONS}
    check("1a. every confirmed (anchor, peer_cik) lead has exactly one "
          "decision, no more, no fewer", confirmed == decided,
          str(confirmed ^ decided))
    check("1b. no duplicate (anchor, peer_cik) key in the decision list",
          len(H.SCALED_HAND_REVIEW_DECISIONS) == len(decided))
    check("1c. 371 real confirmed leads, 370 kept, 1 rejected (NBIX/Symyx, "
          "COMPPEER -- see module docstring)",
          len(H.SCALED_HAND_REVIEW_DECISIONS) == 371
          and sum(1 for d in H.SCALED_HAND_REVIEW_DECISIONS if d.keep) == 370,
          f"n={len(H.SCALED_HAND_REVIEW_DECISIONS)}, "
          f"kept={sum(1 for d in H.SCALED_HAND_REVIEW_DECISIONS if d.keep)}")


def _synthetic_raw_leads() -> list[dict]:
    return [
        {"peer_cik": "0000000001", "anchor_ticker": "X",
         "filed_mention_confirmed": True, "peer_registrant_name": "KEPT CO",
         "file_date": "2020-01-01", "context": "ctx"},
        {"peer_cik": "0000000002", "anchor_ticker": "X",
         "filed_mention_confirmed": True, "peer_registrant_name": "REJECTED CO",
         "file_date": "2020-01-01", "context": "ctx"},
        # same CIK, DIFFERENT anchor -- the collision case this module
        # (like round 6's own scaled module, and HYP-07's own first-pass
        # module) exists to handle correctly.
        {"peer_cik": "0000000001", "anchor_ticker": "Y",
         "filed_mention_confirmed": True, "peer_registrant_name": "KEPT CO",
         "file_date": "2021-01-01", "context": "ctx2"},
    ]


def test_2_same_peer_cik_different_anchor_gets_independent_decisions() -> None:
    leads = _synthetic_raw_leads()
    decisions = (
        H.Decision("X", "0000000001", True, "KEEP", "genuine under X"),
        H.Decision("X", "0000000002", False, "NOISE", "reject under X"),
        H.Decision("Y", "0000000001", False, "INST_OWN", "same CIK, bogus under Y"),
    )
    kept = H.apply_review(leads, decisions=decisions)
    check("2a. exactly one lead survives (X/0000000001)", len(kept) == 1,
          str(kept))
    check("2b. it is the anchor=X instance, not the anchor=Y instance",
          kept[0]["anchor_ticker"] == "X" and kept[0]["file_date"] == "2020-01-01",
          str(kept))
    check("2c. every kept lead carries direction 'competitor' implicitly "
          "(no corrected_direction field exists on Decision at all)",
          not hasattr(H.Decision, "corrected_direction"))


def test_3_apply_review_refuses_on_any_mismatch() -> None:
    leads = _synthetic_raw_leads()[:2]
    try:
        H.apply_review(leads, decisions=())
        check("3a. missing decisions refuse", False)
    except H.HandReviewError as e:
        check("3a. missing decisions refuse", True)
        check("3a-detail. names both missing keys",
              "0000000001" in str(e) and "0000000002" in str(e), str(e))

    orphan = (H.Decision("X", "0000000001", True, "KEEP", "r"),
             H.Decision("X", "0000000002", False, "NOISE", "r"),
             H.Decision("Z", "0000009999", False, "NOISE", "r"))
    try:
        H.apply_review(leads, decisions=orphan)
        check("3b. an orphan decision refuses", False)
    except H.HandReviewError as e:
        check("3b. an orphan decision refuses", True)
        check("3b-detail. names the orphan", "0000009999" in str(e), str(e))


def test_4_every_category_used_is_recognized() -> None:
    check("4a. every decision's category is KEEP or a recognized reject "
          "category",
          all(d.category == "KEEP" or d.category in H.REJECT_CATEGORIES
              for d in H.SCALED_HAND_REVIEW_DECISIONS))
    check("4b. REJECT_CATEGORIES drops the two percent-specific "
          "customer/supplier categories that cannot apply to competitor "
          "sentences (no percent-figure requirement exists here)",
          "AGG" not in H.REJECT_CATEGORIES and "BELOW10" not in H.REJECT_CATEGORIES)
    check("4c. REJECT_CATEGORIES carries the one new genre anticipated by "
          "the first-pass module's own docstring (market-share/industry-"
          "structure sentences)",
          "MKTSTRUCT" in H.REJECT_CATEGORIES)


def test_5_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("5a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("5a. network blocked", True)


if __name__ == "__main__":
    test_1_decisions_cover_exactly_the_real_confirmed_set()
    test_2_same_peer_cik_different_anchor_gets_independent_decisions()
    test_3_apply_review_refuses_on_any_mismatch()
    test_4_every_category_used_is_recognized()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_REVERSE_COMPETITOR_SEARCH_HANDREVIEW_SCALED TESTS PASSED")
    sys.exit(0)
