#!/usr/bin/env python3
"""Stage-1 CANARY runner for the HYP-04 options-coverage audit.

REQUIRES the repo owner's stage-1 go-ahead (Patch 13). Authorized 2026-08-17:
10 tickers from the candidate peer universe, hard cap, no exceptions.

The hard cap is expressed in PROVIDER CALLS, not tickers, because calls are
what is billed. 10 tickers x 2 calls/ticker = 20. If any ticker turns out to
cost more than 2 calls, the cap stops the run early and reports rather than
quietly spending the overflow -- which is the entire point of running a
canary before sizing the full universe.

Usage (from repo root):
    python -m hyp04_supply_chain_hedge.run_canary_audit
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from .audit import Coverage, run_audit, write_report
from .constants import PLACEHOLDER_LINKAGE_WARNING

REPO_ROOT = Path(__file__).resolve().parent.parent
SECTOR_CSV = REPO_ROOT / "Live Signal Engine" / "AllTickers_Sectors.csv"
REPORT_PATH = (REPO_ROOT / "Live Signal Engine"
               / "HYP04_PHASE0_COVERAGE_AUDIT_CANARY_2026-08-17.json")

# Mirrored from gst_market_response/constants.py::LOCKED_24_TICKER_UNIVERSE.
# These are the ANCHORS; the candidate peer universe is everything else in
# the sector file. Copied rather than imported for the same reason that file
# gives for its own copy -- and it is only used here to EXCLUDE, never to
# redefine the locked universe.
LOCKED_24_ANCHORS = frozenset({
    "AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME",
    "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ",
    "SYK", "TSLA", "TTWO", "UAL",
})

# --- OWNER-AUTHORIZED STAGE-1 PARAMETERS (2026-08-17) ---------------------
CANARY_N_TICKERS = 10
EXPECTED_CALLS_PER_TICKER = 2          # tk.options + tk.option_chain(first)
CANARY_HARD_CAP_CALLS = CANARY_N_TICKERS * EXPECTED_CALLS_PER_TICKER   # 20


def candidate_peer_universe() -> list[str]:
    """The Phase 0 placeholder peer UNIVERSE: sector file minus the anchors.

    Reads the `ticker` column only. The `sector` column is NOT read -- this
    returns every non-anchor ticker in the file, regardless of industry, so
    the result is a flat universe and not a sector grouping. (Corrected
    2026-08-18: this docstring previously said "same-sector peers", describing
    GST_Task2_PeerDivergence.py's genuinely sector-based approach rather than
    what this function does.)

    It defines WHO the candidate peers are. It does not pair them with
    anchors -- fixtures.make_panel() does that positionally, by list slice.

    UNCHANGED BY THE 2026-08-18 HAND-CURATION SWITCH, deliberately (Option A).
    The committed EDGAR coverage findings were measured against exactly this
    27-peer universe, so rewiring it to a curated map would silently make
    those artifacts non-reproducible. The curated loader lives alongside it in
    curated_linkage.py; the two answer different questions.

    This is NOT a real supply-chain map, and no result derived from it is a
    finding about supply-chain transmission.
    """
    peers: list[str] = []
    with SECTOR_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            t = (row.get("ticker") or "").strip()
            if t and t not in LOCKED_24_ANCHORS and t not in peers:
                peers.append(t)
    return peers


def select_canary(peers: list[str], n: int) -> list[str]:
    """Deterministic, reproducible selection: evenly spaced across the file.

    Evenly spaced rather than the first n, so the canary spans sectors
    instead of over-sampling whichever sector happens to sort first -- a
    cost-per-call estimate drawn entirely from one sector would extrapolate
    badly to the full universe.
    """
    if len(peers) <= n:
        return list(peers)
    step = len(peers) / n
    return [peers[int(i * step)] for i in range(n)]


def main() -> int:
    print("*** HYP-04 Phase 0 -- options-coverage audit, STAGE 1 (CANARY) ***")
    print(PLACEHOLDER_LINKAGE_WARNING)
    print()

    peers = candidate_peer_universe()
    canary = select_canary(peers, CANARY_N_TICKERS)

    print(f"Candidate peer universe (placeholder linkage): {len(peers)} tickers")
    print(f"Canary selection ({len(canary)}): {', '.join(canary)}")
    print(f"Hard cap: {CANARY_HARD_CAP_CALLS} provider calls "
          f"({CANARY_N_TICKERS} tickers x {EXPECTED_CALLS_PER_TICKER} expected)")
    print("Provider: yfinance, UNAUTHENTICATED public endpoint (no API key)")
    print()

    run = run_audit(canary, stage="canary", hard_cap_calls=CANARY_HARD_CAP_CALLS)

    print(f"{'ticker':<8} {'coverage':<18} {'calls':>5} {'exps':>5} "
          f"{'calls_c':>8} {'puts_c':>7} {'secs':>6}")
    print("-" * 62)
    for r in run.results:
        print(f"{r.ticker:<8} {r.coverage:<18} {r.calls_made:>5} "
              f"{(r.n_expirations if r.n_expirations is not None else '-'):>5} "
              f"{(r.n_calls_contracts if r.n_calls_contracts is not None else '-'):>8} "
              f"{(r.n_puts_contracts if r.n_puts_contracts is not None else '-'):>7} "
              f"{(r.elapsed_seconds if r.elapsed_seconds is not None else '-'):>6}")
        if r.error_type:
            print(f"         -> {r.error_type}: {r.error_message}")

    s = run.summary()
    print()
    print("=== CANARY SUMMARY ===")
    print(f"  total provider calls        : {s['total_calls']} / cap {s['hard_cap_calls']}")
    print(f"  budget exhausted            : {s['budget_exhausted']}")
    print(f"  tickers attempted           : {s['tickers_attempted']} / {s['tickers_requested']}")
    print(f"  calls per ticker            : min={s['calls_per_ticker_min']} "
          f"max={s['calls_per_ticker_max']} mean={s['calls_per_ticker_mean']}")
    print(f"  calls per ticker CONSTANT?  : {s['calls_per_ticker_constant']}")
    print(f"  coverage OK                 : {s['coverage_ok']} / {s['tickers_attempted']}"
          + (f"  ({s['coverage_ok_pct']:.1f}%)" if s['coverage_ok_pct'] is not None else ""))
    print(f"  transport failures          : {s['transport_failures']}"
          "   (a provider defect, NOT a coverage fact)")
    print(f"  full peer universe          : {len(peers)} tickers")

    write_report(run, REPORT_PATH)
    print()
    print(f"Wrote: {REPORT_PATH.relative_to(REPO_ROOT)}")
    print()
    print("STOPPING HERE. Stage 2 (full universe) requires a separate, explicit")
    print("go-ahead with a budget extrapolated from the numbers above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
