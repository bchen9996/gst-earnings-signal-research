#!/usr/bin/env python3
# TASK 3 — Quiet prior quarter: does a ticker coming from a QUIET recent
# search-attention baseline (mean z < 0 over the 13 weeks before the
# spike) show different straddle economics than one coming from an
# already-ELEVATED baseline (mean z >= 0)? All on-disk data, no new pulls:
# reuses Live Signal Engine/AllTickers_ZscoreSeries.csv (the full weekly
# z-score history built for the cross-sectional/EWMA/negative-controls
# round) joined with the existing 147-event z>=5 STRONG_EARNINGS list.
#
# Secondary check: restricts to z in [5,10] only (excludes the extreme
# tail) to test whether the quiet-prior pattern survives once raw z-score
# magnitude is controlled for — same disambiguation discipline used for
# the earlier abnormal-GST-residual finding (which similarly appeared
# strong uncontrolled and evaporated once magnitude was controlled for).
#
# Output: Live Signal Engine/QuietPriorQuarter_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
OUT_PATH = Path("Live Signal Engine") / "QuietPriorQuarter_Results.csv"

Z_THRESHOLD = 5.0
PRIOR_WINDOW_WEEKS = 13
CONTROLLED_Z_MAX = 10.0
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def report(df, win_col, pnl_col, label):
    usable = df[df[win_col].notna()]
    n = len(usable)
    if n == 0:
        print(f"{label}: no usable events")
        return usable
    wr = usable[win_col].mean() * 100
    avg = usable[pnl_col].mean()
    med = usable[pnl_col].median()
    print(f"{label}: n={n:<4} win={wr:5.1f}%  avg={avg:+7.1f}%  median={med:+7.1f}%")
    return usable


def main():
    print(f"*** TASK 3: Quiet prior quarter (z>={Z_THRESHOLD:g}, {PRIOR_WINDOW_WEEKS}wk lookback) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_by_ticker = {t: g.set_index("week")["zscore_simple"] for t, g in z_df.groupby("ticker")}

    prior_means, n_prior_weeks_used = [], []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        series = z_by_ticker.get(ticker)
        if series is None:
            prior_means.append(None); n_prior_weeks_used.append(0)
            continue
        window_start = anchor - timedelta(weeks=PRIOR_WINDOW_WEEKS)
        window = series[(series.index >= window_start) & (series.index < anchor)].dropna()
        if len(window) == 0:
            prior_means.append(None); n_prior_weeks_used.append(0)
        else:
            prior_means.append(float(window.mean()))
            n_prior_weeks_used.append(len(window))
    events["prior_13wk_mean_z"] = prior_means
    events["n_prior_weeks_used"] = n_prior_weeks_used

    n_missing = events["prior_13wk_mean_z"].isna().sum()
    if n_missing:
        print(f"NOTE: {n_missing} event(s) excluded — no prior z-score history available.\n")
    events["regime"] = np.where(events["prior_13wk_mean_z"] < 0, "came_from_quiet",
                                 np.where(events["prior_13wk_mean_z"].notna(), "came_from_elevated", None))

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    print("=== FULL SAMPLE ===")
    quiet = events[events["regime"] == "came_from_quiet"]
    elevated = events[events["regime"] == "came_from_elevated"]
    quiet_u = report(quiet, win_col, pnl_col, "Came from QUIET (prior mean z < 0)")
    elevated_u = report(elevated, win_col, pnl_col, "Came from ELEVATED (prior mean z >= 0)")

    rng = np.random.default_rng(RANDOM_SEED)
    if len(quiet_u) and len(elevated_u):
        diff, p = two_sample_permutation_test(quiet_u[pnl_col].to_numpy(dtype=float),
                                               elevated_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (Quiet - Elevated), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    print(f"\n=== SECONDARY CHECK: controlled for raw z-score magnitude, z in [5, {CONTROLLED_Z_MAX:g}] only ===")
    controlled = events[(events["zscore"] >= Z_THRESHOLD) & (events["zscore"] <= CONTROLLED_Z_MAX)]
    print(f"Controlled subset: n={len(controlled)} (of {len(events)} total)")
    quiet_c = controlled[controlled["regime"] == "came_from_quiet"]
    elevated_c = controlled[controlled["regime"] == "came_from_elevated"]
    quiet_cu = report(quiet_c, win_col, pnl_col, "  Controlled QUIET")
    elevated_cu = report(elevated_c, win_col, pnl_col, "  Controlled ELEVATED")

    if len(quiet_cu) and len(elevated_cu):
        diff_c, p_c = two_sample_permutation_test(quiet_cu[pnl_col].to_numpy(dtype=float),
                                                    elevated_cu[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig_c = "significant" if p_c < 0.05 else "not significant"
        print(f"\nDiff (Quiet - Elevated), controlled, P&L: {diff_c:+.1f}pt  p={p_c:.4f} ({sig_c})")

    events.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
