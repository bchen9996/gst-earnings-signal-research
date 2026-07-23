# ============================================================================
# SHORT-VOL CONTROL-EVENT REAL-QUOTE PULL -- 39 of the 133 matched
# non-signal control events from ShortVol_DefensiveFilter_Test.csv,
# currently priced ONLY with modeled data (no real quote has ever been
# pulled for a control/non-signal earnings date in this project).
#
# Stratified random sample: ticker-proportional, seed=256 (fresh, not
# reused from any prior sample tonight: 42, 7, 99, 123), deduplicated
# against the 133-row control set's own duplicates first (the matched-
# control methodology allows the same real-world control date to be
# reused across multiple signal matches -- pulling it twice would waste a
# call on identical real data). 28 distinct tickers, spans 2021-2025.
#
# *** THIS PRICES THE SHORT SIDE DIRECTLY AND CORRECTLY -- not a negation
# of a long-side pull. *** A short seller SELLS the straddle: receives the
# BID at entry, buys it back (pays the ASK) at exit -- the OPPOSITE legs
# from every long-side pull tonight (which paid ask at entry, received
# bid at exit). This fixes the exact data gap flagged when
# ShortVol_DefensiveFilter_Test.csv was built (that file's signal-side
# real-quote events approximated the short side as -long_pnl_pct, which
# understates true short-side cost since it reuses the long's favorable
# legs). This pull has no such approximation.
#
# short_pnl_pct = (entry_bid_total - exit_ask_total - fees) / entry_bid_total * 100
# (return on premium received, the short-side analogue of the long side's
# "return on premium paid" convention already used throughout tonight).
#
# Same proven contract-selection methodology as every prior pull:
# History<QuoteBar>, ATM strike (closest to entry-day close), first
# expiration on/after exit_date, automated corruption filter
# (checked against entry_bid, the short seller's actual received premium,
# > 25% of spot -> flagged/excluded), $0.65/contract x 4 legs fee.
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
TICKER_OVERRIDES = {"BRK-B": "BRK.B"}

