#!/usr/bin/env python3
# Day-of-Week Sensitivity Test — EXPLORATORY, ONE-OFF DIAGNOSTIC.
#
# Question: for this specific in-progress week, would running the signal
# engine on Tuesday have produced a different z-score / tier than running
# it today? Google Trends only exposes the CURRENT state of its partial-
# week bucket — there is no way to retroactively query "what did the data
# look like as of Tuesday," so this can't be a true replay. Instead:
#   1. Pull the same 300-day WEEKLY-granularity series the production
#      engine uses, to get the trailing 12-week rolling mean/std (unchanged
#      regardless of which day mid-week you ask) and today's actual latest
#      partial-week value.
#   2. Separately pull a ~10-day DAILY-granularity series (a short enough
#      timeframe that Google Trends returns daily, not weekly, points),
#      covering this calendar week's individual days so far.
#   3. From the daily series, compute what FRACTION of the week's
#      cumulative interest had accrued by Tuesday vs by today, and apply
#      that fraction to today's actual weekly-query value to estimate what
#      the partial-week reading would have been on Tuesday.
#   4. Recompute the z-score with the estimated Tuesday value against the
#      SAME rolling mean/std (that part of the calculation never depends on
#      which day mid-week you run it).
#
# *** SCALING CAVEAT — DISCLOSED ***
# Google Trends independently re-normalizes each query's values to its own
# 0-100 scale based on that query's specific term+timeframe combination.
# The daily-granularity query (10-day window) is NOT on the same absolute
# scale as the weekly-granularity query (300-day window) — so daily values
# from step 2 are never compared to weekly values from step 1 directly.
# Only the INTRA-QUERY ratio (Tuesday-cumulative / today-cumulative, both
# from the same daily-granularity query) is used, and that ratio is applied
# multiplicatively to today's own weekly-query value. This is the best
# available proxy for "what fraction of this week's interest existed by
# Tuesday," not an exact reconstruction of what a true Tuesday weekly-
# granularity query would have returned (Google's own smoothing/rounding
# could differ slightly by query). Treat results as directional, not exact.
#
# Output: Live Signal Engine/DayOfWeek_Sensitivity_Test.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys, time, random
import pandas as pd
import numpy as np
import urllib3
from pytrends.request import TrendReq

import GST_Live_Signal_Engine as engine

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = ["NFLX", "AMZN", "MSFT", "SBUX", "NKE", "STZ", "QCOM", "ADBE"]

DAILY_LOOKBACK_DAYS = 10   # 8-269 days -> Google Trends returns DAILY granularity
BETWEEN_TICKERS = (1.5, 3.0)
MAX_ATTEMPTS = 5
HARD_429_SLEEP = 60

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_daily_granularity_series(pt: TrendReq, term: str) -> pd.DataFrame:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=DAILY_LOOKBACK_DAYS)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([term], timeframe=timeframe, geo=engine.GEO, gprop=engine.GPROP, cat=engine.CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Date": pd.to_datetime(df.index).date,
                "gst": pd.to_numeric(df[term], errors="coerce"),
                "isPartial": df["isPartial"].astype(bool),
            }).sort_values("Date").reset_index(drop=True)
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or ("rate" in msg and "limit" in msg) or "too many" in msg) \
                else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"[{term}] daily-granularity attempt {attempt} failed: {e} — sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Date", "gst", "isPartial"])


def compute_roll_mean_std(weekly_df: pd.DataFrame) -> tuple[float | None, float | None]:
    """Same rolling calc as compute_latest_zscore, but returns the mean/std alone
    so a substitute current-week value can be swapped in."""
    if len(weekly_df) < engine.MIN_PERIODS + 1:
        return None, None
    rolling = weekly_df["gst"].shift(1).rolling(window=engine.ROLLING_WINDOW, min_periods=engine.MIN_PERIODS)
    roll_mean = rolling.mean().iloc[-1]
    roll_std = rolling.std().iloc[-1]
    if pd.isna(roll_mean) or pd.isna(roll_std) or roll_std == 0:
        return None, None
    return float(roll_mean), float(roll_std)


