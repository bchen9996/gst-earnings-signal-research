#!/usr/bin/env python3
# GST Intent-Filtered vs Raw-Ticker Z-Score Comparison — does searching
# "[TICKER] earnings" produce a cleaner spike-week signal than the raw
# ticker-symbol search term already used in production?
#
# Aggregates the 40 on-disk pulls in
# "GST Data/Weekly Data (Intent Filtered Earnings)/" (8 tickers x
# 2021-2025) into one weekly series per ticker, computes a rolling
# z-score with the SAME method as production (GST_Build_Foundation_
# AllTickers.py: 12-week trailing window, min_periods=8, shifted so the
# current week never leaks into its own baseline), and joins it against
# the raw ticker z-score already on disk in Live Signal Engine/
# AllTickers_ZscoreSeries.csv (zscore_simple column).
#
# STRONG_EARNINGS events (the raw-ticker z>=5 + near_earnings==True
# population already used throughout this project, n=147 total) are
# pulled from Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv and used to label which (ticker,
# week) rows are spike weeks; every other on-disk week for these 8
# tickers is a non-spike week. Separation between spike and non-spike
# weeks is then compared for the raw z-score vs the intent-filtered
# z-score using Cohen's d and AUC (Mann-Whitney), since the raw z-score
# distribution is heavily right-skewed by a handful of extreme events
# (up to z~18) and AUC is invariant to that skew while Cohen's d is not
# — reporting both surfaces whether the two metrics agree.
#
# Output: Live Signal Engine/IntentFiltered_GST_Results.csv
#   One row per (ticker, week) for all 8 tickers, 2021-2025, with both
#   z-scores side by side and the spike-week flag. Separation stats and
#   the cleaner-approach verdict are printed to stdout, not stored as
#   extra rows, matching this project's convention elsewhere (e.g.
#   GST_RelativeIV_SignalQuality_Test.py).

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

sys.stdout.reconfigure(encoding="utf-8")

TICKERS = ["MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN"]
YEARS = list(range(2021, 2026))

INTENT_DIR = Path("GST Data") / "Weekly Data (Intent Filtered Earnings)"
RAW_ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
STRONG_EVENTS_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "IntentFiltered_GST_Results.csv"

ROLLING_WINDOW = 12   # matches GST_Build_Foundation_AllTickers.py
MIN_PERIODS = 8       # matches GST_Build_Foundation_AllTickers.py
STRONG_TIER_Z_THRESHOLD = 5.0   # matches GST_Live_Signal_Engine.py


