# Offline plan-only CLI for the operations planner.
#
# STRUCTURALLY INCAPABLE OF COLLECTING RESEARCH DATA.
#
# This module imports exactly one project module (operations_plan) plus stdlib.
# It does not import — directly or transitively — any provider, the EventStore,
# the pipeline, or the Phase 2 panel, so there is no code path from this entry
# point to a network call or to a research-state write. A deterministic test
# asserts that running it leaves every provider module out of sys.modules.
#
# The only subcommand is `plan`, and the only thing it writes is a plan JSON at
# an explicitly supplied path. It refuses to overwrite an existing plan.
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .operations_plan import OperationsPlanError, build_operations_plan, finalize_plan

EXIT_OK = 0
EXIT_PLAN_REFUSED = 1
EXIT_OUTPUT_COLLISION = 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="operations_cli",
        description=(
            "Offline, network-free operations planner. Plans only; never collects data, "
            "never transitions event state, never modifies the registry."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="derive the mechanical capture schedule for one registered event")
    plan.add_argument("--registry", required=True, type=Path, help="explicit path to registry.jsonl")
    plan.add_argument("--event-id", required=True)
    plan.add_argument("--company-name", required=True)
    plan.add_argument("--planning-commit", required=True)
    plan.add_argument("--methodology-version", required=True, default=None)
    plan.add_argument("--out", type=Path, default=None, help="write the plan JSON here; refuses to overwrite")
    plan.add_argument(
        "--generated-at-utc",
        default=None,
        help="ISO-8601 UTC timestamp to stamp the plan with; omit to use the current time",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "plan":  # pragma: no cover - argparse enforces
        return EXIT_PLAN_REFUSED

    if args.generated_at_utc:
        generated = datetime.fromisoformat(args.generated_at_utc.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            print("--generated-at-utc must be timezone-aware", file=sys.stderr)
            return EXIT_PLAN_REFUSED
    else:
        generated = datetime.now(timezone.utc)

    # Collision check BEFORE any work, so a refused run does nothing at all.
    if args.out is not None and Path(args.out).exists():
        print(f"refusing to overwrite existing plan at {args.out}", file=sys.stderr)
        return EXIT_OUTPUT_COLLISION

    try:
        plan = build_operations_plan(
            registry_path=args.registry,
            event_id=args.event_id,
            company_name=args.company_name,
            generated_at_utc=generated,
            planning_commit=args.planning_commit,
            methodology_version=args.methodology_version,
        )
    except OperationsPlanError as exc:
        print(f"PLAN REFUSED (fail-closed): {exc}", file=sys.stderr)
        return EXIT_PLAN_REFUSED

    final = finalize_plan(plan)
    text = json.dumps(final, indent=2, ensure_ascii=False) + "\n"

    if args.out is None:
        print(text)
        return EXIT_OK

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():  # re-check: another process may have created it meanwhile
        print(f"refusing to overwrite existing plan at {out}", file=sys.stderr)
        return EXIT_OUTPUT_COLLISION
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote plan: {out.as_posix()}")
    print(f"plan_content_sha256: {final['integrity']['plan_content_sha256']}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
