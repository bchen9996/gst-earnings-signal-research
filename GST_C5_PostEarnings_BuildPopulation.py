#!/usr/bin/env python3
# POPULATION BUILDER for the post-earnings continuation/reversal (C5) test.
# Produces the locked, enumerated sample referenced in
# Live Signal Engine/C5_PostEarnings_PreRegistration.md before any C5 value
# is computed -- this script only resolves WHICH 304 (152 signal + 152
# matched-control) events go into the test and their point-in-time-clean
# covariates (real earnings date, BMO/AMC, gap, continuous z-score). It
# does NOT touch 9:45am-anchored prices at all -- those require
# QuantConnect/AlgoSeek intraday data (see QC_C5_PostEarnings_Pull.py) and
# are out of scope for this script.
#
# REUSES, not reinvents:
#   - the 152 matched signal/control pairs already locked in
#     Live Signal Engine/MatchedControlGroup_CanonicalRecompute.csv (same
#     matching methodology as everywhere else in this project -- see that
#     file's own header)
#   - fetch_earnings_with_time() / BMO-AMC classification, byte-for-byte
#     the same convention as GST_MatchedControlGroup_CanonicalRecompute.py
#     (tz-converted to America/New_York, hour<12 => BMO)
#   - fetch_event_window() / compute_zscore_at_anchor(), byte-for-byte the
#     same per-event, point-in-time-clean fixed-window z-score methodology
#     as GST_FixedWindow_PerEvent_Canonical.py -- applied here to the 152
#     CONTROL dates too, so the eventual regression uses a genuinely
#     continuous z-score across the full pooled sample, not an artificial
#     z=0 stand-in for controls (a disclosed design choice -- see the
#     pre-registration doc, section on the regression specification).
#
# WHAT THIS SCRIPT ADDS, not reused from elsewhere:
#   - resolves each anchor/control_date to its nearest REAL earnings
#     announcement date (yfinance get_earnings_dates, nearest within
#     +/-10 calendar days -- same SPIKE_EXCLUSION_BUFFER_DAYS=10 convention
#     already used for spike-vs-earnings proximity checks elsewhere in
#     this project) -- needed because spike_week/control_date are WEEK
#     anchors, not necessarily the exact earnings date the gap definition
#     requires.
#   - computes the daily-close-based gap (AMC: ln(next_open/ann_close);
#     BMO: ln(ann_open/prior_close)) from yfinance daily OHLC -- adequate
#     at daily resolution since gap doesn't need intraday timing, only
#     open/close prints that already exist as daily bars.
#
# Output: Live Signal Engine/C5_PostEarnings_Population.csv (n<=304, one
# row per signal OR control event; some drop for the same reasons this
# project's other per-event pulls always show attrition -- no earnings
# date resolvable, no z-score resolvable, no gap resolvable, etc, all
# disclosed via the `note` column, nothing silently dropped).

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import sys
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf
from pytrends.request import TrendReq

import GST_FixedWindow_PerEvent_Canonical as canon_mod

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

MATCHED_PATH = Path("Live Signal Engine") / "MatchedControlGroup_CanonicalRecompute.csv"
OUT_PATH = Path("Live Signal Engine") / "C5_PostEarnings_Population.csv"

EARNINGS_MATCH_WINDOW_DAYS = 10   # same SPIKE_EXCLUSION_BUFFER_DAYS convention used elsewhere

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_earnings_with_time(ticker: str) -> pd.DataFrame:
    """Byte-for-byte the same as GST_MatchedControlGroup_CanonicalRecompute.py's
    function of the same name."""
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        df = tk.get_earnings_dates(limit=40)
    except Exception as e:
        print(f"  [{ticker}] earnings pull failed: {e}")
        return pd.DataFrame(columns=["date", "bmo_amc"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "bmo_amc"])
    idx = pd.to_datetime(df.index)
    dates = idx.tz_localize(None) if idx.tz is None else idx.tz_convert("America/New_York").tz_localize(None)
    bmo_amc = ["BMO" if d.hour < 12 else "AMC" for d in dates]
    out = pd.DataFrame({"date": dates.normalize(), "bmo_amc": bmo_amc})
    return out.drop_duplicates(subset="date").reset_index(drop=True)


def nearest_earnings_date(earnings_df: pd.DataFrame, anchor: pd.Timestamp) -> tuple[pd.Timestamp | None, str | None]:
    if earnings_df.empty:
        return None, None
    diffs = (earnings_df["date"] - anchor).abs()
    idx = diffs.idxmin()
    if diffs.loc[idx].days > EARNINGS_MATCH_WINDOW_DAYS:
        return None, None
    row = earnings_df.loc[idx]
    return row["date"], row["bmo_amc"]


def fetch_daily_ohlc(ticker: str) -> pd.DataFrame:
    tk = yf.Ticker(ticker, session=YF_SESSION)
    df = tk.history(start="2020-12-01", end="2026-01-15", interval="1d", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "open", "close"])
    out = pd.DataFrame({
        "Date": pd.to_datetime(df.index).tz_localize(None),
        "open": df["Open"].to_numpy(), "close": df["Close"].to_numpy(),
    })
    return out.sort_values("Date").drop_duplicates(subset="Date").reset_index(drop=True)


