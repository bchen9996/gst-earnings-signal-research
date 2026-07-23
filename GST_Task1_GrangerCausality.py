#!/usr/bin/env python3
# TASK 1 — Granger causality between weekly GST z-score and weekly
# realized volatility (|weekly price return|), 51 tickers, 2021-2025. All
# on-disk data, no new pulls: GST z-scores from AllTickers_ZscoreSeries.csv
# (already built), volatility computed fresh from the on-disk daily price
# data (Daily Excess Return Data*/) as the task specifies.
#
# *** METHODOLOGY DISCLOSURE — PER-TICKER, NOT NAIVELY POOLED ***
# statsmodels' grangercausalitytests operates on a single bivariate time
# series. Concatenating all 51 tickers' series end-to-end would create
# spurious "week-to-week" jumps between unrelated tickers that the
# regression would wrongly treat as consecutive — methodologically
# invalid. Instead, Granger causality is run SEPARATELY per ticker (51
# tests per lag per direction), then aggregated: the fraction of tickers
# showing significant Granger causality (p<0.05) at each lag, plus the
# mean/median F-stat and p-value across tickers. This is the standard way
# to handle this kind of panel data with a non-panel-aware tool.
#
# *** THIS IS TEMPORAL PRECEDENCE, NOT CAUSALITY — STATED EXPLICITLY ***
# Granger causality tests whether past values of X improve prediction of
# current Y beyond Y's own past — a test of statistical temporal ordering
# and predictive content, not a test of true causal mechanism. Reported
# as such throughout, per the task's own instruction.
#
# Output: Live Signal Engine/GrangerCausality_Results.csv

from __future__ import annotations
from pathlib import Path
import sys, io, contextlib
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

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

ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
OUT_PATH = Path("Live Signal Engine") / "GrangerCausality_Results.csv"

MAX_LAG = 4
MIN_OBS = 30   # minimum overlapping weekly observations to attempt Granger test


def week_start(d: pd.Series) -> pd.Series:
    d = pd.to_datetime(d)
    return d - pd.to_timedelta((d.dt.weekday + 1) % 7, unit="D")


def weekly_abs_return(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        ret_col = f"{ticker} Daily Return"
        if "Date" not in df.columns or ret_col not in df.columns:
            continue
        df = df.rename(columns={ret_col: "ret"})[["Date", "ret"]]
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    daily = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)
    daily["week"] = week_start(daily["Date"])
    weekly = daily.groupby("week").agg(weekly_return=("ret", lambda x: float(np.prod(1 + x) - 1))).reset_index()
    weekly["abs_return"] = weekly["weekly_return"].abs()
    return weekly[["week", "abs_return"]]


def run_granger_silent(data: np.ndarray, maxlag: int):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = grangercausalitytests(data, maxlag=maxlag, verbose=True)
    return result


def main():
    print(f"*** TASK 1: Granger causality, GST z-score <-> realized volatility (lags 1-{MAX_LAG}) ***\n")

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])

    rows = []
    n_tested = 0
    n_skipped_insufficient = 0
    for ticker in ALL_TICKERS:
        z_ticker = z_df[z_df["ticker"] == ticker][["week", "zscore_simple"]].dropna()
        vol_ticker = weekly_abs_return(ticker)
        if z_ticker.empty or vol_ticker.empty:
            n_skipped_insufficient += 1
            continue

        merged = z_ticker.merge(vol_ticker, on="week", how="inner").sort_values("week").dropna()
        if len(merged) < MIN_OBS:
            n_skipped_insufficient += 1
            continue

        z_series = merged["zscore_simple"].to_numpy(dtype=float)
        vol_series = merged["abs_return"].to_numpy(dtype=float)
        n_tested += 1

        # Direction (a): does lagged Z help predict current VOL? data = [vol, z]
        try:
            res_a = run_granger_silent(np.column_stack([vol_series, z_series]), MAX_LAG)
            for lag in range(1, MAX_LAG + 1):
                f_stat, p_val, _, _ = res_a[lag][0]["ssr_ftest"]
                rows.append({"ticker": ticker, "direction": "z_causes_vol", "lag": lag,
                             "f_stat": round(f_stat, 4), "p_value": round(p_val, 4), "n_obs": len(merged)})
        except Exception as e:
            print(f"  [{ticker}] direction (a) failed: {e}")

        # Direction (b): does lagged VOL help predict current Z? data = [z, vol]
        try:
            res_b = run_granger_silent(np.column_stack([z_series, vol_series]), MAX_LAG)
            for lag in range(1, MAX_LAG + 1):
                f_stat, p_val, _, _ = res_b[lag][0]["ssr_ftest"]
                rows.append({"ticker": ticker, "direction": "vol_causes_z", "lag": lag,
                             "f_stat": round(f_stat, 4), "p_value": round(p_val, 4), "n_obs": len(merged)})
        except Exception as e:
            print(f"  [{ticker}] direction (b) failed: {e}")

        print(f"[{ticker}] tested, n_obs={len(merged)}")

    print(f"\nTickers tested: {n_tested}   skipped (insufficient overlapping data, need >={MIN_OBS} weeks): {n_skipped_insufficient}\n")

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    print(f"=== AGGREGATE ACROSS {n_tested} TICKERS ===\n")
    for direction, label in [("z_causes_vol", "(a) Does lagged Z Granger-cause VOL?"),
                              ("vol_causes_z", "(b) Does lagged VOL Granger-cause Z?")]:
        print(f"--- {label} ---")
        for lag in range(1, MAX_LAG + 1):
            sub = result[(result["direction"] == direction) & (result["lag"] == lag)]
            if sub.empty:
                continue
            frac_sig = (sub["p_value"] < 0.05).mean() * 100
            mean_f = sub["f_stat"].mean()
            median_p = sub["p_value"].median()
            print(f"  lag={lag}: {frac_sig:.1f}% of tickers significant (p<0.05)   "
                  f"mean F={mean_f:.2f}   median p={median_p:.4f}")
        print()

    print("*** REMINDER: this is a test of temporal predictive precedence, NOT true causality. ***")
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
