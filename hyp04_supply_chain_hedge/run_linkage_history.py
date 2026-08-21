#!/usr/bin/env python3
"""Walk a company's 10-K history to find the EARLIEST disclosure of a relationship.

NOT A TEST. NOT RUN BY CI. MAKES REAL SEC REQUESTS. Deliberately named off the
`test_*` discovery pattern, for the same reason the live audit runners and the
registry generator are: it reaches the network and must only run when a human
decides it should.

=== WHY THIS EXISTS ===

The candidate extractor answers "what does this company disclose NOW?" and
stamps each edge with the filing date of the newest 10-K. Under HYP-04's
peer-eligibility rule an edge counts only for anchor events STRICTLY AFTER its
as_of_date, so an edge dated from the most recent filing covers almost no
history -- even when the relationship it describes is a decade old.

Concretely, from the committed 2026-08-18 run: McKesson names CVS Health as its
largest customer with an as_of_date of 2026-05-08, and Packaging Corp names ODP
with 2026-02-26. Both relationships long predate those filings. Dated that way
each edge is nearly worthless to a sample that needs roughly eight quarters of
history; dated to the earliest filing that discloses them, each may span the
whole window.

So this walks 10-Ks backwards and reports, per named counterparty, the OLDEST
filing that still discloses the relationship -- and the filing before that,
where the disclosure stops.

=== WHAT IT DOES NOT DO ===

It curates nothing and writes no linkage row. Output is a REVIEW QUEUE: a
report a human reads before deciding what to put in the curated map, with
accession numbers so every claim can be checked against the filing itself. Like
the extractor it feeds, it is a CANDIDATE source and is never promoted
automatically.

It also does not prove a relationship began on the earliest date found. It
proves the relationship was PUBLICLY DISCLOSED on that date, which is the claim
the as_of_date field actually makes and the only one the filing supports. An
earlier start date needs a different source.

Usage:
    python -m hyp04_supply_chain_hedge.run_linkage_history \\
        --contact "Name email@realdomain.com" \\
        --tickers MCK,PKG --max-requests 120
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .edgar_linkage import (
    CONTACT_REQUIRED_MESSAGE,
    LSE,
    EdgarClient,
    LinkageEdge,
    extract_edges_from_text,
)


@dataclass
class TickerHistory:
    """Every 10-K examined for one filer, newest first."""

    ticker: str
    cik: Optional[str] = None
    filings_on_record: int = 0
    filings_examined: int = 0
    error: Optional[str] = None
    per_filing: list[dict[str, Any]] = field(default_factory=list)
    stopped_early_reason: Optional[str] = None

    def named_counterparties(self) -> dict[str, dict[str, Any]]:
        """counterparty -> earliest/latest filing that names it.

        The EARLIEST entry is the operative one: it is the as_of_date that
        maximises how many anchor events the edge can serve.
        """
        out: dict[str, dict[str, Any]] = {}
        for f in self.per_filing:
            for name in f["named_counterparties"]:
                rec = out.setdefault(name, {
                    "counterparty": name,
                    "earliest_filing_date": f["filing_date"],
                    "earliest_accession": f["accession"],
                    "latest_filing_date": f["filing_date"],
                    "latest_accession": f["accession"],
                    "filings_naming_it": 0,
                })
                rec["filings_naming_it"] += 1
                if f["filing_date"] < rec["earliest_filing_date"]:
                    rec["earliest_filing_date"] = f["filing_date"]
                    rec["earliest_accession"] = f["accession"]
                if f["filing_date"] > rec["latest_filing_date"]:
                    rec["latest_filing_date"] = f["filing_date"]
                    rec["latest_accession"] = f["accession"]
        return out


def walk_ticker(client: EdgarClient, ticker: str, *,
                max_filings: Optional[int] = None) -> TickerHistory:
    """Walk one ticker's 10-Ks newest -> oldest. MAKES REAL SEC REQUESTS."""
    h = TickerHistory(ticker=ticker)
    try:
        cik = client.cik_for(ticker)
        if cik is None:
            h.error = "no CIK found for ticker"
            return h
        h.cik = cik

        filings = client.all_10ks(cik)
        h.filings_on_record = len(filings)
        if max_filings is not None:
            filings = filings[:max_filings]

        for f in filings:
            text = client.filing_text(cik, f["accession"], f["primary_document"])
            edges, no_conc = extract_edges_from_text(
                text, ticker=ticker, cik=cik, filing_date=f["filing_date"],
                accession=f["accession"], form=f["form"])
            named = sorted({e.named_counterparty for e in edges
                            if e.counterparty_is_named and e.named_counterparty})
            h.per_filing.append({
                "filing_date": f["filing_date"],
                "accession": f["accession"],
                "edges_found": len(edges),
                "named_counterparties": named,
                "explicit_no_concentration": bool(no_conc),
            })
            h.filings_examined += 1
    except Exception as e:                      # noqa: BLE001 -- recorded, not raised
        # A cap hit or a transport failure must not discard the filings already
        # walked: a partial history is still a usable review queue, provided it
        # says plainly that it is partial.
        h.stopped_early_reason = f"{type(e).__name__}: {str(e)[:200]}"
    return h


