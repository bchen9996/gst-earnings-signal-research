# Deterministic return-interval derivation functions. SPEC section 6/7/4.1.
#
# Every formula here is null-safe by construction: if any required input is
# None, the output is None -- never 0. There is exactly one place (this
# module) where these formulas are defined; nothing else in this package
# recomputes a return inline.
from __future__ import annotations

from typing import Optional, Sequence

from .constants import GST_Z_THRESHOLD


def _safe_ratio_minus_one(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator - 1.0


def overnight_gap(next_session_open: Optional[float], previous_close: Optional[float]) -> Optional[float]:
    return _safe_ratio_minus_one(next_session_open, previous_close)


def open_to_30m(price_at_30m: Optional[float], session_open: Optional[float]) -> Optional[float]:
    return _safe_ratio_minus_one(price_at_30m, session_open)


def thirty_min_to_close(session_close: Optional[float], price_at_30m: Optional[float]) -> Optional[float]:
    return _safe_ratio_minus_one(session_close, price_at_30m)


def open_to_close(session_close: Optional[float], session_open: Optional[float]) -> Optional[float]:
    return _safe_ratio_minus_one(session_close, session_open)


def close_to_close(close_t_later: Optional[float], close_t_earlier: Optional[float]) -> Optional[float]:
    return _safe_ratio_minus_one(close_t_later, close_t_earlier)


def full_session_range(
    session_high: Optional[float], session_low: Optional[float], session_open: Optional[float]
) -> Optional[float]:
    if session_high is None or session_low is None or session_open is None or session_open == 0:
        return None
    return (session_high - session_low) / session_open


def volume_share(first_30m_volume: Optional[int], full_session_volume: Optional[int]) -> Optional[float]:
    if first_30m_volume is None or full_session_volume is None or full_session_volume == 0:
        return None
    return first_30m_volume / full_session_volume


def abs_or_none(value: Optional[float]) -> Optional[float]:
    return None if value is None else abs(value)


def relative_return(stock_return: Optional[float], benchmark_return: Optional[float]) -> Optional[float]:
    """stock_return - benchmark_return. NEVER labeled 'abnormal return' or
    'alpha' -- see SPEC section 7.2. Purely a null-safe arithmetic
    difference."""
    if stock_return is None or benchmark_return is None:
        return None
    return stock_return - benchmark_return


def gst_slope_v0_1(trailing_levels: Sequence[Optional[float]]) -> Optional[float]:
    """Simple first-difference slope: mean of consecutive differences over
    the trailing window. Returns None if fewer than 2 non-null observations
    are present -- never silently computed on a partial/short window with a
    substitute value. Development-only, versioned -- see SPEC section 4.1."""
    values = [v for v in trailing_levels if v is not None]
    if len(values) < 2:
        return None
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    return sum(diffs) / len(diffs)


def gst_persistence_v0_1(
    trailing_zscores: Sequence[Optional[float]], threshold: float = GST_Z_THRESHOLD
) -> Optional[float]:
    """Fraction of trailing (non-null) z-scores at/above `threshold`. Returns
    None if no non-null observations exist -- never coerced to 0.0.
    Development-only, versioned -- see SPEC section 4.1."""
    values = [v for v in trailing_zscores if v is not None]
    if not values:
        return None
    elevated = sum(1 for v in values if v >= threshold)
    return elevated / len(values)
