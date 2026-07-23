#!/usr/bin/env python3
# TASK 4 — Calendar-time portfolio simulation: arrange the canonical n=147
# z>=5 STRONG_EARNINGS events chronologically (by exit date, when P&L
# realizes) and simulate two position-sizing schemes against a single
# $100,000 starting bankroll, compared to SPY buy-and-hold.
#
# *** DISCLOSED METHODOLOGY CHOICES ***
# - Uses the spike_week exit horizon (entry=anchor+2, exit=anchor+6,
#   nearest trading day conventions) since the task explicitly frames this
#   as "the 147 events" -- the newer next_day exit rule only has n=138
#   usable events (some earnings dates precede entry), which would silently
#   drop 9 events from the stated population.
# - Flat sizing: $10,000 per trade, fixed.
# - Z-proportional sizing: $10,000 * (z / 5.0), capped at $50,000 -- $10k
#   floor anchored at the z=5 tier threshold (matches flat sizing's
#   baseline at the minimum qualifying z), scaling linearly above that.
# - Both portfolios share one $100,000 starting bankroll (sized comfortably
#   above the $50k single-position cap) purely as an accounting device to
#   compute monthly returns / Sharpe / drawdown -- this is NOT a margin or
#   concurrent-capital-constraint model; overlapping trades are not blocked.
# - SPY comparison: total dollar capital DEPLOYED (sum of position sizes,
#   which differs between the two sizing schemes) is invested in SPY
#   buy-and-hold over the same first-entry-to-last-exit window, for a
#   dollar-equivalent comparison.
#
# Output: Live Signal Engine/CalendarTimePortfolio_Results.csv

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

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "CalendarTimePortfolio_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
STARTING_CAPITAL = 100_000.0
FLAT_POSITION_SIZE = 10_000.0
ZPROP_FLOOR_Z = 5.0
ZPROP_BASE_SIZE = 10_000.0
ZPROP_CAP = 50_000.0


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


def max_drawdown(equity_curve: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - running_max) / running_max
    return float(drawdowns.min())


def longest_streak(is_win: np.ndarray, target: bool) -> int:
    best = cur = 0
    for w in is_win:
        if w == target:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def flag_negative_rolling_windows(monthly_pnl: pd.Series, window_months: int) -> list[str]:
    rolling_sum = monthly_pnl.rolling(window=window_months).sum()
    flagged = rolling_sum[rolling_sum < 0]
    return [str(idx) for idx in flagged.index]


