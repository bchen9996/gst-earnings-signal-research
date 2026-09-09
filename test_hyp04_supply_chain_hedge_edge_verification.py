#!/usr/bin/env python3
"""HYP-04 edge verification and the ratification worksheet.

Pins two things:

  1. The verification artifact recomputes from the committed walks, emits no
     `review_status`, and carries the caveats that stop two of its own numbers
     from misleading a reviewer.
  2. The worksheet is INERT as shipped and VALID once filled. That is the
     promise attached to a document someone is asked to sign.

Repo testing convention (hand-rolled check(), run directly, no pytest).
Offline.

Run directly: python test_hyp04_supply_chain_hedge_edge_verification.py
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

import csv  # noqa: E402
import fnmatch  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import make_edge_verification as V  # noqa: E402
from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    REVIEW_STATUSES,
    load_curated_linkage,
)

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"
WORKSHEET = LSE / "HYP04_LINKAGE_RATIFICATION_WORKSHEET_v1.3.csv"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def _art() -> dict:
    return json.loads(V.OUT_JSON.read_text(encoding="utf-8"))


def test_1_the_artifact_recomputes() -> None:
    check("1a. the verification artifact is on disk", V.OUT_JSON.is_file())
    check("1b. so is the rendered document", V.OUT_MD.is_file())
    if not V.OUT_JSON.is_file():
        return
    fresh = V.build()
    committed = _art()
    check("1c. every published number recomputes from the committed walks",
          fresh == committed,
          f"differing keys: "
          f"{sorted(k for k in committed if committed.get(k) != fresh.get(k))}")
    check("1d. it used no network", committed["uses_network"] is False)


def test_2_it_emits_no_verdict() -> None:
    """The document is evidence for a decision, not the decision."""
    art = _art()
    body = json.dumps(art)
    for e in art["edges"]:
        check(f"2a. {e['edge']} carries no recommended review_status",
              "recommended_review_status" not in e
              and "verdict" not in e)
    check("2b. the artifact says so itself",
          "no review_status" in art["what_this_is_not"])
    md = V.OUT_MD.read_text(encoding="utf-8")
    check("2c. the document says so too",
          "contains no `review_status` and recommends nothing" in md)
    check("2d. and it does not rank edges by whether the sample needs them",
          "worth nothing" in md)


def test_3_the_walks_were_complete() -> None:
    """A partial walk cannot establish an earliest disclosing filing."""
    w = _art()["walk_completeness"]
    check("3a. every contributing anchor's walk is complete",
          w["all_contributing_anchors_complete"] is True,
          str(w["incomplete_anchors"]))


def test_4_the_two_misleading_numbers_are_caveated() -> None:
    """Both were live traps; the fix has to stay."""
    art = _art()
    by = {e["edge"]: e for e in art["edges"]}

    bb = by.get("JBL->BB")
    check("4a. a single-filing edge is flagged as such",
          bb and bb["single_filing_edge"] is True)
    check("4b. and its 100% is marked arithmetic, not evidence",
          bb and bb["after_count_is_tautological"] is True)

    mck = by.get("MCK->CVS")
    later = [c["counterparty"]
             for c in (mck or {}).get(
                 "later_named_counterparties_on_this_anchor", [])]
    check("4c. MCK's later CVS names are surfaced, so its 83% cannot be read "
          "as a lapse", any("CVS" in n for n in later), str(later))
    check("4d. but the alias chain is NOT asserted",
          "not auto-link" in art["alias_chains_not_asserted"].lower()
          or "not asserted" in art["alias_chains_not_asserted"].lower()
          or "judgement" in art["alias_chains_not_asserted"])

    md = V.OUT_MD.read_text(encoding="utf-8")
    check("4e. both markers are explained in the document",
          "arithmetic, not evidence" in md and "reads here as if it stopped" in md)
    check("4f. the document refuses to propose a currency rule",
          "not proposed here" in md)


def test_5_names_are_matched_exactly() -> None:
    art = _art()
    check("5a. the matching mode is exact string equality",
          all(e["match_mode"] == "exact_string_equality" for e in art["edges"]))
    unmatched = [e["edge"] for e in art["edges"] if not e["matched_in_walk"]]
    check("5b. every edge's cited counterparty was found in the walk",
          not unmatched, str(unmatched))
    check("5c. and every as_of agrees with the walk's earliest filing",
          all(e["as_of_agrees_with_walk"] for e in art["edges"]),
          str([e["edge"] for e in art["edges"]
               if not e["as_of_agrees_with_walk"]]))


def test_6_the_worksheet_is_inert_as_shipped() -> None:
    check("6a. the worksheet is on disk", WORKSHEET.is_file())
    if not WORKSHEET.is_file():
        return

    # It must NOT be picked up as a linkage map by ANY consumer. Two globs
    # exist and they differ, which is how the first attempt went wrong:
    # `HYP04_Linkage_Map_WORKSHEET_v1.3.csv` cleared the panel's narrower glob
    # but matched the curated-linkage suite's broader one, which requires every
    # map-like file to load clean -- and this one is deliberately unloadable.
    for pat in ("HYP04_Linkage_Map_v*.csv",     # make_event_panel._inputs
                "HYP04_Linkage_Map*.csv"):      # test_..._curated_linkage
        check(f"6b. its name does not match {pat}",
              not fnmatch.fnmatch(WORKSHEET.name, pat), WORKSHEET.name)

    res = load_curated_linkage(WORKSHEET)
    check("6c. it fails the map validator, so nothing can resolve from it",
          res.ok is False and len(res.edges) == 0,
          f"ok={res.ok} edges={len(res.edges)}")

    rows = list(csv.DictReader(WORKSHEET.open(newline="", encoding="utf-8")))
    for f in ("review_status", "curated_by", "curated_date"):
        check(f"6d. {f} is blank on every row",
              all(not (r.get(f) or "").strip() for r in rows))
    check("6e. nothing else was blanked -- the evidence rows survive",
          all((r.get("source_citation") or "").strip() for r in rows))


def test_7_the_worksheet_is_valid_once_filled() -> None:
    """The promise attached to a document someone signs."""
    rows = list(csv.DictReader(WORKSHEET.open(newline="", encoding="utf-8")))
    for r in rows:
        r["review_status"] = "reviewed"
        r["curated_by"] = "test-operator"
        r["curated_date"] = "2026-09-08"
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "HYP04_Linkage_Map_v1.3.csv"
        with f.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        res = load_curated_linkage(f)
        check("7a. the filled worksheet loads clean",
              res.ok is True and res.rows_rejected == 0,
              f"ok={res.ok} rejected={res.rows_rejected}")
        check("7b. every row becomes a usable edge",
              len(res.edges) == len(rows), f"{len(res.edges)}/{len(rows)}")
        check("7c. 'reviewed' is in the map's own vocabulary",
              "reviewed" in REVIEW_STATUSES)
        check("7d. and the renamed file WOULD be picked up as the map",
              fnmatch.fnmatch(f.name, "HYP04_Linkage_Map_v*.csv"))


def test_8_nothing_was_ratified() -> None:
    check("8a. no v1.3 linkage map exists",
          not (LSE / "HYP04_Linkage_Map_v1.3.csv").exists())
    live = load_curated_linkage(
        sorted(LSE.glob("HYP04_Linkage_Map_v1.*.csv"))[-1])
    check("8b. the map in force still carries no ratified edge",
          all(e.review_status != "reviewed" for e in live.edges),
          str(sorted({e.review_status for e in live.edges})))


if __name__ == "__main__":
    test_1_the_artifact_recomputes()
    test_2_it_emits_no_verdict()
    test_3_the_walks_were_complete()
    test_4_the_two_misleading_numbers_are_caveated()
    test_5_names_are_matched_exactly()
    test_6_the_worksheet_is_inert_as_shipped()
    test_7_the_worksheet_is_valid_once_filled()
    test_8_nothing_was_ratified()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 EDGE-VERIFICATION TESTS PASSED")
    sys.exit(0)
