#!/usr/bin/env python3
"""HYP-04 linkage-draft tests. FULLY OFFLINE -- sockets blocked below.

One test carries this suite: test_2. The draft file uses the CURATED schema on
purpose, so the owner can complete a row and paste it into the map -- which
means the loader will accept its HEADER. The only thing standing between a
machine-prepared candidate and a production edge is that five required fields
are blank.

So test_2 asserts that against the REAL generated file, through the REAL
loader, all the way to `uses_placeholder_linkage` staying True. If a future
change ever pre-fills one of those fields, this fails loudly rather than
letting an uncurated map load.

Run directly: python test_hyp04_supply_chain_hedge_linkage_draft.py
"""
from __future__ import annotations

import csv
import io
import socket
import sys
from pathlib import Path

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


def _no_net(*a, **k):                                    # pragma: no cover
    raise AssertionError("this suite must make no network call")


socket.socket.connect = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    EXPECTED_HEADERS,
    REQUIRED_FIELDS,
    RELATIONSHIP_TYPES,
    SOURCE_TYPES,
    AS_OF_DATE_BASES,
    load_curated_linkage,
)
from hyp04_supply_chain_hedge.linkage_resolution import (  # noqa: E402
    resolve_from_curated_map,
)
from hyp04_supply_chain_hedge.make_linkage_draft import (  # noqa: E402
    AS_OF_BASIS,
    DIRECTION_TO_RELATIONSHIP,
    OWNER_FIELDS,
    SOURCE_TYPE,
)

LSE = Path("Live Signal Engine")
DRAFT = LSE / "HYP04_LINKAGE_ROWS_DRAFT_2026-08-31.csv"
CURATED_MAP = LSE / "HYP04_Linkage_Map_v1.0.csv"


def _rows(p: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.open(p, encoding="utf-8", newline="")))


def test_1_the_owner_fields_are_all_required() -> None:
    print("\n--- 1: the blanks are load-bearing, not cosmetic ---")
    missing = [f for f in OWNER_FIELDS if f not in REQUIRED_FIELDS]
    check("1a. every owner field is a REQUIRED field",
          not missing, f"not required: {missing}")
    check("1b. there are five of them", len(OWNER_FIELDS) == 5,
          str(OWNER_FIELDS))
    # If any owner field stopped being required, a blank draft row would load.
    check("1c. and none is in the optional set",
          all(f in REQUIRED_FIELDS for f in OWNER_FIELDS))
    check("1d. the module's declared source_type is in the vocabulary",
          SOURCE_TYPE in SOURCE_TYPES, SOURCE_TYPE)
    check("1e. its as_of basis is too",
          AS_OF_BASIS in AS_OF_DATE_BASES, AS_OF_BASIS)
    check("1f. every direction maps into the curated vocabulary",
          all(v in RELATIONSHIP_TYPES
              for v in DIRECTION_TO_RELATIONSHIP.values()),
          str(DIRECTION_TO_RELATIONSHIP))


def test_2_the_real_draft_is_inert() -> None:
    print("\n--- 2: THE safety property, against the real file ---")
    if not DRAFT.is_file():
        skip("2. inert draft", "no draft artifact on disk")
        return

    res = load_curated_linkage(DRAFT)
    check("2a. the header IS accepted -- it is the curated schema",
          res.header_matched is True)
    check("2b. rows are present to reject", res.rows_seen > 0,
          str(res.rows_seen))
    check("2c. EVERY row is rejected",
          res.rows_rejected == res.rows_seen,
          f"{res.rows_rejected} of {res.rows_seen}")
    check("2d. so no edge is usable", len(res.edges) == 0, str(len(res.edges)))
    check("2e. and the load is not ok", res.ok is False)

    # Rejected for the RIGHT reason: the owner fields, not something incidental.
    blamed = {i.field for i in res.issues if i.severity == "error"}
    for f in OWNER_FIELDS:
        check(f"2f. {f} is named as a reason for rejection", f in blamed,
              str(sorted(blamed)))

    # All the way through to the gate input.
    panel = resolve_from_curated_map(
        [{"event_id": "X", "anchor": "JBL", "event_date": "2020-01-01"}],
        map_path=DRAFT)
    check("2g. uses_placeholder_linkage stays True -- C5 stays shut",
          panel.provenance.uses_placeholder_linkage is True)
    check("2h. and no pair is eligible", panel.pairs_eligible == 0)

    # CONTROL: completing the owner fields DOES make a row load. Without this,
    # 2c could pass because of an unrelated defect in the draft.
    import tempfile
    rows = _rows(DRAFT)
    filled = dict(rows[0])
    filled.update({"confidence": "high", "date_confidence": "high",
                   "curated_by": "test", "curated_date": "2026-09-01",
                   "review_status": "draft"})
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "filled.csv"
        with p.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(EXPECTED_HEADERS),
                               lineterminator="\n")
            w.writeheader()
            w.writerow(filled)
        got = load_curated_linkage(p)
        check("2i. CONTROL: the same row WITH the owner fields loads",
              len(got.edges) == 1,
              f"edges={len(got.edges)} rejected={got.rows_rejected}")
    check("2j. so the rejection is the blanks, not a malformed row",
          len(res.edges) == 0)


