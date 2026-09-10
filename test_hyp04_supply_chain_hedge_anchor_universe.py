#!/usr/bin/env python3
"""Tests for the HYP-04 anchor-universe RULE.

The module under test exists to stop a universe being chosen after seeing
which tickers turned out to have usable linkage edges. So the tests have to
establish something stronger than "it returns MCK": they have to establish
that the member list is COMPUTED.

Three properties carry the weight.

  1. THE MEMBERS ARE DERIVED, NOT NAMED (test_2). A fabricated screen in which
     a completely different ticker carries the qualifying disclosure must
     return THAT ticker and not the real one. A function with the answer
     hardcoded passes every test that only ever feeds it the real data.

  2. THE RULE CANNOT SEE WHO SURVIVED (test_6). Membership must not depend on
     whether the counterparty still exists or whether prices are obtainable.
     PKG's counterparty ODP delisted in 2026 and its whole price history is
     gone from the provider used here; a universe that dropped anchors for
     that reason would be survivorship-selected, and the pairs it dropped
     would be exactly the ones where the relationship ended in an acquisition.
     The test adds availability fields to an edge and requires the outcome to
     be byte-identical.

  3. A SCREEN THAT CANNOT BE EVALUATED IS REFUSED, NOT SCORED (test_7). The
     published 2026-08-26 screen predates the denominator field. Evaluating it
     would read every absent denominator as a denial and produce an EMPTY
     universe -- which is indistinguishable, from the outside, from a real
     finding that nothing qualifies. It is still on disk and is used here as
     the regression fixture.

Offline. No network. Nothing is written.

Run directly: python test_hyp04_supply_chain_hedge_anchor_universe.py
"""
from __future__ import annotations

