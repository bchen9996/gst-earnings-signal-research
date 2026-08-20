# HYP-04: Supply-Chain Hedge-Lag Model — Build Plan (v0.2)

**Version:** v0.2 · **Dated:** 2026-08-19
**Supersedes:** `HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.1_DRAFT.md` (retained, unedited in substance, as the historical record)
**Absorbs:** all 16 patches from `HYP04_PLAN_ROUND2_EDITS.md`, which is **demoted to a dated amendment record** as of this version and is no longer a live override.

**Status:** Phase 0 complete on placeholder linkage. Not preregistered. This is a build plan, **not** the Phase 2 lock document. No claim of a hedging edge is made anywhere in it.

> **Why this version exists.** v0.1 and the round-2 edits doc were *mutually amending*: the plan stated a decision, the edits doc overrode it, and a reader had to hold both in their head and apply a marker convention to know which text governed. That is workable for a build and unacceptable for a lock — a Phase 2 lock referencing two mutually-amending documents is precisely the drift risk this project's tamper tests exist to catch. **This document is self-contained.** Where v0.1 and a patch disagreed, the patch's text is written in directly and v0.1's superseded wording is not carried forward. Nothing here needs to be read alongside anything else to be applied correctly.

---

## 0. Provenance — where each patch landed

Traceability, so demoting the edits doc loses nothing. Where a patch carried a "Round 2 / 3 / 5 correction" marker, **the corrected version is what was merged** and the original wording was deliberately dropped.

| Patch | Subject | Disposition in v0.2 |
|---|---|---|
| 1 | Prewhitened CCF direction | §3.5 — Round 2 correction applied; double-prewhitening fork **dropped**, not offered |
| 2 | N-gate unit and multiplicity | §6 — Round 2 correction + all three Round 3 additions applied; original double-counted clustering and is **not** carried forward |
| 3 | Horizon grid stated once | §3.2 — single grid h = 1…20 |
| 4 | "Quantum autocorrelation function" | §3.6 — exact term used; removed from Definition of Done |
| 5 | Stage 2's underlying exposure | §4 — assumed existing long-equity peer holding, stated explicitly |
| 6 | Two additional required tests | Bullet 1 **superseded by Patch 10**, not merged. Bullet 2 (residualization-leakage) merged at §3.3 and §5 |
| 7 | Build sequencing within Phase 0 | §5.1 — recorded as build process; explicitly *not* a methodology change |
| 8 | Audit call budget | §5.1 / §3.1 — recorded as build process; superseded in framing by Patch 13 |
| 9 | Realized-volatility estimator | §3.2 — Round 3 correction applied; the unnormalized `RV(h) = √(Σr²)` is **rejected**, with the reason kept |
| 10 | Split negative control into two fixtures | §5.2 — replaces Patch 6 bullet 1 |
| 11 | Linkage map needs an as-of date | §8 — as-of date is a required column, not optional |
| 12 | `min_bucket_count` design decision | §3.3 — accept-and-report; widening buckets rejected on validity grounds |
| 13 | Audit needs a staged go-ahead | §3.1 / §5.1 — Round 5 correction applied; the constraint is rate-limiting, **not** cost, for the provider actually used |
| 14 | Build-session handoff file | §5.1 — recorded as build process, not methodology |
| 15 | "peak" ≠ "onset" | §3.5 — merged with its measured residual bias; v0.1's conflating sentence is **not** carried forward |
| 16 | HYP-04 unclaimed; registry entry is a governed act | §9 — **resolved since the patch was written**: registry v1.1 registers HYP-04 as exploratory |

Two patches changed status after the edits doc was written, and v0.2 reflects the current facts rather than the historical ones:

- **Patch 2's "~190–240" is superseded by a measured figure.** The patch required the multiplicity target be derived empirically rather than assumed, and that run has since happened. The operative floor is **193 anchor events**. 190–240 was a provisional placeholder and is retired.
- **Patch 16's registry action has been taken.** HYP-04 is registered as exploratory in registry v1.1 (v1.0 unedited).

---

## 1. What this model is for

Not a signal to trade the anchor stock's own options — that is the part of this project that has repeatedly failed real-quote validation. This model decides, for each ticker in a supply-chain/competitor basket tied to an anchor stock, two things:

1. **Link-Strength & Lag Score** — given a confirmed anchor earnings shock, how much (if at all) does this specific peer's volatility tend to move, and how many trading days does that reaction take to show up in the peer's own market.
2. **Hedge Structure Selection** — given that score plus the peer's own current options-market conditions, which protective structure (or none) is worth putting on, and how it is sized.

These are deliberately two separate stages. Stage 1 is the actual modeling problem. Stage 2 is closer to standard options-desk arithmetic and stays simple and auditable rather than learned, for reasons in §4.

## 2. Data dependencies

