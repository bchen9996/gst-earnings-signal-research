#!/usr/bin/env python3
# MATCHED CONTROL GROUP -- CANONICAL RECOMPUTE. Re-derives the z>=10 vs
# z=5-9.99 matched-control-excess split against the 152-event fixed-window
# canonical population (Live Signal Engine/FixedWindow_PerEvent_Canonical.csv)
# instead of the archived 147-event population
# (GST_MatchedControlGroup.py / MatchedControlGroup_Results.csv).
#
# SAME matching methodology as the original script, unchanged:
#   1. same ticker, different quarter, no z>=5 spike nearby (+/-10d), same
#      BMO/AMC, trailing-vol band 0.5x-2x -- nearest-vol match wins.
#   2. fallback: cross-ticker, same GICS sector, market cap within ~3x,
#      same BMO/AMC, same vol band.
# Same Black-Scholes pricing (entry=anchor+2, exit=anchor+6, calibrated
# near-earnings IV markup, COST_LOADING=1.05) for the CONTROL side.
#
# KEY DIFFERENCE FROM THE ORIGINAL SCRIPT: the SIGNAL side is NOT re-priced
# here -- FixedWindow_PerEvent_Canonical.csv already has each signal event's
# entry_date/exit_date/pnl_pct/win computed under the canonical fixed-window
# z-score methodology, so those are used directly (single source of truth,
# avoids any risk of drift from re-deriving them a second time). Only the
# MATCHED CONTROL side is newly priced here. Signal-side trailing vol
# (needed only for control-matching, not for the signal's own P&L) is
# recomputed locally from the same daily excess-return files.
#
# The "clean" (non-signal) candidate-date exclusion pool still uses the
# original archived z>=4 spike-week list (group_a_z4_earnings_adjacent.csv)
# to decide which earnings dates are "too close to some kind of spike to
# use as a control" -- this is a conservative exclusion filter, not the
# population under study, so reusing it (rather than a canonical-method
# rescan of literally every week) is an unchanged, disclosed simplification
# carried over from the original script.
#
# Output: Live Signal Engine/MatchedControlGroup_CanonicalRecompute.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import sys
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

TICKERS_ORIGINAL = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
                     "INTC", "TTWO", "QCOM", "GME", "EBAY"]
TICKERS_BROAD50_CLEAR = ['ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
                          'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
                          'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
                          'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM']
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
CANONICAL_PATH = Path("Live Signal Engine") / "FixedWindow_PerEvent_Canonical.csv"
OUT_PATH = Path("Live Signal Engine") / "MatchedControlGroup_CanonicalRecompute.csv"

Z_THRESHOLD = 5.0
HIGH_CONFIDENCE_Z_THRESHOLD = 10.0
SPIKE_EXCLUSION_BUFFER_DAYS = 10
VOL_BAND_LOW, VOL_BAND_HIGH = 0.5, 2.0
MARKET_CAP_BAND = 3.0

ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

N_BOOTSTRAP = 10000
RANDOM_SEED = 42

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or df.empty:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def fetch_earnings_with_time(ticker: str) -> pd.DataFrame:
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        df = tk.get_earnings_dates(limit=40)
    except Exception as e:
        print(f"  [{ticker}] earnings pull failed: {e}")
        return pd.DataFrame(columns=["date", "bmo_amc"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "bmo_amc"])
    idx = pd.to_datetime(df.index)
    dates = idx.tz_localize(None) if idx.tz is None else idx.tz_convert("America/New_York").tz_localize(None)
    bmo_amc = ["BMO" if d.hour < 12 else "AMC" for d in dates]
    out = pd.DataFrame({"date": dates.normalize(), "bmo_amc": bmo_amc})
    return out.drop_duplicates(subset="date").reset_index(drop=True)


def fetch_market_cap(ticker: str) -> float | None:
    try:
        tk = yf.Ticker(ticker, session=YF_SESSION)
        cap = tk.fast_info.get("marketCap")
        return float(cap) if cap else None
    except Exception:
        return None