# ---------------------------------------------------------------------------
# EMBEDDED SAMPLE (n=39) -- stratified ticker-proportional random sample,
# seed=256, from the 85 DISTINCT (deduplicated) control events in
# ShortVol_DefensiveFilter_Test.csv.
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "AAPL", "anchor": "2021-10-28", "entry_date": "2021-10-29", "exit_date": "2021-11-03"},
    {"ticker": "AAPL", "anchor": "2025-10-30", "entry_date": "2025-10-31", "exit_date": "2025-11-05"},
    {"ticker": "ABBV", "anchor": "2023-10-27", "entry_date": "2023-10-27", "exit_date": "2023-11-02"},
    {"ticker": "ADBE", "anchor": "2022-06-16", "entry_date": "2022-06-17", "exit_date": "2022-06-22"},
    {"ticker": "ADBE", "anchor": "2023-09-14", "entry_date": "2023-09-15", "exit_date": "2023-09-20"},
    {"ticker": "AMZN", "anchor": "2021-04-29", "entry_date": "2021-04-30", "exit_date": "2021-05-05"},
    {"ticker": "AMZN", "anchor": "2025-05-01", "entry_date": "2025-05-02", "exit_date": "2025-05-07"},
    {"ticker": "BKR", "anchor": "2024-07-25", "entry_date": "2024-07-26", "exit_date": "2024-07-31"},
    {"ticker": "BRK-B", "anchor": "2025-02-22", "entry_date": "2025-02-24", "exit_date": "2025-02-28"},
    {"ticker": "COHR", "anchor": "2025-11-05", "entry_date": "2025-11-07", "exit_date": "2025-11-11"},
    {"ticker": "CTSH", "anchor": "2021-05-05", "entry_date": "2021-05-07", "exit_date": "2021-05-11"},
    {"ticker": "DELL", "anchor": "2023-11-30", "entry_date": "2023-12-01", "exit_date": "2023-12-06"},
    {"ticker": "DVN", "anchor": "2025-08-05", "entry_date": "2025-08-07", "exit_date": "2025-08-11"},
    {"ticker": "GME", "anchor": "2024-03-26", "entry_date": "2024-03-28", "exit_date": "2024-04-01"},
    {"ticker": "GOOGL", "anchor": "2021-10-26", "entry_date": "2021-10-28", "exit_date": "2021-11-01"},
    {"ticker": "GOOGL", "anchor": "2022-02-01", "entry_date": "2022-02-03", "exit_date": "2022-02-07"},
    {"ticker": "GPN", "anchor": "2024-08-07", "entry_date": "2024-08-09", "exit_date": "2024-08-13"},
    {"ticker": "INTC", "anchor": "2024-01-25", "entry_date": "2024-01-26", "exit_date": "2024-01-31"},
    {"ticker": "INTC", "anchor": "2025-01-30", "entry_date": "2025-01-31", "exit_date": "2025-02-05"},
    {"ticker": "JBL", "anchor": "2022-09-27", "entry_date": "2022-09-29", "exit_date": "2022-10-03"},
    {"ticker": "LDOS", "anchor": "2024-02-13", "entry_date": "2024-02-15", "exit_date": "2024-02-16"},
    {"ticker": "MSFT", "anchor": "2024-04-25", "entry_date": "2024-04-26", "exit_date": "2024-05-01"},
    {"ticker": "NCLH", "anchor": "2021-11-03", "entry_date": "2021-11-05", "exit_date": "2021-11-09"},
    {"ticker": "NFLX", "anchor": "2023-01-19", "entry_date": "2023-01-20", "exit_date": "2023-01-25"},
    {"ticker": "NFLX", "anchor": "2024-04-18", "entry_date": "2024-04-19", "exit_date": "2024-04-24"},
    {"ticker": "NKE", "anchor": "2024-12-19", "entry_date": "2024-12-20", "exit_date": "2024-12-24"},
    {"ticker": "NVDA", "anchor": "2021-08-18", "entry_date": "2021-08-20", "exit_date": "2021-08-24"},
    {"ticker": "NVDA", "anchor": "2024-08-28", "entry_date": "2024-08-30", "exit_date": "2024-09-03"},
    {"ticker": "QCOM", "anchor": "2025-11-05", "entry_date": "2025-11-07", "exit_date": "2025-11-11"},
    {"ticker": "SBUX", "anchor": "2025-01-28", "entry_date": "2025-01-30", "exit_date": "2025-02-03"},
    {"ticker": "SBUX", "anchor": "2025-10-29", "entry_date": "2025-10-31", "exit_date": "2025-11-04"},
    {"ticker": "STZ", "anchor": "2024-07-03", "entry_date": "2024-07-05", "exit_date": "2024-07-09"},
    {"ticker": "SYK", "anchor": "2024-10-29", "entry_date": "2024-10-31", "exit_date": "2024-11-04"},
    {"ticker": "SYK", "anchor": "2025-07-31", "entry_date": "2025-08-01", "exit_date": "2025-08-06"},
    {"ticker": "TSLA", "anchor": "2023-07-19", "entry_date": "2023-07-21", "exit_date": "2023-07-25"},
    {"ticker": "TTWO", "anchor": "2021-08-02", "entry_date": "2021-08-04", "exit_date": "2021-08-06"},
    {"ticker": "TTWO", "anchor": "2024-11-06", "entry_date": "2024-11-08", "exit_date": "2024-11-12"},
    {"ticker": "TTWO", "anchor": "2025-02-06", "entry_date": "2025-02-07", "exit_date": "2025-02-12"},
    {"ticker": "UAL", "anchor": "2023-07-19", "entry_date": "2023-07-21", "exit_date": "2023-07-25"},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["anchor"] = pd.to_datetime(sample["anchor"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])

print(f"Control-event sample: n={len(sample)}  tickers={sample['ticker'].nunique()}  "
      f"(spans {sample['anchor'].dt.year.min()}-{sample['anchor'].dt.year.max()})")