import copy
import json
import socket
import sys
from datetime import date
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.anchor_universe import (  # noqa: E402
    ANNUAL_REPORT_FORM_PREFIX,
    derive_universe_point_in_time,
    format_point_in_time_report,
    CONCENTRATION_THRESHOLD_PCT,
    CONDITIONS,
    LSE,
    NEVER_CONDITIONS,
    REQUIRED_BASIS,
    REQUIRED_EDGE_FIELDS,
    RULE_ID,
    derive_universe,
    evaluate_ticker,
    format_report,
    screening_frame,
)
from hyp04_supply_chain_hedge.edgar_linkage import (  # noqa: E402
    BASIS_CONSOLIDATED_REVENUE,
    BASIS_RECEIVABLES,
    BASIS_SEGMENT_REVENUE,
    BASIS_UNKNOWN,
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


CUTOFF = "2026-08-26"
FRAME = ("AAA", "BBB", "CCC")


def _edge(ticker="AAA", **over):
    e = {
        "reporting_company": ticker,
        "reporting_cik": "0000000001",
        "named_counterparty": "Acme Holdings Inc.",
        "counterparty_is_named": True,
        "direction": "customer",
        "concentration_pct": 24.0,
        "concentration_basis": BASIS_CONSOLIDATED_REVENUE,
        "concentration_basis_text": "our total consolidated revenues",
        "as_of_date": "2026-05-08",
        "accession": "0000000001-26-000001",
        "form": "10-K",
    }
    e.update(over)
    return e


def _screen(edges, *, attempted=len(FRAME)):
    return {"generated_at_utc": "2026-08-26T00:00:00+00:00",
            "coverage": {"companies_attempted": attempted},
            "edges": list(edges)}


# ==========================================================================
def test_1_a_valid_disclosure_qualifies() -> None:
    """The load-bearing POSITIVE case. A rule that only ever denies is
    satisfied by a function that returns False."""
    d = derive_universe(_screen([_edge()]), cutoff_date=CUTOFF, frame=FRAME)
    check("1a. the derivation is not refused", d.derived, str(d.refusals))
    check("1b. the qualifying ticker is a member", d.members == ("AAA",),
          str(d.members))
    check("1c. the whole frame is evaluated, not just the ones with edges",
          len(d.qualifications) == len(FRAME), str(len(d.qualifications)))
    check("1d. the rule id is recorded", d.rule_id == RULE_ID, d.rule_id)
    q = next(q for q in d.qualifications if q.ticker == "AAA")
    ev = q.evidence["qualifying_disclosures"]
    check("1e. the qualifying disclosure is kept as evidence", len(ev) == 1)
    check("1f. with the accession that carries it",
          ev and ev[0]["accession"] == "0000000001-26-000001")
    check("1g. and the filing's own denominator wording",
          ev and ev[0]["concentration_basis_text"]
          == "our total consolidated revenues")


def test_2_the_member_list_is_computed_not_hardcoded() -> None:
    """HARDCODED-OPEN CONTROL.

    Move the qualifying disclosure onto a different ticker. If the answer were
    baked in, the rule would still return the ticker it was written around.
    """
    d = derive_universe(_screen([_edge(ticker="CCC")]),
                        cutoff_date=CUTOFF, frame=FRAME)
    check("2a. the OTHER ticker qualifies", d.members == ("CCC",), str(d.members))

    # And with no qualifying disclosure anywhere, the universe is EMPTY --
    # not defaulted to anything.
    d0 = derive_universe(_screen([]), cutoff_date=CUTOFF, frame=FRAME)
    check("2b. an empty screen yields an empty universe", d0.members == (),
          str(d0.members))
    check("2c. which is still a completed derivation, not a refusal",
          d0.derived, str(d0.refusals))

    # Two qualifying tickers -> two members. A rule capped at one would pass
    # both tests above.
    d2 = derive_universe(_screen([_edge(ticker="AAA"), _edge(ticker="BBB")]),
                         cutoff_date=CUTOFF, frame=FRAME)
    check("2d. two qualifying tickers give two members",
          d2.members == ("AAA", "BBB"), str(d2.members))


def test_3_each_condition_denies_on_its_own() -> None:
    """AU-1 .. AU-6, falsified one at a time against an otherwise valid edge."""
    def denied(label, **over):
        e = _edge(**over)
        q = evaluate_ticker("AAA", [e], cutoff_date=CUTOFF, frame=FRAME)
        check(label, not q.qualifies, f"qualified anyway: {q.evidence}")
        return q

    q1 = evaluate_ticker("ZZZ", [_edge(ticker="ZZZ")],
                         cutoff_date=CUTOFF, frame=FRAME)
    check("3a. AU-1: a ticker outside the frame never qualifies",
          not q1.qualifies, str(q1.denials))
    check("3b. and says so", any("AU-1" in d for d in q1.denials),
          str(q1.denials))

    q2 = evaluate_ticker("BBB", [_edge()], cutoff_date=CUTOFF, frame=FRAME)
    check("3c. AU-2: a ticker with no screened filing does not qualify",
          not q2.qualifies and any("AU-2" in d for d in q2.denials),
          str(q2.denials))
    denied("3d. AU-2: a non-annual form does not qualify", form="8-K")

    denied("3e. AU-3: an unnamed counterparty does not qualify",
           counterparty_is_named=False, named_counterparty=None)
    denied("3f. AU-3: a blank name does not qualify", named_counterparty="   ")

    denied("3g. AU-4: a SEGMENT denominator does not qualify",
           concentration_basis=BASIS_SEGMENT_REVENUE, concentration_pct=58.0)
    denied("3h. AU-4: a RECEIVABLES denominator does not qualify",
           concentration_basis=BASIS_RECEIVABLES, concentration_pct=21.0)
    denied("3i. AU-4: an UNRECOGNISED denominator does not qualify",
           concentration_basis=BASIS_UNKNOWN, concentration_pct=90.0)

    denied("3j. AU-5: below the threshold does not qualify",
           concentration_pct=CONCENTRATION_THRESHOLD_PCT - 0.1)
    denied("3k. AU-5: a non-numeric concentration does not qualify",
           concentration_pct=None)

    denied("3l. AU-6: a malformed filing date does not qualify",
           as_of_date="8 May 2026")
    denied("3m. AU-6: a filing AFTER the cutoff does not qualify",
           as_of_date="2026-08-27")

    bad = evaluate_ticker("AAA", [_edge()], cutoff_date="not-a-date", frame=FRAME)
    check("3n. AU-6: a malformed cutoff denies rather than being guessed at",
          not bad.qualifies, str(bad.denials))


def test_4_boundaries() -> None:
    """Every threshold in the rule, checked at its edge in both directions."""
    def q(**over):
        return evaluate_ticker("AAA", [_edge(**over)],
                               cutoff_date=CUTOFF, frame=FRAME).qualifies

    check("4a. exactly the threshold QUALIFIES (ASC 280 says '10 percent or "
          "more')", q(concentration_pct=CONCENTRATION_THRESHOLD_PCT))
    check("4b. a hair under does not",
          not q(concentration_pct=CONCENTRATION_THRESHOLD_PCT - 0.1))

    # The cutoff is inclusive: a filing made ON the cutoff date was knowable
    # by the cutoff. This is a DIFFERENT question from pair_eligibility's
    # strict `as_of_date < event_date`, which guards look-ahead at an event.
    check("4c. filed ON the cutoff qualifies", q(as_of_date=CUTOFF))
    check("4d. filed one day after does not", not q(as_of_date="2026-08-27"))

    check("4e. a 10-K/A amendment is still an annual report",
          q(form="10-K/A"))


def test_5_denials_accumulate_and_are_specific() -> None:
    e = _edge(concentration_pct=4.0, concentration_basis=BASIS_SEGMENT_REVENUE)
    q = evaluate_ticker("AAA", [e], cutoff_date=CUTOFF, frame=FRAME)
    check("5a. it does not qualify", not q.qualifies)
    near = q.evidence["near_misses"]
    check("5b. the near miss is kept, not discarded", len(near) == 1)
    if near:
        why = near[0]["denials"]
        check("5c. BOTH failures are reported, not just the first",
              any("AU-4" in w for w in why) and any("AU-5" in w for w in why),
              str(why))
        check("5d. the denial names the denominator it actually saw",
              any(BASIS_SEGMENT_REVENUE in w for w in why), str(why))

    txt = format_report(derive_universe(_screen([e]), cutoff_date=CUTOFF,
                                        frame=FRAME))
    check("5e. the report shows what was screened and rejected",
          "SCREENED BUT NOT QUALIFYING" in txt)
    check("5f. and disclaims opening anything",
          "creates no" in txt and "display-gate" in txt)


def test_6_membership_cannot_depend_on_survival() -> None:
    """THE ANTI-SURVIVORSHIP PROPERTY.

    ODP -- PKG's disclosed counterparty -- stopped being a public filer in
    2026, and the provider used for peer closes retains no history for it. If
    membership could see that, the universe would systematically lose the
    anchors whose counterparty was acquired, and acquisition is often caused
    by the very relationship being studied.

    So: attach every availability signal an implementer might reach for, and
    require the outcome to be unchanged. This test fails the moment someone
    adds such a condition.
    """
    plain = _edge()
    loaded = _edge(
        counterparty_delisted=True,
        counterparty_still_public=False,
        peer_price_history_available=False,
        peer_price_rows=0,
        relationship_still_current=False,
        counterparty_acquired_by="Some Acquirer Inc.",
    )
    a = evaluate_ticker("AAA", [plain], cutoff_date=CUTOFF, frame=FRAME)
    b = evaluate_ticker("AAA", [loaded], cutoff_date=CUTOFF, frame=FRAME)
    check("6a. the delisted-counterparty edge still qualifies", b.qualifies,
          str(b.denials))
    check("6b. and the qualification is identical to the plain one",
          a.qualifies == b.qualifies and a.denials == b.denials,
          f"{a.denials} vs {b.denials}")

    check("6c. the rejected conditions are recorded, not merely omitted",
          len(NEVER_CONDITIONS) >= 4, str(len(NEVER_CONDITIONS)))
    check("6d. each rejected condition carries its reason",
          all(len(reason) > 80 for _, reason in NEVER_CONDITIONS))
    joined = " ".join(r for _, r in NEVER_CONDITIONS).lower()
    check("6e. survivorship is named as the reason", "survivorship" in joined)
    check("6f. and 'not missing at random' is the argument, not inconvenience",
          "missing at random" in joined)
    check("6g. the locked 24 is explicitly NOT a membership condition",
          any("locked" in name.lower() for name, _ in NEVER_CONDITIONS),
          str([n for n, _ in NEVER_CONDITIONS]))


def test_7_an_unevaluable_screen_is_refused() -> None:
    """A refusal and an empty universe must not look the same."""
    stale = _screen([{k: v for k, v in _edge().items()
                      if k != "concentration_basis"}])
    d = derive_universe(stale, cutoff_date=CUTOFF, frame=FRAME)
    check("7a. a screen without the denominator is refused", not d.derived)
    check("7b. the refusal names the missing field",
          any("concentration_basis" in r for r in d.refusals), str(d.refusals))
    check("7c. and explains why an empty universe would be misread",
          any("looks like a finding" in r for r in d.refusals), str(d.refusals))
    check("7d. a refused derivation yields NO members", d.members == (),
          str(d.members))

    # HARDCODED-CLOSED CONTROL: the same screen WITH the field derives.
    ok = derive_universe(_screen([_edge()]), cutoff_date=CUTOFF, frame=FRAME)
    check("7e. the same screen with the field present is not refused",
          ok.derived and ok.members == ("AAA",), str(ok.refusals))

    # Fail-closed even when a perfectly good edge is present alongside.
    mixed = _screen([_edge(),
                     {k: v for k, v in _edge(ticker="BBB").items()
                      if k != "concentration_basis"}])
    dm = derive_universe(mixed, cutoff_date=CUTOFF, frame=FRAME)
    check("7f. one unevaluable edge refuses the WHOLE derivation",
          not dm.derived and dm.members == (), str(dm.members))

    d2 = derive_universe(_screen([_edge()], attempted=99),
                         cutoff_date=CUTOFF, frame=FRAME)
    check("7g. a screen that covered a different number of companies is refused",
          not d2.derived and any("frame" in r for r in d2.refusals),
          str(d2.refusals))

    d3 = derive_universe(_screen([_edge(ticker="ZZZ")]),
                         cutoff_date=CUTOFF, frame=FRAME)
    check("7h. a screen reaching outside the frame is refused",
          not d3.derived and any("outside the frame" in r for r in d3.refusals),
          str(d3.refusals))

    d4 = derive_universe({"coverage": {}}, cutoff_date=CUTOFF, frame=FRAME)
    check("7i. a screen with no edges list is refused", not d4.derived,
          str(d4.refusals))


def test_8_the_frame_is_derived_and_predates_the_rule() -> None:
    frame = screening_frame()
    from hyp04_supply_chain_hedge.run_canary_audit import (
        LOCKED_24_ANCHORS, candidate_peer_universe)
    expected = frozenset(LOCKED_24_ANCHORS) | frozenset(candidate_peer_universe())
    check("8a. the frame is read from the pre-existing lists, not restated",
          frame == expected, f"{len(frame)} vs {len(expected)}")
    check("8b. it is bigger than any plausible answer", len(frame) > 40,
          str(len(frame)))
    check("8c. the locked 24 are all inside it",
          frozenset(LOCKED_24_ANCHORS) <= frame)
    check("8d. MCK and PKG are in the frame -- they are candidates, not the "
          "definition", {"MCK", "PKG"} <= frame)

    # A frame equal to the answer would make the rule decorative.
    d = derive_universe(_screen([_edge()]), cutoff_date=CUTOFF, frame=FRAME)
    check("8e. members are a strict subset of the frame, never equal to it",
          set(d.members) < set(FRAME), f"{d.members} vs {FRAME}")


def test_9_the_published_stale_screen_is_the_regression_fixture() -> None:
    """Point the refusal at the REAL artifact it was written for."""
    stale = LSE / "HYP04_EDGAR_CANDIDATE_LINKAGE_FULL51_2026-08-26.json"
    if not stale.is_file():
        skip("9. published 2026-08-26 screen present", f"{stale.name} absent")
        return
    doc = json.loads(stale.read_text(encoding="utf-8-sig"))
    d = derive_universe(doc, cutoff_date=CUTOFF)
    check("9a. the published pre-denominator screen is refused", not d.derived,
          str(d.refusals))
    check("9b. for the reason it was written for",
          any("concentration_basis" in r for r in d.refusals), str(d.refusals))
    check("9c. and produces no universe", d.members == (), str(d.members))
    check("9d. its edge count is unchanged on disk",
          len(doc.get("edges", [])) == 39, str(len(doc.get("edges", []))))

    # Backfilling the field by hand must not be how this gets resolved, but if
    # a caller does it the rule still has to be right. MCK's consolidated 24%
    # qualifies; PKG's 58%-of-segment does not.
    patched = copy.deepcopy(doc)
    for e in patched["edges"]:
        text = (e.get("context") or "")
        if "Paper segment" in text:
            e["concentration_basis"] = BASIS_SEGMENT_REVENUE
        elif "total consolidated revenues" in text and e.get("concentration_pct") == 24.0:
            e["concentration_basis"] = BASIS_CONSOLIDATED_REVENUE
        else:
            e["concentration_basis"] = BASIS_UNKNOWN
    dp = derive_universe(patched, cutoff_date=CUTOFF)
    check("9e. with denominators supplied, the derivation completes", dp.derived,
          str(dp.refusals))
    check("9f. MCK qualifies on its consolidated-revenue disclosure",
          "MCK" in dp.members, str(dp.members))
    check("9g. PKG does NOT -- 58% is of the Paper SEGMENT, not the entity",
          "PKG" not in dp.members, str(dp.members))


def test_10_the_rule_declares_what_it_is() -> None:
    ids = [c for c, _ in CONDITIONS]
    check("10a. the conditions are ordered and complete",
          ids == ["AU-1", "AU-2", "AU-3", "AU-4", "AU-5", "AU-6"], str(ids))
    check("10b. every condition carries a description",
          all(len(t) > 20 for _, t in CONDITIONS))
    check("10c. the threshold is ASC 280's, not a tuned one",
          CONCENTRATION_THRESHOLD_PCT == 10.0, str(CONCENTRATION_THRESHOLD_PCT))
    check("10d. the required denominator is the entity-wide one",
          REQUIRED_BASIS == BASIS_CONSOLIDATED_REVENUE, REQUIRED_BASIS)
    check("10e. the annual-report form prefix is stated",
          ANNUAL_REPORT_FORM_PREFIX == "10-K")
    check("10f. every field the rule reads is declared as required",
          "concentration_basis" in REQUIRED_EDGE_FIELDS
          and "concentration_pct" in REQUIRED_EDGE_FIELDS
          and "as_of_date" in REQUIRED_EDGE_FIELDS)

    src = Path(__import__("hyp04_supply_chain_hedge.anchor_universe",
                          fromlist=["x"]).__file__).read_text(encoding="utf-8")
    flat = " ".join(src.split())
    check("10g. the module states it opens no gate",
          "The gate stays CLOSED" in flat)
    check("10h. and that membership creates no eligible anchor event",
          "produces no such record for anybody" in flat)
    check("10i. and disclaims being evidence",
          "NOTHING HERE IS EVIDENCE ABOUT SUPPLY-CHAIN TRANSMISSION" in flat)



# ==========================================================================
# POINT-IN-TIME evaluation
# ==========================================================================
def _filing(date_, *, disclosures=None, acc=None):
    # extract_edges_from_text stamps every edge with the filing date it was
    # given, so an edge's as_of_date IS its filing's date. The fixture has to
    # do the same or AU-6 denies every historical filing for carrying a
    # future-dated disclosure -- which is the rule working, not a bug.
    disclosures = [{**d, "as_of_date": date_} for d in (disclosures or [])]
    return {"filing_date": date_, "accession": acc or ("acc-" + date_),
            "form": "10-K", "edges_found": len(disclosures or []),
            "named_counterparties": sorted(
                {d["named_counterparty"] for d in (disclosures or [])
                 if d.get("counterparty_is_named")}),
            "explicit_no_concentration": False,
            "disclosures": list(disclosures or [])}


def _history(records):
    return {"artifact": "test", "per_filing_carries_disclosures": True,
            "tickers": list(records)}


def _tickrec(ticker, filings, **over):
    rec = {"ticker": ticker, "cik": "0000000001",
           "filings_on_record": len(filings), "filings_examined": len(filings),
           "filings_failed": [], "stopped_early_reason": None, "error": None,
           "per_filing": list(filings)}
    rec.update(over)
    return rec


def _no_disclosures(f):
    return {k: v for k, v in f.items() if k != "disclosures"}


def test_13_the_rule_is_evaluated_against_the_filing_in_force() -> None:
    """THE CASE THE ONE-SHOT SCREEN CANNOT PRODUCE.

    A company that disclosed a qualifying concentration from 2015 to 2019 and
    then stopped is invisible to `derive_universe`, which reads only the newest
    10-K. It must be visible here -- otherwise membership is filtered by
    whether the relationship survived to the present day, which is the same
    selection the peer-data policy forbids one level down.
    """
    good = _edge(ticker="AAA")
    hist = _history([_tickrec("AAA", [
        _filing("2014-03-01"),                       # nothing disclosed
        _filing("2015-03-01", disclosures=[good]),   # qualifies
        _filing("2016-03-01", disclosures=[good]),
        _filing("2017-03-01"),                       # stopped
        _filing("2018-03-01"),
    ])])
    u = derive_universe_point_in_time(hist, frame=("AAA",))
    check("13a. the derivation is not refused", u.derived, str(u.refusals))
    check("13b. the ticker IS a member although the NEWEST filing does not "
          "qualify", u.members_ever == ("AAA",), str(u.members_ever))
    check("13c. exactly one interval", len(u.intervals) == 1,
          str([(i.start_date, i.end_date) for i in u.intervals]))
    if u.intervals:
        iv = u.intervals[0]
        check("13d. it starts at the FIRST qualifying filing, not the last",
              iv.start_date == "2015-03-01", iv.start_date)
        check("13e. and ends at the filing that stopped qualifying",
              iv.end_date == "2017-03-01", str(iv.end_date))
        check("13f. counting the filings that qualified",
              iv.filings_qualifying == 2, str(iv.filings_qualifying))
        check("13g. carrying the accession that opened it",
              iv.start_accession == "acc-2015-03-01", iv.start_accession)

    # CONTROL: the one-shot screen sees nothing here, because it reads only
    # the newest filing. This is the gap the point-in-time pass exists to fill.
    one_shot = derive_universe(_screen([]), cutoff_date=CUTOFF, frame=FRAME)
    check("13h. CONTROL -- the newest-filing screen finds no member",
          one_shot.members == (), str(one_shot.members))


def test_14_intervals_open_close_and_repeat() -> None:
    good = _edge(ticker="AAA")
    hist = _history([_tickrec("AAA", [
        _filing("2015-03-01", disclosures=[good]),
        _filing("2016-03-01"),                       # lapse
        _filing("2017-03-01", disclosures=[good]),   # resumes
        _filing("2018-03-01", disclosures=[good]),
    ])])
    u = derive_universe_point_in_time(hist, frame=("AAA",))
    spans = [(i.start_date, i.end_date) for i in u.intervals]
    check("14a. a lapse and a resumption give TWO intervals, not one span",
          len(u.intervals) == 2, str(spans))
    check("14b. the first closes at the lapse",
          bool(spans) and spans[0] == ("2015-03-01", "2016-03-01"), str(spans))
    check("14c. the second is still open at the newest filing",
          len(spans) > 1 and spans[1] == ("2017-03-01", None), str(spans))

    # HARDCODED-OPEN CONTROL: move the qualifying filing to another ticker.
    hist2 = _history([
        _tickrec("AAA", [_filing("2015-03-01")]),
        _tickrec("CCC", [_filing("2015-03-01",
                                 disclosures=[_edge(ticker="CCC")])]),
    ])
    u2 = derive_universe_point_in_time(hist2, frame=("AAA", "CCC"))
    check("14d. the intervals follow the data, not a hardcoded ticker",
          u2.members_ever == ("CCC",), str(u2.members_ever))


def test_15_qualifies_at_boundaries() -> None:
    good = _edge(ticker="AAA")
    hist = _history([_tickrec("AAA", [
        _filing("2015-03-01", disclosures=[good]),
        _filing("2017-03-01"),
    ])])
    u = derive_universe_point_in_time(hist, frame=("AAA",))

    check("15a. the day BEFORE the filing: not a member",
          not u.qualifies_at("AAA", "2015-02-28"))
    check("15b. ON the filing date: a member -- the disclosure was public",
          u.qualifies_at("AAA", "2015-03-01"))
    check("15c. mid-interval: a member", u.qualifies_at("AAA", "2016-06-15"))
    check("15d. the day before the superseding filing: still a member",
          u.qualifies_at("AAA", "2017-02-28"))
    check("15e. ON the superseding filing date: NOT a member",
          not u.qualifies_at("AAA", "2017-03-01"))
    check("15f. long after: not a member", not u.qualifies_at("AAA", "2020-01-01"))
    check("15g. a ticker never walked: not a member",
          not u.qualifies_at("BBB", "2016-06-15"))
    check("15h. a malformed date denies rather than raising",
          not u.qualifies_at("AAA", "15 March 2016"))
    check("15i. a date object works as well as a string",
          u.qualifies_at("AAA", date(2016, 6, 15)))

    stale = _history([_tickrec("AAA", [
        _no_disclosures(_filing("2015-03-01", disclosures=[good]))])])
    ur = derive_universe_point_in_time(stale, frame=("AAA",))
    check("15j. a REFUSED derivation is never a member on any date",
          not ur.qualifies_at("AAA", "2016-06-15"), str(ur.refusals))


def test_16_refusal_and_incompleteness_are_different_things() -> None:
    good = _edge(ticker="AAA")

    # REFUSAL: no denominators anywhere. Nothing may be published.
    stale = _history([_tickrec("AAA", [
        _no_disclosures(_filing("2015-03-01", disclosures=[good]))])])
    r = derive_universe_point_in_time(stale, frame=("AAA",))
    check("16a. a walk carrying no denominators is refused", not r.derived)
    check("16b. naming the missing field",
          any("disclosures" in x for x in r.refusals), str(r.refusals))
    check("16c. and its intervals are WITHHELD, not merely empty",
          r.intervals == () and r.members_ever == ())

    # INCOMPLETE: one filing could not be fetched. The answer still stands.
    part = _history([_tickrec(
        "AAA",
        [_filing("2015-03-01", disclosures=[good])],
        filings_on_record=2,
        filings_failed=[{"filing_date": "2011-03-01", "accession": "x",
                         "error": "HTTPError: 404"}])])
    i = derive_universe_point_in_time(part, frame=("AAA",))
    check("16d. an unreachable filing does NOT refuse the derivation",
          i.derived, str(i.refusals))
    check("16e. but the result is not complete", not i.complete, str(i.incomplete))
    check("16f. and the interval it did find still stands",
          i.members_ever == ("AAA",), str(i.members_ever))
    check("16g. the hole is enumerated, not merely flagged",
          any("could not" in x for x in i.incomplete), str(i.incomplete))
    check("16h. an incomplete result is never registry-grade",
          not i.registry_grade)

    # A frame member never walked IS a refusal: a universe over part of the
    # frame is selected by whatever chose the part.
    u = derive_universe_point_in_time(
        _history([_tickrec("AAA", [_filing("2015-03-01", disclosures=[good])])]))
    check("16i. an unwalked frame member refuses the derivation", not u.derived)
    check("16j. saying how many were missed",
          any("were not walked" in x for x in u.refusals), str(u.refusals))

    # An overridden frame is a pilot and must never pass as registry-grade.
    ok = derive_universe_point_in_time(
        _history([_tickrec("AAA", [_filing("2015-03-01", disclosures=[good])])]),
        frame=("AAA",))
    check("16k. a complete, unrefused PILOT is still not registry-grade",
          ok.derived and ok.complete and not ok.registry_grade)
    check("16l. because the frame was overridden, and it says so",
          ok.evidence.get("frame_is_default") is False
          and "not a registry-grade"
          in (ok.evidence.get("frame_override_note") or "").lower())

    txt = format_point_in_time_report(i)
    check("16m. the report shows incompleteness prominently", "INCOMPLETE" in txt)
    check("16n. and a refused report withholds rather than showing zero",
          "withheld" in format_point_in_time_report(r))


def test_17_the_rule_itself_did_not_change() -> None:
    """Point-in-time evaluation must REUSE the rule, never fork it."""
    import inspect

    from hyp04_supply_chain_hedge import anchor_universe as m

    src = inspect.getsource(m._intervals_for_ticker)
    check("17a. the interval builder calls evaluate_ticker",
          "evaluate_ticker(" in src)
    check("17b. and re-implements no condition of its own",
          not any(cid in src for cid, _ in CONDITIONS), src[:160])
    check("17c. the conditions are still exactly AU-1..AU-6",
          [c for c, _ in CONDITIONS]
          == ["AU-1", "AU-2", "AU-3", "AU-4", "AU-5", "AU-6"])
    check("17d. the threshold is unchanged", CONCENTRATION_THRESHOLD_PCT == 10.0)
    check("17e. the denominator is unchanged",
          REQUIRED_BASIS == BASIS_CONSOLIDATED_REVENUE)


def test_11_the_gate_does_not_move() -> None:
    from hyp04_supply_chain_hedge import display_gate as g
    d = g.current_decision()
    # OPENED 2026-09-09 (freeze attested + registry v1.12 moved C1); CLOSED
    # with 4 denials throughout Phase 0. Declaring a universe is still not what
    # opened it, which is what this test is named for.
    check("11a. the display gate is OPEN", d.open, str(d.conditions))
    check("11b. with zero denials", len(d.denials) == 0, str(d.denials))
    check("11c. and C4 still MET",
          d.conditions["C4_decisions_resolved"] is True, str(d.conditions))


def test_12_offline() -> None:
    check("12a. network is blocked in this suite", True)
    try:
        socket.getaddrinfo("www.sec.gov", 443)
        check("12b. a network call raises", False, "it did not")
    except NetworkBlocked:
        check("12b. a network call raises", True)


if __name__ == "__main__":
    test_1_a_valid_disclosure_qualifies()
    test_2_the_member_list_is_computed_not_hardcoded()
    test_3_each_condition_denies_on_its_own()
    test_4_boundaries()
    test_5_denials_accumulate_and_are_specific()
    test_6_membership_cannot_depend_on_survival()
    test_7_an_unevaluable_screen_is_refused()
    test_8_the_frame_is_derived_and_predates_the_rule()
    test_9_the_published_stale_screen_is_the_regression_fixture()
    test_10_the_rule_declares_what_it_is()
    test_13_the_rule_is_evaluated_against_the_filing_in_force()
    test_14_intervals_open_close_and_repeat()
    test_15_qualifies_at_boundaries()
    test_16_refusal_and_incompleteness_are_different_things()
    test_17_the_rule_itself_did_not_change()
    test_11_the_gate_does_not_move()
    test_12_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 ANCHOR-UNIVERSE TESTS PASSED")
    sys.exit(0)
