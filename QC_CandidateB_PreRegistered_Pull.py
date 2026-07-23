# ============================================================================
# CANDIDATE B PRE-REGISTERED TEST -- pre-earnings IV expansion trade. Real
# QuantConnect quote pull for the 59-event sample locked in
# Live Signal Engine/CandidateB_PreRegistration.md BEFORE this script was
# run. Do not add metrics or reinterpret results beyond what that file
# specifies.
#
# MECHANISM UNDER TEST (different from every prior real-quote test
# tonight): enter at the GST signal, exit BEFORE the earnings
# announcement -- never holding through it. This is a NEW kind of pull:
# every prior test only ever observed a POST-earnings exit price. Here,
# the exit quote is pulled at `pre_earnings_exit_date` (the trading day
# immediately before the earnings announcement -- i.e. the trading day
# immediately before this project's usual post-earnings exit_date),
# not at the usual post-earnings exit_date.
#
# Sample: all 35 available z>=10 events (untouched by Candidate A) + 24
# randomly-selected 5<=z<10 events (seed=123), none of which appeared in
# Candidate A's pre-registered pull. (May overlap with the earlier two
# ticker-stratified pulls -- deliberate, see CandidateB_PreRegistration.md
# section 2: those pulls never observed pre-earnings prices for any event,
# so this is still a genuinely new observation for every event here.)
#
# Same proven contract-selection methodology as every prior pull:
# History<QuoteBar>, ATM strike (closest to entry-day close), first
# expiration on/after the ORIGINAL post-earnings exit_date (contract
# selection is unchanged -- only the EXIT TIMING differs), automated
# corruption filter (real_cost_pct_of_spot > 25% of spot -> flagged/
# excluded), $0.65/contract x 4 legs fee assumption.
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
FEE_PER_CONTRACT_USD = 0.65
FEE_LEGS = 4
FEES_IN_QUOTE_UNITS = (FEE_PER_CONTRACT_USD * FEE_LEGS) / 100.0

MAX_PLAUSIBLE_COST_PCT_OF_SPOT = 25.0
FLAT_POSITION_SIZE = 10_000.0
STARTING_CAPITAL = 100_000.0

TICKER_OVERRIDES = {"BRK-B": "BRK.B"}

