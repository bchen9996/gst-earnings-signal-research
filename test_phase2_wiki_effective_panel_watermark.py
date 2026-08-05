#!/usr/bin/env python3
# Deterministic tests for the EFFECTIVE PANEL WATERMARK (2026-08-05).
#
# Background: the aggregate pageviews endpoint answers "did en.wikipedia.org
# publish day D site-wide?", never "did THIS article publish day D?". The
# 2026-08-05 merge-gate PARTIAL proved the two diverge -- the aggregate
# reported 2026-08-04 while only 5 of the 24 locked articles actually
# contained that date, so 19 tickers returned HTTP 200 with a short series
# and were correctly rejected as incomplete_coverage. See Live Signal
# Engine/Phase2 Failure Evidence/2026-08-05_AggregateVsPerArticle_Watermark_
# PARTIAL/ROOT_CAUSE.md.
#
# The fix measures each locked ticker's latest genuinely-published date from
# validated HTTP-200 per-article data and binds the whole panel to the
# MINIMUM of those 24 dates. Crucially it lowers a shared TRAILING edge --
# it does NOT forgive an internal historical gap (test 7), and it does not
# weaken the 24/24 completion gate in any other respect (tests 4, 5, 12, 13).
#
# Coverage (spec items in brackets):
#    1. all article watermarks equal the aggregate watermark        [item 1]
#    2. 5 tickers at D, 19 at D-1 -> common D-1 watermark           [item 2]
#    3. one ticker lagging two days -> D-2                          [item 3]
#    4. a missing/unmeasurable article watermark fails closed       [item 4]
#    5. mixed per-row anchors rejected by the gate                  [item 5]
#    6. post-watermark observations excluded from the z-score       [item 6]
#    7. internal historical gap STILL rejected                      [item 7]
#    8. pull_start anchored to the effective panel watermark        [item 8]
#    9. result invariant to ticker-processing order                 [item 9]
#   10. no zero-fill / no incomplete-coverage acceptance            [item 10]
#   11. operational cache untouched by these tests                  [item 11]
#   12. gate fails closed when the effective watermark is unresolved
#   13. gate fails when a row's anchor is not the effective watermark
#   14. probe uses ONE request of the production shape, no fallback
#   15. aggregate-vs-panel lag recorded, aggregate never raises the panel
#   16. measurement invariant to pageview magnitude (non-circularity)
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


ANCHOR = date(2026, 8, 5)      # "today"
D = date(2026, 8, 4)           # aggregate watermark (lag 1)
TICKER = "AAPL"                # a real key in TICKER_TO_WIKI_ARTICLE

# A 24-name stand-in universe with a stable article mapping. Deliberately
# NOT the locked TICKERS list -- these tests must not depend on, and must
# never be able to alter, the locked universe.
UNIVERSE = [f"T{i:02d}" for i in range(24)]
ARTICLES = {t: f"Article_{t}" for t in UNIVERSE}

_ORIGINAL_CACHE_PATH = wt.CACHE_PATH
_OPERATIONAL_CACHE = Path("Live Signal Engine") / "Phase2_Wikipedia_Cache.csv"


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _use_temp_cache():
    tmp_dir = tempfile.mkdtemp(prefix="wiki_effwm_test_")
    wt.CACHE_PATH = Path(tmp_dir) / "test_cache.csv"
    return tmp_dir


def _restore_cache_path(tmp_dir):
    wt.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _mock_article_fetch(latest_by_article: dict, failures: dict | None = None,
                        views_by_article: dict | None = None):
    """Builds a fetch_fn matching fetch_chunk_isolated's signature and
    return shape. Each article serves a contiguous daily series from the
    requested start through min(requested end, that article's own latest
    published date) -- i.e. exactly the trailing-lag behaviour the real
    endpoint exhibits.

    failures: {article: response_dict} to force a non-ok / non-200 outcome.
    views_by_article: {article: int} to vary pageview MAGNITUDE while
    holding dates fixed (used by test 16 to prove non-circularity).
    """
    calls = []

    def _fn(article, start, end, timeout_s=None):
        calls.append({"article": article, "start": start, "end": end, "timeout_s": timeout_s})
        if failures and article in failures:
            resp = dict(failures[article])
            resp.setdefault("items", [])
            resp.setdefault("url", f"http://mock/{article}")
            resp.setdefault("network_elapsed_s", 0.01)
            return resp
        latest = latest_by_article.get(article)
        items = []
        if latest is not None:
            views = (views_by_article or {}).get(article, 100)
            cursor = start
            while cursor <= min(end, latest):
                items.append({"date": cursor.strftime("%Y%m%d"), "pageviews": views})
                cursor += timedelta(days=1)
        return {"status": "ok", "http_status": 200, "items": items,
                "url": f"http://mock/{article}", "network_elapsed_s": 0.01,
                "retry_after": None, "terminated": False}

    _fn.calls = calls
    return _fn


