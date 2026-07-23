#!/usr/bin/env python3
# PRE-EARNINGS ATTENTION-PRESSURE TEST -- for each of the 152 canonical
# GST events, tests whether a GST spike precedes a sector-relative
# "pressure" run-up in the stock BEFORE earnings (excluding the earnings
# move itself), whether bigger spikes predict bigger pressure, and
# whether that pressure predicts a reversal on the earnings-day move
# itself (give-back pattern).
#
# WINDOWS (all using the SAME anchor+2/anchor+6 entry/exit convention
# already established throughout this project):
#   pressure window:      entry_date (anchor+2)  ->  pre_earnings_date
#   earnings-day window:  pre_earnings_date       ->  exit_date (anchor+6)
# where pre_earnings_date = the trading day immediately preceding
# exit_date, per this project's own established convention that
# exit_date IS "the next trading day's close after the earnings
# announcement" (same logic as GST_CandidateB's pre_earnings_exit_date,
# here derived from the ticker's own local daily-return calendar rather
# than a weekday-only approximation, since real daily data is available).
#
# pressure_return = stock raw return (pressure window) - sector ETF raw
# return (SAME window) -- isolates stock-specific pre-earnings movement
# from broad sector drift, the same spirit as this project's SPY-relative
# "excess return" convention, but sector- instead of market-relative,
# since sector drift is a closer, more specific counterfactual for "would
# this stock have moved anyway."
#
# Sector -> SPDR sector ETF mapping (standard, not tuned):
#   Technology->XLK, Consumer Cyclical->XLY, Communication Services->XLC,
#   Healthcare->XLV, Industrials->XLI, Consumer Defensive->XLP,
#   Energy->XLE, Financial Services->XLF
#
# Data sources: FixedWindow_PerEvent_Canonical.csv (events, z-scores,
# entry/exit dates) + AllTickers_Sectors.csv (sector labels) + each
# ticker's already-local daily excess-return files (stock returns) + a
# FRESH yfinance pull of daily closes for the 8 sector ETFs needed (no
# options data, per the request).
#
# Output: Live Signal Engine/PreEarningsPressure_Analysis.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

import GST_FixedWindow_PerEvent_Canonical as base

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "PreEarningsPressure_Analysis.csv"

SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Consumer Cyclical": "XLY",
    "Communication Services": "XLC",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financial Services": "XLF",
}

ETF_PULL_START, ETF_PULL_END = "2020-12-15", "2026-01-01"   # comfortable buffer around 2021-2025 event range


def fetch_etf_daily_returns(etf: str) -> pd.DataFrame:
    tk = yf.Ticker(etf, session=YF_SESSION)
    df = tk.history(start=ETF_PULL_START, end=ETF_PULL_END, interval="1d", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "ret"])
    out = pd.DataFrame({"Date": pd.to_datetime(df.index).tz_localize(None), "close": df["Close"].to_numpy()})
    out = out.sort_values("Date").reset_index(drop=True)
    out["ret"] = out["close"].pct_change()
    return out[["Date", "ret"]].dropna()


def pre_earnings_date_from_calendar(daily: pd.DataFrame, exit_date) -> pd.Timestamp | None:
    prior = daily.loc[daily["Date"] < exit_date, "Date"]
    return prior.max() if not prior.empty else None


