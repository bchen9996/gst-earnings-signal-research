#!/usr/bin/env python3
# MSFT FORWARD QUOTE LOG — new daily snapshot recorder, unrelated to the
# look-ahead bias audit or the 148-event reconciliation work. Records
# real, live data going FORWARD from today through 2026-07-30, ahead of
# the 2026-07-22 signal check and the 2026-07-29 earnings date, so there
# is a genuine point-in-time record to compare against after the fact --
# nothing here is a recompute or backtest of prior history.
#
# Intended to run once per trading day, ANY TIME between 3:00-4:00pm ET
# (resilient to a late/imprecise trigger rather than requiring an exact
# fixed timestamp) -- scheduled separately from this script itself.
# Appends ONE row per run to Live Signal Engine/MSFT_Forward_Quote_Log.csv,
# creating the file with a header on first run. Runs and records every
# day regardless of whether a signal fires that day. Logs the ACTUAL
# run time (both UTC and US/Eastern, DST-aware via zoneinfo) and flags
# if the run fell outside the 3:00-4:00pm ET target window, or if a
# prior trading day has no entry at all (a gap), so both are visible in
# the file itself rather than silently missing.
#
# Records:
#   - timestamp
#   - MSFT underlying bid/ask (and last price / spot used for ATM selection)
#   - nearest LISTED expiry after the 2026-07-29 earnings date
#   - ATM call + put: strike, bid/ask, bid/ask size, open interest, volume,
#     impliedVolatility (this is REAL quoted market IV from the option
#     chain -- notably different from every other IV figure in this
#     project, which has always been a realized-vol-based model proxy,
#     disclosed repeatedly elsewhere. This log captures the real thing.)
#   - GST z-score for MSFT, via fetch_ticker_series() + compute_latest_zscore()
#     IMPORTED DIRECTLY from GST_Live_Signal_Engine.py (not reimplemented),
#     so this log's z-score is exactly what the live engine would show,
#     including the STD_EPSILON_FLOOR fix already baked into that function.
#
# Output: Live Signal Engine/MSFT_Forward_Quote_Log.csv (append-only)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
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
    fetch_ticker_series, compute_latest_zscore, fetch_days_to_next_earnings, base_tier,
)

TICKER = "MSFT"
OUT_PATH = Path("Live Signal Engine") / "MSFT_Forward_Quote_Log.csv"
EARNINGS_DATE = date(2026, 7, 29)   # disclosed assumption, matches STRATEGY_SPEC_v1.0's target trade
ET_ZONE = ZoneInfo("America/New_York")
TARGET_WINDOW_START, TARGET_WINDOW_END = 15, 16   # 3:00pm-4:00pm ET, as (hour, hour)

RUN_LOG_START_DATE = date(2026, 7, 18)   # this script's own logging start -- no gap check before this

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def get_nearest_post_earnings_expiry(tk: yf.Ticker) -> str | None:
    try:
        expirations = tk.options
    except Exception:
        return None
    if not expirations:
        return None
    candidates = [e for e in expirations if datetime.strptime(e, "%Y-%m-%d").date() > EARNINGS_DATE]
    return min(candidates) if candidates else None


def get_option_snapshot(tk: yf.Ticker, expiry: str, spot: float) -> dict:
    result = {}
    try:
        chain = tk.option_chain(expiry)
    except Exception as e:
        result["option_chain_error"] = str(e)
        return result
    for label, chain_df in [("call", chain.calls), ("put", chain.puts)]:
        if chain_df.empty:
            continue
        idx = (chain_df["strike"] - spot).abs().idxmin()
        row = chain_df.loc[idx]
        result[f"{label}_strike"] = float(row["strike"])
        result[f"{label}_bid"] = float(row["bid"]) if pd.notna(row.get("bid")) else None
        result[f"{label}_ask"] = float(row["ask"]) if pd.notna(row.get("ask")) else None
        result[f"{label}_bid_size"] = int(row["bidSize"]) if pd.notna(row.get("bidSize")) else None
        result[f"{label}_ask_size"] = int(row["askSize"]) if pd.notna(row.get("askSize")) else None
        result[f"{label}_open_interest"] = int(row["openInterest"]) if pd.notna(row.get("openInterest")) else None
        result[f"{label}_volume"] = int(row["volume"]) if pd.notna(row.get("volume")) else None
        result[f"{label}_implied_volatility"] = float(row["impliedVolatility"]) if pd.notna(row.get("impliedVolatility")) else None
    return result


