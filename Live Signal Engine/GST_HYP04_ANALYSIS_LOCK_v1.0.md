# HYP-04 Analysis Lock — v1.0 (SIGNED, IN FORCE)

> **SIGNED 2026-08-20. IN FORCE. AND IT OPENS NOTHING.**
>
> Being in force means the four analysis decisions are settled and may no
> longer be chosen after seeing an outcome. It does not mean a result may be
> displayed. Gate condition C4 reads the **registry**, not this file, so
> signing resolves nothing on its own: registry **v1.2** must additionally be
> authored per **§11** — v1.1 is never edited in place — and the code that pins
> the v1.1 filename must be repointed.
>
> Even after both acts the gate stays **CLOSED**. C4 clears; C1, C2, C3 and C5
> do not. No HYP-04 finding becomes displayable, `method_approved` remains
> false, and the linkage map still does not exist at zero curated rows.

**Drafted:** 2026-08-19 (D1–D10) · **§11 added:** 2026-08-20 · **Signed:** 2026-08-20
**Operative date:** 2026-08-20 (UTC calendar date supplied by the authorizer)
**Authorizer:** Project authorizer / repository owner — see §12
**Hypothesis:** HYP-04 — supply-chain hedge lag (exploratory, registry v1.1)
**Governing plan:** [`HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md`](HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md)
**Authorization record:** [`GST_HYP04_METHOD_AUTHORIZATION_2026-08-20.md`](GST_HYP04_METHOD_AUTHORIZATION_2026-08-20.md)

The machine-readable [`GST_HYP04_ANALYSIS_LOCK_v1.0.json`](GST_HYP04_ANALYSIS_LOCK_v1.0.json)
is the authority and this document is its human companion, mirroring HYP-01's
convention. Where the two are read together and disagree, the JSON governs.

---

## 1. What this lock is, and what it is not

**It is** the dated analysis lock the registry requires for HYP-04's four
`PENDING_SEPARATE_ANALYSIS_LOCK` decisions. Each of those independently holds
the result-display gate closed, and each must be resolved in a dated lock
written *before* any event-set freeze.

**It is not the Phase 2 preregistration lock.** Plan v0.2 §5.3 reserves target
definition, feature set, model specification and validation split for Phase 2,
written before the holdout is touched. Phase 1 has not started — it is blocked
on a linkage map that does not exist — so freezing those now would preregister
against a dataset nobody has seen. This lock fixes **estimator and reporting
rules only**.

**Timing.** This is written at the strongest possible moment: no real anchor
event has been observed, no event set is frozen, no result exists, and the
display gate is CLOSED on all five conditions. Nothing here can be reverse-
engineered from an outcome, because there is no outcome.

## 2. What resolving this lock does — and does not — unlock

Resolving all four decisions clears gate condition **C4 only**.

| | Condition | After this lock |
|---|---|---|
| C1 | status `ACTIVE_COLLECTING` | **NOT MET** — status is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| C2 | eligible events ≥ 193 | **NOT MET** — zero real eligible events |
| C3 | event set frozen before any result | **NOT MET** — no freeze record exists |
| C4 | every decision explicitly resolved | **MET only after signature *and* registry v1.2 (§11)** |
| C5 | real (non-placeholder) linkage | **NOT MET** — positional-synthetic placeholder; zero curated rows |

**The gate remains CLOSED.** This lock unblocks a step, not a result.

## 3. Registry crosswalk

Traceability from the registry's four decisions to this document's numbered
rules, since the mapping is not one-to-one.

| Registry decision | Resolved by |
|---|---|
| two-way clustering (anchor event × calendar period) | **D1**, **D2** |
| ticker-cluster estimator | **D3**, **D4**, **D5**, **D6** |
| the reported lag quantity's uncertainty treatment | **D7**, **D8** |
| whether implied volatility is promoted to primary | **D9** |

**D10** is not a registry decision. It arose from D3 while drafting — HYP-01
designates R as authoritative and HYP-04 has no R path — and is recorded here
because leaving it implicit would have let the weakest reading stand by default.

