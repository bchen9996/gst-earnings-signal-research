# Deterministic, network-free operations planner.
#
# Turns a VERIFIED registry row into the mechanical schedule needed to run one
# event's capture: the pre-event anchor session, the release timestamp, and the
# D1/D2/D3 response sessions, each with UTC and exchange-local open/close, plus
# the earliest instant the Alpaca 15-minute freshness gate would permit a
# retrieval for that session.
#
# WHAT THIS MODULE IS NOT
#
# It plans; it never acts. By construction it:
#   * imports no provider module and constructs no provider,
#   * opens no socket and needs no credential,
#   * never transitions event state or touches the append-only EventStore,
#   * never writes to the registry,
#   * never infers a date from price, volume, attention or any market data.
#
# Every session is derived from the merged XNYS calendar
# (gst_market_response.exchange_calendar, backed by exchange_calendars) and
# every identity rule from gst_market_response.identity /
# gst_market_response.event_registry. Nothing about trading-day arithmetic is
# reimplemented here.
#
# Fail-closed: any registry, identity, calendar or timing inconsistency raises
# OperationsPlanError rather than returning a partial plan.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .constants import is_locked_universe_member
from .event_registry import HumanVerifiedEventRegistry, REGISTRY_SCHEMA_VERSION
from .exchange_calendar import (
    EXCHANGE_CALENDAR_ID,
    is_early_close,
    is_trading_day,
    next_session,
    previous_session,
    session_close_utc,
    session_open_utc,
)
from .identity import EVENT_ID_RE, VALID_RELEASE_SESSIONS

# Mirrors alpaca_provider.MIN_END_AGE_MINUTES. Imported by value rather than by
# module so that planning never pulls a provider module into sys.modules; the
# drift test asserts the two stay equal.
ALPACA_MIN_END_AGE_MINUTES = 15

PLANNER_VERSION = "0.1"
PLAN_SCHEMA_VERSION = "0.1"

