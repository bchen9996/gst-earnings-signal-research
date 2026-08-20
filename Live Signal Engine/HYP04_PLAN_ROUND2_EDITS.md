# HYP-04 Plan — Round 2 Edits (v1.1, post two Claude-Code implementation-review passes)

> # ⚠ SUPERSEDED — HISTORICAL AMENDMENT RECORD, NOT A LIVE OVERRIDE
>
> **As of 2026-08-19 this document no longer governs anything.** All 16 patches
> below were merged into **`HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md`**,
> which is self-contained and is the single authoritative build plan.
>
> **Do not implement from this document.** Read v0.2 instead. It needs no
> companion doc and no marker convention: where a patch here carried a
> "Round 2 / 3 / 5 correction" or a struck-through "Superseded by" note, only
> the corrected text was merged, and the superseded wording was deliberately
> left behind.
>
> This file is retained, unedited below this banner, so the *reasoning* behind
> each decision stays inspectable — several patches document a specific bug and
> why an alternative was rejected, which v0.2 states as conclusions. v0.2 §0
> maps every patch to where it landed.
>
> Two items were **already stale when the merge happened**, and v0.2 carries the
> current facts rather than these:
> - **Patch 2's "~190–240"** was a provisional placeholder awaiting an empirical
>   run. That run happened; the operative floor is **193 anchor events**.
> - **Patch 16's registry action** has been taken — registry v1.1 registers
>   HYP-04 as exploratory.
>
> The process note below asked for exactly this merge. It is now done, and the
> note is left in place as the record of the request.

Source of these edits: two rounds of Claude Code review against `CLAUDE_CODE_BUILD_PROMPT_HYP04.md`. Round 1 produced Patches 1–8. Round 2 reviewed the result and produced corrections to Patches 1 and 2 (both updated in place below, superseding the original wording) plus new Patches 9–11. Each item patches the **plan**, not just the prompt, because each is a methodological decision the plan left ambiguous or got wrong, and this project's convention is to preregister decisions rather than let an implementer infer them. Judgment calls are marked explicitly as **DEFAULT (confirm or override)** — same convention Section 6 already uses for the effect-size assumption.

**Process note (flagged in round 2, ACTIONED 2026-08-19 — see the banner above):** this doc currently overrides the original plan doc for Phase 0 purposes, which is fine for a build but not for a Phase 2 lock — a lock referencing two mutually-amending documents is the drift risk this project's tamper tests exist to catch. Before Phase 2, merge this into a plan v0.2 and let this doc become a dated amendment record rather than a live override.

---

## Patch 1 — Prewhitened CCF direction (Section 3, "Lag detection method")

**Problem:** The plan hedged this as "prewhiten by filtering both series through a model fit to one of them." The build prompt resolved it to "fit AR/ARIMA to the anchor shock series" — the wrong series. The anchor shock series is a sparse, roughly-quarterly point process, already close to white noise; an ARIMA fit to it returns near-zero coefficients, so "apply that filter to both series" is close to a no-op. The actual persistence this cross-check needs to remove lives in the peer's own volatility series (ordinary vol clustering). As specified, the cross-check runs, logs cleanly, and doesn't do the thing it exists to do.

**DEFAULT (confirm or override):** Fit the whitening filter (ARMA or GARCH) to the **peer's realized-volatility series**, apply that **same single filter to both series**, then cross-correlate the residuals. No alternative — see below.

**Round 2 correction:** the original version of this patch offered "double prewhitening" (fit each series its own model independently) as an acceptable alternative. Drop that option. This cross-check's job is lag identification, not just testing whether any correlation exists. Box-Jenkins prewhitening preserves proportionality to the true impulse-response weights specifically *because* the same filter is applied to both series — filter x with one model and y with a different one and that proportionality breaks, biasing the estimated lag even though the significance test would remain technically valid. Since the whole point of this cross-check is cross-validating *where* the lag falls, not just *whether* one exists, double prewhitening undercuts its purpose. One filter, fit to the peer-vol series, applied to both — no sanctioned fork.

**Also add:** Don't rely on Bartlett confidence bands for CCF significance — they assume the standard white-noise-input case, which is exactly the assumption in question here. Use a **circular-shift permutation of the anchor event dates** instead (shift event timing, recompute the CCF, build a null distribution) — this preserves the peer series' own autocorrelation structure under the null, matching the permutation-based approach this project already uses elsewhere (`GST_Task1_PlaceboPermutationTest.py`).

