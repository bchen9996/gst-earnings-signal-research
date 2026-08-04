# Human-verified event registry. TASK 1 of the operational-readiness pass.
#
# This provider deliberately does NOT scrape or infer earnings timing. Every
# row is entered by a human who verified a primary source (company IR press
# release, exchange notice, SEC filing, etc.) -- see source_type/source_url/
# source_title/verified_by. BMO/AMC/INTRADAY is never inferred from price
# movement: identity.determine_release_market_session() (reused here
# unchanged) raises if it isn't independently confirmed.
#
# Storage is append-only, same discipline as event_record.py: a correction
# is a new AMENDMENT row referencing the original by row_id; the original
# row's bytes on disk are never rewritten.
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .atomic_io import append_bytes_never_truncate
from .identity import (
    EventIdentity,
    EventIdentityError,
    compute_expected_next_full_trading_session,
    determine_release_market_session,
)
from .providers import EventTimingProvider, EventTimingResult

REGISTRY_SCHEMA_VERSION = "0.1"

# Versioned identifier for the calendar this registry uses to derive
# expected_response_session. v0.1 is Mon-Fri plus a small, explicitly
# versioned, non-exhaustive set of documented US market holidays -- NOT an
# authoritative multi-decade NYSE calendar. Half-day (early-close) sessions
# are still ordinary trading days for day-count purposes (they only affect
# session-close bar time, handled in bars.py) -- listed here for provenance/
# documentation only, not because they change is_trading_day().
EXCHANGE_CALENDAR_ID = "NYSE_NASDAQ_MON_FRI_PARTIAL_HOLIDAYS_V0.1"

# Disclosed, versioned, non-exhaustive -- see EXCHANGE_CALENDAR_ID docstring
# above. Extend deliberately (new calendar version) rather than silently.
_KNOWN_MARKET_HOLIDAYS_V0_1: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # MLK Day (observed)
        date(2026, 2, 16),  # Presidents' Day (observed)
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day (observed)
        date(2026, 6, 19),  # Juneteenth (observed)
        date(2026, 7, 3),   # Independence Day (observed, falls on a Friday since July 4 is Saturday)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas (observed)
    }
)

_KNOWN_HALF_DAYS_V0_1: frozenset[date] = frozenset(
    {
        date(2026, 11, 27),  # day after Thanksgiving
        date(2026, 7, 2) if date(2026, 7, 3) in _KNOWN_MARKET_HOLIDAYS_V0_1 else date(2026, 7, 3),
    }
)


def is_trading_day_v0_1(d: date) -> bool:
    """The calendar backing EXCHANGE_CALENDAR_ID: Mon-Fri, minus the
    disclosed partial holiday list above. Half-days remain trading days."""
    if d.weekday() >= 5:
        return False
    return d not in _KNOWN_MARKET_HOLIDAYS_V0_1


def is_half_day_v0_1(d: date) -> bool:
    return d in _KNOWN_HALF_DAYS_V0_1


class EventRegistryError(ValueError):
    pass


VERIFICATION_STATUSES = ("verified", "pending", "rejected")


@dataclass(frozen=True)
class EventRegistryRow:
    row_id: str
    row_type: str  # "REGISTRATION" | "AMENDMENT"
    event_id: str
    ticker: str
    fiscal_period: str
    earnings_date: str  # ISO date
    earnings_datetime_utc: Optional[str]  # ISO datetime, nullable
    release_market_session: str  # BMO | AMC | INTRADAY
    source_url: str
    source_title: str
    source_type: str
    source_retrieved_at_utc: str
    verified_at_utc: str
    verified_by: str
    verification_status: str
    expected_response_session: str  # ISO date -- MECHANICALLY DERIVED, never manually entered
    exchange_calendar: str
    registry_version: str
    notes: str
    amends_row_id: Optional[str] = None
    written_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.verification_status not in VERIFICATION_STATUSES:
            raise EventRegistryError(f"verification_status {self.verification_status!r} must be one of {VERIFICATION_STATUSES}")
        if self.release_market_session not in ("BMO", "AMC", "INTRADAY"):
            raise EventRegistryError(f"release_market_session {self.release_market_session!r} invalid")
        if self.row_type not in ("REGISTRATION", "AMENDMENT"):
            raise EventRegistryError(f"row_type {self.row_type!r} invalid")
        if self.row_type == "AMENDMENT" and not self.amends_row_id:
            raise EventRegistryError("an AMENDMENT row must set amends_row_id")


