#!/usr/bin/env python3
"""HYP-04 peer-ceiling tests. FULLY OFFLINE -- sockets are blocked below.

The load-bearing tests here are not the counts. They are the two things that
could turn a review queue into evidence nobody curated:

  * test_4 -- the worklist can NEVER be loaded as a curated linkage map, in
    both directions (the builder refuses, and the real loader rejects the real
    file it wrote).
  * test_5 -- name resolution refuses to guess. Ambiguity, self-links and
    near-misses come back UNRESOLVED, and no scored or fuzzy match exists.

test_7 pins the distinction the whole module rests on: the CEILING is not
eligibility, and `CeilingReport` has no field that could be mistaken for it.

Run directly: python test_hyp04_supply_chain_hedge_peer_ceiling.py
"""
from __future__ import annotations

import csv
import io
import json
import socket
import sys
from datetime import date
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

from hyp04_supply_chain_hedge.anchor_shock import AnchorShock  # noqa: E402
from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    REQUIRED_FIELDS as CURATED_REQUIRED_FIELDS,
    load_curated_linkage,
)
from hyp04_supply_chain_hedge.peer_ceiling import (  # noqa: E402
    PEER_CEILING_RULE_ID,
    RESOLVED,
    UNRESOLVED_AMBIGUOUS,
    UNRESOLVED_NO_MATCH,
    UNRESOLVED_SELF_LINK,
    WORKLIST_FIELDS,
    Resolution,
    union_incremental,
    resolution_survivorship,
    CandidateRow,
    CeilingReport,
    CuratedSchemaLeak,
    build_name_index,
    build_worklist,
    events_from_calendar,
    measure_ceiling,
    normalize_company_name,
    refuse_if_curated_schema,
    resolve_counterparty,
    rule_description,
    shocks_from_rows,
    union_events,
    write_worklist_csv,
)

LSE = Path("Live Signal Engine")
CEILING = LSE / "HYP04_PEER_CEILING_2026-08-31_v3.json"
WORKLIST = LSE / "HYP04_PEER_CURATION_WORKLIST_2026-08-31_v3.csv"
CEILING_V2 = LSE / "HYP04_PEER_CEILING_2026-08-31_v2.json"
WORKLIST_V2 = LSE / "HYP04_PEER_CURATION_WORKLIST_2026-08-31_v2.csv"
# v1 is SUPERSEDED, not retargeted -- the same treatment the v1.7/v1.8/v1.9
# registry suites got. It is still checked, but only for the one property a
# superseded artifact must keep: being byte-identical to what it claimed.
CEILING_V1 = LSE / "HYP04_PEER_CEILING_2026-08-31.json"
WORKLIST_V1 = LSE / "HYP04_PEER_CURATION_WORKLIST_2026-08-31.csv"
CURATED_MAP = LSE / "HYP04_Linkage_Map_v1.0.csv"

TMAP = {
    "0": {"cik_str": 1, "ticker": "CSCO", "title": "Cisco Systems, Inc."},
    "1": {"cik_str": 2, "ticker": "NOK", "title": "Nokia Corporation"},
    "2": {"cik_str": 3, "ticker": "NOKBF", "title": "NOKIA CORP"},
    "3": {"cik_str": 4, "ticker": "MCK", "title": "McKesson Corporation"},
    "4": {"cik_str": 5, "ticker": "AAPL", "title": "Apple Inc."},
}


def _rows(p: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.open(p, encoding="utf-8", newline="")))


