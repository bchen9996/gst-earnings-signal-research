#!/usr/bin/env python3
"""Was the registrant that bears this ticker TODAY the company named THEN?

`peer_ceiling` resolves a counterparty name to a ticker by exact match against
SEC's company list, and marks every such row `requires_lineage_review`. That
flag is honest but inert: it says a question exists and leaves it entirely to
the curator. This module answers the mechanical part of it from SEC's own
record, so the curator starts from evidence rather than from a name.

=== THE QUESTION, AND WHY IT IS NOT PEDANTRY ===

The ticker map describes companies as they are TODAY. A counterparty name comes
from a filing made years or decades ago. Matching them answers "does a company
with this name exist now?", never "is it the same company that was named then?"

This project has already refused that inference twice on the merits. **Caremark
RX** was rejected for MCK and **OfficeMax** for PKG, both because a merger is
not a rename: the pre-merger counterparty is a different company, so an edge
cannot inherit its history and the as_of date does not move back.

And the error is not hypothetical here. Exact matching resolved ADBE's 2006
disclosure of "Ingram Micro" onto INGM -- `Ingram Micro Holding Corp`, CIK
1897762, the 2024 re-IPO vehicle -- because the normaliser stripped "Holding".
The token was removed from `NAME_SUFFIXES` for that reason. This module exists
to catch the same class of error when the NAME gives nothing away.

=== THE TEST, FROM ONE REQUEST PER REGISTRANT ===

SEC's submissions JSON carries everything needed:

  * `formerNames`, each with a `from`/`to` window, so the name IN FORCE at any
    date is a lookup rather than a guess. (Measured: MCK carries
    "MCKESSON HBOC INC", 1999-09-10 to 2001-08-13.)
  * `filings.files[]`, whose `filingFrom`/`filingTo` bound the older shards, so
    the registrant's FULL filing history is derivable WITHOUT fetching them.
    One request per registrant, not one per decade.

From those:

  A registrant whose first filing POSTDATES the disclosure cannot be the
  company that disclosure named. That is a lineage break, and it is decidable.
  It is exactly the Ingram Micro case.

  A registrant that stopped filing BEFORE the disclosure likewise cannot be it.

  A registrant that was filing, but under a name that does not match the
  disclosed one at that date, is NOT resolved here. It may be a subsidiary, a
  brand, or a genuine mismatch, and telling those apart is judgement.

=== WHAT IT REFUSES TO DO ===

It never promotes a row, never writes a curated edge, and never clears a
candidate for use. Its best verdict is CONTINUOUS -- "the registrant existed
under this name when the filing named it" -- which removes one specific way of
being wrong and establishes nothing else. A merger that preserved both the name
and the registrant would pass this test and still be the wrong peer.

Every unknown fails closed to UNKNOWN rather than to a pass, for the reason
`pair_eligibility` gives: an unchecked thing is not a checked thing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from .peer_ceiling import normalize_company_name

PEER_LINEAGE_RULE_ID = "HYP04-PEER-LINEAGE-RULE-v1"

#: The registrant was filing at the disclosure date, under the disclosed name.
#: The WEAKEST useful verdict: it removes one way of being wrong, no more.
VERDICT_CONTINUOUS = "continuous_under_this_name"

#: Decidable lineage breaks. The registrant cannot be the company named.
VERDICT_NOT_YET_FILING = "LINEAGE_BREAK_first_filing_postdates_disclosure"
VERDICT_STOPPED_FILING = "LINEAGE_BREAK_last_filing_predates_disclosure"

#: Filing at the time, under a different name. Judgement, not arithmetic.
VERDICT_NAME_NOT_IN_FORCE = "REVIEW_name_not_in_force_at_disclosure"

#: Fails closed. Never a pass.
VERDICT_UNKNOWN = "UNKNOWN_insufficient_record"

BREAK_VERDICTS = (VERDICT_NOT_YET_FILING, VERDICT_STOPPED_FILING)


def _iso_day(v: Any) -> str:
    """'2001-08-13T00:00:00.000Z' or '2001-08-13' -> '2001-08-13'. Else ''."""
    s = str(v or "")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return ""


@dataclass(frozen=True)
class FormerName:
    name: str
    start: str = ""
    end: str = ""

    def covers(self, day: str) -> bool:
        """Whether this name was in force on `day`. Unknown bounds do NOT cover.

        An open-ended window would quietly cover every date, including ones the
        registrant did not use the name at all.
        """
        if not (self.start and self.end and day):
            return False
        return self.start <= day <= self.end


@dataclass(frozen=True)
class FilerHistory:
    """One registrant's identity over time, derived from SEC's submissions."""

    cik: str = ""
    current_name: str = ""
    former_names: tuple[FormerName, ...] = ()
    first_filing: str = ""
    last_filing: str = ""
    filings_counted: int = 0

    @property
    def known(self) -> bool:
        return bool(self.first_filing and self.last_filing)

    def was_filing_on(self, day: str) -> Optional[bool]:
        """True/False, or None when the record cannot say."""
        if not (self.known and day):
            return None
        return self.first_filing <= day <= self.last_filing

    def name_in_force(self, day: str) -> Optional[str]:
        """The registrant's name on `day`, or None if the record cannot say.

        A former name whose window covers the day wins. Otherwise the current
        name applies only AFTER every former-name window has closed -- before
        the first known window, the record does not say what the name was, and
        this returns None rather than assuming today's.
        """
        if not day:
            return None
        for fn in self.former_names:
            if fn.covers(day):
                return fn.name
        ends = [fn.end for fn in self.former_names if fn.end]
        if ends and day < max(ends):
            return None
        return self.current_name or None


def filer_history(submissions: Mapping[str, Any]) -> FilerHistory:
    """Derive a FilerHistory from one SEC submissions document. PURE.

    The full filing range comes from `filings.files[]`'s `filingFrom`/
    `filingTo` bounds UNIONED with the dates in `filings.recent`. Using only
    `recent` would put the first filing decades late for any long-lived filer
    -- MCK's `recent` starts 2016-05-04 while its record starts 1995-02-08 --
    and a first-filing date that is too late manufactures lineage breaks.
    """
    filings = submissions.get("filings") or {}
    recent = filings.get("recent") or {}
    dates = [d for d in (recent.get("filingDate") or []) if _iso_day(d)]

    firsts = [_iso_day(d) for d in dates]
    lasts = list(firsts)
    for shard in filings.get("files") or []:
        a, b = _iso_day(shard.get("filingFrom")), _iso_day(shard.get("filingTo"))
        if a:
            firsts.append(a)
        if b:
            lasts.append(b)

    former = tuple(
        FormerName(name=str(f.get("name", "")),
                   start=_iso_day(f.get("from")), end=_iso_day(f.get("to")))
        for f in (submissions.get("formerNames") or [])
        if f.get("name"))

    counted = len(dates) + sum(int(s.get("filingCount") or 0)
                               for s in (filings.get("files") or []))

    return FilerHistory(
        cik=str(submissions.get("cik", "")),
        current_name=str(submissions.get("name", "")),
        former_names=former,
        first_filing=min(firsts) if firsts else "",
        last_filing=max(lasts) if lasts else "",
        filings_counted=counted,
    )


@dataclass(frozen=True)
class LineageAssessment:
    """One candidate held against the registrant's own filing record."""

    anchor_ticker: str = ""
    peer_ticker: str = ""
    disclosed_name: str = ""
    as_of_date: str = ""
    verdict: str = VERDICT_UNKNOWN
    detail: str = ""
    history: Optional[FilerHistory] = None

    @property
    def is_break(self) -> bool:
        return self.verdict in BREAK_VERDICTS

    @property
    def clears_this_check(self) -> bool:
        """CONTINUOUS only. Deliberately not called `eligible` or `valid`."""
        return self.verdict == VERDICT_CONTINUOUS

    def as_dict(self) -> dict[str, Any]:
        h = self.history
        return {
            "anchor_ticker": self.anchor_ticker,
            "peer_ticker": self.peer_ticker,
            "disclosed_name": self.disclosed_name,
            "as_of_date": self.as_of_date,
            "verdict": self.verdict,
            "detail": self.detail,
            "is_lineage_break": self.is_break,
            "registrant_cik": h.cik if h else "",
            "registrant_name_now": h.current_name if h else "",
            "registrant_name_at_as_of": (h.name_in_force(self.as_of_date)
                                         if h else None),
            "registrant_first_filing": h.first_filing if h else "",
            "registrant_last_filing": h.last_filing if h else "",
            "registrant_former_names": [
                {"name": f.name, "from": f.start, "to": f.end}
                for f in (h.former_names if h else ())],
        }


