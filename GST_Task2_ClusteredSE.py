#!/usr/bin/env python3
# TASK 2 — Clustered standard errors: the canonical n=147 z>=5
# STRONG_EARNINGS events aren't independent draws — multiple tickers can
# spike in the SAME earnings-calendar week (broad market earnings
# clustering, e.g. "big tech week"), which naive (unclustered) SEs treat
# as independent observations, understating true uncertainty. This
# clusters events by ISO calendar week of the spike anchor date, computes
# cluster-robust SEs for win rate and mean P&L, and compares against the
# naive (i.i.d.) SEs used everywhere else in this project.
#
# *** METHODOLOGY DISCLOSURE ***
# For n_clusters < 30, applies a WILD cluster bootstrap: under each null
# (H0: win rate = 50%, H0: mean P&L = 0), computes per-event residuals
# from the null value, flips the SIGN of each residual by a whole cluster
# at a time (Rademacher weight, one +-1 draw per cluster, applied to every
# event in that cluster together -- this is what makes it "cluster" rather
# than i.i.d. bootstrap), reconstructs a bootstrap sample, and repeats
# 10,000 times to build a null distribution of the test statistic. This is
# a standard simplification of Cameron/Gelbach/Miller wild cluster
# bootstrap adapted to a simple mean/proportion (not a regression) --
# disclosed explicitly since there's no single canonical form for this
# non-regression case. For n_clusters >= 30, uses the standard analytic
# cluster-robust ("CR1") variance formula for a simple mean instead.
#
# Output: Live Signal Engine/ClusteredSE_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import math
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "ClusteredSE_Results.csv"

Z_THRESHOLD = 5.0
N_BOOTSTRAP = 10000
RANDOM_SEED = 42
CLUSTER_COUNT_CUTOFF = 30


def cluster_robust_variance_of_mean(values: np.ndarray, cluster_ids: np.ndarray) -> tuple[float, int]:
    """Standard CR1 sandwich variance for a simple mean (Cameron & Miller 2015, sec 2)."""
    n = len(values)
    clusters = np.unique(cluster_ids)
    g = len(clusters)
    grand_mean = values.mean()
    # cluster-level sums of (value - grand_mean), the "score" for a mean estimator
    cluster_sum_sq = 0.0
    for c in clusters:
        resid_sum = (values[cluster_ids == c] - grand_mean).sum()
        cluster_sum_sq += resid_sum ** 2
    # finite-sample correction factor, standard for CR1
    correction = (g / (g - 1)) * ((n - 1) / (n - len(clusters) if n > len(clusters) else 1))
    var = correction * cluster_sum_sq / (n ** 2)
    return var, g


def wild_cluster_bootstrap_pvalue(values: np.ndarray, cluster_ids: np.ndarray, null_value: float,
                                   n_bootstrap: int, rng: np.random.Generator) -> tuple[float, float]:
    """Wild cluster bootstrap for a simple one-sample mean test, H0: mean(values) = null_value.
    Returns (bootstrap_se, two_sided_pvalue)."""
    clusters = np.unique(cluster_ids)
    resid = values - null_value  # residuals under the null
    observed_stat = values.mean() - null_value

    cluster_to_idx = {c: np.where(cluster_ids == c)[0] for c in clusters}
    boot_stats = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        weights = rng.choice([-1.0, 1.0], size=len(clusters))
        boot_resid = resid.copy()
        for c, w in zip(clusters, weights):
            boot_resid[cluster_to_idx[c]] *= w
        boot_stats[b] = boot_resid.mean()

    boot_se = float(boot_stats.std(ddof=1))
    p_value = float((np.abs(boot_stats) >= np.abs(observed_stat)).mean())
    return boot_se, p_value


