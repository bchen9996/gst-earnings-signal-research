#!/usr/bin/env python3
# ATTENTION SPREAD TEST -- does zscore/real_cost_pct_of_spot predict
# anything raw zscore alone doesn't, on the 76-event real-quote sample
# (Live Signal Engine/QC_Validation_CleanSample_v2_76Events.csv)?
#
# NOTE ON THE SOURCE FILE: that CSV does NOT itself contain a zscore
# column (checked directly before writing this -- its columns are ticker,
# spike_week, real_cost_pct_of_spot, model_implied_cost_pct, real_pnl_pct,
# modeled_pnl_pct, real_win, modeled_win). The z-score is joined in from
# Live Signal Engine/FixedWindow_PerEvent_Canonical.csv on (ticker,
# spike_week) -- that file is this project's single authoritative source
# for z-scores (per STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md
# section 1), so this is the correct way to attach it, not a workaround.
# All 76 rows matched a canonical z-score with none dropped (verified
# before writing this script).
#
# Attention Spread := fixed_window_zscore / real_cost_pct_of_spot.
#
# THREE QUESTIONS, IN THE ORDER ASKED:
#   1. Does Attention Spread's correlation with real_pnl_pct exceed raw
#      z-score's? Also: a multiple regression with z-score AND cost BOTH
#      already in the model, to see whether Attention Spread's own
#      correlation is just a repackaging of information already in its
#      two ingredients (the more direct test of "does the ratio add
#      anything the ingredients don't already have separately").
#   2. Tercile split: top vs. bottom Attention Spread tercile, win rate +
#      median real_pnl_pct.
#   3. Circularity check: does Attention Spread mostly just track
#      real_cost_pct_of_spot (i.e., is "high Attention Spread" really just
#      "unusually cheap options, regardless of z"), via direct correlation
#      plus a rank-based decomposition of which ingredient dominates the
#      ratio's own variation.
#
# Output: Live Signal Engine/AttentionSpread_Analysis.csv (event-level,
# with Attention Spread, its rank, tercile, and both ingredients) +
# console report answering the three questions plainly.

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy import stats

sys.stdout.reconfigure(encoding="utf-8")

SAMPLE_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_v2_76Events.csv"
CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "AttentionSpread_Analysis.csv"


def corr_pair(x: pd.Series, y: pd.Series) -> tuple[float, float, float, float]:
    pr, pp = stats.pearsonr(x, y)
    sr, sp = stats.spearmanr(x, y)
    return pr, pp, sr, sp


