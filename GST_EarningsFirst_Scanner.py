#!/usr/bin/env python3
# GST EARNINGS-FIRST SCANNER — daily priority scan, replacing the
# random-batch-of-50 rotation as the PRIMARY daily coverage mechanism
# (the batch rotation in GST_Live_Signal_Engine.py is unchanged and kept
# running in parallel as a full-universe fallback -- see header there).
#
# PROBLEM THIS FIXES: under pure batch-of-50 rotation (9 batches, one
# run every few days), a ticker reporting earnings TOMORROW could sit
# unscanned for days if its batch isn't due yet -- the exact z>=5-near-
# earnings window this whole project's edge depends on could be missed
# purely due to batch timing, not signal absence.
#
# WHAT THIS SCRIPT DOES, each run:
#   1. EARNINGS-WINDOW IDENTIFICATION (yfinance, cheap, all 425 tickers):
#      for every ticker in the universe, fetch its next earnings date
#      (same yf.Ticker.get_earnings_dates() source used everywhere else
#      in this project -- GST_Live_Signal_Engine.fetch_days_to_next_earnings
#      and GST_MSFT_Forward_Quote_Log.py both call the identical endpoint).
#      A ticker is in the PRIORITY set if its earnings date is within the
#      next 5 TRADING days (Mon-Fri, via numpy.busday_count -- no market-
#      holiday calendar is used anywhere else in this project either, so
#      none is introduced here; a small, disclosed approximation).
#   2. GST Z-SCORE SCAN (pytrends, rate-limited, the expensive step) runs
#      ONLY on: the priority set (guaranteed coverage, regardless of where
#      these tickers would have fallen in the batch rotation) + a smaller
#      random CONTROL_SAMPLE_SIZE non-earnings sample (baseline coverage,
#      so the signal's behavior on non-earnings-adjacent tickers is still
#      observed daily, not just inferred from priority-ticker absence).
#   3. EVERY scanned ticker is logged -- hits and non-hits alike -- exactly
#      like the existing batch rotation's watchlist_log.csv (point-in-time
#      discipline: append-only, never rewritten).
#
# *** TRADING-DAY WINDOW vs. THE VALIDATED CALENDAR-DAY TIER RULE --
# THESE ARE DELIBERATELY DIFFERENT, NOT AN INCONSISTENCY ***
# "Within 5 trading days" here is a SCAN-PRIORITIZATION gate only -- it
# decides which tickers get checked today, not whether a signal counts as
# STRONG_EARNINGS. The actual STRONG_EARNENGS tier classification below
# reuses GST_Live_Signal_Engine's EXACT existing rule unchanged: z>=5 AND
# an earnings date within EARNINGS_WINDOW_DAYS=5 CALENDAR days (the
# validated, frozen definition -- STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md).
# Changing that definition to trading days would be a real rule change,
# out of scope here and not done. The two windows will usually agree, but
# can diverge slightly near weekends (5 trading days can span 7-9 calendar
# days) -- this is why control-sample tickers still get their OWN fresh
# calendar-day earnings check if they clear z>=5, exactly as the existing
# engine already does for every STRONG hit, rather than assuming
# "not in the trading-day priority set" implies "not near-earnings" for
# tier-classification purposes.
#
# Output:
#   Live Signal Engine/earningsfirst_<RUN_TIMESTAMP>.csv   (this run's snapshot)
#   Live Signal Engine/earningsfirst_log.csv                (append-only running log)
#   Live Signal Engine/earningsfirst_latest.csv             (convenience copy, this run only)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import random
import sys
import time
import numpy as np
import pandas as pd
import yfinance as yf

import GST_Live_Signal_Engine as engine

sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRADING_DAY_WINDOW = 5          # priority-scan gate (trading days) -- see header note
CONTROL_SAMPLE_SIZE = 25        # non-earnings baseline coverage sample size
EARNINGS_LOOKUP_PAUSE_S = 0.5   # polite pacing between the 425 yfinance earnings-date calls


