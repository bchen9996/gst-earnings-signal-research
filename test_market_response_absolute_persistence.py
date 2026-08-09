#!/usr/bin/env python3
# Deterministic tests for canonical absolute-response persistence.
#
# Implementation of an EXISTING specification (SPEC v0.1 abs_* fields). No new
# formula, no analysis, no model, no candidate screening, no provider, no
# socket. Synthetic fixtures and temporary directories only.
#
# Run directly: python test_market_response_absolute_persistence.py

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

# --- blockers installed BEFORE importing any project module ----------------


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

_BANNED_TOP = {"yfinance", "pytrends", "requests", "urllib3", "httpx", "aiohttp"}


class _BanProviders:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _BANNED_TOP:
            raise ImportError("BLOCKED provider import: " + fullname)
        return None


sys.meta_path.insert(0, _BanProviders())

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))

from gst_market_response import completeness as C  # noqa: E402
from gst_market_response import response_magnitude as RM  # noqa: E402
from gst_market_response.completion_marker import write_completion_marker  # noqa: E402
from gst_market_response.derivations import abs_or_none  # noqa: E402
from gst_market_response.event_record import EventStore  # noqa: E402
from gst_market_response.pipeline import (  # noqa: E402
    capture_d1,
    capture_d3,
    capture_pre_event_and_option_benchmark_v0_1,
)
from gst_market_response.stage_markers import (  # noqa: E402
    STAGE_D1,
    STAGE_FINAL,
    build_stage_marker,
    marker_path,
    verify_marker_ties_out,
    write_stage_marker,
)

EVENT = "EVT-DELL-FY27Q2-ERN"
LSE = HERE / "Live Signal Engine"
REGISTRY_P = LSE / "Market_Response_Event_Registry" / "registry.jsonl"

CORE = {"previous_close": 101.5, "pre_event_snapshot_asof_utc": "2026-09-02T20:00:00+00:00",
        "gst_zscore": 1.2, "source_status_gst": "ok"}
OPT_NONE = {"option_benchmark_status": "UNAVAILABLE_NO_VERIFIED_SOURCE",
            "option_benchmark_unavailable_reason": "no OPRA-entitled source",
            "expiration": None, "underlying_price": None, "quote_timestamp_utc": None,
            "straddle_mid": None, "long_executable_implied_move_cost": None}

# Deliberately mixed signs, an exact zero, and a negative -- so sign handling,
# zero handling and magnitude are all exercised by the same fixture.
D1_SIGNED = {"overnight_gap": -0.0412, "open_to_30m": 0.0075,
             "thirty_min_to_close": 0.0, "open_to_close": -0.0138}
D3_SIGNED = {"close_T1_to_close_T2": 0.0261, "close_T1_to_close_T3": -0.0093}

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
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: {label} (raised {type(e).__name__}, expected {exc_type.__name__})")
        FAILURES.append(label)
    else:
        print(f"FAIL: {label} (did not raise)")
        FAILURES.append(label)


def _seed(root: Path) -> EventStore:
    s = EventStore(root)
    s.append_state(EVENT, "REGISTERED", {})
    capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
    return s


# ============ 1. the six exact mappings ====================================

def test_1_mappings():
    check("1. D1 map is exactly the four specified pairs",
          RM.D1_ABS_FIELD_MAP == {"overnight_gap": "abs_overnight_gap",
                                  "open_to_30m": "abs_open_to_30m",
                                  "thirty_min_to_close": "abs_thirty_min_to_close",
                                  "open_to_close": "abs_open_to_close"})
    check("1b. D3 map is exactly the two specified pairs",
          RM.D3_ABS_FIELD_MAP == {"close_T1_to_close_T2": "abs_close_T1_to_close_T2",
                                  "close_T1_to_close_T3": "abs_close_T1_to_close_T3"})
    check("1c. six mappings in total", len(RM.ALL_ABS_FIELD_MAP) == 6)
    check("1d. every signed key is a production required field",
          set(RM.D1_ABS_FIELD_MAP) == set(C.D1_REQUIRED_FIELDS)
          and set(RM.D3_ABS_FIELD_MAP) == set(C.D3_REQUIRED_FIELDS))
    # the single definition of abs() is the production helper
    src = (HERE / "gst_market_response" / "response_magnitude.py").read_text(encoding="utf-8")
    check("1e. the module reuses derivations.abs_or_none", "abs_or_none" in src)
    check("1f. it recomputes no signed-return formula",
          not re.search(r"next_session_open|previous_close\s*-\s*1|/\s*previous_close", src))