def week_start(d: pd.Timestamp) -> pd.Timestamp:
    d = pd.Timestamp(d)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


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


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def cumulative_return(daily, ret_col, start_date, end_date):
    mask = (daily["Date"] > start_date) & (daily["Date"] <= end_date)
    rets = daily.loc[mask, ret_col]
    return float((1 + rets).prod() - 1) if not rets.empty else None


def trailing_realized_vol(daily, ret_col, cutoff):
    hist = daily.loc[daily["Date"] < cutoff].tail(VOL_LOOKBACK_TRADING_DAYS)
    if len(hist) < MIN_VOL_HISTORY_DAYS:
        return None
    return float(hist[ret_col].std() * math.sqrt(252))


def price_event(daily, ret_col, anchor, markup):
    entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
    exit_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=EXIT_OFFSET_DAYS))
    if entry_date is None or exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    if dte_days <= 0:
        return None
    sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
    if sigma is None:
        return None
    iv = sigma * markup
    T = dte_days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    pnl_pct = (intrinsic - cost) / cost * 100
    return {"win": pnl_pct > 0, "pnl_pct": pnl_pct, "sigma": sigma}


def build_candidate_pool(earnings_by_ticker, spike_dates_by_ticker, daily_cache):
    rows = []
    for ticker, edf in earnings_by_ticker.items():
        spikes = spike_dates_by_ticker.get(ticker, [])
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        for _, r in edf.iterrows():
            edate = r["date"]
            if any(abs((edate - s).days) <= SPIKE_EXCLUSION_BUFFER_DAYS for s in spikes):
                continue
            anchor = week_start(edate)
            sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
            if sigma is None:
                continue
            rows.append({"ticker": ticker, "earnings_date": edate, "anchor": anchor,
                         "bmo_amc": r["bmo_amc"], "sigma": sigma})
    return pd.DataFrame(rows)


def find_match(signal_ticker, signal_anchor, signal_sigma, signal_bmo_amc,
               candidates: pd.DataFrame, sector_map, cap_map, used_counts):
    same = candidates[(candidates["ticker"] == signal_ticker) & (candidates["bmo_amc"] == signal_bmo_amc)].copy()
    same = same[(same["sigma"] >= signal_sigma * VOL_BAND_LOW) & (same["sigma"] <= signal_sigma * VOL_BAND_HIGH)]
    if not same.empty:
        same["vol_dist"] = (same["sigma"] - signal_sigma).abs()
        same["date_dist"] = (same["anchor"] - signal_anchor).abs()
        best = same.sort_values(["vol_dist", "date_dist"]).iloc[0]
        used_counts[(best["ticker"], best["anchor"])] = used_counts.get((best["ticker"], best["anchor"]), 0) + 1
        return {"match_type": "same_ticker", **best.to_dict()}

    sector = sector_map.get(signal_ticker)
    cap = cap_map.get(signal_ticker)
    pool = candidates[(candidates["ticker"] != signal_ticker) & (candidates["bmo_amc"] == signal_bmo_amc)].copy()
    if sector is not None:
        pool = pool[pool["ticker"].map(sector_map) == sector]
    if cap is not None:
        pool = pool[pool["ticker"].map(cap_map).apply(
            lambda c: c is not None and abs(math.log(c / cap)) < math.log(MARKET_CAP_BAND))]
    pool = pool[(pool["sigma"] >= signal_sigma * VOL_BAND_LOW) & (pool["sigma"] <= signal_sigma * VOL_BAND_HIGH)]
    if not pool.empty:
        pool["vol_dist"] = (pool["sigma"] - signal_sigma).abs()
        pool["date_dist"] = (pool["anchor"] - signal_anchor).abs()
        best = pool.sort_values(["vol_dist", "date_dist"]).iloc[0]
        used_counts[(best["ticker"], best["anchor"])] = used_counts.get((best["ticker"], best["anchor"]), 0) + 1
        return {"match_type": "cross_ticker_sector_cap", **best.to_dict()}

    return None