---

## D1 — Clustering dimension

**One-way, clustered on `calendar_period`.**

Not `event_id` (the Phase 0 default) and not `anchor`. Standard errors and
Satterthwaite degrees of freedom for every local-projection horizon are computed
with `calendar_period` as the cluster variable.

**Why a single dimension, and not two.** The two correlation sources named in
the registry decision — anchors sharing a macro environment, and the same anchor
recurring quarterly — **cross-cut**. They do not nest. The coarsest partition
respecting both is their join, and on the Phase 0 fixture that join is **one
cluster** covering the entire panel, where CR2 is undefined and Satterthwaite df
collapses to zero. A one-way cluster can therefore absorb one of these
dimensions or the other, never both. Two-way clustering would require a
Cameron-Gelbach-Miller implementation, and **no multiway CR2 exists anywhere in
this repository, validated or otherwise**; standing up an unvalidated one would
contradict this project's own treatment of unvalidated inference machinery.

**What this covers:** anchors reporting in the same period sharing a macro
environment.

## D2 — Stated residual limitation

**The same anchor recurring quarterly is NOT covered by D1 and must be stated
in every report that carries a HYP-04 standard error.**

This is not a caveat to be summarised away. D1 selects which half of the
registry's concern is addressed; the other half remains, and reporting it is the
condition under which choosing one dimension is honest rather than convenient.

Two structural consequences, both of which must be reported alongside any result:

1. **Cluster count is set by sample duration, not universe size.** Under
   `calendar_period`, expanding the anchor universe raises `N_events` toward the
   193 floor while adding **zero** clusters. Only a longer observation window
   adds clusters.
2. **Degrees of freedom will be single-digit at the gate threshold.** Measured
   on a fixture matching the panel shape the 193 floor implies (24 quarterly
   anchors × 8 quarters ≈ 192 events): 8 clusters, Satterthwaite df ≈ **5.7**,
   against 24.5 df under `event_id`. A two-sided t critical value at that df is
   roughly 2.5 rather than 1.96, and the CR2/Satterthwaite approximation is
   working near the edge of its range.

Consequence 2 is a reason to report df prominently, **not** a reason to suppress
a result — see D6.

## D3 — Covariance estimator

**CR2 / bias-reduced linearization**, adopting HYP-01's dated amendment (its D1).

`hyp04_supply_chain_hedge/clustered_se.py::cr_vcov(..., kind="CR2")`. The
arithmetic is a documented copy of the implementation the HYP-01 R cross-check
compared against `clubSandwich`, carried with a provenance comment rather than
imported across the bridge boundary the HYP-01 isolation test enforces.

**Specified is not approved.** HYP-01's own artifacts record
`method_approved: false` in both `GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json`
and `GST_HYP01_R_REFERENCE_VALIDATION_v1.0.json`. What exists there is
*implementation agreement* with clubSandwich under preregistered tolerances — a
statement about arithmetic, not a statistical endorsement. **HYP-04 inherits
that status and claims nothing stronger.** This lock fixes which estimator is
used; it does not certify it.

The R validation also does **not** extend to multiway clustering, which is a
second, independent reason D1 is one-way.

## D4 — Finite-sample correction

**The bias-reduced linearization built into CR2, and nothing else.** CR1 scaling
must not be applied on top, and no second correction of any kind is permitted.
Adopted from HYP-01's amendment D2.

## D5 — Degrees-of-freedom rule

**Coefficient-specific Satterthwaite approximation**, per
`clustered_se.py::satterthwaite_df`. The realized continuous degrees of freedom
are **persisted and reported** for every horizon — never rounded, never replaced
by G − 1, never omitted when small. Adopted from HYP-01's amendment D3.

Given D2's consequence 2, the realized df is the most decision-relevant number
this analysis produces after the coefficient itself.

## D6 — Singleton clusters and cluster-count policy

**Retain singleton clusters. Invent no minimum-cluster or effective-df cutoff.**
Adopted from HYP-01's amendment D8 and D10.

