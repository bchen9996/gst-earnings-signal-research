#!/usr/bin/env python3
# GST Live Signal Engine — the validated methodology, run forward.
#
# For each ticker in TICKERS:
#   1. Pull the trailing ~12 months of weekly GST data (US, Web Search, All
#      categories, cat=0 — same as the validated backtests). A ~12-month
#      pull is used (not a short recent window) because Google Trends only
#      returns WEEKLY granularity for date ranges >=269 days; a shorter
#      request would silently switch to daily granularity and break the
#      week-bucketing the whole methodology depends on.
#   2. Compute the z-score for the LATEST returned week using the exact
#      same rolling methodology validated throughout this project
#      (shift(1).rolling(window=12, min_periods=8) — the current week's own
#      value never leaks into its own baseline). is_spike = zscore >= 2.0.
#   3. Classify the ticker symbol as ambiguous or clear using the identical
#      rule from GST_Zscore_VolatilityTest_Broad50_ByTicker.py (symbol
#      length <=2, or a common English word from the same conservative,
#      hand-curated list) — confirmed to matter: ambiguous-symbol tickers
#      showed a NULL volatility effect (+0.004 pts, p=0.98) vs clear-symbol
#      tickers (+0.934 pts, p=0.0000) in the Broad50 generalization test.
#   4. Tag every spike with a signal_tier: HIGH_CONFIDENCE_STRONG_EARNINGS
#      (z>=10 AND an earnings date within the next EARNINGS_WINDOW_DAYS=5
#      days), STRONG_EARNINGS (z=5-9.99 AND the same earnings-proximity
#      check), STRONG (z>=5, no earnings that close), or STANDARD (2<=z<5).
#      All spikes are still logged and still flow through to the straddle
#      logger — the tier is a label for later analysis, not an additional
#      filter here. The earnings check only runs for tickers that already
#      cleared z>=5 (cheap — a handful of tickers per run, not all 425), via
#      yfinance's earnings-date endpoint.
#
# *** SIGNAL-TIERING ENHANCEMENT (2026-07-19): HIGH_CONFIDENCE_STRONG_EARNINGS ***
# Purely a new classification layer on top of the existing validated signal —
# the z-score formula, the z>=5 STRONG_EARNINGS threshold, and the earnings-
# window logic are ALL unchanged. z>=10 events are now split out from the
# broader z=5-9.99 STRONG_EARNINGS tier into their own label, based on a
# verified split of the archived 147-event population (re-derived and
# confirmed from Live Signal Engine/MatchedControlGroup_Results.csv before
# this change was made): z>=10 (n=33) shows 93.9% win rate / +186.9pt median
# matched-control excess return, vs. z=5-9.99 (n=114) at 71.1% win rate /
# +38.6pt excess. This evidence comes from the ORIGINAL archived population
# ("GST-Legacy-v1", the chunked-method 147) — it has NOT yet been
# re-confirmed against the new canonical fixed-window population
# (Live Signal Engine/FixedWindow_PerEvent_Canonical.csv, n=152), which is a
# disclosed gap, not a hidden one. See CHANGELOG.md, 2026-07-19 entry.
#
# *** STRATEGY UNDER FORWARD TEST — FINAL, PRE-REGISTERED SPECIFICATION ***
# STRONG_EARNINGS tier entry (z>=5 AND earnings within 5 days upcoming —
# see THRESHOLD REFINEMENT note below for why this is z>=5, not z>=4),
# at-the-money straddle, EXIT AT THE NEXT TRADING DAY'S CLOSE AFTER THE
# EARNINGS ANNOUNCEMENT (see EXIT RULE REFINEMENT note below — this
# replaced the original hold-to-end-of-spike-week rule), priced with the
# earnings-aware model. This is the end state of a chain of
# pre-specified tests run on this project's historical data (run at the
# ORIGINAL z>=4 cutoff — historical record, not rewritten to match the
# current live threshold):
#   - GST_Strategy_Refinement_Test.py: z>=4 beat the unfiltered baseline at
#     every horizon; a +50%/5-day early-exit rule was tested and REJECTED
#     (underperformed simply holding to either full-hold horizon).
#   - GST_Straddle_Simulation_2021_2025_51Ticker.py: expanding the modern-
#     regime universe from 15 to 51 tickers grew the z>=4 NON-EARNINGS
#     subsample from n=11 to n=88 — and the result REVERSED (median P&L
#     flipped from +28.7%/+90.3% to -17.0%/-20.6%). Plain STRONG (z>=4
#     without nearby earnings) is NOT part of the validated edge — it is
#     still logged for reference, but should not be read as a signal on
#     its own.
#   - GST_EarningsAdjacent_SpikeVsNoSpike_Test.py: among ONLY earnings-
#     adjacent weeks, z>=4-spike weeks beat no-spike weeks by +131.1 pts
#     (spike-week horizon) and +62.4 pts (window horizon), both p=0.0000,
#     n=209 vs n=110. This is the specific combination — z>=4 AND earnings
#     nearby — that carries the real, validated edge, and was the
#     PRIMARY HYPOTHESIS UNDER LIVE FORWARD TEST at the original z>=4
#     cutoff. STRONG (non-earnings) and STANDARD tiers remain logged for
#     reference/comparison only, not as strategies expected to show an edge.
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
# This is NOT a re-embrace of the +50%/5-day profit-target early-exit rule
# GST_Strategy_Refinement_Test.py rejected above — that was a profit/time-
# triggered rule that underperformed full-hold. This is a different,
# EARNINGS-EVENT-ANCHORED exit (fixed to the actual earnings date, not a
# profit target or a fixed day-count from entry) that empirically beat
# full-hold instead of underperforming it.
# Still simulation-priced and pending real-price forward validation, same
# as every other spec in this project. No code logic changed here — the
# straddle logger only records entry; the exit decision itself is applied
# manually when checking outcomes against this documented rule.
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
# confirmed a sizing rule improves risk-adjusted outcomes, and no code
# here implements it; it is a documentation-only note for discretionary
# consideration.
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
# *** LOOK-AHEAD DISCLOSURE ***
# The latest week is typically PARTIAL (isPartial=True) — Google Trends
# reports the current in-progress week's search volume so far, which can
# still shift by week's end and could flip whether it crosses z>=2. This is
# flagged explicitly in the output (is_partial_week column) rather than
# hidden. Using the partial week is inherent to a LIVE signal (a backtest
# can wait for the week to close; a live signal that wants to act this week
# cannot) — the companion options script only acts on rows where is_spike
# is True at the time it's run, and the point-in-time discipline is
# preserved by TIMESTAMPING every run into an append-only log rather than
# ever rewriting history.
#
# *** BATCHED EXECUTION — added after the 425-ticker universe expansion
# repeatedly hit sustained Google Trends 429 rate-limiting when run as one
# 425-consecutive-request session (a real run stalled for 9+ hours). Rather
# than pulling the whole universe every session, tickers are split into
# fixed-size batches (DEFAULT_BATCH_SIZE=50 -> 9 batches for 425 tickers).
#   python GST_Live_Signal_Engine.py --batch 1     # tickers 1-50 only, then exit
#   python GST_Live_Signal_Engine.py --batch 2     # tickers 51-100 only, then exit
#   python GST_Live_Signal_Engine.py               # ALL batches, one per session,
#                                                   # with a 5-minute pause between
#                                                   # each (still one long session —
#                                                   # use --batch N across separate
#                                                   # sessions through the week to
#                                                   # avoid that entirely)
# *** WATCHLIST_LATEST CAVEAT — DISCLOSED, NOT HIDDEN ***
# watchlist_latest.csv is overwritten with ONLY the tickers processed in the
# most recently run batch, same as before batching existed (it was always
# "this run's tickers", not a cumulative cross-run union). If you run
# --batch 1 today and --batch 2 tomorrow, tomorrow's watchlist_latest.csv
# will contain batch 2's 50 tickers only, not the combined 100 — the
# companion straddle logger only sees whichever batch ran last. The
# append-only watchlist_log.csv still has the full history across every
# batch/session if you need to reconstruct broader point-in-time state.
#
# *** watchlist_log.csv LEGACY ROWS (7/8-7/10, pre-batch-numbering) — EXCLUDE ***
# Rows with run_timestamp before 2026-07-10T18:09:20 (the first --batch 1
# run) predate signal_tier/days_to_earnings existing in this script at all,
# so they only have 10 or 11 fields, not the current 12. The header row
# reflects the current 12-field schema; these older rows will read with
# their trailing values shifted into the wrong columns under it. Filter
# them out by run_timestamp >= first real batch run before doing any
# analysis across the full log. See watchlist_log_NOTES.md alongside the
# CSV for the exact cutoff list.
#
# Output: Live Signal Engine/watchlist_<RUN_TIMESTAMP>.csv   (this run's snapshot; filename tags the batch number when --batch is used)
#         Live Signal Engine/watchlist_log.csv                (append-only running log, across all batches/sessions)
#         Live Signal Engine/watchlist_latest.csv              (convenience copy of the most recently processed batch only, for the companion script)

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse, sys, time, random
import pandas as pd
import numpy as np
import urllib3
import requests
import yfinance as yf
from pytrends.request import TrendReq

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

