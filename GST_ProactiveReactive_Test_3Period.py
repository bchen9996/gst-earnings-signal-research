#!/usr/bin/env python3
# GST Proactive-vs-Reactive Test — 3-period refinement of
# GST_ProactiveReactive_Test.py. Splits each event's existing 3-week window
# (anchor-7 to anchor+13) into three roughly equal ~7-calendar-day (~5
# trading-day) periods instead of two:
#   BEFORE      = anchor-7 .. anchor-1   (before the spike week)
#   SPIKE WEEK  = anchor+0 .. anchor+6   (the week GST actually spiked)
#   AFTER       = anchor+7 .. anchor+13  (strictly after the spike week)
#
# This distinguishes two very different stories that the prior two-period
# test couldn't separate: a move concentrated in SPIKE WEEK itself would
# limit real-time actionability (the move and the detectable spike happen
# in the same week — by the time weekly GST data confirms the spike, the
# week's move may already be largely realized), whereas a move concentrated
# in AFTER (strictly the following week or two) is the case that actually
# supports the live signal engine's design (spike detected -> real forward
# window still to capture).
#
# Because all three periods are now ~equal length (~5 trading days each),
# the permutation null (day-count/magnitude-set only, no positional effect)
# should sit close to ~1/3 each — unlike the prior 2-period test where
# AFTER's null was inflated to ~67% purely by being twice as long as
# BEFORE. Same permutation methodology as before: reshuffle each event's
# own observed |excess return| values across its own window positions,
# preserving that event's actual period day-counts.
#
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

PERIODS = ["before", "spike_week", "after"]


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


def period_values(daily: pd.DataFrame, anchor: pd.Timestamp) -> dict:
    before_mask = (daily["Date"] >= anchor - timedelta(days=7)) & (daily["Date"] <= anchor - timedelta(days=1))
    spike_mask = (daily["Date"] >= anchor) & (daily["Date"] <= anchor + timedelta(days=6))
    after_mask = (daily["Date"] >= anchor + timedelta(days=7)) & (daily["Date"] <= anchor + timedelta(days=13))
    return {
        "before": daily.loc[before_mask, EX_COL].abs().to_numpy(),
        "spike_week": daily.loc[spike_mask, EX_COL].abs().to_numpy(),
        "after": daily.loc[after_mask, EX_COL].abs().to_numpy(),
    }


def build_events(anchor_dir: Path, pattern: str, anchor_col: str) -> list[dict]:
    events = []
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
            vals = period_values(daily, anchor)
            if any(len(vals[p]) == 0 for p in PERIODS):
                continue
            events.append({
                "ticker": ticker, "anchor": anchor.date(),
                "vals": vals,
                "n": {p: len(vals[p]) for p in PERIODS},
            })
    return events


def summarize(events: list[dict]) -> dict:
    mass_fracs = {p: [] for p in PERIODS}
    location_counts = {p: 0 for p in PERIODS}

    for e in events:
        totals = {p: e["vals"][p].sum() for p in PERIODS}
        grand_total = sum(totals.values())
        for p in PERIODS:
            mass_fracs[p].append(totals[p] / grand_total if grand_total > 0 else np.nan)

        maxes = {p: e["vals"][p].max() for p in PERIODS}
        argmax_period = max(maxes, key=maxes.get)
        location_counts[argmax_period] += 1

    n = len(events)
    return {
        "n_events": n,
        "mean_mass_fraction": {p: float(np.nanmean(mass_fracs[p])) for p in PERIODS},
        "frac_location": {p: location_counts[p] / n for p in PERIODS},
        "mean_n": {p: float(np.mean([e["n"][p] for e in events])) for p in PERIODS},
    }


