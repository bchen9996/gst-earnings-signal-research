#!/usr/bin/env python3
"""How many anchor events the PEER side could reach -- HYP-04's peer ceiling.

The anchor side is finished: 324 of 342 calendar events carry a well-measured
shock. Every remaining blocker is on the peer side, and until now the project
has described that side with an ordering rather than a number: "the peer price
source is the sole remaining blocker."

This module replaces that sentence with a measurement, the same way
`anchor_calendar` replaced the member-years estimate with 342.

=== THE TWO NUMBERS, AND WHY BOTH ARE PUBLISHED ===

MEASURED. Run the real join -- `linkage_resolution.resolve_from_curated_map`
over the real calendar and the real shocks -- and report what it returns. Today
that is zero eligible pairs, every one denied on P5, because no peer price
source exists. It is the honest state and it is uninformative on its own: P5
denies everything, so nothing behind P5 is visible.

CEILING. Run the same join with peer price availability supplied as a STATED
HYPOTHETICAL, so P5 stops masking P1 and P3. What comes back is the most the
curated map could ever yield, whatever a price source did later.

The ceiling is a SAMPLE-SIZE FEASIBILITY count, the same category as the 342
anchor events and the options-coverage audit. It is not a result, it is not
eligibility, and it says nothing about transmission. `CeilingReport` therefore
has no `eligible` field and never will; the word is reserved for
`pair_eligibility`, which is the only module entitled to use it.

=== WHY THE CEILING WAS WORTH COMPUTING ===

Because it re-orders the blockers, and the previous order was wrong.

The curated map holds two rows. One of them, PKG -> ODP, contributes NOTHING:
PKG is not in the anchor universe, so no calendar event has PKG as its anchor
and that edge is never even evaluated. ODP's price failure is the measured
instance behind `peer_price_data_policy` -- and it sits on an edge that cannot
supply a single pair.

What is left is MCK -> CVS. That caps the whole hypothesis at the MCK events
after 2013-05-07 that carry a shock. A perfect, survivorship-bias-free price
source bought tomorrow would not raise it by one event.

So curation binds first, and prices bind second. Work ordered the other way
round would buy a data source that the map cannot use.

=== THE WORKLIST, AND THE LINE IT DOES NOT CROSS ===

`build_worklist` ranks the EDGAR review queue's candidate counterparties by how
many anchor events each could add if it were curated. That is derivable without
touching linkage: the count comes entirely from the ANCHOR side -- this
anchor's events, after this filing date, with a computed shock.

It resolves a counterparty NAME to a ticker only by EXACT match against SEC's
own `company_tickers.json`, after normalisation that strips corporate suffixes
and nothing else. Ambiguous names, self-links and near-misses are written
UNRESOLVED and left for the curator. No fuzzy matching, no scores: a wrong
ticker is fabricated linkage wearing a number, and it fails silently.

**A resolved name is not a curated edge, and this module cannot make one.** The
worklist's columns deliberately differ from `curated_linkage.REQUIRED_FIELDS`,
so `load_curated_linkage` rejects the worklist on its header rather than
loading it as a map. `refuse_if_curated_schema` enforces that at build time as
well, because the check is worth having in both directions.

=== EVERY RESOLUTION CARRIES A LINEAGE HAZARD ===

The SEC ticker map describes companies as they are TODAY. The counterparty
names come from filings made years or decades ago. Matching one to the other
answers "is there a company with this name now?", never "is it the same
company that was named then?"

This project has already refused that inference twice, on exactly these
grounds: Caremark RX was rejected for MCK and OfficeMax for PKG, both because a
merger is not a rename. So every resolved row carries
`requires_lineage_review=True` and the years elapsed since the disclosure, and
no row is ever promoted automatically.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .anchor_shock import AnchorShock
from .curated_linkage import REQUIRED_FIELDS as CURATED_REQUIRED_FIELDS
from .linkage_resolution import ResolvedPanel, resolve_from_curated_map

PEER_CEILING_RULE_ID = "HYP04-PEER-CEILING-RULE-v1"

#: The status a shock row must carry to count toward the ceiling. A denied
#: anchor event cannot support a peer measurement, so it is not in any ceiling.
SHOCK_COMPUTED = "shock_computed"

#: Worklist columns. DELIBERATELY not `curated_linkage.REQUIRED_FIELDS`: the
#: peer column is named `candidate_peer_ticker`, and `curated_by`,
#: `review_status`, `relationship_type` and `confidence` are absent, because
#: this file makes none of those claims. The difference is the safety property
#: -- see `refuse_if_curated_schema`.
WORKLIST_FIELDS: tuple[str, ...] = (
    "anchor_ticker",
    "candidate_peer_ticker",
    "counterparty_name_as_filed",
    "normalized_name",
    "resolution",
    "resolution_basis",
    "sec_title",
    "sec_cik",
    "requires_lineage_review",
    "earliest_disclosing_filing_date",
    "earliest_accession",
    "filings_naming_it",
    "years_since_disclosure",
    "max_anchor_events",
    "share_of_floor_pct",
)

RESOLVED = "resolved"
UNRESOLVED_NO_MATCH = "UNRESOLVED_no_exact_match"
UNRESOLVED_AMBIGUOUS = "UNRESOLVED_ambiguous"
UNRESOLVED_SELF_LINK = "UNRESOLVED_self_link"

RESOLUTION_BASIS = "exact_match_on_normalised_sec_company_title"

#: Corporate-form tokens stripped from both sides before comparison. This list
#: is deliberately short and structural. It contains no industry words and no
#: company-specific terms, because every entry is a chance to collapse two
#: genuinely different companies onto one normalised form.
NAME_SUFFIXES: frozenset[str] = frozenset({
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
    "LTD", "LIMITED", "LLC", "LP", "PLC", "SA", "NV", "AG", "THE",
    "HOLDING", "HOLDINGS", "GROUP",
})

_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")


class CuratedSchemaLeak(RuntimeError):
    """The worklist grew columns that would let it pass as a curated map."""


def refuse_if_curated_schema(fields: Iterable[str]) -> None:
    """Refuse a worklist whose columns could be read as a curated linkage map.

    The worklist is a REVIEW QUEUE ranked by opportunity. If its header ever
    satisfied `curated_linkage.REQUIRED_FIELDS`, the loader would accept it and
    every candidate name in it would become an edge -- a whole map of linkage
    nobody curated, arriving through a column rename.

    So the two schemas are kept provably disjoint. This is checked here rather
    than only in the tests because the failure it prevents is silent: a map
    that loads is a map that runs.
    """
    names = set(fields)
    missing = [f for f in CURATED_REQUIRED_FIELDS if f not in names]
    if not missing:
        raise CuratedSchemaLeak(
            "the worklist header now satisfies every field in "
            "curated_linkage.REQUIRED_FIELDS, so load_curated_linkage would "
            "accept it as a curated map. It is a review queue: no row in it "
            "has been curated, and no relationship_type, confidence or "
            "reviewer is claimed. Rename the offending columns."
        )


def normalize_company_name(name: str) -> str:
    """Upper-case, drop punctuation, strip leading/trailing corporate forms.

    Only structural tokens are removed, and only from the ends. Nothing in the
    middle of a name is touched, so 'Micro-Star' and 'Micro Star' agree while
    'Atlantic' and 'Atlantic Semiconductor' stay apart.
    """
    s = (name or "").upper().replace("&", " AND ")
    s = _NON_ALNUM.sub(" ", s)
    toks = [t for t in s.split() if t]
    while toks and toks[-1] in NAME_SUFFIXES:
        toks.pop()
    while toks and toks[0] in NAME_SUFFIXES:
        toks.pop(0)
    return " ".join(toks)


@dataclass(frozen=True)
class Resolution:
    """One counterparty name held against SEC's ticker map. Never an edge."""

    ticker: str = ""
    status: str = UNRESOLVED_NO_MATCH
    sec_title: str = ""
    sec_cik: str = ""
    candidates: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED and bool(self.ticker)


