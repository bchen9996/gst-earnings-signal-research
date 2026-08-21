#!/usr/bin/env python3
"""Hand-curated linkage loader tests -- HYP-04.

Every CSV here is a SYNTHETIC TEST FIXTURE written inline, never a data
source. No curated linkage data exists; these rows exist only to exercise the
validator and are labelled as such in the fixtures themselves.

Fully offline. Sockets blocked before import.

Run directly: python test_hyp04_supply_chain_hedge_curated_linkage.py
"""
from __future__ import annotations

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

from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    AS_OF_DATE_BASES,
    CONFIDENCE_LEVELS,
    DIRECTION_CUSTOMER,
    DIRECTION_NOT_APPLICABLE,
    DIRECTION_SUPPLIER,
    EXPECTED_HEADERS,
    RELATIONSHIP_TYPE_TO_DIRECTION,
    RELATIONSHIP_TYPES,
    REVIEW_STATUSES,
    SOURCE_TYPES,
    check_headers,
    direction_for,
    load_curated_linkage,
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


HEADER = ",".join(EXPECTED_HEADERS)

# --- SYNTHETIC fixture rows. Not data. -------------------------------------
GOOD_SUPPLIER = (
    "NVDA,COHR,direct_supplier,SYNTHETIC TEST ROW - optics supplier,high,"
    "10-K Customer Concentration Note,SYNTHETIC citation,https://example.invalid/a,"
    "2026-02-25,filing date of source,high,SYNTHETIC TEST FIXTURE - not real data,"
    "test_fixture,2026-08-18,draft")

GOOD_CUSTOMER = (
    "MCK,CVS,direct_customer,SYNTHETIC TEST ROW - distribution customer,medium,"
    "10-K Customer Concentration Note,SYNTHETIC citation,https://example.invalid/b,"
    "2026-05-08,earlier - explicit statement in source,medium,"
    "SYNTHETIC TEST FIXTURE - not real data,test_fixture,2026-08-18,reviewed")

GOOD_COMPETITOR = (
    "AAPL,MCHP,sector_competitor,SYNTHETIC TEST ROW,low,10-K Competition section,"
    "SYNTHETIC citation,,2026-01-15,earlier - estimated,low,"
    "SYNTHETIC TEST FIXTURE - not real data,test_fixture,2026-08-18,needs revisit")

# Deliberately bad: as_of_date is BLANK (a required field).
BAD_MISSING_DATE = (
    "NVDA,JBL,direct_supplier,SYNTHETIC BAD ROW - missing as_of_date,high,"
    "8-K Material Agreement,SYNTHETIC citation,https://example.invalid/c,"
    ",filing date of source,high,SYNTHETIC TEST FIXTURE - not real data,"
    "test_fixture,2026-08-18,draft")


def _write(tmp: Path, *rows: str, header: str = HEADER) -> Path:
    p = tmp / "curated.csv"
    p.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return p


# ===================== 1. the required smoke test =========================
def test_1_smoke_good_rows_accepted_bad_row_rejected() -> None:
    """2 good rows + 1 deliberately bad row: good in, bad out, file usable."""
    with tempfile.TemporaryDirectory() as td:
        p = _write(Path(td), GOOD_SUPPLIER, BAD_MISSING_DATE, GOOD_CUSTOMER)
        res = load_curated_linkage(p)

        check("1a. the header row matched the authoritative schema",
              res.header_matched, str(res.header_diff))
        check("1b. all three rows were seen", res.rows_seen == 3, str(res.rows_seen))
        check("1c. the two GOOD rows were accepted", len(res.edges) == 2,
              str([(e.anchor_ticker, e.peer_ticker) for e in res.edges]))
        check("1d. the BAD row was rejected", res.rows_rejected == 1)
        check("1e. the rejection names as_of_date",
              any(i.field == "as_of_date" for i in res.errors),
              str([(i.field, i.message) for i in res.errors]))
        check("1f. one bad row does not discard the good ones",
              {e.peer_ticker for e in res.edges} == {"COHR", "CVS"},
              "a bad row must not take the file down with it")
        check("1g. the result is NOT ok overall (errors present)", res.ok is False)