# ============ 2-4. positive, negative, zero, None; never negative ==========

def test_2_value_behaviour():
    cases = [(0.05, 0.05), (-0.05, 0.05), (0.0, 0.0), (-0.0, 0.0), (None, None)]
    for signed, expected in cases:
        got = RM.derive_absolute_fields({"overnight_gap": signed},
                                        RM.D1_ABS_FIELD_MAP)["abs_overnight_gap"]
        check(f"2. abs({signed!r}) -> {expected!r}", got == expected and got is not False)
    check("2b. a signed 0.0 yields 0.0, never None",
          RM.derive_absolute_fields({"overnight_gap": 0.0},
                                    RM.D1_ABS_FIELD_MAP)["abs_overnight_gap"] == 0.0)
    check("2c. a missing signed value yields None, never 0.0",
          RM.derive_absolute_fields({"overnight_gap": None},
                                    RM.D1_ABS_FIELD_MAP)["abs_overnight_gap"] is None)
    check("2d. an ABSENT signed key produces no abs key at all (absence preserved)",
          RM.derive_absolute_fields({}, RM.D1_ABS_FIELD_MAP) == {})
    out = RM.apply_absolute_fields({**D1_SIGNED, **D3_SIGNED}, RM.ALL_ABS_FIELD_MAP)
    check("3. every signed value is unchanged by derivation",
          all(out[k] == v for k, v in {**D1_SIGNED, **D3_SIGNED}.items()))
    check("4. no absolute value is negative",
          all(out[a] is None or out[a] >= 0 for a in RM.ALL_ABS_FIELDS))
    check("4b. each absolute equals abs_or_none of its signed counterpart",
          all(out[a] == abs_or_none(out[s]) for s, a in RM.ALL_ABS_FIELD_MAP.items()))
    check("4c. the input dict is not mutated",
          "abs_overnight_gap" not in D1_SIGNED)


# ============ 5-7. persistence in records and markers ======================

def test_5_6_7_persistence():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = _seed(root)
        st1 = capture_d1(s, EVENT, dict(D1_SIGNED))
        check("5. D1 capture reaches D1_COMPLETE", st1 == "D1_COMPLETE")
        d1rec = [r for r in s.read_all(EVENT) if r["state"] == "D1_COMPLETE"][0]["fields"]
        for a in RM.D1_ABS_FIELDS:
            check(f"5b. D1_COMPLETE persists {a}", a in d1rec)
        check("5c. persisted D1 absolutes are canonical",
              all(d1rec[a] == abs_or_none(D1_SIGNED[sgn])
                  for sgn, a in RM.D1_ABS_FIELD_MAP.items()))
        check("5d. persisted D1 signed values are unchanged",
              all(d1rec[k] == v for k, v in D1_SIGNED.items()))

        write_stage_marker(root, EVENT, STAGE_D1, s)
        mk1 = json.loads(marker_path(root, EVENT, STAGE_D1).read_text(encoding="utf-8"))
        check("7. the D1 stage marker carries a response_magnitude block",
              "response_magnitude" in mk1)
        check("7b. marker D1 values equal the stored record values",
              all(mk1["response_magnitude"][a] == d1rec[a] for a in RM.D1_ABS_FIELDS))
        ok, diffs = verify_marker_ties_out(root, EVENT, STAGE_D1, s)
        check("7c. the D1 marker ties out including response_magnitude", ok and not diffs)

        st3 = capture_d3(s, EVENT, dict(D3_SIGNED))
        check("6. D3 capture reaches COMPLETE", st3 == "COMPLETE")
        d3rec = [r for r in s.read_all(EVENT) if r["state"] == "COMPLETE"][0]["fields"]
        for a in RM.D3_ABS_FIELDS:
            check(f"6b. COMPLETE persists {a}", a in d3rec)
        check("6c. persisted D3 absolutes are canonical",
              all(d3rec[a] == abs_or_none(D3_SIGNED[sgn])
                  for sgn, a in RM.D3_ABS_FIELD_MAP.items()))
        check("6d. persisted D3 signed values are unchanged",
              all(d3rec[k] == v for k, v in D3_SIGNED.items()))

        mkf = write_stage_marker(root, EVENT, STAGE_FINAL, s)
        check("7d. the final marker carries all six canonical values",
              all(mkf["response_magnitude"][a] is not None or a is None
                  for a in RM.ALL_ABS_FIELDS)
              and set(RM.ALL_ABS_FIELDS) <= set(mkf["response_magnitude"]))
        check("7e. final-marker values equal the stored records",
              all(mkf["response_magnitude"][a] == d1rec[a] for a in RM.D1_ABS_FIELDS)
              and all(mkf["response_magnitude"][a] == d3rec[a] for a in RM.D3_ABS_FIELDS))
        cm = write_completion_marker(root, EVENT, s)
        check("7f. the v0.1 completion marker carries the same canonical values",
              all(cm["response_magnitude"][a] == d1rec[a] for a in RM.D1_ABS_FIELDS)
              and all(cm["response_magnitude"][a] == d3rec[a] for a in RM.D3_ABS_FIELDS))


