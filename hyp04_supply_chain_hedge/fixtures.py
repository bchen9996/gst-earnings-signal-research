#!/usr/bin/env python3
"""Synthetic-fixture generator -- HYP-04 Phase 0, build step 1.

SYNTHETIC DATA ONLY. No provider, no network, no research artifact is read.

This is built FIRST, as its own deliverable, so the inference layer is
validated against known ground truth rather than against itself (Patch 7).
Every fixture carries the parameters it was generated from, so a test can
assert recovery rather than merely assert self-consistency.

Three fixture kinds, per Patch 10 (which superseded Patch 6's single-fixture
wording):

  * MAIN            -- known injected lag, known effect size, known cluster
                       structure. What step 3b's max-T permutation runs
                       against, and what the lag-recovery test uses.
  * ZERO_EFFECT     -- no injected anchor->peer effect, ample N. The LP peak
                       must be non-significant post multiplicity-correction
                       and the placebo must show no real-vs-random
                       separation, but the N_eff gate must PASS: the gate
                       measures sample size, not effect. A gate that failed
                       here would be wired to the wrong quantity.
  * INSUFFICIENT_N  -- too few anchor events, effect size irrelevant. The
                       N_eff gate must return False regardless of what is
                       injected.

The generative model is deliberately simple and stated in full:

    log-return r[peer, t] ~ Normal(0, sigma_peer)

  with the peer's daily volatility multiplied by

    (1 + earnings_ramp(days_to_own_earnings))     # the confound
    (1 + effect * shock_magnitude)  for t in [anchor + lag, anchor + lag + W)

The earnings ramp exists precisely so the residualization step has a real
confound to remove -- a fixture without it could not distinguish working
residualization from absent residualization.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Trading-day indexing throughout. Calendar dates are deliberately absent:
# Phase 0's fixtures test estimator behaviour, and a synthetic exchange
# calendar would add a second thing to get wrong without testing anything.
TRADING_DAYS_PER_YEAR = 252
QUARTER_TRADING_DAYS = 63


def stable_seed(name: str, base: int) -> int:
    """Process-stable seed offset.

    Python randomises str hashing per process unless PYTHONHASHSEED is set,
    so hash() must never seed a reproducible fixture. Same reasoning, and
    the same fix, as tools/hyp01_inference_feasibility.py:stable_name_offset.
    """
    digest = hashlib.sha256(name.encode("utf-8")).digest()[:8]
    return (base + int.from_bytes(digest, "big")) % (2**63 - 1)


@dataclass
class SyntheticPanel:
    """A generated fixture plus the ground truth it was generated from."""

    name: str
    returns: dict[str, np.ndarray]           # peer ticker -> daily log returns
    peer_earnings_days: dict[str, list[int]]  # peer -> its own earnings day indices
    anchor_events: list[dict[str, Any]]      # each: anchor, day, shock, peers
    n_trading_days: int

    # --- ground truth, for assertions only; never read by the pipeline ---
    injected_lag: int | None
    injected_effect: float
    injected_effect_window: int
    peer_base_vol: dict[str, float]
    earnings_ramp_amplitude: float
    truth: dict[str, Any] = field(default_factory=dict)

    @property
    def n_events(self) -> int:
        return len(self.anchor_events)

    @property
    def n_pairs(self) -> int:
        return sum(len(ev["peers"]) for ev in self.anchor_events)

    @property
    def mean_peers_per_event(self) -> float:
        return self.n_pairs / self.n_events if self.n_events else 0.0


def earnings_ramp(days_to_earnings: np.ndarray, amplitude: float) -> np.ndarray:
    """Every company's vol rises into its OWN earnings, anchor or no anchor.

    This is the confound the target definition's residualization exists to
    remove (plan Section 3). Modelled as a smooth ramp over the 10 sessions
    before the peer's own report, zero elsewhere.
    """
    ramp = np.zeros_like(days_to_earnings, dtype=float)
    window = (days_to_earnings >= 0) & (days_to_earnings <= 10)
    ramp[window] = amplitude * (1.0 - days_to_earnings[window] / 10.0)
    return ramp


def _days_to_next_earnings(n_days: int, earnings_days: list[int]) -> np.ndarray:
    """For each trading day, sessions until this peer's next own earnings."""
    out = np.full(n_days, 10**6, dtype=float)
    for e in sorted(earnings_days):
        idx = np.arange(n_days)
        gap = e - idx
        mask = (gap >= 0) & (gap < out)
        out[mask] = gap[mask]
    return out


