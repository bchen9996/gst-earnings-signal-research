#!/usr/bin/env python3
"""run_hyp07_peer_market_cap.py tests -- the pure-logic helpers
(_resolved_candidates, the reused DIRECTION_TO_RELATIONSHIP_TYPE/
_anchor_event_dates imports) plus main()'s pre-flight overwrite guard. The
LIVE pipeline beyond that guard is NOT exercised here, same discipline as
every other live-fetch script's test file in this repo.

Fully offline, synthetic fixtures written to a temp dir. Sockets blocked
before import.

Run directly: python test_hyp04_supply_chain_hedge_hyp07_peer_market_cap.py
"""
from __future__ import annotations

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

from hyp04_supply_chain_hedge import run_hyp07_peer_market_cap as M  # noqa: E402
from hyp04_supply_chain_hedge.run_hyp07_peer_market_cap import (  # noqa: E402
    DIRECTION_TO_RELATIONSHIP_TYPE,
    _resolved_candidates,
)

FAILURES: list[str] = []
TMP = Path(tempfile.mkdtemp(prefix="hyp07_mc_test_"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def test_1_resolved_candidates_joins_across_multiple_linkage_files() -> None:
    name_search = {
        "results": [
            {"counterparty": "AMD", "tradeable": True, "peer_ticker": "AMD",
             "registrant_cik": "0000000001", "anchor_ticker": "INTC"},
            {"counterparty": "Siemens Energy", "tradeable": False,
             "peer_ticker": "", "registrant_cik": "", "anchor_ticker": "BKR"},
            {"counterparty": "C4D", "tradeable": True, "peer_ticker": "CFDX",
             "registrant_cik": "0000000002", "anchor_ticker": "ADBE"},
            {"counterparty": "No Edge Co", "tradeable": True,
             "peer_ticker": "NOE", "registrant_cik": "0000000003",
             "anchor_ticker": "INTC"},
        ],
    }
    linkage_1 = {"edges": [
        {"reporting_company": "INTC", "counterparty_is_named": True,
         "named_counterparty": "AMD", "direction": "competitor",
         "as_of_date": "2026-01-23",
         "source": "EDGAR_10K_COMPETITION_SECTION_PROSE"},
        {"reporting_company": "MCK", "counterparty_is_named": True,
         "named_counterparty": "MCK-cust", "direction": "customer",
         "as_of_date": "2019-01-01", "source": "EDGAR_10K_ASC280"},
    ]}
    linkage_2 = {"edges": [
        {"anchor_ticker": "ADBE", "counterparty_is_named": True,
         "named_counterparty": "C4D", "direction": "competitor",
         "as_of_date": "2021-01-15",
         "source": "EDGAR_10K_COMPETITION_SECTION_PROSE_HISTORICAL_WALK"},
    ]}
    ns_path = TMP / "name_search.json"
    cl1_path = TMP / "linkage_1.json"
    cl2_path = TMP / "linkage_2.json"
    ns_path.write_text(json.dumps(name_search), encoding="utf-8")
    cl1_path.write_text(json.dumps(linkage_1), encoding="utf-8")
    cl2_path.write_text(json.dumps(linkage_2), encoding="utf-8")

    rows = _resolved_candidates(ns_path, (cl1_path, cl2_path))
    by_ticker = {r["peer_ticker"]: r for r in rows}

    check("1a. an untradeable result is excluded",
          not any(r["peer_ticker"] == "" for r in rows))
    check("1b. a tradeable result with no matching NAMED edge in either "
          "file is excluded (NOE has no edge anywhere)",
          "NOE" not in by_ticker, str(list(by_ticker)))
    check("1c. a match from the SECOND linkage file resolves (C4D)",
          "CFDX" in by_ticker, str(list(by_ticker)))
    check("1d. exactly the two well-formed, competitor-direction rows "
          "survive", set(by_ticker) == {"AMD", "CFDX"}, str(set(by_ticker)))
    check("1e. direction/as_of_date/source carried from the matched edge",
          by_ticker["AMD"]["direction"] == "competitor"
          and by_ticker["AMD"]["as_of_date"] == "2026-01-23")
    check("1f. a customer-direction edge in the same file never leaks in "
          "(defense in depth -- HYP-07 is competitor-only)",
          "MCK-cust" not in {r["counterparty"] for r in rows})


def test_1g_same_counterparty_name_under_two_anchors_keeps_both_correctly() -> None:
    """Regression test for the real bug found reviewing HYP-07's own
    confirmed leads: FISERV INC genuinely recurs as a confirmed competitor
    under three different real anchors (AAPL, GOOGL, SBUX), each with its
    own as_of_date. A name-only join would silently give every anchor's
    row the SAME (wrong, for at least one) as_of_date. Keyed correctly, by
    (anchor_ticker, named_counterparty), both rows below must keep their
    OWN, distinct as_of_date."""
    name_search = {
        "results": [
            {"counterparty": "FISERV INC", "tradeable": True,
             "peer_ticker": "FI", "registrant_cik": "0000798354",
             "anchor_ticker": "AAPL"},
            {"counterparty": "FISERV INC", "tradeable": True,
             "peer_ticker": "FI", "registrant_cik": "0000798354",
             "anchor_ticker": "GOOGL"},
        ],
    }
    linkage = {"edges": [
        {"anchor_ticker": "AAPL", "counterparty_is_named": True,
         "named_counterparty": "FISERV INC", "direction": "competitor",
         "as_of_date": "2016-02-19", "source": "X"},
        {"anchor_ticker": "GOOGL", "counterparty_is_named": True,
         "named_counterparty": "FISERV INC", "direction": "competitor",
         "as_of_date": "2017-02-23", "source": "X"},
    ]}
    ns_path = TMP / "fiserv_ns.json"
    cl_path = TMP / "fiserv_linkage.json"
    ns_path.write_text(json.dumps(name_search), encoding="utf-8")
    cl_path.write_text(json.dumps(linkage), encoding="utf-8")

    rows = _resolved_candidates(ns_path, (cl_path,))
    check("1g-count. BOTH anchor-pairs survive, not collapsed to one",
          len(rows) == 2, str(rows))
    by_anchor = {r["anchor_ticker"]: r for r in rows}
    check("1g-aapl. the AAPL row keeps ITS OWN as_of_date",
          by_anchor["AAPL"]["as_of_date"] == "2016-02-19", str(by_anchor))
    check("1g-googl. the GOOGL row keeps ITS OWN, DIFFERENT as_of_date",
          by_anchor["GOOGL"]["as_of_date"] == "2017-02-23", str(by_anchor))


def test_2_direction_mapping_reused_unchanged() -> None:
    check("2a. competitor maps to sector_competitor, reused from "
          "run_hyp05_peer_market_cap.py unchanged",
          DIRECTION_TO_RELATIONSHIP_TYPE["competitor"] == "sector_competitor")


def test_3_main_never_overwrites_out() -> None:
    import io
    from contextlib import redirect_stdout, redirect_stderr

    existing = TMP / "already_there.json"
    existing.write_text("{}", encoding="utf-8")
    missing_name_search = TMP / "does_not_exist.json"

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--name-search", str(missing_name_search),
                      "--out", str(existing)])
    check("3a. refuses with a non-zero exit when --out already exists",
          code != 0, str(code))
    check("3b. says why, on stderr, naming the overwrite -- not the "
          "missing name-search file", "already exists" in err.getvalue(),
          err.getvalue()[:200])
    check("3c. never reaches the resolved-candidates step",
          "resolved, tradeable candidates" not in out.getvalue(),
          out.getvalue()[:160])
    check("3d. the existing file is untouched",
          existing.read_text(encoding="utf-8") == "{}")


def test_4_main_refuses_on_missing_input() -> None:
    import io
    from contextlib import redirect_stdout, redirect_stderr

    out_path = TMP / "fresh_out.json"
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--name-search", str(TMP / "nope.json"),
                      "--out", str(out_path)])
    check("4a. refuses with a non-zero exit on a missing name-search file",
          code != 0, str(code))
    check("4b. the out path is untouched", not out_path.exists())


def test_5_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("5a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("5a. network blocked", True)


if __name__ == "__main__":
    test_1_resolved_candidates_joins_across_multiple_linkage_files()
    test_1g_same_counterparty_name_under_two_anchors_keeps_both_correctly()
    test_2_direction_mapping_reused_unchanged()
    test_3_main_never_overwrites_out()
    test_4_main_refuses_on_missing_input()
    test_5_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_PEER_MARKET_CAP TESTS PASSED")
    sys.exit(0)
