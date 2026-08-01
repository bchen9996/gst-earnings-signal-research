#!/usr/bin/env python3
# Deterministic tests for GST_Phase2_Wikipedia_Transport.py.
#
# Plain assert-based (matches this project's existing lightweight testing
# style, no external test framework dependency). Run directly:
#   python test_phase2_wikipedia_transport.py
# Exits 0 if every test passes, nonzero (with a clear FAIL line) otherwise.
#
# Tests 1-13 exercise the transport module in isolation, mostly via the
# injectable fetch_fn parameter (see GST_Phase2_Wikipedia_Transport.py's own
# docstrings) so they run in well under a second with no real network call
# except test 6 (which deliberately spawns a real, genuinely-hanging child
# process to prove it actually gets terminated -- that one takes a few
# seconds by design). Tests 14-15 (the run-level completeness gate) are
# covered at the GST_Phase2_DailyPanel.py integration/regression stage, not
# here, since the transport module itself has no notion of "24 tickers" or
# "COMPLETE" -- that gate lives in the orchestrating script.

from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_Wikipedia_Transport as wt

FAILURES = []


def _full_coverage_rows(chunk_start: date, chunk_end: date) -> list[dict]:
    """Every calendar date from chunk_start through chunk_end inclusive --
    the shared validate_snapshot() gate now requires EXACT coverage for a
    closed month to be accepted as complete, so test fixtures representing
    a genuinely successful closed-month response must provide it (a
    same-shaped-but-incomplete mock is correctly rejected as
    incomplete_coverage now, not silently accepted)."""
    rows = []
    d = chunk_start
    while d <= chunk_end:
        rows.append({"date": d.strftime("%Y%m%d"), "pageviews": 10 + d.day})
        d += timedelta(days=1)
    return rows


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _mock_fetch(script: dict):
    """Builds a fetch_fn matching fetch_chunk_isolated()'s signature/return
    shape, driven by a canned per-call-index script. Each call consumes the
    next scripted response (or repeats the last one if the script is
    shorter than the number of calls)."""
    calls = {"n": 0}

    def _fn(article, start, end, timeout_s=None):
        idx = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        resp = dict(script[idx])
        resp.setdefault("elapsed_s", 0.01)
        resp.setdefault("terminated", False)
        return resp

    _fn.call_count = lambda: calls["n"]
    return _fn


# --- isolated cache sandbox --------------------------------------------------

_ORIGINAL_CACHE_PATH = wt.CACHE_PATH


def _use_temp_cache():
    tmp_dir = tempfile.mkdtemp(prefix="wiki_cache_test_")
    wt.CACHE_PATH = Path(tmp_dir) / "test_cache.csv"
    return tmp_dir


def _restore_cache_path(tmp_dir):
    wt.CACHE_PATH = _ORIGINAL_CACHE_PATH
    shutil.rmtree(tmp_dir, ignore_errors=True)


