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

Each field is backed by the panel leg that **actually produced it**. The Phase 2 panel emits five independent per-leg statuses, and the option-chain leg fails for entirely different reasons than the price-history leg.

| # | Strict-core field | Panel status column | Normalised status consulted |
|---|---|---|---|
| 1 | `gst_zscore` | `gst_status` | `source_status_gst` |
| 2 | `wiki_zscore` | `wiki_status` | `source_status_wiki` |
| 3 | `panel_implied_volatility` | `iv_status` | `source_status_iv` |
| 4 | `realized_volatility` | `realized_vol_status` | `source_status_realized_vol` |
| 5 | `previous_close` (canonical price field) | `price_history_status` | `source_status_price` |
| 6 | `volume` | `price_history_status` | `source_status_price` |

Successful statuses: `ok`, `ok_recent_cache_fallback`. Plus required provenance: `pre_event_snapshot_asof_utc`.

- A **null/missing** value fails.
- A **non-success** source status fails. An **unknown or absent** status fails closed.
- A **legitimate numeric `0.0` with a successful status passes.** Missingness is never inferred from a zero.

**Correction (second audit pass).** Implied volatility and realized volatility previously inherited `source_status_price`. That is a different leg: a failed `iv_status` or `realized_vol_status` passed the six-field gate whenever price history happened to be OK — treating unavailable data as present, which this gate exists to prevent. `previous_close` and `volume` do both come from the price-history leg and legitimately share it.

### 2.1 `panel_implied_volatility` — a deliberate namespacing

SPEC v0.1 §5 and the v0.1 field dictionary prohibit using the panel's generic `implied_volatility` as an earnings-implied-move baseline; `option_chain_adapter` is the only legitimate source for an implied-move-shaped field. **That prohibition is unchanged.**

v0.2 persists the panel's IV strictly as **six-field completeness provenance**, under the namespaced key `panel_implied_volatility`. It is never exposed as `implied_volatility`, never fed to the option benchmark, and never usable as an implied-move value. *Persisting a field as evidence* and *using it as a benchmark* are different acts; only the second is prohibited.

### 2.2 No unversioned capture function (second audit pass)

The v0.2 orchestrator called `pipeline.capture_pre_event_and_option_benchmark()`, which judged the core with `evaluate_pre_event_modules()` — i.e. the **v0.1** gate. The orchestrator ran the strict gate as a separate report check, but the eligibility persisted on the record came from the weaker one, and any caller reaching the pipeline directly bypassed the strict gate entirely.

The capture entry point is now split by protocol version and **no unversioned public capture function exists**:

| Function | Core gate |
|---|---|
| `capture_pre_event_and_option_benchmark_v0_2()` | `evaluate_strict_core_v0_2()` via `evaluate_pre_event_modules_v0_2()` |
| `capture_pre_event_and_option_benchmark_v0_1()` | `is_valid_pre_event_observation()` — legacy contract only |

The old unversioned name raises `AttributeError` with explicit version guidance rather than resolving to either behaviour. The v0.2 orchestrator may call only the `_v0_2` entry point.

## 3. Explicit option-benchmark dispositions

Unavailability is **never inferred** from `{}` or from null fields. The caller declares one:

| Disposition | Requires | Analytically eligible |
|---|---|---|
| `VALID_VERIFIED` | `option_feed` ∈ {`opra`} **and** the existing `is_valid_option_benchmark()` gate | **yes** |
| `UNAVAILABLE_NO_VERIFIED_SOURCE` | all benchmark values null + nonblank reason | no |
| `LOOKUP_FAILED` | failure provenance (nonblank reason) + all values null | no |
| `NOT_ATTEMPTED` | nonblank reason stating why collection was not attempted | no |

Unknown or blank fails closed. Indicative quotes are a **modified derivative of OPRA**; they may be neither promoted to `VALID_VERIFIED` nor relabelled as unavailable. A supplied artifact that contradicts its declared disposition — malformed, crossed, stale, timestamp-less — is **rejected with zero writes**, not downgraded to ordinary unavailability. No disposition bypasses core validation.

**The artifact is bound to the validation that approved it.** Validation canonicalises the complete option disposition — status, reason, feed and every benchmark value — and stores its SHA-256 in the `ValidationReport` and in the capture fingerprint. Execution re-derives the digest from the dict it is actually handed and requires exact equality. Validating `UNAVAILABLE_NO_VERIFIED_SOURCE` and then executing with a different disposition, a different reason, or a dict claiming a verified OPRA benchmark **fails with zero writes**. Canonicalisation is order-independent, so key ordering alone never causes a false mismatch.

