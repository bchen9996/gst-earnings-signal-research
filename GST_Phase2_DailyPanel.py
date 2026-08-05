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
#   - GST z-score: compute_latest_zscore() from GST_Live_Signal_Engine.py,
#     unchanged -- confirmed to use the exact same parameters
#     (ROLLING_WINDOW=12, MIN_PERIODS=8, STD_EPSILON_FLOOR=1.0,
#     PULL_LOOKBACK_DAYS=300, shift(1) rolling) as
#     GST_FixedWindow_PerEvent_Canonical.py's own per-event z-score function
#     -- same methodology, just the branch built for "now" instead of "then".
#     The QUERY itself (fetch_ticker_series() in Live Signal Engine) is
#     NOT reused as-is here -- see the SCOPED 429-BACKOFF FIX note below for
#     why this one piece has a local variant instead of a direct import.
#   - This is also exactly what GST_MultiTicker_Forward_Log.py reuses for
#     its own live per-ticker GST z-score (compute_latest_zscore(), same
#     as here).
#   - Wikipedia z-score: TICKER_TO_WIKI_ARTICLE, fetch_daily_pageviews(),
#     to_weekly() from GST_Wikipedia_Pageviews_Pull.py (built 2026-07-26),
#     plus compute_zscore_at_anchor() from GST_FixedWindow_PerEvent_Canonical.py
#     (same function the Wikipedia pull itself reuses, anchored at TODAY
#     instead of a past spike_week). NOT MODIFIED by this task -- see the
#     OPERATIONAL SAFEGUARDS note below for why an outer time budget is
#     wrapped around it instead of changing its internals.
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
# SCOPED 429-BACKOFF FIX (2026-07-27, after 2 manual test runs) -- WHY THIS
# SCRIPT HAS ITS OWN fetch_ticker_series() INSTEAD OF IMPORTING
# GST_Live_Signal_Engine's:
# Both manual test runs of this script hit real pytrends 429s -- 9/24
# tickers in run 1, 7/24 in run 2, different tickers each time, confirming
# it's a recurring cost, not one-run bad luck. GST_Live_Signal_Engine's
# fetch_ticker_series() (and ~16 other scripts project-wide using the
# identical pattern) retries 429s with a FLAT, UN-JITTERED 60s sleep
# (HARD_429_SLEEP=60, no growth, no randomization on the 429 branch --
# jitter only exists on that function's *non*-429 branch). Of the 16
# ticker-level 429 incidents logged across both runs, 11 cleared after
# exactly ONE 60s wait (suggesting a shorter first retry would often
# succeed sooner), while 3 tickers (NKE run 1, QCOM run 1, ABBV run 2)
# needed 2-3 waits (so persistent cases still need real escalation, not
# just a uniformly shorter wait).
# This fix is DELIBERATELY SCOPED to this script only, per explicit
# instruction -- GST_Live_Signal_Engine.py and the other ~16 scripts
# sharing its flat-60s pattern are untouched. Changing that shared,
# already-in-production code is a separate decision this task does not
# make. fetch_ticker_series_scoped_backoff() below reuses the query
# construction and output shape verbatim (same GEO/GPROP/CATEGORY,
# imported not redeclared) -- only the 429 retry schedule differs.
# Backoff shape modeled on GST_GDELT_PreSpike_NewsVolume_Test.py's
# escalating-list pattern (BACKOFF_429_S = [75, 90, 120, 150] there, for a
# different API), but with a SHORTER first retry tuned to this script's own
# observed data above, plus jitter added to the 429 branch specifically
# (absent from the original) to desynchronize retries across tickers in
# the same run. MAX_ATTEMPTS is kept at 5, unchanged from the original, so
# a run-3 comparison isolates the effect of the backoff schedule alone.
#
# OPERATIONAL SAFEGUARDS (2026-07-29/30) -- WHY THESE WERE ADDED, AND WHY
# RUN 3'S 365-MINUTE DURATION IS NOT TREATED AS PROOF OF AN UNBOUNDED HANG:
#
# Before adding anything, the worst-case duration of the EXISTING (unmodified
# in this pass) code was computed directly from its own retry/timeout
# parameters, not assumed:
#   - GST leg (this script's scoped backoff): TrendReq's own timeout=(30,60)
#     means each of the 5 attempts can legitimately take up to 90s before
#     erroring, THEN sleep up to backoff+jitter (28/48/78/108/138s for
#     attempts 1-5). Fully-adversarial worst case: sum(90+28, 90+48, 90+78,
#     90+108, 90+138) = 850s (14.2 min) per ticker. This is a bounded,
#     documented ceiling -- not infinite -- but it is NOT smaller than the
#     old flat-60s schedule's own worst case (750s) once the request-timeout
#     dimension is included on every attempt; the new schedule's advantage
#     (shown in runs 1-2) is in the realistic/common case, not this
#     pathological bound.
#   - Wikipedia leg (GST_Wikipedia_Pageviews_Pull.py, NOT modified here):
#     _fetch_chunk() retries 429/404 up to 4 attempts (10/20/30s waits,
#     ~30s timeout each -> up to 180s per chunk call), and
#     _fetch_with_bisection() recurses down to MIN_BISECT_DAYS=45 on
#     failure. For this script's single 300-day pull, the bisection tree
#     (300 -> 150 -> 75 -> ~37, stopping once span<=45) makes up to
#     1+2+4+8 = 15 chunk calls if every one fails -- 15 x 180s = 2700s
#     (45 MINUTES) worst case for a single ticker's Wikipedia leg alone.
#     This was already true before today, unrelated to the GST backoff
#     change, and is large enough on its own to matter.
#   - yfinance 1.5.1 (installed version, verified by reading its actual
#     source, not assumed): yfinance/data.py's _make_request() defaults to
#     timeout=30 per underlying HTTP call and YfConfig.network.retries
#     defaults to 0 (so no internal retry-multiplication) -- calls ARE
#     already bounded by yfinance's own defaults, contrary to an initial
#     assumption that they had no timeout at all. A single high-level call
#     (history/options/option_chain/get_earnings_dates) makes 1-3 such
#     underlying requests, so a generous per-call ceiling is ~90-180s, not
#     unbounded.
#   - Summing a fully-adversarial per-ticker worst case (GST 850s + Wiki
#     2700s + ~270s for earnings/price/IV) x 24 tickers = ~1528 minutes
#     (~25.5 hours) as the theoretical ceiling. The observed 365-minute
#     run-3 duration is only ~24% of that ceiling -- comfortably explainable
#     by a handful of tickers hitting worse-than-typical (but still fully
#     bounded, already-documented) retry/bisection paths, especially via
#     the Wikipedia leg's own pre-existing 45-min/ticker ceiling. An
#     unbounded hang is NOT required to explain the observed duration, and
#     is not assumed here.
#
# What was actually added, given that finding (none of it touches the six
# field definitions, the 24-ticker universe, any z-score methodology, or
# the option-contract-selection rule):
#   - Line-buffered, flushed stdout (see log() and sys.stdout.reconfigure
#     below) so a redirected log file updates while the process runs,
#     instead of only at exit.
#   - Explicit START/DONE logging for every source leg, every ticker.
#   - A bounded-call wrapper (run_bounded(), using a daemon threading.Thread
#     + join(timeout=...) -- NOT concurrent.futures.ThreadPoolExecutor, see
#     run_bounded()'s own docstring for the atexit-hang bug that choice was
#     changed to avoid) applied to every network-touching leg (earnings,
#     price history, IV/options, GST, Wikipedia). This does not rely on any
#     library's own timeout= parameter being honored -- it bounds the
#     CALLING code's wait regardless of what the callee does internally,
#     and is proven to work by injecting a deliberately slow call before
#     ever trusting it (see
#     "SAFEGUARD TEST HOOK" below and CHANGELOG.md for the test run).
#   - An explicit, documented cumulative time budget for the GST leg
#     (GST_TICKER_BUDGET_S) and the Wikipedia leg (WIKI_TICKER_BUDGET_S)
#     per ticker, on top of (not replacing) their own existing per-attempt
#     timeouts and retry/bisection limits.
#   - A per-ticker wall-clock budget and a total-run wall-clock budget.
#     Exceeding either preserves the checkpoint written so far, records
#     which ticker/leg was active, and exits nonzero -- it does not retry
#     or restart.
#   - An atomic (write-temp-then-replace) checkpoint file written after
#     every ticker, under a filename that cannot be confused with a
#     finished panel, plus a final completion marker (JSON) stating
#     COMPLETE or PARTIAL with row/field/timing/failure counts.
#   - Any exception for one ticker is caught at the ticker-loop level (in
#     addition to the existing per-leg try/excepts inside process_ticker())
#     so it cannot destroy already-collected rows for other tickers.
#
# Output: Live Signal Engine/GST_Phase2_DailyPanel_TestRun_<run-date>.csv

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
import json
import os
import random
import sys
import threading
import time
import traceback
import pandas as pd
import requests
import yfinance as yf
from pytrends.request import TrendReq

# Line-buffered AND explicitly flushed (belt-and-suspenders): reconfigure()
# alone would leave stdout fully block-buffered when redirected to a file
# (the default for a non-TTY), which is exactly what produced an empty
# phase2_run3.log despite the process running for hours on 2026-07-27 --
# whatever ended that process never triggered a buffer flush. line_buffering
# flushes on every '\n'; log() below also passes flush=True explicitly so
# behavior doesn't silently depend on this reconfigure() call succeeding.
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.insert(0, str(Path(__file__).parent))

from GST_Live_Signal_Engine import (
    compute_latest_zscore, fetch_days_to_next_earnings,
    GEO as GST_GEO, GPROP as GST_GPROP, CATEGORY as GST_CATEGORY,
)
import GST_FixedWindow_PerEvent_Canonical as canonical
from GST_Wikipedia_Pageviews_Pull import TICKER_TO_WIKI_ARTICLE, to_weekly
import GST_Phase2_Wikipedia_Transport as wiki_transport
from GST_MultiTicker_Forward_Log import get_option_snapshot, get_nearest_post_earnings_expiry


def log(msg: str) -> None:
    print(msg, flush=True)


