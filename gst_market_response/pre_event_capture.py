# Pre-event capture orchestrator.
#
# Connects components that already exist; it implements no calendar
# arithmetic, no panel parsing, no gate logic and no state-machine rules of its
# own. Everything it decides, it decides by calling the merged production
# implementations:
#
#   operations_plan.build_operations_plan   -> verified registry row + XNYS anchor
#   phase2_adapter.import_pre_event_fields_for_ticker -> panel CSV/marker + hashes
#   completeness.evaluate_pre_event_modules -> per-module eligibility (protocol v0.2)
#   pipeline.capture_pre_event_and_option_benchmark -> state transitions
#   completion_marker.write_completion_marker        -> atomic marker
#
# IT NEVER TOUCHES A PROVIDER. There is no network client, no credential read,
# and no option/price/attention lookup anywhere in this module or its imports.
# An option benchmark is either handed in already-verified by the operator, or
# explicitly declared unavailable. This module will not fetch one.
#
# VALIDATE-THEN-WRITE. The entire prospective write set is computed and checked
# before the first persistent byte. Any failure raises PreEventCaptureError and
# leaves zero artifacts; a partially-written capture can never present itself as
# success.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .completeness import (
    PROTOCOL_VERSION,
    ModuleEligibility,
    OptionBenchmarkDisposition,
    OptionDispositionError,
    evaluate_pre_event_modules,
)
from .completion_marker import write_completion_marker
from .constants import SIX_FIELD_CONTRACT, is_locked_universe_member
from .event_record import EventStore
from .operations_plan import OperationsPlanError, build_operations_plan
from .phase2_adapter import Phase2AdapterError, import_pre_event_fields_for_ticker

ORCHESTRATOR_VERSION = "0.1"


class PreEventCaptureError(ValueError):
    """Fail-closed. Nothing was written."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ValidationReport:
    """Everything checked before any write. Serialisable, credential-free."""

    event_id: str
    ticker: str
    expected_anchor_session: str
    derived_anchor_session: str
    panel_csv: str
    panel_csv_sha256: str
    panel_marker: str
    panel_marker_sha256: str
    panel_status: str
    panel_run_date: Optional[str]
    option_benchmark_status: str
    checks: list[dict] = field(default_factory=list)
    eligibility: Optional[dict] = None
    planned_writes: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": bool(passed), "detail": detail})

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["all_checks_passed"] = self.ok()
        d["orchestrator_version"] = ORCHESTRATOR_VERSION
        d["protocol_version"] = PROTOCOL_VERSION
        return d


def _panel_run_date(csv_path: Path) -> Optional[str]:
    """The panel's own data date, taken from its retrieval timestamps. Read-only."""
    import csv as _csv

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rows = list(_csv.DictReader(f))
    stamps = {(r.get("retrieval_timestamp_utc") or "")[:10] for r in rows if r.get("retrieval_timestamp_utc")}
    stamps.discard("")
    if len(stamps) != 1:
        return None
    return sorted(stamps)[0]