---

## Patch 2 — N-gate unit and multiplicity (Section 6)

**Problem:** "~126 total observations (~63 per group)" doesn't state a unit. Read as anchor events, 126 is roughly a year of coverage across a 24–50-ticker quarterly-reporting universe. Read as (anchor × peer) pairs, it's a much easier bar — at ICC 0.2–0.4 with ~10 peers per anchor, the pair-level reading could pass with as few as ~13 anchor events, which defeats the purpose of the gate. The two readings aren't close enough to leave ambiguous.

**Round 2 correction — this patch originally double-counted clustering and is replaced below.** Stating the gate purely in anchor events implicitly assumes ICC = 1 (the conservative endpoint — at ICC=1, every peer within an anchor event is redundant with the others, so only the event count is real information). Separately asking for an "empirical ICC estimate + design-effect-adjusted N gate" on top of that, as the original plan's Section 6 and the v3 status-doc requirements both did, applies the clustering correction twice and makes the ICC estimate decorative — it's computed but never actually used to move the gate.

**DEFAULT (confirm or override) — coherent version:**
- Report **N_pairs** (raw anchor×peer observations) and **N_events** (anchor events) as the two bounds — N_events assumes ICC=1, N_pairs assumes ICC=0.
- Estimate ICC empirically from the placeholder-linkage Phase 0 data (as originally intended).
- Compute the **design effect**: DEFF = 1 + (m̄−1)·ICC, where m̄ = average peers per anchor event.
- Compute **N_eff = N_pairs / DEFF**.
- Gate on **N_eff ≥ 190–240** (see multiplicity note below for where 190–240 comes from). This is the only number the gate actually checks — N_pairs and N_events are reported for context, not gated on directly.

**Also add — horizon multiplicity:** Local projections run over a grid of horizons and the "estimated lag" is wherever β_h peaks and clears significance. Picking the max over ~20 horizons without correction inflates the false-positive rate exactly the way this project's placebo-testing culture is built to catch. Apply a **max-T / permutation-based multiplicity correction** across the horizon grid (not Bonferroni — see Patch 9, cumulative RV makes β_h mechanically autocorrelated across horizons, and Bonferroni would be badly over-conservative against that correlation). Under d = 0.5, this pushes the real target above the naive single-test 126 — state the multiplicity-corrected target as **~190–240**, applied to N_eff, not to N_events directly. The 126 number from the original power calc should be kept in the doc as the single-test baseline, but labeled as such, not as the operative gate.

**Also add — implied calendar coverage:** across a 24–50-ticker quarterly-reporting universe, that's ~96–200 anchor events/year. At the ICC=1 conservative endpoint (N_eff = N_events), 190–240 is roughly **1.2–2.5 years of coverage** — materially less once the empirical ICC comes in below 1. State this in the status doc; it turns the gate into something checkable against the existing data window immediately, not just an abstract number.

**Also add — two-way clustering:** SEs clustered by anchor event alone handle peers-within-event but not anchor events that are themselves clustered in calendar time (anchors reporting the same week share a macro environment; the same anchor recurs quarterly). One-way clustering will understate SEs in exactly the direction that makes a marginal result look significant. Cluster two ways — anchor event × calendar period (week or quarter) — if the R-validated CR2/Satterthwaite machinery from HYP-01 generalizes to multiway clustering (Cameron-Gelbach-Miller); if it doesn't straightforwardly generalize, state two-way clustering as a known Phase 0 limitation/robustness TODO rather than silently shipping one-way only.

**Round 3 addition — Satterthwaite dof alongside N_eff:** DEFF = 1 + (m̄−1)·ICC only accounts for one clustering dimension (peers-within-event). Once SEs are two-way clustered, N_eff's assumption and the inference's actual effective sample size diverge — N_eff will read optimistic relative to what the two-way-clustered SEs actually reflect. No new machinery needed: the Satterthwaite degrees of freedom from the CR2 estimator is itself an effective-sample-size estimate, already produced as a byproduct of the LP regression, using machinery already R-validated in `tools/hyp01_r_reference/`. **Report the Satterthwaite dof alongside N_eff in the status doc.** Where the two diverge, the Satterthwaite dof is the more honest number — it reflects whatever clustering structure is actually used in inference, which DEFF doesn't capture once clustering goes two-way.

