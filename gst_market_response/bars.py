# Intraday 5-minute OHLCV bar validation and session-boundary extraction.
# SPEC section 6.1: exchange-local (America/New_York) boundary logic, strict
# input validation (no duplicate or non-monotonic timestamps silently
# accepted), missing-bar fields resolve to None -- never estimated.
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

ET_ZONE = ZoneInfo("America/New_York")
SESSION_OPEN_TIME = time(9, 30)
THIRTY_MIN_BOUNDARY_LAST_BAR_START = time(9, 55)  # last bar inside the first 30 minutes
BAR_INTERVAL_MINUTES = 5


class BarValidationError(ValueError):
    pass


class DuplicateBarError(BarValidationError):
    pass


class NonMonotonicTimestampError(BarValidationError):
    pass


class WrongTickerError(BarValidationError):
    pass


class InvalidOHLCError(BarValidationError):
    pass


class NegativeVolumeError(BarValidationError):
    pass


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp_utc: datetime  # bar START time, tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    volume: int

    def local_time(self) -> datetime:
        return self.timestamp_utc.astimezone(ET_ZONE)


def validate_ohlc_and_volume(bars: Sequence[Bar]) -> None:
    """Raises InvalidOHLCError on any bar where low > open/close/high (or
    low > high), and NegativeVolumeError on any negative volume. Used by
    every provider-diagnostic path (yfinance dev diagnostic, Alpaca live
    diagnostic) as a single, shared check rather than each reimplementing
    its own tolerance."""
    for b in bars:
        if not (b.low <= b.open <= b.high and b.low <= b.close <= b.high and b.low <= b.high):
            raise InvalidOHLCError(f"bar at {b.timestamp_utc} fails OHLC consistency: {b}")
        if b.volume < 0:
            raise NegativeVolumeError(f"bar at {b.timestamp_utc} has negative volume: {b.volume}")


def validate_bars(bars: Sequence[Bar], expected_symbol: str) -> list[Bar]:
    """Raises on any of: wrong ticker, duplicate timestamp, non-monotonic
    timestamp. Returns the bars unchanged (already-sorted-by-caller input is
    required -- this function does not silently re-sort, since re-sorting
    would mask a non-monotonic-input bug rather than reject it)."""
    if not bars:
        return []
    seen_timestamps: set[datetime] = set()
    prev_ts: Optional[datetime] = None
    for bar in bars:
        if bar.symbol != expected_symbol:
            raise WrongTickerError(f"expected {expected_symbol!r}, got bar for {bar.symbol!r}")
        if bar.timestamp_utc in seen_timestamps:
            raise DuplicateBarError(f"duplicate bar timestamp {bar.timestamp_utc}")
        seen_timestamps.add(bar.timestamp_utc)
        if prev_ts is not None and bar.timestamp_utc <= prev_ts:
            raise NonMonotonicTimestampError(
                f"bar timestamp {bar.timestamp_utc} does not strictly follow prior bar {prev_ts}"
            )
        prev_ts = bar.timestamp_utc
    return list(bars)


@dataclass(frozen=True)
class SessionFields:
    session_open: Optional[float]
    price_at_30m: Optional[float]
    session_close: Optional[float]
    session_high: Optional[float]
    session_low: Optional[float]
    first_30m_volume: Optional[int]
    full_session_volume: Optional[int]


class MixedSessionError(BarValidationError):
    """Raised when one call is handed bars from more than one session date --
    a session-level field derived across two sessions is meaningless, so this
    fails closed rather than silently reporting one of them."""


def extract_session_fields(bars: Sequence[Bar], session_date: Optional[date] = None) -> SessionFields:
    """Derives session-level fields from same-session 5-minute bars.

    Boundary bars are selected by their EXPECTED timestamps, taken from the
    authoritative XNYS calendar -- never positionally as bars[0]/bars[-1].
    That distinction is the whole point: under defect ALP-1 an extra
    after-hours bar starting at 16:00 ET arrived at the end of the list and,
    being bars[-1], silently became `session_close`. Selecting the close bar
    by "the calendar says the last bar starts at 15:55 ET" makes that
    impossible -- a stray 16:00 bar simply is not the close bar, whatever
    position it occupies.

    Consequences of that, all deliberate:
      - Input order does not matter. Unordered input yields identical fields.
      - A missing boundary bar yields None for that field, never an estimate
        from an adjacent bar.
      - An early close is handled by the calendar, not by an assumption: the
        expected last bar start is 12:55 ET on a 13:00 close.

    `session_date` may be passed explicitly; otherwise it is derived from the
    bars themselves (which must all belong to one session)."""
    if not bars:
        return SessionFields(None, None, None, None, None, None, None)

    session_dates = {b.local_time().date() for b in bars}
    if session_date is None:
        if len(session_dates) != 1:
            raise MixedSessionError(
                f"bars span {len(session_dates)} session dates {sorted(session_dates)} -- "
                f"pass session_date explicitly or split the input"
            )
        session_date = next(iter(session_dates))

    # Imported here rather than at module scope purely to keep bars.py's
    # import cost independent of the exchange_calendars package for callers
    # that only build/validate Bar objects.
    from .exchange_calendar import expected_bar_starts_utc

    expected_starts = expected_bar_starts_utc(session_date)
    expected_open_start = expected_starts[0]
    expected_close_start = expected_starts[-1]

    by_timestamp: dict[datetime, Bar] = {}
    for b in bars:
        by_timestamp.setdefault(b.timestamp_utc, b)

    open_bar = by_timestamp.get(expected_open_start)
    close_bar = by_timestamp.get(expected_close_start)
    thirty_min_bar = next(
        (b for b in bars if b.local_time().time() == THIRTY_MIN_BOUNDARY_LAST_BAR_START), None
    )

    first_30m_bars = [
        b for b in bars if SESSION_OPEN_TIME <= b.local_time().time() <= THIRTY_MIN_BOUNDARY_LAST_BAR_START
    ]
    # first_30m_volume is only meaningful if the full 6-bar window is present;
    # a partial window would understate volume and silently look like a low-
    # attention open, so it fails closed to None instead.
    has_full_30m_window = thirty_min_bar is not None and open_bar is not None

    # High/low/volume aggregate only over bars on the expected grid. A stray
    # out-of-session bar must not be able to set the session high or inflate
    # the volume any more than it can become the close.
    expected_set = set(expected_starts)
    in_session = [b for b in bars if b.timestamp_utc in expected_set]

    return SessionFields(
        session_open=open_bar.open if open_bar else None,
        price_at_30m=thirty_min_bar.close if thirty_min_bar else None,
        session_close=close_bar.close if close_bar else None,
        session_high=max((b.high for b in in_session), default=None),
        session_low=min((b.low for b in in_session), default=None),
        first_30m_volume=(sum(b.volume for b in first_30m_bars) if has_full_30m_window else None),
        full_session_volume=sum(b.volume for b in in_session) if in_session else None,
    )
