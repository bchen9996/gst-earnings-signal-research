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
    METHODOLOGY_VERSION_V0_2,
    PROTOCOL_VERSION,
    ModuleEligibility,
    OptionBenchmarkDisposition,
    OptionDispositionError,
    evaluate_pre_event_modules,
    evaluate_strict_core_v0_2,
)
from .stage_markers import STAGE_PRE_EVENT, write_stage_marker
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
    panel_price_asof_date: Optional[str] = None
    methodology_version: str = ""
    research_commit_sha: str = ""
    provenance: Optional[dict] = None
    option_benchmark_status: str = "(unvalidated)"
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


def _panel_anchor_session(csv_path: Path) -> tuple[Optional[str], Optional[str], str]:
    """Return (price_asof_date, run_date, note) from the panel's AUTHORITATIVE
    columns.

    v0.1 of this orchestrator used `retrieval_timestamp_utc[:10]`. That was
    wrong. The panel writes two distinct authoritative columns and they DIFFER
    in practice: a real run has run_date=2026-07-30 with
    price_asof_date=2026-07-29, because the panel executes in the small hours
    UTC (04:40Z = 00:40 ET) AFTER the session it summarises. Truncating a UTC
    retrieval timestamp yields run_date, not the session -- so it would have
    bound the anchor to the wrong day and rejected a perfectly good panel.

    `price_asof_date` is the session the price data is as-of, and is therefore
    the field the pre-event anchor must equal. Anything ambiguous fails closed:
    a missing column, a blank value, or more than one distinct value across
    rows all return None and are reported as a failed check rather than
    guessed.
    """
    import csv as _csv

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rows = list(_csv.DictReader(f))
    if not rows:
        return None, None, "panel has no rows"
    if "price_asof_date" not in rows[0]:
        return None, None, ("panel has no authoritative price_asof_date column; refusing to "
                            "infer the session from a UTC retrieval timestamp")
    asof = {(r.get("price_asof_date") or "").strip() for r in rows}
    runs = {(r.get("run_date") or "").strip() for r in rows}
    asof.discard(""); runs.discard("")
    if len(asof) != 1:
        return None, None, f"price_asof_date is ambiguous across rows: {sorted(asof)}"
    run = sorted(runs)[0] if len(runs) == 1 else None
    return sorted(asof)[0], run, "authoritative price_asof_date"


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
        methodology_version=methodology_version, research_commit_sha=research_commit_sha,
        option_benchmark_status="(unvalidated)",
    )

    # v0.2 pins the methodology identifier exactly. Blank, arbitrary, stale and
    # v0.1 values are all refused; the accepted value is persisted downstream.
    rep.add("methodology_version_is_v0_2", methodology_version == METHODOLOGY_VERSION_V0_2,
            f"got {methodology_version!r}, require {METHODOLOGY_VERSION_V0_2!r}")
    rep.add("research_commit_sha_present", bool(str(research_commit_sha).strip()))

    rep.add("registry_row_verified", True, f"row {plan['registry_provenance']['source_registration_row_id']}")
    rep.add("anchor_session_derived_mechanically", True, f"XNYS -> {derived_anchor}")
    rep.add("expected_anchor_equals_derived", expected_anchor_session == derived_anchor,
            f"expected={expected_anchor_session} derived={derived_anchor}")
    rep.add("ticker_in_locked_universe", is_locked_universe_member(ticker), ticker)

    # --- panel identity, freshness and cross-consistency ---------------------
    asof, run_date, note = _panel_anchor_session(panel_csv)
    rep.panel_price_asof_date, rep.panel_run_date = asof, run_date
    rep.add("panel_session_resolvable_from_authoritative_column", asof is not None, note)
    if asof is not None:
        # The ANCHOR is bound to price_asof_date -- the session the price data is
        # as-of -- not to run_date and never to a truncated UTC timestamp.
        rep.add("panel_is_anchor_session", asof == derived_anchor,
                f"price_asof_date {asof} vs anchor {derived_anchor}")
        rep.add("panel_not_stale", not (asof < derived_anchor), f"price_asof_date {asof}")
        rep.add("panel_not_future", not (asof > derived_anchor), f"price_asof_date {asof}")
        if run_date is not None:
            # A panel legitimately RUNS after the session it summarises (often
            # after UTC midnight), so run_date >= price_asof_date. The reverse
            # would mean the panel summarised a session that had not happened.
            rep.add("run_date_not_before_session", run_date >= asof,
                    f"run_date={run_date} price_asof_date={asof}")

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

    # --- STRICT v0.2 six-field core -------------------------------------------
    core_fields = adapted.to_strict_core_fields()
    strict = evaluate_strict_core_v0_2(core_fields)
    rep.add("strict_core_v0_2_all_six_fields_present", not strict.missing_fields,
            f"missing={list(strict.missing_fields)}")
    rep.add("strict_core_v0_2_all_six_statuses_successful", not strict.bad_status_fields,
            f"non-success status for={list(strict.bad_status_fields)}")

    # --- full source provenance, persisted with the record ---------------------
    rep.provenance = {
        "ticker": adapted.ticker,
        "source_csv_path": adapted.source_csv_path,
        "source_csv_sha256": adapted.source_csv_sha256,
        "source_marker_path": adapted.source_marker_path,
        "source_marker_sha256": adapted.source_marker_sha256,
        "panel_status": adapted.panel_status,
        "panel_row_count": adapted.panel_row_count,
        "panel_unique_ticker_count": adapted.panel_unique_ticker_count,
        "panel_all_six_fields_clean_count": adapted.panel_all_six_fields_clean_count,
        "run_date": adapted.run_date,
        "price_asof_date": adapted.price_asof_date,
        "pre_event_snapshot_asof_utc": adapted.pre_event_snapshot_asof_utc,
        "research_commit_sha": adapted.research_commit_sha,
        "methodology_version": adapted.methodology_version,
        "adapter_schema_version": adapted.adapter_schema_version,
    }
    rep.add("provenance_complete", all(v is not None and v != "" for k, v in rep.provenance.items()),
            f"missing={[k for k, v in rep.provenance.items() if v is None or v == '']}")

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
    from .stage_markers import marker_path as _mp
    log_path = store_root / f"{event_id}.jsonl"
    marker_path = _mp(store_root, event_id, STAGE_PRE_EVENT)
    rep.planned_writes = [log_path.as_posix(), marker_path.as_posix()]
    existing_states = []
    if store_root.exists():
        store = EventStore(store_root)
        existing_states = [r for r in store.read_all(event_id) if r["record_type"] == "STATE"]
    rep.add("no_existing_pre_event_stage",
            not any(r["state"] in ("PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED") for r in existing_states),
            f"{len(existing_states)} existing state record(s)")
    rep.add("no_existing_pre_event_stage_marker", not marker_path.exists(), marker_path.as_posix())
    return rep