EARNINGS_SESSION = requests.Session()
EARNINGS_SESSION.verify = False
EARNINGS_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

# Default watch universe = every current S&P 500 constituent whose ticker
# symbol clears the ambiguous-symbol filter (see is_ambiguous() below).
# Snapshot pulled from the Wikipedia S&P 500 constituent table (same source/
# method as Backtest_Universe.py) on 2026-07-10 — 503 constituents, 78
# excluded as ambiguous, 425 kept. Re-pull periodically to track index
# membership changes; this is a dated snapshot, not a live lookup, so the
# live signal engine doesn't take on a Wikipedia dependency on every run.
# Edit freely — every ticker passed through here gets pulled, scored, and
# classified regardless of what's in this default list.
TICKERS = [
    "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACN", "ADBE", "ADI", "ADM", "ADP",
    "ADSK", "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB",
    "ALGN", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "AON", "AOS", "APA", "APD", "APH", "APO", "APTV", "ARES", "ATO",
    "AVB", "AVGO", "AVY", "AWK", "AXON", "AXP", "AZO", "BAC", "BAX", "BBY",
    "BDX", "BEN", "BIIB", "BKNG", "BKR", "BLDR", "BLK", "BMY", "BNY", "BRK-B",
    "BSX", "BXP", "CAH", "CARR", "CASY", "CBOE", "CBRE", "CCI", "CCL", "CDNS",
    "CDW", "CEG", "CFG", "CHD", "CHRW", "CHTR", "CIEN", "CINF", "CLX", "CMCSA",
    "CME", "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COHR", "COIN", "COO",
    "COP", "COR", "CPAY", "CPRT", "CPT", "CRH", "CRL", "CRM", "CRWD", "CSCO",
    "CSGP", "CSX", "CTAS", "CTSH", "CTVA", "CVNA", "CVS", "CVX", "DAL", "DASH",
    "DDOG", "DECK", "DELL", "DGX", "DHI", "DHR", "DIS", "DLR", "DLTR",
    "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN", "DXCM", "EBAY",
    "ECHO", "ECL", "EFX", "EIX", "ELV", "EME", "EMR", "EOG", "EQIX", "EQR",
    "EQT", "ERIE", "ESS", "ETN", "ETR", "EVRG", "EXC", "EXE", "EXPD", "EXPE",
    "EXR", "FANG", "FCX", "FDS", "FDX", "FDXF", "FFIV", "FICO", "FIS", "FISV",
    "FITB", "FLEX", "FOX", "FOXA", "FRT", "FSLR", "FTNT", "FTV", "GDDY", "GEHC",
    "GEN", "GEV", "GILD", "GIS", "GLW", "GNRC", "GOOG", "GOOGL", "GPC", "GPN",
    "GRMN", "GWW", "HAL", "HAS", "HBAN", "HCA", "HIG", "HII", "HLT", "HON", "HONA",
    "HOOD", "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUBB", "HUM", "HWM", "IBKR",
    "IBM", "IDXX", "IEX", "IFF", "INCY", "INTC", "INTU", "INVH", "IQV", "IRM",
    "ISRG", "ITW", "IVZ", "JBHT", "JBL", "JCI", "JKHY", "JNJ", "JPM", "KDP",
    "KEYS", "KHC", "KIM", "KKR", "KLAC", "KMB", "KMI", "KVUE", "LDOS", "LEN",
    "LHX", "LII", "LIN", "LITE", "LLY", "LMT", "LNT", "LRCX", "LULU", "LUV",
    "LVS", "LYB", "LYV", "MAA", "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO",
    "MDLZ", "MDT", "META", "MGM", "MKC", "MLM", "MMM", "MNST", "MOS", "MPC",
    "MPWR", "MRK", "MRNA", "MRSH", "MRVL", "MSCI", "MSFT", "MSI", "MTB", "MTD",
    "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NKE", "NOC", "NRG", "NSC",
    "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWS", "NWSA", "NXPI", "ODFL", "OKE",
    "OMC", "ORCL", "ORLY", "OTIS", "OXY", "PANW", "PAYX", "PCAR", "PCG", "PEP", "PFE",
    "PFG", "PGR", "PHM", "PKG", "PLD", "PLTR", "PNC", "PNR", "PNW", "PODD",
    "PPG", "PPL", "PRU", "PSA", "PSKY", "PSX", "PTC", "PWR", "PYPL", "QCOM",
    "RCL", "REG", "REGN", "RJF", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG",
    "RTX", "RVTY", "SBAC", "SBUX", "SCHW", "SHW", "SJM", "SLB", "SMCI", "SNA",
    "SNDK", "SNPS", "SOLV", "SPG", "SPGI", "SRE", "STE", "STLD", "STT", "STX",
    "STZ", "SWK", "SWKS", "SYF", "SYK", "SYY", "TDG", "TDY", "TECH", "TEL",
    "TER", "TFC", "TGT", "TJX", "TKO", "TMO", "TMUS", "TPL", "TPR", "TRGP",
    "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TTD", "TTWO", "TXN", "TXT",
    "TYL", "UAL", "UBER", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS", "URI",
    "USB", "VEEV", "VICI", "VLO", "VLTO", "VMC", "VRSK", "VRSN", "VRT", "VRTX",
    "VST", "VTR", "VTRS", "WAB", "WAT", "WBD", "WDAY", "WDC", "WEC", "WFC",
    "WMB", "WMT", "WRB", "WSM", "WST", "WTW", "WYNN", "XEL", "XOM", "XYL",
    "ZBH", "ZBRA", "ZTS",
]

