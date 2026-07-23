#!/usr/bin/env python3
# GST Straddle Profitability Test — cost-adjusted, look-ahead-free.
#
# For every historical spike event, simulates buying an at-the-money
# straddle at Tuesday's price (the mid-week detection point validated in
# GST_MidWeek_Detection_Test.py, which found 88% of spike events were
# already detectable by then) and checks whether the realized move by two
# exit horizons — end of spike week (anchor+6) and end of the full 3-week
# analysis window (anchor+13) — covers the straddle's cost.
#
# Runs on ALL 310 spike events, not just the 100 previously sampled: unlike
# the mid-week detection test, this step needs NO new data (no pytrends or
# yfinance calls) — everything comes from data already pulled (Daily
# Excess Return Data has each ticker's own raw daily return, which is what
# a straddle's payoff actually depends on).
#
# *** NO LOOK-AHEAD, BY CONSTRUCTION ***
# The straddle is priced with Black-Scholes using an implied-volatility
# ASSUMPTION derived from each ticker's own TRAILING realized volatility —
# a 60-trading-day window ending strictly BEFORE the analysis window
# starts (before anchor-7), so it never touches any data from the "before",
# "spike week", or "after" periods. A flat 1.10x multiplier is applied on
# top (a simple, disclosed stand-in for the well-documented volatility risk
# premium — options tend to trade above subsequently-realized vol on
# average). The realized move itself is NEVER used to set the price — only
# to grade the payoff afterward. A flat 5% cost loading on top of the
# Black-Scholes fair value approximates real-world bid-ask spread and
# commission costs of actually acquiring the straddle.
#
# *** SIMPLIFICATION, DISCLOSED ***
# The straddle is evaluated AS IF it expires exactly at each exit horizon
# (payoff = |S_exit - S_entry|, i.e. pure intrinsic value at that date) —
# this directly answers "did the realized move cover the cost by then,"
# but does not model selling the position early at its remaining
# time-value if that would be more realistic for e.g. the end-of-spike-week
# horizon on an option that in a real trade might be held to a real
# expiration further out.
#
# Output: Straddle Profitability Test/results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import numpy as np
import pandas as pd

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
YEARS = list(range(2014, 2020))

SPIKE_DIR = Path("Conjunction Zscore")
DAILY_DIR = Path("Daily Excess Return Data")
OUT_DIR = Path("Straddle Profitability Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENTRY_OFFSET_DAYS = 2     # Tuesday, matching the mid-week detection test
EXIT_HORIZONS = {"end_of_spike_week": 6, "end_of_window": 13}  # calendar days from anchor

RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
IV_MARKUP = 1.10           # vol risk premium stand-in — disclosed, not fit to this data
COST_LOADING = 1.05        # pay 5% over BS fair value — bid-ask/commission stand-in


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S: float, K: float, T: float, r: float, sigma: float) -> float | None:
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def load_ticker_returns(ticker: str) -> pd.DataFrame:
    col = f"{ticker} Daily Return"
    frames = []
    for year in YEARS:
        p = DAILY_DIR / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or col not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df[["Date", col]].rename(columns={col: "ret"}).dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame(columns=["Date", "ret"])
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def nearest_trading_day_on_or_before(daily: pd.DataFrame, target) -> pd.Timestamp | None:
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    if eligible.empty:
        return None
    return eligible.max()


def cumulative_return(daily: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> float | None:
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, "ret"]
    if rets.empty:
        return None
    return float((1 + rets).prod() - 1)


def trailing_realized_vol(daily: pd.DataFrame, cutoff: pd.Timestamp) -> float | None:
    """Annualized realized vol from the VOL_LOOKBACK window ending strictly before cutoff."""
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist["ret"].std() * math.sqrt(252))


