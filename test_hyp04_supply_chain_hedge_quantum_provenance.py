#!/usr/bin/env python3
"""Quantum-derived result provenance tests -- HYP-04.

WHAT THIS PINS DOWN. The five-condition display gate governs results produced
by this project's own classical pipeline. It says nothing about HOW a number
was computed, so on its own it would let a result from an unvalidated method
through an open gate. `quantum_provenance.py` is the separate control for
that, and this file tests it.

THE SCENARIO IT WAS BUILT FOR: someone runs a quantum model against
anchor/event/neighbour panel data, outside any lock, CV or placebo process, and
reports a number. It does not matter whether that someone is this project's own
tertiary cross-check module or a person outside the repository handing over a
result. Both are refused identically, and test_3 asserts exactly that -- source
is recorded, never an exemption.

THE PATTERN IS THE DISPLAY GATE'S, deliberately: a one-directional test proves
nothing, because a control hardcoded to DENY passes every "must be blocked"
test and is useless.

  * a control hardcoded to DENY would pass tests 2, 3, 4, 6, 8. So test_5
    supplies a COMPLETE synthetic attestation and asserts it is permitted.
  * a control hardcoded to PERMIT would pass test_5. So test_4 falsifies each
    attestation field INDIVIDUALLY, with every other field held true, and each
    must deny on its own.

Neither direction alone proves anything. Both together pin the control.

NOTHING IS ACTUALLY VALIDATED. Test_5's attestation is synthetic, built in a
temp directory, and asserts that the MECHANISM can pass -- exactly as the gate
suite's test_9 asserts the gate mechanism can open while the real gate stays
shut on five grounds. No quantum-derived result, this project's or anyone
else's, has been validated against the classical reference. Test_1 asserts the
live state says so.

Offline. No network. Synthetic provenance records only.

Run directly: python test_hyp04_supply_chain_hedge_quantum_provenance.py
"""
from __future__ import annotations

import dataclasses
import json
import re
import socket
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline provenance test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

from hyp04_supply_chain_hedge.display_gate import (  # noqa: E402
    FINDINGS_PANELS,
    PROGRESS_PANELS,
    REGISTRY_V1_1,
    RESOLVED_BY_FIELD,
    RESOLVED_TOKEN,
    FreezeRecord,
    GateError,
    assert_display_allowed,
    current_decision,
    evaluate_gate,
)
from hyp04_supply_chain_hedge.quantum_provenance import (  # noqa: E402
    CLASSICAL_INTERNAL,
    NO_QUANTUM_RESULT_IS_VALIDATED,
    ClassicalValidation,
    MethodFamily,
    MethodProvenance,
    Origin,
    ProvenanceError,
    QuantumProvenanceError,
    assert_may_display,
    assert_may_influence_link_strength,
    current_status,
    is_permitted,
    validation_denials,
)

REPO_ROOT = Path(__file__).resolve().parent
PKG = REPO_ROOT / "hyp04_supply_chain_hedge"

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
_REAL = json.loads(REGISTRY_V1_1.read_text(encoding="utf-8-sig"))


def _registry_variant(tmpdir: Path, *, status: str, pending: bool,
                      threshold: int = 193) -> Path:
    """A hypothetical FUTURE registry state, synthesised in a temp file.

    Same device the gate suite uses: to test what happens through an OPEN gate
    we need a registry where HYP-04 is ACTIVE_COLLECTING with nothing pending.
    That state does not exist today and is never written to the real registry.
    """
    doc = json.loads(json.dumps(_REAL))
    for h in doc["hypotheses"]:
        if h["hypothesis_id"] == "HYP-04":
            h["status"] = status
            h["minimum_eligible_events"] = threshold
            if not pending:
                # A real resolution: every decision stays in the ledger, marked
                # resolved and citing the lock. Emptying the ledger is a
                # deletion, not a resolution, and C4 denies it.
                for d in h["unresolved_analysis_decisions"]:
                    d["state"] = RESOLVED_TOKEN
                    d[RESOLVED_BY_FIELD] = "GST_HYP04_ANALYSIS_LOCK_v1.0.json"
    p = tmpdir / "registry_variant.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _good_freeze(n: int = 193) -> FreezeRecord:
    return FreezeRecord(
        frozen=True,
        eligible_event_ids=tuple(f"EVT-SYNTH-{i:04d}" for i in range(n)),
        analysis_commit_sha="0" * 40,
        analysis_lock_document="GST_HYP04_ANALYSIS_LOCK_v1.0.json",
        frozen_before_any_result_computed=True,
        uses_placeholder_linkage=False,
    )


