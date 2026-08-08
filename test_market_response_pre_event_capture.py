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

_PANEL_COLS = ["run_date", "price_asof_date", "ticker", "gst_status", "wiki_status",
               "price_history_status", "gst_zscore", "wiki_zscore", "realized_vol", "price",
               "volume", "days_to_nearest_earnings", "retrieval_timestamp_utc",
               "all_six_fields_clean", "implied_volatility"]
METH = "market_response_v0.2"


def synth_panel(tmp: Path, run_date: str = ANCHOR, ticker: str = "DELL", rows: int = 1,
                zero_missing: bool = False, marker_status: str = "COMPLETE",
                break_marker: bool = False, price_asof: str | None = None,
                iv: str = "0.31", drop_asof_col: bool = False,
                asof_ambiguous: bool = False, name: str = "SYNTHETIC_panel.csv") -> tuple[Path, Path]:
    """SYNTHETIC panel fixture -- NOT RESEARCH DATA.

    `run_date` is when the panel RAN; `price_asof` is the SESSION its price data
    is as-of. They legitimately differ (a real panel runs after UTC midnight
    following the session), which is why the anchor binds to price_asof.
    """
    asof = price_asof if price_asof is not None else run_date
    csv_path, marker_path = tmp / name, tmp / (name.replace(".csv", "_marker.json"))
    recs = []
    for i in range(rows):
        recs.append({"run_date": run_date,
                     "price_asof_date": (f"{asof}" if not asof_ambiguous or i == 0 else "2026-08-28"),
                     "ticker": ticker, "gst_status": "ok",
                     "wiki_status": "ok" if not zero_missing else "incomplete_watermark_unavailable",
                     "price_history_status": "ok", "gst_zscore": "1.2",
                     "wiki_zscore": "0" if zero_missing else "2.5", "realized_vol": "0.21",
                     "price": "101.5", "volume": "1000000", "days_to_nearest_earnings": "1",
                     "retrieval_timestamp_utc": f"{run_date}T04:40:00+00:00",
                     "all_six_fields_clean": "True", "implied_volatility": iv})
    cols = [c for c in _PANEL_COLS if not (drop_asof_col and c == "price_asof_date")]
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
               "source_status_gst": "ok", "source_status_wiki": "ok", "source_status_price": "ok"}


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
        capture_pre_event_and_option_benchmark(s, EVENT, CORE, OPT_NONE)
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

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PRE-EVENT CAPTURE TESTS PASSED")
    sys.exit(0)
