#!/usr/bin/env python3
# TASK 5 — P(win|z) calibration curve. All on-disk data, no new pulls:
# reuses Straddle Profitability Test (2021-2025 51Ticker)/results.csv
# (already-priced z>=4 events, both near_earnings and non-near_earnings).
#
# *** DATA RANGE DISCLOSURE ***
# The underlying pipeline only ever priced z>=4 events (a repeatedly-
# disclosed limitation of this project's straddle simulation, which was
# built on top of a z>=4-filtered dataset from the start). Real observed
# data starts at z=4.02. Requested table values at z=2 and z=3 are
# EXTRAPOLATED from the fitted curves, not empirically observed — flagged
# explicitly in the output, not presented as real data.
#
# (a) Isotonic regression: sklearn IsotonicRegression, monotone increasing
#     P(win) as a function of z — a nonparametric, assumption-light curve.
# (b) Logistic regression: sklearn LogisticRegression, P(win|z) — a
#     smooth parametric curve for comparison.
# Both fit twice: earnings-adjacent-only (near_earnings=True) and all
# events (regardless of near_earnings).
#
# Output: Live Signal Engine/PwinCalibrationCurve_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

sys.stdout.reconfigure(encoding="utf-8")

RESULTS_PATH = Path("Straddle Profitability Test (2021-2025 51Ticker)") / "results.csv"
OUT_PATH = Path("Live Signal Engine") / "PwinCalibrationCurve_Results.csv"

WIN_COL = "end_of_spike_week_win"
TABLE_Z_VALUES = [2, 3, 4, 5, 6, 7, 8, 10]
THRESHOLDS = [0.50, 0.60, 0.70, 0.76]
OBSERVED_MIN_Z = 4.0


def fit_and_evaluate(df: pd.DataFrame, label: str) -> pd.DataFrame:
    usable = df[df[WIN_COL].notna()].copy()
    z = usable["zscore"].to_numpy(dtype=float)
    y = usable[WIN_COL].astype(int).to_numpy()
    n = len(usable)
    print(f"\n--- {label}: n={n}, z range [{z.min():.2f}, {z.max():.2f}] ---")

    iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip")
    iso.fit(z, y)

    logit = LogisticRegression()
    logit.fit(z.reshape(-1, 1), y)

    rows = []
    for zv in TABLE_Z_VALUES:
        p_iso = float(iso.predict([zv])[0])
        p_logit = float(logit.predict_proba([[zv]])[0, 1])
        extrapolated = zv < OBSERVED_MIN_Z
        rows.append({"model_set": label, "z": zv, "p_win_isotonic": round(p_iso, 4),
                     "p_win_logistic": round(p_logit, 4), "extrapolated_beyond_observed_data": extrapolated})
        flag = "  [EXTRAPOLATED]" if extrapolated else ""
        print(f"  z={zv:<3}  P(win)_isotonic={p_iso:.3f}  P(win)_logistic={p_logit:.3f}{flag}")

    print(f"\n  Threshold crossings (z at which P(win) first reaches threshold):")
    z_grid = np.linspace(z.min(), z.max(), 2000)
    iso_grid = iso.predict(z_grid)
    logit_grid = logit.predict_proba(z_grid.reshape(-1, 1))[:, 1]
    crossing_rows = []
    for thr in THRESHOLDS:
        iso_idx = np.argmax(iso_grid >= thr) if (iso_grid >= thr).any() else None
        logit_idx = np.argmax(logit_grid >= thr) if (logit_grid >= thr).any() else None
        iso_z = float(z_grid[iso_idx]) if iso_idx is not None and iso_grid[iso_idx] >= thr else None
        logit_z = float(z_grid[logit_idx]) if logit_idx is not None and logit_grid[logit_idx] >= thr else None
        print(f"    P(win)>={thr*100:.0f}%:  isotonic z>={iso_z:.2f}" if iso_z is not None else
              f"    P(win)>={thr*100:.0f}%:  isotonic NEVER reached in observed range",
              f" logistic z>={logit_z:.2f}" if logit_z is not None else "  logistic NEVER reached")
        crossing_rows.append({"model_set": label, "threshold": thr,
                              "isotonic_first_z": round(iso_z, 2) if iso_z else None,
                              "logistic_first_z": round(logit_z, 2) if logit_z else None})

    return pd.DataFrame(rows), pd.DataFrame(crossing_rows)


def main():
    print("*** TASK 5: P(win|z) calibration curve ***")

    results = pd.read_csv(RESULTS_PATH)

    near = results[results["near_earnings"] == True]  # noqa: E712
    all_events = results

    table_near, cross_near = fit_and_evaluate(near, "earnings_adjacent_only")
    table_all, cross_all = fit_and_evaluate(all_events, "all_events")

    table = pd.concat([table_near, table_all], ignore_index=True)
    crossings = pd.concat([cross_near, cross_all], ignore_index=True)

    combined = pd.concat([table, crossings], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
