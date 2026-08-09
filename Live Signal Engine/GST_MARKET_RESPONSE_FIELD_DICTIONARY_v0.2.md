# GST Market Response Field Dictionary — v0.2

Companion to `GST_Earnings_Market_Response_Decomposition_SPEC_v0.2_DRAFT.md`.
**Supersedes** `GST_MARKET_RESPONSE_FIELD_DICTIONARY_v0.1.md`, which is preserved **byte-for-byte** and remains authoritative for every field v0.2 does not restate. Methodology identifier: **`market_response_v0.2`**.

This document covers **only what the v0.2 amendment adds or changes**. Everything else — the option-benchmark fields, D1/D3 interval fields, provider fields, sector mapping, registry schema, Phase 2 adapter mapping — is unchanged and lives in v0.1.

---

## 1. Module-eligibility fields (new)

Recorded on the pre-event state record and echoed in every stage marker.

| Field | Type | Required | Notes |
|---|---|---|---|
| `core_pre_event_eligible` | bool | yes | The existing pre-event core gate passed. |
| `option_benchmark_eligible` | bool | yes | The existing option gate passed **and** the disposition is `VALID_VERIFIED`. |
| `joint_full_eligible` | bool | yes | `core_pre_event_eligible AND option_benchmark_eligible`. |
| `pre_event_completeness_tier` | enum | yes | `core_invalid` \| `core_only_no_option_benchmark` \| `core_and_option_benchmark`. |
| `option_benchmark_status` | enum | yes | See §2. |
| `option_benchmark_unavailable_reason` | string | conditional | Required and nonblank for every non-`VALID_VERIFIED` disposition. |
| `protocol_version` | string | yes | `0.2`. |

**Only `core_and_option_benchmark` may ever be described as full-data complete.** A pre-amendment (v0.1) record carries none of these fields and raises `LegacyRecordError` on read — it is never silently reinterpreted.

## 2. `option_benchmark_status` (new enum)

| Value | Requires | Analytically eligible |
|---|---|---|
| `VALID_VERIFIED` | `option_feed` ∈ {`opra`} **and** `is_valid_option_benchmark()` passes | **yes** |
| `UNAVAILABLE_NO_VERIFIED_SOURCE` | all benchmark values null + nonblank reason | no |
| `LOOKUP_FAILED` | failure provenance + all benchmark values null | no |
| `NOT_ATTEMPTED` | nonblank reason for not attempting | no |

Unknown/blank fails closed. Unavailability is **never inferred** from `{}` or nulls. Indicative quotes may be neither promoted to `VALID_VERIFIED` nor relabelled as unavailable. `VALID_VERIFIED` is **refused outright by the pre-event capture CLI** until a separately cleared provider artifact exists (SPEC v0.2 §3).

| Field | Type | Notes |
|---|---|---|
| `option_feed` | string | Provider identity. Only `opra` is an accepted verified feed. |

## 3. Strict six-field core (new gate)

`evaluate_strict_core_v0_2()` — required by the pre-event capture orchestrator. The v0.1 gate is unchanged and still used by the legacy path.

| Strict-core field | Panel column | Status consulted | Notes |
|---|---|---|---|
| `gst_zscore` | `gst_status` | `source_status_gst` | |
| `wiki_zscore` | `wiki_status` | `source_status_wiki` | |
| `panel_implied_volatility` | `iv_status` | `source_status_iv` | See §3.1 — **not** an implied-move value. |
| `realized_volatility` | `realized_vol_status` | `source_status_realized_vol` | |
| `previous_close` | `price_history_status` | `source_status_price` | The protocol's canonical price field. |
| `volume` | `price_history_status` | `source_status_price` | Same leg as `previous_close`. |

Successful statuses: `ok`, `ok_recent_cache_fallback`. Also required: `pre_event_snapshot_asof_utc`.

Null fails · non-success status fails · unknown or absent status fails closed · **a legitimate `0.0` with a successful status passes**. Missingness is never inferred from zero.

### 3.0 Per-leg statuses (new fields)

| Field | Type | Notes |
|---|---|---|
| `source_status_iv` | enum | Normalised `iv_status`. Default `missing` — fail-closed, never a success. |
| `source_status_iv_raw` | string | The exact Phase 2 `iv_status` string. |
| `source_status_realized_vol` | enum | Normalised `realized_vol_status`. Default `missing`. |
| `source_status_realized_vol_raw` | string | The exact Phase 2 `realized_vol_status` string. |

