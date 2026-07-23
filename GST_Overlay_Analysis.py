#!/usr/bin/env python3
# GST overlay on the insider-buying + Sloan-accruals "combined" signal.
#
# Hypothesis under test: does search-attention volatility AROUND an
# insider-buying/accruals signal indicate a stronger or weaker trade — NOT
# whether GST predicts returns on its own (already tested separately and
# found null). For every trade the "combined" variant fired (S&P 500 and
# S&P 600 universes, 90d and 180d horizons), check whether that ticker had
# a GST z-score spike (z>=2, 12-week rolling window, same methodology as
# GST_Zscore_Spikes.py / GST_Zscore_Spikes_Backtest.py) in the 21 days
# before the trade's SIGNAL date (test_date — when the insider+accruals
# info was known, not the later entry_date).
#
# Point-in-time note: a week's is_spike flag only depends on that week's own
# value vs. its trailing rolling stats (prior weeks only, via shift(1)), and
# only complete weeks (Week <= signal date) are considered — so this overlay
# introduces no look-ahead beyond what the z-score methodology already
# guarantees.
#
# Benchmarks match each universe's established convention: SPY for S&P 500
# trades, IJR for S&P 600 trades (small-cap index, isolates stock selection
# from the small-cap-vs-large-cap regime effect tested earlier).
#
# Input : Stock Screening/Backtest Data/backtest_variant_trades_combined_{h}d.csv
#         Stock Screening/Backtest Data SP600/backtest_variant_trades_combined_{h}d_vsIJR.csv
#         GST Data/Weekly zscore spikes (Backtest Universe)/<TICKER>_zspikes.csv
# Output: Stock Screening/Backtest Data/gst_overlay_sp500_{h}d.csv
#         Stock Screening/Backtest Data SP600/gst_overlay_sp600_{h}d.csv
#         Stock Screening/gst_overlay_summary.csv

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

import Backtest_Run as bt  # reuse sign_flip_test (pure function, no side effects on import)

GST_DIR = Path("GST Data") / "Weekly zscore spikes (Backtest Universe)"
GST_LOOKBACK_DAYS = 21
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

HORIZONS = [90, 180]

UNIVERSES = [
    {
        "name": "sp500",
        "trade_file": lambda h: Path("Stock Screening") / "Backtest Data" / f"backtest_variant_trades_combined_{h}d.csv",
        "excess_col": "excess_return",
        "benchmark_label": "SPY",
        "out_dir": Path("Stock Screening") / "Backtest Data",
    },
    {
        "name": "sp600",
        "trade_file": lambda h: Path("Stock Screening") / "Backtest Data SP600" / f"backtest_variant_trades_combined_{h}d_vsIJR.csv",
        "excess_col": "excess_return_vs_ijr",
        "benchmark_label": "IJR",
        "out_dir": Path("Stock Screening") / "Backtest Data SP600",
    },
]


def load_spike_weeks(ticker: str) -> pd.DataFrame:
    p = GST_DIR / f"{ticker}_zspikes.csv"
    if not p.exists():
        return pd.DataFrame(columns=["Week"])
    df = pd.read_csv(p)
    if "Week" not in df.columns or "is_spike" not in df.columns:
        return pd.DataFrame(columns=["Week"])
    df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
    if df["is_spike"].dtype == object:
        df["is_spike"] = df["is_spike"].astype(str).str.lower() == "true"
    spikes = df[df["is_spike"] == True][["Week"]].dropna()  # noqa: E712
    return spikes


def spikes_within_window(spike_weeks: pd.DataFrame, signal_date: pd.Timestamp, lookback_days: int) -> int:
    if spike_weeks.empty:
        return 0
    lo = signal_date - pd.Timedelta(days=lookback_days)
    mask = (spike_weeks["Week"] > lo) & (spike_weeks["Week"] <= signal_date)
    return int(mask.sum())


def two_sample_permutation_test(group_a: np.ndarray, group_b: np.ndarray, n_perm: int, rng: np.random.Generator):
    """Two-sided permutation test on the difference in means, GST-confirmed vs no-spike."""
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


