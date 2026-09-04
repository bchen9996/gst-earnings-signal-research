# GST Prospective Hypothesis Registry — v1.11 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11.json)
**Authored:** 2026-09-02 · **Decisions taken:** 2026-09-02 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json` (sha256 `d960190c8202a55b…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version records a DATA SOURCE, not a specification and not a result.**
> No hypothesis is reclassified, the 193-anchor-event threshold is unchanged,
> the anchor universe is byte-identical, every eligible-event counter stays
> zero, and the display gate stays **CLOSED, C4 MET, four denials**.
> **Nothing has been measured.**

---

## 1. What this version is for

Since v1.5, `peer_price_data_policy` has permitted a survivors-only peer price
source **"only if the restriction and its bias are stated in the registry
version that does it."** For six registry versions nobody took that option, and
each generator carried an explicit refusal against touching the policy.

The option has now been taken: 13,056 sessions collected for six peers from
Yahoo, which lists companies that trade today. **v1.11 is the version that
states it**, and `no_option_taken_here` becomes `false`.

## 2. Why it lands exactly here

**It could not have come earlier.** `code_disagreements()` refuses to declare a
source that has produced nothing, so the collection had to happen first. A
registry that named a price source before any price existed would be describing
an intention.

**It must not come later.** The policy bars a survivors-only restriction from
reaching a *measurement* unstated, and the next step wires these prices into
`target.py`. This version sits in the only window where it is both possible and
honest.

## 3. What was collected

| peer | sessions | window |
|---|---|---|
| CSCO | 3716 | 2003-08-20 → 2025-10-23 |
| CVS | 2200 | 2013-04-09 → 2026-06-08 |
| AAPL | 2142 | 2012-11-20 → 2025-10-23 |
| BB | 1974 | 2013-11-18 → 2025-10-23 |
| MSFT | 1764 | 2004-04-07 → 2021-03-25 |
| HPQ | 1260 | 2017-03-29 → 2025-03-03 |

**13,056 of 13,056 requested sessions filled. Zero missing, zero rejected.**
313 of 314 pairs covered; **215 anchor events carry a covered peer** against a
registered floor of 193.

The one shortfall is CVS on MCK-2026-08-05, whose 20-session horizon runs past
the collection date — a right-edge truncation, not a data gap.

**215 is an AVAILABILITY count, not an eligibility count.** It does not move C2,
and no pair has passed `pair_eligibility`. The registry says so in the same
block, because this is precisely the number most likely to be misread.

## 4. The adjustment basis, and why it is registered at all

Collected on `split_and_dividend (yfinance auto_adjust=True)`.

**Splits must be adjusted** — an unadjusted 2-for-1 prints roughly −69% on a
quiet day, and the target's RVar is a sum of squares, so one such day can
dominate a 41-session window. That half is a correctness requirement.

**The dividend half is a judgement call, and it changes the target.** The two
series are genuinely different, and the difference is not negligible for a
variance measure over a window containing an ex-dividend date. `run_peer_closes_fetch`
has printed a warning on every run saying the choice was registered nowhere.
It is registered now.

It also matches the anchor side, collected split and dividend adjusted by the
owner's decision of 2026-08-31. Using different bases on the two legs of a
transmission measurement would compare price definitions rather than companies.

## 5. The robustness variant is DECLARED, not available

The split-only series is registered as a robustness variant with
`status: "DECLARED, NOT COLLECTED"` and `derivable_from_the_primary: false`.

That wording is doing real work, and it is deliberately **unlike** v1.10's
day-0-inclusive window variant. That one costs no second collection, because
`closes_requirements.session_span` emits the wider span and the variant is a
slice of data already held. **A split-only price series is not a slice of
anything.** It is a different series and cannot be recovered from the
dividend-adjusted one.

Registering it without saying so would put a robustness check in this registry
that nobody can run. Running it needs its own authorised fetch of the same
13,056 sessions with `--no-dividend-adjust`. A generator guard refuses to write
this version if either field overclaims.

## 6. The bias this imports, stated in the inconvenient direction

```
queue candidates                                      36
  resolved to a ticker                                 8
  unresolvable                                        28   (27 no exact match, 1 ambiguous)
incremental anchor events behind unresolvable names  106
```

Named among the unreachable: **Dell, Ingram Micro, Tech Data, Foot Locker,
Rite Aid.**

**Why this biases toward the hypothesis.** The peers most likely to have
disappeared are those acquired or taken private, and acquisition is frequently
*caused* by the commercial relationship under study. The 106 unreachable events
are therefore **not missing at random with respect to HYP-04**.

**What it does not touch.** All seven curated peers trade today, so the
restriction costs the present 215 events nothing. It bounds *future* curation.
The registry states both, and adds that neither excuses the other: a restriction
that happens to be harmless on today's sample is still a restriction on what
tomorrow's can contain.

A generator guard refuses to write this version unless the exposure is an
**integer**. "Stated" means quantified — a statement of bias needs a number,
and this is the number the policy has been waiting for since v1.5.

## 7. Scope is one field, deliberately

v1.11 does **not** move `status` to `ACTIVE_COLLECTING`. That vocabulary
requires a production capture path with `data_captured` true, and while closes
now exist there is still no module assembling them into the panel the estimator
consumes. Claiming it would declare a path the repository does not have. C1 is a
later version's to move.

`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` is **empty**, and that is a claim
rather than an oversight: `peer_price_data_policy` is a **top-level** field, not
one of `IMMOVABLE_HYP04_FIELDS`, which are entry fields. So the entry-level
guard runs unweakened over every field it covers while the top-level policy is
amended.

## 8. The generator refuses to outrun the code

`code_disagreements()` checks that the repository already implements what v1.11
declares: the six files exist and total exactly 13,056 rows, every panel loads
clean through `peer_returns.load_panel`, the declared basis **is**
`run_peer_closes_fetch.ADJUST_SPLIT_AND_DIVIDEND` rather than a retyped copy of
it, and the survivorship counts are read from the newest ceiling artifact rather
than transcribed.

Every guard has been forced to fail and observed to fire. A guard nobody has
seen fail is not known to work.

## 9. What this does not do

No target value, no `beta_h`, no peer response, no horizon and no direction has
been computed from these prices. Counts of **data availability** are publishable;
measured **properties** are not. The gate is CLOSED, C4 MET, four denials,
eligible event count zero — and collecting closes moves none of that, because
C2 counts *eligible* anchor events and C2 and C3 move together or not at all.

## 10. Still open

- **The panel assembler**, which must consume the per-pair coverage path.
  Measured: per-pair gives 215 events, the per-peer unit gives 161 — below the
  floor — because one uncollectable CVS event marks CVS unavailable for all 54
  of its events.
- **A discrepancy recorded, not resolved.** Under assumed prices, resolving
  through `closes_requirements` gives 216 events with a peer where the ceiling
  artifact gives 215. The two resolve events differently. The post-coverage
  figures agree numerically but are not shown to be the same set.
- **A survivorship-bias-free source** remains the standing preference. v1.11
  takes the option the policy always permitted; it does not retire it.
- **C1**, the freeze machinery, and the peer earnings calendar.

---

*Nothing in this document is evidence about supply-chain transmission. No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.*
