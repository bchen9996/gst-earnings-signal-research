#!/usr/bin/env python3
# SHORT-VOLATILITY DEFENSIVE-FILTER TEST -- does using GST as a filter to
# AVOID high-GST earnings dates improve a short-ATM-straddle strategy's
# risk profile, even if it doesn't change mean return much?
#
# THE "TRADE EVERY EARNINGS DATE BLIND" BASELINE: per user decision, this
# uses MatchedControlGroup_CanonicalRecompute.csv's 133 usable matched
# pairs -- each canonical GST signal event (z>=5) paired with a matched
# NON-signal earnings date for a similar ticker/sector/vol/timing profile
# (same methodology as GST_MatchedControlGroup_CanonicalRecompute.py).
# The combined universe (133 signal + 133 control = 266 events) is the
# "sell every earnings date, no GST filter" baseline. Excluding the
# signal side entirely = "avoid every GST-flagged date." Excluding only
# the z>=10 subset = "avoid just the rare, most extreme tier."
#
# SHORT SIDE = SELL the ATM straddle (opposite side of every long
# simulation in this project). short_pnl_pct = -long_pnl_pct for the
# same entry/exit timing and prices.
#
# *** DISCLOSED APPROXIMATION, PER USER DECISION *** for events with real
# QC-quoted prices: short_pnl_pct is approximated as the NEGATION of the
# long side's real ask-to-bid return, NOT a true short-side simulation.
# A real short seller trades the OPPOSITE legs (sells at entry BID, buys
# back at exit ASK) -- legs this project never captured (only entry ASK
# and exit BID were exported). This negation therefore UNDERSTATES the
# short seller's true cost/risk -- every real-quote metric below should be
# read as a best-case bound on the short side, not a faithful simulation.
# Modeled-pricing events do not have this problem (both legs are
# computable from the same Black-Scholes cost/intrinsic formula).
#
# PRICING SOURCE, by event type:
#   - Signal events (133): REAL (negated real_pnl_pct) where available
#     from the union of the two QC clean-quote samples (90 events, 23
#     overlapping, pass-2 preferred on overlap); MODELED (negated v2-
#     recalibrated pnl_pct, markup=3.4098, the current best-estimate
#     constant -- see CHANGELOG.md) otherwise.
#   - Control events (133): always MODELED -- no real quote was ever
#     pulled for a control/non-signal date in this project. Re-priced
#     fresh here with the v2-recalibrated markup (3.4098), NOT the
#     original uncorrected markup (1.2398) MatchedControlGroup_
#     CanonicalRecompute.csv itself used, to keep the comparison on a
#     consistent, current-best-estimate footing.
#
# Output: Live Signal Engine/ShortVol_DefensiveFilter_Test.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import numpy as np
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

MATCHED_CONTROL_PATH = Path("Live Signal Engine") / "MatchedControlGroup_CanonicalRecompute.csv"
REAL_SAMPLE_1_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_37Events.csv"
REAL_SAMPLE_2_PATH = Path("Live Signal Engine") / "QC_Validation_CleanSample_v2_76Events.csv"
V2_RECAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_RecalibratedPricing_v2.csv"
OUT_PATH = Path("Live Signal Engine") / "ShortVol_DefensiveFilter_Test.csv"

RECALIBRATED_MARKUP = 3.4098   # v2 recalibration, see CHANGELOG.md -- current best-estimate constant
HIGH_CONFIDENCE_Z_THRESHOLD = 10.0
FLAT_POSITION_SIZE = 10_000.0
STARTING_CAPITAL = 100_000.0


def build_real_quote_lookup() -> dict:
    s1 = pd.read_csv(REAL_SAMPLE_1_PATH)
    s2 = pd.read_csv(REAL_SAMPLE_2_PATH)
    s1["spike_week"] = pd.to_datetime(s1["spike_week"])
    s2["spike_week"] = pd.to_datetime(s2["spike_week"])
    lookup = {}
    for _, r in s1.iterrows():
        lookup[(r["ticker"], r["spike_week"])] = r["real_pnl_pct"]
    for _, r in s2.iterrows():
        lookup[(r["ticker"], r["spike_week"])] = r["real_pnl_pct"]   # pass 2 overwrites pass 1 on overlap
    return lookup


def max_drawdown(equity_curve: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity_curve)
    return float(((equity_curve - running_max) / running_max).min())


