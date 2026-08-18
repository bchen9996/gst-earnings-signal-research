#!/usr/bin/env python3
"""EDGAR material-agreement linkage extractor -- HYP-04, SOURCE B.

=== A SECOND, INDEPENDENT CANDIDATE SOURCE ===

This is deliberately NOT a variant of `edgar_linkage.py` (source A, ASC 280
concentration disclosures). Two sources that share a trigger, a form type, or
a parsing method would fail together and produce a correlated duplicate rather
than a cross-check. The independence is structural:

                    SOURCE A (edgar_linkage)     SOURCE B (this module)
  trigger           >=10% of revenue             a material agreement event
  form              10-K body text               8-K + EX-10.x exhibits
  method            parse one document           full-text search, then parse
  language          concentration percentages    agreement/contract verbs
  names a party?    rarely (ASC 280 exempts it)  usually (contracts name both)
  currency signal   none                         8-K Item 1.01 vs 1.02
  misses            sub-threshold relationships  relationships never filed as
                                                 material agreements

They also fail differently, which is the point: A's failure mode is matching
non-customer percentages (currency mix, geography); B's is matching
hypothetical, competitive, or already-terminated relationships. Neither
failure would be caught by the other method.

=== RELATIONSHIP CURRENCY, WHICH SOURCE A CANNOT DO AT ALL ===

A 10-K concentration disclosure is a snapshot; it says nothing about whether a
relationship persisted. This source can do better because EDGAR's own 8-K item
taxonomy encodes the lifecycle:

    Item 1.01  Entry into a Material Definitive Agreement    -> begins
    Item 1.02  Termination of a Material Definitive Agreement -> ends

So a relationship gets a status, not just a date. The honest limits of that
status are enforced in code, not just documented:

  * ACTIVE_AS_DISCLOSED  -- a 1.01 exists and no matching 1.02 was found.
                            This is NOT proof the relationship is current.
                            Agreements lapse, expire on their own terms, are
                            superseded, or are terminated without a separate
                            8-K. Absence of a termination filing is absence of
                            evidence, never evidence of absence.
  * TERMINATED_DISCLOSED -- a matching 1.02 was found. This IS positive
                            evidence, and such an edge must not be used as a
                            current linkage.
  * UNKNOWN              -- found outside the 1.01/1.02 taxonomy (e.g. a
                            7.01/8.01 press-release exhibit), so no lifecycle
                            signal exists at all.

=== FABRICATION RISK IS HIGHER HERE THAN IN SOURCE A ===

Source A matched a number next to a percent sign. This one matches prose about
business relationships, where the same words describe things that are not
relationships:

  * CONTINGENT  "if we were to enter into an agreement with X"
  * COMPETITIVE "we compete with X, Y and Z"  (risk factors name rivals
                constantly, and a rival is not a supply-chain partner)
  * TERMINATED  "the supply agreement with X was terminated effective..."

Negative tests for all three were written BEFORE the first live run, not
after. Source A needed three rounds of rediscovering false positives at
increasing scale; the cost of that lesson is meant to be paid once.

=== NOT MERGED WITH ANYTHING ===

Output is its own labelled candidate file. It feeds the existing
`edgar_linkage.reconcile()` path unchanged -- that function's merge logic is
deliberately NOT extended here, because there is still nothing to reconcile
against until the teammate's map exists.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .edgar_linkage import (
    CONTACT_REQUIRED_MESSAGE,
    EdgarContactError,
    _ABBREV,
    clean_party,
    strip_markup,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
REQUEST_SPACING_SECONDS = 0.15

# 8-K items that carry relationship lifecycle information.
ITEM_ENTRY = "1.01"          # Entry into a Material Definitive Agreement
ITEM_TERMINATION = "1.02"    # Termination of a Material Definitive Agreement
ITEM_REG_FD = "7.01"         # Regulation FD Disclosure
ITEM_OTHER = "8.01"          # Other Events
RELEVANT_ITEMS = (ITEM_ENTRY, ITEM_TERMINATION, ITEM_REG_FD, ITEM_OTHER)

# Search phrases. Chosen for the AGREEMENT EVENT, deliberately not overlapping
# source A's concentration vocabulary.
SEARCH_PHRASES: tuple[str, ...] = (
    '"supply agreement"',
    '"distribution agreement"',
    '"manufacturing agreement"',
    '"master services agreement"',
    '"strategic partnership"',
    '"purchase agreement"',
)

STATUS_ACTIVE = "ACTIVE_AS_DISCLOSED"
STATUS_TERMINATED = "TERMINATED_DISCLOSED"
STATUS_UNKNOWN = "UNKNOWN"


# ==========================================================================
# Relationship language
# ==========================================================================
# The counterparty follows an executed-agreement verb. Present/past tense
# only -- an executed agreement, not a contemplated one.
AGREEMENT_ANCHOR = re.compile(
    r"\b(?:entered into|executed|signed|amended|"
    # Termination verbs anchor too: a disclosed termination is real
    # information about a real relationship, and dropping it would lose the
    # one lifecycle signal this source has that source A lacks entirely.
    r"terminated|cancell?ed|did not renew|elected not to renew)\s+"
    r"(?:a|an|the|its|that certain)?\s*"
    r"(?P<kind>[A-Za-z][\w\s\-]{0,50}?)?\s*"
    r"(?:agreement|contract|arrangement)\s+"
    r"(?:with|between|among)\s+"
    # The party group is CASE-SENSITIVE via an inline scoped flag. Under the
    # surrounding re.I, [A-Z] also matches lowercase, so the pattern happily
    # captured sentence fragments -- "Company regarding the protection of" was
    # extracted as a counterparty from an employee-NDA clause. Same bug class
    # that produced "Concentration of credit risk. During fiscal 2025, Apple
    # Inc." in source A.
    r"(?-i:(?P<party>[A-Z][A-Za-z0-9.&'\-]*(?:\s+[A-Z][A-Za-z0-9.&'\-]*){0,5}"
    r"(?:\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|PLC|LLC|LP|NV|AG|SA)\.?)?))",
    re.I)

# NEGATIVE REPRESENTATIONS. Contract reps & warranties are full of statements
# that NO agreement exists -- "Neither the Company nor any of its Subsidiaries
# has entered into any agreement or arrangement with a Tax Authority". Read
# positively, these manufacture relationships out of their own denial.
NEGATIVE_REPRESENTATION = re.compile(
    r"\b(?:neither|nor|has\s+not|have\s+not|had\s+not|does\s+not|do\s+not|"
    r"did\s+not|is\s+not|are\s+not|no\s+(?:such\s+)?(?:agreement|contract|"
    r"arrangement)|without\s+(?:having\s+)?enter(?:ed|ing)?|"
    r"except\s+as\s+(?:set\s+forth|disclosed)|other\s+than)\b", re.I)

# GENERIC / NON-COMPANY counterparties. Legal boilerplate names categories of
# entity rather than businesses, and a category is not a supply-chain partner.
GENERIC_COUNTERPARTY = re.compile(
    r"^(?:the\s+)?(?:company|companies|subsidiary|subsidiaries|parent|"
    r"purchaser|seller|buyer|borrower|lender|guarantor|issuer|registrant|"
    r"tax\s+authority|governmental?\s+(?:entity|authority|body|agency)|"
    r"third\s+part(?:y|ies)|any\s+person|such\s+person|each\s+party|"
    r"the\s+parties|other\s+party|counterparty|employee|employees|"
    r"contractor|contractors|affiliate|affiliates|"
    r"trustee|agent|administrative\s+agent|escrow\s+agent|"
    r"underwriters?|placement\s+agents?|customers?|suppliers?|vendors?)\b",
    re.I)

# Contract-body boilerplate, as opposed to an announcement. EX-10.x exhibits
# ARE the contract, so their text is dense with definitional and hypothetical
# "agreement with" phrases. The 8-K BODY is where the relationship is
# announced; the exhibit is where it is papered.
CONTRACT_BOILERPLATE = re.compile(
    r"\b(?:trade\s+secrets?|confidential\s+information|non-disclosure|"
    r"representations?\s+and\s+warrant|covenants?\s+of\s+the|"
    r"schedule\s+\d|section\s+\d+\.\d|exhibit\s+[a-z0-9]|"
    r"as\s+defined\s+(?:herein|below|above)|for\s+purposes\s+of\s+this|"
    r"shall\s+mean|hereinafter|whereas)\b", re.I)

# CONTINGENT / HYPOTHETICAL. A relationship that might exist is not one.
#
# NOTE the negative lookahead on "may". Under re.I, a bare \bmay\b matches the
# MONTH: "On May 5, 2026, the Company amended its master services agreement
# with Umbrella Corp." was silently rejected as hypothetical. Filings are
# dated constantly, so this would have suppressed real edges in roughly a
# twelfth of them -- and silently, since a rejection produces no output to
# notice. The lookahead excludes "May <day>" and "May, <year>" date forms.
CONTINGENT = re.compile(
    r"\b(?:if|should|were\s+to|may(?!\s+\d|\s*,\s*\d)|might|could|would|"
    r"expects?\s+to|intends?\s+to|plans?\s+to|proposes?\s+to|anticipates?|"
    r"in\s+the\s+event|subject\s+to\s+(?:the\s+)?(?:execution|negotiation|"
    r"completion|closing)|no\s+assurance|there\s+can\s+be\s+no|"
    r"under\s+negotiation|non-binding|letter\s+of\s+intent|"
    r"term\s+sheet|contemplated|prospective|potential)\b", re.I)

# COMPETITIVE. Risk-factor sections name rivals constantly; a rival named as
# a competitor is not a supply-chain counterparty.
COMPETITIVE = re.compile(
    r"\b(?:compet(?:e|es|ing|ition|itor|itors|itive)|rival|rivals|"
    r"alternative\s+(?:providers?|suppliers?|vendors?)|"
    r"other\s+(?:participants?|players?)\s+in\s+the\s+(?:market|industry))\b",
    re.I)

# TERMINATED / EXPIRED. Positive evidence the relationship has ended.
TERMINATED = re.compile(
    r"\b(?:terminat(?:e|ed|es|ing|ion)|expir(?:e|ed|es|ation)|"
    r"wound?\s+down|discontinu(?:e|ed)|ceased|"
    r"no\s+longer\s+(?:a\s+)?(?:part(?:y|ies)|customer|supplier)|"
    r"mutually\s+agreed\s+to\s+end|rescind(?:ed)?|"
    r"notice\s+of\s+(?:non-renewal|termination))\b", re.I)

# Risk-factor / forward-looking sections, where relationship language is
# almost always hypothetical or competitive rather than transactional.
RISK_SECTION = re.compile(
    r"\b(?:risk\s+factors?|forward[\-\s]looking\s+statements?|"
    r"we\s+face\s+(?:significant\s+)?(?:risks?|competition)|"
    r"safe\s+harbou?r)\b", re.I)

SENTENCE_SPAN_CHARS = 400


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing [start, end), bounded by real sentence breaks."""
    pre = text[max(0, start - SENTENCE_SPAN_CHARS):start]
    sb = -1
    for i in range(len(pre) - 2, -1, -1):
        if pre[i] in ".;" and i + 1 < len(pre) and pre[i + 1] in " \t":
            if pre[i] == "." and _ABBREV.search(pre[:i + 1]):
                continue
            sb = i + 2
            break
    s0 = max(0, start - SENTENCE_SPAN_CHARS) + (sb if sb != -1 else 0)

    post = text[end:end + SENTENCE_SPAN_CHARS]
    fb = len(post)
    for i in range(len(post) - 1):
        if post[i] in ".;" and post[i + 1] in " \t":
            if post[i] == "." and _ABBREV.search(post[:i + 1]):
                continue
            fb = i + 1
            break
    return text[s0:end + fb]


