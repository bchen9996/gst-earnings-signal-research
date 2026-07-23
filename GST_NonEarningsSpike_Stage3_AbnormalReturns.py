#!/usr/bin/env python3
# NON-EARNINGS SPIKE TEST -- STAGE 3: abnormal return / volatility /
# volume test on the CLEAN, unexplained non-earnings spikes that survived
# stages 1 (fixed-window re-verification) and 2 (contamination check).
#
# ANCHOR CONVENTION (disclosed, since there's no earnings-anchored entry/
# exit rule to reuse here): t0 = the LAST trading day of the spike week
# itself (nearest trading day on/before spike_week+6). next-day metrics
# use t0+1 trading day; 5-day-forward metrics use the 5 trading days
# from t0+1 through t0+5.
#
# METRICS per event, each compared against that ticker's OWN baseline
# (not an earnings baseline -- this is explicitly a different phenomenon):
#   - next-day |return|
#   - 5-day-forward |cumulative return|
#   - 5-day-forward realized volatility (std of the 5 daily returns,
#     annualized) -- distinct from the cumulative-return metric: captures
#     dispersion/choppiness even when net drift is small
#   - abnormal volume (next-day volume / that ticker's own trailing
#     60-day median volume) -- requires a fresh, small yfinance daily-
#     volume pull (this project's local daily-return files have no
#     volume column), fetched only for the clean survivor tickers
#
# BASELINE: for each ticker, the SAME metrics computed across ALL trading
# days in its 2021-2025 history, EXCLUDING any day within 10 calendar
# days of an earnings date or any of the 72 candidate spike weeks (so the
# baseline isn't contaminated by the very effects being tested against
# it) -- an unconditional, disclosed "normal" reference distribution.
#
# STATS: mean/median deviation from baseline per metric, cluster
# bootstrap (resample whole TICKERS, not individual events -- several
# tickers contribute multiple events) for a 95% CI, Cohen's d for the
# return-magnitude metrics, compared directly against the already-
# established earnings-adjacent effect size (d=1.294, STRATEGY_SPEC_v1.0_
# TERMINOLOGY.md section 3).
#
# Output: Live Signal Engine/NonEarningsSpike_Stage3_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

import GST_FixedWindow_PerEvent_Canonical as base

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

STAGE1_PATH = Path("Live Signal Engine") / "NonEarningsSpike_Stage1_Verified.csv"
STAGE2_PATH = Path("Live Signal Engine") / "NonEarningsSpike_Stage2_Contamination.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "NonEarningsSpike_Stage3_Results.csv"

EARNINGS_ADJACENT_COHENS_D = 1.294   # established finding, STRATEGY_SPEC_v1.0_TERMINOLOGY.md section 3
EARNINGS_ADJACENT_MEAN_MOVE = 7.72   # % , same source
BASELINE_EXCLUSION_BUFFER_DAYS = 10
VOLUME_TRAILING_WINDOW = 60
N_BOOTSTRAP = 10000
RANDOM_SEED = 42


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = len(a), len(b)
    pooled_std = np.sqrt(((na - 1) * a.std(ddof=1) ** 2 + (nb - 1) * b.std(ddof=1) ** 2) / (na + nb - 2))
    return float((a.mean() - b.mean()) / pooled_std) if pooled_std > 0 else None


def cluster_bootstrap_ci(event_df: pd.DataFrame, value_col: str, n_boot: int, rng: np.random.RandomState) -> tuple:
    tickers = event_df["ticker"].unique()
    boot_means = np.empty(n_boot)
    grouped = {t: event_df.loc[event_df["ticker"] == t, value_col].to_numpy() for t in tickers}
    for i in range(n_boot):
        sampled_tickers = rng.choice(tickers, size=len(tickers), replace=True)
        vals = np.concatenate([grouped[t] for t in sampled_tickers if len(grouped[t]) > 0])
        boot_means[i] = vals.mean() if len(vals) else np.nan
    return float(np.nanpercentile(boot_means, 2.5)), float(np.nanpercentile(boot_means, 97.5))


