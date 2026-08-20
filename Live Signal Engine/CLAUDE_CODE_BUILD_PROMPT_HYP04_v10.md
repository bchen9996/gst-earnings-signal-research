# Claude Code build prompt — HYP-04 Phase 0 (v10: renamed from HYP-02, confirmed against the registry)

Changes from v9: renamed throughout from HYP-02 to HYP-04. Verified directly against `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json` (not just the README): HYP-02 ("cross-source attention divergence and earnings surprise") and HYP-03 ("post-earnings attention decay") are real, already-registered, unrelated preregistered hypotheses with status `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` — meaning the IDs are reserved but the code namespace was unoccupied, which is exactly what made the original `hyp02_*` naming dangerous rather than just wrong. HYP-04 is confirmed genuinely unclaimed. This file (and the plan and edits docs) are the source set — Claude Code was manually renaming on every install from here; fixing it at the source instead.

Changes from v9 (carried forward): fixed a broken exemplar-file citation in the handoff-file feature (Patch 14) — no external file dependency.

Changes from v7 (carried forward): added the build-session handoff file requirement itself, at both proactive (per build-sequence step) and reactive (low-usage) triggers.

Changes from v6 (carried forward via v7): `min_bucket_count` resolved as accept-and-report; options-coverage audit requires a staged go-ahead (canary batch, then extrapolated full-run budget) from the repo owner directly.

Changes from v5 (carried forward): fixed a build-sequence circularity (step 1 was asked to run machinery step 3 builds); added a log(0) floor and an ICC floor at 0.

Changes from v4 (carried forward from v5), per the round-3 corrections in `HYP04_PLAN_ROUND2_EDITS.md`: **blocking fix** — target is now log(RVar(h)) − log(RVar_ref) with RVar(h) = (1/h)Σr_i², replacing an unnormalized RV(h) = √(Σr_i²) that carried a deterministic √h artifact with no actual volatility content. Also: Satterthwaite dof reported alongside N_eff; the multiplicity target is derived empirically rather than assumed; ICC cluster-count/bootstrap-interval reporting added for transparency.

## Usage note

1. Drop `HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md` into the repo at `Live Signal Engine/`. (Superseded as of 2026-08-19: this step previously installed `MODEL_PLAN_v0.1_DRAFT.md` *and* `HYP04_PLAN_ROUND2_EDITS.md`. v0.2 merges both and is self-contained; the other two are historical records and are not needed to build.)
2. Open Claude Code with working directory set to the local clone of `gst-earnings-signal-research`.
3. Paste the prompt below as the first message.
4. Scoped to Phase 0 only — placeholder linkage, no real capital logic, no result claims.

---

## The prompt

You're working inside the `gst-earnings-signal-research` repo. Before doing anything, read `Live Signal Engine/HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md` in full. **That one document is the whole plan** — as of 2026-08-19 it is self-contained and authoritative on its own. `MODEL_PLAN_v0.1_DRAFT.md` and `HYP04_PLAN_ROUND2_EDITS.md` are **superseded historical records; do not implement from either.** All 16 patches are merged into v0.2, whose §0 maps each patch number to where it landed. The old instruction — read both docs and apply a "Round N correction" marker convention to work out which text governs — is retired, along with the drift risk it carried. Also skim `gst_market_response/` (package/CLI conventions), a `Live Signal Engine/` HYP-01 lock doc (documentation/locking style), and 2-3 root `test_market_response_*.py` files (testing conventions). Match this project's existing rigor and naming style.

### Scope: Phase 0 only

Placeholder linkage (same-sector peers, same limitation as `GST_Task2_PeerDivergence.py`) since the real supply-chain map doesn't exist yet — label it clearly everywhere. Do not implement Phases 1-4.

### Build sequence within Phase 0 (do not skip ahead)

1. **Synthetic-fixture generator**, as its own deliverable: known injected lag, known effect size, known cluster structure across anchor events and peers, plus the two zero/insufficient-effect variants (test item 4 below). **Structural only at this stage — do not run the max-T permutation here; the machinery it needs doesn't exist yet (see 3b).**
2. **Data-availability audit + target computation + earnings-cycle residualization**, validated against the fixtures from (1).
3. **Inference layer**: local projections with two-way clustered SEs, Satterthwaite dof, prewhitened CCF cross-check, ridge/lasso Link-Strength model, leave-one-anchor-out CV, placebo test — built and unit-tested against the fixtures from (1).
3b. **Diagnostic run**: now that step 3's max-T permutation machinery exists, execute it against the step-1 fixture, back out the effective-independent-horizon-test count, and use it to finalize the N-gate's multiplicity target (see the gate bullet under Stage 1 below). This step could not run earlier — it depends on code that step 3 builds.
4. Stage 2 rules engine.
5. Smoke test, Colab notebook, VS Code scaffolding, status doc.

