#!/usr/bin/env python3
# Wikipedia Pageviews Pre-Spike Test — same structure as
# GST_GDELT_PreSpike_NewsVolume_Test.py, different data source: does
# Wikipedia daily pageviews in the 7 days BEFORE a STRONG_EARNINGS GST
# spike differ from the 7 days before a non-spike earnings-adjacent week?
#
# Universe: Group A = STRONG_EARNINGS events, z>=4, near_earnings=True,
# n=209 — the FULL original Group A file (same explicit choice as the
# GDELT test: not filtered to the current live z>=5 threshold). Group B =
# non-spike earnings-adjacent weeks, n=110. Both loaded from
# Earnings-Adjacent Spike vs No-Spike Test/*.csv (already on disk).
#
# *** TICKER -> WIKIPEDIA ARTICLE MAPPING — VERIFIED, NOT GUESSED ***
# Every title below was checked against Wikipedia's page/summary API
# before use (canonical title, page type, redirect status). Three initial
# guesses were redirects and were corrected to their canonical title:
#   CCL  "Carnival Corporation & plc" -> "Carnival Corporation"
#   ERIE "Erie Indemnity" -> "Erie Insurance Group"
#   UAL  "United Airlines Holdings" -> "United Airlines"
# Two mappings are flagged as a defensible judgment call, not a data error:
#   GOOGL -> "Alphabet Inc." (the direct corporate/legal entity match,
#     chosen over "Google" the consumer brand/product page, which would
#     mix in search-engine-product interest unrelated to the stock).
#   ERIE  -> "Erie Insurance Group" (the ticker's legal issuer is "Erie
#     Indemnity" specifically, a public management subsidiary of the
#     larger private Erie Insurance Exchange group; Wikipedia's main
#     article is for the broader group, which is what "Erie Indemnity"
#     redirects to — pageviews here may reflect general insurance-brand/
#     customer interest more than investor-specific interest).
# COHR ("Coherent Corp.") was checked for a point-in-time entity-identity
# risk (II-VI Incorporated acquired the old Coherent, Inc. and renamed
# itself "Coherent Corp." in July 2022, keeping ticker COHR) — ALL 5 COHR
# events in this dataset are 2023-08 through 2025-11, safely after the
# rename, so this does not affect this run.
#
# *** RATE LIMITS — MUCH LIGHTER THAN GDELT ***
# Wikimedia's REST API has no comparable throttling in this environment
# (tested clean on first call) and its documented etiquette policy is far
# more permissive than GDELT's. This script still paces modestly (1s
# between calls) and retries with backoff for resilience, but a full
# 319-event run should take minutes, not hours — unlike the GDELT test.
#
# *** HUMAN TRAFFIC ONLY ***
# Queries agent=user (excludes spider/bot crawl traffic) rather than
# all-agents, since the intent is a human-attention proxy comparable to
# GST/Reddit/news volume, not raw server hit counts.
#
# Output: Live Signal Engine/Wikipedia_PreSpike_PageviewTest.csv (append-only, resumable)
# Label: EXPLORATORY VALIDATION — not yet wired into the live signal engine or straddle logger.

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
OUT_PATH = OUT_DIR / "Wikipedia_PreSpike_PageviewTest.csv"

TICKER_TO_ARTICLE = {
    "TSLA": "Tesla, Inc.", "NVDA": "Nvidia", "AAPL": "Apple Inc.", "MSFT": "Microsoft",
    "AMZN": "Amazon (company)", "GOOGL": "Alphabet Inc.", "NFLX": "Netflix", "ADBE": "Adobe Inc.",
    "NKE": "Nike, Inc.", "SBUX": "Starbucks", "INTC": "Intel", "TTWO": "Take-Two Interactive",
    "QCOM": "Qualcomm", "GME": "GameStop", "EBAY": "EBay",
    "ABBV": "AbbVie", "ADP": "ADP (company)", "ALB": "Albemarle Corporation", "ALLE": "Allegion",
    "AVB": "AvalonBay Communities", "BKR": "Baker Hughes", "BRK-B": "Berkshire Hathaway",
    "CCL": "Carnival Corporation", "COF": "Capital One", "COHR": "Coherent Corp.",
    "CTSH": "Cognizant", "CTVA": "Corteva", "DELL": "Dell Technologies", "DVN": "Devon Energy",
    "ERIE": "Erie Insurance Group", "GPC": "Genuine Parts Company", "GPN": "Global Payments",
    "JBL": "Jabil", "LDOS": "Leidos", "LNT": "Alliant Energy", "MCHP": "Microchip Technology",
    "MCK": "McKesson Corporation", "MDT": "Medtronic", "NCLH": "Norwegian Cruise Line Holdings",
    "PKG": "Packaging Corporation of America", "PLD": "Prologis", "PNW": "Pinnacle West Capital",
    "RCL": "Royal Caribbean Group", "REG": "Regency Centers", "ROP": "Roper Technologies",
    "RTX": "RTX Corporation", "STZ": "Constellation Brands", "SYF": "Synchrony Financial",
    "SYK": "Stryker Corporation", "UAL": "United Airlines", "XOM": "ExxonMobil",
}

