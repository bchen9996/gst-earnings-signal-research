#!/usr/bin/env python3
# DIFFERENTIAL harness for the second corrective audit pass.
#
# Every regression added in that pass is required to FAIL against ed4df74 for
# the specific defect it covers. Asserting that by hand is not reproducible, so
# this file proves it mechanically: for each defect it RESTORES the exact
# ed4df74 behaviour in isolation and asserts that the property the new
# regression guarantees is then VIOLATED.
#
# A test here passing means "the ed4df74 code really was broken in this way, and
# the corresponding regression really does depend on the fix". If a fix were
# reverted, its regression in test_market_response_pre_event_capture.py fails;
# if a fix were a no-op, the matching case here fails instead. The two files are
# load-bearing in opposite directions.
#
# Synthetic fixtures and temporary directories only. No provider, no socket, no
# credential, no operational artifact. The real DELL event is never touched.
#
# Run directly: python test_market_response_second_pass_differential.py

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = Path(os.path.dirname(os.path.abspath(__file__)))

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


# Reuse the synthetic fixtures rather than duplicating them, so the differential
# runs against exactly the panels the regressions run against.
from test_market_response_pre_event_capture import (  # noqa: E402
    ANCHOR,
    CORE,
    EVENT,
    METH,
    OPT_NONE,
    OPT_VALID,
    STRICT_FULL,
    _validate,
    synth_panel,
)
from gst_market_response.event_record import EventStore  # noqa: E402
from gst_market_response.pipeline import (  # noqa: E402
    capture_d1,
    capture_pre_event_and_option_benchmark_v0_1,
)
from gst_market_response.pre_event_capture import execute_pre_event_capture  # noqa: E402


# ---------------------------------------------------------------------------
# D1. atomic_write_json_no_overwrite: exists() then os.replace()
# ---------------------------------------------------------------------------

def diff_1_exists_then_replace_destroys_a_competitor():
    """ed4df74: `if path.exists(): raise` followed by atomic_write_bytes(),
    whose final step is os.replace(). os.replace() REPLACES unconditionally."""
    import gst_market_response.atomic_io as aio
    from gst_market_response.atomic_io import ImmutableArtifactExistsError, atomic_write_json

    def ed4df74_no_overwrite(path, obj):
        path = Path(path)
        if path.exists():                      # (1) check
            raise ImmutableArtifactExistsError(str(path))
        atomic_write_json(path, obj)           # (2) write temp, then os.replace()

    competitor = b'{"written_by": "the other process"}'
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); target = tmp / "EVT-X_PRE_EVENT_CAPTURE_MARKER.json"
        real_fsync, fired = aio.os.fsync, []

        def racing_fsync(fd):
            if not fired:
                fired.append(True)
                target.write_bytes(competitor)   # created between (1) and (2)
            return real_fsync(fd)

        aio.os.fsync = racing_fsync
        try:
            raised = False
            try:
                ed4df74_no_overwrite(target, {"written_by": "us"})
            except ImmutableArtifactExistsError:
                raised = True
        finally:
            aio.os.fsync = real_fsync
        check("D1. ed4df74's exists()+replace did NOT raise on the racing competitor",
              not raised)
        check("D1b. ed4df74 DESTROYED the competing artifact's bytes (R1 depends on the fix)",
              target.read_bytes() != competitor)
        check("D1c. the injection fired (the differential is not vacuous)", bool(fired))


# ---------------------------------------------------------------------------
# D2. dangling PRE_EVENT_PENDING was permanently unrecoverable
# ---------------------------------------------------------------------------

