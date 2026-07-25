# ============================================================================
# HYPOTHESIS #5 (VOLATILITY MISPRICING) -- OUT-OF-SAMPLE CONFIRMATORY PULL.
# See Live Signal Engine/H5_OutOfSample_PreRegistration.md for the full
# locked methodology and binding decision rule this pull feeds.
#
# ORIGINAL FINDING UNDER TEST: r=0.407, n=76 (GST_VolatilitySurprise_Analysis.py,
# CHANGELOG.md's "volatility-surprise check" entry) -- z-score vs.
# volatility_surprise_pct = realized_move_pct - implied_move_pct.
#
# THIS PULL ONLY NEEDS implied_move_pct = real_cost_pct_of_spot, an
# ENTRY-ONLY quantity (real quoted ATM straddle ask cost as % of spot at
# entry_date). realized_move_pct is computed LOCALLY from existing daily
# excess-return data (same as the original test) -- no exit-side option
# quote is pulled here, unlike the full round-trip P&L pulls elsewhere in
# this project. Same contract-selection methodology as
# QC_Options_Validation_Script_v2_Expanded.py (first listed expiration
# on/after exit_date, ATM strike closest to entry-day close), narrowed to
# entry-side only.
#
# SAMPLE: n=45, ticker-proportional stratified random, seed=811, drawn
# from the 152-event canonical population minus the ORIGINAL 76-event
# sample's own (ticker, spike_week) keys (hard-excluded, not approximated).
# Disclosed in the pre-registration: 27 of these 45 events overlap with
# the separately-drawn Attention Spread OOS sample (expected by chance,
# same 76-event eligible pool) -- these two out-of-sample tests are not
# fully independent of each other.
#
# HOW TO USE: paste this entire file into an empty cell in your
# QuantConnect Research notebook and run it. No file upload needed.
# ============================================================================

import pandas as pd
from datetime import timedelta
from QuantConnect.Research import QuantBook

qb = QuantBook()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
TICKER_OVERRIDES = {"BRK-B": "BRK.B"}
MAX_PLAUSIBLE_COST_PCT_OF_SPOT = 25.0   # same automated corruption filter/threshold as prior pulls

