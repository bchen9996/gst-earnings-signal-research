# ============================================================================
# ATTENTION SPREAD -- OUT-OF-SAMPLE CONFIRMATORY PULL. Tests whether the
# tercile pattern found on the 76-event sample
# (Live Signal Engine/AttentionSpread_Analysis.csv: high-tercile win rate
# 56.0% / median return +7.89% vs. low-tercile 30.8% / -32.70%,
# Mann-Whitney p=0.039) replicates on a fresh, disjoint sample.
#
# SAMPLE: n=45, ticker-proportional stratified random, seed=314, drawn from
# the 152-event canonical population MINUS the 76 events already used to
# build/test Attention Spread (Live Signal Engine/
# QC_Validation_CleanSample_v2_76Events.csv). NOT disjoint from Candidate
# A/B or the C5 test's samples -- the 152-event canonical population is
# fully saturated by the union of every prior real-quote pull tonight (0
# events untouched by all five), so a full blind holdout is not possible.
# This is the least-contaminated feasible relaxation: these 45 events have
# real quotes pulled before for OTHER tests, but Attention Spread itself
# has never been computed or tercile-tested on them.
#
# SAME proven methodology as QC_Options_Validation_Script_v2_Expanded.py
# (the script that produced the original 76-event sample): first listed
# expiration on/after exit_date, ATM strike closest to entry-day close,
# real quoted ask at entry / bid at exit, $0.65/contract x 4 legs fee,
# 25%-of-spot automated corruption filter. Copied here, not
# reimplemented from scratch, to avoid any methodology drift between the
# original sample and this confirmatory one.
#
# THIS SCRIPT ONLY PULLS REAL QUOTES AND COMPUTES real_cost_pct_of_spot /
# real_pnl_pct -- it does NOT compute Attention Spread, does NOT apply
# tercile cutpoints, and does NOT run the Mann-Whitney test. That happens
# locally, using the ORIGINAL 76-event sample's tercile cutpoints
# (0.968673 / 1.344624, from Live Signal Engine/AttentionSpread_Analysis.csv)
# applied AS-IS to this new sample, not re-optimized -- per explicit
# instruction, this is confirmatory only.
#
# HOW TO USE: paste this entire file into an empty cell in your
# QuantConnect Research notebook and run it. No file upload needed.
# ============================================================================

import math
import pandas as pd
from datetime import timedelta
from QuantConnect.Research import QuantBook

qb = QuantBook()

# ---------------------------------------------------------------------------
# CONFIG -- identical constants to QC_Options_Validation_Script_v2_Expanded.py
# ---------------------------------------------------------------------------
TICKER_OVERRIDES = {"BRK-B": "BRK.B"}
FEE_PER_CONTRACT_USD = 0.65
FEE_LEGS = 4
FEES_IN_QUOTE_UNITS = (FEE_PER_CONTRACT_USD * FEE_LEGS) / 100.0
MAX_PLAUSIBLE_COST_PCT_OF_SPOT = 25.0   # automated corruption filter, same threshold/reasoning as prior pulls