GEO = "US"
GPROP = ""
CATEGORY = 0            # All categories — matches the validated methodology
PULL_LOOKBACK_DAYS = 300   # >=269 days -> guarantees WEEKLY granularity from Google Trends

ROLLING_WINDOW = 12
Z_THRESHOLD = 2.0
MIN_PERIODS = 8
STRONG_TIER_Z_THRESHOLD = 5.0   # raised from 4.0 -> 5.0; see THRESHOLD REFINEMENT note in the header
HIGH_CONFIDENCE_Z_THRESHOLD = 10.0   # see SIGNAL-TIERING ENHANCEMENT note in the header; a classification
                                      # split within the existing STRONG_EARNINGS tier, not a new threshold
EARNINGS_WINDOW_DAYS = 5        # matches GST_EarningsAdjacent_SpikeVsNoSpike_Test.py's within_5d definition
EARNINGS_PULL_LIMIT = 12        # small — only need the next upcoming date, not history

# "are"/"low"/"bro" are the original, empirically-validated set (Broad50
# generalization test showed these specific tickers had a NULL volatility
# effect vs. clear-symbol tickers). The rest were added by hand for the
# S&P 500 expansion, by the SAME conservative standard (an unmistakably
# common, high-frequency English word/term) but are NOT independently
# statistically validated the way are/low/bro were — this is a disclosed
# judgment call, not a re-run of the volatility test on the new tickers.
COMMON_WORDS = {
    "are", "low", "bro",
    "all", "app", "ball", "cat", "cost", "doc", "fast", "fix", "ice", "key",
    "met", "now", "peg", "tap", "well", "xyz", "yum",
}

OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

BETWEEN_TICKERS = (1.5, 3.0)
MICRO_BATCH_SIZE = 6          # small in-batch pause cadence (unchanged from before outer batching existed)
MICRO_BATCH_PAUSE_S = 20
HARD_429_SLEEP = 60
MAX_ATTEMPTS = 5

DEFAULT_BATCH_SIZE = 50       # tickers per --batch (outer, session-level batching)
BATCH_PAUSE_BETWEEN_BATCHES_S = 300   # 5 min, only used when running multiple batches in one session


def is_ambiguous(ticker: str) -> bool:
    base = ticker.split("-")[0]
    if len(base) <= 2:
        return True
    return base.lower() in COMMON_WORDS


def base_tier(zscore: float | None) -> str | None:
    """z-score-only tier, before any earnings-proximity refinement."""
    if zscore is None or zscore < Z_THRESHOLD:
        return None
    return "STRONG" if zscore >= STRONG_TIER_Z_THRESHOLD else "STANDARD"


def fetch_days_to_next_earnings(ticker: str) -> int | None:
    """Days from today to the ticker's next upcoming earnings date, or None if unavailable."""
    try:
        tk = yf.Ticker(ticker, session=EARNINGS_SESSION)
        df = tk.get_earnings_dates(limit=EARNINGS_PULL_LIMIT)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    today = datetime.now(timezone.utc).date()
    try:
        future = sorted(d.date() for d in pd.to_datetime(df.index).tz_localize(None).normalize()
                         if d.date() >= today)
    except Exception:
        return None
    if not future:
        return None
    return (future[0] - today).days


