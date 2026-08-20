#!/usr/bin/env python3
"""Hand-curated linkage-map loader and validator -- HYP-04.

=== INGESTION PATH ONLY. NO CURATED MAP EXISTS YET. ===

This module can READ a hand-curated linkage map. It does not contain one, and
its existence does not mean one exists. Registry v1.1's required external
measurement stays `does_not_exist` until a real curated file is delivered,
validated, and accepted by the repo owner.

Nothing here fabricates rows. The only CSVs this module ships alongside are
synthetic test fixtures under test_hyp04_supply_chain_hedge_curated_linkage.py,
which are deliberately labelled as such and are never a data source.

=== WHY THIS EXISTS ===

The supply-chain teammate's automated map was deprioritised (2026-08-18); the
project switched to hand curation. See
`Live Signal Engine/HYP04_LINKAGE_SOURCE_DECISION_2026-08-18.md`.

=== RELATIONSHIP TO THE PHASE 0 PLACEHOLDER (Option A) ===

`run_canary_audit.candidate_peer_universe()` is deliberately NOT modified and
NOT replaced. It continues to return the sector-file-minus-anchors list that
the committed EDGAR coverage findings were measured against. Rewiring it to
derive peers from a curated map would silently make
HYP04_EDGAR_CANDIDATE_LINKAGE_FULL_2026-08-18.json and its canary
non-reproducible the moment a curated file landed. This loader lives
ALONGSIDE it; the two answer different questions and must not be merged.

=== DIRECTION IS A FIXED LOOKUP, NEVER PARSED ===

Stage 2's supplier/customer field derives from `relationship_type` through
RELATIONSHIP_TYPE_TO_DIRECTION below -- a closed table, settled by the repo
owner in the template's README tab.

`relationship_direction_notes` is HUMAN CONTEXT ONLY. It is stored verbatim
and never read programmatically, ever. This is not a stylistic preference:
prose-parsing is what produced the false edges in BOTH EDGAR extractors --
"Concentration of credit risk. During fiscal 2025, Apple Inc." as a
counterparty in source A, "Company regarding the protection of" in source B.
A curated map is the one place in this pipeline where a human has already
resolved the ambiguity, and re-deriving it from free text would throw that
away and reintroduce the exact failure mode.
"""
from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

TEMPLATE_HEADERS_CSV = LSE / "HYP04_Linkage_Map_TEMPLATE_headers.csv"

# --- Authoritative schema, supplied verbatim by the repo owner 2026-08-18 ---
# Order is significant: the header-drift check compares the sequence, not just
# the set, so a reordered future template is reported rather than absorbed.
EXPECTED_HEADERS: tuple[str, ...] = (
    "anchor_ticker",
    "peer_ticker",
    "relationship_type",
    "relationship_direction_notes",
    "confidence",
    "source_type",
    "source_citation",
    "source_url",
    "as_of_date",
    "as_of_date_basis",
    "date_confidence",
    "notes_caveats",
    "curated_by",
    "curated_date",
    "review_status",
)

# --- Enums, verbatim and CASE-SENSITIVE ------------------------------------
RELATIONSHIP_TYPES = (
    "direct_supplier", "direct_customer", "sector_competitor",
    "loose_sector_neighbor",
)
CONFIDENCE_LEVELS = ("high", "medium", "low")
DATE_CONFIDENCE_LEVELS = ("high", "medium", "low")
SOURCE_TYPES = (
    "10-K Competition section",
    "10-K Customer Concentration Note",
    "8-K Material Agreement",
    "Press Release",
    "Analyst/Industry Report",
    "Other",
)
AS_OF_DATE_BASES = (
    "filing date of source",
    "earlier - explicit statement in source",
    "earlier - estimated",
    "unknown/uncertain",
)
REVIEW_STATUSES = ("draft", "reviewed", "needs revisit")

# --- Direction lookup (owner-settled; closed table) -------------------------
DIRECTION_SUPPLIER = "supplier"
DIRECTION_CUSTOMER = "customer"
DIRECTION_NOT_APPLICABLE = "not_applicable"

