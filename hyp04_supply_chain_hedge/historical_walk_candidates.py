#!/usr/bin/env python3
"""Reshape a competitor-history-walk report into the candidate-linkage
edges shape `run_hyp05_peer_name_search.py` and `run_hyp05_peer_market_
cap.py` already read -- so that already-tested machinery runs UNCHANGED
against historical-walk candidates, instead of teaching it a second input
shape.

Pure, offline, no network. `INCLUDE` is a fixed, hand-picked ALLOWLIST of
counterparty names worth spending real SEC name-search requests on --
fixed here, in code, BEFORE any name-search request is made, the same
"decided before seeing results" discipline every other candidate list in
this project follows. Large, already-well-known names (Apple, Microsoft,
Google, Yahoo, Autodesk, Oracle, IBM, Samsung, TSMC, Micron, SK Hynix,
GlobalFoundries, SMIC, UMC, AMD) are excluded -- not because they're
uninteresting, but because HYP-04's own real anchors already surfaced
several of them in the first (latest-10-K) pass, and every one is large
enough that a real market-cap check would deny it on PS-3 regardless of
whether the name resolves. Spending a request confirming that is not
worth it; the ones actually worth a fresh look are the smaller, less-
obvious names a single recent snapshot never surfaced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

LSE = Path("Live Signal Engine")
WALK_JSON = LSE / "HYP05_COMPETITOR_HISTORY_WALK.json"

SOURCE_HISTORICAL_WALK = "EDGAR_10K_COMPETITION_SECTION_PROSE_HISTORICAL_WALK"

# Fixed before running. See module docstring for why each excluded name is
# excluded (already large/well-known, not because it's unimportant).
INCLUDE: frozenset[str] = frozenset({
    # ADBE -- smaller/specialised software competitors, several since
    # acquired or defunct, never surfaced by the latest-10-K-only pass.
    "Corel", "Jasc Software", "Macromedia", "Coremetrics", "Nedstat",
    "Quark", "Getty Images", "Shutterstock", "Foundry", "Quixel", "Unity",
    "C4D", "Avid",
    # INTC -- a real, obscure joint-venture name (IM Flash Technologies).
    "IMFT",
    # NVDA -- smaller Taiwanese/Japanese supply-chain names, all three
    # string variants of what may be one real company across different
    # years (resolved separately, not merged -- see the module this walk
    # itself came from for why).
    "Unimicron Technology Corporation", "IbidenCo", "IbidenCo., Ltd",
    "Ibiden Co. Ltd", "Nanya Technology Corporation",
    "Kinsus Interconnect Technology Corporation",
})


def edges_from_walk(walk_json: Path, *,
                    include: frozenset[str] = INCLUDE) -> dict[str, Any]:
    """Build the {"edges": [...]} shape `_candidates()` (in
    run_hyp05_peer_name_search.py) and `_resolved_candidates()` (in
    run_hyp05_peer_market_cap.py) both already read, from a competitor-
    history-walk report's per-ticker `named_counterparties`. Only entries
    whose counterparty is in `include` are kept."""
    with walk_json.open(encoding="utf-8") as fh:
        walk = json.load(fh)

    edges: list[dict[str, Any]] = []
    for t in walk["tickers"]:
        for nc in t["named_counterparties"]:
            if nc["counterparty"] not in include:
                continue
            edges.append({
                "reporting_company": t["ticker"],
                "reporting_cik": t["cik"],
                "named_counterparty": nc["counterparty"],
                "counterparty_is_named": True,
                "direction": nc["direction"],
                "concentration_pct": None,
                "as_of_date": nc["earliest_filing_date"],
                "accession": nc["earliest_accession"],
                "form": "10-K",
                "source": SOURCE_HISTORICAL_WALK,
                "pattern": nc.get("pattern", ""),
                "context": "",
            })
    return {
        "artifact": "HYP05_CANDIDATE_LINKAGE_HISTORICAL_WALK.json",
        "source": SOURCE_HISTORICAL_WALK,
        "is_production_linkage_map": False,
        "status": "CANDIDATE_REVIEW_QUEUE",
        "derived_from": walk_json.name,
        "include_allowlist_size": len(include),
        "edges": edges,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--walk-json", type=Path, default=WALK_JSON)
    ap.add_argument("--out", type=Path,
                    default=LSE / "HYP05_CANDIDATE_LINKAGE_HISTORICAL_WALK_2026-09-12.json")
    a = ap.parse_args(argv)

    if not a.walk_json.is_file():
        print(f"REFUSED: {a.walk_json} does not exist", file=sys.stderr)
        return 1

    out = edges_from_walk(a.walk_json)
    print(f"{len(out['edges'])} candidate edges from {len(INCLUDE)} "
          f"allowlisted names")
    for e in out["edges"]:
        print(f"  {e['reporting_company']:6s} -> {e['named_counterparty']:45s} "
              f"[{e['direction']}] as_of={e['as_of_date']}")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
