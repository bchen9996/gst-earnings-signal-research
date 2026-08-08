# GST Earnings Market-Response Decomposition — SPEC v0.2 (DRAFT)

**Supersedes:** `GST_Earnings_Market_Response_Decomposition_SPEC_v0.1_DRAFT.md`, which is preserved **byte-for-byte** and remains the authority for everything v0.2 does not restate.
**Amendment:** `AMD-001-lifecycle-eligibility-separation` · **amended 2026-08-08 (UTC)** · methodology identifier **`market_response_v0.2`**.

**Provenance of this amendment.** Prompted by deterministic contract tracing, **not** by inspecting data. It was made **after** event registration and **before** any prospective research observation, pre-event snapshot, market-response observation, dossier, or Layer B record existed, and before the 2026-09-02 anchor. No DELL attention, price, volume, volatility, options, earnings-outcome, consensus, or analyst data was inspected. The human-verified timing registry is **not** amended — no timing fact changed. Nothing is backdated.

**Unchanged by v0.2:** the locked 24-ticker universe, the Phase 2 six-field contract, GST and Wikipedia methodology, z-score formulas, earnings-date rules, D1/D3 interval formulas, source retry logic, option-benchmark validity thresholds, quote-age and skew limits, dossier blinding rules, and all historical results.

---

## 1. Lifecycle state versus analytical eligibility

v0.1 used one state variable for two concepts. `PRE_EVENT_CAPTURED` required **both** the pre-event core gate **and** the option-benchmark gate, so an unavailable *optional* option benchmark produced `PARTIAL` — a **terminal** state — and `capture_d1()` then raised. A valid six-field core was destroyed by a missing optional module. That is avoidable event attrition.

v0.2 separates them:

| Concept | Meaning | Where recorded |
|---|---|---|
| **Lifecycle state** | which scheduled collection stages were captured | `event_record` state machine |
| **Analytical eligibility** | which evidence modules are valid for analysis | `ModuleEligibility` fields on the pre-event record |

`PRE_EVENT_CAPTURED` means **"the validated pre-event capture stage was recorded"**. It does **not** mean "every optional module was available". Lifecycle `COMPLETE` at the end of D3 means **collection finished**, never full-data completeness.

| Case | Lifecycle | core | option | joint | `pre_event_completeness_tier` |
|---|---|---|---|---|---|
| core gate fails | `PARTIAL` (terminal) | false | false | false | `core_invalid` |
| core + valid OPRA benchmark | `PRE_EVENT_CAPTURED` | true | true | true | `core_and_option_benchmark` |
| core + explicitly unavailable | `PRE_EVENT_CAPTURED` | true | false | false | `core_only_no_option_benchmark` |

`is_full_data_complete()` requires lifecycle `COMPLETE` **and** the `core_and_option_benchmark` tier. Hypothesis families are gated mechanically, and **lifecycle state is not an argument** to that function:

| Hypothesis family | Requires |
|---|---|
| `core_attention_vs_equity_response` | `core_pre_event_eligible` |
| `options_implied_move` | `option_benchmark_eligible` |
| `joint_attention_plus_options` | `joint_full_eligible` |

## 2. Strict six-field core (v0.2)

The v0.1 gate (`is_valid_pre_event_observation`) is **preserved unchanged** for the legacy path. v0.2 adds `evaluate_strict_core_v0_2()`, required by the pre-event capture orchestrator. All six Phase 2 panel fields must be present **and** each backed by a successful source status:

| # | Strict-core field | Source status consulted |
|---|---|---|
| 1 | `gst_zscore` | `source_status_gst` |
| 2 | `wiki_zscore` | `source_status_wiki` |
| 3 | `panel_implied_volatility` | `source_status_price` |
| 4 | `realized_volatility` | `source_status_price` |
| 5 | `previous_close` (canonical price field) | `source_status_price` |
| 6 | `volume` | `source_status_price` |

Successful statuses: `ok`, `ok_recent_cache_fallback`. Plus required provenance: `pre_event_snapshot_asof_utc`.

- A **null/missing** value fails.
- A **non-success** source status fails.
- A **legitimate numeric `0.0` with a successful status passes.** Missingness is never inferred from a zero.

### 2.1 `panel_implied_volatility` — a deliberate namespacing

SPEC v0.1 §5 and the v0.1 field dictionary prohibit using the panel's generic `implied_volatility` as an earnings-implied-move baseline; `option_chain_adapter` is the only legitimate source for an implied-move-shaped field. **That prohibition is unchanged.**

v0.2 persists the panel's IV strictly as **six-field completeness provenance**, under the namespaced key `panel_implied_volatility`. It is never exposed as `implied_volatility`, never fed to the option benchmark, and never usable as an implied-move value. *Persisting a field as evidence* and *using it as a benchmark* are different acts; only the second is prohibited.

## 3. Explicit option-benchmark dispositions

Unavailability is **never inferred** from `{}` or from null fields. The caller declares one:

