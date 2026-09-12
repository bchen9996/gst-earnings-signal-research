#!/usr/bin/env python3
"""historical_walk_candidates.py tests -- reshaping a competitor-history-
walk report into the candidate-linkage edges shape run_hyp05_peer_name_
search.py and run_hyp05_peer_market_cap.py already read.

Fully offline, synthetic fixture written to a temp dir. Sockets blocked
before import.

Run directly: python test_hyp04_supply_chain_hedge_historical_walk_candidates.py
"""
from __future__ import annotations

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

from hyp04_supply_chain_hedge.historical_walk_candidates import (  # noqa: E402
    SOURCE_HISTORICAL_WALK,
    edges_from_walk,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hist_walk_cand_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


_WALK = {
    "tickers": [
        {
            "ticker": "ADBE",
            "cik": "0000796343",
            "named_counterparties": [
                {"counterparty": "Corel", "direction": "competitor",
                 "pattern": "competitors_include",
                 "earliest_filing_date": "2000-02-16",
                 "earliest_accession": "A-2000"},
                {"counterparty": "Apple", "direction": "competitor",
                 "pattern": "we_compete_with",
                 "earliest_filing_date": "2014-01-21",
                 "earliest_accession": "A-2014"},
            ],
        },
        {
            "ticker": "NVDA",
            "cik": "0001045810",
            "named_counterparties": [
                {"counterparty": "Nanya Technology Corporation",
                 "direction": "supplier", "pattern": "we_purchase_from",
                 "earliest_filing_date": "2011-03-16",
                 "earliest_accession": "A-2011"},
            ],
        },
    ],
}


def _write_walk() -> Path:
    p = TMP / "walk.json"
    p.write_text(json.dumps(_WALK), encoding="utf-8")
    return p


def test_1_only_allowlisted_names_survive() -> None:
    p = _write_walk()
    out = edges_from_walk(p, include=frozenset({"Corel",
                                                  "Nanya Technology Corporation"}))
    names = {e["named_counterparty"] for e in out["edges"]}
    check("1a. Apple (not in the allowlist) is excluded", "Apple" not in names)
    check("1b. exactly the two allowlisted names survive",
          names == {"Corel", "Nanya Technology Corporation"}, str(names))


def test_2_fields_match_what_downstream_consumers_read() -> None:
    p = _write_walk()
    out = edges_from_walk(p, include=frozenset({"Corel"}))
    e = out["edges"][0]
    check("2a. counterparty_is_named is set", e["counterparty_is_named"] is True)
    check("2b. reporting_company is the anchor ticker", e["reporting_company"] == "ADBE")
    check("2c. as_of_date comes from earliest_filing_date, not latest",
          e["as_of_date"] == "2000-02-16")
    check("2d. accession comes from earliest_accession",
          e["accession"] == "A-2000")
    check("2e. direction is carried over unchanged", e["direction"] == "competitor")
    check("2f. source is a distinct, identifiable historical-walk tag",
          e["source"] == SOURCE_HISTORICAL_WALK
          and e["source"] != "EDGAR_10K_ASC280"
          and "HISTORICAL_WALK" in e["source"])


def test_3_empty_include_yields_no_edges_not_an_error() -> None:
    p = _write_walk()
    out = edges_from_walk(p, include=frozenset())
    check("3a. an empty allowlist yields zero edges, not a crash",
          out["edges"] == [])


def test_4_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("4a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("4a. network blocked", True)


if __name__ == "__main__":
    test_1_only_allowlisted_names_survive()
    test_2_fields_match_what_downstream_consumers_read()
    test_3_empty_include_yields_no_edges_not_an_error()
    test_4_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HISTORICAL_WALK_CANDIDATES TESTS PASSED")
    sys.exit(0)
