#!/usr/bin/env python3
# GST Zscore Baseline — 2021-2025 replication. Same random-week sampling
# logic as GST_Zscore_Baseline.py.
#
# Input : GST Data/Weekly zscore spikes no overlaps (2021-2025)/<TICKER>_zspikes_no_overlap.csv
#         Daily Excess Return Data (2021-2025)/<TICKER>_<YEAR>_excess.csv
# Output: Conjunction Zscore Baseline (2021-2025)/<TICKER>_baseline.csv

from __future__ import annotations
from pathlib import Path
import random
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
OUT_DIR    = Path("Conjunction Zscore Baseline (2021-2025)")
OUT_DIR.mkdir(parents=True, exist_ok=True)

EX_COL = "Excess Daily Return"
DP = 3
MIN_GAP_DAYS = 21
N_SAMPLES_PER_TICKER = 25
RANDOM_SEED = 42


def _load_spike_dates(ticker: str) -> list[pd.Timestamp]:
    p = ZSPIKE_DIR / f"{ticker}_zspikes_no_overlap.csv"
    if not p.exists():
        return []
    df = pd.read_csv(p)
    if "Week" not in df.columns:
        return []
    dates = pd.to_datetime(df["Week"], errors="coerce").dropna().tolist()
    return dates


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
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def _window(anchor: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    return anchor - timedelta(days=7), anchor + timedelta(days=13)


def _analyze_window(daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    mask = (daily["Date"] >= start) & (daily["Date"] <= end)
    window = daily.loc[mask].sort_values("Date").reset_index(drop=True)

    if window.empty:
        return {"n_trading_days": 0, "max_pos_excess_pct": None,
                "pos_in_window_pos": None,
                "pos_streak_days_from_max": None,
                "max_abs_excess_pct": None}

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


def _sample_random_weeks(daily: pd.DataFrame, spike_dates: list[pd.Timestamp],
                          n_samples: int, rng: random.Random) -> list[pd.Timestamp]:
    if daily.empty:
        return []
    all_dates = daily["Date"].tolist()
    lo, hi = min(all_dates), max(all_dates)

    candidates = []
    attempts = 0
    max_attempts = n_samples * 50
    while len(candidates) < n_samples and attempts < max_attempts:
        attempts += 1
        offset_days = rng.randint(0, (hi - lo).days)
        candidate = lo + timedelta(days=offset_days)
        too_close = any(abs((candidate - s).days) < MIN_GAP_DAYS for s in spike_dates)
        also_close_to_chosen = any(abs((candidate - c).days) < MIN_GAP_DAYS for c in candidates)
        if not too_close and not also_close_to_chosen:
            candidates.append(candidate)
    return candidates


def main():
    rng = random.Random(RANDOM_SEED)

    for ticker in TICKERS:
        spike_dates = _load_spike_dates(ticker)
        daily = _load_daily_excess(ticker)

        if daily.empty:
            print(f"[{ticker}] no daily data, skipping")
            continue

        random_weeks = _sample_random_weeks(daily, spike_dates, N_SAMPLES_PER_TICKER, rng)

        rows = []
        for anchor in random_weeks:
            start, end = _window(anchor)
            stats = _analyze_window(daily, start, end)
            rows.append({
                "ticker": ticker,
                "random_week": anchor.date(),
                **stats
            })

        out_df = pd.DataFrame(rows)
        out_path = OUT_DIR / f"{ticker}_baseline.csv"
        out_df.to_csv(out_path, index=False)
        print(f"[{ticker}] {len(out_df)} random baseline windows -> {out_path.name}")

    all_events = []
    for f in sorted(OUT_DIR.glob("*_baseline.csv")):
        df = pd.read_csv(f)
        if not df.empty:
            all_events.append(df)

    if all_events:
        combined = pd.concat(all_events, ignore_index=True)
        pos = pd.to_numeric(combined.get("pos_in_window_pos"), errors="coerce").dropna()
        streak = pd.to_numeric(combined.get("pos_streak_days_from_max"), errors="coerce")
        streak = streak[streak > 0].dropna()
        max_abs = pd.to_numeric(combined.get("max_abs_excess_pct"), errors="coerce").dropna()

        print("\n--- BASELINE OVERALL (random non-spike weeks, all tickers pooled) ---")
        print(f"Total random windows:      {len(combined)}")
        print(f"Avg position of max pos:   {pos.mean():.2f}  (out of ~14-15 trading days)")
        print(f"Avg non-negative streak:   {streak.mean():.2f} days")
        print(f"% windows where the single biggest move was actually NEGATIVE: {(max_abs < 0).mean()*100:.1f}%")

if __name__ == "__main__":
    main()
