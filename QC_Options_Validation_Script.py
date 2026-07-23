# ============================================================================
# QuantConnect Research validation: real historical option quotes vs. this
# project's Black-Scholes-modeled entry/exit prices, for a stratified sample
# of the 152-event FixedWindow_PerEvent_Canonical.csv population.
#
# NO FILE UPLOAD NEEDED: the stratified sample (10 top modeled winners, 10
# top modeled losers, 10 random [seed=42], all 15 MSFT events, de-duplicated
# by ticker+spike_week -> n=42) was selected locally from
# Live Signal Engine/FixedWindow_PerEvent_Canonical.csv and is embedded below
# as EMBEDDED_SAMPLE. Re-run the local selection script if the canonical CSV
# is ever regenerated and this sample needs refreshing.
#
# WHAT "MODELED" MEANS HERE: this project's backtest prices every event on a
# SYNTHETIC $100 notional (S=K=100), Black-Scholes fair value x
# COST_LOADING=1.05, using TRAILING REALIZED VOL x a calibrated near-earnings
# IV markup (1.2398, from this project's iv_calibration_buckets.csv) -- NOT a
# real quoted option price. Only the resulting pnl_pct/win are embedded below
# (the canonical CSV's own output); this script recomputes the modeled COST
# INSIDE this notebook (same formula/constants) using QC's own equity
# daily-price history for trailing vol, so the pricing-error comparison has
# something to compare against beyond just pnl_pct.
#
# EXPIRATION SELECTION: no earnings-announcement date is embedded, only
# entry_date (anchor+2) and exit_date (anchor+6). Per this project's own
# exit-rule definition, exit_date IS "the next trading day's close after the
# earnings announcement" -- so "first expiration after earnings" is
# operationalized here as the first listed expiration ON OR AFTER exit_date.
# This is a disclosed proxy, not a re-derivation of the actual earnings date.
#
# FEES: no real commission schedule is available from QC directly; a
# disclosed, adjustable assumption (FEE_PER_CONTRACT_USD, 4 legs: buy
# call+put at entry, sell call+put at exit) is used, converted to
# per-share-quote units (contract = 100 shares) to match the bid/ask scale.
#
# HOW TO USE: paste this entire file's contents into an empty cell in your
# QuantConnect Research notebook (research.ipynb, where `qb` is already
# available as QuantBook) and run it. No file upload required.
# ============================================================================

import pandas as pd
import numpy as np
import math
from datetime import timedelta
from QuantConnect.Research import QuantBook

# QuantBook must be explicitly instantiated at the start of a Research
# notebook session before any qb.* call (History, AddEquity,
# OptionChainProvider, etc.) will work -- it is not pre-defined by default.
qb = QuantBook()

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
RISK_FREE_RATE = 0.02
NEAR_EARNINGS_IV_MARKUP = 1.2398   # from this project's iv_calibration_buckets.csv
COST_LOADING = 1.05
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30

FEE_PER_CONTRACT_USD = 0.65
FEE_LEGS = 4                        # buy call, buy put (entry); sell call, sell put (exit)
FEES_IN_QUOTE_UNITS = (FEE_PER_CONTRACT_USD * FEE_LEGS) / 100.0   # contract = 100 shares

TICKER_OVERRIDES = {"BRK-B": "BRK.B"}   # QC ticker-format normalization; add more here if a symbol fails to resolve

