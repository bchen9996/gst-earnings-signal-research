#!/usr/bin/env python3
"""The HYP-04 anchor universe: a RULE that is evaluated, not a list that is chosen.

=== THE HAZARD THIS EXISTS TO AVOID ===

On 2026-08-26 an EDGAR screen over 51 tickers found exactly two companies
disclosing a named counterparty concentration: MCK and PKG. Both are outside
the project's locked 24-ticker universe. Among the locked 24 the same screen
found ZERO.

The tempting fix is to add MCK and PKG to the anchor universe. That would be
choosing the universe because those are the tickers that turned out to have
usable edges -- selecting on the data, after seeing it, which is the exact
failure locking a universe exists to prevent. Every edge involved is real and
filing-backed, and it would still be post-hoc selection.

So this module does the other thing: it states a RULE, fixed in advance, and
evaluates it over a screening frame that was fixed earlier and for other
reasons. Tickers QUALIFY by satisfying the rule. They are never named into it.
Whatever the rule returns is the universe, including if that is one ticker, or
none.

=== THE RULE IS NOT ALLOWED TO KNOW WHO SURVIVED ===

Three things are DELIBERATELY not conditions: whether the counterparty still
exists, whether price history is obtainable for either side, and whether the
relationship still holds today. See NEVER_CONDITIONS.

This is not fastidiousness. PKG's disclosed counterparty, ODP, ceased to be a
public filer in 2026 and its entire price history is unobtainable from the
provider used here. Conditioning membership on obtainable data would delete
exactly the pairs where a relationship ended in an acquisition -- and
acquisition is frequently CAUSED by the commercial relationship under study.
The missing observations would not be missing at random with respect to the
hypothesis. Data availability is a MEASURABILITY question, reported per pair;
it is never a MEMBERSHIP question.

=== WHAT THIS MODULE DOES NOT DO ===

It does not open, move or touch any display-gate condition. C2 counts eligible
ANCHOR EVENTS, and eligibility is decided by
`gst_market_response.completeness`, which reads per-event capture records.
Declaring who MAY be an anchor produces no such record for anybody. The gate
stays CLOSED and the eligible-event count stays zero.

NOTHING HERE IS EVIDENCE ABOUT SUPPLY-CHAIN TRANSMISSION.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from .edgar_linkage import BASIS_CONSOLIDATED_REVENUE

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

RULE_ID = "HYP04-ANCHOR-UNIVERSE-RULE-v1"

# ==========================================================================
# The rule's fixed parameters
# ==========================================================================
# ASC 280-10-50-42 requires a public entity to disclose reliance on a single
# customer at "10 percent or more of an entity's revenues". The threshold and
# the denominator are BOTH taken from the standard rather than chosen here --
# picking either one to suit an observed set of tickers is the selection this
# module exists to avoid.
CONCENTRATION_THRESHOLD_PCT = 10.0
REQUIRED_BASIS = BASIS_CONSOLIDATED_REVENUE
ANNUAL_REPORT_FORM_PREFIX = "10-K"

# Conditions. Each denies independently; a ticker qualifies only if none fire.
CONDITIONS: tuple[tuple[str, str], ...] = (
    ("AU-1", "the ticker is in the declared screening frame"),
    ("AU-2", "an annual report (10-K) was screened for it, filed on or before "
             "the cutoff"),
    ("AU-3", "that filing NAMES a specific counterparty"),
    ("AU-4", f"the concentration is stated against {REQUIRED_BASIS} -- not a "
             "segment, receivables or an unrecognised denominator"),
    ("AU-5", f"the concentration is >= {CONCENTRATION_THRESHOLD_PCT}% of that "
             "denominator"),
    ("AU-6", "the disclosure carries a valid filing date on or before the cutoff"),
)

# The conditions that were considered and DELIBERATELY REJECTED, recorded here
# so that adding one later is a visible change to a stated decision rather
# than a quiet tightening.
NEVER_CONDITIONS: tuple[tuple[str, str], ...] = (
    ("counterparty still exists",
     "Excluding anchors whose counterparty was acquired or taken private "
     "selects on survival. Acquisition is often caused by the very "
     "relationship under study, so the excluded pairs are not missing at "
     "random with respect to the hypothesis."),
    ("price history obtainable",
     "A provider that drops delisted securities is survivorship-biased by "
     "construction. Letting that provider decide the universe imports its "
     "bias into the preregistration. Measurability is reported per pair; it "
     "never decides membership."),
    ("relationship still current",
     "The measurement is point-in-time: an edge is used at anchor events "
     "AFTER its as-of date. A relationship that has since ended is still a "
     "real relationship for the events it covered."),
    ("the ticker is in the locked 24-ticker universe",
     "The locked universe is HYP-01 confirmatory infrastructure with its own "
     "drift test. HYP-04 is exploratory and does not modify it. Requiring "
     "membership would make this universe empty -- the 51-ticker screen found "
     "zero named counterparties among the locked 24."),
)


def screening_frame() -> frozenset[str]:
    """The set of tickers the rule is EVALUATED OVER.

    A rule applied to a hand-picked candidate list is still a hand-picked
    universe, so the frame has to come from somewhere that predates this
    decision. It does: the locked 24 anchors, plus the Phase 0 candidate peer
    universe read out of AllTickers_Sectors.csv.

    Provenance, checkable in git rather than asserted: the sector file arrived
    in the initial commit (77c18d5, 2026-07-23); candidate_peer_universe() was
    written 2026-08-18 (42cc220); the first curated linkage edge did not exist
    until 2026-08-22 (9f76358). MCK and PKG were inside this frame a month
    before any edge involving them existed. The frame was not drawn around
    them.
    """
    from .run_canary_audit import LOCKED_24_ANCHORS, candidate_peer_universe
    return frozenset(LOCKED_24_ANCHORS) | frozenset(candidate_peer_universe())


# Fields every screened edge must carry. A screen missing any of them is
# REFUSED, not silently evaluated -- an artifact produced before the
# denominator was captured would otherwise yield an empty universe that looks
# like a finding instead of a missing input.
REQUIRED_EDGE_FIELDS: tuple[str, ...] = (
    "reporting_company", "counterparty_is_named", "named_counterparty",
    "concentration_pct", "concentration_basis", "as_of_date", "form",
    "accession",
)


def _valid_iso_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class AnchorQualification:
    """Whether one ticker satisfies the rule, and on what evidence."""

    ticker: str
    qualifies: bool
    denials: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ticker": self.ticker, "qualifies": self.qualifies,
                "denials": list(self.denials), "evidence": self.evidence}


def evaluate_ticker(
    ticker: str,
    edges: Sequence[Mapping[str, Any]],
    *,
    cutoff_date: str,
    frame: Iterable[str],
) -> AnchorQualification:
    """Apply the rule to one ticker. Fail-closed: every unknown denies.

    `edges` is the screened disclosure set for this ticker, in the shape the
    EDGAR screen artifact stores. Qualification is decided from those records
    only; nothing is looked up, and no caller may assert the outcome.
    """
    denials: list[str] = []
    frame_set = {t.upper() for t in frame}
    tick = ticker.upper()
    cutoff = _valid_iso_date(cutoff_date)
    if cutoff is None:
        return AnchorQualification(
            tick, False, (f"AU-6: cutoff date {cutoff_date!r} is not YYYY-MM-DD",),
            {"cutoff_date": cutoff_date})

    if tick not in frame_set:
        denials.append(f"AU-1: {tick} is not in the screening frame")

    mine = [e for e in edges
            if str(e.get("reporting_company", "")).upper() == tick]
    annual = [e for e in mine
              if str(e.get("form", "")).upper().startswith(ANNUAL_REPORT_FORM_PREFIX)]
    if not annual:
        denials.append(
            f"AU-2: no {ANNUAL_REPORT_FORM_PREFIX} disclosure was screened for {tick}")

    qualifying: list[dict[str, Any]] = []
    near_misses: list[dict[str, Any]] = []
    for e in annual:
        why: list[str] = []
        name = e.get("named_counterparty")
        if not e.get("counterparty_is_named") or not isinstance(name, str) \
                or not name.strip():
            why.append("AU-3: no named counterparty")
        basis = e.get("concentration_basis")
        if basis != REQUIRED_BASIS:
            why.append(f"AU-4: denominator is {basis!r}, not {REQUIRED_BASIS!r}")
        pct = e.get("concentration_pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            why.append(f"AU-5: concentration {pct!r} is not a number")
        elif float(pct) < CONCENTRATION_THRESHOLD_PCT:
            why.append(f"AU-5: {float(pct)}% is below "
                       f"{CONCENTRATION_THRESHOLD_PCT}%")
        as_of = _valid_iso_date(e.get("as_of_date"))
        if as_of is None:
            why.append(f"AU-6: filing date {e.get('as_of_date')!r} is not YYYY-MM-DD")
        elif as_of > cutoff:
            why.append(f"AU-6: filed {as_of.isoformat()}, after the "
                       f"{cutoff.isoformat()} cutoff")

        record = {
            "counterparty": name,
            "concentration_pct": pct,
            "concentration_basis": basis,
            "concentration_basis_text": e.get("concentration_basis_text"),
            "as_of_date": e.get("as_of_date"),
            "accession": e.get("accession"),
            "form": e.get("form"),
            "direction": e.get("direction"),
        }
        if why:
            near_misses.append({**record, "denials": why})
        else:
            qualifying.append(record)

    if annual and not qualifying:
        denials.append(
            f"AU-3/4/5/6: {tick} has {len(annual)} screened disclosure(s), none "
            "of which is a named counterparty at or above "
            f"{CONCENTRATION_THRESHOLD_PCT}% of {REQUIRED_BASIS} on or before "
            f"{cutoff.isoformat()}")

    return AnchorQualification(
        ticker=tick,
        qualifies=not denials,
        denials=tuple(denials),
        evidence={
            "qualifying_disclosures": qualifying,
            "screened_disclosures": len(mine),
            "annual_report_disclosures": len(annual),
            "near_misses": near_misses,
            "cutoff_date": cutoff.isoformat(),
        },
    )


@dataclass(frozen=True)
class UniverseDerivation:
    """The universe the rule produces, with every evaluation kept."""

    rule_id: str
    cutoff_date: str
    members: tuple[str, ...]
    qualifications: tuple[AnchorQualification, ...]
    refusals: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def derived(self) -> bool:
        """A refused derivation produces no universe at all, not a small one."""
        return not self.refusals

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "cutoff_date": self.cutoff_date,
            "derived": self.derived,
            "members": list(self.members),
            "refusals": list(self.refusals),
            "evidence": self.evidence,
            "qualifications": [q.as_dict() for q in self.qualifications
                               if q.qualifies or q.evidence.get("near_misses")],
        }


def derive_universe(
    screen: Mapping[str, Any],
    *,
    cutoff_date: str,
    frame: Optional[Iterable[str]] = None,
) -> UniverseDerivation:
    """Run the rule over the whole frame against one screen artifact.

    Every frame member is evaluated, including the ones with no disclosure at
    all, so the derivation records why each ticker is out rather than only
    listing the ones that are in.
    """
    frame_set = frozenset(t.upper() for t in
                          (frame if frame is not None else screening_frame()))
    refusals: list[str] = []

    edges = screen.get("edges")
    if not isinstance(edges, list):
        refusals.append("screen has no `edges` list")
        edges = []

    missing_fields: dict[str, int] = {}
    for e in edges:
        if not isinstance(e, Mapping):
            refusals.append("screen contains a non-mapping edge")
            break
        for f in REQUIRED_EDGE_FIELDS:
            if f not in e:
                missing_fields[f] = missing_fields.get(f, 0) + 1
    for f, n in sorted(missing_fields.items()):
        refusals.append(
            f"{n} screened edge(s) do not carry `{f}`. This screen predates the "
            "field and cannot be evaluated -- an absent denominator would be "
            "read as a denial and produce an empty universe that looks like a "
            "finding. Re-run the screen.")

    outside = sorted({str(e.get("reporting_company", "")).upper()
                      for e in edges if isinstance(e, Mapping)} - frame_set)
    if outside:
        refusals.append(
            f"screen covers tickers outside the frame: {', '.join(outside)}")

    attempted = (screen.get("coverage") or {}).get("companies_attempted")
    if attempted is not None and attempted != len(frame_set):
        refusals.append(
            f"screen attempted {attempted} companies; the frame has "
            f"{len(frame_set)}. The rule must be evaluated over the whole "
            "frame or not at all.")

    quals = tuple(
        evaluate_ticker(t, edges, cutoff_date=cutoff_date, frame=frame_set)
        for t in sorted(frame_set)
    )
    members = tuple(q.ticker for q in quals if q.qualifies)

    return UniverseDerivation(
        rule_id=RULE_ID,
        cutoff_date=cutoff_date,
        # Fail closed: a derivation that could not be trusted yields nothing.
        members=() if refusals else members,
        qualifications=quals,
        refusals=tuple(refusals),
        evidence={
            "frame_size": len(frame_set),
            "frame": sorted(frame_set),
            "screen_generated_at_utc": screen.get("generated_at_utc"),
            "screened_edges": len(edges),
            "threshold_pct": CONCENTRATION_THRESHOLD_PCT,
            "required_basis": REQUIRED_BASIS,
            "evaluated": len(quals),
            "qualified": len(members),
        },
    )


def format_report(d: UniverseDerivation) -> str:
    lines = ["=== HYP-04 anchor universe: rule evaluation ===",
             f"  rule            {d.rule_id}",
             f"  cutoff          {d.cutoff_date}",
             f"  frame           {d.evidence.get('frame_size')} tickers",
             f"  screened edges  {d.evidence.get('screened_edges')}",
             f"  derived         {d.derived}"]
    if d.refusals:
        lines.append("\n  REFUSED:")
        lines += [f"    * {r}" for r in d.refusals]
        lines.append("\n  No universe is produced by a refused derivation.")
        return "\n".join(lines)

    lines.append(f"\n  MEMBERS ({len(d.members)}): "
                 + (", ".join(d.members) if d.members else "(none)"))
    for q in d.qualifications:
        if not q.qualifies:
            continue
        for e in q.evidence["qualifying_disclosures"]:
            lines.append(
                f"    {q.ticker} -> {e['counterparty']}  {e['concentration_pct']}% "
                f"of {e['concentration_basis']}  ({e['as_of_date']}, "
                f"{e['accession']})")

    near = [q for q in d.qualifications
            if not q.qualifies and q.evidence.get("near_misses")]
    if near:
        lines.append(f"\n  SCREENED BUT NOT QUALIFYING ({len(near)}):")
        for q in near:
            for e in q.evidence["near_misses"]:
                if not e.get("counterparty"):
                    continue
                lines.append(f"    {q.ticker} -> {e['counterparty']}  "
                             f"{e['concentration_pct']}% of "
                             f"{e['concentration_basis']}")
                for w in e["denials"]:
                    lines.append(f"        {w}")
    lines.append("\n  Membership says who MAY be an anchor. It creates no "
                 "eligible anchor event,")
    lines.append("  opens no display-gate condition, and is not evidence "
                 "about supply-chain transmission.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Evaluate the HYP-04 anchor-universe rule over an EDGAR "
                    "concentration screen. Reads; writes nothing.")
    ap.add_argument("--screen", required=True,
                    help="path to an EDGAR candidate-linkage screen JSON")
    ap.add_argument("--cutoff", required=True, help="YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="emit the derivation as JSON")
    a = ap.parse_args(argv)

    screen = json.loads(Path(a.screen).read_text(encoding="utf-8-sig"))
    d = derive_universe(screen, cutoff_date=a.cutoff)
    print(json.dumps(d.as_dict(), indent=2) if a.json else format_report(d))
    return 0 if d.derived else 1


if __name__ == "__main__":
    sys.exit(main())
