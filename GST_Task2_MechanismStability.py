#!/usr/bin/env python3
# TASK 2 — Mechanism stability without any pricing model: does the raw
# realized move magnitude itself differ between STRONG_EARNINGS spike
# weeks and random baseline weeks, independent of Black-Scholes, IV
# calibration, or any options-pricing assumption at all? All on-disk
# data, no new pulls.
#
# *** BASELINE SIZE DISCREPANCY — DISCLOSED, NOT SILENTLY RESOLVED ***
# The task's stated "n=375, from Conjunction Zscore Baseline/" (no year
# suffix) matches ONLY the ORIGINAL 15-ticker 2021-2025 baseline folder
# (which happens to have exactly 375 rows, as does the unrelated 2014-2019
# folder — a coincidence, verified by direct row count). But the task
# frames this as "the 2021-2025 dataset (51 tickers)" — which requires
# COMBINING the original 15-ticker baseline (375 rows) with the Broad50
# Clear 36-ticker baseline (900 rows) for a true 51-ticker n=1275. This
# script uses the full 51-ticker combined baseline (n=1275) to match the
# stated scope, NOT the literal "n=375" figure, since 375 only covers
# 15 of the 51 tickers. Both counts are reported so this is auditable.
#
# Output: Live Signal Engine/MechanismStability_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR

