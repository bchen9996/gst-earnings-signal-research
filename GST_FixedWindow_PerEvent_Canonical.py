#!/usr/bin/env python3
# FIXED-WINDOW PER-EVENT CANONICAL RECOMPUTE — replaces both prior
# z-score methodologies:
#   (1) per-calendar-year CHUNKED pulls (original 147-event archive) --
#       flaw: each year independently rescaled to its own peak, causing
#       rolling-window discontinuities at year boundaries.
#   (2) single continuous ALL-HISTORY pulls (the "148-event" recompute,
#       see GST_FullPopulation_ContinuousWindow_Recompute.py) -- flaw:
#       confirmed look-ahead contamination (GST_LookAhead_Audit.py,
#       93/175 events at risk) because a 5-year window rescales every
#       week -- including years-old ones -- against a peak that can occur
#       AFTER the event being scored.
#
# This method pulls ONE independent query PER EVENT: a fixed-length
# window ending at that event's own decision date (spike_week + 7 days,
# to close out the event's own week), never extending past it, never
# stitched across separately-normalized year-chunks. Per-query peak-
# anchor is internal to that single window, so there's no cross-chunk
# discontinuity; the window never reaches past the event date, so
# there's no look-ahead contamination.
#
# NOTE on window length: the user's suggested 12-14 weeks does NOT work
# -- pytrends silently returns DAILY (not weekly) granularity for
# queries under ~269 days (confirmed empirically this project: see
# GST_Reproducibility_Audit.py / CHANGELOG.md). Weekly granularity,
# which the 12-week rolling z-score formula requires, needs a query of
# at least ~269 days. This script uses the SAME 300-day lookback the
# live engine itself uses (PULL_LOOKBACK_DAYS=300 in
# GST_Live_Signal_Engine.py), just anchored at each event's own date
# instead of "today" -- this is the exact methodology already validated
# on MSFT's 15 events and the 10-event reproducibility audit, extended
# here to the full 175-candidate set.
#
# Candidate set: all 175 (ticker, spike_week) pairs considered anywhere
# in this project's audit trail -- the union of the original 147
# (chunked-method archive) and the 28 raw newly-qualifying candidates
# from the continuous-window full scan. Reused directly from
# Live Signal Engine/EventReconciliation_Ledger.csv (already the
# authoritative 175-row union; near_earnings==True already confirmed
# for every row by construction, so this recompute's only new gate is
# the z>=5 re-check under the fixed-window method).
#
# Pricing: identical Black-Scholes straddle methodology as
# GST_FullPopulation_ContinuousWindow_Recompute.py (entry=anchor+2,
# exit=anchor+6, calibrated near-earnings IV markup, COST_LOADING=1.05).
#
# Output: Live Signal Engine/FixedWindow_PerEvent_Canonical.csv
#         (full 175-row detail: every candidate, its fixed-window
#         z-score, whether it qualifies, and pricing if it does)

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

LEDGER_PATH = Path("Live Signal Engine") / "EventReconciliation_Ledger.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"

TICKERS_ORIGINAL = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
                     "INTC", "TTWO", "QCOM", "GME", "EBAY"]
TICKERS_BROAD50_CLEAR = ['ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
                          'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
                          'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
                          'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM']
DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})
YEARS_RANGE = list(range(2021, 2026))

GEO, GPROP, CAT_ALL = "US", "", 0
PULL_LOOKBACK_DAYS = 300   # matches the live engine's own PULL_LOOKBACK_DAYS; the >=269-day floor
                            # needed for weekly (not daily) pytrends granularity, confirmed empirically
POST_EVENT_BUFFER_DAYS = 7  # closes out the event's own week without extending meaningfully past it

ROLLING_WINDOW = 12
MIN_PERIODS = 8
STRONG_Z = 5.0
STD_EPSILON_FLOOR = 1.0

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


def fetch_event_window(pt: TrendReq, ticker: str, anchor: pd.Timestamp) -> pd.DataFrame:
    end_date = (anchor + timedelta(days=POST_EVENT_BUFFER_DAYS)).date()
    start_date = end_date - timedelta(days=PULL_LOOKBACK_DAYS)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([ticker], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CAT_ALL)
            df = pt.interest_over_time()
            if df is None or df.empty or ticker not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            return pd.DataFrame({"Week": pd.to_datetime(df.index),
                                  "gst": pd.to_numeric(df[ticker], errors="coerce").fillna(0)}).sort_values("Week").reset_index(drop=True)
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg or "rate" in msg) else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"    [{ticker} {anchor.date()}] attempt {attempt} failed: {e} -- sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst"])


