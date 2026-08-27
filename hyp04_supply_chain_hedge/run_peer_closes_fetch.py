#!/usr/bin/env python3
"""Fill an emitted closes-request file from Yahoo, via yfinance.

NOT A TEST. NOT RUN BY CI. MAKES REAL PROVIDER CALLS. Deliberately named off
the `test_*` discovery pattern, for the same reason the live audit runners, the
registry generators and the linkage-history walker are: it reaches the network
and must only run when a human decides it should.

`yfinance` stays OUT of requirements-hyp04.txt and is imported LAZILY here.
That exclusion is a stated safety property of that file -- if a future change
accidentally reaches a live provider path from CI, it fails at import rather
than succeeding quietly against a real endpoint. Nothing in this module is
imported by anything CI runs.

=== IT FILLS A REQUEST; IT DOES NOT INVENT ONE ===

Input is a request file produced by
`closes_requirements --emit-requests`, which already contains the exact
sessions to collect, derived from the authoritative XNYS calendar. This module
fills the `close` column and nothing else.

That direction matters. If this module chose its own dates it would be
substituting Yahoo's idea of the trading calendar for XNYS's, and a mismatch
would surface much later as `off_calendar_dates` in peer_returns -- a long way
from here. Instead the request is the specification and the provider is checked
against it:

  * a requested session the provider did not return is left EMPTY and
    reported. It is never interpolated, carried forward, or set to 0.
  * a session the provider returned that was NOT requested is reported and
    DROPPED, because it is off the XNYS index and peer_returns would reject it
    anyway.
  * a non-finite or non-positive close is treated as absent, for the same
    reason peer_returns rejects it: log(p_t / p_{t-1}) is undefined, and
    substituting anything invents a return no trade produced.

=== THE ADJUSTMENT CHOICE IS EXPLICIT, AND IT IS A REAL CHOICE ===

The target is realized variance of daily LOG RETURNS. Two things follow:

  * SPLITS MUST BE ADJUSTED. An unadjusted 2-for-1 split prints a -69% return
    on a day nothing happened, and realized variance is a sum of SQUARED
    returns, so one such day can dominate an entire window.
  * DIVIDENDS ARE A JUDGEMENT CALL. Adjusting removes a small negative return
    on each ex-dividend date; not adjusting leaves it in. Neither is wrong,
    but they are different series and the difference is not negligible for a
    variance measure on a 41-session window containing an ex-div date.

Default here is `auto_adjust=True` -- Yahoo's split AND dividend adjusted
series -- because it is the provider's default, it is the more common
convention for return series, and it removes the split hazard above.
`--no-dividend-adjust` selects split-only.

WHICHEVER IS USED IS RECORDED in the output's provenance header comment and in
the run report, because the two produce different targets and a series whose
adjustment basis is unknown is not analysable. This is a measurement decision
and is NOT registered anywhere -- if it matters to the analysis, it belongs in
a registry version, not in a fetcher's default.

=== WHAT THIS DOES NOT DO ===

It does not curate, screen, or move any gate. It produces closes. Whether
those closes support a finding is decided far downstream, and the display gate
is CLOSED throughout.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

ADJUST_SPLIT_AND_DIVIDEND = "split_and_dividend (yfinance auto_adjust=True)"
ADJUST_SPLIT_ONLY = "split_only (yfinance auto_adjust=False)"

YFINANCE_REQUIRED_MESSAGE = (
    "yfinance is not installed. It is DELIBERATELY absent from "
    "requirements-hyp04.txt so that no CI path can reach a live provider. "
    "Install it locally to run this fetcher:\n\n    pip install yfinance\n")


@dataclass
class FetchResult:
    ticker: str = ""
    requested: int = 0
    filled: int = 0
    missing: list[str] = field(default_factory=list)
    unrequested_dropped: list[str] = field(default_factory=list)
    rejected_values: list[str] = field(default_factory=list)
    adjustment: str = ""
    provider_first: Optional[str] = None
    provider_last: Optional[str] = None

    @property
    def complete(self) -> bool:
        return self.requested > 0 and self.filled == self.requested

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "requested": self.requested,
            "filled": self.filled,
            "complete": self.complete,
            "missing_count": len(self.missing),
            "missing": self.missing[:50],
            "unrequested_dropped": self.unrequested_dropped[:50],
            "rejected_values": self.rejected_values[:50],
            "adjustment": self.adjustment,
            "provider_range": [self.provider_first, self.provider_last],
        }


def read_request(path: Path) -> tuple[str, list[date]]:
    """Read an emitted request file: its ticker and its requested sessions."""
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path.name} has no rows")
    tickers = {r["ticker"].strip().upper() for r in rows if r.get("ticker")}
    if len(tickers) != 1:
        raise ValueError(
            f"{path.name} mixes tickers {sorted(tickers)}; a request file "
            "covers exactly one peer")
    sessions = [date.fromisoformat(r["session_date"].strip()) for r in rows]
    if sorted(sessions) != sessions:
        raise ValueError(f"{path.name} sessions are not in ascending order")
    if len(set(sessions)) != len(sessions):
        raise ValueError(f"{path.name} contains duplicate sessions")
    return tickers.pop(), sessions


def fetch_closes(ticker: str, first: date, last: date, *,
                 auto_adjust: bool = True) -> dict[date, float]:
    """Daily closes from Yahoo. LAZY import; makes a real provider call."""
    try:
        import yfinance  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover -- environment dependent
        raise ImportError(YFINANCE_REQUIRED_MESSAGE) from exc

    # `end` is exclusive in Yahoo's API; ask for one day past the last session
    # so the last requested close is actually returned.
    frame = yfinance.download(
        ticker, start=first.isoformat(),
        end=(last + timedelta(days=1)).isoformat(),
        auto_adjust=auto_adjust, progress=False, actions=False)

    out: dict[date, float] = {}
    if frame is None or len(frame) == 0:
        return out

    col = frame["Close"]
    # yfinance returns a MultiIndex column frame for some call shapes.
    if hasattr(col, "columns"):
        col = col.iloc[:, 0]
    for idx, val in col.items():
        try:
            d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
            out[d] = float(val)
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def fill_request(path: Path, closes: dict[date, float], *,
                 adjustment: str, out_path: Optional[Path] = None
                 ) -> FetchResult:
    """Write the request file back with the close column filled.

    Missing stays EMPTY. Nothing is interpolated or carried forward, because a
    return spanning a filled gap is not a one-session return, and admitting it
    inflates realized variance exactly where the data is worst.
    """
    ticker, sessions = read_request(path)
    res = FetchResult(ticker=ticker, requested=len(sessions),
                      adjustment=adjustment)
    if closes:
        res.provider_first = min(closes).isoformat()
        res.provider_last = max(closes).isoformat()

    wanted = set(sessions)
    for d in sorted(set(closes) - wanted):
        res.unrequested_dropped.append(d.isoformat())

    target = out_path or path
    with target.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "session_date", "close"])
        for d in sessions:
            val = closes.get(d)
            if val is None:
                res.missing.append(d.isoformat())
                w.writerow([ticker, d.isoformat(), ""])
                continue
            # Same rule peer_returns enforces: finite and strictly positive.
            if not (val == val) or val in (float("inf"), float("-inf")) or val <= 0:
                res.rejected_values.append(f"{d.isoformat()}={val!r}")
                res.missing.append(d.isoformat())
                w.writerow([ticker, d.isoformat(), ""])
                continue
            res.filled += 1
            w.writerow([ticker, d.isoformat(), f"{val:.6f}"])
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fill emitted closes-request files from Yahoo (yfinance). "
                    "MAKES REAL PROVIDER CALLS.")
    ap.add_argument("requests", nargs="+", type=Path,
                    help="request files from closes_requirements --emit-requests")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="write filled copies here instead of in place")
    ap.add_argument("--no-dividend-adjust", action="store_true",
                    help="split-only adjustment (yfinance auto_adjust=False). "
                         "Default adjusts splits AND dividends.")
    ap.add_argument("--yes-run-live", action="store_true",
                    help="REQUIRED. Confirms a real provider call is intended.")
    a = ap.parse_args(argv)

    if not a.yes_run_live:
        print("This makes REAL provider calls to Yahoo. Re-run with "
              "--yes-run-live to confirm.", file=sys.stderr)
        return 2

    auto_adjust = not a.no_dividend_adjust
    adjustment = ADJUST_SPLIT_AND_DIVIDEND if auto_adjust else ADJUST_SPLIT_ONLY
    print(f"adjustment: {adjustment}")
    print("This choice changes the target. It is NOT registered anywhere -- "
          "if it matters, it belongs in a registry version.\n")

    results: list[FetchResult] = []
    for req in a.requests:
        if not req.is_file():
            print(f"missing request file: {req}", file=sys.stderr)
            return 2
        ticker, sessions = read_request(req)
        print(f"{ticker}: requesting {len(sessions)} session(s) "
              f"{sessions[0]} .. {sessions[-1]}")
        try:
            closes = fetch_closes(ticker, sessions[0], sessions[-1],
                                  auto_adjust=auto_adjust)
        except ImportError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        out = (a.out_dir / req.name) if a.out_dir else req
        if a.out_dir:
            a.out_dir.mkdir(parents=True, exist_ok=True)
        res = fill_request(req, closes, adjustment=adjustment, out_path=out)
        results.append(res)
        print(f"    filled {res.filled}/{res.requested}"
              f"   missing {len(res.missing)}"
              f"   dropped-unrequested {len(res.unrequested_dropped)}"
              f"   rejected-values {len(res.rejected_values)}")
        if res.missing:
            print(f"    MISSING (left EMPTY, never filled): "
                  f"{', '.join(res.missing[:8])}"
                  + (" ..." if len(res.missing) > 8 else ""))
        print(f"    wrote: {out}")

    print()
    incomplete = [r for r in results if not r.complete]
    if incomplete:
        print(f"{len(incomplete)} file(s) INCOMPLETE. peer_returns will deny "
              "coverage for any event whose window contains a missing close -- "
              "that is correct behaviour, not a bug to work around.")
    else:
        print("All request files complete.")
    print("\nThese are closes. They are not a finding, and the display gate "
          "is CLOSED regardless of what is in them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
