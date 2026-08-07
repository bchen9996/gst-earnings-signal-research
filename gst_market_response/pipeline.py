# Orchestrates state-machine transitions for a single event, given already-
# resolved field dicts (pre-event snapshot, option benchmark, D1/D3
# intervals). This module does not call any provider itself -- callers
# (live capture code, or a test building a synthetic scenario) resolve
# fields first via providers.py/derivations.py/option_chain_adapter.py, then
# hand the resulting dicts here. Keeping orchestration separate from
# provider I/O is what makes the state-machine logic deterministically
# testable without a network.
from __future__ import annotations

from typing import Any, Optional

from .completeness import (
    evaluate_gate,
    is_valid_d1_decomposition,
    is_valid_d3_completion,
    is_valid_option_benchmark,
    is_valid_pre_event_observation,
)
from .event_record import EventStore


def register_event(store: EventStore, event_id: str, identity_fields: dict[str, Any]) -> str:
    store.append_state(event_id, "REGISTERED", identity_fields)
    return "REGISTERED"


def abstain(store: EventStore, event_id: str, reason: str) -> str:
    store.append_state(event_id, "ABSTAIN_DATA_QUALITY", {"reason": reason})
    return "ABSTAIN_DATA_QUALITY"


def capture_pre_event_and_option_benchmark(
    store: EventStore,
    event_id: str,
    pre_event_fields: dict[str, Any],
    option_benchmark_fields: dict[str, Any],
) -> str:
    """PRE_EVENT_PENDING -> PRE_EVENT_CAPTURED if both the pre-event snapshot
    and the option benchmark clear their tier gates; otherwise PARTIAL. Never
    silently promotes a partially-resolved snapshot to CAPTURED."""
    store.append_state(event_id, "PRE_EVENT_PENDING", {})
    combined = {**pre_event_fields, **option_benchmark_fields}
    if is_valid_pre_event_observation(pre_event_fields) and is_valid_option_benchmark(option_benchmark_fields):
        store.append_state(event_id, "PRE_EVENT_CAPTURED", combined)
        return "PRE_EVENT_CAPTURED"
    store.append_state(event_id, "PARTIAL", combined)
    return "PARTIAL"


def capture_d1(store: EventStore, event_id: str, d1_fields: dict[str, Any]) -> str:
    store.append_state(event_id, "D1_PENDING", {})
    if is_valid_d1_decomposition(d1_fields):
        store.append_state(event_id, "D1_COMPLETE", d1_fields)
        return "D1_COMPLETE"
    store.append_state(event_id, "PARTIAL", d1_fields)
    return "PARTIAL"


def capture_d3(store: EventStore, event_id: str, d3_fields: dict[str, Any]) -> str:
    store.append_state(event_id, "D3_PENDING", {})
    if is_valid_d3_completion(d3_fields):
        store.append_state(event_id, "COMPLETE", d3_fields)
        return "COMPLETE"
    store.append_state(event_id, "PARTIAL", d3_fields)
    return "PARTIAL"
