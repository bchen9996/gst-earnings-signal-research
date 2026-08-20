# HYP-04: Supply-Chain Hedge-Lag Model — Build Plan (v0.1, DRAFT)

> # ⚠ SUPERSEDED BY v0.2 — HISTORICAL RECORD
>
> **As of 2026-08-19 this document no longer governs anything.** It is
> superseded by **`HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md`**, which
> merges in all 16 patches from `HYP04_PLAN_ROUND2_EDITS.md` and is
> self-contained.
>
> **Do not implement from this document.** Several decisions here are known to
> be wrong and were corrected in v0.2 — most consequentially §3's lag wording
> (peak is not onset) and the realized-volatility estimator, whose unnormalized
> form would have manufactured a fake signal. Retained unedited apart from the
> in-line correction markers already present, so the record of what was
> originally proposed stays inspectable.

**Status:** proposal / not yet preregistered. No data has been pulled for this hypothesis. Written to define the build sequence and the decision points that need to be locked before any real event is touched, consistent with this project's existing HYP-01 discipline.

## 1. What this model is for

Not a signal to trade the anchor stock's own options (that's the part of this project that has repeatedly failed real-quote validation). This model decides, for each ticker in a supply-chain/competitor basket tied to an anchor stock, two things:

1. **Link-Strength & Lag Score** — given a confirmed anchor earnings shock, how much (if at all) does this specific peer's volatility tend to move, and how many trading days does that reaction typically take to show up in the peer's own market.
2. **Hedge Structure Selection** — given that score plus the peer's own current options-market conditions, which protective structure (or none) is worth putting on, and how it's sized.

These are deliberately two separate stages. Stage 1 is the actual modeling problem. Stage 2 is closer to standard options-desk arithmetic and should stay simple and auditable rather than learned, for reasons covered in Section 4.

## 2. Data dependencies

| Need | Source | Status |
|---|---|---|
| Anchor tickers + confirmed historical earnings-day shocks | Already in repo (`Daily Excess Return Data*`, `GST Data`) | Available |
| Supply-chain / competitor / customer linkage per anchor, with relationship type | Supply-chain teammate's mapping | **Blocking — not yet available.** Sector-level proxy (`AllTickers_Sectors.csv`) exists but is not a real linkage map. |
| Peer tickers' own historical returns, volatility, options quotes | New pull needed (Alpaca/yfinance infra already exists in repo) | Buildable independently |
| Peer coverage/thinness proxy (search volume, analyst count, news volume) | GST + GDELT infra already exists | Buildable independently; benefits from data-validation teammate's calibration work on thin-volume tickers |
| Peer options liquidity, skew, term structure | New pull, same providers as HYP-01 | Buildable independently |
| Peer historical options chains (needed only if IV ends up the target — see Section 3) | Same providers as HYP-01's real-quote validation | **Availability unconfirmed for the full peer universe — must be audited in Phase 0 before the target variable is finalized, not assumed.** |

Only the linkage map is a hard blocker on real data collection. Everything else can be prototyped on a placeholder linkage (e.g., same-sector peers, same limitation as `PeerDivergence`) to validate the pipeline mechanics before the real map exists.

## 3. Stage 1 — Link-Strength & Lag model

**Target variable: realized vol vs. IV — decided by data availability, not preference.** Don't pick between "peer's realized volatility" and "peer's near-term put-implied vol" on theoretical grounds. Realized vol is computable for the entire peer universe from price data alone, which this repo already has. Peer IV requires clean historical options chain data per peer, and that coverage is unconfirmed — small-cap and thinly-covered supply-chain names (exactly the names this hypothesis is most interested in, per Section 1) are the ones most likely to have sparse or unreliable historical options quotes. So: **Phase 0's first task is a data-availability audit** — for every candidate peer ticker, check whether the same options-quote provider used for HYP-01's real-quote validation has usable historical chains far enough back, and record coverage %. Default target is **realized volatility**, usable for 100% of the universe. IV is promoted to a secondary/robustness target only for the subset of peers with confirmed clean coverage, and only if that subset is large enough to be worth a separate parallel analysis (a judgment call, but the coverage % itself must be reported before that call is made — don't decide first and check second). This decision procedure, and whatever coverage threshold the team sets, gets written into the Phase 2 lock document — it is itself a preregistered decision, not something to revisit after seeing which target "looks better."

