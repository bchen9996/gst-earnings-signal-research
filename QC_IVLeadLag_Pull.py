# ============================================================================
# GST-vs-IV LEAD/LAG DIAGNOSTIC PULL -- mechanism diagnosis for why
# Candidate B (pre-earnings IV expansion) never showed a confirmed edge.
# Existing real-quote data (all of tonight's pulls) only ever captured
# entry and exit -- two points, structurally incapable of showing WHEN a
# repricing trend started. This pulls a genuine pre-event TIME SERIES.
#
# SAMPLE: the 35 z>=10 events already locked in
# Live Signal Engine/CandidateB_v1_FORWARD_LOCKED.md /
# QC_CandidateB_PreRegistered_Pull.py -- the tier that's the actual
# subject of "why did Candidate B fail," not a new cherry-pick.
#
# DESIGN: for each event, 6 checkpoints spanning the 15 trading days
# before entry (entry-15, -12, -9, -6, -3, and entry itself -- every 3rd
# trading day, using each ticker's own real trading calendar, not a
# weekday approximation). At each checkpoint, pull the SAME ATM contract
# selected once at entry (fixed strike + expiry, consistent across the
# whole window -- so any cost change reflects repricing of that specific
# contract, not a moving target) and record its ask-side cost as % of
# spot -- the same "implied move" proxy used throughout tonight
# (real_cost_pct_of_spot).
#
# *** RESOLUTION MISMATCH, DISCLOSED UP FRONT: GST is WEEKLY-resolution
# (the canonical z-score is computed per calendar week, not per day) --
# so "GST crossed threshold" can only ever be pinned to a specific WEEK
# (already known: the `spike_week` field below), never a specific day.
# The IV side here IS measured with day-level checkpoints. Any lead/lag
# classification this data supports compares "did IV expansion start
# before/during/after GST's signal WEEK" -- not a day-for-day race on
# both sides. ***
#
# This script ONLY PULLS the raw time series and exports it -- it does
# NOT attempt the lead/lag classification itself (baseline definition,
# expansion-threshold, etc. are analysis choices better made locally,
# after seeing the actual data, using the same discipline as every other
# real-quote analysis tonight).
#
# HOW TO USE: paste this entire file into an empty cell in your
# QuantConnect Research notebook and run it. No file upload needed.
# ============================================================================

import pandas as pd
import numpy as np
from datetime import timedelta
from QuantConnect.Research import QuantBook

qb = QuantBook()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
TICKER_OVERRIDES = {"BRK-B": "BRK.B"}

