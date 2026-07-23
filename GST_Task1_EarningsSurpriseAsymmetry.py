#!/usr/bin/env python3
# TASK 1 — Earnings surprise asymmetry. All on-disk data, no new pulls:
# reuses Live Signal Engine/Task3_InformationLeakageTest_Results.csv
# (surprise_pct already pulled per z>=5 STRONG_EARNINGS event) joined with
# Earnings-Adjacent Spike vs No-Spike Test/group_a_z4_earnings_adjacent.csv
# (win/pnl, earnings-aware pricing already baked in).
#
# Missing surprise data (status != "ok" or surprise_pct null) is FLAGGED
# and excluded, not silently dropped without disclosure.
#
# Output: Live Signal Engine/Task1_EarningsSurpriseAsymmetry_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

SURPRISE_PATH = Path("Live Signal Engine") / "Task3_InformationLeakageTest_Results.csv"
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task1_EarningsSurpriseAsymmetry_Results.csv"

Z_THRESHOLD = 5.0
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


def point_biserial_perm(binary: np.ndarray, cont: np.ndarray, n_perm, rng):
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
    print(f"*** TASK 1: Earnings surprise asymmetry (z>={Z_THRESHOLD:g}) ***\n")

    surprise = pd.read_csv(SURPRISE_PATH)
    surprise = surprise[surprise["group"] == "A_STRONG_EARNINGS"].copy()
    surprise["anchor"] = pd.to_datetime(surprise["anchor"]).dt.date.astype(str)

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["week"] = pd.to_datetime(events["spike_week"]).dt.date.astype(str)

    merged = events.merge(surprise[["ticker", "anchor", "surprise_pct", "status"]],
                           left_on=["ticker", "week"], right_on=["ticker", "anchor"], how="left")

    n_total = len(merged)
    n_missing = merged["surprise_pct"].isna().sum() | (merged["status"] != "ok").sum()
    missing_mask = merged["surprise_pct"].isna() | (merged["status"] != "ok")
    n_missing = int(missing_mask.sum())
    if n_missing:
        print(f"FLAGGED: {n_missing}/{n_total} events have missing/failed surprise data — excluded from grouping, "
              f"not silently dropped: {merged.loc[missing_mask, 'ticker'].tolist()}\n")

    usable = merged[~missing_mask].copy()
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    positive = usable[usable["surprise_pct"] > 0]
    negative = usable[usable["surprise_pct"] < 0]
    zero = usable[usable["surprise_pct"] == 0]
    if len(zero):
        print(f"NOTE: {len(zero)} event(s) with exactly 0% surprise — excluded from the positive/negative split "
              f"(neither beat nor missed), reported separately.\n")

    pos_u = positive[positive[win_col].notna()]
    neg_u = negative[negative[win_col].notna()]

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"Positive surprise (EPS > consensus): n={len(pos_u):<4} win={pos_u[win_col].mean()*100:5.1f}%  "
          f"avg={pos_u[pnl_col].mean():+7.1f}%  median={pos_u[pnl_col].median():+7.1f}%")
    print(f"Negative surprise (EPS < consensus): n={len(neg_u):<4} win={neg_u[win_col].mean()*100:5.1f}%  "
          f"avg={neg_u[pnl_col].mean():+7.1f}%  median={neg_u[pnl_col].median():+7.1f}%")
    if len(zero):
        zero_u = zero[zero[win_col].notna()]
        print(f"Exactly zero surprise (met consensus): n={len(zero_u):<4} win={zero_u[win_col].mean()*100:5.1f}%  "
              f"median={zero_u[pnl_col].median():+7.1f}%")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p = two_sample_permutation_test(pos_u[pnl_col].to_numpy(dtype=float),
                                           neg_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
    sig = "significant" if p < 0.05 else "not significant"
    print(f"\nDiff (Positive - Negative), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    diff_wr, p_wr = two_sample_permutation_test(pos_u[win_col].astype(float).to_numpy(),
                                                 neg_u[win_col].astype(float).to_numpy(), N_PERMUTATIONS, rng)
    sig_wr = "significant" if p_wr < 0.05 else "not significant"
    print(f"Diff (Positive - Negative), win rate: {diff_wr*100:+.1f}pt  p={p_wr:.4f} ({sig_wr})")

    print(f"\n=== DOES SURPRISE DIRECTION PREDICT WIN/LOSS? ===")
    win_bin = usable[win_col].dropna().astype(int).to_numpy()
    surp_cont = usable.loc[usable[win_col].notna(), "surprise_pct"].to_numpy(dtype=float)
    r, p_corr = point_biserial_perm(win_bin, surp_cont, N_PERMUTATIONS, np.random.default_rng(RANDOM_SEED))
    if r is not None:
        sig_corr = "significant" if p_corr < 0.05 else "not significant"
        print(f"Point-biserial correlation (win vs surprise_pct): r={r:+.3f}  permutation p={p_corr:.4f} ({sig_corr})")
        if p_corr < 0.05:
            print("=> Surprise direction/magnitude DOES predict straddle win/loss.")
        else:
            print("=> Surprise direction/magnitude does NOT reliably predict straddle win/loss "
                  "(straddles profit from MOVE SIZE regardless of direction, so this null is expected by design).")

    usable.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
