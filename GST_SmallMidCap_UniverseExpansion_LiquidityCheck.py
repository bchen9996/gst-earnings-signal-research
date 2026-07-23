#!/usr/bin/env python3
# SMALL/MID-CAP UNIVERSE EXPANSION — LIQUIDITY GATING CHECK.
#
# Before spending any effort backtesting the STRONG_EARNINGS signal on a
# small-cap universe, this checks whether that universe's options are even
# tradeable in practice. Two phases:
#
#   PHASE A — Build the filtered candidate universe: current S&P 600
#   constituents (same Wikipedia-table source/method as
#   Backtest_Universe_SP600.py), filtered the same way the existing
#   425-ticker S&P 500 universe was filtered in GST_Live_Signal_Engine.py:
#     (1) unambiguous ticker symbol — reuses that script's EXACT
#         is_ambiguous() function and COMMON_WORDS list, not a re-derived
#         version, so the filter is identical.
#     (2) options available — NOT already applied to the S&P 500 list
#         (virtually every S&P 500 name has listed options, so it was
#         never a binding constraint there); for S&P 600 small-caps this
#         is a genuine, separate check via yfinance's listed-expirations
#         metadata (tk.options) — cheap (no full chain pull), but still a
#         real network call per candidate.
#
#   PHASE B — Real options liquidity sample: from the filtered universe,
#   draw a fixed-seed stratified sample of ~30 names across market-cap
#   terciles (S&P 600 is small-cap by S&P's own classification throughout
#   — there is no separate "mid-cap" cohort inside it; "mix of small/mid"
#   is interpreted as spanning that index's own smallest-to-largest
#   constituents, not pulling from a second mid-cap index/data source).
#   Pulls each name's REAL, CURRENT listed option chain (nearest available
#   expiration to its own front-month) and reads real bid/ask/open interest
#   for the at-the-money call and put.
#
# *** WHY "CURRENT", NOT "AROUND HISTORICAL EARNINGS DATES" — DISCLOSED ***
# This project has never had access to historical option-chain data (same
# disclosed limitation as GST_RelativeIV_SignalQuality_Test.py and the
# stress-test script) — yfinance and every other source available here
# only exposes CURRENTLY listed chains, not what was quoted on a past date.
# There is no way to pull "MSFT's bid-ask spread the week before its
# 2023-04-25 earnings" after the fact. This check uses TODAY'S real chain
# as the best available proxy for each name's structural options-market
# liquidity (which options-market microstructure research finds is fairly
# persistent for a given underlying — a name with wide spreads today
# didn't likely have tight ones during an arbitrary past week, and vice
# versa) — it is a proxy for general tradeability, not a measurement of
# spreads specifically during a past earnings week. Each sampled name's
# CURRENT days-to-next-earnings is reported alongside so it's visible
# which ones happen to be earnings-proximate right now (a bonus,
# opportunistic partial check), not claimed as systematic coverage.
#
# Output: Small-Mid Cap Universe Expansion/SP600_Filtered_Universe.csv
#         Small-Mid Cap Universe Expansion/SP600_OptionsLiquidity_Sample_Results.csv
#
# *** THIS SCRIPT STOPS HERE — NO Z-SCORE/SIGNAL BACKTEST IS RUN ***
# Per the request: flag liquidity first, don't spend backtest effort on a
# universe whose options can't actually be traded at scale.

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import io
import random
import sys
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

USER_AGENT = "Harshith Akurati Independent Research hakurati11@gmail.com"
YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})
OUT_DIR = Path("Small-Mid Cap Universe Expansion")
OUT_DIR.mkdir(parents=True, exist_ok=True)
UNIVERSE_OUT = OUT_DIR / "SP600_Filtered_Universe.csv"
SAMPLE_OUT = OUT_DIR / "SP600_OptionsLiquidity_Sample_Results.csv"

SAMPLE_SIZE = 30
RANDOM_SEED = 42
N_TERCILES = 3

SLEEP_BETWEEN_CALLS_S = 0.4
MAX_ATTEMPTS = 3

LIQUIDITY_OI_FLOOR = 100     # conventional conservative "can you get filled at all" floor
LIQUIDITY_OI_STRICT = 500    # stricter cut, reported alongside for comparison
SPREAD_KILLS_EDGE_PCT = 15.0    # low end of the requested 15-20% "plausibly kills the edge" range
SPREAD_KILLS_EDGE_PCT_HIGH = 20.0
NEAR_EARNINGS_DAYS = 30       # informational only — "happens to have earnings coming up soon"