| Need | Source | Status |
|---|---|---|
| Anchor tickers + confirmed historical earnings-day shocks | Already in repo (`Daily Excess Return Data*`, `GST Data`) | Available |
| Supply-chain / competitor / customer linkage per anchor, with relationship type **and a first-known/established-as-of date per pair** | Hand-curated map (source changed 2026-08-18) | **Blocking — does not exist.** Ingestion path built and tested (`curated_linkage.py`); **zero rows curated.** A loader is not a map. |
| Peer tickers' own historical returns, volatility, options quotes | New pull (Alpaca/yfinance infra exists) | Buildable independently |
| Peer coverage/thinness proxy (search volume, analyst count, news volume) | GST + GDELT infra exists | Buildable independently |
| Peer options liquidity, skew, term structure | Same providers as HYP-01 | Buildable independently |
| Peer **historical** options chains (needed only if IV becomes the target) | Not obtained | **Unavailable.** The Phase 0 audit used yfinance, which serves *current* chains only and has no historical endpoint — see §3.1. |

Only the linkage map is a hard blocker on real data collection. Everything else was prototyped on a placeholder linkage to validate pipeline mechanics before the real map exists.

> **What the Phase 0 placeholder actually is.** Peers are the non-anchor tickers from `AllTickers_Sectors.csv`, assigned to anchors **by list position**. The sector column is not read for pairing. This is *positional-synthetic*, not same-sector — weaker than "same-sector peers" implies. Adequate for exercising estimator mechanics against injected ground truth, and **not** a basis for any claim about transmission.

## 3. Stage 1 — Link-Strength & Lag model

### 3.1 Target variable: realized vol vs. IV — decided by data availability, not preference

Do not choose between the peer's realized volatility and its near-term put-implied vol on theoretical grounds. Realized vol is computable for the entire peer universe from price data this repo already has. Peer IV requires clean *historical* options chains per peer, and the thinly-covered small-cap names this hypothesis is most interested in (§1) are exactly the ones most likely to have sparse or unreliable historical quotes.

**Default target is realized volatility**, usable for 100% of the universe. IV is promoted to a secondary/robustness target only for peers with confirmed clean coverage, and only if that subset is large enough to justify a separate parallel analysis. **The coverage percentage must be reported before that call is made — do not decide first and check second.** This decision procedure and whatever coverage threshold is set are themselves preregistered decisions and belong in the Phase 2 lock, not revisited after seeing which target "looks better."

**The Phase 0 audit does not settle this, and cannot.** *(Patch 13, Round 5 correction.)* The audit ran against yfinance, which serves **current option chains only and has no historical endpoint**. A 100%-current-coverage result establishes that option chains exist for these peers. It says nothing about transmission, and it does **not** promote IV to a secondary target — the plan's actual question, usable historical options data far enough back, remains unanswered. If historical coverage is ever checked against a genuinely historical provider, re-apply the staged process below from scratch rather than assuming the yfinance findings carry over.

**Real provider calls require a staged, explicit go-ahead from the repo owner — at both stages.** *(Patch 13.)*

1. **Canary batch first.** A small, hard-capped run (5–10 tickers) before the full universe, to establish empirically which constraint actually binds — cost, rate-limiting, both, or neither.
2. **Extrapolate, then authorize the full run.** Size the full run against what the canary revealed. For a free/rate-limit-bound provider (the case here): extrapolate call volume and wall-clock time, add pacing between calls as insurance against a provider with known fragility, and proceed once volume and pacing are stated explicitly. For a paid/metered provider: extrapolate real cost-per-call and set an explicit dollar cap, enforced by **failing loudly rather than silently truncating the universe**.

Do not carry the dollar-budget framing forward by default. The canary (10 tickers, 2026-08-17) showed this audit hits Yahoo's free unauthenticated endpoint at $0.00 regardless of volume; the binding constraint is rate-limiting and provider fragility, and this project has already been burned once by this exact provider. Re-derive the right constraint for whatever provider is actually in use. *(Patch 8's caching + stated-budget + loud-failure requirement stands; Patch 13 corrects only what the budget is denominated in.)*

### 3.2 Target definition: one horizon grid, log-variance ratio, earnings-cycle residualization

v0.1's variable-length window (anchor's earnings date to the peer's own next earnings) had a real confound: window length varied across pairs, mechanically capturing more baseline variance for pairs with a longer gap, and it overlapped the peer's own pre-earnings vol ramp — every company's vol rises into its own earnings regardless of any anchor. It is replaced by:

**One grid, stated once.** *(Patch 3.)* **h = 1…20 trading days**, used for *both* target computation and local-projection lag detection. There is no second grid. Headline numbers may be *reported* at h = 5, 10, 20 for interpretability, but that is a reporting choice, not a second computation.

**The realized-volatility estimator, defined explicitly.** *(Patch 9, Round 3 correction.)*

