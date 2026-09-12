#!/usr/bin/env python3
"""Tests for the dated anchor-shock artifact -- HYP-04's FIRST production
measurement.

=== WHAT MAKES THIS SUITE DIFFERENT FROM EVERY OTHER ONE HERE ===

Until now nothing in HYP-04 had been measured, so every suite could assert that
counters were zero. This artifact holds real numbers derived from real closes,
and the risks change shape with it:

  * a shrinking sample looking like a clean one -- so EVERY calendar event must
    appear, computed or denied, and the denominator must reconcile (test_1)
  * a number that cannot be checked -- so every published shock is RE-DERIVED
    from the closes on disk, not trusted (test_3)
  * a measurement being mistaken for an open gate -- so the gate is asserted
    unchanged and the artifact must say so itself (test_5)

Offline. The closes are read from the filled request files; nothing is fetched.

Run directly: python test_hyp04_supply_chain_hedge_anchor_shocks.py
"""
from __future__ import annotations

import csv
import json
import math
import socket
import sys
from collections import Counter
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
    BENCHMARK_BETA,
    BENCHMARK_TICKER,
    MAX_ABS_EXCESS_RETURN,
    RETURN_BASIS,
)
from hyp04_supply_chain_hedge.display_gate import current_decision  # noqa: E402
from hyp04_supply_chain_hedge.make_anchor_shocks import (  # noqa: E402
    OUT_CSV,
    OUT_JSON,
    REQUEST_DIR,
    SHOCK_CSV_FIELDS,
    _newest_calendar,
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


def _have() -> bool:
    return OUT_JSON.is_file() and OUT_CSV.is_file()


def _rows() -> list[dict[str, str]]:
    return list(csv.DictReader(OUT_CSV.open(encoding="utf-8", newline="")))


def _doc() -> dict:
    return json.loads(OUT_JSON.read_text(encoding="utf-8"))


def test_1_every_event_has_a_row_and_the_denominator_reconciles() -> None:
    print("\n--- 1: the denominator stays visible ---")
    if not _have():
        skip("1. artifact", "shock artifact not generated")
        return
    doc, rows = _doc(), _rows()

    cal = _newest_calendar()
    cal_rows = list(csv.DictReader(cal.open(encoding="utf-8", newline="")))
    check("1a. one row per calendar event, none dropped",
          len(rows) == len(cal_rows), f"{len(rows)} vs {len(cal_rows)}")
    check("1b. and the ids are exactly the calendar's",
          {r["event_id"] for r in rows} == {r["event_id"] for r in cal_rows})
    check("1c. no duplicate rows",
          len({r["event_id"] for r in rows}) == len(rows))

    got = Counter(r["status"] for r in rows)
    c = doc["counts"]
    check("1d. the published counts re-derive from the rows",
          c["shock_computed"] == got["shock_computed"]
          and c["denied_session"] == got["denied_session"]
          and c["denied_closes"] == got["denied_closes"],
          f"{dict(got)} vs {c}")
    check("1e. and they sum to the total -- nothing is unaccounted for",
          sum(v for k, v in c.items() if k != "events_total")
          == c["events_total"], str(c))

    # A row is EITHER a shock OR a denial. Both would mean a denied event was
    # still contributing a number somewhere.
    both = [r for r in rows if r["shock"] and r["denial_reasons"]]
    check("1f. no row carries a shock AND a denial", not both,
          str(both[:2]))
    silent = [r for r in rows
              if not r["shock"] and not r["denial_reasons"]]
    check("1g. and no row is silently empty", not silent, str(silent[:2]))

    check("1h. the artifact states why denied events are kept",
          "denominator visible" in doc["every_event_has_a_row"])


def test_2_the_denials_are_the_ones_the_calendar_predicted() -> None:
    print("\n--- 2: denials trace to a stated cause ---")
    if not _have():
        skip("2. denials", "shock artifact not generated")
        return
    rows = _rows()
    cal = _newest_calendar()
    cal_rows = list(csv.DictReader(cal.open(encoding="utf-8", newline="")))

    unknown = {r["event_id"] for r in cal_rows
               if r["release_session"] == "UNKNOWN"}
    denied_session = {r["event_id"] for r in rows
                      if r["status"] == "denied_session"}
    check("2a. every unresolved-session denial is a calendar UNKNOWN",
          denied_session <= unknown, str(sorted(denied_session - unknown)[:3]))
    check("2b. and every calendar UNKNOWN is denied -- none slipped through",
          unknown <= denied_session, str(sorted(unknown - denied_session)[:3]))
    check("2c. each denial names AS-1, not just 'failed'",
          all("AS-1" in r["denial_reasons"] for r in rows
              if r["status"] == "denied_session"))
    check("2d. a denied event carries NO shock",
          all(not r["shock"] for r in rows if r["status"].startswith("denied")))


def test_3_every_published_shock_re_derives_from_the_closes() -> None:
    """The numbers are CHECKED against the closes on disk, not trusted."""
    print("\n--- 3: re-derivation from the filled request files ---")
    if not _have():
        skip("3. re-derivation", "shock artifact not generated")
        return
    if not REQUEST_DIR.is_dir():
        skip("3. re-derivation", "request files not on this machine")
        return

    closes: dict[str, dict[str, float]] = {}
    for p in REQUEST_DIR.glob("*_closes_REQUEST.csv"):
        for r in csv.DictReader(p.open(encoding="utf-8", newline="")):
            v = (r.get("close") or "").strip()
            if v:
                closes.setdefault(r["ticker"].strip().upper(),
                                  {})[r["session_date"].strip()] = float(v)

    rows = [r for r in _rows() if r["status"] == "shock_computed"]
    check("3a. there are shocks to check", len(rows) > 0, str(len(rows)))

    bad_ret, bad_excess, bad_shock, bad_band = [], [], [], []
    for r in rows:
        a_ser = closes.get(r["anchor_ticker"], {})
        b_ser = closes.get(BENCHMARK_TICKER, {})
        p0, p1 = a_ser.get(r["prior_session"]), a_ser.get(r["attributed_session"])
        q0, q1 = b_ser.get(r["prior_session"]), b_ser.get(r["attributed_session"])
        if None in (p0, p1, q0, q1):
            bad_ret.append(r["event_id"])
            continue
        a = math.log(p1 / p0)
        b = math.log(q1 / q0)
        if abs(a - float(r["anchor_return"])) > 1e-9:
            bad_ret.append(r["event_id"])
        ex = a - BENCHMARK_BETA * b
        if abs(ex - float(r["excess_return"])) > 1e-9:
            bad_excess.append(r["event_id"])
        if abs(abs(ex) - float(r["shock"])) > 1e-9:
            bad_shock.append(r["event_id"])
        if abs(ex) > MAX_ABS_EXCESS_RETURN:
            bad_band.append(r["event_id"])

    check("3b. every anchor return re-derives as a LOG return",
          not bad_ret, str(bad_ret[:3]))
    check("3c. every excess return is anchor - beta * benchmark",
          not bad_excess, str(bad_excess[:3]))
    check("3d. every shock is the MAGNITUDE of that excess",
          not bad_shock, str(bad_shock[:3]))
    check("3e. and none exceeds the parse guard the rule fixed in advance",
          not bad_band, str(bad_band[:3]))
    check("3f. no shock is negative",
          all(float(r["shock"]) >= 0.0 for r in rows))
    check("3g. the benchmark is the one the rule names",
          BENCHMARK_TICKER in closes, str(sorted(closes)))
    check("3h. the declared return basis is what was used",
          _doc()["rules"]["return_basis"] == RETURN_BASIS == "log")
    check("3i. and beta was not estimated",
          _doc()["rules"]["beta_is_estimated"] is False)


def test_4_the_attributed_session_is_never_the_release_date_for_AMC() -> None:
    """An AMC release measured on its own session closed BEFORE the news."""
    print("\n--- 4: session attribution held ---")
    if not _have():
        skip("4. attribution", "shock artifact not generated")
        return
    rows = [r for r in _rows() if r["status"] == "shock_computed"]

    amc = [r for r in rows if r["release_session"] == "AMC"]
    bmo = [r for r in rows if r["release_session"] == "BMO"]
    check("4a. there are AMC and BMO events to check",
          len(amc) > 0 and len(bmo) > 0, f"{len(amc)}/{len(bmo)}")
    check("4b. no AMC event is measured on its own release date",
          all(r["attributed_session"] > r["release_date"] for r in amc),
          str([r["event_id"] for r in amc
               if r["attributed_session"] <= r["release_date"]][:3]))
    check("4c. every BMO event IS measured on its release date",
          all(r["attributed_session"] == r["release_date"] for r in bmo),
          str([r["event_id"] for r in bmo
               if r["attributed_session"] != r["release_date"]][:3]))
    check("4d. the prior session is always strictly earlier",
          all(r["prior_session"] < r["attributed_session"] for r in rows))


def test_5_a_measurement_is_not_an_open_gate() -> None:
    print("\n--- 5: the gate did not move ---")
    d = current_decision()
    # NARROWED, not retargeted -- the gate went OPEN (2026-09-09, freeze +
    # v1.12) then CLOSED again (2026-09-11, v1.13 closed HYP-04 as
    # HOLDOUT_TESTED_NULL). The claim in this test's name is unchanged either
    # way -- computing shocks is not what moved the gate in either direction
    # -- so this asserts only what this suite's own business is: C4, which
    # nothing here touches.
    check("5c. C4 still MET", d.conditions["C4_decisions_resolved"] is True)
    # `eligible_event_count`, not `eligible_count` -- the latter is not a key
    # the gate ever emits, so `.get("eligible_count") is None` passes whatever
    # the gate says. Several assertions in this repo read the wrong name and
    # were vacuous for it.
    check("5d. C2 passes on the FROZEN count, not on anything computed here",
          d.conditions["C2_threshold"] is True
          and d.evidence["eligible_event_count"] == 214,
          str(d.evidence.get("eligible_event_count")))

    if not _have():
        skip("5e. artifact disclaimer", "shock artifact not generated")
        return
    doc = _doc()
    check("5e. the artifact says it moves no gate",
          "does not move C2" in doc["what_this_is_not"])
    check("5f. and names WHY -- the literal count and the freeze must agree",
          "eligible_event_count=0" in doc["what_this_is_not"]
          and "freeze" in doc["what_this_is_not"])
    check("5g. the threshold note distinguishes a shock from a met C2",
          "not the same as C2 being met"
          in doc["registered_threshold"]["note"])
    # A count above the floor is the tempting thing to over-read.
    check("5h. the artifact reports the comparison without claiming it",
          isinstance(doc["registered_threshold"]["shocks_vs_threshold"], int))


def test_6_provenance_is_complete_enough_to_reproduce() -> None:
    print("\n--- 6: provenance ---")
    if not _have():
        skip("6. provenance", "shock artifact not generated")
        return
    doc = _doc()
    src = doc["sources"]
    cal = _newest_calendar()
    import hashlib
    check("6a. the calendar it was built from is named and hashed",
          src["calendar"] == cal.name
          and src["calendar_sha256"]
          == hashlib.sha256(cal.read_bytes()).hexdigest())
    check("6b. the session index records the calendar implementation",
          doc["session_index"]["calendar_id"].startswith("XNYS_"))
    check("6c. and that it agreed with the authoritative calendar",
          doc["session_index"]["agrees"] is True
          and doc["session_index"]["disagreements"] == 0)
    check("6d. every request file reports filled vs blank",
          all({"filled", "blank"} <= set(v)
              for v in src["request_files"].values()),
          str(src["request_files"])[:80])
    check("6e. the shock rule id is carried",
          doc["rules"]["shock_rule_id"] == "HYP04-ANCHOR-SHOCK-RULE-v1")
    check("6f. survivorship is reported, not assumed",
          "anchor_side_survivorship_clean" in doc["survivorship"])
    check("6g. the CSV schema is the declared one",
          tuple(_rows()[0].keys()) == SHOCK_CSV_FIELDS,
          str(tuple(_rows()[0].keys())))


def test_7_offline() -> None:
    print("\n--- 7: offline ---")
    try:
        socket.getaddrinfo("query1.finance.yahoo.com", 443)
        check("7a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("7a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_every_event_has_a_row_and_the_denominator_reconciles()
    test_2_the_denials_are_the_ones_the_calendar_predicted()
    test_3_every_published_shock_re_derives_from_the_closes()
    test_4_the_attributed_session_is_never_the_release_date_for_AMC()
    test_5_a_measurement_is_not_an_open_gate()
    test_6_provenance_is_complete_enough_to_reproduce()
    test_7_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 ANCHOR SHOCK ARTIFACT TESTS PASSED")