# Reused verbatim from GST_Live_Signal_Engine.py so the filter is identical,
# not re-derived — see that script's header for the validation history.
COMMON_WORDS = {
    "are", "low", "bro",
    "all", "app", "ball", "cat", "cost", "doc", "fast", "fix", "ice", "key",
    "met", "now", "peg", "tap", "well", "xyz", "yum",
}


def is_ambiguous(ticker: str) -> bool:
    base = ticker.split("-")[0]
    if len(base) <= 2:
        return True
    return base.lower() in COMMON_WORDS


def fetch_sp600_constituents() -> pd.DataFrame:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.verify = False
    resp = session.get("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    sp600 = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
    sp600["Symbol"] = sp600["Symbol"].str.upper().str.replace(".", "-", regex=False)
    return sp600.rename(columns={"Symbol": "ticker", "Security": "company", "GICS Sector": "sector"})


def check_options_and_marketcap(ticker: str) -> dict:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            tk = yf.Ticker(ticker, session=YF_SESSION)
            expirations = tk.options
            cap = None
            try:
                cap = tk.fast_info.get("marketCap")
            except Exception:
                pass
            return {"has_options": bool(expirations), "n_expirations": len(expirations) if expirations else 0,
                    "market_cap": float(cap) if cap else None}
        except Exception as e:
            if attempt == MAX_ATTEMPTS:
                return {"has_options": False, "n_expirations": 0, "market_cap": None, "error": str(e)}
            time.sleep(1.0 * attempt)
    return {"has_options": False, "n_expirations": 0, "market_cap": None}


def nearest_expiration(expirations: tuple, target_days: int = 21) -> str | None:
    today = datetime.now(timezone.utc).date()
    parsed = [(abs((datetime.strptime(e, "%Y-%m-%d").date() - today).days), e) for e in expirations]
    if not parsed:
        return None
    return min(parsed, key=lambda t: abs(t[0] - target_days))[1]


def has_any_weekly_like_expiration(expirations: tuple, max_days: int = 10) -> bool:
    today = datetime.now(timezone.utc).date()
    return any((datetime.strptime(e, "%Y-%m-%d").date() - today).days <= max_days for e in expirations)


def pull_atm_spread(ticker: str, include_earnings: bool = True) -> dict:
    result = {"ticker": ticker, "status": "ok"}
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        expirations = tk.options
        if not expirations:
            result["status"] = "no_options_listed"
            return result

        result["n_expirations_listed"] = len(expirations)
        result["has_weekly_like_expiration_le10d"] = has_any_weekly_like_expiration(expirations)

        exp = nearest_expiration(expirations)
        result["expiration_used"] = exp
        today = datetime.now(timezone.utc).date()
        result["days_to_expiration"] = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days

        hist = tk.history(period="5d")
        if hist.empty:
            result["status"] = "no_price_data"
            return result
        spot = float(hist["Close"].iloc[-1])
        result["spot_price"] = round(spot, 2)

        chain = tk.option_chain(exp)
        calls, puts = chain.calls, chain.puts
        if calls.empty or puts.empty:
            result["status"] = "empty_chain"
            return result

        call_row = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]].iloc[0]
        put_row = puts.iloc[(puts["strike"] - spot).abs().argsort()[:1]].iloc[0]

        call_bid, call_ask = float(call_row["bid"]), float(call_row["ask"])
        put_bid, put_ask = float(put_row["bid"]), float(put_row["ask"])
        call_oi = int(call_row["openInterest"]) if pd.notna(call_row["openInterest"]) else 0
        put_oi = int(put_row["openInterest"]) if pd.notna(put_row["openInterest"]) else 0

        call_mid = (call_bid + call_ask) / 2
        put_mid = (put_bid + put_ask) / 2
        straddle_premium = call_mid + put_mid
        straddle_spread_dollars = (call_ask - call_bid) + (put_ask - put_bid)

        result.update({
            "call_strike": float(call_row["strike"]), "put_strike": float(put_row["strike"]),
            "call_bid": call_bid, "call_ask": call_ask, "call_oi": call_oi,
            "put_bid": put_bid, "put_ask": put_ask, "put_oi": put_oi,
            "straddle_premium": round(straddle_premium, 4),
            "straddle_spread_dollars": round(straddle_spread_dollars, 4),
            "straddle_spread_pct_of_premium": round(straddle_spread_dollars / straddle_premium * 100, 2) if straddle_premium > 0 else None,
            "min_leg_open_interest": min(call_oi, put_oi),
            "liquid_oi_ge_100": min(call_oi, put_oi) >= LIQUIDITY_OI_FLOOR,
            "liquid_oi_ge_500": min(call_oi, put_oi) >= LIQUIDITY_OI_STRICT,
        })

        if include_earnings:
            try:
                edates = tk.get_earnings_dates(limit=8)
                if edates is not None and not edates.empty:
                    future = sorted(d.date() for d in pd.to_datetime(edates.index).tz_localize(None).normalize()
                                     if d.date() >= today)
                    result["days_to_next_earnings"] = (future[0] - today).days if future else None
                    result["near_earnings_now"] = (result["days_to_next_earnings"] is not None and
                                                    result["days_to_next_earnings"] <= NEAR_EARNINGS_DAYS)
            except Exception:
                result["days_to_next_earnings"] = None
                result["near_earnings_now"] = None

    except Exception as e:
        result["status"] = f"error: {e}"
    return result


