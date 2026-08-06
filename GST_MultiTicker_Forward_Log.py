#!/usr/bin/env python3
# MULTI-TICKER FORWARD LOG — expands the MSFT-only forward quote logger
# (GST_MSFT_Forward_Quote_Log.py) to the 29-ticker canonical
# STRONG_EARNINGS universe (the 27 tickers with qualifying events in
# FixedWindow_PerEvent_Canonical.csv, plus MCHP and EBAY -- both part of
# the same candidate universe with zero qualifying events to date).
#
# PURPOSE: this project's forensic point-in-time audit found that every
# HISTORICAL GST z-score in this project was computed via a RETROSPECTIVE
# pytrends query (today, for a window ending years ago) -- which is
# reproducible but NOT provably identical to what a live observer would
# have seen in real time, since Google Trends' recent/provisional data can
# be revised. This log has no such ambiguity: every value is captured
# the moment it's observable, going forward, with the exact retrieval
# timestamp and exact query window recorded alongside it. This is the
# genuinely point-in-time-clean dataset the audit called for.
#
# Runs once per trading day (scheduled via GitHub Actions, see
# .github/workflows/). Resilient to being triggered any time in the
# 3:00-4:00pm ET window, same as the MSFT logger. For EVERY ticker, every
# run, records:
#   - raw GST value, retrieval timestamp, EXACT query start/end date window
#   - calculated z-score (same compute_latest_zscore() the live engine uses)
#   - underlying stock price
#   - days to next earnings
# For any ticker within EARNINGS_WINDOW_DAYS=5 days of earnings, ALSO
# records the full real option chain snapshot (ATM call+put: strike,
# bid/ask, bid/ask size, open interest, volume, quoted impliedVolatility)
# -- identical methodology to the MSFT logger, generalized to any ticker/
# earnings date instead of the hardcoded MSFT/2026-07-29 case.
#
# Output: Live Signal Engine/MultiTicker_Forward_Log.csv (append-only,
# one row per ticker per run)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
import random
import sys
import time
import pandas as pd
import requests
import urllib3
import yfinance as yf
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from GST_Live_Signal_Engine import (
    fetch_ticker_series, compute_latest_zscore, fetch_days_to_next_earnings,
    base_tier, PULL_LOOKBACK_DAYS, EARNINGS_WINDOW_DAYS,
)

# 29 tickers: the 27 with a qualifying canonical event in
# FixedWindow_PerEvent_Canonical.csv, plus MCHP and EBAY -- both part of
# the original candidate universe (TICKERS_ORIGINAL / TICKERS_BROAD50_CLEAR
# in GST_FixedWindow_PerEvent_Canonical.py) with zero qualifying events to
# date, included here for completeness/future-proofing rather than
# dropped. Not the full TICKERS_ORIGINAL+TICKERS_BROAD50_CLEAR set (51
# tickers) -- this is the curated subset actually worth watching daily.
TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
    "ABBV", "BKR", "BRK-B", "COHR", "CTSH", "DELL", "DVN", "GPN", "LDOS",
    "MCHP", "NCLH", "STZ", "SYK", "UAL",
]

OUT_PATH = Path("Live Signal Engine") / "MultiTicker_Forward_Log.csv"
ET_ZONE = ZoneInfo("America/New_York")
TARGET_WINDOW_START, TARGET_WINDOW_END = 15, 16   # 3:00pm-4:00pm ET

RUN_LOG_START_DATE = date(2026, 7, 20)   # this pipeline's own logging start -- no gap check before this

BETWEEN_TICKERS = (1.5, 3.0)
MICRO_BATCH_SIZE = 6
MICRO_BATCH_PAUSE_S = 20

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


# Option-chain helpers moved to GST_Option_Chain_Core.py (2026-08-06) and
# re-exported here, unchanged, so every existing call site --
# GST_MultiTicker_Forward_Log.get_nearest_post_earnings_expiry(...) and
# .get_option_snapshot(...) -- keeps working with no change.
#
# They were extracted because this module is a live execution entry point: it
# imports pytrends and the live GST signal engine at module scope, so anything
# that wanted only these two option helpers was forced to load Google Trends
# and the whole legacy runtime too. The core module carries the single
# implementation; nothing is redefined below.
from GST_Option_Chain_Core import (  # noqa: E402  (path setup above must precede this import)
    get_nearest_post_earnings_expiry,
    get_option_snapshot,
)


def trading_days_between(start_exclusive: date, end_exclusive: date) -> list[date]:
    """Mon-Fri calendar days strictly between the two dates. No US market-holiday
    calendar lookup -- disclosed simplification, same as the MSFT logger."""
    days = []
    d = start_exclusive + timedelta(days=1)
    while d < end_exclusive:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def find_gap_days(today_et: date) -> list[date]:
    """Any Mon-Fri day between this pipeline's logging start and today, strictly
    before today, with no recorded entry for ANY ticker at all (a fully-skipped run)."""
    if not OUT_PATH.exists():
        return []
    existing = pd.read_csv(OUT_PATH)
    if "run_date_et" not in existing.columns or existing.empty:
        return []
    recorded_dates = set(pd.to_datetime(existing["run_date_et"], errors="coerce").dt.date.dropna())
    candidates = trading_days_between(RUN_LOG_START_DATE - timedelta(days=1), today_et)
    return [d for d in candidates if d not in recorded_dates]


def fetch_next_earnings_date(ticker: str) -> date | None:
    """Same yf.Ticker.get_earnings_dates() source as fetch_days_to_next_earnings,
    returning the actual date (needed for option-expiry selection) instead of
    just the day count."""
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        df = tk.get_earnings_dates(limit=12)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    today = datetime.now(timezone.utc).date()
    try:
        future = sorted(d.date() for d in pd.to_datetime(df.index).tz_localize(None).normalize()
                         if d.date() >= today)
    except Exception:
        return None
    return future[0] if future else None


