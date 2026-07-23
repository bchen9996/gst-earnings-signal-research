#!/usr/bin/env python3
# LIQUIDITY-FIRST UNIVERSE EXPANSION — broader candidate pool than the
# existing 425-ticker S&P 500 list, screened for real options liquidity
# BEFORE any z-score/earnings backtest is attempted (same order of
# operations as GST_SmallMidCap_UniverseExpansion_LiquidityCheck.py, which
# flagged the S&P 600 as untradeable at the population level: median
# spread 61.8% of premium, 96% of sampled names failing a 100-OI floor).
#
# *** "RUSSELL 1000" PROXY — DISCLOSED SUBSTITUTION ***
# True Russell 1000 constituent data is FTSE Russell's proprietary product
# and isn't available from any free source this project has access to (no
# Wikipedia table, unlike S&P 500/400/600). Russell 1000 = large+mid cap by
# construction (Russell 2000 is the small-cap complement, already covered
# here by the S&P 600 test). The closest free, disclosed proxy with the
# same large+mid coverage is S&P 500 UNION S&P 400 (mid-cap) — both have
# clean Wikipedia constituent tables, same source/method already used for
# the existing 425-ticker list and the S&P 600 test. This is NOT literally
# Russell 1000 membership; it's the best available free substitute with
# matching size coverage, disclosed rather than silently substituted.
#
# *** DIFFERENCE FROM THE S&P 600 TEST — FULL POOL, NOT A SAMPLE ***
# The S&P 600 check spot-checked a stratified 30-name sample to get a
# population-level verdict quickly. Per this request, every candidate that
# survives the ambiguous-symbol + has-options filter gets its OWN real ATM
# straddle spread/open-interest pull (not sampled) — since the goal here is
# a per-ticker keep/reject universe list, not just a population verdict.
# This is a much larger number of real option-chain pulls and takes
# considerably longer. Earnings-date lookup (informational only in the
# S&P 600 script) is skipped per-ticker here to cut the larger run's
# time — it isn't part of the pass/fail liquidity criteria.
#
# Reuses is_ambiguous(), COMMON_WORDS, check_options_and_marketcap(),
# pull_atm_spread(), YF_SESSION, and the LIQUIDITY_OI_FLOOR/STRICT
# constants VERBATIM from GST_SmallMidCap_UniverseExpansion_LiquidityCheck.py
# (imported, not re-derived) so the screening criteria are identical to
# what already flagged S&P 600. The existing 425-ticker universe is
# imported directly from GST_Live_Signal_Engine.py (not retyped) for the
# overlap comparison.
#
# PASS CRITERIA (per ticker, matching the request):
#   straddle_spread_pct_of_premium < 20%  AND  min_leg_open_interest >= 100
#
# *** NO Z-SCORE / EARNINGS BACKTEST IS RUN HERE — liquidity screening only ***
#
# Output: Small-Mid Cap Universe Expansion/Russell1000Proxy_Filtered_Universe.csv
#         Small-Mid Cap Universe Expansion/Russell1000Proxy_LiquidityScreen_FullResults.csv

from __future__ import annotations
from pathlib import Path
import io
import sys
import time
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

from GST_SmallMidCap_UniverseExpansion_LiquidityCheck import (
    is_ambiguous, check_options_and_marketcap, pull_atm_spread,
    LIQUIDITY_OI_FLOOR, LIQUIDITY_OI_STRICT, USER_AGENT,
)
from GST_Live_Signal_Engine import TICKERS as EXISTING_425

OUT_DIR = Path("Small-Mid Cap Universe Expansion")
OUT_DIR.mkdir(parents=True, exist_ok=True)
UNIVERSE_OUT = OUT_DIR / "Russell1000Proxy_Filtered_Universe.csv"
FULL_RESULTS_OUT = OUT_DIR / "Russell1000Proxy_LiquidityScreen_FullResults.csv"

SLEEP_BETWEEN_CALLS_S = 0.4
SPREAD_PASS_PCT = 20.0
OI_PASS_FLOOR = LIQUIDITY_OI_FLOOR  # 100, same bar that flagged S&P 600


def fetch_index_table(url: str) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.verify = False
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
    df["Symbol"] = df["Symbol"].str.upper().str.replace(".", "-", regex=False)
    return df.rename(columns={"Symbol": "ticker", "Security": "company", "GICS Sector": "sector"})


