#!/usr/bin/env python3
"""Stage-2 FULL runner for the HYP-04 options-coverage audit.

REQUIRES the repo owner's stage-2 go-ahead (Patch 13). Authorized 2026-08-17:
"Run the remaining 17 tickers (34 calls) to complete the placeholder-universe
check. Add a short delay between calls (~1s) given the prior crumb-negotiation
failure."

Runs ONLY the peers the stage-1 canary did not already cover. The canary's 10
results are complete and correct; re-running them would spend calls to
reproduce numbers already committed to
HYP04_PHASE0_COVERAGE_AUDIT_CANARY_2026-08-17.json, and the owner's
authorization was explicitly for the *remaining* tickers.

Pacing rationale (Patch 13, Round 5 correction): the binding constraint for
this provider is rate-limiting and fragility, NOT money -- yfinance is free
and unauthenticated, confirmed at $0.00 across the canary's 20 calls. This
repo has already lost one live diagnostic to this provider's crumb/cookie
negotiation (2026-08-04, Pass 1). The delay is insurance against that, not a
cost-control measure.

Usage (from repo root):
    python -m hyp04_supply_chain_hedge.run_full_audit
"""
from __future__ import annotations

import sys
from pathlib import Path

from .audit import run_audit, write_report
from .constants import PLACEHOLDER_LINKAGE_WARNING
from .run_canary_audit import (
    CANARY_N_TICKERS,
    EXPECTED_CALLS_PER_TICKER,
    candidate_peer_universe,
    select_canary,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = (REPO_ROOT / "Live Signal Engine"
               / "HYP04_PHASE0_COVERAGE_AUDIT_FULL_2026-08-17.json")

# --- OWNER-AUTHORIZED STAGE-2 PARAMETERS (2026-08-17) ---------------------
# The cap is stated in CALLS, derived from the canary's OBSERVED constant
# 2 calls/ticker -- not assumed. If any remaining ticker costs more than 2,
# the cap stops the run and reports rather than spending the overflow.
INTER_CALL_DELAY_SECONDS = 1.0


def main() -> int:
    print("*** HYP-04 Phase 0 -- options-coverage audit, STAGE 2 (FULL) ***")
    print(PLACEHOLDER_LINKAGE_WARNING)
    print()

    peers = candidate_peer_universe()
    canary = select_canary(peers, CANARY_N_TICKERS)
    remaining = [t for t in peers if t not in canary]
    hard_cap = len(remaining) * EXPECTED_CALLS_PER_TICKER

    print(f"Candidate peer universe (placeholder linkage): {len(peers)}")
    print(f"Already covered by stage-1 canary            : {len(canary)}")
    print(f"Remaining to audit                           : {len(remaining)}")
    print(f"  {', '.join(remaining)}")
    print(f"Hard cap: {hard_cap} provider calls "
          f"({len(remaining)} x {EXPECTED_CALLS_PER_TICKER} observed in canary)")
    print(f"Pacing  : {INTER_CALL_DELAY_SECONDS}s between every provider call")
    print("Provider: yfinance, UNAUTHENTICATED public endpoint (no API key, $0.00)")
    print()
    print(f"Estimated wall clock: ~{hard_cap * INTER_CALL_DELAY_SECONDS:.0f}s of pacing "
          f"plus request time. Running...")
    print()

    run = run_audit(remaining, stage="full", hard_cap_calls=hard_cap,
                    delay_seconds=INTER_CALL_DELAY_SECONDS)

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
    print("=== STAGE 2 SUMMARY ===")
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

    write_report(run, REPORT_PATH)
    print()
    print(f"Wrote: {REPORT_PATH.relative_to(REPO_ROOT)}")
    print()
    print("REMINDER: current-chain coverage only. yfinance has no historical")
    print("endpoint, so this does NOT establish that IV is viable as a Stage 1")
    print("target -- realized volatility remains the default (Patch 13 caveat).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
