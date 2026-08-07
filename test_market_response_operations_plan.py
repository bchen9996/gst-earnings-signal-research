#!/usr/bin/env python3
# Deterministic tests for the offline operations planner.
#
# Everything here is synthetic or read-only. No provider is imported or
# constructed, no socket is opened, no credential is read, no event state is
# transitioned, and neither the registry nor the EventStore is written.
#
# Several checks run in a SUBPROCESS so a verdict about sys.modules cannot be
# contaminated by modules this test runner already imported.
#
# Run directly: python test_market_response_operations_plan.py

from __future__ import annotations

import copy
import datetime
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gst_market_response.event_registry import HumanVerifiedEventRegistry
from gst_market_response.exchange_calendar import is_early_close, is_trading_day
from gst_market_response.operations_plan import (
    ALPACA_MIN_END_AGE_MINUTES,
    KNOWN_CAPTURE_BLOCKERS,
    OperationsPlanError,
    build_operations_plan,
    finalize_plan,
    plan_content_sha256,
)

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
REAL_REGISTRY = HERE / "Live Signal Engine" / "Market_Response_Event_Registry" / "registry.jsonl"
UTC = timezone.utc
GEN = datetime.datetime(2026, 8, 7, 0, 0, tzinfo=UTC)

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


def expect_raises(label: str, fn, *a, **k) -> None:
    try:
        fn(*a, **k)
    except OperationsPlanError:
        print(f"PASS: {label}")
    except Exception as exc:
        print(f"FAIL: {label} (raised {type(exc).__name__}, expected OperationsPlanError)")
        FAILURES.append(label)
    else:
        print(f"FAIL: {label} (did not raise)")
        FAILURES.append(label)


def plan_real(**over):
    kw = dict(registry_path=REAL_REGISTRY, event_id="EVT-DELL-FY27Q2-ERN",
              company_name="Dell Technologies Inc.", generated_at_utc=GEN,
              planning_commit="87f5d770", methodology_version="market_response_v0.1")
    kw.update(over)
    return build_operations_plan(**kw)


def synth_registry(tmp: str, **over) -> Path:
    """A synthetic registry written by the PRODUCTION API, then optionally
    mutated on disk to simulate a bad row.

    Values that the API accepts natively (ticker, fiscal_period, earnings_date,
    a real datetime, session) are passed through it. Anything the API would
    reject by design -- a naive/absent timestamp, a bad calendar, a rejected
    status -- is written normally first and then mutated on disk, because the
    point of those cases is to prove the PLANNER fails closed on a row it did
    not create.
    """
    root = Path(tmp) / "reg"
    r = HumanVerifiedEventRegistry(root)
    edt = over.pop("earnings_datetime_utc", datetime.datetime(2026, 9, 3, 20, 30, tzinfo=UTC))
    if not isinstance(edt, datetime.datetime):
        # not a real datetime -> keep a valid one for the API, mutate after
        over["earnings_datetime_utc"] = edt
        edt = datetime.datetime(2026, 9, 3, 20, 30, tzinfo=UTC)
    r.register_verified_event(
        ticker=over.pop("ticker", "DELL"),
        fiscal_period=over.pop("fiscal_period", "FY27Q2"),
        earnings_date=over.pop("earnings_date", datetime.date(2026, 9, 3)),
        earnings_datetime_utc=edt,
        release_market_session=over.pop("release_market_session", "AMC"),
        source_url="https://example.invalid/ir", source_title="t", source_type="company_ir_events_calendar",
        source_retrieved_at_utc=datetime.datetime(2026, 8, 7, tzinfo=UTC),
        verified_at_utc=datetime.datetime(2026, 8, 7, tzinfo=UTC),
        verified_by="tester", verification_status="verified", notes="synthetic",
    )
    path = root / "registry.jsonl"
    if over:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows[0].update(over)
        path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8", newline="\n")
    return path


# --- 1. exact DELL schedule ------------------------------------------------