```
RVar(h)   = (1/h) · Σ r_i²  for i = 1..h        mean squared daily log return over [t+1, t+h]
RVar_ref  = (1/20) · Σ r_i²                      trailing 20 sessions ending at the anchor's earnings date
raw target = log(RVar(h)) − log(RVar_ref)        a log-variance ratio
target     = raw − earnings_cycle_baseline(peer, days_to_own_earnings)
```

Each choice is load-bearing:

- **A variance, not a volatility — mean, not sum, no square root.** `(1/h)Σr²` is unbiased for σ² at every h. A square-rooted version carries a Jensen's-inequality downward bias that itself shrinks with h (worst at h = 1, where E|r| ≈ 0.80σ against a true σ).
- **A log ratio, not a raw difference.** This removes the window-length scale artifact and the Jensen bias, stabilizes variance across the grid, and matches standard realized-volatility practice, where log RVar is used precisely for its better distributional properties.
- **The rejected definition, kept because the reason matters.** An earlier version defined `RV(h) = √(Σ r_i²)` with **no division by window length**. Under constant daily vol σ, `E[RV(h)] ≈ σ√h`, so `RV(h) − reference` carries a deterministic √h-shaped trend with **zero volatility content** — roughly −2.24σ at h = 5, ≈ 0 at h = 20, purely from window-length arithmetic. That is exactly the shape a lag profile exists to detect, so the unnormalized version would have *manufactured a fake signal*. Earnings-cycle residualization cannot rescue it: the residualization is indexed on days-to-the-peer's-own-earnings, a different index from h, and cannot absorb an h-indexed artifact. **Do not reintroduce an unnormalized or square-rooted estimator.**
- **Still true after the fix.** `RVar(h)` is a mean over an *expanding* window, so adjacent horizons remain highly overlapping and β_h stays mechanically autocorrelated across the grid. The normalization changed the scale, not the cross-horizon correlation structure. This is why max-T permutation rather than Bonferroni is the correct multiplicity correction (§6), and why §3.5's onset/peak distinction exists at all.

### 3.3 Earnings-cycle residualization, and what to do about thin buckets

Before comparing to any anchor event, estimate each peer's own unconditional volatility pattern as a function of trading days until *its own* next earnings, using that peer's full history **excluding anchor-adjacent windows**, so the baseline is not contaminated by the effect being measured. Subtract that baseline; the target becomes *abnormal* vol at each horizon, in the same spirit as this project's existing excess-return methodology.

**Exclusion must be verified, not documented.** *(Patch 6, second bullet.)* A test must assert that anchor-adjacent windows are genuinely excluded from each peer's baseline fit, and the pipeline must report **retained-history fraction per peer**. A peer linked to several quarterly-reporting anchors can have most of its history excluded, and peers below a stated retained-history threshold cannot get a reliable baseline at all. This is a universe constraint in the same category as the options-coverage audit and is reported alongside it, not discovered later.

**`min_bucket_count`: accept and report.** *(Patch 12.)* Bucketing days-to-earnings and averaging within buckets can leave under-populated buckets for thin peers, or for peers whose history is heavily consumed by anchor-adjacent exclusions. Three options existed: (a) widen buckets, (b) lower the minimum count, (c) accept and report. **The default is (c)**, and the other two are rejected on validity grounds rather than merely being less conservative:

- **(a) is the worst of the three.** The entire reason for residualizing against days-to-own-earnings is to isolate the universal pre-earnings vol ramp. Widening buckets blurs resolution exactly where that ramp is steepest, reintroducing the confound residualization exists to remove.
- **(b) keeps resolution but degrades baseline reliability** specifically for the thin/small-cap peers this hypothesis cares about most (§1) — the same failure mode the leakage test exists to catch, approached from the input side.

**Implementation.** Peer-anchor-horizon observations whose relevant bucket falls below `min_bucket_count` are treated as **missing** — excluded from the Stage 1 regression sample, never imputed or forced. Report the excluded fraction as its own number, distinct from the retained-history fraction (that one is about anchor-adjacent history excluded from baseline *estimation*; this is about bucket population once that history is in hand). **Fix bucket width and `min_bucket_count` before looking at how many observations survive** — choosing either after seeing the resulting N is exactly the after-the-fact tuning this rule exists to prevent.

### 3.4 Candidate features

Per peer, per anchor event:

- Anchor shock magnitude (confirmed |excess return| or GST z-score, already validated in this project)
- Historical correlation/beta of peer to anchor
- Relationship type: direct supplier/customer vs. sector competitor vs. loose sector neighbour — these likely have different diffusion speeds and should not be pooled without checking
- Peer coverage/thinness: search volume level, analyst count, news volume — a proxy for how likely the market already prices the link
- Days between the anchor's earnings and the peer's own next earnings

