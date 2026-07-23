#!/usr/bin/env python3
# Earnings Timing (BMO vs AMC) as a Signal Quality Filter — does whether a
# ticker reported before market open vs after market close affect
# STRONG_EARNINGS (z>=5) straddle economics?
#
# Universe: z>=5 STRONG_EARNINGS events, n=147, 28 unique tickers, loaded
# from the existing on-disk Group A file (Earnings-Adjacent Spike vs
# No-Spike Test/group_a_z4_earnings_adjacent.csv) and filtered to the
# current live threshold. Straddle P&L (spike_week horizon, earnings-aware
# pricing) reused as-is, not recomputed.
#
# *** BMO/AMC CLASSIFICATION METHOD ***
# yfinance's get_earnings_dates() returns a timestamp with a time-of-day
# component. Spot-checking several tickers showed this is NOT random —
# tickers that consistently report after the close show ~16:00 ET
# uniformly, tickers that consistently report before the open show times
# in the 06:00-09:00 ET range, with occasional genuine variation (e.g. one
# STZ quarter reported at 08:00 instead of its usual 16:00) — so this
# looks like a real (if bucketed/approximate) BMO/AMC signal, not just a
# placeholder default. Classification: hour < 12 -> BMO, hour >= 16 ->
# AMC. Anything in between (12:00-15:59, i.e. during-market-hours, which
# would be unusual for a real earnings release) is flagged AMBIGUOUS
# rather than guessed into either bucket.
#
# For each event, finds the ticker's earnings date NEAREST to the event's
# spike_week anchor (all 147 events are already near_earnings=True, gap<=5
# days by construction, so this recovers the specific earnings report each
# spike is presumably reacting to) and classifies that date's time.
#
# *** COVERAGE DISCLOSURE ***
# If overall BMO+AMC classification coverage falls below 70% of the 147
# events, that is reported explicitly rather than silently proceeding as
# if the classified subset were representative.
#
# Output: Live Signal Engine/EarningsTiming_SignalQuality_Test.csv

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
OUT_PATH = OUT_DIR / "EarningsTiming_SignalQuality_Test.csv"

Z_THRESHOLD = 5.0
EARNINGS_PULL_LIMIT = 40
MAX_MATCH_GAP_DAYS = 5   # matches the near_earnings within_5d definition already used to build Group A
COVERAGE_WARN_THRESHOLD = 0.70
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_earnings_history(ticker: str, max_attempts: int = 3) -> pd.DataFrame:
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


def classify_timing(hist: pd.DataFrame, anchor: date) -> tuple[str, int | None]:
    if hist.empty:
        return "no_earnings_history", None
    gaps = (pd.to_datetime(hist["date"]) - pd.Timestamp(anchor)).abs().dt.days
    nearest_idx = gaps.idxmin()
    nearest_gap = int(gaps.loc[nearest_idx])
    if nearest_gap > MAX_MATCH_GAP_DAYS:
        return "no_earnings_date_within_5d", None
    hour = int(hist.loc[nearest_idx, "hour"])
    if hour < 12:
        return "BMO", hour
    elif hour >= 16:
        return "AMC", hour
    else:
        return "AMBIGUOUS_intraday_time", hour


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
    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"]).dt.date
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} unique tickers\n")

    print("Pulling earnings-date history per ticker (cached, one pull each, with retry)...")
    history_cache: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(tickers, start=1):
        history_cache[ticker] = fetch_earnings_history(ticker)
        print(f"  [{i}/{len(tickers)}] {ticker}: {len(history_cache[ticker])} historical earnings dates")
        time.sleep(0.8)
    print()

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        hist = history_cache.get(ticker, pd.DataFrame())
        timing, hour = classify_timing(hist, anchor)
        rows.append({
            "ticker": ticker, "spike_week": anchor, "zscore": ev["zscore"],
            "reported_hour_et": hour, "timing": timing,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    result = pd.DataFrame(rows)
    out_path = OUT_PATH
    result.to_csv(out_path, index=False)

    n_total = len(result)
    n_classified = (result["timing"].isin(["BMO", "AMC"])).sum()
    coverage = n_classified / n_total
    print(f"Classification coverage: {n_classified}/{n_total} = {coverage*100:.1f}%")
    for status, cnt in result["timing"].value_counts().items():
        print(f"  {status}: {cnt}")
    print()

    if coverage < COVERAGE_WARN_THRESHOLD:
        print(f"*** COVERAGE BELOW {COVERAGE_WARN_THRESHOLD*100:.0f}% THRESHOLD — reporting what's available, "
              f"but this is NOT a representative full-sample result. ***\n")

    bmo = result[result["timing"] == "BMO"]
    amc = result[result["timing"] == "AMC"]
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    bmo_u = bmo[bmo[win_col].notna()]
    amc_u = amc[amc[win_col].notna()]

    print(f"=== BMO vs AMC — spike_week horizon ===")
    if len(bmo_u):
        print(f"BMO: n={len(bmo_u):<4} win={bmo_u[win_col].mean()*100:5.1f}%  "
              f"avg={bmo_u[pnl_col].mean():+7.1f}%  median={bmo_u[pnl_col].median():+7.1f}%")
    if len(amc_u):
        print(f"AMC: n={len(amc_u):<4} win={amc_u[win_col].mean()*100:5.1f}%  "
              f"avg={amc_u[pnl_col].mean():+7.1f}%  median={amc_u[pnl_col].median():+7.1f}%")
    if len(bmo_u) and len(amc_u):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p, bmo_mean, amc_mean = two_sample_permutation_test(
            bmo_u[pnl_col].to_numpy(dtype=float), amc_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Diff (BMO - AMC): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")

    print("\nReminder: EXPLORATORY / UNVALIDATED association test. Not wired into the live signal engine or straddle logger.")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
