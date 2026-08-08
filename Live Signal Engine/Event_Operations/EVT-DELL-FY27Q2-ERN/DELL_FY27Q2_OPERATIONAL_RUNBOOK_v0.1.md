# DELL FY27 Q2 — Operational Runbook v0.1

**Event:** `EVT-DELL-FY27Q2-ERN` · Dell Technologies Inc. (`DELL`) · FY27 Q2
**Machine-readable plan:** `EVT-DELL-FY27Q2-ERN_operations_plan_v0.1.json`
**Calendar:** `XNYS_exchange_calendars_v4.13.2` · **Planner:** `operations_plan.py` v0.1

> **This is an operations document, not research output.** It contains no investment recommendation, no expected price direction, no consensus or analyst figure, no price target, no scenario, and no strategy. Nothing here asserts what the result will be — only what must be done, when, and in what order.
>
> **The event is currently only REGISTERED.** No pre-event snapshot has been taken. No market, attention, option, consensus, or earnings-result data has been inspected for this event.
>
> **This runbook is not yet executable end to end.** Three hard blockers (§11) stand between it and a real capture. Do not start §1 expecting to finish §5.

## Mechanically derived schedule

Every date below was derived from the XNYS calendar by the planner, not typed in. All times UTC with exchange-local (ET) mirrors.

| Stage | Session | Open (UTC / ET) | Close (UTC / ET) | Earliest provider retrieval |
|---|---|---|---|---|
| Pre-event anchor | **2026-09-02** (Wed) | 13:30Z / 09:30 | 20:00Z / 16:00 | 20:10Z / 16:10 |
| **Release** | 2026-09-03 (Thu) | — | — | — |
| D1 | **2026-09-04** (Fri) | 13:30Z / 09:30 | 20:00Z / 16:00 | 20:10Z / 16:10 |
| D2 | **2026-09-08** (Tue) | 13:30Z / 09:30 | 20:00Z / 16:00 | 20:10Z / 16:10 |
| D3 | **2026-09-09** (Wed) | 13:30Z / 09:30 | 20:00Z / 16:00 | 20:10Z / 16:10 |

**Release:** `2026-09-03T20:30:00Z` = 16:30 ET, **AMC**. Derived mechanically: 3:30 PM CDT → 4:30 PM EDT → 20:30Z, which is strictly after the 20:00Z (4:00 PM ET) close. Not from reporting history.

**Why D2 skips to Tuesday 2026-09-08:** 2026-09-05 (Sat) and 2026-09-06 (Sun) are weekend days, and **2026-09-07 (Mon) is Labor Day — XNYS closed**. The calendar skipped it; no arithmetic here assumes a gap.

**Earliest provider retrieval** = final expected 5-minute bar start (close − 5 min) + 15 min, mirroring `alpaca_provider.MIN_END_AGE_MINUTES`. Requesting earlier is refused by the provider's freshness gate.

---

## 1. Pre-event snapshot preparation

**Window:** before 2026-09-02 close. **State:** `REGISTERED` → (later) `PRE_EVENT_PENDING`.

- [ ] Confirm the registry row is still `verified` and unamended: `EVT-DELL-FY27Q2-ERN-REG-001`.
- [ ] Re-derive the plan and confirm `plan_content_sha256` is unchanged; if the calendar package changed, the plan must be regenerated and the difference explained.
- [ ] Decide and record how the anchor-session Phase 2 panel will be produced (see **BLK-PANEL-1**).
- [ ] Resolve the option-benchmark source decision (**BLK-OPT-1**, **BLK-OPT-2**) — or record an explicit decision to proceed without an option benchmark and accept the resulting tier.
- [ ] Confirm `DELL` needs no Alpaca symbol translation (identity; only `BRK-B`→`BRK.B` differs).

**Do not** capture anything in this stage.

## 1b. Exact commands (protocol v0.2, orchestrator v0.1)

**Execution before the anchor session is forbidden.** Do not run `--execute` before 2026-09-02's close. The orchestrator enforces the anchor mechanically and refuses a future-dated panel, but the operational rule stands on its own.

**Preflight (any time)** — confirms the plan still derives the same schedule:

```bash
python -m gst_market_response.operations_cli plan \
  --registry "Live Signal Engine/Market_Response_Event_Registry/registry.jsonl" \
  --event-id EVT-DELL-FY27Q2-ERN --company-name "Dell Technologies Inc." \
  --planning-commit <HEAD_SHA> --methodology-version market_response_v0.2
```

**Validation (read-only, the default — run this first, always).** Writes nothing:

