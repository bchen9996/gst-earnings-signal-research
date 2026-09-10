#!/usr/bin/env python3
"""Tests for the curated-map -> anchor-event join -- HYP-04.

The load-bearing property is NEGATIVE and it is about C5.

`FreezeRecord.uses_placeholder_linkage` is the sole input to display-gate
condition C5, the one condition standing between Phase 0's positional-synthetic
output and a displayed finding. This module exists so that flag is DERIVED from
what a run actually read rather than asserted by a caller. So the tests that
matter most are the ones proving it CANNOT be cleared without a real map:

  * no map file            -> placeholder (test_4)
  * map that fails to load -> placeholder (test_4)
  * map that loads but has zero usable edges -> placeholder (test_4)
  * a real map with edges  -> NOT placeholder (test_2, the control)

Without that last one a function hardcoded to return True would pass every
other case and be useless.

Offline. No network. Synthetic maps in temp directories; the committed map is
read but never written.

Run directly: python test_hyp04_supply_chain_hedge_linkage_resolution.py
"""
from __future__ import annotations

import socket
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.anchor_shock import (  # noqa: E402
    AnchorShock,
    shock_for_event,
)
from hyp04_supply_chain_hedge.curated_linkage import EXPECTED_HEADERS, LSE  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    FreezeRecord,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.linkage_resolution import (  # noqa: E402
    SOURCE_CURATED,
    SOURCE_PLACEHOLDER,
    LinkageProvenance,
    freeze_record_fields,
    resolve_from_curated_map,
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


HEADER = ",".join(EXPECTED_HEADERS)

GOOD_ROW = (
    "MCK,CVS,direct_customer,SYNTHETIC TEST ROW,high,"
    "10-K Customer Concentration Note,SYNTHETIC citation,,"
    "2013-05-07,filing date of source,high,SYNTHETIC TEST FIXTURE,"
    "test_fixture,2026-08-22,draft")

BAD_ROW = (
    "MCK,CVS,direct_customer,SYNTHETIC BAD ROW,,"          # blank confidence
    "10-K Customer Concentration Note,SYNTHETIC citation,,"
    "2013-05-07,filing date of source,high,SYNTHETIC TEST FIXTURE,"
    "test_fixture,2026-08-22,draft")


def _map(tmp: Path, *rows: str, name: str = "m.csv") -> Path:
    p = tmp / name
    p.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return p


ANCHOR_FOR_SHOCK = "MCK"


def _anchor_ok() -> AnchorShock:
    """A well-measured anchor shock: both legs present, session resolved."""
    s, denials = shock_for_event(
        event_id="EVT-1", anchor_ticker=ANCHOR_FOR_SHOCK,
        attributed_session="2026-02-17",
        anchor_return=-0.084, benchmark_return=-0.004)
    assert s is not None and not denials, denials
    return s


EVENTS = [
    {"event_id": "E-2020", "anchor": "MCK", "event_date": "2020-02-05"},
    {"event_id": "E-2010", "anchor": "MCK", "event_date": "2010-02-03"},
    {"event_id": "E-OTHER", "anchor": "NVDA", "event_date": "2024-05-22"},
]


def _resolve(p: Path, events=None, peer_history=None, elig=True):
    events = events if events is not None else EVENTS
    return resolve_from_curated_map(
        events, map_path=p,
        anchor_shock=({e["event_id"]: _anchor_ok() for e in events}
                            if elig else {}),
        peer_history=peer_history if peer_history is not None else {"CVS": True})


# ============ 1. the join attaches real peers ============================
def test_1_join_attaches_curated_peers() -> None:
    with tempfile.TemporaryDirectory() as t:
        panel = _resolve(_map(Path(t), GOOD_ROW))
        by_id = {ev["event_id"]: ev["peers"] for ev in panel.anchor_events}

        check("1a. the 2020 event gets CVS", by_id["E-2020"] == ["CVS"], str(by_id))
        check("1b. the 2010 event gets nothing -- edge postdates it",
              by_id["E-2010"] == [])
        check("1c. an anchor absent from the map gets nothing",
              by_id["E-OTHER"] == [])
        check("1d. every input event survives, none silently dropped",
              len(panel.anchor_events) == len(EVENTS))
        check("1e. the denial is P3, the point-in-time rule",
              panel.denial_reasons() == {"P3": 1}, str(panel.denial_reasons()))
        check("1f. counts reconcile",
              panel.pairs_eligible == 1 and panel.n_pairs == 1)


def test_2_incoming_positional_peers_are_replaced() -> None:
    """A positional list must never survive into a curated-linkage panel."""
    with tempfile.TemporaryDirectory() as t:
        evs = [dict(e, peers=["PEER_001", "PEER_002"]) for e in EVENTS]
        panel = _resolve(_map(Path(t), GOOD_ROW), events=evs)
        leaked = [p for ev in panel.anchor_events for p in ev["peers"]
                  if p.startswith("PEER_")]
        check("2a. synthetic positional peers are GONE", leaked == [], str(leaked))
        check("2b. replaced by the curated peer",
              [ev["peers"] for ev in panel.anchor_events] == [["CVS"], [], []])


# ============ 3. provenance is computed, not asserted ====================
def test_3_provenance_from_a_real_map() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _map(Path(t), GOOD_ROW)
        prov = _resolve(p).provenance
        check("3a. source is the curated map", prov.source == SOURCE_CURATED)
        check("3b. it records the file path", prov.source_path == str(p))
        check("3c. it hashes the file so drift is detectable",
              len(str(prov.source_sha256)) == 64)
        check("3d. it counts usable edges", prov.edges_usable == 1)
        check("3e. load_ok is True", prov.load_ok is True)
        # THE CONTROL. Without this a property hardcoded to True would pass
        # every negative case in test_4 and this module would be useless.
        check("3f. CONTROL -- a real map with edges is NOT placeholder",
              prov.uses_placeholder_linkage is False)


# ============ 4. C5 CANNOT be cleared without a real map =================
def test_4_placeholder_unless_genuinely_read() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        cases = {
            "no map file at all": tmp / "does_not_exist.csv",
            "map with headers only, zero edges": _map(tmp, name="empty.csv"),
            "map whose only row fails validation": _map(tmp, BAD_ROW, name="bad.csv"),
        }
        for label, p in cases.items():
            panel = _resolve(p)
            check(f"4a. '{label}' -> placeholder",
                  panel.provenance.uses_placeholder_linkage is True)
            check(f"4b. '{label}' -> freeze fields say placeholder",
                  freeze_record_fields(panel)["uses_placeholder_linkage"] is True)

        # A default-constructed provenance is placeholder too: the safe value
        # is the one you get by not thinking about it.
        check("4c. a default LinkageProvenance is placeholder",
              LinkageProvenance(source=SOURCE_PLACEHOLDER)
              .uses_placeholder_linkage is True)

        # freeze_record_fields must not offer the operator-process claims --
        # this module has no standing to assert them.
        ff = freeze_record_fields(_resolve(_map(tmp, GOOD_ROW, name="g.csv")))
        for forbidden in ("frozen", "analysis_commit_sha",
                          "analysis_lock_document",
                          "frozen_before_any_result_computed"):
            check(f"4d. freeze fields do NOT assert {forbidden!r}",
                  forbidden not in ff)


# ============ 5. end to end through the REAL gate ========================
def test_5_c5_clears_through_the_real_gate() -> None:
    with tempfile.TemporaryDirectory() as t:
        panel = _resolve(_map(Path(t), GOOD_ROW))
        ff = freeze_record_fields(panel)
        fr = FreezeRecord(frozen=True, analysis_commit_sha="0" * 40,
                          analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
                          frozen_before_any_result_computed=True, **ff)
        d = evaluate_gate(eligible_event_count=len(ff["eligible_event_ids"]),
                          freeze=fr)
        check("5a. C5 CLEARS on curated linkage",
              d.conditions["C5_not_placeholder"] is True, str(d.denials))
        check("5b. only events that got peers are frozen",
              ff["eligible_event_ids"] == ("E-2020",), str(ff["eligible_event_ids"]))
        check("5c. C2 still fails -- one event is not 193",
              d.conditions["C2_threshold"] is False)
        # C1 read False until registry v1.12 moved it on 2026-09-09. The claim
        # this line was making -- linkage is not activation -- is unchanged and
        # is now asserted at its source: C1 tracks the REGISTRY's status field,
        # which nothing in this fixture touches.
        check("5d. C1 tracks the registry, not linkage",
              d.conditions["C1_status"] is True
              and d.evidence["registry_status"] == "ACTIVE_COLLECTING",
              str(d.evidence.get("registry_status")))
        # And the gate is STILL closed on this fixture, for the reason 5c
        # gives: one event is not 193. An open C1 changes nothing about that.
        check("5e. the gate is still CLOSED here -- C2 alone is enough",
              d.open is False and [x for x in d.denials if x.startswith("C2")],
              str(d.denials))

        # CONTROL: the same events with no map must leave C5 shut.
        p2 = _resolve(Path(t) / "nope.csv")
        fr2 = FreezeRecord(frozen=True, analysis_commit_sha="0" * 40,
                           analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
                           frozen_before_any_result_computed=True,
                           **freeze_record_fields(p2))
        d2 = evaluate_gate(eligible_event_count=0, freeze=fr2)
        check("5f. CONTROL -- no map leaves C5 SHUT",
              d2.conditions["C5_not_placeholder"] is False)


# ============ 6. unknowns deny, they are never assumed ===================
def test_6_unknowns_deny() -> None:
    with tempfile.TemporaryDirectory() as t:
        p = _map(Path(t), GOOD_ROW)

        panel = _resolve(p, peer_history={})
        check("6a. a peer absent from the history map is denied (P5)",
              panel.pairs_eligible == 0
              and "P5" in panel.denial_reasons(), str(panel.denial_reasons()))

        panel = _resolve(p, peer_history={"CVS": False})
        check("6b. an explicit False is denied too", panel.pairs_eligible == 0)

        panel = _resolve(p, elig=False)
        check("6c. an event with no anchor eligibility is denied (P1)",
              panel.pairs_eligible == 0
              and "P1" in panel.denial_reasons(), str(panel.denial_reasons()))


# ============ 7. the committed map, if present ===========================
def test_7_the_committed_map() -> None:
    p = LSE / "HYP04_Linkage_Map_v1.0.csv"
    if not p.is_file():
        skip("7. committed curated map", "no HYP04_Linkage_Map_v1.0.csv yet")
        return
    before = p.read_bytes()
    panel = _resolve(p, events=[
        {"event_id": "E1", "anchor": "MCK", "event_date": "2020-02-05"},
        {"event_id": "E2", "anchor": "PKG", "event_date": "2024-04-22"}],
        peer_history={"CVS": True, "ODP": True})
    check("7a. the committed map yields real pairs", panel.pairs_eligible == 2,
          str([ev["peers"] for ev in panel.anchor_events]))
    check("7b. and is NOT placeholder",
          panel.provenance.uses_placeholder_linkage is False)
    check("7c. resolving never writes to the map", p.read_bytes() == before)


def test_8_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("8a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("8a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_join_attaches_curated_peers()
    test_2_incoming_positional_peers_are_replaced()
    test_3_provenance_from_a_real_map()
    test_4_placeholder_unless_genuinely_read()
    test_5_c5_clears_through_the_real_gate()
    test_6_unknowns_deny()
    test_7_the_committed_map()
    test_8_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 LINKAGE-RESOLUTION TESTS PASSED")
    sys.exit(0)
