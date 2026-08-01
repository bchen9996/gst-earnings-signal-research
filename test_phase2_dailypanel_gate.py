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


if __name__ == "__main__":
    test_14_final_completeness_gate()
    test_15_partial_never_named_complete()
    test_watermark_15_completion_marker_cannot_say_complete_without_valid_watermark()
    test_watermark_16_lag_greater_than_max_cannot_produce_complete()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL DAILYPANEL GATE TESTS PASSED (tests 14-16)")
        sys.exit(0)