def validate_pre_event_capture(
    *,
    registry_path: Path,
    event_id: str,
    company_name: str,
    expected_anchor_session: str,
    panel_csv: Path,
    panel_marker: Path,
    store_root: Path,
    research_commit_sha: str,
    methodology_version: str,
    option_benchmark_fields: dict[str, Any],
    now_utc: datetime,
) -> ValidationReport:
    """Run every check. Writes nothing, ever."""
    registry_path, panel_csv, panel_marker = Path(registry_path), Path(panel_csv), Path(panel_marker)
    store_root = Path(store_root)

    # --- registry + mechanically derived anchor (production implementations) --
    try:
        plan = build_operations_plan(
            registry_path=registry_path, event_id=event_id, company_name=company_name,
            generated_at_utc=now_utc, planning_commit=research_commit_sha,
            methodology_version=methodology_version,
        )
    except OperationsPlanError as exc:
        raise PreEventCaptureError(f"registry/calendar validation failed: {exc}") from exc

    ticker = plan["event"]["ticker"]
    derived_anchor = plan["sessions"]["pre_event_anchor"]["session_date"]

    for p in (panel_csv, panel_marker):
        if not p.is_file():
            raise PreEventCaptureError(f"required input not found: {p}")

    rep = ValidationReport(
        event_id=event_id, ticker=ticker,
        expected_anchor_session=expected_anchor_session, derived_anchor_session=derived_anchor,
        panel_csv=panel_csv.as_posix(), panel_csv_sha256=_sha256_file(panel_csv),
        panel_marker=panel_marker.as_posix(), panel_marker_sha256=_sha256_file(panel_marker),
        panel_status="(unread)", panel_run_date=None,
        option_benchmark_status="(unvalidated)",
    )

    rep.add("registry_row_verified", True, f"row {plan['registry_provenance']['source_registration_row_id']}")
    rep.add("anchor_session_derived_mechanically", True, f"XNYS -> {derived_anchor}")
    rep.add("expected_anchor_equals_derived", expected_anchor_session == derived_anchor,
            f"expected={expected_anchor_session} derived={derived_anchor}")
    rep.add("ticker_in_locked_universe", is_locked_universe_member(ticker), ticker)

    # --- panel identity, freshness and cross-consistency ---------------------
    run_date = _panel_run_date(panel_csv)
    rep.panel_run_date = run_date
    rep.add("panel_run_date_resolvable", run_date is not None,
            "a single retrieval date across all rows is required")
    if run_date is not None:
        rep.add("panel_is_anchor_session", run_date == derived_anchor,
                f"panel run date {run_date} vs anchor {derived_anchor}")
        rep.add("panel_not_stale", not (run_date < derived_anchor), f"run date {run_date}")
        rep.add("panel_not_future", not (run_date > derived_anchor), f"run date {run_date}")

    # phase2_adapter re-hashes both files, cross-verifies the marker's own counts
    # against the CSV, and refuses on any disagreement.
    try:
        adapted = import_pre_event_fields_for_ticker(
            csv_path=panel_csv, marker_path=panel_marker, ticker=ticker,
            research_commit_sha=research_commit_sha, methodology_version=methodology_version,
        )
    except Phase2AdapterError as exc:
        raise PreEventCaptureError(f"panel/marker validation failed: {exc}") from exc

    rep.panel_status = adapted.panel_status
    rep.add("panel_marker_cross_verified", True, "row/ticker/clean counts agree with the CSV")
    rep.add("panel_csv_hash_matches_adapter", adapted.source_csv_sha256 == rep.panel_csv_sha256)
    rep.add("panel_marker_hash_matches_adapter", adapted.source_marker_sha256 == rep.panel_marker_sha256)
    rep.add("panel_status_complete", adapted.panel_status == "COMPLETE",
            f"panel_status={adapted.panel_status}")
    rep.add("retrieval_timestamp_present", adapted.pre_event_snapshot_asof_utc is not None)

    # exactly one row for this ticker
    import csv as _csv
    with open(panel_csv, "r", encoding="utf-8", newline="") as f:
        rows = [r for r in _csv.DictReader(f) if (r.get("ticker") or "").strip() == ticker]
    rep.add("exactly_one_row_for_ticker", len(rows) == 1, f"{len(rows)} row(s) for {ticker}")

    # Six-field contract: a missing value must be null, never 0.
    zero_as_missing = []
    if rows:
        for fname in SIX_FIELD_CONTRACT:
            raw = (rows[0].get(fname) or "").strip()
            status_key = {"gst_zscore": "gst_status", "wiki_zscore": "wiki_status"}.get(fname)
            if status_key and (rows[0].get(status_key) or "").strip() not in ("", "ok",
                                                                             "complete_recent_cache_fallback"):
                if raw in ("0", "0.0", "0.00"):
                    zero_as_missing.append(fname)
    rep.add("no_missing_six_field_value_encoded_as_zero", not zero_as_missing, str(zero_as_missing))

    rep.add("source_statuses_present", all(s is not None for s in (
        adapted.source_status_gst, adapted.source_status_wiki, adapted.source_status_price)))

    # --- option module: explicit disposition, never inferred -----------------
    try:
        eligibility = evaluate_pre_event_modules(adapted.to_pre_event_fields(), option_benchmark_fields)
    except OptionDispositionError as exc:
        raise PreEventCaptureError(f"option benchmark rejected: {exc}") from exc
    rep.option_benchmark_status = eligibility.option_benchmark_status
    rep.eligibility = eligibility.as_dict()
    rep.add("option_disposition_explicit", True, eligibility.option_benchmark_status)
    rep.add("core_pre_event_eligible", eligibility.core_pre_event_eligible,
            "existing core gate")

    # --- collision safety: nothing may already exist --------------------------
    # Path shapes come from the production implementations, not invented here:
    # EventStore._log_path -> "{event_id}.jsonl";
    # write_completion_marker -> "{event_id}_COMPLETION_MARKER.json".
    log_path = store_root / f"{event_id}.jsonl"
    marker_path = store_root / f"{event_id}_COMPLETION_MARKER.json"
    rep.planned_writes = [log_path.as_posix(), marker_path.as_posix()]
    existing_states = []
    if store_root.exists():
        store = EventStore(store_root)
        existing_states = [r for r in store.read_all(event_id) if r["record_type"] == "STATE"]
    rep.add("no_existing_pre_event_stage",
            not any(r["state"] in ("PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED") for r in existing_states),
            f"{len(existing_states)} existing state record(s)")
    rep.add("no_existing_completion_marker", not marker_path.exists(), marker_path.as_posix())
    return rep