Singleton presence alone is never an exclusion rule. A result is **not
suppressed** because a post-hoc cluster-count or df threshold was crossed;
introducing any such threshold requires a new dated amendment authored without
outcome inspection.

**Always report:** total cluster count · number of singleton clusters ·
cluster-size distribution · realized Satterthwaite df · `N_pairs`, `N_events`,
raw ICC with its backing cluster count, DEFF, and `N_eff`.

This pairing is deliberate and load-bearing. D1 buys conservatism on the
standard error at the cost of very few clusters; D6 forbids resolving the
resulting thin df by suppression. The obligation therefore falls entirely on
**disclosure** — which only works if the reporting list above is treated as
mandatory rather than best-effort.

## D7 — Reported lag quantity and its uncertainty

**`onset_horizon` is reported as the interval `[onset − 2, onset]`, never as a
point estimate.**

The widening is **one-sided and fixed at k = 2**, preregistered here before any
real data. It matches the invariant the Phase 0 test suite already asserts
(`L ≤ onset_horizon ≤ L + 2`, with "never earlier than L" as the hard
invariant), so lock and code state the same thing.

**Why one-sided.** The defect is a *mechanical bias*, not sampling noise. Under
an expanding-window target, only 1/L of the averaging window is affected at the
true onset horizon, so measured |t| thins as the lag deepens and a noisy draw
reports onset late. The error cannot go the other way: measured |t| at h < L was
0.71 on the draw where h = L measured 2.08. Late, never early — so the interval
extends backward only.

**What this does NOT cover, stated because it would otherwise be assumed.** A
fixed widening addresses the bias and says **nothing about sampling
uncertainty**. At the df D2 establishes (≈ 5.7 at the gate threshold), sampling
uncertainty is not small. `[onset − 2, onset]` is a bias-corrected range, **not
a confidence interval, and must never be reported as one.** Adding a
noise-based band would require a new dated amendment.

**Known imprecision of k itself.** k = 2 was measured on synthetic fixtures at
specific (L, W) combinations, and dilution grows with L — so a constant k
under-covers deep lags and over-covers shallow ones. Fixing k now, before real
data, is what prevents it from being tuned later.

## D8 — What Stage 2 consumes

**Stage 2 sizes hedge tenor off the interval's LOWER bound (`onset − 2`), never
the upper bound and never `peak_horizon`.**

The asymmetry is deliberate: early tenor costs premium, late tenor arrives after
the reaction window it exists to protect against has closed. Given D7's
one-sided bias runs toward late, the lower bound is the only choice that does
not compound the known error.

`peak_horizon` remains reported — combined with onset it gives the window width
W — but it never reaches tenor sizing. This is the defect Patch 15 exists to
prevent and it is restated here so the lock and plan v0.2 §3.5 agree.

## D9 — Implied volatility promotion

**Conditional. Realized volatility remains the default and sole primary target.**
IV is not promoted from a secondary/robustness target to a primary one unless
every condition below holds, all of which are fixed here, before any data.

**D9.1 — Qualifying provider: QuantConnect Research** (`QuantBook`,
`OptionChainProvider`), the path used by `QC_Options_Validation_Script.py`. It
is the only source in this repository with precedent for real *historical*
option quotes. Two are excluded by existing findings, not by preference:
Alpaca — the provider-limitations doc states "never Alpaca's free indicative
options data used as an OPRA benchmark" — and yfinance, which serves current
chains only and has no historical endpoint. Any other provider requires a new
dated amendment and arrives with no validation history here.

**D9.2 — Per-peer coverage floor: ≥ 80%** of the required quarters must carry
usable chains **for that peer individually**. Rounding is by **ceiling**: the
required count is `ceil(0.80 × Q)`, so at Q = 8 a peer must cover 7 quarters and
may miss at most one. The ceiling rule is stated because flooring would silently
double the tolerance.

**D9.3 — Universe floor: ≥ 70%** of the peer universe must clear D9.2.

**D9.4 — Required lookback depth: 8 quarters** of the anchor sample window,
stated in quarters so this constraint and D1's cluster count cannot drift apart.

