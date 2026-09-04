#!/usr/bin/env python3
"""Quantum-derived result provenance control -- HYP-04. FAIL-CLOSED.

This module answers ONE question: may this particular number be shown as a
HYP-04 finding, or be allowed to influence the Stage 1 Link-Strength score?
It answers NO for anything quantum-derived unless a complete validation
attestation says that result was checked against the classical reference on
known cases first.

=== WHY THIS EXISTS SEPARATELY FROM THE FIVE-CONDITION GATE ===

`display_gate.py` gates on the state of the HYPOTHESIS -- status, event count,
freeze, resolved decisions, real linkage. Those five conditions say nothing
about HOW a number was computed. A hypothesis can be in perfect standing and
still be handed a result from a method this project has never validated.

That is a different failure mode and it needs a different control, because:

  * it applies REGARDLESS OF SOURCE. A quantum result computed by this
    project's own tertiary cross-check module and a quantum result supplied
    from outside the repository are treated identically. Neither is privileged
    by having been produced here, and neither is exempted by having been
    produced elsewhere and merely reported.
  * it applies EVEN THROUGH AN OPEN GATE. Opening the five-condition gate
    licenses displaying a CLASSICAL finding. It does not license displaying a
    quantum one. A validated quantum result still needs the gate; an unvalidated
    one is refused whether the gate is open or shut.
  * it is not satisfied by the passage of time or by more data. Only a
    recorded validation against the classical reference satisfies it.

=== THE GOVERNING RULE ===

From the build plan's section on the quantum autocorrelation function (v0.1
section 3, carried into v0.2 section 3.6) -- the plan's own words:

    "...matching this project's own existing pattern of cross-validating novel
    statistical machinery against a trusted reference before it's allowed to
    influence anything (see the R reference bridge under `tools/`), it should
    not be permitted to affect any lock, gate, or hedge decision until it's
    been validated against the classical result on known cases. Treat it the
    same way the R cross-check treats the CR2/Satterthwaite estimator: a check
    on the primary method, not a replacement for it."

The bridge directory is DESCRIBED above rather than named, and that is not
editorial tidying of a quotation. Check 8f of the market-response R-reference
validation suite scans every production module for that literal directory name
and fails if one contains it -- comments included. That suite's own FILENAME
embeds the same string, so it cannot be named here either; this paragraph was
itself rejected once for naming it. market-response-tests.yml documents the identical convention for its
own forbidden entry points: "That scan covers comments too -- which is why the
names of those forbidden entry points are described here rather than spelled
out."

Spelling it out here left 8f RED from 2026-08-19 (81a3bd0) to 2026-09-03, and
nothing could see it. The suite aborts at import without statsmodels, which the
project venv did not carry; and neither workflow that runs the suite triggers on
changes under hyp04_supply_chain_hedge/, so the file that broke the check could
never itself trigger the check. Recorded because a guard that cannot fail
visibly is not a guard.

Build prompt v10 line 77 states the same scoping: tertiary, experimental,
non-load-bearing, isolated, "never feeds into any decision or conclusion".

Until now that rule lived only in prose. Prose does not stop a number. This
module is the rule expressed as a control that raises.

=== NOTHING IS VALIDATED ===

See NO_QUANTUM_RESULT_IS_VALIDATED below. No quantum-derived result -- this
project's or anyone else's -- has been validated against the classical
reference on known cases. No agreement log exists. Nothing here claims
otherwise, and the presence of a validated CODE PATH is a mechanism, not a
claim that anything has ever travelled down it. The same distinction the
display-gate tests draw: the gate can open, and it is shut.

=== FAIL-CLOSED DISCIPLINE ===

Inherited verbatim from the display gate, which inherits it from
`GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` section 4: "Absence of a rule is
never read as permission."

  * an UNDECLARED method family denies -- you cannot validate what you have
    not identified
  * a missing, empty, or unreadable attestation field denies, each on its own
  * an agreement log that does not resolve to a real readable file denies.
    An attestation pointing at a document nobody can open is not evidence, and
    this is specifically what stops an outside supplier from self-attesting.

=== WHAT THIS CONTROL DOES NOT DO ===

It keys on a DECLARED provenance. It cannot read a caller's mind: a quantum
number handed in with no declaration at all is not detectable at runtime by
this or any other function.

That hole is closed structurally rather than dynamically, the same way this
repository closes its other undeclarable holes (CI greps for live-runner
filenames; the display-gate test greps dashboard.py for a locally minted
GateDecision). `test_hyp04_supply_chain_hedge_quantum_provenance.py` asserts
that no module in this package imports any quantum computing library and that
no such library appears in requirements-hyp04.txt -- so "no undeclared quantum
result exists in this package" is a checked fact today, not an assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Union

REPO_ROOT = Path(__file__).resolve().parent.parent

PLAN_DOC = (
    "Live Signal Engine/HYP04_SupplyChain_HedgeLag_MODEL_PLAN_v0.2.md"
)

#: The live state of the world, as of the date below. Read this before
#: reading anything else in this module as permission.
NO_QUANTUM_RESULT_IS_VALIDATED = (
    "As of 2026-08-19 NO quantum-derived result has been validated against the "
    "classical reference on known cases -- not one produced inside this "
    "project, and not one supplied from outside it. No validation has been "
    "run, no agreement log is on file, and none is claimed. Every "
    "quantum-derived result is therefore blocked from every finding panel and "
    "from the Stage 1 Link-Strength score. The validated code path in this "
    "module is a MECHANISM, not a statement that anything has passed through "
    "it."
)


class MethodFamily:
    """How a result was computed. UNKNOWN is a real answer and it denies."""

    CLASSICAL = "classical"
    QUANTUM = "quantum"
    UNKNOWN = "unknown"


class Origin:
    """Where a result came from. Recorded, but never a basis for exemption."""

    INTERNAL_PRIMARY = "internal_primary"
    INTERNAL_TERTIARY_CROSS_CHECK = "internal_tertiary_cross_check"
    EXTERNAL = "external"


#: Families that must clear a classical-validation attestation before use.
#: UNKNOWN is included deliberately: an undeclared method cannot be shown to
#: be classical, and under fail-closed discipline that is a denial, not a
#: default to the permissive case.
REQUIRES_CLASSICAL_VALIDATION = (MethodFamily.QUANTUM, MethodFamily.UNKNOWN)


class ProvenanceError(RuntimeError):
    """Raised when a result's provenance does not permit the requested use."""


