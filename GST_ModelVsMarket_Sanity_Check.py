#!/usr/bin/env python3
# GST Model-vs-Market Sanity Check — how far off is the straddle
# simulation's pricing model from real market prices, right now?
#
# For a handful of tickers, pulls the REAL current option chain (nearest
# expiration >=21 DTE, same convention as GST_Live_Straddle_Logger.py) and
# compares the real market ATM straddle cost / implied vol against what
# GST_Straddle_Profitability_Test.py's model would have charged for the
# same spot/strike/DTE: trailing 60-trading-day realized vol x 1.10
# markup, priced with the same Black-Scholes formula. Also checks whether
# an earnings date falls within the option's DTE window, to connect any
# gap directly back to GST_Earnings_Clustering_Test.py's finding.

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

TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GME"]

TARGET_MIN_DTE = 21
VOL_LOOKBACK_TRADING_DAYS = 60
IV_MARKUP = 1.10
RISK_FREE_RATE = 0.02

OUT_DIR = Path("Earnings Clustering Test")

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def pick_expiration(expirations, today):
    candidates = [(e, (datetime.strptime(e, "%Y-%m-%d").date() - today).days) for e in expirations]
    eligible = [c for c in candidates if c[1] >= TARGET_MIN_DTE]
    return min(eligible, key=lambda c: c[1]) if eligible else (max(candidates, key=lambda c: c[1]) if candidates else None)


def mid_price(row):
    bid, ask, last = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    return float(last) if last is not None and last > 0 else None


def main():
    today = datetime.now(timezone.utc).date()
    rows = []

    for ticker in TICKERS:
        print(f"\n[{ticker}]")
        tk = yf.Ticker(ticker, session=SESSION)

        try:
            spot = tk.fast_info.get("lastPrice")
            hist = tk.history(period="1y", auto_adjust=True)
        except Exception as e:
            print(f"  history/spot fetch failed: {e}")
            continue
        if not spot or hist.empty:
            print("  no spot price or history")
            continue

        daily_ret = hist["Close"].pct_change().dropna()
        trailing_hist = daily_ret.tail(VOL_LOOKBACK_TRADING_DAYS)
        if len(trailing_hist) < 30:
            print("  insufficient trailing history")
            continue
        model_sigma = float(trailing_hist.std() * math.sqrt(252)) * IV_MARKUP

        try:
            expirations = tk.options
        except Exception as e:
            print(f"  no options chain: {e}")
            continue
        picked = pick_expiration(list(expirations), today)
        if picked is None:
            print("  no usable expiration")
            continue
        expiration, dte = picked

        try:
            chain = tk.option_chain(expiration)
        except Exception as e:
            print(f"  chain fetch failed: {e}")
            continue
        calls, puts = chain.calls, chain.puts
        if calls.empty or puts.empty:
            print("  empty chain")
            continue

        atm_strike = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]["strike"].values[0]
        call_row = calls[calls["strike"] == atm_strike]
        put_row = puts[puts["strike"] == atm_strike]
        if call_row.empty or put_row.empty:
            print("  no matching ATM strike")
            continue
        call_row, put_row = call_row.iloc[0], put_row.iloc[0]

        real_call_mid = mid_price(call_row)
        real_put_mid = mid_price(put_row)
        if real_call_mid is None or real_put_mid is None:
            print("  no usable quote")
            continue
        real_straddle_cost = real_call_mid + real_put_mid
        real_avg_iv = np.nanmean([call_row.get("impliedVolatility"), put_row.get("impliedVolatility")])

        T = dte / 365.0
        model_straddle_price = bs_straddle_price(spot, atm_strike, T, RISK_FREE_RATE, model_sigma)

        try:
            earnings_df = tk.get_earnings_dates(limit=12)
            upcoming = pd.to_datetime(earnings_df.index).tz_localize(None).normalize() if earnings_df is not None else []
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
            earnings_in_window = any(today <= d.date() <= exp_date for d in upcoming)
            next_earnings = min([d for d in upcoming if d.date() >= today], default=None)
        except Exception:
            earnings_in_window = None
            next_earnings = None

        gap_dollars = real_straddle_cost - model_straddle_price
        gap_pct = gap_dollars / model_straddle_price * 100

        print(f"  spot=${spot:.2f}  strike={atm_strike}  exp={expiration} (DTE={dte})")
        print(f"  REAL market straddle: ${real_straddle_cost:.2f}  (avg IV: {real_avg_iv*100:.1f}%)")
        print(f"  MODEL straddle (trailing vol x{IV_MARKUP}): ${model_straddle_price:.2f}  (model IV: {model_sigma*100:.1f}%)")
        print(f"  Gap: ${gap_dollars:+.2f}  ({gap_pct:+.1f}% vs model)")
        print(f"  Earnings within DTE window: {earnings_in_window}   Next earnings: "
              f"{next_earnings.date() if next_earnings is not None else 'unknown'}")

        rows.append({
            "ticker": ticker, "spot": spot, "strike": atm_strike, "expiration": expiration, "dte": dte,
            "real_straddle_cost": round(real_straddle_cost, 3), "real_avg_iv_pct": round(real_avg_iv * 100, 2),
            "model_straddle_cost": round(model_straddle_price, 3), "model_iv_pct": round(model_sigma * 100, 2),
            "gap_dollars": round(gap_dollars, 3), "gap_pct_vs_model": round(gap_pct, 1),
            "earnings_within_dte_window": earnings_in_window,
            "next_earnings_date": next_earnings.date() if next_earnings is not None else None,
        })

    if not rows:
        print("\nNo usable comparisons.")
        return

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "model_vs_market_sanity_check.csv"
    results.to_csv(out_path, index=False)

    print(f"\n{'='*70}")
    print(f"Mean gap: real market straddles priced {results['gap_pct_vs_model'].mean():+.1f}% "
          f"vs the model on average (n={len(results)})")
    with_earn = results[results["earnings_within_dte_window"] == True]  # noqa: E712
    without_earn = results[results["earnings_within_dte_window"] == False]  # noqa: E712
    if not with_earn.empty:
        print(f"  Tickers WITH earnings in the DTE window: mean gap {with_earn['gap_pct_vs_model'].mean():+.1f}% (n={len(with_earn)})")
    if not without_earn.empty:
        print(f"  Tickers WITHOUT earnings in the DTE window: mean gap {without_earn['gap_pct_vs_model'].mean():+.1f}% (n={len(without_earn)})")

    print(f"\nWrote results to: {out_path}")


if __name__ == "__main__":
    main()
