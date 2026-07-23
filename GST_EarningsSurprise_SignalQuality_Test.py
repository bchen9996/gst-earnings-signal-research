#!/usr/bin/env python3
# Earnings Surprise History as a Signal Quality Filter — does a ticker's
# track record of large earnings surprises predict better straddle
# economics when it ALSO generates a GST spike?
#
# Universe: STRONG_EARNINGS events (z>=5, near_earnings=True) from the
# 2021-2025 51-ticker dataset, loaded from the existing on-disk Group A
# file (Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv) and filtered to zscore>=5 — the
# CURRENT live threshold (see GST_Live_Signal_Engine.py's THRESHOLD
# REFINEMENT note), n=147 of the file's 209 rows, 28 unique tickers.
# Straddle P&L (both horizons, earnings-aware pricing) is reused as-is
# from that file — not recomputed.
#
# For each event, pulls the ticker's average ABSOLUTE earnings surprise
# over the 4 most recent quarters STRICTLY BEFORE the event's anchor date
# (point-in-time: never uses a surprise from the earnings report the spike
# itself might be anticipating, or any later quarter). One yfinance
# get_earnings_dates() pull per unique ticker (28 calls, cached), not per
# event — the point-in-time slicing happens locally against the cached
# history, no repeated pulls.
#   high surprise history: avg |surprise| > 5%
#   low surprise history:  avg |surprise| <= 5%
#
# *** DATA COMPLETENESS CAVEAT ***
# Requires at least 3 of the 4 most recent prior quarters to have a
# non-null Surprise(%) value (yfinance sometimes has gaps, especially for
# older or newly-listed tickers). Events with fewer than 3 usable prior
# quarters are excluded and counted separately, not silently dropped.
#
# *** THIS IS EXPLORATORY / UNVALIDATED — same standard as this project's
# other exploratory tests. An association here has not been out-of-sample
# tested and is not wired into the live signal engine or straddle logger.
#
# Output: Live Signal Engine/EarningsSurprise_SignalQuality_Test.csv

from __future__ import annotations
from pathlib import Path
from datetime import date
import sys, time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

Z_THRESHOLD = 5.0          # current live STRONG threshold, matches GST_Live_Signal_Engine.py
EARNINGS_PULL_LIMIT = 40   # ~10 years of quarters — comfortably covers 2021-2025 + buffer, well under Yahoo's 100 cap
PRIOR_QUARTERS_WINDOW = 4
MIN_USABLE_PRIOR_QUARTERS = 3
SURPRISE_THRESHOLD_PCT = 5.0
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_earnings_surprise_history(ticker: str, max_attempts: int = 3) -> pd.DataFrame:
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
    if df is None or df.empty or "Surprise(%)" not in df.columns:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df.index).tz_localize(None).normalize().date,
        "surprise_pct": pd.to_numeric(df["Surprise(%)"], errors="coerce"),
    }).dropna(subset=["date"]).sort_values("date", ascending=False).reset_index(drop=True)
    return out


def avg_abs_prior_surprise(history: pd.DataFrame, anchor: date) -> tuple[float | None, int]:
    prior = history[history["date"] < anchor].head(PRIOR_QUARTERS_WINDOW)
    usable = prior["surprise_pct"].dropna()
    if len(usable) < MIN_USABLE_PRIOR_QUARTERS:
        return None, len(usable)
    return float(usable.abs().mean()), len(usable)


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

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"]).dt.date
    tickers = sorted(events["ticker"].unique())
    print(f"STRONG_EARNINGS events at z>={Z_THRESHOLD:g}: n={len(events)} across {len(tickers)} unique tickers\n")

    print("Pulling earnings-surprise history per ticker (cached, one pull each)...")
    history_cache: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(tickers, start=1):
        history_cache[ticker] = fetch_earnings_surprise_history(ticker)
        n = len(history_cache[ticker])
        print(f"  [{i}/{len(tickers)}] {ticker}: {n} historical surprise records")
        time.sleep(0.8)
    print()

    rows = []
    n_excluded = 0
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        hist = history_cache.get(ticker, pd.DataFrame())
        if hist.empty:
            n_excluded += 1
            continue
        avg_surprise, n_usable = avg_abs_prior_surprise(hist, anchor)
        if avg_surprise is None:
            n_excluded += 1
            continue
        group = "high_surprise_history" if avg_surprise > SURPRISE_THRESHOLD_PCT else "low_surprise_history"
        rows.append({
            "ticker": ticker, "spike_week": anchor, "zscore": ev["zscore"],
            "avg_abs_prior_surprise_pct": round(avg_surprise, 2), "n_prior_quarters_used": n_usable,
            "surprise_group": group,
            "end_of_spike_week_win": ev["end_of_spike_week_win"], "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
            "end_of_window_win": ev["end_of_window_win"], "end_of_window_pnl_pct": ev["end_of_window_pnl_pct"],
        })

    result = pd.DataFrame(rows)
    out_path = OUT_DIR / "EarningsSurprise_SignalQuality_Test.csv"
    result.to_csv(out_path, index=False)

    print(f"Usable events: n={len(result)}   Excluded (missing/insufficient surprise history): n={n_excluded}\n")

    rng = np.random.default_rng(RANDOM_SEED)
    high = result[result["surprise_group"] == "high_surprise_history"]
    low = result[result["surprise_group"] == "low_surprise_history"]
    print(f"High surprise history (avg|surprise|>{SURPRISE_THRESHOLD_PCT:g}%): n={len(high)}")
    print(f"Low surprise history  (avg|surprise|<={SURPRISE_THRESHOLD_PCT:g}%): n={len(low)}\n")

    for h in ["end_of_spike_week", "end_of_window"]:
        win_col, pnl_col = f"{h}_win", f"{h}_pnl_pct"
        h_usable = high[high[win_col].notna()]
        l_usable = low[low[win_col].notna()]

        print(f"=== {h} ===")
        if len(h_usable):
            print(f"High surprise history: n={len(h_usable):<4} win={h_usable[win_col].mean()*100:5.1f}%  "
                  f"avg={h_usable[pnl_col].mean():+7.1f}%  median={h_usable[pnl_col].median():+7.1f}%")
        if len(l_usable):
            print(f"Low surprise history:  n={len(l_usable):<4} win={l_usable[win_col].mean()*100:5.1f}%  "
                  f"avg={l_usable[pnl_col].mean():+7.1f}%  median={l_usable[pnl_col].median():+7.1f}%")
        if len(h_usable) and len(l_usable):
            diff, p, h_mean, l_mean = two_sample_permutation_test(
                h_usable[pnl_col].to_numpy(dtype=float), l_usable[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
            sig = "significant" if p < 0.05 else "not significant"
            print(f"Diff (High - Low): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")
        print()

    print("Reminder: EXPLORATORY / UNVALIDATED association test. Not wired into the live signal engine or straddle logger.")
    print(f"\nWrote event-level data to: {out_path}")


if __name__ == "__main__":
    main()
