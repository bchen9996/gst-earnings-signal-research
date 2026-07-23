#!/usr/bin/env python3
# GST Earnings-Adjacent Spike-vs-No-Spike Test — does the z>=4 filter add
# information beyond "an earnings date is nearby," or is it just
# re-detecting the earnings calendar?
#
# GST_Straddle_Simulation_2021_2025_51Ticker.py found the surviving z>=4
# edge (n=297, 64% win, +67.5% median at spike_week) is concentrated in
# earnings-adjacent events — the non-earnings subset (n=88) had a negative
# median. This test asks the natural follow-up: among ONLY earnings-
# adjacent weeks, do the ones that ALSO show a z>=4 GST spike outperform
# the ones that don't?
#
# *** METHODOLOGICAL SUBSTITUTION, DISCLOSED ***
# Raw per-ticker earnings-date lists were never persisted to disk (only
# flags for the specific spike/baseline anchors already sampled), so
# "earnings-adjacent weeks WITHOUT a z>=4 spike" cannot be built directly
# without a new earnings pull. Group B below uses the BASELINE (random,
# non-spike) events instead, filtered to within_5d==True — these are
# confirmed NOT to have any spike at all (not specifically "spike but
# z<4"), which also excludes 2<=z<4 STANDARD-tier weeks from Group B. This
# is the closest construction achievable from data already on disk, and
# if anything makes Group B "quieter" than the letter of the request — a
# conservative substitution, not a favorable one, since a cleaner Group B
# would include weaker spikes too and probably narrow rather than widen
# any A-vs-B gap.
#
#   Group A = z>=4 spike events, near_earnings=True
#             (already computed — filtered from the 51-ticker straddle results)
#   Group B = random baseline events, near_earnings=True
#             (newly priced here, same earnings-aware methodology, no new
#              data pulled — reuses existing baseline anchors + daily
#              excess returns + the existing IV calibration)
#
# Same entry rule (anchor+2 days), same full-window horizons, same
# earnings-aware IV (near-earnings calibrated markup, since both groups
# are within_5d==True by construction here).

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import numpy as np
import pandas as pd

TICKERS_ORIGINAL = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
YEARS = list(range(2021, 2026))

SOURCES = {t: {
    "base_dir": Path("Conjunction Zscore Baseline (2021-2025)"),
    "daily_dir": Path("Daily Excess Return Data (2021-2025)"),
    "earnings_flags": Path("Earnings Clustering Test (2021-2025)") / "baseline_event_earnings_flags.csv",
} for t in TICKERS_ORIGINAL}
SOURCES.update({t: {
    "base_dir": Path("Conjunction Zscore Baseline (2021-2025 Broad50 Clear)"),
    "daily_dir": Path("Daily Excess Return Data (2021-2025 Broad50 Clear)"),
    "earnings_flags": Path("Earnings Clustering Test (2021-2025 Broad50 Clear)") / "baseline_event_earnings_flags.csv",
} for t in TICKERS_BROAD50_CLEAR})

ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR

SPIKE_RESULTS_PATH = Path("Straddle Profitability Test (2021-2025 51Ticker)") / "results.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_DIR = Path("Earnings-Adjacent Spike vs No-Spike Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENTRY_OFFSET_DAYS = 2
EXIT_HORIZONS = {"end_of_spike_week": 6, "end_of_window": 13}
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


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