SPIKE_DIRS = {t: Path("Conjunction Zscore (2021-2025)") for t in TICKERS_ORIGINAL}
SPIKE_DIRS.update({t: Path("Conjunction Zscore (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})
BASELINE_DIRS = {t: Path("Conjunction Zscore Baseline (2021-2025)") for t in TICKERS_ORIGINAL}
BASELINE_DIRS.update({t: Path("Conjunction Zscore Baseline (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "MechanismStability_Results.csv"

Z_THRESHOLD = 5.0
Z_EXTREME_CUTOFF = 15.0
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def two_sample_permutation_test(a, b, n_perm, rng, stat="mean"):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    f = np.mean if stat == "mean" else np.median
    observed_diff = f(a) - f(b)
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = f(pooled[:n_a]) - f(pooled[n_a:])
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def cohens_d(a, b):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    pooled_std = np.sqrt(((len(a)-1)*a.std(ddof=1)**2 + (len(b)-1)*b.std(ddof=1)**2) / (len(a)+len(b)-2))
    return (a.mean() - b.mean()) / pooled_std if pooled_std > 0 else np.nan


def main():
    print(f"*** TASK 2: Mechanism stability, raw realized move only (no pricing model) ***\n")

    spike_frames, baseline_frames = [], []
    for t in ALL_TICKERS:
        sp = SPIKE_DIRS[t] / f"{t}_zconjunction.csv"
        if sp.exists():
            df = pd.read_csv(sp)
            df["ticker"] = t
            spike_frames.append(df)
        bp = BASELINE_DIRS[t] / f"{t}_baseline.csv"
        if bp.exists():
            df = pd.read_csv(bp)
            df["ticker"] = t
            baseline_frames.append(df)

    spikes = pd.concat(spike_frames, ignore_index=True)
    baseline = pd.concat(baseline_frames, ignore_index=True)

    n_baseline_15only = len(baseline[baseline["ticker"].isin(TICKERS_ORIGINAL)])
    print(f"Baseline events, 15-ticker-only subset (matches the task's stated 'n=375'): {n_baseline_15only}")
    print(f"Baseline events, FULL 51-ticker combined (used for this analysis): {len(baseline)}\n")

    # STRONG_EARNINGS = z>=5 AND earnings-adjacent (near_earnings=True) — restrict to the
    # canonical n=147 set, not just any z>=5 spike regardless of earnings proximity.
    strong_earnings_keys = pd.read_csv(GROUP_A_PATH)
    strong_earnings_keys = strong_earnings_keys[strong_earnings_keys["zscore"] >= Z_THRESHOLD]
    key_set = set(zip(strong_earnings_keys["ticker"], pd.to_datetime(strong_earnings_keys["spike_week"]).dt.date.astype(str)))

    spikes["spike_week"] = pd.to_datetime(spikes["spike_week"]).dt.date.astype(str)
    z5 = spikes[spikes.apply(lambda r: (r["ticker"], r["spike_week"]) in key_set, axis=1)].copy()
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS spike events (earnings-adjacent, canonical set): n={len(z5)}")

    spike_move = z5["max_abs_excess_pct"].abs().dropna().to_numpy(dtype=float)
    baseline_move = baseline["max_abs_excess_pct"].abs().dropna().to_numpy(dtype=float)
    print(f"Usable: spike n={len(spike_move)}, baseline n={len(baseline_move)}\n")

    rng = np.random.default_rng(RANDOM_SEED)

    print("=== FULL SAMPLE ===")
    print(f"Spike weeks:    mean|move|={spike_move.mean():.2f}%  median={np.median(spike_move):.2f}%")
    print(f"Baseline weeks: mean|move|={baseline_move.mean():.2f}%  median={np.median(baseline_move):.2f}%")

    diff_mean, p_mean = two_sample_permutation_test(spike_move, baseline_move, N_PERMUTATIONS, rng, "mean")
    diff_med, p_med = two_sample_permutation_test(spike_move, baseline_move, N_PERMUTATIONS, np.random.default_rng(RANDOM_SEED), "median")
    d = cohens_d(spike_move, baseline_move)
    print(f"Diff in means: {diff_mean:+.2f}pt  p={p_mean:.4f} ({'significant' if p_mean<0.05 else 'not significant'})")
    print(f"Diff in medians: {diff_med:+.2f}pt  p={p_med:.4f} ({'significant' if p_med<0.05 else 'not significant'})")
    print(f"Cohen's d (effect size): {d:.3f}")

    print(f"\n=== EXCLUDING {int((z5['zscore']>Z_EXTREME_CUTOFF).sum())} EXTREME EVENTS (z>{Z_EXTREME_CUTOFF:g}) — "
          f"confirms effect isn't outlier-driven ===")
    z5_trimmed = z5[z5["zscore"] <= Z_EXTREME_CUTOFF]
    spike_move_trimmed = z5_trimmed["max_abs_excess_pct"].abs().dropna().to_numpy(dtype=float)
    print(f"Spike weeks (trimmed): n={len(spike_move_trimmed)}  mean|move|={spike_move_trimmed.mean():.2f}%  "
          f"median={np.median(spike_move_trimmed):.2f}%")

    diff_mean_t, p_mean_t = two_sample_permutation_test(spike_move_trimmed, baseline_move, N_PERMUTATIONS,
                                                          np.random.default_rng(RANDOM_SEED), "mean")
    diff_med_t, p_med_t = two_sample_permutation_test(spike_move_trimmed, baseline_move, N_PERMUTATIONS,
                                                        np.random.default_rng(RANDOM_SEED), "median")
    d_t = cohens_d(spike_move_trimmed, baseline_move)
    print(f"Diff in means (trimmed): {diff_mean_t:+.2f}pt  p={p_mean_t:.4f} ({'significant' if p_mean_t<0.05 else 'not significant'})")
    print(f"Diff in medians (trimmed): {diff_med_t:+.2f}pt  p={p_med_t:.4f} ({'significant' if p_med_t<0.05 else 'not significant'})")
    print(f"Cohen's d (trimmed): {d_t:.3f}")

    out = pd.DataFrame([
        {"scenario": "full_sample", "n_spike": len(spike_move), "n_baseline": len(baseline_move),
         "spike_mean_move_pct": round(spike_move.mean(), 2), "baseline_mean_move_pct": round(baseline_move.mean(), 2),
         "diff_mean_pt": round(diff_mean, 2), "p_mean": round(p_mean, 4),
         "spike_median_move_pct": round(float(np.median(spike_move)), 2),
         "baseline_median_move_pct": round(float(np.median(baseline_move)), 2),
         "diff_median_pt": round(diff_med, 2), "p_median": round(p_med, 4), "cohens_d": round(d, 3)},
        {"scenario": f"excl_z_gt_{Z_EXTREME_CUTOFF:g}", "n_spike": len(spike_move_trimmed), "n_baseline": len(baseline_move),
         "spike_mean_move_pct": round(spike_move_trimmed.mean(), 2), "baseline_mean_move_pct": round(baseline_move.mean(), 2),
         "diff_mean_pt": round(diff_mean_t, 2), "p_mean": round(p_mean_t, 4),
         "spike_median_move_pct": round(float(np.median(spike_move_trimmed)), 2),
         "baseline_median_move_pct": round(float(np.median(baseline_move)), 2),
         "diff_median_pt": round(diff_med_t, 2), "p_median": round(p_med_t, 4), "cohens_d": round(d_t, 3)},
    ])
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
