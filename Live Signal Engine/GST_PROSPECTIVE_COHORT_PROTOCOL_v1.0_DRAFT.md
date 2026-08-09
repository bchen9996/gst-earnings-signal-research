# GST Prospective Multi-Event Cohort Protocol — v1.0 (DRAFT)

**Status:** Draft, published **before any candidate investor-relations calendar has been inspected**. Authored 2026-08-08 (UTC).
**Canonical machine-readable form:** `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json` — that file and this one must agree; a mechanical test enforces it.
**Screening log schema:** `GST_PROSPECTIVE_COHORT_SCREENING_LOG_SCHEMA_v1.0.md`.

This protocol fixes **which earnings events enter the GST Market Attention Observatory**, and it does so before we know which events would qualify. That ordering is the whole point: rules written after seeing the candidates are not rules, they are choices.

**This is observational measurement infrastructure.** It does not test, optimise, select for, or claim any profitable trading strategy. It produces no return forecast, no signal ranking, and no buy or sell recommendation.

**Nothing here redefines existing methodology.** The completeness tiers, six-field core gate, D1/D3 interval formulas, option-benchmark validity thresholds, quote-age and skew limits, blinding rules and dossier layer separation all live in the documents referenced in §9 and in `gst_market_response/`, unchanged.

---

## 1. What this protocol prevents

| Failure mode | Prevented by |
|---|---|
| Cherry-picking companies | §2 — the universe is the production locked 24, read from code, exhaustively enrolled |
| Selecting an event because its GST/Wikipedia signal looks interesting | §5 INC-9 and §6 — attention data is a prohibited enrollment input |
| Excluding an event after seeing price movement | §7 — the prohibited-exclusion list, and dispositions being recorded not deleted |
| Quietly changing the cohort window | §3 — the window is immutable once any pre-event observation exists |
| Duplicate ticker-quarter enrollment | §5 INC-10 and the `EXCLUDED_DUPLICATE_TICKER_FISCAL_QUARTER` disposition |
| Retroactive outcome-driven amendments | §8 — append-only amendments, and no amendment may be motivated by collected data |

## 2. Universe — the production locked 24, unchanged

The cohort universe **is** `gst_market_response.constants.LOCKED_24_TICKER_UNIVERSE`. The JSON's ticker list is generated from that constant at authoring time and verified against it element-by-element by `test_market_response_cohort_protocol.py`. It is never retyped, reordered, extended or trimmed here.

No ticker may be added because it looks promising, and none may be dropped because it looks quiet.

## 3. Collection window

| | |
|---|---|
| Begins | **2026-09-01** |
| Ends | **2027-05-31** |
| Applied to | the **mechanically derived pre-event anchor session** — not the earnings date, not the registration date |
| Boundaries | inclusive on both ends |

The window is **immutable** once any pre-event observation exists for any cohort event. Changing it before that point requires a new protocol version with its own dated entry; it is never an in-place edit.

## 4. Target

**At least 60 independently registered events.** Enrollment is exhaustive over eligible events, so 60 is a floor describing intended coverage — it is **not** a stopping rule, and reaching it licenses no analysis. Falling short of it is reported as a coverage fact, never repaired by relaxing a rule.

## 5. Inclusion rules

An event is eligible **only if every one** of these holds:

| # | Rule | Mechanised by |
|---|---|---|
| INC-1 | The ticker is in the locked 24-ticker universe | `constants.is_locked_universe_member` |
| INC-2 | It is a regular quarterly or annual earnings release | — |
| INC-3 | The release date comes from an official company investor-relations source on the permitted list (§6) | — |
| INC-4 | That source explicitly establishes a calendar date | — |
| INC-5 | Release timing is explicit enough for the production registry to classify it **without inference** | `identity.determine_release_market_session` |
| INC-6 | The mechanically derived pre-event anchor falls inside the collection window | `operations_plan.build_operations_plan` |
| INC-7 | The event can be registered **at least 5 XNYS trading sessions** before its pre-event anchor | `exchange_calendar` |
| INC-8 | No pre-event snapshot has already been collected for the event | — |
| INC-9 | **No** GST, Wikipedia, price, volume, volatility, options, analyst-reaction, surprise or news-outcome data was inspected in deciding enrollment | §6 |
| INC-10 | No previously registered event exists for the same ticker and fiscal quarter | registry `read_all` |

