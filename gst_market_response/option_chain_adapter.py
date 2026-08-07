# Adapter around the existing option-chain functions in
# GST_Option_Chain_Core.py (repo root), plus this module's own
# earnings-specific option-benchmark capture logic (SPEC section 5).
#
# Deliberately reuses get_nearest_post_earnings_expiry() and
# get_option_snapshot() as-is (see SPEC "Reused components") rather than
# reimplementing expiry selection or ATM-strike lookup. Everything below
# those two calls -- mid computation, executable-cost separation, the
# reject-on-bad-quote rules -- is new, since the reused functions don't
# provide it.
#
# Import source corrected 2026-08-06: these two helpers used to be imported
# from GST_MultiTicker_Forward_Log, a live execution entry point that loads
# pytrends and the live GST signal engine at module scope. That made merely
# importing this adapter require the entire legacy GST dependency tree, and it
# broke the first real CI run of PR #3 with
# `ModuleNotFoundError: No module named 'pytrends'`. The helpers now live in
# the dependency-light GST_Option_Chain_Core; the functions themselves are
# unchanged, and the legacy logger re-exports them so its own callers are
# unaffected.
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from GST_Option_Chain_Core import (  # noqa: E402  (path setup must precede this import)
    get_nearest_post_earnings_expiry as _select_nearest_expiry_after,
    get_option_snapshot as _capture_atm_snapshot,
)

# Timestamps further apart than this are treated as materially incompatible
# -- see SPEC section 5.2 "Hard rules". Documented here as the single source
# of truth for the threshold (also referenced in the field dictionary).
MAX_COMPATIBLE_QUOTE_SKEW_SECONDS = 120


class ContractSelectionStatus:
    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"
    REJECTED_EXPIRY_NOT_AFTER_EVENT = "rejected_expiry_not_after_event"
    REJECTED_BID_GT_ASK = "rejected_bid_gt_ask"
    REJECTED_INCOMPATIBLE_TIMESTAMPS = "rejected_incompatible_timestamps"


@dataclass(frozen=True)
class OptionBenchmark:
    underlying_price: Optional[float]
    expiration: Optional[date]
    atm_strike_selection_rule: str
    call_bid: Optional[float]
    call_ask: Optional[float]
    call_mid: Optional[float]
    put_bid: Optional[float]
    put_ask: Optional[float]
    put_mid: Optional[float]
    quote_timestamp_utc: Optional[datetime]
    open_interest_call: Optional[int]
    open_interest_put: Optional[int]
    volume_call: Optional[int]
    volume_put: Optional[int]
    straddle_bid: Optional[float]
    straddle_ask: Optional[float]
    straddle_mid: Optional[float]
    midpoint_implied_move: Optional[float]
    long_executable_implied_move_cost: Optional[float]
    short_executable_proceeds_proxy: Optional[float]
    contract_selection_status: str
    data_quality_status: str


ATM_STRIKE_SELECTION_RULE = "nearest strike to spot by absolute distance (min |strike - spot|)"


def select_post_event_expiration(option_expirations, earnings_date: date, tk) -> Optional[str]:
    """Thin pass-through to the reused function, called with earnings_date as
    the anchor (not today) -- see SPEC section 5.1. `tk` is a yfinance
    Ticker-like object (or test double exposing `.options`)."""
    return _select_nearest_expiry_after(tk, earnings_date)


