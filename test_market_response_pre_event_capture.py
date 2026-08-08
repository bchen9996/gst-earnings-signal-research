#!/usr/bin/env python3
# Deterministic tests for protocol amendment v0.2 (lifecycle/eligibility
# separation) and the pre-event capture orchestrator.
#
# Synthetic fixtures and temporary directories only. No operational artifact is
# ever a writable target. No provider is imported or constructed, no socket is
# opened, no credential is read. The real DELL event is never touched.
#
# Run directly: python test_market_response_pre_event_capture.py

from __future__ import annotations

import ast
import csv
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from datetime import timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.completeness import (
    FULL_DATA_COMPLETE_TIER,
    HYPOTHESIS_CORE_ATTENTION_RESPONSE,
    HYPOTHESIS_JOINT_ATTENTION_OPTIONS,
    HYPOTHESIS_OPTIONS_IMPLIED_MOVE,
    PRE_EVENT_TIER_CORE_INVALID,
    PRE_EVENT_TIER_CORE_ONLY,
    PROTOCOL_VERSION,
    LegacyRecordError,
    OptionBenchmarkDisposition as D,
    OptionDispositionError,
    evaluate_pre_event_modules,
    is_eligible_for_hypothesis,
    is_full_data_complete,
    read_module_eligibility,
)
from gst_market_response.completion_marker import write_completion_marker
from gst_market_response.event_record import EventStore
from gst_market_response.event_registry import HumanVerifiedEventRegistry
from gst_market_response.pipeline import (
    capture_d1,
    capture_d3,
    capture_pre_event_and_option_benchmark_v0_1,
)
from gst_market_response.pre_event_capture import (
    PreEventCaptureError,
    execute_pre_event_capture,
    validate_pre_event_capture,
)

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
UTC = timezone.utc
NOW = datetime.datetime(2026, 9, 2, 21, 0, tzinfo=UTC)
EVENT = "EVT-DELL-FY27Q2-ERN"
ANCHOR = "2026-09-02"

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def expect_raises(label, exc_type, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc_type:
        print(f"PASS: {label}")
    except Exception as e:
        print(f"FAIL: {label} (raised {type(e).__name__}, expected {exc_type.__name__})")
        FAILURES.append(label)
    else:
        print(f"FAIL: {label} (did not raise)")
        FAILURES.append(label)


CORE = {"previous_close": 101.5, "pre_event_snapshot_asof_utc": "2026-09-02T20:00:00+00:00",
        "gst_zscore": 1.2, "source_status_gst": "ok"}
CORE_BAD = {"previous_close": None, "pre_event_snapshot_asof_utc": None}
OPT_VALID = {"option_benchmark_status": D.VALID_VERIFIED, "option_feed": "opra",
             "contract_selection_status": "ok", "expiration": "2026-09-04",
             "underlying_price": 101.5, "quote_timestamp_utc": "2026-09-02T19:59:30+00:00",
             "straddle_mid": 4.2}
OPT_NONE = {"option_benchmark_status": D.UNAVAILABLE_NO_VERIFIED_SOURCE,
            "option_benchmark_unavailable_reason": "no OPRA-entitled source available",
            "expiration": None, "underlying_price": None, "quote_timestamp_utc": None,
            "straddle_mid": None, "long_executable_implied_move_cost": None}


def _nulls(status, reason):
    return {"option_benchmark_status": status, "option_benchmark_unavailable_reason": reason,
            "expiration": None, "underlying_price": None, "quote_timestamp_utc": None,
            "straddle_mid": None, "long_executable_implied_move_cost": None}


# ============================ A. protocol semantics =========================

def test_1_core_valid_options_valid():
    with tempfile.TemporaryDirectory() as t:
        s = EventStore(Path(t)); s.append_state(EVENT, "REGISTERED", {})
        st = capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_VALID)
        e = read_module_eligibility([r for r in s.read_all(EVENT) if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"])
        check("1. core valid + options valid -> PRE_EVENT_CAPTURED", st == "PRE_EVENT_CAPTURED")
        check("1b. all three eligibility flags true",
              e.core_pre_event_eligible and e.option_benchmark_eligible and e.joint_full_eligible)
        check("1c. tier is the full core+option tier", e.pre_event_completeness_tier == FULL_DATA_COMPLETE_TIER)


def test_2_core_valid_options_unavailable():
    with tempfile.TemporaryDirectory() as t:
        s = EventStore(Path(t)); s.append_state(EVENT, "REGISTERED", {})
        st = capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
        e = read_module_eligibility([r for r in s.read_all(EVENT) if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"])
        check("2. core valid + explicit no verified source -> PRE_EVENT_CAPTURED", st == "PRE_EVENT_CAPTURED")
        check("2b. core eligible, option ineligible, joint ineligible",
              e.core_pre_event_eligible and not e.option_benchmark_eligible and not e.joint_full_eligible)
        check("2c. tier is core-only", e.pre_event_completeness_tier == PRE_EVENT_TIER_CORE_ONLY)
        check("2d. reason recorded", bool(e.option_benchmark_unavailable_reason))


def test_3_4_5_6_core_only_lifecycle_and_hypotheses():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = EventStore(root); s.append_state(EVENT, "REGISTERED", {})
        capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
        d1 = capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                                   "thirty_min_to_close": 0.01, "open_to_close": 0.02})
        d3 = capture_d3(s, EVENT, {"close_T1_to_close_T2": 0.01, "close_T1_to_close_T3": 0.02})
        check("3. a core-only event can capture D1", d1 == "D1_COMPLETE")
        check("3b. ...and D3", d3 == "COMPLETE")
        m = write_completion_marker(root, EVENT, s)
        check("4. lifecycle reaches COMPLETE", m["final_state"] == "COMPLETE")
        check("4b. its lower tier is preserved and visible in the marker",
              m["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)
        check("4c. the marker states it is NOT full-data complete", m["is_full_data_complete"] is False)
        e = read_module_eligibility([r for r in s.read_all(EVENT) if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"])
        check("5. excluded from options-implied-move analyses",
              not is_eligible_for_hypothesis(HYPOTHESIS_OPTIONS_IMPLIED_MOVE, e))
        check("5b. excluded from joint analyses",
              not is_eligible_for_hypothesis(HYPOTHESIS_JOINT_ATTENTION_OPTIONS, e))
        check("6. still eligible for the core attention-vs-response family",
              is_eligible_for_hypothesis(HYPOTHESIS_CORE_ATTENTION_RESPONSE, e))
        check("16. lifecycle COMPLETE alone cannot satisfy full analytical eligibility",
              is_full_data_complete("COMPLETE", e) is False)


def test_7_8_core_invalid_is_partial_terminal():
    for label, opt in [("7. core invalid + options valid", OPT_VALID),
                       ("8. core invalid + options unavailable", OPT_NONE)]:
        with tempfile.TemporaryDirectory() as t:
            s = EventStore(Path(t)); s.append_state(EVENT, "REGISTERED", {})
            st = capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE_BAD, opt)
            check(f"{label} -> PARTIAL-terminal", st == "PARTIAL")
            from gst_market_response.event_record import InvalidStateTransitionError
            try:
                capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                                      "thirty_min_to_close": 0.01, "open_to_close": 0.02})
                blocked = False
            except InvalidStateTransitionError:
                blocked = True
            check(f"{label} -> D1 blocked (terminal preserved)", blocked)


def test_9_to_15_disposition_contract():
    expect_raises("9. empty options dict without a disposition fails",
                  OptionDispositionError, evaluate_pre_event_modules, CORE, {})
    expect_raises("9b. null-only dict without a disposition fails",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {"expiration": None, "underlying_price": None})
    expect_raises("10. supplied-but-invalid artifact fails (VALID_VERIFIED, gate fails)",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {**OPT_VALID, "contract_selection_status": "rejected_bid_gt_ask"})
    expect_raises("10b. crossed/absent required field fails",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {**OPT_VALID, "quote_timestamp_utc": None})
    expect_raises("11. indicative quotes cannot pass as OPRA",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {**OPT_VALID, "option_feed": "indicative"})
    expect_raises("11b. VALID_VERIFIED without a stated feed fails",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {k: v for k, v in OPT_VALID.items() if k != "option_feed"})
    expect_raises("11c. indicative may not be relabelled as unavailable while carrying values",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {**OPT_NONE, "option_benchmark_status": D.UNAVAILABLE_NO_VERIFIED_SOURCE,
                   "straddle_mid": 4.2})
    e = evaluate_pre_event_modules(CORE, OPT_NONE)
    check("12. missing options are null, never zero",
          all(OPT_NONE[k] is None for k in ("expiration", "underlying_price",
                                            "quote_timestamp_utc", "straddle_mid")))
    lf = evaluate_pre_event_modules(CORE, _nulls(D.LOOKUP_FAILED, "provider returned no chain"))
    na = evaluate_pre_event_modules(CORE, _nulls(D.NOT_ATTEMPTED, "no entitled source configured"))
    check("13. LOOKUP_FAILED is distinct from UNAVAILABLE_NO_VERIFIED_SOURCE",
          lf.option_benchmark_status != e.option_benchmark_status)
    check("14. NOT_ATTEMPTED is distinct from both",
          na.option_benchmark_status not in (lf.option_benchmark_status, e.option_benchmark_status))
    check("14b. none of the three is analytically eligible",
          not any(x.option_benchmark_eligible for x in (e, lf, na)))
    expect_raises("15. unknown status fails closed",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {"option_benchmark_status": "SOMETHING_ELSE"})
    expect_raises("15b. blank status fails closed",
                  OptionDispositionError, evaluate_pre_event_modules, CORE,
                  {"option_benchmark_status": "   "})


def test_17_18_unchanged_and_legacy():
    e = evaluate_pre_event_modules(CORE, OPT_VALID)
    check("17. existing valid full-benchmark behaviour unchanged (all flags true, full tier)",
          e.core_pre_event_eligible and e.option_benchmark_eligible and e.joint_full_eligible
          and e.pre_event_completeness_tier == FULL_DATA_COMPLETE_TIER)
    expect_raises("18. a legacy v0.1 record raises an explicit migration error, never silent reinterpretation",
                  LegacyRecordError, read_module_eligibility,
                  {"previous_close": 101.5, "expiration": "2026-09-04"})
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = EventStore(root)
        s.append_state(EVENT, "REGISTERED", {})
        s.append_state(EVENT, "PRE_EVENT_PENDING", {})
        s.append_state(EVENT, "PRE_EVENT_CAPTURED", {"previous_close": 101.5})  # legacy shape
        m = write_completion_marker(root, EVENT, s)
        check("18b. the marker reports a legacy record explicitly and refuses full-data completeness",
              m["module_eligibility"] is None and m["is_full_data_complete"] is False
              and "legacy" in m["module_eligibility_note"].lower())


# ======================= B. orchestrator (synthetic) ========================

# The real Phase 2 panel emits FIVE independent per-leg statuses. The fixture
# now carries all five (verified against the real
# GST_Phase2_DailyPanel_TestRun_2026-07-30_run3.csv header), because backing
# implied volatility and realized volatility with price_history_status was the
# defect FIX 3 corrects -- a fixture omitting those columns cannot exercise it.
_PANEL_COLS = ["run_date", "price_asof_date", "ticker", "gst_status", "wiki_status",
               "price_history_status", "iv_status", "realized_vol_status",
               "gst_zscore", "wiki_zscore", "realized_vol", "price",
               "volume", "days_to_nearest_earnings", "retrieval_timestamp_utc",
               "all_six_fields_clean", "implied_volatility"]
METH = "market_response_v0.2"


def synth_panel(tmp: Path, run_date: str = ANCHOR, ticker: str = "DELL", rows: int = 1,
                zero_missing: bool = False, marker_status: str = "COMPLETE",
                break_marker: bool = False, price_asof: str | None = None,
                iv: str = "0.31", drop_asof_col: bool = False,
                asof_ambiguous: bool = False, name: str = "SYNTHETIC_panel.csv",
                iv_status: str = "ok", realized_vol_status: str = "ok",
                other_tickers: tuple[str, ...] = (),
                blank_asof_rows: tuple[int, ...] = (),
                blank_run_rows: tuple[int, ...] = (),
                run_date_by_row: dict[int, str] | None = None,
                drop_run_date_col: bool = False) -> tuple[Path, Path]:
    """SYNTHETIC panel fixture -- NOT RESEARCH DATA.

    `run_date` is when the panel RAN; `price_asof` is the SESSION its price data
    is as-of. They legitimately differ (a real panel runs after UTC midnight
    following the session), which is why the anchor binds to price_asof.

    `other_tickers` adds rows for DIFFERENT tickers, so a multi-row date defect
    can be exercised without tripping the adapter's duplicate-ticker refusal
    first. `blank_asof_rows` / `blank_run_rows` / `run_date_by_row` inject
    per-row date defects by index across the whole panel.
    """
    asof = price_asof if price_asof is not None else run_date
    csv_path, marker_path = tmp / name, tmp / (name.replace(".csv", "_marker.json"))
    recs = []
    row_tickers = [ticker] * rows + list(other_tickers)
    for i, row_ticker in enumerate(row_tickers):
        recs.append({"run_date": run_date,
                     "price_asof_date": (f"{asof}" if not asof_ambiguous or i == 0 else "2026-08-28"),
                     "ticker": row_ticker, "gst_status": "ok",
                     "wiki_status": "ok" if not zero_missing else "incomplete_watermark_unavailable",
                     "price_history_status": "ok",
                     "iv_status": iv_status, "realized_vol_status": realized_vol_status,
                     "gst_zscore": "1.2",
                     "wiki_zscore": "0" if zero_missing else "2.5", "realized_vol": "0.21",
                     "price": "101.5", "volume": "1000000", "days_to_nearest_earnings": "1",
                     "retrieval_timestamp_utc": f"{run_date}T04:40:00+00:00",
                     "all_six_fields_clean": "True", "implied_volatility": iv})
    for i in blank_asof_rows:
        recs[i]["price_asof_date"] = ""
    for i in blank_run_rows:
        recs[i]["run_date"] = ""
    for i, value in (run_date_by_row or {}).items():
        recs[i]["run_date"] = value
    cols = [c for c in _PANEL_COLS
            if not (drop_asof_col and c == "price_asof_date")
            and not (drop_run_date_col and c == "run_date")]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in recs:
            w.writerow(r)
    marker = {"status": marker_status, "row_count": len(recs) if not break_marker else len(recs) + 7,
              "unique_ticker_count": len({r["ticker"] for r in recs}),
              "all_six_fields_clean_count": len(recs)}
    marker_path.write_text(json.dumps(marker), encoding="utf-8", newline="\n")
    return csv_path, marker_path


def synth_registry(tmp: Path) -> Path:
    # Idempotent: the registry is append-only, so re-registering on a repeated
    # _validate() call in the same temp dir would create a genuine duplicate
    # REGISTRATION row and mask the behaviour under test.
    existing = tmp / "reg" / "registry.jsonl"
    if existing.exists():
        return existing
    r = HumanVerifiedEventRegistry(tmp / "reg")
    r.register_verified_event(
        ticker="DELL", fiscal_period="FY27Q2", earnings_date=datetime.date(2026, 9, 3),
        earnings_datetime_utc=datetime.datetime(2026, 9, 3, 20, 30, tzinfo=UTC),
        release_market_session="AMC", source_url="https://example.invalid/ir",
        source_title="t", source_type="company_ir_events_calendar",
        source_retrieved_at_utc=datetime.datetime(2026, 8, 7, tzinfo=UTC),
        verified_at_utc=datetime.datetime(2026, 8, 7, tzinfo=UTC),
        verified_by="tester", verification_status="verified", notes="SYNTHETIC")
    return tmp / "reg" / "registry.jsonl"


def _validate(tmp: Path, *, csv_p, marker_p, anchor=ANCHOR, opt=None, store=None):
    return validate_pre_event_capture(
        registry_path=synth_registry(tmp), event_id=EVENT, company_name="Dell Technologies Inc.",
        expected_anchor_session=anchor, panel_csv=csv_p, panel_marker=marker_p,
        store_root=store or (tmp / "store"), research_commit_sha="deadbeef",
        methodology_version=METH,
        option_benchmark_fields=opt if opt is not None else OPT_NONE, now_utc=NOW)


def test_orchestrator_validation_matrix():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp)
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("21. validation mode passes on a good synthetic fixture", rep.ok())
        check("21b. validation mode wrote nothing", not (tmp / "store").exists())
        check("5b(orch). anchor derived mechanically as 2026-09-02", rep.derived_anchor_session == ANCHOR)
        check("2e. option module recorded as explicitly unavailable",
              rep.eligibility["option_benchmark_eligible"] is False
              and rep.eligibility["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-01")
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("3(orch). stale panel from the prior session is rejected",
              not rep.ok() and any(x["check"] == "panel_is_anchor_session" and not x["passed"] for x in rep.checks))
        check("3b(orch). ...with zero writes", not (tmp / "store").exists())

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-03")
        check("4(orch). future-dated panel rejected", not _validate(tmp, csv_p=c, marker_p=m).ok())

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp)
        check("5(orch). wrong expected anchor rejected",
              not _validate(tmp, csv_p=c, marker_p=m, anchor="2026-09-01").ok())

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, break_marker=True)
        expect_raises("7(orch). marker/CSV count mismatch rejected",
                      PreEventCaptureError, _validate, tmp, csv_p=c, marker_p=m)

    with tempfile.TemporaryDirectory() as t:
        # The EXISTING phase2 adapter already fails closed on an ambiguous ticker,
        # so this raises rather than returning a failed report -- the stronger
        # outcome, and the reason the orchestrator reuses it instead of
        # reimplementing uniqueness itself.
        tmp = Path(t); c, m = synth_panel(tmp, rows=2)
        expect_raises("8(orch). duplicate DELL row rejected by the existing adapter",
                      PreEventCaptureError, _validate, tmp, csv_p=c, marker_p=m)

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, ticker="MSFT")
        expect_raises("9/10(orch). missing DELL row / wrong ticker mapping rejected",
                      PreEventCaptureError, _validate, tmp, csv_p=c, marker_p=m)

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, marker_status="PARTIAL")
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("12(orch). PARTIAL panel fails the status check",
              any(x["check"] == "panel_status_complete" and not x["passed"] for x in rep.checks))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, zero_missing=True)
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("12b(orch). a missing six-field value encoded as 0 is rejected",
              any(x["check"] == "no_missing_six_field_value_encoded_as_zero" and not x["passed"]
                  for x in rep.checks))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp)
        expect_raises("14(orch). indicative option artifact rejected", PreEventCaptureError,
                      _validate, tmp, csv_p=c, marker_p=m, opt={**OPT_VALID, "option_feed": "indicative"})
        expect_raises("15(orch). option artifact with no timestamp rejected", PreEventCaptureError,
                      _validate, tmp, csv_p=c, marker_p=m,
                      opt={**OPT_VALID, "quote_timestamp_utc": None})
        expect_raises("17(orch). crossed/invalid quote artifact rejected", PreEventCaptureError,
                      _validate, tmp, csv_p=c, marker_p=m,
                      opt={**OPT_VALID, "contract_selection_status": "rejected_bid_gt_ask"})


