#!/usr/bin/env python3
"""LIVE. Fetch each HYP-04 peer's own 8-K Item 2.02 earnings-release history.

Named off the `test_*` pattern deliberately: this reaches an endpoint and
must never be swept up by a test-runner glob.

STAGED. Without `--yes-run-live` it prints exactly which peers and CIKs it
would fetch and exits, so the request list is reviewable before anything is
asked of SEC.

  python -m hyp04_supply_chain_hedge.run_peer_earnings_fetch          # dry run
  python -m hyp04_supply_chain_hedge.run_peer_earnings_fetch --yes-run-live

=== WHY THIS EXISTS ===

`target.build_feature_table` residualizes each peer's target against that
peer's OWN earnings-cycle baseline (`estimate_earnings_cycle_baseline`), and
that needs `peer_earnings_days` -- the peer's own release dates. There is no
peer-side equivalent of `earnings_events.py` on disk; the anchor side already
walks 8-K Item 2.02 correctly (reportDate not filingDate, BMO/AMC derived from
acceptanceDateTime, UNKNOWN left unresolved rather than guessed), and
`earnings_events.candidates_for_ticker` was already written ticker-agnostic --
it takes any ticker, not only an anchor. This reuses it rather than
reimplementing a second, possibly-diverging walk.

=== WHAT THIS DOES NOT DO ===

It does not attribute a release to a trading-SESSION INDEX. That is what
`event_panel.resolve_events` does for anchor events (BMO -> same session, AMC
-> next session), and the Phase 1 runner is where a peer session index
actually gets built -- so this artifact stops at `release_date` and
`release_session` (BMO/AMC/UNKNOWN, exactly as CandidateEvent already
classifies it). Converting dates to day-indices here would either duplicate
`resolve_events` or silently diverge from it, and the divergence would be
invisible until the two disagreed on some AMC-adjacent date.

It does not curate, screen, or move any gate. These are the peer's OWN
earnings releases -- not a supply-chain relationship, not a peer-anchor link,
not an eligible event. Nothing here moves C1 through C5, and that stays true
whatever the gate reads at the moment this file is read: it is not restated
as a snapshot, because a snapshot of a moving condition is exactly the defect
found and fixed across seven other HYP-04 artifacts on 2026-09-09.

=== THE PEER SET IS FIXED, NOT DERIVED ===

AAPL, BB, CSCO, CVS, HPQ, MSFT -- the six peers HYP-04 already holds real,
curated closes for (HYP04_EVENT_PANEL_2026-09-08.json's `peer_closes` block).
Not re-derived here: authorized by the repo owner for exactly this scope
(2026-09-10), the same way the anchor universe is fixed by registration
rather than recomputed per run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from .earnings_events import (
    CandidateEvent,
    candidates_for_ticker,
    find_cadence_gaps,
    summarise,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-10"
OUT_JSON = LSE / f"HYP04_PEER_EARNINGS_{AS_OF}.json"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

#: See "THE PEER SET IS FIXED, NOT DERIVED" above.
PEER_TICKERS = ("AAPL", "BB", "CSCO", "CVS", "HPQ", "MSFT")

#: One submissions.json per peer, plus older shards for a long filing history
#: (`filings.files[]` in `all_item_202_records`). A rough ceiling, not a
#: measured one -- overridable with --max-requests if a peer's history is
#: unusually sharded.
DEFAULT_MAX_REQUESTS_PER_PEER = 15


def _peer_row(e: CandidateEvent) -> dict[str, Any]:
    """One earnings-release row, as this artifact records it. Pure; no I/O.

    `CandidateEvent.anchor_ticker` is the field name inherited from
    `earnings_events.py`'s anchor-side framing -- the class is ticker-agnostic
    but the field name is not. Relabelled here so a reader of THIS artifact is
    never told a peer is an anchor.
    """
    r = e.as_row()
    r["peer_ticker"] = r.pop("anchor_ticker")
    return r


def _resolve_ciks(*, offline: bool, cache_dir: Path = CACHE_DIR
                  ) -> tuple[dict[str, str], list[str], int]:
    """Ticker -> CIK for every PEER_TICKERS entry. Served from cache.

    `offline=True` means a cache miss raises `OfflineCacheMiss` rather than
    reaching the network -- so the dry-run plan printed below can never
    itself be a live request. Returns (ciks, unknown, requests_made) so the
    caller can refuse if the lookup cost anything.

    `cache_dir` is a parameter, not always the module constant, so a test can
    point it at an empty directory and prove the refusal fires -- the same
    thing `earnings_events.py`'s own suite does for `all_item_202_records`.
    """
    from .edgar_linkage import EdgarClient, FilingCache
    client = EdgarClient(CONTACT, cache=FilingCache(cache_dir), offline=offline)
    ciks: dict[str, str] = {}
    unknown: list[str] = []
    for t in PEER_TICKERS:
        c = client.cik_for(t)
        (ciks.__setitem__(t, c) if c else unknown.append(t))
    return ciks, unknown, client.requests_made


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch each HYP-04 peer's own 8-K Item 2.02 earnings-"
                    "release history. LIVE; staged.")
    ap.add_argument("--yes-run-live", action="store_true",
                    help="actually contact SEC (default: print the plan only)")
    ap.add_argument("--max-requests", type=int,
                    default=len(PEER_TICKERS) * DEFAULT_MAX_REQUESTS_PER_PEER,
                    help="hard cap across all peers combined")
    a = ap.parse_args(argv)

    if OUT_JSON.exists():
        print(f"REFUSED: {OUT_JSON.name} already exists. Dated artifacts are "
              "never overwritten -- delete it deliberately first.",
              file=sys.stderr)
        return 1

    ciks, unknown, lookup_cost = _resolve_ciks(offline=True)
    if lookup_cost:
        print(f"REFUSED: ticker->CIK lookup cost {lookup_cost} request(s); "
              "it must be served from cache", file=sys.stderr)
        return 1
    if unknown:
        # Unlike an unresolved COUNTERPARTY name (routine -- see
        # run_peer_name_search), these are six specific, well-known public
        # companies already curated elsewhere in this project. No CIK for one
        # of them is an anomaly worth stopping for, not a case to route
        # around with a partial set.
        print(f"REFUSED: no CIK for {', '.join(unknown)} -- this peer set is "
              "fixed and every entry is expected to resolve", file=sys.stderr)
        return 1

    print(f"peers: {', '.join(PEER_TICKERS)}")
    for t in PEER_TICKERS:
        print(f"  {t:6} CIK {ciks[t]}")

    if not a.yes_run_live:
        print()
        print(f"DRY RUN. Up to {a.max_requests} request(s) would be made to "
              "data.sec.gov (one submissions.json per peer, plus any older "
              "shards). Re-run with --yes-run-live to proceed.")
        return 0

    from .edgar_linkage import EdgarClient, FilingCache
    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR),
                         max_requests=a.max_requests)

    per_peer: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    cadence_gaps: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for t in PEER_TICKERS:
        try:
            evs = candidates_for_ticker(client, t)
        except Exception as exc:                       # noqa: BLE001
            errors[t] = f"{type(exc).__name__}: {exc}"
            continue
        per_peer[t] = [_peer_row(e) for e in evs]
        gaps = find_cadence_gaps(evs)
        cadence_gaps[t] = [{"from": f, "to": to, "days": d}
                           for f, to, d in gaps]
        s = summarise(evs)
        summaries[t] = s
        print(f"{t}: {s['total']} candidate release(s) "
              f"{s['earliest']} .. {s['latest']}  "
              f"AMC={s['by_session']['AMC']} BMO={s['by_session']['BMO']} "
              f"UNKNOWN={s['by_session']['UNKNOWN']}  flagged={s['flagged']}")
        for g in cadence_gaps[t]:
            print(f"    GAP  {g['from']} -> {g['to']} ({g['days']} days)")

    if errors:
        print(f"\nREFUSED: fetch failed for {', '.join(sorted(errors))}. "
              "Nothing written -- a partial peer set would understate the "
              "baseline for some peers and not others, which is a worse "
              "failure mode than stopping here.", file=sys.stderr)
        for t, e in errors.items():
            print(f"    {t}: {e}", file=sys.stderr)
        return 1

    doc: dict[str, Any] = {
        "artifact": OUT_JSON.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "Each peer's own 8-K Item 2.02 earnings-release history, walked "
            "the same way earnings_events.py walks the anchor side -- "
            "reportDate, never filingDate; release_session derived from "
            "acceptanceDateTime the same way; UNKNOWN left unresolved rather "
            "than guessed."),
        "what_this_is_not": (
            "Not attributed to a trading-session INDEX -- that happens where "
            "the session index is actually built, the same way "
            "event_panel.resolve_events attributes anchor events. Not a "
            "supply-chain relationship: these are the peer's OWN earnings, "
            "used only to residualize its own target against its own "
            "earnings-cycle baseline (target.estimate_earnings_cycle_baseline). "
            "Moves no gate condition -- C1 through C5 are untouched by this "
            "artifact, whatever the gate reads when this file is read."),
        "peers": list(PEER_TICKERS),
        "cik_by_peer": ciks,
        "sources": {
            "endpoint": "data.sec.gov submissions",
            "requests_made": client.requests_made,
            "contact": CONTACT,
        },
        "per_peer_earnings_releases": per_peer,
        "cadence_gaps": {t: g for t, g in cadence_gaps.items() if g},
        "summary_by_peer": summaries,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print()
    print(f"requests made: {client.requests_made}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
