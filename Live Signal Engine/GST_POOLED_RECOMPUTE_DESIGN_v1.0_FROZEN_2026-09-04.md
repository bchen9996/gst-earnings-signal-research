# Pooled clustered-inference recompute — frozen design

**Date:** 2026-09-04
**Status:** FROZEN. Written **before any corrected value has been computed.**
No corrected coefficient, standard error, t-statistic or p-value exists at the
time this document is written, and nothing here estimates what they will be.

---

## 1. Why

`CORRECTION_OVERLAY_2026-08-22.md` §9 marks four pooled clustered-inference
results `AFFECTED`, and §8 assigns them `DO_NOT_CITE_PENDING_CORRECTION`:

> These results are **not withdrawn and not asserted to be wrong.** They are
> unsafe to cite until recomputed, because their stated inference rests on
> assumptions the verified data violate.

Two of the four are load-bearing in a manuscript being prepared for submission.
`GST_RETROSPECTIVE_CITATION_POLICY_v1.0_2026-09-04.md` Rule 3b states that the
label is cleared by **computing the corrected value and reporting it, whatever
it turns out to be** — never by re-labelling. This design is that computation,
specified in advance.

It follows the precedent set by `CORRECTIVE_DESIGN_v1.0_FROZEN_2026-08-22.md`,
which froze its rules before running and is the reason its result is credible.

## 2. The defect, reproduced independently

Measured directly from `Live Signal Engine/retrospective_event_components.csv`
(285 rows), not taken on trust from the overlay:

```
rows                                    285   (152 signal + 133 control)
distinct signal identities              152
distinct control identities              85
control identities used more than once   24   (48 redundant rows, max reuse 6)
identities appearing in BOTH arms        20   (37 control rows)
```

Identity is `(ticker, earnings_date)`, matching the overlay's definition.

Both figures reproduce the overlay exactly. Two distinct defects:

- **Reuse.** 48 control rows are redundant copies of an identity already
  present. In a pooled regression they inflate the control arm's apparent size
  and weight those identities several times over.
- **Cross-arm overlap.** 20 identities carry **both** labels. The same event,
  with the same outcome value, appears once as treated and once as control. This
  is not merely correlated observations — it is a contradiction in the treatment
  indicator the regression estimates a coefficient on.

## 3. The corrected sample — the rule, fixed here

1. **Keep every signal row.** All 152 are distinct identities with no reuse and
   no self-match possible. The overlay lists the treated arm as UNAFFECTED.
2. **Drop control rows whose identity also appears in the signal arm.** These
   identities satisfy the z ≥ 5.0 STRONG-tier rule — that is *why* they are
   signal events — so the signal label is the correct one and the control label
   is the defect. Removes 37 rows.
3. **Keep each remaining control identity exactly once.** Removes the redundant
   copies.

**Resulting sample: 152 signal + 65 control = 217 rows, 28 ticker clusters.**
(85 distinct control identities − 20 that overlap the signal arm = 65.)

**Step 3 needs no tie-break, and this was verified rather than assumed.** All 24
duplicated control identities carry **identical** values across every outcome
column used by any specification — `day_return`, `day_return_ex`, `gap`,
`open_to_close`, `post_1_3`, `post_1_3_ex`, `pre_drift`, `zscore`. Deduplication
is therefore exact-duplicate removal, and which copy survives cannot change any
result. Order is `(ticker, earnings_date, pair_id)` for reproducibility only.

**No outcome value enters any of the three rules.** Membership is decided by
identity and role alone.

## 4. What is recomputed, and what must not change

**All four `AFFECTED` clustered specifications are recomputed, not only the two
the manuscript cites.** Recomputing the cited pair alone would let the choice of
which results to correct depend on which results are inconvenient.

| specification | outcome column |
|---|---|
| `primary_magnitude_abs_day_return` | `abs(day_return)` |
| `magnitude_abs_excess_vs_spy` | `abs(day_return_ex)` |
| `strategy_E_incremental_high_gst` | `sign(gap) × post_1_3_ex` |
| `strategy_B_incremental_high_gst` | `sign(gap) × open_to_close` |

**The estimator is unchanged, so the comparison is like-for-like.**
`tools/run_retrospective_market_response_decomposition.py::cr2_fe` is reused
**unmodified**: `y ~ high_gst + ticker fixed effects` (first level absorbed),
CR2/BRL from `tools/hyp01_inference_feasibility.py::cr_vcov`, clustered on
`ticker`, coefficient-specific Satterthwaite df, coefficient scaled ×100 to
percentage points, two-sided p.

Anything that would change the estimator, the outcome definitions, the cluster
unit, or the fixed-effect structure is **out of scope**. The only thing that
moves is which rows are in the sample.

## 5. Run-once discipline

The recompute runs **once**. Every one of the four results is reported with its
before and after values side by side, including any that move against the
manuscript's argument — specifically including the possibility that the
incremental null at `p = 0.98332` ceases to be null, or that the primary
magnitude coefficient crosses or fails to cross any threshold.

No specification is added, dropped, or re-run after seeing output. If the
corrected sample produces a result that looks wrong, that is recorded as a
finding, not repaired by changing this design.

## 6. What this does not do

It does not re-match anything. Like the 2026-08-22 correction, it is a
**restriction of an existing sample, not a re-pairing**, and the surviving
control arm is therefore a non-random subset — controls that were reused or that
double as signal events are systematically removed. That limitation is inherited
and must be stated wherever the corrected numbers are cited.

It does not touch the 73-pair matched result, the treated-arm-only statistics,
the strategy scorecard's own trade figures, or the magnitude forecast. The
overlay lists all of those as UNAFFECTED or out of lineage.

It confirms no hypothesis, moves no gate, and produces nothing prospective.
Everything it computes is `RETROSPECTIVE_DEVELOPMENT_ONLY` as defined in the
citation policy: computed on a reconstruction carrying a **failed**
point-in-time validity check.

---

*No corrected value exists at the time of writing. Every display gate remains
CLOSED and every eligible-event count remains zero.*
