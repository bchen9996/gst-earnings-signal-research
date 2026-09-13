#!/usr/bin/env python3
"""run_hyp05_peer_market_cap.py tests -- the pure-logic helpers
(_anchor_event_dates, _resolved_candidates, the direction->relationship_type
mapping) plus main()'s pre-flight overwrite guard. The LIVE pipeline
beyond that guard is NOT exercised here, same discipline as every other
live-fetch script's test file in this repo.

Fully offline, synthetic fixtures written to a temp dir. Sockets blocked
before import.

Run directly: python test_hyp04_supply_chain_hedge_hyp05_peer_market_cap.py
"""
from __future__ import annotations

import csv
import json
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

from hyp04_supply_chain_hedge import run_hyp05_peer_market_cap as M  # noqa: E402
from hyp04_supply_chain_hedge.run_hyp05_peer_market_cap import (  # noqa: E402
    DIRECTION_TO_RELATIONSHIP_TYPE,
    _anchor_event_dates,
    _resolved_candidates,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp05_mc_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


_SHOCKS_ROWS = [
    {"event_id": "A-1", "anchor_ticker": "AAA", "release_date": "2020-01-01",
     "status": "shock_computed"},
    {"event_id": "A-2", "anchor_ticker": "AAA", "release_date": "2020-04-01",
     "status": "shock_computed"},
    {"event_id": "A-3", "anchor_ticker": "AAA", "release_date": "2020-07-01",
     "status": "denied_session"},
    {"event_id": "A-4", "anchor_ticker": "AAA", "release_date": "2020-01-01",
     "status": "shock_computed"},  # deliberate duplicate date
    {"event_id": "B-1", "anchor_ticker": "BBB", "release_date": "2021-03-01",
     "status": "shock_computed"},
]
_SHOCKS_FIELDS = ("event_id", "anchor_ticker", "release_date", "status")


def _write_shocks_csv() -> Path:
    p = TMP / "shocks.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_SHOCKS_FIELDS)
        w.writeheader()
        for r in _SHOCKS_ROWS:
            w.writerow(r)
    return p


def test_1_anchor_event_dates_filters_and_dedupes() -> None:
    p = _write_shocks_csv()
    dates_a = _anchor_event_dates(p, "AAA")
    check("1a. only shock_computed rows counted (denied_session excluded)",
          "2020-07-01" not in dates_a, str(dates_a))
    check("1b. duplicate dates for the same anchor are deduplicated",
          dates_a == ["2020-01-01", "2020-04-01"], str(dates_a))
    dates_b = _anchor_event_dates(p, "BBB")
    check("1c. a different anchor's rows don't leak in",
          dates_b == ["2021-03-01"], str(dates_b))
    dates_c = _anchor_event_dates(p, "ZZZ")
    check("1d. an anchor with no rows at all yields an empty list, not an "
          "error", dates_c == [])


def test_1e_anchor_event_dates_unions_multiple_csvs() -> None:
    """Added 2026-09-12 alongside run_hyp05_additional_anchor_shocks.py:
    an anchor whose shock_computed rows live in a SECOND, separate CSV
    (e.g. HYP05_ADDITIONAL_ANCHOR_SHOCKS_*.csv, never merged into HYP-04's
    own file) must still resolve, unioned with the first file's rows for
    the same or a different anchor."""
    p1 = _write_shocks_csv()
    p2 = TMP / "shocks_2.csv"
    with p2.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_SHOCKS_FIELDS)
        w.writeheader()
        w.writerow({"event_id": "C-1", "anchor_ticker": "CCC",
                   "release_date": "2022-01-01", "status": "shock_computed"})
        w.writerow({"event_id": "A-5", "anchor_ticker": "AAA",
                   "release_date": "2020-10-01", "status": "shock_computed"})

    check("1e-single. a bare Path still works unchanged (old call shape)",
          _anchor_event_dates(p1, "AAA") == ["2020-01-01", "2020-04-01"])
    check("1e-list-new-ticker. a ticker present ONLY in the second file "
          "resolves via the list form",
          _anchor_event_dates([p1, p2], "CCC") == ["2022-01-01"])
    check("1e-list-union. a ticker with rows in BOTH files gets the union, "
          "sorted, deduplicated",
          _anchor_event_dates([p1, p2], "AAA")
          == ["2020-01-01", "2020-04-01", "2020-10-01"])