Eight is set against the observation window the 193-event floor implies at 24
quarterly anchors (≈ 8 quarters), so the coverage requirement spans the window
the analysis actually uses rather than a narrower slice of it. A shorter
lookback would be non-binding: a peer could clear it while carrying nothing for
the remaining quarters.

With D9.2's ceiling rule this yields `ceil(0.80 × 8) = 7` — **a peer must cover
7 of 8 quarters and may miss at most one.** That is the same one-miss tolerance
a 5-quarter window would have given, without certifying a span narrower than
the analysis.

**Why two floors and not one mean coverage percentage.** A mean is carried by a
handful of deeply covered names and hides exactly the dispersion that matters
here. The only empirical precedent available is the anchor universe, where
QuantConnect returned clean historical option pricing for **24 of 24** frozen
tickers — but events per ticker still ranged **1 to 8, median 2**. On the most
liquid population in this project, per-name depth already varied eightfold, and
HYP-04's peers are by construction the *thinner* names.

**What D9.3 is actually for.** It is a representativeness condition, not a
data-volume one. IV is a secondary/robustness target whose job is comparability
with the primary RV analysis. If a small share of the universe clears, the
IV-eligible subset is liquidity-selected, and an RV-versus-IV disagreement
becomes uninterpretable — the target changed and the sample changed together,
and nothing distinguishes them.

**Stated tension, recorded rather than resolved.** A coverage bar high enough to
guarantee comparability systematically excludes the thin, small-cap peers plan
§1 says this hypothesis is most interested in. Set high, IV stops being a
robustness check on the same population and becomes a different question about
liquid names. That is an argument for keeping IV **permanently secondary**, not
for lowering the bar.

**Always reported, whatever the outcome:** the per-peer coverage distribution
(min / median / max) and the thinness profile of the IV-eligible subset against
the full peer universe. Per the plan's existing rule, carried over unchanged,
coverage is **reported before any IV result is computed** — never decided first
and checked second.

## D10 — Authoritative CR2 implementation

**Python authoritative for Phases 0–1. An R cross-check is REQUIRED before any
Phase 3 out-of-sample result.**

HYP-01 designates the R / `clubSandwich` path as authoritative and its Python
CR2 as a validated cross-check. HYP-04 has no R path built, so adopting HYP-01's
rule verbatim is not literally available. This defers that work to the point
where it carries weight — a confirmatory out-of-sample number — rather than
claiming an authority now that nothing depends on.

Two constraints follow, and neither is optional:

1. **No Phase 3 result may be produced before the R cross-check exists**, built
   mirroring `tools/hyp01_r_reference/` and reported under preregistered
   tolerances. Reaching Phase 3 without it is a blocking failure, not a
   deferrable TODO.
2. **The exploratory/confirmatory distinction is doing real work here.** This
   option is defensible *because* HYP-04 is exploratory and its display gate is
   closed. Promotion of HYP-04 to confirmatory would invalidate the reasoning
   and requires a new dated amendment.

D3's status statement applies unchanged: implementation agreement is not
statistical approval, and `method_approved` remains `false`.

---

## 9. Decision values, and what they cost

Every slot is closed. This section records the two values whose consequences are
not obvious from their statement, so a later reader does not have to re-derive
them.

**D9.4 = 8 quarters is simultaneously a cluster ceiling.** Under D1 the cluster
variable *is* `calendar_period`, so a lookback of Q quarters caps any IV-based
analysis at Q clusters, and Satterthwaite df follows from that. Eight quarters
is therefore both "how far back coverage must extend" and "the most clusters an
IV analysis can have." The two cannot be tuned independently, and any future
change to one is a change to the other.

**D1's degrees of freedom are single-digit at the gate threshold.** Measured on
a fixture matching the panel shape 193 events implies: 8 clusters, Satterthwaite
df ≈ **5.7**, against 24.5 under `event_id` clustering. This is the price of
D1's conservatism on the standard error, it is not a defect, and under D6 it is
never grounds for suppressing a result — only for reporting it prominently.