def fetch_ticker_series(pt: TrendReq, term: str) -> pd.DataFrame:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=PULL_LOOKBACK_DAYS)
    timeframe = f"{start_date.isoformat()} {end_date.isoformat()}"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pt.build_payload([term], timeframe=timeframe, geo=GEO, gprop=GPROP, cat=CATEGORY)
            df = pt.interest_over_time()
            if df is None or df.empty or term not in df.columns:
                raise RuntimeError("Empty result or missing term column")
            out = pd.DataFrame({
                "Week": df.index,
                "gst": pd.to_numeric(df[term], errors="coerce"),
                "isPartial": df["isPartial"].astype(bool),
            }).sort_values("Week").reset_index(drop=True)
            return out
        except Exception as e:
            msg = str(e).lower()
            pause = HARD_429_SLEEP if ("429" in msg or ("rate" in msg and "limit" in msg) or "too many" in msg) \
                else min(6, 2 * attempt) + random.uniform(0, 0.5)
            print(f"[{term}] attempt {attempt} failed: {e} — sleeping {pause:.1f}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Week", "gst", "isPartial"])


def compute_latest_zscore(df: pd.DataFrame) -> dict:
    if len(df) < MIN_PERIODS + 1:
        return {"zscore": None, "is_spike": False, "note": f"insufficient history ({len(df)} weeks)"}

    rolling = df["gst"].shift(1).rolling(window=ROLLING_WINDOW, min_periods=MIN_PERIODS)
    roll_mean = rolling.mean()
    roll_std = rolling.std()
    # STD_EPSILON_FLOOR: numerical-stability guard added 2026-07-18 (see CHANGELOG.md). A near-zero
    # (but nonzero) roll_std during a flat/low-volume stretch previously produced division-by-near-
    # zero z-scores in the millions (found on GME) that pass straight through as a "valid" spike --
    # unlike an exact-zero std, these don't hit the inf->NaN replacement below. Floor value (1.0)
    # matches gst's integer 0-100 resolution -- the smallest std that could reflect real variation.
    # This does not change the z-score formula's shape or the z>=5 threshold; not a rule change.
    STD_EPSILON_FLOOR = 1.0
    zscore_series = (df["gst"] - roll_mean) / roll_std.clip(lower=STD_EPSILON_FLOOR)
    zscore_series = zscore_series.replace([np.inf, -np.inf], np.nan)

    latest = df.iloc[-1]
    latest_z = zscore_series.iloc[-1]

    if pd.isna(latest_z):
        return {"zscore": None, "is_spike": False, "note": "z-score undefined (flat baseline or insufficient history)"}

    return {
        "zscore": round(float(latest_z), 3),
        "is_spike": bool(latest_z >= Z_THRESHOLD),
        "note": "",
        "week": latest["Week"].date(),
        "gst_value": int(latest["gst"]) if pd.notna(latest["gst"]) else None,
        "is_partial_week": bool(latest["isPartial"]),
    }


