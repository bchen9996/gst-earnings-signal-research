#!/usr/bin/env python3
"""Calibrate `extract_competitor_edges_from_text()` against REAL 10-K text.

That extractor (added this session, in `edgar_linkage.py`) has never been run
against anything but synthetic fixtures. This script is the one deliberate
exception to this pass's offline discipline: it MAKES REAL SEC REQUESTS,
pulls a handful of real "Item 1 Business" filings, runs the extractor on
their actual text, and writes what it found -- including matched context
snippets -- so a human can read and judge each one.

This is NOT a test (no assertion here can know in advance what a real filing
says) and it is NOT curation (nothing it finds is added to any linkage map).
It only produces the evidence a calibration judgment gets made from. Same
"characterize accurately, don't just pass/fail" discipline as HYP-04's own
extraction-quality finding (FAILED_EXTRACTION_QUALITY_GATE alongside
HIGH_CONDITIONAL_PRECISION_BUT_INSUFFICIENT_VERIFIED_COVERAGE, not a single
collapsed label).

Run directly (needs network):
  python -m hyp04_supply_chain_hedge.calibrate_competitor_extractor --write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
CACHE_DIR = REPO_ROOT / ".edgar_cache"

# Same contact string used by every other live-pull script in this module
# (run_peer_earnings_fetch.py, run_peer_lineage_audit.py, run_peer_name_
# search.py, make_peer_ceiling.py) -- one identity across this repo's EDGAR
# fair-access traffic, not a new one per script.
CONTACT = "bchen9996 bchen9996@gmail.com"

# Fixed BEFORE running, not chosen after seeing which filings "look good":
# three tickers already in HYP04_Linkage_Map_v1.3.csv as known-good filers
# with an established Competition section (INTC, JBL, NVDA), plus two large,
# well-covered filers not in that map, for variety (AAPL, MSFT).
CALIBRATION_TICKERS: tuple[str, ...] = ("INTC", "JBL", "NVDA", "AAPL", "MSFT")


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def run_calibration(tickers: tuple[str, ...] = CALIBRATION_TICKERS,
                    *, contact: str = CONTACT) -> dict[str, Any]:
    """MAKES REAL SEC REQUESTS. Returns a structured findings dict; writes
    nothing itself."""
    from .edgar_linkage import (
        EdgarClient,
        FilingCache,
        extract_competitor_edges_from_text,
    )

    client = EdgarClient(contact, cache=FilingCache(CACHE_DIR))
    per_ticker: list[dict[str, Any]] = []

    for ticker in tickers:
        entry: dict[str, Any] = {"ticker": ticker}
        try:
            cik = client.cik_for(ticker)
            if cik is None:
                entry["error"] = "no CIK found for ticker"
                per_ticker.append(entry)
                continue
            entry["cik"] = cik

            filing = client.latest_10k(cik)
            if filing is None:
                entry["error"] = "no 10-K on the recent submissions page"
                per_ticker.append(entry)
                continue
            entry["filing"] = {
                "accession": filing["accession"],
                "filing_date": filing["filing_date"],
                "form": filing["form"],
            }

            text = client.filing_text(cik, filing["accession"],
                                      filing["primary_document"])
            entry["filing_text_chars"] = len(text)

            edges = extract_competitor_edges_from_text(
                text, ticker=ticker, cik=cik,
                filing_date=filing["filing_date"],
                accession=filing["accession"], form=filing["form"])
            entry["edges_found"] = len(edges)
            entry["edges"] = [e.as_dict() for e in edges]
        except Exception as exc:  # noqa: BLE001 -- reported per-ticker, not fatal to the run
            entry["error"] = f"{type(exc).__name__}: {exc}"
        per_ticker.append(entry)

    return {
        "calibration_date": _today_iso(),
        "tickers": list(tickers),
        "contact": contact,
        "requests_made": client.requests_made,
        "results": per_ticker,
    }


def render_findings_markdown(findings: dict[str, Any]) -> str:
    lines = [
        f"# HYP-05 competitor/supplier extractor calibration "
        f"({findings['calibration_date']})",
        "",
        "**Status: raw findings only. No pass/fail judgment is asserted by "
        "this script.** A human reads the context snippets below and writes "
        "the assessment.",
        "",
        f"Tickers: {', '.join(findings['tickers'])} -- fixed before running, "
        "not chosen after seeing results (see module docstring). Real SEC "
        f"requests made: {findings['requests_made']}.",
        "",
        "This script makes real network calls and is deliberately NOT part "
        "of the offline test suite. Nothing found here is added to any "
        "linkage map by this script.",
        "",
    ]
    for r in findings["results"]:
        lines.append(f"## {r['ticker']}")
        if "error" in r:
            lines.append(f"ERROR: {r['error']}")
            lines.append("")
            continue
        f = r["filing"]
        lines.append(f"- Filing: {f['form']} filed {f['filing_date']}, "
                     f"accession {f['accession']} ({r['filing_text_chars']:,} "
                     "chars of extracted text)")
        lines.append(f"- Edges found: {r['edges_found']}")
        lines.append("")
        for i, e in enumerate(r["edges"], 1):
            lines.append(f"{i}. **{e['named_counterparty']}** "
                         f"({e['direction']}, pattern `{e['pattern']}`)")
            lines.append(f"   > {e['context']!r}")
            lines.append("")
        if not r["edges"]:
            lines.append("(no edges found)")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="persist the findings markdown to Live Signal "
                         "Engine/HYP05_EXTRACTOR_CALIBRATION_<date>.md")
    ap.add_argument("--json", action="store_true",
                    help="print the raw findings as JSON instead of markdown")
    a = ap.parse_args(argv)

    findings = run_calibration()
    md = render_findings_markdown(findings)

    if a.json:
        print(json.dumps(findings, indent=2))
    else:
        print(md)

    if a.write:
        out = LSE / f"HYP05_EXTRACTOR_CALIBRATION_{findings['calibration_date']}.md"
        if out.is_file():
            print(f"\nREFUSED: {out} already exists. Dated artifacts are "
                  "never overwritten.", file=sys.stderr)
            return 1
        out.write_text(md, encoding="utf-8")
        print(f"\nwrote: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
