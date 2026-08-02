#!/usr/bin/env python3
# Deterministic tests for the 2026-08-02 additive wiki source-provenance
# correction: cache-union (and cache/fetch) provenance must survive from
# attempt_cache_union_reconstruction()/get_ticker_wikipedia_daily() all the
# way to the finalized panel row, and _finalize_wiki_row() must derive
# wiki_source_mode from the chunks that actually contributed instead of
# hardcoding "fresh". See CHANGELOG.md (2026-08-02 entries) and
# GST_Phase2_DailyPanel._wiki_source_provenance().
#
# No network access, no operational cache access, no panel execution.
#
# Run directly: python test_phase2_wiki_source_provenance.py

from __future__ import annotations
import sys
import os
import json
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_DailyPanel as panel
import GST_Phase2_Wikipedia_Transport as wiki_transport

FAILURES = []

_ORIGINAL_CACHE_PATH = wiki_transport.CACHE_PATH


def _use_temp_cache() -> str:
    """Redirects wiki_transport.CACHE_PATH to a throwaway temp file for the
    duration of a test. REQUIRED before calling any transport function that
    can reach a successful fetch path -- run_bounded_second_pass() (and
    get_ticker_wikipedia_daily() on a genuine fetch success) call
    write_chunk_to_cache() internally, which reads/writes the module-level
    CACHE_PATH directly and is NOT parameterized by whatever in-memory
    cache_df a test passes in. Without this redirection, a test whose
    fetch_fn ever returns a successful result would silently write
    fabricated rows into the real operational
    Live Signal Engine/Phase2_Wikipedia_Cache.csv."""
    tmp_dir = tempfile.mkdtemp(prefix="wiki_source_provenance_test_")
    wiki_transport.CACHE_PATH = Path(tmp_dir) / "test_cache.csv"
    return tmp_dir


def _restore_cache_path(tmp_dir: str) -> None:
    wiki_transport.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(tmp_dir, ignore_errors=True)


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


TICKER = "AAPL"
ARTICLE = "Apple_Inc."


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_phase2_wiki_cache_union.py's fixtures)
# ---------------------------------------------------------------------------

def _date_range(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def _cache_group(ticker: str, article: str, chunk_start: date, chunk_end: date,
                  pageviews_by_date: dict[date, int] | None = None,
                  http_status: int = 200, last_verified_utc: str = "2026-07-15T00:00:00+00:00") -> list[dict]:
    dates = _date_range(chunk_start, chunk_end)
    pageviews_by_date = pageviews_by_date or {}
    daily_rows = [{"date": d.strftime("%Y%m%d"), "pageviews": pageviews_by_date.get(d, 1000 + d.day)}
                  for d in dates]
    content_hash = wiki_transport.compute_chunk_hash(daily_rows)
    return [{
        "ticker": ticker, "configured_article_title": article, "canonical_title": "",
        "page_id": "", "chunk_start": chunk_start.isoformat(), "chunk_end": chunk_end.isoformat(),
        "date": r["date"], "pageviews": r["pageviews"], "source_url": "https://example.org/api",
        "http_status": http_status, "first_retrieved_utc": last_verified_utc,
        "last_verified_utc": last_verified_utc, "cache_schema_version": wiki_transport.CACHE_SCHEMA_VERSION,
        "content_hash": content_hash,
    } for r in daily_rows]


def _cache_df(*groups: list[dict]) -> pd.DataFrame:
    rows = [r for g in groups for r in g]
    return pd.DataFrame(rows, columns=wiki_transport.CACHE_COLUMNS)


def _daily_rows(end_date: date, n_days: int, base_value: int = 1000) -> list[dict]:
    rows = []
    for i in range(n_days):
        d = end_date - timedelta(days=n_days - 1 - i)
        rows.append({"date": d.strftime("%Y%m%d"), "pageviews": base_value + (i * 3) % 97})
    return rows


def _fresh_row() -> dict:
    return {"ticker": TICKER, "gst_zscore": 1.0, "implied_volatility": 0.2,
            "realized_vol": 0.3, "price": 100.0, "volume": 1000}


class _FakeTicker:
    def __init__(self, ticker, session=None):
        self.ticker = ticker

    def history(self, period=None):
        return pd.DataFrame()


def _install_process_ticker_stubs(fake_get_ticker_wikipedia_daily):
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
        {"status": "attempts_exhausted", "attempts": 0, "rate_limit_events": 0, "budget_exhausted": False},
    )
    panel.yf.Ticker = _FakeTicker
    panel.wiki_transport.load_cache = lambda: pd.DataFrame(columns=panel.wiki_transport.CACHE_COLUMNS)
    panel.wiki_transport.get_ticker_wikipedia_daily = fake_get_ticker_wikipedia_daily

    def restore():
        panel.fetch_days_to_next_earnings = originals["fetch_days_to_next_earnings"]
        panel.get_nearest_post_earnings_expiry = originals["get_nearest_post_earnings_expiry"]
        panel.get_option_snapshot = originals["get_option_snapshot"]
        panel.fetch_ticker_series_scoped_backoff = originals["fetch_ticker_series_scoped_backoff"]
        panel.yf.Ticker = originals["yf_Ticker"]
        panel.wiki_transport.load_cache = originals["wiki_load_cache"]
        panel.wiki_transport.get_ticker_wikipedia_daily = originals["wiki_get_daily"]

    return restore