def _agg(watermark_date: date | None, status: str = "ok") -> dict:
    return {"status": status, "watermark_date": watermark_date, "lag_days": 1,
            "retrieved_at_utc": "2026-08-05T02:00:00+00:00",
            "source_url": "https://example.org/aggregate", "http_status": 200}


# === 1. All article watermarks equal the aggregate watermark ===
def test_1_all_articles_equal_aggregate():
    fetch_fn = _mock_article_fetch({a: D for a in ARTICLES.values()})
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn)
    check("1. status ok", res["status"] == "ok", res.get("failure_reason"))
    check("1. effective watermark == aggregate watermark (D)",
          res["effective_panel_watermark_date"] == D, res["effective_panel_watermark_date"])
    check("1. aggregate_vs_panel_lag_days == 0", res["aggregate_vs_panel_lag_days"] == 0,
          res["aggregate_vs_panel_lag_days"])
    check("1. all 24 tickers measured", res["measured_count"] == 24 and res["expected_count"] == 24, res)
    check("1. every ticker binds at the minimum", len(res["binding_tickers"]) == 24, res["binding_tickers"])
    check("1. method recorded", res["method"] == wt.EFFECTIVE_WATERMARK_METHOD, res["method"])


# === 2. 5 tickers at D, 19 at D-1 -> common D-1 watermark (the real 2026-08-05 shape) ===
def test_2_five_at_D_nineteen_at_D_minus_1():
    ahead = UNIVERSE[:5]
    latest = {ARTICLES[t]: (D if t in ahead else D - timedelta(days=1)) for t in UNIVERSE}
    fetch_fn = _mock_article_fetch(latest)
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn)
    check("2. status ok", res["status"] == "ok", res.get("failure_reason"))
    check("2. effective watermark is the COMMON D-1, not D",
          res["effective_panel_watermark_date"] == D - timedelta(days=1),
          res["effective_panel_watermark_date"])
    check("2. aggregate_vs_panel_lag_days == 1 (panel one day behind the aggregate)",
          res["aggregate_vs_panel_lag_days"] == 1, res["aggregate_vs_panel_lag_days"])
    check("2. the 5 ahead tickers are NOT binding", not set(ahead) & set(res["binding_tickers"]),
          res["binding_tickers"])
    check("2. the 19 lagging tickers are the binding set",
          set(res["binding_tickers"]) == set(UNIVERSE[5:]), res["binding_tickers"])
    check("2. the 5 ahead tickers' own measured dates are still recorded as D",
          all(res["per_ticker_latest"][t] == D for t in ahead), res["per_ticker_latest"])


# === 3. One ticker lagging two days pulls the whole panel back ===
def test_3_one_ticker_lagging_two_days():
    laggard = UNIVERSE[7]
    latest = {ARTICLES[t]: (D - timedelta(days=2) if t == laggard else D) for t in UNIVERSE}
    fetch_fn = _mock_article_fetch(latest)
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn)
    check("3. status ok", res["status"] == "ok", res.get("failure_reason"))
    check("3. effective watermark is D-2 (the single slowest article governs)",
          res["effective_panel_watermark_date"] == D - timedelta(days=2),
          res["effective_panel_watermark_date"])
    check("3. aggregate_vs_panel_lag_days == 2", res["aggregate_vs_panel_lag_days"] == 2,
          res["aggregate_vs_panel_lag_days"])
    check("3. exactly the laggard binds", res["binding_tickers"] == [laggard], res["binding_tickers"])