The Phase 2 panel emits five independent per-leg statuses. IV and realized volatility previously inherited `source_status_price`, so a failed option-chain or realized-vol lookup passed the six-field gate whenever price history happened to be OK. Each field is now backed by the leg that produced it. Normalisation is unchanged: `ok` → `ok`, `complete_recent_cache_fallback` → `ok_recent_cache_fallback`, blank → `missing`, anything else → `error`.

### 3.1 `panel_implied_volatility` (new, deliberately namespaced)

| Field | Type | Notes |
|---|---|---|
| `panel_implied_volatility` | float\|null | The Phase 2 panel's generic IV, persisted **only** as six-field completeness provenance. |

The v0.1 dictionary states `implied_volatility` is "never imported anywhere" because SPEC §5 forbids using panel IV as an earnings-implied-move baseline. **That prohibition is unchanged.** v0.2 persists the value under a distinct name so the six-field contract can be verified end to end; it is never exposed as `implied_volatility`, never fed to the option benchmark, and never usable as an implied-move value. `option_chain_adapter` remains the only legitimate source for any implied-move-shaped field.

## 4. Authoritative session fields

| Field | Type | Notes |
|---|---|---|
| `price_asof_date` | date | **Authoritative anchor field.** The session the price data is as-of; the pre-event anchor must equal this. |
| `run_date` | date | The calendar date the panel process ran. Persisted as provenance; `run_date >= price_asof_date` is asserted. |

These legitimately differ (real run: `run_date=2026-07-30`, `price_asof_date=2026-07-29`). The anchor is **never** derived from `run_date` or from a truncated `retrieval_timestamp_utc`. Missing column, blank value, or disagreement across rows → fail closed.

## 4.1 Date-audit fields (new)

Recorded on the `ValidationReport` as `panel_date_audit`, so a report shows the state of **every** row rather than only the resolved value.

| Field | Type | Notes |
|---|---|---|
| `row_count` | int | Rows in the panel. |
| `blank_price_asof_rows` | int | Must be `0`. A blank is never discarded. |
| `blank_run_date_rows` | int | Must be `0`. |
| `distinct_price_asof` | list | Must have exactly one entry. |
| `distinct_run_date` | list | Must have exactly one entry. |
| `problems` | list | Empty when the audit passes. |

Named checks: `panel_price_asof_date_nonblank_in_every_row` · `panel_price_asof_date_single_value_across_rows` · `panel_run_date_nonblank_in_every_row` · `panel_run_date_single_value_across_rows` · `run_date_not_before_session` · `panel_is_anchor_session`.

## 4.2 Capture fingerprint (new)

| Field | Type | Notes |
|---|---|---|
| `capture_fingerprint` | object | Persisted on the `PRE_EVENT_PENDING` record; echoed on the report. |
| `capture_fingerprint.capture_fingerprint_version` | string | `1`. Covered by the self-digest, so versions can never cross-match. |
| `capture_fingerprint.option_fields_digest` | string | SHA-256 of the canonicalised complete option artifact. |
| `capture_fingerprint.capture_fingerprint_sha256` | string | Self-digest over exactly the covered fields. |
| `option_fields_digest` | string | Same digest, stored on the `ValidationReport` for the execution-time binding. |

Covered fields: `capture_fingerprint_version` · `event_id` · `ticker` · `anchor_session` · `panel_csv_sha256` · `panel_marker_sha256` · `research_commit_sha` · `methodology_version` · `option_fields_digest`. Canonicalisation is sorted-key, separator-normalised JSON, so key ordering never changes a digest. See SPEC v0.2 §3 and §6.2.

## 4.3 `failure_stage` (new, on every v0.2 `PARTIAL`)

| Field | Type | Notes |
|---|---|---|
| `failure_stage` | enum | `pre_event` \| `d1` \| `d3`. Which stage produced this `PARTIAL`. |

Legacy `PARTIAL` records carry no such field; their stage is derived from the preceding pending state, never defaulted. An unrecognised value resolves to no stage. See SPEC v0.2 §8.1.

## 4.4 Absolute response fields — now emitted (new)

SPEC v0.1 has always required an `abs_*` counterpart for each signed response interval: "`abs()` of the corresponding signed return, stored alongside it (never replacing it)". Until the canonical absolute-response persistence commit, **no capture path emitted them**. They are now derived and stored by production.

