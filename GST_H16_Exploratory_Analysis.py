#!/usr/bin/env python3
# HYPOTHESIS #16 -- EXPLORATORY ONLY. See
# Live Signal Engine/H16_Exploratory_PreRegistration.md, locked BEFORE
# this script was written. The 152-event canonical population is fully
# saturated by prior tests -- this analysis is descriptive/hypothesis-
# generating, not confirmatory, regardless of what the numbers below say.
#
# RV = realized_move_pct, reused verbatim (not redefined) from
# GST_VolatilitySurprise_Analysis.py: |cumulative stock return,
# entry_date -> exit_date| x 100, via
# base.load_daily_excess / base.nearest_trading_day_on_or_before /
# base.cumulative_return (GST_FixedWindow_PerEvent_Canonical.py).
#
# IV proxy = real_cost_pct_of_spot, reused from four existing real-quote
# pulls -- NO NEW OPTION-QUOTE PULL IS PERFORMED:
#   Pass 1 (37), Pass 2 (76), H5 OOS (45+31, clean rows only),
#   Attention Spread OOS (45, clean rows only).
# Duplicated (ticker, spike_week) across sources are de-duplicated to one
# row, not double-counted.
#
# market_cap: not previously captured anywhere in this project for these
# tickers (checked directly before writing this) -- pulled ONCE per
# unique ticker via yfinance fast_info/info, a current snapshot, not
# point-in-time-per-event (disclosed simplification, same one
# GST_MatchedControlGroup_CanonicalRecompute.py already used).
#
# sector: Live Signal Engine/AllTickers_Sectors.csv, same source used
# throughout this project.
#
# Output: Live Signal Engine/H16_Exploratory_Analysis_Data.csv (per-event
# regression inputs) + console report (t-stat/p-value on GST, incremental
# R^2 -- nothing else, no PASS/WEAK/FAIL, per the locked pre-registration).

from __future__ import annotations
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf
import statsmodels.api as sm

import GST_FixedWindow_PerEvent_Canonical as base

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "H16_Exploratory_Analysis_Data.csv"

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6


def fetch_market_cap(ticker: str) -> float | None:
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        cap = tk.fast_info.get("marketCap") if hasattr(tk, "fast_info") else None
        if not cap:
            cap = tk.info.get("marketCap")
        return float(cap) if cap else None
    except Exception as e:
        print(f"  [{ticker}] market cap fetch failed: {e}")
        return None


