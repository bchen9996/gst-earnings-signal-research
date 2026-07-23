#!/usr/bin/env python3
# GST Strategy Refinement Test — PRE-SPECIFIED, ONE SHOT, NOT OPTIMIZED.
#
# Parameters below (Z_THRESHOLD=4.0, PROFIT_TARGET_PCT=50%, MAX_HOLD_DAYS=5)
# are stated once, in advance, and are not swept or tuned against the
# output. Whatever these specific values produce is the result.
#
# Uses the earnings-aware pricing model throughout (calibrated 1.240x
# markup for events within 5 days of an earnings date, flat 1.10x
# otherwise — see GST_Earnings_IV_Calibration.py /
# GST_Straddle_Profitability_Test_EarningsAware.py).
#
# Three variants, all on the same 310 spike events (and separately, the
# 74-event non-earnings subset):
#   (a) all spikes, original full-hold exits (end_of_spike_week, end_of_window)
#   (b) z-score >= 4.0 filter only, same full-hold exits
#   (c) z-score >= 4.0 filter + early-exit rule: close at +50% gain or
#       day 5 after entry, whichever comes first
#
# *** DISCLOSED SIMPLIFICATION for the early-exit rule *** — like the rest
# of this project's straddle simulation, P&L on any candidate exit day is
# evaluated as pure INTRINSIC value (|S_day - S_entry| - premium), with no
# remaining time value added back in. A real option sold early after a
# quick move would typically fetch MORE than pure intrinsic value (it
# still has time left before expiration), so this likely UNDERSTATES
# variant (c)'s real-world P&L — a conservative bias, not an optimistic one.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import math
import pandas as pd

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
YEARS = list(range(2014, 2020))

SPIKE_DIR = Path("Conjunction Zscore")
DAILY_DIR = Path("Daily Excess Return Data")
EARNINGS_DIR = Path("Earnings Clustering Test")
OUT_DIR = Path("Straddle Profitability Test")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- pre-specified parameters, not tuned ---
Z_THRESHOLD = 4.0
PROFIT_TARGET_PCT = 50.0
MAX_HOLD_DAYS = 5

ENTRY_OFFSET_DAYS = 2
FULL_HOLD_EXITS = {"end_of_spike_week": 6, "end_of_window": 13}

RISK_FREE_RATE = 0.02
VOL_LOOKBACK_TRADING_DAYS = 60
MIN_VOL_HISTORY_DAYS = 30
COST_LOADING = 1.05
NAIVE_MARKUP = 1.10


def load_calibrated_near_earnings_markup() -> float:
    df = pd.read_csv(EARNINGS_DIR / "iv_calibration_buckets.csv", index_col=0)
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


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIR / f"{ticker}_{year}_excess.csv"
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


def simulate_full_hold(daily, ret_col, entry_date, anchor, iv, offset_days):
    exit_target = anchor + timedelta(days=offset_days)
    exit_date = nearest_trading_day_on_or_before(daily, exit_target)
    if exit_date is None or exit_date <= entry_date:
        return None
    dte_days = (exit_date - entry_date).days
    T = dte_days / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING
    cum_ret = cumulative_return(daily, ret_col, entry_date, exit_date)
    if cum_ret is None:
        return None
    intrinsic = abs(100.0 * (1 + cum_ret) - 100.0)
    net_pnl_pct = (intrinsic - cost) / cost * 100
    return {"win": net_pnl_pct > 0, "net_pnl_pct_of_cost": net_pnl_pct}


def simulate_early_exit(daily, ret_col, entry_date, iv):
    exit_target = entry_date + timedelta(days=MAX_HOLD_DAYS)
    final_exit_date = nearest_trading_day_on_or_before(daily, exit_target)
    if final_exit_date is None or final_exit_date <= entry_date:
        return None

    T = MAX_HOLD_DAYS / 365.0
    fair = bs_straddle_price(100.0, 100.0, T, RISK_FREE_RATE, iv)
    if fair is None:
        return None
    cost = fair * COST_LOADING

    mask = (daily["Date"] > entry_date) & (daily["Date"] <= final_exit_date)
    path = daily.loc[mask].sort_values("Date")
    if path.empty:
        return None

    cum = 1.0
    for _, r in path.iterrows():
        cum *= (1 + r[ret_col])
        intrinsic = abs(100.0 * cum - 100.0)
        pnl_pct = (intrinsic - cost) / cost * 100
        if pnl_pct >= PROFIT_TARGET_PCT:
            return {"win": True, "net_pnl_pct_of_cost": pnl_pct, "hit_target": True}

    intrinsic_final = abs(100.0 * cum - 100.0)
    pnl_pct_final = (intrinsic_final - cost) / cost * 100
    return {"win": pnl_pct_final > 0, "net_pnl_pct_of_cost": pnl_pct_final, "hit_target": False}


