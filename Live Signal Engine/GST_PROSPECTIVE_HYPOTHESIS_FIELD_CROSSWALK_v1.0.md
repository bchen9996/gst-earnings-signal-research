# GST Prospective Hypothesis — Field Crosswalk v1.0

Companion to `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md`.

This is the honest inventory: for every measurement the three registered hypotheses need, **where it lives, whether it can actually be captured, and what has not been decided.** It is what makes each hypothesis's status mechanical rather than asserted.

---

## 1. Availability categories

| Category | Meaning |
|---|---|
| **IMPLEMENTED** | A production field exists **and** a production capture path writes it. Usable now. |
| **DOSSIER-ONLY** | A schema field exists in the Event Dossier Protocol, with validator enforcement, but **no production capture path and no production join** to a market-response event. Not usable now. |
| **NOT IMPLEMENTED** | No production field, no capture path, nothing to join. Not usable now. |

Only **IMPLEMENTED** measurements can make a hypothesis `ACTIVE_COLLECTING`.

## 2. Eligibility class versus named hypothesis

| Concept | Lives in | Answers | Example |
|---|---|---|---|
| **Data-eligibility class** | `completeness.HYPOTHESIS_CLASSES` | "which evidence modules does this event carry?" | `core_attention_vs_equity_response` |
| **Named hypothesis** | this registry | "what question, at what threshold, with what display gate?" | `HYP-01` |

A class is a property of an *event*. A hypothesis is a property of the *study*. Many events share one class; one hypothesis maps onto one class plus its own measurement requirements. **Satisfying a class never licenses a result** — only the display gate does.

## 3. HYP-01 — Pre-earnings attention and market repricing

| Measurement | Field(s) | Source | Capture path | Status |
|---|---|---|---|---|
| GST attention | `gst_zscore` | Phase 2 panel → `phase2_adapter` | pre-event capture orchestrator | **IMPLEMENTED** |
| Wikipedia attention | `wiki_zscore` | Phase 2 panel → `phase2_adapter` | pre-event capture orchestrator | **IMPLEMENTED** |
| Panel IV (completeness only) | `panel_implied_volatility` | Phase 2 panel `iv_status` leg | pre-event capture orchestrator | **IMPLEMENTED** |
| Realized volatility | `realized_volatility` | Phase 2 panel `realized_vol_status` leg | pre-event capture orchestrator | **IMPLEMENTED** |
| Price | `previous_close` | Phase 2 panel `price_history_status` leg | pre-event capture orchestrator | **IMPLEMENTED** |
| Volume | `volume` | Phase 2 panel `price_history_status` leg | pre-event capture orchestrator | **IMPLEMENTED** |
| Snapshot provenance | `pre_event_snapshot_asof_utc` | Phase 2 panel | pre-event capture orchestrator | **IMPLEMENTED** |
| D1 intervals | `overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close` | `derivations` | `pipeline.capture_d1` | **IMPLEMENTED** |
| D3 intervals | `close_T1_to_close_T2`, `close_T1_to_close_T3` | `derivations` | `pipeline.capture_d3` | **IMPLEMENTED** |

Gates: `evaluate_strict_core_v0_2` · `is_valid_d1_decomposition` · `is_valid_d3_completion`.

**Every requirement is IMPLEMENTED → `ACTIVE_COLLECTING`.** No new return formula is introduced; the hypothesis binds only to the fields above.

### 3.1 Unresolved for HYP-01 — `PENDING_SEPARATE_ANALYSIS_LOCK`

| # | Decision | Why it is not guessed |
|---|---|---|
| 1 | **Exposure definition** — which attention field, and continuous versus thresholded | No authoritative spec designates one. `GST_Z_THRESHOLD = 2.0` exists in `constants` but is documented as the elevation threshold for `gst_persistence_v0.1`, not as this hypothesis's exposure. |
| 2 | **Primary outcome** — which existing D1/D3 field is *the* absolute-response measure | Six interval fields exist. Choosing after seeing data would be selection; choosing arbitrarily now would be a guess. |
| 3 | **Covariates / benchmark adjustment** | `derivations.relative_return` exists but no spec fixes a benchmark for this hypothesis. |
| 4 | **Ticker-cluster estimator** | Clustering is *required* (CNT-6); the specific estimator is not yet fixed. |

## 4. HYP-02 — Cross-source attention divergence and earnings surprise