def group_stats(df: pd.DataFrame, label: str) -> dict:
    d = df.sort_values("exit_date").reset_index(drop=True)
    n = len(d)
    dollar_pnl = FLAT_POSITION_SIZE * (d["short_pnl_pct"] / 100.0)
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
    worst_pct = d["short_pnl_pct"].min()

    stats_df = d.rename(columns={"short_pnl_pct": "pnl_pct"})
    stats_df["win"] = stats_df["pnl_pct"] > 0
    base_stats = base.compute_win_median_sharpe(stats_df[["exit_date", "pnl_pct", "win"]])

    n_real = (d["pricing_source"] == "real").sum()
    n_modeled = (d["pricing_source"] == "modeled").sum()

    print(f"=== {label} (n={n}, real={n_real}, modeled={n_modeled}) ===")
    print(f"  Mean $ return per $10,000 premium: ${mean_dollar_return:,.0f}")
    print(f"  Win rate: {base_stats['win_rate_pct']}%   Median P&L: {base_stats['median_pnl_pct']}%   "
          f"Sharpe: {base_stats['sharpe_annualized']}")
    print(f"  Max drawdown: {mdd_pct:.1f}%")
    print(f"  Expected shortfall, worst 10%: ${es_10:,.0f}   worst 20%: ${es_20:,.0f}")
    print(f"  Worst single trade: ${worst_dollar:,.0f} ({worst_pct:+.1f}%)\n")

    return {
        "group": label, "n": n, "n_real_priced": int(n_real), "n_modeled_priced": int(n_modeled),
        "mean_dollar_return": round(mean_dollar_return, 2),
        "win_rate_pct": base_stats["win_rate_pct"], "median_pnl_pct": base_stats["median_pnl_pct"],
        "sharpe_annualized": base_stats["sharpe_annualized"], "max_drawdown_pct": round(mdd_pct, 2),
        "expected_shortfall_worst10pct": round(es_10, 2), "expected_shortfall_worst20pct": round(es_20, 2),
        "worst_trade_dollar": round(worst_dollar, 2), "worst_trade_pct": round(worst_pct, 2),
    }


def main():
    print("*** SHORT-VOLATILITY DEFENSIVE-FILTER TEST ***\n")

    matched = pd.read_csv(MATCHED_CONTROL_PATH)
    matched["spike_week"] = pd.to_datetime(matched["spike_week"])
    matched["control_date"] = pd.to_datetime(matched["control_date"])
    usable = matched[matched["pnl_diff"].notna()].copy()
    print(f"Usable matched pairs: {len(usable)}\n")

    real_lookup = build_real_quote_lookup()
    print(f"Real-quote lookup built: {len(real_lookup)} events\n")

    canon = pd.read_csv(Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv")
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    canon["exit_date"] = pd.to_datetime(canon["exit_date"])
    exit_date_lookup = {(r.ticker, r.spike_week): r.exit_date for r in canon.itertuples(index=False)}

    v2 = pd.read_csv(V2_RECAL_PATH)
    v2["spike_week"] = pd.to_datetime(v2["spike_week"])
    v2_lookup = {(r["ticker"], r["spike_week"]): r["v2_recalibrated_pnl_pct"] for _, r in v2.iterrows()}

    daily_cache = {}
    signal_rows, control_rows = [], []
    n_failed_control_price = 0

    for r in usable.itertuples(index=False):
        # --- signal side ---
        key = (r.ticker, r.spike_week)
        if key in real_lookup and pd.notna(real_lookup[key]):
            long_pnl = real_lookup[key]
            source = "real"
        else:
            long_pnl = v2_lookup.get(key)
            source = "modeled"
        if long_pnl is None or pd.isna(long_pnl):
            continue
        signal_rows.append({
            "ticker": r.ticker, "anchor": r.spike_week, "zscore": r.zscore,
            "exit_date": exit_date_lookup.get(key), "short_pnl_pct": -long_pnl,
            "pricing_source": source, "role": "signal",
        })

        # --- control side: always re-priced fresh with the recalibrated markup ---
        c_ticker, c_anchor = r.control_ticker, r.control_date
        if c_ticker not in daily_cache:
            daily_cache[c_ticker] = base.load_daily_excess(c_ticker)
        daily = daily_cache[c_ticker]
        ret_col = f"{c_ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            n_failed_control_price += 1
            continue
        priced = base.price_event(daily, ret_col, c_anchor, RECALIBRATED_MARKUP)
        if priced is None:
            n_failed_control_price += 1
            continue
        control_rows.append({
            "ticker": c_ticker, "anchor": c_anchor, "zscore": None,
            "exit_date": priced["exit_date"], "short_pnl_pct": -priced["pnl_pct"],
            "pricing_source": "modeled", "role": "control",
        })

    print(f"Control events failed to re-price: {n_failed_control_price}\n")

    signal_df = pd.DataFrame(signal_rows)
    control_df = pd.DataFrame(control_rows)
    all_events = pd.concat([signal_df, control_df], ignore_index=True)
    all_events.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    n_real = (signal_df["pricing_source"] == "real").sum()
    print(f"Signal events: n={len(signal_df)} ({n_real} real-priced, {len(signal_df)-n_real} modeled)")
    print(f"Control events: n={len(control_df)} (all modeled)\n")

    baseline_all = pd.concat([signal_df, control_df], ignore_index=True)
    excluding_z5 = control_df.copy()
    excluding_z10 = pd.concat([control_df, signal_df[signal_df["zscore"] < HIGH_CONFIDENCE_Z_THRESHOLD]],
                               ignore_index=True)

    results = []
    results.append(group_stats(baseline_all, "BASELINE (sell every earnings date, no GST filter)"))
    results.append(group_stats(excluding_z5, "EXCLUDING z>=5 (avoid every GST-flagged date)"))
    results.append(group_stats(excluding_z10, "EXCLUDING z>=10 only (avoid just the rare extreme tier)"))

    summary = pd.DataFrame(results)
    summary_path = Path("Live Signal Engine") / "ShortVol_DefensiveFilter_Test_Summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote summary: {summary_path}")
    print("\n=== SIDE BY SIDE ===")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
