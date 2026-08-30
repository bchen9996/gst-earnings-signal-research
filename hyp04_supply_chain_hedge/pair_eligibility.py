#!/usr/bin/env python3
"""HYP-04 peer-side eligibility, at the (anchor event x peer) PAIR level.

FAIL-CLOSED. Every unknown denies.

=== WHY THIS IS NOT A FOURTH HYPOTHESIS CLASS ===

=== P1 CHANGED 2026-08-29: THE ANCHOR SIDE IS A SHOCK, NOT ATTENTION ===

P1 used to require the anchor event to be eligible for
`core_attention_vs_equity_response`, while the denial it raised justified
itself as "the peer measurement is only defined relative to a usable
anchor earnings shock". The justification was information transmission;
the thing enforced was attention. They sat on adjacent lines.

The repo owner determined 2026-08-29 that HYP-04 tests INFORMATION
TRANSMISSION along supply-chain links, so P1 now requires exactly what its
own message always claimed: a well-measured anchor shock, per
`anchor_shock.AnchorShock`. HYP-04's pair side no longer imports
`gst_market_response.completeness` at all -- the paragraphs below describe
the arrangement that was in force until 2026-08-29 and are kept because
the reasoning about UNIT MISMATCH still holds and still explains why no
fourth class was ever created.

See HYP04_ANCHOR_SHOCK_DEFINITION_MEMO_2026-08-29.md and its amendment.

=== THE ORIGINAL NOTE ON WHY THIS IS NOT A FOURTH HYPOTHESIS CLASS ===

Registry v1.2 records HYP-04's `required_eligibility_class` as
`core_attention_vs_equity_response` and notes that the PEER side "has no
eligibility class in gst_market_response.completeness.HYPOTHESIS_CLASSES at
all". That wording invites the wrong fix.

The three classes in HYPOTHESIS_CLASSES are per-ANCHOR-EVENT booleans on
`ModuleEligibility` -- core_pre_event_eligible, option_benchmark_eligible,
joint_full_eligible -- and `is_eligible_for_hypothesis` maps each class name
onto exactly one of them. They answer "which evidence modules does this single
event record carry?"

HYP-04's peer measurement is not a property of an event record. It is a property
of a PAIR: this anchor event, this peer, and a linkage edge whose as-of date
either does or does not precede the event. A fourth boolean on a per-event
record cannot express that, because the fact it would have to encode is not
about the event. This is a unit mismatch, not a missing enum member.

So peer eligibility lives here, in HYP-04's own package, and
`gst_market_response` -- HYP-01's confirmatory infrastructure -- is untouched.
No fourth class was created, which is why registry v1.2's statement that "no new
class is created by this registry version" remains accurate and no registry v1.3
is required. See
`Live Signal Engine/HYP04_PEER_ELIGIBILITY_DECISION_2026-08-20.md`.

=== THE POINT-IN-TIME RULE IS THE POINT ===

P3 and P4 are why this module exists at all.

This project's central unresolved finding is a FAILED point-in-time validity
check: HYP-01's historical GST z-scores were reconstructed by querying Trends
today for windows ending years earlier, which is reproducible but not provably
what a live observer saw. That failure was discovered after the data was built.

A supply-chain linkage map is exposed to exactly the same error, and worse,
because it is curated from documents that exist NOW about relationships that
began THEN. An edge sourced from a 2026 10-K says nothing about whether a 2022
observer knew that relationship existed. Counting such a pair at a 2022 event
imports hindsight into the sample.

So a pair is eligible at an event only if the edge was established STRICTLY
BEFORE that event, and an edge whose as-of basis is "unknown/uncertain" is never
eligible at any event. This WILL disqualify real, correctly-curated edges. That
is the intended cost: it is the difference between applying the discipline
prospectively and discovering the violation afterwards.

=== WHAT IS DELIBERATELY NOT A CONDITION ===

PEER OPTIONS DATA. Analysis-lock decision D9 makes implied volatility a
CONDITIONAL, SECONDARY target; the primary target is realized volatility, which
needs only the peer's own return history. Requiring peer options here would
silently exclude precisely the thin, less-covered peers plan v0.2 section 1 says
this hypothesis is most interested in -- turning a robustness check on the same
population into a different question about liquid names. Do not add it.

THIS OPENS NO GATE. Pair eligibility feeds Phase 1 sample construction. The
display gate's C2 counts eligible ANCHOR EVENTS, a unit registry v1.2 fixes
deliberately, and nothing here changes C1-C5 or the gate's CLOSED state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .anchor_shock import AnchorShock
from .curated_linkage import (
    AS_OF_DATE_BASES,
    RELATIONSHIP_TYPE_TO_DIRECTION,
    RELATIONSHIP_TYPES,
    CuratedEdge,
    _valid_date,
)

# The one as-of basis that can never support eligibility. It is a member of the
# curated schema's closed vocabulary on purpose -- a curator must be able to
# record honest uncertainty rather than being pushed into inventing a date --
# and it is refused here rather than at curation time for the same reason.
UNKNOWN_AS_OF_BASIS = "unknown/uncertain"

# Sentinel separating "not supplied" from "supplied as False". A caller that
# never looked at peer history and a caller that looked and found none are
# different claims, and dict/bool coercion collapses them.
_UNKNOWN = object()


@dataclass(frozen=True)
class PairEligibility:
    """Whether one (anchor event, peer) pair may enter the HYP-04 sample."""

    anchor_ticker: str
    peer_ticker: str
    event_id: str
    event_date: str
    eligible: bool
    denials: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "ELIGIBLE" if self.eligible else "INELIGIBLE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "anchor_ticker": self.anchor_ticker,
            "peer_ticker": self.peer_ticker,
            "event_id": self.event_id,
            "event_date": self.event_date,
            "eligible": self.eligible,
            "denials": list(self.denials),
            "evidence": dict(self.evidence),
        }


def evaluate_pair(
    edge: CuratedEdge,
    *,
    event_id: str,
    event_date: str,
    event_anchor_ticker: str,
    anchor_shock: Optional[AnchorShock] = None,
    peer_history_available: Any = _UNKNOWN,
    from_placeholder_linkage: bool = False,
) -> PairEligibility:
    """Evaluate all conditions. ELIGIBLE only if every one holds.

    Every argument that is unknown denies rather than defaulting to permissive.
    `peer_history_available` uses a sentinel so "not supplied" is distinguishable
    from an explicit False, and both deny.
    """
    denials: list[str] = []
    evidence: dict[str, Any] = {
        "relationship_type": edge.relationship_type,
        "confidence": edge.confidence,
        "source_type": edge.source_type,
        "as_of_date": edge.as_of_date,
        "as_of_date_basis": edge.as_of_date_basis,
        "date_confidence": edge.date_confidence,
    }

    # ---- P1: the ANCHOR event must carry a well-measured shock -----------
    # Delegated, never reimplemented: anchor_shock.shock_for_event decides
    # whether the shock is measurable and fails closed on every unknown. An
    # unsupplied shock is not a shock of zero -- it is an unusable anchor.
    if anchor_shock is None:
        denials.append(
            "P1 FAILED: no anchor shock supplied. The peer measurement is "
            "only defined relative to a usable anchor earnings shock, and an "
            "unsupplied shock is not one."
        )
        evidence["anchor_shock"] = None
    else:
        evidence["anchor_shock"] = anchor_shock.shock
        evidence["anchor_shock_session"] = anchor_shock.session
        evidence["anchor_shock_rule_id"] = anchor_shock.rule_id

    # ---- P2: the edge must belong to THIS anchor -------------------------
    edge_anchor = (edge.anchor_ticker or "").strip().upper()
    want_anchor = (event_anchor_ticker or "").strip().upper()
    evidence["edge_anchor"] = edge_anchor
    evidence["event_anchor"] = want_anchor
    if not edge_anchor or not want_anchor:
        denials.append("P2 FAILED: anchor ticker is blank on the edge or the event")
    elif edge_anchor != want_anchor:
        denials.append(
            f"P2 FAILED: edge anchor {edge_anchor} is not this event's anchor "
            f"{want_anchor}"
        )

    peer = (edge.peer_ticker or "").strip().upper()
    if not peer:
        denials.append("P2 FAILED: peer ticker is blank")
    elif peer == edge_anchor and edge_anchor:
        denials.append(f"P2 FAILED: peer and anchor are the same ticker ({peer})")

    # ---- P3: STRICT point-in-time ----------------------------------------
    # Both dates are format-checked before comparison. ISO YYYY-MM-DD compares
    # correctly as strings, but only once the format is known -- a malformed
    # date must deny, never silently mis-compare.
    as_of_ok = _valid_date(edge.as_of_date or "")
    event_ok = _valid_date(event_date or "")
    evidence["as_of_date_valid"] = as_of_ok
    evidence["event_date_valid"] = event_ok

    if not as_of_ok:
        denials.append(
            f"P3 FAILED: edge as_of_date {edge.as_of_date!r} is not a valid "
            "YYYY-MM-DD date"
        )
    if not event_ok:
        denials.append(
            f"P3 FAILED: event_date {event_date!r} is not a valid YYYY-MM-DD date"
        )
    if as_of_ok and event_ok:
        strictly_before = edge.as_of_date < event_date
        evidence["as_of_strictly_before_event"] = strictly_before
        if not strictly_before:
            denials.append(
                f"P3 FAILED: the edge's as_of_date ({edge.as_of_date}) does not "
                f"strictly precede the event date ({event_date}). An edge "
                "established on or after the event cannot have been known to an "
                "observer at the event."
            )

    # ---- P4: an unknown as-of basis is never eligible --------------------
    basis = (edge.as_of_date_basis or "").strip()
    if basis not in AS_OF_DATE_BASES:
        denials.append(
            f"P4 FAILED: as_of_date_basis {basis!r} is outside the curated "
            f"vocabulary {list(AS_OF_DATE_BASES)}"
        )
    elif basis == UNKNOWN_AS_OF_BASIS:
        denials.append(
            f"P4 FAILED: as_of_date_basis is {UNKNOWN_AS_OF_BASIS!r}. A date "
            "nobody can source cannot establish that the relationship was known "
            "before the event, whatever the date says."
        )

    # ---- P5: peer return history, with unknown denying -------------------
    if peer_history_available is _UNKNOWN:
        evidence["peer_history_available"] = None
        denials.append(
            "P5 FAILED: peer return-history availability was not supplied. An "
            "unchecked peer is not a peer with data."
        )
    else:
        evidence["peer_history_available"] = bool(peer_history_available)
        if not peer_history_available:
            denials.append(
                f"P5 FAILED: no usable return history for {peer or '<blank>'} "
                "around the event window"
            )

    # ---- P6: relationship type and its direction -------------------------
    rt = edge.relationship_type
    if rt not in RELATIONSHIP_TYPES:
        denials.append(
            f"P6 FAILED: relationship_type {rt!r} is outside the curated "
            f"vocabulary {list(RELATIONSHIP_TYPES)}"
        )
    elif RELATIONSHIP_TYPE_TO_DIRECTION.get(rt) is None:
        denials.append(f"P6 FAILED: no direction mapping for {rt!r}")
    evidence["direction"] = RELATIONSHIP_TYPE_TO_DIRECTION.get(rt)

    # ---- P7: placeholder linkage is never eligible -----------------------
    # Mirrors display-gate condition C5. The Phase 0 placeholder is positional
    # and synthetic; registry v1.2's display_rule bars its results at any event
    # count, so it must not be able to produce an eligible pair either.
    evidence["from_placeholder_linkage"] = bool(from_placeholder_linkage)
    if from_placeholder_linkage:
        denials.append(
            "P7 FAILED: this pair derives from the Phase 0 positional-synthetic "
            "placeholder linkage, which is never evidence about supply-chain "
            "transmission at any event count."
        )

    return PairEligibility(
        anchor_ticker=edge_anchor,
        peer_ticker=peer,
        event_id=event_id,
        event_date=event_date,
        eligible=not denials,
        denials=tuple(denials),
        evidence=evidence,
    )


def eligible_pairs(
    edges: list[CuratedEdge],
    *,
    event_id: str,
    event_date: str,
    event_anchor_ticker: str,
    anchor_shock: Optional[AnchorShock] = None,
    peer_history: Optional[dict[str, bool]] = None,
    from_placeholder_linkage: bool = False,
) -> tuple[list[PairEligibility], list[PairEligibility]]:
    """Split edges into (eligible, ineligible) for one anchor event.

    `peer_history` maps upper-case peer ticker -> availability. A peer absent
    from the mapping is UNKNOWN and denies; it is never read as available.
    """
    ok: list[PairEligibility] = []
    no: list[PairEligibility] = []
    for e in edges:
        peer = (e.peer_ticker or "").strip().upper()
        avail: Any = _UNKNOWN
        if peer_history is not None and peer in peer_history:
            avail = peer_history[peer]
        r = evaluate_pair(
            e,
            event_id=event_id,
            event_date=event_date,
            event_anchor_ticker=event_anchor_ticker,
            anchor_shock=anchor_shock,
            peer_history_available=avail,
            from_placeholder_linkage=from_placeholder_linkage,
        )
        (ok if r.eligible else no).append(r)
    return ok, no