def fetch_next_earnings_date(ticker: str):
    """Same yf.Ticker.get_earnings_dates() source as engine.fetch_days_to_next_earnings,
    but returns the actual next earnings date (needed for trading-day math here) instead
    of just the calendar-day count."""
    try:
        tk = yf.Ticker(ticker, session=engine.EARNINGS_SESSION)
        df = tk.get_earnings_dates(limit=engine.EARNINGS_PULL_LIMIT)
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


def trading_days_out(today, target_date) -> int:
    return int(np.busday_count(today, target_date))


def scan_one_ticker(pt, ticker: str, scan_source: str, run_ts: datetime,
                     known_days_to_earnings_calendar: int | None) -> dict:
    series = engine.fetch_ticker_series(pt, ticker)
    ambiguous = engine.is_ambiguous(ticker)

    if series.empty:
        return {
            "ticker": ticker, "run_timestamp": run_ts.isoformat(), "scan_source": scan_source,
            "week": None, "gst_value": None, "is_partial_week": None, "zscore": None,
            "is_spike": False, "signal_tier": None, "days_to_earnings": known_days_to_earnings_calendar,
            "ambiguous_symbol": ambiguous, "eligible_for_options_leg": False,
            "note": "GST pull failed/empty",
        }

    z = engine.compute_latest_zscore(series)
    tier = engine.base_tier(z.get("zscore"))

    days_to_earnings = known_days_to_earnings_calendar
    if tier == "STRONG":
        if days_to_earnings is None:
            # control-sample ticker clearing z>=5: same fresh calendar-day check
            # the existing batch rotation already does for every STRONG hit.
            days_to_earnings = engine.fetch_days_to_next_earnings(ticker)
        if days_to_earnings is not None and 0 <= days_to_earnings <= engine.EARNINGS_WINDOW_DAYS:
            # Same HIGH_CONFIDENCE_STRONG_EARNINGS split as the batch engine
            # (see GST_Live_Signal_Engine.py's SIGNAL-TIERING ENHANCEMENT note
            # and CHANGELOG.md, 2026-07-19) -- a classification layer only,
            # no change to the z-score or earnings-window logic itself.
            zscore = z.get("zscore")
            if zscore is not None and zscore >= engine.HIGH_CONFIDENCE_Z_THRESHOLD:
                tier = "HIGH_CONFIDENCE_STRONG_EARNINGS"
            else:
                tier = "STRONG_EARNINGS"

    eligible = bool(z.get("is_spike", False)) and not ambiguous
    return {
        "ticker": ticker, "run_timestamp": run_ts.isoformat(), "scan_source": scan_source,
        "week": z.get("week"), "gst_value": z.get("gst_value"),
        "is_partial_week": z.get("is_partial_week"),
        "zscore": z.get("zscore"), "is_spike": z.get("is_spike", False),
        "signal_tier": tier, "days_to_earnings": days_to_earnings,
        "ambiguous_symbol": ambiguous, "eligible_for_options_leg": eligible,
        "note": z.get("note", ""),
    }