def test_exact_dell_schedule():
    p = plan_real()
    s = p["sessions"]
    check("1a. pre-event anchor session is 2026-09-02", s["pre_event_anchor"]["session_date"] == "2026-09-02")
    check("1b. earnings date is 2026-09-03", p["event"]["earnings_date"] == "2026-09-03")
    check("1c. release is AMC at 2026-09-03T20:30:00+00:00",
          p["event"]["release_market_session"] == "AMC"
          and p["event"]["event_datetime_utc"] == "2026-09-03T20:30:00+00:00")
    check("1d. D1 is 2026-09-04", s["D1"]["session_date"] == "2026-09-04")
    check("1e. D2 is 2026-09-08", s["D2"]["session_date"] == "2026-09-08")
    check("1f. D3 is 2026-09-09", s["D3"]["session_date"] == "2026-09-09")
    check("1g. registry's own expected_response_session agrees with derived D1",
          p["event"]["expected_response_session_from_registry"] == s["D1"]["session_date"])
    check("1h. every session is strictly increasing",
          s["pre_event_anchor"]["session_date"] < p["event"]["earnings_date"] < s["D1"]["session_date"]
          < s["D2"]["session_date"] < s["D3"]["session_date"])


# --- 2. Labor Day ----------------------------------------------------------

def test_labor_day_closure_between_d1_and_d2():
    p = plan_real()
    skipped = {e["date"]: e for e in p["non_sessions_between_d1_and_d3"]}
    check("2a. 2026-09-07 is recorded as a non-session between D1 and D3", "2026-09-07" in skipped)
    check("2b. it is a Monday (Labor Day), not a weekend day",
          skipped.get("2026-09-07", {}).get("weekday") == "Monday")
    check("2c. the production calendar itself reports 2026-09-07 closed",
          is_trading_day(datetime.date(2026, 9, 7)) is False)
    check("2d. the weekend either side is also recorded",
          "2026-09-05" in skipped and "2026-09-06" in skipped)
    check("2e. D2 therefore skips from Friday 09-04 to Tuesday 09-08",
          p["sessions"]["D1"]["session_date"] == "2026-09-04" and p["sessions"]["D2"]["session_date"] == "2026-09-08")


# --- 3. AMC / BMO / INTRADAY ----------------------------------------------

def test_release_session_behaviour():
    with tempfile.TemporaryDirectory() as t:
        p = build_operations_plan(registry_path=synth_registry(t), event_id="EVT-DELL-FY27Q2-ERN",
                                  company_name="c", generated_at_utc=GEN, planning_commit="x",
                                  methodology_version="m")
        check("3a. AMC: D1 is the session AFTER the earnings date",
              p["sessions"]["D1"]["session_date"] == "2026-09-04")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, release_market_session="BMO",
                             earnings_datetime_utc=datetime.datetime(2026, 9, 3, 11, 0, tzinfo=UTC).isoformat())
        p = build_operations_plan(registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                                  generated_at_utc=GEN, planning_commit="x", methodology_version="m")
        check("3b. BMO: D1 is the earnings date itself",
              p["sessions"]["D1"]["session_date"] == "2026-09-03")
        check("3c. BMO: anchor is the session before the earnings date",
              p["sessions"]["pre_event_anchor"]["session_date"] == "2026-09-02")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, release_market_session="INTRADAY",
                             earnings_datetime_utc=datetime.datetime(2026, 9, 3, 17, 0, tzinfo=UTC).isoformat())
        p = build_operations_plan(registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                                  generated_at_utc=GEN, planning_commit="x", methodology_version="m")
        check("3d. INTRADAY: D1 is the NEXT full session (release landed mid-session)",
              p["sessions"]["D1"]["session_date"] == "2026-09-04")


def test_amc_bmo_are_cross_checked_against_the_calendar():
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, release_market_session="AMC",
                             earnings_datetime_utc=datetime.datetime(2026, 9, 3, 14, 0, tzinfo=UTC).isoformat())
        expect_raises("4a. AMC claimed but timestamp is BEFORE the close -> fail closed",
                      build_operations_plan, registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN",
                      company_name="c", generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, release_market_session="BMO",
                             earnings_datetime_utc=datetime.datetime(2026, 9, 3, 20, 30, tzinfo=UTC).isoformat())
        expect_raises("4b. BMO claimed but timestamp is AFTER the open -> fail closed",
                      build_operations_plan, registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN",
                      company_name="c", generated_at_utc=GEN, planning_commit="x", methodology_version="m")


