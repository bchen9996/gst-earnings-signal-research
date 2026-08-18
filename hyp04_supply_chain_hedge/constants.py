# Preregistered constants for HYP-04 Phase 0. Fixed here before any real
# event is touched, so an implementer cannot infer them and a reviewer can
# diff them against the plan documents.
#
# Every value below traces to a numbered patch in
# Live Signal Engine/HYP04_PLAN_ROUND2_EDITS.md. Where that doc marks a value
# DEFAULT (confirm or override), it is NOT locked in the preregistration sense
# -- Phase 0 is a feasibility check, not the Phase 2 lock.
from __future__ import annotations

# --- Horizon grid (Patch 3) -----------------------------------------------
# ONE grid, used for both target computation and local-projection lag
# detection. h = 5, 10, 20 are a reporting slice of this same grid, never a
# second computation.
HORIZON_GRID: tuple[int, ...] = tuple(range(1, 21))
REPORTING_HORIZONS: tuple[int, ...] = (5, 10, 20)

# --- Target definition (Patch 9, Round 3 correction) ----------------------
# RVar(h) = (1/h) * sum(r_i^2) -- a VARIANCE (no square root), unbiased for
# sigma^2 at every h. The earlier unnormalized RV(h) = sqrt(sum(r_i^2))
# carried a deterministic sqrt(h) artifact with no volatility content and is
# a bug, not a style choice; test_hyp04_supply_chain_hedge_target.py asserts
# its absence directly.
REFERENCE_WINDOW_TRADING_DAYS = 20

# Floor applied before every log() so an exact-zero return day (halted
# trading, stale or bad data) cannot send the target to -inf. Applied
# identically in the fixture generator and the real-data path.
RVAR_LOG_FLOOR = 1e-12

# --- Earnings-cycle residualization (Section 3 of the plan) ---------------
# A peer's own unconditional vol-vs-days-to-its-own-earnings baseline is
# estimated EXCLUDING windows adjacent to any anchor event, so the baseline
# is not contaminated by the effect being measured.
ANCHOR_ADJACENT_EXCLUSION_TRADING_DAYS = 25

# A peer whose retained history falls below this fraction cannot support a
# reliable baseline. Reported as a universe constraint alongside the
# options-coverage audit, never silently dropped.
#
# The value is set by ARITHMETIC, not by what makes Phase 0 pass. Excluding
# +/-E sessions around each anchor removes about (2E+1)/63 of a peer's
# calendar when anchors report quarterly (63 trading days apart). At the
# E = 25 used here that is ~81% removed, so retention has a STRUCTURAL
# CEILING near 0.20-0.30 for any quarterly-anchor dataset -- measured at
# 0.28 on the synthetic fixtures. A threshold above that ceiling would flag
# every peer in every possible dataset, which is a broken check rather than
# a strict one; a threshold tuned just under the observed value would be
# reverse-engineered from the result. 0.10 sits below the structural ceiling
# and above outright starvation.
#
# Retention alone is not sufficient: the baseline is bucketed on
# days-to-own-earnings, so a peer can clear the fraction while leaving some
# bucket nearly empty. MIN_BUCKET_COUNT is checked alongside it.
MIN_RETAINED_HISTORY_FRACTION = 0.10

# Patch 12 -- ACCEPT AND REPORT, option (c) of three.
#
# An observation whose days-to-own-earnings bucket holds fewer than this many
# baseline estimates is EXCLUDED from the Stage 1 regression sample. It is not
# imputed, and the threshold is NOT to be lowered -- nor the buckets widened --
# to recover sample size after seeing how many observations survive.
#
# Why not widen the buckets: the entire purpose of residualizing against
# days-to-own-earnings is to isolate the universal pre-earnings vol ramp.
# Widening blurs resolution exactly where that ramp is steepest, reintroducing
# the confound residualization exists to remove. Widening is the worst of the
# three options on validity grounds, not merely the least conservative.
#
# Why not lower the threshold: that keeps resolution but degrades baseline
# reliability specifically for the thin, small-cap peers this hypothesis cares
# about most -- the same failure the leakage test exists to catch, approached
# from the input side.
#
# Both this value and the bucket boundaries in target.py::_dte_bucket are
# fixed BEFORE looking at how many observations survive. The excluded fraction
# is reported in the status doc as its own number, distinct from the
# retained-history fraction (that one is about anchor-adjacent history removed
# from baseline ESTIMATION; this one is about bucket population once that
# history is in hand).
MIN_BUCKET_COUNT = 20