def main():
    run_ts = datetime.now(timezone.utc)
    today = run_ts.date()
    print(f"*** GST EARNINGS-FIRST SCANNER — run at {run_ts.isoformat()} ***\n")

    # --- Step 1: earnings-window identification, full 425-ticker universe ---
    print(f"Step 1/2: checking next earnings date for all {len(engine.TICKERS)} tickers "
          f"(yfinance, same source as the existing engine)...")
    earnings_info = {}
    for i, ticker in enumerate(engine.TICKERS, start=1):
        next_date = fetch_next_earnings_date(ticker)
        if next_date is not None:
            days_calendar = (next_date - today).days
            days_trading = trading_days_out(today, next_date)
        else:
            days_calendar = None
            days_trading = None
        earnings_info[ticker] = {"next_earnings_date": next_date,
                                  "days_to_earnings_calendar": days_calendar,
                                  "trading_days_out": days_trading}
        if i % 50 == 0:
            print(f"  ...{i}/{len(engine.TICKERS)} earnings-date lookups done")
        time.sleep(EARNINGS_LOOKUP_PAUSE_S)

    priority_tickers = sorted(
        t for t, info in earnings_info.items()
        if info["trading_days_out"] is not None and 0 <= info["trading_days_out"] <= TRADING_DAY_WINDOW
    )
    print(f"\n=== {len(priority_tickers)} tickers currently within the next "
          f"{TRADING_DAY_WINDOW} trading days of earnings ===")
    if priority_tickers:
        for t in priority_tickers:
            info = earnings_info[t]
            print(f"    {t}: earnings {info['next_earnings_date']} "
                  f"({info['trading_days_out']} trading days out, "
                  f"{info['days_to_earnings_calendar']} calendar days out)")
    print()

    # --- Step 2: build the day's scan list (priority + random control sample) ---
    non_earnings_pool = [t for t in engine.TICKERS if t not in priority_tickers]
    control_n = min(CONTROL_SAMPLE_SIZE, len(non_earnings_pool))
    control_tickers = sorted(random.sample(non_earnings_pool, control_n))

    print(f"Step 2/2: GST z-score scan on {len(priority_tickers)} priority + "
          f"{len(control_tickers)} control = {len(priority_tickers) + len(control_tickers)} tickers "
          f"(pytrends, rate-limited)...\n")

    pt = engine.TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                          requests_args={"verify": False})

    scan_list = [(t, "earnings_priority") for t in priority_tickers] + \
                [(t, "control_sample") for t in control_tickers]

    rows = []
    for j, (ticker, source) in enumerate(scan_list, start=1):
        known_days = earnings_info.get(ticker, {}).get("days_to_earnings_calendar")
        row = scan_one_ticker(pt, ticker, source, run_ts, known_days)
        rows.append(row)
        flag = row["signal_tier"] if row["signal_tier"] else "-"
        print(f"[{j}/{len(scan_list)}] ({source}) {ticker}: z={row['zscore']} {flag} "
              f"days_to_earnings={row['days_to_earnings']}")
        time.sleep(random.uniform(*engine.BETWEEN_TICKERS))
        if j % engine.MICRO_BATCH_SIZE == 0 and j != len(scan_list):
            print(f"— small batch pause ({engine.MICRO_BATCH_PAUSE_S}s) —")
            time.sleep(engine.MICRO_BATCH_PAUSE_S)

    watchlist = pd.DataFrame(rows)

    run_ts_str = run_ts.strftime("%Y-%m-%dT%H-%M-%SZ")
    snapshot_path = OUT_DIR / f"earningsfirst_{run_ts_str}.csv"
    watchlist.to_csv(snapshot_path, index=False)

    log_path = OUT_DIR / "earningsfirst_log.csv"
    watchlist.to_csv(log_path, mode="a", index=False, header=not log_path.exists())

    latest_path = OUT_DIR / "earningsfirst_latest.csv"
    watchlist.to_csv(latest_path, index=False)

    eligible = watchlist[watchlist["eligible_for_options_leg"] == True]  # noqa: E712
    high_confidence = eligible[eligible["signal_tier"] == "HIGH_CONFIDENCE_STRONG_EARNINGS"]
    strong_earnings = eligible[eligible["signal_tier"] == "STRONG_EARNINGS"]
    strong = eligible[eligible["signal_tier"] == "STRONG"]
    standard = eligible[eligible["signal_tier"] == "STANDARD"]

    print(f"\n=== RESULTS ===")
    print(f"Tickers within next {TRADING_DAY_WINDOW} trading days of earnings: {len(priority_tickers)}")
    print(f"Total scanned this run: {len(watchlist)} ({len(priority_tickers)} priority + {len(control_tickers)} control)")
    print(f"{len(eligible)} eligible for options leg: {len(high_confidence)} HIGH_CONFIDENCE_STRONG_EARNINGS (z>=10), "
          f"{len(strong_earnings)} STRONG_EARNINGS (z=5-9.99), "
          f"{len(strong)} STRONG (non-earnings, reference only), {len(standard)} STANDARD (reference only)")
    if not eligible.empty:
        print(eligible[["ticker", "scan_source", "zscore", "signal_tier", "days_to_earnings"]].to_string(index=False))

    print(f"\nWrote snapshot to: {snapshot_path}")
    print(f"Appended to running log: {log_path}")
    print(f"Wrote latest-run copy to: {latest_path}")


if __name__ == "__main__":
    main()
