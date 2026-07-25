#!/usr/bin/env python3
# PRE-EARNINGS ATTENTION-PRESSURE TEST, COINTEGRATION VERSION -- redoes
# GST_PreEarningsPressure_Analysis.py (CHANGELOG.md, "pre-earnings
# attention-pressure test" entry: clean null result) replacing its naive
# 1:1 stock-minus-sector-ETF subtraction with a proper cointegration-based
# hedge ratio and equilibrium-deviation measure.
#
# METHOD, per event (spike_week = the GST signal date):
#   1. Estimation window: real daily closes (stock + its sector ETF),
#      STRICTLY BEFORE the signal date, at least 2 years (730 calendar
#      days) of history, min. 450 trading days required. Point-in-time
#      clean by construction -- the signal date's own price is never part
#      of the estimation sample, only the out-of-sample evaluation.
#   2. Engle-Granger cointegration test (statsmodels.tsa.stattools.coint)
#      on log(stock) vs log(ETF) over that window: regresses
#      log(stock) = alpha + beta*log(ETF) + resid, ADF-tests resid.
#      Cointegrated := p < 0.05. beta from this SAME regression is the
#      hedge ratio (no assumed 1:1).
#   3. Johansen trace test (coint_johansen) run as a secondary, independent
#      cross-check on the same window/pair -- reported alongside, not used
#      to gate anything, since Engle-Granger already supplies both the
#      test and the hedge ratio in one coherent step.
#   4. For pairs where Engle-Granger confirms cointegration: evaluate the
#      fitted (alpha, beta) OUT OF SAMPLE at the signal date's own close
#      -- deviation = log(stock) - (alpha + beta*log(ETF)) -- and
#      standardize by the estimation window's own residual std
#      (deviation_z), the standard stat-arb "spread z-score."
#   5. Same pressure-window (entry_date -> pre_earnings_date) and
#      earnings-day-window (pre_earnings_date -> exit_date) convention as
#      the original test, using the SAME entry_date/exit_date already
#      computed in FixedWindow_PerEvent_Canonical.csv, but now sourced
#      from a fresh real-price pull rather than the pre-built excess-
#      return files (needed anyway for the estimation window).
#
# Sector -> ETF map: identical to GST_PreEarningsPressure_Analysis.py
# (not tuned here either). Events whose sector has no ETF mapping are
# excluded the same way the original test excluded them.
#
# Output: Live Signal Engine/PreEarningsPressure_Cointegration_Test.csv

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
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "PreEarningsPressure_Cointegration_Test.csv"

SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Consumer Cyclical": "XLY",
    "Communication Services": "XLC",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financial Services": "XLF",
}

PULL_START, PULL_END = "2019-01-01", "2026-01-01"   # earliest spike_week (2021-03-21) minus >2yr, plus buffer
MIN_ESTIMATION_CALENDAR_DAYS = 730     # "at least 2 years prior" per spec
MIN_ESTIMATION_TRADING_DAYS = 450      # statistical-validity floor (~450/252 = ~1.8yr of ACTUAL trading obs)
EG_PVALUE_THRESHOLD = 0.05
JOHANSEN_CI_LEVEL_COL = 1               # statsmodels cvt columns are [90%, 95%, 99%]


def fetch_daily_close(symbol: str) -> pd.DataFrame:
    tk = yf.Ticker(symbol, session=YF_SESSION)
    df = tk.history(start=PULL_START, end=PULL_END, interval="1d", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "close", "ret"])
    out = pd.DataFrame({"Date": pd.to_datetime(df.index).tz_localize(None), "close": df["Close"].to_numpy()})
    out = out.sort_values("Date").drop_duplicates(subset="Date").reset_index(drop=True)
    out["ret"] = out["close"].pct_change()
    return out


def nearest_trading_day_on_or_after(daily: pd.DataFrame, target) -> pd.Timestamp | None:
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] >= target, "Date"]
    return eligible.min() if not eligible.empty else None


