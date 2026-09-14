#!/usr/bin/env python3
"""LIVE. Fetch real daily close histories (every locked peer, PLUS the SPY
benchmark) and 8-K Item 2.02 earnings-release histories for every one of
HYP-07's locked peers -- the real inputs `make_hyp07_phase3_run.py`'s real
panel needs beyond what `run_hyp07_peer_market_cap.py` already fetched for
a DIFFERENT purpose (point-in-time market cap, `auto_adjust=False`,
discarded after use, never persisted).

=== GENERALIZES run_hyp06_peer_returns_fetch.py, PLUS ONE EXTRA TICKER ===

Same `auto_adjust=True` reasoning (a return-based target needs split-
adjusted closes; an unadjusted split-day return would look like a huge
fake abnormal return on a day nothing happened). Same reused
`earnings_events.candidates_for_ticker`, unchanged, looped once per locked
peer instead of 25 times.

The ONE real difference: `target_signed.build_feature_table_signed`
requires a benchmark ("SPY") return series alongside every peer's own
(`anchor_shock.BENCHMARK_TICKER`, the same ticker this project's anchor
side already benchmarks against) -- fetched into the SAME combined closes
CSV as one more ticker (`peer_returns.load_peer_closes`'s dedup key is
`(ticker, session_date)`, not `session_date` alone, so this needs no
format change). SPY gets NO earnings entry: `build_feature_table_signed`
explicitly skips the benchmark ticker when building `days_to_peer_earnings`
(target_signed.py's own `dte_cache` comprehension excludes it), so
`earnings_events.candidates_for_ticker` is never called for it.

Peers are read from the SIGNED HYP-07 Phase 2 lock's own `locked_peers`
field, not hand-typed here a second time -- same discipline as
run_hyp06_peer_returns_fetch.py's own peer-list sourcing.

STAGED. Without --yes-run-live it prints the plan and exits.

  python -m hyp04_supply_chain_hedge.run_hyp07_peer_returns_fetch
  python -m hyp04_supply_chain_hedge.run_hyp07_peer_returns_fetch --yes-run-live
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
DEFAULT_PHASE2_LOCK = LSE / f"HYP07_PHASE2_LOCK_{AS_OF}.json"

CLOSES_OUT = LSE / f"HYP07_PEER_CLOSES_{AS_OF}.csv"
EARNINGS_OUT = LSE / f"HYP07_PEER_EARNINGS_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

# HYP-07's real earliest locked event is 2010-09-28 (read directly from the
# signed lock, not assumed) -- well after HYP-06's own already-corrected
# floor of 2000-01-01 (see run_hyp06_peer_returns_fetch.py's own dated
# correction for why 1995 clipped make_event_panel._session_index's
# INDEX_PAD_DAYS=200 padding against sessions.py's calendar floor). Reusing
# that same, already-validated floor rather than re-deriving one: over 10
# years of real margin before the earliest genuine need, no analysis
# anywhere reads bytes at this bound as meaningful.
CLOSES_START = date(2000, 1, 1)


def _load_locked_peers(lock_path: Path) -> list[str]:
    if not lock_path.is_file():
        raise RuntimeError(
            f"no signed HYP-07 Phase 2 lock at {lock_path} -- this module "
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
          f"({len(peers)} peers -- benchmark ticker excluded, see module "
          "docstring)")
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
            continue  # no earnings entry for the benchmark -- see docstring

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
        "hypothesis_id": "HYP-07",
        "what_this_is": (
            "Every locked peer's own 8-K Item 2.02 earnings-release "
            "history, walked the same way earnings_events.py walks "
            "HYP-04's anchor side and run_hyp06_peer_returns_fetch.py "
            "walks HYP-06's 25 locked peers -- reportDate, never "
            "filingDate; release_session derived from acceptanceDateTime; "
            "UNKNOWN left unresolved rather than guessed."),
        "what_this_is_not": (
            "Not attributed to a trading-session index -- that happens "
            "where the session index is actually built "
            "(make_hyp07_phase3_run.py). Not a competitor relationship: "
            "these are each peer's OWN earnings, carried only as a "
            "days_to_peer_earnings design-matrix control column -- "
            "HYP-07's target has no residualization step to use them for, "
            "unlike HYP-04/05/06 (see target_signed.py's own docstring, "
            "'DELIBERATELY NOT PORTED')."),
        "peers": peers,
        "benchmark_ticker": BENCHMARK_TICKER,
        "benchmark_ticker_note": (
            "Fetched into the same combined closes CSV as one more "
            "ticker; carries NO earnings entry, since "
            "build_feature_table_signed never reads days_to_peer_earnings "
            "for the benchmark series."),
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
