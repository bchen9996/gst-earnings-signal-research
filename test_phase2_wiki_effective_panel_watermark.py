#!/usr/bin/env python3
# Deterministic tests for the TWO-STAGE EFFECTIVE PANEL WATERMARK
# (2026-08-05 redesign; supersedes the separate-probe design of 9990c39).
#
# Background. The aggregate pageviews endpoint answers "did en.wikipedia.org
# publish day D site-wide?", never "did THIS article publish day D?". The
# first attempt at closing that gap measured availability with a separate
# fixed-14-day per-article probe. A read-only live diagnostic proved that
# design release-blocking before it ever ran a panel -- see Live Signal
# Engine/Phase2 Failure Evidence/
# 2026-08-05_EffectiveWatermark_Probe_Design_Failure/:
#
#   1. 24 unpaced requests hit Wikimedia's rate limiter at request 11.
#   2. Availability is REQUEST-SHAPE-DEPENDENT: the same date is present in
#      one range's response and absent from another's, for the same article,
#      seconds apart. So a probe using one request shape can never certify
#      what a differently-shaped retrieval request returns.
#
# The redesign deletes the probe. Availability is measured from the SAME
# anchor-month response production then reuses, and all Stage-1 requests pass
# through one shared global limiter.
#
# Coverage (required-test list in brackets):
#    1. no separate 14-day probe exists or is called                    [1]
#    2. request end == aggregate watermark, never wall-clock today      [2]
#    3. rollover: aggregate watermark in the prior calendar month       [3]
#    4. ADBE-style: aggregate D, response only through D-1 -> D-1       [4]
#    5. tickers ending D / D-1 / D-2 -> common D-2                      [5]
#    6. Stage-1 responses reused; no second anchor-month request        [6]
#    7. request-shape-dependent fixtures cannot cause disagreement      [7]
#    8. all 24 requests pass through ONE shared pacing mechanism        [8]
#    9. Retry-After honored                                            [9]
#   10. exhausted 429 fails closed                                     [10]
#   11. HTTP 404 fails closed                                          [11]
#   12. trailing missing dates allowed in measurement, removed by the
#       common watermark                                               [12]
#   13. internal gaps still fail                                       [13]
#   14. slicing never zero-fills or infers                             [14]
#   15. every finalized row carries the same effective watermark       [15]
#   16. ticker order does not change the result                        [16]
#   17. pageview magnitudes do not affect watermark selection          [17]
#   18. operational cache byte-identical after this file               [18]
#
# Run directly: python test_phase2_wiki_effective_panel_watermark.py

from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import os
import shutil
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_Wikipedia_Transport as wt
import GST_Phase2_DailyPanel as panel

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


AGG = date(2026, 8, 4)          # aggregate watermark
WALL_CLOCK_TODAY = date(2026, 8, 5)
MONTH_START = date(2026, 8, 1)
TICKER = "AAPL"

UNIVERSE = [f"T{i:02d}" for i in range(24)]
ARTICLES = {t: f"Article_{t}" for t in UNIVERSE}

_ORIGINAL_CACHE_PATH = wt.CACHE_PATH
_OPERATIONAL_CACHE = Path("Live Signal Engine") / "Phase2_Wikipedia_Cache.csv"


def _sha256(p: Path):
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _use_temp_cache():
    d = tempfile.mkdtemp(prefix="wiki_effwm2_")
    wt.CACHE_PATH = Path(d) / "test_cache.csv"
    return d


def _restore_cache_path(d):
    wt.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(d, ignore_errors=True)


def _rows(start: date, end: date, views=100, skip=()):
    out, c = [], start
    while c <= end:
        if c not in skip:
            out.append({"date": c.strftime("%Y%m%d"),
                        "pageviews": views(c) if callable(views) else views})
        c += timedelta(days=1)
    return out


def _fetch(latest_by_article, failures=None, views=None, skip_by_article=None,
           shape_dependent=None):
    """fetch_chunk_isolated-shaped stub. Serves month_start..min(end, latest).

    shape_dependent: {article: {(start, end): latest}} -- lets a fixture make
    an article answer DIFFERENTLY for different ranges, reproducing the exact
    pathology the live diagnostic found. Used by test 7.
    """
    calls = []

    def fn(article, start, end, timeout_s=None):
        calls.append({"article": article, "start": start, "end": end})
        if failures and article in failures:
            resp = dict(failures[article])
            if callable(resp.get("_seq")):
                resp = resp["_seq"](len([c for c in calls if c["article"] == article]))
            resp.setdefault("items", [])
            resp.setdefault("url", "http://mock")
            resp.setdefault("network_elapsed_s", 0.01)
            resp.setdefault("retry_after", None)
            return resp
        latest = latest_by_article.get(article)
        if shape_dependent and article in shape_dependent:
            latest = shape_dependent[article].get((start, end), latest)
        items = []
        if latest is not None:
            v = (views or {}).get(article, 100)
            items = _rows(start, min(end, latest), views=v,
                          skip=(skip_by_article or {}).get(article, ()))
        return {"status": "ok", "http_status": 200, "items": items, "url": "http://mock",
                "network_elapsed_s": 0.01, "retry_after": None, "terminated": False}

    fn.calls = calls
    return fn


