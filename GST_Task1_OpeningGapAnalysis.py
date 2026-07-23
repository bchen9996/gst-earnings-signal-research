#!/usr/bin/env python3
# TASK 1 — Opening gap as prediction target. For each z>=5 STRONG_EARNINGS
# event (n=147), decompose the underlying move into the overnight
# earnings gap vs the exit-day intraday session, and test whether the
# gap alone explains next-day-exit straddle outcomes as well as the
# full entry-to-exit move.
#
# gap definition (AMC/BMO-aware, from EarningsTiming_SignalQuality_Test.csv,
# 145/147 = 98.6% classified, 2 AMBIGUOUS excluded):
#   AMC: gap = (next_trading_day_open - earnings_day_close) / earnings_day_close
#   BMO: gap = (earnings_day_open - prior_trading_day_close) / prior_trading_day_close
#
# *** FRESH PULL REQUIRED — NO OPEN-PRICE DATA EXISTS ON DISK ***
# Every existing daily price file in this project stores RETURNS only
# (close-to-close), never Open. A fresh yfinance OHLC pull (Open, Close)
# is required for the 28 tickers appearing in the 147-event set, plus
# whichever tickers appear in the no-spike baseline (group_b), 2021-2025,
# auto_adjust=True (split-adjusted, consistent with the rest of this
# project). Cached to Daily OHLC Data (2021-2025 Opening Gap Test)/.
#
# *** DECOMPOSITION METHODOLOGY ***
# Entry/exit follow the current adopted spec: entry = nearest trading day
# on/before anchor+2, exit = next trading day after the matched earnings
# date. The entry-to-exit move is decomposed in LOG returns (additive
# across days, unlike simple %): log_total = log(Close_exit/Close_entry) =
# log_gap + log_intraday_exit_day + log_residual (everything else: entry
# up through the pre-earnings close). Two fraction measures are reported:
# a SIGNED fraction (log_gap / log_total — can behave oddly if components
# offset in sign) and a MAGNITUDE-SHARE (|log_gap| / sum of |components| —
# robust to sign cancellation). Straddle P&L itself is NOT path-decomposable
# (it depends only on the endpoint move, not a time-additive sum), so item
# (d) is answered via correlation of |gap| vs pnl_pct compared to
# correlation of |total move| vs pnl_pct, not a P&L decomposition.
#
# Output: Live Signal Engine/OpeningGap_Analysis.csv

from __future__ import annotations
from pathlib import Path
from datetime import timedelta, date
import sys, time
import math
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
GROUP_B_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_b_nospike_earnings_adjacent.csv"
TIMING_PATH = Path("Live Signal Engine") / "EarningsTiming_SignalQuality_Test.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
CALIBRATION_PATH = Path("Earnings Clustering Test") / "iv_calibration_buckets.csv"
OHLC_DIR = Path("Daily OHLC Data (2021-2025 Opening Gap Test)"); OHLC_DIR.mkdir(exist_ok=True)
OUT_PATH = Path("Live Signal Engine") / "OpeningGap_Analysis.csv"

Z_THRESHOLD = 5.0
ENTRY_OFFSET_DAYS = 2
MAX_EARNINGS_GAP_DAYS = 5
YEARS = list(range(2021, 2026))
RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
N_PERMUTATIONS = 10000
RANDOM_SEED = 42
MAX_PULL_ATTEMPTS = 5
INTER_TICKER_SLEEP_SECONDS = 2.0

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


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


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(CALIBRATION_PATH, index_col=0)
    near_row = df[df.index.str.startswith("near earnings")]
    return float(near_row["mean"].iloc[0])


def pull_ohlc(ticker: str) -> pd.DataFrame:
    cache_path = OHLC_DIR / f"{ticker}_ohlc.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["Date"])
        if not df.empty:
            return df
    # Single multi-year call (not one call per year) to minimize request volume / rate-limit risk.
    for attempt in range(1, MAX_PULL_ATTEMPTS + 1):
        try:
            df = yf.download(ticker, start="2021-01-01", end="2026-01-01", session=SESSION, auto_adjust=True,
                              progress=False, group_by="column", threads=False)
            if df is None or df.empty:
                raise RuntimeError("empty result")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            result = pd.DataFrame({"Date": pd.to_datetime(df.index), "Open": df["Open"].values, "Close": df["Close"].values})
            result = result.sort_values("Date").reset_index(drop=True)
            result.to_csv(cache_path, index=False)
            return result
        except Exception as e:
            msg = str(e).lower()
            pause = 60 if ("429" in msg or "too many" in msg or "rate" in msg) else 8 * attempt
            print(f"    [{ticker}] OHLC pull attempt {attempt}/{MAX_PULL_ATTEMPTS} failed: {e} -- sleeping {pause}s")
            time.sleep(pause)
    return pd.DataFrame(columns=["Date", "Open", "Close"])


