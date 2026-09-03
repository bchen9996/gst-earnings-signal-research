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
    resolution_survivorship,
    rule_description,
    shocks_from_rows,
    union_events,
    union_incremental,
    write_worklist_csv,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-02"

#: _v2 (2026-08-31). The v1 pair stays byte-identical on disk -- superseded,
#: not rewritten -- and SUPERSEDES/SUPERSEDES_SHA256 below record what changed.
#: Two defects in v1, both found by reading its own output:
#:   1. The normaliser stripped "Holding", resolving ADBE's 2006 "Ingram Micro"
#:      onto INGM (Ingram Micro Holding Corp, CIK 1897762), a different
#:      registrant. Fixed in peer_ceiling.NAME_SUFFIXES; that row is now
#:      correctly UNRESOLVED.
#:   2. Candidate counts were GROSS. Two resolved rows were MCK -> CVS at as_of
#:      dates later than the curated edge, so their events are a strict subset
#:      of what the map already reaches and they add nothing. v1's union of 231
#:      was neither the incremental figure nor the reachable total.
#: _v3 adds `resolution_survivorship`: names are resolved against SEC's list of
#: CURRENT filers, so the method can only ever return survivors. The worklist
#: rows are unchanged from _v2.
#: 2026-09-02 is a NEW DATE, not a same-day revision, so it carries no _vN and
#: supersedes the whole 2026-08-31 series. What changed is the input, not the
#: method: the owner curated the five draft rows into HYP04_Linkage_Map_v1.1,
#: and every number below is the same measurement over a larger map.
#: _v2 is a SAME-DAY revision: the 2026-09-02 pair was built against the
#: 2026-08-29 walk, and the corrected walk landed the same day. The originals
#: stay byte-identical on disk and are recorded below with their hashes.
OUT_JSON = LSE / f"HYP04_PEER_CEILING_{AS_OF}_v2.json"
OUT_CSV = LSE / f"HYP04_PEER_CURATION_WORKLIST_{AS_OF}_v2.csv"
SUPERSEDES = (LSE / f"HYP04_PEER_CEILING_{AS_OF}.json",
              LSE / f"HYP04_PEER_CURATION_WORKLIST_{AS_OF}.csv")

#: PINNED BY NAME, deliberately, and it sits next to AS_OF so the two go stale
#: together and visibly. A `newest_in` glob here would let the map in force
#: change under a dated artifact without the date moving, which is the drift
#: this convention exists to prevent. Bump both when a new map is curated.
CURATED_MAP = LSE / "HYP04_Linkage_Map_v1.1.csv"
MINIMUM_ELIGIBLE_EVENTS = 193

#: SEC's fair-access User-Agent. Required even offline, because the client
#: refuses to exist without one rather than letting an unattributed client be
#: constructed and later used live by accident.
CONTACT = "bchen9996 bchen9996@gmail.com"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _newest(paths: list[Path]) -> Path:
    # Version-aware; a lexical sort picks _v3 over _v10. See artifacts.py.
    from .artifacts import newest
    return newest(paths)


def _rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))


