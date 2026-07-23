#!/usr/bin/env python3
# EXCESS-MOVE ANALYSIS -- for the 152-event fixed-window canonical
# population, decomposes each priced trade into:
#   model_implied_move_pct = the Black-Scholes theoretical straddle cost
#     (fair value x COST_LOADING) on the backtest's synthetic S=K=100
#     notional -- this is NOT a real historically-quoted option ask
#     price. No historical option chain data (bid/ask by strike/expiry)
#     exists anywhere in this project for 2021-2025 -- yfinance only
#     serves CURRENT live chains, not historical ones -- so a genuine
#     market-implied move cannot be computed for these 152 events. This
#     is the best available proxy: the same trailing-realized-vol x
#     calibrated-markup model already used to price every trade in the
#     canonical backtest.
#   realized_move_pct = the actual |price change| from entry to exit,
#     on the same $100 notional (= "intrinsic" in the pricing code).
#   excess_move_pct = realized_move_pct - model_implied_move_pct.
#
# IMPORTANT CAVEAT, confirmed before running this: in this backtest,
# win is defined EXACTLY as intrinsic > cost, i.e. realized_move_pct >
# model_implied_move_pct. So "% of events where realized exceeded
# implied" is mathematically identical to the win rate already reported
# (76.3%) -- not an independent finding. This script still reports it
# for completeness, flagged as redundant with win rate, not new
# evidence. The genuinely new information is the excess-move MAGNITUDE
# and whether P&L size correlates more with raw realized move or with
# excess move specifically.
#
# To keep win/pnl_pct as the single source of truth (avoid any drift
# from re-deriving cumulative_return independently), intrinsic is
# derived algebraically from the ALREADY-STORED pnl_pct:
#   pnl_pct = (intrinsic - cost) / cost * 100  =>  intrinsic = cost * (1 + pnl_pct/100)
# cost itself is recomputed fresh (deterministic given stored
# spike_week/entry_date/exit_date and the same markup/vol model), since
# the canonical CSV did not persist it.
#
# Output: Live Signal Engine/ExcessMove_Analysis.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

import GST_FixedWindow_PerEvent_Canonical as base

CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "ExcessMove_Analysis.csv"


def main():
    print("*** EXCESS-MOVE ANALYSIS: model-implied vs. realized move, 152-event canonical set ***\n")

    markup = base.load_calibrated_near_earnings_markup()
    df = pd.read_csv(CANONICAL_PATH)
    priced = df[(df["qualifies_z5"] == True) & (df["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Priced events in canonical set: n={len(priced)}\n")

    priced["spike_week"] = pd.to_datetime(priced["spike_week"])
    priced["entry_date"] = pd.to_datetime(priced["entry_date"])
    priced["exit_date"] = pd.to_datetime(priced["exit_date"])

    daily_cache = {}
    rows = []
    skipped = 0
    for r in priced.itertuples(index=False):
        ticker = r.ticker
        if ticker not in daily_cache:
            daily_cache[ticker] = base.load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"

        sigma = base.trailing_realized_vol(daily, ret_col, r.spike_week - timedelta(days=7))
        if sigma is None:
            print(f"  SKIP {ticker} {r.spike_week.date()}: could not recompute trailing vol")
            skipped += 1
            continue
        iv = sigma * markup
        dte_days = (r.exit_date - r.entry_date).days
        T = dte_days / 365.0
        fair = base.bs_straddle_price(100.0, 100.0, T, base.RISK_FREE_RATE, iv)
        if fair is None:
            print(f"  SKIP {ticker} {r.spike_week.date()}: could not recompute fair value")
            skipped += 1
            continue
        cost = fair * base.COST_LOADING
        intrinsic = cost * (1 + r.pnl_pct / 100.0)  # derived from stored pnl_pct, not re-derived from raw returns

        implied_move_pct = cost           # % of $100 notional
        realized_move_pct = intrinsic     # % of $100 notional
        excess_move_pct = realized_move_pct - implied_move_pct

        # internal-consistency check: win must equal (excess_move_pct > 0) by construction
        consistent = (r.win == (excess_move_pct > 0))

        rows.append({
            "ticker": ticker, "spike_week": r.spike_week.date(),
            "entry_date": r.entry_date.date(), "exit_date": r.exit_date.date(),
            "fixed_window_zscore": r.fixed_window_zscore,
            "model_implied_move_pct": round(implied_move_pct, 3),
            "realized_move_pct": round(realized_move_pct, 3),
            "excess_move_pct": round(excess_move_pct, 3),
            "realized_exceeds_implied": bool(excess_move_pct > 0),
            "pnl_pct": r.pnl_pct, "win": r.win,
            "win_matches_excess_sign": consistent,
        })

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}  (n={len(result_df)}, skipped={skipped})\n")

    n = len(result_df)
    pct_realized_exceeds = result_df["realized_exceeds_implied"].mean() * 100
    median_excess = result_df["excess_move_pct"].median()
    n_mismatch = (~result_df["win_matches_excess_sign"]).sum()

    corr_pearson_realized = result_df["pnl_pct"].corr(result_df["realized_move_pct"], method="pearson")
    corr_pearson_excess = result_df["pnl_pct"].corr(result_df["excess_move_pct"], method="pearson")
    corr_spearman_realized = result_df["pnl_pct"].corr(result_df["realized_move_pct"], method="spearman")
    corr_spearman_excess = result_df["pnl_pct"].corr(result_df["excess_move_pct"], method="spearman")

    print("=== RESULTS ===")
    print(f"n = {n}")
    print(f"Internal-consistency check (win == realized>implied by construction): "
          f"{n - n_mismatch}/{n} match ({n_mismatch} mismatches)")
    print(f"% of events where realized move exceeded model-implied move: {pct_realized_exceeds:.1f}%   "
          f"[NOTE: this is definitionally identical to win rate in this backtest, not independent evidence]")
    print(f"Median excess move (realized - implied), all {n} events: {median_excess:+.2f} percentage points "
          f"(of $100 notional)")
    print()
    print("Correlation with pnl_pct (does P&L size track raw realized move, or excess move specifically?):")
    print(f"  pnl_pct vs. realized_move_pct:  Pearson r={corr_pearson_realized:.3f}   Spearman rho={corr_spearman_realized:.3f}")
    print(f"  pnl_pct vs. excess_move_pct:    Pearson r={corr_pearson_excess:.3f}   Spearman rho={corr_spearman_excess:.3f}")
    stronger = "excess_move_pct" if abs(corr_pearson_excess) > abs(corr_pearson_realized) else "realized_move_pct"
    print(f"  -> P&L correlates more strongly with: {stronger}")


if __name__ == "__main__":
    main()
