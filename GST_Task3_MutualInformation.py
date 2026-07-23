#!/usr/bin/env python3
# TASK 3 — Mutual information vs Spearman correlation, z-score vs
# realized move magnitude. All on-disk data, no new pulls: reuses
# max_abs_excess_pct already computed in Conjunction Zscore
# (2021-2025)*/​<TICKER>_zconjunction.csv, merged with the existing 147
# z>=5 STRONG_EARNINGS event list.
#
# MI estimated via sklearn's mutual_info_regression (k-NN based, has a
# stochastic component — hence averaging across 5 random seeds, reporting
# mean and std). Compared to Spearman correlation (monotonic, not
# strictly "linear," but the closest standard/available comparator — this
# distinction is disclosed, not glossed over).
#
# MI is converted to a Gaussian-equivalent R using R = sqrt(1 - exp(-2*MI))
# so it's on a comparable [0,1] scale to |Spearman r| — a standard but
# approximate conversion (exact only under joint-Gaussian assumptions),
# disclosed as an approximation for interpretability, not treated as exact.
#
# Output: Live Signal Engine/MutualInformation_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.feature_selection import mutual_info_regression

sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR

CONJ_DIRS = {t: Path("Conjunction Zscore (2021-2025)") for t in TICKERS_ORIGINAL}
CONJ_DIRS.update({t: Path("Conjunction Zscore (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "MutualInformation_Results.csv"

Z_THRESHOLD = 5.0
N_SEEDS = 5
SEEDS = [42, 43, 44, 45, 46]


def main():
    print(f"*** TASK 3: Mutual information vs Spearman correlation (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"]).dt.date.astype(str)
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    conj_frames = []
    for t in events["ticker"].unique():
        p = CONJ_DIRS[t] / f"{t}_zconjunction.csv"
        if p.exists():
            df = pd.read_csv(p)
            df["ticker"] = t
            df["spike_week"] = pd.to_datetime(df["spike_week"]).dt.date.astype(str)
            conj_frames.append(df[["ticker", "spike_week", "max_abs_excess_pct"]])
    conj = pd.concat(conj_frames, ignore_index=True)

    merged = events.merge(conj, on=["ticker", "spike_week"], how="left")
    n_missing = merged["max_abs_excess_pct"].isna().sum()
    if n_missing:
        print(f"NOTE: {n_missing} event(s) missing max_abs_excess_pct — excluded.\n")
    merged = merged.dropna(subset=["max_abs_excess_pct"])
    print(f"Usable events: n={len(merged)}\n")

    z = merged["zscore"].to_numpy(dtype=float)
    move = merged["max_abs_excess_pct"].abs().to_numpy(dtype=float)

    rho, p_spearman = spearmanr(z, move)
    print(f"=== SPEARMAN CORRELATION (monotonic, not strictly linear — closest standard comparator) ===")
    print(f"rho={rho:+.4f}  p={p_spearman:.4f}")
    r_equiv_spearman = abs(rho)

    print(f"\n=== MUTUAL INFORMATION (sklearn mutual_info_regression, {N_SEEDS} seeds) ===")
    X = z.reshape(-1, 1)
    mi_values = []
    for seed in SEEDS:
        mi = mutual_info_regression(X, move, random_state=seed, n_neighbors=3)[0]
        mi_values.append(mi)
        print(f"  seed={seed}: MI={mi:.4f} nats")
    mi_mean = float(np.mean(mi_values))
    mi_std = float(np.std(mi_values))
    print(f"\nMI: mean={mi_mean:.4f} nats  std={mi_std:.4f} nats")

    mi_r_equiv = float(np.sqrt(max(0.0, 1 - np.exp(-2 * mi_mean))))
    print(f"MI-implied Gaussian-equivalent R: {mi_r_equiv:.4f}  (approximate conversion, disclosed above)")
    print(f"|Spearman r|: {r_equiv_spearman:.4f}")

    excess = mi_r_equiv - r_equiv_spearman
    print(f"\nDiff (MI-equivalent R - |Spearman r|): {excess:+.4f}")
    if excess > 0.10:
        print("=> MI substantially exceeds what the monotonic correlation implies — "
              "evidence of a nonlinear/non-monotonic dependence component.")
    else:
        print("=> MI does NOT substantially exceed the monotonic correlation — "
              "no strong evidence of additional nonlinear dependence beyond what Spearman already captures.")

    out = pd.DataFrame([{
        "n": len(merged), "spearman_rho": round(rho, 4), "spearman_p": round(p_spearman, 4),
        "mi_mean_nats": round(mi_mean, 4), "mi_std_nats": round(mi_std, 4),
        "mi_seeds": SEEDS, "mi_values_per_seed": [round(v, 4) for v in mi_values],
        "mi_r_equivalent": round(mi_r_equiv, 4), "abs_spearman_r": round(r_equiv_spearman, 4),
        "mi_minus_spearman_r_equiv": round(excess, 4),
    }])
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
