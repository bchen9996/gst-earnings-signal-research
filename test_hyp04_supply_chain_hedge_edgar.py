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
    DIRECTION_COMPETITOR,
    DIRECTION_CUSTOMER,
    DIRECTION_SUPPLIER,
    SOURCE_10K_COMPETITION_SECTION_PROSE,
    EdgarClient,
    EdgarContactError,
    ExtractionResult,
    LinkageEdge,
    classify_concentration_basis,
    clean_party,
    extract_competitor_edges_from_text,
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



def test_6k_possessive_denominators_are_read_layer_by_layer() -> None:
    """Was a pinned GAP until 2026-08-28; now pins the fix.

    The anchor's denominator group admits an apostrophe, so "15% of the
    Company's revenues" is matched rather than invisible. This test flipped
    when that landed, which is what it existed to do -- the gap was asserted,
    not described, so closing it had to be a deliberate act.

    THE TWO LAYERS REMAIN DISTINCT, and that is what is pinned now. Matching
    is not accepting: the classifier still decides the denominator, and it
    still fails closed. "the Company's ..." is entity-wide; a possessive built
    on the filer's NAME or on Corporation/Registrant is not in the qualifier
    set, so those match the anchor and are then rejected as
    other_or_unknown -- visible to the extractor, excluded from the universe.
    """
    S = "Sales to Rite Aid Corporation represented approximately 15% of {d}."

    def edges(d):
        e, _ = extract_edges_from_text(
            S.format(d=d), ticker="X", cik="0",
            filing_date="2005-01-01", accession="a")
        return e

    def named(d):
        return {e.named_counterparty for e in edges(d) if e.counterparty_is_named}

    def basis(d):
        got = [e.concentration_basis for e in edges(d)]
        return got[0] if got else None

    # Layer 1: all of these now MATCH, where previously none did.
    entity_possessive = ("the Company's revenues", "the Company's net sales",
                         "the Company's consolidated revenues",
                         "the Company's total revenues")
    for d in entity_possessive:
        check(f"6k. possessive denominator is now matched: {d!r}",
              named(d) == {"Rite Aid Corporation"}, str(named(d)))
        check(f"6k. and layer 2 places it as entity-wide: {d!r}",
              basis(d) == BASIS_CONSOLIDATED_REVENUE, str(basis(d)))

    # Layer 2 still fails closed on a self-reference the qualifier set does
    # not carry. These are MATCHED but NOT usable, and the distinction is the
    # point: an unrecognised denominator is never read as entity-wide.
    unclassified_possessive = ("McKesson's revenues", "the Corporation's revenues",
                               "the Registrant's revenues")
    for d in unclassified_possessive:
        check(f"6k. matched, but the denominator stays unrecognised: {d!r}",
              basis(d) == BASIS_UNKNOWN, str(basis(d)))
        check(f"6k. so it is NOT entity-wide: {d!r}",
              classify_concentration_basis(d) != BASIS_CONSOLIDATED_REVENUE,
              classify_concentration_basis(d))

    # CONTROLS -- the non-possessive forms must be untouched by the widening.
    seen = ("revenues", "net sales", "total revenues", "consolidated revenues",
            "consolidated sales", "our revenues", "our net sales",
            "our total revenues", "our consolidated revenues",
            "total company revenues", "company revenues", "its revenues",
            "their revenues")
    for d in seen:
        check(f"6k. CONTROL -- non-possessive unchanged: {d!r}",
              named(d) == {"Rite Aid Corporation"}, str(named(d)))


