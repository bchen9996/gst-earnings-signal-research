# Project North Star — v1.0 (DRAFT)

**Status:** Draft. Governance and architecture only. **This document changes no active methodology.** It does not revise HYP-01, the cohort protocol, any specification, gate, threshold, or registry. Where it restates a locked value, it reproduces it from the locked artifact.

---

## 1. Umbrella identity

**The Earnings Attention Observatory.**

A prospectively governed research system that measures how unusual public attention propagates into prices, volume, volatility, and related securities around large-cap earnings.

It is **not** an options project, **not** a trading algorithm, **not** an arbitrage claim, and **not** a completed study. It is measurement infrastructure with an append-only evidence trail, including its failures.

## 2. Central research question

> **How does abnormal public attention propagate into prices, volume, volatility, and related securities around large-cap earnings?**

Three sub-questions the architecture is built to separate:

1. **Does** abnormal attention associate with the size of the earnings response? *(HYP-01, confirmatory)*
2. **Where and when** in the event window does the response concentrate? *(localization, exploratory)*
3. **Through which instrument** is any such response best observed or expressed? *(downstream, unstarted)*

## 3. Why the attention signal is the project and the instrument is downstream

GST supplies a candidate **abnormal-attention regime** — a claim about *information arrival*, not about any security's price. Market data then reveals *where and when* a response occurs. An instrument is a **measurement or expression choice made after** the response is characterised.

This ordering is not stylistic. The project already learned it the expensive way: the original straddle economics were driven by a synthetic option-pricing markup, and recalibrating against real quoted costs reversed the result.

**The options-cost recalibration reversed the strategy economics; it does not establish or invalidate the separate attention-response hypothesis.** Those are two different claims about two different things, and the recalibration speaks only to the first. Instrument-first framing would have collapsed them into one and discarded an open question along with a dead expression. The attention-response hypothesis remains **open and untested prospectively** — that is what this project is built to test.

**Consequence:** an unavailable options benchmark lowers an event's completeness tier. It never removes an otherwise valid event from the core attention-versus-market-response cohort.

## 4. Current evidence versus unresolved questions

### What exists

- A retrospective reconstruction over a canonical n=152 event population.
- **A retrospective association was observed within that reconstruction** between GST z-score and earnings-adjacent realized price moves, independent of any options-pricing model. **That reconstruction has a failed point-in-time validity check and is not prospective confirmation.** The prospective study is designed to test the hypothesis it suggests.
- Production infrastructure: attention panel, cohort screening, registry, pre-event capture, dossier protocol, D1/D3 decomposition with canonical `abs_*` magnitudes, hypothesis registry, fail-closed display gates.
- One registered prospective event: `EVT-DELL-FY27Q2-ERN`.

### What is unresolved

- **Point-in-time validity.** Historical z-scores were reconstructed by querying Trends today for windows ending years earlier. Reproducible, but not provably what a live observer saw. The check is treated as **failed**, not waived.
- **Prospective confirmation.** Zero prospective outcomes analyzed. Zero frozen event IDs. `results: null`.
- **Surprise measurement.** HYP-02's fields exist in the dossier schema; no production path populates them and no join reaches a market-response event.
- **Attention decay.** HYP-03's measurement does not exist in any form.
- **Options data.** No cleared, timestamped, executable quote source.
- **Several preregistration elements.** Unresolved by design rather than by oversight — see the gap audit.

## 5. The five layers, and the walls between them

| Layer | Question | Governing artifact | May it change a confirmatory conclusion? |
|---|---|---|---|
| **Confirmatory** | HYP-01 | HYP-01 analysis lock | — it *is* the conclusion |
| **Secondary** | HYP-02; adjusted sensitivity models | hypothesis registry; lock §6 | **No** |
| **Exploratory** | HYP-03; localization; rank/sector variants | hypothesis registry; lock §7 | **No** |
| **Future product** | dashboards, radar, showcase repo | this document, §11 | **No** |
| **Future strategy** | any instrument, rule, or execution | **out of scope entirely** | **No** |

