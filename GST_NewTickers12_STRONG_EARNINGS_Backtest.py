#!/usr/bin/env python3
# STRONG_EARNINGS backtest — 12 new liquidity-clean tickers from the
# Russell-1000-proxy expansion (WHR, RMBS, CPRI, SOLS, PLNT, SGI, SFM,
# DOCS, PINS, BAH, GAP, AMKR). Reported SEPARATELY from the existing
# 425/51-ticker results per the request — not merged, so the mechanism can
# be checked on new names before folding them in.
#
# Replicates the EXACT methodology already used for the existing universe,
# reusing the same constants/formulas from their source scripts (not
# re-derived):
#   - Weekly GST pull cadence: "GST Weekly Data Gathering (2021-2025 Broad50
#     Clear).py" (per-year pulls, same sleep/retry pattern).
#   - Daily excess returns (ticker minus SPY): "Daily Excess Returns
#     (2021-2025 Broad50 Clear).py".
#   - Rolling z-score: GST_Build_Foundation_AllTickers.py (12-week trailing
#     window, min_periods=8, shifted so current week never leaks into its
#     own baseline).
#   - Spike identification + de-overlap: is_spike at z>=2.0 (base tier
#     threshold from GST_Live_Signal_Engine.py), then the same 21-day
#     minimum-gap de-dup rule as GST_Zscore_No_Overlaps_2021_2025_
#     Broad50Clear.py, so a single earnings reaction lingering across
#     consecutive weeks isn't double-counted as separate events.
#   - Near-earnings flag: symmetric +/-5-day window around the spike-week
#     anchor (GST_Earnings_Clustering_Test_2021_2025_Broad50Clear.py's
#     within_5d definition) — NOT the live engine's forward-only
#     days_to_earnings, since this is a historical/hindsight classification
#     like the rest of the backtest suite uses.
#   - STRONG_EARNINGS = deduped spike, zscore>=5, near_earnings=True (same
#     STRONG_TIER_Z_THRESHOLD=5.0 as GST_Live_Signal_Engine.py).
#   - Straddle pricing: Black-Scholes, calibrated near-earnings IV markup
#     (Earnings Clustering Test/iv_calibration_buckets.csv, mean=1.2398x
#     realized vol -- reused, not re-derived), COST_LOADING=1.05, entry =
#     anchor+2 days, exit = anchor+6 days ("end_of_spike_week" horizon,
#     the headline metric quoted throughout this project), nearest-
#     trading-day-on-or-before convention -- identical to
#     GST_Straddle_Simulation_2021_2025_51Ticker.py.
#
# Output: Small-Mid Cap Universe Expansion/NewTickers12_STRONG_EARNINGS_Results.csv
#         (event-level; NOT merged with the existing 425/51-ticker results)

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import random
import sys
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS = ["WHR", "RMBS", "CPRI", "SOLS", "PLNT", "SGI", "SFM", "DOCS", "PINS", "BAH", "GAP", "AMKR"]
YEARS = list(range(2021, 2026))
BENCH = "SPY"

GST_OUT_DIR = Path("GST Data") / "Weekly Data (New12 Liquidity-Clean)"
GST_OUT_DIR.mkdir(parents=True, exist_ok=True)
DAILY_OUT_DIR = Path("Daily Excess Return Data (New12 Liquidity-Clean)")
DAILY_OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR = Path("Small-Mid Cap Universe Expansion")
OUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_OUT = OUT_DIR / "NewTickers12_STRONG_EARNINGS_Results.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"

# --- GST pull constants (matches "GST Weekly Data Gathering (2021-2025 Broad50 Clear).py") ---
GEO, GPROP, CATEGORY = "US", "", 0
BETWEEN_YEARS = (1.0, 2.0)
BETWEEN_TICKERS = (1.5, 3.0)
BATCH_SIZE = 6
BATCH_PAUSE_S = 20
HARD_429_SLEEP = 60

# --- z-score / spike constants (matches GST_Build_Foundation_AllTickers.py / GST_Live_Signal_Engine.py) ---
ROLLING_WINDOW = 12
MIN_PERIODS = 8
BASE_SPIKE_Z_THRESHOLD = 2.0
STRONG_TIER_Z_THRESHOLD = 5.0
MIN_GAP_DAYS = 21          # GST_Zscore_No_Overlaps de-dup rule
EARNINGS_WINDOW_DAYS = 5   # symmetric within_5d, matches Earnings Clustering Test

# --- straddle pricing constants (matches GST_Straddle_Simulation_2021_2025_51Ticker.py) ---
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6   # "end_of_spike_week" horizon
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


# ============================== PHASE 1: GST PULL ==============================