def test_execute_writes_and_collisions():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        res = execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                        ticker="DELL", research_commit_sha="deadbeef",
                                        methodology_version=METH,
                                        option_benchmark_fields=OPT_NONE)
        check("22. execution captured after full validation", res["state"] == "PRE_EVENT_CAPTURED")
        log = store / f"{EVENT}.jsonl"
        before = log.read_bytes()
        rep2 = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("18(orch). an existing pre-event stage is detected as a collision",
              any(x["check"] == "no_existing_pre_event_stage" and not x["passed"] for x in rep2.checks))
        check("19(orch). an existing immutable stage marker is detected as a collision",
              any(x["check"] == "no_existing_pre_event_stage_marker" and not x["passed"] for x in rep2.checks))
        expect_raises("20. repeated execution refuses (byte-idempotent by refusal)",
                      PreEventCaptureError, execute_pre_event_capture, report=rep, store_root=store,
                      panel_csv=c, panel_marker=m, ticker="DELL", research_commit_sha="deadbeef",
                      methodology_version=METH, option_benchmark_fields=OPT_NONE)
        check("20b. the refusal added zero bytes", log.read_bytes() == before)

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-01"); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        expect_raises("23. execution on a failing report is refused",
                      PreEventCaptureError, execute_pre_event_capture, report=rep, store_root=store,
                      panel_csv=c, panel_marker=m, ticker="DELL", research_commit_sha="deadbeef",
                      methodology_version=METH, option_benchmark_fields=OPT_NONE)
        check("23b. ...leaving no artifact at all", not store.exists())


