#!/usr/bin/env python3
"""hand_curated_candidates.py tests -- the proposal list itself is pure
data (no functions, no network), so what's actually checkable is its own
internal contract: every proposal targets one of HYP-04's 7 real anchors,
uses a valid direction, is non-empty, and no (anchor, name) pair repeats.

None of this proves any proposal is TRUE -- that is exactly what
run_hyp05_verify_candidates.py's live full-text-search step is for. This
test only catches the kind of mistake that would be embarrassing before
spending a real SEC request on it: a typo'd anchor ticker, a duplicate
entry, an empty basis note, or a direction outside the extractor's own
vocabulary.

Fully offline, no fixtures needed. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_hand_curated_candidates.py
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

from hyp04_supply_chain_hedge.hand_curated_candidates import (  # noqa: E402
    PROPOSED_CANDIDATES,
)

FAILURES: list[str] = []

# HYP-04's real, verified anchor set (see peer_selection.py's docstring for
# how this was confirmed) -- the only tickers a hand-curated proposal
# should ever target.
REAL_ANCHORS = frozenset({"ADBE", "CTSH", "INTC", "JBL", "MCK", "NKE", "NVDA"})
VALID_DIRECTIONS = frozenset({"competitor", "supplier", "customer"})


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_nonempty() -> None:
    check("1a. at least one proposal exists", len(PROPOSED_CANDIDATES) > 0)


def test_2_every_anchor_is_a_real_anchor() -> None:
    bad = sorted({c.anchor_ticker for c in PROPOSED_CANDIDATES} - REAL_ANCHORS)
    check("2a. every proposal targets one of the 7 real anchors",
          not bad, f"bad anchors: {bad}")


def test_3_every_direction_is_valid() -> None:
    bad = sorted({c.direction for c in PROPOSED_CANDIDATES} - VALID_DIRECTIONS)
    check("3a. every proposal uses a direction the extractor understands",
          not bad, f"bad directions: {bad}")


def test_4_no_duplicate_anchor_name_pairs() -> None:
    pairs = [(c.anchor_ticker, c.counterparty_name) for c in PROPOSED_CANDIDATES]
    check("4a. no (anchor, counterparty_name) pair repeats",
          len(pairs) == len(set(pairs)),
          f"duplicates: {[p for p in set(pairs) if pairs.count(p) > 1]}")


def test_5_no_empty_fields() -> None:
    empty = [c for c in PROPOSED_CANDIDATES
             if not c.counterparty_name.strip() or not c.basis.strip()]
    check("5a. every proposal has a non-empty name and basis note",
          not empty, f"empty entries: {empty}")


def test_6_every_real_anchor_has_at_least_one_proposal() -> None:
    covered = {c.anchor_ticker for c in PROPOSED_CANDIDATES}
    missing = sorted(REAL_ANCHORS - covered)
    check("6a. every one of the 7 real anchors has at least one proposal",
          not missing, f"anchors with zero proposals: {missing}")


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_nonempty()
    test_2_every_anchor_is_a_real_anchor()
    test_3_every_direction_is_valid()
    test_4_no_duplicate_anchor_name_pairs()
    test_5_no_empty_fields()
    test_6_every_real_anchor_has_at_least_one_proposal()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HAND_CURATED_CANDIDATES TESTS PASSED")
    sys.exit(0)