# ---------------------------------------------------------------------------
# EMBEDDED SAMPLE (n=35 events x 6 checkpoints = 210 checkpoint pulls) --
# the 35 z>=10 events from CandidateB_v1_FORWARD_LOCKED.md, unchanged.
# Checkpoints computed from each ticker's own local trading calendar
# (entry-15, -12, -9, -6, -3, entry).
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "ADBE", "spike_week": "2022-09-11", "entry_date": "2022-09-13", "zscore": 24.1066, "checkpoints": ["2022-08-22", "2022-08-25", "2022-08-30", "2022-09-02", "2022-09-08", "2022-09-13"]},
    {"ticker": "ADBE", "spike_week": "2023-12-10", "entry_date": "2023-12-12", "zscore": 15.6618, "checkpoints": ["2023-11-20", "2023-11-24", "2023-11-29", "2023-12-04", "2023-12-07", "2023-12-12"]},
    {"ticker": "BKR", "spike_week": "2025-07-20", "entry_date": "2025-07-22", "zscore": 11.4518, "checkpoints": ["2025-06-30", "2025-07-03", "2025-07-09", "2025-07-14", "2025-07-17", "2025-07-22"]},
    {"ticker": "COHR", "spike_week": "2024-02-04", "entry_date": "2024-02-06", "zscore": 11.4444, "checkpoints": ["2024-01-16", "2024-01-19", "2024-01-24", "2024-01-29", "2024-02-01", "2024-02-06"]},
    {"ticker": "DVN", "spike_week": "2023-02-12", "entry_date": "2023-02-14", "zscore": 10.279, "checkpoints": ["2023-01-24", "2023-01-27", "2023-02-01", "2023-02-06", "2023-02-09", "2023-02-14"]},
    {"ticker": "GPN", "spike_week": "2021-08-01", "entry_date": "2021-08-03", "zscore": 13.574, "checkpoints": ["2021-07-13", "2021-07-16", "2021-07-21", "2021-07-26", "2021-07-29", "2021-08-03"]},
    {"ticker": "MSFT", "spike_week": "2022-01-23", "entry_date": "2022-01-25", "zscore": 13.478, "checkpoints": ["2021-12-31", "2022-01-06", "2022-01-11", "2022-01-14", "2022-01-20", "2022-01-25"]},
    {"ticker": "MSFT", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "zscore": 13.1069, "checkpoints": ["2022-10-04", "2022-10-07", "2022-10-12", "2022-10-17", "2022-10-20", "2022-10-25"]},
    {"ticker": "MSFT", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "zscore": 11.7806, "checkpoints": ["2022-12-29", "2023-01-05", "2023-01-10", "2023-01-13", "2023-01-19", "2023-01-24"]},
    {"ticker": "MSFT", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "zscore": 11.4508, "checkpoints": ["2025-01-03", "2025-01-08", "2025-01-14", "2025-01-17", "2025-01-23", "2025-01-28"]},
    {"ticker": "MSFT", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "zscore": 13.3765, "checkpoints": ["2025-07-08", "2025-07-11", "2025-07-16", "2025-07-21", "2025-07-24", "2025-07-29"]},
    {"ticker": "NFLX", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "zscore": 10.2794, "checkpoints": ["2021-06-28", "2021-07-01", "2021-07-07", "2021-07-12", "2021-07-15", "2021-07-20"]},
    {"ticker": "NFLX", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "zscore": 15.2739, "checkpoints": ["2021-09-28", "2021-10-01", "2021-10-06", "2021-10-11", "2021-10-14", "2021-10-19"]},
    {"ticker": "NFLX", "spike_week": "2022-01-16", "entry_date": "2022-01-18", "zscore": 31.0985, "checkpoints": ["2021-12-23", "2021-12-29", "2022-01-04", "2022-01-07", "2022-01-12", "2022-01-18"]},
    {"ticker": "NFLX", "spike_week": "2022-04-17", "entry_date": "2022-04-19", "zscore": 13.6261, "checkpoints": ["2022-03-28", "2022-03-31", "2022-04-05", "2022-04-08", "2022-04-13", "2022-04-19"]},
    {"ticker": "NFLX", "spike_week": "2022-10-16", "entry_date": "2022-10-18", "zscore": 16.4636, "checkpoints": ["2022-09-27", "2022-09-30", "2022-10-05", "2022-10-10", "2022-10-13", "2022-10-18"]},
    {"ticker": "NFLX", "spike_week": "2023-07-16", "entry_date": "2023-07-18", "zscore": 15.8142, "checkpoints": ["2023-06-26", "2023-06-29", "2023-07-05", "2023-07-10", "2023-07-13", "2023-07-18"]},
    {"ticker": "NFLX", "spike_week": "2024-07-14", "entry_date": "2024-07-16", "zscore": 13.6586, "checkpoints": ["2024-06-24", "2024-06-27", "2024-07-02", "2024-07-08", "2024-07-11", "2024-07-16"]},
    {"ticker": "NFLX", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "zscore": 17.0766, "checkpoints": ["2024-09-24", "2024-09-27", "2024-10-02", "2024-10-07", "2024-10-10", "2024-10-15"]},
    {"ticker": "NFLX", "spike_week": "2025-01-19", "entry_date": "2025-01-21", "zscore": 12.7874, "checkpoints": ["2024-12-24", "2024-12-30", "2025-01-06", "2025-01-10", "2025-01-15", "2025-01-21"]},
    {"ticker": "NKE", "spike_week": "2021-06-20", "entry_date": "2021-06-22", "zscore": 11.9064, "checkpoints": ["2021-06-01", "2021-06-04", "2021-06-09", "2021-06-14", "2021-06-17", "2021-06-22"]},
    {"ticker": "NKE", "spike_week": "2022-03-20", "entry_date": "2022-03-22", "zscore": 10.4459, "checkpoints": ["2022-03-01", "2022-03-04", "2022-03-09", "2022-03-14", "2022-03-17", "2022-03-22"]},
    {"ticker": "NKE", "spike_week": "2023-06-25", "entry_date": "2023-06-27", "zscore": 11.2982, "checkpoints": ["2023-06-05", "2023-06-08", "2023-06-13", "2023-06-16", "2023-06-22", "2023-06-27"]},
    {"ticker": "NKE", "spike_week": "2024-03-17", "entry_date": "2024-03-19", "zscore": 10.7769, "checkpoints": ["2024-02-27", "2024-03-01", "2024-03-06", "2024-03-11", "2024-03-14", "2024-03-19"]},
    {"ticker": "NKE", "spike_week": "2024-06-23", "entry_date": "2024-06-25", "zscore": 22.4678, "checkpoints": ["2024-06-03", "2024-06-06", "2024-06-11", "2024-06-14", "2024-06-20", "2024-06-25"]},
    {"ticker": "NVDA", "spike_week": "2023-05-21", "entry_date": "2023-05-23", "zscore": 17.1935, "checkpoints": ["2023-05-02", "2023-05-05", "2023-05-10", "2023-05-15", "2023-05-18", "2023-05-23"]},
    {"ticker": "QCOM", "spike_week": "2021-10-31", "entry_date": "2021-11-02", "zscore": 18.6841, "checkpoints": ["2021-10-12", "2021-10-15", "2021-10-20", "2021-10-25", "2021-10-28", "2021-11-02"]},
    {"ticker": "QCOM", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "zscore": 10.5713, "checkpoints": ["2023-04-11", "2023-04-14", "2023-04-19", "2023-04-24", "2023-04-27", "2023-05-02"]},
    {"ticker": "QCOM", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "zscore": 12.3111, "checkpoints": ["2025-07-08", "2025-07-11", "2025-07-16", "2025-07-21", "2025-07-24", "2025-07-29"]},
    {"ticker": "SBUX", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "zscore": 12.306, "checkpoints": ["2023-04-11", "2023-04-14", "2023-04-19", "2023-04-24", "2023-04-27", "2023-05-02"]},
    {"ticker": "SBUX", "spike_week": "2024-04-28", "entry_date": "2024-04-30", "zscore": 26.7718, "checkpoints": ["2024-04-09", "2024-04-12", "2024-04-17", "2024-04-22", "2024-04-25", "2024-04-30"]},
    {"ticker": "SBUX", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "zscore": 13.6492, "checkpoints": ["2025-01-03", "2025-01-08", "2025-01-14", "2025-01-17", "2025-01-23", "2025-01-28"]},
    {"ticker": "STZ", "spike_week": "2024-04-07", "entry_date": "2024-04-09", "zscore": 10.1959, "checkpoints": ["2024-03-18", "2024-03-21", "2024-03-26", "2024-04-01", "2024-04-04", "2024-04-09"]},
    {"ticker": "STZ", "spike_week": "2025-01-05", "entry_date": "2025-01-07", "zscore": 11.7801, "checkpoints": ["2024-12-12", "2024-12-17", "2024-12-20", "2024-12-26", "2024-12-31", "2025-01-07"]},
    {"ticker": "TTWO", "spike_week": "2023-05-14", "entry_date": "2023-05-16", "zscore": 12.5688, "checkpoints": ["2023-04-25", "2023-04-28", "2023-05-03", "2023-05-08", "2023-05-11", "2023-05-16"]},
]

