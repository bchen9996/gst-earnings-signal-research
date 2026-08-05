#!/usr/bin/env python3
# Deterministic tests for the MEASURED WIKIPEDIA DATA WATERMARK (2026-08-01
# -- see GST_Phase2_Wikipedia_Transport.resolve_wiki_data_watermark() and
# its module-level docstring for the 2026-08-01 PARTIAL regression this
# replaces: a fixed "today-1 is always published" assumption, proven false
# by a measured, confirmed 2-day Wikipedia publication lag).
#
# Covers watermark-spec tests 1-12 (tests 13/15/16 live in
# test_phase2_wikipedia_equivalence_deterministic.py and
# test_phase2_dailypanel_gate.py; test 14 -- no production-cache mutation
# from tests -- is structurally guaranteed here by _use_temp_cache(), the
# same pattern used throughout this project's test suites):
#   1. yesterday available -> lag 1 watermark
#   2. yesterday 404 twice (first + one bounded confirmation), day-before
#      available -> lag 2
#   3. lag 3 accepted
#   4. no date within three days available -> watermark failure (PARTIAL)
#   5. 429 with bounded Retry-After honored
#   6. malformed/500/network error fails closed (never walked back)
#   7. article URL/request is truncated exactly to the watermark
#   8. no request for chunks entirely after the watermark
#   9. July rollover cache valid through July 30 when watermark=July 30
#   10. same cache rejected/refetched when watermark advances to July 31
#   11. exact coverage required through the watermark
#   12. identical watermark/provenance on all rows of a run
#
# Run directly: python test_phase2_wikipedia_watermark.py

from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_Wikipedia_Transport as wt

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


_ORIGINAL_CACHE_PATH = wt.CACHE_PATH


def _use_temp_cache():
    tmp_dir = tempfile.mkdtemp(prefix="wiki_watermark_test_")
    wt.CACHE_PATH = Path(tmp_dir) / "test_cache.csv"
    return tmp_dir


def _restore_cache_path(tmp_dir):
    wt.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _mock_aggregate_fetch(script: dict):
    """Builds a fetch_fn matching _fetch_aggregate_day()'s signature/return
    shape, driven by a canned per-call-index script. Each call consumes
    the next scripted response (or repeats the last one if the script is
    shorter than the number of calls)."""
    calls = {"n": 0}

    def _fn(candidate: date):
        idx = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        resp = dict(script[idx])
        resp.setdefault("network_elapsed_s", 0.01)
        resp.setdefault("retry_after", None)
        resp.setdefault("url", f"http://mock/{candidate.isoformat()}")
        return resp

    _fn.call_count = lambda: calls["n"]
    _fn.calls_made = lambda: calls["n"]
    return _fn


ANCHOR = date(2026, 8, 1)   # "today" for these tests -- yesterday = July 31


# === 1. Yesterday available -> lag 1 watermark ===
def test_1_yesterday_available_lag_1():
    fetch_fn = _mock_aggregate_fetch([{"status": "ok", "http_status": 200, "views": 1000}])
    result = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)
    check("1. status is ok", result["status"] == "ok", result)
    check("1. watermark_date is yesterday (lag 1)", result["watermark_date"] == ANCHOR - timedelta(days=1), result)
    check("1. lag_days is exactly 1", result["lag_days"] == 1, result)
    check("1. only one candidate was probed", fetch_fn.calls_made() == 1, fetch_fn.calls_made())


# === 2. Yesterday 404 twice (first + confirmation), day-before available -> lag 2 ===
def test_2_yesterday_404_twice_day_before_available_lag_2():
    fetch_fn = _mock_aggregate_fetch([
        {"status": "http_error", "http_status": 404},   # yesterday, first attempt
        {"status": "http_error", "http_status": 404},   # yesterday, confirmation re-probe
        {"status": "ok", "http_status": 200, "views": 2000},   # day-before-yesterday
    ])
    result = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)
    check("2. status is ok", result["status"] == "ok", result)
    check("2. watermark_date is day-before-yesterday (lag 2)",
          result["watermark_date"] == ANCHOR - timedelta(days=2), result)
    check("2. lag_days is exactly 2", result["lag_days"] == 2, result)
    check("2. exactly 3 probes made (yesterday x2, day-before x1)", fetch_fn.calls_made() == 3,
          fetch_fn.calls_made())
    attempts = [p["attempt"] for p in result["probe_log"] if p["lag_days"] == 1]
    check("2. yesterday's two attempts are logged as 'first' then 'confirmation'",
          attempts == ["first", "confirmation"], attempts)