| Measurement | Field(s) | Source | Capture path | Status |
|---|---|---|---|---|
| Strict core pre-event | as HYP-01 | Phase 2 panel | pre-event capture orchestrator | **IMPLEMENTED** |
| EPS surprise | `event_labels.eps_surprise_pct` | Event Dossier Layer A schema | **none in production** — only test fixtures write it | **DOSSIER-ONLY** |
| Revenue surprise | `event_labels.revenue_surprise_pct` | Event Dossier Layer A schema | **none in production** | **DOSSIER-ONLY** |
| Event → dossier join | — | — | **does not exist** | **NOT IMPLEMENTED** |

The surprise fields are real, schema-enforced and blinding-governed — but nothing in production populates them, and no join maps a market-response `event_id` to a dossier surprise value. "Production field **and** capture path" therefore fails.

**→ `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`.** The hypothesis accrues no eligible events.

**Forbidden substitutions:** analyst reaction · price movement · news tone · any other proxy. An event lacking the disclosed-surprise measurement simply does not count. A missing surprise is never zero-filled (CNT-4).

### 4.1 Unresolved for HYP-02 — `PENDING_SEPARATE_ANALYSIS_LOCK`

| # | Decision | Why it is not guessed |
|---|---|---|
| 1 | **Divergence measure** between GST and Wikipedia z-scores | No authoritative specification defines one. Difference, ratio, rank gap and residual-from-regression are all defensible and would give different answers. |
| 2 | **Which surprise field is primary** (EPS or revenue), and sign handling | Both exist in the schema; neither is designated. |
| 3 | **Ticker-cluster estimator** | As HYP-01. |

## 5. HYP-03 — Post-earnings attention decay and continued repricing

| Measurement | Field(s) | Source | Capture path | Status |
|---|---|---|---|---|
| Eligible core event | as HYP-01 | Phase 2 panel | pre-event capture orchestrator | **IMPLEMENTED** |
| D1 / D3 response | as HYP-01 | `derivations` | `pipeline.capture_d1` / `capture_d3` | **IMPLEMENTED** |
| Post-event attention capture stage | — | — | **does not exist** — the state machine captures pre-event, D1 and D3, all *market* observations | **NOT IMPLEMENTED** |
| Attention-decay half-life | — | — | **does not exist** — no module computes a decay curve or half-life | **NOT IMPLEMENTED** |

**→ `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`.**

**Nearest existing measurement, deliberately not reused:** `derivations.gst_slope_v0_1` computes the signed slope of the trailing 12 GST levels ending at the **pre-event** snapshot. It is a pre-event trajectory measure, not a post-release decay half-life. Repurposing it would silently answer a different question, so it is not repurposed.

Building the missing measurement is **not authorised** in this task.

### 5.1 Unresolved for HYP-03 — `PENDING_SEPARATE_ANALYSIS_LOCK`

| # | Decision | Why it is not guessed |
|---|---|---|
| 1 | **Definition of attention-decay half-life** — source series, window, estimator, and handling of series that do not decay | Nothing specifies it. A half-life is undefined for a flat or rising series; that case needs an explicit rule, not a default. |
| 2 | **"Continued repricing after the initial response"** in terms of existing D1/D3 fields | The D3 tier carries `close_T1_to_close_T2` and `close_T1_to_close_T3`; which represents "continued" repricing relative to D1 is a modelling choice. |
| 3 | **Ticker-cluster estimator** | As HYP-01. |

## 6. Options measurements — no registered hypothesis

| Measurement | Status | Display |
|---|---|---|
| `options_implied_move` class | class exists; option benchmark path exists but is gated (CLI refuses `VALID_VERIFIED`; no cleared provider artifact) | **`DENY_NO_REGISTERED_HYPOTHESIS`** |
| `joint_attention_plus_options` class | as above | **`DENY_NO_REGISTERED_HYPOTHESIS`** |

Options unavailability may lower an event to `core_only_no_option_benchmark`. It **never** blocks HYP-01, HYP-02 or HYP-03 enrollment when that event's own core fields are valid.

## 7. Summary

| Hypothesis | Implemented | Dossier-only | Not implemented | Status |
|---|---|---|---|---|
| HYP-01 | all 15 fields | — | — | `ACTIVE_COLLECTING` |
| HYP-02 | strict core (7) | EPS + revenue surprise | event→dossier join | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| HYP-03 | strict core (7) + D1/D3 (6) | — | post-event attention capture; decay half-life | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |

**Ten unresolved analysis decisions** are recorded across the three hypotheses, every one marked `PENDING_SEPARATE_ANALYSIS_LOCK`. None may be resolved by guessing, and none may be resolved after an eligible event set is frozen.
