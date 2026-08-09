# Changelog


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