def _newest_of(pattern: str) -> Optional[Path]:
    from .artifacts import newest_in
    return newest_in(LSE, pattern)


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
                          anchors=anchors,
                          already_reachable=report.ceiling_event_ids)

    day = today or date.today()
    resolved = [r for r in rows if r.resolution.resolved]
    all_union = union_events(rows)
    res_union = union_events(resolved)
    all_inc = union_incremental(rows)
    res_inc = union_incremental(resolved)
    curated_reach = set(report.ceiling_event_ids)
    dominated = [r for r in rows if r.dominated]

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
        "resolution_survivorship": resolution_survivorship(rows),
        # DERIVED, not asserted. Through 2026-08-31 this read "Curation, not
        # prices" as a hardcoded string, and it was true: the ceiling was 54
        # against a floor of 193. Curating v1.1 took the ceiling to 215 and
        # made that sentence false while the artifact went on stating it. The
        # dashboard READS this field rather than recomputing, so a stale claim
        # here is published, not merely stored. Which constraint binds is a
        # measurement; it is now measured.
        "the_binding_constraint": (
            (
                "Curation, not prices. The curated map caps the sample at "
                f"{report.ceiling_events} anchor events against a floor of "
                f"{MINIMUM_ELIGIBLE_EVENTS}. A survivorship-bias-free price "
                "source bought tomorrow would not raise that by one event, "
                "because the ceiling run already assumes prices exist."
            ) if not report.reaches_floor else (
                "Prices, not curation -- REVERSED from every prior version of "
                "this artifact. The curated map now reaches "
                f"{report.ceiling_events} anchor events against a floor of "
                f"{MINIMUM_ELIGIBLE_EVENTS}, so curation no longer caps the "
                "sample below the floor. That ceiling ASSUMES peer prices "
                "exist. None do: the measured join yields "
                f"{report.measured_pairs} eligible pairs and "
                f"{report.measured_events} anchor events with a peer. A peer "
                "price source is now the binding constraint, and no such "
                "source is registered."
            )),
        "worklist": {
            "artifact": out_csv.name,
            "candidates_on_anchor_tickers": len(rows),
            "ticker_resolved": len(resolved),
            "unresolved": len(rows) - len(resolved),
            "dominated_by_curated_map": len(dominated),
            "union_all_candidates": len(all_union),
            "union_ticker_resolved_only": len(res_union),
            # The numbers a curator acts on. GROSS unions double-count what the
            # curated map already reaches; v1 published only those.
            "incremental_all_candidates": len(all_inc),
            "incremental_ticker_resolved_only": len(res_inc),
            "total_reachable_if_resolved_curated": len(res_inc | curated_reach),
            "total_reachable_if_all_curated": len(all_inc | curated_reach),
            "registered_floor": MINIMUM_ELIGIBLE_EVENTS,
            "why_incremental_matters": (
                "A candidate duplicating an existing edge at a LATER as_of "
                "date has a large gross count and buys nothing. Two resolved "
                "rows are exactly that, both MCK -> CVS behind the curated "
                "2013-05-07 edge, and they are flagged "
                "dominated_by_curated_map."),
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
        "supersedes": [q.name for q in SUPERSEDES],
        "supersedes_sha256": {q.name: (_sha256(q) if q.is_file() else None)
                              for q in SUPERSEDES},
        "what_changed_from_2026_09_02": [
            "The review queue is rebuilt from a corrected EDGAR walk. Both "
            "walk entry points filtered on form == '10-K' exactly, which "
            "excluded 10-K405 (a valid annual report 1996-2003) and 10-KT "
            "entirely: 56 annual reports across 25 tickers had never been "
            "examined. They have been, and the walk now reads 1306 filings "
            "instead of 1250, with zero retrieval failures.",
            "The correction moved NO curated as_of_date. NVDA's three "
            "newly-visible 10-K405s (1999-04-29, 2000, 2001-04-27) do not "
            "name Microsoft, so NVDA->MSFT's as_of of 2004-03-29 is now a "
            "PROVEN floor across a complete annual-report series rather than "
            "the earliest of an incomplete one. The same holds for "
            "JBL->CSCO at 2002-11-25 after JBL's 1999 10-K405 was read.",
            "One counterparty name is newly visible across the whole "
            "expansion: NVDA / Celestica, earliest 2001-04-27, from a 10-K405 "
            "the old filter could not see.",
            "XOM now carries a stated refusal instead of a zero. It resolves "
            "through company_tickers.json to CIK 2115436 'ExxonMobil Holdings "
            "Corp', a post-reorganisation registrant with no filing history, "
            "and the previous walk recorded that as filings_on_record 0 with "
            "no error -- indistinguishable from a filer that disclosed "
            "nothing. It is excluded from counts rather than counted as zero.",
            "The ceiling itself is UNCHANGED at 215. It is a function of the "
            "curated map, the calendar and the shocks, none of which moved; "
            "the walk feeds the candidate worklist, not the curated reach.",
        ],
        "what_changed_from_2026_08_31_v3": [
            "The curated map moved from HYP04_Linkage_Map_v1.0.csv (2 edges) "
            "to v1.1 (7 edges). The owner curated the five machine-prepared "
            "draft rows -- JBL->CSCO, JBL->AAPL, JBL->BB, NVDA->MSFT, "
            "INTC->HPQ -- supplying the five fields no derivation can "
            "supply. v1.1 is the UNION: v1.0's two rows are carried through "
            "unchanged, because this artifact's reader takes the newest map "
            "and a v1.1 holding only the new rows would have dropped them.",
            "The method is unchanged. Same calendar, same shocks, same review "
            "queue, same rule. Every difference below follows from the map.",
            "the_binding_constraint is now DERIVED from whether the ceiling "
            "reaches the floor, instead of being a hardcoded string. It has "
            "reversed: through v3 curation bound at a ceiling of 54; it now "
            "reads 215 against a floor of 193, and prices bind.",
            "A ceiling above the floor is still not an eligible event. The "
            "measured join yields zero eligible pairs, the display gate is "
            "CLOSED with four denials, and C2 counts eligible events only.",
        ],
        "what_changed_from_v2": [
            "Adds resolution_survivorship. Names are resolved against SEC's "
            "company_tickers.json, which lists companies that file and trade "
            "TODAY, so a delisted, merged-away, taken-private or "
            "never-US-listed counterparty cannot resolve BY CONSTRUCTION. The "
            "resolved set is therefore a survivorship-biased sample of the "
            "queue. Measured, because peer_price_data_policy permits a "
            "survivors-only restriction only if its bias is stated, and a "
            "statement of bias needs a number.",
            "Worklist rows are unchanged from _v2.",
        ],
        "what_changed_from_v1": [
            "The name normaliser no longer strips HOLDING/HOLDINGS/GROUP. "
            "They are not legal forms: they separate a holding company from "
            "its operating company and a successor vehicle from its "
            "predecessor. v1 resolved ADBE's 2006 disclosure of 'Ingram "
            "Micro' onto INGM (Ingram Micro Holding Corp, CIK 1897762), the "
            "2024 re-IPO vehicle. That row is now UNRESOLVED, which is "
            "correct, and the resolved count falls by one.",
            "Candidate counts are now reported INCREMENTAL to the curated "
            "map as well as gross, and rows the map already covers are "
            "flagged dominated_by_curated_map. v1's headline union of 231 "
            "counted events the curated edge already reaches.",
            "Rows are ranked by incremental opportunity rather than gross.",
        ],
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
