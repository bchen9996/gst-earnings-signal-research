# Market Response — Operational Readiness Checklist (v0.1)

Status as of the 2026-08-04 **live-validation pass** (third pass; PR #3, branch `phase2-market-response`, stacked
on PR #1). **No real event has been registered. No trading strategy is selected. No profitability claim exists.**

**Provider status: `LIVE_DIAGNOSTIC_FAILED` — the Alpaca provider is INELIGIBLE for real event capture.** The one
permitted live diagnostic ran and failed on a located, reproduced request-window defect (ALP-1). This is *not*
"fully production-validated", and it is not partially validated either: the status rule for a failed SPY
diagnostic is that the provider stays ineligible. No fallback to IEX, yfinance, Yahoo, any other provider, or
synthetic data was made or considered.

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

## NOT done — remaining blockers before the first real event can be registered

1. **ALP-1 is unfixed and the Alpaca provider is INELIGIBLE.** Its one live diagnostic failed. The fix is
   prescribed and the defect is pinned by tests, but neither the fix nor a passing live diagnostic exists yet.
   **A live diagnostic must be re-run, and pass, before any real capture.** Note `is_eligible_for_real_event` still
   returns `True` in code — that flag describes the provider's *class* (a real SIP provider, unlike yfinance), not
   its current validation state, and it must not be read as clearance.
2. **One complete prospective earnings event is still required** before this lane can be called production-ready,
   independently of ALP-1. Nothing about a benchmark-ticker diagnostic substitutes for capturing one real event end
   to end.
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
