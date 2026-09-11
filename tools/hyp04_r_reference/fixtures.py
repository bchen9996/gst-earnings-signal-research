#!/usr/bin/env python3
"""Synthetic fixtures for HYP-04's D10 R cross-check.

NOT PRODUCTION CODE. NOT AN ANALYSIS ENTRY POINT. SYNTHETIC DATA ONLY.

SCOPE, DELIBERATELY NARROW. This does not re-validate CR2/Satterthwaite
arithmetic from scratch. `hyp04_supply_chain_hedge/clustered_se.py`'s own
docstring states its `cr_vcov` and `satterthwaite_df` are mirrored verbatim
from `tools/hyp01_inference_feasibility.py` -- the exact functions the
HYP-01 R cross-check bridge already validated against R's `clubSandwich`
(13/13 fixtures, `MATCH_WITHIN_PREREGISTERED_TOLERANCE`, commit `97705ed`).
What is NOT yet validated is HYP-04's own *usage* of that arithmetic: its
own 3-column design matrix (intercept, shock magnitude, days-to-peer-
earnings -- see `_design_matrix` in `hyp04_supply_chain_hedge/inference.py`)
and its own clustering key (`calendar_period`, locked by D1 -- NOT HYP-01's
anchor-event clustering). Every fixture here therefore always carries
exactly those three columns; nothing here adds or removes a column the way
HYP-01's near-collinear/rank-deficient fixtures did.

TOLERANCES and REFUSAL below are copied VERBATIM (same numbers, unchanged)
from `tools/hyp01_inference_feasibility.py`. They are reused by explicit
citation, not re-derived: the CR2/Satterthwaite arithmetic under test is the
identical mirrored code, so there is no basis for a different numerical
tolerance, and inventing one would imply a difference that does not exist.
REFUSAL's thresholds are generic CR2 numerical-stability rules (condition
number, zero-variance columns, degenerate fit) -- not specific to HYP-01's
science, and not specific to HYP-04's either.

G03 and G09 below are new, not present in HYP-01's fixture set: they
exercise the thin/singleton-cluster regime the committed
`HYP04_INFERENCE_PHASE1_2026-09-10.json` diagnostic actually showed at
horizon 20 (8 `calendar_period` clusters, 7 of them singletons) -- the real
fragile edge of HYP-04's own usage, which a HYP-01-shaped fixture set would
never exercise because HYP-01 never had that clustering key.
"""
from __future__ import annotations

import hashlib

import numpy as np

# Dated the day this bridge was built, distinct from HYP-01's MASTER_SEED
# (20260811) -- a new, independently declared seed, not a reuse of HYP-01's.
MASTER_SEED = 20260910

# Copied verbatim from tools/hyp01_inference_feasibility.py::TOLERANCES.
# Reused by citation (see module docstring); nothing here is loosened,
# tightened, or re-derived.
TOLERANCES = {
    "covariance_matrix": {"rtol": 1e-10, "atol": 1e-12},
    "standard_error":    {"rtol": 1e-10, "atol": 1e-12},
    "t_statistic":       {"rtol": 1e-9,  "atol": 1e-11},
    "p_value":           {"rtol": 1e-9,  "atol": 1e-12},
    "degrees_of_freedom": {"exact_integer_equality": True},
}

# Copied verbatim from tools/hyp01_inference_feasibility.py::REFUSAL. Generic
# CR2 numerical-stability thresholds, declared before this comparison first
# ran. This is a BRIDGE-level preregistered gate, separate from and stricter
# than production `fit_local_projections`' own ad hoc floor (n_obs>=3,
# n_clusters>=2, finite positive variance) -- it exists so the bridge can
# decide, per fixture, whether Python should refuse before fitting at all.
REFUSAL = {
    "nonfinite_any": "any non-finite value in the design matrix or outcome",
    "rank_condition_number_max": 1e10,
    "zero_variance_column_std_min": 1e-12,
    "degenerate_fit_relative_rss_min": 1e-18,
    "min_clusters_for_any_output": 2,
}


def stable_name_offset(name: str, modulus: int = 100_000) -> int:
    """Process-stable replacement for abs(hash(name)) % modulus.

    Copied from tools/hyp01_inference_feasibility.py for the same reason:
    Python's built-in hash() for str is randomised per process unless
    PYTHONHASHSEED is fixed, which would silently destroy cross-process
    reproducibility of a "fixed-seed" fixture.
    """
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big") % modulus


def _ols(X: np.ndarray, y: np.ndarray):
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    return beta, XtX_inv, y - X @ beta


def refusal_check(X: np.ndarray, y: np.ndarray, g: np.ndarray):
    """Returns (refuse: bool, reason: str|None). Rules are preregistered above."""
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(X)):
        return True, "NONFINITE_VALUE_PRESENT"
    if len(np.unique(g)) < REFUSAL["min_clusters_for_any_output"]:
        return True, "FEWER_THAN_TWO_CLUSTERS"
    for j in range(1, X.shape[1]):
        if float(np.std(X[:, j])) < REFUSAL["zero_variance_column_std_min"]:
            return True, "ZERO_VARIANCE_PREDICTOR"
    if np.linalg.matrix_rank(X) < X.shape[1]:
        return True, "RANK_DEFICIENT_DESIGN"
    cond = float(np.linalg.cond(X.T @ X))
    if not np.isfinite(cond) or cond > REFUSAL["rank_condition_number_max"]:
        return True, "ILL_CONDITIONED_DESIGN"
    _, _, u = _ols(X, y)
    rss = float(u @ u)
    denom = max(float(np.var(y)) * len(y), 1e-300)
    if rss / denom < REFUSAL["degenerate_fit_relative_rss_min"]:
        return True, "DEGENERATE_FIT_RESIDUAL_VARIANCE_AT_NOISE_FLOOR"
    return False, None