def simulate_portfolio(trades: pd.DataFrame, size_col: str, label: str) -> dict:
    trades = trades.sort_values("exit_date").reset_index(drop=True)
    dollar_pnl = trades[size_col] * (trades["pnl_pct"] / 100.0)
    total_capital_deployed = float(trades[size_col].sum())

    equity = STARTING_CAPITAL + dollar_pnl.cumsum()
    equity_curve = np.concatenate([[STARTING_CAPITAL], equity.to_numpy()])
    mdd = max_drawdown(equity_curve)

    is_win = (trades["pnl_pct"] > 0).to_numpy()
    longest_win_streak = longest_streak(is_win, True)
    longest_loss_streak = longest_streak(is_win, False)

    trades = trades.copy()
    trades["month"] = trades["exit_date"].dt.to_period("M")
    trades["dollar_pnl"] = dollar_pnl
    monthly_pnl_series = trades.groupby("month")["dollar_pnl"].sum()
    full_month_range = pd.period_range(trades["month"].min(), trades["month"].max(), freq="M")
    monthly_pnl_series = monthly_pnl_series.reindex(full_month_range, fill_value=0.0)

    monthly_equity_start = STARTING_CAPITAL + monthly_pnl_series.cumsum().shift(1).fillna(0.0)
    monthly_return = monthly_pnl_series / monthly_equity_start

    mean_monthly_ret = float(monthly_return.mean())
    std_monthly_ret = float(monthly_return.std(ddof=1))
    sharpe_annualized = (mean_monthly_ret / std_monthly_ret * np.sqrt(12)) if std_monthly_ret > 0 else None

    neg_6mo = flag_negative_rolling_windows(monthly_pnl_series, 6)
    neg_12mo = flag_negative_rolling_windows(monthly_pnl_series, 12)

    final_equity = float(equity_curve[-1])
    total_return_pct = (final_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100

    print(f"=== {label} ===")
    print(f"n trades: {len(trades)}   total capital deployed: ${total_capital_deployed:,.0f}")
    print(f"Final equity: ${final_equity:,.0f}  (starting ${STARTING_CAPITAL:,.0f})  total return: {total_return_pct:+.1f}%")
    print(f"Total dollar P&L: ${dollar_pnl.sum():+,.0f}")
    print(f"Max drawdown: {mdd*100:.1f}%")
    print(f"Longest winning streak: {longest_win_streak} trades   Longest losing streak: {longest_loss_streak} trades")
    print(f"Annualized Sharpe (monthly returns, rf=0%): {sharpe_annualized:.2f}" if sharpe_annualized else "Sharpe: n/a")
    print(f"6-month rolling windows with negative cumulative P&L: {len(neg_6mo)} ({neg_6mo if neg_6mo else 'none'})")
    print(f"12-month rolling windows with negative cumulative P&L: {len(neg_12mo)} ({neg_12mo if neg_12mo else 'none'})")
    print()

    return {
        "portfolio": label, "n_trades": len(trades), "total_capital_deployed": round(total_capital_deployed, 0),
        "final_equity": round(final_equity, 0), "total_return_pct": round(total_return_pct, 2),
        "total_dollar_pnl": round(float(dollar_pnl.sum()), 0), "max_drawdown_pct": round(mdd * 100, 2),
        "longest_win_streak_trades": longest_win_streak, "longest_loss_streak_trades": longest_loss_streak,
        "sharpe_annualized": round(sharpe_annualized, 3) if sharpe_annualized else None,
        "n_negative_6mo_windows": len(neg_6mo), "n_negative_12mo_windows": len(neg_12mo),
        "first_exit": str(trades["exit_date"].min().date()), "last_exit": str(trades["exit_date"].max().date()),
    }


def simulate_spy_buyhold(daily_spy: pd.DataFrame, start_date, end_date, capital: float, label: str) -> dict:
    mask = (daily_spy["Date"] >= start_date) & (daily_spy["Date"] <= end_date)
    rets = daily_spy.loc[mask].sort_values("Date")
    cum_ret = float((1 + rets["SPY Daily Return"]).prod() - 1)
    final_equity = capital * (1 + cum_ret)

    rets = rets.copy()
    rets["month"] = rets["Date"].dt.to_period("M")
    monthly_ret = rets.groupby("month")["SPY Daily Return"].apply(lambda r: float((1 + r).prod() - 1))
    mean_m, std_m = float(monthly_ret.mean()), float(monthly_ret.std(ddof=1))
    sharpe = (mean_m / std_m * np.sqrt(12)) if std_m > 0 else None

    equity_curve = capital * (1 + rets["SPY Daily Return"]).cumprod()
    equity_curve = np.concatenate([[capital], equity_curve.to_numpy()])
    mdd = max_drawdown(equity_curve)

    print(f"=== {label} (SPY buy-and-hold, ${capital:,.0f} deployed, {start_date.date()} to {end_date.date()}) ===")
    print(f"Final equity: ${final_equity:,.0f}   total return: {cum_ret*100:+.1f}%")
    print(f"Max drawdown: {mdd*100:.1f}%   Annualized Sharpe: {sharpe:.2f}" if sharpe else "Sharpe: n/a")
    print()

    return {"portfolio": label, "total_capital_deployed": round(capital, 0), "final_equity": round(final_equity, 0),
            "total_return_pct": round(cum_ret * 100, 2), "max_drawdown_pct": round(mdd * 100, 2),
            "sharpe_annualized": round(sharpe, 3) if sharpe else None}


def main():
    print("*** TASK 4: Calendar-time portfolio simulation ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Canonical STRONG_EARNINGS events (z>={Z_THRESHOLD:g}, near_earnings): n={len(events)}\n")

    tickers = sorted(events["ticker"].unique())
    daily_cache = {t: load_daily_excess(t) for t in tickers}

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
        if entry_date is None or exit_date is None or exit_date <= entry_date:
            continue
        rows.append({"ticker": ticker, "spike_week": anchor, "zscore": zscore,
                      "entry_date": entry_date, "exit_date": exit_date,
                      "pnl_pct": ev["end_of_spike_week_pnl_pct"], "win": ev["end_of_spike_week_win"]})

    trades = pd.DataFrame(rows)
    print(f"Trades with valid entry/exit dates: n={len(trades)}\n")

    trades["flat_size"] = FLAT_POSITION_SIZE
    trades["zprop_size"] = (ZPROP_BASE_SIZE * (trades["zscore"] / ZPROP_FLOOR_Z)).clip(lower=ZPROP_BASE_SIZE, upper=ZPROP_CAP)

    result_flat = simulate_portfolio(trades, "flat_size", "PORTFOLIO A: Flat $10,000 sizing")
    result_zprop = simulate_portfolio(trades, "zprop_size", "PORTFOLIO B: Z-score-proportional sizing (floor $10k, cap $50k)")

    # SPY comparison -- build a deduplicated SPY daily return series across all cached ticker files
    spy_frames = [d[["Date", "SPY Daily Return"]] for d in daily_cache.values() if not d.empty and "SPY Daily Return" in d.columns]
    daily_spy = pd.concat(spy_frames, ignore_index=True).drop_duplicates(subset="Date").sort_values("Date").reset_index(drop=True)

    overall_start, overall_end = trades["entry_date"].min(), trades["exit_date"].max()
    result_spy_flat = simulate_spy_buyhold(daily_spy, overall_start, overall_end,
                                            result_flat["total_capital_deployed"],
                                            "SPY_equiv_flat")
    result_spy_zprop = simulate_spy_buyhold(daily_spy, overall_start, overall_end,
                                             result_zprop["total_capital_deployed"],
                                             "SPY_equiv_zprop")

    print("=== HEADLINE COMPARISON ===")
    print(f"{'Portfolio':<35} {'Return':>10} {'Sharpe':>8} {'MaxDD':>8}")
    for r in [result_flat, result_zprop, result_spy_flat, result_spy_zprop]:
        sharpe_str = f"{r['sharpe_annualized']:.2f}" if r.get("sharpe_annualized") is not None else "n/a"
        print(f"{r['portfolio']:<35} {r['total_return_pct']:>9.1f}% {sharpe_str:>8} {r['max_drawdown_pct']:>7.1f}%")

    result_df = pd.DataFrame([result_flat, result_zprop, result_spy_flat, result_spy_zprop])
    result_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