# === 4. A missing / unmeasurable article watermark fails the panel closed ===
def test_4_missing_article_watermark_fails_closed():
    broken = UNIVERSE[3]
    latest = {ARTICLES[t]: D for t in UNIVERSE}
    for label, failure in [
        ("404", {"status": "ok", "http_status": 404}),
        ("timeout", {"status": "timeout", "http_status": None}),
        ("empty 200", {"status": "ok", "http_status": 200, "items": []}),
    ]:
        fetch_fn = _mock_article_fetch(latest, failures={ARTICLES[broken]: failure})
        res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn)
        check(f"4. {label}: status is failed_closed", res["status"] == "failed_closed", res["status"])
        check(f"4. {label}: effective watermark is None (never guessed)",
              res["effective_panel_watermark_date"] is None, res["effective_panel_watermark_date"])
        check(f"4. {label}: the aggregate watermark is NOT substituted",
              res["effective_panel_watermark_date"] != D, res["effective_panel_watermark_date"])
        check(f"4. {label}: the unmeasurable ticker is named",
              [u["ticker"] for u in res["unmeasured"]] == [broken], res["unmeasured"])
        check(f"4. {label}: a minimum over the other 23 was NOT computed",
              res["measured_count"] == 23 and res["effective_panel_watermark_date"] is None, res)

    # A ticker with no article mapping at all is equally unmeasurable.
    no_map = dict(ARTICLES)
    no_map.pop(UNIVERSE[11])
    fetch_fn = _mock_article_fetch(latest)
    res = wt.resolve_effective_panel_watermark(UNIVERSE, no_map, ANCHOR, _agg(D), fetch_fn=fetch_fn)
    check("4. missing article mapping: status is failed_closed", res["status"] == "failed_closed", res)
    check("4. missing article mapping: reason recorded as no_article_mapping",
          res["unmeasured"][0]["reason"] == "no_article_mapping", res["unmeasured"])


# === 5. Mixed per-row anchors rejected by the completion gate ===
def test_5_mixed_per_row_anchors_rejected():
    tickers = ["AAA", "BBB", "CCC"]
    eff = D - timedelta(days=1)

    def row(t, effective=eff, anchor=eff):
        return {"ticker": t, "all_six_fields_clean": True, "earnings_status": "ok",
                "retrieval_timestamp_utc": "2026-08-05T00:00:00+00:00",
                "wiki_effective_panel_watermark_date": effective.isoformat(),
                "wiki_zscore_anchor_date": anchor.isoformat()}

    ok_rows = [row(t) for t in tickers]
    check("5. uniform anchors -> gate passes",
          panel.is_run_complete(ok_rows, "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok", effective_watermark_date=eff) is True)

    mixed_effective = [row("AAA"), row("BBB"), row("CCC", effective=D)]
    check("5. one row with a DIFFERENT effective panel watermark -> gate fails",
          panel.is_run_complete(mixed_effective, "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok", effective_watermark_date=eff) is False)

    mixed_anchor = [row("AAA"), row("BBB"), row("CCC", anchor=D)]
    check("5. one row anchored on its OWN date instead of the panel watermark -> gate fails",
          panel.is_run_complete(mixed_anchor, "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok", effective_watermark_date=eff) is False)

    all_shifted = [row(t, effective=D, anchor=D) for t in tickers]
    check("5. rows uniformly agreeing on the WRONG date (not the run's resolved one) -> gate fails",
          panel.is_run_complete(all_shifted, "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok", effective_watermark_date=eff) is False)


# === 6. Post-watermark observations excluded from the z-score ===
def test_6_post_watermark_observations_excluded():
    eff = D - timedelta(days=1)
    base = [{"date": (eff - timedelta(days=i)).strftime("%Y%m%d"), "pageviews": 100 + i}
            for i in range(15 * 7)]
    poisoned = base + [
        {"date": D.strftime("%Y%m%d"), "pageviews": 10 ** 7},
        {"date": (D + timedelta(days=1)).strftime("%Y%m%d"), "pageviews": 10 ** 8},
    ]

    clean_row, poisoned_row = {}, {}
    panel._finalize_wiki_row(clean_row, "Article_X", base, eff, [])
    panel._finalize_wiki_row(poisoned_row, "Article_X", poisoned, eff, [])

    check("6. z-score is unchanged by observations dated after the effective watermark",
          clean_row["wiki_zscore"] == poisoned_row["wiki_zscore"],
          f"{clean_row['wiki_zscore']} vs {poisoned_row['wiki_zscore']}")
    check("6. the anchor is the effective watermark, not the newest observation",
          poisoned_row["wiki_zscore_anchor_date"] == eff.isoformat(),
          poisoned_row["wiki_zscore_anchor_date"])
    check("6. a huge post-watermark spike did not leak into the score",
          poisoned_row["wiki_zscore"] == clean_row["wiki_zscore"], poisoned_row["wiki_zscore"])


