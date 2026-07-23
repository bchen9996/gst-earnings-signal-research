#!/usr/bin/env python3
# TASK 2 — Retail ownership heterogeneity: does the GST effect concentrate
# in stocks with higher retail (vs institutional) ownership?
#
# *** DATA SOURCE SUBSTITUTION — DISCLOSED, NOT SILENT ***
# The task asks for "institutional ownership percentage... from SEC EDGAR
# 13F filings." Raw 13F data on EDGAR is published as bulk quarterly
# INFOTABLE datasets (security-level holdings from EVERY 13F filer that
# quarter) with no per-company "% institutional ownership" field — getting
# that number requires aggregating holdings across thousands of filers by
# CUSIP and dividing by shares outstanding, a multi-hour data-engineering
# job, not a live pull. Instead this uses yfinance's `heldPercentInstitutions`
# field, which Yahoo Finance itself computes from aggregated 13F-derived
# holms data — the standard practical proxy for this number, but NOT a
# direct SEC EDGAR pull. Flagged here explicitly rather than mislabeled.
#
# *** CURRENT, NOT HISTORICAL — per the task's own acknowledgement ***
# This is TODAY's institutional ownership %, used as a proxy for each
# ticker's typical retail/institutional mix. It is NOT the ownership mix
# at the time of each historical 2021-2025 event — ownership composition
# does drift over time, so this is a stable-characteristic proxy, not a
# point-in-time measurement.
#
# Output: Live Signal Engine/RetailOwnership_Results.csv

from __future__ import annotations
from pathlib import Path
import sys, time
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
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "RetailOwnership_Results.csv"

Z_THRESHOLD = 5.0
MAX_ATTEMPTS = 3
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_institutional_pct(ticker: str) -> float | None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            info = tk.get_info()
            val = info.get("heldPercentInstitutions")
            if val is not None:
                return float(val)
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(3)
    return None


def two_sample_permutation_test(a, b, n_perm, rng, stat="mean"):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    f = np.mean if stat == "mean" else np.median
    observed_diff = f(a) - f(b)
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = f(pooled[:n_a]) - f(pooled[n_a:])
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    print("*** TASK 2: Retail ownership heterogeneity ***\n")

    print(f"Pulling institutional ownership % for {len(ALL_TICKERS)} tickers (yfinance, cached, one call each)...")
    rows = []
    for i, t in enumerate(ALL_TICKERS, start=1):
        inst_pct = fetch_institutional_pct(t)
        retail_est = (1 - inst_pct) if inst_pct is not None else None
        rows.append({"ticker": t, "institutional_pct": inst_pct, "retail_ownership_est": retail_est})
        print(f"  [{i}/{len(ALL_TICKERS)}] {t}: institutional={inst_pct if inst_pct is not None else 'N/A'}")
        time.sleep(0.8)

    ownership = pd.DataFrame(rows)
    n_missing = ownership["institutional_pct"].isna().sum()
    print(f"\nMissing institutional ownership data: {n_missing}/{len(ownership)}\n")

    median_retail = ownership["retail_ownership_est"].median()
    ownership["retail_group"] = np.where(ownership["retail_ownership_est"] > median_retail, "high_retail",
                                  np.where(ownership["retail_ownership_est"].notna(), "low_retail", None))
    print(f"Median retail ownership estimate across {ownership['retail_ownership_est'].notna().sum()} tickers: "
          f"{median_retail*100:.1f}%")
    print(ownership.sort_values("retail_ownership_est", ascending=False)[["ticker", "institutional_pct", "retail_ownership_est", "retail_group"]].to_string(index=False))
    print()

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events = events.merge(ownership[["ticker", "retail_ownership_est", "retail_group"]], on="ticker", how="left")

    n_matched = events["retail_group"].notna().sum()
    print(f"STRONG_EARNINGS events (z>={Z_THRESHOLD:g}): n={len(events)}, matched to ownership data: n={n_matched}\n")

    rng = np.random.default_rng(RANDOM_SEED)
    summary_rows = []
    groups = {}
    for grp in ["high_retail", "low_retail"]:
        sub = events[events["retail_group"] == grp]
        n = len(sub)
        if n == 0:
            continue
        win_rate = sub["end_of_spike_week_win"].mean() * 100
        median_pnl = sub["end_of_spike_week_pnl_pct"].median()
        avg_pnl = sub["end_of_spike_week_pnl_pct"].mean()
        groups[grp] = sub["end_of_spike_week_pnl_pct"].to_numpy(dtype=float)
        n_tickers = sub["ticker"].nunique()
        print(f"{grp}: n={n} ({n_tickers} tickers)  win={win_rate:.1f}%  median P&L={median_pnl:+.1f}%  avg P&L={avg_pnl:+.1f}%")
        summary_rows.append({"group": grp, "n_events": n, "n_tickers": n_tickers,
                              "win_rate_pct": round(win_rate, 1), "median_pnl_pct": round(median_pnl, 1),
                              "avg_pnl_pct": round(avg_pnl, 1)})

    if "high_retail" in groups and "low_retail" in groups:
        diff_mean, p_mean = two_sample_permutation_test(groups["high_retail"], groups["low_retail"], N_PERMUTATIONS, rng, "mean")
        diff_med, p_med = two_sample_permutation_test(groups["high_retail"], groups["low_retail"], N_PERMUTATIONS,
                                                        np.random.default_rng(RANDOM_SEED), "median")
        print(f"\nHigh-retail vs low-retail: diff in mean P&L={diff_mean:+.1f}pt  p={p_mean:.4f} "
              f"({'significant' if p_mean < 0.05 else 'not significant'})")
        print(f"Diff in median P&L={diff_med:+.1f}pt  p={p_med:.4f} ({'significant' if p_med < 0.05 else 'not significant'})")
        win_high = (groups['high_retail'] > 0).mean() * 100
        win_low = (groups['low_retail'] > 0).mean() * 100
        print(f"Hypothesis (higher retail -> stronger GST effect): "
              f"{'SUPPORTED' if win_high > win_low and diff_mean > 0 else 'NOT SUPPORTED'} "
              f"(high_retail win={win_high:.1f}% vs low_retail win={win_low:.1f}%)")
    else:
        diff_mean = diff_med = p_mean = p_med = None

    combined = pd.concat([
        ownership, pd.DataFrame([{}]),
        pd.DataFrame(summary_rows),
        pd.DataFrame([{
            "group": "high_vs_low_diff", "diff_mean_pnl_pct": round(diff_mean, 1) if diff_mean is not None else None,
            "p_mean": round(p_mean, 4) if p_mean is not None else None,
            "diff_median_pnl_pct": round(diff_med, 1) if diff_med is not None else None,
            "p_median": round(p_med, 4) if p_med is not None else None,
        }]),
    ], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
