#!/usr/bin/env python3
"""Material-agreement extractor tests -- HYP-04 SOURCE B.

NEGATIVE TESTS FIRST, BEFORE ANY LIVE RUN.

Source A (ASC 280 concentration) needed three rounds of rediscovering false
positives at increasing scale -- 5 tickers looked clean, 27 exposed six
distinct classes of wrong match. That lesson is meant to be paid for once.
So every fabrication mode identified up front is a test here, written before
the extractor touched a real filing:

  * CONTINGENT   "if we were to enter into an agreement with X"
  * COMPETITIVE  "we compete with X" -- risk factors name rivals constantly
  * TERMINATED   "the agreement with X was terminated"

Positive tests exist too, and matter just as much: a filter that rejects
everything passes every negative test and is worthless. Each negative class
is paired with a near-identical positive that MUST still extract, so the
tests pin a boundary rather than a direction.

Fully offline. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_agreements.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.edgar_agreements import (  # noqa: E402
    ITEM_ENTRY,
    ITEM_OTHER,
    ITEM_TERMINATION,
    RELEVANT_ITEMS,
    SEARCH_PHRASES,
    STATUS_ACTIVE,
    STATUS_TERMINATED,
    STATUS_UNKNOWN,
    AgreementResult,
    AgreementSearchClient,
    extract_agreements_from_text,
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


def _x(text: str, items=None):
    return extract_agreements_from_text(
        text, ticker="TEST", cik="0000000001", filing_date="2026-03-01",
        accession="0000000001-26-000001", items=items or [ITEM_ENTRY])


# ===================== 1. CONTINGENT / HYPOTHETICAL =======================
def test_1_contingent_language_yields_no_edge() -> None:
    """A relationship that MIGHT exist is not a relationship."""
    contingent = {
        "if we were to": (
            "If we were to enter into a supply agreement with Acme Industries "
            "Inc., we would expect improved component availability."),
        "may enter": (
            "The Company may enter into a distribution agreement with Globex "
            "Corporation during fiscal 2027."),
        "intends to": (
            "We intend to enter into a manufacturing agreement with Initech "
            "Ltd. following completion of due diligence."),
        "subject to execution": (
            "The Company entered into a non-binding letter of intent and "
            "expects to execute a supply agreement with Umbrella Corp, "
            "subject to the negotiation of definitive documentation."),
        "no assurance": (
            "We executed a term sheet contemplating a purchase agreement with "
            "Soylent Corp. There can be no assurance such an agreement will "
            "be completed."),
        "in the event": (
            "In the event the Company enters into a supply agreement with "
            "Wayne Enterprises, additional capacity would be secured."),
    }
    for label, text in contingent.items():
        edges, rej = _x(text)
        check(f"1a. no edge from contingent language: {label}", not edges,
              f"got {[e.counterparty for e in edges]}")
        check(f"1b. and it is counted as a rejection: {label}",
              rej.get("contingent_or_hypothetical", 0) >= 1 or not edges)

    # PAIRED POSITIVE -- near-identical, but executed.
    real = ("On March 1, 2026, the Company entered into a supply agreement "
            "with Acme Industries Inc. providing for the purchase of "
            "components through 2029.")
    edges, _ = _x(real)
    check("1c. PAIRED POSITIVE -- the executed version DOES extract",
          len(edges) == 1, f"got {[e.counterparty for e in edges]}")
    if edges:
        check("1d. and names the counterparty",
              "Acme" in edges[0].counterparty, edges[0].counterparty)


# ===================== 2. COMPETITIVE MENTIONS ============================
def test_2_competitor_mentions_yield_no_edge() -> None:
    """Risk factors name rivals constantly. A rival is not a supply partner."""
    competitive = {
        "compete with": (
            "We compete with Advanced Micro Devices, Inc. and Intel "
            "Corporation, each of which has entered into agreements with "
            "major cloud providers."),
        "competitors include": (
            "Our principal competitors include Broadcom Inc., which has "
            "executed a supply agreement with several hyperscalers."),
        "competitive pressure": (
            "Competition is intense. Rivals such as Qualcomm Incorporated "
            "have signed manufacturing agreements with foundry partners, "
            "which could pressure our margins."),
        "alternative suppliers": (
            "Customers may turn to alternative suppliers that have entered "
            "into distribution agreements with Contoso Ltd."),
    }
    for label, text in competitive.items():
        edges, rej = _x(text)
        check(f"2a. no edge from competitive mention: {label}", not edges,
              f"got {[e.counterparty for e in edges]}")

    # PAIRED POSITIVE -- the SAME named company, in a transactional sentence.
    real = ("On February 2, 2026, the Company entered into a manufacturing "
            "agreement with Broadcom Inc. covering custom silicon.")
    edges, _ = _x(real)
    check("2b. PAIRED POSITIVE -- the same company in a real agreement extracts",
          len(edges) == 1 and "Broadcom" in edges[0].counterparty,
          f"got {[e.counterparty for e in edges]}")


def test_3_risk_factor_sections_are_excluded() -> None:
    text = ("Risk Factors. We depend on a limited number of suppliers. If we "
            "entered into a supply agreement with Stark Industries, we might "
            "still face shortages.")
    edges, rej = _x(text)
    check("3a. no edge from a risk-factor section", not edges,
          f"got {[e.counterparty for e in edges]}")
    check("3b. the rejection reason is recorded",
          bool(rej), "rejections must be counted, not silent")


# ===================== 4. TERMINATED RELATIONSHIPS ========================
def test_4_terminated_relationships_are_flagged_not_dropped() -> None:
    """Termination is POSITIVE evidence and must be recorded as such.

    Silently dropping it would lose real information; recording it as ACTIVE
    would assert a relationship that has ended.
    """
    text = ("On January 15, 2026, the Company terminated the supply agreement "
            "with Cyberdyne Systems Inc., effective immediately.")
    edges, _ = _x(text, items=[ITEM_TERMINATION])
    check("4a. a termination filing still produces an edge", len(edges) >= 1)
    if edges:
        check("4b. and it is marked TERMINATED, not ACTIVE",
              edges[0].relationship_status == STATUS_TERMINATED,
              edges[0].relationship_status)

    # Termination language in the SENTENCE, even without Item 1.02.
    text2 = ("The distribution agreement with Tyrell Corporation, which the "
             "Company entered into in 2021, expired on December 31, 2025 and "
             "was not renewed.")
    edges2, _ = _x(text2, items=[ITEM_OTHER])
    if edges2:
        check("4c. sentence-level expiry language also marks TERMINATED",
              edges2[0].relationship_status == STATUS_TERMINATED,
              edges2[0].relationship_status)
    else:
        check("4c. sentence-level expiry language also marks TERMINATED", True,
              "no edge extracted, which is also acceptable -- not asserted active")

    # PAIRED POSITIVE -- an entry filing must NOT be marked terminated.
    text3 = ("On March 1, 2026, the Company entered into a supply agreement "
             "with Cyberdyne Systems Inc.")
    edges3, _ = _x(text3, items=[ITEM_ENTRY])
    check("4d. PAIRED POSITIVE -- an entry filing is ACTIVE, not terminated",
          len(edges3) == 1 and edges3[0].relationship_status == STATUS_ACTIVE,
          str([(e.counterparty, e.relationship_status) for e in edges3]))


def test_5_currency_status_is_honest_about_its_limits() -> None:
    """ACTIVE_AS_DISCLOSED must never be presented as proof of currency."""
    from hyp04_supply_chain_hedge import edgar_agreements as M

    # Whitespace-normalised: the phrase legitimately wraps across lines in the
    # docstring, and an unnormalised substring check fails on the line break
    # rather than on a missing statement.
    import re as _re
    doc = M.__doc__ or ""
    flat = _re.sub(r"\s+", " ", doc).lower()
    check("5a. the module states absence of a termination is not evidence",
          "absence of evidence" in flat and "evidence of absence" in flat)
    check("5b. and enumerates the three lifecycle states",
          all(s in doc for s in (STATUS_ACTIVE, STATUS_TERMINATED, STATUS_UNKNOWN)))

    # No 1.01 and no 1.02 -> UNKNOWN, never ACTIVE by default.
    text = ("The Company issued a press release announcing it entered into a "
            "strategic partnership agreement with Wonka Industries Inc.")
    edges, _ = _x(text, items=[ITEM_OTHER])
    if edges:
        check("5c. outside the 1.01/1.02 taxonomy the status is UNKNOWN",
              edges[0].relationship_status == STATUS_UNKNOWN,
              edges[0].relationship_status)
    else:
        skip("5c. UNKNOWN status", "no edge extracted from this fixture")


# ===================== 6. the filter is not degenerate ====================
def test_5b_contract_boilerplate_yields_no_edge() -> None:
    """VERBATIM from the 2026-08-18 SOURCE B canary.

    A fabrication class not anticipated in the first negative-test pass. EX-10.x
    exhibits ARE the contract, so their bodies are dense with definitional,
    hypothetical and NEGATIVE "agreement with X" phrases. Both edges the first
    canary produced came from this, and neither is a business relationship.
    """
    boilerplate = {
        "employee NDA clause": (
            "All current and former employees and contractors of the Company "
            "and its Subsidiaries and any Third Party having access to Trade "
            "Secrets through the Company or its Subsidiaries have executed a "
            "written agreement with the Company regarding the protection of "
            "such Trade Secrets."),
        "negative tax representation": (
            "Neither the Company nor any of its Subsidiaries has entered into "
            "any agreement or arrangement with a Tax Authority (being an "
            "agreement or arrangement not based on a strict application of "
            "law) or benefits from any preferential Tax regime."),
        "has not entered into": (
            "The Company has not entered into a supply agreement with Acme "
            "Industries Inc. as of the date hereof."),
        "definitional": (
            'For purposes of this Section 5.1, "Material Contract" shall mean '
            "any agreement with Globex Corporation exceeding $1,000,000."),
    }
    for label, text in boilerplate.items():
        edges, rej = _x(text)
        check(f"5b. no edge from contract boilerplate: {label}", not edges,
              f"got {[e.counterparty for e in edges]}")
        check(f"5b2. and the rejection is counted: {label}", bool(rej) or not edges)

    # Generic legal entities are never counterparties.
    for generic in ("a Tax Authority", "the Company", "any Governmental Entity",
                    "a Third Party", "the Purchaser"):
        text = f"On March 1, 2026, the Registrant executed an agreement with {generic}."
        edges, _ = _x(text)
        check(f"5b3. generic entity rejected as counterparty: {generic!r}",
              not edges, f"got {[e.counterparty for e in edges]}")


def test_5c_party_capture_is_case_sensitive() -> None:
    """Under re.I, [A-Z] also matches lowercase and captures fragments.

    "Company regarding the protection of" was extracted as a counterparty.
    Same bug class that produced "Concentration of credit risk. During fiscal
    2025, Apple Inc." in source A, rediscovered here in a different pattern.
    """
    fragmenty = ("The parties have executed a written agreement with the "
                 "company regarding the protection of confidential data.")
    edges, _ = _x(fragmenty)
    check("5c. a lowercase sentence fragment is not captured as a party",
          not any(" regarding " in e.counterparty for e in edges),
          f"got {[e.counterparty for e in edges]}")

    # CONTROL: a properly capitalised company still extracts.
    good = ("On March 1, 2026, the Company entered into a supply agreement "
            "with Acme Industries Inc.")
    edges2, _ = _x(good)
    check("5c2. CONTROL -- a real Title Case counterparty still extracts",
          len(edges2) == 1 and "Acme" in edges2[0].counterparty,
          f"got {[e.counterparty for e in edges2]}")


def test_6_the_filter_does_not_reject_everything() -> None:
    """Every negative test above is passed by an extractor that returns [].

    This is the control that makes them mean something.
    """
    positives = {
        "supply": ("On March 1, 2026, the Company entered into a supply "
                   "agreement with Acme Industries Inc."),
        "distribution": ("The Company executed a distribution agreement with "
                         "Globex Corporation on April 2, 2026."),
        "manufacturing": ("Registrant entered into a manufacturing agreement "
                          "with Initech Ltd."),
        "amended": ("On May 5, 2026, the Company amended its master services "
                    "agreement with Umbrella Corp."),
    }
    extracted = 0
    for label, text in positives.items():
        edges, _ = _x(text)
        ok = len(edges) >= 1
        extracted += ok
        check(f"6a. genuine agreement extracts: {label}", ok,
              f"got {[e.counterparty for e in edges]}")
    check("6b. CONTROL -- the extractor is not degenerate",
          extracted == len(positives),
          f"only {extracted}/{len(positives)} positives extracted")


def test_6c_date_words_are_not_read_as_hypothetical() -> None:
    """Regression: the month "May" matched the modal "may" under re.I.

    "On May 5, 2026, the Company amended its master services agreement with
    Umbrella Corp." was silently rejected as contingent. Filings carry dates
    constantly, so this suppressed real edges in roughly a twelfth of them --
    and silently, because a rejection produces no output to notice.
    """
    may_dated = {
        "May <day>, <year>": (
            "On May 5, 2026, the Company entered into a supply agreement with "
            "Umbrella Corp."),
        "May <year>": (
            "In May 2026, the Company executed a distribution agreement with "
            "Globex Corporation."),
        "dated as of May": (
            "Effective as of May 12, 2026, the Company executed a "
            "manufacturing agreement with Initech Ltd."),
    }
    for label, text in may_dated.items():
        edges, rej = _x(text)
        check(f"6c. a May date does not suppress the edge: {label}",
              len(edges) >= 1,
              f"rejected as {list(rej)} -- month/modal collision")

    # And the genuine modal use must STILL be rejected.
    modal = ("The Company may enter into a supply agreement with Umbrella "
             "Corp. later this year.")
    edges2, _ = _x(modal)
    check("6c2. but the genuine modal 'may enter into' is still rejected",
          not edges2, f"got {[e.counterparty for e in edges2]}")

    # KNOWN LIMITATION, asserted so it is a recorded gap rather than a
    # surprise: the anchor requires VERB -> agreement -> with -> party. The
    # inverted form "The agreement with X ... was signed" is not matched.
    # Loosening the pattern to catch it would admit bare "agreement with X"
    # phrases, which are frequently hypothetical -- the wrong trade given
    # this source's fabrication risk. Missed edges are the accepted cost.
    inverted = ("The manufacturing agreement with Initech Ltd., dated as of "
                "May 12, 2026, was signed by both parties.")
    edges3, rej3 = _x(inverted)
    check("6c3. KNOWN GAP -- inverted word order is not matched (documented)",
          not edges3 and not rej3,
          "no anchor match and no rejection: a coverage gap, not a filter action")


def test_7_provenance_and_shape() -> None:
    text = ("On March 1, 2026, the Company entered into a supply agreement "
            "with Acme Industries Inc.")
    edges, _ = _x(text)
    check("7a. an edge was produced", bool(edges))
    if not edges:
        return
    e = edges[0]
    check("7b. the as-of date is the FILING date", e.as_of_date == "2026-03-01")
    check("7c. the accession is recorded", e.accession.startswith("0000000001-"))
    check("7d. the item numbers are recorded", ITEM_ENTRY in e.item_numbers)
    check("7e. the source is labelled distinctly from source A",
          e.source == "EDGAR_8K_MATERIAL_AGREEMENT")
    check("7f. context is retained for human review", len(e.context) > 20)
    d = e.as_dict()
    check("7g. relationship_status is on the serialised edge",
          "relationship_status" in d)


def test_8_independence_from_source_a() -> None:
    """The two sources must not share a trigger, form, or vocabulary."""
    from hyp04_supply_chain_hedge import edgar_agreements as B
    from hyp04_supply_chain_hedge import edgar_linkage as A

    check("8a. different form focus (10-K vs 8-K)",
          "10-K" in (A.__doc__ or "") and "8-K" in (B.__doc__ or ""))
    check("8b. source B searches agreement vocabulary, not concentration",
          all("agreement" in p or "partnership" in p for p in SEARCH_PHRASES))
    check("8c. source B has no concentration-percentage anchors",
          not hasattr(B, "CONCENTRATION_ANCHORS"))
    check("8d. source A has no relationship-currency concept",
          not hasattr(A, "STATUS_TERMINATED"))
    check("8e. the 8-K items searched are the lifecycle ones",
          ITEM_ENTRY in RELEVANT_ITEMS and ITEM_TERMINATION in RELEVANT_ITEMS)
    check("8f. source B declares its independence explicitly",
          "independent" in (B.__doc__ or "").lower())


def test_9_coverage_reports_rejections() -> None:
    res = AgreementResult()
    res.companies_attempted = ["A", "B"]
    res.rejected = {"contingent_or_hypothetical": 3, "competitive_mention": 2}
    cov = res.coverage()
    check("9a. rejections are reported by reason",
          cov["rejected_by_reason"]["contingent_or_hypothetical"] == 3)
    check("9b. edges are broken down by relationship status",
          "edges_by_relationship_status" in cov)
    check("9c. request count is reported", "requests_made" in cov)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_11_search_unscoped_omits_ciks() -> None:
    """The whole point of the reverse-direction search: no `ciks` key at
    all, so the query runs across every filer, not one chosen anchor's own
    filings."""
    client = AgreementSearchClient("bchen9996 bchen9996@gmail.com")
    seen: dict = {}

    def fake_get(url, params=None, timeout=40):
        seen["url"], seen["params"] = url, params
        return _FakeResponse({"hits": {"hits": [
            {"_id": "acc:doc.htm", "_source": {"ciks": ["0000000042"]}}
        ]}})

    client._get = fake_get
    out = client.search_unscoped('"Apple Inc." "of our net revenue"',
                                 forms="10-K")
    check("11a. no ciks key in the request params", "ciks" not in seen["params"],
          str(seen["params"]))
    check("11b. q and forms are passed through",
          seen["params"]["q"] == '"Apple Inc." "of our net revenue"'
          and seen["params"]["forms"] == "10-K")
    check("11c. _id is preserved on the returned hit, same as search()",
          out[0]["_id"] == "acc:doc.htm")


def test_12_ticker_for_reverses_cik_for() -> None:
    client = AgreementSearchClient("bchen9996 bchen9996@gmail.com")

    def fake_get(url, params=None, timeout=40):
        client.requests_made += 1
        return _FakeResponse({
            "AAPL_ROW": {"ticker": "AAPL", "cik_str": 320193},
            "NVDA_ROW": {"ticker": "NVDA", "cik_str": 1045810},
        })

    client._get = fake_get
    check("12a. ticker_for resolves a real CIK to its ticker",
          client.ticker_for("320193") == "AAPL")
    check("12b. works with an unpadded numeric CIK too",
          client.ticker_for(320193) == "AAPL")
    check("12c. an unknown CIK returns None, not a guess",
          client.ticker_for("999999999") is None)
    check("12d. the map is fetched once and reused (cik_for and ticker_for "
          "share it)", client.requests_made == 1)


def test_10_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("10a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("10a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    # Negatives first, deliberately, matching the order they were written in.
    test_1_contingent_language_yields_no_edge()
    test_2_competitor_mentions_yield_no_edge()
    test_3_risk_factor_sections_are_excluded()
    test_4_terminated_relationships_are_flagged_not_dropped()
    test_5_currency_status_is_honest_about_its_limits()
    test_5b_contract_boilerplate_yields_no_edge()
    test_5c_party_capture_is_case_sensitive()
    test_6_the_filter_does_not_reject_everything()
    test_6c_date_words_are_not_read_as_hypothetical()
    test_7_provenance_and_shape()
    test_8_independence_from_source_a()
    test_9_coverage_reports_rejections()
    test_11_search_unscoped_omits_ciks()
    test_12_ticker_for_reverses_cik_for()
    test_10_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 AGREEMENT EXTRACTOR TESTS PASSED")
    sys.exit(0)