The anchor and every session boundary come from the production calendar and the production planner. **This protocol reimplements no session arithmetic.**

## 6. Enrollment inputs — permitted and prohibited

**Permitted:** ticker identity · fiscal period label · official calendar date · official release-timing label · official source URL, title, type and retrieval time · the XNYS trading calendar · the existing registry contents.

**Prohibited:** `gst_zscore` · `wiki_zscore` · `price` · `previous_close` · `volume` · `realized_volatility` · `implied_volatility` · `panel_implied_volatility` · option chain or benchmark data · analyst reaction · earnings surprise · consensus estimates · news or media coverage · any market-response interval · any prior event's outcome.

Enrollment is a function of the permitted inputs **alone**. Inspecting a prohibited input before an enrollment decision **voids that decision**: the event is recorded `COMPROMISED_ENROLLMENT_BLINDING` and excluded from the confirmatory cohort. It is never silently re-enrolled, and the record is never deleted.

### 6.1 Permitted official-source types

`company_ir_events_calendar` · `company_ir_press_release` · `company_earnings_advisory_pr` · `sec_filing_8k_earnings_date`

Each must be published by the issuer (or filed by the issuer with the SEC) and **directly fetched or directly observed by a named human**. A search-engine snippet, an aggregator, a third-party calendar, a broker estimate, or the company's historical reporting cadence is **never** a source of record. The exact observed text, URL, retrieval timestamp and verifier identity are recorded in the registry row.

This allowlist is **additive and stricter** than production. Production requires a non-empty `event_time_source` and an explicit member of `VALID_RELEASE_SESSIONS` (`BMO`/`AMC`/`INTRADAY`); this list further restricts which source types the cohort accepts. It never weakens a production check.

## 7. Dispositions

Every screened candidate gets exactly one disposition, recorded in the screening log. **Nothing is dropped silently.**

| Code | Class | When |
|---|---|---|
| `ENROLLED` | included | every inclusion rule satisfied; registry row written |
| `PENDING_OFFICIAL_DATE_UNAVAILABLE` | pending | no official source yet establishes a calendar date |
| `PENDING_RELEASE_TIMING_AMBIGUOUS` | pending | date is official but timing is not explicit enough to classify without inference |
| `PENDING_SOURCE_REMOVED_OR_CONTRADICTED` | pending | a previously observed official source was withdrawn or is contradicted by another official source |
| `EXCLUDED_INSUFFICIENT_LEAD_TIME` | excluded | fewer than 5 XNYS sessions between earliest possible registration and the anchor |
| `EXCLUDED_DUPLICATE_TICKER_FISCAL_QUARTER` | excluded | a registered event already exists for this ticker and fiscal quarter |
| `EXCLUDED_OUTSIDE_COLLECTION_WINDOW` | excluded | derived anchor falls outside 2026-09-01…2027-05-31 |
| `EXCLUDED_NOT_A_NORMAL_EARNINGS_RELEASE` | excluded | cancellation, merger, delisting, or no longer a normal quarterly/annual release |
| `EXCLUDED_DISCOVERED_AFTER_ANCHOR` | excluded | discovered only after its anchor session began; it can no longer be enrolled blind |
| `AMENDED_TIMING_CHANGED_BEFORE_ANCHOR` | amended | issuer changed the official date/time **before** the anchor; anchor re-derived, window and lead-time rules re-applied |
| `COMPROMISED_TIMING_CHANGED_AFTER_ANCHOR` | compromised | issuer changed the official date/time **after** the anchor began; correction appended, event marked compromised and excluded from the confirmatory cohort, every collected byte preserved |
| `COMPROMISED_ENROLLMENT_BLINDING` | compromised | a prohibited input was inspected before the enrollment decision |