def _watermark_info(watermark_date: date) -> dict:
    return {"status": "ok", "watermark_date": watermark_date, "lag_days": 1,
            "retrieved_at_utc": "2026-08-01T00:00:00+00:00",
            "source_url": "https://example.org/watermark", "http_status": 200}


# === 1. A union-only ticker's final panel row is not labeled fresh ===
def test_1_union_only_not_labeled_fresh():
    watermark_date = date(2026, 8, 1)
    run_ts = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    daily_rows = _daily_rows(watermark_date, 15 * 7)

    def fake_get_daily(ticker, article, start, end, watermark, cache_df=None, remaining_budget_s=None):
        return {
            "chunk_results": [{
                "chunk_start": start.isoformat(), "chunk_end": end.isoformat(),
                "source": "cache_union_reconstruction", "status": "ok",
                "cache_union_provenance": {
                    "wiki_source_mode": "cache_union_reconstruction",
                    "contributing_chunk_keys": [["2025-10-05", "2025-10-31"]],
                    "contributing_content_hashes": ["abc123"],
                    "contributing_retrieval_timestamps": ["2026-07-15T00:00:00+00:00"],
                    "reconstructed_at_utc": "2026-08-02T00:00:00+00:00",
                    "date_count": len(daily_rows),
                },
            }],
            "failed_chunks": [], "daily_rows": daily_rows,
        }

    restore = _install_process_ticker_stubs(fake_get_daily)
    try:
        row, _ = panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                                       watermark_info=_watermark_info(watermark_date))
    finally:
        restore()

    check("1a. wiki_source_mode == 'cache_union_only' (not 'fresh')",
          row.get("wiki_source_mode") == "cache_union_only", f"got {row.get('wiki_source_mode')!r}")
    check("1b. wiki_source_mode is never the string 'fresh'", row.get("wiki_source_mode") != "fresh")
    check("1c. wiki_cache_union_used is True", row.get("wiki_cache_union_used") is True)
    check("1d. wiki_cache_union_chunk_count == 1", row.get("wiki_cache_union_chunk_count") == 1)
    components = json.loads(row.get("wiki_source_components_json") or "[]")
    check("1e. wiki_source_components_json == ['cache_union_reconstruction']",
          components == ["cache_union_reconstruction"], f"got {components!r}")


