#!/usr/bin/env python3
# RECALIBRATE NEAR_EARNINGS_IV_MARKUP -- v2, using the larger 76-event clean
# QC validation sample (up from 37) to check whether the first-pass
# recalibration (new_markup=3.6516, see CHANGELOG.md and
# GST_Recalibrate_IV_Markup.py) holds up with roughly double the real-quote
# data, or moves meaningfully.
#
# Same method as the v1 script, just re-parameterized for the larger sample:
#   1. Split the 76 events into calibration (55) / holdout (21), fixed
#      seed=42 (same seed as v1, for consistency of method -- the sample
#      itself is different/larger, not the split logic).
#   2. correction_factor = mean(real_cost_pct_of_spot) /
#      mean(model_implied_cost_pct) on the CALIBRATION subset only.
#      new_markup = OLD_MARKUP * correction_factor.
#   3. Validate out-of-sample on the untouched HOLDOUT subset (same linear-
#      approximation caveat as v1: the exported file only has the
#      already-computed model cost, not each event's T/sigma, so holdout
#      validation rescales the old model cost by correction_factor rather
#      than re-inverting Black-Scholes per event).
#   4. If validated, exact re-derivation (real T/sigma per event, via
#      price_event()) against the full 152-event canonical population.
#   5. Three-way comparison: ORIGINAL (markup=1.2398) vs. v1 RECALIBRATED
#      (markup=3.6516, n=37) vs. v2 RECALIBRATED (this run, n=76) -- to see
#      how much the estimate moves with a larger real-quote sample.
#
# Output: Live Signal Engine/FixedWindow_PerEvent_RecalibratedPricing_v2.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

VALIDATION_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_v2_76Events.csv"
CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_RecalibratedPricing_v2.csv"

N_CALIBRATION = 55
N_HOLDOUT = 21
SPLIT_SEED = 42

V1_MARKUP = 3.6516   # first-pass recalibration, n=37 (see GST_Recalibrate_IV_Markup.py / CHANGELOG.md)


def recompute_full_backtest(qualifying, daily_cache, markup):
    rows = []
    for r in qualifying.itertuples(index=False):
        ticker = r.ticker
        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            rows.append({"ticker": ticker, "spike_week": r.spike_week, "exit_date": r.exit_date,
                         "pnl_pct": None, "win": None})
            continue
        priced = base.price_event(daily, ret_col, r.spike_week, markup)
        if priced is None:
            rows.append({"ticker": ticker, "spike_week": r.spike_week, "exit_date": r.exit_date,
                         "pnl_pct": None, "win": None})
            continue
        rows.append({"ticker": ticker, "spike_week": r.spike_week, "exit_date": r.exit_date,
                     "pnl_pct": round(priced["pnl_pct"], 2), "win": priced["win"]})
    return pd.DataFrame(rows)