def main():
    rows = []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if not sp.exists():
            continue
        events = pd.read_csv(sp)
        daily = load_ticker_returns(ticker)
        if daily.empty:
            continue

        for _, ev in events.iterrows():
            anchor = pd.to_datetime(ev["spike_week"], errors="coerce")
            if pd.isna(anchor):
                continue

            entry_target = anchor + timedelta(days=ENTRY_OFFSET_DAYS)
            entry_date = nearest_trading_day_on_or_before(daily, entry_target)
            if entry_date is None:
                continue

            vol_cutoff = anchor - timedelta(days=7)   # never touches before/spike/after periods
            sigma = trailing_realized_vol(daily, vol_cutoff)

            row = {
                "ticker": ticker, "spike_week": anchor.date(), "entry_date": entry_date.date(),
                "full_week_zscore": ev.get("zscore"),
                "trailing_realized_vol_annualized": round(sigma, 4) if sigma else None,
            }

            if sigma is None:
                row["note"] = "insufficient trailing vol history"
                for h in EXIT_HORIZONS:
                    row[f"{h}_note"] = "skipped — no vol estimate"
                rows.append(row)
                continue

            iv_assumed = sigma * IV_MARKUP

            for h, offset in EXIT_HORIZONS.items():
                exit_target = anchor + timedelta(days=offset)
                exit_date = nearest_trading_day_on_or_before(daily, exit_target)
                if exit_date is None or exit_date <= entry_date:
                    row[f"{h}_note"] = "no valid exit date"
                    continue

                dte_days = (exit_date - entry_date).days
                if dte_days <= 0:
                    row[f"{h}_note"] = "zero DTE"
                    continue
                T = dte_days / 365.0

                straddle_fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv_assumed)
                if straddle_fair is None:
                    row[f"{h}_note"] = "BS pricing failed"
                    continue
                straddle_cost = straddle_fair * COST_LOADING

                cum_ret = cumulative_return(daily, entry_date, exit_date)
                if cum_ret is None:
                    row[f"{h}_note"] = "no return data in holding period"
                    continue

                s_exit = 100.0 * (1 + cum_ret)
                intrinsic_value = abs(s_exit - 100.0)
                net_pnl = intrinsic_value - straddle_cost
                net_pnl_pct_of_cost = net_pnl / straddle_cost

                row[f"{h}_dte_days"] = dte_days
                row[f"{h}_straddle_cost"] = round(straddle_cost, 3)
                row[f"{h}_realized_move_pct"] = round(cum_ret * 100, 3)
                row[f"{h}_intrinsic_value"] = round(intrinsic_value, 3)
                row[f"{h}_net_pnl"] = round(net_pnl, 3)
                row[f"{h}_net_pnl_pct_of_cost"] = round(net_pnl_pct_of_cost * 100, 2)
                row[f"{h}_win"] = bool(net_pnl > 0)
                row[f"{h}_note"] = ""

            rows.append(row)

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "results.csv"
    results.to_csv(out_path, index=False)

    print(f"Total spike events processed: {len(results)}\n")

    for h in EXIT_HORIZONS:
        win_col, pnl_col, pnlpct_col = f"{h}_win", f"{h}_net_pnl", f"{h}_net_pnl_pct_of_cost"
        usable = results[results[win_col].notna()] if win_col in results.columns else pd.DataFrame()
        n = len(usable)
        if n == 0:
            print(f"=== {h} ===\nNo usable events.\n")
            continue

        win_rate = usable[win_col].mean()
        avg_pnl = usable[pnl_col].mean()
        avg_pnl_pct = usable[pnlpct_col].mean()
        median_pnl_pct = usable[pnlpct_col].median()

        print(f"=== {h} (DTE ~{usable[f'{h}_dte_days'].mean():.1f} days avg) ===")
        print(f"n = {n}")
        print(f"Win rate (net P&L > 0): {win_rate*100:.1f}%")
        print(f"Avg net P&L: {avg_pnl:+.3f} per 100 notional (avg straddle cost: {usable[f'{h}_straddle_cost'].mean():.3f})")
        print(f"Avg net P&L as % of premium paid: {avg_pnl_pct:+.1f}%")
        print(f"Median net P&L as % of premium paid: {median_pnl_pct:+.1f}%")
        print()

    n_skipped = int(results["trailing_realized_vol_annualized"].isna().sum())
    print(f"({n_skipped} events skipped entirely — insufficient trailing volatility history, "
          f"typically early events in each ticker's series)")
    print(f"\nAssumptions: r={RISK_FREE_RATE:.1%} flat, IV = {IV_MARKUP}x trailing {VOL_LOOKBACK_TRADING_DAYS}d "
          f"realized vol (computed strictly before the analysis window), cost loading = {COST_LOADING}x BS fair value.")
    print(f"\nWrote full results to: {out_path}")


if __name__ == "__main__":
    main()
