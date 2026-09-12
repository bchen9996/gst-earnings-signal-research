#!/usr/bin/env python3
"""point_in_time_market_cap.py tests -- HYP-05's coverage/liquidity input.

Every fixture here is synthetic, written inline. Fully offline. Sockets
blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_point_in_time_market_cap.py
"""
from __future__ import annotations

import socket
import sys
from dataclasses import dataclass
from datetime import date


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.point_in_time_market_cap import (  # noqa: E402
    REASON_MISSING_PRICE,
    REASON_MISSING_SHARES,
    market_cap_as_of,
    price_lookup_from_observations,
)
from hyp04_supply_chain_hedge.shares_outstanding import (  # noqa: E402
    SharesOutstandingFact,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


SHARES = (
    SharesOutstandingFact("ABC", 1_000_000.0, "2020-01-01", "2020-01-15", "10-K"),
)


def _price_lookup(prices: dict) -> callable:
    def _f(ticker, target_date):
        return prices.get((ticker, target_date))
    return _f


def test_1_computes_when_both_sides_succeed() -> None:
    r = market_cap_as_of(
        "ABC", "2020-06-01", shares_series=SHARES,
        price_lookup=_price_lookup({("ABC", "2020-06-01"): 10.0}))
    check("1a. computed is True", r.computed is True)
    check("1b. market cap = price * shares",
          r.market_cap == 10.0 * 1_000_000.0, str(r.market_cap))
    check("1c. no denials", r.denials == ())
    check("1d. as_dict round-trips the key fields",
          r.as_dict()["market_cap"] == r.market_cap
          and r.as_dict()["computed"] is True)


def test_2_missing_shares_denies_with_the_specific_reason() -> None:
    r = market_cap_as_of(
        "ABC", "2019-01-01", shares_series=SHARES,   # before any disclosure
        price_lookup=_price_lookup({("ABC", "2019-01-01"): 10.0}))
    check("2a. computed is False", r.computed is False)
    check("2b. market_cap is None", r.market_cap is None)
    check("2c. denial names the missing-shares reason",
          any(d.startswith(REASON_MISSING_SHARES) for d in r.denials), str(r.denials))
    check("2d. price is still reported even though the result is denied",
          r.price == 10.0)


def test_3_missing_price_denies_with_the_specific_reason() -> None:
    r = market_cap_as_of(
        "ABC", "2020-06-01", shares_series=SHARES,
        price_lookup=_price_lookup({}))   # no price at all
    check("3a. computed is False", r.computed is False)
    check("3b. denial names the missing-price reason",
          any(d.startswith(REASON_MISSING_PRICE) for d in r.denials), str(r.denials))
    check("3c. shares fact is still reported even though the result is denied",
          r.shares is not None and r.shares.shares == 1_000_000.0)


def test_4_both_sides_missing_denies_with_both_reasons() -> None:
    r = market_cap_as_of(
        "ABC", "2019-01-01", shares_series=SHARES,
        price_lookup=_price_lookup({}))
    check("4a. both denial reasons present",
          any(d.startswith(REASON_MISSING_SHARES) for d in r.denials)
          and any(d.startswith(REASON_MISSING_PRICE) for d in r.denials),
          str(r.denials))


def test_5_a_non_positive_or_non_numeric_price_is_rejected_not_used() -> None:
    for bad_price in (0.0, -5.0, "10", True):
        r = market_cap_as_of(
            "ABC", "2020-06-01", shares_series=SHARES,
            price_lookup=_price_lookup({("ABC", "2020-06-01"): bad_price}))
        check(f"5a. price {bad_price!r} is refused, not silently used",
              r.computed is False
              and any(d.startswith(REASON_MISSING_PRICE) for d in r.denials),
              str(r.denials))


@dataclass(frozen=True)
class _Obs:
    ticker: str
    session_date: date
    close: float


def test_6_price_lookup_from_observations_is_exact_date_only() -> None:
    obs = [
        _Obs("ABC", date(2020, 1, 1), 10.0),
        _Obs("ABC", date(2020, 1, 3), 12.0),
    ]
    lookup = price_lookup_from_observations(obs)
    check("6a. exact match returns the close",
          lookup("ABC", "2020-01-01") == 10.0)
    check("6b. exact match, case-insensitive on ticker",
          lookup("abc", "2020-01-03") == 12.0)
    check("6c. no fallback to a nearby date -- 2020-01-02 has no observation",
          lookup("ABC", "2020-01-02") is None)
    check("6d. unknown ticker returns None",
          lookup("XYZ", "2020-01-01") is None)


def test_7_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("7a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("7a. network blocked", True)


if __name__ == "__main__":
    test_1_computes_when_both_sides_succeed()
    test_2_missing_shares_denies_with_the_specific_reason()
    test_3_missing_price_denies_with_the_specific_reason()
    test_4_both_sides_missing_denies_with_both_reasons()
    test_5_a_non_positive_or_non_numeric_price_is_rejected_not_used()
    test_6_price_lookup_from_observations_is_exact_date_only()
    test_7_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL POINT_IN_TIME_MARKET_CAP TESTS PASSED")
    sys.exit(0)