def assess(
    history: Optional[FilerHistory],
    *,
    disclosed_name: str,
    as_of_date: str,
    anchor_ticker: str = "",
    peer_ticker: str = "",
) -> LineageAssessment:
    """Hold one candidate against the registrant's record. FAILS CLOSED."""
    kw = {"anchor_ticker": anchor_ticker, "peer_ticker": peer_ticker,
          "disclosed_name": disclosed_name, "as_of_date": as_of_date,
          "history": history}

    if history is None or not history.known or not as_of_date:
        return LineageAssessment(
            verdict=VERDICT_UNKNOWN,
            detail="the submissions record does not bound this registrant's "
                   "filing history, or no disclosure date was supplied",
            **kw)

    if as_of_date < history.first_filing:
        return LineageAssessment(
            verdict=VERDICT_NOT_YET_FILING,
            detail=(f"the registrant's first filing is "
                    f"{history.first_filing}, AFTER the {as_of_date} filing "
                    f"that named {disclosed_name!r}. It cannot be the company "
                    "that disclosure named."),
            **kw)

    if as_of_date > history.last_filing:
        return LineageAssessment(
            verdict=VERDICT_STOPPED_FILING,
            detail=(f"the registrant's last filing is {history.last_filing}, "
                    f"BEFORE the {as_of_date} disclosure."),
            **kw)

    at = history.name_in_force(as_of_date)
    if at is None:
        return LineageAssessment(
            verdict=VERDICT_UNKNOWN,
            detail=(f"the registrant was filing on {as_of_date}, but its "
                    "former-name windows do not say which name was in force "
                    "then. Today's name is not assumed."),
            **kw)

    if normalize_company_name(at) == normalize_company_name(disclosed_name):
        return LineageAssessment(
            verdict=VERDICT_CONTINUOUS,
            detail=(f"the registrant was filing on {as_of_date} as {at!r}, "
                    "matching the disclosed name. This removes ONE way of "
                    "being wrong; it does not establish the relationship."),
            **kw)

    return LineageAssessment(
        verdict=VERDICT_NAME_NOT_IN_FORCE,
        detail=(f"the registrant was filing on {as_of_date} as {at!r}, not "
                f"{disclosed_name!r}. It may be a subsidiary, a brand, or the "
                "wrong company; that is judgement, not arithmetic."),
        **kw)


