#!/usr/bin/env python3
"""run_hyp05_reverse_concentration_search.py tests -- offline, hermetic,
no network.

  DISCOVER_LEADS DEDUPES BY PEER CIK AND EXCLUDES THE ANCHOR'S OWN
  (test_1) -- keeping the EARLIEST-dated hit when the same peer surfaces
  from more than one phrase/variant.

  VERIFY_LEAD APPLIES THE SAME classify_context REJECTIONS ROUNDS 1-3
  FOUND (test_2) -- reusing the exact real sentences that motivated each
  pattern, so a regression here means the SAME defect class returned.

  VERIFY_LEAD REJECTS A SENTENCE WITH NO PERCENT FIGURE (test_3) -- the
  one NEW check this direction needs that the old one didn't (see module
  docstring, "VERIFICATION"), on a synthetic name-only mention.

  main() NEVER OVERWRITES A DATED ARTIFACT, ACROSS ALL THREE OUTPUTS
  (test_4). main() NEVER GOES LIVE WITHOUT THE FLAG (test_5).

  NO HARDCODED GATE-STATE VERDICT (test_6).

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_reverse_concentration_search.py
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

import io  # noqa: E402
import tempfile  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import (  # noqa: E402
    run_hyp05_reverse_concentration_search as R,
)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


class _FakeClient:
    """Enough of AgreementSearchClient's surface for discover_leads/
    verify_lead: cik_for, search_unscoped, document. Scripted, not a mock
    framework -- this module has no other test using one."""

    def __init__(self, *, hits_by_query: dict, docs_by_key: dict,
                cik_for_result="0000009999"):
        self.hits_by_query = hits_by_query
        self.docs_by_key = docs_by_key
        self._cik_for_result = cik_for_result
        self.requests_made = 0

    def cik_for(self, ticker):
        return self._cik_for_result

    def search_unscoped(self, query, forms="10-K"):
        self.requests_made += 1
        return self.hits_by_query.get(query, [])

    def document(self, cik, accession, doc):
        self.requests_made += 1
        key = (cik, accession, doc)
        if key not in self.docs_by_key:
            raise RuntimeError(f"no fake document for {key}")
        return self.docs_by_key[key]


def _hit(cik: str, name: str, accession: str, doc: str, file_date: str) -> dict:
    return {"ciks": [cik], "display_names": [name], "adsh": accession,
           "_id": f"{accession}:{doc}", "file_date": file_date}


def test_1_discover_leads_dedupes_and_excludes_the_anchor() -> None:
    anchor_cik = "0000000042"
    peer_cik = "0000000099"
    hits_by_query = {
        '"Apple Inc." "of our net sales"': [
            _hit(peer_cik, "SMALL SUPPLIER INC", "0000000099-15-000001",
                "doc1.htm", "2015-03-01"),
            _hit(anchor_cik, "APPLE INC", "0000000042-15-000009",
                "doc9.htm", "2015-01-01"),   # the anchor's OWN filing
        ],
        '"Apple Inc." "of our net revenue"': [
            _hit(peer_cik, "SMALL SUPPLIER INC", "0000000099-12-000002",
                "doc2.htm", "2012-01-01"),   # SAME peer, EARLIER date
        ],
        '"Apple Inc." "of net sales"': [],
        '"Apple Inc." "of total revenue"': [],
    }
    client = _FakeClient(hits_by_query=hits_by_query, docs_by_key={},
                        cik_for_result=anchor_cik)
    leads = R.discover_leads(client, "AAPL", ("Apple Inc.",))

    check("1a. exactly one lead survives (the anchor's own hit excluded)",
          len(leads) == 1, str(leads))
    check("1b. it is the peer, not the anchor",
          leads[0]["peer_cik"] == peer_cik, str(leads[0]))
    check("1c. the EARLIEST-dated hit is kept, not the first one seen",
          leads[0]["file_date"] == "2012-01-01", str(leads[0]))


def test_2_verify_lead_applies_known_rejection_patterns() -> None:
    # The exact real Wolverine World Wide stock-index sentence
    # classify_context was built to catch (round 2).
    text = ("COMPARISON OF 5-YEAR CUMULATIVE TOTAL RETURN "
           "Dow Jones U.S. Footwear Index NIKE, Inc. Wolverine World Wide")
    client = _FakeClient(
        hits_by_query={},
        docs_by_key={("0000000099", "0000000099-15-000001", "doc1.htm"): text})
    lead = {"anchor_ticker": "NKE", "matched_name_variant": "NIKE, Inc.",
           "matched_phrase": "of net sales", "peer_cik": "0000000099",
           "peer_registrant_name": "WOLVERINE WORLD WIDE INC",
           "accession": "0000000099-15-000001",
           "doc_id": "0000000099-15-000001:doc1.htm", "file_date": "2015-01-01"}
    out = R.verify_lead(client, lead)
    check("2a. a known stock-index co-membership false signal is rejected",
          out["filed_mention_confirmed"] is False
          and out.get("context_rejected_as_non_relationship_evidence") is True,
          str(out))


def test_3_verify_lead_requires_a_percent_figure_in_the_same_sentence() -> None:
    """The NEW check: the anchor's own sentence, not just the document,
    must carry a percent-style figure. A bare name mention -- no percent
    figure anywhere near it -- must not be confirmed, even though the
    DOCUMENT-level query already matched a concentration phrase (which, in
    this synthetic case, sits in an unrelated part of the same document)."""
    text = ("Our history and our facilities. NVIDIA Corporation is a "
           "well-known company. Separately, our largest customer "
           "accounted for 41% of our net sales in a different paragraph "
           "about a different customer entirely.")
    client = _FakeClient(
        hits_by_query={},
        docs_by_key={("0000000099", "0000000099-15-000001", "doc1.htm"): text})
    lead = {"anchor_ticker": "NVDA", "matched_name_variant": "NVIDIA Corporation",
           "matched_phrase": "of our net sales", "peer_cik": "0000000099",
           "peer_registrant_name": "SOME SUPPLIER INC",
           "accession": "0000000099-15-000001",
           "doc_id": "0000000099-15-000001:doc1.htm", "file_date": "2015-01-01"}
    out = R.verify_lead(client, lead)
    check("3a. no percent figure in the NAME's own sentence -> not confirmed",
          out["filed_mention_confirmed"] is False, str(out))
    check("3b. reason names the actual gap, not a generic failure",
          "percent" in out.get("reason", "").lower(), str(out))

    # CONTROL: the same figure, now in the name's own sentence, confirms.
    text_ok = ("NVIDIA Corporation accounted for approximately 41% of our "
              "net sales in fiscal 2015.")
    client_ok = _FakeClient(
        hits_by_query={},
        docs_by_key={("0000000099", "0000000099-15-000001", "doc1.htm"): text_ok})
    out_ok = R.verify_lead(client_ok, lead)
    check("3c. CONTROL -- a real concentration sentence DOES confirm",
          out_ok["filed_mention_confirmed"] is True, str(out_ok))


def test_4_main_never_overwrites_any_of_its_three_outputs() -> None:
    with tempfile.TemporaryDirectory() as td:
        paths = {
            "--out-name-search": Path(td) / "ns.json",
            "--out-linkage": Path(td) / "lk.json",
            "--out-raw-hits": Path(td) / "raw.json",
        }
        for existing_flag, existing_path in paths.items():
            existing_path.write_text("{}", encoding="utf-8")
            args = []
            for flag, path in paths.items():
                args += [flag, str(path if path != existing_path else
                                   existing_path)]
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out):
                import contextlib
                with contextlib.redirect_stderr(err):
                    code = R.main(args)
            check(f"4a. refuses when {existing_flag} already exists",
                  code != 0, f"code={code}")
            check(f"4b. says why, on stderr ({existing_flag})",
                  "already exists" in err.getvalue(), err.getvalue()[:160])
            existing_path.unlink()


def test_5_dry_run_never_goes_live() -> None:
    with tempfile.TemporaryDirectory() as td:
        ns = Path(td) / "ns.json"
        lk = Path(td) / "lk.json"
        raw = Path(td) / "raw.json"
        out = io.StringIO()
        with redirect_stdout(out):
            code = R.main(["--out-name-search", str(ns),
                          "--out-linkage", str(lk),
                          "--out-raw-hits", str(raw)])
        text = out.getvalue()
        check("5a. exits 0", code == 0, str(code))
        check("5b. says DRY RUN and names the flag to proceed",
              "DRY RUN" in text and "--yes-run-live" in text)
        check("5c. nothing was written",
              not ns.exists() and not lk.exists() and not raw.exists())
        check("5d. reports the planned query count",
              "planned unscoped searches" in text, text[:300])


def test_6_no_hardcoded_gate_state_verdict() -> None:
    import re
    src = (Path(__file__).resolve().parent / "hyp04_supply_chain_hedge"
           / "run_hyp05_reverse_concentration_search.py").read_text(
               encoding="utf-8")
    verdict = re.compile(
        r"(display )?[Gg]ate (is|stays) CLOSED|Gate CLOSED"
        r"|CLOSED with (C4 MET and )?four denials|CLOSED, C4 MET, four denials")
    hits = [ln for ln in src.splitlines()
            if not ln.strip().startswith("#") and verdict.search(ln)]
    check("6a. no hardcoded gate-state verdict in this module", hits == [],
          str(hits[:2]))


def test_7_looks_like_concentration_sentence_is_pure() -> None:
    check("7a. a plain percent sign counts",
          R._looks_like_concentration_sentence("41% of our net sales"))
    check("7b. the word 'percent' counts too",
          R._looks_like_concentration_sentence(
              "approximately 41 percent of our net sales"))
    check("7c. no figure at all does not count",
          not R._looks_like_concentration_sentence(
              "NVIDIA Corporation is a well-known company"))


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_discover_leads_dedupes_and_excludes_the_anchor()
    test_2_verify_lead_applies_known_rejection_patterns()
    test_3_verify_lead_requires_a_percent_figure_in_the_same_sentence()
    test_4_main_never_overwrites_any_of_its_three_outputs()
    test_5_dry_run_never_goes_live()
    test_6_no_hardcoded_gate_state_verdict()
    test_7_looks_like_concentration_sentence_is_pure()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP05_REVERSE_CONCENTRATION_SEARCH TESTS PASSED")
    sys.exit(0)
