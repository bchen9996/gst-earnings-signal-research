#!/usr/bin/env python3
# STRONG_EARNINGS CONTAMINATION AUDIT — checks all 147 canonical z>=5,
# near_earnings=True events (Earnings-Adjacent Spike vs No-Spike Test/
# group_a_z4_earnings_adjacent.csv) for the same issue found in the CPRI
# 12-ticker-extension outlier: a major NON-earnings corporate action
# (M&A, activist stake, tender offer, litigation/regulatory decision)
# landing inside the entry-to-exit window and driving the realized move
# instead of (or in addition to) the earnings reaction itself.
#
# *** METHODOLOGY — TWO INDEPENDENT CHECKS, DISCLOSED LIMITATIONS ***
#
# (1) QUANTITATIVE SCREEN (on-disk daily excess return data, no new pulls):
#     for each event's window, finds the single biggest one-day |excess
#     return| and what fraction of the window's total absolute move that
#     one day represents. A move dominated by one extreme day (e.g. CPRI's
#     +55.7% single day) is the same signature a merger/tender/litigation
#     surprise leaves -- but a very strong ordinary earnings reaction can
#     ALSO look like this, so this alone is a trigger for closer look, not
#     proof.
#
# (2) SEC EDGAR CROSS-REFERENCE (real filings, reused infrastructure from
#     Live Signal Engine/Mechanism_B/edgar_8k_signal.py -- get_cik/
#     get_all_filings, not re-derived): checks each ticker's REAL filing
#     history for SEC form types that are DISTINCTIVE to M&A/activist/
#     tender activity and don't get filed for routine earnings:
#       SC 13D, SC 13D/A   (beneficial ownership >5% -- often activist stakes)
#       SC TO-T, SC TO-C   (tender offer)
#       SC 14D9            (target company's response to a tender offer)
#       DEFM14A, DEFA14A   (merger-related proxy materials)
#       425                (business-combination prospectus)
#     A hit here is REAL, verifiable evidence -- not an inference from
#     price action.
#
# *** DISCLOSED LIMITATION — LITIGATION / REGULATORY RULINGS ***
# Litigation and regulatory decisions don't have a distinctive SEC form
# type the way M&A does -- they'd typically show up as a generic "8-K"
# (often Item 8.01, "Other Events"), indistinguishable at the form-type
# level from an earnings-related 8-K without fetching and reading each
# filing's actual item codes/text. That per-filing text pull is a much
# heavier task this audit does NOT attempt. Events flagged only by the
# quantitative screen (large single-day-dominated move, no distinctive
# EDGAR form) are reported as SUSPECTED/UNCONFIRMED, not confirmed
# contamination -- could be litigation/regulatory news, could just be an
# unusually strong genuine earnings reaction.
#
# Classification per event:
#   CONFIRMED_MA_CONTAMINATION — distinctive M&A/activist/tender SEC form
#     filed within the event window AND a large single-day move coincides
#   SUSPECTED_UNCONFIRMED — single-day-dominated large move, but no
#     distinctive EDGAR form found (generic 8-K or nothing) -- could be
#     litigation/regulatory, could be a strong genuine earnings reaction
#   CLEAN — neither signal present
#
# Output: Live Signal Engine/STRONG_EARNINGS_ContaminationAudit_Results.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import time
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent / "Live Signal Engine" / "Mechanism_B"))
from edgar_8k_signal import get_cik, get_all_filings  # noqa: E402

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "STRONG_EARNINGS_ContaminationAudit_Results.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
WINDOW_BUFFER_DAYS = 3     # extra margin around entry/exit for the day-by-day scan
FILING_WINDOW_BUFFER_DAYS = 5   # extra margin around anchor for the EDGAR filing search

DOMINANT_DAY_ABS_MOVE_THRESHOLD = 20.0   # % -- single day considered "large"
DOMINANT_DAY_SHARE_THRESHOLD = 0.70      # that day must be >=70% of the window's total abs move

