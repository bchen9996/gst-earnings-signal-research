#!/usr/bin/env python3
# TASK 5 — 2020 COVID stress test: the one calendar year missing from
# every longitudinal test in this project so far (2014-2019 + 2021-2025
# on disk, 2020 never pulled). Runs the full STRONG_EARNINGS pipeline
# (z>=5, earnings within 5 days, earnings-aware pricing, next-day exit —
# current spec) on fresh 2020 GST + price data for the original 15
# tickers, to see whether the signal held, collapsed, or inverted during
# the most extreme volatility regime in the dataset's span.
#
# *** FRESH PULLS REQUIRED, WITH REUSE WHERE POSSIBLE ***
# - Weekly GST: fresh pytrends pull, 2019-06-01 to 2020-12-31 (extra
#   lookback so the 12-week rolling z-score has full history from the
#   start of 2020) — historical/closed period, deterministic per the
#   earlier GST sampling-noise test on closed 2023 data.
# - Daily price/SPY: fresh yfinance pull for 2020 only, using the exact
#   same stock-minus-SPY methodology as "Daily Excess Returns (2021-
#   2025).py". The pre-2020 trailing-vol lookback REUSES the existing
#   on-disk 2019 file (Daily Excess Return Data/<T>_2019_excess.csv) —
#   no need to re-pull 2019.
# - Earnings dates: 100% reused from Live Signal Engine/
#   AllTickers_EarningsDates.csv (already covers 2020, confirmed on disk).
# - IV markup: reuses the existing calibrated near-earnings markup.
#
# Output: Live Signal Engine/COVID2020StressTest_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys, time
import math
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
GST_TIMEFRAME = "2019-06-01 2020-12-31"
PRICE_YEAR = 2020
BENCH = "SPY"
GEO, GPROP, CATEGORY = "US", "", 0

DAILY_2019_DIR = Path("Daily Excess Return Data")  # existing on-disk, 2014-2019
GST_OUT_DIR = Path("GST Data") / "Weekly Data (2020 COVID Stress Test)"
PRICE_OUT_DIR = Path("Daily Excess Return Data (2020 COVID Stress Test)"); PRICE_OUT_DIR.mkdir(parents=True, exist_ok=True)
GST_OUT_DIR.mkdir(parents=True, exist_ok=True)

EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OUT_PATH = Path("Live Signal Engine") / "COVID2020StressTest_Results.csv"

ROLLING_WINDOW = 12
MIN_PERIODS = 8
Z_THRESHOLD = 5.0
MAX_EARNINGS_GAP_DAYS = 5
ENTRY_OFFSET_DAYS = 2
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

MAX_ATTEMPTS = 5
HARD_429_SLEEP = 60

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_weekly_gst(pt: TrendReq, ticker: str) -> pd.DataFrame:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([ticker], timeframe=GST_TIMEFRAME, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or ticker not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({"Week": df.index, "gst": pd.to_numeric(df[ticker], errors="coerce")})
            return out.sort_values("Week").reset_index(drop=True)
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg) else 5 * attempt
            print(f"    attempt {attempt} failed: {e} -- sleeping {pause}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst"])


def dl_prices(ticker: str, start: str, end: str) -> pd.Series:
    df = yf.download(ticker, start=start, end=end, session=SESSION, auto_adjust=True, progress=False,
                      group_by="column", threads=False)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    close = df["Close"] if "Close" in df.columns else df.squeeze("columns")
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return pd.Series(close.values, index=pd.to_datetime(close.index), name=ticker).sort_index()


def pull_2020_excess(ticker: str) -> pd.DataFrame:
    start, end = f"{PRICE_YEAR}-01-01", f"{PRICE_YEAR+1}-01-01"
    s_tkr, s_spy = dl_prices(ticker, start, end), dl_prices(BENCH, start, end)
    if s_tkr.empty or s_spy.empty:
        return pd.DataFrame()
    r_tkr, r_spy = s_tkr.pct_change().dropna(), s_spy.pct_change().dropna()
    idx = r_tkr.index.intersection(r_spy.index)
    df = pd.DataFrame({"Date": idx, f"{ticker} Daily Return": r_tkr.loc[idx].round(4).values,
                        "SPY Daily Return": r_spy.loc[idx].round(4).values})
    return df.reset_index(drop=True)


def load_2019_excess(ticker: str) -> pd.DataFrame:
    p = DAILY_2019_DIR / f"{ticker}_2019_excess.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"])


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


