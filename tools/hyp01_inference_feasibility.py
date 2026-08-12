#!/usr/bin/env python3
"""HYP-01 inference-feasibility reproduction runner.

NOT PRODUCTION CODE. NOT AN ANALYSIS ENTRY POINT. SYNTHETIC DATA ONLY.

This module contains the actual computation behind
`Live Signal Engine/GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json`:
fixture generation, the study-written CR1 / CR2 / CR3 / Satterthwaite /
restricted wild-cluster-bootstrap implementations, the independent statsmodels
reference call for CR1, the refusal rules, and the Monte Carlo grid.

It exists so the published numbers can be regenerated and checked. It:

  * reads NO registry, panel, screening, observation, event or market artifact;
  * makes network access impossible;
  * writes ONLY to a caller-supplied output path;
  * never touches a lock, signoff or canonical research artifact;
  * labels CR2, CR3 and the bootstrap UNVALIDATED_STUDY_IMPLEMENTATION;
  * exposes no production-analysis entry point.

Reproduce with:

    python tools/hyp01_inference_feasibility.py --reproduce --out <path.json>

A fast smoke run (reduced replications, NOT publication precision):

    python tools/hyp01_inference_feasibility.py --reproduce --quick --out <path.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Network is made impossible before any numerical library is imported.
# --------------------------------------------------------------------------
class NetworkBlocked(RuntimeError):
    pass


def _deny_network(*_a, **_k):
    raise NetworkBlocked("network access attempted in an offline feasibility runner")


socket.socket.connect = _deny_network
socket.socket.connect_ex = _deny_network
socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network

import numpy as np                       # noqa: E402
import pandas                            # noqa: E402
import scipy                             # noqa: E402
import statsmodels                       # noqa: E402
import statsmodels.api as sm             # noqa: E402
from scipy import stats                  # noqa: E402

# --------------------------------------------------------------------------
# Canonical-artifact guard. The runner must never read research data.
# --------------------------------------------------------------------------
FORBIDDEN_PATH_TOKENS = (
    "registry.jsonl", "Cohort_Screening", "GST_Phase2_DailyPanel",
    "ANALYSIS_LOCK", "HYPOTHESIS_REGISTRY", "COHORT_PROTOCOL",
    "Event_Dossier", "SEARCH_CONSTRUCT", "Market_Response_Event",
    "SIGNOFF", "panel", "screening", "observation",
)


def assert_not_canonical(path: str | Path) -> None:
    s = str(path).replace("\\", "/")
    for tok in FORBIDDEN_PATH_TOKENS:
        if tok.lower() in s.lower():
            raise PermissionError(
                f"refusing to touch a canonical research artifact: {s} (matched {tok!r})")


# ==========================================================================
# PREREGISTERED CONSTANTS -- fixed before any comparison or simulation run.
# ==========================================================================
TOLERANCES = {
    "covariance_matrix": {"rtol": 1e-10, "atol": 1e-12},
    "standard_error":    {"rtol": 1e-10, "atol": 1e-12},
    "t_statistic":       {"rtol": 1e-9,  "atol": 1e-11},
    "p_value":           {"rtol": 1e-9,  "atol": 1e-12},
    "degrees_of_freedom": {"exact_integer_equality": True},
}

# Numerical refusal thresholds. Declared BEFORE the corrected rerun, so a
# fixture fails by rule rather than because two outputs happened to differ.
REFUSAL = {
    "nonfinite_any": "any non-finite value in the design matrix or outcome",
    "rank_condition_number_max": 1e10,     # cond(X'X) above this -> refuse
    "zero_variance_column_std_min": 1e-12,  # non-intercept column std below -> refuse
    "degenerate_fit_relative_rss_min": 1e-18,  # rss / (n * var(y)) below -> refuse
    "min_clusters_for_any_output": 2,      # arithmetic floor only, NOT an eligibility rule
}

MASTER_SEED = 20260811
BOOTSTRAP = {"B_default": 999, "seed_default": 424242,
             "weights_implemented": ["rademacher", "webb6"],
             "null_imposition": "restricted (null imposed before resampling)"}

ALPHA = 0.05
INTERVAL_METHOD = "Wilson score interval, 95%"

# Monte Carlo simulation plan. Cell list and replication counts fixed here.
SIM_PLAN = {
    "master_seed": MASTER_SEED,
    "nominal_alpha": ALPHA,
    "interval_method": INTERVAL_METHOD,
    "replications_null_cell": 5000,
    "replications_effect_cell": 2000,
    "replications_quick_mode": 200,
    "claim_rule": (
        "'Evidence of over-rejection' only when the entire 95% Wilson interval lies above "
        "the nominal alpha. 'Evidence of under-rejection' only when the entire interval lies "
        "below it. Otherwise 'not distinguishable from nominal at this simulation precision'. "
        "Applied separately to each cell. Blanket words such as 'everywhere', 'all cells' or "
        "'dominant risk factor' are only permitted if every relevant cell's interval supports them."),
    "cells": [
        {"clusters": 24, "shape": "balanced",   "effects": [0.0, 0.2, 0.5]},
        {"clusters": 24, "shape": "unbalanced", "effects": [0.0, 0.2, 0.5]},
        {"clusters": 12, "shape": "balanced",   "effects": [0.0, 0.5]},
        {"clusters": 6,  "shape": "balanced",   "effects": [0.0, 0.5]},
    ],
    "n_obs_per_cell": 60,
    "unvalidated_columns": ["CR2_tG1", "CR2_Satterthwaite"],
    "unvalidated_column_label": "UNVALIDATED ENGINEERING OUTPUT -- NOT METHOD-COMPARISON EVIDENCE",
}

VALIDATED = "IMPLEMENTATION_VALIDATED"
BLOCKED = "IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE"
UNVALIDATED_TAG = "UNVALIDATED_STUDY_IMPLEMENTATION"


# ==========================================================================
# Estimators. CR1 is checked against statsmodels; CR2/CR3/bootstrap are NOT.
# ==========================================================================
def ols(X, y):
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    return beta, XtX_inv, y - X @ beta


def cr_vcov(X, y, g, kind):
    """kind in {CR0, CR1, CR2, CR3}. CR2/CR3 are UNVALIDATED_STUDY_IMPLEMENTATION."""
    n, k = X.shape
    beta, XtX_inv, u = ols(X, y)
    G = len(np.unique(g))
    meat = np.zeros((k, k))
    for c in np.unique(g):
        m = g == c
        Xg, ug = X[m], u[m]
        if kind in ("CR2", "CR3"):
            H = Xg @ XtX_inv @ Xg.T
            I = np.eye(H.shape[0])
            w, V = np.linalg.eigh(I - H)
            w = np.clip(w, 1e-12, None)
            power = -0.5 if kind == "CR2" else -1.0
            A = V @ np.diag(w ** power) @ V.T
            ug = A @ ug
        s = Xg.T @ ug
        meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv
    if kind == "CR1":
        V = V * (G / (G - 1)) * ((n - 1) / (n - k))
    return beta, V, G


def satterthwaite_df(X, g, c):
    """Bell-McCaffrey / Imbens-Kolesar df under the working model Omega = I.
    UNVALIDATED_STUDY_IMPLEMENTATION."""
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    ImH = np.eye(n) - X @ XtX_inv @ X.T
    cols = []
    for cl in np.unique(g):
        m = g == cl
        Xg = X[m]
        H = Xg @ XtX_inv @ Xg.T
        I = np.eye(H.shape[0])
        w, V = np.linalg.eigh(I - H)
        w = np.clip(w, 1e-12, None)
        A = V @ np.diag(w ** -0.5) @ V.T
        cols.append(ImH[:, m] @ A @ Xg @ XtX_inv @ c)
    Gm = np.column_stack(cols)
    lam = np.linalg.eigvalsh(Gm.T @ Gm)
    lam = lam[lam > 1e-12]
    return float((lam.sum() ** 2) / (lam ** 2).sum())


def wcr_bootstrap_t(X, y, g, j, B=None, seed=None, weights="rademacher"):
    """Restricted wild cluster bootstrap-t. UNVALIDATED_STUDY_IMPLEMENTATION."""
    B = BOOTSTRAP["B_default"] if B is None else B
    seed = BOOTSTRAP["seed_default"] if seed is None else seed
    rng = np.random.default_rng(seed)
    beta, V, _ = cr_vcov(X, y, g, "CR1")
    t_obs = float(beta[j] / np.sqrt(V[j, j]))
    keep = [i for i in range(X.shape[1]) if i != j]
    Xr = X[:, keep]
    br, _, ur = ols(Xr, y)                       # null imposed
    yhat_r = Xr @ br
    gs = np.unique(g)
    ts = np.empty(B)
    for b in range(B):
        if weights == "rademacher":
            w = rng.choice([-1.0, 1.0], size=len(gs))
        elif weights == "webb6":
            w = rng.choice([-math.sqrt(1.5), -1.0, -math.sqrt(0.5),
                            math.sqrt(0.5), 1.0, math.sqrt(1.5)], size=len(gs))
        else:
            raise ValueError(f"unknown weight distribution: {weights}")
        wmap = {c: w[i] for i, c in enumerate(gs)}
        yb = yhat_r + ur * np.array([wmap[c] for c in g])
        bb, Vb, _ = cr_vcov(X, yb, g, "CR1")
        ts[b] = bb[j] / np.sqrt(Vb[j, j])
    p = float((np.sum(np.abs(ts) >= abs(t_obs)) + 1) / (B + 1))
    # Digest of the bootstrap t-vector. The p-value alone is a coarse grid at
    # small B, so two different seeds can collide on p while having drawn
    # entirely different samples; the digest tests the draws themselves.
    digest = hashlib.sha256(np.round(ts, 12).tobytes()).hexdigest()
    return {"t_observed": t_obs, "p_value": p, "B": B, "seed": seed,
            "weights": weights, "bootstrap_t_digest": digest, "label": UNVALIDATED_TAG}


# ==========================================================================
# Refusal rules -- evaluated BEFORE any model is fitted.
# ==========================================================================
def refusal_check(X, y, g):
    """Returns (refuse: bool, reason: str|None). Rules are preregistered above."""
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(X)):
        return True, "NONFINITE_VALUE_PRESENT"
    if len(np.unique(g)) < REFUSAL["min_clusters_for_any_output"]:
        return True, "FEWER_THAN_TWO_CLUSTERS"
    for j in range(1, X.shape[1]):
        if float(np.std(X[:, j])) < REFUSAL["zero_variance_column_std_min"]:
            return True, "ZERO_VARIANCE_PREDICTOR"
    XtX = X.T @ X
    if np.linalg.matrix_rank(X) < X.shape[1]:
        return True, "RANK_DEFICIENT_DESIGN"
    cond = float(np.linalg.cond(XtX))
    if not np.isfinite(cond) or cond > REFUSAL["rank_condition_number_max"]:
        return True, "ILL_CONDITIONED_DESIGN"
    _, _, u = ols(X, y)
    rss = float(u @ u)
    denom = max(float(np.var(y)) * len(y), 1e-300)
    if rss / denom < REFUSAL["degenerate_fit_relative_rss_min"]:
        return True, "DEGENERATE_FIT_RESIDUAL_VARIANCE_AT_NOISE_FLOOR"
    return False, None


# ==========================================================================
# Synthetic fixtures. Cluster labels are CLUSTER_### -- never a real ticker.
# ==========================================================================
def stable_name_offset(name: str, modulus: int = 100_000) -> int:
    """Process-stable replacement for abs(hash(name)) % modulus.

    Python randomises str hashing per process unless PYTHONHASHSEED is set,
    so hash() must never seed a reproducible fixture."""
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big") % modulus


def make_fixture(name, n_clusters, n_obs, shape="balanced", effect=0.0, err="normal",
                 near_collinear=False, exact_rank_deficient=False, zero_var=False,
                 perfect=False, missing=False, seed=MASTER_SEED):
    # NOTE: Python's built-in hash() for str is randomised per process unless
    # PYTHONHASHSEED is fixed, which silently destroys cross-process
    # reproducibility. A stable digest is used instead, so the same fixture
    # name always yields the same synthetic data.
    rng = np.random.default_rng(seed + stable_name_offset(name))
    if shape == "balanced":
        sizes = np.full(n_clusters, n_obs // n_clusters)
        sizes[: n_obs - int(sizes.sum())] += 1
    elif shape == "unbalanced":
        w = rng.pareto(1.1, n_clusters) + 1.0
        sizes = np.maximum(1, np.round(w / w.sum() * n_obs).astype(int))
    elif shape == "singletons":
        sizes = np.ones(n_clusters, dtype=int)
        big = max(1, n_clusters // 4)
        sizes[:big] = max(2, (n_obs - n_clusters) // big)
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
    labels = np.array([f"CLUSTER_{i + 1:03d}" for i in gi])
    x = rng.normal(size=gi.size) + rng.normal(size=n_clusters)[gi]
    if zero_var:
        x = np.zeros_like(x)
    cols = [np.ones(gi.size), x]
    if near_collinear:
        cols.append(x + rng.normal(scale=1e-7, size=gi.size))   # high cond, full rank
    if exact_rank_deficient:
        cols.append(x.copy())                                    # exact duplicate column
    X = np.column_stack(cols)

    if err == "heavy":
        e = rng.standard_t(3, size=gi.size)
    elif err == "cluster_hetero":
        e = rng.normal(scale=rng.uniform(0.2, 3.0, size=n_clusters)[gi])
    else:
        e = rng.normal(size=gi.size)
    e = e + rng.normal(size=n_clusters)[gi]
    y = effect * x + e
    if perfect:
        y = 2.0 * x
    if missing:
        y = y.astype(float).copy()
        y[0] = np.nan
    return {"name": name, "labels": labels, "cluster_index": gi, "X": X, "y": y,
            "n_clusters": int(n_clusters), "n_obs": int(gi.size),
            "cluster_sizes": [int(s) for s in sizes]}


FIXTURE_SPECS = [
    ("F01_balanced_24c_72n",            dict(n_clusters=24, n_obs=72, shape="balanced")),
    ("F02_unbalanced_24c_60n",          dict(n_clusters=24, n_obs=60, shape="unbalanced")),
    ("F03_several_singleton_clusters",  dict(n_clusters=20, n_obs=32, shape="singletons")),
    ("F04_one_dominant_cluster",        dict(n_clusters=12, n_obs=60, shape="dominant")),
    ("F05_near_collinear_full_rank",    dict(n_clusters=24, n_obs=72, near_collinear=True)),
    ("F06_exactly_rank_deficient",      dict(n_clusters=24, n_obs=72, exact_rank_deficient=True)),
    ("F07_zero_variance_predictor",     dict(n_clusters=24, n_obs=72, zero_var=True)),
    ("F08_perfect_fit",                 dict(n_clusters=24, n_obs=72, perfect=True)),
    ("F09_missing_value",               dict(n_clusters=24, n_obs=72, missing=True)),
    ("F10_row_permutation_source",      dict(n_clusters=24, n_obs=72)),
    ("F11_cluster_relabel_source",      dict(n_clusters=24, n_obs=72)),
    ("F12_sign_reversed_effect",        dict(n_clusters=24, n_obs=72, effect=-0.4)),
    ("F13_null_effect",                 dict(n_clusters=24, n_obs=72, effect=0.0)),
    ("F14_positive_hypothetical_effect", dict(n_clusters=24, n_obs=72, effect=0.4)),
    ("F15_heavy_tailed_errors",         dict(n_clusters=24, n_obs=72, err="heavy")),
    ("F16_cluster_heteroskedastic",     dict(n_clusters=24, n_obs=72, err="cluster_hetero")),
    ("F17_bootstrap_seed_repeat",       dict(n_clusters=24, n_obs=60, shape="unbalanced")),
    ("F18_below_design_6_clusters",     dict(n_clusters=6, n_obs=30, shape="balanced")),
]


# ==========================================================================
# CR1 independent-reference comparison (statsmodels)
# ==========================================================================
def compare_cr1_to_statsmodels(fx):
    X, y, g = fx["X"], fx["y"], fx["cluster_index"]
    refuse, reason = refusal_check(X, y, g)
    if refuse:
        return {"status": "REFUSED_BEFORE_FIT", "refusal_reason": reason,
                "comparison_performed": False}
    beta, V, G = cr_vcov(X, y, g, "CR1")
    res = sm.OLS(y, X).fit(cov_type="cluster",
                           cov_kwds={"groups": g, "use_correction": True, "df_correction": True},
                           use_t=True)
    se = np.sqrt(np.diag(V))
    t = beta / se
    df = G - 1
    # statsmodels keeps df_resid = n-k and exposes inference df separately.
    sm_df = int(getattr(res, "df_resid_inference", res.df_resid))
    p = 2 * stats.t.sf(np.abs(t), df)
    ok = {
        "covariance": bool(np.allclose(V, res.cov_params(), **TOLERANCES["covariance_matrix"])),
        "standard_error": bool(np.allclose(se, res.bse, **TOLERANCES["standard_error"])),
        "t_statistic": bool(np.allclose(t, res.tvalues, **TOLERANCES["t_statistic"])),
        "inference_df": sm_df == df,
        "p_value": bool(np.allclose(p, res.pvalues, **TOLERANCES["p_value"])),
    }
    return {
        "status": "COMPARED", "comparison_performed": True,
        "reference": f"statsmodels {statsmodels.__version__} "
                     f"OLS.fit(cov_type='cluster', use_correction=True, df_correction=True, use_t=True)",
        "matches": ok,
        "all_within_preregistered_tolerance": all(ok.values()),
        "max_abs_cov_diff": float(np.max(np.abs(V - res.cov_params()))),
        "max_abs_se_diff": float(np.max(np.abs(se - res.bse))),
        "study_inference_df": df, "statsmodels_inference_df": sm_df,
    }


def invariance(fx):
    X, y, g, lab = fx["X"], fx["y"], fx["cluster_index"], fx["labels"]
    refuse, reason = refusal_check(X, y, g)
    if refuse:
        return {"status": "REFUSED_BEFORE_FIT", "refusal_reason": reason}
    b0, V0, _ = cr_vcov(X, y, g, "CR1")
    rng = np.random.default_rng(7)
    perm = rng.permutation(len(y))
    b1, V1, _ = cr_vcov(X[perm], y[perm], g[perm], "CR1")
    remap = {c: f"RELABEL_{i:03d}" for i, c in enumerate(np.unique(lab))}
    _, inv_idx = np.unique(np.array([remap[c] for c in lab]), return_inverse=True)
    b2, V2, _ = cr_vcov(X, y, inv_idx, "CR1")
    return {"status": "RUN",
            "row_permutation_invariant": bool(np.allclose(b0, b1, rtol=1e-12, atol=1e-14)
                                              and np.allclose(V0, V1, rtol=1e-10, atol=1e-14)),
            "cluster_relabel_invariant": bool(np.allclose(b0, b2, rtol=1e-12, atol=1e-14)
                                              and np.allclose(V0, V2, rtol=1e-10, atol=1e-14))}


# ==========================================================================
# Monte Carlo grid with Wilson intervals
# ==========================================================================
def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def classify(k, n, alpha=ALPHA):
    lo, hi = wilson(k, n)
    if lo > alpha:
        return "evidence_of_over_rejection"
    if hi < alpha:
        return "evidence_of_under_rejection"
    return "not_distinguishable_from_nominal_at_this_precision"


def run_grid(quick=False):
    out = []
    for cell in SIM_PLAN["cells"]:
        G, shape = cell["clusters"], cell["shape"]
        for eff in cell["effects"]:
            if quick:
                R = SIM_PLAN["replications_quick_mode"]
            else:
                R = (SIM_PLAN["replications_null_cell"] if eff == 0.0
                     else SIM_PLAN["replications_effect_cell"])
            rng = np.random.default_rng(MASTER_SEED + G * 1000 + int(eff * 100) + len(shape))
            counts = {"CR1_tG1": 0, "CR2_tG1": 0, "CR2_Satterthwaite": 0}
            used = 0
            dfs = []
            c_vec = np.array([0.0, 1.0])
            for _ in range(R):
                fx = make_fixture(f"grid_{G}_{shape}_{eff}", G, SIM_PLAN["n_obs_per_cell"],
                                  shape, effect=eff, seed=int(rng.integers(1, 10 ** 9)))
                X, y, g = fx["X"], fx["y"], fx["cluster_index"]
                refuse, _ = refusal_check(X, y, g)
                if refuse:
                    continue
                used += 1
                b1, V1, Gn = cr_vcov(X, y, g, "CR1")
                if abs(b1[1] / math.sqrt(V1[1, 1])) > stats.t.ppf(1 - ALPHA / 2, Gn - 1):
                    counts["CR1_tG1"] += 1
                b2, V2, _ = cr_vcov(X, y, g, "CR2")
                t2 = abs(b2[1] / math.sqrt(V2[1, 1]))
                if t2 > stats.t.ppf(1 - ALPHA / 2, Gn - 1):
                    counts["CR2_tG1"] += 1
                nu = satterthwaite_df(X, g, c_vec)
                dfs.append(nu)
                if t2 > stats.t.ppf(1 - ALPHA / 2, max(nu, 1.0)):
                    counts["CR2_Satterthwaite"] += 1
            rec = {"clusters": G, "shape": shape, "hypothetical_effect": eff,
                   "replications_requested": R, "replications_used": used,
                   "mean_satterthwaite_df": round(float(np.mean(dfs)), 3) if dfs else None,
                   "p5_satterthwaite_df": round(float(np.percentile(dfs, 5)), 3) if dfs else None,
                   "methods": {}}
            for key, k in counts.items():
                lo, hi = wilson(k, used)
                rec["methods"][key] = {
                    "numerator": k, "denominator": used,
                    "rate": round(k / used, 5) if used else None,
                    "monte_carlo_standard_error": round(math.sqrt((k / used) * (1 - k / used) / used), 5) if used else None,
                    "wilson_95_low": round(lo, 5), "wilson_95_high": round(hi, 5),
                    "claim": classify(k, used) if eff == 0.0 else "power_estimate_not_a_size_claim",
                    "validation_label": (UNVALIDATED_TAG if key in SIM_PLAN["unvalidated_columns"]
                                         else "CR1_reference_validated_estimator"),
                }
            rec["column_warning"] = SIM_PLAN["unvalidated_column_label"]
            out.append(rec)
    return out


# ==========================================================================
def build(quick=False):
    t0 = time.time()
    fixtures, cr1, invar, refusals = {}, {}, {}, {}
    for name, kw in FIXTURE_SPECS:
        fx = make_fixture(name, **kw)
        refuse, reason = refusal_check(fx["X"], fx["y"], fx["cluster_index"])
        fixtures[name] = {"n_clusters": fx["n_clusters"], "n_obs": fx["n_obs"],
                          "cluster_sizes": fx["cluster_sizes"],
                          "n_columns": int(fx["X"].shape[1]),
                          "label_convention": "CLUSTER_###",
                          "refused_before_fit": bool(refuse),
                          "refusal_reason": reason}
        refusals[name] = {"refused": bool(refuse), "reason": reason}
        cr1[name] = compare_cr1_to_statsmodels(fx)
        invar[name] = invariance(fx)

    boot = {}
    fxb = make_fixture("F17_bootstrap_seed_repeat", n_clusters=24, n_obs=60, shape="unbalanced")
    a = wcr_bootstrap_t(fxb["X"], fxb["y"], fxb["cluster_index"], 1, B=199, seed=BOOTSTRAP["seed_default"])
    b = wcr_bootstrap_t(fxb["X"], fxb["y"], fxb["cluster_index"], 1, B=199, seed=BOOTSTRAP["seed_default"])
    c = wcr_bootstrap_t(fxb["X"], fxb["y"], fxb["cluster_index"], 1, B=199, seed=BOOTSTRAP["seed_default"] + 1)
    d = wcr_bootstrap_t(fxb["X"], fxb["y"], fxb["cluster_index"], 1, B=199,
                        seed=BOOTSTRAP["seed_default"], weights="webb6")
    boot["seed_determinism"] = {
        "same_seed_identical": (a["bootstrap_t_digest"] == b["bootstrap_t_digest"]
                                and a["p_value"] == b["p_value"]
                                and a["t_observed"] == b["t_observed"]),
        "different_seed_draws_differ": a["bootstrap_t_digest"] != c["bootstrap_t_digest"],
        "different_seed_p_value_differs": a["p_value"] != c["p_value"],
        "different_weights_draws_differ": a["bootstrap_t_digest"] != d["bootstrap_t_digest"],
        "note": ("p-values sit on a coarse 1/(B+1) grid, so two seeds may collide on p while "
                 "drawing different samples. The digest is the precise determinism test."),
        "rademacher_p": a["p_value"], "repeat_p": b["p_value"],
        "different_seed_p": c["p_value"], "webb6_p": d["p_value"],
        "digest_same_seed": a["bootstrap_t_digest"][:16],
        "digest_different_seed": c["bootstrap_t_digest"][:16],
        "label": UNVALIDATED_TAG,
    }

    grid = run_grid(quick=quick)
    matched = sorted(k for k, v in cr1.items() if v.get("all_within_preregistered_tolerance"))
    refused = sorted(k for k, v in cr1.items() if v["status"] == "REFUSED_BEFORE_FIT")

    runner = Path(__file__).resolve()
    runner_bytes = runner.read_bytes()
    doc = {
        "artifact": "GST HYP-01 Inference Implementation Inventory",
        "version": "1.0",
        "status": "OFFLINE_FEASIBILITY_STUDY_NO_METHOD_APPROVED",
        "generated_by": {
            "runner_path": "tools/hyp01_inference_feasibility.py",
            "runner_sha256": hashlib.sha256(runner_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            "exact_command": "python tools/hyp01_inference_feasibility.py --reproduce --out <path.json>"
                             + (" --quick" if quick else ""),
            "quick_mode": bool(quick),
            "deterministic_build_id": f"seed={MASTER_SEED};quick={int(quick)};"
                                      f"plan={hashlib.sha256(json.dumps(SIM_PLAN, sort_keys=True).encode()).hexdigest()[:16]}",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_seconds": round(time.time() - t0, 1),
        },
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__, "pandas": pandas.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "synthetic_data_only": True,
        "repository_research_artifact_loaded": False,
        "network_requests": 0,
        "packages_installed_or_mutated": 0,
        "method_approved": False,
        "dated_amendment_created": False,
        "operative_lock": "Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json (v1.0, unchanged)",
        "f5_status": "OPEN (unchanged by this study)",

        "preregistered_tolerances": TOLERANCES,
        "tolerances_fixed_before_any_comparison": True,
        "tolerances_revised_after_seeing_results": False,
        "preregistered_refusal_thresholds": REFUSAL,
        "refusal_thresholds_fixed_before_rerun": True,
        "simulation_plan": SIM_PLAN,
        "bootstrap_settings": BOOTSTRAP,

        "environment_validation_limits": {
            "statement": ("CR2 validation is unavailable in the currently tested environment; an "
                          "independently maintained reference runtime must be added and pinned before "
                          "validation. This is a statement about the tested workstation, not about the "
                          "repository's permanent capabilities."),
            "reference_runtime_present": False,
            "reference_runtimes_checked": ["R + clubSandwich", "R + fwildclusterboot",
                                           "Python wildboottest", "Python linearmodels"],
        },

        "methods": {
            "CR1": {"implementation_status": VALIDATED,
                    "reference": f"statsmodels {statsmodels.__version__}",
                    "independently_validated": True,
                    "fixtures_matched": matched,
                    "executable_here": True},
            "CR2": {"implementation_status": BLOCKED, "label": UNVALIDATED_TAG,
                    "independently_validated": False, "executable_here": False,
                    "dependency_needed": "R runtime + clubSandwich (or equivalent independently maintained CR2)",
                    "validation_procedure_needed": "run this fixture matrix through both implementations and "
                                                   "compare under the preregistered tolerances"},
            "CR3": {"implementation_status": BLOCKED, "label": UNVALIDATED_TAG,
                    "independently_validated": False, "executable_here": False,
                    "dependency_needed": "R runtime + clubSandwich",
                    "validation_procedure_needed": "as for CR2, comparing CR3 covariance and t"},
            "WCR_BOOTSTRAP_T": {"implementation_status": BLOCKED, "label": UNVALIDATED_TAG,
                                "independently_validated": False, "executable_here": False,
                                "dependency_needed": "R fwildclusterboot / Stata boottest / Python wildboottest",
                                "validation_procedure_needed": "compare bootstrap p-values at matched "
                                                               "seed/weights/B, allowing Monte Carlo error"},
        },

        "fixtures": fixtures,
        "refusal_outcomes": refusals,
        "cr1_reference_comparison": cr1,
        "invariance_checks": invar,
        "bootstrap_diagnostics": boot,
        "monte_carlo_grid": grid,
        "monte_carlo_grid_warning": SIM_PLAN["unvalidated_column_label"],

        "validation_summary": {
            "cr1_matched_within_tolerance": matched,
            "refused_before_fit": refused,
            "cr2_cr3_bootstrap_validated": False,
        },
        "decisions_not_made_by_this_study": [
            "C6 primary covariance estimator", "C7 finite-sample correction and df rule",
            "E3 multiplicity", "C9 sector encoding", "E8 development boundary",
            "A9 design-sensitivity policy", "NEW-1 minimum-cluster rule",
            "sparse-sector handling", "per-ticker cap", "implementation language and package",
            "wild bootstrap role, weights, repetitions and seed",
        ],
    }
    doc["output_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in doc.items() if k != "generated_by"},
                   sort_keys=True).encode()).hexdigest()
    return doc


def main(argv=None):
    global MASTER_SEED
    ap = argparse.ArgumentParser(description="HYP-01 inference feasibility reproduction runner "
                                             "(synthetic only, not production).")
    ap.add_argument("--reproduce", action="store_true", required=True,
                    help="regenerate the full inventory from computation")
    ap.add_argument("--out", required=True, help="output JSON path (caller-supplied)")
    ap.add_argument("--quick", action="store_true",
                    help="reduced replications; NOT publication precision")
    ap.add_argument("--seed", type=int, default=MASTER_SEED, help="deterministic master seed")
    a = ap.parse_args(argv)

    out = Path(a.out)
    assert_not_canonical(out)
    MASTER_SEED = a.seed
    doc = build(quick=a.quick)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  runtime {doc['generated_by']['runtime_seconds']}s | quick={a.quick}")
    print(f"  CR1 matched fixtures: {len(doc['validation_summary']['cr1_matched_within_tolerance'])}")
    print(f"  refused before fit  : {len(doc['validation_summary']['refused_before_fit'])}")
    print(f"  grid cells          : {len(doc['monte_carlo_grid'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