# Confirmed 24-ticker Phase 2 universe, spec Section 2 (2026-07-26 feasibility decision).
# UNCHANGED by this task.
TICKERS = [
    "AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
    "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
    "SYK", "TSLA", "TTWO", "UAL",
]

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)
RUN_DATE = datetime.now(timezone.utc).date()
FINAL_OUT_PATH = OUT_DIR / f"GST_Phase2_DailyPanel_TestRun_{RUN_DATE.isoformat()}_run3.csv"
# Deliberately distinct from FINAL_OUT_PATH's naming pattern (extra, redundant
# "_CHECKPOINT_PARTIAL" tag) so a partial file can never be mistaken for a
# completed panel -- this filename is never renamed/promoted into
# FINAL_OUT_PATH; a fresh write to FINAL_OUT_PATH only happens on full,
# clean 24/24 completion.
CHECKPOINT_PATH = OUT_DIR / f"GST_Phase2_DailyPanel_TestRun_{RUN_DATE.isoformat()}_run3_CHECKPOINT_PARTIAL.csv"
COMPLETION_MARKER_PATH = OUT_DIR / f"GST_Phase2_DailyPanel_TestRun_{RUN_DATE.isoformat()}_run3_COMPLETION_MARKER.json"

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

# See "SCOPED 429-BACKOFF FIX" note in the header for the rationale.
GST_MAX_ATTEMPTS = 5   # unchanged from GST_Live_Signal_Engine.fetch_ticker_series, for a fair run-3 comparison
GST_BACKOFF_429_S = [20, 40, 70, 100, 130]   # escalating; shorter first try than the original flat 60s
GST_BACKOFF_JITTER_S = 8.0   # +0-8s randomized on top of each scheduled value, desynchronizes retries

# --- OPERATIONAL SAFEGUARD BUDGETS (2026-07-29/30) -- see header note for the
# worst-case arithmetic that justifies each number. ---
# GST_TICKER_BUDGET_S: comfortably above the realistic (fast-429-response)
# full-backoff ceiling (400s), well below the fully-adversarial one (850s) --
# a hard, documented cap so the GST leg cannot run open-ended.
GST_TICKER_BUDGET_S = 480.0
# GST_ATTEMPT_TIMEOUT_S: outer bound on a SINGLE GST fetch attempt (the
# pt.build_payload()/interest_over_time() pair). TrendReq's own
# timeout=(30,60) already bounds this at ~90s; this is an independent,
# verified-by-injection backstop in case that assumption is ever wrong, same
# reasoning as YF_CALL_TIMEOUT_S below.
GST_ATTEMPT_TIMEOUT_S = 100.0
# WIKIPEDIA LEG (2026-07-31 REWRITE): no longer goes through run_bounded()/
# WIKI_TICKER_BUDGET_S at all -- see GST_Phase2_Wikipedia_Transport.py.
# That module replaces the old recursive-bisection design (root-caused in
# Live Signal Engine/Phase2 Failure Evidence/2026-07-30_AMZN_Wikipedia_180s/)
# with deterministic calendar-month chunks, a persistent cross-run cache,
# genuinely killable subprocess isolation per chunk (wiki_transport.CHUNK_TIMEOUT_S,
# proven by a real terminated-process test, unlike the daemon-thread wrapper
# still used below for the other legs), and a single bounded second pass
# over failed chunks run once at the RUN level after all 24 tickers'
# first-pass attempts, not per-ticker and not inline. A ticker whose
# Wikipedia chunks aren't all resolved after the second pass is left
# incomplete -- see main()'s WIKIPEDIA SECOND PASS section -- but this does
# NOT abort the run; other tickers are unaffected, matching the RUN-LEVEL
# FAILURE POLICY this rewrite implements for the Wikipedia leg specifically.
# YF_CALL_TIMEOUT_S: outer bound per individual yfinance call (history,
# options property, option_chain, get_earnings_dates). yfinance 1.5.1's own
# internal default (timeout=30, retries=0, verified by reading its installed
# source -- see header note) already bounds most of these; this wrapper is a
# verified-independent-of-that-assumption backstop, proven via the injected
# slow-call test rather than trusted blindly.
YF_CALL_TIMEOUT_S = 45.0
# PER_TICKER_WALL_BUDGET_S: backstop for the ENTIRE process_ticker() call.
# Set comfortably above the sum of all individual leg budgets above
# (45+45+90+480+90 = 750s) so it never fires ahead of an expected worst-case
# combination of per-leg budgets -- it exists to catch anything unexpected
# slipping past them, not to be the normally-binding constraint.
PER_TICKER_WALL_BUDGET_S = 900.0
# TOTAL_RUN_BUDGET_S: hard outer limit for the whole run, matching the
# "45-minute" bound this task specifies. Checked between tickers (not
# preemptively mid-ticker); on exhaustion the checkpoint already written is
# preserved, the active ticker is recorded, and the process exits nonzero
# without restarting.
TOTAL_RUN_BUDGET_S = 45 * 60.0

# --- SAFEGUARD TEST HOOK (2026-07-30) -- deliberately mocked/injected slow
# call, used ONLY to prove run_bounded()/budgets/checkpointing actually work
# before trusting them on a real run. Inert unless both env vars are set;
# never touches real research legs' logic, only adds an artificial delay
# ahead of the named leg for the named ticker. See CHANGELOG.md for the test
# run this was used for. ---
_INJECT_TICKER = os.environ.get("GST_PHASE2_INJECT_SLOW_TICKER")
_INJECT_LEG = os.environ.get("GST_PHASE2_INJECT_SLOW_LEG")
_INJECT_SLEEP_S = float(os.environ.get("GST_PHASE2_INJECT_SLOW_SECONDS", "9999"))


def _maybe_inject_slow(ticker: str, leg: str) -> None:
    if _INJECT_TICKER and _INJECT_LEG and ticker == _INJECT_TICKER and leg == _INJECT_LEG:
        log(f"    [TEST HOOK] injecting {_INJECT_SLEEP_S:.0f}s artificial delay into "
            f"{ticker}/{leg} (GST_PHASE2_INJECT_SLOW_* env vars set)")
        time.sleep(_INJECT_SLEEP_S)


def run_bounded(fn, timeout_s: float, *args, **kwargs):
    """Runs fn(*args, **kwargs) in a worker thread and waits at most timeout_s.
    Returns (result, timed_out, elapsed_s, error_str). Does NOT rely on fn (or
    any library it calls) honoring its own timeout= parameter -- this bounds
    the CALLER's wait regardless of what the callee does internally.

    Uses a plain daemon threading.Thread, NOT concurrent.futures.ThreadPoolExecutor
    -- confirmed by testing (see CHANGELOG.md), not assumed: an earlier version
    used ThreadPoolExecutor, which returned promptly from THIS function on a
    timeout, but the concurrent.futures.thread module registers a process-wide
    atexit hook that joins every worker thread any ThreadPoolExecutor ever
    created, including abandoned ones -- so the process itself would hang at
    exit waiting for a genuinely-stuck call, exactly the failure mode this
    whole safeguard exists to prevent. A daemon thread is never joined at
    interpreter exit (documented Python behavior), so it can be abandoned for
    real with no such hang. Python still cannot forcibly kill a thread
    mid-syscall -- an abandoned thread keeps running in the background until
    it happens to return, but it can no longer block this process from
    exiting."""
    result_box: dict = {}

    def _runner():
        try:
            result_box["result"] = fn(*args, **kwargs)
        except Exception as e:
            result_box["error"] = str(e)

    t0 = time.time()
    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)
    elapsed = time.time() - t0
    if thread.is_alive():
        return None, True, elapsed, f"timed out after {timeout_s:.0f}s"
    if "error" in result_box:
        return None, False, elapsed, result_box["error"]
    return result_box.get("result"), False, elapsed, None


def _bounded_leg(fn, timeout_s: float, ticker: str, leg: str, *args, **kwargs):
    """run_bounded() wrapper that runs the SAFEGUARD TEST HOOK injection
    INSIDE the bounded thread -- injecting the delay outside run_bounded's
    call would hang the calling thread itself with no timeout protection at
    all, defeating the point of the test. This is the call path every leg
    that touches the network should use."""
    def _wrapped():
        _maybe_inject_slow(ticker, leg)
        return fn(*args, **kwargs)
    return run_bounded(_wrapped, timeout_s)