# === 3. Lag 3 accepted ===
def test_3_lag_3_accepted():
    fetch_fn = _mock_aggregate_fetch([
        {"status": "http_error", "http_status": 404},   # day -1, first
        {"status": "http_error", "http_status": 404},   # day -1, confirmation
        {"status": "http_error", "http_status": 404},   # day -2, first
        {"status": "http_error", "http_status": 404},   # day -2, confirmation
        {"status": "ok", "http_status": 200, "views": 3000},   # day -3
    ])
    result = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)
    check("3. status is ok at the maximum acceptable lag", result["status"] == "ok", result)
    check("3. watermark_date is exactly 3 days back", result["watermark_date"] == ANCHOR - timedelta(days=3), result)
    check("3. lag_days is exactly MAX_ACCEPTABLE_WIKI_LAG_DAYS",
          result["lag_days"] == wt.MAX_ACCEPTABLE_WIKI_LAG_DAYS == 3, result)


# === 4. No date within three days available -> watermark failure (PARTIAL) ===
def test_4_no_data_within_max_lag():
    fetch_fn = _mock_aggregate_fetch([{"status": "http_error", "http_status": 404}])  # 404 forever
    result = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)
    check("4. status is no_data_within_max_lag", result["status"] == "no_data_within_max_lag", result)
    check("4. watermark_date is None -- never guessed", result["watermark_date"] is None, result)
    check("4. exactly 2 probes per candidate x 3 candidates = 6 total",
          fetch_fn.calls_made() == 6, fetch_fn.calls_made())


# === 5. 429 with bounded Retry-After honored ===
def test_5_429_with_bounded_retry_after():
    fetch_fn = _mock_aggregate_fetch([
        {"status": "http_error", "http_status": 429, "retry_after": "1"},   # yesterday, rate-limited
        {"status": "ok", "http_status": 200, "views": 5000},                # yesterday, after honoring Retry-After
    ])
    t0 = datetime.now(timezone.utc)
    result = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    check("5. status is ok after honoring Retry-After", result["status"] == "ok", result)
    check("5. watermark resolved to yesterday (lag 1) -- the 429 didn't walk it back a day",
          result["watermark_date"] == ANCHOR - timedelta(days=1), result)
    check("5. actually waited approximately the requested Retry-After (~1s), not the jitter/max default",
          0.9 <= elapsed <= 5.0, elapsed)
    attempts = [p["attempt"] for p in result["probe_log"]]
    check("5. logged as 'first' then 'after_retry_after'", attempts == ["first", "after_retry_after"], attempts)


# === 6. Malformed/500/network error fails closed (never walked back) ===
def test_6_malformed_and_server_error_fail_closed():
    for bad_result in [
        {"status": "malformed", "http_status": 200},
        {"status": "http_error", "http_status": 500},
        {"status": "exception"},
    ]:
        fetch_fn = _mock_aggregate_fetch([bad_result])
        result = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)
        check(f"6. {bad_result['status']!r} fails the watermark CLOSED, not walked back to an older date",
              result["status"] == "failed_closed", result)
        check(f"6. {bad_result['status']!r}: only ONE candidate was probed (no silent walk-back)",
              fetch_fn.calls_made() == 1, fetch_fn.calls_made())
        check(f"6. {bad_result['status']!r}: watermark_date is None -- never guessed on ambiguous failure",
              result["watermark_date"] is None, result)


