#!/usr/bin/env python3
# GST Proactive-vs-Reactive Test — day-level, DIRECT spike-vs-baseline
# comparison.
#
# GST_ProactiveReactive_Test_DayLevel.py tested spike events and baseline
# events each against their OWN day-count-adjusted null separately, and
# found baseline itself leaning slightly EARLY (p=0.01-0.03) — a possible
# generic day-of-week market seasonality unrelated to GST. That test could
# only argue the spike effect was "larger than and opposite to" whatever
# baseline was doing; it couldn't cleanly separate the two.
#
# This test controls for that directly: instead of each group vs. its own
# null, it's a straight two-sample permutation test on the two groups'
# actual per-event LATE-share values — pool every event's per-event
# statistic (spike and baseline together), shuffle which events are
# labeled "spike" vs "baseline" (preserving group sizes), and see how
# often a random relabeling produces a spike-vs-baseline gap as large as
# what's actually observed. Any common day-of-week seasonality is present
# in BOTH groups equally and cancels out of the difference; only a
# GST-specific effect can survive this comparison.
#
# Same event construction as GST_ProactiveReactive_Test_DayLevel.py:
# EARLY = spike-week trading-day positions 0-2, LATE = positions 3+,
# events need >=4 trading days in the spike week to have both sides
# non-empty.

from __future__ import annotations
from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd

TICKERS = [
    "TSLA", "NVDA", "AAPL", "MSFT", "AMZN",
    "GOOGL", "NFLX", "ADBE", "NKE", "SBUX",
    "INTC", "TTWO", "QCOM", "GME", "EBAY",
]
YEARS = list(range(2014, 2020))

SPIKE_ANCHOR_DIR = Path("Conjunction Zscore")
BASE_ANCHOR_DIR = Path("Conjunction Zscore Baseline")
DAILY_DIR = Path("Daily Excess Return Data")

EX_COL = "Excess Daily Return"
N_PERMUTATIONS = 10000
RANDOM_SEED = 42
EARLY_LATE_SPLIT_IDX = 3
MIN_TRADING_DAYS = 4


def load_daily_excess(ticker: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        p = DAILY_DIR / f"{ticker}_{year}_excess.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "Date" not in df.columns or EX_COL not in df.columns:
            continue
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df[["Date", EX_COL]].dropna(subset=["Date"]))
    if not frames:
        return pd.DataFrame(columns=["Date", EX_COL])
    return pd.concat(frames, ignore_index=True).sort_values("Date").reset_index(drop=True)


def spike_week_ordered_values(daily: pd.DataFrame, anchor: pd.Timestamp) -> np.ndarray:
    mask = (daily["Date"] >= anchor) & (daily["Date"] <= anchor + timedelta(days=6))
    window = daily.loc[mask].sort_values("Date")
    return window[EX_COL].abs().to_numpy()


def build_events(anchor_dir: Path, pattern: str, anchor_col: str) -> tuple[list[dict], int]:
    events = []
    n_excluded_short = 0
    for ticker in TICKERS:
        matches = list(anchor_dir.glob(pattern.format(ticker=ticker)))
        if not matches:
            continue
        anchors_df = pd.read_csv(matches[0])
        if anchor_col not in anchors_df.columns:
            continue
        anchors = pd.to_datetime(anchors_df[anchor_col], errors="coerce").dropna()

        daily = load_daily_excess(ticker)
        if daily.empty:
            continue

        for anchor in anchors:
            vals = spike_week_ordered_values(daily, anchor)
            if len(vals) < MIN_TRADING_DAYS:
                n_excluded_short += 1
                continue
            events.append({"ticker": ticker, "anchor": anchor.date(), "vals": vals, "n": len(vals)})
    return events, n_excluded_short


def per_event_stats(events: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Returns (mass_fraction_late, location_late) arrays, one value per event."""
    mass_frac_late = np.empty(len(events))
    location_late = np.empty(len(events))
    for i, e in enumerate(events):
        vals = e["vals"]
        early = vals[:EARLY_LATE_SPLIT_IDX]
        late = vals[EARLY_LATE_SPLIT_IDX:]
        total = early.sum() + late.sum()
        mass_frac_late[i] = late.sum() / total if total > 0 else np.nan
        location_late[i] = 1.0 if late.max() >= early.max() else 0.0
    return mass_frac_late, location_late


def two_sample_permutation_test(group_a: np.ndarray, group_b: np.ndarray, n_perm: int, rng: np.random.Generator):
    a = group_a[~np.isnan(group_a)]
    b = group_b[~np.isnan(group_b)]
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
    rng = np.random.default_rng(RANDOM_SEED)

    spike_events, spike_excluded = build_events(SPIKE_ANCHOR_DIR, "{ticker}_zconjunction.csv", "spike_week")
    base_events, base_excluded = build_events(BASE_ANCHOR_DIR, "{ticker}_baseline.csv", "random_week")

    print(f"Spike events: {len(spike_events)} usable, {spike_excluded} excluded (short week)")
    print(f"Baseline events: {len(base_events)} usable, {base_excluded} excluded (short week)\n")

    spike_mass, spike_loc = per_event_stats(spike_events)
    base_mass, base_loc = per_event_stats(base_events)

    print("Running direct two-sample permutation test: spike LATE-share vs baseline LATE-share...\n")

    diff_mass, p_mass, spike_mass_mean, base_mass_mean = two_sample_permutation_test(spike_mass, base_mass, N_PERMUTATIONS, rng)
    diff_loc, p_loc, spike_loc_mean, base_loc_mean = two_sample_permutation_test(spike_loc, base_loc, N_PERMUTATIONS, rng)

    print("=== Move-magnitude mass fraction LATE (days 3+) vs EARLY (days 0-2) ===")
    print(f"Spike mean LATE share:    {spike_mass_mean*100:.1f}%  (n={len(spike_mass)})")
    print(f"Baseline mean LATE share: {base_mass_mean*100:.1f}%  (n={len(base_mass)})")
    print(f"Diff (spike - baseline): {diff_mass*100:+.1f} pts")
    print(f"Two-sided p-value: {p_mass:.4f}  {'(significant at 0.05)' if p_mass < 0.05 else '(NOT significant at 0.05)'}")

    print("\n=== Fraction of events where the single biggest move fell LATE ===")
    print(f"Spike:    {spike_loc_mean*100:.1f}%  (n={len(spike_loc)})")
    print(f"Baseline: {base_loc_mean*100:.1f}%  (n={len(base_loc)})")
    print(f"Diff (spike - baseline): {diff_loc*100:+.1f} pts")
    print(f"Two-sided p-value: {p_loc:.4f}  {'(significant at 0.05)' if p_loc < 0.05 else '(NOT significant at 0.05)'}")

    print(f"\n({N_PERMUTATIONS} permutations, seed={RANDOM_SEED} for reproducibility)")


if __name__ == "__main__":
    main()