**Target definition: fixed horizons + earnings-cycle residualization.** The original variable-length-window definition (anchor's earnings date to the peer's own next earnings date) has a real confound: window length varies across anchor-peer pairs, so it mechanically captures more baseline variance for pairs with a longer gap, and it overlaps with the peer's own pre-earnings vol ramp-up — every company's vol rises into its own earnings regardless of any anchor effect, so a window ending at the peer's earnings date will partly just be measuring that universal pattern, not anything anchor-specific. Replace it with:
1. **Fixed horizons**, not a variable window: compute the peer's realized-vol change over several fixed horizons after the anchor's confirmed earnings date (e.g. h = 5, 10, 20 trading days), rather than one window whose length depends on the calendar spacing of that particular pair.
2. **Earnings-cycle residualization**: before comparing to any anchor event, estimate each peer's own unconditional volatility pattern as a function of trading days until its own next earnings, using that peer's full history *excluding* anchor-adjacent windows so the baseline isn't contaminated by the very effect being measured. Subtract this expected baseline from the raw realized-vol change at each horizon — the target becomes the *abnormal* vol at that horizon, in the same spirit as this project's existing excess-return methodology, not the raw level.

**Candidate features** (per peer, per anchor event):
- Anchor shock magnitude (confirmed |excess return| or GST z-score, already validated in this project)
- Historical correlation/beta of peer to anchor (from linkage-mapping teammate, or a computed proxy in the interim)
- Relationship type: direct supplier/customer vs. sector competitor vs. loose sector neighbor — these likely have different diffusion speeds and should not be pooled without checking
- Peer coverage/thinness: search volume level, analyst count, news volume — proxy for how likely the market is to already be pricing the link
- Days between anchor's earnings and peer's own next earnings (the size of the exploitable window)

**Model choice.** Given a universe of roughly 24–50 anchor tickers and a peer basket likely similar in size, the number of independent (anchor event × peer) observations will be small — this is the single biggest risk to this stage. Favor a simple, regularized, interpretable model (ridge/lasso regression, or a basic hazard/survival model for the "days until lag closes" question) over anything tree-based or deep. A model that needs hundreds of parameters to fit will overfit this sample the same way the earlier IV-mispricing and Attention Spread work did.

**Lag detection method: local projections, primary; prewhitened CCF, cross-check.** A raw cross-correlation function has two real weaknesses for this use case: it can't condition on controls (sector/market beta, the peer's own earnings-cycle baseline) at each lag, so a "significant" lag can just be shared sector-wide movement rather than anchor-specific transmission, and it's vulnerable to spurious correlation when either series is itself autocorrelated (standard fix: prewhiten by filtering both series through a model fit to one of them before correlating — this is not optional if CCF is used at all). Rather than build around that weaker method, make the **primary lag-estimation method local projections** (Jordà-style): for each horizon h in a grid (e.g. h = 1…20 trading days), regress the peer's residualized abnormal vol at h on the anchor's shock magnitude plus controls, with standard errors clustered by anchor event — reusing the same cluster-robust SE machinery (CR2/Satterthwaite) already built and R-cross-validated for HYP-01 in `tools/hyp01_r_reference/`, rather than standing up a second inference method from scratch. The resulting β_h sequence directly gives an impulse-response profile with its own confidence bands, **(Superseded by Patch 15 — do not implement the struck wording; see `HYP04_PLAN_ROUND2_EDITS.md`.)** ~~and the horizon where it peaks and clears significance is the estimated lag.~~ Under Patch 9's expanding-window target, `argmax_h β_h` lands at the **end** of the reaction window (h = L+W−1), not at its onset (h = L) — implementation testing confirmed this on 6 of 6 tested (L, W) combinations. Report `onset_horizon` and `peak_horizon` as **two distinct quantities**, and size Stage 2's tenor off **onset**, never peak. Left struck through, not deleted, so the correction is visible in-line rather than silently vanishing. Keep a **prewhitened CCF as a secondary, classical cross-check** against the local-projections result (not the primary method) — if the two substantially disagree, that's a signal to investigate before trusting either, the same spirit as the **quantum autocorrelation function** cross-check described below. *(Corrected 2026-08-19 per Patch 4: this sentence previously read "quantum-inspired," the loose term Patch 4 exists to forbid — it is satisfiable by construction and defeats the skip condition it is paired with.)*