def process_batch(pt: TrendReq, batch_tickers: list[str], run_ts: datetime,
                   global_offset: int, total_tickers: int) -> list[dict]:
    """Runs the fetch/classify loop for one batch's tickers. global_offset is this
    batch's starting 0-index within the full TICKERS list, used only for progress
    printing so batch 2's tickers still show their true position (e.g. 51/425)."""
    rows = []
    for j, ticker in enumerate(batch_tickers, start=1):
        i = global_offset + j
        series = fetch_ticker_series(pt, ticker)
        ambiguous = is_ambiguous(ticker)

        if series.empty:
            rows.append({
                "ticker": ticker, "run_timestamp": run_ts.isoformat(), "week": None,
                "gst_value": None, "is_partial_week": None, "zscore": None,
                "is_spike": False, "signal_tier": None, "days_to_earnings": None,
                "ambiguous_symbol": ambiguous,
                "eligible_for_options_leg": False, "note": "GST pull failed/empty",
            })
            print(f"[{i}/{total_tickers}] {ticker}: GST pull failed/empty")
        else:
            z = compute_latest_zscore(series)
            tier = base_tier(z.get("zscore"))

            days_to_earnings = None
            if tier == "STRONG":
                days_to_earnings = fetch_days_to_next_earnings(ticker)
                if days_to_earnings is not None and 0 <= days_to_earnings <= EARNINGS_WINDOW_DAYS:
                    zscore = z.get("zscore")
                    if zscore is not None and zscore >= HIGH_CONFIDENCE_Z_THRESHOLD:
                        tier = "HIGH_CONFIDENCE_STRONG_EARNINGS"
                    else:
                        tier = "STRONG_EARNINGS"

            eligible = bool(z.get("is_spike", False)) and not ambiguous
            rows.append({
                "ticker": ticker, "run_timestamp": run_ts.isoformat(),
                "week": z.get("week"), "gst_value": z.get("gst_value"),
                "is_partial_week": z.get("is_partial_week"),
                "zscore": z.get("zscore"), "is_spike": z.get("is_spike", False),
                "signal_tier": tier, "days_to_earnings": days_to_earnings,
                "ambiguous_symbol": ambiguous,
                "eligible_for_options_leg": eligible,
                "note": z.get("note", ""),
            })
            flag = tier if tier else "-"
            amb = "AMBIGUOUS" if ambiguous else "clear"
            print(f"[{i}/{total_tickers}] {ticker}: z={z.get('zscore')} {flag} ({amb}) "
                  f"partial_week={z.get('is_partial_week')} days_to_earnings={days_to_earnings}")

        time.sleep(random.uniform(*BETWEEN_TICKERS))
        if j % MICRO_BATCH_SIZE == 0 and j != len(batch_tickers):
            print(f"— small batch pause ({MICRO_BATCH_PAUSE_S}s) —")
            time.sleep(MICRO_BATCH_PAUSE_S)

    return rows


