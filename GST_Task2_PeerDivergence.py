#!/usr/bin/env python3
# TASK 2 — Peer divergence. All on-disk data, no new pulls: reuses
# AllTickers_ZscoreSeries.csv, AllTickers_Sectors.csv, and
# group_a_z4_earnings_adjacent.csv.
#
# For each z>=5 event, divergence = focal ticker's z-score minus the mean
# z-score of OTHER same-sector tickers that same week. Sectors with fewer
# than 3 tickers in the 51-ticker universe can't support a meaningful
# peer mean (1-2 tickers isn't "peers," it's one comparison point) — those
# events are FLAGGED and excluded from the peer-mean calc, not silently
# computed on a degenerate sample.
#
# Output: Live Signal Engine/PeerDivergence_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "PeerDivergence_Results.csv"

Z_THRESHOLD = 5.0
MIN_SECTOR_SIZE = 3
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    print(f"*** TASK 2: Peer divergence (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = dict(zip(sector_df["ticker"], sector_df["sector"]))
    sector_sizes = sector_df["sector"].value_counts().to_dict()
    small_sectors = {s for s, n in sector_sizes.items() if n < MIN_SECTOR_SIZE}
    print(f"Sectors excluded (fewer than {MIN_SECTOR_SIZE} tickers in the 51-ticker universe): "
          f"{ {s: sector_sizes[s] for s in small_sectors} }\n")

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_by_week = {w: g.set_index("ticker")["zscore_simple"] for w, g in z_df.groupby("week")}

    rows = []
    n_flagged_small_sector = 0
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        sector = ticker_to_sector.get(ticker)
        if sector in small_sectors or sector is None or sector == "UNKNOWN":
            n_flagged_small_sector += 1
            rows.append({"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore, "sector": sector,
                         "peer_mean_z": None, "divergence": None, "flagged_small_sector": True,
                         "end_of_spike_week_win": ev["end_of_spike_week_win"],
                         "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"]})
            continue

        week_z = z_by_week.get(anchor)
        if week_z is None:
            n_flagged_small_sector += 1
            continue
        peer_tickers = [t for t, s in ticker_to_sector.items() if s == sector and t != ticker]
        peer_zs = week_z.reindex(peer_tickers).dropna()
        if len(peer_zs) == 0:
            n_flagged_small_sector += 1
            rows.append({"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore, "sector": sector,
                         "peer_mean_z": None, "divergence": None, "flagged_small_sector": True,
                         "end_of_spike_week_win": ev["end_of_spike_week_win"],
                         "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"]})
            continue

        peer_mean_z = float(peer_zs.mean())
        divergence = zscore - peer_mean_z
        rows.append({"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore, "sector": sector,
                     "peer_mean_z": peer_mean_z, "divergence": divergence, "flagged_small_sector": False,
                     "end_of_spike_week_win": ev["end_of_spike_week_win"],
                     "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"]})

    result = pd.DataFrame(rows)
    print(f"Events flagged (small/unknown sector, excluded from peer-mean split): n={n_flagged_small_sector}\n")

    main_set = result[~result["flagged_small_sector"]].copy()
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    median_div = main_set["divergence"].median()
    main_set["group"] = np.where(main_set["divergence"] >= median_div, "high_divergence", "low_divergence")

    print(f"Main analysis set: n={len(main_set)}   median divergence={median_div:+.2f}\n")

    high = main_set[main_set["group"] == "high_divergence"]
    low = main_set[main_set["group"] == "low_divergence"]
    high_u = high[high[win_col].notna()]
    low_u = low[low[win_col].notna()]

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"High divergence (company-specific attention): n={len(high_u):<4} win={high_u[win_col].mean()*100:5.1f}%  "
          f"avg={high_u[pnl_col].mean():+7.1f}%  median={high_u[pnl_col].median():+7.1f}%")
    print(f"Low divergence (sector-wide attention):        n={len(low_u):<4} win={low_u[win_col].mean()*100:5.1f}%  "
          f"avg={low_u[pnl_col].mean():+7.1f}%  median={low_u[pnl_col].median():+7.1f}%")

    rng = np.random.default_rng(RANDOM_SEED)
    diff, p = two_sample_permutation_test(high_u[pnl_col].to_numpy(dtype=float),
                                           low_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
    sig = "significant" if p < 0.05 else "not significant"
    print(f"\nDiff (High - Low), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
