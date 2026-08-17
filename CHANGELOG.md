# Changelog


## 2026-08-16 — Restaurant search pilot: NO_INCREMENTAL_SEARCH_VALUE

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY`. Not HYP-01 confirmation, not prospective collection.
Targets **magnitude**, never direction.

8 usable tickers, 210 candidate events → **122 complete** → **82 out-of-sample** (2021-07-20 →
2025-11-06; 63 AMC / 59 BMO from SEC 8-K item 2.02 acceptance timestamps). Large-move base rate 24.39%.

| Model | Brier | Log loss | AUC |
|---|---|---|---|
| A. Intercept-only training prevalence | **0.18454** | **0.55588** | 0.4665 |
| B. Baseline | 0.20211 | 0.62690 | 0.6460 |
| C. B + investor attention (`[TICKER] stock`) | 0.23665 | 0.81574 | 0.6177 |
| D. C + product demand (brand) | 0.24739 | 0.90235 | 0.6427 |

**Brier degrades monotonically as features are added; the intercept-only null wins outright.**

Central test `Brier loss(C) − Brier loss(D)`: raw mean **−0.010745**, CI [−0.041115, +0.019625];
CR2/BRL clustered by ticker (8 clusters, Satterthwaite df 6.543) **−0.010745, SE 0.02501, t = −0.430,
p = 0.68126, CI [−0.070734, +0.049243]**. **D beats C on 59.76% of events yet the mean is negative** —
product demand wins slightly more often but loses far more heavily; counting wins would invert the
conclusion. Tail lift moves the wrong way too: top-quintile realized large-move rate B 35.29%
(1.447×), C 29.41% (1.206×), D 23.53% (0.965×). Continuous MAE: B 5.4534, C 5.6790, D 5.8543 pp.
Model D is badly miscalibrated — its top bin predicts 0.7549 against a realized 0.2381.

**Leakage assertion: 353 checks, 0 violations** — every search week closes strictly before its
announcement timestamp, asserted mechanically per event and independently rechecked in the test.

**Options: `OPTIONS_HISTORY_UNAVAILABLE`** — no per-event pre-announcement implied move exists for
these tickers (committed IV files cover one ticker and are keyed on the forbidden GST spike window),
and no authenticated provider is configured. Current options data was not substituted and no implied
move was reconstructed from realized returns.

**Relationship to PR #27.** That revenue-nowcasting null is untouched — not reinterpreted, retuned or
rerun. This pilot reuses PR #27's exact frozen query map and weekly consumer series. **Success here
would not have overturned PR #27's null**: different targets, neither substitutes for the other. Two
disclosures from the reuse: the executed consumer queries are `Chipotle Mexican Grill` and `Dutch Bros
Coffee` (this task's spec froze `Chipotle` and `Dutch Bros`), and PR #27's series starts 2020-12-27,
so with the 52-week baseline the panel begins 2021-07-20 rather than 2019. The investor series was
fetched here (2018-12-30 →) since PR #27 had none.

Universe and queries frozen before retrieval; one fixed robust transformation
`(x − median₅₂)/(1.4826·MAD₅₂)` for both families; tail threshold recomputed from the training fold
only at each step; regularization chosen inside each training fold from a grid fixed in advance;
expanding chronological folds, never shuffled; identical folds and observations across A/B/C/D.

A baseline-feature defect was found and fixed during the run: quarterly revenue facts are re-filed
under multiple accessions, so a naive "exactly one year-ago match" silently dropped every established
company (122 events → 3). Deduplicating to the earliest-filed value per period end fixed it — a
point-in-time-preserving dedup, not an outcome-driven choice.
## 2026-08-16 — Brand search demand and revenue nowcasting: INSUFFICIENT_DATA

`EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY`. A **fundamentals-nowcasting** study — no stock return,
option, analyst estimate or prospective HYP-01 outcome retrieved or used. **Ticker GST is not used**;
only the eight frozen brand queries enter.

**Point-in-time limitation.** Google Trends series retrieved today are a **retrospective
reconstruction**: Google rescales to the requested window's maximum and may revise sampling, so the
identical series was not necessarily available when each quarter closed. This MVP can generate a
prospective hypothesis; it cannot establish contemporaneous availability. Every figure inherits that.

**Decision: `INSUFFICIENT_DATA`** — the minimum-sample rule fails at **38 out-of-sample observations
against a required 40** (eligible company-quarters 66 ≥ 60 ✓; out-of-sample companies 7 ≥ 6 ✓). The
label is set by the gate, not by the numbers.

The numbers were computed anyway and point the same way:

| Model | MAE (pp) | RMSE (pp) | OOS R² vs A |
|---|---|---|---|
| A. Expanding company historical mean | 6.3795 | 8.5120 | 0.000 |
| B. Fundamental ridge | **6.3679** | 8.0876 | 0.09724 |
| C. Fundamental + search demand | 6.8735 | 8.1836 | 0.07568 |

**MAE change B → C: −7.94%** — search made the primary metric worse. Decisive paired comparison
`abs_error(B) − abs_error(C)`: mean **−0.5056 pp**, C wins only **44.74%** of events; ticker-clustered
(CR2/BRL, 7 clusters) **−0.5056 pp, SE 0.97855, t = −0.517, p = 0.62525, CI [−2.946, +1.935]**. The
interval is wide — 38 observations cannot resolve a small effect either way, which is why the gate
exists. Not stable across years: 2024 **+0.72 pp**, 2025 **−1.61 pp**, a sign flip across the only two
evaluable folds.

By company, strongest **WING +3.2599 pp** (the company B forecasts worst), weakest **CAVA −3.7141 pp**
(only 2 observations); three of seven improve, four worsen.

A secondary metric does favour C — acceleration-sign accuracy **60.53% vs 55.26%** — while RMSE and
OOS R² do not. **The fixed primary MAE comparison fails, so this is not reinterpreted as success.**

**Why only 38 out-of-sample:** the 2023 fold could not run (9 training observations). Google serves
weekly resolution only for windows up to ~5 years — an 8-year request silently returns *monthly*
points, which cannot fill a fiscal-quarter average — so usable weekly history starts in 2021 and the
first two years are consumed by the year-ago revenue base and the four-quarter search baseline.

292 raw quarterly revenue facts → 251 company-quarters after deduplication by ticker, fiscal period
and accession → 66 eligible. All eight frozen queries returned usable data (none marked unavailable);
TXRH dropped at the feature-completeness stage, not the query stage. Exactly two search features, both
normalized on earlier quarters only; the search window is the company's own fiscal quarter and ends
strictly before the earnings release. One fixed ridge (alpha 1.0) for both B and C; chronological
expanding window with fold-local scaling; no model search, alpha tuning, feature selection, trees,
neural networks or quantum models; universe and query strings frozen before retrieval and unchanged.

**The next-stage rule is not triggered** — search demand did not improve the fixed primary metric, so
no later project may proceed to earnings-gap direction on this basis. No stock return was tested.


## 2026-08-16 — GST does not improve out-of-sample magnitude forecasting

`RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms nothing about HYP-01. **No directional trading or
profitability is evaluated in this study.** Additive files only; HYP-01 locks, registry, F5
artifacts, universe constants and frozen methodology untouched.

Outcome, frozen before fitting: `abs(open(T)/close(T−1) − 1)`. Deduplicated to 217 unique
`(ticker, event_day)` identities, 189 with complete features, **136 out-of-sample** across the same
2023/2024/2025 chronological folds as PR #23.

| Model | MAE | RMSE | OOS R² vs intercept |
|---|---|---|---|
| A. Intercept-only historical mean | 3.6673 pp | 4.7643 pp | 0.000 |
| B. Baseline, no GST | **3.6284 pp** | 4.6844 pp | 0.03325 |
| C. Baseline + pre-event GST z | 3.6299 pp | **4.6395 pp** | **0.05167** |

**MAE change B → C: −0.0413%** — marginally worse on the primary metric. Decisive paired test, event
level, `abs_error(B) − abs_error(C)`, intercept-only design clustered by ticker (26 clusters), CR2/BRL
with Satterthwaite df: **−0.00152 pp, SE 0.06902, t = −0.022, p = 0.9827, CI [−0.14703, +0.14399]**.
GST is better on 49.26% of events. For **this fixed ridge specification, this sample, these folds and
the MAE objective**, and under the stated ticker-clustering assumptions, the interval excludes a mean
MAE improvement greater than approximately **0.144 pp**. It does **not** rule out tail-ranking value,
alternative genuinely prespecified models, prospective performance, or usefulness relative to
options-implied movement. **Conclusion: `GST_DOES_NOT_IMPROVE_MAGNITUDE_FORECAST`.**

**Correction to how PR #22 may be cited.** PR #22's +1.509 pp retrospective association used the
historical spike classification whose 14-day window overlaps the earnings event in this population.
It remains a retrospective association but **cannot be cited as evidence that GST was available
pre-event or predictively caused the larger move.** PR #22's arithmetic is unchanged; this limits
interpretation, not the numbers.

**The GST feature had to be rebuilt to be point-in-time.** The population's own spike z-score spans a
14-day window anchored at the spike week while the maximum anchor-to-event lead here is 5 days, so
its window always overlaps the announcement — and **9 of 217 anchors fall on or after the event day**.
Using it as a predictor would be lookahead. `gst_z_pre` is therefore built from raw weekly GST using
only weeks that **close strictly before** the event day: (latest closed week − mean of the prior 52
such weeks) / stdev, minimum 20 baseline weeks. The spike z-score is retained for reference only and
never enters a model.

**Secondary descriptive metrics that favor GST** — descriptive only, with no prespecified
inferential decision rule here; they generate a prospective tail-ranking hypothesis rather than
establish predictive value: C beats B on RMSE and roughly doubles OOS R² (0.0517
vs 0.0333), and its top predicted quintile realizes larger moves (7.7118 pp vs 6.9000 pp; lift 1.261×
vs 1.129× against a 6.1135 pp overall mean). Both gains are squared-error/tail effects — GST helps
slightly on the largest moves while being neutral-to-worse on the typical one, which is why MAE is
flat. Yearly MAE shows no consistent winner: the intercept-only baseline wins 2023 outright, C wins
only 2025.

One fixed ridge (alpha 1.0) for both B and C, standardization and fitting inside each training fold
only. No model search, no threshold search, no hyperparameter tuning; the primary metric was fixed as
MAE before any result was seen.

A design error was caught during development: the paired clustered test initially used ticker fixed
effects alongside the intercept, which saturates the model at cluster level — within-cluster residuals
vanish and the CR2 adjustment degenerated to a zero standard error with an infinite t. The paired mean
test now uses an intercept-only design clustered by ticker, and the focused test asserts the standard
error is finite and positive.


## 2026-08-16 — Correction: proper probabilistic null added; the null wins

Narrow correction to PR #23. No feature was added, no other strategy tried, nothing searched.

**The Brier baseline was wrong.** Always-positive predicts a hard 1.0, so its Brier (0.46528) and log
loss (12.86) are terrible by construction — beating it proves nothing probabilistic. The proper null
is **`INTERCEPT_ONLY_PREVALENCE`**: within each expanding-window fold, the positive-gap prevalence is
estimated from **training data only** and assigned to every test observation.

| Model | Accuracy | AUC | **Brier** | Log loss |
|---|---|---|---|---|
| **INTERCEPT_ONLY_PREVALENCE** *(selected)* | 0.4653 | 0.5042 | **0.25600** | **0.70522** |
| Logistic L2 | 0.4792 | 0.4654 | 0.27110 | 0.73762 |
| Shallow GBT | 0.4931 | 0.4757 | 0.28710 | 0.78249 |
| Momentum-sign | 0.4792 | 0.4752 | 0.32292 | 0.85988 |
| Always-positive *(classification benchmark only)* | 0.5347 | n/a | 0.46528 | 12.85611 |

**The null beats every learned model on both Brier and log loss.** The frozen selection rule — lowest
pooled out-of-sample Brier, AUC secondary — was reapplied **unchanged** with the null as a candidate,
and it now selects the null. A null model is an acceptable winner. The logistic model's earlier Brier
edge came from predicting near 0.5; against a null that is unconfident by construction, that edge
disappears. Always-positive is kept as a classification benchmark (53.47% accuracy is the bar a
classifier must clear) but is no longer treated as the probabilistic comparator.

**Main conclusion: `TESTED_DIRECTION_MODELS_HAVE_NO_SKILL`** — the tested pre-earnings price-based
direction models have no out-of-sample directional skill, and applying GST as a magnitude filter does
not rescue those models. The earlier line "Neither leg of the two-stage design works on this sample"
was too broad and is removed. `NEITHER_ADDS_VALUE` is retained only as a narrow secondary label for
the tested logistic-direction strategy and its GST combination — not for the two-stage concept.

Because the selected model is the null, **no directional trading strategy is presented as
investable**; a constant-prevalence null emits no directional signal and trading it would be a
disguised always-long rule. The logistic strategy figures (direction-only −0.7027% net; +GST
−0.8865%; incremental GST −1.0404 pp, p=0.5858) are retained explicitly as **secondary evidence about
the failed learned model**.

**Stated explicitly:** this does not invalidate the separate GST magnitude hypothesis; it does not
test GST combined with a direction signal that independently possesses directional skill; it does not
test analyst revisions, point-in-time news, options skew, fundamental expectations or
network-diffusion features; and a failed direction model cannot determine whether GST would improve a
genuinely informative direction model.

**The leakage finding is unchanged and remains prominent:** 68 duplicate rows out of 285 (one event 7
times) meant a duplicate's `prior_gap_dir` read its own gap sign. Before correction the logistic model
showed **63.6% accuracy and +0.60% net**; after deduplication to 217 unique identities and a strictly
lagging `prior_gap_dir`, **47.9% and −0.70% net**.


## 2026-08-16 — Independent pre-earnings direction model (superseded by the correction above)

`RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms nothing about HYP-01, uses no gated prospective outcome.
Additive files only; HYP-01 locks, registry, F5 artifacts, universe constants and frozen methodology
untouched.

Stage 2 of the two-stage design: an independent model predicts the sign of the overnight earnings
gap, and **GST is applied only afterwards** as a magnitude/event-selection filter. GST is never an
input to the direction model.

**A leak was found and removed, and it changed the answer.** The event population reuses matched
controls, so the same `(ticker, event_day)` identity appears several times — **68 duplicate rows out
of 285, one event 7 times**. Left in place this double-counted the evaluation sample and leaked the
outcome: a duplicate's `prior_gap_dir` feature read *the same event's* gap sign. With duplicates
present the logistic model scored **63.6% accuracy, AUC 0.6395, Brier 0.23824** and the strategy
returned **+0.60% net**. After deduplicating to **217 unique identities** and requiring
`prior_gap_dir` to use a strictly earlier date, the same model scores **47.9% accuracy, AUC 0.4654**
and the strategy returns **−0.70% net**. The apparent skill was the leak.

**Out-of-sample (144 events, chronological expanding window: train ≤2022 → test 2023, ≤2023 → 2024,
≤2024 → 2025):**

| Model | Accuracy | AUC | Brier |
|---|---|---|---|
| Always-positive | 0.5347 | 0.500 | 0.46528 |
| Momentum-sign | 0.4792 | 0.4752 | 0.32292 |
| Logistic L2 *(selected on Brier)* | 0.4792 | **0.4654** | **0.27110** |
| Shallow GBT | 0.4931 | 0.4757 | 0.28710 |

Selection was by pooled out-of-sample Brier, fixed before fitting and never based on returns. It
picks the logistic model, but the choice is hollow: accuracy is **below** the always-positive
baseline and AUC is **below 0.5**. The Brier edge comes from predicting near 0.5, not from
discrimination. Calibration is inverted at both ends — in the most-confident-up bin the observed
positive rate is 0.364. Two of three test years are below chance.

**Combined strategy** (enter close(T−1), exit open(T), 10 bps round trip):

| | Direction only | Direction + GST filter | Low-GST comparator |
|---|---:|---:|---:|
| Trades | 144 | 90 | 54 |
| Mean net | −0.7027% | −0.8865% | −0.3962% |
| Hit rate | 47.92% | 47.78% | 48.15% |
| Max drawdown | −81.66% | −78.90% | −26.27% |
| Worst year | 2023: −2.3316% | 2023: −2.5048% | 2023: −1.8785% |

The GST filter selects the *worse* half. Decisive statistic — incremental GST effect,
`strategy_return ~ high_GST + ticker FE`, ticker-clustered CR2/BRL with Satterthwaite df (27
clusters): **−1.0404 pp, SE 1.8752, t=−0.555, p=0.5858, CI [−4.978, +2.897]**. Secondary confidence
filter (one fixed threshold at 0.60, not searched): 63 trades, −1.8891% net.

**Conclusion (superseded — the correction entry above replaces this with
`TESTED_DIRECTION_MODELS_HAVE_NO_SKILL` after adding the proper probabilistic null):** the tested
pre-earnings price-based direction models have no out-of-sample directional skill, and applying GST
as a magnitude filter does not rescue those models. This does not establish that earnings-gap
direction is unpredictable in general.

Verified: one focused test confirms GST never enters the model, that no feature reads an index at or
after T, deduplication of event identities, chronological-only validation with fold-local
standardization, and that every reported metric and strategy figure recomputes.


## 2026-08-16 — Clustered-inference correction to the retrospective decomposition

Narrow statistical review of PR #22. The descriptive results and strategy definitions are unchanged;
the inference is not. Ordinary t-statistics treated observations as independent despite repeated
ticker events and reused matched controls, so every load-bearing statistic is re-estimated with
**CR2/BRL and coefficient-specific Satterthwaite df, clustered by ticker (28 clusters)**, reusing
`tools/hyp01_inference_feasibility.py` unchanged — the implementation tied out against an independent
R `clubSandwich` reference on 13 of 13 admissible fixtures. Retrospective development inference, not
HYP-01 confirmation.

| Model (+ ticker FE) | Coefficient on high_GST |
|---|---|
| **Primary** abs(day_return) | **+1.509 pp**, SE 0.766, df 16.3, t=1.969, **p=0.0662**, CI [-0.113, +3.131] |
| abs(day_return − SPY) | +1.539 pp, SE 0.678, t=2.27, p=0.03707, CI [+0.104, +2.973] |
| **Strategy E incremental** | **+0.013 pp**, SE 0.618, t=0.021, **p=0.98332**, CI [-1.294, +1.320] |
| Strategy B incremental | -0.344 pp, t=-0.747, p=0.46577 |
| Deduplicated abs(day_return) | +1.921 pp, t=3.561, p=0.00193, CI [+0.797, +3.045] |

**The primary magnitude coefficient weakened.** A naive ticker-demeaned t of 2.57 becomes
**t=1.969, p=0.0662**, with a 95% interval spanning zero — directionally unchanged but no longer
supported at 5% in the primary specification. The benchmark-adjusted (p=0.03707) and
deduplicated (p=0.00193) versions do clear 5%. All are reported; no model was chosen after
seeing the answers.

**Repeated controls were real and are now counted:** 152 signal rows = 152 unique events, but
133 control rows collapse to only **85 unique control events** — 24 identities duplicated,
48 extra rows, one control reused **6×**. Duplicated appearances are not treated as
independent: a fully deduplicated analysis (237 rows) is reported, and clustering is on ticker
because every repeated event and reused control is nested strictly within one ticker, making it
weakly coarser than event identity.

**NO STRATEGY is reaffirmed and strengthened, scoped to the five strategies tested.** All five ask
GST or the earnings gap to supply direction; a two-stage design in which direction comes from an
independent pre-earnings model and GST is applied only afterwards as a magnitude filter was not
tested and remains open. E's standalone profitability is post-earnings drift,
not a GST result; its incremental GST coefficient is +0.013 pp with p=0.98332. The high-GST
(+0.854%), low-attention (+0.861%) and all-event (+0.858%) returns are all retained alongside it.

Release timing audited: **249 AMC** events, all mapped to the next trading session; **36 BMO**,
34 on the announcement session and 2 on the next session because the announcement date
(a Berkshire Saturday release) was not a trading day. The 71.7% figure is now stated only as *the
overnight gap accounts for 71.7% of mean |gap| plus mean |open-to-close| among high-GST events* —
never as a share of total return or total movement.

Changes are confined to the existing PR #22 files.


## 2026-08-16 — Retrospective decomposition: the GST filter adds nothing to any stock strategy

`RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms nothing about HYP-01, changes no locked methodology,
uses no gated prospective outcome. Additive files only; F5 remains `OPEN`, collection `BLOCKED`,
the production universe unchanged.

285 usable earnings events, 28 tickers, 2021-03-24 → 2025-12-19, from the existing C5 matched
population plus committed daily OHLC. **No intraday bars exist in this repository**, so the
open→+30min and +30min→close components and **Strategy A** (opening-range breakout) are
**NOT TESTABLE**; no substitute was invented.

**Where the move is.** High abnormal GST does predict a larger absolute earnings move — 7.89% vs
6.45%, **+1.44 pp**, t=2.14 *(unclustered; superseded by the CR2 entry above)* — and the overnight
gap accounts for **71.7% of mean |gap| plus mean |open-to-close| among high-GST events** (7.00% vs
open→close 2.76%). It is stock-specific: 96.6% of the magnitude survives SPY subtraction. The
correlation between the gap and the subsequent open→close move is **−0.003**, so the gap says
nothing about what happens next.

**The magnitude effect is robust.** Matched pairs +1.66 pp (t=2.58), same-ticker pairs only +1.62 pp
(t=2.495), ticker fixed effects +1.50 pp (t=2.57). It weakens across time (+2.18 pp older half →
+1.11 pp newer) but does not vanish.

**The tradable edge is not.** Strategy E (benchmark-neutral continuation, T→T+3) returns +0.854% net
per trade, t=3.03, 63.2% hit rate, −10.4% max drawdown — but the identical rule returns **+0.858% on
all earnings events** and **+0.861% on the low-attention controls**, with a matched within-pair
difference of **+0.116% (t=0.27)**. E is post-earnings drift; GST is not what makes it work. Gap
continuation (B) is worse: controls (+0.840%) beat high-attention (+0.473%). Gap reversal (C) is
−0.673% net, `FAILS_AFTER_COSTS`. Attention–price divergence (D) is `WEAK/UNSTABLE` (quiet 7.43% vs
loud 8.18% absolute, t=−0.76).

**Verdict: NO STRATEGY, scoped to the five strategies tested.** None of the five qualifies for
prospective testing. The
one surviving attention effect is magnitude rather than direction and is realized overnight;
capturing it would need a volatility structure, which is outside this stock-only scope.

Costs (10 bps single-leg, 20 bps two-leg), the quiet-price threshold (|pre-drift| ≤ 2%), event-day
convention and all windows were fixed before outcomes were computed. No window, threshold, holding
period or cost was searched over afterwards.

Verified: one focused test recomputes 25 sampled events exactly from raw OHLC, ties sample counts
(285 usable + 19 dropped = 304), checks gap×(open→close) = day return across all events, verifies
cost subtraction for every strategy, and confirms the report's headline numbers match the results
JSON. The existing market-response decomposition suite also passes.


## 2026-08-16 — Final verification: the tracked-test count was wrong (45 → 47), and disposition recorded

**No numerical result changed.** No classification, category count, metric, source snapshot, frozen
rule, proposed universe, production universe, F5 status or research state was touched. This entry
corrects a **reporting** error and records a disposition.

**The test count was an undercount.** Previous entries and the PR body said "45 tracked test files".
The enumeration used `git ls-files 'test_*.py'`, which matches only the repository root, so it never
had a chance to see `Event_Dossier_Protocol/validator/`. Re-enumerated with
`git ls-files '**/test_*.py' 'test_*.py'` at head `024c614`:

| Category | Count |
|---|---|
| Market Response (`test_market_response*.py`, root) | **33** |
| Phase 2 (`test_phase2*.py`, root) | **12** |
| Event Dossier (`Event_Dossier_Protocol/validator/test_*.py`) | **2** |
| **Total tracked deterministic test files** | **47** |

Nothing is intentionally excluded; the two missing files were an enumeration defect, not a policy.
**All 47 pass** with sockets blocked *externally* via an injected `sitecustomize`, so blocking no
longer depends on each file policing itself. The two Event Dossier files were additionally run
through their workflow's exact discovery loop (`working-directory:
Event_Dossier_Protocol/validator`, `files=$(ls test_*.py)`, `python "$f"`) — both pass. All 47 were
then repeated from a clean-LF `git archive` export of `024c614` — 47/47 again.

**A skip-coverage defect was found and fixed.** Auditing the announced clean-export skips showed two
problems. First, the skipped set was larger than reported: three nested `14h'` sub-checks disappeared
**unannounced** (199 executed labels in the export vs 202 in the repository). Second — and more
importantly — `14h`/`14h'` compared clean-export output against the committed artifacts, so the
skipped set **did** touch classification arithmetic and issuer denominators. That could not be
certified as harmless, so it was removed rather than explained away.

The reproduction guarantee needs no `.git` metadata, so it is now checked unconditionally in every
context (`14A` argument-free reproduction succeeds; `14B` all four artifacts byte-identical; `14C` no
network call). The git-archive checks remain, but only as *packaging* evidence, and every skip —
including nested sub-checks — is announced with its reason.

After the fix: **208 assertions, 0 skips** in the repository; **200 assertions + 8 announced skips**
from a clean export, and 200 + 8 = 208 with **zero unannounced omissions**. All eight skips depend
solely on unavailable `.git` metadata or on attempting a nested `git archive`, and each is a
duplicate of `14A`/`14B`/`14C`, which run everywhere. **No skipped check is now the sole cover for**
classification arithmetic, source hashes, CIK grouping, FF12 derivation, issuer denominators,
universe membership or protected research state.

**Disposition recorded** in `GST_UNIVERSE_50_SECTOR_COMPOSITION_DISPOSITION_v1.0.md`:
**`ACCEPT_CURRENT_BROAD_PROPOSAL`** — no sector-specific or stratified redesign required before F5,
on the grounds that the final 50 covers all 12 FF12 categories, has a 24.0000% largest-category
share, is less concentrated than the legacy 24 on every specified metric, tracks the 100-issuer OEF
proxy within ±3.0 pp under equal weights, and is stable under leave-one-out.

It is recorded as **independent AI technical review plus repository-owner acceptance**, and states
plainly that the AI reviewer is *the same agent that authored the audit* and therefore not
independent of the author. It is **not** a human review and **not** a credentialed-methodologist
review; GitHub contains no approving review. The committed reviewer template remains **unsigned with
every field `PENDING`** — deliberately untouched, since an audit's author must not fill in its own
review. The disposition changes no ticker and activates nothing: F5 remains `OPEN`, collection
remains `BLOCKED`, the production universe remains the original 24.


## 2026-08-16 — Correction: the proxy pool is an issuer denominator, and its sources are now committed

**Supersedes the figures in the entry immediately below for the OEF proxy pool only.** Independent
review returned `REQUEST_CORRECTION` on two findings. Both were correct. The frozen pre-retrieval
rule is **unchanged** (`sha256_lf` still `5ce6a0f0…4dab`), the 50 tickers are untouched, and no
verdict is drawn.

**Issue 1 — security denominator vs issuer denominator.** The frozen rule defines the proxy pool as
every eligible equity **issuer**, but the implementation deduplicated only by canonical ticker. That
gave Alphabet two equal-weight observations (`GOOG` and `GOOGL`, one CIK, one SIC) while the final 50
gives every issuer exactly one — the two sides were not on the same denominator, and the PR body
called the pool both "101-security" and "issuer".

The pool is now grouped by **official SEC CIK**, with the frozen alias `BRKB → BRK-B` applied
**before** identity matching. Every security under one CIK must carry the same SEC SIC **and** the
same FF12 category or the run **refuses and writes nothing**. Each issuer contributes one
observation; all constituent securities are preserved in `source_securities`; the display ticker is
the lexicographically smallest canonical ticker and enters no metric — a test renames every display
ticker to `ZZZZ` and asserts the metrics are identical. The resulting n is recomputed from the
identity snapshot, never hardcoded. The final 50 was **verified** to hold 50 unique CIKs rather than
trusting the proposal's declaration; a duplicate issuer there stops the run.

Every OEF figure was recomputed, none preserved by assumption:

| Figure | Before (security) | After (issuer) |
|---|---|---|
| OEF denominator | 101 securities | **100 unique issuers** |
| OEF `BusEq` | 23 (22.7723%) | **22 (22.0000%)** |
| OEF HHI | 0.128321 | **0.126400** |
| OEF entropy | 2.232480 | **2.239874** |
| OEF effective categories | 9.323290 | **9.392143** |
| Δ `BusEq` | +1.2 pp | **+2.0 pp** |
| Δ `Manuf`, Δ `Shops` | +2.1 pp each | **+2.0 pp each** |
| Δ `Hlth`, Δ `Money`, Δ `Other` | +0.1 / +0.2 / +0.1 pp | **0.0 pp each** |
| Classification requests | 151 | **150** |

`LEGACY_24`, `PROPOSED_ADDITIONS_26` and `PROPOSED_FINAL_50` metrics are unchanged. The **±3.0
percentage-point** statement was **re-derived, not preserved**: the largest absolute gap is still
3.0 pp at `NoDur`, so it remains true on the issuer denominator. The `OEF_ELIGIBLE_PROXY_POOL` label
is renamed `OEF_UNIQUE_ISSUER_PROXY_POOL` throughout — a naming correction stating the denominator
the rule always specified, not a rule change.

**Issue 2 — claimed reproducibility from unavailable inputs.** The review template promised
recomputation "from the committed sources" while naming three inputs that were in no changed path
and nowhere in the repository. Committed outputs cannot serve simultaneously as inputs and as
independently verified results. Added under `Universe_Sector_Audit_2026-08-16/sources/`, identity and
classification metadata only:

- `SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json` — 113 securities / 112 CIKs: canonical ticker, source
  securities, CIK, SEC entity name, SIC, SIC description, SEC URL, retrieval time, raw-response
  SHA-256. No filing financial data, earnings value or market information.
- `FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt` — the official Kenneth R. French definition bytes.
- `FF12_SIC_INTERVALS_NORMALIZED_2026-08-16.json` — the interval table derived from those bytes, with
  ZIP hash, extracted-file hash, canonical URL and the deterministic extraction procedure.
- `GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json` — filename, URL, retrieval time, byte count and
  SHA-256 for every input.

Per-response retrieval timestamps were **not** captured at fetch time. The batch window is recorded
with `timestamp_granularity: "batch"` and the per-record raw-response SHA-256 is the provenance
anchor. Nothing was back-dated or fabricated to fill that field.

The documented reproduction command is now argument-free and needs no external scratch directory:

```
python tools/sector_composition/classify_universe_sectors.py
```

It verifies every declared input against the manifest SHA-256 **before** computing; a missing input
or any hash mismatch is a refusal that writes nothing. Correcting this also exposed a real hole:
input verification resolved paths against the repository root, so a mutated `--sources` directory
would have passed its own hash check and then been used. Verification now resolves the files
actually read.

**Denominator clarification.** The report previously said "151/151" while the CHANGELOG and PR body
said "113/113" — neither defined. All denominators are now stated explicitly: **50** final-50
securities (= 50 issuers); **101** OEF source securities → **100** unique issuers; **113** unique
canonical securities in the union of the two groups; **112** unique CIKs in that union; **150**
classification requests, the overlap counted in both. **113 means unique canonical securities** —
not issuers, not classification requests.

**Verified.** The suite now passes **208 assertions** and the mutation battery is extended to **45
mutations, 45 caught**, including: splitting share classes back to security level; falsifying the
issuer, final-50-CIK or union counts; dropping `source_securities`; claiming the display ticker
affects metrics; choosing a non-deterministic display ticker; duplicating a CIK in either group;
deleting or tampering with any committed source; falsifying a manifest hash; and relabelling the
proxy denominator as securities in the report prose. That last one **survived the first run** — the
suite could not yet detect the exact mislabelling the review asked me to prevent — so the check was
added rather than the finding waved through. New tests also confirm a clean `git archive` export
contains every declared input and reproduces all four artifacts **byte-identically** offline, and
that removing an input, changing a hash, changing a CIK, changing a SIC, changing an FF12 interval,
or giving one CIK conflicting SICs or conflicting FF12 results each fails. All **47 tracked test
files** pass sockets-blocked. *(This entry originally said 45 — an undercount, corrected in the
verification entry above: the enumeration globbed only the repository root and missed the two
`Event_Dossier_Protocol/validator/` files.)*

Protected state is unchanged: `constants.py` (still exactly the original 24), both HYP-01 locks, the
effective-lock report, the cohort protocol, the F5 audit, the merged universe proposal and the single
`DELL` registry row. F5 remains `OPEN`; collection remains `BLOCKED`.


## 2026-08-16 — Descriptive sector-composition audit of the proposed 50 (NO UNIVERSE CHANGE)

**DESCRIPTIVE AUDIT ONLY · NO UNIVERSE CHANGE · PROPOSED 50 REMAIN INACTIVE · PRODUCTION UNIVERSE REMAINS 24 · NO GST OR MARKET OUTCOME USED · F5 REMAINS OPEN · COLLECTION REMAINS BLOCKED · NO CONCENTRATION THRESHOLD WAS INVENTED.**

Not one of the 50 tickers was altered, reordered, replaced or removed, and no
alternative universe was generated. This entry adds measurement, not a decision.

**What was measured.** Every security in the legacy 24, the 26 proposed additions,
their union, and the 101-security OEF eligible-equity proxy pool was assigned a
Fama–French 12 industry **mechanically**: `ticker → CIK → SEC SIC → matched SIC
interval → FF12`. No manual override, no name-based inference, no aggregator, no
encyclopedia, no model-generated sector label, no ETF weight and no market
capitalization was used as evidence. Sources are the official SEC
`company_tickers.json` and `data.sec.gov/submissions/` (identity and SIC metadata
only — no financial statements, no earnings values) and the official Kenneth R.
French `Siccodes12` definition file. All metrics use **equal ticker weights**.

**The rule was frozen first.** `PRE_RETRIEVAL_SECTOR_COMPOSITION_AUDIT_RULE_2026-08-16.md`
(SHA-256 `5ce6a0f0…4dab`) was written and hashed at `2026-08-16T07:49:31Z`, before
any SEC or French retrieval. It fixes the groups, sources, metrics, weighting,
missing-data policy and language discipline, and it deliberately freezes **no**
concentration threshold. A test recomputes that hash from the committed file.

**Coverage: 113/113 securities classified, zero `CLASSIFICATION_UNRESOLVED`.** The
code still refuses to infer a missing SIC — a test asserts a `None` SIC yields
`CLASSIFICATION_UNRESOLVED` rather than a guessed category, and that an unresolved
ticker would be reported in place rather than deleted or replaced.

**Descriptive findings.** Expansion produced **lower** concentration: HHI falls
0.225694 → 0.140800 and the effective number of categories rises 6.22 → 8.55. The
largest category's share falls from 41.6667% (`BusEq`, legacy 24) to 24.0000%
(`BusEq`, final 50). The legacy 24 was missing `Chems`, `Telcm` and `Utils`; the
final 50 represents **all 12** categories with none absent. Against the OEF proxy
pool every category sits within **±3.0 percentage points** (`NoDur` −3.0 the
largest gap; `Manuf` and `Shops` +2.1 each). Leave-one-ticker-out moves the
largest-category share only within 22.449%–24.490% and HHI within
0.137026–0.146189, so no single ticker drives the result.

