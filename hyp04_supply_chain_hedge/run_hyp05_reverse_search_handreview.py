#!/usr/bin/env python3
"""Hand review of the 17 leads `run_hyp05_reverse_concentration_search.py`
confirmed live on 2026-09-12 -- reading every sentence by hand, the same
discipline rounds 1-3 applied to every hand-curated candidate, before any
of this touches a market-cap check.

=== TWO REAL DEFECTS THIS PASS FOUND, NEITHER FIXED BY SILENTLY EDITING
    THE RAW OUTPUT ===

`HYP05_REVERSE_SEARCH_RAW_HITS_2026-09-12.json` is left exactly as the
script produced it -- dated artifacts are append-only, and "corrected,
not edited" is this project's own standing rule (see the 2026-09-10
ratify placeholder-name defect). This module is the correction, written
as its own reviewed, documented, testable artifact.

  1. FOUR FALSE POSITIVES survived `classify_context` and the percent-
     figure check because both guards operate on a SENTENCE, and a
     sentence can carry an unrelated percent figure while still passing:

       - PDL BIOPHARMA / ABBV: the matched sentence is corporate-renaming
         history (Abbott -> AbbVie Biotherapeutics) immediately followed
         by "2.875% Convertible Senior Notes" -- a BOND COUPON RATE, not
         a customer-concentration percentage. NEW false-signal category:
         a financial-instrument interest/coupon rate can satisfy the
         percent-figure check while being unrelated to any customer.
       - MOVIE GALLERY / GME and CARNIVAL PLC / NCLH: both are MARKET-
         SHARE-AMONG-COMPETITORS statements ("no major player holds more
         than a 20% share of the market", "carry approximately 87% of
         all global cruise guests") naming the anchor as a competitor,
         not a customer or supplier. NEW false-signal category: a
         market-share sentence can carry a percent figure and the
         anchor's name without being a concentration disclosure at all.
       - GLOBAL PAYMENT TECHNOLOGIES / GPN: a NAME-COLLISION, not a
         business-relationship false positive -- "Global Payments
         Technology Inc." (the FILER's own name) coincidentally contains
         the short anchor-name variant "Global Payments" the search used
         for GPN. The sentence is about joint-venture OWNERSHIP
         percentages, naming no relationship to Global Payments Inc. at
         all.

     None of the four ever reached `tradeable: true` in the raw output
     (all four CIKs carry no current ticker), so none would have reached
     a market-cap check even unreviewed -- but a false positive sitting
     unlabelled in a linkage artifact is a defect regardless of whether
     it happened to also fail a later, unrelated filter.

  2. TEN OF THE REMAINING THIRTEEN CARRY THE WRONG DIRECTION. The module
     hardcoded `direction: "customer"` for every hit, assuming every
     concentration sentence describes the FILER selling TO the anchor
     (which would make the filer the anchor's SUPPLIER -- direction
     naming the PEER's role relative to the ANCHOR, same convention
     `hand_curated_candidates.py` and the Foot Locker correction already
     use). Two disclosure genres share the same tail-phrases and look
     identical to a phrase search:

       Genre A -- "our SALES TO [anchor] / revenue FROM [anchor]
       accounted for X%": the peer SELLS to the anchor -> peer is the
       anchor's SUPPLIER.
       Genre B -- "our PURCHASES FROM [anchor]" or "[anchor], a
       supplier, accounted for X% of OUR sales" (a reseller describing
       what it resells): the peer BUYS FROM the anchor -> peer is the
       anchor's CUSTOMER.

     Read individually below. This is corrected here, once, by hand,
     rather than patched into the search module as a heuristic that
     would need its own false-positive/false-negative testing to trust
     at the same standard as everything else in this project.

=== ONE REAL RELATIONSHIP, WRONG SCHEMA, LEFT OUT ===

MICRON TECHNOLOGY / INTC's matched sentence describes IMFT/IMFS -- real,
well-documented joint-venture manufacturing entities Intel and Micron
co-owned -- by OWNERSHIP PERCENTAGE, not a customer/supplier/competitor
relationship. `curated_linkage.RELATIONSHIP_TYPES` has no "joint venture
partner" category, and inventing one for a single entry rather than
reusing the existing schema is exactly the kind of one-off this project
avoids. Left out, not miscoded into the nearest available label.

Run:  python -m hyp04_supply_chain_hedge.run_hyp05_reverse_search_handreview --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-12"

RAW_HITS_JSON = LSE / f"HYP05_REVERSE_SEARCH_RAW_HITS_{AS_OF}.json"
OUT_NAME_SEARCH = LSE / f"HYP05_PEER_NAME_SEARCH_REVERSE_SEARCH_HANDREVIEWED_{AS_OF}.json"
OUT_LINKAGE = LSE / f"HYP05_CANDIDATE_LINKAGE_REVERSE_SEARCH_HANDREVIEWED_{AS_OF}.json"

SOURCE_REVERSE_CONCENTRATION_SEARCH_HANDREVIEWED = (
    "EDGAR_10K_FULLTEXT_REVERSE_CONCENTRATION_SEARCH_HAND_REVIEWED")


class Decision(NamedTuple):
    peer_cik: str
    keep: bool
    #: Only meaningful when keep is True. Corrected relative to the raw
    #: output's hardcoded "customer" -- see module docstring, item 2.
    corrected_direction: Optional[str]
    reason: str


#: One entry per raw confirmed lead, no exceptions -- a test asserts this
#: list's peer_cik set is EXACTLY the raw file's confirmed set, so a future
#: run producing a different lead set is caught rather than silently
#: reviewed against a stale decision list.
HAND_REVIEW_DECISIONS: tuple[Decision, ...] = (
    Decision("0001441634", True, "supplier",
            "Avago Technologies/AAPL: 'our aggregate sales TO Apple Inc. "
            "... accounted for more than 10% of our net revenues' -- Avago "
            "sells to Apple, so Avago is Apple's supplier."),
    Decision("0001201663", True, "supplier",
            "Audience Inc/AAPL: 'Apple Inc. ... represented 46%, 75% and "
            "82% of our total revenue' -- Audience is an OEM component "
            "supplier to Apple."),
    Decision("0000882104", False, None,
            "PDL Biopharma/ABBV: FALSE POSITIVE -- corporate-renaming "
            "history sentence; the matched percent figure is a bond "
            "coupon rate ('2.875% Convertible Senior Notes'), unrelated "
            "to any customer concentration."),
    Decision("0001050377", True, "customer",
            "PC Connection/DELL: 'Product purchases from Ingram Micro, "
            "Inc., TD Synnex Corporation and Dell Inc. accounted for "
            "approximately ... 12% ... of our total product purchases' "
            "-- PC Connection BUYS from Dell (a reseller), so PC "
            "Connection is Dell's customer."),
    Decision("0001084991", True, "supplier",
            "Natural Gas Services Group/DVN: 'Sales and rental income to "
            "Devon Energy Production Inc. ... amounted to ... 21% ... of "
            "revenue' -- NGS sells/rents to Devon, so NGS is Devon's "
            "supplier."),
    Decision("0000925178", False, None,
            "Movie Gallery/GME: FALSE POSITIVE -- market-share-among-"
            "competitors statement ('no major player holds more than a "
            "20% share of the market'), not a customer-concentration "
            "disclosure."),
    Decision("0000946581", True, "supplier",
            "Take-Two Interactive/GOOGL: 'Sales to our five largest "
            "customers ... accounted for 79.6% of our net revenue, with "
            "Sony, Google, Apple, and Microsoft each accounting for more "
            "than 10.0%' -- Take-Two sells (distributes) to Google, so "
            "Take-Two is Google's supplier. Take-Two is itself one of "
            "this run's 27 anchor names; kept anyway -- nothing in this "
            "project's rules disqualifies a peer for also being used as "
            "an anchor elsewhere, and the eligibility check downstream "
            "evaluates it on its own merits."),
    Decision("0001094808", True, "supplier",
            "Vertro, Inc./GOOGL: 'search revenue from Google accounted "
            "for approximately 91% of our consolidated revenue' -- "
            "Vertro is paid by Google for search/ad syndication, so "
            "Vertro is Google's supplier."),
    Decision("0000933020", False, None,
            "Global Payment Technologies Inc/GPN: FALSE POSITIVE, NAME "
            "COLLISION -- the filer's OWN name ('Global Payments "
            "Technology Inc.') coincidentally contains the short "
            "anchor-name variant used for GPN ('Global Payments'). The "
            "sentence is joint-venture OWNERSHIP percentages, naming no "
            "relationship to Global Payments Inc. at all."),
    Decision("0000723125", False, None,
            "Micron Technology/INTC: real, well-documented relationship "
            "(IMFT/IMFS joint ventures) but the matched sentence is "
            "OWNERSHIP PERCENTAGE in a joint venture, not a customer/"
            "supplier/competitor relationship this schema has a category "
            "for -- see module docstring, 'ONE REAL RELATIONSHIP, WRONG "
            "SCHEMA'. Also already far above any plausible small-cap "
            "threshold throughout its trading history."),
    Decision("0000893162", True, "supplier",
            "Credence Systems Corp/INTC: 'Intel Corporation ... "
            "accounted for 15% and 25% of our net sales in fiscal years "
            "2006 and 2005' -- Credence sells test equipment to Intel, "
            "so Credence is Intel's supplier."),
    Decision("0000836106", True, "supplier",
            "Novellus Systems Inc/INTC: 'Samsung Electronics, Intel "
            "Corporation, Taiwan Semiconductor Manufacturing Company and "
            "International Business Machines Corporation accounted for "
            "17%, 11%, 11% and 10% of our net sales' -- Novellus sells "
            "semiconductor equipment to Intel, so Novellus is Intel's "
            "supplier."),
    Decision("0000006951", True, "supplier",
            "Applied Materials Inc/INTC: 'Net sales to Intel Corporation "
            "represented 12 percent of Applied's fiscal 2001 net sales' "
            "-- Applied sells to Intel, so Applied is Intel's supplier. "
            "Already a large-cap for essentially its whole trading "
            "history; kept for completeness, expected to fail the "
            "market-cap check on its own merits rather than being "
            "excluded here by assumption."),
    Decision("0001113481", True, "supplier",
            "The Medicines Company/MCK: 'AmerisourceBergen Drug "
            "Corporation, McKesson Corporation and Cardinal Health "
            "accounted for more than 88% of our revenues' -- Medicines "
            "Co sells its drug(s) through McKesson as a distributor, so "
            "Medicines Co is McKesson's supplier."),
    Decision("0001013786", True, "supplier",
            "Zones Inc/MSFT: 'Sales to one of the Company's customers, "
            "Microsoft Corporation, represented 14.7% and 28.7% of total "
            "sales' -- Zones explicitly calls Microsoft ITS customer, so "
            "Zones is Microsoft's supplier."),
    Decision("0001125259", False, None,
            "Carnival PLC/NCLH: FALSE POSITIVE -- market-share-among-"
            "competitors statement ('carry approximately 87% of all "
            "global cruise guests'), not a customer-concentration "
            "disclosure. Also already a large-cap throughout."),
    Decision("0000895447", True, "customer",
            "Shoe Carnival Inc (now Shoe Station Group Inc, renamed "
            "2026-06-11 per SEC formerNames -- same CIK, continuous "
            "filing history, a plain rename per this project's own "
            "lineage rule, not an acquisition)/NKE: 'two branded "
            "suppliers, Nike, Inc. and Skechers USA, Inc., collectively "
            "accounted for approximately 43% of our net sales' -- the "
            "filer explicitly calls Nike a supplier to ITSELF, so the "
            "peer (Shoe Carnival) is Nike's customer -- same direction "
            "as the Foot Locker/NKE correction in round 3."),
)


class HandReviewError(RuntimeError):
    pass


def apply_review(raw_leads: list[dict[str, Any]],
                 decisions: tuple[Decision, ...] = HAND_REVIEW_DECISIONS,
                 ) -> list[dict[str, Any]]:
    """Join the raw confirmed leads to their hand-review decision by peer
    CIK. Refuses on any mismatch between the two sets rather than
    reviewing a lead this list never saw, or silently dropping one it did."""
    confirmed = {l["peer_cik"]: l for l in raw_leads
                if l.get("filed_mention_confirmed")}
    decided = {d.peer_cik: d for d in decisions}

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
            f"{len(orphan_decision)} decision(s) name a peer_cik not in "
            f"the raw confirmed set: {orphan_decision}. The raw hits file "
            "has changed since this review was written -- re-review "
            "rather than trusting a stale decision list.")

    out = []
    for cik, lead in confirmed.items():
        d = decided[cik]
        if not d.keep:
            continue
        out.append({**lead, "corrected_direction": d.corrected_direction,
                   "hand_review_reason": d.reason})
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
    print(f"hand-review kept, direction-corrected: {len(kept)}")
    for k in kept:
        print(f"  {k['anchor_ticker']:6s} <-> {k['peer_registrant_name']:40s} "
              f"[{k['corrected_direction']}]")

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
            "direction": k["corrected_direction"],
            "as_of_date": k["file_date"],
            "source": SOURCE_REVERSE_CONCENTRATION_SEARCH_HANDREVIEWED,
            "evidence_sentence": k["context"],
            "hand_review_reason": k["hand_review_reason"],
        })

    a.out_name_search.parent.mkdir(parents=True, exist_ok=True)
    a.out_name_search.write_text(json.dumps({
        "artifact": a.out_name_search.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "The hand-reviewed subset of HYP05_REVERSE_SEARCH_RAW_HITS_"
            f"{AS_OF}.json's confirmed leads -- 4 false positives and 1 "
            "wrong-relationship-schema entry removed, direction corrected "
            "for 10 of the remaining 13. See run_hyp05_reverse_search_"
            "handreview.py's HAND_REVIEW_DECISIONS for the per-entry "
            "reasoning."),
        "results": name_search_results,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.out_linkage.write_text(json.dumps({
        "artifact": a.out_linkage.name, "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "edges": linkage_edges,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {a.out_name_search}")
    print(f"wrote {a.out_linkage}")

    n_tradeable = sum(1 for r in name_search_results if r["tradeable"])
    print(f"\nhand-reviewed, kept: {len(name_search_results)}   "
          f"tradeable: {n_tradeable}")
    print("\nNext: python -m hyp04_supply_chain_hedge.run_hyp05_peer_market_cap "
          f'--name-search "{a.out_name_search}" --candidate-linkage '
          f'"{a.out_linkage}" --yes-run-live')
    return 0


if __name__ == "__main__":
    sys.exit(main())
