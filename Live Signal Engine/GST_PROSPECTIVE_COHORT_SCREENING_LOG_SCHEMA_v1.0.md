# GST Prospective Cohort — Screening Log Schema v1.0

Companion to `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md` and its canonical JSON.

This document defines the **shape** of the screening log. **It contains no screening rows**, and none may be written until screening is separately authorised — the schema is published before the data so the columns cannot be shaped by what the candidates turn out to be.

---

## 1. File

| | |
|---|---|
| Path | `Live Signal Engine/Market_Response_Event_Registry/cohort_screening_log.jsonl` |
| Format | JSON Lines, one screening decision per line, UTF-8, LF |
| Discipline | **Append-only.** A row's bytes are never rewritten or deleted. A correction is a new row with `supersedes_row_id` set. |
| Relationship to the registry | Separate file. The screening log records *decisions about candidates*; `registry.jsonl` records *human-verified registrations*. An `ENROLLED` decision must reference the registry row it produced. |

The screening log is **not** a research artifact. It carries no attention, price, options or outcome value, and the schema below provides no field in which one could be recorded.

## 2. Required fields — every row

| Field | Type | Notes |
|---|---|---|
| `screening_row_id` | string | `SCR-{ticker}-{fiscal_period}-{seq:03d}`, unique |
| `screened_at_utc` | ISO-8601 UTC | when the decision was recorded |
| `screened_by` | string | named human responsible |
| `protocol_version` | string | `1.0` |
| `ticker` | string | must be in the locked 24-ticker universe |
| `fiscal_period` | string | e.g. `FY27Q2`; the ticker + fiscal_period pair is the duplicate key |
| `disposition` | enum | one of the twelve codes in protocol §7 |
| `disposition_class` | enum | `included` \| `pending` \| `excluded` \| `amended` \| `compromised` |
| `disposition_reason` | string | nonblank; free text explaining the decision in terms of the rules |
| `inclusion_rules_evaluated` | object | `{"INC-1": true, … "INC-10": false}` — every rule explicitly true/false, never omitted |
| `prohibited_inputs_inspected` | array | **must be empty** for any `ENROLLED` row |
| `supersedes_row_id` | string\|null | set only when correcting an earlier screening row |

## 3. Conditional fields

| Field | Required when | Notes |
|---|---|---|
| `official_source_url` | any disposition other than `PENDING_OFFICIAL_DATE_UNAVAILABLE` | issuer-published or issuer-filed |
| `official_source_type` | as above | must be on the permitted list (protocol §6.1) |
| `official_source_title` | as above | as displayed |
| `official_source_retrieved_at_utc` | as above | when the human observed it |
| `official_observed_text` | as above | the exact date/time text observed, quoted |
| `official_release_date` | date is established | calendar date as stated |
| `official_release_timing_label` | timing is explicit | `BMO` \| `AMC` \| `INTRADAY` |
| `derived_pre_event_anchor` | an anchor could be derived | from `operations_plan.build_operations_plan`, never computed here |
| `lead_trading_sessions` | an anchor could be derived | XNYS sessions between screening and the anchor |
| `event_id` | `disposition == "ENROLLED"` | must match `^EVT-[A-Z0-9-]+-FY\d{2}Q\d-[A-Z]+$` |
| `registry_row_id` | `disposition == "ENROLLED"` | the `REGISTRATION` row this decision produced |
| `amends_registry_row_id` | `disposition_class == "amended"` | the `AMENDMENT` row appended |
| `compromise_detail` | `disposition_class == "compromised"` | what was breached and when |

## 4. Fields that may never exist

No column may be added for, and no row may record, any of:

`gst_zscore` · `wiki_zscore` · `price` · `previous_close` · `volume` · `realized_volatility` · `implied_volatility` · `panel_implied_volatility` · any option chain, quote or benchmark field · analyst reaction · earnings surprise · consensus estimate · news or media coverage · any market-response interval · any prior event's outcome · any expected-interestingness score.

A screening log that carries such a field is invalid on its face, regardless of the values in it.

## 5. Validation rules

1. `screening_row_id` is unique across the file.
2. `(ticker, fiscal_period)` may appear more than once **only** when later rows set `supersedes_row_id`, or when an earlier row was `pending` and a later row resolves it.
3. At most **one** `ENROLLED` row per `(ticker, fiscal_period)` — this is the duplicate-enrollment gate.
4. `ticker` is a member of the production locked universe.
5. `disposition` and `disposition_class` are consistent with protocol §7.
6. Every `INC-1`…`INC-10` key is present in `inclusion_rules_evaluated`.
7. An `ENROLLED` row has all ten inclusion rules `true`, an empty `prohibited_inputs_inspected`, and both `event_id` and `registry_row_id` set.
8. A non-`ENROLLED` row has at least one inclusion rule `false` **or** a `pending`/`amended`/`compromised` class.
9. `disposition_reason` is nonblank and does not cite any prohibited exclusion reason (protocol §7.1).
10. No row contains any field named in §4.
11. Rows are strictly append-only: an existing row's bytes never change.

## 6. Relationship to the event registry

An `ENROLLED` screening row is a **precondition** for, not a substitute for, a registry row. Registration still runs through `HumanVerifiedEventRegistry.register_verified_event` with its own human verification, and date/time corrections still append `AMENDMENT` rows there. The screening log records *why an event was or was not put forward*; the registry records *what was verified*.

## 7. No rows yet

Zero screening rows exist. None may be written until candidate screening is separately authorised.
