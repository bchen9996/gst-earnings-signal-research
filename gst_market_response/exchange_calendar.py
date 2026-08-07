# Authoritative XNYS exchange calendar. SECTION C of the second
# operational-readiness pass: replaces the hand-maintained partial holiday
# list (event_registry.is_trading_day_v0_1, SUPERSEDED but left in place for
# auditability -- see that module's own docstring) as the operational
# source of trading-session/holiday/early-close/DST truth.
#
# Backed by the `exchange_calendars` package (pinned in requirements.txt).
# This module is a thin, deterministic wrapper -- it does no network I/O of
# its own; `exchange_calendars` ships its own bundled holiday data.
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import exchange_calendars as xcals

EXCHANGE_CALENDAR_ID = f"XNYS_exchange_calendars_v{__import__('importlib.metadata', fromlist=['version']).version('exchange_calendars')}"

_ET_REGULAR_OPEN = time(9, 30)
BAR_INTERVAL_MINUTES = 5

_calendar = xcals.get_calendar("XNYS")


class ExchangeCalendarError(ValueError):
    pass


def is_trading_day(d: date) -> bool:
    return bool(_calendar.is_session(d.isoformat()))


def previous_session(d: date) -> date:
    """Most recent XNYS session strictly before d -- d itself need not be a
    session (e.g. a weekend/holiday date is a valid input)."""
    snapped = _calendar.date_to_session(d.isoformat(), direction="previous")
    if snapped.date() == d:
        # d was itself a session -- "strictly before" means one further back.
        snapped = _calendar.previous_session(d.isoformat())
    return snapped.date()


def next_session(d: date) -> date:
    """Next XNYS session strictly after d -- d itself need not be a session
    (e.g. a weekend/holiday date is a valid input)."""
    snapped = _calendar.date_to_session(d.isoformat(), direction="next")
    if snapped.date() == d:
        # d was itself a session -- "strictly after" means one further ahead.
        snapped = _calendar.next_session(d.isoformat())
    return snapped.date()


def session_open_utc(d: date) -> datetime:
    if not is_trading_day(d):
        raise ExchangeCalendarError(f"{d} is not an XNYS trading session")
    ts = _calendar.session_open(d.isoformat())
    return ts.to_pydatetime().astimezone(timezone.utc)


def session_close_utc(d: date) -> datetime:
    if not is_trading_day(d):
        raise ExchangeCalendarError(f"{d} is not an XNYS trading session")
    ts = _calendar.session_close(d.isoformat())
    return ts.to_pydatetime().astimezone(timezone.utc)


def is_early_close(d: date) -> bool:
    """True if the session's actual close is earlier than the ordinary
    16:00 ET regular close (i.e. a half day)."""
    if not is_trading_day(d):
        return False
    close_utc = session_close_utc(d)
    close_et = close_utc.astimezone(_ET_ZONE())
    return close_et.time() < time(16, 0)


def _ET_ZONE():
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionBarBoundaries:
    session_date: str
    open_utc: str
    close_utc: str
    is_early_close: bool
    first_bar_start_utc: str
    last_bar_start_utc: str
    expected_bar_count: int


def expected_bar_starts_utc(d: date) -> list[datetime]:
    """THE authoritative, ordered list of 5-minute bar START timestamps for
    session d, derived from the calendar's own real open/close.

    Every consumer that needs to know "which bars must exist" derives it from
    here rather than assuming 78 -- an early close yields a correspondingly
    shorter list (e.g. 42 starts, 09:30..12:55 ET, on a 13:00 close).

    The LAST element is the final legitimate bar start (15:55 ET on an
    ordinary session). That value -- not the 16:00 session close -- is what a
    vendor whose `end` parameter is INCLUSIVE must be asked for; see
    alpaca_provider and defect ALP-1."""
    open_utc = session_open_utc(d)
    close_utc = session_close_utc(d)
    total_minutes = int((close_utc - open_utc).total_seconds() // 60)
    if total_minutes <= 0 or total_minutes % BAR_INTERVAL_MINUTES != 0:
        raise ExchangeCalendarError(
            f"{d}: session length {total_minutes}min is not a positive multiple of {BAR_INTERVAL_MINUTES}min"
        )
    count = total_minutes // BAR_INTERVAL_MINUTES
    return [open_utc + timedelta(minutes=BAR_INTERVAL_MINUTES * i) for i in range(count)]


def expected_bar_boundaries(d: date) -> SessionBarBoundaries:
    """Authoritative expected 5-minute-bar grid for a session, DERIVED from
    the calendar's own real open/close -- correctly shrinks the expected
    bar count on an early-close session rather than assuming a fixed 78."""
    open_utc = session_open_utc(d)
    close_utc = session_close_utc(d)
    total_minutes = int((close_utc - open_utc).total_seconds() // 60)
    if total_minutes <= 0 or total_minutes % BAR_INTERVAL_MINUTES != 0:
        raise ExchangeCalendarError(
            f"{d}: session length {total_minutes}min is not a positive multiple of {BAR_INTERVAL_MINUTES}min"
        )
    expected_bar_count = total_minutes // BAR_INTERVAL_MINUTES
    last_bar_start_utc = close_utc - timedelta(minutes=BAR_INTERVAL_MINUTES)
    return SessionBarBoundaries(
        session_date=d.isoformat(),
        open_utc=open_utc.isoformat(),
        close_utc=close_utc.isoformat(),
        is_early_close=is_early_close(d),
        first_bar_start_utc=open_utc.isoformat(),
        last_bar_start_utc=last_bar_start_utc.isoformat(),
        expected_bar_count=expected_bar_count,
    )


def compute_expected_next_full_trading_session_xnys(earnings_date: date, release_market_session: str) -> date:
    """Same day-count rule as identity.compute_expected_next_full_trading_session,
    but bound to the authoritative XNYS calendar instead of a caller-supplied
    is_trading_day callable. Kept as a separate, explicit function (rather
    than silently changing the generic function's default) so every call
    site states plainly which calendar it is using."""
    from .identity import VALID_RELEASE_SESSIONS, EventIdentityError

    if release_market_session not in VALID_RELEASE_SESSIONS:
        raise EventIdentityError(f"release_market_session {release_market_session!r} not verified")
    if release_market_session == "BMO" and is_trading_day(earnings_date):
        return earnings_date
    return next_session(earnings_date)