def main():
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=(today.weekday() + 1) % 7)   # Sunday, GST's week-label convention
    this_tuesday = week_start + timedelta(days=2)
    print(f"Day-of-week sensitivity test — today is {today.strftime('%A')} {today.isoformat()}, "
          f"this week's Tuesday would have been {this_tuesday.isoformat()}\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    rows = []
    for i, ticker in enumerate(TICKERS, start=1):
        print(f"--- [{i}/{len(TICKERS)}] {ticker} ---")

        weekly = engine.fetch_ticker_series(pt, ticker)
        time.sleep(random.uniform(*BETWEEN_TICKERS))
        daily = fetch_daily_granularity_series(pt, ticker)
        time.sleep(random.uniform(*BETWEEN_TICKERS))

        if weekly.empty or daily.empty:
            rows.append({"ticker": ticker, "status": "pull_failed"})
            print(f"[{ticker}] pull failed (weekly empty={weekly.empty}, daily empty={daily.empty})")
            continue

        roll_mean, roll_std = compute_roll_mean_std(weekly)
        if roll_mean is None:
            rows.append({"ticker": ticker, "status": "insufficient_weekly_history"})
            print(f"[{ticker}] insufficient weekly history for rolling baseline")
            continue

        today_actual_gst = float(weekly["gst"].iloc[-1])
        today_actual_z = round((today_actual_gst - roll_mean) / roll_std, 3)
        today_tier = engine.base_tier(today_actual_z)

        week_days = daily[daily["Date"] >= week_start]
        through_tuesday = week_days[week_days["Date"] <= this_tuesday]
        through_today = week_days[week_days["Date"] <= today]

        if through_tuesday.empty or through_today.empty or through_today["gst"].sum() == 0:
            rows.append({"ticker": ticker, "status": "insufficient_daily_week_data",
                         "today_actual_zscore": today_actual_z, "today_tier": today_tier})
            print(f"[{ticker}] daily-granularity pull didn't cover enough of this week — "
                  f"reporting today's actual z only (z={today_actual_z}, tier={today_tier})")
            continue

        cum_tuesday = float(through_tuesday["gst"].sum())
        cum_today = float(through_today["gst"].sum())
        ratio = cum_tuesday / cum_today
        estimated_tuesday_gst = today_actual_gst * ratio
        estimated_tuesday_z = round((estimated_tuesday_gst - roll_mean) / roll_std, 3)
        tuesday_tier = engine.base_tier(estimated_tuesday_z)

        classification_differs = (today_tier != tuesday_tier)

        rows.append({
            "ticker": ticker, "status": "ok",
            "roll_mean": round(roll_mean, 2), "roll_std": round(roll_std, 2),
            "today_actual_gst": today_actual_gst, "today_actual_zscore": today_actual_z, "today_tier": today_tier,
            "tuesday_fraction_of_week_so_far": round(ratio, 3),
            "estimated_tuesday_gst": round(estimated_tuesday_gst, 2),
            "estimated_tuesday_zscore": estimated_tuesday_z, "estimated_tuesday_tier": tuesday_tier,
            "classification_differs": classification_differs,
        })
        print(f"[{ticker}] today: gst={today_actual_gst} z={today_actual_z} tier={today_tier}  |  "
              f"est. Tuesday: gst≈{estimated_tuesday_gst:.1f} z={estimated_tuesday_z} tier={tuesday_tier}  "
              f"{'>>> DIFFERS <<<' if classification_differs else '(same)'}")

        if i != len(TICKERS):
            print(f"— pausing before next ticker —")
            time.sleep(20)

    result = pd.DataFrame(rows)
    out_path = OUT_DIR / "DayOfWeek_Sensitivity_Test.csv"
    result.to_csv(out_path, index=False)

    print(f"\n=== SUMMARY ===")
    if "classification_differs" in result.columns:
        n_differs = result["classification_differs"].sum()
        n_ok = (result["status"] == "ok").sum()
        print(f"{n_differs}/{n_ok} ticker(s) with usable data show a DIFFERENT tier classification "
              f"between today's actual reading and the estimated Tuesday reading.")
    print("Reminder: this is a same-day reconstruction using intra-week daily proportions, not a true "
          "historical replay — see script header for the scaling caveat.")
    print(f"\nWrote results to: {out_path}")


if __name__ == "__main__":
    main()
