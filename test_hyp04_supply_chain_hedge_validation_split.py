#!/usr/bin/env python3
"""HYP-04 validation split -- the holdout is declared before it is used.

What this suite is defending. Phase 1 runs Stage 1 on real data; Phase 3 runs
the locked model against a holdout once. If Phase 1 ranges over everything,
Phase 2 has no untouched holdout left to declare and the split gets drawn
across events whose behaviour is already known. That is not a preregistered
split, it is a description of one.

So the assertions here are mostly about ORDER and about the split actually
partitioning -- not about the numbers being pleasing. Two in particular:

  * a calendar quarter may not appear on both sides. D1 clusters on
    `calendar_period`, so a straddling quarter is a correlation channel
    between exploration and holdout, which is the property the split exists
    to remove.
  * `build_draft` refuses once a result artifact exists, against the same
    patterns `make_freeze_draft` scans. A split declared after an outcome is
    not a preregistration.

The realized numbers ARE pinned (157/57 at 2021Q1) but for a different reason:
so that a later change to the rule, the fraction or the frozen set shows up as
a failing test rather than a quietly different partition.

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_validation_split.py
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

from hyp04_supply_chain_hedge import make_validation_split as V  # noqa: E402
from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    current_decision,
)

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"
PANEL = LSE / "HYP04_EVENT_PANEL_2026-09-08.json"

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


def _frozen_ids() -> list[str]:
    return list(json.loads(PANEL.read_text(encoding="utf-8"))
                ["eligible_event_ids"])


def _refuses(label: str, fn, expect: str) -> None:
    """Assert fn() raises SplitError whose message contains `expect`.

    `expect` is required and may not be empty: a refusal test that does not
    check WHICH refusal fired passes when an unrelated guard trips first,
    which is how a suite ends up green while testing nothing.
    """
    if not expect:
        raise ValueError("expect fragment is required")
    try:
        fn()
    except V.SplitError as e:
        if expect.lower() in str(e).lower():
            check(label, True)
        else:
            check(label, False, f"refused, but for: {str(e)[:150]}")
    except Exception as e:                                  # noqa: BLE001
        check(label, False, f"{type(e).__name__}: {str(e)[:150]}")
    else:
        check(label, False, "it did not refuse")


def test_0_the_partition_check_actually_bites() -> None:
    """Negative control. Every assertion below rests on derive_split refusing
    a bad partition, so show it refusing one first."""
    # Every event in ONE quarter. Snapping up sends the whole quarter to the
    # holdout, so exploration is empty -- and an empty side must refuse rather
    # than return a "split" that partitions nothing.
    ids = ["AAA-2020-01-06", "AAA-2020-02-10", "AAA-2020-03-11",
           "AAA-2020-03-30"]
    _refuses("0a. a single-quarter set refuses rather than returning an empty "
             "side", lambda: V.derive_split(ids, fraction=0.25),
             "leaves one side empty")

    # And the control: two quarters DO split, so 0a is refusing for the stated
    # reason and not because derive_split refuses everything.
    ok = V.derive_split(ids + ["AAA-2020-04-06", "AAA-2020-05-10"],
                        fraction=0.25)
    check("0b. CONTROL -- a two-quarter set splits cleanly",
          ok["exploration"]["n_events"] == 4
          and ok["holdout"]["n_events"] == 2, str(ok["cut_calendar_period"]))


def test_1_event_ids_are_parsed_not_guessed() -> None:
    check("1a. a normal id yields (year, quarter)",
          V.event_quarter("JBL-2003-09-18") == (2003, 3))
    check("1b. quarter boundaries are right",
          [V.event_quarter(f"X-2021-{m:02d}-01")[1] for m in (1, 3, 4, 6, 7, 12)]
          == [1, 1, 2, 2, 3, 4])
    for bad in ("JBL", "JBL-20030918", "JBL-2003-13-01", "JBL-xxxx-09-18"):
        _refuses(f"1c. {bad!r} is refused, not guessed",
                 lambda b=bad: V.event_quarter(b), "YYYY-MM-DD")


def test_2_the_split_actually_partitions() -> None:
    ids = _frozen_ids()
    s = V.derive_split(ids, fraction=0.25)
    ex = s["exploration"]["event_ids"]
    ho = s["holdout"]["event_ids"]

    check("2a. every frozen event lands on exactly one side",
          sorted(ex + ho) == sorted(ids) and not (set(ex) & set(ho)))
    check("2b. no calendar_period appears on both sides -- no D1 cluster "
          "straddles the cut",
          not ({V.event_quarter(i) for i in ex}
               & {V.event_quarter(i) for i in ho}))
    check("2c. the holdout is strictly later than the exploration set",
          max(V.event_quarter(i) for i in ex)
          < min(V.event_quarter(i) for i in ho))
    check("2d. both sides are enumerated in full, not described",
          len(ex) == s["exploration"]["n_events"]
          and len(ho) == s["holdout"]["n_events"])


def test_3_the_declared_rule_lands_where_the_plan_says() -> None:
    """Pinned so a changed rule, fraction or frozen set fails loudly."""
    s = V.derive_split(_frozen_ids(), fraction=V.HOLDOUT_FRACTION)
    ex, ho = s["exploration"], s["holdout"]
    check("3a. the default holdout fraction is 25%", V.HOLDOUT_FRACTION == 0.25)
    check("3b. the cut is 2021Q1", s["cut_calendar_period"] == "2021Q1",
          s["cut_calendar_period"])
    check("3c. 157 exploration / 57 holdout",
          (ex["n_events"], ho["n_events"]) == (157, 57),
          f"{ex['n_events']}/{ho['n_events']}")
    check("3d. 70 / 22 calendar periods",
          (ex["n_calendar_periods"], ho["n_calendar_periods"]) == (70, 22),
          f"{ex['n_calendar_periods']}/{ho['n_calendar_periods']}")
    check("3e. all four anchors are present on BOTH sides -- a holdout missing "
          "an anchor tests a different population",
          ex["n_anchors"] == ho["n_anchors"] == 4,
          f"{ex['anchors']} / {ho['anchors']}")


def test_4_the_rejected_alternative_is_rejected_for_a_measured_reason() -> None:
    """80/20 was ruled out because its holdout drops an anchor. If that stops
    being true the plan's reasoning has changed and should be revisited, so
    this asserts the reason rather than the conclusion."""
    s = V.derive_split(_frozen_ids(), fraction=0.20)
    check("4a. an 80/20 cut loses an anchor from the holdout",
          s["holdout"]["n_anchors"] < 4, str(s["holdout"]["anchors"]))
    s70 = V.derive_split(_frozen_ids(), fraction=0.30)
    check("4b. 70/30 keeps all four, so the choice between it and 75/25 is a "
          "judgement and not forced",
          s70["holdout"]["n_anchors"] == 4)


def test_5_bad_inputs_refuse() -> None:
    ids = _frozen_ids()
    for f in (0.0, 1.0, -0.1, 1.5):
        _refuses(f"5a. fraction {f} is refused",
                 lambda x=f: V.derive_split(ids, fraction=x), "not in (0, 1)")
    _refuses("5b. duplicate ids are refused",
             lambda: V.derive_split(ids + ids[:1]), "duplicates")
    _refuses("5c. an empty set is refused",
             lambda: V.derive_split([]), "no event ids")


def test_6_an_undeclared_split_constrains_nothing() -> None:
    ids = _frozen_ids()
    s = V.derive_split(ids)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "split.json"

        draft = {**s, "declared": False, "declared_by": "", "declared_date": ""}
        p.write_text(json.dumps(draft), encoding="utf-8")
        _refuses("6a. a DRAFT is refused by load_declared_split",
                 lambda: V.load_declared_split(p), "is a draft")

        unsigned = {**s, "declared": True, "declared_by": "",
                    "declared_date": "2026-09-09"}
        p.write_text(json.dumps(unsigned), encoding="utf-8")
        _refuses("6b. an unattributed declaration is refused",
                 lambda: V.load_declared_split(p), "blank")

        bad = json.loads(json.dumps(s))
        bad["holdout"]["event_ids"].append(bad["exploration"]["event_ids"][0])
        bad.update(declared=True, declared_by="x", declared_date="2026-09-09")
        p.write_text(json.dumps(bad), encoding="utf-8")
        _refuses("6c. a document whose partitions overlap is refused",
                 lambda: V.load_declared_split(p), "both partitions")

        good = {**s, "declared": True, "declared_by": "bchen9996",
                "declared_date": "2026-09-09"}
        p.write_text(json.dumps(good), encoding="utf-8")
        loaded = V.load_declared_split(p)
        check("6d. CONTROL -- a signed, disjoint split loads",
              len(loaded["exploration"]["event_ids"]) == 157)


def test_7_order_is_enforced_before_anything_is_written() -> None:
    """A split declared after a result is a description, not a preregistration."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "split.json"
        out.write_text("{}", encoding="utf-8")
        _refuses("7a. it refuses to overwrite an existing split",
                 lambda: V.build_draft(panel_path=PANEL, out_path=out),
                 "already exists")

        fake_lse = Path(td) / "lse"
        fake_lse.mkdir()
        (fake_lse / "HYP04_INFERENCE_PHASE1_2026-09-09.json").write_text(
            "{}", encoding="utf-8")
        _refuses("7b. it refuses once a result artifact exists",
                 lambda: V.build_draft(panel_path=PANEL,
                                       out_path=Path(td) / "s2.json",
                                       lse=fake_lse),
                 "not a preregistered split")

    check("7c. and the pattern it scans is the freeze machinery's, not a "
          "second list that can drift",
          "HYP04_INFERENCE_*" in V.RESULT_ARTIFACT_PATTERNS)


