#!/usr/bin/env python3
# TASK 3 — Negative control dataset: does the real STRONG_EARNINGS signal
# outperform two negative controls built to isolate specific confounds?
#   (a) MATCHED FIRM: same sector, earnings the same week, but that ticker
#       did NOT have a z>=5 spike that week. Isolates "is it something
#       about GST specifically, or just being a same-sector/same-week
#       earnings reporter?" If multiple eligible matches exist for an
#       event, one is chosen via a FIXED-SEED random draw (not cherry-
#       picked) — disclosed, reproducible.
#   (b) SHIFTED EARNINGS: same ticker, but its own NEAREST PRIOR earnings
#       date where it did NOT spike. Isolates "is it something about THIS
#       ticker generically being a good straddle candidate, or specific to
#       the spike itself?"
# If the real signal beats both, that's evidence beyond what pooled
# permutation tests (which don't control for firm or ticker identity)
# alone can show.
#
# Uses the shared foundation (AllTickers_EarningsDates.csv,
# AllTickers_Sectors.csv, AllTickers_ZscoreSeries.csv). Both control
# groups are priced fresh with the same earnings-aware model (calibrated
# near-earnings IV markup, since both controls are earnings-adjacent by
# construction) — no new pulls beyond the shared foundation already built.
#
# Output: Live Signal Engine/Task3_NegativeControls_Results.csv

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

EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task3_NegativeControls_Results.csv"

Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

BASELINE_WIN_PCT = 76.2
BASELINE_MEDIAN_PCT = 130.0


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


