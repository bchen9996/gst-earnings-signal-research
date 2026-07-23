#!/usr/bin/env python3
# Abnormal GST Residual Signal — does GST search volume that's NOT
# explained by normal market activity (price return, volume, seasonality)
# carry a cleaner STRONG_EARNINGS signal than raw GST z-scores? All
# on-disk data, no new pulls.
#
# Per ticker, OLS regression:
#   GST_weekly_value ~ prior_week_price_return + prior_week_volume_ratio + week_of_year_dummies
# using PRIOR week's return/volume specifically to avoid endogeneity (this
# week's own price move partly reflects the same earnings event the signal
# is trying to predict, so it can't be a control for this week's GST).
# volume_ratio = that week's volume / trailing 52-week average volume
# (strictly prior weeks, no look-ahead in the denominator either).
# Fit via numpy least squares (statsmodels not installed in this
# environment) — R² computed manually as 1 - SS_res/SS_tot.
#
# *** WEEK-OF-YEAR DUMMY SPARSITY — DISCLOSED, NOT HIDDEN ***
# 52 week-of-year categories + 2 continuous predictors = 54 parameters,
# fit on ~200-210 usable weeks per ticker after dropping the first ~52
# weeks needed to build the trailing 52-week volume average. That's a
# tight, likely-overfit ~4:1 observation-to-parameter ratio — R² for many
# tickers may be inflated by fitting noise in individual week-of-year bins
# rather than genuine seasonality. Implemented exactly as specified
# (week-of-year, not month, which would be less sparse) since that's what
# was asked; flagged here rather than silently substituted.
#
# *** EARNINGS-ADJACENCY COVERAGE — A REAL, DISCLOSED LIMITATION ***
# Reclassifying residual-z>=5 weeks as STRONG_EARNINGS requires knowing
# whether EACH such week is within 5 days of an earnings date. No raw
# per-ticker earnings-date list has ever been persisted to disk in this
# project (repeatedly confirmed in earlier sessions) — only two pre-built,
# CURATED sets of (ticker, anchor)->nearest_earnings_gap_days flags exist:
# the original z>=2 raw-GST spike weeks, and a random baseline sample
# (Earnings Clustering Test (2021-2025)*/*_earnings_flags.csv, 4 files
# total: original-15 + Broad50-clear-36, spike + baseline). Since residual
# z-scores identify a DIFFERENT set of weeks than raw GST z-scores, many
# residual-z>=5 weeks will NOT coincide with either pre-flagged set, and
# for those weeks earnings-adjacency is genuinely UNKNOWN from existing
# data — they are excluded from the final classification and counted
# separately, not guessed.
#
# Output: Live Signal Engine/AbnormalGST_Residual_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import numpy as np
import pandas as pd

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
YEARS = list(range(2021, 2026))

