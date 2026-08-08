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
    evaluate_pre_event_modules,
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
    """PRE_EVENT_PENDING -> PRE_EVENT_CAPTURED when the pre-event CORE gate
    passes; otherwise PARTIAL.

    PROTOCOL v0.2 (2026-08-08) -- lifecycle/eligibility separation. Under v0.1
    this required BOTH the core gate and the option gate, so an unavailable
    optional option benchmark drove a perfectly valid core observation to
    PARTIAL, which is terminal, and destroyed D1/D2/D3 collection. The state
    now records the COLLECTION LIFECYCLE; analytical eligibility is carried
    alongside it, per module.

    This does not make an absent benchmark valid. Option values stay null, the
    option module is marked ineligible, the event is classified
    `core_only_no_option_benchmark`, and it can never be called full-data
    complete. Neither existing gate is modified or bypassed.

    Fails closed BEFORE any write (raises OptionDispositionError, nothing
    appended) when the option disposition is unknown/blank, or when a supplied
    artifact contradicts its declared disposition -- a malformed, crossed,
    stale, indicative or timestamp-less artifact is never quietly downgraded to
    ordinary unavailability.
    """
    # --- validate everything first; no bytes are written until this returns ---
    eligibility = evaluate_pre_event_modules(pre_event_fields, option_benchmark_fields)

    combined = {**pre_event_fields, **option_benchmark_fields, **eligibility.as_dict()}

    store.append_state(event_id, "PRE_EVENT_PENDING", {})
    if eligibility.core_pre_event_eligible:
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
