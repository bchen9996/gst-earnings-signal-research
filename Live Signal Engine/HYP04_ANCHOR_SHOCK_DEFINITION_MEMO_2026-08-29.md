# HYP-04 — what is the anchor-side shock?

**Dated 2026-08-29. A design memo. It resolves nothing by itself** — no registry
field moves on the strength of this document, and no measurement is authorized
by it.

**Nothing here is evidence about supply-chain transmission.** No result,
direction, effect estimate, plot, p-value or confidence interval exists for
HYP-04, and none may be displayed while the display gate is closed.

---

## 0. A disclosure about the order this was written in

The author already knew, before writing this, what each answer would imply for
the number of usable anchor events. That cannot be un-known, so it is disclosed
rather than concealed, and the memo is written under two self-imposed rules:

1. **No event count, horizon, or feasibility figure appears anywhere below.**
2. The argument is made from the hypothesis's own text, the model plan, and the
   estimator's code — sources that all predate today.

The reader should judge §4 on its own terms. If the argument only persuades
once the counts are on the table, it has failed and should be rejected. The
ordering was chosen precisely *because* the author knew the arithmetic: a
conclusion reached in the other order would be uninterpretable.

## 1. The question

HYP-04's estimator regresses peer abnormal volatility at horizon *h* on a
per-anchor-event scalar called `shock`:

```
_design_matrix -> [ intercept , shock , days_to_peer_earnings ]
```

**What is `shock`, in production?**

This is not a question invented today. It has never been answered.

## 2. What the code establishes

| Fact | Evidence |
|---|---|
| No HYP-04 module reads attention data at any point | `gst_zscore` appears in **zero** files under `hyp04_supply_chain_hedge/` |
| The target is entirely peer-side | `raw_log_ratio_target(peer_returns, anchor_day, horizon)` — the anchor contributes a **date**, nothing else |
| `shock` is the *only* anchor-side quantity in the model | `_design_matrix`, column 1 |
| `shock` has **no production definition** | It exists only in `fixtures.py` as `abs(rng.normal(0.0, 1.0))` — a synthetic magnitude |
| It is constant within an anchor event | one value per event, shared across that event's peers (`inference.py`, permutation unit) |

So the anchor side of this hypothesis is, today, a single undefined scalar.

## 3. What the record already says

The model plan (`HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md`, §3.4) lists it
as a candidate feature and offers **two alternatives without choosing**:

> "Anchor shock magnitude (confirmed **|excess return| or GST z-score**, already
> validated in this project)"

The four decisions recorded as `RESOLVED_IN_DATED_ANALYSIS_LOCK` are two-way
clustering, implied-volatility promotion, the lag quantity's uncertainty
treatment, and the ticker-cluster estimator. **None of them is this one.** It is
not in `unresolved_analysis_decisions` either. It is simply absent.

Meanwhile `required_eligibility_class` is `core_attention_vs_equity_response`,
inherited from HYP-01's per-event protocol. That class requires attention data
per anchor event. **It therefore forces the GST branch by side effect, without
anywhere stating that attention *is* the shock.** An eligibility class is
currently standing in for a design decision that was never made.

## 4. The design argument

The two candidates are not two encodings of one hypothesis. They are two
different hypotheses about the mechanism.

**H_info — the anchor's earnings news carries information about the peer's own
business.** A customer reports collapsing demand; the supplier's order book is
implicated. Peer volatility responds, with a lag set by how quickly that
implication is worked out. The natural scale of the shock is *how surprising the
news was*, and the market's own aggregation of that is the anchor's earnings-day
**|excess return|**.

**H_attn — the anchor's earnings draws attention, and attention spills along the
link.** Peer volatility responds as investors arrive. The natural scale is the
anchor's **GST z-score**, and the lag is attention-propagation time.

Four things in the existing record point at H_info:

1. **The hypothesis says so.** Its question is "peer volatility transmission and
   lag following anchor **earnings shocks**". The model plan §1 frames Stage 1
   as "given a **confirmed anchor earnings shock**, how much does this specific
   peer's volatility tend to move". Earnings shock, not attention shock.

2. **The stated purpose is hedge selection.** Stage 2 decides whether to put on
   protection for a peer. The production trigger is an anchor earnings release
   and its magnitude. A desk sizing a hedge is reacting to the news, not to
   search volume.

3. **Attention already has a different job in this design, on the other side.**
   §3.4 lists "peer coverage/thinness: search volume, analyst count, news
   volume — a proxy for how likely the market already prices the link" as a
   **peer-side moderator**. Making attention the anchor-side shock as well would
   put the same construct on both sides of one regression carrying two different
   meanings. That is a specification problem, not a richness.

4. **The two are not interchangeable in kind.** An excess return is a *signed
   magnitude of repricing*, aggregated by the market. A search z-score is a
   *count of people looking*. Only the first is a measure of the information
   that could implicate the peer's fundamentals.

**Recommendation: `shock` = the anchor's earnings-day |excess return|, and the
anchor side of HYP-04 does not require attention data.**

## 5. What would overturn this

State it plainly, because it is a live possibility and not a straw man:

**If HYP-04 is intended as a sibling of HYP-01 — a test of *attention* diffusion
along supply-chain links, rather than of information transmission — then the GST
z-score is the shock, the current eligibility class is correct as written, and
§4 is wrong.**

That reading is available. This project is built around search-attention data,
and "lag" is a natural attention story. The question is not which is more
interesting; it is which hypothesis HYP-04 was registered to test. If the answer
is attention diffusion, that should be written into the hypothesis text
explicitly rather than left to be implied by an inherited eligibility class.

