#!/usr/bin/env python3
# Wikipedia EDIT FREQUENCY Pre-Spike Test — same event universe and same
# ticker->article mapping as GST_Wikipedia_PreSpike_PageviewTest.py, but
# counts EDITS to the article in the 7 days before the spike week instead
# of pageviews. Hypothesis: edit frequency may be less contaminated by raw
# company size/fame than pageviews were (that test's raw p=0.0000 collapsed
# to p=0.0616, wrong-signed, once within-ticker normalized — a mega-cap
# has huge baseline pageviews regardless of what's happening that week, but
# it doesn't necessarily get MORE Wikipedia edits than a small-cap just for
# being famous — edits require someone to actually update the page with
# new information, which is arguably closer to "something changed").
#
# Universe: identical to the pageviews test — Group A = STRONG_EARNINGS
# (z>=4, near_earnings=True), n=209, Group B = non-spike earnings-adjacent,
# n=110, both from Earnings-Adjacent Spike vs No-Spike Test/*.csv.
# TICKER_TO_ARTICLE mapping is reused verbatim from the pageviews test
# (already verified against Wikipedia's summary API, including the 3
# redirect corrections and the COHR point-in-time check) — not re-derived.
#
# *** ANALYSIS METHODOLOGY — LEARNED FROM THE PAGEVIEWS TEST ***
# The pageviews test's raw pooled comparison (all 51 tickers) was a
# composition artifact: Group A is stacked with mega-caps that have huge
# baseline Wikipedia traffic regardless of week, Group B is stacked with
# low-follower tickers that rarely spike. This script goes STRAIGHT to the
# corrected methodology rather than reporting a raw number first: restrict
# to tickers present in BOTH groups, normalize each event's edit count to
# that ticker's own mean edit count (within this subset), THEN permutation-
# test the normalized values. The raw (unnormalized, all-51-ticker) number
# is still saved to the output CSV for transparency, but is not the
# headline result.
#
# Edit counts pulled via the MediaWiki Action API (action=query&prop=
# revisions), NOT the pageviews REST API used previously — a different
# endpoint entirely. Tested clean with no rate-limiting in this environment.
#
# Output: Live Signal Engine/Wikipedia_PreSpike_EditFrequencyTest.csv (append-only, resumable)
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
OUT_PATH = OUT_DIR / "Wikipedia_PreSpike_EditFrequencyTest.csv"

# Reused verbatim from GST_Wikipedia_PreSpike_PageviewTest.py — already verified.
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
RVLIMIT = 500
BASE_PAUSE_S = 1.0
MAX_ATTEMPTS = 4
BACKOFF_S = [5, 15, 30, 60]
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "gst-research-monitor/0.1 (contact: hakurati11@gmail.com)"})


def fetch_edit_count(article: str, start, end) -> tuple[int | None, str]:
    rvstart = end.strftime("%Y-%m-%dT23:59:59Z")
    rvend = start.strftime("%Y-%m-%dT00:00:00Z")
    params = {
        "action": "query", "prop": "revisions", "titles": article,
        "rvlimit": RVLIMIT, "rvprop": "timestamp", "format": "json",
        "rvstart": rvstart, "rvend": rvend, "rvdir": "older",
    }
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = SESSION.get("https://en.wikipedia.org/w/api.php", params=params, timeout=20)
        except Exception as e:
            return None, f"error: {e}"

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

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None, "no_page_found"
        page = next(iter(pages.values()))
        if "missing" in page:
            return None, "article_missing"
        revs = page.get("revisions", [])
        capped = data.get("continue") is not None
        return len(revs), ("ok_capped_at_limit" if capped else "ok")

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
        n_edits, status = fetch_edit_count(article, start, end)

        row = {
            "ticker": ticker, "article": article, "anchor": anchor.date().isoformat(), "group": group,
            "pre_window_start": start.date().isoformat(), "pre_window_end": end.date().isoformat(),
            "pre_window_edits": n_edits, "status": status,
        }
        append_row(row)
        already_done.add(key)

        if n_edits is not None:
            n_new += 1
            print(f"[{i+1}/{len(events)}] {ticker} ({article}) {group} {start.date()}..{end.date()}: {n_edits} edits")
        else:
            n_failed += 1
            print(f"[{i+1}/{len(events)}] {ticker} ({article}) {group} {start.date()}..{end.date()}: FAILED ({status})")

        time.sleep(BASE_PAUSE_S)

    print(f"\nDone this run. New: {n_new}   Skipped (already done): {n_skipped}   Failed: {n_failed}")

    result = pd.read_csv(OUT_PATH)
    result = result[result["pre_window_edits"].notna()].copy()

    a_raw_all = result[result["group"] == "A_STRONG_EARNINGS"]["pre_window_edits"].to_numpy(dtype=float)
    b_raw_all = result[result["group"] == "B_no_spike_earnings_adjacent"]["pre_window_edits"].to_numpy(dtype=float)
    print(f"\n=== RAW (all tickers, NOT the headline result — see composition caveat) ===")
    print(f"Group A: n={len(a_raw_all)} mean={a_raw_all.mean():.2f}   Group B: n={len(b_raw_all)} mean={b_raw_all.mean():.2f}")

    counts = result.groupby(["ticker", "group"]).size().unstack(fill_value=0)
    shared_tickers = counts[(counts.get("A_STRONG_EARNINGS", 0) > 0) &
                             (counts.get("B_no_spike_earnings_adjacent", 0) > 0)].index
    shared = result[result["ticker"].isin(shared_tickers)].copy()

    ticker_means = shared.groupby("ticker")["pre_window_edits"].transform("mean")
    # Guard against tickers whose mean edit count is 0 (division undefined) — exclude, don't silently produce inf/NaN
    shared = shared[ticker_means > 0].copy()
    ticker_means = ticker_means[ticker_means > 0]
    shared["normalized"] = shared["pre_window_edits"] / ticker_means

    a_norm = shared[shared["group"] == "A_STRONG_EARNINGS"]["normalized"].to_numpy(dtype=float)
    b_norm = shared[shared["group"] == "B_no_spike_earnings_adjacent"]["normalized"].to_numpy(dtype=float)

    print(f"\n=== HEADLINE RESULT: within-ticker normalized, {len(shared_tickers)} tickers present in both groups ===")
    print(f"Group A (STRONG_EARNINGS): n={len(a_norm)}  normalized mean={a_norm.mean():.3f}x  median={np.median(a_norm):.3f}x")
    print(f"Group B (no-spike, earnings-adjacent): n={len(b_norm)}  normalized mean={b_norm.mean():.3f}x  median={np.median(b_norm):.3f}x")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p, a_mean, b_mean = two_sample_permutation_test(a_norm, b_norm, N_PERMUTATIONS, rng)
    if diff is not None:
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Diff (A - B): {diff:+.3f}x   two-sided p={p:.4f} ({sig})")
        if p < 0.05 and diff > 0:
            print("=> Edit frequency IS a real leading indicator (in-sample, within-ticker corrected).")
        else:
            print("=> Edit frequency is decorrelated from GST spikes (or wrong-signed) — monitor stays exploratory.")
    else:
        print("Not enough data to run the permutation test.")

    print("\nEXPLORATORY VALIDATION — not yet wired into the live signal engine or straddle logger.")
    print(f"Wrote/updated: {OUT_PATH}")


if __name__ == "__main__":
    main()