# Child program for test_25. Kept as a module constant so the test can assert
# structurally on the blocker's own implementation.
#
# WHY find_spec AND NOT find_module (2026-08-08 correction):
# the previous version installed a meta-path finder exposing only the legacy
# `find_module` hook. That hook is not consulted by the modern import system --
# it was deprecated in 3.4 and REMOVED in 3.12 -- so on this project's Python
# the blocker was a silent no-op: `requests`, `yfinance` and `pytrends` all
# imported straight through it. The surrounding LEAKED assertion still held
# honestly (the orchestrator genuinely imports no provider), so the test never
# went red, but its blocker was proving nothing. `find_spec` is the hook the
# import system actually calls, on 3.12 and on 3.14 alike.
#
# The blocker raises a DISTINCTIVE ImportError subclass carrying a unique
# token, so a pass cannot be produced by the package simply being absent from
# the environment: absence yields a plain ModuleNotFoundError, which the test
# rejects.
_BLOCKER_TOKEN = "PROVIDER-IMPORT-BLOCKED-BY-TEST-HARNESS"

_BLOCKER_CHILD_SRC = """
import importlib, sys

TOKEN = {token!r}
BANNED_TOP = ('yfinance', 'pytrends', 'requests', 'urllib3')
BANNED_FULL = ('urllib.request',)
ATTEMPTS = []


class ProviderImportBlocked(ImportError):
    '''Distinctive: proves THIS blocker rejected the import, not absence.'''


class ProviderBlocker:
    # find_spec only. find_module is the legacy hook, ignored by the modern
    # import system and removed in 3.12 -- defining it here would recreate the
    # exact no-op this test was corrected for.
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in BANNED_TOP or fullname in BANNED_FULL:
            ATTEMPTS.append(fullname)
            raise ProviderImportBlocked(TOKEN + ': ' + fullname)
        return None


import socket

def boom(*a, **k):
    raise AssertionError('network during capture')

saved_meta = list(sys.meta_path)
saved_connect = socket.socket.connect
saved_connect_ex = socket.socket.connect_ex
saved_create = socket.create_connection
saved_getaddrinfo = socket.getaddrinfo
saved_modules = set(sys.modules)

try:
    sys.meta_path.insert(0, ProviderBlocker())
    socket.socket.connect = boom
    socket.socket.connect_ex = boom
    socket.create_connection = boom
    socket.getaddrinfo = boom

    # -- positively verify the socket blocker (loopback discard port; the
    #    patch raises before any syscall, so nothing is dialled) ------------
    try:
        socket.create_connection(('127.0.0.1', 9), timeout=1)
        print('SOCKET_BLOCKED=False')
    except AssertionError:
        print('SOCKET_BLOCKED=True')

    # -- explicitly attempt every banned provider import -------------------
    results = {{}}
    for name in ('requests', 'yfinance', 'pytrends'):
        try:
            importlib.import_module(name)
            results[name] = 'IMPORTED'
        except ProviderImportBlocked as e:
            results[name] = 'BLOCKED' if TOKEN in str(e) else 'WRONG_ERROR'
        except ImportError:
            # A plain ImportError/ModuleNotFoundError means the package was
            # merely absent -- the blocker proved nothing. That is a failure.
            results[name] = 'PLAIN_IMPORTERROR'
    print('BLOCK_RESULTS=' + repr(results))
    print('OBSERVED=' + repr(sorted(set(ATTEMPTS))))
    print('NOT_IN_SYS_MODULES=' + repr(
        all(n not in sys.modules for n in ('requests', 'yfinance', 'pytrends'))))

    # -- the v0.2 orchestrator and CLI must IMPORT and RUN under both -------
    import gst_market_response.pre_event_capture as pec
    import gst_market_response.pre_event_capture_cli as cli
    from gst_market_response.completeness import evaluate_strict_core_v0_2
    from gst_market_response.capture_fingerprint import compute_capture_fingerprint
    fp = compute_capture_fingerprint(
        event_id='X', ticker='AAPL', anchor_session='2026-09-02',
        panel_csv_sha256='0' * 64, panel_marker_sha256='1' * 64,
        research_commit_sha='deadbeef', methodology_version='market_response_v0.2',
        option_fields={{'option_benchmark_status': 'NOT_ATTEMPTED'}})
    ran = (evaluate_strict_core_v0_2({{}}).passed is False
           and '--execute' in {{o for a in cli._parser()._actions for o in a.option_strings}}
           and bool(pec.ORCHESTRATOR_VERSION)
           and len(fp['capture_fingerprint_sha256']) == 64)
    print('V02_RUNS=' + repr(bool(ran)))

    leaked = [m for m in ('yfinance', 'requests', 'pytrends',
                          'gst_market_response.alpaca_provider') if m in sys.modules]
    print('LEAKED=' + repr(leaked))
    print('OK')
finally:
    # Restore everything, even on failure.
    sys.meta_path[:] = saved_meta
    socket.socket.connect = saved_connect
    socket.socket.connect_ex = saved_connect_ex
    socket.create_connection = saved_create
    socket.getaddrinfo = saved_getaddrinfo
    for _m in [m for m in sys.modules if m not in saved_modules]:
        del sys.modules[_m]
    print('RESTORED=' + repr(
        sys.meta_path == saved_meta
        and socket.socket.connect is saved_connect
        and socket.socket.connect_ex is saved_connect_ex
        and socket.create_connection is saved_create
        and socket.getaddrinfo is saved_getaddrinfo
        and set(sys.modules) == saved_modules))
""".format(token=_BLOCKER_TOKEN)


