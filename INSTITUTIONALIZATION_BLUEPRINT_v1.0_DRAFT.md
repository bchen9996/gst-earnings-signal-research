# Institutionalization Blueprint — v1.0 (DRAFT)

**Status:** Draft. Planning only. **No methodology changes here.** Nothing in this document is authorized by writing it down; each stage names the human approval it needs.

**Nothing external is obtained.** OSF, Zenodo, WRDS, OptionMetrics, Cboe, a Google Trends API entitlement, reviewers, partners and external datasets are **proposed future dependencies**, not acquisitions. Where a stage says "requires", it means *does not currently have*.

**Anti-duplication rule.** Several stages are already partly built. Each stage below states what **exists** so no one rebuilds it.

**Two deadlines, not one.** These are distinct and are routinely confused:

| Deadline | Date | Governs |
|---|---|---|
| Next screening sweep | **Monday 2026-08-10, 09:00 America/Chicago** | Stage 1 only. Analyzes no outcome, and discharges no decision below. |
| Statistical-rule deadline | **Before the first prospective HYP-01 pre-event capture** | Stages 3, 4, 6 and 14 — the estimator, inference procedure, multiplicity treatment, development boundary and construct validity. **Not** the event-60 freeze. |

---

## Stage 1 — Prospective cohort acquisition

| | |
|---|---|
| **Objective** | Assemble ≥ 60 eligible events under rules fixed before any candidate was seen. |
| **Current status** | **Underway.** 1 registered event; round-1 reconnaissance complete with 0 enrollable candidates found. |
| **Existing evidence** | Cohort protocol v1.1 (window 2026-09-01 → 2027-05-31, 5-session lead, Monday 09:00 America/Chicago cadence); round-1 sweep manifest, correction overlay, evidence audit, human-review queue, round-2 renderer runbook; `registry.jsonl`. |
| **Missing dependency** | A renderer pass for the 9 client-rendered calendars; a located events calendar for 2 discovery-gap tickers; a human verifier for any candidate found. |
| **Next authorized action** | The scheduled Monday 2026-08-10 09:00 America/Chicago sweep, per the existing runbook. **Nothing earlier.** |
| **Deliverable** | Round-2 sweep manifest + human-review queue. |
| **Acceptance** | Every locked ticker appears exactly once; every evidence URL is issuer or SEC; no `ENROLLED` row without named human verification. |
| **Methodology-change risk** | **Low** if the runbook is followed; **high** if a candidate is forced into a disposition the schema cannot represent. |
| **Human approval** | Already granted for the scheduled cadence. A *new* approval is required for any off-cadence sweep. |

## Stage 2 — Point-in-time prediction / evidence ledger

| | |
|---|---|
| **Objective** | Record what was observable *at the time*, so a future claim is not another reconstruction. |
| **Current status** | **Partially exists.** The pre-event capture path already records retrieval timestamps, panel CSV/marker SHA-256s, `run_date`, `price_asof_date`, commit SHA and methodology version, with a TOCTOU-closed validate-then-write and immutable stage markers. |
| **Existing evidence** | Strict v0.2 core gate; 15-field provenance block; capture fingerprint; immutable `PRE_EVENT_CAPTURE` / `D1_CAPTURE` / `FINAL_COMPLETION` markers. |
| **Missing dependency** | The project's central unresolved flaw — the **historical** population is a reconstruction. This stage fixes it *going forward only*; it cannot retroactively repair n=152. |
| **Next authorized action** | None beyond running the existing capture path at the DELL anchor when authorized. |
| **Deliverable** | A prospective ledger whose every row has a real capture timestamp. |
| **Acceptance** | No prospective row exists without provenance; no historical value is ever back-filled into it. |
| **Methodology-change risk** | **Low** — infrastructure exists and is tested. |
| **Human approval** | Required to run the first real pre-event capture. |

## Stage 3 — Formal external preregistration