class HumanVerifiedEventRegistry:
    """Append-only registry store. One JSONL file per registry root. Every
    write is a strict binary append (atomic_io.append_bytes_never_truncate)
    -- an amendment never rewrites the bytes of the row it corrects."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _log_path(self) -> Path:
        return self.root / "registry.jsonl"

    def read_all(self) -> list[dict]:
        path = self._log_path()
        if not path.exists():
            return []
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _next_seq(self, event_id: str, row_type: str) -> int:
        existing = [r for r in self.read_all() if r["event_id"] == event_id and r["row_type"] == row_type]
        return len(existing) + 1

    def register_verified_event(
        self,
        *,
        ticker: str,
        fiscal_period: str,
        earnings_date: date,
        earnings_datetime_utc: Optional[datetime],
        release_market_session: str,
        source_url: str,
        source_title: str,
        source_type: str,
        source_retrieved_at_utc: datetime,
        verified_at_utc: datetime,
        verified_by: str,
        verification_status: str,
        notes: str = "",
        event_type: str = "ERN",
        is_trading_day: Callable[[date], bool] = is_trading_day_v0_1,
    ) -> EventRegistryRow:
        """Registers a human-verified event. release_market_session must be
        independently confirmed by the human verifier -- this function never
        infers it. expected_response_session is NOT accepted as a parameter;
        it is always computed mechanically below, so a caller cannot
        manually override the derived day-count rule."""
        from .identity import build_event_id

        event_id = build_event_id(ticker, fiscal_period, event_type)
        # determine_release_market_session is reused unchanged -- it raises
        # if the label/source pair isn't a genuine confirmed value, which is
        # exactly the fail-closed behavior a human-entry path still needs
        # (a human could still fat-finger an unverified value in).
        confirmed_session = determine_release_market_session(release_market_session, source_type)
        expected_response_session = compute_expected_next_full_trading_session(
            earnings_date, confirmed_session, is_trading_day
        )
        row = EventRegistryRow(
            row_id=f"{event_id}-REG-{self._next_seq(event_id, 'REGISTRATION'):03d}",
            row_type="REGISTRATION",
            event_id=event_id,
            ticker=ticker,
            fiscal_period=fiscal_period,
            earnings_date=earnings_date.isoformat(),
            earnings_datetime_utc=earnings_datetime_utc.isoformat() if earnings_datetime_utc else None,
            release_market_session=confirmed_session,
            source_url=source_url,
            source_title=source_title,
            source_type=source_type,
            source_retrieved_at_utc=source_retrieved_at_utc.isoformat(),
            verified_at_utc=verified_at_utc.isoformat(),
            verified_by=verified_by,
            verification_status=verification_status,
            expected_response_session=expected_response_session.isoformat(),
            exchange_calendar=EXCHANGE_CALENDAR_ID,
            registry_version=REGISTRY_SCHEMA_VERSION,
            notes=notes,
        )
        append_bytes_never_truncate(self._log_path(), (json.dumps(asdict(row)) + "\n").encode("utf-8"))
        return row

    def amend_event(
        self,
        *,
        amends_row_id: str,
        corrected_fields: dict,
        verified_at_utc: datetime,
        verified_by: str,
        notes: str,
        is_trading_day: Callable[[date], bool] = is_trading_day_v0_1,
    ) -> EventRegistryRow:
        """Appends a new AMENDMENT row. Never rewrites amends_row_id's bytes.
        If earnings_date or release_market_session is corrected,
        expected_response_session is recomputed mechanically from the
        CORRECTED values -- never left stale, never manually supplied."""
        rows = self.read_all()
        original = next((r for r in rows if r["row_id"] == amends_row_id), None)
        if original is None:
            raise EventRegistryError(f"no existing row with row_id {amends_row_id!r}")

        merged = dict(original)
        merged.update(corrected_fields)

        confirmed_session = determine_release_market_session(
            merged["release_market_session"], merged.get("source_type")
        )
        earnings_date_obj = date.fromisoformat(merged["earnings_date"])
        expected_response_session = compute_expected_next_full_trading_session(
            earnings_date_obj, confirmed_session, is_trading_day
        )

        amendment = EventRegistryRow(
            row_id=f"{original['event_id']}-AMD-{self._next_seq(original['event_id'], 'AMENDMENT') + 1:03d}",
            row_type="AMENDMENT",
            event_id=original["event_id"],
            ticker=merged["ticker"],
            fiscal_period=merged["fiscal_period"],
            earnings_date=merged["earnings_date"],
            earnings_datetime_utc=merged.get("earnings_datetime_utc"),
            release_market_session=confirmed_session,
            source_url=merged["source_url"],
            source_title=merged["source_title"],
            source_type=merged["source_type"],
            source_retrieved_at_utc=merged["source_retrieved_at_utc"],
            verified_at_utc=verified_at_utc.isoformat(),
            verified_by=verified_by,
            verification_status=merged["verification_status"],
            expected_response_session=expected_response_session.isoformat(),
            exchange_calendar=EXCHANGE_CALENDAR_ID,
            registry_version=REGISTRY_SCHEMA_VERSION,
            notes=notes,
            amends_row_id=amends_row_id,
        )
        append_bytes_never_truncate(self._log_path(), (json.dumps(asdict(amendment)) + "\n").encode("utf-8"))
        return amendment

    def effective_row(self, event_id: str) -> Optional[dict]:
        """The base REGISTRATION row for event_id, with every subsequent
        AMENDMENT's corrected fields folded in, in order. The base row's own
        on-disk bytes are never touched by this -- this only affects what a
        READER sees as 'current'."""
        rows = [r for r in self.read_all() if r["event_id"] == event_id]
        registration = next((r for r in rows if r["row_type"] == "REGISTRATION"), None)
        if registration is None:
            return None
        effective = dict(registration)
        for amendment in [r for r in rows if r["row_type"] == "AMENDMENT"]:
            effective.update(
                {
                    k: v
                    for k, v in amendment.items()
                    if k not in ("row_id", "row_type", "amends_row_id", "written_at_utc")
                }
            )
        return effective

    def to_event_identity(self, event_id: str, company: str) -> EventIdentity:
        """Builds an EventIdentity from the registry's effective row.
        RAISES EventIdentityError -- and therefore CANNOT reach REGISTERED
        -- unless verification_status == 'verified'. This is the mechanical
        enforcement of 'a date without verified release timing cannot reach
        REGISTERED.'"""
        effective = self.effective_row(event_id)
        if effective is None:
            raise EventIdentityError(f"no registry entry for event_id {event_id!r}")
        if effective["verification_status"] != "verified":
            raise EventIdentityError(
                f"event_id {event_id!r} has verification_status={effective['verification_status']!r}, "
                f"not 'verified' -- cannot reach REGISTERED"
            )
        return EventIdentity(
            event_id=effective["event_id"],
            ticker=effective["ticker"],
            company=company,
            fiscal_period=effective["fiscal_period"],
            earnings_date=date.fromisoformat(effective["earnings_date"]),
            earnings_datetime_utc=(
                datetime.fromisoformat(effective["earnings_datetime_utc"])
                if effective.get("earnings_datetime_utc")
                else None
            ),
            release_market_session=effective["release_market_session"],
            event_time_source=effective["source_type"],
            event_time_retrieved_at_utc=datetime.fromisoformat(effective["source_retrieved_at_utc"]),
            expected_next_full_trading_session=date.fromisoformat(effective["expected_response_session"]),
        )


