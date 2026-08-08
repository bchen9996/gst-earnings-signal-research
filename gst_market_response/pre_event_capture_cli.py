# CLI for the pre-event capture orchestrator.
#
# DEFAULT IS READ-ONLY VALIDATION. Persistent writes require an explicit
# --execute. There is deliberately no --force, --override, --ignore,
# --allow-stale, --skip-validation and no --overwrite: every failure mode this
# tool detects is one an operator must fix at the source, not wave through.
#
# The option benchmark is never fetched here. It is either supplied as an
# already-verified artifact (--option-benchmark-json) or explicitly declared
# unavailable (--option-status + --option-reason). Unavailability is never
# inferred from omission.
#
# Exit codes:
#   0  validation passed, or capture succeeded
#   1  validation failed (stale/future/wrong anchor, hash or identity mismatch,
#      missing required core field, bad option artifact, collision, state error)
#   2  usage error
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .completeness import OptionBenchmarkDisposition
from .pre_event_capture import (
    PreEventCaptureError,
    execute_pre_event_capture,
    validate_pre_event_capture,
)

EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE = 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pre_event_capture_cli",
        description="Validate (default) or execute a pre-event capture. Never contacts a provider.",
    )
    p.add_argument("--event-id", required=True)
    p.add_argument("--expected-anchor-session", required=True,
                   help="must equal the anchor the registry+XNYS calendar derive")
    p.add_argument("--panel-csv", required=True, type=Path)
    p.add_argument("--panel-marker", required=True, type=Path)
    p.add_argument("--store-root", required=True, type=Path)
    p.add_argument("--research-commit-sha", required=True)
    p.add_argument("--methodology-version", required=True)
    p.add_argument("--registry", required=True, type=Path)
    p.add_argument("--company-name", required=True)
    p.add_argument("--option-benchmark-json", type=Path, default=None,
                   help="path to an ALREADY-VERIFIED option benchmark artifact")
    p.add_argument("--option-status", default=None, choices=list(OptionBenchmarkDisposition.ALL),
                   help="explicit disposition when no verified artifact is supplied")
    p.add_argument("--option-reason", default=None,
                   help="required with a non-VALID_VERIFIED --option-status")
    p.add_argument("--execute", action="store_true",
                   help="perform persistent writes; omit for read-only validation")
    p.add_argument("--json", action="store_true", help="emit the report as JSON")
    return p


def _resolve_option_fields(args) -> dict:
    if args.option_benchmark_json is not None:
        if args.option_status is not None:
            raise SystemExit(EXIT_USAGE)
        data = json.loads(Path(args.option_benchmark_json).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit(EXIT_USAGE)
        return data
    if args.option_status is None:
        print("ERROR: supply either --option-benchmark-json or an explicit --option-status; "
              "option unavailability is never inferred from omission", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    fields = {"option_benchmark_status": args.option_status}
    if args.option_status != OptionBenchmarkDisposition.VALID_VERIFIED:
        fields["option_benchmark_unavailable_reason"] = args.option_reason
        for k in ("expiration", "underlying_price", "quote_timestamp_utc",
                  "straddle_mid", "long_executable_implied_move_cost"):
            fields[k] = None
    return fields


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    option_fields = _resolve_option_fields(args)

    try:
        report = validate_pre_event_capture(
            registry_path=args.registry, event_id=args.event_id, company_name=args.company_name,
            expected_anchor_session=args.expected_anchor_session,
            panel_csv=args.panel_csv, panel_marker=args.panel_marker, store_root=args.store_root,
            research_commit_sha=args.research_commit_sha,
            methodology_version=args.methodology_version,
            option_benchmark_fields=option_fields,
            now_utc=datetime.now(timezone.utc),
        )
    except PreEventCaptureError as exc:
        print(f"VALIDATION FAILED (fail-closed, nothing written): {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"event      : {report.event_id} ({report.ticker})")
        print(f"anchor     : expected={report.expected_anchor_session} derived={report.derived_anchor_session}")
        print(f"panel      : {report.panel_status}  run_date={report.panel_run_date}")
        print(f"option     : {report.option_benchmark_status}")
        for c in report.checks:
            print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}  {c['detail']}")
        if report.eligibility:
            e = report.eligibility
            print(f"eligibility: core={e['core_pre_event_eligible']} option={e['option_benchmark_eligible']} "
                  f"joint={e['joint_full_eligible']} tier={e['pre_event_completeness_tier']}")

    if not report.ok():
        print("VALIDATION FAILED -- nothing written", file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    if not args.execute:
        print("VALIDATION ONLY -- no writes performed (pass --execute to capture)")
        return EXIT_OK

    try:
        result = execute_pre_event_capture(
            report=report, store_root=args.store_root, panel_csv=args.panel_csv,
            panel_marker=args.panel_marker, ticker=report.ticker,
            research_commit_sha=args.research_commit_sha,
            methodology_version=args.methodology_version,
            option_benchmark_fields=option_fields,
        )
    except PreEventCaptureError as exc:
        print(f"CAPTURE FAILED: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    print(f"CAPTURED state={result['state']}")
    print(f"  event log : {result['event_log']}")
    print(f"  full-data complete: {result['marker']['is_full_data_complete']}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
