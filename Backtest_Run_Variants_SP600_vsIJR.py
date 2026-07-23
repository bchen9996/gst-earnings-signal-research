#!/usr/bin/env python3
# Point-in-time backtest — S&P 600 signal decomposition, re-benchmarked vs IJR.
#
# The prior S&P 600 run (Backtest_Run_Variants_SP600.py) found statistically
# significant NEGATIVE excess returns vs SPY at 180d for all three variants.
# That's likely a small-cap-vs-large-cap regime effect (small caps broadly
# underperformed the S&P 500 over 2022-2025), not evidence about the
# insider-buying/accruals signals themselves — benchmarking a small-cap
# strategy against a large-cap index conflates stock selection with the
# small-cap factor's performance.
#
# This script reuses the EXACT same trades already generated (same entries,
# same exits, same signals, same test dates, same 20bps cost) and only
# swaps the benchmark leg: SPY -> IJR (iShares Core S&P Small-Cap ETF,
# tracks the S&P 600 itself), so excess return now measures stock-selection
# skill WITHIN the small-cap universe, isolated from the small-cap regime
# effect.
#
# No new SEC data. Only new data pulled: IJR daily prices (one symbol).
#
# Input : Stock Screening/Backtest Data SP600/backtest_variant_trades_<variant>_<h>d.csv
# Output: Stock Screening/Backtest Data SP600/backtest_variant_trades_<variant>_<h>d_vsIJR.csv
#         Stock Screening/Backtest Data SP600/backtest_variant_summary_vsIJR.csv

from __future__ import annotations
from datetime import timedelta
import requests
import urllib3
import numpy as np
import pandas as pd
import yfinance as yf

import Backtest_Run_SP600 as bt  # reuse DATA_DIR, price lookup helpers, sign_flip_test

urllib3.disable_warnings()

DATA_DIR = bt.DATA_DIR
HORIZONS = bt.HORIZONS
N_PERMUTATIONS = bt.N_PERMUTATIONS
RANDOM_SEED = bt.RANDOM_SEED
VARIANTS = ["insider_only", "sloan_only", "combined"]
BENCHMARK_SYMBOL = "IJR"


def fetch_benchmark_series() -> pd.Series:
    # Cover the full range any trade's entry/exit date could fall in.
    all_dates = []
    for variant in VARIANTS:
        for h in HORIZONS:
            path = DATA_DIR / f"backtest_variant_trades_{variant}_{h}d.csv"
            tdf = pd.read_csv(path, parse_dates=["entry_date", "exit_date"])
            if not tdf.empty:
                all_dates.extend(tdf["entry_date"].tolist())
                all_dates.extend(tdf["exit_date"].tolist())

    start = (min(all_dates) - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (max(all_dates) + timedelta(days=10)).strftime("%Y-%m-%d")

    print(f"Downloading {BENCHMARK_SYMBOL} prices ({start} to {end})...")
    session = requests.Session()
    session.verify = False
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    df = yf.download(BENCHMARK_SYMBOL, start=start, end=end, session=session,
                      progress=False, auto_adjust=True)
    s = df["Close"][BENCHMARK_SYMBOL].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def main():
    ijr = fetch_benchmark_series()
    print(f"Got {len(ijr)} {BENCHMARK_SYMBOL} price points.\n")

    rng = np.random.default_rng(RANDOM_SEED)
    summary_rows = []

    for variant in VARIANTS:
        for h in HORIZONS:
            in_path = DATA_DIR / f"backtest_variant_trades_{variant}_{h}d.csv"
            tdf = pd.read_csv(in_path, parse_dates=["entry_date", "exit_date"])

            if tdf.empty:
                summary_rows.append({"variant": variant, "horizon_days": h, "n_trades": 0,
                                      "win_rate": None, "avg_excess_return": None,
                                      "avg_net_return": None, "avg_benchmark_return": None, "p_value": None})
                continue

            ijr_entry = tdf["entry_date"].apply(lambda d: ijr.asof(d))
            ijr_exit = tdf["exit_date"].apply(lambda d: ijr.asof(d))
            benchmark_return = ijr_exit / ijr_entry - 1

            tdf["ijr_entry"] = ijr_entry
            tdf["ijr_exit"] = ijr_exit
            tdf["benchmark_return"] = benchmark_return
            tdf["excess_return_vs_ijr"] = tdf["net_return"] - benchmark_return

            out_path = DATA_DIR / f"backtest_variant_trades_{variant}_{h}d_vsIJR.csv"
            tdf.to_csv(out_path, index=False)

            excess = tdf["excess_return_vs_ijr"].to_numpy()
            win_rate = float((excess > 0).mean())
            obs_mean, p_value = bt.sign_flip_test(excess, N_PERMUTATIONS, rng)

            summary_rows.append({
                "variant": variant, "horizon_days": h, "n_trades": len(tdf), "win_rate": round(win_rate, 4),
                "avg_excess_return": round(float(obs_mean), 5),
                "avg_net_return": round(float(tdf["net_return"].mean()), 5),
                "avg_benchmark_return": round(float(benchmark_return.mean()), 5),
                "p_value": round(p_value, 4),
            })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(DATA_DIR / "backtest_variant_summary_vsIJR.csv", index=False)

    print(f"=== Signal decomposition vs {BENCHMARK_SYMBOL} (same-universe small-cap benchmark) ===\n")
    for h in HORIZONS:
        print(f"--- Horizon {h}d ---")
        sub = summary_df[summary_df["horizon_days"] == h]
        for _, r in sub.iterrows():
            if r["n_trades"] == 0:
                print(f"{r['variant']:>15}: 0 trades")
                continue
            sig = "significant" if (r["p_value"] is not None and r["p_value"] < 0.05) else "not significant"
            print(f"{r['variant']:>15}: {int(r['n_trades']):4d} trades | win rate {r['win_rate']*100:5.1f}% | "
                  f"avg excess {r['avg_excess_return']*100:+6.2f}% | avg {BENCHMARK_SYMBOL} return "
                  f"{r['avg_benchmark_return']*100:+6.2f}% | p={r['p_value']:.4f} ({sig})")
        print()

    print(f"Wrote re-benchmarked trade detail and summary to: {DATA_DIR}")


if __name__ == "__main__":
    main()