# DEFA14A deliberately EXCLUDED: verified via the NFLX 2022-04-17 false-positive check
# (see script history) that DEFA14A is routinely filed alongside ordinary annual-meeting
# DEF 14A proxy statements, not just merger deals -- NFLX's hit was its routine annual
# proxy (filed 2022-04-22, same day as a DEF 14A), unrelated to that week's real cause
# (its own 8-K earnings report, filed 2022-04-19, the well-documented subscriber-loss
# crash). DEFM14A ("M" = merger) is the form actually reserved for merger proxies and is
# kept. A DEFA14A hit alone is no longer treated as confirmed M&A evidence.
MA_RELATED_FORMS = {"SC 13D", "SC 13D/A", "SC TO-T", "SC TO-C", "SC 14D9", "DEFM14A", "425"}


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


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
    print("*** STRONG_EARNINGS CONTAMINATION AUDIT (n=147 canonical events) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Auditing n={len(events)} STRONG_EARNINGS events across {events['ticker'].nunique()} tickers\n")

    daily_cache = {t: load_daily_excess(t) for t in events["ticker"].unique()}

    print("Cross-referencing SEC EDGAR filing history per ticker (cached, one pull each)...")
    unique_tickers = sorted(events["ticker"].unique())
    for i, t in enumerate(unique_tickers, start=1):
        cik = get_cik(t)
        get_all_filings(t, earliest_needed=pd.Timestamp("2020-01-01"))
        print(f"  [{i}/{len(unique_tickers)}] {t}: CIK={cik}")
        time.sleep(0.15)
    print()

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or "Excess Daily Return" not in daily.columns:
            excess_col = None
        else:
            excess_col = "Excess Daily Return"

        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS)) if not daily.empty else None
        exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS)) if not daily.empty else None

        scan_start = anchor - timedelta(days=WINDOW_BUFFER_DAYS)
        scan_end = anchor + timedelta(days=EXIT_OFFSET_DAYS + WINDOW_BUFFER_DAYS)

        if excess_col and not daily.empty:
            dom = dominant_day_analysis(daily, excess_col, scan_start, scan_end)
        else:
            dom = {"max_day_date": None, "max_day_abs_move_pct": None, "max_day_share_of_window": None}

        filing_window_start = anchor - timedelta(days=FILING_WINDOW_BUFFER_DAYS)
        filing_window_end = anchor + timedelta(days=EXIT_OFFSET_DAYS + FILING_WINDOW_BUFFER_DAYS)
        ma_filings = check_edgar_ma_filings(ticker, filing_window_start, filing_window_end)

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
            "ticker": ticker, "spike_week": anchor.date(), "zscore": round(float(zscore), 3),
            "entry_date": entry_date.date() if entry_date is not None else None,
            "exit_date": exit_date.date() if exit_date is not None else None,
            "end_of_spike_week_win": ev.get("end_of_spike_week_win"),
            "end_of_spike_week_pnl_pct": ev.get("end_of_spike_week_pnl_pct"),
            "max_day_date": dom["max_day_date"], "max_day_abs_move_pct": dom["max_day_abs_move_pct"],
            "max_day_share_of_window": dom["max_day_share_of_window"],
            "ma_related_filings": "; ".join(f"{f['form']}@{f['filingDate']}" for f in ma_filings) if ma_filings else "",
            "classification": classification,
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}\n")

    print("=== CLASSIFICATION SUMMARY ===")
    print(result["classification"].value_counts().to_string())
    print()

    confirmed = result[result["classification"] == "CONFIRMED_MA_CONTAMINATION"]
    suspected = result[result["classification"] == "SUSPECTED_UNCONFIRMED"]
    if len(confirmed):
        print("=== CONFIRMED M&A/ACTIVIST/TENDER CONTAMINATION ===")
        print(confirmed[["ticker", "spike_week", "zscore", "max_day_date", "max_day_abs_move_pct",
                          "end_of_spike_week_pnl_pct", "ma_related_filings"]].to_string(index=False))
        print()
    if len(suspected):
        print("=== SUSPECTED/UNCONFIRMED (large single-day-dominated move, no distinctive EDGAR M&A form found) ===")
        print(suspected[["ticker", "spike_week", "zscore", "max_day_date", "max_day_abs_move_pct",
                          "end_of_spike_week_pnl_pct"]].to_string(index=False))
        print()

    def summarize(df: pd.DataFrame, label: str):
        usable = df[df["end_of_spike_week_win"].notna()]
        n = len(usable)
        if n == 0:
            print(f"{label}: n=0")
            return
        wr = usable["end_of_spike_week_win"].astype(bool).mean() * 100
        med = usable["end_of_spike_week_pnl_pct"].median()
        avg = usable["end_of_spike_week_pnl_pct"].mean()
        print(f"{label:<55} n={n:<5} win={wr:>6.1f}%  median={med:>8.1f}%  avg={avg:>8.1f}%")

    print("=== WIN RATE / MEDIAN P&L — WITH vs WITHOUT FLAGGED EVENTS ===")
    summarize(result, "ALL 147 events (baseline, unchanged)")
    summarize(result[result["classification"] != "CONFIRMED_MA_CONTAMINATION"], "Excluding CONFIRMED_MA_CONTAMINATION only")
    summarize(result[result["classification"] == "CLEAN"], "CLEAN only (excluding confirmed AND suspected)")

    print(f"\nNOTE: SUSPECTED_UNCONFIRMED events are NOT necessarily contaminated -- litigation/regulatory")
    print(f"news doesn't have a distinctive SEC form type the way M&A does, and a very strong genuine")
    print(f"earnings reaction can also dominate a window. Treat that scenario as a lower bound on the")
    print(f"'clean' population, not a confirmed contamination count.")


if __name__ == "__main__":
    main()
