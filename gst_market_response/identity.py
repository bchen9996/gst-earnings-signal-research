# Event identity: event_id format, BMO/AMC/INTRADAY fail-closed
# determination, and the D1 trading-session day-count rule.
#
# event_id format is mirrored (not imported -- the Event Dossier Protocol
# lives on a different worktree/branch, phase2-event-dossiers, and is not
# reachable at runtime from here) from
# Event_Dossier_Protocol/validator/validate_event_dossier.py's EVENT_ID_RE,
# so records emitted here join cleanly to that protocol's events.csv on
# event_id without a parallel ID scheme.
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Optional

from .constants import is_locked_universe_member

EVENT_ID_RE = re.compile(r"^EVT-[A-Z0-9-]+-FY\d{2}Q\d-[A-Z]+$")

VALID_RELEASE_SESSIONS = ("BMO", "AMC", "INTRADAY")


class EventIdentityError(ValueError):
    """Raised when an event cannot be registered as given -- caller must not
    fabricate a substitute value; the event should be routed to
    ABSTAIN_DATA_QUALITY instead of being force-registered."""


def build_event_id(ticker: str, fiscal_period: str, event_type: str = "ERN") -> str:
    event_id = f"EVT-{ticker}-{fiscal_period}-{event_type}"
    if not EVENT_ID_RE.match(event_id):
        raise EventIdentityError(f"constructed event_id fails its own format check: {event_id!r}")
    return event_id


@dataclass(frozen=True)
class EventIdentity:
    event_id: str
    ticker: str
    company: str
    fiscal_period: str
    earnings_date: date
    earnings_datetime_utc: Optional[datetime]
    release_market_session: str  # one of VALID_RELEASE_SESSIONS
    event_time_source: str
    event_time_retrieved_at_utc: datetime
    expected_next_full_trading_session: date

    def __post_init__(self) -> None:
        if not EVENT_ID_RE.match(self.event_id):
            raise EventIdentityError(f"event_id fails format check: {self.event_id!r}")
        if not is_locked_universe_member(self.ticker):
            raise EventIdentityError(f"ticker {self.ticker!r} is not in the locked 24-ticker universe")
        if self.release_market_session not in VALID_RELEASE_SESSIONS:
            raise EventIdentityError(
                f"release_market_session {self.release_market_session!r} must be one of {VALID_RELEASE_SESSIONS}"
            )


def determine_release_market_session(
    raw_session_label: Optional[str], event_time_source: Optional[str]
) -> str:
    """Fail-closed session classification. NEVER infers BMO/AMC from price
    movement -- the only inputs are an explicit label from a genuine timing
    source and that source's own identifier. Raises EventIdentityError if
    either is missing or the label isn't one of the three valid values;
    callers must catch this and route the event to ABSTAIN_DATA_QUALITY
    rather than guessing a default."""
    if not event_time_source:
        raise EventIdentityError("no event_time_source provided -- cannot verify release timing")
    if raw_session_label not in VALID_RELEASE_SESSIONS:
        raise EventIdentityError(
            f"release session {raw_session_label!r} is not independently verified as one of {VALID_RELEASE_SESSIONS}"
        )
    return raw_session_label


def next_trading_day(d: date, is_trading_day: Callable[[date], bool]) -> date:
    """Smallest date strictly after d for which is_trading_day(d) is True."""
    from datetime import timedelta

    candidate = d + timedelta(days=1)
    # Bounded search -- a real trading calendar always has a next session
    # within a couple of weeks; an unbounded loop here would hang on a
    # misconfigured calendar rather than failing loudly.
    for _ in range(30):
        if is_trading_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    raise EventIdentityError(f"no trading day found within 30 days after {d} -- calendar looks broken")


def compute_expected_next_full_trading_session(
    earnings_date: date,
    release_market_session: str,
    is_trading_day: Callable[[date], bool],
) -> date:
    """SPEC section 3.2 / Event Dossier Protocol's D1 day-count rule:
    - BMO: same session as earnings_date if that date is itself a trading
      day; otherwise (weekend/holiday BMO release) the next trading day.
    - AMC or INTRADAY: the next trading day strictly after earnings_date,
      regardless of whether earnings_date itself was a trading day (an
      INTRADAY release's own, interrupted session is excluded from D1)."""
    if release_market_session not in VALID_RELEASE_SESSIONS:
        raise EventIdentityError(f"release_market_session {release_market_session!r} not verified")
    if release_market_session == "BMO" and is_trading_day(earnings_date):
        return earnings_date
    return next_trading_day(earnings_date, is_trading_day)
