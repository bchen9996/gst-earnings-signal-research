#!/usr/bin/env python3
# Social/News Pre-Spike Volume Monitor — EXPLORATORY, UNVALIDATED.
#
# *** THIS TOOL IS NOT VALIDATED. TREAT ITS OUTPUT AS OBSERVATION ONLY. ***
# Tests a hypothesis, doesn't confirm one: does elevated news/social
# discussion volume precede a GST z-score spike? Nobody has checked whether
# these ratios lead, lag, or have no relationship at all to GST spikes yet.
# Do not act on this output, do not wire it into the signal engine or the
# straddle logger, and do not treat "attention building" as a signal until
# a historical backtest (ratio-before-spike vs ratio-before-no-spike,
# permutation-tested, same discipline as every other finding in this
# project) has actually been run. That backtest has NOT been run.
#
# *** API ACCESS DISCLOSURE — READ BEFORE TRUSTING ANY NUMBER BELOW ***
# 1. NEWS: NewsAPI (newsapi.org) requires an API key. No NEWSAPI_KEY was
#    found in this environment (checked env vars and project files) — so
#    this script does NOT use NewsAPI. Fallback: Google News RSS
#    (news.google.com/rss/search), which needs no key and is free, but:
#      - it's a relevance-blended feed, not a guaranteed-complete article
#        list, and Google caps how many items it returns (~100) — for
#        high-volume tickers during earnings week this will UNDERCOUNT
#        true article volume, not overcount.
#      - pubDate parsing assumes RFC-822 format, which Google News RSS
#        uses consistently as of this writing.
#    Next-best free alternative if this feed ever breaks: Finnhub's free
#    company-news endpoint (needs a free API key, more generous limits
#    than NewsAPI's free tier) or StockNewsAPI's free tier.
# 2. REDDIT: Pushshift is NOT used — third-party Pushshift access has been
#    restricted since Reddit's 2023 API changes and is unreliable/dead for
#    unauthenticated use. Reddit's own public search.json endpoint was tried
#    first and returned HTTP 403 on every single ticker in this environment
#    (a hard block, not a data issue) — so this script uses apewisdom.io's
#    free public API instead (github.com/apewisdom, no auth required),
#    querying the r/wallstreetbets and r/stocks filters separately and
#    summing mentions across both, mirroring the original combined-subreddit
#    intent.
#    *** GRANULARITY MISMATCH — CONFIRMED VIA OFFICIAL DOCS, NOT GUESSED ***
#    Checked https://apewisdom.io/api/ directly: the only documented
#    endpoint is filter/{filter}/page/{pageNbr}, and the only fields are
#    "mentions" (a rolling ~24h count) and "mentions_24h_ago" (the same
#    count as of 24h earlier). There is no days= parameter or any other way
#    to request a 7-day window. So apewisdom's time granularity (24h vs
#    prior 24h) can NOT be made to match news_ratio's window (7d vs prior
#    7d) — they measure different things on different clocks.
#    Consequence: news and Reddit are NOT combined into a single flag.
#    There are two independent, separately-thresholded flags instead —
#    news_elevated and reddit_elevated — kept apart until a backtest shows
#    they're actually correlated (see top-of-file caveat). Reddit columns
#    are named accordingly (reddit_mentions_today / reddit_mentions_prior_24h
#    / reddit_ratio_24h) to keep the mismatched clock visible in the output.
#    Next-best free alternative if apewisdom ever breaks: Stocktwits'
#    public API (has its own mention-volume metric, different methodology
#    again).
#    *** ZERO-BASELINE FIX (Reddit only) ***
#    A 0-mentions-yesterday to 1-mention-today move produces a mathematically
#    infinite ratio that is pure noise at Reddit's low volume for smaller-cap
#    names (observed with STZ). Reddit now uses an absolute-count rule when
#    prior_24h == 0: elevated only if today's count >= REDDIT_MIN_ABSOLUTE_COUNT
#    (default 3) — a single stray mention no longer trips the flag. News
#    keeps the pure-ratio rule (its volumes are high enough that 0->1 moves
#    aren't the dominant noise source there).
#
# Output: Live Signal Engine/Social_News_PreSpike_Monitor_EXPLORATORY.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import sys, time
import xml.etree.ElementTree as ET
import urllib3
import requests
import pandas as pd

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = ["MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN"]