def summarise(rows: Iterable[LineageAssessment]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.verdict] = out.get(r.verdict, 0) + 1
    return out


def rule_description() -> dict[str, Any]:
    return {
        "rule_id": PEER_LINEAGE_RULE_ID,
        "question": (
            "Was the registrant bearing this ticker today the company the "
            "filing named then?"),
        "derived_from": (
            "SEC submissions JSON: formerNames with from/to windows, and "
            "filings.files[] filingFrom/filingTo bounds, which give the full "
            "filing history in ONE request per registrant."),
        "decidable_part": (
            "A registrant whose first filing postdates the disclosure, or "
            "whose last filing predates it, cannot be the company named. "
            "Both are lineage breaks."),
        "judgement_part": (
            "A registrant filing at the time under a different name may be a "
            "subsidiary, a brand, or the wrong company. Reported for review, "
            "never decided here."),
        "what_continuous_does_not_mean": (
            "It removes one way of being wrong. A merger that preserved both "
            "the name and the registrant would pass and still be the wrong "
            "peer -- which is how Caremark RX and OfficeMax were caught, on "
            "the merits rather than by this test."),
        "fails_closed": (
            "Every gap in the record yields UNKNOWN, never a pass. Today's "
            "name is never assumed to have been in force before the "
            "former-name windows close."),
        "promotes_nothing": (
            "No row is curated, no edge is written, and no candidate is "
            "cleared for use. The display gate is untouched."),
    }
