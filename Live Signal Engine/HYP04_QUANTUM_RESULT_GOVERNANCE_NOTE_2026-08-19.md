# HYP-04 — why quantum-derived results are blocked in code

**Written:** 2026-08-19
**Scope:** the `hyp04_supply_chain_hedge` package's result-display and Stage 1 controls.
**Status:** safeguard landed. Nothing about HYP-04's own standing changed — the
five-condition display gate is still CLOSED on all five grounds.

---

## 1. What happened

A teammate independently built and ran a quantum machine-learning pipeline — a
variational circuit with real-device noise simulation — against what appears to
be real anchor/event/neighbour panel data, and reported a result: an
information coefficient.

Three facts about that, stated plainly because they are the whole reason this
note exists:

- **It is not in this repository.** It is the teammate's own separate codebase,
  sent directly to the repo owner. Not a PR, not a branch, not a file here. An
  audit of every branch and the full commit history confirms nothing matching
  it has ever been present.
- **It was produced outside every process this project uses to decide whether a
  number means anything.** No analysis lock, no cross-validation, no placebo
  test, no preregistered threshold, no freeze.
- **No action was taken on the pipeline itself, and none is proposed here.**
  Someone exploring a method on their own machine is not a governance problem.

## 2. The actual gap

The problem is not that result. It is that **nothing in this repository would
have stopped it.**

The five-condition display gate (`display_gate.py`) governs the *state of the
hypothesis*: registry status, eligible event count, a frozen event set, every
`PENDING_SEPARATE_ANALYSIS_LOCK` decision resolved, and a real linkage map. All
five are properties of the sample and the process. **Not one of them says
anything about how a number was computed.**

So the gate as built implicitly assumed that whatever it was gating came out of
this project's own classical pipeline. That assumption held only by accident —
by there being no other pipeline. The moment a number arrives from somewhere
else, the gate has no opinion about it, and the day the gate opens it has no
opinion about it *and* no objection.

That is the general case, and it is why this is worth fixing rather than
shrugging off:

- it recurs whenever anyone runs any unvalidated method against this data,
  quantum or otherwise;
- it is worse, not better, once HYP-04 is in good standing, because an open
  gate would then be the only thing anyone checked;
- the plan already had the right rule, and the rule was **prose**. Prose does
  not stop a number.

The plan's rule, on the quantum autocorrelation function — stated in v0.1
section 3 and carried into `HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md`
section 3.6, which is the authoritative plan as of 2026-08-19:

> …matching this project's own existing pattern of cross-validating novel
> statistical machinery against a trusted reference before it's allowed to
> influence anything (see `tools/hyp01_r_reference/`), it should not be
> permitted to affect any lock, gate, or hedge decision until it's been
> validated against the classical result on known cases.

Build prompt v10 line 77 scopes it the same way: tertiary, experimental,
isolated, non-load-bearing, "never feeds into any decision or conclusion."

## 3. The fix

`hyp04_supply_chain_hedge/quantum_provenance.py` — a second control, deliberately
**not** folded into the five-condition gate, because it answers a different
question and must survive that gate opening.

| | five-condition gate | quantum-provenance control |
|---|---|---|
| asks | is the hypothesis in a state that licenses a finding? | may *this number*, computed *this way*, be used? |
| opens when | all five conditions hold | a complete classical-validation attestation exists |
| governs | display of findings | display **and** the Stage 1 Link-Strength score |

Both must pass. Clearing the provenance control does not open the gate; opening
the gate does not clear the provenance control.

**What is blocked.** Any quantum-derived model output, from every finding panel
and from the Stage 1 Link-Strength score and anything feeding it — a feature, a
weight, a prior, a selection criterion, a post-hoc adjustment.

**Regardless of source.** This project's own tertiary quantum cross-check module
and an externally supplied result are refused identically and for identical
reasons. Being produced here is not a privilege; being produced elsewhere and
merely reported is not an exemption.

