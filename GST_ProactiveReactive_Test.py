#!/usr/bin/env python3
# GST Proactive-vs-Reactive Test — is the volatility effect (spike weeks
# show ~2x the biggest-move magnitude of baseline weeks) concentrated
# BEFORE the spike week (search interest reacting to a move that already
# started) or AFTER it (search interest leading a move still to come)?
#
# This matters for the live signal engine / straddle logger built earlier:
# if the big move typically happens in the days BEFORE the spike is
# detected, a live signal fired at spike detection is already too late to
# capture it. If it's concentrated AFTER, the signal has real forward
# value.
#
# For each spike event's existing 3-week window (anchor-7 to anchor+13),
# split at the anchor into:
#   BEFORE = anchor-7 .. anchor-1   (days strictly before the spike week)
#   AFTER  = anchor   .. anchor+13  (the spike week itself, and after)
#
# Two measures per event:
#   1. location_after (binary) — did the single biggest |excess return| day
#      in the whole window fall in AFTER (True) or BEFORE (False)?
#   2. mass_fraction_after (continuous) — what share of the window's total
#      |excess return| mass (sum of daily |excess return|) fell in AFTER?
#
# *** WHY NOT JUST COMPARE TO 50/50 ***
# BEFORE is ~7 calendar days (~5 trading days), AFTER is ~14 calendar days
# (~10 trading days) — AFTER has roughly 2x as many trading days as BEFORE.
# Even with zero real temporal effect, the single biggest move would land
# in AFTER more often than BEFORE just because it has more chances (more
# days). So both measures are tested against a PERMUTATION null that
# reshuffles each event's own observed |excess return| values across its
# own window positions (preserving that event's actual before/after day
# counts and its actual set of move magnitudes) — this isolates whether
# POSITION within the window matters, independent of the day-count
# imbalance.
#
# Baseline (random-week) events get the identical treatment as a control:
# if baseline windows show the same "after-heavy" pattern as spike windows,
# that's just the day-count imbalance, not something special about spikes.

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


def before_after_values(daily: pd.DataFrame, anchor: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    before_mask = (daily["Date"] >= anchor - timedelta(days=7)) & (daily["Date"] <= anchor - timedelta(days=1))
    after_mask = (daily["Date"] >= anchor) & (daily["Date"] <= anchor + timedelta(days=13))
    before_vals = daily.loc[before_mask, EX_COL].abs().to_numpy()
    after_vals = daily.loc[after_mask, EX_COL].abs().to_numpy()
    return before_vals, after_vals


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
            before_vals, after_vals = before_after_values(daily, anchor)
            if len(before_vals) == 0 or len(after_vals) == 0:
                continue
            events.append({
                "ticker": ticker, "anchor": anchor.date(),
                "before_vals": before_vals, "after_vals": after_vals,
                "n_before": len(before_vals), "n_after": len(after_vals),
            })
    return events


def summarize(events: list[dict]) -> dict:
    locations_after = []
    mass_fracs = []
    for e in events:
        max_before = e["before_vals"].max()
        max_after = e["after_vals"].max()
        locations_after.append(max_after >= max_before)

        total_mass = e["before_vals"].sum() + e["after_vals"].sum()
        mass_fracs.append(e["after_vals"].sum() / total_mass if total_mass > 0 else np.nan)

    return {
        "n_events": len(events),
        "frac_events_after": float(np.mean(locations_after)),
        "mean_mass_fraction_after": float(np.nanmean(mass_fracs)),
        "mean_n_before": float(np.mean([e["n_before"] for e in events])),
        "mean_n_after": float(np.mean([e["n_after"] for e in events])),
    }


def permutation_test(events: list[dict], n_perm: int, rng: np.random.Generator) -> dict:
    observed = summarize(events)
    sim_frac_after = np.empty(n_perm)
    sim_mass_frac = np.empty(n_perm)

    for p in range(n_perm):
        locations_after = np.empty(len(events), dtype=bool)
        mass_fracs = np.empty(len(events))
        for i, e in enumerate(events):
            combined = np.concatenate([e["before_vals"], e["after_vals"]])
            rng.shuffle(combined)
            sim_before = combined[:e["n_before"]]
            sim_after = combined[e["n_before"]:]
            locations_after[i] = sim_after.max() >= sim_before.max()
            total = sim_before.sum() + sim_after.sum()
            mass_fracs[i] = sim_after.sum() / total if total > 0 else np.nan
        sim_frac_after[p] = locations_after.mean()
        sim_mass_frac[p] = np.nanmean(mass_fracs)

    null_center_loc = sim_frac_after.mean()
    p_loc = float(np.mean(np.abs(sim_frac_after - null_center_loc) >= abs(observed["frac_events_after"] - null_center_loc)))

    null_center_mass = sim_mass_frac.mean()
    p_mass = float(np.mean(np.abs(sim_mass_frac - null_center_mass) >= abs(observed["mean_mass_fraction_after"] - null_center_mass)))

    return {
        **observed,
        "null_frac_events_after": float(null_center_loc),
        "p_value_location": p_loc,
        "null_mass_fraction_after": float(null_center_mass),
        "p_value_mass_fraction": p_mass,
    }


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    spike_events = build_events(SPIKE_ANCHOR_DIR, "{ticker}_zconjunction.csv", "spike_week")
    base_events = build_events(BASE_ANCHOR_DIR, "{ticker}_baseline.csv", "random_week")

    print(f"Spike events with usable before+after data: {len(spike_events)}")
    print(f"Baseline events with usable before+after data: {len(base_events)}\n")

    print("Running permutation test on SPIKE events...")
    spike_result = permutation_test(spike_events, N_PERMUTATIONS, rng)
    print("Running permutation test on BASELINE events (control)...")
    base_result = permutation_test(base_events, N_PERMUTATIONS, rng)

    for label, r in [("SPIKE events", spike_result), ("BASELINE events (control)", base_result)]:
        print(f"\n=== {label} ===")
        print(f"n = {r['n_events']}   avg trading days before = {r['mean_n_before']:.2f}   "
              f"avg trading days after = {r['mean_n_after']:.2f}")
        print(f"Fraction of events where the single biggest move fell AFTER the spike week: "
              f"{r['frac_events_after']*100:.1f}%")
        print(f"  Permutation null (day-count/magnitude-set only, no positional effect): {r['null_frac_events_after']*100:.1f}%")
        print(f"  Two-sided p-value: {r['p_value_location']:.4f}  "
              f"{'(significant at 0.05)' if r['p_value_location'] < 0.05 else '(NOT significant at 0.05)'}")
        print(f"Mean fraction of |excess return| mass in the AFTER period: {r['mean_mass_fraction_after']*100:.1f}%")
        print(f"  Permutation null: {r['null_mass_fraction_after']*100:.1f}%")
        print(f"  Two-sided p-value: {r['p_value_mass_fraction']:.4f}  "
              f"{'(significant at 0.05)' if r['p_value_mass_fraction'] < 0.05 else '(NOT significant at 0.05)'}")

    print(f"\n({N_PERMUTATIONS} permutations per group, seed={RANDOM_SEED} for reproducibility)")


if __name__ == "__main__":
    main()