A note on "quantum autocorrelation functions," since it's come up as a possible addition: the term properly refers to quantum time-correlation functions from statistical mechanics (⟨A(0)A(t)⟩ for quantum operators, involving commutators and quantum ensembles) — a real construct in physics, but one with no established, validated application to classical financial return series, and no track record in finance the way CCF, GARCH, or standard lag-regression methods have. If the team wants to explore it anyway, it should be built as an **isolated, clearly-labeled experimental module** that runs *alongside* the classical CCF rather than replacing it — logging where the two methods agree or disagree — and, matching this project's own existing pattern of cross-validating novel statistical machinery against a trusted reference before it's allowed to influence anything (see `tools/hyp01_r_reference/`), it should not be permitted to affect any lock, gate, or hedge decision until it's been validated against the classical result on known cases. Treat it the same way the R cross-check treats the CR2/Satterthwaite estimator: a check on the primary method, not a replacement for it.

**Validation, matching this project's existing standards:**
- **Placebo test**: shuffle anchor-peer assignments (real peer vs. randomly assigned "peer") and confirm the real linkage produces a materially different result than random pairing. If it doesn't, the model has nothing to learn regardless of algorithm.
- **Leave-one-anchor-out cross-validation**, not random k-fold — anchor events cluster in time and by sector, so random folds would leak information across correlated events.
- **Preregister the target definition, feature list, and validation split before pulling any real peer options data**, the same way HYP-01 locked its model before prospective data collection. A short lock document should exist before Phase 2 begins (Section 5).
- **Out-of-sample holdout** reserved and untouched until the in-sample model is fully specified and frozen.

## 4. Stage 2 — Hedge Structure Selection

Deliberately rules-based, not model-fit, because the sample size that would be needed to responsibly train a structure-choice classifier doesn't exist here. Given Stage 1's score for a peer, plus that peer's live options conditions (liquidity/open interest, put skew steepness, term-structure shape relative to the lag window, and a defined cost budget), a decision table picks among: no position, outright protective put, put spread, collar, or a sector-ETF proxy hedge if the single name has no viable options market. This can be expressed as a small constrained optimization (minimize cost subject to a minimum protection threshold) rather than a black box, so every recommendation is explainable — consistent with the audit-oriented culture already in this repo (gates, locks, dated amendments).

## 5. Build sequence

Every phase below ends with a **smoke test** before the next phase is allowed to start — a fast, end-to-end run of that phase's full pipeline (ingest → features → lag detection → model/rules → output) on a small fixed fixture (synthetic or a tiny cached real sample), asserting only that it runs to completion and produces outputs in the right shape/schema. Smoke tests are not statistical validation (that's the placebo test, CV, and OOS test, which are separate and already specified above) — they exist purely to catch integration breakage (a broken join, a schema drift, a silent empty dataframe) before it wastes a phase gate. Each phase's smoke test should be committed alongside that phase's code and run in CI, matching the existing GitHub Actions pattern in `.github/workflows/`.

**Phase 0 — Feasibility check (no locking, no real capital logic).** Confirm the pipeline runs end-to-end on a placeholder linkage (same-sector peers) using data already on hand. Includes: (a) the realized-vol-vs-IV data-availability audit from Section 3, (b) confirming the target variable can actually be computed under its new fixed-horizon/residualized definition, (c) a first empirical ICC estimate to convert Section 6's naive N gate into a design-effect-adjusted one, and (d) checking whether the resulting placeholder-linkage sample size clears that adjusted gate.
*Smoke test:* run the full Phase 0 CLI on a 2–3 anchor-event synthetic fixture with placeholder linkage; assert it completes without error and the output (features table, local-projection lag estimates with prewhitened-CCF cross-check, Stage 2 rules-table decisions) matches the expected schema.

**Phase 1 — Exploratory, non-binding.** Once the real linkage map exists, run Stage 1 openly (no lock yet) to see whether there's a plausible signal, same spirit as the original within-sample GST exploration. Results here are diagnostic only — nothing gets shown as a "finding" per this project's existing result-display-gate convention.
*Smoke test:* same shape as Phase 0's, rerun against the real linkage map's schema (not its actual values) to confirm the real map plugs into the pipeline without a schema mismatch before any exploratory numbers are looked at.

