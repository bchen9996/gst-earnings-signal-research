#!/usr/bin/env python3
# TASK 6 — Spike shape clustering. All on-disk data, no new pulls: reuses
# AllTickers_ZscoreSeries.csv (zscore_simple) and the existing 147 z>=5
# STRONG_EARNINGS event list.
#
# For each event, extracts the z-score trajectory for weeks -4,-3,-2,-1
# (the spike week itself, week 0, is excluded — this describes the
# BUILD-UP shape, not the spike). Each of the 4 lag positions is
# standardized (column-wise z-score of the trajectory data itself) before
# k-means, so no single lag dominates the Euclidean distance purely due to
# having higher variance across events.
#
# *** STABILITY METRIC — DISCLOSED SUBSTITUTION ***
# The task asked for "std of within-cluster win rate across seeds," but
# cluster LABELS are arbitrary and not comparable across different
# k-means random initializations (cluster "1" in one seed run may
# correspond to cluster "3" in another) — computing per-label win-rate std
# across seeds would silently conflate unrelated clusters. Adjusted Rand
# Index (ARI) between pairs of seed runs' assignments is used instead —
# the standard, label-invariant way to measure whether k-means is finding
# the same groupings regardless of which events cluster together, not
# which arbitrary number they're called.
#
# Output: Live Signal Engine/SpikeShapeClustering_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
from itertools import combinations
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
OUT_PATH = Path("Live Signal Engine") / "SpikeShapeClustering_Results.csv"

Z_THRESHOLD = 5.0
LAG_WEEKS = [4, 3, 2, 1]
K_VALUES = [3, 4, 5]
STABILITY_SEEDS = list(range(10))
PRIMARY_SEED = 42


def main():
    print(f"*** TASK 6: Spike shape clustering (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_by_ticker = {t: g.set_index("week")["zscore_simple"] for t, g in z_df.groupby("ticker")}

    trajectories, valid_events = [], []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        series = z_by_ticker.get(ticker)
        if series is None:
            continue
        traj = []
        ok = True
        for lag in LAG_WEEKS:
            wk = anchor - timedelta(weeks=lag)
            val = series.get(wk)
            if val is None or pd.isna(val):
                ok = False
                break
            traj.append(float(val))
        if ok:
            trajectories.append(traj)
            valid_events.append(ev)

    traj_arr = np.array(trajectories)
    valid_df = pd.DataFrame(valid_events).reset_index(drop=True)
    n_dropped = len(events) - len(valid_df)
    print(f"Usable events with complete 4-week prior trajectory: n={len(valid_df)}  (dropped {n_dropped} with missing history)\n")

    # standardize each lag column
    means = traj_arr.mean(axis=0)
    stds = traj_arr.std(axis=0)
    stds[stds == 0] = 1.0
    traj_std = (traj_arr - means) / stds

    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    all_rows = []
    for k in K_VALUES:
        print(f"=== k={k} ===")
        km = KMeans(n_clusters=k, random_state=PRIMARY_SEED, n_init=10)
        labels = km.fit_predict(traj_std)
        valid_df[f"cluster_k{k}"] = labels

        # Stability first: ARI between all pairs of 10 seed runs, attached to every cluster row for this k
        seed_labels = []
        for seed in STABILITY_SEEDS:
            km_s = KMeans(n_clusters=k, random_state=seed, n_init=10)
            seed_labels.append(km_s.fit_predict(traj_std))
        aris = [adjusted_rand_score(a, b) for a, b in combinations(seed_labels, 2)]
        ari_mean, ari_std = float(np.mean(aris)), float(np.std(aris))

        for c in range(k):
            mask = labels == c
            n_c = mask.sum()
            centroid_raw = traj_arr[mask].mean(axis=0)
            shape = describe_shape(centroid_raw)
            sub = valid_df[mask]
            sub_u = sub[sub[win_col].notna()]
            wr = sub_u[win_col].mean() * 100 if len(sub_u) else None
            med = sub_u[pnl_col].median() if len(sub_u) else None
            print(f"  Cluster {c}: n={n_c:<4} shape='{shape}'  centroid(wk-4..wk-1)={np.round(centroid_raw,2).tolist()}  "
                  f"win={wr:.1f}%  median={med:+.1f}%" if wr is not None else
                  f"  Cluster {c}: n={n_c:<4} shape='{shape}'  no usable P&L data")
            all_rows.append({
                "k": k, "cluster": c, "n": int(n_c), "shape_description": shape,
                "centroid_wk_minus4": round(centroid_raw[0], 3), "centroid_wk_minus3": round(centroid_raw[1], 3),
                "centroid_wk_minus2": round(centroid_raw[2], 3), "centroid_wk_minus1": round(centroid_raw[3], 3),
                "win_rate_pct": round(wr, 1) if wr is not None else None,
                "median_pnl_pct": round(med, 1) if med is not None else None,
                "ari_mean_across_seeds": round(ari_mean, 3), "ari_std_across_seeds": round(ari_std, 3),
            })

        print(f"  Stability across {len(STABILITY_SEEDS)} seeds: mean ARI={ari_mean:.3f}  std ARI={ari_std:.3f}  "
              f"({'stable' if ari_mean > 0.7 else 'moderate' if ari_mean > 0.4 else 'UNSTABLE'})\n")

    result = pd.DataFrame(all_rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}")


def describe_shape(centroid: np.ndarray) -> str:
    """centroid is [wk-4, wk-3, wk-2, wk-1] raw z-scores."""
    diffs = np.diff(centroid)
    total_range = centroid.max() - centroid.min()
    if total_range < 0.5:
        return "flat/quiet"
    if np.all(diffs >= -0.1):
        if diffs[-1] > diffs[0] * 1.5 and diffs[-1] > 0.3:
            return "accelerating build (gradual then sharp)"
        return "gradual build (steadily rising into spike)"
    if centroid[-1] == centroid.max() and diffs[-1] > 0.5 and np.all(np.abs(diffs[:-1]) < 0.4):
        return "sudden late jump (quiet then last-week pop)"
    if centroid.argmax() < 3 and diffs[-1] < -0.2:
        return "peak-and-fade (elevated then cooling before spike)"
    return "irregular/mixed"


if __name__ == "__main__":
    main()
