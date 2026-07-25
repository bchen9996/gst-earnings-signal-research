# ============================================================================
# HYPOTHESIS #5 (VOLATILITY MISPRICING) -- SUPPLEMENTAL OUT-OF-SAMPLE PULL.
# See Live Signal Engine/H5_OutOfSample_PreRegistration.md (original
# n=45/seed=811 draw) and its appended supplemental-draw note for the full
# locked methodology and binding decision rule this pull feeds.
#
# WHY THIS EXISTS: the original n=45 draw returned only 29 clean-and-priced
# events after auto-exclusion (15 implausible pricing >25%, 1 no option
# chain) -- below the effective floor needed for the n>=40 target once
# further attrition is accounted for. This pull covers the ENTIRE
# remaining untouched eligible pool (31 events: the 76-event eligible
# pool, minus the original 76-event H5 sample's own exclusion, minus the
# 45 already drawn) -- not a fresh random subsample. No seed is logged
# because none was used: since nothing is being left out of this draw,
# there is no selection to seed. Combined with the original 29 clean
# events, this targets >=40 total assuming a similar ~64% clean-pass rate
# (31 x 0.64 ~ 19.8 expected new clean, ~48.8 combined) -- comfortably
# above 40 even allowing for pass-rate variance, which is why the full
# remainder was drawn rather than a bare-minimum subset.
#
# SAME METHODOLOGY, UNCHANGED: entry-only real_cost_pct_of_spot (ATM
# straddle ask cost as % of spot at entry_date), same contract-selection
# rule as QC_Options_Validation_Script_v2_Expanded.py, same
# MAX_PLAUSIBLE_COST_PCT_OF_SPOT=25.0 corruption filter -- NOT relaxed or
# tuned for this supplemental draw, per explicit instruction that
# threshold is a data-quality filter, not a knob.
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
    {"ticker": "AAPL", "spike_week": "2023-01-29", "entry_date": "2023-01-31", "exit_date": "2023-02-03", "zscore": 6.6056},
    {"ticker": "ADBE", "spike_week": "2024-12-08", "entry_date": "2024-12-10", "exit_date": "2024-12-13", "zscore": 14.6653},
    {"ticker": "ADBE", "spike_week": "2025-09-07", "entry_date": "2025-09-09", "exit_date": "2025-09-12", "zscore": 16.9269},
    {"ticker": "AMZN", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "zscore": 7.2373},
    {"ticker": "AMZN", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 5.1145},
    {"ticker": "COHR", "spike_week": "2024-08-11", "entry_date": "2024-08-13", "exit_date": "2024-08-16", "zscore": 5.4132},
    {"ticker": "GME", "spike_week": "2023-03-19", "entry_date": "2023-03-21", "exit_date": "2023-03-24", "zscore": 8.5408},
    {"ticker": "GOOGL", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "exit_date": "2022-10-28", "zscore": 5.1797},
    {"ticker": "INTC", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "exit_date": "2021-10-22", "zscore": 5.7690},
    {"ticker": "LDOS", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "exit_date": "2024-11-01", "zscore": 6.3776},
    {"ticker": "MSFT", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "exit_date": "2023-10-27", "zscore": 8.2717},
    {"ticker": "MSFT", "spike_week": "2025-10-26", "entry_date": "2025-10-28", "exit_date": "2025-10-31", "zscore": 7.9107},
    {"ticker": "NFLX", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "exit_date": "2021-10-22", "zscore": 15.2739},
    {"ticker": "NFLX", "spike_week": "2023-01-15", "entry_date": "2023-01-17", "exit_date": "2023-01-20", "zscore": 8.9970},
    {"ticker": "NFLX", "spike_week": "2023-07-16", "entry_date": "2023-07-18", "exit_date": "2023-07-21", "zscore": 15.8142},
    {"ticker": "NFLX", "spike_week": "2023-10-15", "entry_date": "2023-10-17", "exit_date": "2023-10-20", "zscore": 8.5654},
    {"ticker": "NFLX", "spike_week": "2024-07-14", "entry_date": "2024-07-16", "exit_date": "2024-07-19", "zscore": 13.6586},
    {"ticker": "NFLX", "spike_week": "2025-01-19", "entry_date": "2025-01-21", "exit_date": "2025-01-24", "zscore": 12.7874},
    {"ticker": "NFLX", "spike_week": "2025-10-19", "entry_date": "2025-10-21", "exit_date": "2025-10-24", "zscore": 8.9863},
    {"ticker": "NKE", "spike_week": "2022-09-25", "entry_date": "2022-09-27", "exit_date": "2022-09-30", "zscore": 22.5318},
    {"ticker": "NKE", "spike_week": "2025-03-16", "entry_date": "2025-03-18", "exit_date": "2025-03-21", "zscore": 9.3732},
    {"ticker": "NVDA", "spike_week": "2022-02-13", "entry_date": "2022-02-15", "exit_date": "2022-02-18", "zscore": 6.1675},
    {"ticker": "NVDA", "spike_week": "2022-05-22", "entry_date": "2022-05-24", "exit_date": "2022-05-27", "zscore": 5.8399},
    {"ticker": "NVDA", "spike_week": "2023-11-19", "entry_date": "2023-11-21", "exit_date": "2023-11-24", "zscore": 5.5047},
    {"ticker": "QCOM", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.8734},
    {"ticker": "QCOM", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "zscore": 7.0749},
    {"ticker": "SBUX", "spike_week": "2023-10-29", "entry_date": "2023-10-31", "exit_date": "2023-11-03", "zscore": 7.9184},
    {"ticker": "SBUX", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 13.2358},
    {"ticker": "STZ", "spike_week": "2025-01-05", "entry_date": "2025-01-07", "exit_date": "2025-01-10", "zscore": 11.7801},
    {"ticker": "SYK", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "zscore": 5.9146},
    {"ticker": "TTWO", "spike_week": "2025-02-02", "entry_date": "2025-02-04", "exit_date": "2025-02-07", "zscore": 9.4169},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])
print(f"H5 SUPPLEMENTAL out-of-sample pull (entire remaining eligible pool): n={len(sample)}  tickers={sample['ticker'].nunique()}")


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
# results_df.to_csv("QC_H5_OutOfSample_Supplemental_RawResults.csv", index=False)