**Universe scope is permissive and that is safe here.** Extension beyond the
frozen 24 tickers is allowed without an amendment, because C3 independently
requires the eligible event-ID set to be enumerated and frozen before any result
exists. Scope may widen; what gets recorded at freeze does not narrow.

---

## 10. What this lock does not touch

Append-only. It rewrites, deletes, renames and activates nothing.

- **Registry v1.0 and v1.1** — unedited. This lock resolves decisions the
  registry lists; it does not amend the registry.
- **HYP-01, HYP-02, HYP-03** — untouched in every respect.
- **The Phase 2 preregistration lock** — target definition, feature set, model
  specification and validation split remain unfrozen and are Phase 2's to fix.
- **The display gate's other four conditions** — see §2.
- **The quantum-provenance control** — independent of this lock in both
  directions. Signing this changes nothing about it, and no quantum-derived
  result is validated.
- **The linkage-map blocker** — unchanged. Zero rows curated.
- **Universe scope** — recorded separately; not fixed by this document.

## 11. What registry v1.2 must contain

Signing this lock does not clear C4. **The gate reads the registry**, so a
second, separate act is required — and the registry's own supersession rule
forbids doing it the obvious way.

**Do not edit v1.1.** Its rule is explicit: *"v1.0 is NOT edited in place. It
remains on disk, unchanged, byte-for-byte, and its own governance tests continue
to run against it."* Resolution therefore means authoring
`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.2.json`, additive, superseding v1.1,
with v1.1 left byte-for-byte intact.

**Do not hand-author it either.** v1.1 carries ~26 top-level keys and four
hypotheses, of which this change touches four nested fields. Copying the rest by
hand invites a silently dropped key — the exact failure the registry's own
governance tests exist to catch. Use the generator:

```bash
python -m hyp04_supply_chain_hedge.make_registry_v1_2            # dry run
python -m hyp04_supply_chain_hedge.make_registry_v1_2 --write
```

It refuses unless the lock is genuinely signed — the signed file must exist
(not the `_DRAFT` one), with a non-draft status, `in_force: true`, an
authorizer, an operative date, and the no-outcome attestation. It will not
overwrite an existing v1.2, it records v1.1's SHA-256 into v1.2 so later drift
is detectable, and it verifies v1.1 is byte-identical after writing. Dry run is
the default.

**Required shape per decision.** C4 enforces this positively — it asks whether
every decision is explicitly resolved, never whether any is still pending — so
the shape is not advisory:

```json
{
  "decision": "<unchanged text from v1.1>",
  "state": "RESOLVED_IN_DATED_ANALYSIS_LOCK",
  "resolved_by_lock": "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
}
```

Every one of these denies, and each was verified against the implementation:

- deleting the `unresolved_analysis_decisions` key
- emptying the ledger — **resolution is recorded by marking a decision, never
  by removing it**, mirroring the registry's own append-only discipline
- omitting `state`, or using any token outside
  `{PENDING_SEPARATE_ANALYSIS_LOCK, RESOLVED_IN_DATED_ANALYSIS_LOCK}` — a
  one-character typo denies rather than passing
- marking a decision resolved without citing the lock in `resolved_by_lock`

All four decisions stay in the ledger after resolution; the ledger still holds
four entries.

**Code that pins the registry filename** and must be repointed in the same
change, or the gate will keep reading v1.1 and C4 will never clear:

| File | What |
|---|---|
| `hyp04_supply_chain_hedge/display_gate.py` | the `REGISTRY_V1_1` constant |
| `hyp04_supply_chain_hedge/dashboard.py` | its `REGISTRY` constant |
| `test_hyp04_supply_chain_hedge_display_gate.py` | imports and reads it |
| `test_hyp04_supply_chain_hedge_quantum_provenance.py` | imports and reads it |
| `test_market_response_hypothesis_registry_v1_1.py` | v1.1 governance suite |

Two separate suites govern v1.2, and both already exist:

