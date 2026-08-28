#!/usr/bin/env python3
"""EDGAR candidate-linkage extractor tests -- HYP-04.

FULLY OFFLINE. Sockets are blocked before the module is imported, so a test
that accidentally reaches SEC fails loudly instead of silently making real
requests. Extraction is a pure function over text, which is what makes this
testable without a network at all.

The extraction fixtures are hand-written to mirror real ASC 280 disclosure
language, including the cases that matter most:

  * a NAMED counterparty with a stated percentage       -> a usable edge
  * an UNNAMED "Customer A" disclosure                  -> recorded, NOT an edge
  * an explicit "no customer exceeded 10%" statement    -> information, not absence
  * supplier-direction language                         -> direction inferred
  * near-miss text that must NOT match                  -> no fabricated edge

That last category is the one worth caring about. A missing edge is a known,
documented limitation of this source. A FABRICATED edge is a false finding
that would propagate into a linkage map and then into a hypothesis test.

Run directly: python test_hyp04_supply_chain_hedge_edgar.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline EDGAR test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.edgar_linkage import (  # noqa: E402
    BASIS_CONSOLIDATED_REVENUE,
    BASIS_DEFERRED_REVENUE,
    BASIS_RECEIVABLES,
    BASIS_SEGMENT_REVENUE,
    BASIS_UNKNOWN,
    CONCENTRATION_BASES,
    CONTACT_REQUIRED_MESSAGE,
    DIRECTION_CUSTOMER,
    DIRECTION_SUPPLIER,
    EdgarClient,
    EdgarContactError,
    ExtractionResult,
    LinkageEdge,
    classify_concentration_basis,
    clean_party,
    extract_edges_from_text,
    infer_direction,
    reconcile,
    strip_markup,
)

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


def _extract(text: str):
    return extract_edges_from_text(
        text, ticker="TEST", cik="0000000001", filing_date="2026-02-14",
        accession="0000000001-26-000001")


# ===================== 1. contact is mandatory ============================
def test_1_client_refuses_without_a_real_contact() -> None:
    """SEC fair-access: www.sec.gov 403s without an email-shaped UA."""
    for bad, why in (
        (None, "None"),
        ("", "empty"),
        ("Quant Research Project", "no @ at all"),
        ("Research Project contact@", "trailing @, no domain"),
    ):
        try:
            EdgarClient(bad)
            check(f"1a. refuses a contact that is {why}", False, "it constructed")
        except EdgarContactError:
            check(f"1a. refuses a contact that is {why}", True)

    # RFC 2606 reserved domains are unreachable -- the repo's existing module
    # uses research@example.com, which is exactly this case.
    for placeholder in ("GST Research research@example.com",
                        "X a@test.invalid", "Y b@localhost.localdomain"):
        try:
            EdgarClient(placeholder)
            check(f"1b. rejects reserved placeholder domain in {placeholder!r}",
                  False, "it constructed")
        except EdgarContactError:
            check(f"1b. rejects reserved placeholder domain in {placeholder!r}", True)

    # Measured against the live host: www.sec.gov 403s a no-reply domain and
    # 200s the same User-Agent with a deliverable address.
    for noreply in ("Quant Research bchen@users.noreply.github.com",
                    "Quant Research noreply@somedomain.com",
                    "Quant Research x@no-reply.example.org"):
        try:
            EdgarClient(noreply)
            check(f"1b2. rejects the no-reply address in {noreply!r}", False,
                  "it constructed; SEC would 403 this mid-run")
        except EdgarContactError:
            check(f"1b2. rejects the no-reply address in {noreply!r}", True)

    check("1c. the refusal explains WHY an implementer may not invent one",
          "not a value an implementer may invent" in CONTACT_REQUIRED_MESSAGE)
    check("1d. and names the host that enforces it",
          "www.sec.gov" in CONTACT_REQUIRED_MESSAGE)

    # A well-formed, deliverable contact must be ACCEPTED -- otherwise the
    # validation above could be satisfied by rejecting everything.
    try:
        c = EdgarClient("Quant Research Project analyst@somerealdomain.com")
        check("1e. CONTROL -- a deliverable contact is accepted", True)
        check("1f. and TLS verification is left ON",
              c._session.verify is True,
              "the pre-existing edgar_8k_signal module disables it")
    except EdgarContactError:
        check("1e. CONTROL -- a deliverable contact is accepted", False,
              "validation rejects everything, so it proves nothing")


# ===================== 2. named-counterparty extraction ===================
def test_2_named_counterparty_with_percentage() -> None:
    text = ("Concentration of credit risk. During fiscal 2025, Apple Inc. "
            "accounted for approximately 22% of net revenues. No other "
            "customer represented a material portion of sales.")
    edges, no_conc = _extract(text)
    named = [e for e in edges if e.counterparty_is_named]
    check("2a. a named counterparty produces an edge", len(named) >= 1)
    if named:
        e = named[0]
        check("2b. the counterparty name is captured",
              "Apple" in (e.named_counterparty or ""), repr(e.named_counterparty))
        check("2c. the concentration percentage is captured",
              e.concentration_pct == 22.0, str(e.concentration_pct))
        check("2d. direction defaults to customer", e.direction == DIRECTION_CUSTOMER)
        check("2e. the as-of date is the FILING date (Patch 11)",
              e.as_of_date == "2026-02-14")
        check("2f. the accession is recorded for provenance",
              e.accession.startswith("0000000001-"))
        check("2g. surrounding context is retained for human review",
              "accounted for" in e.context.lower())


def test_3_sales_to_phrasing() -> None:
    text = ("Sales to Dell Technologies Inc. represented approximately 13% of "
            "total revenues in fiscal 2025.")
    edges, _ = _extract(text)
    named = [e for e in edges if e.counterparty_is_named]
    check("3a. 'sales to X represented Y%' is matched", len(named) >= 1)
    if named:
        check("3b. the counterparty is captured",
              "Dell" in (named[0].named_counterparty or ""))
        check("3c. the percentage is captured", named[0].concentration_pct == 13.0)


# ===================== 4. unnamed disclosures ============================
def test_4_unnamed_customer_is_not_an_edge() -> None:
    """'Customer A accounted for 18%' is compliant, complete, and useless."""
    text = ("Customer A accounted for approximately 18% of net revenues, and "
            "Customer B accounted for 11% of net revenues.")
    edges, _ = _extract(text)
    named = [e for e in edges if e.counterparty_is_named]
    check("4a. an unnamed 'Customer A' yields NO named edge", not named,
          f"got {[e.named_counterparty for e in named]}")
    check("4b. but the disclosure is still recorded as an unnamed edge",
          any(not e.counterparty_is_named for e in edges))
    check("4c. the percentage is still captured on the unnamed edge",
          any(e.concentration_pct in (18.0, 11.0) for e in edges))

    for token in ("one customer", "a single customer", "our largest customer",
                  "The Company", "no customer"):
        check(f"4d. clean_party rejects the placeholder {token!r}",
              clean_party(token) is None)


def test_5_explicit_no_concentration_is_information() -> None:
    """'We checked and nothing exceeded 10%' differs from 'we found nothing'."""
    text = ("No single customer accounted for more than 10% of net revenues "
            "during any period presented.")
    edges, no_conc = _extract(text)
    check("5a. an explicit no-concentration statement is detected", no_conc is True)
    check("5b. and it produces no named edge",
          not [e for e in edges if e.counterparty_is_named])

    _, no_conc2 = _extract("The Company designs and sells semiconductors.")
    check("5c. ordinary prose is NOT read as a no-concentration statement",
          no_conc2 is False)


# ===================== 6. must not fabricate =============================
def test_6_near_miss_text_produces_no_edge() -> None:
    """A fabricated edge is far worse than a missed one."""
    negatives = {
        "percentage with no party": "Revenues increased approximately 12% of prior year.",
        "party with no percentage": "We sell to Apple Inc. under a master agreement.",
        "unrelated percentage": "Gross margin accounted for 45% of the change in operating income.",
        "prose only": "Item 1. Business. We design and manufacture industrial components.",
        "impossible concentration": "Customer accounted for 480% of net revenues.",
    }
    for label, text in negatives.items():
        edges, _ = _extract(text)
        named = [e for e in edges if e.counterparty_is_named]
        check(f"6a. no named edge fabricated from: {label}", not named,
              f"got {[(e.named_counterparty, e.concentration_pct) for e in named]}")

    edges, _ = _extract("Customer accounted for 480% of net revenues.")
    check("6b. an out-of-range concentration is rejected outright",
          not any((e.concentration_pct or 0) > 100 for e in edges))


def test_6b_aggregate_disclosures_are_not_edges() -> None:
    """VERBATIM text from the 2026-08-18 live canary.

    An aggregate concentration spans MANY counterparties and is a portfolio
    statistic, not a relationship with anyone. The first canary run emitted
    three false edges from these exact passages -- including the ALLE one,
    whose very next sentence states no single customer reached 10%.

    Dropped entirely rather than recorded as unnamed edges: an unnamed edge
    still asserts ONE relationship of that size exists, which an aggregate
    does not.
    """
    aggregates = {
        "ALLE 10 largest": (
            "Our 10 largest customers represented approximately 26% of our total "
            "Net revenues in 2025. No single customer represented 10% or more of "
            "our total Net revenues in 2025."),
        "JBL five largest": (
            "In fiscal year 2025, our five largest customers accounted for "
            "approximately 36% of our net revenue and 87 customers accounted for "
            "approximately 90% of our net revenue."),
        "top 10": "Our top 10 customers accounted for 45% of revenues.",
        "several": "Several customers accounted for 30% of net sales.",
        "combined": "These combined customers accounted for 55% of total revenue.",
    }
    for label, text in aggregates.items():
        edges, _ = _extract(text)
        check(f"6b. no edge from the aggregate disclosure: {label}", not edges,
              f"got {[(e.named_counterparty, e.concentration_pct) for e in edges]}")

    # CONTROL: a genuine SINGLE-counterparty disclosure must still produce an
    # unnamed edge, or the aggregate filter has simply suppressed everything.
    single = ("A second major customer accounted for 12% of consolidated revenue "
              "during fiscal 2026.")
    edges, _ = _extract(single)
    check("6b2. CONTROL -- a single unnamed customer still yields an edge",
          len(edges) == 1 and not edges[0].counterparty_is_named,
          f"got {len(edges)} edge(s)")
    check("6b3. and its percentage is captured",
          bool(edges) and edges[0].concentration_pct == 12.0)

    nvda = ("For fiscal year 2026, sales to one direct customer represented 22% "
            "of total revenue and sales to another direct customer represented "
            "14% of total revenue.")
    edges, _ = _extract(nvda)
    check("6b4. CONTROL -- 'one direct customer' / 'another direct customer' "
          "yield unnamed edges", len(edges) == 2
          and not any(e.counterparty_is_named for e in edges),
          f"got {len(edges)}")


def test_6c_non_customer_percentages_are_rejected() -> None:
    """VERBATIM false positives from the 2026-08-18 full-universe run.

    Every one is a real "X% of revenue" sentence that has nothing to do with
    a counterparty. The 5-ticker canary was too small to surface any of them;
    the 27-ticker run produced six. Sub-threshold values were the tell --
    ASC 280 only requires disclosure at ~10% or more, so a 1.3% or 4%
    "concentration" cannot be one.
    """
    false_positives = {
        "NFLX currency mix": (
            "Currencies denominated in other than the U.S. dollar accounted "
            "for 56% of revenue and 31% of operating expenses for the year "
            "ended December 31, 2025."),
        "ALB geography": (
            "In 2025, net sales shipped to or within China represented 39% of "
            "our total net sales."),
        "CCL product mix": (
            "Consolidated Passenger ticket revenues made up 65% of our 2025 "
            "total revenues."),
        "AVB segment mix": (
            "Gross rental revenue provided by leased commercial space in our "
            "portfolio represented 1.3% of our total revenue in 2025."),
        "MCK foreign ops": (
            "Our foreign operations represented approximately 4% of our "
            "consolidated revenues in each of fiscal 2026 and fiscal 2025."),
        "ROP functional currency": (
            "Sales by our operating companies whose functional currency is not "
            "the U.S. dollar represented 9% of our total net revenues."),
    }
    for label, text in false_positives.items():
        edges, _ = _extract(text)
        check(f"6c. no edge from the non-customer statistic: {label}", not edges,
              f"got {[(e.named_counterparty, e.concentration_pct) for e in edges]}")

    # 'China' must never be recorded as a counterparty -- it is a country.
    edges, _ = _extract(false_positives["ALB geography"])
    check("6c2. a country is never recorded as a named counterparty",
          not any((e.named_counterparty or "") == "China" for e in edges))


def test_6d_appositive_names_are_captured() -> None:
    """VERBATIM from MCK's 2026 10-K. CVS was in the text and read as UNNAMED.

    The name follows the role phrase rather than preceding it, so a purely
    backward-looking scan matched 'our largest customer' as an unnamed
    disclosure and discarded the name sitting right beside it.
    """
    text = ('Sales to our largest customer, CVS Health Corporation ("CVS"), '
            "accounted for approximately 24% of our total consolidated "
            "revenues in fiscal 2026.")
    edges, _ = _extract(text)
    named = [e for e in edges if e.counterparty_is_named]
    check("6d. the appositive counterparty is captured", bool(named),
          f"got {[(e.named_counterparty, e.concentration_pct) for e in edges]}")
    if named:
        check("6d2. and it is CVS, not the role phrase",
              "CVS" in (named[0].named_counterparty or ""),
              repr(named[0].named_counterparty))
        check("6d3. with the right percentage", named[0].concentration_pct == 24.0)

    # The aggregate in the SAME filing must still be rejected, including its
    # parenthetical aside, which previously broke the tail match.
    agg = ("During fiscal 2026, sales to our ten largest customers, including "
           'group purchasing organizations ("GPOs") accounted for '
           "approximately 73% of our total consolidated revenues.")
    edges2, _ = _extract(agg)
    check("6d4. the parenthetical-laden aggregate is still rejected", not edges2,
          f"got {[(e.named_counterparty, e.concentration_pct) for e in edges2]}")

    # The hardest real case, verbatim from MCK: an aggregate sentence with a
    # TRAILING clause, immediately followed by a genuine named disclosure.
    # The trailing 43% belongs to the ten largest customers, and CVS begins
    # the NEXT sentence -- attributing 43% to CVS was a bug introduced by the
    # appositive fix reaching forward across the boundary.
    both = ("Sales to our ten largest customers, including group purchasing "
            'organizations ("GPOs"), accounted for approximately 73% of total '
            "consolidated revenues in fiscal 2026 and comprised approximately "
            "43% of total trade accounts receivable at March 31, 2026. Sales "
            'to our largest customer, CVS Health Corporation ("CVS"), '
            "accounted for approximately 24% of our total consolidated revenues.")
    edges3, _ = _extract(both)
    pcts = sorted(e.concentration_pct for e in edges3)
    check("6d5. the aggregate's 73% is rejected", 73.0 not in pcts, str(pcts))
    check("6d6. the aggregate's TRAILING 43% clause is also rejected",
          43.0 not in pcts, f"{pcts} -- 43% belongs to the ten largest, not to CVS")
    check("6d7. only the genuine single-customer 24% survives", pcts == [24.0],
          str(pcts))
    named3 = [e for e in edges3 if e.counterparty_is_named]
    check("6d8. and it is attributed to CVS",
          len(named3) == 1 and "CVS" in (named3[0].named_counterparty or ""),
          str([(e.named_counterparty, e.concentration_pct) for e in edges3]))


def test_7_direction_inference() -> None:
    check("7a. supplier language infers supplier direction",
          infer_direction("our primary contract manufacturer and supplier of wafers")
          == DIRECTION_SUPPLIER)
    check("7b. plain revenue-concentration language infers customer",
          infer_direction("accounted for 20% of net revenues") == DIRECTION_CUSTOMER)

    text = ("Purchases from Taiwan Semiconductor Manufacturing Company accounted "
            "for approximately 30% of total sales of the segment, and this "
            "supplier remains our principal foundry.")
    edges, _ = _extract(text)
    sup = [e for e in edges if e.direction == DIRECTION_SUPPLIER]
    check("7c. a supplier-context disclosure is directed as supplier", bool(sup))


# ===================== 8. markup handling ================================
def test_8_strip_markup() -> None:
    """Markup normalisation only.

    The fixture carries explicit counterparty role language because that is
    what a real ASC 280 disclosure looks like. An earlier version used a bare
    "Apple Inc. accounted for 22% of net revenues", which the extractor now
    correctly REJECTS: a named entity plus a percentage, with no role framing
    and no directed-trade construction, is genuinely ambiguous, and after the
    2026-08-18 false-positive findings the conservative reading is the right
    one. That made this test silently depend on the context rule rather than
    on the markup handling it claims to exercise.
    """
    raw = ("<html><head><style>.x{color:red}</style></head><body>"
           "<p>Sales to our largest customer, Apple&nbsp;Inc., accounted for "
           "<b>22%</b> of net&nbsp;revenues.</p>"
           "<script>var x=1;</script></body></html>")
    txt = strip_markup(raw)
    check("8a. tags are removed", "<p>" not in txt and "<b>" not in txt)
    check("8b. script and style contents are removed",
          "var x" not in txt and "color:red" not in txt)
    check("8c. entities are unescaped and nbsp normalised", "Apple Inc." in txt)
    check("8d. the disclosure survives normalisation and still extracts",
          bool([e for e in _extract(txt)[0] if e.counterparty_is_named]))

    # And the conservative rejection is itself asserted, so it cannot regress
    # into over-matching without a test noticing.
    bare = "Apple Inc. accounted for 22% of net revenues."
    check("8e. a bare entity with NO role language is rejected as ambiguous",
          not _extract(bare)[0],
          "after the false-positive findings, ambiguity resolves to no-edge")


# ===================== 9. coverage reporting =============================
def test_9_coverage_is_reported_as_a_floor() -> None:
    res = ExtractionResult()
    res.companies_attempted = ["A", "B", "C", "D"]
    res.companies_with_10k = ["A", "B", "C"]
    res.companies_with_any_disclosure = ["A", "B"]
    res.companies_with_named_counterparty = ["A"]
    res.edges = [
        LinkageEdge("A", "1", "Apple Inc.", True, DIRECTION_CUSTOMER, 22.0,
                    "2026-02-14", "acc", "10-K"),
        LinkageEdge("B", "2", None, False, DIRECTION_CUSTOMER, 18.0,
                    "2026-02-14", "acc", "10-K"),
    ]
    cov = res.coverage()
    check("9a. named-counterparty coverage is reported separately from any-disclosure",
          cov["companies_with_named_counterparty"] == 1
          and cov["companies_with_any_disclosure"] == 2)
    check("9b. named and unnamed edges are counted separately",
          cov["named_edges"] == 1 and cov["unnamed_edges"] == 1)
    check("9c. percentages are against the ATTEMPTED universe, not the found subset",
          cov["pct_with_named_counterparty"] == 25.0,
          "1 of 4 attempted, not 1 of 2 found -- the denominator matters")
    check("9d. request count is reported", "requests_made" in cov)


# ===================== 10. reconciliation NEVER merges ===================
def test_10_reconcile_flags_and_never_merges() -> None:
    edgar = [
        LinkageEdge("NVDA", "1", "Dell Technologies Inc.", True,
                    DIRECTION_CUSTOMER, 13.0, "2026-02-14", "a", "10-K"),
        LinkageEdge("NVDA", "1", "Acme Holdings", True,
                    DIRECTION_CUSTOMER, 11.0, "2026-02-14", "a", "10-K"),
    ]
    mate = [{"anchor_ticker": "NVDA", "peer_ticker": "Dell Technologies Inc"},
            {"anchor_ticker": "NVDA", "peer_ticker": "Widget Corp"}]

    r = reconcile(edgar, mate)
    check("10a. reconciliation does not merge", r["merged"] is False)
    check("10b. and does not declare itself reconciled", r["reconciled"] is False)
    check("10c. it is explicitly for human review",
          r["status"] == "RECONCILED_FOR_HUMAN_REVIEW")
    check("10d. agreement is detected across punctuation differences",
          r["agreement_count"] == 1, str(r["in_both_sources"]))
    check("10e. edgar-only edges are flagged", len(r["edgar_only"]) == 1)
    check("10f. teammate-only edges are flagged", len(r["teammate_only"]) == 1)
    check("10g. teammate-only absence is explained as EXPECTED, not as a conflict",
          "NOT evidence against" in r["interpretation"]["teammate_only"])
    check("10h. it states plainly that nothing is merged",
          "Nothing is merged" in r["no_automatic_merge"])

    r2 = reconcile(edgar, None)
    check("10i. with no teammate map, it does not self-promote",
          r2["status"] == "TEAMMATE_MAP_UNAVAILABLE"
          and "does NOT become the production map" in r2["note"])


def test_6e_geographies_and_own_segments_are_not_counterparties() -> None:
    """REGRESSION. Four false named edges from the real 2026-08-26 run.

    Extraction over the 51-ticker universe reported five companies with a
    named counterparty. Three were not counterparties at all:

        INTC -> "U.S"             "sales outside the U.S. accounted for 70%"
        NKE  -> "United States"   "sales in the United States accounted for 44%"
        LDOS -> "Digital"         "National Security & Digital represented 44%"
        LDOS -> "Defense Systems" "Defense Systems represented 13%"

    The first two are geographies; the last two are the filer's OWN operating
    segments. Each would have asserted a supply-chain relationship that does
    not exist. Curating any of them would have been fabrication, which is the
    one thing this candidate source must never enable.

    Sentences are verbatim from the filings, so this is a regression fixture
    against the actual defect rather than against a reconstruction of it.
    """
    REAL_POSITIVES = [
        ("MCK", "CVS Health Corporation",
         "Sales to our largest customer, CVS Health Corporation (CVS), "
         "accounted for approximately 24% of our total consolidated revenues "
         "in fiscal 2026."),
        ("PKG", "ODP",
         "In 2025, our sales revenue to ODP represented 58% of our Paper "
         "segment sales revenue and 4% of our consolidated sales revenue."),
    ]
    FALSE_POSITIVES = [
        ("INTC", "geography (bare place name, no 'geographic' word present)",
         "Moreover, sales outside the U.S. accounted for 70% of our revenue "
         "for the fiscal year ended December 27, 2025, with revenue from "
         "billings to China contributing 24% of our total revenue."),
        ("NKE", "geography",
         "For fiscal 2026, NIKE Brand and Converse sales in the United States "
         "accounted for approximately 44% of total revenues, compared to 43%."),
        ("LDOS", "own segment; role word leaks from the previous sentence",
         "We provide services to Intelligence Community customers. National "
         "Security & Digital represented 44% of total revenues for both "
         "fiscal 2025."),
        ("LDOS", "own segment; 'Systems' is a descriptive word, not a legal "
                 "entity suffix",
         "Defense Systems represented 13% of total revenues for fiscal 2025, "
         "and 12% of total revenues for both fiscal 2024 and 2023."),
    ]

    for tk, expected, text in REAL_POSITIVES:
        edges, _ = extract_edges_from_text(
            text, ticker=tk, cik="0", filing_date="2026-01-01",
            accession="x", form="10-K")
        named = [e.named_counterparty for e in edges if e.counterparty_is_named]
        check(f"6e. {tk}: the real counterparty survives",
              expected in named, f"got {named}")

    for tk, why, text in FALSE_POSITIVES:
        edges, _ = extract_edges_from_text(
            text, ticker=tk, cik="0", filing_date="2026-01-01",
            accession="x", form="10-K")
        named = [e.named_counterparty for e in edges if e.counterparty_is_named]
        check(f"6e. {tk}: rejected -- {why}", not named, f"got {named}")

    # HARDCODED-OPEN: the fix must not be "reject every name". The footnote
    # shape the wide topic window exists for -- role word in a NEIGHBOURING
    # sentence, name carrying a legal suffix -- must still be captured.
    foot = ("Concentration of credit risk. The Company sells to a limited "
            "number of customers. Apple Inc. accounted for 22% of net "
            "revenues in fiscal 2025. No other customer exceeded 10%.")
    edges, _ = extract_edges_from_text(
        foot, ticker="FOOT", cik="0", filing_date="2026-01-01",
        accession="x", form="10-K")
    named = [e.named_counterparty for e in edges if e.counterparty_is_named]
    check("6e. the cross-sentence footnote case is still captured",
          any("Apple" in (n or "") for n in named), f"got {named}")


# Verbatim from PKG's 10-K filed 2026-02-26, accession 0001193125-26-074129,
# document pkg-20251231.htm. Fetched and read 2026-08-26.
PKG_ODP_VERBATIM = (
    "ODP Corporation (ODP), formerly Office Depot, Inc., along with its "
    "subsidiaries and affiliates, is our largest customer in the Paper "
    "segment. In 2025, our sales revenue to ODP represented 58% of our Paper "
    "segment sales revenue and 4% of our consolidated sales revenue."
)

# Verbatim from MCK's 10-K filed 2026-05-08, accession 0000927653-26-000069.
MCK_CVS_VERBATIM = (
    "Our ten largest customers, including group purchasing organizations, "
    "accounted for approximately 73% of our total consolidated revenues. "
    "Sales to our largest customer, CVS Health Corporation (CVS), accounted "
    "for approximately 24% of our total consolidated revenues in fiscal 2026 "
    "and comprised approximately 21% of total trade accounts receivable."
)


def test_6f_the_concentration_denominator_is_recorded() -> None:
    """A percentage without its denominator is not a comparable quantity.

    Read as a bare 58%, PKG's ODP disclosure is the largest concentration in
    the whole 51-ticker screen. Read WITH its denominator it is a segment
    share -- and the same sentence puts the entity-wide figure at 4%.

    Until 2026-08-26 the concentration anchors captured that denominator in a
    `basis` group that nothing read, so anything selecting on ">= 10%" across
    these edges was comparing three different quantities: a share of
    consolidated revenue, a share of one segment, and a share of accounts
    receivable. ASC 280-10-50-42 states its threshold against the ENTITY's
    revenues, so only the first is the quantity the standard is about.
    """
    pkg, _ = extract_edges_from_text(
        PKG_ODP_VERBATIM, ticker="PKG", cik="0000075677",
        filing_date="2026-02-26", accession="0001193125-26-074129")
    named = [e for e in pkg if e.counterparty_is_named]
    check("6f-a. the PKG/ODP edge is still extracted", len(named) == 1,
          str([e.named_counterparty for e in pkg]))
    if named:
        e = named[0]
        check("6f-b. and its denominator is the SEGMENT, not the entity",
              e.concentration_basis == BASIS_SEGMENT_REVENUE,
              f"{e.concentration_pct}% of {e.concentration_basis_text!r} "
              f"-> {e.concentration_basis}")
        check("6f-c. the filing's own words are kept alongside the label",
              "paper segment" in e.concentration_basis_text.lower(),
              repr(e.concentration_basis_text))

    mck, _ = extract_edges_from_text(
        MCK_CVS_VERBATIM, ticker="MCK", cik="0000927653",
        filing_date="2026-05-08", accession="0000927653-26-000069")
    named = [e for e in mck if e.counterparty_is_named]
    by_pct = {e.concentration_pct: e for e in named}

    # HARDCODED-OPEN CONTROL. Both figures describe the same counterparty in
    # the same sentence of the same filing. A classifier that collapsed the
    # denominator would make them indistinguishable, and 21% of RECEIVABLES
    # would count toward a revenue-concentration rule.
    check("6f-d. both MCK figures survive as separate edges",
          set(by_pct) == {24.0, 21.0}, str(sorted(by_pct)))
    if 24.0 in by_pct:
        check("6f-e. 24% is against consolidated revenue",
              by_pct[24.0].concentration_basis == BASIS_CONSOLIDATED_REVENUE,
              by_pct[24.0].concentration_basis_text)
    if 21.0 in by_pct:
        check("6f-f. 21% is against RECEIVABLES, not revenue",
              by_pct[21.0].concentration_basis == BASIS_RECEIVABLES,
              by_pct[21.0].concentration_basis_text)

    check("6f-g. every emitted basis is in the closed vocabulary",
          all(e.concentration_basis in CONCENTRATION_BASES for e in pkg + mck),
          str({e.concentration_basis for e in pkg + mck}))


def test_6g_the_basis_classifier_fails_closed() -> None:
    """An unrecognised denominator must never be read as entity-wide.

    The failure that matters is one-directional: calling a narrowed
    denominator "consolidated" admits a company to a revenue-concentration
    universe it does not belong in. Calling a consolidated denominator
    "unknown" only excludes, which is recoverable and visible.
    """
    entity_wide = ("total revenues", "our total consolidated revenues",
                   "total net sales", "our revenue", "net revenues",
                   "our consolidated sales revenue")
    for t in entity_wide:
        check(f"6g. entity-wide: {t!r}",
              classify_concentration_basis(t) == BASIS_CONSOLIDATED_REVENUE,
              classify_concentration_basis(t))

    narrowed = {
        "our Paper segment sales revenue": BASIS_SEGMENT_REVENUE,
        "the Data Center division revenue": BASIS_SEGMENT_REVENUE,
        "total trade accounts receivable": BASIS_RECEIVABLES,
        "the total deferred revenue": BASIS_DEFERRED_REVENUE,
        # Not a segment WORD and not entity-wide either -- fail closed.
        "North America sales": BASIS_UNKNOWN,
        "Data Center revenue": BASIS_UNKNOWN,
        "": BASIS_UNKNOWN,
    }
    for t, expected in narrowed.items():
        got = classify_concentration_basis(t)
        check(f"6g. not entity-wide: {t!r} -> {expected}", got == expected, got)

    check("6g. None is unknown, not consolidated",
          classify_concentration_basis(None) == BASIS_UNKNOWN)
    check("6g. nothing outside the closed vocabulary is ever returned",
          all(classify_concentration_basis(t) in CONCENTRATION_BASES
              for t in list(entity_wide) + list(narrowed) + [None, "  "]))



def test_6h_older_filing_prose_does_not_manufacture_counterparties() -> None:
    """The gates were tuned on 2026 filings. Widening to 1996-2026 broke them.

    Every string below is verbatim from the filing named beside it, taken from
    the full-frame 10-K history walk of 2026-08-27. Each produced a QUALIFYING
    anchor-universe member -- that is, each would have put a company into a
    preregistered universe on the strength of a relationship that does not
    exist as described.

    This is the same failure as the 2026-08-26 geographies-and-segments round,
    and it recurred for the same structural reason: the corpus grew and the
    gates did not. The four gates added here are STRUCTURAL rather than lists,
    because the one list-based gate (GEOGRAPHIC_PARTY) is what failed -- it
    enumerated a dozen places and did not contain "Singapore".
    """
    def named(text, filing_date):
        edges, _ = extract_edges_from_text(text, ticker="T", cik="0",
                                           filing_date=filing_date, accession="a")
        return {e.named_counterparty for e in edges if e.counterparty_is_named}

    # Microchip 10-K 2003-06-05, accession 0000950147-03-000708. "Distributors"
    # is the whole channel; the all-caps section heading above it was swallowed
    # into the name, giving the counterparty "DISTRIBUTION Distributors".
    mchp = ("DISTRIBUTION Distributors accounted for 60% of our net sales in "
            "fiscal 2003, 62% of our net sales in fiscal 2002 and 65% of our "
            "net sales in fiscal 2001. Our largest distributor accounted for "
            "approximately 12% of our net sales.")
    check("6h-a. a bare plural class noun is an aggregate, not a counterparty",
          named(mchp, "2003-06-05") == set(), str(named(mchp, "2003-06-05")))

    # NVIDIA 10-K 2015-03-12, accession 0001045810-15-000036.
    nvda_geo = ("We also generate a significant portion of our revenue from "
                "sales to customers outside the United States and Other "
                "Americas. Revenue from sales to customers outside of the "
                "United States and Other Americas accounted for 75% of total "
                "revenue for both fiscal year 2015 and 2014.")
    check("6h-b. 'outside of the United States' is a geography, not a customer",
          named(nvda_geo, "2015-03-12") == set(),
          str(named(nvda_geo, "2015-03-12")))

    # NVIDIA 10-K 2025-02-26, accession 0001045810-25-000023. GEOGRAPHIC_PARTY
    # is a LIST and did not contain Singapore -- which is the argument for
    # matching the construction instead of the place.
    nvda_sg = ("Singapore (1) 23,684 6,831 2,288 Taiwan 20,573 13,405 6,986 "
               "(1) Singapore represented 18 % of fiscal year 2025 total "
               "revenue based upon customer billing location. Customers use "
               "Singapore to centralize invoicing while our products are "
               "almost always shipped elsewhere.")
    check("6h-c. a billing-location table is a geography, not a customer",
          named(nvda_sg, "2025-02-26") == set(), str(named(nvda_sg, "2025-02-26")))

    # Qualcomm 10-K 2013-11-06, accession 0001234452-13-000483. The 26% is the
    # PAIR; the backward scan attributed all of it to HTC alone.
    qcom = ("QCT and QTL segment revenues from Samsung Electronics and HTC "
            "comprised 26% of total consolidated revenues in fiscal 2013.")
    check("6h-d. a percentage shared by two named parties is attributed to "
          "neither", named(qcom, "2013-11-06") == set(),
          str(named(qcom, "2013-11-06")))

    # Cognizant 10-K 2007-02-16, accession 0001193125-07-034095. The filing
    # states plainly that there was NO 10% customer in 2005 or 2006; the 13.7%
    # is a 2004 comparative. Stamped with the filing date it would have made
    # Cognizant a registered anchor in 2007 on a fact the filing supersedes.
    ctsh_stale = ("No customer accounted for revenues in excess of 10% of "
                  "total revenues in 2006 and 2005. One customer, JPMorgan "
                  "Chase, accounted for 13.7% of revenues in 2004.")
    check("6h-e. a prior-period comparative is not a current disclosure",
          named(ctsh_stale, "2007-02-16") == set(),
          str(named(ctsh_stale, "2007-02-16")))

    # ---- HARDCODED-OPEN CONTROLS ----
    # Without these, a gate that rejected everything would pass all five above.

    # Apple 10-K 2000-12-14, accession 0000912057-00-053623.
    aapl = ("The Company distributes its products through wholesalers, "
            "resellers, national and regional retailers and cataloguers. "
            "During 2000, a single distributor, Ingram Micro Inc., accounted "
            "for approximately 11.5% of net sales. No other customer accounted "
            "for more than 10% of net sales during 2000.")
    check("6h-f. CONTROL -- a genuine single named distributor survives",
          named(aapl, "2000-12-14") == {"Ingram Micro Inc"},
          str(named(aapl, "2000-12-14")))

    # Cognizant 10-K 2004-03-12, accession 0000903100-04-000126. Same
    # counterparty as 6h-e, but the CURRENT year -- so it must survive.
    ctsh_ok = ("During 2003, one customer, JP Morgan Chase, accounted for "
               "10.1% of our revenues and, in 2002, no single customer "
               "accounted for greater than 10% of revenues.")
    check("6h-g. CONTROL -- the same name in the CURRENT year survives",
          named(ctsh_ok, "2004-03-12") == {"JP Morgan Chase"},
          str(named(ctsh_ok, "2004-03-12")))

    # Intel 10-K 2005-02-22, accession 0001193125-05-033162. A one-year lag is
    # normal for an annual report and must NOT read as a stale comparative.
    intc = ("We sell our products primarily to OEMs and ODMs. We also sell our "
            "products to industrial and retail distributors. In 2004, Dell "
            "Inc. accounted for approximately 19% of our total sales, and "
            "Hewlett-Packard Company accounted for approximately 16% of our "
            "total sales.")
    got = named(intc, "2005-02-22")
    check("6h-h. CONTROL -- a one-year lag is current, not stale",
          "Dell Inc" in got, str(got))
    # KNOWN UNDER-INCLUSION, recorded rather than fixed here: "Company" is
    # deliberately absent from LEGAL_ENTITY_SUFFIX (segments are named
    # "...Group", "...Systems"), and this sentence carries no role word, so
    # Hewlett-Packard is dropped by the 2026-08-26 attribution gate. It costs
    # nothing on this filing -- Dell at 19% already qualifies Intel -- and
    # widening that suffix risks the four false positives it was built for.
    check("6h-i. and the two clauses are NOT treated as a joint pair",
          "Dell Inc" in got and len(got) <= 2, str(got))

    # NVIDIA 10-K 2020-02-20, accession 0001045810-20-000010.
    nvda_dell = ("Sales to Dell Technologies Inc., or Dell, accounted for 11% "
                 "of our total revenue for fiscal year 2020.")
    check("6h-j. CONTROL -- a genuine named customer survives",
          named(nvda_dell, "2020-02-20") == {"Dell"},
          str(named(nvda_dell, "2020-02-20")))

    # McKesson 10-K 2001-06-01, accession 0000950149-01-500834 -- the oldest
    # genuine qualifying disclosure the walk found.
    mck = ("Fiscal 2001 sales to, and March 31, 2001 receivables from, the "
           "Company's largest customer, Rite Aid Corporation, represented "
           "approximately 16% of consolidated sales and 10% of consolidated "
           "customer accounts receivable, respectively.")
    check("6h-k. CONTROL -- a 2001 appositive disclosure survives",
          named(mck, "2001-06-01") == {"Rite Aid Corporation"},
          str(named(mck, "2001-06-01")))



def test_6i_exhaustive_enumeration_round_two() -> None:
    """Found by enumerating EVERY qualifying disclosure, not just the visible ones.

    Round one (test_6h) inspected only the disclosures that opened a
    membership interval -- the ones the report happened to print. That is not
    a measurement, it is a spot check. Enumerating all 1,239 filings' named
    disclosures at or above 10% of consolidated revenue surfaced three more
    fabrications that the printed summary had hidden behind a genuine one.

    The lesson is recorded in the gates themselves: each of the three matches
    a CONSTRUCTION. Round one already established that the list-based gate is
    the one that fails, and "Hong Kong" proved it twice over -- a second place
    name, absent from the same list that lacked Singapore.
    """
    def named(text, filing_date):
        edges, _ = extract_edges_from_text(text, ticker="T", cik="0",
                                           filing_date=filing_date, accession="a")
        return {e.named_counterparty for e in edges if e.counterparty_is_named}

    # Intel 10-K 2007-02-26. "Mobility Group" is Intel's own operating
    # segment. The sentence that says so is the PREVIOUS one, and
    # NON_CUSTOMER_SUBJECT is checked sentence-bounded on purpose -- so the
    # giveaway has to be "within the", which is internal by construction.
    intc = ("Net revenue for the Mobility Group operating segment made up 35% "
            "of our consolidated net revenue in 2006. Revenue from sales of "
            "microprocessors within the Mobility Group represented 26% of "
            "consolidated net revenue in 2006.")
    check("6i-a. revenue earned WITHIN the filer is not a counterparty",
          named(intc, "2007-02-26") == set(), str(named(intc, "2007-02-26")))

    # Microchip 10-K 2015-05-27. A SECOND place name missing from
    # GEOGRAPHIC_PARTY's list, after Singapore. The construction is the signal.
    mchp = ("Americas' sales include sales to customers in the U.S., Canada, "
            "Central America and South America. Sales to customers in China, "
            "including Hong Kong, accounted for approximately 28% of our net "
            "sales in fiscal 2015.")
    check("6i-b. 'sales to customers in <place>' is a geography",
          named(mchp, "2015-05-27") == set(), str(named(mchp, "2015-05-27")))

    # NVIDIA 10-K 2007-03-16. "a CEM" is what Asustek IS, not who it is.
    # The real counterparty sits immediately before the category, and must be
    # recovered rather than lost -- dropping both would trade a fabrication
    # for a missing real relationship.
    nvda = ("As a result of our channel strategy, our sales are focused on a "
            "small number of customers. Sales to Asustek Computer Inc., or "
            "Asustek, a CEM, accounted for 12% of our total revenue for "
            "fiscal 2007.")
    got = named(nvda, "2007-03-16")
    check("6i-c. an indefinite article marks a category, not an entity",
          "CEM" not in got, str(got))
    check("6i-d. and the counterparty it describes is still recovered",
          got == {"Asustek"}, str(got))

    # ---- HARDCODED-OPEN CONTROLS ----
    # Microchip's genuine distributor, in the same filings as 6i-b. Without
    # this, gate 6i-b could delete Microchip's real membership unnoticed.
    mchp_ok = ("In fiscal 2011, we derived 58% of our net sales through "
               "distributors. Our largest distributor, Future Electronics, "
               "accounted for approximately 10% of our net sales in each of "
               "fiscal 2012 and fiscal 2011.")
    check("6i-e. CONTROL -- Microchip's real distributor survives",
          named(mchp_ok, "2013-05-30") == {"Future Electronics"},
          str(named(mchp_ok, "2013-05-30")))

    # THE ARTICLE CONTROL. Here "a" governs "single distributor", not the
    # name, so Apple's counterparty must be untouched by gate 6i-c.
    aapl = ("The Company distributes its products through wholesalers and "
            "resellers. During 2000, a single distributor, Ingram Micro Inc., "
            "accounted for approximately 11.5% of net sales.")
    check("6i-f. CONTROL -- an article governing a ROLE word is not the same "
          "thing", named(aapl, "2000-12-14") == {"Ingram Micro Inc"},
          str(named(aapl, "2000-12-14")))

    nvda_ok = ("As a result of our Channel strategy, a small number of our "
               "customers represent the majority of our revenue. Sales to "
               "ASUSTeK Computer Inc., accounted for 11% of our total revenue "
               "for fiscal year 2016.")
    check("6i-g. CONTROL -- the same counterparty without the appositive",
          named(nvda_ok, "2016-03-17") == {"ASUSTeK Computer Inc"},
          str(named(nvda_ok, "2016-03-17")))


def test_6j_the_denominator_classifier_does_not_silently_under_include() -> None:
    """Over-inclusion was measured; under-inclusion has to be measured too.

    Every gate added on 2026-08-27 REJECTS things, and `other_or_unknown`
    fails closed. Both shrink the universe silently. Measured across all 1,239
    filings of the full-frame walk, exactly TWO named disclosures at or above
    10% carried an unrecognised denominator -- both Qualcomm SEGMENT revenues
    ("QCT revenue", "QWS revenue"), which the rule excludes correctly anyway.

    This pins the phrasings that must keep classifying, so a future tightening
    of the classifier cannot quietly start dropping entity-wide denominators.
    """
    entity_wide = (
        "net sales",                    # Apple, 2000
        "our revenues",                 # Cognizant, 2003
        "our total sales",              # Intel, 2004
        "consolidated sales",           # McKesson, 2001
        "our total consolidated revenues",   # McKesson, 2013
        "our total revenue",            # NVIDIA, 2020
        "our net sales",                # Microchip, 2013
        "consolidated net revenue",     # Intel, 2006
        "total revenue",                # NVIDIA, 2002
    )
    for phrase in entity_wide:
        check(f"6j. entity-wide denominator still classifies: {phrase!r}",
              classify_concentration_basis(phrase) == BASIS_CONSOLIDATED_REVENUE,
              classify_concentration_basis(phrase))

    # And the two that legitimately did not classify stay unclassified: a
    # segment denominator must never be read as entity-wide.
    for phrase in ("QCT revenue", "QWS revenue"):
        check(f"6j. a segment-coded denominator is NOT entity-wide: {phrase!r}",
              classify_concentration_basis(phrase) != BASIS_CONSOLIDATED_REVENUE,
              classify_concentration_basis(phrase))


def test_11_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("11a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("11a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_client_refuses_without_a_real_contact()
    test_2_named_counterparty_with_percentage()
    test_3_sales_to_phrasing()
    test_4_unnamed_customer_is_not_an_edge()
    test_5_explicit_no_concentration_is_information()
    test_6_near_miss_text_produces_no_edge()
    test_6b_aggregate_disclosures_are_not_edges()
    test_6c_non_customer_percentages_are_rejected()
    test_6d_appositive_names_are_captured()
    test_6e_geographies_and_own_segments_are_not_counterparties()
    test_6f_the_concentration_denominator_is_recorded()
    test_6g_the_basis_classifier_fails_closed()
    test_6h_older_filing_prose_does_not_manufacture_counterparties()
    test_6i_exhaustive_enumeration_round_two()
    test_6j_the_denominator_classifier_does_not_silently_under_include()
    test_7_direction_inference()
    test_8_strip_markup()
    test_9_coverage_is_reported_as_a_floor()
    test_10_reconcile_flags_and_never_merges()
    test_11_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 EDGAR EXTRACTOR TESTS PASSED")
    sys.exit(0)
