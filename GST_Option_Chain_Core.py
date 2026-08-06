#!/usr/bin/env python3
# Dependency-light option-chain core.
#
# WHY THIS MODULE EXISTS
#
# get_nearest_post_earnings_expiry() and get_option_snapshot() were defined in
# GST_MultiTicker_Forward_Log.py, which is a live execution entry point: at
# import time it pulls in pytrends, the live GST signal engine, requests and
# urllib3, disables warnings, and reconfigures sys.stdout. Anything that wanted
# just these two option helpers had to drag that entire runtime in with them.
#
# That is exactly what broke the first real GitHub Actions run of
# PR #3 (run 31126964980): importing gst_market_response.option_chain_adapter
# reached GST_MultiTicker_Forward_Log line 46, `from pytrends.request import
# TrendReq`, and failed with ModuleNotFoundError. requirements.txt covers the
# gst_market_response package only and deliberately excludes the wider legacy
# GST stack, so the correct fix is to break the import edge -- not to install
# Google Trends into a module that never queries Google Trends.
#
# The two functions below are moved here VERBATIM. No logic, threshold,
# fallback, expiry rule, strike rule, or field extraction was changed:
#   * nearest expiration is strictly after earnings_date (`> earnings_date`)
#   * ATM strike remains min(abs(strike - spot)) via idxmin()
#   * the same try/except behaviour: a failed .options returns None, a failed
#     .option_chain() returns {"option_chain_error": str(e)}
#   * the same bid/ask/bid_size/ask_size/open_interest/volume/
#     implied_volatility extraction, with the same pd.notna() guards and the
#     same float/int casts
#
# Imports are limited to what these two functions genuinely need: datetime,
# pandas, and yfinance (the latter only for the yf.Ticker annotation). This
# module must never import pytrends, GST_Live_Signal_Engine, the daily panel,
# or any live execution entry point -- enforced by
# test_market_response_dependency_boundary.py. It performs no network call at
# import time; both functions act only on the yfinance Ticker handed to them.
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import yfinance as yf


def get_nearest_post_earnings_expiry(tk: yf.Ticker, earnings_date: date) -> str | None:
    try:
        expirations = tk.options
    except Exception:
        return None
    if not expirations:
        return None
    candidates = [e for e in expirations if datetime.strptime(e, "%Y-%m-%d").date() > earnings_date]
    return min(candidates) if candidates else None


def get_option_snapshot(tk: yf.Ticker, expiry: str, spot: float) -> dict:
    result = {}
    try:
        chain = tk.option_chain(expiry)
    except Exception as e:
        result["option_chain_error"] = str(e)
        return result
    for label, chain_df in [("call", chain.calls), ("put", chain.puts)]:
        if chain_df.empty:
            continue
        idx = (chain_df["strike"] - spot).abs().idxmin()
        row = chain_df.loc[idx]
        result[f"{label}_strike"] = float(row["strike"])
        result[f"{label}_bid"] = float(row["bid"]) if pd.notna(row.get("bid")) else None
        result[f"{label}_ask"] = float(row["ask"]) if pd.notna(row.get("ask")) else None
        result[f"{label}_bid_size"] = int(row["bidSize"]) if pd.notna(row.get("bidSize")) else None
        result[f"{label}_ask_size"] = int(row["askSize"]) if pd.notna(row.get("askSize")) else None
        result[f"{label}_open_interest"] = int(row["openInterest"]) if pd.notna(row.get("openInterest")) else None
        result[f"{label}_volume"] = int(row["volume"]) if pd.notna(row.get("volume")) else None
        result[f"{label}_implied_volatility"] = float(row["impliedVolatility"]) if pd.notna(row.get("impliedVolatility")) else None
    return result


__all__ = ["get_nearest_post_earnings_expiry", "get_option_snapshot"]
