#!/usr/bin/env python3
"""Options-coverage data-availability audit -- HYP-04 Phase 0, build step 2.

MAKES REAL, BILLABLE PROVIDER CALLS. Refuses to run without an explicit,
owner-supplied budget (Patch 13).

WHY THIS EXISTS (plan Section 3): the Stage 1 target is realized volatility
BY DEFAULT, because realized vol is computable for 100% of the peer universe
from price data this repo already holds. Peer implied vol is promoted to a
secondary/robustness target ONLY for the subset with confirmed clean
historical options coverage -- and the coverage percentage must be REPORTED
BEFORE that promotion decision is made. Do not decide first and check second.

CONSENT MODEL (Patch 13). The budget is real money and is not a methodology
choice, so neither this module nor its caller may invent one. It arrives from
the repo owner in two stages:

  1. CANARY -- a small hard cap (5-10 tickers) run first, to establish real
     OBSERVED cost-per-call and surface anything unexpected (a ticker costing
     more calls than assumed, an unanticipated pricing tier) while exposure
     is still small.
  2. FULL   -- extrapolated from the canary's real numbers to the full
     candidate universe, stated as a hard number.

Hitting either cap STOPS AND REPORTS. It never silently truncates the
universe and calls the result a coverage measurement -- a truncated audit
that looked like a complete one would corrupt exactly the number the
promotion decision depends on.

PROVIDER NOTE. This uses the same path as HYP-01's real-quote validation:
yfinance, via GST_Option_Chain_Core. That is an UNAUTHENTICATED public
endpoint -- no API key, no credential of any kind. It is NOT the Alpaca
provider (gst_market_response.alpaca_provider), which serves intraday price
bars and does require APCA_API_KEY_ID / APCA_API_SECRET_KEY.

yfinance has a recorded live failure in this repo (2026-08-04, Pass 1:
zero bars, traced to its internal crumb/cookie negotiation, while a direct
curl to the same endpoint succeeded -- see
GST_MARKET_RESPONSE_PROVIDER_LIMITATIONS_v0.1.md). A transport failure is
therefore reported as a transport failure, never as "this ticker has no
options coverage". Those are different findings and conflating them would
silently understate coverage.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .constants import (
    AUDIT_CONSENT_STAGES,
    AUDIT_NO_BUDGET_MESSAGE,
)


class AuditBudgetError(RuntimeError):
    """Raised when the audit is asked to run without an owner-supplied cap."""


class AuditBudgetExhausted(RuntimeError):
    """Raised when the hard cap is reached. Stops; never continues past it."""


# Coverage outcomes. TRANSPORT_FAILED is deliberately distinct from
# NO_OPTIONS -- see module docstring.
class Coverage:
    OK = "ok"                          # expirations AND a readable chain
    NO_OPTIONS = "no_options"          # provider responded, ticker has no chain
    EMPTY_CHAIN = "empty_chain"        # expirations listed but chain unreadable/empty
    TRANSPORT_FAILED = "transport_failed"   # provider/network defect, NOT a coverage fact
    NOT_ATTEMPTED = "not_attempted"    # budget stopped us before reaching this ticker


@dataclass
class TickerAuditResult:
    ticker: str
    coverage: str
    calls_made: int
    n_expirations: Optional[int] = None
    n_calls_contracts: Optional[int] = None
    n_puts_contracts: Optional[int] = None
    first_expiration: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class AuditRun:
    stage: str
    hard_cap_calls: int
    tickers_requested: list[str]
    results: list[TickerAuditResult] = field(default_factory=list)
    total_calls: int = 0
    budget_exhausted: bool = False
    started_utc: str = ""
    finished_utc: str = ""
    provider: str = "yfinance (unauthenticated) via GST_Option_Chain_Core path"
    credentials_used: str = "none -- unauthenticated public endpoint"
    delay_seconds: float = 0.0

    def summary(self) -> dict[str, Any]:
        attempted = [r for r in self.results if r.coverage != Coverage.NOT_ATTEMPTED]
        ok = [r for r in attempted if r.coverage == Coverage.OK]
        transport = [r for r in attempted if r.coverage == Coverage.TRANSPORT_FAILED]
        per_ticker = [r.calls_made for r in attempted]
        return {
            "stage": self.stage,
            "hard_cap_calls": self.hard_cap_calls,
            "total_calls": self.total_calls,
            "budget_exhausted": self.budget_exhausted,
            "tickers_requested": len(self.tickers_requested),
            "tickers_attempted": len(attempted),
            "tickers_not_attempted": len(self.results) - len(attempted),
            "coverage_ok": len(ok),
            "coverage_ok_pct": (100.0 * len(ok) / len(attempted)) if attempted else None,
            "transport_failures": len(transport),
            "calls_per_ticker_min": min(per_ticker) if per_ticker else None,
            "calls_per_ticker_max": max(per_ticker) if per_ticker else None,
            "calls_per_ticker_mean": (sum(per_ticker) / len(per_ticker)) if per_ticker else None,
            "calls_per_ticker_constant": (len(set(per_ticker)) == 1) if per_ticker else None,
        }


def _count_call(run: AuditRun) -> None:
    """Charge one provider call against the cap. Stops AT the cap, not past it."""
    if run.total_calls >= run.hard_cap_calls:
        run.budget_exhausted = True
        raise AuditBudgetExhausted(
            f"hard cap of {run.hard_cap_calls} provider calls reached; stopping. "
            f"No further calls will be made and the universe is NOT truncated "
            f"silently -- unreached tickers are recorded as "
            f"{Coverage.NOT_ATTEMPTED!r}."
        )
    run.total_calls += 1


def audit_one_ticker(ticker: str, run: AuditRun, *, yf_module,
                     delay_seconds: float = 0.0) -> TickerAuditResult:
    """Two provider calls per ticker when things go normally.

    Call 1: tk.options            -- the expiration list
    Call 2: tk.option_chain(exp)  -- one chain, to prove it is readable

    Only the FIRST expiration's chain is fetched. Phase 0 asks whether a
    usable historical chain exists at all, not how deep the surface goes, so
    walking every expiration would multiply cost for no Phase 0 decision.
    """
    t0 = time.time()
    tk = yf_module.Ticker(ticker)

    _count_call(run)
    calls = 1
    try:
        expirations = tuple(tk.options)
    except Exception as e:                      # transport, not a coverage fact
        return TickerAuditResult(
            ticker=ticker, coverage=Coverage.TRANSPORT_FAILED, calls_made=calls,
            elapsed_seconds=round(time.time() - t0, 3),
            error_type=type(e).__name__, error_message=str(e)[:300],
        )

    if not expirations:
        return TickerAuditResult(
            ticker=ticker, coverage=Coverage.NO_OPTIONS, calls_made=calls,
            n_expirations=0, elapsed_seconds=round(time.time() - t0, 3),
        )

    if delay_seconds:
        time.sleep(delay_seconds)

    _count_call(run)
    calls = 2
    try:
        chain = tk.option_chain(expirations[0])
        n_calls, n_puts = len(chain.calls), len(chain.puts)
    except Exception as e:
        return TickerAuditResult(
            ticker=ticker, coverage=Coverage.TRANSPORT_FAILED, calls_made=calls,
            n_expirations=len(expirations), first_expiration=expirations[0],
            elapsed_seconds=round(time.time() - t0, 3),
            error_type=type(e).__name__, error_message=str(e)[:300],
        )

    coverage = Coverage.OK if (n_calls or n_puts) else Coverage.EMPTY_CHAIN
    return TickerAuditResult(
        ticker=ticker, coverage=coverage, calls_made=calls,
        n_expirations=len(expirations), n_calls_contracts=n_calls,
        n_puts_contracts=n_puts, first_expiration=expirations[0],
        elapsed_seconds=round(time.time() - t0, 3),
    )


def run_audit(
    tickers: list[str],
    *,
    stage: str,
    hard_cap_calls: Optional[int],
    yf_module=None,
    delay_seconds: float = 0.0,
) -> AuditRun:
    """Run the coverage audit under an owner-supplied hard cap.

    `hard_cap_calls` MUST be supplied by the repo owner. There is no default
    and no fallback: passing None raises rather than guessing a number.

    `delay_seconds` paces EVERY provider call -- between the two calls within
    a ticker as well as between tickers. Patch 13's Round 5 correction
    establishes that the binding constraint for this provider is rate-limiting
    and fragility, not money (yfinance is free and unauthenticated), so pacing
    is the insurance that matters here. This repo has already lost one live
    diagnostic to this provider's crumb/cookie negotiation (2026-08-04).
    """
    if hard_cap_calls is None:
        raise AuditBudgetError(AUDIT_NO_BUDGET_MESSAGE)
    if stage not in AUDIT_CONSENT_STAGES:
        raise AuditBudgetError(
            f"unknown consent stage {stage!r}; expected one of {AUDIT_CONSENT_STAGES}"
        )
    if yf_module is None:
        import yfinance as yf_module  # noqa: PLC0415  (deferred: import costs nothing until a real run)

    run = AuditRun(
        stage=stage,
        hard_cap_calls=int(hard_cap_calls),
        tickers_requested=list(tickers),
        started_utc=datetime.now(timezone.utc).isoformat(),
        delay_seconds=float(delay_seconds),
    )

    for i, t in enumerate(tickers):
        if delay_seconds and i:
            time.sleep(delay_seconds)
        try:
            run.results.append(audit_one_ticker(
                t, run, yf_module=yf_module, delay_seconds=delay_seconds))
        except AuditBudgetExhausted:
            # Index by the LOOP POSITION, never by tickers.index(t): a repeated
            # ticker would resolve to its first occurrence and duplicate every
            # entry after it, inflating the result list past the requested
            # universe. Caught by the smoke test's duplicate-ticker case.
            run.results.append(TickerAuditResult(
                ticker=t, coverage=Coverage.NOT_ATTEMPTED, calls_made=0))
            for remaining in tickers[i + 1:]:
                run.results.append(TickerAuditResult(
                    ticker=remaining, coverage=Coverage.NOT_ATTEMPTED, calls_made=0))
            break

    run.finished_utc = datetime.now(timezone.utc).isoformat()
    return run


def write_report(run: AuditRun, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "artifact": "HYP-04 Phase 0 options-coverage audit",
        "consent_stage": run.stage,
        "provider": run.provider,
        "credentials_used": run.credentials_used,
        "hard_cap_calls": run.hard_cap_calls,
        "inter_call_delay_seconds": run.delay_seconds,
        "budget_exhausted": run.budget_exhausted,
        "started_utc": run.started_utc,
        "finished_utc": run.finished_utc,
        "summary": run.summary(),
        "per_ticker": [asdict(r) for r in run.results],
        "not_a_claim": (
            "Coverage is a data-availability measurement only. It is not "
            "evidence for or against any hedging edge, and it does not by "
            "itself promote IV to a Stage 1 target."
        ),
    }, indent=1), encoding="utf-8")
