#!/usr/bin/env python3
# TASK 3 — Price/volume anomaly signal infrastructure. All on-disk data,
# no new pulls: reuses this project's existing daily excess-return and
# daily-volume files.
#
#   (a) volume_anomaly = mean daily volume in the 14 days before
#       earnings_date / mean daily volume in the 15-60 days before
#       earnings_date (two adjacent, non-overlapping windows, both
#       strictly before earnings_date)
#   (b) price_momentum = cumulative return in the 14 days before
#       earnings_date, expressed as a PERCENTILE RANK against that
#       ticker's own historical pre-earnings 14-day-return distribution
#
#   price_volume_score = (volume_anomaly - 1) + abs(price_momentum_percentile - 0.5) * 2
#
# *** POINT-IN-TIME DISCLOSURE ***
# The historical distribution used for the percentile rank in (b) is built
# ONLY from this ticker's earnings dates STRICTLY BEFORE the one being
# scored (an expanding window, exactly like this project's z-score
# shift(1).rolling() convention elsewhere) — never from future earnings
# dates. Events with fewer than MIN_HISTORY_EVENTS prior dates return
# price_momentum_percentile=None and are flagged insufficient_history,
# rather than silently using a too-small or look-ahead-contaminated
# reference distribution.
#
# Data coverage note: on-disk daily volume only goes back to 2020-09-01
# (Daily Volume Data (2021-2025)/), so a ticker's usable "historical
# distribution" effectively starts around early-to-mid 2021, regardless of
# how far back its earnings-date list goes.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd

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
DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})
YEARS = list(range(2021, 2026))
VOLUME_DIR = Path("Daily Volume Data (2021-2025)")
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"

RECENT_WINDOW_DAYS = 14
BASELINE_WINDOW_START_DAYS = 60
BASELINE_WINDOW_END_DAYS = 15
MIN_HISTORY_EVENTS = 4

_daily_cache: dict[str, pd.DataFrame] = {}
_volume_cache: dict[str, pd.DataFrame] = {}
_earnings_cache: dict[str, pd.Series] | None = None


def _load_daily_excess(ticker: str) -> pd.DataFrame:
    if ticker in _daily_cache:
        return _daily_cache[ticker]
    frames = []
    for year in YEARS:
        p = DAILY_DIRS.get(ticker, Path(".")) / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    out = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True) if frames else pd.DataFrame()
    _daily_cache[ticker] = out
    return out


def _load_volume(ticker: str) -> pd.DataFrame:
    if ticker in _volume_cache:
        return _volume_cache[ticker]
    p = VOLUME_DIR / f"{ticker}_volume.csv"
    if not p.exists():
        out = pd.DataFrame(columns=["Date", "Volume"])
    else:
        df = pd.read_csv(p)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        out = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    _volume_cache[ticker] = out
    return out


def _load_earnings_dates() -> dict[str, pd.Series]:
    global _earnings_cache
    if _earnings_cache is not None:
        return _earnings_cache
    e = pd.read_csv(EARNINGS_PATH)
    e["earnings_date"] = pd.to_datetime(e["earnings_date"])
    _earnings_cache = {t: g["earnings_date"].sort_values().reset_index(drop=True) for t, g in e.groupby("ticker")}
    return _earnings_cache


def _pre_earnings_14d_return(ticker: str, earnings_date: pd.Timestamp, daily: pd.DataFrame, ret_col: str) -> float | None:
    window_start = earnings_date - timedelta(days=RECENT_WINDOW_DAYS)
    mask = (daily["Date"] >= window_start) & (daily["Date"] < earnings_date)
    rets = daily.loc[mask, ret_col]
    if rets.empty:
        return None
    return float((1 + rets).prod() - 1)


def compute_price_volume_score(ticker: str, earnings_date) -> dict:
    ticker = ticker.upper()
    earnings_date = pd.Timestamp(earnings_date)
    daily = _load_daily_excess(ticker)
    volume = _load_volume(ticker)
    ret_col = f"{ticker} Daily Return"

    result = {"ticker": ticker, "earnings_date": earnings_date.date(), "volume_anomaly": None,
              "price_momentum_return": None, "price_momentum_percentile": None,
              "n_history_events": 0, "insufficient_history": True, "price_volume_score": None}

    if daily.empty or ret_col not in daily.columns or volume.empty:
        return result

    # --- (a) volume anomaly ---
    recent_start = earnings_date - timedelta(days=RECENT_WINDOW_DAYS)
    recent_mask = (volume["Date"] >= recent_start) & (volume["Date"] < earnings_date)
    recent_vol = volume.loc[recent_mask, "Volume"]

    baseline_start = earnings_date - timedelta(days=BASELINE_WINDOW_START_DAYS)
    baseline_end = earnings_date - timedelta(days=BASELINE_WINDOW_END_DAYS)
    baseline_mask = (volume["Date"] >= baseline_start) & (volume["Date"] < baseline_end)
    baseline_vol = volume.loc[baseline_mask, "Volume"]

    if not recent_vol.empty and not baseline_vol.empty and baseline_vol.mean() > 0:
        volume_anomaly = float(recent_vol.mean() / baseline_vol.mean())
        result["volume_anomaly"] = round(volume_anomaly, 4)

    # --- (b) price momentum percentile, point-in-time (expanding window) ---
    current_return = _pre_earnings_14d_return(ticker, earnings_date, daily, ret_col)
    result["price_momentum_return"] = round(current_return, 4) if current_return is not None else None

    earnings_by_ticker = _load_earnings_dates()
    hist_dates = earnings_by_ticker.get(ticker, pd.Series(dtype="datetime64[ns]"))
    prior_dates = hist_dates[hist_dates < earnings_date]

    historical_returns = []
    for d in prior_dates:
        r = _pre_earnings_14d_return(ticker, d, daily, ret_col)
        if r is not None:
            historical_returns.append(r)

    result["n_history_events"] = len(historical_returns)
    if current_return is not None and len(historical_returns) >= MIN_HISTORY_EVENTS:
        hist_arr = np.array(historical_returns)
        percentile = float((hist_arr <= current_return).mean())
        result["price_momentum_percentile"] = round(percentile, 4)
        result["insufficient_history"] = False

    # --- combined score ---
    if result["volume_anomaly"] is not None and result["price_momentum_percentile"] is not None:
        score = (result["volume_anomaly"] - 1) + abs(result["price_momentum_percentile"] - 0.5) * 2
        result["price_volume_score"] = round(score, 4)

    return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(compute_price_volume_score("MSFT", "2023-07-25"))