**Regardless of gate state.** It is refused through an open gate, which is the
case the five conditions could never have covered.

**Unless validated**, which means a complete attestation: the classical
reference result named; the known cases enumerated; a dated
agreement/disagreement log that resolves to a readable file in this repository;
and a statement that the validation preceded the use. Every field defaults to
the denying value, each missing field denies on its own, and an undeclared
method family denies unconditionally — you cannot validate what you have not
identified. Requiring the agreement log to be a real, readable, in-repo file is
specifically what stops an outside supplier from self-attesting.

Wired at three chokepoints, none of which reimplements the logic locally:
`display_gate.assert_display_allowed`, `stage2.select_hedge_structure`, and
`inference.leave_one_anchor_out_cv`.

One deliberate consequence: **once the gate opens, a findings panel with no
declared provenance will not render.** It raises. An unattributed figure should
stop the page rather than appear on it.

Stage 2 raises rather than returning `NO_POSITION` when handed an unvalidated
quantum score. Declining to act *because of what the number said* is still the
number affecting the decision, which is precisely what the plan forbids.

## 4. Tests

`test_hyp04_supply_chain_hedge_quantum_provenance.py`, following the display
gate suite's split pattern, because one-directional tests are satisfiable by
degenerate implementations:

- a control hardcoded to **DENY** would pass every "must be blocked" test — so
  test_5 supplies a complete synthetic attestation and asserts it *is*
  permitted;
- a control hardcoded to **PERMIT** would pass test_5 — so test_4 falsifies each
  attestation field individually, every other field held true, and each must
  deny on its own.

The scenario that prompted this is test_2 directly: an externally supplied
quantum result fed into every finding panel with no validation flag set,
asserted rejected through a closed gate *and* through a synthetically opened
one, with a classical control proving the panel is not simply refusing
everything.

Test_10 closes the hole a runtime check cannot see. The control keys on a
*declared* provenance, so an undeclared quantum number is not detectable at
runtime — by this or any other function. What is checkable is that no quantum
computation exists here to be undeclared: no module in the package imports any
quantum computing library, none is a declared dependency, and the control is
imported by all three modules it governs. If that ever changes, the test fails
and forces the new code through the declared API. Same device CI uses when it
greps for live-runner filenames.

## 5. What this note does not say

- **It does not say any quantum result is validated.** None is — not the
  teammate's, not one of ours. No validation has been run, no agreement log is
  on file, and none is claimed. `quantum_provenance.NO_QUANTUM_RESULT_IS_VALIDATED`
  states this in code and test_1 asserts it. The validated code path is a
  mechanism, not evidence that anything has ever travelled down it.
- **It does not say a real linkage map exists.** It does not. Phase 1 remains
  blocked on it; the curated ingestion path is built and tested with zero rows
  curated.
- **It does not report, reproduce, or evaluate the teammate's number**, and
  makes no claim about whether it is right or wrong. That question is untouched
  and is not what this safeguard is about.
- **It does not change the quantum autocorrelation function's scope.** Still
  tertiary, still non-load-bearing, still out of scope for "done", still skipped
  because no citable construction exists for applying the physics construct to
  classical return series. This note governs what would happen *if* such a
  result ever appeared, from any source.

## 6. Files

| File | Change |
|---|---|
| `hyp04_supply_chain_hedge/quantum_provenance.py` | new — the control |
| `hyp04_supply_chain_hedge/display_gate.py` | routes every panel through it first |
| `hyp04_supply_chain_hedge/stage2.py` | `Stage1Score.link_strength_provenance`; checked before rule R1 |
| `hyp04_supply_chain_hedge/inference.py` | `leave_one_anchor_out_cv(feature_provenance=…)` |
| `hyp04_supply_chain_hedge/dashboard.py` | forwards provenance; renders the control's state |
| `test_hyp04_supply_chain_hedge_quantum_provenance.py` | new — the suite above |
| `test_hyp04_supply_chain_hedge_display_gate.py` | test_9d declares provenance, now required through an open gate |