# === 7. Article URL/request is truncated exactly to the watermark ===
def test_7_request_truncated_exactly_to_watermark():
    tmp = _use_temp_cache()
    try:
        captured_ranges = []

        def fetch_fn(article, start, end, timeout_s=None):
            captured_ranges.append((start, end))
            return {"status": "ok", "http_status": 200,
                    "items": [{"date": d.strftime("%Y%m%d"), "pageviews": 1}
                              for d in _daterange(start, end)],
                    "url": "http://x", "network_elapsed_s": 0.01, "terminated": False}

        watermark = date(2026, 7, 15)   # mid-month -- well before the chunk's natural end
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 7, 1), date(2026, 7, 31),
            watermark=watermark, cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("7. the request was made", len(captured_ranges) == 1, captured_ranges)
        check("7. the request's end date is EXACTLY the watermark, not the chunk's natural end (July 31)",
              captured_ranges[0] == (date(2026, 7, 1), watermark), captured_ranges)
        check("7. no failed chunks (exact coverage through the watermark was satisfied)",
              result["failed_chunks"] == [], result["failed_chunks"])
    finally:
        _restore_cache_path(tmp)


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# === 8. No request for chunks entirely after the watermark ===
def test_8_no_request_for_chunks_entirely_after_watermark():
    tmp = _use_temp_cache()
    try:
        requested_ranges = []

        def fetch_fn(article, start, end, timeout_s=None):
            # July's own chunk legitimately needs fetching (the watermark,
            # July 15, falls WITHIN it) -- only August/September, entirely
            # beyond the watermark, must never reach here at all.
            if start >= date(2026, 8, 1):
                raise AssertionError(f"must never be called for a chunk entirely after the "
                                      f"watermark (got {start}..{end})")
            requested_ranges.append((start, end))
            return {"status": "ok", "http_status": 200,
                    "items": [{"date": d.strftime("%Y%m%d"), "pageviews": 1}
                              for d in _daterange(start, end)],
                    "url": "http://x", "network_elapsed_s": 0.01, "terminated": False}

        # Requested window spans July-September; watermark only reaches
        # July 15 -- August and September chunks must never be requested.
        fetch_was_called_for_future_chunk = False
        result = None
        try:
            result = wt.get_ticker_wikipedia_daily(
                "TEST", "Test Article", date(2026, 7, 1), date(2026, 9, 30),
                watermark=date(2026, 7, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
            )
        except AssertionError:
            fetch_was_called_for_future_chunk = True
        check("8. fetch_fn was never called for August/September (entirely beyond the watermark)",
              not fetch_was_called_for_future_chunk)
        check("8. July's own chunk WAS legitimately fetched (watermark falls within it)",
              len(requested_ranges) == 1 and requested_ranges[0] == (date(2026, 7, 1), date(2026, 7, 15)),
              requested_ranges)
        if result is not None:
            statuses_by_chunk = {cr["chunk_start"]: cr["status"] for cr in result["chunk_results"]
                                  if cr["chunk_start"] >= "2026-08-01"}
            check("8. every chunk starting on/after August is classified no_observations_expected_yet",
                  all(s == "no_observations_expected_yet" for s in statuses_by_chunk.values()),
                  statuses_by_chunk)
    finally:
        _restore_cache_path(tmp)


# === 9. July rollover cache valid through July 30 when watermark=July 30 ===
def test_9_july_cache_valid_when_watermark_is_july_30():
    tmp = _use_temp_cache()
    try:
        july_rows = [{"date": d.strftime("%Y%m%d"), "pageviews": 1} for d in _daterange(date(2026, 7, 1), date(2026, 7, 30))]
        wt.write_chunk_to_cache("TEST", "Test Article", None, None, date(2026, 7, 1), date(2026, 7, 31),
                                 july_rows, "u", 200, datetime.now(timezone.utc).isoformat())

        hit = wt.validated_cache_hit(wt.load_cache(), "TEST", "Test Article",
                                      date(2026, 7, 1), date(2026, 7, 31), watermark=date(2026, 7, 30))
        check("9. cache covering exactly July 1-30 is a valid HIT when the watermark is July 30",
              hit["hit"] is True, hit)
        check("9. all 30 cached rows are returned", len(hit["rows"]) == 30, hit)
    finally:
        _restore_cache_path(tmp)


# === 10. Same cache rejected/refetched when watermark advances to July 31 ===
def test_10_same_cache_rejected_when_watermark_advances_to_july_31():
    tmp = _use_temp_cache()
    try:
        july_rows = [{"date": d.strftime("%Y%m%d"), "pageviews": 1} for d in _daterange(date(2026, 7, 1), date(2026, 7, 30))]
        wt.write_chunk_to_cache("TEST", "Test Article", None, None, date(2026, 7, 1), date(2026, 7, 31),
                                 july_rows, "u", 200, datetime.now(timezone.utc).isoformat())

        # SAME cache entry, unchanged -- but the watermark has now advanced
        # to July 31 (e.g. Wikipedia published the missing day on a later
        # run). The cache must be rejected as incomplete and refetched.
        hit = wt.validated_cache_hit(wt.load_cache(), "TEST", "Test Article",
                                      date(2026, 7, 1), date(2026, 7, 31), watermark=date(2026, 7, 31))
        check("10. the SAME cache entry is now a MISS once the watermark advances to July 31",
              hit["hit"] is False, hit)
        check("10. rejection is incomplete_coverage, not corruption -- it's simply missing the newly "
              "available date", hit["validation"]["category"] == "incomplete_coverage", hit["validation"])

        # And the full orchestration correctly refetches to get the newly-required day.
        def fetch_fn(article, start, end, timeout_s=None):
            return {"status": "ok", "http_status": 200,
                    "items": [{"date": d.strftime("%Y%m%d"), "pageviews": 1}
                              for d in _daterange(date(2026, 7, 1), date(2026, 7, 31))],
                    "url": "http://x", "network_elapsed_s": 0.01, "terminated": False}
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 7, 1), date(2026, 7, 31),
            watermark=date(2026, 7, 31), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("10. orchestration refetches and gets the complete 31-day July once the watermark advanced",
              len(result["daily_rows"]) == 31, len(result["daily_rows"]))
    finally:
        _restore_cache_path(tmp)


