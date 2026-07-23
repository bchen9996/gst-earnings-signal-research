# ============================================================================
# FOLLOW-UP CELL -- run this AFTER QC_Options_Validation_Script.py in the
# SAME notebook session (it reuses the `results_df` DataFrame already built
# by that cell; no re-pulling of History data needed).
#
# 1. Excludes the corrupted NFLX event (real_cost_pct_of_spot=719%, a broken
#    strike/expiry match, not a real result) from the summary stats.
# 2. Recomputes win rate / median return error / median pricing error on the
#    remaining events.
# 3. Separately reports the same stats for ONLY the 10 randomly-selected
#    events (excluding the 10 top-winner and 10 top-loser stratified picks
#    and the MSFT-completeness additions) -- this subsample is the unbiased
#    read on the true population win rate, since the winner/loser groups
#    were deliberately selected on the OUTCOME variable and will overstate
#    dispersion either way.
#
# NOTE ON THE CORRUPTED EVENT'S IDENTITY: this project's canonical unique
# key for an event is (ticker, spike_week), not exit_date. The NFLX event
# with spike_week=2025-01-19 has exit_date=2025-01-24 -- if you spotted the
# corrupted row by its exit_date column in results_df, this is the same row.
# Matched below by (ticker, spike_week) to avoid any ambiguity.
#
# NOTE ON OVERLAP: this NFLX event is ALSO one of the 10 randomly-selected
# events (its random draw happened to land on it), so excluding it drops the
# random-only subsample to n=9, not 10 -- it is excluded from BOTH groups
# below, not just the full sample, since it's a data bug, not a real result,
# regardless of which stratum it happens to belong to.
# ============================================================================

import pandas as pd

CORRUPTED_EVENTS = [
    ("NFLX", pd.Timestamp("2025-01-19")),   # exit_date=2025-01-24; real_cost_pct_of_spot=719%
]

# Exact (ticker, spike_week) pairs in the "10 randomly-selected" stratum
# (RandomState seed=42 against FixedWindow_PerEvent_Canonical.csv) --
# reproduced here since results_df/sample carry no stratum-source column.
RANDOM_SAMPLE_KEYS = [
    ("ADBE", pd.Timestamp("2025-12-07")),
    ("AMZN", pd.Timestamp("2025-07-27")),
    ("BRK-B", pd.Timestamp("2025-02-23")),
    ("LDOS", pd.Timestamp("2024-02-11")),
    ("LDOS", pd.Timestamp("2024-10-27")),
    ("MSFT", pd.Timestamp("2023-04-23")),
    ("NFLX", pd.Timestamp("2023-01-15")),
    ("NFLX", pd.Timestamp("2025-01-19")),   # <- the corrupted one; excluded below
    ("SYK", pd.Timestamp("2024-01-28")),
    ("TTWO", pd.Timestamp("2024-05-12")),
]

results_df["spike_week"] = pd.to_datetime(results_df["spike_week"])
complete = results_df[results_df["real_pnl_pct"].notna()].copy()

is_corrupted = complete.apply(lambda r: (r["ticker"], r["spike_week"]) in CORRUPTED_EVENTS, axis=1)
clean = complete[~is_corrupted].copy()

print(f"Successfully priced (pre-exclusion): n={len(complete)}")
print(f"Excluded as corrupted: {int(is_corrupted.sum())}")
print(f"Clean sample: n={len(clean)}\n")


def summarize(d, label):
    if d.empty:
        print(f"{label}: n=0, no data")
        return
    real_win_rate = d["real_win"].mean() * 100
    match_rate = d["win_match"].mean() * 100
    med_return_err = d["return_error_pct_points"].median()
    med_pricing_err = d["pricing_error_pct_points"].median()
    print(f"{label}:")
    print(f"    n = {len(d)}")
    print(f"    win rate (real, quote-derived)       = {real_win_rate:.1f}%")
    print(f"    median return error (real - modeled)  = {med_return_err:+.2f} pct points")
    print(f"    median pricing error (real - modeled) = {med_pricing_err:+.2f} pct points")
    print(f"    [secondary] model/real win-match rate = {match_rate:.1f}%")
    print()


summarize(clean, f"FULL SAMPLE, corrupted NFLX excluded (n={len(clean)})")

is_random = clean.apply(lambda r: (r["ticker"], r["spike_week"]) in RANDOM_SAMPLE_KEYS, axis=1)
random_only = clean[is_random].copy()
summarize(random_only, "RANDOM-ONLY SUBSAMPLE (unbiased read on true population win rate)")

display(clean[["ticker", "spike_week", "real_pnl_pct", "modeled_pnl_pct", "real_win", "modeled_win",
               "win_match", "return_error_pct_points", "pricing_error_pct_points"]]
        .sort_values(["ticker", "spike_week"]))
