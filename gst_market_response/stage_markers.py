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
from .event_record import (
    FAILURE_STAGE_D1,
    FAILURE_STAGE_D3,
    FAILURE_STAGE_PRE_EVENT,
    TERMINAL_STATES,
    EventStore,
    partial_failure_stage,
    select_stage_record,
)
from .response_magnitude import (
    D1_ABS_FIELD_MAP,
    D3_ABS_FIELD_MAP,
    response_magnitude_block,
)

STAGE_PRE_EVENT = "PRE_EVENT_CAPTURE"
STAGE_D1 = "D1_CAPTURE"
STAGE_FINAL = "FINAL_COMPLETION"
STAGES = (STAGE_PRE_EVENT, STAGE_D1, STAGE_FINAL)

# The stage each marker attests to, and the success state that must already be
# recorded before it may be written. A PARTIAL is acceptable ONLY when it
# belongs to this same stage -- see _stage_state_is_allowed(). A D1 PARTIAL can
# no longer satisfy the requirement for a PRE_EVENT_CAPTURE marker.
_STAGE_SUCCESS_STATE = {
    STAGE_PRE_EVENT: ("PRE_EVENT_CAPTURED",),
    STAGE_D1: ("D1_COMPLETE",),
    STAGE_FINAL: tuple(sorted(TERMINAL_STATES)),
}
_STAGE_PARTIAL_STAGE = {
    STAGE_PRE_EVENT: FAILURE_STAGE_PRE_EVENT,
    STAGE_D1: FAILURE_STAGE_D1,
}

# Provenance echoed into every marker so it ties out to the event record
# without re-deriving anything.
PROVENANCE_KEYS = (
    "ticker", "source_csv_path", "source_csv_sha256", "source_marker_path",
    "source_marker_sha256", "panel_status", "panel_row_count",
    "panel_unique_ticker_count", "panel_all_six_fields_clean_count",
    "run_date", "price_asof_date", "pre_event_snapshot_asof_utc",
    "research_commit_sha", "methodology_version", "adapter_schema_version",
    # Per-leg statuses for the two legs that previously inherited the price
    # leg's status. Persisted so the marker records WHICH leg backed each of
    # the six fields, not merely that some status was successful.
    "source_status_iv", "source_status_iv_raw",
    "source_status_realized_vol", "source_status_realized_vol_raw",
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
    wrong fields entirely. The first v0.2 correction searched backwards for
    PRE_EVENT_CAPTURED *or* PARTIAL, which was still wrong: PARTIAL is reachable
    from D1 and D3 too, so a D1 failure appearing later in the log won the
    reverse search and replaced the pre-event eligibility with D1 interval
    fields. select_stage_record() prefers the stage's own success state and
    accepts only a PARTIAL belonging to THIS stage.
    """
    states = [r for r in store.read_all(event_id) if r["record_type"] == "STATE"]
    return select_stage_record(states, FAILURE_STAGE_PRE_EVENT)


def _response_magnitude(states: list[dict]) -> dict[str, Any]:
    """The canonical abs_* values as PERSISTED on the D1 and D3 stage records.

    Read back from the stored record, never recomputed here, so a marker
    attests to what was actually written. A stage that has not been captured
    contributes nothing rather than a block of nulls -- absence stays absence.
    Historical records written before this field existed simply yield {}.
    """
    block: dict[str, Any] = {}
    for stage_key, field_map in ((FAILURE_STAGE_D1, D1_ABS_FIELD_MAP),
                                 (FAILURE_STAGE_D3, D3_ABS_FIELD_MAP)):
        record = select_stage_record(states, stage_key)
        if record and record.get("fields"):
            block.update(response_magnitude_block(record["fields"], field_map))
    return block


def _stage_state_is_allowed(stage: str, states: list[dict]) -> bool:
    """May a `stage` marker be written given the event's current chronology?"""
    final_state = states[-1]["state"]
    if final_state in _STAGE_SUCCESS_STATE[stage]:
        return True
    if final_state != "PARTIAL":
        return False
    wanted = _STAGE_PARTIAL_STAGE.get(stage)
    if wanted is None:  # STAGE_FINAL: PARTIAL is terminal and always qualifies
        return "PARTIAL" in _STAGE_SUCCESS_STATE[stage]
    return partial_failure_stage(states, len(states) - 1) == wanted


def build_stage_marker(store: EventStore, event_id: str, stage: str) -> dict:
    """Assemble a marker payload. Pure: no write, no clock beyond written_at."""
    if stage not in STAGES:
        raise StageMarkerError(f"unknown stage {stage!r}")
    states = [r for r in store.read_all(event_id) if r["record_type"] == "STATE"]
    if not states:
        raise StageMarkerError(f"no state records for {event_id}; refusing to write a marker")
    final_state = states[-1]["state"]

    if not _stage_state_is_allowed(stage, states):
        allowed = _STAGE_SUCCESS_STATE[stage]
        partial_stage = _STAGE_PARTIAL_STAGE.get(stage)
        raise StageMarkerError(
            f"stage {stage} marker requires the event to be in {allowed}"
            + (f" (or PARTIAL with failure_stage={partial_stage!r})" if partial_stage else "")
            + f", but it is {final_state!r}"
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

    # Canonical absolute response magnitudes, echoed from whichever durable
    # stage record carries them. Read back from the STORED record rather than
    # recomputed, so the marker attests to what was actually persisted.
    marker["response_magnitude"] = _response_magnitude(states)

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
                "is_full_data_complete", "module_eligibility", "provenance",
                "response_magnitude"):
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
