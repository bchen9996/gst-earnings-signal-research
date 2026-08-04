#!/usr/bin/env python3
# SECTION C deterministic tests: the authoritative XNYS exchange_calendars
# wrapper. No live network -- exchange_calendars ships its own bundled
# calendar data.
#
# Run directly: python test_market_response_exchange_calendar.py

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.exchange_calendar import (
    ExchangeCalendarError,
    compute_expected_next_full_trading_session_xnys,
    expected_bar_boundaries,
    is_early_close,
    is_trading_day,
    next_session,
    previous_session,
    session_close_utc,
    session_open_utc,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def test_ordinary_session():
    d = date(2026, 8, 3)  # ordinary Monday
    check("1a. Ordinary Monday is a trading session", is_trading_day(d))
    check("1b. Ordinary session open is 09:30 ET (13:30 UTC in EDT)", session_open_utc(d).isoformat() == "2026-08-03T13:30:00+00:00")
    check("1c. Ordinary session close is 16:00 ET (20:00 UTC in EDT)", session_close_utc(d).isoformat() == "2026-08-03T20:00:00+00:00")
    check("1d. Ordinary session is not an early close", not is_early_close(d))


def test_weekend():
    saturday = date(2026, 8, 8)
    sunday = date(2026, 8, 9)
    check("2a. Saturday is not a trading session", not is_trading_day(saturday))
    check("2b. Sunday is not a trading session", not is_trading_day(sunday))
    check("2c. next_session from a Saturday resolves to the following Monday", next_session(saturday) == date(2026, 8, 10))


def test_full_holiday():
    check("3a. Thanksgiving 2026-11-26 is not a trading session", not is_trading_day(date(2026, 11, 26)))
    check("3b. Christmas 2026-12-25 is not a trading session", not is_trading_day(date(2026, 12, 25)))
    check("3c. New Year's Day 2026-01-01 is not a trading session", not is_trading_day(date(2026, 1, 1)))


def test_early_close():
    d = date(2026, 11, 27)  # day after Thanksgiving
    check("4a. Day after Thanksgiving IS a trading session", is_trading_day(d))
    check("4b. Day after Thanksgiving is flagged as an early close", is_early_close(d))
    check("4c. Early-close session closes before 16:00 ET", session_close_utc(d).isoformat() == "2026-11-27T18:00:00+00:00")
    boundaries = expected_bar_boundaries(d)
    # 09:30-13:00 ET (post-DST-fallback EST) = 3.5h = 210min / 5min = 42 bars.
    check("4d. Early-close expected bar count is shrunk correctly (210min / 5min = 42)", boundaries.expected_bar_count == 42, str(boundaries.expected_bar_count))
    check("4e. Early-close last bar start is 5 min before the actual (early) close", boundaries.last_bar_start_utc == "2026-11-27T17:55:00+00:00")


def test_dst_transition():
    # 2026-03-08 is the US spring-forward Sunday; 2026-03-09 is the first
    # EDT trading session.
    pre_dst = date(2026, 3, 6)  # Friday, still EST (UTC-5)
    post_dst = date(2026, 3, 9)  # Monday, now EDT (UTC-4)
    check("5a. Pre-DST session opens at 14:30 UTC (09:30 EST)", session_open_utc(pre_dst).isoformat() == "2026-03-06T14:30:00+00:00")
    check("5b. Post-DST session opens at 13:30 UTC (09:30 EDT) -- one hour earlier in UTC", session_open_utc(post_dst).isoformat() == "2026-03-09T13:30:00+00:00")

    # 2026-11-01 is the US fall-back Sunday; 2026-11-02 is the first EST session.
    pre_fallback = date(2026, 10, 30)  # Friday, still EDT
    post_fallback = date(2026, 11, 2)  # Monday, now EST
    check("5c. Pre-fallback session opens at 13:30 UTC (EDT)", session_open_utc(pre_fallback).isoformat() == "2026-10-30T13:30:00+00:00")
    check("5d. Post-fallback session opens at 14:30 UTC (EST) -- one hour later in UTC", session_open_utc(post_fallback).isoformat() == "2026-11-02T14:30:00+00:00")


def test_amc_event():
    # AMC always maps to the next session, whether or not earnings_date
    # itself was a trading day.
    result_trading_day = compute_expected_next_full_trading_session_xnys(date(2026, 8, 3), "AMC")
    check("6a. AMC on an ordinary trading day maps to the NEXT session, not the same day", result_trading_day == date(2026, 8, 4))
    result_weekend = compute_expected_next_full_trading_session_xnys(date(2026, 10, 30), "AMC")  # Friday
    check("6b. AMC on a Friday maps to the following Monday", result_weekend == date(2026, 11, 2))


def test_bmo_event():
    result_trading_day = compute_expected_next_full_trading_session_xnys(date(2026, 10, 27), "BMO")  # Tuesday
    check("7a. BMO on an ordinary trading day maps to that SAME day", result_trading_day == date(2026, 10, 27))
    result_holiday = compute_expected_next_full_trading_session_xnys(date(2026, 11, 26), "BMO")  # Thanksgiving
    check("7b. BMO on a holiday rolls forward to the next real session", result_holiday == date(2026, 11, 27))


def test_intraday_release():
    # INTRADAY always maps to the next FULL session, same rule as AMC in
    # this calendar's day-count logic (the interrupted current session is
    # excluded from D1 regardless of calendar backend).
    result = compute_expected_next_full_trading_session_xnys(date(2026, 8, 3), "INTRADAY")
    check("8. INTRADAY release maps to the next full session, never same-day", result == date(2026, 8, 4))


def test_exact_first_last_bar():
    d = date(2026, 8, 3)
    boundaries = expected_bar_boundaries(d)
    check("9a. First expected bar starts exactly at session open", boundaries.first_bar_start_utc == boundaries.open_utc)
    check("9b. Last expected bar starts exactly 5 minutes before session close", boundaries.last_bar_start_utc == "2026-08-03T19:55:00+00:00")
    check("9c. Ordinary session expected bar count is 78 (6.5h * 60 / 5)", boundaries.expected_bar_count == 78)


def test_no_after_hours_contamination():
    # The calendar's own session_open/session_close ARE the regular-session
    # boundaries (exchange_calendars' XNYS session times are regular-hours
    # by definition, excluding pre/post-market) -- confirm the window width
    # matches the known 6.5-hour regular session, not an extended one.
    d = date(2026, 8, 3)
    width_minutes = (session_close_utc(d) - session_open_utc(d)).total_seconds() / 60
    check("10. Regular session window is exactly 390 minutes (6.5h), not extended to include pre/post-market", width_minutes == 390.0, str(width_minutes))


def test_calendar_error_on_nonsession():
    try:
        session_open_utc(date(2026, 8, 8))  # a Saturday
        ok = False
    except ExchangeCalendarError:
        ok = True
    check("11. Requesting open/close for a non-session date raises rather than returning a guess", ok)


if __name__ == "__main__":
    test_ordinary_session()
    test_weekend()
    test_full_holiday()
    test_early_close()
    test_dst_transition()
    test_amc_event()
    test_bmo_event()
    test_intraday_release()
    test_exact_first_last_bar()
    test_no_after_hours_contamination()
    test_calendar_error_on_nonsession()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL EXCHANGE CALENDAR TESTS PASSED")
        sys.exit(0)
