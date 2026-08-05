#!/usr/bin/env python3
# Deterministic tests for the 2026-08-02 pull_start correction:
# process_ticker() must derive the Wikipedia pull_start (lookback window
# start) from the measured watermark_date, never from wall-clock
# run_ts.date() -- the same class of bug already fixed for the wiki
# z-score anchor itself. No network access, no operational cache access,
# no panel execution: every dependency process_ticker() would otherwise
# call over the network is monkeypatched with a deterministic stub.
#
# Run directly: python test_phase2_wiki_pull_start.py

from __future__ import annotations
import sys
import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_DailyPanel as panel

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


TICKER = "AAPL"  # a real key in TICKER_TO_WIKI_ARTICLE -- required so the
                  # wiki branch is actually reached (article is not None)


class _FakeTicker:
    def __init__(self, ticker, session=None):
        self.ticker = ticker

    def history(self, period=None):
        return pd.DataFrame()  # empty is handled gracefully (price/volume -> None)


def _install_stubs(capture: list):
    """Monkeypatches every network-touching dependency of process_ticker()
    with a fast, deterministic, in-memory stub. Returns a restore() callable.
    `capture` collects the (pull_start, end, watermark) tuple passed to
    wiki_transport.get_ticker_wikipedia_daily on each call."""
    originals = {
        "fetch_days_to_next_earnings": panel.fetch_days_to_next_earnings,
        "get_nearest_post_earnings_expiry": panel.get_nearest_post_earnings_expiry,
        "get_option_snapshot": panel.get_option_snapshot,
        "fetch_ticker_series_scoped_backoff": panel.fetch_ticker_series_scoped_backoff,
        "yf_Ticker": panel.yf.Ticker,
        "wiki_load_cache": panel.wiki_transport.load_cache,
        "wiki_get_daily": panel.wiki_transport.get_ticker_wikipedia_daily,
    }

    panel.fetch_days_to_next_earnings = lambda ticker: 30
    panel.get_nearest_post_earnings_expiry = lambda tk, d: None
    panel.get_option_snapshot = lambda tk, expiry, price: {}
    panel.fetch_ticker_series_scoped_backoff = lambda pt, ticker: (
        pd.DataFrame(),
        {"status": "attempts_exhausted", "attempts": 0, "rate_limit_events": 0, "budget_exhausted": False},
    )
    panel.yf.Ticker = _FakeTicker
    panel.wiki_transport.load_cache = lambda: pd.DataFrame(columns=panel.wiki_transport.CACHE_COLUMNS)

    def _fake_get_ticker_wikipedia_daily(ticker, article, start, end, watermark, cache_df=None,
                                          remaining_budget_s=None, extra_daily_rows=None):
        capture.append({"ticker": ticker, "article": article, "start": start, "end": end,
                         "watermark": watermark})
        daily_rows = list(extra_daily_rows or [])
        return {"chunk_results": [], "failed_chunks": [], "daily_rows": daily_rows}

    panel.wiki_transport.get_ticker_wikipedia_daily = _fake_get_ticker_wikipedia_daily

    def restore():
        panel.fetch_days_to_next_earnings = originals["fetch_days_to_next_earnings"]
        panel.get_nearest_post_earnings_expiry = originals["get_nearest_post_earnings_expiry"]
        panel.get_option_snapshot = originals["get_option_snapshot"]
        panel.fetch_ticker_series_scoped_backoff = originals["fetch_ticker_series_scoped_backoff"]
        panel.yf.Ticker = originals["yf_Ticker"]
        panel.wiki_transport.load_cache = originals["wiki_load_cache"]
        panel.wiki_transport.get_ticker_wikipedia_daily = originals["wiki_get_daily"]

    return restore


def _watermark_info(watermark_date: date, lag_days: int) -> dict:
    return {
        "status": "ok", "watermark_date": watermark_date, "lag_days": lag_days,
        "retrieved_at_utc": "2026-08-01T00:00:00+00:00",
        "source_url": "https://example.org/watermark", "http_status": 200,
    }


def _effective_info(watermark_date: date, tickers=(TICKER,)) -> dict:
    """2026-08-05: the BINDING watermark is now the effective panel
    watermark (min of validated per-article latest-available dates), not
    the aggregate one. These tests model the healthy case where every
    article has published through the aggregate watermark, so the effective
    watermark equals it -- which keeps each test probing the dimension it
    was written for. Divergence between the two is covered in
    test_phase2_wiki_effective_panel_watermark.py."""
    return {
        "status": "ok",
        "effective_panel_watermark_date": watermark_date,
        "method": panel.wiki_transport.EFFECTIVE_WATERMARK_METHOD,
        "aggregate_watermark_date": watermark_date,
        "aggregate_vs_panel_lag_days": 0,
        "per_ticker_latest": {t: watermark_date for t in tickers},
        "measurements": [], "unmeasured": [],
        "measured_count": len(tickers), "expected_count": len(tickers),
        "binding_tickers": sorted(tickers),
        "resolved_at_utc": "2026-08-01T00:00:00+00:00",
    }