**Model choice.** With roughly 24–50 anchor tickers and a similarly sized peer basket, the number of independent (anchor event × peer) observations is small — the single biggest risk to this stage. Use a simple, regularized, interpretable model (ridge/lasso, or a basic hazard/survival model for "days until lag closes"), never tree-based or deep. A model needing hundreds of parameters will overfit this sample the way the earlier IV-mispricing and Attention Spread work did.

### 3.5 Lag detection: local projections primary, prewhitened CCF cross-check

A raw cross-correlation function has two real weaknesses here: it cannot condition on controls at each lag, so a "significant" lag can be shared sector-wide movement rather than anchor-specific transmission; and it is vulnerable to spurious correlation when either series is autocorrelated.

**Primary method: local projections** (Jordà-style). For each h in the grid, regress the peer's residualized abnormal vol at h on the anchor's shock magnitude plus controls, with cluster-robust SEs — reusing the CR2/Satterthwaite machinery already built and R-cross-validated for HYP-01 in `tools/hyp01_r_reference/` rather than standing up a second inference method. The β_h sequence is an impulse-response profile with its own confidence bands.

**`peak` is not `onset`, and Stage 2 needs onset.** *(Patch 15. v0.1 said "the horizon where it peaks and clears significance is the estimated lag" — that is wrong under this target and is not carried forward.)*

Because the target is an expanding-window mean from day 1 to day h, its value rises monotonically through a rectangular elevated-response block `[L, L+W−1]` — each newly included elevated day pulls the running mean up — then falls as baseline days re-enter. So `argmax_h β_h` lands at **h = L+W−1, the end of the reaction window**, not at h = L, the onset. This is a direct consequence of expanding-window averaging, not an estimation artifact, and it reproduces on any rectangular-response fixture. Implementation testing confirmed it on **6 of 6** tested (L, W) combinations.

Report **`onset_horizon` and `peak_horizon` as two distinct quantities.** `peak_horizon` stays useful — combined with onset it gives the window width W — but **Stage 2's tenor sizing must read `onset_horizon`, never peak.** Reading peak as onset would size tenor (W−1) days too long and start the hedge (W−1) days late, arriving after the window it exists to protect against has closed.

**Onset, as implemented** (`inference.py::local_projection_analysis`): the first horizon, reading forward from h = 1 in ascending order, whose |t_h| exceeds the **max-T permutation critical value** (empirical 95th percentile of the permuted max-|t| distribution). Two specifics:

- **The threshold is the multiplicity-corrected max-T value, not a per-horizon one.** Onset inherits the same family-wise error control as peak. Reading it off an uncorrected per-horizon threshold would reintroduce the multiplicity problem max-T exists to solve, and would bias onset *early* — a false-positive risk, not merely a timing one.
- **Onset is gated on peak clearing first.** If the overall max-T test does not clear, `onset_horizon` is `None`. There is no path by which an onset is reported while the profile as a whole is non-significant.

**Known residual bias — onset is diluted, not exact.** At the true onset horizon L, only 1/L of the expanding-window average reflects the elevated period, so measured |t_L| thins as L deepens and a noisy draw can miss the threshold and report onset one or two horizons late. Measured: |t| at h = L was 5.58 (L=3), 3.53 (L=5), 3.98 (L=8), 4.69 (L=10) against critical values near 2.6–2.9 — comfortable in general, but one L=8 draw measured 2.08 at h=8 and reported onset = 9. **The error is one-sided — late, never early** (h < L measured 0.71 on that same draw), so it is not a false-positive risk, but a late onset still means a short tenor and a late hedge. Report `onset_horizon` with this caveat, not as an exact point estimate. The test suite asserts `L ≤ onset_horizon ≤ L+2` with "never earlier than L" as the hard invariant, not exact equality. This is also the statistical basis for Stage 2's `R4_lag_ci_too_wide` rule declining to size a position when lag uncertainty is too high.

**Prewhitened CCF — secondary classical cross-check, never the decision-maker.** *(Patch 1, Round 2 correction.)*

- **Fit the whitening filter (ARMA or GARCH) to the peer's realized-volatility series**, and apply that **same single filter to both series**, then cross-correlate the residuals. The anchor shock series is a sparse, roughly quarterly point process already close to white noise — a filter fit to it returns near-zero coefficients, making "apply to both" a no-op that leaves the peer's vol clustering untouched. Confirmed directly: AR(5) on peer-vol gives Σ|φ| = 1.093; on the anchor-shock series, Σ|φ| = 0.048.
- **There is no double-prewhitening fork.** An earlier version offered fitting each series its own model as an acceptable alternative. That option is **dropped**. Box-Jenkins prewhitening preserves proportionality to the true impulse-response weights *specifically because* one filter is applied to both; filtering x and y with different models breaks that proportionality and biases the estimated lag, even though the significance test would remain technically valid. Since this cross-check exists to cross-validate *where* the lag falls, not merely whether one exists, double prewhitening undercuts its purpose.
- **Significance from circular-shift permutation of the anchor event dates, never Bartlett bands.** Bartlett bands assume the white-noise-input case, which is exactly the assumption in question. Shifting event timing and recomputing the CCF preserves the peer series' own autocorrelation under the null, matching the permutation approach already used in `GST_Task1_PlaceboPermutationTest.py`.
- **Expect a power asymmetry, and do not read it as disagreement.** One peer sees ~16 anchor events while the LP pools thousands of observations.