**Round 3 addition — derive the multiplicity target empirically, don't assume it:** The "~190–240" range was a hand estimate (assuming roughly 6–20 effectively-independent horizon tests), made before RV(h) was pinned to the corrected log-variance construction (Patch 9). Because RVar(h) is a mean over an expanding window, adjacent β_h remain highly correlated, and the effective number of independent tests across the 20-horizon grid is likely closer to 2–4 than 6–20 — which would put the real target nearer 150–190. **Don't re-guess it a second time.** The max-T permutation procedure — which is part of the inference layer's own build, not the fixture generator's — run against the synthetic fixture once that machinery exists, empirically yields the multiplicity penalty; back out the effective number of independent tests from that run and compute the target from it directly. This has to happen as a distinct step after the inference layer is built, not folded into fixture generation itself (an earlier version of this instruction asked the fixture step to emit this number directly, which is circular — the permutation machinery it would need doesn't exist until the inference layer is built). **State 190–240 in the status doc only as a provisional placeholder**, explicitly superseded once the post-inference-layer diagnostic run produces the real number.

**Round 3 addition — ICC stability:** N_eff depends on an estimated ICC, and ICC estimates are unreliable with few clusters. Report the **cluster count backing the ICC estimate** in the status doc, and a **bootstrap interval** around it if feasible, so a gate result driven by a noisy low-cluster-count ICC estimate is visible rather than implicit.

**Also add — estimator mismatch caveat:** The two-sample Cohen's-d power calculation doesn't match the continuous LP regression actually being run. Keep it as a **stated conservative proxy**, not something the implementer silently reconciles into an exact match — record this explicitly in the Phase 0 status doc rather than papering over it.

---

## Patch 3 — Horizon grid, stated once (Section 3)

**Problem:** The plan mentions fixed horizons 5/10/20 for the target variable, then separately says local projections run over "a grid (e.g. h = 1…20)." The build prompt inherited both, unreconciled — an implementer would either build two grids or silently pick one.

**DEFAULT (confirm or override):** One grid: **h = 1…20 trading days**, used for both target computation and local-projection lag detection. Report headline/summary numbers at h = 5, 10, 20 for interpretability if useful, but that's a reporting choice, not a second computation grid.

---

## Patch 4 — "Quantum autocorrelation function," not "quantum-inspired" (Section 3, tertiary cross-check)

**Problem:** The plan deliberately uses the precise physics term "quantum autocorrelation function" so the skip condition — "no established, validated application to classical financial return series" — has a clear, checkable answer (no). The build prompt softened this to "quantum-inspired," a much looser term that's almost always satisfiable by construction, which quietly defeats the skip condition it's paired with.

**Fix:** Use the plan's original term — **quantum autocorrelation function** — consistently in any build prompt or code, not "quantum-inspired." Also: **remove it from any "Definition of Done" list.** Listing it there, even parenthesized as optional, creates delivery pressure to build something just to check the box. It should be genuinely optional/absent, not a soft deliverable.

---

## Patch 5 — Stage 2's underlying exposure (Section 4)

**Problem:** "Minimize cost subject to a minimum protection threshold" presupposes a position to protect, and the plan never says what that position is. Left unstated, the implementer will invent an assumption and bake it into code.

**DEFAULT (confirm or override):** Stage 2 assumes an **existing long-equity holding in the peer name** being protected — this matches Section 1's own framing ("protective option structures," "hedging trigger") rather than a standalone directional long-vol trade. State this explicitly in Section 4 rather than leaving it implicit.

---

## Patch 6 — Two additional required tests (Section 5 / build-prompt test list)

- **Negative control (Superseded by Patch 10 — do not use this wording; see below):** ~~a synthetic fixture with **zero injected anchor→peer effect** must produce a non-significant LP peak (post multiplicity-correction) and a `False` result on both the placebo test and the N-gate.~~ This conflated sample-size adequacy with effect significance — a zero-effect fixture with ample N should *pass* the N-gate, not fail it. Patch 10 below replaces this with two separate fixtures. Left here struck through, not deleted, so the correction is visible in-line rather than silently vanishing.
- **Residualization-leakage test:** assert that anchor-adjacent windows are genuinely excluded from each peer's own-earnings-cycle baseline fit (not just documented as excluded), and have the pipeline report **retained-history fraction per peer**. A peer linked to several quarterly-reporting anchors could have most of its history excluded from baseline estimation — peers below a stated retained-history threshold can't get a reliable baseline at all. This is a universe constraint in the same category as the options-coverage audit and should be reported alongside it, not discovered later.

---

## Patch 7 — Build sequencing within Phase 0 (build-prompt only, not a plan-doc change)

**Problem:** As scoped, one build pass produces the package, the audit, the residualized target, LP with clustered SEs, prewhitened CCF, the experimental module, ridge/lasso, LOOCV, the placebo test, ICC/N-gate, Stage 2, six test modules, a CI-wired smoke test, a Colab notebook, and VS Code scaffolding, in one shot — with the same pass writing the statistically load-bearing code (residualization baseline, clustered SEs, ICC) and its own tests. That's the likely-wrong-and-hardest-to-catch part of the whole build.

**Fix (sequencing, not a plan-doc patch):** Within Phase 0, build in this order:
1. **Synthetic-fixture generator** first, as its own deliverable — known injected lag, known effect size, known cluster structure. This is what Patch 6's negative-control and leakage tests validate against.
2. **Audit + target + residualization**, validated against that fixture.
3. **Inference layer** (LP + clustered SEs, prewhitened CCF cross-check, ridge/lasso, LOOCV, placebo, ICC/N-gate), validated against the same fixture.

This keeps the inference code from being validated mostly against itself.

---

## Patch 8 — Audit call budget (build-prompt only)

The coverage-availability audit (checking historical options-chain coverage for every candidate peer) makes real provider calls across the full peer universe — the one Phase 0 step that costs money and can hit rate limits. Add: **local caching of all provider responses, a stated maximum call budget per run, and a loud failure (not a silent universe truncation) if the budget is hit.**

---

## Patch 9 — Realized-volatility estimator, explicitly defined (Section 3)

**Problem:** The plan specifies horizons and residualization but never says how realized vol is actually computed at each h. This is load-bearing — cumulative RV over [t+1, t+h], trailing k-day RV at t+h, and range-based estimators (Parkinson, Garman-Klass) behave differently and would produce materially different results. Left unstated, the implementer invents one. Relatedly, h = 1 is in the grid, and a one-day RV is essentially a single squared return — too noisy on its own to carry a target unless the estimator definition handles that gracefully.

**Round 3 correction — the version below fixes a blocking bug in the original Patch 9.** That version defined RV(h) = √(Σr_i²) over [t+1,t+h] with no division by window length. Under constant daily vol σ, E[RV(h)] ≈ σ√h, so "raw target = RV(h) − reference(20-day)" carries a deterministic √h-shaped trend with zero actual volatility content — e.g. ≈ −2.24σ at h=5, ≈0 at h=20, purely from window-length arithmetic. That's exactly the shape a lag profile exists to detect, so the unnormalized version would have manufactured a fake signal. Earnings-cycle residualization (indexed on days-to-the-peer's-own-earnings, a different index from h) cannot absorb an h-indexed artifact — it doesn't rescue this.

