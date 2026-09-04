#!/usr/bin/env python3
"""Stage 2 -- Hedge Structure Selection. HYP-04 Phase 0, build step 4.

RULES-BASED BY DESIGN, NOT A TRAINED MODEL. The sample size needed to
responsibly fit a structure-choice classifier does not exist here, so this is
an explicit decision function whose every branch is inspectable and whose
every recommendation carries the rule that produced it.

NO REAL CAPITAL LOGIC. Phase 0 constructs recommendations only. Nothing here
prices a live order, sizes against a real account, or submits anything.

=== THE ASSUMED EXPOSURE (Patch 5) ===

Stage 2 protects an ASSUMED EXISTING LONG-EQUITY HOLDING in the peer name.

This assumption is stated in code, carried on every recommendation, and
printed in output, because it is load-bearing and was previously implicit:
"minimize cost subject to a minimum protection threshold" is meaningless
without a position to protect. Absent an underlying holding, buying puts is
not a hedge at all -- it is a directional long-volatility bet with a different
risk profile and different sizing logic entirely, and calling it a hedge would
misdescribe what the recommendation does.

The notional is an ASSUMPTION, not a real position (constants.py:
ASSUMED_PEER_EQUITY_NOTIONAL_USD). Hedge sizing scales linearly with it, so it
is reported alongside every recommendation rather than buried.

=== WHICH LAG FEEDS TENOR SELECTION ===

Tenor is sized against Stage 1's ONSET horizon, never its peak horizon.

With an expanding-window target, argmax|beta_h| identifies the END of the
reaction window (h = L+W-1), while the first horizon clearing significance
identifies its ONSET (h = L) -- confirmed on synthetic fixtures across 15
(L, W) combinations. Sizing tenor off the peak buys protection (W-1) days too
long and arrives after the move has already started.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Union

from .constants import ASSUMED_PEER_EQUITY_NOTIONAL_USD, NO_EDGE_CLAIM
from .onset import OnsetInterval
from .quantum_provenance import (
    MethodProvenance,
    assert_may_influence_link_strength,
)


class Structure:
    NO_POSITION = "no_position"
    PROTECTIVE_PUT = "protective_put"
    PUT_SPREAD = "put_spread"
    COLLAR = "collar"
    SECTOR_ETF_PROXY = "sector_etf_proxy"


# --- Preregistered thresholds --------------------------------------------
# Fixed here so a reviewer can diff them, and so no branch is chosen by
# whichever produces a more attractive recommendation.
MIN_LINK_STRENGTH = 0.20          # below this the link is too weak to act on
MIN_OPEN_INTEREST = 100           # single-name options viability floor
MIN_OPTION_VOLUME = 10
MAX_SPREAD_PCT_OF_MID = 0.25      # wider than this is not executable in size
STEEP_SKEW_THRESHOLD = 0.06       # puts already bid up -> spread/collar, not outright
ELEVATED_IV_THRESHOLD = 0.55      # peer IV already elevated -> market may know
COST_BUDGET_PCT_OF_NOTIONAL = 0.02
WIDE_LAG_CI_TRADING_DAYS = 8      # wider than this and tenor cannot be sized


@dataclass
class PeerOptionsConditions:
    """The peer's own live options-market state. All caller-supplied."""

    ticker: str
    open_interest: Optional[int] = None
    option_volume: Optional[int] = None
    bid_ask_spread_pct_of_mid: Optional[float] = None
    put_skew: Optional[float] = None
    implied_vol: Optional[float] = None
    has_listed_options: bool = True
    sector_etf: Optional[str] = None


@dataclass
class Stage1Score:
    """What Stage 1 hands Stage 2.

    `link_strength_provenance` declares what produced the score -- and, where a
    score has several contributing inputs, a sequence with one entry per input.
    `select_hedge_structure` refuses the whole score if any declared
    contributor is quantum-derived and unvalidated, because "influencing the
    Link-Strength score" covers a single feature just as much as the score
    itself. One unvalidated input is enough to refuse everything downstream
    of it.

    Left as None it declares nothing, which is what every existing caller does
    and is accurate today: no quantum computation exists anywhere in this
    package, which the provenance test suite checks structurally rather than
    assumes. Declare it as soon as a score has a non-classical contributor.
    """

    peer: str
    link_strength: float
    onset_horizon: Optional[int]          # hedge-relevant lag
    peak_horizon: Optional[int] = None    # end of reaction window; NOT tenor
    lag_ci_width_days: Optional[float] = None
    significant: bool = False
    coverage_thinness: Optional[float] = None
    link_strength_provenance: Optional[
        Union[MethodProvenance, Sequence[Optional[MethodProvenance]]]
    ] = None

    @property
    def onset_interval(self) -> Optional[OnsetInterval]:
        """Onset as D7 requires it reported: `[onset - 2, onset]`, never bare.

        `onset_horizon` above stays the raw detected scalar because that is
        what `_tenor_from_onset` consumes, per D8's literal arithmetic. Every
        REPORTING path uses this property instead.
        """
        return OnsetInterval.from_onset(self.onset_horizon)


