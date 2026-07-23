#!/usr/bin/env python3
# STRESS TEST — realistic-cost sanity check on the STRONG_EARNINGS straddle
# backtest, ahead of trading MSFT live on 2026-07-29. Recomputes every
# canonical z>=5, near_earnings=True event (n=147, from
# Earnings-Adjacent Spike vs No-Spike Test/group_a_z4_earnings_adjacent.csv)
# fresh from on-disk daily price data, under three combined adverse
# execution-assumption adjustments,
# and compares against the ORIGINAL methodology (same entry/exit-day
# conventions, same Black-Scholes engine) recomputed identically so the
# only differences are the three stress adjustments below.
#
# *** ADJUSTMENT 1 — ENTRY IV INFLATED FOR PRE-EARNINGS IV CRUSH RISK ***
# This project has never had real historical quoted option IV (disclosed
# repeatedly elsewhere, e.g. GST_RelativeIV_SignalQuality_Test.py) — every
# "IV" here has always been trailing realized vol x a calibrated
# near-earnings markup (Earnings Clustering Test/iv_calibration_buckets.csv:
# mean=1.2398, std=0.2646, n=25). The ORIGINAL sim used the MEAN markup.
# This stress test swaps in MEAN + 1 STD (~1.50x realized vol instead of
# ~1.24x) as the entry IV multiplier — a worse-than-typical, empirically-
# grounded (not arbitrary) proxy for how much richer real pre-earnings IV
# can run versus what a realized-vol-based model assumes. Still a modeled
# proxy, not real market IV — same limitation as everywhere else in this
# project, just disclosed again here.
#
# *** ADJUSTMENT 2 — BID-ASK SPREAD, 5-8% OF PREMIUM, ENTRY AND EXIT ***
# Applied as: pay (1+spread) x fair value on entry (crossing the ask on
# both legs), receive (1-spread) x intrinsic value on exit (crossing the
# bid on both legs). Since no differential spread is specified between the
# call and put leg, applying spread% uniformly to each leg is arithmetically
# identical to applying it to the combined straddle premium — so legs are
# not modeled separately. Two scenarios run: 5% (low) and 8% (high) per the
# requested range.
#
# *** ADJUSTMENT 3 — 1-HOUR EXECUTION DELAY ***
# This project only has daily-resolution price data (disclosed — no
# intraday series exists anywhere on disk), so a literal intraday fill delay
# can't be replayed tick-by-tick. Modeled instead as an adverse-assumption
# slippage cost added directly to entry cost, sized as the stock's
# realized-vol-implied expected 1-hour move: hourly_std = daily_std /
# sqrt(6.5 trading hours), added in full (a full 1-sigma adverse move, not
# an average-case 0.5-sigma) since this is a combined adverse execution-
# assumption scenario, not an average-case estimate. This is
# a proxy, not a measurement of actual intraday slippage — disclosed as such.
#
# *** COST_LOADING NOT DOUBLE-COUNTED ***
# The original sim's flat COST_LOADING=1.05 (a blanket 5% one-time cost) is
# REPLACED, not stacked, by the explicit entry+exit bid-ask modeling here —
# 5-8% on each side is already a stricter superset of that flat 5% figure.
#
# Same entry/exit-day conventions as every other test in this project
# (entry = anchor+2 days, exit = anchor+6 days, nearest trading day
# on-or-before), and the same equity-curve / monthly-return Sharpe / max-
# drawdown methodology as GST_Task4_CalendarTimePortfolio.py (flat $10,000
# sizing), so the stress numbers are directly comparable to that existing
# output, not a new incompatible framework.
#
# Output: Live Signal Engine/StressTest_RealCost_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import math
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

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "StressTest_RealCost_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
ORIGINAL_COST_LOADING = 1.05

SPREAD_SCENARIOS = {"low": 0.05, "high": 0.08}
TRADING_HOURS_PER_DAY = 6.5
EXECUTION_DELAY_HOURS = 1.0

STARTING_CAPITAL = 100_000.0
FLAT_POSITION_SIZE = 10_000.0
FOCUS_TICKER = "MSFT"


def load_calibrated_markup_stats() -> tuple[float, float]:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0]), float(near_row["std"].iloc[0])


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def price_event(daily, ret_col, anchor, markup, spread_pct, apply_delay_slippage):
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if entry_date is None or exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None

    sigma_annual = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma_annual is None:
        return None

    iv = sigma_annual * markup
    T = dte_days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None

    if apply_delay_slippage:
        daily_std = sigma_annual / math.sqrt(252)
        hourly_std = daily_std / math.sqrt(TRADING_HOURS_PER_DAY)
        entry_slippage = hourly_std * EXECUTION_DELAY_HOURS * 100.0   # pct of $100 notional == $ amount
    else:
        entry_slippage = 0.0

    premium_before_spread = fair + entry_slippage
    entry_cost = premium_before_spread * (1 + spread_pct)

    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    exit_value = intrinsic * (1 - spread_pct)

    pnl_pct = (exit_value - entry_cost) / entry_cost * 100
    return {"entry_date": entry_date, "exit_date": exit_date, "pnl_pct": pnl_pct, "win": pnl_pct > 0}


