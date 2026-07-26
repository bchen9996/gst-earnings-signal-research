#!/usr/bin/env python3
# WIKIPEDIA PAGEVIEWS PULL -- DATA PULL ONLY. No correlation, no
# hypothesis test, no significance claim. Computes a Wikipedia-pageview
# z-score for every event in the 152-event canonical population, using
# the EXACT SAME rolling-window z-score function this project already
# uses for GST (`compute_zscore_at_anchor`, imported directly from
# GST_FixedWindow_PerEvent_Canonical.py -- not reimplemented, same
# discipline as the H5 outcome pull reusing `cumulative_return` etc.).
#
# TICKER -> WIKIPEDIA ARTICLE MAPPING: verified against the live
# Wikipedia API before writing this script (MediaWiki `action=query`
# with `redirects=1`, checked for missing/disambiguation pages, then a
# second pass pulling each resolved title's short description to
# confirm it's actually the right company) -- not guessed. One real
# redirect was caught this way: "United Airlines Holdings" (the natural
# guess from the company's legal name) redirects to "United Airlines"
# (the actual article title) -- pulling the guessed title directly would
# have silently returned zero/garbage data, exactly the failure mode
# this verification step exists to catch.
#
# WHY ONE CONTINUOUS PULL PER TICKER, NOT ONE PER EVENT (unlike GST's
# own per-event-pull discipline in GST_FixedWindow_PerEvent_Canonical.py):
# GST's per-event pulls exist because Google Trends RESCALES its 0-100
# output to the peak within the queried window -- a single multi-year
# query lets a future peak distort every earlier week's value. Wikipedia
# pageview counts are raw, unscaled integers with no such rescaling, so
# there is no look-ahead contamination risk in pulling one continuous
# daily series per ticker and computing each event's trailing z-score
# from it. `compute_zscore_at_anchor`'s rolling calculation is itself
# point-in-time-safe regardless (row i's z-score only ever depends on
# rows before i, via `.shift(1)` before the rolling window) -- confirmed
# by reading that function's own source before relying on this design.
#
# Output: Live Signal Engine/Wikipedia_Pageviews_ZScore_PerEvent.csv,
# one row per canonical event, GST z-score and Wikipedia z-score side by
# side -- no comparison or correlation computed between them here.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import json
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "Wikipedia_Pageviews_ZScore_PerEvent.csv"

# Verified against the live Wikipedia API (action=query, redirects=1,
# checked for missing/disambiguation pages + description sanity check)
# immediately before writing this script -- see header note above.
TICKER_TO_WIKI_ARTICLE = {
    "AAPL": "Apple Inc.",
    "ABBV": "AbbVie",
    "ADBE": "Adobe Inc.",
    "AMZN": "Amazon (company)",
    "BKR": "Baker Hughes",
    "BRK-B": "Berkshire Hathaway",
    "COHR": "Coherent Corp.",
    "CTSH": "Cognizant",
    "DELL": "Dell Technologies",
    "DVN": "Devon Energy",
    "GME": "GameStop",
    "GOOGL": "Alphabet Inc.",
    "GPN": "Global Payments",
    "INTC": "Intel",
    "LDOS": "Leidos",
    "MSFT": "Microsoft",
    "NCLH": "Norwegian Cruise Line Holdings",
    "NFLX": "Netflix",
    "NKE": "Nike, Inc.",
    "NVDA": "Nvidia",
    "QCOM": "Qualcomm",
    "SBUX": "Starbucks",
    "STZ": "Constellation Brands",
    "SYK": "Stryker Corporation",
    "TSLA": "Tesla, Inc.",
    "TTWO": "Take-Two Interactive",
    "UAL": "United Airlines",  # redirect target, NOT "United Airlines Holdings" -- see header note
}

PULL_LOOKBACK_DAYS = base.PULL_LOOKBACK_DAYS  # 300, same convention as the GST pull
POST_EVENT_BUFFER_DAYS = base.POST_EVENT_BUFFER_DAYS  # 7
ROLLING_WINDOW = base.ROLLING_WINDOW  # 12 -- reused via compute_zscore_at_anchor, not redeclared logic
MIN_PERIODS = base.MIN_PERIODS  # 8

