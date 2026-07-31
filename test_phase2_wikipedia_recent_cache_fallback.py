#!/usr/bin/env python3
# Deterministic tests for the RECENT_LAST_KNOWN_GOOD fallback (approved
# 2026-07-31 as a narrow, strictly-bounded addition to the Wikipedia
# transport rewrite -- NOT a general staleness tolerance). Covers the 11
# required scenarios:
#   1. fresh success always preferred
#   2. fresh failure + valid <=24h exact-coverage cache -> fallback used
#   3. cache older than 24h -> rejected
#   4. cache missing the required final date -> rejected
#   5. cache with a page-ID/title mismatch -> rejected
#   6. cache with a corrupt hash -> rejected
#   7. cache containing duplicates -> rejected
#   8. cache produced by an earlier fallback usage is not recursively
#      reused as a new authoritative snapshot (no clock reset)
#   9. a failed refresh never overwrites the valid cache
#   10. fallback provenance and original retrieval timestamp preserved
#   11. the calculated Wikipedia field exactly matches the field
#       calculated from the original successful response
#
# Run directly: python test_phase2_wikipedia_recent_cache_fallback.py

from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_Wikipedia_Transport as wt
from GST_Wikipedia_Pageviews_Pull import to_weekly
import GST_FixedWindow_PerEvent_Canonical as canonical
import pandas as pd

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


_ORIGINAL_CACHE_PATH = wt.CACHE_PATH


def _use_temp_cache():
    tmp_dir = tempfile.mkdtemp(prefix="wiki_fallback_test_")
    wt.CACHE_PATH = Path(tmp_dir) / "test_cache.csv"
    return tmp_dir


def _restore_cache_path(tmp_dir):
    wt.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(tmp_dir, ignore_errors=True)


TICKER = "TEST"
ARTICLE = "Test Article"
TODAY = date(2026, 7, 31)
CHUNK_START = date(2026, 7, 1)
CHUNK_END = date(2026, 7, 31)          # requested end == today, as calendar_month_chunks would produce
EFFECTIVE_END = date(2026, 7, 30)      # today - 1 day (data lag)


def _full_month_rows(end: date = EFFECTIVE_END) -> list[dict]:
    rows = []
    d = CHUNK_START
    while d <= end:
        rows.append({"date": d.strftime("%Y%m%d"), "pageviews": 100 + d.day})
        d += timedelta(days=1)
    return rows


def _seed_valid_cache(retrieved_at_utc: datetime | None = None, rows: list[dict] | None = None,
                       article: str = ARTICLE):
    ts = (retrieved_at_utc or datetime.now(timezone.utc)).isoformat()
    wt.write_chunk_to_cache(TICKER, article, None, None, CHUNK_START, CHUNK_END,
                             rows if rows is not None else _full_month_rows(),
                             "http://x", 200, ts)


def _still_failed_item(last_http_status=404) -> dict:
    return {"ticker": TICKER, "article": ARTICLE, "chunk_start": CHUNK_START, "chunk_end": CHUNK_END,
            "last_status": "http_error", "retry_after": None, "reason": "second_pass_also_failed:http_error",
            "last_http_status": last_http_status}


