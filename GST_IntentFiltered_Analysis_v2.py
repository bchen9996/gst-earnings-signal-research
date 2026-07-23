#!/usr/bin/env python3
# GST Intent-Filtered vs Raw-Ticker Z-Score Comparison — v2, CORRECTED.
#
# *** v1 (GST_IntentFiltered_Analysis.py -> IntentFiltered_GST_Results.csv)
# WAS CIRCULAR — DO NOT USE IT. ***
# v1's "is_strong_earnings_spike" label was built from
# (zscore_raw >= 5) AND near_earnings, i.e. literally thresholding the
# same zscore_raw column it was then scored against. That guarantees
# zscore_raw's AUC comes out near 1.0 by construction and tells you
# nothing real about signal quality — it was measuring "does zscore_raw
# separate the group defined by zscore_raw>=5," which is tautological.
#
# v2 fixes this by building the spike label from something neither
# z-score series can see: the REALIZED market-excess price move in the
# calendar week following each (ticker, week) anchor, computed directly
# from Daily Excess Return Data (2021-2025[, Broad50 Clear]) — no GST
# data of any kind feeds into this label.
#
# Ground-truth label: for each ticker, take the absolute realized
# excess return over (anchor, anchor+6 days] (same 6-day "end of spike
# week" horizon this project already uses elsewhere, e.g.
# GST_EarningsAdjacent_SpikeVsNoSpike_Test.py's EXIT_HORIZONS). Flag a
# week as a "realized spike" if that ticker's own absolute move is in
# ITS OWN top decile (>=90th percentile of that ticker's weeks with a
# usable forward window). Per-ticker (not pooled) percentile is used
# because these 8 tickers have very different baseline volatility
# (e.g. NFLX vs STZ) — a pooled cutoff would just relabel "which
# tickers are volatile," not "which weeks were unusual for that
# ticker." Top decile is a standard, defensible tail-event cutoff and
# is NOT tuned to either z-score series.
#
# Same AUC (Mann-Whitney) + Cohen's d comparison as v1, now against
# this independent label.
#
# Output: Live Signal Engine/IntentFiltered_GST_Results_v2.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

sys.stdout.reconfigure(encoding="utf-8")

TICKERS = ["MSFT", "ADBE", "NFLX", "NKE", "STZ", "QCOM", "SBUX", "AMZN"]
TICKERS_ORIGINAL_DIR = Path("Daily Excess Return Data (2021-2025)")
TICKERS_BROAD50_DIR = Path("Daily Excess Return Data (2021-2025 Broad50 Clear)")
DAILY_DIRS = {t: TICKERS_ORIGINAL_DIR for t in TICKERS if t != "STZ"}
DAILY_DIRS["STZ"] = TICKERS_BROAD50_DIR

YEARS = list(range(2021, 2026))

INTENT_DIR = Path("GST Data") / "Weekly Data (Intent Filtered Earnings)"
RAW_ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
OUT_PATH = Path("Live Signal Engine") / "IntentFiltered_GST_Results_v2.csv"
V1_PATH = Path("Live Signal Engine") / "IntentFiltered_GST_Results.csv"

ROLLING_WINDOW = 12   # matches GST_Build_Foundation_AllTickers.py / production
MIN_PERIODS = 8       # matches GST_Build_Foundation_AllTickers.py / production
FORWARD_WINDOW_DAYS = 6   # matches this project's "end_of_spike_week" horizon
SPIKE_PERCENTILE = 0.90   # top decile of a ticker's OWN realized-move distribution


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


def load_daily_excess(ticker: str) -> pd.DataFrame:
    directory = DAILY_DIRS[ticker]
    ret_col = f"{ticker} Daily Return"
    excess_col = "Excess Daily Return"
    frames = []
    for year in YEARS:
        p = directory / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or excess_col not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df[["Date", excess_col]].dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame(columns=["Date", excess_col])
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def realized_forward_move(daily: pd.DataFrame, anchor: pd.Timestamp) -> float | None:
    """Absolute cumulative market-excess return over (anchor, anchor+6d] — independent of any GST z-score."""
    end = anchor + timedelta(days=FORWARD_WINDOW_DAYS)
    mask = (daily["Date"] > anchor) & (daily["Date"] <= end)
    rets = daily.loc[mask, "Excess Daily Return"]
    if rets.empty:
        return None
    cum_ret = float((1 + rets).prod() - 1)
    return abs(cum_ret) * 100


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


def flag_v1_as_circular():
    if not V1_PATH.exists():
        return
    text = V1_PATH.read_text(encoding="utf-8")
    warning = ("# CIRCULAR — DO NOT USE. is_strong_earnings_spike here was thresholded directly off "
               "zscore_raw (zscore_raw>=5 AND near_earnings), so zscore_raw's AUC/Cohen's d against it "
               "is close to tautological. See IntentFiltered_GST_Results_v2.csv for the corrected "
               "comparison against an independent realized-price-move label.\n")
    if text.startswith("# CIRCULAR"):
        return  # already flagged
    V1_PATH.write_text(warning + text, encoding="utf-8")
    print(f"Flagged {V1_PATH} as circular (prepended warning line).")