def test_1_normalisation_strips_form_and_nothing_else() -> None:
    print("\n--- 1: normalisation is structural, never semantic ---")
    n = normalize_company_name
    check("1a. suffixes go", n("Cisco Systems, Inc") == "CISCO SYSTEMS",
          n("Cisco Systems, Inc"))
    check("1b. punctuation goes", n("Micro-Star") == n("Micro Star"))
    check("1c. leading 'The' goes", n("The ODP Corporation") == "ODP")
    check("1d. ampersand normalises",
          n("Procter & Gamble") == n("Procter and Gamble"))
    # The failure this guards: collapsing two genuinely different companies.
    check("1e. a real word is NOT stripped as a suffix",
          n("Atlantic") != n("Atlantic Semiconductor"),
          f"{n('Atlantic')} vs {n('Atlantic Semiconductor')}")
    check("1f. interior tokens survive",
          n("Quanta Computer Incorporated") == "QUANTA COMPUTER")
    check("1g. an all-suffix name does not become empty-matching junk",
          n("The Company") == "", repr(n("The Company")))

    # THE REGRESSION. Stripping "Holding" resolved ADBE's 2006 disclosure of
    # "Ingram Micro" onto INGM / Ingram Micro Holding Corp, CIK 1897762 --
    # first SEC filing 2022-04-13, sixteen years later. HOLDING/HOLDINGS/GROUP
    # are not legal forms and must never rejoin NAME_SUFFIXES.
    check("1h. 'Holding' is NOT a legal form and is not stripped",
          n("Ingram Micro") != n("Ingram Micro Holding Corp"),
          f"{n('Ingram Micro')} vs {n('Ingram Micro Holding Corp')}")
    check("1i. nor is 'Group'", n("UBS") != n("UBS Group AG"))
    check("1j. nor 'Holdings'", n("Graham") != n("Graham Holdings Co"))
    from hyp04_supply_chain_hedge.peer_ceiling import NAME_SUFFIXES
    check("1k. and none of the three is in the suffix set",
          not ({"HOLDING", "HOLDINGS", "GROUP"} & set(NAME_SUFFIXES)),
          str(sorted(NAME_SUFFIXES)))


def test_2_the_ceiling_is_measured_from_the_real_join() -> None:
    print("\n--- 2: the ceiling comes from resolve_from_curated_map ---")
    if not CURATED_MAP.is_file():
        skip("2. ceiling", "no curated map on disk")
        return

    cal = [{"event_id": "MCK-2020-01-01", "anchor_ticker": "MCK",
            "release_date": "2020-01-01"},
           {"event_id": "MCK-2001-01-01", "anchor_ticker": "MCK",
            "release_date": "2001-01-01"}]
    # NO PKG EVENT, mirroring the real calendar: PKG is not in the anchor
    # universe, so the PKG->ODP edge is never evaluated at all. Adding one
    # here would make ODP eligible and quietly destroy what 2f tests.
    shocks = {e["event_id"]: AnchorShock(
        event_id=e["event_id"], anchor_ticker=e["anchor_ticker"],
        session=e["release_date"], anchor_return=0.01, benchmark_return=0.0,
        excess_return=0.01, shock=0.01) for e in cal}

    r = measure_ceiling(events_from_calendar(cal), shocks,
                        map_path=CURATED_MAP, curated_peers=["CVS", "ODP"],
                        floor=193)
    check("2a. measured is zero while no price source exists",
          r.measured_pairs == 0, str(r.measured_pairs))
    check("2b. and every measured denial includes P5",
          "P5" in r.measured_denials, str(r.measured_denials))
    check("2c. the ceiling clears P5 and admits the post-as_of event",
          r.ceiling_pairs == 1, str(r.ceiling_pairs))
    check("2d. the pre-as_of event still dies on P3",
          r.ceiling_denials.get("P3") == 1, str(r.ceiling_denials))
    check("2e. P5 is gone from the ceiling run",
          "P5" not in r.ceiling_denials, str(r.ceiling_denials))
    # The finding the whole artifact turns on.
    check("2f. a peer with no anchor events is reported as NEVER EVALUATED, "
          "not as denied", r.peers_never_evaluated == ("ODP",),
          str(r.peers_never_evaluated))
    check("2g. shortfall is computed against the floor",
          r.shortfall == 192, str(r.shortfall))
    check("2h. and the ceiling does not reach it", r.reaches_floor is False)