def main():
    print(f"*** TASK 2: Clustered standard errors (cluster = ISO earnings-calendar week) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    iso = events["spike_week"].dt.isocalendar()
    events["cluster_id"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)

    n_events = len(events)
    n_clusters = events["cluster_id"].nunique()
    cluster_sizes = events.groupby("cluster_id").size()
    print(f"n events: {n_events}")
    print(f"n clusters (distinct ISO earnings-calendar weeks): {n_clusters}")
    print(f"Cluster size distribution: min={cluster_sizes.min()} max={cluster_sizes.max()} "
          f"mean={cluster_sizes.mean():.2f} median={cluster_sizes.median():.0f}")
    print(f"Clusters with >1 event: {(cluster_sizes > 1).sum()}/{n_clusters}\n")

    win = events["end_of_spike_week_win"].astype(float).to_numpy()
    pnl = events["end_of_spike_week_pnl_pct"].astype(float).to_numpy()
    cluster_ids = events["cluster_id"].to_numpy()

    rng = np.random.default_rng(RANDOM_SEED)
    method = "wild_cluster_bootstrap" if n_clusters < CLUSTER_COUNT_CUTOFF else "analytic_CR1"
    print(f"n_clusters={n_clusters} {'<' if n_clusters < CLUSTER_COUNT_CUTOFF else '>='} {CLUSTER_COUNT_CUTOFF} "
          f"-> using {method}\n")

    results = []

    # --- Win rate ---
    naive_se_win = float(np.sqrt(win.mean() * (1 - win.mean()) / n_events))
    naive_z_win = (win.mean() - 0.5) / naive_se_win
    naive_p_win = float(2 * (1 - 0.5 * (1 + math.erf(abs(naive_z_win) / math.sqrt(2))))) if naive_se_win > 0 else None

    if method == "wild_cluster_bootstrap":
        cr_se_win, cr_p_win = wild_cluster_bootstrap_pvalue(win, cluster_ids, 0.5, N_BOOTSTRAP, rng)
    else:
        var_win, _ = cluster_robust_variance_of_mean(win, cluster_ids)
        cr_se_win = float(np.sqrt(var_win))
        z = (win.mean() - 0.5) / cr_se_win if cr_se_win > 0 else np.nan
        cr_p_win = float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))) if cr_se_win > 0 else None

    print(f"=== WIN RATE (H0: win rate = 50%) ===")
    print(f"Observed win rate: {win.mean()*100:.1f}%  (n={n_events})")
    print(f"Naive (i.i.d.) SE: {naive_se_win:.4f}  p={naive_p_win:.4g}")
    print(f"Cluster-robust SE ({method}): {cr_se_win:.4f}  p={cr_p_win:.4g}")
    print(f"SE inflation factor (cluster/naive): {cr_se_win/naive_se_win:.2f}x")
    print(f"Still significant at 0.05 after clustering: {cr_p_win < 0.05}\n")

    results.append({"metric": "win_rate", "observed": round(win.mean() * 100, 2), "n_events": n_events,
                     "n_clusters": n_clusters, "method": method,
                     "naive_se": round(naive_se_win, 5), "naive_p": round(naive_p_win, 5),
                     "cluster_robust_se": round(cr_se_win, 5), "cluster_robust_p": round(cr_p_win, 5),
                     "se_inflation_factor": round(cr_se_win / naive_se_win, 3) if naive_se_win > 0 else None,
                     "significant_after_clustering": bool(cr_p_win < 0.05)})

    # --- Mean P&L ---
    naive_se_pnl = float(pnl.std(ddof=1) / np.sqrt(n_events))
    naive_z_pnl = pnl.mean() / naive_se_pnl
    naive_p_pnl = float(2 * (1 - 0.5 * (1 + math.erf(abs(naive_z_pnl) / math.sqrt(2)))))

    if method == "wild_cluster_bootstrap":
        cr_se_pnl, cr_p_pnl = wild_cluster_bootstrap_pvalue(pnl, cluster_ids, 0.0, N_BOOTSTRAP, rng)
    else:
        var_pnl, _ = cluster_robust_variance_of_mean(pnl, cluster_ids)
        cr_se_pnl = float(np.sqrt(var_pnl))
        z = pnl.mean() / cr_se_pnl if cr_se_pnl > 0 else np.nan
        cr_p_pnl = float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))) if cr_se_pnl > 0 else None

    print(f"=== MEAN P&L (H0: mean P&L = 0%) ===")
    print(f"Observed mean P&L: {pnl.mean():+.1f}%  (n={n_events})")
    print(f"Naive (i.i.d.) SE: {naive_se_pnl:.3f}  p={naive_p_pnl:.4g}")
    print(f"Cluster-robust SE ({method}): {cr_se_pnl:.3f}  p={cr_p_pnl:.4g}")
    print(f"SE inflation factor (cluster/naive): {cr_se_pnl/naive_se_pnl:.2f}x")
    print(f"Still significant at 0.05 after clustering: {cr_p_pnl < 0.05}\n")

    results.append({"metric": "mean_pnl_pct", "observed": round(pnl.mean(), 2), "n_events": n_events,
                     "n_clusters": n_clusters, "method": method,
                     "naive_se": round(naive_se_pnl, 4), "naive_p": round(naive_p_pnl, 5),
                     "cluster_robust_se": round(cr_se_pnl, 4), "cluster_robust_p": round(cr_p_pnl, 5),
                     "se_inflation_factor": round(cr_se_pnl / naive_se_pnl, 3) if naive_se_pnl > 0 else None,
                     "significant_after_clustering": bool(cr_p_pnl < 0.05)})

    result_df = pd.DataFrame(results)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
