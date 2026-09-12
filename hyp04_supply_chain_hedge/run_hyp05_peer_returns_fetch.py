#!/usr/bin/env python3
"""LIVE. Fetch AMBA's own full daily close history (for return-series/
realized-variance purposes) and its own 8-K Item 2.02 earnings-release
history -- the two real inputs HYP-05's Phase 3 run needs beyond what
`run_hyp05_peer_market_cap.py` already fetched for a DIFFERENT purpose
(point-in-time market cap, `auto_adjust=False`, discarded after use, never
persisted).

=== WHY A SEPARATE FETCH, AND WHY auto_adjust=True HERE (NOT False) ===

`run_hyp05_peer_market_cap.py`'s docstring explains at length why market
cap needs the RAW, unadjusted close (matching the raw, as-disclosed share
count). Realized variance of log returns is the opposite case:
`run_peer_closes_fetch.py`'s own module docstring is explicit that an
unadjusted split prints a return large enough to dominate an entire
variance window on a day nothing happened. This module therefore calls
`fetch_closes(..., auto_adjust=True)` -- HYP-04's own peer-closes default,
reused unchanged, for the same reason.

=== ONE TICKER, NOT A REQUEST-FILE WORKFLOW ===

HYP-04's `run_peer_closes_fetch.py` fills a pre-emitted request file
(`closes_requirements --emit-requests`), built for a multi-peer panel
sharing one XNYS-derived session index. HYP-05's real analysis has exactly
one peer (AMBA) and no shared calendar to reconcile against anything else
-- `peer_returns.py`'s own module docstring is explicit that the session
index is INJECTED by the caller, not derived from a shared calendar
dependency, so AMBA's own observed trading dates are a perfectly valid
session index for a single-ticker analysis. This module therefore writes
closes directly in the same three-column shape (`ticker, session_date,
close`) `peer_returns.load_peer_closes` already reads, rather than
routing through the request-file machinery built for a different shape
of panel.

=== EARNINGS: REUSES earnings_events.py UNCHANGED ===

`earnings_events.candidates_for_ticker` was already written ticker-
agnostic (the same function `run_peer_earnings_fetch.py` uses for HYP-04's
six peers) -- reused here for AMBA, not reimplemented. Output is written
in the SAME shape (`per_peer_earnings_releases`) so
`make_phase1_diagnostics._attribute_peer_earnings` -- the same BMO/AMC
session-attribution logic already validated for HYP-04 -- can read it
unchanged.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp05_peer_returns_fetch
  python -m hyp04_supply_chain_hedge.run_hyp05_peer_returns_fetch --yes-run-live
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-12"
PEER_TICKER = "AMBA"

CLOSES_OUT = LSE / f"HYP05_PEER_CLOSES_{PEER_TICKER}_{AS_OF}.csv"
EARNINGS_OUT = LSE / f"HYP05_PEER_EARNINGS_{PEER_TICKER}_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

# Well before Ambarella's real 2012-10-05 IPO, so the fetch is bounded by
# what the provider actually returns, not by an assumption about when its
# history starts.
CLOSES_START = date(2011, 1, 1)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--closes-out", type=Path, default=CLOSES_OUT)
    ap.add_argument("--earnings-out", type=Path, default=EARNINGS_OUT)
    a = ap.parse_args(argv)

    for p in (a.closes_out, a.earnings_out):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are never "
                  "overwritten.", file=sys.stderr)
            return 1

    print(f"peer: {PEER_TICKER}")
    print(f"closes: yfinance, auto_adjust=True, {CLOSES_START} .. today")
    print("earnings: SEC EDGAR 8-K Item 2.02, full filing history")
    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .run_peer_closes_fetch import fetch_closes
    from .edgar_linkage import EdgarClient, FilingCache
    from .earnings_events import candidates_for_ticker

    closes = fetch_closes(PEER_TICKER, CLOSES_START, date.today(),
                          auto_adjust=True)
    if not closes:
        print(f"REFUSED: yfinance returned zero closes for {PEER_TICKER}",
              file=sys.stderr)
        return 1
    sessions = sorted(closes)
    print(f"\nclose fetch: {len(closes)} sessions, {sessions[0]} .. {sessions[-1]}")

    a.closes_out.parent.mkdir(parents=True, exist_ok=True)
    with a.closes_out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for d in sessions:
            w.writerow([PEER_TICKER, d.isoformat(), f"{closes[d]:.6f}"])
    print(f"wrote {a.closes_out}")

    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR))
    events = candidates_for_ticker(client, PEER_TICKER)
    rows = []
    for e in events:
        r = e.as_row()
        r["peer_ticker"] = r.pop("anchor_ticker")
        rows.append(r)
    print(f"\nearnings fetch: {len(rows)} candidate release(s), "
          f"requests_made={client.requests_made}")

    doc: dict[str, Any] = {
        "artifact": a.earnings_out.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "AMBA's own 8-K Item 2.02 earnings-release history, walked the "
            "same way earnings_events.py walks HYP-04's anchor side and "
            "run_peer_earnings_fetch.py walks HYP-04's peer side -- "
            "reportDate, never filingDate; release_session derived from "
            "acceptanceDateTime; UNKNOWN left unresolved rather than "
            "guessed."),
        "what_this_is_not": (
            "Not attributed to a trading-session index -- that happens "
            "where the session index is actually built (make_hyp05_"
            "phase3_run.py), mirroring how HYP-04 keeps that attribution "
            "out of its own peer-earnings fetcher. Not a supply-chain "
            "relationship: these are AMBA's OWN earnings, used only to "
            "residualize its own target against its own earnings-cycle "
            "baseline."),
        "peer": PEER_TICKER,
        "sources": {
            "endpoint": "data.sec.gov submissions",
            "requests_made": client.requests_made,
            "contact": CONTACT,
        },
        "per_peer_earnings_releases": {PEER_TICKER: rows},
    }
    a.earnings_out.parent.mkdir(parents=True, exist_ok=True)
    a.earnings_out.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.earnings_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
