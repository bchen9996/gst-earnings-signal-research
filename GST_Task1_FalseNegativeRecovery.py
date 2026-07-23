#!/usr/bin/env python3
# TASK 1 — False negative recovery: for the 203 genuine false negatives
# (large realized earnings move, GST did NOT flag it), test whether a
# simple price+volume signal — computed entirely from on-disk daily
# volume and reconstructed price data, no new pulls — would have caught
# them instead.
#
# Signals, computed for the trading week immediately before each earnings
# date:
#   (a) abnormal volume: mean daily volume that week / 20-trading-day
#       trailing average daily volume (ending before that week)
#   (b) |2-week return|: abs cumulative return over the 10 trading days
#       ending the day before the pre-earnings week
#   (c) 14-day RSI (Wilder smoothing) as of the last trading day of the
#       pre-earnings week
#
# "Top quartile for that ticker" is computed from that TICKER'S OWN full
# weekly history (every week, not just earnings weeks) — a ticker-specific
# threshold, not a cross-sectional one, per the task spec.
#
# *** PRICE RECONSTRUCTION DISCLOSURE ***
# No raw daily close-price file exists on disk (only pre-computed daily
# RETURNS). Price is reconstructed as a synthetic index (100 * cumulative
# product of (1+return)) per ticker — this exactly preserves all relative
# price changes and is sufficient for both RSI (which only depends on
# period-over-period changes) and cumulative-return calculations. It is
# NOT a real dollar price and isn't used as one anywhere in this script.
#
# For the "true positive rate" comparison, recoverable false negatives are
# priced with the SAME Black-Scholes straddle / calibrated near-earnings
# IV markup convention used throughout this project, entering the day
# before earnings (mirroring how a price+volume signal would actually
# trigger — right before the print, not 2-5 days ahead like GST) and
# exiting the next trading day's close (current exit-rule spec).
#
# Output: Live Signal Engine/FalseNegativeRecovery_Results.csv

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
VOLUME_DIR = Path("Daily Volume Data (2021-2025)")

DETAIL_PATH = Path("Live Signal Engine") / "FalseNegative_Analysis_Detail.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "FalseNegativeRecovery_Results.csv"

TOP_QUARTILE = 0.75
VOL_LOOKBACK_DAYS = 20
RETURN_LOOKBACK_DAYS = 10
RSI_PERIOD = 14
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05


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


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


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


def load_volume(ticker: str) -> pd.DataFrame:
    p = VOLUME_DIR / f"{ticker}_volume.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)


