#!/usr/bin/env python3
"""Synthetic-fixture generator for HYP-07's signed target
(`target_signed.py`).

SYNTHETIC DATA ONLY. No provider, no network, no research artifact is read.

=== WHY A NEW GENERATOR, NOT fixtures.make_panel() REUSED ===

`fixtures.make_panel()` hardcodes `shock = abs(rng.normal(0.0, 1.0))` at
generation time -- the anchor shock is never signed, because HYP-04/05/06's
target never reads its sign. It also carries no benchmark-series concept
at all. HYP-07's signed target needs BOTH: a genuinely signed anchor shock
(so the fixture can inject a real, direction-testable effect) and a
benchmark ("SPY") return series alongside every peer's own (the leg
`target_signed.signed_car`'s benchmark-adjustment subtracts). Producing a
valid HYP-07 fixture from `make_panel()` would require rewriting it in
place, which is exactly the "new module for a different data shape"
discipline this whole package already applies everywhere else (every
`run_hypNN_*` module in this package is a new, parallel file rather than a
retrofit, for the identical reason).

=== THE GENERATIVE MODEL ===

    r[bench, t]        ~ Normal(0, benchmark_vol)
    r[peer, t]          = r[bench, t] + idiosyncratic[peer, t]
    idiosyncratic[p, t] ~ Normal(0, peer_base_vol[p])

  with an additive abnormal-return bump on top of the idiosyncratic leg,
  for t in [anchor_day + lag, anchor_day + lag + W):

    bump[p, t] = injected_effect * shock[event] * peer_base_vol[p]

  `injected_effect` NEGATIVE injects a competitive-DISPLACEMENT
  relationship (anchor shock and peer reaction move opposite ways --
  `target_signed.py`'s own predicted sign for a genuine competitor);
  POSITIVE injects a COMOVEMENT relationship instead. `shock[event]` is
  itself SIGNED (unlike `fixtures.make_panel`'s `abs(...)`), drawn
  `Normal(0, 1)` per event -- the fixture must carry a real, mixed-sign
  shock series for a sign-recovery test to mean anything.

No earnings-ramp confound is generated here (unlike `fixtures.make_panel`)
-- `target_signed.py`'s own docstring states plainly why the bucketed
earnings-cycle residualizer was not ported, and a fixture testing a
target that carries no such residualizer has nothing to gain from
injecting a confound nothing downstream removes.
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


def make_panel_signed(
    name: str,
    *,
    n_anchors: int,
    n_quarters: int,
    n_peers_per_anchor: int,
    injected_lag: int | None,
    injected_effect: float,
    injected_effect_window: int = 5,
    base_vol_range: tuple[float, float] = (0.012, 0.030),
    benchmark_vol: float = 0.010,
    benchmark_ticker: str = "SPY",
    n_trading_days: int | None = None,
    seed: int = 20260913,
) -> SyntheticPanel:
    """Generate one synthetic panel with fully known ground truth, shaped
    for `target_signed.build_feature_table_signed`.

    injected_lag=None with injected_effect=0.0 produces a pure null panel
    -- peer returns are pure benchmark-plus-idiosyncratic-noise, no
    anchor->peer transmission at any horizon, same convention
    `fixtures.make_panel`'s own null-panel shape uses.
    """
    rng = np.random.default_rng(stable_seed(name, seed))

    if n_trading_days is None:
        n_trading_days = QUARTER_TRADING_DAYS * (n_quarters + 2)

    anchors = [f"ANCHOR_{i + 1:03d}" for i in range(n_anchors)]
    peers = [f"PEER_{i + 1:03d}" for i in range(n_anchors * n_peers_per_anchor)]

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
            if day + injected_effect_window + max(20, 1) >= n_trading_days:
                continue
            anchor_peers = peers[a_i * n_peers_per_anchor:(a_i + 1) * n_peers_per_anchor]
            anchor_events.append({
                "anchor": anchor,
                "anchor_day": int(day),
                # SIGNED, unlike fixtures.make_panel's abs(...) -- a
                # sign-recovery test needs a real, mixed-sign shock series.
                "shock": float(rng.normal(0.0, 1.0)),
                "peers": list(anchor_peers),
                "calendar_period": int(q),
            })

    # --- generate returns: benchmark first, then peer = benchmark + idio --
    benchmark_returns = rng.normal(0.0, benchmark_vol, size=n_trading_days)

    returns: dict[str, np.ndarray] = {benchmark_ticker: benchmark_returns}
    for p in peers:
        idio = rng.normal(0.0, peer_base_vol[p], size=n_trading_days)
        returns[p] = benchmark_returns + idio

    # Anchor transmission: an additive abnormal-return bump on the
    # idiosyncratic leg, signed by injected_effect * the event's own
    # signed shock -- negative injected_effect => displacement (opposite
    # sign), positive => comovement (same sign).
    if injected_lag is not None and injected_effect != 0.0:
        for ev in anchor_events:
            start = ev["anchor_day"] + injected_lag
            stop = min(start + injected_effect_window, n_trading_days)
            if start >= n_trading_days:
                continue
            for p in ev["peers"]:
                bump = injected_effect * ev["shock"] * peer_base_vol[p]
                returns[p][start:stop] += bump

    return SyntheticPanel(
        name=name,
        returns=returns,
        peer_earnings_days=peer_earnings_days,
        anchor_events=anchor_events,
        n_trading_days=n_trading_days,
        injected_lag=injected_lag,
        injected_effect=injected_effect,
        injected_effect_window=injected_effect_window,
        peer_base_vol=peer_base_vol,
        earnings_ramp_amplitude=0.0,
        truth={
            "n_anchors": n_anchors,
            "n_quarters": n_quarters,
            "n_peers_per_anchor": n_peers_per_anchor,
            "benchmark_ticker": benchmark_ticker,
            "benchmark_vol": benchmark_vol,
            "seed": seed,
            "generative_model": (
                "r[bench,t] ~ Normal(0, benchmark_vol); "
                "r[p,t] = r[bench,t] + Normal(0, base_vol[p]) "
                "+ effect*shock[event]*base_vol[p] on "
                "[anchor+lag, anchor+lag+W) -- shock is SIGNED"
            ),
        },
    )