# ---------------------------------------------------------------------------
# EMBEDDED STRATIFIED SAMPLE (n=42) -- selected locally from
# FixedWindow_PerEvent_Canonical.csv: 10 top modeled winners by pnl_pct,
# 10 top modeled losers, 10 random (RandomState seed=42) from the remaining
# pool, plus all 15 MSFT events -- de-duplicated by (ticker, spike_week).
# Spans 2021-2025.
# ---------------------------------------------------------------------------
EMBEDDED_SAMPLE = [
    {"ticker": "ADBE", "spike_week": "2025-12-07", "entry_date": "2025-12-09", "exit_date": "2025-12-12", "pnl_pct": 37.17, "win": True},
    {"ticker": "AMZN", "spike_week": "2023-01-29", "entry_date": "2023-01-31", "exit_date": "2023-02-03", "pnl_pct": -94.47, "win": False},
    {"ticker": "AMZN", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "pnl_pct": 165.55, "win": True},
    {"ticker": "BRK-B", "spike_week": "2025-02-23", "entry_date": "2025-02-25", "exit_date": "2025-02-28", "pnl_pct": 103.57, "win": True},
    {"ticker": "CTSH", "spike_week": "2022-10-30", "entry_date": "2022-11-01", "exit_date": "2022-11-04", "pnl_pct": 536.01, "win": True},
    {"ticker": "INTC", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "pnl_pct": 761.31, "win": True},
    {"ticker": "LDOS", "spike_week": "2023-04-30", "entry_date": "2023-05-02", "exit_date": "2023-05-05", "pnl_pct": -85.7, "win": False},
    {"ticker": "LDOS", "spike_week": "2024-02-11", "entry_date": "2024-02-13", "exit_date": "2024-02-16", "pnl_pct": 83.77, "win": True},
    {"ticker": "LDOS", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "exit_date": "2024-11-01", "pnl_pct": -7.56, "win": False},
    {"ticker": "MSFT", "spike_week": "2021-07-25", "entry_date": "2021-07-27", "exit_date": "2021-07-30", "pnl_pct": -66.57, "win": False},
    {"ticker": "MSFT", "spike_week": "2021-10-24", "entry_date": "2021-10-26", "exit_date": "2021-10-29", "pnl_pct": 308.92, "win": True},
    {"ticker": "MSFT", "spike_week": "2022-01-23", "entry_date": "2022-01-25", "exit_date": "2022-01-28", "pnl_pct": 187.31, "win": True},
    {"ticker": "MSFT", "spike_week": "2022-04-24", "entry_date": "2022-04-26", "exit_date": "2022-04-29", "pnl_pct": -14.67, "win": False},
    {"ticker": "MSFT", "spike_week": "2022-07-24", "entry_date": "2022-07-26", "exit_date": "2022-07-29", "pnl_pct": 227.86, "win": True},
    {"ticker": "MSFT", "spike_week": "2022-10-23", "entry_date": "2022-10-25", "exit_date": "2022-10-28", "pnl_pct": 89.41, "win": True},
    {"ticker": "MSFT", "spike_week": "2023-01-22", "entry_date": "2023-01-24", "exit_date": "2023-01-27", "pnl_pct": -31.69, "win": False},
    {"ticker": "MSFT", "spike_week": "2023-04-23", "entry_date": "2023-04-25", "exit_date": "2023-04-28", "pnl_pct": 321.99, "win": True},
    {"ticker": "MSFT", "spike_week": "2023-10-22", "entry_date": "2023-10-24", "exit_date": "2023-10-27", "pnl_pct": -89.5, "win": False},
    {"ticker": "MSFT", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "pnl_pct": 87.25, "win": True},
    {"ticker": "MSFT", "spike_week": "2024-10-27", "entry_date": "2024-10-29", "exit_date": "2024-11-01", "pnl_pct": 199.1, "win": True},
    {"ticker": "MSFT", "spike_week": "2025-01-26", "entry_date": "2025-01-28", "exit_date": "2025-01-31", "pnl_pct": 242.58, "win": True},
    {"ticker": "MSFT", "spike_week": "2025-07-27", "entry_date": "2025-07-29", "exit_date": "2025-08-01", "pnl_pct": 15.76, "win": True},
    {"ticker": "MSFT", "spike_week": "2025-10-26", "entry_date": "2025-10-28", "exit_date": "2025-10-31", "pnl_pct": 175.8, "win": True},
    {"ticker": "NFLX", "spike_week": "2022-01-16", "entry_date": "2022-01-18", "exit_date": "2022-01-21", "pnl_pct": 719.72, "win": True},
    {"ticker": "NFLX", "spike_week": "2023-01-15", "entry_date": "2023-01-17", "exit_date": "2023-01-20", "pnl_pct": -12.33, "win": False},
    {"ticker": "NFLX", "spike_week": "2025-01-19", "entry_date": "2025-01-21", "exit_date": "2025-01-24", "pnl_pct": 300.32, "win": True},
    {"ticker": "NKE", "spike_week": "2021-06-20", "entry_date": "2021-06-22", "exit_date": "2021-06-25", "pnl_pct": 620.29, "win": True},
    {"ticker": "NKE", "spike_week": "2021-12-19", "entry_date": "2021-12-21", "exit_date": "2021-12-23", "pnl_pct": -70.39, "win": False},
    {"ticker": "NKE", "spike_week": "2022-03-20", "entry_date": "2022-03-22", "exit_date": "2022-03-25", "pnl_pct": -84.36, "win": False},
    {"ticker": "NKE", "spike_week": "2024-06-23", "entry_date": "2024-06-25", "exit_date": "2024-06-28", "pnl_pct": 808.41, "win": True},
    {"ticker": "NVDA", "spike_week": "2023-05-21", "entry_date": "2023-05-23", "exit_date": "2023-05-26", "pnl_pct": 544.46, "win": True},
    {"ticker": "NVDA", "spike_week": "2023-08-20", "entry_date": "2023-08-22", "exit_date": "2023-08-25", "pnl_pct": -87.22, "win": False},
    {"ticker": "QCOM", "spike_week": "2021-10-31", "entry_date": "2021-11-02", "exit_date": "2021-11-05", "pnl_pct": 1093.0, "win": True},
    {"ticker": "SBUX", "spike_week": "2023-07-30", "entry_date": "2023-08-01", "exit_date": "2023-08-04", "pnl_pct": -77.43, "win": False},
    {"ticker": "SBUX", "spike_week": "2023-10-29", "entry_date": "2023-10-31", "exit_date": "2023-11-03", "pnl_pct": 611.53, "win": True},
    {"ticker": "SBUX", "spike_week": "2024-04-28", "entry_date": "2024-04-30", "exit_date": "2024-05-03", "pnl_pct": 966.94, "win": True},
    {"ticker": "SBUX", "spike_week": "2025-04-27", "entry_date": "2025-04-29", "exit_date": "2025-05-02", "pnl_pct": -95.83, "win": False},
    {"ticker": "STZ", "spike_week": "2024-04-07", "entry_date": "2024-04-09", "exit_date": "2024-04-12", "pnl_pct": -82.5, "win": False},
    {"ticker": "STZ", "spike_week": "2025-01-05", "entry_date": "2025-01-07", "exit_date": "2025-01-10", "pnl_pct": 737.23, "win": True},
    {"ticker": "SYK", "spike_week": "2024-01-28", "entry_date": "2024-01-30", "exit_date": "2024-02-02", "pnl_pct": 362.07, "win": True},
    {"ticker": "SYK", "spike_week": "2024-07-28", "entry_date": "2024-07-30", "exit_date": "2024-08-02", "pnl_pct": -75.69, "win": False},
    {"ticker": "TTWO", "spike_week": "2024-05-12", "entry_date": "2024-05-14", "exit_date": "2024-05-17", "pnl_pct": -22.4, "win": False},
]