# ============ 8-9. caller-supplied values ==================================

def test_8_9_caller_supplied():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = _seed(root)
        log = root / f"{EVENT}.jsonl"
        before = log.read_bytes()
        bad = {**D1_SIGNED, "abs_overnight_gap": 0.9999}
        expect_raises("8. a conflicting caller-supplied absolute fails closed",
                      RM.AbsoluteFieldConflictError, capture_d1, s, EVENT, bad)
        check("8b. the refusal wrote zero bytes -- not even D1_PENDING",
              log.read_bytes() == before)
        check("8c. no D1 state record exists after the refusal",
              not [r for r in s.read_all(EVENT) if r["state"] in ("D1_PENDING", "D1_COMPLETE")])
        check("8d. the error is a dedicated type, not a bare ValueError subclass name",
              RM.AbsoluteFieldConflictError.__name__ == "AbsoluteFieldConflictError")
        # a supplied None where a real value is canonical is also a conflict
        expect_raises("8e. supplying None against a real canonical value fails closed",
                      RM.AbsoluteFieldConflictError, RM.apply_absolute_fields,
                      {**D1_SIGNED, "abs_overnight_gap": None}, RM.D1_ABS_FIELD_MAP)
        expect_raises("8f. supplying a non-numeric absolute fails closed",
                      RM.AbsoluteFieldConflictError, RM.apply_absolute_fields,
                      {**D1_SIGNED, "abs_overnight_gap": "0.0412"}, RM.D1_ABS_FIELD_MAP)

    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = _seed(root)
        agreeing = {**D1_SIGNED, "abs_overnight_gap": abs(D1_SIGNED["overnight_gap"])}
        st = capture_d1(s, EVENT, agreeing)
        rec = [r for r in s.read_all(EVENT) if r["state"] == "D1_COMPLETE"][0]["fields"]
        check("9. an exactly-agreeing caller value is accepted", st == "D1_COMPLETE")
        check("9b. it does not change the canonical result",
              rec["abs_overnight_gap"] == abs_or_none(D1_SIGNED["overnight_gap"]))
        check("9c. the signed value is still unchanged",
              rec["overnight_gap"] == D1_SIGNED["overnight_gap"])


# ============ 10-11. missing values, PARTIAL, no zero-fill =================

