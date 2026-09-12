#!/usr/bin/env python3
"""peer_selection.py tests -- the HYP-05 peer-selection rule.

Every candidate/market-cap fixture here is synthetic, written inline. Fully
offline. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_peer_selection.py
"""
from __future__ import annotations

import socket
import sys
from dataclasses import dataclass, field


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.peer_selection import (  # noqa: E402
    CONDITIONS,
    MARKET_CAP_THRESHOLD_USD,
    NEVER_CONDITIONS,
    REQUIRED_CANDIDATE_FIELDS,
    RULE_ID,
    derive_peer_universe,
    evaluate_peer,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


@dataclass(frozen=True)
class _MC:
    computed: bool
    market_cap: float | None = None
    denials: tuple = field(default_factory=tuple)


def _candidate(**overrides) -> dict:
    base = {
        "peer_ticker": "smallco",
        "anchor_ticker": "BIGCO",
        "anchor_event_date": "2020-06-01",
        "relationship_type": "direct_supplier",
        "as_of_date": "2019-01-01",
        "source": "curated",
    }
    base.update(overrides)
    return base


def test_1_qualifies_when_complete_and_below_threshold() -> None:
    mc = _MC(computed=True, market_cap=MARKET_CAP_THRESHOLD_USD - 1.0)
    q = evaluate_peer(_candidate(), mc)
    check("1a. qualifies", q.qualifies is True, str(q.denials))
    check("1b. ticker is upper-cased", q.ticker == "SMALLCO")
    check("1c. no denials", q.denials == ())
    check("1d. evidence carries the market cap and threshold",
          q.evidence["market_cap"] == mc.market_cap
          and q.evidence["threshold_usd"] == MARKET_CAP_THRESHOLD_USD)


def test_2_denies_on_incomplete_candidate_record() -> None:
    mc = _MC(computed=True, market_cap=1.0)
    for field_name in REQUIRED_CANDIDATE_FIELDS:
        c = _candidate()
        c[field_name] = ""
        q = evaluate_peer(c, mc)
        check(f"2a. missing {field_name} denies on PS-1",
              q.qualifies is False
              and any(d.startswith("PS-1") for d in q.denials), str(q.denials))


def test_3_denies_when_market_cap_is_not_computable() -> None:
    q = evaluate_peer(_candidate(), None)
    check("3a. no market cap supplied denies on PS-2",
          q.qualifies is False and any(d.startswith("PS-2") for d in q.denials),
          str(q.denials))

    mc = _MC(computed=False, denials=("missing_price: no close price",))
    q2 = evaluate_peer(_candidate(), mc)
    check("3b. uncomputed market cap denies on PS-2, carrying the reason",
          q2.qualifies is False
          and any("missing_price" in d for d in q2.denials), str(q2.denials))


def test_4_denies_when_market_cap_is_at_or_above_the_threshold() -> None:
    mc_at = _MC(computed=True, market_cap=float(MARKET_CAP_THRESHOLD_USD))
    q_at = evaluate_peer(_candidate(), mc_at)
    check("4a. exactly at the threshold denies (>=, not >)",
          q_at.qualifies is False
          and any(d.startswith("PS-3") for d in q_at.denials), str(q_at.denials))

    mc_above = _MC(computed=True, market_cap=MARKET_CAP_THRESHOLD_USD * 10)
    q_above = evaluate_peer(_candidate(), mc_above)
    check("4b. well above the threshold denies",
          q_above.qualifies is False)

    mc_below = _MC(computed=True, market_cap=1.0)
    q_below = evaluate_peer(_candidate(), mc_below)
    check("4c. well below the threshold qualifies (all else equal)",
          q_below.qualifies is True, str(q_below.denials))


def test_5_derive_universe_evaluates_every_candidate_and_collects_members() -> None:
    candidates = [
        _candidate(peer_ticker="small1"),
        _candidate(peer_ticker="small2"),
        _candidate(peer_ticker="toobig"),
    ]
    market_caps = {
        ("SMALL1", "2020-06-01"): _MC(computed=True, market_cap=1.0),
        ("SMALL2", "2020-06-01"): _MC(computed=True, market_cap=2.0),
        ("TOOBIG", "2020-06-01"): _MC(computed=True,
                                      market_cap=float(MARKET_CAP_THRESHOLD_USD) * 5),
    }
    d = derive_peer_universe(candidates, market_caps)
    check("5a. derived is True", d.derived is True, str(d.refusals))
    check("5b. only the two small peers qualify",
          d.members == ("SMALL1", "SMALL2"), str(d.members))
    check("5c. all three candidates were evaluated",
          len(d.qualifications) == 3)
    check("5d. rule_id matches the module constant", d.rule_id == RULE_ID)


def test_6_derive_universe_refuses_on_structural_defects_rather_than_scoring() -> None:
    d1 = derive_peer_universe("not a list", {})
    check("6a. non-list candidates refuses, not silently empty-passes",
          d1.derived is False and d1.members == (), str(d1.refusals))

    d2 = derive_peer_universe(["not a mapping", _candidate()], {
        ("SMALLCO", "2020-06-01"): _MC(computed=True, market_cap=1.0)})
    check("6b. a non-mapping candidate is flagged in refusals",
          any("not mappings" in r for r in d2.refusals), str(d2.refusals))
    check("6c. but the well-formed candidate alongside it is still evaluated",
          len(d2.qualifications) == 1)


def test_7_a_candidate_with_no_matching_market_cap_record_denies() -> None:
    """The market_caps dict simply lacking an entry for this (peer, date) --
    as opposed to an explicit uncomputed result -- must deny the same way,
    not silently pass or raise a KeyError."""
    d = derive_peer_universe([_candidate()], {})
    check("7a. missing market-cap entry denies on PS-2",
          d.members == ()
          and any(dd.startswith("PS-2") for dd in d.qualifications[0].denials),
          str(d.qualifications[0].denials))


def test_8_never_conditions_are_real_and_rationale_isnt_trivial() -> None:
    check("8a. at least four forbidden criteria are named",
          len(NEVER_CONDITIONS) >= 4, str(len(NEVER_CONDITIONS)))
    check("8b. every rationale is substantive, not a one-liner",
          all(len(reason) > 80 for _, reason in NEVER_CONDITIONS))
    check("8c. the locked-24-universe exclusion is explicitly named",
          any("locked" in name.lower() for name, _ in NEVER_CONDITIONS),
          str([n for n, _ in NEVER_CONDITIONS]))
    check("8d. conditions table names exactly PS-1..PS-3",
          [c[0] for c in CONDITIONS] == ["PS-1", "PS-2", "PS-3"],
          str([c[0] for c in CONDITIONS]))


def test_9_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("9a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("9a. network blocked", True)


if __name__ == "__main__":
    test_1_qualifies_when_complete_and_below_threshold()
    test_2_denies_on_incomplete_candidate_record()
    test_3_denies_when_market_cap_is_not_computable()
    test_4_denies_when_market_cap_is_at_or_above_the_threshold()
    test_5_derive_universe_evaluates_every_candidate_and_collects_members()
    test_6_derive_universe_refuses_on_structural_defects_rather_than_scoring()
    test_7_a_candidate_with_no_matching_market_cap_record_denies()
    test_8_never_conditions_are_real_and_rationale_isnt_trivial()
    test_9_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL PEER_SELECTION TESTS PASSED")
    sys.exit(0)