def price_event(daily_cache, ticker, anchor, sigma_markup):
    daily = daily_cache.get(ticker)
    ret_col = f"{ticker} Daily Return"
    if daily is None or daily.empty or ret_col not in daily.columns:
        return None
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    if entry_date is None:
        return None
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma is None:
        return None
    T = dte_days / 365.0
    iv = sigma * sigma_markup
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"win": pnl_pct > 0, "pnl_pct": pnl_pct}


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def main():
    print(f"*** TASK 3: Negative control dataset (z>={Z_THRESHOLD:g}) ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    rng = np.random.default_rng(RANDOM_SEED)

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earnings_df.groupby("ticker")}

    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = dict(zip(sector_df["ticker"], sector_df["sector"]))

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_lookup = {(r["ticker"], r["week"]): r["zscore_simple"] for _, r in z_df.dropna(subset=["zscore_simple"]).iterrows()}
    weeks_by_ticker = {t: sorted(g["week"].tolist()) for t, g in z_df.groupby("ticker")}

    def zscore_at_or_near(ticker, target_date, tol_days=3):
        weeks = weeks_by_ticker.get(ticker, [])
        if not weeks:
            return None
        nearest = min(weeks, key=lambda w: abs((w - target_date).days))
        if abs((nearest - target_date).days) > tol_days:
            return None
        return z_lookup.get((ticker, nearest))

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Real signal events: n={len(events)}\n")

    daily_cache = {}

    def get_daily(t):
        if t not in daily_cache:
            daily_cache[t] = load_daily_excess(t)
        return daily_cache[t]

    # --- Control (a): matched firm, same sector, same earnings week, no spike ---
    print("Building Control (a): matched firm (same sector, same earnings week, no z>=5 spike)...")
    control_a_rows = []
    n_a_no_match = 0
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        sector = ticker_to_sector.get(ticker)
        candidates = []
        for other_ticker, dates in earnings_by_ticker.items():
            if other_ticker == ticker or ticker_to_sector.get(other_ticker) != sector:
                continue
            if not any(abs((d - anchor).days) <= EARNINGS_WINDOW_DAYS for d in dates):
                continue
            z = zscore_at_or_near(other_ticker, anchor)
            if z is not None and z < Z_THRESHOLD:
                candidates.append(other_ticker)
        if not candidates:
            n_a_no_match += 1
            continue
        chosen = candidates[rng.integers(0, len(candidates))]
        res = price_event(daily_cache, chosen, anchor, near_earnings_markup)
        if res is None:
            get_daily(chosen)
            res = price_event(daily_cache, chosen, anchor, near_earnings_markup)
        if res is None:
            continue
        control_a_rows.append({"real_ticker": ticker, "matched_ticker": chosen, "week": anchor,
                               "win": res["win"], "pnl_pct": res["pnl_pct"]})
    control_a = pd.DataFrame(control_a_rows)
    print(f"Control (a) matched: n={len(control_a)}   no eligible match found: {n_a_no_match}\n")

    # --- Control (b): shifted earnings, same ticker, nearest prior non-spike earnings date ---
    print("Building Control (b): shifted earnings (same ticker, nearest prior non-spike earnings date)...")
    control_b_rows = []
    n_b_no_match = 0
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        dates = earnings_by_ticker.get(ticker, [])
        gaps = [(abs((d - anchor).days), d) for d in dates]
        gaps.sort()
        this_earnings_date = gaps[0][1] if gaps and gaps[0][0] <= EARNINGS_WINDOW_DAYS else anchor

        prior_dates = sorted([d for d in dates if d < this_earnings_date], reverse=True)
        chosen_date = None
        for d in prior_dates:
            z = zscore_at_or_near(ticker, d)
            if z is not None and z < Z_THRESHOLD:
                chosen_date = d
                break
        if chosen_date is None:
            n_b_no_match += 1
            continue
        get_daily(ticker)
        res = price_event(daily_cache, ticker, chosen_date, near_earnings_markup)
        if res is None:
            continue
        control_b_rows.append({"real_ticker": ticker, "real_week": anchor, "shifted_earnings_date": chosen_date,
                               "win": res["win"], "pnl_pct": res["pnl_pct"]})
    control_b = pd.DataFrame(control_b_rows)
    print(f"Control (b) matched: n={len(control_b)}   no eligible prior non-spike quarter found: {n_b_no_match}\n")

    combined = pd.concat([
        control_a.assign(control_type="matched_firm") if len(control_a) else pd.DataFrame(),
        control_b.assign(control_type="shifted_earnings") if len(control_b) else pd.DataFrame(),
    ], ignore_index=True)
    combined.to_csv(OUT_PATH, index=False)

    real_pnl = events["end_of_spike_week_pnl_pct"].dropna().to_numpy(dtype=float)
    real_win = events["end_of_spike_week_win"].dropna().mean() * 100

    print(f"=== RESULTS (spike_week horizon) ===")
    print(f"Real signal:              n={len(events)}  win={real_win:.1f}%  median={np.median(real_pnl):+.1f}%")
    if len(control_a):
        print(f"Control (a) matched firm: n={len(control_a):<4} win={control_a['win'].mean()*100:5.1f}%  "
              f"avg={control_a['pnl_pct'].mean():+7.1f}%  median={control_a['pnl_pct'].median():+7.1f}%")
    if len(control_b):
        print(f"Control (b) shifted earn: n={len(control_b):<4} win={control_b['win'].mean()*100:5.1f}%  "
              f"avg={control_b['pnl_pct'].mean():+7.1f}%  median={control_b['pnl_pct'].median():+7.1f}%")

    rng2 = np.random.default_rng(RANDOM_SEED)
    if len(control_a):
        diff, p = two_sample_permutation_test(real_pnl, control_a["pnl_pct"].to_numpy(dtype=float), N_PERMUTATIONS, rng2)
        print(f"\nReal vs Control (a): diff={diff:+.1f}pt  p={p:.4f} ({'significant' if p<0.05 else 'not significant'})")
    if len(control_b):
        diff, p = two_sample_permutation_test(real_pnl, control_b["pnl_pct"].to_numpy(dtype=float), N_PERMUTATIONS, rng2)
        print(f"Real vs Control (b): diff={diff:+.1f}pt  p={p:.4f} ({'significant' if p<0.05 else 'not significant'})")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