def test_25_no_network_and_no_provider():
    proc = subprocess.run([sys.executable, "-c", _BLOCKER_CHILD_SRC],
                          cwd=str(HERE), capture_output=True, text=True)
    out = proc.stdout
    check("25. orchestrator+CLI import with every provider blocked and sockets poisoned",
          proc.returncode == 0 and "OK" in out)
    check("25b. no provider or network client reaches sys.modules", "LEAKED=[]" in out)

    # --- the blocker must actually intercept, on 3.12 and 3.14 alike -------
    check("25d. the socket blocker is positively verified inside the child",
          "SOCKET_BLOCKED=True" in out)
    check("25e. every banned provider import was rejected BY THE BLOCKER "
          "(a plain ModuleNotFoundError from an absent package does not count)",
          "BLOCK_RESULTS={'requests': 'BLOCKED', 'yfinance': 'BLOCKED', "
          "'pytrends': 'BLOCKED'}" in out)
    check("25f. the blocker recorded all three attempts",
          "OBSERVED=['pytrends', 'requests', 'yfinance']" in out)
    check("25g. none of the three entered sys.modules", "NOT_IN_SYS_MODULES=True" in out)
    check("25h. the v0.2 orchestrator, CLI and fingerprint RUN under both blockers",
          "V02_RUNS=True" in out)
    check("25i. sys.meta_path, socket patches and sys.modules are restored",
          "RESTORED=True" in out)

    # Structural, not substring: the explanatory comments above deliberately
    # name find_module in order to say it must not be used, so a text search
    # would match the explanation rather than a real definition.
    child = ast.parse(_BLOCKER_CHILD_SRC)
    hooks = {n.name for n in ast.walk(child) if isinstance(n, ast.FunctionDef)}
    check("25j. the blocker defines find_spec and never the legacy find_module",
          "find_spec" in hooks and "find_module" not in hooks)
    blocker_cls = next((n for n in ast.walk(child) if isinstance(n, ast.ClassDef)
                        and n.name == "ProviderBlocker"), None)
    check("25k. ProviderBlocker exposes find_spec as its only import hook",
          blocker_cls is not None
          and {m.name for m in blocker_cls.body if isinstance(m, ast.FunctionDef)} == {"find_spec"})
    exc = next((n for n in ast.walk(child) if isinstance(n, ast.ClassDef)
                and n.name == "ProviderImportBlocked"), None)
    check("25l. the distinctive error subclasses ImportError",
          exc is not None and any(getattr(b, "id", None) == "ImportError" for b in exc.bases))

    src = (HERE / "gst_market_response" / "pre_event_capture.py").read_text(encoding="utf-8")
    for banned in ("import requests", "import yfinance", "urlopen", "APCA", "ALPACA_"):
        check(f"25c. orchestrator source never references {banned}", banned not in src)


def test_26_real_artifacts_untouched():
    reg = HERE / "Live Signal Engine" / "Market_Response_Event_Registry" / "registry.jsonl"
    digest = hashlib.sha256(reg.read_bytes()).hexdigest()
    rows = HumanVerifiedEventRegistry(reg.parent).read_all()
    check("26. the real DELL registry still holds exactly one REGISTRATION row", len(rows) == 1)
    check("26b. it is still verified/REGISTERED with no event state",
          rows[0]["verification_status"] == "verified"
          and not list(HERE.rglob("EVT-*.jsonl"))
          and not list(HERE.rglob("EVT-*_COMPLETION_MARKER.json")))
    check("26c. registry digest is stable within this run",
          hashlib.sha256(reg.read_bytes()).hexdigest() == digest)


def test_27_deterministic_lf_bytes():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH,
                                  option_benchmark_fields=OPT_NONE)
        log = (store / f"{EVENT}.jsonl").read_bytes()
        marker = (store / f"{EVENT}_PRE_EVENT_CAPTURE_MARKER.json").read_bytes()
        check("27. event log uses LF only (no CR)", b"\r" not in log)
        check("27b. completion marker uses LF only (no CR)", b"\r" not in marker)
        check("27c. both decode as UTF-8", bool(log.decode("utf-8")) and bool(marker.decode("utf-8")))


def test_cli_subprocess_contract():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); reg = synth_registry(tmp)
        base = [sys.executable, "-m", "gst_market_response.pre_event_capture_cli",
                "--event-id", EVENT, "--expected-anchor-session", ANCHOR,
                "--panel-csv", str(c), "--panel-marker", str(m),
                "--store-root", str(tmp / "store"), "--research-commit-sha", "deadbeef",
                "--methodology-version", METH, "--registry", str(reg),
                "--company-name", "Dell Technologies Inc."]
        r = subprocess.run(base + ["--option-status", "UNAVAILABLE_NO_VERIFIED_SOURCE",
                                   "--option-reason", "no OPRA source"],
                           cwd=str(HERE), capture_output=True, text=True)
        check("CLI-1. validation-only exits 0", r.returncode == 0)
        check("CLI-2. validation-only wrote nothing", not (tmp / "store").exists())
        check("CLI-3. stdout says no writes performed", "no writes performed" in r.stdout)
        r2 = subprocess.run(base, cwd=str(HERE), capture_output=True, text=True)
        check("CLI-4. omitting the option disposition is a usage error (never inferred)",
              r2.returncode == 2 and "never inferred" in r2.stderr)
        r3 = subprocess.run(base + ["--option-status", "UNAVAILABLE_NO_VERIFIED_SOURCE",
                                    "--option-reason", "no OPRA source", "--expected-anchor-session",
                                    "2026-09-01"][0:], cwd=str(HERE), capture_output=True, text=True)
        check("CLI-5. wrong anchor exits nonzero", r3.returncode != 0)
        blob = (r.stdout + r.stderr + r2.stdout + r2.stderr).upper()
        check("CLI-6. no credential material in any CLI output",
              "APCA" not in blob and "SECRET" not in blob and "BEARER" not in blob)
        # Structural, not substring: the module's own comment names these flags in
        # order to state that they are deliberately absent, so a text search would
        # match the explanation rather than any real option.
        from gst_market_response.pre_event_capture_cli import _parser
        declared = {opt for a in _parser()._actions for opt in a.option_strings}
        forbidden = {"--force", "--overwrite", "--skip-validation", "--allow-stale",
                     "--ignore", "--no-validate"}
        check(f"CLI-7. no override/force/skip escape-hatch flag is declared (declared={sorted(declared)})",
              not (declared & forbidden))
        check("CLI-8. --execute is required for writes and defaults off",
              "--execute" in declared)


