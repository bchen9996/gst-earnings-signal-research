#!/usr/bin/env python3
# RECALIBRATE NEAR_EARNINGS_IV_MARKUP against real QuantConnect option
# quotes. The current constant (1.2398) was calibrated from
# iv_calibration_buckets.csv (a different, purely historical-return-based
# source, see Earnings Clustering Test/), never against real quoted option
# prices. This is the first check of that constant against genuine market
# data (37 clean events from the QC AlgoSeek validation, NFLX 2025-01-19
# excluded as corrupted -- see CHANGELOG.md).
#
# METHOD:
#   1. Split the 37 events into a calibration subset (25) and a holdout
#      subset (12), fixed seed=42 (np.random.RandomState), so the split is
#      reproducible, not cherry-picked.
#   2. Derive correction_factor = mean(real_cost_pct_of_spot) /
#      mean(model_implied_cost_pct) on the CALIBRATION subset only -- i.e.
#      the factor that makes the model's AVERAGE cost estimate match the
#      real market average, per the exact framing requested. new_markup =
#      NEAR_EARNINGS_IV_MARKUP * correction_factor.
#   3. VALIDATE out-of-sample on the untouched HOLDOUT subset: since
#      model_implied_cost_pct = bs_straddle_price(100,100,T,r,
#      sigma_realized*markup)*COST_LOADING, and an ATM straddle's price is
#      approximately LINEAR in implied vol for short-dated options near the
#      money (the Brenner-Subrahmanyam approximation: straddle price ~=
#      const * S * sigma * sqrt(T), which holds well for the 4-6 day
#      holding period used throughout this project), rescaling markup by
#      correction_factor is approximated as rescaling the already-computed
#      model cost by the same factor. This is a disclosed approximation --
#      the exported validation file only contains already-computed
#      model_implied_cost_pct, not each event's underlying T/sigma, so an
#      exact Black-Scholes re-inversion per holdout event isn't possible
#      from this data; re-running with real T/sigma inputs would refine
#      this further but is not expected to change the conclusion given how
#      close the linear approximation is at these short tenors.
#   4. Only if the new markup measurably reduces holdout error does this
#      proceed to recompute the full 152-event canonical backtest with the
#      new markup (this time with an EXACT re-derivation, not the linear
#      approximation -- price_event() is re-run per event with real T/sigma
#      from each ticker's own daily-return history and the new markup).
#
# Output: Live Signal Engine/FixedWindow_PerEvent_RecalibratedPricing.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

VALIDATION_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_37Events.csv"
CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_RecalibratedPricing.csv"

N_CALIBRATION = 25
N_HOLDOUT = 12
SPLIT_SEED = 42


def main():
    print("*** RECALIBRATE NEAR_EARNINGS_IV_MARKUP against real QC option quotes ***\n")

    val = pd.read_csv(VALIDATION_PATH)
    assert len(val) == 37, f"expected 37 clean events, got {len(val)}"
    print(f"Loaded {len(val)} clean validation events\n")

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
    print(f"OLD markup = {OLD_MARKUP:.4f}  ->  NEW markup = {new_markup:.4f}\n")

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
        print("*** VALIDATION FAILED: new markup does NOT reduce holdout error. Stopping -- "
              "not applying to the 152-event backtest. ***")
        return

    print("*** VALIDATED: new markup reduces holdout error. Proceeding to full 152-event recompute. ***\n")

    markup_for_pricing = new_markup  # exact re-derivation below, not the linear approximation used for holdout validation

    canonical = pd.read_csv(CANONICAL_PATH)
    canonical["spike_week"] = pd.to_datetime(canonical["spike_week"])
    canonical["entry_date"] = pd.to_datetime(canonical["entry_date"])
    canonical["exit_date"] = pd.to_datetime(canonical["exit_date"])
    qualifying = canonical[(canonical["qualifies_z5"] == True) & (canonical["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Recomputing pricing for {len(qualifying)} qualifying canonical events with NEW markup={new_markup:.4f}...\n")

    daily_cache = {}
    rows = []
    for r in qualifying.itertuples(index=False):
        ticker = r.ticker
        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"

        row = {"ticker": ticker, "spike_week": r.spike_week.date(),
               "entry_date": r.entry_date.date(), "exit_date": r.exit_date.date(),
               "fixed_window_zscore": r.fixed_window_zscore,
               "original_pnl_pct": r.pnl_pct, "original_win": r.win,
               "recalibrated_pnl_pct": None, "recalibrated_win": None, "note": ""}

        if daily.empty or ret_col not in daily.columns:
            row["note"] = "no daily excess-return data available"
            rows.append(row)
            continue

        priced = base.price_event(daily, ret_col, r.spike_week, markup_for_pricing)
        if priced is None:
            row["note"] = "failed to reprice under new markup"
            rows.append(row)
            continue

        row["recalibrated_pnl_pct"] = round(priced["pnl_pct"], 2)
        row["recalibrated_win"] = priced["win"]
        rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    orig_priced = result_df[result_df["original_pnl_pct"].notna()].copy()
    orig_priced["exit_date"] = pd.to_datetime(orig_priced["exit_date"])
    orig_stats_df = orig_priced.rename(columns={"original_pnl_pct": "pnl_pct", "original_win": "win"})
    orig_stats = base.compute_win_median_sharpe(orig_stats_df)

    recal_priced = result_df[result_df["recalibrated_pnl_pct"].notna()].copy()
    recal_priced["exit_date"] = pd.to_datetime(recal_priced["exit_date"])
    recal_stats_df = recal_priced.rename(columns={"recalibrated_pnl_pct": "pnl_pct", "recalibrated_win": "win"})
    recal_stats = base.compute_win_median_sharpe(recal_stats_df)

    print("=== BEFORE vs AFTER: full canonical backtest ===")
    print(f"ORIGINAL (markup={OLD_MARKUP:.4f}):      n={orig_stats['n']}   win={orig_stats['win_rate_pct']}%   "
          f"median={orig_stats['median_pnl_pct']}%   Sharpe={orig_stats['sharpe_annualized']}   "
          f"maxDD={orig_stats['max_drawdown_pct']}%")
    print(f"RECALIBRATED (markup={new_markup:.4f}): n={recal_stats['n']}   win={recal_stats['win_rate_pct']}%   "
          f"median={recal_stats['median_pnl_pct']}%   Sharpe={recal_stats['sharpe_annualized']}   "
          f"maxDD={recal_stats['max_drawdown_pct']}%")

    return {
        "correction_factor": correction_factor, "new_markup": new_markup,
        "old_median_err": old_median_err, "new_median_err": new_median_err,
        "old_mean_err": old_mean_err, "new_mean_err": new_mean_err,
        "old_bias": old_bias, "new_bias": new_bias, "n_improved": int(n_improved), "n_holdout": len(holdout),
        "orig_stats": orig_stats, "recal_stats": recal_stats,
    }


if __name__ == "__main__":
    main()
