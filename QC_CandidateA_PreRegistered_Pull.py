# ============================================================================
# CANDIDATE A PRE-REGISTERED TEST -- real QuantConnect quote pull for the
# 34-event UNTOUCHED sample locked in
# Live Signal Engine/CandidateA_PreRegistration.md BEFORE this script was
# run. Do not add metrics or reinterpret results beyond what that file
# specifies -- the decision-rule check at the bottom of this script's
# output is the whole point of the exercise.
#
# Sample: all 10 untouched z>=10 canonical events + 24 proportionally
# sampled untouched 5<=z<10 events (seed=99), none of which appeared in
# either of the two earlier QC pulls tonight (37/42-event, 76/90-event).
#
# Same proven methodology as both prior pulls: History<QuoteBar>, ATM
# strike (closest to entry-day close), first expiration on/after
# exit_date, automated corruption filter (real_cost_pct_of_spot > 25% of
# spot -> flagged/excluded, not silently dropped), $0.65/contract x 4 legs
# fee assumption. No model-cost recompute here -- irrelevant to this
# test's pre-registered metrics, deliberately left out to avoid inviting
# any post-hoc comparison not specified in advance.
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
# PRE-REGISTERED SAMPLE (n=34) -- locked in CandidateA_PreRegistration.md
# BEFORE this script was run. 10 z>=10 (all untouched z>=10 events) + 24
# proportionally-sampled 5<=z<10 (seed=99), none from either prior QC pull.
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "DELL", "spike_week": "2021-08-22", "entry_date": "2021-08-24", "exit_date": "2021-08-27", "zscore": 10.6750, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2021-04-18", "entry_date": "2021-04-20", "exit_date": "2021-04-23", "zscore": 13.9663, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2022-06-26", "entry_date": "2022-06-28", "exit_date": "2022-07-01", "zscore": 13.4434, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2022-09-25", "entry_date": "2022-09-27", "exit_date": "2022-09-30", "zscore": 22.5318, "tier": "z>=10"},
    {"ticker": "NKE", "spike_week": "2023-03-19", "entry_date": "2023-03-21", "exit_date": "2023-03-24", "zscore": 12.2236, "tier": "z>=10"},
    {"ticker": "TTWO", "spike_week": "2023-11-05", "entry_date": "2023-11-07", "exit_date": "2023-11-10", "zscore": 27.4501, "tier": "z>=10"},
    {"ticker": "NFLX", "spike_week": "2024-01-21", "entry_date": "2024-01-23", "exit_date": "2024-01-26", "zscore": 26.7917, "tier": "z>=10"},
    {"ticker": "ADBE", "spike_week": "2024-12-08", "entry_date": "2024-12-10", "exit_date": "2024-12-13", "zscore": 14.6653, "tier": "z>=10"},
    {"ticker": "SBUX", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "zscore": 13.2358, "tier": "z>=10"},
    {"ticker": "ADBE", "spike_week": "2025-09-07", "entry_date": "2025-09-09", "exit_date": "2025-09-12", "zscore": 16.9269, "tier": "z>=10"},
    {"ticker": "AAPL", "spike_week": "2023-01-29", "entry_date": "2023-01-31", "exit_date": "2023-02-03", "zscore": 6.6056, "tier": "5<=z<10"},
    {"ticker": "ADBE", "spike_week": "2022-03-20", "entry_date": "2022-03-22", "exit_date": "2022-03-25", "zscore": 6.9888, "tier": "5<=z<10"},
    {"ticker": "AMZN", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.5190, "tier": "5<=z<10"},
    {"ticker": "AMZN", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "zscore": 7.2373, "tier": "5<=z<10"},
    {"ticker": "AMZN", "spike_week": "2025-10-26", "entry_date": "2025-10-28", "exit_date": "2025-10-31", "zscore": 8.7855, "tier": "5<=z<10"},
    {"ticker": "COHR", "spike_week": "2024-08-11", "entry_date": "2024-08-13", "exit_date": "2024-08-16", "zscore": 5.4132, "tier": "5<=z<10"},
    {"ticker": "CTSH", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "zscore": 5.5886, "tier": "5<=z<10"},
    {"ticker": "GME", "spike_week": "2023-03-19", "entry_date": "2023-03-21", "exit_date": "2023-03-24", "zscore": 8.5408, "tier": "5<=z<10"},
    {"ticker": "GOOGL", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "exit_date": "2022-10-28", "zscore": 5.1797, "tier": "5<=z<10"},
    {"ticker": "GOOGL", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "exit_date": "2023-10-27", "zscore": 7.0455, "tier": "5<=z<10"},
    {"ticker": "GPN", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "zscore": 5.8377, "tier": "5<=z<10"},
    {"ticker": "INTC", "spike_week": "2021-10-17", "entry_date": "2021-10-19", "exit_date": "2021-10-22", "zscore": 5.7690, "tier": "5<=z<10"},
    {"ticker": "NFLX", "spike_week": "2023-04-16", "entry_date": "2023-04-18", "exit_date": "2023-04-21", "zscore": 7.5055, "tier": "5<=z<10"},
    {"ticker": "NFLX", "spike_week": "2025-07-13", "entry_date": "2025-07-15", "exit_date": "2025-07-18", "zscore": 5.4542, "tier": "5<=z<10"},
    {"ticker": "NFLX", "spike_week": "2025-10-19", "entry_date": "2025-10-21", "exit_date": "2025-10-24", "zscore": 8.9863, "tier": "5<=z<10"},
    {"ticker": "NVDA", "spike_week": "2023-11-19", "entry_date": "2023-11-21", "exit_date": "2023-11-24", "zscore": 5.5047, "tier": "5<=z<10"},
    {"ticker": "NVDA", "spike_week": "2024-02-18", "entry_date": "2024-02-20", "exit_date": "2024-02-23", "zscore": 7.1643, "tier": "5<=z<10"},
    {"ticker": "QCOM", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.8734, "tier": "5<=z<10"},
    {"ticker": "QCOM", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "zscore": 6.5667, "tier": "5<=z<10"},
    {"ticker": "SBUX", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "zscore": 5.6479, "tier": "5<=z<10"},
    {"ticker": "STZ", "spike_week": "2023-12-31", "entry_date": "2023-12-29", "exit_date": "2024-01-05", "zscore": 6.9317, "tier": "5<=z<10"},
    {"ticker": "SYK", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-31", "zscore": 8.2860, "tier": "5<=z<10"},
    {"ticker": "TSLA", "spike_week": "2024-01-21", "entry_date": "2024-01-23", "exit_date": "2024-01-26", "zscore": 7.5137, "tier": "5<=z<10"},
    {"ticker": "TTWO", "spike_week": "2025-02-02", "entry_date": "2025-02-04", "exit_date": "2025-02-07", "zscore": 9.4169, "tier": "5<=z<10"},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])

