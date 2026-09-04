#!/usr/bin/env python3
"""Inference layer -- HYP-04 Phase 0, build step 3.

Primary lag estimator: LOCAL PROJECTIONS (Jorda-style). For each horizon h in
the grid, regress the residualized abnormal-vol target at h on the anchor's
shock magnitude plus controls, with cluster-robust SEs. The resulting beta_h
sequence is an impulse-response profile. The horizon where beta_h peaks is the
END of the reaction window; the first horizon clearing significance is its
ONSET, and onset is the hedge-relevant one.

Local projections rather than a raw CCF because CCF cannot condition on
controls at each lag (so a "significant" lag can be shared sector-wide
movement rather than anchor-specific transmission) and is vulnerable to
spurious correlation when either series is autocorrelated. The prewhitened
CCF is kept as a SECONDARY classical cross-check, never as the decision-maker.

MULTIPLICITY. Significance is judged on max_h |t_h| over ~20 horizons, which is
a max-selection over correlated statistics. Uncorrected per-horizon p-values
are meaningless for it. Significance therefore comes from a max-T PERMUTATION null,
not Bonferroni: RVar(h) is a mean over an expanding window, so adjacent beta_h
are correlated by construction and Bonferroni would be badly over-conservative
against that correlation.

The reported PEAK LOCATION is argmax|beta_h|, a SEPARATE quantity from the
max_h |t_h| this paragraph is about -- see LocalProjectionResult.

The permutation shuffles SHOCK MAGNITUDES ACROSS ANCHOR EVENTS, holding the
panel's cluster structure fixed. That preserves within-event correlation among
peers under the null -- an iid shuffle of rows would destroy it and produce an
anticonservative null, which is the same class of error the prewhitening
direction fix addressed on the CCF side.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .clustered_se import (
    TWO_WAY_CLUSTERING_IMPLEMENTED,
    TWO_WAY_LIMITATION_NOTE,
    cr_vcov,
    ols,
    satterthwaite_df,
)

from .constants import (
    HORIZON_GRID,
    LOCKED_CLUSTER_KEY,
    N_PERMUTATIONS,
    RANDOM_SEED,
)
from .onset import OnsetInterval
from .quantum_provenance import assert_may_influence_link_strength


# ==========================================================================
# Local projections
# ==========================================================================
@dataclass
class HorizonFit:
    horizon: int
    beta: float
    se: float
    t_stat: float
    satterthwaite_dof: float
    n_obs: int
    n_clusters: int


@dataclass
class LocalProjectionResult:
    """Two different lag quantities, deliberately reported separately.

    The plan says "the horizon where it peaks and clears significance is the
    estimated lag." With an EXPANDING-WINDOW target those are two different
    horizons, and conflating them systematically overstates the lag.

    RVar(h) averages over [1, h]. If peer vol is elevated on days
    [L, L+W-1] after the anchor, the affected FRACTION of that window is
    (h-L+1)/h for L <= h < L+W -- maximized at h = L+W-1, after which
    unaffected days dilute it. So:

        onset_horizon  = first h clearing significance  -> L      (ONSET)
        peak_horizon   = argmax_h |beta_h|              -> L+W-1  (END)

    Confirmed empirically on synthetic fixtures: peak_horizon matched L+W-1 on
    15 of 15 (L, W) combinations under the D1-locked clustering, and
    first-significant matched L within the stated late bias.

    PEAK IS argmax|beta|, NOT argmax|t|, and the distinction is load-bearing.
    Plan v0.2 section 3.5 defines it on beta. A location estimate must not move
    when the variance estimate changes, and argmax|t| does: under the
    calendar_period clustering the signed lock requires it recovered the
    injected peak only 9 of 15 times, worst miss h=6 reported at h=15.

    max_abs_t is kept SEPARATE because the max-T permutation null is the
    distribution of max_h |t_h|. Comparing anything else to its critical value
    would be comparing a statistic to a null built for a different one.

    ONSET_HORIZON IS THE HEDGE-RELEVANT ONE. Stage 2 sizes tenor against when
    the reaction STARTS; using the peak would buy a tenor (W-1) days too long
    and be late to the move.

    KNOWN LIMITATION -- onset detection is LATE-BIASED, and the bias grows
    with lag depth. At the onset horizon itself, only (h-L+1)/h = 1/L of the
    averaging window is affected, so the signal there is diluted by exactly
    1/L. Deeper lags therefore carry thinner margin over the
    multiplicity-corrected threshold, and on an unlucky draw the true onset
    horizon fails to clear while h = L+1 does. Measured on synthetic fixtures
    at effect 0.55: |t| at h=L was 5.58 (L=3), 3.53 (L=5), 3.98 (L=8) and 4.69
    (L=10) against critical values near 2.6-2.9 -- real margin, but one draw at
    L=8 produced |t| = 2.08 and reported onset = 9.

    The error direction is ONE-SIDED and conservative in the detection sense:
    onset is reported LATE, never early (h < L carried |t| = 0.71 in that same
    draw). But late onset means a SHORT hedge tenor, which is the same
    direction of practical error as using the peak, just smaller. Report the
    onset with that caveat rather than as a point estimate.
    """

    fits: list[HorizonFit]
    peak_horizon: Optional[int]
    peak_abs_t: float
    onset_horizon: Optional[int] = None
    onset_abs_t: Optional[float] = None
    max_t_critical_value: Optional[float] = None
    max_t_p_value: Optional[float] = None
    max_abs_t: Optional[float] = None
    peak_significant: Optional[bool] = None
    n_permutations: int = 0
    effective_independent_tests: Optional[float] = None
    clustering: str = f"one-way ({LOCKED_CLUSTER_KEY}) -- D1"
    clustering_limitation: str = TWO_WAY_LIMITATION_NOTE
    two_way_implemented: bool = TWO_WAY_CLUSTERING_IMPLEMENTED

    @property
    def onset_interval(self) -> Optional[OnsetInterval]:
        """Onset in the only shape D7 permits it to be reported in.

        `onset_horizon` stays on this dataclass as the raw detected scalar --
        it is what detection produced and what D8's tenor arithmetic consumes.
        Anything that REPORTS the lag quantity uses this instead, because D7
        forbids reporting it as a point estimate.
        """
        return OnsetInterval.from_onset(self.onset_horizon)

    @property
    def horizons(self) -> list[int]:
        return [f.horizon for f in self.fits]

    @property
    def betas(self) -> np.ndarray:
        return np.array([f.beta for f in self.fits])

    @property
    def abs_t(self) -> np.ndarray:
        return np.array([abs(f.t_stat) for f in self.fits])


def _design_matrix(table: dict[str, np.ndarray], mask: np.ndarray,
                   controls: bool = True) -> np.ndarray:
    """Intercept + shock magnitude (+ controls).

    The control is days-to-the-peer's-own-earnings. It is included even though
    the target is already residualized against that same index, because
    residualization removes the peer's own UNCONDITIONAL mean pattern while
    this absorbs any residual linear dependence at the event level. Belt and
    suspenders on the confound the whole target definition exists to defeat.
    """
    cols = [np.ones(int(mask.sum())), table["shock"][mask]]
    if controls:
        cols.append(table["days_to_peer_earnings"][mask])
    return np.column_stack(cols)


def fit_local_projections(
    table: dict[str, np.ndarray],
    *,
    horizons: tuple[int, ...] = HORIZON_GRID,
    controls: bool = True,
    cluster_key: str = LOCKED_CLUSTER_KEY,
) -> list[HorizonFit]:
    """One clustered regression per horizon. Shock coefficient is index 1."""
    fits: list[HorizonFit] = []
    c_vec = None
    for h in horizons:
        mask = table["horizon"] == h
        if mask.sum() < 3:
            continue
        X = _design_matrix(table, mask, controls=controls)
        y = table["target"][mask]
        g = table[cluster_key][mask]
        if np.unique(g).size < 2:
            continue

        beta, V, G = cr_vcov(X, y, g, "CR2")
        var = float(V[1, 1])
        if not np.isfinite(var) or var <= 0:
            continue
        se = float(np.sqrt(var))

        if c_vec is None or c_vec.size != X.shape[1]:
            c_vec = np.zeros(X.shape[1])
            c_vec[1] = 1.0
        dof = satterthwaite_df(X, g, c_vec)

        fits.append(HorizonFit(
            horizon=int(h), beta=float(beta[1]), se=se,
            t_stat=float(beta[1] / se), satterthwaite_dof=dof,
            n_obs=int(mask.sum()), n_clusters=int(G),
        ))
    return fits


def _max_abs_t_for_shuffle(
    table: dict[str, np.ndarray],
    horizons: tuple[int, ...],
    controls: bool,
    shuffled_shock: np.ndarray,
    cluster_key: str = LOCKED_CLUSTER_KEY,
) -> float:
    """max_h |t_h| under one permutation. Mirrors fit_local_projections' math.

    The cluster key must match the one the observed fit used. It was hardcoded
    to event_id here while fit_local_projections took a parameter, so the null
    was clustered on a different dimension from the statistic it calibrated.
    """
    swapped = dict(table)
    swapped["shock"] = shuffled_shock
    best = 0.0
    for h in horizons:
        mask = swapped["horizon"] == h
        if mask.sum() < 3:
            continue
        X = _design_matrix(swapped, mask, controls=controls)
        y = swapped["target"][mask]
        g = swapped[cluster_key][mask]
        if np.unique(g).size < 2:
            continue
        beta, V, _ = cr_vcov(X, y, g, "CR2")
        var = float(V[1, 1])
        if not np.isfinite(var) or var <= 0:
            continue
        best = max(best, abs(float(beta[1] / np.sqrt(var))))
    return best


def max_t_permutation(
    table: dict[str, np.ndarray],
    *,
    horizons: tuple[int, ...] = HORIZON_GRID,
    controls: bool = True,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = RANDOM_SEED,
    observed_max_abs_t: Optional[float] = None,
    cluster_key: str = LOCKED_CLUSTER_KEY,
) -> dict[str, Any]:
    """max-T permutation null over the horizon grid.

    Shock magnitudes are permuted ACROSS ANCHOR EVENTS and re-broadcast to
    that event's peers, so every peer of an event still shares one shock value
    and the within-event correlation structure survives the null. Shuffling
    rows independently would break that and make the null anticonservative.

    The permutation is RESTRICTED to within cluster_key, for the same reason
    at the level above. Under D1 the SE clusters on calendar_period, so period
    carries common variation in peer volatility; anchor shocks vary by period
    too, since earnings seasons differ. Permuting shocks freely across periods
    decouples shock from period and strips that confounding out of the null
    while leaving it in the observed statistic -- a null narrower than the
    truth, which is anticonservative. It is exactly the error the paragraph
    above guards against on the peer dimension, one level up.

    An event's cluster must be constant within the event, and that is
    verified rather than assumed by taking a silent first value.

    When every cluster holds exactly one event -- what cluster_key="event_id"
    produces -- there is no within-cluster structure to preserve and the
    clustering asserts independence across clusters, so the permutation is
    unrestricted. That is the correct null for that choice, not a fallback.
    The mode taken is reported in the result.

    Also returns the EFFECTIVE NUMBER OF INDEPENDENT TESTS implied by the null
    -- the quantity Patch 2's Round 3 addition asks for, so the N-gate's
    multiplicity target can be derived from this run rather than assumed. It is
    backed out by asking what number of independent tests would produce the
    observed max-T critical value under a standard-normal per-test null:

        alpha_per_test = 1 - (1 - alpha)^(1/k)  =>  k = ln(1-alpha)/ln(1-a1)

    with a1 the two-sided normal tail beyond the empirical 95th percentile of
    the max-|t| distribution. k = 1 means the horizons carry no more
    information than a single test; k = 20 would mean they are effectively
    independent.
    """
    rng = np.random.default_rng(seed)

    event_ids = table["event_id"]
    unique_events = np.unique(event_ids)
    # One shock per event -- take the first occurrence, they are constant
    # within an event by construction.
    event_shock = np.array([table["shock"][event_ids == e][0] for e in unique_events])
    index_of = {int(e): i for i, e in enumerate(unique_events)}
    row_event_index = np.array([index_of[int(e)] for e in event_ids])

    # Each event's cluster, verified constant within the event rather than
    # assumed. A shock is a property of the anchor event, so its cluster is
    # too; if that is ever false the exchangeability argument below does not
    # hold and a silent first-value pick would hide it.
    cl = table[cluster_key]
    event_cluster = np.empty(unique_events.size, dtype=cl.dtype)
    for i, e in enumerate(unique_events):
        vals = np.unique(cl[event_ids == e])
        if vals.size != 1:
            raise ValueError(
                f"{cluster_key} is not constant within event {e!r}: {vals!r}. "
                "Restricted permutation requires one cluster per event.")
        event_cluster[i] = vals[0]

    groups = [np.flatnonzero(event_cluster == c) for c in np.unique(event_cluster)]
    movable = int(sum(g.size for g in groups if g.size >= 2))

    # The permutation must preserve exactly the dependence the SE assumes, and
    # which permutation does that depends on the cluster shape.
    #
    #   clusters holding MANY events -> permute WITHIN cluster. The clustering
    #     asserts dependence inside a cluster, so that structure must survive
    #     under the null; permuting across clusters would strip it out of the
    #     null while leaving it in the observed statistic.
    #
    #   clusters that are all SINGLETONS -> cluster is the event, there is no
    #     within-cluster structure to preserve, and the clustering asserts
    #     independence ACROSS clusters. Free permutation is then not a fallback
    #     but the correct null for that choice. This is what cluster_key=
    #     "event_id" produces, and it is the pre-D1 behaviour, kept valid for
    #     the sensitivity fit rather than refused.
    #
    # The mode is reported, never inferred silently by the reader.
    restricted = movable > 0
    mode = (f"restricted within {cluster_key}" if restricted
            else f"unrestricted across {cluster_key} (every cluster is a "
                 f"single event, so there is no within-cluster structure)")

    null_max = np.empty(n_permutations)
    for b in range(n_permutations):
        if restricted:
            permuted = event_shock.copy()
            for ix in groups:
                if ix.size >= 2:
                    permuted[ix] = rng.permutation(event_shock[ix])
        else:
            permuted = rng.permutation(event_shock)
        null_max[b] = _max_abs_t_for_shuffle(
            table, horizons, controls, permuted[row_event_index], cluster_key)

    crit = float(np.percentile(null_max, 95))

    from scipy import stats  # local import: only needed for the tail conversion
    a1 = float(2.0 * stats.norm.sf(crit))
    if 0.0 < a1 < 1.0:
        k_eff = float(np.log(1 - 0.05) / np.log(1 - a1))
    else:
        k_eff = float("nan")

    out: dict[str, Any] = {
        "n_permutations": n_permutations,
        "null_max_abs_t_p95": crit,
        "null_max_abs_t_mean": float(np.mean(null_max)),
        "effective_independent_tests": k_eff,
        "n_horizons_tested": len(horizons),
        "permutation_unit": f"anchor event, {mode} (shock re-broadcast to "
                            "that event's peers)",
        "permutation_restricted": restricted,
        "cluster_key": cluster_key,
        "n_permutation_groups": len(groups),
        "events_movable": movable,
        "events_total": int(unique_events.size),
    }
    if observed_max_abs_t is not None:
        out["max_t_p_value"] = float(
            (np.sum(null_max >= observed_max_abs_t) + 1) / (n_permutations + 1))
        out["peak_significant"] = bool(observed_max_abs_t > crit)
    return out


def local_projection_analysis(
    table: dict[str, np.ndarray],
    *,
    horizons: tuple[int, ...] = HORIZON_GRID,
    controls: bool = True,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = RANDOM_SEED,
    run_permutation: bool = True,
    cluster_key: str = LOCKED_CLUSTER_KEY,
) -> LocalProjectionResult:
    """Fit the LP profile, then judge its peak against a max-T permutation null.

    cluster_key defaults to the D1-locked dimension. It is forwarded to BOTH
    the fit and the permutation null: this function previously accepted no
    cluster_key at all, so the null was always clustered on event_id however
    the fit was configured.
    """
    fits = fit_local_projections(
        table, horizons=horizons, controls=controls, cluster_key=cluster_key)
    result = LocalProjectionResult(
        fits=fits, peak_horizon=None, peak_abs_t=0.0,
        clustering=f"one-way ({cluster_key})"
                   + (" -- D1" if cluster_key == LOCKED_CLUSTER_KEY
                      else " -- SENSITIVITY, NOT THE D1 PRIMARY"))
    if not fits:
        return result

    abs_t = np.array([abs(f.t_stat) for f in fits])

    # THE TEST STATISTIC and THE REPORTED LOCATION are different quantities and
    # are kept in different fields. Conflating them is what this split fixes.
    #
    # max_abs_t is max_h |t_h|, which is what the permutation null is a
    # distribution OF. It alone may be compared to that null's critical value.
    result.max_abs_t = float(np.max(abs_t))

    # peak_horizon is argmax_h |beta_h| -- where the response actually peaks.
    # Plan v0.2 section 3.5 defines it this way ("argmax_h beta_h lands at
    # h = L+W-1, the end of the reaction window"); the argmax|t| this replaces
    # was the code's divergence FROM the plan, not a separate choice. Under the
    # D1-locked calendar_period clustering argmax|t| recovered an injected peak
    # 9/15 while argmax|beta| recovered 15/15, because clustering changes the
    # variance estimate and must never move a location estimate.
    k = int(np.argmax(np.abs(np.array([f.beta for f in fits]))))
    result.peak_horizon = fits[k].horizon
    result.peak_abs_t = float(abs_t[k])          # |t| AT the peak, not the max

    if run_permutation:
        perm = max_t_permutation(
            table, horizons=horizons, controls=controls,
            n_permutations=n_permutations, seed=seed,
            observed_max_abs_t=result.max_abs_t, cluster_key=cluster_key)
        result.max_t_critical_value = perm["null_max_abs_t_p95"]
        result.max_t_p_value = perm["max_t_p_value"]
        result.peak_significant = perm["peak_significant"]
        result.n_permutations = perm["n_permutations"]
        result.effective_independent_tests = perm["effective_independent_tests"]

        # ONSET: the earliest horizon clearing the SAME max-T critical value.
        # Judged against the multiplicity-corrected threshold, not a per-horizon
        # one, so the onset inherits the same false-positive control as the peak
        # rather than being read off an uncorrected t.
        if result.peak_significant:
            crit = result.max_t_critical_value
            for f, t in zip(fits, abs_t):
                if t > crit:
                    result.onset_horizon = f.horizon
                    result.onset_abs_t = float(t)
                    break
    return result


# ==========================================================================
# Prewhitened CCF -- SECONDARY cross-check only
# ==========================================================================
def fit_ar(series: np.ndarray, order: int = 5) -> np.ndarray:
    """Least-squares AR(order) coefficients. No intercept (series is demeaned)."""
    x = series - float(np.mean(series))
    n = x.size
    if n <= order + 1:
        return np.zeros(order)
    X = np.column_stack([x[order - i - 1:n - i - 1] for i in range(order)])
    y = x[order:]
    beta, _, _ = ols(X, y)
    return np.asarray(beta, dtype=float)


def apply_ar_filter(series: np.ndarray, phi: np.ndarray) -> np.ndarray:
    """Whiten by e_t = x_t - sum(phi_i * x_{t-i}). Same filter, both series."""
    x = series - float(np.mean(series))
    p = phi.size
    if x.size <= p:
        return x
    out = np.empty(x.size - p)
    for t in range(p, x.size):
        # lags in order x[t-1], x[t-2], ..., x[t-p]. Written as a forward
        # slice then reversed: the compact reverse-slice form
        # x[t-1 : t-p-1 : -1] silently yields an EMPTY array when t == p,
        # because the stop index -1 wraps to the end of the array.
        lags = x[t - p:t][::-1]
        out[t - p] = x[t] - float(np.dot(phi, lags))
    return out


def prewhitened_ccf(
    peer_vol_series: np.ndarray,
    anchor_shock_series: np.ndarray,
    *,
    max_lag: int = 20,
    ar_order: int = 5,
    n_permutations: int = 500,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Cross-correlate after whitening BOTH series with ONE filter.

    The filter is fit to the PEER VOLATILITY series, never to the anchor shock
    series. The anchor shock series is a sparse, roughly-quarterly point
    process already close to white noise: an AR fit to it returns near-zero
    coefficients, so filtering both series with it is close to a no-op and the
    peer's own vol-clustering persistence -- the actual source of spurious
    cross-correlation -- passes through untouched.

    One filter applied to both, never two. Box-Jenkins prewhitening preserves
    proportionality to the true impulse-response weights precisely BECAUSE the
    same filter hits both series; different filters break that proportionality
    and bias the estimated lag, even though a significance test would remain
    technically valid. Lag identification is this cross-check's entire purpose.

    Significance is a CIRCULAR-SHIFT permutation of the anchor event series,
    not Bartlett bands. Bartlett assumes the white-noise-input case, which is
    exactly the assumption under question; a circular shift preserves the peer
    series' own autocorrelation under the null.
    """
    phi = fit_ar(peer_vol_series, order=ar_order)
    wy = apply_ar_filter(peer_vol_series, phi)
    wx = apply_ar_filter(anchor_shock_series, phi)   # SAME phi -- deliberate
    n = min(wy.size, wx.size)
    wy, wx = wy[:n], wx[:n]

    def ccf_at(lag: int, x: np.ndarray) -> float:
        if lag >= n:
            return 0.0
        a, b = x[:n - lag], wy[lag:]
        if a.size < 3:
            return 0.0
        sa, sb = float(np.std(a)), float(np.std(b))
        if sa <= 0 or sb <= 0:
            return 0.0
        return float(np.mean((a - np.mean(a)) * (b - np.mean(b))) / (sa * sb))

    lags = list(range(max_lag + 1))
    observed = np.array([ccf_at(l, wx) for l in lags])
    peak_idx = int(np.argmax(np.abs(observed)))

    rng = np.random.default_rng(seed)
    null_max = np.empty(n_permutations)
    for b in range(n_permutations):
        shift = int(rng.integers(1, n)) if n > 1 else 0
        shifted = np.roll(wx, shift)
        null_max[b] = float(np.max([abs(ccf_at(l, shifted)) for l in lags]))

    crit = float(np.percentile(null_max, 95))
    peak_abs = float(abs(observed[peak_idx]))
    return {
        "lags": lags,
        "ccf": observed.tolist(),
        "peak_lag": int(lags[peak_idx]),
        "peak_ccf": float(observed[peak_idx]),
        "peak_abs_ccf": peak_abs,
        "null_p95": crit,
        "p_value": float((np.sum(null_max >= peak_abs) + 1) / (n_permutations + 1)),
        "significant": bool(peak_abs > crit),
        "ar_order": ar_order,
        "filter_fit_to": "peer_volatility_series",
        "filter_applied_to": "both series (single filter)",
        "significance_method": "circular-shift permutation (NOT Bartlett bands)",
        "role": "SECONDARY cross-check. Never the decision-maker.",
    }