# === 2. Union provenance survives process_ticker -> checkpoint/DataFrame serialization ===
def test_2_provenance_survives_serialization():
    watermark_date = date(2026, 8, 1)
    run_ts = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    daily_rows = _daily_rows(watermark_date, 15 * 7)
    union_prov = {
        "wiki_source_mode": "cache_union_reconstruction",
        "contributing_chunk_keys": [["2025-10-05", "2025-10-31"], ["2025-09-01", "2025-10-04"]],
        "contributing_content_hashes": ["aaa111", "bbb222"],
        "contributing_retrieval_timestamps": ["2026-07-10T00:00:00+00:00", "2026-07-15T00:00:00+00:00"],
        "reconstructed_at_utc": "2026-08-02T00:00:00+00:00",
        "date_count": len(daily_rows),
    }

    def fake_get_daily(ticker, article, start, end, watermark, cache_df=None, remaining_budget_s=None):
        return {
            "chunk_results": [{
                "chunk_start": start.isoformat(), "chunk_end": end.isoformat(),
                "source": "cache_union_reconstruction", "status": "ok",
                "cache_union_provenance": union_prov,
            }],
            "failed_chunks": [], "daily_rows": daily_rows,
        }

    restore = _install_process_ticker_stubs(fake_get_daily)
    try:
        row, _ = panel.process_ticker(None, TICKER, run_ts, wiki_remaining_budget_s=100.0,
                                       watermark_info=_watermark_info(watermark_date))
    finally:
        restore()

    df = pd.DataFrame([row], columns=panel.COLUMN_ORDER)
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "checkpoint.csv")
        df.to_csv(csv_path, index=False)
        reread = pd.read_csv(csv_path)

    original_json = row["wiki_cache_union_provenance_json"]
    reread_json = reread.iloc[0]["wiki_cache_union_provenance_json"]
    check("2a. wiki_cache_union_provenance_json survives CSV round-trip byte-for-byte",
          reread_json == original_json, f"orig={original_json!r}\nreread={reread_json!r}")
    parsed = json.loads(reread_json)
    check("2b. round-tripped JSON re-parses and contains both contributing chunk keys",
          parsed[0]["contributing_chunk_keys"] == union_prov["contributing_chunk_keys"])
    check("2c. wiki_source_mode also survives the round-trip",
          reread.iloc[0]["wiki_source_mode"] == "cache_union_only",
          f"got {reread.iloc[0]['wiki_source_mode']!r}")


# === 3. Mixed exact-cache/fresh/union input is labeled mixed with all components present ===
def test_3_mixed_labeling():
    chunk_results = [
        {"chunk_start": "2025-10-01", "chunk_end": "2025-10-31", "source": "cache", "status": "ok"},
        {"chunk_start": "2025-11-01", "chunk_end": "2025-11-30", "source": "fetch", "status": "ok"},
        {"chunk_start": "2025-12-01", "chunk_end": "2025-12-31", "source": "cache_union_reconstruction",
         "status": "ok", "cache_union_provenance": {
             "wiki_source_mode": "cache_union_reconstruction",
             "contributing_chunk_keys": [["2025-11-30", "2025-12-31"]],
             "contributing_content_hashes": ["ccc333"],
             "contributing_retrieval_timestamps": ["2026-07-01T00:00:00+00:00"],
             "reconstructed_at_utc": "2026-08-02T00:00:00+00:00", "date_count": 31,
         }},
    ]
    prov = panel._wiki_source_provenance(chunk_results)
    check("3a. mixed sources -> wiki_source_mode == 'mixed'", prov["wiki_source_mode"] == "mixed")
    components = json.loads(prov["wiki_source_components_json"])
    check("3b. all three components present in wiki_source_components_json",
          components == ["cache", "cache_union_reconstruction", "fetch"], f"got {components!r}")
    check("3c. wiki_cache_union_used True with count 1",
          prov["wiki_cache_union_used"] is True and prov["wiki_cache_union_chunk_count"] == 1)


# === 4. Union provenance survives a later successful second pass ===
def test_4_union_survives_second_pass():
    # run_bounded_second_pass()'s successful-recovery path calls
    # write_chunk_to_cache() internally, which reads/writes the module-level
    # wiki_transport.CACHE_PATH directly -- NOT the in-memory cache_df this
    # test constructs. MUST redirect to a temp path for the duration of this
    # test, or the Sep-chunk fetch this test deliberately makes succeed
    # would write fabricated rows into the real operational cache.
    tmp = _use_temp_cache()
    try:
        _test_4_body()
    finally:
        _restore_cache_path(tmp)