def _open_gate(td: Path):
    """A fully OPEN five-condition gate. Synthetic; the real one is shut."""
    reg = _registry_variant(td, status="ACTIVE_COLLECTING", pending=False)
    return evaluate_gate(eligible_event_count=193, freeze=_good_freeze(),
                         registry_path=reg)


EXTERNAL_QUANTUM = MethodProvenance(
    method_family=MethodFamily.QUANTUM,
    origin=Origin.EXTERNAL,
    description=(
        "Variational quantum circuit with device-noise simulation, run outside "
        "this repository against an anchor/event/neighbour panel; an "
        "information coefficient was reported."
    ),
)

OUR_QUANTUM = MethodProvenance(
    method_family=MethodFamily.QUANTUM,
    origin=Origin.INTERNAL_TERTIARY_CROSS_CHECK,
    description="This package's own tertiary quantum autocorrelation cross-check.",
)

UNDECLARED = MethodProvenance()  # every default is the denying one


def _complete_validation(log: Path) -> ClassicalValidation:
    """A synthetic attestation with every field satisfied. Not a real one."""
    return ClassicalValidation(
        validated_against_classical_reference=True,
        classical_reference_result="SYNTHETIC prewhitened-CCF cross-check (test fixture)",
        known_cases=("SYNTHETIC_case_a", "SYNTHETIC_case_b"),
        agreement_log_document=log.name,
        validated_before_this_result_was_used=True,
        validator="SYNTHETIC test fixture -- not a real validation",
    )


# ============== 1. the live state: nothing is validated ===================
def test_1_nothing_is_validated_today() -> None:
    s = current_status()
    check("1a. zero validated quantum results are on file",
          s["validated_results_on_file"] == 0)
    check("1b. zero agreement logs are on file",
          s["agreement_logs_on_file"] == 0)
    check("1c. the status text states plainly that nothing is validated",
          "NO quantum-derived result has been validated" in s["status"])
    check("1d. and that no such claim is being made",
          "none is claimed" in NO_QUANTUM_RESULT_IS_VALIDATED)
    check("1e. the control is declared independent of the five-condition gate",
          s["independent_of_the_five_condition_gate"] is True)
    check("1f. it covers external as well as internal sources",
          Origin.EXTERNAL in s["sources_covered"]
          and Origin.INTERNAL_TERTIARY_CROSS_CHECK in s["sources_covered"])
    check("1g. a classical internal declaration needs no attestation",
          is_permitted(CLASSICAL_INTERNAL),
          "otherwise the control would block the classical pipeline too")


# ===== 2. THE SCENARIO: an external quantum result into a finding panel ====
def test_2_external_quantum_result_is_refused_by_a_finding_panel() -> None:
    """Feed a quantum-sourced result into a finding panel with no validation
    flag set. It must be rejected -- through a closed gate AND an open one."""
    closed = current_decision()

    raised = []
    for panel in FINDINGS_PANELS:
        try:
            assert_display_allowed(panel, closed, EXTERNAL_QUANTUM)
            raised.append(panel)
        except (QuantumProvenanceError, GateError):
            pass
    check("2a. every finding panel refuses it through the closed gate",
          not raised, f"these rendered: {raised[:3]}")

    # The important half: an OPEN gate must NOT let it through. If the quantum
    # block were folded into the five conditions, satisfying them would release
    # this result, which is the exact failure this control exists to prevent.
    with tempfile.TemporaryDirectory() as td:
        d = _open_gate(Path(td))
        check("2b. precondition -- the synthetic gate really is OPEN",
              d.open is True, f"denials={d.denials}")

        leaked = []
        for panel in FINDINGS_PANELS:
            try:
                assert_display_allowed(panel, d, EXTERNAL_QUANTUM)
                leaked.append(panel)
            except QuantumProvenanceError:
                pass
        check("2c. every finding panel STILL refuses it through the OPEN gate",
              not leaked, f"these leaked: {leaked[:3]}")

        # ... while the same panel accepts a classical result, so 2c is not
        # vacuous -- it is the quantum provenance being refused, not the panel
        # refusing everything.
        try:
            assert_display_allowed("onset_horizon", d, CLASSICAL_INTERNAL)
            check("2d. CONTROL -- a classical result IS permitted through the "
                  "same open gate", True)
        except ProvenanceError as e:
            check("2d. CONTROL -- a classical result IS permitted through the "
                  "same open gate", False, str(e))

    check("2e. the refusal names the missing validation, not something vague",
          any("validated against the classical" in x
              for x in validation_denials(EXTERNAL_QUANTUM)))
    check("2f. and it names the governing plan document",
          any("MODEL_PLAN" in x for x in validation_denials(EXTERNAL_QUANTUM)))