ATTENTION_RATIO_THRESHOLD = 1.5
REDDIT_MIN_ABSOLUTE_COUNT = 3   # zero-baseline rule: prior_24h==0 needs >= this many mentions today to count as elevated
APEWISDOM_FILTERS = ["wallstreetbets", "stocks"]
APEWISDOM_MAX_PAGES = 10   # bounded scan per filter; apewisdom sorts by mention rank, not searchable by ticker directly

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

NEWS_SESSION = requests.Session()
NEWS_SESSION.verify = False
NEWS_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

REDDIT_SESSION = requests.Session()
REDDIT_SESSION.verify = False
REDDIT_SESSION.headers.update({"User-Agent": "gst-research-monitor/0.1 (contact: hakurati11@gmail.com)"})


def week_bucket_counts(dates: list[datetime], now: datetime) -> tuple[int, int]:
    this_week = sum(1 for d in dates if now - timedelta(days=7) <= d <= now)
    last_week = sum(1 for d in dates if now - timedelta(days=14) <= d < now - timedelta(days=7))
    return this_week, last_week


def compute_ratio(this_week: int, last_week: int) -> float | None:
    if last_week == 0:
        return None if this_week == 0 else float("inf")
    return this_week / last_week


def fetch_news_dates(ticker: str) -> tuple[list[datetime], str]:
    query = quote(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = NEWS_SESSION.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        return [], f"error: {e}"

    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        return [], f"parse_error: {e}"

    dates = []
    for item in root.iter("item"):
        pub = item.findtext("pubDate")
        if not pub:
            continue
        try:
            d = parsedate_to_datetime(pub)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            dates.append(d.astimezone(timezone.utc))
        except Exception:
            continue

    if not dates:
        return [], "ok_but_empty"
    return dates, "ok"


def fetch_apewisdom_mentions_for_sub(ticker: str, sub_filter: str) -> tuple[int, int, str]:
    """Scans apewisdom's ranked mention list for one subreddit filter, looking for `ticker`.
    Returns (mentions, mentions_24h_ago, status). A ticker absent from the ranked list
    (i.e. too few mentions to place) is treated as 0/0, not an error."""
    page = 1
    while page <= APEWISDOM_MAX_PAGES:
        url = f"https://apewisdom.io/api/v1.0/filter/{sub_filter}/page/{page}"
        try:
            resp = REDDIT_SESSION.get(url, timeout=20)
        except Exception as e:
            return 0, 0, f"error: {e}"
        if resp.status_code != 200:
            return 0, 0, f"blocked_or_error: HTTP {resp.status_code}"
        try:
            data = resp.json()
        except Exception as e:
            return 0, 0, f"parse_error: {e}"

        match = next((r for r in data.get("results", []) if r.get("ticker") == ticker), None)
        if match is not None:
            return int(match.get("mentions") or 0), int(match.get("mentions_24h_ago") or 0), "ok"

        total_pages = data.get("pages", page)
        if page >= total_pages:
            return 0, 0, "ok_not_ranked"   # present zero mentions, no API error
        page += 1
        time.sleep(0.3)
    return 0, 0, "ok_not_ranked"


def fetch_reddit_mentions(ticker: str) -> tuple[int, int, str]:
    """Sums apewisdom mentions across r/wallstreetbets + r/stocks (mirrors the original
    combined-subreddit intent). Returns (mentions_today, mentions_prior_24h, status)."""
    total_today, total_prior, statuses = 0, 0, []
    for sub in APEWISDOM_FILTERS:
        m, m24, status = fetch_apewisdom_mentions_for_sub(ticker, sub)
        total_today += m
        total_prior += m24
        statuses.append(f"{sub}:{status}")
        time.sleep(0.3)

    if any("error" in s or "blocked" in s for s in statuses):
        return total_today, total_prior, "; ".join(statuses)
    if total_today == 0 and total_prior == 0:
        return 0, 0, "ok_but_empty"
    return total_today, total_prior, "ok"


def main():
    now = datetime.now(timezone.utc)
    print("*** EXPLORATORY / UNVALIDATED TOOL — see script header before trusting any number ***")
    print(f"Social/news volume monitor run at {now.isoformat()}")
    print(f"Tickers: {', '.join(TICKERS)}\n")

    rows = []
    for i, ticker in enumerate(TICKERS, start=1):
        news_dates, news_status = fetch_news_dates(ticker)
        news_this, news_last = week_bucket_counts(news_dates, now)
        news_ratio = compute_ratio(news_this, news_last)

        time.sleep(1.0)

        reddit_today, reddit_prior24h, reddit_status = fetch_reddit_mentions(ticker)

        news_elevated = (news_ratio is not None and news_ratio == float("inf")) or \
                        (news_ratio is not None and news_ratio > ATTENTION_RATIO_THRESHOLD)

        # Reddit: zero-baseline uses an absolute-count rule instead of a ratio (0->1 is not "elevated").
        if reddit_prior24h == 0:
            reddit_ratio = None
            reddit_elevated = reddit_today >= REDDIT_MIN_ABSOLUTE_COUNT
        else:
            reddit_ratio = compute_ratio(reddit_today, reddit_prior24h)
            reddit_elevated = reddit_ratio > ATTENTION_RATIO_THRESHOLD

        notes = []
        if "error" in news_status or "blocked" in news_status:
            notes.append(f"NEWS ACCESS ISSUE: {news_status}")
        if news_status == "ok_but_empty":
            notes.append("news feed returned zero items — query may be too narrow or feed unavailable")
        if "error" in reddit_status or "blocked" in reddit_status:
            notes.append(f"REDDIT ACCESS ISSUE: {reddit_status}")
        if reddit_status == "ok_not_ranked" or reddit_status == "ok_but_empty":
            notes.append("ticker not in apewisdom's ranked mention list for wallstreetbets/stocks (too few mentions to rank)")
        if news_ratio == float("inf"):
            notes.append(f"news: 0 mentions prior week, {news_this} this week (ratio undefined/infinite)")
        if reddit_prior24h == 0:
            notes.append(f"reddit: 0 mentions prior 24h, {reddit_today} today — absolute-count rule applied "
                          f"(elevated only if today >= {REDDIT_MIN_ABSOLUTE_COUNT}), ratio not computed")

        rows.append({
            "ticker": ticker,
            "news_this_week": news_this,
            "news_last_week": news_last,
            "news_ratio": None if news_ratio in (None, float("inf")) else round(news_ratio, 3),
            "news_status": news_status,
            "news_elevated": bool(news_elevated),
            "reddit_mentions_today": reddit_today,
            "reddit_mentions_prior_24h": reddit_prior24h,
            "reddit_ratio_24h": None if reddit_ratio is None else round(reddit_ratio, 3),
            "reddit_status": reddit_status,
            "reddit_elevated": bool(reddit_elevated),
            "note": "; ".join(notes),
        })

        print(f"[{i}/{len(TICKERS)}] {ticker}: news={news_this}/{news_last} (7d/7d, {news_status}) "
              f"news_elevated={news_elevated}  |  "
              f"reddit={reddit_today}/{reddit_prior24h} (24h/24h, {reddit_status}) "
              f"reddit_elevated={reddit_elevated}"
              f"{'  [' + '; '.join(notes) + ']' if notes else ''}")

        time.sleep(0.5)

    result = pd.DataFrame(rows)
    out_path = OUT_DIR / "Social_News_PreSpike_Monitor_EXPLORATORY.csv"
    result.to_csv(out_path, index=False)

    print(f"\n=== EXPLORATORY SOCIAL/NEWS VOLUME SNAPSHOT (n={len(result)}) — NOT VALIDATED ===")
    print(result.to_string(index=False))

    n_access_issues = result["note"].str.contains("ACCESS ISSUE", na=False).sum()
    if n_access_issues:
        print(f"\n{n_access_issues} ticker(s) hit an API access issue — see 'note' column and script header "
              f"for fallback suggestions. These rows' ratios are NOT reliable.")

    n_news = result["news_elevated"].sum()
    n_reddit = result["reddit_elevated"].sum()
    n_both = (result["news_elevated"] & result["reddit_elevated"]).sum()
    print(f"\n{n_news}/{len(result)} ticker(s) flagged news_elevated=True (news ratio > {ATTENTION_RATIO_THRESHOLD}x, "
          f"7d vs prior 7d).")
    print(f"{n_reddit}/{len(result)} ticker(s) flagged reddit_elevated=True (ratio > {ATTENTION_RATIO_THRESHOLD}x when "
          f"prior_24h > 0, or today's count >= {REDDIT_MIN_ABSOLUTE_COUNT} when prior_24h == 0; 24h vs prior 24h).")
    print(f"{n_both}/{len(result)} ticker(s) flagged on BOTH — kept as two separate columns, not combined, "
          f"until a backtest shows they're actually correlated.")
    print("Reminder: neither flag has been validated against historical GST spikes. This is observation, not a signal.")
    print("This output is NOT connected to the live signal engine or the straddle logger.")

    print(f"\nWrote exploratory snapshot to: {out_path}")


if __name__ == "__main__":
    main()