Information flows **forward only**. A later layer never feeds back into an earlier one. Secondary and exploratory results carry no independent confirmatory claim and can neither overturn nor rescue the primary result. Promotion to confirmatory requires a new dated registry version written *before* the results that would motivate it are seen.

## 6. Current confirmatory hypothesis — HYP-01, as locked

Reproduced from `Live Signal Engine/GST_HYP01_ANALYSIS_LOCK_v1.0.json`. **Not revised here.**

> **Does higher abnormal pre-earnings Google-search attention associate with a greater absolute overnight earnings response?**

| Element | Locked value |
|---|---|
| Predictor | `gst_zscore` — continuous, unthresholded, at the pre-event anchor session |
| Primary outcome | `abs_overnight_gap` = `abs(overnight_gap)`; `overnight_gap = next_session_open / previous_close - 1` |
| Primary model | `abs_overnight_gap ~ gst_zscore` (OLS) |
| Null | `beta_gst = 0`, two-sided |
| Alpha | `0.05` |
| Covariance | cluster-robust on `ticker`, finite-sample correction enabled |
| Reported | coefficient · 95% CI · p-value · eligible-event count · unique-ticker count |
| Sample | first **60** eligible events, ordered by derived response-session date then `event_id` |
| Sessions | `BMO`, `AMC` eligible; `INTRADAY` ineligible for this outcome |
| Wikipedia | **not** co-primary; cannot change the confirmatory conclusion |
| Current results | `null` · frozen event IDs `[]` · eligible events `0` |

## 7. Market-response localization framework

*Where* a response lands, expressed only in fields the production system already defines. **Exploratory** unless a component is named in a confirmatory lock.

| Window | Field(s) | Status |
|---|---|---|
| Pre-earnings drift | pre-event anchor snapshot vs. prior sessions | framework only; no locked outcome field |
| Overnight gap | `overnight_gap` / `abs_overnight_gap` | implemented; **HYP-01 primary outcome** |
| Open → 30 minutes | `open_to_30m` / `abs_open_to_30m` | implemented; exploratory |
| 30 minutes → close | `thirty_min_to_close` / `abs_thirty_min_to_close` | implemented; exploratory |
| Open → close | `open_to_close` / `abs_open_to_close` | implemented; exploratory |
| Later-session persistence | `close_T1_to_close_T2`, `close_T1_to_close_T3` and their `abs_*` | implemented; exploratory |
| Stock relative to sector | `derivations.relative_return` + `sector_mapping` | helper exists; **SPEC v0.1 lists these as optional and no capture path emits them yet** |
| Full-session range | `derivations.full_session_range` | helper exists; exploratory |

No new interval or formula is introduced by this document.

## 8. Candidate future equity applications — **all unvalidated**

Recorded so the research question stays visible, **not** as a plan of record. **None has been tested, backtested, prospectively evaluated, or validated. None may be described as working.**

| Candidate | What would have to be true first |
|---|---|
| Opening-range breakout | a confirmed, locked intraday localization result |
| Gap continuation or reversal | a confirmed directional result — HYP-01 measures **magnitude**, not direction |
| Attention–price divergence | a defined divergence measure; none is specified anywhere |
| Sector-neutral relative value | sector-relative fields actually emitted, plus a confirmed differential |
| Volatility / range regime selection | a confirmed relationship to realized range |
| Volume / liquidity forecasting | a confirmed relationship to volume, which no registered hypothesis tests |
| Portfolio risk controls | a confirmed relationship stable enough to size against |

## 9. Prohibition

**None of §8 may be called arbitrage, an edge, a working strategy, or profitable — before or after any result — until it has passed a test under a separate dated protocol, written before the data that test uses was examined** (see §10.4: an extension cohort is not automatically such a test).

A confirmatory HYP-01 result would establish an association between attention and response magnitude. It would **not** establish tradability, direction, execution feasibility, capacity, or profitability. Those are distinct claims requiring distinct evidence.

## 10. Development material, the confirmatory cohort, and the freeze