sample = pd.DataFrame(EMBEDDED_SAMPLE)
sample["spike_week"] = pd.to_datetime(sample["spike_week"])
sample["entry_date"] = pd.to_datetime(sample["entry_date"])
sample["exit_date"] = pd.to_datetime(sample["exit_date"])

print(f"Embedded stratified sample: n={len(sample)}  "
      f"(spans {sample['spike_week'].dt.year.min()}-{sample['spike_week'].dt.year.max()}, "
      f"{(sample['ticker']=='MSFT').sum()} MSFT events, "
      f"{sample['win'].sum()} modeled wins / {len(sample)} total)")

# ---------------------------------------------------------------------------
# MODEL RECOMPUTE HELPERS (mirrors this project's Black-Scholes methodology,
# using QC's own equity daily history for trailing realized vol)
# ---------------------------------------------------------------------------
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_straddle_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return call + put


def model_implied_cost_pct(equity_symbol, entry_date, exit_date):
    """Recomputes this project's modeled straddle cost (% of $100 notional),
    using QC's own daily equity history for trailing realized vol.
    Takes the already-resolved Symbol from qb.AddEquity(...).Symbol (obtained
    once per event in the main loop) rather than constructing a new one --
    qb.Symbol.Create does not exist in the Research API (qb.Symbol is not the
    Symbol class); AddEquity(...).Symbol is the correct, already-proven way
    to get a Symbol object in this notebook."""
    vol_start = entry_date - timedelta(days=VOL_LOOKBACK_TRADING_DAYS * 2 + 20)
    vol_end = entry_date - timedelta(days=1)
    px = qb.History(equity_symbol, vol_start, vol_end, Resolution.Daily)
    if px is None or px.empty or "close" not in px.columns:
        return None
    closes = px["close"].tail(VOL_LOOKBACK_TRADING_DAYS + 5)
    if len(closes) < MIN_VOL_HISTORY_DAYS:
        return None
    rets = closes.pct_change().dropna()
    sigma = float(rets.std() * math.sqrt(252))
    if sigma <= 0:
        return None
    iv = sigma * NEAR_EARNINGS_IV_MARKUP
    T = (exit_date - entry_date).days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    return fair * COST_LOADING   # % of $100 notional