def execute_pre_event_capture(
    *, report: ValidationReport, store_root: Path, panel_csv: Path, panel_marker: Path,
    ticker: str, research_commit_sha: str, methodology_version: str,
    option_benchmark_fields: dict[str, Any],
) -> dict:
    """Persist ONLY after a fully passing validation report. Append-only."""
    if not report.ok():
        failed = [c["check"] for c in report.checks if not c["passed"]]
        raise PreEventCaptureError(f"refusing to execute; failed checks: {failed}")

    store_root = Path(store_root)
    store_root.mkdir(parents=True, exist_ok=True)
    store = EventStore(store_root)

    existing = [r for r in store.read_all(report.event_id) if r["record_type"] == "STATE"]
    if any(r["state"] in ("PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED") for r in existing):
        raise PreEventCaptureError("pre-event stage already recorded; refusing to write again")
    marker_path = store_root / f"{report.event_id}_COMPLETION_MARKER.json"
    if marker_path.exists():
        raise PreEventCaptureError(f"completion marker already exists: {marker_path}")

    adapted = import_pre_event_fields_for_ticker(
        csv_path=Path(panel_csv), marker_path=Path(panel_marker), ticker=ticker,
        research_commit_sha=research_commit_sha, methodology_version=methodology_version,
    )
    if not existing:
        store.append_state(report.event_id, "REGISTERED", {"ticker": ticker})

    from .pipeline import capture_pre_event_and_option_benchmark

    state = capture_pre_event_and_option_benchmark(
        store, report.event_id, adapted.to_pre_event_fields(), option_benchmark_fields
    )
    marker = write_completion_marker(store_root, report.event_id, store)
    return {"state": state, "marker": marker,
            "event_log": (store_root / f"{report.event_id}.jsonl").as_posix()}


__all__ = [
    "ORCHESTRATOR_VERSION", "PreEventCaptureError", "ValidationReport",
    "execute_pre_event_capture", "validate_pre_event_capture",
]
