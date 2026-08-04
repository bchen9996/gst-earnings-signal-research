#!/usr/bin/env python3
# TASK 2 deterministic tests: the Phase 2 pre-event adapter. Uses only
# synthetic, hand-built CSV + completion-marker fixtures -- never invokes
# GST_Phase2_DailyPanel.py itself, never reads a real operational panel
# file.
#
# Run directly: python test_market_response_phase2_adapter.py

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.phase2_adapter import (
    MarkerCsvMismatchError,
    Phase2AdapterError,
    import_pre_event_fields_for_ticker,
    sha256_of_file,
)

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="mrd_phase2_adapter_test_"))


_COLUMNS = [
    "ticker", "retrieval_timestamp_utc", "days_to_nearest_earnings",
    "price", "volume", "price_history_status",
    "realized_vol", "realized_vol_status",
    "implied_volatility", "iv_status",
    "gst_zscore", "gst_status",
    "wiki_zscore", "wiki_status",
    "all_six_fields_clean",
]


def _write_panel_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in _COLUMNS})


def _write_marker(path: Path, *, status: str, rows: list[dict]) -> None:
    marker = {
        "status": status,
        "row_count": len(rows),
        "unique_ticker_count": len({r["ticker"] for r in rows}),
        "all_six_fields_clean_count": sum(1 for r in rows if str(r.get("all_six_fields_clean")) == "True"),
    }
    path.write_text(json.dumps(marker), encoding="utf-8")


def _clean_row(ticker: str, **overrides) -> dict:
    row = {
        "ticker": ticker, "retrieval_timestamp_utc": "2026-10-29T20:00:00+00:00",
        "days_to_nearest_earnings": "0",
        "price": "450.25", "volume": "12345678", "price_history_status": "ok",
        "realized_vol": "0.28", "realized_vol_status": "ok",
        "implied_volatility": "0.35", "iv_status": "ok",
        "gst_zscore": "3.2", "gst_status": "ok",
        "wiki_zscore": "2.1", "wiki_status": "ok",
        "all_six_fields_clean": "True",
    }
    row.update(overrides)
    return row


def test_never_discovers_latest_file_implicitly():
    src = "import gst_market_response.phase2_adapter as m\n" + Path("gst_market_response/phase2_adapter.py").read_text(encoding="utf-8")
    check(
        "1. Adapter source contains no directory-scan/glob 'latest file' discovery logic",
        "glob(" not in src and "listdir(" not in src and "iterdir(" not in src,
    )