# ============ 3. our own module gets no better treatment ==================
def test_3_our_own_quantum_module_is_refused_identically() -> None:
    """Source is recorded. It is never an exemption, in either direction."""
    ours = validation_denials(OUR_QUANTUM)
    theirs = validation_denials(EXTERNAL_QUANTUM)
    check("3a. our own tertiary quantum cross-check is refused", bool(ours))
    check("3b. an externally supplied quantum result is refused", bool(theirs))
    check("3c. and for the SAME reasons -- origin changes nothing",
          ours == theirs, f"ours={ours}\ntheirs={theirs}")

    with tempfile.TemporaryDirectory() as td:
        d = _open_gate(Path(td))
        for label, prov in (("ours", OUR_QUANTUM), ("theirs", EXTERNAL_QUANTUM)):
            try:
                assert_display_allowed("link_strength_scores", d, prov)
                check(f"3d. {label}: refused through an open gate", False,
                      "it rendered")
            except QuantumProvenanceError:
                check(f"3d. {label}: refused through an open gate", True)


# ====== 4. each attestation field falsified ALONE (anti-hardcoded-PERMIT) ==
def test_4_each_attestation_field_denies_on_its_own() -> None:
    """Hold every field true but one. Each omission must deny by itself."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        log = tdp / "SYNTHETIC_AGREEMENT_LOG.md"
        log.write_text("synthetic test fixture\n", encoding="utf-8")
        complete = _complete_validation(log)

        # Precondition: the complete attestation passes. Without this, every
        # falsification below would "deny" for an unrelated reason and the
        # test would prove nothing.
        base = MethodProvenance(method_family=MethodFamily.QUANTUM,
                                origin=Origin.EXTERNAL, validation=complete)
        check("4a. precondition -- the complete attestation is permitted",
              is_permitted(base, repo_root=tdp),
              str(validation_denials(base, repo_root=tdp)))

        falsifications = {
            "the validation claim itself unset":
                {"validated_against_classical_reference": False},
            "no classical reference named":
                {"classical_reference_result": None},
            "zero known cases":
                {"known_cases": ()},
            "no agreement log recorded":
                {"agreement_log_document": None},
            "agreement log points at a nonexistent file":
                {"agreement_log_document": "no_such_agreement_log.md"},
            "validation not stated to predate the result":
                {"validated_before_this_result_was_used": False},
        }
        for label, override in falsifications.items():
            v = dataclasses.replace(complete, **override)
            p = MethodProvenance(method_family=MethodFamily.QUANTUM,
                                 origin=Origin.EXTERNAL, validation=v)
            denials = validation_denials(p, repo_root=tdp)
            check(f"4b. '{label}' alone denies", bool(denials))
            try:
                assert_may_display("onset_horizon", p, repo_root=tdp)
                check(f"4c. '{label}' alone raises at the display chokepoint",
                      False, "it was permitted")
            except QuantumProvenanceError:
                check(f"4c. '{label}' alone raises at the display chokepoint", True)

        # No attestation at all.
        check("4d. a quantum result with no attestation denies",
              bool(validation_denials(EXTERNAL_QUANTUM, repo_root=tdp)))

        # An empty attestation form attests to nothing.
        empty = MethodProvenance(method_family=MethodFamily.QUANTUM,
                                 origin=Origin.EXTERNAL,
                                 validation=ClassicalValidation())
        d_empty = validation_denials(empty, repo_root=tdp)
        check("4e. a blank attestation form denies", bool(d_empty))
        check("4f. and reports every unmet field at once, not one per attempt",
              len(d_empty) >= 4, f"{len(d_empty)} denial(s)")


# ============ 5. the other direction: the control CAN permit ==============
def test_5_a_complete_attestation_is_permitted() -> None:
    """Without this, a control hardcoded to DENY would pass everything above.

    This asserts the MECHANISM works. The attestation is synthetic, lives in a
    temp directory, and says so in its own fields. It is not a claim that any
    quantum result has been validated -- none has.
    """
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        log = tdp / "SYNTHETIC_AGREEMENT_LOG.md"
        log.write_text("synthetic test fixture\n", encoding="utf-8")

        for label, origin in (("external", Origin.EXTERNAL),
                              ("our own module", Origin.INTERNAL_TERTIARY_CROSS_CHECK)):
            p = MethodProvenance(method_family=MethodFamily.QUANTUM,
                                 origin=origin,
                                 validation=_complete_validation(log))
            check(f"5a. a fully attested quantum result from {label} is permitted",
                  is_permitted(p, repo_root=tdp),
                  str(validation_denials(p, repo_root=tdp)))
            try:
                assert_may_display("onset_horizon", p, repo_root=tdp)
                check(f"5b. {label}: it clears the display chokepoint", True)
            except QuantumProvenanceError as e:
                check(f"5b. {label}: it clears the display chokepoint", False, str(e))
            try:
                assert_may_influence_link_strength(p, repo_root=tdp)
                check(f"5c. {label}: it clears the Link-Strength chokepoint", True)
            except QuantumProvenanceError as e:
                check(f"5c. {label}: it clears the Link-Strength chokepoint",
                      False, str(e))


# ============ 6. an undeclared method family denies ========================
def test_6_undeclared_method_family_denies() -> None:
    """You cannot validate what you have not identified."""
    check("6a. an unparameterised provenance defaults to UNKNOWN",
          UNDECLARED.method_family == MethodFamily.UNKNOWN)
    check("6b. and to EXTERNAL, the less-trusted origin",
          UNDECLARED.origin == Origin.EXTERNAL)
    check("6c. it is refused", bool(validation_denials(UNDECLARED)))

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        log = tdp / "SYNTHETIC_AGREEMENT_LOG.md"
        log.write_text("synthetic test fixture\n", encoding="utf-8")
        # Even a COMPLETE attestation cannot rescue an UNKNOWN family: the
        # attestation would not say what had been validated.
        p = MethodProvenance(method_family=MethodFamily.UNKNOWN,
                             origin=Origin.EXTERNAL,
                             validation=_complete_validation(log))
        denials = validation_denials(p, repo_root=tdp)
        check("6d. UNKNOWN denies even with a complete attestation", bool(denials))
        check("6e. and says why -- an undeclared method cannot be validated",
              any("UNKNOWN" in x for x in denials))

    # Through an OPEN gate, declaring nothing at all is also refused.
    with tempfile.TemporaryDirectory() as td:
        d = _open_gate(Path(td))
        try:
            assert_display_allowed("onset_horizon", d, None)
            check("6f. an undeclared provenance is refused through an open gate",
                  False, "it rendered")
        except ProvenanceError:
            check("6f. an undeclared provenance is refused through an open gate",
                  True)


# ============ 7. progress panels are not a bypass ==========================
def test_7_progress_panels_are_not_a_bypass() -> None:
    """Progress panels always pass the GATE. They do not bypass this control."""
    closed = current_decision()
    for p in PROGRESS_PANELS:
        try:
            assert_display_allowed(p, closed, CLASSICAL_INTERNAL)
            check(f"7a. {p} still renders classical content", True)
        except ProvenanceError:
            check(f"7a. {p} still renders classical content", False)
        try:
            assert_display_allowed(p, closed, EXTERNAL_QUANTUM)
            check(f"7b. {p} refuses unvalidated quantum content", False,
                  "a progress panel became a bypass")
        except QuantumProvenanceError:
            check(f"7b. {p} refuses unvalidated quantum content", True)


# ============ 8. the Stage 1 Link-Strength score ===========================
def test_8_quantum_cannot_influence_the_link_strength_score() -> None:
    from hyp04_supply_chain_hedge.inference import leave_one_anchor_out_cv
    from hyp04_supply_chain_hedge.stage2 import (
        PeerOptionsConditions,
        Stage1Score,
        select_hedge_structure,
    )

    liquid = PeerOptionsConditions("P", open_interest=5000, option_volume=500,
                                   bid_ask_spread_pct_of_mid=0.05,
                                   put_skew=0.01, implied_vol=0.30)

    # Baseline: an undeclared (classical, today) score still works. Without
    # this, 8b could pass because Stage 2 rejects everything.
    plain = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=9,
                        lag_ci_width_days=1.0, significant=True)
    try:
        rec = select_hedge_structure(plain, liquid)
        check("8a. CONTROL -- an ordinary score still produces a recommendation",
              rec.structure is not None)
    except ProvenanceError as e:
        check("8a. CONTROL -- an ordinary score still produces a recommendation",
              False, str(e))

    quantum_score = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=9,
                                lag_ci_width_days=1.0, significant=True,
                                link_strength_provenance=EXTERNAL_QUANTUM)
    try:
        select_hedge_structure(quantum_score, liquid)
        check("8b. a quantum-derived Link-Strength score is refused by Stage 2",
              False, "it produced a recommendation")
    except QuantumProvenanceError:
        check("8b. a quantum-derived Link-Strength score is refused by Stage 2", True)

    # It must RAISE, not quietly return NO_POSITION. Declining to act because
    # of what the number said is still the number affecting the decision.
    weak_quantum = Stage1Score("P", 0.01, onset_horizon=5, peak_horizon=9,
                               lag_ci_width_days=1.0, significant=True,
                               link_strength_provenance=EXTERNAL_QUANTUM)
    try:
        r = select_hedge_structure(weak_quantum, liquid)
        check("8c. it raises rather than returning a null recommendation",
              False, f"returned {r.rule_fired}")
    except QuantumProvenanceError:
        check("8c. it raises rather than returning a null recommendation", True)

    # One bad contributor among several is enough.
    mixed = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=9,
                        lag_ci_width_days=1.0, significant=True,
                        link_strength_provenance=[CLASSICAL_INTERNAL,
                                                  CLASSICAL_INTERNAL,
                                                  OUR_QUANTUM])
    try:
        select_hedge_structure(mixed, liquid)
        check("8d. one unvalidated contributor among several refuses the score",
              False, "it produced a recommendation")
    except QuantumProvenanceError:
        check("8d. one unvalidated contributor among several refuses the score", True)

    all_classical = Stage1Score("P", 0.8, onset_horizon=5, peak_horizon=9,
                                lag_ci_width_days=1.0, significant=True,
                                link_strength_provenance=[CLASSICAL_INTERNAL,
                                                          CLASSICAL_INTERNAL])
    try:
        select_hedge_structure(all_classical, liquid)
        check("8e. CONTROL -- all-classical contributors are permitted", True)
    except ProvenanceError as e:
        check("8e. CONTROL -- all-classical contributors are permitted", False, str(e))

    # The model fit itself. An empty table is passed deliberately: the guard
    # must raise BEFORE any data is read, so a quantum feature never reaches a
    # solve. A KeyError here would mean the guard runs too late.
    try:
        leave_one_anchor_out_cv({}, horizon=5, feature_provenance=EXTERNAL_QUANTUM)
        check("8f. a quantum feature is refused by the ridge fit", False,
              "the fit ran")
    except QuantumProvenanceError:
        check("8f. a quantum feature is refused by the ridge fit", True)
    except KeyError:
        check("8f. a quantum feature is refused by the ridge fit", False,
              "it reached the data before checking provenance")


# ============ 9. the consumers cannot route around the control =============
def test_9_consumers_cannot_route_around_it() -> None:
    """Source-level checks, mirroring the gate suite's dashboard test.

    A control that a caller can simply not call is not a control.
    """
    gate_src = (PKG / "display_gate.py").read_text(encoding="utf-8")
    check("9a. the display gate delegates to the shared quantum chokepoint",
          "assert_may_display" in gate_src)
    check("9b. and does not reimplement the validation logic locally",
          "def validation_denials" not in gate_src
          and "def assert_may_display" not in gate_src)

    dash_src = (PKG / "dashboard.py").read_text(encoding="utf-8")
    check("9c. the dashboard forwards provenance rather than judging it",
          "provenance" in dash_src
          and not re.findall(r"def\s+(validation_denials|assert_may_display)",
                             dash_src))
    check("9d. the dashboard never mints its own attestation",
          not re.findall(r"ClassicalValidation\s*\(", dash_src),
          "constructing one would let the renderer bless its own content")

    s2_src = (PKG / "stage2.py").read_text(encoding="utf-8")
    check("9e. Stage 2 calls the Link-Strength chokepoint",
          "assert_may_influence_link_strength" in s2_src)
    check("9f. and never mints its own attestation",
          not re.findall(r"ClassicalValidation\s*\(", s2_src))

    inf_src = (PKG / "inference.py").read_text(encoding="utf-8")
    check("9g. the Link-Strength fit calls the chokepoint",
          "assert_may_influence_link_strength" in inf_src)
    check("9h. and never mints its own attestation",
          not re.findall(r"ClassicalValidation\s*\(", inf_src))


# ============ 10. structural: no undeclared quantum code exists ============
def test_10_no_quantum_computation_exists_in_the_package() -> None:
    """Closes the hole a runtime check cannot see.

    The control keys on a DECLARED provenance, so an undeclared quantum number
    is not detectable at runtime -- by this or any other function. What IS
    checkable is that no quantum computation exists here to be undeclared. If
    one is ever added, this fails and forces it through the declared API.

    Same device CI uses when it greps for live-runner filenames, and the gate
    suite when it greps dashboard.py for a locally minted GateDecision.
    """
    libs = ("qiskit", "pennylane", "cirq", "braket", "qutip",
            "tensorflow_quantum", "pyquil", "strawberryfields", "qulacs")

    offenders: list[str] = []
    for py in sorted(PKG.glob("*.py")):
        src = py.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ")
                    or stripped.startswith("from ")):
                continue
            for lib in libs:
                if re.search(rf"\b{lib}\b", stripped):
                    offenders.append(f"{py.name}: {stripped}")
    check("10a. no module in the package imports a quantum computing library",
          not offenders, f"{offenders[:3]}")

    reqs = (REPO_ROOT / "requirements-hyp04.txt").read_text(encoding="utf-8")
    declared = [ln.strip() for ln in reqs.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    req_offenders = [ln for ln in declared
                     if any(re.search(rf"\b{lib}\b", ln.lower()) for lib in libs)]
    check("10b. no quantum computing library is a declared dependency",
          not req_offenders, f"{req_offenders}")

    # And the guard module is actually wired in, not orphaned -- an unimported
    # control is decoration.
    importers = [py.name for py in sorted(PKG.glob("*.py"))
                 if "quantum_provenance" in py.read_text(encoding="utf-8")
                 and py.name != "quantum_provenance.py"]
    check("10c. the control is imported by the modules it governs",
          {"display_gate.py", "stage2.py", "inference.py"} <= set(importers),
          f"importers={importers}")


# ============ 11. the two controls stay independent ========================
def test_11_the_two_controls_are_independent() -> None:
    """Neither control is allowed to stand in for the other."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        log = tdp / "SYNTHETIC_AGREEMENT_LOG.md"
        log.write_text("synthetic test fixture\n", encoding="utf-8")
        attested = MethodProvenance(method_family=MethodFamily.QUANTUM,
                                    origin=Origin.EXTERNAL,
                                    validation=_complete_validation(log))
        check("11a. a fully attested quantum result is permitted by the control",
              is_permitted(attested, repo_root=tdp))

    # Clearing the quantum control does not open the gate. Demonstrated with a
    # CLASSICAL provenance, which satisfies the quantum control outright: that
    # isolates the gate as the sole remaining reason for refusal. (Using the
    # attested quantum record above would not work here -- its agreement log
    # lives in a temp directory, and the real chokepoint resolves paths against
    # the real repo root, so it would be refused by the quantum control for an
    # unrelated reason and prove nothing about the gate.)
    closed = current_decision()
    check("11b. precondition -- the real gate is closed", closed.open is False)
    check("11b2. precondition -- this provenance clears the quantum control",
          is_permitted(CLASSICAL_INTERNAL))
    try:
        assert_display_allowed("onset_horizon", closed, CLASSICAL_INTERNAL)
        check("11c. clearing the quantum control does not open the gate",
              False, "it rendered")
    except GateError:
        check("11c. clearing the quantum control does not open the gate", True)

    # The converse: an OPEN gate does not clear the quantum control. Already
    # asserted in 2c; restated here so the pairing is visible in one place.
    with tempfile.TemporaryDirectory() as td:
        d = _open_gate(Path(td))
        try:
            assert_display_allowed("onset_horizon", d, EXTERNAL_QUANTUM)
            check("11d. an open gate does not clear the quantum control", False,
                  "it rendered")
        except QuantumProvenanceError:
            check("11d. an open gate does not clear the quantum control", True)


def test_12_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("12a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("12a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_nothing_is_validated_today()
    test_2_external_quantum_result_is_refused_by_a_finding_panel()
    test_3_our_own_quantum_module_is_refused_identically()
    test_4_each_attestation_field_denies_on_its_own()
    test_5_a_complete_attestation_is_permitted()
    test_6_undeclared_method_family_denies()
    test_7_progress_panels_are_not_a_bypass()
    test_8_quantum_cannot_influence_the_link_strength_score()
    test_9_consumers_cannot_route_around_it()
    test_10_no_quantum_computation_exists_in_the_package()
    test_11_the_two_controls_are_independent()
    test_12_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 QUANTUM-PROVENANCE TESTS PASSED")
    sys.exit(0)