| Suite | Governs |
|---|---|
| `test_hyp04_supply_chain_hedge_registry_v1_2.py` | the **generator** — that it refuses without a signed lock, and builds correctly with one |
| `test_hyp04_supply_chain_hedge_registry_v1_2_artifact.py` | the **artifact** — the document on disk, however it was authored |

Both are added alongside the v1.1 suite rather than replacing it. v1.1's tests
keep running against v1.1, which is the entire point of not editing it in
place.

The artifact suite runs today, before v1.2 exists, against a synthetic v1.2
generated in a temp directory — so it is not a file that reports SKIP for
months and is first trusted at the moment it is first exercised. It also
carries 23 negative controls, because a checker that asserts nothing passes
every positive test. Writing them caught a dead assertion in this project's own
tests: both suites had compared `hypotheses` filtered to "not HYP-04" against
itself, which is `[] == []` — v1.1's list carries only HYP-04, since
HYP-01/02/03 live in v1.0 by reference. It passed against any document at all.
When v1.2 lands, the two skips become live checks against the real file.

## 11a. Order of operations

1. Complete the authorization record (template in
   `GST_HYP04_METHOD_AUTHORIZATION_TEMPLATE.md`) and verify mechanically that
   the gate reads CLOSED on all five before signing.
2. Complete §12 below; rename this file and its JSON off `_DRAFT`; set
   `status` and `in_force`.
3. Run the generator dry, then with `--write`.
4. Repoint the five files above. Both v1.2 suites already exist; no new suite
   is owed.
5. Re-run the HYP-04 suites and regenerate the dashboard. The artifact suite's
   two skips must turn into passes — if they still skip, step 3 did not
   actually produce a file.

Step 3 refuses if step 2 was skipped, by design.

## 12. Authorization

A human authors and signs this lock. It is not self-executing, and drafting is
not authorization.

| Field | Value |
|---|---|
| Drafted | 2026-08-19 |
| D1 clustering dimension | `calendar_period` — repo owner, 2026-08-19 |
| D7 lag interval | fixed one-sided widening, k = 2 — repo owner, 2026-08-19 |
| D9.1 provider | QuantConnect Research — repo owner, 2026-08-19 |
| D9.2 / D9.3 coverage floors | ≥ 80% per peer (ceiling), ≥ 70% of universe — repo owner, 2026-08-19 |
| D9.4 lookback depth | 8 quarters — repo owner, 2026-08-19 |
| Universe scope | frozen 24-ticker primary, extension permitted — repo owner, 2026-08-19 |
| D10 CR2 authority | Python for Phases 0–1; R cross-check required before Phase 3 — repo owner, 2026-08-19 |
| Authorizer | Project authorizer / repository owner — 2026-08-20 |
| Operative date | 2026-08-20 (UTC calendar date supplied by the authorizer) |
| JSON companion authored | `GST_HYP04_ANALYSIS_LOCK_v1.0.json`, `status: IN_FORCE`, `in_force: true` |
| Authorization record | `GST_HYP04_METHOD_AUTHORIZATION_2026-08-20.md` |
| No outcome inspected before signing | **Attested.** Five of six conditions verified mechanically before signing, not asserted — gate CLOSED on all five, `results: null`, zero eligible events for every hypothesis, no freeze record, zero curated linkage rows. |

**What this signature does not do.** It opens nothing. C4 reads registry v1.1,
not this file, so clearing C4 additionally requires authoring registry v1.2 and
repointing the code that pins the v1.1 filename. Even after both, the gate stays
**CLOSED** — C4 clears; C1, C2, C3 and C5 do not. No finding becomes
displayable, `method_approved` remains false for D3 and D10, and the linkage map
still does not exist at zero curated rows.

**On the authorizer.** A role, not an independent statistician or
methodologist. No external peer review, methodological review, institutional
approval or reviewer sign-off has occurred, and none is claimed. No handwritten
signature exists, and no reviewer identity is recorded because there is no
reviewer.

---

*Nothing in this document constitutes investment advice, a solicitation, or a
representation that any approach is profitable. No hedging edge has been
demonstrated, and Phase 0 established nothing about supply-chain transmission.*
