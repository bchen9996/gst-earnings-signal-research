#!/usr/bin/env python3
# GST Zscore Volatility Test — per-ticker breakdown. Checks whether the
# pooled volatility effect (|max_abs_excess_pct|: spike vs baseline,
# +2.976 pts pooled, p=0.0000, confirmed OOS in both tune and test periods)
# is broadly consistent across the 15 original tickers, or concentrated in
# just one or two names — same question already asked of the position-
# timing effect at the pooled level, now applied per-ticker to this effect.
#
# Uses the existing original-project GST data (15 tickers, 2014-2019) — no
# new data pulled. Per-ticker samples are small (roughly 15-30 spike events
# and 25 baseline events each), so per-ticker p-values are underpowered
# individually — the sign and rough magnitude of the diff across tickers is
# the main thing worth reading, not strict per-ticker significance.

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

SPIKE_DIR = Path("Conjunction Zscore")
BASE_DIR = Path("Conjunction Zscore Baseline")
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]


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

    return observed_diff, count_extreme_two_sided / n_perm


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    rows = []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        bp = BASE_DIR / f"{ticker}_baseline.csv"
        if not sp.exists() or not bp.exists():
            print(f"[{ticker}] missing spike or baseline file, skipping")
            continue

        s = pd.read_csv(sp)
        b = pd.read_csv(bp)

        spike_vol = pd.to_numeric(s["max_abs_excess_pct"], errors="coerce").dropna().abs().to_numpy()
        base_vol = pd.to_numeric(b["max_abs_excess_pct"], errors="coerce").dropna().abs().to_numpy()

        if len(spike_vol) == 0 or len(base_vol) == 0:
            print(f"[{ticker}] empty spike or baseline series, skipping")
            continue

        diff, p_two = permutation_test_mean_diff(spike_vol, base_vol, N_PERMUTATIONS, rng)

        rows.append({
            "ticker": ticker,
            "n_spike": len(spike_vol),
            "n_baseline": len(base_vol),
            "spike_mean": round(float(spike_vol.mean()), 3),
            "baseline_mean": round(float(base_vol.mean()), 3),
            "diff": round(float(diff), 3),
            "p_value": round(p_two, 4),
        })

    result = pd.DataFrame(rows).sort_values("diff", ascending=False)
    out_path = Path("GST_Zscore_VolatilityTest_ByTicker_results.csv")
    result.to_csv(out_path, index=False)

    n_positive = int((result["diff"] > 0).sum())
    n_negative = int((result["diff"] < 0).sum())
    n_sig_positive = int(((result["diff"] > 0) & (result["p_value"] < 0.05)).sum())

    print("--- Per-ticker volatility effect: spike mean - baseline mean of |max_abs_excess_pct| ---\n")
    print(result.to_string(index=False))

    print(f"\n{n_positive}/{len(result)} tickers show a positive diff (spike > baseline volatility)")
    print(f"{n_negative}/{len(result)} tickers show a negative diff (spike < baseline volatility)")
    print(f"{n_sig_positive}/{len(result)} tickers individually significant at p<0.05 in the positive direction")
    print(f"\nWrote per-ticker results to: {out_path}")


if __name__ == "__main__":
    main()
