#!/usr/bin/env python3
# TASK 2 — Related queries breadth: for the 8 highest-frequency tickers'
# z>=5 STRONG_EARNINGS event weeks (n=90), pull pytrends related_queries()
# over that specific week's timeframe and compute breadth_score = number
# of queries in the "top" related-queries list (not "rising" — "top" is
# the stable/frequent list, "rising" is breakout/spiking terms, a
# different concept from what's being tested here).
#
# Rate-limited: 45s gaps between calls, max 5 retries per event. Failed
# pulls (rate-limit exhaustion) are recorded with status="rate_limited",
# NOT silently dropped.
#
# Output: Live Signal Engine/RelatedQueriesBreadth_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys, time
import numpy as np
import pandas as pd
import urllib3
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TEST_TICKERS = ["MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN"]
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "RelatedQueriesBreadth_Results.csv"

Z_THRESHOLD = 5.0
GAP_SECONDS = 45
MAX_RETRIES = 5
GEO, GPROP, CATEGORY = "US", "", 0
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def fetch_related_queries_breadth(pt: TrendReq, ticker: str, week_start, week_end) -> dict:
    timeframe = f"{week_start.date().isoformat()} {week_end.date().isoformat()}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pt.build_payload([ticker], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            rq = pt.related_queries()
            entry = rq.get(ticker)
            if entry is None:
                return {"status": "no_data", "breadth_score": None}
            top_df = entry.get("top")
            breadth = int(len(top_df)) if top_df is not None else 0
            return {"status": "ok", "breadth_score": breadth}
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "too many" in msg
            print(f"    attempt {attempt}/{MAX_RETRIES} failed ({'RATE LIMIT' if is_rate_limit else 'error'}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(60 if is_rate_limit else 10)
    return {"status": "rate_limited", "breadth_score": None}


def two_sample_permutation_test(a, b, n_perm, rng, stat="mean"):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    f = np.mean if stat == "mean" else np.median
    observed_diff = f(a) - f(b)
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = f(pooled[:n_a]) - f(pooled[n_a:])
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    print("*** TASK 2: Related queries breadth ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[(events["zscore"] >= Z_THRESHOLD) & (events["ticker"].isin(TEST_TICKERS))].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    events = events.sort_values(["ticker", "spike_week"]).reset_index(drop=True)
    print(f"Events to pull: n={len(events)}\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})

    rows = []
    for i, ev in events.iterrows():
        ticker, week_start = ev["ticker"], ev["spike_week"]
        week_end = week_start + timedelta(days=6)
        print(f"[{i+1}/{len(events)}] {ticker} {week_start.date()}...")
        res = fetch_related_queries_breadth(pt, ticker, week_start, week_end)
        rows.append({"ticker": ticker, "spike_week": week_start.date(), "zscore": ev["zscore"],
                     "status": res["status"], "breadth_score": res["breadth_score"],
                     "end_of_spike_week_win": ev["end_of_spike_week_win"],
                     "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"]})
        print(f"    -> status={res['status']} breadth_score={res['breadth_score']}")
        if i < len(events) - 1:
            time.sleep(GAP_SECONDS)

    result = pd.DataFrame(rows)

    n_ok = int((result["status"] == "ok").sum())
    n_rate_limited = int((result["status"] == "rate_limited").sum())
    n_no_data = int((result["status"] == "no_data").sum())
    print(f"\n=== PULL SUMMARY ===")
    print(f"ok: {n_ok}   rate_limited: {n_rate_limited}   no_data: {n_no_data}   total: {len(result)}")
    if n_rate_limited > 0:
        print(f"RATE-LIMITED EVENTS (not silently dropped, excluded from analysis below):")
        print(result[result["status"] == "rate_limited"][["ticker", "spike_week"]].to_string(index=False))

    usable = result[result["status"] == "ok"].copy()
    if len(usable) < 4:
        print("\nToo few usable pulls to split into high/low breadth groups. Stopping analysis.")
        result.to_csv(OUT_PATH, index=False)
        return

    median_breadth = usable["breadth_score"].median()
    usable["breadth_group"] = np.where(usable["breadth_score"] > median_breadth, "high_breadth",
                                np.where(usable["breadth_score"] < median_breadth, "low_breadth", "at_median"))
    print(f"\nMedian breadth_score: {median_breadth}")
    print(usable["breadth_group"].value_counts())

    rng = np.random.default_rng(RANDOM_SEED)
    summary_rows = []
    groups = {}
    for grp in ["high_breadth", "low_breadth"]:
        sub = usable[usable["breadth_group"] == grp]
        n = len(sub)
        if n == 0:
            continue
        win_rate = sub["end_of_spike_week_win"].mean() * 100
        median_pnl = sub["end_of_spike_week_pnl_pct"].median()
        groups[grp] = sub["end_of_spike_week_pnl_pct"].to_numpy(dtype=float)
        print(f"\n{grp}: n={n}  win={win_rate:.1f}%  median P&L={median_pnl:+.1f}%")
        summary_rows.append({"group": grp, "n": n, "win_rate_pct": round(win_rate, 1), "median_pnl_pct": round(median_pnl, 1)})

    if "high_breadth" in groups and "low_breadth" in groups:
        diff, p = two_sample_permutation_test(groups["high_breadth"], groups["low_breadth"], N_PERMUTATIONS, rng)
        print(f"\nHigh vs low breadth: diff in mean P&L={diff:+.1f}pt  p={p:.4f} ({'significant' if p < 0.05 else 'not significant'})")
        summary_rows.append({"group": "diff", "n": None, "win_rate_pct": None, "median_pnl_pct": round(diff, 1), "p_value": round(p, 4)})

    combined = pd.concat([result, pd.DataFrame([{}]), pd.DataFrame(summary_rows)], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
