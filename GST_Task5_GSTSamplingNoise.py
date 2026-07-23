#!/usr/bin/env python3
# TASK 5 — GST sampling noise: pull MSFT's 2023 weekly GST series 5
# separate times (45s gaps) and quantify how much pytrends' own sampling
# noise varies run-to-run, and whether that noise is large enough to flip
# tier classifications.
#
# Output: Live Signal Engine/GSTSamplingNoise_Results.csv

from __future__ import annotations
from pathlib import Path
import sys, time
import numpy as np
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKER = "MSFT"
N_PULLS = 5
GAP_SECONDS = 45
TIMEFRAME = "2023-01-01 2023-12-31"
GEO, GPROP, CATEGORY = "US", "", 0

ROLLING_WINDOW = 12
Z_THRESHOLD = 2.0
STRONG_TIER_Z_THRESHOLD = 5.0
MIN_PERIODS = 8

MAX_ATTEMPTS = 5
HARD_429_SLEEP = 60

OUT_PATH = Path("Live Signal Engine") / "GSTSamplingNoise_Results.csv"


def fetch_pull(pt: TrendReq, attempt_label: str) -> pd.DataFrame:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([TICKER], timeframe=TIMEFRAME, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or TICKER not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Week": df.index,
                "gst": pd.to_numeric(df[TICKER], errors="coerce"),
            }).sort_values("Week").reset_index(drop=True)
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg) else 5 * attempt
            print(f"  [{attempt_label}] attempt {attempt} failed: {e} -- sleeping {pause}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst"])


def base_tier(z):
    if z is None or pd.isna(z) or z < Z_THRESHOLD:
        return "none"
    return "STRONG" if z >= STRONG_TIER_Z_THRESHOLD else "STANDARD"


def compute_zscore_series(df: pd.DataFrame) -> pd.Series:
    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    z = (df["gst"] - rolling.mean()) / rolling.std()
    return z.replace([np.inf, -np.inf], np.nan)


def main():
    print(f"*** TASK 5: GST sampling noise — {TICKER}, {TIMEFRAME}, {N_PULLS} pulls, {GAP_SECONDS}s gaps ***\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    pulls = []
    for i in range(1, N_PULLS + 1):
        print(f"--- Pull {i}/{N_PULLS} ---")
        df = fetch_pull(pt, f"pull{i}")
        if df.empty:
            print(f"  Pull {i} FAILED entirely.")
        else:
            df["zscore"] = compute_zscore_series(df)
            df["tier"] = df["zscore"].apply(base_tier)
            print(f"  Pull {i}: {len(df)} weeks retrieved.")
        pulls.append(df)
        if i < N_PULLS:
            print(f"  Sleeping {GAP_SECONDS}s before next pull...")
            time.sleep(GAP_SECONDS)

    valid_pulls = [p for p in pulls if not p.empty]
    print(f"\n{len(valid_pulls)}/{N_PULLS} pulls succeeded.\n")
    if len(valid_pulls) < 2:
        print("Fewer than 2 successful pulls -- cannot compare sampling noise. Stopping.")
        return

    merged = valid_pulls[0][["Week", "gst", "zscore", "tier"]].rename(
        columns={"gst": "gst_1", "zscore": "z_1", "tier": "tier_1"})
    for i, p in enumerate(valid_pulls[1:], start=2):
        merged = merged.merge(
            p[["Week", "gst", "zscore", "tier"]].rename(columns={"gst": f"gst_{i}", "zscore": f"z_{i}", "tier": f"tier_{i}"}),
            on="Week", how="outer")
    merged = merged.sort_values("Week").reset_index(drop=True)

    n_pulls_ok = len(valid_pulls)
    gst_cols = [f"gst_{i}" for i in range(1, n_pulls_ok + 1)]
    z_cols = [f"z_{i}" for i in range(1, n_pulls_ok + 1)]
    tier_cols = [f"tier_{i}" for i in range(1, n_pulls_ok + 1)]

    merged["gst_mean_abs_diff"] = merged[gst_cols].apply(lambda row: np.mean(np.abs(np.diff(row.dropna()))) if row.notna().sum() > 1 else np.nan, axis=1)
    merged["z_max_diff"] = merged[z_cols].apply(lambda row: row.max() - row.min() if row.notna().sum() > 1 else np.nan, axis=1)
    merged["tiers_differ"] = merged[tier_cols].apply(lambda row: row.dropna().nunique() > 1, axis=1)

    n_weeks = len(merged)
    mean_abs_diff_overall = merged["gst_mean_abs_diff"].mean()
    n_tier_differ = merged["tiers_differ"].sum()
    max_z_diff_overall = merged["z_max_diff"].max()
    max_z_diff_week = merged.loc[merged["z_max_diff"].idxmax(), "Week"] if merged["z_max_diff"].notna().any() else None

    print(f"=== RESULTS ({n_weeks} weeks, {n_pulls_ok} valid pulls) ===")
    print(f"(a) Mean absolute difference in raw GST value across pulls, averaged over all weeks: {mean_abs_diff_overall:.2f}")
    print(f"(b) Weeks with different tier classification across pulls: {n_tier_differ}/{n_weeks}")
    print(f"(c) Maximum single-week z-score difference across pulls: {max_z_diff_overall:.3f} (week of {max_z_diff_week})")

    if n_tier_differ > 0:
        print(f"\nWeeks with tier disagreement:")
        print(merged.loc[merged["tiers_differ"], ["Week"] + gst_cols + z_cols + tier_cols].to_string(index=False))

    merged.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
