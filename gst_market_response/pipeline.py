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
    evaluate_pre_event_modules_v0_2,
    is_valid_d1_decomposition,
    is_valid_d3_completion,
    is_valid_option_benchmark,
    is_valid_pre_event_observation,
)
from .event_record import (
    FAILURE_STAGE_D1,
    FAILURE_STAGE_D3,
    FAILURE_STAGE_KEY,
    FAILURE_STAGE_PRE_EVENT,
    EventStore,
)
from .response_magnitude import (
    D1_ABS_FIELD_MAP,
    D3_ABS_FIELD_MAP,
    apply_absolute_fields,
)


def register_event(store: EventStore, event_id: str, identity_fields: dict[str, Any]) -> str:
    store.append_state(event_id, "REGISTERED", identity_fields)
    return "REGISTERED"


def abstain(store: EventStore, event_id: str, reason: str) -> str:
    store.append_state(event_id, "ABSTAIN_DATA_QUALITY", {"reason": reason})
    return "ABSTAIN_DATA_QUALITY"


def capture_pre_event_and_option_benchmark_v0_1(
    store: EventStore,
    event_id: str,
    pre_event_fields: dict[str, Any],
    option_benchmark_fields: dict[str, Any],
) -> str:
    """LEGACY v0.1 capture. Judges the core with is_valid_pre_event_observation().

    Kept, explicitly version-named, for v0.1 callers and the v0.1 regression
    suite. It is NOT the v0.2 path and must never be reached from the v0.2
    orchestrator -- see capture_pre_event_and_option_benchmark_v0_2().

    PRE_EVENT_PENDING -> PRE_EVENT_CAPTURED when the pre-event CORE gate
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
    store.append_state(event_id, "PARTIAL",
                       {**combined, FAILURE_STAGE_KEY: FAILURE_STAGE_PRE_EVENT})
    return "PARTIAL"


def capture_pre_event_and_option_benchmark_v0_2(
    store: EventStore,
    event_id: str,
    strict_core_fields: dict[str, Any],
    option_benchmark_fields: dict[str, Any],
    *,
    pending_fields: dict[str, Any] | None = None,
    resume_from_existing_pending: bool = False,
) -> str:
    """PROTOCOL v0.2 capture. The core is judged by the STRICT six-field gate.

    This is the ONLY capture entry point the v0.2 orchestrator may use. It
    cannot fall through to the v0.1 gate: eligibility comes from
    evaluate_pre_event_modules_v0_2(), which calls evaluate_strict_core_v0_2().

    `pending_fields` is the canonical capture fingerprint persisted ON the
    PRE_EVENT_PENDING record so that a crash between the two appends is
    resumable, and only by an input-identical rerun.

    `resume_from_existing_pending` continues a dangling PRE_EVENT_PENDING that
    the caller has already proved fingerprint-identical. It appends NO second
    pending record and never rewrites or deletes the first one.

    Neither the option gate nor the disposition contract changes here: an
    absent benchmark stays null, the option module stays ineligible, and the
    event is classified core-only and can never be full-data complete.
    """
    # --- validate everything first; no bytes are written until this returns ---
    eligibility = evaluate_pre_event_modules_v0_2(strict_core_fields, option_benchmark_fields)

    combined = {**strict_core_fields, **option_benchmark_fields, **eligibility.as_dict()}

    if not resume_from_existing_pending:
        store.append_state(event_id, "PRE_EVENT_PENDING", dict(pending_fields or {}))
    if eligibility.core_pre_event_eligible:
        store.append_state(event_id, "PRE_EVENT_CAPTURED", combined)
        return "PRE_EVENT_CAPTURED"
    store.append_state(event_id, "PARTIAL",
                       {**combined, FAILURE_STAGE_KEY: FAILURE_STAGE_PRE_EVENT})
    return "PARTIAL"


# There is deliberately NO unversioned public capture function. An unversioned
# name is how the v0.2 orchestrator silently reached the v0.1 core gate in the
# first place, so the old name now raises with instructions rather than
# resolving to either behaviour.
_REMOVED_UNVERSIONED = (
    "pipeline.capture_pre_event_and_option_benchmark has been split by protocol "
    "version and no unversioned capture function exists. Call "
    "capture_pre_event_and_option_benchmark_v0_2() (strict six-field core gate) "
    "or, for the legacy v0.1 contract only, "
    "capture_pre_event_and_option_benchmark_v0_1(). An unversioned name is how "
    "the v0.2 path previously bypassed the strict gate."
)


def __getattr__(name: str):  # module-level, PEP 562
    if name == "capture_pre_event_and_option_benchmark":
        raise AttributeError(_REMOVED_UNVERSIONED)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def capture_d1(store: EventStore, event_id: str, d1_fields: dict[str, Any]) -> str:
    """Persist the D1 decomposition, with its canonical abs_* counterparts.

    The absolute fields are derived here (SPEC v0.1: "abs() of the
    corresponding signed return, stored alongside it, never replacing it"), not
    chosen by the caller. Derivation and conflict validation happen BEFORE the
    first append, so a caller whose supplied abs_* value disagrees with abs() of
    its signed counterpart raises AbsoluteFieldConflictError with zero bytes
    written -- not even D1_PENDING.

    D1_REQUIRED_FIELDS is unchanged: the abs_* fields are stored outputs, never
    a new completeness requirement, so the gate below still sees exactly the
    four signed intervals it always did.
    """
    fields = apply_absolute_fields(d1_fields, D1_ABS_FIELD_MAP)
    store.append_state(event_id, "D1_PENDING", {})
    if is_valid_d1_decomposition(fields):
        store.append_state(event_id, "D1_COMPLETE", fields)
        return "D1_COMPLETE"
    # PROTOCOL v0.2: a PARTIAL says WHICH stage failed, so a D1 failure can
    # never be mistaken for the pre-event eligibility record.
    store.append_state(event_id, "PARTIAL", {**fields, FAILURE_STAGE_KEY: FAILURE_STAGE_D1})
    return "PARTIAL"


def capture_d3(store: EventStore, event_id: str, d3_fields: dict[str, Any]) -> str:
    """Persist the D3 completion, with its canonical abs_* counterparts.

    Same contract as capture_d1(): derived, not caller-chosen; validated before
    the first byte; D3_REQUIRED_FIELDS unchanged.
    """
    fields = apply_absolute_fields(d3_fields, D3_ABS_FIELD_MAP)
    store.append_state(event_id, "D3_PENDING", {})
    if is_valid_d3_completion(fields):
        store.append_state(event_id, "COMPLETE", fields)
        return "COMPLETE"
    store.append_state(event_id, "PARTIAL", {**fields, FAILURE_STAGE_KEY: FAILURE_STAGE_D3})
    return "PARTIAL"
