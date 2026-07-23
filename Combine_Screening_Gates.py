#!/usr/bin/env python3
# Stock Screening Pipeline — Step 3: combine the gates.
#
# Zacks Rank=1 + Analyst Recommendation=1 was already applied upstream to
# arrive at the 26-ticker candidate universe (TICKERS below) — that's a hard
# gate all 26 rows already satisfy, so it's recorded here for completeness
# rather than re-derived.
#
# Insider buying (Step 1) is INFORMATIONAL CONTEXT, not a pass/fail gate —
# buying is a rare, high-signal event and requiring it outright would have
# collapsed the list to ~1 name at 90 days (see Insider_Buying_Gate.py).
#
# Sloan accruals (Step 2) is a RELATIVE CAUTION flag, not a hard exclusion —
# top quartile of accruals ratio (most aggressive/least conservative) among
# tickers with valid data. BEN is EXCLUDED from the Sloan gate specifically
# (no classified balance sheet — a financial-sector structural feature, not
# missing data) and is called out as such rather than silently dropped.
#
# Because neither Step 1 nor Step 2 is a hard filter, this "final candidate
# list" is all 26 tickers annotated with both gates' numbers, not a smaller
# surviving subset — the point of Step 3 is to see the full picture side by
# side before deciding what (if anything) to filter on for a backtest.
#
# Input : Stock Screening/insider_buying_summary.csv   (from Step 1)
#         Stock Screening/sloan_accruals_summary.csv    (from Step 2)
# Output: Stock Screening/final_candidate_list.csv

from __future__ import annotations
from pathlib import Path
import pandas as pd

OUT_DIR = Path("Stock Screening")

TICKERS = [
    "ADI","ALB","AMAT","AXON","BEN","CIEN","COHR","CSCO","DELL","EME","F",
    "FLEX","FOXA","HPE","INTC","JBL","KEYS","MCHP","MU","NWS","Q","ROST",
    "SNPS","TPR","WDC","XYZ"
]


def main():
    insider = pd.read_csv(OUT_DIR / "insider_buying_summary.csv")
    sloan = pd.read_csv(OUT_DIR / "sloan_accruals_summary.csv")

    base = pd.DataFrame({"ticker": TICKERS})
    base["zacks_rank_gate"] = "PASS (Zacks Rank=1 & Analyst Rec=1, pre-applied)"

    insider_cols = [
        "ticker",
        "n_buy_transactions_90d", "total_buy_dollar_value_90d", "n_distinct_insiders_buying_90d",
        "n_buy_transactions_180d", "total_buy_dollar_value_180d", "n_distinct_insiders_buying_180d",
        "n_buy_transactions_365d", "total_buy_dollar_value_365d", "n_distinct_insiders_buying_365d",
    ]
    sloan_cols = ["ticker", "curr_fy_end", "accruals_ratio", "quality_flag", "notes"]

    merged = base.merge(insider[insider_cols], on="ticker", how="left")
    merged = merged.merge(
        sloan[sloan_cols].rename(columns={
            "quality_flag": "sloan_flag",
            "notes": "sloan_notes",
            "curr_fy_end": "sloan_fy_end",
        }),
        on="ticker", how="left"
    )

    def insider_context(row):
        if row["n_buy_transactions_365d"] and row["n_buy_transactions_365d"] > 0:
            return (f"buying present: {int(row['n_buy_transactions_90d'])}/{int(row['n_buy_transactions_180d'])}/"
                    f"{int(row['n_buy_transactions_365d'])} txns (90/180/365d), "
                    f"${row['total_buy_dollar_value_365d']:,.0f} over 365d, "
                    f"{int(row['n_distinct_insiders_buying_365d'])} distinct insider(s)")
        return "no buying activity in any window (90/180/365d)"

    merged["insider_context"] = merged.apply(insider_context, axis=1)

    out_path = OUT_DIR / "final_candidate_list.csv"
    merged.to_csv(out_path, index=False)

    print("=== Step 3: Combined candidate list (all 26 — Zacks Rank gate already satisfied) ===\n")
    print("Insider buying = informational context. Sloan accruals = relative CAUTION flag, not exclusion.\n")

    display = merged[["ticker", "zacks_rank_gate", "insider_context", "accruals_ratio", "sloan_flag"]]
    print(display.to_string(index=False))

    print(f"\nWrote combined list to: {out_path}")

    # Highlight the tickers with the cleanest combined picture: real insider
    # buying AND not in the Sloan caution quartile.
    has_buying = merged["n_buy_transactions_365d"].fillna(0) > 0
    sloan_ok = merged["sloan_flag"] == "OK"
    standout = merged.loc[has_buying & sloan_ok, "ticker"].tolist()
    caution_flagged = merged.loc[merged["sloan_flag"].str.startswith("CAUTION", na=False), "ticker"].tolist()
    excluded = merged.loc[merged["sloan_flag"].str.startswith("EXCLUDED", na=False), "ticker"].tolist()

    print("\n--- Notable groupings (informational, not a filtered output) ---")
    print(f"Insider buying present (any window) AND Sloan flag = OK: {standout if standout else 'none'}")
    print(f"Sloan CAUTION (top quartile, most aggressive accruals): {caution_flagged}")
    print(f"Excluded from Sloan gate (financial sector structure): {excluded}")


if __name__ == "__main__":
    main()
