#!/usr/bin/env python3
# TASK 1 — False negatives: earnings dates with a large realized move but
# no z>=5 STRONG_EARNINGS spike. Characterizes what the model misses.
#
# Reuses AllTickers_EarningsDates.csv, AllTickers_ZscoreSeries.csv,
# AllTickers_Sectors.csv (shared foundation, already on disk) and on-disk
# daily price data. One NEW pull: market cap for the 23/51 tickers not
# already pulled in the earlier market-cap-buckets task (which only
# covered the 28 tickers already in the z>=5 population) — needed here
# because false negatives can be ANY of the 51 tickers, not just ones that
# already had a STRONG_EARNINGS event.
#
# Output: Live Signal Engine/FalseNegative_Analysis.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
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

EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "FalseNegative_Analysis.csv"

# Tickers already market-cap-pulled in the earlier task (reused, not re-pulled)
KNOWN_MARKET_CAPS = {
    "AAPL": 4631.2e9, "ABBV": 438.3e9, "ADBE": 88.9e9, "AMZN": 2639.1e9, "BKR": 57.1e9,
    "BRK-B": 1064.9e9, "COHR": 63.5e9, "CTSH": 20.1e9, "DELL": 281.1e9, "DVN": 48.7e9,
    "GME": 9.7e9, "GOOGL": 4358.5e9, "GPN": 20.8e9, "INTC": 552.1e9, "LDOS": 13.5e9,
    "MCHP": 48.1e9, "MSFT": 2860.7e9, "NCLH": 9.0e9, "NFLX": 308.9e9, "NKE": 65.7e9,
    "NVDA": 5109.7e9, "QCOM": 199.4e9, "SBUX": 120.8e9, "STZ": 22.9e9, "SYK": 126.4e9,
    "TSLA": 1531.4e9, "TTWO": 45.2e9, "UAL": 40.9e9,
}

Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
WEEK_MATCH_TOL_DAYS = 3
LARGE_MOVE_PERCENTILE = 75
PRIOR_QUARTERS = 3
HIST_WINDOW_START = pd.Timestamp("2021-01-01")
HIST_WINDOW_END = pd.Timestamp("2025-12-31")
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_market_cap(ticker: str, max_attempts: int = 3) -> float | None:
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            cap = tk.fast_info.get("marketCap") or tk.info.get("marketCap")
            if cap:
                return float(cap)
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            time.sleep(5)
    return None


