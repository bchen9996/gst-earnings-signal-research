#!/usr/bin/env python3
# Deterministic tests for the 2026-08-02 closed-historical-interval
# cache-union reconstruction: attempt_cache_union_reconstruction() and its
# wiring into get_ticker_wikipedia_daily(). No network access, no
# operational cache access -- every cache_df here is a small synthetic
# in-memory DataFrame built by this file, never Phase2_Wikipedia_Cache.csv.
#
# Run directly: python test_phase2_wiki_cache_union.py

from __future__ import annotations
import sys
import os
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_Wikipedia_Transport as wiki_transport

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


TICKER = "AAPL"
ARTICLE = "Apple_Inc."


def _date_range(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def _cache_group(ticker: str, article: str, chunk_start: date, chunk_end: date,
                  pageviews_by_date: dict[date, int] | None = None,
                  http_status: int = 200, last_verified_utc: str = "2026-07-15T00:00:00+00:00",
                  bad_hash: bool = False) -> list[dict]:
    """Builds a fully-formed, internally hash-consistent cache group (one
    row per date in [chunk_start, chunk_end]) matching CACHE_COLUMNS,
    exactly as write_chunk_to_cache() would have produced it -- but purely
    in memory, never touching CACHE_PATH."""
    dates = _date_range(chunk_start, chunk_end)
    pageviews_by_date = pageviews_by_date or {}
    daily_rows = [{"date": d.strftime("%Y%m%d"), "pageviews": pageviews_by_date.get(d, 1000 + d.day)}
                  for d in dates]
    content_hash = wiki_transport.compute_chunk_hash(daily_rows)
    if bad_hash:
        content_hash = "0" * 16
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


# === 1. Complete union acceptance ===
def test_1_complete_union_accepted():
    # Needed: Oct 6..Oct 31 (a rolling-window's new chunk_start). Cache
    # only has yesterday's chunk boundary, Oct 5..Oct 31 -- no exact-key
    # row for (Oct 6, Oct 31), but every needed date is present within
    # that one older, hash-consistent group.
    chunk_start, chunk_end = date(2025, 10, 6), date(2025, 10, 31)
    watermark = date(2026, 8, 1)
    cache_df = _cache_df(_cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31)))
    result = wiki_transport.attempt_cache_union_reconstruction(cache_df, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("1a. complete coverage from a different chunk-boundary key is accepted", result["hit"] is True)
    check("1b. every needed date present in the reconstructed rows",
          {r["date"] for r in result["rows"]} == {d.strftime("%Y%m%d") for d in _date_range(chunk_start, chunk_end)})
    check("1c. provenance names wiki_source_mode=cache_union_reconstruction",
          result["provenance"]["wiki_source_mode"] == "cache_union_reconstruction")
    check("1d. provenance names the contributing chunk key",
          (date(2025, 10, 5).isoformat(), date(2025, 10, 31).isoformat()) in result["provenance"]["contributing_chunk_keys"])


# === 2. One-date-missing rejection ===
def test_2_one_date_missing_rejected():
    chunk_start, chunk_end = date(2025, 10, 6), date(2025, 10, 31)
    watermark = date(2026, 8, 1)
    # Older group covers Oct 5..Oct 30 only -- missing Oct 31.
    cache_df = _cache_df(_cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 30)))
    result = wiki_transport.attempt_cache_union_reconstruction(cache_df, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("2. a single missing date rejects the whole union (no partial coverage accepted)",
          result["hit"] is False)
    check("2b. rejection reason names incomplete coverage",
          result["provenance"] is not None and result["provenance"].get("rejected_reason") == "incomplete_union_coverage")


# === 3. Conflicting-value rejection ===
def test_3_conflicting_value_rejected():
    chunk_start, chunk_end = date(2025, 10, 6), date(2025, 10, 31)
    watermark = date(2026, 8, 1)
    group_a = _cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31),
                            pageviews_by_date={date(2025, 10, 15): 5000})
    group_b = _cache_group(TICKER, ARTICLE, date(2025, 10, 1), date(2025, 10, 20),
                            pageviews_by_date={date(2025, 10, 15): 9999})  # disagrees with group_a
    cache_df = _cache_df(group_a, group_b)
    result = wiki_transport.attempt_cache_union_reconstruction(cache_df, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("3. two cached groups disagreeing on the same date's pageviews rejects the whole reconstruction",
          result["hit"] is False)
    check("3b. rejection reason names the conflict",
          result["provenance"] is not None and result["provenance"].get("rejected_reason") == "conflicting_pageviews_across_cached_chunks")


# === 4. Identity/hash rejection ===
def test_4_identity_hash_rejected():
    chunk_start, chunk_end = date(2025, 10, 6), date(2025, 10, 31)
    watermark = date(2026, 8, 1)
    tampered_group = _cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31), bad_hash=True)
    cache_df = _cache_df(tampered_group)
    result = wiki_transport.attempt_cache_union_reconstruction(cache_df, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("4a. a group whose stored hash doesn't match its own recomputed hash contributes nothing",
          result["hit"] is False)

    wrong_article_group = _cache_group(TICKER, "Some_Other_Article", date(2025, 10, 5), date(2025, 10, 31))
    cache_df2 = _cache_df(wrong_article_group)
    result2 = wiki_transport.attempt_cache_union_reconstruction(cache_df2, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("4b. a group under a different configured_article_title (identity mismatch) contributes nothing",
          result2["hit"] is False)

    non_200_group = _cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31), http_status=404)
    cache_df3 = _cache_df(non_200_group)
    result3 = wiki_transport.attempt_cache_union_reconstruction(cache_df3, TICKER, ARTICLE, chunk_start, chunk_end, watermark)
    check("4c. a group without HTTP-200 provenance contributes nothing",
          result3["hit"] is False)


