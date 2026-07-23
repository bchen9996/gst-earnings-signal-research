#!/usr/bin/env python3
# MATCHED CONTROL GROUP — for each of the 147 canonical STRONG_EARNINGS
# events (z>=5, near_earnings=True), finds a matched NON-SIGNAL earnings
# event (same ticker's other quarter with no z>=5 spike, or a similar
# sector/market-cap ticker's earnings in a similar period) and prices BOTH
# with the IDENTICAL Black-Scholes straddle methodology as
# GST_Straddle_Simulation_2021_2025_51Ticker.py. This isolates the specific
# question: does having a z>=5 GST spike before earnings improve straddle
# returns relative to just trading every earnings date blind?
#
# *** MATCHING CRITERIA (in priority order) ***
#   1. SAME TICKER, a different quarter where NO z>=5 event fired for that
#      ticker (checked against the full canonical z>=5 population, not just
#      near_earnings ones, +/-10 days buffer around each known spike).
#   2. Hard filter: SAME BMO/AMC release timing. Verified this is real,
#      usable signal (not a data artifact) -- spot-checked JPM/HD/WMT
#      (BMO, ~6am) vs TSLA/NKE (AMC, ~4-6pm) and it matches well-known
#      real-world release conventions for these companies. Classified from
#      yfinance's raw (non-normalized) earnings-date timestamp: hour<12 =
#      BMO, hour>=12 = AMC. Since release timing is a stable per-company
#      convention, this is nearly automatic for same-ticker matches and
#      only binds for the cross-ticker fallback.
#   3. Reasonable band on pre-earnings realized vol: within 0.5x-2x of the
#      signal event's own trailing realized vol (same formula/window as the
#      straddle sim: 60 trading days, min 30, cutoff = anchor-7d). Among
#      passing candidates, nearest-vol match wins; ties broken by nearest
#      calendar date to the signal event.
#   4. FALLBACK (no same-ticker candidate clears the above): pool of every
#      OTHER ticker's clean (no z>=5) earnings events, filtered to same
#      GICS sector (AllTickers_Sectors.csv) and market cap within ~3x
#      either direction (log-market-cap distance < log(3)), same BMO/AMC,
#      same vol band. Nearest-vol match wins, tiebreak nearest calendar
#      date. Controls MAY be reused across multiple signal events (greedy
#      nearest-neighbor, not a 1:1 assignment problem) -- disclosed, not
#      hidden; the number of distinct controls actually used is reported.
#
# Same entry/exit-day convention (anchor+2 / anchor+6, nearest trading day
# on-or-before) and same Black-Scholes engine (calibrated near-earnings IV
# markup, COST_LOADING=1.05) for BOTH signal and control -- the ONLY
# difference between a signal event and its matched control is whether a
# z>=5 GST spike preceded that earnings date.
#
# Output: Live Signal Engine/MatchedControlGroup_Results.csv

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

TICKERS_ORIGINAL = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
TICKERS_BROAD50_CLEAR = [
    'ABBV', 'ADP', 'ALB', 'ALLE', 'AVB', 'BKR', 'BRK-B', 'CCL', 'COF', 'COHR',
    'CTSH', 'CTVA', 'DELL', 'DVN', 'ERIE', 'GPC', 'GPN', 'JBL', 'LDOS', 'LNT',
    'MCHP', 'MCK', 'MDT', 'NCLH', 'PKG', 'PLD', 'PNW', 'RCL', 'REG', 'ROP',
    'RTX', 'STZ', 'SYF', 'SYK', 'UAL', 'XOM',
]
ALL_TICKERS = TICKERS_ORIGINAL + TICKERS_BROAD50_CLEAR
YEARS = list(range(2021, 2026))

DAILY_DIRS = {t: Path("Daily Excess Return Data (2021-2025)") for t in TICKERS_ORIGINAL}
DAILY_DIRS.update({t: Path("Daily Excess Return Data (2021-2025 Broad50 Clear)") for t in TICKERS_BROAD50_CLEAR})

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
SECTOR_PATH = Path("Live Signal Engine") / "AllTickers_Sectors.csv"
OUT_PATH = Path("Live Signal Engine") / "MatchedControlGroup_Results.csv"

Z_THRESHOLD = 5.0
SPIKE_EXCLUSION_BUFFER_DAYS = 10   # keep candidate earnings dates this far from ANY z>=5 event for that ticker
VOL_BAND_LOW, VOL_BAND_HIGH = 0.5, 2.0
MARKET_CAP_BAND = 3.0   # log-space multiplicative band for cross-ticker fallback

ENTRY_OFFSET_DAYS = 2
EXIT_OFFSET_DAYS = 6
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05

N_BOOTSTRAP = 10000
RANDOM_SEED = 42
N_DECILES = 10

YF_SESSION = requests.Session()
YF_SESSION.verify = False
YF_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


# ============================== DATA LOADING ==============================

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


# ============================== PRICING (identical to production) ==============================

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


