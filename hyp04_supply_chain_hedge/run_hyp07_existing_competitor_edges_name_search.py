#!/usr/bin/env python3
"""LIVE. Resolve the 56 competitor-direction counterparty NAMES already
sitting, unused, across three earlier HYP-05 extraction passes -- HYP-07's
Step 0, a free-to-cheap sanity check before any new discovery work.

=== WHY THIS EXISTS, AND WHY IT IS NOT run_hyp05_peer_name_search.py ===

`extract_competitor_edges_from_text()` (edgar_linkage.py) was already run,
calibrated, and wired into `extract_for_universe()` well before HYP-07 was
conceived. Its `direction: "competitor"` output already sits in three
committed HYP-05 artifacts (`HYP05_CANDIDATE_LINKAGE_REAL_ANCHORS_2026-09-12.
json`, `HYP05_CANDIDATE_LINKAGE_LOCKED24ANCHORS_2026-09-12.json`,
`HYP05_CANDIDATE_LINKAGE_HISTORICAL_WALK_2026-09-12.json`) -- 4 + 39 + 13 = 56
edges, never previously carried through name resolution as a single, combined
competitor-only set (HYP-05's own name-search runs covered each of these
files' FULL edge sets, customer/supplier and competitor together, for a
DIFFERENT purpose). `run_hyp05_peer_name_search.py` reads exactly ONE input
JSON; this module reads THREE and filters to `direction == "competitor"`
before merging -- a different input shape, not a parameter this project's
convention would bolt onto the existing script (see every other `run_hypNN_
*` module's own "new module, not a modification" precedent).

=== SAME RESOLUTION MECHANISM, REUSED UNCHANGED ===

`peer_name_search` (the company-search-then-lineage-test decision rule,
`MAX_CANDIDATES_PER_NAME`, `STATUS_*` verdicts) and `peer_lineage`
(`filer_history`/`assess`, the CONTINUOUS-lineage test) are imported and used
exactly as `run_hyp05_peer_name_search.py` already established. Nothing about
resolving a free-text name to a registrant depends on whether the edge came
from a customer-concentration or a competitor-prose extraction.

STAGED. Without --yes-run-live it prints the merged search list and exits.

  python -m hyp04_supply_chain_hedge.run_hyp07_existing_competitor_edges_name_search
  python -m hyp04_supply_chain_hedge.run_hyp07_existing_competitor_edges_name_search --yes-run-live
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"

IN_JSONS: tuple[Path, ...] = (
    LSE / "HYP05_CANDIDATE_LINKAGE_REAL_ANCHORS_2026-09-12.json",
    LSE / "HYP05_CANDIDATE_LINKAGE_LOCKED24ANCHORS_2026-09-12.json",
    LSE / "HYP05_CANDIDATE_LINKAGE_HISTORICAL_WALK_2026-09-12.json",
)
OUT_JSON = LSE / f"HYP07_PEER_NAME_SEARCH_EXISTING_COMPETITOR_EDGES_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

SEARCH_SPACING = 1.0
SEARCH_ATTEMPTS = 3
SEARCH_BACKOFF = 2.0


def _candidates(in_jsons: tuple[Path, ...]) -> list[dict[str, Any]]:
    """One row per DISTINCT named_counterparty across ALL input files,
    filtered to direction == "competitor". A name recurring under more
    than one anchor (or more than one source file) keeps the EARLIEST
    as_of_date (the strictest bound for the lineage test) and records
    every anchor/source it appeared under -- same merge discipline as
    run_hyp05_peer_name_search.py's own _candidates(), generalized from
    one input file to several."""
    by_name: dict[str, dict[str, Any]] = {}
    for in_json in in_jsons:
        with in_json.open(encoding="utf-8") as fh:
            data = json.load(fh)
        for e in data["edges"]:
            if e.get("direction") != "competitor":
                continue
            if not e.get("counterparty_is_named") or not e.get("named_counterparty"):
                continue
            name = e["named_counterparty"]
            row = by_name.setdefault(name, {
                "counterparty": name, "anchors": [], "as_of_date": None,
                "sources": set(), "input_files": set(),
            })
            row["anchors"].append(e["reporting_company"])
            row["sources"].add(e["source"])
            row["input_files"].add(in_json.name)
            if row["as_of_date"] is None or e["as_of_date"] < row["as_of_date"]:
                row["as_of_date"] = e["as_of_date"]
    out = []
    for row in by_name.values():
        out.append({
            "counterparty": row["counterparty"],
            "anchor_ticker": row["anchors"][0],
            "all_anchors": sorted(set(row["anchors"])),
            "as_of_date": row["as_of_date"],
            "sources": sorted(row["sources"]),
            "input_files": sorted(row["input_files"]),
        })
    return sorted(out, key=lambda r: r["counterparty"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--in-json", type=Path, action="append", default=None,
                    help="repeatable; defaults to the 3 known competitor-"
                         "edge sources")
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    a = ap.parse_args(argv)

    in_jsons = tuple(a.in_json) if a.in_json else IN_JSONS
    missing = [p for p in in_jsons if not p.is_file()]
    if missing:
        print(f"REFUSED: missing input file(s): {[str(p) for p in missing]}",
              file=sys.stderr)
        return 1
    if a.out.exists():
        print(f"REFUSED: {a.out} already exists. Dated artifacts are never "
              "overwritten.", file=sys.stderr)
        return 1

    rows = _candidates(in_jsons)
    print(f"inputs: {[p.name for p in in_jsons]}")
    print(f"distinct competitor-direction candidate names: {len(rows)}")
    for r in rows:
        anchors = ",".join(r["all_anchors"])
        print(f"  {r['counterparty']!r:35s} anchor(s)={anchors} "
              f"as_of={r['as_of_date']}")
    print(f"\nrequest ceiling: {len(rows)} search(es) + submissions "
          "fetches for accepted candidates, minus anything already cached")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_linkage import EdgarClient, FilingCache, SUBMISSIONS_URL, TICKER_MAP_URL
    from .peer_lineage import VERDICT_CONTINUOUS, assess, filer_history
    from .peer_name_search import (
        MAX_CANDIDATES_PER_NAME, decide, parse_candidate_ciks,
        parse_conformed_names, rule_description, search_url, summarise,
    )
    from .run_hyp05_peer_name_search import ticker_map_fallback_ciks

    cap = len(rows) * (MAX_CANDIDATES_PER_NAME + 1) * SEARCH_ATTEMPTS + 16
    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR),
                         spacing=SEARCH_SPACING, max_requests=cap)

    tmap = client._get_json(TICKER_MAP_URL)
    ticker_for_cik = {str(v["cik_str"]).zfill(10): str(v["ticker"]).upper()
                      for v in tmap.values()}

    histories: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def history(cik: str):
        if cik not in histories:
            try:
                histories[cik] = filer_history(
                    client._get_json(SUBMISSIONS_URL.format(cik=cik)))
            except Exception as exc:                   # noqa: BLE001
                errors[cik] = f"{type(exc).__name__}: {exc}"
                histories[cik] = None
        return histories[cik]

    out = []
    matched_names: dict[str, list[str]] = {}
    fallback_names_used: list[str] = []
    for r in rows:
        name = r["counterparty"]
        as_of = r["as_of_date"]
        xml, failure = "", ""
        for attempt in range(SEARCH_ATTEMPTS):
            try:
                xml, failure = client._get_text(search_url(name), timeout=60), ""
                break
            except Exception as exc:                   # noqa: BLE001
                failure = f"{type(exc).__name__}: {exc}"
                if attempt < SEARCH_ATTEMPTS - 1:
                    time.sleep(SEARCH_BACKOFF * (attempt + 1))
        if failure:
            errors[name] = failure
        ciks = parse_candidate_ciks(xml)
        conformed = parse_conformed_names(xml)
        if conformed:
            matched_names[name] = conformed

        if not ciks and not failure:
            fallback = ticker_map_fallback_ciks(tmap, name)
            if fallback:
                ciks = fallback
                fallback_names_used.append(name)

        accepted: list[tuple[str, str]] = []
        for cik in ciks:
            h = history(cik)
            if h is None:
                continue
            verdict = assess(h, disclosed_name=name, as_of_date=as_of,
                             anchor_ticker=r["anchor_ticker"])
            if verdict.verdict == VERDICT_CONTINUOUS:
                accepted.append((cik, h.name_in_force(as_of) or h.current_name))

        res = decide(
            anchor_ticker=r["anchor_ticker"], counterparty=name,
            as_of_date=as_of, accepted=accepted,
            candidates_examined=len(ciks), ticker_for_cik=ticker_for_cik,
            incremental_anchor_events=0, search_failed=bool(failure),
            failure=failure)
        out.append(res)

    counts = summarise(out)
    tradeable = [r for r in out if r.tradeable]
    identified = [r for r in out if r.resolved]
    unanswered = [r for r in out if r.status == "SEARCH_FAILED_question_unanswered"]

    payload = {
        "artifact": a.out.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "rule": rule_description(),
        "inputs": [p.name for p in in_jsons],
        "what_this_is": (
            f"Which registrant each of {len(rows)} already-extracted "
            "COMPETITOR-direction counterparty names (merged across three "
            "earlier HYP-05 extraction passes) referred to, and whether "
            "that registrant still trades. HYP-07's Step 0: a free-to-cheap "
            "sanity check on data that already existed before any new "
            "discovery work."),
        "what_this_is_not": (
            "Curation. No edge is written to any linkage map, no peer "
            "universe is derived here. peer_selection.py's evaluate_peer() "
            "is the next, separate step, and needs point-in-time market cap "
            "for whatever resolves here first."),
        "sources": {
            "endpoint": "www.sec.gov company search + data.sec.gov submissions",
            "names_searched": len(rows),
            "registrants_examined": len(histories),
            "requests_made": client.requests_made,
        },
        "counts_by_status": counts,
        "names_unanswered": len(unanswered),
        "unanswered_is_not_a_negative": (
            "A name whose search failed is UNANSWERED, not evidence the "
            "company doesn't exist."),
        "ticker_map_fallback_used_for": fallback_names_used,
        "names_identified": len(identified),
        "names_now_tradeable": len(tradeable),
        "results": [r.as_dict() for r in out],
        "search_matched_conformed_names": matched_names,
        "errors": errors,
        "curates_nothing": (
            "No edge is written and no candidate is promoted. No gate is "
            "touched."),
    }
    a.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    print(f"\nrequests made: {client.requests_made}")
    for k, v in sorted(counts.items()):
        print(f"  {v:3}  {k}")
    if errors:
        print(f"  errors: {list(errors)[:5]}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
