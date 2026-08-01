#!/usr/bin/env python3
# WATERMARK-ONLY LIVE DIAGNOSTIC (2026-08-01). Exercises ONLY
# resolve_wiki_data_watermark() against the real, live SITE-WIDE aggregate
# Wikipedia pageviews endpoint -- no per-article requests, no ticker
# processing, no cache reads/writes, no panel run of any kind. This is the
# single live check authorized alongside the deterministic suites before
# committing the watermark implementation.
#
# Run directly: python diagnose_wiki_watermark_only.py
# Exit code reflects the watermark resolution's own status only:
#   0 -- status == "ok"
#   1 -- any other status ("no_data_within_max_lag" or "failed_closed")

from __future__ import annotations
from datetime import datetime, timezone
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import GST_Phase2_Wikipedia_Transport as wiki_transport

if __name__ == "__main__":
    anchor_date = datetime.now(timezone.utc).date()
    print(f"=== WATERMARK-ONLY LIVE DIAGNOSTIC -- anchor_date={anchor_date.isoformat()} ===")
    print(f"Endpoint: {wiki_transport.WIKI_AGGREGATE_API}")
    print(f"MAX_ACCEPTABLE_WIKI_LAG_DAYS={wiki_transport.MAX_ACCEPTABLE_WIKI_LAG_DAYS}\n")

    result = wiki_transport.resolve_wiki_data_watermark(anchor_date)

    print("--- probe log ---")
    for entry in result["probe_log"]:
        print(f"  candidate={entry['candidate']} lag={entry['lag_days']}d attempt={entry['attempt']!r} "
              f"status={entry['status']} http_status={entry['http_status']} "
              f"retry_after={entry['retry_after']} elapsed={entry['network_elapsed_s']}s url={entry['url']}")

    print("\n--- result ---")
    print(json.dumps({k: (v.isoformat() if hasattr(v, "isoformat") else v)
                       for k, v in result.items() if k != "probe_log"}, indent=2))

    if result["status"] == "ok":
        print(f"\nWatermark resolved: {result['watermark_date']} (lag={result['lag_days']}d). Exit 0.")
        sys.exit(0)
    else:
        print(f"\nWatermark NOT resolved (status={result['status']!r}). This is the correct, honest "
              f"fail-closed outcome if Wikipedia genuinely has no confirmed data within "
              f"{wiki_transport.MAX_ACCEPTABLE_WIKI_LAG_DAYS} days, or if an ambiguous error occurred. "
              f"Exit 1.")
        sys.exit(1)