def fetch_ticker_series_scoped_backoff(pt: TrendReq, term: str) -> tuple[pd.DataFrame, dict]:
    """Same pytrends query/reshape as GST_Live_Signal_Engine.fetch_ticker_series() --
    only the 429 retry schedule differs. See "SCOPED 429-BACKOFF FIX" in the
    module header for why this script has its own copy of this one function.

    UPDATE (2026-07-30): also enforces GST_TICKER_BUDGET_S as a cumulative
    cap and returns a status dict (attempts, rate_limit_events,
    budget_exhausted) alongside the series -- see "OPERATIONAL SAFEGUARDS"
    in the module header."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=PULL_LOOKBACK_DAYS)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"

    budget_start = time.time()
    rate_limit_events = 0
    attempts_used = 0
    budget_exhausted = False

    def _do_request():
        pt.build_payload([term], timeframe=timeframe, geo=GST_GEO, gprop=GST_GPROP, cat=GST_CATEGORY)
        df = pt.interest_over_time()
        if df is None or df.empty or term not in df.columns:
            raise RuntimeError("Empty result or missing term column")
        return pd.DataFrame({
            "Week": df.index,
            "gst": pd.to_numeric(df[term], errors="coerce"),
            "isPartial": df["isPartial"].astype(bool),
        }).sort_values("Week").reset_index(drop=True)

    for attempt in range(1, GST_MAX_ATTEMPTS + 1):
        attempts_used = attempt
        if time.time() - budget_start >= GST_TICKER_BUDGET_S:
            budget_exhausted = True
            log(f"    [{term}] GST cumulative budget ({GST_TICKER_BUDGET_S:.0f}s) exhausted "
                f"before attempt {attempt} -- stopping retries for this ticker.")
            break
        # Routed through _bounded_leg (not a bare call) so a single hung
        # attempt cannot itself run open-ended, independent of whatever
        # TrendReq's own timeout=(30,60) does -- verified via the injected
        # slow-call test, not assumed. leg="gst" is what the SAFEGUARD TEST
        # HOOK matches on for this leg.
        out, timed_out, elapsed, err = _bounded_leg(_do_request, GST_ATTEMPT_TIMEOUT_S, term, "gst")
        if not timed_out and err is None:
            return out, {
                "attempts": attempts_used, "rate_limit_events": rate_limit_events,
                "budget_exhausted": False, "status": "ok",
            }
        e = f"timed out after {GST_ATTEMPT_TIMEOUT_S:.0f}s" if timed_out else err
        msg = str(e).lower()
        is_429 = "429" in msg or ("rate" in msg and "limit" in msg) or "too many" in msg
        if is_429:
            rate_limit_events += 1
            base = GST_BACKOFF_429_S[min(attempt - 1, len(GST_BACKOFF_429_S) - 1)]
            pause = base + random.uniform(0, GST_BACKOFF_JITTER_S)
        else:
            pause = min(6, 2 * attempt) + random.uniform(0, 0.5)
        remaining_budget = GST_TICKER_BUDGET_S - (time.time() - budget_start)
        if remaining_budget <= 0:
            budget_exhausted = True
            log(f"    [{term}] attempt {attempt} failed: {e} -- GST budget exhausted, not sleeping further.")
            break
        pause = min(pause, remaining_budget)
        log(f"    [{term}] attempt {attempt} failed: {e} -- sleeping {pause:.1f}s "
            f"(budget remaining after: {remaining_budget - pause:.0f}s)")
        time.sleep(pause)

    status = "budget_exhausted" if budget_exhausted else "attempts_exhausted"
    return pd.DataFrame(columns=["Week", "gst", "isPartial"]), {
        "attempts": attempts_used, "rate_limit_events": rate_limit_events,
        "budget_exhausted": budget_exhausted, "status": status,
    }


# Fixed, explicit output column order -- same discipline as
# GST_MultiTicker_Forward_Log.py's COLUMN_ORDER (see that repo's
# CHANGELOG.md "column-corruption bug" entry). Every row is pre-filled with
# these keys (None default) so pandas' column order never depends on which
# ticker happens to hit which error/leg first. The six locked research
# fields (gst_zscore, wiki_zscore, implied_volatility, realized_vol, price,
# volume) and days_to_nearest_earnings keep their existing names/meanings,
# unchanged -- everything with a _status/_error/_elapsed_s suffix is new
# observability added by this task, additive only.
COLUMN_ORDER = [
    "run_date", "ticker", "retrieval_timestamp_utc",
    "days_to_nearest_earnings",
    "earnings_status", "earnings_error", "earnings_elapsed_s",
    "price", "volume", "price_asof_date",
    "price_history_status", "price_history_error", "price_history_elapsed_s",
    "realized_vol",
    "realized_vol_status", "realized_vol_error", "realized_vol_elapsed_s",
    "option_expiry", "implied_volatility", "iv_note",
    "call_strike", "call_bid", "call_ask", "call_bid_size", "call_ask_size",
    "call_open_interest", "call_volume", "call_implied_volatility",
    "put_strike", "put_bid", "put_ask", "put_bid_size", "put_ask_size",
    "put_open_interest", "put_volume", "put_implied_volatility",
    "iv_status", "iv_error", "iv_elapsed_s",
    "gst_zscore", "gst_value", "gst_week", "gst_is_partial_week", "gst_note",
    "gst_status", "gst_error", "gst_elapsed_s",
    "gst_retry_count", "gst_rate_limit_events", "gst_budget_exhausted",
    "wikipedia_article", "wiki_zscore", "wiki_aligned_week", "wiki_note",
    "wiki_status", "wiki_error", "wiki_elapsed_s",
    # RECENT_LAST_KNOWN_GOOD fallback provenance (2026-07-31, approved as a
    # narrow addition -- see GST_Phase2_Wikipedia_Transport.evaluate_recent_cache_fallback).
    # All None/False on a normal fresh-success or plain-incomplete row;
    # populated only when the current/open month's chunk is served from a
    # verified recent cached snapshot instead of a fresh fetch.
    "wiki_source_mode", "wiki_fresh_request_failed", "wiki_fresh_failure_category",
    "wiki_fresh_failure_http_status", "wiki_fallback_retrieved_at_utc",
    "wiki_cache_age_hours", "wiki_effective_data_end", "wiki_cache_content_hash",
    # MEASURED WIKIPEDIA DATA WATERMARK provenance (2026-08-01 -- see
    # GST_Phase2_Wikipedia_Transport.resolve_wiki_data_watermark()). RUN-LEVEL:
    # resolved exactly once per run, before any ticker is processed, and
    # identical across all 24 rows -- not recomputed per ticker. Establishes
    # exactly what Wikipedia data was measured as available at the retrieval
    # timestamp; NOT a waiver or a stale-data workaround. A row may be
    # wiki-complete with lag 1-3 only when every required per-article date
    # through wiki_data_watermark_date is present and validated -- the
    # recorded lag remains visible here for later modeling/quality controls.
    "wiki_data_watermark_date", "wiki_data_lag_days", "wiki_watermark_status",
    "wiki_watermark_retrieved_at_utc", "wiki_watermark_source_url",
    "wiki_watermark_http_status", "wiki_required_data_end",
    # EFFECTIVE PANEL WATERMARK provenance (2026-08-05 -- see
    # GST_Phase2_Wikipedia_Transport.resolve_effective_panel_watermark()).
    # ADDITIVE: the aggregate-watermark fields above are unchanged and
    # retained as a source-health observation. What changed is which date
    # BINDS: the aggregate endpoint answers "did en.wikipedia.org publish
    # day D site-wide?", never "did THIS article publish day D?", and the
    # 2026-08-05 PARTIAL proved the two diverge (aggregate said 2026-08-04;
    # only 5 of 24 articles had it). The binding date is now the MINIMUM of
    # the 24 validated per-article latest-available dates, identical on
    # every row of a run -- it is the date every article has demonstrably
    # published, so requiring exact coverage through it asks nothing the
    # source has not already delivered.
    #   wiki_article_latest_available_date is this ticker's OWN measured
    # latest date (per-row, for auditability -- it is NOT what anchors this
    # row's z-score; wiki_effective_panel_watermark_date is).
    #   wiki_aggregate_vs_panel_lag_days = aggregate - effective, in days.
    # Positive means the panel is behind the site-wide aggregate, i.e. at
    # least one article had not yet caught up. Negative would mean an
    # article is ahead of the aggregate -- a source-health anomaly worth
    # seeing, recorded rather than clamped.
    # This addresses TRAILING publication lag only. Exact coverage across
    # the complete required lookback is still required of every ticker; an
    # internal historical gap sits below this watermark and still produces
    # PARTIAL.
    "wiki_aggregate_watermark_date", "wiki_article_latest_available_date",
    "wiki_effective_panel_watermark_date", "wiki_effective_watermark_method",
    "wiki_aggregate_vs_panel_lag_days",
    # Z-SCORE ANCHOR provenance (2026-08-02 correction -- see
    # _finalize_wiki_row()). The anchor passed to compute_zscore_at_anchor()
    # must be the measured watermark date, never the script's real
    # wall-clock run date -- see CHANGELOG.md 2026-08-02 entry for the bug
    # this fixes (a 1-day mismatch pushed 16/24 tickers past the existing
    # 6-day alignment tolerance). wiki_zscore_anchor_date always equals
    # wiki_data_watermark_date on a finalized row; wiki_zscore_anchor_source
    # records how the anchor was derived ("measured_watermark" is currently
    # the only value -- present for forward compatibility/auditability, not
    # because alternate sources exist today).
    "wiki_zscore_anchor_date", "wiki_zscore_anchor_source",
    # WIKI SOURCE PROVENANCE (2026-08-02 additive correction -- see
    # _wiki_source_provenance()). wiki_source_mode is now DERIVED from the
    # chunks that actually contributed rows, never hardcoded: one of
    # "fresh_only", "exact_cache_only", "cache_union_only",
    # "subchunk_salvage_only" (2026-08-03 addition), "mixed", or
    # (via the existing recent_last_known_good override, applied after
    # this derivation, unchanged) "recent_last_known_good". The *_json
    # fields use deterministic, sort_keys=True JSON so identical underlying
    # provenance always serializes identically.
    "wiki_cache_union_used", "wiki_cache_union_chunk_count",
    "wiki_source_components_json", "wiki_cache_union_provenance_json",
    # BOUNDED CLOSED-MONTH SUBCHUNK RECOVERY provenance (2026-08-03 additive
    # correction -- see GST_Phase2_Wikipedia_Transport
    # .run_bounded_subchunk_recovery()). None/"[]" on every row where this
    # last-resort mechanism was never invoked (i.e. every row that didn't
    # still have a closed-month chunk failing after both the second pass
    # and the recent-cache fallback). When invoked, carries the full
    # per-subchunk provenance record (original failed interval, subchunk
    # boundaries, response status, elapsed time, content hashes, retrieval
    # timestamps, expected/observed date counts, and budgets consumed) --
    # whether or not the recovery attempt ultimately succeeded, so a
    # rejected/incomplete attempt is exactly as auditable as a successful
    # one.
    "wiki_subchunk_recovery_attempted", "wiki_subchunk_recovery_provenance_json",
    "all_six_fields_clean", "ticker_total_s",
]


def process_ticker(pt: TrendReq, ticker: str, run_ts: datetime,
                    wiki_remaining_budget_s: float | None = None,
                    watermark_info: dict | None = None,
                    effective_info: dict | None = None) -> tuple[dict, dict | None]:
    row = {c: None for c in COLUMN_ORDER}
    row["run_date"] = RUN_DATE.isoformat()
    row["ticker"] = ticker
    row["retrieval_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    t_ticker_start = time.time()

    # --- days to nearest (next) earnings -- MUST run before any yfinance
    # history/options call for this ticker. See ORDERING CONSTRAINT above.
    log(f"  [{ticker}] START earnings")
    t0 = time.time()
    days_to_earnings, timed_out, elapsed, err = _bounded_leg(
        fetch_days_to_next_earnings, YF_CALL_TIMEOUT_S, ticker, "earnings", ticker)
    row["earnings_elapsed_s"] = round(elapsed, 3)
    if timed_out:
        row["earnings_status"] = "timeout"
        row["earnings_error"] = err
        days_to_earnings = None
    elif err is not None:
        row["earnings_status"] = "error"
        row["earnings_error"] = err
        days_to_earnings = None
    else:
        row["earnings_status"] = "ok"
    row["days_to_nearest_earnings"] = days_to_earnings
    log(f"  [{ticker}] DONE  earnings  status={row['earnings_status']} "
        f"elapsed={elapsed:.2f}s value={days_to_earnings}")

    tk = yf.Ticker(ticker, session=YF_SESSION)

    # --- price history (feeds both price/volume and realized vol) ---
    log(f"  [{ticker}] START price_history")
    hist, timed_out, elapsed, err = _bounded_leg(
        lambda: tk.history(period=PRICE_HISTORY_PERIOD), YF_CALL_TIMEOUT_S, ticker, "price_history")
    row["price_history_elapsed_s"] = round(elapsed, 3)
    if timed_out:
        row["price_history_status"] = "timeout"
        row["price_history_error"] = err
        hist = pd.DataFrame()
    elif err is not None:
        row["price_history_status"] = "error"
        row["price_history_error"] = err
        hist = pd.DataFrame()
    else:
        row["price_history_status"] = "ok"
        if hist is None:
            hist = pd.DataFrame()
    log(f"  [{ticker}] DONE  price_history  status={row['price_history_status']} "
        f"elapsed={elapsed:.2f}s rows={len(hist)}")

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
    # Pure in-memory computation on the already-fetched `hist` -- no network
    # call, so no run_bounded()/status beyond ok-or-exception is needed, but
    # the same status/error/elapsed columns are still populated for a
    # consistent per-leg shape across the output.
    log(f"  [{ticker}] START realized_vol")
    t0 = time.time()
    realized_vol = None
    try:
        if not hist.empty:
            idx = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
            ret_col = f"{ticker} Daily Return"
            daily = pd.DataFrame({"Date": idx, ret_col: hist["Close"].pct_change().to_numpy()})
            cutoff = pd.Timestamp(run_ts.date())
            realized_vol = canonical.trailing_realized_vol(daily, ret_col, cutoff)
        row["realized_vol_status"] = "ok"
    except Exception as e:
        row["realized_vol_status"] = "error"
        row["realized_vol_error"] = str(e)
    row["realized_vol"] = realized_vol
    row["realized_vol_elapsed_s"] = round(time.time() - t0, 3)
    log(f"  [{ticker}] DONE  realized_vol  status={row['realized_vol_status']} "
        f"elapsed={row['realized_vol_elapsed_s']:.2f}s value={realized_vol}")

    # --- implied volatility: unconditional option-chain pull (the untested leg) ---
    log(f"  [{ticker}] START iv")
    t0 = time.time()
    expiry, timed_out, elapsed_expiry, err_expiry = _bounded_leg(
        get_nearest_post_earnings_expiry, YF_CALL_TIMEOUT_S, ticker, "iv", tk, run_ts.date())
    iv_status = "ok"
    iv_error = None
    if timed_out:
        iv_status, iv_error, expiry = "timeout", err_expiry, None
    elif err_expiry is not None:
        iv_status, iv_error, expiry = "error", err_expiry, None

    if expiry and price and iv_status == "ok":
        row["option_expiry"] = expiry
        snap, timed_out2, elapsed_snap, err_snap = _bounded_leg(
            get_option_snapshot, YF_CALL_TIMEOUT_S, ticker, "iv", tk, expiry, price)
        if timed_out2:
            iv_status, iv_error, snap = "timeout", err_snap, {}
        elif err_snap is not None:
            iv_status, iv_error, snap = "error", err_snap, {}
        else:
            snap = snap or {}
        row.update({k: v for k, v in snap.items() if k in COLUMN_ORDER})
        ivs = [v for v in (snap.get("call_implied_volatility"), snap.get("put_implied_volatility"))
               if v is not None]
        row["implied_volatility"] = round(sum(ivs) / len(ivs), 6) if ivs else None
        if not ivs and iv_status == "ok":
            row["iv_note"] = "option chain returned but no impliedVolatility on ATM call/put"
    elif iv_status == "ok":
        row["implied_volatility"] = None
        row["iv_note"] = "no expiration strictly after today available" if not expiry else "no spot price to select ATM strike"
    row["iv_status"] = iv_status
    row["iv_error"] = iv_error
    row["iv_elapsed_s"] = round(time.time() - t0, 3)
    log(f"  [{ticker}] DONE  iv  status={iv_status} elapsed={row['iv_elapsed_s']:.2f}s "
        f"iv={row['implied_volatility']}")

    # --- GST z-score: scoped-backoff query (see header note) + live-engine's z-score func ---
    log(f"  [{ticker}] START gst")
    t0 = time.time()
    try:
        series, gst_status_dict = fetch_ticker_series_scoped_backoff(pt, ticker)
        row["gst_retry_count"] = gst_status_dict["attempts"]
        row["gst_rate_limit_events"] = gst_status_dict["rate_limit_events"]
        row["gst_budget_exhausted"] = gst_status_dict["budget_exhausted"]
        if gst_status_dict["status"] == "ok":
            z = compute_latest_zscore(series)
            row["gst_zscore"] = z.get("zscore")
            row["gst_value"] = z.get("gst_value")
            row["gst_week"] = z.get("week")
            row["gst_is_partial_week"] = z.get("is_partial_week")
            row["gst_note"] = z.get("note", "")
            row["gst_status"] = "ok"
        else:
            row["gst_status"] = gst_status_dict["status"]   # "attempts_exhausted" or "budget_exhausted"
            row["gst_error"] = f"gst_fetch_failed:{gst_status_dict['status']}"
    except Exception as e:
        row["gst_status"] = "error"
        row["gst_error"] = str(e)
    row["gst_elapsed_s"] = round(time.time() - t0, 3)
    log(f"  [{ticker}] DONE  gst  status={row['gst_status']} elapsed={row['gst_elapsed_s']:.2f}s "
        f"retries={row['gst_retry_count']} rate_limit_events={row['gst_rate_limit_events']} "
        f"z={row.get('gst_zscore')}")

    # --- Wikipedia pageview z-score (2026-08-01 WATERMARK CORRECTION, see
    # header note): deterministic calendar-month chunks + persistent cache
    # + killable subprocess isolation, one bounded first-pass attempt per
    # chunk, all bounded by the SINGLE frozen run-level Wikipedia data
    # watermark resolved once in main() before any ticker was processed
    # (GST_Phase2_Wikipedia_Transport.resolve_wiki_data_watermark()) -- NOT
    # a fixed today-1 assumption, which was proven wrong by the 2026-08-01
    # PARTIAL regression (Wikipedia had not yet published the prior day's
    # data for ANY article). A chunk that fails here is queued for the
    # RUN-LEVEL second pass in main() -- it does NOT retry inline and does
    # NOT abort this ticker or the run. compute_latest_zscore/to_weekly/
    # compute_zscore_at_anchor are UNCHANGED -- only how the daily series
    # is gathered, and how much of it is expected, changed. ---
    log(f"  [{ticker}] START wiki")
    t0 = time.time()
    wiki_pending = None
    article = TICKER_TO_WIKI_ARTICLE.get(ticker)

    # Watermark provenance is RUN-LEVEL -- identical on every row,
    # regardless of whether this ticker's own wiki leg succeeds.
    watermark_info = watermark_info or {}
    effective_info = effective_info or {}
    row["wiki_data_watermark_date"] = (
        watermark_info["watermark_date"].isoformat() if watermark_info.get("watermark_date") else None)
    row["wiki_data_lag_days"] = watermark_info.get("lag_days")
    row["wiki_watermark_status"] = watermark_info.get("status")
    row["wiki_watermark_retrieved_at_utc"] = watermark_info.get("retrieved_at_utc")
    row["wiki_watermark_source_url"] = watermark_info.get("source_url")
    row["wiki_watermark_http_status"] = watermark_info.get("http_status")

    # --- EFFECTIVE PANEL WATERMARK provenance (2026-08-05). Also RUN-LEVEL
    # and identical on every row, EXCEPT wiki_article_latest_available_date,
    # which is this ticker's own measured value and is recorded purely for
    # auditability -- it never anchors anything. ---
    effective_watermark_date = effective_info.get("effective_panel_watermark_date")
    row["wiki_aggregate_watermark_date"] = (
        watermark_info["watermark_date"].isoformat() if watermark_info.get("watermark_date") else None)
    _article_latest = (effective_info.get("per_ticker_latest") or {}).get(ticker)
    row["wiki_article_latest_available_date"] = _article_latest.isoformat() if _article_latest else None
    row["wiki_effective_panel_watermark_date"] = (
        effective_watermark_date.isoformat() if effective_watermark_date else None)
    row["wiki_effective_watermark_method"] = effective_info.get("method")
    row["wiki_aggregate_vs_panel_lag_days"] = effective_info.get("aggregate_vs_panel_lag_days")

    if article is None:
        row["wiki_status"] = "error"
        row["wiki_error"] = "no verified Wikipedia article mapping for this ticker"
    elif watermark_info.get("status") != "ok":
        # Fail closed: without a valid measured watermark there is no
        # honest completeness bar to request or validate against -- never
        # guess one. No network request is made for this ticker's wiki leg
        # at all this run.
        row["wiki_status"] = "incomplete_watermark_unavailable"
        row["wiki_error"] = (f"no valid Wikipedia data watermark this run "
                              f"(status={watermark_info.get('status')!r}) -- wiki leg not attempted")
    elif effective_info.get("status") != "ok" or effective_watermark_date is None:
        # Fail closed, same discipline one level up (2026-08-05): a valid
        # AGGREGATE watermark is not on its own proof that every article
        # has published that date. Without a complete set of 24 validated
        # per-article measurements there is no honest shared completeness
        # bar, and the aggregate watermark must NOT be substituted for one.
        # No network request is made for this ticker's wiki leg this run.
        row["wiki_status"] = "incomplete_effective_watermark_unavailable"
        row["wiki_error"] = (f"no valid effective panel watermark this run "
                              f"(status={effective_info.get('status')!r}, "
                              f"measured={effective_info.get('measured_count')}/"
                              f"{effective_info.get('expected_count')}) -- wiki leg not attempted")
    else:
        # THE BINDING WATERMARK (2026-08-05): the effective panel watermark,
        # not the aggregate one. Identical for all 24 tickers this run, so
        # pull_start, expected coverage and the z-score anchor below are the
        # same date for every row -- never ticker-specific.
        watermark_date = effective_watermark_date
        anchor_date = run_ts.date()
        # 2026-08-02 correction: pull_start is derived from watermark_date,
        # not wall-clock anchor_date. The observation window's actual
        # right edge is the measured watermark (data beyond it is never
        # observable), so anchoring the LEFT edge on wall-clock time
        # instead shortens the effective lookback by exactly the
        # watermark's lag whenever it lags anchor_date -- the same class
        # of wall-clock-vs-watermark bug already fixed for the z-score
        # anchor itself. The request horizon/end-date passed to the
        # transport (anchor_date below) is deliberately left unchanged --
        # get_ticker_wikipedia_daily()/required_data_end() already
        # truncate any chunk beyond the watermark, so widening the
        # generated-chunk horizon to wall-clock time is harmless and
        # out of scope for this fix.
        pull_start = watermark_date - timedelta(days=PULL_LOOKBACK_DAYS)
        row["wiki_required_data_end"] = watermark_date.isoformat()
        try:
            cache_df = wiki_transport.load_cache()
        except wiki_transport.CacheCorruptionError as e:
            log(f"  [{ticker}] Wikipedia cache corruption detected, treating as empty cache this run: {e}")
            cache_df = pd.DataFrame(columns=wiki_transport.CACHE_COLUMNS)
        wiki_result = wiki_transport.get_ticker_wikipedia_daily(
            ticker, article, pull_start, anchor_date, watermark_date, cache_df=cache_df,
            remaining_budget_s=wiki_remaining_budget_s,
        )
        for cr in wiki_result["chunk_results"]:
            log(f"    [{ticker}] wiki chunk {cr['chunk_start']}..{cr['chunk_end']} "
                f"source={cr['source']} status={cr['status']} "
                f"http_status={cr.get('http_status')} retry_after={cr.get('retry_after')} "
                f"network={cr.get('network_elapsed_s', 0.0):.2f}s sleep={cr.get('sleep_s', 0.0):.2f}s")
        if wiki_result["failed_chunks"]:
            row["wiki_status"] = "pending_second_pass"
            row["wiki_error"] = (f"{len(wiki_result['failed_chunks'])} of "
                                  f"{len(wiki_result['chunk_results'])} chunk(s) failed first pass -- queued")
            wiki_pending = {
                "ticker": ticker, "article": article, "run_ts": run_ts,
                "daily_rows_so_far": wiki_result["daily_rows"],
                "failed_chunks": wiki_result["failed_chunks"],
                # 2026-08-02 additive correction: first-pass chunk_results
                # (including any successful cache/fetch/cache_union_
                # reconstruction chunks alongside the ones that failed and
                # are queued above) must survive into the second pass so
                # the ticker's FINAL source provenance -- computed after
                # second-pass recovery -- reflects every contributing
                # chunk, not just the ones recovered in second pass.
                "chunk_results": wiki_result["chunk_results"],
            }
        else:
            _finalize_wiki_row(row, article, wiki_result["daily_rows"], watermark_date, wiki_result["chunk_results"])
    row["wiki_elapsed_s"] = round(time.time() - t0, 3)
    log(f"  [{ticker}] DONE  wiki  status={row['wiki_status']} elapsed={row['wiki_elapsed_s']:.2f}s "
        f"z={row.get('wiki_zscore')}")

    row["ticker_total_s"] = round(time.time() - t_ticker_start, 3)

    # all_six_fields_clean covers ONLY the six locked research fields
    # (2026-08-01 correction). days_to_nearest_earnings is contextual
    # metadata, not one of the six -- a successful earnings lookup that
    # honestly finds no upcoming earnings date (earnings_status="ok",
    # days_to_nearest_earnings=None) must NOT make this False. Fail-closed
    # earnings handling is enforced separately by is_run_complete()
    # requiring earnings_status=="ok" for every row.
    six_fields = [row.get("gst_zscore"), row.get("wiki_zscore"), row.get("implied_volatility"),
                  row.get("realized_vol"), row.get("price"), row.get("volume")]
    row["all_six_fields_clean"] = all(v is not None for v in six_fields)

    return row, wiki_pending


def _wiki_source_provenance(chunk_results: list[dict]) -> dict:
    """Derives final wiki-leg source provenance from the chunks that
    ACTUALLY contributed rows -- never hardcoded (2026-08-02 correction:
    _finalize_wiki_row() previously wrote wiki_source_mode="fresh"
    unconditionally, which was simply false for a cache hit, a cache-union
    reconstruction, or any mix of the two).

    chunk_results is the FULL set of chunk attempts behind this ticker's
    finalized wiki_zscore: first-pass entries as returned by
    get_ticker_wikipedia_daily(), plus -- when a second-pass retry
    recovered a chunk that failed first pass -- one NORMALIZED entry per
    recovered chunk with source="fetch" added by the caller (second-pass
    chunk_results carry no "source" field of their own; second pass is
    always a live fetch, never a cache or union hit, by construction). A
    chunk that was never requested (no_observations_expected_yet) or that
    ultimately failed contributes nothing here.

    Returns the four additive COLUMN_ORDER fields as a dict:
      wiki_source_mode: "fresh_only" | "exact_cache_only" |
        "cache_union_only" | "subchunk_salvage_only" (2026-08-03 addition
        -- every contributing chunk recovered via the bounded closed-month
        subchunk mechanism, see GST_Phase2_Wikipedia_Transport
        .run_bounded_subchunk_recovery()) | "mixed" | None (only if
        literally no chunk contributed -- should not happen whenever
        wiki_zscore ends up non-None, but this function never invents a
        value to paper over that). The caller may still overwrite this
        afterward for the UNRELATED recent_last_known_good case (see
        main()'s second-pass loop) -- that override, and its own existing
        provenance, are untouched by this function.
      wiki_cache_union_used / wiki_cache_union_chunk_count: whether/how
        many chunks were recovered via cache_union_reconstruction.
      wiki_source_components_json / wiki_cache_union_provenance_json:
        deterministic JSON (sort_keys=True over already-sorted inputs) so
        identical underlying provenance always serializes identically."""
    ok_chunks = [cr for cr in chunk_results
                 if cr.get("status") == "ok"
                 and cr.get("source") in ("cache", "fetch", "cache_union_reconstruction", "subchunk_salvage")]
    sources_used = sorted({cr["source"] for cr in ok_chunks})

    if not sources_used:
        mode = None
    elif sources_used == ["fetch"]:
        mode = "fresh_only"
    elif sources_used == ["cache"]:
        mode = "exact_cache_only"
    elif sources_used == ["cache_union_reconstruction"]:
        mode = "cache_union_only"
    elif sources_used == ["subchunk_salvage"]:
        mode = "subchunk_salvage_only"
    else:
        mode = "mixed"

    union_chunks = [cr for cr in ok_chunks if cr["source"] == "cache_union_reconstruction"]
    union_provenance_list = [
        {
            "requested_chunk_start": cr.get("chunk_start"),
            "requested_chunk_end": cr.get("chunk_end"),
            **(cr.get("cache_union_provenance") or {}),
        }
        for cr in sorted(union_chunks, key=lambda c: (c.get("chunk_start") or "", c.get("chunk_end") or ""))
    ]

    return {
        "wiki_source_mode": mode,
        "wiki_cache_union_used": len(union_chunks) > 0,
        "wiki_cache_union_chunk_count": len(union_chunks),
        "wiki_source_components_json": json.dumps(sources_used, sort_keys=True),
        "wiki_cache_union_provenance_json": json.dumps(union_provenance_list, sort_keys=True),
    }


def _finalize_wiki_row(row: dict, article: str, daily_rows: list[dict], watermark_date: date,
                        chunk_results: list[dict]) -> None:
    """Assembles the daily series from whatever chunk rows are available
    (cache + first-pass + any second-pass recoveries) and computes the wiki
    z-score using the EXACT SAME unmodified functions as before this
    rewrite (to_weekly(), compute_zscore_at_anchor()) -- only how the daily
    rows were gathered changed, not the z-score methodology itself.

    2026-08-02 correction: the anchor passed to compute_zscore_at_anchor()
    is the measured run-level Wikipedia watermark date, NEVER the script's
    real wall-clock run date. Wikipedia data is truncated at the watermark
    (required_data_end = min(chunk_end, watermark)), so anchoring against
    "today" when today is genuinely ahead of the watermark manufactures a
    spurious gap between the anchor and the nearest available week --
    exactly what caused a systemic wiki_zscore=None across 16/24 tickers on
    2026-08-02 despite every one of their Wikipedia chunks resolving
    cleanly (see Live Signal Engine/Phase2 Failure Evidence/
    2026-08-02_WatermarkAnchor_And_Endpoint_PARTIAL/). Callers must pass the
    SAME watermark_date used to truncate this ticker's chunk fetching --
    this function has no wall-clock fallback and fails closed (raises) if
    watermark_date is missing, rather than silently substituting one.

    chunk_results (2026-08-02 additive correction): the chunk attempts
    behind `daily_rows`, REQUIRED (no default) -- this function no longer
    hardcodes wiki_source_mode="fresh"; see _wiki_source_provenance() for
    exactly how it is derived instead. Passing an accurate chunk_results
    list is the caller's responsibility (see process_ticker() and main()'s
    second-pass loop for the two production call sites).
    """
    if watermark_date is None:
        raise ValueError(
            "_finalize_wiki_row: watermark_date is required and must not be None -- "
            "the wiki z-score anchor must never fall back to a wall-clock date. "
            "Fail closed: do not call this function without a confirmed measured watermark."
        )
    # Defense in depth: no observation dated after the watermark may enter
    # the z-score, regardless of how daily_rows was assembled upstream.
    # Chunk-level truncation (required_data_end) already enforces this at
    # fetch time; this filter makes the invariant hold at the z-score
    # boundary itself, independent of the fetch path.
    daily_rows = [r for r in daily_rows
                  if datetime.strptime(str(r["date"]), "%Y%m%d").date() <= watermark_date]
    daily_df = wiki_transport.assemble_daily_series(daily_rows)
    weekly = to_weekly(daily_df)
    anchor = pd.Timestamp(watermark_date)
    aligned_week, wiki_z, note = canonical.compute_zscore_at_anchor(weekly, anchor)
    row["wikipedia_article"] = article
    row["wiki_zscore"] = round(wiki_z, 4) if wiki_z is not None else None
    row["wiki_aligned_week"] = aligned_week.date().isoformat() if aligned_week is not None else None
    row["wiki_note"] = note
    row["wiki_status"] = "ok"
    row["wiki_fresh_request_failed"] = False
    row["wiki_zscore_anchor_date"] = watermark_date.isoformat()
    row["wiki_zscore_anchor_source"] = "measured_watermark"
    row.update(_wiki_source_provenance(chunk_results))


def write_checkpoint(rows: list[dict]) -> None:
    """Atomic write: build the file under a temp name in the same directory,
    then os.replace() it over the checkpoint path -- os.replace is atomic on
    both POSIX and Windows, so a reader never sees a half-written file."""
    if not rows:
        return
    df = pd.DataFrame(rows, columns=COLUMN_ORDER)
    tmp_path = CHECKPOINT_PATH.with_suffix(".tmp")
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, CHECKPOINT_PATH)


def write_completion_marker(rows: list[dict], elapsed_s: float, status: str,
                             active_ticker: str | None = None, active_leg: str | None = None,
                             watermark_info: dict | None = None,
                             effective_info: dict | None = None) -> None:
    n_total = len(rows)
    n_clean = sum(1 for r in rows if r.get("all_six_fields_clean"))
    six_fields = ["gst_zscore", "wiki_zscore", "implied_volatility", "realized_vol", "price", "volume"]
    field_completeness = {
        f: (sum(1 for r in rows if r.get(f) is not None) / n_total if n_total else 0.0)
        for f in six_fields
    }
    failed_sources: dict[str, int] = {}
    for leg in ["earnings", "price_history", "realized_vol", "iv", "gst", "wiki"]:
        failed_sources[leg] = sum(1 for r in rows if r.get(f"{leg}_status") not in ("ok", None))

    # Additive observability (2026-08-01): distinguishes a genuinely
    # successful earnings lookup that honestly found no upcoming date
    # (earnings_lookup_ok_count high, days_to_nearest_earnings_nonnull_count
    # lower) from an actual lookup FAILURE (earnings_lookup_ok_count itself
    # lower) -- neither of these gates all_six_fields_clean_count, which
    # covers only the six locked research fields above.
    n_earnings_ok = sum(1 for r in rows if r.get("earnings_status") == "ok")
    n_earnings_date_nonnull = sum(1 for r in rows if r.get("days_to_nearest_earnings") is not None)

    marker = {
        "status": status,   # "COMPLETE" or "PARTIAL"
        "row_count": n_total,
        "unique_ticker_count": len(set(r["ticker"] for r in rows)),
        "expected_ticker_count": len(TICKERS),
        "all_six_fields_clean_count": n_clean,
        "earnings_lookup_ok_count": n_earnings_ok,
        "days_to_nearest_earnings_nonnull_count": n_earnings_date_nonnull,
        "field_completeness_pct": {f: round(v * 100, 2) for f, v in field_completeness.items()},
        "failed_source_counts": failed_sources,
        "elapsed_s": round(elapsed_s, 1),
        "elapsed_min": round(elapsed_s / 60, 2),
        "active_ticker_when_stopped": active_ticker,
        "active_leg_when_stopped": active_leg,
        "checkpoint_path": str(CHECKPOINT_PATH) if status == "PARTIAL" else None,
        "final_path": str(FINAL_OUT_PATH) if status == "COMPLETE" else None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if watermark_info is not None:
        marker["wiki_data_watermark"] = {
            "status": watermark_info.get("status"),
            "watermark_date": (watermark_info["watermark_date"].isoformat()
                                if watermark_info.get("watermark_date") else None),
            "lag_days": watermark_info.get("lag_days"),
            "retrieved_at_utc": watermark_info.get("retrieved_at_utc"),
            "source_url": watermark_info.get("source_url"),
            "http_status": watermark_info.get("http_status"),
        }
    if effective_info is not None:
        # 2026-08-05: the binding watermark and the full per-article
        # availability measurement behind it. Recorded whether the run
        # succeeded or failed closed -- a failed measurement set is exactly
        # the evidence needed to diagnose the next PARTIAL.
        eff_date = effective_info.get("effective_panel_watermark_date")
        marker["wiki_effective_panel_watermark"] = {
            "status": effective_info.get("status"),
            "effective_panel_watermark_date": eff_date.isoformat() if eff_date else None,
            "method": effective_info.get("method"),
            "aggregate_vs_panel_lag_days": effective_info.get("aggregate_vs_panel_lag_days"),
            "measured_count": effective_info.get("measured_count"),
            "expected_count": effective_info.get("expected_count"),
            "binding_tickers": effective_info.get("binding_tickers"),
            "unmeasured": effective_info.get("unmeasured"),
            "resolved_at_utc": effective_info.get("resolved_at_utc"),
            "per_ticker_latest_available_date": {
                t: (d.isoformat() if d else None)
                for t, d in sorted((effective_info.get("per_ticker_latest") or {}).items())
            },
        }
    with open(COMPLETION_MARKER_PATH, "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=2)
    log(f"\nCompletion marker written: {COMPLETION_MARKER_PATH}")
    log(json.dumps(marker, indent=2))


def is_run_complete(rows: list[dict], exit_status: str, expected_tickers: list[str],
                     watermark_status: str | None = None,
                     effective_watermark_status: str | None = None,
                     effective_watermark_date: date | None = None) -> bool:
    """The single COMPLETE gate, pulled out as a pure function so it's
    directly unit-testable (see test_phase2_dailypanel_gate.py) without
    running the full panel. A green run requires ALL of:
      - the ticker loop itself reported COMPLETE (no early total-budget stop)
      - exactly len(expected_tickers) rows, with exactly that many UNIQUE
        tickers (a duplicate row must not silently satisfy the count)
      - every row's all_six_fields_clean is True -- covers ONLY the six
        LOCKED research fields (gst_zscore, wiki_zscore,
        implied_volatility, realized_vol, price, volume; which itself
        already requires every Wikipedia chunk resolved, first pass or
        second pass). days_to_nearest_earnings is contextual metadata, NOT
        one of the six, and is deliberately NOT part of this check (see
        below for its own, separate, fail-closed requirement) --
        2026-08-01 correction: the 46aec15 baseline's successful 24/24 run
        legitimately had 4 tickers with earnings_status="ok" but no
        upcoming earnings date found; conflating that honest null into
        all_six_fields_clean would have falsely made that baseline PARTIAL.
      - earnings_status == "ok" for every row (fail-closed, checked
        SEPARATELY from all_six_fields_clean): a successful lookup that
        honestly finds no future earnings date (days_to_nearest_earnings
        is None) is fine and does not block COMPLETE; earnings_status of
        "error" or "timeout" -- an actual lookup FAILURE, not a genuine
        "none found" result -- does block it. No earnings date is ever
        fabricated to satisfy this.
      - every row has a parseable retrieval_timestamp_utc
      - watermark_status == "ok" (2026-08-01 addition): a run cannot be
        COMPLETE without a valid measured Wikipedia data watermark -- a
        watermark that failed closed or found no data within
        MAX_ACCEPTABLE_WIKI_LAG_DAYS means the wiki leg was never
        genuinely attempted with an honest completeness bar for anyone,
        regardless of what individual rows might otherwise show.
      - effective_watermark_status == "ok" (2026-08-05 addition): a valid
        AGGREGATE watermark is necessary but no longer sufficient. Without
        a complete set of validated per-article availability measurements
        there is no honest shared completeness bar, and the aggregate
        watermark must never be substituted for one.
      - EVERY row carries the SAME non-null
        wiki_effective_panel_watermark_date, equal to the run's resolved
        effective watermark, and that same date is also every row's
        wiki_zscore_anchor_date (2026-08-05 addition). One panel means one
        anchor: rows that disagree on the effective watermark, or whose
        z-score was anchored somewhere other than it, are not a comparable
        cross-section and can never be COMPLETE. This is what forbids
        ticker-specific anchor dates inside a single panel.
    Note what is deliberately NOT relaxed here: the effective watermark
    lowers a shared TRAILING edge, and every row must still satisfy
    all_six_fields_clean, which requires exact daily coverage across the
    complete required lookback. An internal historical gap sits BELOW the
    effective watermark and still fails this gate.
    Returns False (never raises) for any malformed row -- a gate that can
    crash on bad input is not a gate."""
    if exit_status != "COMPLETE":
        return False
    if watermark_status != "ok":
        return False
    if effective_watermark_status != "ok":
        return False
    if effective_watermark_date is None:
        return False
    if len(rows) != len(expected_tickers):
        return False
    tickers_seen = {r.get("ticker") for r in rows}
    if len(tickers_seen) != len(expected_tickers) or tickers_seen != set(expected_tickers):
        return False
    expected_effective = effective_watermark_date.isoformat()
    for r in rows:
        if not r.get("all_six_fields_clean"):
            return False
        if r.get("earnings_status") != "ok":
            return False
        # One panel, one watermark, one anchor -- no per-ticker anchors.
        if r.get("wiki_effective_panel_watermark_date") != expected_effective:
            return False
        if r.get("wiki_zscore_anchor_date") != expected_effective:
            return False
        ts = r.get("retrieval_timestamp_utc")
        if not ts:
            return False
        try:
            datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            return False
    return True


def main():
    run_ts = datetime.now(timezone.utc)
    log("*** GST PHASE 2 -- DAILY INFORMATION ARRIVAL PANEL (MANUAL TEST RUN 3) ***")
    log(f"Run timestamp (UTC): {run_ts.isoformat()}")
    log(f"Universe: {len(TICKERS)} tickers")
    log(f"Budgets: GST={GST_TICKER_BUDGET_S:.0f}s/ticker  "
        f"wiki-chunk={wiki_transport.CHUNK_TIMEOUT_S:.0f}s (process-isolated, calendar-chunked, cached)  "
        f"yfinance-call={YF_CALL_TIMEOUT_S:.0f}s  per-ticker={PER_TICKER_WALL_BUDGET_S:.0f}s  "
        f"total-run={TOTAL_RUN_BUDGET_S:.0f}s\n")
    log("NOTE (scope disclosure): only the Wikipedia leg uses genuinely killable "
        "subprocess isolation this pass. GST/earnings/price_history/iv legs still use "
        "the daemon-thread run_bounded() wrapper -- a timeout there is logged and the "
        "run continues, but the underlying call is not guaranteed to actually stop. "
        "This is disclosed, not claimed otherwise.\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    # --- MEASURED WIKIPEDIA DATA WATERMARK (2026-08-01) -- resolved EXACTLY
    # ONCE, here, before any ticker is processed. Not a waiver or stale-data
    # workaround: establishes exactly what Wikipedia data was genuinely
    # available at this retrieval timestamp, frozen for the rest of this
    # run. See GST_Phase2_Wikipedia_Transport.resolve_wiki_data_watermark()
    # for the full resolution policy and the 2026-08-01 PARTIAL regression
    # this replaces (a fixed today-1 assumption that was proven wrong by a
    # measured, confirmed 2-day Wikipedia publication lag). ---
    watermark_info = wiki_transport.resolve_wiki_data_watermark(anchor_date=run_ts.date())
    if watermark_info["status"] == "ok":
        log(f"Wikipedia data watermark: {watermark_info['watermark_date']} "
            f"(lag={watermark_info['lag_days']}d, source={watermark_info['source_url']})\n")
    else:
        log(f"*** WIKIPEDIA DATA WATERMARK COULD NOT BE ESTABLISHED (status={watermark_info['status']!r}) "
            f"-- the Wikipedia leg will be skipped for every ticker this run (fail-closed, not guessed). "
            f"probe_log={watermark_info['probe_log']} ***\n")

    # --- EFFECTIVE PANEL WATERMARK (2026-08-05) -- resolved EXACTLY ONCE,
    # here, before any ticker is processed, and binding for the whole run.
    # The aggregate watermark above is retained as a source-health /
    # provenance observation but no longer binds on its own: it answers
    # "did en.wikipedia.org publish day D site-wide?", never "did THIS
    # article publish day D?". The 2026-08-05 PARTIAL proved the gap
    # (aggregate: 2026-08-04; only 5 of 24 articles actually had it). See
    # GST_Phase2_Wikipedia_Transport.resolve_effective_panel_watermark().
    #
    # This addresses TRAILING publication lag only. Exact coverage across
    # the complete required lookback is still demanded of every ticker, so
    # an internal historical gap (e.g. CTSH 2026-07-08..14) still produces
    # PARTIAL -- lowering a shared trailing edge is not forgiving a hole. ---
    if watermark_info["status"] == "ok":
        log("Measuring per-article availability for all "
            f"{len(TICKERS)} locked tickers (one same-shape range probe each)...")
        effective_info = wiki_transport.resolve_effective_panel_watermark(
            TICKERS, TICKER_TO_WIKI_ARTICLE, anchor_date=run_ts.date(),
            aggregate_watermark_info=watermark_info)
    else:
        effective_info = {
            "status": "not_attempted_aggregate_watermark_failed",
            "effective_panel_watermark_date": None,
            "method": wiki_transport.EFFECTIVE_WATERMARK_METHOD,
            "aggregate_watermark_date": None, "aggregate_vs_panel_lag_days": None,
            "per_ticker_latest": {}, "measurements": [], "unmeasured": [],
            "measured_count": 0, "expected_count": len(TICKERS),
            "binding_tickers": [], "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    if effective_info["status"] == "ok":
        eff_date = effective_info["effective_panel_watermark_date"]
        log(f"Effective panel watermark: {eff_date} "
            f"(method={effective_info['method']}, "
            f"aggregate={effective_info['aggregate_watermark_date']}, "
            f"aggregate_vs_panel_lag_days={effective_info['aggregate_vs_panel_lag_days']}, "
            f"measured={effective_info['measured_count']}/{effective_info['expected_count']})")
        log(f"  binding ticker(s) at the minimum: {', '.join(effective_info['binding_tickers'])}")
        _ahead = sorted(t for t, d in effective_info["per_ticker_latest"].items() if d > eff_date)
        if _ahead:
            log(f"  {len(_ahead)} ticker(s) had newer data available and are deliberately "
                f"truncated to the shared watermark: {', '.join(_ahead)}")
        log("")
    elif watermark_info["status"] == "ok":
        log(f"*** EFFECTIVE PANEL WATERMARK COULD NOT BE ESTABLISHED "
            f"(status={effective_info['status']!r}, "
            f"measured={effective_info['measured_count']}/{effective_info['expected_count']}) -- "
            f"the Wikipedia leg will be skipped for every ticker this run (fail-closed; the "
            f"aggregate watermark is NOT substituted). unmeasured={effective_info['unmeasured']} ***\n")

    # The single binding watermark for every downstream stage this run.
    binding_watermark = effective_info.get("effective_panel_watermark_date")
    wiki_leg_enabled = watermark_info["status"] == "ok" and effective_info["status"] == "ok"

    rows: list[dict] = []
    wiki_pending_by_ticker: dict[str, dict] = {}
    wall_start = time.time()
    active_ticker = None
    exit_status = "COMPLETE"

    for i, ticker in enumerate(TICKERS, start=1):
        elapsed_so_far = time.time() - wall_start
        if elapsed_so_far >= TOTAL_RUN_BUDGET_S:
            log(f"\n*** TOTAL RUN BUDGET ({TOTAL_RUN_BUDGET_S:.0f}s) EXHAUSTED before starting "
                f"ticker {i}/{len(TICKERS)} ({ticker}). Stopping -- not restarting. ***")
            exit_status = "PARTIAL"
            active_ticker = ticker
            break

        active_ticker = ticker
        t0 = time.time()
        # Deadline discipline (2026-07-31 correction): cap this ticker's
        # Wikipedia first-pass chunk loop to whatever total-run budget
        # actually remains right now, so one late ticker's Wikipedia leg
        # cannot materially eat into the deadline meant for the tickers
        # after it -- not just an unconditional per-chunk timeout regardless
        # of how much run time is left.
        wiki_remaining_budget_s = max(0.0, TOTAL_RUN_BUDGET_S - (time.time() - wall_start))
        try:
            row, wiki_pending = process_ticker(pt, ticker, run_ts,
                                                wiki_remaining_budget_s=wiki_remaining_budget_s,
                                                watermark_info=watermark_info,
                                                effective_info=effective_info)
            if wiki_pending is not None:
                wiki_pending_by_ticker[ticker] = wiki_pending
        except Exception as e:
            # Isolation: an unexpected failure for one ticker must not destroy
            # already-collected rows for every other ticker.
            log(f"  [{ticker}] UNHANDLED EXCEPTION -- {e}\n{traceback.format_exc()}")
            row = {c: None for c in COLUMN_ORDER}
            row.update({"run_date": RUN_DATE.isoformat(), "ticker": ticker,
                        "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "all_six_fields_clean": False, "ticker_total_s": round(time.time() - t0, 3)})
        elapsed = time.time() - t0
        rows.append(row)
        write_checkpoint(rows)

        status = "CLEAN" if row.get("all_six_fields_clean") else "INCOMPLETE"
        log(f"[{i}/{len(TICKERS)}] {ticker}: {elapsed:.2f}s  {status}  "
            f"gst_z={row.get('gst_zscore')} wiki_z={row.get('wiki_zscore')} "
            f"iv={row.get('implied_volatility')} rv={row.get('realized_vol')} "
            f"price={row.get('price')} vol={row.get('volume')} "
            f"days_to_earnings={row.get('days_to_nearest_earnings')}")

        if elapsed > PER_TICKER_WALL_BUDGET_S:
            log(f"    NOTE: {ticker} took {elapsed:.0f}s, exceeding its "
                f"{PER_TICKER_WALL_BUDGET_S:.0f}s per-ticker budget -- continuing "
                f"(budget is advisory-logged per-ticker; TOTAL_RUN_BUDGET_S is the hard stop).")

        if i != len(TICKERS):
            time.sleep(random.uniform(*BETWEEN_TICKERS))
            if i % MICRO_BATCH_SIZE == 0:
                log(f"— small batch pause ({MICRO_BATCH_PAUSE_S}s) —")
                time.sleep(MICRO_BATCH_PAUSE_S)
    else:
        active_ticker = None   # loop completed normally, without break

    # --- WIKIPEDIA SECOND PASS (2026-07-31 REWRITE) -- run once at the RUN
    # level, after every ticker's first pass, not per-ticker and not inline.
    # A ticker queued here does NOT abort the run -- it was already
    # preserved in `rows` (as "pending_second_pass") and every other ticker
    # already ran to completion regardless. ---
    if wiki_pending_by_ticker and wiki_leg_enabled:
        combined_queue = []
        for pending in wiki_pending_by_ticker.values():
            combined_queue.extend(pending["failed_chunks"])
        remaining_budget = max(0.0, TOTAL_RUN_BUDGET_S - (time.time() - wall_start))
        log(f"\n*** WIKIPEDIA SECOND PASS: {len(combined_queue)} failed chunk(s) across "
            f"{len(wiki_pending_by_ticker)} ticker(s), remaining run budget {remaining_budget:.0f}s ***")
        second = wiki_transport.run_bounded_second_pass(combined_queue, remaining_budget_s=remaining_budget,
                                                          watermark=binding_watermark)
        for cr in second["chunk_results"]:
            log(f"    [{cr['ticker']}] second-pass chunk {cr['chunk_start']}..{cr['chunk_end']} "
                f"status={cr['status']} http_status={cr.get('http_status')} retry_after={cr.get('retry_after')} "
                f"network={cr['network_elapsed_s']:.2f}s sleep={cr['sleep_s']:.2f}s")
        for item in second["still_failed"]:
            log(f"    [{item['ticker']}] chunk {item['chunk_start']}..{item['chunk_end']} "
                f"STILL FAILED after second pass: {item['reason']}")

        # --- RECENT_LAST_KNOWN_GOOD fallback (2026-07-31, approved as a
        # narrow, strictly-bounded addition) -- runs ONLY after both the
        # fresh attempt and the one bounded second-pass attempt have
        # already failed, and ONLY resolves the current/open month's
        # chunk (a closed month that failed both passes is never eligible
        # -- see apply_recent_cache_fallback's own gating). This is a
        # read-only evaluation: it never writes to the cache, so a failed
        # refresh can never overwrite a valid prior snapshot. ---
        try:
            fallback_cache_df = wiki_transport.load_cache()
        except wiki_transport.CacheCorruptionError as e:
            log(f"  Wikipedia cache corruption detected during recent-cache-fallback "
                f"evaluation -- no fallback candidates available this run: {e}")
            fallback_cache_df = pd.DataFrame(columns=wiki_transport.CACHE_COLUMNS)
        fallback = wiki_transport.apply_recent_cache_fallback(
            second["still_failed"], fallback_cache_df, watermark=binding_watermark,
            now_utc=datetime.now(timezone.utc))
        for ticker, info in fallback["fallback_recovered"].items():
            prov = info["provenance"]
            log(f"    [{ticker}] RECENT_LAST_KNOWN_GOOD fallback used: "
                f"age={prov['wiki_cache_age_hours']:.2f}h retrieved_at={prov['wiki_fallback_retrieved_at_utc']} "
                f"effective_data_end={prov['wiki_effective_data_end']} "
                f"fresh_failure_http_status={prov['wiki_fresh_failure_http_status']}")
        for item in fallback["still_failed"]:
            if "fallback_rejected_reason" in item:
                log(f"    [{item['ticker']}] fallback NOT used ({item['fallback_rejected_reason']}) -- "
                    f"remains incomplete")

        # --- BOUNDED CLOSED-MONTH SUBCHUNK RECOVERY (2026-08-03) -- runs
        # ONLY after both the second pass and the recent-cache fallback
        # have already left something failed. Only closed months are
        # eligible (the fallback above already claimed the open/current
        # chunk, successfully or not); see
        # GST_Phase2_Wikipedia_Transport.run_bounded_subchunk_recovery()
        # for the full bounded, non-recursive, fail-closed contract. ---
        subchunk_remaining_budget = max(0.0, TOTAL_RUN_BUDGET_S - (time.time() - wall_start))
        subchunk = wiki_transport.run_bounded_subchunk_recovery(
            fallback["still_failed"], remaining_budget_s=subchunk_remaining_budget,
            watermark=binding_watermark)
        for ticker, prov in subchunk["subchunk_provenance"].items():
            log(f"    [{ticker}] subchunk recovery for {prov['original_chunk_start']}.."
                f"{prov['original_chunk_end']}: recovered={prov['recovered']} reason={prov['reason']!r} "
                f"requests_used={prov['requests_used']} wall_clock_s={prov['wall_clock_s']:.1f} "
                f"budget_exhausted={prov['budget_exhausted']}")

        for idx, row in enumerate(rows):
            ticker = row["ticker"]
            pending = wiki_pending_by_ticker.get(ticker)
            if pending is None:
                continue
            recovered_rows = second["recovered"].get(ticker, [])
            all_daily_rows = pending["daily_rows_so_far"] + recovered_rows
            still_failed_for_ticker = [f for f in subchunk["still_failed"] if f["ticker"] == ticker]
            fallback_info = fallback["fallback_recovered"].get(ticker)
            subchunk_rows = subchunk["recovered"].get(ticker)
            subchunk_prov = subchunk["subchunk_provenance"].get(ticker)
            row["wiki_subchunk_recovery_attempted"] = subchunk_prov is not None
            row["wiki_subchunk_recovery_provenance_json"] = json.dumps(subchunk_prov, sort_keys=True) if subchunk_prov else None
            # 2026-08-02 additive correction: combine this ticker's
            # preserved first-pass chunk_results (cache/fetch/cache_union_
            # reconstruction successes alongside whatever failed) with a
            # NORMALIZED view of this ticker's second-pass chunk_results
            # (source="fetch" added -- second pass is always a live fetch
            # retry, never a cache or union hit, by construction; the
            # transport module's own chunk_results dicts for second pass
            # carry no "source" field of their own) -- so the final
            # provenance derivation sees every chunk that ever contributed,
            # not just the ones from whichever pass happened to run last.
            ticker_second_pass_results = [
                {**cr, "source": "fetch"} for cr in second["chunk_results"] if cr["ticker"] == ticker
            ]
            combined_chunk_results = pending["chunk_results"] + ticker_second_pass_results
            if fallback_info is not None:
                all_daily_rows = all_daily_rows + fallback_info["rows"]
                _finalize_wiki_row(row, pending["article"], all_daily_rows, binding_watermark,
                                    combined_chunk_results)
                row.update(fallback_info["provenance"])   # overrides wiki_status/wiki_source_mode set by _finalize_wiki_row
                # The RECENT_LAST_KNOWN_GOOD fallback's own existing
                # provenance (set above) is untouched and remains
                # authoritative for wiki_status/wiki_source_mode. This
                # purely ADDS "recent_last_known_good" into the newer,
                # more granular component listing alongside whatever other
                # chunks for this ticker still contributed normally (e.g.
                # cache or cache_union_reconstruction hits for the ticker's
                # other, non-fallback months) -- never removes or
                # overrides anything apply_recent_cache_fallback() itself
                # produced.
                existing_components = json.loads(row.get("wiki_source_components_json") or "[]")
                merged_components = sorted(set(existing_components) | {"recent_last_known_good"})
                row["wiki_source_components_json"] = json.dumps(merged_components, sort_keys=True)
                log(f"    [{ticker}] wiki complete via RECENT_LAST_KNOWN_GOOD fallback: "
                    f"z={row.get('wiki_zscore')}")
            elif subchunk_rows is not None:
                all_daily_rows = all_daily_rows + subchunk_rows
                # Normalized entry so _wiki_source_provenance() recognizes
                # this chunk's contribution -- source="subchunk_salvage" is
                # never emitted by the transport module's own chunk_results
                # (that module reports subchunk-level detail separately, in
                # subchunk_prov["subchunks"]); this single normalized entry
                # represents the ORIGINAL failed chunk, now recovered, at
                # the same granularity as every other entry in
                # combined_chunk_results.
                recovered_entry = {
                    "chunk_start": subchunk_prov["original_chunk_start"],
                    "chunk_end": subchunk_prov["original_chunk_end"],
                    "source": "subchunk_salvage", "status": "ok",
                    "network_elapsed_s": subchunk_prov["wall_clock_s"], "sleep_s": 0.0,
                }
                _finalize_wiki_row(row, pending["article"], all_daily_rows, binding_watermark,
                                    combined_chunk_results + [recovered_entry])
                log(f"    [{ticker}] wiki fully recovered via bounded closed-month subchunk recovery: "
                    f"z={row.get('wiki_zscore')}")
            elif still_failed_for_ticker:
                row["wiki_status"] = "incomplete_after_second_pass"
                row["wiki_error"] = (f"{len(still_failed_for_ticker)} chunk(s) still failed: "
                                      + "; ".join(f"{f['chunk_start'].isoformat()}..{f['chunk_end'].isoformat()}"
                                                   f" ({f['reason']})" for f in still_failed_for_ticker))
                row["wiki_fresh_request_failed"] = True
            else:
                _finalize_wiki_row(row, pending["article"], all_daily_rows, binding_watermark,
                                    combined_chunk_results)
                log(f"    [{ticker}] wiki fully recovered after second pass: z={row.get('wiki_zscore')}")
            # all_six_fields_clean covers ONLY the six locked research
            # fields (2026-08-01 correction) -- see the matching comment in
            # process_ticker(). Recomputed here after second-pass/fallback
            # recovery may have changed wiki_zscore.
            six_fields = [row.get("gst_zscore"), row.get("wiki_zscore"), row.get("implied_volatility"),
                          row.get("realized_vol"), row.get("price"), row.get("volume")]
            row["all_six_fields_clean"] = all(v is not None for v in six_fields)
            rows[idx] = row
        write_checkpoint(rows)

    wall_total = time.time() - wall_start

    # COMPLETE requires 24 unique tickers, all six required fields complete,
    # valid timestamps, every Wikipedia chunk resolved (either in the first
    # pass or the bounded second pass), AND a valid measured Wikipedia data
    # watermark for this run -- see is_run_complete().
    if is_run_complete(rows, exit_status, TICKERS, watermark_status=watermark_info["status"],
                        effective_watermark_status=effective_info["status"],
                        effective_watermark_date=binding_watermark):
        df = pd.DataFrame(rows, columns=COLUMN_ORDER)
        df.to_csv(FINAL_OUT_PATH, index=False)
        log(f"\nWrote final (COMPLETE) output: {FINAL_OUT_PATH}")
    else:
        exit_status = "PARTIAL"
        log(f"\n*** RUN DID NOT PRODUCE A FULLY COMPLETE PANEL -- "
            f"{len(rows)} row(s) collected, "
            f"{sum(1 for r in rows if r.get('all_six_fields_clean'))} fully clean. "
            f"Checkpoint preserved at: {CHECKPOINT_PATH} ***")

    n_clean = sum(1 for r in rows if r.get("all_six_fields_clean"))
    n_earnings_ok = sum(1 for r in rows if r.get("earnings_status") == "ok")
    log("\n=== RUN SUMMARY ===")
    log(f"Status: {exit_status}")
    log(f"Tickers: {len(rows)}/{len(TICKERS)}  Clean (six locked research fields only): {n_clean}  "
        f"Incomplete: {len(rows) - n_clean}  Earnings lookup ok (date may still be null): {n_earnings_ok}")
    log(f"Total wall time: {wall_total:.1f}s ({wall_total/60:.2f} min)")

    write_completion_marker(rows, wall_total, exit_status,
                             active_ticker=active_ticker if exit_status == "PARTIAL" else None,
                             watermark_info=watermark_info, effective_info=effective_info)

    if exit_status != "COMPLETE":
        sys.exit(1)


if __name__ == "__main__":
    main()
