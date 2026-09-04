# Pooled recompute — the corrected numbers, and what they do to the manuscript

**Date:** 2026-09-04
**Design:** [`GST_POOLED_RECOMPUTE_DESIGN_v1.0_FROZEN_2026-09-04.md`](GST_POOLED_RECOMPUTE_DESIGN_v1.0_FROZEN_2026-09-04.md), frozen before any value below existed
**Artifact:** [`GST_POOLED_RECOMPUTE_RESULTS_2026-09-04.json`](GST_POOLED_RECOMPUTE_RESULTS_2026-09-04.json)
**Status:** `RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms no hypothesis, moves no gate.

---

## 1. The numbers

Corrected sample: **217 rows** (152 signal + 65 control), 28 ticker clusters,
down from 285. Estimator reused **unmodified** — only the sample changed.

| specification | before (n=285) | after (n=217) |
|---|---|---|
| `primary_magnitude_abs_day_return` | +1.509 pp, p = **0.0662** | **+2.720 pp, p = 0.00031** |
| `magnitude_abs_excess_vs_spy` | +1.539 pp, p = 0.03707 | +2.668 pp, p = 0.00036 |
| `strategy_E_incremental_high_gst` | +0.013 pp, p = **0.98332** | **+0.767 pp, p = 0.16525** |
| `strategy_B_incremental_high_gst` | −0.344 pp, p = 0.46577 | −0.184 pp, p = 0.73137 |

Satterthwaite df rises 16.301 → 18.510; clusters stay at 28.

## 2. The direction was predictable, and that is why the design was frozen first

**This correction helps the manuscript's association claim.** It roughly doubles
the primary coefficient and takes it from a confidence interval spanning zero to
p = 0.0003. A correction that flatters the result deserves more suspicion than
one that hurts it, so the mechanism is stated plainly.

37 of the 133 control rows were events that **meet the z ≥ 5.0 signal rule** —
they appear in the signal arm too. A control arm salted with high-attention
events understates any true contrast between high and low attention. Removing
them cannot do anything but widen the measured gap. The direction was therefore
determined by the nature of the defect, not discovered in the output.

What protects the number is that the rule was fixed in advance:
`GST_POOLED_RECOMPUTE_DESIGN_v1.0_FROZEN_2026-09-04.md` §3 specifies the three
membership rules, states that **no outcome value enters any of them**, and
commits to reporting all four specifications including any that move against the
argument. Two did move against it — §4 below.

## 3. What the manuscript must now say

Every number the abstract cites from this family changes.

- **"a 1.51-percentage-point coefficient (p = .066) with a confidence interval
  spanning zero"** → **+2.72 pp, p = 0.0003, CI well clear of zero.** The
  hedge is no longer accurate, and it errs conservative: the paper currently
  understates its own association result.
- **"attention contributed 0.013 percentage points (p = .98)"** → **+0.77 pp,
  p = 0.17.** *Still null*, but the rhetorical force of "0.013 pp" was an
  artifact of the contaminated sample. "Not distinguishable from zero at
  p = 0.17" is a much weaker sentence than "0.013 pp, p = .98", and the paper
  must use the weaker one.
- **"across all 285 usable events"** → **217 events.** The 285 figure remains
  correct as a description of the *usable population*, not of this regression.

**The three-claim thesis survives, and is arguably better supported.** The
association leg is now strong rather than marginal; the incremental-prediction
leg is still null; tradability is untouched — `0.8543%` per event is a
treated-arm-only statistic the overlay lists as UNAFFECTED. A paper arguing that
association, prediction and tradability are separate claims is *helped* by an
association that is unambiguous and a prediction null that survives it.

## 4. What moved against the argument, reported because it did

- **`strategy_E`'s null weakened.** The coefficient moved from 0.013 pp to
  0.767 pp — sixty times larger, and no longer a number that can be described as
  indistinguishable from nothing on inspection. It remains non-significant, and
  it must now be argued rather than displayed.
- **`strategy_B` lost what little it had**, −0.344 pp → −0.184 pp at p = 0.73.

## 5. Limitations, inherited and stated

**This is a restriction, not a re-match.** Like the 2026-08-22 correction, a
control that was reused or that doubles as a signal event is *dropped*, never
re-paired. The surviving control arm is a **non-random subset** — 65 of 85
identities — and the events removed are systematically those that were
contested or attention-heavy. That is the same limitation the overlay states
about its own 73-pair result, and it applies here in full.

**The point-in-time check is still failed.** Nothing here makes any of this
prospective, preregistered, or confirmatory. All of it is
`RETROSPECTIVE_DEVELOPMENT_ONLY` as defined in
`GST_RETROSPECTIVE_CITATION_POLICY_v1.0_2026-09-04.md`.

**Two things this does not touch.** The 73-pair matched result
(+2.0797 pp, p = 0.00397) is a different estimand on a different sample and is
unchanged. The magnitude-forecast numbers (MAE 3.6299 vs 3.6284) are out of this
lineage entirely.

## 6. Citation status after this document

Under `GST_RETROSPECTIVE_CITATION_POLICY_v1.0_2026-09-04.md` Rule 3b, the label
is cleared by computing the corrected value and reporting it. That has now
happened for all four:

| specification | status |
|---|---|
| all four `AFFECTED` pooled specifications | `SUPERSEDED` by this artifact |
| the corrected values in `GST_POOLED_RECOMPUTE_RESULTS_2026-09-04.json` | `CURRENT` |

Rule 3c requires that the correction's own numbers travel with it: any external
document citing a corrected value states what changed, in which direction, and
what was lost. §1 through §5 are that statement.

---

*No prospective outcome was used. Every display gate remains CLOSED and every
eligible-event count remains zero. Nothing here is investment advice or a
representation that any approach is profitable.*