def load_intent_series(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = INTENT_DIR / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Week" not in df.columns or "gst" not in df.columns:
            continue
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        frames.append(df[["Week", "gst"]].dropna(subset=["Week"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Week").reset_index(drop=True)


def rolling_zscore(gst: pd.Series) -> pd.Series:
    shifted = gst.shift(1)
    roll = shifted.rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    z = (gst - roll.mean()) / roll.std()
    return z.replace([np.inf, -np.inf], np.nan)


def cohens_d(spike: np.ndarray, nonspike: np.ndarray) -> float | None:
    n1, n2 = len(spike), len(nonspike)
    if n1 < 2 or n2 < 2:
        return None
    pooled_var = ((n1 - 1) * spike.var(ddof=1) + (n2 - 1) * nonspike.var(ddof=1)) / (n1 + n2 - 2)
    if pooled_var <= 0:
        return None
    return float((spike.mean() - nonspike.mean()) / np.sqrt(pooled_var))


def auc_separation(spike: np.ndarray, nonspike: np.ndarray) -> float | None:
    """P(random spike-week z > random non-spike-week z), via Mann-Whitney U."""
    if len(spike) == 0 or len(nonspike) == 0:
        return None
    u, _ = mannwhitneyu(spike, nonspike, alternative="two-sided")
    return float(u / (len(spike) * len(nonspike)))


def main():
    print(f"*** Intent-Filtered vs Raw GST Z-Score Comparison ({len(TICKERS)} tickers) ***\n")

    # --- Intent-filtered weekly series + z-score, per ticker ---
    intent_frames = []
    for ticker in TICKERS:
        weekly = load_intent_series(ticker)
        if weekly.empty:
            print(f"[{ticker}] no intent-filtered data on disk, skipping")
            continue
        weekly["zscore_intent"] = rolling_zscore(weekly["gst"])
        weekly["ticker"] = ticker
        weekly = weekly.rename(columns={"Week": "week", "gst": "gst_intent"})
        intent_frames.append(weekly[["ticker", "week", "gst_intent", "zscore_intent"]])
        print(f"[{ticker}] {len(weekly)} intent-filtered weeks loaded")
    intent_df = pd.concat(intent_frames, ignore_index=True)

    # --- Raw ticker z-score, already on disk ---
    raw = pd.read_csv(RAW_ZSCORE_PATH)
    raw["week"] = pd.to_datetime(raw["week"], errors="coerce")
    raw = raw[raw["ticker"].isin(TICKERS)].rename(
        columns={"gst": "gst_raw", "zscore_simple": "zscore_raw"})[["ticker", "week", "gst_raw", "zscore_raw"]]

    merged = pd.merge(intent_df, raw, on=["ticker", "week"], how="inner")
    print(f"\nMerged (ticker, week) rows with both series present: {len(merged)}")

    # --- STRONG_EARNINGS spike-week labels (raw z>=5, near_earnings, existing 147-event population) ---
    events = pd.read_csv(STRONG_EVENTS_PATH)
    events["spike_week"] = pd.to_datetime(events["spike_week"], errors="coerce")
    strong = events[(events["zscore"] >= STRONG_TIER_Z_THRESHOLD) & (events["near_earnings"] == True)]  # noqa: E712
    spike_keys = set(zip(strong["ticker"], strong["spike_week"]))
    n_strong_total = len(strong)
    n_strong_our8 = strong["ticker"].isin(TICKERS).sum()
    print(f"STRONG_EARNINGS population (z>={STRONG_TIER_Z_THRESHOLD:g}, near_earnings): "
          f"n={n_strong_total} total, n={n_strong_our8} among these {len(TICKERS)} tickers")

    merged["is_strong_earnings_spike"] = list(zip(merged["ticker"], merged["week"]))
    merged["is_strong_earnings_spike"] = merged["is_strong_earnings_spike"].isin(spike_keys)

    out = merged.copy()
    out["week"] = out["week"].dt.date
    out = out.sort_values(["ticker", "week"]).reset_index(drop=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out)} (ticker, week) rows -> {OUT_PATH}")

    # --- Separation: spike weeks vs non-spike weeks, raw z vs intent z ---
    spike_rows = merged[merged["is_strong_earnings_spike"]]
    nonspike_rows = merged[~merged["is_strong_earnings_spike"]]

    print(f"\nMatched spike weeks (in both series): n={len(spike_rows)} / {n_strong_our8} STRONG_EARNINGS events for these tickers")
    print(f"Non-spike weeks: n={len(nonspike_rows)}\n")

    results = {}
    for label, col in [("RAW_TICKER", "zscore_raw"), ("INTENT_FILTERED", "zscore_intent")]:
        s = spike_rows[col].dropna().to_numpy()
        ns = nonspike_rows[col].dropna().to_numpy()
        d = cohens_d(s, ns)
        auc = auc_separation(s, ns)
        results[label] = {
            "n_spike": len(s), "n_nonspike": len(ns),
            "mean_spike": s.mean() if len(s) else None,
            "mean_nonspike": ns.mean() if len(ns) else None,
            "cohens_d": d, "auc": auc,
        }
        print(f"=== {label} (column: {col}) ===")
        print(f"  n_spike={len(s)}  n_nonspike={len(ns)}")
        print(f"  mean z, spike weeks:     {s.mean():+.3f}" if len(s) else "  mean z, spike weeks: n/a")
        print(f"  mean z, non-spike weeks: {ns.mean():+.3f}" if len(ns) else "  mean z, non-spike weeks: n/a")
        print(f"  Cohen's d:  {d:+.3f}" if d is not None else "  Cohen's d: n/a")
        print(f"  AUC (P(spike z > non-spike z)): {auc:.3f}" if auc is not None else "  AUC: n/a")
        print()

    raw_auc, intent_auc = results["RAW_TICKER"]["auc"], results["INTENT_FILTERED"]["auc"]
    raw_d, intent_d = results["RAW_TICKER"]["cohens_d"], results["INTENT_FILTERED"]["cohens_d"]

    print("=== VERDICT ===")
    if raw_auc is not None and intent_auc is not None:
        if abs(raw_auc - intent_auc) < 0.005:
            auc_verdict = "TIE"
        else:
            auc_verdict = "RAW_TICKER" if raw_auc > intent_auc else "INTENT_FILTERED"
        print(f"By AUC:       raw={raw_auc:.3f} vs intent={intent_auc:.3f} -> cleaner separation: {auc_verdict}")
    if raw_d is not None and intent_d is not None:
        d_verdict = "RAW_TICKER" if abs(raw_d) > abs(intent_d) else "INTENT_FILTERED"
        print(f"By |Cohen's d|: raw={raw_d:+.3f} vs intent={intent_d:+.3f} -> cleaner separation: {d_verdict}")
    print("\n(AUC is the primary metric here — the raw z-score distribution is heavily right-skewed")
    print(" by a handful of extreme STRONG_EARNINGS events, which inflates Cohen's d without necessarily")
    print(" reflecting how well a threshold rule would separate spike from non-spike weeks day to day.)")


if __name__ == "__main__":
    main()