**Phase 2 — Preregistration lock.** Freeze target definition, feature set, model spec, and validation split in a dated lock document (mirroring `GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md`) before touching the out-of-sample holdout.
*Smoke test:* run the locked pipeline end-to-end against the in-sample data only (holdout untouched) and confirm it reproduces the exact spec frozen in the lock document — a tamper/drift check in the same spirit as this project's existing "tampered lock file → SystemExit" mutation tests.

**Phase 3 — Out-of-sample test.** Run the locked model against the holdout once, report result regardless of outcome (per the existing result-display-gate discipline — no re-running until it looks better).
*Smoke test:* a dry-run against a copy of the holdout schema (not the real holdout) confirming the exact locked code path executes cleanly, run and passing *before* the one real holdout execution — the real run should never be the first time the code has executed end-to-end.

**Phase 4 — Paper trading gate.** Only if Phase 3 clears its preregistered bar: wire Stage 2's rules engine to real-time data and paper-trade the hedge recommendations for a defined period before any real capital is discussed.
*Smoke test:* a daily automated end-to-end dry run (data pull → features → lag estimate → Stage 2 decision → paper order construction, stopping short of any live submission) that must pass before that day's paper-trading cycle is allowed to run for real.

## 6. Phase 0 sample-size gate — power calculation

Phase 0 previously said only "is the sample size large enough to be worth continuing" — too vague to act as a real gate. Putting a number on it:

**Approach.** Standard two-sample power calculation for detecting a difference in abnormal peer vol (high-anchor-shock events vs. low-anchor-shock events), using the normal approximation: n per group ≈ 2·(z₁₋α/2 + z₁₋β)² / d², two-sided α = 0.05 (z = 1.96), power = 0.80 (z = 0.84).

| Assumed effect size (Cohen's d) | n per group | Total N (2 groups) |
|---|---|---|
| 0.3 (small) | ~175 | ~348 |
| 0.5 (medium) | ~63 | ~126 |
| 0.8 (large, matching the anchor's own confirmed GST→move-magnitude effect) | ~25 | ~50 |

**Which effect size to assume is the actual judgment call, and it must be preregistered, not picked after seeing early results.** Using the anchor's own d ≈ 1.29 (from the validated GST→move-magnitude finding) would be optimistic — that's the effect on the anchor itself, and a spillover onto a less-attention-linked peer should be expected to attenuate substantially. **Recommended default: d = 0.5 (medium), giving a target of ~126 total observations (~63 per group)**, as a defensible middle ground pending real evidence. This should be stated as a placeholder assumption in the Phase 0 status doc and either confirmed or revised with real justification before the Phase 2 lock — not silently carried forward.

**Clustering caveat.** This calculation assumes independent observations. In practice, multiple peers per anchor event (and possibly multiple events per peer over time) means observations are clustered, which inflates the effective variance and means the naive N above is a **floor, not a sufficient target** — the true required N is higher by a design-effect factor that depends on the intraclass correlation (ICC) within anchor-event clusters, which isn't known yet. One of Phase 0's jobs is to produce a first empirical estimate of that ICC from the placeholder-linkage data, so Phase 2's lock document can state a design-effect-adjusted N gate rather than the naive one above.

## 7. Known risks to preregister against

- **Multiple testing**: many candidate peers per anchor means many implicit comparisons. Needs an explicit correction (this project already uses permutation-based significance elsewhere — same approach applies) or a single pooled test rather than per-peer significance hunting.
- **Survivorship in the linkage map**: if the supply-chain teammate's mapping only includes currently-prominent relationships, historically-relevant but now-defunct links could bias the sample.
- **Coverage drift**: a peer's "thinness" isn't static — a name can go from thinly covered to heavily covered over the sample window (e.g., after its own breakout event), which would mechanically shrink the lag this model is trying to find. Needs a time-varying coverage feature, not a static one.
- **Small-N overfitting**, flagged throughout — the single most likely failure mode given this project's history with the IV-mispricing and Attention Spread hypotheses.

## 8. What I need from the team to move past Phase 0

From the supply-chain/competitor teammate: the actual linkage map (ticker pairs + relationship type + confidence), which is the one hard blocker.
From the data-validation teammate: nothing blocking, but their thin-ticker calibration work would directly improve the "coverage/thinness" feature in Stage 1 once available.
