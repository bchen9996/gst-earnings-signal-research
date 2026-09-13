#!/usr/bin/env python3
"""LIVE. Fetch real daily close histories and 8-K Item 2.02 earnings-release
histories for every one of HYP-06's locked peers -- the two real inputs
`make_hyp06_phase3_run.py`'s real panel needs beyond what
`run_hyp05_peer_market_cap.py` already fetched for a DIFFERENT purpose
(point-in-time market cap, `auto_adjust=False`, discarded after use, never
persisted).

=== GENERALIZES run_hyp05_peer_returns_fetch.py FROM ONE TICKER TO 25 ===

Same `auto_adjust=True` reasoning (realized variance needs split-adjusted
closes; an unadjusted split-day return would dominate an entire variance
window on a day nothing happened). Same reused
`earnings_events.candidates_for_ticker`, unchanged, looped once per locked
peer instead of called once for AMBA.

Peers are read from the SIGNED HYP-06 Phase 2 lock's own `locked_peers`
field, not hand-typed here a second time -- the lock is the one place this
list is allowed to be authoritative, and reading it live means a future
peer-list correction cannot silently diverge between the two files.

=== ONE COMBINED FILE PER OUTPUT KIND, NOT 25 ===

`peer_returns.load_peer_closes`'s own dedup key is `(ticker, session_date)`,
not `session_date` alone -- a single combined closes CSV across all locked
peers is a valid input to it, unlike the `HYP04_PEER_CLOSES_REQUEST`
workflow's one-file-per-ticker convention (built for a different,
request-based workflow this module does not use). Earnings are already
dict-of-ticker-keyed (`per_peer_earnings_releases`) by construction, so one
combined JSON needs no format change either.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp06_peer_returns_fetch
  python -m hyp04_supply_chain_hedge.run_hyp06_peer_returns_fetch --yes-run-live
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
AS_OF = "2026-09-13"
DEFAULT_PHASE2_LOCK = LSE / f"HYP06_PHASE2_LOCK_{AS_OF}.json"

CLOSES_OUT = LSE / f"HYP06_PEER_CLOSES_{AS_OF}.csv"
EARNINGS_OUT = LSE / f"HYP06_PEER_EARNINGS_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

# Well before any HYP-06 locked peer's real anchor-event history (round 6's
# own qualifying ranges reach back into the early-to-mid 2000s -- NGS/DVN,
# CKX/EOG, SIG/SPG) -- bounded by what the provider actually returns, not
# by an assumption about when any individual ticker's own history starts.
CLOSES_START = date(1995, 1, 1)


def _load_locked_peers(lock_path: Path) -> list[str]:
    if not lock_path.is_file():
        raise RuntimeError(
            f"no signed HYP-06 Phase 2 lock at {lock_path} -- this module "
            "reads its own peer list from there, not a second, hand-typed "
            "copy.")
    doc = json.loads(lock_path.read_text(encoding="utf-8"))
    if doc.get("declared") is not True:
        raise RuntimeError(
            f"{lock_path.name} is not a SIGNED lock -- refusing to fetch "
            "real return data against an undeclared draft's peer list.")
    peers = doc.get("locked_peers")
    if not peers:
        raise RuntimeError(f"{lock_path.name} has no locked_peers")
    return sorted(peers)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--phase2-lock", type=Path, default=DEFAULT_PHASE2_LOCK)
    ap.add_argument("--closes-out", type=Path, default=CLOSES_OUT)
    ap.add_argument("--earnings-out", type=Path, default=EARNINGS_OUT)
    a = ap.parse_args(argv)

    for p in (a.closes_out, a.earnings_out):
        if p.exists():
            print(f"REFUSED: {p} already exists. Dated artifacts are never "
                  "overwritten.", file=sys.stderr)
            return 1

    peers = _load_locked_peers(a.phase2_lock)
    print(f"peers ({len(peers)}): {peers}")
    print(f"closes: yfinance, auto_adjust=True, {CLOSES_START} .. today")
    print("earnings: SEC EDGAR 8-K Item 2.02, full filing history")
    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .run_peer_closes_fetch import fetch_closes
    from .edgar_linkage import EdgarClient, FilingCache
    from .earnings_events import candidates_for_ticker

    all_rows: list[tuple[str, date, float]] = []
    per_peer_releases: dict[str, list[dict[str, Any]]] = {}
    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR))

    for peer in peers:
        closes = fetch_closes(peer, CLOSES_START, date.today(), auto_adjust=True)
        if not closes:
            print(f"REFUSED: yfinance returned zero closes for {peer}",
                  file=sys.stderr)
            return 1
        for d, c in closes.items():
            all_rows.append((peer, d, c))
        sessions = sorted(closes)
        print(f"  {peer}: {len(closes)} sessions "
              f"{sessions[0]} .. {sessions[-1]}")

        events = candidates_for_ticker(client, peer)
        rows = []
        for e in events:
            r = e.as_row()
            r["peer_ticker"] = r.pop("anchor_ticker")
            rows.append(r)
        per_peer_releases[peer] = rows
        print(f"  {peer}: {len(rows)} candidate earnings release(s)")

    a.closes_out.parent.mkdir(parents=True, exist_ok=True)
    with a.closes_out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for peer, d, c in sorted(all_rows, key=lambda r: (r[0], r[1])):
            w.writerow([peer, d.isoformat(), f"{c:.6f}"])
    print(f"\nwrote {a.closes_out}  ({len(all_rows)} rows, {len(peers)} tickers)")

    doc: dict[str, Any] = {
        "artifact": a.earnings_out.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-06",
        "what_this_is": (
            "Every locked peer's own 8-K Item 2.02 earnings-release "
            "history, walked the same way earnings_events.py walks "
            "HYP-04's anchor side and run_hyp05_peer_returns_fetch.py "
            "walks HYP-05's single peer -- reportDate, never filingDate; "
            "release_session derived from acceptanceDateTime; UNKNOWN "
            "left unresolved rather than guessed."),
        "what_this_is_not": (
            "Not attributed to a trading-session index -- that happens "
            "where the session index is actually built "
            "(make_hyp06_phase3_run.py). Not a supply-chain relationship: "
            "these are each peer's OWN earnings, used only to residualize "
            "its own target against its own earnings-cycle baseline."),
        "peers": peers,
        "sources": {
            "endpoint": "data.sec.gov submissions",
            "requests_made": client.requests_made,
            "contact": CONTACT,
        },
        "per_peer_earnings_releases": per_peer_releases,
    }
    a.earnings_out.parent.mkdir(parents=True, exist_ok=True)
    a.earnings_out.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {a.earnings_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