def main():
    print("*** TASK 5: 2020 COVID stress test ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    earnings = pd.read_csv(EARNINGS_PATH)
    earnings["earnings_date"] = pd.to_datetime(earnings["earnings_date"])
    earnings_by_ticker = {t: g["earnings_date"].sort_values().reset_index(drop=True)
                          for t, g in earnings.groupby("ticker")}

    print(f"Pulling weekly GST ({GST_TIMEFRAME}) for {len(TICKERS)} tickers...")
    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})
    gst_cache = {}
    for i, t in enumerate(TICKERS, start=1):
        cache_path = GST_OUT_DIR / f"{t}_gst.csv"
        if cache_path.exists():
            gst_cache[t] = pd.read_csv(cache_path, parse_dates=["Week"])
            print(f"  [{i}/{len(TICKERS)}] {t}: loaded from cache ({len(gst_cache[t])} weeks)")
            continue
        df = fetch_weekly_gst(pt, t)
        gst_cache[t] = df
        if not df.empty:
            df.to_csv(cache_path, index=False)
        print(f"  [{i}/{len(TICKERS)}] {t}: {len(df)} weeks retrieved")
        time.sleep(1.5)
    print()

    print(f"Pulling 2020 daily price data (yfinance) for {len(TICKERS)} tickers + SPY...")
    daily_cache = {}
    for i, t in enumerate(TICKERS, start=1):
        cache_path = PRICE_OUT_DIR / f"{t}_2020_excess.csv"
        if cache_path.exists():
            df_2020 = pd.read_csv(cache_path, parse_dates=["Date"])
        else:
            df_2020 = pull_2020_excess(t)
            if not df_2020.empty:
                df_2020.to_csv(cache_path, index=False)
            time.sleep(0.5)
        df_2019 = load_2019_excess(t)
        ret_col = f"{t} Daily Return"
        if not df_2019.empty and ret_col in df_2019.columns:
            combined = pd.concat([df_2019[["Date", ret_col, "SPY Daily Return"]], df_2020], ignore_index=True)
        else:
            combined = df_2020
        combined = combined.sort_values("Date").reset_index(drop=True)
        daily_cache[t] = combined
        print(f"  [{i}/{len(TICKERS)}] {t}: {len(df_2020)} 2020 rows (+{len(df_2019)} 2019 lookback rows)")
    print()

    print("Computing z-score series and identifying STRONG_EARNINGS events in 2020...")
    events = []
    for t in TICKERS:
        gst = gst_cache.get(t, pd.DataFrame())
        if gst.empty:
            continue
        rolling = gst["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
        z = (gst["gst"] - rolling.mean()) / rolling.std()
        gst = gst.assign(zscore=z.replace([np.inf, -np.inf], np.nan))
        gst_2020 = gst[(gst["Week"] >= "2020-01-01") & (gst["Week"] <= "2020-12-31")]

        hist = earnings_by_ticker.get(t, pd.Series(dtype="datetime64[ns]"))
        for _, row in gst_2020[gst_2020["zscore"] >= Z_THRESHOLD].iterrows():
            anchor = row["Week"]
            if hist.empty:
                continue
            gaps = (hist - anchor).abs().dt.days
            idx = gaps.idxmin()
            if gaps.loc[idx] > MAX_EARNINGS_GAP_DAYS:
                continue
            events.append({"ticker": t, "spike_week": anchor, "zscore": row["zscore"], "earnings_date": hist.loc[idx]})

    print(f"STRONG_EARNINGS candidate events in 2020: n={len(events)}\n")

    print("Pricing events (entry=anchor+2, exit=next trading day after earnings)...")
    rows = []
    for ev in events:
        t, anchor, earn_date = ev["ticker"], ev["spike_week"], ev["earnings_date"]
        daily = daily_cache.get(t, pd.DataFrame())
        ret_col = f"{t} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        if entry_date is None or earn_date < entry_date:
            continue
        sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
        if sigma is None:
            continue
        exit_date = next_trading_day_after(daily, earn_date)
        res = price_leg(daily, ret_col, entry_date, exit_date, sigma, near_earnings_markup)
        if res:
            rows.append({"ticker": t, "spike_week": anchor.date(), "zscore": ev["zscore"],
                         "earnings_date": earn_date.date(), "win": res["win"], "pnl_pct": res["pnl_pct"]})

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)

    n = len(result)
    print(f"\n=== 2020 COVID STRESS TEST RESULT ===")
    if n > 0:
        win_rate = result["win"].mean() * 100
        median_pnl = result["pnl_pct"].median()
        avg_pnl = result["pnl_pct"].mean()
        print(f"n events: {n}   win rate: {win_rate:.1f}%   median P&L: {median_pnl:+.1f}%   avg P&L: {avg_pnl:+.1f}%")
        print(f"\nComparison:")
        print(f"  2019: n=23  win=52.2%  median=+38.8%")
        print(f"  2020: n={n:<3} win={win_rate:.1f}%  median={median_pnl:+.1f}%   <- THIS TEST")
        print(f"  2021: n=22  win=77.3%  median=+121.5%")
        if win_rate < 40:
            verdict = "COLLAPSED"
        elif median_pnl < 0 and win_rate < 50:
            verdict = "INVERTED"
        elif win_rate >= 52.2 - 10:
            verdict = "HELD (roughly consistent with adjacent years)"
        else:
            verdict = "WEAKENED but not inverted"
        print(f"\nVerdict: signal {verdict} during COVID 2020.")
    else:
        print("n=0 -- no usable STRONG_EARNINGS events found in 2020 for these 15 tickers.")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