def nearest_trading_day_on_or_before(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] <= target, "Date"]
    return eligible.max() if not eligible.empty else None


def next_trading_day_after(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] > target, "Date"]
    return eligible.min() if not eligible.empty else None


def prior_trading_day(daily, target):
    target = pd.Timestamp(target)
    eligible = daily.loc[daily["Date"] < target, "Date"]
    return eligible.max() if not eligible.empty else None


def row_val(daily, d, col):
    r = daily.loc[daily["Date"] == d, col]
    return float(r.iloc[0]) if not r.empty else None


def compute_gap(daily: pd.DataFrame, earnings_date: pd.Timestamp, timing: str) -> dict:
    """Overnight earnings gap. AMC: (next_open - earnings_day_close)/earnings_day_close.
    BMO: (earnings_day_open - prior_close)/prior_close."""
    earnings_day = nearest_trading_day_on_or_before(daily, earnings_date)
    if earnings_day is None:
        return {"gap_pct": None}
    if timing == "AMC":
        prior_close_date = earnings_day
        next_day = next_trading_day_after(daily, earnings_day)
        prior_close = row_val(daily, prior_close_date, "Close")
        next_open = row_val(daily, next_day, "Open") if next_day is not None else None
        if prior_close is None or next_open is None or prior_close == 0:
            return {"gap_pct": None}
        gap = (next_open - prior_close) / prior_close
        return {"gap_pct": gap, "gap_reaction_day": next_day}
    elif timing == "BMO":
        prior_day = prior_trading_day(daily, earnings_day)
        prior_close = row_val(daily, prior_day, "Close") if prior_day is not None else None
        same_day_open = row_val(daily, earnings_day, "Open")
        if prior_close is None or same_day_open is None or prior_close == 0:
            return {"gap_pct": None}
        gap = (same_day_open - prior_close) / prior_close
        return {"gap_pct": gap, "gap_reaction_day": earnings_day}
    return {"gap_pct": None}


def fetch_earnings_hour(ticker: str, max_attempts: int = MAX_PULL_ATTEMPTS) -> pd.DataFrame:
    df = None
    for attempt in range(1, max_attempts + 1):
        try:
            tk = yf.Ticker(ticker, session=SESSION)
            df = tk.get_earnings_dates(limit=40)
        except Exception as e:
            print(f"    [{ticker}] earnings-hour attempt {attempt}/{max_attempts} failed: {e}")
            df = None
        if df is not None and not df.empty:
            break
        if attempt < max_attempts:
            time.sleep(20 * attempt)
    if df is None or df.empty:
        print(f"    [{ticker}] earnings-hour fetch FAILED after {max_attempts} attempts")
        return pd.DataFrame()
    return pd.DataFrame({"date": pd.to_datetime(df.index).tz_localize(None).normalize().date,
                          "hour": pd.to_datetime(df.index).tz_localize(None).hour}).dropna()


def classify_timing(hist: pd.DataFrame, anchor) -> tuple[str, int | None]:
    if hist.empty:
        return "no_earnings_history", None
    gaps = (pd.to_datetime(hist["date"]) - pd.Timestamp(anchor)).abs().dt.days
    nearest_idx = gaps.idxmin()
    if int(gaps.loc[nearest_idx]) > MAX_EARNINGS_GAP_DAYS:
        return "no_earnings_date_within_5d", None
    hour = int(hist.loc[nearest_idx, "hour"])
    if hour < 12:
        return "BMO", hour
    elif hour >= 16:
        return "AMC", hour
    return "AMBIGUOUS_intraday_time", hour


def two_sample_permutation_test(a, b, n_perm, rng, stat="mean"):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    f = np.mean if stat == "mean" else np.median
    observed_diff = f(a) - f(b)
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = f(pooled[:n_a]) - f(pooled[n_a:])
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def pearson_spearman(x, y):
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return None, None
    pearson = float(np.corrcoef(x, y)[0, 1])
    rank_x, rank_y = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    spearman = float(np.corrcoef(rank_x, rank_y)[0, 1])
    return pearson, spearman


