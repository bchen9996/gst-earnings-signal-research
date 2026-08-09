# GST Earnings Attention Observatory

**A prospectively governed research system for measuring how unusual public attention propagates into prices, volume, volatility, and related securities around large-cap earnings.**

Built by Tyler He and Harshith Akurati (high-school researchers, St. Louis MO) with Saint Louis University professor Marcus Painter.

---

## Current status — read this first

| | |
|---|---|
| **Retrospective reconstruction** | Exists. n=152 canonical events. Carries a documented, unresolved **point-in-time limitation** — it is a reconstruction, not a live track record. |
| **Prospective cohort** | **Underway.** Rules locked before any candidate was screened. |
| **Registered events** | **1** — `EVT-DELL-FY27Q2-ERN` (DELL FY27Q2, 2026-09-03, AMC). |
| **Prospective outcomes analyzed** | **0.** Zero observations, zero frozen event IDs, zero results. |
| **Profitable strategy demonstrated** | **No.** None. See [What this project does not claim](#what-this-project-does-not-claim). |
| **Options benchmarking** | **Unavailable / unverified.** No cleared, timestamped, executable options source. |
| **Can the project still proceed?** | **Yes** — via core-only market-response measurement. Missing options data lowers an event's completeness tier; it never removes an otherwise valid event from the core cohort. |

The next authorized screening sweep is **Monday 2026-08-10, 09:00 America/Chicago**, fixed by [cohort protocol v1.1](Live%20Signal%20Engine/GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1_DRAFT.md) *before* the first candidate page was ever opened.

## The scientific question

> **How does abnormal public attention propagate into prices, volume, volatility, and related securities around large-cap earnings?**

Google Search Trends (GST) supplies a candidate *abnormal-attention regime*. Subsequent market data reveals *where and when* the response occurs. Any instrument or strategy would be **downstream** of validated evidence — not the identity of the project. Options were one attempted benchmark and expression, never the project itself.

## Four things that are not the same thing

| Layer | What it is | Where it stands |
|---|---|---|
| **Retrospective evidence** | What the methodology produces on reconstructed history | Exists; point-in-time limitation unresolved |
| **Prospective confirmation** | A preregistered test on events registered *before* the outcome exists | **Underway, 0 outcomes analyzed** |
| **Exploratory localization** | *Where* in the event window a response concentrates | Framework defined; no prospective result |
| **Future trading / product** | Any instrument, rule, or application | **Not started. Not claimed. Downstream of the above.** |

## Architecture

```
 Attention panel            GST + Wikipedia daily panel, six locked fields per ticker
        │                   GST_Phase2_DailyPanel.py
        ▼
 Cohort screening           Official issuer / SEC sources only, fixed Monday cadence
        │                   cohort protocol v1.1
        ▼
 Event registration         Human-verified, append-only registry
        │                   Market_Response_Event_Registry/registry.jsonl
        ▼
 Pre-event capture          Blind six-field snapshot at the derived XNYS anchor
        │                   strict v0.2 core gate, immutable stage markers
        ▼
 Event dossier              Blinded Layer A core / Layer B market addendum
        │                   Event_Dossier_Protocol/
        ▼
 D1 / D3 decomposition      Where and when the move happened
        │                   signed intervals + canonical abs_* magnitudes
        ▼
 Hypothesis registry        Named hypotheses, thresholds, fail-closed display gates
        │                   HYP-01 analysis lock
        ▼
 Append-only evidence       Including the failures. Nothing is rewritten.
```

## The locked universe (24 tickers)

Defined once in [`gst_market_response/constants.py`](gst_market_response/constants.py) as `LOCKED_24_TICKER_UNIVERSE`; every document generates its list from that constant.

```
AAPL  ABBV  ADBE  AMZN  BKR   BRK-B  CTSH  DELL
DVN   GME   GOOGL GPN   INTC  LDOS   MSFT  NCLH
NKE   QCOM  SBUX  STZ   SYK   TSLA   TTWO  UAL
```

## Registered hypotheses

Three named hypotheses are registered. **Eligibility classes are not hypotheses** — a class says which evidence modules an event carries; a hypothesis is a dated question with its own threshold and display gate.

| ID | Question | n ≥ | Status |
|---|---|---|---|
| **HYP-01** | Pre-earnings attention and market repricing | 60 | `ACTIVE_COLLECTING` |
| **HYP-02** | Cross-source attention divergence vs. earnings surprise | 60 | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |
| **HYP-03** | Post-earnings attention decay and continued repricing | 40 | `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED` |

No options hypothesis is registered; both options eligibility classes carry `DENY_NO_REGISTERED_HYPOTHESIS`.

### HYP-01, reproduced from its lock

Reproduced verbatim from [`GST_HYP01_ANALYSIS_LOCK_v1.0.json`](Live%20Signal%20Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json). This README does not restate it in its own words.

> **Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?**

| | |
|---|---|
| Predictor | `gst_zscore` — continuous, unthresholded, at the pre-event anchor session |
| Primary outcome | `abs_overnight_gap` = `abs(overnight_gap)`, where `overnight_gap = next_session_open / previous_close - 1` |
| Primary model | `abs_overnight_gap ~ gst_zscore`, ordinary least squares |
| Null | `beta_gst = 0`, **two-sided**, **α = 0.05** |
| Covariance | cluster-robust on `ticker`, finite-sample correction **on** |
| Reported | coefficient · 95% confidence interval · p-value · eligible-event count · unique-ticker count |
| Sample | first **60** eligible events by derived response-session date, tie-broken by `event_id`; `BMO`/`AMC` eligible, `INTRADAY` ineligible for *this* outcome |
| **Results** | **none — `results: null`, `frozen_event_ids: []`, eligible events: 0** |

`INTRADAY` events stay enrolled in the cohort; they are ineligible for this particular outcome because an overnight window would straddle rather than follow an intraday release. That rule was fixed before any data existed.

## Persisted response fields

Six signed intervals, each stored **alongside** a canonical absolute counterpart (SPEC v0.1; emitted by [`pipeline.py`](gst_market_response/pipeline.py) via [`response_magnitude.py`](gst_market_response/response_magnitude.py)):

| Stage | Signed | Absolute |
|---|---|---|
| D1 | `overnight_gap` | `abs_overnight_gap` |
| D1 | `open_to_30m` | `abs_open_to_30m` |
| D1 | `thirty_min_to_close` | `abs_thirty_min_to_close` |
| D1 | `open_to_close` | `abs_open_to_close` |
| D3 | `close_T1_to_close_T2` | `abs_close_T1_to_close_T2` |
| D3 | `close_T1_to_close_T3` | `abs_close_T1_to_close_T3` |

Signed values are never replaced. A signed `0.0` yields `0.0`; a missing value yields `null`, never zero.

## What this project does not claim

- **Not an options project.** Options were one attempted benchmark. No verified options source exists, and no options hypothesis is registered.
- **Not a proven trading algorithm.** No strategy has been validated prospectively. None is being run.
- **Not arbitrage.** Nothing here identifies a risk-free or near-risk-free opportunity.
- **Not a profitability claim.** The one backtest that ever showed attractive economics was **invalidated** (below).
- **Not a completed prospective study.** Zero prospective outcomes have been analyzed.
- **Not a live track record.** The retrospective population is a reconstruction with a documented point-in-time failure.

## Why the failures matter

Most of what this project has learned came from things that broke. All of it is preserved; none was quietly deleted.

**The straddle economics were reversed by real quotes.** The original backtest used a synthetic Black-Scholes markup of `1.2398`. Recalibrating against real quoted option costs on the same n=152 population reversed it:

| Version | Win rate | Median P&L | Sharpe | Max DD |
|---|---|---|---|---|
| Original (synthetic markup 1.2398) | 76.3% | **+145.5%** | 2.222 | −3.6% |
| Recalibrated (n=76 real quotes, markup 3.4098) | 43.4% | **−10.7%** | +0.273 | −46.37% |

The `+145.5%` figure is **invalidated** and appears here only so it is never cited without its reversal. The estimate stabilized between recalibrations rather than swinging, so this is not small-sample noise. ([status §3](Live%20Signal%20Engine/STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md))

**The point-in-time check failed.** Every historical z-score was reconstructed by querying Trends *today* for a window ending years earlier. Reproducible, but not provably what a live observer saw. No waiver was found; the check is treated as **failed**. ([status §1a](Live%20Signal%20Engine/STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md))

**A reconstruction was quarantined for look-ahead contamination.** The n=148 continuous-window version had confirmed look-ahead bias and is quarantined; n=152 supersedes it. ([status §1](Live%20Signal%20Engine/STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md))

**Out-of-sample tests killed hypotheses.** Hypothesis #5 (volatility mispricing): **dead**. Attention Spread: **dead, direction reversed**. C5 post-earnings continuation: near-miss, does not clear the bar. ([status §§7–9](Live%20Signal%20Engine/STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md))

**Infrastructure failed loudly and was recorded.** A Wikipedia transport failure and a 12-of-24 regression are preserved with logs and exit codes ([AMZN 180s](Live%20Signal%20Engine/Phase2%20Failure%20Evidence/2026-07-30_AMZN_Wikipedia_180s/SECTIONS_A-C_SUMMARY.md), [transport regression](Live%20Signal%20Engine/Phase2%20Failure%20Evidence/2026-07-31_TransportRewrite_12of24_Regression/REGRESSION_SUMMARY.md)). The MSFT dossier pilot was permanently marked blinding-compromised rather than reused ([disposition](Event_Dossier_Protocol/MSFT_PILOT_QC_AND_DISPOSITION.md)).

**Round-one screening over-claimed, and was corrected additively.** The first sweep wrote a canonical `PENDING_OFFICIAL_DATE_UNAVAILABLE` disposition for 23 tickers when no fiscal-period identity had been established, and mislabeled a spill-prevention page as an IR events calendar. The original bytes were kept and hash-locked; a [correction overlay](Live%20Signal%20Engine/Cohort_Screening_Round1/ROUND1_CORRECTION_OVERLAY_v1.json) supersedes the interpretation without rewriting the evidence ([audit](Live%20Signal%20Engine/Cohort_Screening_Round1/ROUND1_EVIDENCE_AUDIT.md)).

## Navigate by what you want

**Quick overview (5 min)** — this README, then [PROJECT_NORTH_STAR_v1.0_DRAFT.md](PROJECT_NORTH_STAR_v1.0_DRAFT.md).

**Methodology** — [cohort protocol v1.1](Live%20Signal%20Engine/GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1_DRAFT.md) · [hypothesis registry](Live%20Signal%20Engine/GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md) · [HYP-01 lock](Live%20Signal%20Engine/GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md) · [eligibility & freeze rules](Live%20Signal%20Engine/GST_HYP01_ELIGIBILITY_AND_FREEZE_RULES_v1.0.md) · [display gates](Live%20Signal%20Engine/GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md) · [field crosswalk](Live%20Signal%20Engine/GST_PROSPECTIVE_HYPOTHESIS_FIELD_CROSSWALK_v1.0.md) · [market-response SPEC v0.1](Live%20Signal%20Engine/GST_Earnings_Market_Response_Decomposition_SPEC_v0.1_DRAFT.md) / [v0.2](Live%20Signal%20Engine/GST_Earnings_Market_Response_Decomposition_SPEC_v0.2_DRAFT.md) · field dictionary [v0.1](Live%20Signal%20Engine/GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.1.md) / [v0.2](Live%20Signal%20Engine/GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.2.md) · [attention-panel SPEC](Live%20Signal%20Engine/GST_Phase2_InformationArrivalPanel_SPEC_DRAFT.md) · [Event Dossier Protocol](Event_Dossier_Protocol/EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md)

**Engineering / reproducibility** — [`gst_market_response/`](gst_market_response/) ([constants](gst_market_response/constants.py) · [completeness gates](gst_market_response/completeness.py) · [pipeline](gst_market_response/pipeline.py) · [derivations](gst_market_response/derivations.py) · [abs\_\* persistence](gst_market_response/response_magnitude.py)) · [attention panel](GST_Phase2_DailyPanel.py) · [dossier validator](Event_Dossier_Protocol/validator/) · CI: [market-response](.github/workflows/market-response-tests.yml), [dossier validator](.github/workflows/event-dossier-validator-tests.yml) · [readiness checklist](Live%20Signal%20Engine/GST_MARKET_RESPONSE_OPERATIONAL_READINESS_CHECKLIST_v0.1.md)

**Historical failures** — [current status](Live%20Signal%20Engine/STRATEGY_SPEC_v1.0_CURRENT_STATUS_2026-07-19.md) · [root CHANGELOG](CHANGELOG.md) · [dossier CHANGELOG](Event_Dossier_Protocol/CHANGELOG.md) · [Phase 2 failure evidence](Live%20Signal%20Engine/Phase2%20Failure%20Evidence/)

**Prospective evidence** — [registry](Live%20Signal%20Engine/Market_Response_Event_Registry/registry.jsonl) · [round-1 sweep manifest](Live%20Signal%20Engine/Cohort_Screening_Round1/SWEEP_MANIFEST_ROUND1.json) · [correction overlay](Live%20Signal%20Engine/Cohort_Screening_Round1/ROUND1_CORRECTION_OVERLAY_v1.json) · [evidence audit](Live%20Signal%20Engine/Cohort_Screening_Round1/ROUND1_EVIDENCE_AUDIT.md) · [human-review queue](Live%20Signal%20Engine/Cohort_Screening_Round1/HUMAN_REVIEW_REQUIRED_ROUND1.json) · [round-2 runbook](Live%20Signal%20Engine/Cohort_Screening_Round1/ROUND2_RENDERER_RUNBOOK.md) · [screening-log schema](Live%20Signal%20Engine/GST_PROSPECTIVE_COHORT_SCREENING_LOG_SCHEMA_v1.0.md)

**Governance blueprints** — [North Star](PROJECT_NORTH_STAR_v1.0_DRAFT.md) · [institutionalization blueprint](INSTITUTIONALIZATION_BLUEPRINT_v1.0_DRAFT.md) · [preregistration gap audit](PREREGISTRATION_GAP_AUDIT_v1.0.md)

## Roadmap — all of this is future work

None of the following has been started, validated, or claimed:

- **Now → 2027-05-31.** Run the weekly cadence, register eligible events, capture blind pre-event observations, collect D1/D3 responses. Target ≥ 60 registered events.
- **Blocked on a dependency.** HYP-02 needs an earnings-surprise capture path (the dossier schema has the fields; nothing populates them). HYP-03 needs a post-event attention-decay measurement that does not exist.
- **Requires external access.** Options benchmarking requires a cleared, timestamped, executable quote source. Not obtained.
- **Requires human decisions.** Several preregistration elements remain unresolved and must not be guessed — see the [gap audit](PREREGISTRATION_GAP_AUDIT_v1.0.md).
- **Only after evidence.** External preregistration, replication, a public radar, and any instrument or strategy work. See the [blueprint](INSTITUTIONALIZATION_BLUEPRINT_v1.0_DRAFT.md).

## History

This repository began in 2025 as a smaller study: 15 retail-heavy tickers, weekly GST spikes ≥ 85 over 2014–2019, and an intention to tune simple trading rules. That framing is **obsolete**. It was superseded by the 24-ticker locked universe, the six-field daily panel, the event-registry and dossier protocols, and the prospectively governed cohort described above. The earlier scripts and outputs remain in the repository as history, not as current methodology.

---

*Nothing in this repository constitutes investment advice, a solicitation, or a representation that any approach is profitable.*