# ---------------------------------------------------------------------------
# EMBEDDED_SAMPLE -- generated programmatically from
# Live Signal Engine/AttentionSpread_OOS_LockedSample.csv (not hand-typed).
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "AAPL", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 5.7387, "modeled_pnl_pct": 83.80, "modeled_win": True},
    {"ticker": "ADBE", "spike_week": "2024-03-10", "entry_date": "2024-03-12", "exit_date": "2024-03-15", "zscore": 8.7884, "modeled_pnl_pct": -19.79, "modeled_win": False},
    {"ticker": "ADBE", "spike_week": "2024-06-09", "entry_date": "2024-06-11", "exit_date": "2024-06-14", "zscore": 8.9431, "modeled_pnl_pct": -21.02, "modeled_win": False},
    {"ticker": "ADBE", "spike_week": "2024-12-08", "entry_date": "2024-12-10", "exit_date": "2024-12-13", "zscore": 14.6653, "modeled_pnl_pct": 27.20, "modeled_win": True},
    {"ticker": "ADBE", "spike_week": "2025-09-07", "entry_date": "2025-09-09", "exit_date": "2025-09-12", "zscore": 16.9269, "modeled_pnl_pct": -12.85, "modeled_win": False},
    {"ticker": "AMZN", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "zscore": 7.2373, "modeled_pnl_pct": 106.85, "modeled_win": True},
    {"ticker": "AMZN", "spike_week": "2025-10-26", "entry_date": "2025-10-28", "exit_date": "2025-10-31", "zscore": 8.7855, "modeled_pnl_pct": 47.14, "modeled_win": True},
    {"ticker": "BKR", "spike_week": "2022-01-16", "entry_date": "2022-01-18", "exit_date": "2022-01-21", "zscore": 9.7434, "modeled_pnl_pct": -8.31, "modeled_win": False},
    {"ticker": "COHR", "spike_week": "2024-08-11", "entry_date": "2024-08-13", "exit_date": "2024-08-16", "zscore": 5.4132, "modeled_pnl_pct": 145.02, "modeled_win": True},
    {"ticker": "CTSH", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "zscore": 5.5886, "modeled_pnl_pct": -34.11, "modeled_win": False},
    {"ticker": "DELL", "spike_week": "2021-08-22", "entry_date": "2021-08-24", "exit_date": "2021-08-27", "zscore": 10.6750, "modeled_pnl_pct": 39.62, "modeled_win": True},
    {"ticker": "GME", "spike_week": "2023-03-19", "entry_date": "2023-03-21", "exit_date": "2023-03-24", "zscore": 8.5408, "modeled_pnl_pct": 213.45, "modeled_win": True},
    {"ticker": "GOOGL", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "exit_date": "2023-10-27", "zscore": 7.0455, "modeled_pnl_pct": -61.27, "modeled_win": False},
    {"ticker": "GPN", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "zscore": 5.8377, "modeled_pnl_pct": -29.84, "modeled_win": False},
    {"ticker": "INTC", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "exit_date": "2023-01-27", "zscore": 8.8728, "modeled_pnl_pct": 288.66, "modeled_win": True},
    {"ticker": "LDOS", "spike_week": "2023-10-29", "entry_date": "2023-10-31", "exit_date": "2023-11-03", "zscore": 5.5514, "modeled_pnl_pct": -44.22, "modeled_win": False},
    {"ticker": "MSFT", "spike_week": "2021-10-24", "entry_date": "2021-10-26", "exit_date": "2021-10-29", "zscore": 9.5574, "modeled_pnl_pct": 21.35, "modeled_win": True},
    {"ticker": "MSFT", "spike_week": "2022-04-24", "entry_date": "2022-04-26", "exit_date": "2022-04-29", "zscore": 6.5625, "modeled_pnl_pct": -12.44, "modeled_win": False},
    {"ticker": "MSFT", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "exit_date": "2023-10-27", "zscore": 8.2717, "modeled_pnl_pct": -3.91, "modeled_win": False},
    {"ticker": "MSFT", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 13.3765, "modeled_pnl_pct": 55.20, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "exit_date": "2021-07-23", "zscore": 10.2794, "modeled_pnl_pct": 28.95, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "exit_date": "2021-10-22", "zscore": 15.2739, "modeled_pnl_pct": 81.17, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2022-04-17", "entry_date": "2022-04-19", "exit_date": "2022-04-22", "zscore": 13.6261, "modeled_pnl_pct": 478.78, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2022-10-16", "entry_date": "2022-10-18", "exit_date": "2022-10-21", "zscore": 16.4636, "modeled_pnl_pct": 299.99, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2023-04-16", "entry_date": "2023-04-18", "exit_date": "2023-04-21", "zscore": 7.5055, "modeled_pnl_pct": -55.65, "modeled_win": False},
    {"ticker": "NFLX", "spike_week": "2024-07-14", "entry_date": "2024-07-16", "exit_date": "2024-07-19", "zscore": 13.6586, "modeled_pnl_pct": 21.67, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "exit_date": "2024-10-18", "zscore": 17.0766, "modeled_pnl_pct": 289.00, "modeled_win": True},
    {"ticker": "NFLX", "spike_week": "2025-07-13", "entry_date": "2025-07-15", "exit_date": "2025-07-18", "zscore": 5.4542, "modeled_pnl_pct": -28.41, "modeled_win": False},
    {"ticker": "NFLX", "spike_week": "2025-10-19", "entry_date": "2025-10-21", "exit_date": "2025-10-24", "zscore": 8.9863, "modeled_pnl_pct": 64.83, "modeled_win": True},
    {"ticker": "NKE", "spike_week": "2022-06-26", "entry_date": "2022-06-28", "exit_date": "2022-07-01", "zscore": 13.4434, "modeled_pnl_pct": 12.83, "modeled_win": True},
    {"ticker": "NKE", "spike_week": "2022-09-25", "entry_date": "2022-09-27", "exit_date": "2022-09-30", "zscore": 22.5318, "modeled_pnl_pct": -78.11, "modeled_win": False},
    {"ticker": "NKE", "spike_week": "2025-03-16", "entry_date": "2025-03-18", "exit_date": "2025-03-21", "zscore": 9.3732, "modeled_pnl_pct": 92.47, "modeled_win": True},
    {"ticker": "NVDA", "spike_week": "2022-02-13", "entry_date": "2022-02-15", "exit_date": "2022-02-18", "zscore": 6.1675, "modeled_pnl_pct": 96.10, "modeled_win": True},
    {"ticker": "NVDA", "spike_week": "2022-05-22", "entry_date": "2022-05-24", "exit_date": "2022-05-27", "zscore": 5.8399, "modeled_pnl_pct": 141.37, "modeled_win": True},
    {"ticker": "NVDA", "spike_week": "2023-11-19", "entry_date": "2023-11-21", "exit_date": "2023-11-24", "zscore": 5.5047, "modeled_pnl_pct": 33.82, "modeled_win": True},
    {"ticker": "QCOM", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "zscore": 7.0749, "modeled_pnl_pct": -22.87, "modeled_win": False},
    {"ticker": "QCOM", "spike_week": "2024-11-03", "entry_date": "2024-11-05", "exit_date": "2024-11-08", "zscore": 6.0433, "modeled_pnl_pct": 71.29, "modeled_win": True},
    {"ticker": "SBUX", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.6479, "modeled_pnl_pct": -41.55, "modeled_win": False},
    {"ticker": "SBUX", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 13.2358, "modeled_pnl_pct": -19.62, "modeled_win": False},
    {"ticker": "STZ", "spike_week": "2025-01-05", "entry_date": "2025-01-07", "exit_date": "2025-01-08", "zscore": 11.7801, "modeled_pnl_pct": 176.03, "modeled_win": True},
    {"ticker": "SYK", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-30", "zscore": 8.2860, "modeled_pnl_pct": 68.91, "modeled_win": True},
    {"ticker": "TSLA", "spike_week": "2024-01-21", "entry_date": "2024-01-23", "exit_date": "2024-01-26", "zscore": 7.5137, "modeled_pnl_pct": -33.68, "modeled_win": False},
    {"ticker": "TTWO", "spike_week": "2023-11-05", "entry_date": "2023-11-07", "exit_date": "2023-11-10", "zscore": 27.4501, "modeled_pnl_pct": 386.89, "modeled_win": True},
    {"ticker": "TTWO", "spike_week": "2025-02-02", "entry_date": "2025-02-04", "exit_date": "2025-02-06", "zscore": 9.4169, "modeled_pnl_pct": 48.05, "modeled_win": True},
    {"ticker": "UAL", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "exit_date": "2024-10-18", "zscore": 7.2832, "modeled_pnl_pct": -35.71, "modeled_win": False},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])