@dataclass
class HedgeRecommendation:
    peer: str
    structure: str
    rule_fired: str
    rationale: str
    tenor_trading_days: Optional[int] = None
    max_cost_usd: Optional[float] = None
    assumed_exposure: str = (
        "ASSUMED existing long-equity holding in the peer name. Not a real "
        "position. Absent that holding this is a directional long-vol bet, "
        "not a hedge."
    )
    assumed_notional_usd: float = ASSUMED_PEER_EQUITY_NOTIONAL_USD
    no_edge_claim: str = NO_EDGE_CLAIM
    inputs: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "peer": self.peer,
            "structure": self.structure,
            "rule_fired": self.rule_fired,
            "rationale": self.rationale,
            "tenor_trading_days": self.tenor_trading_days,
            "max_cost_usd": self.max_cost_usd,
            "assumed_exposure": self.assumed_exposure,
            "assumed_notional_usd": self.assumed_notional_usd,
            "no_edge_claim": self.no_edge_claim,
            "inputs": self.inputs,
        }


def _tenor_from_onset(onset: int) -> int:
    """Tenor covers the interval's LOWER bound plus buffer.

    TWO axes, and this function has to satisfy both. It used to defend only the
    first, which is how it drifted from the lock.

    ONSET, NOT PEAK. Sizing off the peak buys (W-1) days too much tenor and
    arrives after the move started. That axis was never in dispute -- plan,
    lock and code have always agreed on it.

    THE LOWER BOUND, NOT THE POINT ESTIMATE. GST_HYP04_ANALYSIS_LOCK_v1.0 D8
    (SIGNED 2026-08-20, IN FORCE) sizes tenor off "the interval's LOWER bound
    (onset_horizon - 2)", D7 having fixed a one-sided widening at k = 2. This
    returned onset + 5, off the bare point estimate. The reason matters: D7
    establishes that onset is biased LATE, never early, so sizing off the
    uncorrected point estimate compounds the known error in exactly the
    direction D8 exists to prevent -- the same failure as using the peak, only
    smaller, as inference.py says of itself.

    The code predates the lock by two days (written 2026-08-18, lock signed
    2026-08-20), so D7's line claiming "lock and code state the same thing" was
    never true of this half. It is now.

    THE BUFFER IS THE CODE'S OWN CHOICE, not the lock's. No signed artifact
    specifies any buffer -- "buffer" and "5" appear nowhere in the lock or in
    plan v0.2. It stays a fixed 5 sessions rather than a fitted quantity
    because at this sample size fitting a buffer would be fitting noise.

    THE FLOOR DELIBERATELY DOES NOT REACH THIS FUNCTION. The lock sets no floor
    on onset - 2, so onset = 1 yields a lower bound of -1. A REPORTED interval
    of [-1, 1] would claim a horizon HORIZON_GRID cannot express, so onset.py
    clamps the reported bound (decided 2026-09-04). It stops there: D8 states
    the quantity it sizes off literally, as `onset_horizon - 2`, so this
    function still computes on the raw value and its output is unchanged at
    every onset -- (1 - 2) + 5 = 4, as before.

    The two therefore diverge at onset in {1, 2}. That is disclosed rather than
    reconciled: OnsetInterval.diverges_from_tenor_basis reports when it is
    happening, and the serialised interval carries the tenor basis beside the
    floored bound. Making tenor follow the floor would move hedge tenor at
    those onsets and needs its own dated amendment, not a quiet change here.
    """
    return int(onset) - 2 + 5