# === 7. An INTERNAL historical gap is still rejected (the CTSH case) ===
def test_7_internal_historical_gap_still_rejected():
    eff = D - timedelta(days=1)
    chunk_start, chunk_end = date(2026, 7, 1), date(2026, 7, 31)
    full = [{"date": (chunk_start + timedelta(days=i)).strftime("%Y%m%d"), "pageviews": 50}
            for i in range((chunk_end - chunk_start).days + 1)]
    # CTSH's real failure: 2026-07-08..2026-07-14 missing from the middle.
    gapped = [r for r in full
              if not (date(2026, 7, 8) <= datetime.strptime(r["date"], "%Y%m%d").date() <= date(2026, 7, 14))]

    v_full = wt.validate_snapshot("CTSH", "Cognizant", chunk_start, chunk_end, full, eff)
    v_gap = wt.validate_snapshot("CTSH", "Cognizant", chunk_start, chunk_end, gapped, eff)
    check("7. the complete closed month validates", v_full["valid"] is True, v_full)
    check("7. the SAME month with an internal 7-day hole is rejected",
          v_gap["valid"] is False, v_gap)
    check("7. rejection category is incomplete_coverage",
          v_gap["category"] == "incomplete_coverage", v_gap["category"])
    check("7. the missing interior dates are named in the reason",
          "20260708" in v_gap["reason"], v_gap["reason"])

    # The decisive property: lowering the panel watermark cannot heal a hole
    # that sits entirely BELOW it. Walk the watermark back a week at a time.
    still_rejected = []
    for back in (1, 7, 14, 21):
        w = eff - timedelta(days=back)
        v = wt.validate_snapshot("CTSH", "Cognizant", chunk_start, chunk_end, gapped, w)
        if w >= date(2026, 7, 14):
            still_rejected.append(v["valid"] is False)
    check("7. no lowering of the effective watermark rescues an interior gap below it",
          all(still_rejected) and len(still_rejected) > 0, still_rejected)


# === 8/6b/10b. process_ticker-level behaviour ===
class _FakeTicker:
    def __init__(self, ticker, session=None):
        self.ticker = ticker

    def history(self, period=None):
        return pd.DataFrame()


def _install_stubs(capture: list, daily_rows=None):
    originals = {
        "fetch_days_to_next_earnings": panel.fetch_days_to_next_earnings,
        "get_nearest_post_earnings_expiry": panel.get_nearest_post_earnings_expiry,
        "get_option_snapshot": panel.get_option_snapshot,
        "fetch_ticker_series_scoped_backoff": panel.fetch_ticker_series_scoped_backoff,
        "yf_Ticker": panel.yf.Ticker,
        "wiki_load_cache": panel.wiki_transport.load_cache,
        "wiki_get_daily": panel.wiki_transport.get_ticker_wikipedia_daily,
    }
    panel.fetch_days_to_next_earnings = lambda ticker: 30
    panel.get_nearest_post_earnings_expiry = lambda tk, d: None
    panel.get_option_snapshot = lambda tk, expiry, price: {}
    panel.fetch_ticker_series_scoped_backoff = lambda pt, ticker: (
        pd.DataFrame(),
        {"status": "attempts_exhausted", "attempts": 0, "rate_limit_events": 0, "budget_exhausted": False})
    panel.yf.Ticker = _FakeTicker
    panel.wiki_transport.load_cache = lambda: pd.DataFrame(columns=panel.wiki_transport.CACHE_COLUMNS)

    def _fake_get_daily(ticker, article, start, end, watermark, cache_df=None,
                        remaining_budget_s=None, extra_daily_rows=None):
        capture.append({"ticker": ticker, "start": start, "end": end, "watermark": watermark})
        return {"chunk_results": [], "failed_chunks": [], "daily_rows": list(daily_rows or [])}

    panel.wiki_transport.get_ticker_wikipedia_daily = _fake_get_daily

    def restore():
        panel.fetch_days_to_next_earnings = originals["fetch_days_to_next_earnings"]
        panel.get_nearest_post_earnings_expiry = originals["get_nearest_post_earnings_expiry"]
        panel.get_option_snapshot = originals["get_option_snapshot"]
        panel.fetch_ticker_series_scoped_backoff = originals["fetch_ticker_series_scoped_backoff"]
        panel.yf.Ticker = originals["yf_Ticker"]
        panel.wiki_transport.load_cache = originals["wiki_load_cache"]
        panel.wiki_transport.get_ticker_wikipedia_daily = originals["wiki_get_daily"]

    return restore


