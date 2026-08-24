#!/usr/bin/env python3
"""Tests for the operator closes request -- HYP-04.

The linkage-source decision of 2026-08-23 chose operator-supplied CSVs over a
price vendor, which makes "which closes, exactly?" a question someone has to
answer correctly ONCE. Get it wrong and the operator collects the wrong data,
discovers it only when coverage denies, and the denial points at the window
rather than at the request.

Three properties carry the weight:

  1. THE 41st CLOSE (test_1). A 20-session reference window plus a 20-session
     horizon needs 40 RETURNS and 41 CLOSES -- a return at index i needs closes
     at i-1 AND i, so the earliest required return drags in one more close
     before it. Asking for 40 produces "reference window has 19/20 finite
     returns", which is true and unhelpful.

  2. IT AGREES WITH COVERAGE (test_2). The request is only correct if supplying
     exactly what it asks for makes coverage_for_event sufficient. That is
     asserted by BUILDING a panel from precisely the requested sessions and
     checking coverage passes -- and by checking that dropping any single
     requested session makes it fail, so no session in the list is surplus.

  3. IT NEVER ASKS FOR UNUSABLE DATA (test_3). P3 denies a pair whose edge was
     disclosed after the event regardless of prices. Those are reported as
     skipped with a reason, not silently omitted -- an operator who cannot see
     why a peer is missing will assume the tool is broken.

Offline. No network. Nothing is written to the repo.

Run directly: python test_hyp04_supply_chain_hedge_closes_requirements.py
"""
from __future__ import annotations