def _test_4_body():
    watermark = date(2026, 8, 1)

    # First pass: one chunk (Nov) is a genuine exact-key cache hit, one
    # chunk (Oct, via a differently-keyed cache group spanning Sep25-Oct31
    # -- a superset that still fully covers the requested Oct1-31 range
    # under a DIFFERENT boundary key) is a union reconstruction, and one
    # chunk (Sep) fails outright (404) and gets queued for the second pass
    # since no cached data covers Sep1-24 at all.
    cache_df = _cache_df(
        _cache_group(TICKER, ARTICLE, date(2025, 11, 1), date(2025, 11, 30)),
        _cache_group(TICKER, ARTICLE, date(2025, 9, 25), date(2025, 10, 31)),
    )

    def first_pass_fetch(article, start, end, timeout_s=None):
        return {"status": "http_error", "http_status": 404, "items": [], "network_elapsed_s": 0.01}

    first = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, date(2025, 9, 1), date(2025, 11, 30), watermark,
        cache_df=cache_df, fetch_fn=first_pass_fetch)
    check("4a. precondition: first pass has exactly one failed (Sep) chunk queued",
          len(first["failed_chunks"]) == 1, f"got {len(first['failed_chunks'])}")
    check("4b. precondition: first pass recovered a cache_union_reconstruction chunk",
          any(cr.get("source") == "cache_union_reconstruction" and cr.get("status") == "ok"
              for cr in first["chunk_results"]))

    # Second pass: the Sep chunk now succeeds via a real fetch.
    sep_rows = [{"date": d.strftime("%Y%m%d"), "pageviews": 500 + d.day}
                for d in _date_range(date(2025, 9, 1), date(2025, 9, 30))]

    def second_pass_fetch(article, start, end, timeout_s=None):
        return {"status": "ok", "http_status": 200, "items": sep_rows, "network_elapsed_s": 0.01,
                "url": "https://example.org/api"}

    second = wiki_transport.run_bounded_second_pass(
        first["failed_chunks"], remaining_budget_s=100.0, watermark=watermark, fetch_fn=second_pass_fetch)
    check("4c. precondition: second pass recovered the Sep chunk",
          TICKER in second["recovered"] and len(second["recovered"][TICKER]) == 30)

    # Exactly the merge main() performs: preserved first-pass chunk_results
    # (including the union hit) + normalized second-pass results.
    ticker_second_pass_results = [{**cr, "source": "fetch"} for cr in second["chunk_results"] if cr["ticker"] == TICKER]
    combined_chunk_results = first["chunk_results"] + ticker_second_pass_results
    all_daily_rows = first["daily_rows"] + second["recovered"].get(TICKER, [])

    row = _fresh_row()
    panel._finalize_wiki_row(row, ARTICLE, all_daily_rows, watermark, combined_chunk_results)

    check("4d. final wiki_source_mode == 'mixed' (cache + cache_union_reconstruction + fetch)",
          row.get("wiki_source_mode") == "mixed", f"got {row.get('wiki_source_mode')!r}")
    check("4e. wiki_cache_union_used remains True after second pass",
          row.get("wiki_cache_union_used") is True)
    components = json.loads(row.get("wiki_source_components_json") or "[]")
    check("4f. all three components present after second pass", components == ["cache", "cache_union_reconstruction", "fetch"],
          f"got {components!r}")
    union_prov = json.loads(row.get("wiki_cache_union_provenance_json") or "[]")
    check("4g. cache-union provenance itself (contributing chunk keys) preserved after second pass",
          len(union_prov) == 1 and union_prov[0]["contributing_chunk_keys"] == [["2025-09-25", "2025-10-31"]],
          f"got {union_prov!r}")


# === 5. recent_last_known_good behavior remains unchanged ===
def test_5_recent_last_known_good_unchanged():
    watermark = date(2026, 8, 1)
    # Simulate the exact main()-loop fallback branch: _finalize_wiki_row()
    # runs first (deriving provenance from whatever normally-successful
    # chunks exist for this ticker -- here, none, since the only chunk
    # failed and is being rescued by the fallback), then
    # row.update(fallback_info["provenance"]) overrides wiki_status/
    # wiki_source_mode exactly as production code does, then the
    # additive component-merge step runs.
    fallback_provenance = {
        "wiki_status": "complete_recent_cache_fallback",
        "wiki_source_mode": "recent_last_known_good",
        "wiki_fresh_request_failed": True,
        "wiki_fresh_failure_category": "http_error",
        "wiki_fresh_failure_http_status": 404,
        "wiki_fallback_retrieved_at_utc": "2026-07-31T12:00:00+00:00",
        "wiki_cache_age_hours": 18.5,
        "wiki_effective_data_end": "2026-07-31",
        "wiki_cache_content_hash": "deadbeef",
    }
    daily_rows = _daily_rows(watermark, 15 * 7)
    chunk_results_all_failed = [
        {"chunk_start": "2026-08-01", "chunk_end": "2026-08-01", "source": "fetch", "status": "http_error"},
    ]

    row = _fresh_row()
    panel._finalize_wiki_row(row, ARTICLE, daily_rows, watermark, chunk_results_all_failed)
    row.update(fallback_provenance)
    existing_components = json.loads(row.get("wiki_source_components_json") or "[]")
    merged_components = sorted(set(existing_components) | {"recent_last_known_good"})
    row["wiki_source_components_json"] = json.dumps(merged_components, sort_keys=True)

    check("5a. wiki_status == 'complete_recent_cache_fallback' (fallback's own provenance wins)",
          row["wiki_status"] == "complete_recent_cache_fallback")
    check("5b. wiki_source_mode == 'recent_last_known_good' (not overridden by the new derivation)",
          row["wiki_source_mode"] == "recent_last_known_good")
    check("5c. fallback-specific fields (age/effective_data_end/hash) untouched",
          row["wiki_cache_age_hours"] == 18.5 and row["wiki_effective_data_end"] == "2026-07-31"
          and row["wiki_cache_content_hash"] == "deadbeef")
    check("5d. 'recent_last_known_good' additively present in wiki_source_components_json",
          "recent_last_known_good" in json.loads(row["wiki_source_components_json"]))