def test_8_declaring_a_split_opens_no_gate() -> None:
    before = current_decision()
    V.derive_split(_frozen_ids())
    after = current_decision()
    check("8a. the gate is unchanged by deriving a split",
          (before.open, len(before.denials))
          == (after.open, len(after.denials)))
    # `derive_split` returns the partition; the disclaimer lives in the
    # artifact `build_draft` writes, which needs a clean tree. Assert it on the
    # source rather than with an `or True` that would pass either way.
    src = (ROOT / "hyp04_supply_chain_hedge"
           / "make_validation_split.py").read_text(encoding="utf-8")
    check("8b. and the artifact it writes disclaims moving any condition",
          "moves no gate condition" in src)
    check("8c. the partition itself carries no gate verdict to go stale",
          not any(w in json.dumps(V.derive_split(_frozen_ids()))
                  for w in ("gate is OPEN", "gate is CLOSED", "denials")))


def test_9_the_cluster_key_is_declared_not_assumed() -> None:
    check("9a. the module names D1's cluster key",
          V.CLUSTER_KEY == "calendar_period")
    check("9b. and defines it, rather than leaving it to the caller",
          "calendar quarter" in V.CLUSTER_KEY_DEFINITION.lower())
    # The real failure mode: a feature table carries ONE ROW PER PEER, so an
    # event with three edges contributes three rows. `max_t_permutation` raises
    # if the cluster column differs across those rows. Deriving the key from
    # the event id alone makes that impossible -- assert it on rows, not on a
    # one-element set, which would be true however the key were computed.
    rows = [(eid, peer)
            for eid in _frozen_ids()[:40]
            for peer in ("AAPL", "BB", "CSCO")]
    by_event: dict[str, set] = {}
    for eid, _peer in rows:
        by_event.setdefault(eid, set()).add(V.event_quarter(eid))
    check("9c. every row of a multi-peer event carries ONE calendar_period, "
          "which is what max_t_permutation requires",
          len(rows) == 120 and all(len(v) == 1 for v in by_event.values()),
          str([k for k, v in by_event.items() if len(v) != 1][:3]))
    from hyp04_supply_chain_hedge.constants import LOCKED_CLUSTER_KEY
    check("9d. and it matches the locked constant the estimator reads",
          V.CLUSTER_KEY == LOCKED_CLUSTER_KEY, LOCKED_CLUSTER_KEY)


