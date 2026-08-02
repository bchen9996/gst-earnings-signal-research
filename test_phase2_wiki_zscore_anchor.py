#!/usr/bin/env python3
# Deterministic tests for the 2026-08-02 wiki z-score anchor correction:
# _finalize_wiki_row() in GST_Phase2_DailyPanel.py must anchor
# compute_zscore_at_anchor() on the measured Wikipedia watermark date,
# never the script's real wall-clock run date. See CHANGELOG.md
# (2026-08-02 entry) and Live Signal Engine/Phase2 Failure Evidence/
# 2026-08-02_WatermarkAnchor_And_Endpoint_PARTIAL/ for the bug this fixes.
#
# No network access, no cache access, no panel execution -- pure
# synthetic in-memory data. Importing GST_Phase2_DailyPanel does not run
# the panel -- main() is guarded by if __name__ == "__main__".
#
# Run directly: python test_phase2_wiki_zscore_anchor.py

from __future__ import annotations
import sys
import os
import inspect
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import GST_Phase2_DailyPanel as panel
import GST_FixedWindow_PerEvent_Canonical as canonical

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def _daily_rows(end_date: date, n_days: int, base_value: int = 1000) -> list[dict]:
    """n_days consecutive days ending at end_date (inclusive), mild
    variability so weekly sums differ (avoids a degenerate zero-variance
    series)."""
    rows = []
    for i in range(n_days):
        d = end_date - timedelta(days=n_days - 1 - i)
        rows.append({"date": d.strftime("%Y%m%d"), "pageviews": base_value + (i * 3) % 97})
    return rows


def _fresh_row() -> dict:
    return {"ticker": "TEST", "gst_zscore": 1.0, "implied_volatility": 0.2,
            "realized_vol": 0.3, "price": 100.0, "volume": 1000}


# === Test 1: run date Aug 2, watermark Aug 1, nearest week Jul 26 -> valid within 6-day tolerance ===
def test_1_watermark_anchor_within_tolerance():
    watermark_date = date(2026, 8, 1)
    daily_rows = _daily_rows(watermark_date, n_days=15 * 7)  # 15 weeks of history
    row = _fresh_row()
    panel._finalize_wiki_row(row, "Test_Article", daily_rows, watermark_date)
    check("1a. wiki_zscore is not None when anchored at the watermark (gap<=6d)",
          row.get("wiki_zscore") is not None, f"note={row.get('wiki_note')!r}")
    check("1b. wiki_status == 'ok'", row.get("wiki_status") == "ok")
    if row.get("wiki_aligned_week"):
        gap = abs((date.fromisoformat(row["wiki_aligned_week"]) - watermark_date).days)
        check("1c. aligned week is within the existing 6-day tolerance", gap <= 6, f"gap={gap}")


# === Test 2: wall-clock date changes while watermark/data remain fixed -> identical z-score ===
def test_2_wall_clock_independence():
    watermark_date = date(2026, 8, 1)
    daily_rows = _daily_rows(watermark_date, n_days=15 * 7)

    row_a = _fresh_row()
    panel._finalize_wiki_row(row_a, "Test_Article", daily_rows, watermark_date)
    row_b = _fresh_row()
    panel._finalize_wiki_row(row_b, "Test_Article", daily_rows, watermark_date)

    check("2a. identical inputs (data+watermark) produce an identical z-score regardless of when the test runs",
          row_a.get("wiki_zscore") == row_b.get("wiki_zscore"),
          f"{row_a.get('wiki_zscore')!r} vs {row_b.get('wiki_zscore')!r}")

    src = inspect.getsource(panel._finalize_wiki_row)
    check("2b. _finalize_wiki_row's source contains no datetime.now()/wall-clock read",
          "datetime.now(" not in src and ".today()" not in src)
    check("2c. _finalize_wiki_row no longer accepts a run_ts/wall-clock parameter",
          "watermark_date" in inspect.signature(panel._finalize_wiki_row).parameters
          and "run_ts" not in inspect.signature(panel._finalize_wiki_row).parameters)


# === Test 3: observation after watermark -> excluded (not fail closed here; watermark itself is valid) ===
def test_3_observation_after_watermark_excluded():
    watermark_date = date(2026, 8, 1)
    daily_rows = _daily_rows(watermark_date, n_days=15 * 7)

    row_without_future = _fresh_row()
    panel._finalize_wiki_row(row_without_future, "Test_Article", daily_rows, watermark_date)

    daily_rows_with_future = daily_rows + [
        {"date": (watermark_date + timedelta(days=4)).strftime("%Y%m%d"), "pageviews": 999_999_999},
    ]
    row_with_future = _fresh_row()
    panel._finalize_wiki_row(row_with_future, "Test_Article", daily_rows_with_future, watermark_date)

    check("3. an observation dated after the watermark has zero effect on the computed z-score (excluded)",
          row_without_future.get("wiki_zscore") == row_with_future.get("wiki_zscore"),
          f"{row_without_future.get('wiki_zscore')!r} vs {row_with_future.get('wiki_zscore')!r}")