# === 6. Two genuinely separate cached chunk groups jointly reconstruct one interval ===
def test_6_two_separate_groups_jointly_reconstruct():
    chunk_start, chunk_end = date(2025, 10, 1), date(2025, 10, 31)
    watermark = date(2026, 8, 1)
    group_a = _cache_group(TICKER, ARTICLE, date(2025, 9, 20), date(2025, 10, 15))   # covers Oct 1-15
    group_b = _cache_group(TICKER, ARTICLE, date(2025, 10, 16), date(2025, 11, 5))   # covers Oct 16-31
    cache_df = _cache_df(group_a, group_b)
    result = wiki_transport.attempt_cache_union_reconstruction(cache_df, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("6a. two disjoint cached groups jointly covering the interval produce a hit", result["hit"] is True)
    keys = set(tuple(k) for k in result["provenance"]["contributing_chunk_keys"])
    check("6b. BOTH contributing groups are represented in provenance",
          (date(2025, 9, 20).isoformat(), date(2025, 10, 15).isoformat()) in keys
          and (date(2025, 10, 16).isoformat(), date(2025, 11, 5).isoformat()) in keys,
          f"got {keys!r}")
    check("6c. exactly 31 reconstructed rows (full October)", len(result["rows"]) == 31)


# === 7. Wall-clock independence uses nondegenerate data, equal non-null z-scores ===
def test_7_wall_clock_independence_nondegenerate_nonnull():
    watermark_date = date(2026, 8, 1)
    daily_rows = _daily_rows(watermark_date, 15 * 7)  # nondegenerate: varying pageviews
    chunk_results = [{"chunk_start": daily_rows[0]["date"], "chunk_end": daily_rows[-1]["date"],
                       "source": "fetch", "status": "ok"}]

    zscores = []
    for _ in range(2):  # simulates two different wall-clock runs -- no wall-clock input exists anymore
        row = _fresh_row()
        panel._finalize_wiki_row(row, ARTICLE, daily_rows, watermark_date, chunk_results)
        zscores.append(row.get("wiki_zscore"))

    check("7a. both computed z-scores are non-null", all(z is not None for z in zscores), f"{zscores!r}")
    check("7b. both computed z-scores are exactly equal", zscores[0] == zscores[1], f"{zscores!r}")


# === 8. Exact-snapshot and union-snapshot paths calculate equal, non-null z-scores ===
def test_8_exact_vs_union_equal_nonnull_zscores():
    # A single CLOSED historical month chunk (watermark is one day past
    # chunk_end, so is_open_chunk() is False and union reconstruction is
    # attempted for the union path), exercised via both an exact-key cache
    # hit and a cache-union reconstruction -- then padded with identical
    # extra prior-week history (bypassing the transport entirely for the
    # padding, since only the target month itself needs to differ in
    # sourcing mechanism) so there is enough data for a real, non-null
    # z-score, not just enough for the narrower daily-rows-equality check
    # test_phase2_wiki_cache_union.py's test 8 already covers.
    chunk_start, chunk_end = date(2025, 10, 6), date(2025, 10, 31)
    watermark = date(2025, 11, 1)

    exact_group = _cache_group(TICKER, ARTICLE, chunk_start, chunk_end)
    cache_df_exact = _cache_df(exact_group)
    result_exact = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, chunk_start, chunk_end, watermark, cache_df=cache_df_exact,
        fetch_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch")))

    union_group = _cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31))
    cache_df_union = _cache_df(union_group)
    result_union = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, chunk_start, chunk_end, watermark, cache_df=cache_df_union,
        fetch_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch")))

    check("8-precondition. both paths produced identical daily rows for the target month",
          {r["date"]: r["pageviews"] for r in result_exact["daily_rows"]}
          == {r["date"]: r["pageviews"] for r in result_union["daily_rows"]})

    extra_history = _daily_rows(chunk_start - timedelta(days=1), 14 * 7)  # 14 weeks ending the day before the chunk

    row_exact = _fresh_row()
    panel._finalize_wiki_row(row_exact, ARTICLE, extra_history + result_exact["daily_rows"], watermark,
                              result_exact["chunk_results"])
    row_union = _fresh_row()
    panel._finalize_wiki_row(row_union, ARTICLE, extra_history + result_union["daily_rows"], watermark,
                              result_union["chunk_results"])

    check("8a. exact-snapshot path produces a non-null z-score", row_exact.get("wiki_zscore") is not None)
    check("8b. union-snapshot path produces a non-null z-score", row_union.get("wiki_zscore") is not None)
    check("8c. both paths produce the EXACT SAME z-score value (not merely equal daily rows)",
          row_exact.get("wiki_zscore") == row_union.get("wiki_zscore"),
          f"exact={row_exact.get('wiki_zscore')!r} union={row_union.get('wiki_zscore')!r}")
    check("8d. sanity: the two paths used different source mechanisms",
          row_exact.get("wiki_source_mode") == "exact_cache_only"
          and row_union.get("wiki_source_mode") == "cache_union_only",
          f"exact_mode={row_exact.get('wiki_source_mode')!r} union_mode={row_union.get('wiki_source_mode')!r}")