def test_3_worklist_counts_are_anchor_side_and_strict() -> None:
    print("\n--- 3: a candidate's count needs no peer, and excludes denials ---")
    cal = [{"event_id": "A-1", "anchor_ticker": "JBL", "release_date": "2010-01-01"},
           {"event_id": "A-2", "anchor_ticker": "JBL", "release_date": "2000-01-01"},
           {"event_id": "A-3", "anchor_ticker": "JBL", "release_date": "2011-01-01"},
           {"event_id": "A-4", "anchor_ticker": "NKE", "release_date": "2011-01-01"}]
    shk = [{"event_id": "A-1", "status": "shock_computed"},
           {"event_id": "A-2", "status": "shock_computed"},
           {"event_id": "A-3", "status": "denied_session"},
           {"event_id": "A-4", "status": "shock_computed"}]
    q = [{"ticker": "JBL", "named_counterparties": [
        {"counterparty": "Cisco Systems, Inc", "earliest_filing_date": "2005-01-01",
         "earliest_accession": "X", "filings_naming_it": 3}]}]

    rows = build_worklist(q, calendar_rows=cal, shock_rows=shk,
                          name_index=build_name_index(TMAP), anchors=["JBL"])
    check("3a. one candidate row", len(rows) == 1, str(len(rows)))
    r = rows[0]
    check("3b. only the post-as_of, shock-carrying event counts",
          r.event_ids == ("A-1",), str(r.event_ids))
    check("3c. the pre-as_of event is excluded", "A-2" not in r.event_ids)
    check("3d. the DENIED event is excluded even though it is post-as_of",
          "A-3" not in r.event_ids)
    check("3e. another anchor's events never leak in", "A-4" not in r.event_ids)
    check("3f. the ticker resolved without touching any peer data",
          r.resolution.ticker == "CSCO", r.resolution.ticker)

    # The union is the only honest aggregate.
    two = [r, CandidateRow(anchor_ticker="JBL", counterparty="x",
                           normalized_name="X",
                           resolution=resolve_counterparty("x", {},
                                                           anchor_ticker="JBL"),
                           as_of_date="2005-01-01", accession="Y",
                           filings_naming_it=1, event_ids=("A-1",))]
    check("3g. overlapping candidates union rather than sum",
          len(union_events(two)) == 1
          and sum(x.max_anchor_events for x in two) == 2)

    # INCREMENTAL: a candidate the curated map already covers buys nothing,
    # however large its gross count. Two real rows were exactly this.
    rows2 = build_worklist(q, calendar_rows=cal, shock_rows=shk,
                           name_index=build_name_index(TMAP), anchors=["JBL"],
                           already_reachable={"A-1"})
    r2 = rows2[0]
    check("3h. gross is unchanged by what is already reachable",
          r2.max_anchor_events == 1, str(r2.max_anchor_events))
    check("3i. but incremental is zero", r2.incremental_anchor_events == 0,
          str(r2.incremental_anchor_events))
    check("3j. and the row is flagged DOMINATED", r2.dominated)
    check("3k. a row with no events at all is not 'dominated'",
          not CandidateRow(anchor_ticker="X", counterparty="y",
                           normalized_name="Y",
                           resolution=resolve_counterparty("y", {},
                                                           anchor_ticker="X"),
                           as_of_date="2020-01-01", accession="A",
                           filings_naming_it=1).dominated)
    check("3l. union_incremental subtracts what the map reaches",
          len(union_incremental(rows2)) == 0)


def test_4_the_worklist_can_never_pass_as_a_curated_map() -> None:
    print("\n--- 4: the schemas are provably disjoint (BOTH directions) ---")
    missing = [f for f in CURATED_REQUIRED_FIELDS if f not in WORKLIST_FIELDS]
    check("4a. the worklist header omits curated required fields",
          bool(missing), f"omits {missing}")
    check("4b. and specifically claims no reviewer",
          "curated_by" not in WORKLIST_FIELDS and
          "review_status" not in WORKLIST_FIELDS)
    check("4c. and no relationship_type or confidence",
          "relationship_type" not in WORKLIST_FIELDS and
          "confidence" not in WORKLIST_FIELDS)
    check("4d. the real header passes its own guard",
          refuse_if_curated_schema(WORKLIST_FIELDS) is None)

    # CONTROL: the guard must actually fire, or 4d proves nothing.
    fired = False
    try:
        refuse_if_curated_schema(list(WORKLIST_FIELDS) + list(CURATED_REQUIRED_FIELDS))
    except CuratedSchemaLeak:
        fired = True
    check("4e. CONTROL: it refuses a header that WOULD satisfy the loader",
          fired)

    # And the other direction, against the real file the runner wrote.
    if not WORKLIST.is_file():
        skip("4f. real-file rejection", "no worklist artifact on disk")
        return
    res = load_curated_linkage(WORKLIST)
    check("4f. load_curated_linkage REJECTS the published worklist",
          not res.ok or len(res.edges) == 0,
          f"ok={res.ok} edges={len(res.edges)}")
    check("4g. and it rejects it on the HEADER, not row by row",
          res.header_matched is False, str(res.header_matched))