def test_6l_the_verb_set_admits_equivalence_but_not_contribution() -> None:
    """Was a pinned GAP until 2026-08-28; now pins the fix and its boundary.

    Copular and equivalence phrasings state the same relation the original
    five lemmas state, and are ordinary 10-K prose, so they are accepted.

    THE BOUNDARY IS THE POINT OF THIS TEST. generated / provided / contributed
    describe what a counterparty CONTRIBUTED rather than asserting the share
    IS the figure. Admitting them would be a semantic widening, not a phrasing
    fix, and it is still refused. This half must not quietly flip the way the
    first half just did.
    """
    S = "Sales to Rite Aid Corporation {v} consolidated sales."

    def named(v):
        e, _ = extract_edges_from_text(
            S.format(v=v), ticker="X", cik="0",
            filing_date="2005-01-01", accession="a")
        return {x.named_counterparty for x in e if x.counterparty_is_named}

    accepted = ("represented approximately 15% of",
                "accounted for approximately 15% of",
                "comprised approximately 15% of",
                "constituted approximately 15% of",
                "made up approximately 15% of",
                "represented 15% of", "accounted for 15% of",
                # newly accepted 2026-08-28
                "were approximately 15% of", "was approximately 15% of",
                "totaled 15% of", "equaled 15% of", "approximated 15% of")
    for v in accepted:
        check(f"6l. accepted verb form: {v!r}",
              named(v) == {"Rite Aid Corporation"}, str(named(v)))

    still_refused = ("generated 15% of", "provided 15% of",
                     "contributed 15% of", "is 15% of", "are 15% of")
    for v in still_refused:
        check(f"6l. STILL REFUSED -- contribution is not equivalence: {v!r}",
              named(v) == set(), str(named(v)))



def test_6m_the_widening_and_the_four_gates_it_required() -> None:
    """Verbatim fixtures for 2026-08-28. Every one is real filing text.

    The widening (possessive denominators, copular verbs) reached prose no gate
    had been tested against, and measuring it over the cached corpus surfaced
    four separate defects. Three of them were LATENT IN THE OLD CODE, not
    introduced by the widening -- with an accepted verb the old extractor
    produced the same fabrications. The corpus was clean by accident, because
    the filings carrying those constructions happen to use verbs the anchor
    did not match.

    Net effect on the anchor universe: NONE. Six members, nine intervals,
    unchanged. What changed is that three counterparties stopped being
    mis-parsed and four fabrication routes were closed.
    """
    def named(text, filing_date, ticker="X"):
        edges, _ = extract_edges_from_text(
            text, ticker=ticker, cik="0", filing_date=filing_date,
            accession="a")
        return {e.named_counterparty for e in edges if e.counterparty_is_named}

    # ---- 1. THE COMMA BEFORE THE LEGAL SUFFIX -------------------------
    # "Foot Locker, Inc." captured as "Inc" -- a fabricated counterparty
    # standing in for a real one. Corpus-wide this mis-parsed three real
    # names: Ingram Micro (AAPL), Caremark RX (MCK), Hyundai (QCOM).
    nke = ("Major Customers. Revenues derived from Foot Locker, Inc. "
           "represented 11% of the Company's consolidated revenues.")
    check("6m-a. a comma before the legal suffix no longer truncates the name",
          named(nke, "2002-08-14", "NKE") == {"Foot Locker, Inc"},
          str(named(nke, "2002-08-14", "NKE")))

    aapl = ("The Company distributes its products through wholesalers and "
            "resellers. During 2000, a single distributor, Ingram Micro, Inc., "
            "accounted for approximately 11.5% of net sales.")
    check("6m-b. and the appositive path gets the same fix",
          named(aapl, "2000-12-14", "AAPL") == {"Ingram Micro, Inc"},
          str(named(aapl, "2000-12-14", "AAPL")))

    # ---- 2. THE FILER'S OWN BUSINESS UNIT, BY HEAD NOUN ---------------
    # Genuine Parts 2001-03-12. No "of the Company" appositive in the claim's
    # own sentence -- the heading two sentences earlier says "SEGMENT DATA."
    # and nothing nearer does. Only the name's SHAPE gives it away. Ungated,
    # this made GPC an anchor whose counterparty is GPC's own segment at 50%
    # of consolidated revenue.
    gpc = ("SEGMENT DATA. In the year ended December 31, 2000, sales from the "
           "Automotive Parts Group approximated 50% of the Company's net "
           "sales as compared to 51% in 1999 and 49% in 1998.")
    check("6m-c. a unit head noun is not an entity",
          named(gpc, "2001-03-12", "GPC") == set(),
          str(named(gpc, "2001-03-12", "GPC")))

    # THE CONTROL THAT MAKES 6m-c SAFE. A real counterparty carrying "Group"
    # inside its name keeps it; only the HEAD is a unit noun.
    intc = ("Major customers. Sales to Lenovo Group Limited accounted for "
            "12% of our net revenue.")
    check("6m-d. CONTROL -- 'Group' inside a real name is untouched",
          named(intc, "2015-02-17", "INTC") == {"Lenovo Group Limited"},
          str(named(intc, "2015-02-17", "INTC")))

    # ---- 3. "including X" MAKES X AN INSTANCE, NOT A PARTY ------------
    # NVIDIA 2019-02-21. A share attributed to a set is not a bilateral
    # relationship with one member of it.
    nvda = ("Major customers. Revenue from billings to China, including Hong "
            "Kong, was 24% of total revenue.")
    check("6m-e. 'including <X>' is an instance of the measured category",
          named(nvda, "2019-02-21", "NVDA") == set(),
          str(named(nvda, "2019-02-21", "NVDA")))
    # and it is NOT verb-specific: the old accepted verb produced the same
    # fabrication, which is why this is a gate and not a widening artefact.
    check("6m-f. and the same construction with an ACCEPTED verb is also "
          "rejected -- the fabrication was latent, not introduced",
          named(nvda.replace("was 24%", "accounted for 24%"),
                "2019-02-21", "NVDA") == set(),
          str(named(nvda.replace("was 24%", "accounted for 24%"),
                    "2019-02-21", "NVDA")))

    # ---- 4. "year ended <Month> <day>, <year>" IS A STATED YEAR -------
    # NIKE 2004-07-30, in the very filing that says 2004 and 2003 had no
    # customer above 10%. Without this the sentence yields NO stated year, the
    # stale-comparative gate cannot fire, and the disclosure is stamped with
    # the 2004 FILING date -- opening an interval on the filing that denies
    # one.
    nke_stale = ("In 2004 and 2003 the Company did not have a significant "
                 "customer that accounted for more than 10% of consolidated "
                 "revenues. During the year ended May 31, 2002, revenues "
                 "derived from Foot Locker, Inc. represented 11% of the "
                 "Company's consolidated revenues.")
    check("6m-g. a comparative dated by 'year ended <date>' is stale",
          named(nke_stale, "2004-07-30", "NKE") == set(),
          str(named(nke_stale, "2004-07-30", "NKE")))

    # THE CONTROL. One year of lag is NORMAL -- an annual report reports the
    # year that just ended. This must not be rejected, or the gate would empty
    # the universe.
    intc_lag = ("Major customers. For the year ended December 31, 2004, sales "
                "to Dell Inc. were 19% of consolidated revenues.")
    check("6m-h. CONTROL -- the reporting year itself is not stale",
          named(intc_lag, "2005-02-22", "INTC") == {"Dell Inc"},
          str(named(intc_lag, "2005-02-22", "INTC")))

    # ---- 5. THE WIDENING ITSELF STILL WORKS ---------------------------
    mck = ("Sales to the Company's largest customer, Rite Aid Corporation, "
           "were approximately 15% of the Company's consolidated revenues.")
    check("6m-i. copular verb AND possessive denominator together",
          named(mck, "2000-06-13", "MCK") == {"Rite Aid Corporation"},
          str(named(mck, "2000-06-13", "MCK")))