# Findings of the 2026-08-07 capture-gap audit, carried into every plan so the
# plan can never read as "ready". Each entry cites the code inspected. These
# are statements about what the MERGED code does and does not support; none of
# them is resolved by this planning pass.
KNOWN_CAPTURE_BLOCKERS: tuple[dict, ...] = (
    {
        "id": "BLK-OPT-1",
        "severity": "hard",
        "area": "option benchmark",
        "finding": (
            "No operationally verified option-quote source exists. Alpaca contains zero "
            "option support (no option/chain/expiry/strike references in alpaca_provider.py), "
            "so the only option-chain route is yfinance via GST_Option_Chain_Core."
            " option_chain_adapter.py has no provider-eligibility concept at all -- it never "
            "consults is_eligible_for_real_event, which is a bars-provider notion. The option "
            "path therefore has no clearance decision of its own."
        ),
        "evidence": [
            "gst_market_response/alpaca_provider.py (no option endpoint)",
            "gst_market_response/option_chain_adapter.py (no eligibility gate)",
            "GST_Option_Chain_Core.get_option_snapshot (yfinance chain only)",
        ],
        "decision_required_from_human": (
            "Choose and operationally validate an option-quote source with per-quote "
            "timestamps, or decide the first event proceeds without an option benchmark and "
            "accept the resulting completeness tier."
        ),
    },
    {
        "id": "BLK-OPT-2",
        "severity": "hard",
        "area": "option quote provenance",
        "finding": (
            "build_option_benchmark() requires the CALLER to supply quote_timestamp_utc and "
            "underlying_price. A yfinance option chain carries no per-quote timestamp, so that "
            "value would be asserted by the caller rather than observed from the venue. The "
            "adapter's own skew and crossed-quote gates "
            "(MAX_COMPATIBLE_QUOTE_SKEW_SECONDS=120, REJECTED_BID_GT_ASK, "
            "REJECTED_INCOMPATIBLE_TIMESTAMPS) can only be as trustworthy as that asserted input."
        ),
        "evidence": ["gst_market_response/option_chain_adapter.py:build_option_benchmark"],
        "decision_required_from_human": "Establish an observed, venue-sourced quote timestamp before any real option capture.",
    },
    {
        "id": "BLK-ORCH-1",
        "severity": "hard",
        "area": "orchestration",
        "finding": (
            "No end-to-end pre-event capture command exists. build_option_benchmark() is "
            "referenced only by test_market_response_decomposition.py; nothing in production "
            "calls it. pipeline.capture_pre_event_and_option_benchmark() accepts two "
            "already-built dicts and fetches nothing. gst_market_response/cli.py exposes only a "
            "gate check plus completion-marker write (--store-root/--event-id/--tier). "
            "Nothing wires Phase 2 panel -> phase2_adapter -> option benchmark -> EventStore."
        ),
        "evidence": [
            "gst_market_response/pipeline.py:capture_pre_event_and_option_benchmark",
            "gst_market_response/cli.py",
            "grep: build_option_benchmark called only from tests",
        ],
        "decision_required_from_human": "Authorize an orchestration design only after BLK-OPT-1/2 are resolved.",
    },
    {
        "id": "BLK-STALE-1",
        "severity": "material",
        "area": "stale-input protection",
        "finding": (
            "import_pre_event_fields_for_ticker() takes only "
            "(csv_path, marker_path, ticker, research_commit_sha, methodology_version). It hashes "
            "both inputs and cross-verifies the marker's counts against the CSV, but it has no "
            "expected-session parameter, so it cannot reject a panel from the wrong date. A stale "
            "but internally consistent panel would pass every existing check."
        ),
        "evidence": ["gst_market_response/phase2_adapter.py:import_pre_event_fields_for_ticker"],
        "decision_required_from_human": (
            "Decide whether the anchor-session binding is enforced in code or by operator "
            "checklist before the first real capture."
        ),
    },
    {
        "id": "BLK-PANEL-1",
        "severity": "material",
        "area": "Phase 2 panel availability",
        "finding": (
            "A pre-event snapshot needs a COMPLETE Phase 2 panel for the anchor session. The most "
            "recent recorded live attempts were PARTIAL, and the Phase 2 lane's own remaining "
            "blocker (intermittent per-article Wikipedia 404s) is unresolved. Panel availability "
            "on 2026-09-02 is therefore not guaranteed."
        ),
        "evidence": ["Live Signal Engine/Phase2 Failure Evidence/*", "CHANGELOG.md Phase 2 entries"],
        "decision_required_from_human": "Confirm the panel-run plan for the anchor session.",
    },
)

_ET = "America/New_York"


class OperationsPlanError(ValueError):
    """Fail-closed: the plan must not be produced as specified."""


def _et_zone():
    from zoneinfo import ZoneInfo

    return ZoneInfo(_ET)


def _local(dt_utc: datetime) -> str:
    return dt_utc.astimezone(_et_zone()).isoformat()


