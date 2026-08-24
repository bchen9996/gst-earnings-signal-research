#!/usr/bin/env python3
"""Tests for peer-side return-series ingestion -- HYP-04.

Three properties are load-bearing, and each is tested in BOTH directions,
because a rule that only ever denies is satisfied by a function that returns
False and a rule that only ever accepts is satisfied by one that returns True.

  1. COVERAGE IS DERIVED. `pair_eligibility` P5 asks whether a peer has usable
     return history; this module answers from the series itself. So the tests
     that matter are the ones proving a peer CANNOT read as covered without the
     data being there (test_4) -- paired with the control that a genuinely
     complete series DOES read as covered (test_3). Without that control every
     denial test passes trivially.

  2. GAPS ARE NEVER BRIDGED. A missing close must kill the returns on BOTH
     adjacent sessions. A return spanning a gap is not a one-session return,
     and admitting it would inflate realized variance exactly where the data is
     worst -- the direction that manufactures a signal (test_2).

  3. THE IMPORT BOUNDARY HOLDS. HYP-04's CI job installs only
     requirements-hyp04.txt. If this module ever imports the exchange calendar
     (which pulls `exchange_calendars`) that job breaks at import. test_8
     asserts the module leaks no such dependency, so the property is enforced
     rather than merely documented.

The coverage windows are asserted to MATCH `target.raw_log_ratio_target`
(test_5). If those two ever disagree, pairs get counted eligible whose target
then evaluates to NaN -- which inflates the eligible-pair count with
observations that silently vanish later, the worst of the available failures.

Offline. No network. All series synthetic; nothing is written to the repo.

Run directly: python test_hyp04_supply_chain_hedge_peer_returns.py
"""
from __future__ import annotations

import math
import socket
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import numpy as np  # noqa: E402

from hyp04_supply_chain_hedge.constants import (  # noqa: E402
    HORIZON_GRID,
    REFERENCE_WINDOW_TRADING_DAYS,
)
from hyp04_supply_chain_hedge.peer_returns import (  # noqa: E402
    CLOSES_HEADERS,
    SOURCE_OPERATOR_CSV,
    PeerReturnsError,
    PriceObservation,
    build_panel,
    build_series,
    coverage_for_event,
    load_panel,
    normalize_sessions,
    parse_close_rows,
    peer_history_map,
)
from hyp04_supply_chain_hedge.target import raw_log_ratio_target  # noqa: E402

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


N_SESSIONS = 80
SESSIONS = [date(2020, 1, 6) + timedelta(days=i) for i in range(N_SESSIONS)]


def _closes(ticker: str = "CVS", *, drop: set[int] = frozenset(),
            n: int = N_SESSIONS) -> list[PriceObservation]:
    """A clean upward drift; `drop` removes those session indices entirely."""
    return [PriceObservation(ticker, SESSIONS[i], 100.0 * (1.001 ** i))
            for i in range(n) if i not in drop]


# --------------------------------------------------------------------------


def test_1_parsing_rejects_every_bad_row_kind():
    rows = [
        ["CVS", "2020-01-06", "100"],      # good
        ["cvs", "2020-01-07", "101"],      # good, lowercased ticker
        ["CVS", "2020-01-06", "102"],      # duplicate
        ["CVS", "06/01/2020", "103"],      # bad date format
        ["CVS", "2020-13-45", "104"],      # well-formed but impossible date
        ["CVS", "2020-01-08", "0"],        # non-positive close
        ["CVS", "2020-01-09", "-3"],       # negative close
        ["CVS", "2020-01-10", "nan"],      # non-finite
        ["CVS", "2020-01-11", "abc"],      # not a number
        ["", "2020-01-12", "105"],         # blank ticker
        ["CVS", "2020-01-13"],             # short row
    ]
    obs, rejects = parse_close_rows(rows)
    check("1a. only the two valid rows survive", len(obs) == 2, f"got {len(obs)}")
    check("1b. every other row is rejected", len(rejects) == 9, f"got {len(rejects)}")
    check("1c. tickers are upper-cased", obs[1].ticker == "CVS", obs[1].ticker)

    fields = {r.field for r in rejects}
    check("1d. rejects name the offending field",
          {"session_date", "close", "ticker", "row"} <= fields, str(fields))

    dup = [r for r in rejects if "duplicate" in r.message]
    check("1e. the SECOND occurrence is the rejected one",
          len(dup) == 1 and dup[0].row_number == 3,
          str([(r.row_number, r.message) for r in dup]))

    # The positive control: a clean file must reject NOTHING. Without this,
    # a parser that rejected every row would pass 1a-1e.
    obs2, rej2 = parse_close_rows([["CVS", "2020-01-06", "100"],
                                   ["CVS", "2020-01-07", "101"]])
    check("1f. a clean file rejects nothing", len(obs2) == 2 and not rej2,
          f"{len(obs2)} obs, {len(rej2)} rejects")

    ok_hdr, _ = parse_close_rows([["CVS", "2020-01-06", "100"]],
                                 header=list(CLOSES_HEADERS))
    check("1g. correct headers accepted", len(ok_hdr) == 1)
    _, bad_hdr = parse_close_rows([["CVS", "2020-01-06", "100"]],
                                  header=["ticker", "date", "px"])
    check("1h. wrong headers rejected outright",
          len(bad_hdr) == 1 and bad_hdr[0].field == "header")


