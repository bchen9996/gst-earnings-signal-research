#!/usr/bin/env python3
# GST Zscore Volatility Test — Broad50 generalization test. Same
# permutation-test methodology as GST_Zscore_VolatilityTest.py, applied to
# an independent 50-ticker random S&P 500 sample (seed=42, excludes the
# original 15 tickers) instead of the original 15, to check whether the
# volatility finding (+2.976 pts, p=0.0000 pooled; confirmed OOS in both
# tune/test periods; consistent across 14/15 original tickers; replicated
# on the Financial Markets category data) generalizes to a broader,
# independently-drawn universe.

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

SPIKE_DIR = Path("Conjunction Zscore (Broad50)")
BASE_DIR  = Path("Conjunction Zscore Baseline (Broad50)")
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


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    spike = load_pooled(SPIKE_DIR, "*_zconjunction.csv")
    base = load_pooled(BASE_DIR, "*_baseline.csv")

    if spike.empty or base.empty:
        print("Missing spike or baseline data — run the Broad50 pipeline scripts first.")
        return

    print(f"Spike events: {len(spike)}   Baseline events: {len(base)}\n")

    spike_vol = pd.to_numeric(spike["max_abs_excess_pct"], errors="coerce").dropna().abs().to_numpy()
    base_vol = pd.to_numeric(base["max_abs_excess_pct"], errors="coerce").dropna().abs().to_numpy()

    diff, p_two, p_one = permutation_test_mean_diff(spike_vol, base_vol, N_PERMUTATIONS, rng)

    print("--- |max_abs_excess_pct| : biggest move in the window, magnitude only (Broad50) ---")
    print(f"Spike mean:    {spike_vol.mean():.3f}%   (n={len(spike_vol)})")
    print(f"Baseline mean: {base_vol.mean():.3f}%   (n={len(base_vol)})")
    print(f"Diff (spike - baseline): {diff:+.3f} pts")
    print(f"Two-sided p-value: {p_two:.4f}  {'(significant at 0.05)' if p_two < 0.05 else '(NOT significant at 0.05)'}")
    print(f"One-sided p-value (spike > baseline): {p_one:.4f}  "
          f"{'(significant at 0.05)' if p_one < 0.05 else '(NOT significant at 0.05)'}")

    print(f"\n({N_PERMUTATIONS} permutations, seed={RANDOM_SEED} for reproducibility)")
    print("\n--- Comparison to original 15-ticker result ---")
    print(f"Original 15: spike 5.987%, baseline 3.011%, diff +2.976 pts, p=0.0000")
    print(f"Broad50:     spike {spike_vol.mean():.3f}%, baseline {base_vol.mean():.3f}%, diff {diff:+.3f} pts, p={p_two:.4f}")


if __name__ == "__main__":
    main()
