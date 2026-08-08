# Append-only event state machine and record store. SPEC section 9/10.
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .atomic_io import append_bytes_never_truncate

MAINLINE_ORDER = [
    "REGISTERED",
    "PRE_EVENT_PENDING",
    "PRE_EVENT_CAPTURED",
    "D1_PENDING",
    "D1_COMPLETE",
    "D3_PENDING",
    "COMPLETE",
]
TERMINAL_STATES = {"COMPLETE", "PARTIAL", "ABSTAIN_DATA_QUALITY"}
ALL_STATES = set(MAINLINE_ORDER) | TERMINAL_STATES

SOURCE_STATUSES = ("ok", "partial", "missing", "error")

# --- PROTOCOL v0.2: PARTIAL is stage-specific -------------------------------
#
# PARTIAL can be reached from the pre-event, D1 or D3 stage, and it carries the
# fields of whichever stage failed. Selectors that searched backwards for "the
# last PARTIAL with fields" therefore mistook a D1 or D3 failure for the
# PRE-EVENT eligibility record: a D1 PARTIAL would silently replace a perfectly
# good pre-event capture's eligibility, and a "pre_event" gate check would grade
# D1 interval fields.
#
# Every v0.2 PARTIAL record persists an explicit `failure_stage`. For a legacy
# record that predates this field, the stage is DERIVED mechanically from the
# chronology -- the pending state immediately preceding the PARTIAL -- rather
# than guessed or defaulted. An unrecognised declared value resolves to no
# stage at all, so it can never be attributed to the wrong one.

FAILURE_STAGE_KEY = "failure_stage"
FAILURE_STAGE_PRE_EVENT = "pre_event"
FAILURE_STAGE_D1 = "d1"
FAILURE_STAGE_D3 = "d3"
FAILURE_STAGES = (FAILURE_STAGE_PRE_EVENT, FAILURE_STAGE_D1, FAILURE_STAGE_D3)

# The pending state that opens each stage, and the success state that closes it.
_PENDING_STATE_STAGE = {
    "PRE_EVENT_PENDING": FAILURE_STAGE_PRE_EVENT,
    "D1_PENDING": FAILURE_STAGE_D1,
    "D3_PENDING": FAILURE_STAGE_D3,
}
STAGE_SUCCESS_STATE = {
    FAILURE_STAGE_PRE_EVENT: "PRE_EVENT_CAPTURED",
    FAILURE_STAGE_D1: "D1_COMPLETE",
    FAILURE_STAGE_D3: "COMPLETE",
}


def partial_failure_stage(state_records: list[dict], index: int) -> Optional[str]:
    """Which stage does the PARTIAL record at `index` belong to?

    An explicit `failure_stage` wins. An unrecognised explicit value returns
    None (fail closed -- never reattributed). Absent it, the stage is derived
    from the most recent preceding pending state. Returns None if neither
    resolves.
    """
    record = state_records[index]
    if record.get("state") != "PARTIAL":
        return None
    declared = (record.get("fields") or {}).get(FAILURE_STAGE_KEY)
    if declared is not None:
        return declared if declared in FAILURE_STAGES else None
    for previous in reversed(state_records[:index]):
        stage = _PENDING_STATE_STAGE.get(previous.get("state"))
        if stage is not None:
            return stage
    return None


def select_stage_record(state_records: list[dict], stage: str) -> Optional[dict]:
    """The record carrying `stage`'s fields.

    The stage's own success state is preferred; only if none exists may a
    PARTIAL be used, and only one belonging to THAT stage. A D1/D3 failure can
    therefore never erase or replace pre-event eligibility.
    """
    if stage not in FAILURE_STAGES:
        raise ValueError(f"unknown stage {stage!r}; must be one of {FAILURE_STAGES}")
    success = STAGE_SUCCESS_STATE[stage]
    for record in reversed(state_records):
        if record.get("state") == success and record.get("fields"):
            return record
    for i in range(len(state_records) - 1, -1, -1):
        if state_records[i].get("fields") and partial_failure_stage(state_records, i) == stage:
            return state_records[i]
    return None