PRE_WINDOW_DAYS = 7
BASE_PAUSE_S = 1.0
MAX_ATTEMPTS = 4
BACKOFF_S = [5, 15, 30, 60]
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "gst-research-monitor/0.1 (contact: hakurati11@gmail.com)"})


def fetch_pageview_sum(article: str, start, end) -> tuple[int | None, str]:
    title = article.replace(" ", "_")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           f"en.wikipedia/all-access/user/{title}/daily/"
           f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = SESSION.get(url, timeout=20)
        except Exception as e:
            return None, f"error: {e}"

        if r.status_code == 404:
            return 0, "ok_no_data"   # no pageview data for this article/date range (e.g. too early)
        if r.status_code == 429:
            pause = BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)]
            print(f"    [{article}] 429, attempt {attempt}/{MAX_ATTEMPTS} — sleeping {pause}s")
            time.sleep(pause)
            continue
        if r.status_code != 200:
            return None, f"http_{r.status_code}"
        try:
            data = r.json()
        except Exception:
            return None, "parse_error"
        items = data.get("items", [])
        total = sum(item.get("views", 0) for item in items)
        return total, "ok"

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

    events = pd.concat([a, b], ignore_index=True)
    unmapped = sorted(set(events["ticker"]) - set(TICKER_TO_ARTICLE))
    if unmapped:
        print(f"WARNING: no Wikipedia article mapping for: {unmapped} — their events will be excluded.")
        events = events[events["ticker"].isin(TICKER_TO_ARTICLE)]
    return events


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
    print("*** EXPLORATORY VALIDATION — not yet wired into the live signal engine or straddle logger. ***\n")

    events = load_events()
    print(f"Total events to check: {len(events)} (Group A n={len(events[events['group']=='A_STRONG_EARNINGS'])}, "
          f"Group B n={len(events[events['group']=='B_no_spike_earnings_adjacent'])})\n")

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

        article = TICKER_TO_ARTICLE[ticker]
        start = anchor - timedelta(days=PRE_WINDOW_DAYS)
        end = anchor - timedelta(days=1)
        total_views, status = fetch_pageview_sum(article, start, end)

        row = {
            "ticker": ticker, "article": article, "anchor": anchor.date().isoformat(), "group": group,
            "pre_window_start": start.date().isoformat(), "pre_window_end": end.date().isoformat(),
            "pre_window_pageviews": total_views, "status": status,
        }
        append_row(row)
        already_done.add(key)

        if status in ("ok", "ok_no_data"):
            n_new += 1
            print(f"[{i+1}/{len(events)}] {ticker} ({article}) {group} {start.date()}..{end.date()}: {total_views} views")
        else:
            n_failed += 1
            print(f"[{i+1}/{len(events)}] {ticker} ({article}) {group} {start.date()}..{end.date()}: FAILED ({status})")

        time.sleep(BASE_PAUSE_S)

    print(f"\nDone this run. New: {n_new}   Skipped (already done): {n_skipped}   Failed: {n_failed}")

    result = pd.read_csv(OUT_PATH)
    result = result[result["pre_window_pageviews"].notna()]
    a_views = result[result["group"] == "A_STRONG_EARNINGS"]["pre_window_pageviews"].to_numpy(dtype=float)
    b_views = result[result["group"] == "B_no_spike_earnings_adjacent"]["pre_window_pageviews"].to_numpy(dtype=float)

    print(f"\n=== PRE-SPIKE (7 days before anchor) WIKIPEDIA PAGEVIEW COMPARISON ===")
    print(f"Group A (STRONG_EARNINGS): n={len(a_views)}  mean={a_views.mean():.1f}  median={np.median(a_views):.1f}")
    print(f"Group B (no-spike, earnings-adjacent): n={len(b_views)}  mean={b_views.mean():.1f}  median={np.median(b_views):.1f}")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p, a_mean, b_mean = two_sample_permutation_test(a_views, b_views, N_PERMUTATIONS, rng)
    if diff is not None:
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Diff (A - B): {diff:+.1f} pageviews   two-sided p={p:.4f} ({sig})")
    else:
        print("Not enough data in one or both groups yet to run the permutation test.")

    print("\nEXPLORATORY VALIDATION — not yet wired into the live signal engine or straddle logger.")
    print(f"Wrote/updated: {OUT_PATH}")


if __name__ == "__main__":
    main()
