#!/usr/bin/env python3
"""run_hyp07_reverse_competitor_search.py tests -- offline, hermetic, no
network.

  DISCOVER_LEADS DEDUPES BY PEER CIK AND EXCLUDES THE ANCHOR'S OWN
  (test_1) -- keeping the EARLIEST-dated hit when the same peer surfaces
  from more than one phrase/variant. Same logic as the customer/supplier
  module (round 4), exercised here against competitor-phrase queries.

  VERIFY_LEAD APPLIES THE SAME classify_context REJECTIONS ROUNDS 1-3
  FOUND (test_2) -- these are generic governance-mention rejections, not
  concentration-specific, so they apply unchanged to competitor leads too.

  VERIFY_LEAD REQUIRES THE SENTENCE TO MATCH A REAL, CALIBRATED
  COMPETITOR_ANCHORS PATTERN (test_3) -- the one check this direction
  needs that the customer/supplier module's percent-figure check doesn't
  have an analog for.

  main() NEVER OVERWRITES A DATED ARTIFACT, ACROSS ALL THREE OUTPUTS
  (test_4). main() NEVER GOES LIVE WITHOUT THE FLAG (test_5).

  NO HARDCODED GATE-STATE VERDICT (test_6).

Repo testing convention (hand-rolled check(), run directly, no pytest).

Run directly: python test_hyp04_supply_chain_hedge_reverse_competitor_search.py
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
    run_hyp07_reverse_competitor_search as R,
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
    framework -- same pattern the customer/supplier module's own test
    file uses."""

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
        '"Intel Corporation" "principal competitors include"': [
            _hit(peer_cik, "SMALL RIVAL INC", "0000000099-15-000001",
                "doc1.htm", "2015-03-01"),
            _hit(anchor_cik, "INTEL CORP", "0000000042-15-000009",
                "doc9.htm", "2015-01-01"),   # the anchor's OWN filing
        ],
        '"Intel Corporation" "we compete with"': [
            _hit(peer_cik, "SMALL RIVAL INC", "0000000099-12-000002",
                "doc2.htm", "2012-01-01"),   # SAME peer, EARLIER date
        ],
        '"Intel Corporation" "primary competitors include"': [],
        '"Intel Corporation" "our competitors include"': [],
        '"Intel Corporation" "we compete directly with"': [],
    }
    client = _FakeClient(hits_by_query=hits_by_query, docs_by_key={},
                        cik_for_result=anchor_cik)
    leads = R.discover_leads(client, "INTC", ("Intel Corporation",))

    check("1a. exactly one lead survives (the anchor's own hit excluded)",
          len(leads) == 1, str(leads))
    check("1b. it is the peer, not the anchor",
          leads[0]["peer_cik"] == peer_cik, str(leads[0]))
    check("1c. the EARLIEST-dated hit is kept, not the first one seen",
          leads[0]["file_date"] == "2012-01-01", str(leads[0]))


def test_1b_self_match_backstop_fires_when_cik_for_cannot_resolve() -> None:
    # The real, verified gap: 7 of the 788-anchor scaled search's anchors
    # (AVB, EQR, GTLS, JHG, NSA, TMHC, WBS) have no entry at all in SEC's
    # own company_tickers.json map, so cik_for(anchor_ticker) returns None
    # and the CIK-based exclusion in discover_leads is vacuously disabled.
    # Simulated here by cik_for_result=None -- the anchor's OWN filing
    # (registrant name containing the exact searched name variant) must
    # still be excluded, via the name-based backstop.
    hits_by_query = {
        '"AvalonBay Communities, Inc." "we compete with"': [
            _hit("0000001000", "AVALONBAY COMMUNITIES, INC.",
                "0000001000-20-000001", "doc1.htm", "2020-01-01"),
        ],
        '"AvalonBay Communities, Inc." "principal competitors include"': [],
        '"AvalonBay Communities, Inc." "primary competitors include"': [],
        '"AvalonBay Communities, Inc." "our competitors include"': [],
        '"AvalonBay Communities, Inc." "we compete directly with"': [],
    }
    client = _FakeClient(hits_by_query=hits_by_query, docs_by_key={},
                        cik_for_result=None)
    leads = R.discover_leads(client, "AVB", ("AvalonBay Communities, Inc.",))
    check("1b. the anchor's own filing is excluded even when cik_for "
          "cannot resolve a CIK to exclude by",
          leads == [], str(leads))


