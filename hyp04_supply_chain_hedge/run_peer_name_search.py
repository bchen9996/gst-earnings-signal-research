#!/usr/bin/env python3
"""LIVE. Search EDGAR for the registrants behind unresolvable counterparties.

Named off the `test_*` pattern: it reaches an endpoint.

STAGED. Without `--yes-run-live` it prints the exact search list and the
request ceiling, then exits.

  python -m hyp04_supply_chain_hedge.run_peer_name_search           # dry run
  python -m hyp04_supply_chain_hedge.run_peer_name_search --yes-run-live

Request budget: one company search per distinct unresolved name, plus one
submissions fetch per distinct candidate CIK that has not already been seen.
Both land in the shared EDGAR cache, so a re-run is free.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .artifacts import newest_in
from .peer_ceiling import normalize_company_name
from .peer_lineage import VERDICT_CONTINUOUS, assess, filer_history
from .peer_name_search import (
    MAX_CANDIDATES_PER_NAME,
    PEER_NAME_SEARCH_RULE_ID,
    STATUS_SEARCH_FAILED,
    NameSearchResult,
    decide,
    parse_candidate_ciks,
    parse_conformed_names,
    rule_description,
    search_url,
    summarise,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-01"
OUT_JSON = LSE / f"HYP04_PEER_NAME_SEARCH_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

#: browse-edgar is a CGI endpoint, not the JSON API, and it returns 503 under
#: the spacing data.sec.gov tolerates. One second between searches, and three
#: attempts with linear backoff.
SEARCH_SPACING = 1.0
SEARCH_ATTEMPTS = 3
SEARCH_BACKOFF = 2.0


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows(p: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.open(p, encoding="utf-8", newline="")))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Identify registrants behind counterparty names SEC's "
                    "current company list cannot resolve. LIVE; staged.")
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--worklist", type=Path, default=None)
    a = ap.parse_args(argv)

    wl = a.worklist or newest_in(LSE, "HYP04_PEER_CURATION_WORKLIST_*.csv")
    if wl is None or not wl.is_file():
        print("REFUSED: no peer-curation worklist on disk", file=sys.stderr)
        return 1

    rows = _rows(wl)
    # Only names carrying sample are worth requests. A candidate with zero
    # incremental events cannot change the ceiling however it resolves.
    unres = [r for r in rows
             if not (r.get("candidate_peer_ticker") or "").strip()
             and int(r.get("incremental_anchor_events") or 0) > 0]
    if not unres:
        print(f"REFUSED: {wl.name} has no unresolved rows carrying sample",
              file=sys.stderr)
        return 1

    # One search per DISTINCT name, even when several anchors name it.
    by_name: dict[str, list[dict[str, str]]] = {}
    for r in unres:
        by_name.setdefault(r["counterparty_name_as_filed"], []).append(r)

    print(f"worklist: {wl.name}")
    print(f"unresolved rows carrying sample: {len(unres)}")
    print(f"distinct names to search: {len(by_name)}")
    for n, rs in sorted(by_name.items(),
                        key=lambda kv: -max(int(x["incremental_anchor_events"])
                                            for x in kv[1])):
        best = max(int(x["incremental_anchor_events"]) for x in rs)
        print(f"  {best:4} events  {n}")
    print(f"\nrequest ceiling: {len(by_name)} search(es) + up to "
          f"{len(by_name) * MAX_CANDIDATES_PER_NAME} submissions fetch(es), "
          "minus anything already cached")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_linkage import (
        EdgarClient, FilingCache, SUBMISSIONS_URL, TICKER_MAP_URL)

    cap = len(by_name) * (MAX_CANDIDATES_PER_NAME + 1) * SEARCH_ATTEMPTS + 16
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

    out: list[NameSearchResult] = []
    # Conformed names, when the response was the single-match shape. Reported
    # so a reader can see what the search actually matched; nothing is
    # accepted on their strength.
    matched_names: dict[str, list[str]] = {}
    for name, rs in by_name.items():
        r0 = max(rs, key=lambda x: int(x["incremental_anchor_events"]))
        as_of = r0["earliest_disclosing_filing_date"]
        # RETRIED, and 60s rather than the 30s default. browse-edgar is a CGI
        # script that returns 503 under load: the first run of this module lost
        # 8 of 24 names to 503s and read timeouts. `edgar_linkage._get` has no
        # retry (it is shared with the linkage walk and is not changed here),
        # so the backoff lives at this call site.
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

        accepted: list[tuple[str, str]] = []
        for cik in ciks:
            h = history(cik)
            if h is None:
                continue
            verdict = assess(h, disclosed_name=name, as_of_date=as_of,
                             anchor_ticker=r0["anchor_ticker"])
            if verdict.verdict == VERDICT_CONTINUOUS:
                accepted.append((cik, h.name_in_force(as_of) or h.current_name))

        res = decide(
            anchor_ticker=r0["anchor_ticker"], counterparty=name,
            as_of_date=as_of, accepted=accepted,
            candidates_examined=len(ciks), ticker_for_cik=ticker_for_cik,
            incremental_anchor_events=int(r0["incremental_anchor_events"]),
            search_failed=bool(failure), failure=failure)
        out.append(res)

    counts = summarise(out)
    tradeable = [r for r in out if r.tradeable]
    identified = [r for r in out if r.resolved]
    unanswered = [r for r in out if r.status == STATUS_SEARCH_FAILED]

    payload = {
        "artifact": OUT_JSON.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "rule": rule_description(),
        "what_this_is": (
            "Which registrant each unresolvable counterparty name referred "
            "to, and whether that registrant still trades."),
        "what_this_is_not": (
            "Curation. No edge is written, and a resolved registrant is a "
            "candidate for review, not an edge."),
        "sources": {
            "worklist": wl.name,
            "worklist_sha256": _sha256(wl),
            "endpoint": "www.sec.gov company search + data.sec.gov submissions",
            "names_searched": len(by_name),
            "registrants_examined": len(histories),
            "requests_made": client.requests_made,
        },
        "counts_by_status": counts,
        "names_unanswered": len(unanswered),
        "events_behind_unanswered_names": sum(
            r.incremental_anchor_events for r in unanswered),
        "unanswered_is_not_a_negative": (
            "A name whose search failed is UNANSWERED. The first run of this "
            "module recorded 8 such names as 'no registrant matched', which "
            "reported an endpoint outage as a fact about those companies. "
            "They are counted separately and excluded from every conclusion."),
        "names_identified": len(identified),
        "names_now_tradeable": len(tradeable),
        "events_behind_identified_but_untradeable": sum(
            r.incremental_anchor_events for r in identified if not r.tradeable),
        "events_behind_newly_tradeable": sum(
            r.incremental_anchor_events for r in tradeable),
        "results": [r.as_dict() for r in out],
        "search_matched_conformed_names": matched_names,
        "errors": errors,
        "opens_no_gate": (
            "Gate CLOSED, C4 MET, four denials, eligible count zero."),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"\nrequests made: {client.requests_made}")
    for k, v in sorted(counts.items()):
        print(f"  {v:3}  {k}")
    if errors:
        print(f"  errors: {list(errors)[:5]}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