class InvalidStateTransitionError(ValueError):
    pass


def validate_transition(old_state: Optional[str], new_state: str) -> None:
    """Enforces: never backward, PARTIAL/ABSTAIN_DATA_QUALITY are terminal
    (so PARTIAL can never later become COMPLETE), and mainline states only
    advance exactly one step at a time. old_state=None means "registering
    for the first time" and only REGISTERED or ABSTAIN_DATA_QUALITY are
    valid targets."""
    if new_state not in ALL_STATES:
        raise InvalidStateTransitionError(f"unknown state {new_state!r}")

    if old_state is None:
        if new_state not in ("REGISTERED", "ABSTAIN_DATA_QUALITY"):
            raise InvalidStateTransitionError(
                f"first transition must be REGISTERED or ABSTAIN_DATA_QUALITY, got {new_state!r}"
            )
        return

    if old_state in TERMINAL_STATES:
        raise InvalidStateTransitionError(
            f"{old_state!r} is terminal -- no further state transitions allowed "
            f"(corrections must be amendment records, not a new state)"
        )

    if new_state in ("PARTIAL", "ABSTAIN_DATA_QUALITY"):
        return  # reachable from any non-terminal mainline state

    if old_state not in MAINLINE_ORDER or new_state not in MAINLINE_ORDER:
        raise InvalidStateTransitionError(f"cannot transition {old_state!r} -> {new_state!r}")

    old_idx = MAINLINE_ORDER.index(old_state)
    new_idx = MAINLINE_ORDER.index(new_state)
    if new_idx != old_idx + 1:
        raise InvalidStateTransitionError(
            f"{old_state!r} -> {new_state!r} skips or reverses mainline order "
            f"(must advance exactly one step)"
        )


@dataclass
class EventRecord:
    event_id: str
    state: str
    fields: dict[str, Any] = field(default_factory=dict)
    written_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventStore:
    """Append-only, per-event JSON-Lines log. Every write is a strict binary
    append (see atomic_io.append_bytes_never_truncate) -- prior bytes on disk
    are never rewritten, so a frozen record can never be silently edited by
    a later amendment."""

    def __init__(self, root: Path):
        self.root = root

    def _log_path(self, event_id: str) -> Path:
        return self.root / f"{event_id}.jsonl"

    def read_all(self, event_id: str) -> list[dict]:
        path = self._log_path(event_id)
        if not path.exists():
            return []
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def current_state(self, event_id: str) -> Optional[str]:
        records = self.read_all(event_id)
        state_records = [r for r in records if r["record_type"] == "STATE"]
        return state_records[-1]["state"] if state_records else None

    def append_state(self, event_id: str, new_state: str, fields: Optional[dict] = None) -> dict:
        old_state = self.current_state(event_id)
        validate_transition(old_state, new_state)
        records = self.read_all(event_id)
        record = {
            "seq": len(records),
            "record_type": "STATE",
            "event_id": event_id,
            "state": new_state,
            "fields": fields or {},
            "written_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        append_bytes_never_truncate(self._log_path(event_id), (json.dumps(record, default=str) + "\n").encode("utf-8"))
        return record

    def append_amendment(self, event_id: str, amends_seq: int, corrected_fields: dict, reason: str) -> dict:
        """Records a correction WITHOUT modifying the record at amends_seq --
        that record's bytes remain exactly as first written (see
        atomic_io.append_bytes_never_truncate). See SPEC section 9 /
        Testing requirement 14."""
        records = self.read_all(event_id)
        if amends_seq < 0 or amends_seq >= len(records):
            raise ValueError(f"amends_seq {amends_seq} out of range for event {event_id}")
        record = {
            "seq": len(records),
            "record_type": "AMENDMENT",
            "event_id": event_id,
            "amends_seq": amends_seq,
            "corrected_fields": corrected_fields,
            "reason": reason,
            "written_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        append_bytes_never_truncate(self._log_path(event_id), (json.dumps(record, default=str) + "\n").encode("utf-8"))
        return record