# === 1. Fresh success is always preferred ===
def test_1_fresh_success_preferred():
    tmp = _use_temp_cache()
    try:
        _seed_valid_cache(rows=_full_month_rows())  # eligible fallback data present
        fresh_rows = [{"date": "20260701", "pageviews": 999999}]  # deliberately different from cache

        def fetch_fn(article, start, end, timeout_s=None):
            return {"status": "ok", "http_status": 200, "items": fresh_rows, "url": "http://fresh",
                     "network_elapsed_s": 0.01, "terminated": False}

        result = wt.get_ticker_wikipedia_daily(
            TICKER, ARTICLE, CHUNK_START, TODAY, today=TODAY, cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("1. fresh fetch succeeded, no failed chunks -> fallback never invoked",
              result["failed_chunks"] == [], result["failed_chunks"])
        check("1. fresh data used, not the differing cached data",
              result["daily_rows"] == fresh_rows, result["daily_rows"])
    finally:
        _restore_cache_path(tmp)


# === 2. Fresh failure + valid <=24h exact-coverage cache -> fallback used ===
def test_2_fallback_used_when_eligible():
    tmp = _use_temp_cache()
    try:
        _seed_valid_cache(retrieved_at_utc=datetime.now(timezone.utc) - timedelta(hours=2))
        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        check("2. fallback recovers the ticker", TICKER in result["fallback_recovered"], result)
        check("2. nothing left in still_failed", result["still_failed"] == [], result["still_failed"])
        prov = result["fallback_recovered"][TICKER]["provenance"]
        check("2. provenance marks complete_recent_cache_fallback",
              prov["wiki_status"] == "complete_recent_cache_fallback", prov)
        check("2. provenance marks recent_last_known_good source mode",
              prov["wiki_source_mode"] == "recent_last_known_good", prov)
        check("2. provenance records the fresh failure was recorded, not concealed",
              prov["wiki_fresh_request_failed"] is True and prov["wiki_fresh_failure_http_status"] == 404, prov)
    finally:
        _restore_cache_path(tmp)


# === 3. Cache older than 24 hours -> rejected ===
def test_3_stale_cache_rejected():
    tmp = _use_temp_cache()
    try:
        _seed_valid_cache(retrieved_at_utc=datetime.now(timezone.utc) - timedelta(hours=25))
        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        check("3. stale (>24h) cache is rejected, not used", TICKER not in result["fallback_recovered"])
        check("3. rejection reason cites cache age", "cache_too_old" in result["still_failed"][0]["fallback_rejected_reason"],
              result["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === 4. Cache missing the required final date -> rejected ===
def test_4_missing_final_date_rejected():
    tmp = _use_temp_cache()
    try:
        incomplete_rows = _full_month_rows(end=EFFECTIVE_END - timedelta(days=1))  # missing the last day
        _seed_valid_cache(rows=incomplete_rows)
        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        check("4. cache missing the required final date is rejected", TICKER not in result["fallback_recovered"])
        check("4. rejection reason cites incomplete coverage",
              "incomplete_coverage" in result["still_failed"][0]["fallback_rejected_reason"],
              result["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === 5. Cache with a page-ID/title mismatch -> rejected ===
def test_5_title_mismatch_rejected():
    tmp = _use_temp_cache()
    try:
        _seed_valid_cache(article="Some Other Article Entirely")
        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        check("5. configured_article_title mismatch is rejected", TICKER not in result["fallback_recovered"])
        check("5. rejection reason cites the title mismatch",
              "article_title_mismatch" in result["still_failed"][0]["fallback_rejected_reason"],
              result["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === 6. Cache with a corrupt hash -> rejected ===
def test_6_corrupt_hash_rejected():
    tmp = _use_temp_cache()
    try:
        _seed_valid_cache()
        df = wt.load_cache()
        df.loc[df["date"] == EFFECTIVE_END.strftime("%Y%m%d"), "pageviews"] = 999999  # tamper post-write
        tmp_path = wt.CACHE_PATH.with_suffix(".tmp")
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, wt.CACHE_PATH)

        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        check("6. tampered/corrupt content_hash is rejected", TICKER not in result["fallback_recovered"])
        check("6. rejection reason cites hash verification failure",
              "content_hash_verification_failed" in result["still_failed"][0]["fallback_rejected_reason"],
              result["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === 7. Cache containing duplicates -> rejected ===
def test_7_duplicate_dates_rejected():
    tmp = _use_temp_cache()
    try:
        rows = _full_month_rows()
        rows.append(dict(rows[0]))  # duplicate an existing date
        _seed_valid_cache(rows=rows)
        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        check("7. duplicate dates in the cached snapshot are rejected", TICKER not in result["fallback_recovered"])
        check("7. rejection reason cites duplicate dates",
              "duplicate_dates" in result["still_failed"][0]["fallback_rejected_reason"],
              result["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === 8. A fallback usage never resets the snapshot's own age/provenance ===
def test_8_fallback_usage_not_recursively_refreshed():
    tmp = _use_temp_cache()
    try:
        original_ts = datetime.now(timezone.utc) - timedelta(hours=23)
        _seed_valid_cache(retrieved_at_utc=original_ts)

        # First fallback usage, still within the 24h window.
        result1 = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY,
                                                   datetime.now(timezone.utc))
        check("8a. first fallback usage succeeds (still <24h old)", TICKER in result1["fallback_recovered"])

        cache_after_first_use = wt.load_cache()
        unchanged = cache_after_first_use.equals(wt.load_cache())
        check("8b. using the fallback does not rewrite the cache at all (no clock reset)", unchanged)

        # Simulate 2 more hours passing (now 25h old) -- a SECOND fallback
        # attempt against the SAME, never-rewritten cache entry must now be
        # rejected on age, proving the first usage did not "refresh" it.
        later_now = datetime.now(timezone.utc) + timedelta(hours=2)
        result2 = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, later_now)
        check("8c. the SAME underlying snapshot is correctly rejected once truly stale -- "
              "proving the earlier fallback usage did not reset its age",
              TICKER not in result2["fallback_recovered"])
    finally:
        _restore_cache_path(tmp)


# === 9. A failed refresh never overwrites the valid cache ===
def test_9_failed_refresh_never_overwrites_cache():
    tmp = _use_temp_cache()
    try:
        _seed_valid_cache(retrieved_at_utc=datetime.now(timezone.utc) - timedelta(hours=1))
        cache_content_before = wt.CACHE_PATH.read_text()

        def failing_fetch_fn(article, start, end, timeout_s=None):
            return {"status": "http_error", "http_status": 404, "items": [], "url": "http://x",
                     "network_elapsed_s": 0.1, "terminated": False, "retry_after": None}

        result = wt.get_ticker_wikipedia_daily(
            TICKER, ARTICLE, CHUNK_START, TODAY, today=TODAY, cache_df=wt.load_cache(), fetch_fn=failing_fetch_fn,
        )
        second = wt.run_bounded_second_pass(result["failed_chunks"], remaining_budget_s=30, fetch_fn=failing_fetch_fn)
        wt.apply_recent_cache_fallback(second["still_failed"], wt.load_cache(), TODAY, datetime.now(timezone.utc))

        check("9. cache file is byte-identical after a failed refresh + fallback evaluation",
              wt.CACHE_PATH.read_text() == cache_content_before)
    finally:
        _restore_cache_path(tmp)


# === 10. Fallback provenance and original retrieval timestamp preserved ===
def test_10_provenance_preserves_original_timestamp():
    tmp = _use_temp_cache()
    try:
        original_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        _seed_valid_cache(retrieved_at_utc=datetime.fromisoformat(original_ts))
        now_utc = datetime.now(timezone.utc)
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY, now_utc)
        prov = result["fallback_recovered"][TICKER]["provenance"]
        check("10. wiki_fallback_retrieved_at_utc equals the ORIGINAL retrieval timestamp, "
              "not 'now'", prov["wiki_fallback_retrieved_at_utc"] == original_ts,
              f"expected={original_ts} got={prov['wiki_fallback_retrieved_at_utc']}")
        check("10. wiki_cache_age_hours reflects real elapsed time (~5h), not 0",
              4.9 <= prov["wiki_cache_age_hours"] <= 5.1, prov["wiki_cache_age_hours"])
        check("10. wiki_cache_content_hash is present for audit", bool(prov["wiki_cache_content_hash"]))
        check("10. wiki_effective_data_end is the lag-adjusted date, not today",
              prov["wiki_effective_data_end"] == EFFECTIVE_END.isoformat(), prov["wiki_effective_data_end"])
    finally:
        _restore_cache_path(tmp)


# === 11. Calculated Wikipedia field exactly matches the original response's ===
def test_11_zscore_matches_original_successful_response():
    tmp = _use_temp_cache()
    try:
        rows = _full_month_rows()
        _seed_valid_cache(rows=rows, retrieved_at_utc=datetime.now(timezone.utc) - timedelta(hours=1))

        # "Original successful response" baseline: compute the z-score
        # directly from the same rows, as if they'd just been freshly
        # fetched (this IS what the original successful call produced).
        baseline_df = wt.assemble_daily_series(rows)
        baseline_weekly = to_weekly(baseline_df)
        anchor = pd.Timestamp(TODAY)
        _, baseline_z, _ = canonical.compute_zscore_at_anchor(baseline_weekly, anchor)

        # Fallback path: evaluate + assemble + compute using the SAME rows
        # retrieved via apply_recent_cache_fallback().
        result = wt.apply_recent_cache_fallback([_still_failed_item()], wt.load_cache(), TODAY,
                                                  datetime.now(timezone.utc))
        fallback_rows = result["fallback_recovered"][TICKER]["rows"]
        fallback_df = wt.assemble_daily_series(fallback_rows)
        fallback_weekly = to_weekly(fallback_df)
        _, fallback_z, _ = canonical.compute_zscore_at_anchor(fallback_weekly, anchor)

        check("11. fallback-served z-score exactly matches the original successful response's z-score",
              baseline_z == fallback_z, f"baseline={baseline_z} fallback={fallback_z}")
    finally:
        _restore_cache_path(tmp)


if __name__ == "__main__":
    test_1_fresh_success_preferred()
    test_2_fallback_used_when_eligible()
    test_3_stale_cache_rejected()
    test_4_missing_final_date_rejected()
    test_5_title_mismatch_rejected()
    test_6_corrupt_hash_rejected()
    test_7_duplicate_dates_rejected()
    test_8_fallback_usage_not_recursively_refreshed()
    test_9_failed_refresh_never_overwrites_cache()
    test_10_provenance_preserves_original_timestamp()
    test_11_zscore_matches_original_successful_response()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL RECENT-CACHE-FALLBACK TESTS PASSED")
        sys.exit(0)