# ===================== 2. direction is a fixed lookup =====================
def test_2_direction_comes_from_the_lookup_not_from_notes() -> None:
    check("2a. direct_supplier -> supplier",
          direction_for("direct_supplier") == DIRECTION_SUPPLIER)
    check("2b. direct_customer -> customer",
          direction_for("direct_customer") == DIRECTION_CUSTOMER)
    check("2c. sector_competitor -> not_applicable",
          direction_for("sector_competitor") == DIRECTION_NOT_APPLICABLE)
    check("2d. loose_sector_neighbor -> not_applicable",
          direction_for("loose_sector_neighbor") == DIRECTION_NOT_APPLICABLE)
    check("2e. an unknown type returns None, never a guess",
          direction_for("some_new_type") is None)
    check("2f. the lookup covers exactly the four declared types",
          set(RELATIONSHIP_TYPE_TO_DIRECTION) == set(RELATIONSHIP_TYPES))

    # The notes field must NOT influence direction. Same row, contradictory
    # prose -- the lookup must win.
    misleading = (
        "NVDA,COHR,direct_supplier,"
        "SYNTHETIC - this text says CUSTOMER and must be ignored,high,"
        "10-K Customer Concentration Note,c,,2026-02-25,filing date of source,"
        "high,SYNTHETIC TEST FIXTURE,test_fixture,2026-08-18,draft")
    with tempfile.TemporaryDirectory() as td:
        res = load_curated_linkage(_write(Path(td), misleading))
        check("2g. contradictory prose in the notes does NOT change direction",
              len(res.edges) == 1 and res.edges[0].direction == DIRECTION_SUPPLIER,
              str([(e.direction, e.relationship_direction_notes[:30])
                   for e in res.edges]))
        check("2h. but the notes are still stored verbatim",
              bool(res.edges) and "must be ignored"
              in res.edges[0].relationship_direction_notes)


# ===================== 3. required fields and enums =======================
def test_3_required_fields_and_enum_validation() -> None:
    base = GOOD_SUPPLIER.split(",")
    idx = {h: i for i, h in enumerate(EXPECTED_HEADERS)}

    def mutate(field: str, value: str) -> str:
        row = list(base)
        row[idx[field]] = value
        return ",".join(row)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for f in ("anchor_ticker", "peer_ticker", "relationship_type",
                  "confidence", "source_type", "source_citation", "as_of_date",
                  "as_of_date_basis", "date_confidence", "curated_by",
                  "curated_date", "review_status"):
            res = load_curated_linkage(_write(tmp, mutate(f, "")))
            check(f"3a. blank required field {f!r} rejects the row",
                  res.rows_rejected == 1 and not res.edges)

        for f, bad in (("relationship_type", "supplier"),
                       ("confidence", "HIGH"),
                       ("date_confidence", "very high"),
                       ("source_type", "10-K"),
                       ("as_of_date_basis", "filing date"),
                       ("review_status", "Draft")):
            res = load_curated_linkage(_write(tmp, mutate(f, bad)))
            check(f"3b. invalid {f}={bad!r} rejects the row (case-sensitive)",
                  res.rows_rejected == 1 and not res.edges)

        for bad_date in ("2026-13-01", "18/08/2026", "2026-8-18", "not a date"):
            res = load_curated_linkage(_write(tmp, mutate("as_of_date", bad_date)))
            check(f"3c. malformed as_of_date {bad_date!r} rejects the row",
                  res.rows_rejected == 1 and not res.edges)

        # Optional fields may be blank. This check used to blank BOTH
        # source_citation and source_url and assert the row was accepted, which
        # encoded the gap fixed on 2026-08-20: source_type is required and names
        # a specific filing, so a row could cite a 10-K without saying which.
        # source_url stays optional; the citation does not.
        row = ",".join([c if i != idx["source_url"] else ""
                        for i, c in enumerate(base)])
        res = load_curated_linkage(_write(tmp, row))
        check("3d. optional fields may be blank", len(res.edges) == 1,
              str([(i.field, i.message) for i in res.errors]))