def build_report(histories: list[TickerHistory], *, contact_used: bool,
                 requests_made: int) -> dict[str, Any]:
    return {
        "artifact": "HYP04_EDGAR_LINKAGE_HISTORY.json",
        "source": "EDGAR 10-K history walk (ASC 280 concentration disclosures)",
        "is_production_linkage_map": False,
        "status": "CANDIDATE_REVIEW_QUEUE",
        "not_a_replacement": (
            "A review queue for a human, not a linkage map. No row here is "
            "curated, and none is promoted automatically. Every claim carries "
            "an accession number so it can be checked against the filing."),
        "what_the_earliest_date_means": (
            "The earliest filing that DISCLOSES the relationship, which is the "
            "claim as_of_date makes. It is not evidence the relationship began "
            "then -- only that it was publicly known by then. An earlier start "
            "date requires a different source."),
        "why_earliest_matters": (
            "Peer eligibility counts an edge only for anchor events strictly "
            "after its as_of_date. The earliest disclosing filing therefore "
            "maximises the events an edge can serve; the newest one, which the "
            "candidate extractor records, minimises it."),
        "contact_supplied": contact_used,
        "requests_made": requests_made,
        "tickers": [
            {
                "ticker": h.ticker,
                "cik": h.cik,
                "filings_on_record": h.filings_on_record,
                "filings_examined": h.filings_examined,
                "stopped_early_reason": h.stopped_early_reason,
                "error": h.error,
                "named_counterparties": list(h.named_counterparties().values()),
                "per_filing": h.per_filing,
            }
            for h in histories
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Walk 10-K history for the earliest disclosure of a named "
                    "counterparty. MAKES REAL SEC REQUESTS.")
    ap.add_argument("--contact", default=None,
                    help="REQUIRED. 'Name email@realdomain.com' per SEC fair-access policy.")
    ap.add_argument("--tickers", default="MCK,PKG",
                    help="comma-separated. Default is the two anchors whose "
                         "committed candidate edges NAME a counterparty.")
    ap.add_argument("--max-requests", type=int, default=150,
                    help="hard cap on SEC requests; the walk stops and reports.")
    ap.add_argument("--max-filings", type=int, default=None,
                    help="optional per-ticker cap on 10-Ks examined")
    ap.add_argument("--out", type=Path,
                    default=LSE / "HYP04_EDGAR_LINKAGE_HISTORY.json")
    a = ap.parse_args(argv)

    if not a.contact:
        print(CONTACT_REQUIRED_MESSAGE, file=sys.stderr)
        return 2

    tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    client = EdgarClient(a.contact, max_requests=a.max_requests)

    print(f"EDGAR 10-K history walk over {len(tickers)} ticker(s): {tickers}")
    print(f"  request cap: {a.max_requests}")

    histories = [walk_ticker(client, t, max_filings=a.max_filings) for t in tickers]

    print("\n=== EARLIEST NAMED DISCLOSURE ===")
    for h in histories:
        print(f"\n{h.ticker}  (10-Ks on record: {h.filings_on_record}, "
              f"examined: {h.filings_examined})")
        if h.error:
            print(f"  ERROR: {h.error}")
        if h.stopped_early_reason:
            print(f"  STOPPED EARLY: {h.stopped_early_reason}")
        named = h.named_counterparties()
        if not named:
            print("  no named counterparty in any filing examined")
        for rec in named.values():
            print(f"  {rec['counterparty']}")
            print(f"     earliest: {rec['earliest_filing_date']}  "
                  f"{rec['earliest_accession']}")
            print(f"     latest:   {rec['latest_filing_date']}  "
                  f"{rec['latest_accession']}")
            print(f"     filings naming it: {rec['filings_naming_it']}")

    report = build_report(histories, contact_used=True,
                          requests_made=client.requests_made)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\nWrote: {a.out}")
    print(f"Requests made: {client.requests_made}")
    print("\nCANDIDATE REVIEW QUEUE. Not the production linkage map, and no row "
          "is curated by this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