def main():
    print("*** SMALL/MID-CAP UNIVERSE EXPANSION — LIQUIDITY GATING CHECK ***\n")
    print("PHASE A: building filtered S&P 600 candidate universe...\n")

    sp600 = fetch_sp600_constituents()
    print(f"S&P 600 constituents (Wikipedia snapshot): n={len(sp600)}")

    sp600["ambiguous_symbol"] = sp600["ticker"].apply(is_ambiguous)
    n_ambiguous = int(sp600["ambiguous_symbol"].sum())
    clear = sp600[~sp600["ambiguous_symbol"]].copy()
    print(f"Excluded as ambiguous symbol: {n_ambiguous}   Remaining (clear): {len(clear)}\n")

    print("Checking options availability + market cap per candidate (yfinance, one call each)...")
    opt_rows = []
    for i, ticker in enumerate(clear["ticker"], start=1):
        info = check_options_and_marketcap(ticker)
        opt_rows.append(info)
        if i % 50 == 0:
            print(f"  {i}/{len(clear)} checked...")
        time.sleep(SLEEP_BETWEEN_CALLS_S)
    opt_df = pd.DataFrame(opt_rows)
    clear = pd.concat([clear.reset_index(drop=True), opt_df.reset_index(drop=True)], axis=1)

    n_has_options = int(clear["has_options"].sum())
    print(f"\nHave >=1 listed option expiration: {n_has_options} / {len(clear)}")

    filtered_universe = clear[clear["has_options"]].copy()
    filtered_universe = filtered_universe.dropna(subset=["market_cap"])
    print(f"Final filtered universe (unambiguous + options available + market-cap available): n={len(filtered_universe)}\n")

    filtered_universe.to_csv(UNIVERSE_OUT, index=False)
    print(f"Wrote: {UNIVERSE_OUT}\n")

    print("PHASE B: stratified ~30-name sample + real options liquidity pull...\n")

    fu = filtered_universe.sort_values("market_cap").reset_index(drop=True)
    tercile_bounds = np.array_split(fu.index, N_TERCILES)
    rng = random.Random(RANDOM_SEED)
    per_tercile = SAMPLE_SIZE // N_TERCILES
    sampled_idx = []
    for bound in tercile_bounds:
        pool = list(bound)
        take = min(per_tercile, len(pool))
        sampled_idx.extend(rng.sample(pool, take))
    sample_universe = fu.loc[sampled_idx].sort_values("market_cap").reset_index(drop=True)
    print(f"Sampled {len(sample_universe)} names across {N_TERCILES} market-cap terciles (seed={RANDOM_SEED}):")
    print(f"  market cap range: ${sample_universe['market_cap'].min()/1e6:.0f}M - ${sample_universe['market_cap'].max()/1e6:.0f}M\n")

    print("Pulling REAL current option chains (bid/ask/open interest, ATM call+put)...")
    results = []
    for i, ticker in enumerate(sample_universe["ticker"], start=1):
        res = pull_atm_spread(ticker)
        results.append(res)
        status = res.get("status", "ok")
        spread = res.get("straddle_spread_pct_of_premium")
        print(f"  [{i}/{len(sample_universe)}] {ticker}: status={status}"
              + (f"  spread={spread:.1f}% of premium  min_OI={res.get('min_leg_open_interest')}" if spread is not None else ""))
        time.sleep(SLEEP_BETWEEN_CALLS_S)

    sample_df = pd.DataFrame(results)
    sample_df = sample_df.merge(sample_universe[["ticker", "company", "sector", "market_cap"]], on="ticker", how="left")
    sample_df.to_csv(SAMPLE_OUT, index=False)
    print(f"\nWrote: {SAMPLE_OUT}\n")

    usable = sample_df[sample_df["straddle_spread_pct_of_premium"].notna()]
    n_usable = len(usable)
    n_no_options = (sample_df["status"] == "no_options_listed").sum()
    n_other_fail = len(sample_df) - n_usable - n_no_options

    print("=== RESULTS ===")
    print(f"Sampled: {len(sample_df)}   Usable ATM spread pulled: {n_usable}   "
          f"No options listed: {n_no_options}   Other failure: {n_other_fail}\n")

    if n_usable == 0:
        print("No usable spread data — cannot assess liquidity. Stopping (no backtest run).")
        return

    median_spread = usable["straddle_spread_pct_of_premium"].median()
    mean_spread = usable["straddle_spread_pct_of_premium"].mean()
    n_liquid_100 = int(usable["liquid_oi_ge_100"].sum())
    n_liquid_500 = int(usable["liquid_oi_ge_500"].sum())
    n_has_weekly = int(usable["has_weekly_like_expiration_le10d"].sum())

    print(f"Median straddle bid-ask spread, % of premium: {median_spread:.1f}%")
    print(f"Mean straddle bid-ask spread, % of premium:   {mean_spread:.1f}%")
    print(f"Names with min-leg open interest >= {LIQUIDITY_OI_FLOOR}: {n_liquid_100}/{n_usable} ({n_liquid_100/n_usable*100:.0f}%)")
    print(f"Names with min-leg open interest >= {LIQUIDITY_OI_STRICT}: {n_liquid_500}/{n_usable} ({n_liquid_500/n_usable*100:.0f}%)")
    print(f"Names with a weekly-like expiration (<=10d out) available: {n_has_weekly}/{n_usable} "
          f"({n_has_weekly/n_usable*100:.0f}%) — relevant since this project's short-dated earnings-week "
          f"structure needs near-dated options to exist at all\n")

    print("Full per-name detail:")
    cols = ["ticker", "market_cap", "straddle_spread_pct_of_premium", "min_leg_open_interest",
            "liquid_oi_ge_100", "has_weekly_like_expiration_le10d", "days_to_next_earnings"]
    print(usable[cols].sort_values("straddle_spread_pct_of_premium").to_string(index=False))

    print(f"\n=== VERDICT ===")
    if median_spread > SPREAD_KILLS_EDGE_PCT_HIGH:
        print(f"*** FLAG: median spread ({median_spread:.1f}%) is ABOVE the {SPREAD_KILLS_EDGE_PCT_HIGH:g}% threshold. ***")
        print("Spreads this wide will very likely consume most or all of any STRONG_EARNINGS-style edge on this")
        print("universe (the original 425-ticker backtest's median P&L was ~130%, but that's against a ~5%")
        print("all-in cost assumption -- a >20% round-trip spread on top of the entry premium is a categorically")
        print("different cost regime). RECOMMENDATION: do not proceed to a full z-score/signal backtest on the")
        print("full S&P 600 as constructed here. If pursuing this universe at all, restrict to a liquid subset")
        print(f"(e.g. only names with min_leg_open_interest >= {LIQUIDITY_OI_STRICT} and a weekly-like expiration)")
        print("and re-run this same liquidity check on THAT subset first.")
    elif median_spread > SPREAD_KILLS_EDGE_PCT:
        print(f"*** FLAG: median spread ({median_spread:.1f}%) is within the requested 15-20% caution band. ***")
        print("This is borderline -- plausibly large enough to materially erode the edge, not obviously large")
        print("enough to kill it outright. RECOMMENDATION: do not run the full backtest on the unfiltered S&P 600")
        print(f"universe. Restrict first to the liquid subset (min_leg_open_interest >= {LIQUIDITY_OI_FLOOR}) and")
        print("re-run this liquidity check on that narrower list before committing backtest effort.")
    else:
        print(f"Median spread ({median_spread:.1f}%) is below the 15-20% caution threshold.")
        print("Liquidity does not look like an obvious edge-killer for this sample. A full backtest MAY be")
        print(f"worth running, but restrict the tradeable universe to names with min_leg_open_interest >= "
              f"{LIQUIDITY_OI_FLOOR} (see SP600_Filtered_Universe.csv / sample results) -- the illiquid tail")
        print("of this universe should still be excluded even if the median looks fine.")


if __name__ == "__main__":
    main()
