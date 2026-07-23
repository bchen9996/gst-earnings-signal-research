#!/usr/bin/env python3
# TASK 1 — Permutation/placebo test: is being near a REAL earnings date
# what drives the STRONG_EARNINGS (z>=5) edge, or would being near ANY
# random date show the same pattern? All on-disk data, no new pulls.
#
# For each of the 201 z>=5 spike events (all 51 tickers, regardless of
# real earnings proximity — Straddle Profitability Test (2021-2025
# 51Ticker)/results.csv), the FIXED ingredients (trailing realized vol,
# realized forward return, entry/exit dates) are recomputed ONCE from the
# on-disk Daily Excess Return Data — these don't depend on which dates get
# treated as "earnings" and are shared across every permutation. Only the
# near-earnings CLASSIFICATION is randomized: each permutation replaces
# every ticker's real earnings-date list with the SAME COUNT of uniformly
# random pseudo-dates (count per ticker taken from the already-on-disk
# Live Signal Engine/historical_spike_frequency_prior.csv's
# total_quarters_2021_2025 — real, not guessed), reclassifies every event
# as placebo-near-earnings or not (within 5 days of any pseudo-date, same
# rule as the real within_5d definition), re-prices using the same
# calibrated near-earnings markup for placebo-near events and the same
# naive markup otherwise, and recomputes win rate / median P&L for the
# placebo-STRONG_EARNINGS subset (z>=5 AND placebo-near).
#
# 1000 permutations, seed=42. Reports what fraction produce win_rate >=
# 76.2% AND median_pnl >= +130.0% (the real, observed result) — a direct
# one-sided permutation test of whether real earnings-date proximity is
# doing genuine work, or whether z>=5 spikes are just broadly profitable
# regardless of the earnings framing.
#
# *** SANITY CHECK BEFORE TRUSTING THE PERMUTATION RESULT ***
# Before running any permutation, the same re-simulation pipeline is run
# ONCE using the REAL near_earnings flags already in results.csv — this
# must reproduce the established n=147/win=76.2%/median=+130.0% headline
# exactly, or the re-implementation has a bug and the permutation result
# can't be trusted.
#
# Output: Live Signal Engine/Task1_PlaceboPermutationTest_Results.csv

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

RESULTS_PATH = Path("Straddle Profitability Test (2021-2025 51Ticker)") / "results.csv"
FREQ_PRIOR_PATH = Path("Live Signal Engine") / "historical_spike_frequency_prior.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "Task1_PlaceboPermutationTest_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
SPIKE_WEEK_EXIT_OFFSET = 6
EARNINGS_WINDOW_DAYS = 5
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
NAIVE_MARKUP = 1.10
HIST_WINDOW_START = pd.Timestamp("2021-01-01")
HIST_WINDOW_END = pd.Timestamp("2025-12-31")

N_PERMUTATIONS = 10000
RANDOM_SEED = 42
REAL_WIN_RATE_PCT = 76.2
REAL_MEDIAN_PNL_PCT = 130.0


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


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


def build_fixed_ingredients(events: pd.DataFrame) -> pd.DataFrame:
    """Precomputes sigma, cum_ret, dte_days ONCE per event — identical across every permutation."""
    daily_cache: dict[str, pd.DataFrame] = {}
    rows = []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        if ticker not in daily_cache:
            daily_cache[ticker] = load_daily_excess(ticker)
        daily = daily_cache[ticker]
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue

        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        if entry_date is None:
            continue
        exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=SPIKE_WEEK_EXIT_OFFSET))
        if exit_date is None or exit_date <= entry_date:
            continue
        dte_days = (exit_date - entry_date).days
        if dte_days <= 0:
            continue

        sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
        if sigma is None:
            continue
        cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
        if cum_ret is None:
            continue

        rows.append({
            "ticker": ticker, "spike_week": anchor, "zscore": ev["zscore"],
            "real_near_earnings": ev["near_earnings"],
            "sigma": sigma, "dte_days": dte_days, "cum_ret": cum_ret,
        })
    return pd.DataFrame(rows)


def price_and_score(fixed: pd.DataFrame, near_earnings_flags: np.ndarray, near_earnings_markup: float) -> tuple[float, float, int]:
    """Given a near_earnings boolean array aligned to `fixed`, prices every event and returns
    (win_rate_pct, median_pnl_pct, n) for the near_earnings==True subset."""
    iv = np.where(near_earnings_flags, fixed["sigma"].to_numpy() * near_earnings_markup,
                  fixed["sigma"].to_numpy() * NAIVE_MARKUP)
    T = fixed["dte_days"].to_numpy() / 365.0
    cum_ret = fixed["cum_ret"].to_numpy()

    pnl_pct = np.full(len(fixed), np.nan)
    for i in range(len(fixed)):
        fair = bs_straddle_price(100.0, 100.0, T[i], RISK_FREE_RATE, iv[i])
        if fair is None:
            continue
        cost = fair * COST_LOADING
        intrinsic = abs(100.0 * (1 + cum_ret[i]) - 100.0)
        pnl_pct[i] = (intrinsic - cost) / cost * 100

    mask = near_earnings_flags & ~np.isnan(pnl_pct)
    n = int(mask.sum())
    if n == 0:
        return None, None, 0
    win_rate = float((pnl_pct[mask] > 0).mean() * 100)
    median_pnl = float(np.median(pnl_pct[mask]))
    return win_rate, median_pnl, n


