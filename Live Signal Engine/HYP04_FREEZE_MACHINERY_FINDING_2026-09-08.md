# HYP-04 freeze machinery — built, and shipped unexecuted

**Date:** 2026-09-08
**Status:** the tool exists. No freeze has been made, and this module cannot make one.

---

## 1. What a freeze would do, said first

The display gate denies on four conditions today. A valid freeze record
supplies **C3** directly, carries the count that satisfies **C2**, and clears
**C5** — the panel already derives `uses_placeholder_linkage: false` from the
real curated map. **C4** has been MET since registry v1.2.

> **A completed freeze would take the display gate from four denials to one.**
> The survivor is **C1**: `status` is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`,
> not `ACTIVE_COLLECTING`, and moving it is a registry act requiring a v1.12.

That is asserted, not argued: `test_5_a_completed_freeze_leaves_exactly_c1`
builds a complete freeze on a fixture and requires `len(denials) == 1` with
`C1_status` false.

Because that is the most consequential single action available in this project,
`hyp04_supply_chain_hedge/make_freeze_draft.py` ships the **tool** and never
performs the **act**.

## 2. The procedure it implements

`GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` §5:

1. enumerate the eligible `event_id` set mechanically, and record it;
2. record the analysis-code commit SHA;
3. record the resolved analysis lock, written *before* this step;
4. hash and append all three, immutably — **then** compute results.

Steps 1–3 are derivable and are derived. Step 4's *"then"* is an ordering the
module can guard but cannot prove.

**A gap this exposed in the panel.** §5 point 1 requires the set to be
*enumerated*, not merely counted, and the panel artifact shipped in `df9a4ed`
recorded only the count. It now enumerates all 214 ids and their anchors,
routed through `linkage_resolution.freeze_record_fields` — the one function
whose job that is — rather than a local comprehension.

## 3. The one field a machine must not fill

`frozen_before_any_result_computed` is **null in every draft**.

No filesystem check can establish that nobody has looked at an outcome; someone
can compute a regression in a notebook that never touches this repository. The
module does scan for result artifacts, but that scan is a **backstop against
the obvious case, not a proof**, and the draft says so in its own text. Treating
it as proof would be the more dangerous error.

`frozen` also stays `false`. A draft is not a freeze. Both, with
`attested_by` and `attested_date`, are the owner's — the same pattern
`make_linkage_draft` uses for the five linkage fields it refuses to fill.

## 4. It refuses on unratified linkage, and it refuses today

`curated_linkage.REVIEW_STATUSES` is `("draft", "reviewed", "needs revisit")`.
The machinery **refuses while any edge contributing an eligible event is not
`reviewed`**. Run against the real repository right now:

```
6 contributing edge(s) are not 'reviewed':
  INTC->HPQ (needs revisit), JBL->AAPL (draft), JBL->BB (draft),
  JBL->CSCO (draft), MCK->CVS (draft), NVDA->MSFT (draft)
```

**That refusal is the feature, not a defect.** The frozen set is never
retroactively changed, so freezing over an edge the owner flagged
`needs revisit` at low date confidence would make questionable linkage
permanent. `PKG→ODP` is correctly absent: PKG has no eligible events, so it
contributes nothing to freeze.

## 5. Everything else it checks

Each has its own refusal, and each was forced to fire and observed:

| refusal | why it matters |
|---|---|
| a contributing edge is not `reviewed` | §4 above |
| the event panel is missing | C3 freezes the set C2 counted; it cannot invent one |
| the curated map's hash has moved since the panel | a freeze must name the exact map it froze |
| the working tree is dirty | a sha that does not describe the tree names code that is not the code that ran |
| the analysis lock is missing or unsigned | C3 requires a dated lock |
| the lock is signed **on or after** the freeze date | equal is not *before*; same-day ordering cannot be established from a date |
| the derived count is below the floor | a freeze records a sample that cleared its floor |
| `uses_placeholder_linkage` is true | C5 bars it at any event count |
| a freeze already exists for the date | append-only; a second freeze makes the first unfalsifiable |
| a result artifact already exists | §5 orders the freeze first |

**Two of these were passing against the wrong guard on first run.** The
unsigned-lock and missing-lock tests mutated the fixture's lock file, which
dirtied its git tree, so the dirty-tree refusal fired and both tests "passed"
without exercising what they named. The fixture now commits after each
mutation. This is the second instance of that failure mode in two days — the
first was a `filled == 0` check in the panel assembler that could never run —
and both were found only by reading the refusal message rather than the
pass/fail.

## 6. The validator

`validate_freeze(path)` reads a *filled-in* draft and builds a
`display_gate.FreezeRecord`. It refuses an unset `frozen`, a null attestation,
a blank attributor, a duplicated event id, declared placeholder linkage, a
missing sha or lock — and, given the panel, refuses if the event-id set was
edited away from what the panel says. **An operator may supply the attestation
and nothing else.**

## 7. What this does not do

No freeze exists. `git status` after this work shows no
`HYP04_FREEZE_DRAFT_*.json`, and the display gate is **CLOSED, C4 MET, four
denials, eligible count unset** — asserted by `test_8_the_real_gate_is_untouched`.

Three things stand between here and a Phase 0 exit, and none of them is mine:

- **Ratify the curated map.** Six contributing edges are `draft` or
  `needs revisit`. `INTC→HPQ` was flagged for re-examination at low date
  confidence for a reason.
- **Attest and freeze.** The count is 214 against a floor of 193. The
  attestation is a claim about what you have and have not looked at.
- **Registry v1.12.** Moving `status` to `ACTIVE_COLLECTING` is what would open
  the gate once a freeze exists.

---

*Nothing in this document is evidence about supply-chain transmission. No target
value, `beta_h`, peer response, horizon or direction has been computed for
HYP-04, and none may be displayed while the gate is closed.*

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable.*