**What this does not establish.** No accept/reject threshold was specified by this
task, so no such verdict is drawn, and the audit does not call any distribution
representative, balanced, acceptable, unacceptable, biased or statistically
significant. Whether this composition is adequate for HYP-01 — and whether a
stratified or sector-specific redesign is warranted — is left to an independent
reviewer. `GST_UNIVERSE_50_SECTOR_COMPOSITION_REVIEW_TEMPLATE_v1.0.md` ships with
every finding and all four dispositions `PENDING`; none is preselected. That
decision must be made **without consulting GST attention data or return outcomes**,
since choosing a universe after seeing outcomes would make the sampling frame
outcome-dependent.

**Verified before committing.** `test_market_response_universe_50_sector_composition.py`
runs offline with sockets blocked and passes **127 assertions**. It does not trust
the audit's own declarations: it re-executes `ff12_for_sic` against the frozen
intervals for all 113 records, recomputes every count, percentage, HHI, entropy,
effective-category count, FINAL_50-vs-OEF difference and the full 50-way
leave-one-out sweep, and confirms the ordering matches the merged proposal exactly.
A **28-mutation battery** confirms the suite actually fails: reordering, dropping or
substituting a ticker; overriding a category away from its SIC; falsifying any
metric or sensitivity bound; citing a non-SEC provenance URL; inferring a category
for a missing SIC; leaking an OEF weight; claiming a threshold, a verdict, a subset
search or an altered universe; falsifying or post-dating the frozen-rule hash;
editing the frozen rule; ticking a disposition or naming a reviewer; deleting a
banner or the no-threshold statement; desynchronising the CSV from the JSON;
removing the socket block; or making the classifier read a price field. **28 of 28
were caught.**

Three test failures during development were traced to the test, not the audit, and
each matcher was tightened rather than the guarantee relaxed: a substring search for
prohibited weight fields was matching the Python `return` keyword and the disclaimer
strings that assert those fields were *not* read (now matched only in read position,
with a self-check that the matcher catches a planted `row["price"]`); a 1e-6
tolerance was applied to percentages stored at 4 dp, so denominators of 24, 26 and
101 summed to 100.0001 (replaced with the **stricter** pair — unrounded shares sum
to exactly 100, and each stored value equals the exact 4-dp rounding of its share);
and a required phrase was line-wrapped in the Markdown source, so a raw substring
match missed text that was present.

Protected state is asserted byte-identical: `constants.py` (still exactly the
original 24), both HYP-01 locks, the effective-lock report, the cohort protocol, the
F5 audit, the merged universe proposal, and the single unchanged `DELL` registry
row. F5 remains `OPEN`; prospective collection remains `BLOCKED`.


## 2026-08-16 — Proposed outcome-blind universe expansion 24 → 50 (PROPOSAL ONLY, NOT ACTIVE)

**PROPOSAL ONLY · NOT ACTIVE · NOT AN S&P DJI CONSTITUENT FILE · CURRENT 24 REMAIN OPERATIVE · F5 REMAINS OPEN · COLLECTION REMAINS BLOCKED · NO PRODUCTION QUERY CHANGED · NO TICKER WAS SELECTED USING ATTENTION, PRICE, EARNINGS, OUTCOME OR PERFORMANCE INFORMATION.**

The production constant `LOCKED_24_TICKER_UNIVERSE` is byte-identical. Nothing is activated by merging this.

**Three artifacts were frozen and hashed in order, each before the step it governs.**

| Step | Artifact | Frozen before | SHA-256 |
|---|---|---|---|
| 1 | `PRE_RETRIEVAL_SELECTION_RULE.md` | any constituent retrieval | `6911726c…761cde` |
| 2 | `PRE_RETRIEVAL_SOURCE_AMENDMENT_2026-08-16.md` | any OEF request | `bf88f226…ab0d6bd` |
| 3 | `PRE_SELECTION_ALIAS_AMENDMENT_2026-08-16.md` | any final selection | `5faabac1…b30ffc6` |

Steps 1 and 2 are byte-for-byte unchanged by everything that followed.

**S&P DJI was unobtainable, and its controls were not circumvented.** Four routes returned HTTP 403 or failed DNS; a real browser engine received an explicit **"Security Controls Triggered"** page (`e8e8b3e3…8975b465`). That is an access control the operator imposed. It was **not retried, evaded, proxied around, or circumvented**, and no aggregator, encyclopedia or generated list was substituted.

**The permitted source was amended, additively, to a fund-holdings proxy** — *the dated official iShares OEF holdings snapshot, used as an identity-only proxy for the S&P 100 investable universe*. It is **not** the index provider's canonical constituent list, and no document in the proposal calls it one. Downloaded from the link the official product page itself publishes: 17,200 bytes, raw SHA-256 `3d85de45…f125f892`, as-of **Aug 13, 2026**, quarantined outside Git.

**Only three identity columns survived sanitization** — `Ticker`, `Name`, `Asset Class`. **Twelve were dropped**, including Market Value, Weight (%), Notional Value, Quantity, Price and FX Rate. No prohibited value was read, printed, persisted or used, and the selector fails closed if a non-identity field reaches it.

**An identity collision stopped the first attempt.** The OEF file writes Berkshire Hathaway class B as `BRKB`; the repository writes `BRK-B`. Frozen rule R4 converts a provider *separator*, but this provider emits none — zero of 101 equity identifiers contain `.`, `-` or a space — so producing `BRK-B` required *inserting* one, which is interpretation, not transformation. R5 could not rescue it either, because the locked 24 is a ticker list with no issuer names. The provisional run had selected `BRKB` at rank 10, which would have put **one security in the universe twice under two spellings**. Work stopped and the provisional artifact was deleted rather than patched.

**A narrow alias amendment resolved it**, frozen at `{"BRKB": "BRK-B"}` and applied before locked-24 comparison, issuer deduplication, hashing and uniqueness counting. Source `BRKB` is classified `ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION`, excluded from the addition pool, and **never hashed as a candidate**. Both identifiers survive in the ledger so the transformation is visible. The amendment was created **after** the collision was discovered and **before** final selection — stated plainly, because the collision had to be seen before it could be described — and was informed by two identifiers and an issuer name, nothing else.

**Dispositions — 105 source rows, each with exactly one:** 4 excluded as non-equity (`XTSLA`, `MSFUT`, `ESU6`, `USD`), 1 excluded as a duplicate economic issuer (`GOOG`, because `GOOGL` is locked), 0 malformed, 12 already locked (including `BRKB`→`BRK-B`), 88 eligible candidates, **26 selected**, 62 not selected.

**Selected 26**, first-26 under `SHA256(UTF8("GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" + ticker))` sorted ascending: CAT, MMM, BA, COF, NEE, HONA, CL, DUK, HD, GS, INTU, BMY, BNY, AMT, ACN, LRCX, MS, TMO, ISRG, T, BLK, LMT, AXP, LLY, WMT, NFLX. **No human judgment affected which 26.**

**NFLX entered at rank 26 mechanically.** It was rank 27 before `BRKB` left the pool; removing an ineligible entry shifts the tail up by one. That is a smaller pool, **not a backfill and not a manual insertion** — and R14 still forbids replacing any selected ticker that later fails F5, access, eligibility or data quality.

Final proposed universe: **50 entries, 50 unique tickers, 50 unique securities, 0 issuers represented twice**, with positions 1–24 the existing locked tickers in their existing order.

**The proposed cohort/universe amendment is append-only** and states why 24 was an operational starting scope rather than a derived optimum, why expansion happens now (zero eligible observations exist, so nothing can be influenced), and why 50 balances recruitment, cluster diversity, F5 workload and feasibility — offered as a governance judgment, **not** a demonstrated power target. It records that all 24 remain, that no failed ticker will be replaced, and that the first-60-eligible-events rule, D1–D16 and DELL's registration are unchanged.

**Correction after independent review (`REQUEST_CORRECTION`).** The first version's `issuer_key()` stripped a trailing `CLASS/CL/SER/SERIES` designator with a general regex. That is **not** the case-and-punctuation-only normalization frozen rule R5 specifies, yet it materially grouped `ALPHABET CLASS A` with `ALPHABET CLASS C` and drove `GOOG`'s exclusion — and disclosing it in the review template did not make the implementation consistent with the frozen rule. The reviewer was right to treat it as blocking.

The general suffix stripping is **removed entirely** and replaced by an exact frozen source-name map, `{"ALPHABET CLASS A": "ALPHABET", "ALPHABET CLASS C": "ALPHABET"}`, applied immediately before R5 deduplication and nowhere else; every other name falls back to R5's sentence verbatim. An unlisted share-class group makes the build **stop** rather than guess, and a mutation test found a second gap on the way: a map that *covers* both names but sends them to *different* groups would have defeated R5 silently, so the detector now also requires every member of a share-class group to resolve to one issuer key. A fourth dated amendment (`ff7131e7…3c3dc6`, 06:05:57Z) records the resolution, created after retrieval, after the inconsistency was found, after the earlier selection existed, and **before** the corrected one. The v1 selection artifacts were **deleted from the branch** before recomputation so no stale selection survives.

**The corrected recomputation produced an identical selected 26**, and `GOOG`'s exclusion was independently verified **not** to move the rank-26 boundary — its digest sorts below rank 26. The defect was a real rule inconsistency, not a wrong outcome.

**Governance mappings are now fail-closed, not merely review-detectable.** A second review pass found that mutating a frozen map still produced a proposal — the tests asserted only that the change was *noticeable*. That is not the guarantee. The selector now runs `assert_governance_integrity()` **before any disposition, hashing, ranking or output**, and refuses — emitting nothing — unless three independent things agree: each in-code map's canonical digest (`json.dumps(map, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`, UTF-8, SHA-256) equals its frozen expected digest (`d4b80e13…05d860` for `{"BRKB":"BRK-B"}`, `50bd57cf…3fa8a0` for the Alphabet pair); every amendment artifact still hashes to its recorded value; and the map parsed **out of** the amendment equals the in-code map. Twelve mutation classes — alias removed/retargeted/extended, issuer map removed/partial/retargeted/broadened/extended, either amendment missing or altered, expected digest altered, and code disagreeing with amendment — each now assert **SystemExit occurred and the output directory is empty**, and the phrases "detectable by review" and "refused or visibly changes the outcome" are gone.

**A hash-only evidence manifest** now lets a reviewer verify the historical raw bytes without the repository ever containing them: filename, repository-external location, byte count, SHA-256, retrieval timestamp, as-of date, official URL, confirmation it remains available to an authorized reviewer, and confirmation it is untracked. The raw file was re-hashed in place and still matches.

**A review template ships with every field `PENDING`**, all three dispositions unticked, and no reviewer identity invented. It flags for the reviewer the one mechanical step the frozen rule required but did not spell out — removal of a trailing share-class designator when building the issuer grouping key, applied to the key only and never to the ticker.

Tests: `test_market_response_universe_expansion_50.py` (**102 assertions**) executes the selector and recomputes rather than trusting the proposal, and includes mutation tests proving that removing the alias reintroduces the duplicate security, that a changed or unapproved alias is detectable, that 25 or 27 additions fail closed, that removing or reordering the original 24 fails, that malformed input fails closed, that selection is invariant to input row order, and that a one-character ticker change changes the digest. All tracked test files pass with sockets blocked, in the working tree and in a line-ending-normalized archive export.

Added `tools/universe_expansion/` (sanitizer and selector) and `Live Signal Engine/Universe_Expansion_2026-08-16/` (the three frozen governance artifacts copied in unchanged, the identity-only snapshot, provenance manifest, proposal JSON and Markdown, audit, cohort amendment and review template). Protected hashes, DELL and all research state unchanged.


## 2026-08-16 — Dated authorizer amendment: D1–D16 authorized; F5 still OPEN and collection still BLOCKED

**Dated authorizer amendment for HYP-01 statistical rules. No prospective outcome was inspected, F5 remains OPEN, and collection remains blocked.**

**The authorization, verbatim:** *"I authorize the recommended D1–D16 methodological package as specified on August 16, 2026."*

Authorized by the **project authorizer / repository owner**. **No external peer review, methodological review, institutional approval or reviewer sign-off occurred**, and none is claimed — the authorizer is not an independent statistician or methodologist, and no handwritten signature exists. Declared authorization date **2026-08-16**, basis **user-declared UTC calendar date**; recorded at 2026-08-16T03:57:18Z. The record does **not** assert the authorization happened on 2026-08-16 in America/Chicago — at that UTC instant the local civil date was 2026-08-15. Commit timestamps, preserved by git, record entry into history separately.

**Nothing was rewritten.** The amendment is append-only. v1.0 and its companion, the proposed v1.1 and its companion, the signoff template and the PR #17 / PR #18 validation artifacts are all byte-identical, and their exact hashes are recorded inside the amendment so drift is detectable.

**The authorized package:**

| | Decision |
|---|---|
| D1 | **CR2 / bias-reduced linearization**; official path R 4.6.1 + clubSandwich 0.7.0, `vcovCR(..., type = "CR2")`. Python is a validated cross-check, not the authoritative calculation |
| D2 | **BRL adjustment built into clubSandwich CR2** — no CR1 scaling, no second correction |
| D3 | **Coefficient-specific Satterthwaite** via `coef_test(..., test = "Satterthwaite")`; realized continuous df persisted and reported |
| D4–D7 | **Wild bootstrap not used in HYP-01**; weights, repetitions and seed not applicable, with **no activatable placeholder retained** |
| D8 | **Retain singleton ticker clusters**; report cluster count, singleton count, permitted singleton identities and effective df |
| D9 | **Refuse and abort** on nine conditions, thresholds adopted **verbatim** from the committed feasibility runner; a refusal is **not** a null result |
| D10 | **No invented cluster or effective-df cutoff**; report five quantities always |
| D11 | R official / Python cross-check, **roles may not be reversed**; eight items frozen at event 60; a discrepancy **stops release** and may not be averaged or hand-reconciled |
| D12 | **Treatment/reference coding**, deterministic reference recorded before fitting, secondary model only |
| D13 | **Pool sectors with fewer than 3 eligible events into OTHER**, from counts only, map computed once and persisted |
| D14 | **No per-ticker cap** |
| D15 | **No multiplicity adjustment**; protected family = 1 predictor, 1 outcome, 1 test, α = 0.05 two-sided |
| D16 | **No project-derived power claim**; n = 60 is a **governance floor**, not a demonstrated power target |

**No new numerical threshold was invented.** D9's guards are read out of `tools/hyp01_inference_feasibility.py` (symbol `REFUSAL`, SHA recorded): condition number 1e10, zero-variance std 1e-12, relative RSS 1e-18, arithmetic cluster floor 2. `min_clusters_for_any_output` is labelled an arithmetic floor, explicitly **not** an eligibility rule — D10 imposes no cluster policy.

**Split tolerance provenance survives into the lock.** CR2 covariance, SE, t and p were validated under the **PR #17** tolerances; the continuous **Satterthwaite df** under a **separately prespecified PR #18 tolerance that was not preregistered in PR #17**. D3 carries that qualification inline, and the resolver refuses if it is ever dropped.

**No outcome existed to inspect.** At authorization `results` was null, `frozen_event_ids` empty, `eligible_events_now` 0 and `screening_rows` empty. There was no estimate, direction, p-value or plot to see.

**Effective state:** statistical package **AUTHORIZED** · implementation **VALIDATED** (implementation agreement, not scientific proof) · F5 construct validity **OPEN** · prospective collection **BLOCKED** · scientific result **NONE** · analysis **NOT RUN** · external preregistration **NOT PERFORMED**. Completing the internal lock does not make the study externally preregistered; that needs actual submission to an external timestamped registry.

**The decision matrix no longer contradicts the lock.** It carried "nothing here is decided… every authorizer field is PENDING". It now opens with a conspicuous banner stating that D1–D16 were decided on 2026-08-16 and that every `PENDING` marker and blank checkbox below is **historical**. The checkboxes were deliberately left unticked rather than back-filled, so the page stays an honest record of what was open when it was written. Its option tables and analysis are preserved unchanged.

**Enforcement.** `tools/hyp01_effective_lock/resolve_effective_lock.py` resolves the effective lock from exactly three inputs — the v1.0 base lock, the dated amendment, and the protected hashes recorded inside it — and **fails closed**, emitting nothing, if an artifact is missing, a hash drifts, more than one amendment claims a field, an amended field is absent, an unamended field drifts, the authorization statement or date is missing, the authorizer role is misrepresented, F5 is marked closed, bootstrap settings activate, CR3 is selected, CR1 becomes primary, package versions drift, the R/Python roles reverse, sector pooling reads outcomes, a ticker cap appears, alpha or sidedness changes, or n = 60 is called empirically powered. The proposed v1.1 takes no part in resolution. A machine-readable `GST_HYP01_EFFECTIVE_LOCK_REPORT_v1.0.json` is generated solely from the base lock and the amendment.

**No analysis runner was created or executed.** This freezes methodology; it analyzes nothing.

Tests: `test_market_response_hyp01_dated_amendment.py` (**187 assertions**), including **25 mutation tests** that independently corrupt each critical decision plus five structural corruptions — a missing decision, a hash drift, two competing amendments, unamended base-lock drift — and require the resolver to refuse every one. One mutation found a real gap: `package_version` could drift on its own because only the `locked_packages` map was checked. The resolver was strengthened.

Added the amendment JSON and companion, the authorization record, the effective-lock resolver and report, and the test file. Protected artifacts, DELL and all research state unchanged.


## 2026-08-12 — CR2 now has an independent R reference: 13 of 13 fixtures agree at the noise floor

**Independent synthetic implementation validation only. No statistical method is approved, no lock is activated, and F5 remains OPEN.** `GST_HYP01_ANALYSIS_LOCK_v1.0` stays operative, the proposed v1.1 stays non-authoritative, every authorizer field stays `PENDING`, no signoff is completed and no dated amendment is created. DELL and every research artifact are byte-identical.

**The dependency that was blocking CR2 is now installed and pinned.** PR #17 recorded CR2 as `IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE` — the Python code ran, but nothing independent existed here to check it against. **R 4.6.1 + clubSandwich 0.7.0** now serve as that reference: written by other authors, maintained independently, not written for this study.

**Result: 13 of 13 admissible fixtures `MATCH_WITHIN_PR17_TOLERANCES_AND_PR18_DF_TOLERANCE`.** The supported claim is two-part and the parts must not be merged:

> The study-written Python CR2 **covariance, standard-error, t-statistic, and p-value** outputs agree with clubSandwich on the prespecified synthetic fixture matrix **under the PR #17 tolerances**. The continuous **Satterthwaite degrees of freedom** agree under a **separately prespecified PR #18 tolerance that was not preregistered in PR #17**.

The PR #17 tolerances were used exactly as written — none loosened, reinterpreted or replaced. Every fixture carries three separate statuses (`pr17_covered_fields_status`, `satterthwaite_df_status`, `overall_implementation_agreement_status`), so the df comparison cannot be read as a PR #17-preregistered one.

| Field | Worst absolute difference | Tolerance and provenance |
|---|---|---|
| CR2 covariance matrix | 1.735 × 10⁻¹⁶ | PR #17: rtol 1e-10 |
| Target variance | 3.990 × 10⁻¹⁷ | PR #17: rtol 1e-10 |
| Standard error | 1.943 × 10⁻¹⁶ | PR #17: rtol 1e-10 |
| t-statistic | 2.887 × 10⁻¹⁵ | PR #17: rtol 1e-9 |
| p-value | 8.882 × 10⁻¹⁶ | PR #17: rtol 1e-9 |
| **Satterthwaite df** | 7.105 × 10⁻¹⁵ | **PR #18: rtol 1e-8 — NOT preregistered in PR #17** |

**The continuous-df tolerance is a PR #18 tolerance and is never called preregistered.** The PR #17 set defines degrees of freedom as `exact_integer_equality` — a rule written for CR1's integer *G* − 1 that cannot express agreement on a continuous quantity. PR #18 therefore prespecified its own (rtol 1e-8), in source, before the comparison first ran, labelled `preregistered_in_pr17: false` and `prespecified_in_pr18: true`. The artifact keeps `pr17_covered_fields` and `pr18_covered_fields` disjoint and tags every field record with its own provenance, so nothing can silently migrate between the two sets.

**CR2 + Satterthwaite is described as implementation-validated only with that split provenance attached** — in the artifact, the report, the decision matrix and the PR body.

**The fixtures are never regenerated in R.** One generator — the committed `make_fixture` — is exported to a strict-JSON interchange file carrying only the outcome vector, design matrix, coefficient names, cluster labels, target coefficient, fixture id and expected refusal status. Missing values travel as JSON `null`, never as a sentinel number. Each fixture carries a SHA-256 over a language-neutral canonical string (`%.17g` per double, fixed field order) that **R rebuilds and re-verifies itself — all 18 confirmed**. Results travel back as `%.17g` strings: jsonlite writes doubles at ~15 significant digits, which would have made the reported discrepancies partly a measurement of the JSON writer rather than of the two implementations.

**Nothing was left to a default.** Intercept handling (the design matrix carries its own ones column; fitted with `~ 0 + .` so R adds no second intercept), coefficient and cluster ordering (first-appearance factor levels, not locale-dependent sorting), target coefficient, null value, confidence level, and matrix tolerance behaviour are all resolved and recorded. `na.action = na.fail` is set deliberately: R's default `na.omit` would have silently dropped the missing row and returned a number — a false agreement. One argument's resolved default is not visible from `formals()`, so `inverse_var` is computed **both ways** on every fixture; maximum difference 2.08 × 10⁻¹⁶.

**Refusals were reported, not forced.** Four fixtures are refused by both implementations through different diagnostics — Python screens condition number, column variance and residual variance explicitly; R discovers the same degeneracies as aliased coefficients in the QR fit. `F08_perfect_fit` is a genuine `REFERENCE_BEHAVIOR_DIFFERENCE`: R returns an estimate with a standard error of 3.97 × 10⁻¹⁷ after warning "essentially perfect fit", where Python refuses by a prespecified threshold. **Neither side was adjusted to make it agree**, and no fixture was deleted, reseeded or omitted.

**CR3 and the wild cluster bootstrap-t remain independently unvalidated.** `fwildclusterboot` was deliberately not installed, and CR2 agreement is never treated as evidence about either.

**What this supports, exactly:** *the study-written Python implementation agrees with the independent clubSandwich reference on the prespecified synthetic fixture matrix under the preregistered tolerances.* It is **not** evidence that CR2 is scientifically optimal or preferable, not an approval, not a power claim, and not a change to F5.

**One command reproduces it**, and exits nonzero on any unexplained mismatch:

```
python tools/hyp01_r_reference/run_validation.py --out <artifact.json>
```

Package installation and validation are separate phases: the install step may reach the pinned CRAN snapshot; the validation itself makes no network request.

