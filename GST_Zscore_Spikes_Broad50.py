#!/usr/bin/env python3
# GST Zscore Spikes — Broad50 generalization test. Same rolling z-score
# methodology as GST_Zscore_Spikes.py (ROLLING_WINDOW=12, Z_THRESHOLD=2.0,
# MIN_PERIODS=8), applied to the 50-ticker Broad50 sample instead of the
# original 15.
#
# Input : GST Data/Weekly Data (Broad50)/<TICKER>_<YEAR>.csv
# Output: GST Data/Weekly zscore spikes (Broad50)/<TICKER>_zspikes.csv

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

TICKERS = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'ARE', 'AVB', 'BKR', 'BRK-B', 'BRO', 'CCL',
    'CI', 'CL', 'COF', 'COHR', 'CTSH', 'CTVA', 'DELL', 'DVN', 'EL', 'ERIE',
    'FE', 'GPC', 'GPN', 'HD', 'JBL', 'KO', 'LDOS', 'LNT', 'LOW', 'MCHP',
    'MCK', 'MDT', 'NCLH', 'NI', 'PKG', 'PLD', 'PM', 'PNW', 'RCL', 'REG',
    'ROP', 'RTX', 'STZ', 'SYF', 'SYK', 'T', 'TT', 'UAL', 'VZ', 'XOM',
]
YEARS = list(range(2014, 2020))

ROLLING_WINDOW = 12
Z_THRESHOLD    = 2.0
MIN_PERIODS    = 8

IN_DIR  = Path("GST Data") / "Weekly Data (Broad50)"
OUT_DIR = Path("GST Data") / "Weekly zscore spikes (Broad50)"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_ticker_series(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = IN_DIR / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, encoding="utf-8-sig")
        if "Week" not in df.columns:
            continue
        value_col = next((c for c in df.columns if c.lower() not in {"week", "ispartial"}), None)
        if value_col is None:
            continue
        df = df.rename(columns={value_col: "gst"})
        df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
        df = df.dropna(subset=["Week"])
        frames.append(df[["Week", "gst"]])
    if not frames:
        return pd.DataFrame(columns=["Week", "gst"])
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values("Week").drop_duplicates(subset="Week").reset_index(drop=True)
    return out


def compute_zscore_spikes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["gst"] = pd.to_numeric(df["gst"], errors="coerce")

    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    df["rolling_mean"] = rolling.mean()
    df["rolling_std"] = rolling.std()

    df["zscore"] = (df["gst"] - df["rolling_mean"]) / df["rolling_std"]
    df["zscore"] = df["zscore"].replace([np.inf, -np.inf], np.nan)

    df["is_spike"] = df["zscore"] >= Z_THRESHOLD

    return df


def main():
    summary_rows = []
    for ticker in TICKERS:
        series = load_ticker_series(ticker)
        if series.empty:
            print(f"[{ticker}] no data found, skipping")
            continue

        result = compute_zscore_spikes(series)
        n_spikes = int(result["is_spike"].sum())
        n_valid = int(result["zscore"].notna().sum())
        pct_spike = (n_spikes / n_valid * 100) if n_valid else 0.0

        out_path = OUT_DIR / f"{ticker}_zspikes.csv"
        result.to_csv(out_path, index=False)

        print(f"[{ticker}] {n_spikes} spike weeks out of {n_valid} scored weeks "
              f"({pct_spike:.1f}%) -> {out_path.name}")

        summary_rows.append({
            "ticker": ticker,
            "n_weeks_scored": n_valid,
            "n_spikes": n_spikes,
            "pct_spike_weeks": round(pct_spike, 2)
        })

    summary = pd.DataFrame(summary_rows).sort_values("pct_spike_weeks", ascending=False)
    summary_path = OUT_DIR / "_summary_pct_spike_by_ticker.csv"
    summary.to_csv(summary_path, index=False)
    print("\n--- Summary ---")
    print(summary.to_string(index=False))
    print(f"\nWrote summary to: {summary_path}")


if __name__ == "__main__":
    main()
