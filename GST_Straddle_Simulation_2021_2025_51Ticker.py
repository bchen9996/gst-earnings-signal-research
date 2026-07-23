#!/usr/bin/env python3
# GST Straddle Simulation — 2021-2025, COMBINED 51-ticker universe (original
# 15 + 36 Broad50 clear-symbol tickers). Same validated strategy as
# GST_Straddle_Simulation_2021_2025.py (z>=4 entry, earnings-aware pricing,
# full-window hold, no early exit) — this just expands the ticker universe
# to grow the underpowered n=11 non-earnings subset from the 15-ticker run.
#
# Merges two independently-pulled data sources:
#   - original 15 tickers: Conjunction Zscore (2021-2025)/,
#     Daily Excess Return Data (2021-2025)/,
#     Earnings Clustering Test (2021-2025)/
#   - 36 new Broad50-clear tickers: Conjunction Zscore (2021-2025 Broad50 Clear)/,
#     Daily Excess Return Data (2021-2025 Broad50 Clear)/,
#     Earnings Clustering Test (2021-2025 Broad50 Clear)/
#
# Reuses the SAME calibrated near-earnings IV markup (1.240x) as every
# other earnings-aware run in this project — not re-derived.
#
# Output: Straddle Profitability Test (2021-2025 51Ticker)/results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
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

# Per-ticker source folders
SOURCES = {t: {
    "spike_dir": Path("Conjunction Zscore (2021-2025)"),
    "daily_dir": Path("Daily Excess Return Data (2021-2025)"),
    "earnings_flags": Path("Earnings Clustering Test (2021-2025)") / "spike_event_earnings_flags.csv",
} for t in TICKERS_ORIGINAL}
SOURCES.update({t: {
    "spike_dir": Path("Conjunction Zscore (2021-2025 Broad50 Clear)"),
    "daily_dir": Path("Daily Excess Return Data (2021-2025 Broad50 Clear)"),
    "earnings_flags": Path("Earnings Clustering Test (2021-2025 Broad50 Clear)") / "spike_event_earnings_flags.csv",
} for t in TICKERS_BROAD50_CLEAR})

ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR

CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_DIR = Path("Straddle Profitability Test (2021-2025 51Ticker)")
OUT_DIR.mkdir(parents=True, exist_ok=True)

Z_THRESHOLD = 4.0
ENTRY_OFFSET_DAYS = 2
EXIT_HORIZONS = {"end_of_spike_week": 6, "end_of_window": 13}

RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
NAIVE_MARKUP = 1.10


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


def main():
    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Combined universe: {len(TICKERS_ORIGINAL)} original + {len(TICKERS_BROAD50_CLEAR)} "
          f"Broad50-clear = {len(ALL_TICKERS)} tickers")
    print(f"Using calibrated near-earnings markup: {near_earnings_markup:.4f}x (reused, not re-derived)\n")

    # Load and combine earnings flags from both sources
    flags_frames = []
    for path in {s["earnings_flags"] for s in SOURCES.values()}:
        if path.exists():
            f = pd.read_csv(path)
            f["anchor"] = pd.to_datetime(f["anchor"]).dt.date.astype(str)
            flags_frames.append(f)
        else:
            print(f"WARNING: missing earnings flags file: {path}")
    earnings_flags = pd.concat(flags_frames, ignore_index=True)
    within_5d_lookup = {(r["ticker"], r["anchor"]): bool(r["within_5d"]) for _, r in earnings_flags.iterrows()}

    rows = []
    n_missing_flags = 0
    for ticker in ALL_TICKERS:
        src = SOURCES[ticker]
        sp = src["spike_dir"] / f"{ticker}_zconjunction.csv"
        if not sp.exists():
            print(f"[{ticker}] missing zconjunction file, skipping")
            continue
        events = pd.read_csv(sp)
        ret_col = f"{ticker} Daily Return"
        daily = load_daily_excess(src["daily_dir"], ticker)
        if daily.empty or ret_col not in daily.columns:
            print(f"[{ticker}] missing/empty daily excess data, skipping")
            continue

        for _, ev in events.iterrows():
            anchor = pd.to_datetime(ev["spike_week"], errors="coerce")
            zscore = ev.get("zscore")
            if pd.isna(anchor) or pd.isna(zscore) or zscore < Z_THRESHOLD:
                continue

            key = (ticker, anchor.date().isoformat())
            if key not in within_5d_lookup:
                n_missing_flags += 1
            near_earnings = within_5d_lookup.get(key, False)

            entry_target = anchor + timedelta(days=ENTRY_OFFSET_DAYS)
            entry_date = nearest_trading_day_on_or_before(daily, entry_target)
            if entry_date is None:
                continue

            vol_cutoff = anchor - timedelta(days=7)
            sigma = trailing_realized_vol(daily, ret_col, vol_cutoff)
            if sigma is None:
                continue
            iv = sigma * (near_earnings_markup if near_earnings else NAIVE_MARKUP)

            row = {"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore, "near_earnings": near_earnings}

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

    if n_missing_flags:
        print(f"NOTE: {n_missing_flags} z>=4 events had no earnings-flag match "
              f"(treated as near_earnings=False) — check ticker/date alignment if this is large.\n")

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "results.csv"
    results.to_csv(out_path, index=False)

    def report(df: pd.DataFrame, label: str):
        print(f"\n=== {label} (n={len(df)} z>=4 events) ===")
        for h in EXIT_HORIZONS:
            win_col, pnl_col = f"{h}_win", f"{h}_pnl_pct"
            if win_col not in df.columns:
                print(f"{h}: no usable events")
                continue
            usable = df[df[win_col].notna()]
            n = len(usable)
            if n == 0:
                print(f"{h}: no usable events")
                continue
            wr = usable[win_col].mean() * 100
            avg = usable[pnl_col].mean()
            med = usable[pnl_col].median()
            print(f"{h:<20}n={n:<5}win={wr:>6.1f}%  avg={avg:>8.1f}%  median={med:>8.1f}%")

    print(f"Total z>=4 spike events (2021-2025, 51 tickers): {len(results)}")
    report(results, "ALL EVENTS")
    report(results[~results["near_earnings"]], "NON-EARNINGS SUBSET")

    print("\n--- Comparison to 15-ticker 2021-2025 result ---")
    print("15-ticker ALL:          spike_week win=77.2% avg=+156.5% median=+127.6%  |  "
          "window win=63.8% avg=+66.3% median=+47.2%  (n=149)")
    print("15-ticker NON-EARNINGS: spike_week win=63.6% avg=+100.1% median=+28.7%   |  "
          "window win=72.7% avg=+79.7% median=+90.3%  (n=11)")

    print(f"\nWrote full results to: {out_path}")


if __name__ == "__main__":
    main()
