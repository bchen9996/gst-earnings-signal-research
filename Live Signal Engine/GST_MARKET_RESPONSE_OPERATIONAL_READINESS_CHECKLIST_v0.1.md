# Market Response — Operational Readiness Checklist (v0.1)

Status as of the 2026-08-04 **post-fix validation pass** (fourth pass; PR #3, branch `phase2-market-response`,
stacked on PR #1). **No real event has been registered. No trading strategy is selected. No profitability claim
exists.**

**Provider status: `LIVE_DIAGNOSTIC_PASSED` — the Alpaca provider is CLEARED for real event capture.** Defect
ALP-1 is fixed and closed; the post-fix live diagnostic passed for both SPY (33/33) and BRK-B (29/29), each
returning **exactly 78 SIP/raw 5-minute bars from 09:30 through 15:55 ET** with no extra or missing timestamps.

**Clearance is not production-readiness.** It means one bounded live diagnostic passed against two benchmark
tickers on one historical session. **One complete prospective earnings event is still required** before this lane
can be called production-ready — see the blockers below.

## Done — first pass (2026-08-04)

- [x] `HumanVerifiedEventRegistryProvider` (`event_registry.py`) — human-verified-only event timing; a date without
      verified timing cannot reach `REGISTERED`; BMO/AMC/INTRADAY never inferred from price; `expected_response_session`
      always mechanically derived; corrections are amendment rows, originals never overwritten.
- [x] Phase 2 pre-event adapter (`phase2_adapter.py`) — explicit-path-only (no implicit "latest file" discovery),
      both input files hashed, marker cross-verified against the CSV rather than trusted blindly, `COMPLETE`/`PARTIAL`
      and all nulls/source statuses preserved exactly, generic panel IV never imported as `earnings_implied_move`,
      input files left byte-identical, research commit SHA + methodology version recorded.
- [x] Sector-ETF mapping mechanical review gate (`sector_mapping.py`) — exactly the locked 24 tickers, no
      duplicates/extras, valid ETF symbols, `mapping_version`/`review_status`/`reviewed_by`/`reviewed_at_utc` fields.
- [x] Amendment semantics deterministically proven (21 checks).

## Done — second pass (2026-08-04, this update)

- [x] **`AlpacaHistoricalSipIntradayProvider`** (`alpaca_provider.py`) — official REST endpoint, no SDK; bounded
      retries (429/5xx, `Retry-After` honored, capped), 401/403 never retried, `MAX_WALL_CLOCK_S=60`/`MAX_ATTEMPTS=5`/
      `MAX_PAGES=20` bounds, 15-minute freshness gate checked before any HTTP call, sanitized provenance (10 required
      fields), `BRK-B -> BRK.B` symbol translation with both identifiers always recorded, never falls back to
      IEX/yfinance/undocumented endpoints/synthetic bars, `is_eligible_for_real_event = True` (vs. `False` for
      yfinance, explicit). **43 deterministic checks, all passing. Never exercised against a real Alpaca response —
      credentials absent (see below).**
- [x] **Authoritative XNYS calendar** (`exchange_calendar.py`, `exchange_calendars==4.13.2` pinned in
      `requirements.txt`) — replaces the hand-maintained partial holiday list as the operational default (old list
      kept, unused, for auditability only). Ordinary/weekend/holiday/early-close/DST/AMC/BMO/INTRADAY/bar-boundary
      behavior all deterministically tested (29 checks).
- [x] **Sector-ETF mapping v0.2, `review_status: "APPROVED"`** — all 24 tickers individually reviewed. **GPN
      corrected XLK → XLF** (consistent with the 2023 GICS payment-processor reclassification).
      *(Superseded by v0.3 in the third pass: v0.2's framing treated ETF membership as the thing being verified,
      which was wrong in kind. See below.)*
- [x] **Phase 2 adapter dry run against a real preserved panel** — `GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv`
      + its completion marker (24 rows, `COMPLETE`), read-only. **24/24 tickers imported cleanly, `panel_status`
      preserved exactly, 24/24 eligible for `PRE_EVENT_CAPTURED`, both files byte-identical before/after.** Adapter
      confirmed operationally compatible with real panel output.
- [x] 116 new deterministic checks across 2 new test files (`test_market_response_alpaca_provider.py`: 43,
      `test_market_response_exchange_calendar.py`: 29) plus 7 additional checks added to the existing sector-mapping
      test file (13 → 20). Full 19-file deterministic suite (11 pre-existing Phase 2/Wikipedia + 8 market-response)
      passes with zero regressions — **638 total checks, all passing.**
- [ ] **Live Alpaca diagnostic (Section F): NOT RUN in that pass.** `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` were
      absent from the environment at preflight. Per instruction, the pass stopped before any live call rather than
      fake or claim a result. **Superseded by the third pass below, which ran it.**

## Done — third pass (2026-08-04, this update): live validation

- [x] **The live Alpaca diagnostic RAN**, exactly once per ticker, credentials present (values never printed,
      logged, serialized or committed). **Both diagnostics FAILED.** Full evidence, including every passing check
      and every discrepancy, is in `GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md` and the two committed
      sanitized reports.
  - Diagnostic A — SPY, 2026-08-03 session: HTTP 200, `feed=sip`/`timeframe=5Min`/`adjustment=raw` all confirmed on
    the wire, 1 page, 0 retries. **27/31 checks passed.** Failed on returning **79 bars instead of 78**, with a
    trailing bar starting 16:00 ET.
  - Diagnostic B — canonical `BRK-B` / provider `BRK.B`, same session: HTTP 200, **Alpaca echoed `"symbol":
    "BRK.B"`**. **25/29 checks passed**, failing on the identical four checks and no others.
- [x] **Open defect ALP-1 located, reproduced and pinned.** `end = session_close_utc` is treated inclusively by
      Alpaca, admitting one after-hours (16:00–16:05 ET) bar into every regular-session request. It silently became
      `session_close`, shifting SPY's `open_to_close` by 6.7 bp and full-session volume by 3.1%. **Fix prescribed
      but deliberately not applied** — it could not be live-validated in this pass (one-run-only rule), so it is
      pinned by characterization tests instead.
- [x] **Daily cross-check corroborates the root cause.** Aggregating only the 78 regular-session bars reproduces
      Alpaca's own 1Day SIP OHLC **exactly** (0.0 relative difference on open/high/low/close). Volume differs by
      **-15.50%** — reported as a separate finding: Alpaca's 1Day bar includes extended-hours volume, so a 1Day
      volume must never be compared against or substituted for a regular-session aggregate.
- [x] **`BRK-B -> BRK.B` symbol translation is now LIVE-VERIFIED** (server-side echo), no longer an assumption.
- [x] **Sector mapping corrected to v0.3** (`schema_version` 0.2) — the ETF is a **GICS-sector benchmark**, not a
      membership claim. `gics_sector`, `benchmark_etf`, `benchmark_basis`, `constituent_status`,
      `constituent_status_source`, `classification_source` and `retrieval_date` are now separate fields; the
      membership-count framing is gone entirely and is blocked by test. GPN stays XLF. **GME stays XLY**: its GICS
      Consumer Discretionary classification is authoritatively confirmed by S&P Dow Jones Indices (GICS co-owner),
      and it is recorded as a **confirmed nonconstituent** of XLY — structural, since XLY's universe is the S&P 500
      and GME is an S&P MidCap 400 member. GME is nowhere represented as an XLY holding.
- [x] **`APPROVED` is now mechanically conditional on all 24 entries actually having been reviewed** — any ticker
      lacking a `classification_source`/`retrieval_date`, or still `constituent_status="not_verified"`, makes an
      APPROVED mapping invalid (the same entry is fine while DRAFT).
- [x] **99 new deterministic checks** — `test_market_response_alpaca_diagnostic_harness.py` (47, new: proves the
      harness's own detectors are real), `test_market_response_alpaca_provider.py` (45 → 70), sector-mapping gate
      (20 → 47). **Full 20-file deterministic suite: 737 checks, all passing, zero regressions** (baseline 638 /
      19 files). All 17 untouched test files pass unchanged.

## Done — fourth pass (2026-08-04, this update): ALP-1 fix and post-fix validation

- [x] **Defect ALP-1 FIXED**, in three independent layers:
  1. **Request** — `end` is now the **final expected bar start** from `exchange_calendar.expected_bar_starts_utc()`
     (19:55Z / 15:55 ET), never `session_close_utc`. Derived dynamically, so an early close asks through 12:55 ET
     (42 bars) instead of a hard-coded 15:55.
  2. **Validation** — `_assert_exact_session_grid()` requires the returned timestamp set to **equal** the expected
     set. Missing, extra, duplicate, misaligned and out-of-session bars each raise `AlpacaSessionGridError`.
     Nothing trims, pads, re-sorts or de-duplicates.
  3. **Extraction** — `extract_session_fields()` selects open/close bars **by expected timestamp**, never
     `bars[0]`/`bars[-1]`. A stray 16:00 ET bar cannot become the close, set the high/low, or inflate volume even
     if layers 1–2 were bypassed. Extraction is now also order-independent.
- [x] **Post-fix live diagnostic PASSED**, one run per ticker, 2026-08-03 session, neither registering an event:
  - **SPY — 33/33 checks.** HTTP 200, `feed=sip`/`timeframe=5Min`/`adjustment=raw` on the wire, **78/78 bars,
    09:30 → 15:55 ET**, 0 off-grid, 0 missing, 1 page, 0 retries, raw SHA-256 `1313d07b…`.
  - **BRK-B (`BRK.B`) — 29/29 checks.** Same window and counts, Alpaca echoed `"symbol": "BRK.B"`, raw SHA-256
    `4d3c6713…`.
  - **Daily cross-check now matches exactly**: aggregated 78 × 5Min OHLC vs Alpaca's 1Day SIP bar gives **0.0**
    relative difference on open/high/low/close (749.44 / 758.58 / 748.80 / **757.67**). The contaminated pass-3
    aggregate had been 6.6 bp off on close.
- [x] **Eligibility split.** `supports_real_event_semantics` (structural, permanent) is now separate from
      `operational_clearance_status` (operational, changes over time), and `is_eligible_for_real_event` is
      **derived** from both via the pure `providers.compute_real_event_eligibility()`. It requires SIP feed, raw
      adjustment, the ALP-1 grid guard active, and credentials present. `NOT_RUN`, `LIVE_DIAGNOSTIC_FAILED`, an
      unrecognized status, `feed="iex"`, and yfinance are each ineligible on their own. Disabling the grid guard
      mechanically revokes clearance.
- [x] **Retraction.** The pass-3 claim that the −15.50% daily-vs-aggregate volume difference was "most likely"
      extended-hours volume is **withdrawn** — it was an unsupported guess. It is now classified
      **`unresolved_provider_aggregation_semantics`**: daily OHLC remains a gated sanity comparison (10 bp), daily
      volume is **informational only and not an equality gate** unless identical aggregation semantics are proven.
- [x] **89 new deterministic checks, 3 removed, net +86** — `test_market_response_alp1_session_grid.py` (79, new:
      request boundary, dynamic early-close end, extra 16:00 bar, missing 15:55 bar, missing interior bar,
      duplicates, unordered input, misalignment, premarket bar, exact-boundary extraction, order independence,
      and the full eligibility truth table), harness 47 → 57, provider 70 → 67 (the 3 removed are the ALP-1
      characterization checks, which asserted the *defective* boundary and were replaced — exactly as their own
      docstring instructed — by corrected-boundary assertions in the new file). **Full 21-file suite: 737 → 823
      checks, all passing, zero regressions**, verified in *both* clearance states.

## Done — fifth pass (2026-08-06, this update): cross-protocol integration hardening

Merging main (carrying the Event Dossier Protocol from PR #2) into this branch put Phase 2, the Event Dossier
Protocol and Market Response in one tree for the first time. Six integration defects surfaced and were fixed.
**No prospective event was selected or registered, no dossier was created, no panel was run, no live
market-data request or broker order was made, and no trading strategy was tested.**

- [x] **Session-vocabulary boundary** (`protocol_boundary.py`) — this module's `BMO`/`INTRADAY`/`AMC` and the
      protocol's `before_open`/`during_session`/`after_close` are both left unchanged; one pure, total translation
      function converts between them at the boundary. Exact, case-sensitive matching; `SessionVocabularyError` on
      unknown/blank/malformed/wrong-typed input; **never infers a session from a timestamp**. A test proves the
      shipped validator accepts the translated value and rejects the untranslated one.
- [x] **Phase 2 `complete_recent_cache_fallback` handled correctly** (`phase2_adapter.py`) — previously collapsed to
      `error`, mislabelling a Phase-2-complete observation as a failure. Now an explicit allowlist maps it to its own
      success category `ok_recent_cache_fallback` (never folded into plain `ok`, so cache-served data is never
      presented as fresh), with the exact original Phase 2 string preserved in new `source_status_*_raw` fields.
      Unknown non-blank statuses fail closed to `error` while retaining their raw value. Phase 2's own status values,
      completeness rules, source selection and panel output are untouched.
- [x] **Canonical drift guards** (`test_market_response_canonical_drift.py`) — the locked 24-ticker universe and the
      event-ID pattern are compared against their *executable* canonical definitions (`locked_universe_v0.1.json`
      and the validator module itself, loaded and executed rather than text-parsed). Any divergence, including
      ordering, now fails a test. Tickers and event-ID syntax unchanged. The stale comments claiming the protocol
      was unreachable from this branch are corrected.
- [x] **Layer B emission boundary** (`layer_b_addendum.py`) — the protocol's `market_response_addendum.csv` schema
      had no producer; it now has one. Column order read from the protocol's schema file. Only `COMPLETE`
      market-response records are eligible; PARTIAL/ABSTAIN and non-terminal states are refused; Layer A event and
      label must exist and agree; timestamps must be timezone-aware; `price_reaction_window` is required whenever
      `price_reaction_pct` is set. **Missing values stay empty and are never zero-filled**; a real measured `0.0` is
      preserved as `0.0`. Append-only and atomic — an existing `addendum_id` raises rather than being overwritten,
      an amendment leaves the original row byte-identical, and no Layer A table or freeze manifest is ever written.
      Emission is verified by running the real, unmodified validator over the combined fixture in all three modes.
      Per the protocol's corrected capture-vs-reveal rule (README 2026-08-02) and fixture
      `case_10_layerB_captured_before_freeze_unrevealed`, **capture is deliberately not gated on freeze** — reveal
      is, and reveal lives in the freeze manifest this emitter never touches.
- [x] **Real CI for this lane** (`.github/workflows/market-response-tests.yml`) — until now PR #3 had **no CI at
      all**, because the only workflow was path-filtered to `Event_Dossier_Protocol/**`. The new workflow discovers
      every `test_market_response*.py` (failing if discovery finds none), also runs the Event Dossier validator
      suite, uses least privilege and pinned Python/requirements, and never invokes the live smoke script, a
      provider diagnostic, the panel, or anything needing a credential or network.

Suite totals after this pass: Phase 2 **12 files / 617 assertions**; Market Response **15 files / 601 assertions**;
Event Dossier validator **27 e2e assertions + 21 unit tests**. All re-run with outbound sockets blocked.

## Done — tenth pass (2026-08-09): canonical absolute-response persistence

- [x] **The six SPEC v0.1 `abs_*` fields are now emitted.** `abs_overnight_gap`, `abs_open_to_30m`, `abs_thirty_min_to_close`, `abs_open_to_close` on D1; `abs_close_T1_to_close_T2`, `abs_close_T1_to_close_T3` on D3. Derived by `response_magnitude.apply_absolute_fields()` via the existing `derivations.abs_or_none()`; no signed-return formula is recomputed.
- [x] **Stored alongside, never replacing** — signed values unchanged; `0.0` → `0.0`; missing → `null`, never zero; no imputation, winsorization, clipping, rounding or outlier removal.
- [x] **Not a completeness requirement** — `D1_REQUIRED_FIELDS` and `D3_REQUIRED_FIELDS` unchanged; the fields are canonical derived outputs.
- [x] **Caller cannot choose them** — a disagreeing caller-supplied value raises `AbsoluteFieldConflictError` before the first byte, including before `D1_PENDING`.
- [x] **Persisted into the durable record and the markers** — D1/D3 state record plus a `response_magnitude` block in the `D1_CAPTURE` and `FINAL_COMPLETION` stage markers and the legacy completion marker; marker tie-out covers it.
- [x] **No backfill** — historical records are untouched and transparently ineligible for analyses requiring the fields.
- [x] **HYP-01 lock implementation status updated only** — `abs_overnight_gap` moves from `SPECIFIED_NOT_YET_EMITTED` to `IMPLEMENTED_AND_EMITTED` and is no longer blocking for freeze. The analytical definition, predictor, model, alpha, clustering, ordering and n=60 are unchanged.
- [x] **93 assertions** in `test_market_response_absolute_persistence.py`; the HYP-01 lock suite grows to 145 and now verifies the emitted claim against the real production path.

## Done — ninth pass (2026-08-08): second corrective audit of the v0.2 contract

- [x] **True atomic write-once** — `atomic_write_json_no_overwrite()` was `exists()` → `os.replace()`, a TOCTOU race that destroyed any artifact created in between. Now: write+fsync a temp file, then an exclusive `os.link()` create (`O_CREAT|O_EXCL` fallback), fsync the directory, clean up on every path. An existence check followed by `os.replace()` is prohibited.
- [x] **Dangling `PRE_EVENT_PENDING` is recoverable** — a crash between the two appends previously left the event permanently stuck. `PRE_EVENT_PENDING` now persists a canonical capture fingerprint; a rerun resumes **only** on an exact match, appends no duplicate pending, never deletes or rewrites the pending record, and never skips the strict gate. Mismatch, missing/non-recomputing fingerprint, or multiple pending records all fail closed.
- [x] **Correct per-leg statuses** — `panel_implied_volatility` → `iv_status`, `realized_volatility` → `realized_vol_status`; only `previous_close` and `volume` share `price_history_status`. A failed IV leg no longer passes the six-field gate because price history happened to be OK. Unknown statuses fail closed; normalised **and** raw values are persisted as provenance.
- [x] **`PARTIAL` is stage-specific** — every v0.2 `PARTIAL` carries `failure_stage` (`pre_event` / `d1` / `d3`). Pre-event selectors prefer `PRE_EVENT_CAPTURED` and accept only a pre-event `PARTIAL`; a D1/D3 failure can never erase or replace pre-event eligibility. Legacy records derive their stage from the chronology, never a default.
- [x] **Option inputs bound to validation** — the complete disposition artifact is canonicalised and hashed at validation; execution re-derives it and refuses on any change to status, reason or benchmark value, with zero writes.
- [x] **Blank and cross-row date validation** — blanks are no longer discarded before validating. Every row must carry a nonblank `price_asof_date` and `run_date`, each must resolve to exactly one value, `run_date >= price_asof_date` is asserted rather than skipped, and the anchor must equal `price_asof_date`.
- [x] **Legacy-gate bypass removed** — the capture entry point is split into `_v0_1` (legacy) and `_v0_2` (strict six-field). No unversioned public capture function exists; the old name raises with version guidance.
- [x] **Differential harness** — `test_market_response_second_pass_differential.py` restores each `ed4df74` defect in isolation and proves the corresponding regression depends on the fix.
- [x] **206 assertions** in the pre-event capture suite (13 required second-pass regressions plus crash injection at four points), and **26** in the differential harness.

## Done — eighth pass (2026-08-08): v0.2 contract formalised and hardened

- [x] **Formal v0.2 documents** — `SPEC_v0.2_DRAFT.md` and `FIELD_DICTIONARY_v0.2.md`; v0.1 preserved byte-for-byte.
- [x] **Strict six-field core gate** (`evaluate_strict_core_v0_2`) — all six panel fields present AND each backed by a successful source status; a legitimate `0.0` passes, missingness is never inferred from zero. The v0.1 gate is untouched.
- [x] **`panel_implied_volatility`** persisted as six-field provenance under a namespaced key; SPEC §5's prohibition on using panel IV as an implied-move baseline is **unchanged**.
- [x] **Full provenance persisted and marker tie-out** — 15 fields on the record, echoed field-for-field in every stage marker.
- [x] **TOCTOU closed** — execution re-hashes both panel files and re-runs anchor/status/strict-core checks before the first write; any drift fails with zero writes.
- [x] **Immutable stage markers** — write-once `PRE_EVENT_CAPTURE` / `D1_CAPTURE` / `FINAL_COMPLETION`; no path may unlink or overwrite to progress; deterministic crash recovery that regenerates only a *missing* marker and fails closed on a mismatched one.
- [x] **`check_required_gate` corrected** — reads the record for the tier being checked, not the latest record.
- [x] **`VALID_VERIFIED` refused by the CLI** — no hand-written JSON can assert OPRA verification.
- [x] **Authoritative session date** — the anchor binds to `price_asof_date`, never `run_date` or a truncated UTC timestamp; ambiguity fails closed.
- [x] **Stage vocabulary corrected** — the state machine implements D1 and D3; the D3 tier carries the D2 close-to-close measurement; the D2 *session* is owned by `operations_plan.py`. No D2 state was invented.
- [x] **122 assertions** in the pre-event capture suite.

## Done — seventh pass (2026-08-08): protocol v0.2 amendment + pre-event capture orchestrator

**Authorized methodology amendment, made before any prospective observation exists.** `EVT-DELL-FY27Q2-ERN` remains **`REGISTERED`**; no pre-event snapshot, market-response observation, dossier, or Layer B record exists, and no DELL attention/price/volume/volatility/options/earnings/consensus/analyst data was inspected. The human-verified timing registry was **not** amended — no timing fact changed.

- [x] **Protocol v0.2 — lifecycle/eligibility separation.** v0.1 required both the core gate *and* the option gate for `PRE_EVENT_CAPTURED`, so an unavailable **optional** option benchmark forced `PARTIAL` (terminal) and made D1/D2/D3 uncollectable. Lifecycle state now records collection; analytical eligibility is per-module (`core_pre_event_eligible`, `option_benchmark_eligible`, `joint_full_eligible`, `pre_event_completeness_tier`, `option_benchmark_status`, `option_benchmark_unavailable_reason`). **No existing threshold, required-field list, quote-age limit or skew limit was changed.**
- [x] **Explicit option disposition** — `VALID_VERIFIED` / `UNAVAILABLE_NO_VERIFIED_SOURCE` / `LOOKUP_FAILED` / `NOT_ATTEMPTED`. Unavailability is never inferred from `{}` or nulls; unknown/blank fails closed; indicative can be neither relabelled as unavailable nor promoted to OPRA; a supplied-but-invalid artifact is rejected with zero writes; legacy v0.1 records raise an explicit migration error rather than being reinterpreted.
- [x] **A core-only event is never full-data complete.** It may reach lifecycle `COMPLETE`, but the completion marker carries the `core_only_no_option_benchmark` tier and `is_full_data_complete: false`, and it is mechanically excluded from options-implied-move and joint hypotheses.
- [x] **Pre-event capture orchestrator** (`pre_event_capture.py` + `pre_event_capture_cli.py`) — connects existing components only; never contacts a provider; read-only by default; `--execute` required; no force/override/skip/allow-stale flag exists; validation completes before the first byte; collisions and repeat runs fail closed with zero additional bytes.
- [x] **84 new deterministic assertions**; `test_market_response_decomposition.py` now 87.

**Deliberately still not done:** no real capture has occurred, and the options benchmark remains unavailable (Alpaca entitlement INCONCLUSIVE). The amendment makes that situation survivable; it does not resolve it.

## Done — sixth pass (2026-08-07): DELL FY27 Q2 registered, offline operational plan built

**The first prospective event is registered.** `EVT-DELL-FY27Q2-ERN` (Dell Technologies Inc., FY27 Q2) is preregistered on `main` via PR #4 and remains in state **`REGISTERED` only**. **No pre-event snapshot has been taken**, and no market, attention, option, consensus, or earnings-result data has been inspected — for selection or since. This pass tests no strategy and produces no research result.

- [x] **Deterministic operations planner** (`operations_plan.py` + plan-only `operations_cli.py`) — derives the schedule from the merged XNYS calendar and the verified registry row; reimplements no trading-day arithmetic. Fail-closed on absent, duplicated, unverified, amended-into-unusable, wrong-calendar, missing/naive-timestamp, non-locked-universe and malformed-id events, and on an AMC/BMO claim that disagrees with the session close/open.
- [x] **DELL schedule derived** — anchor **2026-09-02**, release **2026-09-03T20:30:00Z (AMC)**, **D1 2026-09-04**, **D2 2026-09-08**, **D3 2026-09-09**; 2026-09-07 (Labor Day) plus the weekend recorded as non-sessions. Each session carries UTC + ET open/close and the earliest freshness-gate-permitted retrieval instant.
- [x] **Structurally offline** — no provider imported or constructed, no socket, no credential, no event-state transition, no registry write. Proven by AST checks and subprocess isolation with providers import-blocked and `socket.connect` patched to raise.
- [x] **Versioned plan + runbook** in `Live Signal Engine/Event_Operations/EVT-DELL-FY27Q2-ERN/`, with a deterministic `plan_content_sha256`; the CLI refuses to overwrite an existing plan.
- [x] **89 new deterministic assertions** (`test_market_response_operations_plan.py`).

**Not done in this pass, deliberately:** no live capture runner was built. The capture-gap audit found **no end-to-end pre-event capture command exists**, with three hard blockers (BLK-OPT-1/2, BLK-ORCH-1) and two material ones (BLK-STALE-1, BLK-PANEL-1) carried inside the plan. See the blocker list below.

## NOT done — remaining blockers before the first real event can be registered

0. **A Layer A dossier for the chosen event must exist before Layer B can be emitted for it.** The emitter refuses
   an addendum whose Layer A event/label is absent or disagrees. Emission has only ever been exercised against
   synthetic fixtures; it has never run against a real dossier, by design.
1. **One complete prospective earnings event is still required.** This is now the primary blocker. Nothing about a
   benchmark-ticker diagnostic on a historical session substitutes for capturing one real event end to end.
2. **Clearance rests on one session and two benchmark tickers.** Neither ticker is in the locked 24-ticker
   universe, and no early-close session has been live-validated (the early-close path is deterministically tested,
   not live-tested). The vendor's 1Day aggregation semantics remain unresolved.
3. **`YFinanceDevIntradayProvider` remains explicitly ineligible** (`is_eligible_for_real_event = False`) and its
   one live diagnostic to date FAILED (2026-08-04, SPY, root cause likely environment-specific, not remediated).
   Not a blocker for Alpaca-based capture, but yfinance itself is not, and will not become, usable for a real event.
4. **No `EventTimingProvider` other than the human-verified registry exists** (by design). A real event still
   requires a human to manually verify and enter its timing.
5. **Sector-mapping source quality.** For the 22 tickers whose GICS sector was established via confirmed
   Select-Sector-ETF membership, the membership evidence is a third-party aggregator's holdings page, not an
   issuer-published holdings file. The inference is sound but the observation is one source tier below ideal; this
   is disclosed in the mapping file itself.
6. **No live wiring exists between the Phase 2 adapter and a currently-running Phase 2 panel process** — the dry
   run proved compatibility with one real, already-completed panel output; it has never been invoked as part of an
   active capture pipeline.
7. **No Radar integration, no strategy test, no backtest** — all explicitly out of scope for this and every prior
   pass in this lane.
8. **This branch is still stacked on, and must not be merged ahead of, PR #1.**

## Explicit statements (restated per instruction)

- YFinance remains a development provider.
- The event registry requires human-verified primary-source timing.
- No trading strategy is selected.
- No profitability claim exists.
- The first real event has not yet been registered.