def bootstrap_ci(diffs: np.ndarray, n_boot: int, rng: np.random.Generator) -> tuple:
    n = len(diffs)
    boot_medians = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_medians[i] = np.median(diffs[idx])
    return float(np.percentile(boot_medians, 2.5)), float(np.percentile(boot_medians, 97.5))


def main():
    print("*** MATCHED CONTROL GROUP -- CANONICAL RECOMPUTE (152-event fixed-window population) ***\n")

    markup = load_calibrated_near_earnings_markup()

    canonical = pd.read_csv(CANONICAL_PATH)
    canonical["spike_week"] = pd.to_datetime(canonical["spike_week"])
    strong = canonical[(canonical["qualifies_z5"] == True) & (canonical["pnl_pct"].notna())].copy()  # noqa: E712
    print(f"Canonical signal events (n=152 population): n={len(strong)}\n")

    # "clean" exclusion pool still sourced from the archived z>=4 spike-week
    # list -- a conservative "is there ANY kind of spike nearby" filter for
    # building candidate control dates, not the population under study.
    archived_events = pd.read_csv(GROUP_A_PATH)
    all_z5 = archived_events[archived_events["zscore"] >= Z_THRESHOLD].copy()
    all_z5["spike_week"] = pd.to_datetime(all_z5["spike_week"])
    spike_dates_by_ticker = {t: sorted(g["spike_week"].tolist()) for t, g in all_z5.groupby("ticker")}

    sector_df = pd.read_csv(SECTOR_PATH)
    sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))

    print("Pulling market cap for all 28 canonical tickers...")
    cap_map = {}
    for i, t in enumerate(ALL_TICKERS, start=1):
        cap_map[t] = fetch_market_cap(t)
        if i % 15 == 0:
            print(f"  {i}/{len(ALL_TICKERS)}...")
        time.sleep(0.3)
    print()

    print("Pulling earnings dates + BMO/AMC classification for all 28 canonical tickers...")
    earnings_by_ticker = {}
    for i, t in enumerate(ALL_TICKERS, start=1):
        earnings_by_ticker[t] = fetch_earnings_with_time(t)
        if i % 15 == 0:
            print(f"  {i}/{len(ALL_TICKERS)}...")
        time.sleep(0.3)
    print()

    daily_cache = {t: load_daily_excess(t) for t in ALL_TICKERS}

    print("Building clean (non-signal) candidate pool...")
    candidates = build_candidate_pool(earnings_by_ticker, spike_dates_by_ticker, daily_cache)
    print(f"Candidate pool size: {len(candidates)}\n")

    print("Matching + pricing each signal event's control (signal side reused from canonical CSV)...")
    used_counts: dict = {}
    rows = []
    for _, ev in strong.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["fixed_window_zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue

        signal_sigma = trailing_realized_vol(daily, ret_col, anchor - timedelta(days=7))
        if signal_sigma is None:
            continue

        edf = earnings_by_ticker.get(ticker, pd.DataFrame())
        signal_bmo_amc = None
        if not edf.empty:
            gaps = (edf["date"] - anchor).abs()
            nearest = gaps.idxmin()
            if gaps.loc[nearest] <= timedelta(days=7):
                signal_bmo_amc = edf.loc[nearest, "bmo_amc"]
        if signal_bmo_amc is None:
            signal_bmo_amc = "AMC"

        match = find_match(ticker, anchor, signal_sigma, signal_bmo_amc, candidates, sector_map, cap_map, used_counts)

        base_row = {"ticker": ticker, "spike_week": anchor.date(), "zscore": round(float(zscore), 4),
                    "signal_pnl_pct": round(float(ev["pnl_pct"]), 2), "signal_win": bool(ev["win"])}

        if match is None:
            rows.append({**base_row, "match_type": "NO_MATCH_FOUND", "control_ticker": None,
                         "control_date": None, "control_pnl_pct": None, "control_win": None, "pnl_diff": None})
            continue

        control_daily = daily_cache.get(match["ticker"], pd.DataFrame())
        control_ret_col = f"{match['ticker']} Daily Return"
        control_priced = price_event(control_daily, control_ret_col, match["anchor"], markup)
        if control_priced is None:
            rows.append({**base_row, "match_type": "MATCH_UNPRICEABLE", "control_ticker": match["ticker"],
                         "control_date": match["earnings_date"].date(), "control_pnl_pct": None,
                         "control_win": None, "pnl_diff": None})
            continue

        rows.append({
            **base_row, "match_type": match["match_type"], "control_ticker": match["ticker"],
            "control_date": match["earnings_date"].date(),
            "control_pnl_pct": round(control_priced["pnl_pct"], 2), "control_win": control_priced["win"],
            "pnl_diff": round(ev["pnl_pct"] - control_priced["pnl_pct"], 2),
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}\n")

    usable = result[result["pnl_diff"].notna()].copy()
    n_no_match = (result["match_type"] == "NO_MATCH_FOUND").sum()
    n_unpriceable = (result["match_type"] == "MATCH_UNPRICEABLE").sum()

    print(f"Matched + priced: n={len(usable)} / {len(strong)}")
    print(f"No match found: {n_no_match}   Match found but unpriceable: {n_unpriceable}\n")

    def group_stats(d, label):
        if d.empty:
            print(f"{label}: n=0")
            return
        win_rate = d["signal_win"].mean() * 100
        median_pnl = d["signal_pnl_pct"].median()
        diffs = d["pnl_diff"].to_numpy(dtype=float)
        median_diff = float(np.median(diffs))
        pct_outperform = float((diffs > 0).mean() * 100)
        rng = np.random.default_rng(RANDOM_SEED)
        ci_lo, ci_hi = bootstrap_ci(diffs, N_BOOTSTRAP, rng)
        print(f"{label}: n={len(d)}")
        print(f"    win rate                     = {win_rate:.1f}%")
        print(f"    median P&L                   = {median_pnl:+.1f}%")
        print(f"    median matched-control excess = {median_diff:+.1f}pt  "
              f"(95% CI [{ci_lo:+.1f}, {ci_hi:+.1f}])")
        print(f"    % outperforming control       = {pct_outperform:.1f}%")
        print()
        return {"n": len(d), "win_rate_pct": round(win_rate, 1), "median_pnl_pct": round(median_pnl, 2),
                "median_matched_control_excess_pt": round(median_diff, 2),
                "ci_95_low": round(ci_lo, 2), "ci_95_high": round(ci_hi, 2),
                "pct_outperform_control": round(pct_outperform, 1)}

    print("=== FULL 152-EVENT CANONICAL POPULATION (usable subset, matched+priced) ===")
    full_stats = group_stats(usable, "ALL")

    high = usable[usable["zscore"] >= HIGH_CONFIDENCE_Z_THRESHOLD]
    mid = usable[(usable["zscore"] >= Z_THRESHOLD) & (usable["zscore"] < HIGH_CONFIDENCE_Z_THRESHOLD)]

    print("=== z>=10 vs z=5-9.99 SPLIT (canonical fixed-window population) ===")
    high_stats = group_stats(high, "z>=10")
    mid_stats = group_stats(mid, "z=5-9.99")

    summary = pd.DataFrame([
        {"group": "ALL", **full_stats},
        {"group": "z>=10", **high_stats},
        {"group": "z=5-9.99", **mid_stats},
    ])
    summary_path = Path("Live Signal Engine") / "MatchedControlGroup_CanonicalRecompute_Summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote summary: {summary_path}")


if __name__ == "__main__":
    main()