def test_2_gaps_are_never_bridged():
    s = build_series(_closes(drop={30}), ticker="CVS", sessions=SESSIONS)

    check("2a. the missing session has no return", s.log_returns[30] is None)
    check("2b. the session AFTER the gap also has no return",
          s.log_returns[31] is None,
          "a return spanning a gap is not a one-session return")
    check("2c. the session before the gap is unaffected",
          s.log_returns[29] is not None)
    check("2d. the second session after the gap recovers",
          s.log_returns[32] is not None)

    # The control: without the drop, all three are finite. Otherwise a function
    # that returned None everywhere would satisfy 2a and 2b.
    clean = build_series(_closes(), ticker="CVS", sessions=SESSIONS)
    check("2e. control -- no gap means all three are finite",
          all(clean.log_returns[i] is not None for i in (30, 31, 32)))

    check("2f. index 0 never has a return", clean.log_returns[0] is None,
          "no prior close exists inside the index")
    check("2g. finite count is n-1 on a complete series",
          clean.n_finite == N_SESSIONS - 1, str(clean.n_finite))

    # Missing is None, never 0.0 -- a zero return is a real observation
    # (a halt, a flat close) and must not be confused with absent data.
    check("2h. absent data is None, not 0.0",
          not any(r == 0.0 for r in s.log_returns if r is not None))

    vals = [r for r in clean.log_returns if r is not None]
    check("2i. returns are log ratios",
          math.isclose(vals[0], math.log(1.001), rel_tol=1e-12), str(vals[0]))


def test_3_coverage_accepts_a_genuinely_complete_series():
    """The load-bearing POSITIVE control for the whole module."""
    s = build_series(_closes(), ticker="CVS", sessions=SESSIONS)
    h = max(HORIZON_GRID)
    day = 40
    c = coverage_for_event(s, event_id="E1", anchor_day=day)
    check("3a. a complete series covers a mid-index event", c.sufficient,
          str(c.reasons))
    check("3b. it reports the full reference window",
          c.reference_have == REFERENCE_WINDOW_TRADING_DAYS, str(c.reference_have))
    check("3c. it reports the full horizon window", c.horizon_have == h,
          str(c.horizon_have))
    check("3d. no reasons on a sufficient coverage", c.reasons == ())

    # Exact boundaries. Index 0 has no return, so the earliest usable anchor
    # day is REFERENCE_WINDOW, not REFERENCE_WINDOW - 1.
    first_ok = REFERENCE_WINDOW_TRADING_DAYS
    check("3e. earliest sufficient anchor day is the reference window",
          coverage_for_event(s, event_id="E", anchor_day=first_ok).sufficient)
    check("3f. one day earlier is NOT sufficient",
          not coverage_for_event(s, event_id="E", anchor_day=first_ok - 1).sufficient)

    last_ok = N_SESSIONS - 1 - h
    check("3g. latest sufficient anchor day leaves a full horizon",
          coverage_for_event(s, event_id="E", anchor_day=last_ok).sufficient)
    check("3h. one day later is NOT sufficient",
          not coverage_for_event(s, event_id="E", anchor_day=last_ok + 1).sufficient)


