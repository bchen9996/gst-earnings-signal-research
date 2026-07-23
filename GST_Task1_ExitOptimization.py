#!/usr/bin/env python3
# TASK 1 — Exit rule optimization: for each z>=5 STRONG_EARNINGS event,
# compare three exit rules using on-disk daily price data:
#   (a) exit at end of earnings announcement day
#   (b) exit at next trading day's close
#   (c) hold to end of spike week (current spec, anchor+6)
#
# *** WHY A NEW PULL WAS NEEDED DESPITE "EXISTING DAILY PRICE DATA" ***
# Rules (a) and (b) are keyed to the EXACT earnings date, not just "within
# 5 days of the anchor" (nearest_earnings_gap_days on disk is an absolute
# distance only — sign/actual date was never persisted, confirmed
# repeatedly earlier in this project). Getting the actual date requires a
# fresh yfinance earnings-date pull — one call per unique ticker (28),
# cached, same pattern used several times already. The underlying PRICE
# data used to compute every exit rule's P&L is 100% on-disk, not re-pulled.
#
# Entry unchanged (anchor+2 days, nearest trading day on-or-before).
# Each exit rule reprices its own straddle cost (different T = days held
# changes the option's time value) using the same earnings-aware IV model
# (calibrated near-earnings markup, since all 147 events are near_earnings
# by construction) — not a single cost reused across all three rules.
#
# Events where the earnings date falls BEFORE entry (possible since the
# 5-day window is symmetric around the anchor) make rules (a)/(b)
# nonsensical (negative holding period) — excluded from those two rules
# specifically and counted, not silently dropped without disclosure.
#
# Output: Live Signal Engine/Task1_ExitOptimization_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys, time
import math
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

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
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "Task1_ExitOptimization_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EARNINGS_PULL_LIMIT = 40
MAX_MATCH_GAP_DAYS = 5
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


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


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def next_trading_day_after(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] > target, "Date"]
    return eligible.min() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def fetch_earnings_dates(ticker: str, max_attempts: int = 3) -> pd.DataFrame:
    df = None
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            df = tk.get_earnings_dates(limit=EARNINGS_PULL_LIMIT)
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
            df = None
        if df is not None and not df.empty:
            break
        if attempt < max_attempts:
            time.sleep(5)
    if df is None or df.empty:
        return pd.DataFrame()
    return pd.DataFrame({"date": pd.to_datetime(df.index).tz_localize(None).normalize()}).dropna()


def price_leg(daily, ret_col, entry_date, exit_date, sigma, markup):
    if exit_date is None or entry_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    T = dte_days / 365.0
    iv = sigma * markup
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"win": pnl_pct > 0, "pnl_pct": pnl_pct, "dte_days": dte_days}


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    print(f"*** TASK 1: Exit rule optimization (z>={Z_THRESHOLD:g}) ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Calibrated near-earnings markup (reused): {near_earnings_markup:.4f}x\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} tickers\n")

    print("Pulling exact earnings dates per ticker (cached, one pull each, with retry)...")
    earnings_cache: dict[str, pd.DataFrame] = {}
    daily_cache: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(tickers, start=1):
        earnings_cache[ticker] = fetch_earnings_dates(ticker)
        daily_cache[ticker] = load_daily_excess(ticker)
        print(f"  [{i}/{len(tickers)}] {ticker}: {len(earnings_cache[ticker])} earnings dates")
        time.sleep(0.8)
    print()

    rows = []
    n_no_earnings_match, n_earnings_before_entry = 0, 0
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        earn_hist = earnings_cache.get(ticker, pd.DataFrame())
        if daily.empty or ret_col not in daily.columns or earn_hist.empty:
            continue

        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        if entry_date is None:
            continue
        sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
        if sigma is None:
            continue

        gaps = (earn_hist["date"] - anchor).abs().dt.days
        nearest_idx = gaps.idxmin()
        if gaps.loc[nearest_idx] > MAX_MATCH_GAP_DAYS:
            n_no_earnings_match += 1
            continue
        earnings_date = earn_hist.loc[nearest_idx, "date"]

        row = {"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore,
               "earnings_date": earnings_date.date(), "entry_date": entry_date.date()}

        # Rule (c): hold to end of spike week (unchanged spec)
        exit_c = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=6))
        res_c = price_leg(daily, ret_col, entry_date, exit_c, sigma, near_earnings_markup)
        if res_c:
            row["exit_c_date"] = exit_c.date()
            row["exit_c_win"] = res_c["win"]
            row["exit_c_pnl_pct"] = res_c["pnl_pct"]

        # Rules (a)/(b) only make sense if earnings is on/after entry
        if earnings_date < entry_date:
            n_earnings_before_entry += 1
        else:
            exit_a = nearest_trading_day_on_or_before(daily, earnings_date)
            res_a = price_leg(daily, ret_col, entry_date, exit_a, sigma, near_earnings_markup)
            if res_a:
                row["exit_a_date"] = exit_a.date()
                row["exit_a_win"] = res_a["win"]
                row["exit_a_pnl_pct"] = res_a["pnl_pct"]

            exit_b = next_trading_day_after(daily, earnings_date)
            res_b = price_leg(daily, ret_col, entry_date, exit_b, sigma, near_earnings_markup)
            if res_b:
                row["exit_b_date"] = exit_b.date()
                row["exit_b_win"] = res_b["win"]
                row["exit_b_pnl_pct"] = res_b["pnl_pct"]

        rows.append(row)

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    print(f"Usable events: n={len(result)}")
    print(f"Excluded — no earnings date match within {MAX_MATCH_GAP_DAYS}d: {n_no_earnings_match}")
    print(f"Rules (a)/(b) skipped — earnings date before entry: {n_earnings_before_entry}\n")

    rng = np.random.default_rng(RANDOM_SEED)
    labels = {"exit_a": "(a) end of earnings-announcement day", "exit_b": "(b) next trading day close",
              "exit_c": "(c) end of spike week (current spec)"}
    summaries = {}
    for key, label in labels.items():
        win_col, pnl_col = f"{key}_win", f"{key}_pnl_pct"
        usable = result[result[win_col].notna()] if win_col in result.columns else pd.DataFrame()
        n = len(usable)
        if n == 0:
            print(f"{label}: no usable events")
            continue
        wr = usable[win_col].mean() * 100
        avg = usable[pnl_col].mean()
        med = usable[pnl_col].median()
        summaries[key] = usable[pnl_col].to_numpy(dtype=float)
        print(f"{label}: n={n:<4} win={wr:5.1f}%  avg={avg:+7.1f}%  median={med:+7.1f}%")

    print()
    if "exit_a" in summaries and "exit_c" in summaries:
        diff, p = two_sample_permutation_test(summaries["exit_a"], summaries["exit_c"], N_PERMUTATIONS, rng)
        print(f"(a) vs (c): diff={diff:+.1f}pt  p={p:.4f} ({'significant' if p<0.05 else 'not significant'})")
    if "exit_b" in summaries and "exit_c" in summaries:
        diff, p = two_sample_permutation_test(summaries["exit_b"], summaries["exit_c"], N_PERMUTATIONS, rng)
        print(f"(b) vs (c): diff={diff:+.1f}pt  p={p:.4f} ({'significant' if p<0.05 else 'not significant'})")
    if "exit_a" in summaries and "exit_b" in summaries:
        diff, p = two_sample_permutation_test(summaries["exit_a"], summaries["exit_b"], N_PERMUTATIONS, rng)
        print(f"(a) vs (b): diff={diff:+.1f}pt  p={p:.4f} ({'significant' if p<0.05 else 'not significant'})")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
