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


# ---------------------------------------------------------------------------
# PROTOCOL AMENDMENT v0.2 (2026-08-08): lifecycle / eligibility separation
# ---------------------------------------------------------------------------
#
# WHAT CHANGED AND WHY
#
# v0.1 used a single state variable for two different concepts: (1) which
# scheduled collection stages were captured, and (2) which evidence modules are
# analytically valid. Because PRE_EVENT_CAPTURED required BOTH the pre-event
# core gate AND the option-benchmark gate, an unavailable *optional* option
# benchmark drove the event to PARTIAL -- a terminal state -- which made D1/D2/D3
# uncollectable even when the six-field attention/market core was perfectly
# valid. That is avoidable event attrition: a missing optional module destroyed
# a valid core observation.
#
# This amendment separates the two concepts. It does NOT declare options
# unnecessary, and it never treats absent options as present:
#
#   * the core module is eligible only when the EXISTING core gate passes;
#   * the option module is eligible only when the EXISTING option gate passes;
#   * joint analyses need both;
#   * missing options stay null -- never zero, inferred, indicative, or valid;
#   * a core-only event is NEVER "full-data complete".
#
# No existing threshold, required-field list, quote-age limit, skew limit, or
# validity rule is modified. is_valid_pre_event_observation() and
# is_valid_option_benchmark() are called unchanged; everything below is
# additive.

PROTOCOL_VERSION = "0.2"
PROTOCOL_AMENDED_AT_UTC = "2026-08-08"
PROTOCOL_AMENDMENT_ID = "AMD-001-lifecycle-eligibility-separation"

# The ONLY methodology identifier the v0.2 capture path accepts. Blank,
# arbitrary, stale and v0.1 values are rejected by the CLI and the orchestrator.
METHODOLOGY_VERSION_V0_2 = "market_response_v0.2"

# --- STRICT v0.2 CORE GATE --------------------------------------------------
#
# The legacy gate (is_valid_pre_event_observation) required only
# previous_close + pre_event_snapshot_asof_utc, with gst_zscore satisfiable by
# an honest missing/error status. It is PRESERVED UNCHANGED because existing
# tests and the v0.1 contract depend on it.
#
# v0.2 adds a STRICTER gate used by the new pre-event capture path: all six
# Phase 2 panel fields must be present with a successful source status.
#
# NOTE ON implied_volatility -- read this before changing it.
# SPEC v0.1 section 5 and the field dictionary state that the panel's generic
# `implied_volatility` must NEVER be used as an earnings-implied-move baseline;
# option_chain_adapter is the only legitimate source for an implied-move-shaped
# field. That prohibition is UNCHANGED. v0.2 persists the panel's IV strictly as
# SIX-FIELD COMPLETENESS PROVENANCE, under the deliberately namespaced key
# `panel_implied_volatility`, and it is never exposed as `implied_volatility`,
# never fed to the option benchmark, and never usable as an implied-move value.
# Persisting a field as evidence and using it as a benchmark are different acts;
# only the second is prohibited.

STRICT_CORE_SIX_FIELDS = (
    "gst_zscore",
    "wiki_zscore",
    "panel_implied_volatility",
    "realized_volatility",
    "previous_close",          # the protocol's canonical price field
    "volume",
)

# Source statuses that count as a successful observation. Mirrors
# phase2_adapter's normalised success categories; a fallback-served value is a
# success but is not "fresh" -- that distinction lives in the raw status.
STRICT_CORE_SUCCESS_STATUSES = ("ok", "ok_recent_cache_fallback")

