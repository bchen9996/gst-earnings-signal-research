#!/usr/bin/env python3
"""LIVE. Resolve HYP-05's 39 candidate counterparty NAMES to real registrants.

Reuses HYP-04's own name-resolution machinery UNCHANGED -- `peer_name_search`
(the company-search-then-lineage-test decision rule, MAX_CANDIDATES_PER_NAME,
STATUS_* verdicts) and `peer_lineage` (`filer_history`/`assess`, the same
CONTINUOUS-lineage test that rejected INGM). Nothing about resolving a name
to a registrant is HYP-specific; only the INPUT SHAPE differs from
`run_peer_name_search.py`'s (a HYP-04 peer-curation worklist CSV). HYP-05's
input is `named_counterparty`/`reporting_company`/`as_of_date` triples read
directly from the wired extract_for_universe() output
(HYP05_CANDIDATE_LINKAGE_LOCKED24ANCHORS_2026-09-12.json) -- no worklist
CSV exists for HYP-05, so this reads that JSON instead.

STAGED, same discipline as run_peer_name_search.py: without --yes-run-live
it prints the search list and the request ceiling, then exits.

  python -m hyp04_supply_chain_hedge.run_hyp05_peer_name_search              # dry run
  python -m hyp04_supply_chain_hedge.run_hyp05_peer_name_search --yes-run-live

`cik_for()` alone cannot do this: it is an exact-ticker lookup against
TODAY's company list, and these are free-text NAMES extracted from prose
(some foreign, some private, some no longer trading) -- exactly the gap
`peer_name_search`'s company-search-plus-lineage-test exists to close.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

LSE = Path("Live Signal Engine")
IN_JSON = LSE / "HYP05_CANDIDATE_LINKAGE_LOCKED24ANCHORS_2026-09-12.json"
AS_OF = "2026-09-12"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

SEARCH_SPACING = 1.0
SEARCH_ATTEMPTS = 3
SEARCH_BACKOFF = 2.0


def ticker_map_fallback_ciks(tmap: dict[str, Any], name: str) -> list[str]:
    """Fallback candidate discovery for when EDGAR's browse-edgar company
    search returns zero candidates for a name that is a real, findable
    company. Found live, not speculatively: 'Columbia Sportswear' (a
    real, currently-trading NKE-scale candidate, CIK 0001050797, ticker
    COLM) returned a genuinely empty search feed; a broader one-word
    query ('Columbia') returned entries, but with the conformed company
    name replaced by a literal Perl array-reference dump
    ('ARRAY(0x55a888699870)') instead of an actual name -- a defect on
    SEC's own browse-edgar side, reproduced directly against the live
    endpoint, not a bug in this project's request construction.

    `company_tickers.json` (already used elsewhere in this package, e.g.
    AgreementSearchClient.cik_for() in edgar_agreements.py) is a
    different, independently-maintained SEC endpoint. Any CURRENTLY-
    TRADING company whose registered title starts with `name`
    (case-insensitive) is returned. This only helps a name that is ALSO
    a current ticker's registered company -- it has none of browse-
    edgar's broader coverage of delisted, private, or historically-named
    entities, so it is tried ONLY as a fallback, after a zero-candidate
    search, never in place of the primary search."""
    name_lower = name.strip().lower()
    if not name_lower:
        return []
    out: list[str] = []
    for v in tmap.values():
        title = str(v.get("title", ""))
        if title.lower().startswith(name_lower):
            out.append(str(v["cik_str"]).zfill(10))
    return out


def _candidates(in_json: Path) -> list[dict[str, str]]:
    """One row per DISTINCT named_counterparty from the wired extraction
    output. A name that recurs under more than one anchor keeps the
    EARLIEST as_of_date (the strictest bound for the lineage test) and
    records every anchor it appeared under."""
    with in_json.open(encoding="utf-8") as fh:
        data = json.load(fh)
    by_name: dict[str, dict[str, Any]] = {}
    for e in data["edges"]:
        if not e.get("counterparty_is_named") or not e.get("named_counterparty"):
            continue
        name = e["named_counterparty"]
        row = by_name.setdefault(name, {
            "counterparty": name, "anchors": [], "as_of_date": None,
            "sources": set(),
        })
        row["anchors"].append(e["reporting_company"])
        row["sources"].add(e["source"])
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
        })
    return sorted(out, key=lambda r: r["counterparty"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--in-json", type=Path, default=IN_JSON)
    a = ap.parse_args(argv)

    if not a.in_json.is_file():
        print(f"REFUSED: {a.in_json} does not exist", file=sys.stderr)
        return 1

    # Output filename is derived from the input's own scope label, not a
    # fixed constant -- two different candidate-linkage inputs (e.g.
    # LOCKED24ANCHORS vs REAL_ANCHORS) must never write to, or be confused
    # with, the same output file.
    scope = a.in_json.stem
    for prefix in ("HYP05_CANDIDATE_LINKAGE_",):
        if scope.startswith(prefix):
            scope = scope[len(prefix):]
    out_json = LSE / f"HYP05_PEER_NAME_SEARCH_{scope}.json"

    rows = _candidates(a.in_json)
    print(f"input: {a.in_json.name}")
    print(f"distinct candidate names: {len(rows)}")
    for r in rows:
        anchors = ",".join(r["all_anchors"])
        print(f"  {r['counterparty']!r:45s} anchor(s)={anchors} "
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

        # A real search (no exception, no retry-exhausted failure) that
        # still found zero candidates may be this project's own request
        # being wrong -- or it may be browse-edgar itself malfunctioning
        # for this query (see ticker_map_fallback_ciks()'s docstring for
        # a reproduced live example). Try the independent ticker-map
        # endpoint before concluding "no registrant" for a real company.
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
        "artifact": out_json.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "rule": rule_description(),
        "input": a.in_json.name,
        "what_this_is": (
            f"Which registrant each of {len(rows)} extracted competitor/"
            "supplier counterparty names (from the input above) referred "
            "to, and whether that registrant still trades."),
        "what_this_is_not": (
            "Curation. No edge is written to any linkage map, no peer "
            "universe is derived here. peer_selection.py's evaluate_peer() "
            "is the next, separate step, and needs point-in-time market cap "
            "(shares_outstanding.py + point_in_time_market_cap.py) for "
            "whatever resolves here first."),
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
            "company doesn't exist -- an endpoint outage deciding a result "
            "is the failure this project refuses everywhere else."),
        "ticker_map_fallback_used_for": fallback_names_used,
        "ticker_map_fallback_note": (
            "browse-edgar's company search returned zero candidates for "
            "these names despite a successful (non-failed) request; "
            "company_tickers.json resolved a currently-trading match "
            "instead. See ticker_map_fallback_ciks()'s docstring for a "
            "reproduced live example of browse-edgar's own malfunction "
            "(a genuinely empty feed for an exact real company name, and "
            "a corrupted-name response for a broader query)."),
        "names_identified": len(identified),
        "names_now_tradeable": len(tradeable),
        "results": [r.as_dict() for r in out],
        "search_matched_conformed_names": matched_names,
        "errors": errors,
        "curates_nothing": (
            "No edge is written and no candidate is promoted. Neither "
            "HYP-04's nor HYP-05's display gate is touched."),
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"\nrequests made: {client.requests_made}")
    for k, v in sorted(counts.items()):
        print(f"  {v:3}  {k}")
    if errors:
        print(f"  errors: {list(errors)[:5]}")
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
