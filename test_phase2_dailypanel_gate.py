#!/usr/bin/env python3
# Deterministic tests for GST_Phase2_DailyPanel.is_run_complete() -- the
# run-level completeness gate. Covers tests 14 (final completeness gate) and
# 15 (a PARTIAL run must never be nameable COMPLETE) from the 15-test
# requirement; tests 1-13 (transport-module-level) live in
# test_phase2_wikipedia_transport.py. Importing GST_Phase2_DailyPanel does
# not run the panel -- main() is guarded by if __name__ == "__main__".
#
# Run directly: python test_phase2_dailypanel_gate.py

from __future__ import annotations
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_DailyPanel as panel

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


TICKERS = ["AAA", "BBB", "CCC"]


def _clean_row(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "all_six_fields_clean": True,
        "earnings_status": "ok",
        "days_to_nearest_earnings": 42,
        "retrieval_timestamp_utc": "2026-07-31T00:00:00+00:00",
    }


def _dirty_row(ticker: str, **overrides) -> dict:
    row = _clean_row(ticker)
    row.update(overrides)
    return row


# === 14. Final completeness gate ===
def test_14_final_completeness_gate():
    all_clean = [_clean_row(t) for t in TICKERS]
    check("14a. 3/3 unique tickers, all clean, COMPLETE status, valid watermark -> gate passes",
          panel.is_run_complete(all_clean, "COMPLETE", TICKERS, watermark_status="ok") is True)

    missing = [_clean_row(t) for t in TICKERS[:-1]]
    check("14b. fewer rows than expected tickers -> gate fails",
          panel.is_run_complete(missing, "COMPLETE", TICKERS, watermark_status="ok") is False)

    duplicate = [_clean_row("AAA"), _clean_row("AAA"), _clean_row("CCC")]
    check("14c. duplicate ticker (not 3 unique) -> gate fails, does not silently satisfy count",
          panel.is_run_complete(duplicate, "COMPLETE", TICKERS, watermark_status="ok") is False)

    one_incomplete = [_clean_row("AAA"), _clean_row("BBB"), _dirty_row("CCC", all_six_fields_clean=False)]
    check("14d. one row missing a required field -> gate fails",
          panel.is_run_complete(one_incomplete, "COMPLETE", TICKERS, watermark_status="ok") is False)

    bad_ts = [_clean_row("AAA"), _clean_row("BBB"), _dirty_row("CCC", retrieval_timestamp_utc="not-a-timestamp")]
    check("14e. unparseable retrieval timestamp -> gate fails",
          panel.is_run_complete(bad_ts, "COMPLETE", TICKERS, watermark_status="ok") is False)

    missing_ts = [_clean_row("AAA"), _clean_row("BBB"), _dirty_row("CCC", retrieval_timestamp_utc=None)]
    check("14f. missing retrieval timestamp -> gate fails",
          panel.is_run_complete(missing_ts, "COMPLETE", TICKERS, watermark_status="ok") is False)

    wrong_universe = [_clean_row("AAA"), _clean_row("BBB"), _clean_row("ZZZ")]
    check("14g. rows cover a different ticker set entirely -> gate fails",
          panel.is_run_complete(wrong_universe, "COMPLETE", TICKERS, watermark_status="ok") is False)

    check("14h. gate never raises on a malformed row (empty dict)",
          panel.is_run_complete([{}], "COMPLETE", TICKERS, watermark_status="ok") is False)


# === 15. PARTIAL output never named COMPLETE ===
def test_15_partial_never_named_complete():
    all_clean = [_clean_row(t) for t in TICKERS]
    check("15a. all rows clean but exit_status already PARTIAL (e.g. total-budget stop) -> gate still fails",
          panel.is_run_complete(all_clean, "PARTIAL", TICKERS, watermark_status="ok") is False)

    pending_second_pass = [_clean_row("AAA"), _clean_row("BBB"),
                            _dirty_row("CCC", all_six_fields_clean=False)]
    check("15b. a ticker left in pending_second_pass/incomplete state -> COMPLETE status alone is not enough",
          panel.is_run_complete(pending_second_pass, "COMPLETE", TICKERS, watermark_status="ok") is False)

    check("15c. empty rows with COMPLETE status (pathological) -> gate fails, not vacuously true",
          panel.is_run_complete([], "COMPLETE", TICKERS, watermark_status="ok") is False)


# === 2026-08-01 watermark additions: tests 15/16 from the watermark spec ===
def test_watermark_15_completion_marker_cannot_say_complete_without_valid_watermark():
    all_clean = [_clean_row(t) for t in TICKERS]
    check("watermark-15: all rows perfectly clean, COMPLETE status, but NO watermark_status given "
          "(None) -> gate still fails", panel.is_run_complete(all_clean, "COMPLETE", TICKERS) is False)
    check("watermark-15: watermark_status='failed_closed' -> gate fails even with perfectly clean rows",
          panel.is_run_complete(all_clean, "COMPLETE", TICKERS, watermark_status="failed_closed") is False)
    check("watermark-15: watermark_status='no_data_within_max_lag' -> gate fails even with "
          "perfectly clean rows",
          panel.is_run_complete(all_clean, "COMPLETE", TICKERS, watermark_status="no_data_within_max_lag") is False)
    check("watermark-15: watermark_status='ok' with otherwise-clean rows -> gate passes",
          panel.is_run_complete(all_clean, "COMPLETE", TICKERS, watermark_status="ok") is True)


