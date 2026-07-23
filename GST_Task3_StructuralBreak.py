#!/usr/bin/env python3
# TASK 3 — Structural break detection: formalizes the eyeballed "decay
# then reset" pattern in year-by-year win rate (Live Signal Engine/
# Task2_LongitudinalStability_Results.csv, 11 points: 2014-2019 + 2021-2025,
# 2020 is a genuine data gap, not a modeling choice) into a Chow test for a
# break at 2020/2021 and a CUSUM test for parameter stability over time.
#
# *** SMALL-SAMPLE DISCLOSURE ***
# n=11 (6 pre-break, 5 post-break) is a genuinely small sample for both
# tests. The Chow test's F-distribution assumptions (normal, homoskedastic
# residuals) are unlikely to hold exactly with this few points, and the
# CUSUM test (Brown/Durbin/Evans recursive-residual form) only has 9 usable
# recursive residuals (k=2 parameters, n=11). Results are reported as-is,
# not adjusted or dismissed, but should be read as suggestive rather than
# conclusive given the sample size.
#
# Output: Live Signal Engine/StructuralBreak_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy import stats

sys.stdout.reconfigure(encoding="utf-8")

SRC_PATH = Path("Live Signal Engine") / "Task2_LongitudinalStability_Results.csv"
OUT_PATH = Path("Live Signal Engine") / "StructuralBreak_Results.csv"

BREAK_AFTER_YEAR = 2019  # pre: 2014-2019, post: 2021-2025 (2020 absent)
CUSUM_SIGNIFICANCE_A = 0.948  # Brown-Durbin-Evans 5% two-sided critical value


def ols_fit(x, y):
    X = np.column_stack([np.ones_like(x), x])
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    rss = float(resid @ resid)
    return beta, rss, X


def chow_test(x, y, break_x):
    beta_pooled, rss_pooled, _ = ols_fit(x, y)

    mask1, mask2 = x <= break_x, x > break_x
    x1, y1 = x[mask1], y[mask1]
    x2, y2 = x[mask2], y[mask2]
    n1, n2 = len(x1), len(x2)
    k = 2  # intercept + slope

    _, rss1, _ = ols_fit(x1, y1)
    _, rss2, _ = ols_fit(x2, y2)

    numerator = (rss_pooled - (rss1 + rss2)) / k
    denom_df = n1 + n2 - 2 * k
    denominator = (rss1 + rss2) / denom_df
    f_stat = numerator / denominator if denominator > 0 else np.inf
    p_value = float(1 - stats.f.cdf(f_stat, k, denom_df))

    return {"f_stat": f_stat, "p_value": p_value, "df1": k, "df2": denom_df,
            "rss_pooled": rss_pooled, "rss1": rss1, "rss2": rss2, "n1": n1, "n2": n2}


def cusum_test(x, y):
    n = len(x)
    k = 2
    X_full = np.column_stack([np.ones_like(x), x])

    recursive_resid = []
    for r in range(k + 1, n + 1):
        X_r = X_full[:r - 1]
        y_r = y[:r - 1]
        beta_r, _, _, _ = np.linalg.lstsq(X_r, y_r, rcond=None)
        x_next = X_full[r - 1]
        pred = x_next @ beta_r
        XtX_inv = np.linalg.inv(X_r.T @ X_r)
        leverage_term = 1 + x_next @ XtX_inv @ x_next
        w_r = (y[r - 1] - pred) / np.sqrt(leverage_term)
        recursive_resid.append(w_r)

    recursive_resid = np.array(recursive_resid)
    sigma_hat = np.sqrt(np.sum(recursive_resid ** 2) / (n - k))

    cusum_path = np.cumsum(recursive_resid) / sigma_hat
    rs = np.arange(k + 1, n + 1)
    bounds = CUSUM_SIGNIFICANCE_A * np.sqrt(n - k) * (1 + 2 * (rs - k) / (n - k))

    crosses = bool(np.any(np.abs(cusum_path) > bounds))
    return {"r": rs, "cusum": cusum_path, "bound": bounds, "sigma_hat": sigma_hat,
            "crosses_5pct_bound": crosses}


