# GST Prospective Hypothesis Registry — v1.0 (DRAFT)

**Status:** Draft, registered **after** the cohort rules merged and **before** any candidate screening or prospective observation. Authored 2026-08-09 (UTC).
**Canonical machine-readable form:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json` — a mechanical test enforces that the two agree.
**Companions:** `GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` · `GST_PROSPECTIVE_HYPOTHESIS_FIELD_CROSSWALK_v1.0.md` · `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md`

**No result exists.** No direction, effect estimate, plot, p-value or confidence interval has been produced for any hypothesis, and none may be before that hypothesis's threshold is reached and its event set and analysis commit are frozen.

---

## 1. The critical distinction: eligibility classes are not hypotheses

`gst_market_response.completeness.HYPOTHESIS_CLASSES` — `core_attention_vs_equity_response`, `options_implied_move`, `joint_attention_plus_options` — are **data-eligibility classes**. A class states which evidence modules an event carries. It says nothing about what question is being asked, what threshold applies, or whether anything may be displayed.

A **hypothesis** is a named, dated research question with its own minimum event count, classification, status and display gate. The two are registered separately here, and each hypothesis maps explicitly onto the class and measurements it requires. **A class is never a hypothesis**, and satisfying a class never by itself licenses a result.

## 2. The three registered hypotheses

| ID | Title | Class | n ≥ | Options? | Status |
|---|---|---|---|---|---|
| **HYP-01** | Pre-earnings attention and market repricing | primary confirmatory observational | **60** | no | **`ACTIVE_COLLECTING`** |
| **HYP-02** | Cross-source attention divergence and earnings surprise | preregistered secondary | **60** | no | **`PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`** |
| **HYP-03** | Post-earnings attention decay and continued repricing | preregistered exploratory | **40** | no | **`PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`** |

`ACTIVE_COLLECTING` requires that **every** required measurement already has a production field **and** a production capture path. Otherwise the hypothesis is registered but accrues **no eligible events at all**. Missing implementation is never counted as eligibility.

---

### HYP-01 — Pre-earnings attention and market repricing

> Does abnormal pre-earnings public attention precede greater absolute market response around the earnings release?

**Sole primary confirmatory hypothesis.** Minimum **60** eligible events. Required eligibility class: `core_attention_vs_equity_response`. Options benchmark **not** required.

Bound **only** to existing fields — no new return formula is introduced:

| Role | Fields | Gate |
|---|---|---|
| Pre-event | `gst_zscore`, `wiki_zscore`, `panel_implied_volatility`, `realized_volatility`, `previous_close`, `volume`, `pre_event_snapshot_asof_utc` | `evaluate_strict_core_v0_2` |
| D1 | `overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close` | `is_valid_d1_decomposition` |
| D3 | `close_T1_to_close_T2`, `close_T1_to_close_T3` | `is_valid_d3_completion` |

**Status basis:** every field above exists in production and has a production capture path — the pre-event capture orchestrator for the core, `pipeline.capture_d1` / `capture_d3` for the response intervals.

**Unresolved (`PENDING_SEPARATE_ANALYSIS_LOCK`, never guessed):** the exposure definition (which attention field, continuous or thresholded); which existing D1/D3 field is *the* primary absolute-response measure; the covariate set and any benchmark adjustment; the ticker-cluster estimator.

**Display:** nothing — no result, direction, effect estimate, plot, p-value or confidence interval — before **60** eligible events.

---

### HYP-02 — Cross-source attention divergence and earnings surprise

> Does divergence between Google-search attention and Wikipedia attention before earnings associate with the magnitude of subsequently disclosed earnings surprise?

**Preregistered secondary.** Minimum **60** eligible events. Options benchmark **not** required.

**Status: `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`**, determined mechanically:

- the strict core pre-event observation **is** implemented;
- `eps_surprise_pct` and `revenue_surprise_pct` exist **only** as Event Dossier Layer A schema columns (`Event_Dossier_Protocol/A_Blinded_Event_Core/schemas/event_labels.csv`), with validator enforcement;
- **no production code writes them** — the only writers in the tree are test fixtures;
- **no production join** maps a market-response `event_id` to a dossier surprise value.

"Production field **and** capture path" therefore fails on the capture path and the join. The hypothesis is registered and dated; it accrues no eligible events until that is built under a separate authorised task, which this task does not perform.

**Never substituted:** analyst reaction · price movement · news tone · any other proxy for disclosed earnings surprise. If the disclosed-surprise measurement is unavailable for an event, that event simply does not count toward HYP-02. A missing surprise is never zero-filled.

**Unresolved (`PENDING_SEPARATE_ANALYSIS_LOCK`):** the divergence measure between GST and Wikipedia z-scores — no authoritative specification defines one; which surprise field is primary (EPS or revenue) and its sign handling; the ticker-cluster estimator.

---

### HYP-03 — Post-earnings attention decay and continued repricing

> Among events with valid post-release measurements, is attention-decay half-life associated with continued market repricing after the initial response?

**Preregistered exploratory.** Minimum **40** eligible events. Options benchmark **not** required.

**Status: `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`**, determined mechanically: **no production attention-decay measurement exists.** The market-response state machine captures pre-event, D1 and D3 — all *market* observations. There is no post-event **attention** capture stage, and no module computes a decay curve or half-life.

`derivations.gst_slope_v0_1` is the nearest existing thing and is **not** a substitute: it is a *pre-event* trailing slope over the 12-observation window ending at the pre-event snapshot. Repurposing it would answer a different question, so it is not repurposed.

**Building the missing measurement is not authorised in this task.**

**Unresolved (`PENDING_SEPARATE_ANALYSIS_LOCK`):** the definition of attention-decay half-life (source series, window, estimator, handling of non-decaying series); the definition of "continued repricing after the initial response" in terms of existing D1/D3 fields; the ticker-cluster estimator.

---

## 3. Options-related classes — no hypothesis registered

`options_implied_move` and `joint_attention_plus_options` remain valid data-eligibility classes, and events may continue to be classified into them. **No named hypothesis is registered against either**, so their result-display status is **`DENY_NO_REGISTERED_HYPOTHESIS`**. Registering one is a separate, dated decision.

An unavailable options benchmark may lower an event to `core_only_no_option_benchmark`. It **never** prevents HYP-01, HYP-02 or HYP-03 enrollment when that event's own required core fields are otherwise valid.

## 4. Counting rules

| # | Rule |
|---|---|
| CNT-1 | One unique `event_id` counts **at most once** for a given hypothesis. |
| CNT-2 | Duplicate ticker/fiscal-quarter events never count twice; the cohort protocol bars a second registration for the same pair. |
| CNT-3 | An event counts only if **every** required gate and measurement for that hypothesis passes. |
| CNT-4 | Missing values remain missing — no zero-fill, no imputation, no carry-forward, no proxy. |
| CNT-5 | Events are **never** removed because their results are null or unfavourable. |
| CNT-6 | Repeated observations from the same ticker are distinct events and must be identified for clustered analysis. They are **never** described as statistically independent companies. |
| CNT-7 | Reaching the threshold **freezes** the eligible event-ID set and the analysis-code commit **before** any result is calculated. |
| CNT-8 | **No optional stopping.** The threshold is not re-checked for significance; collection is neither stopped early nor extended because of what results look like. |
| CNT-9 | Events collected after the frozen analysis form an **extension cohort**, reported separately, unless a new dated protocol version specifies otherwise. |
| CNT-10 | `EVT-DELL-FY27Q2-ERN` counts only if it passes the same gates as every other event. No exemption, no priority, no special case. |

## 5. Statistical governance — registered, nothing calculated

- **HYP-01 is the sole primary confirmatory hypothesis.** HYP-02 is secondary; HYP-03 is exploratory.
- All tests use **two-sided** inference.
- Primary significance level **α = 0.05**.
- Report **effect sizes** and **95% confidence intervals**.
- Repeated ticker observations require **ticker-cluster-aware inference**.
- HYP-02 and HYP-03 may **never** be promoted to confirmatory on the basis of observed results. Promotion requires a new dated registry version written *before* the results that would motivate it are seen.
- **No model may be changed after the eligible event set is frozen.**
- Any exact model term or outcome mapping not already established in an existing authoritative specification is marked **`PENDING_SEPARATE_ANALYSIS_LOCK`** and is never guessed.

**On the numbers.** No power calculation was performed, and none may be performed using observed project results. **60 / 60 / 40 are governance eligibility floors** — the minimum evidence required before a result may be looked at — **not** claims of guaranteed statistical power, and not estimates of detectable effect size.

Multiplicity: three hypotheses are registered, one confirmatory. Any adjustment across families is itself `PENDING_SEPARATE_ANALYSIS_LOCK`.

## 6. External dashboard — a coincidence, not an authority

The separate `gst-attention-radar` repository ships **DEMO / development-pilot fixtures only**, with no live pipeline. Its fixture happens to carry `minimum_observations` of **60 / 60 / 40** for `H1-attention-precedes-repricing`, `H2-wikipedia-vs-search-divergence` and `H3-attention-decay-half-life`, matching the thresholds registered here.

That is recorded as an observation, not a justification. **The demo fixture is not the source of authority — this registry is.** Its observation counts are fixture values, not real observations. If the two ever disagree, this registry governs and the fixture is wrong. It was **not edited** by this task.

## 7. Current state

Eligible event counts: **HYP-01 = 0 · HYP-02 = 0 · HYP-03 = 0**. Results: **none**. No candidate has been screened, no prospective event has been observed, and no DELL data has been collected.