print(f"Out-of-sample confirmatory pull: n={len(sample)}  tickers={sample['ticker'].nunique()}")


# ---------------------------------------------------------------------------
# HELPERS -- identical to QC_Options_Validation_Script_v2_Expanded.py
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
# MAIN PER-EVENT LOOP -- identical structure/logic to the v2 script
# ---------------------------------------------------------------------------
results = []

for idx, row in sample.iterrows():
    raw_ticker = row["ticker"]
    qc_ticker = TICKER_OVERRIDES.get(raw_ticker, raw_ticker)
    entry_date = row["entry_date"].to_pydatetime()
    exit_date = row["exit_date"].to_pydatetime()

    rec = {"ticker": raw_ticker, "spike_week": row["spike_week"].date(),
           "entry_date": entry_date.date(), "exit_date": exit_date.date(),
           "zscore": float(row["zscore"]), "modeled_pnl_pct": float(row["modeled_pnl_pct"]),
           "modeled_win": bool(row["modeled_win"]), "corrupted": False, "note": ""}

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
        rec["entry_underlying_price"] = entry_underlying_price

        contracts = list(qb.OptionChainProvider.GetOptionContractList(equity_symbol, entry_date))
        if not contracts:
            rec["note"] = "no option chain listed at entry date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        expiries = sorted(set(c.ID.Date for c in contracts if c.ID.Date >= exit_date))
        if not expiries:
            rec["note"] = "no listed expiration on/after exit date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        target_expiry = expiries[0]
        rec["expiry"] = target_expiry.date()

        same_expiry = [c for c in contracts if c.ID.Date == target_expiry]
        strikes = sorted(set(c.ID.StrikePrice for c in same_expiry))
        if not strikes:
            rec["note"] = "no strikes found for chosen expiration"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue
        atm_strike = min(strikes, key=lambda k: abs(k - entry_underlying_price))
        rec["strike"] = atm_strike

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
        call_exit_bid, call_exit_ask = get_bid_ask(call_symbol, exit_date)
        put_exit_bid, put_exit_ask = get_bid_ask(put_symbol, exit_date)

        missing = [v is None for v in [call_entry_ask, put_entry_ask, call_exit_bid, put_exit_bid]]
        if any(missing):
            rec["note"] = "missing real quote data at entry or exit"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        entry_cost = call_entry_ask + put_entry_ask
        exit_value = call_exit_bid + put_exit_bid
        real_pnl_pct = (exit_value - entry_cost - FEES_IN_QUOTE_UNITS) / entry_cost * 100
        real_win = real_pnl_pct > 0
        real_cost_pct_of_spot = entry_cost / entry_underlying_price * 100

        if real_cost_pct_of_spot > MAX_PLAUSIBLE_COST_PCT_OF_SPOT:
            rec["corrupted"] = True
            rec["real_cost_pct_of_spot"] = round(real_cost_pct_of_spot, 3)
            rec["note"] = (f"EXCLUDED: implausible real_cost_pct_of_spot="
                            f"{real_cost_pct_of_spot:.1f}% (> {MAX_PLAUSIBLE_COST_PCT_OF_SPOT}% threshold)")
            results.append(rec)
            print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        rec.update({
            "call_entry_ask": call_entry_ask, "put_entry_ask": put_entry_ask,
            "call_exit_bid": call_exit_bid, "put_exit_bid": put_exit_bid,
            "real_entry_cost": entry_cost, "real_exit_value": exit_value,
            "real_pnl_pct": round(real_pnl_pct, 2), "real_win": real_win,
            "real_cost_pct_of_spot": round(real_cost_pct_of_spot, 3),
        })
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: "
              f"real_pnl={real_pnl_pct:.1f}%  cost%spot={real_cost_pct_of_spot:.2f}%")

    except Exception as e:
        rec["note"] = f"exception: {e}"
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: EXCEPTION: {e}")

results_df = pd.DataFrame(results)
n_corrupted = int(results_df["corrupted"].sum())
complete = results_df[results_df.get("real_pnl_pct").notna() & (~results_df["corrupted"])].copy()

print(f"\nSample: {len(sample)}   Auto-flagged corrupted: {n_corrupted}   "
      f"Clean + priced: {len(complete)}   Failed/incomplete (other): {len(sample) - len(complete) - n_corrupted}")

display(results_df)

# To export for local Attention Spread tercile analysis:
# results_df.to_csv("QC_AttentionSpread_OOS_RawResults.csv", index=False)