def make_fixture(name, n_clusters, n_obs, shape="balanced", effect=0.0, err="normal",
                 near_collinear=False, exact_rank_deficient=False,
                 zero_var_control=False, perfect=False, missing=False,
                 seed=None):
    """Synthetic (X, y, cluster) matching HYP-04's real 3-column shape.

    Column 0: intercept. Column 1 ("shock_magnitude", the target coefficient,
    index 1 -- same convention `fit_local_projections` uses). Column 2
    ("days_to_peer_earnings", the control). Cluster labels are
    CALENDAR_PERIOD_### -- never a real quarter-year value, matching D1's
    `calendar_period` key in shape only.
    """
    seed = MASTER_SEED if seed is None else seed
    rng = np.random.default_rng(seed + stable_name_offset(name))

    if shape == "balanced":
        sizes = np.full(n_clusters, n_obs // n_clusters)
        sizes[: n_obs - int(sizes.sum())] += 1
    elif shape == "unbalanced":
        w = rng.pareto(1.1, n_clusters) + 1.0
        sizes = np.maximum(1, np.round(w / w.sum() * n_obs).astype(int))
    elif shape == "singletons":
        # The thin/singleton-heavy regime actually observed at horizon 20 in
        # the committed Phase 1 diagnostic: most clusters hold exactly one
        # pair, one cluster absorbs whatever remainder is needed to reach
        # n_obs. Not a generic HYP-01-style singleton fixture -- sized to
        # HYP-04's own real fragile edge.
        sizes = np.ones(n_clusters, dtype=int)
        remainder = n_obs - n_clusters
        if remainder > 0:
            sizes[0] += remainder
    elif shape == "dominant":
        sizes = np.ones(n_clusters, dtype=int)
        sizes[0] = n_obs - (n_clusters - 1)
    else:
        raise ValueError(shape)
    while sizes.sum() > n_obs and sizes.max() > 1:
        sizes[np.argmax(sizes)] -= 1
    while sizes.sum() < n_obs:
        sizes[np.argmin(sizes)] += 1

    gi = np.repeat(np.arange(n_clusters), sizes)
    labels = np.array([f"CALENDAR_PERIOD_{i + 1:03d}" for i in gi])

    shock = rng.normal(size=gi.size) + rng.normal(size=n_clusters)[gi]
    control = rng.normal(size=gi.size) + rng.normal(size=n_clusters)[gi]
    if zero_var_control:
        control = np.zeros_like(control)
    if near_collinear:
        control = shock + rng.normal(scale=1e-7, size=gi.size)
    if exact_rank_deficient:
        control = shock.copy()
    X = np.column_stack([np.ones(gi.size), shock, control])

    if err == "heavy":
        e = rng.standard_t(3, size=gi.size)
    else:
        e = rng.normal(size=gi.size)
    e = e + rng.normal(size=n_clusters)[gi]
    y = effect * shock + e
    if perfect:
        y = 2.0 * shock
    if missing:
        y = y.astype(float).copy()
        y[0] = np.nan

    return {"name": name, "labels": labels, "cluster_index": gi, "X": X, "y": y,
            "n_clusters": int(n_clusters), "n_obs": int(gi.size),
            "cluster_sizes": [int(s) for s in sizes]}


# HYP-04-specific fixture set. G01/G02 are generic balanced/unbalanced
# controls; G03 is the real thin/singleton regime (see module docstring);
# G04-G07 are numerical edge cases on the CONTROL column (near-collinear,
# exactly rank-deficient, zero-variance, missing outcome); G08 exercises the
# "fewer than two clusters" refusal directly (the same failure mode
# `test_hyp04_supply_chain_hedge_phase1_diagnostics.py::test_5` exercises in
# production); G09 is one dominant cluster; G10-G13 vary the effect sign/
# magnitude and error tails, matching HYP-01's F12-F15 in spirit.
FIXTURE_SPECS = [
    ("G01_balanced_70c_300n",          dict(n_clusters=70, n_obs=300, shape="balanced")),
    ("G02_unbalanced_40c_150n",        dict(n_clusters=40, n_obs=150, shape="unbalanced")),
    ("G03_thin_singleton_8c_9n",       dict(n_clusters=8,  n_obs=9,   shape="singletons")),
    ("G04_near_collinear_full_rank",   dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             near_collinear=True)),
    ("G05_exactly_rank_deficient",     dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             exact_rank_deficient=True)),
    ("G06_zero_variance_control",      dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             zero_var_control=True)),
    ("G07_missing_value",              dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             missing=True)),
    ("G08_below_min_two_clusters",     dict(n_clusters=1,  n_obs=12,  shape="balanced")),
    ("G09_one_dominant_cluster",       dict(n_clusters=20, n_obs=100, shape="dominant")),
    ("G10_perfect_fit",                dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             perfect=True)),
    ("G11_sign_reversed_effect",       dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             effect=-0.4)),
    ("G12_null_effect",                dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             effect=0.0)),
    ("G13_positive_effect",            dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             effect=0.4)),
    ("G14_heavy_tailed_errors",        dict(n_clusters=40, n_obs=150, shape="unbalanced",
                                             err="heavy")),
]