def trading_days_between(start_exclusive: date, end_exclusive: date) -> list[date]:
    """Mon-Fri calendar days strictly between the two dates. No US market-holiday
    calendar lookup -- disclosed simplification, fine for the 2026-07-18 to
    2026-07-30 window this script covers (no market holidays fall in that range)."""
    days = []
    d = start_exclusive + timedelta(days=1)
    while d < end_exclusive:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def find_gap_days(today_et: date) -> list[date]:
    """Any Mon-Fri day between this script's logging start and today, strictly
    before today, that has no recorded entry at all."""
    if not OUT_PATH.exists():
        return []   # first-ever run -- nothing to compare against yet
    existing = pd.read_csv(OUT_PATH)
    if "run_date_et" not in existing.columns or existing.empty:
        return []
    recorded_dates = set(pd.to_datetime(existing["run_date_et"], errors="coerce").dt.date.dropna())
    candidates = trading_days_between(RUN_LOG_START_DATE - timedelta(days=1), today_et)
    return [d for d in candidates if d not in recorded_dates]


def main():
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET_ZONE)
    today_et = now_et.date()

    print(f"*** MSFT FORWARD QUOTE LOG — snapshot at {now_utc.isoformat()} "
          f"({now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}) ***\n")

    within_window = TARGET_WINDOW_START <= now_et.hour < TARGET_WINDOW_END
    if not within_window:
        print(f"*** NOTE: run time {now_et.strftime('%H:%M %Z')} is OUTSIDE the 3:00-4:00pm ET "
              f"target window -- recording anyway, flagged in this row. ***\n")

    gap_days = find_gap_days(today_et)
    if gap_days:
        gap_str = ", ".join(d.isoformat() for d in gap_days)
        print(f"*** GAP DETECTED: no entry found for {len(gap_days)} prior trading day(s): {gap_str} ***\n")
    else:
        print("No gap: all prior trading days since 2026-07-18 have an entry (or this is the first run).\n")

    row = {
        "timestamp_utc": now_utc.isoformat(),
        "run_timestamp_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "run_date_et": today_et.isoformat(),
        "within_3_4pm_et_window": within_window,
        "missing_trading_days_since_last_entry": "; ".join(d.isoformat() for d in gap_days) if gap_days else "",
        "ticker": TICKER,
    }

    # --- days to next earnings: MUST run before any tk.options/tk.option_chain/tk.history/
    # tk.fast_info calls below. Confirmed empirically (2026-07-18) that yfinance's internal
    # per-ticker state gets left in a state where get_earnings_dates() silently fails (returns
    # None) if an options-chain call for the SAME ticker symbol has already happened earlier in
    # the same process -- a one-directional yfinance quirk, not a rate limit (retrying with
    # backoff did not help; calling earnings first does). Order matters here, don't reshuffle.
    days_to_earnings = None
    for attempt, wait_s in enumerate([0, 5, 15], start=1):
        if wait_s:
            time.sleep(wait_s)
        days_to_earnings = fetch_days_to_next_earnings(TICKER)
        if days_to_earnings is not None:
            break
        print(f"  days_to_next_earnings attempt {attempt} returned None")
    row["days_to_next_earnings"] = days_to_earnings

    tk = yf.Ticker(TICKER, session=YF_SESSION)

    # --- underlying quote ---
    try:
        fi = tk.fast_info
        row["underlying_bid"] = fi.get("bid")
        row["underlying_ask"] = fi.get("ask")
        row["underlying_last"] = fi.get("last_price")
    except Exception as e:
        row["underlying_quote_error"] = str(e)

    spot = row.get("underlying_last")
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
    row["spot_used_for_atm"] = spot

    # --- options: nearest listed expiry after earnings ---
    expiry = get_nearest_post_earnings_expiry(tk)
    row["nearest_post_earnings_expiry"] = expiry
    if expiry and spot:
        row["days_to_expiry"] = (datetime.strptime(expiry, "%Y-%m-%d").date() - date.today()).days
        row.update(get_option_snapshot(tk, expiry, spot))
    else:
        row["options_note"] = f"no expiry or spot available (expiry={expiry}, spot={spot})"

    # --- GST z-score: SAME functions the live engine itself uses, imported not reimplemented ---
    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})
        series = fetch_ticker_series(pt, TICKER)
        z = compute_latest_zscore(series)
        row["gst_zscore"] = z.get("zscore")
        row["gst_week"] = z.get("week")
        row["gst_value"] = z.get("gst_value")
        row["gst_is_partial_week"] = z.get("is_partial_week")
        row["gst_note"] = z.get("note")
        row["gst_tier"] = base_tier(z.get("zscore"))
    except Exception as e:
        row["gst_error"] = str(e)

    print("Snapshot:")
    for k, v in row.items():
        print(f"  {k}: {v}")

    df_row = pd.DataFrame([row])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        df_row.to_csv(OUT_PATH, mode="a", header=False, index=False)
    else:
        df_row.to_csv(OUT_PATH, mode="w", header=True, index=False)
    print(f"\nAppended to: {OUT_PATH}")


if __name__ == "__main__":
    main()
