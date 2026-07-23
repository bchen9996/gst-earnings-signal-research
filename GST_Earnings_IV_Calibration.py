#!/usr/bin/env python3
# GST Earnings IV Calibration — derives a data-driven (not arbitrary)
# earnings-proximity IV markup for the straddle pricing model, instead of
# the flat, disclosed-as-a-guess 1.10x used in GST_Straddle_Profitability_Test.py.
#
# For each ticker with an earnings date on the calendar, pulls the real
# option chain for the expiration nearest to (and covering) that earnings
# date — or, for tickers with no earnings in the next 45 days, the nearest
# available expiration as a "no imminent catalyst" control point — and
# computes markup_ratio = real market ATM implied vol / trailing 60-day
# realized vol (NO markup baked in, so this ratio IS the raw empirical
# markup). Recording days_to_earnings alongside each point gives more than
# one calibration point across the distance spectrum, instead of a single
# flat number.
#
# Combines this new pull with the earlier n=4 earnings-adjacent sample from
# GST_ModelVsMarket_Sanity_Check.py (re-derived onto the same raw-ratio
# basis) for a slightly larger combined calibration set.
#
# *** THIS IS A SMALL, NOISY, LIVE-MARKET CALIBRATION SAMPLE — NOT A
# VALIDATED HISTORICAL RELATIONSHIP. *** It reflects option pricing on ONE
# day (today), for tickers/expirations that happen to be available right
# now. Treat the resulting bucketed markups as a better-than-nothing,
# data-grounded estimate, not a confirmed, stable relationship.
#
# Output: Earnings Clustering Test/iv_calibration_points.csv
#         Earnings Clustering Test/iv_calibration_buckets.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import math
import sys
import urllib3
import requests
import numpy as np
import pandas as pd
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

CALIBRATION_TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "NFLX", "ADBE", "NKE",
    "SBUX", "INTC", "TTWO", "QCOM", "GME", "EBAY", "ABBV", "ADP", "ALB",
    "ALLE", "HD", "JBL", "KO", "LOW", "MCHP", "MDT", "RTX", "SYK", "T",
    "VZ", "XOM",
]

VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
NO_EARNINGS_HORIZON_DAYS = 45   # beyond this, treat as a "no imminent catalyst" control point

OUT_DIR = Path("Earnings Clustering Test")

# Bucket edges on days_to_earnings. MIN_DTE=7 means every "near earnings" pick is
# already >=7 days out by construction, so a finer 0-3d/4-7d split is empty by
# design — the real, data-driven split is the NO_EARNINGS_HORIZON_DAYS=45 cutoff
# itself: <=45d picks were deliberately chosen to span an upcoming earnings date,
# >45d picks are "no imminent catalyst" controls.
BUCKET_EDGES = [(-1, 45, "near earnings (<=45d, spans earnings date)"), (45, 9999, "far / no imminent earnings")]

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


MIN_DTE = 7   # avoid noisy/illiquid near-zero-DTE weekly options for ALL picks, near-earnings or not


def pick_expiration_near_earnings(expirations: list[str], today, next_earnings):
    exp_dates = [(e, datetime.strptime(e, "%Y-%m-%d").date()) for e in expirations]
    exp_dates = [(e, d) for e, d in exp_dates if (d - today).days >= MIN_DTE]
    if not exp_dates:
        return None, None, None

    if next_earnings is not None and (next_earnings - today).days <= NO_EARNINGS_HORIZON_DAYS:
        after = [(e, d) for e, d in exp_dates if d >= next_earnings]
        if after:
            e, d = min(after, key=lambda x: (x[1] - next_earnings).days)
            return e, d, (next_earnings - today).days

    # no imminent earnings within horizon (or none found on/after) -> nearest DTE>=MIN_DTE expiration, control point
    e, d = min(exp_dates, key=lambda x: x[1])
    gap = (next_earnings - today).days if next_earnings is not None else 9999
    return e, d, gap


def mid_price(row):
    bid, ask, last = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    return float(last) if last is not None and last > 0 else None


def bucket_for(days_to_earnings):
    for lo, hi, label in BUCKET_EDGES:
        if lo < days_to_earnings <= hi:
            return label
    return BUCKET_EDGES[-1][2]


