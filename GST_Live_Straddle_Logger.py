#!/usr/bin/env python3
# GST Live Straddle Logger — companion to GST_Live_Signal_Engine.py.
#
# Reads the most recent watchlist (Live Signal Engine/watchlist_latest.csv),
# takes every ticker flagged eligible_for_options_leg == True (spike AND
# clear/unambiguous symbol), pulls its current option chain via yfinance,
# and records the ATM straddle cost at today's prices — the entry point for
# a live, forward, zero-look-ahead paper trade of the volatility finding
# (spike weeks show ~2x the price-move magnitude of baseline weeks,
# validated pooled/OOS/per-ticker/independent-category/broader-universe
# throughout this project).
#
# *** STRATEGY UNDER FORWARD TEST — FINAL, PRE-REGISTERED SPECIFICATION ***
# STRONG_EARNINGS tier entry (z>=5 AND an earnings date within 5 days
# upcoming, per GST_Live_Signal_Engine.py's tiering — see THRESHOLD
# REFINEMENT note below for why this is z>=5, not z>=4) — at-the-money
# straddle, EXIT AT THE NEXT TRADING DAY'S CLOSE AFTER THE EARNINGS
# ANNOUNCEMENT (see EXIT RULE REFINEMENT note below — replaces the
# original hold-to-end-of-spike-week rule), priced at real market prices.
# This is the end state of a chain of pre-specified tests (run at the
# ORIGINAL z>=4 cutoff — historical record, not rewritten to match the
# current live threshold):
#   - GST_Strategy_Refinement_Test.py: z>=4 beat the unfiltered baseline;
#     a +50%/5-day early-exit rule was tested and REJECTED (a DIFFERENT
#     profit/time-triggered rule than the earnings-event-anchored exit
#     below — see EXIT RULE REFINEMENT for how these two findings coexist
#     without contradiction). This script never implemented any exit path
#     itself — expiration is picked once at entry and never closed early
#     by code; the exit rule below is applied manually when checking
#     outcomes against the paper-trade log, same as "hold the full window"
#     always was.
#   - GST_Straddle_Simulation_2021_2025_51Ticker.py: growing the z>=4
#     NON-EARNINGS subsample from n=11 to n=88 REVERSED the result (median
#     P&L went from positive to -17.0%/-20.6%). Plain STRONG (z>=4 without
#     nearby earnings) is NOT part of the validated edge.
#   - GST_EarningsAdjacent_SpikeVsNoSpike_Test.py: among earnings-adjacent
#     weeks only, z>=4 beat no-spike by +131.1/+62.4 pts (p=0.0000 both
#     horizons, n=209 vs n=110) — this is the combination that's real.
#
# *** THRESHOLD REFINEMENT: z>=4 -> z>=5 ***
# Threshold raised from z>=4 to z>=5 based on in-sample zscore breakdown
# analysis (zscore_threshold_breakdown.csv) showing monotonic improvement
# in win rate and median P&L. This refinement is simulated-better but not
# yet validated out-of-sample - the forward test will evaluate z>=5
# economics specifically.
#
# *** EXIT RULE REFINEMENT: hold-to-end-of-spike-week -> next-day-after-earnings ***
# Based on GST_Task1_ExitOptimization.py (Live Signal Engine/
# Task1_ExitOptimization_Results.csv), which compared three exit rules on
# the same 147 z>=5 STRONG_EARNINGS events, earnings-aware pricing:
#   - exit SAME DAY as the earnings announcement: n=85, 42.4% win,
#     -10.1% median — a LOSING rule (often exits before the market has
#     finished digesting the reaction, especially for AMC reporters).
#   - exit NEXT TRADING DAY'S CLOSE after earnings: n=138, 82.6% win,
#     +165.1% median — beats the prior full-week-hold spec (76.2% win,
#     +130.0% median), p=0.0170.
#   - hold to end of spike week (the ORIGINAL spec): n=147, 76.2% win,
#     +130.0% median.
# Still simulation-priced and pending real-price forward validation, same
# as every other spec in this project. No code logic changed here — this
# script only records entry (spot price, expiration, ATM strike, straddle
# cost at signal time); the exit decision is applied manually when
# checking outcomes against the paper-trade log.
#
# *** OPENING GAP NOTE ***
# Opening gap analysis (Live Signal Engine/OpeningGap_Analysis.csv) shows
# spike events produce a mean absolute overnight gap of 6.60% vs 3.01% for
# the no-spike baseline (p<0.0001). The gap accounts for 63.7% (median) of
# total move magnitude, but gap and intraday moves often offset in
# direction (mean SIGNED fraction: -37.9%) — the exit-day intraday session
# is not just noise around the gap, it's a real, partly-offsetting
# component. The full entry-to-exit move explains straddle P&L better
# than the gap alone (R^2=0.57 vs 0.31). Implication: the next-day-close
# exit rule above correctly captures both the gap AND the residual
# intraday move — do NOT exit at the open on the day after earnings, since
# the intraday session adds meaningful incremental P&L beyond the gap.
#
# *** LONGITUDINAL STABILITY NOTE ***
# The signal showed decay within 2014-2019 (81.2% -> 52.2% win rate) but
# reset to a stable 73-79% band in 2021-2025 with no further decay across
# 5 years. Monitor live results year-over-year for signs of regime decay.
# If forward-test win rate trends consistently downward over 12+ months,
# treat as a warning signal.
#
# *** LONGITUDINAL COVERAGE NOTE ***
# Signal confirmed positive across 12 consecutive years (2014-2025)
# including COVID 2020 (76.2% win, +174.5% median, n=21). Formal
# structural break at 2019/2021 confirmed (Chow F=51.87, p=0.0001).
#
# *** ENTRY TIMING NOTE ***
# Signal decay analysis shows the sweet spot is 2-4 days before earnings
# (86.1% and 85.4% win rates). 1-day-before entry shows materially worse
# economics (50.0% win, n=8). Enter straddle on signal detection day
# rather than waiting for closer confirmation — detection already occurs
# at 2-5 days out by construction.
#
# *** POSITION SIZING NOTE (suggested guideline, NOT a validated filter) ***
# The P(win|z) calibration curve (Live Signal Engine/
# PwinCalibrationCurve_Results.csv) shows earnings-adjacent win rate
# climbing to ~76% around z=8.3-9.6, well above the ~62% seen right at the
# z>=5 threshold. Within the STRONG_EARNINGS tier, z-score magnitude
# itself appears informative — a z=9 signal has a meaningfully higher
# empirical win rate than a z=5.1 signal, even though both clear the same
# binary threshold and are currently logged/treated identically. Consider
# scaling position size proportionally to z-score rather than sizing every
# STRONG_EARNINGS signal the same. This is a suggested guideline based on
# the calibration curve, not a validated filter — no dedicated test has
# confirmed a sizing rule improves risk-adjusted outcomes, and this script
# does not implement it (it logs the same ATM straddle cost regardless of
# z-score); it is a documentation-only note for discretionary consideration.
#
# *** UPDATE — CALENDAR-TIME PORTFOLIO SIMULATION CONTRADICTS THIS ***
# The calendar-time portfolio simulation (Live Signal Engine/
# CalendarTimePortfolio_Results.csv) tested a concrete z-proportional
# sizing rule (floor $10k at z=5, linear scaling, cap $50k) against flat
# $10k sizing across all 147 STRONG_EARNINGS events, chronologically. Flat
# sizing produced a HIGHER risk-adjusted return (Sharpe 2.33) than
# z-proportional sizing (Sharpe 1.84), despite z-proportional sizing
# producing a higher gross return (+5380.7% vs +2369.5%) — the extra
# return came with proportionally more variance, not a better risk-adjusted
# outcome. So while the calibration curve above shows higher z carries a
# genuinely higher win rate, that edge did NOT translate into a better
# risk-adjusted result under this simulation's linear sizing rule.
# RECOMMENDATION: use flat sizing for now. Revisit proportional sizing
# only if the live forward test accumulates enough real trades to evaluate
# Sharpe directly, rather than relying on this simulation's assumptions.
#
# All three tiers are logged (STRONG_EARNINGS, STRONG, STANDARD, carried
# over from the watchlist's signal_tier column) so the record stays
# complete, but STRONG_EARNINGS is now tracked independently in the
# summary output as the primary hypothesis under test — STRONG (non-
# earnings) and STANDARD are reference/comparison only, expected to show
# no edge based on the tests above.
#
# This is a PAPER TRADE LOG ONLY — no order is placed, no money moves. It
# exists to create an immutable, timestamped record of what the signal
# would have entered and at what cost, so a future check-in can compare
# against what actually happened without any risk of after-the-fact
# cherry-picking. Every row is appended, never rewritten or deleted.
#
# Expiration selection: nearest listed expiration >= TARGET_MIN_DTE days out
# (default 21 — matches the 3-week/~15-trading-day window the volatility
# finding was measured over). ATM strike = closest listed strike to the
# current spot price. Straddle cost = call mid + put mid at that strike
# (mid = (bid+ask)/2 when both are quoted and positive, else lastPrice).
#
# Idempotent: if a (ticker, watchlist run_timestamp) pair is already logged,
# it's skipped rather than duplicated — safe to re-run.
#
# Input : Live Signal Engine/watchlist_latest.csv
# Output: Live Signal Engine/straddle_paper_trades_log.csv  (append-only)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import sys
import urllib3
import requests
import pandas as pd
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

