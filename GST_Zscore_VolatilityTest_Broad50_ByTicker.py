#!/usr/bin/env python3
# GST Zscore Volatility Test — Broad50 per-ticker breakdown, same format as
# GST_Zscore_VolatilityTest_ByTicker.py (the original 15-ticker version).
#
# Additionally flags tickers with a SHORT (<=2 character) or COMMON-ENGLISH-
# WORD symbol, and runs the pooled spike-vs-baseline volatility permutation
# test separately on the "ambiguous symbol" subset vs the "clear symbol"
# subset. This tests directly — not just by eyeballing — the proposed
# explanation for why the pooled Broad50 effect (+0.679 pts) came in much
# smaller than the original 15-ticker effect (+2.976 pts): that ambiguous
# ticker symbols make GST search volume a noisier proxy for stock-specific
# attention, diluting the effect.
#
# Classification rule (disclosed, not cherry-picked): a symbol is flagged
# AMBIGUOUS if len(symbol) <= 2, OR the symbol (case-insensitive) is a
# common English word. The word list below is a hand-curated, deliberately
# conservative set — only unambiguous, common dictionary words are
# included (e.g. "are", "low"); borderline abbreviations like "reg" or
# "pkg" are NOT flagged, to avoid stacking the deck toward confirming the
# hypothesis. DELL ("dell" = a small wooded valley) is also deliberately
# NOT flagged, since it's an obscure/archaic word dominated by an
# unambiguous, globally-recognized brand association — flagging it would
# be a stretch in the other direction.

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

SPIKE_DIR = Path("Conjunction Zscore (Broad50)")
BASE_DIR = Path("Conjunction Zscore Baseline (Broad50)")
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

TICKERS = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'ARE', 'AVB', 'BKR', 'BRK-B', 'BRO', 'CCL',
    'CI', 'CL', 'COF', 'COHR', 'CTSH', 'CTVA', 'DELL', 'DVN', 'EL', 'ERIE',
    'FE', 'GPC', 'GPN', 'HD', 'JBL', 'KO', 'LDOS', 'LNT', 'LOW', 'MCHP',
    'MCK', 'MDT', 'NCLH', 'NI', 'PKG', 'PLD', 'PM', 'PNW', 'RCL', 'REG',
    'ROP', 'RTX', 'STZ', 'SYF', 'SYK', 'T', 'TT', 'UAL', 'VZ', 'XOM',
]

COMMON_WORDS = {"are", "low", "bro"}  # conservative, hand-curated — see header


def is_ambiguous(ticker: str) -> bool:
    base = ticker.split("-")[0]  # BRK-B -> BRK for length purposes
    if len(base) <= 2:
        return True
    return base.lower() in COMMON_WORDS


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
    spike_by_group = {"ambiguous": [], "clear": []}
    base_by_group = {"ambiguous": [], "clear": []}

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
        ambiguous = is_ambiguous(ticker)
        group = "ambiguous" if ambiguous else "clear"
        spike_by_group[group].append(spike_vol)
        base_by_group[group].append(base_vol)

        rows.append({
            "ticker": ticker,
            "ambiguous_symbol": ambiguous,
            "n_spike": len(spike_vol),
            "n_baseline": len(base_vol),
            "spike_mean": round(float(spike_vol.mean()), 3),
            "baseline_mean": round(float(base_vol.mean()), 3),
            "diff": round(float(diff), 3),
            "p_value": round(p_two, 4),
        })

    result = pd.DataFrame(rows).sort_values("diff", ascending=False)
    out_path = Path("GST_Zscore_VolatilityTest_Broad50_ByTicker_results.csv")
    result.to_csv(out_path, index=False)

    print("--- Per-ticker volatility effect: spike mean - baseline mean of |max_abs_excess_pct| (Broad50) ---\n")
    print(result.to_string(index=False))

    for label, grp in [("Ambiguous-symbol tickers", result[result["ambiguous_symbol"]]),
                        ("Clear-symbol tickers", result[~result["ambiguous_symbol"]])]:
        n_pos = int((grp["diff"] > 0).sum())
        n_sig_pos = int(((grp["diff"] > 0) & (grp["p_value"] < 0.05)).sum())
        print(f"\n{label} (n={len(grp)}): {n_pos}/{len(grp)} positive diff, "
              f"{n_sig_pos}/{len(grp)} individually significant positive, "
              f"mean diff = {grp['diff'].mean():+.3f} pts")

    print("\n\n=== Group-level pooled test: ambiguous-symbol subset vs clear-symbol subset ===")
    for label, key in [("Ambiguous-symbol subset", "ambiguous"), ("Clear-symbol subset", "clear")]:
        spike_pool = np.concatenate(spike_by_group[key]) if spike_by_group[key] else np.array([])
        base_pool = np.concatenate(base_by_group[key]) if base_by_group[key] else np.array([])
        if len(spike_pool) == 0 or len(base_pool) == 0:
            print(f"\n{label}: no data")
            continue
        diff, p_two = permutation_test_mean_diff(spike_pool, base_pool, N_PERMUTATIONS, rng)
        print(f"\n{label}:")
        print(f"  Spike events: {len(spike_pool)}   Baseline events: {len(base_pool)}")
        print(f"  Spike mean: {spike_pool.mean():.3f}%   Baseline mean: {base_pool.mean():.3f}%   "
              f"Diff: {diff:+.3f} pts")
        print(f"  Two-sided p-value: {p_two:.4f}  {'(significant at 0.05)' if p_two < 0.05 else '(NOT significant at 0.05)'}")

    print(f"\n\nWrote per-ticker results to: {out_path}")


if __name__ == "__main__":
    main()
