#!/usr/bin/env python3
"""HYP-04 result-display gate. FAIL-CLOSED.

This module decides whether a HYP-04 FINDING may be displayed. It mirrors
`Live Signal Engine/GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` -- the same
document that governs HYP-01 -- rather than inventing a weaker gate for a
younger hypothesis.

=== IMPORTANT: THE GATE HAS FOUR CONDITIONS, NOT TWO ===

The dashboard request asked to unlock on two conditions: n >= 193 real anchor
events, and a frozen event set. Those are necessary. They are NOT sufficient,
because the governing document requires four things to hold simultaneously
(section 1). Implementing only the requested two would have produced a gate
strictly WEAKER than HYP-01's, which is the opposite of mirroring it. All four
are implemented:

  C1  the hypothesis status is ACTIVE_COLLECTING
  C2  eligible event count >= registered threshold (193 for HYP-04)
  C3  the eligible event-ID set is frozen, together with the analysis-code
      commit, BEFORE any result was calculated
  C4  every PENDING_SEPARATE_ANALYSIS_LOCK decision is resolved in a dated
      analysis lock written BEFORE the freeze

Under registry v1.2 (2026-08-20), HYP-04 CLEARS C4: the four analysis decisions
are recorded as resolved in the signed, dated analysis lock. It still fails C1
(status is PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED). So even a hypothetical
193 frozen real events would leave this gate CLOSED, and that is correct, not a
bug: resolving how a thing will be measured is not the same as being ready to
measure it.

C4 is the first of the five conditions to have ever cleared in this project.
That is worth stating precisely, because it is the kind of change that invites
over-reading: it removed a governance blocker and moved nothing else. No result
exists, none is closer to existing, and the binding Phase 1 blocker remains a
linkage map with zero curated rows.

=== WHAT COUNTS AS A DISPLAY ===

Per section 3 of the governing document, ALL of these are displays and are
equally gated -- a lag score, an onset or peak horizon, a beta_h coefficient,
a direction, a plot or dashboard tile, a correlation or model summary, a
count-with-implication, or a verbal summary anywhere including a commit
message or a conversation.

The eligible event COUNT itself is not a result and may be shown at any time.
So may thresholds, statuses, and the list of unresolved decisions. Progress is
public; findings are gated.

=== PLACEHOLDER LINKAGE IS NOT A LOOPHOLE ===

Registry v1.1's display_rule for HYP-04 bars placeholder-linkage results "under
any circumstances, at any event count". Phase 0's synthetic-fixture and
positional-synthetic-placeholder output is therefore permanently ineligible for display
as a HYP-04 finding, independent of the four conditions above. This module
enforces that as its own condition rather than trusting callers to remember it.

=== QUANTUM-DERIVED RESULTS ARE BLOCKED SEPARATELY, AND HARDER ===

The five conditions above describe the state of the HYPOTHESIS. They say
nothing about HOW a number was computed, so they cannot stop a result from a
method this project has never validated -- and an OPEN gate would let one
straight through.

`quantum_provenance.py` is the control for that, and it composes with this one
rather than being folded into it: a quantum-derived result is refused
regardless of gate state and regardless of source (this project's own tertiary
cross-check module, or a result supplied from outside the repository), unless
it carries a complete attestation that it was validated against the classical
reference on known cases. Nothing has such an attestation; nothing is claimed
to. Both controls must pass -- clearing the quantum control does not open this
gate, and opening this gate does not clear the quantum control.

=== FAIL-CLOSED DISCIPLINE ===

Every unknown resolves to DENY. A missing file, an unparseable artifact, an
absent field, an unrecognised status -- each denies on its own. Section 4:
"Absence of a rule is never read as permission."
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .quantum_provenance import (
    MethodProvenance,
    ProvenanceError,
    assert_may_display,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

# The registry version the gate READS. Deliberately named for its role rather
# than its version: the previous constant was REGISTRY_V1_1, so bumping the
# registry meant renaming a constant across four files and a version number
# stayed embedded in code that does not care which version it is. The next bump
# should touch this one line.
#
# v1.2 (2026-08-20) records HYP-04's four analysis decisions as resolved in the
# signed analysis lock. v1.1 is NOT edited in place and is still governed by its
# own suite -- test_market_response_hypothesis_registry_v1_1.py keeps pointing
# at v1.1 on purpose, and must not be repointed here.
REGISTRY_CURRENT = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7.json"
GATES_DOC = LSE / "GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md"

HYPOTHESIS_ID = "HYP-04"
REQUIRED_STATUS = "ACTIVE_COLLECTING"

# --- Analysis-decision state vocabulary -----------------------------------
# A CLOSED vocabulary, deliberately. C4 requires every decision to carry one of
# these exact tokens; anything else -- a typo, a made-up string, an absent
# field -- is an unknown and denies. See the C4 block in evaluate_gate for why
# this is checked positively rather than as "not PENDING".
PENDING_TOKEN = "PENDING_SEPARATE_ANALYSIS_LOCK"
RESOLVED_TOKEN = "RESOLVED_IN_DATED_ANALYSIS_LOCK"
DECISION_STATES: frozenset[str] = frozenset({PENDING_TOKEN, RESOLVED_TOKEN})

# A decision marked resolved must name the dated lock that resolved it. The
# decision state's own name says the resolution happens in a separate analysis
# lock; a resolution that cannot cite one has not shown that lock exists.
RESOLVED_BY_FIELD = "resolved_by_lock"

# Sentinel distinguishing "key absent" from "key present and set to None".
# `dict.get(k)` collapses those two, and they are not the same claim.
_MISSING = object()

# Panel identifiers that carry FINDINGS. Every one of these is gated.
# Listed explicitly so a new findings panel must be added here consciously
# rather than defaulting to visible.
FINDINGS_PANELS: tuple[str, ...] = (
    "lag_scores",
    "onset_horizon",
    "peak_horizon",
    "beta_h_coefficients",
    "impulse_response_profile",
    "direction_of_effect",
    "link_strength_scores",
    "ccf_cross_check_result",
    "placebo_test_result",
    "stage2_recommendations",
)

# Panels that are PROGRESS, not findings. Explicitly enumerated so the
# distinction is auditable rather than implied.
PROGRESS_PANELS: tuple[str, ...] = (
    "build_test_status",
    "audit_coverage",
    "instrument_calibration",
    "registry_status",
    "phase_roadmap",
    "eligible_event_count",
    "unresolved_decisions",
)


def _is_real_int(x: Any) -> bool:
    """int, and not a bool wearing an int's clothes.

    `isinstance(True, int)` is True in Python, so a plain isinstance check
    would silently read `eligible_event_count=True` as a count of 1 and
    `minimum_eligible_events=True` as a threshold of 1. Neither is a count.
    On a fail-closed control an input that means nothing must deny, not be
    quietly coerced into the smallest passing value.
    """
    return isinstance(x, int) and not isinstance(x, bool)


class GateError(RuntimeError):
    """Raised when gated content is requested through a closed gate."""


@dataclass
class GateDecision:
    """The gate's verdict. `open` is only ever True when `denials` is empty."""

    open: bool
    denials: list[str] = field(default_factory=list)
    conditions: dict[str, bool] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "OPEN" if self.open else "CLOSED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": HYPOTHESIS_ID,
            "gate": self.status,
            "conditions": self.conditions,
            "denials": self.denials,
            "evidence": self.evidence,
            "governing_document": (
                "Live Signal Engine/GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md"
            ),
            "fail_closed": "Absence of a rule is never read as permission.",
        }