| | |
|---|---|
| **Objective** | Place the locked hypothesis on an external, timestamped, immutable registry. |
| **Current status** | **Internal only.** HYP-01 is locked in-repository with a git history; nothing is externally registered. |
| **Existing evidence** | Hypothesis registry v1.0, HYP-01 analysis lock v1.0, display gates, eligibility & freeze rules. |
| **Missing dependency** | An external registry account (OSF or equivalent) — **not obtained**. Plus the gap audit's **11 scientific decisions**, of which **C6, C7, E3 and E8 must be settled before this stage can honestly proceed**. |
| **Next authorized action** | Resolve those gap-audit decisions. **Do not register a preregistration containing invented values, and do not file one while the primary estimator and inference procedure are still open.** |
| **Deliverable** | An external preregistration mirroring the internal lock exactly. |
| **Acceptance** | External record is timestamped **before the first eligible prospective observation** and matches the internal lock field-for-field, with no element left as "to be decided later". |
| **Methodology-change risk** | **High** — the act of writing an external preregistration tempts resolution of open items by guessing. |
| **Human approval** | **Required**, and a methodologist should review before submission. |
| **Deadline** | Before the first prospective HYP-01 pre-event capture. **Not** the event-60 freeze. |

## Stage 4 — Search-construct validity audit

| | |
|---|---|
| **Objective** | Establish that the GST query measures *attention to the company*, not an unrelated homonym or a shifting Google construct. |
| **Current status** | **Not started as a formal audit.** Ticker-level query construction exists in the panel; its construct validity has not been separately audited. |
| **Existing evidence** | Panel implementation; the documented Trends transport failures and revision behaviour. |
| **Missing dependency** | A documented mapping from ticker → query term, a homonym/ambiguity review (e.g. `GME`, `STZ`, `BKR`), and evidence on Trends' own revision behaviour. |
| **Next authorized action** | Offline review of the existing query construction. **No new Trends calls.** |
| **Deliverable** | A construct-validity memo, per ticker. |
| **Acceptance** | Every ticker's query term is justified and its ambiguity risk stated. |
| **Methodology-change risk** | **High** — changing a query term changes the signal. Any change must be a dated methodology version, never a silent edit. |
| **Human approval** | **Required** for any query-term change. |
| **Deadline** | This stage is gap-audit **F5**: **before the first prospective HYP-01 observation.** A query term cannot be revised once observations are being collected against it. |

## Stage 5 — Institutional options / market-data access

| | |
|---|---|
| **Objective** | Obtain a timestamped, executable, verified options and market-data source. |
| **Current status** | **Blocked.** No cleared source. The capture CLI **refuses** `VALID_VERIFIED` outright, because nothing in the tool can authenticate provider identity, endpoint, response hash, contracts, strike, expiration, per-leg quote timestamps, quote age, skew, or a recomputed benchmark. An earlier Alpaca entitlement diagnostic returned **INCONCLUSIVE**. |
| **Existing evidence** | Option-benchmark validity thresholds, quote-age and skew limits, explicit disposition contract, `DENY_NO_REGISTERED_HYPOTHESIS` on both options classes. |
| **Missing dependency** | WRDS / OptionMetrics / Cboe or an equivalent entitlement — **none obtained**; plus a documented threat model for accepting a provider artifact. |
| **Next authorized action** | None. This is an institutional-access question, not an engineering one. |
| **Deliverable** | A cleared provider artifact specification, then an implementation. |
| **Acceptance** | A benchmark can be independently recomputed from stored raw quotes with per-leg timestamps. |
| **Methodology-change risk** | **Very high** — this is precisely where the original project went wrong by substituting synthetic pricing. |
| **Human approval** | **Required**, plus Stage 7 review before any options hypothesis is registered. |

## Stage 6 — External econometrics review

| | |
|---|---|
| **Objective** | Have the identification strategy and error structure reviewed by someone outside the project. |
| **Current status** | **Not started.** |
| **Existing evidence** | HYP-01 lock (OLS, ticker-clustered, finite-sample corrected, two-sided α = 0.05, n ≥ 60); counting rules; multiplicity noted as unresolved. |
| **Missing dependency** | A reviewer — **none engaged**. Faculty supervision exists but is not an external review. |
| **Next authorized action** | Prepare a review packet from existing artifacts, centred on gap-audit **C6, C7 and E3**. |
| **Deliverable** | A written review with findings. |
| **Acceptance** | Findings are recorded and either adopted in a dated version or explicitly declined with reasons. |
| **Methodology-change risk** | **High** — review may recommend a different estimator or error structure. Adopting one must happen **before the first prospective observation**; adopting one after the freeze is prohibited outright, and adopting one after observations begin would forfeit the preregistration claim. |
| **Human approval** | **Required**. |
| **Deadline** | This stage gates C6 and C7, so it must complete **before the first prospective HYP-01 observation**. |