def test_2_resolved_candidates_joins_and_filters() -> None:
    name_search = {
        "results": [
            {"counterparty": "Foo Inc", "tradeable": True, "peer_ticker": "FOO",
             "registrant_cik": "0000000001", "anchor_ticker": "AAA"},
            {"counterparty": "Bar Corp", "tradeable": False, "peer_ticker": "",
             "registrant_cik": "", "anchor_ticker": "AAA"},
            {"counterparty": "Baz LLC", "tradeable": True, "peer_ticker": "BAZ",
             "registrant_cik": "0000000002", "anchor_ticker": "BBB"},
            {"counterparty": "No Edge Co", "tradeable": True,
             "peer_ticker": "NOE", "registrant_cik": "0000000003",
             "anchor_ticker": "AAA"},
        ],
    }
    candidate_linkage = {
        "edges": [
            {"counterparty_is_named": True, "named_counterparty": "Foo Inc",
             "direction": "customer", "as_of_date": "2019-01-01",
             "source": "EDGAR_10K_ASC280"},
            {"counterparty_is_named": True, "named_counterparty": "Baz LLC",
             "direction": "competitor", "as_of_date": "2019-06-01",
             "source": "EDGAR_10K_COMPETITION_SECTION_PROSE"},
            {"counterparty_is_named": False, "named_counterparty": None,
             "direction": "supplier", "as_of_date": "2019-01-01",
             "source": "EDGAR_10K_ASC280"},
        ],
    }
    ns_path = TMP / "name_search.json"
    cl_path = TMP / "candidate_linkage.json"
    ns_path.write_text(json.dumps(name_search), encoding="utf-8")
    cl_path.write_text(json.dumps(candidate_linkage), encoding="utf-8")

    rows = _resolved_candidates(ns_path, cl_path)
    by_ticker = {r["peer_ticker"]: r for r in rows}

    check("2a. an untradeable result is excluded",
          "" not in by_ticker and not any(r["peer_ticker"] == "" for r in rows))
    check("2b. a tradeable result with no matching NAMED edge is excluded "
          "(NOE has no edge in candidate_linkage at all)",
          "NOE" not in by_ticker, str(list(by_ticker)))
    check("2c. exactly the two well-formed rows survive",
          set(by_ticker) == {"FOO", "BAZ"}, str(set(by_ticker)))
    check("2d. direction/as_of_date/source are carried over from the "
          "matched edge",
          by_ticker["FOO"]["direction"] == "customer"
          and by_ticker["FOO"]["as_of_date"] == "2019-01-01"
          and by_ticker["FOO"]["source"] == "EDGAR_10K_ASC280")
    check("2e. registrant_cik and anchor_ticker come from the name-search "
          "result, not the edge",
          by_ticker["BAZ"]["registrant_cik"] == "0000000002"
          and by_ticker["BAZ"]["anchor_ticker"] == "BBB")


def test_3_direction_mapping_is_complete_and_sane() -> None:
    check("3a. all three extractor directions have a mapping",
          set(DIRECTION_TO_RELATIONSHIP_TYPE) == {"customer", "supplier",
                                                    "competitor"},
          str(set(DIRECTION_TO_RELATIONSHIP_TYPE)))
    check("3b. customer maps to a direct_ relationship type",
          DIRECTION_TO_RELATIONSHIP_TYPE["customer"] == "direct_customer")
    check("3c. supplier maps to a direct_ relationship type",
          DIRECTION_TO_RELATIONSHIP_TYPE["supplier"] == "direct_supplier")
    check("3d. competitor maps to sector_competitor, not a direct_ type -- "
          "it names a rival, not a transacting counterparty",
          DIRECTION_TO_RELATIONSHIP_TYPE["competitor"] == "sector_competitor")


def test_4_main_never_overwrites_out() -> None:
    """Fixed 2026-09-12 after this script's own default --out silently
    overwrote a real, already-committed governance artifact from an
    earlier pass -- see run_hyp05_peer_market_cap.py's inline comment.
    This must refuse before touching name-search/candidate-linkage at
    all, the same way every other staged script in this project does."""
    import io
    from contextlib import redirect_stdout, redirect_stderr

    existing = TMP / "already_there.json"
    existing.write_text("{}", encoding="utf-8")
    # A name-search path that does NOT exist -- if the overwrite guard
    # did not fire FIRST, this would refuse for the wrong reason instead.
    missing_name_search = TMP / "does_not_exist.json"

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--name-search", str(missing_name_search),
                      "--out", str(existing)])
    check("4a. refuses with a non-zero exit when --out already exists",
          code != 0, str(code))
    check("4b. says why, on stderr, naming the overwrite -- not the "
          "missing name-search file", "already exists" in err.getvalue(),
          err.getvalue()[:200])
    check("4c. never reaches the resolved-candidates step",
          "resolved, tradeable candidates" not in out.getvalue(),
          out.getvalue()[:160])
    check("4d. the existing file is untouched",
          existing.read_text(encoding="utf-8") == "{}")


def test_5_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("5a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("5a. network blocked", True)


if __name__ == "__main__":
    test_1_anchor_event_dates_filters_and_dedupes()
    test_1e_anchor_event_dates_unions_multiple_csvs()
    test_2_resolved_candidates_joins_and_filters()
    test_3_direction_mapping_is_complete_and_sane()
    test_4_main_never_overwrites_out()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_PEER_MARKET_CAP TESTS PASSED")
    sys.exit(0)