@dataclass(frozen=True)
class SessionPlan:
    """One trading session, fully specified in UTC with exchange-local mirrors."""

    label: str
    session_date: str
    is_early_close: bool
    open_utc: str
    close_utc: str
    open_local_et: str
    close_local_et: str
    # Earliest wall-clock instant at which Alpaca's freshness gate would accept
    # a request whose end timestamp is this session's final expected bar start.
    earliest_provider_retrieval_utc: str
    earliest_provider_retrieval_local_et: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _build_session(label: str, d: date) -> SessionPlan:
    if not is_trading_day(d):
        raise OperationsPlanError(f"{label}: {d.isoformat()} is not an XNYS trading session")
    open_utc = session_open_utc(d)
    close_utc = session_close_utc(d)
    if close_utc <= open_utc:
        raise OperationsPlanError(f"{label}: close {close_utc} is not after open {open_utc}")
    # The provider's freshness gate is applied to the request's END timestamp.
    # The research path's end is the final expected 5-minute bar START, i.e.
    # one interval before the close (see alpaca_provider: "the correct end is
    # the FINAL EXPECTED BAR START -- 15:55 ET"). Retrieval becomes permissible
    # MIN_END_AGE_MINUTES after that instant.
    final_bar_start = close_utc - timedelta(minutes=5)
    earliest = final_bar_start + timedelta(minutes=ALPACA_MIN_END_AGE_MINUTES)
    return SessionPlan(
        label=label,
        session_date=d.isoformat(),
        is_early_close=is_early_close(d),
        open_utc=open_utc.isoformat(),
        close_utc=close_utc.isoformat(),
        open_local_et=_local(open_utc),
        close_local_et=_local(close_utc),
        earliest_provider_retrieval_utc=earliest.isoformat(),
        earliest_provider_retrieval_local_et=_local(earliest),
    )


def _parse_dt(raw: Optional[str], field_name: str) -> datetime:
    if raw is None or str(raw).strip() == "":
        raise OperationsPlanError(f"{field_name} is missing from the registry row")
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperationsPlanError(f"{field_name}={raw!r} is not a valid ISO-8601 timestamp") from exc
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise OperationsPlanError(f"{field_name}={raw!r} is timezone-naive; refusing to plan from it")
    return dt.astimezone(timezone.utc)


def load_verified_registration(registry_path: Path, event_id: str) -> dict:
    """Return the single usable REGISTRATION row for event_id, or fail closed.

    Rejects: absent, duplicated, unverified, superseded-by-amendment-into-an-
    unusable-state, non-locked-universe, and malformed-identity events.
    """
    registry_path = Path(registry_path)
    if not registry_path.exists():
        raise OperationsPlanError(f"registry file not found: {registry_path}")
    if registry_path.name != "registry.jsonl":
        raise OperationsPlanError(
            f"expected a registry.jsonl written by HumanVerifiedEventRegistry, got {registry_path.name}"
        )

    if not EVENT_ID_RE.match(event_id):
        raise OperationsPlanError(f"event_id {event_id!r} does not match the protocol/event-id pattern")

    registry = HumanVerifiedEventRegistry(registry_path.parent)
    rows = registry.read_all()

    regs = [r for r in rows if r.get("event_id") == event_id and r.get("row_type") == "REGISTRATION"]
    if not regs:
        raise OperationsPlanError(f"no REGISTRATION row for event_id {event_id!r}")
    if len(regs) > 1:
        raise OperationsPlanError(
            f"{len(regs)} REGISTRATION rows for {event_id!r} -- duplicate registration, refusing to plan"
        )

    # effective_row applies every later amendment on top of the base row. It
    # raises for an unverified event, which is exactly the fail-closed
    # behaviour wanted here.
    effective = registry.effective_row(event_id)
    if effective is None:
        raise OperationsPlanError(f"registry has no effective row for {event_id!r}")
    if effective.get("verification_status") != "verified":
        raise OperationsPlanError(
            f"{event_id!r} has verification_status="
            f"{effective.get('verification_status')!r}; only 'verified' events may be planned"
        )
    if not is_locked_universe_member(effective.get("ticker", "")):
        raise OperationsPlanError(
            f"ticker {effective.get('ticker')!r} is not in the locked 24-ticker universe"
        )
    session = effective.get("release_market_session")
    if session not in VALID_RELEASE_SESSIONS:
        raise OperationsPlanError(
            f"release_market_session {session!r} is not one of {VALID_RELEASE_SESSIONS}"
        )
    cal = effective.get("exchange_calendar", "")
    if not str(cal).startswith("XNYS"):
        raise OperationsPlanError(
            f"registry row was written against exchange_calendar={cal!r}; this planner only "
            f"plans XNYS events (running calendar: {EXCHANGE_CALENDAR_ID})"
        )
    return effective


