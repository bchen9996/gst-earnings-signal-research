#!/usr/bin/env python3
# TASK 4 — Historical earnings reaction size as a signal quality filter:
# do tickers that HISTORICALLY move a lot on earnings day show better
# STRONG_EARNINGS (z>=5) economics than tickers that are historically
# quiet on earnings day?
#
# For each ticker, pulls earnings-date history + report timing (BMO/AMC,
# same classification method as GST_EarningsTiming_SignalQuality_Test.py —
# new, lightweight yfinance pull, cached once per ticker) and combines it
# with the ticker's own on-disk daily return data to compute the actual
# price move on each earnings reaction day (same day for BMO, next trading
# day for AMC). For each event, averages |move| over the 4 most recent
# earnings dates STRICTLY BEFORE the event's anchor (point-in-time, no
# look-ahead — same discipline as GST_EarningsSurprise_SignalQuality_Test.py).
#   historically volatile on earnings: avg |move| > 5%
#   historically quiet on earnings:    avg |move| <= 5%
#
# Straddle P&L (spike_week horizon) reused as-is from the existing Group A
# file, not recomputed.
#
# Output: Live Signal Engine/Task4_HistoricalEarningsReactionSize_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import date, timedelta
import sys, time
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
OUT_PATH = Path("Live Signal Engine") / "Task4_HistoricalEarningsReactionSize_Results.csv"

Z_THRESHOLD = 5.0
EARNINGS_PULL_LIMIT = 40
PRIOR_EARNINGS_WINDOW = 4
MIN_USABLE_PRIOR = 2
REACTION_THRESHOLD_PCT = 5.0
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_earnings_timing(ticker: str, max_attempts: int = 3) -> pd.DataFrame:
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
    out = pd.DataFrame({
        "date": pd.to_datetime(df.index).tz_localize(None).normalize().date,
        "hour": pd.to_datetime(df.index).tz_localize(None).hour,
    })
    return out.dropna()


def load_daily(ticker: str) -> pd.DataFrame:
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


def reaction_day_move(daily: pd.DataFrame, ret_col: str, earnings_date: date, hour: int) -> float | None:
    target = pd.Timestamp(earnings_date)
    if hour < 12:  # BMO -> same day reaction
        row = daily.loc[daily["Date"] == target, ret_col]
    else:  # AMC (or ambiguous, treated as AMC) -> next trading day reaction
        after = daily.loc[daily["Date"] > target, "Date"]
        if after.empty:
            return None
        next_day = after.min()
        row = daily.loc[daily["Date"] == next_day, ret_col]
    if row.empty or pd.isna(row.iloc[0]):
        return None
    return float(row.iloc[0])


def avg_abs_prior_reaction(timing: pd.DataFrame, daily: pd.DataFrame, ret_col: str, anchor: date) -> tuple[float | None, int]:
    prior = timing[timing["date"] < anchor].sort_values("date", ascending=False).head(PRIOR_EARNINGS_WINDOW)
    moves = []
    for _, r in prior.iterrows():
        move = reaction_day_move(daily, ret_col, r["date"], int(r["hour"]))
        if move is not None:
            moves.append(abs(move))
    if len(moves) < MIN_USABLE_PRIOR:
        return None, len(moves)
    return float(np.mean(moves)) * 100, len(moves)


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
    print(f"*** TASK 4: Historical earnings reaction size (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"]).dt.date
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} tickers\n")

    print("Pulling earnings-date + timing history per ticker (cached, one pull each)...")
    timing_cache: dict[str, pd.DataFrame] = {}
    daily_cache: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(tickers, start=1):
        timing_cache[ticker] = fetch_earnings_timing(ticker)
        daily_cache[ticker] = load_daily(ticker)
        print(f"  [{i}/{len(tickers)}] {ticker}: {len(timing_cache[ticker])} earnings dates with timing")
        time.sleep(0.8)
    print()

    rows = []
    n_excluded = 0
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        timing = timing_cache.get(ticker, pd.DataFrame())
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if timing.empty or daily.empty or ret_col not in daily.columns:
            n_excluded += 1
            continue
        avg_move, n_used = avg_abs_prior_reaction(timing, daily, ret_col, anchor)
        if avg_move is None:
            n_excluded += 1
            continue
        group = "historically_volatile" if avg_move > REACTION_THRESHOLD_PCT else "historically_quiet"
        rows.append({
            "ticker": ticker, "spike_week": anchor, "zscore": ev["zscore"],
            "avg_abs_prior_earnings_move_pct": round(avg_move, 2), "n_prior_earnings_used": n_used,
            "reaction_group": group,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Usable events: n={len(result)}   Excluded (insufficient prior earnings-reaction data): n={n_excluded}\n")

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    volatile = result[result["reaction_group"] == "historically_volatile"]
    quiet = result[result["reaction_group"] == "historically_quiet"]
    vol_u = volatile[volatile[win_col].notna()]
    quiet_u = quiet[quiet[win_col].notna()]

    print(f"=== HISTORICALLY VOLATILE ON EARNINGS (avg|move|>{REACTION_THRESHOLD_PCT:g}%), n={len(vol_u)} ===")
    print(f"win={vol_u[win_col].mean()*100:.1f}%  avg={vol_u[pnl_col].mean():+.1f}%  median={vol_u[pnl_col].median():+.1f}%")
    print(f"=== HISTORICALLY QUIET ON EARNINGS (avg|move|<={REACTION_THRESHOLD_PCT:g}%), n={len(quiet_u)} ===")
    print(f"win={quiet_u[win_col].mean()*100:.1f}%  avg={quiet_u[pnl_col].mean():+.1f}%  median={quiet_u[pnl_col].median():+.1f}%")

    if len(vol_u) and len(quiet_u):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p, v_mean, q_mean = two_sample_permutation_test(
            vol_u[pnl_col].to_numpy(dtype=float), quiet_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (Volatile - Quiet): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
