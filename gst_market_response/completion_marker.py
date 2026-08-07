# Completion marker + gate-check exit codes. SPEC "Implementation" bullet:
# "a completion marker" and "nonzero exit on a failed required-data gate".
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .completeness import evaluate_gate
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
    latest_fields = state_records[-1]["fields"]
    if not latest_fields:
        return EXIT_INCONCLUSIVE
    result = evaluate_gate(tier, latest_fields)
    return EXIT_OK if result.passed else EXIT_GATE_FAILED