# === Tests for watermark lags 0, 1, 2, 3 days ===
def test_pull_start_fixed_relative_to_watermark_across_lags():
    watermark_date = date(2026, 8, 1)
    expected_pull_start = watermark_date - timedelta(days=panel.PULL_LOOKBACK_DAYS)

    captured_pull_starts = []
    captured_ends = []
    for lag in (0, 1, 2, 3):
        wall_clock_today = watermark_date + timedelta(days=lag)
        run_ts = datetime(wall_clock_today.year, wall_clock_today.month, wall_clock_today.day,
                           12, 0, 0, tzinfo=timezone.utc)
        capture = []
        restore = _install_stubs(capture)
        try:
            panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                                  watermark_info=_watermark_info(watermark_date, lag),
                                  effective_info=_effective_info(watermark_date))
        finally:
            restore()
        check(f"lag={lag}d: get_ticker_wikipedia_daily was called exactly once",
              len(capture) == 1, f"got {len(capture)} calls")
        if capture:
            captured_pull_starts.append(capture[0]["start"])
            captured_ends.append(capture[0]["end"])
            check(f"lag={lag}d: pull_start == watermark_date - PULL_LOOKBACK_DAYS (fixed relative to watermark)",
                  capture[0]["start"] == expected_pull_start,
                  f"got {capture[0]['start']!r}, expected {expected_pull_start!r}")
            check(f"lag={lag}d: request end/horizon still reflects wall-clock run_ts.date() (deliberately unchanged)",
                  capture[0]["end"] == wall_clock_today,
                  f"got {capture[0]['end']!r}, expected {wall_clock_today!r}")
            check(f"lag={lag}d: watermark passed through to the transport unchanged",
                  capture[0]["watermark"] == watermark_date)

    check("all 4 lags produced the IDENTICAL pull_start (window boundary fixed relative to watermark, not wall clock)",
          len(set(captured_pull_starts)) == 1, f"distinct values: {set(captured_pull_starts)}")
    check("request end/horizon DID vary with wall-clock across the 4 lags (confirms end-date behavior deliberately untouched)",
          len(set(captured_ends)) == 4, f"distinct values: {set(captured_ends)}")


def test_wall_clock_cannot_change_zscore_when_data_and_watermark_fixed():
    # Same watermark, same (empty) daily_rows in both calls -- only the
    # wall-clock run_ts differs. The resulting row's wiki_zscore must be
    # identical (here: both None, since no daily data was supplied -- the
    # point is that varying wall-clock time alone cannot change the
    # outcome).
    watermark_date = date(2026, 8, 1)
    results = []
    for lag in (0, 3):
        wall_clock_today = watermark_date + timedelta(days=lag)
        run_ts = datetime(wall_clock_today.year, wall_clock_today.month, wall_clock_today.day,
                           12, 0, 0, tzinfo=timezone.utc)
        capture = []
        restore = _install_stubs(capture)
        try:
            row, _ = panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                                           watermark_info=_watermark_info(watermark_date, lag),
                                  effective_info=_effective_info(watermark_date))
        finally:
            restore()
        results.append(row.get("wiki_zscore"))
    check("wiki_zscore identical across wall-clock lag=0d vs lag=3d given fixed watermark/data",
          results[0] == results[1], f"{results!r}")


def test_no_post_watermark_observation_reaches_the_calculation():
    watermark_date = date(2026, 8, 1)
    run_ts = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)

    def _daily(end_date: date, n_days: int) -> list[dict]:
        rows = []
        for i in range(n_days):
            d = end_date - timedelta(days=n_days - 1 - i)
            rows.append({"date": d.strftime("%Y%m%d"), "pageviews": 1000 + (i * 3) % 97})
        return rows

    clean_rows = _daily(watermark_date, 15 * 7)
    poisoned_rows = clean_rows + [
        {"date": (watermark_date + timedelta(days=4)).strftime("%Y%m%d"), "pageviews": 999_999_999},
    ]

    zscores = []
    for rows in (clean_rows, poisoned_rows):
        capture = []
        restore = _install_stubs(capture)
        panel.wiki_transport.get_ticker_wikipedia_daily = (
            lambda ticker, article, start, end, watermark, cache_df=None, remaining_budget_s=None, _r=rows:
            (capture.append({"ticker": ticker, "start": start, "end": end, "watermark": watermark})
             or {"chunk_results": [], "failed_chunks": [], "daily_rows": _r})
        )
        try:
            row, _ = panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                                           watermark_info=_watermark_info(watermark_date, 1),
                                  effective_info=_effective_info(watermark_date))
        finally:
            restore()
        zscores.append(row.get("wiki_zscore"))

    check("a post-watermark observation reaching process_ticker's wiki leg has zero effect on wiki_zscore",
          zscores[0] == zscores[1], f"{zscores!r}")


def test_missing_watermark_fails_closed():
    run_ts = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    capture = []
    restore = _install_stubs(capture)
    try:
        row, _ = panel.process_ticker(
            None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
            watermark_info={"status": "no_data_within_max_lag", "watermark_date": None,
                             "lag_days": None, "retrieved_at_utc": None, "source_url": None,
                             "http_status": None},
        )
    finally:
        restore()
    check("a missing/errored watermark: get_ticker_wikipedia_daily is never called (no network attempt)",
          len(capture) == 0, f"got {len(capture)} calls")
    check("a missing/errored watermark: row.wiki_status == 'incomplete_watermark_unavailable'",
          row.get("wiki_status") == "incomplete_watermark_unavailable", f"got {row.get('wiki_status')!r}")
    check("a missing/errored watermark: row.wiki_zscore stays None (never computed)",
          row.get("wiki_zscore") is None)


if __name__ == "__main__":
    test_pull_start_fixed_relative_to_watermark_across_lags()
    test_wall_clock_cannot_change_zscore_when_data_and_watermark_fixed()
    test_no_post_watermark_observation_reaches_the_calculation()
    test_missing_watermark_fails_closed()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL PULL_START/WATERMARK TESTS PASSED")
        sys.exit(0)
