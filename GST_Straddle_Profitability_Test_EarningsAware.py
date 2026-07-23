#!/usr/bin/env python3
# GST Straddle Profitability Test — EARNINGS-AWARE pricing, run side by
# side against the original naive model.
#
# GST_Straddle_Profitability_Test.py priced every straddle with a flat
# 1.10x markup over trailing realized volatility, disclosed at the time as
# an arbitrary stand-in for the general volatility risk premium.
# GST_Earnings_Clustering_Test.py then found 80.3% of spike events fall
# within an earnings date's window, and GST_Earnings_IV_Calibration.py
# measured the REAL markup for options spanning a known earnings date at
# 1.240x trailing vol (n=25 live points) vs 1.045x for no-imminent-earnings
# controls (n=7) — confirming the flat 1.10x undercharges earnings-adjacent
# events specifically.
#
# This re-runs the full 310-event simulation with a DIFFERENTIATED markup:
#   - events within 5 days of an earnings date (per the existing
#     spike_event_earnings_flags.csv) are priced with the CALIBRATED
#     1.240x near-earnings markup instead of the flat 1.10x
#   - all other events are priced EXACTLY as before (flat 1.10x, unchanged)
#
# Both the original naive result and this earnings-aware result are
# computed from the same 310 events in the same run and reported side by
# side, so the difference is directly attributable to the pricing change
# alone.
#
# *** THIS CORRECTION IS ITSELF AN ESTIMATE, NOT A VERIFIED HISTORICAL
# PRICE. *** The 1.240x figure comes from a 25-point LIVE market snapshot
# taken on one day (today), for tickers/expirations available right now —
# not from actual historical option prices on the 310 spike-event dates
# themselves (which don't exist / weren't pulled — see the original
# profitability test's header for why). Treat the earnings-aware numbers
# below as a BETTER ESTIMATE than the naive ones, grounded in real current
# market data instead of an arbitrary guess — not as a confirmed result.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import numpy as np
import pandas as pd

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
YEARS = list(range(2014, 2020))

SPIKE_DIR = Path("Conjunction Zscore")
DAILY_DIR = Path("Daily Excess Return Data")
EARNINGS_DIR = Path("Earnings Clustering Test")
OUT_DIR = Path("Straddle Profitability Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENTRY_OFFSET_DAYS = 2
EXIT_HORIZONS = {"end_of_spike_week": 6, "end_of_window": 13}

RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

NAIVE_MARKUP = 1.10          # original flat assumption, unchanged for non-earnings events


def load_calibrated_near_earnings_markup() -> float:
    p = EARNINGS_DIR / "iv_calibration_buckets.csv"
    if not p.exists():
        raise FileNotFoundError(f"Run GST_Earnings_IV_Calibration.py first — missing {p}")
    df = pd.read_csv(p, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    if near_row.empty:
        raise ValueError("Could not find the 'near earnings' bucket in the calibration file")
    markup = float(near_row["mean"].iloc[0])
    n = int(near_row["count"].iloc[0])
    print(f"Loaded calibrated near-earnings markup: {markup:.4f}x (from n={n} live calibration points)\n")
    return markup


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIR / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def main():
    near_earnings_markup = load_calibrated_near_earnings_markup()

    earnings_flags = pd.read_csv(EARNINGS_DIR / "spike_event_earnings_flags.csv")
    earnings_flags["anchor"] = pd.to_datetime(earnings_flags["anchor"]).dt.date.astype(str)
    within_5d_lookup = {(r["ticker"], r["anchor"]): bool(r["within_5d"]) for _, r in earnings_flags.iterrows()}

    rows = []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if not sp.exists():
            continue
        events = pd.read_csv(sp)
        ret_col = f"{ticker} Daily Return"
        daily = load_daily_excess(ticker)
        if daily.empty or ret_col not in daily.columns:
            continue

        for _, ev in events.iterrows():
            anchor = pd.to_datetime(ev["spike_week"], errors="coerce")
            if pd.isna(anchor):
                continue
            near_earnings = within_5d_lookup.get((ticker, anchor.date().isoformat()), False)

            entry_target = anchor + timedelta(days=ENTRY_OFFSET_DAYS)
            entry_date = nearest_trading_day_on_or_before(daily, entry_target)
            if entry_date is None:
                continue

            vol_cutoff = anchor - timedelta(days=7)
            sigma = trailing_realized_vol(daily, ret_col, vol_cutoff)
            row = {"ticker": ticker, "spike_week": anchor.date(), "near_earnings": near_earnings}
            if sigma is None:
                rows.append(row)
                continue

            iv_naive = sigma * NAIVE_MARKUP
            iv_aware = sigma * (near_earnings_markup if near_earnings else NAIVE_MARKUP)

            for h, offset in EXIT_HORIZONS.items():
                exit_target = anchor + timedelta(days=offset)
                exit_date = nearest_trading_day_on_or_before(daily, exit_target)
                if exit_date is None or exit_date <= entry_date:
                    continue
                dte_days = (exit_date - entry_date).days
                if dte_days <= 0:
                    continue
                T = dte_days / 365.0

                cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
                if cum_ret is None:
                    continue
                intrinsic_value = abs(100.0 * (1 + cum_ret) - 100.0)

                for label, iv in [("naive", iv_naive), ("aware", iv_aware)]:
                    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
                    if fair is None:
                        continue
                    cost = fair * COST_LOADING
                    net_pnl = intrinsic_value - cost
                    row[f"{h}_{label}_straddle_cost"] = round(cost, 3)
                    row[f"{h}_{label}_net_pnl_pct_of_cost"] = round(net_pnl / cost * 100, 2)
                    row[f"{h}_{label}_win"] = bool(net_pnl > 0)

            rows.append(row)

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "results_naive_vs_earnings_aware.csv"
    results.to_csv(out_path, index=False)

    n_near = int(results["near_earnings"].sum())
    print(f"Total events: {len(results)}  (near-earnings, corrected: {n_near}; "
          f"other, unchanged: {len(results) - n_near})\n")

    for h in EXIT_HORIZONS:
        print(f"=== {h} ===")
        print(f"{'model':<16}{'n':>6}{'win rate':>12}{'avg P&L%':>12}{'median P&L%':>14}")
        for label, title in [("naive", "naive (flat 1.10x)"), ("aware", "earnings-aware")]:
            win_col = f"{h}_{label}_win"
            pnl_col = f"{h}_{label}_net_pnl_pct_of_cost"
            if win_col not in results.columns:
                continue
            usable = results[results[win_col].notna()]
            n = len(usable)
            if n == 0:
                continue
            win_rate = usable[win_col].mean() * 100
            avg_pnl = usable[pnl_col].mean()
            median_pnl = usable[pnl_col].median()
            print(f"{title:<16}{n:>6}{win_rate:>11.1f}%{avg_pnl:>11.1f}%{median_pnl:>13.1f}%")
        print()

    print("*** The 'earnings-aware' correction (1.24x near-earnings markup) is derived from a "
          "25-point LIVE option-market snapshot taken today, not from verified historical prices "
          "on the actual 310 spike-event dates. Treat it as a better-grounded ESTIMATE, not a "
          "confirmed result. ***")
    print(f"\nWrote full side-by-side results to: {out_path}")


if __name__ == "__main__":
    main()
