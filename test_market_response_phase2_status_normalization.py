#!/usr/bin/env python3
# Deterministic tests for Phase 2 source-status normalisation in the
# market-response adapter.
#
# The bug this locks down: the adapter used to collapse every status that was
# not literally "ok" to "error", which mislabelled Phase 2's
# "complete_recent_cache_fallback" -- a COMPLETE outcome carrying a real
# z-score -- as a failure.
#
# Synthetic fixtures only. Never invokes GST_Phase2_DailyPanel.py, never reads
# an operational panel, never touches the network.
#
# Run directly: python test_market_response_phase2_status_normalization.py

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.phase2_adapter import (
    NORMALIZED_ERROR,
    NORMALIZED_MISSING,
    NORMALIZED_OK,
    NORMALIZED_OK_RECENT_CACHE_FALLBACK,
    NORMALIZED_STATUSES,
    import_pre_event_fields_for_ticker,
    is_successful_leg_status,
    normalize_leg_status,
    was_served_from_recent_cache_fallback,
)

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def test_required_status_mappings():
    cases = [
        ("ok", NORMALIZED_OK, "1a"),
        ("complete_recent_cache_fallback", NORMALIZED_OK_RECENT_CACHE_FALLBACK, "1b"),
        ("", NORMALIZED_MISSING, "1c"),
        (None, NORMALIZED_MISSING, "1d"),
        ("timeout", NORMALIZED_ERROR, "1e"),
        ("error", NORMALIZED_ERROR, "1f"),
        ("incomplete_after_second_pass", NORMALIZED_ERROR, "1g"),
        ("incomplete_effective_watermark_unavailable", NORMALIZED_ERROR, "1h"),
        ("incomplete_watermark_unavailable", NORMALIZED_ERROR, "1i"),
        ("some_status_invented_next_month", NORMALIZED_ERROR, "1j"),
    ]
    for raw, expected, tag in cases:
        got = normalize_leg_status(raw)
        check(f"{tag}. {raw!r} normalises to {expected!r}", got == expected)


def test_fallback_is_success_but_not_ordinary_fresh_data():
    check(
        "2a. 'ok' is a success category",
        is_successful_leg_status(NORMALIZED_OK),
    )
    check(
        "2b. the recent-cache fallback is ALSO a success category (not an error)",
        is_successful_leg_status(NORMALIZED_OK_RECENT_CACHE_FALLBACK),
    )
    check(
        "2c. the fallback does NOT normalise to plain 'ok' -- it is never presented "
        "as ordinary fresh data",
        NORMALIZED_OK_RECENT_CACHE_FALLBACK != NORMALIZED_OK,
    )
    check(
        "2d. the fallback is identifiable via was_served_from_recent_cache_fallback",
        was_served_from_recent_cache_fallback(NORMALIZED_OK_RECENT_CACHE_FALLBACK)
        and not was_served_from_recent_cache_fallback(NORMALIZED_OK),
    )
    check(
        "2e. missing and error are NOT success categories",
        not is_successful_leg_status(NORMALIZED_MISSING)
        and not is_successful_leg_status(NORMALIZED_ERROR),
    )
    check(
        "2f. every normalised value comes from the declared enum",
        all(
            normalize_leg_status(r) in NORMALIZED_STATUSES
            for r in ("ok", "complete_recent_cache_fallback", "", None, "weird", "timeout")
        ),
    )