# ============ 3e-3h. a source claim must carry its citation ===============
def test_3_source_claims_must_be_auditable() -> None:
    """source_type names a filing; source_citation says WHICH filing.

    Both directions. A rule that only rejected would be satisfied by a loader
    that rejects everything, so the accept case carries equal weight -- and the
    source_url case proves the rule targets the citation specifically rather
    than "any provenance field".
    """
    base = GOOD_SUPPLIER.split(",")
    idx = {h: i for i, h in enumerate(EXPECTED_HEADERS)}

    def mutate(field: str, value: str) -> str:
        row = list(base)
        row[idx[field]] = value
        return ",".join(row)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # A filing is named, nothing identifies it.
        res = load_curated_linkage(_write(tmp, mutate("source_citation", "")))
        check("3e. a blank citation REJECTS the row",
              res.rows_rejected == 1 and not res.edges)
        check("3e. and the failure is an error naming source_citation",
              any(i.field == "source_citation" and i.severity == "error"
                  for i in res.errors),
              str([(i.field, i.severity, i.message) for i in res.issues]))
        check("3e. so the file as a whole is not ok", res.ok is False)

        # Whitespace is not a citation.
        res = load_curated_linkage(_write(tmp, mutate("source_citation", "   ")))
        check("3f. a whitespace-only citation REJECTS the row",
              res.rows_rejected == 1 and not res.edges)

        # The other direction: with a citation the row is accepted, and the
        # citation survives onto the edge rather than being dropped.
        res = load_curated_linkage(_write(tmp, GOOD_SUPPLIER))
        check("3g. a row WITH a citation is accepted",
              len(res.edges) == 1 and res.ok is True,
              str([(i.field, i.message) for i in res.errors]))
        check("3g. and the citation reaches the edge",
              bool(res.edges and res.edges[0].source_citation.strip()))

        # source_url is deliberately still optional -- URLs rot, and requiring
        # one would push curators toward pasting a fragile link to satisfy the
        # validator. GOOD_COMPETITOR ships with a blank url for this reason.
        res = load_curated_linkage(_write(tmp, mutate("source_url", "")))
        check("3h. a blank source_url is still ACCEPTED when a citation exists",
              len(res.edges) == 1 and res.ok is True,
              str([(i.field, i.message) for i in res.errors]))
        res = load_curated_linkage(_write(tmp, GOOD_COMPETITOR))
        check("3h. the blank-url fixture row still loads",
              len(res.edges) == 1, str([(i.field, i.message) for i in res.errors]))


# ===================== 4. duplicates and self-pairs =======================
def test_4_duplicate_pairs_are_flagged() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        res = load_curated_linkage(_write(tmp, GOOD_SUPPLIER, GOOD_SUPPLIER))
        check("4a. a duplicate anchor-peer pair is rejected",
              res.rows_rejected == 1 and len(res.edges) == 1)
        check("4b. the message points at the first occurrence",
              any("first seen on row 1" in i.message for i in res.errors),
              str([i.message for i in res.errors]))

        # Case-insensitive on tickers: nvda/cohr duplicates NVDA/COHR.
        lower = GOOD_SUPPLIER.replace("NVDA,COHR", "nvda,cohr", 1)
        res2 = load_curated_linkage(_write(tmp, GOOD_SUPPLIER, lower))
        check("4c. duplicate detection is case-insensitive on tickers",
              res2.rows_rejected == 1, str(res2.rows_rejected))

        selfpair = GOOD_SUPPLIER.replace("NVDA,COHR", "NVDA,NVDA", 1)
        res3 = load_curated_linkage(_write(tmp, selfpair))
        check("4d. an anchor paired with itself is rejected",
              res3.rows_rejected == 1 and not res3.edges)

        # A peer legitimately linked to TWO anchors is NOT a duplicate.
        other = GOOD_SUPPLIER.replace("NVDA,COHR", "AAPL,COHR", 1)
        res4 = load_curated_linkage(_write(tmp, GOOD_SUPPLIER, other))
        check("4e. the same peer under a different anchor is NOT a duplicate",
              len(res4.edges) == 2 and res4.rows_rejected == 0)