def load_daily(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        ret_col = f"{ticker} Daily Return"
        if "Date" not in df.columns or ret_col not in df.columns:
            continue
        df = df.rename(columns={ret_col: "ret"})[["Date", "ret"]]
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def realized_move(daily: pd.DataFrame, earnings_date: pd.Timestamp) -> float | None:
    same_day = daily.loc[daily["Date"] == earnings_date, "ret"]
    after = daily.loc[daily["Date"] > earnings_date, "Date"]
    next_ret = None
    if not after.empty:
        next_day = after.min()
        next_ret = daily.loc[daily["Date"] == next_day, "ret"]
    candidates = []
    if not same_day.empty and pd.notna(same_day.iloc[0]):
        candidates.append(abs(float(same_day.iloc[0])))
    if next_ret is not None and not next_ret.empty and pd.notna(next_ret.iloc[0]):
        candidates.append(abs(float(next_ret.iloc[0])))
    if not candidates:
        return None
    return max(candidates) * 100


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
    print("*** TASK 1: False negatives — large realized moves with no z>=5 spike ***\n")

    print("Filling in market cap for tickers not already pulled...")
    market_caps = dict(KNOWN_MARKET_CAPS)
    missing = [t for t in ALL_TICKERS if t not in market_caps]
    for i, ticker in enumerate(missing, start=1):
        cap = fetch_market_cap(ticker)
        market_caps[ticker] = cap
        print(f"  [{i}/{len(missing)}] {ticker}: {'$'+format(cap/1e9,'.1f')+'B' if cap else 'N/A'}")
        time.sleep(0.8)
    print()

    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = dict(zip(sector_df["ticker"], sector_df["sector"]))

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_df = earnings_df[(earnings_df["earnings_date"] >= HIST_WINDOW_START) &
                               (earnings_df["earnings_date"] <= HIST_WINDOW_END)].copy()
    print(f"Earnings dates in 2021-2025 window: n={len(earnings_df)} across {earnings_df['ticker'].nunique()} tickers\n")

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_by_ticker = {t: g.set_index("week")["zscore_simple"] for t, g in z_df.groupby("ticker")}

    def zscore_near(ticker, target_date, tol=WEEK_MATCH_TOL_DAYS):
        series = z_by_ticker.get(ticker)
        if series is None or series.empty:
            return None, None
        diffs = np.abs((series.index - target_date).days.to_numpy())
        nearest_pos = int(diffs.argmin())
        gap = int(diffs[nearest_pos])
        if gap > tol:
            return None, gap
        val = series.iloc[nearest_pos]
        return (float(val) if pd.notna(val) else None), gap

    print("Computing realized move for every earnings date...")
    daily_cache = {t: load_daily(t) for t in ALL_TICKERS}
    rows = []
    for _, ev in earnings_df.iterrows():
        ticker, edate = ev["ticker"], ev["earnings_date"]
        daily = daily_cache.get(ticker)
        if daily is None or daily.empty:
            continue
        move = realized_move(daily, edate)
        if move is None:
            continue
        z_here, week_gap = zscore_near(ticker, edate)
        rows.append({"ticker": ticker, "earnings_date": edate.date(), "realized_move_pct": move,
                     "z_at_earnings_week": z_here, "week_match_gap_days": week_gap})

    all_events = pd.DataFrame(rows)
    print(f"Usable earnings-date events with a computable realized move: n={len(all_events)}\n")

    large_move_threshold = np.percentile(all_events["realized_move_pct"], LARGE_MOVE_PERCENTILE)
    print(f"{LARGE_MOVE_PERCENTILE}th percentile realized move threshold: {large_move_threshold:.2f}%\n")

    all_events["large_move"] = all_events["realized_move_pct"] >= large_move_threshold
    all_events["had_spike"] = all_events["z_at_earnings_week"] >= Z_THRESHOLD
    all_events["data_missing"] = all_events["z_at_earnings_week"].isna()

    false_negatives = all_events[all_events["large_move"] & (~all_events["had_spike"].fillna(False))].copy()
    fn_data_issue = false_negatives[false_negatives["data_missing"]]
    fn_genuine = false_negatives[~false_negatives["data_missing"]]

    print(f"Large-move events: n={all_events['large_move'].sum()}")
    print(f"False negatives (large move, no z>=5 at that week): n={len(false_negatives)}")
    print(f"  Of which: DATA-MISSING (z unavailable, not genuinely low): n={len(fn_data_issue)}")
    print(f"  Of which: GENUINE (z computed and confirmed <5): n={len(fn_genuine)}\n")

    # Prior-quarter mean z for false negatives (genuine subset) and comparison to true positives
    def prior_quarter_mean_z(ticker, edate):
        dates = earnings_df[earnings_df["ticker"] == ticker]["earnings_date"].tolist()
        prior = sorted([d for d in dates if d < edate], reverse=True)[:PRIOR_QUARTERS]
        zs = []
        for d in prior:
            z, _ = zscore_near(ticker, d)
            if z is not None:
                zs.append(z)
        return float(np.mean(zs)) if zs else None

    fn_genuine = fn_genuine.copy()
    fn_genuine["sector"] = fn_genuine["ticker"].map(ticker_to_sector)
    fn_genuine["market_cap"] = fn_genuine["ticker"].map(market_caps)
    fn_genuine["prior_quarter_mean_z"] = [prior_quarter_mean_z(t, pd.Timestamp(d)) for t, d in
                                           zip(fn_genuine["ticker"], fn_genuine["earnings_date"])]

    # True positives for comparison
    tp = pd.read_csv(GROUP_A_PATH)
    tp = tp[tp["zscore"] >= Z_THRESHOLD].copy()
    tp["sector"] = tp["ticker"].map(ticker_to_sector)
    tp["market_cap"] = tp["ticker"].map(market_caps)

    print("=== FALSE NEGATIVE (genuine) vs TRUE POSITIVE characteristics ===\n")
    print(f"FN z-at-earnings-week: mean={fn_genuine['z_at_earnings_week'].mean():.2f}  "
          f"median={fn_genuine['z_at_earnings_week'].median():.2f}")
    print(f"TP z-score: mean={tp['zscore'].mean():.2f}  median={tp['zscore'].median():.2f}\n")

    print(f"FN market cap: mean=${fn_genuine['market_cap'].mean()/1e9:.1f}B  median=${fn_genuine['market_cap'].median()/1e9:.1f}B")
    print(f"TP market cap: mean=${tp['market_cap'].mean()/1e9:.1f}B  median=${tp['market_cap'].median()/1e9:.1f}B\n")

    print("FN sector composition:")
    print(fn_genuine["sector"].value_counts().to_string())
    print("\nTP sector composition:")
    print(tp["sector"].value_counts().to_string())

    print(f"\nFN prior-quarter mean z: mean={fn_genuine['prior_quarter_mean_z'].mean():.2f}  "
          f"median={fn_genuine['prior_quarter_mean_z'].median():.2f}")

    all_events.to_csv(OUT_PATH, index=False)
    fn_out = Path("Live Signal Engine") / "FalseNegative_Analysis_Detail.csv"
    fn_genuine.to_csv(fn_out, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"Wrote genuine-false-negative detail: {fn_out}")


if __name__ == "__main__":
    main()