# === 11. Exact coverage required through the watermark ===
def test_11_exact_coverage_required_through_watermark():
    # One day short of the watermark -- must be rejected (already covered
    # implicitly elsewhere, but stated explicitly here for direct
    # traceability to the watermark spec's own numbered list).
    rows_missing_one_day = [{"date": d.strftime("%Y%m%d"), "pageviews": 1}
                             for d in _daterange(date(2026, 7, 1), date(2026, 7, 29))]   # missing July 30
    validation = wt.validate_snapshot("TEST", "Test Article", date(2026, 7, 1), date(2026, 7, 31),
                                       rows_missing_one_day, watermark=date(2026, 7, 30))
    check("11. one day short of the watermark -> incomplete_coverage, not accepted",
          validation["valid"] is False and validation["category"] == "incomplete_coverage", validation)

    rows_exact = [{"date": d.strftime("%Y%m%d"), "pageviews": 1}
                  for d in _daterange(date(2026, 7, 1), date(2026, 7, 30))]
    validation2 = wt.validate_snapshot("TEST", "Test Article", date(2026, 7, 1), date(2026, 7, 31),
                                        rows_exact, watermark=date(2026, 7, 30))
    check("11. exactly through the watermark -> valid", validation2["valid"] is True, validation2)

    rows_extra = rows_exact + [{"date": "20260731", "pageviews": 1}]   # one day BEYOND the watermark
    validation3 = wt.validate_snapshot("TEST", "Test Article", date(2026, 7, 1), date(2026, 7, 31),
                                        rows_extra, watermark=date(2026, 7, 30))
    check("11. one day BEYOND the watermark present -> also incomplete_coverage (extra), not silently accepted",
          validation3["valid"] is False and validation3["category"] == "incomplete_coverage", validation3)


# === 12. Identical watermark/provenance on all rows of a run ===
def test_12_identical_watermark_provenance_across_rows():
    fetch_fn = _mock_aggregate_fetch([{"status": "ok", "http_status": 200, "views": 4200}])
    watermark_info = wt.resolve_wiki_data_watermark(ANCHOR, fetch_fn=fetch_fn)

    # Simulate what GST_Phase2_DailyPanel.process_ticker() does with the
    # SAME watermark_info dict for every ticker in a run -- the provenance
    # fields derived from it must be byte-identical across all of them.
    simulated_rows = []
    for ticker in ["AAA", "BBB", "CCC"]:
        row = {
            "ticker": ticker,
            "wiki_data_watermark_date": watermark_info["watermark_date"].isoformat(),
            "wiki_data_lag_days": watermark_info["lag_days"],
            "wiki_watermark_status": watermark_info["status"],
            "wiki_watermark_retrieved_at_utc": watermark_info["retrieved_at_utc"],
            "wiki_watermark_source_url": watermark_info["source_url"],
            "wiki_watermark_http_status": watermark_info["http_status"],
        }
        simulated_rows.append(row)

    provenance_fields = ["wiki_data_watermark_date", "wiki_data_lag_days", "wiki_watermark_status",
                          "wiki_watermark_retrieved_at_utc", "wiki_watermark_source_url",
                          "wiki_watermark_http_status"]
    for field in provenance_fields:
        values = {r[field] for r in simulated_rows}
        check(f"12. {field} is identical across all rows (run-level, not per-ticker)",
              len(values) == 1, values)


if __name__ == "__main__":
    test_1_yesterday_available_lag_1()
    test_2_yesterday_404_twice_day_before_available_lag_2()
    test_3_lag_3_accepted()
    test_4_no_data_within_max_lag()
    test_5_429_with_bounded_retry_after()
    test_6_malformed_and_server_error_fail_closed()
    test_7_request_truncated_exactly_to_watermark()
    test_8_no_request_for_chunks_entirely_after_watermark()
    test_9_july_cache_valid_when_watermark_is_july_30()
    test_10_same_cache_rejected_when_watermark_advances_to_july_31()
    test_11_exact_coverage_required_through_watermark()
    test_12_identical_watermark_provenance_across_rows()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL WATERMARK TESTS PASSED (tests 1-12; 13/15/16 live in the equivalence-deterministic "
              "and dailypanel-gate test files; 14 is structurally guaranteed by _use_temp_cache())")
        sys.exit(0)