### 7.1 An event may NEVER be excluded because of

- low attention, high attention, or an interesting/uninteresting attention signal;
- missing or unavailable options data;
- an unfavourable market response, or a null one;
- a source failure occurring **after** valid registration;
- an expectation that the event will or will not produce an interesting result;
- any post-hoc judgement informed by collected data.

Once an event is validly registered, subsequent source trouble is a **data-quality fact about that event**, recorded and carried, not grounds for removing it from the cohort.

## 8. Amendments — append-only

Date/time corrections use the existing mechanism: `event_registry.HumanVerifiedEventRegistry.amend_event`, which appends a new `AMENDMENT` row referencing the original by `row_id`.

- The original registration's bytes are **never** overwritten, edited or deleted.
- The effective view folds amendments over the base row in order; the base row's own bytes remain exactly as first written.
- An amendment may correct a date, time, session label or source. It may **never** change the ticker, the fiscal quarter, or the fact that the event was enrolled.
- **No amendment may be motivated by collected attention or market-response data.**

## 9. Analysis separation

Information flows forward only. A later stage never feeds back into an earlier one.

| Stage | Decides | May read |
|---|---|---|
| 1 · Cohort enrollment | which events enter the study | official IR sources, XNYS calendar, existing registry — **nothing else** |
| 2 · Pre-event measurement | the blind pre-event observation | SPEC v0.2 §2 and §7; strict six-field core gate |
| 3 · Post-event response measurement | D1 and D3 intervals | SPEC v0.1 interval definitions, unchanged |
| 4 · Hypothesis eligibility | which families an event may inform | `completeness.is_eligible_for_hypothesis` |
| 5 · Future trading-strategy research | — | **OUT OF SCOPE.** No stage of this protocol produces, evaluates or implies a trading rule. |

Referenced and **not** redefined here: `GST_Earnings_Market_Response_Decomposition_SPEC_v0.2_DRAFT.md`, `GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.2.md`, the v0.1 SPEC's interval definitions, `Event_Dossier_Protocol/EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md`, and `gst_market_response.completeness`.

## 10. Options availability does not gate cohort membership

An absent verified options benchmark may lower an event to `core_only_no_option_benchmark`. It **never** removes an otherwise valid event from the core attention-versus-market-response cohort.

A core-only event remains eligible for `core_attention_vs_equity_response` and ineligible for `options_implied_move` and `joint_attention_plus_options` — exactly as SPEC v0.2 §1 already specifies. An unavailable benchmark stays null; it never becomes zero and never authorises an indicative substitute.

## 11. Display gate

**No hypothesis result may be displayed, summarised, plotted or informally described before that hypothesis's own registered sample-size threshold is reached.**

The governing rule already exists: `GST_Phase2_InformationArrivalPanel_SPEC_DRAFT.md` §3 requires a pre-set minimum sample size *decided now, not adjusted later*, with each hypothesis carrying its own dated pre-registration file.

**No numeric per-hypothesis threshold is currently registered for the market-response families.** This protocol deliberately does **not** invent one — choosing that number is a separate, dated pre-registration decision, and setting it here, in the same document that defines the cohort, is exactly the coupling the governance rule exists to prevent. Until a threshold is registered for a family, **the gate denies display for that family**. Absence of a registered number is never read as absence of a gate.

## 12. Existing provenance — DELL FY2027 Q2

`EVT-DELL-FY27Q2-ERN` (row `EVT-DELL-FY27Q2-ERN-REG-001`) was registered before any pre-event observation existed and satisfies these same rules. It is the first prospective event by chronology only: **no special treatment, no exemption, no priority.** Its registry blob is `71681aa4…f4974` and is untouched by this protocol.

## 13. No candidates yet

This document contains **no screening rows**, and the JSON's `screening_rows` array is deliberately empty. Publishing the rules first is what makes the later screening a test rather than a selection.