# Per-field source-status key. EVERY field is backed by the panel leg that
# actually produced it.
#
# CORRECTION (second audit pass): implied volatility and realized volatility
# previously inherited `source_status_price`. The Phase 2 panel does not work
# that way -- it emits five independent per-leg statuses (gst_status,
# wiki_status, iv_status, realized_vol_status, price_history_status), and the
# option-chain leg that produces implied_volatility fails independently of the
# price-history leg that produces price/volume. Backing IV with the price
# status meant a failed iv_status passed the six-field gate whenever price
# history happened to be OK, which is exactly the "treat missing data as
# present" failure the gate exists to prevent. previous_close and volume DO
# both come from the price-history leg, so they legitimately share it.
STRICT_CORE_STATUS_KEY = {
    "gst_zscore": "source_status_gst",
    "wiki_zscore": "source_status_wiki",
    "panel_implied_volatility": "source_status_iv",
    "realized_volatility": "source_status_realized_vol",
    "previous_close": "source_status_price",
    "volume": "source_status_price",
}

STRICT_CORE_REQUIRED_PROVENANCE = ("pre_event_snapshot_asof_utc",)


@dataclass(frozen=True)
class StrictCoreResult:
    passed: bool
    missing_fields: tuple[str, ...]
    bad_status_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"strict_core_passed": self.passed,
                "strict_core_missing_fields": list(self.missing_fields),
                "strict_core_bad_status_fields": list(self.bad_status_fields)}


def evaluate_strict_core_v0_2(fields: dict[str, Any]) -> StrictCoreResult:
    """All six panel fields present AND each backed by a successful source
    status. A legitimate numeric 0.0 with a successful status PASSES; missingness
    is never inferred from a zero value."""
    missing = [k for k in STRICT_CORE_SIX_FIELDS if fields.get(k) is None]
    missing += [k for k in STRICT_CORE_REQUIRED_PROVENANCE if _missing_prov(fields, k)]
    bad = []
    for f in STRICT_CORE_SIX_FIELDS:
        if fields.get(f) is None:
            continue  # already counted as missing
        status = fields.get(STRICT_CORE_STATUS_KEY[f])
        if status not in STRICT_CORE_SUCCESS_STATUSES:
            bad.append(f)
    return StrictCoreResult(passed=not missing and not bad,
                            missing_fields=tuple(missing), bad_status_fields=tuple(bad))


def _missing_prov(fields: dict[str, Any], key: str) -> bool:
    v = fields.get(key)
    return v is None or (isinstance(v, str) and v.strip() == "")


def is_valid_strict_core_v0_2(fields: dict[str, Any]) -> bool:
    return evaluate_strict_core_v0_2(fields).passed


class OptionBenchmarkDisposition:
    """Explicit, operator-declared disposition of the option benchmark.

    Unavailability is NEVER inferred from `{}` or from null fields -- the
    caller must say which of these applies, and each carries its own
    obligations. Anything else fails closed.
    """

    VALID_VERIFIED = "VALID_VERIFIED"
    UNAVAILABLE_NO_VERIFIED_SOURCE = "UNAVAILABLE_NO_VERIFIED_SOURCE"
    LOOKUP_FAILED = "LOOKUP_FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"

    ALL = (VALID_VERIFIED, UNAVAILABLE_NO_VERIFIED_SOURCE, LOOKUP_FAILED, NOT_ATTEMPTED)
    # Only a verified benchmark is ever analytically eligible.
    ANALYTICALLY_ELIGIBLE = (VALID_VERIFIED,)
    # These three require null benchmark values plus a nonblank reason.
    REQUIRE_NULL_VALUES_AND_REASON = (
        UNAVAILABLE_NO_VERIFIED_SOURCE, LOOKUP_FAILED, NOT_ATTEMPTED,
    )


# Feeds acceptable as a verified option benchmark. Alpaca's `indicative` feed
# is a MODIFIED derivative of OPRA and is explicitly not acceptable -- it may
# never be relabelled as unavailable-but-fine, nor promoted to OPRA-valid.
ACCEPTED_OPTION_FEEDS = ("opra",)

