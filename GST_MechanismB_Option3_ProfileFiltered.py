#!/usr/bin/env python3
# Mechanism B Option 3 — Profile-filtered validation. Does the price/
# volume signal work specifically within the false-negative PROFILE
# (small/mid-cap, specific sectors, quiet prior-quarter GST history) even
# though it was weak across the full 978-event population (Task 4)?
#
# Step 1: filter ALL 978 events (not just false negatives) to the profile:
#   market_cap < $200B AND sector IN (Consumer Cyclical, Industrials,
#   Financial Services, Basic Materials, Energy) AND prior_quarter_mean_z < 1.5
# Report n and local base rate. Stop here (no Step 2/3) if n<50 or local
# base rate <30%.
#
# Step 2 (only if Step 1 passes): precision/recall for price_volume_score
# at the same thresholds as Task 4, within the filtered population, vs
# global base rate / local base rate / GST precision in the same population.
#
# Step 3: flag genuine Mechanism-B-for-this-profile signal if precision
# clears local_base_rate+10pt at any threshold with recall>10%.
#
# market_cap, sector, prior_quarter_mean_z reuse the EXACT methodology
# from GST_Task1_FalseNegatives.py (KNOWN_MARKET_CAPS + fresh pull for the
# rest; AllTickers_Sectors.csv; 3-prior-earnings-dates mean z, 3-day match
# tolerance) so profile membership is computed identically to how the
# false-negative characteristics that DEFINED this profile were computed.
#
# Output: Live Signal Engine/Mechanism_B/option3_profile_filtered_validation.csv

from __future__ import annotations
from pathlib import Path
import sys, time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

EVENT_LEVEL_PATH = Path("Live Signal Engine") / "Mechanism_B" / "mechanism_b_event_level.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
ZSCORE_PATH = Path("Live Signal Engine") / "AllTickers_ZscoreSeries.csv"
OUT_PATH = Path("Live Signal Engine") / "Mechanism_B" / "option3_profile_filtered_validation.csv"

KNOWN_MARKET_CAPS = {
    "AAPL": 4631.2e9, "ABBV": 438.3e9, "ADBE": 88.9e9, "AMZN": 2639.1e9, "BKR": 57.1e9,
    "BRK-B": 1064.9e9, "COHR": 63.5e9, "CTSH": 20.1e9, "DELL": 281.1e9, "DVN": 48.7e9,
    "GME": 9.7e9, "GOOGL": 4358.5e9, "GPN": 20.8e9, "INTC": 552.1e9, "LDOS": 13.5e9,
    "MCHP": 48.1e9, "MSFT": 2860.7e9, "NCLH": 9.0e9, "NFLX": 308.9e9, "NKE": 65.7e9,
    "NVDA": 5109.7e9, "QCOM": 199.4e9, "SBUX": 120.8e9, "STZ": 22.9e9, "SYK": 126.4e9,
    "TSLA": 1531.4e9, "TTWO": 45.2e9, "UAL": 40.9e9,
}
PROFILE_MARKET_CAP_MAX = 200e9
PROFILE_SECTORS = {"Consumer Cyclical", "Industrials", "Financial Services", "Basic Materials", "Energy"}
PROFILE_PRIOR_Q_Z_MAX = 1.5
PRIOR_QUARTERS = 3
WEEK_MATCH_TOL_DAYS = 3
MIN_N_FOR_POWER = 50
MIN_LOCAL_BASE_RATE = 0.30
PV_THRESHOLDS = [0, 0.25, 0.5, 0.75, 1.0]
GLOBAL_BASE_RATE = 0.254
PRECISION_LIFT_FLAG = 0.10
RECALL_FLOOR_FLAG = 0.10

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def fetch_market_cap(ticker: str, max_attempts: int = 3) -> float | None:
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            cap = tk.fast_info.get("marketCap") or tk.info.get("marketCap")
            if cap:
                return float(cap)
        except Exception as e:
            print(f"  [{ticker}] attempt {attempt} failed: {e}")
        if attempt < max_attempts:
            time.sleep(5)
    return None


def precision_recall(predicted_positive: np.ndarray, actual_positive: np.ndarray) -> dict:
    tp = int((predicted_positive & actual_positive).sum())
    fp = int((predicted_positive & ~actual_positive).sum())
    fn = int((~predicted_positive & actual_positive).sum())
    n_flagged = int(predicted_positive.sum())
    n_actual = int(actual_positive.sum())
    precision = tp / n_flagged if n_flagged > 0 else None
    recall = tp / n_actual if n_actual > 0 else None
    return {"n_flagged": n_flagged, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None}


