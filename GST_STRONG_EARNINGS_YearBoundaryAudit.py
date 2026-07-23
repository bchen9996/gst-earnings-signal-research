#!/usr/bin/env python3
# YEAR-BOUNDARY NaN-DROP BUG AUDIT — 147 STRONG_EARNINGS events.
#
# GST_STRONG_EARNINGS bug found while auditing the SPY benchmark (see
# Live Signal Engine/SPY_Benchmark_Audit.md): every "Daily Excess Return
# Data" CSV in this project is pulled ONE CALENDAR YEAR AT A TIME, and
# daily returns are computed via .pct_change().dropna() INDEPENDENTLY
# within each year's file. The first trading day of every year has no
# prior row in that same file to diff against, so it's NaN and silently
# dropped -- for every ticker, not just SPY. Confirmed missing dates in
# the 2021-2025 data (checked, not assumed):
#   2022-01-03, 2023-01-03, 2024-01-02, 2025-01-02
# (2021 has no missing first-day issue relevant here since no event's
# window reaches back before the data starts.)
#
# This script rebuilds a CONTINUOUS (non-chunked, no year-boundary gaps)
# daily price/return series per ticker directly from yfinance for all 28
# tickers in the 147-event population, re-prices every event with BOTH
# the existing (gapped) data and the corrected (continuous) data using
# the IDENTICAL Black-Scholes straddle methodology as
# GST_Straddle_Simulation_2021_2025_51Ticker.py, and reports which events
# differ, by how much, and the corrected aggregate win rate / median P&L
# / Sharpe for the full 147-event set.
#
# Output: Live Signal Engine/STRONG_EARNINGS_YearBoundaryAudit_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import sys
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
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
YEARS = list(range(2021, 2026))
DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "STRONG_EARNINGS_YearBoundaryAudit_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

KNOWN_MISSING_DATES = [pd.Timestamp(d) for d in ["2022-01-03", "2023-01-03", "2024-01-02", "2025-01-02"]]
PROXIMITY_TRADING_DAYS = 2

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


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


def load_daily_excess_buggy(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or df.empty:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def pull_continuous_price(ticker: str) -> pd.Series:
    df = yf.download(ticker, start="2020-12-15", end="2026-01-01", session=YF_SESSION,
                      auto_adjust=True, progress=False, group_by="column", threads=False)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    close = df["Close"] if "Close" in df.columns else df.squeeze("columns")
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    s = pd.Series(close.values, index=pd.to_datetime(close.index).tz_localize(None), name=ticker).sort_index()
    return s


def build_corrected_daily(ticker: str, spy_price: pd.Series) -> pd.DataFrame:
    s_tkr = pull_continuous_price(ticker)
    if s_tkr.empty or spy_price.empty:
        return pd.DataFrame()
    r_tkr = s_tkr.pct_change().dropna()
    r_spy = spy_price.pct_change().dropna()
    idx = r_tkr.index.intersection(r_spy.index)
    r_tkr, r_spy = r_tkr.loc[idx], r_spy.loc[idx]
    return pd.DataFrame({"Date": idx, f"{ticker} Daily Return": r_tkr.values,
                          "Excess Daily Return": (r_tkr - r_spy).values}).reset_index(drop=True)


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


def price_event(daily, ret_col, anchor, markup):
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if entry_date is None or exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma is None:
        return None
    iv = sigma * markup
    T = dte_days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"entry_date": entry_date, "exit_date": exit_date, "win": pnl_pct > 0, "pnl_pct": pnl_pct}


def is_near_boundary(entry_date, exit_date) -> bool:
    if entry_date is None or exit_date is None:
        return False
    for missing in KNOWN_MISSING_DATES:
        if (entry_date - timedelta(days=PROXIMITY_TRADING_DAYS + 2)) <= missing <= (exit_date + timedelta(days=PROXIMITY_TRADING_DAYS + 2)):
            return True
    return False


def window_contains_missing(entry_date, exit_date) -> list:
    if entry_date is None or exit_date is None:
        return []
    return [str(m.date()) for m in KNOWN_MISSING_DATES if entry_date < m <= exit_date]


def max_drawdown(equity_curve: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity_curve)
    return float(((equity_curve - running_max) / running_max).min())


def compute_sharpe_and_dd(trades: pd.DataFrame) -> tuple:
    trades = trades.sort_values("exit_date").reset_index(drop=True)
    dollar_pnl = 10_000 * (trades["pnl_pct"] / 100.0)
    equity = 100_000 + dollar_pnl.cumsum()
    equity_curve = np.concatenate([[100_000], equity.to_numpy()])
    mdd = max_drawdown(equity_curve)
    t = trades.copy()
    t["month"] = pd.to_datetime(t["exit_date"]).dt.to_period("M")
    t["dollar_pnl"] = dollar_pnl
    monthly = t.groupby("month")["dollar_pnl"].sum()
    full_range = pd.period_range(t["month"].min(), t["month"].max(), freq="M")
    monthly = monthly.reindex(full_range, fill_value=0.0)
    monthly_equity_start = 100_000 + monthly.cumsum().shift(1).fillna(0.0)
    monthly_return = monthly / monthly_equity_start
    mean_m, std_m = float(monthly_return.mean()), float(monthly_return.std(ddof=1))
    sharpe = (mean_m / std_m * np.sqrt(12)) if std_m > 0 else None
    return sharpe, mdd