def process_ticker(pt: TrendReq, ticker: str, run_ts_utc: datetime) -> dict:
    row = {"ticker": ticker, "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat()}

    # Earnings date/day-count MUST run before any yfinance options/history calls
    # for this ticker -- see the one-directional yfinance internal-state quirk
    # documented in GST_MSFT_Forward_Quote_Log.py. Order matters, don't reshuffle.
    earnings_date = fetch_next_earnings_date(ticker)
    days_to_earnings = (earnings_date - run_ts_utc.date()).days if earnings_date else None
    row["next_earnings_date"] = earnings_date.isoformat() if earnings_date else None
    row["days_to_next_earnings"] = days_to_earnings
    within_earnings_window = days_to_earnings is not None and 0 <= days_to_earnings <= EARNINGS_WINDOW_DAYS
    row["within_earnings_window"] = within_earnings_window

    tk = yf.Ticker(ticker, session=YF_SESSION)

    # --- underlying price ---
    spot = None
    try:
        fi = tk.fast_info
        row["underlying_bid"] = fi.get("bid")
        row["underlying_ask"] = fi.get("ask")
        row["underlying_last"] = fi.get("last_price")
        spot = fi.get("last_price")
    except Exception as e:
        row["underlying_quote_error"] = str(e)
    if not spot:
        b, a = row.get("underlying_bid"), row.get("underlying_ask")
        if b and a:
            spot = (b + a) / 2
    if not spot:
        try:
            hist = tk.history(period="1d")
            spot = float(hist["Close"].iloc[-1]) if not hist.empty else None
        except Exception:
            spot = None
    row["underlying_price"] = spot

    # --- option chain, ONLY if within the earnings window ---
    if within_earnings_window:
        expiry = get_nearest_post_earnings_expiry(tk, earnings_date)
        row["nearest_post_earnings_expiry"] = expiry
        if expiry and spot:
            row["days_to_expiry"] = (datetime.strptime(expiry, "%Y-%m-%d").date() - run_ts_utc.date()).days
            row.update(get_option_snapshot(tk, expiry, spot))
        else:
            row["options_note"] = f"no expiry or spot available (expiry={expiry}, spot={spot})"

    # --- GST z-score: exact same functions the live engine uses ---
    gst_query_end = datetime.now(timezone.utc).date()
    gst_query_start = gst_query_end - timedelta(days=PULL_LOOKBACK_DAYS)
    row["gst_query_start_date"] = gst_query_start.isoformat()
    row["gst_query_end_date"] = gst_query_end.isoformat()
    try:
        series = fetch_ticker_series(pt, ticker)
        z = compute_latest_zscore(series)
        row["gst_zscore"] = z.get("zscore")
        row["gst_week"] = z.get("week")
        row["gst_value"] = z.get("gst_value")
        row["gst_is_partial_week"] = z.get("is_partial_week")
        row["gst_note"] = z.get("note", "")
        row["gst_tier"] = base_tier(z.get("zscore"))
    except Exception as e:
        row["gst_error"] = str(e)

    return row


def main():
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET_ZONE)
    today_et = now_et.date()

    print(f"*** MULTI-TICKER FORWARD LOG — run at {now_utc.isoformat()} "
          f"({now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}) — {len(TICKERS)} tickers ***\n")

    within_window = TARGET_WINDOW_START <= now_et.hour < TARGET_WINDOW_END
    if not within_window:
        print(f"*** NOTE: run time {now_et.strftime('%H:%M %Z')} is OUTSIDE the 3:00-4:00pm ET "
              f"target window -- recording anyway, flagged in every row. ***\n")

    gap_days = find_gap_days(today_et)
    if gap_days:
        gap_str = ", ".join(d.isoformat() for d in gap_days)
        print(f"*** GAP DETECTED: no entries found for {len(gap_days)} prior trading day(s): {gap_str} ***\n")
    else:
        print(f"No gap: all prior trading days since {RUN_LOG_START_DATE.isoformat()} have entries "
              f"(or this is the first run).\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    rows = []
    for i, ticker in enumerate(TICKERS, start=1):
        row = process_ticker(pt, ticker, now_utc)
        row.update({
            "run_timestamp_utc": now_utc.isoformat(),
            "run_timestamp_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "run_date_et": today_et.isoformat(),
            "within_3_4pm_et_window": within_window,
            "missing_trading_days_since_last_entry": "; ".join(d.isoformat() for d in gap_days) if gap_days else "",
        })
        rows.append(row)
        flag = row.get("gst_tier") or "-"
        earn_flag = "EARNINGS-WINDOW" if row.get("within_earnings_window") else ""
        print(f"[{i}/{len(TICKERS)}] {ticker}: gst_z={row.get('gst_zscore')} {flag} "
              f"days_to_earnings={row.get('days_to_next_earnings')} {earn_flag}")

        time.sleep(random.uniform(*BETWEEN_TICKERS))
        if i % MICRO_BATCH_SIZE == 0 and i != len(TICKERS):
            print(f"— small batch pause ({MICRO_BATCH_PAUSE_S}s) —")
            time.sleep(MICRO_BATCH_PAUSE_S)

    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        df.to_csv(OUT_PATH, mode="a", header=False, index=False)
    else:
        df.to_csv(OUT_PATH, mode="w", header=True, index=False)

    n_earnings_window = df["within_earnings_window"].sum()
    print(f"\n{len(df)} tickers recorded. {n_earnings_window} within the earnings window "
          f"(full option chain captured for those).")
    print(f"Appended to: {OUT_PATH}")


if __name__ == "__main__":
    main()
