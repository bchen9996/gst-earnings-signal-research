#!/usr/bin/env python3
# TASK 3 test harness — runs price_volume_signal.compute_price_volume_score
# against MSFT, NVDA, NFLX, NKE, ADBE for each of their 2023 earnings dates.
#
# Output: Live Signal Engine/Mechanism_B/price_volume_test_results.csv

from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / "Live Signal Engine" / "Mechanism_B"))

import pandas as pd
from price_volume_signal import compute_price_volume_score

sys.stdout.reconfigure(encoding="utf-8")

TEST_TICKERS = ["MSFT", "NVDA", "NFLX", "NKE", "ADBE"]
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "Mechanism_B" / "price_volume_test_results.csv"


def main():
    print("*** TASK 3 test: price/volume anomaly score, 5 tickers x 2023 earnings dates ***\n")

    earnings = pd.read_csv(EARNINGS_PATH)
    earnings["earnings_date"] = pd.to_datetime(earnings["earnings_date"])
    test_events = earnings[(earnings["ticker"].isin(TEST_TICKERS)) & (earnings["earnings_date"].dt.year == 2023)]
    test_events = test_events.sort_values(["ticker", "earnings_date"])
    print(f"Test events: n={len(test_events)}\n")

    rows = []
    for _, ev in test_events.iterrows():
        result = compute_price_volume_score(ev["ticker"], ev["earnings_date"])
        rows.append(result)
        print(f"  {result['ticker']:<5} {result['earnings_date']}: vol_anomaly={result['volume_anomaly']}  "
              f"mom_return={result['price_momentum_return']}  mom_pctile={result['price_momentum_percentile']}  "
              f"n_hist={result['n_history_events']:<3} score={result['price_volume_score']}")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)

    print(f"\n=== SUMMARY ===")
    valid = result_df[result_df["price_volume_score"].notna()]
    print(f"Usable scores: {len(valid)}/{len(result_df)}")
    if len(valid) > 0:
        print(f"Score range: [{valid['price_volume_score'].min():.2f}, {valid['price_volume_score'].max():.2f}]  "
              f"mean={valid['price_volume_score'].mean():.2f}  std={valid['price_volume_score'].std():.2f}")
        print(f"\nPer ticker:")
        print(result_df.groupby("ticker")["price_volume_score"].agg(["count", "mean", "std"]).round(2))

    n_insufficient = int(result_df["insufficient_history"].sum())
    print(f"\nEvents flagged insufficient_history: {n_insufficient}/{len(result_df)}")

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