# ---------------------------------------------------------------------------
# PRE-REGISTERED SAMPLE (n=59) -- locked in CandidateB_PreRegistration.md
# BEFORE this script was run. All 35 available z>=10 events (untouched by
# Candidate A) + 24 randomly-sampled 5<=z<10 events (seed=123).
#
# NOTE: contract selection still uses the ORIGINAL post-earnings exit_date
# to pick "first expiration on/after" (unchanged from prior pulls, see
# pre-registration doc section 3) -- that date is recomputed below from
# pre_earnings_exit_date + 1 trading day is NOT reliable in general
# (calendar gaps), so the original exit_date is embedded directly too.
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "AAPL", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "pre_earnings_exit_date": "2023-05-04", "orig_exit_date": "2023-05-05", "zscore": 7.2824, "tier": "5<=z<10"},
    {"ticker": "ABBV", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "pre_earnings_exit_date": "2024-10-31", "orig_exit_date": "2024-11-01", "zscore": 6.6894, "tier": "5<=z<10"},
    {"ticker": "ADBE", "spike_week": "2022-09-11", "entry_date": "2022-09-13", "pre_earnings_exit_date": "2022-09-15", "orig_exit_date": "2022-09-16", "zscore": 24.1066, "tier": "z>=10"},
    {"ticker": "ADBE", "spike_week": "2023-03-12", "entry_date": "2023-03-14", "pre_earnings_exit_date": "2023-03-16", "orig_exit_date": "2023-03-17", "zscore": 6.1013, "tier": "5<=z<10"},
    {"ticker": "ADBE", "spike_week": "2023-12-10", "entry_date": "2023-12-12", "pre_earnings_exit_date": "2023-12-14", "orig_exit_date": "2023-12-15", "zscore": 15.6618, "tier": "z>=10"},
    {"ticker": "ADBE", "spike_week": "2024-03-10", "entry_date": "2024-03-12", "pre_earnings_exit_date": "2024-03-14", "orig_exit_date": "2024-03-15", "zscore": 8.7884, "tier": "5<=z<10"},
    {"ticker": "AMZN", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "pre_earnings_exit_date": "2025-07-31", "orig_exit_date": "2025-08-01", "zscore": 5.1145, "tier": "5<=z<10"},
    {"ticker": "BKR", "spike_week": "2025-07-20", "entry_date": "2025-07-22", "pre_earnings_exit_date": "2025-07-24", "orig_exit_date": "2025-07-25", "zscore": 11.4518, "tier": "z>=10"},
    {"ticker": "COHR", "spike_week": "2024-02-04", "entry_date": "2024-02-06", "pre_earnings_exit_date": "2024-02-08", "orig_exit_date": "2024-02-09", "zscore": 11.4444, "tier": "z>=10"},
    {"ticker": "CTSH", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "pre_earnings_exit_date": "2022-11-03", "orig_exit_date": "2022-11-04", "zscore": 7.8797, "tier": "5<=z<10"},
    {"ticker": "DELL", "spike_week": "2025-11-30", "entry_date": "2025-12-02", "pre_earnings_exit_date": "2025-12-04", "orig_exit_date": "2025-12-05", "zscore": 5.8041, "tier": "5<=z<10"},
    {"ticker": "DVN", "spike_week": "2023-02-12", "entry_date": "2023-02-14", "pre_earnings_exit_date": "2023-02-16", "orig_exit_date": "2023-02-17", "zscore": 10.279, "tier": "z>=10"},
    {"ticker": "GPN", "spike_week": "2021-08-01", "entry_date": "2021-08-03", "pre_earnings_exit_date": "2021-08-05", "orig_exit_date": "2021-08-06", "zscore": 13.574, "tier": "z>=10"},
    {"ticker": "GPN", "spike_week": "2024-08-04", "entry_date": "2024-08-06", "pre_earnings_exit_date": "2024-08-08", "orig_exit_date": "2024-08-09", "zscore": 5.2022, "tier": "5<=z<10"},
    {"ticker": "INTC", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "pre_earnings_exit_date": "2023-01-26", "orig_exit_date": "2023-01-27", "zscore": 8.8728, "tier": "5<=z<10"},
    {"ticker": "LDOS", "spike_week": "2023-10-29", "entry_date": "2023-10-31", "pre_earnings_exit_date": "2023-11-02", "orig_exit_date": "2023-11-03", "zscore": 5.5514, "tier": "5<=z<10"},
    {"ticker": "MSFT", "spike_week": "2022-01-23", "entry_date": "2022-01-25", "pre_earnings_exit_date": "2022-01-27", "orig_exit_date": "2022-01-28", "zscore": 13.478, "tier": "z>=10"},
    {"ticker": "MSFT", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "pre_earnings_exit_date": "2022-10-27", "orig_exit_date": "2022-10-28", "zscore": 13.1069, "tier": "z>=10"},
    {"ticker": "MSFT", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "pre_earnings_exit_date": "2023-01-26", "orig_exit_date": "2023-01-27", "zscore": 11.7806, "tier": "z>=10"},
    {"ticker": "MSFT", "spike_week": "2023-04-23", "entry_date": "2023-04-25", "pre_earnings_exit_date": "2023-04-27", "orig_exit_date": "2023-04-28", "zscore": 7.3757, "tier": "5<=z<10"},
    {"ticker": "MSFT", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "pre_earnings_exit_date": "2023-10-26", "orig_exit_date": "2023-10-27", "zscore": 8.2717, "tier": "5<=z<10"},
    {"ticker": "MSFT", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "pre_earnings_exit_date": "2025-01-30", "orig_exit_date": "2025-01-31", "zscore": 11.4508, "tier": "z>=10"},
    {"ticker": "MSFT", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "pre_earnings_exit_date": "2025-07-31", "orig_exit_date": "2025-08-01", "zscore": 13.3765, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "pre_earnings_exit_date": "2021-07-22", "orig_exit_date": "2021-07-23", "zscore": 10.2794, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "pre_earnings_exit_date": "2021-10-21", "orig_exit_date": "2021-10-22", "zscore": 15.2739, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2022-01-16", "entry_date": "2022-01-18", "pre_earnings_exit_date": "2022-01-20", "orig_exit_date": "2022-01-21", "zscore": 31.0985, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2022-04-17", "entry_date": "2022-04-19", "pre_earnings_exit_date": "2022-04-21", "orig_exit_date": "2022-04-22", "zscore": 13.6261, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2022-10-16", "entry_date": "2022-10-18", "pre_earnings_exit_date": "2022-10-20", "orig_exit_date": "2022-10-21", "zscore": 16.4636, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2023-07-16", "entry_date": "2023-07-18", "pre_earnings_exit_date": "2023-07-20", "orig_exit_date": "2023-07-21", "zscore": 15.8142, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2024-07-14", "entry_date": "2024-07-16", "pre_earnings_exit_date": "2024-07-18", "orig_exit_date": "2024-07-19", "zscore": 13.6586, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "pre_earnings_exit_date": "2024-10-17", "orig_exit_date": "2024-10-18", "zscore": 17.0766, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2025-01-19", "entry_date": "2025-01-21", "pre_earnings_exit_date": "2025-01-23", "orig_exit_date": "2025-01-24", "zscore": 12.7874, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2021-06-20", "entry_date": "2021-06-22", "pre_earnings_exit_date": "2021-06-24", "orig_exit_date": "2021-06-25", "zscore": 11.9064, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2022-03-20", "entry_date": "2022-03-22", "pre_earnings_exit_date": "2022-03-24", "orig_exit_date": "2022-03-25", "zscore": 10.4459, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2023-06-25", "entry_date": "2023-06-27", "pre_earnings_exit_date": "2023-06-29", "orig_exit_date": "2023-06-30", "zscore": 11.2982, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2024-03-17", "entry_date": "2024-03-19", "pre_earnings_exit_date": "2024-03-21", "orig_exit_date": "2024-03-22", "zscore": 10.7769, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2024-06-23", "entry_date": "2024-06-25", "pre_earnings_exit_date": "2024-06-27", "orig_exit_date": "2024-06-28", "zscore": 22.4678, "tier": "z>=10"},
    {"ticker": "NVDA", "spike_week": "2023-05-21", "entry_date": "2023-05-23", "pre_earnings_exit_date": "2023-05-25", "orig_exit_date": "2023-05-26", "zscore": 17.1935, "tier": "z>=10"},
    {"ticker": "NVDA", "spike_week": "2023-08-20", "entry_date": "2023-08-22", "pre_earnings_exit_date": "2023-08-24", "orig_exit_date": "2023-08-25", "zscore": 9.4449, "tier": "5<=z<10"},
    {"ticker": "QCOM", "spike_week": "2021-10-31", "entry_date": "2021-11-02", "pre_earnings_exit_date": "2021-11-04", "orig_exit_date": "2021-11-05", "zscore": 18.6841, "tier": "z>=10"},
    {"ticker": "QCOM", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "pre_earnings_exit_date": "2023-05-04", "orig_exit_date": "2023-05-05", "zscore": 10.5713, "tier": "z>=10"},
    {"ticker": "QCOM", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "pre_earnings_exit_date": "2024-02-01", "orig_exit_date": "2024-02-02", "zscore": 7.0749, "tier": "5<=z<10"},
    {"ticker": "QCOM", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "pre_earnings_exit_date": "2025-07-31", "orig_exit_date": "2025-08-01", "zscore": 12.3111, "tier": "z>=10"},
    {"ticker": "SBUX", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "pre_earnings_exit_date": "2023-05-04", "orig_exit_date": "2023-05-05", "zscore": 12.306, "tier": "z>=10"},
    {"ticker": "SBUX", "spike_week": "2024-04-28", "entry_date": "2024-04-30", "pre_earnings_exit_date": "2024-05-02", "orig_exit_date": "2024-05-03", "zscore": 26.7718, "tier": "z>=10"},
    {"ticker": "SBUX", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "pre_earnings_exit_date": "2025-01-30", "orig_exit_date": "2025-01-31", "zscore": 13.6492, "tier": "z>=10"},
    {"ticker": "SBUX", "spike_week": "2025-04-27", "entry_date": "2025-04-29", "pre_earnings_exit_date": "2025-05-01", "orig_exit_date": "2025-05-02", "zscore": 5.5662, "tier": "5<=z<10"},
    {"ticker": "STZ", "spike_week": "2023-01-01", "entry_date": "2022-12-30", "pre_earnings_exit_date": "2023-01-05", "orig_exit_date": "2023-01-06", "zscore": 5.9029, "tier": "5<=z<10"},
    {"ticker": "STZ", "spike_week": "2024-04-07", "entry_date": "2024-04-09", "pre_earnings_exit_date": "2024-04-11", "orig_exit_date": "2024-04-12", "zscore": 10.1959, "tier": "z>=10"},
    {"ticker": "STZ", "spike_week": "2025-01-05", "entry_date": "2025-01-07", "pre_earnings_exit_date": "2025-01-08", "orig_exit_date": "2025-01-10", "zscore": 11.7801, "tier": "z>=10"},
    {"ticker": "SYK", "spike_week": "2023-01-29", "entry_date": "2023-01-31", "pre_earnings_exit_date": "2023-02-02", "orig_exit_date": "2023-02-03", "zscore": 7.2622, "tier": "5<=z<10"},
    {"ticker": "SYK", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "pre_earnings_exit_date": "2024-02-01", "orig_exit_date": "2024-02-02", "zscore": 8.6168, "tier": "5<=z<10"},
    {"ticker": "SYK", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "pre_earnings_exit_date": "2025-07-31", "orig_exit_date": "2025-08-01", "zscore": 5.2274, "tier": "5<=z<10"},
    {"ticker": "TSLA", "spike_week": "2024-04-21", "entry_date": "2024-04-23", "pre_earnings_exit_date": "2024-04-25", "orig_exit_date": "2024-04-26", "zscore": 5.5972, "tier": "5<=z<10"},
    {"ticker": "TTWO", "spike_week": "2021-05-16", "entry_date": "2021-05-18", "pre_earnings_exit_date": "2021-05-20", "orig_exit_date": "2021-05-21", "zscore": 8.3187, "tier": "5<=z<10"},
    {"ticker": "TTWO", "spike_week": "2022-11-06", "entry_date": "2022-11-08", "pre_earnings_exit_date": "2022-11-10", "orig_exit_date": "2022-11-11", "zscore": 8.0837, "tier": "5<=z<10"},
    {"ticker": "TTWO", "spike_week": "2023-05-14", "entry_date": "2023-05-16", "pre_earnings_exit_date": "2023-05-18", "orig_exit_date": "2023-05-19", "zscore": 12.5688, "tier": "z>=10"},
    {"ticker": "TTWO", "spike_week": "2024-05-12", "entry_date": "2024-05-14", "pre_earnings_exit_date": "2024-05-16", "orig_exit_date": "2024-05-17", "zscore": 8.5275, "tier": "5<=z<10"},
    {"ticker": "UAL", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "pre_earnings_exit_date": "2021-07-22", "orig_exit_date": "2021-07-23", "zscore": 5.5255, "tier": "5<=z<10"},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["pre_earnings_exit_date"] = pd.to_datetime(sample["pre_earnings_exit_date"])
sample["orig_exit_date"] = pd.to_datetime(sample["orig_exit_date"])

print(f"Pre-registered sample: n={len(sample)}  "
      f"({(sample['tier']=='z>=10').sum()} z>=10, {(sample['tier']=='5<=z<10').sum()} 5<=z<10)")

# ---------------------------------------------------------------------------
# REAL-QUOTE PULL HELPERS
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


# ---------------------------------------------------------------------------
# MAIN PER-EVENT LOOP
# ---------------------------------------------------------------------------
results = []

for idx, row in sample.iterrows():
    raw_ticker = row["ticker"]
    qc_ticker = TICKER_OVERRIDES.get(raw_ticker, raw_ticker)
    entry_date = row["entry_date"].to_pydatetime()
    pre_earnings_exit_date = row["pre_earnings_exit_date"].to_pydatetime()
    orig_exit_date = row["orig_exit_date"].to_pydatetime()  # contract selection only, NOT the exit timing

    rec = {"ticker": raw_ticker, "spike_week": row["spike_week"].date(), "zscore": row["zscore"],
           "tier": row["tier"], "entry_date": entry_date.date(),
           "pre_earnings_exit_date": pre_earnings_exit_date.date(),
           "corrupted": False, "note": ""}

    try:
        equity = qb.AddEquity(qc_ticker, Resolution.Daily)
        equity_symbol = equity.Symbol

        px_hist = qb.History(equity_symbol, entry_date - timedelta(days=7), entry_date + timedelta(days=1),
                              Resolution.Daily)
        if px_hist is None or px_hist.empty:
            rec["note"] = "no underlying price history at entry"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        entry_underlying_price = float(px_hist["close"].iloc[-1])

        contracts = list(qb.OptionChainProvider.GetOptionContractList(equity_symbol, entry_date))
        if not contracts:
            rec["note"] = "no option chain listed at entry date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        # Contract selection is UNCHANGED from prior pulls: first expiration
        # on/after the ORIGINAL post-earnings exit_date -- only the EXIT
        # TIMING (below) differs for this test.
        expiries = sorted(set(c.ID.Date for c in contracts if c.ID.Date >= orig_exit_date))
        if not expiries:
            rec["note"] = "no listed expiration on/after original exit date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        target_expiry = expiries[0]

        same_expiry = [c for c in contracts if c.ID.Date == target_expiry]
        strikes = sorted(set(c.ID.StrikePrice for c in same_expiry))
        if not strikes:
            rec["note"] = "no strikes found for chosen expiration"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        atm_strike = min(strikes, key=lambda k: abs(k - entry_underlying_price))

        call_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                             and c.ID.OptionRight == OptionRight.Call), None)
        put_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                            and c.ID.OptionRight == OptionRight.Put), None)
        if call_symbol is None or put_symbol is None:
            rec["note"] = "missing call or put contract at chosen strike/expiry"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        call_entry_bid, call_entry_ask = get_bid_ask(call_symbol, entry_date)
        put_entry_bid, put_entry_ask = get_bid_ask(put_symbol, entry_date)
        # KEY DIFFERENCE: exit quote pulled at pre_earnings_exit_date, not
        # the original post-earnings exit_date.
        call_exit_bid, call_exit_ask = get_bid_ask(call_symbol, pre_earnings_exit_date)
        put_exit_bid, put_exit_ask = get_bid_ask(put_symbol, pre_earnings_exit_date)

        missing = [v is None for v in [call_entry_ask, put_entry_ask, call_exit_bid, put_exit_bid]]
        if any(missing):
            rec["note"] = "missing real quote data at entry or pre-earnings exit"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        entry_cost = call_entry_ask + put_entry_ask
        exit_value = call_exit_bid + put_exit_bid
        real_cost_pct_of_spot = entry_cost / entry_underlying_price * 100

        if real_cost_pct_of_spot > MAX_PLAUSIBLE_COST_PCT_OF_SPOT:
            rec["corrupted"] = True
            rec["real_cost_pct_of_spot"] = round(real_cost_pct_of_spot, 3)
            rec["note"] = (f"EXCLUDED: implausible real_cost_pct_of_spot="
                            f"{real_cost_pct_of_spot:.1f}% (> {MAX_PLAUSIBLE_COST_PCT_OF_SPOT}% threshold)")
            results.append(rec)
            print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        real_pnl_pct = (exit_value - entry_cost - FEES_IN_QUOTE_UNITS) / entry_cost * 100
        dollar_pnl = FLAT_POSITION_SIZE * (real_pnl_pct / 100.0)

        rec.update({
            "real_cost_pct_of_spot": round(real_cost_pct_of_spot, 3),
            "real_pnl_pct": round(real_pnl_pct, 2),
            "dollar_pnl": round(dollar_pnl, 2),
        })
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()} ({row['tier']}): "
              f"real_pnl={real_pnl_pct:.1f}%  ${dollar_pnl:,.0f}")

    except Exception as e:
        rec["note"] = f"exception: {e}"
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: EXCEPTION: {e}")