**The decision matrix is now one coherent current-state document.** It previously carried the new result alongside pre-validation prose that contradicted it. Corrected throughout: the opening constraint section (which claimed no R runtime or reference exists), D1 option B (CR2 is implementation-validated, unapproved, production eligibility pending), D1 option C and D2 option C (CR3 is independently unvalidated — clubSandwich implements it, but PR #18 did not validate it), D2 option B (the BRL/CR2 path is independently checked; scientific selection pending), D3 option B (Satterthwaite implementation agreement established, with the PR #18 df-tolerance qualification stated inline), D4 (bootstrap still independently unvalidated — no bootstrap reference installed), D10 (the Satterthwaite figures are no longer unvalidated engineering output, but validated arithmetic still cannot establish an evidentiary threshold), D11 (option B is already done and pinned; it is a potential CR3 reference, but PR #18 did not validate CR3), and the summary row that claimed the preferred options were blocked. The rule that no method may be used for collection while independently unvalidated is retained and now applies to CR3 and the bootstrap, not to CR2.

It still separates three things that are easy to run together: implementation-validation evidence (established, with split tolerance provenance), a scientific method recommendation (offered only as a **proposal**, with alternatives and tradeoffs), and the final authorizer decision (**unchanged and `PENDING`**). Validation is not approval. All 59 checkboxes remain blank and no authorizer field is filled.

**The dependency lock is now truthful and enforced.** The lockfile pins R and **ten** packages; CI previously installed with `dependencies = TRUE` and verified only three of them. It now installs every locked package explicitly using only the classes required to run the reference (`Depends`, `Imports`, `LinkingTo` — never `Suggests`), verifies the exact R version, and iterates over **every** package in the lockfile, failing closed on absence or version difference. The dated snapshot was checked against the lockfile: all ten versions match. The Windows binary SHA-256 values are now scoped explicitly to the developer workstation's Windows install and no longer sit where they could be read as authenticating the Linux CI installation, which is pinned by (snapshot date + exact version) instead.

**Every external action is pinned to an immutable commit SHA**, not a movable tag: `actions/checkout` (v4 → `11d5960a`), `actions/setup-python` (v5 → `a26af69b`) and `r-lib/actions/setup-r` (v2 → `d3c5be51`). Tags are recorded in comments and the lockfile for readability only. Permissions, triggers, Python version, runner version, timeout and validation semantics are unchanged.

**Artifact reproduction in CI now compares every material field**, not just classifications: fixture identities and coverage, classifications and the three split statuses, tolerance provenance, all Python and reference numeric values, worst-difference summaries, refusal outcomes, behaviour differences, the reference package version, and the no-approval and F5 fields. Continuous quantities are compared under documented tolerances rather than bitwise — CI runs a different OS, R build and BLAS than the artifact was generated on — while discrete fields are exact.

Added `tools/hyp01_r_reference/` (exporter, R reference, comparison harness, driver, artifact verifier, lockfile), the validation artifact and report, `test_market_response_hyp01_r_reference_validation.py` (which executes the bridge rather than reading declarations and skips-with-notice where R is absent), and a **separate** `hyp01-r-reference-validation.yml` workflow. `market-response-tests.yml` is not modified: its permissions, triggers, Python pin, discovery glob and timeout are untouched.


## 2026-08-12 — PR #17 CI repair, an explicit supersession notice, and implementation status split into four facts

Offline apart from reading the GitHub Actions log. No method approved, no dated amendment, no signoff field completed. **F5 remains OPEN.** DELL unchanged. The corrected full-precision results are unchanged — every statistical section of the regenerated artifact is byte-identical to the one it replaces.

**⚠ The "2026-08-11 — HYP-01 inference feasibility" entry below is SUPERSEDED and its numbers must not be cited.** That entry's grid came from the unstable `hash()` seeding described in the corrective entry above and is not reproducible by anyone, on any machine. Its "0.090–0.110" CR1 range, its "≈11.5 / ≈7.5" Satterthwaite figures, its "Both are correct" perfect-fit claim and its "71 assertions" count are all withdrawn. Only the SHA-256-seeded run at **5,000 replications per null cell and 2,000 per effect cell** is current, as recorded in `GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json`. That artifact is authoritative **for this synthetic feasibility study only**; `GST_HYP01_ANALYSIS_LOCK_v1.0` remains the only operative scientific lock. The original entry's text is preserved verbatim under an adjacent supersession banner rather than edited, following the append-only convention used elsewhere in this repository (protocol v1.0 preserved byte-for-byte; superseded code renamed, not deleted).

**CI root cause — and it was not a statistical problem.** Run `31563766381` failed at the step *Discover and run every deterministic market-response test file*:

```
=== Running test_market_response_hyp01_inference_feasibility.py ===
  File ".../tools/hyp01_inference_feasibility.py", line 60, in <module>
    import scipy
ModuleNotFoundError: No module named 'scipy'
```

The test aborted at import, before a single assertion ran. The workflow installed `requirements.txt` (scoped by its own header to `gst_market_response/`) and the validator's `jsonschema`, and nothing else. Making the test *computational* in the previous commit gave it a real dependency on the runner, and therefore on `scipy` and `statsmodels`, which CI never had. Deterministic and environment-specific: it would fail identically on every rerun, and it says nothing about any published number.

**Fix.** A separate pinned `tools/requirements-hyp01-feasibility.txt` — kept out of `requirements.txt`, whose header states it covers `gst_market_response/` only — installed by a third `pip install` line. `statsmodels` is pinned exactly, because it is the reference that defines what CR1 validation means; `scipy` carries a floor, because it supplies the t-distribution used on both sides of a comparison made under preregistered tolerance, and CI runs Python 3.12 where an exact pin of the study's build may have no wheel. **No tolerance was loosened and no assertion weakened.** Nothing here supplies a CR2/CR3/bootstrap reference, so those remain blocked and F5 stays open.

The workflow's path filter also gained `tools/**`. The runner is imported by a discovered test, so before this a runner-only edit would not have triggered CI at all — the failure would have surfaced later, on an unrelated change.

**Implementation status was one boolean pretending to be four facts.** `executable_here: false` on CR2, CR3 and the bootstrap read as *these cannot run*. They run fine. What is absent is an independent reference, and therefore any basis for production use. The field is replaced by four independent ones — `study_implementation_runnable`, `independent_reference_available`, `independently_validated`, `production_eligible` — plus a `production_eligibility_status`. CR1 now records all four separately too: runnable, reference available, implementation agreement validated, **production selection not approved**, eligibility `PENDING_AUTHORIZER_DECISION`. A test asserts the concepts cannot collapse back into one flag, and that no document describes an unvalidated method as unable to execute.

**Provenance honesty.** The output digest previously excluded the entire `generated_by` block, which quietly left `runner_sha256` and the build id outside a hash whose name implied full coverage. It now excludes exactly two nondeterministic fields — `generated_at_utc` and `runtime_seconds` — and a committed `output_sha256_canonicalization` block states the rule, what is covered, and that the digest is a same-environment check rather than a claim of bitwise portability. A new `portability_probe` block stores full-precision CR1 outputs for four fixtures so another environment can recompute them: continuous fields compared under the preregistered tolerances, discrete fields under exact equality.

**Runner isolation language narrowed.** `assert_not_canonical()` screens the **output path** only. It is not a filesystem sandbox and cannot stop a future edit from adding an arbitrary read. The runner and artifact now claim what is true of this revision — *contains no canonical-read path, enforced by review and test* — instead of implying reads are impossible.

Changed: the workflow, the new requirements file, the runner, the regenerated artifact, the report, the decision matrix, this file and the test.


## 2026-08-11 — Corrective reproducibility audit: the feasibility study's numbers were not reproducible, and now are

Offline. No method approved, no dated amendment, no signoff field completed. **F5 remains OPEN.** DELL unchanged.

**The original defect.** The committed test read the generated inventory and Markdown and verified their *declarations*. The code that generated the fixtures, computed CR1, compared against statsmodels, computed CR2/CR3/Satterthwaite, ran the bootstrap, tested invariance and produced the simulation grid was never committed — it lived in a scratch file. **The published numbers were therefore not reproducible from the PR.**

**The runner is now committed** at `tools/hyp01_inference_feasibility.py`, clearly marked non-production with no analysis entry point. It contains the actual fixture generation, the study-written CR1/CR2/CR3/Satterthwaite/restricted-bootstrap implementations, the independent statsmodels reference call, the refusal rules and the Monte Carlo grid. It blocks network access before importing any numerical library, refuses canonical research paths by name, accepts a deterministic seed and writes only to a caller-supplied output path.

```
python tools/hyp01_inference_feasibility.py --reproduce --out <path.json>
```

**A second, worse defect surfaced while verifying the first.** Re-running the study into a fresh directory did **not** reproduce the committed artifact. Root cause: fixtures were seeded with `abs(hash(name)) % 100000`, and **Python randomises `str` hashing per process unless `PYTHONHASHSEED` is fixed**. Every run produced different synthetic data. The published numbers were not merely uncommitted — they were unreproducible in principle. Replacing it with a stable SHA-256-derived offset fixed it: an independent re-run now reproduces the artifact with identical discrete fields and a worst-case floating-point difference of **0.000e+00**.

**Monte Carlo precision corrected.** The earlier grid used 300 replications per cell, giving a 95% half-width of roughly ±0.03 — far too coarse for categorical language about size distortion. The plan is now fixed in the runner: master seed 20260811, nominal alpha 0.05, **5,000** replications per null cell, **2,000** per effect cell, Wilson score intervals, and an explicit claim rule applied **separately to each cell**. Every rate is reported with numerator, denominator, Monte Carlo standard error and interval.

**CR1 null-cell size**, the reference-validated estimator, at 5,000 replications:

| Cell | k/n | Rate | MCSE | Wilson 95% | Claim |
|---|---|---|---|---|---|
| G=24 balanced | 398/5000 | 0.0796 | 0.0038 | [0.0724, 0.0874] | evidence of over-rejection |
| G=24 unbalanced | 590/5000 | 0.1180 | 0.0046 | [0.1094, 0.1272] | evidence of over-rejection |
| G=12 balanced | 427/5000 | 0.0854 | 0.0040 | [0.0780, 0.0935] | evidence of over-rejection |
| G=6 balanced | 456/5000 | 0.0912 | 0.0041 | [0.0835, 0.0995] | evidence of over-rejection |

All four intervals lie entirely above 0.05, so the claim is permitted in each. The unbalanced cell is the largest observed rate, but **no cell is described as the "dominant" risk factor** — no prespecified between-cell comparison was performed.

**Unsupported language corrected.** The perfect-fit case previously said two "correct" implementations disagreed; without an independent reference that verdict is unsupported, and it now reads that both became numerically unstable near the noise floor and disagreed materially, so the configuration must be refused. CR2/CR3/bootstrap columns are labelled **`UNVALIDATED ENGINEERING OUTPUT — NOT METHOD-COMPARISON EVIDENCE`** and are never used to argue one method beats another. The absence of R is scoped to the **currently tested environment**, not to the repository in principle. Nothing infers that CR1 should be selected merely because it executes.

**Fixture semantics corrected.** Near-collinearity (full rank, ill-conditioned) and exact rank deficiency are now **separate fixtures with separate reasons**. Zero-variance predictors and perfect fit are **refusals, not matches**. Missing values fail before fitting. All five refusal thresholds were declared in the runner before the corrected rerun: `ILL_CONDITIONED_DESIGN`, `RANK_DEFICIENT_DESIGN`, `ZERO_VARIANCE_PREDICTOR`, `DEGENERATE_FIT_RESIDUAL_VARIANCE_AT_NOISE_FLOOR`, `NONFINITE_VALUE_PRESENT`.

**Bootstrap determinism corrected.** Seed variation is now tested by comparing a SHA-256 digest of the bootstrap t-statistic vector, not the p-value: the p-value lies on a coarse 1/(B+1) grid where two seeds can legitimately collide while having drawn entirely different samples.

**The test now computes.** `test_market_response_hyp01_inference_feasibility.py` (**85 assertions**) invokes the runner, regenerates fixtures, recomputes CR1 and independently calls statsmodels, recomputes all five refusals, recomputes permutation and relabel invariance and sign reversal, recomputes bootstrap seed behaviour, runs a reduced deterministic smoke grid in a temporary directory, and verifies the committed full-precision artifact's arithmetic — that every rate equals k/n, every MCSE matches the binomial formula, every Wilson interval recomputes exactly and every claim follows the preregistered rule. It also fails if the runner or simulation plan changes without the artifact being regenerated, if a Markdown number is absent from the inventory, or if any unvalidated method is described as validated. Routine CI runs the smoke grid only; the full grid takes two to three minutes and is reproduced manually.

Changed: `tools/hyp01_inference_feasibility.py` (new), the computational test, the regenerated inventory, the corrected report and decision matrix.


## 2026-08-11 — HYP-01 inference feasibility: only CR1 can be validated here; CR2, CR3 and the wild bootstrap are blocked

> ### ⚠ SUPERSEDED — DO NOT CITE THE NUMBERS BELOW
>
> **Superseded by the "2026-08-11 — Corrective reproducibility audit" entry above, as amended by the "2026-08-12" entry.** The original text of this entry is preserved verbatim below and nothing in it has been edited, per the repository's append-only convention. It is kept for auditability, not for reference.
>
> **Its numerical grid is invalid.** Fixtures were seeded with `abs(hash(name)) % 100000`, and Python randomises `str` hashing per process, so the run that produced these figures cannot be reproduced — by anyone, including on the same machine. The grid was also run at 300 replications per cell, a precision too coarse to support the categorical language used.
>
> **Specifically not to be cited:** the "0.090–0.110" CR1 null-rejection range; the "≈11.5 balanced to ≈7.5 unbalanced" Satterthwaite figures; the perfect-fit claim that "**Both are correct**"; the "71 assertions" test count; and the description of CR2/CR3/bootstrap as blocked in a way that implies they cannot execute.
>
> **The current figures** are the SHA-256-seeded run at 5,000 replications per null cell and 2,000 per effect cell, recorded in `GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json` and the corrective entry above. That artifact is authoritative **for this synthetic feasibility study only** — `GST_HYP01_ANALYSIS_LOCK_v1.0` remains the only operative scientific lock, and **F5 remains OPEN**.

Synthetic data only. **No method approved, no dated amendment created, no signoff field completed.** `GST_HYP01_ANALYSIS_LOCK_v1.0` remains operative and the proposed v1.1 remains `PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL`, both byte-identical. **F5 remains OPEN.** DELL unchanged.

**Why this study exists.** The merged proposal names **CR2/BRL plus Satterthwaite** as its provisional recommendation while recording that `statsmodels` does not supply it. This study asked the narrow engineering question: what can actually be implemented reproducibly, today, before the authorizer chooses.

**The answer is uncomfortable, and is reported as found.** **There is no R runtime on this machine** — `R` and `Rscript` are not on `PATH` and a filesystem search of the standard install locations returned nothing, so `clubSandwich`, `sandwich`, `lmtest` and `fwildclusterboot` are **absent, not merely unconfigured**. `linearmodels`, `wildboottest` and `pyfixest` are absent too. Working Python implementations of CR2, CR3, the Satterthwaite degrees of freedom and the restricted wild cluster bootstrap were written and run deterministically, **and are deliberately not labelled validated**, because the validation hierarchy requires agreement with an independently maintained implementation and comparing code to itself proves only self-consistency. **Nothing was installed to close the gap.** Each blocked method records the exact dependency and the exact validation procedure that would be needed.

| Method | Status |
|---|---|
| **CR1** + cluster-count finite-sample correction | **`IMPLEMENTATION_VALIDATED`** |
| CR2 / BRL + Satterthwaite | `IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE` |
| CR3 / cluster jackknife | `IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE` |
| Restricted wild cluster bootstrap-t | `IMPLEMENTATION_BLOCKED_REFERENCE_UNAVAILABLE` |

**CR1 was validated against `statsmodels` 0.14.6** — independently maintained, already installed, not written for this study — on 11 of 14 synthetic fixtures, matching covariance, standard errors, t, inference degrees of freedom and p-values. **Tolerances were preregistered before any comparison and were not revised afterwards.** Two fixtures were skipped by design and one is a documented refusal case. **This is not a reason to prefer CR1**: the synthetic grid shows it over-rejecting under the null in every configuration tested, and the decision matrix says so plainly.

**A comparison defect was found and corrected mid-study.** An initial pass reported a degrees-of-freedom mismatch on every fixture. The cause was reading the wrong attribute: **`statsmodels` keeps `results.df_resid = n − k` and exposes the inference degrees of freedom separately as `results.df_resid_inference = G − 1`**, which is what its p-values use. The comparison target was corrected; **the preregistered tolerances were not touched**, and the mismatch disappeared.

**Four refusal conditions were identified, none of which has a rule today.** The sharpest is **perfect or near-perfect fit**: with residual sum of squares at 3.7 × 10⁻²⁹, two implementations agreed on the covariance matrix to 2.6 × 10⁻³² and on standard errors to 8.4 × 10⁻¹⁷ — and still reported t-statistics differing by a factor of about 1.7, because at that scale a 10⁻¹⁶ absolute difference is a **75% relative** difference. Both are correct; the ratio β/se is simply not numerically identifiable. A production implementation must **refuse**, not report. The others are missing values (must be refused, never silently row-dropped), rank-deficient designs (a pseudo-inverse absorbs them silently), and zero-variance predictors.

**Eighteen synthetic fixtures** cover balanced and highly unbalanced clusters, singletons, one dominant cluster, near-collinearity, zero variance, perfect fit, missing values, row permutation, cluster relabelling, sign reversal, null and hypothetical positive effects, heavy tails, cluster-level heteroskedasticity, seed reproduction, seed variation and a below-design cluster count. Cluster labels are `CLUSTER_001`-style; **no real ticker appears anywhere**. Row-permutation and cluster-relabelling invariance held on all twelve runnable fixtures, and the bootstrap reproduced exactly under a fixed seed — **which is reproducibility, not validation, and is not counted as such**.

**A hypothetical design-sensitivity grid** was produced with generic standardized effects chosen before simulation. It is labelled throughout as an engineering fixture and **uses no repository effect estimate, because none exists**. It shows CR1 over-rejecting under the null (0.090–0.110 against nominal 0.050) and Satterthwaite degrees of freedom falling from ≈11.5 balanced to ≈7.5 unbalanced at 24 clusters. **It is not converted into a GST power claim and does not produce a minimum-cluster threshold** — that placeholder stands.

Added `GST_HYP01_INFERENCE_IMPLEMENTATION_INVENTORY_v1.0.json`, `GST_HYP01_SYNTHETIC_VALIDATION_REPORT_v1.0_DRAFT.md`, `GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md` (**16 decisions, 0 made**, every checkbox blank, authorizer and date `PENDING`; recommendations offered only where the offline evidence supports one, and withheld on the primary-estimator choice precisely because the methodologically preferred options are the blocked ones), and `test_market_response_hyp01_inference_feasibility.py` (**71 assertions**). The existing signoff template was **not modified and not filled in**.


## 2026-08-11 — Round-2 screenshot OCR audit: all 20 images machine-read, none carries market data

Offline only. **No live request, no browser, no screenshot manually viewed, no quarantined body reopened.** No ticker classification changed.

**Why this was needed.** The round-2 screenshots had never been read. Their cleanliness was asserted *structurally* — the DOM had passed the prohibition scan, so the image rendering that DOM was presumed clean. For CTSH and MSFT that inference was especially weak, because their retrieval-log records were lost and could not corroborate it. An unread image is not evidence of anything.

**Method.** Every committed screenshot was mechanically OCR'd with **Windows.Media.Ocr** (the Windows built-in engine, recognizer **en-US**) — already installed, nothing downloaded. The tallest image, MSFT at 1367×10790, exceeds the engine's 10000-pixel limit and was processed as **3 vertically overlapping tiles** so no text could fall in a seam. Token counts come from the engine's own `OcrLine`/`OcrWord` results; where the engine status is missing the image is `OCR_UNVERIFIABLE`, with **no fallback word split**. Recognized text was written to a temp file, scanned in memory, and deleted — it was never printed, returned or persisted, and **no matched numeric value was recorded anywhere**.

**A harness bug was fixed before any result was trusted.** `$result.Lines.Count` on a WinRT collection triggers PowerShell member enumeration and yields `Object[]` rather than an integer, which aborted the status line. WinRT collections are now materialised into real arrays before counting. A second, separate defect in the earlier probing — relative paths passed to `GetFileFromPathAsync`, which requires absolute ones — had briefly made the engine look unreliable; it was not.

**Result: 20 screenshots, 0 prohibited, 0 unverifiable.** 19 plain `OCR_CLEAN`, and 1 `OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH`. Three complete runs produced **identical** hashes, OCR status, token counts, value-rule hits, structural-rule hits and dispositions.

**The adjudication rule, authorized by Harshith Akurati.** A standalone navigation or heading phrase such as a stock-information link is **not itself prohibited market data**. A structural match becomes prohibited only when the same bounded region (±220 characters) also carries a corroborator: a recognized market value or metric, an explicit market-data attribution naming a financial-data provider, or a machine-detected populated quote-field structure — checked in the OCR output **and** in the committed DOM and accessibility artifacts. A structure-only phrase is retained as `OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH`, which counts as clean for the merge gate while **preserving the original rule name**. Nothing is erased or concealed.

**BRK-B carries the single advisory.** Its screenshot matched `quote_widget_word` — Berkshire's official home page carries a stock-information navigation link. **Zero value, zero attribution and zero populated-quote-field corroborators fired**, in the OCR output and in the committed DOM and accessibility text, across all three runs, and the structural match is explicitly recorded as uncorroborated. **BRK-B's round-two screening classification (`NO_ENROLLMENT_DECISION_REACHED`) is unchanged, and its screenshot was neither removed nor rewritten.**

**CTSH and MSFT are both plain `OCR_CLEAN`** — 241 and 1394 engine-recognized tokens respectively. This settles their *screenshot content*. It settles nothing else: **OCR does not recover their missing retrieval provenance**, and their timestamps, blocked-domain lists, allowed-host lists and canvas counts remain permanently unavailable.

**Stated limitation.** OCR reduces but does not eliminate image-recognition error. A negative OCR result is evidence of absence only to the accuracy of the recognizer; low-contrast, clipped, canvas-rendered or non-Latin glyphs may be missed.

Added `SCREENSHOT_OCR_AUDIT_ROUND2.json` — sanitized, carrying only filename, SHA-256, dimensions, engine and language, processing method, tile count, engine-sourced token and line counts, the rule names in each category, the per-rule corroboration flags and the disposition. Added `test_market_response_round2_screenshot_ocr_audit.py` (**77 assertions**), which exercises the adjudication rule against four synthetic fixtures — structure-only passing with an advisory, and structure-plus-price, structure-plus-volume and structure-plus-attribution each failing — verifies all 20 screenshots appear exactly once with hashes tying out to the images on disk, re-derives every disposition from the recorded rule names, confirms CTSH, MSFT and BRK-B specifically, and asserts that no OCR text, monetary value or percentage is persisted anywhere in the artifact.


## 2026-08-10 — Offline corrective audit of the round-2 sweep (five defects; no classification changed)

Offline only. **No new live request, no browser, no reopened quarantine body, no rewritten raw evidence.** No classification changed, because no committed evidence proved one wrong. Five defects in the round-2 *documentation and manifest* are corrected.

**1 — The retrieval claim was inaccurate.** The sweep entry asserted that no price or volume data "was retrieved or inspected". That is false: DVN and TTWO are exactly the exceptions, which is why both carry `COMPROMISED_ENROLLMENT_BLINDING`. Corrected everywhere to the precise statement: *prohibited market data was incidentally received for DVN and TTWO; it was not used in an enrollment decision, no numeric value was transcribed into canonical evidence, and both tickers were excluded for this cycle.* For **DVN** the values were **visually exposed** to the operator during ordinary retrieval, which has no suppression mechanism. For **TTWO** the populated content was **mechanically detected** by a scanner reporting rule names only, **without its values being presented** to the reviewer. No numeric value is reproduced anywhere.

**2 — The scan denominator was unlabelled, and the reported figure was wrong.** "0 pages failed the scan" was published without saying what it counted, and the sweep report claimed **20** rendered pages while committed logs hold **18** navigation records. Both are now stated explicitly, with every denominator separated: 24 locked tickers · 20 rendered artifact sets committed · 18 navigations with committed log records · 20 reaching the scan · 20 passing · 0 failing · 0 blocked before extraction · 2 static-evidence compromises · 16 access failures · 4 issuer-stated absences · 2 no-decision. The manifest now records plainly that the zero **does not** mean all 24 tickers passed, **does not** cover static evidence, **does not** cover access-failed pages, and **does not** include DVN or TTWO, whose exposures happened in ordinary retrieval and never reached the gate.

**3 — Two rendered artifact sets lack retrieval provenance.** CTSH and MSFT have committed DOM text, accessibility text and screenshots but **no retrieval-log record**: their log file was overwritten when the runner switched to per-batch log filenames mid-sweep. What is still derivable offline from the committed artifacts — the prohibition-scan outcome (both re-verified **PASS**, zero rule hits) and the artifact hashes — is recorded. What is gone — timestamps, blocked-domain list, allowed hosts, canvas count, per-request decisions — is named as gone. **Consequently the claim that MSFT's same-site stock-ticker component was blocked before its response was received is withdrawn**; it is not provable from committed evidence. What committed evidence does prove is that MSFT's DOM and accessibility text carry no populated prohibited value. Neither ticker's classification changes: both rest on their committed DOM text.

**4 — The `.gitignore` addition was removed.** Its patterns were narrowly scoped and hid nothing canonical (verified against manifests, rendered artifacts, screenshots, a hypothetical round-3 directory, the registry, event logs, markers, dossiers, observations, test logs and generic `.html`/`.json`/`.csv`/`.png`/`.log` paths — all remained visible to Git). But the quarantine lives **outside the repository**, so the patterns matched nothing that exists and served no repository-local purpose. Removed rather than kept as decoration implying a repo-local quarantine that does not exist.

**5 — CTSH wording strengthened.** It now states only that the URL fixed in advance failed under the current protocol and that root navigation was **unauthorized for section 1.1** — that permission belongs to sections 1.2 and 1.3 alone. It explicitly is **not** a finding that CTSH has no event. A **prospective scope correction** is recorded: re-derive that ticker's URL before the next scheduled cycle. The URL was not changed and not re-run.

**`screening_rows: []` is required by the protocol, not an omission.** Round 2 established no fiscal period for any ticker, so no candidate identity exists. The correction overlay's `canonical_pending_rule` permits a canonical `PENDING_OFFICIAL_DATE_UNAVAILABLE` row **only when ticker *and* fiscal period exist**, "so the screening-log schema can be satisfied without inventing a label"; runbook §5 directs that otherwise "the item stays in the round-2 manifest with the reconnaissance status `NO_ENROLLMENT_DECISION_REACHED`"; and the overlay defines that label as "a RECONNAISSANCE label, not a protocol disposition … deliberately outside the twelve codes … so it can never be mistaken for a screening decision." Appending the 24 classifications to `screening_rows` would manufacture 24 canonical dispositions the evidence does not support. **Nothing was backfilled and no schema was changed.**

**Language guard added.** "Zero enrollable candidates" may not be paraphrased as "no eligible events exist" or "no candidate exists". The 16 access failures are **unresolved source access, not negative eligibility findings** — nothing in round 2 establishes that any ticker lacks an upcoming earnings event. DELL's failed recheck is **not** confirmation of its registered date: no source was readable, so neither contradiction nor confirmation was observed.

**Verified unchanged:** all six quarantined bodies present and byte-identical to the pre-action manifest, hashed without being opened, none tracked by Git; committed quarantine records carry only filename, hash, byte length, source URL, reason and flags; the four classification totals (16/4/2/2) and unique coverage of all 24 locked tickers; zero enrollable candidates; DELL still the sole registered event, verified, unaltered. `test_market_response_round2_isolation_rule.py` gains assertions for the denominators, the totals, the language guard, the provenance gap and `.gitignore` narrowness.


## 2026-08-10 — Round-2 prospective-cohort sweep: 24 tickers, zero enrollable candidates

Executed **Monday 2026-08-10 17:12:42 America/Chicago**, after the 09:00 cadence gate. Scope was fixed in advance by the round-1 correction overlay; round 2 visited those URLs and nothing else. The isolation rule governing every classification below was committed **first**, in `801a325`, so it predates the classifications it governs.

**Result: 0 enrollable candidates, 0 human-review candidates, 0 canonical dispositions, 0 registry rows, 0 human verifications.** DELL remains the sole registered event, unaltered.

| Outcome | Count | Tickers |
|---|---|---|
| `ACCESS_FAILED` | **16** | AAPL, ABBV, ADBE, AMZN, BKR, CTSH, DELL, GME, GOOGL, LDOS, NKE, QCOM, SBUX, SYK, TSLA, UAL |
| `ISSUER_STATED_ABSENCE_CONFIRMED` | **4** | GPN, INTC, NCLH, STZ |
| `COMPROMISED_ENROLLMENT_BLINDING` (this cycle) | **2** | DVN, TTWO |
| `NO_ENROLLMENT_DECISION_REACHED` | **2** | BRK-B, MSFT |

**The dominant finding is that automated retrieval can no longer read most of these issuers.** Nine tickers served bot-verification interstitials that headless rendering cannot pass; six returned edge "Access Denied" or transport errors on every recorded URL. **Blocking was never weakened to get past any of them**, and no third-party source was substituted. The correction overlay already records direct observation by a named human as an acceptable alternative for the client-rendered set — that is now the path forward for nine tickers, and it needs a person, not an agent.

**Two pages did render and were read, both after passing the pre-extraction prohibition scan.** MSFT is the clean demonstration of the new rule working: the issuer's **own same-site stock-ticker component was blocked before its response was received**, the DOM and accessibility text came back free of prohibited values, and the page was only then inspected — it displayed no upcoming-events listing, which is recorded as no decision reached rather than as absence. BRK-B rendered the issuer's official home page, which carries reports, news releases, SEC filings and annual-meeting information but **no events calendar and no dated upcoming earnings event**; that too is a discovery outcome, not issuer-stated absence.

**Four issuers still state absence in their own words.** GPN, INTC, NCLH and STZ each display, under an "Upcoming Events" heading, the verbatim sentence *"There are no upcoming events scheduled at this time."* Every dated entry on those pages sits under "Past Events" and none was promoted to a candidate — the round-1 error that the evidence audit corrected.

**One scope defect surfaced.** The URL fixed in advance for CTSH now returns the issuer's own 404 page; it no longer serves an events calendar. Section 1.1 carries no navigate-from-issuer-root permission — that is granted only to sections 1.2 and 1.3 — so no substitute URL was sought and CTSH is recorded as an access failure. The next cycle's scope should be re-derived for this ticker.

**DELL: the recheck could not be performed.** Both recorded URLs failed under ordinary retrieval and the render attempt returned "Access Denied". Because no official source was readable, **no contradiction was observed**, and the registration was not altered, amended or re-verified. It stays on the cadence for amendment detection only.

**Blocking.** Deny-by-default interception was installed **before navigation** on every rendered page. Market-data paths were denied on any host, first- or third-party; analytics and financial-data vendors were denied by host; all remaining cross-site requests were denied. Bot-verification infrastructure was permitted as a resource necessary to render the issuer's own page — it is not a quote, chart, market-data, analytics or financial-data provider, and permitting it changed no outcome, since the challenges still did not pass. Blocked requests are logged as registrable domain and normalized path only; **no query string and no response body was logged**.

**Quarantine.** Six retrieved bodies are held outside version control and will not be re-inspected: four containing populated prohibited values (three DVN, one TTWO) and two Berkshire Hathaway bodies whose brotli encoding this environment could not decode, and which therefore could not be *verified* clean. Their SHA-256, byte length, source URL and reason are recorded in the manifest. **No observed price, percentage change or volume appears in any artifact, log, commit message or report.**

Artifacts: `Live Signal Engine/Cohort_Screening_Round2/` — `SWEEP_MANIFEST_ROUND2.json` (24 rows, each ticker exactly once, each with its governing rule), `HUMAN_REVIEW_REQUIRED_ROUND2.json` (empty queue, plus what needs a human next cycle), the static and rendered retrieval logs, 14 verified-clean static bodies, and rendered DOM text, accessibility text and screenshots for every page that passed the scan. Round-1 artifacts and the correction overlay are untouched — round 2 adds, it never rewrites.

**Prohibited market data was incidentally received for DVN and TTWO. It was not used in an enrollment decision, no numeric value was transcribed into canonical evidence, and both tickers were excluded for this cycle as `COMPROMISED_ENROLLMENT_BLINDING`.** For DVN the values were **visually exposed** to the operator; for TTWO the populated content was **mechanically detected without its values being presented** to the reviewer. No such data was retrieved or inspected for any other ticker, and none was used as an enrollment input anywhere. No model, plot, backtest or strategy test was run. No event state changed and no registration occurred.

*(Corrected 2026-08-10 by the offline corrective audit below. This paragraph previously read "No attention, price, volume … was retrieved or inspected", which was inaccurate — DVN and TTWO are precisely the exceptions.)*


## 2026-08-10 — Round-2 runbook clarification: what "isolated" means (additive; no methodology changed)

**This entry records a methodological decision only. It is committed deliberately *before* any remaining round-two enrollment classification, so the rule predates the classifications it governs.** No screening decision, registry row, event state or statistical rule changes here.

**The conflict that forced it.** The round-two sweep halted partway through. Devon Energy's investor events calendar — located correctly from the issuer's own navigation — renders a live quote widget carrying price, percentage change and volume on the same page as the event listing. Runbook §4 requires an immediate stop when prohibited data cannot be isolated from the event listing; §2's only remedy is suppressing market-data widgets, which is a *renderer* capability, and §2 routes every set other than §1.1 through *ordinary retrieval*, which has no suppression mechanism at all. The rule anticipating the problem supplied a remedy the mandated method could not use. That is a genuine ambiguity, and it was escalated rather than improvised around.

**The decisions, made by Harshith Akurati and encoded additively as runbook §4.1.** §4 governs **actual exposure**; §2 supplies the **preventive mechanism**. Prohibited data counts as **isolated only if its network requests were blocked before their responses were received and before any value populated the rendered page** — isolation is a property of what never arrived, not of what was subsequently avoided. Ignoring, cropping, masking, excluding from extraction or omitting an already-rendered widget **does not restore blinding**. Pre-render request blocking is permitted for **every** issuer page regardless of whether the ticker was originally assigned ordinary or renderer retrieval; this is a retrieval-method permission that expands no source set and reaches no new host. If a prohibited value populates the DOM, accessibility tree, screenshot, extracted text, console output **or saved evidence**, that ticker stops and takes a **cycle-specific `COMPROMISED_ENROLLMENT_BLINDING`** disposition. Blocking may never be weakened to obtain a listing; if blocking prevents the listing rendering, the existing access-failure or unresolved rule applies. Before any extraction, an automated scan must confirm the rendered DOM, accessibility text and screenshot carry no populated quote, price, percentage-change, volume, chart-value, options, surprise, analyst or outcome field — and **no page may be inspected manually until that scan passes**.

**The compromised disposition is cycle-specific.** It is not a permanent exclusion, not a registry amendment, not an event-state transition, and not a claim that any existing registered event is compromised. An affected ticker returns to the ordinary cadence next cycle.

**Two tickers are affected this cycle, not one.** DVN was the exposure that halted the sweep. Applying the newly encoded rule to the already-collected static evidence surfaced a **second**: the Take-Two investor root page carries a populated quote in its saved body. Under §4.1 an exposure in *saved evidence* counts, so **TTWO takes the same cycle-specific disposition as DVN**. It was found by a mechanical scan that reports rule names only; no value was displayed to a reader, and none is recorded anywhere.

**Quarantine.** Six retrieved bodies are held **outside version control** and will never be re-inspected: three DVN pages and one TTWO page containing populated prohibited values, plus two Berkshire Hathaway bodies whose brotli-encoded bytes could not be decoded and therefore could not be *verified* free of such values. Only SHA-256, retrieval timestamp, source URL and reason are carried into the audit trail. `.gitignore` now blocks the quarantine path so those bytes cannot be committed by accident. **No observed price, percentage change or volume appears in any artifact, log, commit message or report.**

**Unchanged, and asserted by test.** The locked 24-ticker universe, the Monday 09:00 America/Chicago cadence, the 2026-09-01 → 2027-05-31 collection window, the 5-XNYS-session registration lead, the four permitted official source types, the enrollment criteria, the outcome firewall and every statistical rule. `screening_rows` remains `[]`, and the registry still holds exactly one row: the verified DELL registration.

Added `test_market_response_round2_isolation_rule.py` (**32 assertions**) in the repository's established location for cohort and runbook invariants. It asserts the precedence and definition, that post-render remedies are declared insufficient, that the disposition is cycle-specific and is not a registry amendment, that the pre-extraction gate exists, that **no committed round-2 artifact contains a populated prohibited value and none is left undecodable and therefore unverifiable**, that the governance parameters above are untouched, and that neither DVN nor TTWO reached the registry. It runs offline with sockets blocked.
## 2026-08-10 — Offline GST search-construct validity audit, all 24 tickers (zero Trends calls, zero query changes, F5 still open)

**Offline semantic and implementation audit only.** No Google Trends call, no `pytrends` invocation, no search-volume source of any kind, and **no production query was changed**. Gap-audit item **F5 remains OPEN** — this closes its offline half.

**What the production query actually is.** Traced mechanically from `LOCKED_24_TICKER_UNIVERSE` through `process_ticker()` (line 710) to `pt.build_payload([term], …)` (line 401): **the query for every one of the 24 tickers is the bare ticker symbol, verbatim.** There is no company-name mapping, no Google topic entity, no qualifier, no alias and no fallback anywhere in the repository — the ticker *is* the query. Parameters are identical for all 24: `geo="US"`, `gprop=""` (plain Web Search), `cat=0` (All categories), a 300-day ISO timeframe computed at runtime, capitalization preserved, and no project-side URL encoding.

**Documentation matches implementation exactly, and no mismatch was found.** `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md` §1 specifies "the bare ticker symbol string … no qualifier, no company name, no `<TICKER> stock` suffix", `US`, `""`, `0`, 300-day lookback — precisely what the code sends. The historical path (`GST_FixedWindow_PerEvent_Canonical.py` line 110) issues the same bare-ticker query with the same parameters, so historical and prospective collection are consistent. The panel's `TICKERS` list is identical in order and content to the locked universe constant.

**Risk distribution: 13 LOW, 8 MODERATE, 3 HIGH, 0 implementation-unclear.** Every query was established, so nothing failed closed.

**Three high-risk queries.** `BRK-B` is the only query containing punctuation and the only issuer with a second listed class: hyphen tokenization cannot be determined offline, `BRK.B` and `BRK/B` are competing spellings, and a sparse or empty series would be recorded downstream as missing data rather than as a construct failure. `GOOGL` is one character from the most-searched string on the web, with leakage of unknowable magnitude, plus `GOOG`/`GOOGL` class ambiguity. `GME` collides with **Graduate Medical Education**, a common US acronym, and separately carries a meme-driven retail-attention regime in which spikes are generated by social-media dynamics rather than company information — the clearest case in the universe where lexical uniqueness does not deliver construct validity.

**Eight moderate.** `STZ` is the standard abbreviation for **streptozotocin** and `SYK` for **spleen tyrosine kinase**; neither string resembles its issuer's name, so searchers interested in Constellation Brands or Stryker are unlikely to type them while biomedical users type them for unrelated reasons. `DELL` is an ordinary English word whose brand traffic measures product and support demand rather than investor attention — worth noting because DELL is currently the sole registered prospective event. `BKR`, `DVN`, `GPN`, `NKE` and `UAL` carry short-string, brand-adjacency or institutional-abbreviation risk.

**A finding that applies to the thirteen LOW tickers too.** A bare ticker systematically measures an investor-framed slice of attention, not public attention: nobody curious about Apple types `AAPL`. That may be exactly what the study wants, but it is a choice that was never stated as one, and it is not what "abnormal public attention" implies in the project's own framing.

**Lexical ambiguity is not construct validity, and this audit establishes only the former.** A `LOW` label means no obvious semantic collision was identified offline — the absence of one kind of counter-evidence, not evidence of validity. Offline screening can identify a collision but cannot size it: that `STZ` also means streptozotocin is a fact, whether that traffic is 0.1% or 60% of `STZ` volume is unknowable here. Confidence is recorded as `LOW` for all eleven MODERATE/HIGH tickers for exactly that reason.

**Six candidate comparison forms per ticker are recorded as proposals only** — none retrieved, none compared, no winner selected, no production mapping updated. Google topic entities were **not** enumerated because that requires a live Trends suggestion call, so every topic slot reads `NONE_KNOWN_FROM_REPOSITORY_EVIDENCE` rather than a guess. A future comparison must pre-declare its criterion; **selecting a query by its association with returns would invalidate the study**, and the review template states that prohibition explicitly.

**No outcome was inspected.** `results: null`, `frozen_event_ids: []`, eligible counts 0/0/0, DELL still the sole registered event at `REGISTRATION` / `verified`. No screening, provider call, panel run, browser session, event transition, observation, analysis or strategy test occurred. No market price, news, earnings outcome or historical correlation was used to assess any query's risk.

**Any future query change would be a methodology change** requiring a new dated methodology version that preserves the current one byte-for-byte, plus a decision about the existing historical series — which were all collected with the bare-ticker query, and would otherwise become non-comparable with prospective ones.

Added: `GST_SEARCH_CONSTRUCT_INVENTORY_v1.0.csv` (24 rows, 30 columns), `GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json` (same 24 records, generated from one source of truth so the two cannot drift), `GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_DRAFT.md`, and `GST_SEARCH_CONSTRUCT_REVIEW_TEMPLATE_v1.0.md` (every field `PENDING`, no checkbox preselected, no reviewer named). Query construction, the ticker universe, panel code, methodology, HYP-01, the hypothesis registry, cohort protocol, event registry, specifications, source modules, tests, workflows, README, North Star and the gap audit are **unchanged and byte-identical**.
## 2026-08-09 — HYP-01 statistical-method review packet and PROPOSED v1.1 amendment (nothing approved, nothing activated)

**`GST_HYP01_ANALYSIS_LOCK_v1.0` remains the authoritative lock.** This entry adds a **proposal** and a **request for review**. It approves nothing, activates nothing, and changes no methodology. The proposed v1.1 files carry the status `PROPOSED_PENDING_HUMAN_AND_METHODOLOGIST_APPROVAL` and are explicitly barred from being described as active, registered, approved, frozen or authoritative.

**No statistical choice has been approved.** The gap audit merged earlier today identified C6 (cluster-robust covariance estimator), C7 (finite-sample inference), E3 (multiplicity) and C9 (sector fixed-effect encoding) as unresolved scientific decisions due **before the first prospective observation**. This work prepares them for a qualified reviewer; it does not decide them. Claude authored the packet and may not supply any approval it requests.

**Why the decisions matter here.** The locked design is n = 60 eligible events over a universe of at most 24 tickers, unbalanced by construction. Cluster-robust inference is asymptotic in the number of clusters, and its small-sample bias runs *downward* — inflating apparent significance, the worst direction for a confirmatory test. Published Monte Carlo evidence (Cameron & Miller 2015, Table 2) reports Imbens–Kolesár effective degrees of freedom averaging 9.4 at twenty nominal clusters. A synthetic exercise on data of this project's shape — fixed seed, no real ticker, no project value, run outside the repository and deleted afterwards — put the effective degrees of freedom at roughly 11 balanced and 7 unbalanced at 24 clusters, not 23.

**Provisional recommendation, labelled `PROPOSED_NOT_APPROVED`.** CV2 (bias-reduced linearization) clustered on ticker; Satterthwaite/Bell–McCaffrey degrees of freedom computed from the realized design; alpha 0.05 two-sided unchanged; the realized degrees of freedom, effective cluster count and a CV1 reference standard error all reported alongside the coefficient; wild cluster bootstrap as a labelled sensitivity analysis that may never rescue or overturn the primary result; no multiplicity adjustment for the single primary confirmatory test; sum coding for the secondary model's sector fixed effects. **The estimand is unchanged in every option considered** — this concerns how uncertainty is quantified, never what is estimated.

**Two places the packet argues against its own starting position.** CV3 with t(G−1) is recorded as a genuine competitor rather than an also-ran: Cameron & Miller's published rejection rates are comparable and its degrees-of-freedom rule is simpler and more reproducible, so the signoff form asks the reviewer directly whether to prefer it. And the wild cluster bootstrap did *not* dominate CV2 + Satterthwaite at small cluster counts in that same table, which is the evidential reason it is proposed as sensitivity rather than primary.

**One number was deliberately not written.** If eligible events concentrate in a few tickers, the effective degrees of freedom could fall very low. Whether there is a floor below which no confirmatory conclusion should be drawn — and what the consequence should be — is left as `PLACEHOLDER_PENDING_METHODOLOGIST`. Inventing a threshold would be exactly the failure the gap audit exists to prevent: a value that looks locked because it appears in a file, chosen by an author with no standing to choose it.

**A structural inversion in v1.0 is identified and proposed for correction.** v1.0 defers the cluster-covariance *option string* to the event-60 freeze while leaving the estimator unspecified — which means the statistical rule would be chosen implicitly by whoever types the option string. The proposal separates the rule (fixed before the first observation) from the record (transcribed at the freeze). A rule is chosen by a human on scientific grounds; a record is transcribed from the environment.

**A practical obstacle is recorded rather than glossed.** CV2 with Satterthwaite degrees of freedom is **not available in statsmodels 0.14.6**, this project's regression library — verified by reading the installed package's own docstring. Adopting it requires either an R/clubSandwich dependency or a Python implementation validated against a published reference, and that work must complete before the first observation, not at the freeze.

**No outcome was inspected and none exists.** `results: null`, `frozen_event_ids: []`, eligible-event counts 0/0/0, DELL still the sole registered event at `REGISTERED`. No screening was run, no provider called, no panel executed, no event transitioned. The synthetic demonstration used pseudo-random values only and no project observation entered it. No power analysis was performed.

**A separate approved amendment is required before the first pre-event capture.** Activation needs a named methodologist's decisions on C6, C7 and E3, a decision or explicit declination on the minimum-cluster rule, Harshith Akurati's approval, and a further dated commit — all before the first HYP-01-eligible prospective pre-event capture, and none of it at the event-60 freeze. Until then v1.0 governs.

Added: `GST_HYP01_STATISTICAL_METHOD_REVIEW_PACKET_v1.0_DRAFT.md`, `GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json`, `GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED_DRAFT.md`, `GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md` (every field `PENDING`; no reviewer named, no approval recorded), and `GST_HYP01_METHOD_REVIEW_REQUEST_v1.0_DRAFT.md` (no recipient named, not sent). The v1.0 lock, hypothesis registry, cohort protocol, eligibility and freeze rules, display gates, event registry, specifications, field dictionaries, gap audit, North Star, README, source code, tests and workflows are all unchanged and byte-identical.


## 2026-08-09 — Truthful public front door: README rebuild, North Star, institutionalization blueprint, preregistration gap audit

Documentation and governance only. **No methodology, threshold, formula, protocol, registry, gate, specification or evidence artifact was changed.** No screening, data collection, analysis or strategy testing was performed, and no research process was run.

**Root `README.md` rebuilt.** The previous front page described a 2025 study of 15 retail-heavy tickers, weekly GST spikes ≥ 85 over 2014–2019, and an intention to tune trading rules. That framing is obsolete and is now labelled as history rather than presented as current methodology. The new README leads with a status box stating plainly that a retrospective reconstruction exists **with an unresolved point-in-time limitation**, that the prospective cohort is underway with **1 registered event and 0 outcomes analyzed**, that **no profitable strategy has been demonstrated**, and that options benchmarking is **unavailable and unverified** while the project can still proceed on core-only measurement. It reproduces HYP-01 from its lock rather than paraphrasing it, generates the 24-ticker list from `LOCKED_24_TICKER_UNIVERSE`, and carries an explicit "What this project does not claim" section.

**Failures are on the front page, not buried.** The straddle economics appear as a two-row table showing the original `+145.5%` median beside the recalibrated `−10.7%`, so the invalidated figure can never be cited without its reversal. The failed point-in-time check, the quarantined n=148 look-ahead reconstruction, the two dead out-of-sample hypotheses, the preserved Phase 2 transport failures, the blinding-compromised MSFT pilot, and round one's own canonical-disposition over-claim are all linked from the README.

**Added `PROJECT_NORTH_STAR_v1.0_DRAFT.md`** — the umbrella identity (attention measurement, with any instrument strictly downstream), the central question, the five-layer separation and the forward-only wall between layers, the market-response localization framework expressed only in fields the system already defines, seven **unvalidated** candidate equity applications with an explicit prohibition on calling any of them arbitrage or an edge, the development-versus-holdout cycle, the four deliberately separate interfaces, and success criteria that a null result satisfies.

**Added `INSTITUTIONALIZATION_BLUEPRINT_v1.0_DRAFT.md`** — a fourteen-stage plan giving each stage its objective, current status, existing evidence, missing dependency, next authorized action, deliverable, acceptance criterion, methodology-change risk and required human approval. It marks what already exists so nothing is rebuilt, and it represents OSF, Zenodo, WRDS, OptionMetrics, Cboe, Google Trends API access, reviewers, partners and external datasets as **proposed future dependencies, none obtained**.

**Added `PREREGISTRATION_GAP_AUDIT_v1.0.md`** — a per-element audit across sample definition, provenance, hypothesis and outcome, data handling, multiplicity and stopping. Twenty-eight elements are locked and reproducible from the repository. Eleven require a human or external methodological decision, of which three — the cluster-covariance estimator variant, the finite-sample correction at roughly 24 clusters, and the multiple-testing treatment currently marked `PENDING_SEPARATE_ANALYSIS_LOCK` — could each change whether HYP-01 is reported as significant. **No missing value was invented to complete a table**; each gap names the decision, its severity, whether resolving it changes methodology, and its deadline relative to the freeze.

All three new documents are drafts and change nothing that is locked. The DELL registry, every protocol and specification, the hypothesis registry, the HYP-01 lock, the round-1 evidence and every production module are byte-identical.

**Correction, same day, applied additively — the paragraphs above are left standing so the error stays visible.** A corrective audit of the above found four defects in the documentation, all now fixed. None of them touched a scientific artifact.

*Gap count was miscategorized.* The audit reported "11 requiring a human decision" while mixing three different kinds of thing into one list. `F1` (predictor form) was listed as unresolved when the HYP-01 lock had **already fixed it** — `gst_zscore`, continuous, entered on its natural scale, unthresholded, with no confirmatory transform; the registry's older "continuous versus threshold form" entry was superseded by that lock, and the only rank-related item remaining is the definition of a *secondary sensitivity* analysis. `B4` (statistics package, version, cluster-covariance option string, seed) is an **operational freeze record** — a value to be recorded, not a decision to be made. `E9` (named analysis authorizer) is an **administrative assignment**. Counting these three as methodological debt inflated the apparent gap. The audit now classes every row as `SCIENTIFIC_DECISION` (11), `OPERATIONAL_FREEZE_RECORD` (1), `OPERATIONAL_ASSIGNMENT` (1) or `RESOLVED` (28), totalling 41, and states the three counts separately. The eleven genuine decisions are A9, B3, C6, C7, C9, E3, E8, F2, F3, F4 and F5.

*Deadlines were wrong in a way that would have broken the preregistration claim.* The first version let the primary estimator and inference rules sit unspecified until the event-60 freeze. **A study cannot call itself preregistered while its primary estimator and inference procedure are still open.** C6, C7, E3 and E8 now fall due **before external preregistration and before the first HYP-01-eligible prospective observation**, and may never be resolved using prospective outcome data. What may still be settled at event 60 is narrow and explicitly listed: the exact event IDs, and the software package, version, option strings, seed and analysis-code commit that *express* an already-fixed rule. Analysis code may be written later only if it mechanically implements that fixed rule and is tested exclusively on synthetic fixtures or explicitly permitted historical material. A9 is likewise constrained — any design-sensitivity or power analysis must precede prospective outcomes, use externally justified or clearly hypothetical effect sizes, never use observed project results, and never silently revise the locked `n = 60`. **No power analysis was performed.** One consequence is recorded openly in the audit: the HYP-01 lock currently schedules the cluster-covariance option string at `TO_BE_FROZEN_AT_EVENT_60` and bundles it with package and version, so splitting the statistical rule from the software record **requires a dated lock amendment authored by a human**. That amendment was not made here.

*The development/holdout language contradicted itself.* The North Star's table called prospective events collected after the lock "holdout data" while the next paragraph called everything before the event-60 freeze "development". Section 10 is now four unambiguous parts. **Development material** is synthetic fixtures and explicitly labelled historical/reconstructed artifacts, with no prospective outcomes ever. The **confirmatory evaluation cohort** is the first 60 eligible prospective events, governed from event 1 by the pre-data lock, with outcomes gated and unexamined until the full set and the analysis environment are frozen — these are **never development data at any point**. The **event-60 freeze** fixes event IDs, analysis commit, environment and reproducibility metadata; it does not retroactively convert development material into holdout data and does not authorize changing the statistical rule. The **extension cohort** is separately labelled and is **not automatically a formal holdout test** — it becomes one only under a new dated protocol written before those outcomes are examined. The same vocabulary was applied to blueprint Stage 14 and to the North Star's §9 prohibition and §13 governance rule.

*Three overclaims removed.* "A validated-on-reconstruction relationship" became "a retrospective association was observed within that reconstruction", followed by the statement that the reconstruction has a failed point-in-time validity check and is not prospective confirmation. "The attention→price-move relationship was unaffected by that reversal" became "the options-cost recalibration reversed the strategy economics; it does not establish or invalidate the separate attention-response hypothesis". The README's "so this is not small-sample noise" was the strongest claim and needed care rather than deletion: the status document does assert it verbatim, so the sentence is now **attributed** to that document rather than asserted by the README, with the explicit note that no formal test in this repository rules sampling noise out — and the previously omitted **Recalibrated v1** row (n=37, markup 3.6516, 39.5%, −16.6%, −0.298, −85.73%) is now shown alongside the other two so a reader can judge the stability argument directly. "Downstream of validated evidence" became "downstream of evidence that survives the prospective test".

*The two deadlines are now stated side by side* in the README, the blueprint and the audit: **Monday 2026-08-10 09:00 America/Chicago** is the next authorized screening sweep and analyzes no outcome; the statistical-rule and construct-validity decisions are due **before the first prospective pre-event capture**, whose anchor falls in the 2026-09-01 → 2027-05-31 window. A sweep that enrolls a candidate brings the capture deadline closer; it never pushes it back.

Documentation only. The HYP-01 lock, hypothesis registry, cohort protocol, event registry, every specification, source module, test, workflow and evidence artifact are **unchanged and byte-identical**. DELL remains the sole registered event at `REGISTERED`, and zero prospective outcomes have been analyzed.

**Second correction, same day, again additive — the README roadmap.** A consistency search across the five documents found the contradiction in exactly one place, `README.md`, and both defects were in its roadmap.

*External preregistration was listed under "Only after evidence."* That contradicted the corrected gap audit, the institutionalization blueprint, this changelog's own preceding paragraph and the requirement that the primary statistical rule be fixed before the first prospective observation — a preregistration filed after the evidence is not a preregistration. The roadmap is now four ordered, gated stages. **(1) Before the first prospective pre-event capture:** resolve C6, C7, E3, E8 and F5, decide A9, create the required dated HYP-01 lock amendment, obtain methodological review where available, and submit the external preregistration if the project intends to call the study externally preregistered. **(2) During prospective collection:** run only the fixed cadence, register eligible events, capture under the locked rules, keep outcomes gated. **(3) At the 60th eligible event:** freeze the event IDs, freeze the analysis code and environment, verify all gates, run the locked primary analysis once. **(4) After evidence:** replication, public reporting, a dashboard built on authorized results, and any separately preregistered strategy or product work. Blocked dependencies (HYP-02's surprise path, HYP-03's decay measurement, options access) are listed separately because they are not stages in that sequence.

*"Target ≥ 60 registered events" conflated registration with eligibility.* HYP-01 requires the first **60 HYP-01-eligible** events — enrolled under the cohort protocol, eligible for the core class, strict v0.2 core passed, D1 passed, `gst_zscore` present with successful GST provenance, `abs_overnight_gap` non-null, and a `BMO` or `AMC` release. A registered event failing any of those is not eligible, so the project may need **more than 60 registered events** to reach 60 eligible ones. **How many more is not projected** — no prospective evidence exists yet to estimate how often capture and data-quality gates fail, and inventing a figure would be a fabricated projection. **No registered event is ever deleted for being ineligible:** it stays in the registry with its disposition recorded and simply does not count toward the 60, because deleting it would be exactly the selection the append-only registry exists to prevent.

The consistency search covered `external preregistration`, `after evidence`, `after results`, `registered events`, `eligible events`, `n = 60`, `first 60`, `event 60` and `freeze` across all five documents. The other four were already consistent and were not modified. No lock, registry, protocol, source file, test, workflow, evidence artifact or research state was touched.


## 2026-08-09 — Round-1 evidence audit and correction overlay (additive)

Offline audit of the round-1 reconnaissance evidence. No retrieval, no candidate lookup, and **no round 2** — protocol v1.1 fixes the next sweep at Monday 09:00 America/Chicago, and this audit is deliberately not an unscheduled re-screen.

**Originals preserved, mistakes included.** `sweep_raw_round1.json`, `sweep_raw_round1_pass2.json`, `SWEEP_MANIFEST_ROUND1.json` and `HUMAN_REVIEW_REQUIRED_ROUND1.json` are hash-locked and byte-identical; neither prior commit was amended, squashed or rewritten. The overlay is authoritative for *interpreting* round 1 and never pretends the original bytes were different.

**Correction A — no unsupported canonical disposition.** Round 1 wrote `PENDING_OFFICIAL_DATE_UNAVAILABLE` for 23 tickers. That is a *canonical protocol disposition*, and using it presupposes a candidate identity — ticker **and** fiscal period — so the screening-log schema can be satisfied. No fiscal period was established for any ticker, so the effective `proposed_disposition` for every non-DELL ticker is **`null`** with the status **`NO_ENROLLMENT_DECISION_REACHED`** — explicitly *not* one of the twelve protocol dispositions. Every such ticker remains eligible for the next scheduled sweep. No fiscal period was fabricated to make the schema fit.

**Correction B — source-type audit.** All 77 checked URLs were re-classified: 21 `PERMITTED_SOURCE_OF_RECORD`, 26 `RECONNAISSANCE_ONLY`, 18 `ACCESS_FAILED`, 11 `NAVIGATION_ONLY`, 1 `INVALID_OR_UNRELATED`. The known DVN error (`/sustainability/environment/spill-prevention`, recorded as an IR events calendar) is corrected to `INVALID_OR_UNRELATED` and cannot support any conclusion. Its **root cause** is recorded: pass 2's link filter tested `event` as a substring and **"pr-event-ion"** matched. The whole evidence set was searched rather than only DVN, yielding 18 misclassification corrections — company homepages and IR landing roots as `NAVIGATION_ONLY`, press-release and news indexes as `RECONNAISSANCE_ONLY`.

**Correction C — the SEC submissions index.** All 24 `data.sec.gov/submissions/CIK….json` reads are `RECONNAISSANCE_ONLY`, **not** `sec_filing_8k_earnings_date`. The index is filing metadata; a specific 8-K qualifies only once opened and found to state the future date and timing explicitly. An accession number, filing date or `Item 2.02` label establishes nothing, and no prior filing metadata may influence enrollment. **No filing content was opened in round 1.** The `recent_8k` metadata stays in the raw artifact but is marked unused and prohibited from the effective decision.

**Correction D — the renderer set, recomputed not assumed.** The original queue said "ten calendars" without naming them; the real figure is **9 tickers / 11 URLs**, and three categories the original conflated are now separated: **8** access-failure tickers, **4** issuer-stated-absence tickers, and **2** where round 1 never located an events calendar at all (a discovery gap, neither failure nor absence). All 23 non-DELL tickers are bucketed exactly once.

**Corrected conclusion.** 0 enrollable candidates, 0 canonical dispositions, 0 registry rows, 0 human verifications, 1 unchanged enrolled event (DELL). Round 1 is **reconnaissance evidence**, not a completed canonical screening decision for 23 unnamed fiscal periods. Retrieval failure is never described as issuer-confirmed absence.

Added: `ROUND1_EVIDENCE_AUDIT.md`, `ROUND1_CORRECTION_OVERLAY_v1.json`, `ROUND2_RENDERER_RUNBOOK.md` (offline; scheduled, not executed), `build_correction_overlay.py`, and `test_market_response_round1_correction_overlay.py` (**85 assertions**). Two pre-existing assertions that compare against `git show HEAD:` now report NOT APPLICABLE in a detached `git archive` export instead of failing there; the declared-hash lock and the field-by-field v1.0 comparison run everywhere and remain load-bearing.


## 2026-08-09 — Round-1 official-source reconnaissance sweep (no candidate enrolled)

First sweep under the v1.1 cadence, run **after** the cadence commit `153c6239` was pushed. Official investor-relations and issuer-filed SEC sources only. **No attention, market, options, outcome or strategy data was inspected**, and no aggregator, broker calendar, analyst estimate or search snippet was used as evidence.

**Result: zero enrollable candidates.** All 24 locked-universe tickers were swept exactly once. No ticker produced an explicitly dated **upcoming** regular earnings event from a permitted official source, so **no canonical screening row and no registry row were written**, and the human-review queue holds no enrollable candidate.

Two apparent hits were checked and rejected on inspection rather than accepted: GPN's page carried a dated earnings line under **"Past Events"** and states verbatim *"There are no upcoming events scheduled at this time"*; TTWO's and INTC's dated lines are likewise past events. A past date is never promoted into an upcoming candidate. Four issuers (GPN, INTC, NCLH, STZ) state on their own pages that no upcoming events are scheduled — issuer evidence of absence, recorded as such and distinguished from a retrieval gap.

**Retrieval honesty.** 10 IR pages returned HTTP 200 but render their event lists client-side, so the served HTML carried no dated event; that is a limitation of this retrieval method, **not** issuer evidence of absence, and it is labelled that way. A second pass recovered the pages whose first-pass URL 404'd by following the **issuer's own** navigation links from its root domain — a 404 on a URL I constructed is evidence my URL was wrong, not that the issuer publishes nothing. Sources that could not be read (ABBV, DELL, LDOS, TSLA, UAL) are recorded as access failures; **no third-party source was substituted**.

**DELL was neither duplicated nor altered.** It is identified as the existing pre-protocol enrolled event (`EVT-DELL-FY27Q2-ERN` / `-REG-001`), not a newly discovered candidate. Its official source timed out on both attempts, so the date/time recheck could not be performed. The registration was **not** altered, amended or re-verified, and no contradiction was observed because no source was readable. The access limitation is recorded and DELL stays on the weekly cadence for amendment detection only.

**No canonical rows, deliberately.** The screening-log schema requires a `fiscal_period` label and keys duplicates on ticker+fiscal_period. No official source supplied one for any pending candidate, so a canonical row could only be written by inventing a label. The protocol forbids that and forbids weakening a schema to fit an observation, so every item stays in the sweep manifest instead.

Evidence: `Live Signal Engine/Cohort_Screening_Round1/` — `SWEEP_MANIFEST_ROUND1.json` (all 24, once each), `HUMAN_REVIEW_REQUIRED_ROUND1.json`, the two raw retrieval passes, the SEC ticker→CIK map, and the three retrieval scripts. Validated by `test_market_response_cohort_sweep_round1.py` (**58 assertions**): exactly the locked 24 with no duplicates, every evidence URL an issuer or SEC host, no third-party citation, no prohibited research field, no automated finding represented as human-verified, DELL not registered twice, no anchor or lead count computed outside the production planner and XNYS calendar, and no GST/panel/options/market-response module imported by any sweep script.


## 2026-08-09 — Cohort protocol v1.1: the screening cadence, fixed before the first sweep

Additive protocol version. **The only methodological addition is the screening cadence.** v1.0 is preserved **byte-for-byte** and is never rewritten; v1.1 supersedes it **prospectively only**, and nothing decided under v1.0 is re-decided.

**Why.** v1.0 said pending candidates are "re-screened on a fixed cadence" and then never defined it. That is a real gap, not a wording nit: an undefined cadence is an opening for discretion, and a sweep run whenever it feels useful is a sweep whose *timing* can be shaped by what one expects to find. Defining it after the first sweep would be defining it with knowledge of what the sweep returned — so it is fixed here, and this commit is pushed **before the first candidate investor-relations page is inspected**.

**The cadence.** Initial sweep immediately after this commit is pushed, over the full locked 24-ticker universe. Recurring sweep **every Monday at 09:00 America/Chicago**. If a scheduled sweep cannot run because of a documented technical failure it runs on the **next available calendar day**, with the delay and its cause recorded — never silently skipped, never back-dated.

**Who stays on it.** Every pending candidate until it is enrolled or receives a terminal disposition; every already-enrolled event until its pre-event anchor begins, **solely** to detect official date/time amendments — a recheck may never revisit enrollment itself. Re-screening uses exactly the v1.0 permitted inputs and blinding prohibitions; being a re-screen relaxes neither. **No unscheduled re-screen** may be triggered by attention, price, volatility, news, options, earnings results or perceived interestingness. **Reaching 60 events does not stop enrollment.** Changing the cadence requires a new dated version written before the sweep it would affect.

**Unchanged:** locked universe, collection window, target, five-session lead rule, INC-1…INC-10, permitted source types, every disposition code and class, prohibited exclusion reasons, amendment rules, blinding prohibitions, v0.2 tier relationship, analysis separation and display gate. Exactly one disposition text changed — `PENDING_OFFICIAL_DATE_UNAVAILABLE` now points at the defined cadence instead of a dangling reference; what it *means* is unchanged.

Deliverables: `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1_DRAFT.md`, its canonical `..._v1.1.json` (generated from the v1.0 JSON so every carried-forward rule is provably identical), and `test_market_response_cohort_protocol_v1_1.py` (**68 assertions**, including a byte-for-byte check that both v1.0 files are unchanged and a diff proving exactly one disposition text moved).


## 2026-08-09 — Canonical absolute-response persistence

Implementation of an **existing specification**, not a new formula or analytical decision. SPEC v0.1 has always required an `abs_*` counterpart for each signed response interval — "`abs()` of the corresponding signed return, stored alongside it (never replacing it)" — and the merged HYP-01 lock named `abs_overnight_gap` as its primary outcome while recording, truthfully, that no capture path emitted it. This closes exactly that gap.

**Six mappings, now emitted.** D1: `abs_overnight_gap`, `abs_open_to_30m`, `abs_thirty_min_to_close`, `abs_open_to_close`. D3: `abs_close_T1_to_close_T2`, `abs_close_T1_to_close_T3`. Derived by `pipeline.capture_d1()` / `capture_d3()` through the new `response_magnitude.apply_absolute_fields()`, which applies the existing `derivations.abs_or_none()` — the single definition of `abs()` in the package. No signed-return formula is recomputed anywhere.

**Stored alongside, never replacing.** Signed values remain present and unchanged. A signed `0.0` yields `0.0`; a missing signed value yields `None`, never zero; an absent signed key produces no `abs_*` key at all. No imputation, winsorization, clipping, rounding or outlier removal.

**Not a new lifecycle requirement.** `D1_REQUIRED_FIELDS` and `D3_REQUIRED_FIELDS` are unchanged — the absolute fields are canonical derived **outputs**. A record is neither made complete nor made incomplete by their presence, and the gates see exactly the fields they always did. Lifecycle transitions, completeness thresholds, the strict v0.2 core gate, option dispositions, cohort rules, HYP-01's sample size and model, and HYP-02/HYP-03 are all untouched.

**Callers do not choose these values.** The pipeline derives them. A caller-supplied `abs_*` value is accepted only when it exactly equals the canonical value; any disagreement — including a `None` against a real value, or a non-numeric — raises the dedicated `AbsoluteFieldConflictError` **before the first event-log or marker byte**, not even `D1_PENDING`. Verified by asserting the log is byte-identical after the refusal.

**Where they land.** The durable D1/D3 state record, plus a `response_magnitude` block in the immutable `D1_CAPTURE` and `FINAL_COMPLETION` stage markers and in the legacy `{event_id}_COMPLETION_MARKER.json`. Marker values are read back from the stored record rather than recomputed, so a marker attests to what was actually written, and marker tie-out now covers the block so recovery detects drift in it.

**No backfill.** Records written before this commit carry no `abs_*` fields and were not rewritten. They remain transparently ineligible for analyses requiring them — the honest state, not a defect. A marker built over such a record yields an empty `response_magnitude` block rather than a block of nulls.

**HYP-01 lock — implementation status only.** `abs_overnight_gap` moves from `SPECIFIED_NOT_YET_EMITTED` to `IMPLEMENTED_AND_EMITTED` and is no longer blocking for freeze; the emitting path and its sinks are named. The **analytical definition did not change**: same predictor (`gst_zscore`, continuous, unthresholded), same outcome, same model, α = 0.05 two-sided, ticker-clustered with finite-sample correction, same ordering, n = 60, still no results and no frozen event IDs. The lock's test now verifies the emitted claim by driving the real production path instead of asserting it.

**Tests.** New `test_market_response_absolute_persistence.py` (**93 assertions**) covers all six mappings; positive, negative, zero and `None` behaviour; signed values unchanged; absolutes never negative; D1_COMPLETE and COMPLETE persistence; marker equality; conflicting-caller refusal with zero writes; agreeing-caller no-op; missing values keeping existing PARTIAL behaviour; no zero-fill; the required-field tuples unchanged; and historical records neither rewritten nor backfilled. The HYP-01 lock suite grows to **145**. No analysis runner was added and no model, coefficient, p-value, interval, descriptive result or plot was computed.


## 2026-08-09 — HYP-01 primary analysis lock v1.0 (draft)

Preregistration and tests only. **No model was implemented and none was run**; no historical or prospective outcome was analysed, no candidate was screened, no observation was collected. `EVT-DELL-FY27Q2-ERN` remains `REGISTERED` and its registry blob is untouched.

**Locked.** Question: does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response? Predictor **`gst_zscore`** — continuous, unthresholded, measured at the pre-event anchor, no data-driven cutoff, no winsorization, no outcome-informed transformation; Wikipedia is explicitly **not** co-primary and cannot change the confirmatory conclusion. Primary outcome **`abs_overnight_gap`**. Primary model **`abs_overnight_gap ~ gst_zscore`**, OLS, two-sided `β_gst = 0`, `α = 0.05`, ticker-clustered covariance with finite-sample correction, reporting coefficient, 95% CI, p-value, eligible-event count and unique-ticker count. Exactly one right-hand-side term; no covariate may be selected on observed data. The software, package, version and cluster-covariance option string are recorded as `TO_BE_FROZEN_AT_EVENT_60` — deliberately unset, so the freeze step must capture them rather than let the environment drift.

**Sample.** Enrolled under the cohort protocol · eligible for `core_attention_vs_equity_response` · strict v0.2 core passed · D1 passed · `gst_zscore` non-null with successful GST provenance · `abs_overnight_gap` non-null with valid provenance · release session `BMO` or `AMC` · among the first 60 by mechanically derived response-session date (`compute_expected_next_full_trading_session_xnys`), tie-broken by `event_id`. Both sort keys are fixed before any event exists and read no observed value, so the membership of the first 60 cannot be steered by results. **`INTRADAY` releases stay enrolled in the cohort** and are ineligible for this analysis only — the overnight window would straddle rather than follow an intraday release. That is a measurement incompatibility fixed in advance, not a post-hoc exclusion.

**A gap stated plainly.** `abs_overnight_gap` is an authoritative SPEC v0.1 field ("`abs()` of the corresponding signed return, stored alongside it") and its formula is fixed, but **the capture path does not yet emit it** — `D1_REQUIRED_FIELDS` holds only the four signed intervals and no module writes an `abs_*` key. The lock names the specified field rather than inventing one or substituting another return, and records the persistence gap as **blocking for freeze**: event 60 cannot be frozen until the field is actually persisted. Building it is a separate task, not done here. The same "specified, not yet emitted" caveat is recorded for `abs_open_to_30m`, `abs_open_to_close` and the sector-relative fields.

**Secondary only.** The adjusted sensitivity model (`+ realized_volatility + release_session_BMO + sector fixed effects`) cannot overturn or rescue the primary; `panel_implied_volatility` may not be used as an implied-move benchmark or substitute. Wikipedia, `abs_open_to_30m`, `abs_open_to_close`, `full_session_range`, sector-relative variants and a rank-based GST sensitivity are registered as secondary/exploratory with no independent confirmatory claim.

**Discipline.** No imputation, zero-fill, winsorization or outlier deletion; no removal on direction, magnitude, surprise, news, options availability or apparent outlier status; provider and schema failures stay documented missing observations; a failing event stays in the enrollment audit; one event counts once; DELL gets no exemption. Before 60 eligible events only the **count and status** may be shown — no estimate, direction, plot, interim p-value or informal description. At event 60: freeze the 60 IDs, freeze the code and environment, verify all gates, then run the model **once**. Later events form a separately labelled extension cohort. No optional stopping, no repeated testing, no model change after the freeze.

HYP-02 and HYP-03 keep their thresholds, statuses, missing-measurement classifications and unresolved choices. The cohort protocol and every v0.2 gate and interval formula are unchanged. Deliverables: `GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md`, its canonical `..._v1.0.json`, `GST_HYP01_ELIGIBILITY_AND_FREEZE_RULES_v1.0.md`, and `test_market_response_hyp01_analysis_lock.py` (**143 assertions**, including verification that the "not yet emitted" claims are true of the tree).


## 2026-08-09 — Prospective hypothesis registry and numeric result-display gates v1.0 (draft)

Registry definition only, written after the cohort rules merged and **before any candidate screening or prospective observation**. No result, direction, effect estimate, plot, p-value or confidence interval exists for any hypothesis. `EVT-DELL-FY27Q2-ERN` remains `REGISTERED` and its registry blob is untouched.

**Eligibility classes are not hypotheses.** `completeness.HYPOTHESIS_CLASSES` state which evidence modules an event carries; they are not named research questions. The registry defines named hypotheses separately and maps each onto the class and measurements it requires. Satisfying a class never licenses a result.

**Three hypotheses registered.** **HYP-01** (pre-earnings attention and market repricing, n ≥ 60, sole primary confirmatory) is `ACTIVE_COLLECTING`: every required field is an existing v0.2 pre-event field or existing D1/D3 interval field, and each has a production capture path. No new return formula is introduced. **HYP-02** (cross-source attention divergence and earnings surprise, n ≥ 60, secondary) and **HYP-03** (post-earnings attention decay and continued repricing, n ≥ 40, exploratory) are `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`, determined mechanically and verified against the tree: `eps_surprise_pct`/`revenue_surprise_pct` exist only as Event Dossier Layer A schema columns, no production code writes them and no production join maps a market-response `event_id` to a dossier surprise value; and no post-event attention capture stage or decay/half-life measurement exists anywhere. `gst_slope_v0_1` is a pre-event trailing slope and is deliberately **not** repurposed. Neither missing measurement is built here, and missing implementation never counts as eligibility.

**Options.** No options hypothesis is registered; `options_implied_move` and `joint_attention_plus_options` remain valid data classes with display status `DENY_NO_REGISTERED_HYPOTHESIS`. Options unavailability never blocks HYP-01/02/03 enrollment when an event's own core fields are valid.

**Counting and governance.** Ten counting rules: one event counts once, no duplicate ticker-quarter double-count, all gates must pass, missing stays missing (no zero-fill or imputation), no removal for null or unfavourable results, ticker-repeat events flagged for clustered analysis and never called independent companies, threshold freezes the event-ID set **and** the analysis commit before results, no optional stopping, later events form an extension cohort, and DELL gets no exemption. Two-sided inference, α = 0.05, effect sizes with 95% CIs, ticker-cluster-aware inference required, no promotion to confirmatory on observed results, no model change after freeze. **Ten analysis decisions are marked `PENDING_SEPARATE_ANALYSIS_LOCK`** rather than guessed — including HYP-01's exposure definition and primary outcome field. **60/60/40 are governance eligibility floors, not power calculations**; no power calculation was performed and none may use observed project results.

**Deliverables.** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md`, its canonical `..._v1.0.json` (generated from production constants so it cannot drift), `GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` (all three gates CLOSED; fail-closed default table; freeze procedure), `GST_PROSPECTIVE_HYPOTHESIS_FIELD_CROSSWALK_v1.0.md` (implemented vs dossier-only vs not-implemented, class vs hypothesis, and every unresolved decision), and `test_market_response_hypothesis_registry.py` (**132 assertions**). The separate `gst-attention-radar` DEMO fixture happens to carry the same 60/60/40 `minimum_observations`; that is recorded as a coincidence, the fixture is explicitly not the source of authority, and it was not edited.


## 2026-08-08 — Prospective multi-event cohort protocol v1.0 (draft)

Protocol definition only. **No candidate investor-relations calendar was inspected, no panel was run, no provider was contacted, and no DELL observation was made.** The rules are published *before* we learn which events qualify — rules written after seeing the candidates are not rules, they are choices. `EVT-DELL-FY27Q2-ERN` remains `REGISTERED` and its registry blob is untouched.

**What it fixes.** Which earnings events enter the GST Market Attention Observatory: the production locked 24-ticker universe (read from `constants.LOCKED_24_TICKER_UNIVERSE`, never retyped), a collection window of 2026-09-01 … 2027-05-31 applied to the **mechanically derived pre-event anchor**, a floor of at least 60 independently registered events, and a minimum registration lead of 5 XNYS trading sessions. Ten inclusion rules, twelve dispositions covering every pending / excluded / amended / compromised outcome, an explicit permitted/prohibited enrollment-input split, and an explicit list of reasons an event may **never** be excluded — low or high attention, missing options data, an unfavourable or null market response, post-registration source failure, or an expectation about how interesting the result will be.

**What it does not do.** It defines no interval formula, threshold, quote-age or skew limit, completeness tier or gate: those live in the v0.2 SPEC, the v0.2 field dictionary and `gst_market_response.completeness`, referenced and unchanged. It reimplements no session arithmetic — anchors come from `operations_plan.build_operations_plan` and sessions from the production XNYS calendar. It is observational measurement infrastructure and **does not test, optimise, select for, or claim a profitable trading strategy**; future strategy research is a named out-of-scope stage.

**Display gate fails closed.** The existing governance rule (`GST_Phase2_InformationArrivalPanel_SPEC_DRAFT.md` §3) requires a pre-set minimum sample size per hypothesis, in its own dated pre-registration. No numeric threshold is currently registered for the market-response families, and this protocol deliberately does **not** invent one — setting that number inside the document that also defines the cohort is exactly the coupling the governance rule exists to prevent. Until a family has a registered threshold, the gate denies display for it; absence of a number is never read as absence of a gate.

**Deliverables.** `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md`, its canonical `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json` (generated from production constants so it cannot drift), `GST_PROSPECTIVE_COHORT_SCREENING_LOG_SCHEMA_v1.0.md` (schema only — zero rows, and no column in which an attention, price, options or outcome value could be recorded), and `test_market_response_cohort_protocol.py` (**128 assertions**). The tests prove the JSON and Markdown agree, the universe equals production element-for-element, the window/lead/target are fixed, enrollment never depends on outcome-bearing data, options unavailability never excludes a core-eligible event, duplicate ticker-quarter enrollment is barred, amendments are append-only, every v0.2 threshold and interval list is unchanged, no trading-strategy claim is introduced (checked structurally, since the document's own non-goals name those terms), no network or provider access is possible during validation, and the DELL registry is byte-identical.


## 2026-08-08 — test: make the provider import blocker Python 3.14 compatible

Test infrastructure only. No production module, schema, gate, workflow, registry row, methodology document or historical artifact changed. `EVT-DELL-FY27Q2-ERN` remains `REGISTERED`; no panel was run, no provider contacted, no DELL data inspected.

**The blocker was a silent no-op.** `test_25_no_network_and_no_provider` installed a meta-path finder exposing only the legacy `find_module` hook. That hook was deprecated in 3.4 and **removed in 3.12**, so the modern import system never consulted it: under this project's Python, `requests`, `yfinance` and `pytrends` all imported straight through the "blocker". The surrounding `LEAKED == []` assertion still held honestly — the orchestrator genuinely imports no provider — so the test never went red while its blocker proved nothing.

Replaced with a standards-compliant `find_spec` finder. It records every blocked attempt and raises a distinctive `ProviderImportBlocked(ImportError)` carrying a unique token, so a pass can no longer be produced by the package merely being **absent** from the environment: a plain `ModuleNotFoundError` is now an explicit failure. The test attempts all three imports outright and asserts the blocker observed each, that each failed with the distinctive error, and that none entered `sys.modules`. The socket blocker is preserved and now positively verified inside the child, the v0.2 orchestrator, CLI and fingerprint must import **and run** under both blockers, and `sys.meta_path`, all four socket patches and `sys.modules` are restored in a `finally` block whose success is itself asserted. Three AST assertions pin the implementation: `find_spec` is defined, `find_module` is not, and the distinctive error subclasses `ImportError` — structural rather than substring, because the surrounding comments name `find_module` in order to say it must not be used. Nothing was weakened, skipped, xfailed or version-gated; the file parses against the 3.12 grammar used by CI and the blocker API is 3.4+.

**Historical provenance, recorded for the record — no code or artifact changed.** The preserved `GST_Phase2_DailyPanel_TestRun_2026-07-30_run3` panel reports `all_six_fields_clean_count = 20` while all 24 rows carry six populated research fields. That is **not** a stale flag. The producing commit is `46aec15` (it introduced the CSV, the marker and `phase2_run3.log`; the marker's `generated_at_utc` is 26 minutes before that commit), and at `46aec15` the flag was defined as `all(six fields non-None) and days_to_earnings is not None` — a seven-condition test. `phase2_run3.log` states it verbatim: `Clean (all 6 fields + earnings): 20  Incomplete: 4`. The four rows had a successful earnings lookup that honestly found no upcoming earnings date. Commit `50c4916` (2026-08-01, "align completion gate with six-field contract") corrected the definition to the six locked research fields only, moved fail-closed earnings handling into `is_run_complete()` via `earnings_status == "ok"`, and applied the same six-field expression to the second-pass recomputation. Current `main` therefore cannot produce six populated fields with a stale false flag, and the v0.2 strict-core gate is right to accept those rows: they are six-field complete. Classification: **HISTORICAL_ALREADY_FIXED**.


## 2026-08-08 — second corrective audit of the v0.2 contract (PR #6)

A second audit of the v0.2 implementation found seven further defects, each of which could have destroyed or falsified evidence. **`EVT-DELL-FY27Q2-ERN` remains `REGISTERED`**; no pre-event snapshot, market-response observation, dossier, Layer B record, event log or stage marker exists; no provider was contacted; no DELL data was inspected; the registry row is untouched; the v0.1 documents remain byte-for-byte.

**The write-once primitive was not actually atomic.** `atomic_write_json_no_overwrite()` was `path.exists()` → `atomic_write_json()` → `os.replace()`. `os.replace()` replaces unconditionally, so any artifact created between the check and the replace was silently destroyed — precisely the evidence loss the immutable-marker rule exists to prevent, and no reordering of check-then-replace fixes it. The create itself must be exclusive: the payload is written and fsynced to a temp file, then `os.link()` creates the final directory entry (it raises `FileExistsError` rather than replacing), the directory is fsynced, and the temp file is removed on every path including failures. Filesystems without hard links fall back to `O_CREAT|O_EXCL`. A race-injection test creates the competing artifact *during the temp-file fsync* — inside the old window — and proves its bytes survive byte-for-byte.

**A dangling `PRE_EVENT_PENDING` was a permanent dead end.** `REGISTERED → PRE_EVENT_PENDING → crash` left the event stuck forever: every rerun refused because a pre-event state existed, and the pending record may never be deleted. Nothing had actually been captured. Resuming is only safe if the rerun is provably capturing the same thing, so `PRE_EVENT_PENDING` now persists a canonical capture fingerprint — event id, ticker, anchor, both panel hashes, commit SHA, methodology version, canonicalised option-disposition digest, plus a self-digest over exactly those fields. A rerun revalidates every input from scratch and resumes **only** on an exact match, appending the outcome state with no second pending record. Mismatch, a missing or non-recomputing fingerprint, or more than one pending record all fail closed. The pending record is never deleted or rewritten, and resume never skips the strict core gate.

**Implied volatility and realized volatility were backed by the wrong leg.** The Phase 2 panel emits five independent per-leg statuses; the strict gate consulted `price_history_status` for IV, realized volatility, `previous_close` and `volume` alike. The option-chain leg fails for entirely different reasons than the price-history leg, so a failed `iv_status` or `realized_vol_status` passed the six-field gate whenever price history happened to be OK — treating unavailable data as present. Each field is now backed by the leg that produced it (`iv_status`, `realized_vol_status`); only `previous_close` and `volume` legitimately share the price leg. Normalised **and** raw statuses for both legs are persisted as provenance, unknown statuses fail closed, and the synthetic panel fixture now carries all five columns, matching the real panel header.

**`PARTIAL` was not stage-specific.** `PARTIAL` is reachable from the pre-event, D1 and D3 stages and carries the failing stage's fields, but selectors searched backwards for "`PRE_EVENT_CAPTURED` or `PARTIAL` with fields". A later D1 failure therefore won and replaced a perfectly good pre-event capture's eligibility — the completion marker reported it as a legacy record with no eligibility at all — and a `pre_event` gate check graded D1 interval fields. Every v0.2 `PARTIAL` now carries `failure_stage`; the stage's own success state always wins, and only a `PARTIAL` belonging to that stage may substitute. Legacy records derive their stage mechanically from the preceding pending state rather than defaulting, and an unrecognised value resolves to no stage at all. `_pre_event_record()`, `check_required_gate()`, the completion-marker lookup and the stage-marker state requirement are all corrected.

**The option artifact was unbound between validation and execution.** Only the panel files were re-verified, so a caller could validate `UNAVAILABLE_NO_VERIFIED_SOURCE` and then execute with a different disposition, a different reason, or a dict claiming a verified OPRA benchmark — and the event record would carry `VALID_VERIFIED` with `option_benchmark_eligible: true`, approved by nothing. The complete artifact is now canonicalised and hashed at validation; execution re-derives the digest and requires exact equality, failing with zero writes. Canonicalisation is order-independent, so key ordering alone never causes a false mismatch.

**Blank dates were discarded before validation.** The date resolver built a set of the rows' values and then called `.discard("")`, so a blank `price_asof_date` among otherwise agreeing rows vanished and the panel resolved to a single session. `run_date` was weaker still: ambiguity silently produced `None`, which skipped the `run_date >= price_asof_date` check entirely. Blank is not absent — a row with a blank session is one the panel did not record a session for, and it cannot be certified as belonging to the anchor. Nothing is discarded now: every row must carry a nonblank value in both columns, both must resolve to exactly one value, the ordering rule is asserted rather than skipped, and the anchor must equal `price_asof_date`. Each rule is its own named check, and the full per-row audit is persisted on the report.

**The v0.2 path still reached the v0.1 core gate.** `capture_pre_event_and_option_benchmark()` — the function the v0.2 orchestrator called — judged the core with `is_valid_pre_event_observation()`: `previous_close` plus a timestamp, with `gst_zscore` satisfiable by an honest missing status. An observation with no wiki z-score, IV, realized volatility or volume could be recorded as `PRE_EVENT_CAPTURED` with `core_pre_event_eligible: true`. The orchestrator ran the strict gate as a separate report check, but the eligibility persisted on the record came from the weaker one, and any direct caller bypassed the strict gate entirely. The entry point is now split into `capture_pre_event_and_option_benchmark_v0_1()` (legacy contract only) and `capture_pre_event_and_option_benchmark_v0_2()` (strict six-field, via the new `evaluate_pre_event_modules_v0_2()`); **no unversioned public capture function exists**, and the old name raises with explicit version guidance.

**Tests.** `test_market_response_pre_event_capture.py` grows to 206 assertions, including the thirteen required regressions: the atomic race, exact-fingerprint resume, changed-input refusal, no duplicate pending or captured state, independent IV and realized-vol status enforcement, D1 and D3 `PARTIAL` not replacing pre-event eligibility, option-disposition mutation, blank `price_asof_date` and blank `run_date`, the strict-gate bypass, and a full chronology that completes without unlinking or overwriting anything — plus crash injection after `REGISTERED`, after `PRE_EVENT_PENDING`, after `PRE_EVENT_CAPTURED` and before marker creation. A new `test_market_response_second_pass_differential.py` (26 assertions) restores each `ed4df74` defect in isolation and proves the corresponding regression depends on the fix rather than passing vacuously.


## 2026-08-08 — v0.2 contract formalised and hardened (corrective pass on PR #6)

The v0.2 amendment landed as code before it existed as a document. This pass writes the formal contract and closes seven defects found by auditing it. **`EVT-DELL-FY27Q2-ERN` remains `REGISTERED`**; no pre-event snapshot, market-response observation, dossier, Layer B record, event log or stage marker exists; no provider was contacted and no DELL market/attention/options/earnings data was inspected. The registry row is untouched.

**Formal contract.** New `GST_Earnings_Market_Response_Decomposition_SPEC_v0.2_DRAFT.md` and `GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.2.md`; the v0.1 documents are preserved **byte-for-byte**. The methodology identifier `market_response_v0.2` is now enforced — blank, arbitrary, stale and v0.1 values are rejected by both the CLI and the orchestrator, and the accepted value is persisted into the event record and every stage marker.

**The core is now actually six-field.** v0.2 adds `evaluate_strict_core_v0_2()` (the v0.1 gate is untouched and still serves the legacy path). It requires all six panel fields — `gst_zscore`, `wiki_zscore`, `panel_implied_volatility`, `realized_volatility`, `previous_close`, `volume` — each backed by a successful source status (`ok` or `ok_recent_cache_fallback`), plus `pre_event_snapshot_asof_utc`. A null fails; a non-success status fails; **a legitimate `0.0` with a successful status passes**, so missingness is never inferred from a zero.

*On `panel_implied_volatility`:* SPEC v0.1 §5 forbids using the panel's generic IV as an earnings-implied-move baseline, and **that prohibition is unchanged**. The value is persisted under a deliberately namespaced key purely as six-field completeness provenance — never exposed as `implied_volatility`, never fed to the option benchmark, never usable as an implied-move value. Persisting a field as evidence and using it as a benchmark are different acts; only the second was ever prohibited.

**Full provenance, with marker tie-out.** Fifteen fields are persisted on the pre-event record and echoed field-for-field in every stage marker: panel CSV/marker paths and SHA-256s, panel status, row / unique-ticker / all-six-clean counts, ticker, `run_date`, `price_asof_date`, `pre_event_snapshot_asof_utc`, research commit SHA, methodology version, adapter schema version.

**TOCTOU closed.** Validation approved files that stayed mutable on disk, and execution re-read them without proving they were unchanged. Execution now re-hashes both panel files, requires exact equality with the approved report, and re-runs the anchor, panel-status, marker/CSV and strict-core checks before the first byte. Any drift in either file, the methodology, the commit SHA or the ticker fails with zero writes.

**Immutable stage markers.** v0.1 had a single completion marker that had to be *replaced* to progress — the chronology test literally unlinked it. v0.2 writes one write-once marker per durable stage (`PRE_EVENT_CAPTURE`, `D1_CAPTURE`, `FINAL_COMPLETION`, the last only at a terminal state) via a new `atomic_write_json_no_overwrite()` that raises rather than replacing. Crash recovery is deterministic: a *missing* marker is regenerated from the event record without appending any state, a *tying-out* marker is returned untouched, and a *mismatched* marker fails closed and is never overwritten.

**`check_required_gate()` corrected.** It evaluated `state_records[-1]`, so once D1/D3 were captured a `pre_event` or `option_benchmark` check silently graded D1/D3 fields. It now selects the record belonging to the tier being checked.

**The unsafe options route is closed.** The CLI accepted a hand-written JSON that merely asserted `option_feed="opra"`. Nothing in this tool can authenticate provider identity, endpoint, response hash, contracts, strike, expiration, per-leg quote timestamps, quote age, skew, or a recomputed benchmark, so that route let an operator manufacture a "verified" benchmark by typing a file. `VALID_VERIFIED` is now **refused outright** through the CLI; explicit unavailable dispositions are unaffected, so core-only capture still works. The runbook no longer instructs anyone to produce such a file.

**Authoritative session date — a real correctness bug.** The orchestrator derived the panel's session from `retrieval_timestamp_utc[:10]`. The panel writes two authoritative columns and they genuinely differ: a real run has `run_date=2026-07-30` with `price_asof_date=2026-07-29`, because the panel executes in the small hours UTC (04:40Z = 00:40 ET) **after** the session it summarises. Truncating the UTC timestamp yields `run_date`, so the anchor was being bound to the wrong day. The anchor now binds to **`price_asof_date`**; `run_date >= price_asof_date` is asserted; and a missing column, blank value, or disagreement across rows fails closed rather than being guessed.

**Stage vocabulary corrected.** The market-response state machine implements **D1 and D3**, not D2: `MAINLINE_ORDER` has no D2 state, and the D3 tier's own fields (`close_T1_to_close_T2`, `close_T1_to_close_T3`) already carry the D2 close-to-close measurement. The D2 *session* is owned by `operations_plan.py`, which schedules it as a calendar session. Prose claiming the state machine captures "D1/D2/D3" is corrected. **No D2 state was invented to match prose.**

**Tests.** `test_market_response_pre_event_capture.py` grows to **122 assertions**, including regressions that cannot pass against `9b006a4`: the strict six-field gate and each individual missing field, legitimate-zero vs zero-with-bad-status, provenance persistence and marker tie-out, panel and marker mutation between validation and execution, methodology enforcement, marker immutability, crash recovery including the mismatched-marker refusal, the OPRA-claiming JSON rejection, the corrected gate record selection, and the session-ambiguity cases (including the run-date-after-session case that must *pass*).



## 2026-08-08 — PROTOCOL AMENDMENT v0.2: separate collection lifecycle from analytical eligibility

**Authorized methodology amendment**, made **before** any prospective DELL research observation, pre-event snapshot, market-response observation, dossier, or Layer B record exists. It was prompted by deterministic contract tracing, not by looking at data: no DELL attention, price, volume, volatility, options, earnings outcome, consensus, or analyst figure was inspected at any point. `EVT-DELL-FY27Q2-ERN` remains **`REGISTERED`**. The human-verified timing registry is **not** amended — no timing fact changed. Nothing is backdated; the prior v0.1 behaviour and its rationale are preserved in this trail rather than rewritten.

**The defect (v0.1).** One state variable carried two different concepts: *which scheduled stages were captured* and *which evidence modules are analytically valid*. `PRE_EVENT_CAPTURED` required **both** the pre-event core gate **and** the option-benchmark gate. An unavailable **optional** option benchmark therefore drove the event to `PARTIAL` — a **terminal** state — after which `capture_d1()` raised `InvalidStateTransitionError`. A valid six-field attention/market core was destroyed by the absence of an optional module, and D1/D2/D3 became uncollectable. That is avoidable event attrition, and with the Alpaca options entitlement INCONCLUSIVE it would have hit the very first prospective event.

**The correction.** Lifecycle state records collection; analytical eligibility is carried alongside it, per module. This does **not** declare options unnecessary and never treats an absent benchmark as present:

| Case | Lifecycle | core | option | joint | tier |
|---|---|---|---|---|---|
| core fails | `PARTIAL` (terminal, unchanged) | false | false | false | `core_invalid` |
| core + valid OPRA benchmark | `PRE_EVENT_CAPTURED` | true | true | true | `core_and_option_benchmark` |
| core + explicitly unavailable | `PRE_EVENT_CAPTURED` | true | **false** | **false** | `core_only_no_option_benchmark` |

A core-only event may reach lifecycle `COMPLETE` and **is still not full-data complete**: `is_full_data_complete()` requires both lifecycle completion *and* the core+option tier, and the completion marker surfaces the tier plus `is_full_data_complete: false`. Hypothesis families are gated mechanically — core-attention needs `core_pre_event_eligible`, options-implied-move needs `option_benchmark_eligible`, joint needs `joint_full_eligible`. Lifecycle state is deliberately not an argument to that function, so `COMPLETE` can never by itself authorize an options-linked claim.

**Missingness is explicit, never inferred.** An empty dict or null fields no longer imply "unavailable". The caller must declare `option_benchmark_status` ∈ `VALID_VERIFIED` / `UNAVAILABLE_NO_VERIFIED_SOURCE` / `LOOKUP_FAILED` / `NOT_ATTEMPTED`. `VALID_VERIFIED` requires provider identity (`option_feed`, OPRA only) and must pass the **existing** option gate; the other three require **null** benchmark values and a nonblank reason. A supplied-but-invalid artifact — malformed, crossed, indicative, timestamp-less, or contradicting its own disposition — is rejected with zero writes rather than silently downgraded to ordinary unavailability. Indicative quotes cannot be relabelled as either unavailable or OPRA-valid. Unknown or blank dispositions fail closed. Legacy v0.1 records raise `LegacyRecordError` rather than being silently reinterpreted.

**No threshold was weakened.** `is_valid_pre_event_observation()` and `is_valid_option_benchmark()` are called unchanged. The locked universe, six-field contract, GST/Wikipedia methodology, z-score formulas, earnings rules, D1/D2/D3 interval formulas, retry logic, quote-age and skew limits, event timing, the DELL registry row, historical results, and dossier blinding rules are untouched.

**Changed prior expectation, explained rather than quietly updated.** `test_market_response_decomposition.py` FF-3b asserted that a rejected benchmark plus a valid core yields `PARTIAL`. That assertion encoded the defect. It is replaced by two: handing over the rejected benchmark dict as-is now fails closed (it still carries a populated `underlying_price` while declaring no usable benchmark, and states no disposition), and declaring the honest `LOOKUP_FAILED` with null values captures the core while marking the option module ineligible. Three other call sites kept their assertions and only gained the now-required explicit disposition.

**Pre-event capture orchestrator.** New `pre_event_capture.py` + `pre_event_capture_cli.py` connect existing components — `operations_plan` (registry + XNYS anchor), `phase2_adapter` (panel CSV/marker + hashes), `completeness` (per-module eligibility), `pipeline` (transitions), `completion_marker` (atomic marker). They implement no calendar arithmetic, panel parsing, gate logic, or state rules of their own, and **never contact a provider**. Default is read-only validation; writes require `--execute`. There is deliberately no `--force`, `--overwrite`, `--skip-validation`, `--allow-stale` or `--ignore`. Validation completes entirely before the first byte; collisions and repeated execution fail closed with zero additional bytes.

**Scope notes.** The options benchmark is **separate from the Phase 2 six-field contract**. An unavailable benchmark never becomes zero; it may lower the event's completeness tier; it does not authorize indicative substitution. The attention signal and the equity market-response decomposition remain collectible for a core-only event. No strategy, return forecast, or trading recommendation is produced.

**Tests.** New `test_market_response_pre_event_capture.py` — **84 assertions** covering all 28 required scenarios. `test_market_response_decomposition.py` is now 87 assertions.


## 2026-08-07 — DELL FY27 Q2: offline capture plan and operational schedule

**Status of the event.** `EVT-DELL-FY27Q2-ERN` is **registered and preregistered on `main`** (PR #4, merge `87f5d770`) and remains in state **`REGISTERED` only**. **No pre-event snapshot has been taken.** No market, attention, option, consensus, or earnings-result data was inspected in this pass, and none was inspected to select the event. **This pass does not test a strategy and produces no research result.**

**The operational calendar is mechanically derived, never hardcoded.** A new dependency-light planner (`gst_market_response/operations_plan.py`, plus the plan-only `operations_cli.py`) reads the verified registry row and derives every session from the merged XNYS calendar, reimplementing no trading-day arithmetic. For DELL it derives: pre-event anchor **2026-09-02**, release **2026-09-03T20:30:00Z (AMC)**, **D1 2026-09-04**, **D2 2026-09-08**, **D3 2026-09-09**. The D1→D2 gap is explained by the calendar itself — 2026-09-05/06 are the weekend and **2026-09-07 is Labor Day (XNYS closed)** — and all three are recorded in the plan as non-sessions. Each session carries UTC and exchange-local open/close plus the earliest instant Alpaca's 15-minute freshness gate would permit a retrieval (final expected bar start + 15 min). AMC/BMO claims are cross-checked against the session close/open and fail closed on disagreement.

**Structurally offline.** The planner imports no provider and constructs none; the CLI imports exactly one project module plus stdlib. Verified by AST and by subprocess isolation: with every provider and panel module import-blocked and `socket.connect` patched to raise, planning still succeeds and no network client or research-state-writing module reaches `sys.modules`. One transitive load is recorded rather than hidden — `gst_market_response.providers` arrives via `event_registry` for the `EventTimingProvider` interface; its module-scope imports are stdlib plus `.bars` and it imports yfinance lazily, so it carries no network client.

**Artifacts.** `Live Signal Engine/Event_Operations/EVT-DELL-FY27Q2-ERN/` holds the versioned machine-readable plan (with a deterministic `plan_content_sha256` over the canonicalised plan, excluding its own integrity block) and `DELL_FY27Q2_OPERATIONAL_RUNBOOK_v0.1.md`. The directory is separate from raw bars, registry rows, event records, and dossiers. The CLI refuses to overwrite an existing plan.

**Capture-gap audit — no end-to-end pre-event capture command exists.** Five blockers are carried inside the plan itself so it can never read as ready. Three are hard: **BLK-OPT-1**, no operationally verified option-quote source — Alpaca has zero option support, and `option_chain_adapter.py` has no provider-eligibility concept at all, so the option path has never had a clearance decision of its own (the yfinance *bars* ineligibility neither proves nor disproves it); **BLK-OPT-2**, `build_option_benchmark()` requires the caller to supply `quote_timestamp_utc`, which a yfinance chain does not provide, so quote provenance would be asserted rather than observed; **BLK-ORCH-1**, nothing wires panel → adapter → option → EventStore (`build_option_benchmark()` is referenced only by tests, and `cli.py` offers only a gate check plus marker write). Two are material: **BLK-STALE-1**, `import_pre_event_fields_for_ticker()` has no expected-session parameter and so cannot reject a wrong-date panel; **BLK-PANEL-1**, a COMPLETE Phase 2 panel for the anchor session is not guaranteed. No live capture runner was built, no schema was weakened, and no gate was relaxed.

**Tests.** New `test_market_response_operations_plan.py` — **89 assertions**: the exact DELL schedule, Labor Day closure, AMC/BMO/INTRADAY behaviour and their calendar cross-checks, weekend and holiday releases, early-close sessions, DST-safe UTC↔ET conversion in both September and January, freshness-gate derivation, and fail-closed refusal for absent, duplicated, unverified, amended-into-unusable, wrong-calendar, missing-timestamp, naive-timestamp, non-locked-universe and malformed-id events; plus determinism, integrity-digest tamper detection, output-path collision refusal, and proof of no registry mutation, no EventStore write, no provider construction, no credential use and no network call.


## 2026-08-06 — Isolate the option helpers from the legacy GST runtime dependencies

**Why.** The first GitHub Actions run that PR #3 ever produced (run `31126964980`, `event=push`, ubuntu-latest, Python 3.12.13) discovered all 15 `test_market_response*.py` files and then failed importing `test_market_response_decomposition.py`:

```
gst_market_response.option_chain_adapter
  -> GST_MultiTicker_Forward_Log        (line 46)
    -> pytrends.request
ModuleNotFoundError: No module named 'pytrends'
```

An import-time dependency leak, not a logic defect. `option_chain_adapter.py` needs exactly two helpers — `get_nearest_post_earnings_expiry` and `get_option_snapshot` — but imported them from `GST_MultiTicker_Forward_Log.py`, a *live execution entry point* that at module scope loads pytrends, the live GST signal engine, `requests` and `urllib3`, disables warnings and reconfigures `sys.stdout`. Merely importing the adapter therefore dragged in the whole legacy GST runtime. `requirements.txt` covers `gst_market_response/` only and deliberately excludes that stack, so **no `pytrends` dependency was added**: installing Google Trends into a module that never queries Google Trends would have hidden the leak rather than fixed it.

**What changed.** The two helpers were moved **verbatim** into a new dependency-light `GST_Option_Chain_Core.py`, which imports only `datetime`, `pandas` and `yfinance` (the last only for the `yf.Ticker` annotation) and performs no network call at import. `GST_MultiTicker_Forward_Log.py` now imports and re-exports them and defines no duplicate, so every existing `GST_MultiTicker_Forward_Log.get_nearest_post_earnings_expiry(...)` / `.get_option_snapshot(...)` call site keeps working unchanged; the forward logger was not otherwise refactored or executed. `gst_market_response/option_chain_adapter.py` now imports from the core directly.

**No option methodology changed.** The moved functions were verified textually identical to the originals before the originals were removed. Nearest expiry is still the earliest strictly after `earnings_date`; the ATM strike is still `min(abs(strike - spot))` via `idxmin()`; the same fail-quiet behaviour (a raising `.options` → `None`, a raising `.option_chain()` → `{"option_chain_error": ...}`); the same bid/ask/bid-size/ask-size/open-interest/volume/implied-volatility extraction with the same `pd.notna()` guards and casts. No new fallback, pricing rule, expiry rule or quote transformation. `MAX_COMPATIBLE_QUOTE_SKEW_SECONDS` and every `ContractSelectionStatus` value are unchanged.

**A second instance of the same leak, found in a clean environment.** Reproducing in a fresh virtualenv outside the repo with only `requirements.txt` installed exposed `test_market_response_layer_b_emission.py` failing 7 assertions: it runs the real Event Dossier validator, which fails closed when `jsonschema` is absent ("the 'jsonschema' package … is not installed — freeze-manifest structural validation cannot run"). `jsonschema` is already pinned in `Event_Dossier_Protocol/validator/requirements.txt`, so the workflow's install step now installs that file too, from where it is already declared — it was **not** duplicated into `requirements.txt`, and the validator's fail-closed gate was **not** weakened.

**New coverage.** `test_market_response_dependency_boundary.py` (42 assertions) proves, using subprocess isolation so the verdict cannot be contaminated by already-imported modules, that the adapter imports while `pytrends`, `GST_Live_Signal_Engine` and `GST_MultiTicker_Forward_Log` are all forbidden by a `sys.meta_path` blocker; that none of them lands in `sys.modules`; that expiry selection and ATM snapshot behave identically against synthetic ticker/chain doubles (including exact-tie strikes, missing fields staying `None` rather than `0`, empty legs, and the error dict); that the legacy logger re-exports rather than duplicates; that the core's imports are AST-verified dependency-light and network-free; and that `requirements.txt` stays sufficient and `pytrends`-free.

**Verification.** Clean venv, `requirements.txt` + the validator's pinned file, `pytrends` confirmed absent: the previously failing `test_market_response_decomposition.py` passes (83 assertions), the workflow's discovery loop runs 16/16 files (655 assertions), and the validator's exact CI command exits 0. With outbound sockets blocked (Yahoo, Google Trends and Alpaca all positively confirmed unreachable): Market Response 16/16 files / 655 assertions, Phase 2 12/12 files / 617 assertions, Event Dossier validator 27 end-to-end assertions + 21 unit tests. No panel run, no live provider call, no event registration, no dossier or Layer B output, no operational-cache or artifact write.


## 2026-08-06 — Market Response: cross-protocol integration hardening (PR #3)

**Why.** Merging main (which now carries the Event Dossier Protocol, PR #2) into `phase2-market-response` put all three modules in one tree for the first time and surfaced six integration defects. None of them required a methodology change; all were boundary problems. **No prospective event was selected or registered, no dossier was created, no panel was run, no live market-data request or broker order was made, and no trading strategy was tested or evaluated for profitability.**

**1. Explicit session-vocabulary translation.** Both modules have a `release_market_session` field with *different* value domains — Market Response uses `BMO`/`INTRADAY`/`AMC`, the protocol uses `before_open`/`during_session`/`after_close` — so a market-response identity written straight into the protocol's `events.csv` was rejected by the validator's enum gate. Neither enum was renamed or widened. A single pure translation layer now lives in `gst_market_response/protocol_boundary.py`: `BMO → before_open`, `INTRADAY → during_session`, `AMC → after_close`. It matches exactly and case-sensitively, and raises `SessionVocabularyError` on unknown, blank, whitespace-only, wrong-typed, wrong-cased, or protocol-side input. **It never infers a session from a timestamp** — deriving `after_close` from a 20:05 UTC release would manufacture a protocol field from a clock reading, which is precisely what the registry's human-verification requirement exists to prevent. A test proves the translated value is accepted by the shipped validator and that the untranslated `AMC` is rejected by it, so the translation is demonstrably load-bearing.

**2. Correct treatment of `complete_recent_cache_fallback`.** The Phase 2 adapter previously collapsed every status that was not literally `"ok"` to `"error"`, which mislabelled a Phase-2-*complete* observation as a failure. Phase 2 itself treats `complete_recent_cache_fallback` as COMPLETE (`validate_amzn_wiki_only.py` maps both it and `"ok"` to COMPLETE, and `test_phase2_wikipedia_recent_cache_fallback.py` proves the fallback-served z-score exactly equals the original successful response's). Normalisation is now an explicit allowlist: `ok → ok`; `complete_recent_cache_fallback → ok_recent_cache_fallback`; blank/None → `missing`; everything else non-blank — timeout, error, `incomplete_after_second_pass`, `incomplete_effective_watermark_unavailable`, `incomplete_watermark_unavailable`, or any status invented later — fails closed to `error`. The fallback keeps its **own** success category rather than being folded into `ok`, so it is never presented as ordinary fresh data, and the exact original Phase 2 string is preserved separately in new `source_status_*_raw` fields. Phase 2's own status values, completeness rules, source-selection logic, and panel output are untouched.

**3. Canonical drift guards.** `LOCKED_24_TICKER_UNIVERSE` and `EVENT_ID_RE` are duplicated in `gst_market_response/`. Both copies are currently identical to their canonical sources, but nothing detected divergence. `test_market_response_canonical_drift.py` now compares each against the **executable** canonical definition — `locked_universe_v0.1.json` for the universe, and the validator module itself (loaded and executed, not text-parsed) for the event-ID pattern and both session enums — and fails on any drift, including ordering. The 24 tickers and the event-ID syntax are unchanged. The stale comments in `identity.py` and `constants.py` claiming the protocol "is not reachable at runtime from here" / was "literally unreachable ... from a different git worktree" have been corrected: that stopped being true when PR #2 merged.

**4. Layer B emission boundary.** `B_Market_Response_Addendum/schemas/market_response_addendum.csv` had a schema but no producer. `gst_market_response/layer_b_addendum.py` now converts an eligible completed market-response record into a schema-exact addendum row. Column order is read from the protocol's own schema file, never hardcoded. Fail-closed rules: only a `COMPLETE` market-response state is eligible (PARTIAL, ABSTAIN_DATA_QUALITY and every non-terminal state are refused); the referenced Layer A event and label must exist and must agree with each other; `captured_at_utc` must be timezone-aware; `price_reaction_window` is required whenever `price_reaction_pct` is set and must be in the protocol's enum. Missing values stay **empty — never zero-filled** (a genuine measured `0.0` is still recorded as `0.0`). Writes are append-only and atomic: an existing `addendum_id` raises rather than being overwritten, the original row's bytes survive an amendment verbatim, and the emitter touches no Layer A table and no freeze manifest.

  **On freeze sequencing:** the emitter deliberately does **not** require the linked label to be `human_frozen`. The protocol's corrected capture-vs-reveal rule (`B_Market_Response_Addendum/README.md`, 2026-08-02) states that capture "may happen automatically and contemporaneously with Layer A", that "capture and storage do not constitute reveal", and that a row "may be created regardless of the linked label's status". Fixture `case_10_layerB_captured_before_freeze_unrevealed` encodes this as an expected PASS. Requiring freeze at capture time would invent stricter sequencing than the protocol defines and would contradict a locked fixture verdict. Reveal remains gated in the freeze manifest, which this emitter never writes.

**5. New CI workflow — PR #3 previously had no CI at all.** The only existing workflow was path-filtered to `Event_Dossier_Protocol/**`, so no market-response change ever triggered a check. `.github/workflows/market-response-tests.yml` now runs on `pull_request` for `gst_market_response/**`, `test_market_response*.py`, `Event_Dossier_Protocol/**`, the market-response specifications and field dictionaries, `requirements.txt`, and the workflow itself, plus `workflow_dispatch`. Least privilege (`contents: read`), pinned Python 3.12, pinned `requirements.txt`. It **discovers** every `test_market_response*.py` rather than hardcoding filenames and **fails if discovery returns nothing**, so a vacuous pass is impossible; it also runs the Event Dossier validator suite as a cross-protocol dependency. It never invokes the live smoke script, a provider diagnostic, the 24-ticker panel, or anything requiring a credential or network access — `test_market_response_ci_workflow.py` asserts all of that statically against the file.

**CI bootstrap trigger (added 2026-08-06, temporary).** GitHub created **zero** workflow runs and **zero** check suites from the `pull_request` trigger, despite the workflow file being present and byte-identical at the PR head, the branch tip and `refs/pull/3/merge`; despite its path filters matching 45 of the PR's 51 changed files; despite `GET /actions/permissions` reporting `enabled: true` with `allowed_actions: all`; and despite nothing sitting in `action_required`, `waiting` or `queued`. Closing and reopening PR #3 — a default `pull_request` activity type, and confirmed recorded in the timeline as `reopened` — produced nothing either. Because the workflow is not yet registered on `main`, `workflow_dispatch` cannot be used to start it manually. A `push` trigger scoped to `branches: [phase2-market-response]` was therefore added purely to get a first run recorded for this branch; a deterministic test pins it to that single branch so it can never run repo-wide, and it should be removed once the workflow has landed on `main` and the `pull_request` trigger is confirmed working. No job, step, test command, permission, dependency, timeout or discovery rule was changed.

**Tests.** Five new deterministic files, all fixture-based and offline: `test_market_response_protocol_boundary.py` (23), `test_market_response_layer_b_emission.py` (55), `test_market_response_canonical_drift.py` (15), `test_market_response_phase2_status_normalization.py` (31), `test_market_response_ci_workflow.py` (44). Full local gates: Phase 2 **12 files / 617 assertions**, Market Response **15 files / 601 assertions**, Event Dossier validator **27 end-to-end assertions + 21 unit tests** via its exact CI discovery command. Every suite was re-run with outbound sockets blocked and still passed. Operational Wikipedia cache (`2cc29dde…ad93d`, 8238 rows) and all preserved panel artifacts verified byte-identical.


## 2026-08-05 — Phase 2: bounded identical-request retry on HTTP 404 in the anchor-month availability stage

**Why.** The 22/24 availability gate (`4501e36`, evidence in `Live Signal Engine/Phase2 Failure Evidence/2026-08-05_AnchorMonth_AvailabilityGate_22of24/`) confirmed the pacing fix works — zero unhandled 429s across 26 requests — but left GPN and TTWO failing on a *single* HTTP 404 against the exact anchor-month request. That is transient CDN transport behaviour, not unavailable data and not an identity problem: both articles are locked and previously identity-validated, the set of 404-ing articles changes between runs, and CTSH/INTC/SYK (the three previously "unresolved" intervals) all returned clean 200s in the same gate.

**What changed** (`GST_Phase2_Wikipedia_Transport.py`, Stage 1 only):

- A 404 now triggers a bounded retry of the **identical** request — same article title, same date boundaries, same endpoint/access/agent/granularity. Stage 1 has exactly one `fetch_fn` call site with a fixed argument tuple, so no code path can vary the request between attempts (asserted by test 25).
- `ANCHOR_MONTH_MAX_ATTEMPTS = 3` (initial + 2 retries); `ANCHOR_MONTH_404_BACKOFF_S = [20.0, 40.0]` plus bounded 0–5 s jitter. A longer server `Retry-After` is honoured over the schedule, still capped at `AVAILABILITY_MAX_RETRY_AFTER_WAIT_S`.
- Every attempt, retries included, passes through the one `SharedRequestLimiter`; the backoff is applied *through* that shared gate, so a burst of retries cannot exceed the global rate.
- Retries stop early if the next wait would push past the total-run safety budget (`remaining_budget_s`, wired to `TOTAL_RUN_BUDGET_S`).
- **First structurally valid HTTP 200 wins** — no further attempt is ever made to chase a fresher watermark (test 26).
- Only a 404 *opens* a retry sequence; an invalid 200 may *continue* an open one, so a first-attempt malformed response keeps its prior fail-closed behaviour. 400/401/403 are never retried. 429 and 5xx/timeout keep their pre-existing bounded handling unchanged.
- A 404 surviving all three attempts remains a hard fail-closed result. No alternate request shape, cached magnitude data, zero-fill, interpolation, synthetic observation, or aggregate-watermark substitution — and Stage-1 responses are still never written to the operational cache.

**Additive provenance** (per ticker, on the panel row, in `stage1_results`, and in the completion marker): `anchor_month_attempt_count`, `anchor_month_attempt_statuses`, `anchor_month_retry_wait_seconds`, `anchor_month_recovered_after_transient_404`, `anchor_month_final_http_status`. None participates in any gate.

**Tests**: 15 new deterministic tests (19–33) covering every required case — success on attempt 1; 404→200; 404,404→200; three 404s fail closed; 404 then malformed 200 (with and without a later valid attempt); 400/401/403 never retried; identical URL and boundaries on every attempt; no alternative-range fallback; first valid 200 stops further calls; all attempts through the shared limiter; `Retry-After` honoured, capped, and not shrinking the schedule; total-run budget stopping retries; deterministic jitter injection; provenance matching the real attempt sequence; no cache writes; and magnitude-independence of retry and watermark decisions. Full deterministic suite: **12 files, 617 assertions, all passing**; operational cache byte-identical (`2cc29dde…ad93d`, 8238 rows).

**Live availability gate (cache-isolated, no panel): 23/24, still failed closed.** The mechanism works as intended — **GPN recovered on attempt 2** (`404, 200_ok`, 24.8 s wait), exactly the case it was built for, and zero 429s occurred across 27 requests. **TTWO exhausted all three attempts** (`404, 404, 404`; waits 24.6 s and 43.8 s; ~68 s span). Of the 23 that succeeded, 12 reported `2026-08-03` and 11 reported `2026-08-04`, so the candidate common watermark would have been `2026-08-03`. Per the gate, no panel was run, the gate was not rerun, and no further fallback was added.

## 2026-08-05 — Phase 2 correction: two-stage anchor-month watermark replaces the separate availability probe

**Corrects commit `9990c39`**, which a read-only live diagnostic proved release-blocking before it ever ran a panel. Full evidence: `Live Signal Engine/Phase2 Failure Evidence/2026-08-05_EffectiveWatermark_Probe_Design_Failure/` (commits `a0ec503`, `1ec102a`).

**What was wrong with `9990c39`:**

1. `resolve_effective_panel_watermark()` issued 24 unpaced requests. Wikimedia throttles from request 11 (14 × HTTP 429, `Retry-After` counting down 39→20 s), so `measured=9/24` → `failed_closed` → every run would be PARTIAL. Strictly worse than the behaviour it replaced.
2. Availability is **request-shape-dependent**. The same date is present in one range's response and absent from another's, for the same article, seconds apart (ADBE and GOOGL both return `2026-08-04` for `07-22..08-04` but not for `08-01..08-04`) — consistent with URL-keyed CDN response caching. A separate fixed-14-day probe therefore cannot certify what the production calendar-chunk request returns. The premise was unsound, not merely mistuned.

**What changed.** The separate probe is **deleted**, not tuned — `measure_article_latest_available_date()` and `PER_ARTICLE_PROBE_WINDOW_DAYS` no longer exist. Availability is now measured from the *same response production reuses*:

- **Stage 1** (`retrieve_anchor_month_availability()`): one request per ticker, exactly `anchor_month_start(aggregate_watermark) .. aggregate_watermark` — the same calendar-chunk shape production consumes, never through wall-clock today, never past the aggregate watermark (an upper bound only). All requests pass through a single `SharedRequestLimiter` (3.5 s minimum interval — the smallest rate this project has direct evidence for) which also absorbs capped `Retry-After` backoff on behalf of every subsequent caller. One bounded 429 re-attempt per ticker; a second 429 fails closed.
- `validate_anchor_month_response()` accepts a **trailing** shortfall (that is the measurement) but rejects empty, malformed, out-of-range, duplicate/conflicting, late-starting, or internally gapped responses.
- **Stage 2** (`resolve_effective_panel_watermark()`): `effective = min(anchor-month latest observed)` across all 24, then each Stage-1 response is **sliced to that watermark and reused in memory** — no second anchor-month request, and nothing trailing-short is ever cached under a key implying coverage through the aggregate watermark. Each sliced response must still have exact daily coverage from `anchor_month_start` through the effective watermark.
- `get_ticker_wikipedia_daily()` gains `prefetched_chunk_rows`; a matching chunk is satisfied from memory with zero network calls and zero cache writes, still passing through `validate_snapshot()`. New source mode `anchor_month_stage1`.
- The request horizon in `process_ticker()` is now the aggregate watermark, so the final generated chunk is exactly the Stage-1 shape. The prior comment claiming a wall-clock horizon was harmless is rewritten: it was *accurate* about HTTP truncation (verified — production always requested `chunk_start..min(chunk_end, watermark)`), but it left the chunk's nominal end past the watermark, which is the wrong shape to match Stage 1 against.
- Completion marker gains anchor-month request boundaries, per-ticker observed boundaries, and response-reuse provenance.

**Scope, unchanged.** This removes only **trailing** unpublished dates. Interior historical gaps still fail — `validate_anchor_month_response()` rejects them outright, and lowering a trailing edge cannot reach inside a sequence. Untouched: locked 24-ticker universe, six-field contract, z-score formula, earnings rules, historical results, cache-integrity requirements, cache-union and bounded-subchunk rules, and the COMPLETE decision rule's existing criteria.

**Tests**: `test_phase2_wiki_effective_panel_watermark.py` rewritten for the two-stage design (108 assertions, zero network) covering all 18 required items, including that the deleted probe is absent from production source, rollover into a prior calendar month, request-shape-dependent fixtures being unable to split measurement from retrieval, single-shared-limiter pacing under a deterministic fake clock, `Retry-After` honoured and capped, exhausted-429 and 404 fail-closed, slicing as pure filtering, and magnitude/order invariance. Full deterministic suite: **12 files, 503 assertions, all passing**; operational cache byte-identical (`2cc29dde…ad93d`, 8238 rows).

**Live availability-only diagnostic (cache-isolated, no panel).** Pacing is fixed: **zero unhandled 429s** across 26 requests; two transient throttles auto-recovered via `Retry-After`. But Stage 1 **failed closed at 22/24** — GPN and TTWO returned HTTP 404 on the anchor-month range. Of the 22 that succeeded, 17 reported `2026-08-03` and 5 reported `2026-08-04`, so the common watermark would have been `2026-08-03`. Per the gate, no panel was run and no fallback was added.

## 2026-08-05 — Phase 2: common per-article availability watermark (aggregate endpoint is no longer the binding bar)

**Why this changed.** The 2026-08-05 PR #1 merge-gate regression returned PARTIAL with `all_six_fields_clean=5`. Root cause: the binding Wikipedia data watermark was measured from the **aggregate** pageviews endpoint (`.../aggregate/en.wikipedia.org/...`) but enforced against the **per-article** endpoints — two different publication pipelines. At 02:14Z the aggregate had published `2026-08-04`; only 5 of the 24 locked articles had. The other 19 returned HTTP 200 with a short series and were correctly rejected as `incomplete_coverage`, on the first pass and again on the second pass ~16 minutes later. Full evidence, including the cross-run lag correlation that isolates watermark lag (not the branch under test) as the discriminator: `Live Signal Engine/Phase2 Failure Evidence/2026-08-05_AggregateVsPerArticle_Watermark_PARTIAL/`.

The 2026-08-01 correction was right as far as it went — it made the *measured* watermark the single source of truth for open and closed chunks alike. The residual gap was one level up: that watermark is measured from a different endpoint than the one it gates, and a single aggregate probe cannot certify 24 independent per-article publication states.

**What changed** (`GST_Phase2_Wikipedia_Transport.py`, `GST_Phase2_DailyPanel.py`):

- New `measure_article_latest_available_date()`: one per-article range request of **exactly the production request shape** (`fetch_chunk_isolated`, range not single-day — a single-day per-article probe is known to 404 where a wider range succeeds), returning `max(observed dates)` from validated HTTP-200 rows. Fails closed on 404/timeout/malformed/empty; never retries, widens, reshapes, or consults the cache. Reads `date` and transport metadata only.
- New `resolve_effective_panel_watermark()`: `effective_panel_watermark = min(per-article latest available date)` across **all 24** locked tickers, resolved once at run start. Taking the minimum is what makes one shared date safe — it is by construction a date every article has already published. Fails closed if even one ticker is unmeasurable; a minimum over a subset is not a panel watermark, and the aggregate watermark is never substituted.
- The effective watermark now binds `pull_start`, expected coverage, the z-score anchor and provenance for **every** ticker in a run. Per-ticker anchor dates inside one panel are impossible by construction and rejected by the gate.
- The aggregate watermark is retained unchanged as a source-health/provenance observation, with the signed divergence recorded. It never raises the effective watermark.
- Five additive provenance fields: `wiki_aggregate_watermark_date`, `wiki_article_latest_available_date` (this ticker's own measured value, for audit — it anchors nothing), `wiki_effective_panel_watermark_date`, `wiki_effective_watermark_method`, `wiki_aggregate_vs_panel_lag_days`. The completion marker gains the full per-article measurement set.
- `is_run_complete()` gains two fail-closed conditions: the effective watermark must have resolved, and every row must carry the same non-null effective watermark **and** be anchored on it.

**What deliberately did NOT change.** This lowers a shared **trailing** edge; it does not forgive a hole. Exact daily coverage across the complete required lookback is still demanded of every ticker, so an internal historical gap — CTSH's missing `2026-07-08..2026-07-14`, and the persistent INTC/SYK `2026-08` 404s — sits *below* the effective watermark and still produces PARTIAL. Untouched: the locked 24-ticker universe, the six-field contract, the z-score formula (`to_weekly`/`compute_zscore_at_anchor`), earnings rules, retry counts, subchunk boundaries, and the COMPLETE decision rule's existing criteria.

**Tests**: `test_phase2_wiki_effective_panel_watermark.py` (new, 94 assertions, zero network calls) covers all 11 required scenarios — all-articles-equal-aggregate; 5-at-D/19-at-D−1 producing a common D−1; one ticker lagging two days; missing article watermark; mixed per-row anchors rejected; post-watermark observations excluded; internal historical gap still rejected (including that no lowering of the watermark rescues a gap below it); `pull_start` anchored to the effective watermark and not to the aggregate or wall clock; result invariant to ticker-processing order; no zero-fill or incomplete-coverage acceptance; operational cache byte-identical before and after — plus fail-closed gate coverage, probe-shape/no-fallback coverage, aggregate-as-provenance coverage, and a direct **non-circularity** proof that the measurement is invariant to pageview magnitude (identical result across all-1s, all-1e9, pseudo-random, and all-0 view counts).

Three existing test files were updated for the new call signatures (`test_phase2_dailypanel_gate.py`, `test_phase2_wiki_pull_start.py`, `test_phase2_wiki_source_provenance.py`) — each supplies a healthy effective watermark by default so it keeps probing the dimension it was written for. Full deterministic suite: **12 files, 484 assertions, all passing**; operational cache verified byte-identical (`2cc29dde…ad93d`, 8238 rows) before and after.

No live 24-ticker panel was run in this pass.


## 2026-08-04 — Market Response: ALP-1 fix + post-fix validation (PR #3, fourth pass, no real event registered)

**What this is.** Fix defect ALP-1, split provider eligibility into its two real components, retract an
unsupported claim from the pass-3 report, and run one post-fix live validation. **No earnings event was
registered, no Radar integration, no backtest, no other worktree touched, nothing merged.**

**Preflight**: HEAD `34bf25033e9174405e76b4901d0fe2610fb70645` as expected, tracked tree clean, no relevant
process running, Wikipedia cache `29d072f2…` and both preserved panel artifacts unchanged, both credentials
present (presence only — never printed, logged, serialized or committed).

### Defect ALP-1: FIXED and CLOSED

Alpaca treats `end` as **inclusive** of a bar whose start equals `end`, so requesting `end = session_close_utc`
(16:00 ET) pulled the 16:00–16:05 ET after-hours bar into every regular-session request as a 79th bar. Fixed in
three independent layers, each of which alone would prevent the observed corruption:

1. **Request boundary** — `fetch_bars_alpaca_sip` now sets `end` to the **final expected bar start** from the new
   `exchange_calendar.expected_bar_starts_utc()` (19:55Z / 15:55 ET), never `session_close_utc`. Derived
   dynamically from the calendar, so an early close asks through 12:55 ET (42 bars) with no special case.
2. **Fail-closed validation** — new `_assert_exact_session_grid()` requires the returned timestamp set to
   **equal** the expected set. Missing, extra, duplicate, misaligned and out-of-session bars each raise the new
   `AlpacaSessionGridError`. It never trims, pads, re-sorts or de-duplicates: silently repairing a malformed
   response is exactly how ALP-1 stayed invisible until a live diagnostic looked for it. Bypassed only on the
   1Day cross-check path, which does its own "exactly one bar" check.
3. **Boundary selection** — `bars.extract_session_fields()` now selects the open and close bars **by their
   expected timestamps**, never `bars[0]`/`bars[-1]`, and aggregates high/low/volume over on-grid bars only. A
   stray 16:00 ET bar cannot become `session_close`, set the session high/low, or inflate volume even with layers
   1–2 bypassed entirely. Extraction is now order-independent, and bars spanning two sessions raise the new
   `MixedSessionError` rather than silently using one.

### Post-fix live validation: **BOTH PASSED**

One run per ticker, 2026-08-03 XNYS session, neither registering a research event.

| | SPY | BRK-B (`BRK.B`) |
|---|---|---|
| Verdict | **PASSED 33/33** | **PASSED 29/29** |
| HTTP | 200 | 200 |
| Query on the wire | `adjustment=raw&end=2026-08-03T19:55:00Z&feed=sip&limit=10000&sort=asc&start=2026-08-03T13:30:00Z&timeframe=5Min` | identical |
| Symbol echo | `SPY` | **`BRK.B`** |
| **Bars** | **78 / 78** | **78 / 78** |
| First → last bar | **09:30 → 15:55 ET** | **09:30 → 15:55 ET** |
| Off-grid / missing | 0 / 0 | 0 / 0 |
| Pages / retries | 1 / 0 | 1 / 0 |
| Raw SHA-256 | `1313d07b2a5843d89d6e3bd0cc7c4cb3e011482709812cc21cb1132a18aa7af2` | `4d3c6713b6ce1f6b75f9d53dfe73a32c13f569bab18f1e2a36021e9983d0ffd9` |

The requested `end` is now `19:55:00Z` rather than `20:00:00Z` — that single change is the fix.

**The daily cross-check independently confirms it.** The uncontaminated 78-bar aggregate reproduces Alpaca's own
1Day SIP OHLC **exactly**: open 749.44, high 758.58, low 748.80, close **757.67**, all at **0.0** relative
difference. The pass-3 contaminated 79-bar aggregate had put close at 757.72, 6.6 bp off.

**Provider status advanced to `LIVE_DIAGNOSTIC_PASSED`.** This clears the provider for real event capture. It is
**not** production-readiness: one complete prospective earnings event is still required.

### Eligibility split

`is_eligible_for_real_event` was a hard-coded `True` on the Alpaca provider. That one flag fused two unrelated
ideas, so it read as clearance for real capture while no live diagnostic had ever run — and kept reading that way
after one FAILED. Now separate:

- **`supports_real_event_semantics`** — structural, permanent. `True` for Alpaca, `False` for yfinance.
- **`operational_clearance_status`** — operational, changes over time: `NOT_RUN` / `LIVE_DIAGNOSTIC_FAILED` /
  `LIVE_DIAGNOSTIC_PASSED`.
- **`is_eligible_for_real_event`** — **derived**, never set directly, via the new pure
  `providers.compute_real_event_eligibility()`, which additionally requires `feed == "sip"`,
  `adjustment == "raw"`, the ALP-1 grid guard active, and credentials present.

`NOT_RUN`, `LIVE_DIAGNOSTIC_FAILED`, an unrecognized clearance string (unknown fails closed), `feed="iex"`, a
non-raw adjustment, a disabled grid guard, absent credentials, and yfinance are each independently disqualifying.
Disabling the ALP-1 guard mechanically revokes clearance. Being pure, the full truth table is deterministically
tested without constructing a provider or touching a network — `feed="iex"` is exercised as an *input*, so no IEX
code path exists.

### Correction to the pass-3 report

**Retracted:** the claim that the −15.50% daily-vs-aggregate **volume** difference was "most likely" extended-hours
volume. That was an unsupported guess, never verified against vendor documentation or a controlled experiment, and
it should not have been offered as a leading explanation. It is now classified
**`unresolved_provider_aggregation_semantics`** — which trades each series counts is unknown, and **no explanation
is offered**. The retraction is recorded inline in the preserved pass-3 section rather than by rewriting it.

Consequently: daily **OHLC** remains a genuine sanity comparison and *is* gated (10 bp) — as pass 3 demonstrated
when contamination pushed close 6.6 bp off. Daily **volume** is **informational only and not an equality gate**,
and becomes one only if identical aggregation semantics are first proven. An Alpaca 1Day volume must never be
compared against, or substituted for, a regular-session volume aggregate.

### Tests

New `test_market_response_alp1_session_grid.py` (**79 checks**): inclusive-`end` request boundary; dynamically
derived early-close end (42 bars, 12:55 ET); normal session returning exactly 78 bars 09:30→15:55; extra 16:00 ET
bar; missing 15:55 ET bar; missing interior bar; duplicate bar; unordered response; misaligned bar; premarket bar;
clean-grid acceptance; exact-boundary extraction; a stray 16:00 bar being unable to affect close/high/low/volume;
order independence; early-close extraction; missing-boundary-yields-None; mixed-session rejection; and the full
eligibility truth table across every clearance state.

Harness 47 → 57 (corrected daily-comparison semantics, OHLC-gated vs volume-informational, retraction enforced by
test). Provider 70 → 67: the 3 removed are the ALP-1 characterization checks that asserted the *defective*
boundary — replaced, exactly as their own docstring instructed, by corrected-boundary assertions in the new file.

**Full suite: 21 files, 737 → 823 checks, all passing, zero regressions** (+89 added, −3 replaced). Verified in
**both** clearance states — the truth-table tests are deliberately state-independent, so flipping the constant
cannot make them vacuous.

### Data protection

Credentials never printed, logged, serialized or committed. Raw bars written only to the session scratchpad
outside the repository. **The pass-3 failed diagnostic reports are preserved byte-identical**; the new post-fix
evidence is committed alongside as `..._LIVE_DIAGNOSTIC_POSTFIX_{SPY,BRK-B}_2026-08-03.json` (checks, aggregates,
statuses, provenance and hashes only — no bar rows). Byte-level credential scan over all tracked and untracked
files plus staged/unstaged diffs: zero hits. Wikipedia cache `29d072f2…` and both preserved panel artifacts
re-verified byte-identical. No child process remained.

**Remaining blockers**: one complete prospective earnings event; clearance rests on one session and two
non-universe benchmark tickers; no early-close session has been live-validated (deterministically tested only);
the vendor's 1Day aggregation semantics remain unresolved.

**No real event has been registered. No trading strategy is selected. No profitability claim exists.**

## 2026-08-04 — Market Response: live-validation pass (PR #3, third pass, no real event registered)

**What this is.** One narrow live-validation pass on the Earnings Market-Response Decomposition lane (PR #3,
stacked on PR #1): correct how the sector mapping states its own basis, and run the single permitted bounded live
Alpaca diagnostic. **No earnings event was registered, no Radar integration was started, no strategy or backtest
was run, no other worktree was modified, nothing was merged.**

**Preflight**: branch `phase2-market-response` confirmed, local HEAD == `origin/phase2-market-response` ==
`ca7fca61f91b08b76241f4a7d6c2c8dd1b8a45fc` as expected, tracked working tree clean, no market-response/Phase 2
process running (the seven live Python processes belong to an unrelated `charis11_offset_analysis.py` run),
operational Wikipedia cache hash `29d072f2...` unchanged. `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` both confirmed
**present** (presence only — values never printed, logged, serialized or committed). PR #3 confirmed to exist and
be unmerged via `refs/pull/3/head == ca7fca6` (distinct from `main` @ `46aec158`); **its draft flag could not be
read** — `gh` is not installed, the repository is private so the unauthenticated API returns 404, and a
credential-based API probe was blocked by the environment's permission policy. Nothing in this pass alters PR
state; pushing commits to a draft PR's branch leaves it draft.

### Bounded live Alpaca diagnostic: **RAN — FAILED** (both tickers)

Two diagnostics, **exactly once each**, against the completed 2026-08-03 XNYS session. Neither registered a
research event. No fallback to IEX, yfinance, Yahoo, another provider, or synthetic data was made or considered,
and neither diagnostic was restarted.

- **Diagnostic A — SPY** (not in the locked universe, no earnings date): HTTP 200; `feed=sip`, `timeframe=5Min`,
  `adjustment=raw` all confirmed **on the wire**; 1 page; 0 retries; raw-response SHA-256 `e253a7b6...`.
  **27/31 checks passed. Verdict FAILED.**
- **Diagnostic B — canonical `BRK-B` / provider `BRK.B`**, same session, symbol-translation validation only:
  HTTP 200; **Alpaca echoed `"symbol": "BRK.B"`**; raw-response SHA-256 `9b0bb3aa...`. **25/29 checks passed.
  Verdict FAILED**, on the identical four checks and no others.

**Defect ALP-1 (open).** Both returned **79 bars where the XNYS calendar requires 78**, with a trailing bar
starting 16:00 ET. Root cause: `fetch_bars_alpaca_sip` requests `end = session_close_utc` (20:00:00Z), and
Alpaca's `end` is **inclusive** of a bar whose start equals `end` — so every request admits one after-hours
(16:00–16:05 ET) bar. This is not cosmetic: `extract_session_fields()` takes `session_close` from `bars[-1].close`,
so the after-hours bar silently *became* the session close, shifting SPY's `open_to_close` from `0.01098153` to
`0.01104825` (**+6.7 bp**) and full-session volume from 50,712,611 to 52,265,414 (**+3.1%**).

**The daily cross-check independently corroborates it.** Aggregating only the 78 regular-session bars reproduces
Alpaca's own 1Day SIP bar's OHLC **exactly, to the cent** (open/high/low/close all `0.0` relative difference:
749.44 / 758.58 / 748.80 / 757.67). Under the contaminated 79-bar aggregate the close diverges by 6.6 bp.
**Separate finding, reported not explained away**: aggregate volume differs from the 1Day bar by **-15.50%**
(50,712,611 vs 60,014,445). Leading explanation — Alpaca's 1Day equity bar includes extended-hours volume, so a
regular-session aggregate by construction will not match. Not confirmed against Alpaca documentation in this pass.
Practical consequence: an Alpaca 1Day volume must never be compared against or substituted for a regular-session
volume aggregate.

**Everything else passed**, on both tickers: exact XNYS window requested; **zero missing** regular-session bars;
first bar exactly 09:30 ET; unique, strictly monotonically increasing timestamps; every consecutive gap exactly
5 minutes; valid OHLC and nonnegative volume on every bar; no zero-fill signature and no zero-volume bar at all;
exactly 6 bars in the first 30 minutes; all five market-response derivations matching an independent recomputation
off the raw bars to within 1e-12; pagination handled and bounded; provenance complete; both canonical and provider
symbols preserved; IEX never requested.

**Status per the governing rule: `LIVE_DIAGNOSTIC_FAILED`. The Alpaca provider is INELIGIBLE for real event
capture.** It is not production-validated and not partially validated. `BRK-B` events are ineligible too, but by
inheritance from ALP-1 (which affects all 24 tickers equally) — **not** for a symbol-translation reason, since
`BRK-B -> BRK.B` is now live-verified and no longer an assumption. Note `is_eligible_for_real_event` still returns
`True` in code; that flag describes the provider's *class*, not its validation state, and is documented as not
constituting clearance.

**The fix is prescribed but deliberately NOT applied** (request `end = last_bar_start_utc`). The pass's one-run
rule meant a fix could not be live-validated here, and committing an unvalidated change would have left the
committed failure evidence describing code that no longer exists. It is pinned instead by characterization tests
that assert the current boundary **and its downstream consequence**, so it cannot land silently.

### Sector-mapping correction (v0.2 → v0.3, `schema_version` 0.1 → 0.2)

The mapping assigns each stock the broad sector ETF for its **GICS sector**; the company need not be a constituent.
v0.2 nonetheless summarised itself as a count of tickers verified to be *holdings* of their assigned ETF, flagging
GME as an unresolved ambiguity for failing that check — wrong in kind, not merely in wording. **The benchmark
methodology itself is unchanged.**

- Per-ticker fields separated into `gics_sector`, `benchmark_etf`, `benchmark_basis`, `constituent_status`,
  `constituent_status_source`, `classification_source`, `retrieval_date`. `benchmark_basis` is constrained to
  `"gics_sector"`; `"etf_membership"` is not an accepted value.
- The membership-count framing is **gone entirely**, and a test blocks any restatement of it.
- **GPN stays XLF.** **GME stays XLY**: its GICS Consumer Discretionary classification is **authoritatively
  confirmed by S&P Dow Jones Indices** (GICS co-owner) in its own index-announcement press release, corroborated
  by GME's current S&P MidCap 400 constituent row. GME is recorded as a **`confirmed_nonconstituent`** of XLY —
  structural, since XLY's eligible universe is the S&P 500 and GME is an S&P MidCap 400 member. **GME is nowhere
  represented as an XLY holding.**
- **`APPROVED` is now mechanically conditional on all 24 entries actually having been reviewed** — any ticker
  missing a `classification_source`/`retrieval_date`, or still `constituent_status="not_verified"`, invalidates an
  APPROVED mapping (the same entry stays fine while DRAFT).
- **Source-quality caveat disclosed in the file**: for the 22 tickers whose GICS sector was established via
  confirmed Select-Sector-ETF membership, the membership evidence is a third-party aggregator's holdings page, not
  an issuer-published holdings file.

### Code changes

- `gst_market_response/alpaca_provider.py` — added two sanitized provenance fields, `request_query_string` (the
  only first-hand evidence of what was requested, since Alpaca's single-symbol bars response does not echo `feed`)
  and `response_symbol_echo` (server-side confirmation the translated symbol resolved). `fetch_daily_bar_alpaca_sip`
  now requests the **calendar day** rather than the regular session — a 1Day bar is timestamped at midnight ET, so
  the old window excluded it and the absent bar was indistinguishable from a vendor gap — and raises rather than
  silently taking `bars[0]` if more than one comes back. The two window-override parameters serve only that path
  and cannot bypass the exchange calendar. **No SIP-only, raw-adjustment, timeout, retry, pagination or
  fail-closed rule was weakened.**
- `gst_market_response/diagnostics/alpaca_intraday_diagnostic.py` — rewritten from 13 partly-tautological checks
  to 31 real ones, covering every requirement of this pass. The prior check 9 ("missing intervals cause failure
  rather than zero-fill") was `missing == (len(bars) != expected)`, which is true unconditionally; it is replaced
  by exact grid-set comparison plus an explicit zero-fill-signature scan. Session boundaries are now compared as
  datetimes rather than ISO strings.
- `gst_market_response/sector_mapping.py` — `SectorMappingEntry` restructured to the seven separated fields;
  `VALID_BENCHMARK_BASES`/`VALID_CONSTITUENT_STATUSES` added; loader rejects an entry missing any required field;
  `validate_sector_mapping()` enforces the APPROVED-requires-actual-review gate. `sector_etf_for()`/`sector_for()`
  retained as aliases.

**Tests**: 1 new file — `test_market_response_alpaca_diagnostic_harness.py` (47 checks) proves the harness's own
detectors are real: it reconstructs the exact 79-bar response offline and confirms checks 8/10/12/19 fail and
*only* those, that a clean 78-bar session passes, that a 77-bar session fails *differently* (missing, not
contaminated), that zero-fill signatures / invalid OHLC / negative volume are each caught, that a mismatched symbol
echo fails, and that a provider error yields FAILED rather than a vacuous pass. `test_market_response_alpaca_provider.py`
**45 → 70** checks (sanitized request evidence, the calendar-day daily window, override-cannot-bypass-calendar, and
the ALP-1 characterization tests). `test_market_response_sector_mapping_gate.py` **20 → 47** checks, including the
required proof that a **confirmed nonconstituent can hold an approved sector benchmark without being represented as
an ETF holding**. One pre-existing test was corrected: `test_credentials_absent` asserted the provider constructor
raises because the ambient environment was empty — no longer true with credentials present, and confirmed to fail
when the baseline file is run against this environment — so it now creates and restores the absent-credential
condition explicitly instead of assuming it.

**Full deterministic suite re-run: 20 files, 737 checks, all passing, zero regressions** (baseline was 638 checks /
19 files; 638 − 45 − 20 + 70 + 47 + 47 = 737). All 17 untouched test files pass unchanged. Zero live network calls
beyond the two permitted bounded diagnostics. *(The prior pass's "43 checks" figure for the Alpaca provider file
counted `check()` call sites; 45 is the number actually executed, since one call site sits inside a four-iteration
loop. Corrected here for consistency — no test was removed.)*

**Data protection**: raw bars (79 rows × 2 tickers) written **only** to the session scratchpad outside the
repository, never committed. Committed artifacts are the two sanitized harness reports
(`GST_MARKET_RESPONSE_LIVE_DIAGNOSTIC_{SPY,BRK-B}_2026-08-03.json`) — check names, pass/fail, aggregates, statuses,
provenance and content hashes only, no bar rows, no credentials. A byte-level scan of all **3,605** tracked and
untracked files, plus the staged and unstaged diffs, found **zero** occurrences of either credential. Operational
Wikipedia cache re-verified byte-identical (`29d072f2...`) and the preserved Phase 2 panel CSV + completion marker
re-verified byte-identical, before and after. No child process remained afterward.

**Remaining blockers**: ALP-1 unfixed and the provider ineligible until a live diagnostic passes; **one complete
prospective earnings event is still required** regardless.

**No real event has been registered. No trading strategy is selected. No profitability claim exists.**

## 2026-08-04 — Market Response: operational-data pass (PR #3, second pass, no real event registered)

**What this is.** A second, narrower operational-data pass on the Earnings Market-Response Decomposition lane
(PR #3, stacked on PR #1): replaces the development-only intraday provider path and hand-maintained calendar with
operationally-eligible ones, reviews the sector mapping against real current data, and dry-runs the Phase 2
adapter against a real preserved panel run. **No research event was registered, no strategy/backtest was run, no
Radar integration was started.**

**Preflight**: branch/HEAD confirmed (`e755a90c14200633043fd3bba030557a6b4358b7`), no tracked/untracked drift, no
market-response/Phase 2 process running, PR #3 confirmed draft/open/stacked, operational Wikipedia cache hash
recorded (`29d072f2...`, unchanged throughout). **`APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` confirmed absent** (both
Bash and PowerShell, process and user scope, values never printed) -- this gated Section F (live Alpaca diagnostic)
to a documented stop-before-call, per instruction.

**What changed:**

- `gst_market_response/alpaca_provider.py` (new) -- `AlpacaHistoricalSipIntradayProvider`, calling
  `GET /v2/stocks/{symbol}/bars` directly (`timeframe=5Min, feed=sip, adjustment=raw, sort=asc`), bounded
  pagination, 401/403 fail immediately, 429/5xx retry (honoring `Retry-After`, capped) up to `MAX_ATTEMPTS=5`
  within `MAX_WALL_CLOCK_S=60`, a 15-minute freshness gate checked before any HTTP call, sanitized
  `AlpacaProvenance` (10 fields, never a secret), `BRK-B -> BRK.B` symbol translation (both identifiers always
  recorded, not yet live-verified), and `is_eligible_for_real_event = True` -- never falls back to IEX/yfinance/an
  undocumented endpoint/another vendor/synthetic bars on any failure.
- `gst_market_response/providers.py` (modified) -- added `IntradayOHLCVProvider.is_eligible_for_real_event`
  (default `False`); `YFinanceDevIntradayProvider` overrides it explicitly to `False` (unchanged behavior, now
  structurally enforced rather than only documented).
- `gst_market_response/exchange_calendar.py` (new) -- wraps `exchange_calendars` (`XNYS`, pinned
  `exchange_calendars==4.13.2` in new `requirements.txt`) for `is_trading_day`/`previous_session`/`next_session`/
  `session_open_utc`/`session_close_utc`/`is_early_close`/`expected_bar_boundaries` (correctly shrinks the expected
  5-minute-bar count on an early-close session, e.g. 42 instead of 78 on the day after Thanksgiving).
- `gst_market_response/event_registry.py` (modified) -- the hand-maintained partial holiday list
  (`is_trading_day_v0_1` and its constants) is superseded, renamed with a `_SUPERSEDED_` prefix, and kept only for
  auditability; `register_verified_event()`/`amend_event()` now default to the real XNYS calendar;
  `EXCHANGE_CALENDAR_ID` recorded in new rows is `XNYS_exchange_calendars_v4.13.2`.
- `gst_market_response/bars.py` (modified) -- added `validate_ohlc_and_volume()` (`InvalidOHLCError`/
  `NegativeVolumeError`), shared by both the yfinance and Alpaca diagnostics.
- `gst_market_response/diagnostics/alpaca_intraday_diagnostic.py` (new) -- the bounded live-diagnostic harness for
  Alpaca (12 checks matching Section F's requirements). **Not executed in this pass** -- credentials absent.
- `Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json` (modified, `mapping_version` 0.1 -> 0.2,
  `review_status` DRAFT -> **APPROVED**) -- all 24 tickers individually reviewed against actual current sector-ETF
  holdings (companiesmarketcap.com fund-holdings pages) or sourced GICS classification, retrieved 2026-08-04.
  **GPN corrected from XLK to XLF** -- confirmed absent from XLK's 77 holdings, confirmed present in XLF's holdings
  (0.24% weight), consistent with the real 2023 GICS reclassification of the "Transaction & Payment Processing
  Services" sub-industry from Information Technology to Financials. **GME's XLY fund-constituency could not be
  confirmed** against XLY's disclosed ~50-holding list (GICS sector itself -- Consumer Discretionary -- is
  source-confirmed and unchanged) -- left explicitly documented as an open question, not silently resolved.
  22 other tickers confirmed as current constituents of their existing assignment, unchanged.
- `gst_market_response/sector_mapping.py` (modified, additive) -- `SectorMappingEntry`/`SectorMapping` gained
  `review`/`effective_date` fields to carry the above per-ticker provenance.
- Phase 2 adapter dry run (no code change) -- `import_pre_event_fields_for_ticker()` run read-only against
  `GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv` + its completion marker (a real, preserved, COMPLETE 24-row
  panel run from the `phase2-wikipedia-reliability` worktree). **24/24 tickers imported without error,
  `panel_status="COMPLETE"` preserved exactly, 24/24 rows eligible for `PRE_EVENT_CAPTURED`, both input files
  SHA-256-verified byte-identical before and after.** Confirms the adapter is operationally compatible with a real
  panel run, not just synthetic fixtures.

**Tests**: 2 new deterministic test files -- `test_market_response_alpaca_provider.py` (43 checks: credentials
absent, 401/403 never retried, 429+Retry-After, transient 5xx recovery, bounded retry exhaustion, timeout, empty
bars, pagination, duplicate-timestamp/out-of-session/missing-bar detection via composition with existing
validators, invalid OHLC/negative volume, symbol translation, 15-minute freshness gate, IEX never requested,
yfinance-ineligible/Alpaca-eligible, no file writes, secrets never in logs/provenance/repr) and
`test_market_response_exchange_calendar.py` (29 checks: ordinary session, weekend, full holiday, early close, DST
both directions, AMC, BMO, INTRADAY, exact first/last bar, no after-hours contamination, non-session error). 7
checks added to the existing sector-mapping test file (13 -> 20) proving every ticker carries a review block, GPN's
correction, and GME's documented ambiguity. **116 new checks total.** Full 19-file deterministic suite (11
pre-existing + 8 market-response) re-run: **638 checks, all passing, zero regressions.** Zero live network calls
(the one permitted live diagnostic did not run -- credentials absent). Operational Wikipedia cache re-verified
byte-identical (`29d072f2...`); the real preserved Phase 2 panel CSV and its marker also re-verified byte-identical.

**No real event has been registered. No trading strategy is selected. No profitability claim exists.**

## 2026-08-04 — Market Response: operational-readiness pass (PR #3, no real event registered)

**What this is.** An operational-readiness pass on top of the Earnings Market-Response Decomposition lane
(PR #3, `phase2-market-response`, stacked on PR #1) -- not a new research module, and no strategy test, backtest,
24-ticker panel run, Radar integration, or real-money trade was performed.

**What changed** (all additive, scoped to `gst_market_response/` and its docs):

- `gst_market_response/event_registry.py` (new) -- `HumanVerifiedEventRegistry` + `RegistryBackedEventTimingProvider`,
  a `providers.EventTimingProvider` implementation backed entirely by human-verified primary-source rows (never
  scraped/inferred). A date without `verification_status == "verified"` cannot reach `REGISTERED`
  (`to_event_identity()` raises). `expected_response_session` is always mechanically derived, never a manual input.
  Corrections are append-only `AMENDMENT` rows; originals are never overwritten. Synthetic fixtures only -- no real
  event was populated.
- `gst_market_response/phase2_adapter.py` (new) -- explicit-path-only Phase 2 pre-event importer. Never discovers
  "the latest file," hashes both the CSV and completion marker, cross-verifies the marker's claimed counts against
  the CSV's actual content (rejects on mismatch), preserves `COMPLETE`/`PARTIAL` and all nulls/source statuses
  exactly, and structurally excludes the panel's generic `implied_volatility` from ever being imported as
  `earnings_implied_move`.
- `gst_market_response/sector_mapping.py` (modified, additive) -- `validate_sector_mapping()` and
  `assert_usable_for_real_event()`. `Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json` (modified) now carries
  `mapping_version`, `review_status` (currently `DRAFT`), `reviewed_by`, `reviewed_at_utc`, and per-ticker `sector`
  names alongside `sector_etf`; the file's own `description` field now states explicitly this is a benchmark-design
  choice, not an alpha assertion. The mapping is **not** silently declared final by this change.
- `gst_market_response/providers.py` (modified) -- `YFinanceDevIntradayProvider.get_bars()`/`get_daily_bar()` now
  pass `auto_adjust=False, prepost=False` to `yfinance` explicitly rather than relying on its library default;
  added `get_daily_bar()` for cross-checking aggregated intraday OHLC.
- `gst_market_response/diagnostics/intraday_provider_diagnostic.py` (new) -- the bounded live-diagnostic harness
  (code only; produces no committed data).

**Bounded live diagnostic result: FAILED.** One live diagnostic of `YFinanceDevIntradayProvider` was run against
SPY (not a locked-universe ticker, no earnings date -- structurally non-research) for the 2026-08-03 session.
The provider returned zero bars. A direct `curl` request to the identical Yahoo Finance endpoint succeeded with
real data immediately afterward, pointing to an environment-specific defect in `yfinance`'s own cookie/crumb
negotiation pipeline rather than a genuine data gap -- but per instruction, no workaround was applied and no
substitute provider was used. Classified FAILED and stopped. Full detail:
`GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md`.

**Tests**: 4 new deterministic test files -- `test_market_response_amendment_semantics.py` (21 checks: PARTIAL
immutability/terminality, amendment linkage, byte-identical originals, independent per-tier gate satisfaction,
full chronology reconstruction), `test_market_response_event_registry.py` (16 checks), `test_market_response_phase2_adapter.py`
(27 checks), `test_market_response_sector_mapping_gate.py` (13 checks) -- 77 new checks total, all passing. Full
17-file deterministic suite (11 pre-existing Phase 2/Wikipedia files + 6 market-response files, 2 pre-existing plus
these 4 new) re-run: all passing, zero regressions, zero live network calls beyond the single bounded diagnostic
above. Operational Wikipedia cache independently re-verified byte-identical (`29d072f2...`) before and after.

Documentation updated: spec (new "Operational-readiness addendum" section, nothing in sections 1-10 changed),
field dictionary (new sections for the registry/adapter/mapping-gate/diagnostic result + restated standing
disclaimers), two new docs (`GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md`,
`GST_MARKET_RESPONSE_OPERATIONAL_READINESS_CHECKLIST_v0.1.md`).

**No real event has been registered. No trading strategy is selected. No profitability claim exists.**

## 2026-08-04 — New lane: Earnings Market-Response Decomposition (measurement module, v0.1 draft)

**Branch:** `phase2-market-response`, a new sibling worktree at `gst-market-response-worktree`, based on
`origin/phase2-wikipedia-reliability` @ `b400af239d89b313f7705e941ddfa7b4c2beb76b`. **Stacked on PR #1** — this
branch depends on `phase2-wikipedia-reliability` and must not be reviewed or merged ahead of it.

**What this is.** A new, isolated research lane collecting the data needed to determine WHERE earnings-related
market movement occurs relative to a pre-event GST/Wikipedia attention observation — overnight gap, first 30
minutes, rest of session, and the next two trading sessions, each also computed relative to a locked sector-ETF
mapping and SPY. **This is a measurement module. It does not test, optimize, select, or report a trading strategy**
— see `GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.1.md` for the explicit non-advisory framing.

**What changed** (entirely additive, new files only — nothing in the existing Wikipedia transport, GST z-score
methodology, six-field contract, locked 24-ticker universe, or Event Dossier Protocol was touched):

- `Live Signal Engine/GST_Earnings_Market_Response_Decomposition_SPEC_v0.1_DRAFT.md` (new) — locked draft spec:
  event identity (BMO/AMC/INTRADAY fail-closed, never inferred from price), pre-event snapshot (including two new
  development-only, separately-versioned features, `gst_slope_v0.1`/`gst_persistence_v0.1` — no locked definition
  for either existed anywhere in the codebase before this), an earnings-specific option benchmark deliberately
  distinct from the Phase 2 panel's generic nearest-expiry-after-today IV, market-response interval formulas,
  sector/SPY relative-return controls (never called "abnormal return"/"alpha"), immutable raw-bar storage, an
  append-only forward-only event state machine, and an explicit completeness policy (missing data stays null,
  never zero).
- `gst_market_response/` (new package) — `constants.py` (24-ticker universe + six-field contract, mirrored
  verbatim from `GST_Phase2_DailyPanel.py`, unchanged), `identity.py` (event_id format mirrored from the Event
  Dossier Protocol's validator regex; BMO/AMC/INTRADAY fail-closed determination; the D1 trading-session day-count
  rule), `bars.py` (5-minute bar validation — rejects duplicate/non-monotonic/wrong-ticker bars — and
  America/New_York session-boundary extraction), `derivations.py` (every return-interval formula, null-safe by
  construction), `providers.py` (abstract `IntradayOHLCVProvider`/`EventTimingProvider` interfaces, plus a
  `YFinanceDevIntradayProvider` explicitly labeled development-only, not exchange-grade/NBBO/institutional),
  `option_chain_adapter.py` (reuses `get_nearest_post_earnings_expiry()`/`get_option_snapshot()` from
  `GST_MultiTicker_Forward_Log.py` as-is, called with the verified earnings date as anchor; adds the
  reject-on-crossed-quote, reject-on-on/before-event-expiry, and reject-on-incompatible-timestamp rules on top),
  `sector_mapping.py` + `Live Signal Engine/GST_Sector_ETF_Mapping_v0.1.json` (new locked mapping — nothing
  existed to reuse), `atomic_io.py` (write-temp-then-rename; append-only, never-truncating log writes),
  `raw_bars.py` (immutable raw-bar files + SHA-256 manifest, `verify()` for hash-mismatch detection),
  `event_record.py` (append-only JSONL event log; forward-only state-transition validation; `PARTIAL`/
  `ABSTAIN_DATA_QUALITY` are terminal by construction, so `PARTIAL` can never later become `COMPLETE`; amendment
  records that never rewrite an earlier record's bytes), `completeness.py` (the four completeness tiers, required
  vs. explicitly-optional fields enumerated once), `pipeline.py` (orchestrates the state machine from
  already-resolved field dicts — no provider I/O of its own, which is what keeps it deterministically testable),
  `completion_marker.py` + `cli.py` (nonzero exit on a failed required-data gate; reuses this project's existing
  0/1/2 PASS-equivalent/FAIL/INCONCLUSIVE exit-code convention rather than inventing a new one).
- `Live Signal Engine/GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.1.md` (new) — field-by-field reference, with the
  explicit non-advisory framing required by the spec (historical association is retrospective; prospective value
  is still under collection; this module does not establish profitability; options are a benchmark, not the only
  future instrument; no strategy is selected in v0.1; strategy selection may occur only after the first
  development earnings cycle completes).

**Reused vs. new** (full detail in the spec's "Reused components" table): earnings-date lookup, option-expiration
selection, and the ATM option-chain snapshot are reused from existing functions with documented semantic caveats
(all existing earnings-date lookups are forward-only; `pick_expiration()` in `GST_Live_Straddle_Logger.py` was
identified and deliberately NOT reused, since its DTE-floor selection rule is unrelated to event-date anchoring).
The GST z-score formula, the 24-ticker universe, and the `event_id` scheme are reused unchanged. Intraday OHLCV
retrieval, the sector-ETF mapping, `gst_slope`/`gst_persistence`, and the BMO/AMC D1 day-count rule are new — none
of them existed anywhere in the codebase before this lane.

**Tests**: `test_market_response_decomposition.py` (new, 74 checks) covers all 20 required scenarios (AMC/BMO/
weekend/holiday/half-day timing; missing-boundary-bar fail-closed; duplicate/non-monotonic/wrong-ticker bar
rejection; stock/sector/SPY interval alignment; every return formula; null-never-zero in both directions;
PARTIAL-never-becomes-COMPLETE; byte-identical raw files; non-destructive amendments; raw-file hash-mismatch
rejection; on/before-event expiration rejection including a defensive double-check independent of the reused
selector; crossed-quote rejection; incompatible-timestamp rejection; the generic Phase 2 IV is structurally
excluded from ever being imported as `earnings_implied_move`; no trading-decision/P&L field exists in the schema),
a full synthetic `REGISTERED → PRE_EVENT_CAPTURED → D1_COMPLETE → COMPLETE` end-to-end event, and 5 failure
fixtures (missing event timing, missing opening bar, invalid option expiration, partial sector data, raw-file hash
mismatch). `test_market_response_cli_gate.py` (new, 9 checks) covers the completion marker and the CLI's nonzero
exit codes (gate pass / gate fail / unregistered event → INCONCLUSIVE, never a false pass).

Full deterministic suite re-run: 13 files (11 pre-existing Phase 2/Wikipedia files + the 2 new market-response
files), all passing. **No live network call was made at any point.** The 24-ticker panel was not run. The
operational Wikipedia cache does not exist in this new worktree at all (git worktree checkout of tracked files
only) and the source worktree's cache was independently re-verified byte-identical (`29d072f2...`) before and
after this work.


## 2026-08-03 — Safety correction: live equivalence smoke test can no longer mutate operational data by default

**Why this changed.** The prior cache-hash-discrepancy reconciliation identified the exact mechanism: `test_phase2_wikipedia_equivalence.py` is a genuinely live-network test (unlike `test_phase2_wikipedia_equivalence_deterministic.py`) that never redirected `GST_Phase2_Wikipedia_Transport.CACHE_PATH`, so any accidental inclusion in a "run every test file" pass wrote real fetched data into the real operational cache. This closes that gap structurally rather than relying on remembering to exclude one filename.

**What changed:**

- Renamed `test_phase2_wikipedia_equivalence.py` → `phase2_live_smoke_wiki_equivalence.py`, off the `test_*.py` pattern, so no glob-based or `test_*` discovery convention (including this project's own regression-check loops) can ever pick it up by accident again.
- `main()` now requires `RUN_PHASE2_LIVE_WIKI_SMOKE=1` to do anything at all. Without it: zero network calls, zero access to `CACHE_PATH` (real or otherwise), and the existing three-state `PASS`/`INCONCLUSIVE`/`FAIL` contract is reused rather than inventing a fourth state — every ticker reports `INCONCLUSIVE` with an explicit "skipped, not evaluated" reason, preserving `decide_exit_code()`'s existing exit-code mapping (0/1/2).
- When explicitly enabled, `_run_live_smoke()` redirects `CACHE_PATH` to an isolated temp file for the entire run via a new `_TempCacheRedirect` context manager (unconditional restore-and-cleanup in `__exit__`, including on an exception), then independently hash-verifies the REAL operational cache is byte-identical before and after as defense in depth — a hard failure (exit 1) if that check ever disagrees, rather than a silent pass.
- Fixed a resulting breakage: `test_phase2_wikipedia_equivalence_deterministic.py`'s `test_live_smoke_verdict_exit_code_mapping` imported the old module name; updated to import `phase2_live_smoke_wiki_equivalence`.

**Tests**: `test_phase2_live_wiki_smoke_gating.py` (new, 18 assertions, zero network calls, live mode never invoked) proves: default invocation never calls `_run_live_smoke()`; default invocation makes zero network calls even if one were attempted (patched `urlopen` never reached); default invocation never reassigns `CACHE_PATH` and leaves the real cache byte-identical; `_TempCacheRedirect` genuinely isolates `CACHE_PATH` to a different, non-operational path; the redirect restores `CACHE_PATH` and deletes its temp directory both on normal exit AND when an exception is raised inside it; the real operational cache is byte-identical before and after the whole test file. Full deterministic suite (11 files) re-run: all passing, operational cache verified byte-identical before and after.

Only deterministic tests were run. Live mode was not invoked at any point while producing this correction.

## 2026-08-03 — Correction: cache-hash discrepancy reconciled (report-only, no cache/code change)

**What was flagged.** The prior report for the subchunk-recovery pass recorded the operational cache's SHA-256 as `e3ebecd2...` at Lane B preflight, then `29d072f2...` "immediately before the deterministic suite" a few steps later, without explaining the difference. This entry reconciles it.

**Finding.** Both hashes were computed identically — same absolute path (`Live Signal Engine/Phase2_Wikipedia_Cache.csv` under this repo root), same tool (`sha256sum`, which hashes raw bytes with no line-ending normalization), same algorithm. This is not a hashing-procedure or path artifact: the file's content genuinely changed between the two checkpoints, from 8,162 to 8,163 data rows (net +1).

**Root cause.** Between preflight and the "before suite" checkpoint, an initial regression-check pass mistakenly included `test_phase2_wikipedia_equivalence.py` — a live-network test (distinct from `test_phase2_wikipedia_equivalence_deterministic.py`) that never overrides `CACHE_PATH` and therefore reads/writes the real operational cache by design. It fetched fresh AAPL/AMZN Wikipedia data to compare direct-vs-chunked equivalence; AMZN came back INCONCLUSIVE (nothing written), AAPL succeeded. `write_chunk_to_cache()` first removes any existing rows for the same `(ticker, chunk_start, chunk_end)` key before appending — AAPL's existing 1-row group for chunk `(2026-08-01, 2026-08-03)` (from the earlier 24-ticker regression, watermark then at 2026-08-01) was replaced by a fresh 2-row group (`20260801`, `20260802`; watermark had since advanced to 2026-08-02), both `last_verified_utc=2026-08-03T20:35:45+00:00`, matching the file's own recorded mtime exactly. Net effect: −1 row, +2 rows = +1, fully accounted for.

**Legitimacy.** Both changed rows carry `http_status=200` and a genuine `wikimedia.org` per-article URL, written through the same production `get_ticker_wikipedia_daily()` → `validate_snapshot()` → `write_chunk_to_cache()` path used everywhere else in this module — not a bug, not corruption, not a test artifact bypassing validation. The gap was in test-run *hygiene* (a live test was run during a "confirm no regressions" pass that should have been deterministic-only) and in *reporting* (the subsequent "byte-identical before/after the deterministic suite" claim was true for that specific window but did not disclose that the cache had already changed once, earlier, for an unrelated reason).

**No correction to the subchunk-recovery mechanism, its tests, or the operational cache was needed or made.** The cache was not modified, restored, or normalized as part of producing this note — it was only inspected.

## 2026-08-03 — Phase 2: bounded closed-month Wikipedia subchunk recovery

**Why this changed.** The 2026-08-03 CTSH/GME PARTIAL regression traced to two mid-history full-month chunks returning HTTP 404 on both the first attempt and the bounded second pass, while a read-only diagnostic (`Live Signal Engine/Phase2 Failure Evidence/2026-08-03_CTSH_GME_Historical_Endpoint_PARTIAL/`) later showed the exact same requests succeeded cleanly on retry, as did every fixed 7-day subrange of each — consistent with transient/rate-limited server behavior on a per-request-shape basis, not a genuine data-availability gap. This adds a third, strictly bounded, last-resort recovery mechanism for exactly that failure pattern.

**What changed** (additive only -- no change to data selection, z-score methodology, cache acceptance rules, the earnings leg, the six locked research fields, or the locked 24-ticker universe):

- `week_aligned_subchunks()`, `attempt_closed_month_subchunk_recovery()`, `run_bounded_subchunk_recovery()` (new, `GST_Phase2_Wikipedia_Transport.py`): a fixed, calendar-aligned 7-day partition of a closed month that already failed both the first pass and the bounded second pass, one attempt per subchunk (never recursive, never bisected further), production-appropriate pacing (`SUBCHUNK_PACING_RANGE_S = (2.0, 5.0)`, matching the existing second pass), and independent per-month `SUBCHUNK_MAX_REQUESTS_PER_MONTH = 6` / `SUBCHUNK_MAX_WALL_CLOCK_S = 120.0` budgets on top of the run-level clock. Applies ONLY to closed months (`is_open_chunk()` gates it out for the open/current chunk, which remains `apply_recent_cache_fallback()`'s exclusive domain). Every subchunk response is validated through the SAME shared `validate_snapshot()` gate used everywhere else in this module (identity, duplicate dates, invalid pageviews, date-outside-range, content-hash, exact coverage through `required_data_end()` -- which structurally excludes any post-watermark observation). A subchunk that validates is cached immediately through the existing `write_chunk_to_cache()` path, keyed by its own boundaries -- never a synthesized whole-month entry, so a genuine partial recovery survives even when the overall month does not end up fully recovered. The overall recovery succeeds only when the union of successful subchunks exactly equals the full expected date set, with no duplicate/conflicting observation across subchunks; even one missing date fails the whole attempt closed.
- `_wiki_source_provenance()` (`GST_Phase2_DailyPanel.py`): additively recognizes a new `source="subchunk_salvage"` chunk-result tag, producing `wiki_source_mode="subchunk_salvage_only"` when it is the sole contributor (falls into the existing `"mixed"` bucket alongside any other source otherwise, unchanged logic).
- `GST_Phase2_DailyPanel.py` `main()`: wires `run_bounded_subchunk_recovery()` in as a third stage, running after the bounded second pass AND the recent-cache fallback, on whatever remains failed. Two new additive `COLUMN_ORDER` fields, `wiki_subchunk_recovery_attempted` / `wiki_subchunk_recovery_provenance_json`, record the full per-subchunk provenance (original failed interval, subchunk boundaries, response status, elapsed time, content hashes, retrieval timestamps, expected/observed date counts, recovery status, and budgets consumed) on every row where this mechanism was invoked, whether or not it ultimately succeeded -- `None`/`null` on every row where it never ran.

**Tests**: `test_phase2_wiki_subchunk_recovery.py` (new) -- complete recovery, one missing date, one failed subchunk, duplicate/conflicting dates across subchunks, invalid identity/hash detection, invalid pageview values, post-watermark observation rejection, open-month non-use, request-count exhaustion, wall-clock-budget exhaustion, 429/404 behavior, no recursive descent, correct cache writes (including no cache write on incomplete union), provenance/source-mode correctness, and a final byte-identical check on the real operational cache. Full deterministic Phase 2 suite (10 files) re-run in full: all passing, operational cache verified byte-identical before and after.

Only deterministic tests were run. No live network access, no operational-cache mutation, and the 24-ticker panel itself was not rerun.

## 2026-08-02 — Phase 2: preserve wiki source provenance end-to-end, fix article-identity gap in cache-union

**Why this changed.** The cache-union implementation above (fa172a1) computed detailed, per-chunk provenance (`attempt_cache_union_reconstruction()`'s return value) but it never reached the finalized panel row: `process_ticker()` logged only `source`/`status` per chunk and discarded the rest; `wiki_pending` (the struct carried into the second pass) didn't retain `chunk_results` at all; and `_finalize_wiki_row()` unconditionally wrote `wiki_source_mode="fresh"` regardless of what actually happened. A ticker fully recovered via cache-union reconstruction, or via a mix of cache/fetch/union, would show up in the panel output indistinguishable from a genuinely fresh network fetch.

**What changed** (additive only -- no change to data selection, z-score methodology, cache acceptance rules, retry behavior, budgets, or the six locked research fields):

- `_wiki_source_provenance()` (new, `GST_Phase2_DailyPanel.py`): derives final source provenance from the chunks that **actually contributed** rows (`status="ok"` and `source` in `{cache, fetch, cache_union_reconstruction}`) -- never hardcoded. Produces `wiki_source_mode` (`fresh_only` / `exact_cache_only` / `cache_union_only` / `mixed`, or `None` if nothing contributed -- never invented), `wiki_cache_union_used`, `wiki_cache_union_chunk_count`, and two deterministic (`sort_keys=True`, over already-sorted inputs) JSON fields: `wiki_source_components_json` and `wiki_cache_union_provenance_json` (contributing chunk keys, content hashes, and retrieval timestamps for every union-recovered chunk).
- `_finalize_wiki_row()` now takes a **required** `chunk_results` parameter (no default -- matches the existing `watermark_date` fail-closed pattern) and calls `_wiki_source_provenance()` instead of hardcoding `"fresh"`.
- `wiki_pending` now retains first-pass `chunk_results` (previously discarded), and `main()`'s second-pass loop merges them with a normalized view of the ticker's second-pass results (`source="fetch"` added -- second pass is always a live retry, never a cache/union hit) before finalizing, so provenance survives a chunk being queued, retried, and recovered.
- The existing `recent_last_known_good` fallback's own provenance (`wiki_status`, `wiki_source_mode`, and its other fields) is completely untouched -- still applied via the same `row.update(fallback_info["provenance"])` override, unchanged. Purely additively, `"recent_last_known_good"` is merged into `wiki_source_components_json` afterward, so a ticker recovered by the fallback still shows any OTHER chunks that contributed normally, without ever overriding the fallback's own authoritative labels.
- Fixed a related identity gap in `attempt_cache_union_reconstruction()`'s per-group hash-reverification: the full-group re-lookup used for recomputing a candidate group's stored hash filtered on `(ticker, chunk_start, chunk_end)` but **not** `configured_article_title` -- two different article mappings for the same ticker sharing an identical chunk-boundary key could have their rows silently mixed together during hash recomputation. Now filtered on all four fields.
- 9 required deterministic scenarios / 35 assertions added (`test_phase2_wiki_source_provenance.py`): union-only never labeled fresh, provenance survives CSV/DataFrame round-trip, mixed-source labeling with all components present, provenance survives a later successful second pass, `recent_last_known_good` unchanged, two genuinely separate cached chunk groups jointly reconstructing one interval with both represented in provenance, wall-clock independence with nondegenerate non-null z-scores, exact-snapshot vs. union-snapshot producing equal non-null z-scores (not merely equal daily rows), and differing article titles sharing a ticker/chunk boundary provably unable to interfere.
- `test_phase2_wiki_zscore_anchor.py` updated for `_finalize_wiki_row()`'s new required `chunk_results` parameter (mechanical signature update only, no behavioral change to that file's own assertions).

**Caught and fixed during test development, before this commit:** an early version of the new second-pass test called the real `run_bounded_second_pass()` with a fetch stub that returned a successful result, which -- exactly as the real code is supposed to -- triggered `write_chunk_to_cache()` against the real, global `wiki_transport.CACHE_PATH`, appending 30 fabricated rows to the actual operational `Live Signal Engine/Phase2_Wikipedia_Cache.csv`. Caught immediately via a before/after cache-hash mismatch; the 30 synthetic rows were identified precisely (a clean append at the file's tail, confirmed by the exact row-count delta -- no pre-existing row was overwritten) and removed, restoring the cache to its exact prior SHA-256. The test itself was then fixed to redirect `CACHE_PATH` to a temp file for its duration (the same pattern already used elsewhere in this suite), and the full suite was re-run to reconfirm a byte-identical cache hash before and after.

**Full deterministic suite: 291 assertions passing** (up from 256), across all 9 test files. No live-network test, no 24-ticker panel run in this pass. Operational cache confirmed byte-identical before/after the final suite run.

## 2026-08-02 — Phase 2: fix pull_start watermark propagation, add closed-interval cache-union reconstruction

**Why this changed.** Two follow-ups to the same-day anchor fix above, found while re-verifying the watermark's propagation end-to-end.

**1. `pull_start` was still wall-clock-derived.** `process_ticker()` computed `pull_start = anchor_date - timedelta(days=PULL_LOOKBACK_DAYS)` using `anchor_date = run_ts.date()` (wall-clock), not `watermark_date` -- the same class of bug just fixed for the z-score anchor itself. Since the effective data end is truncated to the watermark regardless, a wall-clock-derived `pull_start` silently shortens the effective lookback by exactly the watermark's lag whenever it lags wall-clock time. Fix: `pull_start = watermark_date - timedelta(days=PULL_LOOKBACK_DAYS)`. The request horizon/end-date passed to the transport (`anchor_date`, still wall-clock) is deliberately unchanged -- `get_ticker_wikipedia_daily()`/`required_data_end()` already truncate any chunk beyond the watermark, so this is harmless and out of scope. 4 required lag scenarios (0/1/2/3 days) added, 23 assertions total, in `test_phase2_wiki_pull_start.py` -- proves `pull_start` is fixed relative to `watermark_date` regardless of wall-clock date, the request horizon still varies with wall-clock (confirming it was deliberately left alone), a post-watermark observation has zero effect on the resulting z-score, and a missing/errored watermark still fails closed (zero network calls attempted).

**2. Closed-historical-interval cache-union reconstruction (new capability, not a bug fix).** The 2026-08-02 endpoint-failure diagnostis found that most of the 8 "genuine failure" tickers' failed chunks (see `COMPOSITE_SNAPSHOT_DESIGN_PROPOSAL_NOT_IMPLEMENTED.md`) were re-fetching calendar dates already fully, validly cached under a *different* rolling-window chunk-boundary key -- `cached_daily_rows_for_chunk()`/`validated_cache_hit()` key on an exact `(chunk_start, chunk_end)` match, so this coverage was invisible to the lookup that mattered. Implemented the proposal exactly as designed, conservatively:

- `attempt_cache_union_reconstruction()` (new, `GST_Phase2_Wikipedia_Transport.py`): on an exact-key cache miss for a **closed historical interval only** (never the open/current chunk -- gated by `is_open_chunk()` at the call site, live-first + the existing `recent_last_known_good` fallback there is completely unchanged), attempts a day-level union of already-validated cache rows for the same ticker + configured article, tried *before* any network request.
- Fails closed unless: every calendar date in the requested interval is present (no partial-coverage union ever accepted); every contributing row has `http_status == 200`, a genuinely nonnegative-integer `pageviews` value, and belongs to a chunk-group whose stored `content_hash` matches a hash recomputed from that group's own full row set (the same check `verify_cache_integrity()` runs, applied per candidate group -- a tampered/inconsistent group contributes nothing); two cached rows disagreeing on the same date's `pageviews` rejects the *whole* reconstruction (never averaged, never picked); every contributing date is independently re-checked against the watermark.
- Never writes the synthetic union back to the cache as though it were a real network response -- read-only.
- Explicit `cache_union_reconstruction` provenance recorded per recovered chunk: contributing `(chunk_start, chunk_end)` keys, contributing `content_hash` values, contributing `last_verified_utc` timestamps, reconstruction timestamp.
- 8 required scenarios / 19 assertions added in `test_phase2_wiki_cache_union.py`: complete-union acceptance, one-date-missing rejection, conflicting-value rejection, identity/hash rejection (three sub-cases: tampered hash, wrong article, non-200), watermark exclusion, current/open-month non-use (proven even when full day-level coverage exists under another key), zero-network-call recovery, and byte-identical daily values vs. an exact-boundary snapshot for the same interval.

**Full deterministic suite: 256 assertions passing** (up from 214), across all 8 test files. No live-network test, no 24-ticker panel run in this pass. Operational cache confirmed byte-identical before/after the full suite run.

## 2026-08-02 — Phase 2: anchor the wiki z-score on the measured watermark, not wall-clock time

**Why this changed.** A bounded 24-ticker regression on 2026-08-02 (commit
`50c4916`) came back PARTIAL with `wiki_zscore` 0/24, even though the
watermark mechanism (`e2d7d80`) and the completion gate (`50c4916`) both
worked correctly this run (watermark `status=ok`, `lag_days=1`; every row
`earnings_status=ok`). Root cause, confirmed via each affected row's
`wiki_note`: `_finalize_wiki_row()` in `GST_Phase2_DailyPanel.py` anchored
`compute_zscore_at_anchor()` on `pd.Timestamp(run_ts.date())` — the
script's real wall-clock run date — instead of the measured watermark
date. Since Wikipedia data is genuinely truncated at the watermark
(`required_data_end = min(chunk_end, watermark)`), anchoring one day past
it manufactured a 7-day gap to the nearest available week for 16/24
tickers, one day past the existing 6-day alignment tolerance in
`compute_zscore_at_anchor()` (unchanged, not touched by this fix).
Evidence preserved in `Live Signal Engine/Phase2 Failure Evidence/
2026-08-02_WatermarkAnchor_And_Endpoint_PARTIAL/`.

**What changed** (the anchor computation only; chunk boundaries, budgets,
retry counts, source hierarchy, the six locked research fields, and the
core z-score formula in `GST_FixedWindow_PerEvent_Canonical.py` are all
untouched):

- `_finalize_wiki_row(row, article, daily_rows, watermark_date)` — the
  `run_ts: datetime` parameter is replaced by a required `watermark_date:
  date` parameter (no default; matches this project's established
  "no implicit today" pattern). The function now raises `ValueError` if
  `watermark_date` is `None` — fail-closed, no wall-clock fallback.
- Added a defense-in-depth filter inside `_finalize_wiki_row()`: any
  `daily_rows` entry dated after `watermark_date` is excluded before the
  weekly series is assembled, independent of whatever upstream chunk
  truncation already did.
- Two new provenance columns: `wiki_zscore_anchor_date` (always equal to
  the watermark date on a finalized row) and `wiki_zscore_anchor_source`
  (currently always `"measured_watermark"`).
- All three call sites (`process_ticker()`'s first pass, and both
  finalization branches in `main()`'s second-pass/fallback loop) updated
  to pass `watermark_info["watermark_date"]` instead of a wall-clock
  timestamp.
- Added `test_phase2_wiki_zscore_anchor.py`: 8 required scenarios / 14
  assertions, covering the exact within-tolerance/over-tolerance
  boundary, wall-clock independence, post-watermark exclusion, and
  fail-closed behavior on a missing/errored watermark.
- Full deterministic suite re-run after this change: **214 assertions**
  passing across `test_phase2_wikipedia_transport.py` (79),
  `test_phase2_dailypanel_gate.py` (24),
  `test_phase2_wikipedia_recent_cache_fallback.py` (26),
  `test_phase2_wikipedia_watermark.py` (48),
  `test_phase2_wikipedia_equivalence_deterministic.py` (23), and the new
  `test_phase2_wiki_zscore_anchor.py` (14).

**Separately investigated, not fixed:** the same regression's 8/24
"genuine endpoint failure" tickers (ADBE, AMZN, BKR, CTSH, GME, LDOS,
NCLH, TSLA) were diagnosed read-only. No narrow implementation bug was
found — the existing `recent_last_known_good` fallback is correctly
scoped to the open month only and correctly does not apply to the
closed-month chunks that failed (October 2025, January 2026, July 2026),
and the open-month failures for CTSH/GME/NCLH have zero cached history to
fall back to. A forward-looking design proposal for reconstructing a
complete chunk from a day-level union of overlapping cached fetches
(rather than requiring an exact chunk-boundary cache key match) is
documented, **not implemented**, in
`COMPOSITE_SNAPSHOT_DESIGN_PROPOSAL_NOT_IMPLEMENTED.md` alongside the
evidence. No fallback logic was changed in this pass.

## 2026-08-01 — Phase 2: align completion gate with six-field contract

**Why this changed.** GitHub review of the watermark commits (`7fa1762`,
`e2d7d80`) found a real logic bug in the completion gate. The locked six
research fields are `gst_zscore`, `wiki_zscore`, `implied_volatility`,
`realized_vol`, `price`, `volume`; `days_to_nearest_earnings` is contextual
metadata, not one of them. `all_six_fields_clean` had drifted to require
all six fields **and** `days_to_nearest_earnings` non-null, and
`is_run_complete()` required `all_six_fields_clean=True` for every row.
Under that logic, the successful `46aec15` baseline -- which had all six
research fields 24/24 but legitimately found no upcoming earnings date for
four tickers (`earnings_status="ok"`, `days_to_nearest_earnings=None`) --
would have been incorrectly classified PARTIAL. A genuinely successful
"no earnings found" result is not a failure and must not block COMPLETE.

**What changed** (completion-gate logic only; watermark algorithm,
Wikipedia transport, z-score formulas, ticker universe, retry policy,
budgets, option selection, and historical data are all untouched):

- `all_six_fields_clean` (both computation sites: `process_ticker()` and
  the post-second-pass/fallback finalization loop in `main()`) now covers
  **only** the six locked research fields.
- `is_run_complete()` separately and independently requires
  `earnings_status == "ok"` for every row -- fail-closed: `"error"` or
  `"timeout"` still block COMPLETE, but a null `days_to_nearest_earnings`
  alongside `earnings_status="ok"` does not. No earnings date is ever
  fabricated.
- `write_completion_marker()` gains two additive observability fields,
  `earnings_lookup_ok_count` and `days_to_nearest_earnings_nonnull_count`,
  so a successful-null-earnings run is visibly distinguishable from an
  earnings-lookup failure. No existing marker field was removed or renamed.
- Corrected the RUN SUMMARY log line, which previously read "Clean (all 6
  fields + earnings)" -- now "Clean (six locked research fields only)"
  with a separate "Earnings lookup ok (date may still be null)" count.
- Added 7 new deterministic assertions to
  `test_phase2_dailypanel_gate.py` (`earnings-a` through `earnings-d`,
  `marker-e` x3) proving: six fields clean + `earnings_status="ok"` +
  null date is COMPLETE-eligible; `earnings_status="error"` or `"timeout"`
  forces PARTIAL even with six clean fields; a missing core field still
  forces PARTIAL independent of earnings status; and the new marker
  counters correctly distinguish a successful-null-earnings row from a
  lookup-failure row.
- Full deterministic suite re-run after this change: 200 assertions
  passing across `test_phase2_wikipedia_transport.py` (79),
  `test_phase2_dailypanel_gate.py` (24),
  `test_phase2_wikipedia_recent_cache_fallback.py` (26),
  `test_phase2_wikipedia_watermark.py` (48), and
  `test_phase2_wikipedia_equivalence_deterministic.py` (23). No live
  network test was run in this pass; the 24-ticker panel was not run.

## 2026-08-01 — Phase 2: measure and enforce a Wikimedia publication watermark

**Why this changed.** The 2026-08-01 24-ticker regression (the PR's
operational merge gate) came back PARTIAL: `wiki_zscore` 0/24. Root cause,
independently confirmed via direct probe of both the per-article and the
site-wide aggregate Wikipedia endpoints: this run landed ~3.5 hours into
August 1, immediately after July closed, and Wikipedia had not yet
published July 31 for any article. The fixed "coverage through `today-1`"
assumption -- previously baked into `effective_open_chunk_data_end()` and
applied only to the calendar-open month -- was proven false on a real,
measured day, and it never protected CLOSED months at all (a closed
month's own last day can be just as unpublished). Evidence preserved in
`Live Signal Engine/Phase2 Failure Evidence/2026-08-01_Wikipedia_SourceWatermark_Lag2/`.

**Phase B feasibility probe** (read-only, before any implementation):
tested the site-wide aggregate pageviews endpoint
(`.../pageviews/aggregate/en.wikipedia.org/all-access/user/daily/{start}/{end}`,
requiring `YYYYMMDD` + a trailing `"00"` hour component -- a different
format than the per-article endpoint) for July 31 and July 30
individually. Result: clean, non-flaky, reproducible --  July 30 returned
HTTP 200 consistently, July 31 returned HTTP 404 consistently (confirmed
twice, 2 seconds apart), and a 3-day range query correctly omitted the
unavailable trailing date rather than erroring the whole range. This
endpoint does NOT exhibit the per-article/per-request-shape flakiness
documented elsewhere in this investigation, making it a reliable
foundation for a watermark. Evidence:
`aggregate_endpoint_probe_evidence.csv`.

**What changed** (none of it touches the Wikipedia z-score formula, GST
methodology, the ticker universe, any option/price/volume field, the six
required research-field meanings, historical datasets, or existing
PARTIAL evidence):

- **`resolve_wiki_data_watermark()`** (new): resolves the SINGLE run-level
  Wikipedia data watermark exactly once, at run start, before any ticker
  is processed. Probes candidates `anchor_date-1` through `anchor_date-3`
  (`MAX_ACCEPTABLE_WIKI_LAG_DAYS`, locked) newest-to-oldest against the
  aggregate endpoint. A 404 gets exactly one bounded confirmation re-probe
  before moving to the next-older candidate. A 429 honors a bounded
  `Retry-After` and retries the SAME candidate (never walks back on a rate
  limit). Any other ambiguous outcome (exception, non-404/429 HTTP status,
  malformed response) FAILS THE WATERMARK CLOSED immediately -- never
  interpreted as "unpublished". No watermark within the lag budget leaves
  the run's Wikipedia leg entirely unresolved (PARTIAL), never guessed.
- **`required_data_end(chunk_end, watermark) = min(chunk_end, watermark)`**
  replaces `effective_open_chunk_data_end()` and is now applied UNIFORMLY
  to every chunk, open or closed alike -- the exact fix for the incident,
  since the old code only ever capped the open month.
- **`today` removed from the transport module's public API entirely**,
  replaced by `watermark` throughout: `validate_snapshot()`,
  `validated_cache_hit()`, `get_ticker_wikipedia_daily()`,
  `run_bounded_second_pass()` (now a required parameter, no silent
  default), `evaluate_recent_cache_fallback()`/`apply_recent_cache_fallback()`
  (the fallback's "current chunk" gate is now `is_open_chunk(chunk_start,
  chunk_end, watermark)` -- the watermark, not the calendar, defines the
  frontier). A fresh fetch now requests ONLY `chunk_start..required_data_end`
  -- never a date beyond the measured watermark, and never the chunk's
  full nominal end.
- **Rollover behavior now generalizes correctly**: a cache snapshot valid
  against an earlier, smaller watermark is rejected (`incomplete_coverage`)
  and refetched once the watermark advances -- for BOTH open and closed
  chunks, closing the exact gap that caused the 2026-08-01 PARTIAL (23 of
  24 tickers' cached July snapshots, valid through July 30, will now be
  accepted directly once the watermark reaches July 30, and correctly
  refreshed once it reaches July 31).
- **7 new additive, run-level provenance columns** (identical across every
  row of a run, never recomputed per ticker): `wiki_data_watermark_date`,
  `wiki_data_lag_days`, `wiki_watermark_status`,
  `wiki_watermark_retrieved_at_utc`, `wiki_watermark_source_url`,
  `wiki_watermark_http_status`, `wiki_required_data_end`. The same
  metadata is added to the completion marker
  (`wiki_data_watermark` object).
- **`is_run_complete()`** now requires `watermark_status == "ok"` in
  addition to its existing checks -- a run cannot be COMPLETE without a
  valid measured watermark, and a lag exceeding `MAX_ACCEPTABLE_WIKI_LAG_DAYS`
  structurally can never reach `watermark_status == "ok"` in the first
  place, so it can never produce COMPLETE either.
- `GST_Phase2_DailyPanel.py`'s `main()` resolves the watermark once,
  before the ticker loop; if resolution fails, every ticker's wiki leg is
  marked `incomplete_watermark_unavailable` and skipped entirely (fail
  closed, no network request, no guess) while the other five fields still
  process normally.

**Tests**: 5 files updated for the `today` -> `watermark` API change (all
prior tests re-verified passing under the new semantics, several fixed
where their setup's premise no longer applied under the unified
watermark-driven model -- e.g. a cache exactly satisfying the current
watermark is now legitimately reused rather than always refetched). New
coverage: `test_phase2_wikipedia_watermark.py` (48 assertions, tests 1-12:
lag 1/2/3 resolution, no-data-within-max-lag, 429/Retry-After, fail-closed
on ambiguous errors, request truncated exactly to the watermark, no
request for chunks entirely beyond it, July-rollover cache valid/rejected
across a watermark advance, exact coverage enforcement, identical
provenance across rows); `test_phase2_wikipedia_equivalence_deterministic.py`
gains a watermark-truncation test (13: a manually-truncated frozen fixture
exactly matches the pipeline's own truncation); `test_phase2_dailypanel_gate.py`
gains tests 15/16 (no COMPLETE without a valid watermark; lag > max cannot
produce COMPLETE). Total deterministic suite: 193 assertions across 5
files, all passing; operational cache confirmed byte-identical before and
after.

**Live diagnostic** (the only live check run before this commit, per
instruction -- no full panel): `diagnose_wiki_watermark_only.py` exercises
only `resolve_wiki_data_watermark()` against the real aggregate endpoint.
Result at commit time: `status=ok`, `watermark_date=2026-07-31`,
`lag_days=1` -- Wikipedia's publication lag had already recovered to 1 day
by the time of this commit (confirming the earlier 2-day lag was
genuinely transient, exactly as classified throughout this investigation).

**Remaining limitations, disclosed:** the watermark is resolved from the
SITE-WIDE aggregate endpoint, which is a proxy for per-article
availability, not a per-article guarantee -- an individual article could
theoretically still lag behind the aggregate signal (not observed in this
investigation). `MAX_ACCEPTABLE_WIKI_LAG_DAYS=3` is a locked policy
constant, not derived; a genuinely longer Wikipedia-side outage would
still correctly produce PARTIAL rather than an incorrect COMPLETE, but
requires a deliberate policy change (not an automatic escalation) to
extend. No new 24-ticker regression has been run under this watermark
implementation -- per instruction, none was authorized this pass.

## 2026-07-31 — Phase 2 follow-up: close test-isolation and edge-case validation gaps

Four further review findings closed on top of the prior corrective commit:

1. **Real no-observations-yet orchestration.** The real Wikipedia worker
   returns `status="empty"` (not `"ok"`) for a zero-item HTTP-200 response
   -- so the prior fix (which only classified `no_observations_expected_yet`
   AFTER a fetch, and only when `status=="ok"`) could still queue the very
   first day of a new open month as a genuine failure forever, since that
   day's request will always come back "empty". Fixed prospectively:
   `get_ticker_wikipedia_daily()` now checks, BEFORE making any request for
   an open chunk, whether `effective_data_end < chunk_start` (nothing in
   range could possibly be published yet); if so, no network call is made,
   `chunk_results` gets `source="not_requested"` /
   `status="no_observations_expected_yet"` with zero network/sleep time,
   nothing is cached, and no failed chunk is produced. Verified with an
   orchestration-level test using a `fetch_fn` that raises if called at
   all, plus a run-completeness test showing the run can still be COMPLETE
   using the preceding available dates.
2. **Deterministic equivalence test isolated from the operational cache.**
   `test_phase2_wikipedia_equivalence_deterministic.py`'s fixture-backed
   chunks still called the real `write_chunk_to_cache()` against the
   module-global `CACHE_PATH` -- using the real ticker symbols AAPL/AMZN,
   an unredirected run could pollute the actual operational
   `Phase2_Wikipedia_Cache.csv`. Fixed: `CACHE_PATH` is now redirected to a
   temporary file for the test's duration, restored in `finally`, and the
   run explicitly verifies the operational cache is byte-identical before
   and after (or confirms none was created if it didn't exist). No
   deterministic test may mutate operational data.
3. **Unambiguous live-smoke-test exit codes.** `test_phase2_wikipedia_equivalence.py`
   (the optional live diagnostic) now exits 0 only if every tested ticker
   PASSes, 1 if any ticker FAILs, 2 if none FAIL but at least one is
   INCONCLUSIVE -- extracted into a pure `decide_exit_code()` function,
   directly unit-tested with zero network calls. Final PASS/INCONCLUSIVE/
   FAIL counts are printed. Explicitly documented as an optional live
   diagnostic, not a deterministic CI gate.
4. **Genuinely integral pageviews.** `validate_snapshot()` used
   `int(value)`, which silently truncates `1.5` to `1` and silently
   accepts `True` as `1`. New `_is_valid_nonnegative_integer_pageviews()`
   accepts real integers and integer-valued numeric representations (`5.0`,
   `"5"`, `"5.0"`), and rejects fractional values, NaN, +/-infinity,
   booleans, and negatives outright -- never silently coerced. Tested for
   every accepted and rejected case.

None of this touches request behavior, retries, budgets, chunk boundaries,
fallback rules, z-score methodology, field definitions, ticker universe,
or completeness policy. Full existing deterministic suite (133 assertions
across 4 files) passes; operational cache confirmed byte-identical before
and after the full suite run; no orphan process from any test (two
unrelated `llm_pull.py` processes observed on the machine were
independently confirmed, by command line and parent PID, to belong to a
different script entirely).

## 2026-07-31 — Phase 2 corrective commit: cache completeness, identity, equivalence, and deadline gates

Following a GitHub review of the two prior commits, five correctness gaps
were closed. None of it touches request behavior, retries, budgets, chunk
boundaries, fallback rules, z-score methodology, field definitions, ticker
universe, or completeness policy -- confirmed by the full existing
deterministic suite passing unchanged, plus new tests for each fix.

1. **Shared validation for every fresh response and every cache hit.**
   New `validate_snapshot()` is now the SINGLE gate used before (a) writing
   a fresh HTTP-200 response to cache, (b) treating a fresh response as
   successful, (c) reusing any closed-month cache entry (via new
   `validated_cache_hit()`), and (d) accepting the open-month
   RECENT_LAST_KNOWN_GOOD fallback (`evaluate_recent_cache_fallback()` now
   delegates to it instead of duplicating checks). Enforces: configured
   ticker/article identity, one content hash per snapshot with successful
   recomputation, no duplicate dates, parseable dates, non-negative integer
   pageviews, no dates outside the requested range, and EXACT expected
   date coverage (closed chunk: every date through chunk_end; open chunk:
   every date through `min(chunk_end, today-1)`). A nonempty HTTP 200 with
   missing required dates is classified `incomplete_coverage`, never
   cached, never treated as success, and enters the bounded second pass
   like any other failure -- no zero-filling, ever. If today is the very
   start of a new open month (no date could legitimately be published
   yet), an empty response is explicitly classified
   `no_observations_expected_yet`, not fabricated and not an error.
   **Rollover case fixed and tested**: a month fetched while still open
   (e.g. July 31, covering only through July 30) is correctly rejected as
   `incomplete_coverage` once that month closes and requires its own final
   day too -- it is never silently reused as a complete closed month; the
   orchestration falls through to a fresh fetch instead. `verify_cache_integrity()`
   -- previously exercised only by tests, never called from production --
   is now also invoked once per `get_ticker_wikipedia_daily()` call as a
   whole-cache sanity pass, on top of `validate_snapshot()`'s own per-read
   hash re-verification, so schema-valid-but-corrupted cache content can
   no longer bypass validation.
2. **Split the scientific-equivalence gate.** The prior single test
   checked only overlapping values (so it could pass even with different
   date sets between the two routes) and treated `probe_inconclusive` as
   acceptable -- not equivalence. Now two separate files:
   - `test_phase2_wikipedia_equivalence_deterministic.py` (Section A,
     mandatory): frozen, provenance-documented fixtures for AAPL and AMZN
     (`Live Signal Engine/Phase2_Wikipedia_Equivalence_Fixtures/`, captured
     once from the real direct-response route with exact dates, values,
     retrieval timestamp, article identity, source URL, and content hash
     recorded and self-verified). Requires EXACT date-set equality (not
     overlap), exact value equality for every date, and z-score match
     within 1e-9. No live-network dependency at test-run time. No
     unavailable/inconclusive outcome is possible -- this test only ever
     PASSES or FAILS.
   - `test_phase2_wikipedia_equivalence.py` (Section B, optional,
     observational): live smoke test against the real direct route, now
     reporting one of exactly three verdicts per ticker -- PASS (identical
     date sets, exact values, z-score within tolerance), INCONCLUSIVE
     (source unavailable or date sets differ -- never counted as PASS,
     regardless of how an independent re-probe classifies the gap), or
     FAIL (a true value mismatch on a date both routes returned complete
     data for). Exit code reflects only true FAILUREs; INCONCLUSIVE never
     blocks anything. Explicitly documented as not substituting for
     Section A.
3. **Cache-identity honesty.** The production cache-write path has never
   independently resolved or verified a canonical article title or
   Wikipedia page ID -- no identity registry exists for the 24-ticker
   universe, and `canonical_title`/`page_id` are always written blank.
   Prior docstring wording that implied stronger verification was
   happening has been corrected: `evaluate_recent_cache_fallback()` now
   states plainly that only ticker + configured article title are actually
   enforced (via `validate_snapshot()`), and that `canonical_title`/
   `page_id` are optional, best-effort checks that only fire if a caller
   explicitly supplies them AND a stored value happens to be non-blank
   (which production never populates today). The schema columns remain,
   for a future registry, but nothing claims they're checked when they
   aren't.
4. **Genuinely bounded time budget.** `run_bounded_second_pass()`
   previously checked remaining budget only BEFORE the jitter/Retry-After
   wait, then could launch a full-`chunk_timeout_s` request regardless of
   how little budget the wait itself had consumed. Now: remaining budget
   is recomputed AFTER any wait; a request is never launched once usable
   budget (<1s) is gone; the subprocess timeout passed to `fetch_fn` is
   capped to whatever budget actually remains, never the full
   `chunk_timeout_s`. The same discipline now applies BETWEEN first-pass
   chunks too: `get_ticker_wikipedia_daily()` accepts an optional
   `remaining_budget_s`, and `GST_Phase2_DailyPanel.py`'s ticker loop
   computes and passes the actual remaining total-run budget before each
   ticker's Wikipedia leg starts, so one late ticker's first pass cannot
   materially eat into the deadline meant for the tickers after it.
   Verified with deterministic mock-based tests (budget capping and
   exhaustion, both between second-pass items and between first-pass
   chunks) AND one real-subprocess test (a genuinely-hanging worker under
   a tiny real budget, proving the capped value -- not just any timeout
   value -- actually bounds execution end-to-end, with no orphan process
   left behind).
5. **Corrected cache-persistence wording.** `Phase2_Wikipedia_Cache.csv`
   was described as "repository-committed" while actually being untracked
   and deliberately excluded from both prior commits. Corrected: it is
   persistent ACROSS LOCAL RUNS on the same machine (atomic writes,
   accumulates over time), not currently repository-committed; a future
   unattended workflow (e.g. GitHub Actions) must explicitly persist it
   itself; the first cache intended for repository commit is the one
   produced by a validated COMPLETE 24/24 regression, reserved for
   Commit 3; automation is not ready until persistence on a clean runner
   is actually verified, not merely designed for. The volatile
   partial-run cache accumulated locally during this branch's testing is
   still not committed by this corrective commit either.

**Tests**: full existing 26-test deterministic suite (13 transport + 2
completeness-gate + 11 fallback) still passes unchanged after every fix
above, plus new coverage: 1 rollover-case test, 1
no-observations-expected-yet test, 2 tiny-budget tests (mock-based, second
pass and first pass), 1 real-subprocess tiny-budget test (proves no
overshoot, no orphan process), and the 2-ticker deterministic
scientific-equivalence test (Section A). Total: 33 assertions-worth of new
coverage across `test_phase2_wikipedia_transport.py`, plus 3 existing
fallback-test assertions updated to match `validate_snapshot()`'s
consolidated rejection-reason categories (no behavior change, only
matching the now-shared error-category names).

**Not run as part of this commit's test gate** (by instruction): another
24-ticker panel, or anything depending on current Wikipedia availability
(Section B, the live smoke test, is optional/observational and was not
executed as a precondition for this commit).

## 2026-07-31 — Phase 2 Wikipedia transport rewrite: deterministic chunking, persistent cache, bounded retry, process isolation, recent-cache fallback

**Why this changed.** The 2026-07-30 run-3 safeguards (below) bounded the
Wikipedia leg per-ticker but did not fix its underlying transport. A
subsequent investigation (preserved in `Live Signal Engine/Phase2 Failure
Evidence/2026-07-30_AMZN_Wikipedia_180s/`) found AMZN repeatedly timing out
under the old recursive-bisection design. Direct evidence: real network
time across an entire failed 180s attempt was under 3 seconds; the rest was
the old code's own mandatory 10s+20s+30s=60s retry-wait schedule, paid once
per HTTP 404 encountered, with no caching, so successful sub-ranges were
re-fetched from scratch on every run. A separate deterministic test also
proved the existing daemon-thread timeout wrapper (`run_bounded()`) returns
control to the caller while the timed-out call keeps running in the
background -- "fail-closed" described the orchestration's exit, not a
guarantee the underlying worker actually stopped.

**What changed** (new module `GST_Phase2_Wikipedia_Transport.py`, isolated
from the shared `GST_Wikipedia_Pageviews_Pull.py` used elsewhere --
confirmed unmodified). None of it touches the Wikipedia z-score formula,
any of the six locked scientific field definitions, the 24-ticker universe,
GST collection, option selection, implied volatility, realized volatility,
price, volume, or earnings-date methodology -- confirmed by diff review and
by a dedicated scientific-equivalence test (below):

- **Deterministic calendar-month chunking** (`calendar_month_chunks()`)
  replacing recursive, data-dependent bisection. The exact requested
  start/end dates are preserved; interior chunks run full calendar months.
  Deterministic boundaries make chunks reliably cacheable, unlike
  recursively-computed bisection midpoints.
- **Persistent, repository-committed, human-auditable CSV cache**
  (`Live Signal Engine/Phase2_Wikipedia_Cache.csv`, 14 columns: ticker,
  configured/canonical article title, page ID, chunk bounds, date,
  pageviews, source URL, HTTP status, first-retrieved/last-verified UTC
  timestamps, schema version, content hash). Closed months are cached and
  reused; the open/current month is always refreshed. Atomic writes
  (temp file + `os.replace`). HTTP 404 is never cached as a legitimate
  zero-view period; missing dates stay explicitly missing, never
  zero-filled. Cache corruption (missing columns, schema mismatch, hash
  mismatch) is detected and treated as a source failure, never silently
  coerced.
- **Bounded second-pass retry queue**: one attempt per chunk during normal
  processing; failures queue instead of sleeping inline; after all 24
  tickers' first passes finish, each failed chunk gets exactly one bounded
  retry with short jitter (2-5s) for ordinary failures, honoring a real
  `Retry-After` header (capped at 30s) for 429s. No recursive splitting of
  a still-failing chunk. Explicitly NOT the old 10s+20s+30s schedule.
- **Genuinely killable subprocess isolation** for the Wikipedia leg
  (`run_process_bounded()`, Windows-safe `multiprocessing` spawn context):
  on timeout, terminate() then kill() if needed, then join() to actually
  reap the child before the parent continues. Proven by a deterministic
  test that spawns a real, deliberately-hanging worker and verifies via
  `os.kill(pid, 0)` that no process with that PID survives. **Scope
  disclosure**: this isolation applies to the Wikipedia leg only -- GST,
  earnings, price-history, and IV still use the older daemon-thread
  `run_bounded()` wrapper, which does not guarantee a timed-out call
  actually stops. Converting every leg would be a substantially larger
  rewrite than this pass covers.
- **Run-level fail-closed completeness**: a failed/isolated ticker no
  longer discards other tickers' rows. `is_run_complete()` (pulled out as
  a directly unit-tested pure function) requires the loop itself reported
  COMPLETE, exactly the expected unique ticker count, every row's six
  required fields complete, and every timestamp parseable -- a PARTIAL run
  can never be mistaken for COMPLETE.
- **RECENT_LAST_KNOWN_GOOD fallback** (approved as a narrow, strictly-bounded
  addition, not a general staleness tolerance): for the current/open month
  ONLY, after both the fresh attempt and the one bounded second-pass
  attempt have failed, a persisted cache snapshot may stand in if -- and
  only if -- it originated from a real HTTP 200, its content hash verifies,
  its configured article title matches, it has no duplicate dates, it
  covers every date through a lag-adjusted effective data-end date (capped
  at yesterday, since Wikipedia's own same-day pageview count is never
  complete yet regardless of any transient failure), and it was verified
  within the last 24 hours. Read-only evaluation -- never writes to cache,
  so a failed refresh can never overwrite a valid prior snapshot, and using
  the fallback never resets that snapshot's own age. Provenance fields
  (`wiki_source_mode`, `wiki_fresh_request_failed`,
  `wiki_fresh_failure_http_status`, `wiki_fallback_retrieved_at_utc`,
  `wiki_cache_age_hours`, `wiki_effective_data_end`,
  `wiki_cache_content_hash`) preserve the ORIGINAL retrieval timestamp --
  a fallback-served value is never mislabeled as freshly retrieved.
- **Observational HTTP-status/Retry-After logging** (2026-07-31, purely
  additive): chunk-level diagnostic log lines and `chunk_results` now
  surface the raw numeric HTTP status and `Retry-After` header for both
  the fresh attempt and the bounded second-pass attempt. No request,
  retry, timing, budget, chunk-boundary, fallback, or completeness
  behavior changed -- confirmed by a dedicated test
  (`test_http_status_retry_after_logging_is_purely_additive`) and by the
  full existing suite (26 prior tests) passing unchanged before and after.

**Tests** (all passing, run directly, no external framework): 13
deterministic transport-module tests (`test_phase2_wikipedia_transport.py`,
covering full success, 404-then-recovery, repeated 404, 429/Retry-After,
timeout, real process termination, malformed response, cache corruption,
atomic-write interruption, cache resume, open-month refresh, no
zero-filling, duplicate-date prevention) plus the purely-additive logging
test; 2 run-level completeness-gate tests
(`test_phase2_dailypanel_gate.py`, tests 14-15: the final gate, and PARTIAL
never nameable COMPLETE); 11 RECENT_LAST_KNOWN_GOOD fallback tests
(`test_phase2_wikipedia_recent_cache_fallback.py`: fresh-preferred, valid
fallback used, stale/incomplete/mismatched/corrupt/duplicate cache
rejected, no recursive re-use resetting the clock, failed refresh never
overwrites cache, provenance/timestamp preserved, fallback z-score exactly
matches the original successful response's).

**Scientific-equivalence test** (`test_phase2_wikipedia_equivalence.py`,
AAPL and AMZN): direct full-window response vs. monthly-chunk-assembled
response (including the fallback where applicable) -- every overlapping
date/pageview value matched exactly (300/300 both tickers), and the wiki
z-score field agreed within tolerance for both.

**AMZN-only validation** (`validate_amzn_wiki_only.py`): under live source
conditions where AMZN's July 2026 chunk 404'd on both fresh attempts, the
RECENT_LAST_KNOWN_GOOD fallback correctly used an 11.2-hour-old, fully
gated snapshot; all 300 observations assembled; the resulting field matched
the direct-response calculation exactly; status was correctly
`complete_recent_cache_fallback`, not `fresh`; no child process remained.

**24-ticker regression (2026-07-31): PARTIAL, not COMPLETE.** 2634.8s
(43.9 min), exit code 1, no automatic restart. 24/24 unique tickers, every
non-wiki required field 100% complete (0 nulls across `gst_zscore`,
`implied_volatility`, `realized_vol`, `price`, `volume`). The `wiki_zscore`
field completed for only 12/24 tickers -- 25 calendar-month chunks across
12 tickers failed both the fresh attempt and the bounded second pass.
Evidence preserved in `Live Signal Engine/Phase2 Failure Evidence/
2026-07-31_TransportRewrite_12of24_Regression/` (full failure matrix,
root-cause analysis, preserved checkpoint/marker/logs).

The evidence strongly supports transient, query-specific Wikipedia API
failures, not a defect in this rewrite: failures were scattered across 9
calendar months with no concentration near the most recent data (11/12
affected tickers' open/current month succeeded); a live re-probe of 6
sampled failures recovered 5 within minutes; a minimal single-day
availability probe (AMZN vs. AAPL, a control that fully succeeded in this
same run) showed non-monotonic success/failure on adjacent individual
days for both articles, not a clean recency cutoff. CDN or edge-cache
inconsistency is a possible mechanism for this transience -- it is **not**
confirmed; no lower-level Wikimedia-side diagnostic evidence was available
to verify it. The RECENT_LAST_KNOWN_GOOD fallback correctly stayed out of
scope for the 24 closed-month failures (by design) and correctly rejected
the one open-month failure it did evaluate (NCLH, no prior snapshot
existed).

**This PARTIAL regression validates the fail-closed transport behavior --
not 24/24 dataset completeness. No trading or substantive research
conclusion may use this PARTIAL output.** A disclosed logging gap (the 25
failures were recorded by status category, not raw numeric HTTP code, for
that specific run) is closed prospectively by the observational logging
addition above; it does not retroactively change the classification of
that run's failures, independently confirmed HTTP 404 via a sampled spot
re-probe.

**Remaining limitations, disclosed:** GST/earnings/price-history/IV legs
still use the older daemon-thread mechanism, not process isolation. The
RECENT_LAST_KNOWN_GOOD fallback only ever applies to the current/open
month -- closed-month failures under elevated source instability have no
recovery path in this design. The fallback's effective-data-end check
assumes a fixed 1-day Wikipedia publish lag and requires an exact match;
on a day where the true lag is 2+ days, an otherwise-valid snapshot could
be spuriously rejected -- not observed in the 2026-07-31 regression (whose
one open-month failure was rejected for an unrelated reason), but a
plausible edge case, not fixed in this pass. Commit 3 (a new COMPLETE
24/24 regression) is reserved for a future run under calmer source
conditions.

## 2026-07-30 — Phase 2 run-3: duration correction, operational safeguards, and a passing bounded run

No CHANGELOG.md existed in this repo before this entry.

**Correction to an earlier (informal) hypothesis:** after run 3's first
attempt (2026-07-27) ran for `real 365m3.843s` and produced a completely
empty `phase2_run3.log`, an unbounded yfinance hang was floated as the likely
cause. That was wrong to assert without doing the arithmetic first, and the
arithmetic was done before writing any code this pass, not after:

- **GST leg** (this script's scoped 429 backoff): `TrendReq`'s own
  `timeout=(30, 60)` bounds each of 5 attempts at ~90s before erroring, then
  sleeps up to `backoff+jitter` (28/48/78/108/138s across attempts 1-5).
  Fully-adversarial worst case: `sum(90+28, 90+48, 90+78, 90+108, 90+138) =
  850s` (14.2 min) per ticker -- bounded, and not smaller than the *old*
  flat-60s schedule's own worst case (750s) once the request-timeout
  dimension is included on every attempt.
- **Wikipedia leg** (`GST_Wikipedia_Pageviews_Pull.py`, not modified by this
  entry): `_fetch_chunk()` retries 429/404 up to 4 attempts (10/20/30s waits,
  ~30s timeout each -> up to 180s per chunk), and `_fetch_with_bisection()`
  recurses to `MIN_BISECT_DAYS=45`. For this script's single 300-day pull,
  the bisection tree (300→150→75→~37) makes up to `1+2+4+8 = 15` chunk calls
  if every one fails: **2700s (45 minutes) worst case for a single ticker's
  Wikipedia leg alone** -- true before today, unrelated to the GST change,
  and large enough on its own to matter.
- **yfinance 1.5.1** (installed version, read directly, not assumed):
  `yfinance/data.py`'s `_make_request()` defaults to `timeout=30` per
  underlying HTTP call, and `YfConfig.network.retries` defaults to `0` (no
  internal retry-multiplication). Calls were already bounded by yfinance's
  own defaults -- an initial assumption that they had no timeout at all was
  incorrect.
- Summing a fully-adversarial per-ticker worst case (GST 850s + Wiki 2700s +
  ~270s for earnings/price/IV) × 24 tickers ≈ **1528 minutes (~25.5 hours)**.
  The observed 365-minute duration is only ~24% of that ceiling --
  comfortably explainable by ordinary (if unlucky) bounded retry/bisection
  behavior, especially via the Wikipedia leg. An unbounded hang is not
  required to explain it, and was not assumed going forward.

**What was added** (none of it touches the six field definitions, the
24-ticker universe, any z-score methodology, or the option-contract-selection
rule -- confirmed by diff review before and after):

- Line-buffered, explicitly-flushed stdout (`sys.stdout.reconfigure(...,
  line_buffering=True)` + a `log()` helper using `print(..., flush=True)`) --
  the empty 2026-07-27 log was itself caused by fully-buffered output on a
  redirected, non-TTY stdout combined with a process that never reached a
  normal exit to flush it.
- Explicit START/DONE logging for every source leg (earnings, price
  history, realized vol, IV/options, GST, Wikipedia), every ticker.
- `run_bounded()`: a reusable wrapper that runs any call in a thread and
  waits at most a configured timeout, independent of whether the callee (or
  any library it uses) honors its own `timeout=` parameter.
  **Caught a real bug via the mandated pre-run test, not assumed to work**:
  the first version used `concurrent.futures.ThreadPoolExecutor`, which
  returned promptly from `run_bounded()` on a timeout, but
  `concurrent.futures.thread` registers a process-wide `atexit` hook that
  joins *every* worker thread any `ThreadPoolExecutor` ever created --
  including abandoned ones -- so the whole process would hang at exit
  waiting for a genuinely-stuck call, exactly the failure mode this
  safeguard exists to prevent. Fixed by switching to a plain daemon
  `threading.Thread` (daemon threads are never joined at interpreter exit).
  Verified with two tests before trusting it: (1) `run_bounded()` in
  isolation against an injected 9999s sleep with a 2s budget -- returned in
  2.02s both before and after the fix, but the *process* only exited
  cleanly after the fix (before the fix, the process hung until an outer
  `timeout` wrapper killed it); (2) a full `process_ticker("AAPL")` call
  with a 9999s delay injected into the `price_history` leg specifically
  (via `GST_PHASE2_INJECT_SLOW_TICKER`/`GST_PHASE2_INJECT_SLOW_LEG` env
  vars) -- `price_history_status` correctly recorded `"timeout"` after
  ~45s, the other four legs completed normally with real values (including
  a real GST 429 retry that resolved on its own), and the process exited
  with code 0 on its own.
- `GST_TICKER_BUDGET_S=480s` and `WIKI_TICKER_BUDGET_S=90s`: documented
  cumulative caps per ticker, on top of (not replacing) each leg's existing
  per-attempt timeout/retry/bisection limits. Verified live during the real
  run below: BKR and GME both hit real Wikipedia bisection (visible in
  `phase2_run3.log` as `"...failed -- bisecting at..."`, from the
  unmodified Wikipedia module), taking 61.7s and 61.5s respectively --
  comfortably under the 90s cap, both resolved successfully.
- `PER_TICKER_WALL_BUDGET_S=900s` and `TOTAL_RUN_BUDGET_S=2700s` (45 min):
  checked between tickers; on exhaustion the checkpoint already written is
  preserved, the next (not-yet-started) ticker is recorded as active, and
  the process exits with code 1 without restarting. Verified with a
  monkeypatched 5-second total budget against 3 real tickers: exited code 1
  after 2 tickers, checkpoint file contained exactly those 2 rows, no file
  was written under the completed-run naming convention, and the
  completion marker correctly read `"status": "PARTIAL"`,
  `"active_ticker_when_stopped": "ADBE"`.
- An atomic (write-temp-then-`os.replace`) checkpoint file after every
  ticker, named
  `GST_Phase2_DailyPanel_TestRun_<date>_run3_CHECKPOINT_PARTIAL.csv` --
  deliberately never reused as the final filename, so a partial file can
  never be mistaken for a completed panel.
- A JSON completion marker
  (`GST_Phase2_DailyPanel_TestRun_<date>_run3_COMPLETION_MARKER.json`) with
  row/unique-ticker counts, per-field completeness, per-source failure
  counts, elapsed time, and `COMPLETE`/`PARTIAL` status.
- Per-source `{leg}_status`/`{leg}_error`/`{leg}_elapsed_s` columns
  (additive; the six locked research fields and
  `days_to_nearest_earnings` keep their existing names/meanings), plus
  `gst_retry_count`/`gst_rate_limit_events`/`gst_budget_exhausted`, all
  under an explicit fixed `COLUMN_ORDER` (pre-filled per row, same
  discipline as `GST_MultiTicker_Forward_Log.py`'s own column-order guard).
- Per-ticker exception isolation at the `main()` loop level (in addition to
  the existing per-leg `try`/`except`s inside `process_ticker()`), so one
  ticker's unhandled failure cannot destroy already-collected rows for the
  others.

**Run 3 result (2026-07-30, bounded, unbuffered, hard 45-minute outer
`timeout` wrapper, no auto-restart):** exited code 0 (`COMPLETE`) in
**16m 1.4s** (`real` per `phase2_run3_time.log`; 959.5s per the completion
marker) -- squarely inside the established 15-17 minute baseline.

- 24 rows, 24 unique tickers, 0 duplicates, universe exactly matches the
  locked 24-ticker list.
- All six required fields (`gst_zscore`, `wiki_zscore`,
  `implied_volatility`, `realized_vol`, `price`, `volume`): **0 nulls / 24**
  -- 100% complete, matching runs 1 and 2.
- `days_to_nearest_earnings` is null for 4 tickers (CTSH, MSFT, QCOM,
  SBUX) -- `earnings_status="ok"` for all four (a genuine "no upcoming
  earnings date found" result, not a fetch failure), plausibly explained by
  MSFT's earnings landing 2026-07-29, the day before this run, shifting
  what "next" earnings resolves to. This is why
  `all_six_fields_clean_count=20` rather than 24, even though the six core
  research fields are fully complete.
- `retrieval_timestamp_utc` parses cleanly for all rows and is
  monotonically increasing (tickers processed in the intended
  priority-then-list order); single consistent `run_date`.
- `option_expiry` present for all 24 rows and strictly later than
  `run_date` for all 24 -- the contract-selection rule
  (`get_nearest_post_earnings_expiry`, imported unchanged) is intact.
  Observed one pre-existing, disclosed-in-code data quality pattern, not a
  new bug: ADBE's nearest listed expiry was 1 day out (2026-07-31),
  producing a near-degenerate `implied_volatility=0.00001` on both legs --
  the same class of issue this script's header already flagged from the
  original AAPL smoke test (a very-near-term expiry can have effectively no
  time value), just one day further out than the literal same-day case
  that fix already excludes.
- GST leg vs. runs 1/2: `gst_status="ok"` for 24/24 (no `attempts_exhausted`
  or `budget_exhausted`). Total retry attempts 41 (mean 1.71/ticker), 17
  rate-limit events across 9/24 tickers -- comparable to run 1's disclosed
  9/24 tickers hitting a 429, somewhat more than run 2's 7/24. Total GST
  time 690.0s (mean 28.8s, max 145.2s), sitting between run 1 (815.3s
  total, max 183.6s) and run 2 (658.8s total, max 182.9s) -- not a clear
  win or loss on total time, but run 3's single worst ticker (145.2s) was
  faster than both prior runs' worst ticker, directionally consistent with
  the escalating/shorter-first-retry schedule's intent. One run is not
  enough to call this a proven improvement either way.
- IV and Wikipedia legs: IV timing in line with runs 1/2 (mean 0.29s vs.
  0.37s/0.42s). Wikipedia timing shows real variance runs 1/2 didn't
  exhibit (mean 5.54s, max 61.71s vs. ~0.3-0.6s in both prior runs) --
  explained above by BKR/GME's real bisection, not a regression, and
  correctly bounded by the new per-ticker Wikipedia budget rather than
  running unbounded.

**Verified before committing:** implementation tests (above) passed before
this run was attempted, and the run itself completed 24/24 with the checks
this entry documents. GitHub Actions is deliberately NOT wired up by this
entry -- this remains a manual test-run script.