WATCHLIST_PATH = Path("Live Signal Engine") / "watchlist_latest.csv"
LOG_PATH = Path("Live Signal Engine") / "straddle_paper_trades_log.csv"

TARGET_MIN_DTE = 21   # calendar days — matches the 3-week window the finding was measured over

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def pick_expiration(expirations: list[str], today) -> tuple[str, int] | None:
    candidates = []
    for e in expirations:
        exp_date = datetime.strptime(e, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        candidates.append((e, dte))
    eligible = [c for c in candidates if c[1] >= TARGET_MIN_DTE]
    if eligible:
        return min(eligible, key=lambda c: c[1])
    if candidates:
        return max(candidates, key=lambda c: c[1])  # fallback: longest available
    return None


def mid_price(row: pd.Series) -> float | None:
    bid, ask, last = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    if last is not None and last > 0:
        return float(last)
    return None


def log_straddle(ticker: str, watchlist_row: pd.Series, snapshot_ts: str) -> dict:
    tk = yf.Ticker(ticker, session=SESSION)

    try:
        spot = tk.fast_info.get("lastPrice")
    except Exception as e:
        return {"ticker": ticker, "status": "spot_fetch_failed", "error": str(e)}

    if not spot:
        return {"ticker": ticker, "status": "no_spot_price", "error": ""}

    try:
        expirations = tk.options
    except Exception as e:
        return {"ticker": ticker, "status": "no_options_chain", "error": str(e)}

    if not expirations:
        return {"ticker": ticker, "status": "no_expirations_listed", "error": ""}

    today = datetime.now(timezone.utc).date()
    picked = pick_expiration(list(expirations), today)
    if picked is None:
        return {"ticker": ticker, "status": "no_expiration_found", "error": ""}
    expiration, dte = picked

    try:
        chain = tk.option_chain(expiration)
    except Exception as e:
        return {"ticker": ticker, "status": "chain_fetch_failed", "error": str(e)}

    calls, puts = chain.calls, chain.puts
    if calls.empty or puts.empty:
        return {"ticker": ticker, "status": "empty_chain", "error": ""}

    atm_strike = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]["strike"].values[0]

    call_rows = calls[calls["strike"] == atm_strike]
    put_rows = puts[puts["strike"] == atm_strike]
    if call_rows.empty or put_rows.empty:
        return {"ticker": ticker, "status": "no_matching_strike", "error": ""}

    call_row, put_row = call_rows.iloc[0], put_rows.iloc[0]
    call_mid = mid_price(call_row)
    put_mid = mid_price(put_row)

    if call_mid is None or put_mid is None:
        return {"ticker": ticker, "status": "no_usable_quote", "error": ""}

    # ENTRY TIMING NOTE (see header): 1-day-out entries historically show materially
    # worse economics (50.0% win, n=8) than the 2-4 day sweet spot (86.1%/85.4% win).
    # Flagged, not blocked — the trade is still logged, this just makes the decision
    # conscious rather than accidental.
    tier = watchlist_row.get("signal_tier")
    days_to_earnings = watchlist_row.get("days_to_earnings")
    entry_timing_warning = ""
    if tier == "STRONG_EARNINGS" and pd.notna(days_to_earnings) and float(days_to_earnings) <= 1:
        entry_timing_warning = ("1-DAY-OUT: historically 50% win rate vs 86% at 2-4 days - "
                                 "consider skipping or sizing down")

    return {
        "ticker": ticker,
        "status": "ok",
        "error": "",
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "signal_watchlist_timestamp": snapshot_ts,
        "signal_week": watchlist_row.get("week"),
        "signal_zscore": watchlist_row.get("zscore"),
        "signal_tier": tier,
        "signal_days_to_earnings": days_to_earnings,
        "spot_price": round(float(spot), 2),
        "expiration": expiration,
        "days_to_expiration": dte,
        "atm_strike": float(atm_strike),
        "call_mid": round(call_mid, 3),
        "put_mid": round(put_mid, 3),
        "straddle_cost": round(call_mid + put_mid, 3),
        "call_iv": round(float(call_row.get("impliedVolatility")), 4) if pd.notna(call_row.get("impliedVolatility")) else None,
        "put_iv": round(float(put_row.get("impliedVolatility")), 4) if pd.notna(put_row.get("impliedVolatility")) else None,
        "entry_timing_warning": entry_timing_warning,
    }