**Write a build handoff file after each of the steps above** (see "Session continuity" below) — this is a checkpoint at every step boundary, not just a fallback for running out of usage mid-build.

### Session continuity (build handoff file)

This build is large enough that a single session may run into its usage/context limit mid-build. Write a dated **build handoff file** at `Live Signal Engine/HYP04_PHASE0_BUILD_HANDOFF_<date>.md`. (No external exemplar file to reference for this — describe it self-contained, per the contents below.)

**Write it at two triggers:**
1. **Proactively**, at the end of each build-sequence step above (1, 2, 3, 3b, 4, 5) — a routine checkpoint, not just a crisis measure.
2. **Reactively**, as soon as usage/context is running low mid-step, with enough margin to actually finish writing it — a handoff attempted only after the limit is already hit can't be written at all, so trigger before the hard cutoff, not at it.

**Contents:**
- Which build-sequence steps are complete, in progress, or not started, and exactly what's unfinished in the in-progress one.
- File/module state: what exists, what's stubbed vs. finished, what's untested.
- Test status: passing, failing, not-yet-written.
- Any open decisions still awaiting the repo owner's sign-off — in particular, don't let a pending audit go-ahead (canary or full-run stage) get silently dropped across a session boundary.
- The single next concrete action for whoever picks this up.
- A pointer back to the two authoritative docs (plan v0.2 and this build prompt) rather than re-summarizing their content. (Was three; the edits doc was merged into v0.2 on 2026-08-19.)

This is distinct from item 5's dated Phase 0 feasibility status doc below — that one reports methodological results once the pipeline runs end-to-end. This handoff doc is about build-process continuity and should exist even mid-build, before Phase 0 is finished.

### What to build

1. New package `hyp04_supply_chain_hedge/`, structured like `gst_market_response/`.