def main():
    print("*** TASK 1: Opening gap as prediction target ***\n")

    near_earnings_markup = load_calibrated_near_earnings_markup()
    earnings = pd.read_csv(EARNINGS_PATH)
    earnings["earnings_date"] = pd.to_datetime(earnings["earnings_date"])
    earnings_by_ticker = {t: g["earnings_date"].sort_values().reset_index(drop=True) for t, g in earnings.groupby("ticker")}

    timing_df = pd.read_csv(TIMING_PATH)
    timing_df["spike_week"] = pd.to_datetime(timing_df["spike_week"])
    spike_events = timing_df[timing_df["timing"].isin(["AMC", "BMO"])].copy()
    print(f"STRONG_EARNINGS events with clear AMC/BMO timing: n={len(spike_events)}/147\n")

    baseline_events = pd.read_csv(GROUP_B_PATH)
    baseline_events["anchor"] = pd.to_datetime(baseline_events["anchor"])
    print(f"No-spike earnings-adjacent baseline events: n={len(baseline_events)}\n")

    spike_tickers = sorted(spike_events["ticker"].unique())
    baseline_tickers = sorted(baseline_events["ticker"].unique())
    all_tickers = sorted(set(spike_tickers) | set(baseline_tickers))
    print(f"Pulling fresh OHLC (Open, Close) for {len(all_tickers)} tickers, 2021-2025 (cached)...")
    ohlc_cache = {}
    for i, t in enumerate(all_tickers, start=1):
        ohlc_cache[t] = pull_ohlc(t)
        print(f"  [{i}/{len(all_tickers)}] {t}: {len(ohlc_cache[t])} rows")
        if len(ohlc_cache[t]) == 0:
            print(f"    WARNING: {t} has no OHLC data -- all its events will be excluded downstream.")
        time.sleep(INTER_TICKER_SLEEP_SECONDS)
    print()

    # --- classify baseline timing (fresh, same method, cached earnings-hour history per ticker) ---
    print("Classifying baseline event timing (AMC/BMO)...")
    hour_hist_cache = {}
    baseline_rows = []
    for t in baseline_tickers:
        if t not in hour_hist_cache:
            hour_hist_cache[t] = fetch_earnings_hour(t)
            time.sleep(INTER_TICKER_SLEEP_SECONDS)
    for _, ev in baseline_events.iterrows():
        t, anchor = ev["ticker"], ev["anchor"]
        timing, hour = classify_timing(hour_hist_cache.get(t, pd.DataFrame()), anchor)
        baseline_rows.append({"ticker": t, "anchor": anchor, "timing": timing})
    baseline_timing_df = pd.DataFrame(baseline_rows)
    baseline_clear = baseline_timing_df[baseline_timing_df["timing"].isin(["AMC", "BMO"])]
    print(f"Baseline events with clear AMC/BMO timing: n={len(baseline_clear)}/{len(baseline_events)}\n")

    # --- gaps for spike events ---
    print("Computing overnight gaps for spike events...")
    spike_gap_rows = []
    for _, ev in spike_events.iterrows():
        t, anchor, timing, zscore = ev["ticker"], ev["spike_week"], ev["timing"], ev["zscore"]
        daily = ohlc_cache.get(t, pd.DataFrame())
        if daily.empty:
            continue
        hist = earnings_by_ticker.get(t, pd.Series(dtype="datetime64[ns]"))
        gaps_days = (hist - anchor).abs().dt.days
        if hist.empty or gaps_days.min() > MAX_EARNINGS_GAP_DAYS:
            continue
        earnings_date = hist.loc[gaps_days.idxmin()]
        res = compute_gap(daily, earnings_date, timing)
        if res["gap_pct"] is None:
            continue
        spike_gap_rows.append({"ticker": t, "spike_week": anchor.date(), "zscore": zscore, "timing": timing,
                               "earnings_date": earnings_date.date(), "gap_pct": res["gap_pct"] * 100})
    spike_gaps = pd.DataFrame(spike_gap_rows)
    print(f"Usable spike-event gaps: n={len(spike_gaps)}\n")

    # --- gaps for baseline events ---
    print("Computing overnight gaps for baseline events...")
    baseline_gap_rows = []
    for _, ev in baseline_clear.iterrows():
        t, anchor, timing = ev["ticker"], ev["anchor"], ev["timing"]
        daily = ohlc_cache.get(t, pd.DataFrame())
        if daily.empty:
            continue
        hist = earnings_by_ticker.get(t, pd.Series(dtype="datetime64[ns]"))
        gaps_days = (hist - anchor).abs().dt.days
        if hist.empty or gaps_days.min() > MAX_EARNINGS_GAP_DAYS:
            continue
        earnings_date = hist.loc[gaps_days.idxmin()]
        res = compute_gap(daily, earnings_date, timing)
        if res["gap_pct"] is None:
            continue
        baseline_gap_rows.append({"ticker": t, "anchor": anchor.date(), "timing": timing,
                                  "earnings_date": earnings_date.date(), "gap_pct": res["gap_pct"] * 100})
    baseline_gaps = pd.DataFrame(baseline_gap_rows)
    print(f"Usable baseline-event gaps: n={len(baseline_gaps)}\n")

    # === (a) mean/median abs gap, spike vs baseline ===
    print("=== (a) ABSOLUTE GAP SIZE: spike vs baseline ===")
    if spike_gaps.empty or baseline_gaps.empty or "gap_pct" not in baseline_gaps.columns:
        print(f"INSUFFICIENT DATA: spike_gaps n={len(spike_gaps)}, baseline_gaps n={len(baseline_gaps)}. "
              f"Cannot compute spike-vs-baseline comparison. Writing whatever data was collected and stopping.")
        spike_gaps.to_csv(OUT_PATH, index=False)
        print(f"Wrote partial data only: {OUT_PATH}")
        return
    spike_abs = spike_gaps["gap_pct"].abs().to_numpy()
    baseline_abs = baseline_gaps["gap_pct"].abs().to_numpy()
    print(f"Spike events:    n={len(spike_abs)}  mean|gap|={spike_abs.mean():.2f}%  median|gap|={np.median(spike_abs):.2f}%")
    print(f"Baseline events: n={len(baseline_abs)}  mean|gap|={baseline_abs.mean():.2f}%  median|gap|={np.median(baseline_abs):.2f}%")
    rng = np.random.default_rng(RANDOM_SEED)
    diff_mean, p_mean = two_sample_permutation_test(spike_abs, baseline_abs, N_PERMUTATIONS, rng, "mean")
    print(f"Diff in mean|gap|: {diff_mean:+.2f}pt  p={p_mean:.4f} ({'significant' if p_mean < 0.05 else 'not significant'})\n")

    # === (b) correlation z-score vs abs gap ===
    print("=== (b) CORRELATION: z-score magnitude vs |gap| (spike events) ===")
    pearson_r, spearman_r = pearson_spearman(spike_gaps["zscore"].to_numpy(dtype=float), spike_gaps["gap_pct"].abs().to_numpy())
    print(f"Pearson r={pearson_r:.4f}   Spearman rho={spearman_r:.4f}\n")

    # === (c)/(d) decomposition: entry-to-exit move vs gap vs intraday-exit-day ===
    print("Pricing entry-to-exit straddles and decomposing the move (log-return additive)...")
    decomp_rows = []
    for _, ev in spike_gaps.iterrows():
        t = ev["ticker"]
        daily = ohlc_cache.get(t, pd.DataFrame())
        anchor = pd.Timestamp(ev["spike_week"])
        earnings_date = pd.Timestamp(ev["earnings_date"])
        timing = ev["timing"]

        entry_date = nearest_trading_day_on_or_before(daily, anchor + timedelta(days=ENTRY_OFFSET_DAYS))
        exit_date = next_trading_day_after(daily, earnings_date)
        if entry_date is None or exit_date is None or exit_date <= entry_date:
            continue

        close_entry = row_val(daily, entry_date, "Close")
        close_exit = row_val(daily, exit_date, "Close")
        open_exit = row_val(daily, exit_date, "Open")
        if None in (close_entry, close_exit, open_exit) or close_entry <= 0 or open_exit <= 0:
            continue

        log_total = math.log(close_exit / close_entry)
        log_gap = math.log(1 + ev["gap_pct"] / 100)
        log_intraday_exit = math.log(close_exit / open_exit)
        log_residual = log_total - log_gap - log_intraday_exit

        abs_sum = abs(log_gap) + abs(log_intraday_exit) + abs(log_residual)
        signed_frac_gap = (log_gap / log_total) if log_total != 0 else None
        magnitude_share_gap = (abs(log_gap) / abs_sum) if abs_sum > 0 else None

        # BS straddle P&L, entry-to-exit
        vol_hist = daily.assign(ret=daily["Close"].pct_change()).loc[daily["Date"] < (anchor - timedelta(days=7))].tail(VOL_LOOKBACK_TRADING_DAYS)
        if len(vol_hist) < MIN_VOL_HISTORY_DAYS:
            continue
        sigma = float(vol_hist["ret"].std() * math.sqrt(252))
        dte_days = (exit_date - entry_date).days
        if dte_days <= 0:
            continue
        T = dte_days / 365.0
        iv = sigma * near_earnings_markup
        fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
        if fair is None:
            continue
        cost = fair * COST_LOADING
        total_move_pct = (math.exp(log_total) - 1) * 100
        intrinsic = abs(100.0 * math.exp(log_total) - 100.0)
        pnl_pct = (intrinsic - cost) / cost * 100

        decomp_rows.append({
            "ticker": t, "spike_week": ev["spike_week"], "timing": timing, "gap_pct": ev["gap_pct"],
            "total_move_pct": round(total_move_pct, 3), "log_total": round(log_total, 5),
            "log_gap": round(log_gap, 5), "log_intraday_exit_day": round(log_intraday_exit, 5),
            "log_residual": round(log_residual, 5),
            "signed_frac_gap_of_total": round(signed_frac_gap, 4) if signed_frac_gap is not None else None,
            "magnitude_share_gap": round(magnitude_share_gap, 4) if magnitude_share_gap is not None else None,
            "pnl_pct": round(pnl_pct, 2),
        })

    decomp = pd.DataFrame(decomp_rows)
    print(f"Usable entry-to-exit decompositions: n={len(decomp)}\n")

    print("=== (c) FRACTION OF MOVE FROM OVERNIGHT GAP vs INTRADAY EXIT-DAY MOVE ===")
    print(f"Mean magnitude share attributable to gap: {decomp['magnitude_share_gap'].mean()*100:.1f}%")
    print(f"Median magnitude share attributable to gap: {decomp['magnitude_share_gap'].median()*100:.1f}%")
    print(f"(Mean signed fraction: {decomp['signed_frac_gap_of_total'].mean()*100:.1f}% -- can differ from the "
          f"magnitude share when gap and intraday moves partly offset in sign)\n")

    print("=== (d) DOES GAP ALONE EXPLAIN STRADDLE P&L AS WELL AS THE FULL MOVE? ===")
    r_gap, _ = pearson_spearman(decomp["gap_pct"].abs().to_numpy(), decomp["pnl_pct"].to_numpy())
    r_total, _ = pearson_spearman(decomp["total_move_pct"].abs().to_numpy(), decomp["pnl_pct"].to_numpy())
    print(f"corr(|gap|, pnl_pct):        r={r_gap:.4f}   R^2={r_gap**2:.4f}")
    print(f"corr(|total_move|, pnl_pct): r={r_total:.4f}   R^2={r_total**2:.4f}")
    verdict = "GAP ALONE explains P&L about as well as the full move" if abs(r_gap) >= abs(r_total) * 0.9 else \
              "Full move explains P&L meaningfully better than gap alone"
    print(f"Verdict: {verdict}\n")

    summary = pd.DataFrame([{
        "n_spike_gaps": len(spike_gaps), "n_baseline_gaps": len(baseline_gaps),
        "spike_mean_abs_gap_pct": round(spike_abs.mean(), 2), "baseline_mean_abs_gap_pct": round(baseline_abs.mean(), 2),
        "diff_mean_abs_gap_pct": round(diff_mean, 2), "p_value": round(p_mean, 4),
        "pearson_r_z_vs_absgap": round(pearson_r, 4), "spearman_rho_z_vs_absgap": round(spearman_r, 4),
        "mean_magnitude_share_gap": round(decomp["magnitude_share_gap"].mean(), 4),
        "median_magnitude_share_gap": round(decomp["magnitude_share_gap"].median(), 4),
        "corr_gap_vs_pnl": round(r_gap, 4), "corr_totalmove_vs_pnl": round(r_total, 4),
    }])

    combined = pd.concat([summary, pd.DataFrame([{}]), decomp, pd.DataFrame([{}]), spike_gaps, pd.DataFrame([{}]), baseline_gaps],
                          ignore_index=True, sort=False)
    combined.to_csv(OUT_PATH, index=False)
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