def test_4_coverage_denies_without_the_data():
    s_clean = build_series(_closes(), ticker="CVS", sessions=SESSIONS)

    c = coverage_for_event(s_clean, event_id="E", anchor_day=3)
    check("4a. reference window before the index start denies", not c.sufficient)
    check("4b. and says so", any("before the session index" in r for r in c.reasons),
          str(c.reasons))

    c = coverage_for_event(s_clean, event_id="E", anchor_day=N_SESSIONS - 2)
    check("4c. horizon running past the index denies", not c.sufficient)
    check("4d. and says so", any("past the session index" in r for r in c.reasons),
          str(c.reasons))

    # A HOLE inside an otherwise long-enough window. This is the case a naive
    # length check would wave through.
    s_ref_hole = build_series(_closes(drop={35}), ticker="CVS", sessions=SESSIONS)
    c = coverage_for_event(s_ref_hole, event_id="E", anchor_day=40)
    check("4e. a hole INSIDE the reference window denies", not c.sufficient)
    check("4f. and reports the shortfall, not just a boolean",
          any("reference window has" in r for r in c.reasons), str(c.reasons))

    s_post_hole = build_series(_closes(drop={45}), ticker="CVS", sessions=SESSIONS)
    c = coverage_for_event(s_post_hole, event_id="E", anchor_day=40)
    check("4g. a hole inside the horizon window denies", not c.sufficient)
    check("4h. and reports it separately from the reference window",
          any("horizon window has" in r for r in c.reasons), str(c.reasons))

    # An empty series must deny rather than raise or read as covered.
    empty = build_series([], ticker="CVS", sessions=SESSIONS)
    check("4i. a series with no closes denies",
          not coverage_for_event(empty, event_id="E", anchor_day=40).sufficient)
    check("4j. an empty series has zero finite returns", empty.n_finite == 0)


def test_5_windows_match_the_target_definition():
    """Coverage must agree with target.py, or eligible pairs evaluate to NaN."""
    s = build_series(_closes(), ticker="CVS", sessions=SESSIONS)
    # Missing returns become NaN, NOT 0.0. Substituting a zero would fabricate
    # the very observation this module refuses to invent, and would make the
    # target compute a finite value from data that does not exist -- which is
    # exactly the disagreement this test is meant to catch.
    arr = np.array([np.nan if r is None else r for r in s.log_returns],
                   dtype=float)
    h = max(HORIZON_GRID)

    agree = disagree = 0
    for day in range(0, N_SESSIONS):
        cov = coverage_for_event(s, event_id="E", anchor_day=day).sufficient
        val = raw_log_ratio_target(arr, day, h)
        finite = bool(np.isfinite(val))
        if cov == finite:
            agree += 1
        else:
            disagree += 1

    check("5a. coverage agrees with the target's own windows at every day",
          disagree == 0, f"{disagree} disagreement(s) of {agree + disagree}")
    check("5b. and the comparison actually exercised both outcomes",
          0 < sum(1 for d in range(N_SESSIONS)
                  if coverage_for_event(s, event_id="E", anchor_day=d).sufficient)
          < N_SESSIONS,
          "if every day agreed trivially the test proves nothing")


def test_6_peer_history_map_is_conservative():
    s = build_series(_closes(), ticker="CVS", sessions=SESSIONS)
    covered = {"event_id": "E1", "anchor_day": 40, "peers": ["CVS"]}
    too_early = {"event_id": "E2", "anchor_day": 2, "peers": ["CVS"]}

    check("6a. a peer covering its only event is available",
          peer_history_map({"CVS": s}, [covered]) == {"CVS": True})
    check("6b. one uncovered event denies the peer entirely",
          peer_history_map({"CVS": s}, [covered, too_early]) == {"CVS": False},
          "per-peer is a lossy unit; it must resolve conservatively")
    check("6c. a peer with NO series is denied, not assumed",
          peer_history_map({}, [covered]) == {"CVS": False})

    m = peer_history_map({"CVS": s}, [{"event_id": "E", "anchor_day": 40,
                                       "peers": ["cvs"]}])
    check("6d. peer names are matched case-insensitively", m == {"CVS": True}, str(m))

    check("6e. a peer absent from every event is absent from the map",
          peer_history_map({"CVS": s}, []) == {})

    # The map's values must be usable as P5 input: real bools, not truthy objects.
    vals = peer_history_map({"CVS": s}, [covered, too_early]).values()
    check("6f. values are real bools", all(isinstance(v, bool) for v in vals))