def _eff_info(effective: date, aggregate: date, tickers=(TICKER,), status="ok") -> dict:
    return {"status": status,
            "effective_panel_watermark_date": effective if status == "ok" else None,
            "method": wt.EFFECTIVE_WATERMARK_METHOD,
            "aggregate_watermark_date": aggregate,
            "aggregate_vs_panel_lag_days": ((aggregate - effective).days
                                             if status == "ok" and aggregate else None),
            "per_ticker_latest": {t: effective for t in tickers},
            "measurements": [], "unmeasured": [],
            "measured_count": len(tickers) if status == "ok" else 0,
            "expected_count": len(tickers), "binding_tickers": sorted(tickers),
            "resolved_at_utc": "2026-08-05T02:00:00+00:00"}


def test_8_pull_start_anchored_to_effective_panel_watermark():
    eff = D - timedelta(days=1)
    run_ts = datetime(2026, 8, 5, 2, 14, 0, tzinfo=timezone.utc)
    capture = []
    restore = _install_stubs(capture)
    try:
        panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                              watermark_info=_agg(D),
                              effective_info=_eff_info(eff, D))
    finally:
        restore()

    check("8. the wiki leg ran", len(capture) == 1, capture)
    if capture:
        expected = eff - timedelta(days=panel.PULL_LOOKBACK_DAYS)
        check("8. pull_start == EFFECTIVE panel watermark - PULL_LOOKBACK_DAYS",
              capture[0]["start"] == expected, f"got {capture[0]['start']}, expected {expected}")
        check("8. pull_start is NOT anchored on the aggregate watermark",
              capture[0]["start"] != D - timedelta(days=panel.PULL_LOOKBACK_DAYS), capture[0]["start"])
        check("8. pull_start is NOT anchored on wall-clock today",
              capture[0]["start"] != run_ts.date() - timedelta(days=panel.PULL_LOOKBACK_DAYS),
              capture[0]["start"])
        check("8. the transport is given the EFFECTIVE watermark as its completeness bar",
              capture[0]["watermark"] == eff, capture[0]["watermark"])

    # And the row's provenance reflects the same single date.
    capture2 = []
    restore = _install_stubs(capture2)
    try:
        row, _ = panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                                       watermark_info=_agg(D),
                                       effective_info=_eff_info(eff, D))
    finally:
        restore()
    check("8. row records the effective panel watermark",
          row["wiki_effective_panel_watermark_date"] == eff.isoformat(),
          row["wiki_effective_panel_watermark_date"])
    check("8. row still records the aggregate watermark as provenance",
          row["wiki_aggregate_watermark_date"] == D.isoformat(), row["wiki_aggregate_watermark_date"])
    check("8. row records the method", row["wiki_effective_watermark_method"] == wt.EFFECTIVE_WATERMARK_METHOD,
          row["wiki_effective_watermark_method"])
    check("8. row records aggregate-vs-panel lag of 1 day",
          row["wiki_aggregate_vs_panel_lag_days"] == 1, row["wiki_aggregate_vs_panel_lag_days"])
    check("8. row records this ticker's own measured latest date",
          row["wiki_article_latest_available_date"] == eff.isoformat(),
          row["wiki_article_latest_available_date"])


# === 9. Result invariant to ticker-processing order ===
def test_9_result_invariant_to_ticker_order():
    latest = {ARTICLES[t]: D - timedelta(days=(i % 3)) for i, t in enumerate(UNIVERSE)}
    orders = [list(UNIVERSE), list(reversed(UNIVERSE)),
              [UNIVERSE[i] for i in (7, 0, 23, 4, 15, 8, 1, 19, 3, 11, 22, 2,
                                      5, 20, 9, 13, 6, 17, 10, 21, 12, 16, 14, 18)]]
    results = []
    for order in orders:
        fetch_fn = _mock_article_fetch(latest)
        res = wt.resolve_effective_panel_watermark(order, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn)
        results.append(res)
    dates = {r["effective_panel_watermark_date"] for r in results}
    check("9. all three processing orders produce the IDENTICAL effective watermark",
          len(dates) == 1, dates)
    check("9. and the identical binding-ticker set",
          len({tuple(r["binding_tickers"]) for r in results}) == 1,
          [r["binding_tickers"] for r in results])
    check("9. and the identical per-ticker measurement map",
          len({tuple(sorted(r["per_ticker_latest"].items())) for r in results}) == 1)