@dataclass
class AgreementEdge:
    reporting_company: str
    reporting_cik: str
    counterparty: str
    agreement_kind: Optional[str]
    relationship_status: str
    as_of_date: str
    accession: str
    form: str
    item_numbers: list[str] = field(default_factory=list)
    file_type: Optional[str] = None
    source: str = "EDGAR_8K_MATERIAL_AGREEMENT"
    context: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgreementResult:
    edges: list[AgreementEdge] = field(default_factory=list)
    companies_attempted: list[str] = field(default_factory=list)
    companies_with_hits: list[str] = field(default_factory=list)
    companies_with_edges: list[str] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    requests_made: int = 0

    def coverage(self) -> dict[str, Any]:
        n = len(self.companies_attempted) or 1
        by_status: dict[str, int] = {}
        for e in self.edges:
            by_status[e.relationship_status] = by_status.get(e.relationship_status, 0) + 1
        return {
            "companies_attempted": len(self.companies_attempted),
            "companies_with_search_hits": len(self.companies_with_hits),
            "companies_with_extracted_edges": len(self.companies_with_edges),
            "pct_with_edges": round(100.0 * len(self.companies_with_edges) / n, 1),
            "total_edges": len(self.edges),
            "edges_by_relationship_status": by_status,
            "rejected_by_reason": dict(self.rejected),
            "errors": len(self.errors),
            "requests_made": self.requests_made,
        }