# ===================== 5. unknown tickers WARN, never fail ================
def test_5_unknown_tickers_warn_but_are_kept() -> None:
    unknown = GOOD_SUPPLIER.replace("NVDA,COHR", "NVDA,ZZZZ", 1)
    with tempfile.TemporaryDirectory() as td:
        res = load_curated_linkage(_write(Path(td), unknown),
                                   known_tickers={"NVDA", "COHR"})
        check("5a. an out-of-universe ticker is KEPT", len(res.edges) == 1,
              "a curated map is expected to exceed the placeholder universe")
        check("5b. and produces a WARNING, not an error",
              any(i.severity == "warning" and i.field == "peer_ticker"
                  for i in res.issues) and not res.errors)
        check("5c. warnings alone leave the result ok", res.ok is True)

        res2 = load_curated_linkage(_write(Path(td), unknown), known_tickers=None)
        check("5d. the universe check is skippable", not res2.warnings)


# ===================== 6. header-drift insurance ==========================
def test_6_header_mismatch_is_reported_not_absorbed() -> None:
    check("6a. the authoritative header matches itself",
          check_headers(EXPECTED_HEADERS)[0])
    check("6b. a UTF-8 BOM does not break the match",
          check_headers(["﻿anchor_ticker", *EXPECTED_HEADERS[1:]])[0])

    renamed = list(EXPECTED_HEADERS)
    renamed[9] = "as_of_basis"
    ok, diff = check_headers(renamed)
    check("6c. a renamed column is detected", not ok)
    check("6d. and the diff names both sides",
          "as_of_date_basis" in diff["missing"] and "as_of_basis" in diff["unexpected"])

    reordered = [EXPECTED_HEADERS[1], EXPECTED_HEADERS[0], *EXPECTED_HEADERS[2:]]
    ok2, diff2 = check_headers(reordered)
    check("6e. a reordered header is detected", not ok2)
    check("6f. and is identified as an ordering difference",
          diff2["order_differs"] is True)

    with tempfile.TemporaryDirectory() as td:
        p = _write(Path(td), GOOD_SUPPLIER, header=",".join(renamed))
        res = load_curated_linkage(p, strict_headers=True)
        check("6g. strict mode refuses to parse a drifted file",
              res.header_matched is False and not res.edges)
        check("6h. and the result is not ok", res.ok is False)


# ===================== 7. Option A: nothing was rewired ==================
def test_7_placeholder_universe_is_untouched() -> None:
    """Option A: candidate_peer_universe() must be unchanged and independent."""
    import inspect

    from hyp04_supply_chain_hedge import curated_linkage as CL
    from hyp04_supply_chain_hedge import run_canary_audit as RCA

    peers = RCA.candidate_peer_universe()
    check("7a. candidate_peer_universe() still returns the 27 placeholder peers",
          len(peers) == 27, str(len(peers)))
    # The function body uses the module-level SECTOR_CSV constant, so assert
    # against the resolved path rather than a literal inside the function.
    check("7b. it still reads the sector file, not a curated map",
          "AllTickers_Sectors" in str(RCA.SECTOR_CSV)
          and "SECTOR_CSV" in inspect.getsource(RCA.candidate_peer_universe),
          str(RCA.SECTOR_CSV))

    # Check actual IMPORTS via AST, not a substring scan. run_canary_audit's
    # docstring legitimately NAMES curated_linkage.py when explaining why
    # Option A keeps them separate, and a naive scan flags that -- failing on
    # the documentation of the very property it is asserting.
    import ast

    rca_tree = ast.parse(inspect.getsource(RCA))
    imported: list[str] = []
    for n in ast.walk(rca_tree):
        if isinstance(n, ast.Import):
            imported += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            imported.append(n.module or "")
            imported += [f"{n.module or ''}.{a.name}" for a in n.names]
    check("7c. run_canary_audit does not IMPORT the curated loader",
          not any("curated_linkage" in m for m in imported),
          f"Option A: the two paths stay independent; imports={imported}")

    cl_src = inspect.getsource(CL)
    check("7d. the curated loader never parses the notes field",
          "relationship_direction_notes" in cl_src
          and ".lower()" not in cl_src.split("relationship_direction_notes")[-1][:200])
    check("7e. and states it is not a production linkage map",
          "is_production_linkage_map" in cl_src)


