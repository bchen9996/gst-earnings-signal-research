#!/usr/bin/env python3
# FULL-POPULATION CONTINUOUS-WINDOW RECOMPUTE — applies the same
# measurement-methodology correction validated on MSFT (see
# Live Signal Engine/CHANGELOG.md, 2026-07-18 entry) to the entire
# 147-event STRONG_EARNINGS population, AND does the fuller scan that
# MSFT-only check disclosed as missing: recomputes each of the 28
# tickers' ENTIRE weekly GST series from ONE continuous multi-year pull
# (single peak-anchor, no per-year chunking discontinuity -- confirmed
# feasible: a single 2021-2025 pytrends query returns weekly granularity,
# 262 points, one call instead of ~260 per ticker), re-runs the SAME
# spike-detection -> 21-day-dedup -> near-earnings pipeline as the
# original historical backtest, and compares the resulting population
# against the original 147 for BOTH dropped events (no longer clear z>=5)
# AND newly-qualifying events (previously below z>=5, now clear it).
#
# Same de-dup rule as GST_Zscore_No_Overlaps_2021_2025_Broad50Clear.py
# (base spike z>=2, keep first, then only keep next spike if >=21 days
# from the last KEPT spike). Same near-earnings rule as
# GST_Earnings_Clustering_Test_2021_2025_Broad50Clear.py (symmetric
# +/-5 day window around the spike-week anchor -- the HISTORICAL rule,
# not the live engine's forward-only rule, since this recompute is
# rebuilding the historical population on corrected input data, not
# changing what the live engine watches for). Same Black-Scholes
# straddle pricing as GST_Straddle_Simulation_2021_2025_51Ticker.py.
#
# This is a data-measurement correction, not a strategy rule change --
# same governance classification as the MSFT-only check. Logged in
# Live Signal Engine/CHANGELOG.md.
#
# Output: Live Signal Engine/FullPopulation_ContinuousWindow_Recompute.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import random
import sys
import time
import numpy as np
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
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
YEARS_RANGE = list(range(2021, 2026))
DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "FullPopulation_ContinuousWindow_Recompute.csv"

PULL_START, PULL_END = "2021-01-01", "2025-12-31"   # exactly 5 years -- longer spans silently fall back to MONTHLY granularity
GEO, GPROP, CAT_ALL = "US", "", 0

ROLLING_WINDOW = 12
MIN_PERIODS = 8
BASE_SPIKE_Z = 2.0
STRONG_Z = 5.0
MIN_GAP_DAYS = 21
EARNINGS_WINDOW_DAYS = 5   # symmetric, matches the HISTORICAL backtest rule

ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

FLAT_POSITION_SIZE = 10_000.0
STARTING_CAPITAL = 100_000.0

MAX_ATTEMPTS = 5
HARD_429_SLEEP = 60


def fetch_full_series(pt: TrendReq, ticker: str) -> pd.DataFrame:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([ticker], timeframe=f"{PULL_START} {PULL_END}", geo=GEO, gprop=GPROP, cat=CAT_ALL)
            df = pt.interest_over_time()
            if df is None or df.empty or ticker not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            return pd.DataFrame({"Week": pd.to_datetime(df.index),
                                  "gst": pd.to_numeric(df[ticker], errors="coerce").fillna(0)}).sort_values("Week").reset_index(drop=True)
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg or "rate" in msg) else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"  [{ticker}] attempt {attempt} failed: {e} -- sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst"])


STD_EPSILON_FLOOR = 1.0   # smallest std treated as meaningful, given gst is an integer 0-100 scale;
                          # bug found 2026-07-18: unfloored std can collapse toward 0 during flat/
                          # low-volume stretches, producing division-by-near-zero z-scores in the
                          # millions (GME). This floor is a numerical-stability guard only -- it does
                          # not change the z-score formula's shape or the z>=5 threshold, so it is not
                          # a rule change (see CHANGELOG.md).


def compute_zscore(weekly: pd.DataFrame) -> pd.DataFrame:
    shifted = weekly["gst"].shift(1)
    roll = shifted.rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    raw_std = roll.std()
    floored_std = raw_std.clip(lower=STD_EPSILON_FLOOR)
    z = (weekly["gst"] - roll.mean()) / floored_std
    weekly = weekly.copy()
    weekly["zscore"] = z.replace([np.inf, -np.inf], np.nan)
    weekly["raw_std"] = raw_std
    weekly["std_floor_activated"] = raw_std.notna() & (raw_std < STD_EPSILON_FLOOR)
    return weekly