def test_7_alignment_and_provenance():
    off = _closes() + [PriceObservation("CVS", date(1999, 1, 1), 50.0)]
    s = build_series(off, ticker="CVS", sessions=SESSIONS)
    check("7a. off-calendar dates are excluded",
          s.sessions_covered == N_SESSIONS, str(s.sessions_covered))
    check("7b. and surfaced rather than dropped silently",
          s.off_calendar_dates == (date(1999, 1, 1),), str(s.off_calendar_dates))

    mixed = _closes("CVS") + _closes("ODP")
    panel = build_panel(mixed, sessions=SESSIONS)
    check("7c. a panel separates tickers", panel.peers == ("CVS", "ODP"),
          str(panel.peers))
    check("7d. each series holds only its own ticker",
          panel.series["ODP"].closes_seen == N_SESSIONS,
          str(panel.series["ODP"].closes_seen))
    check("7e. provenance reports peers loaded",
          panel.provenance.peers_loaded == 2)
    check("7f. a populated panel is usable", panel.provenance.usable)

    empty = build_panel([], sessions=SESSIONS)
    check("7g. an empty panel is NOT usable", not empty.provenance.usable,
          "reading nothing is not a capture")

    # An unsorted session index is a caller bug and must not be survivable.
    for label, bad in (("unsorted", [SESSIONS[1], SESSIONS[0]]),
                       ("duplicated", [SESSIONS[0], SESSIONS[0]])):
        try:
            normalize_sessions(bad)
            check(f"7h. a {label} session index raises", False, "no exception")
        except PeerReturnsError:
            check(f"7h. a {label} session index raises", True)
        except Exception as e:  # noqa: BLE001
            check(f"7h. a {label} session index raises", False,
                  f"wrong type {type(e).__name__}")

    check("7i. a well-formed index is accepted",
          len(normalize_sessions(SESSIONS)) == N_SESSIONS)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "closes.csv"
        p.write_text(
            ",".join(CLOSES_HEADERS) + "\n"
            + "CVS,2020-01-06,100\nCVS,2020-01-07,101\nCVS,bad,102\n",
            encoding="utf-8")
        loaded = load_panel(p, sessions=SESSIONS)
        check("7j. a CSV load records its source",
              loaded.provenance.source == SOURCE_OPERATOR_CSV)
        check("7k. and hashes the bytes it read",
              len(loaded.provenance.source_sha256 or "") == 64)
        check("7l. a file with a bad row does not load clean",
              not loaded.provenance.loads_clean
              and loaded.provenance.rows_rejected == 1,
              str(loaded.provenance.rows_rejected))

        missing = load_panel(Path(td) / "nope.csv", sessions=SESSIONS)
        check("7m. an absent file yields an unusable panel, not an exception",
              not missing.provenance.usable and missing.series == {})