```bash
python -m gst_market_response.pre_event_capture_cli \
  --event-id EVT-DELL-FY27Q2-ERN \
  --expected-anchor-session 2026-09-02 \
  --panel-csv  "<PATH>/GST_Phase2_DailyPanel_<RUN>.csv" \
  --panel-marker "<PATH>/GST_Phase2_DailyPanel_<RUN>_COMPLETION_MARKER.json" \
  --store-root "Live Signal Engine/Event_Operations/EVT-DELL-FY27Q2-ERN/event_store" \
  --research-commit-sha <HEAD_SHA> \
  --methodology-version market_response_v0.2 \
  --registry "Live Signal Engine/Market_Response_Event_Registry/registry.jsonl" \
  --company-name "Dell Technologies Inc." \
  --option-status UNAVAILABLE_NO_VERIFIED_SOURCE \
  --option-reason "Alpaca options entitlement INCONCLUSIVE; no OPRA-verified source"
```

**Execution — only after validation exits 0.** The same command plus `--execute`.

If a verified OPRA benchmark does become available, replace the two `--option-*` flags with `--option-benchmark-json <path>`; that artifact must declare `option_benchmark_status: VALID_VERIFIED` and `option_feed: opra`, and pass the existing benchmark gate.

**Exit codes:** `0` validation passed / capture succeeded · `1` validation failed (stale, future, wrong anchor, hash or identity mismatch, missing core field, bad option artifact, collision, state error) · `2` usage error.

**Expected files after execution**, under `--store-root`:

| File | |
|---|---|
| `EVT-DELL-FY27Q2-ERN.jsonl` | append-only event log |
| `EVT-DELL-FY27Q2-ERN_COMPLETION_MARKER.json` | atomic marker carrying the tier and `is_full_data_complete` |

**Required hashes.** Record the panel CSV and marker SHA-256 printed in the validation report; the adapter re-hashes both and cross-verifies the marker's own counts against the CSV. The registry blob must remain `71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974`.

**Collision stop conditions — all fail closed with zero new bytes.** An existing `PRE_EVENT_PENDING`/`PRE_EVENT_CAPTURED` state, or an existing completion marker, aborts the run. Repeated execution is idempotent by refusal. **Never** delete an event log or marker to "retry" — a correction is an append-only amendment.

**Unavailable-options behaviour.** With `--option-status UNAVAILABLE_NO_VERIFIED_SOURCE` the capture proceeds: core eligible, option module **ineligible**, joint **ineligible**, tier `core_only_no_option_benchmark`, every option value **null — never zero**. D1/D2/D3 remain collectible and the event may reach lifecycle `COMPLETE`, but the marker reports `is_full_data_complete: false` and the event is mechanically excluded from options-implied-move and joint hypotheses. Indicative quotes are not an acceptable substitute and cannot be relabelled as either unavailable or OPRA-valid.

**Rollback / recovery.** There is no rollback of an append-only store. If a capture is wrong: stop, delete nothing, and record an append-only amendment. Re-running against a corrected panel is a new decision, not a flag — there is no `--force`, `--overwrite`, `--skip-validation`, `--allow-stale` or `--ignore`.

## 2. The locked 2026-09-02 snapshot anchor

**This is the outcome-blind boundary.** Everything captured here must be observable *before* the release. Nothing captured after 2026-09-03T20:30:00Z may enter the pre-event record.

- [ ] Produce a **COMPLETE** Phase 2 panel for 2026-09-02. A `PARTIAL` panel does not qualify.
- [ ] Pass the panel CSV **and** its paired completion marker to `phase2_adapter.import_pre_event_fields_for_ticker()` by **explicit path** — the adapter never discovers "the latest file".
- [ ] Confirm the adapter's marker↔CSV cross-verification passed and both input hashes are recorded.
- [ ] **Manually confirm the panel's data date is 2026-09-02** — the adapter has no expected-session parameter and cannot do this for you (**BLK-STALE-1**).
- [ ] Capture the option benchmark, if unblocked, with a genuine venue quote timestamp.
- [ ] Submit both to `pipeline.capture_pre_event_and_option_benchmark()`. It writes `PRE_EVENT_PENDING`, then `PRE_EVENT_CAPTURED` **only if both tier gates pass**, otherwise `PARTIAL`. It never silently promotes.

## 3. The 2026-09-03 earnings release

- [ ] Take **no** action against the pre-event record after 20:30Z. It is closed.
- [ ] Do not amend, re-run, or "improve" the anchor snapshot after the release. A correction is an append-only amendment with a reason (§10), never an edit.

## 4. Outcome-blinded Layer A dossier work

Layer A is the blinded event core. It may be prepared **before** the release and must remain free of any market-reaction content.

- [ ] Build Layer A tables per the Event Dossier Protocol (`events.csv`, `claims.csv`, `claim_sources.csv`, `event_labels.csv`, …).
- [ ] Keep every market-response figure out of Layer A — the validator's blinding gate rejects reaction language in Layer-A fields, and Layer-A child rows may not cite Layer-B evidence.
- [ ] Note the protocol vocabulary difference: the registry says `AMC`; the protocol's `events.csv` requires `after_close`. Convert only via `protocol_boundary.to_protocol_release_session()`.

## 5. D1 raw market-response capture (2026-09-04)

