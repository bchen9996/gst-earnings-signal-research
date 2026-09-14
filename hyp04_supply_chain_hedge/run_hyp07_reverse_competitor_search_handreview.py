#!/usr/bin/env python3
"""Hand review of the leads `run_hyp07_reverse_competitor_search.py`
confirmed live -- reading every sentence by hand, the same discipline
every prior round in this project applied to every hand-curated or
extracted candidate, before any of this touches a market-cap check.

=== SAME SHAPE AS run_hyp05_reverse_search_handreview.py, ONE REAL
    SIMPLIFICATION ===

A customer/supplier concentration sentence is genuinely ambiguous in
direction -- the same tail-phrase matches both "our sales TO [anchor]"
(peer is the anchor's supplier) and "our purchases FROM [anchor]" (peer
is the anchor's customer), which is why that module's `Decision` carries a
`corrected_direction` field. A competitor relationship is symmetric: once
a sentence is confirmed to genuinely describe the filer competing with the
anchor, there is no direction to get wrong. `Decision` here therefore
carries no `corrected_direction` -- every kept lead's `direction` is
simply `"competitor"`, fixed.

=== A REAL SCHEMA FIX THIS SET ALREADY NEEDED, DISCOVERED BY READING THE
    ACTUAL DATA, NOT ASSUMED FROM THE ROUND-4 TEMPLATE ===

Round 4's own `Decision(peer_cik, keep, corrected_direction, reason)`,
keyed by `peer_cik` ALONE, was safe only because no peer happened to
recur across two different anchors in that round's 17 confirmed leads.
HYP-07's own confirmed set breaks that immediately: FISERV INC (CIK
0000798354) genuinely appears as a confirmed competitor lead under THREE
different anchors (AAPL, GOOGL, SBUX -- the same boilerplate "newer
competitors include Alphabet, Amazon, Apple, ... Starbucks, ..." sentence
recurs near-verbatim across several fiscal years' filings). A `peer_cik`-
only key would silently collapse those three real, distinct anchor-pairs
down to one. `Decision` here is keyed by `(anchor_ticker, peer_cik)`
instead -- the same fix round 6's `run_hyp05_reverse_search_handreview_
scaled.py` already made for exactly this reason, reused in shape, not by
import (this module's own raw-hits shape and review categories differ).

=== A NEW FALSE-POSITIVE GENRE THIS DIRECTION CAN SURFACE, WATCHED FOR,
    NOT PRE-SOLVED ===

A sentence can use real `COMPETITOR_ANCHORS` phrasing while describing
market-share or industry structure rather than a bilateral claim that the
FILER itself competes with the anchor (HYP-05's own hand review already
found two sentences of exactly this shape under the customer/supplier
pipeline's percent-figure check -- Movie Gallery/GME's "no major player
holds more than a 20% share of the market", Carnival PLC/NCLH's "carry
approximately 87% of all global cruise guests" -- both genuinely
competitor-shaped, not concentration-shaped, sentences). No regex is
pre-built for this distinction here either -- it is read and decided
lead-by-lead below, exactly the way every prior round's false-positive
categories were discovered by reading real sentences, not predicted in
advance.

Run:  python -m hyp04_supply_chain_hedge.run_hyp07_reverse_competitor_search_handreview --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-13"

RAW_HITS_JSON = LSE / f"HYP07_REVERSE_COMPETITOR_SEARCH_RAW_HITS_{AS_OF}.json"
OUT_NAME_SEARCH = LSE / f"HYP07_PEER_NAME_SEARCH_REVERSE_COMPETITOR_SEARCH_HANDREVIEWED_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP07_CANDIDATE_LINKAGE_REVERSE_COMPETITOR_SEARCH_HANDREVIEWED_{AS_OF}.json"

SOURCE_REVERSE_COMPETITOR_SEARCH_HANDREVIEWED = (
    "EDGAR_10K_FULLTEXT_REVERSE_COMPETITOR_SEARCH_HAND_REVIEWED")


class Decision(NamedTuple):
    anchor_ticker: str
    peer_cik: str
    keep: bool
    reason: str


def _key(anchor_ticker: str, peer_cik: str) -> tuple[str, str]:
    return (anchor_ticker, peer_cik)


#: One entry per raw confirmed (anchor_ticker, peer_cik) lead, no
#: exceptions -- a test asserts this set's keys are EXACTLY the raw file's
#: confirmed set, so a future run producing a different lead set is
#: caught rather than silently reviewed against a stale decision list.
#: Keyed by (anchor_ticker, peer_cik), NOT peer_cik alone -- see module
#: docstring, "A REAL SCHEMA FIX".
#:
#: Every one of the 33 confirmed leads is a genuine, verified "our
#: competitors include ..." / "we compete with ..." disclosure -- none of
#: the plan's own anticipated market-share/industry-structure false-
#: positive genre (the Movie Gallery/Carnival PLC shape from HYP-05's own
#: hand review) actually recurred here; every sentence directly claims the
#: FILER itself competes with the anchor, not merely that the anchor
#: participates in some described market structure. Two entries name the
#: anchor via a SUBSIDIARY/business-unit, not the anchor's own core
#: business (Encore Wire vs. Cerrowire, a Marmon/Berkshire Hathaway
#: company; Omnicell vs. McKesson Automation Inc., a McKesson business
#: unit) -- kept, flagged, since the disclosure is still real and
#: "competitor" is the right schema category; whether the relationship is
#: economically close enough to produce a measurable reaction is exactly
#: what the statistical test is for, not something to prejudge in
#: curation (same reasoning this project has applied since round 4 to
#: large, expected-to-fail-on-size candidates kept "for completeness").
#: DJ Orthopedics/SYK's stored context was truncated by the 400-char
#: display limit before reaching the anchor's name -- verified by fetching
#: the real filing directly and confirming "our competitors include ...
#: Stryker Corporation" appears in full (see reason text).
HAND_REVIEW_DECISIONS: tuple[Decision, ...] = (
    Decision("AAPL", "0000798354", True,
            "Fiserv Inc: 'These newer competitors include ... Apple Inc. "
            "...' -- a named, specific competitor-list disclosure (2016 "
            "filing); recurs under GOOGL/SBUX too, from similar-year "
            "filings -- kept independently, same as any peer legitimately "
            "confirmed under more than one anchor."),
    Decision("ABBV", "0001496671", True,
            "Calithera Biosciences: 'Our principal competitors include "
            "Abbvie Inc., ...' among ~15 named oncology/biotech peers -- "
            "a genuine, specific competitor-naming disclosure, not a "
            "market-share statement."),
    Decision("ABBV", "0001787306", True,
            "Arcutis Biotherapeutics: 'our primary competitors include "
            "injected biologic therapies such as Humira, marketed by "
            "AbbVie Inc. ...' -- names AbbVie's specific competing drug "
            "in the psoriasis therapy market."),
    Decision("ADBE", "0001002638", True,
            "OpenText Corp: 'Our competitors include IBM, EMC, HP and "
            "Adobe Inc. ...' -- direct, specific."),
    Decision("AMZN", "0001506439", True,
            "SMTP, Inc.: 'Our principal competitors include ... larger "
            "companies such as Amazon.com, ...' -- direct, specific."),
    Decision("BKR", "0001603923", True,
            "Weatherford International: 'Our principal competitors "
            "include SLB, Halliburton, Baker Hughes, National Oilwell "
            "Varco, ChampionX and Expro Group Holdings.' -- direct, "
            "specific, oilfield-services peer group."),
    Decision("BRK-B", "0000850460", True,
            "Encore Wire Corp: 'primary competitors include Southwire "
            "..., Cerrowire (a Marmon/Berkshire Hathaway company), ...' "
            "-- INDIRECT: names a Berkshire SUBSIDIARY (Cerrowire, under "
            "Marmon Holdings), not Berkshire's own core business. Kept, "
            "flagged -- a real disclosure, 'competitor' is still the "
            "right schema category; the relationship's economic strength "
            "is for the statistical test, not curation, to judge."),
    Decision("BRK-B", "0000011544", True,
            "W. R. Berkley Corp: 'These competitors include Berkshire "
            "Hathaway, Employers Reinsurance, Transatlantic Reinsurance "
            "and Everest Reinsurance, ...' -- direct 'competitors include' "
            "clause naming Berkshire's own reinsurance business; the "
            "trailing market-share detail is supplementary color, not a "
            "substitute for the direct claim (distinguishing this from "
            "HYP-05's own Movie Gallery/Carnival PLC market-share false "
            "positives, which carried no direct competitor-naming clause "
            "at all)."),
    Decision("BRK-B", "0001141719", True,
            "Max Re Capital Ltd: 'Our worldwide reinsurance competitors "
            "include ACE Limited, ... Berkshire Hathaway, Inc., ...' -- "
            "direct, specific."),
    Decision("CTSH", "0000918581", True,
            "Ciber Inc: 'Our principal competitors include Accenture "
            "..., Cognizant Technology Solutions, ...' -- direct, "
            "specific."),
    Decision("CTSH", "0001040426", True,
            "Syntel Inc: 'The Company's most direct competitors include "
            "Cognizant, Infosys Technologies, Tata Consultancy Services "
            "and Wipro Technologies ...' -- small, specific list, strong "
            "direct claim ('most direct competitors')."),
    Decision("CTSH", "0001677703", True,
            "Conduent Inc: 'Our competitors include: Large multinational "
            "service providers such as ... Cognizant, ...' -- direct, "
            "specific."),
    Decision("DELL", "0001645590", True,
            "Hewlett Packard Enterprise: 'Our primary competitors include "
            "technology vendors such as Dell Technologies Inc. ...' -- "
            "direct, specific, DELL named first."),
    Decision("GOOGL", "0000798354", True,
            "Fiserv Inc, 2017 filing: 'These newer competitors include "
            "... Alphabet Inc., ...' -- same peer as the AAPL/SBUX "
            "entries, a DIFFERENT year's filing and a DIFFERENT anchor; "
            "kept independently -- see AAPL entry's note."),
    Decision("GPN", "0000721683", True,
            "Total System Services Inc (TSYS): 'Our primary competitors "
            "include First Data Corporation ..., Vantiv, Inc., Global "
            "Payments Inc. and Elavon, Inc. ...' -- direct, specific."),
    Decision("GPN", "0000896878", True,
            "Intuit Inc: 'we compete directly with ... many payment "
            "processors, including First Data Corporation, Elavon, "
            "Global Payments and FIS-Certegy.' -- direct, specific."),
    Decision("INTC", "0000918386", True,
            "QLogic Corp: 'we compete with Emulex Corporation, ... we "
            "also compete with Ethernet adapter suppliers Broadcom "
            "Corporation and Intel Corporation.' -- direct, specific "
            "market segment (FCoE/Ethernet adapters)."),
    Decision("JBL", "0000863436", True,
            "Benchmark Electronics Inc: 'Our competitors include "
            "Celestica, Inc., Flextronics International Ltd., Jabil "
            "Circuit, Inc., ...' -- direct, specific EMS peer group."),
    Decision("JBL", "0000315449", True,
            "UQM Technologies Inc: 'principal competitors include Jabil "
            "Circuit, Plexus, EFTC Corporation, Flextronics International, "
            "Solestica Corporation and Baldwin.' -- direct, specific."),
    Decision("LDOS", "0000785557", True,
            "DLH Holdings Corp: 'Our competitors include operating units "
            "within, among others: ... Leidos Holdings, Inc., ...' -- "
            "direct, specific, government-services peer group."),
    Decision("LDOS", "0001994624", True,
            "ScanTech AI Systems Inc: 'Our competitors include Leidos, "
            "Smiths Detection, Analogic Corporation and IDSS Corp.' -- "
            "small, specific list, security-screening technology niche."),
    Decision("MCK", "0001018833", True,
            "QuadraMed Corp: 'Some principal competitors include: ... "
            "McKesson Corporation, ...' -- direct, specific market "
            "segment (enterprise healthcare information systems)."),
    Decision("MCK", "0000926326", True,
            "Omnicell Inc: 'Other competitors include McKesson "
            "Automation Inc. (a business unit of McKesson Corporation), "
            "...' -- INDIRECT: names a McKesson BUSINESS UNIT, not "
            "McKesson's core pharmaceutical-distribution business. Kept, "
            "flagged -- same reasoning as the Encore Wire/BRK-B entry "
            "above."),
    Decision("NKE", "0001059763", True,
            "Adams Golf Inc: 'Our competitors include ... Nike, Inc. "
            "(Nike Golf), ...' -- Nike Golf is Nike's OWN product-line "
            "branding, same corporate entity and ticker (NOT a separate "
            "subsidiary the way Cerrowire/McKesson Automation are) -- a "
            "clean, direct mention, no flag needed."),
    Decision("QCOM", "0000772406", True,
            "Cirrus Logic Inc: 'Our primary competitors include AAC "
            "Technologies, ..., Qualcomm Incorporated, ...' -- direct, "
            "specific, audio/analog-semiconductor peer group."),
    Decision("SBUX", "0000798354", True,
            "Fiserv Inc, 2015 filing: 'These newer competitors include "
            "..., Starbucks Corporation, ...' -- third Fiserv occurrence "
            "(with AAPL/GOOGL), a third year's filing; kept "
            "independently -- see AAPL entry's note."),
    Decision("STZ", "0001350073", True,
            "Iconic Brands, Inc.: 'Our competitors include, but are not "
            "limited to, Gallo, Mionetto, Gruppo Campari, Constellation "
            "Brands, ...' -- direct, specific, small list."),
    Decision("SYK", "0001591165", True,
            "Medovex Corp: 'our principal competitors include device "
            "manufacturers Cosman Medical Inc., Stryker Corporation and "
            "Spembly Medical Systems.' -- direct, specific, very small "
            "list (3 companies) -- strong signal, and Medovex is a "
            "micro-cap."),
    Decision("SYK", "0001157972", True,
            "DJ Orthopedics Inc: stored context was truncated (400-char "
            "display limit) before reaching the match; fetched the real "
            "filing directly (accession 0001104659-04-007240) and "
            "confirmed the actual sentence in full: 'In the pain "
            "management products market, our competitors include "
            "Aircast, I-Flow Corp., Orthofix and Stryker Corporation.' -- "
            "direct, specific, genuine mention; the automated "
            "COMPETITOR_ANCHORS check that confirmed it was correct all "
            "along."),
    Decision("TTWO", "0001022080", True,
            "Midway Games Inc: 'These competitors include Activision, "
            "..., Take-Two Interactive Software, ...' -- direct, "
            "specific, video-game publisher peer group."),
    Decision("TTWO", "0001439404", True,
            "Zynga Inc: 'Some of these competitors include ... Take-Two "
            "Interactive Software, ...' -- direct, specific, large but "
            "genuine mobile/social-gaming competitive landscape."),
    Decision("TTWO", "0001823878", True,
            "PlayStudios, Inc.: 'Our primary competitors include "
            "Activision Blizzard ..., Take-Two Interactive Software, "
            "...' -- direct, specific."),
    Decision("TTWO", "0000712515", True,
            "Electronic Arts Inc: 'These competitors include ..., "
            "Take-Two Interactive, ...' -- direct, specific. EA itself is "
            "a mega-cap for essentially its whole trading history; kept "
            "for completeness, expected to fail the market-cap check on "
            "its own merits rather than being excluded here by "
            "assumption -- same precedent as Applied Materials/INTC in "
            "round 4."),
)


class HandReviewError(RuntimeError):
    pass


def apply_review(raw_leads: list[dict[str, Any]],
                 decisions: tuple[Decision, ...] = HAND_REVIEW_DECISIONS,
                 ) -> list[dict[str, Any]]:
    """Join the raw confirmed leads to their hand-review decision by
    (anchor_ticker, peer_cik). Refuses on any mismatch between the two
    sets rather than reviewing a lead this list never saw, or silently
    dropping one it did -- and, critically, never collapses two distinct
    anchor-pairs sharing one peer_cik into a single entry (see module
    docstring)."""
    confirmed = {_key(l["anchor_ticker"], l["peer_cik"]): l for l in raw_leads
                if l.get("filed_mention_confirmed")}
    decided = {_key(d.anchor_ticker, d.peer_cik): d for d in decisions}

    missing_decision = sorted(set(confirmed) - set(decided))
    if missing_decision:
        raise HandReviewError(
            f"{len(missing_decision)} confirmed lead(s) have no hand-review "
            f"decision: {missing_decision}. Every confirmed lead must be "
            "reviewed explicitly -- add a Decision for each before "
            "proceeding.")
    orphan_decision = sorted(set(decided) - set(confirmed))
    if orphan_decision:
        raise HandReviewError(
            f"{len(orphan_decision)} decision(s) name an (anchor_ticker, "
            f"peer_cik) pair not in the raw confirmed set: "
            f"{orphan_decision}. The raw hits file has changed since this "
            "review was written -- re-review rather than trusting a stale "
            "decision list.")

    out = []
    for key, lead in confirmed.items():
        d = decided[key]
        if not d.keep:
            continue
        out.append({**lead, "hand_review_reason": d.reason})
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-hits", type=Path, default=RAW_HITS_JSON)
    ap.add_argument("--out-name-search", type=Path, default=OUT_NAME_SEARCH)
    ap.add_argument("--out-linkage", type=Path, default=OUT_LINKAGE)
    ap.add_argument("--write", action="store_true",
                    help="actually write the two reviewed artifacts "
                         "(default prints the review and exits)")
    a = ap.parse_args(argv)

    if not a.raw_hits.is_file():
        print(f"REFUSED: no raw hits file at {a.raw_hits}", file=sys.stderr)
        return 1
    for p in (a.out_name_search, a.out_linkage):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are never "
                  "overwritten.", file=sys.stderr)
            return 1

    raw = json.loads(a.raw_hits.read_text(encoding="utf-8"))
    try:
        kept = apply_review(raw["leads"])
    except HandReviewError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1

    n_confirmed = sum(1 for l in raw["leads"] if l.get("filed_mention_confirmed"))
    n_rejected = n_confirmed - len(kept)
    print(f"raw confirmed leads: {n_confirmed}")
    print(f"hand-review rejected: {n_rejected}")
    print(f"hand-review kept: {len(kept)}")
    for k in kept:
        print(f"  {k['anchor_ticker']:6s} <-> {k['peer_registrant_name']:40s} "
              "[competitor]")

    if not a.write:
        print("\nDRY RUN (review only). Re-run with --write to create the "
              "two reviewed artifacts.")
        return 0

    from .edgar_agreements import AgreementSearchClient

    client = AgreementSearchClient("bchen9996 bchen9996@gmail.com",
                                   max_requests=len(kept) + 5)

    name_search_results = []
    linkage_edges = []
    for k in kept:
        ticker = client.ticker_for(k["peer_cik"])
        if ticker is not None and ticker.upper() == k["anchor_ticker"].upper():
            continue
        counterparty = k["peer_registrant_name"]
        name_search_results.append({
            "counterparty": counterparty,
            "anchor_ticker": k["anchor_ticker"],
            "registrant_cik": k["peer_cik"],
            "peer_ticker": ticker,
            "tradeable": ticker is not None,
        })
        linkage_edges.append({
            "anchor_ticker": k["anchor_ticker"],
            "counterparty_is_named": True,
            "named_counterparty": counterparty,
            "direction": "competitor",
            "as_of_date": k["file_date"],
            "source": SOURCE_REVERSE_COMPETITOR_SEARCH_HANDREVIEWED,
            "evidence_sentence": k["context"],
            "hand_review_reason": k["hand_review_reason"],
        })

    a.out_name_search.parent.mkdir(parents=True, exist_ok=True)
    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            f"The hand-reviewed subset of {RAW_HITS_JSON.name}'s confirmed "
            "leads. See run_hyp07_reverse_competitor_search_handreview.py's "
            "HAND_REVIEW_DECISIONS for the per-entry reasoning."),
        "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-07",
        "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")

    n_tradeable = sum(1 for r in name_search_results if r["tradeable"])
    print(f"\nhand-reviewed, kept: {len(name_search_results)}   "
          f"tradeable: {n_tradeable}")
    print("\nNext: python -m hyp04_supply_chain_hedge.run_hyp07_peer_market_cap "
          f'--name-search "{a.out_name_search}" --candidate-linkage '
          f'"{a.out_linkage}" --yes-run-live')
    return 0


if __name__ == "__main__":
    sys.exit(main())