print(f"Pre-registered sample: n={len(sample)}  "
      f"({(sample['tier']=='z>=10').sum()} z>=10, {(sample['tier']=='5<=z<10').sum()} 5<=z<10)")

# ---------------------------------------------------------------------------
# REAL-QUOTE PULL HELPERS (identical to prior pulls)
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

    rec = {"ticker": raw_ticker, "spike_week": row["spike_week"].date(), "zscore": row["zscore"],
           "tier": row["tier"], "entry_date": entry_date.date(), "exit_date": exit_date.date(),
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

        expiries = sorted(set(c.ID.Date for c in contracts if c.ID.Date >= exit_date))
        if not expiries:
            rec["note"] = "no listed expiration on/after exit date"
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
        call_exit_bid, call_exit_ask = get_bid_ask(call_symbol, exit_date)
        put_exit_bid, put_exit_ask = get_bid_ask(put_symbol, exit_date)

        missing = [v is None for v in [call_entry_ask, put_entry_ask, call_exit_bid, put_exit_bid]]
        if any(missing):
            rec["note"] = "missing real quote data at entry or exit"
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
# in CandidateA_PreRegistration.md, before any other discussion.
# ---------------------------------------------------------------------------
def max_drawdown(equity_curve):
    running_max = np.maximum.accumulate(equity_curve)
    return float(((equity_curve - running_max) / running_max).min())


def tier_report(df, label):
    df = df[df["dollar_pnl"].notna()].sort_values("exit_date").reset_index(drop=True)
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


results_df.to_csv("CandidateA_PreRegistered_Results.csv", index=False)

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
