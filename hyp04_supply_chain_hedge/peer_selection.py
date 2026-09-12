#!/usr/bin/env python3
"""The HYP-05 peer-selection rule: a RULE that is evaluated, not a list that
is chosen. Same discipline as `anchor_universe.py`, applied to a different
question: not "does this filer qualify as an anchor" but "was this peer
small enough, at the time of THIS anchor's event, to count as lower-coverage
for HYP-05's purpose."

=== WHY THE CUTOFF IS A FIXED DOLLAR FIGURE, NOT A PERCENTILE OF CANDIDATES ===

A percentile computed over whichever peers happen to be curated would move
every time a new edge is added, and picking a percentile AFTER seeing the
candidate pool's own distribution is exactly the outcome-adjacent selection
`NEVER_CONDITIONS` exists to forbid on the anchor side. `MARKET_CAP_THRESHOLD_
USD` is instead a fixed, externally-grounded convention (the traditional
small/mid-cap boundary), decided once, here, before any HYP-05 candidate's
market cap is computed -- the same reasoning `anchor_universe.py` gives for
citing ASC 280-10-50-42 rather than fitting `CONCENTRATION_THRESHOLD_PCT` to
HYP-04's own candidates.

RATIFIED (2026-09-12), not merely provisional. This was one of HYP-05's four
`unresolved_analysis_decisions`, and two alternatives were considered and
rejected before ratifying the fixed figure below: (1) calibrating the dollar
cutoff off a percentile of the repo's existing 789-ticker Russell-1000-proxy
universe (`Russell1000Proxy_Filtered_Universe.csv`) -- rejected because that
universe is a TODAY snapshot (current `yfinance` market cap), not
point-in-time, so it could only ever calibrate the fixed figure once, not
replace it with a genuine point-in-time percentile; and (2) building a real
point-in-time percentile system (point-in-time market cap for a broad
reference universe across every anchor event date) -- rejected as a
substantial new data-engineering task disproportionate to the benefit, given
the external-convention approach already has a direct precedent in this same
codebase (`anchor_universe.py`'s `CONCENTRATION_THRESHOLD_PCT`). The figure
itself, and the reasoning above, are unchanged from the original
implementation -- only its status moved from provisional to decided.

=== THE TARGET ANCHOR/PEER UNIVERSE (RATIFIED 2026-09-12) ===

The fourth and last of HYP-05's `unresolved_analysis_decisions`. Anchors =
`LOCKED_24_ANCHORS`, reused unchanged from HYP-04 -- HYP-05 does not select
new anchors. This was already implicit in `NEVER_CONDITIONS` below (a
candidate already IN `LOCKED_24_ANCHORS` is forbidden as a peer), made
explicit here: HYP-05's novelty is in who counts as a peer, not in which
anchors produce the shocks, exactly parallel to reusing HYP-04's `target.py`
construction for the outcome side. See `calibrate_competitor_extractor_
full_anchors.py`'s module docstring for the full reasoning, and
`HYP05_EXTRACTOR_CALIBRATION_FULL24ANCHORS_2026-09-12.md` for the calibration
this decision doubled as evidence for (candidate peers now come from running
the competitor/supplier extractor -- wired into `extract_for_universe()` as
of this same date -- and the ASC 280 path across exactly this anchor set).

=== WHAT THIS MODULE DOES NOT DO ===

It does not compute market cap (see `point_in_time_market_cap.py`) or fetch
relationship edges (see `curated_linkage.py`, `edgar_linkage.py`). It only
evaluates the rule against already-computed inputs, fail-closed. It does not
touch any display-gate condition, and it is not evidence about supply-chain
transmission -- it is a membership rule for who is eligible to be measured.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

RULE_ID = "HYP05-PEER-SELECTION-RULE-v1"

# ==========================================================================
# The rule's fixed parameter
# ==========================================================================
# The conventional boundary between small-cap and mid-cap (e.g. the
# small/mid split used by S&P's own cap-range documentation and widely
# adopted elsewhere). Ratified 2026-09-12 -- externally cited, not measured,
# not fit to any candidate pool -- see the module docstring.
MARKET_CAP_THRESHOLD_USD = 2_000_000_000

# Each candidate record must carry these to be evaluable at all.
REQUIRED_CANDIDATE_FIELDS: tuple[str, ...] = (
    "peer_ticker", "anchor_ticker", "anchor_event_date", "relationship_type",
    "as_of_date", "source",
)

# Conditions. Each denies independently; a candidate qualifies only if none
# fire.
CONDITIONS: tuple[tuple[str, str], ...] = (
    ("PS-1", "the candidate record is complete -- carries every required field"),
    ("PS-2", "a point-in-time market cap is computable for the peer as of "
             "the anchor event date"),
    ("PS-3", f"that market cap is below ${MARKET_CAP_THRESHOLD_USD:,}"),
)

# The conditions that were considered and DELIBERATELY REJECTED, recorded so
# that adding one later is a visible change to a stated decision rather than
# a quiet tightening. Mirrors anchor_universe.py's own NEVER_CONDITIONS.
NEVER_CONDITIONS: tuple[tuple[str, str], ...] = (
    ("peer still trades today",
     "A provider that drops delisted securities is survivorship-biased by "
     "construction (see anchor_universe.py's identical reasoning for ODP). "
     "Coverage/liquidity is decided from the point-in-time market cap; "
     "whether the peer still exists now is never a membership question."),
    ("the peer is in the locked 24-ticker universe",
     "The locked universe is HYP-01 confirmatory infrastructure. HYP-05 is "
     "exploratory and does not modify it, and HYP-05's whole premise is "
     "peers the LOCKED_24 construction does not reach."),
    ("the peer 'looks like' it will produce a strong result",
     "Eligibility is decided from market cap alone, computed before any "
     "outcome is examined. A candidate is never added or removed because of "
     "how its inclusion would affect a downstream estimate."),
    ("the candidate was chosen after inspecting any return or outcome data",
     "Same rule as HYP-04's own NEVER_CONDITIONS: measurability and "
     "membership are never decided from the thing being measured."),
)


@dataclass(frozen=True)
class PeerQualification:
    """Whether one (anchor event, peer) candidate satisfies the rule."""

    ticker: str
    qualifies: bool
    denials: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ticker": self.ticker, "qualifies": self.qualifies,
                "denials": list(self.denials), "evidence": self.evidence}


def evaluate_peer(
    candidate: Mapping[str, Any],
    market_cap: Optional[Any],
) -> PeerQualification:
    """Apply the rule to one (anchor event, peer) candidate. Fail-closed:
    every unknown or missing input denies.

    `candidate` is one relationship-edge-shaped record (from a curated CSV
    row or an extractor output, normalised to a plain mapping by the
    caller). `market_cap` is a `point_in_time_market_cap.MarketCapResult`
    already computed for (candidate["peer_ticker"], candidate[
    "anchor_event_date"]) -- this module does not compute it, only reads it.
    """
    denials: list[str] = []
    peer = str(candidate.get("peer_ticker", "") or "").upper()

    missing = [f for f in REQUIRED_CANDIDATE_FIELDS
              if not candidate.get(f)]
    if missing:
        denials.append(
            f"PS-1: candidate record is missing required field(s): "
            f"{', '.join(sorted(missing))}")

    mc_value = None
    if market_cap is None:
        denials.append("PS-2: no market cap result supplied for this candidate")
    elif not getattr(market_cap, "computed", False):
        reason = "; ".join(getattr(market_cap, "denials", ())) or "not computed"
        denials.append(f"PS-2: point-in-time market cap not computable -- {reason}")
    else:
        mc_value = market_cap.market_cap
        if mc_value >= MARKET_CAP_THRESHOLD_USD:
            denials.append(
                f"PS-3: market cap ${mc_value:,.0f} is at or above the "
                f"${MARKET_CAP_THRESHOLD_USD:,} cutoff")

    return PeerQualification(
        ticker=peer or "UNKNOWN",
        qualifies=not denials,
        denials=tuple(denials),
        evidence={
            "candidate": dict(candidate),
            "market_cap": mc_value,
            "threshold_usd": MARKET_CAP_THRESHOLD_USD,
        },
    )


@dataclass(frozen=True)
class PeerUniverseDerivation:
    """The peer set the rule produces over a batch of candidates, with every
    evaluation kept."""

    rule_id: str
    members: tuple[str, ...]
    qualifications: tuple[PeerQualification, ...]
    refusals: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def derived(self) -> bool:
        """A refused derivation produces no universe at all, not a small one."""
        return not self.refusals

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "derived": self.derived,
            "members": list(self.members),
            "refusals": list(self.refusals),
            "evidence": self.evidence,
            "qualifications": [q.as_dict() for q in self.qualifications],
        }


def _candidate_key(candidate: Mapping[str, Any]) -> tuple[str, Any]:
    return (str(candidate.get("peer_ticker", "") or "").upper(),
           candidate.get("anchor_event_date"))


def derive_peer_universe(
    candidates: Sequence[Mapping[str, Any]],
    market_caps: Mapping[tuple[str, Any], Any],
) -> PeerUniverseDerivation:
    """Run the rule over every candidate. Refuses (not silently scores) on
    structural defects, the same discipline as `anchor_universe.derive_
    universe`.

    `market_caps` is keyed by `(peer_ticker.upper(), anchor_event_date)`,
    matching `_candidate_key`.
    """
    refusals: list[str] = []

    if not isinstance(candidates, list):
        refusals.append("candidates is not a list")
        candidates = []

    non_mapping = sum(1 for c in candidates if not isinstance(c, Mapping))
    if non_mapping:
        refusals.append(f"{non_mapping} candidate record(s) are not mappings")
        candidates = [c for c in candidates if isinstance(c, Mapping)]

    quals = tuple(
        evaluate_peer(c, market_caps.get(_candidate_key(c)))
        for c in candidates
    )
    members = tuple(sorted({q.ticker for q in quals if q.qualifies}))

    return PeerUniverseDerivation(
        rule_id=RULE_ID,
        members=members,
        qualifications=quals,
        refusals=tuple(refusals),
        evidence={
            "candidates_evaluated": len(quals),
            "threshold_usd": MARKET_CAP_THRESHOLD_USD,
        },
    )


def format_report(d: PeerUniverseDerivation) -> str:
    lines = [f"rule: {d.rule_id}", f"derived: {d.derived}"]
    if not d.derived:
        lines.append("REFUSALS:")
        lines.extend(f"  - {r}" for r in d.refusals)
        return "\n".join(lines)
    lines.append(f"qualifying peers: {len(d.members)}")
    for t in d.members:
        lines.append(f"  - {t}")
    denied = [q for q in d.qualifications if not q.qualifies]
    lines.append(f"denied candidates: {len(denied)}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Evaluate the HYP-05 peer-selection rule over a batch of "
                    "candidate records and precomputed market caps. Reads; "
                    "writes nothing.")
    ap.add_argument("--candidates", required=True,
                    help="JSON file: a list of candidate records")
    ap.add_argument("--market-caps", required=True, dest="market_caps",
                    help="JSON file: a list of {ticker, anchor_event_date, "
                         "computed, market_cap, denials} records (the "
                         "as_dict() shape MarketCapResult produces)")
    ap.add_argument("--json", action="store_true", help="emit the derivation as JSON")
    a = ap.parse_args(argv)

    candidates = json.loads(Path(a.candidates).read_text(encoding="utf-8-sig"))
    mc_records = json.loads(Path(a.market_caps).read_text(encoding="utf-8-sig"))

    class _MC:
        def __init__(self, rec: dict[str, Any]) -> None:
            self.computed = bool(rec.get("computed"))
            self.market_cap = rec.get("market_cap")
            self.denials = tuple(rec.get("denials", ()))

    market_caps = {
        (str(r.get("ticker", "")).upper(), r.get("target_date")): _MC(r)
        for r in mc_records
    }

    d = derive_peer_universe(candidates, market_caps)
    print(json.dumps(d.as_dict(), indent=2) if a.json else format_report(d))
    return 0 if d.derived else 1


if __name__ == "__main__":
    sys.exit(main())
