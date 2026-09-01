#!/usr/bin/env python3
"""Anchor-side closes: what to collect, and the shock derived from them.

=== WHY THE ANCHOR SIDE IS SEPARABLE, AND WHY THAT MATTERS ===

Since registry v1.9, `required_eligibility_class` is HYP04-ANCHOR-SHOCK-RULE-v1
-- not HYP-01's attention screen. An anchor event becomes ELIGIBLE when its
earnings-day excess return is well measured, which needs the anchor's closes and
the benchmark's, and NOTHING ELSE. No peer, no linkage edge, no attention
series, no option chain.

So the anchor side can be completed while the peer side is still blocked on the
linkage map (C5) and on a survivorship-bias-free peer source. That is the whole
point of this module: it is the one path to C2 that does not wait on either.

=== IT IS ALSO WHERE THE SURVIVORSHIP ARGUMENT DOES NOT APPLY, BY LUCK ===

`peer_price_data_policy` requires a survivorship-bias-free PEER source, and the
repo has measured that the provider it used returns zero rows for ODP across its
entire history. That policy governs the peer side.

The anchor side happens to be clean: all eight members of the point-in-time
universe are currently listed. That is an OBSERVATION ABOUT THIS UNIVERSE, not a
property of the rule -- the universe is derived point-in-time from historical
10-Ks and its intervals include exits, so a future re-walk could perfectly well
admit a delisted anchor. `survivorship_exposure()` reports the position rather
than assuming it, so the day it stops being true is visible.

=== THE REQUEST IS THE SPECIFICATION ===

Same direction `run_peer_closes_fetch` states for the peer side: this module
derives the exact (ticker, session) pairs from the XNYS calendar, and the
provider is checked against them. A session the provider does not return is left
EMPTY and reported -- never interpolated, carried forward, or set to zero.

Two closes per (ticker, event): the attributed session and the one before it,
because a daily return needs both. Deduplicated across events, because anchors
report quarterly and SPY appears in every event.

=== IT DOES NOT DECIDE WHICH SESSION A RELEASE AFFECTS. IT RESOLVES IT. ===

`earnings_events` classifies a release as BMO / AMC / UNKNOWN from the
acceptance timestamp and refuses to guess. This module turns that into a
SESSION against the trading calendar:

    BMO      -> the release date itself if it is a session, else the next one
    AMC      -> the next session strictly after the release date
    UNKNOWN  -> DENIED. AS-1 cannot be satisfied without a resolved session, and
                a guess here is a mis-dated anchor event.

An off-by-one here is look-ahead, silently, exactly as `event_panel` warns.
Neither error raises; both produce a finite number.

=== NOTHING HERE FETCHES ===

This module derives requirements and computes shocks from closes handed to it.
It imports no provider and opens no socket. Filling a request is
`run_peer_closes_fetch`'s job and requires the repo owner's staged go-ahead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .anchor_shock import (
    BENCHMARK_TICKER,
    RETURN_BASIS,
    AnchorShock,
    shock_for_event,
)
from .earnings_events import SESSION_AMC, SESSION_BMO

ANCHOR_CLOSES_RULE_ID = "HYP04-ANCHOR-CLOSES-REQUEST-v1"

# A daily return needs the close on the session and the close before it.
CLOSES_PER_TICKER_PER_EVENT = 2

REQUEST_CSV_SUFFIX = "_closes_REQUEST.csv"


class AnchorClosesError(ValueError):
    """Programming errors only. Bad event data is REPORTED, not raised."""


@dataclass(frozen=True)
class ResolvedAnchorEvent:
    """One calendar event pinned to the session its shock is measured on."""

    event_id: str
    anchor_ticker: str
    release_date: str
    release_session: str          # BMO | AMC | UNKNOWN
    attributed_session: str       # ISO date, resolved against XNYS
    prior_session: str            # the close the return is computed from

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "anchor_ticker": self.anchor_ticker,
            "release_date": self.release_date,
            "release_session": self.release_session,
            "attributed_session": self.attributed_session,
            "prior_session": self.prior_session,
        }


@dataclass(frozen=True)
class DeniedAnchorEvent:
    event_id: str
    anchor_ticker: str
    release_date: str
    release_session: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "anchor_ticker": self.anchor_ticker,
            "release_date": self.release_date,
            "release_session": self.release_session,
            "reason": self.reason,
        }


@dataclass
class AnchorClosesRequest:
    """What to collect. Every session here is load-bearing for some event."""

    rule_id: str = ANCHOR_CLOSES_RULE_ID
    resolved: list[ResolvedAnchorEvent] = field(default_factory=list)
    denied: list[DeniedAnchorEvent] = field(default_factory=list)
    sessions_by_ticker: dict[str, list[str]] = field(default_factory=dict)
    return_basis: str = RETURN_BASIS
    benchmark_ticker: str = BENCHMARK_TICKER

    @property
    def total_rows(self) -> int:
        return sum(len(v) for v in self.sessions_by_ticker.values())

    @property
    def tickers(self) -> list[str]:
        return sorted(self.sessions_by_ticker)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "return_basis": self.return_basis,
            "benchmark_ticker": self.benchmark_ticker,
            "events_resolved": len(self.resolved),
            "events_denied": len(self.denied),
            "tickers": self.tickers,
            "rows_per_ticker": {t: len(s)
                                for t, s in sorted(self.sessions_by_ticker.items())},
            "total_rows": self.total_rows,
            "closes_per_ticker_per_event": CLOSES_PER_TICKER_PER_EVENT,
            "denied": [d.as_dict() for d in self.denied],
            "measurement_status": (
                "A REQUEST. No close has been collected and no shock has been "
                "computed from production data. Emitting a request moves no "
                "gate and creates no eligible anchor event."),
        }


def _iso(d: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(d))
    except (TypeError, ValueError):
        return None


def resolve_attributed_session(
    release_date: str, release_session: str, sessions: Sequence[date],
) -> tuple[Optional[date], Optional[date], str]:
    """(attributed, prior, reason). A missing pair means the event is DENIED.

    Delegates nothing and guesses nothing: the BMO/AMC classification is
    `earnings_events`', the trading calendar is the caller's, and this only
    joins them. UNKNOWN denies, because AS-1 requires the session the release is
    attributed to and there is no honest default for it.
    """
    d = _iso(release_date)
    if d is None:
        return None, None, f"release_date {release_date!r} is not an ISO date"

    s = (release_session or "").strip().upper()
    if s == SESSION_BMO:
        # Before the open, so the release lands on that session -- unless the
        # release date is not a trading day at all, in which case the first
        # session that can react is the next one.
        idx = next((i for i, x in enumerate(sessions) if x >= d), None)
    elif s == SESSION_AMC:
        # After the close, so the first session that can react is the next one.
        idx = next((i for i, x in enumerate(sessions) if x > d), None)
    else:
        return None, None, (
            f"release session {release_session!r} is unresolved. AS-1 needs the "
            "session the release is attributed to; this module refuses to guess "
            "it, for the same reason earnings_events refuses to classify it.")

    if idx is None:
        return None, None, (
            f"no trading session on or after {d.isoformat()} in the supplied "
            "index; extend it rather than clipping the request")
    if idx == 0:
        return None, None, (
            f"the attributed session {sessions[0].isoformat()} is the FIRST in "
            "the index, so the prior close a return needs is outside it")
    return sessions[idx], sessions[idx - 1], ""


def build_request(
    entries: Iterable[dict[str, Any]],
    *,
    sessions: Sequence[date],
    benchmark_ticker: str = BENCHMARK_TICKER,
) -> AnchorClosesRequest:
    """Derive the exact closes to collect for a set of calendar rows.

    `entries` are calendar CSV rows: event_id, anchor_ticker, release_date,
    release_session.
    """
    idx = sorted({s for s in sessions})
    req = AnchorClosesRequest(benchmark_ticker=benchmark_ticker)
    wanted: dict[str, set[str]] = {}

    for row in entries:
        eid = str(row.get("event_id", "")).strip()
        tk = str(row.get("anchor_ticker", "")).strip().upper()
        rd = str(row.get("release_date", "")).strip()
        rs = str(row.get("release_session", "")).strip().upper()

        if not eid or not tk:
            req.denied.append(DeniedAnchorEvent(
                eid, tk, rd, rs, "blank event_id or anchor_ticker"))
            continue

        attributed, prior, why = resolve_attributed_session(rd, rs, idx)
        if attributed is None or prior is None:
            req.denied.append(DeniedAnchorEvent(eid, tk, rd, rs, why))
            continue

        req.resolved.append(ResolvedAnchorEvent(
            event_id=eid, anchor_ticker=tk, release_date=rd,
            release_session=rs,
            attributed_session=attributed.isoformat(),
            prior_session=prior.isoformat()))

        # The benchmark is needed on the SAME sessions. AS-3 denies without it,
        # and a missing benchmark is never read as zero.
        for t in (tk, benchmark_ticker):
            wanted.setdefault(t, set()).update(
                {attributed.isoformat(), prior.isoformat()})

    req.sessions_by_ticker = {t: sorted(v) for t, v in sorted(wanted.items())}
    return req


def write_request_csvs(req: AnchorClosesRequest, out_dir: Path
                       ) -> list[tuple[Path, int]]:
    """One pre-filled request file per ticker; the close column left EMPTY.

    Empty, never zero. A zero close is not a real observation and a zero return
    is -- conflating them is how a halt becomes a flat session.
    """
    import csv as _csv

    from .closes_requirements import request_csv_header

    header = request_csv_header()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, int]] = []

    for ticker, sess in sorted(req.sessions_by_ticker.items()):
        path = out_dir / f"{ticker}{REQUEST_CSV_SUFFIX}"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(header)
            for s in sess:
                row = []
                for col in header:
                    if col == "ticker":
                        row.append(ticker)
                    elif col == "session_date":
                        row.append(s)
                    else:
                        row.append("")
                w.writerow(row)
        written.append((path, len(sess)))
    return written


def survivorship_exposure(tickers: Iterable[str],
                          listed_today: Iterable[str]) -> dict[str, Any]:
    """Report the anchor side's survivorship position. Never assume it.

    The anchor universe currently contains no delisted member, which is why the
    peer-side survivorship problem does not bite here. That is a fact about this
    universe on this date, not a property of the rule, so it is MEASURED and
    reported -- the day it stops being true has to be visible rather than
    inferred from silence.
    """
    want = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    have = {str(t).strip().upper() for t in listed_today}
    missing = [t for t in want if t not in have]
    return {
        "tickers_required": want,
        "tickers_not_currently_listed": missing,
        "anchor_side_survivorship_clean": not missing,
        "why_this_is_not_the_peer_side_policy": (
            "peer_price_data_policy requires a survivorship-bias-free PEER "
            "source and is unchanged. This reports the ANCHOR side only."),
        "not_a_property_of_the_rule": (
            "The anchor universe is derived point-in-time and its intervals "
            "include exits, so a future re-walk can admit a delisted anchor. A "
            "clean result here is an observation about today's universe."),
    }


def shocks_for_request(
    req: AnchorClosesRequest,
    closes: dict[str, dict[str, float]],
) -> tuple[list[AnchorShock], list[dict[str, Any]]]:
    """Compute one shock per resolved event. Returns (shocks, denials).

    `closes` is {ticker: {session_date: close}}. Every arithmetic step is
    delegated to `anchor_shock`, which fails closed on each unknown; this
    function only assembles the two returns.

    RETURN BASIS IS LOG, matching peer_returns and declared by registry v1.10.
    Both legs use it -- mixing bases would put a systematic wedge in every
    excess return, largest on exactly the big-move days that carry the signal.
    """
    import math

    shocks: list[AnchorShock] = []
    denials: list[dict[str, Any]] = []

    def _ret(ticker: str, prior: str, session: str) -> tuple[Optional[float], str]:
        series = closes.get(ticker) or {}
        p0, p1 = series.get(prior), series.get(session)
        for label, v, when in (("prior", p0, prior), ("session", p1, session)):
            if v is None:
                return None, (f"{ticker} has no close for the {label} session "
                              f"{when}; it is absent, not zero")
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return None, f"{ticker} close for {when} is not a number: {v!r}"
            if not math.isfinite(fv) or fv <= 0.0:
                return None, (f"{ticker} close for {when} is {v!r}; a "
                              "non-positive or non-finite close makes "
                              "log(p_t/p_{t-1}) undefined and is treated as "
                              "absent rather than substituted")
        return math.log(float(p1) / float(p0)), ""

    for ev in req.resolved:
        a, why_a = _ret(ev.anchor_ticker, ev.prior_session,
                        ev.attributed_session)
        b, why_b = _ret(req.benchmark_ticker, ev.prior_session,
                        ev.attributed_session)
        reasons = [w for w in (why_a, why_b) if w]
        if reasons:
            denials.append({"event_id": ev.event_id,
                            "anchor_ticker": ev.anchor_ticker,
                            "attributed_session": ev.attributed_session,
                            "reasons": reasons})
            continue

        shock, why = shock_for_event(
            event_id=ev.event_id, anchor_ticker=ev.anchor_ticker,
            attributed_session=ev.attributed_session,
            anchor_return=a, benchmark_return=b)
        if shock is None:
            denials.append({"event_id": ev.event_id,
                            "anchor_ticker": ev.anchor_ticker,
                            "attributed_session": ev.attributed_session,
                            "reasons": why})
            continue
        shocks.append(shock)

    return shocks, denials
