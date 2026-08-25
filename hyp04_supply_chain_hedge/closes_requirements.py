#!/usr/bin/env python3
"""What closes an operator must actually supply -- HYP-04.

The linkage-source decision of 2026-08-23 chose operator-supplied CSVs over a
price vendor. That leaves a practical question the rest of the package does not
answer: **which closes, for which tickers, on which dates?**

"Get some prices for CVS" is not an answerable instruction. This module turns
it into a checkable list, derived from the same constants the target uses, so
the request and the analysis cannot drift apart.

=== THE OFF-BY-ONE THAT MATTERS ===

It is tempting to say a 20-session reference window plus a 20-session horizon
needs 40 closes. It needs 41.

`coverage_for_event` requires finite RETURNS across
`[anchor_day - 19 .. anchor_day + 20]` -- 40 of them. A return at index `i` is
`log(close[i] / close[i-1])`, so it needs closes at BOTH `i-1` and `i`. The
earliest required return is at `anchor_day - 19`, which needs a close at
`anchor_day - 20`.

Ask for 40 and the first reference return cannot be computed. Coverage then
denies the pair with "reference window has 19/20 finite returns", which is
correct but points at the window rather than at the missing close -- a
confusing failure a long way from its cause.

=== IT REPORTS SESSIONS, NOT A DATE RANGE ===

The output is the explicit list of sessions, not `min..max`. A vendor asked for
a date range returns what it thinks the sessions are, and a mismatch between
that calendar and this one shows up later as `off_calendar_dates` or as holes.
Naming the sessions makes the request verifiable before the data is collected.

=== IT APPLIES P3, SO IT NEVER ASKS FOR DATA THAT CANNOT BE USED ===

A pair whose edge was disclosed after the event is ineligible under
`pair_eligibility` P3 no matter what prices exist. Requesting its closes would
waste the operator's effort on observations the analysis must discard, so those
pairs are reported as skipped, with the reason, rather than silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .constants import HORIZON_GRID, REFERENCE_WINDOW_TRADING_DAYS
from .curated_linkage import CuratedEdge
from .event_panel import ResolvedEvent, normalize_sessions


@dataclass(frozen=True)
class SkippedPair:
    anchor: str
    peer: str
    event_id: str
    reason: str


@dataclass(frozen=True)
class PeerRequirement:
    """Every session of closes one peer needs, across all its events."""

    peer: str
    sessions: tuple[date, ...] = ()
    events_covered: tuple[str, ...] = ()

    @property
    def n_sessions(self) -> int:
        return len(self.sessions)

    @property
    def first(self) -> Optional[date]:
        return self.sessions[0] if self.sessions else None

    @property
    def last(self) -> Optional[date]:
        return self.sessions[-1] if self.sessions else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "peer": self.peer,
            "n_sessions": self.n_sessions,
            "first_session": self.first.isoformat() if self.first else None,
            "last_session": self.last.isoformat() if self.last else None,
            "events_covered": list(self.events_covered),
            "sessions": [d.isoformat() for d in self.sessions],
        }


@dataclass(frozen=True)
class RequirementsReport:
    requirements: tuple[PeerRequirement, ...] = ()
    skipped: tuple[SkippedPair, ...] = ()
    truncated: tuple[SkippedPair, ...] = ()
    reference_window: int = REFERENCE_WINDOW_TRADING_DAYS
    max_horizon: int = max(HORIZON_GRID)

    @property
    def total_rows(self) -> int:
        """Rows the operator must produce -- one per (peer, session)."""
        return sum(r.n_sessions for r in self.requirements)

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference_window": self.reference_window,
            "max_horizon": self.max_horizon,
            "closes_per_peer_per_event": closes_per_event(
                self.reference_window, self.max_horizon),
            "total_rows": self.total_rows,
            "peers": [r.as_dict() for r in self.requirements],
            "skipped": [vars(s) for s in self.skipped],
            "truncated": [vars(t) for t in self.truncated],
        }


def closes_per_event(reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
                     max_horizon: Optional[int] = None) -> int:
    """Closes needed for ONE (peer, event): reference + horizon + the prior close.

    The `+ 1` is the close before the first reference return. See the module
    docstring -- dropping it is the difference between a pair that resolves and
    one that denies for a reason pointing somewhere else.
    """
    h = int(max_horizon if max_horizon is not None else max(HORIZON_GRID))
    return reference_window + h + 1


def session_span(anchor_day: int, *,
                 reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
                 max_horizon: Optional[int] = None) -> tuple[int, int]:
    """Inclusive [start, end] session indices of closes needed for one event."""
    h = int(max_horizon if max_horizon is not None else max(HORIZON_GRID))
    return anchor_day - reference_window, anchor_day + h


def requirements_for(
    events: Sequence[ResolvedEvent],
    edges: Iterable[CuratedEdge],
    *,
    sessions: Sequence[date],
    reference_window: int = REFERENCE_WINDOW_TRADING_DAYS,
    max_horizon: Optional[int] = None,
) -> RequirementsReport:
    """Which closes to collect, per peer, for these events and this map.

    `events` are already pinned to the session index by `event_panel`. Edges
    whose `as_of_date` is not strictly before the event's response session are
    SKIPPED -- P3 would deny the pair regardless of the prices, so asking for
    them would waste effort on observations the analysis must discard.

    A span running off either end of the session index is reported as
    `truncated` rather than clipped: a clipped request looks complete and would
    be collected, and the pair would then fail coverage for a reason that
    points at the window instead of at the index.
    """
    idx = normalize_sessions(sessions)
    h = int(max_horizon if max_horizon is not None else max(HORIZON_GRID))

    by_anchor: dict[str, list[CuratedEdge]] = {}
    for e in edges:
        by_anchor.setdefault(e.anchor_ticker.upper(), []).append(e)

    wanted: dict[str, set[date]] = {}
    covered: dict[str, set[str]] = {}
    skipped: list[SkippedPair] = []
    truncated: list[SkippedPair] = []

    for ev in events:
        for edge in by_anchor.get(ev.anchor.upper(), []):
            peer = edge.peer_ticker.upper()

            # P3, applied here so the operator is never asked for unusable data.
            if not (edge.as_of_date and
                    str(edge.as_of_date) < ev.response_session_date.isoformat()):
                skipped.append(SkippedPair(
                    ev.anchor, peer, ev.event_id,
                    f"P3: edge as_of {edge.as_of_date!r} is not strictly before "
                    f"the response session {ev.response_session_date.isoformat()}"))
                continue

            start, end = session_span(ev.day_index,
                                      reference_window=reference_window,
                                      max_horizon=h)
            if start < 0 or end >= len(idx):
                truncated.append(SkippedPair(
                    ev.anchor, peer, ev.event_id,
                    f"needs sessions [{start}..{end}] but the index holds "
                    f"[0..{len(idx) - 1}]; extend it rather than collecting a "
                    "partial window"))
                continue

            wanted.setdefault(peer, set()).update(idx[start:end + 1])
            covered.setdefault(peer, set()).add(ev.event_id)

    reqs = tuple(
        PeerRequirement(peer=p, sessions=tuple(sorted(wanted[p])),
                        events_covered=tuple(sorted(covered.get(p, ()))))
        for p in sorted(wanted))

    return RequirementsReport(requirements=reqs, skipped=tuple(skipped),
                              truncated=tuple(truncated),
                              reference_window=reference_window, max_horizon=h)


def format_report(rep: RequirementsReport, *, max_sessions_shown: int = 6) -> str:
    """A human-readable request an operator can act on."""
    out: list[str] = []
    per = closes_per_event(rep.reference_window, rep.max_horizon)
    out.append(
        f"Closes needed: {per} sessions per (peer, event) -- "
        f"{rep.reference_window} reference + {rep.max_horizon} horizon + 1 "
        "prior close for the first reference return.")
    out.append(f"Schema: HYP04_Peer_Closes_TEMPLATE_headers.csv "
               f"(ticker,session_date,close)")
    out.append("")

    if not rep.requirements:
        out.append("NOTHING TO COLLECT -- no (event, peer) pair is usable.")
    for r in rep.requirements:
        shown = [d.isoformat() for d in r.sessions[:max_sessions_shown]]
        tail = "" if r.n_sessions <= max_sessions_shown else \
            f" ... (+{r.n_sessions - max_sessions_shown} more)"
        out.append(f"{r.peer}: {r.n_sessions} session(s) "
                   f"{r.first} .. {r.last}  for event(s) "
                   f"{', '.join(r.events_covered)}")
        out.append(f"    {', '.join(shown)}{tail}")

    out.append("")
    out.append(f"TOTAL ROWS TO PRODUCE: {rep.total_rows}")

    if rep.skipped:
        out.append("")
        out.append(f"SKIPPED -- {len(rep.skipped)} pair(s) P3 would deny "
                   "regardless of prices:")
        for s in rep.skipped:
            out.append(f"  {s.anchor} -> {s.peer} @ {s.event_id}: {s.reason}")

    if rep.truncated:
        out.append("")
        out.append(f"TRUNCATED -- {len(rep.truncated)} pair(s) need sessions "
                   "outside the supplied index:")
        for t in rep.truncated:
            out.append(f"  {t.anchor} -> {t.peer} @ {t.event_id}: {t.reason}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
#
# The session index MUST come from the authoritative XNYS calendar. A weekday
# approximation is not good enough here and is worse than refusing: it would
# put market holidays into the request, the operator would collect closes that
# do not exist, and the mismatch would surface later as off_calendar_dates --
# a long way from the CLI that caused it.
#
# `gst_market_response.exchange_calendar` imports `exchange_calendars`, which
# requirements-hyp04.txt deliberately does not install. So it is imported
# LAZILY, inside main() only. Importing this module never pulls it, HYP-04's CI
# job stays clean, and running the CLI without the dependency REFUSES with an
# actionable message rather than falling back to something approximate.
#
# This mirrors how edgar_linkage defers `requests`.

def _load_sessions(first: date, last: date) -> list[date]:
    from gst_market_response.exchange_calendar import is_trading_day

    out: list[date] = []
    d = first
    while d <= last:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Which peer closes an operator must collect for given "
                    "anchor events. Reads the curated linkage map; makes no "
                    "network call and writes nothing.")
    ap.add_argument("--event", action="append", default=[], metavar="ID:ANCHOR:DATE",
                    help="anchor event as ID:TICKER:YYYY-MM-DD, where DATE is "
                         "the RESPONSE session (resolve BMO/AMC first via "
                         "exchange_calendar."
                         "compute_expected_next_full_trading_session_xnys)")
    ap.add_argument("--events-csv", type=Path, default=None, metavar="CSV",
                    help="candidate events from earnings_events. Resolves "
                         "BMO/AMC to the response session for you; rows whose "
                         "release_session is UNKNOWN are reported and skipped. "
                         "Use this instead of --event for more than a handful.")
    ap.add_argument("--map", type=Path, default=None,
                    help="curated linkage CSV (default: the committed map)")
    ap.add_argument("--pad-years", type=int, default=1,
                    help="years of session index to build BEFORE the earliest "
                         "event (the end is capped at --as-of regardless)")
    ap.add_argument("--emit-requests", type=Path, default=None,
                    metavar="DIR",
                    help="write one pre-filled ticker,session_date,close "
                         "file per peer here, every required row present "
                         "and the close column blank")
    ap.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                    help="the last session whose close can actually be "
                         "collected; default today. Sessions after this do "
                         "not exist yet and are never requested -- an event "
                         "whose horizon runs past it is reported as truncated.")
    a = ap.parse_args(argv)

    if not a.event and not a.events_csv:
        print("No --event or --events-csv supplied. Nothing to compute.",
              file=sys.stderr)
        return 2

    as_of = date.today() if a.as_of is None else _parse_iso(a.as_of)
    if as_of is None:
        print(f"--as-of must be YYYY-MM-DD, got {a.as_of!r}", file=sys.stderr)
        return 2

    from .curated_linkage import LSE, load_curated_linkage
    from .event_panel import resolve_events

    map_path = a.map or (LSE / "HYP04_Linkage_Map_v1.0.csv")
    if not map_path.is_file():
        print(f"No curated map at {map_path}", file=sys.stderr)
        return 2
    res = load_curated_linkage(map_path)
    if not res.ok:
        print(f"{map_path.name} does not load clean: "
              f"{res.rows_rejected} of {res.rows_seen} row(s) rejected. "
              "Refusing to build a request from an invalid map.", file=sys.stderr)
        return 1

    raw: list[dict[str, Any]] = []
    for spec in a.event:
        parts = spec.split(":")
        if len(parts) != 3:
            print(f"Bad --event {spec!r}; expected ID:TICKER:YYYY-MM-DD",
                  file=sys.stderr)
            return 2
        raw.append({"event_id": parts[0], "anchor": parts[1],
                    "response_session_date": parts[2]})

    if a.events_csv:
        loaded, unresolved = _events_from_csv(a.events_csv)
        for eid, why in unresolved:
            print(f"SKIPPED {eid}: {why}", file=sys.stderr)
        if not loaded and not raw:
            print(f"No usable events in {a.events_csv}", file=sys.stderr)
            return 2
        raw.extend(loaded)

    dates = [d for d in (_parse_iso(e["response_session_date"]) for e in raw) if d]
    if len(dates) != len(raw):
        print("Every event date must be YYYY-MM-DD.", file=sys.stderr)
        return 2

    # The index ENDS at as_of. A close that has not happened cannot be
    # collected, and a request that includes one sends the operator looking
    # for prices that do not exist. Capping here rather than padding forward
    # means requirements_for reports those events as `truncated`, with the
    # reason, instead of listing future sessions as though they were data.
    try:
        sessions = _load_sessions(
            date(min(dates).year - a.pad_years, 1, 1), as_of)
    except ImportError:
        print("The authoritative XNYS calendar is unavailable "
              "(`pip install exchange_calendars`). REFUSING rather than "
              "approximating with weekdays -- an approximate calendar would "
              "put market holidays into the request.", file=sys.stderr)
        return 3
    except Exception as exc:                       # calendar bounds, etc.
        print(f"The XNYS calendar refused the requested range "
              f"({min(dates).year - a.pad_years} .. {as_of}): {exc}",
              file=sys.stderr)
        return 3

    if not sessions:
        print(f"No trading sessions between "
              f"{date(min(dates).year - a.pad_years, 1, 1)} and {as_of}.",
              file=sys.stderr)
        return 2

    panel = resolve_events(raw, sessions=sessions)
    for r in panel.rejected:
        print(f"REJECTED {r.event_id}: {r.reason} {r.detail}", file=sys.stderr)

    rep = requirements_for(panel.resolved, res.edges, sessions=sessions)
    print(format_report(rep))

    if a.emit_requests:
        try:
            written = write_request_csvs(rep, a.emit_requests)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print()
        for path, n in written:
            print(f"wrote: {path}  ({n} row(s), close column blank)")
        print(f"Fill the close column. peer_returns.load_panel rejects "
              f"gaps, duplicates and off-calendar dates rather than "
              f"repairing them, so leave a missing close EMPTY -- never 0.")

    # `requirements_for` reports a truncated window as "extend the index".
    # When the index ends at --as-of that advice is wrong: the sessions have
    # not happened. Say which boundary actually bound.
    if rep.truncated:
        print(f"\nNOTE: the session index ends at --as-of {as_of.isoformat()} "
              f"(last session {sessions[-1].isoformat()}). A pair truncated at "
              "the RIGHT edge is waiting on sessions that do not exist yet -- "
              "collect it after they trade; the index cannot be extended into "
              "the future. A pair truncated at the LEFT edge needs --pad-years "
              "raised.")
    return 0


REQUEST_CSV_SUFFIX = "_closes_REQUEST.csv"


def request_csv_header() -> list[str]:
    """The close-file schema, READ from the template rather than restated.

    peer_returns owns this schema and validates against it. Writing a second
    copy of the column names here would be one more place for them to drift --
    the failure this project has spent most of its guards on. If the template
    is missing, that is an error worth surfacing, not a default worth guessing.
    """
    from .peer_returns import TEMPLATE_HEADERS_CSV

    if not TEMPLATE_HEADERS_CSV.is_file():
        raise FileNotFoundError(
            f"the closes template {TEMPLATE_HEADERS_CSV} is missing; refusing "
            "to invent a schema for files peer_returns will have to validate")
    first = TEMPLATE_HEADERS_CSV.read_text(encoding="utf-8").splitlines()[0]
    return [c.strip() for c in first.split(",") if c.strip()]


def write_request_csvs(rep: "RequirementsReport", out_dir: Path
                       ) -> list[tuple[Path, int]]:
    """One pre-filled request file per peer: every row present, close blank.

    The operator fills a COLUMN instead of constructing rows, which removes the
    step most likely to introduce an off-calendar date, a duplicate, or a
    missing session -- all of which peer_returns rejects rather than repairs,
    and all of which are cheaper to avoid than to diagnose.

    The close column is left EMPTY, never zero. A zero return is a real
    observation (a halt, a flat close); an empty cell is the absence of one.
    """
    import csv as _csv

    header = request_csv_header()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, int]] = []

    for req in rep.requirements:
        path = out_dir / f"{req.peer}{REQUEST_CSV_SUFFIX}"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            w.writerow(header)
            for session in req.sessions:
                row = []
                for col in header:
                    if col == "ticker":
                        row.append(req.peer)
                    elif col == "session_date":
                        row.append(session.isoformat())
                    else:
                        row.append("")          # close, and anything added later
                w.writerow(row)
        written.append((path, len(req.sessions)))
    return written


def _events_from_csv(path: Path) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Read an earnings_events candidate CSV into resolved-session events.

    Returns (events, unresolved) where `unresolved` names every row that could
    NOT be turned into a request, with the reason. Nothing is dropped quietly:
    a candidate that vanishes without explanation is indistinguishable from
    one that was never in the file.

    BMO/AMC is resolved to the response session HERE, via the authoritative
    calendar, so the caller never hand-converts. An UNKNOWN release session is
    skipped rather than assumed -- guessing it would put every mis-guessed AMC
    event one session early, which is the look-ahead direction.
    """
    import csv

    from gst_market_response.exchange_calendar import (
        compute_expected_next_full_trading_session_xnys as _resolve)
    from .earnings_events import SESSION_AMC, SESSION_BMO

    events: list[dict[str, Any]] = []
    unresolved: list[tuple[str, str]] = []

    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            eid = (row.get("event_id") or "").strip()
            anchor = (row.get("anchor_ticker") or "").strip().upper()
            rel_raw = (row.get("release_date") or "").strip()
            sess = (row.get("release_session") or "").strip().upper()

            if not eid or not anchor:
                unresolved.append((eid or "<no event_id>",
                                   "missing event_id or anchor_ticker"))
                continue
            if sess not in (SESSION_BMO, SESSION_AMC):
                unresolved.append(
                    (eid, f"release_session is {sess or '<blank>'}; only "
                          f"{SESSION_BMO}/{SESSION_AMC} can be resolved to a "
                          "response session, and guessing is not an option"))
                continue
            rel = _parse_iso(rel_raw)
            if rel is None:
                unresolved.append((eid, f"release_date {rel_raw!r} is not "
                                        "YYYY-MM-DD"))
                continue

            events.append({"event_id": eid, "anchor": anchor,
                           "response_session_date": _resolve(rel, sess)
                           .isoformat()})
    return events, unresolved


def _parse_iso(value: str) -> Optional[date]:
    from datetime import datetime as _dt
    try:
        return _dt.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


if __name__ == "__main__":
    sys.exit(main())