# === 5. Watermark exclusion ===
def test_5_watermark_exclusion():
    # required_data_end() at the real call site would already truncate
    # req_end to the watermark, but this function is tested here with an
    # req_end that (incorrectly, hypothetically) extends past the
    # watermark, to prove the function's OWN independent exclusion holds
    # regardless of what the caller passes.
    chunk_start = date(2026, 7, 20)
    req_end_past_watermark = date(2026, 8, 5)
    watermark = date(2026, 8, 1)
    cache_df = _cache_df(_cache_group(TICKER, ARTICLE, date(2026, 7, 20), date(2026, 8, 5)))
    result = wiki_transport.attempt_cache_union_reconstruction(
        cache_df, TICKER, ARTICLE, chunk_start, req_end_past_watermark, watermark)
    check("5. an interval extending past the watermark is rejected (incomplete once post-watermark dates are excluded)",
          result["hit"] is False)


# === 6. Current-month non-use (open chunk never attempts union) ===
def test_6_open_chunk_never_uses_union():
    watermark = date(2026, 8, 1)
    open_chunk_start, open_chunk_end = date(2026, 8, 1), date(2026, 8, 31)
    check("6. is_open_chunk() correctly identifies the current/open chunk relative to the watermark",
          wiki_transport.is_open_chunk(open_chunk_start, open_chunk_end, watermark) is True)

    called = []

    def _fake_fetch(article, start, end, timeout_s=None):
        called.append((start, end))
        return {"status": "http_error", "http_status": 404, "items": [], "network_elapsed_s": 0.01}

    # Cache has full coverage for the open chunk's dates under a
    # different key -- if the open-chunk exemption were broken, this
    # would produce a union hit and fetch_fn would never be called.
    cache_df = _cache_df(_cache_group(TICKER, ARTICLE, date(2026, 7, 25), date(2026, 8, 1)))
    result = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, date(2026, 8, 1), date(2026, 8, 31), watermark, cache_df=cache_df, fetch_fn=_fake_fetch)
    union_used = any(cr.get("source") == "cache_union_reconstruction" for cr in result["chunk_results"])
    check("6b. the open/current chunk never uses cache-union reconstruction, even with full day-level coverage available",
          not union_used)
    check("6c. the open chunk still goes through the normal live-first fetch path", len(called) >= 1)


# === 7. Zero-network-call recovery ===
def test_7_zero_network_call_recovery():
    watermark = date(2026, 8, 1)
    closed_start, closed_end = date(2025, 10, 6), date(2025, 10, 31)
    cache_df = _cache_df(_cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31)))

    def _fail_if_called(article, start, end, timeout_s=None):
        raise AssertionError("fetch_fn must never be called when a complete cache union is available")

    result = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, closed_start, closed_end, watermark, cache_df=cache_df, fetch_fn=_fail_if_called)
    check("7a. no network call is made when a complete closed-interval union is available",
          not any(cr.get("source") == "fetch" for cr in result["chunk_results"]))
    check("7b. the chunk is recovered via cache_union_reconstruction",
          any(cr.get("source") == "cache_union_reconstruction" and cr.get("status") == "ok"
              for cr in result["chunk_results"]))
    check("7c. no failed_chunks recorded for the recovered interval", result["failed_chunks"] == [])


# === 8. Z-score equivalence against an exact-boundary snapshot ===
def test_8_zscore_equivalence_vs_exact_boundary():
    watermark = date(2026, 8, 1)

    # Scenario A: an exact-boundary cache hit for (Oct 6, Oct 31).
    exact_group = _cache_group(TICKER, ARTICLE, date(2025, 10, 6), date(2025, 10, 31))
    cache_df_exact = _cache_df(exact_group)
    result_exact = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, date(2025, 10, 6), date(2025, 10, 31), watermark,
        cache_df=cache_df_exact, fetch_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch")))

    # Scenario B: the SAME underlying daily values, but cached only under
    # a different (older) chunk boundary -- forcing a union reconstruction
    # for the identical requested interval.
    union_group = _cache_group(TICKER, ARTICLE, date(2025, 10, 5), date(2025, 10, 31))
    cache_df_union = _cache_df(union_group)
    result_union = wiki_transport.get_ticker_wikipedia_daily(
        TICKER, ARTICLE, date(2025, 10, 6), date(2025, 10, 31), watermark,
        cache_df=cache_df_union, fetch_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch")))

    rows_exact = {r["date"]: r["pageviews"] for r in result_exact["daily_rows"]}
    rows_union = {r["date"]: r["pageviews"] for r in result_union["daily_rows"]}
    check("8. exact-boundary snapshot and cache-union reconstruction produce byte-identical daily values "
          "for the same requested interval",
          rows_exact == rows_union, f"exact={rows_exact}\nunion={rows_union}")


if __name__ == "__main__":
    test_1_complete_union_accepted()
    test_2_one_date_missing_rejected()
    test_3_conflicting_value_rejected()
    test_4_identity_hash_rejected()
    test_5_watermark_exclusion()
    test_6_open_chunk_never_uses_union()
    test_7_zero_network_call_recovery()
    test_8_zscore_equivalence_vs_exact_boundary()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL CACHE-UNION RECONSTRUCTION TESTS PASSED (8 required scenarios)")
        sys.exit(0)
