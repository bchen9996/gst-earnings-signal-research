# Overnight goal

**Edit this file to steer the night. The runner reads it first.**

## Current goal

Close the remaining open items from `PREREGISTRATION_GAP_AUDIT_v1.0.md` and the
D7/D8 conformance work, without opening any display gate and without pushing.

In scope:

- **D7 interval representation.** The signed lock requires onset be *reported*
  as the interval `[onset - 2, onset]`, never as a point estimate. No interval
  type exists anywhere: `onset_horizon` is a scalar `int` on both `Stage1Score`
  and `LocalProjectionResult`. D8's arithmetic was fixed on 2026-09-04; D7's
  reporting requirement is still unimplemented.
- **The `onset - 2` floor.** No artifact specifies a floor, so `onset = 1`
  yields `-1`. The tenor path is unaffected (`(1-2)+5 = 4`), but the interval's
  lower bound is not. This likely needs a human decision — see the note below.
**Corrected 2026-09-04, after reading the audit rather than the IDs.** The
first draft of this file listed gap-audit items A9, C9, E3, E8, F2, F3, F4 and
F5 as overnight work. **That was wrong, and they are now out of scope.** Every
one of the eight is classified `SCIENTIFIC_DECISION`, and the audit is explicit
about what that forbids:

> Code is an implementation of a decision, never the place a decision gets
> made.

> Three of these — C6, C7 and E3 — could each change whether HYP-01 is reported
> as significant. That is why they must be resolved by **a qualified human, in
> a dated lock**, before any prospective observation, and never after seeing
> data.

An unattended loop cannot make any of them. Under `CLAUDE_OVERNIGHT.md` rule 3
it would have to write `BLOCKED.md` on the first one it reached and stop, so
pointing the night at them wastes the night. They are listed below as human
work, not loop work.
- **The 7.97 / 7.28 attribution fix** in
  `Live Signal Engine/GST_RETROSPECTIVE_CITATION_POLICY_v1.0_2026-09-04.md`
  §5. It introduces `7.97` inside a clause beginning "among the 73 survivors",
  which reads as though 7.97 were the survivors' median treated z. It is not:
  7.97 is the median across all 152 signal events; the survivors' median is
  **7.28**. Both are real and the substantive claim (max control z = 14.60
  exceeds both) holds either way, but the attribution must say which population
  it means. That file is committed and pushed, so correct it in a new dated
  note or an explicit amendment line — do not silently rewrite history.

Out of scope tonight:

- Anything requiring a network fetch or a live runner.
- Anything that would move a display gate.
- Any push, to any remote.
- The manuscript repo entirely — it is a different checkout with a different
  remote and its own pending decisions.

## Decisions only a qualified human can make

None of these is loop work. Listed so the next session can see the shape of
what is actually outstanding.

**On the preregistration critical path** — the audit states a study "cannot
call itself preregistered while its primary estimator and inference procedure
are still open", and named C6, C7, E3 and E8. **C6 and C7 were discharged
2026-09-04**, so the blocking set is now:

| # | Decision | Deadline |
|---|---|---|
| **E3** | Multiplicity treatment across hypothesis families | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |
| **E8** | Written boundary between development material and the confirmatory cohort | `BEFORE_PREREG_AND_FIRST_OBSERVATION` |

**E3 is now the only remaining open decision the audit says could change
whether HYP-01 is reported as significant.** Of the three it named, two are
resolved. That makes E3 the highest-value item in the project right now, and it
is a decision, not an implementation.

E8 carries its own warning worth reading before starting it: writing the
boundary down "may reveal that a past choice was informed by data now inside
the cohort."

**Not on the critical path:** A9 (design sensitivity — note the outcome-free
MDE work already in `gate.py` is the permitted form; project-derived power
calculations are prohibited), C9 (`BEFORE_SECONDARY_ANALYSIS`), F5 (construct
validity, `BEFORE_FIRST_OBSERVATION`), and F2/F3/F4, which are gated on HYP-02
and HYP-03 activation and are not needed yet.

**Already settled, recorded so it is not re-litigated:** the `onset - 2` floor
was decided 2026-09-04 — floor the reported interval, keep D8's tenor
arithmetic literal. See `hyp04_supply_chain_hedge/onset.py`.