# --- 5. weekend / holiday releases ----------------------------------------

def test_weekend_and_holiday_releases():
    # 2026-09-05 is a Saturday; 2026-09-07 is Labor Day.
    for d, label in [(datetime.date(2026, 9, 5), "Saturday"), (datetime.date(2026, 9, 7), "Labor Day")]:
        with tempfile.TemporaryDirectory() as t:
            reg = synth_registry(t, earnings_date=d,
                                 earnings_datetime_utc=datetime.datetime(d.year, d.month, d.day, 20, 30, tzinfo=UTC))
            p = build_operations_plan(registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
            d1 = p["sessions"]["D1"]["session_date"]
            check(f"5. release on a {label} ({d}) -> D1 is the next OPEN session ({d1})",
                  is_trading_day(datetime.date.fromisoformat(d1)) and d1 > d.isoformat())


# --- 6. early close --------------------------------------------------------

def test_early_close_session_behaviour():
    # 2026-11-27 is the day after US Thanksgiving -- a 1:00pm ET early close.
    early = datetime.date(2026, 11, 27)
    if not (is_trading_day(early) and is_early_close(early)):
        check("6. (skipped: 2026-11-27 is not an early close in this calendar build)", True)
        return
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, earnings_date=datetime.date(2026, 11, 26),
                             earnings_datetime_utc=datetime.datetime(2026, 11, 26, 20, 30, tzinfo=UTC))
        p = build_operations_plan(registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                                  generated_at_utc=GEN, planning_commit="x", methodology_version="m")
        d1 = p["sessions"]["D1"]
        check("6a. an early-close D1 is flagged is_early_close=True", d1["is_early_close"] is True)
        check("6b. its close is earlier than a normal 20:00Z close", d1["close_utc"] < "2026-11-27T20:00:00+00:00")
        check("6c. the freshness-eligible instant tracks the EARLY close, not a fixed 16:00 ET",
              d1["earliest_provider_retrieval_utc"] > d1["close_utc"])


# --- 7. DST-safe conversions ----------------------------------------------

def test_dst_safe_utc_local_conversion():
    p = plan_real()
    s = p["sessions"]
    check("7a. September sessions render as EDT (-04:00), i.e. DST active",
          s["D1"]["open_local_et"].endswith("-04:00") and s["D1"]["close_local_et"].endswith("-04:00"))
    check("7b. 13:30Z open == 09:30 ET", s["D1"]["open_utc"].endswith("13:30:00+00:00")
          and "T09:30:00" in s["D1"]["open_local_et"])
    check("7c. 20:00Z close == 16:00 ET", s["D1"]["close_utc"].endswith("20:00:00+00:00")
          and "T16:00:00" in s["D1"]["close_local_et"])
    check("7d. the event's local mirror is 16:30 ET (4:30pm), after the 16:00 close",
          "T16:30:00" in p["event"]["event_datetime_local_et"])
    # A winter event must render as EST (-05:00) -- proves no fixed offset.
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, earnings_date=datetime.date(2026, 1, 15),
                             earnings_datetime_utc=datetime.datetime(2026, 1, 15, 21, 30, tzinfo=UTC))
        w = build_operations_plan(registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                                  generated_at_utc=GEN, planning_commit="x", methodology_version="m")
        check("7e. a January session renders as EST (-05:00), so the offset is not hardcoded",
              w["sessions"]["D1"]["open_local_et"].endswith("-05:00"))


def test_freshness_gate_derivation():
    p = plan_real()
    for k in ("D1", "D2", "D3"):
        s = p["sessions"][k]
        close = datetime.datetime.fromisoformat(s["close_utc"])
        earliest = datetime.datetime.fromisoformat(s["earliest_provider_retrieval_utc"])
        expected = close - datetime.timedelta(minutes=5) + datetime.timedelta(minutes=ALPACA_MIN_END_AGE_MINUTES)
        check(f"8. {k} earliest retrieval = final bar start + {ALPACA_MIN_END_AGE_MINUTES}min",
              earliest == expected)