def test_28_synthetic_dell_chronology():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH,
                                  option_benchmark_fields=OPT_NONE)
        s = EventStore(store)
        # PROTOCOL v0.2: no unlink, no overwrite. Each stage writes its OWN
        # immutable marker at the moment that stage becomes durable.
        from gst_market_response.stage_markers import STAGE_D1, STAGE_FINAL, write_stage_marker
        capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                              "thirty_min_to_close": 0.01, "open_to_close": 0.02})
        write_stage_marker(store, EVENT, STAGE_D1, s)
        capture_d3(s, EVENT, {"close_T1_to_close_T2": 0.01, "close_T1_to_close_T3": 0.02})
        mk = write_stage_marker(store, EVENT, STAGE_FINAL, s)
        chain = [r["state"] for r in s.read_all(EVENT) if r["record_type"] == "STATE"]
        check("28. full synthetic chronology reaches lifecycle COMPLETE",
              chain[-1] == "COMPLETE" and "PRE_EVENT_CAPTURED" in chain)
        check("28b. its tier stays core-only through completion",
              mk["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)
        check("28c. never described as full-data complete", mk["is_full_data_complete"] is False)
        check("28d. the real DELL event was never touched (this used a temp store)",
              not (HERE / f"{EVENT}.jsonl").exists())




# ================= C. v0.2 HARDENING REGRESSIONS (fail against 9b006a4) =======

STRICT_FULL = {"gst_zscore": 1.2, "wiki_zscore": 2.5, "panel_implied_volatility": 0.31,
               "realized_volatility": 0.21, "previous_close": 101.5, "volume": 1000000,
               "pre_event_snapshot_asof_utc": "2026-09-02T20:00:00+00:00",
               "source_status_gst": "ok", "source_status_wiki": "ok", "source_status_price": "ok",
               "source_status_iv": "ok", "source_status_realized_vol": "ok"}


def test_h1_h4_strict_six_field_gate():
    from gst_market_response.completeness import (STRICT_CORE_SIX_FIELDS,
                                                  evaluate_strict_core_v0_2)
    check("H1. strict v0.2 core accepts a full six-field observation",
          evaluate_strict_core_v0_2(STRICT_FULL).passed)
    check("H1b. all six panel fields are named in the strict contract",
          set(STRICT_CORE_SIX_FIELDS) == {"gst_zscore", "wiki_zscore", "panel_implied_volatility",
                                          "realized_volatility", "previous_close", "volume"})
    for f in STRICT_CORE_SIX_FIELDS:
        d = dict(STRICT_FULL); d[f] = None
        r = evaluate_strict_core_v0_2(d)
        check("H2. missing " + f + " fails the strict gate", not r.passed and f in r.missing_fields)
    z = dict(STRICT_FULL); z["volume"] = 0.0; z["gst_zscore"] = 0.0
    check("H3. a legitimate 0.0 with a successful status PASSES (zero is not missing)",
          evaluate_strict_core_v0_2(z).passed)
    b = dict(STRICT_FULL); b["volume"] = 0.0; b["source_status_price"] = "error"
    r = evaluate_strict_core_v0_2(b)
    check("H4. 0.0 with a NON-SUCCESS status fails", not r.passed and "volume" in r.bad_status_fields)


def test_h5_provenance_persisted_and_marker_ties_out():
    from gst_market_response.stage_markers import PROVENANCE_KEYS, STAGE_PRE_EVENT, marker_path
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH, option_benchmark_fields=OPT_NONE)
        rec = [r for r in EventStore(store).read_all(EVENT)
               if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"]
        missing = [k for k in PROVENANCE_KEYS if rec.get(k) in (None, "")]
        check("H5. every provenance field is persisted on the event record (missing=" + str(missing) + ")",
              not missing)
        mk = json.loads(marker_path(store, EVENT, STAGE_PRE_EVENT).read_text(encoding="utf-8"))
        check("H5b. the stage marker echoes provenance and ties out to the record",
              all(mk["provenance"][k] == rec.get(k) for k in PROVENANCE_KEYS))
        check("H5c. all six panel field values are on the record",
              all(rec.get(k) is not None for k in
                  ("gst_zscore", "wiki_zscore", "panel_implied_volatility",
                   "realized_volatility", "previous_close", "volume")))


def test_h6_h7_toctou_mutation_after_validation():
    for label, which in (("H6. panel CSV", "csv"), ("H7. panel marker", "marker")):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
            rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
            target = c if which == "csv" else m
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="")
            expect_raises(label + " mutated after validation -> execution refuses",
                          PreEventCaptureError, execute_pre_event_capture, report=rep,
                          store_root=store, panel_csv=c, panel_marker=m, ticker="DELL",
                          research_commit_sha="deadbeef", methodology_version=METH,
                          option_benchmark_fields=OPT_NONE)
            check(label + " mutation -> zero writes", not store.exists())


def test_h8_methodology_version_enforced():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp)
        for bad in ("", "market_response_v0.1", "whatever", "V0.2"):
            rep = validate_pre_event_capture(
                registry_path=synth_registry(tmp), event_id=EVENT,
                company_name="Dell Technologies Inc.", expected_anchor_session=ANCHOR,
                panel_csv=c, panel_marker=m, store_root=tmp / "store",
                research_commit_sha="deadbeef", methodology_version=bad,
                option_benchmark_fields=OPT_NONE, now_utc=NOW)
            check("H8. methodology " + repr(bad) + " is rejected",
                  any(x["check"] == "methodology_version_is_v0_2" and not x["passed"]
                      for x in rep.checks))


def test_h10_markers_are_immutable():
    from gst_market_response.atomic_io import ImmutableArtifactExistsError
    from gst_market_response.stage_markers import STAGE_PRE_EVENT, write_stage_marker
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH, option_benchmark_fields=OPT_NONE)
        expect_raises("H10. rewriting an existing stage marker raises",
                      ImmutableArtifactExistsError, write_stage_marker,
                      store, EVENT, STAGE_PRE_EVENT, EventStore(store))


def test_h11_crash_recovery():
    from gst_market_response.stage_markers import (STAGE_PRE_EVENT, StageMarkerError, marker_path,
                                                   recover_missing_marker, verify_marker_ties_out)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH, option_benchmark_fields=OPT_NONE)
        st = EventStore(store)
        log_before = (store / (EVENT + ".jsonl")).read_bytes()
        marker_path(store, EVENT, STAGE_PRE_EVENT).unlink()   # crash between state and marker
        rec = recover_missing_marker(store, EVENT, STAGE_PRE_EVENT, st)
        check("H11. a marker missing after a crash is regenerated from the event record",
              rec["lifecycle_state"] == "PRE_EVENT_CAPTURED")
        check("H11b. recovery appended no duplicate state",
              (store / (EVENT + ".jsonl")).read_bytes() == log_before)
        ok, diffs = verify_marker_ties_out(store, EVENT, STAGE_PRE_EVENT, st)
        check("H11c. the regenerated marker ties out exactly", ok and not diffs)
        again = recover_missing_marker(store, EVENT, STAGE_PRE_EVENT, st)
        check("H11d. recovery on an already-correct marker is a no-op",
              again["stage"] == STAGE_PRE_EVENT)
        p = marker_path(store, EVENT, STAGE_PRE_EVENT)
        bad = json.loads(p.read_text(encoding="utf-8")); bad["lifecycle_state"] = "COMPLETE"
        p.write_text(json.dumps(bad), encoding="utf-8", newline="")
        expect_raises("H11e. a mismatched existing marker fails closed rather than being replaced",
                      StageMarkerError, recover_missing_marker, store, EVENT, STAGE_PRE_EVENT, st)


def test_h13_opra_claiming_json_rejected():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); reg = synth_registry(tmp)
        art = tmp / "hand_written.json"
        art.write_text(json.dumps(dict(OPT_VALID)), encoding="utf-8", newline="")
        r = subprocess.run([sys.executable, "-m", "gst_market_response.pre_event_capture_cli",
                            "--event-id", EVENT, "--expected-anchor-session", ANCHOR,
                            "--panel-csv", str(c), "--panel-marker", str(m),
                            "--store-root", str(tmp / "store"), "--research-commit-sha", "deadbeef",
                            "--methodology-version", METH, "--registry", str(reg),
                            "--company-name", "Dell Technologies Inc.",
                            "--option-benchmark-json", str(art)],
                           cwd=str(HERE), capture_output=True, text=True)
        check("H13. a hand-written JSON claiming OPRA VALID_VERIFIED is rejected", r.returncode == 2)
        check("H13b. the refusal explains there is no cleared provider artifact",
              "cleared provider" in r.stderr.lower() or "cannot be asserted" in r.stderr.lower())
        check("H13c. nothing was written", not (tmp / "store").exists())


def test_h16_gate_reads_pre_event_record():
    from gst_market_response.completion_marker import EXIT_OK, check_required_gate
    with tempfile.TemporaryDirectory() as t:
        store = Path(t); s = EventStore(store)
        s.append_state(EVENT, "REGISTERED", {})
        capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
        capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                              "thirty_min_to_close": 0.01, "open_to_close": 0.02})
        capture_d3(s, EVENT, {"close_T1_to_close_T2": 0.01, "close_T1_to_close_T3": 0.02})
        check("H16. the pre_event gate reads the PRE-EVENT record, not the latest D3 record",
              check_required_gate(s, EVENT, "pre_event") == EXIT_OK)
        check("H16b. the d1 gate still resolves against the D1 record",
              check_required_gate(s, EVENT, "d1") == EXIT_OK)


def test_h17_session_ambiguity_fails_closed():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-03", price_asof=ANCHOR)
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("H17. run_date the day AFTER the session still validates "
              "(anchor binds to price_asof_date)",
              rep.ok() and rep.panel_price_asof_date == ANCHOR and rep.panel_run_date == "2026-09-03")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date=ANCHOR, price_asof="2026-09-01")
        check("H17b. a stale price_asof_date fails even when run_date equals the anchor",
              not _validate(tmp, csv_p=c, marker_p=m).ok())
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, asof_ambiguous=True, rows=2)
        expect_raises("H17c. rows disagreeing on price_asof_date fail closed",
                      PreEventCaptureError, _validate, tmp, csv_p=c, marker_p=m)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, drop_asof_col=True)
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("H17d. a panel with no authoritative price_asof_date column fails closed "
              "(never inferred from a UTC timestamp)",
              not rep.ok() and any(x["check"] == "panel_session_resolvable_from_authoritative_column"
                                   and not x["passed"] for x in rep.checks))


