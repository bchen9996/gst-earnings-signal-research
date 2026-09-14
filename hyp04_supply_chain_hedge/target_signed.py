#!/usr/bin/env python3
"""HYP-07's own target: a SIGNED cumulative abnormal return, not the
direction-agnostic realized-variance-ratio `target.py` computes for
HYP-04/05/06.

=== WHY A NEW TARGET, NOT target.py REUSED ===

HYP-04/05/06 all test the same magnitude-only question: did a peer's
VOLATILITY elevate around an anchor's earnings surprise, regardless of
which way price moved (`target.raw_log_ratio_target` is built from
SQUARED returns -- see that module's own docstring). HYP-07's competitor
mechanism makes a genuinely DIRECTIONAL prediction instead: a rival's bad
earnings surprise should move a competitor's stock the OPPOSITE way (and
vice versa). Reusing the RVar-ratio target would only test "did the
competitor react at all," not the sharper, more specific claim that makes
competitor relationships interesting in the first place -- so this module
exists as a deliberate, real piece of new methodology, not a rescale.

=== THE FORMULA ===

    signed_car(h) = sum_{i=t+1..t+h} (r_peer,i - beta * r_bench,i)
                    - h * mean_{i in [ref_start, ref_end)} (r_peer,i - beta * r_bench,i)

Three choices, each inherited from ALREADY-VALIDATED machinery, not
invented fresh:

  1. Fixed beta=1.0 against SPY, never estimated -- the exact same
     `anchor_shock.BENCHMARK_TICKER`/`BENCHMARK_BETA` convention this
     project already uses on the anchor side (AS-2), applied here
     peer-side. An estimated beta would need an estimation window, and
     choosing that window after seeing how results move is exactly the
     after-the-fact tuning this project's rules exist to prevent.
  2. The reference window is `target.py`'s own `REFERENCE_WINDOW_
     TRADING_DAYS`/`REFERENCE_WINDOW_OFFSET_SESSIONS`, reused unchanged --
     the same 20-session, ends-one-session-before-the-event baseline
     window HYP-04/05/06 already use, just averaged here instead of
     log-variance-ratio'd.
  3. Log returns throughout, matching `anchor_shock.RETURN_BASIS` -- log
     returns are additive across days, which is exactly what makes a
     CUMULATIVE SUM the natural signed analog of RVar's mean.

=== DELIBERATELY NOT PORTED: THE BUCKETED EARNINGS-CYCLE RESIDUALIZER ===

`target.EarningsCycleBaseline` removes a MAGNITUDE confound -- every
company's volatility rises into its own earnings, regardless of any
anchor. A peer's cumulative abnormal RETURN has no equivalent obvious
drift as a function of days-to-its-own-earnings (a return's sign isn't
mechanically pulled one way as earnings approaches, the way variance is
mechanically pulled up). Porting that machinery over without the same
empirical motivation that justified it for the magnitude target would be
inventing new methodology this pass does not attempt to defend. This is a
stated, explicit v1 simplification, not an oversight: `build_feature_
table_signed` still carries `days_to_peer_earnings` as a column (the
control `inference._design_matrix` already applies to every hypothesis's
table, "belt" without the magnitude target's own "suspenders").

=== SIGN CONVENTION: NOTHING IS FLIPPED, ANYWHERE ===

The anchor's raw, SIGNED `excess_return` (already computed and stored by
`anchor_shock.py`, alongside the magnitude-only `shock` HYP-04/05/06 read
instead) is used as-is; `signed_car` above is used as-is. Read the fitted
peak beta's sign directly:

  - Significantly NEGATIVE  -> confirms competitive displacement (anchor
    bad news, peer good news, and vice versa).
  - Significantly POSITIVE  -> comovement/contagion instead -- the
    OPPOSITE of what a competitor relationship predicts. Flagged
    explicitly as evidence the "competitor" label may be picking up
    shared-sector/macro exposure rather than genuine displacement, never
    silently relabeled as a confirming result.
  - Not significant         -> a null, same reporting discipline as
    HYP-04/05/06.

Flipping either the regressor's or the outcome's sign changes nothing
statistical (no p-value, SE, t-stat magnitude, or permutation critical
value moves) -- there is no principled reason to prefer one convention,
so neither is chosen; `inference.py`'s own peak-detection already
separates sign (`HorizonFit.beta`, kept signed) from magnitude
(`abs(...)`, used only to find the peak and drive the permutation null),
so this target slots into that existing separation for free. See
test_hyp04_supply_chain_hedge_target_signed.py's sign-convention
algebraic proof (flipping every event's shock sign flips the recovered
peak beta's sign and changes nothing else, bit-for-bit).

=== A REAL CAVEAT THIS DESIGN SURFACES: peak_horizon MEANS SOMETHING
    DIFFERENT HERE ===

`target.py`'s RVar(h) is a MEAN over an expanding window -- later,
unaffected days DILUTE it, so `peak_horizon = argmax|beta_h|` necessarily
lands at the END of the true reaction window (HYP-04/05/06's own peak
semantics). `signed_car(h)` is a CUMULATIVE SUM instead -- it does not
dilute with additional zero-abnormal-return days past the reaction
window, it PLATEAUS. So for any HYP-07 result, `peak_horizon` should be
read as "where the cumulative effect saturates," not "the single horizon
where a diluting average is least diluted" -- the two are not the same
geometric quantity, even though they share a name. No code changes follow
from this -- `inference.py` stays correct exactly as written -- but any
future reporting of a HYP-07 result must carry this disclosure rather
than silently comparing a HYP-07 peak_horizon next to a HYP-04/05/06 one
as if they measured the same thing.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .anchor_shock import BENCHMARK_BETA, BENCHMARK_TICKER
from .constants import (
    HORIZON_GRID,
    REFERENCE_WINDOW_OFFSET_SESSIONS,
    REFERENCE_WINDOW_TRADING_DAYS,
)
from .fixtures import SyntheticPanel, _days_to_next_earnings


class TargetSignedError(RuntimeError):
    """A precondition does not hold -- reserved for caller misuse (e.g. no
    benchmark series in the panel), never for a per-observation data gap,
    which fails closed to NaN instead."""


def signed_car(
    peer_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    anchor_day: int,
    horizon: int,
    *,
    reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
    reference_offset: int = REFERENCE_WINDOW_OFFSET_SESSIONS,
    benchmark_beta: float = BENCHMARK_BETA,
) -> float:
    """Signed cumulative abnormal return for one (anchor event, peer,
    horizon). See module docstring for the full formula and its
    provenance.

    Post-event window is [anchor_day+1, anchor_day+h], matching
    `target.raw_log_ratio_target` exactly, for direct positional
    comparability. Fails closed to NaN on a short/missing window or any
    non-finite input in either window -- mirrors
    `target.raw_log_ratio_target`'s own discipline; never a fabricated
    zero.
    """
    n = peer_returns.size
    if benchmark_returns.size != n:
        raise TargetSignedError(
            f"peer_returns has {n} sessions but benchmark_returns has "
            f"{benchmark_returns.size} -- both must share the same "
            "session index. A length mismatch is a caller error, not a "
            "per-observation data gap.")

    start, stop = anchor_day + 1, anchor_day + 1 + horizon
    if stop > n:
        return float("nan")
    ref_end = anchor_day - reference_offset + 1      # exclusive
    ref_start = max(0, ref_end - reference_window)
    if ref_end - ref_start < reference_window:
        return float("nan")

    post_peer = peer_returns[start:stop]
    post_bench = benchmark_returns[start:stop]
    ref_peer = peer_returns[ref_start:ref_end]
    ref_bench = benchmark_returns[ref_start:ref_end]

    if not (np.all(np.isfinite(post_peer)) and np.all(np.isfinite(post_bench))
            and np.all(np.isfinite(ref_peer)) and np.all(np.isfinite(ref_bench))):
        return float("nan")

    post_excess = post_peer - benchmark_beta * post_bench
    ref_excess = ref_peer - benchmark_beta * ref_bench

    return float(np.sum(post_excess) - horizon * np.mean(ref_excess))


def build_feature_table_signed(
    panel: SyntheticPanel,
    *,
    horizons: tuple[int, ...] = HORIZON_GRID,
    reference_offset: int = REFERENCE_WINDOW_OFFSET_SESSIONS,
    benchmark_ticker: str = BENCHMARK_TICKER,
    benchmark_beta: float = BENCHMARK_BETA,
) -> dict[str, Any]:
    """Assemble the (anchor event x peer x horizon) panel for HYP-07's
    signed target. Same table schema `inference.py`'s `_design_matrix`/
    `fit_local_projections`/`local_projection_analysis` already expect
    (`event_id`, `anchor`, `peer`, `horizon`, `shock`, `calendar_period`,
    `days_to_peer_earnings`, `target`) -- reused unchanged, zero edits, by
    matching the contract rather than importing `target.py`'s own
    (different-formula) builder.

    `panel.returns` must carry `benchmark_ticker`'s own series alongside
    every real peer's -- the same panel-construction path that adds each
    locked peer's closes can add one more ticker (SPY) the same way, no
    special-casing needed downstream.
    """
    if benchmark_ticker not in panel.returns:
        raise TargetSignedError(
            f"no {benchmark_ticker!r} return series in panel.returns -- "
            "the signed target needs a benchmark series fetched and "
            "carried alongside every peer's own.")
    benchmark_returns = panel.returns[benchmark_ticker]

    dte_cache = {
        p: _days_to_next_earnings(panel.n_trading_days,
                                  panel.peer_earnings_days.get(p, []))
        for p in panel.returns if p != benchmark_ticker
    }

    rows: dict[str, list] = {
        "event_id": [], "anchor": [], "peer": [], "horizon": [],
        "shock": [], "calendar_period": [], "anchor_day": [],
        "days_to_peer_earnings": [], "target": [],
    }
    n_candidate_obs = 0
    n_excluded_nan = 0

    for ev_i, ev in enumerate(panel.anchor_events):
        for peer in ev["peers"]:
            if peer == benchmark_ticker:
                continue
            returns = panel.returns[peer]
            for h in horizons:
                n_candidate_obs += 1
                val = signed_car(
                    returns, benchmark_returns, ev["anchor_day"], h,
                    reference_offset=reference_offset,
                    benchmark_beta=benchmark_beta)
                if not np.isfinite(val):
                    n_excluded_nan += 1
                    continue
                dte_val = float(dte_cache[peer][ev["anchor_day"]])
                rows["event_id"].append(ev_i)
                rows["anchor"].append(ev["anchor"])
                rows["peer"].append(peer)
                rows["horizon"].append(h)
                rows["shock"].append(ev["shock"])
                rows["calendar_period"].append(ev["calendar_period"])
                rows["anchor_day"].append(ev["anchor_day"])
                rows["days_to_peer_earnings"].append(dte_val)
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
        "target": np.asarray(rows["target"], dtype=float),
    }

    return {
        "table": table,
        "residualized": False,
        "residualization_note": (
            "No bucketed earnings-cycle residualizer -- see module "
            "docstring, 'DELIBERATELY NOT PORTED'. days_to_peer_earnings "
            "is still carried as a design-matrix control."),
        "n_candidate_observations": n_candidate_obs,
        "n_excluded_short_or_missing_window": n_excluded_nan,
        "excluded_fraction": (
            n_excluded_nan / n_candidate_obs if n_candidate_obs else 0.0),
    }
