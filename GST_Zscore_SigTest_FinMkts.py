#!/usr/bin/env python3
# GST Zscore Significance Test (Financial Markets category) — permutation
# test comparing spike-week stats vs random-baseline stats, same logic as
# GST_Zscore_SigTest.py but reading the Financial Markets category pipeline
# output.

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

SPIKE_DIR = Path("Conjunction Zscore (Financial Markets)")
BASE_DIR  = Path("Conjunction Zscore Baseline (Financial Markets)")
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def load_pooled(directory: Path, pattern: str) -> pd.DataFrame:
    frames = []
    for f in sorted(directory.glob(pattern)):
        df = pd.read_csv(f)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def permutation_test_mean_diff(group_a, group_b, n_perm, rng):
    observed_diff = group_a.mean() - group_b.mean()
    pooled = np.concatenate([group_a, group_b])
    n_a = len(group_a)

    count_extreme_two_sided = 0
    count_a_greater = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        perm_a = pooled[:n_a]
        perm_b = pooled[n_a:]
        diff = perm_a.mean() - perm_b.mean()
        if abs(diff) >= abs(observed_diff):
            count_extreme_two_sided += 1
        if diff >= observed_diff:
            count_a_greater += 1

    p_two_sided = count_extreme_two_sided / n_perm
    p_one_sided = count_a_greater / n_perm
    return observed_diff, p_two_sided, p_one_sided


def permutation_test_proportion_diff(group_a, group_b, n_perm, rng):
    observed_diff = group_a.mean() - group_b.mean()
    pooled = np.concatenate([group_a, group_b])
    n_a = len(group_a)

    count_extreme = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        perm_a = pooled[:n_a]
        perm_b = pooled[n_a:]
        diff = perm_a.mean() - perm_b.mean()
        if abs(diff) >= abs(observed_diff):
            count_extreme += 1

    return observed_diff, count_extreme / n_perm


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    spike = load_pooled(SPIKE_DIR, "*_zconjunction.csv")
    base = load_pooled(BASE_DIR, "*_baseline.csv")

    if spike.empty or base.empty:
        print("Missing spike or baseline data — run GST_Zscore_Combiner_FinMkts.py and GST_Zscore_Baseline_FinMkts.py first.")
        return

    print(f"Spike events: {len(spike)}   Baseline events: {len(base)}\n")

    spike_pos = pd.to_numeric(spike["pos_in_window_pos"], errors="coerce").dropna().to_numpy()
    base_pos = pd.to_numeric(base["pos_in_window_pos"], errors="coerce").dropna().to_numpy()
    diff, p_two, p_one = permutation_test_mean_diff(spike_pos, base_pos, N_PERMUTATIONS, rng)
    print("--- Position of max positive move (day 1-15) ---")
    print(f"Spike mean: {spike_pos.mean():.3f}   Baseline mean: {base_pos.mean():.3f}   Diff: {diff:+.3f}")
    print(f"Two-sided p-value: {p_two:.4f}  {'(significant at 0.05)' if p_two < 0.05 else '(NOT significant at 0.05)'}")

    spike_streak = pd.to_numeric(spike["pos_streak_days_from_max"], errors="coerce")
    spike_streak = spike_streak[spike_streak > 0].dropna().to_numpy()
    base_streak = pd.to_numeric(base["pos_streak_days_from_max"], errors="coerce")
    base_streak = base_streak[base_streak > 0].dropna().to_numpy()
    diff2, p_two2, _ = permutation_test_mean_diff(spike_streak, base_streak, N_PERMUTATIONS, rng)
    print("\n--- Non-negative streak length (days) ---")
    print(f"Spike mean: {spike_streak.mean():.3f}   Baseline mean: {base_streak.mean():.3f}   Diff: {diff2:+.3f}")
    print(f"Two-sided p-value: {p_two2:.4f}  {'(significant at 0.05)' if p_two2 < 0.05 else '(NOT significant at 0.05)'}")

    spike_neg = (pd.to_numeric(spike["max_abs_excess_pct"], errors="coerce").dropna() < 0).astype(int).to_numpy()
    base_neg = (pd.to_numeric(base["max_abs_excess_pct"], errors="coerce").dropna() < 0).astype(int).to_numpy()
    diff3, p3 = permutation_test_proportion_diff(spike_neg, base_neg, N_PERMUTATIONS, rng)
    print("\n--- % of events where the biggest move was NEGATIVE ---")
    print(f"Spike: {spike_neg.mean()*100:.1f}%   Baseline: {base_neg.mean()*100:.1f}%   Diff: {diff3*100:+.1f} points")
    print(f"Two-sided p-value: {p3:.4f}  {'(significant at 0.05)' if p3 < 0.05 else '(NOT significant at 0.05)'}")

    print(f"\n({N_PERMUTATIONS} permutations, seed={RANDOM_SEED} for reproducibility)")


if __name__ == "__main__":
    main()