def select_hedge_structure(
    score: Stage1Score,
    conditions: PeerOptionsConditions,
    *,
    notional_usd: float = ASSUMED_PEER_EQUITY_NOTIONAL_USD,
    cost_budget_pct: float = COST_BUDGET_PCT_OF_NOTIONAL,
) -> HedgeRecommendation:
    """Decision table. Every branch names the rule that fired.

    Rules are evaluated in order; the first match wins. Ordering is itself a
    preregistered decision: viability gates come before structure selection so
    a structure is never recommended into a market that cannot support it.

    The provenance control runs BEFORE rule R1, ahead of every threshold. A
    quantum-derived Link-Strength score that has not been validated against the
    classical reference does not get evaluated and returned as
    `NO_POSITION` -- returning a recommendation, even a null one, would mean
    the score had been read and acted on. It raises instead. The plan's rule is
    that such a result "should not be permitted to affect any lock, gate, or
    hedge decision", and declining to act because of what the number said is
    still the number affecting the decision.
    """
    assert_may_influence_link_strength(
        score.link_strength_provenance,
        context=f"the Stage 1 Link-Strength score for peer {score.peer!r}",
    )

    budget = notional_usd * cost_budget_pct
    _onset_interval = score.onset_interval
    inputs = {
        "link_strength": score.link_strength,
        # D7: the lag quantity is REPORTED as an interval, never as a point
        # estimate. The bare `onset_horizon` scalar that used to sit here was
        # the reporting-side D7 violation; the raw value is still carried,
        # inside the interval, where its k and its floor travel with it.
        "onset_interval": (_onset_interval.as_dict()
                           if _onset_interval is not None else None),
        "peak_horizon_not_used_for_tenor": score.peak_horizon,
        "lag_ci_width_days": score.lag_ci_width_days,
        "significant": score.significant,
        "coverage_thinness": score.coverage_thinness,
        "open_interest": conditions.open_interest,
        "option_volume": conditions.option_volume,
        "bid_ask_spread_pct_of_mid": conditions.bid_ask_spread_pct_of_mid,
        "put_skew": conditions.put_skew,
        "implied_vol": conditions.implied_vol,
        "cost_budget_usd": budget,
    }

    def rec(structure: str, rule: str, rationale: str,
            tenor: Optional[int] = None,
            cost: Optional[float] = None) -> HedgeRecommendation:
        return HedgeRecommendation(
            peer=score.peer, structure=structure, rule_fired=rule,
            rationale=rationale, tenor_trading_days=tenor,
            max_cost_usd=cost, assumed_notional_usd=notional_usd,
            inputs=inputs,
        )

    # --- R1-R3: is there anything worth acting on at all? -----------------
    if not score.significant:
        return rec(Structure.NO_POSITION, "R1_not_significant",
                   "Stage 1 link is not significant after multiplicity "
                   "correction. No transmission established, nothing to hedge.")

    if score.link_strength < MIN_LINK_STRENGTH:
        return rec(Structure.NO_POSITION, "R2_link_too_weak",
                   f"Link strength {score.link_strength:.3f} below "
                   f"{MIN_LINK_STRENGTH}. Too weak to justify carrying cost.")

    if score.onset_horizon is None:
        return rec(Structure.NO_POSITION, "R3_no_onset_horizon",
                   "No onset horizon cleared significance, so tenor cannot be "
                   "sized. A hedge with an unsized tenor is a guess.")

    # --- R4: lag uncertainty propagates into the decision ------------------
    if (score.lag_ci_width_days is not None
            and score.lag_ci_width_days > WIDE_LAG_CI_TRADING_DAYS):
        return rec(Structure.NO_POSITION, "R4_lag_ci_too_wide",
                   f"Lag CI width {score.lag_ci_width_days:.1f} sessions exceeds "
                   f"{WIDE_LAG_CI_TRADING_DAYS}. Tenor cannot be sized reliably; "
                   "a point estimate would overstate what is known.")

    tenor = _tenor_from_onset(score.onset_horizon)

    # --- R5: no viable single-name options market -> proxy or nothing ------
    if not conditions.has_listed_options:
        if conditions.sector_etf:
            return rec(Structure.SECTOR_ETF_PROXY, "R5a_no_single_name_options",
                       f"No listed options on {conditions.ticker}. Falling back "
                       f"to {conditions.sector_etf} proxy, which hedges sector "
                       "beta only and NOT the peer-specific component.",
                       tenor=tenor, cost=budget)
        return rec(Structure.NO_POSITION, "R5b_no_options_no_proxy",
                   "No listed options and no sector-ETF proxy available.")

    illiquid = (
        (conditions.open_interest is not None
         and conditions.open_interest < MIN_OPEN_INTEREST)
        or (conditions.option_volume is not None
            and conditions.option_volume < MIN_OPTION_VOLUME)
        or (conditions.bid_ask_spread_pct_of_mid is not None
            and conditions.bid_ask_spread_pct_of_mid > MAX_SPREAD_PCT_OF_MID)
    )
    if illiquid:
        if conditions.sector_etf:
            return rec(Structure.SECTOR_ETF_PROXY, "R6a_single_name_illiquid",
                       f"Single-name options too illiquid (OI="
                       f"{conditions.open_interest}, vol={conditions.option_volume}, "
                       f"spread={conditions.bid_ask_spread_pct_of_mid}). Proxy "
                       f"via {conditions.sector_etf}; sector beta only.",
                       tenor=tenor, cost=budget)
        return rec(Structure.NO_POSITION, "R6b_illiquid_no_proxy",
                   "Single-name options illiquid and no proxy available. "
                   "Execution cost would exceed the protection bought.")

    # --- R7: the market may already know ----------------------------------
    # High link strength with ALREADY-ELEVATED peer IV is the case where the
    # relationship is public and priced. The hypothesis is about links the
    # peer's own market has NOT yet reflected, so elevated IV is evidence
    # against acting, not for it.
    if (conditions.implied_vol is not None
            and conditions.implied_vol > ELEVATED_IV_THRESHOLD):
        return rec(Structure.NO_POSITION, "R7_iv_already_elevated",
                   f"Peer IV {conditions.implied_vol:.2f} already above "
                   f"{ELEVATED_IV_THRESHOLD}. The link appears priced; paying "
                   "elevated premium for an already-reflected relationship is "
                   "the opposite of the exploitable case.")

    # --- R8-R10: structure selection under the cost budget -----------------
    if (conditions.put_skew is not None
            and conditions.put_skew > STEEP_SKEW_THRESHOLD):
        return rec(Structure.PUT_SPREAD, "R8_steep_put_skew",
                   f"Put skew {conditions.put_skew:.3f} above "
                   f"{STEEP_SKEW_THRESHOLD}: outright puts are expensive. A put "
                   "spread finances the long strike by selling the steep wing, "
                   "capping protection in exchange for a payable cost.",
                   tenor=tenor, cost=budget)

    if score.link_strength >= 0.50:
        return rec(Structure.PROTECTIVE_PUT, "R9_strong_link_clean_market",
                   f"Link strength {score.link_strength:.3f} with liquid options "
                   "and unremarkable skew. Outright protective put gives "
                   "uncapped downside protection within budget.",
                   tenor=tenor, cost=budget)

    return rec(Structure.COLLAR, "R10_moderate_link_finance_the_hedge",
               f"Link strength {score.link_strength:.3f} is actionable but "
               "moderate. A collar finances the put by selling upside, "
               "appropriate when conviction does not justify paying full "
               "premium out of pocket.",
               tenor=tenor, cost=budget)


