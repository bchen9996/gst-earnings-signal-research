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