def extract_agreements_from_text(
    text: str, *, ticker: str, cik: str, filing_date: str, accession: str,
    form: str = "8-K", items: Optional[list[str]] = None,
    file_type: Optional[str] = None,
) -> tuple[list[AgreementEdge], dict[str, int]]:
    """Extract agreement edges from one filing. Pure function -- no I/O.

    Returns (edges, rejection_counts). Rejections are counted by reason so the
    filter's behaviour is measurable rather than invisible.
    """
    items = items or []
    edges: list[AgreementEdge] = []
    rejected: dict[str, int] = {}
    seen: set[tuple] = set()

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    # Item 1.02 marks the whole filing as a termination event.
    filing_is_termination = ITEM_TERMINATION in items

    for m in AGREEMENT_ANCHOR.finditer(text):
        sentence = _sentence_around(text, m.start(), m.end())

        if CONTINGENT.search(sentence):
            reject("contingent_or_hypothetical")
            continue
        if COMPETITIVE.search(sentence):
            reject("competitive_mention")
            continue
        if RISK_SECTION.search(sentence):
            reject("risk_factor_section")
            continue
        if NEGATIVE_REPRESENTATION.search(sentence):
            reject("negative_representation")
            continue
        if CONTRACT_BOILERPLATE.search(sentence):
            reject("contract_boilerplate")
            continue

        raw_party = (m.group("party") or "").strip()
        if GENERIC_COUNTERPARTY.match(raw_party):
            reject("generic_non_company_counterparty")
            continue
        party = clean_party(raw_party)
        if party is None:
            reject("unusable_counterparty_name")
            continue

        sentence_terminated = bool(TERMINATED.search(sentence))
        if filing_is_termination or sentence_terminated:
            status = STATUS_TERMINATED
        elif ITEM_ENTRY in items:
            status = STATUS_ACTIVE
        else:
            status = STATUS_UNKNOWN

        kind = (m.group("kind") or "").strip() or None
        if kind and len(kind) > 40:
            kind = None

        key = (party.lower(), status)
        if key in seen:
            continue
        seen.add(key)

        edges.append(AgreementEdge(
            reporting_company=ticker, reporting_cik=cik, counterparty=party,
            agreement_kind=kind, relationship_status=status,
            as_of_date=filing_date, accession=accession, form=form,
            item_numbers=list(items), file_type=file_type,
            context=sentence[:400],
        ))

    return edges, rejected


