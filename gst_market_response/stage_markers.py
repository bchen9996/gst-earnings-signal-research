# Immutable stage markers (PROTOCOL v0.2).
#
# v0.1 had a single `{event_id}_COMPLETION_MARKER.json` that had to be REPLACED
# as the event progressed -- the synthetic chronology test literally unlinked it
# to move from PRE_EVENT_CAPTURED to COMPLETE. Deleting evidence to make
# progress is exactly the failure mode this project forbids everywhere else, so
# v0.2 replaces it with one write-once marker per durable stage:
#
#   {event_id}_PRE_EVENT_CAPTURE_MARKER.json
#   {event_id}_D1_CAPTURE_MARKER.json
#   {event_id}_FINAL_COMPLETION_MARKER.json     <- only at a terminal state
#
# Every marker is written with atomic_write_json_no_overwrite(), so an existing
# marker is never replaced; a second attempt raises. The v0.1
# `{event_id}_COMPLETION_MARKER.json` writer is left in place, unchanged, for
# the legacy path and legacy tests.
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .atomic_io import ImmutableArtifactExistsError, atomic_write_json_no_overwrite
from .completeness import (
    PROTOCOL_VERSION,
    LegacyRecordError,
    is_full_data_complete,
    read_module_eligibility,
)
from .event_record import TERMINAL_STATES, EventStore

STAGE_PRE_EVENT = "PRE_EVENT_CAPTURE"
STAGE_D1 = "D1_CAPTURE"
STAGE_FINAL = "FINAL_COMPLETION"
STAGES = (STAGE_PRE_EVENT, STAGE_D1, STAGE_FINAL)

# The stage each marker attests to, and the lifecycle state that must already be
# recorded before it may be written.
_STAGE_REQUIRED_STATE = {
    STAGE_PRE_EVENT: ("PRE_EVENT_CAPTURED", "PARTIAL"),
    STAGE_D1: ("D1_COMPLETE", "PARTIAL"),
    STAGE_FINAL: tuple(sorted(TERMINAL_STATES)),
}

# Provenance echoed into every marker so it ties out to the event record
# without re-deriving anything.
PROVENANCE_KEYS = (
    "ticker", "source_csv_path", "source_csv_sha256", "source_marker_path",
    "source_marker_sha256", "panel_status", "panel_row_count",
    "panel_unique_ticker_count", "panel_all_six_fields_clean_count",
    "run_date", "price_asof_date", "pre_event_snapshot_asof_utc",
    "research_commit_sha", "methodology_version", "adapter_schema_version",
)


class StageMarkerError(ValueError):
    """Fail-closed marker condition."""


def marker_path(root: Path, event_id: str, stage: str) -> Path:
    if stage not in STAGES:
        raise StageMarkerError(f"unknown stage {stage!r}; must be one of {STAGES}")
    return Path(root) / f"{event_id}_{stage}_MARKER.json"


def _pre_event_record(store: EventStore, event_id: str) -> Optional[dict]:
    """The pre-event stage record -- NOT simply the latest record.

    v0.1's gate read the last state record, so after D1/D3 it evaluated the
    wrong fields entirely. Eligibility and provenance always come from the
    pre-event stage.
    """
    states = [r for r in store.read_all(event_id) if r["record_type"] == "STATE"]
    return next((r for r in reversed(states)
                 if r["state"] in ("PRE_EVENT_CAPTURED", "PARTIAL") and r.get("fields")), None)


def build_stage_marker(store: EventStore, event_id: str, stage: str) -> dict:
    """Assemble a marker payload. Pure: no write, no clock beyond written_at."""
    if stage not in STAGES:
        raise StageMarkerError(f"unknown stage {stage!r}")
    states = [r for r in store.read_all(event_id) if r["record_type"] == "STATE"]
    if not states:
        raise StageMarkerError(f"no state records for {event_id}; refusing to write a marker")
    final_state = states[-1]["state"]

    allowed = _STAGE_REQUIRED_STATE[stage]
    if final_state not in allowed:
        raise StageMarkerError(
            f"stage {stage} marker requires the event to be in {allowed}, but it is {final_state!r}"
        )
    if stage == STAGE_FINAL and final_state not in TERMINAL_STATES:
        raise StageMarkerError(
            f"the final completion marker may only be written at a terminal state; "
            f"event is {final_state!r}"
        )

    pre = _pre_event_record(store, event_id)
    marker: dict[str, Any] = {
        "event_id": event_id,
        "stage": stage,
        "protocol_version": PROTOCOL_VERSION,
        "lifecycle_state": final_state,
        "state_transition_count": len(states),
        "state_chronology": [r["state"] for r in states],
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if pre is None:
        marker["module_eligibility"] = None
        marker["module_eligibility_note"] = "no pre-event stage recorded"
        marker["is_full_data_complete"] = False
        marker["provenance"] = None
        return marker

    try:
        elig = read_module_eligibility(pre["fields"])
    except LegacyRecordError as exc:
        marker["module_eligibility"] = None
        marker["module_eligibility_note"] = f"legacy pre-amendment record: {exc}"
        marker["is_full_data_complete"] = False
    else:
        marker["module_eligibility"] = elig.as_dict()
        marker["is_full_data_complete"] = is_full_data_complete(final_state, elig)

    marker["provenance"] = {k: pre["fields"].get(k) for k in PROVENANCE_KEYS}
    return marker


def write_stage_marker(root: Path, event_id: str, stage: str, store: EventStore) -> dict:
    """Write-once. Raises ImmutableArtifactExistsError if the marker exists."""
    payload = build_stage_marker(store, event_id, stage)
    atomic_write_json_no_overwrite(marker_path(root, event_id, stage), payload)
    return payload


def verify_marker_ties_out(root: Path, event_id: str, stage: str, store: EventStore) -> tuple[bool, list[str]]:
    """Does an existing marker match what the event record says now?

    Used by recovery: a marker that agrees is left alone; a marker that
    disagrees fails closed rather than being regenerated or replaced.
    """
    path = marker_path(root, event_id, stage)
    if not path.exists():
        return False, ["marker does not exist"]
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    expected = build_stage_marker(store, event_id, stage)
    diffs = []
    for key in ("event_id", "stage", "lifecycle_state", "state_chronology",
                "is_full_data_complete", "module_eligibility", "provenance"):
        if on_disk.get(key) != expected.get(key):
            diffs.append(key)
    return (not diffs), diffs


def recover_missing_marker(root: Path, event_id: str, stage: str, store: EventStore) -> dict:
    """Deterministic recovery for a crash BETWEEN the state append and its marker.

    Regenerates a MISSING marker only. It never deletes or replaces evidence:
      * marker absent   -> rebuild from the event record and write once;
      * marker present and tying out -> return it untouched;
      * marker present and disagreeing -> fail closed.
    The event record is never appended to here, so recovery cannot duplicate a
    state transition.
    """
    path = marker_path(root, event_id, stage)
    if path.exists():
        ok, diffs = verify_marker_ties_out(root, event_id, stage, store)
        if ok:
            return json.loads(path.read_text(encoding="utf-8"))
        raise StageMarkerError(
            f"existing {stage} marker disagrees with the event record on {diffs}; "
            f"failing closed rather than overwriting evidence"
        )
    return write_stage_marker(root, event_id, stage, store)


__all__ = [
    "PROVENANCE_KEYS", "STAGES", "STAGE_D1", "STAGE_FINAL", "STAGE_PRE_EVENT",
    "StageMarkerError", "build_stage_marker", "marker_path",
    "recover_missing_marker", "verify_marker_ties_out", "write_stage_marker",
]