# Completeness tiers for the pre-event stage. Ordered least -> most complete.
PRE_EVENT_TIER_CORE_INVALID = "core_invalid"
PRE_EVENT_TIER_CORE_ONLY = "core_only_no_option_benchmark"
PRE_EVENT_TIER_CORE_AND_OPTION = "core_and_option_benchmark"
PRE_EVENT_TIERS = (
    PRE_EVENT_TIER_CORE_INVALID, PRE_EVENT_TIER_CORE_ONLY, PRE_EVENT_TIER_CORE_AND_OPTION,
)
# The ONLY tier that may ever be described as full-data complete.
FULL_DATA_COMPLETE_TIER = PRE_EVENT_TIER_CORE_AND_OPTION

# Hypothesis families and the module eligibility each one requires.
HYPOTHESIS_CORE_ATTENTION_RESPONSE = "core_attention_vs_equity_response"
HYPOTHESIS_OPTIONS_IMPLIED_MOVE = "options_implied_move"
HYPOTHESIS_JOINT_ATTENTION_OPTIONS = "joint_attention_plus_options"
HYPOTHESIS_CLASSES = (
    HYPOTHESIS_CORE_ATTENTION_RESPONSE,
    HYPOTHESIS_OPTIONS_IMPLIED_MOVE,
    HYPOTHESIS_JOINT_ATTENTION_OPTIONS,
)


class OptionDispositionError(ValueError):
    """Fail-closed: the option disposition is unknown, blank, or contradicts
    the artifact supplied with it. The caller must correct the artifact or
    declare an explicit no-verified-source path; nothing is written."""


class LegacyRecordError(ValueError):
    """A pre-amendment record lacks the module-eligibility fields. Raised so a
    legacy record can never be SILENTLY reinterpreted under v0.2 semantics."""


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def option_benchmark_value_fields(fields: dict[str, Any]) -> tuple[str, ...]:
    """Every benchmark-carrying field that must be null when the benchmark is
    not VALID_VERIFIED."""
    return tuple(OPTION_BENCHMARK_REQUIRED_FIELDS) + tuple(OPTION_BENCHMARK_REQUIRED_ANY_OF)


def validate_option_disposition(option_fields: dict[str, Any]) -> str:
    """Validate the declared disposition against the artifact supplied.

    Returns the disposition on success. Raises OptionDispositionError on any
    unknown/blank disposition, on a VALID_VERIFIED claim that fails the
    existing option gate or is not on an accepted feed, or on an
    unavailable/failed/not-attempted claim that still carries benchmark values
    or omits its reason.
    """
    if option_fields is None:
        raise OptionDispositionError(
            "no option_benchmark_fields supplied; an explicit disposition is required "
            f"(one of {OptionBenchmarkDisposition.ALL}) -- unavailability is never inferred"
        )
    disposition = option_fields.get("option_benchmark_status")
    if _blank(disposition):
        raise OptionDispositionError(
            "option_benchmark_status is missing or blank; unavailability is never inferred "
            f"from an empty dict or null fields. Declare one of {OptionBenchmarkDisposition.ALL}"
        )
    if disposition not in OptionBenchmarkDisposition.ALL:
        raise OptionDispositionError(
            f"unknown option_benchmark_status {disposition!r}; must be one of "
            f"{OptionBenchmarkDisposition.ALL}"
        )

    if disposition == OptionBenchmarkDisposition.VALID_VERIFIED:
        feed = option_fields.get("option_feed")
        if _blank(feed):
            raise OptionDispositionError(
                "VALID_VERIFIED requires an explicit option_feed (provider identity); "
                "a benchmark with no stated feed cannot be verified"
            )
        if str(feed).strip().lower() not in ACCEPTED_OPTION_FEEDS:
            raise OptionDispositionError(
                f"option_feed={feed!r} is not an accepted verified feed {ACCEPTED_OPTION_FEEDS}. "
                f"Indicative quotes are a modified derivative of OPRA and may not be presented "
                f"as VALID_VERIFIED, nor relabelled as unavailable"
            )
        if not is_valid_option_benchmark(option_fields):
            raise OptionDispositionError(
                "option_benchmark_status=VALID_VERIFIED but the artifact fails the existing "
                "option-benchmark gate (contract_selection_status/required fields). Correct the "
                "artifact or declare LOOKUP_FAILED / UNAVAILABLE_NO_VERIFIED_SOURCE explicitly"
            )
        return disposition

    # UNAVAILABLE_NO_VERIFIED_SOURCE / LOOKUP_FAILED / NOT_ATTEMPTED
    if _blank(option_fields.get("option_benchmark_unavailable_reason")):
        raise OptionDispositionError(
            f"option_benchmark_status={disposition} requires a nonblank "
            f"option_benchmark_unavailable_reason recording why no verified benchmark exists"
        )
    populated = [k for k in option_benchmark_value_fields(option_fields)
                 if option_fields.get(k) is not None]
    if populated:
        raise OptionDispositionError(
            f"option_benchmark_status={disposition} requires every benchmark value to be null, "
            f"but these are populated: {sorted(populated)}. Missing options are null -- never "
            f"zero, inferred, or partially carried"
        )
    return disposition


