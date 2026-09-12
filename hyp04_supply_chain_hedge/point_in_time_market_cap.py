#!/usr/bin/env python3
"""Point-in-time market cap: price x shares outstanding, both as of the SAME
date -- HYP-05's coverage/liquidity input.

Combines `shares_outstanding.shares_outstanding_as_of()` with a caller-
supplied point-in-time close-price lookup. The price side is deliberately
NOT reimplemented here: this repo already has operator-fetched, provenance-
tracked historical closes (`peer_returns.load_peer_closes`), and a second
price reader would be a second thing to keep consistent with the first. A
caller wires in whatever price source it already has via `price_lookup`;
this module only combines the two and enforces that BOTH sides succeed.

Fails closed on either side missing -- `missing_shares`, `missing_price`, or
both -- rather than falling back to a live TODAY snapshot for the side that
failed. A market cap computed from one point-in-time input and one current
one would be neither, and would look like a real point-in-time figure to
anything reading the result later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .shares_outstanding import SharesOutstandingFact, shares_outstanding_as_of

PriceLookup = Callable[[str, str], Optional[float]]

REASON_MISSING_SHARES = "missing_shares"
REASON_MISSING_PRICE = "missing_price"


@dataclass(frozen=True)
class MarketCapResult:
    """The computed market cap, or a specific, fail-closed reason it isn't."""

    ticker: str
    target_date: str
    market_cap: Optional[float]
    price: Optional[float]
    shares: Optional[SharesOutstandingFact]
    denials: tuple[str, ...] = field(default_factory=tuple)

    @property
    def computed(self) -> bool:
        return self.market_cap is not None and not self.denials

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "target_date": self.target_date,
            "computed": self.computed,
            "market_cap": self.market_cap,
            "price": self.price,
            "shares_outstanding": self.shares.as_dict() if self.shares else None,
            "denials": list(self.denials),
        }


def market_cap_as_of(
    ticker: str,
    target_date: str,
    *,
    shares_series: Sequence[SharesOutstandingFact],
    price_lookup: PriceLookup,
) -> MarketCapResult:
    """Point-in-time market cap for `ticker` as of `target_date`.

    `shares_series` is the ticker's already-fetched shares-outstanding
    series (see `shares_outstanding.fetch_shares_outstanding_series`).
    `price_lookup(ticker, target_date)` returns a close price for that exact
    session, or None -- this module never substitutes a nearby date; a
    caller that wants that behaviour makes it explicit in its own lookup.
    """
    tick = ticker.upper()
    denials: list[str] = []

    shares_fact = shares_outstanding_as_of(shares_series, target_date)
    if shares_fact is None:
        denials.append(
            f"{REASON_MISSING_SHARES}: no shares-outstanding fact known as "
            f"of {target_date}")

    price = price_lookup(tick, target_date)
    if price is None:
        denials.append(
            f"{REASON_MISSING_PRICE}: no close price for {tick} on {target_date}")
    elif not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        denials.append(f"{REASON_MISSING_PRICE}: price {price!r} is not a "
                       "positive number")
        price = None

    if denials:
        return MarketCapResult(tick, target_date, None, price, shares_fact,
                               tuple(denials))

    assert shares_fact is not None and price is not None  # denials would be non-empty otherwise
    return MarketCapResult(tick, target_date, price * shares_fact.shares,
                           price, shares_fact, ())


def price_lookup_from_observations(
    observations: Sequence[Any],
) -> PriceLookup:
    """Adapt a sequence of `peer_returns.PriceObservation` (ticker,
    session_date, close) into the `price_lookup` callable this module wants.

    Exact-date match only -- deliberately does not fall back to the nearest
    prior session. Anchor event dates are XNYS trading sessions by
    construction (`hyp04_supply_chain_hedge.sessions`), so an exact match is
    expected to exist whenever the underlying closes file actually covers
    that peer for that date; a caller that wants nearest-session tolerance
    makes that choice explicitly rather than getting it silently here.
    """
    index: dict[tuple[str, str], float] = {}
    for o in observations:
        index[(o.ticker.upper(), o.session_date.isoformat())] = o.close

    def _lookup(ticker: str, target_date: str) -> Optional[float]:
        return index.get((ticker.upper(), target_date))

    return _lookup