def test_5_resolution_refuses_to_guess() -> None:
    print("\n--- 5: exact or UNRESOLVED; there is no third answer ---")
    idx = build_name_index(TMAP)
    r = resolve_counterparty("Cisco Systems, Inc", idx, anchor_ticker="JBL")
    check("5a. an exact normalised title resolves",
          r.resolved and r.ticker == "CSCO", r.status)
    check("5b. and carries the SEC entry that matched",
          r.sec_title == "Cisco Systems, Inc." and r.sec_cik == "1",
          f"{r.sec_title}/{r.sec_cik}")

    r = resolve_counterparty("Nokia Corporation", idx, anchor_ticker="JBL")
    check("5c. two SEC filers sharing a name is AMBIGUOUS, not a coin flip",
          r.status == UNRESOLVED_AMBIGUOUS and not r.ticker, r.status)
    check("5d. and both candidates are reported",
          r.candidates == ("NOK", "NOKBF"), str(r.candidates))

    r = resolve_counterparty("McKesson Corporation", idx, anchor_ticker="MCK")
    check("5e. a self-link is UNRESOLVED with the reason visible",
          r.status == UNRESOLVED_SELF_LINK and not r.ticker, r.status)

    r = resolve_counterparty("Asustek Computer", idx, anchor_ticker="NVDA")
    check("5f. a near-miss is a non-match, never a nearest neighbour",
          r.status == UNRESOLVED_NO_MATCH and not r.ticker, r.status)
    r = resolve_counterparty("Cisco", idx, anchor_ticker="JBL")
    check("5g. a genuine PREFIX of a real title does not match",
          r.status == UNRESOLVED_NO_MATCH, r.status)
    r = resolve_counterparty("Apple", idx, anchor_ticker="JBL")
    check("5g2. but a name differing only by a stripped suffix DOES",
          r.resolved and r.ticker == "AAPL", r.status)

    # Asserted against the IMPORTS, not the prose -- the module's own
    # docstring says "no fuzzy matching", which a substring check trips on.
    check("5h. Resolution carries no score field that a caller could act on",
          not any(f in Resolution.__dataclass_fields__
                  for f in ("score", "confidence", "similarity", "distance")),
          str(sorted(Resolution.__dataclass_fields__)))


def test_6_shock_and_event_readers_fail_closed() -> None:
    print("\n--- 6: a denied event is not a shock of zero ---")
    rows = [{"event_id": "A", "anchor_ticker": "MCK", "attributed_session": "2020-01-02",
             "anchor_return": "0.01", "benchmark_return": "0.0",
             "excess_return": "0.01", "shock": "0.01", "status": "shock_computed"},
            {"event_id": "B", "anchor_ticker": "MCK", "attributed_session": "",
             "anchor_return": "", "benchmark_return": "", "excess_return": "",
             "shock": "", "status": "denied_session"},
            {"event_id": "C", "anchor_ticker": "MCK", "attributed_session": "2020-01-02",
             "anchor_return": "not-a-number", "benchmark_return": "0.0",
             "excess_return": "0.01", "shock": "0.01", "status": "shock_computed"}]
    s = shocks_from_rows(rows)
    check("6a. computed rows become shocks", "A" in s)
    check("6b. a denied row is ABSENT, not zero", "B" not in s)
    check("6c. and absent means P1 denies it downstream, which is correct",
          s.get("B") is None)
    check("6d. an unparseable row is dropped rather than coerced", "C" not in s)

    cal = [{"event_id": "A", "anchor_ticker": "MCK", "release_date": "2020-01-01"}]
    ev = events_from_calendar(cal)
    # AMC events attribute to the NEXT session; using it would widen the
    # point-in-time window by a day in the permissive direction.
    check("6e. event_date is the RELEASE date, not the attributed session",
          ev[0]["event_date"] == "2020-01-01", ev[0]["event_date"])


