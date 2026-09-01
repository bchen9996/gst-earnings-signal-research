#!/usr/bin/env python3
"""Measure the peer side's reach, and rank what would extend it. OFFLINE.

Writes two dated artifacts:

    HYP04_PEER_CEILING_<date>.json          the measured join and the ceiling
    HYP04_PEER_CURATION_WORKLIST_<date>.csv the review queue, ranked

Nothing here reaches an endpoint. The SEC ticker map is served from the EDGAR
cache with `offline=True`, so a cache miss REFUSES rather than fetching -- the
same guard `earnings_events` needed after `_get` was found bypassing it, and the
run asserts `requests_made == 0` before writing.

=== WHY BOTH ARTIFACTS ARE ONE RUN ===

Because the ceiling is the reason the worklist is ranked the way it is. Split
apart, the worklist becomes a list of companies with no statement of what it is
for, and the ceiling becomes a number with no statement of what would move it.

  python -m hyp04_supply_chain_hedge.make_peer_ceiling --build
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .curated_linkage import load_curated_linkage
from .peer_ceiling import (
    PEER_CEILING_RULE_ID,
    WORKLIST_FIELDS,
    build_name_index,
    build_worklist,
    events_from_calendar,
    measure_ceiling,
    rule_description,
    shocks_from_rows,
    union_events,
    write_worklist_csv,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-08-31"

OUT_JSON = LSE / f"HYP04_PEER_CEILING_{AS_OF}.json"
OUT_CSV = LSE / f"HYP04_PEER_CURATION_WORKLIST_{AS_OF}.csv"

CURATED_MAP = LSE / "HYP04_Linkage_Map_v1.0.csv"
MINIMUM_ELIGIBLE_EVENTS = 193

#: SEC's fair-access User-Agent. Required even offline, because the client
#: refuses to exist without one rather than letting an unattributed client be
#: constructed and later used live by accident.
CONTACT = "bchen9996 bchen9996@gmail.com"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _newest(paths: list[Path]) -> Path:
    return sorted(paths, key=lambda p: p.name)[-1]


def _rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))


def _newest_of(pattern: str) -> Optional[Path]:
    hits = list(LSE.glob(pattern))
    return _newest(hits) if hits else None


def build(*, out_json: Path = OUT_JSON, out_csv: Path = OUT_CSV,
          map_path: Path = CURATED_MAP, today: Optional[date] = None,
          ) -> list[str]:
    refusals: list[str] = []
    for p in (out_json, out_csv):
        if p.exists():
            refusals.append(
                f"{p.name} already exists. Refusing to overwrite a dated "
                "artifact -- delete it deliberately first.")

    cal_p = _newest_of("HYP04_ANCHOR_EVENT_CALENDAR_*.csv")
    shk_p = _newest_of("HYP04_ANCHOR_SHOCKS_*.csv")
    queue_p = _newest_of("HYP04_EDGAR_LINKAGE_HISTORY_FULL51_*.json")
    if cal_p is None:
        refusals.append("no anchor-event calendar artifact on disk")
    if shk_p is None:
        refusals.append("no anchor-shock artifact on disk")
    if queue_p is None:
        refusals.append("no EDGAR linkage-history review queue on disk")
    if not map_path.is_file():
        refusals.append(f"no curated linkage map at {map_path}")
    if refusals:
        return refusals

    cal_rows = _rows(cal_p)
    shk_rows = _rows(shk_p)
    queue = json.loads(queue_p.read_text(encoding="utf-8"))

    # The queue is a REVIEW QUEUE and must say so. Reading a promoted map from
    # this slot would silently turn candidates into curated edges.
    if queue.get("is_production_linkage_map") is not False:
        return [f"{queue_p.name} does not declare "
                "is_production_linkage_map=false; refusing to treat it as a "
                "review queue"]

    # The calendar and the shocks must describe the same events, or every
    # count below is drawn from two different samples.
    cal_ids = [r["event_id"] for r in cal_rows]
    shk_ids = [r["event_id"] for r in shk_rows]
    if sorted(cal_ids) != sorted(shk_ids):
        return [f"{cal_p.name} and {shk_p.name} disagree on which events "
                f"exist ({len(cal_ids)} vs {len(shk_ids)})"]

    from .edgar_linkage import EdgarClient, FilingCache, TICKER_MAP_URL
    client = EdgarClient(CONTACT, cache=FilingCache(Path(".edgar_cache")),
                         offline=True)
    ticker_map = client._get_json(TICKER_MAP_URL)
    if client.requests_made:
        return [f"the SEC ticker map cost {client.requests_made} request(s); "
                "this runner is offline and must serve it from cache"]

    shocks = shocks_from_rows(shk_rows)
    events = events_from_calendar(cal_rows)
    loaded = load_curated_linkage(map_path)
    peers = [e.peer_ticker for e in loaded.edges]

    report = measure_ceiling(events, shocks, map_path=map_path,
                             curated_peers=peers,
                             floor=MINIMUM_ELIGIBLE_EVENTS)

    anchors = sorted({r["anchor_ticker"] for r in cal_rows})
    rows = build_worklist(queue.get("tickers") or [],
                          calendar_rows=cal_rows, shock_rows=shk_rows,
                          name_index=build_name_index(ticker_map),
                          anchors=anchors)

    day = today or date.today()
    resolved = [r for r in rows if r.resolution.resolved]
    all_union = union_events(rows)
    res_union = union_events(resolved)

    payload: dict[str, Any] = {
        "artifact": out_json.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "rule": rule_description(),
        "what_this_is": (
            "How far the peer side can reach with the linkage that exists "
            "today, and which unreviewed candidates would extend it. A "
            "feasibility measurement of the SAMPLE, not of the hypothesis."),
        "what_this_is_not": (
            "Evidence about supply-chain transmission. No peer return has "
            "been measured, no pair is eligible, and the display gate is "
            "CLOSED with the eligible-event count at zero."),
        "sources": {
            "calendar": cal_p.name,
            "calendar_sha256": _sha256(cal_p),
            "shocks": shk_p.name,
            "shocks_sha256": _sha256(shk_p),
            "review_queue": queue_p.name,
            "review_queue_sha256": _sha256(queue_p),
            "curated_map": map_path.name,
            "curated_map_sha256": _sha256(map_path),
            "sec_ticker_map": TICKER_MAP_URL,
            "sec_ticker_map_entries": len(ticker_map),
            "sec_ticker_map_served_from": "EDGAR cache, offline",
            "requests_made": client.requests_made,
        },
        "curated_map_load": {
            "rows_seen": loaded.rows_seen,
            "rows_rejected": loaded.rows_rejected,
            "edges_usable": len(loaded.edges),
        },
        "ceiling": report.as_dict(),
        "the_binding_constraint": (
            "Curation, not prices. The curated map caps the sample at "
            f"{report.ceiling_events} anchor events against a floor of "
            f"{MINIMUM_ELIGIBLE_EVENTS}. A survivorship-bias-free price source "
            "bought tomorrow would not raise that by one event, because the "
            "ceiling run already assumes prices exist."),
        "worklist": {
            "artifact": out_csv.name,
            "candidates_on_anchor_tickers": len(rows),
            "ticker_resolved": len(resolved),
            "unresolved": len(rows) - len(resolved),
            "union_all_candidates": len(all_union),
            "union_ticker_resolved_only": len(res_union),
            "registered_floor": MINIMUM_ELIGIBLE_EVENTS,
            "union_is_not_a_sum": (
                "Candidates on one anchor cover overlapping stretches of the "
                "same event list, so summing max_anchor_events would "
                "double-count heavily. The union is the only honest total."),
            "what_the_union_means": (
                "The queue CONTAINS enough material to reach the floor. It "
                "does not make any of it eligible: no candidate is curated, "
                "no as_of is ratified, every resolution needs lineage review, "
                "and no peer price source exists."),
        },
        "top_candidates": [
            r.as_row(today=day, floor=MINIMUM_ELIGIBLE_EVENTS)
            for r in rows[:12]
        ],
        "opens_no_gate": (
            "The display gate is CLOSED, C4 MET, four denials. C2 counts "
            "ELIGIBLE anchor events; this artifact supplies none, and C2 and "
            "C3 move together or not at all."),
    }

    n = write_worklist_csv(rows, out_csv, today=day,
                           floor=MINIMUM_ELIGIBLE_EVENTS)
    payload["worklist"]["rows_written"] = n
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return []


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Measure the HYP-04 peer-side ceiling and rank the "
                    "curation worklist. Offline; makes no network call.")
    ap.add_argument("--build", action="store_true",
                    help="write the dated artifacts")
    a = ap.parse_args(argv)
    if not a.build:
        ap.print_help()
        return 2
    refusals = build()
    if refusals:
        print("REFUSED:", file=sys.stderr)
        for r in refusals:
            print("  - " + r, file=sys.stderr)
        return 1
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