def window_return(daily: pd.DataFrame, start_date, end_date) -> float | None:
    if start_date is None or end_date is None or end_date <= start_date:
        return None
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, "ret"]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def cointegration_and_hedge_ratio(stock_est: pd.DataFrame, etf_est: pd.DataFrame) -> dict:
    """stock_est / etf_est: Date-aligned daily closes STRICTLY BEFORE the signal
    date, already merged 1:1 on Date. Returns EG + Johansen results and the
    fitted (alpha, beta, resid_std) needed to evaluate an out-of-sample deviation."""
    log_stock = np.log(stock_est["close"].to_numpy())
    log_etf = np.log(etf_est["close"].to_numpy())

    coint_t, pvalue, crit = coint(log_stock, log_etf, trend="c")

    # Same regression coint() runs internally (OLS, y=log_stock on x=log_etf,
    # with constant) -- re-derived explicitly here to recover alpha/beta/resid.
    X = np.column_stack([np.ones_like(log_etf), log_etf])
    (alpha, beta), _, _, _ = np.linalg.lstsq(X, log_stock, rcond=None)
    resid = log_stock - (alpha + beta * log_etf)
    resid_std = float(np.std(resid, ddof=2))

    johansen_cointegrated = None
    johansen_trace_stat = None
    johansen_crit_95 = None
    try:
        jres = coint_johansen(np.column_stack([log_stock, log_etf]), det_order=0, k_ar_diff=1)
        johansen_trace_stat = float(jres.lr1[0])
        johansen_crit_95 = float(jres.cvt[0, JOHANSEN_CI_LEVEL_COL])
        johansen_cointegrated = johansen_trace_stat > johansen_crit_95
    except Exception:
        pass   # Johansen is a secondary cross-check only; EG result still stands alone

    return {
        "eg_pvalue": float(pvalue), "eg_cointegrated": bool(pvalue < EG_PVALUE_THRESHOLD),
        "hedge_ratio_beta": float(beta), "alpha": float(alpha), "resid_std": resid_std,
        "n_estimation_obs": len(log_stock),
        "johansen_cointegrated": johansen_cointegrated,
        "johansen_trace_stat": johansen_trace_stat, "johansen_crit_95": johansen_crit_95,
    }


