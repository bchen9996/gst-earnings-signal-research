#!/usr/bin/env python3
"""EDGAR-derived CANDIDATE linkage extractor -- HYP-04.

=== THIS IS NOT THE PRODUCTION LINKAGE MAP ===

It is a SECOND, INDEPENDENT candidate source, built to be reconciled against
the supply-chain teammate's map -- not to replace it, and never to be merged
into it automatically. Two independently-derived maps that agree raise
confidence; where they disagree, that disagreement is the finding, and it goes
to a human. `reconcile()` below flags and never merges.

Registry v1.1 lists the linkage map as a required external measurement whose
availability is `does_not_exist`. Output from this module does NOT change that
status. Only the teammate's map, or a human decision to promote this one, can.

=== WHY IT EXISTS: THE AS-OF DATE COMES FREE ===

Patch 11 requires a first-known/established-as-of date per linkage pair,
because a map built today encodes relationships known today, and applying it
to historical anchor events without that date is look-ahead bias.

An EDGAR-derived relationship carries its as-of date structurally: the filing
date of the 10-K that disclosed it. The relationship was, by construction,
publicly known on that date -- it was in a public filing. That is a stronger
provenance claim than a hand-assembled map can usually make, and it is the
main reason this source is worth having even though its coverage is partial.

=== COVERAGE IS A FLOOR, NOT A MAP ===

ASC 280-10-50-42 requires disclosure of a customer only when that customer
accounts for 10% or more of revenue. So this source systematically:

  * FINDS large customer relationships above that threshold
  * MISSES every real relationship below it
  * MISSES most supplier relationships (no symmetric disclosure requirement)
  * OFTEN finds the concentration WITHOUT the counterparty's name --
    "Customer A accounted for 18% of revenues" is a complete and compliant
    disclosure, and is useless as a linkage edge

An absent edge here is therefore NOT evidence of no relationship. Coverage is
reported explicitly, in the same spirit as the options-coverage audit, so the
floor is visible rather than mistaken for a census.

=== ACCESS DISCIPLINE ===

SEC's fair-access policy requires a User-Agent that identifies the requester
with a REACHABLE contact, and asks that clients stay under ~10 requests/second.

This module will not run without an owner-supplied contact. There is no
default and no fallback, for the same reason the options audit has no default
budget: it is not an implementer's call to make, and a placeholder address
defeats the entire purpose of the requirement. Measured behaviour:

    no User-Agent               -> 403 on every SEC host
    descriptive, no email       -> 403 on www.sec.gov (which serves /Archives/)
    identifying + real contact  -> 200

TLS verification is ON. The pre-existing `edgar_8k_signal.py` sets
`session.verify = False` and silences urllib3 warnings; this module does not
inherit that, because disabling certificate verification against the
authoritative source of the filings is not a tradeoff worth making in a
project whose entire premise is data provenance.
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

# --- SEC endpoints ---------------------------------------------------------
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# Older filings live in separate paginated files named by `filings.files[].name`.
SUBMISSIONS_EXTRA_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

# SEC asks for <10 req/sec. 0.15s between requests is ~6.7/sec, the same
# spacing the existing edgar_8k_signal module already uses.
REQUEST_SPACING_SECONDS = 0.15

CONTACT_REQUIRED_MESSAGE = (
    "EDGAR extraction refused: no owner-supplied contact. SEC's fair-access "
    "policy requires a User-Agent identifying the requester with a REACHABLE "
    "contact address, and www.sec.gov -- which serves both company_tickers.json "
    "and the /Archives/ filing documents -- returns 403 without one. This is "
    "not a value an implementer may invent: a placeholder address defeats the "
    "purpose of the requirement, which exists so SEC can reach the requester. "
    "Pass contact='Name email@realdomain.com'."
)


class EdgarContactError(RuntimeError):
    """Raised when EDGAR access is attempted without an owner-supplied contact."""


# ==========================================================================
# ASC 280 concentration-disclosure patterns
# ==========================================================================
# Deliberately conservative. A pattern that over-matches manufactures linkage
# edges that do not exist, which is worse than missing real ones -- a missing
# edge is a known limitation, a fabricated edge is a false finding.
# Extraction is TWO-STAGE rather than one large regex, because a single
# pattern with a lazy party group silently crosses sentence boundaries: on
# "Concentration of credit risk. During fiscal 2025, Apple Inc. accounted
# for 22%...", a leading [A-Z] under re.I happily captured the whole run-up
# as the "party". Stage 1 anchors on the concentration claim, which is
# unambiguous; stage 2 looks BACKWARD a bounded distance within the same
# sentence for the counterparty.
CONCENTRATION_ANCHORS: tuple[tuple[str, str], ...] = (
    (r"\baccounted for\s+(?:approximately\s+|about\s+|nearly\s+)?"
     r"(?P<pct>\d{1,3}(?:\.\d)?)\s*%\s+of\s+(?P<basis>[\w\s]{0,40}?"
     r"(?:revenue|revenues|sales|receivable|receivables))\b", "accounted_for"),
    (r"\b(?:represented|comprised|constituted|made up)\s+"
     r"(?:approximately\s+|about\s+)?(?P<pct>\d{1,3}(?:\.\d)?)\s*%\s+of\s+"
     r"(?P<basis>[\w\s]{0,40}?(?:revenue|revenues|sales|receivable|receivables))\b",
     "represented"),
)

# How far back from the concentration claim to look for the counterparty.
# Bounded, and never across a sentence boundary.
PARTY_LOOKBACK_CHARS = 120

# The counterparty phrase immediately preceding the claim. Anchored to the
# END of the lookback window so it is the NEAREST candidate, not the first.
PARTY_TAIL = re.compile(
    r"(?:(?:sales|revenues?|purchases|shipments)\s+to\s+)?"
    r"(?P<party>[A-Z][A-Za-z0-9.&'\-]*(?:\s+[A-Z][A-Za-z0-9.&'\-]*){0,4}"
    r"(?:\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?)?)"
    r"[,\s]*$")

# The unnamed-disclosure forms: a SINGLE real counterparty whose identity is
# withheld. "One customer accounted for 22%" means a genuine bilateral
# relationship exists and we simply do not know who it is with -- worth
# recording as an unnamed edge.
UNNAMED_TAIL = re.compile(
    r"(?:one|a single|another|the largest|our largest|a major|a second|"
    r"a third|certain|no)\s+"
    r"(?:direct\s+|major\s+|significant\s+|key\s+)?"
    r"(?:customer|client|distributor|reseller)s?"
    r"[,\s]*$|customer\s+[A-Z1-9][,\s]*$", re.I)

# AGGREGATE disclosures span MULTIPLE counterparties and are not a
# relationship with anyone. "Our 10 largest customers represented 26%" and
# "87 customers accounted for 90%" describe a portfolio, not an edge.
#
# These are dropped entirely rather than recorded as unnamed edges, because
# an unnamed edge still asserts that ONE relationship of that size exists --
# which an aggregate does not. Found in the 2026-08-18 canary, where this
# pattern produced three false edges out of nine, including one from a
# passage whose very next sentence read "No single customer represented 10%
# or more of our total Net revenues."
AGGREGATE_TAIL = re.compile(
    r"(?:\d{1,3}|two|three|four|five|six|seven|eight|nine|ten|"
    r"several|multiple|various|top|our top|largest|combined|aggregate)\s+"
    r"(?:\d{1,3}\s+)?"
    r"(?:largest\s+|major\s+|significant\s+|principal\s+|key\s+)?"
    r"(?:customer|client|distributor|reseller)s"      # PLURAL only
    r"(?:\s*,?\s*(?:including|such as|comprising)[^,]{0,60})?"  # parenthetical aside
    r"[,\s]*$", re.I)

# APPOSITIVE naming: "our largest customer, CVS Health Corporation ("CVS"),"
# The counterparty IS named, but it follows the role phrase rather than
# preceding it, so a purely backward-looking scan reads "our largest customer"
# as an unnamed disclosure and discards the name sitting right beside it.
# Found on MCK in the 2026-08-18 run, where CVS was in the filing text and
# recorded as UNNAMED.
APPOSITIVE_NAME = re.compile(
    r"(?:our|the|its)\s+(?:single\s+)?(?:largest|principal|primary|biggest|"
    r"major|top)\s+(?:customer|client|distributor)\s*,\s*"
    r"(?P<party>[A-Z][A-Za-z0-9.&'\-]*(?:\s+[A-Z][A-Za-z0-9.&'\-]*){0,5}"
    r"(?:\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?)?)"
    r"\s*(?:\(|,)", re.I)

# A disclosure explicitly stating there is NO concentration. Recorded, because
# "we checked and there is nothing above 10%" is genuine information -- it is
# distinguishable from "we found no disclosure", which is merely absence.
NEGATIVE_PATTERN = re.compile(
    r"no\s+(?:single\s+)?(?:customer|client)[^.]{0,120}?"
    r"(?:accounted for|represented|exceeded)[^.]{0,40}?"
    r"(?:more than\s+)?\d{1,2}\s*%", re.I)

# Generic placeholders that are NOT company names. A disclosure naming
# "Customer A" is compliant and complete, and completely useless as an edge.
UNNAMED_TOKENS = re.compile(
    r"^(?:customers?|clients?|distributors?|resellers?|one|a single|our largest|"
    r"two|three|another|certain|the largest|"
    r"customer\s+[a-z1-9]|company|the company|our company|"
    r"this customer|such customer|each|no customer|"
    r"concentration|revenue|revenues|sales|net sales|total|segment|"
    r"gross margin|accounts receivable)\b\.?$", re.I)

CORP_SUFFIX = re.compile(
    r"\b(inc|corp|corporation|company|co|ltd|limited|plc|llc|lp|holdings|"
    r"group|technologies|systems|international|nv|ag|sa)\b\.?", re.I)

# Abbreviations whose trailing period is NOT a sentence boundary. Without
# this, "Apple Inc. accounted for 22%..." has its lookback window truncated at
# the period in "Inc.", leaving nothing to match -- the naive splitter destroys
# precisely the corporate names this extractor exists to capture.
_ABBREV = re.compile(
    r"(?:^|[\s(])(?:Inc|Corp|Co|Ltd|Lim|LLC|LLP|LP|PLC|NV|AG|SA|SE|AB|AS|"
    r"Mr|Mrs|Ms|Dr|Jr|Sr|St|No|Nos|U\.S|Fig|Approx|[A-Z])\.$")


# How far to look for a sentence boundary in either direction.
SENTENCE_SPAN_CHARS = 400

# An aggregate SUBJECT anywhere earlier in the same sentence governs every
# clause in it. Unlike AGGREGATE_TAIL this is not anchored to the end, so it
# catches trailing clauses: "...ten largest customers accounted for 73% ...
# and comprised 43% of receivables" -- the 43% is equally aggregate.
AGGREGATE_SUBJECT = re.compile(
    r"\b(?:\d{1,3}|two|three|four|five|six|seven|eight|nine|ten|"
    r"several|multiple|various|top|combined)\s+"
    r"(?:\d{1,3}\s+)?"
    r"(?:largest\s+|major\s+|significant\s+|principal\s+|key\s+)?"
    r"(?:customer|client|distributor|reseller)s\b", re.I)


def _first_sentence_break(window: str) -> int:
    """Index of the first REAL sentence break, or -1. Mirror of the reverse scan."""
    for i in range(len(window) - 1):
        if window[i] not in ".;":
            continue
        if window[i + 1] not in " \t":
            continue
        if window[i] == "." and _ABBREV.search(window[:i + 1]):
            continue
        return i + 1
    return -1


def _last_sentence_break(window: str) -> int:
    """Index just past the last REAL sentence break, or -1 if there is none.

    Scans candidate ". " / "; " positions from the right and skips any whose
    preceding token is a known abbreviation or a single capital letter.
    """
    for i in range(len(window) - 2, -1, -1):
        if window[i] not in ".;":
            continue
        if i + 1 < len(window) and window[i + 1] not in " \t":
            continue
        if window[i] == "." and _ABBREV.search(window[:i + 1]):
            continue
        return i + 2
    return -1


# POSITIVE requirement: the disclosure must actually be about a customer.
#
# Without this the extractor matched any "X% of revenue" sentence, and the
# overwhelming majority of those in a 10-K are not customer concentrations at
# all. The 2026-08-18 full-universe run produced these false positives, none
# of which involve a counterparty:
#
#   NFLX 56%  "Currencies denominated in other than the U.S. dollar
#              accounted for 56% of revenue"              -> currency mix
#   ALB  39%  "net sales shipped to or within China
#              represented 39% of our total net sales"    -> geography
#   CCL  65%  "Passenger ticket revenues made up 65%"     -> product mix
#   AVB  1.3% "leased commercial space ... 1.3%"          -> segment mix
#   ROP  9%   "operating companies whose functional
#              currency is not the U.S. dollar ... 9%"    -> currency mix
#
# Sub-threshold values were the tell: ASC 280 requires disclosure only at
# ~10% or more, so a 1.3% or 4% "concentration" cannot be one.
# Satisfied by EITHER counterparty ROLE language, OR a directed
# sales-to / purchases-from construction naming an entity. Requiring the
# literal word "customer" was too strict: "Sales to Dell Technologies Inc.
# represented 13% of total revenues" is unambiguously a counterparty
# disclosure and never uses it.
COUNTERPARTY_ROLE = re.compile(
    r"\b(?:customer|customers|client|clients|distributor|distributors|"
    r"reseller|resellers|purchaser|purchasers|licensee|licensees|"
    r"supplier|suppliers|vendor|vendors|foundry|contract manufacturer)\b", re.I)

DIRECTED_TRADE = re.compile(
    r"\b(?:sales|revenues?|shipments|purchases|orders)\s+(?:to|from)\s+"
    r"(?!or within\b)(?:our\s+|the\s+|its\s+)?[A-Z]", re.I)


def _has_counterparty_context(sentence: str) -> bool:
    return bool(COUNTERPARTY_ROLE.search(sentence)
                or DIRECTED_TRADE.search(sentence))

# Statistics that are ABOUT something other than a counterparty. Presence of
# any of these in the sentence disqualifies it even if customer language also
# appears somewhere nearby.
NON_CUSTOMER_SUBJECT = re.compile(
    r"\b(?:currenc(?:y|ies)|foreign exchange|exchange rate|"
    r"denominated|functional currency|foreign operations|"
    r"shipped to or within|geograph|region|regional|country|countries|"
    r"segment revenue|product line|passenger ticket|onboard|"
    r"commercial space|square feet|square foot)\b", re.I)

DIRECTION_CUSTOMER = "customer"       # counterparty BUYS from the filer
DIRECTION_SUPPLIER = "supplier"       # counterparty SELLS to the filer
SUPPLIER_HINT = re.compile(r"\b(supplier|vendor|contract manufacturer|foundry|"
                           r"purchases from|sourced from)\b", re.I)


@dataclass
class LinkageEdge:
    """One extracted candidate relationship, with its provenance attached."""

    reporting_company: str            # ticker of the filer
    reporting_cik: str
    named_counterparty: Optional[str]  # None when the filing said "Customer A"
    counterparty_is_named: bool
    direction: str                    # customer | supplier
    concentration_pct: Optional[float]
    as_of_date: str                   # the 10-K filing date -- Patch 11's field
    accession: str
    form: str
    source: str = "EDGAR_10K_ASC280"
    pattern: str = ""
    context: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    edges: list[LinkageEdge] = field(default_factory=list)
    companies_attempted: list[str] = field(default_factory=list)
    companies_with_10k: list[str] = field(default_factory=list)
    companies_with_any_disclosure: list[str] = field(default_factory=list)
    companies_with_named_counterparty: list[str] = field(default_factory=list)
    companies_with_explicit_no_concentration: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    requests_made: int = 0

    def coverage(self) -> dict[str, Any]:
        n = len(self.companies_attempted) or 1
        named_edges = [e for e in self.edges if e.counterparty_is_named]
        return {
            "companies_attempted": len(self.companies_attempted),
            "companies_with_10k": len(self.companies_with_10k),
            "companies_with_any_disclosure": len(self.companies_with_any_disclosure),
            "companies_with_named_counterparty": len(self.companies_with_named_counterparty),
            "companies_with_explicit_no_concentration":
                len(self.companies_with_explicit_no_concentration),
            "pct_with_10k": round(100.0 * len(self.companies_with_10k) / n, 1),
            "pct_with_any_disclosure":
                round(100.0 * len(self.companies_with_any_disclosure) / n, 1),
            "pct_with_named_counterparty":
                round(100.0 * len(self.companies_with_named_counterparty) / n, 1),
            "total_edges": len(self.edges),
            "named_edges": len(named_edges),
            "unnamed_edges": len(self.edges) - len(named_edges),
            "errors": len(self.errors),
            "requests_made": self.requests_made,
        }


# ==========================================================================
# Text handling
# ==========================================================================
def strip_markup(raw: str) -> str:
    """Filing HTML/XBRL -> readable text. Not a parser; a normaliser."""
    txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = _html.unescape(txt)
    txt = txt.replace("\xa0", " ")
    return re.sub(r"\s+", " ", txt)


def clean_party(name: str) -> Optional[str]:
    """Normalise a captured party, or None if it is not a real company name.

    The blocklist is checked BOTH before and after stripping a leading
    article. Checking only afterwards let "The Company" through: the article
    strip turned it into "Company", which is not in the pre-strip blocklist
    and carries a corporate suffix, so it validated as a company name.
    """
    n = (name or "").strip(" ,.;:-")
    if not n or UNNAMED_TOKENS.match(n):
        return None
    stripped = re.sub(r"^(?:the|our|its|a|an)\s+", "", n, flags=re.I).strip()
    if not stripped or UNNAMED_TOKENS.match(stripped):
        return None
    n = stripped
    if len(n) < 3 or n.count(" ") > 6:
        return None
    # Require either a corporate suffix or Title Case -- otherwise sentence
    # fragments get captured as company names.
    if not CORP_SUFFIX.search(n) and not re.match(r"^(?:[A-Z][\w.&'\-]*\s?){1,5}$", n):
        return None
    return n


def infer_direction(context: str) -> str:
    return DIRECTION_SUPPLIER if SUPPLIER_HINT.search(context) else DIRECTION_CUSTOMER


def extract_edges_from_text(
    text: str, *, ticker: str, cik: str, filing_date: str,
    accession: str, form: str = "10-K",
) -> tuple[list[LinkageEdge], bool]:
    """Extract candidate edges from one filing's text.

    Returns (edges, explicit_no_concentration). Pure function -- no I/O, which
    is what lets the whole extraction path be tested offline against fixtures.
    """
    edges: list[LinkageEdge] = []
    seen: set[tuple] = set()

    for pattern, label in CONCENTRATION_ANCHORS:
        for m in re.finditer(pattern, text, re.I):
            try:
                pct = float(m.group("pct"))
            except (TypeError, ValueError):
                continue
            # A "concentration" above 100% is a parse error, not a disclosure.
            if not (0.0 < pct <= 100.0):
                continue

            # Look BACKWARD for the counterparty, bounded, and never across a
            # sentence boundary -- the preceding sentence's subject is not this
            # sentence's counterparty.
            back_start = max(0, m.start() - PARTY_LOOKBACK_CHARS)
            window = text[back_start:m.start()]
            sentence_break = _last_sentence_break(window)
            if sentence_break != -1:
                window = window[sentence_break:]

            # The sentence this claim sits in. Both ends are bounded by REAL
            # sentence breaks, not by a fixed character count.
            #
            # A fixed forward window let the appositive scan reach into the
            # NEXT sentence: on MCK, the 43%-of-receivables clause belongs to
            # "our ten largest customers", but "Sales to our largest customer,
            # CVS Health Corporation" began the following sentence and landed
            # inside the window, attributing an aggregate to CVS.
            lookback_start = max(0, m.start() - SENTENCE_SPAN_CHARS)
            pre = text[lookback_start:m.start()]
            sb = _last_sentence_break(pre)
            sent_start = lookback_start + (sb if sb != -1 else 0)

            post = text[m.end():min(len(text), m.end() + SENTENCE_SPAN_CHARS)]
            fb = _first_sentence_break(post)
            sent_end = m.end() + (fb if fb != -1 else len(post))
            sentence = text[sent_start:sent_end]

            # The aggregate subject is established once at the START of a
            # sentence and governs every clause in it, so it is checked
            # against the whole preceding span, not the short tail window.
            # "...ten largest customers ... accounted for 73% ... and
            # comprised 43% ..." -- the 43% is just as aggregate as the 73%.
            subject_span = text[sent_start:m.start()]

            # POSITIVE requirement: this must be a disclosure ABOUT a
            # counterparty. Most "X% of revenue" sentences in a 10-K are
            # currency, geographic, segment or product mix, and matching them
            # produced six false edges in the 2026-08-18 full-universe run.
            # TOPIC context may legitimately come from neighbouring sentences
            # -- a concentration footnote reads "Concentration of credit risk.
            # ... Apple Inc. accounted for 22% ... No other customer ..." and
            # the role word can sit in any of them. ATTRIBUTION (which name,
            # which subject) must stay sentence-bounded, and does: `sentence`
            # and `subject_span` below are used for that and are not widened.
            topic_window = text[max(0, m.start() - SENTENCE_SPAN_CHARS):
                                min(len(text), m.end() + SENTENCE_SPAN_CHARS)]
            if not _has_counterparty_context(topic_window):
                continue
            # The disqualifier is checked on the SENTENCE, not the wider
            # window: a neighbouring sentence about currency mix must not veto
            # a genuine customer disclosure, and vice versa.
            if NON_CUSTOMER_SUBJECT.search(sentence):
                continue

            # An AGGREGATE disclosure describes a portfolio of counterparties,
            # not a relationship with any one of them. Dropped outright --
            # recording it even as an "unnamed edge" would assert that a
            # single relationship of that size exists, which is false.
            if AGGREGATE_TAIL.search(window) or AGGREGATE_SUBJECT.search(subject_span):
                continue

            party = None
            # Appositive form first: the name follows the role phrase, so a
            # backward-only scan would classify it as unnamed.
            am = APPOSITIVE_NAME.search(sentence)
            if am:
                party = clean_party(am.group("party"))
            if party is None and not UNNAMED_TAIL.search(window):
                pm = PARTY_TAIL.search(window)
                if pm:
                    party = clean_party(pm.group("party"))

            start, end = max(0, m.start() - 200), min(len(text), m.end() + 200)
            ctx = text[start:end].strip()

            key = (party, pct, label)
            if key in seen:
                continue
            seen.add(key)

            edges.append(LinkageEdge(
                reporting_company=ticker,
                reporting_cik=cik,
                named_counterparty=party,
                counterparty_is_named=party is not None,
                direction=infer_direction(ctx),
                concentration_pct=pct,
                as_of_date=filing_date,
                accession=accession,
                form=form,
                pattern=label,
                context=ctx[:400],
            ))

    return edges, bool(NEGATIVE_PATTERN.search(text))


# ==========================================================================
# Live EDGAR client -- refuses to run without an owner-supplied contact
# ==========================================================================
class EdgarClient:
    """Minimal SEC client. Verifies TLS. Paces requests. Caches per process."""

    def __init__(self, contact: Optional[str], *,
                 spacing: float = REQUEST_SPACING_SECONDS,
                 max_requests: Optional[int] = None):
        if not contact or "@" not in contact or contact.strip().endswith("@"):
            raise EdgarContactError(CONTACT_REQUIRED_MESSAGE)
        if re.search(r"@(?:example|test|invalid|localhost)\.", contact, re.I):
            raise EdgarContactError(
                CONTACT_REQUIRED_MESSAGE
                + f" The supplied contact {contact!r} uses a reserved "
                  "placeholder domain (RFC 2606), which is not reachable."
            )
        # Measured, not assumed: www.sec.gov returns 403 for no-reply domains
        # while accepting the same User-Agent with a deliverable address. That
        # is the fair-access policy working as intended -- a no-reply address
        # cannot receive the contact the policy exists to enable. Rejecting it
        # here turns an opaque 403 mid-run into a clear refusal up front.
        if re.search(r"@(?:.*\.)?(?:noreply|no-reply|donotreply)\.", contact, re.I) \
                or re.search(r"\bnoreply@|\bno-reply@|\bdonotreply@", contact, re.I):
            raise EdgarContactError(
                CONTACT_REQUIRED_MESSAGE
                + f" The supplied contact {contact!r} uses a no-reply domain. "
                  "Measured behaviour: www.sec.gov returns 403 for these and "
                  "200 for a deliverable address."
            )
        import requests  # deferred: importing this module must not require it

        self.contact = contact.strip()
        self.spacing = spacing
        self.max_requests = max_requests
        self.requests_made = 0
        self._session = requests.Session()
        self._session.verify = True          # deliberately ON
        self._session.headers.update({
            "User-Agent": self.contact,
            "Accept-Encoding": "gzip, deflate",
        })
        self._cik_map: Optional[dict[str, str]] = None

    def _get(self, url: str, timeout: int = 30):
        if self.max_requests is not None and self.requests_made >= self.max_requests:
            raise RuntimeError(
                f"EDGAR request cap of {self.max_requests} reached; stopping "
                "rather than continuing. No silent truncation.")
        if self.requests_made:
            time.sleep(self.spacing)
        self.requests_made += 1
        r = self._session.get(url, timeout=timeout)
        r.raise_for_status()
        return r

    def cik_for(self, ticker: str) -> Optional[str]:
        if self._cik_map is None:
            data = self._get(TICKER_MAP_URL).json()
            self._cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                             for v in data.values()}
        return self._cik_map.get(ticker.upper())

    def latest_10k(self, cik: str) -> Optional[dict[str, str]]:
        data = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
        rec = data["filings"]["recent"]
        for i, form in enumerate(rec["form"]):
            if form == "10-K":
                return {"accession": rec["accessionNumber"][i],
                        "filing_date": rec["filingDate"][i],
                        "primary_document": rec["primaryDocument"][i],
                        "form": form}
        return None

    def all_10ks(self, cik: str) -> list[dict[str, str]]:
        """EVERY 10-K on record, newest first.

        `latest_10k` above answers "what does this company disclose now?".
        That is the wrong question for a linkage map. An edge's as_of_date is
        the filing date that disclosed it, and under the peer-eligibility rule
        an edge only counts for anchor events STRICTLY AFTER that date -- so an
        edge sourced from the newest 10-K covers almost no history, even when
        the underlying relationship is a decade old. The useful question is
        "what is the EARLIEST filing that discloses this relationship?", and
        answering it requires every 10-K, not the first one found.

        SEC splits the submissions record: `filings.recent` holds roughly the
        last thousand filings, and anything older lives in separate paginated
        JSON files listed under `filings.files`. A walk that reads only
        `recent` silently truncates at whatever depth that block happens to
        reach -- which for a frequent filer can be well short of its earliest
        10-K, and would look identical to "no earlier disclosure exists".
        Those extra files are fetched, and each costs a request.
        """
        data = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
        filings = data.get("filings", {})
        blocks = [filings.get("recent", {})]

        for extra in filings.get("files", []) or []:
            name = extra.get("name")
            if not name:
                continue
            blocks.append(self._get(SUBMISSIONS_EXTRA_URL.format(name=name)).json())

        out: list[dict[str, str]] = []
        for blk in blocks:
            forms = blk.get("form") or []
            for i, form in enumerate(forms):
                if form != "10-K":
                    continue
                out.append({
                    "accession": blk["accessionNumber"][i],
                    "filing_date": blk["filingDate"][i],
                    "primary_document": blk["primaryDocument"][i],
                    "form": form,
                })
        # Newest first, so a caller can stop early and still know it has seen
        # every filing more recent than where it stopped.
        out.sort(key=lambda f: f["filing_date"], reverse=True)
        return out

    def filing_text(self, cik: str, accession: str, document: str) -> str:
        url = ARCHIVE_DOC_URL.format(cik=int(cik), acc=accession.replace("-", ""),
                                     doc=document)
        return strip_markup(self._get(url, timeout=60).text)


def extract_for_universe(
    tickers: Iterable[str], *, contact: Optional[str],
    max_requests: Optional[int] = None,
) -> ExtractionResult:
    """Run extraction across a ticker universe. MAKES REAL SEC REQUESTS."""
    client = EdgarClient(contact, max_requests=max_requests)
    res = ExtractionResult()

    for t in tickers:
        res.companies_attempted.append(t)
        try:
            cik = client.cik_for(t)
            if cik is None:
                res.errors[t] = "no CIK found for ticker"
                continue
            filing = client.latest_10k(cik)
            if filing is None:
                res.errors[t] = "no 10-K on the recent submissions page"
                continue
            res.companies_with_10k.append(t)
            text = client.filing_text(cik, filing["accession"],
                                      filing["primary_document"])
            edges, no_conc = extract_edges_from_text(
                text, ticker=t, cik=cik, filing_date=filing["filing_date"],
                accession=filing["accession"], form=filing["form"])
            if edges:
                res.companies_with_any_disclosure.append(t)
                if any(e.counterparty_is_named for e in edges):
                    res.companies_with_named_counterparty.append(t)
            if no_conc:
                res.companies_with_explicit_no_concentration.append(t)
            res.edges.extend(edges)
        except Exception as e:                     # noqa: BLE001 -- recorded, not raised
            res.errors[t] = f"{type(e).__name__}: {str(e)[:160]}"

    res.requests_made = client.requests_made
    return res


# ==========================================================================
# Reconciliation -- FLAGS, never merges
# ==========================================================================
def reconcile(edgar_edges: list[LinkageEdge],
              teammate_map: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    """Compare the two candidate sources. Produces a review queue, not a map.

    Deliberately has no merge path. Agreement raises confidence; disagreement
    is the finding and goes to a human. Automatically reconciling two sources
    would destroy exactly the independence that makes having two worthwhile.
    """
    if teammate_map is None:
        return {
            "status": "TEAMMATE_MAP_UNAVAILABLE",
            "reconciled": False,
            "note": ("The teammate's supply-chain map does not exist yet, so "
                     "there is nothing to reconcile against. The EDGAR source "
                     "stands alone as a candidate and does NOT become the "
                     "production map by default."),
            "edgar_named_edges": sum(1 for e in edgar_edges if e.counterparty_is_named),
        }

    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    edgar_pairs = {(e.reporting_company.upper(), norm(e.named_counterparty or ""))
                   for e in edgar_edges if e.counterparty_is_named}
    mate_pairs = {(str(r.get("anchor_ticker", "")).upper(),
                   norm(str(r.get("peer_ticker", "")))) for r in teammate_map}

    both = sorted(edgar_pairs & mate_pairs)
    edgar_only = sorted(edgar_pairs - mate_pairs)
    mate_only = sorted(mate_pairs - edgar_pairs)

    return {
        "status": "RECONCILED_FOR_HUMAN_REVIEW",
        "reconciled": False,
        "merged": False,
        "in_both_sources": both,
        "edgar_only": edgar_only,
        "teammate_only": mate_only,
        "agreement_count": len(both),
        "disagreement_count": len(edgar_only) + len(mate_only),
        "interpretation": {
            "in_both": "Independently corroborated. Highest confidence.",
            "edgar_only": ("Disclosed in a 10-K but absent from the teammate's "
                           "map. May be a genuine gap in the map, or a "
                           "relationship the map deliberately excluded."),
            "teammate_only": ("In the map but not found in EDGAR. Expected and "
                              "common -- ASC 280 only requires naming customers "
                              "above 10% of revenue, so most real relationships "
                              "are invisible to this source. Absence here is "
                              "NOT evidence against the relationship."),
        },
        "no_automatic_merge": ("Nothing is merged. Every disagreement is a "
                               "human reconciliation item."),
    }


def concentration_feature_candidate(res: ExtractionResult) -> dict[str, Any]:
    """Per-company customer-concentration magnitude, as a PROVISIONAL feature.

    This is the one thing the EDGAR source produces reliably even when it
    yields no linkage edges at all: a dated, per-company concentration
    magnitude with filing-date provenance.

    IT IS NOT THE COVERAGE/THINNESS PROXY. Those measure different things and
    must not be conflated:

      coverage/thinness  -- how much ATTENTION a peer receives (search volume,
                            analyst count, news volume). A proxy for whether
                            the market is likely already pricing a link.
      concentration      -- how much of the peer's OWN REVENUE depends on its
                            largest customer. A property of its business, not
                            of the market's attention to it.

    A thinly-covered peer may have no customer concentration; a heavily
    covered one may have 90%. Folding this into the existing proxy would
    silently change what that proxy means after the fact.

    NOT ADOPTED. This is recorded as a candidate for the Phase 2 feature-list
    lock, where including it is a real decision made before results are seen --
    not something that accretes into the feature set because the data happened
    to be lying around.
    """
    by_company: dict[str, dict[str, Any]] = {}
    for e in res.edges:
        rec = by_company.setdefault(e.reporting_company, {
            "ticker": e.reporting_company,
            "as_of_date": e.as_of_date,
            "accession": e.accession,
            "disclosed_concentrations_pct": [],
            "max_disclosed_pct": None,
            "n_disclosures": 0,
            "any_named_counterparty": False,
        })
        if e.concentration_pct is not None:
            rec["disclosed_concentrations_pct"].append(e.concentration_pct)
        rec["n_disclosures"] += 1
        rec["any_named_counterparty"] |= e.counterparty_is_named

    for rec in by_company.values():
        pcts = rec["disclosed_concentrations_pct"]
        rec["max_disclosed_pct"] = max(pcts) if pcts else None

    # Companies that affirmatively stated NO customer reached the threshold
    # are informative and distinct from companies where nothing was found.
    for t in res.companies_with_explicit_no_concentration:
        by_company.setdefault(t, {
            "ticker": t, "as_of_date": None, "accession": None,
            "disclosed_concentrations_pct": [], "max_disclosed_pct": None,
            "n_disclosures": 0, "any_named_counterparty": False,
        })["explicit_no_concentration"] = True

    silent = [t for t in res.companies_with_10k
              if t not in by_company
              and t not in res.companies_with_explicit_no_concentration]

    return {
        "feature_name": "edgar_customer_concentration_pct",
        "status": "PROVISIONAL_CANDIDATE_NOT_ADOPTED",
        "adopted": False,
        "decision_point": (
            "Phase 2 feature-list lock. Including this is a preregistered "
            "decision to be made BEFORE results are seen, not an adoption that "
            "happens because the data exists."),
        "is_the_coverage_thinness_proxy": False,
        "why_distinct_from_coverage_thinness": (
            "coverage/thinness measures ATTENTION paid to a peer (search "
            "volume, analyst count, news volume) as a proxy for whether the "
            "market already prices a link. This measures how much of the "
            "peer's OWN REVENUE depends on its largest customer -- a property "
            "of its business, not of attention to it. A thinly-covered peer "
            "may have no concentration; a heavily-covered one may have 90%. "
            "Merging them would silently redefine the existing proxy."),
        "provenance": (
            "Each value carries the filing date of the 10-K that disclosed it, "
            "so it is point-in-time by construction."),
        "known_limitations": [
            "ASC 280 discloses only concentrations at or above ~10% of "
            "revenue, so a null is 'nothing above the threshold', never zero.",
            "Aggregate disclosures ('our 10 largest customers') are excluded "
            "and contribute nothing to this feature.",
            "Values are as-reported and are not normalised across differing "
            "revenue bases or fiscal calendars.",
            "One filing per company (most recent 10-K); this is not a panel.",
        ],
        "per_company": sorted(by_company.values(), key=lambda r: r["ticker"]),
        "companies_silent_no_disclosure_found": sorted(silent),
        "n_with_a_disclosed_concentration":
            sum(1 for r in by_company.values() if r["max_disclosed_pct"] is not None),
        "n_explicit_no_concentration": len(res.companies_with_explicit_no_concentration),
        "n_silent": len(silent),
    }


def write_report(res: ExtractionResult, path: Path,
                 reconciliation: Optional[dict] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "artifact": "HYP-04 EDGAR-derived CANDIDATE linkage",
        "source": "SEC EDGAR 10-K ASC 280 concentration disclosures",
        "is_production_linkage_map": False,
        "status": "CANDIDATE_SOURCE_FOR_RECONCILIATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "not_a_replacement": (
            "This does NOT replace the supply-chain teammate's map and does not "
            "change registry v1.1's required-external-measurement availability, "
            "which remains does_not_exist. It is a parallel candidate source."),
        "coverage_is_a_floor": (
            "ASC 280 requires naming a customer only at >=10% of revenue. This "
            "source systematically misses smaller-but-real relationships, most "
            "supplier relationships, and every disclosure that says 'Customer A' "
            "without naming. An absent edge is NOT evidence of no relationship."),
        "as_of_date_provenance": (
            "Each edge's as_of_date is the filing date of the 10-K that "
            "disclosed it, satisfying Patch 11 structurally: the relationship "
            "was public on that date by construction."),
        "coverage": res.coverage(),
        "edges": [e.as_dict() for e in res.edges],
        "errors": res.errors,
        "reconciliation": reconciliation or {"status": "NOT_RUN"},
        "provisional_feature_candidate": concentration_feature_candidate(res),
    }, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="EDGAR candidate-linkage extractor (MAKES REAL SEC REQUESTS).")
    ap.add_argument("--contact", default=None,
                    help="REQUIRED. 'Name email@realdomain.com' per SEC fair-access policy.")
    ap.add_argument("--tickers", default=None, help="comma-separated; default = universe")
    ap.add_argument("--max-requests", type=int, default=None,
                    help="hard cap on SEC requests; stops and reports if hit")
    ap.add_argument("--out", type=Path,
                    default=LSE / "HYP04_EDGAR_CANDIDATE_LINKAGE.json")
    a = ap.parse_args(argv)

    if not a.contact:
        print(CONTACT_REQUIRED_MESSAGE, file=sys.stderr)
        return 2

    from .run_canary_audit import candidate_peer_universe
    tickers = ([t.strip().upper() for t in a.tickers.split(",")] if a.tickers
               else candidate_peer_universe())

    print(f"EDGAR candidate-linkage extraction over {len(tickers)} tickers")
    print(f"  cap: {a.max_requests or 'none'}   spacing: {REQUEST_SPACING_SECONDS}s")
    res = extract_for_universe(tickers, contact=a.contact, max_requests=a.max_requests)

    cov = res.coverage()
    print("\n=== COVERAGE ===")
    for k, v in cov.items():
        print(f"  {k:42s} {v}")
    write_report(res, a.out, reconciliation=reconcile(res.edges, None))
    print(f"\nWrote: {a.out}")
    print("\nCANDIDATE SOURCE ONLY. Not the production linkage map. "
          "Not merged with the teammate's map.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