@dataclass
class FreezeRecord:
    """The frozen eligible-event set, per the governing document's section 5.

    A freeze is only real when all of: the event-ID set is enumerated, the
    analysis-code commit SHA is recorded, the resolved analysis lock is
    recorded, and all three were written BEFORE any result was computed.
    """

    frozen: bool = False
    eligible_event_ids: tuple[str, ...] = ()
    analysis_commit_sha: Optional[str] = None
    analysis_lock_document: Optional[str] = None
    frozen_before_any_result_computed: bool = False
    uses_placeholder_linkage: bool = True


def _load_registry(path: Path = REGISTRY_CURRENT) -> tuple[Optional[dict], list[str]]:
    """Load the registry, or explain why it could not be loaded.

    A missing or malformed registry DENIES. It never falls back to a default,
    a cached copy, or an assumed status.
    """
    if not path.is_file():
        return None, [f"registry not found at {path.name} -- cannot establish status or threshold"]
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), []
    except json.JSONDecodeError as e:
        return None, [f"registry {path.name} is not valid JSON ({e}) -- denying"]


def _hyp04_entry(registry: dict) -> tuple[Optional[dict], list[str]]:
    for h in registry.get("hypotheses", []):
        if h.get("hypothesis_id") == HYPOTHESIS_ID:
            return h, []
    return None, [f"{HYPOTHESIS_ID} is not registered in this registry version -- DENY"]