class QuantumProvenanceError(ProvenanceError):
    """Raised specifically for an unvalidated quantum-derived result."""


@dataclass(frozen=True)
class ClassicalValidation:
    """Attestation that a quantum-derived result was checked classically first.

    Frozen on purpose. A caller that could mutate an attestation after the
    guard read it would be able to defeat the guard, and there is no legitimate
    reason to edit one in place -- build a new one with `dataclasses.replace`.

    Every field defaults to the DENYING value. An attestation constructed with
    no arguments attests to nothing and is refused, which is the correct
    reading of an empty form.
    """

    #: The explicit claim. False, missing, or absent all deny.
    validated_against_classical_reference: bool = False
    #: WHICH classical result was compared against -- named, not implied.
    classical_reference_result: Optional[str] = None
    #: The known cases the comparison ran on. Zero cases is not a validation.
    known_cases: tuple[str, ...] = ()
    #: Repo-relative path to the dated agreement/disagreement log. Must resolve
    #: to a real readable file under the repo root.
    agreement_log_document: Optional[str] = None
    #: The validation must predate the use, exactly as the freeze must predate
    #: the result. A check assembled afterwards to bless a number already in
    #: hand is a rationalisation, not a validation.
    validated_before_this_result_was_used: bool = False
    #: Who performed it. Recorded for audit; not itself a pass condition.
    validator: Optional[str] = None


@dataclass(frozen=True)
class MethodProvenance:
    """How a result was produced, declared by whoever is presenting it.

    Defaults are the denying ones: an unparameterised MethodProvenance is an
    UNKNOWN-family EXTERNAL result with no validation, which is refused
    everywhere. Declaring nothing is never the permissive case.
    """

    method_family: str = MethodFamily.UNKNOWN
    origin: str = Origin.EXTERNAL
    description: str = ""
    validation: Optional[ClassicalValidation] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "method_family": self.method_family,
            "origin": self.origin,
            "description": self.description,
            "validation_supplied": self.validation is not None,
        }


#: Convenience for the ordinary case: this package's own classical estimators
#: (local projections, prewhitened CCF, ridge). Not an exemption -- it is a
#: declaration that happens to be of the family that needs no attestation.
CLASSICAL_INTERNAL = MethodProvenance(
    method_family=MethodFamily.CLASSICAL,
    origin=Origin.INTERNAL_PRIMARY,
    description=(
        "Classical estimator implemented in hyp04_supply_chain_hedge "
        "(local projections / prewhitened CCF / closed-form ridge)."
    ),
)


def requires_classical_validation(provenance: Optional[MethodProvenance]) -> bool:
    """True if this provenance must clear an attestation before use.

    `None` -- no declaration at all -- returns False, because there is nothing
    to evaluate. That is NOT a statement that the result is classical; it is
    the boundary of what a runtime check can see. See the module docstring's
    "WHAT THIS CONTROL DOES NOT DO", and the structural test that closes it.
    """
    if provenance is None:
        return False
    return provenance.method_family in REQUIRES_CLASSICAL_VALIDATION


