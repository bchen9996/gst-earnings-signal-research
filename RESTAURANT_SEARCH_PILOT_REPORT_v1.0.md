# Pre-Earnings Brand vs Investor Search and Large Earnings Moves

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY`. Not HYP-01 confirmation, not prospective collection.
Targets **magnitude**, never direction — stock direction is never a target anywhere in this pilot.

## Decision

# `NO_INCREMENTAL_SEARCH_VALUE`

**No search family helps, and nothing beats the probabilistic null.**

| Model | **Brier** | Log loss | AUC | Accuracy @0.5 |
|---|---|---|---|---|
| **A.** Intercept-only training prevalence | **0.18454** | **0.55588** | 0.4665 | 0.7561 |
| **B.** Baseline (history / vol / revenue / quarter / ticker) | 0.20211 | 0.62690 | 0.6460 | 0.7317 |
| **C.** B + investor attention (`[TICKER] stock`) | 0.23665 | 0.81574 | 0.6177 | 0.7073 |
| **D.** C + product demand (consumer brand) | 0.24739 | 0.90235 | 0.6427 | 0.6829 |

**Brier gets monotonically worse as features are added.** The intercept-only null wins outright; adding
investor attention makes it worse; adding brand demand makes it worse again.

## Central test — C versus D

`Brier loss(C) − Brier loss(D)`; positive means product demand helped.

> raw mean **−0.010745**, 95% CI [−0.041115, +0.019625]
> **CR2/BRL clustered by ticker** (8 clusters, Satterthwaite df 6.543): mean −0.010745,
> SE 0.02501, **t = −0.430, p = 0.68126, CI [−0.070734, +0.049243]**

**D beats C on 59.76% of individual events** — yet the mean is *negative*. Product demand wins slightly
more often but loses much more heavily when it loses. Counting wins would invert the conclusion; the
loss mean and the clustered interval do not support any improvement.

`PRODUCT_DEMAND_ADDS_INCREMENTAL_VALUE` requires D to beat C on pooled Brier **and** a clustered
interval supporting positive improvement. Neither holds.

## Tail lift — the one place ordering survives, and it favours *no* search

Large-move base rate 24.39% (82 OOS events).

| Model | Top-quintile n | Realized large-move rate | Lift |
|---|---|---|---|
| **B** (no search) | 17 | **35.29%** | **1.447×** |
| C (+ investor) | 17 | 29.41% | 1.206× |
| D (+ product) | 17 | 23.53% | 0.965× |

Adding search **degrades** tail ranking monotonically. Model D's top quintile is no better than the
base rate.

## Continuous magnitude (ridge on |return|)

| Model | MAE (pp) |
|---|---|
| **B** | **5.4534** |
| C | 5.6790 |
| D | 5.8543 |

Same ordering: search makes the continuous forecast worse too.

## Calibration — Model D

| Bin | n | Mean predicted | Observed rate |
|---|---|---|---|
| 1 | 21 | 0.0032 | 0.0952 |
| 2 | 20 | 0.0594 | 0.2000 |
| 3 | 20 | 0.2614 | 0.4500 |
| 4 | 21 | **0.7549** | **0.2381** |

D is badly miscalibrated: it is far too confident in its top bin, where the realized rate (23.8%) is
*below* the base rate. AUC near 0.64 with a worse Brier than a constant is the signature of usable
*ordering* destroyed by overconfident probabilities — which is exactly why Brier, not AUC, is primary.

## Sample and timing

210 candidate events → **122 complete** (all 8 tickers usable, no query unavailable) → **82
out-of-sample** after the 40-event minimum training window, 2021-07-20 → 2025-11-06.

Per ticker: SBUX 19, WING 19, DPZ 18, CMG 18, MCD 18, BROS 17, TXRH 7, CAVA 6.
Timing from SEC 8-K item 2.02 acceptance timestamps: **63 AMC, 59 BMO**.

**Leakage assertion: 353 checks, 0 violations.** Every search week used closes strictly before its
announcement timestamp; the check is mechanical and per-event, not a claim.

## Relationship to PR #27 — read this before citing either

PR #27 found brand search did **not** improve quarterly revenue-growth MAE. That result is untouched
here: it was not reinterpreted, retuned or rerun. This pilot **reuses PR #27's exact frozen query map
and its weekly consumer series**.

**A success on this target would not have overturned PR #27's revenue-nowcasting null** — they are
different targets (earnings-move magnitude vs revenue growth), and neither result substitutes for the
other. As it happens both are negative, but that coincidence is not evidence for either.

**Two disclosures about the reuse**, since it changes what was executed versus this task's own spec:

| Ticker | This task's frozen query | Query actually used (PR #27) |
|---|---|---|
| CMG | `Chipotle` | `Chipotle Mexican Grill` |
| BROS | `Dutch Bros` | `Dutch Bros Coffee` |

Reuse also caps consumer history at PR #27's window (2020-12-27 →), so with the 52-week baseline the
product features only become available from late 2021 — which is why the panel starts 2021-07-20
rather than 2019. The investor `[TICKER] stock` series was fetched for this pilot (2018-12-30 →) since
PR #27 contained none.

## Historical options

**`OPTIONS_HISTORY_UNAVAILABLE`.** No per-event pre-announcement implied move exists for these tickers:
the repository's committed IV files cover a single ticker (SBUX) and are keyed on the GST spike window
this task forbids, and no authenticated options provider is configured (`APCA_API_KEY_ID` absent, no
vendor keys). **Current options data was not substituted, and no implied move was reconstructed from
realized returns.** The main pilot continued without an options sensitivity baseline.

## Discipline

Universe and queries frozen before retrieval; nothing added, removed, replaced or ranked after seeing
outcomes. One fixed robust transformation — `(x − median₅₂) / (1.4826 · MAD₅₂)` — applied identically
to both search families; no window, transformation or alternate-term search. The large-move threshold
is the **75th percentile of the training fold only**, recomputed at every step. Regularization is
chosen inside each training fold from a grid fixed in advance (`C ∈ {0.1, 1, 10}`,
`alpha ∈ {0.1, 1, 10}`). Expanding chronological folds; events are never shuffled; identical folds and
observations across A/B/C/D. Unique ticker-event identities only. No matched controls, no
outcome-driven feature selection, no post-hoc thresholds.

One baseline feature required a correction found during the run: quarterly revenue facts are re-filed
under multiple accessions, so a naive "exactly one year-ago match" test silently dropped every
established company (122 events → 3). Deduplicating to the earliest-filed value per period end fixed
it. That is a point-in-time-preserving dedup, not an outcome-driven choice.

## Scope

This tests two search families on eight restaurant companies over 2021–2025 against one prespecified
model pair. It does not establish that no search construction could predict earnings-move magnitude,
and it says nothing about direction — which was never a target.

Reproduce: `python tools/run_restaurant_search_demand_pilot.py`
