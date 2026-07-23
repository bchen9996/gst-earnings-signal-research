#!/usr/bin/env python3
# Pre-Spike Price/Volume Test — EXPLORATORY, UNVALIDATED.
#
# Does unusual price action in the 5 trading days BEFORE a STRONG_EARNINGS
# GST spike distinguish it from earnings weeks that don't spike? Uses only
# the existing, already-validated 2021-2025 51-ticker dataset on disk — no
# new pulls, no new tickers, no new date ranges.
#
#   Group A = STRONG_EARNINGS events (z>=4, near_earnings=True), n=209 —
#             loaded directly from Earnings-Adjacent Spike vs No-Spike
#             Test/group_a_z4_earnings_adjacent.csv (already on disk,
#             already the canonical n=209 used throughout this project).
#   Group B = non-spike earnings-adjacent weeks, n=110 — loaded directly
#             from .../group_b_nospike_earnings_adjacent.csv (same
#             disclosed substitution as that test: "no spike at all," not
#             specifically "spike with z<4" — see that script's header).
#
# For each event, pulls the 5 trading days strictly BEFORE the anchor date
# from the ticker's own daily excess-return file (already on disk) and
# computes:
#   pre_window_return       — signed cumulative stock return over those 5 days
#   pre_window_abs_return   — |pre_window_return| (magnitude of the net move)
#   pre_window_mean_abs_daily_return — mean(|daily return|) over the 5 days
#                              (catches whipsaw/choppiness that a net-return
#                              figure can hide if up/down days cancel out)
#
# *** VOLUME REQUIRED A NEW PULL — DISCLOSED, NOT SILENT ***
# Checked every price-pull script in this project (Daily Excess Returns
# *.py, Backtest_Data_Pull*.py): all of them call yfinance's yf.download(),
# which DOES return a Volume column, but every one of them extracts only
# Close/Adj Close before saving — Volume was never persisted anywhere on
# disk. This broke the original "existing data only" scope; per an explicit
# decision to proceed anyway, GST_Pull_Volume_2021_2025.py did one new,
# lightweight yf.download() per ticker (51 calls total, not the heavier
# per-year GST-style pulls) and persisted the result to
# Daily Volume Data (2021-2025)/<TICKER>_volume.csv so it's not a one-off.
#   pre_window_avg_volume   — mean daily Volume over the 5 trading days
#                              before the anchor
#   baseline_avg_volume     — mean daily Volume over the 60 trading days
#                              BEFORE that 5-day window (mirrors the
#                              VOL_LOOKBACK_TRADING_DAYS=60 trailing-
#                              baseline convention already used for IV
#                              elsewhere in this project)
#   pre_window_volume_ratio — pre_window_avg_volume / baseline_avg_volume.
#                              Raw volume spans orders of magnitude across
#                              a 51-ticker universe (AAPL vs ERIE) and can't
#                              be pooled directly — this ratio is what's
#                              actually compared between groups.
#
# *** THIS IS EXPLORATORY / UNVALIDATED — SAME AS THE SOCIAL/NEWS MONITOR ***
# A price-return relationship found here is an association in a specific
# 209-vs-110 sample, not a proven leading indicator. It has not been out-
# of-sample tested, and "5 trading days before" was picked because it's a
# natural pre-event window, not because it was swept against alternatives
# for the best-looking result.
#
# Output: Live Signal Engine/PreSpike_PriceVolume_Test_EXPLORATORY.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

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

VOLUME_DIR = Path("Daily Volume Data (2021-2025)")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
GROUP_B_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_b_nospike_earnings_adjacent.csv"
OUT_DIR = Path("Live Signal Engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PRE_WINDOW_TRADING_DAYS = 5
VOLUME_BASELINE_LOOKBACK_DAYS = 60   # matches VOL_LOOKBACK_TRADING_DAYS convention used for IV elsewhere
MIN_VOLUME_BASELINE_DAYS = 30
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def load_volume(ticker: str) -> pd.DataFrame:
    p = VOLUME_DIR / f"{ticker}_volume.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)


def pre_window_volume_stats(volume: pd.DataFrame, anchor: pd.Timestamp) -> dict | None:
    prior = volume.loc[volume["Date"] < anchor]
    pre_window = prior.tail(PRE_WINDOW_TRADING_DAYS)
    if len(pre_window) < PRE_WINDOW_TRADING_DAYS:
        return None
    baseline = prior.iloc[:-PRE_WINDOW_TRADING_DAYS].tail(VOLUME_BASELINE_LOOKBACK_DAYS)
    if len(baseline) < MIN_VOLUME_BASELINE_DAYS:
        return None
    pre_avg = float(pre_window["Volume"].mean())
    base_avg = float(baseline["Volume"].mean())
    if base_avg <= 0:
        return None
    return {
        "pre_window_avg_volume": pre_avg,
        "baseline_avg_volume": base_avg,
        "pre_window_volume_ratio": pre_avg / base_avg,
    }


def load_daily(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIRS[ticker] / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def pre_window_stats(daily: pd.DataFrame, ret_col: str, anchor: pd.Timestamp) -> dict | None:
    prior = daily.loc[daily["Date"] < anchor].tail(PRE_WINDOW_TRADING_DAYS)
    if len(prior) < PRE_WINDOW_TRADING_DAYS:
        return None
    rets = prior[ret_col].to_numpy(dtype=float)
    cum_ret = float(np.prod(1 + rets) - 1)
    return {
        "pre_window_return": cum_ret,
        "pre_window_abs_return": abs(cum_ret),
        "pre_window_mean_abs_daily_return": float(np.mean(np.abs(rets))),
    }


def build_group(events: pd.DataFrame, anchor_col: str, group_label: str) -> pd.DataFrame:
    rows = []
    n_insufficient_price, n_insufficient_volume = 0, 0
    volume_cache: dict[str, pd.DataFrame] = {}
    for _, ev in events.iterrows():
        ticker = ev["ticker"]
        anchor = pd.to_datetime(ev[anchor_col], errors="coerce")
        if pd.isna(anchor) or ticker not in DAILY_DIRS:
            continue
        daily = load_daily(ticker)
        ret_col = f"{ticker} Daily Return"
        if daily.empty or ret_col not in daily.columns:
            continue
        price_stats = pre_window_stats(daily, ret_col, anchor)
        if price_stats is None:
            n_insufficient_price += 1
            continue

        if ticker not in volume_cache:
            volume_cache[ticker] = load_volume(ticker)
        volume_stats = pre_window_volume_stats(volume_cache[ticker], anchor)
        if volume_stats is None:
            n_insufficient_volume += 1
            volume_stats = {"pre_window_avg_volume": None, "baseline_avg_volume": None, "pre_window_volume_ratio": None}

        rows.append({"ticker": ticker, "anchor": anchor.date(), "group": group_label, **price_stats, **volume_stats})
    if n_insufficient_price:
        print(f"  [{group_label}] {n_insufficient_price} event(s) skipped (price) — fewer than "
              f"{PRE_WINDOW_TRADING_DAYS} trading days of history before the anchor.")
    if n_insufficient_volume:
        print(f"  [{group_label}] {n_insufficient_volume} event(s) missing volume ratio — insufficient "
              f"{VOLUME_BASELINE_LOOKBACK_DAYS}-day baseline history (kept in output with volume fields blank).")
    return pd.DataFrame(rows)


def two_sample_permutation_test(a: np.ndarray, b: np.ndarray, n_perm: int, rng: np.random.Generator):
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None, None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b])
    n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(diff) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm, a.mean(), b.mean()


