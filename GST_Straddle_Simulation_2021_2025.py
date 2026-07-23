#!/usr/bin/env python3
# GST Straddle Simulation — 2021-2025 replication of the VALIDATED
# strategy: z>=4 (STRONG tier) entry, at-the-money straddle, full-window
# hold (no early exit — GST_Strategy_Refinement_Test.py tested and
# rejected a +50%/5-day early-exit rule on the 2014-2019 data), priced with
# the earnings-aware model.
#
# Reuses the SAME calibrated near-earnings IV markup (1.240x, from the
# 25-point live calibration in GST_Earnings_IV_Calibration.py) rather than
# re-deriving it — that calibration reflects a structural feature of how
# options are priced around known catalysts, not something specific to the
# 2014-2019 period, so applying it unchanged to 2021-2025 keeps the pricing
# methodology identical across both eras for a clean comparison. This is a
# deliberate choice, not an oversight — flagged here explicitly.
#
# Runs on ALL z>=4 spike events in the 2021-2025 window, both full-hold
# horizons (end_of_spike_week, end_of_window), for the full set and the
# non-earnings subset, matching the report format already established for
# 2014-2019.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import pandas as pd

TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]
YEARS = list(range(2021, 2026))

SPIKE_DIR = Path("Conjunction Zscore (2021-2025)")
DAILY_DIR = Path("Daily Excess Return Data (2021-2025)")
EARNINGS_DIR = Path("Earnings Clustering Test (2021-2025)")
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"   # reused, not re-derived
OUT_DIR = Path("Straddle Profitability Test (2021-2025)")
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
    print(f"Using calibrated near-earnings markup: {near_earnings_markup:.4f}x (reused from the "
          f"original live calibration, not re-derived)\n")

    earnings_flags_path = EARNINGS_DIR / "spike_event_earnings_flags.csv"
    if not earnings_flags_path.exists():
        print(f"Missing {earnings_flags_path} — run GST_Earnings_Clustering_Test_2021_2025.py first.")
        return
    earnings_flags = pd.read_csv(earnings_flags_path)
    earnings_flags["anchor"] = pd.to_datetime(earnings_flags["anchor"]).dt.date.astype(str)
    within_5d_lookup = {(r["ticker"], r["anchor"]): bool(r["within_5d"]) for _, r in earnings_flags.iterrows()}

    rows = []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if not sp.exists():
            continue
        events = pd.read_csv(sp)
        ret_col = f"{ticker} Daily Return"
        daily = load_daily_excess(ticker)
        if daily.empty or ret_col not in daily.columns:
            continue

        for _, ev in events.iterrows():
            anchor = pd.to_datetime(ev["spike_week"], errors="coerce")
            zscore = ev.get("zscore")
            if pd.isna(anchor) or pd.isna(zscore) or zscore < Z_THRESHOLD:
                continue

            near_earnings = within_5d_lookup.get((ticker, anchor.date().isoformat()), False)

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

    print(f"Total z>=4 spike events (2021-2025): {len(results)}")
    report(results, "ALL EVENTS")
    report(results[~results["near_earnings"]], "NON-EARNINGS SUBSET")

    print("\n--- Comparison to original 2014-2019 z>=4, earnings-aware, full-hold result ---")
    print("2014-2019 ALL:          end_of_spike_week win=66.3% avg=+141.5% median=+83.4%  |  "
          "end_of_window win=61.7% avg=+60.2% median=+27.0%")
    print("2014-2019 NON-EARNINGS: end_of_spike_week win=58.8% avg=+165.8% median=+29.5%  |  "
          "end_of_window win=64.7% avg=+103.8% median=+27.0%")

    print(f"\nWrote full results to: {out_path}")


if __name__ == "__main__":
    main()
