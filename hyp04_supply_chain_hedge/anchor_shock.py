#!/usr/bin/env python3
"""HYP-04 anchor-side shock. FAIL-CLOSED. Every unknown denies.

=== WHY THIS MODULE EXISTS ===

HYP-04's estimator regresses peer abnormal volatility on a per-anchor-event
scalar called `shock` -- the only anchor-side quantity in the model. Until
2026-08-29 that scalar had NO production definition. It existed solely in
`fixtures.py` as `abs(rng.normal(0.0, 1.0))`, the model plan offered
"confirmed |excess return| or GST z-score" without choosing, and none of the
four decisions in the dated analysis lock was this one.

Meanwhile `required_eligibility_class` inherited HYP-01's
`core_attention_vs_equity_response`, which requires the strict six-field gate --
gst_zscore, wiki_zscore, panel_implied_volatility, realized_volatility,
previous_close, volume, plus a pre-event snapshot. So certifying ONE HYP-04
anchor event required two attention series and an option chain, and the choice
of shock was being made by side effect through an inherited class.

The repo owner determined 2026-08-29 that HYP-04 tests INFORMATION TRANSMISSION
along supply-chain links -- how an anchor's earnings news dictates volatility
and a range of price changes for stocks across the supply chain. See
`Live Signal Engine/HYP04_ANCHOR_SHOCK_DEFINITION_MEMO_2026-08-29.md` and its
same-day amendment.

=== THE SAME PRECEDENT pair_eligibility SET ===

There is no class in `gst_market_response.completeness.HYPOTHESIS_CLASSES` for
"the anchor's earnings-day excess return is well measured", and none is created
here. `pair_eligibility` faced the identical situation on the peer side and
resolved it by keeping HYP-04's own requirement in HYP-04's own package, leaving
HYP-01's confirmatory infrastructure untouched. This module does the same on the
anchor side. NOTHING under `gst_market_response/` is modified or extended.

=== WHAT IT DOES NOT DO ===

It computes a shock from returns handed to it. It fetches nothing, and a module
that CAN compute is not computed data -- the same distinction that keeps HYP-04's
status unchanged. No anchor shock has been computed from production data through
this module, and importing it moves no registry field.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ANCHOR_SHOCK_RULE_ID = "HYP04-ANCHOR-SHOCK-RULE-v1"

# The benchmark is FIXED IN ADVANCE and its coefficient is not estimated.
#
# An estimated beta would need an estimation window, and choosing that window
# after seeing how the results move is precisely the after-the-fact tuning this
# project's rules exist to prevent. Worse, a beta fitted on the full sample uses
# post-event data to define a pre-event expectation -- look-ahead by
# construction, the same defect class as the reconstructed GST z-score history.
#
# beta = 1 against a broad-market proxy is therefore chosen for being
# ASSUMPTION-FREE rather than for being the best-fitting model. It is a stated
# limitation, not a claim that the market model is correct.
BENCHMARK_TICKER = "SPY"
BENCHMARK_BETA = 1.0

# A same-session return from t-1 close to t close cannot be revised by anything
# that happens after t, which is the property the shock needs and the property a
# search-attention z-score does not have. Split and dividend adjustment rescales
# a price series uniformly and therefore leaves a daily RATIO unchanged, so an
# adjusted series does not retroactively rewrite a computed daily return.
POINT_IN_TIME_BASIS = (
    "A daily return is computed from the t-1 and t closes only. No input to it "
    "postdates session t, so it cannot be revised by later information. Uniform "
    "split/dividend adjustment rescales the series and leaves the daily ratio "
    "unchanged. This is the asymmetry that separates a price-based shock from a "
    "search-attention z-score, whose value depends on the query window used at "
    "download time."
)

# A daily excess return outside this band is treated as a DATA ERROR rather than
# an extraordinary session. The bound is deliberately loose: it is a parse
# guard, not an outlier filter, and it is applied before any result is seen.
# Mirrors the extractor's rule that a concentration above 100% is a parse error.
MAX_ABS_EXCESS_RETURN = 2.0

# HOW A "RETURN" IS COMPUTED. Declared by registry v1.10.
#
# This module has always ACCEPTED returns and never computed them, so simple
# vs log was never stated anywhere -- a gap found while planning the anchor-side
# collection, not by anything failing. At daily scale the two differ in the
# third decimal, which is exactly why it would never have surfaced as a bug and
# exactly why it has to be written down: two collections computed under
# different conventions are not comparable, and nothing would say so.
#
# LOG, matching `peer_returns`, which builds log(p_t / p_{t-1}) and is the other
# half of every pair this shock is joined to. One convention across both sides
# of the join beats the marginally more conventional choice on one side.
#
# Both legs of the excess return use it. Mixing bases -- a log anchor return
# against a simple benchmark return -- would put a small systematic wedge in
# every excess return, largest exactly on the big-move days that carry the
# signal.
RETURN_BASIS = "log"
RETURN_BASIS_DEFINITION = "log(close_t / close_{t-1})"
RETURN_BASIS_NOTE = (
    "Both legs use the same basis. This module does not compute returns -- it "
    "accepts them -- so the basis is a CONTRACT WITH THE CALLER, not something "
    "it can enforce. It is declared here and in the registry so a series "
    "collected under the other convention is a stated mismatch rather than a "
    "silent one.")

RULE_CONDITIONS: tuple[tuple[str, str], ...] = (
    ("AS-1", "The shock is measured on the session the earnings release is "
             "ATTRIBUTED to -- the same session the peer target indexes as "
             "anchor_day. The attribution itself (BMO on the same session, "
             "otherwise the next) is delegated, never reimplemented here."),
    ("AS-2", "excess = anchor_return - BENCHMARK_BETA * benchmark_return, with "
             "the benchmark fixed in advance and its coefficient NOT estimated."),
    ("AS-3", "Both returns must be present and finite for that session. A "
             "missing benchmark return denies; it is never treated as zero."),
    ("AS-4", "shock = |excess|. The hypothesis is about VOLATILITY "
             "transmission, which is a magnitude response, and the estimator's "
             "shock column has always been non-negative."),
    ("AS-5", "One shock per anchor event, constant across that event's peers -- "
             "the unit the permutation test already permutes."),
    ("AS-6", "Fail closed. Any missing, unparseable or out-of-band input denies "
             "the event. Nothing is imputed, inferred, or defaulted to zero."),
)


class AnchorShockError(ValueError):
    """Fail-closed: an input is missing, unparseable, or out of band."""


@dataclass(frozen=True)
class AnchorShock:
    """One anchor event's shock, with the arithmetic kept visible.

    Both legs are retained rather than only the result, so a reader can check
    the subtraction against the filing-day data instead of trusting this module.
    """

    event_id: str
    anchor_ticker: str
    session: str
    anchor_return: float
    benchmark_return: float
    excess_return: float
    shock: float
    benchmark_ticker: str = BENCHMARK_TICKER
    benchmark_beta: float = BENCHMARK_BETA
    rule_id: str = ANCHOR_SHOCK_RULE_ID

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "anchor_ticker": self.anchor_ticker,
            "session": self.session,
            "anchor_return": self.anchor_return,
            "benchmark_return": self.benchmark_return,
            "excess_return": self.excess_return,
            "shock": self.shock,
            "benchmark_ticker": self.benchmark_ticker,
            "benchmark_beta": self.benchmark_beta,
            "rule_id": self.rule_id,
        }


def _finite(x: Any) -> Optional[float]:
    """A number, or None. Booleans are NOT numbers here.

    `isinstance(True, int)` is True in Python, so an unguarded float() would
    turn a stray True into a 1.0 return -- a fabricated 100% move.
    """
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def excess_return(anchor_return: Any, benchmark_return: Any) -> Optional[float]:
    """AS-2. Returns None if either leg is missing or non-finite."""
    a = _finite(anchor_return)
    b = _finite(benchmark_return)
    if a is None or b is None:
        return None
    return a - BENCHMARK_BETA * b


def shock_for_event(
    *,
    event_id: str,
    anchor_ticker: str,
    attributed_session: str,
    anchor_return: Any,
    benchmark_return: Any,
) -> tuple[Optional[AnchorShock], list[str]]:
    """Return (shock, denials). A non-empty denial list means NO shock.

    `attributed_session` must already be resolved by the caller -- this module
    does not decide which session an earnings release affects, for the same
    reason `event_panel` does not: that decision belongs to the authoritative
    XNYS calendar, and reimplementing it here would create a second, divergent
    answer to a question that already has one.
    """
    denials: list[str] = []

    eid = (event_id or "").strip()
    if not eid:
        denials.append("AS-6 FAILED: blank event_id.")
    tk = (anchor_ticker or "").strip().upper()
    if not tk:
        denials.append("AS-6 FAILED: blank anchor_ticker.")

    sess = (attributed_session or "").strip()
    if not DATE_RE.match(sess):
        denials.append(
            f"AS-1 FAILED: attributed_session {attributed_session!r} is not an "
            "ISO date. The session must be resolved by the caller against the "
            "XNYS calendar; this module refuses to guess it.")

    a = _finite(anchor_return)
    if a is None:
        denials.append(
            f"AS-3 FAILED: anchor return {anchor_return!r} is missing or "
            "non-finite.")
    b = _finite(benchmark_return)
    if b is None:
        denials.append(
            f"AS-3 FAILED: benchmark ({BENCHMARK_TICKER}) return "
            f"{benchmark_return!r} is missing or non-finite. A missing "
            "benchmark is NEVER read as zero -- that would silently promote a "
            "raw return to an excess return.")

    if denials:
        return None, denials

    ex = a - BENCHMARK_BETA * b
    if abs(ex) > MAX_ABS_EXCESS_RETURN:
        return None, [
            f"AS-6 FAILED: |excess| {abs(ex):.4f} exceeds "
            f"{MAX_ABS_EXCESS_RETURN}. Treated as a data error rather than an "
            "extraordinary session; the bound is a parse guard fixed before any "
            "result is seen, not an outlier filter."]

    return AnchorShock(
        event_id=eid,
        anchor_ticker=tk,
        session=sess,
        anchor_return=a,
        benchmark_return=b,
        excess_return=ex,
        shock=abs(ex),
    ), []


def is_shock_eligible(
    *,
    event_id: str,
    anchor_ticker: str,
    attributed_session: str,
    anchor_return: Any,
    benchmark_return: Any,
) -> bool:
    """AS-1..AS-6 all hold. Convenience only; `shock_for_event` gives reasons."""
    shock, denials = shock_for_event(
        event_id=event_id, anchor_ticker=anchor_ticker,
        attributed_session=attributed_session, anchor_return=anchor_return,
        benchmark_return=benchmark_return)
    return shock is not None and not denials


def rule_description() -> dict[str, Any]:
    """The rule, for a registry version to declare rather than paraphrase."""
    return {
        "rule_id": ANCHOR_SHOCK_RULE_ID,
        "shock_definition": "abs(anchor_return - beta * benchmark_return)",
        "benchmark_ticker": BENCHMARK_TICKER,
        "benchmark_beta": BENCHMARK_BETA,
        "beta_is_estimated": False,
        "max_abs_excess_return": MAX_ABS_EXCESS_RETURN,
        "return_basis": RETURN_BASIS,
        "return_basis_definition": RETURN_BASIS_DEFINITION,
        "return_basis_note": RETURN_BASIS_NOTE,
        "point_in_time_basis": POINT_IN_TIME_BASIS,
        "conditions": [{"id": c, "text": t} for c, t in RULE_CONDITIONS],
        "measurement_status": (
            "NO anchor shock has been computed from production data through "
            "this module. A module that CAN compute is not computed data."),
    }