def test_10_11_missing():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = _seed(root)
        incomplete = {**D1_SIGNED, "open_to_30m": None}
        st = capture_d1(s, EVENT, incomplete)
        check("10. a missing signed value follows existing PARTIAL behaviour",
              st == "PARTIAL")
        rec = [r for r in s.read_all(EVENT) if r["state"] == "PARTIAL"][-1]["fields"]
        check("10b. the PARTIAL record still carries the abs_* fields",
              all(a in rec for a in RM.D1_ABS_FIELDS))
        check("11. the missing value's absolute is None, NOT 0.0",
              rec["abs_open_to_30m"] is None and rec["open_to_30m"] is None)
        check("11b. present values still have real absolutes",
              rec["abs_overnight_gap"] == abs(D1_SIGNED["overnight_gap"]))
        check("11c. a legitimate 0.0 stays 0.0 and is not confused with missing",
              rec["abs_thirty_min_to_close"] == 0.0)
        check("10c. the failure stage is still d1",
              rec.get("failure_stage") == "d1")


# ============ 12-13. gates unchanged; history not rewritten ================

def test_12_13_invariants():
    check("12. D1_REQUIRED_FIELDS unchanged",
          C.D1_REQUIRED_FIELDS == ("overnight_gap", "open_to_30m",
                                   "thirty_min_to_close", "open_to_close"))
    check("12b. D3_REQUIRED_FIELDS unchanged",
          C.D3_REQUIRED_FIELDS == ("close_T1_to_close_T2", "close_T1_to_close_T3"))
    check("12c. no abs_* field became a completeness requirement",
          not (set(RM.ALL_ABS_FIELDS) & (set(C.D1_REQUIRED_FIELDS) | set(C.D3_REQUIRED_FIELDS))))
    check("12d. the strict v0.2 core gate is unchanged",
          C.STRICT_CORE_SIX_FIELDS == ("gst_zscore", "wiki_zscore", "panel_implied_volatility",
                                       "realized_volatility", "previous_close", "volume"))
    check("12e. option dispositions unchanged",
          C.OptionBenchmarkDisposition.ALL == ("VALID_VERIFIED",
                                               "UNAVAILABLE_NO_VERIFIED_SOURCE",
                                               "LOOKUP_FAILED", "NOT_ATTEMPTED"))
    check("12f. completeness tiers unchanged",
          C.PRE_EVENT_TIERS == ("core_invalid", "core_only_no_option_benchmark",
                                "core_and_option_benchmark"))
    # a D1 record whose abs_* fields are absent (a historical record) is still
    # gated exactly as before, and nothing backfills it
    legacy = dict(D1_SIGNED)
    check("13. a historical D1 record with no abs_* fields still passes the D1 gate",
          C.is_valid_d1_decomposition(legacy))
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = _seed(root)
        s.append_state(EVENT, "D1_PENDING", {})
        s.append_state(EVENT, "D1_COMPLETE", dict(D1_SIGNED))   # written the old way
        before = (root / f"{EVENT}.jsonl").read_bytes()
        mk = build_stage_marker(s, EVENT, STAGE_D1)
        check("13b. building a marker over a historical record rewrites nothing",
              (root / f"{EVENT}.jsonl").read_bytes() == before)
        check("13c. the historical record is transparently missing its abs_* values",
              mk["response_magnitude"] == {})
        rec = [r for r in s.read_all(EVENT) if r["state"] == "D1_COMPLETE"][0]["fields"]
        check("13d. no abs_* key was backfilled into the historical record",
              not any(a in rec for a in RM.ALL_ABS_FIELDS))


# ============ 14-15. HYP-01 lock intact; no analysis runner ================