def main():
    print("*** LIQUIDITY-FIRST UNIVERSE EXPANSION — Russell 1000 proxy (S&P 500 U S&P 400) ***\n")
    print("PHASE A: building broader candidate pool...\n")

    sp500 = fetch_index_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    sp400 = fetch_index_table("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")
    print(f"S&P 500 constituents: {len(sp500)}   S&P 400 constituents: {len(sp400)}")

    pool = pd.concat([sp500, sp400], ignore_index=True).drop_duplicates(subset="ticker").reset_index(drop=True)
    print(f"Union (Russell 1000 proxy), deduplicated: {len(pool)}\n")

    pool["ambiguous_symbol"] = pool["ticker"].apply(is_ambiguous)
    n_ambiguous = int(pool["ambiguous_symbol"].sum())
    clear = pool[~pool["ambiguous_symbol"]].copy()
    print(f"Excluded as ambiguous symbol: {n_ambiguous}   Remaining (clear): {len(clear)}\n")

    print("Checking options availability + market cap per candidate (yfinance, one call each)...")
    opt_rows = []
    for i, ticker in enumerate(clear["ticker"], start=1):
        info = check_options_and_marketcap(ticker)
        opt_rows.append(info)
        if i % 100 == 0:
            print(f"  {i}/{len(clear)} checked...")
        time.sleep(SLEEP_BETWEEN_CALLS_S)
    opt_df = pd.DataFrame(opt_rows)
    clear = pd.concat([clear.reset_index(drop=True), opt_df.reset_index(drop=True)], axis=1)

    n_has_options = int(clear["has_options"].sum())
    print(f"\nHave >=1 listed option expiration: {n_has_options} / {len(clear)}")

    filtered_universe = clear[clear["has_options"]].copy().dropna(subset=["market_cap"])
    filtered_universe = filtered_universe.sort_values("ticker").reset_index(drop=True)
    print(f"Final Phase A filtered candidate pool: n={len(filtered_universe)}\n")
    filtered_universe.to_csv(UNIVERSE_OUT, index=False)
    print(f"Wrote: {UNIVERSE_OUT}\n")

    print("PHASE B: real ATM options liquidity pull, EVERY candidate (not sampled)...\n")
    results = []
    n = len(filtered_universe)
    for i, ticker in enumerate(filtered_universe["ticker"], start=1):
        res = pull_atm_spread(ticker, include_earnings=False)
        results.append(res)
        if i % 25 == 0 or i == n:
            print(f"  {i}/{n} pulled...")
        time.sleep(SLEEP_BETWEEN_CALLS_S)

    results_df = pd.DataFrame(results)
    results_df = results_df.merge(filtered_universe[["ticker", "company", "sector", "market_cap"]],
                                   on="ticker", how="left")

    results_df["passes_liquidity_screen"] = (
        results_df["straddle_spread_pct_of_premium"].notna()
        & (results_df["straddle_spread_pct_of_premium"] < SPREAD_PASS_PCT)
        & (results_df["min_leg_open_interest"] >= OI_PASS_FLOOR)
    )
    results_df["in_existing_425"] = results_df["ticker"].isin(EXISTING_425)

    results_df.to_csv(FULL_RESULTS_OUT, index=False)
    print(f"\nWrote: {FULL_RESULTS_OUT}\n")

    usable = results_df[results_df["straddle_spread_pct_of_premium"].notna()]
    n_usable = len(usable)
    n_no_options = (results_df["status"] == "no_options_listed").sum()
    n_other_fail = len(results_df) - n_usable - n_no_options

    print("=== RESULTS ===")
    print(f"Candidates screened: {len(results_df)}   Usable ATM spread pulled: {n_usable}   "
          f"No options listed at pull time: {n_no_options}   Other failure: {n_other_fail}\n")

    if n_usable:
        print(f"Median straddle spread, % of premium (usable names): {usable['straddle_spread_pct_of_premium'].median():.1f}%")
        print(f"Names with min-leg OI >= {OI_PASS_FLOOR}: {int(usable['min_leg_open_interest'].ge(OI_PASS_FLOOR).sum())}/{n_usable}")
        print(f"Names with min-leg OI >= {LIQUIDITY_OI_STRICT}: {int(usable['min_leg_open_interest'].ge(LIQUIDITY_OI_STRICT).sum())}/{n_usable}\n")

    passing = results_df[results_df["passes_liquidity_screen"]].copy()
    n_pass = len(passing)
    n_overlap = int(passing["in_existing_425"].sum())
    new_liquid = passing[~passing["in_existing_425"]].sort_values("market_cap", ascending=False)
    n_new = len(new_liquid)

    print(f"=== PASS CRITERIA: spread < {SPREAD_PASS_PCT:g}% of premium AND min-leg OI >= {OI_PASS_FLOOR} ===")
    print(f"Names passing: {n_pass} / {len(results_df)} screened ({n_pass/len(results_df)*100:.1f}%)")
    print(f"Overlap with existing 425-ticker list: {n_overlap}/{n_pass}")
    print(f"Genuinely NEW liquid tickers (pass AND not already in the 425): {n_new}\n")

    if n_new:
        print("New liquid tickers (sorted by market cap, largest first):")
        print(new_liquid[["ticker", "company", "sector", "market_cap",
                           "straddle_spread_pct_of_premium", "min_leg_open_interest"]].to_string(index=False))
    else:
        print("No genuinely new liquid tickers found beyond the existing 425.")

    print(f"\n*** NO z-score/earnings backtest was run — liquidity screening only, per the request. ***")


if __name__ == "__main__":
    main()