2. Stage 1 pipeline:
   - **Data-availability audit first**: for every candidate peer ticker, check historical options-chain coverage via the same provider used for HYP-01. Default target = realized volatility (full-universe coverage); promote IV to secondary/robustness target only for the subset with confirmed clean coverage, reported before that call is made. **Bound this step, and stop before the first live call**: cache all provider responses locally, and do not run against real data until the repo owner has given an explicit go-ahead in two stages — (1) a small hard-capped canary batch (e.g. 5–10 tickers) to establish real observed cost-per-call, then (2) an extrapolated, explicitly-stated budget cap for the full candidate universe, derived from the canary's real numbers rather than assumed. Fail loudly (not a silent universe truncation) if either cap is hit. Do not pick a budget number yourself or proceed without both go-aheads.
   - **Target variable, explicitly defined — this is the one place a previous version of this prompt had a real bug, so implement exactly as follows:**
     - Single grid, h = 1…20 trading days post-anchor-earnings.
     - **RVar(h) = (1/h) · Σ r_i² for i = 1..h** — mean squared daily log return over [t+1, t+h]. This is a variance (no square root), unbiased for σ² at every h.
     - **RVar_ref = (1/20) · Σ r_i²** over the trailing 20 trading days ending at the anchor's earnings date (t=0), same construction.
     - **Raw target = log(RVar(h)) − log(RVar_ref)** — a log-variance ratio, not a raw difference and not a square-rooted quantity. **Floor before taking the log**: `log(max(RVar(h), ε))` for a small ε (and the same floor on RVar_ref) — a day with an exact zero return (halted trading, stale/bad data) sends RVar(h) to exactly 0 at h=1 without this, and log(0) is −∞. Apply the same floor in both the fixture and the real-data pipeline so behavior matches. Do **not** implement RV(h) = √(Σr_i²) without normalizing by h — that version has a deterministic √h-shaped artifact with no volatility content (verify against the fixture: under constant-vol synthetic data with zero injected effect, the target series should show no systematic trend across h; if it does, the normalization is wrong).
     - Apply **earnings-cycle residualization** on top of this log-ratio raw target (subtract each peer's own unconditional vol-vs-days-to-its-earnings baseline, estimated excluding anchor-adjacent windows) to get the final abnormal-vol target. **Bucket population (`min_bucket_count`)**: fix the days-to-earnings bucket width and a minimum observation count per bucket before looking at results. Peer-anchor-horizon observations whose relevant bucket falls below `min_bucket_count` are **excluded from the Stage 1 regression sample, not imputed, and not fixed by widening buckets or lowering the threshold after the fact** — report the excluded fraction in the status doc as its own number, separate from the leakage test's retained-history-fraction below.
     - Note in code comments: RVar(h) is a mean over an expanding window, so adjacent horizons remain correlated by construction even after normalizing — β_h is still mechanically autocorrelated across the grid, which is why permutation-based max-T (not Bonferroni) is correct, and why the multiplicity target is derived empirically (see below) rather than assumed.
   - Feature computation per the plan (anchor shock magnitude, correlation/beta placeholder, relationship-type placeholder, coverage/thinness proxy, days-until-peer-earnings).
   - **Lag detection, primary: local projections** (Jordà-style) over h = 1…20 — regress residualized abnormal vol at each horizon h on anchor shock magnitude + controls. **SEs clustered two ways: anchor event × calendar period** (week or quarter), reusing the CR2/Satterthwaite code already R-validated for HYP-01 if it generalizes to multiway clustering (Cameron-Gelbach-Miller); if it does not straightforwardly generalize, implement one-way (anchor event) clustering and explicitly flag two-way clustering as a stated Phase 0 limitation. **Report the Satterthwaite degrees of freedom** from the CR2 estimator alongside N_eff (see gate below) — it's a byproduct of the regression, already validated, and it reflects the actual clustering structure used in inference in a way the gate's DEFF formula (single clustering dimension) does not. Apply a **max-T / permutation-based multiplicity correction** across the 20-horizon grid before calling any peak "significant" — this is the same machinery step 3b runs against the fixture to derive the N-gate's multiplicity target, so build it once here and reuse it in 3b rather than duplicating the permutation logic.
   - **Secondary cross-check: prewhitened CCF, single filter, no fork.** Fit the whitening filter (ARMA or GARCH) to the **peer's realized-volatility series** — not the anchor shock series, which is a sparse quarterly point process already close to white noise. Apply that **same single filter to both series** before cross-correlating. No double-prewhitening option — different filters on each series would bias the estimated lag even though significance testing would remain technically valid, and lag identification is this cross-check's entire purpose. **Do not use Bartlett confidence bands** — use a circular-shift permutation of the anchor event dates instead. Log agreement/disagreement vs. local projections.
   - **Tertiary, experimental, non-load-bearing**: an optional **quantum autocorrelation function** variant (use this exact term, not "quantum-inspired"), isolated module, never feeds into any decision or conclusion. Skip it and say so explicitly if there's no well-defined, citable construction for applying the real physics construct to classical return series (there almost certainly isn't). Do not list this item in the Definition of Done even as "(if built)."
   - Regularized regression (ridge/lasso, not tree-based/deep) for the Link-Strength score.
   - Leave-one-anchor-out CV.
   - Placebo test (shuffled anchor-peer assignments), per `GST_Task1_PlaceboPermutationTest.py`'s pattern.
   - **Phase 0 sample-size gate — N_eff, empirically-derived multiplicity target, not assumed:**
     - Report **N_pairs** and **N_events** as the two bounds, estimate **ICC** empirically (report the **cluster count backing the ICC estimate**, and a **bootstrap interval** if feasible — ICC is unreliable with few clusters and a gate result riding on a noisy estimate should be visible, not implicit).
     - Compute **DEFF = 1 + (m̄−1)·ICC** and **N_eff = N_pairs / DEFF**. **Floor ICC at 0** before computing DEFF — ICC estimates can come out negative with small cluster counts (a known small-sample artifact), and an unfloored negative ICC would push DEFF below 1, making N_eff exceed N_pairs, which is backwards for what a design effect is supposed to represent. This floor is separate from the bootstrap-interval reporting above — report the raw (possibly negative) estimate for transparency, but use the floored value in the DEFF computation itself.
     - **Multiplicity target**: use the effective-independent-test count from step 3b's diagnostic run (not step 1 — that machinery doesn't exist until step 3) to compute the actual required N — do not hardcode 190–240. State 190–240 in the status doc explicitly as a **provisional pre-3b placeholder**, superseded by the step-3b-derived number once available. The naive single-test 126 should appear only as a labeled baseline, never as the operative gate.
     - Gate on N_eff against the fixture-derived target. Report the Satterthwaite dof alongside N_eff; where they diverge, note that the Satterthwaite dof is the more honest number since DEFF only captures one clustering dimension.
     - Report implied calendar coverage (~96–200 anchor events/year across a 24–50-ticker quarterly universe).
     - Record the two-sample-d-vs-continuous-LP-regression mismatch as a stated conservative proxy. Don't round up or reinterpret to make Phase 0 look passed.