def test_3_every_row_cites_a_filing() -> None:
    print("\n--- 3: a draft row is still auditable back to its source ---")
    if not DRAFT.is_file():
        skip("3. citations", "no draft artifact on disk")
        return
    rows = _rows(DRAFT)
    check("3a. the header is exactly the curated schema",
          tuple(rows[0].keys()) == EXPECTED_HEADERS if rows else False)
    check("3b. every row names an accession",
          all("accession" in r["source_citation"] for r in rows))
    check("3c. every row states a concentration percentage",
          all("%" in r["source_citation"] for r in rows))
    check("3d. every row carries an EDGAR url",
          all(r["source_url"].startswith("https://www.sec.gov/Archives/")
              for r in rows), str([r["source_url"][:40] for r in rows][:2]))
    check("3e. relationship_type is always in the vocabulary",
          all(r["relationship_type"] in RELATIONSHIP_TYPES for r in rows))
    check("3f. as_of_date_basis is always the filing date",
          all(r["as_of_date_basis"] == AS_OF_BASIS for r in rows))
    check("3g. every row is marked DRAFT and machine-prepared",
          all("DRAFT" in r["notes_caveats"]
              and "MACHINE-PREPARED" in r["notes_caveats"] for r in rows))
    check("3h. every row carries its lineage evidence",
          all("LINEAGE" in r["notes_caveats"] for r in rows))
    check("3i. and warns that a preserved name proves nothing",
          all("merger" in r["notes_caveats"].lower() for r in rows))
    check("3j. every owner field is blank on every row",
          all(not r[f] for r in rows for f in OWNER_FIELDS))


def test_4_it_never_duplicates_a_curated_edge() -> None:
    print("\n--- 4: no row the map already has ---")
    if not (DRAFT.is_file() and CURATED_MAP.is_file()):
        skip("4. duplicates", "draft or curated map missing")
        return
    have = {(r["anchor_ticker"].upper(), r["peer_ticker"].upper())
            for r in _rows(CURATED_MAP)}
    draft = [(r["anchor_ticker"].upper(), r["peer_ticker"].upper())
             for r in _rows(DRAFT)]
    dupes = [p for p in draft if p in have]
    check("4a. no draft row duplicates an existing edge", not dupes, str(dupes))
    check("4b. and the draft has no internal duplicates",
          len(set(draft)) == len(draft), str(draft))
    # The two MCK->CVS candidates were excluded for exactly this reason.
    check("4c. MCK->CVS is not redrafted", ("MCK", "CVS") not in draft)


def test_5_the_gate_is_untouched() -> None:
    print("\n--- 5: nothing here moves the display gate ---")
    from hyp04_supply_chain_hedge.display_gate import current_decision
    d = current_decision()
    check("5a. gate CLOSED", d.status == "CLOSED", d.status)
    check("5b. C4 MET", d.conditions.get("C4_decisions_resolved") is True)
    check("5c. exactly 4 denials", len(d.denials) == 4, str(len(d.denials)))
    check("5d. eligible count still zero",
          d.evidence.get("eligible_event_count") == 0)


if __name__ == "__main__":
    test_1_the_owner_fields_are_all_required()
    test_2_the_real_draft_is_inert()
    test_3_every_row_cites_a_filing()
    test_4_it_never_duplicates_a_curated_edge()
    test_5_the_gate_is_untouched()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 LINKAGE-DRAFT TESTS PASSED")