# ==========================================================================
# Live client
# ==========================================================================
class AgreementSearchClient:
    """efts.sec.gov full-text search + document fetch. Contact required."""

    def __init__(self, contact: Optional[str], *,
                 spacing: float = REQUEST_SPACING_SECONDS,
                 max_requests: Optional[int] = None):
        # Reuses source A's contact validation deliberately -- the SEC
        # fair-access rule is a property of the requester, not of the method.
        from .edgar_linkage import EdgarClient
        probe = EdgarClient(contact, max_requests=1)
        self.contact = probe.contact
        self._session = probe._session
        self.spacing = spacing
        self.max_requests = max_requests
        self.requests_made = 0
        self._cik_map: Optional[dict[str, str]] = None

    # efts.sec.gov intermittently returns 500 on otherwise-valid queries --
    # observed on 2 of 30 canary searches. Retried with backoff rather than
    # treated as "this company has no agreements", which would silently
    # understate coverage. Retries count against the cap like any other
    # request, so a flapping endpoint cannot quietly blow the budget.
    RETRY_STATUSES = frozenset({500, 502, 503, 504})
    MAX_ATTEMPTS = 3

    def _get(self, url: str, params: Optional[dict] = None, timeout: int = 40):
        last_exc = None
        for attempt in range(self.MAX_ATTEMPTS):
            if self.max_requests is not None and self.requests_made >= self.max_requests:
                raise RuntimeError(
                    f"EDGAR request cap of {self.max_requests} reached; stopping "
                    "rather than continuing. No silent truncation.")
            if self.requests_made:
                time.sleep(self.spacing * (1 + attempt * 3))
            self.requests_made += 1
            r = self._session.get(url, params=params, timeout=timeout)
            if r.status_code in self.RETRY_STATUSES and attempt < self.MAX_ATTEMPTS - 1:
                last_exc = r
                continue
            r.raise_for_status()
            return r
        if last_exc is not None:
            last_exc.raise_for_status()
        raise RuntimeError("unreachable")

    def cik_for(self, ticker: str) -> Optional[str]:
        if self._cik_map is None:
            data = self._get("https://www.sec.gov/files/company_tickers.json").json()
            self._cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                             for v in data.values()}
        return self._cik_map.get(ticker.upper())

    def search(self, cik: str, phrase: str, forms: str = "8-K") -> list[dict]:
        """Search hits with `_id` PRESERVED.

        `_id` lives on the hit, not inside `_source`, and carries the document
        filename as "<accession>:<file>". Returning bare `_source` dropped it,
        so every document fetch resolved to None and the canary extracted zero
        edges while reporting search hits -- a silent no-op, not an error.
        """
        d = self._get(FULL_TEXT_SEARCH_URL,
                      params={"q": phrase, "ciks": cik, "forms": forms}).json()
        out = []
        for h in d.get("hits", {}).get("hits", []):
            src = dict(h.get("_source") or {})
            src["_id"] = h.get("_id")
            out.append(src)
        return out

    def document(self, cik: str, accession: str, doc: str) -> str:
        url = ARCHIVE_DOC_URL.format(cik=int(cik), acc=accession.replace("-", ""),
                                     doc=doc)
        return strip_markup(self._get(url, timeout=60).text)


