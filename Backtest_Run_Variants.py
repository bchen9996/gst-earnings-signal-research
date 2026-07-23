#!/usr/bin/env python3
# Point-in-time backtest — signal decomposition.
#
# Re-runs the SAME point-in-time engine as Backtest_Run.py (same 150-ticker
# universe, same already-pulled data, same 13 quarterly test dates, same
# 90d/180d horizons, same 20bps round-trip cost) but splits the combined
# signal into its two components, tested separately:
#   (a) insider_only — any Form 4 open-market buy in the trailing 90 days,
#       NO Sloan accruals filter applied
#   (b) sloan_only    — not in that test date's top-quartile-accruals group,
#       NO insider buying requirement
#   (c) combined      — both required (reproduces Backtest_Run.py's result,
#       included here for direct side-by-side comparison)
#
# No new SEC calls — reuses insider_buys_raw.csv, accrual_facts_raw.csv,
# and backtest_prices.csv from the prior pull, and imports the point-in-time
# helper functions directly from Backtest_Run.py rather than duplicating
# them.
#
# Output: Stock Screening/Backtest Data/backtest_variant_trades_<variant>_<h>d.csv
#         Stock Screening/Backtest Data/backtest_variant_summary.csv
#         Stock Screening/Backtest Data/backtest_variant_signal_log.csv

from __future__ import annotations
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

import Backtest_Run as bt  # reuse point-in-time engine + constants; importing does not run main()

DATA_DIR = bt.DATA_DIR
HORIZONS = bt.HORIZONS
N_PERMUTATIONS = bt.N_PERMUTATIONS
RANDOM_SEED = bt.RANDOM_SEED

VARIANTS = [
    ("insider_only", True, False),
    ("sloan_only", False, True),
    ("combined", True, True),
]