def compute_zscore_at_anchor(weekly: pd.DataFrame, anchor: pd.Timestamp):
    if weekly.empty:
        return None, None, "no data"
    shifted = weekly["gst"].shift(1)
    roll = shifted.rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    raw_std = roll.std()
    floored_std = raw_std.clip(lower=STD_EPSILON_FLOOR)
    z = (weekly["gst"] - roll.mean()) / floored_std
    z = z.replace([np.inf, -np.inf], np.nan)
    weekly = weekly.copy()
    weekly["zscore"] = z

    idx = (weekly["Week"] - anchor).abs().idxmin()
    row = weekly.loc[idx]
    gap_days = abs((row["Week"] - anchor).days)
    if gap_days > 6:
        return None, None, f"nearest pulled week {row['Week'].date()} is {gap_days}d from anchor -- no aligned week"
    if pd.isna(row["zscore"]):
        return row["Week"], None, "z-score undefined (insufficient prior weeks in window)"
    return row["Week"], float(row["zscore"]), ""


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
    print("*** FIXED-WINDOW PER-EVENT CANONICAL RECOMPUTE (175 candidates, 28 tickers) ***\n")
    print(f"Window: {PULL_LOOKBACK_DAYS} days ending at each event's own spike_week + {POST_EVENT_BUFFER_DAYS}d "
          f"(one independent pytrends query per event -- not 12-14 weeks: that would silently return "
          f"DAILY granularity, see script header note)\n")

    markup = load_calibrated_near_earnings_markup()
    ledger = pd.read_csv(LEDGER_PATH)
    ledger["spike_week"] = pd.to_datetime(ledger["spike_week"])
    print(f"Candidate set loaded from EventReconciliation_Ledger.csv: n={len(ledger)}\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    daily_cache = {}
    rows = []
    for i, r in enumerate(ledger.itertuples(index=False), start=1):
        ticker, anchor = r.ticker, r.spike_week
        weekly = fetch_event_window(pt, ticker, anchor)
        aligned_week, z, note = compute_zscore_at_anchor(weekly, anchor)
        qualifies = (z is not None) and (z >= STRONG_Z)
        print(f"[{i}/{len(ledger)}] {ticker} {anchor.date()}: fixed_window_z="
              f"{'None' if z is None else round(z,3)} {'QUALIFIES' if qualifies else ''} {note}")

        row = {"ticker": ticker, "spike_week": anchor.date(), "original_category": r.category,
               "aligned_gst_week": aligned_week.date() if aligned_week is not None else None,
               "fixed_window_zscore": round(z, 4) if z is not None else None,
               "qualifies_z5": qualifies, "note": note,
               "entry_date": None, "exit_date": None, "win": None, "pnl_pct": None, "priced_note": ""}

        if qualifies:
            if ticker not in daily_cache:
                daily_cache[ticker] = load_daily_excess(ticker)
            daily = daily_cache[ticker]
            ret_col = f"{ticker} Daily Return"
            if daily.empty or ret_col not in daily.columns:
                row["priced_note"] = "no daily excess-return data available"
            else:
                priced = price_event(daily, ret_col, anchor, markup)
                if priced is None:
                    row["priced_note"] = "failed to price (insufficient trading-day history around anchor)"
                else:
                    row["entry_date"] = priced["entry_date"].date()
                    row["exit_date"] = priced["exit_date"].date()
                    row["win"] = priced["win"]
                    row["pnl_pct"] = round(priced["pnl_pct"], 2)

        rows.append(row)
        time.sleep(random.uniform(1.2, 2.2))

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}\n")

    qualifying = result_df[result_df["qualifies_z5"] == True].copy()  # noqa: E712
    priced = qualifying[qualifying["pnl_pct"].notna()].copy()
    priced["exit_date"] = pd.to_datetime(priced["exit_date"])
    stats = compute_win_median_sharpe(priced)

    print("=== RESULTS ===")
    print(f"Candidates considered (union of original 147 + 28 raw newly-qualifying): n={len(result_df)}")
    print(f"Qualify z>=5 under fixed-window per-event method: n={len(qualifying)}")
    print(f"Successfully priced: n={len(priced)}")
    print(f"GST-Legacy-v1 (original, chunked method):        n=147   win=76.2%   median=+130.0%   Sharpe=2.33")
    print(f"Quarantined continuous-window reconstruction:     n=148   win=76.4%   median=+145.5%   Sharpe=2.22   maxDD=-2.6%")
    print(f"FIXED-WINDOW PER-EVENT CANONICAL (this run):      n={stats['n']}   win={stats['win_rate_pct']}%   "
          f"median={stats['median_pnl_pct']}%   Sharpe={stats['sharpe_annualized']}   maxDD={stats['max_drawdown_pct']}%")


if __name__ == "__main__":
    main()
