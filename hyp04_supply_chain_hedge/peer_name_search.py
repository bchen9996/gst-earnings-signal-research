#!/usr/bin/env python3
"""Find the REGISTRANT behind a counterparty name SEC's current list cannot see.

`peer_ceiling.resolve_counterparty` matches against `company_tickers.json`, a
list of companies that file and trade TODAY. 27 of 35 candidate counterparties
do not appear there, carrying 109 incremental anchor events, and the reason is
structural: a company that was delisted, merged away, taken private or never a
US filer is simply absent from that file.

EDGAR's company search sees more. Measured 2026-09-01: searching "Dell
Computer" returns CIK 0000826083 with `formerly-names` carrying
`DELL COMPUTER CORP` until 2003-07-22, and "Marconi" returns the registrant now
named `telent plc`. Those are FORMER-NAME matches -- the historical record the
ticker file drops.

=== WHAT THIS DOES AND DOES NOT DECIDE ===

The search is a CANDIDATE GENERATOR, nothing more. Its matching is a prefix
rule nobody at SEC documents as an API, it returned different results for
"Marconi" and "Marconi Communications", and in multi-hit mode its own XML
carries `ARRAY(0x...)` where the company name should be -- an SEC-side bug, so
names cannot be read from a list response at all.

So acceptance is never the search's call. A candidate CIK is accepted only if
`peer_lineage.assess` returns CONTINUOUS against that registrant's own
submissions record: the registrant must have been filing on the disclosure
date, under a name that matches the disclosed one. The same test that rejected
INGM decides here, and it fails closed.

=== THE OUTCOME IS EVIDENCE EITHER WAY ===

A resolved registrant may still have no current ticker -- Dell's original
registrant stopped filing after the 2013 buyout. That is not a failure of this
module. It converts "unreachable" from an inference about the method into a
documented fact about a named company: the registrant is identified, the
lineage is confirmed, and the security is gone. That is what a survivorship
statement needs, and it is strictly better than an unresolved name.

The form-type filter is deliberately NOT set. `type=10-K` silently excludes
foreign private issuers, who file 20-F -- Nokia and Philips among them -- which
would have made "no such registrant" indistinguishable from "files a different
form".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urlencode

PEER_NAME_SEARCH_RULE_ID = "HYP04-PEER-NAME-SEARCH-RULE-v1"

COMPANY_SEARCH_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

#: Cap on candidate CIKs taken from one search response. A name matching
#: dozens of registrants is a name too generic to resolve, and following all of
#: them would spend requests to produce ambiguity we would refuse anyway.
MAX_CANDIDATES_PER_NAME = 8

_CIK_RE = re.compile(r"<cik>(\d+)</cik>", re.I)
_CONFORMED_RE = re.compile(r"<conformed-name>([^<]*)</conformed-name>", re.I)

STATUS_NO_HITS = "no_registrant_matched"
STATUS_RESOLVED = "registrant_resolved"
STATUS_AMBIGUOUS = "AMBIGUOUS_multiple_registrants_match"
STATUS_NO_LINEAGE_MATCH = "hits_found_but_none_matched_at_the_disclosure_date"

#: A registrant was identified and confirmed, but carries no current ticker.
#: The peer is genuinely untradeable, which is a MEASURED survivorship loss.
STATUS_RESOLVED_NOT_TRADED = "registrant_resolved_but_no_current_ticker"

#: The search never returned. SEPARATE FROM "no registrant matched", and the
#: distinction is not pedantry: the first run of this module recorded eight
#: 503s and read timeouts as "no_registrant_matched", turning an unanswered
#: question into a stated finding about 249 events of sample. That is data
#: availability deciding a result, which is the failure this project refuses
#: everywhere else. An unanswered name is unanswered.
STATUS_SEARCH_FAILED = "SEARCH_FAILED_question_unanswered"


def search_url(name: str, *, count: int = 40) -> str:
    """The company-search URL for `name`. No form-type filter, deliberately."""
    return COMPANY_SEARCH_URL + "?" + urlencode({
        "action": "getcompany",
        "company": name,
        "owner": "include",
        "count": str(count),
        "output": "atom",
    })


def parse_candidate_ciks(xml: str, *,
                         limit: int = MAX_CANDIDATES_PER_NAME) -> list[str]:
    """CIKs from a company-search response, in order, deduplicated.

    Both response shapes yield `<cik>`: the single-match form nests it in
    `company-info`, the multi-match form repeats it per `entry`. Only the CIK
    is read -- the multi-match form's company name is an unusable
    `ARRAY(0x...)` string, so names always come from `submissions` instead.
    """
    out: list[str] = []
    for m in _CIK_RE.findall(xml or ""):
        c = m.zfill(10)
        if c not in out:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def parse_conformed_names(xml: str) -> list[str]:
    """Conformed names, when the response is the single-match shape.

    Returns [] for a multi-match response. Used for reporting only; nothing is
    accepted on the strength of it.
    """
    return [n for n in _CONFORMED_RE.findall(xml or "")
            if n and not n.startswith("ARRAY(")]


@dataclass(frozen=True)
class NameSearchResult:
    """One unresolved counterparty held against EDGAR's company search."""

    anchor_ticker: str = ""
    counterparty: str = ""
    as_of_date: str = ""
    status: str = STATUS_NO_HITS
    peer_ticker: str = ""
    registrant_cik: str = ""
    registrant_name_at_as_of: str = ""
    candidates_examined: int = 0
    accepted_ciks: tuple[str, ...] = ()
    detail: str = ""
    incremental_anchor_events: int = 0

    @property
    def resolved(self) -> bool:
        return self.status in (STATUS_RESOLVED, STATUS_RESOLVED_NOT_TRADED)

    @property
    def tradeable(self) -> bool:
        return self.status == STATUS_RESOLVED and bool(self.peer_ticker)

    def as_dict(self) -> dict[str, Any]:
        return {
            "anchor_ticker": self.anchor_ticker,
            "counterparty": self.counterparty,
            "as_of_date": self.as_of_date,
            "status": self.status,
            "peer_ticker": self.peer_ticker,
            "registrant_cik": self.registrant_cik,
            "registrant_name_at_as_of": self.registrant_name_at_as_of,
            "candidates_examined": self.candidates_examined,
            "accepted_ciks": list(self.accepted_ciks),
            "detail": self.detail,
            "incremental_anchor_events": self.incremental_anchor_events,
            "resolved": self.resolved,
            "tradeable": self.tradeable,
        }