**DEFAULT (confirm or override) — corrected:**
- **RVar(h) = (1/h)·Σ r_i² for i = 1..h** (mean squared daily log return over [t+1, t+h] — a variance, not a volatility; no square root). This is unbiased for σ² at every h, unlike a square-rooted version, which carries a Jensen's-inequality downward bias that itself shrinks with h (worst at h=1: E|r| ≈ 0.80σ vs. the true σ).
- **Reference**: RVar_ref = (1/20)·Σ r_i² over the trailing 20 trading days ending at the anchor's earnings date (t=0) — same normalized construction, so it's already on a per-day basis.
- **Raw target = log(RVar(h)) − log(RVar_ref)** — a log-variance ratio ("log abnormal volatility"), not a raw difference. This removes both the window-length scale artifact and the Jensen bias, stabilizes variance across the grid, and matches standard realized-volatility literature practice (log RV/RVar is used specifically because it has better distributional properties than raw RV). Earnings-cycle residualization is then applied on top of this log-ratio raw target, as originally specified.
- **Still true after this correction**: RVar(h) is a mean over an expanding window [1,h], so adjacent horizons remain highly overlapping/correlated by construction even after normalizing — β_h is still mechanically autocorrelated across the grid. This is why permutation-based max-T (not Bonferroni) remains the correct multiplicity correction, and why the multiplicity target should be derived empirically rather than assumed (see Patch 2 addendum below) — the normalization fix changes the scale, not the cross-horizon correlation structure.

---

