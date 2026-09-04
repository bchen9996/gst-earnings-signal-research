# Plan

Written 2026-09-04. Each item is one build pass: small enough to implement and
verify in a single turn, with the verification command stated so the pass
cannot check itself off on a feeling.

`VENV=./.venv/Scripts/python.exe` throughout.

---

## Standing check after every build pass that touches HYP-04 code

```bash
$VENV -c "from hyp04_supply_chain_hedge.display_gate import evaluate_gate; d=evaluate_gate(); c=d.conditions; print('CLOSED', d.open is False, '| C4', c['C4_decisions_resolved'], '| denials', len(d.denials), '| eligible', d.evidence.get('eligible_event_count'))"
```

Expected: `CLOSED True | C4 True | denials 4 | eligible None`.
Anything else: stop, write `BLOCKED.md`.

*Corrected 2026-09-04 against the real API. The first draft of this snippet
was written from memory and named `evaluate_display_gate`, `r.status`, `r.c4`
and `r.eligible_count`, none of which exist. The entry point is
`evaluate_gate()`; C4 is read from the `conditions` dict, and the four denials
are C1, C2, C3 and C5 — C4 is the one condition that passes.*

---

## Items

- [ ] **1. Correct the 7.97/7.28 attribution.**
  `GST_RETROSPECTIVE_CITATION_POLICY_v1.0_2026-09-04.md` §5 implies 7.97 is the
  median treated z among the 73 survivors. It is the median across all 152
  signal events; the survivors' median is 7.28. The file is already pushed, so
  append a dated correction note rather than rewriting the sentence in place.
  *Verify:* `grep -n "7.28" "Live Signal Engine/GST_RETROSPECTIVE_CITATION_POLICY_v1.0_2026-09-04.md"`
  returns a line, and the note states which population each median describes.

- [ ] **2. Re-derive both medians independently before writing item 1.**
  Do not copy 7.28 from this plan. Recompute from
  `Live Signal Engine/retrospective_event_components.csv` and from the E1/E2
  replay in the manuscript repo's matching tool logic.
  *Verify:* the recomputed pair is (7.97 over 152 signal rows, 7.28 over the 73
  surviving treated). If either differs, that is the finding — record it and
  stop.

- [x] **3. Read the gap audit and expand the eight open items.** Done, and the
  result is that **they do not belong in this plan at all.** Every one is
  classified `SCIENTIFIC_DECISION`. `PREREGISTRATION_GAP_AUDIT_v1.0.md` is
  explicit: *"Code is an implementation of a decision, never the place a
  decision gets made"*, and the three that could change whether HYP-01 reads as
  significant *"must be resolved by a qualified human, in a dated lock."*

  Moved to `TASK.md` under "Decisions only a qualified human can make", with
  one finding worth surfacing: **C6 and C7 were discharged on 2026-09-04, so
  E3 is now the only remaining open decision the audit says could change
  whether HYP-01 is reported as significant.** That makes it the
  highest-value item in the project — and it is not something this plan, or an
  overnight loop, can execute.

  *This item also corrected an error in my own `TASK.md`*, which had listed all
  eight as overnight work. Under `CLAUDE_OVERNIGHT.md` rule 3 the loop would
  have written `BLOCKED.md` on the first one and stopped.

- [x] **4. Decide the `onset - 2` floor.** *(Had to come first — the interval
  cannot be built without it.)* **Decided 2026-09-04: floor the REPORT, keep
  D8's tenor arithmetic literal.** The reported lower bound clamps to
  `min(HORIZON_GRID)`; `_tenor_from_onset` still computes on the raw
  `onset - 2`, so tenor is unchanged at every onset. The two diverge only at
  onset in {1, 2}, and the divergence is self-reporting.

- [x] **5. Add an `OnsetInterval` type expressing D7's requirement.**
  `hyp04_supply_chain_hedge/onset.py`: frozen dataclass, `__str__` renders
  `[lower_floored, point]`, `lower_raw` always reported beside it on the
  `icc_raw`/`icc_floored` precedent from `gate.py`. Every guard raises
  `RefusedError`, never `assert`.
  *Verified:* tests 17a–17n, all passing.

- [x] **6. Wire it into `Stage1Score` and `LocalProjectionResult`.** Added as
  a derived `onset_interval` property on both — additive, the scalar
  `onset_horizon` stays. **Stage 2's `inputs` dict no longer carries a bare
  `onset_horizon` point estimate**; that serialisation was the live D7
  violation. Test 17g asserts the bare key is gone.
  *Verified:* inference/gate/stage-2, smoke, quantum-provenance and
  display-gate suites all exit 0; gate CLOSED, C4 MET, 4 denials, eligible
  None; no registry file appears in `git diff --name-only`.

- [ ] **7. Commit items 4–6.** Explicit paths only:
  `constants.py`, `onset.py`, `inference.py`, `stage2.py`,
  `test_hyp04_supply_chain_hedge_inference.py`. Do **not** sweep the untracked
  runner scaffolding (`PLAN.md`, `TASK.md`, `CLAUDE_OVERNIGHT.md`,
  `tools/overnight_runner.sh`) into the same commit — different concern.
  *Verify:* `git show --stat HEAD` lists exactly those five files.

- [ ] **8. D7 has a second half still unimplemented.** The interval now exists
  and Stage 2 reports it, but `LocalProjectionResult` is not the only reporting
  surface — check `dashboard.py` and `artifacts.py` for any path that renders
  or serialises `onset_horizon` as a bare scalar.
  *Verify:* `grep -rn "onset_horizon" hyp04_supply_chain_hedge/` shows only
  the dataclass fields, the display-gate panel identifier, the `R3` rule name,
  and the interval's own construction.

---

## Notes for the next planning pass

- Item 3 gates items beyond it: the eight audit items cannot be sequenced until
  their text is read.
- Items 4 and 5 are deliberately split. A type with no callers is verifiable on
  its own; wiring it in is where the blast radius lives.
- If item 5's suite run is slow, run the three suites that import `stage2`
  first (inference, smoke, quantum-provenance) and the full 40-file batch after.