def validation_denials(
    provenance: Optional[MethodProvenance],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    """Every reason this provenance is refused. Empty list means permitted.

    Reasons accumulate rather than short-circuit, so a caller trying to comply
    sees the whole list at once instead of fixing one field per attempt.
    """
    if not requires_classical_validation(provenance):
        return []

    assert provenance is not None  # narrowed by requires_classical_validation
    denials: list[str] = []

    if provenance.method_family == MethodFamily.UNKNOWN:
        denials.append(
            "method family is UNKNOWN -- an undeclared method cannot be "
            "validated, because there is no statement of what would have been "
            "validated. Declare the family."
        )

    v = provenance.validation
    if v is None:
        denials.append(
            "no classical-validation attestation was supplied. A "
            "quantum-derived result is refused by default; the plan permits it "
            "only once it has 'been validated against the classical result on "
            f"known cases' ({PLAN_DOC}, section 3)."
        )
        return denials

    if not v.validated_against_classical_reference:
        denials.append(
            "the attestation does not claim validation against the classical "
            "reference."
        )
    if not v.classical_reference_result:
        denials.append(
            "the attestation does not name WHICH classical reference result "
            "was compared against. 'Validated' without a named reference is "
            "not checkable."
        )
    if not v.known_cases:
        denials.append(
            "the attestation lists zero known cases. Validation on no cases is "
            "not validation."
        )
    if not v.validated_before_this_result_was_used:
        denials.append(
            "the attestation does not state that validation happened BEFORE "
            "this result was used. A check assembled afterwards to bless a "
            "number already in hand is not a validation, for the same reason a "
            "freeze recorded after the fact is not a freeze."
        )

    if not v.agreement_log_document:
        denials.append(
            "the attestation records no dated agreement/disagreement log "
            "document."
        )
    else:
        log_path = Path(v.agreement_log_document)
        if not log_path.is_absolute():
            log_path = repo_root / log_path
        if not log_path.is_file():
            denials.append(
                f"the agreement log {v.agreement_log_document!r} does not "
                "resolve to a readable file. An attestation pointing at a "
                "document nobody can open is not evidence -- this is what "
                "prevents an externally supplied result from self-attesting."
            )

    return denials


def is_permitted(
    provenance: Optional[MethodProvenance],
    *,
    repo_root: Path = REPO_ROOT,
) -> bool:
    """Whether this provenance clears the quantum control. No side effects."""
    return not validation_denials(provenance, repo_root=repo_root)


def _raise(context: str, provenance: MethodProvenance, denials: list[str]) -> None:
    raise QuantumProvenanceError(
        f"REFUSED: {context}. A {provenance.method_family}-family result from "
        f"{provenance.origin!r} is blocked until it has been validated against "
        f"the classical reference on known cases ({PLAN_DOC}, section 3). "
        + " | ".join(denials)
    )


def assert_may_display(
    panel_id: str,
    provenance: Optional[MethodProvenance],
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    """Raise unless this provenance may appear in this panel.

    Applies to EVERY panel, findings and progress alike. A quantum-derived
    model output has no business in either, and restricting the block to
    findings panels would leave the progress lane as a bypass.

    A statement ABOUT the quantum module -- "skipped, no citable construction
    exists" -- is a status, not a model output, and is not routed through here.
    What is routed through here is a NUMBER the module produced.
    """
    denials = validation_denials(provenance, repo_root=repo_root)
    if denials:
        assert provenance is not None
        _raise(f"display of {panel_id!r}", provenance, denials)


def assert_may_influence_link_strength(
    contributors: Union[
        None, MethodProvenance, Iterable[Optional[MethodProvenance]]
    ],
    *,
    context: str = "the Stage 1 Link-Strength score",
    repo_root: Path = REPO_ROOT,
) -> None:
    """Raise unless every declared contributor may feed the Link-Strength score.

    Accepts a single provenance or an iterable of them, because a score can
    have several contributing inputs and each must clear the control
    independently -- one unvalidated feature is enough to refuse the score it
    feeds. "Influence" is read broadly: a feature, a weight, a prior, a
    selection criterion, or a post-hoc adjustment all count.
    """
    if contributors is None:
        return
    items: list[Optional[MethodProvenance]]
    if isinstance(contributors, MethodProvenance):
        items = [contributors]
    else:
        items = list(contributors)

    for p in items:
        denials = validation_denials(p, repo_root=repo_root)
        if denials:
            assert p is not None
            _raise(f"contribution to {context}", p, denials)


def current_status() -> dict[str, Any]:
    """The live control state, for the dashboard and the status doc.

    Every value here is PROGRESS information -- a statement about which
    controls exist and what they currently permit. It contains no finding.
    """
    return {
        "control": "quantum-derived result provenance",
        "applies_to": [
            "every finding panel (and every progress panel)",
            "the Stage 1 Link-Strength score and anything feeding it",
        ],
        "independent_of_the_five_condition_gate": True,
        "sources_covered": [
            Origin.INTERNAL_PRIMARY,
            Origin.INTERNAL_TERTIARY_CROSS_CHECK,
            Origin.EXTERNAL,
        ],
        "validated_results_on_file": 0,
        "agreement_logs_on_file": 0,
        "status": NO_QUANTUM_RESULT_IS_VALIDATED,
        "governing_document": PLAN_DOC,
        "fail_closed": "Absence of a rule is never read as permission.",
    }
