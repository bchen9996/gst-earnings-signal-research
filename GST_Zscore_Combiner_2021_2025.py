#!/usr/bin/env python3
# GST Zscore Combiner — 2021-2025 replication. Same 3-week window logic as
# GST_Zscore_Combiner.py.
#
# Input : GST Data/Weekly zscore spikes no overlaps (2021-2025)/<TICKER>_zspikes_no_overlap.csv
#         Daily Excess Return Data (2021-2025)/<TICKER>_<YEAR>_excess.csv
# Output: Conjunction Zscore (2021-2025)/<TICKER>_zconjunction.csv

from __future__ import annotations
from pathlib import Path
import pandas as pd
from datetime import timedelta

TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]
YEARS = list(range(2021, 2026))

ZSPIKE_DIR = Path("GST Data") / "Weekly zscore spikes no overlaps (2021-2025)"
DAILY_DIR  = Path("Daily Excess Return Data (2021-2025)")
OUT_DIR    = Path("Conjunction Zscore (2021-2025)")
OUT_DIR.mkdir(parents=True, exist_ok=True)

EX_COL = "Excess Daily Return"
DP = 3


def _load_spikes(ticker: str) -> pd.DataFrame:
    p = ZSPIKE_DIR / f"{ticker}_zspikes_no_overlap.csv"
    if not p.exists():
        return pd.DataFrame(columns=["Week"])
    df = pd.read_csv(p)
    if "Week" not in df.columns:
        return pd.DataFrame(columns=["Week"])
    df["Week"] = pd.to_datetime(df["Week"], errors="coerce")
    return df.dropna(subset=["Week"]).reset_index(drop=True)


def _load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIR / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or EX_COL not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df[["Date", EX_COL]].dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame(columns=["Date", EX_COL])
    out = pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)
    return out


def _window(anchor: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    return anchor - timedelta(days=7), anchor + timedelta(days=13)


def _analyze_window(daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    mask = (daily["Date"] >= start) & (daily["Date"] <= end)
    window = daily.loc[mask].sort_values("Date").reset_index(drop=True)

    if window.empty:
        return {
            "n_trading_days": 0,
            "max_pos_excess_pct": None,
            "pos_in_window_pos": None,
            "pos_streak_days_from_max": None,
            "max_abs_excess_pct": None,
        }

    excess = window[EX_COL]
    n_days = len(excess)

    max_pos_idx = excess.idxmax() if (excess > 0).any() else None
    max_pos_val = excess.loc[max_pos_idx] if max_pos_idx is not None else None
    pos_in_window = int(window.index.get_loc(max_pos_idx)) + 1 if max_pos_idx is not None else None

    streak = 0
    if max_pos_idx is not None:
        start_pos = window.index.get_loc(max_pos_idx)
        for v in excess.iloc[start_pos:]:
            if v >= 0:
                streak += 1
            else:
                break

    max_abs_idx = excess.abs().idxmax()
    max_abs_val = excess.loc[max_abs_idx]

    return {
        "n_trading_days": n_days,
        "max_pos_excess_pct": round(max_pos_val * 100, DP) if max_pos_val is not None else None,
        "pos_in_window_pos": pos_in_window,
        "pos_streak_days_from_max": streak if max_pos_idx is not None else None,
        "max_abs_excess_pct": round(max_abs_val * 100, DP),
    }


def main():
    for ticker in TICKERS:
        spikes = _load_spikes(ticker)
        daily = _load_daily_excess(ticker)

        if spikes.empty or daily.empty:
            print(f"[{ticker}] missing spike or daily data, skipping")
            continue

        rows = []
        for _, spike_row in spikes.iterrows():
            anchor = spike_row["Week"]
            start, end = _window(anchor)
            stats = _analyze_window(daily, start, end)
            rows.append({
                "ticker": ticker,
                "spike_week": anchor.date(),
                "zscore": round(spike_row.get("zscore", float("nan")), 3) if "zscore" in spike_row else None,
                **stats
            })

        out_df = pd.DataFrame(rows)
        out_path = OUT_DIR / f"{ticker}_zconjunction.csv"
        out_df.to_csv(out_path, index=False)
        print(f"[{ticker}] {len(out_df)} spike events -> {out_path.name}")

    print(f"\nDone. Files in: {OUT_DIR}")


if __name__ == "__main__":
    main()