def test_8_template_is_blank_and_any_curated_map_validates() -> None:
    """Two DIFFERENT properties, one per kind of file.

    This began as a single blanket rule -- every HYP04_Linkage_Map*.csv must
    contain headers only -- which was correct while zero rows were curated and
    the repo carried nothing but a schema. It also forbade a real curated map
    from ever living in the repo, which is untenable: the display gate's C3
    requires the eligible event set to be frozen together with the analysis
    code, and a map that is not committed makes any later result
    irreproducible and the freeze record unverifiable.

    So the rule is split by what each file IS:

      * the TEMPLATE must stay headers-only. It is the blank schema, and a
        stray data row in it is how half-finished content ships by accident.
      * a CURATED MAP must LOAD CLEAN. Committing rows is expected; committing
        rows that do not validate is not, because an invalid map is worse than
        no map -- it looks like data.

    A curated map that fails to load is a FAILURE here, not a skip. Rows whose
    judgement fields are still blank belong in a draft file named outside this
    glob, which is where they currently are.
    """
    from hyp04_supply_chain_hedge.curated_linkage import (
        TEMPLATE_HEADERS_CSV, LSE)

    # --- the template -------------------------------------------------
    if TEMPLATE_HEADERS_CSV.is_file():
        lines = [l for l in TEMPLATE_HEADERS_CSV.read_text(encoding="utf-8-sig")
                 .splitlines() if l.strip()]
        check(f"8a. {TEMPLATE_HEADERS_CSV.name} contains headers only",
              len(lines) <= 1, f"{len(lines)} non-blank lines")
        res = load_curated_linkage(TEMPLATE_HEADERS_CSV)
        check("8b. the template's header row matches the schema",
              res.header_matched, str(res.header_diff))
    else:
        skip("8a. template CSV present",
             f"{TEMPLATE_HEADERS_CSV.name} not in Live Signal Engine")

    # --- any curated map ----------------------------------------------
    maps = [p for p in LSE.glob("HYP04_Linkage_Map*.csv")
            if p != TEMPLATE_HEADERS_CSV]
    if not maps:
        skip("8c. curated linkage map present", "no curated map exists yet")
        return

    for p in maps:
        res = load_curated_linkage(p)
        check(f"8c. {p.name} loads clean", res.ok,
              f"{len(res.errors)} error(s): "
              + "; ".join(f"row {i.row_number} {i.field}" for i in res.errors[:6]))
        check(f"8d. {p.name} carries at least one edge",
              bool(res.edges), "a committed map with zero usable rows is not a map")


def test_9_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("9a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("9a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_smoke_good_rows_accepted_bad_row_rejected()
    test_2_direction_comes_from_the_lookup_not_from_notes()
    test_3_required_fields_and_enum_validation()
    test_3_source_claims_must_be_auditable()
    test_4_duplicate_pairs_are_flagged()
    test_5_unknown_tickers_warn_but_are_kept()
    test_6_header_mismatch_is_reported_not_absorbed()
    test_7_placeholder_universe_is_untouched()
    test_8_template_is_blank_and_any_curated_map_validates()
    test_9_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 CURATED-LINKAGE TESTS PASSED")
    sys.exit(0)