def test_h18_real_artifacts_untouched():
    reg = HERE / "Live Signal Engine" / "Market_Response_Event_Registry" / "registry.jsonl"
    rows = HumanVerifiedEventRegistry(reg.parent).read_all()
    check("H18. real DELL registry still holds exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["verification_status"] == "verified"
          and rows[0]["row_type"] == "REGISTRATION")
    check("H18b. no real event log or stage marker exists anywhere in the repo",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


# ============ D. SECOND-PASS AUDIT REGRESSIONS (fail against ed4df74) ========
#
# Each test below targets one defect found in the second corrective audit, and
# each fails against ed4df74 for that specific defect. Everything is synthetic
# and network-free; no operational artifact is a writable target.

from gst_market_response.capture_fingerprint import CAPTURE_FINGERPRINT_KEY


def _seed_pending(store: Path, fingerprint) -> EventStore:
    """A store crashed BETWEEN the PRE_EVENT_PENDING append and the next one."""
    store.mkdir(parents=True, exist_ok=True)
    s = EventStore(store)
    s.append_state(EVENT, "REGISTERED", {"ticker": "DELL"})
    s.append_state(EVENT, "PRE_EVENT_PENDING", {CAPTURE_FINGERPRINT_KEY: fingerprint})
    return s


def _states(store: Path):
    return [r["state"] for r in EventStore(store).read_all(EVENT) if r["record_type"] == "STATE"]


def test_r1_atomic_no_overwrite_race():
    """R1. A competitor created AFTER any existence check must never be
    overwritten, and its bytes must survive byte-for-byte.

    Against ed4df74 the sequence was exists() -> atomic_write_bytes() ->
    os.replace(). The injection below creates the competing artifact during the
    temp-file fsync, i.e. after the check and before the replace -- exactly the
    window os.replace() destroyed. os.link() cannot: it never replaces.
    """
    import gst_market_response.atomic_io as aio
    from gst_market_response.atomic_io import (ImmutableArtifactExistsError,
                                               atomic_write_json_no_overwrite)
    competitor = b'{"written_by": "the other process"}'

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); target = tmp / "EVT-X_PRE_EVENT_CAPTURE_MARKER.json"
        real_fsync, fired = aio.os.fsync, []

        def racing_fsync(fd):
            if not fired:                      # exactly once, on the temp file
                fired.append(True)
                target.write_bytes(competitor)  # <- the race
            return real_fsync(fd)

        aio.os.fsync = racing_fsync
        try:
            raised = False
            try:
                atomic_write_json_no_overwrite(target, {"written_by": "us"})
            except ImmutableArtifactExistsError:
                raised = True
        finally:
            aio.os.fsync = real_fsync
        check("R1. a competitor created after the check is not overwritten (raises)", raised)
        check("R1b. the competing artifact's bytes are unchanged",
              target.read_bytes() == competitor)
        check("R1c. the race actually fired (the test is not vacuous)", bool(fired))
        check("R1d. no temporary file is left behind",
              not [p for p in tmp.iterdir() if p.name.endswith(".tmp")])

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); target = tmp / "m.json"
        target.write_bytes(competitor)
        expect_raises("R1e. a pre-existing artifact raises rather than being replaced",
                      ImmutableArtifactExistsError, atomic_write_json_no_overwrite,
                      target, {"written_by": "us"})
        check("R1f. ...and its bytes are unchanged", target.read_bytes() == competitor)
        check("R1g. no temporary file is left behind after a refusal",
              not [p for p in tmp.iterdir() if p.name.endswith(".tmp")])
        # Structural: the implementation must not be exists()-then-replace.
        import ast
        src = (HERE / "gst_market_response" / "atomic_io.py").read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_exclusive_create_bytes")
        called = {n.func.attr for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        check("R1h. the write-once primitive uses an exclusive create, never os.replace",
              "link" in called and "replace" not in called)


def test_r2_r3_r4_dangling_pending_resume():
    # --- R2: exact-fingerprint resume ------------------------------------
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        seed = _validate(tmp, csv_p=c, marker_p=m, store=store)
        _seed_pending(store, seed.capture_fingerprint)
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("R2. a dangling PRE_EVENT_PENDING with an identical fingerprint is resumable",
              rep.ok() and rep.resume_from_pending is True)
        res = execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                        ticker="DELL", research_commit_sha="deadbeef",
                                        methodology_version=METH, option_benchmark_fields=OPT_NONE)
        chain = _states(store)
        check("R2b. the resume completes the capture", res["state"] == "PRE_EVENT_CAPTURED")
        # R4: no duplicate pending, no duplicate captured
        check("R4. exactly one PRE_EVENT_PENDING record exists after the resume",
              chain.count("PRE_EVENT_PENDING") == 1)
        check("R4b. exactly one PRE_EVENT_CAPTURED record exists",
              chain.count("PRE_EVENT_CAPTURED") == 1)
        check("R4c. the pending record was never deleted or rewritten",
              chain[:2] == ["REGISTERED", "PRE_EVENT_PENDING"])
        expect_raises("R4d. a further execution is still refused",
                      PreEventCaptureError, execute_pre_event_capture, report=rep,
                      store_root=store, panel_csv=c, panel_marker=m, ticker="DELL",
                      research_commit_sha="deadbeef", methodology_version=METH,
                      option_benchmark_fields=OPT_NONE)

    # --- R3: changed inputs fail closed ----------------------------------
    for label, kw in (("a different option disposition", {"opt": _nulls(D.LOOKUP_FAILED, "other")}),
                      ("a different panel file", {"other_panel": True})):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
            seed = _validate(tmp, csv_p=c, marker_p=m, store=store)
            _seed_pending(store, seed.capture_fingerprint)
            if kw.pop("other_panel", False):
                c, m = synth_panel(tmp, iv="0.44", name="SYNTHETIC_panel_b.csv")
            rep = _validate(tmp, csv_p=c, marker_p=m, store=store, **kw)
            check(f"R3. resuming with {label} fails closed",
                  not rep.ok() and rep.resume_from_pending is False
                  and any(x["check"] == "dangling_pending_absent_or_resumable" and not x["passed"]
                          for x in rep.checks))
            before = (store / f"{EVENT}.jsonl").read_bytes()
            expect_raises(f"R3b. executing with {label} raises",
                          PreEventCaptureError, execute_pre_event_capture, report=rep,
                          store_root=store, panel_csv=c, panel_marker=m, ticker="DELL",
                          research_commit_sha="deadbeef", methodology_version=METH,
                          option_benchmark_fields=kw.get("opt", OPT_NONE))
            check(f"R3c. ...and adds zero bytes ({label})",
                  (store / f"{EVENT}.jsonl").read_bytes() == before)

    # --- malformed / ambiguous pending records fail closed ----------------
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        seed = _validate(tmp, csv_p=c, marker_p=m, store=store)
        store.mkdir(parents=True, exist_ok=True)
        s = EventStore(store); s.append_state(EVENT, "REGISTERED", {"ticker": "DELL"})
        s.append_state(EVENT, "PRE_EVENT_PENDING", {})       # the ed4df74 shape: no fingerprint
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("R3d. a pending record with NO fingerprint is not resumable",
              not rep.ok() and rep.resume_from_pending is False)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        seed = _validate(tmp, csv_p=c, marker_p=m, store=store)
        tampered = dict(seed.capture_fingerprint); tampered["ticker"] = "MSFT"
        _seed_pending(store, tampered)                        # self-digest no longer recomputes
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("R3e. a pending fingerprint that does not recompute fails closed",
              not rep.ok() and rep.resume_from_pending is False)


def test_r2b_crash_injection_at_every_stage():
    """Crash after REGISTERED, after PRE_EVENT_PENDING, after PRE_EVENT_CAPTURED
    and before marker creation."""
    from gst_market_response.stage_markers import (STAGE_PRE_EVENT, marker_path,
                                                   recover_missing_marker)
    # (a) crash after REGISTERED only
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        store.mkdir(parents=True, exist_ok=True)
        EventStore(store).append_state(EVENT, "REGISTERED", {"ticker": "DELL"})
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        res = execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                        ticker="DELL", research_commit_sha="deadbeef",
                                        methodology_version=METH, option_benchmark_fields=OPT_NONE)
        check("R2c. crash after REGISTERED -> the capture proceeds normally",
              res["state"] == "PRE_EVENT_CAPTURED"
              and _states(store) == ["REGISTERED", "PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED"])

    # (b) crash after PRE_EVENT_PENDING is covered by R2 above.
    # (c)/(d) crash after PRE_EVENT_CAPTURED, before the marker was written.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH, option_benchmark_fields=OPT_NONE)
        marker_path(store, EVENT, STAGE_PRE_EVENT).unlink()
        before = (store / f"{EVENT}.jsonl").read_bytes()
        rec = recover_missing_marker(store, EVENT, STAGE_PRE_EVENT, EventStore(store))
        check("R2d. crash before the marker -> recovery regenerates it",
              rec["lifecycle_state"] == "PRE_EVENT_CAPTURED")
        check("R2e. recovery appended no state record",
              (store / f"{EVENT}.jsonl").read_bytes() == before)
        rep2 = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("R2f. re-running the capture after a completed stage is still refused",
              not rep2.ok() and rep2.resume_from_pending is False)


