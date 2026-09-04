# Retrospective citation policy — v1.0

**Date:** 2026-09-04
**Discharges:** `PREREGISTRATION_GAP_AUDIT_v1.0.md` item **B3**, "Citation policy
for reconstructed retrospective results", severity **Critical (publication)**,
deadline `BEFORE_PUBLICATION`.
**Governs citation only.** It changes no prospective design, no threshold, no
estimator, no universe and no gate. It creates no result and reclassifies no
hypothesis.

---

## 1. Why this exists

The gap audit's B3 row states the problem exactly:

> the retrospective population's point-in-time check is **failed**; no policy
> states whether, and with what caveat, any retrospective figure may be cited
> externally

Two facts made that gap live rather than theoretical:

- **`RETROSPECTIVE_DEVELOPMENT_ONLY` is stamped on artifacts across the project
  and is defined nowhere.** A label that governs nothing is decoration.
- **Two committed artifacts currently disagree about whether the same two
  numbers may be cited**, and a manuscript cites them. §5 disposes of that case.

## 2. What a retrospective figure is

A figure is **retrospective** if it was computed on data assembled after the
outcomes existed — the reconstructed population, its decomposition, its
strategy scorecard, and every statistic derived from them. The governing fact
about all of them is recorded in `PROJECT_NORTH_STAR_v1.0_DRAFT.md` §4:

> **That reconstruction has a failed point-in-time validity check and is not
> prospective confirmation.**

**`RETROSPECTIVE_DEVELOPMENT_ONLY`**, used as a status token throughout, is
hereby defined to mean exactly this: *computed on the reconstruction; carries
the failed point-in-time check; confirms no hypothesis; may not be described as
prospective, preregistered, out-of-sample, or confirmatory.*

## 3. Citation states

Every retrospective figure sits in exactly one state.

| State | Meaning | May appear in an external document? |
|---|---|---|
| `CURRENT` | Computed on data no known defect reaches | **Yes**, with the §4 caveats |
| `SUPERSEDED` | A later artifact recomputed it | **No** — cite the successor |
| `DO_NOT_CITE_PENDING_CORRECTION` | A known defect reaches its inputs and no corrected value has been computed | **No** |

The third state's meaning is taken verbatim from
`CORRECTION_OVERLAY_2026-08-22.md` §8, and it is narrower than it sounds:

> These results are **not withdrawn and not asserted to be wrong.** They are
> unsafe to cite until recomputed, because their stated inference rests on
> assumptions the verified data violate.

**Rule 3a — the restrictive label wins.** Where two artifacts assign different
states to the same figure, **the more restrictive state governs** until a dated
artifact reconciles them. A figure is not made citable by a later document that
was unaware of the defect.

**Rule 3b — recomputation, not re-labelling, is what clears the third state.**
The state is cleared by computing the corrected value and reporting it,
whatever it turns out to be. It is never cleared by argument that the defect is
small, and never by a later audit marking the figure `CURRENT`.

**Rule 3c — the correction's own numbers travel with it.** When a corrected
value replaces a defective one, the external document reports what changed, in
which direction, and what was lost. A correction that quietly substitutes a
better number is a worse failure than the defect.

## 4. Caveats every retrospective citation carries

1. The point-in-time validity check is **failed**, not waived.
2. The figure **confirms no hypothesis**. Every display gate is CLOSED and every
   eligible-event count is zero.
3. It is **not** prospective, preregistered, out-of-sample, or confirmatory.
4. Where implementation validation is cited, it carries its own limit verbatim:
   agreement with an independent reference *"is not evidence that CR2 is the
   scientifically correct or optimal estimator for HYP-01, and it is not a
   result about the world."*

**Sample-scope claims must match the specification quoted.** A ticker or event
count true of one analysis is not automatically true of another computed on a
subset — see §5's second finding for a live instance.

## 5. Disposition of the open case

`CORRECTION_OVERLAY_2026-08-22.md` §9 marks these `AFFECTED` — they pool 152
treated and 133 control rows containing 20 self-matches and 48 redundant
control rows — and §8 assigns them `DO_NOT_CITE_PENDING_CORRECTION`:

| statistic | value as published | in the manuscript as |
|---|---|---|
| `primary_magnitude_abs_day_return` | +1.509 pp, p = 0.0662 | the primary inferential specification |
| `strategy_E_incremental_high_gst` | +0.013 pp, p = 0.98332 | **the headline incremental null** |

`SIGNAL_WITHOUT_STRATEGY_NUMBER_AUDIT_v1.1.md` marks both `CURRENT`. Under
**Rule 3a the overlay governs**, and both are `DO_NOT_CITE_PENDING_CORRECTION`
until recomputed. `CORRECTIVE_REPORT_2026-08-22.md` §7 states the position
plainly: the incremental null *"remains `DO_NOT_CITE_PENDING_CORRECTION` and
remains un-recomputed."*

**Disposition, decided 2026-09-04: recompute both on the corrected sample, then
cite the corrected values under Rule 3c.** Reporting whatever results, including
a reversal of the incremental null. Until that computation exists and is
committed, neither figure may appear in an external document.

Two further corrections the same submission must carry, both measured:

- **The scope claim is wrong for the matched result.** "28 companies" is true of
  the 285-event pooled regression. The 73-pair analysis uses **26 clusters**, and
  the treated arm spans **27** tickers — JBL appears only as a control. The
  overlay's own phrasing is the correct one: *"28 tickers in the retrospective
  matched population (27 in the treated arm)."*
- **The control arm is attenuated, and the disclosure understates it.** Controls
  were not required to fall below the signal threshold, and among the 73
  survivors **6 are themselves z ≥ 5 STRONG-tier events**, 32 are z ≥ 2, and the
  largest control z (14.60) exceeds the *median* signal z (7.97). Stating that
  controls "were not required to fall below that threshold" is true but leaves
  the magnitude to the reader's imagination; the counts belong in the text.

**Not affected, and not to be swept up:** the 73-pair corrected result
(+2.0797 pp, p = 0.00397) is computed on 73 unique treated and 73 unique control
identities with zero overlap — verified by subtracting the 60 dropped pairs from
the 133 usable ones. The strategy figure `0.8543%` and the magnitude-forecast
numbers are one-sample or out-of-lineage statistics the overlay lists
explicitly as **UNAFFECTED**.

## 6. What this does not do

It does not approve a submission, clear any display gate, resolve any other gap
audit item, or make any retrospective figure into evidence about a hypothesis.
It states which figures may be cited, in what state, and carrying what.

---

*No result, direction, effect estimate, plot, p-value or confidence interval is
created or displayed by this document. Every display gate remains CLOSED and
every eligible-event count remains zero.*
