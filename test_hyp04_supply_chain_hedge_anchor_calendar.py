#!/usr/bin/env python3
"""HYP-04 anchor-event CALENDAR tests. FULLY OFFLINE.

The calendar crosses the point-in-time anchor universe with 8-K results
filings, and every way of getting it wrong inflates a number that looks like
progress:

  * counting a re-filing of the same release twice (18 real cases)
  * letting an SEC item RENUMBERING read as a filer that stopped reporting
  * accepting a legacy code silently, which is a specification change
  * calling a candidate count an eligible count, which is a gate claim

So the tests here are mostly about what the calendar REFUSES to say.

Run directly: python test_hyp04_supply_chain_hedge_anchor_calendar.py
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

from hyp04_supply_chain_hedge.anchor_calendar import (  # noqa: E402
    ANCHOR_CALENDAR_RULE_ID,
    DEDUP_RULE,
    FLAG_LEGACY_ITEM_12,
    FLAG_MODERN_CODE_BEFORE_RENUMBERING,
    ITEM_12_INTRODUCED,
    ITEM_RENUMBERED_TO_2_02,
    CalendarEntry,
    dedup_one_event_per_release,
    derive_anchor_calendar,
    item_codes,
    results_item_verdict,
)
from hyp04_supply_chain_hedge.earnings_events import (  # noqa: E402
    candidate_from_record,
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


# --------------------------------------------------------------------------
# Stubs. A fake universe and a fake client, so nothing here needs the cache,
# the network, or the pinned history artifact.
# --------------------------------------------------------------------------
class FakeInterval:
    def __init__(self, ticker, start, end):
        self.ticker = ticker
        self.start_date = start
        self.end_date = end


class FakeUniverse:
    def __init__(self, intervals, registry_grade=True):
        self.intervals = intervals
        self.registry_grade = registry_grade
        self.refusals: list[str] = []
        self.incomplete: list[str] = []

    def qualifies_at(self, ticker, day):
        for i in self.intervals:
            if i.ticker != ticker:
                continue
            if day >= i.start_date and (i.end_date is None or day < i.end_date):
                return True
        return False


class FakeClient:
    """Serves canned submissions blocks. Counts nothing as a live request."""

    def __init__(self, blocks_by_cik):
        self.blocks_by_cik = blocks_by_cik
        self.requests_made = 0
        self.urls: list[str] = []

    def cik_for(self, ticker):
        return {"AAA": "0000000001", "BBB": "0000000002"}.get(ticker)

    def _get_json(self, url, timeout=30):
        self.urls.append(url)
        for cik, payload in self.blocks_by_cik.items():
            if cik in url:
                return payload
        raise AssertionError("unexpected url " + url)

    def _get(self, url, timeout=30):
        raise AssertionError(
            "the calendar reached the RAW transport, below the cache and "
            "below the offline guard: " + url)


def _sub(rows, files=()):
    """Build a submissions payload from (form, items, report, filed, acc, id)."""
    return {"filings": {
        "recent": {
            "form": [r[0] for r in rows],
            "items": [r[1] for r in rows],
            "reportDate": [r[2] for r in rows],
            "filingDate": [r[3] for r in rows],
            "acceptanceDateTime": [r[4] for r in rows],
            "accessionNumber": [r[5] for r in rows],
        },
        "files": list(files)}}


def test_1_item_codes_are_exact_tokens() -> None:
    print("\n--- 1: item codes are tokens, not substrings ---")
    check("1a. a plain list splits", item_codes("2.02,9.01") == {"2.02", "9.01"})
    check("1b. whitespace is tolerated", item_codes(" 12 , 7 ") == {"12", "7"})
    check("1c. empty is empty", item_codes("") == set() and item_codes(None) == set())
    # The legacy code is "12". A substring test would find it inside a code
    # like "1.12" the moment the SEC invents one, and would silently promote an
    # unrelated 8-K into the earnings calendar.
    m, lg, _ = results_item_verdict("1.12,9.01", "2003-06-01")
    check("1d. '12' is NOT found inside another code", not lg and not m,
          "matched as a substring")


def test_2_the_item_code_means_different_things_by_era() -> None:
    print("\n--- 2: the code is an artefact of its era ---")
    m, lg, note = results_item_verdict("2.02,9.01", "2010-04-13")
    check("2a. a modern code after renumbering is modern", m and not note)
    m, lg, note = results_item_verdict("12,7", "2004-01-22")
    check("2b. a legacy code in its window is legacy and flagged",
          lg and not m and note == FLAG_LEGACY_ITEM_12, note)
    m, lg, note = results_item_verdict("2.02", "2001-12-16")
    # NKE really does have one of these. It is counted under the strict rule --
    # the index is what it is -- but it must not pass unremarked.
    check("2c. a MODERN code BEFORE the renumbering is flagged, not dropped",
          m and note == FLAG_MODERN_CODE_BEFORE_RENUMBERING, note)
    m, lg, _ = results_item_verdict("5,7", "2001-06-01")
    check("2d. the pre-2003 codes are not results items",
          not m and not lg)
    check("2e. the two era boundaries are the SEC's, and stated",
          ITEM_12_INTRODUCED == "2003-03-28"
          and ITEM_RENUMBERED_TO_2_02 == "2004-08-23")


def test_3_deduplication_keeps_the_earliest_acceptance() -> None:
    """THE LOAD-BEARING ONE. 18 real release dates carry two 8-Ks: a same-day
    wire filing and a later re-filing with the SAME reportDate."""
    print("\n--- 3: one anchor event per release ---")

    def entry(acc, acceptance, items="2.02"):
        ev = candidate_from_record("AAA", {
            "accessionNumber": acc, "filingDate": "2010-04-14",
            "reportDate": "2010-04-13", "acceptanceDateTime": acceptance,
            "items": items})
        return CalendarEntry(event=ev, ticker="AAA",
                             interval_start="2005-01-01", interval_end=None,
                             item_era="modern")

    same_day = entry("0001157523-10-002015", "2010-04-13T20:20:00.000Z")
    refiling = entry("0000050863-10-000033", "2010-04-14T15:47:00.000Z")

    kept, dropped = dedup_one_event_per_release([refiling, same_day])
    check("3a. one event survives", len(kept) == 1, str(len(kept)))
    check("3b. and it is the SAME-DAY filing, not the re-filing",
          kept[0].event.accession == "0001157523-10-002015",
          kept[0].event.accession)
    check("3c. the re-filing is recorded, not silently discarded",
          len(dropped) == 1
          and dropped[0]["superseded_accession"] == "0000050863-10-000033",
          str(dropped))
    check("3d. the record names what displaced it",
          dropped[0]["kept_accession"] == "0001157523-10-002015")
    check("3e. and states the rule", dropped[0]["reason"] == DEDUP_RULE)

    # This is WHY it matters: the re-filing lands intraday, so keeping it would
    # drag an unusable UNKNOWN session into the set in place of a clean AMC.
    check("3f. the kept filing has a usable session",
          kept[0].event.release_session == "AMC",
          kept[0].event.release_session)
    check("3g. CONTROL -- the re-filing on its own is UNRESOLVED",
          refiling.event.release_session == "UNKNOWN",
          refiling.event.release_session)

    # Order of arrival must not decide the answer.
    kept2, _ = dedup_one_event_per_release([same_day, refiling])
    check("3h. input order does not change the winner",
          kept2[0].event.accession == kept[0].event.accession)

    # A filing with no acceptance timestamp cannot be shown to be earliest.
    untimed = entry("0000000000-00-000000", "")
    kept3, _ = dedup_one_event_per_release([untimed, refiling])
    check("3i. an untimed filing does not beat a timed one",
          kept3[0].event.accession == "0000050863-10-000033",
          kept3[0].event.accession)

    # Ties break deterministically, so two runs cannot disagree.
    a = entry("0000000000-00-000002", "2010-04-13T20:20:00.000Z")
    b = entry("0000000000-00-000001", "2010-04-13T20:20:00.000Z")
    k4, _ = dedup_one_event_per_release([a, b])
    k5, _ = dedup_one_event_per_release([b, a])
    check("3j. an exact acceptance tie breaks on accession, both ways",
          k4[0].event.accession == k5[0].event.accession
          == "0000000000-00-000001", k4[0].event.accession)

    # Different releases must NOT be collapsed.
    other = CalendarEntry(
        event=candidate_from_record("AAA", {
            "accessionNumber": "x", "filingDate": "2010-07-14",
            "reportDate": "2010-07-13",
            "acceptanceDateTime": "2010-07-13T20:20:00.000Z",
            "items": "2.02"}),
        ticker="AAA", interval_start="2005-01-01", interval_end=None,
        item_era="modern")
    k6, d6 = dedup_one_event_per_release([same_day, refiling, other])
    check("3k. CONTROL -- a different release date is NOT collapsed",
          len(k6) == 2 and len(d6) == 1, f"{len(k6)}/{len(d6)}")


def test_4_legacy_recovery_is_opt_in() -> None:
    """Accepting Item 12 is a SPECIFICATION change. Measuring it is not."""
    print("\n--- 4: the legacy code is measured, not adopted ---")
    rows = [
        ("8-K", "2.02,9.01", "2005-01-20", "2005-01-20",
         "2005-01-20T21:20:00.000Z", "a-modern"),
        ("8-K", "12,7", "2004-01-22", "2004-01-22",
         "2004-01-22T21:20:00.000Z", "a-legacy"),
        ("8-K", "5,7", "2002-01-22", "2002-01-22",
         "2002-01-22T21:20:00.000Z", "a-untagged"),
        ("10-K", "", "2005-02-01", "2005-02-01", "", "a-10k"),
    ]
    u = FakeUniverse([FakeInterval("AAA", "2000-01-01", None)])

    c = FakeClient({"0000000001": _sub(rows)})
    strict = derive_anchor_calendar(u, c, today="2026-08-29")
    check("4a. the default rule is Item 2.02 only",
          strict.accept_legacy_item_12 is False and strict.total == 1,
          str(strict.total))
    check("4b. the untagged pre-2003 release is invisible to it",
          all(e.event.accession != "a-untagged" for e in strict.entries))
    check("4c. and a 10-K is never an earnings release",
          all(e.event.accession != "a-10k" for e in strict.entries))

    c2 = FakeClient({"0000000001": _sub(rows)})
    loose = derive_anchor_calendar(u, c2, accept_legacy_item_12=True,
                                   today="2026-08-29")
    check("4d. opting in recovers the Item 12 release",
          loose.total == 2 and loose.legacy_total == 1, str(loose.total))
    check("4e. the recovered rows are labelled by era",
          {e.item_era for e in loose.entries} == {"modern", "legacy"})
    check("4f. and carry the note",
          any(FLAG_LEGACY_ITEM_12 in e.notes for e in loose.entries))
    check("4g. even opted in, the untagged era stays invisible",
          all(e.event.accession != "a-untagged" for e in loose.entries))
    check("4h. the choice is reported in the artifact, not implied",
          loose.as_dict()["accept_legacy_item_12"] is True
          and strict.as_dict()["accept_legacy_item_12"] is False)


def test_5_membership_bounds_are_respected() -> None:
    print("\n--- 5: an event outside the span is not an anchor event ---")
    rows = [
        ("8-K", "2.02", "2004-12-01", "2004-12-01",
         "2004-12-01T21:20:00.000Z", "before"),
        ("8-K", "2.02", "2006-01-15", "2006-01-15",
         "2006-01-15T21:20:00.000Z", "inside"),
        ("8-K", "2.02", "2009-01-15", "2009-01-15",
         "2009-01-15T21:20:00.000Z", "after"),
        ("8-K", "2.02", "2005-01-01", "2005-01-01",
         "2005-01-01T21:20:00.000Z", "on-start"),
        ("8-K", "2.02", "2008-01-01", "2008-01-01",
         "2008-01-01T21:20:00.000Z", "on-end"),
    ]
    u = FakeUniverse([FakeInterval("AAA", "2005-01-01", "2008-01-01")])
    cal = derive_anchor_calendar(u, FakeClient({"0000000001": _sub(rows)}),
                                 today="2026-08-29")
    got = {e.event.accession for e in cal.entries}
    check("5a. an event before the span is excluded", "before" not in got)
    check("5b. an event after the span is excluded", "after" not in got)
    check("5c. an event inside is kept", "inside" in got)
    # qualifies_at is INCLUSIVE of the start (the disclosure was public that
    # day) and EXCLUSIVE of the end (the exit filing superseded it).
    check("5d. the start date itself is INSIDE", "on-start" in got)
    check("5e. the end date itself is OUTSIDE", "on-end" not in got, str(got))


def test_6_it_refuses_a_universe_it_cannot_stand_on() -> None:
    print("\n--- 6: refusals ---")
    u = FakeUniverse([FakeInterval("AAA", "2005-01-01", None)],
                     registry_grade=False)
    u.incomplete = ["3 filings unread"]
    cal = derive_anchor_calendar(u, FakeClient({}), today="2026-08-29")
    check("6a. a non-registry-grade universe yields NO calendar",
          cal.total == 0 and not cal.derived, str(cal.total))
    check("6b. and says why", any("not registry grade" in r for r in cal.refusals),
          str(cal.refusals))
    check("6c. CONTROL -- the same universe at registry grade derives",
          derive_anchor_calendar(
              FakeUniverse([FakeInterval("AAA", "2005-01-01", None)]),
              FakeClient({"0000000001": _sub([
                  ("8-K", "2.02", "2006-01-15", "2006-01-15",
                   "2006-01-15T21:20:00.000Z", "ok")])}),
              today="2026-08-29").total == 1)

    # Overlapping intervals for one ticker would break the per-interval
    # deduplication. The post-check exists to catch that; prove it fires.
    dup = FakeUniverse([FakeInterval("AAA", "2005-01-01", "2008-01-01"),
                        FakeInterval("AAA", "2006-01-01", "2009-01-01")])
    cal2 = derive_anchor_calendar(
        dup, FakeClient({"0000000001": _sub([
            ("8-K", "2.02", "2007-01-15", "2007-01-15",
             "2007-01-15T21:20:00.000Z", "twice")])}), today="2026-08-29")
    check("6d. CONTROL -- overlapping intervals are REFUSED, not summed",
          not cal2.derived
          and any("disjoint" in r for r in cal2.refusals), str(cal2.refusals))


def test_7_it_claims_nothing_about_eligibility() -> None:
    print("\n--- 7: candidate is not eligible ---")
    u = FakeUniverse([FakeInterval("AAA", "2005-01-01", None)])
    cal = derive_anchor_calendar(
        u, FakeClient({"0000000001": _sub([
            ("8-K", "2.02", "2006-01-15", "2006-01-15",
             "2006-01-15T21:20:00.000Z", "ok")])}), today="2026-08-29")
    d = cal.as_dict()
    check("7a. the eligible count is None, never the candidate count",
          d["eligible_event_count"] is None, str(d["eligible_event_count"]))
    check("7b. the status names the shock rule as the missing step",
          "HYP04-ANCHOR-SHOCK-RULE-v1" in d["measurement_status"])
    check("7c. and says C2 does not count these",
          "C2 counts eligible events, not these" in d["measurement_status"])
    check("7d. the candidate field is named candidate",
          "candidate_events_total" in d)
    check("7e. the rule id is carried", d["rule_id"] == ANCHOR_CALENDAR_RULE_ID)


def test_8_offline_and_through_the_cache() -> None:
    print("\n--- 8: no endpoint is reached ---")
    u = FakeUniverse([FakeInterval("AAA", "2005-01-01", None)])
    c = FakeClient({"0000000001": _sub(
        [("8-K", "2.02", "2006-01-15", "2006-01-15",
          "2006-01-15T21:20:00.000Z", "ok")],
        files=[{"name": "CIK0000000001-submissions-001.json"}])})
    cal = derive_anchor_calendar(u, c, today="2026-08-29")
    check("8a. live requests made is recorded, and is zero",
          cal.live_requests_made == 0, str(cal.live_requests_made))
    check("8b. extra submission blocks are followed", len(c.urls) == 2,
          str(c.urls))
    # FakeClient._get raises. Reverting to the raw transport fails here.
    try:
        c._get("https://data.sec.gov/anything")
        check("8c. CONTROL -- the raw-transport trap is armed", False,
              "it did not raise")
    except AssertionError:
        check("8c. CONTROL -- the raw-transport trap is armed", True)


def test_9_the_blind_era_is_measured_not_described() -> None:
    print("\n--- 9: the unlabelled era is a number ---")
    u = FakeUniverse([FakeInterval("AAA", "2001-03-28", "2005-03-28")])
    cal = derive_anchor_calendar(u, FakeClient({"0000000001": _sub([])}),
                                 today="2026-08-29")
    # 2001-03-28 .. 2003-03-28 is exactly two years with no results item code.
    check("9a. member-years before Item 12 existed are counted",
          abs(cal.unlabelled_member_years - 2.0) < 0.01,
          str(cal.unlabelled_member_years))
    u2 = FakeUniverse([FakeInterval("AAA", "2010-01-01", "2012-01-01")])
    cal2 = derive_anchor_calendar(u2, FakeClient({"0000000001": _sub([])}),
                                  today="2026-08-29")
    check("9b. a wholly modern span contributes none",
          cal2.unlabelled_member_years == 0.0,
          str(cal2.unlabelled_member_years))
    check("9c. the eras are published with the artifact",
          cal.as_dict()["item_code_eras"]["item_2_02_from"]
          == ITEM_RENUMBERED_TO_2_02)


def test_11_the_published_artifact_re_derives() -> None:
    """The artifact is checked against a fresh derivation, not trusted.

    v1.7's companion records the failure this guards: a repository holding code
    implementing one thing and an authoritative file describing another, with
    no test able to see it. So the published counts are RE-DERIVED here from
    the pinned history and the on-disk cache and compared field by field.

    Skipped, never silently passed, when the cache or the history is absent --
    a CI checkout has neither, and a green tick from a test that ran nothing is
    worse than an honest skip.
    """
    import json
    from pathlib import Path

    print()
    print("--- 11: the published calendar re-derives from source ---")

    LSE = Path("Live Signal Engine")
    art = LSE / "HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29.json"
    hist = LSE / "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-29_v1.json"
    cache_dir = Path(".edgar_cache")

    if not art.is_file():
        skip("11. published calendar re-derives", f"{art.name} not present")
        return
    if not hist.is_file() or not cache_dir.is_dir():
        skip("11. published calendar re-derives",
             "the pinned history or the EDGAR cache is not on this machine")
        return

    import hyp04_supply_chain_hedge.anchor_universe as au
    from hyp04_supply_chain_hedge.edgar_linkage import EdgarClient, FilingCache
    from hyp04_supply_chain_hedge.make_registry_v1_7 import _load

    published = json.loads(art.read_text(encoding="utf-8"))
    u = au.derive_universe_point_in_time(_load(hist))
    client = EdgarClient("hyp04-test@example-real-domain.org",
                         cache=FilingCache(cache_dir, readonly=True),
                         offline=True)

    strict = derive_anchor_calendar(u, client, today="2026-08-29")
    legacy = derive_anchor_calendar(u, client, accept_legacy_item_12=True,
                                    today="2026-08-29")

    ps = published["primary_specification_unchanged"]
    pl = published["measured_alternative_not_adopted"]
    check("11a. the strict total re-derives",
          ps["candidate_events_total"] == strict.total,
          f'{ps["candidate_events_total"]} vs {strict.total}')
    check("11b. the superseded count re-derives",
          ps["duplicate_filings_superseded"] == len(strict.superseded),
          f'{ps["duplicate_filings_superseded"]} vs {len(strict.superseded)}')
    check("11c. the measured alternative re-derives",
          pl["candidate_events_total"] == legacy.total,
          f'{pl["candidate_events_total"]} vs {legacy.total}')
    check("11d. per-interval counts re-derive",
          ps["per_interval"] == strict.per_interval, "they diverged")
    check("11e. the artifact was written from an offline derivation",
          published["sources"]["live_requests_made"] == 0
          and strict.live_requests_made == 0)
    check("11f. and the strict artifact really is the DEFAULT rule",
          ps["accept_legacy_item_12"] is False)

    # The threshold comparison must come from the registry, not from a number
    # typed into the artifact next to it.
    reg = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9.json"
    if reg.is_file():
        registry = json.loads(reg.read_text(encoding="utf-8"))
        entry = [h for h in registry["hypotheses"]
                 if h.get("hypothesis_id") == "HYP-04"][0]
        check("11g. the threshold matches the registry, not a local constant",
              published["registered_threshold"]["minimum_eligible_events"]
              == entry["minimum_eligible_events"],
              str(entry.get("minimum_eligible_events")))
        # The whole point of publishing a 321-candidate calendar is that it
        # must not move this. `eligible_event_counts` carries an explanatory
        # note beside the integers, so only the integers are checked.
        counts = registry["eligible_event_counts"]
        check("11h. and the registry still counts ZERO eligible events",
              counts["HYP-04"] == 0
              and all(v == 0 for v in counts.values() if isinstance(v, int)),
              str(counts))
    else:
        skip("11g. threshold matches the registry", "registry v1.9 not present")

    check("11i. the artifact says in words that it moves no gate",
          "moves no gate" in published["what_this_is_not"]
          and "CLOSED" in published["what_this_is_not"])


def test_10_offline_suite() -> None:
    print("\n--- 10: the suite itself is offline ---")
    try:
        socket.getaddrinfo("data.sec.gov", 443)
        check("10. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("10. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_item_codes_are_exact_tokens()
    test_2_the_item_code_means_different_things_by_era()
    test_3_deduplication_keeps_the_earliest_acceptance()
    test_4_legacy_recovery_is_opt_in()
    test_5_membership_bounds_are_respected()
    test_6_it_refuses_a_universe_it_cannot_stand_on()
    test_7_it_claims_nothing_about_eligibility()
    test_8_offline_and_through_the_cache()
    test_9_the_blind_era_is_measured_not_described()
    test_11_the_published_artifact_re_derives()
    test_10_offline_suite()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 ANCHOR CALENDAR TESTS PASSED")