### 3.6 Quantum autocorrelation function — tertiary, non-load-bearing, and now gated in code

*(Patch 4.)* Use **that exact term**, never "quantum-inspired." The precise term is deliberate: it makes the skip condition — no established, validated application to classical financial return series — a clear, checkable question with a clear answer (no). "Quantum-inspired" is loose enough to be satisfiable by construction, which quietly defeats the skip condition it is paired with.

The term properly refers to quantum time-correlation functions from statistical mechanics (⟨A(0)A(t)⟩ for quantum operators, involving commutators and quantum ensembles) — a real construct in physics with no established application to classical return series and no track record in finance the way CCF, GARCH, and lag-regression methods have.

If explored anyway, it must be an **isolated, clearly labelled experimental module** running *alongside* the classical CCF rather than replacing it, logging where the two agree or disagree. Matching this project's existing pattern of cross-validating novel machinery against a trusted reference before it influences anything (`tools/hyp01_r_reference/`), **it may not affect any lock, gate, or hedge decision until it has been validated against the classical result on known cases.** Treat it exactly as the R cross-check treats the CR2/Satterthwaite estimator: a check on the primary method, not a replacement.

**It is excluded from the Definition of Done** — not listed there even parenthesized as optional. Listing it creates delivery pressure to build something just to close the box. It should be genuinely optional or absent.

**Status: skipped**, because no citable construction exists. Nothing quantum-flavoured was improvised to fill the slot.