def test_7_a_ceiling_is_not_an_eligibility_count() -> None:
    print("\n--- 7: the word 'eligible' stays with pair_eligibility ---")
    r = CeilingReport()
    check("7a. CeilingReport has no 'eligible' attribute",
          not hasattr(r, "eligible"))
    d = r.as_dict()
    check("7b. and the ceiling block never uses the word",
          "eligible" not in json.dumps(d["ceiling_peer_prices_assumed"]),
          json.dumps(d["ceiling_peer_prices_assumed"])[:120])
    check("7c. the ceiling is labelled with its hypothetical in the key name",
          "ceiling_peer_prices_assumed" in d)
    rd = rule_description()
    check("7d. the rule says outright it is not eligibility",
          "eligibility" in rd["what_the_ceiling_is_not"].lower())
    check("7e. and that it opens no gate",
          "closed" in rd["opens_no_gate"].lower())
    check("7f. the rule id is stable", r.rule_id == PEER_CEILING_RULE_ID)


def test_8_the_published_artifacts_agree_with_a_fresh_derivation() -> None:
    print("\n--- 8: the artifacts are re-derived, not trusted ---")
    if not (CEILING.is_file() and WORKLIST.is_file()):
        skip("8. artifacts", "peer-ceiling artifacts not on disk")
        return
    doc = json.loads(CEILING.read_text(encoding="utf-8"))
    rows = _rows(WORKLIST)

    check("8a. the worklist header is exactly WORKLIST_FIELDS",
          tuple(rows[0].keys()) == WORKLIST_FIELDS if rows else False)
    check("8b. row count matches the summary",
          len(rows) == doc["worklist"]["rows_written"], str(len(rows)))
    res = [r for r in rows if r["candidate_peer_ticker"]]
    check("8c. resolved count matches",
          len(res) == doc["worklist"]["ticker_resolved"], str(len(res)))
    check("8d. EVERY resolved row demands lineage review",
          all(r["requires_lineage_review"] == "yes" for r in res))
    check("8e. and no unresolved row carries a ticker",
          all(not r["candidate_peer_ticker"] for r in rows
              if r["resolution"] != RESOLVED and
              r["resolution"].startswith("UNRESOLVED")))
    check("8f. rows are ranked by INCREMENTAL opportunity, descending",
          [int(r["incremental_anchor_events"]) for r in rows]
          == sorted((int(r["incremental_anchor_events"]) for r in rows),
                    reverse=True))
    check("8f2. incremental never exceeds gross",
          all(int(r["incremental_anchor_events"]) <= int(r["max_anchor_events"])
              for r in rows))
    dom = [r for r in rows if r["dominated_by_curated_map"] == "yes"]
    check("8f3. dominated rows are exactly those adding nothing",
          all(int(r["incremental_anchor_events"]) == 0 for r in dom)
          and len(dom) == doc["worklist"]["dominated_by_curated_map"],
          f"{len(dom)} flagged")
    check("8f4. and some row IS dominated, so the flag is not vacuous",
          len(dom) > 0, str(len(dom)))
    check("8f5. INGM is gone from the worklist entirely",
          all(r["candidate_peer_ticker"] != "INGM" for r in rows))
    check("8g. every row cites the accession that disclosed it",
          all(r["earliest_accession"] for r in rows))

    # The claim the finding rests on, now stated as the REACHABLE TOTAL
    # rather than v1's gross union, which counted events the curated map
    # already reaches.
    w = doc["worklist"]
    check("8h. the reachable total clears the floor",
          w["total_reachable_if_resolved_curated"] >= 193,
          str(w["total_reachable_if_resolved_curated"]))
    check("8h2. and it equals incremental plus the curated ceiling",
          w["total_reachable_if_resolved_curated"]
          == w["incremental_ticker_resolved_only"]
          + doc["ceiling"]["ceiling_peer_prices_assumed"]
              ["anchor_events_with_a_peer"],
          str(w["total_reachable_if_resolved_curated"]))
    check("8h3. incremental is strictly below the gross union it corrects",
          w["incremental_ticker_resolved_only"]
          < w["union_ticker_resolved_only"],
          f"{w['incremental_ticker_resolved_only']} < "
          f"{w['union_ticker_resolved_only']}")
    check("8i. and the CURATED ceiling does not",
          doc["ceiling"]["ceiling_reaches_floor"] is False)
    check("8j. the artifact makes no network claim",
          doc["sources"]["requests_made"] == 0,
          str(doc["sources"]["requests_made"]))
    check("8k. ODP is recorded as never evaluated",
          doc["ceiling"]["peers_never_evaluated"] == ["ODP"],
          str(doc["ceiling"]["peers_never_evaluated"]))

    # SUPERSESSION INTEGRITY. v1 must still be on disk and must still hash to
    # what v2 says it hashed to. A superseded artifact that quietly changed
    # would make the correction unauditable.
    import hashlib
    for name, path in (("ceiling", CEILING_V1), ("worklist", WORKLIST_V1),
                       ("ceiling", CEILING_V2), ("worklist", WORKLIST_V2)):
        claimed = (doc.get("supersedes_sha256") or {}).get(path.name)
        if not path.is_file():
            check(f"8l. superseded {name} v1 is still on disk", False,
                  str(path))
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        check(f"8l. superseded {name} {path.name} is byte-identical to "
              "the current artifact's claim", claimed == actual,
              f"{claimed} vs {actual}")
    check("8m. it records what it changed from v1",
          len(doc.get("what_changed_from_v1") or []) >= 2)
    check("8m2. and from v2",
          len(doc.get("what_changed_from_v2") or []) >= 1)