def price_event_original(daily, ret_col, anchor, markup):
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if entry_date is None or exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma_annual = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma_annual is None:
        return None
    iv = sigma_annual * markup
    T = dte_days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * ORIGINAL_COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"entry_date": entry_date, "exit_date": exit_date, "pnl_pct": pnl_pct, "win": pnl_pct > 0}


def max_drawdown(equity_curve: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - running_max) / running_max
    return float(drawdowns.min())


def summarize_scenario(trades: pd.DataFrame, scenario: str, population: str) -> dict:
    trades = trades.sort_values("exit_date").reset_index(drop=True)
    n = len(trades)
    if n == 0:
        return {"scenario": scenario, "population": population, "n_trades": 0}

    win_rate = trades["win"].mean() * 100
    median_pnl = trades["pnl_pct"].median()
    mean_pnl = trades["pnl_pct"].mean()

    dollar_pnl = FLAT_POSITION_SIZE * (trades["pnl_pct"] / 100.0)
    equity = STARTING_CAPITAL + dollar_pnl.cumsum()
    equity_curve = np.concatenate([[STARTING_CAPITAL], equity.to_numpy()])
    mdd = max_drawdown(equity_curve)

    t = trades.copy()
    t["month"] = t["exit_date"].dt.to_period("M")
    t["dollar_pnl"] = dollar_pnl
    monthly_pnl = t.groupby("month")["dollar_pnl"].sum()
    full_range = pd.period_range(t["month"].min(), t["month"].max(), freq="M")
    monthly_pnl = monthly_pnl.reindex(full_range, fill_value=0.0)
    monthly_equity_start = STARTING_CAPITAL + monthly_pnl.cumsum().shift(1).fillna(0.0)
    monthly_return = monthly_pnl / monthly_equity_start
    mean_m, std_m = float(monthly_return.mean()), float(monthly_return.std(ddof=1))
    sharpe = (mean_m / std_m * np.sqrt(12)) if std_m > 0 else None

    return {
        "scenario": scenario, "population": population, "n_trades": n,
        "win_rate_pct": round(win_rate, 1), "median_pnl_pct": round(median_pnl, 1),
        "mean_pnl_pct": round(mean_pnl, 1), "max_drawdown_pct": round(mdd * 100, 2),
        "sharpe_annualized": round(sharpe, 3) if sharpe is not None else None,
        "final_equity": round(float(equity_curve[-1]), 0),
    }


