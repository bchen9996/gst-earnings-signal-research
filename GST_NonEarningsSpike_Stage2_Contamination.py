#!/usr/bin/env python3
# NON-EARNINGS SPIKE TEST -- STAGE 2: contamination check.
#
# For every candidate that survived stage 1 (still clears z>=5 under the
# canonical fixed-window method), checks for a confounding corporate
# action using the EXACT same two-part methodology already built for the
# main backtest (GST_STRONG_EARNINGS_ContaminationAudit.py, reused, not
# re-derived): (1) a quantitative single-dominant-day-move screen on
# local daily excess-return data, (2) a real SEC EDGAR cross-reference for
# SC 13D/13D-A, SC TO-T/TO-C, SC 14D9, DEFM14A, 425 (form types
# distinctive to M&A/activist/tender activity -- NOT DEFA14A, excluded
# per the same NFLX false-positive finding documented in the original
# script). Classification: CONFIRMED_MA_CONTAMINATION / SUSPECTED_UNCONFIRMED
# (large single-day move, no distinctive EDGAR form -- could be
# litigation/regulatory news this check can't distinguish from a strong
# genuine reaction) / CLEAN.
#
# WINDOW (different from the earnings version, since there's no earnings-
# anchored entry/exit here): anchor-3 to anchor+12 calendar days -- covers
# the spike week itself plus the 5-trading-day-forward measurement window
# stage 3 will use, with a few days of buffer on each side.
#
# Output: Live Signal Engine/NonEarningsSpike_Stage2_Contamination.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import time
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "Live Signal Engine" / "Mechanism_B"))
from edgar_8k_signal import get_cik, get_all_filings  # noqa: E402
import GST_FixedWindow_PerEvent_Canonical as base

sys.stdout.reconfigure(encoding="utf-8")

STAGE1_PATH = Path("Live Signal Engine") / "NonEarningsSpike_Stage1_Verified.csv"
OUT_PATH = Path("Live Signal Engine") / "NonEarningsSpike_Stage2_Contamination.csv"

WINDOW_START_BUFFER_DAYS = 3
WINDOW_END_BUFFER_DAYS = 12

DOMINANT_DAY_ABS_MOVE_THRESHOLD = 20.0
DOMINANT_DAY_SHARE_THRESHOLD = 0.70

MA_RELATED_FORMS = {"SC 13D", "SC 13D/A", "SC TO-T", "SC TO-C", "SC 14D9", "DEFM14A", "425"}


def dominant_day_analysis(daily: pd.DataFrame, ret_col: str, window_start: pd.Timestamp, window_end: pd.Timestamp) -> dict:
    mask = (daily["Date"] >= window_start) & (daily["Date"] <= window_end)
    window = daily.loc[mask, ["Date", ret_col]].copy()
    if window.empty:
        return {"max_day_date": None, "max_day_abs_move_pct": None, "max_day_share_of_window": None}
    window["abs_ret"] = window[ret_col].abs()
    total_abs = window["abs_ret"].sum()
    idx = window["abs_ret"].idxmax()
    max_row = window.loc[idx]
    share = float(max_row["abs_ret"] / total_abs) if total_abs > 0 else None
    return {
        "max_day_date": max_row["Date"].date(),
        "max_day_abs_move_pct": round(float(max_row["abs_ret"]) * 100, 2),
        "max_day_share_of_window": round(share, 3) if share is not None else None,
    }


def check_edgar_ma_filings(ticker: str, window_start: pd.Timestamp, window_end: pd.Timestamp) -> list[dict]:
    filings = get_all_filings(ticker, earliest_needed=window_start - timedelta(days=30))
    if filings.empty:
        return []
    mask = (filings["filingDate"] >= window_start) & (filings["filingDate"] <= window_end) & (filings["form"].isin(MA_RELATED_FORMS))
    hits = filings.loc[mask]
    return [{"form": r["form"], "filingDate": r["filingDate"].date()} for _, r in hits.iterrows()]


def main():
    print("*** NON-EARNINGS SPIKE TEST -- STAGE 2: contamination check ***\n")

    stage1 = pd.read_csv(STAGE1_PATH)
    stage1["spike_week"] = pd.to_datetime(stage1["spike_week"])
    verified = stage1[stage1["still_qualifies_z5"] == True].copy()  # noqa: E712
    print(f"Events to check: n={len(verified)}\n")

    unique_tickers = sorted(verified["ticker"].unique())
    print("Cross-referencing SEC EDGAR filing history per ticker (cached, one pull each)...")
    for i, t in enumerate(unique_tickers, start=1):
        cik = get_cik(t)
        get_all_filings(t, earliest_needed=pd.Timestamp("2020-01-01"))
        print(f"  [{i}/{len(unique_tickers)}] {t}: CIK={cik}")
        time.sleep(0.15)
    print()

    daily_cache = {t: base.load_daily_excess(t) for t in unique_tickers}

    rows = []
    for _, ev in verified.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["fixed_window_zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        excess_col = "Excess Daily Return" if not daily.empty and "Excess Daily Return" in daily.columns else None

        window_start = anchor - timedelta(days=WINDOW_START_BUFFER_DAYS)
        window_end = anchor + timedelta(days=WINDOW_END_BUFFER_DAYS)

        dom = dominant_day_analysis(daily, excess_col, window_start, window_end) if excess_col else \
            {"max_day_date": None, "max_day_abs_move_pct": None, "max_day_share_of_window": None}
        ma_filings = check_edgar_ma_filings(ticker, window_start, window_end)

        quant_flag = (dom["max_day_abs_move_pct"] is not None
                      and dom["max_day_abs_move_pct"] >= DOMINANT_DAY_ABS_MOVE_THRESHOLD
                      and dom["max_day_share_of_window"] is not None
                      and dom["max_day_share_of_window"] >= DOMINANT_DAY_SHARE_THRESHOLD)

        if ma_filings and quant_flag:
            classification = "CONFIRMED_MA_CONTAMINATION"
        elif quant_flag:
            classification = "SUSPECTED_UNCONFIRMED"
        else:
            classification = "CLEAN"

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "fixed_window_zscore": zscore,
            "max_day_date": dom["max_day_date"], "max_day_abs_move_pct": dom["max_day_abs_move_pct"],
            "max_day_share_of_window": dom["max_day_share_of_window"],
            "ma_related_filings": "; ".join(f"{f['form']}@{f['filingDate']}" for f in ma_filings) if ma_filings else "",
            "classification": classification,
        })
        print(f"{ticker} {anchor.date()}: {classification}"
              + (f"  [{rows[-1]['ma_related_filings']}]" if ma_filings else ""))

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}\n")

    print("=== CLASSIFICATION SUMMARY ===")
    print(result["classification"].value_counts().to_string())

    clean = result[result["classification"] == "CLEAN"]
    print(f"\nClean, unexplained non-earnings spikes proceeding to stage 3: n={len(clean)}")


if __name__ == "__main__":
    main()