def test_8_import_boundary_and_offline():
    """HYP-04 CI installs only requirements-hyp04.txt -- keep it that way."""
    forbidden = ("exchange_calendars", "yfinance", "sklearn")
    leaked = [m for m in forbidden if m in sys.modules]
    check("8a. no heavy dependency is pulled in by this package",
          not leaked, f"leaked: {leaked}")

    # Check actual IMPORT STATEMENTS, not substrings: this module's docstring
    # discusses the exchange calendar at length to explain why it does not
    # import it, and a naive substring match fails on that prose.
    import ast

    import hyp04_supply_chain_hedge.peer_returns as pr
    tree = ast.parse(Path(pr.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()      # absolute imports only
    relative: set[str] = set()      # `from .x import ...` -- in-package by construction
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import carries level >= 1 and a bare module name, so
            # it cannot be told from an absolute one by string inspection.
            if node.level:
                relative.add("." * node.level + (node.module or ""))
            elif node.module:
                imported.add(node.module)

    banned = {"exchange_calendars", "yfinance", "requests", "urllib.request",
              "gst_market_response.exchange_calendar"}
    hit = sorted(n for n in imported
                 if n in banned or n.split(".")[0] in {"exchange_calendars",
                                                       "yfinance", "requests"})
    check("8b. the module imports no calendar and no HTTP client", not hit,
          f"imports {hit}; the session index is injected precisely so it need not")
    stdlib = {"csv", "hashlib", "math", "re", "dataclasses", "datetime",
              "pathlib", "typing", "__future__"}
    nonstd = sorted(n for n in imported if n.split(".")[0] not in stdlib)
    check("8c. every absolute import is stdlib", not nonstd, str(nonstd))
    check("8d. and the only non-stdlib imports are in-package",
          relative == {".constants"}, str(sorted(relative)))

    try:
        socket.getaddrinfo("example.com", 443)
        check("8e. network blocked", False, "a lookup succeeded")
    except Exception as e:  # noqa: BLE001
        check("8e. network blocked", type(e).__name__ == "NetworkBlocked")


def test_9_nothing_here_opens_the_gate():
    """This module changes no display condition. It is a capture path only."""
    from hyp04_supply_chain_hedge.display_gate import current_decision

    d = current_decision()
    check("9a. the display gate is still CLOSED", not d.open, str(d.status))
    check("9b. C5 still denies -- peer returns are not linkage",
          not d.conditions.get("C5_not_placeholder", True))
    check("9c. exactly four denials, unchanged", len(d.denials) == 4,
          f"{len(d.denials)}: {d.denials}")


def test_10_derived_availability_actually_satisfies_p5():
    """The whole point: P5 answered from data, not from a caller's assertion.

    `resolve_from_curated_map` takes a `peer_history` dict. This proves the dict
    `peer_history_map` derives is accepted there AND is what clears P5 -- by
    checking P5 is ABSENT from the denial profile while P1 still denies, since
    no anchor eligibility was supplied. A test that only checked "eligible == 0"
    could not tell those two conditions apart.
    """
    from hyp04_supply_chain_hedge.curated_linkage import LSE
    from hyp04_supply_chain_hedge.linkage_resolution import resolve_from_curated_map

    map_path = LSE / "HYP04_Linkage_Map_v1.0.csv"
    if not map_path.is_file():
        skip("10. derived availability satisfies P5", "no committed map on disk")
        return

    obs = _closes("CVS")
    panel = build_panel(obs, sessions=SESSIONS)
    events = [{"event_id": "MCK-TEST", "anchor": "MCK",
               "event_date": "2020-03-04", "anchor_day": 40, "peers": ["CVS"]}]

    hist = peer_history_map(panel.series, events)
    check("10a. availability is derived as True for a covered peer",
          hist == {"CVS": True}, str(hist))

    res = resolve_from_curated_map(events, map_path=map_path, peer_history=hist)
    reasons = res.denial_reasons()
    check("10b. P5 does not deny -- the derived history was accepted",
          "P5" not in reasons, str(reasons))
    check("10c. P1 still denies -- no anchor eligibility was supplied",
          reasons.get("P1", 0) == 1, str(reasons))

    # The other direction: an EMPTY panel must put P5 back into the denials.
    # Without this, "P5 absent" could just mean P5 never fires at all.
    empty_hist = peer_history_map({}, events)
    res2 = resolve_from_curated_map(events, map_path=map_path,
                                    peer_history=empty_hist)
    check("10d. control -- with no series, P5 denies",
          "P5" in res2.denial_reasons(), str(res2.denial_reasons()))


def test_11_the_operator_template() -> None:
    """The blank schema stays blank, and matches what the loader accepts."""
    from hyp04_supply_chain_hedge.peer_returns import TEMPLATE_HEADERS_CSV

    if not TEMPLATE_HEADERS_CSV.is_file():
        skip("11. closes template present", f"{TEMPLATE_HEADERS_CSV.name} missing")
        return

    lines = [l for l in TEMPLATE_HEADERS_CSV.read_text(encoding="utf-8-sig")
             .splitlines() if l.strip()]
    check("11a. the template contains headers only", len(lines) == 1,
          f"{len(lines)} non-blank lines -- a data row in a template is how "
          "half-finished content ships by accident")
    check("11b. its header row is exactly the loader's schema",
          tuple(h.strip() for h in lines[0].split(",")) == CLOSES_HEADERS,
          f"{lines[0]!r} vs {CLOSES_HEADERS}")

    # It must round-trip: the loader accepts the template as a valid, empty file
    # rather than rejecting its own schema.
    panel = load_panel(TEMPLATE_HEADERS_CSV, sessions=SESSIONS)
    check("11c. the loader accepts the template's header row",
          panel.provenance.rows_rejected == 0, str(panel.provenance.as_dict()))
    check("11d. and an empty template yields an unusable panel, not a crash",
          not panel.provenance.usable and panel.series == {},
          "a schema is not data")


if __name__ == "__main__":
    test_1_parsing_rejects_every_bad_row_kind()
    test_2_gaps_are_never_bridged()
    test_3_coverage_accepts_a_genuinely_complete_series()
    test_4_coverage_denies_without_the_data()
    test_5_windows_match_the_target_definition()
    test_6_peer_history_map_is_conservative()
    test_7_alignment_and_provenance()
    test_8_import_boundary_and_offline()
    test_9_nothing_here_opens_the_gate()
    test_10_derived_availability_actually_satisfies_p5()
    test_11_the_operator_template()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 PEER-RETURNS TESTS PASSED")
    sys.exit(0)