def extract_for_universe(
    tickers: Iterable[str], *, contact: Optional[str],
    max_requests: Optional[int] = None,
    phrases: tuple[str, ...] = SEARCH_PHRASES,
    max_docs_per_ticker: int = 3,
) -> AgreementResult:
    """MAKES REAL SEC REQUESTS. Bounded by max_requests."""
    client = AgreementSearchClient(contact, max_requests=max_requests)
    res = AgreementResult()

    for t in tickers:
        res.companies_attempted.append(t)
        try:
            cik = client.cik_for(t)
            if cik is None:
                res.errors[t] = "no CIK for ticker"
                continue

            hits: dict[str, dict] = {}
            for phrase in phrases:
                for h in client.search(cik, phrase):
                    items = h.get("items") or []
                    if not any(i in RELEVANT_ITEMS for i in items):
                        continue
                    hits[h["adsh"]] = h
            if hits:
                res.companies_with_hits.append(t)

            ordered = sorted(hits.values(), key=lambda s: s.get("file_date", ""),
                             reverse=True)[:max_docs_per_ticker]
            for src in ordered:
                doc_id = src.get("_id") or ""
                doc_name = doc_id.split(":")[-1] if ":" in doc_id else None
                if not doc_name:
                    continue
                try:
                    text = client.document(cik, src["adsh"], doc_name)
                except Exception as e:                     # noqa: BLE001
                    res.errors[f"{t}:{src['adsh']}"] = f"{type(e).__name__}: {str(e)[:100]}"
                    continue
                edges, rej = extract_agreements_from_text(
                    text, ticker=t, cik=cik, filing_date=src.get("file_date", ""),
                    accession=src["adsh"], form=src.get("form", "8-K"),
                    items=src.get("items") or [], file_type=src.get("file_type"))
                for k, v in rej.items():
                    res.rejected[k] = res.rejected.get(k, 0) + v
                if edges:
                    if t not in res.companies_with_edges:
                        res.companies_with_edges.append(t)
                    res.edges.extend(edges)
        except Exception as e:                             # noqa: BLE001
            res.errors[t] = f"{type(e).__name__}: {str(e)[:160]}"

    res.requests_made = client.requests_made
    return res


