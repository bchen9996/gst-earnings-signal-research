#!/usr/bin/env python3
# CONCENTRATION AND DEPENDENCE AUDIT — 147 STRONG_EARNINGS events. Checks
# how much of the headline result rides on a small number of extreme
# events/tickers, and whether the standard event-level bootstrap CI
# understates uncertainty by ignoring within-ticker and within-quarter
# correlation (the same 147 events are NOT 147 independent draws -- many
# come from the same 28 tickers and cluster in the same earnings seasons).
#
# All on-disk data, no new pulls: reuses Earnings-Adjacent Spike vs
# No-Spike Test/group_a_z4_earnings_adjacent.csv (already-computed
# win/pnl_pct) and Daily Excess Return Data*/ (for entry/exit dates used
# only to order the equity curve for Sharpe -- same methodology as
# GST_Task4_CalendarTimePortfolio.py, flat $10,000 sizing).
#
# Output: Live Signal Engine/ConcentrationDependence_Audit.csv

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
YEARS = list(range(2021, 2026))
DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "ConcentrationDependence_Audit.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
FLAT_POSITION_SIZE = 10_000.0
STARTING_CAPITAL = 100_000.0

MEGA_CAP_TECH = ["MSFT", "AAPL", "GOOGL", "AMZN", "META", "NVDA"]

N_BOOTSTRAP = 10000
RANDOM_SEED = 42


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or df.empty:
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
    return float(((equity_curve - running_max) / running_max).min())