# ==========================================================================
# Link-Strength model: ridge, leave-one-anchor-out CV, placebo
#
# PROVENANCE. Everything below is classical by construction -- a closed-form
# ridge solve and a leave-one-anchor-out split, both in numpy. Nothing quantum
# is computed here and no quantum library is imported anywhere in this package
# (checked structurally, not assumed, by
# test_hyp04_supply_chain_hedge_quantum_provenance.py).
#
# `feature_provenance` exists so that stays true if a non-classical feature is
# ever proposed: it declares what produced the columns being fitted, and
# quantum_provenance refuses the fit outright rather than letting an
# unvalidated input contribute a coefficient. The plan scopes the quantum
# autocorrelation function as tertiary and non-load-bearing -- "it should not
# be permitted to affect any lock, gate, or hedge decision until it's been
# validated against the classical result on known cases" -- and the
# Link-Strength score is precisely such a decision input.
# ==========================================================================
def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Closed-form ridge. Intercept (column 0) is NOT penalized.

    Implemented directly rather than via scikit-learn: ridge is a two-line
    closed form, and this repository does not otherwise depend on sklearn.
    Adding a heavy dependency for this would not match its conventions.
    """
    k = X.shape[1]
    P = np.eye(k)
    P[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + alpha * P, X.T @ y)


def leave_one_anchor_out_cv(
    table: dict[str, np.ndarray],
    *,
    horizon: int,
    alpha: float = 1.0,
    feature_provenance: Optional[Any] = None,
) -> dict[str, Any]:
    """Leave-one-ANCHOR-out CV, never random k-fold.

    Anchor events cluster in time and by sector, so random folds would leak
    information across correlated events and report an optimistic error.

    `feature_provenance` declares what produced the fitted columns -- one
    entry, or one per feature. A declared quantum-derived feature without a
    classical-validation attestation raises before the first solve, so it
    cannot contribute a coefficient to the Link-Strength score. Today's
    features are the intercept, the anchor shock and days-to-peer-earnings,
    all classical, so callers pass nothing.
    """
    assert_may_influence_link_strength(
        feature_provenance,
        context=f"the Link-Strength ridge fit at horizon {horizon}",
    )

    mask = table["horizon"] == horizon
    anchors = table["anchor"][mask]
    y = table["target"][mask]
    X = np.column_stack([
        np.ones(int(mask.sum())),
        table["shock"][mask],
        table["days_to_peer_earnings"][mask],
    ])

    held = np.unique(anchors)
    errs: list[float] = []
    for a in held:
        te = anchors == a
        tr = ~te
        if tr.sum() < X.shape[1] + 1 or te.sum() == 0:
            continue
        beta = ridge_fit(X[tr], y[tr], alpha)
        errs.append(float(np.mean((y[te] - X[te] @ beta) ** 2)))

    baseline = float(np.mean((y - np.mean(y)) ** 2))
    cv_mse = float(np.mean(errs)) if errs else float("nan")
    return {
        "horizon": horizon,
        "n_folds": len(errs),
        "n_anchors_held_out": int(held.size),
        "cv_mse": cv_mse,
        "baseline_mse_intercept_only": baseline,
        "skill_vs_baseline": float(1.0 - cv_mse / baseline) if baseline > 0 else float("nan"),
        "alpha": alpha,
        "split": "leave-one-anchor-out (NOT random k-fold)",
    }


def placebo_test(
    table: dict[str, np.ndarray],
    *,
    horizon: int,
    n_permutations: int = 1000,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Shuffle anchor-peer assignment; real linkage should beat random pairing.

    Follows GST_Task1_PlaceboPermutationTest.py's pattern: recompute the same
    statistic under randomized assignment and report where the real value falls
    in that distribution. If real linkage is indistinguishable from random
    pairing, the model has nothing to learn regardless of algorithm.

    Peers are reassigned ACROSS anchor events, which is exactly the linkage
    claim under test -- the placeholder linkage asserts these peers belong to
    this anchor.

    Note what that claim actually is under Phase 0: the placeholder assigns
    peers to anchors by LIST POSITION, not by sector or by any real
    relationship. So the placebo here tests whether the estimator can tell a
    stated pairing from a shuffled one; it says nothing about whether the
    stated pairing is meaningful, because under the placeholder it is not.
    """
    mask = table["horizon"] == horizon
    y = table["target"][mask]
    shock = table["shock"][mask]
    events = table["event_id"][mask]

    def stat(sh: np.ndarray) -> float:
        s_sh, s_y = float(np.std(sh)), float(np.std(y))
        if s_sh <= 0 or s_y <= 0:
            return 0.0
        return float(abs(np.mean((sh - np.mean(sh)) * (y - np.mean(y))) / (s_sh * s_y)))

    observed = stat(shock)

    rng = np.random.default_rng(seed)
    unique_events = np.unique(events)
    ev_shock = np.array([shock[events == e][0] for e in unique_events])
    idx = {int(e): i for i, e in enumerate(unique_events)}
    row_idx = np.array([idx[int(e)] for e in events])

    null = np.empty(n_permutations)
    for b in range(n_permutations):
        null[b] = stat(rng.permutation(ev_shock)[row_idx])

    p = float((np.sum(null >= observed) + 1) / (n_permutations + 1))
    return {
        "horizon": horizon,
        "observed_abs_corr": observed,
        "placebo_mean_abs_corr": float(np.mean(null)),
        "placebo_p95": float(np.percentile(null, 95)),
        "p_value": p,
        "separates_from_random": bool(p < 0.05),
        "n_permutations": n_permutations,
    }
