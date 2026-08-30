#!/usr/bin/env python3
"""HYP-04 anchor-side shock tests. FULLY OFFLINE.

The anchor-side shock is the ONLY anchor-side quantity in HYP-04's model, and
until 2026-08-29 it had no production definition at all. What this suite mostly
does is assert the REFUSALS, because every way of being wrong here is silent:

  * a missing benchmark read as zero promotes a raw return to an excess return
  * a stray True read as 1.0 fabricates a 100% move
  * an unresolved session lets the shock be measured on the wrong day
  * an estimated beta would import look-ahead through the estimation window

None of those raises on its own. Each produces a finite, plausible number.

Run directly: python test_hyp04_supply_chain_hedge_anchor_shock.py
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

from hyp04_supply_chain_hedge.anchor_shock import (  # noqa: E402
    ANCHOR_SHOCK_RULE_ID,
    BENCHMARK_BETA,
    BENCHMARK_TICKER,
    MAX_ABS_EXCESS_RETURN,
    RULE_CONDITIONS,
    AnchorShock,
    excess_return,
    is_shock_eligible,
    rule_description,
    shock_for_event,
)

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


GOOD = dict(event_id="MCK-2013-07-25", anchor_ticker="MCK",
            attributed_session="2013-07-26",
            anchor_return=-0.084, benchmark_return=-0.004)


def test_1_the_happy_path() -> None:
    print("\n--- 1: a well-measured event ---")
    s, d = shock_for_event(**GOOD)
    check("1a. it produces a shock", s is not None, str(d))
    check("1b. with no denials", d == [], str(d))
    if s is None:
        return
    check("1c. excess is anchor minus beta*benchmark",
          abs(s.excess_return - (-0.084 - 1.0 * -0.004)) < 1e-12,
          str(s.excess_return))
    check("1d. shock is the MAGNITUDE", abs(s.shock - 0.080) < 1e-12,
          str(s.shock))
    check("1e. shock is never negative", s.shock >= 0.0, str(s.shock))
    check("1f. both legs are retained, not just the result",
          s.anchor_return == -0.084 and s.benchmark_return == -0.004)
    check("1g. it records the session it was measured on",
          s.session == "2013-07-26", s.session)
    check("1h. and the rule that produced it",
          s.rule_id == ANCHOR_SHOCK_RULE_ID, s.rule_id)
    check("1i. ticker is normalised", shock_for_event(
        **{**GOOD, "anchor_ticker": " mck "})[0].anchor_ticker == "MCK")


def test_2_a_missing_benchmark_is_never_zero() -> None:
    """THE DANGEROUS ONE. Reading a missing benchmark as 0.0 silently turns a
    raw return into an 'excess' return -- a number that is finite, plausible,
    and wrong by exactly the market move."""
    print("\n--- 2: a missing benchmark denies ---")
    for bad in (None, "", "n/a", float("nan"), float("inf")):
        s, d = shock_for_event(**{**GOOD, "benchmark_return": bad})
        check(f"2a. benchmark {bad!r} denies", s is None and bool(d),
              str(d)[:90])
        check(f"2b. and says why, naming the zero trap: {bad!r}",
              any("NEVER read as zero" in x for x in d), str(d)[:90])
    # CONTROL -- a genuine 0.0 benchmark is a real observation and must PASS.
    s, d = shock_for_event(**{**GOOD, "benchmark_return": 0.0})
    check("2c. CONTROL -- a real 0.0 benchmark is kept, not confused with "
          "missing", s is not None and abs(s.shock - 0.084) < 1e-12, str(d))


def test_3_booleans_are_not_returns() -> None:
    """isinstance(True, int) is True in Python, so an unguarded float() turns a
    stray True into a 1.0 return -- a fabricated 100% move."""
    print("\n--- 3: booleans are not numbers ---")
    for leg in ("anchor_return", "benchmark_return"):
        for b in (True, False):
            s, d = shock_for_event(**{**GOOD, leg: b})
            check(f"3a. {leg}={b} denies", s is None and bool(d), str(d)[:80])
    check("3b. excess_return() refuses them too",
          excess_return(True, 0.0) is None and excess_return(0.0, True) is None)


def test_4_the_session_must_be_resolved() -> None:
    """This module must not decide which session an earnings release affects.
    That belongs to the XNYS calendar; a second answer here would diverge."""
    print("\n--- 4: an unresolved session denies ---")
    for bad in ("", None, "2013-7-26", "26/07/2013", "AMC", "2013-07-26T00:00Z"):
        s, d = shock_for_event(**{**GOOD, "attributed_session": bad})
        check(f"4a. session {bad!r} denies", s is None and bool(d), str(d)[:80])
        check(f"4b. and refuses to guess it: {bad!r}",
              any("refuses to guess" in x for x in d), str(d)[:80])
    s, _ = shock_for_event(**{**GOOD, "attributed_session": "2013-07-26"})
    check("4c. CONTROL -- a resolved ISO session passes", s is not None)


def test_5_the_parse_guard() -> None:
    print("\n--- 5: out-of-band excess is a data error ---")
    s, d = shock_for_event(**{**GOOD, "anchor_return": 5.0,
                              "benchmark_return": 0.0})
    check("5a. |excess| beyond the bound denies", s is None and bool(d),
          str(d)[:80])
    check("5b. and says it is a parse guard, not an outlier filter",
          any("parse guard" in x for x in d), str(d)[:90])
    # The bound is loose ON PURPOSE: a real -60% earnings session must survive.
    s, d = shock_for_event(**{**GOOD, "anchor_return": -0.60,
                              "benchmark_return": 0.01})
    check("5c. CONTROL -- a real 61% adverse session is KEPT",
          s is not None and abs(s.shock - 0.61) < 1e-12, str(d))
    check("5d. the bound is documented as a constant", MAX_ABS_EXCESS_RETURN == 2.0)


def test_6_beta_is_not_estimated() -> None:
    """An estimated beta needs an estimation window. Choosing that window after
    seeing results is after-the-fact tuning; fitting it on the full sample uses
    post-event data to define a pre-event expectation."""
    print("\n--- 6: the benchmark coefficient is fixed, not fitted ---")
    r = rule_description()
    check("6a. beta is declared NOT estimated",
          r["beta_is_estimated"] is False, str(r["beta_is_estimated"]))
    check("6b. beta is exactly 1", BENCHMARK_BETA == 1.0, str(BENCHMARK_BETA))
    check("6c. the benchmark is named", BENCHMARK_TICKER == "SPY",
          BENCHMARK_TICKER)
    check("6d. there is no parameter to pass a fitted beta through",
          "beta" not in shock_for_event.__code__.co_varnames,
          str(shock_for_event.__code__.co_varnames))
    check("6e. the point-in-time basis is stated, not assumed",
          "cannot be revised by later information" in r["point_in_time_basis"])


def test_7_the_rule_is_declarable() -> None:
    print("\n--- 7: a registry version can declare this rather than paraphrase ---")
    r = rule_description()
    check("7a. it carries a rule id", r["rule_id"] == ANCHOR_SHOCK_RULE_ID)
    check("7b. every condition is present",
          [c["id"] for c in r["conditions"]] == [c for c, _ in RULE_CONDITIONS],
          str([c["id"] for c in r["conditions"]]))
    check("7c. six conditions, AS-1..AS-6", len(RULE_CONDITIONS) == 6)
    check("7d. the shock formula is stated in full",
          r["shock_definition"] == "abs(anchor_return - beta * benchmark_return)")
    check("7e. and it states that NOTHING has been computed yet",
          "not computed data" in r["measurement_status"])


def test_8_no_attention_data_anywhere() -> None:
    """The whole point of the 2026-08-29 decision. If a future edit reintroduces
    an attention requirement on the anchor side, it must be a deliberate act
    that flips this test, not a quiet import."""
    print("\n--- 8: the anchor side does not require attention data ---")
    src = open(__file__.replace("test_hyp04_supply_chain_hedge_anchor_shock.py",
                                "hyp04_supply_chain_hedge/anchor_shock.py"),
               encoding="utf-8").read()
    body = src.split('"""', 2)[-1]  # skip the module docstring, which cites it
    for token in ("gst_zscore", "wiki_zscore", "panel_implied_volatility"):
        check(f"8a. {token} is not required by the anchor-side rule",
              token not in body, "present in module body")
    check("8b. and gst_market_response is not imported",
          "gst_market_response" not in body, "imported")
    s, _ = shock_for_event(**GOOD)
    check("8c. a shock is produced with no attention input of any kind",
          s is not None)


def test_9_eligibility_agrees_with_the_reasons() -> None:
    print("\n--- 9: the convenience wrapper cannot disagree ---")
    check("9a. eligible when a shock is produced", is_shock_eligible(**GOOD))
    check("9b. not eligible when the benchmark is missing",
          not is_shock_eligible(**{**GOOD, "benchmark_return": None}))
    check("9c. not eligible when the session is unresolved",
          not is_shock_eligible(**{**GOOD, "attributed_session": "AMC"}))


def test_10_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("10. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("10. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_the_happy_path()
    test_2_a_missing_benchmark_is_never_zero()
    test_3_booleans_are_not_returns()
    test_4_the_session_must_be_resolved()
    test_5_the_parse_guard()
    test_6_beta_is_not_estimated()
    test_7_the_rule_is_declarable()
    test_8_no_attention_data_anywhere()
    test_9_eligibility_agrees_with_the_reasons()
    test_10_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 ANCHOR SHOCK TESTS PASSED")