def compute_win_median_sharpe(trades: pd.DataFrame) -> dict:
    """trades needs columns: pnl_pct, win, exit_date (datetime)."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate_pct": None, "median_pnl_pct": None, "sharpe_annualized": None, "max_drawdown_pct": None}
    trades = trades.sort_values("exit_date").reset_index(drop=True)
    win_rate = trades["win"].mean() * 100
    median_pnl = trades["pnl_pct"].median()

    dollar_pnl = FLAT_POSITION_SIZE * (trades["pnl_pct"] / 100.0)
    equity = STARTING_CAPITAL + dollar_pnl.cumsum()
    equity_curve = np.concatenate([[STARTING_CAPITAL], equity.to_numpy()])
    mdd = max_drawdown(equity_curve)

    t = trades.copy()
    t["month"] = t["exit_date"].dt.to_period("M")
    t["dollar_pnl"] = dollar_pnl
    monthly = t.groupby("month")["dollar_pnl"].sum()
    if monthly.empty or t["month"].nunique() < 2:
        sharpe = None
    else:
        full_range = pd.period_range(t["month"].min(), t["month"].max(), freq="M")
        monthly = monthly.reindex(full_range, fill_value=0.0)
        monthly_equity_start = STARTING_CAPITAL + monthly.cumsum().shift(1).fillna(0.0)
        monthly_return = monthly / monthly_equity_start
        mean_m, std_m = float(monthly_return.mean()), float(monthly_return.std(ddof=1))
        sharpe = (mean_m / std_m * np.sqrt(12)) if std_m > 0 else None

    return {"n": n, "win_rate_pct": round(win_rate, 1), "median_pnl_pct": round(median_pnl, 1),
            "sharpe_annualized": round(sharpe, 3) if sharpe is not None else None,
            "max_drawdown_pct": round(mdd * 100, 2)}


def main():
    print("*** CONCENTRATION AND DEPENDENCE AUDIT — 147 STRONG_EARNINGS EVENTS ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    strong = events[(events["zscore"] >= Z_THRESHOLD) & (events["near_earnings"] == True)].copy()  # noqa: E712
    strong["spike_week"] = pd.to_datetime(strong["spike_week"])
    strong = strong.rename(columns={"end_of_spike_week_win": "win", "end_of_spike_week_pnl_pct": "pnl_pct"})
    print(f"Population: n={len(strong)}\n")

    print("Computing entry/exit dates (for equity-curve ordering) from on-disk daily data...")
    daily_cache = {t: load_daily_excess(t) for t in strong["ticker"].unique()}
    exit_dates = []
    for _, ev in strong.iterrows():
        daily = daily_cache.get(ev["ticker"], pd.DataFrame())
        exit_d = nearest_trading_day_on_or_before(daily, ev["spike_week"] + timedelta(days=EXIT_OFFSET_DAYS)) if not daily.empty else None
        exit_dates.append(exit_d)
    strong["exit_date"] = exit_dates
    strong = strong.dropna(subset=["exit_date"]).reset_index(drop=True)
    print(f"Usable (has exit_date): n={len(strong)}\n")

    result_rows = []

    # --- Baseline ---
    base = compute_win_median_sharpe(strong)
    result_rows.append({"analysis": "1_baseline", "cut": "ALL 147 events (baseline)", **base})
    print(f"BASELINE: n={base['n']}  win={base['win_rate_pct']}%  median={base['median_pnl_pct']}%  sharpe={base['sharpe_annualized']}\n")

    # === PART 1: remove top-N best events by pnl_pct ===
    print("=== PART 1: removing top-N best-performing events ===")
    sorted_desc = strong.sort_values("pnl_pct", ascending=False).reset_index(drop=True)
    for n_remove in [1, 5, 10]:
        removed = sorted_desc.iloc[:n_remove]
        remaining = sorted_desc.iloc[n_remove:]
        stats = compute_win_median_sharpe(remaining)
        removed_tickers = ", ".join(f"{r['ticker']}({r['pnl_pct']:.0f}%)" for _, r in removed.iterrows())
        result_rows.append({"analysis": "1_remove_top_events", "cut": f"best {n_remove} removed", **stats,
                             "detail": removed_tickers})
        print(f"  best {n_remove} removed: n={stats['n']}  win={stats['win_rate_pct']}%  "
              f"median={stats['median_pnl_pct']}%  sharpe={stats['sharpe_annualized']}")
    print()

    # === PART 2: remove single best-performing TICKER by total $ contribution ===
    print("=== PART 2: removing best-performing ticker by total P&L contribution ===")
    ticker_totals = strong.groupby("ticker")["pnl_pct"].sum().sort_values(ascending=False)
    best_ticker = ticker_totals.index[0]
    print(f"Best ticker by summed pnl_pct (proxy for total $ contribution, flat sizing): {best_ticker} "
          f"(sum={ticker_totals.iloc[0]:.1f}%, n_events={len(strong[strong['ticker']==best_ticker])})")
    without_best_ticker = strong[strong["ticker"] != best_ticker]
    stats = compute_win_median_sharpe(without_best_ticker)
    result_rows.append({"analysis": "2_remove_best_ticker", "cut": f"{best_ticker} removed (all its events)",
                         **stats, "detail": f"{best_ticker}, total_pnl_sum={ticker_totals.iloc[0]:.1f}%"})
    print(f"  without {best_ticker}: n={stats['n']}  win={stats['win_rate_pct']}%  "
          f"median={stats['median_pnl_pct']}%  sharpe={stats['sharpe_annualized']}\n")

    # === PART 3: remove mega-cap tech ===
    print("=== PART 3: removing mega-cap tech tickers ===")
    present = [t for t in MEGA_CAP_TECH if t in strong["ticker"].unique()]
    absent = [t for t in MEGA_CAP_TECH if t not in strong["ticker"].unique()]
    print(f"Present in dataset: {present}   Absent: {absent}")
    without_megacap = strong[~strong["ticker"].isin(MEGA_CAP_TECH)]
    stats = compute_win_median_sharpe(without_megacap)
    result_rows.append({"analysis": "3_remove_megacap_tech", "cut": f"removed {present} (absent: {absent})",
                         **stats, "detail": f"n_removed_events={len(strong)-stats['n']}"})
    print(f"  without mega-cap tech: n={stats['n']}  win={stats['win_rate_pct']}%  "
          f"median={stats['median_pnl_pct']}%  sharpe={stats['sharpe_annualized']}\n")

    # === PART 4: % of total profit from top 5/10/20% of events ===
    print("=== PART 4: profit concentration ===")
    total_profit = strong["pnl_pct"].sum()   # proportional to total $ P&L under flat sizing
    sorted_desc_all = strong.sort_values("pnl_pct", ascending=False).reset_index(drop=True)
    n_total = len(sorted_desc_all)
    for pct in [0.05, 0.10, 0.20]:
        n_top = int(round(pct * n_total))
        top_profit = sorted_desc_all.iloc[:n_top]["pnl_pct"].sum()
        share = top_profit / total_profit * 100
        result_rows.append({"analysis": "4_profit_concentration",
                             "cut": f"top {int(pct*100)}% of events ({n_top}/{n_total})",
                             "n": n_top, "win_rate_pct": None, "median_pnl_pct": None,
                             "sharpe_annualized": None, "max_drawdown_pct": None,
                             "detail": f"share_of_total_profit_pct={share:.1f}"})
        print(f"  top {int(pct*100)}% ({n_top} events): {share:.1f}% of total portfolio profit")
    print()

    # === PART 5: cluster bootstrap by ticker and by quarter, vs event-level i.i.d. bootstrap ===
    print("=== PART 5: cluster bootstrap (by ticker, by quarter) vs event-level i.i.d. bootstrap ===")
    rng = np.random.default_rng(RANDOM_SEED)
    wins = strong["win"].astype(int).to_numpy()
    n = len(wins)

    # (a) standard i.i.d. event-level bootstrap (matches GST_Task1_BootstrapCI.py convention)
    boot_iid = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, size=n)
        boot_iid[i] = wins[idx].mean()
    ci_iid = (np.percentile(boot_iid, 2.5) * 100, np.percentile(boot_iid, 97.5) * 100)

    # (b) cluster bootstrap by ticker: resample TICKERS with replacement, keep all their events
    rng_b = np.random.default_rng(RANDOM_SEED)
    tickers_unique = strong["ticker"].unique()
    n_tickers = len(tickers_unique)
    win_by_ticker = {t: strong.loc[strong["ticker"] == t, "win"].astype(int).to_numpy() for t in tickers_unique}
    boot_ticker = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        sampled_tickers = tickers_unique[rng_b.integers(0, n_tickers, size=n_tickers)]
        pooled = np.concatenate([win_by_ticker[t] for t in sampled_tickers])
        boot_ticker[i] = pooled.mean()
    ci_ticker = (np.percentile(boot_ticker, 2.5) * 100, np.percentile(boot_ticker, 97.5) * 100)

    # (c) cluster bootstrap by earnings quarter: resample (year, quarter) buckets with replacement
    strong["yr_q"] = strong["spike_week"].dt.to_period("Q")
    rng_q = np.random.default_rng(RANDOM_SEED)
    quarters_unique = strong["yr_q"].unique()
    n_quarters = len(quarters_unique)
    win_by_quarter = {q: strong.loc[strong["yr_q"] == q, "win"].astype(int).to_numpy() for q in quarters_unique}
    boot_quarter = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        sampled_q = quarters_unique[rng_q.integers(0, n_quarters, size=n_quarters)]
        pooled = np.concatenate([win_by_quarter[q] for q in sampled_q])
        boot_quarter[i] = pooled.mean()
    ci_quarter = (np.percentile(boot_quarter, 2.5) * 100, np.percentile(boot_quarter, 97.5) * 100)

    print(f"n_tickers={n_tickers}  n_quarters={n_quarters}\n")
    print(f"  Event-level i.i.d. bootstrap:  win={wins.mean()*100:.1f}%  95% CI=[{ci_iid[0]:.1f}, {ci_iid[1]:.1f}]  width={ci_iid[1]-ci_iid[0]:.1f}pt")
    print(f"  Cluster bootstrap by ticker:   win={wins.mean()*100:.1f}%  95% CI=[{ci_ticker[0]:.1f}, {ci_ticker[1]:.1f}]  width={ci_ticker[1]-ci_ticker[0]:.1f}pt")
    print(f"  Cluster bootstrap by quarter:  win={wins.mean()*100:.1f}%  95% CI=[{ci_quarter[0]:.1f}, {ci_quarter[1]:.1f}]  width={ci_quarter[1]-ci_quarter[0]:.1f}pt")

    result_rows.append({"analysis": "5_bootstrap_comparison", "cut": "event-level i.i.d. (standard)",
                         "n": n, "win_rate_pct": round(wins.mean()*100, 1), "median_pnl_pct": None,
                         "sharpe_annualized": None, "max_drawdown_pct": None,
                         "detail": f"95% CI=[{ci_iid[0]:.1f}, {ci_iid[1]:.1f}], width={ci_iid[1]-ci_iid[0]:.1f}pt"})
    result_rows.append({"analysis": "5_bootstrap_comparison", "cut": f"cluster by ticker (n_clusters={n_tickers})",
                         "n": n, "win_rate_pct": round(wins.mean()*100, 1), "median_pnl_pct": None,
                         "sharpe_annualized": None, "max_drawdown_pct": None,
                         "detail": f"95% CI=[{ci_ticker[0]:.1f}, {ci_ticker[1]:.1f}], width={ci_ticker[1]-ci_ticker[0]:.1f}pt"})
    result_rows.append({"analysis": "5_bootstrap_comparison", "cut": f"cluster by earnings quarter (n_clusters={n_quarters})",
                         "n": n, "win_rate_pct": round(wins.mean()*100, 1), "median_pnl_pct": None,
                         "sharpe_annualized": None, "max_drawdown_pct": None,
                         "detail": f"95% CI=[{ci_quarter[0]:.1f}, {ci_quarter[1]:.1f}], width={ci_quarter[1]-ci_quarter[0]:.1f}pt"})

    result_df = pd.DataFrame(result_rows)
    result_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