# ---------------------------------------------------------------------------
# REAL-QUOTE PULL HELPERS
# ---------------------------------------------------------------------------
def get_bid_ask(option_symbol, target_date):
    """Nearest QuoteBar on/before target_date's close, via History<QuoteBar>."""
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
    modeled_pnl_pct = float(row["pnl_pct"])
    modeled_win = bool(row["win"])

    rec = {"ticker": raw_ticker, "spike_week": row["spike_week"].date(),
           "entry_date": entry_date.date(), "exit_date": exit_date.date(),
           "modeled_pnl_pct": modeled_pnl_pct, "modeled_win": modeled_win,
           "note": ""}

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

        model_cost_pct = model_implied_cost_pct(equity_symbol, entry_date, exit_date)
        real_cost_pct_of_spot = entry_cost / entry_underlying_price * 100

        rec.update({
            "call_entry_ask": call_entry_ask, "put_entry_ask": put_entry_ask,
            "call_exit_bid": call_exit_bid, "put_exit_bid": put_exit_bid,
            "real_entry_cost": entry_cost, "real_exit_value": exit_value,
            "real_pnl_pct": round(real_pnl_pct, 2), "real_win": real_win,
            "model_implied_cost_pct": round(model_cost_pct, 3) if model_cost_pct is not None else None,
            "real_cost_pct_of_spot": round(real_cost_pct_of_spot, 3),
            "pricing_error_pct_points": round(real_cost_pct_of_spot - model_cost_pct, 3) if model_cost_pct is not None else None,
            "return_error_pct_points": round(real_pnl_pct - modeled_pnl_pct, 2),
            "win_match": real_win == modeled_win,
        })
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: "
              f"real_pnl={real_pnl_pct:.1f}% modeled_pnl={modeled_pnl_pct:.1f}% "
              f"match={rec['win_match']}")

    except Exception as e:
        rec["note"] = f"exception: {e}"
        results.append(rec)
        print(f"[{idx+1}/{len(sample)}] {raw_ticker} {row['spike_week'].date()}: EXCEPTION: {e}")

results_df = pd.DataFrame(results)

# ---------------------------------------------------------------------------
# FINAL SUMMARY
# ---------------------------------------------------------------------------
complete = results_df[results_df.get("real_pnl_pct").notna()] if "real_pnl_pct" in results_df.columns else pd.DataFrame()

print("\n" + "=" * 70)
print("SUMMARY: real historical option quotes vs. modeled Black-Scholes prices")
print("=" * 70)
print(f"Sample size: {len(sample)}   Successfully pulled + priced: {len(complete)}   "
      f"Failed/incomplete: {len(sample) - len(complete)}")

if not complete.empty:
    median_pricing_error = complete["pricing_error_pct_points"].median()
    median_return_error = complete["return_error_pct_points"].median()
    win_match_rate = complete["win_match"].mean() * 100

    print(f"\nMedian pricing error (real entry cost % of spot - modeled implied cost %): "
          f"{median_pricing_error:+.2f} pct points")
    print(f"Median return error (real pnl% - modeled pnl%): {median_return_error:+.2f} pct points")
    print(f"Win/loss classification match rate (real vs. modeled): {win_match_rate:.1f}%")

    summary_table = pd.DataFrame([{
        "n_sampled": len(sample),
        "n_successfully_priced": len(complete),
        "median_pricing_error_pct_points": round(median_pricing_error, 3),
        "median_return_error_pct_points": round(median_return_error, 2),
        "win_loss_match_rate_pct": round(win_match_rate, 1),
    }])
else:
    print("\nNo events were successfully priced with real quotes -- check the 'note' "
          "column in results_df for why each event failed (missing chain, missing "
          "quotes, ticker-symbol mismatch, etc.).")
    summary_table = pd.DataFrame([{
        "n_sampled": len(sample), "n_successfully_priced": 0,
        "median_pricing_error_pct_points": None,
        "median_return_error_pct_points": None,
        "win_loss_match_rate_pct": None,
    }])

display(results_df)
display(summary_table)