class RegistryBackedEventTimingProvider(EventTimingProvider):
    """Adapts HumanVerifiedEventRegistry to the EventTimingProvider
    interface (providers.py). Returns all-None timing fields -- never a
    guess -- for anything not verification_status == 'verified', so a
    caller using this provider through the generic interface fails closed
    exactly like any other EventTimingProvider implementation must."""

    def __init__(self, registry: HumanVerifiedEventRegistry):
        self._registry = registry

    def get_event_timing(self, ticker: str, fiscal_period: str) -> EventTimingResult:
        from .identity import build_event_id

        event_id = build_event_id(ticker, fiscal_period)
        effective = self._registry.effective_row(event_id)
        now = datetime.now(timezone.utc)
        if effective is None or effective["verification_status"] != "verified":
            return EventTimingResult(
                earnings_date=None,
                earnings_datetime_utc=None,
                release_market_session=None,
                event_time_source=None,
                event_time_retrieved_at_utc=now,
            )
        return EventTimingResult(
            earnings_date=date.fromisoformat(effective["earnings_date"]),
            earnings_datetime_utc=(
                datetime.fromisoformat(effective["earnings_datetime_utc"])
                if effective.get("earnings_datetime_utc")
                else None
            ),
            release_market_session=effective["release_market_session"],
            event_time_source=effective["source_type"],
            event_time_retrieved_at_utc=datetime.fromisoformat(effective["source_retrieved_at_utc"]),
        )
