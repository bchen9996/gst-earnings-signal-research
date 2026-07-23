#!/usr/bin/env python3
# TASK 1 — Earnings-relative attention surprise. All on-disk data, no new
# pulls: reuses AllTickers_EarningsDates.csv, AllTickers_ZscoreSeries.csv
# (the shared foundation built for the cross-sectional/EWMA/negative-
# controls round) and group_a_z4_earnings_adjacent.csv (win/pnl,
# earnings-aware pricing already baked in).
#
# For each z>=5 event, finds the ticker's prior 3 earnings dates (before
# THIS event's own earnings date, not just before the anchor), looks up
# the z-score in the GST week nearest each prior earnings date, and
# averages them (prior_earnings_mean_z). relative_surprise = current
# z-score - prior_earnings_mean_z. Events with <2 usable prior earnings
# quarters are flagged LOW-CONFIDENCE and reported separately, not
# silently included in the main split.
#
# Output: Live Signal Engine/EarningsRelativeSurprise_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
OUT_PATH = Path("Live Signal Engine") / "EarningsRelativeSurprise_Results.csv"

Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
PRIOR_QUARTERS = 3
MIN_PRIOR_FOR_CONFIDENCE = 2
WEEK_MATCH_TOL_DAYS = 3
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


def point_biserial_perm(binary, cont, n_perm, rng):
    mask = ~np.isnan(cont)
    b = binary[mask].astype(float); c = cont[mask]
    if len(c) < 3:
        return None, None
    observed_r = np.corrcoef(b, c)[0, 1]
    count = 0
    c_shuf = c.copy()
    for _ in range(n_perm):
        rng.shuffle(c_shuf)
        r = np.corrcoef(b, c_shuf)[0, 1]
        if abs(r) >= abs(observed_r):
            count += 1
    return observed_r, count / n_perm


def main():
    print(f"*** TASK 1: Earnings-relative attention surprise (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earnings_df.groupby("ticker")}

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_by_ticker = {t: g.set_index("week")["zscore_simple"] for t, g in z_df.groupby("ticker")}

    def zscore_near(ticker, target_date, tol=WEEK_MATCH_TOL_DAYS):
        series = z_by_ticker.get(ticker)
        if series is None or series.empty:
            return None
        diffs = np.abs((series.index - target_date).days.to_numpy())
        nearest_pos = int(diffs.argmin())
        if diffs[nearest_pos] > tol:
            return None
        val = series.iloc[nearest_pos]
        return float(val) if pd.notna(val) else None

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        dates = earnings_by_ticker.get(ticker, [])
        gaps = [(abs((d - anchor).days), d) for d in dates]
        gaps.sort()
        this_earnings_date = gaps[0][1] if gaps and gaps[0][0] <= EARNINGS_WINDOW_DAYS else anchor

        prior_dates = sorted([d for d in dates if d < this_earnings_date], reverse=True)[:PRIOR_QUARTERS]
        prior_zs = []
        for d in prior_dates:
            z = zscore_near(ticker, d)
            if z is not None:
                prior_zs.append(z)

        n_prior = len(prior_zs)
        low_confidence = n_prior < MIN_PRIOR_FOR_CONFIDENCE
        prior_mean_z = float(np.mean(prior_zs)) if prior_zs else None
        relative_surprise = (zscore - prior_mean_z) if prior_mean_z is not None else None

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": zscore,
            "n_prior_earnings_used": n_prior, "prior_earnings_mean_z": prior_mean_z,
            "relative_surprise": relative_surprise, "low_confidence": low_confidence,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    result = pd.DataFrame(rows)
    n_low_conf = result["low_confidence"].sum()
    print(f"Low-confidence events (<{MIN_PRIOR_FOR_CONFIDENCE} usable prior earnings quarters): n={n_low_conf}")
    print(f"  Reported separately, excluded from the main high/low split.\n")

    main_set = result[~result["low_confidence"]].copy()
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    median_rs = main_set["relative_surprise"].median()
    main_set["group"] = np.where(main_set["relative_surprise"] >= median_rs, "high_relative_surprise", "low_relative_surprise")

    print(f"Main analysis set (confidence-qualified): n={len(main_set)}   median relative_surprise={median_rs:+.2f}\n")

    high = main_set[main_set["group"] == "high_relative_surprise"]
    low = main_set[main_set["group"] == "low_relative_surprise"]
    high_u = high[high[win_col].notna()]
    low_u = low[low[win_col].notna()]

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"High relative_surprise (>= median): n={len(high_u):<4} win={high_u[win_col].mean()*100:5.1f}%  "
          f"avg={high_u[pnl_col].mean():+7.1f}%  median={high_u[pnl_col].median():+7.1f}%")
    print(f"Low relative_surprise (< median):   n={len(low_u):<4} win={low_u[win_col].mean()*100:5.1f}%  "
          f"avg={low_u[pnl_col].mean():+7.1f}%  median={low_u[pnl_col].median():+7.1f}%")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p = two_sample_permutation_test(high_u[pnl_col].to_numpy(dtype=float),
                                           low_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
    sig = "significant" if p < 0.05 else "not significant"
    print(f"\nDiff (High - Low), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    low_conf_set = result[result["low_confidence"]]
    if len(low_conf_set):
        lc_u = low_conf_set[low_conf_set[win_col].notna()]
        print(f"\n=== LOW-CONFIDENCE events (reported separately), n={len(lc_u)} ===")
        if len(lc_u):
            print(f"win={lc_u[win_col].mean()*100:.1f}%  median={lc_u[pnl_col].median():+.1f}%")

    print(f"\n=== DOES relative_surprise ADD PREDICTIVE POWER BEYOND RAW Z-SCORE? ===")
    win_bin = main_set[win_col].dropna().astype(int).to_numpy()
    rs_cont = main_set.loc[main_set[win_col].notna(), "relative_surprise"].to_numpy(dtype=float)
    r, p_corr = point_biserial_perm(win_bin, rs_cont, N_PERMUTATIONS, np.random.default_rng(RANDOM_SEED))
    if r is not None:
        sig_corr = "significant" if p_corr < 0.05 else "not significant"
        print(f"Point-biserial correlation (win vs relative_surprise): r={r:+.3f}  permutation p={p_corr:.4f} ({sig_corr})")

    z_bin_r, z_p = point_biserial_perm(win_bin, main_set.loc[main_set[win_col].notna(), "zscore"].to_numpy(dtype=float),
                                        N_PERMUTATIONS, np.random.default_rng(RANDOM_SEED))
    if z_bin_r is not None:
        print(f"(For comparison) Point-biserial correlation (win vs raw zscore): r={z_bin_r:+.3f}  p={z_p:.4f}")

    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
