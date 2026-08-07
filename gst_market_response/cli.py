#!/usr/bin/env python3
# Entry point: checks a required-data completeness gate for a registered
# event and exits nonzero on failure. Does NOT perform any live capture --
# v0.1 has no live event registration (see SPEC "Explicitly out of scope").
# This CLI operates only on an already-written event record store.
#
# Usage: python -m gst_market_response.cli --store-root DIR --event-id ID --tier pre_event
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .completion_marker import EXIT_INCONCLUSIVE, check_required_gate, write_completion_marker
from .event_record import EventStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a market-response event's completeness gate.")
    parser.add_argument("--store-root", required=True, type=Path)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--tier", required=True, choices=["pre_event", "option_benchmark", "d1", "d3"])
    parser.add_argument("--write-marker", action="store_true")
    args = parser.parse_args(argv)

    store = EventStore(args.store_root)
    exit_code = check_required_gate(store, args.event_id, args.tier)

    if args.write_marker:
        write_completion_marker(args.store_root, args.event_id, store)

    if exit_code == EXIT_INCONCLUSIVE:
        print(f"INCONCLUSIVE: no recorded fields for event {args.event_id!r}", file=sys.stderr)
    elif exit_code != 0:
        print(f"GATE FAILED: {args.tier} gate did not pass for event {args.event_id!r}", file=sys.stderr)
    else:
        print(f"GATE OK: {args.tier} gate passed for event {args.event_id!r}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
