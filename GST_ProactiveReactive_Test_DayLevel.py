#!/usr/bin/env python3
# GST Proactive-vs-Reactive Test — day-level refinement.
#
# GST_ProactiveReactive_Test_3Period.py found the move-magnitude mass is
# concentrated in the SPIKE WEEK itself (47.5% vs a 33.5% null), not in the
# weeks before or after. That result only resolves timing at week
# granularity, so it can't say whether that week's move happens early
# (still catchable if the live signal engine detects the spike from the
# partial current-week GST reading) or late (already largely over by the
# time the week — and the spike — is confirmed).
#
# For each spike event, within the spike week's trading days ONLY
# (chronological order, position 0 = first trading day of that week),
# classify position < 3 as EARLY and position >= 3 as LATE (matches the
# requested "days 0-2 early, days 3-5 late" split; naturally handles
# shorter holiday weeks since the >=3 threshold just yields an empty or
# smaller LATE group in that case — events needing both groups non-empty,
# i.e. at least 4 trading days in the spike week, are kept; events with
# fewer are excluded and the exclusion count is reported).
#
# Same permutation methodology as the prior two timing tests: reshuffle
# each event's own observed |excess return| values across its own spike-
# week trading-day positions, preserving that event's actual EARLY/LATE
# day-count split — this is the correct null given EARLY and LATE aren't
# equal-length in every event (a 4-day week splits 3/1, a 5-day week 3/2).
# Baseline (random-week) events get the identical treatment as a control.

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
EARLY_LATE_SPLIT_IDX = 3   # position < 3 -> early, position >= 3 -> late
MIN_TRADING_DAYS = 4        # need at least 1 day on each side of the split


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


def summarize(events: list[dict]) -> dict:
    mass_frac_late = []
    location_late = []

    for e in events:
        vals = e["vals"]
        early = vals[:EARLY_LATE_SPLIT_IDX]
        late = vals[EARLY_LATE_SPLIT_IDX:]
        total = early.sum() + late.sum()
        mass_frac_late.append(late.sum() / total if total > 0 else np.nan)
        location_late.append(late.max() >= early.max())

    return {
        "n_events": len(events),
        "mean_mass_fraction_late": float(np.nanmean(mass_frac_late)),
        "frac_location_late": float(np.mean(location_late)),
        "mean_n_early": float(np.mean([min(e["n"], EARLY_LATE_SPLIT_IDX) for e in events])),
        "mean_n_late": float(np.mean([max(e["n"] - EARLY_LATE_SPLIT_IDX, 0) for e in events])),
    }


def permutation_test(events: list[dict], n_perm: int, rng: np.random.Generator) -> dict:
    observed = summarize(events)
    n_events = len(events)

    sim_mass_late = np.empty(n_perm)
    sim_loc_late = np.empty(n_perm)

    for it in range(n_perm):
        mass_fracs = np.empty(n_events)
        loc_hits = 0
        for i, e in enumerate(events):
            shuffled = e["vals"].copy()
            rng.shuffle(shuffled)
            early = shuffled[:EARLY_LATE_SPLIT_IDX]
            late = shuffled[EARLY_LATE_SPLIT_IDX:]
            total = early.sum() + late.sum()
            mass_fracs[i] = late.sum() / total if total > 0 else np.nan
            if late.max() >= early.max():
                loc_hits += 1
        sim_mass_late[it] = np.nanmean(mass_fracs)
        sim_loc_late[it] = loc_hits / n_events

    null_center_mass = sim_mass_late.mean()
    p_mass = float(np.mean(np.abs(sim_mass_late - null_center_mass) >= abs(observed["mean_mass_fraction_late"] - null_center_mass)))

    null_center_loc = sim_loc_late.mean()
    p_loc = float(np.mean(np.abs(sim_loc_late - null_center_loc) >= abs(observed["frac_location_late"] - null_center_loc)))

    return {
        **observed,
        "null_mass_fraction_late": float(null_center_mass),
        "p_value_mass": p_mass,
        "null_frac_location_late": float(null_center_loc),
        "p_value_location": p_loc,
    }


def print_result(label: str, r: dict, n_excluded: int):
    print(f"\n=== {label} ===")
    print(f"n = {r['n_events']} (excluded {n_excluded} events with <{MIN_TRADING_DAYS} trading days in spike week)")
    print(f"avg early-period trading days = {r['mean_n_early']:.2f}   avg late-period trading days = {r['mean_n_late']:.2f}")

    print(f"\nMove-magnitude mass fraction LATE (days {EARLY_LATE_SPLIT_IDX}-5) vs EARLY (days 0-{EARLY_LATE_SPLIT_IDX-1}):")
    print(f"  observed LATE share: {r['mean_mass_fraction_late']*100:.1f}%   "
          f"null: {r['null_mass_fraction_late']*100:.1f}%   p={r['p_value_mass']:.4f}  "
          f"{'(significant)' if r['p_value_mass'] < 0.05 else '(NOT significant)'}")

    print(f"\nFraction of events where the single biggest move fell LATE vs EARLY:")
    print(f"  observed LATE share: {r['frac_location_late']*100:.1f}%   "
          f"null: {r['null_frac_location_late']*100:.1f}%   p={r['p_value_location']:.4f}  "
          f"{'(significant)' if r['p_value_location'] < 0.05 else '(NOT significant)'}")


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    spike_events, spike_excluded = build_events(SPIKE_ANCHOR_DIR, "{ticker}_zconjunction.csv", "spike_week")
    base_events, base_excluded = build_events(BASE_ANCHOR_DIR, "{ticker}_baseline.csv", "random_week")

    print(f"Spike events: {len(spike_events)} usable, {spike_excluded} excluded (short week)")
    print(f"Baseline events: {len(base_events)} usable, {base_excluded} excluded (short week)")

    print("\nRunning permutation test on SPIKE events...")
    spike_result = permutation_test(spike_events, N_PERMUTATIONS, rng)
    print("Running permutation test on BASELINE events (control)...")
    base_result = permutation_test(base_events, N_PERMUTATIONS, rng)

    print_result("SPIKE events", spike_result, spike_excluded)
    print_result("BASELINE events (control)", base_result, base_excluded)

    print(f"\n({N_PERMUTATIONS} permutations per group, seed={RANDOM_SEED} for reproducibility)")


if __name__ == "__main__":
    main()