def fetch_volume_series(ticker: str) -> pd.DataFrame:
    tk = yf.Ticker(ticker, session=YF_SESSION)
    df = tk.history(start="2021-01-01", end="2026-01-01", interval="1d", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Volume"])
    out = pd.DataFrame({"Date": pd.to_datetime(df.index).tz_localize(None), "Volume": df["Volume"].to_numpy()})
    return out.sort_values("Date").reset_index(drop=True)


def main():
    print("*** NON-EARNINGS SPIKE TEST -- STAGE 3: abnormal return/volatility/volume ***\n")

    stage2 = pd.read_csv(STAGE2_PATH)
    stage2["spike_week"] = pd.to_datetime(stage2["spike_week"])
    clean = stage2[stage2["classification"] == "CLEAN"].copy()
    print(f"Clean, unexplained non-earnings spikes: n={len(clean)}\n")
    if clean.empty:
        print("No clean events -- nothing to test. Stopping.")
        return

    earn = pd.read_csv(EARNINGS_PATH)
    earn["earnings_date"] = pd.to_datetime(earn["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earn.groupby("ticker")}

    all_spike_weeks_by_ticker = clean.groupby("ticker")["spike_week"].apply(list).to_dict()

    tickers = sorted(clean["ticker"].unique())
    print(f"Pulling fresh daily volume history for {len(tickers)} survivor tickers...")
    volume_cache = {}
    for t in tickers:
        volume_cache[t] = fetch_volume_series(t)
        time.sleep(0.2)
    print()

    daily_cache = {t: base.load_daily_excess(t) for t in tickers}

    def is_excluded(ticker, date):
        for ed in earnings_by_ticker.get(ticker, []):
            if abs((date - ed).days) <= BASELINE_EXCLUSION_BUFFER_DAYS:
                return True
        for sw in all_spike_weeks_by_ticker.get(ticker, []):
            if abs((date - sw).days) <= BASELINE_EXCLUSION_BUFFER_DAYS:
                return True
        return False

    def compute_metrics_at(daily, ret_col, t0):
        next_day_rows = daily.loc[daily["Date"] > t0, "Date"]
        if len(next_day_rows) < 5:
            return None
        next_5 = next_day_rows.iloc[:5]
        next_day_ret = daily.loc[daily["Date"] == next_5.iloc[0], ret_col]
        if next_day_ret.empty:
            return None
        next_day_abs = abs(float(next_day_ret.iloc[0]))
        five_day_abs = abs(base.cumulative_return(daily, ret_col, t0, next_5.iloc[-1]))
        five_day_rets = daily.loc[daily["Date"].isin(next_5), ret_col]
        five_day_vol = float(five_day_rets.std() * np.sqrt(252)) if len(five_day_rets) >= 2 else None
        return {"next_day_abs_return_pct": next_day_abs * 100,
                "five_day_abs_return_pct": five_day_abs * 100 if five_day_abs is not None else None,
                "five_day_realized_vol_pct": five_day_vol * 100 if five_day_vol is not None else None,
                "t0": t0, "next_day_date": next_5.iloc[0]}

    def compute_volume_ratio(ticker, next_day_date):
        vol_df = volume_cache.get(ticker, pd.DataFrame())
        if vol_df.empty:
            return None
        trailing = vol_df.loc[vol_df["Date"] < next_day_date].tail(VOLUME_TRAILING_WINDOW)
        if len(trailing) < 20:
            return None
        baseline_vol = trailing["Volume"].median()
        next_day_vol_row = vol_df.loc[vol_df["Date"] == next_day_date, "Volume"]
        if next_day_vol_row.empty or baseline_vol == 0:
            return None
        return float(next_day_vol_row.iloc[0] / baseline_vol)

    event_rows = []
    for _, ev in clean.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["fixed_window_zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        t0 = base.nearest_trading_day_on_or_before(daily, anchor + timedelta(days=6))
        if t0 is None:
            continue
        metrics = compute_metrics_at(daily, ret_col, t0)
        if metrics is None:
            continue
        vol_ratio = compute_volume_ratio(ticker, metrics["next_day_date"])
        event_rows.append({"ticker": ticker, "spike_week": anchor.date(), "fixed_window_zscore": zscore,
                            "t0": t0.date(), **{k: v for k, v in metrics.items() if k not in ("t0",)},
                            "volume_ratio_vs_60d_median": vol_ratio})

    event_df = pd.DataFrame(event_rows)
    event_df["next_day_date"] = pd.to_datetime(event_df["next_day_date"])
    print(f"Events with computable forward metrics: n={len(event_df)}\n")

    # ---------------------------------------------------------------------
    # BASELINE: unconditional, per-ticker, excluding windows around
    # earnings dates and any of the 72 candidate spike weeks.
    # ---------------------------------------------------------------------
    print("Building per-ticker baseline distributions (all trading days, spike/earnings windows excluded)...")
    baseline_rows = []
    for ticker in tickers:
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        candidate_days = daily["Date"].tolist()
        for d in candidate_days:
            if is_excluded(ticker, d):
                continue
            metrics = compute_metrics_at(daily, ret_col, d)
            if metrics is None:
                continue
            vol_ratio = compute_volume_ratio(ticker, metrics["next_day_date"])
            baseline_rows.append({"ticker": ticker, "next_day_abs_return_pct": metrics["next_day_abs_return_pct"],
                                   "five_day_abs_return_pct": metrics["five_day_abs_return_pct"],
                                   "five_day_realized_vol_pct": metrics["five_day_realized_vol_pct"],
                                   "volume_ratio_vs_60d_median": vol_ratio})
    baseline_df = pd.DataFrame(baseline_rows)
    print(f"Baseline reference days: n={len(baseline_df)}\n")

    baseline_df.to_csv(Path("Live Signal Engine") / "NonEarningsSpike_Baseline_Reference.csv", index=False)
    event_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    rng = np.random.RandomState(RANDOM_SEED)
    print("=== RESULTS ===")
    for metric, label in [("next_day_abs_return_pct", "Next-day |return|"),
                           ("five_day_abs_return_pct", "5-day-forward |cumulative return|"),
                           ("five_day_realized_vol_pct", "5-day-forward realized volatility (annualized)"),
                           ("volume_ratio_vs_60d_median", "Volume ratio vs. 60-day trailing median")]:
        ev_vals = event_df[metric].dropna()
        base_vals = baseline_df[metric].dropna()
        if ev_vals.empty or base_vals.empty:
            print(f"{label}: insufficient data")
            continue
        ci_lo, ci_hi = cluster_bootstrap_ci(event_df.dropna(subset=[metric]), metric, N_BOOTSTRAP, rng)
        d = cohens_d(ev_vals.to_numpy(), base_vals.to_numpy())
        print(f"\n{label}:")
        print(f"  Spike events (n={len(ev_vals)}): mean={ev_vals.mean():.3f}, median={ev_vals.median():.3f}")
        print(f"  Baseline (n={len(base_vals)}):    mean={base_vals.mean():.3f}, median={base_vals.median():.3f}")
        print(f"  95% cluster-bootstrap CI on spike-event mean (by ticker): [{ci_lo:.3f}, {ci_hi:.3f}]")
        print(f"  Cohen's d (spike vs. baseline): {d:.3f}" if d is not None else "  Cohen's d: n/a")

    print(f"\n=== COMPARISON TO THE VALIDATED EARNINGS-ADJACENT EFFECT ===")
    print(f"Earnings-adjacent (established): mean move 7.72% vs. 3.72% baseline, Cohen's d=1.294 (n=147)")
    ev_5day = event_df["five_day_abs_return_pct"].dropna()
    base_5day = baseline_df["five_day_abs_return_pct"].dropna()
    if not ev_5day.empty and not base_5day.empty:
        d_nonearnings = cohens_d(ev_5day.to_numpy(), base_5day.to_numpy())
        print(f"Non-earnings (this test): mean move {ev_5day.mean():.2f}% vs. {base_5day.mean():.2f}% baseline, "
              f"Cohen's d={d_nonearnings:.3f} (n={len(ev_5day)})")
        if d_nonearnings is not None:
            print(f"Relative effect size: non-earnings d is "
                  f"{d_nonearnings/EARNINGS_ADJACENT_COHENS_D*100:.0f}% of the earnings-adjacent effect")


if __name__ == "__main__":
    main()
