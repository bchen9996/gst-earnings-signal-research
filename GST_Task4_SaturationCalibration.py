#!/usr/bin/env python3
# TASK 4 — Attention saturation and forecast calibration. All on-disk
# data, no new pulls: reuses Straddle Profitability Test (2021-2025
# 51Ticker)/results.csv (same source as the original P(win|z) calibration
# curve task), restricted to near_earnings=True events.
#
# (a) Extends the isotonic/logistic P(win|z) curve to z = 5,6,7,8,9,10,
#     12,15,20 to see whether the relationship flattens (saturates) or
#     keeps climbing at high z. Empirical (raw, unsmoothed) bucket win
#     rates are reported alongside the fitted curves for z>=15/20, since
#     those buckets are thin and a smoothed curve alone could mask that.
#
# (b) Brier score: predicted probability = isotonic-regression P(win|z)
#     evaluated at each event's own z, outcome = actual win/loss. Reported
#     alongside the logistic-regression Brier score for comparison, plus a
#     reliability diagram (predicted-probability decile bins vs observed
#     win rate in each bin).
#
# *** IN-SAMPLE DISCLOSURE ***
# Both the isotonic and logistic models are FIT and EVALUATED on the same
# n=209 near-earnings event set (same as the original calibration-curve
# task, which was also in-sample) — no held-out split. Brier scores here
# measure GOODNESS OF FIT to this data, not out-of-sample forecast skill;
# isotonic regression in particular is flexible enough that its in-sample
# Brier score is optimistically biased relative to genuine forecasting
# performance. The logistic score, with only 2 free parameters, is far
# less prone to this and is the more trustworthy of the two here.
#
# Output: Live Signal Engine/Saturation_Calibration_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

sys.stdout.reconfigure(encoding="utf-8")

RESULTS_PATH = Path("Straddle Profitability Test (2021-2025 51Ticker)") / "results.csv"
OUT_PATH = Path("Live Signal Engine") / "Saturation_Calibration_Results.csv"

WIN_COL = "end_of_spike_week_win"
TABLE_Z_VALUES = [5, 6, 7, 8, 9, 10, 12, 15, 20]
N_RELIABILITY_BINS = 5