# === Test 4: missing watermark -> fail closed ===
def test_4_missing_watermark_fails_closed():
    daily_rows = _daily_rows(date(2026, 8, 1), n_days=15 * 7)
    row = _fresh_row()
    raised = False
    try:
        panel._finalize_wiki_row(row, "Test_Article", daily_rows, None)
    except ValueError:
        raised = True
    check("4. _finalize_wiki_row(watermark_date=None) raises ValueError (fail closed, no wall-clock fallback)",
          raised)


# === Test 5: watermark error (e.g. status='failed_closed', watermark_date=None) -> fail closed ===
def test_5_watermark_error_fails_closed():
    # Mirrors the real watermark_info contract: any non-"ok" status carries
    # watermark_date=None (see resolve_wiki_data_watermark()); this is the
    # exact value process_ticker()/main() would pass through if the
    # existing != "ok" guard were ever bypassed.
    watermark_info = {"status": "failed_closed", "watermark_date": None}
    daily_rows = _daily_rows(date(2026, 8, 1), n_days=15 * 7)
    row = _fresh_row()
    raised = False
    try:
        panel._finalize_wiki_row(row, "Test_Article", daily_rows, watermark_info["watermark_date"])
    except ValueError:
        raised = True
    check("5. a watermark-resolution error (status != 'ok', watermark_date=None) fails closed the same way",
          raised)


# === Test 6: seven-day distance remains invalid (tolerance not widened) ===
def test_6_seven_day_distance_still_invalid():
    weeks = pd.date_range("2026-01-04", periods=12, freq="7D")  # Sundays
    weekly = pd.DataFrame({"Week": weeks, "gst": [1000 + (i * 37) % 211 for i in range(len(weeks))]})
    anchor = weeks[-1] + pd.Timedelta(days=7)  # exactly 7 days past the last available week
    aligned_week, z, note = canonical.compute_zscore_at_anchor(weekly, anchor)
    check("6. a 7-day gap between anchor and nearest week is still rejected (None, 'no aligned week')",
          z is None and "no aligned week" in note, f"z={z!r} note={note!r}")


# === Test 7: six-day distance remains valid (tolerance not narrowed) ===
def test_7_six_day_distance_still_valid():
    weeks = pd.date_range("2026-01-04", periods=12, freq="7D")  # Sundays
    weekly = pd.DataFrame({"Week": weeks, "gst": [1000 + (i * 37) % 211 for i in range(len(weeks))]})
    anchor = weeks[-1] + pd.Timedelta(days=6)  # exactly 6 days past the last available week
    aligned_week, z, note = canonical.compute_zscore_at_anchor(weekly, anchor)
    check("7. a 6-day gap between anchor and nearest week is still accepted (non-None z-score)",
          z is not None, f"z={z!r} note={note!r}")


# === Test 8: output provenance records the watermark anchor ===
def test_8_provenance_records_watermark_anchor():
    watermark_date = date(2026, 8, 1)
    daily_rows = _daily_rows(watermark_date, n_days=15 * 7)
    row = _fresh_row()
    panel._finalize_wiki_row(row, "Test_Article", daily_rows, watermark_date)
    check("8a. wiki_zscore_anchor_date == watermark_date",
          row.get("wiki_zscore_anchor_date") == watermark_date.isoformat(),
          f"got {row.get('wiki_zscore_anchor_date')!r}")
    check("8b. wiki_zscore_anchor_source == 'measured_watermark'",
          row.get("wiki_zscore_anchor_source") == "measured_watermark")
    check("8c. new provenance columns are present in COLUMN_ORDER",
          "wiki_zscore_anchor_date" in panel.COLUMN_ORDER and "wiki_zscore_anchor_source" in panel.COLUMN_ORDER)


if __name__ == "__main__":
    test_1_watermark_anchor_within_tolerance()
    test_2_wall_clock_independence()
    test_3_observation_after_watermark_excluded()
    test_4_missing_watermark_fails_closed()
    test_5_watermark_error_fails_closed()
    test_6_seven_day_distance_still_invalid()
    test_7_six_day_distance_still_valid()
    test_8_provenance_records_watermark_anchor()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL WIKI Z-SCORE ANCHOR TESTS PASSED (8 required scenarios)")
        sys.exit(0)
