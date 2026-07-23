#!/usr/bin/env python3
# GST Zscore Summary — aggregate across all tickers from the z-score
# conjunction files. Mirrors the original Conjunction Summary.py logic,
# plus adds a positive/negative split since we now know max_abs can be
# negative (i.e. the biggest move in the window was actually a drop).

from __future__ import annotations
from pathlib import Path
import pandas as pd

CONJ_DIR = Path("Conjunction Zscore")
OUTFILE  = CONJ_DIR / "_overall_zscore_summary.csv"

def main():
    rows = []
    all_events = []

    for f in sorted(CONJ_DIR.glob("*_zconjunction.csv")):
        ticker = f.stem.replace("_zconjunction", "")
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if df.empty:
            rows.append({"ticker": ticker, "n_events": 0,
                         "avg_pos_in_window": None, "avg_streak_days": None,
                         "pct_events_max_move_was_negative": None})
            continue

        all_events.append(df)

        pos = pd.to_numeric(df.get("pos_in_window_pos"), errors="coerce").dropna()
        streak = pd.to_numeric(df.get("pos_streak_days_from_max"), errors="coerce")
        streak = streak[streak > 0].dropna()

        max_abs = pd.to_numeric(df.get("max_abs_excess_pct"), errors="coerce").dropna()
        pct_negative = float((max_abs < 0).mean() * 100) if len(max_abs) else None

        rows.append({
            "ticker": ticker,
            "n_events": len(df),
            "avg_pos_in_window": round(float(pos.mean()), 2) if len(pos) else None,
            "avg_streak_days": round(float(streak.mean()), 2) if len(streak) else None,
            "pct_events_max_move_was_negative": round(pct_negative, 1) if pct_negative is not None else None,
        })

    summary = pd.DataFrame(rows).sort_values("n_events", ascending=False)
    summary.to_csv(OUTFILE, index=False)
    print("--- Per-ticker summary ---")
    print(summary.to_string(index=False))

    if all_events:
        combined = pd.concat(all_events, ignore_index=True)
        pos = pd.to_numeric(combined.get("pos_in_window_pos"), errors="coerce").dropna()
        streak = pd.to_numeric(combined.get("pos_streak_days_from_max"), errors="coerce")
        streak = streak[streak > 0].dropna()
        max_abs = pd.to_numeric(combined.get("max_abs_excess_pct"), errors="coerce").dropna()

        print("\n--- OVERALL (all tickers, all events pooled) ---")
        print(f"Total spike events:        {len(combined)}")
        print(f"Avg position of max pos:   {pos.mean():.2f}  (out of ~14-15 trading days)")
        print(f"Avg non-negative streak:   {streak.mean():.2f} days")
        print(f"% events where the single biggest move was actually NEGATIVE: {(max_abs < 0).mean()*100:.1f}%")

    print(f"\nWrote per-ticker summary to: {OUTFILE}")

if __name__ == "__main__":
    main()