def main():
    universe = pd.read_csv(DATA_DIR / "backtest_universe.csv")
    tickers = universe["ticker"].tolist()

    buys = pd.read_csv(DATA_DIR / "insider_buys_raw.csv")
    buys["transaction_date"] = pd.to_datetime(buys["transaction_date"])
    buys["filing_date"] = pd.to_datetime(buys["filing_date"])

    facts = pd.read_csv(DATA_DIR / "accrual_facts_raw.csv")
    facts["filed"] = pd.to_datetime(facts["filed"])

    prices = pd.read_csv(DATA_DIR / "backtest_prices.csv")
    prices["Date"] = pd.to_datetime(prices["Date"])

    price_series = {t: g.set_index("Date")["close"].sort_index() for t, g in prices.groupby("ticker")}
    spy = price_series["SPY"]

    buys_by_ticker = {t: g for t, g in buys.groupby("ticker")} if not buys.empty else {}
    facts_by_ticker = {t: g for t, g in facts.groupby("ticker")} if not facts.empty else {}

    now = datetime.now(timezone.utc)
    test_date_end = (now - timedelta(days=bt.END_BUFFER_DAYS)).date()
    test_date_start = (pd.Timestamp(test_date_end) - pd.Timedelta(days=bt.LOOKBACK_YEARS * 365)).date()
    test_dates = pd.date_range(test_date_start, test_date_end, freq=f"{bt.TEST_DATE_STEP_DAYS}D")

    print(f"Test dates ({len(test_dates)}): {test_dates[0].date()} to {test_dates[-1].date()}\n")

    trades = {name: {h: [] for h in HORIZONS} for name, _, _ in VARIANTS}
    signal_log = []

    for test_date in test_dates:
        rows = []
        for ticker in tickers:
            tbuys = buys_by_ticker.get(ticker, pd.DataFrame(columns=["filing_date", "transaction_date"]))
            insider_flag, n_buys = bt.insider_signal_asof(tbuys, test_date)

            tfacts = facts_by_ticker.get(ticker)
            accr = bt.accruals_asof(tfacts, test_date) if tfacts is not None else None

            rows.append({"ticker": ticker, "insider_flag": insider_flag, "n_buys": n_buys, "accr": accr})

        day_df = pd.DataFrame(rows)
        valid = day_df["accr"].notna()
        n_valid = int(valid.sum())
        if n_valid >= 4:
            q75 = day_df.loc[valid, "accr"].quantile(bt.SLOAN_CAUTION_QUANTILE)
            day_df["sloan_ok"] = valid & (day_df["accr"] < q75)
        else:
            day_df["sloan_ok"] = False

        log_row = {"test_date": test_date.date(), "n_insider_flagged": int(day_df["insider_flag"].sum()),
                   "n_accruals_valid": n_valid}

        for name, use_insider, use_sloan in VARIANTS:
            if use_insider and use_sloan:
                mask = day_df["insider_flag"] & day_df["sloan_ok"]
            elif use_insider:
                mask = day_df["insider_flag"]
            else:
                mask = day_df["sloan_ok"]

            fired = day_df[mask]
            log_row[f"n_fired_{name}"] = len(fired)

            for _, sig_row in fired.iterrows():
                ticker = sig_row["ticker"]
                s = price_series.get(ticker)
                if s is None or s.empty:
                    continue
                entry_date, entry_price = bt.price_on_or_after(s, test_date)
                spy_entry_date, spy_entry_price = bt.price_on_or_after(spy, test_date)
                if entry_price is None or spy_entry_price is None:
                    continue

                for h in HORIZONS:
                    exit_target = entry_date + pd.Timedelta(days=h)
                    exit_date, exit_price = bt.price_on_or_before(s, exit_target)
                    spy_exit_date, spy_exit_price = bt.price_on_or_before(spy, exit_target)
                    if exit_price is None or spy_exit_price is None or exit_date <= entry_date:
                        continue

                    raw_return = exit_price / entry_price - 1
                    net_return = raw_return - 2 * bt.TRANSACTION_COST_ONE_WAY
                    spy_return = spy_exit_price / spy_entry_price - 1
                    excess_return = net_return - spy_return

                    trades[name][h].append({
                        "test_date": test_date.date(), "ticker": ticker,
                        "n_insider_buys": int(sig_row["n_buys"]), "accruals_ratio": sig_row["accr"],
                        "entry_date": entry_date.date(), "entry_price": entry_price,
                        "exit_date": exit_date.date(), "exit_price": exit_price,
                        "raw_return": raw_return, "net_return": net_return,
                        "spy_return": spy_return, "excess_return": excess_return,
                    })

        signal_log.append(log_row)

    signal_log_df = pd.DataFrame(signal_log)
    signal_log_df.to_csv(DATA_DIR / "backtest_variant_signal_log.csv", index=False)
    print("--- Signal fire counts per test date, by variant ---")
    print(signal_log_df.to_string(index=False))

    rng = np.random.default_rng(RANDOM_SEED)
    summary_rows = []
    for name, _, _ in VARIANTS:
        for h in HORIZONS:
            tdf = pd.DataFrame(trades[name][h])
            out_path = DATA_DIR / f"backtest_variant_trades_{name}_{h}d.csv"
            tdf.to_csv(out_path, index=False)

            if tdf.empty:
                summary_rows.append({"variant": name, "horizon_days": h, "n_trades": 0, "win_rate": None,
                                      "avg_excess_return": None, "avg_net_return": None,
                                      "avg_spy_return": None, "p_value": None})
                continue

            excess = tdf["excess_return"].to_numpy()
            win_rate = float((excess > 0).mean())
            obs_mean, p_value = bt.sign_flip_test(excess, N_PERMUTATIONS, rng)

            summary_rows.append({
                "variant": name, "horizon_days": h, "n_trades": len(tdf), "win_rate": round(win_rate, 4),
                "avg_excess_return": round(float(obs_mean), 5),
                "avg_net_return": round(float(tdf["net_return"].mean()), 5),
                "avg_spy_return": round(float(tdf["spy_return"].mean()), 5),
                "p_value": round(p_value, 4),
            })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(DATA_DIR / "backtest_variant_summary.csv", index=False)

    print("\n=== Signal decomposition: combined vs. each component alone ===\n")
    for h in HORIZONS:
        print(f"--- Horizon {h}d ---")
        sub = summary_df[summary_df["horizon_days"] == h]
        for _, r in sub.iterrows():
            if r["n_trades"] == 0:
                print(f"{r['variant']:>15}: 0 trades")
                continue
            sig = "significant" if (r["p_value"] is not None and r["p_value"] < 0.05) else "not significant"
            print(f"{r['variant']:>15}: {int(r['n_trades']):4d} trades | win rate {r['win_rate']*100:5.1f}% | "
                  f"avg excess {r['avg_excess_return']*100:+6.2f}% | p={r['p_value']:.4f} ({sig})")
        print()

    print(f"Wrote per-variant trade detail and summary to: {DATA_DIR}")


if __name__ == "__main__":
    main()