def main():
    print("*** PRE-EARNINGS ATTENTION-PRESSURE TEST -- COINTEGRATION VERSION (152-event canonical population) ***\n")

    canon = pd.read_csv(CANONICAL_PATH)
    canon["spike_week"] = pd.to_datetime(canon["spike_week"])
    canon["entry_date"] = pd.to_datetime(canon["entry_date"])
    canon["exit_date"] = pd.to_datetime(canon["exit_date"])
    qualifying = canon[(canon["qualifies_z5"] == True) & (canon["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Qualifying priced events: n={len(qualifying)}\n")

    sector_df = pd.read_csv(SECTOR_PATH)
    sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))

    tickers = sorted(qualifying["ticker"].unique())
    needed_etfs = sorted(set(SECTOR_ETF_MAP[sector_map[t]] for t in tickers if sector_map.get(t) in SECTOR_ETF_MAP))
    print(f"Tickers: {len(tickers)}   Sector ETFs needed: {needed_etfs}")
    print("Pulling fresh daily price history (yfinance, 2019-2025+ for a >=2yr pre-signal estimation window)...\n")

    price_cache: dict[str, pd.DataFrame] = {}
    for sym in tickers + needed_etfs:
        price_cache[sym] = fetch_daily_close(sym)
        print(f"  {sym}: {len(price_cache[sym])} daily rows")
        time.sleep(1.0)
    print()

    rows = []
    for r in qualifying.itertuples(index=False):
        ticker = r.ticker
        sector = sector_map.get(ticker)
        etf = SECTOR_ETF_MAP.get(sector)
        row = {
            "ticker": ticker, "spike_week": r.spike_week.date(), "sector": sector, "sector_etf": etf,
            "fixed_window_zscore": r.fixed_window_zscore,
            "eg_pvalue": None, "eg_cointegrated": None, "hedge_ratio_beta": None,
            "johansen_cointegrated": None, "n_estimation_obs": None,
            "deviation_at_signal": None, "deviation_z": None,
            "pressure_window_stock_return_pct": None, "earnings_day_move_pct": None, "note": "",
        }

        if etf is None:
            row["note"] = f"no ETF mapping for sector '{sector}'"
            rows.append(row)
            continue

        stock_all = price_cache.get(ticker, pd.DataFrame())
        etf_all = price_cache.get(etf, pd.DataFrame())
        if stock_all.empty or etf_all.empty:
            row["note"] = "missing price history for ticker or ETF"
            rows.append(row)
            continue

        signal_date = nearest_trading_day_on_or_after(stock_all, r.spike_week)
        if signal_date is None:
            row["note"] = "could not resolve a trading day at/after spike_week"
            rows.append(row)
            continue

        est_start = signal_date - timedelta(days=MIN_ESTIMATION_CALENDAR_DAYS)
        stock_est = stock_all[(stock_all["Date"] >= est_start) & (stock_all["Date"] < signal_date)]
        etf_est = etf_all[(etf_all["Date"] >= est_start) & (etf_all["Date"] < signal_date)]
        merged_est = pd.merge(stock_est[["Date", "close"]], etf_est[["Date", "close"]],
                               on="Date", suffixes=("_stock", "_etf")).dropna()

        if len(merged_est) < MIN_ESTIMATION_TRADING_DAYS:
            row["note"] = f"insufficient pre-signal estimation history (n={len(merged_est)} trading days, need >={MIN_ESTIMATION_TRADING_DAYS})"
            rows.append(row)
            continue

        stock_est_aligned = merged_est[["Date"]].assign(close=merged_est["close_stock"])
        etf_est_aligned = merged_est[["Date"]].assign(close=merged_est["close_etf"])
        eg = cointegration_and_hedge_ratio(stock_est_aligned, etf_est_aligned)
        row.update({
            "eg_pvalue": round(eg["eg_pvalue"], 4), "eg_cointegrated": eg["eg_cointegrated"],
            "hedge_ratio_beta": round(eg["hedge_ratio_beta"], 4),
            "johansen_cointegrated": eg["johansen_cointegrated"],
            "n_estimation_obs": eg["n_estimation_obs"],
        })

        if not eg["eg_cointegrated"]:
            row["note"] = "not cointegrated (Engle-Granger p >= 0.05) -- no hedge ratio applied, deviation not computed"
            rows.append(row)
            continue

        stock_signal_row = stock_all.loc[stock_all["Date"] == signal_date, "close"]
        etf_signal_row = etf_all.loc[etf_all["Date"] == signal_date, "close"]
        if stock_signal_row.empty or etf_signal_row.empty:
            row["note"] = "no aligned stock/ETF close on the resolved signal date"
            rows.append(row)
            continue

        log_stock_signal = np.log(float(stock_signal_row.iloc[0]))
        log_etf_signal = np.log(float(etf_signal_row.iloc[0]))
        deviation = log_stock_signal - (eg["alpha"] + eg["hedge_ratio_beta"] * log_etf_signal)
        deviation_z = deviation / eg["resid_std"] if eg["resid_std"] > 0 else None
        row["deviation_at_signal"] = round(deviation, 5)
        row["deviation_z"] = round(deviation_z, 3) if deviation_z is not None else None

        prior = stock_all.loc[stock_all["Date"] < r.exit_date, "Date"]
        pre_earnings_date = prior.max() if not prior.empty else None
        if pre_earnings_date is None or pre_earnings_date <= r.entry_date:
            row["note"] = "could not resolve a valid pre-earnings date; deviation computed, outcome windows unavailable"
            rows.append(row)
            continue

        pressure_ret = window_return(stock_all, r.entry_date, pre_earnings_date)
        earnings_day_move = window_return(stock_all, pre_earnings_date, r.exit_date)
        row["pressure_window_stock_return_pct"] = round(pressure_ret * 100, 3) if pressure_ret is not None else None
        row["earnings_day_move_pct"] = round(earnings_day_move * 100, 3) if earnings_day_move is not None else None

        rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    # ---- headline stat: how much of this approach even applies ----
    attempted = result_df[result_df["eg_pvalue"].notna()].copy()
    n_attempted = len(attempted)
    n_cointegrated = int(attempted["eg_cointegrated"].sum()) if n_attempted else 0
    print("=== COINTEGRATION COVERAGE ===")
    print(f"Events with a valid >=2yr pre-signal estimation window: {n_attempted} / {len(qualifying)}")
    print(f"Engle-Granger cointegrated (p<{EG_PVALUE_THRESHOLD}): {n_cointegrated} / {n_attempted} "
          f"({100 * n_cointegrated / n_attempted:.1f}%)" if n_attempted else "n/a")
    if n_attempted:
        joh = attempted["johansen_cointegrated"].dropna()
        if len(joh):
            agree = (attempted.loc[joh.index, "eg_cointegrated"] == joh).mean() * 100
            print(f"Johansen trace test agrees with Engle-Granger on cointegration status: {agree:.1f}% of pairs "
                  f"(cross-check only, not used to gate the deviation analysis below)")
    print()

    usable = result_df[result_df["deviation_at_signal"].notna()].copy()
    print(f"Cointegrated events with a usable deviation measure: n={len(usable)}\n")
    if usable.empty:
        print("No cointegrated pairs -- the deviation-based approach cannot be evaluated further on this population.")
        return

    print("=== DEVIATION FROM EQUILIBRIUM AT THE GST SIGNAL DATE ===")
    print(f"Mean deviation (log-price residual): {usable['deviation_at_signal'].mean():+.4f}")
    print(f"Median deviation: {usable['deviation_at_signal'].median():+.4f}")
    print(f"Mean deviation_z (residual std units): {usable['deviation_z'].mean():+.3f}")
    print(f"Median deviation_z: {usable['deviation_z'].median():+.3f}")
    print(f"Fraction with POSITIVE deviation (stock rich vs. its cointegrating relationship): "
          f"{(usable['deviation_at_signal'] > 0).mean() * 100:.1f}%\n")

    corr_z_dev_p = usable["fixed_window_zscore"].corr(usable["deviation_z"], method="pearson")
    corr_z_dev_s = usable["fixed_window_zscore"].corr(usable["deviation_z"], method="spearman")
    print("Does GST z-score magnitude coincide with equilibrium deviation magnitude?")
    print(f"  z-score vs. deviation_z: Pearson r={corr_z_dev_p:.3f}   Spearman rho={corr_z_dev_s:.3f}\n")

    usable_pressure = usable[usable["pressure_window_stock_return_pct"].notna()].copy()
    corr_pressure_p = usable_pressure["deviation_z"].corr(usable_pressure["pressure_window_stock_return_pct"], method="pearson")
    corr_pressure_s = usable_pressure["deviation_z"].corr(usable_pressure["pressure_window_stock_return_pct"], method="spearman")
    print(f"Does deviation at the signal date predict the pressure-window stock return? (n={len(usable_pressure)})")
    print(f"  deviation_z vs. pressure_window_stock_return_pct: Pearson r={corr_pressure_p:.3f}   "
          f"Spearman rho={corr_pressure_s:.3f}")
    if corr_pressure_p < -0.15:
        print("  -> Negative: some evidence of mean-reversion toward the cointegrating equilibrium "
              "during the pressure window.")
    elif corr_pressure_p > 0.15:
        print("  -> Positive: deviation tends to EXTEND (momentum away from equilibrium), not revert.")
    else:
        print("  -> Weak/no relationship.")
    print()

    usable_reversal = usable[usable["earnings_day_move_pct"].notna()].copy()
    corr_reversal_p = usable_reversal["deviation_z"].corr(usable_reversal["earnings_day_move_pct"], method="pearson")
    corr_reversal_s = usable_reversal["deviation_z"].corr(usable_reversal["earnings_day_move_pct"], method="spearman")
    print(f"Does deviation at the signal date predict the earnings-day move? (n={len(usable_reversal)})")
    print(f"  deviation_z vs. earnings_day_move_pct: Pearson r={corr_reversal_p:.3f}   "
          f"Spearman rho={corr_reversal_s:.3f}")
    if corr_reversal_p < -0.15:
        print("  -> Negative: some evidence deviation predicts a reversal/give-back on the earnings-day move.")
    elif corr_reversal_p > 0.15:
        print("  -> Positive: deviation tends to continue into the earnings-day move (momentum, not reversal).")
    else:
        print("  -> Weak/no relationship.")


if __name__ == "__main__":
    main()
