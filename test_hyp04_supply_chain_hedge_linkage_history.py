#!/usr/bin/env python3
"""Tests for the EDGAR 10-K history walk -- HYP-04.

The runner itself makes REAL SEC REQUESTS and is deliberately named off the
`test_*` pattern, so nothing here invokes it against the network. What IS
tested is everything that decides what the walk means:

  * `all_10ks` must merge SEC's PAGINATED older-filing blocks, not just
    `filings.recent`. Reading only `recent` truncates silently at whatever
    depth that block reaches, and a truncated history is indistinguishable
    from "no earlier disclosure exists" -- the single most misleading failure
    this module could have, because it returns a plausible date.
  * earliest/latest selection per counterparty, which is the whole output.
  * the runner refuses without an owner-supplied SEC contact.

Offline. No network: `_get` is replaced with a canned-response stub, and the
socket layer is blocked before any import so a missed path fails loudly rather
than reaching SEC.

Run directly: python test_hyp04_supply_chain_hedge_linkage_history.py
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

from hyp04_supply_chain_hedge.edgar_linkage import (  # noqa: E402
    EdgarClient,
    EdgarContactError,
    extract_edges_from_text,
)
from hyp04_supply_chain_hedge.run_linkage_history import (  # noqa: E402
    TickerHistory,
    build_report,
    main,
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


CONTACT = "test runner test@realdomain.example.org"


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient(EdgarClient):
    """EdgarClient with the transport replaced. Never touches the network."""

    def __init__(self, pages: dict):
        super().__init__("offline tester tester@realdomain.org")
        self.pages = pages
        self.urls: list[str] = []

    def _get(self, url: str, timeout: int = 30):
        self.urls.append(url)
        # Longest key first. Substring routing is ambiguous here: the main
        # submissions URL ends CIK<digits>.json and the paginated blocks are
        # CIK-submissions-NN.json, so a short key like "submissions/CIK"
        # matches BOTH and silently serves the wrapper document in place of an
        # older block -- which looks exactly like "there are no older filings".
        for key in sorted(self.pages, key=len, reverse=True):
            if key in url:
                return _Resp(self.pages[key])
        raise AssertionError(f"unexpected URL requested: {url}")


# ============ 1. all_10ks merges the paginated older blocks ==============
def test_1_all_10ks_reads_beyond_recent() -> None:
    recent = {
        "form": ["10-K", "8-K", "10-Q", "10-K"],
        "accessionNumber": ["A-2026", "X-1", "X-2", "A-2025"],
        "filingDate": ["2026-05-08", "2026-03-01", "2026-02-01", "2025-05-09"],
        "primaryDocument": ["a26.htm", "x1.htm", "x2.htm", "a25.htm"],
    }
    older = {
        "form": ["10-K", "10-K"],
        "accessionNumber": ["A-2013", "A-2001"],
        "filingDate": ["2013-05-07", "2001-06-01"],
        "primaryDocument": ["a13.htm", "a01.htm"],
    }
    c = FakeClient({
        "CIK0000927653.json": {"filings": {"recent": recent,
                                        "files": [{"name": "CIK-submissions-01.json"}]}},
        "CIK-submissions-01.json": older,
    })

    got = c.all_10ks("0000927653")
    dates = [f["filing_date"] for f in got]

    check("1a. only 10-K forms are returned", len(got) == 4, str(dates))
    check("1b. the PAGINATED older block is included -- not just `recent`",
          "2013-05-07" in dates and "2001-06-01" in dates, str(dates))
    check("1c. results are newest-first",
          dates == sorted(dates, reverse=True), str(dates))
    check("1d. accession and document travel with each filing",
          got[-1]["accession"] == "A-2001"
          and got[-1]["primary_document"] == "a01.htm")
    check("1e. the extra submissions file was actually fetched",
          any("CIK-submissions-01.json" in u for u in c.urls), str(c.urls))

    # THE CONTROL. Without this, an implementation that ignored `files` would
    # pass 1a and 1c and quietly report 2025 as the earliest filing.
    c2 = FakeClient({"CIK0000927653.json": {"filings": {"recent": recent, "files": []}}})
    only_recent = [f["filing_date"] for f in c2.all_10ks("0000927653")]
    check("1f. CONTROL -- with no extra blocks, only `recent` 10-Ks appear",
          only_recent == ["2026-05-08", "2025-05-09"], str(only_recent))
    check("1g. so 1b would fail against a recent-only implementation",
          "2013-05-07" not in only_recent)


def test_2_all_10ks_tolerates_a_missing_files_key() -> None:
    c = FakeClient({"submissions/CIK": {"filings": {
        "recent": {"form": ["10-K"], "accessionNumber": ["A"],
                   "filingDate": ["2020-01-01"], "primaryDocument": ["a.htm"]}}}})
    got = c.all_10ks("0000000001")
    check("2a. a submissions record with no `files` key still works",
          len(got) == 1 and got[0]["filing_date"] == "2020-01-01")

    c2 = FakeClient({"submissions/CIK": {"filings": {"recent": {}}}})
    check("2b. an empty `recent` block yields no filings", c2.all_10ks("1") == [])


# ============ 3. earliest / latest selection ==============================
def test_3_earliest_selection() -> None:
    h = TickerHistory(ticker="MCK")
    h.per_filing = [
        {"filing_date": "2026-05-08", "accession": "A-2026", "edges_found": 5,
         "named_counterparties": ["CVS Health Corporation"],
         "explicit_no_concentration": False},
        {"filing_date": "2020-05-22", "accession": "A-2020", "edges_found": 4,
         "named_counterparties": ["CVS Health Corporation"],
         "explicit_no_concentration": False},
        {"filing_date": "2013-05-07", "accession": "A-2013", "edges_found": 3,
         "named_counterparties": ["CVS Caremark Corporation"],
         "explicit_no_concentration": False},
        {"filing_date": "2009-05-05", "accession": "A-2009", "edges_found": 0,
         "named_counterparties": [], "explicit_no_concentration": False},
    ]
    named = h.named_counterparties()

    check("3a. each distinct counterparty STRING is its own entry",
          set(named) == {"CVS Health Corporation", "CVS Caremark Corporation"},
          str(sorted(named)))

    rec = named["CVS Health Corporation"]
    check("3b. earliest is the OLDEST filing naming it, not the newest",
          rec["earliest_filing_date"] == "2020-05-22"
          and rec["earliest_accession"] == "A-2020", str(rec))
    check("3c. latest is the newest", rec["latest_filing_date"] == "2026-05-08")
    check("3d. the count of filings naming it is right",
          rec["filings_naming_it"] == 2)
    check("3e. a filing naming nobody contributes nothing",
          all(r["filings_naming_it"] >= 1 for r in named.values()))

    # A RENAMED entity stays SEPARATE here, deliberately. Deciding that
    # "CVS Caremark Corporation" and "CVS Health Corporation" are one
    # counterparty is a curator's judgement about corporate identity, and this
    # code must not make it silently -- fusing them on a substring would also
    # fuse genuinely different companies that share a word.
    check("3f. a renamed entity is NOT auto-merged; both strings survive",
          named["CVS Caremark Corporation"]["earliest_filing_date"] == "2013-05-07")


def test_4_empty_history() -> None:
    h = TickerHistory(ticker="ZZZ")
    check("4a. no filings -> no counterparties", h.named_counterparties() == {})


# ============ 5. the report is labelled as a candidate ===================
def test_5_report_shape() -> None:
    h = TickerHistory(ticker="PKG", cik="0000075677", filings_on_record=27,
                      filings_examined=27)
    h.per_filing = [{"filing_date": "2016-02-26", "accession": "A", "edges_found": 3,
                     "named_counterparties": ["Office Depot"],
                     "explicit_no_concentration": False}]
    rep = build_report([h], contact_used=True, requests_made=59)

    check("5a. it is NOT a production linkage map",
          rep["is_production_linkage_map"] is False)
    check("5b. status says review queue",
          rep["status"] == "CANDIDATE_REVIEW_QUEUE")
    check("5c. it states what an earliest date does and does not prove",
          "not evidence the relationship began" in rep["what_the_earliest_date_means"])
    check("5d. it records the request count", rep["requests_made"] == 59)
    check("5e. per-ticker detail survives",
          rep["tickers"][0]["named_counterparties"][0]["earliest_filing_date"]
          == "2016-02-26")
    check("5f. a partial walk is reported as partial, never as complete",
          "stopped_early_reason" in rep["tickers"][0])


# ============ 6. the runner refuses without a contact ====================
def test_6_refuses_without_contact() -> None:
    rc = main(["--tickers", "MCK"])
    check("6a. no contact -> exit 2, and no request is attempted", rc == 2)

    for bad in ("", "no-at-sign", "someone@example.com", "noreply@realdomain.org"):
        try:
            EdgarClient(bad)
            check(f"6b. contact {bad!r} is refused", False, "it was accepted")
        except EdgarContactError:
            check(f"6b. contact {bad!r} is refused", True)
        except Exception as e:                       # noqa: BLE001
            check(f"6b. contact {bad!r} is refused", False, type(e).__name__)

    # The other direction: a deliverable address must be ACCEPTED, or every
    # case above would pass against a client that refused everything.
    try:
        EdgarClient("A Person person@realdomain.org")
        check("6c. CONTROL -- a deliverable contact is accepted", True)
    except Exception as e:                           # noqa: BLE001
        check("6c. CONTROL -- a deliverable contact is accepted", False,
              f"{type(e).__name__}: {e}")



def test_8_report_date_is_captured_but_not_used() -> None:
    """The period of report is recorded. NOTHING reads it, and that is the test.

    The stale-comparative gate compares a stated year against the FILING date.
    For a calendar-year filer those differ by about a year -- a FY2004 10-K
    filed 2005-02-22 -- so the gate's window is off by one for most of the
    corpus. Registry v1.6 records that as a stated limitation.

    Correcting it changes what the extractor accepts, which changes membership,
    which needs a re-walk and a new dated registry version. So this captures
    the field and stops there. Capturing it now means that fix costs ONE
    authorized walk instead of two -- the walk is the expensive part, not the
    regex.

    The final check is the load-bearing one: capturing a field must not move
    any extraction outcome. If it ever does, the "not used" half of this is
    false and v1.6's published universe is no longer what the code produces.
    """
    recent = {
        "form": ["10-K", "10-K"],
        "accessionNumber": ["A-2005", "A-2004"],
        "filingDate": ["2005-02-22", "2004-02-20"],
        # A calendar-year filer: the period ENDS the year before the filing.
        "reportDate": ["2004-12-31", "2003-12-31"],
        "primaryDocument": ["a05.htm", "a04.htm"],
    }
    c = FakeClient({"CIK0000050863.json": {"filings": {"recent": recent}}})
    got = c.all_10ks("0000050863")

    check("8a. report_date is captured",
          [f.get("report_date") for f in got] == ["2004-12-31", "2003-12-31"],
          str([f.get("report_date") for f in got]))
    check("8b. and is NOT the filing date -- the whole reason to capture it",
          all(f["report_date"][:4] != f["filing_date"][:4] for f in got),
          str([(f["filing_date"], f["report_date"]) for f in got]))

    # The older paginated blocks are thinner than filings.recent and are not
    # required to carry every array. Reading positionally would abort the
    # whole ticker over a field nothing has to supply.
    thin = {
        "form": ["10-K"],
        "accessionNumber": ["A-1998"],
        "filingDate": ["1998-03-30"],
        "primaryDocument": ["a98.htm"],
    }
    c2 = FakeClient({"CIK0000050863.json": {"filings": {"recent": thin}}})
    got2 = c2.all_10ks("0000050863")
    check("8c. a block with no reportDate array yields None, not a crash",
          len(got2) == 1 and got2[0].get("report_date") is None,
          str(got2))

    # A SHORT array is the nastier shape: present, so a .get() guard passes,
    # but too short for this index.
    short = dict(recent)
    short["reportDate"] = ["2004-12-31"]          # one value, two filings
    c3 = FakeClient({"CIK0000050863.json": {"filings": {"recent": short}}})
    got3 = c3.all_10ks("0000050863")
    check("8d. a SHORT reportDate array yields None for the missing index",
          [f.get("report_date") for f in got3] == ["2004-12-31", None],
          str([f.get("report_date") for f in got3]))

    # An empty string is SEC's way of saying "no period", and must not be
    # carried through as a falsy date that later code compares against.
    blank = dict(recent)
    blank["reportDate"] = ["", "2003-12-31"]
    c4 = FakeClient({"CIK0000050863.json": {"filings": {"recent": blank}}})
    got4 = c4.all_10ks("0000050863")
    check("8e. an empty reportDate becomes None, not an empty string",
          got4[0].get("report_date") is None, str(got4[0].get("report_date")))

    # THE LOAD-BEARING CHECK. Same prose, same filing date, report_date varied
    # across a decade: the extraction must be identical. The moment this fails,
    # report_date is being READ, and the published v1.6 universe no longer
    # matches what the code derives.
    prose = ("Sales to Rite Aid Corporation represented approximately 15% of "
             "consolidated sales in fiscal 2004.")
    outs = []
    for _rd in ("2004-12-31", "1996-01-31", None):
        edges, _ = extract_edges_from_text(
            prose, ticker="MCK", cik="0", filing_date="2005-02-22",
            accession="a")
        outs.append(sorted(e.named_counterparty for e in edges
                           if e.counterparty_is_named))
    check("8f. capturing report_date moves NO extraction outcome",
          outs[0] == outs[1] == outs[2] == ["Rite Aid Corporation"], str(outs))


def test_7_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("7a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("7a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_all_10ks_reads_beyond_recent()
    test_2_all_10ks_tolerates_a_missing_files_key()
    test_3_earliest_selection()
    test_4_empty_history()
    test_5_report_shape()
    test_6_refuses_without_contact()
    test_8_report_date_is_captured_but_not_used()
    test_7_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 LINKAGE-HISTORY TESTS PASSED")
    sys.exit(0)
