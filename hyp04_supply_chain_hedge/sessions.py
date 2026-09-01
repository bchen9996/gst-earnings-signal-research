#!/usr/bin/env python3
"""HYP-04's XNYS session index. WIDER than the authoritative instance, and
CHECKED against it.

=== WHY THIS EXISTS ===

`gst_market_response.exchange_calendar` builds `xcals.get_calendar("XNYS")` with
no `start`, so `exchange_calendars` applies its default window and the instance's
first session is 2006-08-31. That is a DEFAULT, not a data limitation: the
package ships XNYS sessions back to 1885.

HYP-04's anchor-event calendar reaches back to 2003-08-07, and **57 of its 342
events (17%) fall before 2006-08-31** -- NVDA 15, JBL 13, MCK 13, NKE 6, INTC 6,
CTSH 4. Resolving sessions with the default instance raises DateOutOfBounds on
every one of them.

Silently dropping them would be DATA AVAILABILITY DECIDING MEMBERSHIP, which
this project has refused twice already -- once for a filer's print format and
once for a regulator's item renumbering. It would also discard more events than
registry v1.10's Item-12 rule just recovered, which would make that decision
self-defeating.

=== WHY NOT JUST WIDEN THE AUTHORITATIVE ONE ===

Because it is HYP-01's. `gst_market_response/` is the confirmatory
infrastructure this package has never modified, and changing a shared calendar
instance's bounds to suit HYP-04 would alter another hypothesis's behaviour for
a reason that has nothing to do with it.

This is the pattern `peer_returns` and `event_panel` already set: HYP-04 INJECTS
its session index rather than importing that module, so the two stay decoupled.
`pair_eligibility` and `anchor_shock` set the same precedent for rules.

=== AND WHY IT IS CHECKED RATHER THAN TRUSTED ===

A second calendar is a second answer to a question that already has one. If it
disagreed with the authoritative instance anywhere, every downstream session
would be suspect and nothing would say so -- the divergence `event_panel`'s
docstring warns about, where an off-by-one is look-ahead that raises nothing.

So `verify_agreement()` compares the two over their entire overlap and this
module REFUSES to hand out an index that disagrees. Measured 2026-08-31 against
exchange_calendars 4.13.2: 5,030 overlapping sessions, ZERO disagreements.

The wider window is used ONLY to reach further back. Inside the overlap the two
are the same calendar, and that is asserted, not assumed.

=== NO NETWORK ===

`exchange_calendars` ships its own holiday data and resolves with sockets
blocked. Nothing here reaches an endpoint.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional, Sequence

# Far enough back to cover the anchor calendar's earliest release (2003-08-07)
# with room for the prior-session close, and for any earlier member interval a
# future re-walk might open. Not "as far as possible": a start date is a stated
# choice, and an unbounded one would make the index's size depend on the
# package's own history rather than on this hypothesis's needs.
DEFAULT_INDEX_START = "1995-01-01"

CALENDAR_NAME = "XNYS"


class SessionIndexError(ValueError):
    """Fail-closed: the wider index disagrees with the authoritative one."""


def calendar_id() -> str:
    """The exact calendar implementation this index came from."""
    from importlib.metadata import version

    return f"{CALENDAR_NAME}_exchange_calendars_v{version('exchange_calendars')}"


def _wide_calendar(start: str = DEFAULT_INDEX_START):
    import exchange_calendars as xcals

    return xcals.get_calendar(CALENDAR_NAME, start=start)


def _authoritative_calendar():
    """HYP-01's instance, imported lazily and NEVER modified.

    Lazy because this module must remain importable in suites that do not
    exercise the agreement check, and because importing `gst_market_response`
    at module scope would couple every caller to it -- the exact coupling
    `peer_returns` avoids by injecting the index.
    """
    from gst_market_response.exchange_calendar import _calendar

    return _calendar


def verify_agreement(*, start: str = DEFAULT_INDEX_START,
                     wide: Any = None, authoritative: Any = None,
                     ) -> dict[str, Any]:
    """Compare the wider index with the authoritative one over their overlap.

    Returns a report. `agrees` False means the index MUST NOT be used: the two
    calendars would give different answers to the same question and the
    downstream error -- a session off by one -- is look-ahead that raises
    nothing.
    """
    w = wide if wide is not None else _wide_calendar(start)
    a = authoritative if authoritative is not None else _authoritative_calendar()

    lo = max(w.first_session, a.first_session)
    hi = min(w.last_session, a.last_session)
    ws = {d.date() for d in w.sessions_in_range(lo, hi)}
    as_ = {d.date() for d in a.sessions_in_range(lo, hi)}
    only_wide = sorted(ws - as_)
    only_auth = sorted(as_ - ws)

    return {
        "calendar_id": calendar_id(),
        "index_start": start,
        "wide_first_session": w.first_session.date().isoformat(),
        "authoritative_first_session": a.first_session.date().isoformat(),
        "overlap_first": lo.date().isoformat(),
        "overlap_last": hi.date().isoformat(),
        "overlap_sessions": len(as_),
        "disagreements": len(only_wide) + len(only_auth),
        "only_in_wide": [d.isoformat() for d in only_wide[:20]],
        "only_in_authoritative": [d.isoformat() for d in only_auth[:20]],
        "agrees": not only_wide and not only_auth,
        "why_wider": (
            "The authoritative instance is built with no `start`, so its first "
            "session is a package default rather than a data limit. HYP-04's "
            "anchor calendar reaches earlier, and dropping those events would "
            "let data availability decide membership."),
    }


def xnys_sessions(first: date, last: date, *,
                  start: str = DEFAULT_INDEX_START,
                  verify: bool = True) -> list[date]:
    """Ordered XNYS sessions in [first, last]. REFUSES on disagreement.

    `verify=False` exists only for tests that inject their own calendars;
    production callers must leave it on. A silent second calendar is the whole
    risk this module was written to contain.
    """
    if first > last:
        raise SessionIndexError(
            f"empty range: first {first.isoformat()} is after last "
            f"{last.isoformat()}")

    if verify:
        report = verify_agreement(start=start)
        if not report["agrees"]:
            raise SessionIndexError(
                "the wider XNYS index disagrees with the authoritative "
                f"calendar on {report['disagreements']} session(s) in "
                f"{report['overlap_first']}..{report['overlap_last']}: "
                f"only_in_wide={report['only_in_wide']}, "
                f"only_in_authoritative={report['only_in_authoritative']}. "
                "Refusing to hand out an index that would give a different "
                "answer from the authoritative one.")

    cal = _wide_calendar(start)
    if first < cal.first_session.date():
        raise SessionIndexError(
            f"{first.isoformat()} is before the index start "
            f"{cal.first_session.date().isoformat()}. Widen `start` rather "
            "than clipping the range -- a clipped index looks complete.")
    if last > cal.last_session.date():
        raise SessionIndexError(
            f"{last.isoformat()} is past the index end "
            f"{cal.last_session.date().isoformat()}.")

    return [d.date() for d in cal.sessions_in_range(first, last)]


def sessions_for_release_dates(release_dates: Iterable[str], *,
                               pad_days: int = 20,
                               start: str = DEFAULT_INDEX_START,
                               ) -> tuple[list[date], dict[str, Any]]:
    """The session index a set of release dates needs, plus its provenance.

    Padded on both ends: a release on the first date still needs the session
    before it for a return, and an AMC release on the last date lands on the
    session after it.
    """
    from datetime import timedelta

    ds = sorted({d for d in (str(x).strip() for x in release_dates) if d})
    if not ds:
        raise SessionIndexError("no release dates supplied")
    try:
        lo = date.fromisoformat(ds[0]) - timedelta(days=pad_days)
        hi = date.fromisoformat(ds[-1]) + timedelta(days=pad_days)
    except ValueError as exc:
        raise SessionIndexError(f"unparseable release date: {exc}") from exc

    report = verify_agreement(start=start)
    if not report["agrees"]:
        raise SessionIndexError(
            "refusing to build an index that disagrees with the authoritative "
            f"calendar: {report['disagreements']} disagreement(s)")

    sessions = xnys_sessions(lo, hi, start=start, verify=False)
    provenance = dict(report)
    provenance.update({
        "requested_first": lo.isoformat(),
        "requested_last": hi.isoformat(),
        "sessions_returned": len(sessions),
        "earliest_release_date": ds[0],
        "latest_release_date": ds[-1],
        "pad_days": pad_days,
    })
    return sessions, provenance