def compute_gap(daily: pd.DataFrame, earnings_date: pd.Timestamp, bmo_amc: str) -> tuple[float | None, str | None]:
    """AMC: ln(next trading day's open / earnings_date's own close).
    BMO: ln(earnings_date's own open / prior trading day's close)."""
    on_date = daily.loc[daily["Date"] == earnings_date]
    if on_date.empty:
        return None, "no daily bar on the resolved earnings date"
    if bmo_amc == "AMC":
        after = daily.loc[daily["Date"] > earnings_date]
        if after.empty:
            return None, "no next trading day for AMC gap"
        next_open = after.iloc[0]["open"]
        ann_close = on_date.iloc[0]["close"]
        if next_open is None or ann_close is None or ann_close <= 0:
            return None, "missing open/close for AMC gap"
        return float(np.log(next_open / ann_close)), None
    else:  # BMO
        before = daily.loc[daily["Date"] < earnings_date]
        if before.empty:
            return None, "no prior trading day for BMO gap"
        prior_close = before.iloc[-1]["close"]
        ann_open = on_date.iloc[0]["open"]
        if prior_close is None or ann_open is None or prior_close <= 0:
            return None, "missing open/close for BMO gap"
        return float(np.log(ann_open / prior_close)), None


def main():
    print("*** C5 POST-EARNINGS TEST -- POPULATION BUILDER ***\n")
    matched = pd.read_csv(MATCHED_PATH)
    matched["spike_week"] = pd.to_datetime(matched["spike_week"])
    matched["control_date"] = pd.to_datetime(matched["control_date"])
    print(f"Matched signal/control pairs loaded: n={len(matched)}\n")

    # Build the flat list of 304 "role rows": each pair contributes one
    # signal row (ticker, spike_week, known zscore) and one control row
    # (control_ticker, control_date, zscore TO BE COMPUTED).
    role_rows = []
    for r in matched.itertuples(index=False):
        role_rows.append({"pair_id": len(role_rows) // 2, "role": "signal", "ticker": r.ticker,
                           "anchor": r.spike_week, "zscore_known": r.zscore})
        role_rows.append({"pair_id": len(role_rows) // 2, "role": "control", "ticker": r.control_ticker,
                           "anchor": r.control_date, "zscore_known": None})
    roles = pd.DataFrame(role_rows)

    tickers = sorted(roles["ticker"].unique())
    print(f"Unique tickers across signal+control roles: {len(tickers)}")
    print("Pulling earnings-date/BMO-AMC calendars and daily OHLC per ticker...\n")

    earnings_cache, daily_cache = {}, {}
    for i, t in enumerate(tickers, start=1):
        earnings_cache[t] = fetch_earnings_with_time(t)
        daily_cache[t] = fetch_daily_ohlc(t)
        print(f"  [{i}/{len(tickers)}] {t}: {len(earnings_cache[t])} earnings dates, {len(daily_cache[t])} daily bars")
        time.sleep(0.8)
    print()

    print("Resolving earnings date / BMO-AMC / gap for each of the 304 role-rows...\n")
    for row in role_rows:
        t, anchor = row["ticker"], row["anchor"]
        edate, bmo_amc = nearest_earnings_date(earnings_cache.get(t, pd.DataFrame()), anchor)
        row["earnings_date"] = edate.date() if edate is not None else None
        row["bmo_amc"] = bmo_amc
        row["note"] = ""
        if edate is None:
            row["note"] = f"no real earnings date within {EARNINGS_MATCH_WINDOW_DAYS}d of anchor {anchor.date()}"
            row["gap"] = None
            continue
        gap, gap_note = compute_gap(daily_cache.get(t, pd.DataFrame()), edate, bmo_amc)
        row["gap"] = gap
        if gap_note:
            row["note"] = gap_note

    resolved = pd.DataFrame(role_rows)
    n_gap_ok = resolved["gap"].notna().sum()
    print(f"Rows with a resolved earnings date + gap: {n_gap_ok} / {len(resolved)}\n")

    # --- continuous z-score for CONTROL rows (signal rows already have zscore_known) ---
    needs_z = resolved[(resolved["role"] == "control") & resolved["gap"].notna()].copy()
    print(f"Control rows needing a fresh point-in-time z-score computation: {len(needs_z)}")
    print("(same per-event fixed-window pytrends methodology as every signal event's own z-score,")
    print(" applied here to the control dates -- this is what makes the eventual regression use a")
    print(" genuinely CONTINUOUS z-score across signal+control, not an artificial z=0 for controls.)\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0, requests_args={"verify": False})
    computed_z = {}
    for i, r in enumerate(needs_z.itertuples(index=False), start=1):
        weekly = canon_mod.fetch_event_window(pt, r.ticker, r.anchor)
        _, z, note = canon_mod.compute_zscore_at_anchor(weekly, r.anchor)
        computed_z[(r.pair_id, r.role)] = (z, note)
        print(f"  [{i}/{len(needs_z)}] {r.ticker} {r.anchor.date()}: control_zscore="
              f"{'None' if z is None else round(z, 3)} {note}")

    resolved["zscore"] = resolved.apply(
        lambda r: r["zscore_known"] if r["role"] == "signal" else computed_z.get((r["pair_id"], r["role"]), (None, ""))[0],
        axis=1)
    resolved["zscore_note"] = resolved.apply(
        lambda r: "" if r["role"] == "signal" else computed_z.get((r["pair_id"], r["role"]), (None, ""))[1],
        axis=1)

    resolved.drop(columns=["zscore_known"], inplace=True)
    resolved.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}\n")

    usable = resolved[resolved["gap"].notna() & resolved["zscore"].notna()]
    print("=== POPULATION SUMMARY ===")
    print(f"Total role-rows: {len(resolved)} (152 signal + 152 control)")
    print(f"Usable (real earnings date + gap + zscore all resolved): {len(usable)}")
    complete_pairs = usable.groupby("pair_id").size()
    n_complete_pairs = (complete_pairs == 2).sum()
    print(f"Complete pairs (BOTH signal and control usable): {n_complete_pairs} / {len(matched)}")
    print(f"BMO/AMC split (usable rows): \n{usable['bmo_amc'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