def build_ticker_frame(ticker: str) -> pd.DataFrame:
    daily = load_daily_excess(ticker)
    ret_col = f"{ticker} Daily Return"
    if daily.empty or ret_col not in daily.columns:
        return pd.DataFrame()
    vol = load_volume(ticker)
    df = daily[["Date", ret_col]].rename(columns={ret_col: "ret"}).merge(vol, on="Date", how="left")
    df = df.sort_values("Date").reset_index(drop=True)
    df["price"] = 100.0 * (1 + df["ret"]).cumprod()

    delta = df["price"].diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / RSI_PERIOD, adjust=False, min_periods=RSI_PERIOD).mean()
    avg_loss = losses.ewm(alpha=1 / RSI_PERIOD, adjust=False, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    df["rsi14"] = 100 - 100 / (1 + rs)
    df.loc[avg_loss == 0, "rsi14"] = 100.0

    df["vol_20d_avg"] = df["Volume"].shift(1).rolling(VOL_LOOKBACK_DAYS, min_periods=VOL_LOOKBACK_DAYS).mean()
    return df


def week_signals(df: pd.DataFrame, week_start, week_end):
    """Signals for the trading week [week_start, week_end] (inclusive), using data available up to week_end."""
    week_mask = (df["Date"] >= week_start) & (df["Date"] <= week_end)
    week_rows = df.loc[week_mask]
    if week_rows.empty:
        return None
    last_idx = week_rows.index[-1]

    mean_vol = week_rows["Volume"].mean()
    trailing_avg_vol = df.loc[last_idx, "vol_20d_avg"]
    abnormal_volume = mean_vol / trailing_avg_vol if pd.notna(trailing_avg_vol) and trailing_avg_vol > 0 else None

    ret_window_start = week_end - timedelta(days=RETURN_LOOKBACK_DAYS)
    ret_mask = (df["Date"] > ret_window_start) & (df["Date"] <= week_end)
    rets = df.loc[ret_mask, "ret"]
    two_week_abs_return = abs(float((1 + rets).prod() - 1)) if not rets.empty else None

    rsi = df.loc[last_idx, "rsi14"]
    rsi = float(rsi) if pd.notna(rsi) else None

    return {"abnormal_volume": abnormal_volume, "two_week_abs_return": two_week_abs_return, "rsi14": rsi}


def compute_full_weekly_history(df: pd.DataFrame) -> pd.DataFrame:
    """Every ISO week in this ticker's history -> (abnormal_volume, two_week_abs_return, rsi14) at week end."""
    df = df.copy()
    df["iso_week"] = df["Date"].dt.isocalendar().year.astype(str) + "-W" + df["Date"].dt.isocalendar().week.astype(str).str.zfill(2)
    rows = []
    for iso_week, g in df.groupby("iso_week"):
        week_start, week_end = g["Date"].min(), g["Date"].max()
        sig = week_signals(df, week_start, week_end)
        if sig:
            rows.append(sig)
    return pd.DataFrame(rows)


def price_leg(daily, ret_col, entry_date, exit_date, sigma, markup):
    if exit_date is None or entry_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    T = dte_days / 365.0
    iv = sigma * markup
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    mask = (daily["Date"] > entry_date) & (daily["Date"] <= exit_date)
    rets = daily.loc[mask, ret_col]
    if rets.empty:
        return None
    cum_ret = float((1 + rets).prod() - 1)
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"win": pnl_pct > 0, "pnl_pct": pnl_pct}


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def next_trading_day_after(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] > target, "Date"]
    return eligible.min() if not eligible.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def main():
    print("*** TASK 1: False negative recovery via price+volume signal ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    fn = pd.read_csv(DETAIL_PATH)
    fn["earnings_date"] = pd.to_datetime(fn["earnings_date"])
    print(f"False negatives to test: n={len(fn)}\n")

    tickers = sorted(fn["ticker"].unique())
    print(f"Building per-ticker daily/volume/RSI frames and weekly threshold distributions ({len(tickers)} tickers)...")
    ticker_frames, thresholds = {}, {}
    for t in tickers:
        df = build_ticker_frame(t)
        if df.empty or "Volume" not in df.columns or df["Volume"].isna().all():
            print(f"  [{t}] insufficient volume/price data -- skipped")
            continue
        ticker_frames[t] = df
        weekly_hist = compute_full_weekly_history(df)
        thresholds[t] = {
            "abnormal_volume_q75": weekly_hist["abnormal_volume"].quantile(TOP_QUARTILE),
            "two_week_abs_return_q75": weekly_hist["two_week_abs_return"].quantile(TOP_QUARTILE),
            "rsi14_q75": weekly_hist["rsi14"].quantile(TOP_QUARTILE),
        }
    print(f"  {len(ticker_frames)}/{len(tickers)} tickers usable\n")

    rows = []
    for _, ev in fn.iterrows():
        ticker, earn_date = ev["ticker"], ev["earnings_date"]
        df = ticker_frames.get(ticker)
        thr = thresholds.get(ticker)
        if df is None or thr is None:
            continue

        week_end = earn_date - timedelta(days=1)
        week_start = week_end - timedelta(days=6)
        sig = week_signals(df, week_start, week_end)
        if sig is None:
            continue

        hit_volume = sig["abnormal_volume"] is not None and sig["abnormal_volume"] >= thr["abnormal_volume_q75"]
        hit_return = sig["two_week_abs_return"] is not None and sig["two_week_abs_return"] >= thr["two_week_abs_return_q75"]
        hit_rsi = sig["rsi14"] is not None and sig["rsi14"] >= thr["rsi14_q75"]
        recoverable = hit_volume or hit_return or hit_rsi

        rows.append({"ticker": ticker, "earnings_date": earn_date.date(),
                      "abnormal_volume": sig["abnormal_volume"], "abnormal_volume_q75_threshold": thr["abnormal_volume_q75"],
                      "two_week_abs_return": sig["two_week_abs_return"], "two_week_abs_return_q75_threshold": thr["two_week_abs_return_q75"],
                      "rsi14": sig["rsi14"], "rsi14_q75_threshold": thr["rsi14_q75"],
                      "hit_volume": hit_volume, "hit_return": hit_return, "hit_rsi": hit_rsi,
                      "recoverable": recoverable})

    result = pd.DataFrame(rows)
    n_total = len(result)
    n_recoverable = int(result["recoverable"].sum())
    print(f"=== RECOVERY RATE ===")
    print(f"Usable false negatives: n={n_total}")
    print(f"Recoverable (>=1 signal in ticker's own top quartile): {n_recoverable} ({n_recoverable/n_total*100:.1f}%)")
    print(f"  via volume: {int(result['hit_volume'].sum())}  via 2wk return: {int(result['hit_return'].sum())}  via RSI: {int(result['hit_rsi'].sum())}\n")

    # --- Price the recoverable subset: entry = day before earnings, exit = next trading day after ---
    print("Pricing recoverable false negatives (entry=day-before-earnings, exit=next-day-after)...")
    recoverable_events = result[result["recoverable"]]
    pv_pnls = []
    for _, ev in recoverable_events.iterrows():
        ticker, earn_date = ev["ticker"], pd.Timestamp(ev["earnings_date"])
        daily = ticker_frames[ticker]
        ret_col = "ret"
        entry_date = nearest_trading_day_on_or_before(daily, earn_date - timedelta(days=1))
        exit_date = next_trading_day_after(daily, earn_date)
        if entry_date is None or exit_date is None:
            continue
        sigma = trailing_realized_vol(daily, ret_col, earn_date - timedelta(days=7))
        if sigma is None:
            continue
        res = price_leg(daily, ret_col, entry_date, exit_date, sigma, near_earnings_markup)
        if res:
            pv_pnls.append(res)

    pv_df = pd.DataFrame(pv_pnls)
    if len(pv_df) > 0:
        pv_win_rate = pv_df["win"].mean() * 100
        pv_median_pnl = pv_df["pnl_pct"].median()
        print(f"Price+volume-caught events priced: n={len(pv_df)}  win rate={pv_win_rate:.1f}%  median P&L={pv_median_pnl:+.1f}%")
    else:
        pv_win_rate = pv_median_pnl = None
        print("No price+volume-caught events could be priced (insufficient data).")

    gst_events = pd.read_csv(GROUP_A_PATH)
    gst_events = gst_events[gst_events["zscore"] >= 5.0]
    gst_win_rate = gst_events["end_of_spike_week_win"].mean() * 100
    gst_median_pnl = gst_events["end_of_spike_week_pnl_pct"].median()
    print(f"\nGST-caught events (canonical z>=5 STRONG_EARNINGS, n={len(gst_events)}): "
          f"win rate={gst_win_rate:.1f}%  median P&L={gst_median_pnl:+.1f}%")

    summary = pd.DataFrame([{
        "n_false_negatives_tested": n_total, "n_recoverable": n_recoverable,
        "pct_recoverable": round(n_recoverable / n_total * 100, 1),
        "n_recoverable_via_volume": int(result["hit_volume"].sum()),
        "n_recoverable_via_return": int(result["hit_return"].sum()),
        "n_recoverable_via_rsi": int(result["hit_rsi"].sum()),
        "price_volume_signal_n_priced": len(pv_df), "price_volume_signal_win_rate_pct": round(pv_win_rate, 1) if pv_win_rate is not None else None,
        "price_volume_signal_median_pnl_pct": round(pv_median_pnl, 1) if pv_median_pnl is not None else None,
        "gst_signal_n": len(gst_events), "gst_signal_win_rate_pct": round(gst_win_rate, 1),
        "gst_signal_median_pnl_pct": round(gst_median_pnl, 1),
    }])

    combined = pd.concat([result, pd.DataFrame([{}]), summary], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