def test_unknown_status_fails_closed_but_retains_raw():
    """An unrecognised non-blank status must become error AND keep its exact
    original text on the result object."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        csv_path, marker_path = _write_panel(root, wiki_status="totally_new_status")
        result = import_pre_event_fields_for_ticker(
            ticker="AAPL", csv_path=csv_path, marker_path=marker_path,
            research_commit_sha="deadbeef", methodology_version="v0.1",
        )
        check(
            "3a. unknown non-blank status fails closed to error",
            result.source_status_wiki == NORMALIZED_ERROR,
        )
        check(
            "3b. the exact original status text is retained verbatim",
            result.source_status_wiki_raw == "totally_new_status",
        )


def _write_panel(root: Path, wiki_status: str, gst_status: str = "ok") -> tuple[Path, Path]:
    csv_path = root / "panel.csv"
    marker_path = root / "marker.json"
    header = [
        "ticker", "gst_status", "wiki_status", "price_history_status",
        "gst_zscore", "wiki_zscore", "realized_vol", "price", "volume",
        "days_to_nearest_earnings", "retrieval_timestamp_utc",
        "all_six_fields_clean",
    ]
    row = [
        "AAPL", gst_status, wiki_status, "ok",
        "1.5", "2.5", "0.21", "195.5", "1000000",
        "3", "2026-07-29T12:00:00+00:00",
        "True",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerow(row)
    marker = {
        "status": "COMPLETE",
        "row_count": 1,
        "unique_ticker_count": 1,
        "all_six_fields_clean_count": 1,
    }
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    return csv_path, marker_path


def test_end_to_end_fallback_row_keeps_provenance():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        csv_path, marker_path = _write_panel(root, wiki_status="complete_recent_cache_fallback")
        result = import_pre_event_fields_for_ticker(
            ticker="AAPL", csv_path=csv_path, marker_path=marker_path,
            research_commit_sha="deadbeef", methodology_version="v0.1",
        )
        check(
            "4a. a fallback-served wiki leg normalises to the fallback success category",
            result.source_status_wiki == NORMALIZED_OK_RECENT_CACHE_FALLBACK,
        )
        check(
            "4b. it is NOT reported as an error (the old bug)",
            result.source_status_wiki != NORMALIZED_ERROR,
        )
        check(
            "4c. the original Phase 2 string is preserved separately",
            result.source_status_wiki_raw == "complete_recent_cache_fallback",
        )
        check(
            "4d. the convenience flag reports cache-served provenance",
            result.is_recent_cache_fallback_wiki
            and result.any_leg_served_from_recent_cache_fallback,
        )
        check(
            "4e. the wiki z-score itself is carried through unchanged",
            result.wiki_zscore == 2.5,
        )
        check(
            "4f. a fresh 'ok' gst leg is not flagged as cache-served",
            result.source_status_gst == NORMALIZED_OK and not result.is_recent_cache_fallback_gst,
        )
        fields = result.to_pre_event_fields()
        check(
            "4g. raw statuses cross into the pre-event field dict for downstream provenance",
            fields["source_status_wiki_raw"] == "complete_recent_cache_fallback"
            and fields["source_status_wiki"] == NORMALIZED_OK_RECENT_CACHE_FALLBACK,
        )


def test_blank_and_error_end_to_end():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        csv_path, marker_path = _write_panel(root, wiki_status="")
        result = import_pre_event_fields_for_ticker(
            ticker="AAPL", csv_path=csv_path, marker_path=marker_path,
            research_commit_sha="deadbeef", methodology_version="v0.1",
        )
        check("5a. blank wiki_status -> missing", result.source_status_wiki == NORMALIZED_MISSING)
        check("5b. blank raw is preserved as empty string", result.source_status_wiki_raw == "")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        csv_path, marker_path = _write_panel(root, wiki_status="timeout")
        result = import_pre_event_fields_for_ticker(
            ticker="AAPL", csv_path=csv_path, marker_path=marker_path,
            research_commit_sha="deadbeef", methodology_version="v0.1",
        )
        check("5c. timeout -> error", result.source_status_wiki == NORMALIZED_ERROR)
        check("5d. timeout raw preserved", result.source_status_wiki_raw == "timeout")


def test_phase2_own_statuses_are_not_modified():
    """This module must never redefine Phase 2's vocabulary -- only interpret
    it. Assert the strings we key on still exist in Phase 2's own source."""
    here = Path(os.path.dirname(os.path.abspath(__file__)))
    transport = (here / "GST_Phase2_Wikipedia_Transport.py").read_text(encoding="utf-8")
    check(
        "6a. 'complete_recent_cache_fallback' is still a real Phase 2 status",
        '"complete_recent_cache_fallback"' in transport,
    )
    validate_amzn = (here / "validate_amzn_wiki_only.py").read_text(encoding="utf-8")
    check(
        "6b. Phase 2's own tooling still treats it as COMPLETE alongside 'ok' "
        "(the premise of this normalisation)",
        'wiki_status in ("ok", "complete_recent_cache_fallback")' in validate_amzn,
    )


if __name__ == "__main__":
    test_required_status_mappings()
    test_fallback_is_success_but_not_ordinary_fresh_data()
    test_unknown_status_fails_closed_but_retains_raw()
    test_end_to_end_fallback_row_keeps_provenance()
    test_blank_and_error_end_to_end()
    test_phase2_own_statuses_are_not_modified()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PHASE 2 STATUS NORMALIZATION TESTS PASSED")
    sys.exit(0)