def test_r5_r6_per_leg_statuses_enforced():
    from gst_market_response.completeness import (STRICT_CORE_STATUS_KEY,
                                                  evaluate_strict_core_v0_2)
    check("R5. panel_implied_volatility is backed by the IV leg, not the price leg",
          STRICT_CORE_STATUS_KEY["panel_implied_volatility"] == "source_status_iv")
    check("R6. realized_volatility is backed by the realized-vol leg",
          STRICT_CORE_STATUS_KEY["realized_volatility"] == "source_status_realized_vol")
    # A NON-NULL value whose own leg failed, while price history is OK.
    iv_bad = dict(STRICT_FULL, source_status_iv="error")
    r = evaluate_strict_core_v0_2(iv_bad)
    check("R5b. a non-null IV with a FAILED iv_status fails even when price history is ok",
          not r.passed and "panel_implied_volatility" in r.bad_status_fields
          and iv_bad["panel_implied_volatility"] is not None
          and iv_bad["source_status_price"] == "ok")
    rv_bad = dict(STRICT_FULL, source_status_realized_vol="error")
    r = evaluate_strict_core_v0_2(rv_bad)
    check("R6b. a non-null realized vol with a FAILED realized_vol_status fails likewise",
          not r.passed and "realized_volatility" in r.bad_status_fields
          and rv_bad["source_status_price"] == "ok")
    check("R5c. an unknown IV status fails closed",
          not evaluate_strict_core_v0_2(dict(STRICT_FULL, source_status_iv="brand_new")).passed)
    check("R5d. an absent IV status key fails closed",
          not evaluate_strict_core_v0_2(
              {k: v for k, v in STRICT_FULL.items() if k != "source_status_iv"}).passed)
    # End to end through the orchestrator, on a panel whose iv_status failed.
    for label, kw, field_name in (
            ("R5e. iv_status", {"iv_status": "timeout"}, "panel_implied_volatility"),
            ("R6c. realized_vol_status", {"realized_vol_status": "timeout"}, "realized_volatility")):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t); c, m = synth_panel(tmp, **kw)
            rep = _validate(tmp, csv_p=c, marker_p=m)
            check(f"{label} failure is rejected by the orchestrator (price history still ok)",
                  not rep.ok()
                  and any(x["check"] == "strict_core_v0_2_all_six_statuses_successful"
                          and not x["passed"] and field_name in x["detail"] for x in rep.checks))
    # The adapter reads the real column names.
    from gst_market_response.phase2_adapter import import_pre_event_fields_for_ticker
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, iv_status="complete_recent_cache_fallback")
        a = import_pre_event_fields_for_ticker(csv_path=c, marker_path=m, ticker="DELL",
                                               research_commit_sha="x", methodology_version=METH)
        check("R5f. the adapter reads iv_status from its own column and normalises it",
              a.source_status_iv == "ok_recent_cache_fallback"
              and a.source_status_iv_raw == "complete_recent_cache_fallback")
        check("R5g. a fallback-served IV is still a success for the strict gate",
              evaluate_strict_core_v0_2(a.to_strict_core_fields()).passed)


def test_r7_r8_partial_is_stage_specific():
    from gst_market_response.completion_marker import (EXIT_INCONCLUSIVE, EXIT_OK,
                                                       check_required_gate, write_completion_marker)
    from gst_market_response.event_record import FAILURE_STAGE_KEY
    from gst_market_response.stage_markers import STAGE_D1, build_stage_marker

    def _pre_event_ok(store_root, s):
        m = write_completion_marker(store_root, EVENT, s)
        return m

    # --- R7: a D1 PARTIAL must not replace pre-event eligibility ----------
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = EventStore(root); s.append_state(EVENT, "REGISTERED", {})
        capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
        d1 = capture_d1(s, EVENT, {"overnight_gap": 0.01})       # incomplete -> PARTIAL
        check("R7. an incomplete D1 is PARTIAL", d1 == "PARTIAL")
        last = [r for r in s.read_all(EVENT) if r["record_type"] == "STATE"][-1]
        check("R7b. the D1 PARTIAL declares its own failure stage",
              last["fields"].get(FAILURE_STAGE_KEY) == "d1")
        m = _pre_event_ok(root, s)
        check("R7c. the completion marker still reports the PRE-EVENT eligibility",
              m["module_eligibility"] is not None
              and m["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)
        check("R7d. the pre_event gate still resolves against the pre-event record",
              check_required_gate(s, EVENT, "pre_event") == EXIT_OK)
        check("R7e. the d1 gate resolves against the D1 PARTIAL and fails it",
              check_required_gate(s, EVENT, "d1") != EXIT_INCONCLUSIVE)
        expect_raises("R7f. a D1 PARTIAL cannot satisfy a PRE_EVENT_CAPTURE marker",
                      Exception, build_stage_marker, s, EVENT, "PRE_EVENT_CAPTURE")
        mk = build_stage_marker(s, EVENT, STAGE_D1)
        check("R7g. the D1 marker still carries the pre-event eligibility block",
              mk["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)

    # --- R8: a D3 PARTIAL must not replace pre-event eligibility ----------
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = EventStore(root); s.append_state(EVENT, "REGISTERED", {})
        capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
        capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                              "thirty_min_to_close": 0.01, "open_to_close": 0.02})
        d3 = capture_d3(s, EVENT, {"close_T1_to_close_T2": 0.01})   # incomplete -> PARTIAL
        check("R8. an incomplete D3 is PARTIAL", d3 == "PARTIAL")
        last = [r for r in s.read_all(EVENT) if r["record_type"] == "STATE"][-1]
        check("R8b. the D3 PARTIAL declares failure_stage=d3",
              last["fields"].get(FAILURE_STAGE_KEY) == "d3")
        m = _pre_event_ok(root, s)
        check("R8c. the completion marker still reports the PRE-EVENT eligibility",
              m["module_eligibility"] is not None
              and m["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)
        check("R8d. it is still not full-data complete", m["is_full_data_complete"] is False)
        check("R8e. the pre_event gate is unaffected by the D3 failure",
              check_required_gate(s, EVENT, "pre_event") == EXIT_OK)
        check("R8f. the d1 gate still resolves against D1_COMPLETE",
              check_required_gate(s, EVENT, "d1") == EXIT_OK)


def test_r9_option_artifact_bound_to_validation():
    mutations = [
        ("a different disposition", _nulls(D.LOOKUP_FAILED, "no OPRA-entitled source available")),
        ("a different reason", _nulls(D.UNAVAILABLE_NO_VERIFIED_SOURCE, "changed my mind")),
        ("a claimed OPRA artifact", dict(OPT_VALID)),
    ]
    for label, mutated in mutations:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
            rep = _validate(tmp, csv_p=c, marker_p=m, store=store, opt=OPT_NONE)
            check(f"R9 setup. validation approved UNAVAILABLE_NO_VERIFIED_SOURCE ({label})",
                  rep.ok() and rep.option_benchmark_status == D.UNAVAILABLE_NO_VERIFIED_SOURCE)
            expect_raises(f"R9. executing with {label} is refused",
                          PreEventCaptureError, execute_pre_event_capture, report=rep,
                          store_root=store, panel_csv=c, panel_marker=m, ticker="DELL",
                          research_commit_sha="deadbeef", methodology_version=METH,
                          option_benchmark_fields=mutated)
            check(f"R9b. ...with zero writes ({label})", not store.exists())
    # The digest covers the WHOLE artifact, and dict ordering does not change it.
    from gst_market_response.capture_fingerprint import option_fields_digest
    reordered = {k: OPT_NONE[k] for k in reversed(list(OPT_NONE))}
    check("R9c. the option digest is order-independent",
          option_fields_digest(OPT_NONE) == option_fields_digest(reordered))
    check("R9d. the option digest changes when any single value changes",
          option_fields_digest(OPT_NONE)
          != option_fields_digest({**OPT_NONE, "option_benchmark_unavailable_reason": "x"}))


def test_r10_r11_blank_and_cross_row_dates():
    # R10: one blank price_asof_date among otherwise matching rows.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, other_tickers=("MSFT",), blank_asof_rows=(1,))
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("R10. one blank price_asof_date among matching rows fails "
              "(blanks are never discarded before validation)",
              not rep.ok()
              and any(x["check"] == "panel_price_asof_date_nonblank_in_every_row"
                      and not x["passed"] for x in rep.checks))
    # R11: one blank run_date among otherwise matching rows.
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, other_tickers=("MSFT",), blank_run_rows=(1,))
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("R11. one blank run_date among matching rows fails",
              not rep.ok()
              and any(x["check"] == "panel_run_date_nonblank_in_every_row"
                      and not x["passed"] for x in rep.checks))
    # multiple run dates across rows
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, other_tickers=("MSFT",),
                                          run_date_by_row={1: "2026-09-04"})
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("R11b. rows disagreeing on run_date fail closed",
              not rep.ok()
              and any(x["check"] == "panel_run_date_single_value_across_rows"
                      and not x["passed"] for x in rep.checks))
    # a panel with no run_date column at all
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, drop_run_date_col=True)
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("R11c. a panel with no run_date column fails closed",
              not rep.ok()
              and any(x["check"] == "panel_run_date_nonblank_in_every_row"
                      and not x["passed"] for x in rep.checks))
    # run_date BEFORE the session it summarises
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-01", price_asof=ANCHOR)
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("R11d. run_date preceding price_asof_date fails closed",
              not rep.ok()
              and any(x["check"] == "run_date_not_before_session" and not x["passed"]
                      for x in rep.checks))
    # the good case still passes, and the audit is persisted on the report
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-03", price_asof=ANCHOR,
                                          other_tickers=("MSFT",))
        rep = _validate(tmp, csv_p=c, marker_p=m)
        check("R10b. a multi-row panel with consistent nonblank dates still passes",
              rep.ok() and rep.panel_date_audit["ok"] is True
              and rep.panel_date_audit["blank_price_asof_rows"] == 0)


