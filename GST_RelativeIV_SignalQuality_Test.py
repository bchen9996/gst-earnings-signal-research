#!/usr/bin/env python3
# Relative IV as a Signal Quality Filter — does entering a STRONG_EARNINGS
# straddle when IV is CHEAP relative to that ticker's own historical
# pre-earnings level improve economics vs entering when IV is EXPENSIVE?
#
# *** "IV" HERE IS THE MODEL'S PROXY, NOT QUOTED MARKET IV — DISCLOSED ***
# This project has never had real historical option-chain IV for 2021-2025
# dates and can't get it now: yfinance only exposes CURRENTLY listed option
# chains, not historical ones, so there is no way to look up "what IV was
# quoted on 2023-04-12" after the fact. Every earnings-aware straddle price
# in this project — including these — has always used a MODEL of IV:
# trailing 60-trading-day realized volatility x the calibrated near-earnings
# markup (1.2398x, from GST_Earnings_IV_Calibration.py). This test compares
# THAT model input, not real market IV, across a ticker's own STRONG_EARNINGS
# events. It's a legitimate test of "does the pricing model's own IV input
# being relatively low predict better outcomes," not a market-IV finding.
#
# Universe: STRONG_EARNINGS events (z>=5, near_earnings=True), same n=147
# from the existing on-disk Group A file, current live threshold. Straddle
# P&L (both horizons) is reused as-is from that file, not recomputed.
#
# For each event, recomputes the exact same "iv" value the original
# simulation priced with (trailing realized vol x calibrated markup, using
# on-disk Daily Excess Return Data — no new pulls). For each ticker, that
# ticker's "historical average pre-earnings IV" is the LEAVE-ONE-OUT mean
# of this iv value across its OTHER STRONG_EARNINGS events in the dataset
# (excludes the event itself, so a ticker isn't compared against a baseline
# containing its own value). Tickers with only 1 qualifying event have no
# "other" events to average, so those events are excluded and counted
# separately, not silently dropped (4 tickers / 4 events, per a pre-check).
#   IV below historical average: iv < ticker's leave-one-out average (cheap)
#   IV above historical average: iv >= ticker's leave-one-out average (expensive)
#
# Output: Live Signal Engine/RelativeIV_SignalQuality_Test.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import math
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

Z_THRESHOLD = 5.0   # current live STRONG threshold
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
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


def trailing_realized_vol(daily: pd.DataFrame, ret_col: str, cutoff: pd.Timestamp) -> float | None:
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def two_sample_permutation_test(a: np.ndarray, b: np.ndarray, n_perm: int, rng: np.random.Generator):
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None, None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b])
    n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(diff) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm, a.mean(), b.mean()


def main():
    if not GROUP_A_PATH.exists():
        print(f"Missing {GROUP_A_PATH} — run GST_EarningsAdjacent_SpikeVsNoSpike_Test.py first.")
        return

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Using calibrated near-earnings markup: {near_earnings_markup:.4f}x (reused, not re-derived)\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"STRONG_EARNINGS events at z>={Z_THRESHOLD:g}: n={len(events)} across {events['ticker'].nunique()} unique tickers\n")

    print("Recomputing the pricing model's IV input for each event (on-disk data only)...")
    daily_cache: dict[str, pd.DataFrame] = {}
    ivs = []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        if ticker not in daily_cache:
            daily_cache[ticker] = load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            ivs.append(None)
            continue
        vol_cutoff = anchor - timedelta(days=7)
        sigma = trailing_realized_vol(daily, ret_col, vol_cutoff)
        ivs.append(sigma * near_earnings_markup if sigma is not None else None)
    events["iv"] = ivs
    events = events.dropna(subset=["iv"]).copy()

    # Leave-one-out per-ticker historical average IV
    rows = []
    n_excluded_single_event = 0
    for ticker, grp in events.groupby("ticker"):
        if len(grp) < 2:
            n_excluded_single_event += len(grp)
            continue
        total_iv = grp["iv"].sum()
        n = len(grp)
        for _, ev in grp.iterrows():
            loo_avg = (total_iv - ev["iv"]) / (n - 1)
            iv_group = "iv_below_historical_avg" if ev["iv"] < loo_avg else "iv_above_historical_avg"
            rows.append({
                "ticker": ticker, "spike_week": ev["spike_week"].date(), "zscore": ev["zscore"],
                "iv": round(ev["iv"], 4), "ticker_loo_avg_iv": round(loo_avg, 4),
                "iv_group": iv_group,
                "end_of_spike_week_win": ev["end_of_spike_week_win"], "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
                "end_of_window_win": ev["end_of_window_win"], "end_of_window_pnl_pct": ev["end_of_window_pnl_pct"],
            })

    result = pd.DataFrame(rows)
    out_path = OUT_DIR / "RelativeIV_SignalQuality_Test.csv"
    result.to_csv(out_path, index=False)

    print(f"Usable events: n={len(result)}   Excluded (ticker has only 1 qualifying event, no leave-one-out baseline): n={n_excluded_single_event}\n")

    rng = np.random.default_rng(RANDOM_SEED)
    below = result[result["iv_group"] == "iv_below_historical_avg"]
    above = result[result["iv_group"] == "iv_above_historical_avg"]
    print(f"IV below historical average (cheap):    n={len(below)}")
    print(f"IV above historical average (expensive): n={len(above)}\n")

    for h in ["end_of_spike_week", "end_of_window"]:
        win_col, pnl_col = f"{h}_win", f"{h}_pnl_pct"
        b_usable = below[below[win_col].notna()]
        a_usable = above[above[win_col].notna()]

        print(f"=== {h} ===")
        if len(b_usable):
            print(f"IV below avg (cheap):     n={len(b_usable):<4} win={b_usable[win_col].mean()*100:5.1f}%  "
                  f"avg={b_usable[pnl_col].mean():+7.1f}%  median={b_usable[pnl_col].median():+7.1f}%")
        if len(a_usable):
            print(f"IV above avg (expensive): n={len(a_usable):<4} win={a_usable[win_col].mean()*100:5.1f}%  "
                  f"avg={a_usable[pnl_col].mean():+7.1f}%  median={a_usable[pnl_col].median():+7.1f}%")
        if len(b_usable) and len(a_usable):
            diff, p, b_mean, a_mean = two_sample_permutation_test(
                b_usable[pnl_col].to_numpy(dtype=float), a_usable[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
            sig = "significant" if p < 0.05 else "not significant"
            print(f"Diff (Below - Above): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")
        print()

    print("Reminder: 'IV' is the trailing-realized-vol-based pricing model's own input, not quoted market IV — see header.")
    print("EXPLORATORY / UNVALIDATED association test. Not wired into the live signal engine or straddle logger.")
    print(f"\nWrote event-level data to: {out_path}")


if __name__ == "__main__":
    main()