**Operational restriction:** the pre-event capture CLI **refuses `VALID_VERIFIED`** entirely. It cannot authenticate provider identity, endpoint, response hash, contracts, strike, expiration, per-leg quote timestamps, quote age, skew, or a recomputed benchmark, so accepting an asserted OPRA claim from a hand-written file would let an operator manufacture a verified benchmark by typing one. Until a separately cleared provider artifact exists, only the unavailable dispositions are accepted through that route.

## 4. Immutable stage-marker lifecycle

v0.1 had one `{event_id}_COMPLETION_MARKER.json` that had to be **replaced** as the event progressed. Deleting evidence to make progress is forbidden everywhere else in this project, so v0.2 uses one **write-once** marker per durable stage:

| Marker | Written when |
|---|---|
| `{event_id}_PRE_EVENT_CAPTURE_MARKER.json` | pre-event stage becomes durable |
| `{event_id}_D1_CAPTURE_MARKER.json` | D1 becomes durable |
| `{event_id}_FINAL_COMPLETION_MARKER.json` | **only** at a genuinely terminal state |

All are written with `atomic_write_json_no_overwrite()`, which raises `ImmutableArtifactExistsError` rather than replacing. No production path or test may unlink or overwrite a marker to progress. The v0.1 writer remains in place, unchanged, for the legacy path.

**The write-once primitive must be genuinely atomic (second audit pass).** The first implementation was `if path.exists(): raise` followed by `atomic_write_json()`, whose final step is `os.replace()` — an unconditional replace. Any artifact created between the check and the replace was silently destroyed, which is the exact evidence loss this rule exists to prevent, and no reordering of check-then-replace fixes it.

The create itself must be the exclusive operation:

1. write the complete payload to a temporary file in the target directory and `fsync` it, so the bytes are durable before the final name exists at all;
2. `os.link()` the temporary file to the final path. `link()` creates a **new** directory entry and raises `FileExistsError` if the name is taken — it never replaces. The final name therefore appears atomically already carrying complete content, and the loser of a race raises;
3. `fsync` the directory, and unlink the temporary file on every path, including failures.

Where the filesystem does not support hard links, an exclusive `O_CREAT|O_EXCL` open is used instead: equally race-safe on the create, with weaker content atomicity only. **An existence check followed by `os.replace()` is prohibited.**

## 5. Provenance requirements

Every pre-event record and stage marker persists, and the marker mechanically ties out to the record on: panel CSV path and SHA-256, panel marker path and SHA-256, panel status, row count, unique-ticker count, all-six-fields-clean count, ticker, `run_date`, `price_asof_date`, `pre_event_snapshot_asof_utc`, research commit SHA, methodology version, adapter schema version.

## 6. Crash and recovery semantics

### 6.1 Crash between a durable state append and its marker

- marker absent → rebuild from the event record and write once;
- marker present and tying out → returned untouched;
- marker present and **disagreeing** → **fail closed**; never overwritten.

Recovery never appends to the event record, so it cannot duplicate a state transition, and never deletes evidence.

### 6.2 Crash between `PRE_EVENT_PENDING` and `PRE_EVENT_CAPTURED` (second audit pass)

This is the more dangerous crash and the first version did not handle it. `REGISTERED → PRE_EVENT_PENDING → crash` left an event **permanently stuck**: every rerun refused because a pre-event state already existed, and the pending record may never be deleted or rewritten. Nothing had actually been captured.

Resuming is only safe if the rerun is provably capturing **the same thing**, so `PRE_EVENT_PENDING` now persists a **canonical capture-input fingerprint** covering:

`capture_fingerprint_version` · `event_id` · `ticker` · `anchor_session` · `panel_csv_sha256` · `panel_marker_sha256` · `research_commit_sha` · `methodology_version` · `option_fields_digest`

plus a self-digest over exactly those fields. The rerun revalidates **every** input from scratch and then:

| Pending state | Outcome |
|---|---|
| none | ordinary capture: append `PRE_EVENT_PENDING`, then the outcome state |
| exactly one, fingerprint matches exactly, no stage marker | **resume**: append the outcome state only — no second `PRE_EVENT_PENDING` |
| fingerprint differs in any field | **fail closed**, zero writes |
| no fingerprint (pre-contract record) | **fail closed** |
| self-digest does not recompute | **fail closed** |
| more than one pending record | **fail closed** — ambiguous |
| the pre-event stage already completed | refused as before |

The pending record is **never deleted, rewritten or duplicated**, and resume **never skips the strict core gate**: the full six-field evaluation, panel re-hash and date audit all run again before the outcome state is appended.

## 7. Authoritative session date

The pre-event anchor binds to the panel's **`price_asof_date`** column — the session the price data is as-of.

