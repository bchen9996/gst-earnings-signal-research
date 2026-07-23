#!/usr/bin/env python3
# TASK 3 — Macro event exclusion: does the STRONG_EARNINGS (z>=5) edge
# survive excluding events within 2 days of an FOMC decision or CPI
# release (i.e. is the "earnings-adjacent" signal actually just picking
# up broad market-wide vol spikes around known macro catalysts, not
# something specific to the company's own earnings)?
#
# *** CALENDAR CONFIDENCE — DISCLOSED, NOT UNIFORM ***
# No FRED API key is configured in this environment, so both calendars
# are hardcoded from public knowledge rather than pulled:
#   FOMC decision dates: HIGH CONFIDENCE. These are among the most widely
#     published, stable dates in finance (fixed meeting schedule announced
#     a year+ in advance) — 8 meetings/year, 2021-2025, decision date =
#     the second day of each 2-day meeting.
#   CPI release dates: LOWER CONFIDENCE. BLS releases CPI monthly, usually
#     in the second week, but the EXACT day genuinely varies month to
#     month and this list is reconstructed from memory, not verified
#     against an authoritative feed. Treat this specific list as a
#     best-effort approximation, not a verified historical record — if
#     precision matters for a real trading decision, cross-check against
#     BLS's official release calendar before relying on it.
#
# Output: Live Signal Engine/Task3_MacroEventExclusion_Results.csv

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

GROUP_A_PATH = Path("Earnings-Adjacent Spike vs No-Spike Test") / "group_a_z4_earnings_adjacent.csv"
OUT_PATH = Path("Live Signal Engine") / "Task3_MacroEventExclusion_Results.csv"

Z_THRESHOLD = 5.0
EXCLUSION_WINDOW_DAYS = 2
N_PERMUTATIONS = 10000
RANDOM_SEED = 42

# HIGH CONFIDENCE — FOMC decision dates (2nd day of each 2-day meeting), 2021-2025
FOMC_DATES = [
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
]

# LOWER CONFIDENCE — CPI release dates (approximate, see header disclosure)
CPI_DATES = [
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12", "2021-06-10",
    "2021-07-13", "2021-08-11", "2021-09-14", "2021-10-13", "2021-11-10", "2021-12-10",
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11", "2022-06-10",
    "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13", "2022-11-10", "2022-12-13",
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10", "2023-06-13",
    "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12", "2023-11-14", "2023-12-12",
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15", "2024-06-12",
    "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13", "2025-06-11",
    "2025-07-15", "2025-08-12", "2025-09-11", "2025-10-10", "2025-11-13", "2025-12-10",
]


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


def main():
    print(f"*** TASK 3: Macro event exclusion (z>={Z_THRESHOLD:g}, +/-{EXCLUSION_WINDOW_DAYS}d of FOMC/CPI) ***\n")
    print(f"FOMC dates loaded: {len(FOMC_DATES)} (high confidence)")
    print(f"CPI dates loaded: {len(CPI_DATES)} (lower confidence, approximate — see script header)\n")

    macro_dates = pd.to_datetime(FOMC_DATES + CPI_DATES)

    events = pd.read_csv(GROUP_A_PATH)
    events = events[events["zscore"] >= Z_THRESHOLD].copy()
    events["spike_week"] = pd.to_datetime(events["spike_week"])
    win_col, pnl_col = "end_of_spike_week_win", "end_of_spike_week_pnl_pct"

    def near_macro(anchor):
        gaps = (macro_dates - anchor).days.to_numpy()
        return bool((np.abs(gaps) <= EXCLUSION_WINDOW_DAYS).any())

    events["near_macro_event"] = events["spike_week"].apply(near_macro)

    full = events[events[win_col].notna()]
    cleaned = events[~events["near_macro_event"]]
    cleaned_usable = cleaned[cleaned[win_col].notna()]
    excluded = events[events["near_macro_event"]]
    excluded_usable = excluded[excluded[win_col].notna()]

    print(f"Full baseline: n={len(full)}  win={full[win_col].mean()*100:.1f}%  median={full[pnl_col].median():+.1f}%")
    print(f"Excluded (within {EXCLUSION_WINDOW_DAYS}d of FOMC/CPI): n={len(excluded_usable)}  "
          f"win={excluded_usable[win_col].mean()*100:.1f}% median={excluded_usable[pnl_col].median():+.1f}%"
          if len(excluded_usable) else f"Excluded: n=0")
    print(f"Cleaned subset (macro-adjacent removed): n={len(cleaned_usable)}  "
          f"win={cleaned_usable[win_col].mean()*100:.1f}%  median={cleaned_usable[pnl_col].median():+.1f}%")

    if len(cleaned_usable) and len(excluded_usable):
        rng = np.random.default_rng(RANDOM_SEED)
        diff, p = two_sample_permutation_test(
            cleaned_usable[pnl_col].to_numpy(dtype=float), excluded_usable[pnl_col].to_numpy(dtype=float),
            N_PERMUTATIONS, rng)
        sig = "significant" if p < 0.05 else "not significant"
        print(f"\nDiff (cleaned - macro-adjacent), P&L: {diff:+.1f}pt  p={p:.4f} ({sig})")

    events.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
