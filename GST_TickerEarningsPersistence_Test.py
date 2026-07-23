#!/usr/bin/env python3
# TICKER-SPECIFIC EARNINGS-REACTION PERSISTENCE TEST -- properly powered,
# NOT the small GST-flagged subsample from GST_DirectionalBias_Analysis.py
# (which had only 5-16 events per ticker, cherry-picked to weeks a GST
# spike happened to fire). This pulls EVERY earnings date 2021-2025 for
# each candidate ticker (~22 quarters each), independent of GST entirely
# -- testing a well-known market phenomenon (company-specific earnings-
# reaction persistence) on its own terms.
#
# TICKER SELECTION: INTC, TTWO, SBUX (named explicitly) plus every other
# ticker from the earlier GST-flagged check whose lean was >=20 points
# from 50% (a disclosed, consistent threshold, not cherry-picked further):
# NKE (30.8%), QCOM (30.0%), ADBE (28.6%). NVDA (66.7%, |lean|=16.7) and
# AAPL/LDOS (60.0%, |lean|=10, n=5 only) fall under this threshold and are
# excluded -- MSFT (exactly 50%) and NFLX (43.75%, |lean|=6.25) show no
# notable lean at all.
#
# EARNINGS-DAY MOVE: raw stock return from the nearest trading day BEFORE
# the earnings date to the nearest trading day ON/AFTER it (a 1-2 day
# window wide enough to catch the reaction regardless of BMO/AMC timing,
# without needing that classification here) -- computed from each
# ticker's own already-local daily excess-return data, no fresh pull
# needed, no GST/z-score involved anywhere in this test.
#
# Output: Live Signal Engine/TickerEarningsPersistence_Test.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
from math import comb
import sys
import pandas as pd

import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

EARNINGS_DATES_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "TickerEarningsPersistence_Test.csv"

TICKERS = ["INTC", "TTWO", "SBUX", "NKE", "QCOM", "ADBE"]
WINDOW_START, WINDOW_END = "2021-01-01", "2026-07-19"   # past-only, matches project's "today"


def binomial_two_sided_p(n_pos: int, n: int) -> float | None:
    if n == 0:
        return None
    k = min(n_pos, n - n_pos)
    p_point = lambda x: comb(n, x) * 0.5 ** n
    p_k = p_point(k)
    return min(sum(p_point(x) for x in range(n + 1) if p_point(x) <= p_k + 1e-12), 1.0)


def earnings_day_move(daily: pd.DataFrame, ret_col: str, earnings_date: pd.Timestamp) -> float | None:
    pre = daily.loc[daily["Date"] < earnings_date, "Date"]
    post = daily.loc[daily["Date"] >= earnings_date, "Date"]
    if pre.empty or post.empty:
        return None
    pre_day, post_day = pre.max(), post.min()
    mask = (daily["Date"] > pre_day) & (daily["Date"] <= post_day)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def main():
    print("*** TICKER-SPECIFIC EARNINGS-REACTION PERSISTENCE TEST ***\n")
    print(f"Tickers: {TICKERS}\n")

    earnings_df = pd.read_csv(EARNINGS_DATES_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])

    all_rows = []
    ticker_summaries = []

    for ticker in TICKERS:
        daily = base.load_daily_excess(ticker)
        ret_col = f"{ticker} Daily Return"
        dates = sorted(earnings_df[(earnings_df["ticker"] == ticker) &
                                    (earnings_df["earnings_date"] >= WINDOW_START) &
                                    (earnings_df["earnings_date"] < WINDOW_END)]["earnings_date"].tolist())

        events = []
        for ed in dates:
            move = earnings_day_move(daily, ret_col, ed)
            if move is None:
                continue
            events.append({"ticker": ticker, "earnings_date": ed.date(), "move_pct": round(move * 100, 3),
                            "direction": "positive" if move > 0 else ("negative" if move < 0 else "flat")})
        all_rows.extend(events)

        edf = pd.DataFrame(events)
        edf = edf[edf["direction"] != "flat"]
        n = len(edf)
        n_pos = (edf["direction"] == "positive").sum()
        pct_pos = n_pos / n * 100 if n else None
        p_val = binomial_two_sided_p(n_pos, n)

        half = n // 2
        first_half = edf.iloc[:half]
        second_half = edf.iloc[half:]
        fh_pct = (first_half["direction"] == "positive").mean() * 100 if len(first_half) else None
        sh_pct = (second_half["direction"] == "positive").mean() * 100 if len(second_half) else None
        stable = None
        if fh_pct is not None and sh_pct is not None:
            fh_lean = "positive" if fh_pct > 50 else ("negative" if fh_pct < 50 else "neutral")
            sh_lean = "positive" if sh_pct > 50 else ("negative" if sh_pct < 50 else "neutral")
            overall_lean = "positive" if pct_pos > 50 else "negative"
            stable = (fh_lean == overall_lean) and (sh_lean == overall_lean)

        print(f"=== {ticker} (n={n} quarters, 2021-2025) ===")
        print(f"  Positive: {n_pos}/{n} ({pct_pos:.1f}%)   Binomial p={p_val:.4f}"
              f"   {'SIGNIFICANT at 5%' if p_val < 0.05 else 'not significant at 5%'}")
        print(f"  First half (n={len(first_half)}): {fh_pct:.1f}% positive   "
              f"Second half (n={len(second_half)}): {sh_pct:.1f}% positive")
        print(f"  Direction stable across both halves: {stable}\n")

        ticker_summaries.append({
            "ticker": ticker, "n_quarters": n, "n_positive": int(n_pos), "pct_positive": round(pct_pos, 1),
            "binomial_p": round(p_val, 4), "significant_5pct": bool(p_val < 0.05),
            "first_half_pct_positive": round(fh_pct, 1) if fh_pct is not None else None,
            "second_half_pct_positive": round(sh_pct, 1) if sh_pct is not None else None,
            "direction_stable_across_halves": stable,
        })

    events_df = pd.DataFrame(all_rows)
    events_df.to_csv(OUT_PATH, index=False)
    summary_df = pd.DataFrame(ticker_summaries)
    summary_path = Path("Live Signal Engine") / "TickerEarningsPersistence_Test_Summary.csv"
    summary_df.to_csv(summary_path, index=False)

    print(f"Wrote per-event detail: {OUT_PATH}")
    print(f"Wrote summary: {summary_path}\n")
    print("=== SIDE BY SIDE ===")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
