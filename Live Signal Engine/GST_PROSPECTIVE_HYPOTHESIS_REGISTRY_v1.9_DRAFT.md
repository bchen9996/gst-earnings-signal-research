# GST Prospective Hypothesis Registry — v1.9 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9.json)
**Authored:** 2026-08-29 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.8.json` (sha256 `574baa5dc4b86b73…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version changes the SPECIFICATION, not the corpus.** v1.6, v1.7 and
> v1.8 corrected what the extractor could read and each froze the hypothesis
> specification. v1.9 does the opposite: it states HYP-04's **anchor-side
> requirement** in HYP-04's own terms, and freezes membership. No hypothesis is
> reclassified, the 193-anchor-event threshold is unchanged, every
> eligible-event counter stays zero, and the display gate stays **CLOSED, C4
> MET, four denials**. **Nothing has been measured.**

---

## 1. What was wrong

HYP-04's estimator regresses peer abnormal volatility on a per-event scalar
`shock` — its **only** anchor-side quantity. That scalar had **no production
definition**:

- it existed solely in `fixtures.py` as `abs(rng.normal(0, 1))`
- the model plan offered *"confirmed **|excess return| or GST z-score**"* and
  never chose
- none of the four decisions in the dated analysis lock was this one, and it was
  not in `unresolved_analysis_decisions` either — it was simply **absent**

Meanwhile `required_eligibility_class` inherited HYP-01's
`core_attention_vs_equity_response`, whose strict gate requires `gst_zscore`,
`wiki_zscore`, `panel_implied_volatility`, `realized_volatility`,
`previous_close` and `volume` — each with a successful per-leg source status —
plus a pre-event snapshot.

**So certifying one HYP-04 anchor event required two attention series and an
option chain, and the choice of shock was being made by side effect.**

`pair_eligibility`'s P1 held the contradiction in one place: it enforced the
attention class while the denial it raised justified itself as *"the peer
measurement is only defined relative to a usable anchor **earnings shock**."*
The justification was information transmission; the thing enforced was
attention.

## 2. The decision

**The repo owner determined, 2026-08-29, that HYP-04 tests INFORMATION
TRANSMISSION along supply-chain links** — how an anchor's earnings news dictates
volatility and a range of price changes for stocks in industries across the
supply chain. It is a sibling of HYP-01 in the sense of *the same research
programme approached from a different angle*, **not** in the sense of testing
the same mechanism.

Basis: [`HYP04_ANCHOR_SHOCK_DEFINITION_MEMO_2026-08-29.md`](HYP04_ANCHOR_SHOCK_DEFINITION_MEMO_2026-08-29.md)
and its same-day amendment, both written and committed **before** this version.

## 3. The rule

```
shock = | anchor_return − β · benchmark_return |,     β = 1 vs SPY
```

`HYP04-ANCHOR-SHOCK-RULE-v1`, defined in
`hyp04_supply_chain_hedge/anchor_shock.py`, fail-closed on every unknown:
AS-1…AS-6. The registry **declares it from the rule** rather than paraphrasing
it, and a test re-derives every declared field.

**β is not estimated, and that is the point.** An estimated β needs an
estimation window, and choosing that window after seeing how results move is
after-the-fact tuning. A β fitted on the full sample uses post-event data to
define a pre-event expectation — look-ahead by construction, the same defect
class as the reconstructed GST z-score history this project's central finding is
about. **β = 1 is chosen for being assumption-free, and is recorded as a stated
limitation, not as a claim that the market model is right.**

**No fourth hypothesis class was created.** There is none in
`gst_market_response.completeness.HYPOTHESIS_CLASSES` for this requirement, and
none was added. The rule lives in HYP-04's own package — exactly the precedent
`pair_eligibility` set for the peer side — and HYP-01's confirmatory
infrastructure is untouched. `pair_eligibility` and `linkage_resolution` no
longer import `gst_market_response` at all.

## 4. Exactly one field moved, by name

A version permitted to move a specification field is a version that could move
others. So the exception is **named in the generator's source**, not granted by
loosening a guard:

```python
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE = ("required_eligibility_class",)
```

Every other field of `IMMOVABLE_HYP04_FIELDS` is still checked, and the
**anchor universe is byte-identical to v1.8** — this version is not about
membership. The four analysis decisions are untouched, so C4 is not disturbed by
a specification change.

## 5. The generator refuses to outrun the code

v1.7's companion records the failure mode: the repository holding code
implementing one thing and an authoritative registry describing another, with no
test able to see it.

**v1.9's generator refuses to write while `pair_eligibility` still enforces the
attention class.** The code was changed first and the registry follows, and the
guard makes that ordering compulsory. The suite forces each disagreement and
asserts the refusal fires — *a guard nobody has seen fail is not known to work*.

## 6. Known limitations, stated rather than fixed

- **β = 1 against a broad-market proxy is not a risk model.** A peer whose
  anchor has high market beta will carry part of the market move in its "excess"
  return.
- **The shock is a magnitude.** Direction is discarded — correct for a
  volatility-transmission question, wrong for a signed-return one.
- **OPEN, recorded, NOT resolved here:** the peer target's reference window is
  `peer_returns[ref_start : anchor_day + 1]` — **inclusive of day 0**. If
  transmission is partly same-day, part of the response sits in the baseline it
  is measured against. True however the shock is defined, and sharper when the
  shock is the anchor's own day-0 move. Needs its own decision and a robustness
  check against a window ending at `anchor_day − 1`.

## 7. What this does not do

- **It measures nothing.** A module that *can* compute a shock is not a computed
  shock — the same distinction that has kept HYP-04's status unchanged
  throughout. No anchor shock has been computed from production data.
- **It creates no eligible anchor event.** `minimum_eligible_events` is still
  **193 anchor events** — the unit is deliberately not (anchor × peer) pairs.
  C2 still counts zero.
- **It does not decide feasibility.** Whether enough eligible anchor events can
  exist is a separate question this version does not touch and does not answer.
- **v1.8 remains on disk unchanged**, including the inherited eligibility class
  this version replaces. A superseded version is allowed to be wrong.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