def main():
    print("*** TASK 3: Structural break detection (Chow test + CUSUM) ***\n")

    df = pd.read_csv(SRC_PATH).sort_values("year").reset_index(drop=True)
    print(f"Input: {len(df)} year-points -- {df['year'].tolist()}\n")

    x = df["year"].to_numpy(dtype=float)
    y = df["win_rate_pct"].to_numpy(dtype=float)

    print("=== CHOW TEST (break at 2019/2021, win rate ~ year) ===")
    chow = chow_test(x, y, BREAK_AFTER_YEAR)
    print(f"Pre-break (2014-2019, n={chow['n1']}): RSS={chow['rss1']:.2f}")
    print(f"Post-break (2021-2025, n={chow['n2']}): RSS={chow['rss2']:.2f}")
    print(f"Pooled RSS: {chow['rss_pooled']:.2f}")
    print(f"F-statistic: {chow['f_stat']:.4f}  (df1={chow['df1']}, df2={chow['df2']})")
    print(f"p-value: {chow['p_value']:.4f}")
    print(f"Structural break significant at 0.05: {chow['p_value'] < 0.05}\n")

    print("=== CUSUM TEST (recursive residuals, win rate ~ year) ===")
    cusum = cusum_test(x, y)
    print(f"sigma_hat (recursive residual std): {cusum['sigma_hat']:.4f}")
    for r, c, b in zip(cusum["r"], cusum["cusum"], cusum["bound"]):
        year_at_r = int(x[r - 1])
        flag = "  [OUTSIDE 5% BOUND]" if abs(c) > b else ""
        print(f"  r={r} (up to year {year_at_r}): CUSUM={c:+.3f}  bound=±{b:.3f}{flag}")
    print(f"\nCUSUM crosses the 5% significance bound at any point: {cusum['crosses_5pct_bound']}\n")

    print("=== SAME TESTS ON MEDIAN P&L (robustness check) ===")
    y2 = df["median_pnl_pct"].to_numpy(dtype=float)
    chow2 = chow_test(x, y2, BREAK_AFTER_YEAR)
    print(f"Chow F-statistic (median P&L): {chow2['f_stat']:.4f}  p={chow2['p_value']:.4f}  "
          f"significant: {chow2['p_value'] < 0.05}")
    cusum2 = cusum_test(x, y2)
    print(f"CUSUM crosses bound (median P&L): {cusum2['crosses_5pct_bound']}\n")

    cusum_rows = pd.DataFrame({
        "metric": "win_rate_pct", "r": cusum["r"], "year_up_to": x[cusum["r"] - 1].astype(int),
        "cusum": cusum["cusum"], "bound": cusum["bound"],
        "outside_bound": np.abs(cusum["cusum"]) > cusum["bound"],
    })
    cusum_rows2 = pd.DataFrame({
        "metric": "median_pnl_pct", "r": cusum2["r"], "year_up_to": x[cusum2["r"] - 1].astype(int),
        "cusum": cusum2["cusum"], "bound": cusum2["bound"],
        "outside_bound": np.abs(cusum2["cusum"]) > cusum2["bound"],
    })

    chow_rows = pd.DataFrame([
        {"metric": "win_rate_pct", "test": "chow", "f_stat": chow["f_stat"], "p_value": chow["p_value"],
         "df1": chow["df1"], "df2": chow["df2"], "n1": chow["n1"], "n2": chow["n2"],
         "significant_at_05": chow["p_value"] < 0.05},
        {"metric": "median_pnl_pct", "test": "chow", "f_stat": chow2["f_stat"], "p_value": chow2["p_value"],
         "df1": chow2["df1"], "df2": chow2["df2"], "n1": chow2["n1"], "n2": chow2["n2"],
         "significant_at_05": chow2["p_value"] < 0.05},
    ])

    combined = pd.concat([chow_rows, pd.DataFrame([{}]), cusum_rows, cusum_rows2], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