WEEKLY_GST_DIRS = {t: Path("GST Data/Weekly Data (2021-2025)") for t in TICKERS_ORIGINAL}
WEEKLY_GST_DIRS.update({t: Path("GST Data/Weekly Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

VOLUME_DIR = Path("Daily Volume Data (2021-2025)")

EARNINGS_FLAGS_PATHS = [
    Path("Earnings Clustering Test (2021-2025)") / "spike_event_earnings_flags.csv",
    Path("Earnings Clustering Test (2021-2025)") / "baseline_event_earnings_flags.csv",
    Path("Earnings Clustering Test (2021-2025 Broad50 Clear)") / "spike_event_earnings_flags.csv",
    Path("Earnings Clustering Test (2021-2025 Broad50 Clear)") / "baseline_event_earnings_flags.csv",
]

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "AbnormalGST_Residual_Results.csv"

ROLLING_WINDOW = 12
MIN_PERIODS = 8
VOLUME_ROLLING_WEEKS = 52
MIN_VOLUME_HISTORY_WEEKS = 26
Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
MIN_R2_FLAG = 0.1
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

REAL_WIN_RATE_PCT = 76.2
REAL_MEDIAN_PNL_PCT = 130.0


def week_start(d: pd.Series) -> pd.Series:
    """Sunday of the week containing date d (matches GST's own week-labeling convention)."""
    d = pd.to_datetime(d)
    return d - pd.to_timedelta((d.dt.weekday + 1) % 7, unit="D")


def load_weekly_gst(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = WEEKLY_GST_DIRS[ticker] / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Week" not in df.columns or ticker not in df.columns:
            continue
        df = df.rename(columns={ticker: "gst"})[["Week", "gst"]]
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        frames.append(df.dropna(subset=["Week"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Week").reset_index(drop=True)


def load_weekly_price_and_volume(ticker: str) -> pd.DataFrame:
    ret_frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        ret_col = f"{ticker} Daily Return"
        if "Date" not in df.columns or ret_col not in df.columns:
            continue
        df = df.rename(columns={ret_col: "ret"})[["Date", "ret"]]
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        ret_frames.append(df.dropna(subset=["Date"]))
    if not ret_frames:
        return pd.DataFrame()
    daily_ret = pd.concat(ret_frames, ignore_index=True).sort_values("Date").reset_index(drop=True)

    vol_path = VOLUME_DIR / f"{ticker}_volume.csv"
    if not vol_path.exists():
        return pd.DataFrame()
    daily_vol = pd.read_csv(vol_path)
    daily_vol["Date"] = pd.to_datetime(daily_vol["Date"], errors="coerce")

    daily = pd.merge(daily_ret, daily_vol, on="Date", how="inner").dropna()
    if daily.empty:
        return pd.DataFrame()

    daily["week"] = week_start(daily["Date"])
    weekly = daily.groupby("week").agg(
        weekly_return=("ret", lambda x: float(np.prod(1 + x) - 1)),
        weekly_volume=("Volume", "sum"),
    ).reset_index()
    return weekly.sort_values("week").reset_index(drop=True)


def build_earnings_lookup() -> dict:
    frames = []
    for p in EARNINGS_FLAGS_PATHS:
        if p.exists():
            f = pd.read_csv(p)
            f["anchor"] = pd.to_datetime(f["anchor"]).dt.date.astype(str)
            frames.append(f)
    combined = pd.concat(frames, ignore_index=True)
    return {(r["ticker"], r["anchor"]): bool(r["within_5d"]) for _, r in combined.iterrows()}


def fit_ols_and_residuals(merged: pd.DataFrame) -> tuple[pd.DataFrame | None, float, int]:
    """merged has columns: Week, gst, prior_return, prior_vol_ratio, week_of_year (1-52).
    Returns (df with residual column, R^2, n_obs) or (None, nan, n) if unfittable."""
    df = merged.dropna(subset=["gst", "prior_return", "prior_vol_ratio"]).copy()
    n = len(df)
    if n < 60:   # need enough rows for 54 parameters to even be identified
        return None, np.nan, n

    df = df.reset_index(drop=True)
    dummies = pd.get_dummies(df["week_of_year"], prefix="woy", drop_first=True).astype(float).to_numpy()
    const = np.ones((n, 1))
    continuous = df[["prior_return", "prior_vol_ratio"]].to_numpy(dtype=float)
    X = np.hstack([const, continuous, dummies])
    y = df["gst"].to_numpy(dtype=float)

    try:
        coef, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return None, np.nan, n

    y_pred = X @ coef
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    df["residual"] = y - y_pred
    return df[["Week", "residual"]], r2, n


def compute_rolling_zscore(series: pd.Series) -> pd.Series:
    rolling = series.shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    z = (series - rolling.mean()) / rolling.std()
    return z.replace([np.inf, -np.inf], np.nan)


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None, None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b])
    n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(diff) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm, a.mean(), b.mean()


def main():
    print("*** Abnormal GST Residual Signal ***\n")

    earnings_lookup = build_earnings_lookup()
    print(f"Earnings-adjacency lookup built from existing flagged data: {len(earnings_lookup)} (ticker, week) pairs "
          f"covered — ONLY these can be classified; residual-z>=5 weeks outside this set are excluded, not guessed.\n")

    all_events_rows = []
    ticker_diagnostics = []

    for ticker in ALL_TICKERS:
        gst = load_weekly_gst(ticker)
        pv = load_weekly_price_and_volume(ticker)
        if gst.empty or pv.empty:
            ticker_diagnostics.append({"ticker": ticker, "status": "missing_data", "n_obs": 0, "r2": None})
            continue

        pv = pv.sort_values("week").reset_index(drop=True)
        pv["vol_roll_avg"] = pv["weekly_volume"].shift(1).rolling(
            window=VOLUME_ROLLING_WEEKS, min_periods=MIN_VOLUME_HISTORY_WEEKS).mean()
        pv["vol_ratio"] = pv["weekly_volume"] / pv["vol_roll_avg"]

        merged = gst.merge(pv, left_on="Week", right_on="week", how="left")
        merged["prior_return"] = merged["weekly_return"].shift(1)
        merged["prior_vol_ratio"] = merged["vol_ratio"].shift(1)
        merged["week_of_year"] = merged["Week"].dt.isocalendar().week.astype(int).clip(upper=52)

        resid_df, r2, n_obs = fit_ols_and_residuals(merged)
        if resid_df is None:
            ticker_diagnostics.append({"ticker": ticker, "status": "insufficient_data", "n_obs": n_obs, "r2": r2})
            continue

        full = merged.merge(resid_df, on="Week", how="left").sort_values("Week").reset_index(drop=True)
        full["residual_z"] = compute_rolling_zscore(full["residual"])

        flagged_poor_fit = r2 < MIN_R2_FLAG
        ticker_diagnostics.append({
            "ticker": ticker, "status": "ok", "n_obs": n_obs, "r2": round(r2, 4),
            "poor_fit_r2_lt_0.1": flagged_poor_fit,
        })

        for _, row in full.iterrows():
            if pd.isna(row["residual_z"]) or row["residual_z"] < Z_THRESHOLD:
                continue
            week_str = row["Week"].date().isoformat()
            key = (ticker, week_str)
            if key not in earnings_lookup:
                all_events_rows.append({
                    "ticker": ticker, "week": week_str, "residual_z": round(float(row["residual_z"]), 3),
                    "earnings_status": "unknown_not_in_flagged_data",
                })
                continue
            near_earnings = earnings_lookup[key]
            all_events_rows.append({
                "ticker": ticker, "week": week_str, "residual_z": round(float(row["residual_z"]), 3),
                "earnings_status": "near_earnings" if near_earnings else "not_near_earnings",
            })

        print(f"[{ticker}] n_obs={n_obs} R2={r2:.3f}{'  [POOR FIT R2<0.1]' if flagged_poor_fit else ''}")

    diagnostics_df = pd.DataFrame(ticker_diagnostics)
    residual_events_df = pd.DataFrame(all_events_rows)

    print(f"\n{'='*70}")
    print(f"Tickers with usable regression: {(diagnostics_df['status']=='ok').sum()}/{len(ALL_TICKERS)}")
    n_poor_fit = diagnostics_df.get("poor_fit_r2_lt_0.1", pd.Series(dtype=bool)).sum()
    print(f"Tickers flagged POOR FIT (R2<{MIN_R2_FLAG}): {n_poor_fit}")
    if n_poor_fit:
        print("  " + ", ".join(diagnostics_df[diagnostics_df.get('poor_fit_r2_lt_0.1', False) == True]['ticker'].tolist()))  # noqa: E712
    n_missing = (diagnostics_df["status"] != "ok").sum()
    if n_missing:
        print(f"Tickers excluded (missing/insufficient data): {n_missing} — "
              + ", ".join(diagnostics_df[diagnostics_df['status'] != 'ok']['ticker'].tolist()))

    print(f"\nResidual-z>=5 candidate weeks found: {len(residual_events_df)}")
    if not residual_events_df.empty:
        print(residual_events_df["earnings_status"].value_counts().to_string())

    residual_strong_earnings = residual_events_df[residual_events_df["earnings_status"] == "near_earnings"] if not residual_events_df.empty else pd.DataFrame()

    # --- Reclassification comparison against original z>=5 near-earnings STRONG_EARNINGS set ---
    original = pd.read_csv(GROUP_A_PATH)
    original = original[original["zscore"] >= Z_THRESHOLD].copy()
    original["week"] = pd.to_datetime(original["spike_week"]).dt.date.astype(str)
    original_keys = set(zip(original["ticker"], original["week"]))
    residual_keys = set(zip(residual_strong_earnings["ticker"], residual_strong_earnings["week"])) if not residual_strong_earnings.empty else set()

    lost = original_keys - residual_keys
    gained = residual_keys - original_keys
    retained = original_keys & residual_keys

    print(f"\n=== RECLASSIFICATION vs original z>=5 STRONG_EARNINGS (n={len(original_keys)}) ===")
    print(f"Retained (both raw-GST AND residual flag it): {len(retained)}")
    print(f"Lost (raw-GST flagged, residual does NOT): {len(lost)}")
    print(f"Gained (residual flags, raw-GST did NOT): {len(gained)}")

    # --- Win rate / median P&L for residual-based STRONG_EARNINGS, using existing pricing for RETAINED events only ---
    # (gained events have no pre-computed straddle pricing on disk — reusing pricing requires the event to already
    # exist in the priced dataset; this is disclosed, not silently worked around with a new simulation run.)
    retained_df = original[original.apply(lambda r: (r["ticker"], r["week"]) in retained, axis=1)]
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"
    retained_usable = retained_df[retained_df[win_col].notna()]

    print(f"\n=== ECONOMICS: retained residual-confirmed events (n={len(retained_usable)}), reusing existing pricing ===")
    if len(retained_usable):
        r_win = retained_usable[win_col].mean() * 100
        r_med = retained_usable[pnl_col].median()
        r_avg = retained_usable[pnl_col].mean()
        print(f"win={r_win:.1f}%  avg={r_avg:+.1f}%  median={r_med:+.1f}%")
        print(f"vs baseline: win={REAL_WIN_RATE_PCT}%  median={REAL_MEDIAN_PNL_PCT:+.1f}%")
        if r_win > REAL_WIN_RATE_PCT and r_med > REAL_MEDIAN_PNL_PCT:
            verdict = "IMPROVES on the raw z-score baseline"
        elif abs(r_win - REAL_WIN_RATE_PCT) < 2 and abs(r_med - REAL_MEDIAN_PNL_PCT) < 10:
            verdict = "roughly MATCHES the raw z-score baseline"
        else:
            verdict = "WEAKENS relative to the raw z-score baseline"
        print(f"=> Residual approach {verdict}.")
    else:
        print("No usable retained events with pricing data.")
        r_win = r_med = r_avg = None

    # Save outputs
    diagnostics_df.to_csv(OUT_PATH, index=False)
    residual_events_out = Path("Live Signal Engine") / "AbnormalGST_Residual_Events.csv"
    residual_events_df.to_csv(residual_events_out, index=False)
    print(f"\nWrote ticker diagnostics to: {OUT_PATH}")
    print(f"Wrote residual event detail to: {residual_events_out}")


if __name__ == "__main__":
    main()