# ---------------------------------------------------------------------------
# REAL-QUOTE PULL HELPERS (identical History<QuoteBar> pattern as every
# prior pull tonight)
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
    exit_date = row["exit_date"].to_pydatetime()

    rec = {"ticker": raw_ticker, "anchor": row["anchor"].date(), "entry_date": entry_date.date(),
           "exit_date": exit_date.date(), "corrupted": False, "note": ""}

    try:
        equity = qb.AddEquity(qc_ticker, Resolution.Daily)
        equity_symbol = equity.Symbol

        px_hist = qb.History(equity_symbol, entry_date - timedelta(days=7), entry_date + timedelta(days=1),
                              Resolution.Daily)
        if px_hist is None or px_hist.empty:
            rec["note"] = "no underlying price history at entry"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue
        entry_underlying_price = float(px_hist["close"].iloc[-1])

        contracts = list(qb.OptionChainProvider.GetOptionContractList(equity_symbol, entry_date))
        if not contracts:
            rec["note"] = "no option chain listed at entry date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue

        expiries = sorted(set(c.ID.Date for c in contracts if c.ID.Date >= exit_date))
        if not expiries:
            rec["note"] = "no listed expiration on/after exit date"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue
        target_expiry = expiries[0]

        same_expiry = [c for c in contracts if c.ID.Date == target_expiry]
        strikes = sorted(set(c.ID.StrikePrice for c in same_expiry))
        if not strikes:
            rec["note"] = "no strikes found for chosen expiration"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue
        atm_strike = min(strikes, key=lambda k: abs(k - entry_underlying_price))

        call_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                             and c.ID.OptionRight == OptionRight.Call), None)
        put_symbol = next((c for c in same_expiry if c.ID.StrikePrice == atm_strike
                            and c.ID.OptionRight == OptionRight.Put), None)
        if call_symbol is None or put_symbol is None:
            rec["note"] = "missing call or put contract at chosen strike/expiry"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue

        call_entry_bid, call_entry_ask = get_bid_ask(call_symbol, entry_date)
        put_entry_bid, put_entry_ask = get_bid_ask(put_symbol, entry_date)
        call_exit_bid, call_exit_ask = get_bid_ask(call_symbol, exit_date)
        put_exit_bid, put_exit_ask = get_bid_ask(put_symbol, exit_date)

        # SHORT SIDE: receive entry BID, pay exit ASK -- the opposite legs from every long pull tonight.
        missing = [v is None for v in [call_entry_bid, put_entry_bid, call_exit_ask, put_exit_ask]]
        if any(missing):
            rec["note"] = "missing real quote data at entry (bid) or exit (ask)"
            results.append(rec); print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue

        entry_bid_total = call_entry_bid + put_entry_bid   # premium RECEIVED by the short seller
        exit_ask_total = call_exit_ask + put_exit_ask       # premium PAID to buy back and close
        real_cost_pct_of_spot = entry_bid_total / entry_underlying_price * 100

        if real_cost_pct_of_spot > MAX_PLAUSIBLE_COST_PCT_OF_SPOT:
            rec["corrupted"] = True
            rec["real_cost_pct_of_spot"] = round(real_cost_pct_of_spot, 3)
            rec["note"] = (f"EXCLUDED: implausible entry_bid_pct_of_spot="
                            f"{real_cost_pct_of_spot:.1f}% (> {MAX_PLAUSIBLE_COST_PCT_OF_SPOT}% threshold)")
            results.append(rec)
            print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: {rec['note']}")
            continue

        short_pnl_pct = (entry_bid_total - exit_ask_total - FEES_IN_QUOTE_UNITS) / entry_bid_total * 100
        dollar_pnl_10k = 10000.0 * (short_pnl_pct / 100.0)

        rec.update({
            "call_entry_bid": call_entry_bid, "put_entry_bid": put_entry_bid,
            "call_exit_ask": call_exit_ask, "put_exit_ask": put_exit_ask,
            "entry_bid_total": round(entry_bid_total, 3), "exit_ask_total": round(exit_ask_total, 3),
            "real_cost_pct_of_spot": round(real_cost_pct_of_spot, 3),
            "short_pnl_pct": round(short_pnl_pct, 2),
            "short_win": bool(short_pnl_pct > 0),
            "dollar_pnl_per_10k": round(dollar_pnl_10k, 2),
        })
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: "
              f"short_pnl={short_pnl_pct:.1f}%  ${dollar_pnl_10k:,.0f}")

    except Exception as e:
        rec["note"] = f"exception: {e}"
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['anchor'].date()}: EXCEPTION: {e}")

results_df = pd.DataFrame(results)

n_corrupted = int(results_df["corrupted"].sum()) if "corrupted" in results_df.columns else 0
complete = results_df[(results_df.get("short_pnl_pct").notna()) & (~results_df["corrupted"])].copy() \
    if "short_pnl_pct" in results_df.columns else pd.DataFrame()

print("\n" + "=" * 70)
print("SUMMARY: real short-side quotes on 39 control (non-signal) events")
print("=" * 70)
print(f"Sample size: {len(sample)}   Auto-flagged corrupted: {n_corrupted}   "
      f"Successfully priced (clean): {len(complete)}   "
      f"Failed/incomplete (other): {len(sample) - len(complete) - n_corrupted}")

if not complete.empty:
    print(f"\nMean short_pnl_pct: {complete['short_pnl_pct'].mean():+.2f}%")
    print(f"Median short_pnl_pct: {complete['short_pnl_pct'].median():+.2f}%")
    print(f"Win rate (short_pnl_pct > 0): {complete['short_win'].mean()*100:.1f}%")
    print(f"Mean $ return per $10k: ${complete['dollar_pnl_per_10k'].mean():,.0f}")
    print(f"Worst single trade: ${complete['dollar_pnl_per_10k'].min():,.0f} "
          f"({complete['short_pnl_pct'].min():+.1f}%)")
else:
    print("\nNo events were successfully priced -- check the 'note' column in results_df.")

if n_corrupted > 0:
    print(f"\nAuto-flagged corrupted events (excluded from summary, kept in results_df for audit):")
    display(results_df[results_df["corrupted"] == True][["ticker", "anchor", "real_cost_pct_of_spot", "note"]])

display(results_df)

# To export for local analysis:
# complete.to_csv("QC_ShortVol_ControlSample_39Events.csv", index=False)