@dataclass(frozen=True)
class ModuleEligibility:
    """Per-module analytical eligibility, kept separate from lifecycle state."""

    core_pre_event_eligible: bool
    option_benchmark_eligible: bool
    joint_full_eligible: bool
    pre_event_completeness_tier: str
    option_benchmark_status: str
    option_benchmark_unavailable_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "core_pre_event_eligible": self.core_pre_event_eligible,
            "option_benchmark_eligible": self.option_benchmark_eligible,
            "joint_full_eligible": self.joint_full_eligible,
            "pre_event_completeness_tier": self.pre_event_completeness_tier,
            "option_benchmark_status": self.option_benchmark_status,
            "option_benchmark_unavailable_reason": self.option_benchmark_unavailable_reason,
            "protocol_version": PROTOCOL_VERSION,
        }

    @property
    def is_full_data_complete(self) -> bool:
        """True ONLY for a core+option event. Lifecycle COMPLETE never implies
        this -- see is_full_data_complete() free function."""
        return self.pre_event_completeness_tier == FULL_DATA_COMPLETE_TIER


def evaluate_pre_event_modules(
    pre_event_fields: dict[str, Any],
    option_benchmark_fields: dict[str, Any],
) -> ModuleEligibility:
    """Evaluate both modules independently using the EXISTING gates.

    Raises OptionDispositionError before any caller writes anything if the
    option disposition is unknown/blank or contradicts its artifact.
    """
    disposition = validate_option_disposition(option_benchmark_fields)
    core_ok = is_valid_pre_event_observation(pre_event_fields)
    option_ok = (
        disposition in OptionBenchmarkDisposition.ANALYTICALLY_ELIGIBLE
        and is_valid_option_benchmark(option_benchmark_fields)
    )
    if not core_ok:
        tier = PRE_EVENT_TIER_CORE_INVALID
    elif option_ok:
        tier = PRE_EVENT_TIER_CORE_AND_OPTION
    else:
        tier = PRE_EVENT_TIER_CORE_ONLY
    return ModuleEligibility(
        core_pre_event_eligible=core_ok,
        option_benchmark_eligible=option_ok,
        joint_full_eligible=core_ok and option_ok,
        pre_event_completeness_tier=tier,
        option_benchmark_status=disposition,
        option_benchmark_unavailable_reason=option_benchmark_fields.get(
            "option_benchmark_unavailable_reason"
        ),
    )


