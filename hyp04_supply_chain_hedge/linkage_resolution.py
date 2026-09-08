#!/usr/bin/env python3
"""Resolve anchor events to REAL peers from the curated linkage map -- HYP-04.

This is the join the registry's `status_basis` calls missing: "there is no
production join mapping a market-response event_id to any peer observation."
It builds one, from the curated map rather than from position.

=== WHAT IT REPLACES, AND WHAT IT DELIBERATELY DOES NOT ===

Phase 0 paired anchors to peers POSITIONALLY -- `peers[i*k:(i+1)*k]` in
fixtures.py -- a synthetic pairing carrying no claim about any real
relationship. Registry v1.2 bars displaying results built on it "under any
circumstances, at any event count", and display-gate condition C5 enforces it.

This module produces the SAME anchor-event shape the analysis already consumes,
so nothing downstream changes, but sources each event's peers from the curated
map through `pair_eligibility.evaluate_pair` -- which applies the strict
point-in-time rule, so a peer appears only for events after its edge was
publicly disclosed.

It does NOT rewire `run_canary_audit.candidate_peer_universe()`. That still
returns the Phase 0 placeholder universe, deliberately: the linkage-source
decision of 2026-08-18 chose "Option A -- the loader lives alongside the
placeholder", because rewiring it would make the already-committed EDGAR
coverage findings non-reproducible the moment a curated file landed. A new path
is added; the old one stays where the committed audits can still find it.

=== WHY uses_placeholder_linkage IS DERIVED, NEVER PASSED IN ===

`FreezeRecord.uses_placeholder_linkage` defaults to True and is the sole input
to C5. If a caller could simply set it False, C5 would be an honour system: the
one condition standing between placeholder output and a displayed finding would
rest on the person with the most reason to want it cleared.

So this module never accepts that flag. It returns a `LinkageProvenance` that
computes it from what was ACTUALLY loaded -- the file, its hash, whether it
loaded clean, and whether it yielded usable edges. `freeze_record_fields()`
emits the value from that provenance, so a freeze claiming non-placeholder
linkage can only come from a run that genuinely read a curated map.

A map that loads clean but yields ZERO usable edges is still treated as
placeholder-equivalent here. It was not really "used", and letting an empty file
clear C5 would reintroduce the loophole the derivation closes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .anchor_shock import AnchorShock

from .curated_linkage import CuratedEdge, load_curated_linkage
from .pair_eligibility import PairEligibility, evaluate_pair

SOURCE_CURATED = "curated_map"
SOURCE_PLACEHOLDER = "phase0_positional_placeholder"


@dataclass(frozen=True)
class LinkageProvenance:
    """Where the peers came from. The basis for C5, computed not asserted."""

    source: str
    source_path: Optional[str] = None
    source_sha256: Optional[str] = None
    rows_seen: int = 0
    rows_rejected: int = 0
    edges_usable: int = 0
    load_ok: bool = False

    @property
    def uses_placeholder_linkage(self) -> bool:
        """True unless a curated map was genuinely read AND yielded edges."""
        if self.source != SOURCE_CURATED:
            return True
        if not self.load_ok:
            return True
        return self.edges_usable < 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "rows_seen": self.rows_seen,
            "rows_rejected": self.rows_rejected,
            "edges_usable": self.edges_usable,
            "load_ok": self.load_ok,
            "uses_placeholder_linkage": self.uses_placeholder_linkage,
        }


@dataclass(frozen=True)
class ResolvedPanel:
    """Anchor events with real peers attached, plus why the rest were dropped."""

    anchor_events: list[dict[str, Any]] = field(default_factory=list)
    provenance: LinkageProvenance = field(
        default_factory=lambda: LinkageProvenance(source=SOURCE_PLACEHOLDER))
    pairs_eligible: int = 0
    pairs_denied: int = 0
    denied: list[PairEligibility] = field(default_factory=list)

    @property
    def n_events_with_peers(self) -> int:
        return sum(1 for ev in self.anchor_events if ev["peers"])

    @property
    def n_pairs(self) -> int:
        return sum(len(ev["peers"]) for ev in self.anchor_events)

    def denial_reasons(self) -> dict[str, int]:
        """Denial code -> count. A profile of WHY pairs were dropped.

        Reported rather than summarised away. If most pairs die on P3, the
        limit is how far back the map's as_of dates reach, which is a curation
        problem. If they die on P5, it is a data problem. Those need different
        work, and a single aggregate count cannot tell them apart.
        """
        out: dict[str, int] = {}
        for p in self.denied:
            for d in p.denials:
                code = d.split()[0] if d else "UNKNOWN"
                out[code] = out.get(code, 0) + 1
        return out


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def resolve_from_curated_map(
    anchor_events: list[dict[str, Any]],
    *,
    map_path: Path,
    anchor_shock: Optional[dict[str, AnchorShock]] = None,
    peer_history: Optional[dict[str, bool]] = None,
    peer_history_by_pair: Optional[dict[tuple[str, str], bool]] = None,
) -> ResolvedPanel:
    """Attach real peers to each anchor event from the curated map.

    `anchor_events` is the shape the analysis already uses; each entry needs
    `event_id`, `anchor` and `event_date`. Any incoming `peers` value is
    IGNORED and replaced -- a positional list must never survive into a panel
    that claims curated linkage.

    `anchor_shock` maps event_id -> AnchorShock. An event absent
    from it is denied by P1, never assumed eligible. `peer_history` maps peer
    ticker -> availability; a peer absent from it is UNKNOWN and denied by P5,
    never assumed available.

    `peer_history_by_pair` maps (event_id, peer) -> availability and TAKES
    PRECEDENCE over `peer_history` for pairs it covers. Registry v1.11: "Peer-
    side price data availability is a MEASURABILITY question, reported per
    pair." The per-peer unit marks a peer unavailable for every event it
    appears in as soon as ONE event is uncoverable, which is lossy in the
    direction that matters -- measured at 54 events on the real panel. A pair
    absent from BOTH maps is still UNKNOWN and still denied by P5.
    """
    if not map_path.is_file():
        return ResolvedPanel(
            anchor_events=[dict(ev, peers=[]) for ev in anchor_events],
            provenance=LinkageProvenance(
                source=SOURCE_CURATED, source_path=str(map_path), load_ok=False),
        )

    res = load_curated_linkage(map_path)
    prov = LinkageProvenance(
        source=SOURCE_CURATED,
        source_path=str(map_path),
        source_sha256=_sha256(map_path),
        rows_seen=res.rows_seen,
        rows_rejected=res.rows_rejected,
        edges_usable=len(res.edges),
        load_ok=res.ok,
    )

    by_anchor: dict[str, list[CuratedEdge]] = {}
    for e in res.edges:
        by_anchor.setdefault(e.anchor_ticker.upper(), []).append(e)

    out: list[dict[str, Any]] = []
    denied: list[PairEligibility] = []
    n_ok = 0

    for ev in anchor_events:
        anchor = str(ev.get("anchor", "")).upper()
        event_id = str(ev.get("event_id", ""))
        event_date = str(ev.get("event_date", ""))

        peers: list[str] = []
        for edge in by_anchor.get(anchor, []):
            peer = edge.peer_ticker.upper()
            kw: dict[str, Any] = {
                "event_id": event_id,
                "event_date": event_date,
                "event_anchor_ticker": anchor,
                "anchor_shock": (anchor_shock or {}).get(event_id),
                "from_placeholder_linkage": False,
            }
            # Only supply peer availability when it is actually known. Omitting
            # the argument leaves evaluate_pair's own sentinel in place, which
            # denies on P5 -- an unchecked peer is not a peer with data.
            pair_key = (event_id, peer)
            if (peer_history_by_pair is not None
                    and pair_key in peer_history_by_pair):
                kw["peer_history_available"] = peer_history_by_pair[pair_key]
            elif peer_history is not None and peer in peer_history:
                kw["peer_history_available"] = peer_history[peer]

            r = evaluate_pair(edge, **kw)
            if r.eligible:
                peers.append(peer)
                n_ok += 1
            else:
                denied.append(r)

        out.append(dict(ev, peers=peers))

    return ResolvedPanel(anchor_events=out, provenance=prov,
                         pairs_eligible=n_ok, pairs_denied=len(denied),
                         denied=denied)


def freeze_record_fields(panel: ResolvedPanel) -> dict[str, Any]:
    """The freeze fields this run can HONESTLY claim.

    Supplies `uses_placeholder_linkage` from the panel's provenance, so a
    caller cannot assert non-placeholder linkage a run did not actually use,
    and `eligible_event_ids` from the events that ended up with peers.

    It deliberately does NOT supply `frozen`, `analysis_commit_sha`,
    `analysis_lock_document` or `frozen_before_any_result_computed`. Those are
    claims about the operator's process and the repository's state at freeze
    time, not about linkage, and this module has no standing to make them.
    """
    return {
        "eligible_event_ids": tuple(
            str(ev.get("event_id", "")) for ev in panel.anchor_events
            if ev.get("peers")),
        "uses_placeholder_linkage": panel.provenance.uses_placeholder_linkage,
    }
