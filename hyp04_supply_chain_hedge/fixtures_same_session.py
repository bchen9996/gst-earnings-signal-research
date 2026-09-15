#!/usr/bin/env python3
"""Synthetic-fixture generator for HYP-08's same-session target
(`target_same_session.py`).

SYNTHETIC DATA ONLY. No provider, no network, no research artifact is read.

=== WHY A NEW GENERATOR, NOT fixtures_signed.make_panel_signed() REUSED ===

`make_panel_signed` injects ONE scalar `injected_effect` uniformly across
every anchor event -- there is no way to give customer/supplier events a
different sign from competitor events within one call, and testing
`inference.fit_interaction_model`'s heterogeneity recovery needs exactly
that: two SUBPOPULATIONS with two different, known, opposite-signed true
effects. This module assigns a `relationship_type` per ANCHOR (every event
under that anchor inherits it, and every one of that anchor's peers
inherits it too), with its own injected-effect parameter per type, and
injects the bump on the anchor's own event-day session ONLY (width=1,
lag=0) -- matching what "same-session" actually means, unlike
`make_panel_signed`'s default multi-day window starting the day after.

=== THE GENERATIVE MODEL ===

    r[bench, t]        ~ Normal(0, benchmark_vol)
    r[peer, t]          = r[bench, t] + idiosyncratic[peer, t]
    idiosyncratic[p, t] ~ Normal(0, peer_base_vol[p])

  with an additive abnormal-return bump on top of the idiosyncratic leg,
  applied ONLY at t = anchor_day (the same trading session the anchor's
  own shock is attributed to):

    bump[p, anchor_day] = effect[relationship_type(event)] * shock[event]
                           * peer_base_vol[p]

  where effect[...] is `injected_effect_customer_supplier` or
  `injected_effect_competitor` depending on the ANCHOR's assigned type.
  `shock[event]` is SIGNED, drawn Normal(0, 1) per event, same as
  `fixtures_signed.make_panel_signed`.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .fixtures import (
    QUARTER_TRADING_DAYS,
    SyntheticPanel,
    _days_to_next_earnings,
    stable_seed,
)

CUSTOMER_SUPPLIER_TYPE = "direct_supplier"
COMPETITOR_TYPE = "competitor"


def make_panel_same_session(
    name: str,
    *,
    n_anchors: int,
    n_quarters: int,
    n_peers_per_anchor: int,
    injected_effect_customer_supplier: float,
    injected_effect_competitor: float,
    base_vol_range: tuple[float, float] = (0.012, 0.030),
    benchmark_vol: float = 0.010,
    benchmark_ticker: str = "SPY",
    n_trading_days: int | None = None,
    seed: int = 20260914,
) -> SyntheticPanel:
    """One synthetic panel, half its anchors assigned
    `relationship_type="direct_supplier"` (alternating), half
    `"competitor"` -- with fully known, independently-settable ground
    truth per type, shaped for `target_same_session.
    build_feature_table_same_session` and `inference.
    fit_interaction_model`.

    Both injected effects 0.0 produces a pure null panel -- no
    anchor->peer transmission for either type, at any session.
    """
    rng = np.random.default_rng(stable_seed(name, seed))

    if n_trading_days is None:
        n_trading_days = QUARTER_TRADING_DAYS * (n_quarters + 2)

    anchors = [f"ANCHOR_{i + 1:03d}" for i in range(n_anchors)]
    peers = [f"PEER_{i + 1:03d}" for i in range(n_anchors * n_peers_per_anchor)]
    anchor_type = {
        a: (CUSTOMER_SUPPLIER_TYPE if i % 2 == 0 else COMPETITOR_TYPE)
        for i, a in enumerate(anchors)
    }

    peer_earnings_days: dict[str, list[int]] = {}
    for i, p in enumerate(peers):
        offset = int(rng.integers(0, QUARTER_TRADING_DAYS))
        peer_earnings_days[p] = list(range(offset, n_trading_days, QUARTER_TRADING_DAYS))

    peer_base_vol = {p: float(rng.uniform(*base_vol_range)) for p in peers}

    anchor_events: list[dict[str, Any]] = []
    for q in range(n_quarters):
        season_start = QUARTER_TRADING_DAYS * (q + 1)
        for a_i, anchor in enumerate(anchors):
            day = season_start + int(rng.integers(0, 10))
            if day >= n_trading_days - 1:
                continue
            anchor_peers = peers[a_i * n_peers_per_anchor:(a_i + 1) * n_peers_per_anchor]
            anchor_events.append({
                "anchor": anchor,
                "anchor_day": int(day),
                "shock": float(rng.normal(0.0, 1.0)),
                "peers": list(anchor_peers),
                "calendar_period": int(q),
                "relationship_type": anchor_type[anchor],
            })

    benchmark_returns = rng.normal(0.0, benchmark_vol, size=n_trading_days)
    returns: dict[str, np.ndarray] = {benchmark_ticker: benchmark_returns}
    for p in peers:
        idio = rng.normal(0.0, peer_base_vol[p], size=n_trading_days)
        returns[p] = benchmark_returns + idio

    for ev in anchor_events:
        effect = (injected_effect_customer_supplier
                  if ev["relationship_type"] == CUSTOMER_SUPPLIER_TYPE
                  else injected_effect_competitor)
        if effect == 0.0:
            continue
        t = ev["anchor_day"]
        for p in ev["peers"]:
            bump = effect * ev["shock"] * peer_base_vol[p]
            returns[p][t] += bump

    return SyntheticPanel(
        name=name,
        returns=returns,
        peer_earnings_days=peer_earnings_days,
        anchor_events=anchor_events,
        n_trading_days=n_trading_days,
        injected_lag=0,
        injected_effect=injected_effect_customer_supplier,
        injected_effect_window=1,
        peer_base_vol=peer_base_vol,
        earnings_ramp_amplitude=0.0,
        truth={
            "n_anchors": n_anchors,
            "n_quarters": n_quarters,
            "n_peers_per_anchor": n_peers_per_anchor,
            "benchmark_ticker": benchmark_ticker,
            "benchmark_vol": benchmark_vol,
            "seed": seed,
            "injected_effect_customer_supplier": injected_effect_customer_supplier,
            "injected_effect_competitor": injected_effect_competitor,
            "anchor_type": anchor_type,
            "generative_model": (
                "r[bench,t] ~ Normal(0, benchmark_vol); "
                "r[p,t] = r[bench,t] + Normal(0, base_vol[p]) "
                "+ effect[type]*shock[event]*base_vol[p] on t=anchor_day "
                "ONLY -- same-session, not a multi-day window"
            ),
        },
    )