def build_name_index(
    ticker_map: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Normalised SEC company title -> every entry sharing it.

    A list, not a single entry: several SEC filers normalise to one name (a
    company with two share classes, most often). Collapsing them would pick a
    ticker arbitrarily, so they are all kept and the ambiguity is reported.
    """
    idx: dict[str, list[dict[str, str]]] = {}
    for v in ticker_map.values():
        title = str(v.get("title", ""))
        tick = str(v.get("ticker", "")).upper()
        cik = str(v.get("cik_str", ""))
        if not tick:
            continue
        idx.setdefault(normalize_company_name(title), []).append(
            {"ticker": tick, "title": title, "cik": cik})
    return idx


def resolve_counterparty(
    name: str,
    index: Mapping[str, list[dict[str, str]]],
    *,
    anchor_ticker: str,
) -> Resolution:
    """Exact normalised match, or an honest UNRESOLVED. Never a guess.

    A name matching the anchor's own ticker is UNRESOLVED rather than resolved,
    because a self-link is not a supply-chain relationship and `evaluate_pair`
    would deny it on P2 anyway. Reporting it as unresolved keeps the reason
    visible to the curator instead of burying it in a downstream denial.
    """
    norm = normalize_company_name(name)
    hits = index.get(norm) or []
    if not hits:
        return Resolution(status=UNRESOLVED_NO_MATCH)

    tickers = sorted({h["ticker"] for h in hits})
    if len(tickers) > 1:
        return Resolution(status=UNRESOLVED_AMBIGUOUS, candidates=tuple(tickers))

    hit = hits[0]
    if hit["ticker"] == (anchor_ticker or "").strip().upper():
        return Resolution(status=UNRESOLVED_SELF_LINK,
                          candidates=(hit["ticker"],))
    return Resolution(ticker=hit["ticker"], status=RESOLVED,
                      sec_title=hit["title"], sec_cik=hit["cik"])


@dataclass(frozen=True)
class CandidateRow:
    """One review-queue counterparty, ranked by the events it could add."""

    anchor_ticker: str
    counterparty: str
    normalized_name: str
    resolution: Resolution
    as_of_date: str
    accession: str
    filings_naming_it: int
    event_ids: tuple[str, ...] = ()

    @property
    def max_anchor_events(self) -> int:
        return len(self.event_ids)

    def years_since_disclosure(self, today: date) -> int:
        try:
            y, m, d = (int(x) for x in self.as_of_date.split("-"))
        except ValueError:
            return -1
        return (today - date(y, m, d)).days // 365

    def as_row(self, *, today: date, floor: Optional[int]) -> dict[str, Any]:
        r = self.resolution
        share = ("" if not floor else
                 round(100.0 * self.max_anchor_events / floor, 1))
        status = r.status
        if r.candidates and not r.resolved:
            status = status + ":" + "|".join(r.candidates)
        return {
            "anchor_ticker": self.anchor_ticker,
            "candidate_peer_ticker": r.ticker,
            "counterparty_name_as_filed": self.counterparty,
            "normalized_name": self.normalized_name,
            "resolution": status,
            "resolution_basis": RESOLUTION_BASIS if r.resolved else "",
            "sec_title": r.sec_title,
            "sec_cik": r.sec_cik,
            # Always true for a resolved row, never a judgement this module
            # makes. The SEC map describes today; the filing described then.
            "requires_lineage_review": "yes" if r.resolved else "",
            "earliest_disclosing_filing_date": self.as_of_date,
            "earliest_accession": self.accession,
            "filings_naming_it": self.filings_naming_it,
            "years_since_disclosure": self.years_since_disclosure(today),
            "max_anchor_events": self.max_anchor_events,
            "share_of_floor_pct": share,
        }


@dataclass(frozen=True)
class CeilingReport:
    """The peer side's reach. A FEASIBILITY count, never an eligibility count.

    There is no `eligible` field here on purpose. `pair_eligibility` decides
    eligibility and nothing else may claim it, so the most this type can say is
    how many anchor events COULD carry a peer if every unresolved thing
    resolved favourably.
    """

    measured_pairs: int = 0
    measured_events: int = 0
    measured_denials: dict[str, int] = field(default_factory=dict)
    ceiling_pairs: int = 0
    ceiling_events: int = 0
    ceiling_denials: dict[str, int] = field(default_factory=dict)
    ceiling_by_anchor: dict[str, int] = field(default_factory=dict)
    curated_peers: tuple[str, ...] = ()
    peers_never_evaluated: tuple[str, ...] = ()
    floor: Optional[int] = None
    rule_id: str = PEER_CEILING_RULE_ID

    @property
    def reaches_floor(self) -> bool:
        """Whether the CEILING reaches the registered floor. Not a gate input."""
        return self.floor is not None and self.ceiling_events >= self.floor

    @property
    def shortfall(self) -> Optional[int]:
        if self.floor is None:
            return None
        return max(0, self.floor - self.ceiling_events)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "measured": {
                "pairs_eligible": self.measured_pairs,
                "anchor_events_with_a_peer": self.measured_events,
                "denials_by_code": dict(self.measured_denials),
            },
            "ceiling_peer_prices_assumed": {
                "pairs": self.ceiling_pairs,
                "anchor_events_with_a_peer": self.ceiling_events,
                "denials_by_code": dict(self.ceiling_denials),
                "by_anchor": dict(self.ceiling_by_anchor),
            },
            "curated_peers": list(self.curated_peers),
            "peers_never_evaluated": list(self.peers_never_evaluated),
            "registered_floor": self.floor,
            "ceiling_reaches_floor": self.reaches_floor,
            "shortfall_against_floor": self.shortfall,
        }


def shocks_from_rows(rows: Iterable[Mapping[str, str]]) -> dict[str, AnchorShock]:
    """Rebuild AnchorShock objects from a published shock CSV.

    Only `shock_computed` rows become shocks. A denied row is left out
    entirely rather than becoming a shock of zero -- `evaluate_pair` denies a
    missing shock on P1, which is the correct treatment, and a zero would be a
    measurement nobody made.
    """
    out: dict[str, AnchorShock] = {}
    for r in rows:
        if (r.get("status") or "") != SHOCK_COMPUTED:
            continue
        try:
            out[r["event_id"]] = AnchorShock(
                event_id=r["event_id"],
                anchor_ticker=r["anchor_ticker"],
                session=r["attributed_session"],
                anchor_return=float(r["anchor_return"]),
                benchmark_return=float(r["benchmark_return"]),
                excess_return=float(r["excess_return"]),
                shock=float(r["shock"]),
            )
        except (KeyError, ValueError, TypeError):
            continue                      # unparseable row is not a shock
    return out


def events_from_calendar(
    rows: Iterable[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Calendar rows -> the anchor-event shape `resolve_from_curated_map` takes.

    `event_date` is the RELEASE date, not the attributed session. P3 asks
    whether an observer at the event could have known the relationship, and the
    release is when the event happened. For an AMC release the attributed
    session is the next day, so using it would widen the point-in-time window
    by one day in the permissive direction. The conservative date is the right
    one for a rule that exists to keep hindsight out.
    """
    return [{"event_id": r["event_id"], "anchor": r["anchor_ticker"],
             "event_date": r["release_date"]} for r in rows]


def _by_code(panel: ResolvedPanel) -> dict[str, int]:
    return panel.denial_reasons()


def measure_ceiling(
    events: list[dict[str, Any]],
    shocks: Mapping[str, AnchorShock],
    *,
    map_path: Path,
    curated_peers: Iterable[str],
    floor: Optional[int] = None,
) -> CeilingReport:
    """Run the real join twice: as it stands, and with prices assumed.

    The second run supplies `peer_history` as a stated hypothetical so P5 stops
    masking P1 and P3. It is the only place this module departs from measured
    inputs, it is confined to one argument, and what it produces is labelled a
    ceiling everywhere it appears.
    """
    shock_map = dict(shocks)
    peers = tuple(sorted({p.strip().upper() for p in curated_peers if p.strip()}))

    measured = resolve_from_curated_map(events, map_path=map_path,
                                        anchor_shock=shock_map)
    ceiling = resolve_from_curated_map(
        events, map_path=map_path, anchor_shock=shock_map,
        peer_history={p: True for p in peers})

    by_anchor: dict[str, int] = {}
    for ev in ceiling.anchor_events:
        if ev.get("peers"):
            a = str(ev.get("anchor", ""))
            by_anchor[a] = by_anchor.get(a, 0) + 1

    # A peer that never appears in ANY pair evaluation was not denied -- it was
    # never asked about, because its anchor has no calendar events. That is a
    # different fact from a denial and the denial profile cannot show it.
    seen = {p.peer_ticker.upper() for p in ceiling.denied}
    for ev in ceiling.anchor_events:
        seen.update(str(x).upper() for x in ev.get("peers") or ())
    never = tuple(p for p in peers if p not in seen)

    return CeilingReport(
        measured_pairs=measured.pairs_eligible,
        measured_events=measured.n_events_with_peers,
        measured_denials=_by_code(measured),
        ceiling_pairs=ceiling.pairs_eligible,
        ceiling_events=ceiling.n_events_with_peers,
        ceiling_denials=_by_code(ceiling),
        ceiling_by_anchor=by_anchor,
        curated_peers=peers,
        peers_never_evaluated=never,
        floor=floor,
    )


def build_worklist(
    queue_tickers: Iterable[Mapping[str, Any]],
    *,
    calendar_rows: list[Mapping[str, str]],
    shock_rows: list[Mapping[str, str]],
    name_index: Mapping[str, list[dict[str, str]]],
    anchors: Optional[Iterable[str]] = None,
) -> list[CandidateRow]:
    """Rank review-queue counterparties by the anchor events each could add.

    The count is ANCHOR-SIDE ONLY: this anchor's calendar events that carry a
    computed shock and fall strictly after the earliest filing that disclosed
    the counterparty. It needs no peer ticker, no peer prices and no curation,
    which is exactly why it can be derived today.

    It is a CEILING for the candidate. Curating the edge could only lower it --
    a rejected as_of moves the date later, and a rejected relationship removes
    the row.
    """
    refuse_if_curated_schema(WORKLIST_FIELDS)

    ok_events: dict[str, list[Mapping[str, str]]] = {}
    computed = {r["event_id"] for r in shock_rows
                if (r.get("status") or "") == SHOCK_COMPUTED}
    for r in calendar_rows:
        if r["event_id"] in computed:
            ok_events.setdefault(r["anchor_ticker"], []).append(r)

    want = ({a.strip().upper() for a in anchors} if anchors is not None
            else set(ok_events))

    out: list[CandidateRow] = []
    for t in queue_tickers:
        anchor = str(t.get("ticker", "")).strip().upper()
        if anchor not in want:
            continue
        for nc in (t.get("named_counterparties") or []):
            name = str(nc.get("counterparty", ""))
            as_of = str(nc.get("earliest_filing_date", ""))
            ids = tuple(r["event_id"] for r in ok_events.get(anchor, [])
                        if r["release_date"] > as_of)
            out.append(CandidateRow(
                anchor_ticker=anchor,
                counterparty=name,
                normalized_name=normalize_company_name(name),
                resolution=resolve_counterparty(name, name_index,
                                                anchor_ticker=anchor),
                as_of_date=as_of,
                accession=str(nc.get("earliest_accession", "")),
                filings_naming_it=int(nc.get("filings_naming_it") or 0),
                event_ids=ids,
            ))

    out.sort(key=lambda r: (-r.max_anchor_events, r.anchor_ticker,
                            r.counterparty))
    return out


def union_events(rows: Iterable[CandidateRow]) -> set[str]:
    """Distinct anchor events covered by a set of candidates.

    Summing `max_anchor_events` would double-count heavily -- most candidates
    on one anchor cover overlapping stretches of the same event list -- so the
    only honest aggregate is the union.
    """
    s: set[str] = set()
    for r in rows:
        s.update(r.event_ids)
    return s


def write_worklist_csv(rows: list[CandidateRow], path: Path, *,
                       today: date, floor: Optional[int]) -> int:
    refuse_if_curated_schema(WORKLIST_FIELDS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(WORKLIST_FIELDS),
                           lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r.as_row(today=today, floor=floor))
    return len(rows)


def rule_description() -> dict[str, Any]:
    """What this rule is, for an artifact to DECLARE rather than restate."""
    return {
        "rule_id": PEER_CEILING_RULE_ID,
        "what_the_ceiling_is": (
            "The most anchor events the peer side could reach if every "
            "unresolved question resolved favourably. A sample-size "
            "feasibility count, the same category as the 342 anchor events."),
        "what_the_ceiling_is_not": (
            "Eligibility. No pair here has passed pair_eligibility, the "
            "ceiling run supplies peer price availability as a stated "
            "hypothetical rather than a measurement, and CeilingReport has no "
            "eligible field."),
        "measured_vs_ceiling": (
            "Both are published. The measured join is the honest state and "
            "returns zero, all denied on P5. The ceiling exists because P5 "
            "denying everything hides whether P1 and P3 would have denied it "
            "too."),
        "worklist_counts_are_anchor_side_only": (
            "A candidate's count is this anchor's shock-carrying events after "
            "the earliest filing that disclosed the counterparty. No peer "
            "ticker or price is involved, which is why it is derivable now."),
        "name_resolution": RESOLUTION_BASIS,
        "name_resolution_refuses": (
            "Fuzzy matching and scored matching. A wrong ticker is fabricated "
            "linkage wearing a number and it fails silently. Ambiguous names, "
            "self-links and near-misses are left UNRESOLVED for the curator."),
        "every_resolution_needs_lineage_review": (
            "SEC's ticker map describes companies as they are today; the names "
            "come from filings made years earlier. Caremark RX and OfficeMax "
            "were both rejected on exactly this ground -- a merger is not a "
            "rename -- so no row is promoted automatically."),
        "not_a_curated_map": (
            "The worklist's columns are provably disjoint from "
            "curated_linkage.REQUIRED_FIELDS, so load_curated_linkage refuses "
            "it on the header. refuse_if_curated_schema enforces the same "
            "thing at build time."),
        "opens_no_gate": (
            "The display gate is CLOSED, C4 MET, four denials. C2 counts "
            "eligible anchor events and this supplies none; C2 and C3 move "
            "together or not at all."),
    }