> **This rule is now enforced in code, not just stated here.** `hyp04_supply_chain_hedge/quantum_provenance.py` hard-blocks any quantum-derived output from every finding panel and from the Stage 1 Link-Strength score — **regardless of source** (this project's own tertiary module, or a result supplied from outside the repository) and **regardless of the display gate's state** — unless it carries a complete attestation of validation against the classical reference on known cases. No such validation exists and none is claimed. See `HYP04_QUANTUM_RESULT_GOVERNANCE_NOTE_2026-08-19.md`.

### 3.7 Validation, matching this project's existing standards

- **Placebo test.** Shuffle anchor-peer assignments and confirm the real linkage produces a materially different result than random pairing. If it does not, the model has nothing to learn regardless of algorithm.
- **Leave-one-anchor-out cross-validation**, never random k-fold — anchor events cluster in time and by sector, so random folds leak information across correlated events.
- **Preregister the target definition, feature list, and validation split before pulling any real peer options data.** A dated lock document must exist before Phase 2 begins.
- **Out-of-sample holdout** reserved and untouched until the in-sample model is fully specified and frozen.

## 4. Stage 2 — Hedge Structure Selection

Deliberately **rules-based, never a trained model**. The sample size needed to responsibly fit a structure-choice classifier does not exist here. Given Stage 1's score plus the peer's live options conditions (liquidity/open interest, put skew, term structure relative to the lag window, and a defined cost budget), a decision table picks among: no position, outright protective put, put spread, collar, or a sector-ETF proxy if the single name has no viable options market. Expressed as an explicit decision function or small constrained optimization, so every recommendation names the rule that produced it — consistent with this repo's audit-oriented culture.

**The assumed exposure, stated rather than implied.** *(Patch 5.)* Stage 2 protects an **assumed existing long-equity holding in the peer name**. "Minimize cost subject to a minimum protection threshold" is meaningless without a position to protect, and left unstated an implementer will invent an assumption and bake it into code. Absent that holding, buying puts is not a hedge at all — it is a directional long-volatility bet with a different risk profile and different sizing logic, and calling it a hedge would misdescribe what the recommendation does. The notional is an **assumption, not a real position**; hedge sizing scales linearly with it, so it is reported alongside every recommendation rather than buried.

**Tenor is sized off `onset_horizon`, never `peak_horizon`** — see §3.5.

**No real-capital or live-trading logic anywhere**, at any phase before Phase 4's paper-trading gate.

## 5. Build sequence

Every phase ends with a **smoke test** before the next may start: a fast end-to-end run of that phase's pipeline on a small fixed fixture, asserting only that it completes and produces outputs in the right shape and schema. Smoke tests are **not** statistical validation — the placebo test, CV, and OOS test are separate and specified above. They exist to catch integration breakage (a broken join, schema drift, a silent empty dataframe) before it wastes a phase gate. Each phase's smoke test is committed alongside that phase's code and run in CI.

### 5.1 Build process (not methodology)

Recorded here so it is not lost when the edits doc is demoted. **None of this changes a methodological decision.**

**Sequencing within Phase 0.** *(Patch 7.)* Build in this order, so the inference code is not validated mostly against itself:

1. **Synthetic-fixture generator** first, as its own deliverable — known injected lag, known effect size, known cluster structure.
2. **Audit + target + residualization**, validated against that fixture.
3. **Inference layer** (LP + clustered SEs, prewhitened CCF, ridge/lasso, LOOCV, placebo, ICC/N-gate), validated against the same fixture.

**Provider calls.** *(Patches 8 and 13.)* Cache all provider responses locally, state a maximum call budget per run, and **fail loudly rather than silently truncating the universe** if it is hit. The staged canary → full-run go-ahead in §3.1 governs, and the budget's denomination depends on which constraint actually binds for the provider in use.

**Build-session handoff file.** *(Patch 14.)* Write a dated `HYP04_PHASE0_BUILD_HANDOFF_<date>.md` at two triggers: **proactively** at the end of each build-sequence step, and **reactively** as soon as context is running low mid-step — with margin to actually finish writing it, since a handoff attempted after the limit is exhausted cannot be written at all. Contents: which steps are complete/in-progress/not-started and exactly what is unfinished; file and module state; test status; **any open decisions awaiting the repo owner's sign-off**, so a pending consent gate is never silently dropped across a session boundary; the single next concrete action; and a pointer to the authoritative docs rather than a re-summary. This is **distinct from** the Phase 0 feasibility status doc — that reports methodological results, this is build-process continuity, and neither substitutes for the other.

### 5.2 Required tests

Beyond each phase's smoke test:

- **Two split negative-control fixtures, not one.** *(Patch 10, replacing Patch 6's original single-fixture wording.)*
  - **Fixture A — zero effect, ample N:** LP peak non-significant post multiplicity-correction; placebo shows no real-vs-random separation; **the N-gate passes.** Confirms the gate correctly ignores effect size.
  - **Fixture B — insufficient N, any effect size:** the N-gate returns `False` regardless of the injected effect. Confirms the gate is sensitive to sample size specifically.
  - The original single-fixture version asked a zero-effect fixture to fail *both* the placebo test and the N-gate. The placebo half was right; the N-gate half was wrong — the gate measures whether the sample is large enough, not whether an effect exists. As written it would either fail against a correct implementation or pressure the implementer into wiring effect size into the gate, which would be a real bug.
- **Residualization-leakage test** — assert anchor-adjacent windows are genuinely excluded from each peer's baseline fit, and report retained-history fraction per peer (§3.3).
- **h-trend regression test** — assert the *contrast*, not an absolute threshold: the corrected target's h-trend must shrink with N while the rejected `√(Σr²)` definition's does not. A contrast cannot be passed by tuning.
- LP recovers a known injected lag; SEs are genuinely clustered; multiplicity correction actually moves the threshold; Satterthwaite dof computed; the CCF filter is fit to peer-vol and **verifiably not** to anchor-shock; LOOCV split correctness; placebo correctness; Stage 2 edge cases.

### 5.3 Phases

**Phase 0 — Feasibility (no locking, no real capital logic).** Confirm the pipeline runs end-to-end on placeholder linkage using data on hand: the options-availability audit (§3.1), that the target computes under its §3.2 definition, a first empirical ICC estimate, and whether the placeholder sample clears the §6 gate. **Status: complete.**

**Phase 1 — Exploratory, non-binding.** Once the real linkage map exists, run Stage 1 openly (no lock) to see whether a plausible signal exists. Results are diagnostic only; nothing is shown as a finding, per the result-display-gate convention. **Status: blocked** on the linkage map.

**Phase 2 — Preregistration lock.** Freeze target definition, feature set, model spec, and validation split in a dated lock before touching the holdout. *Smoke test:* run the locked pipeline against in-sample data only and confirm it reproduces the exact frozen spec — a tamper/drift check in the spirit of this project's "tampered lock file → SystemExit" mutation tests.

**Phase 3 — Out-of-sample test.** Run the locked model against the holdout **once**, report the result regardless of outcome, no re-running until it looks better. *Smoke test:* a dry run against a copy of the holdout *schema* must pass **before** the one real execution — the real run should never be the first time the code has executed end-to-end.

**Phase 4 — Paper-trading gate.** Only if Phase 3 clears its preregistered bar. Also where formal options eligibility would have to be resolved (§9). *Smoke test:* a daily end-to-end dry run stopping short of any live submission, passing before that day's cycle runs.

## 6. Sample-size gate

*(Patch 2, Round 2 correction plus all three Round 3 additions. v0.1's naive gate and the original patch's double-counted version are both superseded.)*

**The unit ambiguity that made this necessary.** "~126 total observations" states no unit. Read as anchor events, that is roughly a year of coverage across a 24–50-ticker quarterly universe. Read as (anchor × peer) pairs, it is a far easier bar — at ICC 0.2–0.4 with ~10 peers per anchor it could pass with as few as ~13 anchor events, defeating the gate's purpose. The two readings are not close enough to leave ambiguous.

**Do not apply the clustering correction twice.** Stating the gate purely in anchor events implicitly assumes ICC = 1 (the conservative endpoint, where every peer within an event is redundant). Asking additionally for a design-effect-adjusted gate on top of that applies the correction twice and makes the ICC estimate decorative — computed but never moving the gate.

**The gate:**

```
DEFF  = 1 + (m̄ − 1) · ICC        m̄ = average peers per anchor event; ICC floored at 0 for DEFF only
N_eff = N_pairs / DEFF
```

- Report **N_pairs** (ICC = 0 bound) and **N_events** (ICC = 1 bound) for context. **Neither is gated on directly.**
- Estimate ICC empirically from the data. Report the **raw** value even when floored for DEFF.
- **Gate on `N_eff` against the operative floor.**

**The operative floor is 193 anchor events.** Derived, not assumed: max-T permutation on synthetic fixtures measured the effective number of independent tests across the 20-horizon grid at **6.05–6.34** — far below 20, because an expanding-window target makes adjacent horizons correlated by construction (§3.2) — and Šidák correction at that measured k, with d = 0.5, α = 0.05, power = 0.80, gives 193.

- **The naive single-test 126 appears only as a labelled baseline, never as the operative gate.**
- **"190–240" is retired.** It was a hand estimate assuming 6–20 effectively independent tests, stated explicitly as a provisional placeholder to be superseded once the post-inference-layer diagnostic run produced a real number. That run has happened; this is that number.
- **This is a governance floor, not a power guarantee.** Inputs were a hypothetical d = 0.5 chosen before any data, on synthetic fixtures with injected ground truth. No observed project result entered it. **Reaching a threshold licenses looking, not concluding.**

**Report alongside the gate, always:**

- **Satterthwaite dof.** DEFF accounts for one clustering dimension only (peers within event). Once SEs are two-way clustered, N_eff reads optimistic relative to what the SEs actually reflect. The Satterthwaite dof from the CR2 estimator is itself an effective-sample-size estimate, produced as a byproduct of the LP regression using machinery already R-validated. **Where the two diverge, the Satterthwaite dof is the more honest number.**
- **ICC stability.** ICC estimates are unreliable with few clusters. Report the **cluster count** behind the estimate and a **bootstrap interval** if feasible, so a gate result driven by a noisy low-cluster ICC is visible rather than implicit.
- **Implied calendar coverage.** Across a 24–50-ticker quarterly universe (~96–200 anchor events/year), the floor is roughly 1–2 years of coverage at the conservative endpoint — less once the empirical ICC comes in below 1. This makes the gate checkable against the existing data window rather than abstract.
- **The estimator-mismatch caveat.** The two-sample Cohen's-d power calculation does not match the continuous LP regression actually run. Keep it as a **stated conservative proxy**; do not silently reconcile the two into an apparent exact match.

**Clustering the standard errors.** Cluster **two ways — anchor event × calendar period** — if the R-validated CR2/Satterthwaite machinery generalizes to multiway clustering (Cameron-Gelbach-Miller). Anchors reporting the same week share a macro environment and the same anchor recurs quarterly; one-way clustering understates SEs in exactly the direction that makes a marginal result look significant. **If it does not straightforwardly generalize, state two-way clustering as a known limitation — never ship one-way silently.**

> **As built:** no multiway CR2/Satterthwaite implementation exists in this repository, validated or otherwise. Phase 0 ships **one-way (anchor-event) clustering with two-way flagged as a stated limitation**, which is the fallback this rule authorises. It is registered as an open `PENDING_SEPARATE_ANALYSIS_LOCK` decision (§9).

## 7. Known risks to preregister against

- **Multiple testing.** Many candidate peers per anchor means many implicit comparisons. Addressed by max-T permutation across the horizon grid (§6); the peer dimension needs the same discipline rather than per-peer significance hunting.
- **Survivorship in the linkage map.** A map including only currently-prominent relationships would bias the sample against historically relevant but now-defunct links.
- **Coverage drift.** A peer's thinness is not static — a name can go from thinly to heavily covered mid-sample (e.g. after its own breakout), mechanically shrinking the lag this model looks for. Needs a **time-varying** coverage feature, not a static one.
- **Small-N overfitting.** Flagged throughout; the single most likely failure mode given this project's history with the IV-mispricing and Attention Spread hypotheses.
- **Look-ahead through the linkage map.** See §8 — the as-of date is the control.

## 8. What is needed to move past Phase 0

**The linkage map is the one hard blocker**, and it requires four things per pair:

1. Ticker pair
2. Relationship type
3. Confidence
4. **A first-known / established-as-of date** *(Patch 11)*

**The date column is required, not optional.** A map built today encodes relationships known today; applying it to historical anchor events without knowing when each relationship was first established or publicly known is look-ahead bias — the same class of problem this project's own forensic audit already found in the GST z-score history. **A map delivered without that column is a blocking data-quality failure, not a partial delivery.** Retrofitting a first-observed date after the map is built is far more expensive than requesting the column up front.

> **Source changed 2026-08-18; the blocker is unchanged.** The automated teammate mapping was deprioritised in favour of **hand curation** against a fixed 15-column template that carries the as-of date natively, so the retrofit risk is resolved by construction. A validating ingestion path is built and tested (`curated_linkage.py`); **zero rows are curated.** Registry v1.1 still records the required linkage measurement as `does_not_exist`.
>
> **Open, and the repo owner's call:** whether the curated map targets HYP-01's frozen 24-ticker universe or a smaller first pass. This drives how long Phase 1 stays blocked and what `N_events` can reach against the 193 floor.

From the data-validation teammate: nothing blocking, but thin-ticker calibration work would directly improve the coverage/thinness feature.

## 9. Registry status and open decisions

*(Patch 16, updated to current facts.)*

**Why the ID is HYP-04.** The planning documents arrived named HYP-02. That ID was already held by a real, registered, unrelated hypothesis ("cross-source attention divergence vs. earnings surprise"), as is HYP-03 ("post-earnings attention decay") — both `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`, meaning the IDs are reserved and dated even though no code occupies them. Landing this work under an in-use ID would have looked unclaimed while overwriting a registered hypothesis's identity. A full repo sweep confirmed HYP-04 was genuinely unclaimed, and the rename was made with owner approval.

**Registration is a governed act, and it has now been performed.** Renaming a document does not register a hypothesis. Registry changes are dated, versioned, and written *before* the evidence that would motivate them. HYP-04 is registered as **exploratory** in **registry v1.1** (v1.0 unedited), with a threshold of **193 eligible anchor events** — the same unit as HYP-01/02/03's 60/60/40.

**The options tension, resolved deliberately rather than discovered later.** The registry has no registered options hypothesis and both options-eligibility classes carry `DENY_NO_REGISTERED_HYPOTHESIS`. HYP-04's Stage 2 is options-adjacent by construction. Phase 0 sidesteps this cleanly — realized vol is the target, Stage 2 only constructs recommendations, nothing options-eligible executes — and **HYP-04 is not registered against an options class.** Phase 4 is where this would have to be resolved for real.

**Open `PENDING_SEPARATE_ANALYSIS_LOCK` decisions.** Each independently holds the result-display gate closed, and each must be resolved in a dated analysis lock written *before* any event-set freeze:

1. Two-way clustering (anchor event × calendar period) — see §6.
2. Whether implied volatility is ever promoted from secondary to primary — see §3.1.
3. The reported lag quantity's uncertainty treatment — `onset_horizon` is late-biased by construction, see §3.5.
4. Ticker-cluster estimator.

## 10. Defaults requiring confirmation before this is treated as locked

None of these are locked in the preregistration sense — this is a build plan, not the Phase 2 lock. Per this project's convention they are stated as decisions rather than silently carried into code.

1. **Prewhitening** — filter fit to the peer-vol series, applied to both; not the anchor-shock series; no double-prewhitening fork. *(§3.5)*
2. **N-gate** — `N_eff = N_pairs / (1 + (m̄−1)·ICC)`, gated at the empirically derived floor of **193**, with Satterthwaite dof, ICC cluster count and bootstrap interval reported alongside. *(§6)*
3. **Target definition** — single grid h = 1…20; target `log(RVar(h)) − log(RVar_ref)` with `RVar(h) = (1/h)Σr_i²`; trailing-20-session reference, same construction. Not the unnormalized `√(Σr_i²)`. *(§3.2)*
4. **Term** — "quantum autocorrelation function," excluded from the Definition of Done, and now gated in code. *(§3.6)*
5. **Stage 2 exposure** — assumed existing long-equity peer holding. *(§4)*
6. **SE clustering** — two-way if the existing machinery generalizes; otherwise a stated limitation, never silently one-way. Currently one-way, flagged. *(§6)*
7. **Negative-control tests** — two separate fixtures. *(§5.2)*
8. **`min_bucket_count`** — accept-and-report; do not widen buckets or lower the threshold to make the gate pass. *(§3.3)*
9. **Options-coverage audit** — staged go-ahead, canary then extrapolated full run. **Requires the repo owner's sign-off directly; not a default anyone else can set.** *(§3.1)*
10. **Lag reporting** — `onset_horizon` reported separately from `peak_horizon`, with tenor sized off onset. *(§3.5)*

---

*Nothing in this document constitutes investment advice, a solicitation, or a representation that any approach is profitable. No hedging edge has been demonstrated, and Phase 0 established nothing about supply-chain transmission.*