def dedupe_spikes(weekly: pd.DataFrame) -> pd.DataFrame:
    spikes = weekly[weekly["zscore"] >= BASE_SPIKE_Z].dropna(subset=["Week"]).sort_values("Week").reset_index(drop=True)
    if spikes.empty:
        return spikes
    kept = [spikes.iloc[0]]
    last_date = spikes.iloc[0]["Week"]
    for _, row in spikes.iloc[1:].iterrows():
        if (row["Week"] - last_date).days >= MIN_GAP_DAYS:
            kept.append(row)
            last_date = row["Week"]
    return pd.DataFrame(kept).reset_index(drop=True)


def near_earnings_flag(anchor: pd.Timestamp, earnings_dates: list) -> bool:
    lo, hi = anchor - timedelta(days=EARNINGS_WINDOW_DAYS), anchor + timedelta(days=EARNINGS_WINDOW_DAYS)
    return any(lo <= ed <= hi for ed in earnings_dates)


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


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
    for year in YEARS_RANGE:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if p.exists():
            df = pd.read_csv(p)
            if "Date" in df.columns and not df.empty:
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


def price_event(daily, ret_col, anchor, markup):
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if entry_date is None or exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma is None:
        return None
    iv = sigma * markup
    T = dte_days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"entry_date": entry_date, "exit_date": exit_date, "win": pnl_pct > 0, "pnl_pct": pnl_pct}


def max_drawdown(equity_curve: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity_curve)
    return float(((equity_curve - running_max) / running_max).min())