It does **not** bind to `run_date`, and never to a truncated `retrieval_timestamp_utc`. These genuinely differ: a real panel run has `run_date = 2026-07-30` with `price_asof_date = 2026-07-29`, because the panel executes in the small hours UTC (04:40Z = 00:40 ET) **after** the session it summarises. `run_date >= price_asof_date` is asserted; the reverse would mean summarising a session that had not happened.

### 7.1 Every row is audited; nothing is discarded first (second audit pass)

The first implementation built a set of the rows' values and then called `.discard("")`, so a **blank** `price_asof_date` among otherwise agreeing rows vanished before validation and the panel resolved to a single session. `run_date` was weaker still: ambiguity silently produced `None`, which **skipped** the ordering check entirely.

Blank is not the same as absent. A row with a blank session is a row whose session the panel did not record, and it cannot be certified as belonging to the anchor. Nothing is discarded. All six rules are required, each reported as its own named check:

1. every row has a **nonblank** `price_asof_date`;
2. every row agrees on **exactly one** `price_asof_date`;
3. every row has a **nonblank** `run_date`;
4. every row agrees on **exactly one** `run_date`;
5. `run_date >= price_asof_date` — asserted, never skipped; an unresolvable pair **fails** rather than being waived;
6. `price_asof_date` equals the mechanically derived anchor.

A missing column makes every row blank, and therefore fails for the same reason. Ambiguity is a validation failure, never a guess.

## 8. Market-response stages: D1 and D3

**The market-response state machine implements D1 and D3, not D2.** `MAINLINE_ORDER` is `REGISTERED → PRE_EVENT_PENDING → PRE_EVENT_CAPTURED → D1_PENDING → D1_COMPLETE → D3_PENDING → COMPLETE`, and the completeness tiers are `pre_event`, `option_benchmark`, `d1`, `d3`.

- **D1** = the first full session able to price the release (`overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close`).
- **D3** = the multi-session completion, whose fields are `close_T1_to_close_T2` and `close_T1_to_close_T3` — i.e. the D3 tier **already carries the T2 (D2) close-to-close measurement**; there is no separate D2 *state*.

**D2 ownership.** The D2 *session* is owned by the **operations planner** (`operations_plan.py`), which derives and schedules `D2` as a calendar session so an operator knows when the T2 close is observable. It is deliberately **not** a state-machine stage, because no gate depends on D2 alone. **No D2 state was invented to match prose**; instead, prose claiming the state machine captures "D1/D2/D3" is corrected to "D1 and D3, with the D2 close measured inside the D3 tier".

## 8.1 `PARTIAL` is stage-specific (second audit pass)

`PARTIAL` is reachable from the pre-event, D1 **and** D3 stages, and it carries the fields of whichever stage failed. Selectors that searched backwards for "the last record that is `PRE_EVENT_CAPTURED` or `PARTIAL` with fields" therefore mistook a later D1/D3 failure for the pre-event eligibility record: a D1 `PARTIAL` replaced a perfectly good pre-event capture's eligibility, and a `pre_event` gate check graded D1 interval fields.

Every v0.2 `PARTIAL` persists an explicit discriminator — `failure_stage` ∈ {`pre_event`, `d1`, `d3`}. Selection is then mechanical:

| Consumer | May use |
|---|---|
| pre-event eligibility (completion marker, stage markers, `pre_event` / `option_benchmark` gates) | `PRE_EVENT_CAPTURED`; only if none exists, `PARTIAL` with `failure_stage="pre_event"` |
| D1 marker and `d1` gate | `D1_COMPLETE`; else `PARTIAL` with `failure_stage="d1"` |
| D3 / final logic | `COMPLETE`; else `PARTIAL` with `failure_stage="d3"` — and pre-event eligibility is read from the **pre-event** record regardless |

The stage's own success state always wins over any `PARTIAL`. For a legacy record predating the field, the stage is **derived mechanically** from the chronology (the pending state immediately preceding the `PARTIAL`), never guessed or defaulted; an unrecognised explicit value resolves to no stage at all, so it can never be attributed to the wrong one. **A D1 or D3 failure can never erase or replace pre-event eligibility.**

## 9. Methodology identifier

The v0.2 capture path accepts exactly `market_response_v0.2`. Blank, arbitrary, stale and v0.1 values are rejected by both the CLI and the orchestrator, and the accepted value is persisted into the event record and every stage marker.

## 10. Scope statements

The options benchmark is **separate from the Phase 2 six-field contract**. An unavailable benchmark **never becomes zero**; it may **lower the event's completeness tier**; it **does not authorize indicative substitution**. The attention signal and the equity market-response decomposition remain collectible for a core-only event. **No strategy, return forecast, or trading recommendation is produced by this module.**