def test_hashes_verified_and_recorded():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        rows = [_clean_row("MSFT")]
        _write_panel_csv(csv_path, rows)
        _write_marker(marker_path, status="COMPLETE", rows=rows)

        expected_csv_hash = sha256_of_file(csv_path)
        expected_marker_hash = sha256_of_file(marker_path)

        result = import_pre_event_fields_for_ticker(
            csv_path=csv_path, marker_path=marker_path, ticker="MSFT",
            research_commit_sha="833636e306bf79ce5fec0a9ff670284df6967bf8", methodology_version="phase2-v0.1",
        )
        check("2a. Recorded CSV hash matches an independently computed hash", result.source_csv_sha256 == expected_csv_hash)
        check("2b. Recorded marker hash matches an independently computed hash", result.source_marker_sha256 == expected_marker_hash)
        check("2c. research_commit_sha is recorded exactly as supplied", result.research_commit_sha == "833636e306bf79ce5fec0a9ff670284df6967bf8")
        check("2d. methodology_version is recorded exactly as supplied", result.methodology_version == "phase2-v0.1")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_marker_csv_count_mismatch_rejected():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        rows = [_clean_row("MSFT"), _clean_row("AAPL")]
        _write_panel_csv(csv_path, rows)
        # Marker CLAIMS 2 rows are clean but only write the marker for 1 --
        # a real world "the marker lied" or was copy-pasted from a different run.
        marker_path.write_text(json.dumps({"status": "COMPLETE", "row_count": 1, "unique_ticker_count": 1, "all_six_fields_clean_count": 1}), encoding="utf-8")

        try:
            import_pre_event_fields_for_ticker(
                csv_path=csv_path, marker_path=marker_path, ticker="MSFT",
                research_commit_sha="deadbeef", methodology_version="phase2-v0.1",
            )
            ok = False
        except MarkerCsvMismatchError:
            ok = True
        check("3. Marker/CSV row-count mismatch is rejected, never silently trusted", ok)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_complete_vs_partial_preserved_exactly():
    root = temp_dir()
    try:
        for status in ("COMPLETE", "PARTIAL"):
            csv_path = root / f"panel_{status}.csv"
            marker_path = root / f"marker_{status}.json"
            rows = [_clean_row("AAPL")]
            _write_panel_csv(csv_path, rows)
            _write_marker(marker_path, status=status, rows=rows)
            result = import_pre_event_fields_for_ticker(
                csv_path=csv_path, marker_path=marker_path, ticker="AAPL",
                research_commit_sha="x", methodology_version="v0.1",
            )
            check(f"4. panel_status preserved exactly as {status!r}, not normalized/renamed", result.panel_status == status)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_nulls_and_source_statuses_preserved():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        rows = [_clean_row("GME", gst_zscore="", gst_status="error", wiki_zscore="", wiki_status="", all_six_fields_clean="False")]
        _write_panel_csv(csv_path, rows)
        _write_marker(marker_path, status="PARTIAL", rows=rows)

        result = import_pre_event_fields_for_ticker(
            csv_path=csv_path, marker_path=marker_path, ticker="GME",
            research_commit_sha="x", methodology_version="v0.1",
        )
        check("5a. Empty CSV cell for gst_zscore imports as None, never 0", result.gst_zscore is None)
        check("5b. gst_status='error' normalizes to source_status_gst='error'", result.source_status_gst == "error")
        check("5c. Empty wiki_status normalizes to source_status_wiki='missing' (not silently 'ok')", result.source_status_wiki == "missing")
        check("5d. wiki_zscore stays None", result.wiki_zscore is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_imports_required_fields_never_earnings_implied_move():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        rows = [_clean_row("TSLA", implied_volatility="0.55")]
        _write_panel_csv(csv_path, rows)
        _write_marker(marker_path, status="COMPLETE", rows=rows)

        result = import_pre_event_fields_for_ticker(
            csv_path=csv_path, marker_path=marker_path, ticker="TSLA",
            research_commit_sha="x", methodology_version="v0.1",
        )
        check("6a. gst_zscore imported", result.gst_zscore == 3.2)
        check("6b. wiki_zscore imported", result.wiki_zscore == 2.1)
        check("6c. realized_volatility imported", result.realized_volatility == 0.28)
        check("6d. price imported", result.price == 450.25)
        check("6e. volume imported", result.volume == 12345678)
        check("6f. days_to_earnings imported", result.days_to_earnings == 0)
        check("6g. retrieval provenance (pre_event_snapshot_asof_utc) imported", result.pre_event_snapshot_asof_utc == "2026-10-29T20:00:00+00:00")

        field_names = set(result.__dataclass_fields__.keys())
        check("6h. Adapter result schema has no 'earnings_implied_move' field at all", "earnings_implied_move" not in field_names)

        pre_event_fields = result.to_pre_event_fields()
        check("6i. to_pre_event_fields() also never emits an implied-move-shaped key", not any("implied" in k.lower() for k in pre_event_fields.keys()))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_refuses_pre_event_captured_when_gate_fails():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        rows = [_clean_row("CTSH", gst_zscore="", gst_status="", price="")]
        _write_panel_csv(csv_path, rows)
        _write_marker(marker_path, status="PARTIAL", rows=rows)

        result = import_pre_event_fields_for_ticker(
            csv_path=csv_path, marker_path=marker_path, ticker="CTSH",
            research_commit_sha="x", methodology_version="v0.1",
        )
        check("7a. Missing previous_close AND missing/errored gst_zscore -> not eligible for PRE_EVENT_CAPTURED", not result.eligible_for_pre_event_captured)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_input_files_remain_byte_identical():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        rows = [_clean_row("AAPL")]
        _write_panel_csv(csv_path, rows)
        _write_marker(marker_path, status="COMPLETE", rows=rows)

        before_csv = csv_path.read_bytes()
        before_marker = marker_path.read_bytes()

        import_pre_event_fields_for_ticker(
            csv_path=csv_path, marker_path=marker_path, ticker="AAPL",
            research_commit_sha="x", methodology_version="v0.1",
        )

        check("8a. CSV input file is byte-identical after import", csv_path.read_bytes() == before_csv)
        check("8b. Marker input file is byte-identical after import", marker_path.read_bytes() == before_marker)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_never_invokes_phase2_panel():
    src = Path("gst_market_response/phase2_adapter.py").read_text(encoding="utf-8")
    check(
        "9. Adapter never imports or subprocess-invokes GST_Phase2_DailyPanel (comment mentions are fine, code isn't)",
        "import GST_Phase2_DailyPanel" not in src
        and "from GST_Phase2_DailyPanel" not in src
        and "import subprocess" not in src,
    )


def test_missing_files_and_ambiguous_ticker_rejected():
    root = temp_dir()
    try:
        csv_path = root / "panel.csv"
        marker_path = root / "marker.json"
        try:
            import_pre_event_fields_for_ticker(
                csv_path=csv_path, marker_path=marker_path, ticker="AAPL",
                research_commit_sha="x", methodology_version="v0.1",
            )
            ok = False
        except Phase2AdapterError:
            ok = True
        check("10a. Nonexistent CSV path is rejected explicitly, never silently treated as empty", ok)

        rows = [_clean_row("AAPL"), _clean_row("AAPL")]  # duplicate ticker rows
        _write_panel_csv(csv_path, rows)
        _write_marker(marker_path, status="COMPLETE", rows=rows)
        try:
            import_pre_event_fields_for_ticker(
                csv_path=csv_path, marker_path=marker_path, ticker="AAPL",
                research_commit_sha="x", methodology_version="v0.1",
            )
            ok2 = False
        except Phase2AdapterError:
            ok2 = True
        check("10b. Ambiguous (duplicate) ticker rows in the CSV are rejected, not silently picking the first", ok2)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_never_discovers_latest_file_implicitly()
    test_hashes_verified_and_recorded()
    test_marker_csv_count_mismatch_rejected()
    test_complete_vs_partial_preserved_exactly()
    test_nulls_and_source_statuses_preserved()
    test_imports_required_fields_never_earnings_implied_move()
    test_refuses_pre_event_captured_when_gate_fails()
    test_input_files_remain_byte_identical()
    test_never_invokes_phase2_panel()
    test_missing_files_and_ambiguous_ticker_rejected()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL PHASE 2 ADAPTER TESTS PASSED")
        sys.exit(0)
