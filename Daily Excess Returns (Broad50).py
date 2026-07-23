#!/usr/bin/env python3
# Daily Excess Returns (yfinance) — Broad50 generalization test. Same
# ticker/stock-minus-SPY methodology as Daily Excess Returns.py, applied to
# the 50-ticker Broad50 sample instead of the original 15.
#
# Adds a custom requests session with verify=False (local AVG web-shield
# SSL interception breaks cert verification on this machine — same issue
# handled elsewhere in this project); the original script didn't need this
# since its data predates hitting that issue on this machine.
#
# Writes: Daily Excess Return Data (Broad50)/<TICKER>_<YEAR>_excess.csv

from __future__ import annotations
from pathlib import Path
from typing import List
import sys
import urllib3
import requests
import pandas as pd
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS: List[str] = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'ARE', 'AVB', 'BKR', 'BRK-B', 'BRO', 'CCL',
    'CI', 'CL', 'COF', 'COHR', 'CTSH', 'CTVA', 'DELL', 'DVN', 'EL', 'ERIE',
    'FE', 'GPC', 'GPN', 'HD', 'JBL', 'KO', 'LDOS', 'LNT', 'LOW', 'MCHP',
    'MCK', 'MDT', 'NCLH', 'NI', 'PKG', 'PLD', 'PM', 'PNW', 'RCL', 'REG',
    'ROP', 'RTX', 'STZ', 'SYF', 'SYK', 'T', 'TT', 'UAL', 'VZ', 'XOM',
]
YEARS = list(range(2014, 2020))
BENCH = "SPY"
OUTDIR = Path("Daily Excess Return Data (Broad50)")
OUTDIR.mkdir(parents=True, exist_ok=True)

RAW_DP = 4
PCT_DP = 3

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def _fmt_pct(x: float) -> str:
    return f"{x*100:.{PCT_DP}f}%"

def _dl_prices(ticker: str, start: str, end: str) -> pd.Series:
    df = yf.download(
        ticker, start=start, end=end, session=SESSION,
        auto_adjust=True, progress=False, group_by="column", threads=False
    )
    if df is None or df.empty:
        return pd.Series(dtype=float)

    close = None
    if "Close" in df.columns:
        close = df["Close"]
    elif "Adj Close" in df.columns:
        close = df["Adj Close"]
    else:
        close = df.squeeze("columns")

    if isinstance(close, pd.DataFrame):
        if close.shape[1] == 1:
            close = close.iloc[:, 0]
        else:
            close = close.iloc[:, 0]

    s = pd.Series(close.values, index=pd.to_datetime(close.index), name=ticker).sort_index()
    return s

def _daily_returns(s: pd.Series) -> pd.Series:
    return s.pct_change().dropna()

def _one_year_df(tkr: str, year: int) -> pd.DataFrame:
    start = f"{year}-01-01"
    end   = f"{year+1}-01-01"

    s_tkr = _dl_prices(tkr, start, end)
    s_spy = _dl_prices(BENCH, start, end)

    if s_tkr.empty or s_spy.empty:
        return pd.DataFrame(columns=[
            "Date", f"{tkr} Daily Return", "SPY Daily Return", "Excess Daily Return",
            f"{tkr} Daily Return (%)", "SPY Daily Return (%)", "Excess Daily Return (%)"
        ])

    r_tkr = _daily_returns(s_tkr)
    r_spy = _daily_returns(s_spy)

    idx = r_tkr.index.intersection(r_spy.index)
    r_tkr = r_tkr.loc[idx]
    r_spy = r_spy.loc[idx]
    r_exc = (r_tkr - r_spy)

    df = pd.DataFrame({
        "Date": idx,
        f"{tkr} Daily Return": r_tkr.round(RAW_DP).values,
        "SPY Daily Return":   r_spy.round(RAW_DP).values,
        "Excess Daily Return": r_exc.round(RAW_DP).values,
    })

    df[f"{tkr} Daily Return (%)]"] = [ _fmt_pct(x) for x in r_tkr.values ]
    df["SPY Daily Return (%)"]     = [ _fmt_pct(x) for x in r_spy.values ]
    df["Excess Daily Return (%)"]  = [ _fmt_pct(x) for x in r_exc.values ]

    df = df[[
        "Date",
        f"{tkr} Daily Return", "SPY Daily Return", "Excess Daily Return",
        f"{tkr} Daily Return (%)]", "SPY Daily Return (%)", "Excess Daily Return (%)"
    ]]

    return df.reset_index(drop=True)

def main():
    for tkr in TICKERS:
        for yr in YEARS:
            out = OUTDIR / f"{tkr}_{yr}_excess.csv"
            df = _one_year_df(tkr, yr)
            df.to_csv(out, index=False, encoding="utf-8")
            print(f"[{tkr} {yr}] wrote {len(df):4d} rows → {out.name}")
    print("\nDone. Files saved in:", OUTDIR.resolve())

if __name__ == "__main__":
    main()