def main():
    near_earnings_markup = load_calibrated_near_earnings_markup()
    print(f"Pre-specified parameters: z>={Z_THRESHOLD}, profit target={PROFIT_TARGET_PCT}%, "
          f"max hold={MAX_HOLD_DAYS}d. Earnings-aware markup: {near_earnings_markup:.4f}x near earnings, "
          f"{NAIVE_MARKUP}x otherwise.\n")

    earnings_flags = pd.read_csv(EARNINGS_DIR / "spike_event_earnings_flags.csv")
    earnings_flags["anchor"] = pd.to_datetime(earnings_flags["anchor"]).dt.date.astype(str)
    within_5d_lookup = {(r["ticker"], r["anchor"]): bool(r["within_5d"]) for _, r in earnings_flags.iterrows()}

    rows = []
    for ticker in TICKERS:
        sp = SPIKE_DIR / f"{ticker}_zconjunction.csv"
        if not sp.exists():
            continue
        events = pd.read_csv(sp)
        ret_col = f"{ticker} Daily Return"
        daily = load_daily_excess(ticker)
        if daily.empty or ret_col not in daily.columns:
            continue

        for _, ev in events.iterrows():
            anchor = pd.to_datetime(ev["spike_week"], errors="coerce")
            if pd.isna(anchor):
                continue
            zscore = ev.get("zscore")
            near_earnings = within_5d_lookup.get((ticker, anchor.date().isoformat()), False)

            entry_target = anchor + timedelta(days=ENTRY_OFFSET_DAYS)
            entry_date = nearest_trading_day_on_or_before(daily, entry_target)
            if entry_date is None:
                continue

            vol_cutoff = anchor - timedelta(days=7)
            sigma = trailing_realized_vol(daily, ret_col, vol_cutoff)
            if sigma is None:
                continue
            iv = sigma * (near_earnings_markup if near_earnings else NAIVE_MARKUP)

            row = {"ticker": ticker, "spike_week": anchor.date(), "zscore": zscore,
                   "near_earnings": near_earnings, "z_ge_4": bool(zscore >= Z_THRESHOLD)}

            for h, offset in FULL_HOLD_EXITS.items():
                res = simulate_full_hold(daily, ret_col, entry_date, anchor, iv, offset)
                if res:
                    row[f"fullhold_{h}_win"] = res["win"]
                    row[f"fullhold_{h}_pnl_pct"] = res["net_pnl_pct_of_cost"]

            res_early = simulate_early_exit(daily, ret_col, entry_date, iv)
            if res_early:
                row["earlyexit_win"] = res_early["win"]
                row["earlyexit_pnl_pct"] = res_early["net_pnl_pct_of_cost"]
                row["earlyexit_hit_target"] = res_early["hit_target"]

            rows.append(row)

    results = pd.DataFrame(rows)
    out_path = OUT_DIR / "strategy_refinement_results.csv"
    results.to_csv(out_path, index=False)

    def report(df: pd.DataFrame, label: str):
        print(f"\n{'='*78}\n{label}  (n={len(df)} spike events in this event-set)\n{'='*78}")

        variants = [
            ("(a) all spikes, full hold", df),
            ("(b) z>=4 filter, full hold", df[df["z_ge_4"]]),
        ]
        for name, sub in variants:
            for h in FULL_HOLD_EXITS:
                win_col, pnl_col = f"fullhold_{h}_win", f"fullhold_{h}_pnl_pct"
                usable = sub[sub[win_col].notna()] if win_col in sub.columns else pd.DataFrame()
                n = len(usable)
                if n == 0:
                    print(f"{name:<32}{h:<20}{'n=0':>10}")
                    continue
                wr = usable[win_col].mean() * 100
                avg = usable[pnl_col].mean()
                med = usable[pnl_col].median()
                print(f"{name:<32}{h:<20}n={n:<5}win={wr:>6.1f}%  avg={avg:>8.1f}%  median={med:>8.1f}%")

        sub_c = df[df["z_ge_4"]]
        win_col, pnl_col = "earlyexit_win", "earlyexit_pnl_pct"
        usable = sub_c[sub_c[win_col].notna()] if win_col in sub_c.columns else pd.DataFrame()
        n = len(usable)
        name = "(c) z>=4 + early-exit (+50%/5d)"
        if n == 0:
            print(f"{name:<32}{'':<20}{'n=0':>10}")
        else:
            wr = usable[win_col].mean() * 100
            avg = usable[pnl_col].mean()
            med = usable[pnl_col].median()
            hit_rate = usable["earlyexit_hit_target"].mean() * 100
            print(f"{name:<32}{'':<20}n={n:<5}win={wr:>6.1f}%  avg={avg:>8.1f}%  median={med:>8.1f}%   "
                  f"(hit +50% target early: {hit_rate:.1f}% of trades)")

    report(results, "ALL EVENTS")
    report(results[~results["near_earnings"]], "NON-EARNINGS SUBSET")

    print(f"\n\nWrote full per-event results to: {out_path}")
    print("Parameters (z>=4, +50% target, 5-day max hold) were pre-specified and not swept.")


if __name__ == "__main__":
    main()
