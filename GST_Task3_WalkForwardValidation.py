#!/usr/bin/env python3
# TASK 3 — Walk-forward year-by-year cross-validation. All on-disk data,
# no new pulls: reuses Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv (z>=5 filtered) and
# group_b_nospike_earnings_adjacent.csv.
#
# Three expanding folds: train 2021-2022/test 2023, train 2021-2023/test
# 2024, train 2021-2024/test 2025. No parameter is actually FIT from the
# train fold — z>=5 and the pricing model are pre-specified, fixed
# constants throughout this project, not something tuned per fold. "Train"
# here means "the accumulated track record available before this test
# year" — reported alongside each test year so it's visible whether the
# prior-years' track record held up in the following year, which is the
# actual point of a walk-forward check when there's no fitting step.
#
# Group B (non-spike, earnings-adjacent) is also broken out per year as
# context, so each test year's STRONG_EARNINGS result can be read against
# that same year's no-spike baseline, not just against the multi-year
# Group A average.
#
# Output: Live Signal Engine/Task3_WalkForwardValidation_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
GROUP_B_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_b_nospike_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task3_WalkForwardValidation_Results.csv"

Z_THRESHOLD = 5.0
HORIZON = "end_of_spike_week"
FOLDS = [
    {"train_years": [2021, 2022], "test_year": 2023},
    {"train_years": [2021, 2022, 2023], "test_year": 2024},
    {"train_years": [2021, 2022, 2023, 2024], "test_year": 2025},
]


def summarize(df: pd.DataFrame, win_col: str, pnl_col: str) -> dict:
    usable = df[df[win_col].notna()]
    n = len(usable)
    if n == 0:
        return {"n": 0, "win_rate_pct": None, "avg_pnl_pct": None, "median_pnl_pct": None}
    return {
        "n": n,
        "win_rate_pct": round(usable[win_col].mean() * 100, 1),
        "avg_pnl_pct": round(usable[pnl_col].mean(), 1),
        "median_pnl_pct": round(usable[pnl_col].median(), 1),
    }


def main():
    print(f"*** TASK 3: Walk-forward year-by-year validation (z>={Z_THRESHOLD:g}, {HORIZON}) ***\n")

    a = pd.read_csv(GROUP_A_PATH)
    a = a[a["zscore"] >= Z_THRESHOLD].copy()
    a["year"] = pd.to_datetime(a["spike_week"]).dt.year

    b = pd.read_csv(GROUP_B_PATH)
    b["year"] = pd.to_datetime(b["anchor"]).dt.year

    win_col, pnl_col = f"{HORIZON}_win", f"{HORIZON}_pnl_pct"

    rows = []
    for fold in FOLDS:
        train_years, test_year = fold["train_years"], fold["test_year"]

        a_train = a[a["year"].isin(train_years)]
        a_test = a[a["year"] == test_year]
        b_train = b[b["year"].isin(train_years)]
        b_test = b[b["year"] == test_year]

        a_train_stats = summarize(a_train, win_col, pnl_col)
        a_test_stats = summarize(a_test, win_col, pnl_col)
        b_train_stats = summarize(b_train, win_col, pnl_col)
        b_test_stats = summarize(b_test, win_col, pnl_col)

        print(f"--- Fold: train {train_years[0]}-{train_years[-1]}, test {test_year} ---")
        print(f"  Group A (STRONG_EARNINGS) train: n={a_train_stats['n']:<4} "
              f"win={a_train_stats['win_rate_pct']}%  median={a_train_stats['median_pnl_pct']}%")
        print(f"  Group A (STRONG_EARNINGS) test:  n={a_test_stats['n']:<4} "
              f"win={a_test_stats['win_rate_pct']}%  median={a_test_stats['median_pnl_pct']}%")
        print(f"  Group B (no-spike) train:        n={b_train_stats['n']:<4} "
              f"win={b_train_stats['win_rate_pct']}%  median={b_train_stats['median_pnl_pct']}%")
        print(f"  Group B (no-spike) test:         n={b_test_stats['n']:<4} "
              f"win={b_test_stats['win_rate_pct']}%  median={b_test_stats['median_pnl_pct']}%")
        print()

        rows.append({"fold": f"train {train_years[0]}-{train_years[-1]} / test {test_year}",
                      "test_year": test_year, "group": "A_STRONG_EARNINGS", "split": "train", **a_train_stats})
        rows.append({"fold": f"train {train_years[0]}-{train_years[-1]} / test {test_year}",
                      "test_year": test_year, "group": "A_STRONG_EARNINGS", "split": "test", **a_test_stats})
        rows.append({"fold": f"train {train_years[0]}-{train_years[-1]} / test {test_year}",
                      "test_year": test_year, "group": "B_no_spike", "split": "train", **b_train_stats})
        rows.append({"fold": f"train {train_years[0]}-{train_years[-1]} / test {test_year}",
                      "test_year": test_year, "group": "B_no_spike", "split": "test", **b_test_stats})

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
