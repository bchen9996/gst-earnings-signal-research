#!/usr/bin/env python3
"""Cluster-robust covariance and Satterthwaite dof for HYP-04's local projections.

Also reused by HYP-05 (same package) for `dual_cluster_report` below -- see
that function's docstring for HYP-05's own re-decision on two-way clustering.

PROVENANCE -- THIS IS A COPY, NOT AN IMPORT.

`cr_vcov` and `satterthwaite_df` below are mirrored from
`tools/hyp01_inference_feasibility.py` (functions `cr_vcov`, `satterthwaite_df`),
the same CR2 implementation that was independently validated against R's
`clubSandwich` package by the HYP-01 R cross-check bridge under `tools/`, and
reported in
`Live Signal Engine/GST_HYP01_R_REFERENCE_VALIDATION_REPORT_v1.0_DRAFT.md`.

Copied rather than imported for two independent reasons:

  1. That module's own header states "NOT PRODUCTION CODE. NOT AN ANALYSIS
     ENTRY POINT." It also patches `socket` at import time to block the
     network, which is appropriate for an offline feasibility runner and
     inappropriate as a side effect of importing a production module.
  2. The HYP-01 R-cross-check validation suite carries an isolation test
     (`test_8_isolation`) asserting that NO production module anywhere in the
     tree so much as names that bridge directory. It enforces this with a
     plain substring scan over every non-test, non-`tools/` `.py` file, so it
     cannot distinguish an import from a passing mention in a comment. This
     module honours the underlying invariant -- it imports nothing from the
     bridge -- and deliberately avoids spelling the guarded directory token
     here, because doing so would trip that scan and turn a provenance note
     into a governance-test failure. The bridge is therefore described rather
     than named. Do not "helpfully" restore the literal path.

This mirrors the pattern `gst_market_response/constants.py` already
establishes for the same situation: "These are copied rather than imported
because [the source] is a large module with unrelated top-level side effects.
A copy carries a provenance comment; it is never silently redefined."

WHAT THE R VALIDATION DOES AND DOES NOT COVER. The HYP-01 cross-check
established implementation agreement between this CR2 arithmetic and
clubSandwich under preregistered tolerances. That is a statement about
*implementation*, not a statistical endorsement, and it does not extend to:

  * Two-way / multiway clustering (Cameron-Gelbach-Miller). No two-way
    implementation exists anywhere in this repository, validated or not.
    HYP-04 Phase 0 therefore ships ONE-WAY (anchor-event) clustering with
    two-way recorded as a stated limitation -- which is the fallback the
    build prompt authorises for exactly this case, not a silent shortcut.
  * Any claim that CR2 is the approved estimator for HYP-01 or HYP-04. It
    is not: HYP-01's own artifact records `method_approved: false`.
"""
from __future__ import annotations

import numpy as np

# Mirrored verbatim in behaviour from tools/hyp01_inference_feasibility.py.
# UNCHANGED arithmetic; only typing and docstrings differ.
TWO_WAY_CLUSTERING_IMPLEMENTED = False

TWO_WAY_LIMITATION_NOTE = (
    "SEs are clustered ONE WAY, on anchor event. Anchor events are themselves "
    "clustered in calendar time (anchors reporting the same week share a macro "
    "environment; the same anchor recurs quarterly), so one-way clustering "
    "understates SEs in the direction that makes a marginal result look "
    "significant. Two-way (anchor event x calendar period) clustering is NOT "
    "implemented: no multiway CR2 implementation exists in this repository, "
    "validated or otherwise, and standing up an unvalidated one would "
    "contradict this project's own treatment of unvalidated inference "
    "machinery. Recorded as a stated Phase 0 limitation."
)

HYP05_TWO_WAY_LIMITATION_NOTE = (
    "HYP-05 re-decided this question on its own terms (2026-09-12) rather "
    "than inheriting HYP-04's conclusion unexamined -- the underlying "
    "constraint is unchanged (no multiway/Satterthwaite CR2 implementation "
    "exists anywhere in this repository, validated or otherwise), but "
    "HYP-05's peer sets are structurally different from HYP-04's: the "
    "competitor/supplier extractor now walks full comma/'and'-separated "
    "lists (edgar_linkage.py, fixed 2026-09-12) rather than capturing only "
    "the first name, so a single anchor's filing can name several peers at "
    "once, and those peers are more likely to share a reporting calendar "
    "with each other than HYP-04's smaller, hand-curated peer set was. That "
    "makes the omitted calendar-period dimension a larger open question "
    "here, not a smaller one. Rather than silently ship one-way and record "
    "the same limitation text, HYP-05 additionally reports a SECOND "
    "one-way clustering (by calendar period) alongside the primary "
    "anchor-event one -- see `dual_cluster_report()`. This is two ONE-WAY "
    "lenses shown side by side, not a two-way estimator: it bounds how much "
    "the calendar dimension could move the SE without claiming to correct "
    "for it jointly with the anchor-event dimension."
)