def diff_2_dangling_pending_was_a_dead_end():
    """ed4df74 refused execution whenever ANY PRE_EVENT_PENDING existed, and the
    pending record may never be deleted -- so a crash between the two appends
    left the event permanently stuck."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        store.mkdir(parents=True, exist_ok=True)
        s = EventStore(store)
        s.append_state(EVENT, "REGISTERED", {"ticker": "DELL"})
        s.append_state(EVENT, "PRE_EVENT_PENDING", {})     # the ed4df74 shape: no fingerprint
        existing = [r for r in s.read_all(EVENT) if r["record_type"] == "STATE"]

        ed4df74_refuses = any(
            r["state"] in ("PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED") for r in existing)
        check("D2. ed4df74 refused any rerun once PRE_EVENT_PENDING existed", ed4df74_refuses)
        check("D2b. ...and nothing had actually been captured, so the event was stuck",
              not any(r["state"] == "PRE_EVENT_CAPTURED" for r in existing))
        # The v0.2 contract distinguishes the two cases mechanically.
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store)
        check("D2c. an UNFINGERPRINTED pending is still not resumable under v0.2 (fail closed)",
              rep.resume_from_pending is False)
        seed = _validate(tmp, csv_p=c, marker_p=m, store=tmp / "fresh")
        check("D2d. a fingerprint is what makes resume decidable at all",
              seed.capture_fingerprint is not None
              and seed.capture_fingerprint["capture_fingerprint_sha256"])


# ---------------------------------------------------------------------------
# D3. IV / realized vol were backed by the PRICE leg
# ---------------------------------------------------------------------------

def diff_3_iv_and_realized_vol_inherited_the_price_status():
    """ed4df74 mapped panel_implied_volatility and realized_volatility to
    source_status_price, so a failed iv_status or realized_vol_status passed the
    six-field gate whenever price history happened to be OK."""
    from gst_market_response import completeness as comp

    original = dict(comp.STRICT_CORE_STATUS_KEY)
    try:
        comp.STRICT_CORE_STATUS_KEY["panel_implied_volatility"] = "source_status_price"
        comp.STRICT_CORE_STATUS_KEY["realized_volatility"] = "source_status_price"
        iv_bad = dict(STRICT_FULL, source_status_iv="error")
        rv_bad = dict(STRICT_FULL, source_status_realized_vol="error")
        check("D3. under ed4df74's mapping a FAILED iv_status still passed the strict gate",
              comp.evaluate_strict_core_v0_2(iv_bad).passed)
        check("D3b. ...and so did a FAILED realized_vol_status",
              comp.evaluate_strict_core_v0_2(rv_bad).passed)
    finally:
        comp.STRICT_CORE_STATUS_KEY.clear()
        comp.STRICT_CORE_STATUS_KEY.update(original)
    check("D3c. with the corrected mapping the same fixtures fail",
          not comp.evaluate_strict_core_v0_2(dict(STRICT_FULL, source_status_iv="error")).passed
          and not comp.evaluate_strict_core_v0_2(
              dict(STRICT_FULL, source_status_realized_vol="error")).passed)


# ---------------------------------------------------------------------------
# D4. a D1/D3 PARTIAL won the reverse search for the pre-event record
# ---------------------------------------------------------------------------

def diff_4_partial_reverse_search_stole_the_pre_event_record():
    """ed4df74 searched backwards for the last record in
    ("PRE_EVENT_CAPTURED", "PARTIAL") with fields. PARTIAL is reachable from D1
    and D3 too, so a later D1 failure won and the pre-event eligibility was
    replaced by D1 interval fields."""
    from gst_market_response import completion_marker as cm

    def ed4df74_selector(state_records, stage):
        return next((r for r in reversed(state_records)
                     if r["state"] in ("PRE_EVENT_CAPTURED", "PARTIAL") and r.get("fields")), None)

    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = EventStore(root); s.append_state(EVENT, "REGISTERED", {})
        capture_pre_event_and_option_benchmark_v0_1(s, EVENT, CORE, OPT_NONE)
        capture_d1(s, EVENT, {"overnight_gap": 0.01})          # incomplete -> D1 PARTIAL

        real = cm.select_stage_record
        try:
            cm.select_stage_record = ed4df74_selector
            marker = cm.write_completion_marker(root, EVENT, s)
        finally:
            cm.select_stage_record = real
        check("D4. under ed4df74's reverse search the D1 PARTIAL replaced the pre-event record",
              marker["module_eligibility"] is None)
        check("D4b. ...and the marker reported it as a legacy record instead of the real tier",
              "legacy" in (marker["module_eligibility_note"] or "").lower())

        # Corrected: the same chronology resolves to the pre-event record.
        (root / f"{EVENT}_COMPLETION_MARKER.json").unlink()
        fixed = cm.write_completion_marker(root, EVENT, s)
        check("D4c. with the corrected selector the pre-event eligibility survives a D1 PARTIAL",
              fixed["module_eligibility"] is not None
              and fixed["module_eligibility"]["pre_event_completeness_tier"]
              == "core_only_no_option_benchmark")


# ---------------------------------------------------------------------------
# D5. the option artifact was unbound between validation and execution
# ---------------------------------------------------------------------------

def diff_5_option_artifact_could_be_swapped_after_validation():
    """ed4df74 re-verified only the panel files. Nothing bound the option
    disposition, so a caller could validate UNAVAILABLE_NO_VERIFIED_SOURCE and
    execute with a dict claiming a verified OPRA benchmark."""
    from gst_market_response import pre_event_capture as pec

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t); c, m = synth_panel(tmp); store = tmp / "store"
        rep = _validate(tmp, csv_p=c, marker_p=m, store=store, opt=OPT_NONE)
        # Restore ed4df74: no option digest, no capture fingerprint.
        real_digest = pec.option_fields_digest
        try:
            pec.option_fields_digest = lambda _fields: rep.option_fields_digest
            rep.capture_fingerprint = None
            res = execute_pre_event_capture(
                report=rep, store_root=store, panel_csv=c, panel_marker=m, ticker="DELL",
                research_commit_sha="deadbeef", methodology_version=METH,
                option_benchmark_fields=dict(OPT_VALID))     # <- swapped after validation
        finally:
            pec.option_fields_digest = real_digest
        captured = [r for r in EventStore(store).read_all(EVENT)
                    if r["state"] == "PRE_EVENT_CAPTURED"][0]["fields"]
        check("D5. ed4df74 accepted an option artifact that was never validated",
              res["state"] == "PRE_EVENT_CAPTURED")
        check("D5b. ...and recorded a VALID_VERIFIED OPRA benchmark that validation "
              "never approved (R9 depends on the fix)",
              captured["option_benchmark_status"] == "VALID_VERIFIED"
              and captured["option_benchmark_eligible"] is True)


# ---------------------------------------------------------------------------
# D6. blank dates were discarded before validation
# ---------------------------------------------------------------------------

def diff_6_blank_dates_were_discarded_before_validation():
    """ed4df74 built a set of row values and then called `.discard("")`, so a
    blank price_asof_date among otherwise agreeing rows vanished and the panel
    resolved to a single value. run_date ambiguity silently yielded None, which
    SKIPPED the run_date >= price_asof_date check entirely."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        c, _m = synth_panel(tmp, other_tickers=("MSFT",), blank_asof_rows=(1,))
        with open(c, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        asof = {(r.get("price_asof_date") or "").strip() for r in rows}
        runs = {(r.get("run_date") or "").strip() for r in rows}
        asof.discard(""); runs.discard("")                    # <- the ed4df74 line
        check("D6. ed4df74 discarded the blank price_asof_date and resolved a single session",
              len(asof) == 1 and len(rows) == 2)
        check("D6b. ...even though one of the two rows recorded no session at all",
              sum(1 for r in rows if not (r.get("price_asof_date") or "").strip()) == 1)

        c2, _ = synth_panel(tmp, other_tickers=("MSFT",), run_date_by_row={1: "2026-09-04"},
                            name="SYNTHETIC_panel_runs.csv")
        with open(c2, "r", encoding="utf-8", newline="") as f:
            rows2 = list(csv.DictReader(f))
        runs2 = {(r.get("run_date") or "").strip() for r in rows2}
        runs2.discard("")
        ed4df74_run = sorted(runs2)[0] if len(runs2) == 1 else None
        check("D6c. ed4df74 yielded run_date=None on disagreement, skipping the ordering check",
              ed4df74_run is None and len(runs2) == 2)

        # Corrected behaviour, on the same fixtures.
        from gst_market_response.pre_event_capture import _audit_panel_dates
        check("D6d. the corrected audit rejects the blank row",
              _audit_panel_dates(c).blank_price_asof_rows == 1
              and not _audit_panel_dates(c).ok)
        check("D6e. the corrected audit rejects disagreeing run dates rather than skipping",
              not _audit_panel_dates(c2).ok)


# ---------------------------------------------------------------------------
# D7. the v0.2 capture path reached the v0.1 core gate
# ---------------------------------------------------------------------------

def diff_7_v0_2_path_used_the_v0_1_core_gate():
    """ed4df74's capture_pre_event_and_option_benchmark() -- the one the v0.2
    orchestrator called -- judged the core with is_valid_pre_event_observation()
    via evaluate_pre_event_modules()."""
    from gst_market_response.completeness import (evaluate_pre_event_modules,
                                                  evaluate_pre_event_modules_v0_2,
                                                  is_valid_pre_event_observation)
    weak = {"previous_close": 101.5, "pre_event_snapshot_asof_utc": "2026-09-02T20:00:00+00:00",
            "gst_zscore": 1.2, "source_status_gst": "ok"}
    check("D7. the v0.1 gate accepts an observation with no wiki z-score, IV, "
          "realized vol or volume", is_valid_pre_event_observation(weak))
    check("D7b. ed4df74's module evaluator therefore reported the core as ELIGIBLE",
          evaluate_pre_event_modules(weak, OPT_NONE).core_pre_event_eligible is True)
    check("D7c. the v0.2 evaluator reports it INELIGIBLE (R12 depends on the fix)",
          evaluate_pre_event_modules_v0_2(weak, OPT_NONE).core_pre_event_eligible is False)
    check("D7d. and a genuine six-field observation is still eligible under v0.2",
          evaluate_pre_event_modules_v0_2(STRICT_FULL, OPT_NONE).core_pre_event_eligible is True)


def diff_8_real_artifacts_untouched():
    from gst_market_response.event_registry import HumanVerifiedEventRegistry
    reg = HERE / "Live Signal Engine" / "Market_Response_Event_Registry" / "registry.jsonl"
    rows = HumanVerifiedEventRegistry(reg.parent).read_all()
    check("D8. the real DELL registry still holds exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["verification_status"] == "verified")
    check("D8b. no real event log or stage marker exists anywhere in the repo",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


if __name__ == "__main__":
    diff_1_exists_then_replace_destroys_a_competitor()
    diff_2_dangling_pending_was_a_dead_end()
    diff_3_iv_and_realized_vol_inherited_the_price_status()
    diff_4_partial_reverse_search_stole_the_pre_event_record()
    diff_5_option_artifact_could_be_swapped_after_validation()
    diff_6_blank_dates_were_discarded_before_validation()
    diff_7_v0_2_path_used_the_v0_1_core_gate()
    diff_8_real_artifacts_untouched()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL SECOND-PASS DIFFERENTIAL TESTS PASSED")
    sys.exit(0)
