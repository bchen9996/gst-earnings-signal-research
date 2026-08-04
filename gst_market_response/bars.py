# Intraday 5-minute OHLCV bar validation and session-boundary extraction.
# SPEC section 6.1: exchange-local (America/New_York) boundary logic, strict
# input validation (no duplicate or non-monotonic timestamps silently
# accepted), missing-bar fields resolve to None -- never estimated.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
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


def extract_session_fields(bars: Sequence[Bar]) -> SessionFields:
    """Derives session-level fields from a validated, chronologically-sorted
    list of same-session 5-minute bars. Any boundary bar that's absent from
    the input produces a None field -- never an estimate from adjacent
    bars."""
    if not bars:
        return SessionFields(None, None, None, None, None, None, None)

    open_bar = next((b for b in bars if b.local_time().time() == SESSION_OPEN_TIME), None)
    thirty_min_bar = next(
        (b for b in bars if b.local_time().time() == THIRTY_MIN_BOUNDARY_LAST_BAR_START), None
    )
    close_bar = bars[-1]  # last bar of the session, whatever the session's actual close time is (half-day aware)

    first_30m_bars = [
        b for b in bars if SESSION_OPEN_TIME <= b.local_time().time() <= THIRTY_MIN_BOUNDARY_LAST_BAR_START
    ]
    # first_30m_volume is only meaningful if the full 6-bar window is present;
    # a partial window would understate volume and silently look like a low-
    # attention open, so it fails closed to None instead.
    has_full_30m_window = thirty_min_bar is not None and open_bar is not None

    return SessionFields(
        session_open=open_bar.open if open_bar else None,
        price_at_30m=thirty_min_bar.close if thirty_min_bar else None,
        session_close=close_bar.close if close_bar else None,
        session_high=max((b.high for b in bars), default=None),
        session_low=min((b.low for b in bars), default=None),
        first_30m_volume=(sum(b.volume for b in first_30m_bars) if has_full_30m_window else None),
        full_session_volume=sum(b.volume for b in bars),
    )
