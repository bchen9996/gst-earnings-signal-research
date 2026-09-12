#!/usr/bin/env python3
"""Point-in-time shares-outstanding lookup, for HYP-05's market-cap proxy.

=== WHY THIS EXISTS ===

HYP-05's coverage/liquidity cutoff is point-in-time market cap: was this peer
small at the time of the anchor event, not today. Market cap is price x
shares outstanding, and no point-in-time shares-outstanding data exists
anywhere in this repo -- `GST_Task3_MarketCapBuckets.py` computes market cap
from TODAY's `yfinance` snapshot and says so plainly in its own header. Using
today's cap to classify a 2015 event would be exactly the kind of look-ahead
this project's `as_of_date` discipline exists to forbid elsewhere
(`curated_linkage.py`, `anchor_universe.py`'s AU-6).

SEC filers disclose shares outstanding on the cover page of every 10-K and
10-Q, tagged `dei:EntityCommonStockSharesOutstanding` in XBRL. That gives
quarterly-ish density -- far better than the annual-only `us-gaap` tags
`Sloan_Accruals_Gate.py` reads for its own companyfacts pull, whose pattern
this module's network path mirrors via `EdgarClient.companyfacts()`.

=== THE POINT-IN-TIME GUARANTEE ===

A fact has two dates: `end` (the as-of date printed on the cover page) and
`filed` (when the filing itself reached the SEC). Both must be on or before
the target date. A fact whose `end` predates the target but whose `filed`
date is AFTER it must never be used -- the filer had not yet told anyone that
value as of the target date, even though it describes an earlier state. This
is the same two-date discipline `curated_linkage.py` keeps between
`as_of_date` and discovery/curation date, applied here to a different pair.

`shares_outstanding_as_of()` is a pure function over already-parsed facts,
so it is fully testable against synthetic companyfacts fixtures with no
network call. `fetch_shares_outstanding_series()` is the thin, separately
swappable wrapper that actually talks to SEC, via `EdgarClient` (this
project's existing rate-limited, cached, contact-validated client) rather
than a second HTTP implementation.

NOTHING HERE IS EVIDENCE ABOUT SUPPLY-CHAIN TRANSMISSION. This is a data
utility only.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional, Sequence

# --- The tag this module reads ---------------------------------------------
SHARES_TAXONOMY = "dei"
SHARES_TAG = "EntityCommonStockSharesOutstanding"
SHARES_UNIT = "shares"
# Cover-page shares outstanding appears on both annual and quarterly reports
# and their amendments -- prefix match catches 10-K/10-K-A and 10-Q/10-Q-A.
#
# "20-F" added 2026-09-12, found via a real HYP-05 candidate: GlobalFoundries
# (CIK 0001709048, a foreign private issuer) files 20-F, not 10-K -- its real
# `dei:EntityCommonStockSharesOutstanding` facts (2021-2025, real filed
# values) were being silently excluded, making every point-in-time market
# cap for it "missing_shares" instead of a real computed number. Safe to
# widen: `dei:EntityCommonStockSharesOutstanding` is a standardized
# cover-page fact in EDGAR's Document and Entity Information taxonomy,
# defined the same way regardless of which annual-report form disclosed it
# -- unlike a us-gaap financial-statement tag, it does not depend on GAAP
# vs. IFRS. Only 20-F is added here because only 20-F has been measured
# against a real filer; other foreign-issuer forms (40-F, 6-K) may carry
# the same tag but are not yet verified, so they are not assumed.
QUALIFYING_FORM_PREFIXES: tuple[str, ...] = ("10-K", "10-Q", "20-F")


def _valid_iso_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class SharesOutstandingFact:
    """One disclosed shares-outstanding figure, with both of its dates."""

    ticker: str
    shares: float
    end: str        # as-of date printed on the filing's cover page
    filed: str       # date the filing itself was submitted to the SEC
    form: str
    accession: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {"ticker": self.ticker, "shares": self.shares, "end": self.end,
                "filed": self.filed, "form": self.form,
                "accession": self.accession}


def facts_from_companyfacts(
    ticker: str, companyfacts: Mapping[str, Any],
) -> tuple[SharesOutstandingFact, ...]:
    """Parse one SEC companyfacts JSON document into shares-outstanding facts.

    Pure function, no network -- offline-testable against a synthetic
    companyfacts dict shaped like the real API response:
    `{"facts": {"dei": {"EntityCommonStockSharesOutstanding":
    {"units": {"shares": [{"end": ..., "filed": ..., "val": ..., "form": ...,
    "accn": ...}, ...]}}}}}`.

    Malformed or absent structure returns an empty tuple rather than raising
    -- a filer that has never tagged this fact (rare, but not impossible) is
    a real, reportable absence, not a bug in this parser.
    """
    try:
        entries = (companyfacts["facts"][SHARES_TAXONOMY][SHARES_TAG]
                   ["units"][SHARES_UNIT])
    except (KeyError, TypeError):
        return ()
    if not isinstance(entries, list):
        return ()

    out: list[SharesOutstandingFact] = []
    for e in entries:
        if not isinstance(e, Mapping):
            continue
        form = str(e.get("form", ""))
        if not any(form.upper().startswith(p) for p in QUALIFYING_FORM_PREFIXES):
            continue
        val = e.get("val")
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        end, filed = e.get("end"), e.get("filed")
        if _valid_iso_date(end) is None or _valid_iso_date(filed) is None:
            continue
        out.append(SharesOutstandingFact(
            ticker=ticker.upper(), shares=float(val), end=end, filed=filed,
            form=form, accession=e.get("accn")))
    return tuple(out)


def shares_outstanding_as_of(
    facts: Sequence[SharesOutstandingFact], target_date: str,
) -> Optional[SharesOutstandingFact]:
    """The most recent shares-outstanding figure actually known as of
    `target_date` -- the point-in-time guarantee described in this module's
    docstring. Returns None, never a guess or an interpolation, when nothing
    qualifies; the caller records that as a refusal, not a zero."""
    cutoff = _valid_iso_date(target_date)
    if cutoff is None:
        return None

    qualifying = []
    for f in facts:
        end = _valid_iso_date(f.end)
        filed = _valid_iso_date(f.filed)
        if end is None or filed is None:
            continue
        if end <= cutoff and filed <= cutoff:
            qualifying.append(f)
    if not qualifying:
        return None
    return max(qualifying, key=lambda f: f.end)


def fetch_shares_outstanding_series(
    ticker: str, cik: str, client: Any,
) -> tuple[SharesOutstandingFact, ...]:
    """MAKES REAL SEC REQUESTS via `client` (an `EdgarClient`). Thin wrapper
    around `facts_from_companyfacts` -- kept separate so the point-in-time
    selection logic above is fully testable without a network call."""
    data = client.companyfacts(cik)
    return facts_from_companyfacts(ticker, data)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Point-in-time shares-outstanding lookup for one ticker. "
                    "MAKES REAL SEC REQUESTS.")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--cik", required=True,
                    help="10-digit zero-padded CIK")
    ap.add_argument("--as-of", required=True, dest="as_of",
                    help="YYYY-MM-DD -- the target date")
    ap.add_argument("--contact", required=True,
                    help="EDGAR fair-access contact, e.g. 'Name email@x.com'")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    from .edgar_linkage import EdgarClient
    client = EdgarClient(a.contact)
    series = fetch_shares_outstanding_series(a.ticker, a.cik, client)
    fact = shares_outstanding_as_of(series, a.as_of)

    if a.json:
        print(json.dumps({
            "ticker": a.ticker, "as_of": a.as_of,
            "series_length": len(series),
            "result": fact.as_dict() if fact else None,
        }, indent=2))
    elif fact is None:
        print(f"{a.ticker}: no qualifying shares-outstanding fact on or "
              f"before {a.as_of} ({len(series)} fact(s) in the full series)")
    else:
        print(f"{a.ticker} as of {a.as_of}: {fact.shares:,.0f} shares "
              f"(disclosed {fact.end}, filed {fact.filed}, {fact.form})")
    return 0 if fact is not None else 1


if __name__ == "__main__":
    sys.exit(main())
