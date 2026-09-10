#!/usr/bin/env python3
"""HYP-04 peer-lineage tests. FULLY OFFLINE -- sockets are blocked below.

The question this rule answers is "was the registrant bearing this ticker today
the company the filing named then?", and the way it fails is silent: a wrong
peer that trades and has prices produces a clean-looking sample.

So the load-bearing tests are the ones that pin the failure directions:

  * test_2 -- a registrant whose first filing POSTDATES the disclosure is a
    break. This is the real INGM case, with SEC's real dates.
  * test_3 -- `name_in_force` never assumes today's name applied before the
    former-name windows close, and an open-ended window covers nothing.
  * test_5 -- every gap fails closed to UNKNOWN, never to a pass.
  * test_6 -- the published audit carries a control that actually FIRED.

Run directly: python test_hyp04_supply_chain_hedge_peer_lineage.py
"""
from __future__ import annotations

import io
import json
import socket
import sys
from pathlib import Path

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


def _no_net(*a, **k):                                    # pragma: no cover
    raise AssertionError("this suite must make no network call")


socket.socket.connect = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.peer_lineage import (  # noqa: E402
    PEER_LINEAGE_RULE_ID,
    VERDICT_CONTINUOUS,
    VERDICT_NAME_NOT_IN_FORCE,
    VERDICT_NOT_YET_FILING,
    VERDICT_STOPPED_FILING,
    VERDICT_UNKNOWN,
    FilerHistory,
    FormerName,
    assess,
    filer_history,
    rule_description,
    summarise,
)

LSE = Path("Live Signal Engine")
AUDIT = LSE / "HYP04_PEER_LINEAGE_AUDIT_2026-08-31_v2.json"

# Shaped exactly like SEC's submissions payload, including the `files` shard
# that bounds the older filings.
SUBMISSIONS = {
    "cik": "0000064803",
    "name": "CVS HEALTH Corp",
    "formerNames": [
        {"name": "CVS CAREMARK CORP", "from": "2006-12-27T00:00:00.000Z",
         "to": "2014-09-03T00:00:00.000Z"},
        {"name": "CVS CORP", "from": "1997-02-07T00:00:00.000Z",
         "to": "2007-03-22T00:00:00.000Z"},
        {"name": "MELVILLE CORP", "from": "1994-03-31T00:00:00.000Z",
         "to": "1997-01-10T00:00:00.000Z"},
    ],
    "filings": {
        "recent": {"filingDate": ["2016-05-04", "2020-01-02", "2026-08-17"]},
        "files": [{"filingFrom": "1994-02-10", "filingTo": "2016-05-02",
                   "filingCount": 1500}],
    },
}


def test_1_history_is_derived_from_the_whole_record() -> None:
    print("\n--- 1: the shard bounds are part of the filing history ---")
    h = filer_history(SUBMISSIONS)
    check("1a. first filing comes from the SHARD, not from `recent`",
          h.first_filing == "1994-02-10", h.first_filing)
    check("1b. last filing comes from `recent`",
          h.last_filing == "2026-08-17", h.last_filing)
    # The failure this prevents: `recent` starts 2016, so trusting it alone
    # would date the first filing 22 years late and manufacture breaks.
    naive = min(SUBMISSIONS["filings"]["recent"]["filingDate"])
    check("1c. and that materially differs from the naive answer",
          h.first_filing < naive, f"{h.first_filing} vs {naive}")
    check("1d. former names are parsed with their windows",
          len(h.former_names) == 3 and h.former_names[0].start == "2006-12-27",
          str(h.former_names[:1]))
    check("1e. ISO timestamps are reduced to days",
          all(len(f.start) == 10 for f in h.former_names))
    check("1f. the shard's count is included", h.filings_counted == 1503,
          str(h.filings_counted))
    check("1g. an empty record is not 'known'", not filer_history({}).known)