def test_6n_a_list_under_a_stated_denominator_is_unreadable() -> None:
    """Was a pinned GAP for the length of one commit; now pins the fix.

    Every anchor in CONCENTRATION_ANCHORS requires the percentage and the
    denominator to sit adjacent in ONE match -- "<pct>% of <basis>". Real
    filings routinely state the denominator ONCE in a scope clause and then
    list parties carrying bare percentages:

        prose   "our three largest customers accounted for 40% of our net
                 revenue, with Dell Inc. accounting for 16% ..."
        table   "accounted for the following percentage of our net revenue:
                 ... Dell Inc. 19 % 19 % 21 %"

    Neither can satisfy an adjacency-based anchor, so BOTH are invisible. The
    surface form is incidental -- the verb tense, the table layout and the
    parenthetical comparatives are all downstream of the one structural fact
    that the denominator is not repeated per party.

    THE COST IS ALREADY IN THE PUBLISHED REGISTRY. Intel's membership interval
    closes at 2017-02-17, which is not when the relationship ended but when
    Intel moved the disclosure out of Item 1 prose. Dell is disclosed at
    15-21% of Intel's net revenue in every filing from 2017-02-17 through
    2024-01-26, in plain English. Adobe never appears in any registry version
    at all, though Ingram Micro is disclosed at 11-21% of net revenue across
    2008-2015. Both are data AVAILABILITY deciding membership, which AU-1..AU-6
    forbid.

    The fixtures below are verbatim from the cached corpus, accession noted.
    """
    # ---------------- THE GAP: real disclosures, currently unreadable -------
    # INTC 0000050863-18-000007, filed 2018-02-16, period 2017-12-30.
    intc_prose = (
        "In 2017 , our three largest customers accounted for 40% of our net "
        "revenue ( 38% in 2016 ), with Dell Inc. (Dell) accounting for 16% "
        "( 15% in 2016 ), Lenovo Group Limited (Lenovo) accounting for 13% "
        "( 13% in 2016 ), and HP Inc. accounting for 11% ( 10% in 2016 ). "
        "These three customers accounted for 36% of our accounts receivable "
        "as of December 30, 2017 ( 31% as of December 31, 2016 )."
    )
    # INTC 0000050863-24-000010, filed 2024-01-26, period 2023-12-30.
    intc_table = (
        "Our three largest customers accounted for the following percentage "
        "of our net revenue: Years Ended Dec 30, 2023 Dec 31, 2022 Dec 25, "
        "2021 Dell Inc. 19 % 19 % 21 % Lenovo Group Limited 11 % 12 % 12 % "
        "HP Inc. 10 % 11 % 10 % Total percentage of net revenue 40 % 42 % 43 %"
    )
    # ADBE 0000796343-11-000003, filed 2011-01-27, period 2010-12-03.
    adbe_table = (
        "The table below lists our significant customers, as a percentage of "
        "net revenue for fiscal 2010, 2009 and 2008. As listed, our "
        "significant customers are distributors who sell products across our "
        "various segments. 2010 2009 2008 Ingram Micro 15 % 15 % 18 %"
    )

    def named(text, filing_date, report_date):
        e, _ = extract_edges_from_text(
            text, ticker="X", cik="0", filing_date=filing_date,
            accession="a", report_date=report_date)
        return {x.named_counterparty for x in e if x.counterparty_is_named}

    def pairs(text, filing_date, report_date):
        e, _ = extract_edges_from_text(
            text, ticker="X", cik="0", filing_date=filing_date,
            accession="a", report_date=report_date)
        return {(x.named_counterparty, x.concentration_pct, x.concentration_basis)
                for x in e if x.counterparty_is_named}

    # THE READING IS PINNED, NOT JUST THE FACT OF ONE. Taking the wrong column
    # would attribute a prior year's concentration to the reporting year --
    # the error the stale gate exists to prevent, committed inside a table
    # where that gate cannot see it. So every percentage is asserted.
    R = BASIS_CONSOLIDATED_REVENUE
    now_read = (
        ("INTC prose, FY2017", intc_prose, "2018-02-16", "2017-12-30",
         {("Dell Inc", 16.0, R), ("Lenovo Group Limited", 13.0, R),
          ("HP Inc", 11.0, R)}),
        ("INTC table, FY2023", intc_table, "2024-01-26", "2023-12-30",
         {("Dell Inc", 19.0, R), ("Lenovo Group Limited", 11.0, R),
          ("HP Inc", 10.0, R)}),
        ("ADBE table, FY2010", adbe_table, "2011-01-27", "2010-12-03",
         {("Ingram Micro", 15.0, R)}),
    )
    for label, text, fd, rd, want in now_read:
        got = pairs(text, fd, rd)
        check(f"6n. {label} is read, with the reporting year's column",
              got == want, f"got {sorted(got)}")

    # The comparatives in those same fixtures must NOT appear. INTC's FY2017
    # prose carries "( 15% in 2016 )" beside Dell's 16%, and its FY2023 table
    # carries 19% and 21% for FY2022 and FY2021 in the same row.
    got = {p for _, p, _ in pairs(intc_table, "2024-01-26", "2023-12-30")}
    check("6n. the prior-year columns are not read as the reporting year",
          21.0 not in got and 12.0 not in got, str(sorted(got)))

    # REFUSAL: multi-column with no readable year header. The same table with
    # its header removed must yield nothing rather than a guess -- column
    # order is not a convention and there is nothing left to read it from.
    headless = (
        "Our three largest customers accounted for the following percentage "
        "of our net revenue: Dell Inc. 19 % 19 % 21 % Lenovo Group Limited "
        "11 % 12 % 12 %"
    )
    got = named(headless, "2024-01-26", "2023-12-30")
    check("6n. REFUSES a multi-column list whose year header is unreadable",
          got == set(), str(got))

    # REFUSAL: a header that does not carry the reporting year at all is a
    # table of comparatives, and none of it belongs to this filing's year.
    stale_header = (
        "Our three largest customers accounted for the following percentage "
        "of our net revenue: Years Ended Dec 31, 2019 Dec 31, 2018 Dec 31, "
        "2017 Dell Inc. 19 % 19 % 21 %"
    )
    got = named(stale_header, "2024-01-26", "2023-12-30")
    check("6n. REFUSES a header that never names the reporting year",
          got == set(), str(got))

    # ---------------- CONTROLS: these must hold BEFORE and AFTER ------------
    # Each is a real scope clause governing a real list of names with figures
    # at or above the threshold. Every one of them must yield NO counterparty.
    # They are the reason a scoped-list reader cannot simply take every name
    # that follows a denominator.

    # GOOGL 0001652044-25-000014, filed 2025-02-05. A GEOGRAPHY table whose
    # scope clause names customers outright -- "the addresses of our
    # customers". Role word, revenue denominator, names, figures over the
    # threshold, and not one counterparty in it.
    googl_geo = (
        "Revenues by Geography The following table presents revenues by "
        "geography as a percentage of revenues, determined based on the "
        "addresses of our customers: Year Ended December 31, 2023 2024 "
        "United States 47 % 49 % EMEA 30 % 29 % APAC 17 % 16 % Other "
        "Americas 6 % 6 % Hedging gains (losses) 0 % 0 %"
    )
    got = named(googl_geo, "2025-02-05", "2024-12-31")
    check("6n. CONTROL -- a geography table names no counterparty",
          got == set(), str(got))

    # CTSH 0001058290-20-000008, filed 2020-02-14. An AGGREGATE table: the
    # rows are portfolios, not parties. 14.6% is real and belongs to nobody.
    ctsh_agg = (
        "Revenues from our top clients as a percentage of total revenues "
        "were as follows: For the years ended December 31, 2019 2018 2017 "
        "Top five clients 7.9 % 8.6 % 8.9 % Top ten clients 14.6 % 15.4 % "
        "14.9 %"
    )
    got = named(ctsh_agg, "2020-02-14", "2019-12-31")
    check("6n. CONTROL -- an aggregate table names no counterparty",
          got == set(), str(got))

    # ADBE 0000796343-11-000003. The RECEIVABLES twin of the qualifying table,
    # in the same filing. Same party, same layout, denominator the rule
    # excludes. If a reader takes this one it has stopped reading the header.
    adbe_recv = (
        "Receivables from our significant distributors, as a percentage of "
        "gross trade receivables for fiscal 2010 and 2009 were as follows: "
        "2010 2009 Ingram Micro 14 % 16 %"
    )
    e, _ = extract_edges_from_text(
        adbe_recv, ticker="X", cik="0", filing_date="2011-01-27",
        accession="a", report_date="2010-12-03")
    check("6n. CONTROL -- the receivables twin is never consolidated revenue",
          all(x.concentration_basis != BASIS_CONSOLIDATED_REVENUE for x in e),
          str([(x.named_counterparty, x.concentration_basis) for x in e]))

    # INTC 0000050863-25-000010, filed 2025-01-31. Intel ANONYMISED its
    # customers for FY2024. This is a genuine, rule-based exit from the
    # universe -- not a defect -- and it must stay an exit however good the
    # reader gets. "Customer A" is not a name.
    intc_anon = (
        "Our three largest customers accounted for the following percentage "
        "of our net revenue: Years Ended Dec 28, 2024 Dec 30, 2023 Dec 31, "
        "2022 Customer A 19 % 19 % 19 % Customer B 14 % 11 % 12 % Customer C "
        "12 % 10 % 11 % Total percentage of net revenue 45 % 40 % 42 %"
    )
    got = named(intc_anon, "2025-01-31", "2024-12-28")
    check("6n. CONTROL -- Customer A/B/C is not a named counterparty",
          got == set(), str(got))

    # ---------------- COLUMN ORDER IS NOT A CONVENTION ----------------------
    # The multi-year "respectively" reader takes the FIRST percentage as the
    # reporting year's, because filings list years newest-first. That holds
    # for INTC, ADBE and CTSH above -- and NOT for GOOGL, whose header reads
    # "2023 2024". Both orders are present in this corpus, so a table reader
    # may not carry the respectively-form assumption across. It must read the
    # year header, and refuse when it cannot.
    check("6n. newest-first and oldest-first BOTH occur in the corpus",
          "2010 2009 2008" in adbe_table and "2023 2024" in googl_geo)


