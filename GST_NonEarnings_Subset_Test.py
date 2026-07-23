#!/usr/bin/env python3
# GST Non-Earnings Subset Test — isolates whether GST carries information
# beyond the earnings calendar the market already prices in.
#
# GST_Earnings_Clustering_Test.py found 80.3% of spike events fall within
# the full analysis window of an earnings date (vs 10.1% for baseline) —
# meaning the pooled volatility effect and the pooled straddle-profitability
# result were both mostly measuring earnings-adjacent events, where
# elevated realized volatility (and, per GST_ModelVsMarket_Sanity_Check.py,
# elevated real option pricing) is unsurprising and largely already
# anticipated by the market.
#
# This filters to the 74 spike events (23.9% of 310) and 356 baseline
# events (94.9% of 375) that are NOT within 5 days of an earnings date, and
# re-runs both tests on that subset only:
#   1. The volatility permutation test (|max_abs_excess_pct|: spike vs
#      baseline) — same methodology as GST_Zscore_VolatilityTest.py.
#   2. The cost-adjusted straddle profitability simulation — same
#      methodology as GST_Straddle_Profitability_Test.py (trailing-vol
#      Black-Scholes pricing, no look-ahead, same cost assumptions).
#
# Baseline events are filtered too (not just spike), for a fair
# apples-to-apples non-earnings-vs-non-earnings comparison in the
# volatility test.
#
# If the effect and profitability survive this filter, that's evidence GST
# is flagging something the earnings calendar doesn't already explain — a
# real, less-priced-in signal. If they collapse, the pooled results were
# essentially an earnings-proximity effect wearing a GST costume.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import numpy as np
import pandas as pd

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
YEARS = list(range(2014, 2020))