## Stage 7 — External options / execution review

| | |
|---|---|
| **Objective** | Have any future options or execution claim reviewed by a practitioner. |
| **Current status** | **Not started, and not yet applicable** — no options hypothesis is registered. |
| **Existing evidence** | The straddle-economics reversal is the concrete case for why this stage exists. |
| **Missing dependency** | Stage 5, plus a reviewer — **none engaged**. |
| **Next authorized action** | None until Stage 5 resolves. |
| **Deliverable** | A written execution-feasibility review. |
| **Acceptance** | Slippage, spread, capacity and borrow are addressed with real quotes. |
| **Methodology-change risk** | **Very high.** |
| **Human approval** | **Required**. |

## Stage 8 — Engineering reliability review

| | |
|---|---|
| **Objective** | Confirm the capture and evidence path cannot silently corrupt or lose data. |
| **Current status** | **Substantially exists.** Two CI workflows; a large deterministic suite; sockets-blocked runs; clean-LF archive verification; append-only stores; immutable write-once markers via exclusive create; TOCTOU-closed capture; a differential harness proving each correction is load-bearing. |
| **Existing evidence** | `.github/workflows/`; the market-response, Phase 2 and Event Dossier suites; the second-pass differential harness. |
| **Missing dependency** | An external reviewer; a documented restore-from-scratch drill. |
| **Next authorized action** | Offline reliability write-up from existing tests. **Do not add CI triggers merely to produce green badges.** |
| **Deliverable** | A reliability memo plus a restore drill. |
| **Acceptance** | A clean clone reproduces every deterministic suite with sockets blocked. |
| **Methodology-change risk** | **Low.** |
| **Human approval** | Not required for the write-up. |

## Stage 9 — Public red-team challenge

| | |
|---|---|
| **Objective** | Invite outsiders to break the claims and the infrastructure. |
| **Current status** | **Not started.** |
| **Existing evidence** | Public repository; preserved failures; correction overlays. |
| **Missing dependency** | A stable public presentation (Stage 12) and a published result worth attacking. |
| **Next authorized action** | None until a result exists. |
| **Deliverable** | A challenge brief and a log of submissions with dispositions. |
| **Acceptance** | Every submission is answered in public, including the ones that land. |
| **Methodology-change risk** | **Medium** — post-hoc changes in response to criticism must be dated versions, never silent edits. |
| **Human approval** | **Required**. |

## Stage 10 — Independent replication

| | |
|---|---|
| **Objective** | Have a third party reproduce the analysis from the repository alone. |
| **Current status** | **Not started.** |
| **Existing evidence** | Deterministic suites; pinned dependency files; frozen commit SHAs; the analysis-lock environment-freeze block. |
| **Missing dependency** | A replicator; a frozen result to replicate; a resolved data-access path for anything not in-repo. |
| **Next authorized action** | None until after the first freeze. |
| **Deliverable** | A replication report. |
| **Acceptance** | Independent reproduction of the coefficient, CI and p-value from the frozen inputs. |
| **Methodology-change risk** | **Low** post-freeze. |
| **Human approval** | **Required** to share any unpublished frozen result. |

## Stage 11 — Stable DOI-backed release

| | |
|---|---|
| **Objective** | Give the archive a citable, immutable identifier. |
| **Current status** | **Not started.** |
| **Existing evidence** | Git history; append-only artifacts; hash-locked evidence. |
| **Missing dependency** | A Zenodo (or equivalent) deposit — **not obtained**. |
| **Next authorized action** | None until a release is worth citing. |
| **Deliverable** | A DOI-backed archival snapshot. |
| **Acceptance** | The DOI resolves to an immutable snapshot whose hashes match the repository. |
| **Methodology-change risk** | **None.** |
| **Human approval** | **Required.** |

## Stage 12 — Public dashboard / radar