def fetch_one_year(pt: TrendReq, term: str, year: int) -> pd.DataFrame:
    timeframe = f"{year}-01-01 {year}-12-31"
    for attempt in range(1, 6):
        try:
            pt.build_payload([term], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Week": df.index.date,
                term: pd.to_numeric(df[term], errors="coerce").fillna(0).round(0).astype(int),
                "isPartial": df["isPartial"].astype(bool)
            })
            out = out[(pd.to_datetime(out["Week"]).dt.year == year)]
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or "too many" in msg or "rate" in msg) else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"  [{term} {year}] attempt {attempt} failed: {e} — sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", term, "isPartial"])


def pull_weekly_gst():
    print("PHASE 1: pulling weekly GST 2021-2025 for 12 tickers...\n")
    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})
    for i, term in enumerate(TICKERS, start=1):
        for yr in YEARS:
            out_path = GST_OUT_DIR / f"{term}_{yr}.csv"
            if out_path.exists():
                continue
            df = fetch_one_year(pt, term, yr)
            if df.empty:
                out_path.write_text(f"Week,{term},isPartial\n", encoding="utf-8")
                print(f"  [{term}] {yr}: FAILED — header-only")
            else:
                df.to_csv(out_path, index=False, encoding="utf-8")
                print(f"  [{term}] {yr}: wrote {len(df)} weeks (max={int(df[term].max())})")
            time.sleep(random.uniform(*BETWEEN_YEARS))
        time.sleep(random.uniform(*BETWEEN_TICKERS))
        if i % BATCH_SIZE == 0 and i != len(TICKERS):
            print(f"  — batch pause ({BATCH_PAUSE_S}s) —")
            time.sleep(BATCH_PAUSE_S)
    print("\nGST pull complete.\n")


# ============================== PHASE 2: DAILY EXCESS RETURNS ==============================

def _dl_prices(ticker: str, start: str, end: str) -> pd.Series:
    df = yf.download(ticker, start=start, end=end, session=YF_SESSION,
                      auto_adjust=True, progress=False, group_by="column", threads=False)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    close = df["Close"] if "Close" in df.columns else df.squeeze("columns")
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return pd.Series(close.values, index=pd.to_datetime(close.index), name=ticker).sort_index()


def pull_daily_excess():
    print("PHASE 2: pulling daily prices (ticker + SPY) and computing excess returns...\n")
    for tkr in TICKERS:
        for yr in YEARS:
            out = DAILY_OUT_DIR / f"{tkr}_{yr}_excess.csv"
            if out.exists():
                continue
            start, end = f"{yr}-01-01", f"{yr+1}-01-01"
            s_tkr, s_spy = _dl_prices(tkr, start, end), _dl_prices(BENCH, start, end)
            if s_tkr.empty or s_spy.empty:
                pd.DataFrame(columns=["Date", f"{tkr} Daily Return", "SPY Daily Return", "Excess Daily Return"]).to_csv(out, index=False)
                continue
            r_tkr, r_spy = s_tkr.pct_change().dropna(), s_spy.pct_change().dropna()
            idx = r_tkr.index.intersection(r_spy.index)
            r_tkr, r_spy = r_tkr.loc[idx], r_spy.loc[idx]
            df = pd.DataFrame({"Date": idx, f"{tkr} Daily Return": r_tkr.round(4).values,
                                "SPY Daily Return": r_spy.round(4).values,
                                "Excess Daily Return": (r_tkr - r_spy).round(4).values})
            df.to_csv(out, index=False)
        print(f"  [{tkr}] daily excess returns done")
    print("\nDaily excess return pull complete.\n")


# ============================== PHASE 3: Z-SCORE + SPIKE DEDUP ==============================