RELATIONSHIP_TYPE_TO_DIRECTION: dict[str, str] = {
    "direct_supplier": DIRECTION_SUPPLIER,
    "direct_customer": DIRECTION_CUSTOMER,
    "sector_competitor": DIRECTION_NOT_APPLICABLE,
    "loose_sector_neighbor": DIRECTION_NOT_APPLICABLE,
}

# Fields that must be non-empty on every row.
#
# `source_citation` was moved from OPTIONAL to REQUIRED on 2026-08-20, narrowing
# the semantics of the owner-supplied schema above. The COLUMN SET AND ITS ORDER
# ARE UNCHANGED -- EXPECTED_HEADERS is byte-identical, so no template is
# invalidated and the header-drift check is not triggered. Only the
# blank-allowed rule tightens.
#
# Why: `source_type` is required and drawn from a closed vocabulary naming
# specific SEC filing sections ("10-K Customer Concentration Note", "8-K
# Material Agreement", ...). With the citation optional, a row could assert that
# a named filing establishes a supply-chain edge without identifying WHICH
# filing -- an unverifiable provenance claim that passed validation and reached
# res.edges. A linkage map is only as good as the ability to audit one edge
# back to its source, and that ability is exactly what a blank citation removes.
#
# Zero rows were curated when this changed, so it invalidates no existing data.
REQUIRED_FIELDS: tuple[str, ...] = (
    "anchor_ticker", "peer_ticker", "relationship_type", "confidence",
    "source_type", "source_citation", "as_of_date", "as_of_date_basis",
    "date_confidence", "curated_by", "curated_date", "review_status",
)

