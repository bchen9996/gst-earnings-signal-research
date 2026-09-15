#!/usr/bin/env python3
"""HYP-08's target: the peer's SIGNED excess return on the SAME trading
session as the anchor's own earnings release. No horizon grid, no
cumulation -- the genuinely distinct design external review asked for
after HYP-06 and HYP-07 (see `HYP08_SameSessionReactionHeterogeneity_
MODEL_PLAN_<date>.md`).

=== WHY NOT target_signed.py's signed_car(h) ===

`signed_car`'s post-event window is `[anchor_day+1, anchor_day+1+h)` --
strictly AFTER the anchor's own event day, and `HORIZON_GRID = range(1,
21)` has no h=0 case. Even HYP-07's own target starts one session late
relative to what "same-session" means. `same_session_excess_return` below
reads the peer's return on `attributed_session` itself -- the exact
session index `anchor_shock.py` already resolves BMO/AMC release timing
to for the ANCHOR's own excess return -- so both sides of the comparison
are measured on the same, single, already-validated session.

=== POOLING TWO RELATIONSHIP TYPES, ON PURPOSE ===

Unlike `target.py` (customer/supplier only) or `target_signed.py`
(competitor only), this module's `build_feature_table_same_session`
expects `panel.anchor_events` to carry a `relationship_type` string on
every event (already a real field on both HYP-06's and HYP-07's own
locked events) and derives one boolean design column from it,
`is_competitor`. This is what lets a single call test BOTH of external
review's literal questions: an average same-session effect (pooled
`shock` coefficient) AND reaction heterogeneity between relationship
types (the `shock x is_competitor` interaction `inference.
fit_interaction_model` fits) -- see that function's own docstring for
why a plain pooled coefficient and the interaction term are complementary
tests, not redundant ones.

=== SIGN CONVENTION, UNCHANGED FROM target_signed.py ===

Nothing is flipped. The anchor's raw signed `excess_return` and the raw
signed same-session excess return are used as-is. A priori, economically
motivated predictions (stated before any fit, not discovered after):
customer/supplier peers should show a POSITIVE coefficient (shared
revenue chain -- comovement); competitor peers should show a NEGATIVE
coefficient (displacement, same convention `target_signed.py` already
uses). Not significant is a null either way.

=== EVERY ROW'S horizon FIELD IS THE CONSTANT 0 ===

Not a real horizon grid position -- there is no grid. Set this way purely
so the existing table schema (`event_id`, `anchor`, `peer`, `horizon`,
`shock`, `calendar_period`, `days_to_peer_earnings`, `target`) stays
compatible with `inference.fit_local_projections(table, horizons=(0,),
...)`, letting the primary same-session fit reuse that function, and
`clustered_se.cr_vcov`/`satterthwaite_df` beneath it, completely
unchanged.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .anchor_shock import BENCHMARK_BETA, BENCHMARK_TICKER
from .fixtures import SyntheticPanel, _days_to_next_earnings

#: The only two relationship-type strings this module maps to a design
#: column. Anything else refuses rather than silently defaulting to one
#: side -- see build_feature_table_same_session's own check.
CUSTOMER_SUPPLIER_TYPES = frozenset({
    "direct_supplier", "direct_customer", "supplier", "customer",
})
COMPETITOR_TYPES = frozenset({"competitor", "sector_competitor"})


class TargetSameSessionError(RuntimeError):
    """A precondition does not hold -- caller misuse (no benchmark series,
    an unrecognized relationship_type), never a per-observation data gap,
    which fails closed to NaN instead."""


def same_session_excess_return(
    peer_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    anchor_day: int,
    *,
    benchmark_beta: float = BENCHMARK_BETA,
) -> float:
    """The peer's benchmark-adjusted return on the anchor's own event-day
    session, and nothing else -- no reference window, no cumulation.

    Fails closed to NaN if `anchor_day` falls outside either series (a
    real, possible data gap near the edge of fetched history) or either
    session's return is non-finite. Never a fabricated zero, mirroring
    `target.raw_log_ratio_target`'s and `target_signed.signed_car`'s own
    discipline.
    """
    n = peer_returns.size
    if benchmark_returns.size != n:
        raise TargetSameSessionError(
            f"peer_returns has {n} sessions but benchmark_returns has "
            f"{benchmark_returns.size} -- both must share the same "
            "session index. A length mismatch is a caller error, not a "
            "per-observation data gap.")
    if not (0 <= anchor_day < n):
        return float("nan")

    peer_r = peer_returns[anchor_day]
    bench_r = benchmark_returns[anchor_day]
    if not (np.isfinite(peer_r) and np.isfinite(bench_r)):
        return float("nan")

    return float(peer_r - benchmark_beta * bench_r)


def _is_competitor(relationship_type: str) -> float:
    if relationship_type in COMPETITOR_TYPES:
        return 1.0
    if relationship_type in CUSTOMER_SUPPLIER_TYPES:
        return 0.0
    raise TargetSameSessionError(
        f"relationship_type {relationship_type!r} is not one of "
        f"{sorted(COMPETITOR_TYPES | CUSTOMER_SUPPLIER_TYPES)} -- refusing "
        "to silently default it to either side of the heterogeneity "
        "split.")


def build_feature_table_same_session(
    panel: SyntheticPanel,
    *,
    benchmark_ticker: str = BENCHMARK_TICKER,
    benchmark_beta: float = BENCHMARK_BETA,
) -> dict[str, Any]:
    """Assemble the (anchor event x peer) same-session table. Same schema
    `inference.py`'s `_design_matrix`/`fit_local_projections` already
    expect, reused unchanged, plus one new column (`is_competitor`) the
    new interaction fit reads. Every row's `horizon` is the constant 0 --
    see module docstring.

    `panel.returns` must carry `benchmark_ticker`'s own series, exactly
    as `target_signed.build_feature_table_signed` requires.
    """
    if benchmark_ticker not in panel.returns:
        raise TargetSameSessionError(
            f"no {benchmark_ticker!r} return series in panel.returns -- "
            "the same-session target needs a benchmark series fetched "
            "and carried alongside every peer's own.")
    benchmark_returns = panel.returns[benchmark_ticker]

    dte_cache = {
        p: _days_to_next_earnings(panel.n_trading_days,
                                  panel.peer_earnings_days.get(p, []))
        for p in panel.returns if p != benchmark_ticker
    }

    rows: dict[str, list] = {
        "event_id": [], "anchor": [], "peer": [], "horizon": [],
        "shock": [], "calendar_period": [], "anchor_day": [],
        "days_to_peer_earnings": [], "relationship_type": [],
        "is_competitor": [], "target": [],
    }
    n_candidate_obs = 0
    n_excluded_nan = 0

    for ev_i, ev in enumerate(panel.anchor_events):
        rel_type = ev["relationship_type"]
        is_comp = _is_competitor(rel_type)
        for peer in ev["peers"]:
            if peer == benchmark_ticker:
                continue
            returns = panel.returns[peer]
            n_candidate_obs += 1
            val = same_session_excess_return(
                returns, benchmark_returns, ev["anchor_day"],
                benchmark_beta=benchmark_beta)
            if not np.isfinite(val):
                n_excluded_nan += 1
                continue
            dte_val = float(dte_cache[peer][ev["anchor_day"]])
            rows["event_id"].append(ev_i)
            rows["anchor"].append(ev["anchor"])
            rows["peer"].append(peer)
            rows["horizon"].append(0)
            rows["shock"].append(ev["shock"])
            rows["calendar_period"].append(ev["calendar_period"])
            rows["anchor_day"].append(ev["anchor_day"])
            rows["days_to_peer_earnings"].append(dte_val)
            rows["relationship_type"].append(rel_type)
            rows["is_competitor"].append(is_comp)
            rows["target"].append(val)

    table = {
        "event_id": np.asarray(rows["event_id"], dtype=int),
        "anchor": np.asarray(rows["anchor"], dtype=object),
        "peer": np.asarray(rows["peer"], dtype=object),
        "horizon": np.asarray(rows["horizon"], dtype=int),
        "shock": np.asarray(rows["shock"], dtype=float),
        "calendar_period": np.asarray(rows["calendar_period"], dtype=int),
        "anchor_day": np.asarray(rows["anchor_day"], dtype=int),
        "days_to_peer_earnings": np.asarray(rows["days_to_peer_earnings"], dtype=float),
        "relationship_type": np.asarray(rows["relationship_type"], dtype=object),
        "is_competitor": np.asarray(rows["is_competitor"], dtype=float),
        "target": np.asarray(rows["target"], dtype=float),
    }

    n_competitor = int(np.sum(table["is_competitor"] == 1.0))
    return {
        "table": table,
        "residualized": False,
        "residualization_note": (
            "No residualizer of any kind, same v1 simplification "
            "target_signed.py states -- days_to_peer_earnings is still "
            "carried as a design-matrix control."),
        "n_candidate_observations": n_candidate_obs,
        "n_excluded_short_or_missing_window": n_excluded_nan,
        "excluded_fraction": (
            n_excluded_nan / n_candidate_obs if n_candidate_obs else 0.0),
        "n_rows": int(table["event_id"].size),
        "n_rows_customer_supplier": int(table["event_id"].size) - n_competitor,
        "n_rows_competitor": n_competitor,
    }