## Patch 10 — Split the negative-control test into two fixtures (Section 5 / build-prompt tests)

**Problem:** The original Patch 6 asked a zero-effect synthetic fixture to produce a `False` result on **both** the placebo test and the N-gate. The placebo half is correct. The N-gate half is wrong — the gate measures whether the sample is large enough, not whether an effect exists. A zero-effect fixture with ample observations should *pass* the N-gate; that's the gate working correctly, not a failure to catch. As written, this test either fails against a correct implementation or pressures the implementer into wiring effect size into the gate, which would be a real bug.

**Fix — two separate fixtures, not one:**
- **Fixture A (zero effect, ample N):** LP peak non-significant post multiplicity-correction; placebo test shows no real-vs-random separation; **N-gate (N_eff-based) passes.** Confirms the gate correctly ignores effect size.
- **Fixture B (insufficient N, any effect size):** N-gate returns `False`, independent of whatever effect is injected. Confirms the gate is sensitive to sample size specifically.

---

## Patch 11 — Linkage map needs an as-of date (Section 8)

**Problem:** Section 8 asks the supply-chain teammate for "ticker pairs + relationship type + confidence" — no date field. A map built today encodes relationships known *today*; applying it to historical anchor events without knowing when each relationship was first established or publicly known is look-ahead bias. This is the same class of problem this project's own forensic audit already found in the GST z-score history (data reconstructed with present-day access, not provably identical to real-time observation). Retrofitting a first-observed date onto the map after it's built is far more expensive than requesting the column up front.

**Fix:** Add to the Section 8 ask: a **first-known/established-as-of date** per linkage pair, alongside relationship type and confidence. Get this in front of the teammate before the map is finalized, not after.

---

## Patch 12 — `min_bucket_count` design decision (Section 3, earnings-cycle residualization)

**Problem:** Estimating each peer's own unconditional volatility-vs-days-to-its-own-earnings baseline requires bucketing days-to-earnings and averaging within each bucket. Peers with thin history, or peers whose history is heavily consumed by anchor-adjacent exclusions (Patch 6's residualization-leakage test), can produce under-populated buckets. Surfaced during implementation as `min_bucket_count` — the minimum observation count a bucket needs before its average is trusted — with three options on the table: (a) widen buckets, (b) lower the minimum count, (c) accept and report (exclude observations relying on an under-populated bucket, flag the fraction excluded). Correctly flagged as a decision that shouldn't be made by whichever option happens to make the N-gate pass.

**DEFAULT (confirm or override): (c), accept and report.**

(a) is the worst of the three on validity grounds, not just the most conservative to avoid — the whole reason the plan residualizes against days-to-own-earnings is to isolate the universal pre-earnings vol ramp (Section 3's own stated rationale for abandoning the original variable-window design). Widening buckets blurs resolution exactly where that ramp is steepest, reintroducing the confound residualization exists to remove. (b) keeps resolution but degrades baseline reliability specifically for the thin/small-cap peers this hypothesis cares about most (Section 1) — the same failure mode the leakage test already exists to catch, approached from the input side instead of the output side. (c) is the only option that doesn't trade validity for sample size, and matches this doc's existing pattern (retained-history-fraction reporting, "don't round up," provisional-placeholder labeling).

**Implementation:** peer-anchor-horizon observations whose relevant days-to-earnings bucket falls below `min_bucket_count` are treated as missing — excluded from the Stage 1 regression sample, not imputed or forced. Report the excluded fraction in the status doc as its own number, distinct from the leakage test's retained-history-fraction (that's about anchor-adjacent history excluded from baseline *estimation*; this is about bucket population once that history is in hand). Fix bucket width and `min_bucket_count` before looking at how many observations survive — choosing either after seeing the resulting N is the same after-the-fact tuning this patch exists to prevent.

---

## Patch 13 — Options-coverage audit: real calls need an explicit, staged go-ahead (Section 3 / build sequence)

**Round 5 correction:** this patch originally assumed the audit hits a paid, metered provider (mirroring HYP-01's real-quote validation via QuantConnect) and framed the staged go-ahead entirely around a dollar budget. The stage-1 canary (10 tickers, run 2026-08-17) revealed this assumption was wrong for this specific check: the implementation uses yfinance against Yahoo's free, unauthenticated endpoint — $0.00 cost regardless of volume, confirmed at 20/20 calls with zero billing. The staged-consent principle below is still correct and still needed, but the constraint it should be sized against is **rate-limiting and provider fragility, not money** — this project has already been burned once by this exact provider (a 2026-08-04 crumb-negotiation failure). Don't carry the dollar-budget framing forward if this audit is ever pointed at a genuinely metered provider later (e.g. once real historical options-chain data is needed, which yfinance doesn't serve at all — see the caveat below) — re-derive the right constraint for whatever provider is actually in use rather than assuming either framing by default.