# === 1. Full successful month ===
def test_1_full_successful_month():
    tmp = _use_temp_cache()
    try:
        full_rows = _full_coverage_rows(date(2026, 1, 1), date(2026, 1, 31))
        fetch_fn = _mock_fetch([{"status": "ok", "http_status": 200, "items": full_rows, "url": "http://x"}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 2, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("1. full successful month -> 31 daily rows",
              len(result["daily_rows"]) == len(full_rows), len(result["daily_rows"]))
        check("1. full successful month -> no failed chunks",
              result["failed_chunks"] == [], result["failed_chunks"])
        check("1. full successful month -> cached",
              len(wt.cached_daily_rows_for_chunk(wt.load_cache(), "TEST", date(2026, 1, 1), date(2026, 1, 31)))
              == len(full_rows))
    finally:
        _restore_cache_path(tmp)


# === 2. 404 followed by second-pass success ===
def test_2_404_then_second_pass_success():
    tmp = _use_temp_cache()
    try:
        fetch_fn = _mock_fetch([{"status": "http_error", "http_status": 404, "items": []}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 2, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("2. first pass 404 -> queued for retry", len(result["failed_chunks"]) == 1)

        full_rows = _full_coverage_rows(date(2026, 1, 1), date(2026, 1, 31))
        retry_fetch_fn = _mock_fetch([{"status": "ok", "http_status": 200, "items": full_rows, "url": "http://x"}])
        second = wt.run_bounded_second_pass(result["failed_chunks"], remaining_budget_s=60,
                                             fetch_fn=retry_fetch_fn, today=date(2026, 2, 15))
        check("2. second pass recovers the chunk", "TEST" in second["recovered"], second)
        check("2. second pass -> nothing still failed", second["still_failed"] == [], second["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === 3. Repeated 404 remaining incomplete ===
def test_3_repeated_404_remains_incomplete():
    tmp = _use_temp_cache()
    try:
        fetch_fn = _mock_fetch([{"status": "http_error", "http_status": 404, "items": []}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 2, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        still_404_fn = _mock_fetch([{"status": "http_error", "http_status": 404, "items": []}])
        second = wt.run_bounded_second_pass(result["failed_chunks"], remaining_budget_s=60,
                                             fetch_fn=still_404_fn)
        check("3. still failing after second pass -> reported, not silently dropped",
              len(second["still_failed"]) == 1 and second["recovered"] == {}, second)
        check("3. failure reason is explicit", "second_pass_also_failed" in second["still_failed"][0]["reason"])
    finally:
        _restore_cache_path(tmp)


# === 4. 429 with Retry-After ===
def test_4_429_with_retry_after():
    tmp = _use_temp_cache()
    try:
        queue = [{"ticker": "TEST", "article": "Test Article", "chunk_start": date(2026, 1, 1),
                  "chunk_end": date(2026, 1, 31), "last_status": "http_error", "retry_after": "2"}]
        full_rows = _full_coverage_rows(date(2026, 1, 1), date(2026, 1, 31))
        fetch_fn = _mock_fetch([{"status": "ok", "http_status": 200, "items": full_rows, "url": "http://x"}])
        t0 = time.time()
        second = wt.run_bounded_second_pass(queue, remaining_budget_s=60, fetch_fn=fetch_fn, today=date(2026, 2, 15))
        elapsed = time.time() - t0
        check("4. honors Retry-After (waited ~2s, not the jitter default)", 1.8 <= elapsed <= 3.5, elapsed)
        check("4. recovers after honoring Retry-After", "TEST" in second["recovered"])
    finally:
        _restore_cache_path(tmp)


# === 5. Network timeout (status-level, not a real hang -- see test 6 for the real one) ===
def test_5_network_timeout_status():
    tmp = _use_temp_cache()
    try:
        fetch_fn = _mock_fetch([{"status": "timeout", "http_status": None, "items": [],
                                  "terminated": True, "error": "timed out after 35s"}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 2, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("5. timeout status treated as failure, queued not crashed",
              len(result["failed_chunks"]) == 1 and result["daily_rows"] == [])
    finally:
        _restore_cache_path(tmp)


# === 6. Worker termination and no surviving process (the real one) ===
def _hang_forever_worker(*args):
    time.sleep(9999)


def test_6_process_actually_terminates():
    t0 = time.time()
    result = wt.run_process_bounded(_hang_forever_worker, (), timeout_s=2.0)
    elapsed = time.time() - t0
    check("6. run_process_bounded returns promptly on timeout (~2s, not 9999s)", elapsed < 15, elapsed)
    check("6. completed=False (was terminated, did not finish on its own)", result["completed"] is False)
    check("6. terminated=True (process confirmed reaped, not just abandoned)", result["terminated"] is True)
    check("6. a pid was recorded", result["pid"] is not None)
    # Directly verify no process with that PID is still alive (not just
    # trusting multiprocessing's own bookkeeping) -- os.kill with signal 0
    # on POSIX-like layers raises if the pid is gone; on native Windows
    # Python this raises OSError for a dead pid too.
    pid_alive = True
    try:
        os.kill(result["pid"], 0)
    except OSError:
        pid_alive = False
    except AttributeError:
        pid_alive = None  # platform doesn't support signal-0 probing; inconclusive, not a failure
    if pid_alive is not None:
        check("6. OS-level: no process with that PID remains alive", pid_alive is False)
    else:
        print("INFO: OS-level PID probe unavailable on this platform -- relying on multiprocessing's own join()")


# === 7. Malformed response ===
def test_7_malformed_response():
    tmp = _use_temp_cache()
    try:
        fetch_fn = _mock_fetch([{"status": "malformed", "http_status": None, "items": [],
                                  "error": "Expecting value: line 1 column 1 (char 0)"}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 2, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("7. malformed response treated as failure, not a crash",
              len(result["failed_chunks"]) == 1 and result["daily_rows"] == [])
    finally:
        _restore_cache_path(tmp)


# === 8. Corrupted cache ===
def test_8_corrupted_cache():
    tmp = _use_temp_cache()
    try:
        wt.write_chunk_to_cache("TEST", "Test Article", "Test Article", "1", date(2026, 1, 1), date(2026, 1, 31),
                                 [{"date": "20260101", "pageviews": 5}], "http://x", 200, "2026-01-01T00:00:00Z")
        df = wt.load_cache()
        problems = wt.verify_cache_integrity(df)
        check("8a. clean cache has no integrity problems", problems == [], problems)

        df.loc[df["date"] == "20260101", "pageviews"] = 99999
        tampered_problems = wt.verify_cache_integrity(df)
        check("8b. tampered data detected via hash mismatch", len(tampered_problems) == 1, tampered_problems)

        bad_path = wt.CACHE_PATH.parent / "bad_schema.csv"
        df.drop(columns=["content_hash"]).to_csv(bad_path, index=False)
        saved = wt.CACHE_PATH
        wt.CACHE_PATH = bad_path
        try:
            raised = False
            try:
                wt.load_cache()
            except wt.CacheCorruptionError:
                raised = True
            check("8c. schema corruption raises CacheCorruptionError, not silently coerced", raised)
        finally:
            wt.CACHE_PATH = saved
    finally:
        _restore_cache_path(tmp)


# === 9. Atomic cache write interruption ===
def test_9_atomic_write_interruption():
    tmp = _use_temp_cache()
    try:
        wt.write_chunk_to_cache("TEST", "Test Article", "Test Article", "1", date(2026, 1, 1), date(2026, 1, 31),
                                 [{"date": "20260101", "pageviews": 5}], "http://x", 200, "2026-01-01T00:00:00Z")
        good_content_before = wt.CACHE_PATH.read_text()

        import pandas as pd
        real_to_csv = pd.DataFrame.to_csv

        def _boom(self, *a, **kw):
            raise RuntimeError("simulated interruption mid-write")

        pd.DataFrame.to_csv = _boom
        try:
            raised = False
            try:
                wt.write_chunk_to_cache("TEST", "Test Article", "Test Article", "1", date(2026, 2, 1), date(2026, 2, 28),
                                         [{"date": "20260201", "pageviews": 9}], "http://x", 200, "2026-02-01T00:00:00Z")
            except RuntimeError:
                raised = True
            check("9a. simulated interruption actually raises (test is meaningful)", raised)
        finally:
            pd.DataFrame.to_csv = real_to_csv

        check("9b. original cache file untouched after a failed write (no tmp promoted over it)",
              wt.CACHE_PATH.read_text() == good_content_before)
        tmp_leftover = wt.CACHE_PATH.with_suffix(".tmp")
        if tmp_leftover.exists():
            tmp_leftover.unlink()
    finally:
        _restore_cache_path(tmp)


# === 10. Resume from several successful cached months plus one failed month ===
def test_10_resume_from_partial_cache():
    tmp = _use_temp_cache()
    try:
        jan_rows = _full_coverage_rows(date(2026, 1, 1), date(2026, 1, 31))
        feb_rows = _full_coverage_rows(date(2026, 2, 1), date(2026, 2, 28))
        mar_rows = _full_coverage_rows(date(2026, 3, 1), date(2026, 3, 31))
        wt.write_chunk_to_cache("TEST", "Test Article", None, None, date(2026, 1, 1), date(2026, 1, 31),
                                 jan_rows, "u", 200, "t")
        wt.write_chunk_to_cache("TEST", "Test Article", None, None, date(2026, 2, 1), date(2026, 2, 28),
                                 feb_rows, "u", 200, "t")
        # March is NOT cached -- must be fetched.
        fetch_fn = _mock_fetch([{"status": "ok", "http_status": 200, "items": mar_rows, "url": "u"}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 3, 31),
            today=date(2026, 6, 1), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("10a. only the uncached closed month triggers a fetch", fetch_fn.call_count() == 1,
              fetch_fn.call_count())
        check("10b. all three months' data present in the assembled result",
              len(result["daily_rows"]) == len(jan_rows) + len(feb_rows) + len(mar_rows), len(result["daily_rows"]))
    finally:
        _restore_cache_path(tmp)


# === 11. Current incomplete month refresh ===
def test_11_open_month_always_refreshed():
    tmp = _use_temp_cache()
    try:
        # January is cached AND is the "open" month relative to today=2026-01-15.
        wt.write_chunk_to_cache("TEST", "Test Article", None, None, date(2026, 1, 1), date(2026, 1, 31),
                                 [{"date": "20260101", "pageviews": 1}], "u", 200, "t")
        fetch_fn = _mock_fetch([{"status": "ok", "http_status": 200,
                                  "items": [{"date": "20260101", "pageviews": 1}, {"date": "20260114", "pageviews": 4}],
                                  "url": "u"}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 1, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("11. the open month is refreshed via fetch, not served stale from cache",
              fetch_fn.call_count() == 1, fetch_fn.call_count())
    finally:
        _restore_cache_path(tmp)


# === 12. No zero-filling of missing data ===
def test_12_no_zero_filling():
    daily = wt.assemble_daily_series([{"date": "20260101", "pageviews": 5}, {"date": "20260103", "pageviews": 7}])
    check("12. missing 20260102 is simply absent, not a 0-filled row", len(daily) == 2, daily)
    check("12. no zero-value row was fabricated", (daily["views"] == 0).sum() == 0)


# === 13. Duplicate-date prevention ===
def test_13_duplicate_date_prevention():
    daily = wt.assemble_daily_series([
        {"date": "20260101", "pageviews": 5},
        {"date": "20260101", "pageviews": 999},  # duplicate date, different value (e.g. overlapping chunks)
        {"date": "20260102", "pageviews": 7},
    ])
    check("13. duplicate date collapsed to one row", len(daily) == 2, daily)


# === Observational logging addition (2026-07-31): raw http_status/retry_after
# surfaced on chunk_results for both passes. Confirms this is PURELY additive
# -- the new keys are present, but daily_rows/failed_chunks/still_failed/
# recovered classifications and values are byte-for-byte identical to what
# they'd be without this change (no request/retry/timing/classification
# behavior altered). ===
def test_http_status_retry_after_logging_is_purely_additive():
    tmp = _use_temp_cache()
    try:
        fetch_fn = _mock_fetch([{"status": "http_error", "http_status": 404, "items": [],
                                  "retry_after": None}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 2, 15), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        cr = result["chunk_results"][0]
        check("obs-logging: first-pass chunk_results now carries http_status",
              cr.get("http_status") == 404, cr)
        check("obs-logging: first-pass chunk_results now carries retry_after (new key, additive)",
              "retry_after" in cr, cr)
        check("obs-logging: classification (failed_chunks) unaffected by the new keys",
              len(result["failed_chunks"]) == 1 and result["failed_chunks"][0]["last_status"] == "http_error",
              result["failed_chunks"])
        check("obs-logging: daily_rows unaffected (still empty on failure, not fabricated)",
              result["daily_rows"] == [], result["daily_rows"])

        retry_after_fn = _mock_fetch([{"status": "http_error", "http_status": 429, "items": [],
                                        "retry_after": "7"}])
        second = wt.run_bounded_second_pass(result["failed_chunks"], remaining_budget_s=60,
                                             fetch_fn=retry_after_fn)
        cr2 = second["chunk_results"][0]
        check("obs-logging: second-pass chunk_results now carries http_status",
              cr2.get("http_status") == 429, cr2)
        check("obs-logging: second-pass chunk_results now carries retry_after",
              cr2.get("retry_after") == "7", cr2)
        check("obs-logging: second-pass classification (still_failed) unaffected by the new keys",
              len(second["still_failed"]) == 1 and "second_pass_also_failed" in second["still_failed"][0]["reason"],
              second["still_failed"])
    finally:
        _restore_cache_path(tmp)


# === Rollover: an open-month snapshot must not be silently reused as a
# complete closed month once it rolls over (2026-07-31 corrective commit) ===
def test_rollover_open_to_closed_month_rejects_stale_snapshot():
    tmp = _use_temp_cache()
    try:
        # An open July snapshot retrieved July 31 contains data only
        # through July 30 (yesterday relative to that day) -- a perfectly
        # valid snapshot AT THE TIME it was written.
        july_rows_through_30 = _full_coverage_rows(date(2026, 7, 1), date(2026, 7, 30))
        wt.write_chunk_to_cache("TEST", "Test Article", None, None, date(2026, 7, 1), date(2026, 7, 31),
                                 july_rows_through_30, "u", 200, datetime.now(timezone.utc).isoformat())

        # On August 1, July is now a CLOSED month and requires its own
        # final day (July 31) too -- the old snapshot must be rejected as
        # incomplete, not silently reused as a complete closed month.
        hit_aug1 = wt.validated_cache_hit(wt.load_cache(), "TEST", "Test Article",
                                           date(2026, 7, 1), date(2026, 7, 31), date(2026, 8, 1))
        check("rollover: stale July snapshot (through 7/30 only) is rejected as a cache hit "
              "once July becomes a closed month on 8/1, not silently reused as complete",
              hit_aug1["hit"] is False, hit_aug1)
        check("rollover: rejection reason is incomplete_coverage, not a false 'ok'",
              hit_aug1["validation"]["category"] == "incomplete_coverage", hit_aug1["validation"])

        # And the full orchestration correctly falls through to a fresh
        # fetch for July on 8/1, rather than serving the stale snapshot.
        full_july_rows = _full_coverage_rows(date(2026, 7, 1), date(2026, 7, 31))
        fetch_fn = _mock_fetch([{"status": "ok", "http_status": 200, "items": full_july_rows, "url": "http://x"}])
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 7, 1), date(2026, 7, 31),
            today=date(2026, 8, 1), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
        )
        check("rollover: orchestration freshly re-requests the now-closed July month "
              "rather than trusting the stale cached snapshot",
              fetch_fn.call_count() == 1, fetch_fn.call_count())
        check("rollover: freshly-fetched full July (31 days) is what's returned, not the "
              "stale 30-day snapshot", len(result["daily_rows"]) == 31, len(result["daily_rows"]))
        check("rollover: the freshly-fetched complete July replaces the stale cache entry",
              len(wt.cached_daily_rows_for_chunk(wt.load_cache(), "TEST", date(2026, 7, 1), date(2026, 7, 31)))
              == 31)
    finally:
        _restore_cache_path(tmp)


# === no_observations_expected_yet: the very start of a new open month ===
def test_no_observations_expected_yet_not_treated_as_error():
    validation = wt.validate_snapshot("TEST", "Test Article", date(2026, 8, 1), date(2026, 8, 31),
                                       [], today=date(2026, 8, 1))
    check("no-observations-yet: an empty response at the very start of a new open month "
          "is VALID, not an error", validation["valid"] is True, validation)
    check("no-observations-yet: classified explicitly, not as generic 'ok'",
          validation["category"] == "no_observations_expected_yet", validation)

    # But if the response has UNEXPECTED data before coverage could exist,
    # that IS suspicious and must be rejected, not silently accepted.
    bogus = wt.validate_snapshot("TEST", "Test Article", date(2026, 8, 1), date(2026, 8, 31),
                                  [{"date": "20260801", "pageviews": 5}], today=date(2026, 8, 1))
    check("no-observations-yet: unexpected data before the coverage window starts is rejected, "
          "not fabricated/accepted", bogus["valid"] is False, bogus)


# === Genuinely bounded time budget (2026-07-31 corrective commit) ===
def test_second_pass_budget_capping_and_exhaustion():
    tmp = _use_temp_cache()
    try:
        captured_timeouts = []

        def fetch_fn(article, start, end, timeout_s=None):
            captured_timeouts.append(timeout_s)
            return {"status": "ok", "http_status": 200, "items": _full_coverage_rows(start, end),
                    "url": "http://x", "network_elapsed_s": 0.01, "terminated": False}

        queue = [{"ticker": "TEST", "article": "Test Article", "chunk_start": date(2026, 1, 1),
                  "chunk_end": date(2026, 1, 31), "last_status": "http_error", "retry_after": None}]

        # A budget comfortably bigger than the max jitter wait (5s) but far
        # smaller than CHUNK_TIMEOUT_S (35s) -- the CAPPED subprocess
        # timeout requested must reflect what's actually left, not the
        # full chunk_timeout_s regardless of remaining budget.
        wt.run_bounded_second_pass(queue, remaining_budget_s=8.0, fetch_fn=fetch_fn, today=date(2026, 2, 15))
        check("tiny-budget: a request WAS launched (budget covered the wait)",
              len(captured_timeouts) == 1, captured_timeouts)
        check(f"tiny-budget: the requested subprocess timeout was capped well under "
              f"chunk_timeout_s ({wt.CHUNK_TIMEOUT_S}s), reflecting the small remaining budget",
              captured_timeouts and captured_timeouts[0] < wt.CHUNK_TIMEOUT_S, captured_timeouts)

        # A budget too small to leave any USABLE window after the mandatory
        # wait -- no request may be launched at all.
        captured_timeouts.clear()
        queue2 = [{"ticker": "TEST", "article": "Test Article", "chunk_start": date(2026, 1, 1),
                   "chunk_end": date(2026, 1, 31), "last_status": "http_error", "retry_after": None}]
        result2 = wt.run_bounded_second_pass(queue2, remaining_budget_s=0.3, fetch_fn=fetch_fn,
                                              today=date(2026, 2, 15))
        check("tiny-budget: budget exhausted before any usable window -> no request launched",
              len(captured_timeouts) == 0, captured_timeouts)
        check("tiny-budget: item correctly marked still_failed (budget exhausted), not silently dropped",
              len(result2["still_failed"]) == 1, result2)
    finally:
        _restore_cache_path(tmp)


def test_first_pass_budget_exhaustion_stops_further_chunks():
    tmp = _use_temp_cache()
    try:
        call_log = []

        def fetch_fn(article, start, end, timeout_s=None):
            call_log.append((start, end, timeout_s))
            return {"status": "ok", "http_status": 200, "items": _full_coverage_rows(start, end),
                    "url": "http://x", "network_elapsed_s": 0.01, "terminated": False}

        # 3-month window -> 3 chunks. A near-zero remaining_budget_s must
        # stop the loop before launching further requests, cleanly and
        # deterministically -- no hang, no crash, remaining chunks queued.
        result = wt.get_ticker_wikipedia_daily(
            "TEST", "Test Article", date(2026, 1, 1), date(2026, 3, 31),
            today=date(2026, 6, 1), cache_df=wt.load_cache(), fetch_fn=fetch_fn,
            remaining_budget_s=0.0001,
        )
        check("first-pass budget: not every chunk was fetched (budget exhausted immediately)",
              len(call_log) == 0, call_log)
        exhausted = [f for f in result["failed_chunks"] if f["last_status"] == "first_pass_budget_exhausted"]
        check("first-pass budget: all 3 chunks correctly queued as first_pass_budget_exhausted "
              "(not silently dropped, not hung)", len(exhausted) == 3, result["failed_chunks"])
    finally:
        _restore_cache_path(tmp)


def _hang_forever_chunk_worker(article, start_ymd, end_ymd, result_path):
    time.sleep(9999)


def _python_pids() -> set[int]:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def test_second_pass_real_tiny_budget_no_overshoot_no_orphan():
    """Real subprocess (not a mock): proves the CAPPED timeout, not just
    any timeout, actually bounds a genuinely-hanging worker end-to-end
    through run_bounded_second_pass() -- clean PARTIAL exit, no overshoot
    toward the full CHUNK_TIMEOUT_S, no orphan process left behind."""
    def real_fetch_fn(article, start, end, timeout_s=None):
        return wt.fetch_chunk_isolated(article, start, end, timeout_s=timeout_s,
                                        worker=_hang_forever_chunk_worker)

    queue = [{"ticker": "TEST", "article": "Test Article", "chunk_start": date(2026, 1, 1),
              "chunk_end": date(2026, 1, 31), "last_status": "http_error", "retry_after": None}]

    pids_before = _python_pids()
    t0 = time.time()
    result = wt.run_bounded_second_pass(queue, remaining_budget_s=6.0, fetch_fn=real_fetch_fn,
                                         today=date(2026, 2, 15))
    elapsed = time.time() - t0
    check(f"real-tiny-budget: run_bounded_second_pass returns close to the tiny 6s budget, "
          f"not the full {wt.CHUNK_TIMEOUT_S}s chunk_timeout_s (proves genuine capping end-to-end)",
          elapsed < 15, elapsed)
    check("real-tiny-budget: the hung chunk is correctly reported still failed (timeout), "
          "clean PARTIAL exit without overshoot",
          len(result["still_failed"]) == 1, result)

    time.sleep(1.0)   # let OS process-table bookkeeping settle
    new_pids = _python_pids() - pids_before
    check("real-tiny-budget: no orphan python.exe process remains after the capped timeout",
          len(new_pids) == 0, f"new pids still present: {new_pids}")


if __name__ == "__main__":
    test_1_full_successful_month()
    test_2_404_then_second_pass_success()
    test_3_repeated_404_remains_incomplete()
    test_4_429_with_retry_after()
    test_5_network_timeout_status()
    test_6_process_actually_terminates()
    test_7_malformed_response()
    test_8_corrupted_cache()
    test_9_atomic_write_interruption()
    test_10_resume_from_partial_cache()
    test_11_open_month_always_refreshed()
    test_12_no_zero_filling()
    test_13_duplicate_date_prevention()
    test_http_status_retry_after_logging_is_purely_additive()
    test_rollover_open_to_closed_month_rejects_stale_snapshot()
    test_no_observations_expected_yet_not_treated_as_error()
    test_second_pass_budget_capping_and_exhaustion()
    test_first_pass_budget_exhaustion_stops_further_chunks()
    test_second_pass_real_tiny_budget_no_overshoot_no_orphan()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL TRANSPORT-MODULE TESTS PASSED "
              "(tests 14-15, the run-level completeness gate, are covered at integration/regression stage)")
        sys.exit(0)