# === 9. Different configured article titles sharing ticker/chunk boundaries cannot interfere ===
def test_9_different_article_titles_cannot_interfere():
    chunk_start, chunk_end = date(2025, 10, 6), date(2025, 10, 31)
    watermark = date(2026, 8, 1)
    shared_start, shared_end = date(2025, 10, 5), date(2025, 10, 31)   # SAME boundary key for both articles

    correct_pageviews = {d: 7000 + d.day for d in _date_range(shared_start, shared_end)}
    wrong_pageviews = {d: 1 for d in _date_range(shared_start, shared_end)}  # deliberately distinct values

    correct_group = _cache_group(TICKER, ARTICLE, shared_start, shared_end, pageviews_by_date=correct_pageviews)
    wrong_article_group = _cache_group(TICKER, "Old_Superseded_Article", shared_start, shared_end,
                                        pageviews_by_date=wrong_pageviews)
    cache_df = _cache_df(correct_group, wrong_article_group)

    result = wiki_transport.attempt_cache_union_reconstruction(cache_df, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("9a. reconstruction succeeds using only the correct article's group", result["hit"] is True)
    rows_by_date = {r["date"]: r["pageviews"] for r in result["rows"]}
    check("9b. reconstructed pageviews match the CORRECT article's values, not the other article's",
          all(rows_by_date[d.strftime("%Y%m%d")] == correct_pageviews[d]
              for d in _date_range(chunk_start, chunk_end)),
          f"sample got={list(rows_by_date.items())[:3]}")
    check("9c. none of the wrong-article's distinct sentinel values (1) leaked into the result",
          all(v != 1 for v in rows_by_date.values()))


if __name__ == "__main__":
    test_1_union_only_not_labeled_fresh()
    test_2_provenance_survives_serialization()
    test_3_mixed_labeling()
    test_4_union_survives_second_pass()
    test_5_recent_last_known_good_unchanged()
    test_6_two_separate_groups_jointly_reconstruct()
    test_7_wall_clock_independence_nondegenerate_nonnull()
    test_8_exact_vs_union_equal_nonnull_zscores()
    test_9_different_article_titles_cannot_interfere()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL WIKI SOURCE-PROVENANCE TESTS PASSED (9 required scenarios)")
        sys.exit(0)