# ============================== MATCHING ==============================

def build_candidate_pool(earnings_by_ticker, spike_dates_by_ticker, daily_cache, markup):
    """Every ticker's earnings dates that are NOT within SPIKE_EXCLUSION_BUFFER_DAYS of
    any of that ticker's own z>=5 events -- i.e. genuinely 'clean' non-signal earnings."""
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
    # Priority 1: same ticker
    same = candidates[(candidates["ticker"] == signal_ticker) & (candidates["bmo_amc"] == signal_bmo_amc)].copy()
    same = same[(same["sigma"] >= signal_sigma * VOL_BAND_LOW) & (same["sigma"] <= signal_sigma * VOL_BAND_HIGH)]
    if not same.empty:
        same["vol_dist"] = (same["sigma"] - signal_sigma).abs()
        same["date_dist"] = (same["anchor"] - signal_anchor).abs()
        best = same.sort_values(["vol_dist", "date_dist"]).iloc[0]
        used_counts[(best["ticker"], best["anchor"])] = used_counts.get((best["ticker"], best["anchor"]), 0) + 1
        return {"match_type": "same_ticker", **best.to_dict()}

    # Fallback: cross-ticker, same sector, market cap within band, same BMO/AMC, vol band
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
    print("*** MATCHED CONTROL GROUP — 147 STRONG_EARNINGS events ***\n")

    markup = load_calibrated_near_earnings_markup()
    events = pd.read_csv(GROUP_A_PATH)
    strong = events[(events["zscore"] >= Z_THRESHOLD) & (events["near_earnings"] == True)].copy()  # noqa: E712
    strong["spike_week"] = pd.to_datetime(strong["spike_week"])
    all_z5 = events[events["zscore"] >= Z_THRESHOLD].copy()
    all_z5["spike_week"] = pd.to_datetime(all_z5["spike_week"])
    print(f"Signal events: n={len(strong)}\n")

    sector_df = pd.read_csv(SECTOR_PATH)
    sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))

    print("Pulling market cap for all 51 tickers...")
    cap_map = {}
    for i, t in enumerate(ALL_TICKERS, start=1):
        cap_map[t] = fetch_market_cap(t)
        if i % 15 == 0:
            print(f"  {i}/{len(ALL_TICKERS)}...")
        time.sleep(0.3)
    print()

    print("Pulling earnings dates + BMO/AMC classification for all 51 tickers...")
    earnings_by_ticker = {}
    for i, t in enumerate(ALL_TICKERS, start=1):
        earnings_by_ticker[t] = fetch_earnings_with_time(t)
        if i % 15 == 0:
            print(f"  {i}/{len(ALL_TICKERS)}...")
        time.sleep(0.3)
    print()

    daily_cache = {t: load_daily_excess(t) for t in ALL_TICKERS}

    spike_dates_by_ticker = {t: sorted(g["spike_week"].tolist()) for t, g in all_z5.groupby("ticker")}

    print("Building clean (non-signal) candidate pool...")
    candidates = build_candidate_pool(earnings_by_ticker, spike_dates_by_ticker, daily_cache, markup)
    print(f"Candidate pool size: {len(candidates)}\n")

    print("Matching + pricing each signal event and its control...")
    used_counts: dict = {}
    rows = []
    for _, ev in strong.iterrows():
        ticker, anchor, zscore = ev["ticker"], ev["spike_week"], ev["zscore"]
        daily = daily_cache.get(ticker, pd.DataFrame())
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue

        signal_priced = price_event(daily, ret_col, anchor, markup)
        if signal_priced is None:
            continue

        edf = earnings_by_ticker.get(ticker, pd.DataFrame())
        signal_bmo_amc = None
        if not edf.empty:
            gaps = (edf["date"] - anchor).abs()
            nearest = gaps.idxmin()
            if gaps.loc[nearest] <= timedelta(days=7):
                signal_bmo_amc = edf.loc[nearest, "bmo_amc"]
        if signal_bmo_amc is None:
            signal_bmo_amc = "AMC"  # neutral default if no matched earnings record found

        match = find_match(ticker, anchor, signal_priced["sigma"], signal_bmo_amc, candidates, sector_map, cap_map, used_counts)
        if match is None:
            rows.append({"ticker": ticker, "spike_week": anchor.date(), "zscore": round(float(zscore), 3),
                         "signal_pnl_pct": round(signal_priced["pnl_pct"], 2), "signal_win": signal_priced["win"],
                         "match_type": "NO_MATCH_FOUND", "control_ticker": None, "control_date": None,
                         "control_pnl_pct": None, "control_win": None, "pnl_diff": None})
            continue

        control_daily = daily_cache.get(match["ticker"], pd.DataFrame())
        control_ret_col = f"{match['ticker']} Daily Return"
        control_priced = price_event(control_daily, control_ret_col, match["anchor"], markup)
        if control_priced is None:
            rows.append({"ticker": ticker, "spike_week": anchor.date(), "zscore": round(float(zscore), 3),
                         "signal_pnl_pct": round(signal_priced["pnl_pct"], 2), "signal_win": signal_priced["win"],
                         "match_type": "MATCH_UNPRICEABLE", "control_ticker": match["ticker"],
                         "control_date": match["earnings_date"].date(), "control_pnl_pct": None,
                         "control_win": None, "pnl_diff": None})
            continue

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": round(float(zscore), 3),
            "signal_pnl_pct": round(signal_priced["pnl_pct"], 2), "signal_win": signal_priced["win"],
            "signal_sigma": round(signal_priced["sigma"], 4), "signal_bmo_amc": signal_bmo_amc,
            "match_type": match["match_type"], "control_ticker": match["ticker"],
            "control_date": match["earnings_date"].date(), "control_sigma": round(match["sigma"], 4),
            "control_pnl_pct": round(control_priced["pnl_pct"], 2), "control_win": control_priced["win"],
            "pnl_diff": round(signal_priced["pnl_pct"] - control_priced["pnl_pct"], 2),
        })

    result = pd.DataFrame(rows)

    usable = result[result["pnl_diff"].notna()].copy()
    usable["z_decile"] = pd.qcut(usable["zscore"], N_DECILES, labels=False, duplicates="drop") + 1

    n_no_match = (result["match_type"] == "NO_MATCH_FOUND").sum()
    n_unpriceable = (result["match_type"] == "MATCH_UNPRICEABLE").sum()
    n_distinct_controls = len(used_counts)
    n_reused = sum(1 for c in used_counts.values() if c > 1)

    print(f"\nMatched + priced: n={len(usable)} / {len(strong)}")
    print(f"No match found: {n_no_match}   Match found but unpriceable: {n_unpriceable}")
    print(f"Distinct control events used: {n_distinct_controls}  (reused >1x: {n_reused})")
    print(f"Match type breakdown:\n{usable['match_type'].value_counts().to_string()}\n")

    diffs = usable["pnl_diff"].to_numpy(dtype=float)
    median_diff = float(np.median(diffs))
    pct_outperform = float((diffs > 0).mean() * 100)

    rng = np.random.default_rng(RANDOM_SEED)
    ci_lo, ci_hi = bootstrap_ci(diffs, N_BOOTSTRAP, rng)

    print(f"=== HEADLINE ===")
    print(f"Median (signal - control) P&L difference: {median_diff:+.1f}pt")
    print(f"95% bootstrap CI on median difference: [{ci_lo:+.1f}, {ci_hi:+.1f}]pt")
    print(f"% of signal events outperforming their matched control: {pct_outperform:.1f}%\n")

    print(f"=== BY Z-SCORE DECILE ({N_DECILES} deciles, 1=lowest z, {N_DECILES}=highest z) ===")
    decile_rows = []
    for d in sorted(usable["z_decile"].dropna().unique()):
        sub = usable[usable["z_decile"] == d]
        med = sub["pnl_diff"].median()
        pct_out = (sub["pnl_diff"] > 0).mean() * 100
        z_range = f"{sub['zscore'].min():.2f}-{sub['zscore'].max():.2f}"
        print(f"  Decile {int(d):>2} (z={z_range:<13}) n={len(sub):<4} median_diff={med:+7.1f}pt  %outperform={pct_out:5.1f}%")
        decile_rows.append({"decile": int(d), "z_range": z_range, "n": len(sub),
                             "median_pnl_diff": round(med, 2), "pct_outperform": round(pct_out, 1)})

    decile_df = pd.DataFrame(decile_rows)
    zs = usable["zscore"].to_numpy(dtype=float)
    ds = usable["pnl_diff"].to_numpy(dtype=float)
    spearman_rho = pd.Series(zs).corr(pd.Series(ds), method="spearman")
    print(f"\nSpearman correlation, zscore vs pnl_diff (monotonicity check): rho={spearman_rho:+.3f}")
    if abs(spearman_rho) < 0.15:
        print("=> Weak/no monotonic relationship -- effect does not scale smoothly with z, consistent with a")
        print("   threshold-specific (possibly overfit) effect rather than 'bigger spike = bigger excess move'.")
    else:
        print("=> Some monotonic relationship between z-score magnitude and excess return over matched control.")

    summary_row = pd.DataFrame([{
        "ticker": "SUMMARY", "n_events": len(usable), "median_pnl_diff": round(median_diff, 2),
        "ci_95_low": round(ci_lo, 2), "ci_95_high": round(ci_hi, 2),
        "pct_outperform": round(pct_outperform, 1), "spearman_rho_z_vs_diff": round(float(spearman_rho), 3),
        "n_no_match": int(n_no_match), "n_unpriceable": int(n_unpriceable),
        "n_distinct_controls_used": n_distinct_controls, "n_controls_reused": n_reused,
    }])

    combined = pd.concat([summary_row, pd.DataFrame([{}]), decile_df, pd.DataFrame([{}]), result], ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