def main():
    print("*** ATTENTION SPREAD TEST (zscore / real_cost_pct_of_spot, 76-event real-quote sample) ***\n")

    sample = pd.read_csv(SAMPLE_PATH)
    canon = pd.read_csv(CANONICAL_PATH)
    sample["spike_week"] = pd.to_datetime(sample["spike_week"])
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])

    print(f"Source sample: {SAMPLE_PATH} (n={len(sample)})")
    print("NOTE: that file has no zscore column of its own -- joined in from "
          "FixedWindow_PerEvent_Canonical.csv on (ticker, spike_week), the project's "
          "single authoritative z-score source.\n")

    df = sample.merge(canon[["ticker", "spike_week", "fixed_window_zscore"]],
                       on=["ticker", "spike_week"], how="left")
    n_unmatched = df["fixed_window_zscore"].isna().sum()
    print(f"Unmatched rows (no canonical z-score found): {n_unmatched}")
    if n_unmatched:
        df = df.dropna(subset=["fixed_window_zscore"])
    df = df.rename(columns={"fixed_window_zscore": "zscore"})
    print(f"Usable rows: n={len(df)}\n")

    df["attention_spread"] = df["zscore"] / df["real_cost_pct_of_spot"]
    df["attention_spread_rank"] = df["attention_spread"].rank()
    df["zscore_rank"] = df["zscore"].rank()
    df["cost_rank"] = df["real_cost_pct_of_spot"].rank()

    tercile_labels = pd.qcut(df["attention_spread"], 3, labels=["low", "mid", "high"])
    df["attention_spread_tercile"] = tercile_labels

    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    # =====================================================================
    # Q1: does Attention Spread beat raw z-score as a predictor of real_pnl_pct?
    # =====================================================================
    print("=" * 78)
    print("Q1: Attention Spread vs. raw z-score as a predictor of real_pnl_pct")
    print("=" * 78 + "\n")

    as_pr, as_pp, as_sr, as_sp = corr_pair(df["attention_spread"], df["real_pnl_pct"])
    z_pr, z_pp, z_sr, z_sp = corr_pair(df["zscore"], df["real_pnl_pct"])
    cost_pr, cost_pp, cost_sr, cost_sp = corr_pair(df["real_cost_pct_of_spot"], df["real_pnl_pct"])

    print(f"Attention Spread vs. real_pnl_pct:  Pearson r={as_pr:+.3f} (p={as_pp:.3f})   "
          f"Spearman rho={as_sr:+.3f} (p={as_sp:.3f})")
    print(f"Raw z-score      vs. real_pnl_pct:  Pearson r={z_pr:+.3f} (p={z_pp:.3f})   "
          f"Spearman rho={z_sr:+.3f} (p={z_sp:.3f})")
    print(f"real_cost_pct_of_spot vs. real_pnl_pct: Pearson r={cost_pr:+.3f} (p={cost_pp:.3f})   "
          f"Spearman rho={cost_sr:+.3f} (p={cost_sp:.3f})\n")

    beats = abs(as_pr) > abs(z_pr)
    print(f"Does |r(Attention Spread, pnl)| exceed |r(z-score, pnl)|? {beats}  "
          f"({abs(as_pr):.3f} vs. {abs(z_pr):.3f})\n")

    print("--- Multiple regression: does Attention Spread add anything once z-score AND")
    print("    cost are BOTH already in the model? (the direct redundancy test) ---")
    import statsmodels.api as sm
    X_ingredients = sm.add_constant(df[["zscore", "real_cost_pct_of_spot"]])
    fit_ingredients = sm.OLS(df["real_pnl_pct"], X_ingredients).fit()
    print(f"Model A: real_pnl_pct ~ zscore + real_cost_pct_of_spot   R^2={fit_ingredients.rsquared:.4f}")
    print(f"  zscore coef={fit_ingredients.params['zscore']:+.3f} (p={fit_ingredients.pvalues['zscore']:.3f})   "
          f"cost coef={fit_ingredients.params['real_cost_pct_of_spot']:+.3f} "
          f"(p={fit_ingredients.pvalues['real_cost_pct_of_spot']:.3f})")

    X_full = sm.add_constant(df[["zscore", "real_cost_pct_of_spot", "attention_spread"]])
    fit_full = sm.OLS(df["real_pnl_pct"], X_full).fit()
    print(f"\nModel B: real_pnl_pct ~ zscore + real_cost_pct_of_spot + attention_spread   "
          f"R^2={fit_full.rsquared:.4f}")
    print(f"  attention_spread coef={fit_full.params['attention_spread']:+.3f}  "
          f"p={fit_full.pvalues['attention_spread']:.3f}")
    r2_gain = fit_full.rsquared - fit_ingredients.rsquared
    print(f"\nR^2 gain from adding Attention Spread on top of its own two ingredients: {r2_gain:+.4f}")
    adds_info = fit_full.pvalues["attention_spread"] < 0.05
    print(f"Attention Spread statistically significant AFTER controlling for zscore AND cost "
          f"separately: {adds_info}")
    if not adds_info:
        print("  -> Attention Spread does NOT add information beyond what zscore and cost already")
        print("     supply separately -- it is a repackaging of the same two variables, not a new signal.")
    else:
        print("  -> Attention Spread carries information beyond zscore and cost taken separately.")
    print()

    # =====================================================================
    # Q2: tercile split
    # =====================================================================
    print("=" * 78)
    print("Q2: Attention Spread tercile split -- win rate and median return")
    print("=" * 78 + "\n")

    tercile_stats = df.groupby("attention_spread_tercile", observed=True).agg(
        n=("real_pnl_pct", "size"),
        win_rate_pct=("real_win", lambda s: s.mean() * 100),
        median_pnl_pct=("real_pnl_pct", "median"),
        mean_pnl_pct=("real_pnl_pct", "mean"),
        mean_attention_spread=("attention_spread", "mean"),
        mean_zscore=("zscore", "mean"),
        mean_cost=("real_cost_pct_of_spot", "mean"),
    ).reindex(["low", "mid", "high"])
    print(tercile_stats.round(2).to_string())
    print()

    low_pnl = df.loc[df["attention_spread_tercile"] == "low", "real_pnl_pct"]
    high_pnl = df.loc[df["attention_spread_tercile"] == "high", "real_pnl_pct"]
    u_stat, u_p = stats.mannwhitneyu(high_pnl, low_pnl, alternative="two-sided")
    print(f"High vs. low tercile real_pnl_pct: Mann-Whitney U p={u_p:.3f} "
          f"({'significant' if u_p < 0.05 else 'not significant'} at 95%)")

    # Same split done on raw z-score terciles, for direct comparison of separating power
    z_tercile = pd.qcut(df["zscore"], 3, labels=["low", "mid", "high"])
    z_low_pnl = df.loc[z_tercile == "low", "real_pnl_pct"]
    z_high_pnl = df.loc[z_tercile == "high", "real_pnl_pct"]
    zu_stat, zu_p = stats.mannwhitneyu(z_high_pnl, z_low_pnl, alternative="two-sided")
    print(f"(For comparison) High vs. low RAW Z-SCORE tercile real_pnl_pct: Mann-Whitney U p={zu_p:.3f} "
          f"({'significant' if zu_p < 0.05 else 'not significant'} at 95%)\n")

    # =====================================================================
    # Q3: circularity check
    # =====================================================================
    print("=" * 78)
    print("Q3: circularity -- is 'high Attention Spread' mostly just 'unusually cheap options'?")
    print("=" * 78 + "\n")

    as_cost_pr, as_cost_pp, as_cost_sr, as_cost_sp = corr_pair(df["attention_spread"], df["real_cost_pct_of_spot"])
    as_z_pr, as_z_pp, as_z_sr, as_z_sp = corr_pair(df["attention_spread"], df["zscore"])
    print(f"Attention Spread vs. real_cost_pct_of_spot (its own denominator): "
          f"Pearson r={as_cost_pr:+.3f}   Spearman rho={as_cost_sr:+.3f}")
    print(f"Attention Spread vs. zscore (its own numerator):                 "
          f"Pearson r={as_z_pr:+.3f}   Spearman rho={as_z_sr:+.3f}\n")

    cv_z = df["zscore"].std() / df["zscore"].mean()
    cv_cost = df["real_cost_pct_of_spot"].std() / df["real_cost_pct_of_spot"].mean()
    print(f"Coefficient of variation, zscore: {cv_z:.3f}")
    print(f"Coefficient of variation, real_cost_pct_of_spot: {cv_cost:.3f}")
    dominant = "z-score" if cv_z > cv_cost else "cost"
    print(f"-> The ingredient with MORE relative variation ({dominant}) will mechanically dominate "
          f"the ratio's own variation.\n")

    rank_dom = "cost" if abs(as_cost_sr) > abs(as_z_sr) else "z-score"
    print(f"Which ingredient's RANK better predicts Attention Spread's own rank? "
          f"|rho vs cost|={abs(as_cost_sr):.3f} vs. |rho vs z|={abs(as_z_sr):.3f} -> dominated by {rank_dom}")

    circular = abs(as_cost_sr) > 0.5 and abs(as_cost_sr) > abs(as_z_sr)
    print(f"\nCIRCULARITY VERDICT: {'YES -- Attention Spread is mostly tracking cost variation, not attention' if circular else 'NO -- Attention Spread is not dominated by cost alone'}\n")

    # =====================================================================
    # PLAIN VERDICT
    # =====================================================================
    print("=" * 78)
    print("PLAIN VERDICT")
    print("=" * 78 + "\n")
    if adds_info and not circular:
        print("Attention Spread OUTPERFORMS raw z-score: it adds real information beyond its own")
        print("ingredients and is not just a repackaging of cost variation.")
    elif circular:
        print("Attention Spread is largely REDUNDANT/CIRCULAR: its variation is dominated by")
        print(f"real_cost_pct_of_spot (rank correlation {as_cost_sr:+.3f}), not by z-score. A 'high")
        print("Attention Spread' event is mostly just a cheap-options event, not a high-attention one.")
    else:
        print("Attention Spread does NOT clearly outperform raw z-score: once z-score and cost are")
        print("both already in the model, the ratio adds no statistically significant information")
        print("(Model B's attention_spread coefficient is not significant) -- it is a repackaging of")
        print("information already available in its two ingredients separately, not a new signal.")


if __name__ == "__main__":
    main()