def evaluate_gate(
    *,
    eligible_event_count: Optional[int] = None,
    freeze: Optional[FreezeRecord] = None,
    registry_path: Path = REGISTRY_CURRENT,
) -> GateDecision:
    """Evaluate all four conditions. Returns OPEN only if every one holds.

    `eligible_event_count` is the count of REAL eligible anchor events. It is
    not defaulted: passing None denies, because an unknown count is explicitly
    a DENY condition ("Eligible count unknown or not mechanically derivable").
    """
    denials: list[str] = []
    conditions: dict[str, bool] = {}
    evidence: dict[str, Any] = {}

    registry, load_denials = _load_registry(registry_path)
    denials.extend(load_denials)
    if registry is None:
        conditions = {c: False for c in ("C1_status", "C2_threshold",
                                         "C3_frozen", "C4_decisions_resolved",
                                         "C5_not_placeholder")}
        return GateDecision(open=False, denials=denials, conditions=conditions,
                            evidence=evidence)

    entry, entry_denials = _hyp04_entry(registry)
    denials.extend(entry_denials)
    if entry is None:
        conditions = {c: False for c in ("C1_status", "C2_threshold",
                                         "C3_frozen", "C4_decisions_resolved",
                                         "C5_not_placeholder")}
        return GateDecision(open=False, denials=denials, conditions=conditions,
                            evidence=evidence)

    # ---- C1: status must be ACTIVE_COLLECTING --------------------------
    status = entry.get("status")
    evidence["registry_status"] = status
    c1 = status == REQUIRED_STATUS
    conditions["C1_status"] = c1
    if not c1:
        denials.append(
            f"C1 FAILED: status is {status!r}, not {REQUIRED_STATUS!r}. "
            "A hypothesis whose measurement has no production capture path "
            "cannot display a finding."
        )

    # ---- C2: eligible count must reach the registered threshold --------
    threshold = entry.get("minimum_eligible_events")
    evidence["registered_threshold"] = threshold
    evidence["eligible_event_count"] = eligible_event_count
    if not _is_real_int(threshold):
        conditions["C2_threshold"] = False
        denials.append("C2 FAILED: registered threshold is missing or not an integer.")
    elif eligible_event_count is None:
        conditions["C2_threshold"] = False
        denials.append(
            "C2 FAILED: eligible event count is unknown / not mechanically "
            "derivable. An unknown count denies -- it never defaults to zero "
            "or to pass."
        )
    elif not _is_real_int(eligible_event_count) or eligible_event_count < 0:
        conditions["C2_threshold"] = False
        denials.append(
            f"C2 FAILED: eligible event count {eligible_event_count!r} is not a "
            "non-negative integer."
        )
    else:
        c2 = eligible_event_count >= threshold
        conditions["C2_threshold"] = c2
        if not c2:
            denials.append(
                f"C2 FAILED: {eligible_event_count} eligible events is below the "
                f"registered threshold of {threshold}."
            )

    # ---- C3: the event set must be frozen ------------------------------
    if freeze is None:
        conditions["C3_frozen"] = False
        denials.append("C3 FAILED: no freeze record supplied. An absent freeze denies.")
    else:
        problems: list[str] = []
        if not freeze.frozen:
            problems.append("freeze flag is not set")
        if not freeze.eligible_event_ids:
            problems.append("the eligible event-ID set is empty or unenumerated")
        if not freeze.analysis_commit_sha:
            problems.append("no analysis-code commit SHA was recorded")
        if not freeze.analysis_lock_document:
            problems.append("no dated analysis lock document was recorded")
        if not freeze.frozen_before_any_result_computed:
            problems.append(
                "the freeze is not attested as happening BEFORE any result was "
                "computed -- a freeze recorded afterwards is not a freeze"
            )
        # A frozen set whose size contradicts the reported count is not
        # mechanically derivable, and section 4 denies on exactly that.
        if (freeze.eligible_event_ids and _is_real_int(eligible_event_count)
                and len(freeze.eligible_event_ids) != eligible_event_count):
            problems.append(
                f"the frozen set holds {len(freeze.eligible_event_ids)} ids but the "
                f"reported eligible count is {eligible_event_count} -- these must agree"
            )
        conditions["C3_frozen"] = not problems
        evidence["frozen_event_id_count"] = len(freeze.eligible_event_ids)
        evidence["analysis_commit_sha_present"] = bool(freeze.analysis_commit_sha)
        if problems:
            denials.append("C3 FAILED: " + "; ".join(problems) + ".")

    # ---- C4: every decision must be EXPLICITLY resolved ----------------
    #
    # This asks "is every decision explicitly RESOLVED?", never "is any
    # decision still PENDING?". The difference is not cosmetic. A
    # not-PENDING test passes on a deleted ledger, a missing state field, an
    # unrecognised token and a one-character typo -- all five were verified to
    # open this gate before this was rewritten. In a module whose stated rule
    # is "absence of a rule is never read as permission", the burden belongs on
    # the resolution to prove itself, not on the denial to survive a typo.
    #
    # Resolution is recorded by MARKING each decision, never by removing it.
    # That mirrors the registry's own append-only discipline -- "no registered
    # event is ever deleted" -- and is why an emptied ledger denies.
    c4_problems: list[str] = []
    raw_decisions = entry.get("unresolved_analysis_decisions", _MISSING)

    if raw_decisions is _MISSING:
        c4_problems.append(
            "the 'unresolved_analysis_decisions' key is absent -- an absent "
            "decision ledger is not an empty one, and its absence proves nothing"
        )
    elif not isinstance(raw_decisions, list):
        c4_problems.append(
            f"'unresolved_analysis_decisions' is {type(raw_decisions).__name__}, "
            "not a list"
        )
    elif not raw_decisions:
        c4_problems.append(
            "the decision ledger is empty. Resolution is recorded by marking "
            "each decision resolved, never by removing it -- an emptied ledger "
            "is a deletion, not a resolution"
        )
    else:
        for i, d in enumerate(raw_decisions):
            if not isinstance(d, dict):
                c4_problems.append(f"entry {i} is {type(d).__name__}, not an object")
                continue
            label = str(d.get("decision", f"<unnamed entry {i}>"))[:70]
            state = d.get("state", _MISSING)
            if state is _MISSING:
                c4_problems.append(f"{label!r} carries no 'state' field")
            elif state not in DECISION_STATES:
                # Catches typos. An unrecognised token is an unknown, and an
                # unknown denies -- it is never read as "probably resolved".
                c4_problems.append(
                    f"{label!r} has unrecognised state {str(state)[:40]!r}; "
                    f"permitted states are {sorted(DECISION_STATES)}"
                )
            elif state == PENDING_TOKEN:
                c4_problems.append(f"{label!r} is still {PENDING_TOKEN}")
            elif not str(d.get(RESOLVED_BY_FIELD, "") or "").strip():
                # The decision's own name says resolution happens in a
                # SEPARATE ANALYSIS LOCK. A resolution that cannot name that
                # lock has not demonstrated one exists.
                c4_problems.append(
                    f"{label!r} is marked {RESOLVED_TOKEN} but names no "
                    f"{RESOLVED_BY_FIELD!r} -- resolution must cite the dated "
                    "analysis lock that performed it"
                )

    # Two distinct counts, reported separately because they answer different
    # questions: how many decisions are still openly pending, versus how many
    # things are wrong with the ledger (which includes tampering, typos and
    # absent fields that are not "pending" in any meaningful sense).
    evidence["decision_ledger_entries"] = (
        len(raw_decisions) if isinstance(raw_decisions, list) else None
    )
    evidence["pending_analysis_decisions"] = sum(
        1 for d in raw_decisions
        if isinstance(raw_decisions, list) and isinstance(d, dict)
        and d.get("state") == PENDING_TOKEN
    ) if isinstance(raw_decisions, list) else 0
    evidence["c4_problem_count"] = len(c4_problems)
    conditions["C4_decisions_resolved"] = not c4_problems
    if c4_problems:
        denials.append(
            f"C4 FAILED: {len(c4_problems)} decision problem(s). Every decision "
            "must be explicitly marked "
            f"{RESOLVED_TOKEN} and cite the dated analysis lock that resolved "
            "it, written before the freeze. " + "; ".join(c4_problems)
        )

    # ---- C5: placeholder linkage is never displayable ------------------
    # Registry v1.1's display_rule bars this "under any circumstances, at any
    # event count", so it is enforced as its own condition rather than left to
    # caller discipline.
    uses_placeholder = True if freeze is None else freeze.uses_placeholder_linkage
    evidence["uses_placeholder_linkage"] = uses_placeholder
    c5 = not uses_placeholder
    conditions["C5_not_placeholder"] = c5
    if not c5:
        denials.append(
            "C5 FAILED: this freeze record declares the Phase 0 "
            "positional-synthetic placeholder linkage (peers assigned to "
            "anchors by list position, not by sector or by any real "
            "relationship). The registry bars displaying placeholder-linkage "
            "results as HYP-04 findings under any circumstances, at any event "
            "count. To clear this, build the freeze from a curated map via "
            "linkage_resolution.resolve_from_curated_map(), which DERIVES "
            "uses_placeholder_linkage from what was actually read rather than "
            "letting a caller assert it."
        )

    return GateDecision(open=not denials, denials=denials,
                        conditions=conditions, evidence=evidence)


