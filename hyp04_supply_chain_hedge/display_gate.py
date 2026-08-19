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

Under registry v1.1, HYP-04 fails C1 (status is
PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED) and fails C4 (four decisions are
still PENDING). So even a hypothetical 193 frozen real events would leave this
gate CLOSED, and that is correct, not a bug: a frozen sample measured through
an unresolved estimator is not a licensed result.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

REGISTRY_V1_1 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
GATES_DOC = LSE / "GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md"

HYPOTHESIS_ID = "HYP-04"
REQUIRED_STATUS = "ACTIVE_COLLECTING"
PENDING_TOKEN = "PENDING_SEPARATE_ANALYSIS_LOCK"

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


def _load_registry(path: Path = REGISTRY_V1_1) -> tuple[Optional[dict], list[str]]:
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
    registry_path: Path = REGISTRY_V1_1,
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
    if not isinstance(threshold, int):
        conditions["C2_threshold"] = False
        denials.append("C2 FAILED: registered threshold is missing or not an integer.")
    elif eligible_event_count is None:
        conditions["C2_threshold"] = False
        denials.append(
            "C2 FAILED: eligible event count is unknown / not mechanically "
            "derivable. An unknown count denies -- it never defaults to zero "
            "or to pass."
        )
    elif not isinstance(eligible_event_count, int) or eligible_event_count < 0:
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
        if (freeze.eligible_event_ids and isinstance(eligible_event_count, int)
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

    # ---- C4: every PENDING decision must be resolved -------------------
    pending = [
        d.get("decision", "<unnamed>")
        for d in entry.get("unresolved_analysis_decisions", [])
        if d.get("state") == PENDING_TOKEN
    ]
    evidence["pending_analysis_decisions"] = len(pending)
    c4 = not pending
    conditions["C4_decisions_resolved"] = c4
    if not c4:
        denials.append(
            f"C4 FAILED: {len(pending)} analysis decision(s) still marked "
            f"{PENDING_TOKEN}. Each must be resolved in a dated analysis lock "
            "written before the freeze. Unresolved: "
            + "; ".join(str(p)[:70] for p in pending)
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
            "C5 FAILED: the underlying linkage is the Phase 0 "
            "positional-synthetic placeholder (peers assigned to anchors by "
            "list position, not by sector or by any real relationship). "
            "Registry v1.1 bars displaying placeholder-linkage results as "
            "HYP-04 findings under any circumstances, at any event count. A "
            "real linkage map is required -- as of 2026-08-18 that means a "
            "hand-curated one, and zero rows are curated."
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


def assert_display_allowed(panel_id: str, decision: GateDecision) -> None:
    """Raise unless this panel may be displayed under this decision.

    Progress panels always pass. Findings panels pass only through an OPEN
    gate. This is the single chokepoint the dashboard calls -- rendering code
    never inspects the conditions itself and never decides for itself.
    """
    if not is_findings_panel(panel_id):
        return
    if decision.open:
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
    }


def current_decision() -> GateDecision:
    """The gate as it stands right now, from committed artifacts.

    No freeze record exists, no real eligible events exist, and the linkage is
    the Phase 0 placeholder -- so this denies on multiple independent grounds.
    """
    return evaluate_gate(eligible_event_count=0, freeze=None)