CHECKPOINT_LABELS = ["entry-15td", "entry-12td", "entry-9td", "entry-6td", "entry-3td", "entry"]

# ---------------------------------------------------------------------------
# HELPERS (same History<QuoteBar> pattern as every prior pull tonight)
# ---------------------------------------------------------------------------
def get_bid_ask(option_symbol, target_date):
    start = target_date - timedelta(days=5)
    end = target_date + timedelta(days=1)
    hist = qb.History(QuoteBar, option_symbol, start, end, Resolution.Minute)
    if hist is None or hist.empty:
        return None, None
    if isinstance(hist.index, pd.MultiIndex):
        times = hist.index.get_level_values(-1)
    else:
        times = hist.index
    mask = pd.to_datetime(times).date <= target_date.date()
    day_rows = hist[mask] if mask.any() else hist
    if day_rows.empty:
        return None, None
    last = day_rows.iloc[-1]
    bid = float(last["bidclose"]) if "bidclose" in last and pd.notna(last["bidclose"]) else None
    ask = float(last["askclose"]) if "askclose" in last and pd.notna(last["askclose"]) else None
    return bid, ask


def get_spot(equity_symbol, target_date):
    hist = qb.History(equity_symbol, target_date - timedelta(days=7), target_date + timedelta(days=1), Resolution.Daily)
    if hist is None or hist.empty:
        return None
    return float(hist["close"].iloc[-1])


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
results = []