Three things are often collapsed into two. They are distinct, and the distinction is what makes the study preregistered rather than merely careful.

### 10.1 Development material

Synthetic fixtures · explicitly labelled historical and reconstructed artifacts · **no prospective outcomes, ever**.

This is what the code was built and debugged against. Iteration is free here, and it may inform methodology. It is *not* a holdout, was never treated as one, and no result computed on it is confirmatory.

### 10.2 The confirmatory evaluation cohort

The **first 60 eligible prospective events**.

These are **not development data at any point in their life.** Event 1 is governed by the pre-data HYP-01 lock exactly as event 60 is; the lock was written before any candidate was screened. Their outcomes remain **gated and unexamined** until the complete 60-event set *and* the analysis environment are frozen. An event does not become confirmatory at the freeze — it was confirmatory from the moment it was enrolled.

### 10.3 The event-60 freeze

The freeze records: the exact 60 event IDs · the analysis-code commit · the software environment · reproducibility metadata. Then all gates are verified, then the primary model runs **once**.

What the freeze does **not** do:

- It does **not** retroactively convert development material into holdout data. Nothing crosses that line, in either direction.
- It does **not** authorize changing the statistical rule. The rule must already be fixed — see the [gap audit](PREREGISTRATION_GAP_AUDIT_v1.0.md), items C6, C7, E3 and E8, all of which fall due **before the first prospective observation**, not at the freeze.
- It does **not** permit optional stopping, repeated testing, or a model change.

The freeze fixes *which events* and *which software*. It never fixes *which statistics* — that has to be settled earlier or the preregistration claim fails.

### 10.4 The extension cohort

Events becoming eligible after the frozen 60 are **separately labelled**. They never enlarge the frozen set and never re-open the primary analysis.

An extension cohort is **not automatically a formal holdout test.** It becomes one only if a **new dated protocol says so, written before those events' outcomes are examined.** Absent that document, extension events are additional observations with no confirmatory standing.

## 11. Four interfaces, deliberately separate

| Interface | Purpose | Status |
|---|---|---|
| **Research archive** (this repository) | append-only evidence, protocols, code, failures | **exists** |
| **Showcase repository** | a clean, reviewable presentation of method and results | **designed only — not created in this task** |
| **Public radar / dashboard** | live status, counts, gate state — never ungated results | **not built**; a separate DEMO fixture exists elsewhere and is not authoritative |
| **Paper** | the eventual written result | **not started** |

They stay separate so a presentation layer can never quietly become the source of truth, and so the archive is never edited to look better.

## 12. Success criteria that survive a null result

The project succeeds if it produces a **trustworthy answer**, not a positive one.

1. A prospective cohort assembled under rules fixed before any candidate was seen.
2. ≥ 60 eligible events, or an honest account of why not.
3. A HYP-01 result computed once, after a freeze, and reported with its confidence interval **whatever its sign**.
4. Every failure preserved, including the ones that make the project look worse.
5. Enough provenance that an outsider can reproduce the analysis from the repository alone.
6. A clear statement of what remains unresolved.

**A null or negative HYP-01 result is a successful outcome of this design.** The point-in-time failure, the straddle reversal, and two dead out-of-sample hypotheses are already evidence that this system reports against its own interest.

## 13. Governance rule

> **No attractive outcome may silently redefine the hypothesis, the outcome, the model, the sample, or the success criterion.**

Concretely: the predictor, outcome field, model formula, alpha, event ordering and sample size are locked *before* data exists. Unresolved analysis decisions are marked `PENDING_SEPARATE_ANALYSIS_LOCK` and resolved in a dated lock — never inferred from what the data turned out to look like. The **statistical decision rule** (estimator variant, finite-sample correction, multiplicity treatment) must be resolved **before the first prospective observation**, not merely before the freeze; see the [gap audit](PREREGISTRATION_GAP_AUDIT_v1.0.md). Any change is a new dated version that preserves the old one byte-for-byte and states plainly what changed and why.

If a result is attractive and a rule is inconvenient, **the rule wins.**
