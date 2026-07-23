#!/usr/bin/env python3
# TASK 4 — Transaction cost stress test. All on-disk data, no new pulls.
#
# group_a_z4_earnings_adjacent.csv only stores NET pnl_pct, not the raw
# cost/intrinsic split needed to rescale cost independently — so cost and
# intrinsic value are recomputed fresh here (same trailing-vol + Black-
# Scholes methodology used throughout this project, deterministic, reused
# not re-derived) to get both components separately, then five cost
# multipliers are applied to the SAME intrinsic values.
#
# Cost scenarios are multiplicative on top of the ALREADY earnings-aware
# model (which itself already applies the calibrated 1.2398x near-earnings
# markup over naive trailing vol) — so e.g. "+30%" here means
# 1.2398 * 1.30 = 1.611x the naive model, not 1.30x. Stated explicitly, not
# left implicit.
#
# Output: Live Signal Engine/TransactionCostStressTest_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import math
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "TransactionCostStressTest_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
BASE_COST_LOADING = 1.05
COST_SCENARIOS = {"baseline": 1.00, "+10%": 1.10, "+20%": 1.20, "+30%": 1.30, "+50%": 1.50}
WIN_RATE_FLOOR = 60.0


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def main():
    print(f"*** TASK 4: Transaction cost stress test (z>={Z_THRESHOLD:g}) ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Calibrated near-earnings markup (reused): {near_earnings_markup:.4f}x")
    print("Cost scenario multipliers are ON TOP of this already-earnings-aware model:")
    for label, mult in COST_SCENARIOS.items():
        print(f"  {label}: effective total markup = {near_earnings_markup*mult:.4f}x naive (naive=1.10x)")
    print()

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    print("Recomputing cost/intrinsic components fresh (on-disk data, deterministic re-derivation)...")
    daily_cache = {}
    rows = []
    n_repro_mismatch = 0
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        if ticker not in daily_cache:
            daily_cache[ticker] = load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue

        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
        if entry_date is None or exit_date is None or exit_date <= entry_date:
            continue
        dte_days = (exit_date - entry_date).days
        sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
        if sigma is None:
            continue
        T = dte_days / 365.0
        iv = sigma * near_earnings_markup
        fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
        if fair is None:
            continue
        base_cost = fair * BASE_COST_LOADING
        cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
        if cum_ret is None:
            continue
        intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)

        repro_pnl = (intrinsic - base_cost) / base_cost * 100
        if abs(repro_pnl - ev["end_of_spike_week_pnl_pct"]) > 0.5:
            n_repro_mismatch += 1

        row = {"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore,
               "intrinsic": intrinsic, "base_cost": base_cost}
        for label, mult in COST_SCENARIOS.items():
            cost = base_cost * mult
            pnl_pct = (intrinsic - cost) / cost * 100
            row[f"win_{label}"] = pnl_pct > 0
            row[f"pnl_{label}"] = pnl_pct
        rows.append(row)

    result = pd.DataFrame(rows)
    print(f"Usable events: n={len(result)}   "
          f"Reproduction sanity check (baseline should match existing pnl_pct): {n_repro_mismatch} mismatches > 0.5pt\n")

    print(f"=== RESULTS (spike_week horizon) ===")
    floor_crossing_scenario = None
    negative_median_scenario = None
    for label in COST_SCENARIOS:
        win_col, pnl_col = f"win_{label}", f"pnl_{label}"
        wr = result[win_col].mean() * 100
        med = result[pnl_col].median()
        avg = result[pnl_col].mean()
        print(f"{label:<8} win={wr:5.1f}%  avg={avg:+8.1f}%  median={med:+8.1f}%")
        if wr < WIN_RATE_FLOOR and floor_crossing_scenario is None:
            floor_crossing_scenario = label
        if med < 0 and negative_median_scenario is None:
            negative_median_scenario = label

    print(f"\nWin rate first drops below {WIN_RATE_FLOOR:g}%: "
          f"{floor_crossing_scenario if floor_crossing_scenario else 'NEVER within tested range (+50%)'}")
    print(f"Median P&L first goes negative: "
          f"{negative_median_scenario if negative_median_scenario else 'NEVER within tested range (+50%)'}")

    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
