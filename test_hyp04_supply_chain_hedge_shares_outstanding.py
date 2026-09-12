#!/usr/bin/env python3
"""shares_outstanding.py tests -- HYP-05's point-in-time market-cap input.

Every companyfacts document here is a SYNTHETIC TEST FIXTURE written inline,
shaped like the real SEC API response, never a real pull. Fully offline.
Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_shares_outstanding.py
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

from hyp04_supply_chain_hedge.shares_outstanding import (  # noqa: E402
    SharesOutstandingFact,
    facts_from_companyfacts,
    fetch_shares_outstanding_series,
    shares_outstanding_as_of,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _fact(end: str, filed: str, val: float, form: str = "10-Q", accn: str = "a") -> dict:
    return {"end": end, "filed": filed, "val": val, "form": form, "accn": accn}


def _companyfacts(entries: list[dict], *, taxonomy: str = "dei",
                  tag: str = "EntityCommonStockSharesOutstanding",
                  unit: str = "shares") -> dict:
    return {"facts": {taxonomy: {tag: {"units": {unit: entries}}}}}


def test_1_parses_qualifying_forms_only() -> None:
    doc = _companyfacts([
        _fact("2020-01-31", "2020-02-05", 100.0, form="10-K"),
        _fact("2020-04-30", "2020-05-05", 101.0, form="10-Q"),
        _fact("2020-07-31", "2020-08-05", 102.0, form="10-K/A"),
        _fact("2020-10-31", "2020-11-05", 103.0, form="10-Q/A"),
        _fact("2020-01-31", "2020-02-05", 999.0, form="8-K"),
    ])
    facts = facts_from_companyfacts("ABC", doc)
    check("1a. all four qualifying forms parsed", len(facts) == 4, str(facts))
    check("1b. the 8-K entry is excluded", 999.0 not in [f.shares for f in facts])
    check("1c. ticker is upper-cased", all(f.ticker == "ABC" for f in facts))


def test_2_malformed_or_missing_structure_returns_empty() -> None:
    check("2a. wrong taxonomy returns empty",
          facts_from_companyfacts("ABC", _companyfacts([_fact("2020-01-31", "2020-02-05", 1.0)], taxonomy="us-gaap")) == ())
    check("2b. wrong unit returns empty",
          facts_from_companyfacts("ABC", _companyfacts([_fact("2020-01-31", "2020-02-05", 1.0)], unit="USD")) == ())
    check("2c. completely absent structure returns empty",
          facts_from_companyfacts("ABC", {"facts": {}}) == ())
    check("2d. non-dict document returns empty",
          facts_from_companyfacts("ABC", {}) == ())
    check("2e. entries list containing a non-mapping is skipped, not fatal",
          facts_from_companyfacts("ABC", _companyfacts(["not a dict", _fact("2020-01-31", "2020-02-05", 1.0)])) == (
              SharesOutstandingFact("ABC", 1.0, "2020-01-31", "2020-02-05", "10-Q", "a"),))


def test_3_non_numeric_or_bad_date_entries_skipped() -> None:
    doc = _companyfacts([
        _fact("2020-01-31", "2020-02-05", "not a number"),
        _fact("not-a-date", "2020-02-05", 100.0),
        _fact("2020-01-31", "not-a-date", 100.0),
        _fact("2020-01-31", "2020-02-05", True),   # bool is not a valid count
    ])
    check("3a. every malformed entry skipped", facts_from_companyfacts("ABC", doc) == ())


def test_4_as_of_picks_the_latest_qualifying_fact() -> None:
    facts = (
        SharesOutstandingFact("ABC", 100.0, "2019-12-31", "2020-01-15", "10-K"),
        SharesOutstandingFact("ABC", 105.0, "2020-03-31", "2020-04-15", "10-Q"),
        SharesOutstandingFact("ABC", 110.0, "2020-06-30", "2020-07-15", "10-Q"),
    )
    r = shares_outstanding_as_of(facts, "2020-05-01")
    check("4a. picks the latest fact whose end is <= target",
          r is not None and r.shares == 105.0, str(r))

    r2 = shares_outstanding_as_of(facts, "2019-01-01")
    check("4b. refuses (None) when nothing qualifies -- before any disclosure",
          r2 is None)

    r3 = shares_outstanding_as_of(facts, "2020-12-31")
    check("4c. picks the newest fact when target is after everything",
          r3 is not None and r3.shares == 110.0)


def test_5_the_point_in_time_guarantee_excludes_late_filed_facts() -> None:
    """The core guarantee this module exists for: a fact whose `end` predates
    the target but whose `filed` date is AFTER it must never be used -- that
    value was not yet public knowledge as of the target date."""
    facts = (
        SharesOutstandingFact("ABC", 100.0, "2020-01-01", "2020-06-01", "10-K"),
    )
    r = shares_outstanding_as_of(facts, "2020-03-01")
    check("5a. an early-end/late-filed fact is refused even though `end` "
          "alone would qualify", r is None, str(r))

    r2 = shares_outstanding_as_of(facts, "2020-07-01")
    check("5b. the same fact qualifies once the target is past its filed date",
          r2 is not None and r2.shares == 100.0)


def test_6_as_of_rejects_a_malformed_target_date() -> None:
    facts = (SharesOutstandingFact("ABC", 100.0, "2020-01-01", "2020-01-15", "10-K"),)
    check("6a. malformed target date refuses rather than guessing",
          shares_outstanding_as_of(facts, "not-a-date") is None)
    check("6b. empty facts sequence refuses",
          shares_outstanding_as_of((), "2020-01-01") is None)


class _FakeClient:
    def __init__(self, doc: dict) -> None:
        self._doc = doc
        self.calls: list[str] = []

    def companyfacts(self, cik: str) -> dict:
        self.calls.append(cik)
        return self._doc


def test_7_fetch_series_is_a_thin_wrapper() -> None:
    doc = _companyfacts([_fact("2020-01-31", "2020-02-05", 100.0)])
    client = _FakeClient(doc)
    series = fetch_shares_outstanding_series("ABC", "0000000001", client)
    check("7a. delegates to client.companyfacts with the given CIK",
          client.calls == ["0000000001"])
    check("7b. returns the same parse facts_from_companyfacts would",
          series == facts_from_companyfacts("ABC", doc))


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_parses_qualifying_forms_only()
    test_2_malformed_or_missing_structure_returns_empty()
    test_3_non_numeric_or_bad_date_entries_skipped()
    test_4_as_of_picks_the_latest_qualifying_fact()
    test_5_the_point_in_time_guarantee_excludes_late_filed_facts()
    test_6_as_of_rejects_a_malformed_target_date()
    test_7_fetch_series_is_a_thin_wrapper()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL SHARES_OUTSTANDING TESTS PASSED")
    sys.exit(0)