def make_panel(
    name: str,
    *,
    n_anchors: int,
    n_quarters: int,
    n_peers_per_anchor: int,
    injected_lag: int | None,
    injected_effect: float,
    injected_effect_window: int = 5,
    earnings_ramp_amplitude: float = 0.60,
    base_vol_range: tuple[float, float] = (0.012, 0.030),
    n_trading_days: int | None = None,
    seed: int = 20260817,
) -> SyntheticPanel:
    """Generate one synthetic panel with fully known ground truth.

    injected_lag=None with injected_effect=0.0 produces a pure null panel:
    peers still carry their own earnings ramps (so residualization has work
    to do) but no anchor->peer transmission exists at any horizon.
    """
    rng = np.random.default_rng(stable_seed(name, seed))

    if n_trading_days is None:
        n_trading_days = QUARTER_TRADING_DAYS * (n_quarters + 2)

    anchors = [f"ANCHOR_{i + 1:03d}" for i in range(n_anchors)]
    peers = [f"PEER_{i + 1:03d}" for i in range(n_anchors * n_peers_per_anchor)]

    # Each peer reports on its own quarterly cycle, offset so peers do not
    # all report in the same week -- otherwise "days to own earnings" would
    # be collinear with calendar time and the confound would be untestable.
    peer_earnings_days: dict[str, list[int]] = {}
    for i, p in enumerate(peers):
        offset = int(rng.integers(0, QUARTER_TRADING_DAYS))
        peer_earnings_days[p] = list(range(offset, n_trading_days, QUARTER_TRADING_DAYS))

    peer_base_vol = {p: float(rng.uniform(*base_vol_range)) for p in peers}

    # Anchor events: each anchor reports once per quarter, with a shock
    # magnitude drawn per event. Events cluster in calendar time the way real
    # earnings seasons do -- anchors within a season report within ~10
    # sessions of each other.
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
                "day": int(day),
                "shock": float(abs(rng.normal(0.0, 1.0))),
                "peers": list(anchor_peers),
                "calendar_period": int(q),
            })

    # --- generate returns -------------------------------------------------
    vol_multiplier: dict[str, np.ndarray] = {}
    for p in peers:
        dte = _days_to_next_earnings(n_trading_days, peer_earnings_days[p])
        vol_multiplier[p] = 1.0 + earnings_ramp(dte, earnings_ramp_amplitude)

    # Anchor transmission: peer vol is elevated starting `injected_lag`
    # sessions after the anchor's report, for `injected_effect_window`
    # sessions, scaled by that event's shock magnitude.
    if injected_lag is not None and injected_effect != 0.0:
        for ev in anchor_events:
            start = ev["day"] + injected_lag
            stop = min(start + injected_effect_window, n_trading_days)
            if start >= n_trading_days:
                continue
            bump = 1.0 + injected_effect * ev["shock"]
            for p in ev["peers"]:
                vol_multiplier[p][start:stop] *= bump

    returns: dict[str, np.ndarray] = {}
    for p in peers:
        sigma = peer_base_vol[p] * vol_multiplier[p]
        returns[p] = rng.normal(0.0, sigma)

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
        earnings_ramp_amplitude=earnings_ramp_amplitude,
        truth={
            "n_anchors": n_anchors,
            "n_quarters": n_quarters,
            "n_peers_per_anchor": n_peers_per_anchor,
            "seed": seed,
            "generative_model": (
                "r[p,t] ~ Normal(0, base_vol[p] * (1 + earnings_ramp(dte[p,t])) "
                "* (1 + effect*shock) on [anchor+lag, anchor+lag+W))"
            ),
        },
    )