# --- N gate (Patch 2, Round 2 + Round 3 corrections) ----------------------
# The gate checks N_eff = N_pairs / DEFF, where DEFF = 1 + (m_bar - 1) * ICC.
# N_pairs and N_events are reported as the two bounds (ICC=0 and ICC=1
# respectively) but are never themselves what clears the gate.
#
# NAIVE_SINGLE_TEST_N is the original power calculation's output at d = 0.5:
# n per group = 2*(1.96 + 0.84)^2 / 0.5^2 ~ 63, so ~126 total. It appears in
# the status doc as a LABELLED BASELINE only -- never as the operative gate.
NAIVE_SINGLE_TEST_N = 126

# Provisional pre-3b placeholder. Superseded by the fixture-derived number
# once step 3b's max-T permutation emits the effective independent-test
# count. Stated as a range because it was a hand estimate, not a computation.
PROVISIONAL_MULTIPLICITY_TARGET_N = (190, 240)

ASSUMED_COHENS_D = 0.5
ALPHA = 0.05
POWER = 0.80
Z_ALPHA_TWO_SIDED = 1.959963984540054
Z_POWER = 0.8416212335729143

# ICC estimates can come out negative with few clusters (a known small-sample
# artifact). An unfloored negative ICC would push DEFF below 1 and make N_eff
# exceed N_pairs, which is backwards for what a design effect represents.
# The RAW estimate is still reported for transparency; only DEFF uses the
# floored value.
ICC_FLOOR = 0.0

# --- Permutation / multiplicity (Patch 2) ---------------------------------
# max-T across the horizon grid, not Bonferroni: RVar(h) is a mean over an
# expanding window, so adjacent beta_h are highly correlated by construction
# and Bonferroni would be badly over-conservative against that correlation.
N_PERMUTATIONS = 2000
RANDOM_SEED = 42

# --- Options-coverage audit (Patch 8, superseded by Patch 13) -------------
# There is deliberately NO default call budget here.
#
# Patch 13 is explicit that the budget is "real money, not a methodology
# choice, and not something that should be picked by an implementer." An
# earlier revision of this file carried DEFAULT_AUDIT_CALL_BUDGET = 500 --
# a number with no basis in observed provider pricing, which is precisely
# the invention that patch exists to prevent. It was removed rather than
# adjusted.
#
# The budget arrives from the repo owner in two stages, and the audit must
# refuse to make its first live call until both are supplied:
#   1. CANARY  -- a small hard cap (e.g. 5-10 candidate peer tickers) to
#                 establish real observed cost-per-call.
#   2. FULL    -- extrapolated from the canary's real numbers to the full
#                 candidate universe, stated as a hard number.
# Hitting either cap fails loudly; it never silently truncates the universe.
AUDIT_BUDGET_MUST_BE_SUPPLIED_BY_OWNER = True

AUDIT_CONSENT_STAGES: tuple[str, ...] = ("canary", "full")

AUDIT_NO_BUDGET_MESSAGE = (
    "Options-coverage audit refused: no owner-supplied call budget. Patch 13 "
    "requires a staged go-ahead -- a hard-capped canary batch first, then a "
    "full-run cap extrapolated from the canary's OBSERVED cost-per-call. "
    "Neither this module nor its caller may choose that number."
)

# --- Stage 2 (Patch 5) ----------------------------------------------------
# Stage 2 protects an ASSUMED existing long-equity holding in the peer name.
# This is an assumption made visible, not an actual position: Phase 0 has no
# real capital logic of any kind.
ASSUMED_PEER_EQUITY_NOTIONAL_USD = 100_000.0

# --- Placeholder-linkage banner -------------------------------------------
PLACEHOLDER_LINKAGE_WARNING = (
    "PLACEHOLDER LINKAGE (same-sector peers) -- the real supply-chain map does "
    "not exist yet. Same limitation as GST_Task2_PeerDivergence.py. No result "
    "from this pipeline is a finding about supply-chain transmission."
)

NO_EDGE_CLAIM = (
    "Phase 0 is a feasibility check. Nothing here demonstrates, or is evidence "
    "for, a hedging edge."
)