def main():
    print("*** HYPOTHESIS #16 -- EXPLORATORY ONLY (see H16_Exploratory_PreRegistration.md) ***\n")

    sources = {
        "Pass1_37": Path("Live Signal Engine") / "QC_Validation_CleanSample_37Events.csv",
        "Pass2_76": Path("Live Signal Engine") / "QC_Validation_CleanSample_v2_76Events.csv",
        "H5_orig": Path("Live Signal Engine") / "QC_H5_OutOfSample_RawResults.csv",
        "H5_supp": Path("Live Signal Engine") / "QC_H5_OutOfSample_Supplemental_RawResults.csv",
        "AttnSpread_OOS": Path("Live Signal Engine") / "QC_AttentionSpread_OOS_RawResults.csv",
    }

    frames = []
    for name, path in sources.items():
        df = pd.read_csv(path)
        if "corrupted" in df.columns:
            df = df[(df["corrupted"] == False) & df["real_cost_pct_of_spot"].notna()].copy()  # noqa: E712
        else:
            df = df[df["real_cost_pct_of_spot"].notna()].copy()
        df["spike_week"] = pd.to_datetime(df["spike_week"])
        df["source"] = name
        frames.append(df[["ticker", "spike_week", "real_cost_pct_of_spot", "source"]])
        print(f"  {name}: {len(df)} clean rows with real_cost_pct_of_spot")

    combined = pd.concat(frames, ignore_index=True)
    print(f"\nTotal rows across all 4 sources before dedup: {len(combined)}")

    dup_mask = combined.duplicated(subset=["ticker", "spike_week"], keep=False)
    n_dup_rows = int(dup_mask.sum())
    n_unique_dup_events = combined.loc[dup_mask, ["ticker", "spike_week"]].drop_duplicates().shape[0]
    print(f"Rows involved in a cross-source duplicate (ticker, spike_week): {n_dup_rows} "
          f"({n_unique_dup_events} unique events appearing more than once)")

    deduped = combined.drop_duplicates(subset=["ticker", "spike_week"], keep="first").copy()
    print(f"After de-duplication (kept first occurrence): n={len(deduped)}\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    zmap = canon.set_index(["ticker", "spike_week"])["fixed_window_zscore"].to_dict()
    deduped["zscore"] = deduped.apply(lambda r: zmap.get((r["ticker"], r["spike_week"])), axis=1)
    n_no_z = deduped["zscore"].isna().sum()
    print(f"Events with no canonical z-score match: {n_no_z}")
    deduped = deduped.dropna(subset=["zscore"])

    print("\nComputing realized_move_pct (RV) from local daily excess-return data "
          "-- same helper functions as GST_VolatilitySurprise_Analysis.py...")
    daily_cache = {}
    rv_vals, notes = [], []
    for r in deduped.itertuples(index=False):
        ticker, anchor = r.ticker, r.spike_week
        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            rv_vals.append(None); notes.append("no local daily data")
            continue
        entry_date = base.nearest_trading_day_on_or_before(daily, anchor + pd.Timedelta(days=ENTRY_OFFSET_DAYS))
        exit_date = base.nearest_trading_day_on_or_before(daily, anchor + pd.Timedelta(days=EXIT_OFFSET_DAYS))
        if entry_date is None or exit_date is None or exit_date <= entry_date:
            rv_vals.append(None); notes.append("could not resolve entry/exit")
            continue
        cum_ret = base.cumulative_return(daily, ret_col, entry_date, exit_date)
        if cum_ret is None:
            rv_vals.append(None); notes.append("no return data over window")
            continue
        rv_vals.append(abs(cum_ret) * 100)
        notes.append("")
    deduped["realized_move_pct"] = rv_vals
    deduped["rv_note"] = notes
    n_no_rv = deduped["realized_move_pct"].isna().sum()
    print(f"Events with no resolvable RV: {n_no_rv}")
    deduped = deduped.dropna(subset=["realized_move_pct"])
    print(f"After RV resolution: n={len(deduped)}\n")

    sector_df = pd.read_csv(SECTOR_PATH)
    sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))
    deduped["sector"] = deduped["ticker"].map(sector_map)
    n_no_sector = deduped["sector"].isna().sum()
    print(f"Events with no sector mapping: {n_no_sector}")
    deduped = deduped.dropna(subset=["sector"])

    unique_tickers = sorted(deduped["ticker"].unique())
    print(f"\nFetching market cap for {len(unique_tickers)} unique tickers (current snapshot, one pull each)...")
    cap_cache = {}
    for t in unique_tickers:
        cap_cache[t] = fetch_market_cap(t)
        time.sleep(0.5)
    deduped["market_cap"] = deduped["ticker"].map(cap_cache)
    n_no_cap = deduped["market_cap"].isna().sum()
    print(f"Events with no market cap resolved: {n_no_cap}")
    deduped = deduped.dropna(subset=["market_cap"])
    deduped["log_market_cap"] = np.log(deduped["market_cap"])

    print(f"\nFINAL regression sample: n={len(deduped)} (from {len(unique_tickers)} tickers)\n")

    deduped.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    sector_dummies = pd.get_dummies(deduped["sector"], prefix="sector", drop_first=True).astype(float)
    X_base = pd.concat([deduped[["real_cost_pct_of_spot", "log_market_cap"]], sector_dummies], axis=1)
    X_full = pd.concat([X_base, deduped[["zscore"]]], axis=1)

    model_base = sm.OLS(deduped["realized_move_pct"], sm.add_constant(X_base)).fit()
    model_full = sm.OLS(deduped["realized_move_pct"], sm.add_constant(X_full)).fit()

    print("=" * 78)
    print("HYPOTHESIS #16 -- EXPLORATORY RESULT (not confirmatory -- see pre-registration)")
    print("=" * 78 + "\n")
    print(f"n = {len(deduped)}")
    print(f"Model without GST (RV ~ IV + log_cap + sector):  R^2 = {model_base.rsquared:.4f}")
    print(f"Model with GST    (RV ~ IV + GST + log_cap + sector): R^2 = {model_full.rsquared:.4f}")
    incremental_r2 = model_full.rsquared - model_base.rsquared
    print(f"\nIncremental R^2 from adding GST z-score: {incremental_r2:+.4f}")
    print(f"\nGST z-score coefficient: {model_full.params['zscore']:+.4f}")
    print(f"GST t-statistic: {model_full.tvalues['zscore']:.3f}")
    print(f"GST p-value: {model_full.pvalues['zscore']:.4f}")
    print(f"\nIV (real_cost_pct_of_spot) coefficient: {model_full.params['real_cost_pct_of_spot']:+.4f}  "
          f"p={model_full.pvalues['real_cost_pct_of_spot']:.4f}")
    print(f"log(market cap) coefficient: {model_full.params['log_market_cap']:+.4f}  "
          f"p={model_full.pvalues['log_market_cap']:.4f}")

    print("\n*** EXPLORATORY ONLY. No PASS/WEAK/FAIL bucket. This population is fully")
    print("*** saturated by prior tests -- no held-out data exists. A promising result")
    print("*** here is not evidence; it requires an independent confirmatory test on")
    print("*** fresh forward data before being treated as real. ***")


if __name__ == "__main__":
    main()
