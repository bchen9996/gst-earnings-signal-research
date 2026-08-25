#!/usr/bin/env python3
"""Tests for CANDIDATE anchor-event derivation from 8-K Item 2.02 -- HYP-04.

The whole module exists to avoid one defect, and that defect is invisible on
half the real sample:

  THE FILING DATE IS NOT THE EVENT DATE (test_3, the load-bearing test).
  SEC stamps a submission accepted after 17:30 ET with the NEXT business day
  as its filingDate. Measured 2026-08-23, MCK is accepted 16:05-16:07 ET and
  its reportDate ALWAYS equals its filingDate; PKG is accepted 17:48-18:18 ET
  and its reportDate NEVER does. An implementation that reached for filingDate
  -- the obvious field, and the one all_10ks uses -- would be perfect on MCK
  and one day late on every single PKG event. After the AMC next-session rule
  that is one SESSION late, which is the look-ahead direction: the reference
  window would extend past the news.

  So test_3 pins a PKG-shaped record and requires release_date to be the
  report date. A mutation swapping reportDate for filingDate must fail here.

The other properties:

  UNKNOWN IS A REFUSAL, NOT A DEFAULT (test_2, test_5). An intraday
  acceptance, a missing timestamp, a malformed timestamp, and an acceptance on
  a different calendar day all resolve to UNKNOWN with a stated reason. None
  of them may resolve to BMO or AMC, because a wrong session is silent and a
  refusal is not.

  THE BOUNDARIES ARE EXACT (test_4). 16:00:00 ET is AMC and 09:29:59 is BMO;
  09:30:00 is UNKNOWN. Both bands are checked from both sides, because a rule
  that only ever denies is satisfied by a function returning UNKNOWN always.

  EST AND EDT BOTH APPEAR IN THE REAL DATA (test_6). A naive fixed -5 or -4
  offset is right for half the year. Both are asserted against known UTC
  instants.

  NOTHING HERE MOVES A GATE (test_7). Candidates are not eligible events.

Offline. No network. Nothing is written to the repo.

Run directly: python test_hyp04_supply_chain_hedge_earnings_events.py
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

from hyp04_supply_chain_hedge.earnings_events import (  # noqa: E402
    FLAG_NON_STANDARD_ITEMS,
    FLAG_REPORT_BEFORE_FILING,
    FLAG_SESSION_UNRESOLVED,
    SESSION_AMC,
    SESSION_BMO,
    SESSION_UNKNOWN,
    CandidateEvent,
    candidate_from_record,
    find_cadence_gaps,
    PROVENANCE_CURATED,
    PROVENANCE_DERIVED,
    classify_release_session,
    event_id_for,
    summarise,
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


# Real records, copied verbatim from the SEC submissions API on 2026-08-23.
# These are FIXTURES of observed data, not invented shapes.
MCK_REAL = {
    "accessionNumber": "0000927653-26-000232",
    "filingDate": "2026-08-05",
    "reportDate": "2026-08-05",
    "acceptanceDateTime": "2026-08-05T20:06:03.000Z",
    "items": "2.02,9.01",
}
PKG_REAL = {
    "accessionNumber": "0001193125-26-312651",
    "filingDate": "2026-07-23",          # <-- one day AFTER the release
    "reportDate": "2026-07-22",          # <-- the release
    "acceptanceDateTime": "2026-07-22T22:04:21.000Z",
    "items": "2.02,9.01",
}
MCK_BMO_REAL = {
    "accessionNumber": "0000927653-25-000121",
    "filingDate": "2025-09-18",
    "reportDate": "2025-09-18",
    "acceptanceDateTime": "2025-09-18T12:00:41.000Z",   # 08:00 EDT
    "items": "2.02,8.01,9.01",
}


def test_1_the_standard_amc_case():
    ev = candidate_from_record("MCK", MCK_REAL)
    check("1a. release_date is the report date",
          ev.release_date == "2026-08-05", ev.release_date)
    check("1b. classified AMC", ev.release_session == SESSION_AMC,
          ev.release_session)
    check("1c. the basis names the observed time and the rule",
          "16:06" in ev.session_basis and "16:00 ET close" in ev.session_basis,
          ev.session_basis)
    check("1d. acceptance is rendered in ET, not left in UTC",
          ev.acceptance_et.startswith("2026-08-05 16:06"), ev.acceptance_et)
    check("1e. a routine 2.02,9.01 release carries no flags",
          ev.flags == (), str(ev.flags))
    check("1f. event_id is anchor + release date",
          ev.event_id == "MCK-2026-08-05", ev.event_id)


def test_2_unknown_is_a_refusal_not_a_default():
    cases = [
        ("no timestamp", "2026-01-05", "", "no acceptance timestamp"),
        ("malformed timestamp", "2026-01-05", "not-a-time", "unparseable"),
        ("intraday", "2026-01-05", "2026-01-05T17:30:00.000Z", "intraday"),
        ("different day", "2026-01-05", "2026-01-07T21:00:00.000Z",
         "not the release date"),
    ]
    for name, rd, acc, needle in cases:
        session, basis = classify_release_session(rd, acc)
        check(f"2. {name} -> UNKNOWN", session == SESSION_UNKNOWN, session)
        check(f"2. {name} -> the reason is stated", needle in basis, basis)

    # The whole point: none of these may become a tradeable classification.
    for name, rd, acc, _ in cases:
        session, _ = classify_release_session(rd, acc)
        check(f"2. {name} is never silently BMO or AMC",
              session not in (SESSION_BMO, SESSION_AMC), session)


def test_3_the_filing_date_is_never_the_event_date():
    """LOAD-BEARING. A PKG-shaped record must resolve to the REPORT date."""
    ev = candidate_from_record("PKG", PKG_REAL)

    check("3a. release_date is the report date, not the filing date",
          ev.release_date == "2026-07-22",
          f"got {ev.release_date}, filingDate is {PKG_REAL['filingDate']}")
    check("3b. and they genuinely differ in this fixture",
          PKG_REAL["reportDate"] != PKG_REAL["filingDate"])
    check("3c. the filing date is still carried as evidence",
          ev.filing_date == "2026-07-23", ev.filing_date)
    check("3d. the divergence is flagged for a human",
          FLAG_REPORT_BEFORE_FILING in ev.flags, str(ev.flags))
    check("3e. event_id uses the release date",
          ev.event_id == "PKG-2026-07-22", ev.event_id)
    check("3f. an 18:04 ET acceptance is AMC",
          ev.release_session == SESSION_AMC, ev.release_session)

    # The mutation this guards: had release_date come from filingDate, the
    # event would sit one calendar day late -- and AMC resolution then puts
    # the response session one session late, extending the reference window
    # PAST the news. Assert the wrong answer is actually different.
    check("3g. the wrong field would have given a different date",
          PKG_REAL["filingDate"] != ev.release_date)


def test_4_the_boundaries_are_exact():
    # 2026-01-05 is EST (UTC-5). 16:00 EST == 21:00 UTC.
    at_close = classify_release_session("2026-01-05", "2026-01-05T21:00:00.000Z")
    check("4a. exactly 16:00 ET is AMC", at_close[0] == SESSION_AMC, at_close[0])

    just_before = classify_release_session("2026-01-05",
                                           "2026-01-05T20:59:59.000Z")
    check("4b. 15:59:59 ET is not AMC", just_before[0] == SESSION_UNKNOWN,
          just_before[0])

    # 09:30 EST == 14:30 UTC.
    at_open = classify_release_session("2026-01-05", "2026-01-05T14:30:00.000Z")
    check("4c. exactly 09:30 ET is not BMO", at_open[0] == SESSION_UNKNOWN,
          at_open[0])

    just_before_open = classify_release_session("2026-01-05",
                                                "2026-01-05T14:29:59.000Z")
    check("4d. 09:29:59 ET is BMO", just_before_open[0] == SESSION_BMO,
          just_before_open[0])

    # Both directions: the function must be capable of every verdict, or a
    # constant-UNKNOWN implementation would pass every denial check above.
    verdicts = {at_close[0], just_before[0], at_open[0], just_before_open[0]}
    check("4e. the classifier produces more than one verdict",
          len(verdicts) >= 2, str(verdicts))


def test_5_the_real_bmo_case_is_found_and_flagged():
    ev = candidate_from_record("MCK", MCK_BMO_REAL)
    check("5a. an 08:00 ET acceptance is BMO",
          ev.release_session == SESSION_BMO, ev.release_session)
    check("5b. items beyond 2.02/9.01 are flagged",
          FLAG_NON_STANDARD_ITEMS in ev.flags, str(ev.flags))
    check("5c. but the event is NOT dropped",
          ev.release_date == "2025-09-18", ev.release_date)
    check("5d. a resolved session carries no unresolved flag",
          FLAG_SESSION_UNRESOLVED not in ev.flags, str(ev.flags))


def test_6_est_and_edt_are_both_handled():
    # Same wall-clock ET hour, opposite sides of the DST boundary. A fixed
    # offset gets one of these wrong.
    edt = classify_release_session("2026-08-05", "2026-08-05T20:06:03.000Z")
    est = classify_release_session("2026-02-04", "2026-02-04T21:05:57.000Z")
    check("6a. August 20:06Z is 16:06 EDT -> AMC", edt[0] == SESSION_AMC,
          edt[1])
    check("6b. February 21:05Z is 16:05 EST -> AMC", est[0] == SESSION_AMC,
          est[1])
    check("6c. the bases name the two different zones",
          "EDT" in edt[1] and "EST" in est[1], f"{edt[1]} | {est[1]}")

    # A fixed UTC-5 would read the August stamp as 15:06 -> UNKNOWN.
    check("6d. a fixed -5 offset would have misread the summer stamp",
          edt[0] == SESSION_AMC)


def test_7_candidates_are_not_eligible_events():
    src = open("hyp04_supply_chain_hedge/earnings_events.py",
               encoding="utf-8").read()
    check("7a. the module says candidates are not eligible events",
          "NOT ELIGIBLE EVENTS" in src)
    check("7b. it disclaims moving C2",
          "C2" in src and "not moved" in src)
    check("7c. it does not import the display gate",
          "display_gate" not in src)
    check("7d. it does not import or write a registry",
          "make_registry" not in src and "REGISTRY" not in src)
    check("7e. it does not touch eligible_event_counts",
          "eligible_event_counts" in src and "stays whatever" in src,
          "must mention the field only to disclaim changing it")


def test_8_summarise_counts_what_it_says():
    evs = [candidate_from_record("MCK", MCK_REAL),
           candidate_from_record("PKG", PKG_REAL),
           candidate_from_record("MCK", MCK_BMO_REAL)]
    s = summarise(evs)
    check("8a. total", s["total"] == 3, str(s))
    check("8b. AMC count", s["by_session"][SESSION_AMC] == 2, str(s))
    check("8c. BMO count", s["by_session"][SESSION_BMO] == 1, str(s))
    check("8d. UNKNOWN count", s["by_session"][SESSION_UNKNOWN] == 0, str(s))
    check("8e. earliest/latest span the fixtures",
          s["earliest"] == "2025-09-18" and s["latest"] == "2026-08-05", str(s))
    check("8f. flagged counts events, not flags",
          s["flagged"] == 2, str(s))


def _ev(ticker: str, d: str) -> CandidateEvent:
    return CandidateEvent(
        event_id=event_id_for(ticker, d), anchor_ticker=ticker,
        release_date=d, release_session=SESSION_AMC, session_basis="fixture",
        filing_date=d, acceptance_utc="", acceptance_et="", items="2.02,9.01",
        accession="", flags=())


def test_9_cadence_gaps_are_detected_not_filled():
    # The REAL MCK gap: 2019-10-30 -> 2020-05-20, because the 2020-02-04
    # release was filed with items "9.01" only and Item 2.02 cannot see it.
    mck = [_ev("MCK", d) for d in
           ("2019-04-24", "2019-07-24", "2019-10-30", "2020-05-20",
            "2020-08-03")]
    gaps = find_cadence_gaps(mck)
    check("9a. the real MCK gap is found", len(gaps) == 1, str(gaps))
    check("9b. it names both ends and the length",
          gaps[0][:2] == ("2019-10-30", "2020-05-20") and gaps[0][2] == 203,
          str(gaps))

    # An unbroken quarterly cadence must report nothing -- otherwise the
    # detector "finds" a gap everywhere and means nothing.
    pkg = [_ev("PKG", d) for d in
           ("2020-01-29", "2020-04-27", "2020-07-24", "2020-10-26")]
    check("9c. an unbroken cadence yields no gap",
          find_cadence_gaps(pkg) == [], str(find_cadence_gaps(pkg)))

    # Per ticker, not across the merged list: interleaving two tickers must
    # not manufacture or mask a gap.
    both = find_cadence_gaps(mck + pkg)
    check("9d. gaps are computed per ticker", len(both) == 1, str(both))

    # Boundary: 130 days is not a gap, 131 is.
    at = find_cadence_gaps([_ev("X", "2020-01-01"), _ev("X", "2020-05-10")])
    over = find_cadence_gaps([_ev("X", "2020-01-01"), _ev("X", "2020-05-11")])
    check("9e. exactly 130 days is not a gap", at == [], str(at))
    check("9f. 131 days is a gap", len(over) == 1, str(over))

    # It must not invent events.
    check("9g. the detector returns intervals, not events",
          all(isinstance(g, tuple) and len(g) == 3 for g in gaps), str(gaps))

    src = open("hyp04_supply_chain_hedge/earnings_events.py",
               encoding="utf-8").read()
    check("9h. the module records that Item 2.02 is a floor, not a census",
          "FLOOR, NOT A CENSUS" in src.upper())
    check("9i. and names the confirmed miss",
          "0000927653-20-000013" in src)
    check("9j. and refuses to fill gaps",
          "do not guess" in src.lower() or "does NOT try to fill" in src)


ADDENDA_HEADER = (
    "event_id,anchor_ticker,release_date,release_session,supersedes_event_id,"
    "source_accession,source_citation,curated_by,curated_date,review_status,"
    "notes_caveats\n")
GOOD_ROW = ("X-2020-01-02,MCK,2020-01-02,BMO,,0000-00-000000,a real citation,"
            "tester,2026-08-24,draft,\n")


def _addenda(tmp, body: str, header: str = ADDENDA_HEADER):
    from pathlib import Path as _P
    p = _P(tmp) / "add.csv"
    p.write_text(header + body, encoding="utf-8")
    return p


def test_11_addenda_demand_provenance():
    import tempfile

    from hyp04_supply_chain_hedge.earnings_events import (
        AddendaError, load_addenda)

    with tempfile.TemporaryDirectory() as td:
        ev, sup, rej = load_addenda(_addenda(td, GOOD_ROW))
        check("11a. a fully-cited row loads", len(ev) == 1 and not rej, str(rej))
        check("11b. and is marked CURATED, not derived",
              ev[0].provenance == PROVENANCE_CURATED, ev[0].provenance)
        check("11c. its basis names the citation",
              "CURATED" in ev[0].session_basis
              and "a real citation" in ev[0].session_basis,
              ev[0].session_basis)

        # Each required provenance field, blanked one at a time.
        cols = ADDENDA_HEADER.strip().split(",")
        for field in ("source_citation", "curated_by", "curated_date",
                      "source_accession"):
            parts = GOOD_ROW.rstrip("\n").split(",")
            parts[cols.index(field)] = ""
            ev2, _, rej2 = load_addenda(_addenda(td, ",".join(parts) + "\n"))
            check(f"11d. a row missing {field} is rejected",
                  not ev2 and len(rej2) == 1, f"{ev2} {rej2}")
            check(f"11e. and the rejection names {field}",
                  field in rej2[0], rej2[0] if rej2 else "")

        # Curating UNKNOWN is curating an absence.
        unk = GOOD_ROW.replace(",BMO,", ",UNKNOWN,")
        ev3, _, rej3 = load_addenda(_addenda(td, unk))
        check("11f. UNKNOWN is refused in an addendum",
              not ev3 and rej3, f"{ev3} {rej3}")

        bad_date = GOOD_ROW.replace("2020-01-02,BMO", "02/01/2020,BMO")
        ev4, _, rej4 = load_addenda(_addenda(td, bad_date))
        check("11g. a malformed release_date is refused", not ev4 and rej4,
              f"{ev4} {rej4}")

        ev5, _, rej5 = load_addenda(_addenda(td, GOOD_ROW + GOOD_ROW))
        check("11h. a duplicate event_id is refused once, kept once",
              len(ev5) == 1 and len(rej5) == 1, f"{ev5} {rej5}")

        # A missing COLUMN is worse than a bad row: it is absent from every
        # row, so it raises instead of rejecting row by row.
        short = ADDENDA_HEADER.replace(",source_citation", "")
        raised = False
        try:
            load_addenda(_addenda(td, "", header=short))
        except AddendaError:
            raised = True
        check("11i. a missing required COLUMN raises, not rejects", raised)

        check("11j. an absent file is not an error",
              load_addenda(_addenda(td, "").with_name("nope.csv"))
              == ([], {}, []))


def test_12_supersession_prevents_double_counting():
    """A curated row and the derived row it corrects do NOT share an id.

    MCK-2023-11-01 corrects MCK-2023-10-27; the id embeds the date, and the
    date is the thing being corrected. Merging both would count one earnings
    release twice, and a double-count is invisible in a total.
    """
    import tempfile

    from hyp04_supply_chain_hedge.earnings_events import (
        AddendaError, load_addenda, merge_addenda)

    derived = [_ev("MCK", "2023-10-27"), _ev("MCK", "2024-02-07")]
    curated = [_ev("MCK", "2023-11-01")]
    for c in curated:
        object.__setattr__(c, "provenance", PROVENANCE_CURATED)

    merged, notes = merge_addenda(derived, curated,
                                  {"MCK-2023-11-01": "MCK-2023-10-27"})
    ids = [e.event_id for e in merged]
    check("12a. the superseded event is gone", "MCK-2023-10-27" not in ids,
          str(ids))
    check("12b. the curated one is present", "MCK-2023-11-01" in ids, str(ids))
    check("12c. the count did not grow", len(merged) == 2, str(ids))
    check("12d. the supersession is reported", notes == ["MCK-2023-11-01 "
                                                         "supersedes "
                                                         "MCK-2023-10-27"],
          str(notes))

    # HARDCODED-OPEN: a pure addition must still ADD.
    merged2, notes2 = merge_addenda(derived, [_ev("MCK", "2020-02-04")], {})
    check("12e. an addendum superseding nothing adds an event",
          len(merged2) == 3, str([e.event_id for e in merged2]))
    check("12f. and reports no supersession", notes2 == [], str(notes2))

    # STALE ADDENDUM: the target is not in the derived set.
    raised = False
    try:
        merge_addenda(derived, curated, {"MCK-2023-11-01": "MCK-1999-01-01"})
    except AddendaError as exc:
        raised = "stale" in str(exc)
    check("12g. superseding an absent event raises as STALE", raised)

    # COLLISION: same id in both sets is ambiguous.
    raised2 = False
    try:
        merge_addenda(derived, [_ev("MCK", "2024-02-07")], {})
    except AddendaError as exc:
        raised2 = "collides" in str(exc)
    check("12h. a curated id colliding with a derived id raises", raised2)

    # The committed addenda file must itself load clean.
    from pathlib import Path as _P
    real = _P("Live Signal Engine/HYP04_ANCHOR_EVENT_ADDENDA.csv")
    if not real.is_file():
        skip("12i. committed addenda", "file not present")
    else:
        ev, sup, rej = load_addenda(real)
        check("12i. the committed addenda file loads with no rejections",
              not rej, str(rej))
        check("12j. every committed row carries a real citation",
              all(len(e.session_basis) > 40 for e in ev),
              str([len(e.session_basis) for e in ev]))
        check("12k. and every one is CURATED provenance",
              all(e.provenance == PROVENANCE_CURATED for e in ev))


def test_13_the_dashboard_derives_the_count_and_disclaims_c2():
    """The page may show candidates only if it counts them and disclaims C2.

    This project has already had to remove one hardcoded count from this file
    ("zero rows are curated"), so the guard is structural rather than a promise:
    the number must not appear as a literal in the source, and the C2
    disclaimer must be present.
    """
    import re as _re

    src = open("hyp04_supply_chain_hedge/dashboard.py", encoding="utf-8").read()

    check("13a. the dashboard counts candidates from disk",
          "def read_anchor_event_candidates" in src)
    check("13b. by reading the CSV, not a constant",
          "HYP04_ANCHOR_EVENT_CANDIDATES" in src and "DictReader" in src)
    check("13c. and splits derived from curated provenance",
          "by_provenance" in src)

    # The live totals must NOT appear as literals anywhere in the renderer.
    from hyp04_supply_chain_hedge.dashboard import read_anchor_event_candidates
    cand = read_anchor_event_candidates()
    if not cand.get("present"):
        skip("13d. no baked count", "candidates file absent")
    else:
        baked = [str(n) for n in (cand["total"], *cand["by_anchor"].values())
                 if _re.search(rf"[^0-9]{n}[^0-9]", src)]
        # A bare number can appear innocently (a year, a width). Require that
        # the total specifically is not written next to candidate wording.
        near = _re.search(r"candidate[^\"'\n]{0,40}" + str(cand["total"]), src,
                          _re.I) or _re.search(
                              str(cand["total"]) + r"[^\"'\n]{0,40}candidate",
                              src, _re.I)
        check("13d. the candidate total is not baked next to candidate wording",
              near is None, f"found {near.group(0)!r}" if near else "")

    # Prose in an f-string wraps across source lines, so a contiguous
    # substring match fails against CORRECT text. Collapse whitespace first --
    # this exact mistake was made once already, in the curated-linkage guard.
    flat = " ".join(src.split())
    check("13e. the page states candidates are NOT eligible events",
          "NOT eligible events" in flat and "does not move C2" in flat)
    check("13f. and says the eligible count remains zero",
          "eligible count remains zero" in flat)
    check("13g. and says screening belongs to HYP-01",
          "screening is HYP-01" in flat)
    check("13h. the block is omitted, not zeroed, when the file is absent",
          'candidates_block = ""' in src)


def test_10_offline():
    check("10a. network is blocked in this suite", True)
    try:
        socket.getaddrinfo("www.sec.gov", 443)
        check("10b. a network call raises", False, "it did not")
    except NetworkBlocked:
        check("10b. a network call raises", True)


if __name__ == "__main__":
    test_1_the_standard_amc_case()
    test_2_unknown_is_a_refusal_not_a_default()
    test_3_the_filing_date_is_never_the_event_date()
    test_4_the_boundaries_are_exact()
    test_5_the_real_bmo_case_is_found_and_flagged()
    test_6_est_and_edt_are_both_handled()
    test_7_candidates_are_not_eligible_events()
    test_8_summarise_counts_what_it_says()
    test_9_cadence_gaps_are_detected_not_filled()
    test_11_addenda_demand_provenance()
    test_12_supersession_prevents_double_counting()
    test_13_the_dashboard_derives_the_count_and_disclaims_c2()
    test_10_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 EARNINGS-EVENTS TESTS PASSED")
    sys.exit(0)
