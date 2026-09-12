#!/usr/bin/env python3
"""run_hyp05_peer_name_search.py tests -- ticker_map_fallback_ciks(), the
pure fallback lookup added after a live run found browse-edgar's own
company search returning a genuinely empty feed for 'Columbia Sportswear'
(a real, currently-trading company, CIK 0001050797) and a corrupted,
name-free response (literal 'ARRAY(0x...)' Perl dumps) for the broader
'Columbia' query -- reproduced directly against the live endpoint, not
assumed.

The synthetic tmap fixture below mirrors company_tickers.json's real
shape: {"0": {"cik_str": int, "ticker": str, "title": str}, ...}.

Fully offline, no network. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_hyp05_name_search_fallback.py
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

from hyp04_supply_chain_hedge.run_hyp05_peer_name_search import (  # noqa: E402
    ticker_map_fallback_ciks,
)

FAILURES: list[str] = []

TMAP = {
    "0": {"cik_str": 1050797, "ticker": "COLM", "title": "COLUMBIA SPORTSWEAR CO"},
    "1": {"cik_str": 1500435, "ticker": "GPRO", "title": "GoPro, Inc."},
    "2": {"cik_str": 99999, "ticker": "COLB", "title": "Columbia Banking System, Inc."},
}


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_exact_real_case_resolves() -> None:
    ciks = ticker_map_fallback_ciks(TMAP, "Columbia Sportswear")
    check("1a. Columbia Sportswear resolves to its real CIK",
          ciks == ["0001050797"], str(ciks))


def test_2_case_insensitive() -> None:
    ciks = ticker_map_fallback_ciks(TMAP, "columbia sportswear")
    check("2a. lookup is case-insensitive", ciks == ["0001050797"], str(ciks))


def test_3_prefix_not_substring() -> None:
    # "Sportswear" alone should NOT match "COLUMBIA SPORTSWEAR CO" -- this
    # is a prefix match on the registered title, same discipline
    # browse-edgar's own company= search documents for itself.
    ciks = ticker_map_fallback_ciks(TMAP, "Sportswear")
    check("3a. a non-prefix substring does not match", ciks == [], str(ciks))


def test_4_ambiguous_prefix_returns_all_candidates() -> None:
    # "Columbia" alone is a real prefix of BOTH Columbia Sportswear and
    # Columbia Banking System -- both come back; disambiguation is the
    # caller's (lineage test's) job, not this function's.
    ciks = ticker_map_fallback_ciks(TMAP, "Columbia")
    check("4a. an ambiguous prefix returns every matching candidate",
          sorted(ciks) == sorted(["0001050797", "0000099999"]), str(ciks))


def test_5_no_match_returns_empty_not_a_crash() -> None:
    ciks = ticker_map_fallback_ciks(TMAP, "Nonexistent Company Name")
    check("5a. no match returns an empty list, not an error", ciks == [])


def test_6_empty_name_returns_empty() -> None:
    ciks = ticker_map_fallback_ciks(TMAP, "")
    check("6a. an empty name returns an empty list, not everything",
          ciks == [], str(ciks))


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_exact_real_case_resolves()
    test_2_case_insensitive()
    test_3_prefix_not_substring()
    test_4_ambiguous_prefix_returns_all_candidates()
    test_5_no_match_returns_empty_not_a_crash()
    test_6_empty_name_returns_empty()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_NAME_SEARCH_FALLBACK TESTS PASSED")
    sys.exit(0)