def compute_win_median_sharpe(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate_pct": None, "median_pnl_pct": None, "sharpe_annualized": None, "max_drawdown_pct": None}
    trades = trades.sort_values("exit_date").reset_index(drop=True)
    win_rate = trades["win"].mean() * 100
    median_pnl = trades["pnl_pct"].median()
    dollar_pnl = FLAT_POSITION_SIZE * (trades["pnl_pct"] / 100.0)
    equity = STARTING_CAPITAL + dollar_pnl.cumsum()
    equity_curve = np.concatenate([[STARTING_CAPITAL], equity.to_numpy()])
    mdd = max_drawdown(equity_curve)
    t = trades.copy()
    t["month"] = t["exit_date"].dt.to_period("M")
    t["dollar_pnl"] = dollar_pnl
    monthly = t.groupby("month")["dollar_pnl"].sum()
    full_range = pd.period_range(t["month"].min(), t["month"].max(), freq="M")
    monthly = monthly.reindex(full_range, fill_value=0.0)
    monthly_equity_start = STARTING_CAPITAL + monthly.cumsum().shift(1).fillna(0.0)
    monthly_return = monthly / monthly_equity_start
    mean_m, std_m = float(monthly_return.mean()), float(monthly_return.std(ddof=1))
    sharpe = (mean_m / std_m * np.sqrt(12)) if std_m > 0 else None
    return {"n": n, "win_rate_pct": round(win_rate, 1), "median_pnl_pct": round(median_pnl, 1),
            "sharpe_annualized": round(sharpe, 3) if sharpe is not None else None,
            "max_drawdown_pct": round(mdd * 100, 2)}


def main():
    print("*** FULL-POPULATION CONTINUOUS-WINDOW RECOMPUTE (147 events, 28 tickers) ***\n")

    markup = load_calibrated_near_earnings_markup()
    orig_events = pd.read_csv(GROUP_A_PATH)
    orig_strong = orig_events[(orig_events["zscore"] >= STRONG_Z) & (orig_events["near_earnings"] == True)].copy()  # noqa: E712
    orig_strong["spike_week"] = pd.to_datetime(orig_strong["spike_week"])
    orig_keys = set(zip(orig_strong["ticker"], orig_strong["spike_week"]))
    tickers = sorted(orig_strong["ticker"].unique())
    print(f"Original population: n={len(orig_strong)} across {len(tickers)} tickers\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earnings_df.groupby("ticker")}

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    print("Pulling ONE continuous multi-year series per ticker (single peak-anchor)...")
    daily_cache, recomputed_populations = {}, []
    for i, ticker in enumerate(tickers, start=1):
        weekly = fetch_full_series(pt, ticker)
        if weekly.empty:
            print(f"  [{i}/{len(tickers)}] {ticker}: NO DATA, skipping")
            continue
        weekly = compute_zscore(weekly)
        deduped = dedupe_spikes(weekly)
        earnings_dates = earnings_by_ticker.get(ticker, [])

        n_strong = 0
        for _, row in deduped.iterrows():
            if pd.isna(row["zscore"]) or row["zscore"] < STRONG_Z:
                continue
            if not near_earnings_flag(row["Week"], earnings_dates):
                continue
            n_strong += 1
            recomputed_populations.append({"ticker": ticker, "spike_week": row["Week"], "continuous_zscore": row["zscore"]})
        print(f"  [{i}/{len(tickers)}] {ticker}: {len(deduped)} deduped spikes -> {n_strong} STRONG_EARNINGS (continuous method)")
        daily_cache[ticker] = load_daily_excess(ticker)
        time.sleep(random.uniform(1.5, 3.0))
    print()

    recomputed_df = pd.DataFrame(recomputed_populations)
    recomputed_keys = set(zip(recomputed_df["ticker"], recomputed_df["spike_week"]))

    retained = orig_keys & recomputed_keys
    dropped = orig_keys - recomputed_keys
    newly_added = recomputed_keys - orig_keys

    print(f"=== POPULATION COMPARISON ===")
    print(f"Original 147-event population: n={len(orig_keys)}")
    print(f"Retained (still clear z>=5 under continuous method): n={len(retained)}")
    print(f"DROPPED (no longer clear z>=5): n={len(dropped)}")
    for t, d in sorted(dropped, key=lambda x: x[1]):
        orig_z = orig_strong[(orig_strong["ticker"] == t) & (orig_strong["spike_week"] == d)]["zscore"].iloc[0]
        print(f"    {t} {d.date()}  original_z={orig_z:.3f}")
    print(f"NEWLY QUALIFYING (previously did not clear z>=5, now do): n={len(newly_added)}")
    for t, d in sorted(newly_added, key=lambda x: x[1]):
        new_z = recomputed_df[(recomputed_df["ticker"] == t) & (recomputed_df["spike_week"] == d)]["continuous_zscore"].iloc[0]
        print(f"    {t} {d.date()}  continuous_z={new_z:.3f}")
    print()

    final_keys = retained | newly_added
    print(f"Final recomputed population size: n={len(final_keys)}\n")

    print("Pricing all events in the recomputed population...")
    rows = []
    for ticker, anchor in final_keys:
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        priced = price_event(daily, ret_col, anchor, markup)
        if priced is None:
            continue
        z_row = recomputed_df[(recomputed_df["ticker"] == ticker) & (recomputed_df["spike_week"] == anchor)]
        continuous_z = float(z_row["continuous_zscore"].iloc[0]) if not z_row.empty else None
        status = "retained" if (ticker, anchor) in retained else "newly_qualifying"
        rows.append({"ticker": ticker, "spike_week": anchor.date(), "continuous_zscore": round(continuous_z, 4) if continuous_z else None,
                     "status": status, "entry_date": priced["entry_date"].date(), "exit_date": priced["exit_date"].date(),
                     "win": priced["win"], "pnl_pct": round(priced["pnl_pct"], 2)})

    result_df = pd.DataFrame(rows)
    result_df["exit_date"] = pd.to_datetime(result_df["exit_date"])
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    stats = compute_win_median_sharpe(result_df)
    print("=== RESULTS ===")
    print(f"Original 147-event backtest (chunked method):    n=147   win=76.2%   median=+130.0%   Sharpe=2.33")
    print(f"Recomputed (continuous-window method):           n={stats['n']}   win={stats['win_rate_pct']}%   "
          f"median={stats['median_pnl_pct']}%   Sharpe={stats['sharpe_annualized']}   maxDD={stats['max_drawdown_pct']}%")
    print(f"\nDropped: {len(dropped)}   Newly qualifying: {len(newly_added)}   Net change in n: {stats['n']-147:+d}")


if __name__ == "__main__":
    main()
