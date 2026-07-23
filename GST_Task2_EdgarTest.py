#!/usr/bin/env python3
# TASK 2 test harness — runs edgar_8k_signal.compute_8k_anomaly_score
# against MSFT, NVDA, NFLX, NKE, ADBE for each of their 2023 earnings
# dates (4 quarters each, n=20), using earnings dates already on disk
# (Live Signal Engine/AllTickers_EarningsDates.csv).
#
# Output: Live Signal Engine/Mechanism_B/edgar_8k_test_results.csv

from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / "Live Signal Engine" / "Mechanism_B"))

import pandas as pd
from edgar_8k_signal import compute_8k_anomaly_score

sys.stdout.reconfigure(encoding="utf-8")

TEST_TICKERS = ["MSFT", "NVDA", "NFLX", "NKE", "ADBE"]
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "Mechanism_B" / "edgar_8k_test_results.csv"


def main():
    print("*** TASK 2 test: 8-K anomaly score, 5 tickers x 2023 earnings dates ***\n")

    earnings = pd.read_csv(EARNINGS_PATH)
    earnings["earnings_date"] = pd.to_datetime(earnings["earnings_date"])
    test_events = earnings[(earnings["ticker"].isin(TEST_TICKERS)) & (earnings["earnings_date"].dt.year == 2023)]
    test_events = test_events.sort_values(["ticker", "earnings_date"])
    print(f"Test events: n={len(test_events)}\n")

    rows = []
    for _, ev in test_events.iterrows():
        result = compute_8k_anomaly_score(ev["ticker"], ev["earnings_date"])
        rows.append(result)
        print(f"  {result['ticker']:<5} {result['earnings_date']}: recent_30d={result['recent_30d_count']:<3} "
              f"baseline_rate={result['baseline_monthly_rate']:<6} baseline_std={result['baseline_std']:<6} "
              f"anomaly_score={result['anomaly_score']}")

    result_df = pd.DataFrame(rows)
    result_df.to_csv(OUT_PATH, index=False)

    print(f"\n=== SUMMARY ===")
    valid = result_df[result_df["anomaly_score"].notna()]
    print(f"Usable anomaly scores: {len(valid)}/{len(result_df)}")
    if len(valid) > 0:
        print(f"Score range: [{valid['anomaly_score'].min():.2f}, {valid['anomaly_score'].max():.2f}]  "
              f"mean={valid['anomaly_score'].mean():.2f}  std={valid['anomaly_score'].std():.2f}")
        print(f"\nPer ticker:")
        print(result_df.groupby("ticker")["anomaly_score"].agg(["count", "mean", "std"]).round(2))

    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
