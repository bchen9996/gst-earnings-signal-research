#!/usr/bin/env python3
"""LIVE. Scaled reverse-direction EDGAR full-text search: the SAME
mechanism as run_hyp05_reverse_concentration_search.py (round 4), run
over a much larger anchor set. MAKES REAL PROVIDER CALLS.

=== WHY A SEPARATE SCRIPT, NOT A MODIFIED ROUND-4 ONE ===

Round 4's script is already tested and committed. This reuses its exact,
UNCHANGED `discover_leads()` / `verify_lead()` / `CONCENTRATION_PHRASES` /
`MAX_HITS_PER_QUERY` rather than editing it -- the same "new script,
shared pure functions" pattern `run_hyp05_additional_anchor_shocks.py`
already established against `make_anchor_shocks.py`.

=== THE EXPANDED ANCHOR SET, AND WHY IT IS PRINCIPLED, NOT CHERRY-PICKED
===

Round 4 searched 27 anchors: the locked-24 plus 3 more (JBL, MCK, NVDA).
Scaling further needs many more anchor NAMES, and the temptation is to
hand-pick which large companies "plausibly" have documented small-cap
counterparties -- exactly the failure mode round 4's own docstring
already rejected once ("No anchor is pre-filtered by plausibility").

This reuses `Small-Mid Cap Universe Expansion/Russell1000Proxy_Filtered_
Universe.csv` -- 788 tickers, already in this repo, built well before
this decision for an unrelated purpose (a liquidity screen for
options-based work). Using it here mirrors the reasoning `anchor_
universe.py`'s own `screening_frame()` gives for its locked-24-plus-
candidate-universe frame: a frame that predates the decision it is used
for cannot have been drawn around the outcome.

Every one of its 788 companies is searched, unconditionally -- no
plausibility filter, no market-cap or sector filter, matching round 4's
own stated discipline. Each net-new ticker gets exactly ONE name variant:
that file's own `company` column, which is already natural-prose-shaped
("American Airlines Group", not an all-caps filer title) -- see round
4's own docstring for why an all-caps registrant title is the wrong kind
of string to search for. This is a real, disclosed reduction in per-
anchor recall against round 4's hand-curated anchors (some of which carry
2 spelling variants); the tradeoff is breadth (27 -> ~800 anchors) over
depth, made explicitly rather than silently.

Any of the 27 anchors already searched in round 4 are skipped here
entirely -- never re-searched, never given a second, possibly-redundant
variant list. See `load_expanded_anchor_universe()`.

=== EVERYTHING ELSE IS IDENTICAL TO ROUND 4 ===

Same phrases, same MAX_HITS_PER_QUERY, same verification
(`classify_context` plus the percent-in-sentence check, both reused
unchanged inside `verify_lead`), same output shapes, same source tag (the
mechanism really is identical; only the anchor list is bigger) --
distinguished from round 4's artifacts by filename/date alone, the same
way round 4's hand-reviewed artifacts are distinguished from its raw
ones, never by inventing a parallel source-tag namespace for an
identical mechanism.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp05_reverse_concentration_search_scaled
  python -m hyp04_supply_chain_hedge.run_hyp05_reverse_concentration_search_scaled --yes-run-live
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .run_hyp05_reverse_concentration_search import (
    ANCHOR_NAME_VARIANTS,
    CONCENTRATION_PHRASES,
    CONTACT,
    MAX_HITS_PER_QUERY,
    SOURCE_REVERSE_CONCENTRATION_SEARCH,
    discover_leads,
    verify_lead,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"

RUSSELL1000_PROXY_CSV = (Path("Small-Mid Cap Universe Expansion")
                         / "Russell1000Proxy_Filtered_Universe.csv")

OUT_NAME_SEARCH = LSE / f"HYP05_PEER_NAME_SEARCH_REVERSE_SEARCH_SCALED_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP05_CANDIDATE_LINKAGE_REVERSE_SEARCH_SCALED_{AS_OF}.json"
OUT_RAW_HITS = LSE / f"HYP05_REVERSE_SEARCH_RAW_HITS_SCALED_{AS_OF}.json"

PROVENANCE_HAND_CURATED = "hand_curated"
PROVENANCE_RUSSELL1000_PROXY = "russell1000_proxy_company_name"

#: Requests needed scale with ~800 anchors, not 27 -- see module docstring.
#: Set generously above the realistic estimate (~3,200 searches + up to
#: one document fetch per raw lead) so a real run fails LOUD on a genuine
#: runaway rather than being silently truncated by too-tight a cap.
MAX_REQUESTS = 50_000


def load_expanded_anchor_universe(
    *, hand_curated: dict[str, tuple[str, ...]] = ANCHOR_NAME_VARIANTS,
    proxy_csv: Path = RUSSELL1000_PROXY_CSV,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Merge round 4's hand-curated anchors with every Russell1000-proxy
    ticker not already covered. Returns (variants, provenance_by_ticker).

    Never overwrites a hand-curated entry: a ticker present in BOTH keeps
    its hand-curated, possibly-multi-variant name list, never replaced by
    the proxy file's single company-name column.
    """
    variants: dict[str, tuple[str, ...]] = dict(hand_curated)
    provenance: dict[str, str] = {t: PROVENANCE_HAND_CURATED for t in hand_curated}

    with proxy_csv.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ticker = (row.get("ticker") or "").strip().upper()
            company = (row.get("company") or "").strip()
            if not ticker or not company or ticker in variants:
                continue
            variants[ticker] = (company,)
            provenance[ticker] = PROVENANCE_RUSSELL1000_PROXY

    return variants, provenance


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--proxy-csv", type=Path, default=RUSSELL1000_PROXY_CSV)
    ap.add_argument("--out-name-search", type=Path, default=OUT_NAME_SEARCH)
    ap.add_argument("--out-linkage", type=Path, default=OUT_LINKAGE)
    ap.add_argument("--out-raw-hits", type=Path, default=OUT_RAW_HITS)
    a = ap.parse_args(argv)

    for p in (a.out_name_search, a.out_linkage, a.out_raw_hits):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are "
                  "never overwritten.", file=sys.stderr)
            return 1
    if not a.proxy_csv.is_file():
        print(f"REFUSED: {a.proxy_csv} does not exist", file=sys.stderr)
        return 1

    variants, provenance = load_expanded_anchor_universe(proxy_csv=a.proxy_csv)
    n_hand_curated = sum(1 for v in provenance.values()
                         if v == PROVENANCE_HAND_CURATED)
    n_proxy = sum(1 for v in provenance.values()
                 if v == PROVENANCE_RUSSELL1000_PROXY)
    n_variants = sum(len(v) for v in variants.values())
    n_queries = n_variants * len(CONCENTRATION_PHRASES)
    print(f"anchors: {len(variants)}  (hand_curated: {n_hand_curated}, "
          f"russell1000_proxy: {n_proxy})")
    print(f"name variants: {n_variants}   phrases: {len(CONCENTRATION_PHRASES)}")
    print(f"planned unscoped searches: {n_queries} "
          f"(up to {MAX_HITS_PER_QUERY} hits kept per search)")
    print("document-fetch count depends on how many distinct peer CIKs "
          "the searches surface -- unknown until run")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_agreements import AgreementSearchClient

    client = AgreementSearchClient(CONTACT, max_requests=MAX_REQUESTS)

    all_leads: list[dict[str, Any]] = []
    ordered = sorted(variants.items())
    for i, (anchor_ticker, name_variants) in enumerate(ordered, 1):
        leads = discover_leads(client, anchor_ticker, name_variants)
        for lead in leads:
            lead["anchor_variant_provenance"] = provenance[anchor_ticker]
        all_leads.extend(leads)
        if i % 25 == 0 or i == len(ordered):
            print(f"  [{i}/{len(ordered)}] {anchor_ticker:6s}: "
                  f"{len(leads)} peer CIK(s)  (requests so far: "
                  f"{client.requests_made}, total leads so far: "
                  f"{len(all_leads)})")

    print(f"\ntotal distinct (anchor, peer_cik) leads: {len(all_leads)}")

    verified = [verify_lead(client, lead) for lead in all_leads]
    n_confirmed = sum(1 for v in verified if v.get("filed_mention_confirmed"))
    print(f"confirmed (real, readable, concentration-shaped sentence): "
          f"{n_confirmed} / {len(verified)}")
    print(f"total requests made: {client.requests_made}")

    a.out_raw_hits.parent.mkdir(parents=True, exist_ok=True)
    a.out_raw_hits.write_text(json.dumps({
        "artifact": a.out_raw_hits.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "Round 4's exact mechanism (search_unscoped for [anchor name] "
            "AND [concentration tail-phrase], classify_context plus the "
            "percent-in-sentence check), run over round 4's 27 hand-"
            "curated anchors PLUS every one of the 788 Russell1000-proxy "
            "tickers not already among them -- see module docstring."),
        "proxy_csv": str(a.proxy_csv),
        "concentration_phrases": list(CONCENTRATION_PHRASES),
        "max_hits_per_query": MAX_HITS_PER_QUERY,
        "n_anchors": len(variants),
        "n_anchors_hand_curated": n_hand_curated,
        "n_anchors_russell1000_proxy": n_proxy,
        "requests_made": client.requests_made,
        "n_leads_discovered": len(verified),
        "n_confirmed": n_confirmed,
        "leads": verified,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out_raw_hits}")

    name_search_results: list[dict[str, Any]] = []
    linkage_edges: list[dict[str, Any]] = []
    for v in verified:
        if not v.get("filed_mention_confirmed"):
            continue
        cik = v["peer_cik"]
        ticker = client.ticker_for(cik)
        if ticker is not None and ticker.upper() == v["anchor_ticker"].upper():
            # Backstop against a self-match the CIK exclusion in
            # discover_leads should already have caught -- kept as a
            # second, independent check rather than trusting one alone.
            continue
        counterparty = v["peer_registrant_name"]
        name_search_results.append({
            "counterparty": counterparty,
            "anchor_ticker": v["anchor_ticker"],
            "registrant_cik": cik,
            "peer_ticker": ticker,
            "tradeable": ticker is not None,
        })
        linkage_edges.append({
            "anchor_ticker": v["anchor_ticker"],
            "counterparty_is_named": True,
            "named_counterparty": counterparty,
            "direction": "customer",
            "as_of_date": v["file_date"],
            "source": SOURCE_REVERSE_CONCENTRATION_SEARCH,
            "evidence_sentence": v["context"],
        })

    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