def ols(X: np.ndarray, y: np.ndarray):
    """Mirrored from tools/hyp01_inference_feasibility.py::ols."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    return beta, XtX_inv, y - X @ beta


def cr_vcov(X: np.ndarray, y: np.ndarray, g: np.ndarray, kind: str = "CR2"):
    """Cluster-robust covariance. Mirrored from hyp01_inference_feasibility.

    kind in {CR0, CR1, CR2, CR3}. CR2 is the estimator the R cross-check
    validated for implementation agreement.
    """
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


def satterthwaite_df(X: np.ndarray, g: np.ndarray, c: np.ndarray) -> float:
    """Bell-McCaffrey / Imbens-Kolesar dof under working model Omega = I.

    Mirrored from tools/hyp01_inference_feasibility.py::satterthwaite_df.

    This quantity doubles as an EFFECTIVE-SAMPLE-SIZE estimate, which is why
    Patch 2's Round 3 addition asks for it alongside N_eff: DEFF captures only
    the peers-within-event clustering dimension, whereas this reflects
    whatever clustering structure inference actually used.
    """
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
    if lam.size == 0:
        return float("nan")
    return float((lam.sum() ** 2) / (lam ** 2).sum())


def intraclass_correlation(values: np.ndarray, cluster: np.ndarray) -> dict:
    """One-way random-effects ICC, for the N_eff design effect.

    ICC = s2_between / (s2_between + s2_within), estimated by the standard
    one-way ANOVA decomposition.

    The RAW estimate is returned unfloored -- it can legitimately come out
    NEGATIVE with few clusters, a known small-sample artifact. Flooring is the
    caller's job at the point DEFF is computed (Patch 2's Round 3 addition
    keeps the raw value visible for transparency and uses the floored one only
    in the arithmetic).
    """
    clusters = np.unique(cluster)
    G = clusters.size
    n = values.size
    if G < 2 or n <= G:
        return {"icc_raw": float("nan"), "n_clusters": int(G), "n_obs": int(n),
                "mean_cluster_size": float(n / G) if G else float("nan"),
                "ms_between": float("nan"), "ms_within": float("nan")}

    grand = float(np.mean(values))
    ss_between = 0.0
    ss_within = 0.0
    sizes = []
    for c in clusters:
        m = cluster == c
        v = values[m]
        sizes.append(v.size)
        ss_between += v.size * (float(np.mean(v)) - grand) ** 2
        ss_within += float(np.sum((v - np.mean(v)) ** 2))

    ms_between = ss_between / (G - 1)
    ms_within = ss_within / (n - G) if n > G else float("nan")

    sizes_arr = np.asarray(sizes, dtype=float)
    # Unequal-cluster-size correction (n_0), standard for one-way ANOVA ICC.
    n0 = (n - float(np.sum(sizes_arr ** 2)) / n) / (G - 1)

    if not np.isfinite(ms_within) or n0 <= 0:
        icc = float("nan")
    else:
        var_between = (ms_between - ms_within) / n0
        denom = var_between + ms_within
        icc = float(var_between / denom) if denom != 0 else float("nan")

    return {
        "icc_raw": icc,
        "n_clusters": int(G),
        "n_obs": int(n),
        "mean_cluster_size": float(np.mean(sizes_arr)),
        "n0_unequal_size_correction": float(n0),
        "ms_between": float(ms_between),
        "ms_within": float(ms_within),
    }


def dual_cluster_report(X: np.ndarray, y: np.ndarray, g_primary: np.ndarray,
                         g_secondary: np.ndarray, kind: str = "CR2") -> dict:
    """Two ONE-WAY clusterings, reported side by side. NOT two-way clustering.

    See `HYP05_TWO_WAY_LIMITATION_NOTE` for why this exists: no multiway CR2
    implementation exists in this repository, so the two dimensions cannot be
    combined into a single, formally correct joint estimator. What this DOES
    give is an honest bound -- the primary (`g_primary`, expected to be
    anchor-event) result is HYP-05's actual inferential result, unchanged
    from what one-way clustering alone would produce; the secondary
    (`g_secondary`, expected to be calendar-period) result is a robustness
    lens only, showing how much the SE would move under a differently-shaped
    but equally valid single clustering choice. Report both; do not silently
    prefer whichever one is smaller.
    """
    beta, V_primary, G_primary = cr_vcov(X, y, g_primary, kind=kind)
    _, V_secondary, G_secondary = cr_vcov(X, y, g_secondary, kind=kind)
    se_primary = np.sqrt(np.diag(V_primary))
    se_secondary = np.sqrt(np.diag(V_secondary))
    ratio = np.divide(se_secondary, se_primary,
                       out=np.full_like(se_primary, float("nan")),
                       where=se_primary != 0)
    return {
        "kind": kind,
        "beta": beta,
        "primary": {"dimension": "anchor_event", "se": se_primary,
                    "n_clusters": int(G_primary)},
        "secondary": {"dimension": "calendar_period", "se": se_secondary,
                      "n_clusters": int(G_secondary)},
        "se_ratio_secondary_over_primary": ratio,
        "note": ("Two ONE-WAY clusterings, not a two-way estimator. "
                 "`primary` (anchor_event) is HYP-05's inferential result; "
                 "`secondary` (calendar_period) is a robustness lens only."),
    }
