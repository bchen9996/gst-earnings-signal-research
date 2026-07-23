#!/usr/bin/env python3
# TASK 4 — Search exhaustion / consecutive spikes. All on-disk data, no
# new pulls: reuses AllTickers_EarningsDates.csv and
# group_a_z4_earnings_adjacent.csv (self-referential — checks the same
# known 147-event z>=5 list for prior occurrences, same logic pattern as
# the earlier "first vs repeated spike" task, but keyed to specific PRIOR
# EARNINGS DATES rather than a generic week-count lookback).
#
# For each event, looks at the ticker's prior 3 earnings dates (before
# THIS event's own earnings date) and counts how many of those quarters
# ALSO had a z>=5 STRONG_EARNINGS spike within 5 days of THAT earnings
# date. isolated=0, occasional=1, habitual=2-3.
#
# Output: Live Signal Engine/SearchExhaustion_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
EARNINGS_PATH = Path("Live Signal Engine") / "AllTickers_EarningsDates.csv"
OUT_PATH = Path("Live Signal Engine") / "SearchExhaustion_Results.csv"

Z_THRESHOLD = 5.0
EARNINGS_WINDOW_DAYS = 5
PRIOR_QUARTERS = 3
HIGH_FREQ_MIN_EVENTS = 8   # tickers with >= this many total z>=5 events, disclosed cutoff
N_PERMUTATIONS = 10000
RANDOM_SEED = 42


def two_sample_permutation_test(a, b, n_perm, rng):
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None, None
    observed_diff = a.mean() - b.mean()
    pooled = np.concatenate([a, b]); n_a = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        d = pooled[:n_a].mean() - pooled[n_a:].mean()
        if abs(d) >= abs(observed_diff):
            count += 1
    return observed_diff, count / n_perm


def report(df, win_col, pnl_col, label):
    usable = df[df[win_col].notna()]
    n = len(usable)
    if n == 0:
        print(f"{label}: no usable events")
        return usable
    wr = usable[win_col].mean() * 100
    avg = usable[pnl_col].mean()
    med = usable[pnl_col].median()
    print(f"{label}: n={n:<4} win={wr:5.1f}%  avg={avg:+7.1f}%  median={med:+7.1f}%")
    return usable


def main():
    print(f"*** TASK 4: Search exhaustion / consecutive spikes (z>={Z_THRESHOLD:g}) ***\n")

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    print(f"Total z>={Z_THRESHOLD:g} STRONG_EARNINGS events: n={len(events)}\n")

    earnings_df = pd.read_csv(EARNINGS_PATH)
    earnings_df["earnings_date"] = pd.to_datetime(earnings_df["earnings_date"])
    earnings_by_ticker = {t: sorted(g["earnings_date"].tolist()) for t, g in earnings_df.groupby("ticker")}

    spike_dates_by_ticker = {t: sorted(g["spike_week"].tolist()) for t, g in events.groupby("ticker")}

    def had_spike_near(ticker, target_date):
        spikes = spike_dates_by_ticker.get(ticker, [])
        return any(abs((s - target_date).days) <= EARNINGS_WINDOW_DAYS for s in spikes)

    rows = []
    for _, ev in events.iterrows():
        ticker, anchor = ev["ticker"], ev["spike_week"]
        dates = earnings_by_ticker.get(ticker, [])
        gaps = [(abs((d - anchor).days), d) for d in dates]
        gaps.sort()
        this_earnings_date = gaps[0][1] if gaps and gaps[0][0] <= EARNINGS_WINDOW_DAYS else anchor

        prior_dates = sorted([d for d in dates if d < this_earnings_date], reverse=True)[:PRIOR_QUARTERS]
        n_prior_available = len(prior_dates)
        n_prior_spiked = sum(1 for d in prior_dates if had_spike_near(ticker, d))

        if n_prior_spiked == 0:
            classification = "isolated"
        elif n_prior_spiked == 1:
            classification = "occasional"
        else:
            classification = "habitual"

        rows.append({
            "ticker": ticker, "spike_week": anchor.date(), "zscore": ev["zscore"],
            "n_prior_quarters_available": n_prior_available, "n_prior_quarters_spiked": n_prior_spiked,
            "classification": classification,
            "end_of_spike_week_win": ev["end_of_spike_week_win"],
            "end_of_spike_week_pnl_pct": ev["end_of_spike_week_pnl_pct"],
        })

    result = pd.DataFrame(rows)
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    print("=== FULL SAMPLE ===")
    for cls in ["isolated", "occasional", "habitual"]:
        report(result[result["classification"] == cls], win_col, pnl_col, cls.capitalize())

    rng = np.random.default_rng(RANDOM_SEED)
    isolated_u = result[(result["classification"] == "isolated") & result[win_col].notna()]
    habitual_u = result[(result["classification"] == "habitual") & result[win_col].notna()]
    if len(isolated_u) and len(habitual_u):
        diff, p = two_sample_permutation_test(isolated_u[pnl_col].to_numpy(dtype=float),
                                               habitual_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (Isolated - Habitual), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    print(f"\n=== TICKER COMPOSITION — flag if 'habitual' is just high-frequency tickers ===")
    habitual_events = result[result["classification"] == "habitual"]
    print("Habitual group ticker counts:")
    print(habitual_events["ticker"].value_counts().to_string())

    total_by_ticker = result["ticker"].value_counts()
    high_freq_tickers = set(total_by_ticker[total_by_ticker >= HIGH_FREQ_MIN_EVENTS].index)
    print(f"\nHigh-frequency tickers (>= {HIGH_FREQ_MIN_EVENTS} total z>={Z_THRESHOLD:g} events): "
          f"{sorted(high_freq_tickers)}")
    habitual_hf_share = habitual_events["ticker"].isin(high_freq_tickers).mean() * 100 if len(habitual_events) else 0
    print(f"Share of 'habitual' events from high-frequency tickers: {habitual_hf_share:.1f}%")

    print(f"\n=== SECONDARY CHECK: within high-frequency tickers ONLY ===")
    hf_subset = result[result["ticker"].isin(high_freq_tickers)]
    print(f"High-frequency ticker subset: n={len(hf_subset)}")
    for cls in ["isolated", "occasional", "habitual"]:
        report(hf_subset[hf_subset["classification"] == cls], win_col, pnl_col, f"  {cls.capitalize()} (HF only)")

    hf_isolated_u = hf_subset[(hf_subset["classification"] == "isolated") & hf_subset[win_col].notna()]
    hf_habitual_u = hf_subset[(hf_subset["classification"] == "habitual") & hf_subset[win_col].notna()]
    if len(hf_isolated_u) and len(hf_habitual_u):
        diff_hf, p_hf = two_sample_permutation_test(hf_isolated_u[pnl_col].to_numpy(dtype=float),
                                                      hf_habitual_u[pnl_col].to_numpy(dtype=float), N_PERMUTATIONS, rng)
        sig_hf = "significant" if p_hf < 0.05 else "not significant"
        print(f"\nWithin HF only — Diff (Isolated - Habitual), P&L: {diff_hf:+.1f}pt  p={p_hf:.4f} ({sig_hf})")
    else:
        print("\nInsufficient isolated and/or habitual events within the high-frequency subset to compare.")

    result.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