def test_1c_self_match_backstop_never_excludes_a_genuine_different_peer() -> None:
    # Control: a genuinely different, differently-named peer surfacing
    # under the same unresolvable-CIK anchor must NOT be excluded -- the
    # backstop is a name-containment check, not a blanket "cik_for failed"
    # rejection.
    hits_by_query = {
        '"AvalonBay Communities, Inc." "we compete with"': [
            _hit("0000002000", "EQUITY RESIDENTIAL",
                "0000002000-20-000005", "doc5.htm", "2020-02-01"),
        ],
        '"AvalonBay Communities, Inc." "principal competitors include"': [],
        '"AvalonBay Communities, Inc." "primary competitors include"': [],
        '"AvalonBay Communities, Inc." "our competitors include"': [],
        '"AvalonBay Communities, Inc." "we compete directly with"': [],
    }
    client = _FakeClient(hits_by_query=hits_by_query, docs_by_key={},
                        cik_for_result=None)
    leads = R.discover_leads(client, "AVB", ("AvalonBay Communities, Inc.",))
    check("1c. a genuine, differently-named peer is never excluded by the "
          "name-based backstop",
          len(leads) == 1 and leads[0]["peer_cik"] == "0000002000",
          str(leads))


def test_1d_joint_filing_resolves_peer_name_at_the_SAME_index_as_peer_cik() -> None:
    # A jointly-filed document (e.g. a parent anchor + subsidiary
    # co-registrants) can carry MORE than one entry in ciks/display_names,
    # as PARALLEL arrays. A real bug (found by independent review, not
    # assumed) read peer_registrant_name from display_names[0]
    # unconditionally while peer_cik correctly scanned ciks for a
    # non-anchor entry at ANY index -- when the anchor was co-registrant
    # #0 and the genuine peer was co-registrant #1, the self-match check
    # then compared the ANCHOR's own name and wrongly dropped a real lead.
    anchor_cik = "0000000042"
    peer_cik = "0000000077"
    hit_joint = {
        "ciks": [anchor_cik, peer_cik],
        "display_names": ["INTEL CORP", "GENUINE RIVAL CORP"],
        "adsh": "0000000077-15-000003", "_id": "0000000077-15-000003:doc3.htm",
        "file_date": "2015-06-01",
    }
    hits_by_query = {
        '"Intel Corporation" "we compete with"': [hit_joint],
        '"Intel Corporation" "principal competitors include"': [],
        '"Intel Corporation" "primary competitors include"': [],
        '"Intel Corporation" "our competitors include"': [],
        '"Intel Corporation" "we compete directly with"': [],
    }
    client = _FakeClient(hits_by_query=hits_by_query, docs_by_key={},
                        cik_for_result=anchor_cik)
    leads = R.discover_leads(client, "INTC", ("Intel Corporation",))

    check("1d. the genuine peer at ciks[1] is NOT wrongly dropped by the "
          "self-match check", len(leads) == 1, str(leads))
    check("1d-detail. peer_cik resolves to the REAL peer, not the anchor",
          leads and leads[0]["peer_cik"] == peer_cik, str(leads))
    check("1d-detail. peer_registrant_name is read from the SAME index as "
          "peer_cik (the peer's own name), not display_names[0] (the "
          "anchor's own name)",
          leads and leads[0]["peer_registrant_name"] == "GENUINE RIVAL CORP",
          str(leads))


def test_2_verify_lead_applies_known_rejection_patterns() -> None:
    # The exact real Wolverine World Wide stock-index sentence
    # classify_context was built to catch (round 2) -- a generic
    # governance-mention rejection, reused unchanged here.
    text = ("COMPARISON OF 5-YEAR CUMULATIVE TOTAL RETURN "
           "Dow Jones U.S. Footwear Index NIKE, Inc. Wolverine World Wide")
    client = _FakeClient(
        hits_by_query={},
        docs_by_key={("0000000099", "0000000099-15-000001", "doc1.htm"): text})
    lead = {"anchor_ticker": "NKE", "matched_name_variant": "NIKE, Inc.",
           "matched_phrase": "we compete with", "peer_cik": "0000000099",
           "peer_registrant_name": "WOLVERINE WORLD WIDE INC",
           "accession": "0000000099-15-000001",
           "doc_id": "0000000099-15-000001:doc1.htm", "file_date": "2015-01-01"}
    out = R.verify_lead(client, lead)
    check("2a. a known stock-index co-membership false signal is rejected",
          out["filed_mention_confirmed"] is False
          and out.get("context_rejected_as_non_relationship_evidence") is True,
          str(out))