import socket
import sys
from datetime import date, timedelta


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.closes_requirements import (  # noqa: E402
    closes_per_event,
    format_report,
    requirements_for,
    session_span,
)
from hyp04_supply_chain_hedge.constants import (  # noqa: E402
    HORIZON_GRID,
    REFERENCE_WINDOW_TRADING_DAYS,
)
from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    CuratedEdge,
    direction_for,
)
from hyp04_supply_chain_hedge.event_panel import resolve_events  # noqa: E402
from hyp04_supply_chain_hedge.peer_returns import (  # noqa: E402
    PriceObservation,
    build_panel,
    coverage_for_event,
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


R = REFERENCE_WINDOW_TRADING_DAYS
H = max(HORIZON_GRID)
N = 300


def _sessions(n: int = N) -> list[date]:
    out: list[date] = []
    d = date(2019, 6, 3)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


SESSIONS = _sessions()


_ROW = [0]


def _edge(anchor: str, peer: str, as_of: str) -> CuratedEdge:
    """A synthetic edge. `direction` is DERIVED via direction_for(), never
    hand-set -- the loader treats it as derived and a fixture that hardcodes it
    could disagree with production without any test noticing."""
    _ROW[0] += 1
    return CuratedEdge(
        anchor_ticker=anchor, peer_ticker=peer,
        relationship_type="direct_customer",
        direction=direction_for("direct_customer"),
        relationship_direction_notes="", confidence="high",
        source_type="10-K Customer Concentration Note",
        source_citation="synthetic fixture", source_url="",
        as_of_date=as_of, as_of_date_basis="filing date of source",
        date_confidence="high", notes_caveats="",
        curated_by="test", curated_date="2026-08-23", review_status="draft",
        row_number=_ROW[0])


def _event(event_id: str, anchor: str, day: int):
    return resolve_events(
        [{"event_id": event_id, "anchor": anchor,
          "response_session_date": SESSIONS[day]}],
        sessions=SESSIONS).resolved[0]


# --------------------------------------------------------------------------


def test_1_the_41st_close() -> None:
    check("1a. one event needs reference + horizon + ONE more close",
          closes_per_event() == R + H + 1, str(closes_per_event()))
    check("1b. which is 41 at the registered constants",
          closes_per_event() == 41, str(closes_per_event()))
    check("1c. and is NOT reference + horizon",
          closes_per_event() != R + H,
          "40 would leave the first reference return uncomputable")

    start, end = session_span(100)
    check("1d. the span starts a full reference window BEFORE the anchor",
          start == 100 - R, str(start))
    check("1e. not reference-1, which is where the returns start",
          start != 100 - R + 1,
          "the earliest reference RETURN needs a close before it")
    check("1f. and ends at the last horizon session", end == 100 + H, str(end))
    check("1g. the span is inclusive and matches the count",
          end - start + 1 == closes_per_event(), f"{start}..{end}")


def test_2_the_request_is_exactly_what_coverage_needs() -> None:
    """Supplying precisely the requested closes must satisfy coverage."""
    day = 120
    ev = _event("E1", "MCK", day)
    rep = requirements_for([ev], [_edge("MCK", "CVS", "2013-05-07")],
                           sessions=SESSIONS)

    check("2a. one peer is requested", len(rep.requirements) == 1,
          str([r.peer for r in rep.requirements]))
    req = rep.requirements[0]
    check("2b. it asks for exactly 41 sessions", req.n_sessions == 41,
          str(req.n_sessions))
    check("2c. nothing was skipped or truncated",
          not rep.skipped and not rep.truncated,
          f"{len(rep.skipped)} skipped, {len(rep.truncated)} truncated")

    # Build a panel from ONLY the requested sessions.
    obs = [PriceObservation("CVS", d, 100.0 * (1.001 ** i))
           for i, d in enumerate(req.sessions)]
    series = build_panel(obs, sessions=SESSIONS).series["CVS"]
    cov = coverage_for_event(series, event_id="E1", anchor_day=day)
    check("2d. supplying exactly the request satisfies coverage", cov.sufficient,
          str(cov.reasons))

    # And every requested session is load-bearing: drop any one and it fails.
    # Checked across the whole list, not a sample -- a surplus session would
    # mean the operator was asked for data the analysis never reads.
    surplus: list[str] = []
    for i in range(req.n_sessions):
        subset = [o for j, o in enumerate(obs) if j != i]
        s = build_panel(subset, sessions=SESSIONS).series["CVS"]
        if coverage_for_event(s, event_id="E1", anchor_day=day).sufficient:
            surplus.append(req.sessions[i].isoformat())
    check("2e. every requested session is load-bearing -- none is surplus",
          not surplus, f"removable: {surplus}")

    # The control: one MORE session than requested is still sufficient, so 2e
    # is measuring necessity rather than a coverage function that denies always.
    extra = obs + [PriceObservation("CVS", SESSIONS[day + H + 1], 999.0)]
    s = build_panel(extra, sessions=SESSIONS).series["CVS"]
    check("2f. control -- a superset also satisfies coverage",
          coverage_for_event(s, event_id="E1", anchor_day=day).sufficient)


def test_3_p3_ineligible_pairs_are_skipped_with_a_reason() -> None:
    day = 120
    ev = _event("E1", "PKG", day)
    event_iso = SESSIONS[day].isoformat()

    # Edge disclosed AFTER the event -> P3 denies regardless of prices.
    late = requirements_for([ev], [_edge("PKG", "ODP", "2099-01-01")],
                            sessions=SESSIONS)
    check("3a. an edge disclosed after the event asks for nothing",
          not late.requirements, str([r.peer for r in late.requirements]))
    check("3b. and is reported as skipped, not silently omitted",
          len(late.skipped) == 1, str(late.skipped))
    check("3c. with P3 named in the reason",
          "P3" in late.skipped[0].reason, late.skipped[0].reason)

    # Same day is NOT strictly before -- the boundary P3 denies.
    same = requirements_for([ev], [_edge("PKG", "ODP", event_iso)],
                            sessions=SESSIONS)
    check("3d. an edge dated ON the event day is skipped (strictly before)",
          not same.requirements and len(same.skipped) == 1)

    # One day earlier IS eligible -- the control for 3a-3d.
    early = requirements_for([ev], [_edge("PKG", "ODP",
                                          SESSIONS[day - 1].isoformat())],
                             sessions=SESSIONS)
    check("3e. control -- one session earlier IS requested",
          len(early.requirements) == 1 and not early.skipped,
          str(early.skipped))


def test_4_spans_off_the_index_are_truncated_not_clipped() -> None:
    edge = [_edge("MCK", "CVS", "2013-05-07")]

    early = requirements_for([_event("E", "MCK", 3)], edge, sessions=SESSIONS)
    check("4a. an event too near the start is truncated, not clipped",
          not early.requirements and len(early.truncated) == 1,
          str(early.truncated))
    check("4b. and the reason names the index bounds",
          "index holds" in early.truncated[0].reason, early.truncated[0].reason)

    late = requirements_for([_event("E", "MCK", N - 3)], edge, sessions=SESSIONS)
    check("4c. an event too near the end is truncated too",
          not late.requirements and len(late.truncated) == 1)

    ok = requirements_for([_event("E", "MCK", R)], edge, sessions=SESSIONS)
    check("4d. control -- the earliest fully-covered event IS requested",
          len(ok.requirements) == 1 and not ok.truncated,
          str(ok.truncated))


def test_5_multiple_events_share_sessions() -> None:
    """Overlapping windows must be unioned, not double-counted."""
    edge = [_edge("MCK", "CVS", "2013-05-07")]
    far = requirements_for([_event("A", "MCK", 100), _event("B", "MCK", 200)],
                           edge, sessions=SESSIONS)
    check("5a. two distant events need two full windows",
          far.total_rows == 2 * closes_per_event(), str(far.total_rows))

    near = requirements_for([_event("A", "MCK", 100), _event("B", "MCK", 101)],
                            edge, sessions=SESSIONS)
    check("5b. two adjacent events share all but one session",
          near.total_rows == closes_per_event() + 1, str(near.total_rows))
    check("5c. both events are recorded against the peer",
          near.requirements[0].events_covered == ("A", "B"),
          str(near.requirements[0].events_covered))
    check("5d. sessions are sorted and unique",
          list(near.requirements[0].sessions)
          == sorted(set(near.requirements[0].sessions)))


def test_6_the_report_is_actionable() -> None:
    rep = requirements_for([_event("E1", "MCK", 120)],
                           [_edge("MCK", "CVS", "2013-05-07"),
                            _edge("MCK", "RAD", "2099-01-01")],
                           sessions=SESSIONS)
    text = format_report(rep)

    check("6a. it names the schema file", "TEMPLATE_headers.csv" in text)
    check("6b. it states the per-event count and why the +1 exists",
          "41 sessions per (peer, event)" in text
          and "prior close" in text, text[:160])
    check("6c. it gives a total row count",
          f"TOTAL ROWS TO PRODUCE: {rep.total_rows}" in text)
    check("6d. it names the peer and its span", "CVS:" in text)
    check("6e. and explains the skipped pair rather than hiding it",
          "SKIPPED" in text and "RAD" in text, text[-200:])

    d = rep.as_dict()
    check("6f. the dict form carries the explicit session list",
          len(d["peers"][0]["sessions"]) == 41)
    check("6g. and records the constants it was computed from",
          d["reference_window"] == R and d["max_horizon"] == H)


def test_7_against_the_committed_map() -> None:
    from hyp04_supply_chain_hedge.curated_linkage import LSE, load_curated_linkage

    map_path = LSE / "HYP04_Linkage_Map_v1.0.csv"
    if not map_path.is_file():
        skip("7. committed map", "no curated map on disk")
        return

    res = load_curated_linkage(map_path)
    check("7a. the committed map loads clean", res.ok and len(res.edges) >= 1,
          str(res.rows_rejected))

    ev = _event("MCK-REAL", "MCK", 150)
    rep = requirements_for([ev], res.edges, sessions=SESSIONS)
    check("7b. it produces a request from the real edges",
          len(rep.requirements) == 1 and rep.requirements[0].peer == "CVS",
          str([r.peer for r in rep.requirements]))
    check("7c. asking for exactly 41 CVS sessions",
          rep.requirements[0].n_sessions == 41)
    check("7d. PKG's edge contributes nothing to an MCK event",
          all(r.peer != "ODP" for r in rep.requirements),
          "an edge belongs to its own anchor")


def test_8_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("8a. network blocked", False, "a lookup succeeded")
    except Exception as e:  # noqa: BLE001
        check("8a. network blocked", type(e).__name__ == "NetworkBlocked")


def test_9_the_cli_defers_the_calendar() -> None:
    """Importing this module must not pull the exchange calendar.

    The CLI needs the AUTHORITATIVE XNYS sessions -- a weekday approximation
    would put market holidays into the request, and the operator would collect
    closes that do not exist. But `gst_market_response.exchange_calendar`
    imports `exchange_calendars`, which requirements-hyp04.txt deliberately
    omits, so importing it at module scope would break HYP-04's CI job.

    It is therefore imported lazily inside main(), and the CLI REFUSES when it
    is unavailable rather than approximating. This asserts the boundary rather
    than trusting the comment that describes it.
    """
    import ast
    from pathlib import Path

    import hyp04_supply_chain_hedge.closes_requirements as cr

    check("9a. a plain import leaks no heavy dependency",
          "exchange_calendars" not in sys.modules,
          "importing this module must stay cheap and CI-safe")

    tree = ast.parse(Path(cr.__file__).read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:                      # MODULE SCOPE only
        if isinstance(node, ast.Import):
            top_level.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            top_level.add(node.module)
    bad = sorted(n for n in top_level
                 if n.split(".")[0] in {"exchange_calendars", "gst_market_response",
                                        "requests", "yfinance", "numpy"})
    check("9b. no heavy import at module scope", not bad, str(bad))

    src = Path(cr.__file__).read_text(encoding="utf-8")
    check("9c. the calendar IS imported somewhere -- deferred, not absent",
          "from gst_market_response.exchange_calendar import" in src,
          "the CLI must use the authoritative calendar, not a weekday guess")
    check("9d. and the refusal path names the reason",
          "REFUSING rather than" in src and "holidays" in src)


if __name__ == "__main__":
    test_1_the_41st_close()
    test_2_the_request_is_exactly_what_coverage_needs()
    test_3_p3_ineligible_pairs_are_skipped_with_a_reason()
    test_4_spans_off_the_index_are_truncated_not_clipped()
    test_5_multiple_events_share_sessions()
    test_6_the_report_is_actionable()
    test_7_against_the_committed_map()
    test_8_offline()
    test_9_the_cli_defers_the_calendar()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 CLOSES-REQUIREMENTS TESTS PASSED")
    sys.exit(0)
