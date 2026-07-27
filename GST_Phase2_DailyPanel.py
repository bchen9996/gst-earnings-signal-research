#!/usr/bin/env python3
# GST PHASE 2 -- DAILY INFORMATION ARRIVAL PANEL
# Per the locked spec: Live Signal Engine/GST_Phase2_InformationArrivalPanel_SPEC_DRAFT.md
# (commit 490332d). Pulls, for a single run, six fields per ticker across the
# confirmed 24-ticker Phase 2 universe (spec Section 2):
#   GST z-score, Wikipedia pageview z-score, implied volatility, realized
#   volatility, price, volume, plus days_to_nearest_earnings.
#
# THIS IS A MANUAL TEST RUN SCRIPT ONLY. Not wired into GitHub Actions.
# Per spec Section 6b, the unconditional option-chain (IV) leg has never
# been run before at any scale -- this script's first run is the actual
# measurement of its per-ticker timing cost, replacing the spec's
# extrapolated 13-27s/ticker estimate (Section 6a) with a real one.
#
# REUSE, NOT REIMPLEMENTATION -- what's imported from where and why:
#   - GST z-score: fetch_ticker_series() + compute_latest_zscore() from
#     GST_Live_Signal_Engine.py. This is NOT GST_FixedWindow_PerEvent_Canonical.py's
#     own compute_zscore_at_anchor() -- that function scores a PAST event at a
#     fixed historical anchor. compute_latest_zscore() is the live-engine's
#     "today" equivalent, and is CONFIRMED to use the exact same parameters
#     (ROLLING_WINDOW=12, MIN_PERIODS=8, STD_EPSILON_FLOOR=1.0,
#     PULL_LOOKBACK_DAYS=300, shift(1) rolling) as the Canonical script --
#     same methodology, just the branch of that methodology built for "now"
#     instead of "then". This is also exactly what GST_MultiTicker_Forward_Log.py
#     already reuses for its own live per-ticker GST z-score.
#   - Wikipedia z-score: TICKER_TO_WIKI_ARTICLE, fetch_daily_pageviews(),
#     to_weekly() from GST_Wikipedia_Pageviews_Pull.py (built 2026-07-26),
#     plus compute_zscore_at_anchor() from GST_FixedWindow_PerEvent_Canonical.py
#     (same function the Wikipedia pull itself reuses, anchored at TODAY
#     instead of a past spike_week).
#   - Realized volatility: trailing_realized_vol() from
#     GST_FixedWindow_PerEvent_Canonical.py, called directly (not reimplemented)
#     against a small live daily-return frame built from yfinance price
#     history -- same formula, same VOL_LOOKBACK_TRADING_DAYS=60 /
#     MIN_VOL_HISTORY_DAYS=30 constants, same shape the function already expects.
#   - Implied volatility: get_option_snapshot() from GST_MultiTicker_Forward_Log.py,
#     called UNCONDITIONALLY (every ticker, every run) instead of only for
#     tickers within the earnings window -- this is the untested leg per
#     spec Section 6a/6b. Expiry choice: get_nearest_post_earnings_expiry()
#     (also from GST_MultiTicker_Forward_Log.py), reused as-is but called
#     with TODAY'S date instead of an earnings date -- it already does
#     exactly what's needed here ("nearest expiration strictly after
#     [date]"), so passing today's date gets "nearest expiration strictly
#     after today" for free. This exists because the first smoke test
#     (single-ticker, AAPL) picking the literal nearest expiration
#     (tk.options[0]) landed on a same-day 0DTE contract and returned a
#     degenerate near-zero call IV (1.0e-05) -- caught before the full run,
#     not after.
#   - days_to_nearest_earnings: fetch_days_to_next_earnings() from
#     GST_Live_Signal_Engine.py, the exact function GST_MultiTicker_Forward_Log.py
#     already uses for its own days_to_next_earnings field. NOTE: this only
#     ever looks FORWARD (next upcoming earnings date, per its own
#     docstring) -- there is no "nearest including past earnings" lookup
#     anywhere in this project to reuse, and building one would itself be
#     reimplementing rather than reusing. Column is named
#     days_to_nearest_earnings to match the spec's field name, but its
#     values are exactly this forward-looking lookup's output -- disclosed
#     here, not hidden.
#   - Price, volume: read directly off the same yfinance price-history pull
#     used for realized volatility (tk.history()) -- one fewer network call
#     than adding a separate fast_info quote, and avoids a confirmed dead
#     key lookup in the currently installed yfinance version (fast_info's
#     "last_price"/"bid"/"ask" keys returned None in a live check against
#     this environment; the multiticker log's fast_info-first fallback
#     chain would silently fall through to history anyway).
#
# ORDERING CONSTRAINT (carried over from GST_MSFT_Forward_Quote_Log.py /
# GST_MultiTicker_Forward_Log.py): days-to-earnings MUST be fetched before
# any tk.history/tk.options/tk.option_chain/tk.fast_info call for the SAME
# ticker -- a confirmed one-directional yfinance internal-state quirk where
# an options-chain call first leaves get_earnings_dates() silently
# returning nothing. Don't reshuffle process_ticker()'s call order.
#
# Output: Live Signal Engine/GST_Phase2_DailyPanel_TestRun_<run-date>.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
import random
import sys
import time
import pandas as pd
import requests
import yfinance as yf
from pytrends.request import TrendReq

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from GST_Live_Signal_Engine import (
    fetch_ticker_series, compute_latest_zscore, fetch_days_to_next_earnings,
)
import GST_FixedWindow_PerEvent_Canonical as canonical
from GST_Wikipedia_Pageviews_Pull import TICKER_TO_WIKI_ARTICLE, fetch_daily_pageviews, to_weekly
from GST_MultiTicker_Forward_Log import get_option_snapshot, get_nearest_post_earnings_expiry

