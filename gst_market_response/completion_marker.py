# Completion marker + gate-check exit codes. SPEC "Implementation" bullet:
# "a completion marker" and "nonzero exit on a failed required-data gate".
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .completeness import (
    PROTOCOL_VERSION,
    LegacyRecordError,
    evaluate_gate,
    is_full_data_complete,
    read_module_eligibility,
)
from .event_record import EventStore

# Exit codes -- mirrors this project's existing PASS/INCONCLUSIVE/FAIL
# 3-state convention (see phase2_live_smoke_wiki_equivalence.py) rather than
# inventing a new scheme: 0 = gate passed, 1 = gate failed (required data
# missing), 2 = event not found / inconclusive (cannot evaluate at all).
EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_INCONCLUSIVE = 2


def write_completion_marker(root: Path, event_id: str, store: EventStore) -> dict[str, Any]:
    records = store.read_all(event_id)
    state_records = [r for r in records if r["record_type"] == "STATE"]
    final_state = state_records[-1]["state"] if state_records else None
    marker = {
        "event_id": event_id,
        "final_state": final_state,
        "state_transition_count": len(state_records),
        "amendment_count": len([r for r in records if r["record_type"] == "AMENDMENT"]),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    # PROTOCOL v0.2: the marker must never let a reader mistake lifecycle
    # completion for full-data completeness. Surface the per-module eligibility
    # recorded at the pre-event stage alongside the lifecycle state. A legacy
    # (v0.1) record carries none of these fields; that is reported explicitly
    # rather than defaulted, so a pre-amendment event is never silently
    # presented as core-only or as fully complete.
    marker["protocol_version"] = PROTOCOL_VERSION
    eligibility_source = next(
        (r for r in reversed(state_records)
         if r["state"] in ("PRE_EVENT_CAPTURED", "PARTIAL") and r.get("fields")),
        None,
    )
    if eligibility_source is None:
        marker["module_eligibility"] = None
        marker["module_eligibility_note"] = "no pre-event stage recorded for this event"
        marker["is_full_data_complete"] = False
    else:
        try:
            elig = read_module_eligibility(eligibility_source["fields"])
        except LegacyRecordError as exc:
            marker["module_eligibility"] = None
            marker["module_eligibility_note"] = f"legacy pre-amendment record: {exc}"
            marker["is_full_data_complete"] = False
        else:
            marker["module_eligibility"] = elig.as_dict()
            marker["is_full_data_complete"] = is_full_data_complete(final_state, elig)

    atomic_write_json(root / f"{event_id}_COMPLETION_MARKER.json", marker)
    return marker


def check_required_gate(store: EventStore, event_id: str, tier: str) -> int:
    """Returns an exit code: EXIT_OK if the given tier's gate passes on the
    event's latest fields, EXIT_GATE_FAILED if it fails, EXIT_INCONCLUSIVE if
    the event has no recorded fields to check at all."""
    records = store.read_all(event_id)
    state_records = [r for r in records if r["record_type"] == "STATE"]
    if not state_records:
        return EXIT_INCONCLUSIVE

    # PROTOCOL v0.2 correction: read the fields belonging to the tier being
    # checked, not simply the LATEST record. v0.1 always used state_records[-1],
    # so once D1/D3 had been captured a "pre_event"/"option_benchmark" check
    # silently evaluated D1/D3 fields and reported a meaningless result.
    _STAGE_FOR_TIER = {
        "pre_event": ("PRE_EVENT_CAPTURED", "PARTIAL"),
        "option_benchmark": ("PRE_EVENT_CAPTURED", "PARTIAL"),
        "d1": ("D1_COMPLETE", "PARTIAL"),
        "d3": ("COMPLETE", "PARTIAL"),
    }
    wanted = _STAGE_FOR_TIER.get(tier)
    if wanted is None:
        source = state_records[-1]
    else:
        source = next((r for r in reversed(state_records)
                       if r["state"] in wanted and r.get("fields")), None)
    if source is None or not source.get("fields"):
        return EXIT_INCONCLUSIVE
    result = evaluate_gate(tier, source["fields"])
    return EXIT_OK if result.passed else EXIT_GATE_FAILED
