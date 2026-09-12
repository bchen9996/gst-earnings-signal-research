#!/usr/bin/env python3
"""Tests for the competitor/supplier 10-K history walk -- HYP-05.

The runner itself makes REAL SEC REQUESTS and is deliberately named off the
`test_*` pattern, so nothing here invokes it against the network. What IS
tested is everything that decides what the walk means: earliest/latest
selection per (counterparty, direction) pair, and the report shape.
`all_10ks` pagination itself is already covered by test_hyp04_supply_chain_
hedge_linkage_history.py and unchanged here -- not re-tested.

Offline. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_competitor_history_walk.py
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

from hyp04_supply_chain_hedge.run_competitor_history_walk import (  # noqa: E402
    DEFAULT_TICKERS,
    TickerCompetitorHistory,
    build_report,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _disclosure(name: str, direction: str, pattern: str = "we_compete_with") -> dict:
    return {"named_counterparty": name, "direction": direction,
            "pattern": pattern}


def test_1_default_tickers_are_the_real_verified_anchor_set() -> None:
    check("1a. exactly HYP-04's 7 real anchors, not LOCKED_24_ANCHORS",
          set(DEFAULT_TICKERS) == {"ADBE", "CTSH", "INTC", "JBL", "MCK",
                                    "NKE", "NVDA"}, str(DEFAULT_TICKERS))


def test_2_earliest_selection_per_counterparty_and_direction() -> None:
    h = TickerCompetitorHistory(ticker="ADBE")
    h.per_filing = [
        {"filing_date": "2021-01-15", "accession": "A-2021",
         "disclosures": [_disclosure("Autodesk", "competitor")]},
        {"filing_date": "2014-01-21", "accession": "A-2014",
         "disclosures": [_disclosure("Autodesk", "competitor")]},
        {"filing_date": "2000-02-16", "accession": "A-2000",
         "disclosures": [_disclosure("Macromedia", "competitor")]},
        {"filing_date": "2009-05-05", "accession": "A-2009",
         "disclosures": []},
    ]
    named = h.named_counterparties()

    check("2a. each distinct (counterparty, direction) pair is its own entry",
          set(named) == {"Autodesk|competitor", "Macromedia|competitor"},
          str(sorted(named)))

    rec = named["Autodesk|competitor"]
    check("2b. earliest is the OLDEST filing naming it, not the newest",
          rec["earliest_filing_date"] == "2014-01-21"
          and rec["earliest_accession"] == "A-2014", str(rec))
    check("2c. latest is the newest", rec["latest_filing_date"] == "2021-01-15")
    check("2d. filings_naming_it count is right", rec["filings_naming_it"] == 2)


def test_3_same_name_different_direction_is_a_separate_entry() -> None:
    """A company could plausibly be named as both a competitor in one
    filing and a supplier in another -- these must not collapse into one
    record, since direction is part of what the candidate means."""
    h = TickerCompetitorHistory(ticker="TEST")
    h.per_filing = [
        {"filing_date": "2020-01-01", "accession": "A-1",
         "disclosures": [_disclosure("Acme Corp", "competitor")]},
        {"filing_date": "2021-01-01", "accession": "A-2",
         "disclosures": [_disclosure("Acme Corp", "supplier")]},
    ]
    named = h.named_counterparties()
    check("3a. two distinct entries, one per direction",
          set(named) == {"Acme Corp|competitor", "Acme Corp|supplier"},
          str(sorted(named)))


def test_4_a_renamed_entity_is_not_auto_merged() -> None:
    """Same discipline as run_linkage_history.py's own test_3f: two
    different exact strings for what a human might recognize as the same
    company (e.g. 'IbidenCo' vs 'Ibiden Co. Ltd', both real strings found
    in NVDA's actual filing history) stay separate. Merging is a curator's
    judgement call, never made silently by this code."""
    h = TickerCompetitorHistory(ticker="NVDA")
    h.per_filing = [
        {"filing_date": "2017-03-01", "accession": "A-1",
         "disclosures": [_disclosure("IbidenCo", "supplier")]},
        {"filing_date": "2021-02-26", "accession": "A-2",
         "disclosures": [_disclosure("Ibiden Co. Ltd", "supplier")]},
    ]
    named = h.named_counterparties()
    check("4a. both string variants survive as separate entries",
          set(named) == {"IbidenCo|supplier", "Ibiden Co. Ltd|supplier"},
          str(sorted(named)))


def test_5_empty_history() -> None:
    h = TickerCompetitorHistory(ticker="ZZZ")
    check("5a. no filings -> no counterparties", h.named_counterparties() == {})


def test_6_report_shape() -> None:
    h = TickerCompetitorHistory(ticker="MCK", cik="0000927653")
    h.filings_on_record = 10
    h.filings_examined = 10
    h.per_filing = [
        {"filing_date": "2020-01-01", "accession": "A-1",
         "disclosures": [_disclosure("Foo Inc", "competitor")]},
    ]
    rep = build_report([h], contact_used=True, requests_made=5)
    check("6a. source names the competitor/supplier path, not the ASC 280 "
          "walk's own exact source string",
          "competitor" in rep["source"].lower()
          and "ASC 280 concentration disclosures" not in rep["source"])
    check("6b. status is a candidate review queue, same as every other "
          "extraction source in this repo",
          rep["status"] == "CANDIDATE_REVIEW_QUEUE")
    check("6c. contact_used and requests_made are reported",
          rep["contact_supplied"] is True and rep["requests_made"] == 5)
    check("6d. per-ticker named_counterparties are present in the report",
          rep["tickers"][0]["named_counterparties"][0]["counterparty"]
          == "Foo Inc")


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_default_tickers_are_the_real_verified_anchor_set()
    test_2_earliest_selection_per_counterparty_and_direction()
    test_3_same_name_different_direction_is_a_separate_entry()
    test_4_a_renamed_entity_is_not_auto_merged()
    test_5_empty_history()
    test_6_report_shape()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL COMPETITOR_HISTORY_WALK TESTS PASSED")
    sys.exit(0)
