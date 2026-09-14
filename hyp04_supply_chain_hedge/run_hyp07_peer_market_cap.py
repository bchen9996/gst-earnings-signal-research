#!/usr/bin/env python3
"""LIVE. Point-in-time market cap for HYP-07's resolved competitor-peer
candidates, evaluated against every real anchor event available for their
anchor -- MAKES REAL PROVIDER CALLS (SEC companyfacts for shares
outstanding, Yahoo for historical closes).

=== WHY A NEW SCRIPT, NOT run_hyp05_peer_market_cap.py EDITED ===

Reuses that script's own pure pieces directly (`DIRECTION_TO_RELATIONSHIP_
TYPE` -- already maps "competitor" -> "sector_competitor", no change
needed; `_anchor_event_dates` -- already generic over a list of
anchor-shocks CSVs) rather than editing it, because this script's own
`_resolved_candidates` must join against MULTIPLE candidate-linkage JSONs
(HYP-07's Step 0 reads three existing HYP-05 extraction files at once,
unlike HYP-05's own script, which always reads exactly one) and because
every dated artifact this writes needs its own "hypothesis_id": "HYP-07"
tag -- hardcoding "HYP-05" into that field the way the original script does
is exactly why it can't be reused unchanged here. Everything else --
`auto_adjust=False` (raw historical price matching shares_outstanding.py's
raw, as-disclosed share count -- see that module's own docstring for why
auto_adjust=True would silently understate market cap after a later
split), `market_cap_as_of`, `peer_selection.derive_peer_universe` -- is
identical.

Serves BOTH of HYP-07's candidate streams (Step 0's already-extracted
edges, Step 2's reverse-search-confirmed edges) -- both produce the
identical {name-search JSON, candidate-linkage JSON} shape, so one script
reads either via --name-search/--candidate-linkage.

Run (needs network, and a completed name-search to read candidates from):
  python -m hyp04_supply_chain_hedge.run_hyp07_peer_market_cap \
    --name-search "Live Signal Engine/HYP07_PEER_NAME_SEARCH_EXISTING_COMPETITOR_EDGES_2026-09-13.json" \
    --yes-run-live
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"
ANCHOR_SHOCKS_CSVS_DEFAULT: tuple[Path, ...] = (
    LSE / "HYP04_ANCHOR_SHOCKS_2026-08-31.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-12.csv",
    LSE / "HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-13.csv",
)
CANDIDATE_LINKAGE_JSONS_DEFAULT: tuple[Path, ...] = (
    LSE / "HYP05_CANDIDATE_LINKAGE_REAL_ANCHORS_2026-09-12.json",
    LSE / "HYP05_CANDIDATE_LINKAGE_LOCKED24ANCHORS_2026-09-12.json",
    LSE / "HYP05_CANDIDATE_LINKAGE_HISTORICAL_WALK_2026-09-12.json",
)

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

# Reused verbatim from run_hyp05_peer_market_cap.py -- "competitor" already
# maps to "sector_competitor" (named as a rival, not a transacting
# counterparty), no change needed for HYP-07's use.
from .run_hyp05_peer_market_cap import (  # noqa: E402
    DIRECTION_TO_RELATIONSHIP_TYPE, _anchor_event_dates,
)


def _resolved_candidates(name_search_json: Path,
                         candidate_linkage_jsons: tuple[Path, ...]
                         ) -> list[dict[str, Any]]:
    """Join the name-search result (peer_ticker, registrant_cik) back onto
    the original extracted edges (direction, as_of_date, source) by
    counterparty name, keeping only STATUS_RESOLVED rows with a tradeable
    ticker. Generalizes run_hyp05_peer_market_cap.py's own single-file
    version to read across SEVERAL candidate-linkage JSONs, since HYP-07's
    Step 0 name-search input was itself merged from three files.

    Keyed by (anchor_ticker, named_counterparty), NOT named_counterparty
    alone -- HYP-07's real reverse-search output genuinely has the same
    counterparty name (e.g. FISERV INC) confirmed under multiple DIFFERENT
    anchors (AAPL, GOOGL, SBUX), each with its own as_of_date. A name-only
    key would silently give every anchor's row the SAME (wrong, for two
    of the three) as_of_date -- the same (anchor, peer_cik) collision
    round 6's scaled hand-review already found and fixed, showing up here
    one join step later. Reads either edge-schema's anchor field
    (`anchor_ticker`, this project's newer convention -- or
    `reporting_company`, the older extraction schema HYP-05's three
    existing candidate-linkage files still use)."""
    import json

    with name_search_json.open(encoding="utf-8") as fh:
        search = json.load(fh)

    edge_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for linkage_json in candidate_linkage_jsons:
        with linkage_json.open(encoding="utf-8") as fh:
            linkage = json.load(fh)
        for e in linkage["edges"]:
            if e.get("direction") != "competitor":
                continue
            if not (e.get("counterparty_is_named") and e.get("named_counterparty")):
                continue
            anchor = e.get("anchor_ticker") or e.get("reporting_company")
            if not anchor:
                continue
            edge_by_key.setdefault((anchor, e["named_counterparty"]), e)

    out = []
    for r in search["results"]:
        if not r.get("tradeable") or not r.get("peer_ticker"):
            continue
        edge = edge_by_key.get((r["anchor_ticker"], r["counterparty"]))
        if edge is None:
            continue
        out.append({
            "counterparty": r["counterparty"],
            "peer_ticker": r["peer_ticker"],
            "registrant_cik": r["registrant_cik"],
            "anchor_ticker": r["anchor_ticker"],
            "direction": edge["direction"],
            "as_of_date": edge["as_of_date"],
            "source": edge["source"],
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--name-search", type=Path, required=True)
    ap.add_argument("--candidate-linkage", type=Path, nargs="+",
                    default=list(CANDIDATE_LINKAGE_JSONS_DEFAULT))
    ap.add_argument("--anchor-shocks-csv", type=Path, nargs="+",
                    default=list(ANCHOR_SHOCKS_CSVS_DEFAULT))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    out_path = a.out or (LSE / f"HYP07_PEER_UNIVERSE_{AS_OF}.json")
    if out_path.exists():
        print(f"REFUSED: {out_path} already exists. Dated artifacts are "
              "never overwritten.", file=sys.stderr)
        return 1

    for p in (a.name_search, *a.candidate_linkage, *a.anchor_shocks_csv):
        if not p.is_file():
            print(f"REFUSED: {p} does not exist", file=sys.stderr)
            return 1

    resolved = _resolved_candidates(a.name_search, tuple(a.candidate_linkage))
    print(f"resolved, tradeable candidates: {len(resolved)}")

    plan: list[dict[str, Any]] = []
    for c in resolved:
        events = _anchor_event_dates(a.anchor_shocks_csv, c["anchor_ticker"])
        plan.append({**c, "event_dates": events})
        print(f"  {c['peer_ticker']:8s} (from {c['counterparty']!r}, "
              f"anchor={c['anchor_ticker']}): {len(events)} events, "
              f"{events[0] if events else '-'}..{events[-1] if events else '-'}")

    total_pairs = sum(len(p["event_dates"]) for p in plan)
    print(f"\ntotal (peer, anchor_event) pairs to evaluate: {total_pairs}")
    print(f"yfinance calls needed: {len(plan)} (one date-range pull per peer)")
    print(f"companyfacts calls needed: up to {len(plan)} (one per peer, "
          "cached if already pulled)")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_linkage import EdgarClient, FilingCache
    from .shares_outstanding import facts_from_companyfacts
    from .point_in_time_market_cap import (
        market_cap_as_of, price_lookup_from_observations)
    from .run_peer_closes_fetch import fetch_closes
    from .peer_returns import PriceObservation
    from .peer_selection import derive_peer_universe, format_report

    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR))

    market_caps: dict[tuple[str, str], Any] = {}
    candidates_for_rule: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for p in plan:
        ticker = p["peer_ticker"]
        events = p["event_dates"]
        if not events:
            errors[ticker] = "anchor has zero shock_computed events"
            continue
        try:
            facts_json = client.companyfacts(p["registrant_cik"])
            shares_series = facts_from_companyfacts(ticker, facts_json)
        except Exception as exc:                       # noqa: BLE001
            errors[ticker] = f"shares_outstanding: {type(exc).__name__}: {exc}"
            shares_series = ()

        first = date.fromisoformat(min(events))
        last = date.fromisoformat(max(events))
        try:
            closes = fetch_closes(ticker, first, last, auto_adjust=False)
        except Exception as exc:                       # noqa: BLE001
            errors[ticker] = f"fetch_closes: {type(exc).__name__}: {exc}"
            closes = {}
        obs = [PriceObservation(ticker=ticker, session_date=d, close=c)
               for d, c in closes.items()]
        price_lookup = price_lookup_from_observations(obs)

        for ev_date in events:
            mc = market_cap_as_of(ticker, ev_date, shares_series=shares_series,
                                  price_lookup=price_lookup)
            market_caps[(ticker.upper(), ev_date)] = mc
            candidates_for_rule.append({
                "peer_ticker": ticker,
                "anchor_ticker": p["anchor_ticker"],
                "anchor_event_date": ev_date,
                "relationship_type": DIRECTION_TO_RELATIONSHIP_TYPE.get(
                    p["direction"], "loose_sector_neighbor"),
                "as_of_date": p["as_of_date"],
                "source": p["source"],
            })

    derivation = derive_peer_universe(candidates_for_rule, market_caps)

    import json
    payload = {
        "artifact": out_path.name,
        "hypothesis_id": "HYP-07",
        "inputs": {
            "name_search": str(a.name_search),
            "candidate_linkage": [str(p) for p in a.candidate_linkage],
            "anchor_shocks_csv": [str(p) for p in a.anchor_shocks_csv],
        },
        "what_this_is": (
            "Real point-in-time market-cap evaluation of every resolved, "
            "tradeable HYP-07 competitor-relationship candidate peer, "
            "against every real anchor event available for its anchor."),
        "adjustment_note": (
            "Closes fetched with auto_adjust=False -- raw historical price, "
            "matching shares_outstanding.py's raw, as-disclosed share "
            "count."),
        "candidates_evaluated": len(candidates_for_rule),
        "peer_tickers": sorted({c["peer_ticker"] for c in candidates_for_rule}),
        "errors": errors,
        "derivation": {
            "derived": derivation.derived,
            "rule_id": derivation.rule_id,
            "refusals": list(derivation.refusals),
            "members": sorted(set(derivation.members)),
        },
        "qualifications": [q.as_dict() for q in derivation.qualifications],
        "report": format_report(derivation),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                        encoding="utf-8")

    print(f"\nderived: {derivation.derived}")
    print(f"qualifying (peer, event) pairs: "
          f"{sum(1 for q in derivation.qualifications if q.qualifies)} of "
          f"{len(derivation.qualifications)}")
    print(f"distinct qualifying peer tickers: {sorted(set(derivation.members))}")
    if errors:
        print(f"errors: {errors}")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