def main():
    print("*** Mechanism B Option 3: Profile-filtered validation ***\n")

    events = pd.read_csv(EVENT_LEVEL_PATH)
    events["earnings_date"] = pd.to_datetime(events["earnings_date"])
    print(f"Loaded event-level data: n={len(events)}\n")

    all_tickers = sorted(events["ticker"].unique())
    print(f"Filling market cap for {len(all_tickers)} tickers...")
    market_caps = dict(KNOWN_MARKET_CAPS)
    missing = [t for t in all_tickers if t not in market_caps]
    for i, t in enumerate(missing, start=1):
        cap = fetch_market_cap(t)
        market_caps[t] = cap
        print(f"  [{i}/{len(missing)}] {t}: {'$'+format(cap/1e9,'.1f')+'B' if cap else 'N/A'}")
        time.sleep(0.8)
    print()

    sector_df = pd.read_csv(SECTOR_PATH)
    ticker_to_sector = dict(zip(sector_df["ticker"], sector_df["sector"]))

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])

    z_df = pd.read_csv(ZSCORE_PATH)
    z_df["week"] = pd.to_datetime(z_df["week"])
    z_by_ticker = {t: g.set_index("week")["zscore_simple"] for t, g in z_df.groupby("ticker")}

    def zscore_near(ticker, target_date, tol=WEEK_MATCH_TOL_DAYS):
        series = z_by_ticker.get(ticker)
        if series is None or series.empty:
            return None
        diffs = np.abs((series.index - target_date).days.to_numpy())
        nearest_pos = int(diffs.argmin())
        if int(diffs[nearest_pos]) > tol:
            return None
        val = series.iloc[nearest_pos]
        return float(val) if pd.notna(val) else None

    def prior_quarter_mean_z(ticker, edate):
        dates = earnings_df[earnings_df["ticker"] == ticker]["earnings_date"].tolist()
        prior = sorted([d for d in dates if d < edate], reverse=True)[:PRIOR_QUARTERS]
        zs = [z for z in (zscore_near(ticker, d) for d in prior) if z is not None]
        return float(np.mean(zs)) if zs else None

    print("Computing profile characteristics (market_cap, sector, prior_quarter_mean_z) for all 978 events...")
    events["market_cap"] = events["ticker"].map(market_caps)
    events["sector"] = events["ticker"].map(ticker_to_sector)
    events["prior_quarter_mean_z"] = [prior_quarter_mean_z(t, d) for t, d in zip(events["ticker"], events["earnings_date"])]
    print("Done.\n")

    # === STEP 1 ===
    print("=== STEP 1: Profile filter applied to all 978 events ===")
    profile_mask = (
        (events["market_cap"] < PROFILE_MARKET_CAP_MAX) &
        (events["sector"].isin(PROFILE_SECTORS)) &
        (events["prior_quarter_mean_z"] < PROFILE_PRIOR_Q_Z_MAX)
    )
    n_missing_inputs = int((events["market_cap"].isna() | events["sector"].isna() | events["prior_quarter_mean_z"].isna()).sum())
    print(f"Events with missing market_cap/sector/prior_quarter_mean_z (excluded from filter by NaN comparison): {n_missing_inputs}")

    profile = events[profile_mask].copy()
    n_profile = len(profile)
    local_base_rate = profile["large_move"].mean() if n_profile > 0 else None

    print(f"Profile filter: market_cap<${PROFILE_MARKET_CAP_MAX/1e9:.0f}B AND sector in {sorted(PROFILE_SECTORS)} "
          f"AND prior_quarter_mean_z<{PROFILE_PRIOR_Q_Z_MAX}")
    print(f"Events matching profile: n={n_profile}/{len(events)}")
    if n_profile > 0:
        print(f"Local base rate (fraction large_move=True within profile): {local_base_rate*100:.1f}%")
        print(f"Global base rate (from Task 4, full population): {GLOBAL_BASE_RATE*100:.1f}%")
        print(f"Sector breakdown within profile:\n{profile['sector'].value_counts()}")
    print()

    underpowered = n_profile < MIN_N_FOR_POWER
    base_rate_too_low = (local_base_rate is None) or (local_base_rate < MIN_LOCAL_BASE_RATE)

    step1_summary = pd.DataFrame([{
        "step": 1, "n_total_events": len(events), "n_profile_matched": n_profile,
        "local_base_rate_pct": round(local_base_rate * 100, 1) if local_base_rate is not None else None,
        "global_base_rate_pct": round(GLOBAL_BASE_RATE * 100, 1),
        "n_missing_inputs": n_missing_inputs,
        "underpowered_n_lt_50": underpowered, "base_rate_lt_30pct": base_rate_too_low,
        "proceed_to_step2": not (underpowered or base_rate_too_low),
    }])

    if underpowered or base_rate_too_low:
        reason = []
        if underpowered:
            reason.append(f"n={n_profile} < {MIN_N_FOR_POWER}")
        if base_rate_too_low:
            reason.append(f"local base rate {local_base_rate*100:.1f}% < {MIN_LOCAL_BASE_RATE*100:.0f}%"
                          if local_base_rate is not None else "local base rate undefined (n=0)")
        print(f"*** FLAGGED UNDERPOWERED / NOT MEANINGFULLY ABOVE BASE RATE: {', '.join(reason)}. STOPPING per instructions. ***")
        combined = pd.concat([step1_summary, pd.DataFrame([{}]), profile], ignore_index=True, sort=False)
        combined.to_csv(OUT_PATH, index=False)
        print(f"\nWrote (Step 1 only): {OUT_PATH}")
        return

    print("Step 1 PASSED. Proceeding to Step 2.\n")

    # === STEP 2 ===
    print("=== STEP 2: Precision/recall within profile-filtered population ===")
    actual = profile["large_move"].to_numpy(dtype=bool)

    gst_pred = profile["had_spike"].to_numpy(dtype=bool)
    gst_pr = precision_recall(gst_pred, actual)
    print(f"GST (had_spike) in filtered population: n_flagged={gst_pr['n_flagged']}  "
          f"precision={gst_pr['precision']}  recall={gst_pr['recall']}\n")

    pv_valid = profile["price_volume_score"].notna()
    n_pv_valid = int(pv_valid.sum())
    print(f"Usable price_volume_score in profile: {n_pv_valid}/{n_profile}\n")

    step2_rows = []
    for thr in PV_THRESHOLDS:
        pred = np.where(pv_valid, profile["price_volume_score"].fillna(-999) >= thr, False)
        pr = precision_recall(pred, actual)
        precision_str = f"{pr['precision']*100:.1f}%" if pr['precision'] is not None else "n/a"
        recall_str = f"{pr['recall']*100:.1f}%" if pr['recall'] is not None else "n/a"
        print(f"  PV score>={thr:<5} n_flagged={pr['n_flagged']:<4} precision={precision_str:<8} recall={recall_str}")
        step2_rows.append({"step": 2, "signal": "price_volume", "threshold": f"score>={thr}", **pr,
                           "local_base_rate_pct": round(local_base_rate * 100, 1),
                           "global_base_rate_pct": round(GLOBAL_BASE_RATE * 100, 1)})
    step2_rows.append({"step": 2, "signal": "GST_had_spike", "threshold": "z>=5,gap<=5d", **gst_pr,
                       "local_base_rate_pct": round(local_base_rate * 100, 1),
                       "global_base_rate_pct": round(GLOBAL_BASE_RATE * 100, 1)})
    step2_df = pd.DataFrame(step2_rows)
    print()

    # === STEP 3 ===
    print("=== STEP 3: Verdict ===")
    pv_only = step2_df[step2_df["signal"] == "price_volume"].copy()
    pv_only["precision_lift_over_local"] = pv_only["precision"] - local_base_rate
    qualifying = pv_only[(pv_only["precision_lift_over_local"] > PRECISION_LIFT_FLAG) & (pv_only["recall"] > RECALL_FLOOR_FLAG)]

    if len(qualifying) > 0:
        print(f"GENUINE MECHANISM B SIGNAL FOUND for this profile at threshold(s):")
        print(qualifying[["threshold", "precision", "recall", "precision_lift_over_local"]].to_string(index=False))
        verdict = "GENUINE_SIGNAL"
    else:
        print("NO threshold clears precision > local_base_rate+10pt AND recall>10%.")
        print("Conclusion: Mechanism B (8-K frequency, price/volume) does NOT work even for the specific")
        print("false-negative profile. Would require paid data (options flow, analyst dispersion, transcript NLP).")
        verdict = "NO_SIGNAL_NEEDS_PAID_DATA"
    print(f"\nVerdict: {verdict}")

    verdict_row = pd.DataFrame([{"step": 3, "verdict": verdict, "n_qualifying_thresholds": len(qualifying)}])

    combined = pd.concat([step1_summary, pd.DataFrame([{}]), step2_df, pd.DataFrame([{}]), verdict_row,
                          pd.DataFrame([{}]), profile], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
