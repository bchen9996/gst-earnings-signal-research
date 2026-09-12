#!/usr/bin/env python3
"""LIVE. Verify HYP-05's hand-curated candidate PROPOSALS (`hand_curated_
candidates.py`) against EDGAR's own full-text search before any of them
can reach the existing name-resolution / market-cap pipeline.

=== WHY THIS EXISTS ===

Every candidate in `hand_curated_candidates.py` is an assertion from
general/training knowledge, not something extracted from a filing read
this session -- a different kind of claim than everything else in this
project. `run_hyp05_peer_name_search.py`'s EDGAR company search only
confirms a NAME resolves to a real, continuously-filing registrant; it
says nothing about whether that registrant is actually a counterparty of
the anchor claimed. This script closes that gap the same way the rest of
the project closes every other one: by checking a real, citable filing
before trusting the claim, not after.

For each proposal, it searches efts.sec.gov's full-text index for the
counterparty's name RESTRICTED TO THE ANCHOR'S OWN 10-K filings (reusing
`AgreementSearchClient` from `edgar_agreements.py` unchanged -- the same
full-text-search-then-fetch client already built and calibrated for
SOURCE B, repurposed here for a name lookup instead of an agreement-verb
lookup). Only a real hit -- with a real accession number, filing date,
and the actual sentence the name appears in -- lets a candidate through
to `HYP05_CANDIDATE_LINKAGE_HAND_CURATED_<date>.json`, in the same edges
shape `run_hyp05_peer_name_search.py` and `run_hyp05_peer_market_cap.py`
already read.

A confirmed hit means the anchor's own 10-K names this company. It does
NOT independently confirm the specific `direction` (competitor/supplier/
customer) hand-classified in `hand_curated_candidates.py` -- that stays
my classification. The captured `context` sentence is written into both
output artifacts specifically so that classification can be read and
judged, not just trusted.

STAGED, same discipline as every other live script in this project:
without --yes-run-live it prints the proposal list and the request
ceiling, then exits.

  python -m hyp04_supply_chain_hedge.run_hyp05_verify_candidates
  python -m hyp04_supply_chain_hedge.run_hyp05_verify_candidates --yes-run-live
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .hand_curated_candidates import PROPOSED_CANDIDATES

LSE = Path("Live Signal Engine")
CONTACT = "bchen9996 bchen9996@gmail.com"

SOURCE_HAND_CURATED = "EDGAR_10K_FULLTEXT_SEARCH_HAND_CURATED_VERIFIED"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--out-verification", type=Path,
                    default=LSE / "HYP05_HAND_CURATED_VERIFICATION_2026-09-12.json")
    ap.add_argument("--out-linkage", type=Path,
                    default=LSE / "HYP05_CANDIDATE_LINKAGE_HAND_CURATED_2026-09-12.json")
    a = ap.parse_args(argv)

    print(f"proposed candidates: {len(PROPOSED_CANDIDATES)}")
    for c in PROPOSED_CANDIDATES:
        print(f"  {c.anchor_ticker:5s} <-> {c.counterparty_name:28s} "
              f"[{c.direction}]  {c.basis}")
    print(f"\nrequest ceiling: up to {len(PROPOSED_CANDIDATES)} full-text "
          f"searches + up to {len(PROPOSED_CANDIDATES)} document fetches "
          "(one per confirmed hit)")

    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_agreements import AgreementSearchClient, _sentence_around

    client = AgreementSearchClient(CONTACT)

    verifications: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for c in PROPOSED_CANDIDATES:
        key = f"{c.anchor_ticker}:{c.counterparty_name}"
        cik = client.cik_for(c.anchor_ticker)
        if cik is None:
            verifications.append({**c._asdict(),
                                   "filed_mention_confirmed": False,
                                   "reason": "no CIK for anchor ticker"})
            continue

        try:
            hits = client.search(cik, f'"{c.counterparty_name}"', forms="10-K")
        except Exception as exc:                            # noqa: BLE001
            errors[key] = f"{type(exc).__name__}: {exc}"
            verifications.append({**c._asdict(),
                                   "filed_mention_confirmed": False,
                                   "reason": f"search failed: {errors[key]}"})
            continue

        if not hits:
            verifications.append({**c._asdict(),
                                   "filed_mention_confirmed": False,
                                   "reason": "no full-text hit in this "
                                             "anchor's 10-K filings"})
            continue

        # A hit from efts.sec.gov's own index means the SEC's index found
        # the name somewhere in this filing -- but that index covers text
        # this project's own document fetcher cannot always reproduce (old
        # pre-2001 filings with non-standard archive paths; 10-Ks whose
        # indexed document is an "unofficial pdf" copy, which strip_markup
        # -- built for HTML -- cannot parse). Without a context sentence
        # actually containing the name, there is no independent evidence
        # of what the filing really says, so this must NOT be reported as
        # confirmed. A real index hit with unreadable context is a
        # DIFFERENT, weaker finding than a hit with readable context, and
        # is recorded as such rather than collapsed into either bucket.
        earliest = sorted(hits, key=lambda h: h.get("file_date", ""))[0]
        doc_id = earliest.get("_id") or ""
        doc_name = doc_id.split(":")[-1] if ":" in doc_id else None
        context = ""
        fetch_note = ""
        if doc_name:
            try:
                text = client.document(cik, earliest["adsh"], doc_name)
                idx = text.find(c.counterparty_name)
                if idx == -1:
                    idx = text.lower().find(c.counterparty_name.lower())
                if idx != -1:
                    context = _sentence_around(
                        text, idx, idx + len(c.counterparty_name))
                else:
                    fetch_note = ("document fetched but the name could not "
                                   "be located in the extracted text (often "
                                   "means the indexed document is a PDF or "
                                   "other format strip_markup cannot parse)")
            except Exception as exc:                        # noqa: BLE001
                errors[f"{key}:document"] = f"{type(exc).__name__}: {exc}"
                fetch_note = f"document fetch failed: {errors[f'{key}:document']}"

        if context:
            verifications.append({
                **c._asdict(),
                "filed_mention_confirmed": True,
                "accession": earliest["adsh"],
                "filing_date": earliest.get("file_date", ""),
                "form": earliest.get("form", "10-K"),
                "context": context[:400],
                "all_hits": len(hits),
            })
            edges.append({
                "reporting_company": c.anchor_ticker,
                "reporting_cik": cik,
                "named_counterparty": c.counterparty_name,
                "counterparty_is_named": True,
                "direction": c.direction,
                "concentration_pct": None,
                "as_of_date": earliest.get("file_date", ""),
                "accession": earliest["adsh"],
                "form": earliest.get("form", "10-K"),
                "source": SOURCE_HAND_CURATED,
                "pattern": "hand_curated_proposal_fulltext_confirmed",
                "context": context[:400],
            })
        else:
            verifications.append({
                **c._asdict(),
                "filed_mention_confirmed": False,
                "search_hit_found_but_context_unreadable": True,
                "accession": earliest["adsh"],
                "filing_date": earliest.get("file_date", ""),
                "all_hits": len(hits),
                "reason": fetch_note or "context extraction failed",
            })

    confirmed = sum(1 for v in verifications if v["filed_mention_confirmed"])
    print(f"\nrequests made: {client.requests_made}")
    print(f"filed_mention_confirmed: {confirmed} of {len(PROPOSED_CANDIDATES)}")
    for v in verifications:
        status = "CONFIRMED" if v["filed_mention_confirmed"] else "unconfirmed"
        print(f"  {v['anchor_ticker']:5s} <-> {v['counterparty_name']:28s} "
              f"[{status}]")

    verification_payload = {
        "artifact": a.out_verification.name,
        "what_this_is": (
            "Whether each hand-proposed HYP-05 candidate (see "
            "hand_curated_candidates.py -- proposals from general "
            "knowledge, not extracted from a filing) actually appears, by "
            "name, in a real 10-K filed by its proposed anchor -- WITH a "
            "readable sentence of context actually confirming it, not just "
            "a raw search-index hit. `filed_mention_confirmed: true` "
            "requires both: efts.sec.gov reported a hit AND this script "
            "independently located the name inside the fetched document "
            "text. A hit with no readable context (common for pre-2001 "
            "filings with non-standard archive paths, or 10-Ks whose "
            "indexed document is a PDF that strip_markup cannot parse) is "
            "marked `search_hit_found_but_context_unreadable: true` and "
            "kept OUT of filed_mention_confirmed and out of the linkage "
            "edges file -- a real index hit is not the same claim as a "
            "readable, checkable sentence. Confirmation of the NAME does "
            "NOT independently confirm the claimed direction (competitor/"
            "supplier/customer) -- read `context` for that."),
        "what_this_is_not": (
            "Curation. Confirmation here only gates entry into the "
            "existing name-resolution + point-in-time market-cap pipeline "
            "(run_hyp05_peer_name_search.py, run_hyp05_peer_market_cap."
            "py) -- no edge here is a production linkage-map row."),
        "unconfirmed_is_not_a_negative": (
            "A candidate with no full-text hit may still be a real "
            "relationship that was simply never named in a 10-K, or "
            "named using different wording than proposed here. "
            "filed_mention_confirmed: false means unconfirmed by this "
            "evidence standard, not disproven."),
        "proposed_count": len(PROPOSED_CANDIDATES),
        "confirmed_count": confirmed,
        "requests_made": client.requests_made,
        "errors": errors,
        "verifications": verifications,
    }
    a.out_verification.parent.mkdir(parents=True, exist_ok=True)
    a.out_verification.write_text(
        json.dumps(verification_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"\nwrote {a.out_verification}")

    linkage_payload = {
        "artifact": a.out_linkage.name,
        "source": SOURCE_HAND_CURATED,
        "is_production_linkage_map": False,
        "status": "CANDIDATE_REVIEW_QUEUE",
        "derived_from": a.out_verification.name,
        "note": (
            "Only proposals with filed_mention_confirmed=true in the "
            "verification artifact above. Direction is still a hand "
            "classification, not independently verified -- see that "
            "artifact's context field."),
        "edges": edges,
    }
    a.out_linkage.write_text(
        json.dumps(linkage_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"wrote {a.out_linkage}  ({len(edges)} confirmed edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