def summarize_group(label: str, excess: np.ndarray, rng: np.random.Generator) -> dict:
    if len(excess) == 0:
        return {"group": label, "n_trades": 0, "win_rate": None, "avg_excess_return": None, "p_value_vs_zero": None}
    win_rate = float((excess > 0).mean())
    obs_mean, p_value = bt.sign_flip_test(excess, N_PERMUTATIONS, rng)
    return {
        "group": label, "n_trades": len(excess), "win_rate": round(win_rate, 4),
        "avg_excess_return": round(float(obs_mean), 5), "p_value_vs_zero": round(p_value, 4),
    }


def main():
    rng = np.random.default_rng(RANDOM_SEED)
    all_summary_rows = []

    for uni in UNIVERSES:
        print(f"\n{'='*70}\n{uni['name'].upper()} — combined signal, GST overlay (benchmark: {uni['benchmark_label']})\n{'='*70}")

        for h in HORIZONS:
            path = uni["trade_file"](h)
            tdf = pd.read_csv(path, parse_dates=["test_date"])

            spike_cache: dict[str, pd.DataFrame] = {}
            n_spikes_col = []
            confirmed_col = []
            for _, row in tdf.iterrows():
                ticker = row["ticker"]
                if ticker not in spike_cache:
                    spike_cache[ticker] = load_spike_weeks(ticker)
                n = spikes_within_window(spike_cache[ticker], row["test_date"], GST_LOOKBACK_DAYS)
                n_spikes_col.append(n)
                confirmed_col.append(n > 0)

            tdf["n_gst_spikes_in_window"] = n_spikes_col
            tdf["gst_confirmed"] = confirmed_col

            out_path = uni["out_dir"] / f"gst_overlay_{uni['name']}_{h}d.csv"
            tdf.to_csv(out_path, index=False)

            excess_col = uni["excess_col"]
            confirmed = tdf.loc[tdf["gst_confirmed"], excess_col].to_numpy()
            not_confirmed = tdf.loc[~tdf["gst_confirmed"], excess_col].to_numpy()

            row_confirmed = summarize_group("GST-confirmed", confirmed, rng)
            row_not = summarize_group("no GST spike", not_confirmed, rng)
            diff_obs, diff_p = two_sample_permutation_test(confirmed, not_confirmed, N_PERMUTATIONS, rng)

            for r in (row_confirmed, row_not):
                r["universe"] = uni["name"]
                r["horizon_days"] = h
                r["benchmark"] = uni["benchmark_label"]
                r["diff_vs_other_group"] = round(diff_obs, 5) if r["group"] == "GST-confirmed" and diff_obs is not None else None
                r["diff_p_value"] = round(diff_p, 4) if r["group"] == "GST-confirmed" and diff_p is not None else None
                all_summary_rows.append(r)

            print(f"\n--- Horizon {h}d ---")
            print(f"Total combined-signal trades: {len(tdf)}  "
                  f"(GST-confirmed: {len(confirmed)}, no spike: {len(not_confirmed)})")
            for r in (row_confirmed, row_not):
                if r["n_trades"] == 0:
                    print(f"  {r['group']:>15}: 0 trades")
                    continue
                sig = "significant" if r["p_value_vs_zero"] is not None and r["p_value_vs_zero"] < 0.05 else "not significant"
                print(f"  {r['group']:>15}: {r['n_trades']:4d} trades | win rate {r['win_rate']*100:5.1f}% | "
                      f"avg excess {r['avg_excess_return']*100:+6.2f}% | p(vs 0)={r['p_value_vs_zero']:.4f} ({sig})")
            if diff_obs is not None:
                diff_sig = "significant" if diff_p < 0.05 else "not significant"
                print(f"  Difference (confirmed - no spike): {diff_obs*100:+.2f} pts, "
                      f"p={diff_p:.4f} ({diff_sig})")
            else:
                print("  Difference: not computable (one group empty)")

    summary_df = pd.DataFrame(all_summary_rows)
    summary_path = Path("Stock Screening") / "gst_overlay_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\n\nWrote overlay summary to: {summary_path}")
    print("Wrote per-trade detail with gst_confirmed flag to each universe's Backtest Data folder.")


if __name__ == "__main__":
    main()