def permutation_test(events: list[dict], n_perm: int, rng: np.random.Generator) -> dict:
    observed = summarize(events)
    n_events = len(events)

    sim_mass = {p: np.empty(n_perm) for p in PERIODS}
    sim_loc = {p: np.empty(n_perm) for p in PERIODS}

    for it in range(n_perm):
        mass_fracs = {p: np.empty(n_events) for p in PERIODS}
        loc_hits = {p: 0 for p in PERIODS}

        for i, e in enumerate(events):
            combined = np.concatenate([e["vals"][p] for p in PERIODS])
            rng.shuffle(combined)
            splits = {}
            idx = 0
            for p in PERIODS:
                n_p = e["n"][p]
                splits[p] = combined[idx: idx + n_p]
                idx += n_p

            totals = {p: splits[p].sum() for p in PERIODS}
            grand_total = sum(totals.values())
            for p in PERIODS:
                mass_fracs[p][i] = totals[p] / grand_total if grand_total > 0 else np.nan

            maxes = {p: splits[p].max() for p in PERIODS}
            argmax_period = max(maxes, key=maxes.get)
            loc_hits[argmax_period] += 1

        for p in PERIODS:
            sim_mass[p][it] = np.nanmean(mass_fracs[p])
            sim_loc[p][it] = loc_hits[p] / n_events

    result = {**observed, "null_mass_fraction": {}, "p_value_mass": {},
              "null_frac_location": {}, "p_value_location": {}}
    for p in PERIODS:
        null_center_mass = sim_mass[p].mean()
        result["null_mass_fraction"][p] = float(null_center_mass)
        result["p_value_mass"][p] = float(np.mean(
            np.abs(sim_mass[p] - null_center_mass) >= abs(observed["mean_mass_fraction"][p] - null_center_mass)))

        null_center_loc = sim_loc[p].mean()
        result["null_frac_location"][p] = float(null_center_loc)
        result["p_value_location"][p] = float(np.mean(
            np.abs(sim_loc[p] - null_center_loc) >= abs(observed["frac_location"][p] - null_center_loc)))

    return result


def print_result(label: str, r: dict):
    print(f"\n=== {label} ===")
    print(f"n = {r['n_events']}   avg trading days: "
          + ", ".join(f"{p}={r['mean_n'][p]:.2f}" for p in PERIODS))

    print("\nMove-magnitude mass fraction by period:")
    for p in PERIODS:
        obs = r["mean_mass_fraction"][p]
        null = r["null_mass_fraction"][p]
        pval = r["p_value_mass"][p]
        sig = "significant" if pval < 0.05 else "not significant"
        print(f"  {p:>10}: observed {obs*100:5.1f}%   null {null*100:5.1f}%   p={pval:.4f} ({sig})")

    print("\nFraction of events where the single biggest move fell in each period:")
    for p in PERIODS:
        obs = r["frac_location"][p]
        null = r["null_frac_location"][p]
        pval = r["p_value_location"][p]
        sig = "significant" if pval < 0.05 else "not significant"
        print(f"  {p:>10}: observed {obs*100:5.1f}%   null {null*100:5.1f}%   p={pval:.4f} ({sig})")


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    spike_events = build_events(SPIKE_ANCHOR_DIR, "{ticker}_zconjunction.csv", "spike_week")
    base_events = build_events(BASE_ANCHOR_DIR, "{ticker}_baseline.csv", "random_week")

    print(f"Spike events with usable 3-period data: {len(spike_events)}")
    print(f"Baseline events with usable 3-period data: {len(base_events)}")

    print("\nRunning permutation test on SPIKE events...")
    spike_result = permutation_test(spike_events, N_PERMUTATIONS, rng)
    print("Running permutation test on BASELINE events (control)...")
    base_result = permutation_test(base_events, N_PERMUTATIONS, rng)

    print_result("SPIKE events", spike_result)
    print_result("BASELINE events (control)", base_result)

    print(f"\n({N_PERMUTATIONS} permutations per group, seed={RANDOM_SEED} for reproducibility)")


if __name__ == "__main__":
    main()