results_df = pd.DataFrame(results)

# ---------------------------------------------------------------------------
# PRE-REGISTERED DECISION RULE CHECK -- reported FIRST, exactly as specified
# in CandidateB_PreRegistration.md, before any other discussion.
# ---------------------------------------------------------------------------
def max_drawdown(equity_curve):
    running_max = np.maximum.accumulate(equity_curve)
    return float(((equity_curve - running_max) / running_max).min())


def tier_report(df, label):
    df = df[df["dollar_pnl"].notna()].sort_values("pre_earnings_exit_date").reset_index(drop=True)
    n = len(df)
    if n == 0:
        print(f"{label}: n=0, no usable events")
        return None

    mean_dollar_return = df["dollar_pnl"].mean()
    equity = STARTING_CAPITAL + df["dollar_pnl"].cumsum()
    equity_curve = np.concatenate([[STARTING_CAPITAL], equity.to_numpy()])
    mdd_pct = max_drawdown(equity_curve) * 100

    sorted_pnl = df["dollar_pnl"].sort_values()
    n10 = max(1, round(n * 0.10))
    n20 = max(1, round(n * 0.20))
    es_10 = sorted_pnl.iloc[:n10].mean()
    es_20 = sorted_pnl.iloc[:n20].mean()
    worst_dollar = df["dollar_pnl"].min()
    worst_pct = df["real_pnl_pct"].min()

    total_pnl = df["dollar_pnl"].sum()
    top20_pnl = sorted_pnl.iloc[-n20:].sum()
    pct_from_top20 = (top20_pnl / total_pnl * 100) if total_pnl != 0 else None

    print(f"\n=== {label} (n={n}) ===")
    print(f"  Mean $ return per $10,000 premium: ${mean_dollar_return:,.0f}")
    print(f"  Max drawdown: {mdd_pct:.1f}%")
    print(f"  Expected shortfall, worst 10%: ${es_10:,.0f}")
    print(f"  Expected shortfall, worst 20%: ${es_20:,.0f}")
    print(f"  Worst single trade: ${worst_dollar:,.0f} ({worst_pct:+.1f}%)")
    print(f"  Total net $ P&L: ${total_pnl:,.0f}")
    print(f"  % of profit from top 20% of events: {pct_from_top20:.1f}%" if pct_from_top20 is not None else "  n/a")

    return {"n": n, "mean_dollar_return": mean_dollar_return, "pct_from_top20": pct_from_top20,
            "max_drawdown_pct": mdd_pct, "es_10": es_10, "es_20": es_20,
            "worst_dollar": worst_dollar, "worst_pct": worst_pct, "total_pnl": total_pnl}