def main():
    print("*** STRESS TEST: realistic-cost STRONG_EARNINGS backtest (pre-MSFT-live sanity check) ***\n")

    markup_mean, markup_std = load_calibrated_markup_stats()
    markup_stress = markup_mean + markup_std
    print(f"Calibrated near-earnings IV markup: mean={markup_mean:.4f}  std={markup_std:.4f}")
    print(f"ORIGINAL entry IV multiplier: {markup_mean:.4f}x realized vol")
    print(f"STRESS entry IV multiplier (mean+1std, 'IV crush risk'): {markup_stress:.4f}x realized vol\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"STRONG_EARNINGS events (z>={Z_THRESHOLD:g}, near_earnings): n={len(events)}\n")

    tickers = sorted(events["ticker"].unique())
    daily_cache = {t: load_daily_excess(t) for t in tickers}

    scenario_defs = {
        "ORIGINAL":            dict(markup=markup_mean,   spread=0.0,  delay=False),
        "IV_CRUSH_ONLY":       dict(markup=markup_stress, spread=0.0,  delay=False),
        "SPREAD_ONLY_5PCT":    dict(markup=markup_mean,   spread=0.05, delay=False),
        "SPREAD_ONLY_8PCT":    dict(markup=markup_mean,   spread=0.08, delay=False),
        "EXEC_DELAY_ONLY_1HR": dict(markup=markup_mean,   spread=0.0,  delay=True),
        "COMBINED_ADVERSE_LOW":  dict(markup=markup_stress, spread=0.05, delay=True),
        "COMBINED_ADVERSE_HIGH": dict(markup=markup_stress, spread=0.08, delay=True),
    }

    all_rows_by_scenario: dict[str, list[dict]] = {name: [] for name in scenario_defs}

    print("Recomputing all events under each scenario...")
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        for name, cfg in scenario_defs.items():
            if name == "ORIGINAL":
                res = price_event_original(daily, ret_col, anchor, cfg["markup"])
            else:
                res = price_event(daily, ret_col, anchor, cfg["markup"], cfg["spread"], cfg["delay"])
            if res is None:
                continue
            res["ticker"] = ticker
            res["spike_week"] = anchor
            all_rows_by_scenario[name].append(res)

    for name in scenario_defs:
        print(f"  [{name}] usable events: {len(all_rows_by_scenario[name])}")
    print()

    summary_rows = []
    detail_frames = []
    for name in scenario_defs:
        trades = pd.DataFrame(all_rows_by_scenario[name])
        if trades.empty:
            continue
        trades["scenario"] = name
        detail_frames.append(trades)

        full_summary = summarize_scenario(trades, name, "ALL_STRONG_EARNINGS")
        summary_rows.append(full_summary)

        msft_trades = trades[trades["ticker"] == FOCUS_TICKER]
        msft_summary = summarize_scenario(msft_trades, name, f"{FOCUS_TICKER}_ONLY")
        summary_rows.append(msft_summary)

    summary_df = pd.DataFrame(summary_rows)

    print("=== HEADLINE COMPARISON (ALL_STRONG_EARNINGS, n=147 population) ===")
    print(f"{'Scenario':<20} {'n':>4} {'Win%':>7} {'MedianPnL%':>11} {'Sharpe':>8} {'MaxDD%':>8}")
    for _, r in summary_df[summary_df["population"] == "ALL_STRONG_EARNINGS"].iterrows():
        sharpe_str = f"{r['sharpe_annualized']:.2f}" if pd.notna(r["sharpe_annualized"]) else "n/a"
        print(f"{r['scenario']:<20} {r['n_trades']:>4} {r['win_rate_pct']:>6.1f}% {r['median_pnl_pct']:>10.1f}% "
              f"{sharpe_str:>8} {r['max_drawdown_pct']:>7.1f}%")

    print(f"\n=== {FOCUS_TICKER}-ONLY COMPARISON (n={len(events[events['ticker']==FOCUS_TICKER])} historical events — small sample, directional only) ===")
    print(f"{'Scenario':<20} {'n':>4} {'Win%':>7} {'MedianPnL%':>11} {'Sharpe':>8} {'MaxDD%':>8}")
    for _, r in summary_df[summary_df["population"] == f"{FOCUS_TICKER}_ONLY"].iterrows():
        sharpe_str = f"{r['sharpe_annualized']:.2f}" if pd.notna(r["sharpe_annualized"]) else "n/a"
        print(f"{r['scenario']:<20} {r['n_trades']:>4} {r['win_rate_pct']:>6.1f}% {r['median_pnl_pct']:>10.1f}% "
              f"{sharpe_str:>8} {r['max_drawdown_pct']:>7.1f}%")

    orig = summary_df[(summary_df["scenario"] == "ORIGINAL") & (summary_df["population"] == "ALL_STRONG_EARNINGS")].iloc[0]
    stress_hi = summary_df[(summary_df["scenario"] == "COMBINED_ADVERSE_HIGH") & (summary_df["population"] == "ALL_STRONG_EARNINGS")].iloc[0]
    print(f"\n=== VERDICT ===")
    print(f"ORIGINAL:                win={orig['win_rate_pct']:.1f}%  median_pnl={orig['median_pnl_pct']:+.1f}%  "
          f"sharpe={orig['sharpe_annualized']}  maxDD={orig['max_drawdown_pct']:.1f}%")
    print(f"COMBINED_ADVERSE_HIGH:   win={stress_hi['win_rate_pct']:.1f}%  median_pnl={stress_hi['median_pnl_pct']:+.1f}%  "
          f"sharpe={stress_hi['sharpe_annualized']}  maxDD={stress_hi['max_drawdown_pct']:.1f}%")
    if stress_hi["median_pnl_pct"] > 0:
        print("=> Simulated profitability remains positive under the selected adverse execution assumptions "
              "(net positive median P&L at 8% spread + IV-crush + delay, combined).")
    else:
        print("=> Simulated profitability does NOT remain positive under the selected adverse execution assumptions "
              "(median P&L turns negative, combined) — reconsider position sizing/entry timing.")

    detail_df = pd.concat(detail_frames, ignore_index=True)
    detail_df["spike_week"] = detail_df["spike_week"].dt.date
    detail_df["entry_date"] = detail_df["entry_date"].dt.date
    detail_df["exit_date"] = detail_df["exit_date"].dt.date

    combined = pd.concat([summary_df, pd.DataFrame([{}]), detail_df], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