def is_findings_panel(panel_id: str) -> bool:
    """True if this panel carries a finding and is therefore gated.

    An UNKNOWN panel id returns True -- it is treated as a findings panel and
    denied. A new panel must be explicitly enumerated in PROGRESS_PANELS to be
    shown, so forgetting to classify one fails closed rather than open.
    """
    if panel_id in PROGRESS_PANELS:
        return False
    return True


def assert_display_allowed(
    panel_id: str,
    decision: GateDecision,
    provenance: Optional[MethodProvenance] = None,
) -> None:
    """Raise unless this panel may be displayed under this decision.

    Progress panels always pass. Findings panels pass only through an OPEN
    gate. This is the single chokepoint the dashboard calls -- rendering code
    never inspects the conditions itself and never decides for itself.

    TWO INDEPENDENT CONTROLS, EVALUATED IN THIS ORDER:

    1. The quantum-provenance control, first and for EVERY panel including
       progress panels. A declared quantum-derived result without a complete
       classical-validation attestation raises `QuantumProvenanceError` here
       even when the gate is wide open, because an open gate licenses showing a
       CLASSICAL finding and nothing more. Checking it first also means the
       caller is told the real reason rather than a generic gate denial.

    2. The five-condition gate, as before.

    `provenance=None` means the caller declared nothing. That is tolerated
    while the gate is CLOSED -- the panel is refused anyway and the gate's own
    denial is the honest reason -- but it is refused once the gate is OPEN,
    where an undeclared method family is exactly the "unknown resolves to DENY"
    case. Concretely: the day this gate opens, every findings panel must state
    what produced its number or it will not render. That is deliberate, and it
    is why the dashboard's findings loop currently passes nothing: today it
    fails on the gate, and later it will fail loudly on the missing
    declaration rather than quietly publishing an unattributed figure.
    """
    assert_may_display(panel_id, provenance)

    if not is_findings_panel(panel_id):
        return
    if decision.open:
        if provenance is None:
            raise ProvenanceError(
                f"Display DENIED for findings panel {panel_id!r}. The gate is "
                "OPEN, but no method provenance was declared for this result. "
                "An undeclared method family cannot be shown to be classical, "
                "and absence of a declaration is not permission. Pass a "
                "MethodProvenance (quantum_provenance.CLASSICAL_INTERNAL for "
                "this package's own classical estimators)."
            )
        return
    raise GateError(
        f"Display DENIED for findings panel {panel_id!r}. Gate is "
        f"{decision.status}. "
        + (" | ".join(decision.denials) if decision.denials
           else "no denial recorded, which itself denies")
    )