results_df.to_csv("CandidateB_PreRegistered_Results.csv", index=False)

high_stats = tier_report(results_df[results_df["tier"] == "z>=10"], "z>=10")

print("\n" + "=" * 70)
print("PRE-REGISTERED DECISION RULE CHECK (z>=10) -- stated in advance, binding")
print("=" * 70)
if high_stats:
    cond1 = high_stats["mean_dollar_return"] > 0
    cond2 = (high_stats["pct_from_top20"] is not None) and (high_stats["pct_from_top20"] < 100)
    print(f"Condition 1 (mean $ return positive): {high_stats['mean_dollar_return']:+,.0f} -> {'PASS' if cond1 else 'FAIL'}")
    print(f"Condition 2 (% profit from top 20% < 100%): {high_stats['pct_from_top20']:.1f}% -> {'PASS' if cond2 else 'FAIL'}")
    print(f"\nRESULT: z>=10 {'SHOWS REAL EDGE' if (cond1 and cond2) else 'DOES NOT SHOW REAL EDGE'} on this pre-registered test.")
else:
    print("No usable z>=10 events -- cannot evaluate decision rule.")

mid_stats = tier_report(results_df[results_df["tier"] == "5<=z<10"], "5<=z<10 (comparison, not part of decision rule)")

display(results_df)