class _FakeClock:
    """Deterministic monotonic clock + sleep recorder for limiter tests."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def _limiter(interval=wt.AVAILABILITY_MIN_REQUEST_INTERVAL_S):
    c = _FakeClock()
    lim = wt.SharedRequestLimiter(min_interval_s=interval, sleep_fn=c.sleep, clock_fn=c.clock)
    return lim, c


def _agg(d=AGG, status="ok"):
    return {"status": status, "watermark_date": d, "lag_days": 1,
            "retrieved_at_utc": "2026-08-05T02:00:00+00:00",
            "source_url": "https://example.org/agg", "http_status": 200}


# === 1. The separate 14-day probe is gone ===
def test_1_no_separate_probe():
    check("1. measure_article_latest_available_date() no longer exists",
          not hasattr(wt, "measure_article_latest_available_date"))
    check("1. PER_ARTICLE_PROBE_WINDOW_DAYS no longer exists",
          not hasattr(wt, "PER_ARTICLE_PROBE_WINDOW_DAYS"))
    src = Path("GST_Phase2_Wikipedia_Transport.py").read_text(encoding="utf-8")
    panel_src = Path("GST_Phase2_DailyPanel.py").read_text(encoding="utf-8")
    check("1. no reference to the removed probe anywhere in production source",
          "measure_article_latest_available_date" not in src
          and "measure_article_latest_available_date" not in panel_src)

    # Exactly ONE request per ticker, and it is the anchor-month range.
    fn = _fetch({a: AGG for a in ARTICLES.values()})
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("1. exactly one request per ticker", len(fn.calls) == 24, len(fn.calls))
    check("1. every request is the anchor-month range (no 14-day window)",
          all(c["start"] == MONTH_START and c["end"] == AGG for c in fn.calls),
          {(c["start"], c["end"]) for c in fn.calls})
    check("1. resolves ok", res["status"] == "ok", res.get("failure_reason"))


# === 2. Request end == aggregate watermark, never wall-clock today ===
def test_2_request_end_is_aggregate_watermark():
    fn = _fetch({a: AGG for a in ARTICLES.values()})
    lim, _ = _limiter()
    wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    ends = {c["end"] for c in fn.calls}
    check("2. every Stage-1 request ends exactly at the aggregate watermark", ends == {AGG}, ends)
    check("2. no request ends at wall-clock today", WALL_CLOCK_TODAY not in ends, ends)
    check("2. no request ends after the aggregate watermark",
          all(e <= AGG for e in ends), ends)

    # And through the panel: process_ticker's horizon.
    cap = []
    restore = _install_stubs(cap)
    try:
        panel.process_ticker(None, TICKER, datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                             wiki_remaining_budget_s=100.0, watermark_info=_agg(),
                             effective_info=_eff_info(AGG))
    finally:
        restore()
    check("2. panel request horizon == aggregate watermark, not wall-clock today",
          cap and cap[0]["end"] == AGG, cap[0]["end"] if cap else None)


# === 3. Rollover: the aggregate watermark is in the prior calendar month ===
def test_3_rollover_prior_month():
    agg = date(2026, 7, 31)      # wall clock would be 2026-08-01/02
    fn = _fetch({a: agg for a in ARTICLES.values()})
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(agg), fetch_fn=fn, limiter=lim)
    check("3. anchor month is the watermark's month (July), not the wall-clock month",
          res["anchor_month_start"] == date(2026, 7, 1), res["anchor_month_start"])
    check("3. every request is 2026-07-01..2026-07-31",
          all(c["start"] == date(2026, 7, 1) and c["end"] == agg for c in fn.calls))
    check("3. effective watermark is 2026-07-31",
          res["effective_panel_watermark_date"] == agg, res["effective_panel_watermark_date"])
    check("3. resolves ok across the rollover", res["status"] == "ok", res.get("failure_reason"))

    check("3. anchor_month_start() maps any day to its month's first day",
          wt.anchor_month_start(date(2026, 2, 28)) == date(2026, 2, 1)
          and wt.anchor_month_start(date(2026, 1, 1)) == date(2026, 1, 1))


# === 4. ADBE-style: aggregate says D, the response only reaches D-1 ===
def test_4_adbe_style_response_trails_aggregate():
    lagger = UNIVERSE[3]
    latest = {ARTICLES[t]: (AGG - timedelta(days=1) if t == lagger else AGG) for t in UNIVERSE}
    fn = _fetch(latest)
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("4. a response trailing the aggregate is NOT an error", res["status"] == "ok",
          res.get("failure_reason"))
    check("4. effective watermark becomes D-1", res["effective_panel_watermark_date"] == AGG - timedelta(days=1),
          res["effective_panel_watermark_date"])
    check("4. the trailing ticker is the binding one", res["binding_tickers"] == [lagger],
          res["binding_tickers"])
    check("4. aggregate_vs_panel_lag_days == 1", res["aggregate_vs_panel_lag_days"] == 1)
    check("4. the aggregate watermark is still recorded", res["aggregate_watermark_date"] == AGG)
    check("4. every reused response now ends exactly at D-1",
          all(rows[-1]["date"] == (AGG - timedelta(days=1)).strftime("%Y%m%d")
              for rows in res["anchor_month_rows"].values()))


# === 5. Tickers ending D, D-1, D-2 -> common D-2 ===
def test_5_mixed_endings_common_minimum():
    latest = {}
    for i, t in enumerate(UNIVERSE):
        latest[ARTICLES[t]] = AGG - timedelta(days=(0 if i < 8 else 1 if i < 16 else 2))
    fn = _fetch(latest)
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("5. effective watermark is the minimum, D-2",
          res["effective_panel_watermark_date"] == AGG - timedelta(days=2),
          res["effective_panel_watermark_date"])
    check("5. binding set is exactly the 8 D-2 tickers",
          set(res["binding_tickers"]) == set(UNIVERSE[16:]), res["binding_tickers"])
    check("5. all 24 sliced responses end at D-2",
          {rows[-1]["date"] for rows in res["anchor_month_rows"].values()}
          == {(AGG - timedelta(days=2)).strftime("%Y%m%d")})
    check("5. aggregate_vs_panel_lag_days == 2", res["aggregate_vs_panel_lag_days"] == 2)


# === 6. Stage-1 responses reused; no second anchor-month request ===
def test_6_responses_reused_no_second_request():
    fn = _fetch({a: AGG for a in ARTICLES.values()})
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("6. exactly 24 requests total for 24 tickers (no second sweep)",
          len(fn.calls) == 24, len(fn.calls))
    check("6. sliced rows are carried for every ticker",
          len(res["anchor_month_rows"]) == 24, len(res["anchor_month_rows"]))
    check("6. reuse flag reports no second anchor-month request",
          res["second_anchor_month_request_issued"] is False)

    # And the transport consumes them without a network call.
    fetch_calls = []

    def never(article, start, end, timeout_s=None):
        fetch_calls.append((article, start, end))
        return {"status": "http_error", "http_status": 500, "items": [], "url": "x",
                "network_elapsed_s": 0.0, "retry_after": None}

    t0 = UNIVERSE[0]
    out = wt.get_ticker_wikipedia_daily(
        t0, ARTICLES[t0], MONTH_START, AGG, AGG,
        cache_df=pd.DataFrame(columns=wt.CACHE_COLUMNS), fetch_fn=never,
        prefetched_chunk_rows={(MONTH_START, AGG): res["anchor_month_rows"][t0]})
    check("6. the anchor-month chunk was satisfied with ZERO network calls",
          len(fetch_calls) == 0, fetch_calls)
    check("6. it is recorded with source=anchor_month_stage1",
          [c["source"] for c in out["chunk_results"]] == ["anchor_month_stage1"],
          out["chunk_results"])
    check("6. no chunk failed", out["failed_chunks"] == [], out["failed_chunks"])
    check("6. the reused rows became the daily rows",
          len(out["daily_rows"]) == len(res["anchor_month_rows"][t0]))
    check("6. reuse wrote nothing to the cache (cache file still absent)",
          not wt.CACHE_PATH.exists(), str(wt.CACHE_PATH))


# === 7. Request-shape-dependent fixtures cannot cause probe/retrieval disagreement ===
def test_7_shape_dependence_cannot_split_measurement_from_retrieval():
    # Reproduce the live pathology: this article answers D for a 14-day
    # window but only D-1 for the anchor-month range. Under the OLD design
    # the probe would have published D and retrieval would then have failed.
    tricky = UNIVERSE[5]
    art = ARTICLES[tricky]
    probe_range = (AGG - timedelta(days=13), WALL_CLOCK_TODAY)
    fn = _fetch({a: AGG for a in ARTICLES.values()},
                shape_dependent={art: {(MONTH_START, AGG): AGG - timedelta(days=1),
                                       probe_range: AGG}})
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)

    check("7. only the anchor-month range was ever requested",
          {(c["start"], c["end"]) for c in fn.calls} == {(MONTH_START, AGG)},
          {(c["start"], c["end"]) for c in fn.calls})
    check("7. the watermark follows the ANCHOR-MONTH answer (D-1), not the 14-day one (D)",
          res["effective_panel_watermark_date"] == AGG - timedelta(days=1),
          res["effective_panel_watermark_date"])
    check("7. the shape-dependent ticker binds", res["binding_tickers"] == [tricky],
          res["binding_tickers"])
    # The decisive property: what was measured IS what is reused, so the two
    # cannot disagree by construction.
    reused_last = {t: rows[-1]["date"] for t, rows in res["anchor_month_rows"].items()}
    check("7. every reused response ends exactly at the measured effective watermark",
          set(reused_last.values()) == {(AGG - timedelta(days=1)).strftime("%Y%m%d")},
          set(reused_last.values()))
    check("7. measurement and retrieval are the same observation (no second request to disagree with)",
          len(fn.calls) == 24)


# === 8. One shared pacing mechanism for all 24 requests ===
def test_8_single_shared_limiter():
    fn = _fetch({a: AGG for a in ARTICLES.values()})
    lim, clock = _limiter(interval=3.5)
    wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("8. the limiter counted all 24 requests", lim.request_count == 24, lim.request_count)
    check("8. 23 inter-request waits occurred (first is free)",
          len([s for s in clock.sleeps if s > 0]) == 23, clock.sleeps[:5])
    check("8. every enforced wait is the configured minimum interval",
          all(abs(s - 3.5) < 1e-9 for s in clock.sleeps if s > 0), set(clock.sleeps))
    check("8. total elapsed >= 23 * interval (rate genuinely bounded)",
          clock.t >= 23 * 3.5 - 1e-9, clock.t)
    check("8. a pacing record exists per request", len(lim.waits) == 24, len(lim.waits))
    check("8. pacing records carry request number and wait, and no payload data",
          all(set(w) == {"request_number", "waited_s", "reason"} for w in lim.waits))

    # A second, independent limiter would NOT bound the combined rate --
    # this asserts the production path passes one instance through.
    import inspect
    src = inspect.getsource(wt.retrieve_anchor_month_availability)
    check("8. Stage 1 acquires from the limiter it was given (single instance)",
          "limiter.acquire(" in src and "limiter = limiter or SharedRequestLimiter()" in src)


# === 9. Retry-After is honored ===
def test_9_retry_after_honored():
    throttled = UNIVERSE[2]
    art = ARTICLES[throttled]
    state = {"n": 0}

    def fn(article, start, end, timeout_s=None):
        if article == art:
            state["n"] += 1
            if state["n"] == 1:
                return {"status": "http_error", "http_status": 429, "retry_after": 17,
                        "items": [], "url": "x", "network_elapsed_s": 0.01}
        return {"status": "ok", "http_status": 200,
                "items": _rows(start, min(end, AGG)), "url": "x",
                "network_elapsed_s": 0.01, "retry_after": None}

    lim, clock = _limiter(interval=3.5)
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("9. the 429 ticker was retried and then succeeded", res["status"] == "ok",
          res.get("failure_reason"))
    check("9. it took exactly 2 attempts",
          [r["attempts"] for r in res["stage1_results"] if r["ticker"] == throttled] == [2],
          [r["attempts"] for r in res["stage1_results"] if r["ticker"] == throttled])
    check("9. a wait of the server-specified 17s was actually slept",
          any(abs(s - 17.0) < 1e-6 for s in clock.sleeps), sorted(set(clock.sleeps)))
    check("9. the limiter issued 25 requests (24 + one retry)", lim.request_count == 25,
          lim.request_count)

    # Retry-After is capped, and applies to the SHARED gate.
    lim2, clock2 = _limiter(interval=1.0)
    waited = lim2.note_retry_after(10 ** 6)
    check("9. an absurd Retry-After is capped",
          waited == wt.AVAILABILITY_MAX_RETRY_AFTER_WAIT_S, waited)
    lim2.acquire()
    check("9. the cap pushes out the SHARED gate, not just one caller",
          any(abs(s - wt.AVAILABILITY_MAX_RETRY_AFTER_WAIT_S) < 1e-6 for s in clock2.sleeps),
          clock2.sleeps)
    check("9. a malformed Retry-After falls back to the cap rather than crashing",
          wt.SharedRequestLimiter().note_retry_after("not-a-number")
          == wt.AVAILABILITY_MAX_RETRY_AFTER_WAIT_S)


# === 10. Exhausted 429 fails closed ===
def test_10_exhausted_429_fails_closed():
    stuck = UNIVERSE[7]
    fn = _fetch({a: AGG for a in ARTICLES.values()},
                failures={ARTICLES[stuck]: {"status": "http_error", "http_status": 429,
                                            "retry_after": 5}})
    lim, _ = _limiter()
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
    check("10. panel fails closed", res["status"] == "failed_closed", res["status"])
    check("10. effective watermark is None -- never guessed",
          res["effective_panel_watermark_date"] is None)
    check("10. the aggregate watermark is NOT substituted",
          res["effective_panel_watermark_date"] != AGG)
    check("10. the throttled ticker is named",
          [u["ticker"] for u in res["unmeasured"]] == [stuck], res["unmeasured"])
    check("10. retries were bounded, not unlimited",
          [r["attempts"] for r in res["stage1_results"] if r["ticker"] == stuck]
          == [wt.AVAILABILITY_MAX_429_RETRIES + 1])
    check("10. no minimum was computed over the other 23",
          res["measured_count"] == 23 and res["effective_panel_watermark_date"] is None)


# === 11. HTTP 404 fails closed ===
def test_11_404_fails_closed():
    for label, failure in [("404", {"status": "http_error", "http_status": 404}),
                           ("empty 200", {"status": "ok", "http_status": 200, "items": []}),
                           ("timeout", {"status": "timeout", "http_status": None}),
                           ("500", {"status": "http_error", "http_status": 500})]:
        broken = UNIVERSE[1]
        fn = _fetch({a: AGG for a in ARTICLES.values()}, failures={ARTICLES[broken]: failure})
        lim, _ = _limiter()
        res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn, limiter=lim)
        check(f"11. {label} -> failed_closed", res["status"] == "failed_closed", res["status"])
        check(f"11. {label} -> no effective watermark",
              res["effective_panel_watermark_date"] is None)
        check(f"11. {label} -> the failing ticker is named",
              [u["ticker"] for u in res["unmeasured"]] == [broken], res["unmeasured"])

    no_map = dict(ARTICLES)
    no_map.pop(UNIVERSE[9])
    fn = _fetch({a: AGG for a in ARTICLES.values()})
    res = wt.resolve_effective_panel_watermark(UNIVERSE, no_map, _agg(), fetch_fn=fn,
                                                limiter=_limiter()[0])
    check("11. missing article mapping -> failed_closed with no_article_mapping",
          res["status"] == "failed_closed"
          and res["unmeasured"][0]["reason"] == "no_article_mapping", res["unmeasured"])

    res_noagg = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(None, "failed_closed"),
                                                      fetch_fn=fn, limiter=_limiter()[0])
    check("11. no aggregate watermark -> failed closed (Stage-1 bound undefined)",
          res_noagg["status"] == "failed_closed", res_noagg["status"])


# === 12. Trailing gaps allowed while measuring, removed by the common watermark ===
def test_12_trailing_allowed_then_removed():
    v = wt.validate_anchor_month_response("T", "A", MONTH_START, AGG,
                                          _rows(MONTH_START, AGG - timedelta(days=2)))
    check("12. a response stopping 2 days short of the aggregate is USABLE",
          v["usable"] is True, v)
    check("12. its latest_available_date is its own last observation",
          v["latest_available_date"] == AGG - timedelta(days=2), v)

    latest = {ARTICLES[t]: (AGG if t != UNIVERSE[0] else AGG - timedelta(days=2))
              for t in UNIVERSE}
    fn = _fetch(latest)
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn,
                                                limiter=_limiter()[0])
    ends = {rows[-1]["date"] for rows in res["anchor_month_rows"].values()}
    check("12. after slicing, no response retains a trailing date beyond the common watermark",
          ends == {(AGG - timedelta(days=2)).strftime("%Y%m%d")}, ends)
    check("12. and each is exactly contiguous from anchor_month_start",
          all(rows[0]["date"] == MONTH_START.strftime("%Y%m%d")
              and len(rows) == (AGG - timedelta(days=2) - MONTH_START).days + 1
              for rows in res["anchor_month_rows"].values()))


# === 13. Internal gaps still fail ===
def test_13_internal_gaps_still_fail():
    gapped = _rows(MONTH_START, AGG, skip=(date(2026, 8, 2),))
    v = wt.validate_anchor_month_response("T", "A", MONTH_START, AGG, gapped)
    check("13. an interior hole is rejected", v["usable"] is False, v)
    check("13. category is internal_gap", v["category"] == "internal_gap", v["category"])
    check("13. the missing date is named", "2026-08-02" in v["reason"], v["reason"])

    late = _rows(MONTH_START + timedelta(days=1), AGG)
    v2 = wt.validate_anchor_month_response("T", "A", MONTH_START, AGG, late)
    check("13. a response that does not start at anchor_month_start is rejected",
          v2["usable"] is False and v2["category"] == "does_not_start_at_month_start", v2)

    gap_ticker = UNIVERSE[4]
    fn = _fetch({a: AGG for a in ARTICLES.values()},
                skip_by_article={ARTICLES[gap_ticker]: (date(2026, 8, 2),)})
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn,
                                                limiter=_limiter()[0])
    check("13. one ticker with an interior gap fails the whole panel closed",
          res["status"] == "failed_closed", res["status"])
    check("13. lowering the watermark cannot rescue it -- it is never even computed",
          res["effective_panel_watermark_date"] is None)

    # The CTSH case, at the chunk validator: no watermark lowering heals it.
    cs, ce = date(2026, 7, 1), date(2026, 7, 31)
    ctsh = [r for r in _rows(cs, ce)
            if not (date(2026, 7, 8) <= datetime.strptime(r["date"], "%Y%m%d").date()
                    <= date(2026, 7, 14))]
    outcomes = [wt.validate_snapshot("CTSH", "Cognizant", cs, ce, ctsh, w)["valid"]
                for w in (date(2026, 7, 31), date(2026, 7, 25), date(2026, 7, 20), date(2026, 7, 15))]
    check("13. CTSH's interior July gap is rejected at every watermark above it",
          not any(outcomes), outcomes)


# === 14. Slicing never zero-fills or infers ===
def test_14_slicing_is_pure_filtering():
    rows = _rows(MONTH_START, AGG, views=lambda d: d.day * 7)
    sliced = wt.slice_rows_to_watermark(rows, AGG - timedelta(days=2))
    check("14. slicing only removes rows", len(sliced) == len(rows) - 2, len(sliced))
    check("14. surviving rows are byte-identical to their originals",
          sliced == rows[:len(sliced)], sliced[:2])
    check("14. no date beyond the watermark survives",
          all(datetime.strptime(r["date"], "%Y%m%d").date() <= AGG - timedelta(days=2)
              for r in sliced))
    check("14. no zero-filled row was introduced",
          all(r["pageviews"] != 0 for r in sliced))

    with_gap = wt.slice_rows_to_watermark(
        _rows(MONTH_START, AGG, skip=(date(2026, 8, 2),)), AGG)
    check("14. slicing does NOT fill a pre-existing interior hole",
          "20260802" not in {r["date"] for r in with_gap}, len(with_gap))
    check("14. slicing a series entirely after the watermark yields nothing (never invents)",
          wt.slice_rows_to_watermark(rows, MONTH_START - timedelta(days=1)) == [])


# === 15. Every finalized row carries the same effective watermark ===
def test_15_uniform_watermark_across_rows():
    eff = AGG - timedelta(days=1)
    tickers = ["AAA", "BBB", "CCC"]

    def row(t, effective=eff, anchor=eff):
        return {"ticker": t, "all_six_fields_clean": True, "earnings_status": "ok",
                "retrieval_timestamp_utc": "2026-08-05T00:00:00+00:00",
                "wiki_effective_panel_watermark_date": effective.isoformat(),
                "wiki_zscore_anchor_date": anchor.isoformat()}

    check("15. uniform rows pass",
          panel.is_run_complete([row(t) for t in tickers], "COMPLETE", tickers,
                                 watermark_status="ok", effective_watermark_status="ok",
                                 effective_watermark_date=eff) is True)
    check("15. one row with a different effective watermark fails",
          panel.is_run_complete([row("AAA"), row("BBB"), row("CCC", effective=AGG)],
                                 "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok",
                                 effective_watermark_date=eff) is False)
    check("15. one row anchored elsewhere fails",
          panel.is_run_complete([row("AAA"), row("BBB"), row("CCC", anchor=AGG)],
                                 "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok",
                                 effective_watermark_date=eff) is False)
    check("15. unresolved effective watermark fails even with perfect rows",
          panel.is_run_complete([row(t) for t in tickers], "COMPLETE", tickers,
                                 watermark_status="ok",
                                 effective_watermark_status="failed_closed",
                                 effective_watermark_date=eff) is False)

    # End-to-end through process_ticker: provenance fields are run-level.
    rows_out = []
    for tk in ("AAPL", "MSFT"):
        cap = []
        restore = _install_stubs(cap)
        try:
            r, _ = panel.process_ticker(None, tk, datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                                        wiki_remaining_budget_s=100.0, watermark_info=_agg(),
                                        effective_info=_eff_info(eff))
        finally:
            restore()
        rows_out.append(r)
    check("15. both rows carry the identical effective panel watermark",
          {r["wiki_effective_panel_watermark_date"] for r in rows_out} == {eff.isoformat()},
          {r["wiki_effective_panel_watermark_date"] for r in rows_out})
    check("15. both rows carry the aggregate watermark as provenance",
          {r["wiki_aggregate_watermark_date"] for r in rows_out} == {AGG.isoformat()})
    check("15. both rows record the redesigned method",
          {r["wiki_effective_watermark_method"] for r in rows_out}
          == {wt.EFFECTIVE_WATERMARK_METHOD})
    check("15. aggregate-vs-panel lag recorded identically",
          {r["wiki_aggregate_vs_panel_lag_days"] for r in rows_out} == {1})


# === 16. Ticker order does not change the result ===
def test_16_order_invariance():
    latest = {ARTICLES[t]: AGG - timedelta(days=(i % 3)) for i, t in enumerate(UNIVERSE)}
    orders = [list(UNIVERSE), list(reversed(UNIVERSE)),
              [UNIVERSE[i] for i in (7, 0, 23, 4, 15, 8, 1, 19, 3, 11, 22, 2,
                                     5, 20, 9, 13, 6, 17, 10, 21, 12, 16, 14, 18)]]
    out = [wt.resolve_effective_panel_watermark(o, ARTICLES, _agg(), fetch_fn=_fetch(latest),
                                                 limiter=_limiter()[0]) for o in orders]
    check("16. identical effective watermark across orders",
          len({r["effective_panel_watermark_date"] for r in out}) == 1,
          [r["effective_panel_watermark_date"] for r in out])
    check("16. identical binding set", len({tuple(r["binding_tickers"]) for r in out}) == 1)
    check("16. identical per-ticker measurements",
          len({tuple(sorted(r["per_ticker_latest"].items())) for r in out}) == 1)
    check("16. identical sliced row sets",
          len({tuple(sorted((t, len(v)) for t, v in r["anchor_month_rows"].items()))
               for r in out}) == 1)


# === 17. Pageview magnitudes do not affect watermark selection ===
def test_17_magnitude_invariance():
    latest = {ARTICLES[t]: AGG - timedelta(days=(i % 2)) for i, t in enumerate(UNIVERSE)}
    out = []
    for views in ({a: 1 for a in ARTICLES.values()},
                  {a: 10 ** 9 for a in ARTICLES.values()},
                  {a: (i * 977) % 100003 for i, a in enumerate(ARTICLES.values())},
                  {a: 0 for a in ARTICLES.values()}):
        out.append(wt.resolve_effective_panel_watermark(
            UNIVERSE, ARTICLES, _agg(), fetch_fn=_fetch(latest, views=views),
            limiter=_limiter()[0]))
    check("17. effective watermark identical across wildly different magnitudes",
          len({r["effective_panel_watermark_date"] for r in out}) == 1,
          [r["effective_panel_watermark_date"] for r in out])
    check("17. binding set identical too", len({tuple(r["binding_tickers"]) for r in out}) == 1)
    check("17. an all-zero-views panel measures the same dates",
          out[3]["effective_panel_watermark_date"] == out[0]["effective_panel_watermark_date"])

    bad = [{"date": (AGG - timedelta(days=1)).strftime("%Y%m%d"), "pageviews": 5},
           {"date": AGG.strftime("%Y%m%d"), "pageviews": "not-a-number"}]
    v = wt.validate_anchor_month_response("T", "A", AGG - timedelta(days=1), AGG, bad)
    check("17. a structurally invalid pageviews value rejects the response "
          "(shape check, not magnitude)",
          v["usable"] is False and v["category"] == "malformed", v)


# === 18. Operational cache untouched ===
def test_18_operational_cache_untouched(before_hash, before_size):
    after_hash = _sha256(_OPERATIONAL_CACHE)
    after_size = _OPERATIONAL_CACHE.stat().st_size if _OPERATIONAL_CACHE.exists() else None
    check("18. operational Phase2_Wikipedia_Cache.csv SHA-256 unchanged",
          after_hash == before_hash, f"{before_hash} -> {after_hash}")
    check("18. operational cache byte size unchanged", after_size == before_size,
          f"{before_size} -> {after_size}")
    check("18. wt.CACHE_PATH restored to the operational path",
          wt.CACHE_PATH == _ORIGINAL_CACHE_PATH, wt.CACHE_PATH)


# --- panel stubs -------------------------------------------------------------
class _FakeTicker:
    def __init__(self, ticker, session=None):
        self.ticker = ticker

    def history(self, period=None):
        return pd.DataFrame()


def _install_stubs(capture):
    orig = {
        "e": panel.fetch_days_to_next_earnings, "x": panel.get_nearest_post_earnings_expiry,
        "o": panel.get_option_snapshot, "g": panel.fetch_ticker_series_scoped_backoff,
        "y": panel.yf.Ticker, "l": panel.wiki_transport.load_cache,
        "d": panel.wiki_transport.get_ticker_wikipedia_daily,
    }
    panel.fetch_days_to_next_earnings = lambda t: 30
    panel.get_nearest_post_earnings_expiry = lambda tk, d: None
    panel.get_option_snapshot = lambda tk, e, p: {}
    panel.fetch_ticker_series_scoped_backoff = lambda pt, t: (
        pd.DataFrame(), {"status": "attempts_exhausted", "attempts": 0,
                         "rate_limit_events": 0, "budget_exhausted": False})
    panel.yf.Ticker = _FakeTicker
    panel.wiki_transport.load_cache = lambda: pd.DataFrame(columns=panel.wiki_transport.CACHE_COLUMNS)

    def fake(ticker, article, start, end, watermark, cache_df=None, remaining_budget_s=None,
             prefetched_chunk_rows=None):
        capture.append({"ticker": ticker, "start": start, "end": end, "watermark": watermark,
                        "prefetched_keys": sorted((prefetched_chunk_rows or {}).keys())})
        return {"chunk_results": [], "failed_chunks": [], "daily_rows": []}

    panel.wiki_transport.get_ticker_wikipedia_daily = fake

    def restore():
        panel.fetch_days_to_next_earnings = orig["e"]
        panel.get_nearest_post_earnings_expiry = orig["x"]
        panel.get_option_snapshot = orig["o"]
        panel.fetch_ticker_series_scoped_backoff = orig["g"]
        panel.yf.Ticker = orig["y"]
        panel.wiki_transport.load_cache = orig["l"]
        panel.wiki_transport.get_ticker_wikipedia_daily = orig["d"]

    return restore


def _eff_info(effective, aggregate=AGG, tickers=("AAPL", "MSFT")):
    return {"status": "ok", "effective_panel_watermark_date": effective,
            "method": wt.EFFECTIVE_WATERMARK_METHOD, "aggregate_watermark_date": aggregate,
            "aggregate_vs_panel_lag_days": (aggregate - effective).days,
            "per_ticker_latest": {t: effective for t in tickers},
            "stage1_results": [], "unmeasured": [], "measured_count": len(tickers),
            "expected_count": len(tickers), "binding_tickers": sorted(tickers),
            "anchor_month_rows": {}, "anchor_month_start": MONTH_START,
            "anchor_month_requested_end": aggregate, "request_count": len(tickers),
            "pacing_waits": [], "second_anchor_month_request_issued": False,
            "resolved_at_utc": "2026-08-05T02:00:00+00:00"}




# =============================================================================
# BOUNDED IDENTICAL-REQUEST RETRY ON HTTP 404 (2026-08-05)
#
# The 22/24 availability gate left GPN and TTWO failing on a single 404 against
# the exact anchor-month request -- transient CDN transport, not unavailable
# data (the set of 404-ing articles changes between runs, and CTSH/INTC/SYK,
# the three previously "unresolved" intervals, all returned clean 200s in the
# same gate). See Live Signal Engine/Phase2 Failure Evidence/
# 2026-08-05_AnchorMonth_AvailabilityGate_22of24/.
# =============================================================================

ONE = ["T00"]
ONE_ART = {"T00": "Article_T00"}


def _scripted(script):
    """fetch stub driven by a per-attempt script. Each entry is one of:
    'ok' | 'invalid' | 'timeout' | int status | (status, retry_after).
    Records the exact (article, start, end, timeout_s) of every call so tests
    can assert the request never varies between attempts."""
    calls = []

    def fn(a, start, end, timeout_s=None):
        calls.append({"article": a, "start": start, "end": end, "timeout_s": timeout_s})
        step = script[min(len(calls) - 1, len(script) - 1)]
        if step == "ok":
            return {"status": "ok", "http_status": 200, "items": _rows(start, min(end, AGG)),
                    "url": "http://mock/x", "network_elapsed_s": 0.01, "retry_after": None}
        if step == "invalid":   # HTTP 200 but structurally unusable (interior gap)
            return {"status": "ok", "http_status": 200,
                    "items": _rows(start, min(end, AGG), skip=(MONTH_START + timedelta(days=1),)),
                    "url": "http://mock/x", "network_elapsed_s": 0.01, "retry_after": None}
        if step == "timeout":
            return {"status": "timeout", "http_status": None, "items": [], "url": "http://mock/x",
                    "network_elapsed_s": None, "retry_after": None, "terminated": True}
        if isinstance(step, tuple):
            code, ra = step
            return {"status": "http_error", "http_status": code, "items": [],
                    "url": "http://mock/x", "network_elapsed_s": 0.01, "retry_after": ra}
        return {"status": "http_error", "http_status": step, "items": [],
                "url": "http://mock/x", "network_elapsed_s": 0.01, "retry_after": None}

    fn.calls = calls
    return fn


def _no_jitter(lo, hi):
    return 0.0


def _stage1(script, **kw):
    """Runs Stage 1 for a single ticker under a deterministic clock."""
    fn = _scripted(script)
    lim, clock = _limiter()
    res = wt.retrieve_anchor_month_availability(
        ONE, ONE_ART, AGG, fetch_fn=fn, limiter=lim,
        jitter_fn=kw.pop("jitter_fn", _no_jitter), **kw)
    return res, res["results"][0], fn, lim, clock


# === 19. 200 on attempt 1 -> exactly one request ===
def test_19_success_first_attempt():
    res, r, fn, lim, _ = _stage1(["ok"])
    check("19. exactly one request issued", len(fn.calls) == 1, len(fn.calls))
    check("19. attempt count is 1", r["anchor_month_attempt_count"] == 1, r)
    check("19. attempt statuses == ['200_ok']", r["anchor_month_attempt_statuses"] == ["200_ok"], r)
    check("19. no retry waits recorded", r["anchor_month_retry_wait_seconds"] == [], r)
    check("19. not flagged as recovered after a transient 404",
          r["anchor_month_recovered_after_transient_404"] is False, r)
    check("19. final http status 200", r["anchor_month_final_http_status"] == 200, r)
    check("19. usable", r["status"] == "ok" and res["usable_count"] == 1, r)


# === 20. 404 then 200 -> accepted on attempt 2 ===
def test_20_404_then_200():
    res, r, fn, lim, clock = _stage1([404, "ok"])
    check("20. exactly two requests", len(fn.calls) == 2, len(fn.calls))
    check("20. accepted on attempt 2", r["anchor_month_attempt_count"] == 2, r)
    check("20. statuses are ['404', '200_ok']",
          r["anchor_month_attempt_statuses"] == ["404", "200_ok"], r)
    check("20. one retry wait recorded, 20s + zero jitter",
          r["anchor_month_retry_wait_seconds"] == [20.0], r["anchor_month_retry_wait_seconds"])
    check("20. flagged as recovered after a transient 404",
          r["anchor_month_recovered_after_transient_404"] is True, r)
    check("20. the 20s wait was genuinely slept",
          any(abs(s - 20.0) < 1e-6 for s in clock.sleeps), clock.sleeps)
    check("20. measurement is usable", r["status"] == "ok" and res["usable_count"] == 1, r)
    check("20. final http status 200", r["anchor_month_final_http_status"] == 200, r)


# === 21. 404, 404, then 200 -> accepted on attempt 3 ===
def test_21_404_404_then_200():
    res, r, fn, lim, clock = _stage1([404, 404, "ok"])
    check("21. exactly three requests", len(fn.calls) == 3, len(fn.calls))
    check("21. accepted on attempt 3", r["anchor_month_attempt_count"] == 3, r)
    check("21. statuses are ['404','404','200_ok']",
          r["anchor_month_attempt_statuses"] == ["404", "404", "200_ok"], r)
    check("21. waits are the scheduled 20s then 40s",
          r["anchor_month_retry_wait_seconds"] == [20.0, 40.0],
          r["anchor_month_retry_wait_seconds"])
    check("21. both waits genuinely slept",
          any(abs(s - 20.0) < 1e-6 for s in clock.sleeps)
          and any(abs(s - 40.0) < 1e-6 for s in clock.sleeps), clock.sleeps)
    check("21. usable and flagged recovered",
          r["status"] == "ok" and r["anchor_month_recovered_after_transient_404"] is True, r)


# === 22. Three 404s -> failed closed ===
def test_22_three_404s_fail_closed():
    res, r, fn, _, _ = _stage1([404, 404, 404])
    check("22. exactly three requests -- never a fourth",
          len(fn.calls) == wt.ANCHOR_MONTH_MAX_ATTEMPTS, len(fn.calls))
    check("22. ticker is unusable", r["status"] == "unusable", r["status"])
    check("22. statuses are three 404s",
          r["anchor_month_attempt_statuses"] == ["404", "404", "404"], r)
    check("22. no latest date was invented", r["latest_available_date"] is None, r)
    check("22. Stage 1 reports the failure",
          res["usable_count"] == 0 and len(res["failures"]) == 1, res["failures"])
    check("22. the reason names the attempt count", "3 attempt(s)" in r["reason"], r["reason"])
    full = wt.resolve_effective_panel_watermark(ONE, ONE_ART, _agg(),
                                                 fetch_fn=_scripted([404, 404, 404]),
                                                 limiter=_limiter()[0], jitter_fn=_no_jitter)
    check("22. panel fails closed with no effective watermark",
          full["status"] == "failed_closed"
          and full["effective_panel_watermark_date"] is None, full["status"])
    check("22. the aggregate watermark is NOT substituted",
          full["effective_panel_watermark_date"] != AGG)


# === 23. 404 then malformed 200, then a valid 200 on the last allowed attempt ===
def test_23_404_then_malformed_then_valid():
    res, r, fn, _, _ = _stage1([404, "invalid", "ok"])
    check("23. all three attempts used", len(fn.calls) == 3, len(fn.calls))
    check("23. the malformed 200 did not end the sequence",
          r["anchor_month_attempt_statuses"] == ["404", "200_invalid:internal_gap", "200_ok"],
          r["anchor_month_attempt_statuses"])
    check("23. the later valid 200 is accepted", r["status"] == "ok", r)

    res2, r2, fn2, _, _ = _stage1([404, "invalid", "invalid"])
    check("23. 404 + two malformed 200s -> failed closed", r2["status"] == "unusable", r2["status"])
    check("23. the malformed response was never accepted as data",
          r2["latest_available_date"] is None, r2)
    check("23. reason names the structural category", "internal_gap" in r2["reason"], r2["reason"])

    res3, r3, fn3, _, _ = _stage1(["invalid", "ok"])
    check("23. a first-attempt malformed 200 is NOT retried (prior behaviour preserved)",
          len(fn3.calls) == 1 and r3["status"] == "unusable", (len(fn3.calls), r3["status"]))


# === 24. 400 / 401 / 403 are never retried; 5xx and timeout keep prior handling ===
def test_24_no_retry_on_client_errors():
    for code in (400, 401, 403):
        res, r, fn, _, _ = _stage1([code, "ok"])
        check(f"24. HTTP {code}: exactly one request, no retry", len(fn.calls) == 1, len(fn.calls))
        check(f"24. HTTP {code}: fails closed", r["status"] == "unusable", r["status"])
        check(f"24. HTTP {code}: recorded as the final status",
              r["anchor_month_final_http_status"] == code, r)
        check(f"24. HTTP {code}: no retry wait", r["anchor_month_retry_wait_seconds"] == [], r)

    for label, step in (("500", 500), ("timeout", "timeout")):
        res, r, fn, _, _ = _stage1([step, "ok"])
        check(f"24. {label}: prior bounded handling preserved -- one request, fails closed",
              len(fn.calls) == 1 and r["status"] == "unusable", (len(fn.calls), r["status"]))


# === 25. Same URL and boundaries on every attempt; no alternative shape ===
def test_25_identical_request_every_attempt():
    res, r, fn, _, _ = _stage1([404, 404, "ok"])
    shapes = {(c["article"], c["start"], c["end"]) for c in fn.calls}
    check("25. all three attempts used ONE identical (article, start, end)",
          len(shapes) == 1, shapes)
    check("25. the article title never varied",
          {c["article"] for c in fn.calls} == {"Article_T00"})
    check("25. the boundaries are exactly the anchor month through the aggregate watermark",
          shapes == {("Article_T00", MONTH_START, AGG)}, shapes)
    check("25. no attempt used a wider or narrower range (no alternative-range fallback)",
          all(c["start"] == MONTH_START and c["end"] == AGG for c in fn.calls))
    check("25. the timeout passed is identical on every attempt",
          len({c["timeout_s"] for c in fn.calls}) == 1, {c["timeout_s"] for c in fn.calls})
    import inspect
    src = inspect.getsource(wt.retrieve_anchor_month_availability)
    stripped = (src.replace("fetch_fn(article, month_start, requested_end, timeout_s)", "")
                   .replace("fetch_fn = fetch_fn or fetch_chunk_isolated", ""))
    check("25. Stage 1 has exactly ONE fetch call site, with a fixed argument tuple -- "
          "endpoint/access/agent/granularity cannot vary between attempts",
          src.count("fetch_fn(article, month_start, requested_end, timeout_s)") == 1
          and "fetch_fn(" not in stripped)


# === 26. First valid 200 stops further calls ===
def test_26_first_valid_200_wins():
    calls = []

    def fn(a, start, end, timeout_s=None):
        calls.append(1)
        latest = AGG - timedelta(days=1) if len(calls) == 1 else AGG
        return {"status": "ok", "http_status": 200, "items": _rows(start, latest),
                "url": "u", "network_elapsed_s": 0.01, "retry_after": None}

    lim, _ = _limiter()
    res = wt.retrieve_anchor_month_availability(ONE, ONE_ART, AGG, fetch_fn=fn, limiter=lim,
                                                 jitter_fn=_no_jitter)
    r = res["results"][0]
    check("26. only one request was made", len(calls) == 1, len(calls))
    check("26. the FIRST valid response's date is kept, not a fresher one",
          r["latest_available_date"] == AGG - timedelta(days=1), r["latest_available_date"])
    check("26. no second attempt was made to chase a fresher watermark",
          r["anchor_month_attempt_count"] == 1, r)


# === 27. Every attempt passes through the shared limiter ===
def test_27_retries_use_shared_limiter():
    res, r, fn, lim, clock = _stage1([404, 404, "ok"])
    check("27. the limiter counted all three attempts", lim.request_count == 3, lim.request_count)
    check("27. one pacing record per attempt", len(lim.waits) == 3, len(lim.waits))
    check("27. retry waits were enforced BY the limiter, not an ad-hoc sleep",
          [round(x) for x in clock.sleeps if x > 0] == [20, 40], clock.sleeps)
    check("27. the backoff SUPERSEDES the shared minimum interval rather than adding to it "
          "(the limiter gate is a max, so a 20s backoff already covers the 3.5s floor)",
          all(x >= wt.AVAILABILITY_MIN_REQUEST_INTERVAL_S for x in clock.sleeps if x > 0),
          clock.sleeps)
    check("27. total elapsed covers both backoffs (rate genuinely bounded across retries)",
          clock.t >= 60.0, clock.t)

    seen = []
    target = ARTICLES[UNIVERSE[0]]

    def fn24(a, start, end, timeout_s=None):
        seen.append(a)
        if a == target and len([x for x in seen if x == a]) == 1:
            return {"status": "http_error", "http_status": 404, "items": [], "url": "u",
                    "network_elapsed_s": 0.0, "retry_after": None}
        return {"status": "ok", "http_status": 200, "items": _rows(start, min(end, AGG)),
                "url": "u", "network_elapsed_s": 0.0, "retry_after": None}

    lim2, clock2 = _limiter()
    res2 = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, _agg(), fetch_fn=fn24,
                                                 limiter=lim2, jitter_fn=_no_jitter)
    check("27. 24 tickers + 1 retry = 25 limiter-gated requests",
          lim2.request_count == 25, lim2.request_count)
    check("27. the retry did not bypass the global rate",
          len(lim2.waits) == 25 and res2["status"] == "ok", res2["status"])


# === 28. Retry-After honored when it asks for longer; 429 unchanged ===
def test_28_retry_after_on_404():
    res, r, fn, _, clock = _stage1([(404, 55), "ok"])
    check("28. a 404 carrying a longer Retry-After overrides the 20s schedule",
          r["anchor_month_retry_wait_seconds"] == [55.0], r["anchor_month_retry_wait_seconds"])
    check("28. the 55s wait was genuinely slept",
          any(abs(s - 55.0) < 1e-6 for s in clock.sleeps), clock.sleeps)

    res2, r2, _, _, _ = _stage1([(404, 3), "ok"])
    check("28. a SHORTER Retry-After does not shrink the scheduled backoff",
          r2["anchor_month_retry_wait_seconds"] == [20.0], r2["anchor_month_retry_wait_seconds"])

    res3, r3, _, _, _ = _stage1([(404, 10 ** 6), "ok"])
    check("28. an absurd Retry-After is capped at the module bound",
          r3["anchor_month_retry_wait_seconds"] == [wt.AVAILABILITY_MAX_RETRY_AFTER_WAIT_S],
          r3["anchor_month_retry_wait_seconds"])

    res4, r4, fn4, _, clock4 = _stage1([(429, 12), "ok"])
    check("28. 429 still retried once via its own pre-existing path",
          len(fn4.calls) == 2 and r4["status"] == "ok", (len(fn4.calls), r4["status"]))
    check("28. 429 honored its Retry-After of 12s",
          any(abs(s - 12.0) < 1e-6 for s in clock4.sleeps), clock4.sleeps)
    res5, r5, fn5, _, _ = _stage1([429, 429, 429])
    check("28. 429 retries stay bounded at the pre-existing limit (2 attempts, not 3)",
          len(fn5.calls) == wt.AVAILABILITY_MAX_429_RETRIES + 1, len(fn5.calls))


# === 29. Total-run budget exhaustion stops retries ===
def test_29_budget_stops_retries():
    res, r, fn, _, _ = _stage1([404, "ok"], remaining_budget_s=5.0)
    check("29. the retry wait would exceed the budget, so no second attempt was made",
          len(fn.calls) == 1, len(fn.calls))
    check("29. the ticker fails closed rather than overrunning the budget",
          r["status"] == "unusable", r["status"])
    check("29. the budget stop is recorded in the attempt statuses",
          "budget_exhausted_no_further_attempt" in r["anchor_month_attempt_statuses"],
          r["anchor_month_attempt_statuses"])
    check("29. the reason names the budget", "budget" in r["reason"], r["reason"])
    check("29. no wait was recorded for the attempt that never happened",
          r["anchor_month_retry_wait_seconds"] == [], r)

    res2, r2, fn2, _, _ = _stage1([404, "ok"], remaining_budget_s=10_000.0)
    check("29. with ample budget the retry proceeds normally",
          len(fn2.calls) == 2 and r2["status"] == "ok", (len(fn2.calls), r2["status"]))

    res3, r3, fn3, _, _ = _stage1([404, 404, "ok"], remaining_budget_s=40.0)
    check("29. a budget allowing the first retry but not the second stops after two attempts",
          len(fn3.calls) == 2, len(fn3.calls))


# === 30. Deterministic jitter injection ===
def test_30_deterministic_jitter():
    for j in (0.0, 2.5, 5.0):
        res, r, _, _, _ = _stage1([404, "ok"], jitter_fn=lambda lo, hi, _j=j: _j)
        check(f"30. jitter {j}s is added to the 20s schedule",
              r["anchor_month_retry_wait_seconds"] == [20.0 + j],
              r["anchor_month_retry_wait_seconds"])
    seen = []

    def spy(lo, hi):
        seen.append((lo, hi))
        return 1.0

    _stage1([404, 404, "ok"], jitter_fn=spy)
    check("30. jitter is drawn from the bounded 0..ANCHOR_MONTH_404_JITTER_S range",
          seen == [(0.0, wt.ANCHOR_MONTH_404_JITTER_S)] * 2, seen)


# === 31. Provenance matches the actual attempt sequence ===
def test_31_provenance_matches_attempts():
    cases = [
        (["ok"], 1, ["200_ok"], [], False, 200),
        ([404, "ok"], 2, ["404", "200_ok"], [20.0], True, 200),
        ([404, 404, "ok"], 3, ["404", "404", "200_ok"], [20.0, 40.0], True, 200),
        ([404, 404, 404], 3, ["404", "404", "404"], [20.0, 40.0], False, 404),
    ]
    for script, n, statuses, waits, recovered, final in cases:
        _, r, fn, _, _ = _stage1(script)
        check(f"31. {script}: attempt_count matches the real request count",
              r["anchor_month_attempt_count"] == n == len(fn.calls),
              (r["anchor_month_attempt_count"], len(fn.calls)))
        check(f"31. {script}: attempt_statuses in order",
              r["anchor_month_attempt_statuses"] == statuses, r["anchor_month_attempt_statuses"])
        check(f"31. {script}: retry_wait_seconds matches the waits taken",
              r["anchor_month_retry_wait_seconds"] == waits, r["anchor_month_retry_wait_seconds"])
        check(f"31. {script}: recovered_after_transient_404 == {recovered}",
              r["anchor_month_recovered_after_transient_404"] is recovered, r)
        check(f"31. {script}: final_http_status == {final}",
              r["anchor_month_final_http_status"] == final, r)

    eff = _eff_info(AGG - timedelta(days=1))
    eff["stage1_results"] = [{"ticker": TICKER, "anchor_month_attempt_count": 2,
                              "anchor_month_attempt_statuses": ["404", "200_ok"],
                              "anchor_month_retry_wait_seconds": [20.0],
                              "anchor_month_recovered_after_transient_404": True,
                              "anchor_month_final_http_status": 200}]
    cap = []
    restore = _install_stubs(cap)
    try:
        row, _ = panel.process_ticker(None, TICKER, datetime(2026, 8, 5, 2, 0, tzinfo=timezone.utc),
                                       wiki_remaining_budget_s=100.0, watermark_info=_agg(),
                                       effective_info=eff)
    finally:
        restore()
    import json as _json
    check("31. panel row carries the attempt count",
          row["wiki_anchor_month_attempt_count"] == 2, row["wiki_anchor_month_attempt_count"])
    check("31. panel row carries the attempt statuses as deterministic JSON",
          _json.loads(row["wiki_anchor_month_attempt_statuses"]) == ["404", "200_ok"],
          row["wiki_anchor_month_attempt_statuses"])
    check("31. panel row carries the retry waits",
          _json.loads(row["wiki_anchor_month_retry_wait_seconds"]) == [20.0],
          row["wiki_anchor_month_retry_wait_seconds"])
    check("31. panel row flags the transient-404 recovery",
          row["wiki_anchor_month_recovered_after_transient_404"] is True, row)
    check("31. panel row carries the final http status",
          row["wiki_anchor_month_final_http_status"] == 200, row)


# === 32. Retries write nothing to the cache ===
def test_32_no_cache_writes_from_retries():
    before = wt.CACHE_PATH.exists()
    for script in ([404, "ok"], [404, 404, "ok"], [404, 404, 404]):
        _stage1(script)
    check("32. no cache file was created by any retry path",
          wt.CACHE_PATH.exists() == before, str(wt.CACHE_PATH))

    full = wt.resolve_effective_panel_watermark(ONE, ONE_ART, _agg(),
                                                 fetch_fn=_scripted([404, "ok"]),
                                                 limiter=_limiter()[0], jitter_fn=_no_jitter)
    check("32. a recovered response is carried in memory, not cached",
          full["status"] == "ok" and ONE[0] in full["anchor_month_rows"]
          and not wt.CACHE_PATH.exists(), full["status"])
    import inspect
    check("32. Stage 1 contains no cache-write call at all",
          "write_chunk_to_cache" not in inspect.getsource(wt.retrieve_anchor_month_availability))


# === 33. Pageview magnitudes cannot affect retry or watermark decisions ===
def test_33_magnitude_cannot_affect_retry():
    outcomes = []
    for mag in (0, 1, 10 ** 9):
        calls = []

        def fn(a, start, end, timeout_s=None, _m=mag):
            calls.append(1)
            if len(calls) == 1:
                return {"status": "http_error", "http_status": 404, "items": [], "url": "u",
                        "network_elapsed_s": 0.0, "retry_after": None}
            return {"status": "ok", "http_status": 200,
                    "items": _rows(start, min(end, AGG), views=_m), "url": "u",
                    "network_elapsed_s": 0.0, "retry_after": None}

        lim, _ = _limiter()
        res = wt.retrieve_anchor_month_availability(ONE, ONE_ART, AGG, fetch_fn=fn, limiter=lim,
                                                     jitter_fn=_no_jitter)
        r = res["results"][0]
        outcomes.append((len(calls), r["anchor_month_attempt_count"],
                         tuple(r["anchor_month_attempt_statuses"]),
                         tuple(r["anchor_month_retry_wait_seconds"]),
                         r["latest_available_date"]))
    check("33. retry count, statuses, waits and measured date are identical across magnitudes",
          len(set(outcomes)) == 1, outcomes)
    check("33. an all-zero-views response is accepted exactly like any other",
          outcomes[0][4] == AGG, outcomes[0])


if __name__ == "__main__":
    _bh = _sha256(_OPERATIONAL_CACHE)
    _bs = _OPERATIONAL_CACHE.stat().st_size if _OPERATIONAL_CACHE.exists() else None
    _tmp = _use_temp_cache()
    try:
        test_1_no_separate_probe()
        test_2_request_end_is_aggregate_watermark()
        test_3_rollover_prior_month()
        test_4_adbe_style_response_trails_aggregate()
        test_5_mixed_endings_common_minimum()
        test_6_responses_reused_no_second_request()
        test_7_shape_dependence_cannot_split_measurement_from_retrieval()
        test_8_single_shared_limiter()
        test_9_retry_after_honored()
        test_10_exhausted_429_fails_closed()
        test_11_404_fails_closed()
        test_12_trailing_allowed_then_removed()
        test_13_internal_gaps_still_fail()
        test_14_slicing_is_pure_filtering()
        test_15_uniform_watermark_across_rows()
        test_16_order_invariance()
        test_17_magnitude_invariance()
        test_19_success_first_attempt()
        test_20_404_then_200()
        test_21_404_404_then_200()
        test_22_three_404s_fail_closed()
        test_23_404_then_malformed_then_valid()
        test_24_no_retry_on_client_errors()
        test_25_identical_request_every_attempt()
        test_26_first_valid_200_wins()
        test_27_retries_use_shared_limiter()
        test_28_retry_after_on_404()
        test_29_budget_stops_retries()
        test_30_deterministic_jitter()
        test_31_provenance_matches_attempts()
        test_32_no_cache_writes_from_retries()
        test_33_magnitude_cannot_affect_retry()
    finally:
        _restore_cache_path(_tmp)
    test_18_operational_cache_untouched(_bh, _bs)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL TWO-STAGE EFFECTIVE-PANEL-WATERMARK TESTS PASSED (required items 1-18)")
        sys.exit(0)
