#!/usr/bin/env python3
# GST Zscore Out-of-Sample check (Financial Markets category) — same
# tune/test split logic as GST_Zscore_OOS.py, reading the Financial
# Markets category pipeline output instead.

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

SPIKE_DIR = Path("Conjunction Zscore (Financial Markets)")
BASE_DIR = Path("Conjunction Zscore Baseline (Financial Markets)")
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

TUNE_YEARS = (2014, 2017)
TEST_YEARS = (2018, 2019)


def load_pooled(directory: Path, pattern: str, date_col: str) -> pd.DataFrame:
    frames = []
    for f in sorted(directory.glob(pattern)):
        df = pd.read_csv(f)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out[date_col] = pd.to_datetime(out[date_col])
    return out


def permutation_test_mean_diff(group_a, group_b, n_perm, rng):
    observed_diff = group_a.mean() - group_b.mean()
    pooled = np.concatenate([group_a, group_b])
    n_a = len(group_a)

    count_extreme_two_sided = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        perm_a = pooled[:n_a]
        perm_b = pooled[n_a:]
        diff = perm_a.mean() - perm_b.mean()
        if abs(diff) >= abs(observed_diff):
            count_extreme_two_sided += 1

    p_two_sided = count_extreme_two_sided / n_perm
    return observed_diff, p_two_sided


def run_period(spike: pd.DataFrame, base: pd.DataFrame, years: tuple, label: str, rng):
    lo, hi = years
    s = spike[(spike["spike_week"].dt.year >= lo) & (spike["spike_week"].dt.year <= hi)]
    b = base[(base["random_week"].dt.year >= lo) & (base["random_week"].dt.year <= hi)]

    spike_pos = pd.to_numeric(s["pos_in_window_pos"], errors="coerce").dropna().to_numpy()
    base_pos = pd.to_numeric(b["pos_in_window_pos"], errors="coerce").dropna().to_numpy()

    diff, p_two = permutation_test_mean_diff(spike_pos, base_pos, N_PERMUTATIONS, rng)

    print(f"--- {label} ({lo}-{hi}) ---")
    print(f"Spike events: {len(s)}   Baseline events: {len(b)}")
    print(f"Spike mean: {spike_pos.mean():.3f}   Baseline mean: {base_pos.mean():.3f}   Diff: {diff:+.3f}")
    print(f"Two-sided p-value: {p_two:.4f}  {'(significant at 0.05)' if p_two < 0.05 else '(NOT significant at 0.05)'}")
    print()
    return p_two


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    spike = load_pooled(SPIKE_DIR, "*_zconjunction.csv", "spike_week")
    base = load_pooled(BASE_DIR, "*_baseline.csv", "random_week")

    if spike.empty or base.empty:
        print("Missing spike or baseline data — run GST_Zscore_Combiner_FinMkts.py and GST_Zscore_Baseline_FinMkts.py first.")
        return

    print(f"Total spike events: {len(spike)}   Total baseline events: {len(base)}\n")
    print("Position-timing effect (pos_in_window_pos: spike vs baseline), split out-of-sample\n")

    p_tune = run_period(spike, base, TUNE_YEARS, "TUNE", rng)
    p_test = run_period(spike, base, TEST_YEARS, "TEST", rng)

    print("--- Summary ---")
    print(f"Tune period ({TUNE_YEARS[0]}-{TUNE_YEARS[1]}): p={p_tune:.4f}  {'SIGNIFICANT' if p_tune < 0.05 else 'not significant'}")
    print(f"Test period ({TEST_YEARS[0]}-{TEST_YEARS[1]}): p={p_test:.4f}  {'SIGNIFICANT' if p_test < 0.05 else 'not significant'}")
    print(f"\n({N_PERMUTATIONS} permutations, seed={RANDOM_SEED} for reproducibility)")


if __name__ == "__main__":
    main()