- [ ] Wait until **20:10Z** — earlier requests are refused by the freshness gate.
- [ ] Capture D1 5-minute bars for `DELL` and its benchmark (XLK; sector mapping APPROVED, DELL a confirmed constituent).
- [ ] Derive `overnight_gap`, `open_to_30m`, `thirty_min_to_close`, `open_to_close` via `derivations.py`. Do not recompute intervals by hand.
- [ ] Submit to `pipeline.capture_d1()`; expect `D1_COMPLETE`, else `PARTIAL`.
- [ ] Store raw bars immutably, separately from the registry, plan, and dossier.

## 6. D2 / D3 completion (2026-09-08, 2026-09-09)

- [ ] D2 2026-09-08 from 20:10Z; D3 2026-09-09 from 20:10Z.
- [ ] Derive `close_T1_to_close_T2` and `close_T1_to_close_T3`.
- [ ] Submit to `pipeline.capture_d3()`; expect `COMPLETE`, else `PARTIAL`.
- [ ] `COMPLETE`, `PARTIAL` and `ABSTAIN_DATA_QUALITY` are **terminal** — `PARTIAL` can never later become `COMPLETE`. Corrections are amendment records.

## 7. Layer A human freeze and reviewer separation

- [ ] Freeze the Layer A label only when a human reviewer signs it; record `freeze_timestamp_utc` and `frozen_by` in the freeze manifest.
- [ ] **A reviewer exposed to Layer B content for this event before the Layer A freeze is permanently disqualified from signing that label.** The validator enforces this via `reviewer_capture_exposure_log`.
- [ ] The freeze manifest must not reference any `market_response_addendum` path — Layer B never belongs in a frozen Layer A bundle.

## 8. Layer B emission eligibility

- [ ] Only a **`COMPLETE`** market-response record is eligible. `PARTIAL` and `ABSTAIN_DATA_QUALITY` are refused by `layer_b_addendum.check_eligibility()`.
- [ ] The Layer A event and label must exist and agree on `event_id`.
- [ ] `captured_at_utc` must be timezone-aware. `price_reaction_window` is required whenever `price_reaction_pct` is set, and must be in the protocol enum.
- [ ] **Capture is not gated on freeze** — the protocol permits Layer B capture before the Layer A freeze, provided it is not revealed. *Reveal* is gated, and is recorded in the freeze manifest's `reveal_events[]`, strictly after `freeze_timestamp_utc`.
- [ ] Missing values stay empty. **Never zero-fill.** A real measured `0.0` is recorded as `0.0`.
- [ ] Emission is append-only: an existing `addendum_id` raises rather than overwriting.

## 9. Final completeness verification

- [ ] Run the real, unmodified Event Dossier validator over the combined fixture. Do not weaken a gate to make output pass.
- [ ] Confirm the event's terminal state and its completion marker agree.
- [ ] Confirm the operational Wikipedia cache and preserved panel artifacts are byte-identical to their pre-run hashes.

## 10. Failure handling and append-only amendment rules

- Every store is **append-only**. Never rewrite a row's bytes.
- A correction is an **AMENDMENT** row citing the row it corrects; the original survives verbatim.
- If required data cannot be obtained honestly, route to **`ABSTAIN_DATA_QUALITY`** rather than fabricating, interpolating, zero-filling, or substituting a midpoint for an executable cost.
- A failed provider call is never retried into a different request shape to obtain a "better" answer.
- If the release timing turns out to differ from the registered value, **stop** — that invalidates the anchor and the derived schedule, and requires a human decision.

## 11. Blockers that currently prevent §2 and §5

| ID | Severity | Blocker |
|---|---|---|
| **BLK-OPT-1** | hard | No operationally verified option-quote source. Alpaca has zero option support; the only route is yfinance, and `option_chain_adapter.py` has no provider-eligibility concept at all. |
| **BLK-OPT-2** | hard | `build_option_benchmark()` requires the *caller* to supply `quote_timestamp_utc`; a yfinance chain carries no per-quote timestamp, so provenance would be asserted, not observed. |
| **BLK-ORCH-1** | hard | No end-to-end capture command exists. `build_option_benchmark()` is called only from tests; `cli.py` does only a gate check plus marker write. |
| **BLK-STALE-1** | material | `import_pre_event_fields_for_ticker()` has no expected-session parameter, so it cannot reject a panel from the wrong date. |
| **BLK-PANEL-1** | material | A COMPLETE Phase 2 panel for 2026-09-02 is not guaranteed; recent live attempts were PARTIAL and the Wikipedia 404 issue is unresolved. |

Each hard blocker requires a human methodology or provider decision. **Do not build a live capture runner until BLK-OPT-1, BLK-OPT-2 and BLK-ORCH-1 are resolved.**

## Last safe registration deadline (already met)

Registration completed 2026-08-07, well inside the 2026-08-26 deadline that preserves ≥5 pre-event sessions. **18** sessions remained at registration.