def test_2_a_late_registrant_is_a_break() -> None:
    print("\n--- 2: the INGM case, with SEC's real dates ---")
    # Ingram Micro Holding Corp, CIK 1897762: first filing 2022-04-13.
    ingm = FilerHistory(cik="0001897762", current_name="Ingram Micro Holding Corp",
                        first_filing="2022-04-13", last_filing="2026-08-14")
    r = assess(ingm, disclosed_name="Ingram Micro", as_of_date="2006-02-08",
               anchor_ticker="ADBE", peer_ticker="INGM")
    check("2a. it is a lineage break", r.is_break, r.verdict)
    check("2b. specifically: first filing postdates the disclosure",
          r.verdict == VERDICT_NOT_YET_FILING, r.verdict)
    check("2c. and the detail names both dates",
          "2022-04-13" in r.detail and "2006-02-08" in r.detail, r.detail)
    check("2d. it does NOT clear the check", not r.clears_this_check)

    # The other direction: a registrant that stopped filing before.
    gone = FilerHistory(current_name="X", first_filing="1994-01-01",
                        last_filing="2010-01-01")
    r2 = assess(gone, disclosed_name="X", as_of_date="2016-01-01")
    check("2e. a registrant that stopped filing first is also a break",
          r2.verdict == VERDICT_STOPPED_FILING, r2.verdict)

    # CONTROL: the same rule must PASS a registrant that really was filing.
    r3 = assess(filer_history(SUBMISSIONS), disclosed_name="CVS Health",
                as_of_date="2016-05-05")
    check("2f. CONTROL: a registrant filing at the time is not a break",
          r3.verdict == VERDICT_CONTINUOUS, r3.verdict)


def test_3_the_name_in_force_is_looked_up_not_assumed() -> None:
    print("\n--- 3: today's name is never back-projected ---")
    h = filer_history(SUBMISSIONS)
    check("3a. a covered date returns the name in force THEN",
          h.name_in_force("2010-01-01") == "CVS CAREMARK CORP",
          str(h.name_in_force("2010-01-01")))
    check("3b. after every window closes, the current name applies",
          h.name_in_force("2016-05-05") == "CVS HEALTH Corp",
          str(h.name_in_force("2016-05-05")))
    # The load-bearing one: before the windows close, the record does not say.
    check("3c. BEFORE the windows close, it returns None rather than today's",
          h.name_in_force("1990-01-01") is None,
          str(h.name_in_force("1990-01-01")))
    check("3d. an unbounded former name covers nothing",
          not FormerName(name="X", start="2000-01-01", end="").covers("2001-01-01"))
    check("3e. and neither does one with no start",
          not FormerName(name="X", start="", end="2001-01-01").covers("2000-06-01"))

    # A registrant filing under a DIFFERENT name is reported, not decided.
    r = assess(h, disclosed_name="Melville Corporation", as_of_date="2010-01-01")
    check("3f. a name mismatch is REVIEW, not a break and not a pass",
          r.verdict == VERDICT_NAME_NOT_IN_FORCE, r.verdict)
    check("3g. and it does not clear the check", not r.clears_this_check)
    check("3h. nor is it counted as a break", not r.is_break)


def test_4_normalisation_is_shared_with_the_resolver() -> None:
    print("\n--- 4: the same normaliser decides both ---")
    h = filer_history(SUBMISSIONS)
    # "CVS Health" vs SEC's "CVS HEALTH Corp" differ only by legal form.
    r = assess(h, disclosed_name="CVS Health", as_of_date="2016-05-05")
    check("4a. legal-form differences do not create a mismatch",
          r.verdict == VERDICT_CONTINUOUS, r.verdict)
    r2 = assess(h, disclosed_name="CVS Health Corporation",
                as_of_date="2020-05-22")
    check("4b. nor does a spelled-out corporate suffix",
          r2.verdict == VERDICT_CONTINUOUS, r2.verdict)
    # But a HOLDING-style difference must NOT be normalised away -- that is
    # the defect the Ingram Micro case exposed in peer_ceiling.
    r3 = assess(FilerHistory(current_name="Ingram Micro Holding Corp",
                             first_filing="1990-01-01", last_filing="2026-01-01"),
                disclosed_name="Ingram Micro", as_of_date="2006-02-08")
    check("4c. 'Holding' is NOT normalised away, so this is a name mismatch",
          r3.verdict == VERDICT_NAME_NOT_IN_FORCE, r3.verdict)