def test_r12_v0_2_pipeline_cannot_bypass_strict_gate():
    import ast
    from gst_market_response import pipeline as pl
    from gst_market_response.event_record import FAILURE_STAGE_KEY

    # Structural: the v0.2 capture must reach the STRICT gate, not the v0.1 one.
    src = (HERE / "gst_market_response" / "pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name == "capture_pre_event_and_option_benchmark_v0_2")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("R12. the v0.2 capture calls evaluate_pre_event_modules_v0_2",
          "evaluate_pre_event_modules_v0_2" in called)
    check("R12b. it never calls the v0.1 module evaluator or the v0.1 core gate",
          "evaluate_pre_event_modules" not in called
          and "is_valid_pre_event_observation" not in called)
    v2src = (HERE / "gst_market_response" / "completeness.py").read_text(encoding="utf-8")
    v2fn = next(n for n in ast.walk(ast.parse(v2src)) if isinstance(n, ast.FunctionDef)
                and n.name == "evaluate_pre_event_modules_v0_2")
    v2called = {n.func.id for n in ast.walk(v2fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    check("R12c. evaluate_pre_event_modules_v0_2 judges the core with the strict gate",
          "evaluate_strict_core_v0_2" in v2called
          and "is_valid_pre_event_observation" not in v2called)

    # No unversioned public capture function exists at all.
    check("R12d. no unversioned capture function is exported",
          "capture_pre_event_and_option_benchmark" not in dir(pl))
    try:
        getattr(pl, "capture_pre_event_and_option_benchmark")
        raised = False
    except AttributeError as exc:
        raised = "v0_2" in str(exc)
    check("R12e. the unversioned name raises with explicit version guidance", raised)

    # Behavioural: fields that PASS the v0.1 gate but FAIL the strict six-field
    # gate must not be recorded as an eligible capture.
    weak = {"previous_close": 101.5, "pre_event_snapshot_asof_utc": "2026-09-02T20:00:00+00:00",
            "gst_zscore": 1.2, "source_status_gst": "ok"}
    from gst_market_response.completeness import is_valid_pre_event_observation
    check("R12f. the weak fixture DOES pass the legacy v0.1 gate (the test is not vacuous)",
          is_valid_pre_event_observation(weak))
    with tempfile.TemporaryDirectory() as t:
        s = EventStore(Path(t)); s.append_state(EVENT, "REGISTERED", {})
        st = pl.capture_pre_event_and_option_benchmark_v0_2(s, EVENT, weak, OPT_NONE)
        rec = [r for r in s.read_all(EVENT) if r["record_type"] == "STATE"][-1]
        check("R12g. the v0.2 pipeline records it as PARTIAL, not PRE_EVENT_CAPTURED",
              st == "PARTIAL")
        check("R12h. ...with core_pre_event_eligible False and a pre_event failure stage",
              rec["fields"]["core_pre_event_eligible"] is False
              and rec["fields"][FAILURE_STAGE_KEY] == "pre_event")
    with tempfile.TemporaryDirectory() as t:
        s = EventStore(Path(t)); s.append_state(EVENT, "REGISTERED", {})
        st = pl.capture_pre_event_and_option_benchmark_v0_2(s, EVENT, STRICT_FULL, OPT_NONE)
        check("R12i. a genuine six-field observation still captures", st == "PRE_EVENT_CAPTURED")


def test_r13_full_chronology_without_unlink_or_overwrite():
    """R13. A complete synthetic chronology, with every artifact byte recorded
    before and after, proving nothing was unlinked or overwritten."""
    from gst_market_response.stage_markers import (STAGE_D1, STAGE_FINAL, STAGE_PRE_EVENT,
                                                   marker_path, write_stage_marker)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        execute_pre_event_capture(report=rep, store_root=store, panel_csv=c, panel_marker=m,
                                  ticker="DELL", research_commit_sha="deadbeef",
                                  methodology_version=METH, option_benchmark_fields=OPT_NONE)
        s = EventStore(store)
        pre_bytes = marker_path(store, EVENT, STAGE_PRE_EVENT).read_bytes()
        log_len_after_pre = len((store / f"{EVENT}.jsonl").read_bytes())

        capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                              "thirty_min_to_close": 0.01, "open_to_close": 0.02})
        write_stage_marker(store, EVENT, STAGE_D1, s)
        d1_bytes = marker_path(store, EVENT, STAGE_D1).read_bytes()
        capture_d3(s, EVENT, {"close_T1_to_close_T2": 0.01, "close_T1_to_close_T3": 0.02})
        final = write_stage_marker(store, EVENT, STAGE_FINAL, s)

        chain = _states(store)
        check("R13. the full chronology reaches lifecycle COMPLETE",
              chain == ["REGISTERED", "PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED",
                        "D1_PENDING", "D1_COMPLETE", "D3_PENDING", "COMPLETE"])
        check("R13b. the pre-event marker's bytes are untouched by later stages",
              marker_path(store, EVENT, STAGE_PRE_EVENT).read_bytes() == pre_bytes)
        check("R13c. the D1 marker's bytes are untouched by the final stage",
              marker_path(store, EVENT, STAGE_D1).read_bytes() == d1_bytes)
        check("R13d. all three stage markers coexist; none replaced another",
              all(marker_path(store, EVENT, st).exists()
                  for st in (STAGE_PRE_EVENT, STAGE_D1, STAGE_FINAL)))
        check("R13e. the event log only ever grew",
              len((store / f"{EVENT}.jsonl").read_bytes()) > log_len_after_pre)
        check("R13f. the final marker preserves the core-only tier and refuses full-data completeness",
              final["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY
              and final["is_full_data_complete"] is False)
        check("R13g. the real DELL event was never touched (temp store only)",
              not (HERE / f"{EVENT}.jsonl").exists())


def test_r14_real_artifacts_untouched_after_second_pass():
    reg = HERE / "Live Signal Engine" / "Market_Response_Event_Registry" / "registry.jsonl"
    rows = HumanVerifiedEventRegistry(reg.parent).read_all()
    check("R14. the real DELL registry still holds exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["verification_status"] == "verified"
          and rows[0]["row_type"] == "REGISTRATION")
    check("R14b. no real event log or stage marker exists anywhere in the repo",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


if __name__ == "__main__":
    test_1_core_valid_options_valid()
    test_2_core_valid_options_unavailable()
    test_3_4_5_6_core_only_lifecycle_and_hypotheses()
    test_7_8_core_invalid_is_partial_terminal()
    test_9_to_15_disposition_contract()
    test_17_18_unchanged_and_legacy()
    test_orchestrator_validation_matrix()
    test_execute_writes_and_collisions()
    test_25_no_network_and_no_provider()
    test_26_real_artifacts_untouched()
    test_27_deterministic_lf_bytes()
    test_cli_subprocess_contract()
    test_28_synthetic_dell_chronology()
    test_h1_h4_strict_six_field_gate()
    test_h5_provenance_persisted_and_marker_ties_out()
    test_h6_h7_toctou_mutation_after_validation()
    test_h8_methodology_version_enforced()
    test_h10_markers_are_immutable()
    test_h11_crash_recovery()
    test_h13_opra_claiming_json_rejected()
    test_h16_gate_reads_pre_event_record()
    test_h17_session_ambiguity_fails_closed()
    test_h18_real_artifacts_untouched()
    test_r1_atomic_no_overwrite_race()
    test_r2_r3_r4_dangling_pending_resume()
    test_r2b_crash_injection_at_every_stage()
    test_r5_r6_per_leg_statuses_enforced()
    test_r7_r8_partial_is_stage_specific()
    test_r9_option_artifact_bound_to_validation()
    test_r10_r11_blank_and_cross_row_dates()
    test_r12_v0_2_pipeline_cannot_bypass_strict_gate()
    test_r13_full_chronology_without_unlink_or_overwrite()
    test_r14_real_artifacts_untouched_after_second_pass()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PRE-EVENT CAPTURE TESTS PASSED")
    sys.exit(0)