**Problem:** The data-availability audit makes real calls against a peer-coverage-checking provider, across the full candidate peer universe. The build prompt requires caching and a stated call budget, but real-world sizing depends entirely on what constraint actually binds for the provider in use (cost, rate limit, or both) — that has to be established empirically (as the canary did), not assumed from a different provider's characteristics (as the original version of this patch did).

**Process (still staged, now correctly framed):**
1. **Canary batch first**: authorize a small, hard-capped run (e.g., 5–10 candidate peer tickers) before the full universe. Establishes which constraint actually binds — cost, rate-limiting, both, or (as it turned out here) neither in the cost dimension — before committing to the full run.
2. **Extrapolate, then authorize the full run**: size the full run against whatever the canary actually revealed. For a free/rate-limit-bound provider (this case): extrapolate call volume and wall-clock time, add pacing/delay between calls as insurance against a provider with known fragility, and proceed once volume and pacing are stated explicitly — no dollar cap needed. For a paid/metered provider: extrapolate real cost-per-call as originally specified, and set an explicit dollar cap, enforced by failing loudly rather than silently truncating.

**Important limitation surfaced by the canary, not previously anticipated:** yfinance serves current option chains only — it has no historical endpoint. A 100%-current-coverage result does **not** establish that IV is viable as a Stage 1 target; the plan's actual question (usable *historical* options data, far enough back) remains unanswered by this specific check. This is the same limitation that made realized volatility the default target in the first place (Section 3) — the audit confirms current-chain existence as a first-pass sanity check, but does not and cannot promote IV to a secondary target on its own. If historical options-chain coverage is ever checked against a different, genuinely historical-data provider, re-apply this patch's staged process fresh rather than assuming the yfinance canary's cost/rate-limit findings carry over.

This go-ahead has to come from the repo owner directly before the audit's first live run, at both stages — regardless of which constraint ends up binding.

---

## Patch 14 — Build-session handoff file (process, not methodology)

**Round 4 correction:** the original version of this patch pointed Claude Code at `claude/session-handoff-2026-08-17.md` as a style exemplar. That path doesn't exist in the target repo — it's a project-context document visible only in this planning conversation, not a file that was ever committed to `gst-earnings-signal-research`. Rather than ask for an unrelated (and largely irrelevant — most of that document concerns a GitHub-connector access saga, not build continuity) document to be committed just to serve as an example, the style is described directly below, self-contained. No external file dependency.

**Problem:** This build is large enough (fixture generator, audit with a two-stage consent gate, residualized target, two-way-clustered LP inference, CCF cross-check, Stage 2, six-plus test modules, CI, notebook, VS Code scaffolding) that a single Claude Code session may run into its usage/context limit mid-build. Without an explicit handoff step, a session cut off mid-step leaves the next session to reconstruct state from a partial diff.

**Requirement:** Claude Code writes a dated **build handoff file** — `Live Signal Engine/HYP04_PHASE0_BUILD_HANDOFF_<date>.md` — at two triggers:
1. **Proactively**, at the end of each build-sequence step (1, 2, 3, 3b, 4, 5) — a natural checkpoint, not just a crisis measure.
2. **Reactively**, as soon as usage/context is running low mid-step — with margin to actually finish writing it. A handoff attempted only after the limit is already exhausted can't be written at all, so this has to trigger before the hard cutoff, not at it.

**Contents**, self-contained (no external exemplar file — describe the style directly):
- Which build-sequence steps are complete, in progress, or not started, and exactly what's unfinished in the in-progress one.
- File/module state: what exists, what's stubbed vs. finished, what's untested.
- Test status: which tests pass, which are failing, which aren't written yet.
- Any open decisions still awaiting the repo owner's sign-off (audit go-ahead stage 1 or 2, or anything else not yet confirmed) — don't let a pending consent gate get silently dropped across a session boundary.
- The single next concrete action for whoever (or whichever fresh session) picks this up.
- A pointer back to the three authoritative docs (plan, this edits doc, the build prompt) rather than re-summarizing their content.