for event_idx, ev in enumerate(EMBEDDED_SAMPLE):
    raw_ticker = ev["ticker"]
    qc_ticker = TICKER_OVERRIDES.get(raw_ticker, raw_ticker)
    entry_date = pd.Timestamp(ev["entry_date"]).to_pydatetime()

    print(f"\n[{event_idx+1}/{len(EMBEDDED_SAMPLE)}] {raw_ticker} spike_week={ev['spike_week']} z={ev['zscore']}")

    try:
        equity = qb.AddEquity(qc_ticker, Resolution.Daily)
        equity_symbol = equity.Symbol

        # Select the ATM contract ONCE, at entry -- same contract used for every checkpoint.
        entry_spot = get_spot(equity_symbol, entry_date)
        if entry_spot is None:
            print("  no entry spot -- skipping event")
            continue

        contracts = list(qb.OptionChainProvider.GetOptionContractList(equity_symbol, entry_date))
        if not contracts:
            print("  no option chain at entry -- skipping event")
            continue
        expiries = sorted(set(c.ID.Date for c in contracts if c.ID.Date >= entry_date + timedelta(days=5)))
        if not expiries:
            print("  no suitable expiration -- skipping event")
            continue
        target_expiry = expiries[0]
        same_expiry = [c for c in contracts if c.ID.Date == target_expiry]
        strikes = sorted(set(c.ID.StrikePrice for c in same_expiry))
        if not strikes:
            print("  no strikes -- skipping event")
            continue
        atm_strike = min(strikes, key=lambda k: abs(k - entry_spot))
        call_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                             and c.ID.OptionRight == OptionRight.Call), None)
        put_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                            and c.ID.OptionRight == OptionRight.Put), None)
        if call_symbol is None or put_symbol is None:
            print("  missing call/put at ATM strike -- skipping event")
            continue

        for cp_label, cp_date_str in zip(CHECKPOINT_LABELS, ev["checkpoints"]):
            cp_date = pd.Timestamp(cp_date_str).to_pydatetime()
            spot = get_spot(equity_symbol, cp_date)
            call_bid, call_ask = get_bid_ask(call_symbol, cp_date)
            put_bid, put_ask = get_bid_ask(put_symbol, cp_date)

            row = {"event_idx": event_idx, "ticker": raw_ticker, "spike_week": ev["spike_week"],
                   "zscore": ev["zscore"], "entry_date": ev["entry_date"], "checkpoint_label": cp_label,
                   "checkpoint_date": cp_date_str, "atm_strike": atm_strike,
                   "expiry": target_expiry.date().isoformat(), "spot": spot,
                   "call_ask": call_ask, "put_ask": put_ask, "note": ""}

            if spot is None or call_ask is None or put_ask is None:
                row["note"] = "missing spot or quote data at this checkpoint"
                row["cost_pct_of_spot"] = None
            else:
                row["cost_pct_of_spot"] = round((call_ask + put_ask) / spot * 100, 3)

            results.append(row)
            print(f"    {cp_label} ({cp_date_str}): cost_pct_of_spot="
                  f"{row['cost_pct_of_spot']}" + (f"  [{row['note']}]" if row["note"] else ""))

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results.append({"event_idx": event_idx, "ticker": raw_ticker, "spike_week": ev["spike_week"],
                         "note": f"exception: {e}"})

results_df = pd.DataFrame(results)
print(f"\nTotal checkpoint rows: {len(results_df)}")
usable = results_df[results_df.get("cost_pct_of_spot").notna()] if "cost_pct_of_spot" in results_df.columns else pd.DataFrame()
print(f"Usable checkpoint rows: {len(usable)}")
print(f"Events with at least one usable checkpoint: {usable['event_idx'].nunique() if not usable.empty else 0} / {len(EMBEDDED_SAMPLE)}")

display(results_df)

# To export for local lead/lag analysis:
# results_df.to_csv("QC_IVLeadLag_RawSeries.csv", index=False)