def _mid_or_none(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    return (bid + ask) / 2.0


def build_option_benchmark(
    *,
    tk,
    earnings_date: date,
    underlying_price: Optional[float],
    quote_timestamp_utc: Optional[datetime],
    call_quote_timestamp_utc: Optional[datetime] = None,
    put_quote_timestamp_utc: Optional[datetime] = None,
) -> OptionBenchmark:
    """Orchestrates SPEC section 5: selects the nearest post-event expiry,
    captures the ATM snapshot via the reused function, then applies the hard
    rejection rules. Never substitutes a midpoint value for an executable
    cost, and never silently keeps a crossed or timestamp-incompatible
    quote."""

    def _rejected(status: str) -> OptionBenchmark:
        return OptionBenchmark(
            underlying_price=underlying_price,
            expiration=None,
            atm_strike_selection_rule=ATM_STRIKE_SELECTION_RULE,
            call_bid=None, call_ask=None, call_mid=None,
            put_bid=None, put_ask=None, put_mid=None,
            quote_timestamp_utc=quote_timestamp_utc,
            open_interest_call=None, open_interest_put=None,
            volume_call=None, volume_put=None,
            straddle_bid=None, straddle_ask=None, straddle_mid=None,
            midpoint_implied_move=None,
            long_executable_implied_move_cost=None,
            short_executable_proceeds_proxy=None,
            contract_selection_status=status,
            data_quality_status="missing" if status != ContractSelectionStatus.OK else "ok",
        )

    expiry_str = _select_nearest_expiry_after(tk, earnings_date)
    if expiry_str is None:
        return _rejected(ContractSelectionStatus.MISSING)

    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    if expiry_date <= earnings_date:
        # Belt-and-suspenders: the reused selector already enforces "strictly
        # after", but this module never trusts an upstream invariant silently
        # -- see Testing requirement 16.
        return _rejected(ContractSelectionStatus.REJECTED_EXPIRY_NOT_AFTER_EVENT)

    if underlying_price is None:
        return _rejected(ContractSelectionStatus.MISSING)

    snapshot = _capture_atm_snapshot(tk, expiry_str, underlying_price)

    call_bid = snapshot.get("call_bid")
    call_ask = snapshot.get("call_ask")
    put_bid = snapshot.get("put_bid")
    put_ask = snapshot.get("put_ask")

    if (call_bid is not None and call_ask is not None and call_bid > call_ask) or (
        put_bid is not None and put_ask is not None and put_bid > put_ask
    ):
        return _rejected(ContractSelectionStatus.REJECTED_BID_GT_ASK)

    if call_quote_timestamp_utc is not None and put_quote_timestamp_utc is not None:
        skew = abs((call_quote_timestamp_utc - put_quote_timestamp_utc).total_seconds())
        if skew > MAX_COMPATIBLE_QUOTE_SKEW_SECONDS:
            return _rejected(ContractSelectionStatus.REJECTED_INCOMPATIBLE_TIMESTAMPS)

    call_mid = _mid_or_none(call_bid, call_ask)
    put_mid = _mid_or_none(put_bid, put_ask)

    straddle_bid = (call_bid + put_bid) if (call_bid is not None and put_bid is not None) else None
    straddle_ask = (call_ask + put_ask) if (call_ask is not None and put_ask is not None) else None
    straddle_mid = (call_mid + put_mid) if (call_mid is not None and put_mid is not None) else None

    midpoint_implied_move = (
        straddle_mid / underlying_price if straddle_mid is not None and underlying_price else None
    )
    long_executable_implied_move_cost = (
        straddle_ask / underlying_price if straddle_ask is not None and underlying_price else None
    )
    short_executable_proceeds_proxy = (
        straddle_bid / underlying_price if straddle_bid is not None and underlying_price else None
    )

    has_any_quote = call_bid is not None or call_ask is not None or put_bid is not None or put_ask is not None
    status = ContractSelectionStatus.OK if has_any_quote else ContractSelectionStatus.MISSING
    dq_status = "ok" if (straddle_mid is not None or long_executable_implied_move_cost is not None) else "partial"

    return OptionBenchmark(
        underlying_price=underlying_price,
        expiration=expiry_date,
        atm_strike_selection_rule=ATM_STRIKE_SELECTION_RULE,
        call_bid=call_bid, call_ask=call_ask, call_mid=call_mid,
        put_bid=put_bid, put_ask=put_ask, put_mid=put_mid,
        quote_timestamp_utc=quote_timestamp_utc,
        open_interest_call=snapshot.get("call_open_interest"),
        open_interest_put=snapshot.get("put_open_interest"),
        volume_call=snapshot.get("call_volume"),
        volume_put=snapshot.get("put_volume"),
        straddle_bid=straddle_bid, straddle_ask=straddle_ask, straddle_mid=straddle_mid,
        midpoint_implied_move=midpoint_implied_move,
        long_executable_implied_move_cost=long_executable_implied_move_cost,
        short_executable_proceeds_proxy=short_executable_proceeds_proxy,
        contract_selection_status=status,
        data_quality_status=dq_status,
    )