def pull_new_calibration_points() -> list[dict]:
    today = datetime.now(timezone.utc).date()
    rows = []

    for ticker in CALIBRATION_TICKERS:
        tk = yf.Ticker(ticker, session=SESSION)
        try:
            spot = tk.fast_info.get("lastPrice")
            hist = tk.history(period="1y", auto_adjust=True)
        except Exception as e:
            print(f"[{ticker}] spot/history failed: {e}")
            continue
        if not spot or hist.empty:
            continue

        daily_ret = hist["Close"].pct_change().dropna()
        trailing = daily_ret.tail(VOL_LOOKBACK_TRADING_DAYS)
        if len(trailing) < MIN_VOL_HISTORY_DAYS:
            continue
        trailing_vol = float(trailing.std() * math.sqrt(252))

        try:
            earnings_df = tk.get_earnings_dates(limit=12)
            future = sorted(d.date() for d in pd.to_datetime(earnings_df.index).tz_localize(None).normalize()
                             if d.date() >= today) if earnings_df is not None else []
            next_earnings = future[0] if future else None
        except Exception:
            next_earnings = None

        try:
            expirations = list(tk.options)
        except Exception as e:
            print(f"[{ticker}] no options: {e}")
            continue

        picked = pick_expiration_near_earnings(expirations, today, next_earnings)
        if picked[0] is None:
            continue
        expiration, exp_date, days_to_earnings = picked

        try:
            chain = tk.option_chain(expiration)
        except Exception as e:
            print(f"[{ticker}] chain fetch failed: {e}")
            continue
        calls, puts = chain.calls, chain.puts
        if calls.empty or puts.empty:
            continue

        atm_strike = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]["strike"].values[0]
        call_row = calls[calls["strike"] == atm_strike]
        put_row = puts[puts["strike"] == atm_strike]
        if call_row.empty or put_row.empty:
            continue
        call_row, put_row = call_row.iloc[0], put_row.iloc[0]
        real_avg_iv = np.nanmean([call_row.get("impliedVolatility"), put_row.get("impliedVolatility")])
        if pd.isna(real_avg_iv) or real_avg_iv <= 0:
            continue

        markup_ratio = real_avg_iv / trailing_vol
        dte = (exp_date - today).days

        print(f"[{ticker}] days_to_earnings={days_to_earnings} dte={dte} "
              f"real_iv={real_avg_iv*100:.1f}% trailing_vol={trailing_vol*100:.1f}% "
              f"markup_ratio={markup_ratio:.3f}")

        rows.append({
            "ticker": ticker, "source": "live_pull_today", "days_to_earnings": days_to_earnings,
            "expiration": expiration, "dte": dte, "real_avg_iv_pct": round(real_avg_iv * 100, 2),
            "trailing_vol_pct": round(trailing_vol * 100, 2), "markup_ratio": round(markup_ratio, 4),
        })

    return rows


def load_prior_sanity_check_points() -> list[dict]:
    """Re-derive the original n=6 (4 earnings-adjacent + 2 control) sample onto the raw markup_ratio basis."""
    p = OUT_DIR / "model_vs_market_sanity_check.csv"
    if not p.exists():
        print("No prior model_vs_market_sanity_check.csv found — skipping that calibration source.")
        return []
    df = pd.read_csv(p)
    rows = []
    for _, r in df.iterrows():
        # model_iv_pct = trailing_vol_raw * 1.10 (IV_MARKUP baked in by that script) -> back it out
        trailing_vol_raw_pct = r["model_iv_pct"] / 1.10
        markup_ratio = r["real_avg_iv_pct"] / trailing_vol_raw_pct
        if pd.isna(r["next_earnings_date"]):
            days_to_earnings = 9999
        else:
            next_earn = pd.to_datetime(r["next_earnings_date"]).date()
            today = datetime.now(timezone.utc).date()
            days_to_earnings = (next_earn - today).days
        rows.append({
            "ticker": r["ticker"], "source": "prior_sanity_check", "days_to_earnings": days_to_earnings,
            "expiration": r["expiration"], "dte": r["dte"], "real_avg_iv_pct": r["real_avg_iv_pct"],
            "trailing_vol_pct": round(trailing_vol_raw_pct, 2), "markup_ratio": round(markup_ratio, 4),
        })
    return rows


def main():
    print("Pulling new calibration points across a range of days-to-earnings...\n")
    new_points = pull_new_calibration_points()
    prior_points = load_prior_sanity_check_points()

    all_points = pd.DataFrame(new_points + prior_points)
    points_path = OUT_DIR / "iv_calibration_points.csv"
    all_points.to_csv(points_path, index=False)

    all_points["bucket"] = all_points["days_to_earnings"].apply(bucket_for)

    bucket_summary = (all_points.groupby("bucket")["markup_ratio"]
                       .agg(["mean", "median", "std", "count"])
                       .reindex([b[2] for b in BUCKET_EDGES]))
    bucket_path = OUT_DIR / "iv_calibration_buckets.csv"
    bucket_summary.to_csv(bucket_path)

    print(f"\nTotal calibration points: {len(all_points)} "
          f"({len(new_points)} new live pulls + {len(prior_points)} from the prior sanity check)\n")
    print("--- Markup ratio (real IV / trailing realized vol) by days-to-earnings bucket ---")
    print(bucket_summary.to_string())
    print(f"\n*** SMALL SAMPLE — this is a live, single-day snapshot, not a validated historical "
          f"relationship. Bucket means with count<5 are especially noisy. ***")
    print(f"\nWrote calibration points to: {points_path}")
    print(f"Wrote bucket summary to: {bucket_path}")


if __name__ == "__main__":
    main()