# === 10. No zero-fill, no incomplete-coverage acceptance ===
def test_10_no_zero_fill_no_incomplete_acceptance():
    eff = D - timedelta(days=1)
    chunk_start, chunk_end = date(2026, 8, 1), date(2026, 8, 5)
    # Exactly the 2026-08-05 shape: HTTP 200, but one day short of the bar.
    short = [{"date": (chunk_start + timedelta(days=i)).strftime("%Y%m%d"), "pageviews": 7}
             for i in range((eff - chunk_start).days)]      # missing `eff` itself
    v = wt.validate_snapshot("T", "Article_T", chunk_start, chunk_end, short, eff)
    check("10. an HTTP-200 response one day short of the watermark is REJECTED",
          v["valid"] is False and v["category"] == "incomplete_coverage", v)

    # The missing date must not be invented with a zero.
    zero_filled = short + [{"date": eff.strftime("%Y%m%d"), "pageviews": 0}]
    v_zero = wt.validate_snapshot("T", "Article_T", chunk_start, chunk_end, zero_filled, eff)
    check("10. a zero-filled row would satisfy coverage -- proving the fill must never happen upstream",
          v_zero["valid"] is True, v_zero)
    series = wt.assemble_daily_series(short)
    check("10. assemble_daily_series does NOT zero-fill the missing date",
          len(series) == len(short) and eff.strftime("%Y%m%d") not in
          set(series["date"].dt.strftime("%Y%m%d")), len(series))

    # And the availability probe never invents a date either: its answer is
    # the newest date actually observed, never the requested end.
    fetch_fn = _mock_article_fetch({"Article_T": eff})
    m = wt.measure_article_latest_available_date("T", "Article_T", ANCHOR, fetch_fn=fetch_fn)
    check("10. probe reports the newest OBSERVED date, not the requested end date",
          m["latest_available_date"] == eff and m["latest_available_date"] != ANCHOR, m)


# === 11. Operational cache untouched by these tests ===
def test_11_operational_cache_untouched(before_hash, before_size):
    after_hash = _sha256(_OPERATIONAL_CACHE)
    after_size = _OPERATIONAL_CACHE.stat().st_size if _OPERATIONAL_CACHE.exists() else None
    check("11. operational Phase2_Wikipedia_Cache.csv SHA-256 unchanged by this test file",
          after_hash == before_hash, f"{before_hash} -> {after_hash}")
    check("11. operational cache byte size unchanged",
          after_size == before_size, f"{before_size} -> {after_size}")
    check("11. wt.CACHE_PATH was restored to the operational path",
          wt.CACHE_PATH == _ORIGINAL_CACHE_PATH, wt.CACHE_PATH)


# === 12. Gate fails closed when the effective watermark is unresolved ===
def test_12_gate_fails_closed_without_effective_watermark():
    tickers = ["AAA", "BBB", "CCC"]
    eff = D - timedelta(days=1)
    rows = [{"ticker": t, "all_six_fields_clean": True, "earnings_status": "ok",
             "retrieval_timestamp_utc": "2026-08-05T00:00:00+00:00",
             "wiki_effective_panel_watermark_date": eff.isoformat(),
             "wiki_zscore_anchor_date": eff.isoformat()} for t in tickers]

    check("12. perfectly clean rows + valid aggregate watermark but effective status missing -> fails",
          panel.is_run_complete(rows, "COMPLETE", tickers, watermark_status="ok") is False)
    for bad in ("failed_closed", "not_attempted_aggregate_watermark_failed", None):
        check(f"12. effective_watermark_status={bad!r} -> gate fails",
              panel.is_run_complete(rows, "COMPLETE", tickers, watermark_status="ok",
                                     effective_watermark_status=bad,
                                     effective_watermark_date=eff) is False)
    check("12. effective status ok but date None -> gate fails",
          panel.is_run_complete(rows, "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok",
                                 effective_watermark_date=None) is False)
    check("12. a failed AGGREGATE watermark still fails even with a valid effective one",
          panel.is_run_complete(rows, "COMPLETE", tickers, watermark_status="failed_closed",
                                 effective_watermark_status="ok",
                                 effective_watermark_date=eff) is False)
    check("12. both valid -> gate passes (no weakening of any other criterion)",
          panel.is_run_complete(rows, "COMPLETE", tickers, watermark_status="ok",
                                 effective_watermark_status="ok",
                                 effective_watermark_date=eff) is True)