def main():
    print(f"*** TASK 1: Placebo permutation test (n_perm={N_PERMUTATIONS}, seed={RANDOM_SEED}) ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Calibrated near-earnings markup (reused): {near_earnings_markup:.4f}x\n")

    results = pd.read_csv(RESULTS_PATH)
    events = results[results["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"z>={Z_THRESHOLD:g} events (all tickers, regardless of real earnings proximity): n={len(events)}")

    print("Precomputing fixed simulation ingredients (sigma, cum_ret, dte) once per event...")
    fixed = build_fixed_ingredients(events)
    print(f"Usable events with complete ingredients: n={len(fixed)}\n")

    # --- Sanity check: reproduce the real, established headline using REAL near_earnings flags ---
    real_flags = fixed["real_near_earnings"].to_numpy(dtype=bool)
    real_win, real_median, real_n = price_and_score(fixed, real_flags, near_earnings_markup)
    print(f"SANITY CHECK (real near_earnings flags): n={real_n}  win={real_win:.1f}%  median={real_median:+.1f}%")
    print(f"  Expected (established headline): n=147  win=76.2%  median=+130.0%")
    if real_n == 147 and abs(real_win - 76.2) < 0.15 and abs(real_median - 130.0) < 0.15:
        print("  MATCH — re-implementation verified, proceeding with permutations.\n")
    else:
        print("  *** MISMATCH — re-implementation does NOT reproduce the known result. "
              "Permutation results below should NOT be trusted until this is fixed. ***\n")

    freq_prior = pd.read_csv(FREQ_PRIOR_PATH)
    quarters_by_ticker = dict(zip(freq_prior["ticker"], freq_prior["total_quarters_2021_2025"]))
    default_quarters = int(freq_prior["total_quarters_2021_2025"].median())
    print(f"Real earnings-date counts loaded for {len(quarters_by_ticker)} tickers "
          f"(default={default_quarters} for any ticker missing from the prior file).\n")

    rng = np.random.default_rng(RANDOM_SEED)
    anchors = fixed["spike_week"].to_numpy()
    tickers = fixed["ticker"].to_numpy()
    unique_tickers = fixed["ticker"].unique()
    window_days = (HIST_WINDOW_END - HIST_WINDOW_START).days

    perm_results = []
    print(f"Running {N_PERMUTATIONS} permutations...")
    for p in range(N_PERMUTATIONS):
        placebo_flags = np.zeros(len(fixed), dtype=bool)
        for ticker in unique_tickers:
            n_dates = quarters_by_ticker.get(ticker, default_quarters)
            offsets = rng.integers(0, window_days + 1, size=n_dates)
            pseudo_dates = HIST_WINDOW_START + pd.to_timedelta(offsets, unit="D")

            idx = np.where(tickers == ticker)[0]
            for i in idx:
                anchor = pd.Timestamp(anchors[i])
                gaps = np.abs((pseudo_dates - anchor).days)
                if gaps.min() <= EARNINGS_WINDOW_DAYS:
                    placebo_flags[i] = True

        win_rate, median_pnl, n = price_and_score(fixed, placebo_flags, near_earnings_markup)
        if win_rate is not None:
            perm_results.append({"perm": p, "n": n, "win_rate_pct": win_rate, "median_pnl_pct": median_pnl})

        if (p + 1) % 1000 == 0:
            print(f"  {p+1}/{N_PERMUTATIONS} done")

    perm_df = pd.DataFrame(perm_results)
    perm_df.to_csv(OUT_PATH, index=False)

    both = ((perm_df["win_rate_pct"] >= REAL_WIN_RATE_PCT) & (perm_df["median_pnl_pct"] >= REAL_MEDIAN_PNL_PCT))
    frac_both = both.mean()
    frac_win_only = (perm_df["win_rate_pct"] >= REAL_WIN_RATE_PCT).mean()
    frac_median_only = (perm_df["median_pnl_pct"] >= REAL_MEDIAN_PNL_PCT).mean()

    print(f"\n=== RESULTS ({len(perm_df)} valid permutations out of {N_PERMUTATIONS}) ===")
    print(f"Permutation win rate distribution: mean={perm_df['win_rate_pct'].mean():.1f}%  "
          f"median={perm_df['win_rate_pct'].median():.1f}%  "
          f"[{perm_df['win_rate_pct'].min():.1f}%, {perm_df['win_rate_pct'].max():.1f}%]")
    print(f"Permutation median P&L distribution: mean={perm_df['median_pnl_pct'].mean():+.1f}%  "
          f"median={perm_df['median_pnl_pct'].median():+.1f}%  "
          f"[{perm_df['median_pnl_pct'].min():+.1f}%, {perm_df['median_pnl_pct'].max():+.1f}%]")
    print(f"\nFraction of permutations with win_rate >= {REAL_WIN_RATE_PCT}%: {frac_win_only*100:.1f}%")
    print(f"Fraction of permutations with median_pnl >= {REAL_MEDIAN_PNL_PCT}%: {frac_median_only*100:.1f}%")
    print(f"Fraction of permutations with BOTH >= real result: {frac_both*100:.2f}%")

    if frac_both <= 0.05:
        print(f"\n=> Real result is in the top {frac_both*100:.2f}% of placebo permutations — "
              f"strong evidence real earnings-date proximity (not just random date proximity) matters.")
    else:
        print(f"\n=> Real result is NOT rare among placebo permutations ({frac_both*100:.2f}% >= 5%) — "
              f"random date proximity produces similar-looking results about as often, weakening the "
              f"case that REAL earnings timing specifically is what's driving the edge.")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