**Distinct from item 5's Phase 0 feasibility status doc**: that doc reports Phase 0's methodological results once the pipeline runs end-to-end. This handoff doc is purely about *build-process* continuity and should exist even if Phase 0 isn't finished yet — don't conflate the two or let one substitute for the other.

---

## Patch 15 — Local-projections "peak" ≠ "onset" under an expanding-window target (Section 3, Lag detection method)

**Problem:** The plan states "the horizon where [β_h] peaks and clears significance is the estimated lag" — this conflates peak with onset, and implementation testing (6/6 across tested (L,W) combinations) confirmed the conflation produces the wrong number. Because the target (Patch 9's log(RVar(h))) is an **expanding-window mean** from day 1 to day h, not a marginal/instantaneous measurement, its value rises monotonically through a rectangular elevated-response block [L, L+W−1] — each newly-included elevated day pulls the running mean up — and falls monotonically afterward, as newly-included baseline days pull the mean back down. So argmax_h β_h lands exactly at h = L+W−1, the **end** of the reaction window, not h = L, the onset. This is a direct consequence of averaging over an expanding window, not an estimation artifact, and it reproduces on any rectangular-response fixture.

**Consequence:** Stage 2 sizes hedge tenor off "the lag." Reading peak_horizon as onset_horizon would size tenor (W−1) days too long and start the hedge (W−1) days too late — positioned to arrive after the reaction window it's meant to protect against has already closed.

**Fix:** report `onset_horizon` and `peak_horizon` as two distinct quantities, not one. `peak_horizon` (argmax β_h) remains useful — combined with a separately-estimated onset it gives the window width W — but Stage 2's tenor sizing must read from `onset_horizon` specifically, not peak.

**Confirmed against implementation** (`hyp04_supply_chain_hedge/inference.py::local_projection_analysis`): `onset_horizon` = the first horizon, reading forward from h=1 in ascending order, whose |t_h| exceeds the max-T permutation critical value (empirical 95th percentile of the permuted max-|t| distribution). Matches the default proposed above, plus two specifics this patch didn't originally state:
- **The threshold is the multiplicity-corrected max-T value, not a per-horizon one.** Onset inherits the same family-wise error control as peak — reading it off an uncorrected per-horizon threshold would reintroduce the multiplicity problem max-T exists to solve, and would bias onset early (a false-positive risk, not just a timing one).
- **Onset is gated on peak clearing first.** If the overall max-T test doesn't clear significance, `onset_horizon` is `None` — there's no path where an onset gets reported while the profile as a whole is non-significant.

**Known residual bias, smaller than the bug this patch fixes but real: onset is diluted, not exact.** At the true onset horizon L itself, only 1/L of the expanding-window average reflects the elevated period — the same expanding-window mechanism this patch already describes, showing up at the other end of the window. That dilution shrinks the measured |t_L| specifically at the true onset (more so for larger/later L), so on noisier draws the true onset horizon can just miss the corrected threshold and get caught one or two horizons later instead. Measured empirically: |t| at h=L was 5.58 (L=3), 3.53 (L=5), 3.98 (L=8), 4.69 (L=10) against a critical value near 2.6–2.9 — comfortable margin in general, but one L=8 draw measured |t|=2.08 at h=8 and reported onset=9. The error is one-sided (h<L measured |t|=0.71 on that same draw — never early, only late), so it's not a false-positive risk, but late onset still means short tenor and a late hedge, the same practical failure this patch exists to prevent, just smaller in magnitude. Report `onset_horizon` with this caveat rather than as an exact point estimate — the test suite already reflects this, asserting `L ≤ onset_horizon ≤ L+2` with "never earlier than L" as the hard invariant, not exact equality. This is also the statistical basis for Stage 2's `R4_lag_ci_too_wide` rule declining to size a position when lag uncertainty is too high, rather than acting on an onset estimate that isn't precise.

---

## Patch 16 — HYP-04 confirmed unclaimed; registry entry is a governed act, not a rename (naming)

**Confirmed against `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json` directly, not just the README:** HYP-02 ("cross-source attention divergence and earnings surprise" — Google-search vs. Wikipedia divergence against disclosed surprise) and HYP-03 ("post-earnings attention decay and continued repricing") are both real, registered, unrelated hypotheses — status `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` on both, meaning the IDs are reserved and dated even though no code occupies them yet. That's precisely what made the original `hyp02_*` naming a real collision risk, not just an awkward label — it would have looked unclaimed while actually overwriting a registered hypothesis's identity. A full repo sweep confirms **HYP-04 is genuinely unclaimed.** This doc, the plan doc, and the build prompt have been renamed throughout to HYP-04 — this was previously drifting because Claude Code was manually renaming on every install from a source set still named HYP-02; fixed at the source now.

**What renaming doesn't do: register the hypothesis.** The registry states HYP-02 and HYP-03 may never be promoted to confirmatory on the basis of observed results, and that promotion requires a new dated registry version written *before* the results that would motivate it are seen. That specific rule is about promotion, not addition, but it establishes the operating norm for this registry: changes are dated, versioned, and written before the evidence that would motivate them — not after. Adding HYP-04 should follow the same discipline: a dated registry version, authored by a human (not written unilaterally by an implementer), declaring HYP-04's question, class, and n-threshold, before Phase 1 produces anything. **This has not happened yet and is not something to resolve inside this edits doc** — it's a registry action, separate from the build-plan patches above.

**Two decisions to make when that registry entry gets written, not before:**
1. **Class.** HYP-01 is this project's sole primary confirmatory hypothesis. HYP-04 would presumably register as exploratory, at least initially — it currently has no real linkage map and no real-data result, only a placeholder-linkage feasibility pipeline.
2. **The options tension.** The registry currently has no registered options hypothesis, and both options-eligibility classes carry `DENY_NO_REGISTERED_HYPOTHESIS`. HYP-04's Stage 2 is options-adjacent by construction (protective put/spread/collar selection). Phase 0 sidesteps this cleanly — realized vol is the target, Stage 2 only constructs recommendations, nothing options-eligible actually executes — but registering HYP-04 surfaces this tension explicitly, and it's better resolved deliberately at registration than discovered later at Phase 4 when Stage 2 would actually need options eligibility to mean something.

**Not blocking:** neither of these blocks the Phase 0 work already built and tested — that's all feasibility on synthetic fixtures and a placeholder linkage, nothing that touches the registry's promotion or options-eligibility rules yet.

---

## Summary of defaults requiring confirmation before this is treated as locked

1. Prewhitening: fit filter to peer-vol series, apply to both — **not** anchor shock series, **no** double-prewhitening fork.
2. N-gate: N_eff = N_pairs / (1 + (m̄−1)·ICC), gated at a target derived empirically from the fixture's own max-T permutation (190–240 is a **provisional pre-fixture placeholder only**, likely revising toward 150–190) — plus Satterthwaite dof reported alongside N_eff since two-way clustering makes DEFF's single-dimension assumption optimistic, plus cluster count/bootstrap interval behind the ICC estimate reported for transparency.
3. Target definition: single grid, h = 1…20, with the target as **log(RVar(h)) − log(RVar_ref)** — RVar(h) = (1/h)Σr_i² (mean squared return, not cumulative sum, not square-rooted) — trailing-20-day reference, same construction. Not the earlier unnormalized RV(h) = √(Σr_i²), which carried a deterministic √h artifact with no volatility content.
4. Term: "quantum autocorrelation function," dropped from Definition of Done.
5. Stage 2 exposure: assumed existing long-equity peer holding.
6. SE clustering: anchor event × calendar period (two-way) if the existing CR2/Satterthwaite machinery generalizes; otherwise flagged as a stated limitation, not silently one-way.
7. Negative-control tests: two separate fixtures (zero-effect/ample-N passes the gate; insufficient-N fails the gate regardless of effect) — Patch 6's original single-fixture wording is superseded, not just supplemented.

8. `min_bucket_count`: accept-and-report — exclude under-populated-bucket observations, report the excluded fraction; do not widen buckets or lower the threshold to make the gate pass.
9. Options-coverage audit: staged go-ahead (canary batch → extrapolated full-run budget), not a blanket authorization or an unbounded run — this one requires the repo owner's sign-off directly, not a default I can set.

10. Lag reporting: `onset_horizon` (what Stage 2 needs for tenor sizing) reported separately from `peak_horizon` (argmax β_h, which lands at the end of the reaction window under an expanding-window target, not the start) — the plan's original wording conflated the two.

None of these are locked in the preregistration sense yet — this is a Phase 0 build-plan revision, not the Phase 2 lock document — but per this project's own convention, they shouldn't be silently carried forward into code without being stated as decisions first.