def window_return(daily: pd.DataFrame, ret_col: str, start_date, end_date) -> float | None:
    if start_date is None or end_date is None or end_date <= start_date:
        return None
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def main():
    print("*** PRE-EARNINGS ATTENTION-PRESSURE TEST (152-event canonical population) ***\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    canon["entry_date"] = pd.to_datetime(canon["entry_date"])
    canon["exit_date"] = pd.to_datetime(canon["exit_date"])
    qualifying = canon[(canon["qualifies_z5"] == True) & (canon["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Qualifying priced events: n={len(qualifying)}\n")

    sector_df = pd.read_csv(SECTOR_PATH)
    sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))

    needed_etfs = sorted(set(SECTOR_ETF_MAP[sector_map[t]] for t in qualifying["ticker"].unique()
                              if sector_map.get(t) in SECTOR_ETF_MAP))
    print(f"Sector ETFs needed: {needed_etfs}")
    print("Pulling fresh daily ETF price history (yfinance, no options)...")
    etf_cache = {}
    for etf in needed_etfs:
        etf_cache[etf] = fetch_etf_daily_returns(etf)
        print(f"  {etf}: {len(etf_cache[etf])} daily return rows")
    print()

    daily_cache = {}
    rows = []
    for r in qualifying.itertuples(index=False):
        ticker = r.ticker
        sector = sector_map.get(ticker)
        etf = SECTOR_ETF_MAP.get(sector)

        row = {"ticker": ticker, "spike_week": r.spike_week.date(), "fixed_window_zscore": r.fixed_window_zscore,
               "sector": sector, "sector_etf": etf, "pressure_return_pct": None,
               "earnings_day_move_pct": None, "note": ""}

        if etf is None:
            row["note"] = f"no ETF mapping for sector '{sector}'"
            rows.append(row)
            continue

        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            row["note"] = "no daily stock-return data available"
            rows.append(row)
            continue

        pre_earnings_date = pre_earnings_date_from_calendar(daily, r.exit_date)
        if pre_earnings_date is None or pre_earnings_date <= r.entry_date:
            row["note"] = "could not resolve a valid pre-earnings date from the trading calendar"
            rows.append(row)
            continue
        row["pre_earnings_date"] = pre_earnings_date.date()

        stock_pressure_ret = window_return(daily, ret_col, r.entry_date, pre_earnings_date)
        etf_daily = etf_cache.get(etf, pd.DataFrame())
        etf_pressure_ret = window_return(etf_daily, "ret", r.entry_date, pre_earnings_date) if not etf_daily.empty else None

        if stock_pressure_ret is None or etf_pressure_ret is None:
            row["note"] = "missing return data over the pressure window"
            rows.append(row)
            continue

        earnings_day_move = window_return(daily, ret_col, pre_earnings_date, r.exit_date)

        row.update({
            "pressure_return_pct": round((stock_pressure_ret - etf_pressure_ret) * 100, 3),
            "stock_pressure_window_return_pct": round(stock_pressure_ret * 100, 3),
            "etf_pressure_window_return_pct": round(etf_pressure_ret * 100, 3),
            "earnings_day_move_pct": round(earnings_day_move * 100, 3) if earnings_day_move is not None else None,
        })
        rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    usable = result_df[result_df["pressure_return_pct"].notna()].copy()
    print(f"Usable events: {len(usable)} / {len(qualifying)}\n")

    mean_pressure = usable["pressure_return_pct"].mean()
    median_pressure = usable["pressure_return_pct"].median()
    pct_positive = (usable["pressure_return_pct"] > 0).mean() * 100

    print("=== RESULTS ===")
    print(f"n = {len(usable)}")
    print(f"Mean pressure return: {mean_pressure:+.2f} pct points")
    print(f"Median pressure return: {median_pressure:+.2f} pct points")
    print(f"Fraction with POSITIVE pressure return: {pct_positive:.1f}%\n")

    corr_z_pressure_p = usable["fixed_window_zscore"].corr(usable["pressure_return_pct"], method="pearson")
    corr_z_pressure_s = usable["fixed_window_zscore"].corr(usable["pressure_return_pct"], method="spearman")
    print("Does z-score magnitude predict pressure-return magnitude?")
    print(f"  z-score vs. pressure_return_pct: Pearson r={corr_z_pressure_p:.3f}   Spearman rho={corr_z_pressure_s:.3f}\n")

    usable_reversal = usable[usable["earnings_day_move_pct"].notna()].copy()
    corr_reversal_p = usable_reversal["pressure_return_pct"].corr(usable_reversal["earnings_day_move_pct"], method="pearson")
    corr_reversal_s = usable_reversal["pressure_return_pct"].corr(usable_reversal["earnings_day_move_pct"], method="spearman")
    print(f"Reversal test (n={len(usable_reversal)}): does pressure return predict the earnings-day move direction?")
    print(f"  pressure_return_pct vs. earnings_day_move_pct: Pearson r={corr_reversal_p:.3f}   "
          f"Spearman rho={corr_reversal_s:.3f}")
    if corr_reversal_p < -0.15:
        print("  -> Negative relationship: some evidence of a give-back/reversal pattern "
              "(high pre-earnings pressure precedes a smaller or negative earnings-day move).")
    elif corr_reversal_p > 0.15:
        print("  -> Positive relationship: pre-earnings pressure tends to CONTINUE into the "
              "earnings-day move, not reverse (momentum, not reversal).")
    else:
        print("  -> Weak/no relationship either way.")


if __name__ == "__main__":
    main()