def test_3_verify_lead_requires_a_real_competitor_pattern_match() -> None:
    """The NEW check: the anchor's own sentence must match one of the
    three real, calibrated COMPETITOR_ANCHORS patterns. A bare name
    mention -- no competitor-language pattern anywhere near it -- must not
    be confirmed, even though the DOCUMENT-level query already matched a
    competitor phrase (which, in this synthetic case, sits in an unrelated
    part of the same document)."""
    text = ("Our history and our facilities. Intel Corporation is a "
           "well-known company. Separately, in an unrelated paragraph, "
           "we compete with several other firms in a different market "
           "entirely.")
    client = _FakeClient(
        hits_by_query={},
        docs_by_key={("0000000099", "0000000099-15-000001", "doc1.htm"): text})
    lead = {"anchor_ticker": "INTC", "matched_name_variant": "Intel Corporation",
           "matched_phrase": "we compete with", "peer_cik": "0000000099",
           "peer_registrant_name": "SOME RIVAL INC",
           "accession": "0000000099-15-000001",
           "doc_id": "0000000099-15-000001:doc1.htm", "file_date": "2015-01-01"}
    out = R.verify_lead(client, lead)
    check("3a. no competitor-pattern match in the NAME's own sentence -> "
          "not confirmed", out["filed_mention_confirmed"] is False, str(out))
    check("3b. reason names the actual gap, not a generic failure",
          "competitor_anchors" in out.get("reason", "").lower()
          or "pattern" in out.get("reason", "").lower(), str(out))

    # CONTROL: the same anchor name, now in a sentence that DOES match a
    # real COMPETITOR_ANCHORS pattern, confirms.
    text_ok = ("We compete with Intel Corporation and several other "
              "semiconductor firms in this market.")
    client_ok = _FakeClient(
        hits_by_query={},
        docs_by_key={("0000000099", "0000000099-15-000001", "doc1.htm"): text_ok})
    out_ok = R.verify_lead(client_ok, lead)
    check("3c. CONTROL -- a real competitor-pattern sentence DOES confirm",
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
        check("5e. anchor set is the same 27 round 4 used",
              "anchors: 27" in text, text[:200])


def test_6_no_hardcoded_gate_state_verdict() -> None:
    import re
    src = (Path(__file__).resolve().parent / "hyp04_supply_chain_hedge"
           / "run_hyp07_reverse_competitor_search.py").read_text(
               encoding="utf-8")
    verdict = re.compile(
        r"(display )?[Gg]ate (is|stays) CLOSED|Gate CLOSED"
        r"|CLOSED with (C4 MET and )?four denials|CLOSED, C4 MET, four denials")
    hits = [ln for ln in src.splitlines()
            if not ln.strip().startswith("#") and verdict.search(ln)]
    check("6a. no hardcoded gate-state verdict in this module", hits == [],
          str(hits[:2]))


def test_7_looks_like_competitor_sentence_is_pure() -> None:
    check("7a. 'principal competitors include' matches",
          R._looks_like_competitor_sentence(
              "Our principal competitors include Intel and AMD."))
    check("7b. 'we compete with' matches",
          R._looks_like_competitor_sentence(
              "We compete with several other firms."))
    check("7c. a bare name mention with no competitor language does not",
          not R._looks_like_competitor_sentence(
              "Intel Corporation is a well-known company."))
    check("7d. case-insensitive",
          R._looks_like_competitor_sentence(
              "WE COMPETE DIRECTLY WITH several other firms."))


def test_8_offline() -> None:
    try:
        socket.socket().connect(("example.invalid", 80))
        check("8a. network blocked", False, "connect() did not raise")
    except NetworkBlocked:
        check("8a. network blocked", True)


if __name__ == "__main__":
    test_1_discover_leads_dedupes_and_excludes_the_anchor()
    test_1b_self_match_backstop_fires_when_cik_for_cannot_resolve()
    test_1c_self_match_backstop_never_excludes_a_genuine_different_peer()
    test_1d_joint_filing_resolves_peer_name_at_the_SAME_index_as_peer_cik()
    test_2_verify_lead_applies_known_rejection_patterns()
    test_3_verify_lead_requires_a_real_competitor_pattern_match()
    test_4_main_never_overwrites_any_of_its_three_outputs()
    test_5_dry_run_never_goes_live()
    test_6_no_hardcoded_gate_state_verdict()
    test_7_looks_like_competitor_sentence_is_pure()
    test_8_offline()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP07_REVERSE_COMPETITOR_SEARCH TESTS PASSED")
    sys.exit(0)
