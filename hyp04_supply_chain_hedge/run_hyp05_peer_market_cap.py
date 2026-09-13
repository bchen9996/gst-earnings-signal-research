#!/usr/bin/env python3
"""LIVE. Point-in-time market cap for HYP-05's resolved peer candidates,
evaluated against every real HYP-04 anchor event -- MAKES REAL PROVIDER
CALLS (SEC companyfacts for shares outstanding, Yahoo for historical
closes).

=== WHY A NEW SCRIPT, AND WHY auto_adjust=False (NOT run_peer_closes_
fetch.py's own default) ===

`run_peer_closes_fetch.fetch_closes()` is reused UNCHANGED for the actual
provider call -- no reimplementation. But that module's own default,
`auto_adjust=True`, is chosen for a RETURN-SERIES purpose ("splits must be
adjusted [for realized variance], dividends are a judgement call") that
does not transfer here. Market cap is price x shares, both evaluated AT A
SPECIFIC HISTORICAL DATE: `shares_outstanding.py` returns the ACTUAL,
contemporaneously-disclosed share count as of that date, never adjusted
for a later split. Multiplying that against a split-adjusted price would
silently understate market cap by the cumulative split ratio -- e.g. a
share count from before a later 4-for-1 split, multiplied by a price
already divided by 4 for that same split, is wrong by 4x. This script
therefore calls `fetch_closes(..., auto_adjust=False)` explicitly: the
RAW close the stock actually traded at on that date, matching the RAW,
as-disclosed share count `shares_outstanding.py` already returns.

=== WHICH ANCHOR EVENT DATES ===

`HYP04_ANCHOR_SHOCKS_2026-08-31.csv`'s `release_date` column -- the actual
calendar date of the anchor's earnings release -- for every row with
`status == "shock_computed"` (a denied-session row has no usable event to
evaluate a peer against). EVERY qualifying event for the candidate's
anchor is evaluated, not a sample: `fetch_closes()` returns a whole date
range in one provider call, so evaluating all of an anchor's events costs
one yfinance call per peer ticker, not one call per event. Sampling would
also need its own justification for which events were kept -- evaluating
all of them avoids that judgment call entirely.

=== RELATIONSHIP-TYPE MAPPING ===

`peer_selection.py`'s candidate schema uses `curated_linkage.RELATIONSHIP_
TYPES` ("direct_supplier", "direct_customer", "sector_competitor",
"loose_sector_neighbor"); the extractor's edges carry `direction` in
{"customer", "supplier", "competitor"}. Mapped customer->direct_customer,
supplier->direct_supplier, competitor->sector_competitor -- "direct_" for
the two ASC-280/supplier-context directions (a real, cited relationship),
"sector_competitor" for the competitor-context direction (named as a
rival, not a counterparty in a transaction).

Run (needs network, and a completed name-search to read candidates from):
  python -m hyp04_supply_chain_hedge.run_hyp05_peer_market_cap \
    --name-search "Live Signal Engine/HYP05_PEER_NAME_SEARCH_REAL_ANCHORS_2026-09-12.json" \
    --yes-run-live
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

LSE = Path("Live Signal Engine")
ANCHOR_SHOCKS_CSV = LSE / "HYP04_ANCHOR_SHOCKS_2026-08-31.csv"
CANDIDATE_LINKAGE_JSON = LSE / "HYP05_CANDIDATE_LINKAGE_REAL_ANCHORS_2026-09-12.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

DIRECTION_TO_RELATIONSHIP_TYPE = {
    "customer": "direct_customer",
    "supplier": "direct_supplier",
    "competitor": "sector_competitor",
}


def _anchor_event_dates(csv_paths: Path | list[Path],
                        anchor_ticker: str) -> list[str]:
    """Every `status == shock_computed` release_date for one anchor,
    sorted, deduplicated, across one or more anchor-shocks CSVs. A
    denied-session row is skipped -- it has no usable event to evaluate a
    peer's eligibility against.

    Accepts either a single Path (HYP-04's original call shape, unchanged)
    or a list -- e.g. HYP04_ANCHOR_SHOCKS_2026-08-31.csv (7 anchors) PLUS
    HYP05_ADDITIONAL_ANCHOR_SHOCKS_2026-09-12.csv (DELL/DVN/GOOGL), neither
    file ever merged or edited, both read side by side."""
    paths = [csv_paths] if isinstance(csv_paths, Path) else list(csv_paths)
    out: set[str] = set()
    for csv_path in paths:
        with csv_path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row["anchor_ticker"] == anchor_ticker
                        and row["status"] == "shock_computed"):
                    out.add(row["release_date"])
    return sorted(out)


def _resolved_candidates(name_search_json: Path,
                         candidate_linkage_json: Path) -> list[dict[str, Any]]:
    """Join the name-search result (peer_ticker, registrant_cik) back onto
    the original extracted edges (direction, as_of_date, source) by
    counterparty name, keeping only STATUS_RESOLVED rows with a tradeable
    ticker."""
    with name_search_json.open(encoding="utf-8") as fh:
        search = json.load(fh)
    with candidate_linkage_json.open(encoding="utf-8") as fh:
        linkage = json.load(fh)

    edge_by_name: dict[str, dict[str, Any]] = {}
    for e in linkage["edges"]:
        if e.get("counterparty_is_named") and e.get("named_counterparty"):
            edge_by_name.setdefault(e["named_counterparty"], e)

    out = []
    for r in search["results"]:
        if not r.get("tradeable") or not r.get("peer_ticker"):
            continue
        edge = edge_by_name.get(r["counterparty"])
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
    ap.add_argument("--candidate-linkage", type=Path,
                    default=CANDIDATE_LINKAGE_JSON)
    ap.add_argument("--anchor-shocks-csv", type=Path, nargs="+",
                    default=[ANCHOR_SHOCKS_CSV])
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    out_path = a.out or (LSE / "HYP05_PEER_UNIVERSE_2026-09-12.json")
    if out_path.exists():
        # Missing until 2026-09-12: this script's OWN default --out
        # silently overwrote a real, already-committed governance
        # artifact from an earlier pass (the first, pre-hand-curation
        # extraction-based run) because nothing here ever checked. Every
        # OTHER dated-output script in this project refuses up front;
        # this one now does too.
        print(f"REFUSED: {out_path} already exists. Dated artifacts are "
              "never overwritten.", file=sys.stderr)
        return 1

    for p in (a.name_search, a.candidate_linkage, *a.anchor_shocks_csv):
        if not p.is_file():
            print(f"REFUSED: {p} does not exist", file=sys.stderr)
            return 1

    resolved = _resolved_candidates(a.name_search, a.candidate_linkage)
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
    from .shares_outstanding import (
        facts_from_companyfacts, shares_outstanding_as_of)
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

    payload = {
        "artifact": out_path.name,
        "hypothesis_id": "HYP-05",
        "inputs": {
            "name_search": str(a.name_search),
            "candidate_linkage": str(a.candidate_linkage),
            "anchor_shocks_csv": [str(p) for p in a.anchor_shocks_csv],
        },
        "what_this_is": (
            "Real point-in-time market-cap evaluation of every resolved, "
            "tradeable HYP-05 candidate peer, against EVERY real HYP-04 "
            "anchor event (not a sample) for its anchor."),
        "adjustment_note": (
            "Closes fetched with auto_adjust=False -- raw historical price, "
            "matching shares_outstanding.py's raw, as-disclosed share "
            "count. See module docstring for why auto_adjust=True would "
            "silently understate market cap after any later split."),
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