| Signed field | Absolute counterpart | Stage |
|---|---|---|
| `overnight_gap` | `abs_overnight_gap` | D1 |
| `open_to_30m` | `abs_open_to_30m` | D1 |
| `thirty_min_to_close` | `abs_thirty_min_to_close` | D1 |
| `open_to_close` | `abs_open_to_close` | D1 |
| `close_T1_to_close_T2` | `abs_close_T1_to_close_T2` | D3 |
| `close_T1_to_close_T3` | `abs_close_T1_to_close_T3` | D3 |

Derived by `pipeline.capture_d1()` / `capture_d3()` through `response_magnitude.apply_absolute_fields()`, which applies `derivations.abs_or_none()` — the single definition of `abs()` in the package. No signed-return formula is recomputed anywhere.

**Stored alongside, never replacing.** The signed values remain present and unchanged. A signed `0.0` yields `0.0`; a missing signed value yields `null`, never `0.0`. No imputation, winsorization, clipping, rounding or outlier removal.

**Not a completeness requirement.** `D1_REQUIRED_FIELDS` and `D3_REQUIRED_FIELDS` are unchanged. These are canonical derived **outputs**: a record is neither made complete nor made incomplete by their presence.

**Callers do not choose them.** The pipeline derives them. A caller-supplied `abs_*` value is accepted only when it exactly equals the canonical value; otherwise `response_magnitude.AbsoluteFieldConflictError` is raised **before the first event-log or marker byte is written** — not even the `D1_PENDING`/`D3_PENDING` record.

**Where they land.** The durable D1/D3 state record, plus a `response_magnitude` block in the `D1_CAPTURE` and `FINAL_COMPLETION` stage markers and in the legacy `{event_id}_COMPLETION_MARKER.json`. Marker tie-out covers the block, so recovery detects drift in it.

**No backfill.** Records written before this commit carry no `abs_*` fields and were not rewritten. They are transparently ineligible for analyses requiring them.

## 5. Persisted provenance (echoed in every stage marker)

`ticker` · `source_csv_path` · `source_csv_sha256` · `source_marker_path` · `source_marker_sha256` · `panel_status` · `panel_row_count` · `panel_unique_ticker_count` · `panel_all_six_fields_clean_count` · `run_date` · `price_asof_date` · `pre_event_snapshot_asof_utc` · `research_commit_sha` · `methodology_version` · `adapter_schema_version` · `source_status_iv` · `source_status_iv_raw` · `source_status_realized_vol` · `source_status_realized_vol_raw`.

The stage marker's `provenance` block must tie out field-for-field to the pre-event event record.

## 6. Stage markers (new artifacts)

| File | Written at |
|---|---|
| `{event_id}_PRE_EVENT_CAPTURE_MARKER.json` | pre-event stage durable |
| `{event_id}_D1_CAPTURE_MARKER.json` | D1 durable |
| `{event_id}_FINAL_COMPLETION_MARKER.json` | terminal state only |

| Marker field | Notes |
|---|---|
| `stage` | `PRE_EVENT_CAPTURE` \| `D1_CAPTURE` \| `FINAL_COMPLETION` |
| `lifecycle_state` | the event's state at write time |
| `state_chronology` | full ordered state list |
| `module_eligibility` | the §1 block, or `null` for a legacy record |
| `is_full_data_complete` | lifecycle `COMPLETE` **and** `core_and_option_benchmark` |
| `provenance` | the §5 block |

Write-once. `atomic_write_json_no_overwrite()` raises `ImmutableArtifactExistsError` rather than replacing an existing marker, via an exclusive `os.link()` create (falling back to `O_CREAT|O_EXCL`) — **never** an existence check followed by `os.replace()`. See SPEC v0.2 §4.

A `PRE_EVENT_CAPTURE` marker requires `PRE_EVENT_CAPTURED`, or a `PARTIAL` whose `failure_stage` is `pre_event`; a `D1_CAPTURE` marker requires `D1_COMPLETE` or a `d1` `PARTIAL`. A D1 failure can no longer satisfy a pre-event marker.

## 7. Stage vocabulary correction

The market-response state machine implements **D1 and D3**. The D3 tier's fields (`close_T1_to_close_T2`, `close_T1_to_close_T3`) already carry the D2 close-to-close measurement, so there is **no separate D2 state**. The D2 **session** is owned by `operations_plan.py`, which schedules it as a calendar session. Prose describing the state machine as capturing "D1/D2/D3" is corrected accordingly; **no D2 state was invented to match prose**.