WIKI_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{article}/daily/{start}/{end}"


CHUNK_DAYS = 365   # see fetch_daily_pageviews() docstring for why chunking is needed at all


def _empty_daily_df() -> pd.DataFrame:
    # Explicit dtypes matter here: an untyped pd.DataFrame(columns=["date","views"])
    # has object dtype for "date", and concatenating that with a real chunk's
    # datetime64 "date" column silently downgrades the merged column to object
    # (this is what crashed to_weekly()'s .dt accessor on UAL after a bisection
    # branch gave up and its empty result got pd.concat'd with real data).
    return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "views": pd.Series(dtype="int64")})


def _fetch_chunk(article: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = WIKI_API.format(article=encoded, start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; GST project)"})
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            # Retry on 429 (genuine rate-limit) AND 404. The 404 case is NOT the usual
            # "page doesn't exist" meaning here -- empirically confirmed (GPN, NVDA) that
            # the SAME article, SAME full multi-year range 404s consistently across 5
            # retries even minutes apart, while narrower sub-windows of that exact range
            # return 200 with real data. This isn't transience; see the docstring below
            # -- retrying a couple of times here is just a cheap safety net, the real fix
            # is chunking the request range, not this retry.
            if e.code in (429, 404) and attempt < max_attempts:
                wait = 10 * attempt
                time.sleep(wait)
                continue
            return _empty_daily_df()
        except Exception:
            return _empty_daily_df()
    else:
        return _empty_daily_df()
    items = data.get("items", [])
    if not items:
        return _empty_daily_df()
    rows = [{"date": pd.to_datetime(it["timestamp"][:8], format="%Y%m%d"), "views": it["views"]} for it in items]
    return pd.DataFrame(rows)


MIN_BISECT_DAYS = 45   # below this, give up and report the sub-range as genuinely unavailable


def _fetch_with_bisection(article: str, start: pd.Timestamp, end: pd.Timestamp, depth: int = 0) -> pd.DataFrame:
    """If a range fails even after _fetch_chunk's own retries, split it in half and
    recurse, down to MIN_BISECT_DAYS. Empirically necessary, not precautionary:
    GPN ("Global Payments") and NVDA ("Nvidia") both 404'd consistently (5/5 retries,
    minutes apart) on their full multi-year range, while EVERY narrower sub-window
    tested -- including ones covering the exact same days that failed as part of the
    larger request -- returned 200 with real data. That pattern (small windows
    reliable, large ones intermittently not) pointed to a size/timeout-related
    server-side quirk rather than a fixed 'bad date range' or a genuinely missing
    article, so a fixed chunk size alone was not reliable (confirmed directly: a
    365-day chunk still failed for part of NVDA's range). Recursive bisection on
    failure handles this regardless of where the threshold actually sits, without
    needing to fully diagnose the server-side cause."""
    result = _fetch_chunk(article, start, end)
    if not result.empty:
        return result
    span_days = (end - start).days
    if span_days <= MIN_BISECT_DAYS:
        print(f"    giving up on {start.date()}..{end.date()} ({span_days}d) after bisection -- genuinely unavailable")
        return _empty_daily_df()
    mid = start + timedelta(days=span_days // 2)
    print(f"    {start.date()}..{end.date()} failed -- bisecting at {mid.date()}")
    left = _fetch_with_bisection(article, start, mid, depth + 1)
    right = _fetch_with_bisection(article, mid + timedelta(days=1), end, depth + 1)
    return pd.concat([left, right], ignore_index=True)


def fetch_daily_pageviews(article: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Fetches in ~365-day chunks, recursively bisecting any chunk that still fails
    after _fetch_chunk's own retries (see _fetch_with_bisection docstring for why
    a fixed chunk size alone is not reliable for every article in this ticker list)."""
    chunks = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        chunk = _fetch_with_bisection(article, cursor, chunk_end)
        if not chunk.empty:
            chunks.append(chunk)
        cursor = chunk_end + timedelta(days=1)
        if cursor < end:
            time.sleep(1.0)
    if not chunks:
        return _empty_daily_df()
    return pd.concat(chunks, ignore_index=True).drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Sunday-start weekly sums, matching this project's own documented
    Google Trends week convention (README: 'Google's weeks run Sunday->Saturday')."""
    if daily.empty:
        return pd.DataFrame(columns=["Week", "gst"])
    d = daily.copy()
    # days since the most recent Sunday (Mon=0..Sun=6 from .dayofweek; Sunday=6 -> 0 offset)
    offset = (d["date"].dt.dayofweek + 1) % 7
    d["week_start"] = d["date"] - pd.to_timedelta(offset, unit="D")
    weekly = d.groupby("week_start", as_index=False)["views"].sum()
    weekly = weekly.rename(columns={"week_start": "Week", "views": "gst"})  # "gst" column name reused verbatim
    return weekly.sort_values("Week").reset_index(drop=True)


def main():
    print("*** WIKIPEDIA PAGEVIEWS PULL -- DATA PULL ONLY, NO CORRELATION/TEST ***\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    pop = canon[(canon["qualifies_z5"] == True) & (canon["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Canonical population: n={len(pop)}, {pop['ticker'].nunique()} unique tickers\n")

    missing_mapping = sorted(set(pop["ticker"].unique()) - set(TICKER_TO_WIKI_ARTICLE.keys()))
    if missing_mapping:
        print(f"ERROR: no verified Wikipedia mapping for: {missing_mapping} -- stopping, not guessing.")
        sys.exit(1)

    weekly_cache: dict[str, pd.DataFrame] = {}
    rows = []

    for ticker in sorted(pop["ticker"].unique()):
        article = TICKER_TO_WIKI_ARTICLE[ticker]
        events = pop[pop["ticker"] == ticker]
        earliest_anchor = events["spike_week"].min()
        latest_anchor = events["spike_week"].max()
        pull_start = earliest_anchor - timedelta(days=PULL_LOOKBACK_DAYS)
        pull_end = latest_anchor + timedelta(days=POST_EVENT_BUFFER_DAYS)

        print(f"[{ticker}] article='{article}'  pulling {pull_start.date()} -> {pull_end.date()} "
              f"({len(events)} event(s))")
        daily = fetch_daily_pageviews(article, pull_start, pull_end)
        print(f"    {len(daily)} daily rows returned")
        weekly = to_weekly(daily)
        weekly_cache[ticker] = weekly
        time.sleep(3.0)  # widened from 0.5s after the first run hit 429s starting at ticker #11

        for r in events.itertuples(index=False):
            aligned_week, wiki_z, note = base.compute_zscore_at_anchor(weekly, r.spike_week)
            row = {
                "ticker": ticker, "spike_week": r.spike_week.date(),
                "wikipedia_article": article,
                "gst_zscore": r.fixed_window_zscore,
                "wiki_aligned_week": aligned_week.date() if aligned_week is not None else None,
                "wiki_value": (weekly.loc[weekly["Week"] == aligned_week, "gst"].iloc[0]
                               if aligned_week is not None and (weekly["Week"] == aligned_week).any() else None),
                "wiki_zscore": round(wiki_z, 4) if wiki_z is not None else None,
                "note": note,
            }
            rows.append(row)

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")

    n_resolved = result["wiki_zscore"].notna().sum()
    print(f"\nEvents with a resolved Wikipedia z-score: {n_resolved} / {len(result)}")
    if n_resolved < len(result):
        print("Unresolved events (see note column):")
        print(result.loc[result["wiki_zscore"].isna(), ["ticker", "spike_week", "note"]].to_string(index=False))

    print("\n*** DATA PULL ONLY. No correlation between gst_zscore and wiki_zscore")
    print("*** was computed here, and none should be inferred from this output alone. ***")


if __name__ == "__main__":
    main()