def main():
    if not WATCHLIST_PATH.exists():
        print(f"No watchlist found at {WATCHLIST_PATH} — run GST_Live_Signal_Engine.py first.")
        return

    watchlist = pd.read_csv(WATCHLIST_PATH)
    eligible = watchlist[watchlist["eligible_for_options_leg"] == True]  # noqa: E712

    if eligible.empty:
        print("No tickers eligible for the options leg in the latest watchlist (no spike + clear-symbol tickers).")
        return

    snapshot_ts = eligible["run_timestamp"].iloc[0]

    existing = pd.DataFrame()
    already_logged = set()
    if LOG_PATH.exists():
        existing = pd.read_csv(LOG_PATH)
        if not existing.empty:
            already_logged = set(zip(existing["ticker"], existing["signal_watchlist_timestamp"]))

    n_strong_earnings = int((eligible["signal_tier"] == "STRONG_EARNINGS").sum())
    n_strong = int((eligible["signal_tier"] == "STRONG").sum())
    n_standard = int((eligible["signal_tier"] == "STANDARD").sum())
    print(f"{len(eligible)} eligible tickers from watchlist run {snapshot_ts} "
          f"({n_strong_earnings} STRONG_EARNINGS / PRIMARY HYPOTHESIS under forward test, "
          f"{n_strong} STRONG / reference only, {n_standard} STANDARD / reference only)\n")

    new_rows = []
    for _, row in eligible.iterrows():
        ticker = row["ticker"]
        if (ticker, snapshot_ts) in already_logged:
            print(f"[{ticker}] already logged for this watchlist run, skipping")
            continue

        result = log_straddle(ticker, row, snapshot_ts)
        new_rows.append(result)

        if result["status"] == "ok":
            print(f"[{ticker}] [{result['signal_tier']}] spot=${result['spot_price']} exp={result['expiration']} "
                  f"({result['days_to_expiration']}d) strike={result['atm_strike']} "
                  f"straddle=${result['straddle_cost']}")
            if result.get("entry_timing_warning"):
                print(f"    *** ENTRY TIMING WARNING [{ticker}]: {result['entry_timing_warning']} ***")
        else:
            print(f"[{ticker}] FAILED: {result['status']} {result.get('error', '')}")

    if not new_rows:
        print("\nNothing new to log.")
        return

    new_df = pd.DataFrame(new_rows)
    new_df.to_csv(LOG_PATH, mode="a", index=False, header=not LOG_PATH.exists())

    n_ok = int((new_df["status"] == "ok").sum())
    n_ok_strong_earnings = int(((new_df["status"] == "ok") & (new_df["signal_tier"] == "STRONG_EARNINGS")).sum())
    print(f"\nLogged {n_ok}/{len(new_df)} new straddle entries to: {LOG_PATH} "
          f"({n_ok_strong_earnings} STRONG_EARNINGS / PRIMARY HYPOTHESIS under forward test)")

    if "entry_timing_warning" in new_df.columns:
        warned = new_df[(new_df["status"] == "ok") & (new_df["entry_timing_warning"] != "")]
        if not warned.empty:
            print(f"\n*** {len(warned)} entry logged with a 1-DAY-OUT TIMING WARNING: "
                  f"{', '.join(warned['ticker'].tolist())} — see entry_timing_warning column. ***")

    print("This is a paper-trade record only — no orders were placed.")


if __name__ == "__main__":
    main()
