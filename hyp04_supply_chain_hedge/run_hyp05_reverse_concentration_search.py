#!/usr/bin/env python3
"""LIVE. Reverse-direction EDGAR full-text search for HYP-05 peer
candidates.

Rounds 1-3 (this project's 751d9c5 / 3d7a240 / abf4527) proposed 96
candidate SMALL counterparty names from Claude's own recall and checked
whether a chosen large anchor's OWN 10-K mentioned them. That found
exactly one qualifying peer. The bottleneck was never which anchors were
searched -- it was that every candidate name had to occur to Claude first.

This module searches the other way: instead of a chosen anchor's own
filings for a guessed name, it searches the WHOLE EDGAR full-text corpus,
unscoped by CIK, for [an anchor's name] AND [a customer-concentration
tail-phrase] -- so a SMALL company's OWN 10-K, disclosing that a large
anchor accounts for a material share of ITS revenue, surfaces directly.
No guessing: `AgreementSearchClient.search_unscoped()` (added alongside
this module) confirmed live that AAPL + "of our net revenue" alone
surfaces Molex Inc, Rainmaker Systems Inc, and Avago Technologies among
141 hits -- none proposed in three rounds of hand curation.

=== WHY A CUSTOMER-CONCENTRATION TAIL-PHRASE, NOT A COMPETITOR PHRASE ===

ASC 280 requires disclosing when one customer accounts for a material
share of revenue, and naming that customer is standard practice, close to
formulaic: "[N]% of our net sales/net revenue/..." Competitor mentions
carry no equivalent disclosure mandate and are phrased far less
predictably -- exactly why the anchor-side search (rounds 1-3) depended so
heavily on Claude already knowing which name to type. Searching for a
mandatory, formulaic disclosure from the SMALL company's own side inverts
that dependency instead of just running the same dependency against more
anchors.

=== THE PHRASE LIST AND ANCHOR SET ARE DELIBERATELY BOUNDED, NOT CLAIMED
    EXHAUSTIVE ===

`CONCENTRATION_PHRASES` is four tail-phrases, not an enumeration of every
way a concentration disclosure might be worded ("of the Company's net
sales", "of consolidated net revenues", etc. are missed). `MAX_HITS_PER_
QUERY` caps each individual query to its top 5 hits rather than paging
through everything EDGAR's index returns. `ANCHOR_NAME_VARIANTS` covers
HYP-05's original 7 anchors plus the 20 members of HYP-01's `LOCKED_24_
ANCHORS` never mined this way (the 4 already in both lists appear once).
Every one of these bounds is disclosed here exactly the way "26
proposals," "42 more," and "28 more" were each disclosed as bounded,
non-exhaustive batches in the hand-curated rounds -- this run is a first,
bounded pass with a genuinely different mechanism, not a claim of
complete coverage.

=== NO ANCHOR IS PRE-FILTERED BY PLAUSIBILITY ===

Some of the 27 anchors (BRK-B, NCLH, UAL, GME) look like poor fits for a
physical supply chain on their face. They are searched anyway: deciding
in advance which large companies "plausibly" have a documented small-cap
supply chain is exactly the kind of judgment call that got this project's
own candidate list stuck at 96 hand-picked names. Let the systematic
search show which anchors yield nothing rather than deciding it up front.

=== VERIFICATION: THE SAME DISCIPLINE, PLUS ONE CHECK THIS DIRECTION NEEDS
    THAT THE OLD ONE DIDN'T ===

`classify_context()` (imported UNCHANGED from `run_hyp05_verify_candidates
.py`) rejects the same false-signal patterns rounds 1-3 found and fixed
(stock-index co-membership, biographical year ranges, board/officer
affiliation bios) -- generic "governance mention, not business
relationship" patterns, not specific to how the mention was found.

One check this direction needs that the old one didn't:
`_looks_like_concentration_sentence()` requires the extracted sentence
itself (not just the document) to carry a percent-style figure. The
search query ANDs the anchor's name with a concentration tail-phrase at
the DOCUMENT level, but `_sentence_around` extracts only the sentence
around the anchor's NAME -- if the tail-phrase that matched sits in a
DIFFERENT sentence (describing some other customer), the name's own
sentence could be an unrelated, coincidental mention. Requiring a percent
figure in that SAME sentence is the guard against exactly that gap.

=== TICKER RESOLUTION IS DIRECT, NOT VIA run_hyp05_peer_name_search.py ===

That module exists because the OLD flow started from a guessed NAME with
an unknown CIK, and SEC's `browse-edgar` company-name search can return
corrupted or genuinely-empty results for a real company (round 2's
`ticker_map_fallback_ciks()` finding). Every hit here already carries its
CIK directly from the search index -- `AgreementSearchClient.ticker_for()`
(added alongside `search_unscoped()`) resolves it from the SAME
`company_tickers.json` map `cik_for()` already uses, one fetch shared.
There is nothing for the name-search step to do here, so it is skipped,
not reimplemented.

=== OUTPUT: THE SAME TWO SHAPES run_hyp05_peer_market_cap.py ALREADY READS
===

Rather than inventing a third input shape, this writes a name-search-
shaped JSON and a candidate-linkage-shaped JSON matching exactly what
`run_hyp05_peer_market_cap._resolved_candidates()` already expects --
reuse, not a parallel path. A third artifact (`OUT_RAW_HITS`) keeps the
FULL record -- every lead attempted, confirmed or not -- since a "N
confirmed" count without the rejected majority visible is exactly the
failure mode rounds 1-3 spent three rounds guarding against.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp05_reverse_concentration_search
  python -m hyp04_supply_chain_hedge.run_hyp05_reverse_concentration_search --yes-run-live
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from .run_hyp05_verify_candidates import classify_context

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-12"

OUT_NAME_SEARCH = LSE / f"HYP05_PEER_NAME_SEARCH_REVERSE_SEARCH_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP05_CANDIDATE_LINKAGE_REVERSE_SEARCH_{AS_OF}.json"
OUT_RAW_HITS = LSE / f"HYP05_REVERSE_SEARCH_RAW_HITS_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"

SOURCE_REVERSE_CONCENTRATION_SEARCH = (
    "EDGAR_10K_FULLTEXT_REVERSE_CONCENTRATION_SEARCH_VERIFIED")

#: Deliberately small -- see module docstring, "THE PHRASE LIST AND
#: ANCHOR SET ARE DELIBERATELY BOUNDED".
CONCENTRATION_PHRASES: tuple[str, ...] = (
    "of our net sales", "of our net revenue", "of net sales",
    "of total revenue",
)

#: Top hits per (name variant, phrase) query kept for verification --
#: EDGAR's index may report far more; this is a bound, not the true count.
MAX_HITS_PER_QUERY = 5

#: One or more name-forms per anchor, as OTHER filers would plausibly
#: write it in prose -- deliberately NOT company_tickers.json's own
#: registrant "title" field, which is often an abbreviated/all-caps filer
#: identifier ("NVIDIA CORP") rather than natural prose ("NVIDIA
#: Corporation"). Covers HYP-05's original 7 anchors (already mined by
#: hand curation for a DIFFERENT candidate-name-guessing mechanism, not
#: redundant with this one) plus every LOCKED_24_ANCHORS member never
#: mined this way.
ANCHOR_NAME_VARIANTS: dict[str, tuple[str, ...]] = {
    "AAPL": ("Apple Inc.",),
    "ABBV": ("AbbVie Inc.",),
    "ADBE": ("Adobe Inc.", "Adobe Systems"),
    "AMZN": ("Amazon.com",),
    "BKR": ("Baker Hughes",),
    "BRK-B": ("Berkshire Hathaway",),
    "CTSH": ("Cognizant",),
    "DELL": ("Dell Inc.", "Dell Technologies"),
    "DVN": ("Devon Energy",),
    "GME": ("GameStop",),
    "GOOGL": ("Google", "Alphabet Inc."),
    "GPN": ("Global Payments",),
    "INTC": ("Intel Corporation",),
    "JBL": ("Jabil Inc.", "Jabil Circuit"),
    "LDOS": ("Leidos",),
    "MCK": ("McKesson Corporation",),
    "MSFT": ("Microsoft Corporation",),
    "NCLH": ("Norwegian Cruise Line",),
    "NKE": ("NIKE, Inc.", "Nike, Inc."),
    "NVDA": ("NVIDIA Corporation",),
    "QCOM": ("QUALCOMM Incorporated", "Qualcomm Incorporated"),
    "SBUX": ("Starbucks Corporation",),
    "STZ": ("Constellation Brands",),
    "SYK": ("Stryker Corporation",),
    "TSLA": ("Tesla, Inc.", "Tesla Motors"),
    "TTWO": ("Take-Two Interactive",),
    "UAL": ("United Airlines",),
}

#: The extracted sentence must carry a percent-style figure -- see module
#: docstring, "VERIFICATION". `\b` sits only after the "percent" branch:
#: "%" is itself a non-word character, so a boundary check immediately
#: after it can never match (no \w/\W transition exists there), which is
#: exactly the failure mode this comment exists to prevent someone from
#: reintroducing.
_PERCENT_PATTERN = re.compile(r"\d{1,3}(?:\.\d+)?\s*(?:%|percent\b)", re.I)


def _looks_like_concentration_sentence(sentence: str) -> bool:
    return bool(_PERCENT_PATTERN.search(sentence))


class ReverseSearchError(RuntimeError):
    pass


def discover_leads(client: Any, anchor_ticker: str,
                   name_variants: tuple[str, ...],
                   *, max_hits_per_query: int = MAX_HITS_PER_QUERY,
                   ) -> list[dict[str, Any]]:
    """Unscoped search for [name] AND [concentration phrase], over every
    name-variant x phrase combination for one anchor.

    Deduplicated by peer CIK, excluding the anchor's own CIK: the SAME
    peer can surface from several phrase variants and several filing
    years, and only the EARLIEST-dated hit is kept per peer, since that
    is the one whose point-in-time provenance a later eligibility check
    should cite.
    """
    anchor_cik = client.cik_for(anchor_ticker)
    by_peer_cik: dict[str, dict[str, Any]] = {}
    for name in name_variants:
        for phrase in CONCENTRATION_PHRASES:
            query = f'"{name}" "{phrase}"'
            hits = client.search_unscoped(query, forms="10-K")
            for h in hits[:max_hits_per_query]:
                ciks = h.get("ciks") or []
                peer_cik = next(
                    (c for c in ciks
                     if anchor_cik is None
                     or c.lstrip("0") != anchor_cik.lstrip("0")),
                    None)
                if peer_cik is None:
                    continue
                lead = {
                    "anchor_ticker": anchor_ticker,
                    "matched_name_variant": name,
                    "matched_phrase": phrase,
                    "peer_cik": peer_cik,
                    "peer_registrant_name": (h.get("display_names") or [""])[0],
                    "accession": h.get("adsh", ""),
                    "doc_id": h.get("_id", ""),
                    "file_date": h.get("file_date", ""),
                }
                existing = by_peer_cik.get(peer_cik)
                if existing is None or lead["file_date"] < existing["file_date"]:
                    by_peer_cik[peer_cik] = lead
    return list(by_peer_cik.values())


def verify_lead(client: Any, lead: dict[str, Any]) -> dict[str, Any]:
    """Fetch the document, locate the matched name, extract its sentence,
    and require BOTH that it survive `classify_context`'s known
    false-signal patterns AND that it look like a real concentration
    disclosure -- see module docstring, "VERIFICATION"."""
    from .edgar_agreements import _sentence_around

    out = dict(lead)
    doc_id = lead["doc_id"]
    doc_name = doc_id.split(":", 1)[1] if ":" in doc_id else None
    if not doc_name or not lead["accession"]:
        out.update(filed_mention_confirmed=False,
                   reason="hit carried no usable document reference")
        return out

    try:
        text = client.document(lead["peer_cik"], lead["accession"], doc_name)
    except Exception as exc:                              # noqa: BLE001
        out.update(filed_mention_confirmed=False,
                   reason=f"document fetch failed: {type(exc).__name__}: {exc}")
        return out

    name = lead["matched_name_variant"]
    idx = text.find(name)
    if idx == -1:
        idx = text.lower().find(name.lower())
    if idx == -1:
        out.update(filed_mention_confirmed=False,
                   reason="document fetched but the matched name could not "
                          "be located in the extracted text (often means "
                          "the indexed document is a PDF or other format "
                          "strip_markup cannot parse)")
        return out

    context = _sentence_around(text, idx, idx + len(name))
    rejection = classify_context(context)
    if rejection:
        out.update(filed_mention_confirmed=False,
                   context_rejected_as_non_relationship_evidence=True,
                   context=context[:400], reason=rejection)
        return out

    if not _looks_like_concentration_sentence(context):
        out.update(filed_mention_confirmed=False, context=context[:400],
                   reason="the anchor's own sentence carries no percent-"
                          "style figure -- the concentration phrase that "
                          "matched at the document level likely sits "
                          "elsewhere, describing a different customer")
        return out

    out.update(filed_mention_confirmed=True, context=context[:400])
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--out-name-search", type=Path, default=OUT_NAME_SEARCH)
    ap.add_argument("--out-linkage", type=Path, default=OUT_LINKAGE)
    ap.add_argument("--out-raw-hits", type=Path, default=OUT_RAW_HITS)
    a = ap.parse_args(argv)

    for p in (a.out_name_search, a.out_linkage, a.out_raw_hits):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are never "
                  "overwritten.", file=sys.stderr)
            return 1

    n_anchors = len(ANCHOR_NAME_VARIANTS)
    n_variants = sum(len(v) for v in ANCHOR_NAME_VARIANTS.values())
    n_queries = n_variants * len(CONCENTRATION_PHRASES)
    print(f"anchors: {n_anchors}   name variants: {n_variants}   "
          f"phrases: {len(CONCENTRATION_PHRASES)}")
    print(f"planned unscoped searches: {n_queries} "
          f"(up to {MAX_HITS_PER_QUERY} hits kept per search)")
    print("document-fetch count depends on how many distinct peer CIKs "
          "the searches surface -- unknown until run")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_agreements import AgreementSearchClient

    client = AgreementSearchClient(CONTACT, max_requests=3000)

    all_leads: list[dict[str, Any]] = []
    for anchor_ticker, variants in ANCHOR_NAME_VARIANTS.items():
        leads = discover_leads(client, anchor_ticker, variants)
        print(f"  {anchor_ticker:6s}: {len(leads)} distinct peer CIK(s) "
              f"discovered  (requests so far: {client.requests_made})")
        all_leads.extend(leads)

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
            "Every lead this run discovered and attempted to verify, "
            "confirmed or not -- the full record, not just the survivors."),
        "search_mechanism": (
            "EDGAR full-text search, UNSCOPED (no ciks restriction), for "
            "[anchor name variant] AND [customer-concentration tail-"
            "phrase], across every 10-K in the corpus. Inverse of rounds "
            "1-3's hand-curated, anchor-scoped search."),
        "concentration_phrases": list(CONCENTRATION_PHRASES),
        "max_hits_per_query": MAX_HITS_PER_QUERY,
        "anchor_name_variants": ANCHOR_NAME_VARIANTS,
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

    n_tradeable = sum(1 for r in name_search_results if r["tradeable"])
    print(f"\nconfirmed: {len(name_search_results)}   tradeable: {n_tradeable}")
    print("\nNext: python -m hyp04_supply_chain_hedge.run_hyp05_peer_market_cap "
          f'--name-search "{a.out_name_search}" --candidate-linkage '
          f'"{a.out_linkage}" --yes-run-live')
    return 0


if __name__ == "__main__":
    sys.exit(main())
