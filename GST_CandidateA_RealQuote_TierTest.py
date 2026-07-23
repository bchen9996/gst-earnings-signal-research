#!/usr/bin/env python3
# CANDIDATE A TEST (z>=10 vs 5<=z<10), run on the REAL QuantConnect
# ask-to-bid quote data (76-event sample) -- not modeled/recalibrated
# prices. Reuses real_pnl_pct exactly as computed by the QC validation
# script: (exit_value - entry_cost - fees) / entry_cost * 100, already net
# of the disclosed fee assumption.
#
# *** THIS SAMPLE WAS NOT COLLECTED AS A CLEAN, PRE-REGISTERED TEST FOR
# THIS SPECIFIC QUESTION *** -- it was pulled (stratified by ticker, not by
# z-tier) before this z-tier hypothesis was posed tonight. Every event in
# it has already been used in prior analyses this session (the IV markup
# recalibration, the volatility-surprise check). Results below are a
# FIRST READ on the hypothesis, not a clean confirmatory test. A genuinely
# clean version would require a fresh pull on canonical events NOT used in
# any analysis tonight, consistent with pre-registration principles
# (deciding the test before seeing data it could be fit to).
#
# Metrics (primary metric is dollar return per fixed premium -- NOT win
# rate or median, per the request):
#   - mean dollar P&L per event, at a flat $10,000 notional per trade
#     (matches this project's established FLAT_POSITION_SIZE convention)
#   - max drawdown across the tier's own chronological event sequence
#     (ordered by exit_date, reconstructed from spike_week via the
#     canonical entry=anchor+2/exit=anchor+6 rule -- not in the exported
#     QC file, joined back in from FixedWindow_PerEvent_Canonical.csv)
#   - expected shortfall: mean $ loss in the worst 10% and worst 20% of
#     outcomes (both reported, since "10-20%" was given as a range)
#   - worst single trade ($ and %)
#   - profit concentration: % of the tier's TOTAL net $ P&L contributed by
#     the single best event, and by the top 20% of events by P&L (same
#     definition as this project's earlier concentration/dependence audit)
#
# Output: Live Signal Engine/CandidateA_RealQuote_TierTest.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

VALIDATION_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_v2_76Events.csv"
CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "CandidateA_RealQuote_TierTest.csv"

HIGH_CONFIDENCE_Z_THRESHOLD = 10.0
FLAT_POSITION_SIZE = 10_000.0
STARTING_CAPITAL = 100_000.0


def max_drawdown(equity_curve: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity_curve)
    return float(((equity_curve - running_max) / running_max).min())


def tier_metrics(sub: pd.DataFrame, label: str) -> dict:
    sub = sub.sort_values("exit_date").reset_index(drop=True)
    n = len(sub)
    dollar_pnl = FLAT_POSITION_SIZE * (sub["real_pnl_pct"] / 100.0)

    mean_dollar_return = dollar_pnl.mean()

    equity = STARTING_CAPITAL + dollar_pnl.cumsum()
    equity_curve = np.concatenate([[STARTING_CAPITAL], equity.to_numpy()])
    mdd_pct = max_drawdown(equity_curve) * 100

    sorted_pnl = dollar_pnl.sort_values()
    n10 = max(1, round(n * 0.10))
    n20 = max(1, round(n * 0.20))
    es_10 = sorted_pnl.iloc[:n10].mean()
    es_20 = sorted_pnl.iloc[:n20].mean()

    worst_dollar = dollar_pnl.min()
    worst_pct = sub["real_pnl_pct"].min()

    total_pnl = dollar_pnl.sum()
    best_event_pnl = dollar_pnl.max()
    top20_pnl = sorted_pnl.iloc[-n20:].sum()
    pct_from_best = (best_event_pnl / total_pnl * 100) if total_pnl != 0 else None
    pct_from_top20 = (top20_pnl / total_pnl * 100) if total_pnl != 0 else None

    print(f"=== {label} (n={n}) ===")
    print(f"  Mean $ return per $10,000 premium: ${mean_dollar_return:,.0f}")
    print(f"  Max drawdown (tier's own equity curve): {mdd_pct:.1f}%")
    print(f"  Expected shortfall, worst 10% (n={n10}): ${es_10:,.0f}")
    print(f"  Expected shortfall, worst 20% (n={n20}): ${es_20:,.0f}")
    print(f"  Worst single trade: ${worst_dollar:,.0f}  ({worst_pct:+.1f}%)")
    print(f"  Total tier net $ P&L: ${total_pnl:,.0f}")
    print(f"  % of total profit from single best event: {pct_from_best:.1f}%" if pct_from_best is not None else "  n/a")
    print(f"  % of total profit from top 20% of events: {pct_from_top20:.1f}%" if pct_from_top20 is not None else "  n/a")
    print()

    return {
        "tier": label, "n": n, "mean_dollar_return_per_10k": round(mean_dollar_return, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "expected_shortfall_worst10pct": round(es_10, 2),
        "expected_shortfall_worst20pct": round(es_20, 2),
        "worst_trade_dollar": round(worst_dollar, 2), "worst_trade_pct": round(worst_pct, 2),
        "total_net_pnl": round(total_pnl, 2),
        "pct_profit_from_best_event": round(pct_from_best, 1) if pct_from_best is not None else None,
        "pct_profit_from_top20pct": round(pct_from_top20, 1) if pct_from_top20 is not None else None,
    }


def main():
    print("*** CANDIDATE A TEST: z>=10 vs 5<=z<10, REAL QuantConnect ask-to-bid quotes (n=76) ***\n")
    print("*** NOT a clean pre-registered sample for this specific question -- see header. ***\n")

    val = pd.read_csv(VALIDATION_PATH)
    val["spike_week"] = pd.to_datetime(val["spike_week"])
    print(f"Loaded {len(val)} real-quote events\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    canon["exit_date"] = pd.to_datetime(canon["exit_date"])
    join_cols = canon.set_index(["ticker", "spike_week"])[["fixed_window_zscore", "exit_date"]]

    merged = val.join(join_cols, on=["ticker", "spike_week"])
    missing = merged["fixed_window_zscore"].isna().sum()
    if missing:
        print(f"WARNING: {missing} events failed to join a z-score/exit_date from the canonical file -- dropped.\n")
    merged = merged.dropna(subset=["fixed_window_zscore", "exit_date"]).copy()
    print(f"Usable (joined) events: {len(merged)} / {len(val)}\n")

    merged.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    high = merged[merged["fixed_window_zscore"] >= HIGH_CONFIDENCE_Z_THRESHOLD]
    mid = merged[(merged["fixed_window_zscore"] >= 5) & (merged["fixed_window_zscore"] < HIGH_CONFIDENCE_Z_THRESHOLD)]

    high_stats = tier_metrics(high, "z>=10") if not high.empty else None
    mid_stats = tier_metrics(mid, "5<=z<10") if not mid.empty else None

    if high_stats and mid_stats:
        print("=== SIDE-BY-SIDE ===")
        summary = pd.DataFrame([high_stats, mid_stats])
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
