#!/usr/bin/env python3
# Deterministic tests for the completion-marker writer and the CLI's
# nonzero-exit-on-failed-gate behavior (gst_market_response/cli.py,
# completion_marker.py). No live network, no panel run.
#
# Run directly: python test_market_response_cli_gate.py

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response import cli
from gst_market_response.completion_marker import EXIT_GATE_FAILED, EXIT_INCONCLUSIVE, EXIT_OK, write_completion_marker
from gst_market_response.event_record import EventStore

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="mrd_cli_test_"))


def test_gate_passes_returns_zero():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-MSFT-FY26Q4-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        store.append_state(
            eid, "PRE_EVENT_CAPTURED",
            {"previous_close": 450.0, "pre_event_snapshot_asof_utc": "2026-07-29T20:00:00+00:00", "gst_zscore": 2.0},
        )
        code = cli.main(["--store-root", str(root), "--event-id", eid, "--tier", "pre_event"])
        check("CLI exits 0 when the pre_event gate passes", code == EXIT_OK, str(code))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_gate_fails_returns_nonzero():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-AAPL-FY26Q4-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        store.append_state(eid, "PARTIAL", {"previous_close": None})
        code = cli.main(["--store-root", str(root), "--event-id", eid, "--tier", "pre_event"])
        check("CLI exits nonzero when required pre_event fields are missing", code == EXIT_GATE_FAILED, str(code))
        check("Failed-gate exit code is nonzero (mechanically usable by a caller/CI step)", code != 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_unknown_event_is_inconclusive_not_a_false_pass():
    root = temp_dir()
    try:
        code = cli.main(["--store-root", str(root), "--event-id", "EVT-NOPE-FY26Q1-ERN", "--tier", "pre_event"])
        check(
            "CLI returns INCONCLUSIVE (nonzero) for an unregistered event, never a false OK",
            code == EXIT_INCONCLUSIVE and code != EXIT_OK,
            str(code),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_completion_marker_written_atomically_and_readable():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-TSLA-FY26Q3-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        store.append_state(eid, "PRE_EVENT_CAPTURED", {"previous_close": 250.0, "pre_event_snapshot_asof_utc": "x", "gst_zscore": 1.0})
        marker = write_completion_marker(root, eid, store)
        marker_path = root / f"{eid}_COMPLETION_MARKER.json"
        check("Completion marker file written to disk", marker_path.exists())
        on_disk = json.loads(marker_path.read_text(encoding="utf-8"))
        check("Completion marker records the correct final_state", on_disk["final_state"] == "PRE_EVENT_CAPTURED")
        check("Completion marker records a state_transition_count matching the log", on_disk["state_transition_count"] == 3)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_gate_passes_returns_zero()
    test_gate_fails_returns_nonzero()
    test_unknown_event_is_inconclusive_not_a_false_pass()
    test_completion_marker_written_atomically_and_readable()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL CLI/COMPLETION-MARKER GATE TESTS PASSED")
        sys.exit(0)
