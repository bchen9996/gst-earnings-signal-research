#!/usr/bin/env python3
# GDELT Pre-Spike News Volume Test — does news article volume in the 7 days
# BEFORE a STRONG_EARNINGS GST spike differ from the 7 days before a
# non-spike earnings-adjacent week? Historical (2021-2025), via GDELT's
# DOC 2.0 API, which — unlike Google News RSS or NewsAPI — supports
# arbitrary historical date-range queries, needed since these events are
# years in the past.
#
# Universe: Group A = STRONG_EARNINGS events, z>=4, near_earnings=True,
# n=209 — the FULL original Group A file, used here exactly as the task
# specified (n=209), NOT filtered to the current live z>=5 threshold
# (n=147). Flagged explicitly so this isn't later confused with the live
# engine's threshold — this is a deliberately broader historical sample for
# statistical power on a leading-indicator question, independent of what
# the live engine currently gates on.
# Group B = non-spike earnings-adjacent weeks, n=110. Both loaded directly
# from Earnings-Adjacent Spike vs No-Spike Test/*.csv (already on disk).
#
# *** SCALE / RATE-LIMIT DISCLOSURE ***
# GDELT's stated policy is "one request per 5 seconds," but empirically in
# this environment (shared/proxied IP) that was nowhere near sufficient —
# 5s, 6s, 20s, and 30s gaps all hit HTTP 429; only ~45-60s gaps reliably
# succeeded during manual testing. This script paces every call at
# BASE_PAUSE_S=65s with additional escalating backoff on 429, so a full
# 319-event run takes 5-6+ hours minimum. Progress is written to disk
# incrementally (append, flushed after every event) and the script SKIPS
# any (ticker, anchor, group) already present in the output file, so it is
# safely resumable if interrupted and re-run.
#
# *** COUNT CAP ***
# mode=ArtList caps at maxrecords=250 — GDELT does not return a separate
# "true total" count field in this mode, so any week with >250 matching
# articles is reported as exactly 250, an undercount. This matters most for
# mega-cap tickers in unusually newsy weeks; disclosed, not hidden.
#
# Output: Live Signal Engine/GDELT_PreSpike_NewsVolume_Test.csv  (append-only, resumable)

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys, time
import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
GROUP_B_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_b_nospike_earnings_adjacent.csv"
OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "GDELT_PreSpike_NewsVolume_Test.csv"

PRE_WINDOW_DAYS = 7
MAXRECORDS = 250
BASE_PAUSE_S = 65
MAX_ATTEMPTS = 4
BACKOFF_429_S = [75, 90, 120, 150]
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "gst-research-monitor/0.1 (contact: hakurati11@gmail.com)"})


def gdelt_query_string(ticker: str) -> str:
    return f"{ticker.replace('-', ' ')} stock"


def fetch_gdelt_article_count(ticker: str, start, end) -> tuple[int | None, str]:
    params = {
        "query": gdelt_query_string(ticker),
        "mode": "ArtList",
        "format": "json",
        "maxrecords": MAXRECORDS,
        "startdatetime": start.strftime("%Y%m%d") + "000000",
        "enddatetime": end.strftime("%Y%m%d") + "235959",
    }
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = SESSION.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=30)
        except Exception as e:
            return None, f"error: {e}"

        if r.status_code == 429:
            pause = BACKOFF_429_S[min(attempt - 1, len(BACKOFF_429_S) - 1)]
            print(f"    [{ticker}] 429, attempt {attempt}/{MAX_ATTEMPTS} — sleeping {pause}s")
            time.sleep(pause)
            continue
        if r.status_code != 200:
            return None, f"http_{r.status_code}"
        try:
            data = r.json()
        except Exception:
            return None, "parse_error"
        articles = data.get("articles", [])
        return len(articles), "ok"

    return None, "429_exhausted"


def load_events():
    a = pd.read_csv(GROUP_A_PATH)
    a["anchor"] = pd.to_datetime(a["spike_week"])
    a = a[["ticker", "anchor"]].copy()
    a["group"] = "A_STRONG_EARNINGS"

    b = pd.read_csv(GROUP_B_PATH)
    b["anchor"] = pd.to_datetime(b["anchor"])
    b = b[["ticker", "anchor"]].copy()
    b["group"] = "B_no_spike_earnings_adjacent"

    return pd.concat([a, b], ignore_index=True)