def test_11_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("11a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("11a. network blocked", type(e).__name__ == "NetworkBlocked")


def _extract_competitor(text: str):
    return extract_competitor_edges_from_text(
        text, ticker="TEST", cik="0000000001", filing_date="2026-02-14",
        accession="0000000001-26-000001")


# ============ 12. competitor/supplier-context extraction (UNCALIBRATED) ====
def test_12_competitor_supplier_context_extraction() -> None:
    """Offline, synthetic-fixture coverage of a function that HAS ALSO been
    measured against real filing text (24-anchor calibration, 2026-09-12: 0
    false positives across 39 real edges) and is now wired into extract_for_
    universe(). Every fixture below marked "real X gap/defect, fixed" is the
    synthetic reproduction of an actual real-filing finding from that
    calibration -- this file still tests the pure function offline, exactly
    like every other extractor test here, but the cases it covers are no
    longer hypothetical. See the module comment above its definition in
    edgar_linkage.py, and HYP05_EXTRACTOR_CALIBRATION_FULL24ANCHORS_
    2026-09-12.md for the live-filing evidence itself."""
    e1 = _extract_competitor(
        "We compete with Broadcom Inc. and other semiconductor companies "
        "in this market.")
    check("12a. a direct 'we compete with' sentence yields a candidate edge",
          len(e1) == 1 and e1[0].named_counterparty == "Broadcom Inc"
          and e1[0].direction == DIRECTION_COMPETITOR, str(e1))
    check("12b. it is tagged with its own distinct source, not the ASC 280 "
          "one -- wiring this path in does not claim equal confidence with "
          "a percentage-backed ASC 280 disclosure",
          e1[0].source == SOURCE_10K_COMPETITION_SECTION_PROSE
          and e1[0].source != "EDGAR_10K_ASC280")
    check("12c. and carries no percentage -- this path never has one",
          e1[0].concentration_pct is None)

    e2 = _extract_competitor(
        "Our principal competitors include Intel Corporation and AMD in "
        "the CPU market.")
    check("12d. 'principal competitors include' yields exactly the two "
          "listed names, deduplicated across BOTH anchors it matches "
          "('principal_competitors' and the plainer 'competitors_include' "
          "substring) -- not four, and not silently truncated to one",
          {e.named_counterparty for e in e2} == {"Intel Corporation", "AMD"}
          and len(e2) == 2, str(e2))

    e3 = _extract_competitor("We purchase memory chips from Micron "
                             "Technology, Inc.")
    check("12e. supplier-context prose (no percentage, unlike the ASC 280 "
          "path) is captured with DIRECTION_SUPPLIER",
          len(e3) == 1 and e3[0].named_counterparty == "Micron Technology, Inc"
          and e3[0].direction == DIRECTION_SUPPLIER, str(e3))

    e4 = _extract_competitor(
        "Our contract manufacturers include Foxconn and Pegatron.")
    check("12f. contract-manufacturer prose captures BOTH listed names, "
          "not just the first",
          {e.named_counterparty for e in e4} == {"Foxconn", "Pegatron"}
          and len(e4) == 2, str(e4))

    # Adversarial: the same discipline test_6/test_6b-h hold the calibrated
    # path to -- a near-miss must not fabricate a named counterparty.
    e5 = _extract_competitor("We compete with many companies in this "
                             "industry.")
    check("12g. an unnamed competitor ('many companies') is not fabricated "
          "into a company name", e5 == [], str(e5))

    e6 = _extract_competitor("The industry in which we operate is highly "
                             "competitive.")
    check("12h. generic competitive-landscape prose with no anchor phrase "
          "yields nothing", e6 == [], str(e6))

    # 12j/12k are the exact shape of two real false positives found in
    # HYP05_EXTRACTOR_CALIBRATION_2026-09-12.md (NVDA's 10-K): a region name
    # ("Asia") and a product-category noun ("GPUs") captured as if either
    # were a company, because the OLD extractor searched the whole
    # lookahead window instead of anchoring at the start of it. Both must
    # now yield nothing -- no real company name immediately follows the
    # anchor phrase in either sentence.
    e7 = _extract_competitor(
        "Some of our suppliers are located in Asia, making our operations "
        "vulnerable to natural disasters.")
    check("12j. a bare region name after 'suppliers are' is not captured "
          "as a supplier (real NVDA false positive, fixed)", e7 == [], str(e7))

    e8 = _extract_competitor(
        "Our current competitors include: suppliers and licensors of "
        "hardware and software for discrete and integrated GPUs, custom "
        "chips and other accelerators.")
    check("12k. a product-category noun deep in a descriptive sentence is "
          "not captured as a competitor (real NVDA false positive, fixed)",
          e8 == [], str(e8))

    e9 = _extract_competitor(
        "We compete with Apple, Google and Microsoft in this market.")
    check("12l. a three-item list captures all three names, not just the "
          "first",
          {e.named_counterparty for e in e9}
          == {"Apple", "Google", "Microsoft"} and len(e9) == 3, str(e9))

    # 12m is the exact shape of a real false positive found by the LARGER
    # (24-anchor) calibration run, 2026-09-12 same day: TTWO's 10-K reads
    # "we compete with: * Other interactive entertainment companies that
    # range in size..." -- anchoring (which fixed 12j/12k) does not by
    # itself catch this, because "Other" genuinely IS the first capitalized
    # token right after the anchor phrase; the defect is that it is a
    # common English determiner heading a descriptive clause, not a company
    # name. Fixed by extending the shared UNNAMED_TOKENS blocklist.
    e10 = _extract_competitor(
        "In our business, we compete with: Other interactive entertainment "
        "companies that range in size and cost structure.")
    check("12m. a generic determiner ('Other') starting a descriptive "
          "clause is not captured as a competitor (real TTWO false "
          "positive, fixed)", e10 == [], str(e10))

    # 12n guards the fix's precision: the new UNNAMED_TOKENS entries match
    # the ENTIRE captured name after stripping, not a prefix -- a genuine
    # company whose name happens to START with one of the new stopwords
    # must still be captured.
    e11 = _extract_competitor(
        "We compete with Otherworld Games and Roblox in this market.")
    check("12n. a real company name that merely starts with a stopword "
          "('Otherworld Games') is still captured, not rejected as a "
          "prefix match",
          {e.named_counterparty for e in e11}
          == {"Otherworld Games", "Roblox"} and len(e11) == 2, str(e11))

    # 12o/12p are the exact shape of a real RECALL gap found by the same
    # 24-anchor calibration: NCLH's 10-K reads "Our primary competition
    # includes operators such as Carnival and Royal Caribbean, as well as
    # other cruise lines such as MSC Cruises..." -- two real defects
    # compound here: "competition" (not "competitors") wasn't in the anchor
    # pattern at all, and even once widened, "operators such as" sits
    # between the anchor's verb and the first real name. Fixed by widening
    # COMPETITOR_ANCHORS's first pattern and adding _EXAMPLE_CUE.
    e12 = _extract_competitor(
        "Our primary competition includes operators such as Carnival and "
        "Royal Caribbean, as well as other cruise lines.")
    check("12o. 'primary competition includes' (not 'competitors') is "
          "recognized as an anchor phrase (real NCLH gap, fixed)",
          len(e12) > 0, str(e12))
    check("12p. and the descriptive-noun-phrase-then-'such as' preamble is "
          "skipped to reach the first two real names",
          {e.named_counterparty for e in e12}
          == {"Carnival", "Royal Caribbean"}, str(e12))

    # 12q: the SAME real NCLH sentence, in full, documents the accepted
    # residual limitation named in _extract_party_names's docstring -- a
    # SECOND, nested "such as" clause mid-list ("other cruise lines such as
    # MSC Cruises, Viking Ocean Cruises and Virgin Voyages") is not walked
    # into. Two real names recovered (up from zero) is the honest claim;
    # this pins it so a future change to _LIST_SEPARATOR is deliberate, not
    # an accidental silent behavior change either direction.
    e13 = _extract_competitor(
        "Our primary competition includes operators such as Carnival and "
        "Royal Caribbean, as well as other cruise lines such as MSC "
        "Cruises, Viking Ocean Cruises and Virgin Voyages.")
    check("12q. the nested second 'such as' clause is NOT walked into "
          "(documented limitation, not silently dropped or guessed at)",
          {e.named_counterparty for e in e13}
          == {"Carnival", "Royal Caribbean"}, str(e13))

    # 12r: the widened anchor still fails closed when nothing capitalized
    # genuinely follows -- "primary competition is intense" must not
    # fabricate a name out of "intense".
    e14 = _extract_competitor(
        "Our primary competition is intense and comes from many sources.")
    check("12r. 'primary competition is <lowercase>' yields nothing -- the "
          "widened anchor doesn't fabricate a name where none follows",
          e14 == [], str(e14))

    # 12s is the exact shape of a real recall gap found by the same
    # 24-anchor calibration: GME's 10-K names four real competitors in one
    # sentence, each followed by a parenthetical short-name annotation,
    # which previously broke the list walk after the very first name.
    e15 = _extract_competitor(
        "In the United States, we compete with Walmart Stores, Inc. "
        '("Walmart"), Target Corporation ("Target"), Best Buy Co., Inc. '
        '("Best Buy") and Amazon.com, Inc.')
    check("12s. a parenthetical short-name annotation after each list item "
          "no longer breaks the walk (real GME gap, fixed)",
          {e.named_counterparty for e in e15}
          == {"Walmart Stores, Inc", "Target Corporation", "Best Buy Co., Inc",
              "Amazon.com, Inc"}, str(e15))

    # 12t is the exact shape of a real defect found by the FIRST HISTORICAL
    # (multi-year) competitor walk, 2026-09-12: ADBE's 10-K lists
    # "...Apple, Autodesk, Avid, Corel, Microsoft, Quark..." and the
    # unbounded suffix alternative "Co" matched as a bare prefix of
    # "Corel" (no word boundary required), merging two names into one
    # malformed "Avid, Co" and silently dropping Corel, Microsoft and
    # Quark -- the list-walk's separator never got a chance to fire
    # because the capture had already consumed part of the token it
    # needed to see next. Fixed with \b after the suffix alternation.
    e16 = _extract_competitor(
        "Our competitors include offerings from companies such as Apple, "
        "Autodesk, Avid, Corel, Microsoft, Quark and others, as well as "
        "from many lower-cost providers.")
    check("12t. a company name immediately followed by another name "
          "starting with a corp-suffix PREFIX ('Corel' after 'Co') is not "
          "truncated or merged (real ADBE defect, fixed)",
          {e.named_counterparty for e in e16}
          == {"Apple", "Autodesk", "Avid", "Corel", "Microsoft", "Quark"},
          str(e16))

    # 12i previously asserted this function was NOT wired into
    # extract_for_universe -- true when this module was first added, and
    # deliberately re-checked here (grep the source, don't trust a comment)
    # rather than just deleted, so the switch from "not wired" to "wired"
    # is a visible, deliberate test change and not a silent drift. It
    # flipped 2026-09-12 on the strength of the calibration cited in the
    # module comment above COMPETITOR_ANCHORS: 0 false positives across 39
    # real edges, 24 real anchor filings, 3 independent real-evidence-driven
    # fix rounds.
    check("12i. this function IS now wired into extract_for_universe, on "
          "the strength of the 24-anchor calibration -- grep the source "
          "rather than trust a comment",
          "extract_competitor_edges_from_text" in
          __import__("inspect").getsource(
              __import__("hyp04_supply_chain_hedge.edgar_linkage",
                         fromlist=["extract_for_universe"]).extract_for_universe))


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
    test_6k_possessive_denominators_are_read_layer_by_layer()
    test_6l_the_verb_set_admits_equivalence_but_not_contribution()
    test_6m_the_widening_and_the_four_gates_it_required()
    test_6n_a_list_under_a_stated_denominator_is_unreadable()
    test_7_direction_inference()
    test_8_strip_markup()
    test_9_coverage_is_reported_as_a_floor()
    test_10_reconcile_flags_and_never_merges()
    test_11_offline()
    test_12_competitor_supplier_context_extraction()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 EDGAR EXTRACTOR TESTS PASSED")
    sys.exit(0)