# Confirmed 24-ticker Phase 2 universe, spec Section 2 (2026-07-26 feasibility decision).
TICKERS = [
    "AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
    "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
    "SYK", "TSLA", "TTWO", "UAL",
]

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

PRICE_HISTORY_PERIOD = "6mo"   # margin over VOL_LOOKBACK_TRADING_DAYS=60 trading days

# Reused directly, not redeclared -- same discipline as GST_Wikipedia_Pageviews_Pull.py.
PULL_LOOKBACK_DAYS = canonical.PULL_LOOKBACK_DAYS          # 300
VOL_LOOKBACK_TRADING_DAYS = canonical.VOL_LOOKBACK_TRADING_DAYS  # 60
MIN_VOL_HISTORY_DAYS = canonical.MIN_VOL_HISTORY_DAYS       # 30

BETWEEN_TICKERS = (1.5, 3.0)   # same pacing as GST_Live_Signal_Engine.py / GST_MultiTicker_Forward_Log.py
MICRO_BATCH_SIZE = 6
MICRO_BATCH_PAUSE_S = 20


def process_ticker(pt: TrendReq, ticker: str, run_ts: datetime) -> dict:
    row = {"ticker": ticker, "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat()}
    timings = {}
    t_ticker_start = time.time()

    # --- days to nearest (next) earnings -- MUST run before any yfinance
    # history/options call for this ticker. See ORDERING CONSTRAINT above.
    t0 = time.time()
    try:
        days_to_earnings = fetch_days_to_next_earnings(ticker)
    except Exception as e:
        days_to_earnings = None
        row["earnings_error"] = str(e)
    row["days_to_nearest_earnings"] = days_to_earnings
    timings["earnings_lookup_s"] = time.time() - t0

    tk = yf.Ticker(ticker, session=YF_SESSION)

    # --- price history (feeds both price/volume and realized vol) ---
    t0 = time.time()
    try:
        hist = tk.history(period=PRICE_HISTORY_PERIOD)
    except Exception as e:
        hist = pd.DataFrame()
        row["price_history_error"] = str(e)
    timings["price_history_pull_s"] = time.time() - t0

    price = volume = price_asof = None
    if not hist.empty:
        price = float(hist["Close"].iloc[-1])
        volume = int(hist["Volume"].iloc[-1])
        price_asof = hist.index[-1]
        price_asof = (price_asof.tz_localize(None) if price_asof.tzinfo else price_asof).date()
    row["price"] = price
    row["volume"] = volume
    row["price_asof_date"] = price_asof.isoformat() if price_asof else None

    # --- realized volatility: canonical.trailing_realized_vol(), reused verbatim ---
    t0 = time.time()
    realized_vol = None
    if not hist.empty:
        idx = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
        ret_col = f"{ticker} Daily Return"
        daily = pd.DataFrame({"Date": idx, ret_col: hist["Close"].pct_change().to_numpy()})
        cutoff = pd.Timestamp(run_ts.date())
        realized_vol = canonical.trailing_realized_vol(daily, ret_col, cutoff)
    row["realized_vol"] = realized_vol
    timings["realized_vol_compute_s"] = time.time() - t0

    # --- implied volatility: unconditional option-chain pull (the untested leg) ---
    t0 = time.time()
    try:
        expiry = get_nearest_post_earnings_expiry(tk, run_ts.date())
    except Exception as e:
        expiry = None
        row["iv_error"] = str(e)
    if expiry and price:
        row["option_expiry"] = expiry
        snap = get_option_snapshot(tk, expiry, price)
        row.update(snap)
        ivs = [v for v in (snap.get("call_implied_volatility"), snap.get("put_implied_volatility"))
               if v is not None]
        row["implied_volatility"] = round(sum(ivs) / len(ivs), 6) if ivs else None
        if not ivs and "option_chain_error" not in snap:
            row["iv_note"] = "option chain returned but no impliedVolatility on ATM call/put"
    else:
        row["implied_volatility"] = None
        row["iv_note"] = "no expiration strictly after today available" if not expiry else "no spot price to select ATM strike"
    timings["iv_pull_s"] = time.time() - t0

    # --- GST z-score: exact live-engine functions, same params as Canonical ---
    t0 = time.time()
    try:
        series = fetch_ticker_series(pt, ticker)
        z = compute_latest_zscore(series)
        row["gst_zscore"] = z.get("zscore")
        row["gst_value"] = z.get("gst_value")
        row["gst_week"] = z.get("week")
        row["gst_is_partial_week"] = z.get("is_partial_week")
        row["gst_note"] = z.get("note", "")
    except Exception as e:
        row["gst_error"] = str(e)
    timings["gst_pull_s"] = time.time() - t0

    # --- Wikipedia pageview z-score: same reused functions as the July 26 pull ---
    t0 = time.time()
    article = TICKER_TO_WIKI_ARTICLE.get(ticker)
    if article is None:
        row["wiki_error"] = "no verified Wikipedia article mapping for this ticker"
    else:
        anchor = pd.Timestamp(run_ts.date())
        pull_start = anchor - timedelta(days=PULL_LOOKBACK_DAYS)
        try:
            daily_views = fetch_daily_pageviews(article, pull_start, anchor)
            weekly = to_weekly(daily_views)
            aligned_week, wiki_z, note = canonical.compute_zscore_at_anchor(weekly, anchor)
            row["wikipedia_article"] = article
            row["wiki_zscore"] = round(wiki_z, 4) if wiki_z is not None else None
            row["wiki_aligned_week"] = aligned_week.date().isoformat() if aligned_week is not None else None
            row["wiki_note"] = note
        except Exception as e:
            row["wiki_error"] = str(e)
    timings["wiki_pull_s"] = time.time() - t0

    for k, v in timings.items():
        row[f"timing_{k}"] = round(v, 3)
    row["ticker_total_s"] = round(time.time() - t_ticker_start, 3)

    six_fields = [row.get("gst_zscore"), row.get("wiki_zscore"), row.get("implied_volatility"),
                  row.get("realized_vol"), row.get("price"), row.get("volume")]
    row["all_six_fields_clean"] = all(v is not None for v in six_fields) and days_to_earnings is not None

    return row


def main():
    run_ts = datetime.now(timezone.utc)
    run_date = run_ts.date()
    print(f"*** GST PHASE 2 -- DAILY INFORMATION ARRIVAL PANEL (MANUAL TEST RUN) ***")
    print(f"Run timestamp (UTC): {run_ts.isoformat()}")
    print(f"Universe: {len(TICKERS)} tickers\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    rows = []
    wall_start = time.time()
    for i, ticker in enumerate(TICKERS, start=1):
        t0 = time.time()
        row = process_ticker(pt, ticker, run_ts)
        elapsed = time.time() - t0
        rows.append(row)
        status = "CLEAN" if row["all_six_fields_clean"] else "INCOMPLETE"
        print(f"[{i}/{len(TICKERS)}] {ticker}: {elapsed:.2f}s  {status}  "
              f"gst_z={row.get('gst_zscore')} wiki_z={row.get('wiki_zscore')} "
              f"iv={row.get('implied_volatility')} rv={row.get('realized_vol')} "
              f"price={row.get('price')} vol={row.get('volume')} "
              f"days_to_earnings={row.get('days_to_nearest_earnings')}")
        errs = {k: v for k, v in row.items() if k.endswith("_error")}
        if errs:
            print(f"    errors: {errs}")

        if i != len(TICKERS):
            time.sleep(random.uniform(*BETWEEN_TICKERS))
            if i % MICRO_BATCH_SIZE == 0:
                print(f"— small batch pause ({MICRO_BATCH_PAUSE_S}s) —")
                time.sleep(MICRO_BATCH_PAUSE_S)

    wall_total = time.time() - wall_start

    df = pd.DataFrame(rows)
    df.insert(0, "run_date", run_date.isoformat())
    out_path = OUT_DIR / f"GST_Phase2_DailyPanel_TestRun_{run_date.isoformat()}.csv"
    df.to_csv(out_path, index=False)

    n_clean = int(df["all_six_fields_clean"].sum())
    print(f"\n=== RUN SUMMARY ===")
    print(f"Tickers: {len(df)}  Clean (all 6 fields + earnings): {n_clean}  Incomplete: {len(df) - n_clean}")
    print(f"Total wall time: {wall_total:.1f}s ({wall_total/60:.2f} min) for {len(df)} tickers "
          f"-> {wall_total/len(df):.2f}s/ticker average (includes inter-ticker pacing sleeps)")
    print(f"Per-ticker work time (excludes pacing sleeps): "
          f"mean={df['ticker_total_s'].mean():.2f}s  min={df['ticker_total_s'].min():.2f}s  "
          f"max={df['ticker_total_s'].max():.2f}s")
    for leg in ["earnings_lookup_s", "price_history_pull_s", "realized_vol_compute_s",
                "iv_pull_s", "gst_pull_s", "wiki_pull_s"]:
        col = f"timing_{leg}"
        if col in df.columns:
            print(f"  {leg}: mean={df[col].mean():.2f}s  max={df[col].max():.2f}s")

    if len(df) - n_clean > 0:
        print("\nIncomplete tickers (field-level):")
        incomplete = df[~df["all_six_fields_clean"]]
        for _, r in incomplete.iterrows():
            missing = []
            if pd.isna(r.get("gst_zscore")): missing.append("gst_zscore")
            if pd.isna(r.get("wiki_zscore")): missing.append("wiki_zscore")
            if pd.isna(r.get("implied_volatility")): missing.append("implied_volatility")
            if pd.isna(r.get("realized_vol")): missing.append("realized_vol")
            if pd.isna(r.get("price")): missing.append("price")
            if pd.isna(r.get("volume")): missing.append("volume")
            if pd.isna(r.get("days_to_nearest_earnings")): missing.append("days_to_nearest_earnings")
            print(f"  {r['ticker']}: missing {missing}")

    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