# ==========================================================================
# The three committed fixtures (Patch 10).
# ==========================================================================
def make_main_fixture(seed: int = 20260817) -> SyntheticPanel:
    """Known lag, known effect, realistic cluster structure.

    Sized to comfortably clear any plausible N gate so that lag-recovery
    failures are attributable to the estimator, not to sample size.
    """
    return make_panel(
        "MAIN_known_lag_5",
        n_anchors=24,
        n_quarters=16,
        n_peers_per_anchor=8,
        injected_lag=5,
        injected_effect=0.55,
        seed=seed,
    )


def make_zero_effect_fixture(seed: int = 20260817) -> SyntheticPanel:
    """No anchor->peer transmission, ample N.

    Peers still carry their own earnings ramps, so a pipeline that skipped
    residualization would still find "signal" here -- which is exactly what
    this fixture is for.
    """
    return make_panel(
        "ZERO_EFFECT_ample_n",
        n_anchors=24,
        n_quarters=16,
        n_peers_per_anchor=8,
        injected_lag=None,
        injected_effect=0.0,
        seed=seed + 1,
    )


def make_insufficient_n_fixture(seed: int = 20260817) -> SyntheticPanel:
    """Too few anchor events to support inference, effect deliberately large.

    The effect is large ON PURPOSE: the N gate must return False anyway. A
    gate that passed here because the effect was strong would be wired to
    the wrong quantity.
    """
    return make_panel(
        "INSUFFICIENT_N_large_effect",
        n_anchors=3,
        n_quarters=2,
        n_peers_per_anchor=4,
        injected_lag=5,
        injected_effect=0.80,
        seed=seed + 2,
    )


def make_constant_vol_fixture(seed: int = 20260817) -> SyntheticPanel:
    """Constant volatility, no earnings ramp, no anchor effect.

    The direct regression fixture for the RV-normalization bug (Patch 9):
    under constant vol with zero injected effect, the target must show NO
    systematic trend across h. The unnormalized RV(h) = sqrt(sum(r^2))
    definition produces a deterministic sqrt(h)-shaped trend here even
    though nothing in the data varies with horizon.
    """
    return make_panel(
        "CONSTANT_VOL_no_ramp",
        n_anchors=12,
        n_quarters=12,
        n_peers_per_anchor=6,
        injected_lag=None,
        injected_effect=0.0,
        earnings_ramp_amplitude=0.0,
        base_vol_range=(0.02, 0.02),
        seed=seed + 3,
    )


FIXTURE_BUILDERS = {
    "MAIN_known_lag_5": make_main_fixture,
    "ZERO_EFFECT_ample_n": make_zero_effect_fixture,
    "INSUFFICIENT_N_large_effect": make_insufficient_n_fixture,
    "CONSTANT_VOL_no_ramp": make_constant_vol_fixture,
}


def summarize(panel: SyntheticPanel) -> dict[str, Any]:
    """Shape summary for status-doc reporting. Carries no research value."""
    return {
        "fixture": panel.name,
        "n_events": panel.n_events,
        "n_pairs": panel.n_pairs,
        "mean_peers_per_event": round(panel.mean_peers_per_event, 3),
        "n_trading_days": panel.n_trading_days,
        "injected_lag": panel.injected_lag,
        "injected_effect": panel.injected_effect,
        "earnings_ramp_amplitude": panel.earnings_ramp_amplitude,
    }


if __name__ == "__main__":
    for fixture_name, builder in FIXTURE_BUILDERS.items():
        print(summarize(builder()))