def test_5_everything_unknown_fails_closed() -> None:
    print("\n--- 5: an unchecked registrant is not a checked one ---")
    r = assess(None, disclosed_name="X", as_of_date="2016-01-01")
    check("5a. no history at all is UNKNOWN", r.verdict == VERDICT_UNKNOWN,
          r.verdict)
    check("5b. and UNKNOWN never clears the check", not r.clears_this_check)
    check("5c. nor is it reported as a break", not r.is_break)
    r2 = assess(FilerHistory(current_name="X"), disclosed_name="X",
                as_of_date="2016-01-01")
    check("5d. an unbounded filing history is UNKNOWN",
          r2.verdict == VERDICT_UNKNOWN, r2.verdict)
    r3 = assess(filer_history(SUBMISSIONS), disclosed_name="X", as_of_date="")
    check("5e. a missing disclosure date is UNKNOWN",
          r3.verdict == VERDICT_UNKNOWN, r3.verdict)

    rd = rule_description()
    check("5f. the rule states that CONTINUOUS is weak",
          "one way of being wrong" in rd["what_continuous_does_not_mean"])
    check("5g. and that it promotes nothing",
          "no edge is written" in rd["promotes_nothing"])
    check("5h. rule id is stable",
          rd["rule_id"] == PEER_LINEAGE_RULE_ID)
    check("5i. summarise counts by verdict",
          summarise([r, r2, r3]) == {VERDICT_UNKNOWN: 3})


def test_6_the_published_audit_carries_a_control_that_fired() -> None:
    print("\n--- 6: a check never seen to fail is not known to work ---")
    if not AUDIT.is_file():
        skip("6. audit artifact", "no lineage audit on disk")
        return
    d = json.loads(AUDIT.read_text(encoding="utf-8"))
    c = d.get("control") or {}
    check("6a. the audit carries a control at all", bool(c))
    check("6b. and the control FIRED", c.get("is_lineage_break") is True,
          str(c.get("verdict")))
    check("6c. it is the case that motivated the rule",
          c.get("peer_ticker") == "INGM" and c.get("as_of_date") == "2006-02-08",
          f"{c.get('peer_ticker')} @ {c.get('as_of_date')}")
    check("6d. with SEC's own first-filing date as the evidence",
          c.get("registrant_first_filing", "") > c.get("as_of_date", ""),
          f"{c.get('registrant_first_filing')} vs {c.get('as_of_date')}")
    check("6e. the control is NOT counted among the candidates",
          all(a.get("peer_ticker") != "INGM"
              for a in d.get("assessments") or []))

    n = len(d.get("assessments") or [])
    check("6f. every resolved candidate was assessed", n == 7, str(n))
    check("6g. counts agree with the rows",
          sum((d.get("counts_by_verdict") or {}).values()) == n)
    check("6h. no candidate is claimed to be curated",
          "curated_by" not in json.dumps(d))
    check("6i. the audit says it opens no gate",
          "CLOSED" in d.get("opens_no_gate", ""))


def test_7_the_module_reaches_no_endpoint() -> None:
    print("\n--- 7: import boundary ---")
    import ast
    tree = ast.parse(io.open("hyp04_supply_chain_hedge/peer_lineage.py",
                             encoding="utf-8").read())
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    for bad in ("requests", "urllib", "http", "yfinance"):
        check(f"7. peer_lineage does not import {bad}", bad not in mods,
              str(sorted(mods)))
    # The live runner is deliberately named off the test_* pattern.
    check("7e. the live runner is not named like a test",
          Path("hyp04_supply_chain_hedge/run_peer_lineage_audit.py").is_file())


def test_8_the_gate_is_untouched() -> None:
    print("\n--- 8: nothing here moves the display gate ---")
    from hyp04_supply_chain_hedge.display_gate import current_decision
    d = current_decision()
    # OPENED 2026-09-09 (freeze attested + registry v1.12). Auditing peer
    # lineage is still not what opened it.
    check("8a. gate OPEN", d.status == "OPEN", d.status)
    check("8b. C4 MET", d.conditions.get("C4_decisions_resolved") is True)
    check("8c. zero denials", len(d.denials) == 0, str(d.denials))
    check("8d. the count is the frozen 214",
          d.evidence["eligible_event_count"] == 214,
          str(d.evidence["eligible_event_count"]))


if __name__ == "__main__":
    test_1_history_is_derived_from_the_whole_record()
    test_2_a_late_registrant_is_a_break()
    test_3_the_name_in_force_is_looked_up_not_assumed()
    test_4_normalisation_is_shared_with_the_resolver()
    test_5_everything_unknown_fails_closed()
    test_6_the_published_audit_carries_a_control_that_fired()
    test_7_the_module_reaches_no_endpoint()
    test_8_the_gate_is_untouched()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PEER-LINEAGE TESTS PASSED")