# ---------------------------------------------------------------------------
# EMBEDDED_SAMPLE -- generated programmatically from
# Live Signal Engine/H5_OutOfSample_LockedSample.csv (not hand-typed).
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "AAPL", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 5.7387},
    {"ticker": "ADBE", "spike_week": "2022-03-20", "entry_date": "2022-03-22", "exit_date": "2022-03-25", "zscore": 6.9888},
    {"ticker": "ADBE", "spike_week": "2024-03-10", "entry_date": "2024-03-12", "exit_date": "2024-03-15", "zscore": 8.7884},
    {"ticker": "ADBE", "spike_week": "2024-06-09", "entry_date": "2024-06-11", "exit_date": "2024-06-14", "zscore": 8.9431},
    {"ticker": "ADBE", "spike_week": "2025-06-08", "entry_date": "2025-06-10", "exit_date": "2025-06-13", "zscore": 8.2885},
    {"ticker": "AMZN", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.5190},
    {"ticker": "AMZN", "spike_week": "2025-10-26", "entry_date": "2025-10-28", "exit_date": "2025-10-31", "zscore": 8.7855},
    {"ticker": "BKR", "spike_week": "2022-01-16", "entry_date": "2022-01-18", "exit_date": "2022-01-21", "zscore": 9.7434},
    {"ticker": "COHR", "spike_week": "2024-02-04", "entry_date": "2024-02-06", "exit_date": "2024-02-09", "zscore": 11.4444},
    {"ticker": "CTSH", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "zscore": 5.5886},
    {"ticker": "DELL", "spike_week": "2021-08-22", "entry_date": "2021-08-24", "exit_date": "2021-08-27", "zscore": 10.6750},
    {"ticker": "GME", "spike_week": "2024-03-24", "entry_date": "2024-03-26", "exit_date": "2024-03-28", "zscore": 5.7715},
    {"ticker": "GOOGL", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "exit_date": "2023-10-27", "zscore": 7.0455},
    {"ticker": "GPN", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "zscore": 5.8377},
    {"ticker": "INTC", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "exit_date": "2023-01-27", "zscore": 8.8728},
    {"ticker": "LDOS", "spike_week": "2023-10-29", "entry_date": "2023-10-31", "exit_date": "2023-11-03", "zscore": 5.5514},
    {"ticker": "MSFT", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.7949},
    {"ticker": "MSFT", "spike_week": "2021-10-24", "entry_date": "2021-10-26", "exit_date": "2021-10-29", "zscore": 9.5574},
    {"ticker": "MSFT", "spike_week": "2022-04-24", "entry_date": "2022-04-26", "exit_date": "2022-04-29", "zscore": 6.5625},
    {"ticker": "MSFT", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 13.3765},
    {"ticker": "NFLX", "spike_week": "2021-04-18", "entry_date": "2021-04-20", "exit_date": "2021-04-23", "zscore": 13.9663},
    {"ticker": "NFLX", "spike_week": "2021-07-18", "entry_date": "2021-07-20", "exit_date": "2021-07-23", "zscore": 10.2794},
    {"ticker": "NFLX", "spike_week": "2022-01-16", "entry_date": "2022-01-18", "exit_date": "2022-01-21", "zscore": 31.0985},
    {"ticker": "NFLX", "spike_week": "2022-04-17", "entry_date": "2022-04-19", "exit_date": "2022-04-22", "zscore": 13.6261},
    {"ticker": "NFLX", "spike_week": "2022-10-16", "entry_date": "2022-10-18", "exit_date": "2022-10-21", "zscore": 16.4636},
    {"ticker": "NFLX", "spike_week": "2023-04-16", "entry_date": "2023-04-18", "exit_date": "2023-04-21", "zscore": 7.5055},
    {"ticker": "NFLX", "spike_week": "2024-01-21", "entry_date": "2024-01-23", "exit_date": "2024-01-26", "zscore": 26.7917},
    {"ticker": "NFLX", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "exit_date": "2024-10-18", "zscore": 17.0766},
    {"ticker": "NFLX", "spike_week": "2025-07-13", "entry_date": "2025-07-15", "exit_date": "2025-07-18", "zscore": 5.4542},
    {"ticker": "NKE", "spike_week": "2021-12-19", "entry_date": "2021-12-21", "exit_date": "2021-12-23", "zscore": 5.7069},
    {"ticker": "NKE", "spike_week": "2022-06-26", "entry_date": "2022-06-28", "exit_date": "2022-07-01", "zscore": 13.4434},
    {"ticker": "NKE", "spike_week": "2023-03-19", "entry_date": "2023-03-21", "exit_date": "2023-03-24", "zscore": 12.2236},
    {"ticker": "NVDA", "spike_week": "2023-05-21", "entry_date": "2023-05-23", "exit_date": "2023-05-26", "zscore": 17.1935},
    {"ticker": "NVDA", "spike_week": "2023-08-20", "entry_date": "2023-08-22", "exit_date": "2023-08-25", "zscore": 9.4449},
    {"ticker": "NVDA", "spike_week": "2024-02-18", "entry_date": "2024-02-20", "exit_date": "2024-02-23", "zscore": 7.1643},
    {"ticker": "QCOM", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "zscore": 6.5667},
    {"ticker": "QCOM", "spike_week": "2024-11-03", "entry_date": "2024-11-05", "exit_date": "2024-11-08", "zscore": 6.0433},
    {"ticker": "SBUX", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.6479},
    {"ticker": "SBUX", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "zscore": 8.7049},
    {"ticker": "STZ", "spike_week": "2023-12-31", "entry_date": "2023-12-29", "exit_date": "2024-01-05", "zscore": 6.9317},
    {"ticker": "SYK", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-31", "zscore": 8.2860},
    {"ticker": "TSLA", "spike_week": "2024-01-21", "entry_date": "2024-01-23", "exit_date": "2024-01-26", "zscore": 7.5137},
    {"ticker": "TTWO", "spike_week": "2023-11-05", "entry_date": "2023-11-07", "exit_date": "2023-11-10", "zscore": 27.4501},
    {"ticker": "TTWO", "spike_week": "2024-05-12", "entry_date": "2024-05-14", "exit_date": "2024-05-17", "zscore": 8.5275},
    {"ticker": "UAL", "spike_week": "2024-10-13", "entry_date": "2024-10-15", "exit_date": "2024-10-18", "zscore": 7.2832},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])
print(f"H5 out-of-sample confirmatory pull: n={len(sample)}  tickers={sample['ticker'].nunique()}")


# ---------------------------------------------------------------------------
# HELPERS -- entry-side quote logic identical in spirit to
# QC_Options_Validation_Script_v2_Expanded.py, narrowed to entry-only.
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
# MAIN PER-EVENT LOOP -- entry-only (no exit quote needed for implied_move_pct)
# ---------------------------------------------------------------------------
results = []

for idx, row in sample.iterrows():
    raw_ticker = row["ticker"]
    qc_ticker = TICKER_OVERRIDES.get(raw_ticker, raw_ticker)
    entry_date = row["entry_date"].to_pydatetime()
    exit_date = row["exit_date"].to_pydatetime()

    rec = {"ticker": raw_ticker, "spike_week": row["spike_week"].date(),
           "entry_date": entry_date.date(), "exit_date": exit_date.date(),
           "zscore": float(row["zscore"]), "corrupted": False, "note": ""}

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

        if call_entry_ask is None or put_entry_ask is None:
            rec["note"] = "missing real entry quote data"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: {rec['note']}")
            continue

        entry_cost = call_entry_ask + put_entry_ask
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
            "real_entry_cost": entry_cost, "real_cost_pct_of_spot": round(real_cost_pct_of_spot, 3),
        })
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: "
              f"real_cost_pct_of_spot={real_cost_pct_of_spot:.2f}%")

    except Exception as e:
        rec["note"] = f"exception: {e}"
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: EXCEPTION: {e}")

results_df = pd.DataFrame(results)
n_corrupted = int(results_df["corrupted"].sum())
complete = results_df[results_df.get("real_cost_pct_of_spot").notna() & (~results_df["corrupted"])].copy()

print(f"\nSample: {len(sample)}   Auto-flagged corrupted: {n_corrupted}   "
      f"Clean + priced: {len(complete)}   Failed/incomplete (other): {len(sample) - len(complete) - n_corrupted}")

display(results_df)

# To export for local volatility-surprise correlation analysis:
# results_df.to_csv("QC_H5_OutOfSample_RawResults.csv", index=False)