def test_9_the_gate_is_untouched() -> None:
    print("\n--- 9: nothing here moves the display gate ---")
    from hyp04_supply_chain_hedge.display_gate import current_decision
    d = current_decision()
    check("9a. the gate is still CLOSED", d.status == "CLOSED", d.status)
    check("9b. C4 is still MET",
          d.conditions.get("C4_decisions_resolved") is True,
          str(d.conditions.get("C4_decisions_resolved")))
    check("9c. exactly 4 denials", len(d.denials) == 4, str(len(d.denials)))
    check("9d. and the eligible count is still zero",
          d.evidence.get("eligible_event_count") == 0,
          str(d.evidence.get("eligible_event_count")))


def test_10_the_module_reaches_no_provider() -> None:
    print("\n--- 10: import boundary ---")
    import ast
    tree = ast.parse(io.open("hyp04_supply_chain_hedge/peer_ceiling.py",
                             encoding="utf-8").read())
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    for bad in ("yfinance", "requests", "pandas", "numpy", "urllib",
                "difflib", "rapidfuzz", "fuzzywuzzy", "Levenshtein"):
        check(f"10. peer_ceiling does not import {bad}", bad not in mods,
              str(sorted(mods)))




def test_11_the_resolver_can_only_ever_return_survivors() -> None:
    print("\n--- 11: the resolution method is survivorship-biased by "
          "construction ---")
    # A queue where one counterparty survives and one did not. The SEC map is
    # a list of CURRENT filers, so the second cannot resolve at all -- there
    # is nothing to match it against, however good the matcher is.
    idx = build_name_index({
        "0": {"cik_str": 1, "ticker": "CSCO", "title": "Cisco Systems, Inc."}})
    cal = [{"event_id": f"J-{i}", "anchor_ticker": "JBL",
            "release_date": f"20{10 + i}-01-01"} for i in range(4)]
    shk = [{"event_id": r["event_id"], "status": "shock_computed"} for r in cal]
    q = [{"ticker": "JBL", "named_counterparties": [
        {"counterparty": "Cisco Systems, Inc", "earliest_filing_date": "2011-06-01",
         "earliest_accession": "A", "filings_naming_it": 2},
        {"counterparty": "Marconi Communications",
         "earliest_filing_date": "2009-06-01",
         "earliest_accession": "B", "filings_naming_it": 2}]}]
    rows = build_worklist(q, calendar_rows=cal, shock_rows=shk,
                          name_index=idx, anchors=["JBL"])
    rep = resolution_survivorship(rows)

    check("11a. the survivor resolves", rep["resolved"] == 1, str(rep))
    check("11b. the non-survivor does not", rep["unresolved"] == 1)
    check("11c. and it is a plain non-match, not a near miss",
          rep["unresolved_by_reason"].get(UNRESOLVED_NO_MATCH) == 1,
          str(rep["unresolved_by_reason"]))
    # The measurement that matters: sample sitting behind unreachable names.
    check("11d. events behind unresolvable names are counted",
          rep["incremental_events_behind_unresolvable_names"] > 0,
          str(rep["incremental_events_behind_unresolvable_names"]))
    check("11e. reachable + behind accounts for the queue total",
          rep["incremental_events_reachable_by_resolution"]
          + rep["incremental_events_behind_unresolvable_names"]
          == rep["incremental_events_total_in_queue"],
          str(rep))
    check("11f. the biggest unreachable counterparties are named",
          any(x["counterparty"] == "Marconi Communications"
              for x in rep["largest_unresolvable_counterparties"]))
    check("11g. it says the limit is structural, not a matcher problem",
          "by construction" in rep["why_this_is_structural"])
    check("11h. and refuses the overclaim that all of them are delisted",
          "not claim" in rep["what_it_does_not_claim"].lower()
          or "does not claim" in rep["what_it_does_not_claim"].lower()
          or "That every" in rep["what_it_does_not_claim"])

    # CONTROL: with every name resolvable, nothing is behind the method.
    idx2 = build_name_index({
        "0": {"cik_str": 1, "ticker": "CSCO", "title": "Cisco Systems, Inc."},
        "1": {"cik_str": 2, "ticker": "MRCY", "title": "Marconi Communications"}})
    rows2 = build_worklist(q, calendar_rows=cal, shock_rows=shk,
                           name_index=idx2, anchors=["JBL"])
    rep2 = resolution_survivorship(rows2)
    check("11i. CONTROL: all resolvable leaves nothing behind",
          rep2["incremental_events_behind_unresolvable_names"] == 0
          and rep2["unresolved"] == 0, str(rep2["unresolved"]))

    # And against the published artifact.
    if CEILING.is_file():
        real = json.loads(CEILING.read_text(encoding="utf-8"))
        rs = real.get("resolution_survivorship") or {}
        check("11j. the artifact carries the measurement", bool(rs))
        check("11k. with a non-trivial amount of sample behind it",
              rs.get("incremental_events_behind_unresolvable_names", 0) > 0,
              str(rs.get("incremental_events_behind_unresolvable_names")))
        check("11l. and its parts still sum to the total",
              rs.get("incremental_events_reachable_by_resolution", 0)
              + rs.get("incremental_events_behind_unresolvable_names", 0)
              == rs.get("incremental_events_total_in_queue"),
              str(rs.get("incremental_events_total_in_queue")))


if __name__ == "__main__":
    test_1_normalisation_strips_form_and_nothing_else()
    test_2_the_ceiling_is_measured_from_the_real_join()
    test_3_worklist_counts_are_anchor_side_and_strict()
    test_4_the_worklist_can_never_pass_as_a_curated_map()
    test_5_resolution_refuses_to_guess()
    test_6_shock_and_event_readers_fail_closed()
    test_7_a_ceiling_is_not_an_eligibility_count()
    test_8_the_published_artifacts_agree_with_a_fresh_derivation()
    test_9_the_gate_is_untouched()
    test_10_the_module_reaches_no_provider()
    test_11_the_resolver_can_only_ever_return_survivors()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PEER-CEILING TESTS PASSED")