**This memo does not decide that.** It establishes that the choice exists, has
never been made, and is currently being made by accident.

## 6. Two consequences that must not be skipped

**6.1 Adopting |excess return| is a registry change, not a code change.**
`required_eligibility_class` would have to state HYP-04's anchor-side
requirement in HYP-04's own terms rather than inheriting HYP-01's. That is a new
dated registry version with its justification written into it. Nothing may be
measured on the strength of this memo.

**6.2 It sharpens an existing specification issue in the target.** The peer's
reference window is `peer_returns[ref_start : anchor_day + 1]` — **inclusive of
day 0**, the anchor's earnings day. If transmission is partly same-day, part of
the response sits in the baseline the response is measured against, deflating
the target. This is true regardless of how `shock` is defined, but it becomes
pointed when the shock is itself the anchor's day-0 move, because whatever
shared factor moves both names on day 0 enters the regressor and the reference
window together.

**This needs its own decision and its own robustness check** — the obvious
candidate being a reference window ending at `anchor_day − 1`, reported
alongside the primary specification rather than replacing it. Recorded here
because it was found while answering the §1 question; it is not resolved here.

## 7. Status

Nothing in the repository changes because this document exists. HYP-04's status
remains `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`, every eligible-event
counter remains zero, and the display gate remains **CLOSED, C4 MET, four
denials**.

---

# AMENDMENT — 2026-08-29 (same day, after the memo was circulated)

**Appended, not merged.** Sections 0–7 above stand as written. This amendment
records the repo owner's decision and corrects one word in §5 that would
otherwise mislead a later reader into the opposite conclusion.

## A1. The decision

**The repo owner determined, 2026-08-29, that HYP-04 tests INFORMATION
TRANSMISSION along supply-chain links** — how an anchor's earnings news
dictates volatility and a range of price changes for stocks in industries
across the supply chain.

**The recommendation in §4 therefore stands: `shock` is the anchor's
earnings-day |excess return|, and HYP-04's anchor side does not require
attention data.**

## A2. "Sibling" — §5 is superseded, and the word was doing two jobs

§5 said the recommendation would be overturned if HYP-04 were "intended as a
sibling of HYP-01". The owner's answer used the same word for a different
thing, and the distinction is the whole decision:

| | |
|---|---|
| **§5's sense** (the overturning condition) | HYP-04 tests the same MECHANISM as HYP-01 — attention diffusion — with supply-chain links as the medium |
| **The owner's sense** (what is actually true) | HYP-04 belongs to the same RESEARCH PROGRAMME and attacks the same central issue **from a different angle than HYP-01** |

HYP-04 is a sibling in the second sense and not the first. Same programme,
different mechanism. **§5's overturning condition is NOT met**, and a later
reader must not read "sibling of HYP-01" in §5 as satisfied by the owner's
answer. It is not.

## A3. Two things found after the memo was written

Both sharpen §3 and neither changes the conclusion.

**A3.1 — The side effect is visible in a single line.**
`pair_eligibility.py`'s P1 check hardcodes `HYPOTHESIS_CORE_ATTENTION_RESPONSE`,
and the denial it raises reads:

> "P1 FAILED: the anchor event is not eligible for
> `core_attention_vs_equity_response`. **The peer measurement is only defined
> relative to a usable anchor earnings shock.**"

The *justification* given is the information-transmission one — a usable
earnings shock. The *thing enforced* is the attention class. The two sit on
adjacent lines. This is §3's claim, in the code, stated by the code itself.

**A3.2 — The inherited class is far heavier than "the shock is well measured".**
`core_pre_event_eligible` requires the STRICT six-field gate, each field backed
by a successful per-leg source status, plus a `pre_event_snapshot_asof_utc`:

    gst_zscore   wiki_zscore   panel_implied_volatility
    realized_volatility   previous_close   volume

So certifying one HYP-04 anchor event currently requires **two attention series
and an option chain**. Under information transmission the anchor-side
requirement is that the earnings-day excess return is well measured. Neither
attention series, nor the option chain, nor a pre-event snapshot bears on that.

This is not an argument that those fields are worthless. It is that they are
HYP-01's requirements, imported wholesale, and never examined against HYP-04's
own question.

## A4. How this gets recorded, and what is deliberately NOT done

**It is recorded at REGISTRY level, not through the analysis-lock mechanism.**
`required_eligibility_class` — this decision's closest sibling — is a plain
registry field, not a locked decision. The four decisions the lock carries
(clustering, IV promotion, lag-quantity uncertainty, ticker-cluster estimator)
are estimator and reporting choices. What the independent variable IS sits
above those, in the hypothesis specification.

**Two things are deliberately not done.** This decision is NOT added to
`unresolved_analysis_decisions`: marking it RESOLVED would have to cite
`GST_HYP04_ANALYSIS_LOCK_v1.0`, which predates the decision and does not
contain it — a false citation — and marking it PENDING would flip C4 for a
decision that is not pending. And no analysis lock is authored here: that
artifact carries an authorizer and a
`no_outcome_inspected_before_signing_attested` attestation, which is the repo
owner's to sign and not this session's to write.

**If the owner wants this decision at lock grade rather than registry grade,
that is an authorization they sign, and it should happen before any
measurement runs.**

## A5. Status is unchanged

Nothing is measured. No capture path runs. HYP-04's status remains
`PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`, every eligible-event counter
remains zero, and the display gate remains **CLOSED, C4 MET, four denials**.
