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
    CONTACT_REQUIRED_MESSAGE,
    DIRECTION_CUSTOMER,
    DIRECTION_SUPPLIER,
    EdgarClient,
    EdgarContactError,
    ExtractionResult,
    LinkageEdge,
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
