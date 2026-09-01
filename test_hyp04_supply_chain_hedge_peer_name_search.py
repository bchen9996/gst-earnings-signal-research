#!/usr/bin/env python3
"""HYP-04 peer name-search tests. FULLY OFFLINE -- sockets blocked below.

The load-bearing tests:

  * test_3 -- a FAILED search is UNANSWERED, never "no registrant matched".
    The first live run lost 8 of 24 names to 503s and recorded every one as a
    negative finding about the company. That is data availability deciding a
    result.
  * test_2 -- acceptance is the lineage test, not the search. Two accepted
    registrants is AMBIGUOUS and resolves to nothing.
  * test_4 -- a registrant identified but no longer traded is a RESULT, and it
    is never counted as tradeable.

Run directly: python test_hyp04_supply_chain_hedge_peer_name_search.py
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

from hyp04_supply_chain_hedge.peer_name_search import (  # noqa: E402
    MAX_CANDIDATES_PER_NAME,
    PEER_NAME_SEARCH_RULE_ID,
    STATUS_AMBIGUOUS,
    STATUS_NO_HITS,
    STATUS_NO_LINEAGE_MATCH,
    STATUS_RESOLVED,
    STATUS_RESOLVED_NOT_TRADED,
    STATUS_SEARCH_FAILED,
    decide,
    parse_candidate_ciks,
    parse_conformed_names,
    rule_description,
    search_url,
    summarise,
)

LSE = Path("Live Signal Engine")
ARTIFACT = LSE / "HYP04_PEER_NAME_SEARCH_2026-09-01.json"

SINGLE = """<feed><company-info><cik>0000826083</cik>
<conformed-name>DELL INC</conformed-name>
<formerly-names count="1"><names><date>2003-07-22</date>
<name>DELL COMPUTER CORP</name></names></formerly-names>
</company-info></feed>"""

# The multi-match shape, with SEC's own ARRAY(0x...) bug where the name
# should be. This is why names are never read from a list response.
MULTI = """<feed>
<entry title="ARRAY(0x55f65cb07f30)"><content><company-info name="ARRAY(0x1)">
<cik>0000826083</cik></company-info></content></entry>
<entry title="ARRAY(0x2)"><content><company-info name="ARRAY(0x3)">
<cik>0001855280</cik></company-info></content></entry>
</feed>"""

TICKERS = {"0000858877": "CSCO"}


def test_1_both_response_shapes_yield_ciks() -> None:
    print("\n--- 1: CIKs parse from both shapes; names only from one ---")
    check("1a. single-match yields its CIK",
          parse_candidate_ciks(SINGLE) == ["0000826083"],
          str(parse_candidate_ciks(SINGLE)))
    check("1b. multi-match yields all CIKs in order",
          parse_candidate_ciks(MULTI) == ["0000826083", "0001855280"],
          str(parse_candidate_ciks(MULTI)))
    check("1c. CIKs are zero-padded to 10",
          all(len(c) == 10 for c in parse_candidate_ciks(MULTI)))
    check("1d. duplicates collapse",
          parse_candidate_ciks(SINGLE + SINGLE) == ["0000826083"])
    check("1e. the candidate cap is enforced",
          len(parse_candidate_ciks(
              "".join(f"<cik>{i:010d}</cik>" for i in range(50))))
          == MAX_CANDIDATES_PER_NAME)
    check("1f. a name IS readable from the single-match shape",
          parse_conformed_names(SINGLE) == ["DELL INC"],
          str(parse_conformed_names(SINGLE)))
    # The reason names are never trusted from a list.
    check("1g. and SEC's ARRAY(0x...) bug is filtered out, not returned",
          parse_conformed_names(MULTI) == [], str(parse_conformed_names(MULTI)))
    check("1h. empty input is handled",
          parse_candidate_ciks("") == [] and parse_conformed_names("") == [])

    u = search_url("Dell Computer")
    check("1i. the search URL sets NO form-type filter",
          "type=" not in u, u)
    check("1j. and asks for atom", "output=atom" in u)


def test_2_acceptance_is_the_lineage_test_not_the_search() -> None:
    print("\n--- 2: the search only nominates; lineage decides ---")
    r = decide(anchor_ticker="JBL", counterparty="Cisco Systems, Inc",
               as_of_date="2002-11-25",
               accepted=[("0000858877", "CISCO SYSTEMS INC")],
               candidates_examined=3, ticker_for_cik=TICKERS)
    check("2a. one lineage-accepted registrant resolves",
          r.status == STATUS_RESOLVED and r.peer_ticker == "CSCO", r.status)
    check("2b. and it is reported tradeable", r.tradeable)
    check("2c. carrying the name in force at the disclosure date",
          r.registrant_name_at_as_of == "CISCO SYSTEMS INC")

    # Candidates found, none surviving the lineage test.
    r2 = decide(anchor_ticker="JBL", counterparty="X", as_of_date="2002-11-25",
                accepted=[], candidates_examined=8, ticker_for_cik=TICKERS)
    check("2d. hits with no lineage match is its own status",
          r2.status == STATUS_NO_LINEAGE_MATCH, r2.status)
    check("2e. and is NOT resolved", not r2.resolved)

    # Two registrants matching at the same date is a question, not an answer.
    r3 = decide(anchor_ticker="JBL", counterparty="X", as_of_date="2002-11-25",
                accepted=[("0000000001", "A"), ("0000000002", "B")],
                candidates_examined=8, ticker_for_cik=TICKERS)
    check("2f. two accepted registrants is AMBIGUOUS",
          r3.status == STATUS_AMBIGUOUS, r3.status)
    check("2g. and resolves to no ticker at all",
          not r3.peer_ticker and not r3.resolved)
    check("2h. with both CIKs reported for the curator",
          r3.accepted_ciks == ("0000000001", "0000000002"))

    r4 = decide(anchor_ticker="JBL", counterparty="X", as_of_date="2002-11-25",
                accepted=[], candidates_examined=0, ticker_for_cik=TICKERS)
    check("2i. no candidates at all is no_registrant_matched",
          r4.status == STATUS_NO_HITS, r4.status)


def test_3_a_failed_search_is_unanswered_not_negative() -> None:
    print("\n--- 3: an outage is not a finding about the company ---")
    r = decide(anchor_ticker="JBL", counterparty="Lenovo Group Limited",
               as_of_date="2013-02-19", accepted=[], candidates_examined=0,
               ticker_for_cik=TICKERS, search_failed=True,
               failure="HTTPError: 503 Server Error")
    check("3a. a failed search gets its OWN status",
          r.status == STATUS_SEARCH_FAILED, r.status)
    # The exact bug: a failed search also has zero candidates, so without the
    # explicit check it fell through to "no registrant matched".
    check("3b. NOT no_registrant_matched, though it also had 0 candidates",
          r.status != STATUS_NO_HITS)
    check("3c. the failure is carried into the detail",
          "503" in r.detail, r.detail)
    check("3d. and it says the name is unanswered",
          "UNANSWERED" in r.detail or "unanswered" in r.detail.lower())
    check("3e. it is not resolved and not tradeable",
          not r.resolved and not r.tradeable)

    # CONTROL: the same inputs WITHOUT the failure flag must give the negative.
    ok = decide(anchor_ticker="JBL", counterparty="Lenovo Group Limited",
                as_of_date="2013-02-19", accepted=[], candidates_examined=0,
                ticker_for_cik=TICKERS)
    check("3f. CONTROL: without the flag the same input IS a negative",
          ok.status == STATUS_NO_HITS, ok.status)
    check("3g. so the two are genuinely distinguished", ok.status != r.status)


def test_4_identified_but_untradeable_is_a_result() -> None:
    print("\n--- 4: a confirmed registrant with no ticker is the finding ---")
    r = decide(anchor_ticker="ADBE", counterparty="Ingram Micro",
               as_of_date="2006-02-08",
               accepted=[("0001018003", "INGRAM MICRO INC")],
               candidates_examined=4, ticker_for_cik=TICKERS,
               incremental_anchor_events=29)
    check("4a. it resolves", r.resolved, r.status)
    check("4b. with its own status", r.status == STATUS_RESOLVED_NOT_TRADED)
    check("4c. but is NOT counted tradeable", not r.tradeable)
    check("4d. and carries no peer ticker", r.peer_ticker == "")
    check("4e. the registrant is named and cited",
          r.registrant_cik == "0001018003"
          and r.registrant_name_at_as_of == "INGRAM MICRO INC")
    check("4f. the detail calls it a measured survivorship loss",
          "survivorship" in r.detail.lower(), r.detail)
    check("4g. the sample it carries is retained",
          r.incremental_anchor_events == 29)
    check("4h. summarise counts by status",
          summarise([r, r]) == {STATUS_RESOLVED_NOT_TRADED: 2})


def test_5_the_rule_states_its_own_limits() -> None:
    print("\n--- 5: the rule is honest about the search ---")
    rd = rule_description()
    check("5a. it says the search is an undocumented prefix match",
          "prefix match" in rd["the_search_only_generates_candidates"]
          and "Nothing is accepted"
          in rd["the_search_only_generates_candidates"],
          rd["the_search_only_generates_candidates"][:80])
    check("5b. it names the lineage test as the acceptance rule",
          "CONTINUOUS" in rd["acceptance_is_the_lineage_test"])
    check("5c. it explains the missing form filter",
          "20-F" in rd["no_form_type_filter"])
    check("5d. it says an untradeable registrant is a result",
          "not a failure" in rd["a_resolved_registrant_may_not_trade"].lower())
    check("5e. it curates nothing",
          "no edge is written" in rd["curates_nothing"].lower(),
          rd["curates_nothing"])
    check("5f. rule id is stable", rd["rule_id"] == PEER_NAME_SEARCH_RULE_ID)


def test_6_the_published_artifact_is_coherent() -> None:
    print("\n--- 6: against the real search results ---")
    if not ARTIFACT.is_file():
        skip("6. artifact", "no name-search artifact on disk")
        return
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    res = d.get("results") or []
    check("6a. every name got a result",
          len(res) == sum((d.get("counts_by_status") or {}).values()),
          str(len(res)))
    check("6b. NO name was left unanswered after the retries",
          d.get("names_unanswered") == 0, str(d.get("names_unanswered")))
    check("6c. and no errors remain", not d.get("errors"), str(d.get("errors")))
    check("6d. the artifact states that unanswered is not a negative",
          "unanswered_is_not_a_negative" in d)

    ident = [r for r in res if r.get("resolved")]
    trade = [r for r in res if r.get("tradeable")]
    check("6e. registrants were identified", len(ident) > 0, str(len(ident)))
    check("6f. identified count agrees with the rows",
          d.get("names_identified") == len(ident))
    check("6g. tradeable count agrees with the rows",
          d.get("names_now_tradeable") == len(trade))
    check("6h. no identified registrant claims a ticker it has not got",
          all(r.get("peer_ticker") for r in trade)
          and all(not r.get("peer_ticker") for r in ident if not r.get("tradeable")))
    check("6i. the events behind untradeable registrants are summed",
          d.get("events_behind_identified_but_untradeable")
          == sum(r["incremental_anchor_events"] for r in ident
                 if not r.get("tradeable")),
          str(d.get("events_behind_identified_but_untradeable")))
    check("6j. it opens no gate", "CLOSED" in d.get("opens_no_gate", ""))


def test_7_the_module_reaches_no_endpoint() -> None:
    print("\n--- 7: import boundary ---")
    import ast
    tree = ast.parse(io.open("hyp04_supply_chain_hedge/peer_name_search.py",
                             encoding="utf-8").read())
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    for bad in ("requests", "http", "yfinance", "pandas"):
        check(f"7. peer_name_search does not import {bad}", bad not in mods,
              str(sorted(mods)))
    # urllib appears, and only for urlencode -- the module builds a URL but
    # never opens one. Asserted on the imported NAMES, not the package.
    names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("urllib"):
            names.update(a.name for a in n.names)
    check("7e. urllib is imported only for urlencode",
          names == {"urlencode"}, str(sorted(names)))
    check("7f. and urlopen/request are never imported",
          not (names & {"urlopen", "Request", "urlretrieve"}))


def test_8_the_gate_is_untouched() -> None:
    print("\n--- 8: nothing here moves the display gate ---")
    from hyp04_supply_chain_hedge.display_gate import current_decision
    d = current_decision()
    check("8a. gate CLOSED", d.status == "CLOSED", d.status)
    check("8b. C4 MET", d.conditions.get("C4_decisions_resolved") is True)
    check("8c. exactly 4 denials", len(d.denials) == 4, str(len(d.denials)))
    check("8d. eligible count still zero",
          d.evidence.get("eligible_event_count") == 0)


if __name__ == "__main__":
    test_1_both_response_shapes_yield_ciks()
    test_2_acceptance_is_the_lineage_test_not_the_search()
    test_3_a_failed_search_is_unanswered_not_negative()
    test_4_identified_but_untradeable_is_a_result()
    test_5_the_rule_states_its_own_limits()
    test_6_the_published_artifact_is_coherent()
    test_7_the_module_reaches_no_endpoint()
    test_8_the_gate_is_untouched()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PEER NAME-SEARCH TESTS PASSED")