def load_weekly_series(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = GST_OUT_DIR / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Week" not in df.columns or ticker not in df.columns:
            continue
        df = df.rename(columns={ticker: "gst"})[["Week", "gst"]]
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        frames.append(df.dropna(subset=["Week"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Week").reset_index(drop=True)


def compute_zscore(weekly: pd.DataFrame) -> pd.DataFrame:
    shifted = weekly["gst"].shift(1)
    roll = shifted.rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    z = (weekly["gst"] - roll.mean()) / roll.std()
    weekly["zscore"] = z.replace([np.inf, -np.inf], np.nan)
    return weekly


def dedupe_spikes(weekly: pd.DataFrame) -> pd.DataFrame:
    spikes = weekly[weekly["zscore"] >= BASE_SPIKE_Z_THRESHOLD].copy()
    spikes = spikes.dropna(subset=["Week"]).sort_values("Week").reset_index(drop=True)
    if spikes.empty:
        return spikes
    kept = [spikes.iloc[0]]
    last_date = spikes.iloc[0]["Week"]
    for _, row in spikes.iloc[1:].iterrows():
        if (row["Week"] - last_date).days >= MIN_GAP_DAYS:
            kept.append(row)
            last_date = row["Week"]
    return pd.DataFrame(kept).reset_index(drop=True)


# ============================== PHASE 4: EARNINGS DATES / NEAR-EARNINGS FLAG ==============================

def fetch_earnings_dates(ticker: str) -> list:
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        df = tk.get_earnings_dates(limit=100)
    except Exception as e:
        print(f"  [{ticker}] earnings pull failed: {e}")
        return []
    if df is None or df.empty:
        return []
    return sorted(pd.to_datetime(df.index).tz_localize(None).normalize().tolist())


def near_earnings_flag(anchor: pd.Timestamp, earnings_dates: list) -> bool:
    lo, hi = anchor - timedelta(days=EARNINGS_WINDOW_DAYS), anchor + timedelta(days=EARNINGS_WINDOW_DAYS)
    return any(lo <= ed <= hi for ed in earnings_dates)


# ============================== PHASE 5: STRADDLE PRICING ==============================

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
        p = DAILY_OUT_DIR / f"{ticker}_{year}_excess.csv"
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


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def price_event(daily, ret_col, anchor, markup):
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if entry_date is None or exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma is None:
        return None
    iv = sigma * markup
    T = dte_days / 365.0
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


def main():
    print("*** STRONG_EARNINGS BACKTEST — 12 NEW LIQUIDITY-CLEAN TICKERS (kept separate from 425) ***\n")

    pull_weekly_gst()
    pull_daily_excess()

    markup = load_calibrated_near_earnings_markup()
    print(f"Using calibrated near-earnings IV markup: {markup:.4f}x realized vol (reused, not re-derived)\n")

    print("PHASE 3+4: z-score, spike de-dup, earnings dates, near-earnings flag...\n")
    all_events = []
    for ticker in TICKERS:
        weekly = load_weekly_series(ticker)
        if weekly.empty:
            print(f"  [{ticker}] no GST data, skipping")
            continue
        weekly = compute_zscore(weekly)
        deduped = dedupe_spikes(weekly)
        earnings_dates = fetch_earnings_dates(ticker)
        time.sleep(0.5)

        n_strong = 0
        for _, row in deduped.iterrows():
            if pd.isna(row["zscore"]) or row["zscore"] < STRONG_TIER_Z_THRESHOLD:
                continue
            near = near_earnings_flag(row["Week"], earnings_dates)
            if not near:
                continue
            n_strong += 1
            all_events.append({"ticker": ticker, "spike_week": row["Week"], "zscore": row["zscore"], "near_earnings": near})
        print(f"  [{ticker}] {len(deduped)} deduped spikes (z>={BASE_SPIKE_Z_THRESHOLD:g}) -> "
              f"{n_strong} STRONG_EARNINGS candidates (z>={STRONG_TIER_Z_THRESHOLD:g} + near_earnings)")

    print(f"\nTotal STRONG_EARNINGS candidate events across 12 tickers: {len(all_events)}\n")

    print("PHASE 5: pricing each event (Black-Scholes straddle, earnings-aware IV)...\n")
    daily_cache = {t: load_daily_excess(t) for t in TICKERS}
    results = []
    for ev in all_events:
        daily = daily_cache.get(ev["ticker"], pd.DataFrame())
        ret_col = f"{ev['ticker']} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        priced = price_event(daily, ret_col, ev["spike_week"], markup)
        if priced is None:
            continue
        results.append({**ev, **priced})

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df["spike_week"] = pd.to_datetime(results_df["spike_week"]).dt.date
    results_df.to_csv(RESULTS_OUT, index=False)
    print(f"Wrote: {RESULTS_OUT}\n")

    print("=== RESULTS (12 new liquidity-clean tickers, kept SEPARATE from the existing 425/51-ticker results) ===")
    n = len(results_df)
    print(f"Usable priced STRONG_EARNINGS events: n={n}")
    if n == 0:
        print("No priceable STRONG_EARNINGS events found for this ticker set in 2021-2025.")
        return
    win_rate = results_df["win"].mean() * 100
    median_pnl = results_df["pnl_pct"].median()
    avg_pnl = results_df["pnl_pct"].mean()
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Median P&L (model-priced): {median_pnl:+.1f}%")
    print(f"Mean P&L (model-priced): {avg_pnl:+.1f}%")
    print(f"\nPer-ticker breakdown:")
    print(results_df.groupby("ticker").agg(n=("win", "size"), win_rate_pct=("win", lambda x: round(x.mean()*100, 1)),
                                            median_pnl_pct=("pnl_pct", lambda x: round(x.median(), 1))).to_string())
    print(f"\n--- For comparison (NOT merged) — existing 425/51-ticker STRONG_EARNINGS baseline: "
          f"n=147, win=76.2%, median=+130.0% ---")


if __name__ == "__main__":
    main()