def evaluate_pre_event_modules_v0_2(
    strict_core_fields: dict[str, Any],
    option_benchmark_fields: dict[str, Any],
) -> ModuleEligibility:
    """v0.2 module eligibility: the CORE module is judged by the STRICT
    six-field gate, not by the v0.1 gate.

    CORRECTION (second audit pass): the v0.2 capture path called
    evaluate_pre_event_modules(), whose core test is
    is_valid_pre_event_observation() -- previous_close + a timestamp, with
    gst_zscore satisfiable by an honest missing/error status. So an observation
    missing wiki_zscore, IV, realized volatility or volume entirely could still
    be recorded as PRE_EVENT_CAPTURED with core_pre_event_eligible=True. The
    orchestrator ran the strict gate as a separate report check, but the field
    persisted on the record came from the weaker one, and any caller reaching
    the pipeline directly bypassed the strict gate altogether.

    The option module is evaluated by the unchanged v0.1 option gate and the
    same explicit-disposition contract; no option threshold moves here.
    """
    disposition = validate_option_disposition(option_benchmark_fields)
    core_ok = evaluate_strict_core_v0_2(strict_core_fields).passed
    option_ok = (
        disposition in OptionBenchmarkDisposition.ANALYTICALLY_ELIGIBLE
        and is_valid_option_benchmark(option_benchmark_fields)
    )
    if not core_ok:
        tier = PRE_EVENT_TIER_CORE_INVALID
    elif option_ok:
        tier = PRE_EVENT_TIER_CORE_AND_OPTION
    else:
        tier = PRE_EVENT_TIER_CORE_ONLY
    return ModuleEligibility(
        core_pre_event_eligible=core_ok,
        option_benchmark_eligible=option_ok,
        joint_full_eligible=core_ok and option_ok,
        pre_event_completeness_tier=tier,
        option_benchmark_status=disposition,
        option_benchmark_unavailable_reason=option_benchmark_fields.get(
            "option_benchmark_unavailable_reason"
        ),
    )


def read_module_eligibility(record_fields: dict[str, Any]) -> ModuleEligibility:
    """Read eligibility back off a stored record.

    A pre-amendment (v0.1) record has none of these fields. Rather than
    defaulting -- which would silently reinterpret a legacy record as
    core-only, or worse as fully complete -- this raises LegacyRecordError so
    the migration decision is explicit.
    """
    required = ("core_pre_event_eligible", "option_benchmark_eligible",
                "joint_full_eligible", "pre_event_completeness_tier",
                "option_benchmark_status")
    missing = [k for k in required if k not in record_fields]
    if missing:
        raise LegacyRecordError(
            f"record predates protocol v{PROTOCOL_VERSION} (missing {sorted(missing)}); "
            f"refusing to reinterpret it under lifecycle/eligibility separation. Migrate it "
            f"explicitly or read it under v0.1 semantics"
        )
    tier = record_fields["pre_event_completeness_tier"]
    if tier not in PRE_EVENT_TIERS:
        raise LegacyRecordError(f"unknown pre_event_completeness_tier {tier!r}")
    return ModuleEligibility(
        core_pre_event_eligible=bool(record_fields["core_pre_event_eligible"]),
        option_benchmark_eligible=bool(record_fields["option_benchmark_eligible"]),
        joint_full_eligible=bool(record_fields["joint_full_eligible"]),
        pre_event_completeness_tier=tier,
        option_benchmark_status=record_fields["option_benchmark_status"],
        option_benchmark_unavailable_reason=record_fields.get("option_benchmark_unavailable_reason"),
    )


def is_eligible_for_hypothesis(hypothesis: str, eligibility: ModuleEligibility) -> bool:
    """Mechanical hypothesis-family gate.

    Lifecycle state is deliberately NOT an argument: reaching lifecycle
    COMPLETE can never, by itself, make an event eligible for an
    options-linked hypothesis.
    """
    if hypothesis not in HYPOTHESIS_CLASSES:
        raise ValueError(f"unknown hypothesis family {hypothesis!r}; must be one of {HYPOTHESIS_CLASSES}")
    if hypothesis == HYPOTHESIS_CORE_ATTENTION_RESPONSE:
        return eligibility.core_pre_event_eligible
    if hypothesis == HYPOTHESIS_OPTIONS_IMPLIED_MOVE:
        return eligibility.option_benchmark_eligible
    return eligibility.joint_full_eligible


def is_full_data_complete(lifecycle_state: str, eligibility: ModuleEligibility) -> bool:
    """Full-data completeness requires BOTH lifecycle completion AND the
    core+option tier. A core-only event that reaches lifecycle COMPLETE is
    still not full-data complete."""
    return lifecycle_state == "COMPLETE" and eligibility.is_full_data_complete


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
