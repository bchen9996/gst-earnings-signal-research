#!/usr/bin/env python3
# TASK 3 — Information leakage test: does z-score magnitude correlate with
# EPS surprise size, and do z>=5 STRONG_EARNINGS weeks show bigger EPS
# surprises than non-spike earnings-adjacent weeks? If GST spikes were
# just picking up pre-leaked knowledge of the surprise itself, this would
# show up as a strong, mechanical correlation.
#
# Group A = z>=5 STRONG_EARNINGS events, n=147, 28 unique tickers.
# Group B = non-spike earnings-adjacent events, n=110, 41 unique tickers
# (union of both: 50 tickers — one yfinance get_earnings_dates() pull per
# unique ticker, cached, ~50 calls total, with retry given past transient
# per-ticker failures seen in this project).
#
# For each event, matches to the ticker's ACTUAL earnings report nearest
# the event's anchor date (within 5 days, same convention as the BMO/AMC
# timing test) and pulls its Surprise(%) (reported EPS vs consensus,
# already a percentage per yfinance's own units — not re-derived).
#
# Output: Live Signal Engine/Task3_InformationLeakageTest_Results.csv

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
GROUP_B_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_b_nospike_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task3_InformationLeakageTest_Results.csv"

Z_THRESHOLD = 5.0
EARNINGS_PULL_LIMIT = 40
MAX_MATCH_GAP_DAYS = 5
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_surprise_history(ticker: str, max_attempts: int = 3) -> pd.DataFrame:
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
    }).dropna(subset=["date"])
    return out


def match_nearest_surprise(hist: pd.DataFrame, anchor: date) -> tuple[float | None, str]:
    if hist.empty:
        return None, "no_earnings_history"
    valid = hist.dropna(subset=["surprise_pct"])
    if valid.empty:
        return None, "no_surprise_data"
    gaps = (pd.to_datetime(valid["date"]) - pd.Timestamp(anchor)).abs().dt.days
    nearest_idx = gaps.idxmin()
    if gaps.loc[nearest_idx] > MAX_MATCH_GAP_DAYS:
        return None, "no_earnings_date_within_5d"
    return float(valid.loc[nearest_idx, "surprise_pct"]), "ok"


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


def spearman_corr(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Spearman rank correlation with a permutation-based p-value (consistent with this
    project's permutation-testing convention rather than a parametric t-approximation)."""
    rng = np.random.default_rng(RANDOM_SEED)
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    observed_r = np.corrcoef(xr, yr)[0, 1]
    n_perm = 10000
    count = 0
    yr_shuffled = yr.copy()
    for _ in range(n_perm):
        rng.shuffle(yr_shuffled)
        r = np.corrcoef(xr, yr_shuffled)[0, 1]
        if abs(r) >= abs(observed_r):
            count += 1
    return observed_r, count / n_perm


def main():
    a = pd.read_csv(GROUP_A_PATH)
    a = a[a["zscore"] >= Z_THRESHOLD].copy()
    a["anchor"] = pd.to_datetime(a["spike_week"]).dt.date
    a["group"] = "A_STRONG_EARNINGS"

    b = pd.read_csv(GROUP_B_PATH)
    b["anchor"] = pd.to_datetime(b["anchor"]).dt.date
    b["group"] = "B_no_spike_earnings_adjacent"
    b["zscore"] = np.nan  # Group B has no z-score (baseline/random weeks)

    all_tickers = sorted(set(a["ticker"]) | set(b["ticker"]))
    print(f"Group A (z>={Z_THRESHOLD:g}): n={len(a)}, {a['ticker'].nunique()} tickers")
    print(f"Group B (no-spike): n={len(b)}, {b['ticker'].nunique()} tickers")
    print(f"Union: {len(all_tickers)} unique tickers to pull\n")

    print("Pulling EPS surprise history per ticker (cached, one pull each, with retry)...")
    history_cache: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(all_tickers, start=1):
        history_cache[ticker] = fetch_surprise_history(ticker)
        print(f"  [{i}/{len(all_tickers)}] {ticker}: {len(history_cache[ticker])} historical surprise records")
        time.sleep(0.8)
    print()

    rows = []
    for _, ev in pd.concat([a, b], ignore_index=True).iterrows():
        ticker, anchor, group = ev["ticker"], ev["anchor"], ev["group"]
        hist = history_cache.get(ticker, pd.DataFrame())
        surprise, status = match_nearest_surprise(hist, anchor)
        rows.append({
            "ticker": ticker, "anchor": anchor, "group": group, "zscore": ev["zscore"],
            "surprise_pct": surprise, "abs_surprise_pct": abs(surprise) if surprise is not None else None,
            "status": status,
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    n_total = len(result)
    n_matched = result["surprise_pct"].notna().sum()
    print(f"Overall EPS surprise match coverage: {n_matched}/{n_total} = {n_matched/n_total*100:.1f}%")
    for status, cnt in result["status"].value_counts().items():
        print(f"  {status}: {cnt}")
    print()

    # --- Test 1: z-score magnitude vs |surprise|, within Group A only (has real z-scores) ---
    a_matched = result[(result["group"] == "A_STRONG_EARNINGS") & (result["abs_surprise_pct"].notna())]
    print(f"=== TEST 1: z-score vs |EPS surprise| correlation (Group A, n={len(a_matched)}) ===")
    if len(a_matched) >= 5:
        r, p = spearman_corr(a_matched["zscore"].to_numpy(dtype=float),
                              a_matched["abs_surprise_pct"].to_numpy(dtype=float))
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Spearman r={r:+.3f}  permutation p={p:.4f} ({sig})")
    else:
        print("Not enough matched events to test correlation.")
    print()

    # --- Test 2: Group A |surprise| vs Group B |surprise| ---
    a_surp = result[(result["group"] == "A_STRONG_EARNINGS") & (result["abs_surprise_pct"].notna())]["abs_surprise_pct"].to_numpy(dtype=float)
    b_surp = result[(result["group"] == "B_no_spike_earnings_adjacent") & (result["abs_surprise_pct"].notna())]["abs_surprise_pct"].to_numpy(dtype=float)
    print(f"=== TEST 2: |EPS surprise| — Group A (n={len(a_surp)}) vs Group B (n={len(b_surp)}) ===")
    if len(a_surp) and len(b_surp):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p, a_mean, b_mean = two_sample_permutation_test(a_surp, b_surp, N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Group A: mean={a_mean:.2f}%  median={np.median(a_surp):.2f}%")
        print(f"Group B: mean={b_mean:.2f}%  median={np.median(b_surp):.2f}%")
        print(f"Diff (A - B): {diff:+.2f}pts  two-sided p={p:.4f} ({sig})")
        if p < 0.05 and diff > 0:
            print("=> z>=5 weeks DO show significantly larger EPS surprises — possible information leakage into GST.")
        else:
            print("=> No significant difference — GST spikes are not simply proxying for surprise magnitude.")
    else:
        print("Not enough matched events in one or both groups.")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