| | |
|---|---|
| **Objective** | Show progress publicly without leaking a gated result. |
| **Current status** | **Not built here.** A separate DEMO-fixture dashboard exists outside this repository; it ships development-pilot fixtures only, has no live pipeline, and **is not authoritative**. |
| **Existing evidence** | Display gates (all currently **CLOSED**); the rule that eligible-event *count* is not a result. |
| **Missing dependency** | A read-only feed from the archive; a hard guarantee that no ungated estimate can render. |
| **Next authorized action** | Design only. Do not connect a live feed. |
| **Deliverable** | A dashboard spec whose default state is DENY. |
| **Acceptance** | No effect estimate, direction, interim p-value or plot can render before a freeze. |
| **Methodology-change risk** | **Medium** — a dashboard is the most likely place for an interim peek to leak. |
| **Human approval** | **Required** before any public deployment. |

## Stage 13 — Prospective forecasting tournament

| | |
|---|---|
| **Objective** | Convert the signal into dated, scored, public forecasts. |
| **Current status** | **Not started.** |
| **Existing evidence** | Registry and cadence infrastructure that could carry dated forecasts. |
| **Missing dependency** | A confirmed HYP-01 result; a scoring rule locked in advance; a rule preventing forecasts from contaminating the confirmatory sample. |
| **Next authorized action** | None. |
| **Deliverable** | A tournament protocol with a pre-locked scoring rule. |
| **Acceptance** | Forecasts are timestamped before outcomes and scored by the pre-locked rule. |
| **Methodology-change risk** | **High** — a tournament is a strategy claim in disguise if not walled off. |
| **Human approval** | **Required**. |

## Stage 14 — Development material / confirmatory-cohort boundary

*This is gap-audit item **E8**. Vocabulary follows [North Star §10](PROJECT_NORTH_STAR_v1.0_DRAFT.md).*

| | |
|---|---|
| **Objective** | Guarantee that the material used to build the system is never the material used to test the locked claim. |
| **Current status** | **Partially exists.** The freeze procedure, extension-cohort rule, no-optional-stopping rule and no-model-change-after-freeze rule are all locked. |
| **Existing evidence** | HYP-01 eligibility & freeze rules; counting rules CNT-1…CNT-10; display gates. |
| **Missing dependency** | An explicit dated statement of which *retrospective* artifacts may inform development without contaminating the **confirmatory evaluation cohort** — currently implicit. |
| **Next authorized action** | Write that boundary down as a dated document. |
| **Deliverable** | A development-material / confirmatory-cohort boundary statement. |
| **Acceptance** | Every artifact is labelled **development material** or **confirmatory cohort**; no confirmatory-cohort outcome informs a methodology choice; the first 60 prospective events are never labelled development material; an extension cohort is not labelled a formal holdout test absent a new dated protocol. |
| **Methodology-change risk** | **Medium** — writing it down may reveal that a past choice was informed by data now inside the confirmatory cohort. If so, say so. |
| **Human approval** | **Required** if any contamination is found. |
| **Deadline** | **Before external preregistration and before the first prospective HYP-01 observation** — not at the event-60 freeze. |

---

## What already exists — do not rebuild

Append-only registry and event store · immutable stage markers with exclusive-create semantics · TOCTOU-closed pre-event capture · strict six-field v0.2 core gate with per-leg statuses · canonical `abs_*` response persistence · cohort protocol with fixed cadence · hypothesis registry with fail-closed display gates · HYP-01 analysis lock with freeze procedure · Event Dossier Protocol with blinding and capture-vs-reveal · two CI workflows and a large deterministic suite · preserved failure evidence and correction overlays.

## Dependency order

```
Stage 1 (cohort)  ──┬──> Stage 2 (point-in-time ledger) ──> Stage 14 (dev/holdout) ──> Stage 10 (replication)
                    │
Stage 4 (construct) ┘
Stage 3 (external prereg)  <── gap audit resolution  <── Stage 6 (econometrics review)
Stage 5 (options access) ──> Stage 7 (execution review) ──> [any options hypothesis]
Stage 8 (reliability) ── independent of the science
Stages 9, 11, 12, 13 ── all require a frozen result first
```

**Nothing downstream of a frozen result may begin before that freeze.**