SPIKE_DIR = Path("Conjunction Zscore")
BASE_DIR = Path("Conjunction Zscore Baseline")
DAILY_DIR = Path("Daily Excess Return Data")
EARNINGS_DIR = Path("Earnings Clustering Test")
OUT_DIR = Path("Non-Earnings Subset Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_PERMUTATIONS = 10000
RANDOM_SEED = 42

ENTRY_OFFSET_DAYS = 2
EXIT_HORIZONS = {"end_of_spike_week": 6, "end_of_window": 13}
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
IV_MARKUP = 1.10
COST_LOADING = 1.05


# ---------- shared loaders ----------

def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIR / f"{ticker}_{year}_excess.csv"
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


def non_earnings_anchors(flags_path: Path, anchor_col: str = "anchor") -> pd.DataFrame:
    flags = pd.read_csv(flags_path)
    return flags[flags["within_5d"] == False][["ticker", anchor_col]].rename(columns={anchor_col: "anchor"})  # noqa: E712


# ---------- Part 1: volatility permutation test ----------

def permutation_test_mean_diff(group_a, group_b, n_perm, rng):
    observed_diff = group_a.mean() - group_b.mean()
    pooled = np.concatenate([group_a, group_b])
    n_a = len(group_a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(diff) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def run_volatility_test(rng):
    spike_anchors = non_earnings_anchors(EARNINGS_DIR / "spike_event_earnings_flags.csv")
    base_anchors = non_earnings_anchors(EARNINGS_DIR / "baseline_event_earnings_flags.csv")

    spike_vols, base_vols = [], []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if sp.exists():
            df = pd.read_csv(sp)
            df["spike_week"] = pd.to_datetime(df["spike_week"]).dt.date.astype(str)
            keep = set(spike_anchors.loc[spike_anchors["ticker"] == ticker, "anchor"].astype(str))
            filtered = df[df["spike_week"].isin(keep)]
            spike_vols.append(pd.to_numeric(filtered["max_abs_excess_pct"], errors="coerce").dropna().abs())

        bp = BASE_DIR / f"{ticker}_baseline.csv"
        if bp.exists():
            df = pd.read_csv(bp)
            df["random_week"] = pd.to_datetime(df["random_week"]).dt.date.astype(str)
            keep = set(base_anchors.loc[base_anchors["ticker"] == ticker, "anchor"].astype(str))
            filtered = df[df["random_week"].isin(keep)]
            base_vols.append(pd.to_numeric(filtered["max_abs_excess_pct"], errors="coerce").dropna().abs())

    spike_vol = pd.concat(spike_vols).to_numpy()
    base_vol = pd.concat(base_vols).to_numpy()

    diff, p_two = permutation_test_mean_diff(spike_vol, base_vol, N_PERMUTATIONS, rng)

    print("=== Volatility test, NON-EARNINGS subset ===")
    print(f"Spike events: {len(spike_vol)}   Baseline events: {len(base_vol)}")
    print(f"Spike mean:    {spike_vol.mean():.3f}%")
    print(f"Baseline mean: {base_vol.mean():.3f}%")
    print(f"Diff (spike - baseline): {diff:+.3f} pts")
    print(f"Two-sided p-value: {p_two:.4f}  {'(significant at 0.05)' if p_two < 0.05 else '(NOT significant at 0.05)'}")
    print(f"\nFor reference, the ORIGINAL POOLED result was: diff +2.976 pts, p=0.0000 "
          f"(spike 5.987% vs baseline 3.011%, n=310 spike / 375 baseline)\n")

    return {"n_spike": len(spike_vol), "n_base": len(base_vol), "spike_mean": spike_vol.mean(),
            "base_mean": base_vol.mean(), "diff": diff, "p_value": p_two}


# ---------- Part 2: straddle profitability ----------

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


def run_straddle_test():
    spike_anchors = non_earnings_anchors(EARNINGS_DIR / "spike_event_earnings_flags.csv")

    rows = []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if not sp.exists():
            continue
        events = pd.read_csv(sp)
        events["spike_week"] = pd.to_datetime(events["spike_week"])
        keep = set(spike_anchors.loc[spike_anchors["ticker"] == ticker, "anchor"].astype(str))
        events = events[events["spike_week"].dt.date.astype(str).isin(keep)]
        if events.empty:
            continue

        ret_col = f"{ticker} Daily Return"
        daily = load_daily_excess(ticker)
        if daily.empty or ret_col not in daily.columns:
            continue

        for _, ev in events.iterrows():
            anchor = ev["spike_week"]
            entry_target = anchor + timedelta(days=ENTRY_OFFSET_DAYS)
            entry_date = nearest_trading_day_on_or_before(daily, entry_target)
            if entry_date is None:
                continue

            vol_cutoff = anchor - timedelta(days=7)
            sigma = trailing_realized_vol(daily, ret_col, vol_cutoff)
            row = {"ticker": ticker, "spike_week": anchor.date(), "entry_date": entry_date.date()}
            if sigma is None:
                continue
            iv_assumed = sigma * IV_MARKUP

            for h, offset in EXIT_HORIZONS.items():
                exit_target = anchor + timedelta(days=offset)
                exit_date = nearest_trading_day_on_or_before(daily, exit_target)
                if exit_date is None or exit_date <= entry_date:
                    continue
                dte_days = (exit_date - entry_date).days
                if dte_days <= 0:
                    continue
                T = dte_days / 365.0
                straddle_fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv_assumed)
                if straddle_fair is None:
                    continue
                straddle_cost = straddle_fair * COST_LOADING

                cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
                if cum_ret is None:
                    continue
                s_exit = 100.0 * (1 + cum_ret)
                intrinsic_value = abs(s_exit - 100.0)
                net_pnl = intrinsic_value - straddle_cost

                row[f"{h}_dte_days"] = dte_days
                row[f"{h}_straddle_cost"] = round(straddle_cost, 3)
                row[f"{h}_net_pnl"] = round(net_pnl, 3)
                row[f"{h}_net_pnl_pct_of_cost"] = round(net_pnl / straddle_cost * 100, 2)
                row[f"{h}_win"] = bool(net_pnl > 0)

            rows.append(row)

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "straddle_results.csv"
    results.to_csv(out_path, index=False)

    print("=== Straddle profitability, NON-EARNINGS subset ===")
    print(f"Total non-earnings spike events processed: {len(results)}\n")

    summary = {}
    for h in EXIT_HORIZONS:
        win_col, pnlpct_col = f"{h}_win", f"{h}_net_pnl_pct_of_cost"
        if win_col not in results.columns:
            print(f"{h}: no usable events")
            continue
        usable = results[results[win_col].notna()]
        n = len(usable)
        if n == 0:
            print(f"{h}: no usable events")
            continue
        win_rate = usable[win_col].mean()
        avg_pnl_pct = usable[pnlpct_col].mean()
        median_pnl_pct = usable[pnlpct_col].median()
        print(f"--- {h} (n={n}, avg DTE {usable[f'{h}_dte_days'].mean():.1f}d) ---")
        print(f"Win rate: {win_rate*100:.1f}%")
        print(f"Avg net P&L (% of premium): {avg_pnl_pct:+.1f}%")
        print(f"Median net P&L (% of premium): {median_pnl_pct:+.1f}%\n")
        summary[h] = {"n": n, "win_rate": win_rate, "avg_pnl_pct": avg_pnl_pct, "median_pnl_pct": median_pnl_pct}

    print("For reference, the ORIGINAL POOLED (n=310) result was:")
    print("  end_of_spike_week: win rate 68.1%, avg +135.5%, median +65.6%")
    print("  end_of_window:     win rate 59.7%, avg +58.3%,  median +22.1%")
    print(f"\nWrote full results to: {out_path}")

    return summary


def main():
    rng = np.random.default_rng(RANDOM_SEED)
    run_volatility_test(rng)
    run_straddle_test()


if __name__ == "__main__":
    main()