3. Stage 2 rules engine: explicit, traceable decision function/constrained optimization, not a trained model. **Assumed exposure**: Stage 2 protects an assumed existing long-equity holding in the peer name — encode this assumption explicitly and visibly in code/docstrings.

4. Tests (pytest, `test_*.py`): target-variable computation incl. the exact log(RVar(h)) definition (assert no systematic h-trend under a constant-vol, zero-effect fixture — this is the direct regression test for the bug this version fixes) and residualization, local-projections logic (recovers a known injected lag on synthetic data; SEs actually clustered both ways or one-way-with-flagged-limitation; multiplicity correction actually changes the significance threshold vs. uncorrected; Satterthwaite dof is computed and reported), prewhitened-CCF correctness (filter fit to peer-vol series specifically, verify it is NOT fit to the anchor-shock series), leave-one-anchor-out split correctness, placebo test's own correctness, Stage 2 edge cases, PLUS two **separate** negative-control fixtures:
   - **Fixture A — zero effect, ample N**: LP peak non-significant post multiplicity-correction; placebo test shows no real-vs-random separation; **N_eff-based gate PASSES** (confirms the gate correctly ignores effect size).
   - **Fixture B — insufficient N, any effect size**: N_eff-based gate returns `False`, independent of injected effect.
   - **Residualization-leakage test**: assert anchor-adjacent windows are genuinely excluded from each peer's own-earnings-cycle baseline fit, and have the pipeline report retained-history fraction per peer; flag peers below a stated retained-history threshold as having an unreliable baseline.

4b. **Smoke test (required, separate from above)**: one end-to-end run of the full Phase 0 pipeline (ingest → audit → features → local-projections + CCF cross-check → Stage 1 model → Stage 2 decision → N_eff gate check) on a small fixed fixture, asserting completion + schema correctness only. Wire into CI.

5. Dated status doc in `Live Signal Engine/` (`HYP04_PHASE0_FEASIBILITY_STATUS_<date>.md`): coverage audit result + target used (+ both audit go-ahead stages and their actual observed/budgeted costs), pipeline runs end-to-end (y/n), **N_pairs, N_events, empirical ICC (+ cluster count, bootstrap interval), DEFF (ICC floored at 0), N_eff, Satterthwaite dof, fixture-derived multiplicity target (with 190–240 labeled as the superseded provisional placeholder), implied calendar coverage**, clustering approach used (two-way or one-way-with-limitation-flag), retained-history-fraction summary, **`min_bucket_count`-excluded-observation fraction (reported separately from retained-history)**, honest pass/fail assessment. No performance claim about the hedge strategy. If the real linkage map has arrived and lacks first-known/established-as-of dates per pair, flag this explicitly as a blocking data-quality issue for Phase 1.

### Colab notebook

Self-contained `.ipynb` (`notebooks/HYP04_Phase0_Colab.ipynb`): git-clone/pip-install first cell, explicit installs, walks through Phase 0 with markdown explanations, renders CV + placebo-test results inline, bannered as Phase 0/placeholder-linkage only.

### VS Code hosting

`requirements.txt`, `.vscode/settings.json` (interpreter/venv + pytest runner), `.vscode/launch.json` (debug config), `README.md` inside `hyp04_supply_chain_hedge/` (setup/tests/CLI/placeholder-linkage caveat).

### Non-negotiables

No real-capital/live-trading logic. No claim anywhere that a hedging edge has been found. Don't silently swap linkage source, model family, lag-detection method, prewhitening target, RV/RVar estimator, or N-gate formulation without flagging it. Match existing repo conventions.

### Definition of done

`hyp04_supply_chain_hedge/` package (synthetic-fixture generator incl. zero-effect/insufficient-N variants and max-T-derived multiplicity target; audit with call budget; residualized target using log(RVar(h)), correctly normalized; local-projections lag detection w/ two-way-clustered SEs, Satterthwaite dof, multiplicity correction; correctly-directed single-filter prewhitened-CCF cross-check with permutation-based significance; N_eff-based gate with empirically-derived target and ICC-stability reporting) + Stage 2 with stated exposure assumption, passing tests including the h-trend regression test, both split negative-control fixtures, and the leakage test; Phase 0 smoke test wired into CI and passing; Colab notebook runs top-to-bottom fresh; VS Code workspace ready to clone/open/run/debug; dated status doc with the full N_pairs/N_events/ICC/DEFF/N_eff/Satterthwaite-dof/multiplicity-target/calendar-coverage picture; **at least one build handoff file demonstrating the checkpoint pattern actually ran** (one per completed build-sequence step, at minimum). The quantum autocorrelation function module is explicitly out of scope for "done" — build it only if a citable construction exists, otherwise state in the status doc that it was skipped and why.