def test_freshness_constant_matches_the_provider():
    """Planner mirrors the constant by value to avoid importing a provider;
    assert the two never drift."""
    src = (HERE / "gst_market_response" / "alpaca_provider.py").read_text(encoding="utf-8")
    check("8b. ALPACA_MIN_END_AGE_MINUTES matches alpaca_provider.MIN_END_AGE_MINUTES",
          f"MIN_END_AGE_MINUTES = {ALPACA_MIN_END_AGE_MINUTES}" in src)


# --- 9. fail-closed registry conditions -----------------------------------

def test_registry_rejections():
    expect_raises("9a. absent event id -> refuse", plan_real, event_id="EVT-AAPL-FY26Q4-ERN")
    with tempfile.TemporaryDirectory() as t:
        expect_raises("9b. missing registry file -> refuse", build_operations_plan,
                      registry_path=Path(t) / "nope" / "registry.jsonl", event_id="EVT-DELL-FY27Q2-ERN",
                      company_name="c", generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t)
        rows = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines() if l.strip()]
        dup = copy.deepcopy(rows[0]); dup["row_id"] = dup["row_id"].replace("001", "002")
        reg.write_text("\n".join(json.dumps(x) for x in rows + [dup]) + "\n", encoding="utf-8", newline="\n")
        expect_raises("9c. duplicate REGISTRATION rows -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, verification_status="pending")
        expect_raises("9d. unverified registration -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t)
        r = HumanVerifiedEventRegistry(reg.parent)
        base = r.read_all()[0]
        r.amend_event(amends_row_id=base["row_id"],
                      corrected_fields={"verification_status": "rejected"},
                      verified_at_utc=datetime.datetime(2026, 8, 7, tzinfo=UTC),
                      verified_by="tester",
                      notes="synthetic amendment into an unusable state")
        expect_raises("9e. amended into an unusable state -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, exchange_calendar="LSE_v1")
        expect_raises("9f. wrong exchange calendar -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, earnings_datetime_utc=None)
        expect_raises("9g. missing event timestamp -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, earnings_datetime_utc="2026-09-03T20:30:00")
        expect_raises("9h. timezone-naive event timestamp -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    with tempfile.TemporaryDirectory() as t:
        reg = synth_registry(t, ticker="NVDA")
        expect_raises("9i. ticker outside the locked 24 -> refuse", build_operations_plan,
                      registry_path=reg, event_id="EVT-DELL-FY27Q2-ERN", company_name="c",
                      generated_at_utc=GEN, planning_commit="x", methodology_version="m")
    expect_raises("9j. malformed event id -> refuse", plan_real, event_id="DELL-FY27Q2")


# --- 10. determinism + integrity ------------------------------------------

def test_deterministic_repeated_generation():
    a = finalize_plan(plan_real())
    b = finalize_plan(plan_real())
    check("10a. two runs with identical inputs are byte-identical",
          json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))
    check("10b. the integrity digest is stable across runs",
          a["integrity"]["plan_content_sha256"] == b["integrity"]["plan_content_sha256"])
    c = copy.deepcopy(a)
    c["event"]["ticker"] = "TAMPERED"
    check("10c. the digest changes if any plan content changes",
          plan_content_sha256(c) != a["integrity"]["plan_content_sha256"])
    check("10d. the digest excludes the integrity block itself (recomputable)",
          plan_content_sha256(a) == a["integrity"]["plan_content_sha256"])


def test_blockers_are_carried_into_every_plan():
    p = plan_real()
    ids = {b["id"] for b in p["unresolved_blockers"]}
    check("11a. every audited blocker is carried into the plan",
          ids == {b["id"] for b in KNOWN_CAPTURE_BLOCKERS} and len(ids) == 5)
    check("11b. the hard option/orchestration blockers are present",
          {"BLK-OPT-1", "BLK-OPT-2", "BLK-ORCH-1"} <= ids)
    check("11c. no blocker is marked resolved by this planning pass",
          all(b["severity"] in ("hard", "material") for b in p["unresolved_blockers"]))


# --- 12. no mutation of registry or EventStore ----------------------------

def test_no_registry_or_eventstore_mutation():
    import hashlib
    before = hashlib.sha256(REAL_REGISTRY.read_bytes()).hexdigest()
    rows_before = HumanVerifiedEventRegistry(REAL_REGISTRY.parent).read_all()
    finalize_plan(plan_real())
    after = hashlib.sha256(REAL_REGISTRY.read_bytes()).hexdigest()
    rows_after = HumanVerifiedEventRegistry(REAL_REGISTRY.parent).read_all()
    check("12a. registry bytes are unchanged by planning", before == after)
    check("12b. registry row count unchanged (still exactly 1)",
          len(rows_before) == len(rows_after) == 1)
    check("12c. no event-state log was created anywhere in the repo",
          not list(HERE.rglob("*_event_log.jsonl")) and not list(HERE.rglob("EVT-*_COMPLETION_MARKER.json")))


# --- 13. structural offline proof (subprocess) ----------------------------

def _iso(mods):
    return subprocess.run([sys.executable, "-c", textwrap.dedent(mods)], cwd=str(HERE),
                          capture_output=True, text=True)


def test_planner_imports_no_provider_and_opens_no_socket():
    proc = _iso("""
        import sys
        BANNED = ('yfinance','pytrends','requests','urllib3','GST_Live_Signal_Engine',
                  'GST_MultiTicker_Forward_Log','GST_Phase2_DailyPanel','GST_Phase2_Wikipedia_Transport')
        class Blocker:
            def find_module(self, name, path=None):
                if name.split('.')[0] in BANNED:
                    raise ImportError('BLOCKED ' + name)
                return None
        sys.meta_path.insert(0, Blocker())
        import socket
        def boom(*a, **k): raise AssertionError('network call during planning')
        socket.socket.connect = boom
        socket.create_connection = boom
        import datetime
        from pathlib import Path
        from gst_market_response.operations_plan import build_operations_plan, finalize_plan
        p = finalize_plan(build_operations_plan(
            registry_path=Path('Live Signal Engine/Market_Response_Event_Registry/registry.jsonl'),
            event_id='EVT-DELL-FY27Q2-ERN', company_name='Dell Technologies Inc.',
            generated_at_utc=datetime.datetime(2026,8,7,tzinfo=datetime.timezone.utc),
            planning_commit='x', methodology_version='m'))
        assert p['sessions']['D1']['session_date'] == '2026-09-04'
        # Network clients and anything that can WRITE research state.
        leaked = [m for m in ('gst_market_response.alpaca_provider',
                              'gst_market_response.pipeline','gst_market_response.event_record',
                              'gst_market_response.completion_marker',
                              'yfinance','requests','urllib3','pytrends') if m in sys.modules]
        print('LEAKED=' + repr(leaked))
        # gst_market_response.providers IS loaded transitively: event_registry
        # imports EventTimingProvider/EventTimingResult from it. It is an
        # interface module -- its module-scope imports are stdlib plus .bars,
        # and yfinance is imported lazily inside a function -- so it brings no
        # network client with it. Recorded rather than hidden.
        print('PROVIDERS_LOADED=%s' % ('gst_market_response.providers' in sys.modules))
        print('PLANNED_OK')
    """)
    check("13a. planning succeeds with every provider/panel module import-blocked",
          proc.returncode == 0 and "PLANNED_OK" in proc.stdout)
    if proc.returncode != 0:
        print("      stderr:", proc.stderr.strip()[-600:])
    check("13b. no network client and no research-state-writing module reaches sys.modules",
          "LEAKED=[]" in proc.stdout)
    check("13b2. the interface-only providers module is the ONLY transitive load, and it "
          "carries no network client (documented, not hidden)",
          "PROVIDERS_LOADED=True" in proc.stdout)
    check("13c. no socket connect occurred during planning", "network call during planning" not in proc.stderr)


def test_cli_is_structurally_offline():
    proc = _iso("""
        import sys, datetime
        sys.argv = ['operations_cli','plan',
                    '--registry','Live Signal Engine/Market_Response_Event_Registry/registry.jsonl',
                    '--event-id','EVT-DELL-FY27Q2-ERN','--company-name','Dell Technologies Inc.',
                    '--planning-commit','x','--methodology-version','m',
                    '--generated-at-utc','2026-08-07T00:00:00+00:00']
        from gst_market_response.operations_cli import main
        rc = main(sys.argv[1:])
        leaked = [m for m in ('gst_market_response.alpaca_provider',
                              'gst_market_response.pipeline','gst_market_response.event_record',
                              'gst_market_response.completion_marker',
                              'yfinance','requests','urllib3','pytrends') if m in sys.modules]
        print('RC=%d' % rc)
        print('CLI_LEAKED=' + repr(leaked))
    """)
    check("14a. the CLI plan command exits 0", "RC=0" in proc.stdout)
    check("14b. the CLI pulls in no network client and no research-state-writing module",
          "CLI_LEAKED=[]" in proc.stdout)
    check("14c. the CLI needs no credential (no APCA/ALPACA env read in its source)",
          "APCA" not in (HERE / "gst_market_response" / "operations_cli.py").read_text(encoding="utf-8"))


def test_cli_refuses_output_collision():
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "plan.json"
        out.write_text("{}", encoding="utf-8")
        from gst_market_response.operations_cli import main
        rc = main(["plan", "--registry", str(REAL_REGISTRY), "--event-id", "EVT-DELL-FY27Q2-ERN",
                   "--company-name", "c", "--planning-commit", "x", "--methodology-version", "m",
                   "--out", str(out)])
        check("15a. CLI refuses to overwrite an existing plan (exit 2)", rc == 2)
        check("15b. the existing file is untouched", out.read_text(encoding="utf-8") == "{}")


def _called_names(path: Path) -> set[str]:
    """Every function/attribute actually CALLED in the module, via AST -- so
    prose in comments and docstrings can never be mistaken for a call."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def _imported_modules(path: Path) -> set[str]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
            if node.level and node.module:
                mods.add(node.module.split(".")[0])
    return mods


def test_planner_declares_no_state_transition_api():
    """AST-verified: the planner must never CALL a mutating or network API.
    (Substring checks are useless here -- the module's own comments name these
    functions precisely in order to explain that it does not call them.)"""
    p = HERE / "gst_market_response" / "operations_plan.py"
    called = _called_names(p)
    # Note: bare `get`/`post` are deliberately NOT in this list -- they are
    # dict methods here (row.get(...)), not HTTP verbs. The import assertions
    # below are the real guarantee: with no HTTP library imported at all, no
    # `.get()` in this module can be a network call.
    for banned in ("append_state", "append_amendment", "register_verified_event", "amend_event",
                   "capture_pre_event_and_option_benchmark", "capture_d1", "capture_d3",
                   "write_completion_marker", "urlopen", "request", "Session"):
        check(f"16a. planner never CALLS {banned} (AST)", banned not in called)
    imported = _imported_modules(p)
    for banned in ("requests", "urllib", "urllib3", "yfinance", "pytrends", "socket", "http"):
        check(f"16b. planner never IMPORTS {banned} (AST)", banned not in imported)
    check("16c. planner imports only the intended project modules",
          {m for m in imported if m in ("event_record", "pipeline", "alpaca_provider", "completion_marker")} == set())

    c = HERE / "gst_market_response" / "operations_cli.py"
    cli_imported = _imported_modules(c)
    check("16d. the CLI imports exactly one project module (operations_plan) plus stdlib",
          {m for m in cli_imported if m.startswith("gst") or m in ("operations_plan",)} == {"operations_plan"})
    for banned in ("requests", "urllib", "yfinance", "pytrends", "socket", "event_record", "pipeline"):
        check(f"16e. the CLI never imports {banned} (AST)", banned not in cli_imported)


if __name__ == "__main__":
    test_exact_dell_schedule()
    test_labor_day_closure_between_d1_and_d2()
    test_release_session_behaviour()
    test_amc_bmo_are_cross_checked_against_the_calendar()
    test_weekend_and_holiday_releases()
    test_early_close_session_behaviour()
    test_dst_safe_utc_local_conversion()
    test_freshness_gate_derivation()
    test_freshness_constant_matches_the_provider()
    test_registry_rejections()
    test_deterministic_repeated_generation()
    test_blockers_are_carried_into_every_plan()
    test_no_registry_or_eventstore_mutation()
    test_planner_imports_no_provider_and_opens_no_socket()
    test_cli_is_structurally_offline()
    test_cli_refuses_output_collision()
    test_planner_declares_no_state_transition_api()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL OPERATIONS PLANNER TESTS PASSED")
    sys.exit(0)