def main():
    print(f"*** Intent-Filtered vs Raw GST Z-Score Comparison — v2, vs independent realized-move label ***\n")

    flag_v1_as_circular()

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
    intent_df = pd.concat(intent_frames, ignore_index=True)

    # --- Raw ticker z-score, already on disk ---
    raw = pd.read_csv(RAW_ZSCORE_PATH)
    raw["week"] = pd.to_datetime(raw["week"], errors="coerce")
    raw = raw[raw["ticker"].isin(TICKERS)].rename(
        columns={"gst": "gst_raw", "zscore_simple": "zscore_raw"})[["ticker", "week", "gst_raw", "zscore_raw"]]

    merged = pd.merge(intent_df, raw, on=["ticker", "week"], how="inner")
    print(f"Merged (ticker, week) rows with both z-score series present: {len(merged)}")

    # --- Independent ground-truth label: realized forward excess-return move, from daily price data only ---
    print(f"\nComputing realized forward ({FORWARD_WINDOW_DAYS}-day) excess-return move per (ticker, week), "
          f"from Daily Excess Return Data — no GST/z-score input involved...")
    daily_cache: dict[str, pd.DataFrame] = {t: load_daily_excess(t) for t in TICKERS}
    moves = []
    for _, row in merged.iterrows():
        daily = daily_cache[row["ticker"]]
        moves.append(realized_forward_move(daily, row["week"]) if not daily.empty else None)
    merged["realized_fwd_excess_move_pct"] = moves

    usable = merged["realized_fwd_excess_move_pct"].notna()
    print(f"Weeks with a usable realized-move window: {usable.sum()} / {len(merged)}")

    # Per-ticker top-decile cutoff, so a "spike" means unusual FOR THAT TICKER, not just high-vol ticker noise
    def label_group(g: pd.DataFrame) -> pd.Series:
        vals = g["realized_fwd_excess_move_pct"]
        cutoff = vals.quantile(SPIKE_PERCENTILE)
        return vals >= cutoff

    merged["is_realized_spike"] = False
    for ticker, idx in merged.groupby("ticker").groups.items():
        sub = merged.loc[idx]
        sub_usable = sub[sub["realized_fwd_excess_move_pct"].notna()]
        if sub_usable.empty:
            continue
        cutoff = sub_usable["realized_fwd_excess_move_pct"].quantile(SPIKE_PERCENTILE)
        merged.loc[sub_usable.index, "is_realized_spike"] = sub_usable["realized_fwd_excess_move_pct"] >= cutoff
        print(f"  [{ticker}] top-{int((1-SPIKE_PERCENTILE)*100)}% realized-move cutoff: "
              f"{cutoff:.2f}% abs move (n_usable={len(sub_usable)}, n_spike={int((sub_usable['realized_fwd_excess_move_pct'] >= cutoff).sum())})")

    out = merged.copy()
    out["week"] = out["week"].dt.date
    out = out.sort_values(["ticker", "week"]).reset_index(drop=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out)} (ticker, week) rows -> {OUT_PATH}")

    # --- Separation: realized-spike weeks vs everything else, raw z vs intent z ---
    labeled = merged[merged["realized_fwd_excess_move_pct"].notna()]
    spike_rows = labeled[labeled["is_realized_spike"]]
    nonspike_rows = labeled[~labeled["is_realized_spike"]]
    print(f"\nRealized-spike weeks (top decile per ticker): n={len(spike_rows)}")
    print(f"Non-spike weeks: n={len(nonspike_rows)}\n")

    results = {}
    for label, col in [("RAW_TICKER", "zscore_raw"), ("INTENT_FILTERED", "zscore_intent")]:
        s = spike_rows[col].dropna().to_numpy()
        ns = nonspike_rows[col].dropna().to_numpy()
        d = cohens_d(s, ns)
        auc = auc_separation(s, ns)
        results[label] = {"cohens_d": d, "auc": auc}
        print(f"=== {label} (column: {col}) ===")
        print(f"  n_spike={len(s)}  n_nonspike={len(ns)}")
        print(f"  mean z, realized-spike weeks:     {s.mean():+.3f}" if len(s) else "  mean z, realized-spike weeks: n/a")
        print(f"  mean z, non-spike weeks:          {ns.mean():+.3f}" if len(ns) else "  mean z, non-spike weeks: n/a")
        print(f"  Cohen's d:  {d:+.3f}" if d is not None else "  Cohen's d: n/a")
        print(f"  AUC (P(spike z > non-spike z)): {auc:.3f}" if auc is not None else "  AUC: n/a")
        print()

    raw_auc, intent_auc = results["RAW_TICKER"]["auc"], results["INTENT_FILTERED"]["auc"]
    raw_d, intent_d = results["RAW_TICKER"]["cohens_d"], results["INTENT_FILTERED"]["cohens_d"]

    print("=== VERDICT (vs independent realized-price-move label) ===")
    if raw_auc is not None and intent_auc is not None:
        auc_verdict = "TIE" if abs(raw_auc - intent_auc) < 0.005 else ("RAW_TICKER" if raw_auc > intent_auc else "INTENT_FILTERED")
        print(f"By AUC:         raw={raw_auc:.3f} vs intent={intent_auc:.3f} -> cleaner separation: {auc_verdict}")
    if raw_d is not None and intent_d is not None:
        d_verdict = "RAW_TICKER" if abs(raw_d) > abs(intent_d) else "INTENT_FILTERED"
        print(f"By |Cohen's d|: raw={raw_d:+.3f} vs intent={intent_d:+.3f} -> cleaner separation: {d_verdict}")
    print(f"\nNOTE: label = top {int((1-SPIKE_PERCENTILE)*100)}% of each ticker's own realized {FORWARD_WINDOW_DAYS}-day "
          f"forward |excess return|, computed purely from price data. Neither z-score series was used to build it.")
    print("v1 (IntentFiltered_GST_Results.csv) has been flagged as circular; use this file's results instead.")


if __name__ == "__main__":
    main()