def load_daily_excess(daily_dir: Path, ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = daily_dir / f"{ticker}_{year}_excess.csv"
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


def two_sample_permutation_test(group_a: np.ndarray, group_b: np.ndarray, n_perm: int, rng: np.random.Generator):
    a = group_a[~np.isnan(group_a)]
    b = group_b[~np.isnan(group_b)]
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


def build_group_b_earnings_adjacent_baseline():
    """Random (non-spike) baseline events, filtered to within_5d==True, priced with earnings-aware IV."""
    near_earnings_markup = load_calibrated_near_earnings_markup()

    flags_frames = []
    for path in {s["earnings_flags"] for s in SOURCES.values()}:
        if path.exists():
            f = pd.read_csv(path)
            f["anchor"] = pd.to_datetime(f["anchor"]).dt.date.astype(str)
            flags_frames.append(f)
    flags = pd.concat(flags_frames, ignore_index=True)
    flags_near = flags[flags["within_5d"] == True]  # noqa: E712
    near_keys = set(zip(flags_near["ticker"], flags_near["anchor"]))

    rows = []
    for ticker in ALL_TICKERS:
        src = SOURCES[ticker]
        bp = src["base_dir"] / f"{ticker}_baseline.csv"
        if not bp.exists():
            continue
        base_events = pd.read_csv(bp)
        ret_col = f"{ticker} Daily Return"
        daily = load_daily_excess(src["daily_dir"], ticker)
        if daily.empty or ret_col not in daily.columns:
            continue

        for _, ev in base_events.iterrows():
            anchor = pd.to_datetime(ev["random_week"], errors="coerce")
            if pd.isna(anchor):
                continue
            key = (ticker, anchor.date().isoformat())
            if key not in near_keys:
                continue  # only earnings-adjacent baseline weeks

            entry_target = anchor + timedelta(days=ENTRY_OFFSET_DAYS)
            entry_date = nearest_trading_day_on_or_before(daily, entry_target)
            if entry_date is None:
                continue

            vol_cutoff = anchor - timedelta(days=7)
            sigma = trailing_realized_vol(daily, ret_col, vol_cutoff)
            if sigma is None:
                continue
            iv = sigma * near_earnings_markup  # all Group B events are within_5d==True by construction

            row = {"ticker": ticker, "anchor": anchor.date(), "group": "B_no_spike_earnings_adjacent"}
            for h, offset in EXIT_HORIZONS.items():
                exit_target = anchor + timedelta(days=offset)
                exit_date = nearest_trading_day_on_or_before(daily, exit_target)
                if exit_date is None or exit_date <= entry_date:
                    continue
                dte_days = (exit_date - entry_date).days
                if dte_days <= 0:
                    continue
                T = dte_days / 365.0
                fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
                if fair is None:
                    continue
                cost = fair * COST_LOADING
                cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
                if cum_ret is None:
                    continue
                intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
                net_pnl_pct = (intrinsic - cost) / cost * 100
                row[f"{h}_win"] = net_pnl_pct > 0
                row[f"{h}_pnl_pct"] = net_pnl_pct
            rows.append(row)

    return pd.DataFrame(rows)


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    if not SPIKE_RESULTS_PATH.exists():
        print(f"Missing {SPIKE_RESULTS_PATH} — run GST_Straddle_Simulation_2021_2025_51Ticker.py first.")
        return

    spike_results = pd.read_csv(SPIKE_RESULTS_PATH)
    group_a = spike_results[spike_results["near_earnings"] == True].copy()  # noqa: E712
    group_a["group"] = "A_z_ge_4_earnings_adjacent"

    print(f"Group A (z>=4, earnings-adjacent, from existing results): n={len(group_a)}")
    print("Building Group B (random baseline, earnings-adjacent, no spike)...\n")
    group_b = build_group_b_earnings_adjacent_baseline()
    print(f"Group B (no spike, earnings-adjacent): n={len(group_b)}\n")

    group_a.to_csv(OUT_DIR / "group_a_z4_earnings_adjacent.csv", index=False)
    group_b.to_csv(OUT_DIR / "group_b_nospike_earnings_adjacent.csv", index=False)

    for h in EXIT_HORIZONS:
        win_a, pnl_a = f"{h}_win", f"{h}_pnl_pct"
        a_usable = group_a[group_a[win_a].notna()]
        b_usable = group_b[group_b[win_a].notna()] if win_a in group_b.columns else pd.DataFrame()

        print(f"=== {h} ===")
        if len(a_usable):
            print(f"Group A (z>=4, earnings-adjacent):    n={len(a_usable):<4} "
                  f"win={a_usable[win_a].mean()*100:5.1f}%  avg={a_usable[pnl_a].mean():+7.1f}%  "
                  f"median={a_usable[pnl_a].median():+7.1f}%")
        if len(b_usable):
            print(f"Group B (no spike, earnings-adjacent): n={len(b_usable):<4} "
                  f"win={b_usable[win_a].mean()*100:5.1f}%  avg={b_usable[pnl_a].mean():+7.1f}%  "
                  f"median={b_usable[pnl_a].median():+7.1f}%")

        if len(a_usable) and len(b_usable):
            diff, p, a_mean, b_mean = two_sample_permutation_test(
                a_usable[pnl_a].to_numpy(), b_usable[pnl_a].to_numpy(), N_PERMUTATIONS, rng)
            sig = "significant" if p < 0.05 else "not significant"
            print(f"Diff (A - B): {diff:+.1f} pts   two-sided p={p:.4f} ({sig})")
        print()

    print("*** Group B substitution note: 'no spike' (baseline/random weeks), not specifically "
          "'spike with z<4' — see script header. ***")


if __name__ == "__main__":
    main()