def main():
    print("*** EXPLORATORY / UNVALIDATED — pre-spike PRICE and VOLUME (volume via new pull, see header). ***\n")

    if not GROUP_A_PATH.exists() or not GROUP_B_PATH.exists():
        print(f"Missing {GROUP_A_PATH} or {GROUP_B_PATH} — run GST_EarningsAdjacent_SpikeVsNoSpike_Test.py first.")
        return

    group_a_events = pd.read_csv(GROUP_A_PATH)
    group_b_events = pd.read_csv(GROUP_B_PATH)
    print(f"Group A (STRONG_EARNINGS, z>=4, earnings-adjacent): n={len(group_a_events)} events on disk")
    print(f"Group B (no-spike, earnings-adjacent):              n={len(group_b_events)} events on disk\n")

    print("Computing 5-trading-day pre-window price and volume stats...")
    group_a = build_group(group_a_events, "spike_week", "A_STRONG_EARNINGS")
    group_b = build_group(group_b_events, "anchor", "B_no_spike_earnings_adjacent")
    print(f"\nGroup A usable: n={len(group_a)}   Group B usable: n={len(group_b)}\n")

    combined = pd.concat([group_a, group_b], ignore_index=True)
    out_path = OUT_DIR / "PreSpike_PriceVolume_Test_EXPLORATORY.csv"
    combined.to_csv(out_path, index=False)

    rng = np.random.default_rng(RANDOM_SEED)

    print(f"=== PRE-SPIKE (5 trading days before anchor) PRICE COMPARISON ===\n")
    for metric in ["pre_window_return", "pre_window_abs_return", "pre_window_mean_abs_daily_return"]:
        a_vals = group_a[metric].to_numpy(dtype=float)
        b_vals = group_b[metric].to_numpy(dtype=float)
        diff, p, a_mean, b_mean = two_sample_permutation_test(a_vals, b_vals, N_PERMUTATIONS, rng)

        print(f"--- {metric} ---")
        print(f"Group A: mean={a_mean*100:+.2f}%  median={np.median(a_vals)*100:+.2f}%")
        print(f"Group B: mean={b_mean*100:+.2f}%  median={np.median(b_vals)*100:+.2f}%")
        if diff is not None:
            sig = "significant" if p < 0.05 else "not significant"
            print(f"Diff (A - B): {diff*100:+.2f} pts   two-sided p={p:.4f} ({sig})")
        print()

    print(f"=== PRE-SPIKE (5 trading days before anchor) VOLUME COMPARISON ===\n")
    a_ratio = group_a["pre_window_volume_ratio"].dropna().to_numpy(dtype=float)
    b_ratio = group_b["pre_window_volume_ratio"].dropna().to_numpy(dtype=float)
    n_a_missing = group_a["pre_window_volume_ratio"].isna().sum()
    n_b_missing = group_b["pre_window_volume_ratio"].isna().sum()
    diff, p, a_mean, b_mean = two_sample_permutation_test(a_ratio, b_ratio, N_PERMUTATIONS, rng)

    print(f"--- pre_window_volume_ratio (pre-window avg volume / {VOLUME_BASELINE_LOOKBACK_DAYS}-day trailing baseline) ---")
    print(f"Group A: n={len(a_ratio)} (missing={n_a_missing})  mean={a_mean:.3f}x  median={np.median(a_ratio):.3f}x")
    print(f"Group B: n={len(b_ratio)} (missing={n_b_missing})  mean={b_mean:.3f}x  median={np.median(b_ratio):.3f}x")
    if diff is not None:
        sig = "significant" if p < 0.05 else "not significant"
        print(f"Diff (A - B): {diff:+.3f}x   two-sided p={p:.4f} ({sig})")
    print()

    print("Reminder: this is an EXPLORATORY, UNVALIDATED association test — price AND volume.")
    print(f"\nWrote combined event-level data to: {out_path}")


if __name__ == "__main__":
    main()
