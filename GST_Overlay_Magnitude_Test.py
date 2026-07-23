#!/usr/bin/env python3
# GST overlay MAGNITUDE test — risk/position-sizing hypothesis.
#
# GST_Overlay_Analysis.py already tested DIRECTION: do trades with a nearby
# GST spike show a higher excess RETURN than trades without one (found: no
# significant effect either way). This tests MAGNITUDE instead: do trades
# with a nearby GST spike show a LARGER absolute excess return, regardless
# of sign? If so, that would support using GST as a variance/risk signal
# (position sizing) rather than a directional one — the same distinction
# already drawn for the standalone GST volatility finding
# (GST_Zscore_VolatilityTest.py), now applied to the insider+accruals
# "combined" trades specifically instead of raw spike-vs-baseline weeks.
#
# Uses the existing gst_overlay_*.csv files (already have gst_confirmed
# flag + excess_return / excess_return_vs_ijr columns) — no new data pulled,
# same two-sample permutation-test methodology already built.

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

N_PERMUTATIONS = 10000
RANDOM_SEED = 42
HORIZONS = [90, 180]

UNIVERSES = [
    {
        "name": "sp500",
        "file": lambda h: Path("Stock Screening") / "Backtest Data" / f"gst_overlay_sp500_{h}d.csv",
        "excess_col": "excess_return",
        "benchmark_label": "SPY",
    },
    {
        "name": "sp600",
        "file": lambda h: Path("Stock Screening") / "Backtest Data SP600" / f"gst_overlay_sp600_{h}d.csv",
        "excess_col": "excess_return_vs_ijr",
        "benchmark_label": "IJR",
    },
]


def two_sample_permutation_test(group_a: np.ndarray, group_b: np.ndarray, n_perm: int, rng: np.random.Generator):
    if len(group_a) == 0 or len(group_b) == 0:
        return None, None
    observed_diff = group_a.mean() - group_b.mean()
    pooled = np.concatenate([group_a, group_b])
    n_a = len(group_a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(diff) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    rng = np.random.default_rng(RANDOM_SEED)
    all_rows = []

    for uni in UNIVERSES:
        print(f"\n{'='*70}\n{uni['name'].upper()} — combined signal, GST MAGNITUDE overlay (benchmark: {uni['benchmark_label']})\n{'='*70}")

        for h in HORIZONS:
            path = uni["file"](h)
            if not path.exists():
                print(f"  [{h}d] file not found: {path} — skipping")
                continue
            tdf = pd.read_csv(path)

            abs_excess = tdf[uni["excess_col"]].abs()
            confirmed = abs_excess[tdf["gst_confirmed"]].to_numpy()
            not_confirmed = abs_excess[~tdf["gst_confirmed"]].to_numpy()

            diff, p_value = two_sample_permutation_test(confirmed, not_confirmed, N_PERMUTATIONS, rng)

            print(f"\n--- Horizon {h}d ---")
            print(f"Total trades: {len(tdf)}  (GST-confirmed: {len(confirmed)}, no spike: {len(not_confirmed)})")
            print(f"GST-confirmed  mean |excess return|: {confirmed.mean()*100:6.2f}%")
            print(f"No spike       mean |excess return|: {not_confirmed.mean()*100:6.2f}%")
            if diff is not None:
                sig = "significant" if p_value < 0.05 else "not significant"
                print(f"Diff (confirmed - no spike): {diff*100:+.2f} pts, p={p_value:.4f} ({sig})")
            else:
                print("Diff: not computable (one group empty)")

            all_rows.append({
                "universe": uni["name"], "horizon_days": h, "benchmark": uni["benchmark_label"],
                "n_confirmed": len(confirmed), "n_no_spike": len(not_confirmed),
                "mean_abs_excess_confirmed": round(float(confirmed.mean()), 5) if len(confirmed) else None,
                "mean_abs_excess_no_spike": round(float(not_confirmed.mean()), 5) if len(not_confirmed) else None,
                "diff": round(float(diff), 5) if diff is not None else None,
                "p_value": round(p_value, 4) if p_value is not None else None,
            })

    summary_df = pd.DataFrame(all_rows)
    out_path = Path("Stock Screening") / "gst_overlay_magnitude_summary.csv"
    summary_df.to_csv(out_path, index=False)
    print(f"\n\nWrote summary to: {out_path}")


if __name__ == "__main__":
    main()
