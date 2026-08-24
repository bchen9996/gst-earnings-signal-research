#!/usr/bin/env python3
"""Bridge calendar anchor events onto the session index -- HYP-04.

=== THE SEAM THIS CLOSES ===

Four modules are meant to compose, and until now nothing joined two of their
vocabularies:

    linkage_resolution  reasons in CALENDAR DATES  (`event_date`)
    pair_eligibility    reasons in CALENDAR DATES  (P3: as_of < event date)
    peer_returns        reasons in SESSION INDICES (`anchor_day`)
    target              reasons in SESSION INDICES (`anchor_day`)

Both halves are right. P3 has to compare an edge's disclosure date to an event
date, which is calendar arithmetic. `target` has to slice a returns array,
which is positional. Real data arrives as dates. Something has to convert, and
nothing did.

=== WHY THIS IS THE DANGEROUS SEAM ===

An off-by-one here is look-ahead bias, silently.

`target.raw_log_ratio_target` takes the reference window as the sessions ending
AT `anchor_day` and the post-event window as `[anchor_day+1, ...]`. So
`anchor_day` must be the index of the session the market response is measured
FROM. Choose the session one too late and the reference window swallows the
event's own move; one too early and the post window starts before the news.

Neither error raises. Both produce a finite number.

=== IT DOES NOT DECIDE WHICH SESSION AN EARNINGS RELEASE AFFECTS ===

That decision -- BMO before the open lands on the same session, everything else
on the next one -- belongs to
`gst_market_response.exchange_calendar.compute_expected_next_full_trading_session_xnys`,
which is bound to the authoritative XNYS calendar.

This module DELEGATES it by requiring the caller to pass a session date that
has already been resolved, the same way `pair_eligibility` delegates P1 to
`completeness.is_eligible_for_hypothesis` rather than reimplementing it.

It cannot import that function directly: `exchange_calendar` imports
`exchange_calendars`, which `requirements-hyp04.txt` deliberately does not
install, so importing it would break HYP-04's CI job. The session index is
injected for the same reason `peer_returns` injects it.

**A caller that passes a raw earnings date instead of a resolved response
session will silently be one session early for every AMC release.** That is
why the field is named `response_session_date` and not `event_date`, and why
`assert_sessions_resolved()` exists.

=== FAIL CLOSED: A DATE OFF THE INDEX IS REJECTED, NEVER SNAPPED ===

If a response session date is not IN the session index, this rejects the event.
It does not snap to the nearest session. Snapping would move an event to a day
the market did something else, and the resulting number would look ordinary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Optional, Sequence

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# THE canonical name for an event's position in the session index.
#
# It was briefly two names: `day` (fixtures and target) and `anchor_day`
# (peer_returns), emitted as aliases of one value. They were unified onto
# `anchor_day` on 2026-08-23. `day` does not say WHICH day, and target.py was
# already WRITING its output column as "anchor_day" while READING ev["day"],
# so the canonical name was settled everywhere except the input key.
KEY_ANCHOR_DAY = "anchor_day"


class EventPanelError(ValueError):
    """Programming errors only. Bad event data is REPORTED, not raised."""


@dataclass(frozen=True)
class RejectedEvent:
    event_id: str
    anchor: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class ResolvedEvent:
    """One anchor event pinned to a session index position."""

    event_id: str
    anchor: str
    response_session_date: date
    day_index: int
    peers: tuple[str, ...] = ()

    def as_analysis_event(self) -> dict[str, Any]:
        """The dict shape the existing consumers accept.

        `anchor_day` is the position in the session index (KEY_ANCHOR_DAY).
        `event_date` is the ISO RESPONSE-session date, so `pair_eligibility`'s
        P3 compares against the session the response is measured from -- not
        against a raw earnings date that may fall on a non-session.
        """
        iso = self.response_session_date.isoformat()
        return {
            "event_id": self.event_id,
            "anchor": self.anchor,
            "event_date": iso,
            "response_session_date": iso,
            KEY_ANCHOR_DAY: self.day_index,
            "peers": list(self.peers),
        }


@dataclass(frozen=True)
class EventPanel:
    resolved: tuple[ResolvedEvent, ...] = ()
    rejected: tuple[RejectedEvent, ...] = ()
    sessions_in_index: int = 0

    @property
    def n_resolved(self) -> int:
        return len(self.resolved)

    def analysis_events(self) -> list[dict[str, Any]]:
        return [e.as_analysis_event() for e in self.resolved]

    def rejection_reasons(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rejected:
            out[r.reason] = out.get(r.reason, 0) + 1
        return out


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value or "")
    if not DATE_RE.match(s):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_sessions(sessions: Sequence[date]) -> tuple[date, ...]:
    """Strictly increasing, no duplicates. Raises -- a bad index is a caller bug."""
    out = tuple(sessions)
    for a, b in zip(out, out[1:]):
        if b <= a:
            raise EventPanelError(
                f"session index must be strictly increasing; {a} then {b}")
    return out


def resolve_events(
    events: Iterable[dict[str, Any]],
    *,
    sessions: Sequence[date],
    date_field: str = "response_session_date",
) -> EventPanel:
    """Pin each anchor event to its session-index position.

    Each event needs `event_id`, `anchor`, and a date under `date_field` that
    has ALREADY been resolved to the session the market response is measured
    from. `peers` is optional and carried through untouched.

    Every failure is a rejection with a reason, never an exception and never a
    silent drop: an event that vanishes without explanation is indistinguishable
    from one that was never supplied.
    """
    idx = normalize_sessions(sessions)
    pos = {d: i for i, d in enumerate(idx)}

    resolved: list[ResolvedEvent] = []
    rejected: list[RejectedEvent] = []
    seen: set[str] = set()

    for ev in events:
        eid = str(ev.get("event_id", "")).strip()
        anchor = str(ev.get("anchor", "")).strip().upper()

        if not eid:
            rejected.append(RejectedEvent("", anchor, "missing_event_id"))
            continue
        if eid in seen:
            rejected.append(RejectedEvent(eid, anchor, "duplicate_event_id"))
            continue
        seen.add(eid)
        if not anchor:
            rejected.append(RejectedEvent(eid, anchor, "missing_anchor"))
            continue

        raw = ev.get(date_field)
        if raw is None:
            rejected.append(RejectedEvent(
                eid, anchor, "missing_response_session_date",
                f"expected field {date_field!r}"))
            continue
        d = _parse_date(raw)
        if d is None:
            rejected.append(RejectedEvent(
                eid, anchor, "malformed_date", f"{raw!r} is not YYYY-MM-DD"))
            continue

        i = pos.get(d)
        if i is None:
            # NOT snapped. See the module docstring.
            rejected.append(RejectedEvent(
                eid, anchor, "date_not_in_session_index",
                f"{d.isoformat()} is not a session in the supplied index "
                f"({idx[0].isoformat()}..{idx[-1].isoformat()})"))
            continue

        peers = tuple(str(p).strip().upper()
                      for p in (ev.get("peers") or ()) if str(p).strip())
        resolved.append(ResolvedEvent(
            event_id=eid, anchor=anchor, response_session_date=d,
            day_index=i, peers=peers))

    return EventPanel(resolved=tuple(resolved), rejected=tuple(rejected),
                      sessions_in_index=len(idx))


def assert_sessions_resolved(
    events: Iterable[dict[str, Any]],
    *,
    sessions: Sequence[date],
    date_field: str = "response_session_date",
) -> list[str]:
    """Warn where a caller looks to have passed RAW earnings dates.

    Cannot prove it -- a BMO release genuinely lands on its own earnings date,
    so a correct panel and an unresolved one overlap. What it CAN do is report
    how many supplied dates are not sessions at all, which is the signature of
    raw dates: weekends and holidays survive in an unresolved set and cannot
    survive in a resolved one.

    Returns a list of human-readable warnings; empty means nothing suspicious.
    """
    idx = set(normalize_sessions(sessions))
    total = off = 0
    for ev in events:
        d = _parse_date(ev.get(date_field))
        if d is None:
            continue
        total += 1
        if d not in idx:
            off += 1

    warnings: list[str] = []
    if total and off:
        warnings.append(
            f"{off} of {total} supplied {date_field} value(s) are not sessions "
            "in the index. A RESOLVED response session is always a session, so "
            "this usually means raw earnings dates were passed. Resolve them "
            "with gst_market_response.exchange_calendar."
            "compute_expected_next_full_trading_session_xnys(earnings_date, "
            "release_market_session) first -- every AMC release is otherwise "
            "one session early."
        )
    return warnings
