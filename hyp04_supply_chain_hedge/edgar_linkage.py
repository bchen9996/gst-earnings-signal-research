#!/usr/bin/env python3
"""EDGAR-derived CANDIDATE linkage extractor -- HYP-04.

=== THIS IS NOT THE PRODUCTION LINKAGE MAP ===

It is a SECOND, INDEPENDENT candidate source, built to be reconciled against
the supply-chain teammate's map -- not to replace it, and never to be merged
into it automatically. Two independently-derived maps that agree raise
confidence; where they disagree, that disagreement is the finding, and it goes
to a human. `reconcile()` below flags and never merges.

The registry lists the linkage map as a required external measurement with a
recorded availability. Output from this module does NOT change it, whatever it
currently reads -- only a governed registry version does. The value is
deliberately not restated here; read the registry.

Only a human decision to promote this source, or the teammate's map, changes
what is curated.

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

import gzip
import hashlib
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
# Every document of a filing, concatenated. The only route to pre-2001
# filings, whose per-document path does not exist.
FULL_SUBMISSION_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}.txt"

SOURCE_PRIMARY_DOCUMENT = "primary_document"
SOURCE_FULL_SUBMISSION = "full_submission_text"

# Server-side conditions worth exactly one retry. A 404 is not among them:
# it is a statement about the layout, not about load.
TRANSIENT_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)
TRANSIENT_RETRY_SECONDS = 1.0

# The on-disk response cache. Format is versioned because a stored body is
# only interchangeable with a live fetch if the reader agrees with the writer
# about what was stored; a reader that finds an older version ignores the
# entry rather than guessing.
CACHE_FORMAT_VERSION = 1
CACHE_KIND_TEXT = "text"
CACHE_KIND_JSON = "json"
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
# The denominator's qualifier class admits an APOSTROPHE. Without it, "15% of
# the Company's revenues" does not match at all -- such a disclosure is not
# merely unclassified, it is INVISIBLE, and classify_concentration_basis is
# never reached. Measured 2026-08-27 over a controlled grid: every
# apostrophe-s form was rejected and every non-possessive form accepted, and
# the split was exactly the apostrophe. Measured again 2026-08-28 over the
# cached corpus: it cost at least one real anchor, NIKE / Foot Locker at 11%
# of consolidated revenues.
_BASIS = (r"(?P<basis>[\w\s'\u2019]{0,40}?"
          r"(?:revenue|revenues|sales|receivable|receivables))\b")
_PCT = r"(?P<pct>\d{1,3}(?:\.\d)?)\s*%\s+of\s+"
_APPROX = r"(?:approximately\s+|about\s+|nearly\s+)?"

CONCENTRATION_ANCHORS: tuple[tuple[str, str], ...] = (
    (r"\baccounted for\s+" + _APPROX + _PCT + _BASIS, "accounted_for"),
    (r"\b(?:represented|comprised|constituted|made up)\s+"
     + _APPROX + _PCT + _BASIS, "represented"),
    # Copular and equivalence phrasings state exactly the relation the verbs
    # above state: "sales to X WERE approximately 15% of net sales" is
    # ordinary 10-K prose, not exotic phrasing.
    #
    # DELIBERATELY NOT INCLUDED: generated, provided, contributed. Those
    # describe what a counterparty CONTRIBUTED rather than asserting the share
    # IS the figure, so admitting them would be a semantic widening rather
    # than a phrasing fix. test_6l pins that distinction so a future change
    # admitting them is a visible decision.
    (r"\b(?:were|was|totaled|totalled|equaled|equalled|approximated)\s+"
     + _APPROX + _PCT + _BASIS, "equivalence"),
    # THE MULTI-YEAR "RESPECTIVELY" FORM. NIKE, 2002-08-14:
    #
    #   "During the years ended May 31, 2002, 2001 and 2000, revenues derived
    #    from Foot Locker, Inc. represented 10.9%, 11.8% and 12.4%,
    #    respectively of the Company's consolidated revenues."
    #
    # One sentence carrying one figure per fiscal year. Filings list the years
    # NEWEST FIRST and the percentages in the same order, so the FIRST
    # percentage is the reporting year's -- which is why `pct` captures only
    # that one and the rest are consumed unnamed.
    #
    # Pairing by position is what makes this safe to read at all. Taking the
    # largest of the percentages, or the last, would silently attribute a
    # prior year's concentration to the reporting year -- the same error the
    # stale-comparative gate exists to prevent, committed inside a single
    # sentence where that gate cannot see it.
    (r"\b(?:represented|accounted for|comprised|constituted|made up|were|was"
     r"|totaled|totalled)\s+" + _APPROX
     + r"(?P<pct>\d{1,3}(?:\.\d)?)\s*%"
     r"(?:\s*,\s*\d{1,3}(?:\.\d)?\s*%)*"
     r"\s+and\s+\d{1,3}(?:\.\d)?\s*%\s*,?\s*respectively\s*,?\s+of\s+"
     + _BASIS, "respectively"),
)

# How far back from the concentration claim to look for the counterparty.
# Bounded, and never across a sentence boundary.
PARTY_LOOKBACK_CHARS = 120

# ==========================================================================
# The DENOMINATOR of a concentration percentage
# ==========================================================================
# "58% of our Paper segment sales revenue" and "24% of our total consolidated
# revenues" are not the same disclosure. Until 2026-08-26 this module recorded
# both as a bare `concentration_pct` and threw the denominator away -- the
# anchors above already captured it in a `basis` group that nothing read.
#
# It matters because ASC 280-10-50-42 states its threshold against the
# ENTITY's revenues. Any rule that selects on ">= 10%" without fixing the
# denominator silently treats a segment share, an accounts-receivable share
# and a deferred-revenue share as the same quantity. PKG's ODP disclosure is
# the worked example, verbatim from the 2026-02-26 10-K: "our sales revenue to
# ODP represented 58% of our Paper segment sales revenue and 4% of our
# consolidated sales revenue."
#
# Classification is FAIL-CLOSED: a denominator this cannot confidently place
# is `other_or_unknown`, never the entity-wide reading.
BASIS_CONSOLIDATED_REVENUE = "consolidated_revenue"
BASIS_SEGMENT_REVENUE = "segment_revenue"
BASIS_RECEIVABLES = "receivables"
BASIS_DEFERRED_REVENUE = "deferred_revenue"
BASIS_UNKNOWN = "other_or_unknown"

CONCENTRATION_BASES: tuple[str, ...] = (
    BASIS_CONSOLIDATED_REVENUE, BASIS_SEGMENT_REVENUE, BASIS_RECEIVABLES,
    BASIS_DEFERRED_REVENUE, BASIS_UNKNOWN,
)

# Words that may qualify a revenue denominator while leaving it ENTITY-WIDE.
# Anything outside this set ("Paper", "North America", "Data Center") narrows
# the denominator to something smaller than the entity, so the basis is not
# consolidated.
_ENTITY_WIDE_QUALIFIER = re.compile(
    r"^(?:our|the|its|their|a|an|all|total|consolidated|combined|aggregate|"
    r"company|companys|net|gross|worldwide|global|overall|annual|fiscal|"
    r"year|years|ended|reported|sales|\d{2,4})$", re.I)
_REVENUE_HEAD = re.compile(r"^(?:revenue|revenues|sales)$", re.I)
_NARROWER_THAN_ENTITY = re.compile(
    r"\b(?:segment|segments|division|divisions|business\s+unit|product\s+line)\b",
    re.I)


def classify_concentration_basis(basis_text: Optional[str]) -> str:
    """Which denominator a concentration percentage was stated against.

    Reads only the words the filing used. Returns a member of
    CONCENTRATION_BASES; unrecognised denominators return BASIS_UNKNOWN rather
    than being assumed entity-wide.
    """
    if not basis_text:
        return BASIS_UNKNOWN
    low = " ".join(basis_text.split()).lower().replace("’", "").replace("'", "")
    if re.search(r"\breceivables?\b", low):
        return BASIS_RECEIVABLES
    if re.search(r"\bdeferred\b", low):
        return BASIS_DEFERRED_REVENUE
    if _NARROWER_THAN_ENTITY.search(low):
        return BASIS_SEGMENT_REVENUE
    tokens = low.split()
    if not tokens or not _REVENUE_HEAD.match(tokens[-1]):
        return BASIS_UNKNOWN
    if all(_ENTITY_WIDE_QUALIFIER.match(t) for t in tokens[:-1]):
        return BASIS_CONSOLIDATED_REVENUE
    return BASIS_UNKNOWN

# ==========================================================================
# Two fabrication CONSTRUCTIONS that no gate covered until 2026-08-28.
#
# Both were found by measuring a candidate anchor widening over the cached
# corpus -- and both turned out to be latent in the CURRENT extractor, not
# introduced by the widening. Measured: with an accepted verb ("accounted
# for", "represented") today's code produces both fabrications. They are
# absent from the corpus only because the particular filings that contain
# them happen to use a copular verb the anchor does not match.
#
# That is protection by accident. A filing writing the same construction with
# an accepted verb would produce a fabricated supply-chain relationship today,
# which is the one failure this source must not have.
# ==========================================================================

# "sales from the Company's Office Products Group were 16% of net sales"
# (Genuine Parts, 2010-02-26). The subject is the FILER'S OWN segment reached
# through a possessive self-reference, which INTERNAL_SUBJECT does not cover
# because it looks for "within the|our". Checked against the resolved PARTY,
# so it is construction-based rather than a list of segment names -- the
# lesson of the GEOGRAPHIC_PARTY list that lacked Singapore and Hong Kong.
SELF_REFERENTIAL_PARTY = re.compile(
    r"^(?:the\s+)?(?:Compan(?:y|ies)|Corporation|Registrant|Group)"
    r"(?:['\u2019]s)?\b", re.I)

# "Revenue from billings to China, including Hong Kong, was 24% of our
# revenue" (NVIDIA, 2019-02-21). "including X" makes X an INSTANCE of the
# category being measured, so the percentage belongs to the category and not
# to X. True whether X is a place or a company: a share attributed to a set
# is not a bilateral relationship with one member of it.
INCLUDING_APPOSITIVE = re.compile(
    r"\b(?:including|includes|such\s+as)[\s,]*$", re.I)


# THE COMMA IN "Foot Locker, Inc." -- both PARTY_TAIL and APPOSITIVE_NAME
# allowed a legal suffix only after whitespace, so the continuation stopped at
# the comma and the match, anchored to the end of the window, captured the
# bare suffix "Inc". That is a fabricated counterparty standing in for a real
# one. Measured on NIKE's FY2002 disclosure of Foot Locker at 11% of
# consolidated revenues, which this had reduced to "Inc".


# The counterparty phrase immediately preceding the claim. Anchored to the
# END of the lookback window so it is the NEAREST candidate, not the first.
PARTY_TAIL = re.compile(
    r"(?:(?:sales|revenues?|purchases|shipments)\s+to\s+)?"
    r"(?P<party>[A-Z][A-Za-z0-9.&'\-]*(?:\s+[A-Z][A-Za-z0-9.&'\-]*){0,4}"
    r"(?:,?\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?)?)"
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
    r"(?:,?\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?)?)"
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

# A LEGAL entity marker, as opposed to a descriptive word that merely appears
# in company names. The distinction matters: "Systems", "Technologies",
# "Group" and "International" are also how filers name their own operating
# SEGMENTS -- Leidos's "Defense Systems" is a segment, not a counterparty --
# so CORP_SUFFIX above cannot be used to establish that a name is a company.
LEGAL_ENTITY_SUFFIX = re.compile(
    r"\b(inc|corp|corporation|incorporated|ltd|limited|plc|llc|llp|lp|"
    r"nv|ag|sa|se|ab|as|oyj|kgaa|gmbh|pte|bhd)\b\.?", re.I)

# Places are not counterparties. Measured on the 2026-08-26 51-ticker run:
# Intel's "sales outside the U.S. accounted for 70% of our revenue" and Nike's
# "sales in the United States accounted for approximately 44% of total
# revenues" were both extracted as named customers. NON_CUSTOMER_SUBJECT
# already covers the WORDS "geographic", "region" and "country", but neither
# sentence contains one -- the geography is the bare place name itself.
GEOGRAPHIC_PARTY = re.compile(
    r"^(?:the\s+)?(?:u\.?\s?s\.?(?:a\.?)?|united\s+states(?:\s+of\s+america)?|"
    r"u\.?k\.?|united\s+kingdom|e\.?u\.?|europe|european\s+union|"
    r"emea|apac|latam|asia(?:\s*[-/]?\s*pacific)?|greater\s+china|china|"
    r"japan|korea|india|canada|mexico|brazil|germany|france|taiwan|"
    r"north\s+america|south\s+america|latin\s+america|"
    r"international|domestic|foreign|abroad|overseas)\.?$", re.I)

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

# A BARE PLURAL CLASS NOUN is just as aggregate as "our ten largest customers",
# and AGGREGATE_SUBJECT above cannot see it: that pattern requires a counting
# word first. Measured on Microchip, whose 10-Ks from 2003 to 2025 read
# "Distributors accounted for 60% of our net sales" -- a whole channel, not a
# counterparty. The preceding word was an all-caps section heading
# ("DISTRIBUTION"), which the name scan swallowed, producing the counterparty
# "DISTRIBUTION Distributors". The very next sentence names no one either:
# "Our largest distributor accounted for approximately 12% of our net sales."
#
# Anchored to the END of the subject span so it only fires when the class noun
# is what the claim is ABOUT. "Sales to Ingram Micro Inc. ... distributors ..."
# elsewhere in a sentence must not veto a real named counterparty.
BARE_CLASS_SUBJECT = re.compile(
    r"(?:^|[.;:]|\b)(?:our\s+|the\s+)?"
    r"(?:customer|client|distributor|reseller|dealer|wholesaler|"
    r"retailer|end.?user|oem|odm)s\s*$", re.I)

# TWO NAMES SHARING ONE PERCENTAGE. Measured on Qualcomm: "QCT and QTL segment
# revenues from Samsung Electronics and HTC comprised 26% of total
# consolidated revenues" -- 26% is the PAIR. The backward scan takes the
# nearest name and attributes the whole figure to HTC alone, which overstates
# a real relationship by an unknown amount.
#
# Anchored to the end, and both sides must look like NAMES: Intel's "Dell Inc.
# accounted for approximately 19% of our total sales, and Hewlett-Packard
# Company accounted for approximately 16%" must survive, because there the
# token before "and" is "sales," -- not a name.
JOINT_SUBJECT = re.compile(
    r"[A-Z][A-Za-z0-9.&'\-]*(?:\s+[A-Z][A-Za-z0-9.&'\-]*){0,4}"
    r"\s+and\s+"
    r"[A-Z][A-Za-z0-9.&'\-]*(?:\s+[A-Z][A-Za-z0-9.&'\-]*){0,4}"
    r"[,\s]*$")

# A GEOGRAPHIC claim that no list of place names would catch. GEOGRAPHIC_PARTY
# enumerates places and therefore can never be complete -- it did not contain
# "Singapore", and NVIDIA's fiscal-2025 10-K says "Singapore represented 18% of
# fiscal year 2025 total revenue based upon customer billing location", with
# the next sentence explaining the products ship elsewhere. These are
# STRUCTURAL markers of a geography table instead.
GEOGRAPHIC_CONSTRUCTION = re.compile(
    r"\b(?:billing location|bill.to location|customer location|"
    r"based upon (?:the )?location|based on (?:the )?location|"
    r"shipped elsewhere|by geographic|geographic area|"
    r"outside\s+(?:of\s+)?(?:the\s+)?(?:United States|U\.?S\.?A?\.?|"
    r"North America|Americas)|"
    # "Sales to customers in China, including Hong Kong, accounted for
    # approximately 28% of our net sales" -- Microchip, fiscal 2015. The name
    # scan lifts "Hong Kong" out of the apposition. The subject of the claim
    # is a PLACE, and the giveaway is the construction "customers in", not the
    # place name -- which is the whole reason GEOGRAPHIC_PARTY's list failed
    # on Singapore.
    r"(?:customers|clients)\s+(?:located\s+)?in)\b", re.I)

# The filer's OWN internals. "Revenue from sales of microprocessors WITHIN THE
# Mobility Group represented 26% of consolidated net revenue" -- Intel, 2006.
# Mobility Group is Intel's operating segment; the preceding sentence says so
# outright, but the claim's own sentence does not, so NON_CUSTOMER_SUBJECT
# (which is checked sentence-bounded, deliberately) cannot see it. Revenue
# earned "within" something is internal by construction.
INTERNAL_SUBJECT = re.compile(r"\bwithin\s+(?:the|our)\b", re.I)

# The filer's own named unit, identified by an APPOSITIVE rather than by the
# word "within". Genuine Parts, 2001-03-12: "The Automotive Parts Group, the
# largest DIVISION OF THE COMPANY, distributes automotive replacement parts",
# and 2002-03-07: "The Office Products Group, operated through S. P. Richards
# Company, a wholly-owned SUBSIDIARY OF THE COMPANY".
#
# Found 2026-08-28 when the anchor widening first made these sentences
# matchable. Left ungated they would have registered GPC as an anchor with its
# OWN Automotive Parts Group as the counterparty at 50% of consolidated
# revenue -- a fabricated member, and the one failure this source must not
# have.
#
# Matched as a CONSTRUCTION, not a list of unit names. A list of the filer's
# segments could never be complete across 51 companies and 30 years, which is
# the lesson GEOGRAPHIC_PARTY taught by lacking Singapore and Hong Kong.
# A party whose HEAD NOUN is a unit type is a business unit, not an entity.
# Genuine Parts, 2001-03-12: "sales from the Automotive Parts Group
# approximated 50% of the Company's net sales." There is no "of the Company"
# appositive in that sentence to catch -- the heading two sentences earlier
# reads "SEGMENT DATA." and nothing in the claim's own sentence says the Group
# is GPC's. Only the name's shape gives it away.
#
# Ungated this registered GPC as an anchor whose counterparty is GPC's own
# Automotive Parts Group at 50% of consolidated revenue -- five such segments
# across its filings, and a fabricated member.
#
# THE HEAD NOUN, not any occurrence: "Lenovo Group Limited" is a real Intel
# counterparty and its head is "Limited", so it is untouched. Measured over
# the full corpus, this rejects exactly the five GPC segments and no real
# counterparty. Under-inclusive by construction -- a real firm whose name ends
# in "Group" would be dropped -- which is the correct direction for a source
# that must never assert a relationship that does not exist.
UNIT_HEAD_PARTY = re.compile(
    r"\b(?:Group|Division|Segment|Unit|Operations)$", re.I)

OWN_BUSINESS_UNIT = re.compile(
    r"\b(?:division|segment|group|business\s+unit|subsidiary|affiliate)s?\s+"
    r"of\s+(?:the\s+(?:Company|Corporation|Registrant)|us|our\b)", re.I)

# An INDEFINITE ARTICLE immediately before the name means the phrase describes
# a category, not an entity. "Sales to Asustek Computer Inc., or Asustek, a
# CEM, accounted for 12% of our total revenue" -- NVIDIA, fiscal 2007: the
# real counterparty is Asustek, and "CEM" (contract electronics manufacturer)
# is what it IS. Checked immediately before the captured name, so "a single
# distributor, Ingram Micro Inc., accounted for..." is untouched -- there the
# article governs "distributor", not the name.
ARTICLE_BEFORE_NAME = re.compile(r"\b(?:a|an)\s+$", re.I)


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

# A PRIOR-PERIOD COMPARATIVE is not a statement about the filing's own year.
# Measured on Cognizant: the 10-K filed 2007-02-16 says "One customer,
# JPMorgan Chase, accounted for 13.7% of revenues in 2004" -- in the same
# breath as "No customer accounted for revenues in excess of 10% of total
# revenues in 2006 and 2005". Stamping that with the filing date would make
# Cognizant a registered anchor in 2007 on the strength of a 2004 fact the
# filing itself supersedes.
#
# One year of lag is NORMAL and must not be rejected: an annual report reports
# the year that just ended, so Intel's 10-K filed 2005-02-22 saying "In 2004,
# Dell Inc. accounted for approximately 19%" is current, not stale. Only a gap
# of two years or more is treated as a comparative.
# The "ended" branch was added 2026-08-28, and it is load-bearing rather than
# cosmetic. NIKE's 10-K of 2004-07-30 says, in the SAME filing that states
# 2004 and 2003 had no customer above 10%:
#
#     "During the year ended May 31, 2002, revenues derived from Foot Locker,
#      Inc. represented 11% of the Company's consolidated revenues."
#
# With only the in|for|during|of branch, that sentence yields NO stated year --
# "During" is followed by "the year ended May 31," and not by the year itself.
# The stale-comparative gate then cannot fire, and the disclosure is stamped
# with the 2004 FILING date. That would open an anchor-universe interval on
# precisely the filing that denies one.
#
# Found by measuring the 2026-08-28 anchor widening: the widening makes this
# sentence matchable for the first time, so the gap became reachable.
STATED_YEAR = re.compile(
    r"\b(?:"
    r"(?:in|for|during|of)\s+(?:fiscal\s+(?:year\s+)?)?"
    r"|(?:fiscal\s+)?(?:years?\s+)?ended\s+(?:[A-Z][a-z]+\.?\s+\d{1,2},\s*)?"
    r")(?P<year>(?:19|20)\d{2})\b",
    re.I)
STALE_COMPARATIVE_YEARS = 2

# Used when the submission's period of report is known. One year, not two: with
# the actual fiscal period in hand there is no filing-lag slack to absorb, so
# anything not naming the reported year is a comparative.
STALE_PERIOD_YEARS = 1

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
    # The DENOMINATOR the percentage was stated against. Recorded verbatim as
    # well as classified, so a reader can check the classification against the
    # filing's own words rather than trusting this module's vocabulary.
    concentration_basis: str = BASIS_UNKNOWN
    concentration_basis_text: str = ""

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
def first_document_of_submission(raw: str) -> str:
    """The 10-K itself, out of a concatenated full submission.

    A full submission text file is every document of the filing end to end:
    the 10-K, then every exhibit. Handing all of it to the extractor is NOT a
    neutral convenience. HYP04_Linkage_Map_v1.0.csv records that CVS appears
    in McKesson's FY2000 filing only inside an EXHIBIT -- a receivables
    facility defining "Special Obligor" as Rite Aid, Osco Drug, CVS Corp. and
    Wal-Mart -- and that it was rejected as a source for exactly that reason:
    it names no percentage and is not a customer-concentration disclosure.

    Feeding exhibits to the extractor would recreate that error across the
    whole frame, on filings nobody has read. So only the first document whose
    TYPE begins "10-K" is returned, falling back to the first document.
    """
    blocks = raw.split("<DOCUMENT>")[1:]
    if not blocks:
        return raw
    chosen = None
    for b in blocks:
        head = b[:400].upper()
        i = head.find("<TYPE>")
        if i == -1:
            continue
        kind = head[i + len("<TYPE>"):].splitlines()[0].strip()
        if kind.startswith("10-K"):
            chosen = b
            break
    if chosen is None:
        chosen = blocks[0]
    end = chosen.find("</DOCUMENT>")
    if end != -1:
        chosen = chosen[:end]
    start = chosen.find("<TEXT>")
    if start != -1:
        stop = chosen.find("</TEXT>")
        chosen = chosen[start + len("<TEXT>"):stop if stop != -1 else len(chosen)]
    return chosen


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


# ==========================================================================
# A LIST UNDER A STATED DENOMINATOR
# ==========================================================================
# Every anchor in CONCENTRATION_ANCHORS requires the percentage and the
# denominator to be ADJACENT -- "<pct>% of <basis>". Filings routinely state
# the denominator once and then list parties carrying bare percentages, in
# prose or as a table:
#
#   INTC 2018-02-16  "our three largest customers accounted for 40% of our net
#                     revenue, with Dell Inc. (Dell) accounting for 16% ..."
#   INTC 2024-01-26  "accounted for the following percentage of our net
#                     revenue: ... Dell Inc. 19 % 19 % 21 %"
#   ADBE 2011-01-27  "as a percentage of net revenue for fiscal 2010, 2009 and
#                     2008 ... 2010 2009 2008 Ingram Micro 15 % 15 % 18 %"
#
# Adjacency cannot be satisfied by any of them, so all three were invisible.
# The verb tense and the table layout are incidental; the structural fact is
# that the denominator is not repeated per party.
#
# The cost was already in the published registry. INTC's membership interval
# closed at 2017-02-17 -- not when the relationship ended, but when Intel
# moved the disclosure out of Item 1 prose into the segment note. ADBE never
# appeared at all. Both are availability deciding membership, which AU-1..AU-6
# forbid.

# The scope clause. Two shapes, and BOTH require a counterparty role word to
# come before the denominator, so a geography table headed "revenues by
# geography as a percentage of revenues, determined based on the addresses of
# our customers" is not a scope clause at all -- its role word trails.
SCOPED_LIST_HEADER = re.compile(
    # (a) "...customers ... percentage of <basis>"   -- the table form
    r"(?:customer|client|distributor|reseller)s?\b[^.:;]{0,200}?"
    r"percentages?\s+of\s+"
    r"(?P<basis>[\w\s'’]{0,40}?(?:revenues?|sales|receivables?))\b"
    r"|"
    # (b) "...customers accounted for N% of <basis>, with X ..., Y ..."
    # The aggregate figure here is the SCOPE, never taken as an edge; only
    # the per-party items beneath it are read.
    r"(?:customer|client|distributor|reseller)s?\b[^.:;]{0,80}?"
    r"(?:accounted\s+for|represented|comprised)\s+(?:approximately\s+)?"
    r"\d{1,3}(?:\.\d)?\s*%\s+of\s+"
    r"(?P<basis2>[\w\s'’]{0,40}?(?:revenues?|sales|receivables?))\b",
    re.I)

# One row: a name, then a short span, then its figures. The span is bounded so
# a name cannot reach across a neighbouring row to claim its percentage.
# THE COMMA IN "Apple, Inc." AGAIN. Jabil discloses Apple at 11-28% of net
# revenue in 26 filings; a name that stops at the comma records the bare
# suffix "Inc" as the counterparty -- the same defect that reduced NIKE's
# Foot Locker to "Inc", now in a second reader.
#
# "and" is NOT a name continuation here. Allowing it produced
# "Hewlett-Packard Company and Lucent Technologies" as one party sharing one
# percentage, which is what JOINT_SUBJECT exists to refuse.
SCOPED_LIST_ITEM = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9.&'’\-]*"
    r"(?:\s+(?:[A-Z][A-Za-z0-9.&'’\-]*|of|de|van|der))*"
    r"(?:,?\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?)?)"
    r"[^%.;:]{0,30}?"
    r"(?P<pcts>(?:(?:\d{1,3}(?:\.\d)?\s*%|\*|\u2014|\u2013)\s*){1,8})")

# A row that is entirely placeholders states nothing.
SCOPED_LIST_HAS_PCT = re.compile(r"\d{1,3}(?:\.\d)?\s*%")
# One cell: a figure, or the filer's "below the threshold" placeholder.
# Jabil writes "Cisco Systems, Inc 10 % 13 % 15 % * *" -- five columns, of
# which the last two are deliberately blank. Reading the "*" as a column
# rather than as noise is what keeps the row aligned with the year header;
# discarding rows whose width disagreed with the header dropped Cisco at
# 12% of consolidated net revenue from the fiscal-2004 filing while keeping
# Philips at 18% from the row above it.
SCOPED_LIST_CELL = re.compile(r"(\d{1,3}(?:\.\d)?)\s*%|(\*|\u2014|\u2013)")


def _scoped_list_cells(run: str) -> list[Optional[float]]:
    """One entry per column, None where the filer left the cell blank."""
    out: list[Optional[float]] = []
    for m in SCOPED_LIST_CELL.finditer(run):
        out.append(float(m.group(1)) if m.group(1) else None)
    return out

# A legal suffix standing alone is the wreckage of a mis-parsed name, never a
# counterparty.
BARE_SUFFIX_PARTY = re.compile(
    r"^(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?$",
    re.I)

# TABLE FURNITURE. Row and column labels are capitalised exactly like company
# names and sit in exactly the same place relative to the figures. UNNAMED_TOKENS
# already refuses the obvious ones; these are the ones a TABLE adds.
TABLE_FURNITURE_PARTY = re.compile(
    r"^(?:amounts?|accounts?|percentages?|totals?|net|gross|fiscal|years?|"
    r"ended|ending|approximately|other|various|balance|amount\s+due|"
    r"period|periods|quarter|quarters|as\s+of|for\s+the)\b", re.I)

# A METRIC-LABELLED BLOCK TABLE. Some filers head a block with the party and
# then label each row of figures by METRIC rather than by party:
#
#   STZ 2026-04-22   "Reyes Beer Division entities
#                     Net sales           27.5 %  25.4 %  25.1 %
#                     Accounts receivable 22.0 %  15.0 %  17.7 %
#                     Southern Glazer's Wine and Spirits
#                     Net sales           11.2 %  11.7 %  13.0 %"
#
# The nearest label to every figure is a metric, not a party, so a reader that
# pairs a figure with the capitalised token before it attributes net sales to
# "Accounts". This reader cannot attribute those rows and REFUSES the whole
# list rather than guess which block a figure belongs to.
#
# The cost is real and is recorded as under-inclusion, not hidden: STZ
# discloses Reyes Beer Division entities at 25-27% and Southern Glazer's Wine
# and Spirits at 11-13% of net sales, and this reader takes neither. Missing a
# real relationship is the safe direction; inventing one is not.
#
# THE REVENUE BLOCK COMES FIRST. Jabil shares ONE year row between a
# "Percentage of Net Revenue" block and a "Percentage of Accounts
# Receivable" block, so the reporting year appears twice in the header and
# the FIRST occurrence is the revenue column. That is only safe while the
# revenue label precedes the receivables label, so the order is checked
# rather than trusted: reversed, the reader refuses instead of reporting a
# receivables figure as a share of revenue.
REVENUE_BLOCK_LABEL = re.compile(
    r"percentage\s+of\s+(?:consolidated\s+|total\s+|net\s+){0,2}(?:net\s+)?(?:revenues?|sales)", re.I)
RECEIVABLE_BLOCK_LABEL = re.compile(
    r"percentage\s+of\s+(?:trade\s+)?(?:accounts\s+)?receivables?", re.I)

# The lookbehind matters: "Total percentage OF net revenue 40 %" is Intel's
# own total row, not a metric label heading a block, and refusing on it
# would throw away the very table this reader exists to read.
METRIC_LABELLED_BLOCK = re.compile(
    r"(?<!of )\b(?:net\s+(?:sales|revenues?)|accounts\s+receivable|"
    r"trade\s+receivables?)\s+\d{1,3}(?:\.\d)?\s*%", re.I)

SCOPED_LIST_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
SCOPED_LIST_PAREN = re.compile(r"\([^()]{0,80}\)")
SCOPED_LIST_SPAN_CHARS = 420
SCOPED_LIST_LABEL = "scoped_list"


def _scoped_list_edges(
    text: str, *, ticker: str, cik: str, filing_date: str, accession: str,
    form: str, report_date: Optional[str],
    already: set[tuple],
) -> list[LinkageEdge]:
    """Read lists governed by a scope clause that states the denominator once.

    Fails closed at every step where the filing is ambiguous. In particular it
    REFUSES rather than guesses when it cannot tell which column belongs to the
    reporting year, because column order is not a convention: INTC, ADBE and
    CTSH list years newest-first and GOOGL lists "2023 2024" oldest-first, all
    in this corpus. The multi-year "respectively" reader may assume newest-first
    within one sentence; a table may not.
    """
    out: list[LinkageEdge] = []
    for m in SCOPED_LIST_HEADER.finditer(text):
        basis_text = " ".join(
            (m.group("basis") or m.group("basis2") or "").split())
        basis = classify_concentration_basis(basis_text)

        # The scope clause must be ABOUT counterparties. A "segment revenue"
        # or geographic scope disqualifies every row beneath it at once.
        scope_start = max(0, m.start() - SENTENCE_SPAN_CHARS)
        sb = _last_sentence_break(text[scope_start:m.start()])
        scope_text = text[scope_start + (sb if sb != -1 else 0):m.end()]
        if NON_CUSTOMER_SUBJECT.search(scope_text):
            continue

        window = text[m.end():m.end() + SCOPED_LIST_SPAN_CHARS]
        # Refused outright: the figures in this window are labelled by metric,
        # so no pairing of a figure with a nearby name is trustworthy.
        if METRIC_LABELLED_BLOCK.search(window):
            continue
        # A parenthesised figure in this construction is a prior-year
        # comparative -- "accounting for 16% ( 15% in 2016 )". Removing them
        # before parsing is what turns the prose form into a clean list.
        window = SCOPED_LIST_PAREN.sub(" ", window)

        first = SCOPED_LIST_ITEM.search(window)
        if not first:
            continue
        ncols = len(_scoped_list_cells(first.group("pcts")))

        # Two blocks sharing one year row: only trustworthy while the
        # revenue block is the first of them.
        #
        # Read from the COLUMN HEADER, not from the scope sentence. Jabil's
        # scope clause ends "...expressed as a percentage of consolidated
        # net revenue, and the percentage of accounts receivable for each
        # customer, were as follows:" -- so the sentence introducing the
        # table mentions receivables before the table's own revenue label,
        # and a check reading the whole span refused every Jabil filing.
        head = window[:first.start()]
        hdr = head.rsplit(":", 1)[-1] if ":" in head else head
        rec = RECEIVABLE_BLOCK_LABEL.search(hdr)
        rev = REVENUE_BLOCK_LABEL.search(hdr)
        if rec and (not rev or rec.start() < rev.start()):
            continue

        # THE COLUMN HEADER. Take the last `ncols` years stated before the
        # first row -- ADBE states the years twice, once in the scope tail and
        # again as the header row, and it is the row that labels the columns.
        years = [int(y) for y in SCOPED_LIST_YEAR.findall(window[:first.start()])]
        header = years[-ncols:] if len(years) >= ncols else []

        period_year = None
        if report_date and len(report_date) >= 4 and report_date[:4].isdigit():
            period_year = int(report_date[:4])
        elif len(filing_date) >= 4 and filing_date[:4].isdigit():
            period_year = int(filing_date[:4])

        if ncols > 1:
            # Multiple columns and no readable header is exactly the case this
            # refuses. Guessing the order would attribute a prior year's
            # concentration to the reporting year -- the error the stale gate
            # exists to prevent, committed where that gate cannot see it.
            if len(header) != ncols or period_year is None:
                continue
            if period_year in header:
                col = header.index(period_year)
            elif period_year - 1 in header:
                # A filing whose period ends early in the calendar year labels
                # its own year one lower. ADBE's FY2010 ended 2010-12-03 and is
                # headed 2010; a January filer's is not.
                col = header.index(period_year - 1)
            else:
                continue
        else:
            col = 0
            # A SINGLE COLUMN MUST SIT IN THE SCOPE CLAUSE'S OWN SENTENCE.
            # A multi-column table announces itself with a year header and may
            # cross sentences; a one-figure list has nothing to announce it, so
            # letting it run on attaches the denominator to whatever follows.
            #
            # This guard was originally waived whenever any year appeared in
            # the window, which is nearly always -- and the corpus enumeration
            # showed what that cost: MCHP's "sales into China, including Hong
            # Kong" became a 30% counterparty, MCK's "accounts receivable from
            # our ten largest customers and Rite Aid Corporation were
            # approximately 49%" became Rite Aid at 49% OF REVENUE, and NVDA's
            # "There were no customers with 10% or more" became "There".
            fb = _first_sentence_break(window)
            if fb != -1:
                if first.start() > fb:
                    continue
                # Checking only the first row let a LATER sentence supply rows
                # under this scope clause's denominator. STZ 2009-04-29 states
                # its customer at 15.7% of sales and then, a sentence later,
                # the prior year at 12.3%; the 12.3% was taken as if current.
                window = window[:fb]

        for it in SCOPED_LIST_ITEM.finditer(window):
            if not SCOPED_LIST_HAS_PCT.search(it.group("pcts")):
                continue
            pcts = _scoped_list_cells(it.group("pcts"))
            if len(pcts) != ncols or col >= len(pcts):
                continue
            pct = pcts[col]
            # A blank cell is the filer saying this party was below the
            # threshold that year. It is information, and it is not an edge.
            if pct is None or not (0.0 < pct <= 100.0):
                continue

            # THE GATES NEED THE ROW'S NEIGHBOURHOOD, NOT THE ROW. STZ's
            # "of which 87.3% is reported within the Constellation Wines
            # segment and 12.7% is reported within the Constellation Spirits
            # segment" puts "within the" outside the matched row, so a gate
            # reading only the row cannot see that the party is a segment.
            # ...and it must not cross a sentence boundary to get it. Widening
            # to a flat 80/40 characters let the NEXT sentence veto a real row:
            # "and HP Inc. accounting for 11% . These three customers accounted
            # for 36% of our accounts receivable" -- the aggregate belongs to
            # the following sentence, and HP is a genuine 11% counterparty.
            lo = max(0, it.start() - 80)
            b = _last_sentence_break(window[lo:it.start()])
            lo += b if b != -1 else 0
            post = window[it.end():it.end() + 40]
            fb2 = _first_sentence_break(post)
            item_text = window[lo:it.end() + (fb2 if fb2 != -1 else len(post))]
            # THE AGGREGATE GATE BELONGS ON THE ROW, NOT THE SCOPE. "our three
            # largest customers" is the legitimate scope of a list that then
            # names its members; "Top ten clients 14.6 %" is a row that names
            # nobody. Applying it to the scope would reject the construction
            # this function exists to read.
            if AGGREGATE_SUBJECT.search(item_text) or AGGREGATE_TAIL.search(item_text):
                continue
            if OWN_BUSINESS_UNIT.search(item_text) or INTERNAL_SUBJECT.search(item_text):
                continue
            # The same structural gates the anchor pass applies. Each was left
            # out of the first draft of this reader and each produced a
            # fabrication in the 1,250-filing enumeration.
            if JOINT_SUBJECT.search(it.group("name") + " "):
                continue
            if GEOGRAPHIC_CONSTRUCTION.search(item_text):
                continue
            if BARE_CLASS_SUBJECT.search(it.group("name")):
                continue
            if NEGATIVE_PATTERN.search(item_text):
                continue
            # A name whose next word is a unit type is the filer's own unit,
            # however ordinary the name itself looks.
            if re.match(r"\s*(?:segment|division|business\s+unit)\b",
                        window[it.end("name"):it.end("name") + 20], re.I):
                continue

            party = clean_party(it.group("name"))
            if party is None:
                continue
            if GEOGRAPHIC_PARTY.match(party) or SELF_REFERENTIAL_PARTY.match(party):
                continue
            if BARE_SUFFIX_PARTY.match(party) or TABLE_FURNITURE_PARTY.match(party):
                continue
            if UNIT_HEAD_PARTY.search(party):
                continue
            # The scope clause supplies the counterparty context for every row,
            # so a bare name in a table is legitimate here -- but the name must
            # still look like an entity rather than a stray capitalised token.
            if not LEGAL_ENTITY_SUFFIX.search(party) \
                    and not _has_counterparty_context(item_text) \
                    and " " not in party:
                continue

            key = (party, pct, basis)
            if key in already:
                continue
            already.add(key)

            ctx = text[max(0, m.start()):
                       min(len(text), m.end() + SCOPED_LIST_SPAN_CHARS)].strip()
            out.append(LinkageEdge(
                reporting_company=ticker,
                reporting_cik=cik,
                named_counterparty=party,
                counterparty_is_named=True,
                direction=infer_direction(ctx),
                concentration_pct=pct,
                as_of_date=filing_date,
                accession=accession,
                form=form,
                pattern=SCOPED_LIST_LABEL,
                context=ctx[:400],
                concentration_basis=basis,
                concentration_basis_text=basis_text,
            ))
    return out


def extract_edges_from_text(
    text: str, *, ticker: str, cik: str, filing_date: str,
    accession: str, form: str = "10-K", report_date: Optional[str] = None,
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
            basis_text = " ".join((m.groupdict().get("basis") or "").split())
            basis = classify_concentration_basis(basis_text)
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
            # Added 2026-08-27 after the full-frame HISTORY walk. The gates
            # above were tuned against 2026 filings only; widening the corpus
            # to 1996-2026 surfaced four prose patterns they do not cover.
            if BARE_CLASS_SUBJECT.search(window):
                continue
            if JOINT_SUBJECT.search(window):
                continue
            if INTERNAL_SUBJECT.search(window):
                continue
            # Sentence-scoped: the appositive naming the unit as the filer's
            # own sits beside the name, not in the short lookback window.
            if OWN_BUSINESS_UNIT.search(sentence):
                continue
            if GEOGRAPHIC_CONSTRUCTION.search(sentence):
                continue
            # STALENESS IS MEASURED AGAINST THE PERIOD OF REPORT when the
            # submission supplies one, and against the FILING DATE otherwise.
            #
            # The two differ by about a year for any calendar-year filer -- a
            # FY2004 10-K filed 2005-02-22 -- so a window measured from the
            # filing date has to be two years wide just to avoid rejecting the
            # reporting year itself. That slack is what let NIKE's FY2002
            # comparative pass in a filing covering FY2003.
            #
            # Given the actual period, the rule is exact and the window
            # narrows to one: a figure is current if it names the year the
            # filing reports on, and is a comparative otherwise. Recorded as a
            # v1.6 limitation; closed here because the "respectively" form
            # above cannot be read correctly without it.
            years = [int(m.group("year")) for m in STATED_YEAR.finditer(sentence)]
            period_year = None
            if report_date and len(report_date) >= 4 and report_date[:4].isdigit():
                period_year = int(report_date[:4])
                stale_window = STALE_PERIOD_YEARS
            elif len(filing_date) >= 4 and filing_date[:4].isdigit():
                period_year = int(filing_date[:4])
                stale_window = STALE_COMPARATIVE_YEARS
            if years and period_year is not None \
                    and max(years) <= period_year - stale_window:
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
                    lead = window[:pm.start("party")]
                    if ARTICLE_BEFORE_NAME.search(lead):
                        # An appositive CATEGORY, not the counterparty -- but
                        # the counterparty is usually right in front of it:
                        # "Sales to Asustek Computer Inc., or Asustek, a CEM,
                        # accounted for 12%...". Dropping the category and
                        # taking nothing would lose a real, named relationship,
                        # so look once more at what the category describes.
                        trimmed = ARTICLE_BEFORE_NAME.sub("", lead).rstrip()
                        trimmed = trimmed.rstrip(",").rstrip()
                        pm2 = PARTY_TAIL.search(trimmed)
                        if pm2:
                            party = clean_party(pm2.group("party"))
                    elif INCLUDING_APPOSITIVE.search(lead):
                        # An instance of the measured category, not the
                        # counterparty. Take nothing rather than the instance.
                        party = None
                    else:
                        party = clean_party(pm.group("party"))

            # ATTRIBUTION GATES. Both added 2026-08-26 after the 51-ticker run
            # produced four false named edges -- two geographies and two of
            # the filer's own segments. Each would have asserted a
            # supply-chain relationship that does not exist, which is the one
            # failure this source must not have.
            if party is not None and GEOGRAPHIC_PARTY.match(party):
                party = None
            if party is not None and SELF_REFERENTIAL_PARTY.match(party):
                party = None
            if party is not None and UNIT_HEAD_PARTY.search(party):
                party = None

            # The topic window above is deliberately WIDE, so a role word in a
            # neighbouring footnote sentence still counts. That is right for
            # "Concentration of credit risk. ... Apple Inc. accounted for
            # 22% ...", and wrong for "...services to Intelligence Community
            # customers. National Security & Digital represented 44% of total
            # revenues.", where the role word leaks across a sentence boundary
            # onto a segment name.
            #
            # So a NAME is kept only if the SENTENCE itself establishes a
            # counterparty -- or the name carries a legal entity suffix, which
            # preserves the footnote case the wide window exists for.
            # Measured: MCK ("Sales to our largest customer, CVS Health
            # Corporation") and PKG ("our sales revenue to ODP represented
            # 58%") both pass; all four false positives fail.
            if (party is not None
                    and not _has_counterparty_context(sentence)
                    and not LEGAL_ENTITY_SUFFIX.search(party)):
                party = None

            start, end = max(0, m.start() - 200), min(len(text), m.end() + 200)
            ctx = text[start:end].strip()

            # The basis is part of the identity of a disclosure: "58% of the
            # Paper segment" and "58% of consolidated revenue" are different
            # claims and must not collapse into one edge.
            key = (party, pct, label, basis)
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
                concentration_basis=basis,
                concentration_basis_text=basis_text,
            ))

    # SECOND PASS: lists governed by a scope clause that states the
    # denominator once. Runs after the anchors so an item already taken
    # by an adjacency match is not recorded twice.
    taken = {(e.named_counterparty, e.concentration_pct, e.concentration_basis)
             for e in edges}
    edges.extend(_scoped_list_edges(
        text, ticker=ticker, cik=cik, filing_date=filing_date,
        accession=accession, form=form, report_date=report_date,
        already=taken))

    return edges, bool(NEGATIVE_PATTERN.search(text))


# ==========================================================================
# Live EDGAR client -- refuses to run without an owner-supplied contact
# ==========================================================================
class _CachedHTTPError(Exception):
    """A stored non-200, raised so a replay takes the SAME branch as the live
    run did. `filing_text_with_source` decides between the full-submission
    fallback and a hard failure on `status_code`, so a replayed 404 must carry
    one; without this the fallback would not fire offline and the walk would
    lose exactly the 2000-2001 filings the fallback exists to recover."""

    def __init__(self, status, url):
        super().__init__(f"cached HTTP {status} for {url}")
        self.response = type("_R", (), {"status_code": status})()



def _parallel_field(block: dict, name: str, i: int) -> Optional[str]:
    """One value out of SEC's parallel-array submissions block, or None.

    The arrays are index-aligned and SEC does not guarantee every one is
    present in every block -- the paginated older-filing files are thinner than
    `filings.recent`. Reading them positionally with [] turns a missing array
    into a KeyError and a short array into an IndexError, either of which would
    abort a whole ticker's walk over a field nothing is required to have.
    """
    arr = block.get(name)
    if not isinstance(arr, list) or i >= len(arr):
        return None
    v = arr[i]
    return v if v else None


class OfflineCacheMiss(RuntimeError):
    """An offline client was asked for something the cache does not hold.

    Deliberately fatal. The alternative -- quietly reaching the network from a
    run the caller asked to be offline -- is how a "no requests made" claim
    becomes false without anyone noticing.
    """


class FilingCache:
    """An on-disk cache of raw EDGAR responses, keyed by URL.

    WHY THIS EXISTS. Every change to the extractor has to be MEASURED against
    the whole corpus, because the 2026-08-27 walk established that widening
    the corpus raises the false-positive rate with no code change -- the gates
    did not regress, the corpus outgrew them. Without a cache each such
    measurement costs ~1,250 live SEC requests, which needs the repo owner's
    staged go-ahead, so in practice the measurement does not get done and the
    recorded limitations stay open. One authorized walk populates this; every
    later re-measurement is free and reaches no endpoint.

    IT STORES WHAT THE TRANSPORT RETURNED, not what the parser made of it --
    before strip_markup and before first_document_of_submission. Caching the
    cleaned text would freeze both of those, and they are exactly the code a
    re-measurement most needs to vary. The cost is disk; bodies are gzipped.

    NEGATIVE RESULTS ARE CACHED TOO. 10 of the 11 filings the full-frame walk
    could not retrieve were 2000-2001 filings returning 404, which is what
    drives the full-submission fallback. A cache that stored only successes
    would replay those as cache misses and take a different path offline than
    it took live, which would make an offline re-run quietly non-equivalent.

    Keyed by URL because that is the only key the SEC guarantees is stable:
    accession plus document is not sufficient (the same filing is reachable at
    two different URLs, and which one answered is the thing being recorded).
    """

    def __init__(self, root, *, readonly: bool = False) -> None:
        self.root = Path(root)
        self.readonly = readonly
        self.hits = 0
        self.misses = 0
        self.writes = 0

    def _path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.root / h[:2] / f"{h}.json.gz"

    def get(self, url: str, kind: str) -> Optional[dict]:
        """The stored entry, or None. A shape or version mismatch is a miss."""
        f = self._path(url)
        if not f.is_file():
            self.misses += 1
            return None
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError, EOFError):
            # A truncated or corrupt entry is a miss, never a crash and never
            # a partial body handed to the parser as though it were complete.
            #
            # EOFError is listed explicitly because it is the one that actually
            # happens: a gzip stream cut short -- an interrupted walk, a full
            # disk -- raises EOFError, not OSError, and the first draft of this
            # method crashed on precisely the corruption it was written to
            # tolerate. gzip.BadGzipFile does subclass OSError; EOFError does
            # not subclass anything useful here.
            self.misses += 1
            return None
        if rec.get("v") != CACHE_FORMAT_VERSION or rec.get("kind") != kind:
            self.misses += 1
            return None
        self.hits += 1
        return rec

    def put(self, url: str, kind: str, status: int, body) -> None:
        if self.readonly:
            return
        f = self._path(url)
        f.parent.mkdir(parents=True, exist_ok=True)
        rec = {"v": CACHE_FORMAT_VERSION, "url": url, "kind": kind,
               "status": status, "body": body,
               "stored_at_utc": datetime.now(timezone.utc)
               .strftime("%Y-%m-%dT%H:%M:%SZ")}
        # Write-then-rename, so an interrupted walk cannot leave a half-written
        # body that a later run would read as a complete filing.
        tmp = f.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(rec, fh)
        tmp.replace(f)
        self.writes += 1

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses,
                "writes": self.writes, "root": str(self.root)}


class EdgarClient:
    """Minimal SEC client. Verifies TLS. Paces requests. Caches per process."""

    def __init__(self, contact: Optional[str], *,
                 spacing: float = REQUEST_SPACING_SECONDS,
                 max_requests: Optional[int] = None,
                 cache: Optional["FilingCache"] = None,
                 offline: bool = False):
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
        # A cache is passed in, never discovered from the environment. A test
        # or a CI run that silently picked up a developer's cache directory
        # would stop being hermetic, and its "no network" claim would depend
        # on which machine it ran on.
        self.cache = cache
        self.offline = offline
        if offline and cache is None:
            raise ValueError(
                "offline=True requires a cache; there is nothing else to read "
                "from. Refusing rather than reaching the network.")

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

    def _cached(self, url: str, kind: str, timeout: int):
        """Serve `url` from the cache when possible, else fetch and store it.

        Sits ABOVE `_get`, which stays the transport seam the offline suites
        replace. A client with no cache is byte-for-byte the old path: this
        returns whatever `_get` returned, untouched.

        A cache hit is not a request and is not counted as one -- the walk's
        `requests_made` is a claim about what was asked of the SEC, and
        inflating it with reads from local disk would make that claim false in
        the direction that matters (it would overstate our load on a
        fair-access endpoint, and understate how much of a run was replayed).
        """
        if self.cache is not None:
            rec = self.cache.get(url, kind)
            if rec is not None:
                if rec.get("status") != 200:
                    raise _CachedHTTPError(rec.get("status"), url)
                return rec.get("body")
        if self.offline:
            raise OfflineCacheMiss(
                f"offline client has no cached entry for {url}. Populate the "
                "cache with an authorized walk before replaying it.")

        try:
            resp = self._get(url, timeout=timeout)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # Only a DEFINITIVE answer from the server is worth storing.
            #
            # Two things are not definitive. A timeout or connection reset
            # carries no status at all and says nothing about the filing. And a
            # status in TRANSIENT_STATUSES is the server declining to answer
            # right now -- this module already treats those as retryable, so
            # storing one would contradict that contract and turn a passing
            # 503 into a permanent failure for every future replay.
            #
            # Measured: the 2026-08-28 full-frame walk hit exactly two 503s
            # (ADP 1998-09-23, ERIE 2001-03-23), both of which had already
            # consumed their retry. Caching them would have made those filings
            # permanently unreachable from the cache while looking like a
            # settled fact about the corpus.
            if (status is not None
                    and status not in TRANSIENT_STATUSES
                    and self.cache is not None):
                self.cache.put(url, kind, status, None)
            raise
        body = resp.json() if kind == CACHE_KIND_JSON else resp.text
        if self.cache is not None:
            self.cache.put(url, kind, 200, body)
        return body

    def _get_json(self, url: str, timeout: int = 30):
        return self._cached(url, CACHE_KIND_JSON, timeout)

    def _get_text(self, url: str, timeout: int = 30) -> str:
        return self._cached(url, CACHE_KIND_TEXT, timeout)

    def cik_for(self, ticker: str) -> Optional[str]:
        if self._cik_map is None:
            data = self._get_json(TICKER_MAP_URL)
            self._cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                             for v in data.values()}
        return self._cik_map.get(ticker.upper())

    def latest_10k(self, cik: str) -> Optional[dict[str, str]]:
        data = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        rec = data["filings"]["recent"]
        for i, form in enumerate(rec["form"]):
            if form == "10-K":
                return {"accession": rec["accessionNumber"][i],
                        "filing_date": rec["filingDate"][i],
                        "report_date": _parallel_field(rec, "reportDate", i),
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
        data = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        filings = data.get("filings", {})
        blocks = [filings.get("recent", {})]

        for extra in filings.get("files", []) or []:
            name = extra.get("name")
            if not name:
                continue
            blocks.append(self._get_json(
                SUBMISSIONS_EXTRA_URL.format(name=name)))

        out: list[dict[str, str]] = []
        for blk in blocks:
            forms = blk.get("form") or []
            for i, form in enumerate(forms):
                if form != "10-K":
                    continue
                out.append({
                    "accession": blk["accessionNumber"][i],
                    "filing_date": blk["filingDate"][i],
                    # The PERIOD the filing covers, not the day it was filed.
                    # For a calendar-year filer these differ by about a year --
                    # a FY2004 10-K filed 2005-02-22 -- which is exactly the
                    # error in the stale-comparative gate, recorded as a
                    # limitation in registry v1.6. Captured now, read by
                    # nothing: using it would change what the extractor
                    # accepts, and that is a derivation change needing a
                    # re-walk and a new registry version. Capturing it early
                    # means that fix costs one walk instead of two.
                    "report_date": _parallel_field(blk, "reportDate", i),
                    "primary_document": blk["primaryDocument"][i],
                    "form": form,
                })
        # Newest first, so a caller can stop early and still know it has seen
        # every filing more recent than where it stopped.
        out.sort(key=lambda f: f["filing_date"], reverse=True)
        return out

    def filing_text_with_source(self, cik: str, accession: str,
                                document: str) -> tuple[str, str]:
        """A filing's text, and WHICH path it came from.

        Measured on the 2026-08-27 full-frame history walk: 10 of 11
        unretrievable filings were from 2000-2001 and returned 404. They
        predate the modern per-document layout, so the `primaryDocument` named
        in the submissions JSON does not exist at ARCHIVE_DOC_URL. Those are
        precisely the OLDEST filings -- the ones a history walk exists to
        reach -- so losing them biases the walk toward recent history.

        The eleventh was a 503, which is transient and worth one retry.

        The source is returned rather than hidden, because a full-submission
        extraction is not equivalent to a primary-document one and a reader
        must be able to tell them apart.
        """
        import requests

        url = ARCHIVE_DOC_URL.format(cik=int(cik), acc=accession.replace("-", ""),
                                     doc=document)
        status = None
        for attempt in (1, 2):
            try:
                return (strip_markup(self._get_text(url, timeout=60)),
                        SOURCE_PRIMARY_DOCUMENT)
            except (requests.HTTPError, _CachedHTTPError) as exc:
                status = getattr(exc.response, "status_code", None)
                if status in TRANSIENT_STATUSES and attempt == 1:
                    time.sleep(TRANSIENT_RETRY_SECONDS)
                    continue
                break
        if status != 404:
            raise RuntimeError(
                f"{accession}: primary document unavailable (HTTP {status})")
        raw = self._get_text(
            FULL_SUBMISSION_URL.format(cik=int(cik), acc=accession),
            timeout=120)
        return (strip_markup(first_document_of_submission(raw)),
                SOURCE_FULL_SUBMISSION)

    def filing_text(self, cik: str, accession: str, document: str) -> str:
        return self.filing_text_with_source(cik, accession, document)[0]


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
            "change the registry's required-external-measurement availability, "
            "whatever it currently records -- only a governed registry version "
            "does. It is a parallel candidate source."),
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