def _response_sessions(earnings_date: date, release_session: str) -> tuple[date, date, date]:
    """D1/D2/D3, purely from the XNYS calendar.

    D1 is the first FULL session able to price the release: the earnings date
    itself for a BMO release, otherwise the next session. D2 and D3 are the
    next two sessions after that. Weekends and exchange holidays are skipped by
    the calendar, never by arithmetic here.
    """
    if release_session == "BMO":
        d1 = earnings_date if is_trading_day(earnings_date) else next_session(earnings_date)
    elif release_session in ("AMC", "INTRADAY"):
        # INTRADAY shares AMC's treatment: the first FULL session that can
        # price the release is the following one, because the release landed
        # inside a session that was already partly traded.
        d1 = next_session(earnings_date)
    else:  # pragma: no cover - guarded by load_verified_registration
        raise OperationsPlanError(f"unsupported release_market_session {release_session!r}")
    d2 = next_session(d1)
    d3 = next_session(d2)
    return d1, d2, d3


def build_operations_plan(
    *,
    registry_path: Path,
    event_id: str,
    company_name: str,
    generated_at_utc: datetime,
    planning_commit: str,
    methodology_version: str,
) -> dict:
    """The whole plan, as a plain dict ready to serialise. Pure: same inputs
    produce byte-identical output (the caller supplies generated_at_utc rather
    than the function reading a clock)."""
    row = load_verified_registration(Path(registry_path), event_id)

    earnings_date = date.fromisoformat(row["earnings_date"])
    release_session = row["release_market_session"]
    event_dt = _parse_dt(row.get("earnings_datetime_utc"), "earnings_datetime_utc")

    if event_dt.date() != earnings_date:
        raise OperationsPlanError(
            f"earnings_datetime_utc date {event_dt.date()} disagrees with earnings_date {earnings_date}"
        )

    # --- mechanical AMC/BMO cross-check against the calendar -----------------
    if is_trading_day(earnings_date):
        close = session_close_utc(earnings_date)
        open_ = session_open_utc(earnings_date)
        if release_session == "AMC" and event_dt <= close:
            raise OperationsPlanError(
                f"registry says AMC but event {event_dt.isoformat()} is not after the "
                f"{earnings_date} close {close.isoformat()}"
            )
        if release_session == "BMO" and event_dt >= open_:
            raise OperationsPlanError(
                f"registry says BMO but event {event_dt.isoformat()} is not before the "
                f"{earnings_date} open {open_.isoformat()}"
            )

    # --- anchor: last FULL session strictly before the event -----------------
    if release_session == "BMO":
        anchor = previous_session(earnings_date) if is_trading_day(earnings_date) else previous_session(earnings_date)
    else:
        # AMC/INTRADAY: the release lands after (or during) the earnings-date
        # session, so the last session that is entirely pre-event is the one
        # before it.
        anchor = previous_session(earnings_date) if is_trading_day(earnings_date) else previous_session(earnings_date)

    d1, d2, d3 = _response_sessions(earnings_date, release_session)

    if not (anchor < earnings_date <= d1 or anchor < earnings_date < d1):
        raise OperationsPlanError(f"anchor {anchor} / earnings {earnings_date} / D1 {d1} are not ordered")
    if not (d1 < d2 < d3):
        raise OperationsPlanError(f"response sessions are not strictly increasing: {d1}, {d2}, {d3}")

    # Sessions the calendar skipped between D1 and D3 -- recorded so a human
    # can see WHY a gap exists (e.g. Labor Day) rather than trusting it.
    skipped: list[dict] = []
    cur = d1 + timedelta(days=1)
    while cur < d3:
        if not is_trading_day(cur):
            skipped.append({"date": cur.isoformat(), "weekday": cur.strftime("%A"), "xnys_open": False})
        cur += timedelta(days=1)

    anchor_plan = _build_session("pre_event_anchor", anchor)
    d1_plan = _build_session("D1", d1)
    d2_plan = _build_session("D2", d2)
    d3_plan = _build_session("D3", d3)

    plan: dict[str, Any] = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "planner_version": PLANNER_VERSION,
        "planning_commit": planning_commit,
        "methodology_version": methodology_version,
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "exchange_calendar": EXCHANGE_CALENDAR_ID,
        "generated_at_utc": generated_at_utc.astimezone(timezone.utc).isoformat(),
        "event": {
            "event_id": row["event_id"],
            "ticker": row["ticker"],
            "company_name": company_name,
            "fiscal_period": row["fiscal_period"],
            "earnings_date": row["earnings_date"],
            "event_datetime_utc": event_dt.isoformat(),
            "event_datetime_local_et": _local(event_dt),
            "release_market_session": release_session,
            "expected_response_session_from_registry": row.get("expected_response_session"),
        },
        "registry_provenance": {
            "source_registration_row_id": row["row_id"],
            "registry_path": Path(registry_path).as_posix(),
            "verification_status": row["verification_status"],
            "verified_by": row["verified_by"],
            "verified_at_utc": row["verified_at_utc"],
            "source_url": row["source_url"],
            "source_title": row["source_title"],
            "source_type": row["source_type"],
            "source_retrieved_at_utc": row["source_retrieved_at_utc"],
        },
        "sessions": {
            "pre_event_anchor": anchor_plan.as_dict(),
            "D1": d1_plan.as_dict(),
            "D2": d2_plan.as_dict(),
            "D3": d3_plan.as_dict(),
        },
        "non_sessions_between_d1_and_d3": skipped,
        "required_inputs": {
            "pre_event_snapshot": [
                "Phase 2 daily panel CSV for the anchor session (explicit path)",
                "paired Phase 2 completion marker JSON (explicit path)",
                "option benchmark: expiration, underlying_price, quote_timestamp_utc "
                "(+ straddle_mid OR long_executable_implied_move_cost)",
            ],
            "D1": ["intraday 5-minute bars for D1", "benchmark ETF bars for D1", "anchor previous_close"],
            "D2_D3": ["daily closes for D1, D2, D3", "benchmark ETF closes for the same sessions"],
        },
        "required_completeness_gates": {
            "pre_event": "completeness.is_valid_pre_event_observation",
            "option_benchmark": "completeness.is_valid_option_benchmark",
            "d1": "completeness.is_valid_d1_decomposition",
            "d3": "completeness.is_valid_d3_completion",
        },
        "prohibited_actions": [
            "planner must never call a market-data or attention provider",
            "planner must never transition event state or write to the EventStore",
            "planner must never modify the registry",
            "planner must never infer a date from price, volume or attention data",
            "no Layer B emission before the linked Layer A label is frozen AND revealed per protocol",
        ],
        "unresolved_blockers": [dict(b) for b in KNOWN_CAPTURE_BLOCKERS],
    }
    return plan


def plan_content_sha256(plan: dict) -> str:
    """Deterministic integrity field. Hashes the plan with any existing
    integrity block removed, so the value can be embedded without self-
    reference — the same convention the freeze manifests use (hash the content,
    store the digest beside it)."""
    body = {k: v for k, v in plan.items() if k != "integrity"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def finalize_plan(plan: dict) -> dict:
    plan = dict(plan)
    plan["integrity"] = {
        "algorithm": "sha256",
        "canonicalization": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False), 'integrity' key excluded",
        "plan_content_sha256": plan_content_sha256(plan),
    }
    return plan


__all__ = [
    "ALPACA_MIN_END_AGE_MINUTES",
    "OperationsPlanError",
    "PLANNER_VERSION",
    "PLAN_SCHEMA_VERSION",
    "SessionPlan",
    "build_operations_plan",
    "finalize_plan",
    "load_verified_registration",
    "plan_content_sha256",
]
