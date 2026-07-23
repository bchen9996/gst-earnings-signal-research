#!/usr/bin/env python3
# GST Zscore Spikes — replaces flat threshold (>=85) with a rolling z-score
# so spike detection is relative to each ticker's OWN recent baseline,
# instead of an absolute cutoff that unfairly flags noisy tickers (e.g. EBAY, GME)
# as "spiking" nearly every week.
#
# Input : GST Data/Weekly Data/<TICKER>_<YEAR>.csv  (columns: Week,<TICKER>,isPartial)
# Output: GST Data/Weekly zscore spikes/<TICKER>_zspikes.csv
#         one file per ticker, ALL years concatenated (need continuity for rolling window)

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

# ----- Settings (tune these — these are literally the README's "knobs") -----
TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]
YEARS = list(range(2014, 2020))

ROLLING_WINDOW = 12      # weeks of prior history used to compute baseline mean/std
Z_THRESHOLD    = 2.0     # how many std devs above rolling mean counts as a "spike"
MIN_PERIODS    = 8       # minimum weeks of history required before we trust a z-score
                         # (avoids using a rolling std computed off only 1-2 points)

IN_DIR  = Path("GST Data") / "Weekly Data"
OUT_DIR = Path("GST Data") / "Weekly zscore spikes"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_ticker_series(ticker: str) -> pd.DataFrame:
    """Concatenate all years for a ticker into one continuous weekly series."""
    frames = []
    for year in YEARS:
        p = IN_DIR / f"{ticker}_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, encoding="utf-8-sig")
        if "Week" not in df.columns:
            continue
        # value column is whatever isn't Week/isPartial (usually the ticker name)
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
    """
    Rolling mean/std computed over the PRIOR window only (shifted by 1),
    so this week's own value never leaks into its own baseline.
    """
    df = df.copy()
    df["gst"] = pd.to_numeric(df["gst"], errors="coerce")

    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    df["rolling_mean"] = rolling.mean()
    df["rolling_std"] = rolling.std()

    # z-score: how many std devs is this week above its own recent baseline
    df["zscore"] = (df["gst"] - df["rolling_mean"]) / df["rolling_std"]

    # guard against div-by-zero (flat baseline -> std=0) producing inf
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
    print("\n--- Summary (sorted by % spike weeks, should now be roughly even across tickers) ---")
    print(summary.to_string(index=False))
    print(f"\nWrote summary to: {summary_path}")


if __name__ == "__main__":
    main()