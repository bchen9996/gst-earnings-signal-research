#!/usr/bin/env python3
"""run_hyp05_verify_candidates.py tests -- classify_context(), the pure
false-signal filter that decides whether a genuinely-found, genuinely-
readable context sentence actually supports a relationship claim.

Both patterns tested here were written to fix a REAL defect found by
hand-reading round 2's live output, not written speculatively:

  * STOCK_INDEX_COMEMBERSHIP -- five NKE candidates (Wolverine World
    Wide, Crocs, Deckers Outdoor, Skechers, Steven Madden) all
    "confirmed" purely from a stock-performance-graph benchmark-index
    table, not from anything NKE's own prose says about competitors.
  * BIOGRAPHICAL_YEAR_RANGE -- an MCK/Owens & Minor "hit" was actually a
    director's prior-employment bio ("Group Vice President and Corporate
    Officer, Owens & Minor (1994 - 1996)."), not a business relationship.

Both test sentences below are the ACTUAL real filed text captured in
HYP05_HAND_CURATED_VERIFICATION_ROUND2_2026-09-12.json, not paraphrases.

Fully offline, no network. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_verify_candidates.py
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

from hyp04_supply_chain_hedge.run_hyp05_verify_candidates import (  # noqa: E402
    classify_context,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_stock_index_comembership_rejected() -> None:
    # The real NKE/Wolverine World Wide sentence.
    sentence = (
        "19 Table of Contents COMPARISON OF 5-YEAR CUMULATIVE TOTAL "
        "RETURN AMONG NIKE, INC., S&P 500 INDEX, S&P APPAREL, "
        "ACCESSORIES & LUXURY GOODS INDEX, AND THE DOW JONES U.S. "
        "FOOTWEAR INDEX The Dow Jones U.S. Footwear Index consists of "
        "NIKE, Stride Rite Corp., Timberland Co., Wolverine World Wide, "
        "Inc., and Crocs, Inc.")
    reason = classify_context(sentence)
    check("1a. stock-index performance-graph sentence is rejected",
          reason is not None, f"got: {reason!r}")
    check("1b. rejection reason mentions the benchmark-index pattern",
          reason is not None and "benchmark-index" in reason)


def test_2_biographical_year_range_rejected() -> None:
    # The real MCK/Owens & Minor sentence.
    sentence = "Group Vice President and Corporate Officer, Owens & Minor (1994 - 1996)."
    reason = classify_context(sentence)
    check("2a. director prior-employment bio sentence is rejected",
          reason is not None, f"got: {reason!r}")
    check("2b. rejection reason mentions the biography pattern",
          reason is not None and "biograph" in reason)


def test_3_genuine_relationship_sentences_pass_through() -> None:
    # Real, GOOD sentences from the same live run -- must NOT be rejected.
    gopro = (
        "Based on net revenue, for the fiscal year ended August 31, "
        "2017, our largest customers include Apple, Inc., Cisco "
        "Systems, Inc., GoPro, Inc., Hewlett-Packard Company, Ingenico "
        "S.A., LM Ericsson Telephone Company, NetApp, Inc., Nokia "
        "Networks, Valeo S.A.")
    check("3a. real customer-concentration sentence is NOT rejected",
          classify_context(gopro) is None)

    nike_competitors = (
        "BY WAY OF ILLUSTRATION ONLY, examples of NIKE competitors "
        "include, but are not limited to: Adidas, FILA, Reebok, Puma, "
        "Champion, Oakley, DKNY, Converse, Asics, Saucony, New Balance, "
        "B.U.M, FUBU, The Gap, Tommy Hilfiger, Umbro, Northface, "
        "Venator (Footlockers), Sports Authority, Columbia Sportswear, "
        "Wilson, Mizuno, Callaway Golf and Titleist.")
    check("3b. real 'examples of competitors' sentence is NOT rejected",
          classify_context(nike_competitors) is None)


def test_4_empty_context_is_not_misclassified() -> None:
    check("4a. empty string yields no rejection reason (caller's job to "
          "gate on emptiness separately)", classify_context("") is None)


def test_5_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("5a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("5a. network blocked", True)


if __name__ == "__main__":
    test_1_stock_index_comembership_rejected()
    test_2_biographical_year_range_rejected()
    test_3_genuine_relationship_sentences_pass_through()
    test_4_empty_context_is_not_misclassified()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL VERIFY_CANDIDATES TESTS PASSED")
    sys.exit(0)
