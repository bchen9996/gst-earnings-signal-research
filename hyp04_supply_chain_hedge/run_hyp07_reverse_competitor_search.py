#!/usr/bin/env python3
"""LIVE. Reverse-direction EDGAR full-text search for HYP-07 competitor-
relationship peer candidates.

Mirrors `run_hyp05_reverse_concentration_search.py` structurally --
searching the WHOLE EDGAR full-text corpus, unscoped by CIK, for [an
anchor's name] AND [a phrase], so a SMALL company's OWN 10-K surfaces
directly rather than depending on the anchor's own filing naming it -- but
is NOT that module modified: the phrase set and the sentence-verification
check are both swapped for competitor language, a different data shape
from customer-concentration disclosures.

=== WHY THIS PIVOT, NOT MORE FORWARD EXTRACTION ===

HYP-05's own first pass already ran `extract_competitor_edges_from_text()`
(calibrated, wired into `extract_for_universe()`) against anchors' OWN
filings -- both a latest-10-K pass and a full historical multi-year walk --
and diagnosed a real structural bias: it surfaces only a filer's most
PROMINENT named rivals (AMD, Samsung, TSMC, Siemens Energy, ...), which
then fail the <$2B market-cap eligibility test (`HYP05_PEER_UNIVERSE_
2026-09-12.md`, "the historical walk" section). HYP-07's own Step 0 (`run_
hyp07_existing_competitor_edges_name_search.py` / `run_hyp07_peer_market_
cap.py`) confirmed this again directly: of 52 already-extracted competitor
names, only 2 resolved to an evaluable ticker, both dead ends (GlobalFoundries
too large at $25-30B; Shutterstock's disclosure date postdates every
available ADBE anchor event). This module is the SAME pivot that rescued
customer/supplier discovery in round 4: search from the SMALL company's own
voice, not the large anchor's.

=== PHRASES: LITERAL INSTANTIATIONS OF THE REAL, CALIBRATED REGEX ===

`edgar_linkage.COMPETITOR_ANCHORS` is three regex patterns, calibrated
against 24 real anchor filings (0 false positives) for FORWARD extraction.
`COMPETITOR_PHRASES` below are literal, quotable instantiations of those
same patterns -- deliberately bounded, not an enumeration of every possible
competitor-disclosure phrasing (same "bounded, not exhaustive" discipline
`CONCENTRATION_PHRASES` is declared under in the customer/supplier module).

=== ANCHOR SET: THE SAME 27 ROUND 4 USED, FOR DIRECT COMPARABILITY ===

`ANCHOR_NAME_VARIANTS` is imported UNCHANGED from `run_hyp05_reverse_
concentration_search.py` -- not redefined here. The 788-anchor scaled
version (mirroring round 6) is an explicit next step, not this pass.

=== VERIFICATION: THE REAL REGEX, NOT A NEW HEURISTIC ===

`_looks_like_concentration_sentence()`'s percent-figure check has no
competitor-disclosure analog (no equivalent mandatory, formulaic
disclosure exists). `_looks_like_competitor_sentence()` instead requires
the extracted sentence to match one of the three real `COMPETITOR_ANCHORS`
patterns directly -- stronger grounding than a new heuristic, since these
are the exact patterns the forward extractor was already calibrated
against real filings with. `classify_context()` (imported unchanged from
`run_hyp05_verify_candidates.py`) is reused for the same generic
governance-mention false signals (stock-index co-membership, biographical,
board/officer) this project's every prior round has found.

Ticker resolution stays direct (`AgreementSearchClient.ticker_for()`), same
reasoning as round 4's own module: every hit already carries its CIK from
the search index.

Output: the same three-artifact shape (name-search JSON, candidate-linkage
JSON, full raw-hits record) `run_hyp05_reverse_concentration_search.py`
already established, so `run_hyp07_peer_market_cap.py` reads it without a
new input shape being invented. `direction` is always "competitor" -- no
customer/supplier ambiguity to resolve at this stage.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp07_reverse_competitor_search
  python -m hyp04_supply_chain_hedge.run_hyp07_reverse_competitor_search --yes-run-live
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from .edgar_linkage import COMPETITOR_ANCHORS
from .run_hyp05_reverse_concentration_search import ANCHOR_NAME_VARIANTS
from .run_hyp05_verify_candidates import classify_context

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"

OUT_NAME_SEARCH = LSE / f"HYP07_PEER_NAME_SEARCH_REVERSE_COMPETITOR_SEARCH_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP07_CANDIDATE_LINKAGE_REVERSE_COMPETITOR_SEARCH_{AS_OF}.json"
OUT_RAW_HITS = LSE / f"HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"

SOURCE_REVERSE_COMPETITOR_SEARCH = (
    "EDGAR_10K_FULLTEXT_REVERSE_COMPETITOR_SEARCH_VERIFIED")

#: Literal instantiations of edgar_linkage.COMPETITOR_ANCHORS's three real,
#: calibrated regex patterns -- deliberately small, see module docstring.
COMPETITOR_PHRASES: tuple[str, ...] = (
    "principal competitors include",
    "primary competitors include",
    "our competitors include",
    "we compete with",
    "we compete directly with",
)

#: Top hits per (name variant, phrase) query kept for verification -- same
#: bound as the customer/supplier module, same reasoning.
MAX_HITS_PER_QUERY = 5


def _looks_like_competitor_sentence(sentence: str) -> bool:
    """The sentence must match one of the real, calibrated COMPETITOR_
    ANCHORS patterns -- not merely that the document-level query matched
    somewhere else in the document."""
    return any(re.search(pattern, sentence, re.I)
              for pattern, _label in COMPETITOR_ANCHORS)


def _looks_like_self_match(registrant_name: str, name_variant: str) -> bool:
    """A name-based backstop against the anchor's own filing surfacing as
    its own "competitor" lead, for when cik_for(anchor_ticker) cannot
    resolve a CIK to exclude by in the first place.

    A REAL, verified gap, not a hypothetical one: of the 788-anchor scaled
    search's own anchor universe, 7 tickers (AVB, EQR, GTLS, JHG, NSA,
    TMHC, WBS) have NO entry at all in SEC's own company_tickers.json
    ticker map -- confirmed directly against the live map, not assumed.
    That silently disables BOTH discover_leads's own CIK-based exclusion
    below (anchor_cik is None makes the `or` vacuously True) AND main()'s
    ticker_for()-based backstop (built from the exact same map, so it has
    the exact same blind spot). Since a company's own 10-K naturally
    contains both its own name and, very often, a sentence describing its
    own competitors, an anchor with this gap searching for "[its own name]"
    AND "[competitor phrase]" can trivially match its OWN filing.

    Deliberately conservative: fires only when the registrant's own SEC
    display name contains the EXACT name variant that was searched for. An
    unrelated company happening to be registered under a name that
    contains the anchor's own full name-plus-suffix string ("Apple Inc.",
    not just "Apple") is vanishingly rare, so this does not risk excluding
    a genuine, differently-named competitor -- see
    test_hyp04_supply_chain_hedge_reverse_competitor_search.py for cases
    checked."""
    return name_variant.strip().upper() in registrant_name.strip().upper()


class ReverseSearchError(RuntimeError):
    pass


def discover_leads(client: Any, anchor_ticker: str,
                   name_variants: tuple[str, ...],
                   *, max_hits_per_query: int = MAX_HITS_PER_QUERY,
                   ) -> list[dict[str, Any]]:
    """Unscoped search for [name] AND [competitor phrase], over every
    name-variant x phrase combination for one anchor. Same dedup-by-peer-
    CIK, earliest-hit-kept discipline as the customer/supplier module --
    none of that logic is concentration-specific."""
    anchor_cik = client.cik_for(anchor_ticker)
    by_peer_cik: dict[str, dict[str, Any]] = {}
    for name in name_variants:
        for phrase in COMPETITOR_PHRASES:
            query = f'"{name}" "{phrase}"'
            hits = client.search_unscoped(query, forms="10-K")
            for h in hits[:max_hits_per_query]:
                ciks = h.get("ciks") or []
                names = h.get("display_names") or []
                # ciks and display_names are PARALLEL arrays -- a jointly-
                # filed document (parent + subsidiaries as co-registrants)
                # can have more than one entry in each, at matching
                # indices. Resolving peer_cik by scanning ciks but then
                # reading peer_registrant_name from names[0] unconditionally
                # was a REAL bug: whenever the anchor was co-registrant #0
                # and the real peer was co-registrant #1+, the self-match
                # check below compared the ANCHOR's own name (names[0])
                # instead of the peer's, wrongly dropping a genuine lead --
                # found by an independent review pass, verified against
                # this exact index-misalignment before being trusted.
                peer_idx = next(
                    (i for i, c in enumerate(ciks)
                     if anchor_cik is None
                     or c.lstrip("0") != anchor_cik.lstrip("0")),
                    None)
                if peer_idx is None:
                    continue
                peer_cik = ciks[peer_idx]
                peer_registrant_name = (
                    names[peer_idx] if peer_idx < len(names)
                    else (names[0] if names else ""))
                if _looks_like_self_match(peer_registrant_name, name):
                    continue
                lead = {
                    "anchor_ticker": anchor_ticker,
                    "matched_name_variant": name,
                    "matched_phrase": phrase,
                    "peer_cik": peer_cik,
                    "peer_registrant_name": peer_registrant_name,
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
    false-signal patterns AND that it match a real, calibrated competitor
    pattern."""
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

    if not _looks_like_competitor_sentence(context):
        out.update(filed_mention_confirmed=False, context=context[:400],
                   reason="the anchor's own sentence matches none of the "
                          "three calibrated COMPETITOR_ANCHORS patterns -- "
                          "the phrase that matched at the document level "
                          "likely sits elsewhere, describing something "
                          "else")
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
    n_queries = n_variants * len(COMPETITOR_PHRASES)
    print(f"anchors: {n_anchors}   name variants: {n_variants}   "
          f"phrases: {len(COMPETITOR_PHRASES)}")
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
    print(f"confirmed (real, readable, competitor-shaped sentence): "
          f"{n_confirmed} / {len(verified)}")
    print(f"total requests made: {client.requests_made}")

    a.out_raw_hits.parent.mkdir(parents=True, exist_ok=True)
    a.out_raw_hits.write_text(json.dumps({
        "artifact": a.out_raw_hits.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            "Every lead this run discovered and attempted to verify, "
            "confirmed or not -- the full record, not just the survivors."),
        "search_mechanism": (
            "EDGAR full-text search, UNSCOPED (no ciks restriction), for "
            "[anchor name variant] AND [competitor-language phrase], "
            "across every 10-K in the corpus -- the same reverse-search "
            "pivot that rescued customer/supplier discovery in round 4, "
            "applied to competitor language instead."),
        "competitor_phrases": list(COMPETITOR_PHRASES),
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
            "direction": "competitor",
            "as_of_date": v["file_date"],
            "source": SOURCE_REVERSE_COMPETITOR_SEARCH,
            "evidence_sentence": v["context"],
        })

    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")

    n_tradeable = sum(1 for r in name_search_results if r["tradeable"])
    print(f"\nconfirmed: {len(name_search_results)}   tradeable: {n_tradeable}")
    print("\nNext: python -m hyp04_supply_chain_hedge.run_hyp07_reverse_"
          "competitor_search_handreview")
    return 0


if __name__ == "__main__":
    sys.exit(main())
