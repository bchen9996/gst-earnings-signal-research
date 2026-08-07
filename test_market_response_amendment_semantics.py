#!/usr/bin/env python3
# TASK 5 of the operational-readiness pass: deterministic tests proving the
# amendment semantics around a PARTIAL record. No live network.
#
# Run directly: python test_market_response_amendment_semantics.py

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response import completeness, pipeline
from gst_market_response.event_record import EventStore, InvalidStateTransitionError, validate_transition

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL: {name}" + (f" -- {detail}" if detail else ""))


def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="mrd_amendment_test_"))


UTC = timezone.utc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_1_partial_record_remains_immutable_and_terminal():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-AAPL-FY26Q3-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        store.append_state(eid, "PARTIAL", {"reason": "incomplete D1 data"})

        try:
            store.append_state(eid, "D1_PENDING", {})
            ok = False
        except InvalidStateTransitionError:
            ok = True
        check("1a. No further STATE transition accepted once PARTIAL is reached", ok)

        try:
            store.append_state(eid, "COMPLETE", {"forced": True})
            ok2 = False
        except InvalidStateTransitionError:
            ok2 = True
        check("1b. PARTIAL cannot be force-advanced directly to COMPLETE either", ok2)

        records = store.read_all(eid)
        partial_records = [r for r in records if r["record_type"] == "STATE" and r["state"] == "PARTIAL"]
        check("1c. Exactly one PARTIAL STATE record exists -- it was never duplicated or replaced", len(partial_records) == 1)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_2_later_recovery_creates_separately_identified_amendment():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-MSFT-FY26Q4-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        partial_record = store.append_state(eid, "PARTIAL", {
            "overnight_gap": None, "open_to_30m": 0.01, "thirty_min_to_close": 0.02, "open_to_close": None,
        })
        partial_seq = partial_record["seq"]

        # A later recovery run finds the missing bars and wants to record
        # the now-complete D1 decomposition. It must NOT be written as a new
        # STATE (impossible -- PARTIAL is terminal, proven above) and must
        # NOT overwrite the PARTIAL record -- it is recorded as a distinct
        # AMENDMENT record instead.
        amendment = store.append_amendment(
            eid, amends_seq=partial_seq,
            corrected_fields={
                "overnight_gap": 0.015, "open_to_30m": 0.01, "thirty_min_to_close": 0.02, "open_to_close": 0.031,
            },
            reason="recovered missing overnight-gap/open-to-close bars from a corrected raw-bar re-fetch",
        )
        check("2a. Recovery is recorded as an AMENDMENT record, distinct from the original STATE record", amendment["record_type"] == "AMENDMENT")
        check("2b. The amendment has its own sequence number, separate from the original", amendment["seq"] != partial_seq)

        records = store.read_all(eid)
        record_types_at_amendment_seq = [r["record_type"] for r in records if r["seq"] == amendment["seq"]]
        check("2c. Exactly one record occupies the amendment's own seq slot", record_types_at_amendment_seq == ["AMENDMENT"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_3_amendment_links_to_original_record():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-TSLA-FY26Q3-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        partial_record = store.append_state(eid, "PARTIAL", {"open_to_close": None})
        amendment = store.append_amendment(eid, amends_seq=partial_record["seq"], corrected_fields={"open_to_close": 0.02}, reason="recovered")

        check("3a. Amendment's amends_seq points at the exact original record's seq", amendment["amends_seq"] == partial_record["seq"])

        records = store.read_all(eid)
        linked_original = next(r for r in records if r["seq"] == amendment["amends_seq"])
        check("3b. Following amends_seq resolves back to the correct original PARTIAL record", linked_original["state"] == "PARTIAL")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_4_original_bytes_and_hash_unchanged():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-QCOM-FY26Q3-ERN"
        store.append_state(eid, "REGISTERED", {})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        partial_record = store.append_state(eid, "PARTIAL", {"open_to_close": None})

        log_path = store._log_path(eid)
        before_bytes = log_path.read_bytes()
        before_hash = _sha256(before_bytes)

        store.append_amendment(eid, amends_seq=partial_record["seq"], corrected_fields={"open_to_close": 0.04}, reason="recovered")

        after_bytes = log_path.read_bytes()
        after_hash = _sha256(after_bytes)

        check("4a. Original bytes remain an exact, untouched prefix of the file after the amendment", after_bytes.startswith(before_bytes))
        check("4b. The pre-amendment file's own hash is still reproducible by re-hashing that exact byte range", _sha256(after_bytes[: len(before_bytes)]) == before_hash)
        check("4c. Amendment strictly grew the file rather than rewriting it", len(after_bytes) > len(before_bytes))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_5_amendment_reaches_complete_only_if_independently_valid():
    root = temp_dir()
    try:
        store = EventStore(root)

        # Case A: the "recovered" fields are STILL incomplete -- the
        # amendment must not be treated as satisfying the D1 gate just
        # because a recovery attempt was made.
        eid_a = "EVT-NKE-FY26Q3-ERN"
        store.append_state(eid_a, "REGISTERED", {})
        store.append_state(eid_a, "PRE_EVENT_PENDING", {})
        partial_a = store.append_state(eid_a, "PARTIAL", {"overnight_gap": None, "open_to_30m": None, "thirty_min_to_close": None, "open_to_close": None})
        amendment_a = store.append_amendment(
            eid_a, amends_seq=partial_a["seq"],
            corrected_fields={"overnight_gap": 0.01, "open_to_30m": None, "thirty_min_to_close": None, "open_to_close": None},
            reason="partial recovery -- overnight gap only, still missing intraday bars",
        )
        gate_a = completeness.evaluate_gate("d1", amendment_a["corrected_fields"])
        check("5a. An amendment with STILL-missing required fields does NOT independently satisfy the D1 gate", not gate_a.passed, str(gate_a.missing_required_fields))

        # Case B: the recovered fields genuinely satisfy every required field
        # for the tier -- only then does the amendment "count" as complete
        # for that tier, and it is the caller's job to check this
        # independently rather than trusting that "it's an amendment" implies success.
        eid_b = "EVT-SBUX-FY26Q3-ERN"
        store.append_state(eid_b, "REGISTERED", {})
        store.append_state(eid_b, "PRE_EVENT_PENDING", {})
        partial_b = store.append_state(eid_b, "PARTIAL", {"overnight_gap": None, "open_to_30m": None, "thirty_min_to_close": None, "open_to_close": None})
        amendment_b = store.append_amendment(
            eid_b, amends_seq=partial_b["seq"],
            corrected_fields={"overnight_gap": 0.01, "open_to_30m": 0.005, "thirty_min_to_close": 0.007, "open_to_close": 0.012},
            reason="full recovery -- all D1 bars re-fetched successfully",
        )
        gate_b = completeness.evaluate_gate("d1", amendment_b["corrected_fields"])
        check("5b. An amendment with every required field present DOES independently satisfy the D1 gate", gate_b.passed)

        # Critically: the ORIGINAL event record's own state is still PARTIAL
        # in both cases -- satisfying the gate on the amendment's fields is
        # not the same thing as the event itself being COMPLETE (see test 6).
        check("5c. Case A's underlying event state is still PARTIAL, not silently upgraded", store.current_state(eid_a) == "PARTIAL")
        check("5d. Case B's underlying event state is ALSO still PARTIAL -- a passing amendment gate does not, by itself, mutate event state", store.current_state(eid_b) == "PARTIAL")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_6_chronology_reconstructable_without_treating_partial_as_upgraded():
    root = temp_dir()
    try:
        store = EventStore(root)
        eid = "EVT-GOOGL-FY26Q3-ERN"
        store.append_state(eid, "REGISTERED", {"ticker": "GOOGL"})
        store.append_state(eid, "PRE_EVENT_PENDING", {})
        store.append_state(eid, "PRE_EVENT_CAPTURED", {"previous_close": 180.0, "pre_event_snapshot_asof_utc": "x", "gst_zscore": 1.0})
        store.append_state(eid, "D1_PENDING", {})
        partial = store.append_state(eid, "PARTIAL", {"open_to_close": None})
        amendment1 = store.append_amendment(eid, amends_seq=partial["seq"], corrected_fields={"open_to_close": 0.02}, reason="first recovery attempt")
        amendment2 = store.append_amendment(eid, amends_seq=partial["seq"], corrected_fields={"open_to_close": 0.021, "note": "refined estimate"}, reason="second, more precise recovery")

        records = store.read_all(eid)
        chronology = [(r["seq"], r["record_type"], r.get("state")) for r in records]
        expected = [
            (0, "STATE", "REGISTERED"),
            (1, "STATE", "PRE_EVENT_PENDING"),
            (2, "STATE", "PRE_EVENT_CAPTURED"),
            (3, "STATE", "D1_PENDING"),
            (4, "STATE", "PARTIAL"),
            (5, "AMENDMENT", None),
            (6, "AMENDMENT", None),
        ]
        check("6a. Full chronology is reconstructable in strict seq order", chronology == expected, str(chronology))

        # A reader must be able to tell that record 4 (PARTIAL) was never
        # itself edited to say COMPLETE or to carry the amended value -- its
        # own state field is untouched.
        original_partial_record = next(r for r in records if r["seq"] == 4)
        check("6b. The original PARTIAL record's own 'state' field still literally reads PARTIAL, never COMPLETE", original_partial_record["state"] == "PARTIAL")
        check("6c. The original PARTIAL record's own fields dict still shows the ORIGINAL null, not the amended value", original_partial_record["fields"].get("open_to_close") is None)

        # Both amendments reference the SAME original record -- a reader can
        # walk amends_seq to find every correction ever made to it, in order.
        amendments = [r for r in records if r["record_type"] == "AMENDMENT" and r["amends_seq"] == 4]
        check("6d. Both amendments are discoverable by walking amends_seq back to the original PARTIAL record", len(amendments) == 2)
        check("6e. Amendments are readable in the order they were made (second refines the first)", amendments[0]["corrected_fields"]["open_to_close"] == 0.02 and amendments[1]["corrected_fields"]["open_to_close"] == 0.021)

        # The event's CURRENT state (per current_state()) is still PARTIAL --
        # amendments never change what current_state() reports, since
        # current_state() only looks at STATE records, not AMENDMENT records.
        check("6f. current_state() still reports PARTIAL after two amendments -- amendments never masquerade as a state change", store.current_state(eid) == "PARTIAL")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_1_partial_record_remains_immutable_and_terminal()
    test_2_later_recovery_creates_separately_identified_amendment()
    test_3_amendment_links_to_original_record()
    test_4_original_bytes_and_hash_unchanged()
    test_5_amendment_reaches_complete_only_if_independently_valid()
    test_6_chronology_reconstructable_without_treating_partial_as_upgraded()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    else:
        print("ALL AMENDMENT SEMANTICS TESTS PASSED")
        sys.exit(0)
