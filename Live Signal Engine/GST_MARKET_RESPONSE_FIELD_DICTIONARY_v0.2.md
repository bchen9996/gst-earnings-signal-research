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

| Strict-core field | Status consulted | Notes |
|---|---|---|
| `gst_zscore` | `source_status_gst` | |
| `wiki_zscore` | `source_status_wiki` | |
| `panel_implied_volatility` | `source_status_price` | See §3.1 — **not** an implied-move value. |
| `realized_volatility` | `source_status_price` | |
| `previous_close` | `source_status_price` | The protocol's canonical price field. |
| `volume` | `source_status_price` | |

Successful statuses: `ok`, `ok_recent_cache_fallback`. Also required: `pre_event_snapshot_asof_utc`.

Null fails · non-success status fails · **a legitimate `0.0` with a successful status passes**. Missingness is never inferred from zero.

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

## 5. Persisted provenance (echoed in every stage marker)

`ticker` · `source_csv_path` · `source_csv_sha256` · `source_marker_path` · `source_marker_sha256` · `panel_status` · `panel_row_count` · `panel_unique_ticker_count` · `panel_all_six_fields_clean_count` · `run_date` · `price_asof_date` · `pre_event_snapshot_asof_utc` · `research_commit_sha` · `methodology_version` · `adapter_schema_version`.

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

Write-once. `atomic_write_json_no_overwrite()` raises `ImmutableArtifactExistsError` rather than replacing an existing marker.

## 7. Stage vocabulary correction

The market-response state machine implements **D1 and D3**. The D3 tier's fields (`close_T1_to_close_T2`, `close_T1_to_close_T3`) already carry the D2 close-to-close measurement, so there is **no separate D2 state**. The D2 **session** is owned by `operations_plan.py`, which schedules it as a calendar session. Prose describing the state machine as capturing "D1/D2/D3" is corrected accordingly; **no D2 state was invented to match prose**.