def decision_table_summary() -> list[dict[str, str]]:
    """The full rule set, in evaluation order. For the status doc and audits."""
    return [
        {"rule": "R1", "condition": "Stage 1 not significant", "action": Structure.NO_POSITION},
        {"rule": "R2", "condition": f"link_strength < {MIN_LINK_STRENGTH}", "action": Structure.NO_POSITION},
        {"rule": "R3", "condition": "no onset horizon", "action": Structure.NO_POSITION},
        {"rule": "R4", "condition": f"lag CI width > {WIDE_LAG_CI_TRADING_DAYS}d", "action": Structure.NO_POSITION},
        {"rule": "R5", "condition": "no listed options", "action": f"{Structure.SECTOR_ETF_PROXY} or {Structure.NO_POSITION}"},
        {"rule": "R6", "condition": "options illiquid", "action": f"{Structure.SECTOR_ETF_PROXY} or {Structure.NO_POSITION}"},
        {"rule": "R7", "condition": f"peer IV > {ELEVATED_IV_THRESHOLD}", "action": Structure.NO_POSITION},
        {"rule": "R8", "condition": f"put skew > {STEEP_SKEW_THRESHOLD}", "action": Structure.PUT_SPREAD},
        {"rule": "R9", "condition": "link_strength >= 0.50", "action": Structure.PROTECTIVE_PUT},
        {"rule": "R10", "condition": "otherwise", "action": Structure.COLLAR},
    ]
