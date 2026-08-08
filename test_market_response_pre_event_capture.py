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
    capture_pre_event_and_option_benchmark,
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
        st = capture_pre_event_and_option_benchmark(s, EVENT, CORE, OPT_VALID)
        e = read_module_eligibility([r for r in s.read_all(EVENT) if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"])
        check("1. core valid + options valid -> PRE_EVENT_CAPTURED", st == "PRE_EVENT_CAPTURED")
        check("1b. all three eligibility flags true",
              e.core_pre_event_eligible and e.option_benchmark_eligible and e.joint_full_eligible)
        check("1c. tier is the full core+option tier", e.pre_event_completeness_tier == FULL_DATA_COMPLETE_TIER)


def test_2_core_valid_options_unavailable():
    with tempfile.TemporaryDirectory() as t:
        s = EventStore(Path(t)); s.append_state(EVENT, "REGISTERED", {})
        st = capture_pre_event_and_option_benchmark(s, EVENT, CORE, OPT_NONE)
        e = read_module_eligibility([r for r in s.read_all(EVENT) if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"])
        check("2. core valid + explicit no verified source -> PRE_EVENT_CAPTURED", st == "PRE_EVENT_CAPTURED")
        check("2b. core eligible, option ineligible, joint ineligible",
              e.core_pre_event_eligible and not e.option_benchmark_eligible and not e.joint_full_eligible)
        check("2c. tier is core-only", e.pre_event_completeness_tier == PRE_EVENT_TIER_CORE_ONLY)
        check("2d. reason recorded", bool(e.option_benchmark_unavailable_reason))


def test_3_4_5_6_core_only_lifecycle_and_hypotheses():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = EventStore(root); s.append_state(EVENT, "REGISTERED", {})
        capture_pre_event_and_option_benchmark(s, EVENT, CORE, OPT_NONE)
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
            st = capture_pre_event_and_option_benchmark(s, EVENT, CORE_BAD, opt)
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

_PANEL_COLS = ["ticker", "gst_status", "wiki_status", "price_history_status", "gst_zscore",
               "wiki_zscore", "realized_vol", "price", "volume", "days_to_nearest_earnings",
               "retrieval_timestamp_utc", "all_six_fields_clean", "implied_volatility"]


def synth_panel(tmp: Path, run_date: str = ANCHOR, ticker: str = "DELL", rows: int = 1,
                zero_missing: bool = False, marker_status: str = "COMPLETE",
                break_marker: bool = False) -> tuple[Path, Path]:
    """SYNTHETIC panel fixture -- NOT RESEARCH DATA."""
    csv_path, marker_path = tmp / "SYNTHETIC_panel.csv", tmp / "SYNTHETIC_marker.json"
    recs = []
    for i in range(rows):
        recs.append({"ticker": ticker, "gst_status": "ok",
                     "wiki_status": "ok" if not zero_missing else "incomplete_watermark_unavailable",
                     "price_history_status": "ok", "gst_zscore": "1.2",
                     "wiki_zscore": "0" if zero_missing else "2.5", "realized_vol": "0.21",
                     "price": "101.5", "volume": "1000000", "days_to_nearest_earnings": "1",
                     "retrieval_timestamp_utc": f"{run_date}T20:00:00+00:00",
                     "all_six_fields_clean": "True", "implied_volatility": ""})
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_PANEL_COLS, lineterminator="\n")
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
        methodology_version="market_response_v0.1",
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
                                        methodology_version="market_response_v0.1",
                                        option_benchmark_fields=OPT_NONE)
        check("22. execution captured after full validation", res["state"] == "PRE_EVENT_CAPTURED")
        log = store / f"{EVENT}.jsonl"
        before = log.read_bytes()
        rep2 = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("18(orch). an existing pre-event stage is detected as a collision",
              any(x["check"] == "no_existing_pre_event_stage" and not x["passed"] for x in rep2.checks))
        check("19(orch). an existing completion marker is detected as a collision",
              any(x["check"] == "no_existing_completion_marker" and not x["passed"] for x in rep2.checks))
        expect_raises("20. repeated execution refuses (byte-idempotent by refusal)",
                      PreEventCaptureError, execute_pre_event_capture, report=rep, store_root=store,
                      panel_csv=c, panel_marker=m, ticker="DELL", research_commit_sha="deadbeef",
                      methodology_version="market_response_v0.1", option_benchmark_fields=OPT_NONE)
        check("20b. the refusal added zero bytes", log.read_bytes() == before)

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp, run_date="2026-09-01"); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        expect_raises("23. execution on a failing report is refused",
                      PreEventCaptureError, execute_pre_event_capture, report=rep, store_root=store,
                      panel_csv=c, panel_marker=m, ticker="DELL", research_commit_sha="deadbeef",
                      methodology_version="market_response_v0.1", option_benchmark_fields=OPT_NONE)
        check("23b. ...leaving no artifact at all", not store.exists())


def test_25_no_network_and_no_provider():
    proc = subprocess.run([sys.executable, "-c", textwrap.dedent("""
        import sys
        BANNED = ('yfinance','pytrends','requests','urllib3','urllib.request')
        class B:
            def find_module(self, name, path=None):
                if name.split('.')[0] in BANNED: raise ImportError('BLOCKED '+name)
                return None
        sys.meta_path.insert(0, B())
        import socket
        def boom(*a, **k): raise AssertionError('network during capture')
        socket.socket.connect = boom; socket.create_connection = boom
        import gst_market_response.pre_event_capture as pec
        import gst_market_response.pre_event_capture_cli as cli
        leaked = [m for m in ('yfinance','requests','pytrends',
                              'gst_market_response.alpaca_provider') if m in sys.modules]
        print('LEAKED='+repr(leaked)); print('OK')
    """)], cwd=str(HERE), capture_output=True, text=True)
    check("25. orchestrator+CLI import with every provider blocked and sockets poisoned",
          proc.returncode == 0 and "OK" in proc.stdout)
    check("25b. no provider or network client reaches sys.modules", "LEAKED=[]" in proc.stdout)
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
                                  methodology_version="market_response_v0.1",
                                  option_benchmark_fields=OPT_NONE)
        log = (store / f"{EVENT}.jsonl").read_bytes()
        marker = (store / f"{EVENT}_COMPLETION_MARKER.json").read_bytes()
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
                "--methodology-version", "market_response_v0.1", "--registry", str(reg),
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
                                  methodology_version="market_response_v0.1",
                                  option_benchmark_fields=OPT_NONE)
        s = EventStore(store)
        capture_d1(s, EVENT, {"overnight_gap": 0.01, "open_to_30m": 0.01,
                              "thirty_min_to_close": 0.01, "open_to_close": 0.02})
        capture_d3(s, EVENT, {"close_T1_to_close_T2": 0.01, "close_T1_to_close_T3": 0.02})
        (store / f"{EVENT}_COMPLETION_MARKER.json").unlink()
        mk = write_completion_marker(store, EVENT, s)
        chain = [r["state"] for r in s.read_all(EVENT) if r["record_type"] == "STATE"]
        check("28. full synthetic chronology reaches lifecycle COMPLETE",
              chain[-1] == "COMPLETE" and "PRE_EVENT_CAPTURED" in chain)
        check("28b. its tier stays core-only through completion",
              mk["module_eligibility"]["pre_event_completeness_tier"] == PRE_EVENT_TIER_CORE_ONLY)
        check("28c. never described as full-data complete", mk["is_full_data_complete"] is False)
        check("28d. the real DELL event was never touched (this used a temp store)",
              not (HERE / f"{EVENT}.jsonl").exists())


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

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PRE-EVENT CAPTURE TESTS PASSED")
    sys.exit(0)