| Disposition | Requires | Analytically eligible |
|---|---|---|
| `VALID_VERIFIED` | `option_feed` ∈ {`opra`} **and** the existing `is_valid_option_benchmark()` gate | **yes** |
| `UNAVAILABLE_NO_VERIFIED_SOURCE` | all benchmark values null + nonblank reason | no |
| `LOOKUP_FAILED` | failure provenance (nonblank reason) + all values null | no |
| `NOT_ATTEMPTED` | nonblank reason stating why collection was not attempted | no |

Unknown or blank fails closed. Indicative quotes are a **modified derivative of OPRA**; they may be neither promoted to `VALID_VERIFIED` nor relabelled as unavailable. A supplied artifact that contradicts its declared disposition — malformed, crossed, stale, timestamp-less — is **rejected with zero writes**, not downgraded to ordinary unavailability. No disposition bypasses core validation.

**Operational restriction:** the pre-event capture CLI **refuses `VALID_VERIFIED`** entirely. It cannot authenticate provider identity, endpoint, response hash, contracts, strike, expiration, per-leg quote timestamps, quote age, skew, or a recomputed benchmark, so accepting an asserted OPRA claim from a hand-written file would let an operator manufacture a verified benchmark by typing one. Until a separately cleared provider artifact exists, only the unavailable dispositions are accepted through that route.

## 4. Immutable stage-marker lifecycle

v0.1 had one `{event_id}_COMPLETION_MARKER.json` that had to be **replaced** as the event progressed. Deleting evidence to make progress is forbidden everywhere else in this project, so v0.2 uses one **write-once** marker per durable stage:

| Marker | Written when |
|---|---|
| `{event_id}_PRE_EVENT_CAPTURE_MARKER.json` | pre-event stage becomes durable |
| `{event_id}_D1_CAPTURE_MARKER.json` | D1 becomes durable |
| `{event_id}_FINAL_COMPLETION_MARKER.json` | **only** at a genuinely terminal state |

All are written with `atomic_write_json_no_overwrite()`, which raises `ImmutableArtifactExistsError` rather than replacing. No production path or test may unlink or overwrite a marker to progress. The v0.1 writer remains in place, unchanged, for the legacy path.

## 5. Provenance requirements

Every pre-event record and stage marker persists, and the marker mechanically ties out to the record on: panel CSV path and SHA-256, panel marker path and SHA-256, panel status, row count, unique-ticker count, all-six-fields-clean count, ticker, `run_date`, `price_asof_date`, `pre_event_snapshot_asof_utc`, research commit SHA, methodology version, adapter schema version.

## 6. Crash and recovery semantics

A crash between a durable state append and its marker is recoverable **deterministically**:

- marker absent → rebuild from the event record and write once;
- marker present and tying out → returned untouched;
- marker present and **disagreeing** → **fail closed**; never overwritten.

Recovery never appends to the event record, so it cannot duplicate a state transition, and never deletes evidence.

## 7. Authoritative session date

The pre-event anchor binds to the panel's **`price_asof_date`** column — the session the price data is as-of.

It does **not** bind to `run_date`, and never to a truncated `retrieval_timestamp_utc`. These genuinely differ: a real panel run has `run_date = 2026-07-30` with `price_asof_date = 2026-07-29`, because the panel executes in the small hours UTC (04:40Z = 00:40 ET) **after** the session it summarises. `run_date >= price_asof_date` is asserted; the reverse would mean summarising a session that had not happened.

Fail-closed on ambiguity: a missing `price_asof_date` column, a blank value, or more than one distinct value across rows is a validation failure, never a guess.

## 8. Market-response stages: D1 and D3

**The market-response state machine implements D1 and D3, not D2.** `MAINLINE_ORDER` is `REGISTERED → PRE_EVENT_PENDING → PRE_EVENT_CAPTURED → D1_PENDING → D1_COMPLETE → D3_PENDING → COMPLETE`, and the completeness tiers are `pre_event`, `option_benchmark`, `d1`, `d3`.

- **D1** = the first full session able to price the release (`overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close`).
- **D3** = the multi-session completion, whose fields are `close_T1_to_close_T2` and `close_T1_to_close_T3` — i.e. the D3 tier **already carries the T2 (D2) close-to-close measurement**; there is no separate D2 *state*.

**D2 ownership.** The D2 *session* is owned by the **operations planner** (`operations_plan.py`), which derives and schedules `D2` as a calendar session so an operator knows when the T2 close is observable. It is deliberately **not** a state-machine stage, because no gate depends on D2 alone. **No D2 state was invented to match prose**; instead, prose claiming the state machine captures "D1/D2/D3" is corrected to "D1 and D3, with the D2 close measured inside the D3 tier".

## 9. Methodology identifier

The v0.2 capture path accepts exactly `market_response_v0.2`. Blank, arbitrary, stale and v0.1 values are rejected by both the CLI and the orchestrator, and the accepted value is persisted into the event record and every stage marker.

## 10. Scope statements

The options benchmark is **separate from the Phase 2 six-field contract**. An unavailable benchmark **never becomes zero**; it may **lower the event's completeness tier**; it **does not authorize indicative substitution**. The attention signal and the equity market-response decomposition remain collectible for a core-only event. **No strategy, return forecast, or trading recommendation is produced by this module.**
