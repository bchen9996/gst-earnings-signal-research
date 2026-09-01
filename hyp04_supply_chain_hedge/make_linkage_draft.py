#!/usr/bin/env python3
"""Draft linkage rows for the owner to review. OFFLINE. Curates NOTHING.

Writes `HYP04_LINKAGE_ROWS_DRAFT_<date>.csv` in the curated schema, with every
field that can be DERIVED from the filings filled in, and every field that
requires a human left BLANK.

=== THE SAFETY PROPERTY, WHICH IS THE POINT ===

`confidence`, `date_confidence`, `curated_by`, `curated_date` and
`review_status` are all in `curated_linkage.REQUIRED_FIELDS`, and this module
leaves all five EMPTY. Measured against the generated file: 5 rows seen, 5
rejected, 0 edges usable. So if
the draft file were pointed at as a linkage map, `load_curated_linkage` rejects
every row for a missing required field and `edges` comes back empty -- which
`LinkageProvenance.uses_placeholder_linkage` then reports as placeholder,
keeping C5 shut.

**The draft cannot become production until a person fills the fields only a
person can fill.** That is not a convention; it is the loader's own validation,
and the suite asserts it against the real generated file.

=== WHY THESE FIELDS AND NOT OTHERS ===

DERIVED, because the filing says so:
  relationship_type   from the disclosure's `direction`
  source_type         these are all ASC 280 customer-concentration notes
  source_citation     filer, form, filing date, accession, concentration pct
  source_url          EDGAR's own index URL for that accession
  as_of_date          the EARLIEST filing that disclosed the relationship
  as_of_date_basis    "filing date of source" -- what that date actually is

LEFT BLANK, because no derivation can supply them:
  confidence          how much the curator believes the edge
  date_confidence     whether the earliest-disclosure date is really the floor
  curated_by          who is making the claim
  curated_date        when they made it
  review_status       whether it has been reviewed

The lineage verdict and the incremental event count go in `notes_caveats`, so
the reviewer sees the evidence and the stake without either being mistaken for
a curated judgement.

=== WHAT IS DELIBERATELY EXCLUDED ===

Rows whose (anchor, peer) pair is ALREADY in the curated map. Two candidates
were MCK -> CVS at as_of dates LATER than the existing 2013-05-07 edge; they
add nothing, and `load_curated_linkage` rejects duplicate anchor-peer pairs
anyway. Including them would put rows in front of a reviewer that cannot help
and cannot load.

Rows that did not resolve to a ticker, and rows whose lineage audit did not
come back CONTINUOUS. Both are unfinished questions, not draft answers.

  python -m hyp04_supply_chain_hedge.make_linkage_draft --build
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .artifacts import newest_in
from .curated_linkage import (
    EXPECTED_HEADERS,
    RELATIONSHIP_TYPES,
    SOURCE_TYPES,
)
from .peer_lineage import VERDICT_CONTINUOUS

LSE = Path("Live Signal Engine")
AS_OF = "2026-08-31"
OUT_CSV = LSE / f"HYP04_LINKAGE_ROWS_DRAFT_{AS_OF}.csv"

CURATED_MAP = LSE / "HYP04_Linkage_Map_v1.0.csv"

#: The only source_type these rows can honestly claim. Every candidate comes
#: from an ASC 280-10-50-42 customer-concentration disclosure in a 10-K, which
#: is what the review queue extracts and nothing else.
SOURCE_TYPE = "10-K Customer Concentration Note"
AS_OF_BASIS = "filing date of source"

#: Disclosure `direction` -> curated relationship_type. A `customer` direction
#: means the NAMED COUNTERPARTY is a customer of the filer, so from the
#: anchor's point of view the peer is a direct customer.
DIRECTION_TO_RELATIONSHIP = {
    "customer": "direct_customer",
    "supplier": "direct_supplier",
}

#: Fields a human must supply. Left blank on every draft row, which is what
#: makes the file fail closed. All five are in REQUIRED_FIELDS, so the loader
#: rejects any row that is missing one. See the module docstring.
OWNER_FIELDS = ("confidence", "date_confidence", "curated_by", "curated_date",
                "review_status")

INDEX_URL = ("https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/"
             "{acc}-index.htm")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows(p: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.open(p, encoding="utf-8", newline="")))


def _existing_pairs(map_path: Path) -> set[tuple[str, str]]:
    if not map_path.is_file():
        return set()
    return {((r.get("anchor_ticker") or "").strip().upper(),
             (r.get("peer_ticker") or "").strip().upper())
            for r in _rows(map_path)}


def _disclosure_for(queue: dict[str, Any], anchor: str, accession: str,
                    counterparty: str) -> Optional[dict[str, Any]]:
    """The specific disclosure record naming this counterparty in this filing.

    A filing carries several disclosures -- an unnamed aggregate plus one per
    named customer -- so the row must be matched by NAME, not taken as the
    first. Taking the first would attach another company's concentration
    percentage to this edge.
    """
    for t in queue.get("tickers") or []:
        if str(t.get("ticker", "")).upper() != anchor:
            continue
        for f in t.get("per_filing") or []:
            if f.get("accession") != accession:
                continue
            for d in f.get("disclosures") or []:
                if (d.get("named_counterparty") or "") == counterparty:
                    return dict(d, _form=f.get("form"),
                                _filing_date=f.get("filing_date"))
    return None


def build(*, out_csv: Path = OUT_CSV, map_path: Path = CURATED_MAP,
          ) -> list[str]:
    refusals: list[str] = []
    if out_csv.exists():
        refusals.append(f"{out_csv.name} already exists. Refusing to overwrite "
                        "a dated artifact -- delete it deliberately first.")

    wl = newest_in(LSE, "HYP04_PEER_CURATION_WORKLIST_*.csv")
    aud = newest_in(LSE, "HYP04_PEER_LINEAGE_AUDIT_*.json")
    q = newest_in(LSE, "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_*.json")
    if wl is None:
        refusals.append("no peer-curation worklist on disk")
    if aud is None:
        refusals.append("no peer-lineage audit on disk")
    if q is None:
        refusals.append("no EDGAR review queue on disk")
    if refusals:
        return refusals

    worklist = _rows(wl)
    audit = json.loads(aud.read_text(encoding="utf-8"))
    queue = json.loads(q.read_text(encoding="utf-8"))

    # A CONTINUOUS lineage verdict is required. Anything else is an open
    # question, and an open question is not a draft answer.
    clean: set[tuple[str, str, str]] = {
        (a.get("anchor_ticker", ""), a.get("peer_ticker", ""),
         a.get("as_of_date", ""))
        for a in audit.get("assessments") or []
        if a.get("verdict") == VERDICT_CONTINUOUS}

    already = _existing_pairs(map_path)
    out: list[dict[str, str]] = []
    skipped: list[str] = []

    for r in worklist:
        anchor = (r.get("anchor_ticker") or "").strip().upper()
        peer = (r.get("candidate_peer_ticker") or "").strip().upper()
        name = r.get("counterparty_name_as_filed") or ""
        as_of = r.get("earliest_disclosing_filing_date") or ""
        acc = r.get("earliest_accession") or ""

        if not peer:
            continue                       # unresolved: an open question
        if (anchor, peer, as_of) not in clean:
            skipped.append(f"{anchor}->{peer}: lineage verdict is not "
                           f"{VERDICT_CONTINUOUS}")
            continue
        if (anchor, peer) in already:
            skipped.append(f"{anchor}->{peer}: already in the curated map; "
                           "this candidate's as_of is later and adds nothing")
            continue

        d = _disclosure_for(queue, anchor, acc, name)
        if d is None:
            skipped.append(f"{anchor}->{peer}: no disclosure record naming "
                           f"{name!r} in {acc}")
            continue

        rel = DIRECTION_TO_RELATIONSHIP.get(str(d.get("direction") or ""))
        if rel not in RELATIONSHIP_TYPES:
            skipped.append(f"{anchor}->{peer}: direction "
                           f"{d.get('direction')!r} maps to no curated "
                           "relationship_type")
            continue

        pct = d.get("concentration_pct")
        basis = d.get("concentration_basis") or "unstated basis"
        cik = str(d.get("reporting_cik") or "").lstrip("0")
        url = ("" if not (cik and acc) else
               INDEX_URL.format(cik=cik, nodash=acc.replace("-", ""), acc=acc))

        lineage = next(
            (a for a in audit.get("assessments") or []
             if a.get("anchor_ticker") == anchor
             and a.get("peer_ticker") == peer
             and a.get("as_of_date") == as_of), {})

        out.append({
            "anchor_ticker": anchor,
            "peer_ticker": peer,
            "relationship_type": rel,
            "relationship_direction_notes": (
                f"{name} is a CUSTOMER of {anchor} per the filer's own "
                f"concentration disclosure ({pct}% of {basis}). Direction "
                f"taken from the disclosure, not inferred."),
            "confidence": "",                       # OWNER
            "source_type": SOURCE_TYPE,
            "source_citation": (
                f"{anchor} Form {d.get('_form') or '10-K'} filed "
                f"{d.get('_filing_date') or as_of}, accession {acc}, ASC 280 "
                f"customer-concentration disclosure naming {name} at {pct}% "
                f"of {basis}."),
            "source_url": url,
            "as_of_date": as_of,
            "as_of_date_basis": AS_OF_BASIS,
            "date_confidence": "",                  # OWNER
            "notes_caveats": (
                "DRAFT, UNVALIDATED, MACHINE-PREPARED. Derived from the EDGAR "
                "review queue; no human has reviewed this edge. as_of_date is "
                "the EARLIEST filing in the walk that names this counterparty "
                "-- found, not proven to be the floor. LINEAGE: SEC's record "
                f"shows the registrant filing on {as_of} as "
                f"{lineage.get('registrant_name_at_as_of')!r} (CIK "
                f"{lineage.get('registrant_cik')}, filing since "
                f"{lineage.get('registrant_first_filing')}), which matches the "
                "disclosed name -- this removes ONE way of being wrong and "
                "does not establish the relationship. A merger that preserved "
                "the name and the registrant would look identical here; check "
                "it the way Caremark RX and OfficeMax were checked. STAKE: "
                f"{r.get('incremental_anchor_events')} anchor events beyond "
                "what the curated map already reaches."),
            "curated_by": "",                       # OWNER
            "curated_date": "",                     # OWNER
            "review_status": "",                    # OWNER
        })

    if not out:
        return ["no candidate produced a draft row: " + "; ".join(skipped)]

    out.sort(key=lambda r: (r["anchor_ticker"], r["peer_ticker"]))
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(EXPECTED_HEADERS),
                           lineterminator="\n")
        w.writeheader()
        for r in out:
            w.writerow(r)

    print(f"wrote {out_csv}  ({len(out)} draft row(s))")
    for r in out:
        print(f"  {r['anchor_ticker']:5} -> {r['peer_ticker']:5} "
              f"as_of {r['as_of_date']}  {r['relationship_type']}")
    if skipped:
        print("\nnot drafted:")
        for s in skipped:
            print("  - " + s)
    print("\nEVERY ROW IS INERT until you fill " + ", ".join(OWNER_FIELDS) + ".")
    print(f"All {len(OWNER_FIELDS)} are required fields, so "
          "load_curated_linkage rejects each row while they are blank, and C5 "
          "stays shut.")
    print(f"\nsources: {wl.name} ({_sha256(wl)[:16]}), {aud.name}, {q.name}")
    return []


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Draft linkage rows for owner review. Offline; curates "
                    "nothing; every row is inert until a human completes it.")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args(argv)
    if not a.build:
        ap.print_help()
        return 2
    refusals = build()
    if refusals:
        print("REFUSED:", file=sys.stderr)
        for r in refusals:
            print("  - " + r, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
