#!/usr/bin/env python3
# DIRECTIONAL BIAS CHECK -- cheap first check using data already collected:
# does a GST spike carry any directional lean (up vs down), or is the
# signal purely about MAGNITUDE (which the straddle backtest already
# exploits, direction-agnostic by construction) with zero directional
# information? Answers this before any post-earnings continuation/
# reversal pull is built -- if there's no directional lean here, a
# continuation/reversal strategy has nothing to work with.
#
# Uses the 152-event FixedWindow_PerEvent_Canonical.csv population. Signed
# cumulative return (entry_date -> exit_date, same window the straddle
# backtest already prices) is recomputed from local daily excess-return
# data -- the canonical CSV only stores pnl_pct (straddle P&L, direction-
# agnostic since a straddle pays off on magnitude either way), not the
# signed move itself.
#
# Output: Live Signal Engine/DirectionalBias_Analysis.csv

from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "DirectionalBias_Analysis.csv"

HIGH_CONFIDENCE_Z_THRESHOLD = 10.0


def binomial_two_sided_p(n_pos, n):
    """Exact two-sided binomial test p-value against p=0.5, no scipy dependency."""
    if n == 0:
        return None
    from math import comb
    k = min(n_pos, n - n_pos)
    p_point = lambda x: comb(n, x) * 0.5 ** n
    p_k = p_point(k)
    total = sum(p_point(x) for x in range(n + 1) if p_point(x) <= p_k + 1e-12)
    return min(total, 1.0)


def main():
    print("*** DIRECTIONAL BIAS CHECK (152-event canonical population) ***\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    canon["entry_date"] = pd.to_datetime(canon["entry_date"])
    canon["exit_date"] = pd.to_datetime(canon["exit_date"])
    qualifying = canon[(canon["qualifies_z5"] == True) & (canon["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Qualifying priced events: n={len(qualifying)}\n")

    sector_df = pd.read_csv(SECTOR_PATH)
    sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))

    daily_cache = {}
    rows = []
    for r in qualifying.itertuples(index=False):
        ticker = r.ticker
        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"

        row = {"ticker": ticker, "spike_week": r.spike_week.date(),
               "fixed_window_zscore": r.fixed_window_zscore,
               "sector": sector_map.get(ticker), "signed_move_pct": None,
               "direction": None, "note": ""}

        if daily.empty or ret_col not in daily.columns:
            row["note"] = "no daily excess-return data available"
            rows.append(row)
            continue

        cum_ret = base.cumulative_return(daily, ret_col, r.entry_date, r.exit_date)
        if cum_ret is None:
            row["note"] = "no realized-return data over entry-exit window"
            rows.append(row)
            continue

        row["signed_move_pct"] = round(cum_ret * 100, 3)
        row["direction"] = "positive" if cum_ret > 0 else ("negative" if cum_ret < 0 else "flat")
        rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    usable = result_df[result_df["direction"].notna() & (result_df["direction"] != "flat")].copy()
    print(f"Usable events (excludes exact-zero moves, if any): {len(usable)} / {len(qualifying)}\n")

    n_pos = (usable["direction"] == "positive").sum()
    n_neg = (usable["direction"] == "negative").sum()
    n = len(usable)
    pct_pos = n_pos / n * 100
    p_val = binomial_two_sided_p(n_pos, n)

    print("=== OVERALL ===")
    print(f"n={n}   positive={n_pos} ({pct_pos:.1f}%)   negative={n_neg} ({100-pct_pos:.1f}%)")
    print(f"Two-sided binomial test vs. 50/50: p={p_val:.4f}")
    if p_val is not None and p_val < 0.05:
        print("=> Statistically distinguishable from a coin flip at the 5% level.")
    else:
        print("=> NOT statistically distinguishable from a coin flip (no detectable directional lean overall).")
    print()

    print("=== BY Z-SCORE TIER ===")
    high = usable[usable["fixed_window_zscore"] >= HIGH_CONFIDENCE_Z_THRESHOLD]
    mid = usable[usable["fixed_window_zscore"] < HIGH_CONFIDENCE_Z_THRESHOLD]
    for label, sub in [("z>=10", high), ("z=5-9.99", mid)]:
        if sub.empty:
            print(f"{label}: n=0")
            continue
        sp = (sub["direction"] == "positive").sum()
        sn = (sub["direction"] == "negative").sum()
        sn_total = len(sub)
        pv = binomial_two_sided_p(sp, sn_total)
        print(f"{label}: n={sn_total}   positive={sp} ({sp/sn_total*100:.1f}%)   "
              f"negative={sn} ({sn/sn_total*100:.1f}%)   binomial p={pv:.4f}")
    print()

    print("=== BY SECTOR ===")
    sector_stats = usable.groupby("sector")["direction"].apply(
        lambda d: pd.Series({"n": len(d), "pct_positive": (d == "positive").mean() * 100})
    ).unstack()
    sector_stats = sector_stats.sort_values("n", ascending=False)
    print(sector_stats.to_string())
    print()

    print("=== BY TICKER (only tickers with n>=5) ===")
    ticker_stats = usable.groupby("ticker")["direction"].apply(
        lambda d: pd.Series({"n": len(d), "pct_positive": (d == "positive").mean() * 100})
    ).unstack()
    ticker_stats = ticker_stats[ticker_stats["n"] >= 5].sort_values("pct_positive", ascending=False)
    print(ticker_stats.to_string())


if __name__ == "__main__":
    main()