def test_watermark_16_lag_greater_than_max_cannot_produce_complete():
    """A watermark resolution that exceeded MAX_ACCEPTABLE_WIKI_LAG_DAYS
    never reaches status='ok' in the first place (see
    resolve_wiki_data_watermark() -- it returns 'no_data_within_max_lag'
    once every candidate within the lag budget is exhausted), so lag>3 can
    structurally never produce COMPLETE via this gate regardless of what
    individual rows show."""
    all_clean = [_clean_row(t) for t in TICKERS]
    for bad_status in ("no_data_within_max_lag", "failed_closed"):
        check(f"watermark-16: watermark_status={bad_status!r} (the only way an out-of-budget lag "
              f"surfaces) cannot produce COMPLETE",
              panel.is_run_complete(all_clean, "COMPLETE", TICKERS, watermark_status=bad_status) is False)


# === 2026-08-01 completion-gate correction: six-locked-fields vs
# fail-closed earnings-lookup separation (GitHub review finding) ===
def test_earnings_status_separation():
    # (a) six fields complete + earnings_status="ok" + days_to_nearest_earnings=None
    #     -- a genuinely successful lookup that honestly found no upcoming
    #     earnings date (the 46aec15 baseline shape for 4/24 tickers) must
    #     remain eligible for COMPLETE.
    ok_no_date = [_dirty_row(t, days_to_nearest_earnings=None) for t in TICKERS]
    check("earnings-a. six fields clean + earnings_status='ok' + date=None -> eligible for COMPLETE",
          panel.is_run_complete(ok_no_date, "COMPLETE", TICKERS, watermark_status="ok") is True)

    # (b) six fields complete but earnings_status="error" -- an actual lookup
    #     failure must block COMPLETE even though the six research fields
    #     are all clean.
    earnings_error = [_clean_row(t) for t in TICKERS[:-1]] + \
        [_dirty_row(TICKERS[-1], earnings_status="error")]
    check("earnings-b. six fields clean but one row earnings_status='error' -> PARTIAL",
          panel.is_run_complete(earnings_error, "COMPLETE", TICKERS, watermark_status="ok") is False)

    # (c) six fields complete but earnings_status="timeout" -- same as (b),
    #     a different fail-closed lookup outcome.
    earnings_timeout = [_clean_row(t) for t in TICKERS[:-1]] + \
        [_dirty_row(TICKERS[-1], earnings_status="timeout")]
    check("earnings-c. six fields clean but one row earnings_status='timeout' -> PARTIAL",
          panel.is_run_complete(earnings_timeout, "COMPLETE", TICKERS, watermark_status="ok") is False)

    # (d) one row missing a core (six-field) value, earnings otherwise ok --
    #     isolates that the six-field check still independently blocks
    #     COMPLETE regardless of earnings_status.
    missing_core = [_clean_row(t) for t in TICKERS[:-1]] + \
        [_dirty_row(TICKERS[-1], all_six_fields_clean=False)]
    check("earnings-d. one row missing a core six-field value (earnings ok) -> PARTIAL",
          panel.is_run_complete(missing_core, "COMPLETE", TICKERS, watermark_status="ok") is False)


def test_completion_marker_counts_distinguish_null_earnings_from_failure():
    # (e) write_completion_marker()'s new counters must distinguish a
    #     successful-but-null earnings lookup from an actual lookup failure.
    # 2 rows: successful lookup with no upcoming date, 1 row: lookup failure.
    rows = [
        _dirty_row("AAA", days_to_nearest_earnings=None),
        _dirty_row("BBB", days_to_nearest_earnings=7),
        _dirty_row("CCC", earnings_status="error", days_to_nearest_earnings=None),
    ]

    original_path = panel.COMPLETION_MARKER_PATH
    tmp_dir = tempfile.mkdtemp()
    tmp_path = Path(tmp_dir) / "test_completion_marker.json"
    panel.COMPLETION_MARKER_PATH = tmp_path
    try:
        panel.write_completion_marker(rows, elapsed_s=1.0, status="PARTIAL")
        with open(tmp_path, "r", encoding="utf-8") as f:
            marker = json.load(f)
    finally:
        panel.COMPLETION_MARKER_PATH = original_path
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

    check("marker-e. all_six_fields_clean_count unaffected by earnings outcome (3/3)",
          marker["all_six_fields_clean_count"] == 3, str(marker.get("all_six_fields_clean_count")))
    check("marker-e. earnings_lookup_ok_count counts only real 'ok' status (2/3)",
          marker["earnings_lookup_ok_count"] == 2, str(marker.get("earnings_lookup_ok_count")))
    check("marker-e. days_to_nearest_earnings_nonnull_count counts only the row with a real date (1/3)",
          marker["days_to_nearest_earnings_nonnull_count"] == 1,
          str(marker.get("days_to_nearest_earnings_nonnull_count")))


if __name__ == "__main__":
    test_14_final_completeness_gate()
    test_15_partial_never_named_complete()
    test_watermark_15_completion_marker_cannot_say_complete_without_valid_watermark()
    test_watermark_16_lag_greater_than_max_cannot_produce_complete()
    test_earnings_status_separation()
    test_completion_marker_counts_distinguish_null_earnings_from_failure()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL DAILYPANEL GATE TESTS PASSED (tests 14-16 + earnings/marker separation)")
        sys.exit(0)