def decide(
    *,
    anchor_ticker: str,
    counterparty: str,
    as_of_date: str,
    accepted: list[tuple[str, str]],
    candidates_examined: int,
    ticker_for_cik: dict[str, str],
    incremental_anchor_events: int = 0,
    search_failed: bool = False,
    failure: str = "",
) -> NameSearchResult:
    """Turn lineage-accepted CIKs into one verdict. FAILS CLOSED.

    `accepted` is [(cik, name_in_force_at_as_of)] for every candidate whose
    submissions record passed `peer_lineage.assess` as CONTINUOUS. Two or more
    is AMBIGUOUS and resolves to nothing: a counterparty that matches two
    distinct registrants at the same date is a question, not an answer.
    """
    base = {
        "anchor_ticker": anchor_ticker,
        "counterparty": counterparty,
        "as_of_date": as_of_date,
        "candidates_examined": candidates_examined,
        "incremental_anchor_events": incremental_anchor_events,
    }
    # Checked BEFORE the no-hits branch, deliberately. A failed search also
    # has zero candidates, and letting it fall through would report silence
    # from the endpoint as an answer about the company.
    if search_failed:
        return NameSearchResult(
            status=STATUS_SEARCH_FAILED,
            detail="the company search did not return: " + (failure or
                   "unknown error") + ". This name is UNANSWERED, not "
                   "answered in the negative.",
            **base)
    if not candidates_examined:
        return NameSearchResult(
            status=STATUS_NO_HITS,
            detail="EDGAR's company search returned no registrant for this "
                   "name. It is a prefix match, so a name that does not start "
                   "the registrant's own name will not be found.",
            **base)
    if not accepted:
        return NameSearchResult(
            status=STATUS_NO_LINEAGE_MATCH,
            detail=f"{candidates_examined} registrant(s) matched the name but "
                   f"none was filing on {as_of_date} under it. The lineage "
                   "test refused them, the same way it refused INGM.",
            **base)
    if len(accepted) > 1:
        return NameSearchResult(
            status=STATUS_AMBIGUOUS,
            accepted_ciks=tuple(c for c, _ in accepted),
            detail="two or more distinct registrants match this name at the "
                   "disclosure date; that is a question for the curator, not "
                   "something to resolve by picking one.",
            **base)

    cik, name_then = accepted[0]
    ticker = ticker_for_cik.get(cik.zfill(10), "") or ticker_for_cik.get(
        cik.lstrip("0"), "")
    if not ticker:
        return NameSearchResult(
            status=STATUS_RESOLVED_NOT_TRADED,
            registrant_cik=cik, registrant_name_at_as_of=name_then,
            accepted_ciks=(cik,),
            detail="the registrant is identified and its lineage confirmed, "
                   "but it carries no ticker in SEC's current company list -- "
                   "it no longer trades. This is a MEASURED survivorship "
                   "loss, not an unresolved name.",
            **base)
    return NameSearchResult(
        status=STATUS_RESOLVED, peer_ticker=ticker,
        registrant_cik=cik, registrant_name_at_as_of=name_then,
        accepted_ciks=(cik,),
        detail=f"the registrant was filing on {as_of_date} as {name_then!r} "
               f"and trades today as {ticker}.",
        **base)


def summarise(rows: Iterable[NameSearchResult]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.status] = out.get(r.status, 0) + 1
    return out


def rule_description() -> dict[str, Any]:
    return {
        "rule_id": PEER_NAME_SEARCH_RULE_ID,
        "question": (
            "Which registrant did this counterparty name refer to, when SEC's "
            "list of current filers does not contain it?"),
        "the_search_only_generates_candidates": (
            "EDGAR's company search is an undocumented prefix match; it "
            "returned different results for 'Marconi' and 'Marconi "
            "Communications', and its multi-hit XML carries ARRAY(0x...) "
            "where the company name should be. Nothing is accepted on its "
            "say-so."),
        "acceptance_is_the_lineage_test": (
            "A candidate CIK is accepted only if peer_lineage.assess returns "
            "CONTINUOUS against that registrant's own submissions record: "
            "filing on the disclosure date, under a matching name. Two "
            "accepted registrants is AMBIGUOUS and resolves to nothing."),
        "no_form_type_filter": (
            "type=10-K silently excludes foreign private issuers, who file "
            "20-F. Filtering would make 'no such registrant' "
            "indistinguishable from 'files a different form'."),
        "a_resolved_registrant_may_not_trade": (
            "Identifying the registrant and finding it has no current ticker "
            "is a RESULT, not a failure: it converts an inference about the "
            "method into a documented fact about a named company, which is "
            "what a survivorship statement needs."),
        "curates_nothing": (
            "No edge is written and no candidate is promoted. The display "
            "gate is untouched."),
    }