def main():
    print("*** RECALIBRATE NEAR_EARNINGS_IV_MARKUP v2 -- 76-event clean sample ***\n")

    val = pd.read_csv(VALIDATION_PATH)
    assert len(val) == 76, f"expected 76 clean events, got {len(val)}"
    print(f"Loaded {len(val)} clean validation events (v2, up from 37 in v1)\n")

    OLD_MARKUP = base.load_calibrated_near_earnings_markup()

    rng = np.random.RandomState(SPLIT_SEED)
    idx = rng.permutation(len(val))
    calib = val.iloc[idx[:N_CALIBRATION]].copy()
    holdout = val.iloc[idx[N_CALIBRATION:N_CALIBRATION + N_HOLDOUT]].copy()
    print(f"Split (seed={SPLIT_SEED}): calibration n={len(calib)}, holdout n={len(holdout)}\n")

    correction_factor = calib["real_cost_pct_of_spot"].mean() / calib["model_implied_cost_pct"].mean()
    new_markup = OLD_MARKUP * correction_factor
    print(f"Calibration subset: mean real_cost_pct_of_spot={calib['real_cost_pct_of_spot'].mean():.3f}, "
          f"mean model_implied_cost_pct={calib['model_implied_cost_pct'].mean():.3f}")
    print(f"Correction factor = {correction_factor:.4f}")
    print(f"OLD markup = {OLD_MARKUP:.4f}  ->  NEW markup (v2) = {new_markup:.4f}   "
          f"(v1 markup was {V1_MARKUP:.4f})\n")

    holdout = holdout.copy()
    holdout["old_model_cost"] = holdout["model_implied_cost_pct"]
    holdout["new_model_cost_approx"] = holdout["model_implied_cost_pct"] * correction_factor
    holdout["old_abs_err"] = (holdout["old_model_cost"] - holdout["real_cost_pct_of_spot"]).abs()
    holdout["new_abs_err"] = (holdout["new_model_cost_approx"] - holdout["real_cost_pct_of_spot"]).abs()

    old_median_err = holdout["old_abs_err"].median()
    new_median_err = holdout["new_abs_err"].median()
    old_mean_err = holdout["old_abs_err"].mean()
    new_mean_err = holdout["new_abs_err"].mean()
    old_bias = (holdout["old_model_cost"] - holdout["real_cost_pct_of_spot"]).mean()
    new_bias = (holdout["new_model_cost_approx"] - holdout["real_cost_pct_of_spot"]).mean()
    n_improved = (holdout["new_abs_err"] < holdout["old_abs_err"]).sum()

    print("=== HOLDOUT VALIDATION (out-of-sample, n=%d) ===" % len(holdout))
    print(f"Median abs pricing error:  OLD={old_median_err:.3f}   NEW={new_median_err:.3f}")
    print(f"Mean abs pricing error:    OLD={old_mean_err:.3f}   NEW={new_mean_err:.3f}")
    print(f"Mean signed bias:          OLD={old_bias:+.3f}   NEW={new_bias:+.3f}")
    print(f"Events improved: {n_improved}/{len(holdout)}\n")

    validated = new_median_err < old_median_err
    if not validated:
        print("*** VALIDATION FAILED: new markup does NOT reduce holdout error. Stopping. ***")
        return

    print("*** VALIDATED: new markup reduces holdout error. Proceeding to full 152-event recompute. ***\n")

    canonical = pd.read_csv(CANONICAL_PATH)
    canonical["spike_week"] = pd.to_datetime(canonical["spike_week"])
    canonical["entry_date"] = pd.to_datetime(canonical["entry_date"])
    canonical["exit_date"] = pd.to_datetime(canonical["exit_date"])
    qualifying = canonical[(canonical["qualifies_z5"] == True) & (canonical["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Recomputing pricing for {len(qualifying)} qualifying canonical events -- "
          f"ORIGINAL, v1 (markup={V1_MARKUP}), and v2 (markup={new_markup:.4f})...\n")

    daily_cache = {}

    # ORIGINAL pricing already stored in the canonical file -- reuse directly.
    orig_df = qualifying[["ticker", "spike_week", "exit_date", "pnl_pct", "win"]].copy()

    v1_df = recompute_full_backtest(qualifying, daily_cache, V1_MARKUP)
    v2_df = recompute_full_backtest(qualifying, daily_cache, new_markup)

    merged = qualifying[["ticker", "spike_week", "entry_date", "exit_date", "fixed_window_zscore"]].copy()
    merged["original_pnl_pct"] = qualifying["pnl_pct"].to_numpy()
    merged["original_win"] = qualifying["win"].to_numpy()
    merged["v1_recalibrated_pnl_pct"] = v1_df["pnl_pct"].to_numpy()
    merged["v1_recalibrated_win"] = v1_df["win"].to_numpy()
    merged["v2_recalibrated_pnl_pct"] = v2_df["pnl_pct"].to_numpy()
    merged["v2_recalibrated_win"] = v2_df["win"].to_numpy()
    merged["spike_week"] = merged["spike_week"].dt.date
    merged["entry_date"] = merged["entry_date"].dt.date
    merged["exit_date"] = merged["exit_date"].dt.date

    merged.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    def stats_for(pnl_col, win_col, markup_label):
        sub = merged[merged[pnl_col].notna()].copy()
        sub_df = sub.rename(columns={pnl_col: "pnl_pct", win_col: "win"})
        sub_df["exit_date"] = pd.to_datetime(sub_df["exit_date"])
        return base.compute_win_median_sharpe(sub_df), markup_label

    orig_stats, _ = stats_for("original_pnl_pct", "original_win", "ORIGINAL")
    v1_stats, _ = stats_for("v1_recalibrated_pnl_pct", "v1_recalibrated_win", "V1")
    v2_stats, _ = stats_for("v2_recalibrated_pnl_pct", "v2_recalibrated_win", "V2")

    print("=== THREE-WAY COMPARISON: full 152-event canonical backtest ===")
    print(f"ORIGINAL      (markup={OLD_MARKUP:.4f}, uncorrected):        "
          f"n={orig_stats['n']}   win={orig_stats['win_rate_pct']}%   median={orig_stats['median_pnl_pct']}%   "
          f"Sharpe={orig_stats['sharpe_annualized']}   maxDD={orig_stats['max_drawdown_pct']}%")
    print(f"V1 RECALIBRATED (markup={V1_MARKUP:.4f}, n=37 real quotes):  "
          f"n={v1_stats['n']}   win={v1_stats['win_rate_pct']}%   median={v1_stats['median_pnl_pct']}%   "
          f"Sharpe={v1_stats['sharpe_annualized']}   maxDD={v1_stats['max_drawdown_pct']}%")
    print(f"V2 RECALIBRATED (markup={new_markup:.4f}, n=76 real quotes): "
          f"n={v2_stats['n']}   win={v2_stats['win_rate_pct']}%   median={v2_stats['median_pnl_pct']}%   "
          f"Sharpe={v2_stats['sharpe_annualized']}   maxDD={v2_stats['max_drawdown_pct']}%")

    print(f"\nMarkup estimate movement: v1={V1_MARKUP:.4f} -> v2={new_markup:.4f} "
          f"({(new_markup/V1_MARKUP - 1)*100:+.1f}% change with ~2x the real-quote sample size)")

    return {
        "correction_factor": correction_factor, "new_markup": new_markup,
        "old_median_err": old_median_err, "new_median_err": new_median_err,
        "old_mean_err": old_mean_err, "new_mean_err": new_mean_err,
        "old_bias": old_bias, "new_bias": new_bias, "n_improved": int(n_improved), "n_holdout": len(holdout),
        "orig_stats": orig_stats, "v1_stats": v1_stats, "v2_stats": v2_stats,
    }


if __name__ == "__main__":
    main()