# === 13. An unresolved effective watermark stops the wiki leg entirely ===
def test_13_unresolved_effective_watermark_skips_wiki_leg():
    run_ts = datetime(2026, 8, 5, 2, 14, 0, tzinfo=timezone.utc)
    capture = []
    restore = _install_stubs(capture)
    try:
        row, pending = panel.process_ticker(
            None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
            watermark_info=_agg(D),
            effective_info=_eff_info(None, D, status="failed_closed"))
    finally:
        restore()
    check("13. no Wikipedia request was made at all", len(capture) == 0, capture)
    check("13. wiki_status is incomplete_effective_watermark_unavailable",
          row["wiki_status"] == "incomplete_effective_watermark_unavailable", row["wiki_status"])
    check("13. wiki_zscore stays None (never computed)", row["wiki_zscore"] is None, row["wiki_zscore"])
    check("13. the aggregate watermark was NOT substituted as the anchor",
          row.get("wiki_zscore_anchor_date") is None, row.get("wiki_zscore_anchor_date"))
    check("13. all_six_fields_clean is False", row["all_six_fields_clean"] is False)


# === 14. The probe uses ONE production-shaped request and never falls back ===
def test_14_probe_shape_and_no_fallback():
    fetch_fn = _mock_article_fetch({"Article_T": D})
    m = wt.measure_article_latest_available_date("T", "Article_T", ANCHOR, fetch_fn=fetch_fn)
    check("14. exactly ONE request was issued", len(fetch_fn.calls) == 1, fetch_fn.calls)
    call = fetch_fn.calls[0]
    check("14. it is a RANGE request, not a single-day one", call["start"] < call["end"],
          (call["start"], call["end"]))
    check("14. the range ends at the anchor date", call["end"] == ANCHOR, call["end"])
    check("14. the range starts PER_ARTICLE_PROBE_WINDOW_DAYS earlier",
          call["start"] == ANCHOR - timedelta(days=wt.PER_ARTICLE_PROBE_WINDOW_DAYS), call["start"])
    check("14. measurement succeeded", m["status"] == "ok" and m["latest_available_date"] == D, m)

    # On failure it must NOT retry, widen, or reshape.
    failing = _mock_article_fetch({}, failures={"Article_T": {"status": "ok", "http_status": 404}})
    m2 = wt.measure_article_latest_available_date("T", "Article_T", ANCHOR, fetch_fn=failing)
    check("14. a 404 produces exactly ONE request -- no retry, no widening, no reshaping",
          len(failing.calls) == 1, failing.calls)
    check("14. a 404 is unmeasured, not silently downgraded to an older date",
          m2["status"] == "unmeasured" and m2["latest_available_date"] is None, m2)
    check("14. the failure reason is recorded", "404" in m2["reason"], m2["reason"])


# === 15. Aggregate is provenance only and never raises the panel watermark ===
def test_15_aggregate_never_raises_panel_watermark():
    # Every article is a day behind the aggregate.
    latest = {ARTICLES[t]: D - timedelta(days=1) for t in UNIVERSE}
    fetch_fn = _mock_article_fetch(latest)
    res = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn)
    check("15. the aggregate's newer date does NOT raise the effective watermark",
          res["effective_panel_watermark_date"] == D - timedelta(days=1),
          res["effective_panel_watermark_date"])
    check("15. the aggregate is still recorded for source-health",
          res["aggregate_watermark_date"] == D, res["aggregate_watermark_date"])
    check("15. the divergence is quantified", res["aggregate_vs_panel_lag_days"] == 1,
          res["aggregate_vs_panel_lag_days"])

    # Articles AHEAD of the aggregate: recorded as a negative lag, not clamped.
    ahead = {ARTICLES[t]: D + timedelta(days=1) for t in UNIVERSE}
    res2 = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR + timedelta(days=2),
                                                 _agg(D), fetch_fn=_mock_article_fetch(ahead))
    check("15. an article ahead of the aggregate yields a negative lag, recorded not clamped",
          res2["aggregate_vs_panel_lag_days"] == -1, res2["aggregate_vs_panel_lag_days"])

    # With no aggregate available at all the lag is simply unknown.
    res3 = wt.resolve_effective_panel_watermark(UNIVERSE, ARTICLES, ANCHOR, _agg(None, status="failed_closed"),
                                                 fetch_fn=_mock_article_fetch(latest))
    check("15. no aggregate -> lag is None, effective watermark still measured independently",
          res3["aggregate_vs_panel_lag_days"] is None
          and res3["effective_panel_watermark_date"] == D - timedelta(days=1), res3)


