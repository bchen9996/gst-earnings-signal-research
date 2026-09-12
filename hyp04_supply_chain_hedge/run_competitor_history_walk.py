#!/usr/bin/env python3
"""Walk a company's 10-K history for the EARLIEST disclosure of a named
competitor/supplier -- the competitor/supplier-context analogue of
`run_linkage_history.py` (which does the same walk for the ASC 280
concentration path only; `extract_competitor_edges_from_text` was never
included there). NOT A TEST. NOT RUN BY CI. MAKES REAL SEC REQUESTS.

=== WHY THIS EXISTS ===

HYP-05's first real curation pass (2026-09-12, HYP05_PEER_UNIVERSE_2026-09-
12.md) used only each anchor's LATEST 10-K, because that is all `extract_
for_universe()` ever reads. Every candidate it surfaced (CVS Health, AMD,
Samsung, Micron, GlobalFoundries, SMIC, UMC) was a large, well-known
company -- unsurprising, since a single recent snapshot tends to surface
whichever counterparties a filer's CURRENT Competition/Business section
happens to name, and those are usually its biggest, most prominent rivals
or customers. A company's disclosed competitors and customers change
across years and filings; reaching further back is how a thinner,
less-obvious candidate pool gets found, exactly the reasoning already
established by `run_linkage_history.py` for the ASC 280 path ("dated to
the earliest filing that discloses them, each may span the whole window").

=== WHY A NEW MODULE, NOT AN EDIT TO run_linkage_history.py ===

That module's own `build_report()` names its `source` as "ASC 280
concentration disclosures" specifically, and its dated FULL51 artifacts
already on disk were produced by exactly that walk. Changing `walk_ticker`
to also run a second extractor risks that already-relied-upon output for
a capability those artifacts never claimed. This module reuses the same
resilience pattern deliberately (per-filing try/except so one unreachable
document does not truncate the whole walk; a request-cap hit preserves
whatever was already found rather than discarding it) but is otherwise
independent -- provenance noted, not silently duplicated logic pretending
to be original.

Usage:
    python -m hyp04_supply_chain_hedge.run_competitor_history_walk \\
        --contact "Name email@realdomain.com" --max-requests 300
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .edgar_linkage import (
    ANNUAL_REPORT_FORMS,
    CONTACT_REQUIRED_MESSAGE,
    LSE,
    EdgarClient,
    EdgarContactError,
    FilingCache,
    extract_competitor_edges_from_text,
)

# HYP-04's real, verified anchor set (see peer_selection.py's docstring for
# the correction and the four independent sources confirming it) -- NOT
# LOCKED_24_ANCHORS.
DEFAULT_TICKERS = ("ADBE", "CTSH", "INTC", "JBL", "MCK", "NKE", "NVDA")


@dataclass
class TickerCompetitorHistory:
    """Every 10-K examined for one filer's competitor/supplier-context
    prose, newest first."""

    ticker: str
    cik: Optional[str] = None
    filings_on_record: int = 0
    filings_examined: int = 0
    error: Optional[str] = None
    per_filing: list[dict[str, Any]] = field(default_factory=list)
    stopped_early_reason: Optional[str] = None
    filings_failed: list[dict[str, Any]] = field(default_factory=list)
    no_annual_reports_reason: Optional[str] = None

    def named_counterparties(self) -> dict[str, dict[str, Any]]:
        """(counterparty, direction) -> earliest/latest filing that names
        it. The EARLIEST entry is the operative one -- same reasoning as
        run_linkage_history.py's own method of the same name."""
        out: dict[tuple, dict[str, Any]] = {}
        for f in self.per_filing:
            for d in f["disclosures"]:
                key = (d["named_counterparty"], d["direction"])
                rec = out.setdefault(key, {
                    "counterparty": d["named_counterparty"],
                    "direction": d["direction"],
                    "pattern": d["pattern"],
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
        return {f"{k[0]}|{k[1]}": v for k, v in out.items()}


def walk_ticker(client: EdgarClient, ticker: str, *,
                max_filings: Optional[int] = None) -> TickerCompetitorHistory:
    """Walk one ticker's 10-Ks newest -> oldest for competitor/supplier
    prose. MAKES REAL SEC REQUESTS."""
    h = TickerCompetitorHistory(ticker=ticker)
    try:
        cik = client.cik_for(ticker)
        if cik is None:
            h.error = "no CIK found for ticker"
            return h
        h.cik = cik

        filings = client.all_10ks(cik)
        h.filings_on_record = len(filings)
        if not filings:
            h.no_annual_reports_reason = (
                f"ticker {ticker} resolved to CIK {cik}, which has no annual "
                f"report of any accepted form "
                f"({', '.join(sorted(ANNUAL_REPORT_FORMS))}). A resolution "
                "failure, not a finding -- see run_linkage_history.py's own "
                "note on this, measured on XOM.")
            h.error = h.no_annual_reports_reason
            return h
        if max_filings is not None:
            filings = filings[:max_filings]

        for f in filings:
            try:
                text, src = client.filing_text_with_source(
                    cik, f["accession"], f["primary_document"])
            except Exception as e:              # noqa: BLE001 -- recorded
                if "request cap" in str(e):
                    raise
                h.filings_failed.append({
                    "filing_date": f["filing_date"],
                    "accession": f["accession"],
                    "error": f"{type(e).__name__}: {str(e)[:160]}",
                })
                continue
            edges = extract_competitor_edges_from_text(
                text, ticker=ticker, cik=cik, filing_date=f["filing_date"],
                accession=f["accession"], form=f["form"])
            h.per_filing.append({
                "filing_date": f["filing_date"],
                "report_date": f.get("report_date"),
                "accession": f["accession"],
                "form": f["form"],
                "edges_found": len(edges),
                "source_path": src,
                "disclosures": [e.as_dict() for e in edges],
            })
            h.filings_examined += 1
    except Exception as e:                      # noqa: BLE001 -- recorded, not raised
        h.stopped_early_reason = f"{type(e).__name__}: {str(e)[:200]}"
    return h


def build_report(histories: list[TickerCompetitorHistory], *,
                 contact_used: bool, requests_made: int) -> dict[str, Any]:
    return {
        "artifact": "HYP05_COMPETITOR_HISTORY_WALK.json",
        "source": ("EDGAR 10-K history walk (competitor/supplier-context "
                    "prose, EDGAR_10K_COMPETITION_SECTION_PROSE) -- the "
                    "analogue of HYP04_EDGAR_LINKAGE_HISTORY.json for the "
                    "ASC 280 path, which this walk does not cover"),
        "is_production_linkage_map": False,
        "status": "CANDIDATE_REVIEW_QUEUE",
        "not_a_replacement": (
            "A review queue for a human, not a linkage map. No row here is "
            "curated, and none is promoted automatically. Every claim "
            "carries an accession number so it can be checked against the "
            "filing."),
        "what_the_earliest_date_means": (
            "The earliest filing that NAMES the counterparty, which is the "
            "claim as_of_date makes. Not evidence the relationship began "
            "then -- only that it was publicly disclosed by then."),
        "why_earliest_matters": (
            "Peer eligibility (peer_selection.py) counts a candidate only "
            "for anchor events at or after its as_of_date. The earliest "
            "disclosing filing maximises how many real anchor events "
            "(HYP04_ANCHOR_SHOCKS_2026-08-31.csv) a candidate can be "
            "evaluated against."),
        "contact_supplied": contact_used,
        "requests_made": requests_made,
        "tickers": [
            {
                "ticker": h.ticker,
                "cik": h.cik,
                "filings_on_record": h.filings_on_record,
                "filings_examined": h.filings_examined,
                "filings_failed": h.filings_failed,
                "stopped_early_reason": h.stopped_early_reason,
                "error": h.error,
                "no_annual_reports_reason": h.no_annual_reports_reason,
                "named_counterparties": list(h.named_counterparties().values()),
                "per_filing": h.per_filing,
            }
            for h in histories
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Walk 10-K history for the earliest disclosure of a "
                    "named competitor/supplier. MAKES REAL SEC REQUESTS.")
    ap.add_argument("--contact", default=None,
                    help="REQUIRED. 'Name email@realdomain.com' per SEC "
                         "fair-access policy.")
    ap.add_argument("--tickers", default=",".join(DEFAULT_TICKERS),
                    help="comma-separated. Default is HYP-04's real, "
                         "verified 7-ticker anchor set.")
    ap.add_argument("--max-requests", type=int, default=300,
                    help="hard cap on SEC requests; the walk stops and "
                         "reports.")
    ap.add_argument("--max-filings", type=int, default=None,
                    help="optional per-ticker cap on 10-Ks examined")
    ap.add_argument("--out", type=Path,
                    default=LSE / "HYP05_COMPETITOR_HISTORY_WALK.json")
    ap.add_argument("--cache-dir", type=Path, default=Path(".edgar_cache"))
    a = ap.parse_args(argv)

    if not a.contact:
        print(CONTACT_REQUIRED_MESSAGE, file=sys.stderr)
        return 2

    try:
        client = EdgarClient(a.contact, cache=FilingCache(a.cache_dir),
                             max_requests=a.max_requests)
    except EdgarContactError as e:
        print(str(e), file=sys.stderr)
        return 2

    tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    histories: list[TickerCompetitorHistory] = []
    try:
        for t in tickers:
            print(f"walking {t}...")
            h = walk_ticker(client, t, max_filings=a.max_filings)
            histories.append(h)
            print(f"  {h.filings_examined}/{h.filings_on_record} filings "
                  f"examined, {len(h.named_counterparties())} distinct "
                  f"(counterparty, direction) pairs found"
                  + (f", stopped early: {h.stopped_early_reason}"
                     if h.stopped_early_reason else ""))
    except Exception as e:                      # noqa: BLE001
        print(f"WALK STOPPED: {type(e).__name__}: {e}", file=sys.stderr)

    report = build_report(histories, contact_used=bool(a.contact),
                          requests_made=client.requests_made)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\nrequests made: {client.requests_made}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