def write_report(res: AgreementResult, path: Path) -> None:
    from .edgar_linkage import reconcile

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "artifact": "HYP-04 EDGAR material-agreement CANDIDATE linkage (SOURCE B)",
        "source": "SEC EDGAR full-text search over 8-K material-agreement items",
        "is_production_linkage_map": False,
        "status": "CANDIDATE_SOURCE_FOR_RECONCILIATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "independent_of": (
            "HYP04_EDGAR_CANDIDATE_LINKAGE_FULL (source A, ASC 280 "
            "concentration). Different trigger, form, method, vocabulary and "
            "failure modes, so the two can serve as a genuine cross-check "
            "rather than a correlated duplicate."),
        "relationship_currency": {
            "ACTIVE_AS_DISCLOSED": (
                "An Item 1.01 entry exists and no matching Item 1.02 "
                "termination was found. This is NOT proof the relationship is "
                "current -- agreements expire on their own terms, are "
                "superseded, or end without a separate 8-K. Absence of a "
                "termination filing is absence of evidence."),
            "TERMINATED_DISCLOSED": (
                "A termination was disclosed. Positive evidence the "
                "relationship ended; must not be used as a current linkage."),
            "UNKNOWN": (
                "Found outside the 1.01/1.02 taxonomy, so no lifecycle signal "
                "exists at all."),
        },
        "coverage": res.coverage(),
        "edges": [e.as_dict() for e in res.edges],
        "errors": res.errors,
        "reconciliation": reconcile([], None),
        "reconciliation_note": (
            "Routed through the existing reconcile() path unchanged. Its merge "
            "logic is deliberately NOT extended: there is nothing to reconcile "
            "against until the teammate's map exists."),
    }, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="EDGAR material-agreement extractor (MAKES REAL SEC REQUESTS).")
    ap.add_argument("--contact", default=None)
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--out", type=Path,
                    default=LSE / "HYP04_EDGAR_AGREEMENT_LINKAGE.json")
    a = ap.parse_args(argv)

    if not a.contact:
        print(CONTACT_REQUIRED_MESSAGE, file=sys.stderr)
        return 2

    from .run_canary_audit import candidate_peer_universe
    tickers = ([t.strip().upper() for t in a.tickers.split(",")] if a.tickers
               else candidate_peer_universe())

    res = extract_for_universe(tickers, contact=a.contact,
                               max_requests=a.max_requests)
    for k, v in res.coverage().items():
        print(f"  {k:36s} {v}")
    write_report(res, a.out)
    print(f"\nWrote: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
