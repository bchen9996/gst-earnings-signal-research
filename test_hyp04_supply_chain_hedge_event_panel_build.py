#!/usr/bin/env python3
"""HYP-04 panel assembler -- the derived count agrees with its inputs.

The artifact is recomputed here from the committed calendar, shocks, curated
map and peer closes, so the published count cannot drift from the evidence
without this failing.

Repo testing convention (hand-rolled check(), run directly, no pytest).
Offline: reads committed CSVs only.

Run directly: python test_hyp04_supply_chain_hedge_event_panel_build.py
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

import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_event_panel as M  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import evaluate_gate  # noqa: E402
from hyp04_supply_chain_hedge.linkage_resolution import (  # noqa: E402
    resolve_from_curated_map,
)

ART = M.OUT_JSON
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _art() -> dict:
    return json.loads(ART.read_text(encoding="utf-8"))


def test_1_the_artifact_exists_and_recomputes() -> None:
    check("1a. the panel artifact is on disk", ART.is_file(), str(ART))
    if not ART.is_file():
        return
    committed = _art()
    with tempfile.TemporaryDirectory() as td:
        fresh = M.build(out_json=Path(td) / "panel.json", force=True)
    volatile = {"artifact"}
    same = {k: v for k, v in fresh.items() if k not in volatile}
    old = {k: v for k, v in committed.items() if k not in volatile}
    check("1b. every published number recomputes from the committed inputs",
          same == old,
          f"differing keys: {sorted(k for k in old if old.get(k) != same.get(k))}")


def test_2_the_registered_unit_is_per_pair() -> None:
    a = _art()
    check("2a. the artifact names per-pair as the registered unit",
          a["unit_registered"] == "per_pair")
    check("2b. and cites the registry rather than asserting it",
          "MEASURABILITY" in a["unit_basis"] and "v1.11" in a["unit_basis"])
    check("2c. both units are published, not just the one that clears",
          "per_pair" in a and "per_peer" in a)


def test_3_the_unit_choice_is_worth_stating() -> None:
    """If the two units ever agreed, publishing both would be noise. They do not."""
    a = _art()
    pp, pq = a["per_pair"], a["per_peer"]
    check("3a. per-pair clears the registered floor",
          pp["reaches_floor"] is True,
          f"{pp['eligible_anchor_events']} vs {a['registered_floor']}")
    check("3b. per-peer does NOT clear it -- the choice decides the sample",
          pq["reaches_floor"] is False,
          f"{pq['eligible_anchor_events']} vs {a['registered_floor']}")
    check("3c. the cost of the unit is reported as a number",
          a["unit_costs_events"] == (pp["eligible_anchor_events"]
                                     - pq["eligible_anchor_events"]))
    check("3d. and it is large enough to matter",
          a["unit_costs_events"] > 0)


def test_4_the_per_peer_scoping_is_disclosed() -> None:
    """The per-peer unit's answer depends on the event list it ranges over."""
    a = _art()["per_peer_scoping"]
    s, all_ = a["scoped_to_p1_p3_survivors"], a["scoped_to_all_events"]
    check("4a. both scopings are published",
          "eligible_anchor_events" in s and "eligible_anchor_events" in all_)
    check("4b. they genuinely differ, so the scoping is not cosmetic",
          s["eligible_anchor_events"] != all_["eligible_anchor_events"],
          f"{s['eligible_anchor_events']} vs {all_['eligible_anchor_events']}")
    check("4c. the like-for-like comparison uses the survivor scoping",
          _art()["per_peer"] == s)


def test_5_the_registry_discrepancy_is_resolved() -> None:
    """Registry v1.11 section 10 left the two routes unreconciled by event set."""
    r = _art()["reconciliation"]
    check("5a. both routes are counted", r["assumed_prices_events"] > 0
          and r["real_coverage_events"] > 0)
    check("5b. the sets are compared by id, not just by count",
          "in_assumed_not_in_real" in r and "in_real_not_in_assumed" in r)
    check("5c. every differing event names the peer that failed coverage",
          all(r["why"].get(e, {}).get("peers_short")
              for e in r["in_assumed_not_in_real"]),
          str(r["why"]))
    check("5d. no event is eligible under real coverage but not under "
          "assumed prices -- that would mean coverage INVENTED a pair",
          r["in_real_not_in_assumed"] == [],
          str(r["in_real_not_in_assumed"]))


def test_6_the_floor_cannot_drift_unnoticed() -> None:
    seen = M.assert_floor_agreement()
    check("6a. every module's copy of the floor agrees",
          len(set(seen.values())) == 1, str(seen))
    check("6b. the artifact records the agreement it checked",
          _art()["registered_floor_agrees_across_modules"] == seen)

    from hyp04_supply_chain_hedge import make_anchor_shocks
    real = make_anchor_shocks.MINIMUM_ELIGIBLE_EVENTS
    try:
        make_anchor_shocks.MINIMUM_ELIGIBLE_EVENTS = real + 1
        try:
            M.assert_floor_agreement()
            check("6c. a drifted floor is refused", False)
        except M.PanelError:
            check("6c. a drifted floor is refused", True)
    finally:
        make_anchor_shocks.MINIMUM_ELIGIBLE_EVENTS = real