def execute_pre_event_capture(
    *, report: ValidationReport, store_root: Path, panel_csv: Path, panel_marker: Path,
    ticker: str, research_commit_sha: str, methodology_version: str,
    option_benchmark_fields: dict[str, Any],
) -> dict:
    """Persist ONLY after a fully passing validation report. Append-only.

    TOCTOU: validation approved files that remain mutable on disk. Before the
    first write this REHASHES both inputs and requires exact equality with the
    approved report, and re-checks the anchor, panel status, marker/CSV counts,
    methodology and commit SHA. Any drift fails with zero writes.
    """
    if not report.ok():
        failed = [c["check"] for c in report.checks if not c["passed"]]
        raise PreEventCaptureError(f"refusing to execute; failed checks: {failed}")

    panel_csv, panel_marker, store_root = Path(panel_csv), Path(panel_marker), Path(store_root)

    # --- re-verify identity of the approved inputs ---------------------------
    if methodology_version != report.methodology_version:
        raise PreEventCaptureError(
            f"methodology changed since validation: {report.methodology_version!r} -> {methodology_version!r}")
    if methodology_version != METHODOLOGY_VERSION_V0_2:
        raise PreEventCaptureError(
            f"methodology_version must be {METHODOLOGY_VERSION_V0_2!r}, got {methodology_version!r}")
    if research_commit_sha != report.research_commit_sha:
        raise PreEventCaptureError("research_commit_sha changed since validation")
    if ticker != report.ticker:
        raise PreEventCaptureError(f"ticker changed since validation: {report.ticker} -> {ticker}")
    for p_, approved, label in ((panel_csv, report.panel_csv_sha256, "panel CSV"),
                                (panel_marker, report.panel_marker_sha256, "panel marker")):
        if not p_.is_file():
            raise PreEventCaptureError(f"{label} disappeared between validation and execution: {p_}")
        now = _sha256_file(p_)
        if now != approved:
            raise PreEventCaptureError(
                f"{label} CHANGED between validation and execution "
                f"(approved {approved[:16]}..., now {now[:16]}...); refusing to write")

    # --- re-run the session/freshness and marker/CSV checks on the live files --
    asof, run_date, note = _panel_anchor_session(panel_csv)
    if asof is None:
        raise PreEventCaptureError(f"panel session no longer resolvable at execution: {note}")
    if asof != report.derived_anchor_session:
        raise PreEventCaptureError(
            f"panel session changed since validation: {asof} != anchor {report.derived_anchor_session}")

    adapted = import_pre_event_fields_for_ticker(
        csv_path=panel_csv, marker_path=panel_marker, ticker=ticker,
        research_commit_sha=research_commit_sha, methodology_version=methodology_version,
    )
    if adapted.panel_status != report.panel_status:
        raise PreEventCaptureError(
            f"panel status changed since validation: {report.panel_status} -> {adapted.panel_status}")
    if adapted.source_csv_sha256 != report.panel_csv_sha256 or        adapted.source_marker_sha256 != report.panel_marker_sha256:
        raise PreEventCaptureError("adapter re-hash disagrees with the approved report")

    strict = evaluate_strict_core_v0_2(adapted.to_strict_core_fields())
    if not strict.passed:
        raise PreEventCaptureError(
            f"strict v0.2 core no longer passes at execution: missing={list(strict.missing_fields)} "
            f"bad_status={list(strict.bad_status_fields)}")

    # --- collision checks against durable artifacts --------------------------
    store_root.mkdir(parents=True, exist_ok=True)
    store = EventStore(store_root)
    existing = [r for r in store.read_all(report.event_id) if r["record_type"] == "STATE"]
    if any(r["state"] in ("PRE_EVENT_PENDING", "PRE_EVENT_CAPTURED") for r in existing):
        raise PreEventCaptureError("pre-event stage already recorded; refusing to write again")
    from .stage_markers import marker_path as _mp
    if _mp(store_root, report.event_id, STAGE_PRE_EVENT).exists():
        raise PreEventCaptureError(
            f"immutable {STAGE_PRE_EVENT} marker already exists; refusing to overwrite evidence")

    # --- durable writes ------------------------------------------------------
    if not existing:
        store.append_state(report.event_id, "REGISTERED", {"ticker": ticker})

    from .pipeline import capture_pre_event_and_option_benchmark

    state = capture_pre_event_and_option_benchmark(
        store, report.event_id, adapted.to_strict_core_fields(), option_benchmark_fields
    )
    marker = write_stage_marker(store_root, report.event_id, STAGE_PRE_EVENT, store)
    return {"state": state, "marker": marker,
            "marker_path": _mp(store_root, report.event_id, STAGE_PRE_EVENT).as_posix(),
            "event_log": (store_root / f"{report.event_id}.jsonl").as_posix()}


__all__ = [
    "ORCHESTRATOR_VERSION", "PreEventCaptureError", "ValidationReport",
    "execute_pre_event_capture", "validate_pre_event_capture",
]