def write_outputs(rows: list[dict], run_ts: datetime, batch_tag: str) -> None:
    watchlist = pd.DataFrame(rows)

    run_ts_str = run_ts.strftime("%Y-%m-%dT%H-%M-%SZ")
    snapshot_path = OUT_DIR / f"watchlist_{run_ts_str}{batch_tag}.csv"
    watchlist.to_csv(snapshot_path, index=False)

    log_path = OUT_DIR / "watchlist_log.csv"
    watchlist.to_csv(log_path, mode="a", index=False, header=not log_path.exists())

    latest_path = OUT_DIR / "watchlist_latest.csv"
    watchlist.to_csv(latest_path, index=False)

    flagged = watchlist[watchlist["is_spike"] == True]  # noqa: E712
    eligible = watchlist[watchlist["eligible_for_options_leg"] == True]  # noqa: E712
    high_confidence = eligible[eligible["signal_tier"] == "HIGH_CONFIDENCE_STRONG_EARNINGS"]
    strong_earnings = eligible[eligible["signal_tier"] == "STRONG_EARNINGS"]
    strong = eligible[eligible["signal_tier"] == "STRONG"]
    standard = eligible[eligible["signal_tier"] == "STANDARD"]

    print(f"\n{len(flagged)} tickers flagged (is_spike=True) out of {len(watchlist)}")
    print(f"{len(eligible)} eligible for options leg (spike AND clear symbol): "
          f"{len(high_confidence)} HIGH_CONFIDENCE_STRONG_EARNINGS (z>={HIGH_CONFIDENCE_Z_THRESHOLD:g} + earnings "
          f"within {EARNINGS_WINDOW_DAYS}d, HIGHEST-CONFIDENCE SUBSET), "
          f"{len(strong_earnings)} STRONG_EARNINGS (z={STRONG_TIER_Z_THRESHOLD:g}-{HIGH_CONFIDENCE_Z_THRESHOLD-0.01:g} + earnings "
          f"within {EARNINGS_WINDOW_DAYS}d, PRIMARY HYPOTHESIS under forward test), "
          f"{len(strong)} STRONG (z>={STRONG_TIER_Z_THRESHOLD:g}, non-earnings, reference only), "
          f"{len(standard)} STANDARD ({Z_THRESHOLD:g}<=z<{STRONG_TIER_Z_THRESHOLD:g}, reference only)")
    if not eligible.empty:
        print(eligible[["ticker", "zscore", "signal_tier", "days_to_earnings", "week", "is_partial_week"]]
              .to_string(index=False))

    print(f"\nWrote snapshot to: {snapshot_path}")
    print(f"Appended to running log: {log_path}")
    print(f"Wrote latest-run copy to: {latest_path} "
          f"(contains ONLY this batch's {len(watchlist)} tickers — see WATCHLIST_LATEST CAVEAT in the script header)")


def parse_args():
    parser = argparse.ArgumentParser(description="GST Live Signal Engine — batched execution.")
    parser.add_argument("--batch", type=int, default=None,
                         help="1-indexed batch number to run (e.g. 1 = tickers 1-50). "
                              "If omitted, runs ALL batches in this one session, "
                              f"pausing {BATCH_PAUSE_BETWEEN_BATCHES_S}s between each.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                         help=f"Tickers per batch (default {DEFAULT_BATCH_SIZE}).")
    return parser.parse_args()


def main():
    args = parse_args()
    batch_size = args.batch_size
    ticker_batches = [TICKERS[i:i + batch_size] for i in range(0, len(TICKERS), batch_size)]
    n_batches = len(ticker_batches)

    if args.batch is not None:
        if not (1 <= args.batch <= n_batches):
            print(f"ERROR: --batch {args.batch} out of range. With batch-size={batch_size} and "
                  f"{len(TICKERS)} tickers, valid batches are 1-{n_batches}.")
            sys.exit(1)
        batches_to_run = [(args.batch, ticker_batches[args.batch - 1])]
    else:
        batches_to_run = list(enumerate(ticker_batches, start=1))

    print(f"Universe: {len(TICKERS)} tickers total, batch-size={batch_size} -> {n_batches} batches. "
          f"Running batch(es): {[b for b, _ in batches_to_run]}\n")

    pt = TrendReq(hl="en-US", tz=0, timeout=(30, 60), retries=0, backoff_factor=0.0,
                  requests_args={"verify": False})

    for k, (batch_num, batch_tickers) in enumerate(batches_to_run):
        run_ts = datetime.now(timezone.utc)
        global_offset = (batch_num - 1) * batch_size
        print(f"=== Batch {batch_num}/{n_batches} (tickers {global_offset + 1}-{global_offset + len(batch_tickers)} "
              f"of {len(TICKERS)}) — run at {run_ts.isoformat()} ===")

        rows = process_batch(pt, batch_tickers, run_ts, global_offset, len(TICKERS))
        write_outputs(rows, run_ts, batch_tag=f"_batch{batch_num}")

        is_last = (k == len(batches_to_run) - 1)
        if not is_last:
            print(f"\n— pausing {BATCH_PAUSE_BETWEEN_BATCHES_S}s before batch {batches_to_run[k+1][0]}/{n_batches} —\n")
            time.sleep(BATCH_PAUSE_BETWEEN_BATCHES_S)


if __name__ == "__main__":
    main()
