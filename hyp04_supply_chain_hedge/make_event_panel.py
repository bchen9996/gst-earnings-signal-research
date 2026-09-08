#!/usr/bin/env python3
"""The real-data panel assembler -- HYP-04's first mechanically derived count.

Registry v1.11 section 10 lists this as the top open item:

    "The panel assembler, which must consume the per-pair coverage path.
     Measured: per-pair gives 215 events, the per-peer unit gives 161 --
     below the floor -- because one uncollectable CVS event marks CVS
     unavailable for all 54 of its events."

Every input already exists. The anchor calendar carries 342 events, 324 of them with a
computed shock. The curated map reaches seven edges. All 13,056 peer closes are
collected and load clean. Nothing had joined them, so C2's denial has been
"eligible event count is unknown / NOT MECHANICALLY DERIVABLE" -- a statement
about missing machinery, not about the data.

This is that machinery. It derives the count; it does not decide anything.

=== IT REPORTS BOTH UNITS, AND SAYS WHICH ONE THE REGISTRY PICKED ===

Registry v1.11: "Peer-side price data availability is a MEASURABILITY question,
reported per pair. It is never a MEMBERSHIP question."

The per-pair unit is therefore the registered one, and it was registered on
2026-09-02 -- before this assembler existed and with no knowledge of what it
would return. Both units are computed and both are published anyway, because
the difference between them is large enough (54 events, measured) to decide
whether the floor is cleared, and a reader is entitled to see the number that
choice is worth rather than take it on trust.

=== IT OPENS NO GATE ===

Deriving a count is not freezing one. C2 needs the count, C3 needs a freeze
record naming an analysis lock and a commit, and C5 needs the linkage
provenance to be non-placeholder. This module supplies the first and the
material for the third. It does not write a freeze, and `evaluate_gate()` with
no arguments is unchanged by anything here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from . import sessions as sessions_mod
from .artifacts import newest_in
from .constants import HORIZON_GRID
from .linkage_resolution import freeze_record_fields, resolve_from_curated_map
from .peer_ceiling import events_from_calendar, shocks_from_rows
from .peer_returns import (
    build_series,
    coverage_for_event,
    load_peer_closes,
    peer_history_map,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"
PEER_CLOSES_DIR = LSE / "HYP04_PEER_CLOSES_REQUEST"

AS_OF = "2026-09-08"
OUT_JSON = LSE / f"HYP04_EVENT_PANEL_{AS_OF}.json"

#: Padding around the observed date range when building the session index. The
#: reference window reaches back before the earliest event and the horizon
#: reaches past the latest, so an index spanning only the observed dates would
#: deny the edge events for the wrong reason.
INDEX_PAD_DAYS = 200

#: The registered eligible-event floor. Declared here because
#: `make_anchor_calendar`, `make_anchor_shocks` and `make_peer_ceiling` each
#: declare their own copy and none of them is the canonical home. A fourth
#: silent copy would be one more place for it to drift, so
#: `assert_floor_agreement` makes disagreement a refusal instead.
MINIMUM_ELIGIBLE_EVENTS = 193


def assert_floor_agreement() -> dict[str, int]:
    """Refuse if the repository's copies of the floor have drifted apart.

    A count compared against the wrong floor is worse than no count: it reads
    as a verdict.
    """
    from . import make_anchor_calendar, make_anchor_shocks, make_peer_ceiling
    seen = {
        "make_event_panel": MINIMUM_ELIGIBLE_EVENTS,
        "make_anchor_calendar": make_anchor_calendar.MINIMUM_ELIGIBLE_EVENTS,
        "make_anchor_shocks": make_anchor_shocks.MINIMUM_ELIGIBLE_EVENTS,
        "make_peer_ceiling": make_peer_ceiling.MINIMUM_ELIGIBLE_EVENTS,
    }
    if len(set(seen.values())) != 1:
        raise PanelError(
            f"the registered floor disagrees across modules: {seen}. "
            "Reconcile them before deriving a count against any of them.")
    return seen


class PanelError(RuntimeError):
    """A precondition does not hold.

    PanelError, never a bare `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _require(path: Optional[Path], what: str) -> Path:
    if path is None or not path.is_file():
        raise PanelError(f"no {what} on disk; the panel cannot be assembled")
    return path


def _inputs() -> dict[str, Path]:
    cal = _require(newest_in(LSE, "HYP04_ANCHOR_EVENT_CALENDAR_*.csv"),
                   "anchor-event calendar")
    shocks = _require(newest_in(LSE, "HYP04_ANCHOR_SHOCKS_*.csv"),
                      "anchor-shock artifact")
    cmap = _require(newest_in(LSE, "HYP04_Linkage_Map_v*.csv"),
                    "curated linkage map")
    if not PEER_CLOSES_DIR.is_dir():
        raise PanelError(f"no peer-closes directory at {PEER_CLOSES_DIR}")
    return {"calendar": cal, "shocks": shocks, "curated_map": cmap}


def _load_peer_series(session_index: list[date]) -> tuple[dict, dict]:
    series: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    files = sorted(PEER_CLOSES_DIR.glob("*_closes_REQUEST.csv"))
    if not files:
        raise PanelError(f"no peer closes files in {PEER_CLOSES_DIR}")
    for f in files:
        # Third value is the file's sha256, NOT a ticker. The ticker comes
        # from the rows themselves, and every row must agree on it -- a file
        # mixing tickers would silently key one peer's series under another's.
        obs, rejects, digest = load_peer_closes(f)
        # Rejects FIRST. `load_peer_closes` drops a row with a blank close
        # rather than returning it with close=None, so an uncollected request
        # file arrives as zero observations and N rejects -- checking a
        # "filled == 0" count after this point would be unreachable code, which
        # is worse than no check because it reads as one.
        if rejects:
            raise PanelError(
                f"{f.name} has {len(rejects)} unparseable rows. If they are "
                "blank closes the file is still a REQUEST: collect it before "
                "assembling a panel. A panel is not built over rows that did "
                "not parse.")
        tickers = {o.ticker for o in obs if o.ticker}
        if len(tickers) != 1:
            raise PanelError(
                f"{f.name} names {sorted(tickers) or 'no'} ticker(s); exactly "
                "one is required")
        ticker = tickers.pop()
        filled = sum(1 for o in obs if o.close is not None)
        s = build_series(obs, ticker=ticker, sessions=session_index)
        series[ticker] = s
        provenance[ticker] = {
            "file": f.name,
            "sha256": digest,
            "rows_seen": len(obs),
            "rows_filled": filled,
            "rows_rejected": len(rejects),
            "off_calendar_dates": len(s.off_calendar_dates),
            "finite_returns": s.n_finite,
        }
    return series, provenance


def _session_index(attributed: dict[str, date],
                   peer_files: list[Path]) -> tuple[list[date], dict]:
    seen: list[date] = list(attributed.values())
    for f in peer_files:
        for r in _rows(f):
            d = (r.get("session_date") or "").strip()
            if d:
                try:
                    seen.append(date.fromisoformat(d))
                except ValueError:
                    continue
    if not seen:
        raise PanelError("no dates found to build a session index from")
    first = min(seen) - timedelta(days=INDEX_PAD_DAYS)
    last = max(seen) + timedelta(days=INDEX_PAD_DAYS)
    idx = sessions_mod.xnys_sessions(first, last)
    return idx, {
        "calendar_id": sessions_mod.calendar_id(),
        "first": idx[0].isoformat(),
        "last": idx[-1].isoformat(),
        "n_sessions": len(idx),
        "pad_days": INDEX_PAD_DAYS,
        "verified_against_authoritative": True,
    }


def _attributed_sessions(shock_rows: list[dict[str, str]]) -> dict[str, date]:
    """event_id -> the session the response is measured from.

    Taken from the shock artifact, which already resolved BMO/AMC. Deriving it
    again here would be a second rule that could disagree with the first.
    """
    out: dict[str, date] = {}
    for r in shock_rows:
        s = (r.get("attributed_session") or "").strip()
        eid = (r.get("event_id") or "").strip()
        if not s or not eid:
            continue
        try:
            out[eid] = date.fromisoformat(s)
        except ValueError:
            continue
    return out


def _coverage(series: dict, events: list[dict], edges_by_anchor: dict,
              attributed: dict[str, date], pos: dict[date, int],
              ) -> tuple[dict, dict, list]:
    """Per-pair P5 answers, derived from the collected closes themselves."""
    by_pair: dict[tuple[str, str], bool] = {}
    detail: list[dict[str, Any]] = []
    unresolved: dict[str, int] = {}
    h = max(HORIZON_GRID)

    for ev in events:
        eid = ev["event_id"]
        anchor = str(ev["anchor"]).upper()
        sess = attributed.get(eid)
        if sess is None:
            unresolved["no_attributed_session"] = \
                unresolved.get("no_attributed_session", 0) + 1
            continue
        day = pos.get(sess)
        if day is None:
            unresolved["session_not_in_index"] = \
                unresolved.get("session_not_in_index", 0) + 1
            continue
        for peer in edges_by_anchor.get(anchor, ()):
            s = series.get(peer)
            if s is None:
                # No closes file for this peer. UNKNOWN, so it is left out of
                # the map entirely and P5 denies it. Never recorded as False,
                # which would read as "checked and absent".
                unresolved["peer_has_no_closes_file"] = \
                    unresolved.get("peer_has_no_closes_file", 0) + 1
                continue
            cov = coverage_for_event(s, event_id=eid, anchor_day=day,
                                     max_horizon=h)
            by_pair[(eid, peer)] = cov.sufficient
            if not cov.sufficient:
                detail.append(cov.as_dict())
    return by_pair, unresolved, detail


def build(*, out_json: Path = OUT_JSON, force: bool = False) -> dict[str, Any]:
    if out_json.exists() and not force:
        raise PanelError(
            f"{out_json.name} exists; refusing to overwrite a dated artifact "
            "-- delete it deliberately first.")

    floors = assert_floor_agreement()
    paths = _inputs()
    cal_rows = _rows(paths["calendar"])
    shock_rows = _rows(paths["shocks"])
    events = events_from_calendar(cal_rows)
    shocks = shocks_from_rows(shock_rows)
    attributed = _attributed_sessions(shock_rows)

    peer_files = sorted(PEER_CLOSES_DIR.glob("*_closes_REQUEST.csv"))
    idx, idx_prov = _session_index(attributed, peer_files)
    pos = {d: i for i, d in enumerate(idx)}
    series, peer_prov = _load_peer_series(idx)

    # Which peers each anchor reaches, read from the curated map through the
    # same loader the resolver uses, so the two cannot disagree.
    from .curated_linkage import load_curated_linkage
    res = load_curated_linkage(paths["curated_map"])
    if not res.ok:
        raise PanelError(
            f"{paths['curated_map'].name} did not load cleanly "
            f"({res.rows_rejected} rows rejected); a panel is not assembled "
            "over a map that failed its own validation.")
    edges_by_anchor: dict[str, list[str]] = {}
    for e in res.edges:
        edges_by_anchor.setdefault(e.anchor_ticker.upper(), []).append(
            e.peer_ticker.upper())

    by_pair, unresolved, short_detail = _coverage(
        series, events, edges_by_anchor, attributed, pos)

    # The per-peer unit, for the comparison the registry's choice is worth.
    #
    # SCOPING MATTERS AND IT IS NOT OBVIOUS. `peer_history_map` marks a peer
    # available only if it covers EVERY event in the list it is given, so the
    # list decides the answer. Ranged over ALL events, a peer is condemned by
    # events P1 or P3 would deny anyway -- AAPL is checked against JBL events
    # from 2003, a decade before its edge's as_of date. Ranged over the events
    # that already survive P1 and P3, the unit is isolated and only the price
    # question remains. The second is the like-for-like comparison against the
    # per-pair figure; the first is reported too so the scoping is visible
    # rather than buried in a helper.
    def _hist(evlist):
        return peer_history_map(series, evlist, max_horizon=max(HORIZON_GRID))

    all_events_scope = [
        {"event_id": ev["event_id"], "anchor": ev["anchor"],
         "peers": edges_by_anchor.get(str(ev["anchor"]).upper(), []),
         "anchor_day": pos.get(attributed.get(ev["event_id"]))}
        for ev in events if attributed.get(ev["event_id"]) in pos
    ]

    panel_pair = resolve_from_curated_map(
        events, map_path=paths["curated_map"], anchor_shock=shocks,
        peer_history_by_pair=by_pair)
    # The ceiling artifact's "peer prices assumed" hypothetical, recomputed
    # here so the two routes can be diffed by event id rather than compared by
    # count. Registry v1.11 section 10 left that reconciliation to this module:
    # "The post-coverage figures agree numerically but are not shown to be the
    # same set."
    assumed = {peer: True for peers in edges_by_anchor.values() for peer in peers}
    panel_assumed = resolve_from_curated_map(
        events, map_path=paths["curated_map"], anchor_shock=shocks,
        peer_history=assumed)

    survivor_scope = [
        {"event_id": str(ev["event_id"]), "peers": ev["peers"],
         "anchor_day": pos.get(attributed.get(str(ev["event_id"])))}
        for ev in panel_assumed.anchor_events
        if ev.get("peers") and attributed.get(str(ev["event_id"])) in pos
    ]
    by_peer = _hist(survivor_scope)
    by_peer_all = _hist(all_events_scope)
    panel_peer = resolve_from_curated_map(
        events, map_path=paths["curated_map"], anchor_shock=shocks,
        peer_history=by_peer)
    panel_peer_all = resolve_from_curated_map(
        events, map_path=paths["curated_map"], anchor_shock=shocks,
        peer_history=by_peer_all)

    def summarize(p) -> dict[str, Any]:
        return {
            "eligible_anchor_events": p.n_events_with_peers,
            "eligible_pairs": p.pairs_eligible,
            "pairs_denied": p.pairs_denied,
            "denials_by_code": p.denial_reasons(),
            "reaches_floor": p.n_events_with_peers >= MINIMUM_ELIGIBLE_EVENTS,
            "shortfall": max(0, MINIMUM_ELIGIBLE_EVENTS - p.n_events_with_peers),
        }

    per_pair = summarize(panel_pair)
    per_peer = summarize(panel_peer)

    def ids(p) -> set[str]:
        return {str(ev.get("event_id")) for ev in p.anchor_events if ev.get("peers")}

    # P1 counts PAIRS, not events, and on this data the two happen to coincide
    # at 18. Deriving both makes the coincidence visible instead of inviting a
    # reader to equate them.
    shockless = [ev for ev in events if ev["event_id"] not in shocks]
    shockless_with_edges = [
        ev for ev in shockless
        if edges_by_anchor.get(str(ev["anchor"]).upper())]
    denial_note = {
        "codes_count_pairs_not_events": True,
        "events_in_calendar": len(events),
        "events_with_a_shock": len(shocks),
        "events_without_a_shock": len(shockless),
        "shockless_events_on_an_anchor_with_edges": len(shockless_with_edges),
        "p1_denied_pairs": per_pair["denials_by_code"].get("P1", 0),
        "p1_pairs_equals_shockless_events_by_coincidence": (
            per_pair["denials_by_code"].get("P1", 0) == len(shockless)
            and len(shockless_with_edges) != len(shockless)),
        "why": (
            "a shockless event generates one denied pair per curated edge on "
            "its anchor, so an anchor with three edges contributes three; the "
            "counts are not interchangeable"),
    }

    only_assumed = sorted(ids(panel_assumed) - ids(panel_pair))
    only_real = sorted(ids(panel_pair) - ids(panel_assumed))
    short_by_event: dict[str, list[str]] = {}
    for c in short_detail:
        short_by_event.setdefault(c["event_id"], []).append(c["peer"])
    reconciliation = {
        "question": (
            "registry v1.11 section 10: the assumed-price route and the "
            "real-coverage route agree numerically but were not shown to be "
            "the same event set"),
        "assumed_prices_events": len(ids(panel_assumed)),
        "assumed_prices_pairs": panel_assumed.pairs_eligible,
        "real_coverage_events": per_pair["eligible_anchor_events"],
        "real_coverage_pairs": per_pair["eligible_pairs"],
        "sets_are_identical": not only_assumed and not only_real,
        "in_assumed_not_in_real": only_assumed,
        "in_real_not_in_assumed": only_real,
        "why": {
            eid: {"peers_short": short_by_event.get(eid, [])}
            for eid in only_assumed
        },
        "resolved": (
            "the two routes differ by exactly the events listed above, each "
            "identified with the peer whose coverage window is empty; the "
            "discrepancy is no longer a bare count difference"),
    }

    doc: dict[str, Any] = {
        "artifact": out_json.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "The first mechanically derived eligible-event count for HYP-04. "
            "Joins the anchor calendar, the anchor shocks, the curated linkage "
            "map and the collected peer closes through pair_eligibility."),
        "what_this_is_not": (
            "Evidence about supply-chain transmission, and not a freeze. No "
            "target value, beta_h, horizon or direction has been computed. A "
            "count of data availability is publishable under the display-gate "
            "convention; what it implies is not."),
        "sources": {k: v.name for k, v in paths.items()}
        | {f"{k}_sha256": _sha256(v) for k, v in paths.items()},
        "session_index": idx_prov,
        "peer_closes": peer_prov,
        "registered_floor": MINIMUM_ELIGIBLE_EVENTS,
        "registered_floor_agrees_across_modules": floors,
        "unit_registered": "per_pair",
        "unit_basis": (
            "Registry v1.11: 'Peer-side price data availability is a "
            "MEASURABILITY question, reported per pair. It is never a "
            "MEMBERSHIP question.' Registered 2026-09-02, before this "
            "assembler existed."),
        # Section 5 point 1 of the display-gates document requires the
        # eligible set to be ENUMERATED mechanically, not merely counted. A
        # count cannot be frozen; a set can.
        "eligible_event_ids": list(
            freeze_record_fields(panel_pair)["eligible_event_ids"]),
        "eligible_event_anchors": {
            str(ev["event_id"]): str(ev["anchor"])
            for ev in panel_pair.anchor_events if ev.get("peers")},
        "per_pair": per_pair,
        "denial_note": denial_note,
        "per_peer": per_peer,
        "per_peer_scoping": {
            "note": (
                "the per-peer unit's answer depends on which events it ranges "
                "over; both scopings are published so the choice is visible"),
            "scoped_to_p1_p3_survivors": per_peer,
            "scoped_to_all_events": summarize(panel_peer_all),
            "availability_survivors": by_peer,
            "availability_all_events": by_peer_all,
        },
        "reconciliation": reconciliation,
        "unit_costs_events": (per_pair["eligible_anchor_events"]
                              - per_peer["eligible_anchor_events"]),
        "pairs_short_on_coverage": len(short_detail),
        "coverage_shortfalls": short_detail,
        "pairs_left_unknown": unresolved,
        "linkage_provenance": panel_pair.provenance.as_dict(),
        "opens_no_gate": (
            "The display gate is CLOSED, C4 MET, four denials. This artifact "
            "supplies the count C2 asks for; it does not supply the freeze C3 "
            "asks for, and C2 and C3 move together or not at all."),
    }
    out_json.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="overwrite the dated artifact")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print without writing")
    args = ap.parse_args(argv)

    if args.dry_run:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            doc = build(out_json=Path(td) / "panel.json", force=True)
    else:
        doc = build(force=args.force)

    pp, pq = doc["per_pair"], doc["per_peer"]
    print(f"session index : {doc['session_index']['n_sessions']} sessions "
          f"{doc['session_index']['first']}..{doc['session_index']['last']}")
    print(f"peers loaded  : {len(doc['peer_closes'])}")
    print(f"registered floor: {doc['registered_floor']}   unit: "
          f"{doc['unit_registered']}")
    print()
    print(f"{'unit':10s} {'events':>7s} {'pairs':>7s} {'denied':>7s} "
          f"{'floor':>7s}")
    for name, s in (("per-pair", pp), ("per-peer", pq)):
        print(f"{name:10s} {s['eligible_anchor_events']:7d} "
              f"{s['eligible_pairs']:7d} {s['pairs_denied']:7d} "
              f"{'OK' if s['reaches_floor'] else 'SHORT ' + str(s['shortfall']):>7s}")
    print(f"\nthe unit is worth {doc['unit_costs_events']} events")
    print(f"denials (per-pair): {pp['denials_by_code']}")
    print(f"pairs short on coverage: {doc['pairs_short_on_coverage']}")
    print(f"pairs left unknown     : {doc['pairs_left_unknown']}")
    rec = doc["reconciliation"]
    print()
    print(f"reconciliation vs assumed prices: "
          f"{rec['assumed_prices_events']} -> {rec['real_coverage_events']} events, "
          f"identical sets: {rec['sets_are_identical']}")
    for eid, why in rec["why"].items():
        print(f"  only under assumed prices: {eid}  "
              f"peer(s) short: {why['peers_short']}")
    if not args.dry_run:
        print(f"\nWROTE {doc['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