# === 16. NON-CIRCULARITY: measurement is invariant to pageview magnitude ===
def test_16_measurement_is_invariant_to_pageview_magnitude():
    latest = {ARTICLES[t]: D - timedelta(days=(i % 2)) for i, t in enumerate(UNIVERSE)}
    results = []
    for views in ({a: 1 for a in ARTICLES.values()},
                  {a: 10 ** 9 for a in ARTICLES.values()},
                  {a: (i * 977) % 100003 for i, a in enumerate(ARTICLES.values())},
                  {a: 0 for a in ARTICLES.values()}):
        fetch_fn = _mock_article_fetch(latest, views_by_article=views)
        results.append(wt.resolve_effective_panel_watermark(
            UNIVERSE, ARTICLES, ANCHOR, _agg(D), fetch_fn=fetch_fn))
    check("16. effective watermark is identical across wildly different pageview magnitudes",
          len({r["effective_panel_watermark_date"] for r in results}) == 1,
          [r["effective_panel_watermark_date"] for r in results])
    check("16. binding-ticker set is identical too",
          len({tuple(r["binding_tickers"]) for r in results}) == 1,
          [r["binding_tickers"] for r in results])
    check("16. even an all-zero-views panel measures the same dates (counts are never a threshold)",
          results[3]["effective_panel_watermark_date"] == results[0]["effective_panel_watermark_date"],
          (results[3]["effective_panel_watermark_date"], results[0]["effective_panel_watermark_date"]))

    # A structurally INVALID pageviews value is skipped -- that is a shape
    # check, not a magnitude check.
    def _bad_fetch(article, start, end, timeout_s=None):
        return {"status": "ok", "http_status": 200, "url": "http://mock", "network_elapsed_s": 0.0,
                "items": [{"date": (D - timedelta(days=1)).strftime("%Y%m%d"), "pageviews": 5},
                          {"date": D.strftime("%Y%m%d"), "pageviews": "not-a-number"}]}
    m = wt.measure_article_latest_available_date("T", "Article_T", ANCHOR, fetch_fn=_bad_fetch)
    check("16. a malformed pageviews value cannot set the watermark",
          m["latest_available_date"] == D - timedelta(days=1), m)


if __name__ == "__main__":
    _before_hash = _sha256(_OPERATIONAL_CACHE)
    _before_size = _OPERATIONAL_CACHE.stat().st_size if _OPERATIONAL_CACHE.exists() else None
    _tmp = _use_temp_cache()
    try:
        test_1_all_articles_equal_aggregate()
        test_2_five_at_D_nineteen_at_D_minus_1()
        test_3_one_ticker_lagging_two_days()
        test_4_missing_article_watermark_fails_closed()
        test_5_mixed_per_row_anchors_rejected()
        test_6_post_watermark_observations_excluded()
        test_7_internal_historical_gap_still_rejected()
        test_8_pull_start_anchored_to_effective_panel_watermark()
        test_9_result_invariant_to_ticker_order()
        test_10_no_zero_fill_no_incomplete_acceptance()
        test_12_gate_fails_closed_without_effective_watermark()
        test_13_unresolved_effective_watermark_skips_wiki_leg()
        test_14_probe_shape_and_no_fallback()
        test_15_aggregate_never_raises_panel_watermark()
        test_16_measurement_is_invariant_to_pageview_magnitude()
    finally:
        _restore_cache_path(_tmp)
    test_11_operational_cache_untouched(_before_hash, _before_size)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL EFFECTIVE-PANEL-WATERMARK TESTS PASSED (spec items 1-11 + fail-closed, "
              "probe-shape, aggregate-provenance and non-circularity coverage)")
        sys.exit(0)
