#!/usr/bin/env python3
# GST Zscore No Overlaps — dedupe z-score spike weeks so anchors are
# at least MIN_GAP_DAYS apart, same spacing rule as the original
# "GST Weekly, no overlaps.py" but applied to z-score spikes instead
# of the flat >=85 threshold.
#
# Input : GST Data/Weekly zscore spikes/<TICKER>_zspikes.csv
#         (full weekly series with zscore + is_spike columns, from GST_Zscore_Spikes.py)
# Output: GST Data/Weekly zscore spikes no overlaps/<TICKER>_zspikes_no_overlap.csv
#         (only the spike weeks that survive the spacing rule)

from __future__ import annotations
from pathlib import Path
import pandas as pd

TICKERS = [
    "TSLA","NVDA","AAPL","MSFT","AMZN",
    "GOOGL","NFLX","ADBE","NKE","SBUX",
    "INTC","TTWO","QCOM","GME","EBAY"
]

MIN_GAP_DAYS = 21   # same 3-week spacing rule as the original overlap script

IN_DIR  = Path("GST Data") / "Weekly zscore spikes"
OUT_DIR = Path("GST Data") / "Weekly zscore spikes no overlaps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def dedupe_spikes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only spike weeks (is_spike == True), then walk through them in
    chronological order and drop any spike that falls within MIN_GAP_DAYS
    of the last KEPT spike. This mirrors the original "no overlaps" logic:
    first spike in a cluster wins, later ones within the gap are dropped.
    """
    spikes = df[df["is_spike"] == True].copy()  # noqa: E712 (explicit True check for clarity)
    spikes["Week"] = pd.to_datetime(spikes["Week"], errors="coerce")
    spikes = spikes.dropna(subset=["Week"]).sort_values("Week").reset_index(drop=True)

    if spikes.empty:
        return spikes

    kept_rows = [spikes.iloc[0]]
    last_kept_date = spikes.iloc[0]["Week"]

    for _, row in spikes.iloc[1:].iterrows():
        gap = (row["Week"] - last_kept_date).days
        if gap >= MIN_GAP_DAYS:
            kept_rows.append(row)
            last_kept_date = row["Week"]
        # else: dropped, too close to the last kept anchor

    return pd.DataFrame(kept_rows).reset_index(drop=True)


def main():
    summary_rows = []
    for ticker in TICKERS:
        in_path = IN_DIR / f"{ticker}_zspikes.csv"
        if not in_path.exists():
            print(f"[{ticker}] no input file found, skipping")
            continue

        df = pd.read_csv(in_path)
        if "is_spike" not in df.columns:
            print(f"[{ticker}] missing is_spike column, skipping")
            continue

        # pandas may load the boolean column as string on round-trip; normalize
        if df["is_spike"].dtype == object:
            df["is_spike"] = df["is_spike"].astype(str).str.lower() == "true"

        n_before = int(df["is_spike"].sum())
        deduped = dedupe_spikes(df)
        n_after = len(deduped)

        out_path = OUT_DIR / f"{ticker}_zspikes_no_overlap.csv"
        deduped.to_csv(out_path, index=False)

        print(f"[{ticker}] {n_before} raw spikes -> {n_after} after de-overlap ({MIN_GAP_DAYS}-day gap) -> {out_path.name}")

        summary_rows.append({
            "ticker": ticker,
            "raw_spikes": n_before,
            "deduped_spikes": n_after,
            "pct_kept": round(n_after / n_before * 100, 1) if n_before else 0.0
        })

    summary = pd.DataFrame(summary_rows).sort_values("deduped_spikes", ascending=False)
    summary_path = OUT_DIR / "_summary_dedup_by_ticker.csv"
    summary.to_csv(summary_path, index=False)
    print("\n--- Summary ---")
    print(summary.to_string(index=False))
    print(f"\nWrote summary to: {summary_path}")


if __name__ == "__main__":
    main()