def test_14_15_lock_and_no_runner():
    lock = json.loads((LSE / "GST_HYP01_ANALYSIS_LOCK_v1.0.json").read_text(encoding="utf-8"))
    p, m, s = lock["predictor"], lock["primary_model"], lock["sample"]
    check("14. predictor still continuous unthresholded gst_zscore",
          p["primary"] == "gst_zscore" and p["form"] == "continuous"
          and p["thresholded"] is False)
    check("14b. primary outcome still abs_overnight_gap",
          lock["primary_outcome"]["field"] == "abs_overnight_gap")
    check("14c. primary model unchanged",
          m["formula"] == "abs_overnight_gap ~ gst_zscore")
    check("14d. alpha 0.05 two-sided unchanged",
          m["alpha"] == 0.05 and m["sidedness"] == "two_sided")
    check("14e. ticker clustering with finite-sample correction unchanged",
          m["covariance"] == {"type": "cluster_robust", "cluster_variable": "ticker",
                              "finite_sample_correction": True})
    check("14f. ordering and n=60 unchanged",
          s["target_n"] == 60 and "response-session date" in s["ordering"]["primary_key"]
          and "event_id" in s["ordering"]["tie_breaker"])
    check("14g. still no results and no frozen event ids",
          lock["results"] is None and lock["frozen_event_ids"] == []
          and lock["eligible_events_now"] == 0)
    # the implementation status -- and only that -- has moved
    check("14h. the persistence status now records the field as emitted",
          lock["primary_outcome"]["persistence_status"] == "IMPLEMENTED_AND_EMITTED")
    check("14i. it is no longer blocking for freeze",
          lock["primary_outcome"]["blocking_for_freeze"] is False)
    check("14j. the analytical definition is untouched",
          lock["primary_outcome"]["definition"] == "abs(overnight_gap)"
          and lock["primary_outcome"]["new_formula_created"] is False)
    check("14k. the emitting path is named",
          "capture_d1" in lock["primary_outcome"].get("emitted_by", ""))

    # Scoped to HYP-01. The repo root carries pre-existing legacy analysis
    # scripts from the historical backtest work; this task adds no HYP-01
    # runner and touches none of them.
    runners = [p_.name for p_ in HERE.glob("*.py")
               if re.search(r"hyp0?1", p_.name, re.I) and not p_.name.startswith("test_")]
    check(f"15. no HYP-01 analysis runner exists (found={runners})", not runners)
    pkg = "\n".join(p_.read_text(encoding="utf-8")
                    for p_ in (HERE / "gst_market_response").glob("*.py"))
    # Precise modelling tokens only. A bare "regress" would match the word
    # "regression" in a comment about the v0.1 regression suite.
    for banned in ("statsmodels", "sklearn", "scipy.stats", "p_value", "pvalue",
                   "OLS(", "cluster_robust", ".fit("):
        check(f"15b. the market-response package performs no modelling ({banned})",
              banned not in pkg)


# ============ 16. no screening, provider or network ========================

def test_16_no_network_or_screening():
    reached = []
    for host in ("data.alpaca.markets", "en.wikipedia.org", "trends.google.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001
            pass
    check(f"16. sockets are blocked (reached={reached})", not reached)
    for mod in ("requests", "yfinance", "pytrends"):
        if mod in sys.modules:
            check(f"16b. {mod} is not importable", False)
            continue
        try:
            __import__(mod)
            check(f"16b. {mod} is not importable", False)
        except ImportError:
            check(f"16b. {mod} is not importable", True)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"16c. no provider module reached sys.modules (leaked={leaked})", not leaked)
    cohort = json.loads((LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json").read_text(
        encoding="utf-8"))
    check("16d. cohort screening rows remain empty", cohort["screening_rows"] == [])
    check("16e. no cohort screening log exists",
          not (LSE / "Market_Response_Event_Registry" / "cohort_screening_log.jsonl").exists())
    raw = REGISTRY_P.read_bytes()
    check("16f. the DELL registry is byte-identical to the baseline",
          hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
          == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    check("16g. DELL remains a single verified REGISTRATION row",
          len(rows) == 1 and rows[0]["verification_status"] == "verified")
    check("16h. no real event log or stage marker exists anywhere",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))
    hyp = json.loads((LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json").read_text(
        encoding="utf-8"))
    H = {h["hypothesis_id"]: h for h in hyp["hypotheses"]}
    check("16i. HYP-02 unchanged",
          H["HYP-02"]["minimum_eligible_events"] == 60
          and H["HYP-02"]["status"] == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED")
    check("16j. HYP-03 unchanged",
          H["HYP-03"]["minimum_eligible_events"] == 40
          and H["HYP-03"]["status"] == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED")


if __name__ == "__main__":
    test_1_mappings()
    test_2_value_behaviour()
    test_5_6_7_persistence()
    test_8_9_caller_supplied()
    test_10_11_missing()
    test_12_13_invariants()
    test_14_15_lock_and_no_runner()
    test_16_no_network_or_screening()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL ABSOLUTE PERSISTENCE TESTS PASSED")
    sys.exit(0)