def main():
    print("*** TASK 4: Attention saturation and forecast calibration ***\n")

    results = pd.read_csv(RESULTS_PATH)
    near = results[(results["near_earnings"] == True) & (results[WIN_COL].notna())].copy()  # noqa: E712
    z = near["zscore"].to_numpy(dtype=float)
    y = near[WIN_COL].astype(int).to_numpy()
    n = len(near)
    print(f"n={n}, z range [{z.min():.2f}, {z.max():.2f}]\n")

    iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip")
    iso.fit(z, y)
    logit = LogisticRegression()
    logit.fit(z.reshape(-1, 1), y)

    print("=== (a) SATURATION: P(win|z) at higher z, fitted curves + raw empirical bucket ===")
    rows_a = []
    for zv in TABLE_Z_VALUES:
        p_iso = float(iso.predict([zv])[0])
        p_logit = float(logit.predict_proba([[zv]])[0, 1])
        # empirical: events within +-1.5 of zv (or, for the top bucket, z>=zv)
        if zv >= 15:
            bucket = near[near["zscore"] >= zv]
            bucket_label = f">= {zv}"
        else:
            bucket = near[(near["zscore"] >= zv - 1.5) & (near["zscore"] < zv + 1.5)]
            bucket_label = f"[{zv-1.5:g}, {zv+1.5:g})"
        n_bucket = len(bucket)
        empirical_wr = bucket[WIN_COL].mean() * 100 if n_bucket > 0 else None
        wr_str = f"win={empirical_wr:.1f}%" if empirical_wr is not None else "win=n/a"
        print(f"  z={zv:<3} P(win)_isotonic={p_iso:.3f}  P(win)_logistic={p_logit:.3f}  "
              f"empirical bucket {bucket_label}: n={n_bucket:<3} {wr_str}")
        rows_a.append({"z": zv, "p_win_isotonic": round(p_iso, 4), "p_win_logistic": round(p_logit, 4),
                        "empirical_bucket": bucket_label, "empirical_n": n_bucket,
                        "empirical_win_rate_pct": round(empirical_wr, 1) if empirical_wr is not None else None})

    # Saturation check: does the isotonic curve's slope flatten at high z?
    z_grid = np.linspace(5, z.max(), 500)
    iso_grid = iso.predict(z_grid)
    slope_5_10 = (iso.predict([10])[0] - iso.predict([5])[0]) / 5
    top_z = min(z.max(), 20)
    slope_15_top = (iso.predict([top_z])[0] - iso.predict([15])[0]) / (top_z - 15) if top_z > 15 else None
    print(f"\n  Isotonic slope, z=5->10: {slope_5_10:+.4f} P(win) per unit z")
    if slope_15_top is not None:
        print(f"  Isotonic slope, z=15->{top_z:.0f}: {slope_15_top:+.4f} P(win) per unit z")
        flattens = abs(slope_15_top) < abs(slope_5_10) * 0.5
        print(f"  Relationship {'FLATTENS (saturates)' if flattens else 'KEEPS IMPROVING'} at high z "
              f"(slope ratio: {slope_15_top/slope_5_10:.2f}x the z=5-10 slope)" if slope_5_10 != 0 else "")
    print()

    print("=== (b) BRIER SCORE + RELIABILITY DIAGRAM ===")
    p_iso_events = iso.predict(z)
    p_logit_events = logit.predict_proba(z.reshape(-1, 1))[:, 1]

    brier_iso = float(np.mean((p_iso_events - y) ** 2))
    brier_logit = float(np.mean((p_logit_events - y) ** 2))
    brier_baseline = float(np.mean((y.mean() - y) ** 2))  # naive "always predict base rate"
    print(f"Brier score (isotonic, in-sample):  {brier_iso:.4f}")
    print(f"Brier score (logistic, in-sample):  {brier_logit:.4f}")
    print(f"Brier score (naive base-rate-only baseline): {brier_baseline:.4f}")
    print(f"Skill vs baseline: isotonic {(1-brier_iso/brier_baseline)*100:+.1f}%  "
          f"logistic {(1-brier_logit/brier_baseline)*100:+.1f}%\n")

    print(f"Reliability diagram ({N_RELIABILITY_BINS} bins by predicted probability, isotonic model):")
    near = near.copy()
    near["p_pred"] = p_iso_events
    near["bin"] = pd.qcut(near["p_pred"], N_RELIABILITY_BINS, duplicates="drop")
    reliability = near.groupby("bin", observed=True).agg(
        n=("p_pred", "count"), mean_predicted=("p_pred", "mean"), observed_win_rate=(WIN_COL, "mean")
    ).reset_index()
    reliability["observed_win_rate"] = reliability["observed_win_rate"] * 100
    reliability["mean_predicted_pct"] = reliability["mean_predicted"] * 100
    reliability["calibration_gap_pt"] = reliability["observed_win_rate"] - reliability["mean_predicted_pct"]
    for _, r in reliability.iterrows():
        print(f"  bin {r['bin']}: n={int(r['n']):<3} mean_predicted={r['mean_predicted_pct']:.1f}%  "
              f"observed={r['observed_win_rate']:.1f}%  gap={r['calibration_gap_pt']:+.1f}pt")

    mean_abs_gap = reliability["calibration_gap_pt"].abs().mean()
    print(f"\nMean absolute calibration gap across bins: {mean_abs_gap:.1f}pt")
    print(f"Calibration quality: {'GOOD' if mean_abs_gap < 5 else 'MODERATE' if mean_abs_gap < 10 else 'POOR'}")

    table_a = pd.DataFrame(rows_a)
    reliability_out = reliability[["bin", "n", "mean_predicted_pct", "observed_win_rate", "calibration_gap_pt"]].copy()
    reliability_out["bin"] = reliability_out["bin"].astype(str)
    brier_summary = pd.DataFrame([{
        "brier_isotonic": round(brier_iso, 4), "brier_logistic": round(brier_logit, 4),
        "brier_baseline": round(brier_baseline, 4), "mean_abs_calibration_gap_pt": round(mean_abs_gap, 2),
        "n_events": n,
    }])

    combined = pd.concat([table_a, pd.DataFrame([{}]), brier_summary, pd.DataFrame([{}]), reliability_out],
                          ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
