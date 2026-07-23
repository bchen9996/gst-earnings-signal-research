#!/usr/bin/env python3
# TASK 2 — Sector effects: does the STRONG_EARNINGS (z>=5) edge concentrate
# in particular GICS sectors? Sector classification is a new, lightweight
# yfinance pull (51 tickers, one call each, cached) — the underlying
# STRONG_EARNINGS event/pricing data itself is 100% existing on-disk data,
# not re-pulled.
#
# Output: Live Signal Engine/Task2_SectorEffects_Results.csv

from __future__ import annotations
from pathlib import Path
import sys, time
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task2_SectorEffects_Results.csv"

Z_THRESHOLD = 5.0
MIN_N_WARN = 10

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_sector(ticker: str, max_attempts: int = 3) -> str | None:
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            info = tk.info
            sector = info.get("sector")
            if sector:
                return sector
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            time.sleep(5)
    return None


def main():
    print(f"*** TASK 2: Sector effects (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    tickers = sorted(events["ticker"].unique())
    print(f"z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)} across {len(tickers)} tickers\n")

    print("Pulling GICS sector per ticker (cached, one pull each)...")
    sector_map = {}
    for i, ticker in enumerate(tickers, start=1):
        sector = fetch_sector(ticker)
        sector_map[ticker] = sector or "UNKNOWN"
        print(f"  [{i}/{len(tickers)}] {ticker}: {sector_map[ticker]}")
        time.sleep(0.8)
    print()

    events["sector"] = events["ticker"].map(sector_map)
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    rows = []
    for sector, sub in events.groupby("sector"):
        usable = sub[sub[win_col].notna()]
        n = len(usable)
        if n == 0:
            continue
        wr = usable[win_col].mean() * 100
        avg = usable[pnl_col].mean()
        med = usable[pnl_col].median()
        underpowered = n < MIN_N_WARN
        rows.append({
            "sector": sector, "n": n, "win_rate_pct": round(wr, 1),
            "avg_pnl_pct": round(avg, 1), "median_pnl_pct": round(med, 1),
            "underpowered_n_lt_10": underpowered,
            "tickers": ", ".join(sorted(sub["ticker"].unique())),
        })

    result = pd.DataFrame(rows).sort_values("n", ascending=False)
    result.to_csv(OUT_PATH, index=False)

    print("=== SECTOR BREAKDOWN (spike_week horizon) ===")
    for _, r in result.iterrows():
        flag = "  [UNDERPOWERED n<10]" if r["underpowered_n_lt_10"] else ""
        print(f"{r['sector']:<25} n={r['n']:<4} win={r['win_rate_pct']:5.1f}%  "
              f"avg={r['avg_pnl_pct']:+7.1f}%  median={r['median_pnl_pct']:+7.1f}%{flag}")

    n_underpowered = result["underpowered_n_lt_10"].sum()
    print(f"\n{n_underpowered}/{len(result)} sector(s) flagged underpowered (n<{MIN_N_WARN}).")
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