# Fields allowed to be blank. relationship_direction_notes is optional AND
# never read programmatically.
#
# `source_url` stays optional DELIBERATELY, not by oversight. URLs rot, and
# several source types (an analyst report, a paper filing) may have no stable
# public URL at all. The citation string is the durable artifact; requiring a
# URL too would push curators toward pasting a fragile link to satisfy the
# validator. Requiring the citation is what makes an edge auditable.
OPTIONAL_FIELDS: tuple[str, ...] = (
    "relationship_direction_notes", "source_url", "notes_caveats",
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LinkageSchemaError(RuntimeError):
    """Raised when the file's header row does not match the expected schema."""


@dataclass
class RowIssue:
    row_number: int          # 1-based data row (header excluded)
    severity: str            # "error" | "warning"
    field: Optional[str]
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CuratedEdge:
    anchor_ticker: str
    peer_ticker: str
    relationship_type: str
    direction: str                       # DERIVED, never parsed from notes
    confidence: str
    source_type: str
    source_citation: str
    source_url: str
    as_of_date: str
    as_of_date_basis: str
    date_confidence: str
    curated_by: str
    curated_date: str
    review_status: str
    relationship_direction_notes: str    # stored, NEVER read programmatically
    notes_caveats: str
    row_number: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LinkageLoadResult:
    edges: list[CuratedEdge] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    rows_seen: int = 0
    rows_rejected: int = 0
    header_matched: bool = True
    header_diff: dict[str, Any] = field(default_factory=dict)
    source_path: Optional[str] = None

    @property
    def errors(self) -> list[RowIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[RowIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return self.header_matched and not self.errors

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        by_direction: dict[str, int] = {}
        by_review: dict[str, int] = {}
        for e in self.edges:
            by_type[e.relationship_type] = by_type.get(e.relationship_type, 0) + 1
            by_direction[e.direction] = by_direction.get(e.direction, 0) + 1
            by_review[e.review_status] = by_review.get(e.review_status, 0) + 1
        return {
            "source_path": self.source_path,
            "header_matched": self.header_matched,
            "rows_seen": self.rows_seen,
            "rows_accepted": len(self.edges),
            "rows_rejected": self.rows_rejected,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "unique_anchors": len({e.anchor_ticker for e in self.edges}),
            "unique_peers": len({e.peer_ticker for e in self.edges}),
            "by_relationship_type": by_type,
            "by_direction": by_direction,
            "by_review_status": by_review,
            "is_production_linkage_map": False,
            "note": (
                "Ingestion result only. A validated file is not an accepted "
                "linkage map -- acceptance is a separate repo-owner decision."),
        }


# ==========================================================================
def direction_for(relationship_type: str) -> Optional[str]:
    """Stage 2 direction from relationship_type. Closed lookup, no inference.

    Returns None for an unrecognised type rather than guessing, so an unknown
    value surfaces as a validation error instead of silently becoming
    not_applicable.
    """
    return RELATIONSHIP_TYPE_TO_DIRECTION.get(relationship_type)


def check_headers(actual: Iterable[str]) -> tuple[bool, dict[str, Any]]:
    """Compare a header row against EXPECTED_HEADERS, in order.

    Cheap insurance against a future template revision drifting from the
    2026-08-18 spec. Reports a diff rather than absorbing the difference,
    because silently accepting a renamed column is how a schema change
    becomes a data-integrity problem nobody notices.
    """
    actual = [h.strip().lstrip("﻿") for h in actual]
    expected = list(EXPECTED_HEADERS)
    if actual == expected:
        return True, {}
    return False, {
        "expected": expected,
        "actual": actual,
        "missing": [h for h in expected if h not in actual],
        "unexpected": [h for h in actual if h not in expected],
        "order_differs": (sorted(actual) == sorted(expected) and actual != expected),
        "expected_count": len(expected),
        "actual_count": len(actual),
    }


def _valid_date(value: str) -> bool:
    if not DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def load_curated_linkage(
    path: Path,
    *,
    known_tickers: Optional[set[str]] = None,
    strict_headers: bool = True,
) -> LinkageLoadResult:
    """Load and validate a hand-curated linkage CSV.

    Validation policy, matching the Phase 0 audit's style -- classify and
    report rather than crash, so one bad row never hides the rest of the file:

      ERROR   (row rejected)  missing/blank required field; unknown enum
                              value; malformed date; unrecognised
                              relationship_type; duplicate anchor-peer pair
      WARNING (row kept)      ticker outside the known universe

    The ticker check is a WARNING on purpose. The curated map is expected to
    reach beyond the Phase 0 placeholder universe -- that is much of the point
    of curating one -- so an unfamiliar ticker is a thing to look at, not a
    thing to reject.
    """
    res = LinkageLoadResult(source_path=str(path))

    if not path.is_file():
        res.header_matched = False
        res.issues.append(RowIssue(0, "error", None, f"file not found: {path}"))
        return res

    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            res.header_matched = False
            res.issues.append(RowIssue(0, "error", None, "file is empty"))
            return res

        matched, diff = check_headers(header)
        res.header_matched = matched
        res.header_diff = diff
        if not matched:
            res.issues.append(RowIssue(
                0, "error", None,
                "header row does not match the expected schema; "
                f"missing={diff.get('missing')} unexpected={diff.get('unexpected')}"))
            if strict_headers:
                return res

        cols = [h.strip().lstrip("﻿") for h in header]
        seen_pairs: dict[tuple[str, str], int] = {}

        for i, raw in enumerate(reader, start=1):
            res.rows_seen += 1
            if not any((c or "").strip() for c in raw):
                continue                       # blank line, silently skipped
            row = {cols[j]: (raw[j].strip() if j < len(raw) else "")
                   for j in range(len(cols))}
            row_errors: list[RowIssue] = []

            for f in REQUIRED_FIELDS:
                if not row.get(f):
                    row_errors.append(RowIssue(
                        i, "error", f, f"required field {f!r} is missing or blank"))

            rt = row.get("relationship_type", "")
            if rt and rt not in RELATIONSHIP_TYPES:
                row_errors.append(RowIssue(
                    i, "error", "relationship_type",
                    f"{rt!r} is not one of {list(RELATIONSHIP_TYPES)}"))
            for fname, allowed in (("confidence", CONFIDENCE_LEVELS),
                                   ("date_confidence", DATE_CONFIDENCE_LEVELS),
                                   ("source_type", SOURCE_TYPES),
                                   ("as_of_date_basis", AS_OF_DATE_BASES),
                                   ("review_status", REVIEW_STATUSES)):
                v = row.get(fname, "")
                if v and v not in allowed:
                    row_errors.append(RowIssue(
                        i, "error", fname, f"{v!r} is not one of {list(allowed)}"))

            for fname in ("as_of_date", "curated_date"):
                v = row.get(fname, "")
                if v and not _valid_date(v):
                    row_errors.append(RowIssue(
                        i, "error", fname,
                        f"{v!r} is not a valid YYYY-MM-DD date"))

            anchor = row.get("anchor_ticker", "").upper()
            peer = row.get("peer_ticker", "").upper()
            if anchor and peer:
                if anchor == peer:
                    row_errors.append(RowIssue(
                        i, "error", "peer_ticker",
                        f"anchor and peer are the same ticker ({anchor})"))
                pair = (anchor, peer)
                if pair in seen_pairs:
                    row_errors.append(RowIssue(
                        i, "error", "peer_ticker",
                        f"duplicate anchor-peer pair {anchor}->{peer}, "
                        f"first seen on row {seen_pairs[pair]}"))
                else:
                    seen_pairs[pair] = i

            direction = direction_for(rt) if rt else None
            if rt and direction is None:
                row_errors.append(RowIssue(
                    i, "error", "relationship_type",
                    f"no direction mapping for {rt!r}"))

            if known_tickers is not None:
                for fname, val in (("anchor_ticker", anchor), ("peer_ticker", peer)):
                    if val and val not in known_tickers:
                        res.issues.append(RowIssue(
                            i, "warning", fname,
                            f"{val} is outside the known anchor/peer universe "
                            "-- kept, but worth confirming"))

            if row_errors:
                res.issues.extend(row_errors)
                res.rows_rejected += 1
                continue

            res.edges.append(CuratedEdge(
                anchor_ticker=anchor,
                peer_ticker=peer,
                relationship_type=rt,
                direction=direction or DIRECTION_NOT_APPLICABLE,
                confidence=row.get("confidence", ""),
                source_type=row.get("source_type", ""),
                source_citation=row.get("source_citation", ""),
                source_url=row.get("source_url", ""),
                as_of_date=row.get("as_of_date", ""),
                as_of_date_basis=row.get("as_of_date_basis", ""),
                date_confidence=row.get("date_confidence", ""),
                curated_by=row.get("curated_by", ""),
                curated_date=row.get("curated_date", ""),
                review_status=row.get("review_status", ""),
                # Stored verbatim. NEVER read programmatically.
                relationship_direction_notes=row.get(
                    "relationship_direction_notes", ""),
                notes_caveats=row.get("notes_caveats", ""),
                row_number=i,
            ))

    return res


def known_universe() -> set[str]:
    """Anchors + Phase 0 placeholder peers, for the ticker WARNING only.

    Reads run_canary_audit rather than duplicating either list. Used purely to
    decide whether a ticker is familiar; it never constrains what a curated
    map may contain.
    """
    from .run_canary_audit import LOCKED_24_ANCHORS, candidate_peer_universe
    return set(LOCKED_24_ANCHORS) | set(candidate_peer_universe())


def format_report(res: LinkageLoadResult, *, max_issues: int = 30) -> str:
    lines = ["=== HYP-04 hand-curated linkage: ingestion report ==="]
    for k, v in res.summary().items():
        lines.append(f"  {k:28s} {v}")
    if res.header_diff:
        lines.append("\n  HEADER MISMATCH:")
        for k, v in res.header_diff.items():
            lines.append(f"    {k:16s} {v}")
    if res.issues:
        lines.append(f"\n  issues (showing up to {max_issues}):")
        for it in res.issues[:max_issues]:
            loc = f"row {it.row_number}" if it.row_number else "file"
            fld = f" [{it.field}]" if it.field else ""
            lines.append(f"    {it.severity.upper():7s} {loc}{fld}: {it.message}")
    lines.append("\n  NOTE: a validated file is an INGESTED file, not an accepted "
                 "linkage map.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Validate a hand-curated HYP-04 linkage CSV. Reads only.")
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--no-universe-check", action="store_true")
    a = ap.parse_args(argv)

    res = load_curated_linkage(
        a.csv_path,
        known_tickers=None if a.no_universe_check else known_universe())
    print(format_report(res))
    return 0 if res.ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