def locked_panel_placeholder(panel_id: str, decision: GateDecision) -> dict[str, Any]:
    """What a locked findings panel renders instead of its content.

    Deliberately carries NO finding-shaped information: no value, no
    direction, no count-with-implication, not even a hint of magnitude. It
    shows which conditions are unmet, which is progress information and
    explicitly displayable.
    """
    return {
        "panel_id": panel_id,
        "state": "LOCKED",
        "gate": decision.status,
        "why": decision.denials,
        "conditions_met": {k: v for k, v in decision.conditions.items()},
        "what_unlocks_it": (
            "All conditions true simultaneously: status ACTIVE_COLLECTING; "
            "eligible real anchor events >= 193; event-ID set frozen with its "
            "analysis-code commit before any result was computed; every "
            "PENDING_SEPARATE_ANALYSIS_LOCK decision resolved in a dated lock; "
            "and a real (non-placeholder) linkage map."
        ),
        "note": (
            "Reaching a threshold licenses LOOKING, not CONCLUDING. This panel "
            "shows no value, direction, or magnitude while locked."
        ),
        "separately_blocked": (
            "Independently of the conditions above, any quantum-derived result "
            "-- from this project's own tertiary cross-check module or supplied "
            "from outside the repository -- is refused in this panel unless it "
            "has been validated against the classical reference on known cases. "
            "No such validation exists and none is claimed. Opening the gate "
            "does not lift this; it is a separate control."
        ),
    }


def current_decision() -> GateDecision:
    """The gate as it stands right now, from committed artifacts.

    No freeze record exists, no real eligible events exist, and the linkage is
    the Phase 0 placeholder -- so this denies on multiple independent grounds.
    """
    return evaluate_gate(eligible_event_count=0, freeze=None)
