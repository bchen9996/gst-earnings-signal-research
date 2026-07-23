#!/usr/bin/env python3
# TASK 3 — Partial-week sampling noise: pulls MSFT's CURRENT (partial,
# in-progress) week 5 times with 60s gaps — unlike the earlier historical
# (2023, fully-closed) sampling-noise test, which found zero noise because
# closed periods are served deterministically, this tests the actual
# live/partial week the signal engine acts on every run, which genuinely
# accumulates search volume as the week progresses.
#
# *** LOWER-BOUND DISCLOSURE ***
# All 5 pulls happen within ~5 minutes. Noise observed here is a LOWER
# BOUND on real-world noise between live signal-engine runs, which
# typically happen hours or days apart — true run-to-run noise in
# production could be larger than what's measured here.
#
# Output: Live Signal Engine/PartialWeekSamplingNoise_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys, time
import numpy as np
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKER = "MSFT"
N_PULLS = 5
GAP_SECONDS = 60
PULL_LOOKBACK_DAYS = 300
GEO, GPROP, CATEGORY = "US", "", 0

ROLLING_WINDOW = 12
MIN_PERIODS = 8
Z_THRESHOLD = 2.0
STRONG_TIER_Z_THRESHOLD = 5.0

MAX_ATTEMPTS = 5
HARD_429_SLEEP = 60

OUT_PATH = Path("Live Signal Engine") / "PartialWeekSamplingNoise_Results.csv"


def fetch_pull(pt: TrendReq, attempt_label: str) -> pd.DataFrame:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=PULL_LOOKBACK_DAYS)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([TICKER], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or TICKER not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Week": df.index,
                "gst": pd.to_numeric(df[TICKER], errors="coerce"),
                "isPartial": df["isPartial"].astype(bool),
            }).sort_values("Week").reset_index(drop=True)
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg) else 5 * attempt
            print(f"  [{attempt_label}] attempt {attempt} failed: {e} -- sleeping {pause}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst", "isPartial"])


def base_tier(z):
    if z is None or pd.isna(z) or z < Z_THRESHOLD:
        return "none"
    return "STRONG" if z >= STRONG_TIER_Z_THRESHOLD else "STANDARD"


def compute_latest_zscore(df: pd.DataFrame) -> dict:
    if len(df) < MIN_PERIODS + 1:
        return {"zscore": None}
    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    z = (df["gst"] - rolling.mean()) / rolling.std()
    z = z.replace([np.inf, -np.inf], np.nan)
    latest_z = z.iloc[-1]
    latest = df.iloc[-1]
    return {
        "zscore": round(float(latest_z), 4) if pd.notna(latest_z) else None,
        "week": latest["Week"].date(), "gst_value": int(latest["gst"]) if pd.notna(latest["gst"]) else None,
        "is_partial_week": bool(latest["isPartial"]),
    }


def main():
    print(f"*** TASK 3: Partial-week sampling noise -- {TICKER}, {N_PULLS} pulls, {GAP_SECONDS}s gaps ***\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    results = []
    for i in range(1, N_PULLS + 1):
        print(f"--- Pull {i}/{N_PULLS} at {datetime.now(timezone.utc).isoformat()} ---")
        df = fetch_pull(pt, f"pull{i}")
        if df.empty:
            print(f"  Pull {i} FAILED entirely.")
            results.append({"pull": i, "status": "failed"})
        else:
            latest = compute_latest_zscore(df)
            tier = base_tier(latest["zscore"])
            print(f"  week={latest['week']} gst={latest['gst_value']} is_partial={latest['is_partial_week']} "
                  f"z={latest['zscore']} tier={tier}")
            results.append({"pull": i, "status": "ok", "week": latest["week"], "gst_value": latest["gst_value"],
                            "is_partial_week": latest["is_partial_week"], "zscore": latest["zscore"], "tier": tier})
        if i < N_PULLS:
            print(f"  Sleeping {GAP_SECONDS}s before next pull...")
            time.sleep(GAP_SECONDS)

    result_df = pd.DataFrame(results)
    result_df.to_csv(OUT_PATH, index=False)

    ok = result_df[result_df["status"] == "ok"]
    print(f"\n=== SUMMARY ({len(ok)}/{N_PULLS} pulls succeeded) ===")
    if len(ok) >= 2:
        gst_vals = ok["gst_value"].dropna().to_numpy(dtype=float)
        z_vals = ok["zscore"].dropna().to_numpy(dtype=float)
        tiers = ok["tier"].tolist()

        identical_gst = len(set(gst_vals.tolist())) == 1
        identical_z = len(set(np.round(z_vals, 6).tolist())) == 1
        print(f"(a) All 5 raw GST values identical: {identical_gst}   "
              f"range=[{gst_vals.min():.0f}, {gst_vals.max():.0f}]  spread={gst_vals.max()-gst_vals.min():.0f}")
        print(f"    All 5 z-scores identical: {identical_z}   "
              f"range=[{z_vals.min():.4f}, {z_vals.max():.4f}]  spread={z_vals.max()-z_vals.min():.4f}")

        tiers_differ = len(set(tiers)) > 1
        print(f"(c) Tier classifications across pulls: {tiers}")
        print(f"    Tier classification changed across pulls: {tiers_differ}")

        if not identical_gst or not identical_z:
            print(f"\n=> Partial-week GST IS subject to sampling noise (unlike the fully-closed-period test, "
                  f"which found zero noise) -- this is the noise that matters operationally.")
        else:
            print(f"\n=> No noise detected across these 5 pulls within ~{(N_PULLS-1)*GAP_SECONDS}s -- "
                  f"but see LOWER-BOUND disclosure in the script header before concluding partial-week "
                  f"data is fully stable in production (hours/days between real runs, not minutes).")
    else:
        print("Fewer than 2 successful pulls -- cannot assess noise.")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