def main():
    print("*** YEAR-BOUNDARY NaN-DROP BUG AUDIT — 147 STRONG_EARNINGS EVENTS ***\n")

    markup = load_calibrated_near_earnings_markup()
    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    tickers = sorted(events["ticker"].unique())
    print(f"Auditing n={len(events)} events across {len(tickers)} tickers\n")

    print("Pulling SPY continuous price series (single pull, no year chunking)...")
    spy_price = pull_continuous_price("SPY")

    print("Building CORRECTED continuous daily series per ticker (fresh yfinance pull, no chunking)...")
    buggy_cache, corrected_cache = {}, {}
    for i, t in enumerate(tickers, start=1):
        buggy_cache[t] = load_daily_excess_buggy(t)
        corrected_cache[t] = build_corrected_daily(t, spy_price)
        print(f"  [{i}/{len(tickers)}] {t}: buggy rows={len(buggy_cache[t])}  corrected rows={len(corrected_cache[t])}")
    print()

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        ret_col_buggy = f"{ticker} Daily Return"
        ret_col_corr = f"{ticker} Daily Return"

        buggy_daily = buggy_cache.get(ticker, pd.DataFrame())
        corr_daily = corrected_cache.get(ticker, pd.DataFrame())
        if buggy_daily.empty or corr_daily.empty or ret_col_buggy not in buggy_daily.columns:
            continue

        buggy_priced = price_event(buggy_daily, ret_col_buggy, anchor, markup)
        corr_priced = price_event(corr_daily, ret_col_corr, anchor, markup)
        if buggy_priced is None or corr_priced is None:
            continue

        missing_in_window = window_contains_missing(buggy_priced["entry_date"], buggy_priced["exit_date"])
        near_boundary = is_near_boundary(buggy_priced["entry_date"], buggy_priced["exit_date"])
        entry_shifted = buggy_priced["entry_date"] != corr_priced["entry_date"]
        exit_shifted = buggy_priced["exit_date"] != corr_priced["exit_date"]
        pnl_diff = corr_priced["pnl_pct"] - buggy_priced["pnl_pct"]
        affected = bool(missing_in_window) or entry_shifted or exit_shifted

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": round(float(zscore), 3),
            "near_year_boundary": near_boundary,
            "missing_dates_in_window": "; ".join(missing_in_window),
            "entry_date_original": buggy_priced["entry_date"].date(), "exit_date_original": buggy_priced["exit_date"].date(),
            "entry_date_corrected": corr_priced["entry_date"].date(), "exit_date_corrected": corr_priced["exit_date"].date(),
            "entry_date_shifted": entry_shifted, "exit_date_shifted": exit_shifted,
            "win_original": buggy_priced["win"], "pnl_pct_original": round(buggy_priced["pnl_pct"], 2),
            "win_corrected": corr_priced["win"], "pnl_pct_corrected": round(corr_priced["pnl_pct"], 2),
            "pnl_pct_diff": round(pnl_diff, 2),
            "affected_by_bug": affected,
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    print(f"Total events priced both ways: {len(result)}\n")

    near_boundary_events = result[result["near_year_boundary"]]
    affected_events = result[result["affected_by_bug"]]
    print(f"Events near a year boundary (+/-{PROXIMITY_TRADING_DAYS} trading days, per request): {len(near_boundary_events)}")
    print(f"Events ACTUALLY AFFECTED (missing date inside window OR entry/exit date shifted): {len(affected_events)}\n")

    if len(near_boundary_events):
        print("=== NEAR-BOUNDARY EVENTS — full detail ===")
        cols = ["ticker", "spike_week", "entry_date_original", "exit_date_original", "missing_dates_in_window",
                "entry_date_shifted", "exit_date_shifted", "pnl_pct_original", "pnl_pct_corrected", "pnl_pct_diff", "affected_by_bug"]
        print(near_boundary_events[cols].to_string(index=False))
        print()

    # --- Recompute aggregate metrics using CORRECTED values everywhere (identical to original for unaffected events) ---
    final = result.copy()
    final["win_final"] = final["win_corrected"]
    final["pnl_pct_final"] = final["pnl_pct_corrected"]
    final["exit_date_final"] = final["exit_date_corrected"]

    orig_win = result["win_original"].mean() * 100
    orig_median = result["pnl_pct_original"].median()
    orig_trades = result.rename(columns={"pnl_pct_original": "pnl_pct", "exit_date_original": "exit_date"})
    orig_sharpe, orig_mdd = compute_sharpe_and_dd(orig_trades[["pnl_pct", "exit_date"]])

    final_win = final["win_final"].mean() * 100
    final_median = final["pnl_pct_final"].median()
    final_trades = final.rename(columns={"pnl_pct_final": "pnl_pct", "exit_date_final": "exit_date"})
    final_sharpe, final_mdd = compute_sharpe_and_dd(final_trades[["pnl_pct", "exit_date"]])

    print("=== AGGREGATE COMPARISON, FULL 147-EVENT SET ===")
    print(f"{'':<12}{'n':>5}{'Win%':>10}{'Median P&L':>14}{'Sharpe':>10}{'MaxDD':>10}")
    print(f"{'ORIGINAL':<12}{len(result):>5}{orig_win:>9.1f}%{orig_median:>13.1f}%{orig_sharpe:>10.2f}{orig_mdd*100:>9.1f}%")
    print(f"{'CORRECTED':<12}{len(final):>5}{final_win:>9.1f}%{final_median:>13.1f}%{final_sharpe:>10.2f}{final_mdd*100:>9.1f}%")

    print(f"\n{len(affected_events)}/{len(result)} events actually changed value due to the year-boundary bug.")


if __name__ == "__main__":
    main()
