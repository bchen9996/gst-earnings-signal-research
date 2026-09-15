#!/usr/bin/env python3
"""LIVE. Fetch real daily close histories (every one of HYP-08's 31 pooled
peers, PLUS the SPY benchmark) and 8-K Item 2.02 earnings-release
histories for every one of them -- the real inputs
`make_hyp08_phase3_run.py`'s real panel needs.

=== A FRESH FETCH, EVEN THOUGH BOTH SOURCE PEER SETS WERE ALREADY FETCHED ===

`HYP06_PEER_CLOSES_2026-09-13.csv` (25 peers) and `HYP07_PEER_CLOSES_
2026-09-14.csv` (6 peers, + SPY) both already exist -- but HYP-06's own
fetch never included a benchmark ticker (its target never needed one), so
it cannot be reused directly for a signed, benchmark-adjusted same-session
target. Rather than patch two mismatched CSVs together (one with SPY, one
without) this fetches all 31 distinct peers (confirmed zero overlap
between the two source universes) PLUS SPY into one combined file, exactly
mirroring `run_hyp07_peer_returns_fetch.py`'s own mechanism.

Peers are read from HYP-08's OWN signed Phase 2 lock's `locked_peers`
field, not hand-typed here a second time and not the union of the two
source locks' own peer lists re-derived independently (which could
silently drift from what HYP-08's lock actually fixed).

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp08_peer_returns_fetch
  python -m hyp04_supply_chain_hedge.run_hyp08_peer_returns_fetch --yes-run-live
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .anchor_shock import BENCHMARK_TICKER

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-14"
DEFAULT_PHASE2_LOCK = LSE / f"HYP08_PHASE2_LOCK_{AS_OF}.json"

CLOSES_OUT = LSE / f"HYP08_PEER_CLOSES_{AS_OF}.csv"
EARNINGS_OUT = LSE / f"HYP08_PEER_EARNINGS_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

#: Same already-validated floor HYP-06's and HYP-07's own fetches use --
#: not re-derived here.
CLOSES_START = date(2000, 1, 1)


def _load_locked_peers(lock_path: Path) -> list[str]:
    if not lock_path.is_file():
        raise RuntimeError(
            f"no signed HYP-08 Phase 2 lock at {lock_path} -- this module "
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
    tickers = [*peers, BENCHMARK_TICKER]
    print(f"peers ({len(peers)}): {peers}")
    print(f"+ benchmark: {BENCHMARK_TICKER}")
    print(f"closes: yfinance, auto_adjust=True, {CLOSES_START} .. today, "
          f"{len(tickers)} tickers")
    print("earnings: SEC EDGAR 8-K Item 2.02, full filing history "
          f"({len(peers)} peers -- benchmark ticker excluded)")
    if not a.yes_run_live:
        print("\nDRY RUN. Re-run with --yes-run-live to proceed.")
        return 0

    from .run_peer_closes_fetch import fetch_closes
    from .edgar_linkage import EdgarClient, FilingCache
    from .earnings_events import candidates_for_ticker

    all_rows: list[tuple[str, date, float]] = []
    per_peer_releases: dict[str, list[dict[str, Any]]] = {}
    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR))

    for ticker in tickers:
        closes = fetch_closes(ticker, CLOSES_START, date.today(), auto_adjust=True)
        if not closes:
            print(f"REFUSED: yfinance returned zero closes for {ticker}",
                  file=sys.stderr)
            return 1
        for d, c in closes.items():
            all_rows.append((ticker, d, c))
        sessions = sorted(closes)
        print(f"  {ticker}: {len(closes)} sessions "
              f"{sessions[0]} .. {sessions[-1]}")

        if ticker == BENCHMARK_TICKER:
            continue

        events = candidates_for_ticker(client, ticker)
        rows = []
        for e in events:
            r = e.as_row()
            r["peer_ticker"] = r.pop("anchor_ticker")
            rows.append(r)
        per_peer_releases[ticker] = rows
        print(f"  {ticker}: {len(rows)} candidate earnings release(s)")

    a.closes_out.parent.mkdir(parents=True, exist_ok=True)
    with a.closes_out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for ticker, d, c in sorted(all_rows, key=lambda r: (r[0], r[1])):
            w.writerow([ticker, d.isoformat(), f"{c:.6f}"])
    print(f"\nwrote {a.closes_out}  ({len(all_rows)} rows, {len(tickers)} "
          "tickers)")

    doc: dict[str, Any] = {
        "artifact": a.earnings_out.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-08",
        "what_this_is": (
            "Every locked peer's own 8-K Item 2.02 earnings-release "
            "history -- reportDate, never filingDate; release_session "
            "derived from acceptanceDateTime; UNKNOWN left unresolved "
            "rather than guessed. Same mechanism every prior "
            "hypothesis's own peer-earnings fetch uses."),
        "what_this_is_not": (
            "Not attributed to a trading-session index here -- that "
            "happens where the session index is actually built "
            "(make_hyp08_phase3_run.py). Carried only as a "
            "days_to_peer_earnings design-matrix control column -- "
            "HYP-08's target has no residualization step to use it for, "
            "same as HYP-07's own target_signed.py."),
        "peers": peers,
        "benchmark_ticker": BENCHMARK_TICKER,
        "benchmark_ticker_note": (
            "Fetched into the same combined closes CSV as one more "
            "ticker; carries NO earnings entry."),
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
