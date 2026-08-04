# Tier-based completeness gates. SPEC section 10.
#
# Each tier's required-field list is enumerated explicitly here -- exactly
# once -- so "is this field required for this tier" is mechanically
# testable rather than an implicit judgment call scattered through the
# codebase. Optional fields (liquidity context) are listed separately and
# their absence never blocks a gate.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Required fields per tier (SPEC section 10.1) ---------------------------

PRE_EVENT_REQUIRED_FIELDS = ("previous_close", "pre_event_snapshot_asof_utc")
# gst_zscore is satisfied either by a real value OR an honest missing/error
# source_status -- see is_valid_pre_event_observation() below, this can't be
# expressed as a flat "non-null" list alone.

OPTION_BENCHMARK_REQUIRED_FIELDS = ("expiration", "underlying_price", "quote_timestamp_utc")
OPTION_BENCHMARK_REQUIRED_ANY_OF = ("straddle_mid", "long_executable_implied_move_cost")

D1_REQUIRED_FIELDS = ("overnight_gap", "open_to_30m", "thirty_min_to_close", "open_to_close")

D3_REQUIRED_FIELDS = ("close_T1_to_close_T2", "close_T1_to_close_T3")

# --- Explicitly optional fields (never treated as equivalent to a missing
#     required price bar -- SPEC section 10.2) ------------------------------

OPTION_BENCHMARK_OPTIONAL_FIELDS = (
    "open_interest_call", "open_interest_put", "volume_call", "volume_put",
)


def _has(fields: dict[str, Any], key: str) -> bool:
    return fields.get(key) is not None


def is_valid_pre_event_observation(fields: dict[str, Any]) -> bool:
    if not all(_has(fields, k) for k in PRE_EVENT_REQUIRED_FIELDS):
        return False
    gst_ok = _has(fields, "gst_zscore") or fields.get("source_status_gst") in ("missing", "error")
    return gst_ok


def is_valid_option_benchmark(fields: dict[str, Any]) -> bool:
    if fields.get("contract_selection_status") != "ok":
        return False
    if not all(_has(fields, k) for k in OPTION_BENCHMARK_REQUIRED_FIELDS):
        return False
    return any(_has(fields, k) for k in OPTION_BENCHMARK_REQUIRED_ANY_OF)


def is_valid_d1_decomposition(fields: dict[str, Any]) -> bool:
    return all(_has(fields, k) for k in D1_REQUIRED_FIELDS)


def is_valid_d3_completion(fields: dict[str, Any]) -> bool:
    return all(_has(fields, k) for k in D3_REQUIRED_FIELDS)


@dataclass(frozen=True)
class GateResult:
    tier: str
    passed: bool
    missing_required_fields: tuple[str, ...]


def evaluate_gate(tier: str, fields: dict[str, Any]) -> GateResult:
    checkers = {
        "pre_event": (is_valid_pre_event_observation, PRE_EVENT_REQUIRED_FIELDS),
        "option_benchmark": (is_valid_option_benchmark, OPTION_BENCHMARK_REQUIRED_FIELDS),
        "d1": (is_valid_d1_decomposition, D1_REQUIRED_FIELDS),
        "d3": (is_valid_d3_completion, D3_REQUIRED_FIELDS),
    }
    if tier not in checkers:
        raise ValueError(f"unknown completeness tier {tier!r}")
    fn, required = checkers[tier]
    passed = fn(fields)
    missing = tuple(k for k in required if not _has(fields, k)) if not passed else ()
    return GateResult(tier=tier, passed=passed, missing_required_fields=missing)