def test_7_an_unchecked_pair_still_denies() -> None:
    """P5's 'unknown denies' semantics must survive the per-pair path."""
    events = [{"event_id": "E1", "anchor": "MCK", "event_date": "2020-01-02"}]
    cmap = M._inputs()["curated_map"]
    panel = resolve_from_curated_map(events, map_path=cmap)
    check("7a. with neither availability map supplied, nothing is eligible",
          panel.pairs_eligible == 0)
    check("7b. and the denial is P5, not a silent drop",
          "P5" in panel.denial_reasons(), str(panel.denial_reasons()))

    panel2 = resolve_from_curated_map(
        events, map_path=cmap, peer_history_by_pair={("E1", "CVS"): True})
    check("7c. a pair marked available is still denied for its OTHER reasons",
          panel2.pairs_eligible == 0 and "P1" in panel2.denial_reasons(),
          str(panel2.denial_reasons()))


def test_8_the_panel_opens_no_gate() -> None:
    d = evaluate_gate()
    c = d.conditions
    check("8a. the display gate is still CLOSED", d.open is False)
    check("8b. C4 is still MET", c["C4_decisions_resolved"] is True)
    check("8c. there are still exactly four denials", len(d.denials) == 4,
          str(len(d.denials)))
    check("8d. the eligible count the gate sees is still unset",
          d.evidence.get("eligible_count") is None)
    check("8e. the artifact says so itself",
          "CLOSED" in _art()["opens_no_gate"])
    check("8f. and does not claim to be a freeze",
          "does not supply the freeze" in _art()["opens_no_gate"])


#: Fields that exist to SAY no result was computed. A forbidden word inside
#: one of these is the disclaimer working, not a leak, and a test that cannot
#: tell those apart would push the author toward deleting the disclaimer.
DISCLAIMER_FIELDS = ("what_this_is", "what_this_is_not", "opens_no_gate",
                     "unit_basis", "note", "why", "resolved", "question",
                     "reasons")

FORBIDDEN = ("beta_h", "p_value", "p-value", "confidence interval",
             "effect size", "coefficient", "correlation")


def _non_disclaimer_strings(node, key=None, out=None) -> list[str]:
    out = [] if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            _non_disclaimer_strings(v, k, out)
    elif isinstance(node, list):
        for v in node:
            _non_disclaimer_strings(v, key, out)
    elif isinstance(node, str) and key not in DISCLAIMER_FIELDS:
        out.append(node.lower())
    return out


def test_10_denial_codes_count_pairs_not_events() -> None:
    """18 P1 denials and 18 shockless events is a coincidence, not an identity."""
    d = _art()["denial_note"]
    check("10a. the artifact says denial codes count pairs",
          d["codes_count_pairs_not_events"] is True)
    check("10b. the calendar arithmetic is derived, not asserted",
          d["events_in_calendar"] - d["events_with_a_shock"]
          == d["events_without_a_shock"])
    check("10c. fewer shockless events sit on an anchor with edges than there "
          "are shockless events",
          d["shockless_events_on_an_anchor_with_edges"]
          < d["events_without_a_shock"],
          f"{d['shockless_events_on_an_anchor_with_edges']} vs "
          f"{d['events_without_a_shock']}")
    check("10d. so the matching 18s are flagged as coincidence",
          d["p1_pairs_equals_shockless_events_by_coincidence"] is True)


def test_9_no_result_is_published() -> None:
    """Availability counts are publishable; measured properties are not."""
    art = _art()
    body = " ".join(_non_disclaimer_strings(art))
    for word in FORBIDDEN:
        check(f"9a. no '{word}' outside the disclaimers", word not in body)

    # The disclaimer must still actually be there, or 9a passes vacuously.
    said = json.dumps({k: art.get(k) for k in
                       ("what_this_is_not", "opens_no_gate")}).lower()
    check("9b. the artifact still explicitly disclaims a result",
          "beta_h" in said and "not a freeze" in said)


if __name__ == "__main__":
    test_1_the_artifact_exists_and_recomputes()
    test_2_the_registered_unit_is_per_pair()
    test_3_the_unit_choice_is_worth_stating()
    test_4_the_per_peer_scoping_is_disclosed()
    test_5_the_registry_discrepancy_is_resolved()
    test_6_the_floor_cannot_drift_unnoticed()
    test_7_an_unchecked_pair_still_denies()
    test_8_the_panel_opens_no_gate()
    test_9_no_result_is_published()
    test_10_denial_codes_count_pairs_not_events()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PANEL-ASSEMBLER TESTS PASSED")
    sys.exit(0)
