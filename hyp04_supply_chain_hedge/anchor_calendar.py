#!/usr/bin/env python3
"""HYP-04 anchor-event CALENDAR: candidate events inside membership spans.

=== WHAT THIS ANSWERS ===

Registry v1.9 leaves one question open by name: "Whether enough eligible anchor
events CAN exist is a separate question this version does not touch and does not
answer." Until now the only figures for it were ESTIMATES -- member-years times
an assumed 4.25 releases a year. This module derives the number instead.

It intersects two things the repo already had and had never crossed:

  * the point-in-time anchor universe (`anchor_universe`), 11 membership
    intervals over 8 tickers, derived from the pinned linkage history
  * candidate anchor events (`earnings_events`), derived from 8-K item tagging

An event counts only if it falls inside a span during which its filer was a
registered anchor, which is `qualifies_at` -- inclusive of the filing date,
because the disclosure was public that day.

=== CANDIDATE, NOT ELIGIBLE. THIS MOVES NO GATE ===

Every number here is a CANDIDATE count. An eligible anchor event additionally
needs a well-measured shock (`anchor_shock`, AS-1..AS-6), which needs the
anchor's and the benchmark's closes for the attributed session. No price source
has been decided for HYP-04, so no shock has been computed from production data
and the eligible count is still zero. C2 counts eligible events, not these.

A calendar that CAN be filled is not a filled calendar.

=== THE ITEM CODE IS AN ARTEFACT OF ITS ERA, NOT A FACT ABOUT THE FILER ===

`earnings_events` selects on Item 2.02, "Results of Operations and Financial
Condition". Measured across all eight members: the earliest Item 2.02 in the
data is 2004-09-20 (ADBE), and seven of the eight fall in September-October
2004. That is not a change in corporate behaviour. The SEC's additional Form
8-K disclosure requirements took effect 2004-08-23 and RENUMBERED Item 12 to
Item 2.02; Item 12 itself only came into being 2003-03-28. Before that an
earnings release was furnished under Item 5 or Item 7 -- the same codes every
unrelated 8-K carried, so the index cannot distinguish it at all.

So the item code partitions the corpus into three eras:

  before 2003-03-28   no earnings-specific code exists.  INVISIBLE to any
                      index-level rule. Recoverable only by reading text.
  2003-03-28..08-22   the release is Item 12.
  from 2004-08-23     the release is Item 2.02.

This is the same principle already settled twice in this project: DATA
AVAILABILITY MUST NOT DECIDE MEMBERSHIP, and a filer changing PRINT FORMAT is
not a changed relationship. A regulator renumbering a form item is not a filer
that stopped reporting earnings. NKE is the clean case -- ZERO Item 2.02 events
inside its 2002-08-14..2004-07-30 span and EIGHT Item 12 events, so its zero is
an artefact of the renumbering and nothing else.

BUT ACCEPTING ITEM 12 IS A SPECIFICATION CHANGE, so it is NOT the default here.
`accept_legacy_item_12` defaults to False, which reproduces the existing rule
exactly; both totals are derived and reported side by side, and the owner
decides which one the registry adopts. Measuring a change is not making it.

A modern code before the renumbering date is a data anomaly, not a licence: it
is counted under the strict rule (the index is what it is) and FLAGGED, so it
cannot pass unnoticed. Exactly one exists -- NKE 2001-12-16.

=== OFFLINE ===

Derivation reads submissions blocks through `_get_json`, which sits above the
on-disk cache and above the `offline=True` guard. `earnings_events` reached for
the raw `_get` until 2026-08-29 and so bypassed both; see that module's note.
The delta in `requests_made` across a derivation is recorded in the result, so
"no endpoint was reached" is a measured field rather than a claim in a commit
message.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from .earnings_events import (
    SUBMISSIONS_EXTRA_URL,
    SUBMISSIONS_URL,
    CandidateEvent,
    candidate_from_record,
)

ANCHOR_CALENDAR_RULE_ID = "HYP04-ANCHOR-CALENDAR-RULE-v1"

ITEM_RESULTS_MODERN = "2.02"
ITEM_RESULTS_LEGACY = "12"

# SEC Release 33-8400, "Additional Form 8-K Disclosure Requirements and
# Acceleration of Filing Date", effective 2004-08-23: Item 12 became Item 2.02.
ITEM_RENUMBERED_TO_2_02 = "2004-08-23"
# Item 12 was itself created by the Regulation G release, effective 2003-03-28.
ITEM_12_INTRODUCED = "2003-03-28"

FLAG_LEGACY_ITEM_12 = "legacy_item_12"
FLAG_MODERN_CODE_BEFORE_RENUMBERING = "modern_code_before_renumbering"

# ONE ANCHOR EVENT PER (ticker, release_date). EARLIEST ACCEPTANCE WINS.
#
# MEASURED, and it is not a rare edge. Of 339 results filings inside membership
# spans, 18 release dates carry TWO 8-Ks. The shape is identical every time:
# one accepted on the release day just after the 16:00 close, through a filing
# agent, and a second carrying the SAME reportDate accepted days later at an
# intraday hour. INTC does this every quarter from 2009-10 to 2013-10 -- the
# same-day filing comes through agent CIK 0001157523 and the re-filing through
# Intel's own CIK 0000050863.
#
# Counting both would be wrong twice over. It double-counts one release, and
# because the re-filing lands intraday it resolves to UNKNOWN, so the duplicate
# also drags a spurious unusable session into the set: 17 of the 32 UNKNOWN
# sessions in the raw calendar are re-filings of a release whose same-day
# filing is cleanly AMC.
#
# Earliest acceptance wins because that is when the news reached the market,
# which is the quantity BOTH the session attribution and the shock depend on. A
# later re-filing of the same results cannot make the release later. Ties break
# on accession so the choice is deterministic. Records with no acceptance
# timestamp sort LAST: a filing that cannot be timed cannot be shown to be the
# earliest.
#
# Nothing is discarded silently -- every dropped filing is returned in
# `superseded`, with the accession that displaced it.
DEDUP_RULE = ("one anchor event per (anchor_ticker, release_date); the "
              "earliest ACCEPTANCE wins, ties broken on accession")


def item_codes(items: Optional[str]) -> set[str]:
    """The comma-separated item codes, as EXACT tokens.

    A substring test would be wrong in both directions here: the legacy code is
    "12", which occurs inside no other real code today but is one edit away
    from doing so, and the whole point of this module is that codes mean
    different things in different eras.
    """
    return {c.strip() for c in (items or "").split(",") if c.strip()}


def results_item_verdict(items: Optional[str],
                         report_date: str) -> tuple[bool, bool, str]:
    """(is_modern, is_legacy, note) for one 8-K's item string.

    Neither flag is set for an 8-K reporting something other than results.
    """
    codes = item_codes(items)
    modern = ITEM_RESULTS_MODERN in codes
    legacy = ITEM_RESULTS_LEGACY in codes
    note = ""
    if modern and report_date and report_date < ITEM_RENUMBERED_TO_2_02:
        note = FLAG_MODERN_CODE_BEFORE_RENUMBERING
    elif legacy and not modern:
        note = FLAG_LEGACY_ITEM_12
    return modern, legacy, note


@dataclass(frozen=True)
class CalendarEntry:
    """One candidate anchor event, placed in the interval that contains it."""

    event: CandidateEvent
    ticker: str
    interval_start: str
    interval_end: Optional[str]
    item_era: str            # "modern" | "legacy"
    notes: tuple[str, ...] = ()

    def as_row(self) -> dict[str, Any]:
        row = self.event.as_row()
        row["interval_start"] = self.interval_start
        row["interval_end"] = self.interval_end or ""
        row["item_era"] = self.item_era
        row["calendar_notes"] = ";".join(self.notes)
        return row


@dataclass
class AnchorCalendar:
    """The derived calendar. Every count is CANDIDATE, never eligible."""

    rule_id: str = ANCHOR_CALENDAR_RULE_ID
    derived: bool = False
    accept_legacy_item_12: bool = False
    entries: list[CalendarEntry] = field(default_factory=list)
    per_interval: list[dict[str, Any]] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    superseded: list[dict[str, Any]] = field(default_factory=list)
    live_requests_made: int = 0
    unlabelled_member_years: float = 0.0

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def strict_total(self) -> int:
        return sum(1 for e in self.entries if e.item_era == "modern")

    @property
    def legacy_total(self) -> int:
        return sum(1 for e in self.entries if e.item_era == "legacy")

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "derived": self.derived,
            "accept_legacy_item_12": self.accept_legacy_item_12,
            "dedup_rule": DEDUP_RULE,
            "candidate_events_total": self.total,
            "candidate_events_item_2_02": self.strict_total,
            "candidate_events_item_12": self.legacy_total,
            "duplicate_filings_superseded": len(self.superseded),
            "superseded": list(self.superseded),
            "per_interval": list(self.per_interval),
            "refusals": list(self.refusals),
            "live_requests_made": self.live_requests_made,
            "member_years_with_no_results_item_code":
                round(self.unlabelled_member_years, 2),
            "item_code_eras": {
                "no_results_item_exists_before": ITEM_12_INTRODUCED,
                "item_12_window":
                    ITEM_12_INTRODUCED + ".." + ITEM_RENUMBERED_TO_2_02,
                "item_2_02_from": ITEM_RENUMBERED_TO_2_02,
            },
            "eligible_event_count": None,
            "measurement_status": (
                "CANDIDATE counts only. An eligible anchor event additionally "
                "requires a well-measured shock (HYP04-ANCHOR-SHOCK-RULE-v1), "
                "which requires anchor and benchmark closes for the attributed "
                "session. No price source is decided, no shock has been "
                "computed from production data, and the eligible count is "
                "zero. C2 counts eligible events, not these."),
        }


def _blocks(client, cik: str) -> list[dict]:
    data = client._get_json(SUBMISSIONS_URL.format(cik=cik))
    filings = data.get("filings", {}) or {}
    out = [filings.get("recent", {}) or {}]
    for extra in filings.get("files", []) or []:
        name = extra.get("name")
        if name:
            out.append(client._get_json(SUBMISSIONS_EXTRA_URL.format(name=name)))
    return out


def _iso(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def _acceptance_key(entry: CalendarEntry) -> tuple[str, str]:
    """Sort key implementing DEDUP_RULE. Missing acceptance sorts LAST."""
    acc = (entry.event.acceptance_utc or "").strip()
    return (acc or "9999", entry.event.accession or "")


def dedup_one_event_per_release(
    entries: list[CalendarEntry],
) -> tuple[list[CalendarEntry], list[dict[str, Any]]]:
    """Collapse same-release re-filings. Returns (kept, superseded)."""
    by_key: dict[tuple[str, str], list[CalendarEntry]] = {}
    for e in entries:
        by_key.setdefault((e.ticker, e.event.release_date), []).append(e)

    kept: list[CalendarEntry] = []
    dropped: list[dict[str, Any]] = []
    for key in sorted(by_key):
        group = sorted(by_key[key], key=_acceptance_key)
        kept.append(group[0])
        for loser in group[1:]:
            dropped.append({
                "event_id": loser.event.event_id,
                "anchor_ticker": loser.ticker,
                "release_date": loser.event.release_date,
                "superseded_accession": loser.event.accession,
                "superseded_acceptance_et": loser.event.acceptance_et,
                "superseded_release_session": loser.event.release_session,
                "kept_accession": group[0].event.accession,
                "kept_acceptance_et": group[0].event.acceptance_et,
                "kept_release_session": group[0].event.release_session,
                "reason": DEDUP_RULE,
            })
    return kept, dropped


def derive_anchor_calendar(
    universe,
    client,
    *,
    accept_legacy_item_12: bool = False,
    today: Optional[str] = None,
) -> AnchorCalendar:
    """Cross the point-in-time universe with 8-K results filings.

    Refuses outright on a universe that is not registry grade: a calendar built
    over membership that is itself not declarable would carry the weaker claim
    silently inside a stronger-looking number.
    """
    cal = AnchorCalendar(accept_legacy_item_12=accept_legacy_item_12)
    before = getattr(client, "requests_made", 0)

    if not getattr(universe, "registry_grade", False):
        cal.refusals.append(
            "the anchor universe is not registry grade, so no calendar is "
            "derivable from it: " + "; ".join(
                list(getattr(universe, "refusals", []))
                + list(getattr(universe, "incomplete", []))))
        return cal

    horizon = _iso(today) or date.today()
    intro = _iso(ITEM_12_INTRODUCED)

    for iv in universe.intervals:
        cik = client.cik_for(iv.ticker)
        if cik is None:
            cal.refusals.append("no CIK on record for " + repr(iv.ticker))
            continue

        start, end = _iso(iv.start_date), _iso(iv.end_date)
        if start is None:
            cal.refusals.append(
                iv.ticker + " interval has an unparseable start "
                + repr(iv.start_date))
            continue

        found: list[CalendarEntry] = []
        for blk in _blocks(client, cik):
            forms = blk.get("form") or []
            n = len(forms)
            for k, form in enumerate(forms):
                if form != "8-K":
                    continue
                items = (blk.get("items") or [""] * n)[k]
                rd = (blk.get("reportDate") or [""] * n)[k] \
                    or (blk.get("filingDate") or [""] * n)[k]
                d = _iso(rd)
                if d is None or d < start:
                    continue
                if end is not None and d >= end:
                    continue
                # Belt and braces: the interval arithmetic above and the
                # universe's own predicate must agree. They are the same rule
                # expressed twice, and a disagreement would mean one of them
                # has drifted.
                if not universe.qualifies_at(iv.ticker, rd):
                    continue

                modern, legacy, note = results_item_verdict(items, rd)
                if modern:
                    era = "modern"
                elif legacy and accept_legacy_item_12:
                    era = "legacy"
                else:
                    continue

                ev = candidate_from_record(iv.ticker, {
                    "accessionNumber": blk["accessionNumber"][k],
                    "filingDate": (blk.get("filingDate") or [""] * n)[k],
                    "reportDate": rd,
                    "acceptanceDateTime":
                        (blk.get("acceptanceDateTime") or [""] * n)[k],
                    "items": items,
                })
                found.append(CalendarEntry(
                    event=ev, ticker=iv.ticker, interval_start=iv.start_date,
                    interval_end=iv.end_date, item_era=era,
                    notes=(note,) if note else ()))

        found, dropped = dedup_one_event_per_release(found)
        found.sort(key=lambda e: e.event.release_date)
        cal.entries.extend(found)
        cal.superseded.extend(dropped)

        stop = end or horizon
        blind_days = max(0, ((intro if intro < stop else stop) - start).days)
        blind_years = blind_days / 365.25
        cal.unlabelled_member_years += blind_years

        cal.per_interval.append({
            "ticker": iv.ticker,
            "start_date": iv.start_date,
            "end_date": iv.end_date,
            "candidate_events": len(found),
            "item_2_02": sum(1 for e in found if e.item_era == "modern"),
            "item_12": sum(1 for e in found if e.item_era == "legacy"),
            "member_years_with_no_results_item_code": round(blind_years, 2),
        })

    cal.entries.sort(key=lambda e: (e.event.release_date, e.ticker))

    # Deduplication ran per interval, which is sound only because a ticker's
    # intervals are disjoint. Check the conclusion rather than trust the
    # premise: if two intervals ever overlapped, this is where it would show.
    seen: set[tuple[str, str]] = set()
    for e in cal.entries:
        k = (e.ticker, e.event.release_date)
        if k in seen:
            cal.refusals.append(
                "duplicate release survived deduplication: "
                + e.ticker + " " + e.event.release_date
                + " -- a ticker's membership intervals are supposed to be "
                  "disjoint, so this means they are not.")
        seen.add(k)

    cal.derived = not cal.refusals
    cal.live_requests_made = getattr(client, "requests_made", 0) - before
    return cal


CALENDAR_CSV_FIELDS = (
    "event_id", "anchor_ticker", "release_date", "release_session",
    "session_basis", "filing_date", "acceptance_utc", "acceptance_et",
    "items", "accession", "flags", "provenance",
    "interval_start", "interval_end", "item_era", "calendar_notes",
)