def load_already_done() -> set:
    if not OUT_PATH.exists():
        return set()
    df = pd.read_csv(OUT_PATH)
    return set(zip(df["ticker"], df["anchor"].astype(str), df["group"]))


def append_row(row: dict):
    df = pd.DataFrame([row])
    df.to_csv(OUT_PATH, mode="a", index=False, header=not OUT_PATH.exists())


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
    events = load_events()
    print(f"Total events to check: {len(events)} (Group A n={len(events[events['group']=='A_STRONG_EARNINGS'])}, "
          f"Group B n={len(events[events['group']=='B_no_spike_earnings_adjacent'])})")
    print(f"Pacing: {BASE_PAUSE_S}s between calls, up to {MAX_ATTEMPTS} attempts with escalating backoff on 429.")
    print(f"Estimated minimum runtime: {len(events) * BASE_PAUSE_S / 3600:.1f} hours (more if 429s require backoff).\n")

    already_done = load_already_done()
    if already_done:
        print(f"Resuming: {len(already_done)} events already in {OUT_PATH}, will be skipped.\n")

    n_new, n_skipped, n_failed = 0, 0, 0
    for i, ev in events.reset_index(drop=True).iterrows():
        ticker, anchor, group = ev["ticker"], ev["anchor"], ev["group"]
        key = (ticker, str(anchor), group)
        if key in already_done:
            n_skipped += 1
            continue

        start = anchor - timedelta(days=PRE_WINDOW_DAYS)
        end = anchor - timedelta(days=1)
        count, status = fetch_gdelt_article_count(ticker, start, end)

        row = {
            "ticker": ticker, "anchor": anchor.date().isoformat(), "group": group,
            "pre_window_start": start.date().isoformat(), "pre_window_end": end.date().isoformat(),
            "gdelt_article_count": count, "status": status,
        }
        append_row(row)
        already_done.add(key)

        if status == "ok":
            n_new += 1
            print(f"[{i+1}/{len(events)}] {ticker} {group} {start.date()}..{end.date()}: {count} articles")
        else:
            n_failed += 1
            print(f"[{i+1}/{len(events)}] {ticker} {group} {start.date()}..{end.date()}: FAILED ({status})")

        time.sleep(BASE_PAUSE_S)

    print(f"\nDone this run. New: {n_new}   Skipped (already done): {n_skipped}   Failed: {n_failed}")

    result = pd.read_csv(OUT_PATH)
    result = result[result["gdelt_article_count"].notna()]
    a_counts = result[result["group"] == "A_STRONG_EARNINGS"]["gdelt_article_count"].to_numpy(dtype=float)
    b_counts = result[result["group"] == "B_no_spike_earnings_adjacent"]["gdelt_article_count"].to_numpy(dtype=float)

    print(f"\n=== PRE-SPIKE (7 days before anchor) GDELT NEWS VOLUME COMPARISON ===")
    print(f"Group A (STRONG_EARNINGS): n={len(a_counts)}  mean={a_counts.mean():.1f}  median={np.median(a_counts):.1f}")
    print(f"Group B (no-spike, earnings-adjacent): n={len(b_counts)}  mean={b_counts.mean():.1f}  median={np.median(b_counts):.1f}")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p, a_mean, b_mean = two_sample_permutation_test(a_counts, b_counts, N_PERMUTATIONS, rng)
    if diff is not None:
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Diff (A - B): {diff:+.1f} articles   two-sided p={p:.4f} ({sig})")
        if p < 0.05:
            print("=> News volume IS a real leading indicator (in-sample, this dataset).")
        else:
            print("=> News volume is decorrelated from GST spikes — monitor stays exploratory.")
    else:
        print("Not enough data in one or both groups yet to run the permutation test.")

    print(f"\nWrote/updated: {OUT_PATH}")


if __name__ == "__main__":
    main()