def test_9b_a_correction_annotates_without_re_declaring() -> None:
    """The real case: `declared_by` carries stray brackets from an
    incompletely-filled template. `annotate_correction` must record that
    without touching what was actually signed."""
    s = V.derive_split(_frozen_ids())
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "split.json"

        draft = {**s, "declared": False, "declared_by": "", "declared_date": ""}
        p.write_text(json.dumps(draft), encoding="utf-8")
        _refuses("9b-a. cannot annotate an undeclared draft -- there is no "
                 "signature yet for a note to be about",
                 lambda: V.annotate_correction(p, note="x"), "never declared")

        signed = {**s, "declared": True, "declared_by": "<bchen9996>",
                  "declared_date": "2026-09-10",
                  "attestation_text": "the real affirmation"}
        p.write_text(json.dumps(signed), encoding="utf-8")
        _refuses("9b-b. a blank note documents nothing",
                 lambda: V.annotate_correction(p, note="   "), "documents nothing")

        after = V.annotate_correction(
            p, note="The angle brackets are a copy-paste artifact from the "
                    "template, not part of the name. This declaration is by "
                    "bchen9996.")
        check("9b-c. the note is written",
              "bchen9996" in after["correction_note"])
        check("9b-d. and what was SIGNED is untouched -- same value, warts "
              "and all",
              after["declared_by"] == "<bchen9996>"
              and after["declared_date"] == "2026-09-10"
              and after["attestation_text"] == "the real affirmation")
        check("9b-e. nothing else moved",
              {k: v for k, v in after.items() if k != "correction_note"}
              == signed)

        _refuses("9b-f. a second correction on the same record is refused -- "
                 "one note per document",
                 lambda: V.annotate_correction(p, note="another note"),
                 "already carries a correction_note")


def test_10_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("10a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("10a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_0_the_partition_check_actually_bites()
    test_1_event_ids_are_parsed_not_guessed()
    test_2_the_split_actually_partitions()
    test_3_the_declared_rule_lands_where_the_plan_says()
    test_4_the_rejected_alternative_is_rejected_for_a_measured_reason()
    test_5_bad_inputs_refuse()
    test_6_an_undeclared_split_constrains_nothing()
    test_7_order_is_enforced_before_anything_is_written()
    test_8_declaring_a_split_opens_no_gate()
    test_9_the_cluster_key_is_declared_not_assumed()
    test_9b_a_correction_annotates_without_re_declaring()
    test_10_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 VALIDATION-SPLIT TESTS PASSED")
    sys.exit(0)
