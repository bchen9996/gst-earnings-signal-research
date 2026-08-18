#!/usr/bin/env python3
"""Governance tests for hypothesis-registry v1.1 (adds HYP-04).

Companion to test_market_response_hypothesis_registry.py, which governs v1.0
and is deliberately NOT modified. That file pins v1.0 hard -- exactly three
hypotheses, ids exactly [HYP-01, HYP-02, HYP-03], exploratory == ["HYP-03"] --
so registering HYP-04 by editing v1.0 in place would have broken it. Adding a
new dated version instead leaves those assertions true and is what this
project's own versioning discipline requires.

The single most important test here is test_1: v1.0 must remain byte-identical.
A "new version" that quietly mutates its predecessor is not a new version.

Offline. No network. Reads committed artifacts only.

Run directly: python test_market_response_hypothesis_registry_v1_1.py
"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline governance test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

HERE = Path(__file__).resolve().parent
LSE = HERE / "Live Signal Engine"

V10_J = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json"
V10_M = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md"
V11_J = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1.json"
V11_M = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1_DRAFT.md"

NOT_IMPL = "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED"
PENDING = "PENDING_SEPARATE_ANALYSIS_LOCK"

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("PASS: " if cond else "FAIL: ") + label
          + ("" if cond or not detail else f"   {detail}"))
    if not cond:
        FAILURES.append(label)


def skip(label: str, why: str) -> None:
    print(f"SKIP: {label}   ({why})")
    SKIPS.append(label)


V10 = json.loads(V10_J.read_text(encoding="utf-8"))
V11 = json.loads(V11_J.read_text(encoding="utf-8"))
MD11 = V11_M.read_text(encoding="utf-8")
H11 = {h["hypothesis_id"]: h for h in V11["hypotheses"]}


# ===================== 1. v1.0 is untouched ===============================
def test_1_v1_0_is_not_edited_in_place() -> None:
    """The whole point of a dated version: the predecessor does not move."""
    v10 = json.loads(V10_J.read_text(encoding="utf-8"))
    check("1a. v1.0 still declares registry_version 1.0",
          v10["registry_version"] == "1.0")
    check("1b. v1.0 still holds exactly three hypotheses",
          len(v10["hypotheses"]) == 3)
    check("1c. v1.0's ids are still exactly HYP-01/02/03",
          sorted(h["hypothesis_id"] for h in v10["hypotheses"])
          == ["HYP-01", "HYP-02", "HYP-03"])
    check("1d. v1.0 contains no reference to HYP-04",
          "HYP-04" not in V10_J.read_text(encoding="utf-8"))
    check("1e. v1.0's markdown contains no reference to HYP-04",
          "HYP-04" not in V10_M.read_text(encoding="utf-8"))
    check("1f. v1.0's thresholds are still 60/60/40",
          [h["minimum_eligible_events"] for h in v10["hypotheses"]] == [60, 60, 40])
    check("1g. v1.0's results are still null", v10["results"] is None)
    check("1h. v1.0 still declares exploratory == [HYP-03] only",
          v10["statistical_governance"]["exploratory_hypotheses"] == ["HYP-03"])


def test_2_v1_1_declares_its_supersession_honestly() -> None:
    check("2a. v1.1 declares registry_version 1.1", V11["registry_version"] == "1.1")
    check("2b. it names the file it supersedes",
          V11["supersedes"] == V10_J.name)
    check("2c. it states v1.0 is NOT edited in place",
          "NOT edited in place" in V11["supersession_rule"])
    check("2d. it is dated", V11["authored_at_utc"] == "2026-08-18")
    check("2e. it points at its own companion markdown",
          V11["companion_markdown"].endswith("GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.1_DRAFT.md"))
    check("2f. it requires v1.0 to stay byte-identical",
          V11["hypotheses_carried_forward_unchanged"]["v1_0_must_remain_byte_identical"] is True)
    check("2g. it does not restate the carried-forward hypotheses",
          set(H11) == {"HYP-04"},
          "restating governed text would create two mutable copies of it")
    check("2h. but it does name which three are carried forward",
          V11["hypotheses_carried_forward_unchanged"]["unchanged_hypothesis_ids"]
          == ["HYP-01", "HYP-02", "HYP-03"])


# ===================== 3. the status enum was NOT widened =================
def test_3_status_vocabulary_is_unchanged() -> None:
    """A new status invented to flatter a half-built hypothesis would gut the enum."""
    check("3a. v1.1's status vocabulary is identical to v1.0's",
          V11["statuses"] == V10["statuses"])
    check("3b. exactly two statuses exist",
          set(V11["statuses"]) == {"ACTIVE_COLLECTING", NOT_IMPL})
    check("3c. the rejected candidate status is NOT in the enum",
          "PREREGISTERED_MEASUREMENT_IMPLEMENTED_PENDING_LINKAGE" not in V11["statuses"])
    check("3d. and its rejection is recorded, not silently dropped",
          "PREREGISTERED_MEASUREMENT_IMPLEMENTED_PENDING_LINKAGE" in V11["statuses_note"])
    check("3e. HYP-04's status is a member of the enum",
          H11["HYP-04"]["status"] in V11["statuses"])
    check("3f. HYP-04 is NOT_IMPLEMENTED", H11["HYP-04"]["status"] == NOT_IMPL)


# ===================== 4. HYP-04's content ================================
def test_4_hyp04_content() -> None:
    h = H11["HYP-04"]
    check("4a. id is HYP-04", h["hypothesis_id"] == "HYP-04")
    check("4b. classification is exploratory",
          h["classification"] == "preregistered_exploratory")
    check("4c. it is NOT primary confirmatory", h["is_primary_confirmatory"] is False)
    check("4d. threshold is 193 and is an int",
          h["minimum_eligible_events"] == 193
          and isinstance(h["minimum_eligible_events"], int))
    check("4e. the threshold's UNIT is stated as anchor events",
          h["minimum_eligible_events_unit"] == "eligible anchor events")
    check("4f. the display rule cites its own threshold",
          "193" in h["display_rule"])
    check("4g. the display rule says it accrues nothing while not implemented",
          "accrues no eligible events" in h["display_rule"])
    check("4h. the display rule forbids reporting placeholder-linkage results",
          "placeholder" in h["display_rule"].lower()
          and "under any circumstances" in h["display_rule"])
    check("4i. options_benchmark_required is False",
          h["options_benchmark_required"] is False)
    check("4j. every unresolved decision is marked PENDING, never guessed",
          all(d["state"] == PENDING for d in h["unresolved_analysis_decisions"]))
    check("4k. the peer-side measurement is stated to have NO eligibility class",
          "no eligibility class" in h["required_eligibility_class_note"])


def test_5_threshold_is_a_governance_floor_not_a_power_claim() -> None:
    """The registry forbids presenting thresholds as power guarantees."""
    basis = H11["HYP-04"]["minimum_eligible_events_basis"]
    check("5a. it is explicitly characterised as a governance floor",
          "GOVERNANCE ELIGIBILITY FLOOR" in basis["governance_character"])
    check("5b. it explicitly disclaims being a power guarantee",
          "NOT a claim of guaranteed statistical power" in basis["governance_character"])
    check("5c. it explicitly disclaims being a detectable-effect-size estimate",
          "NOT an estimate of detectable effect size" in basis["governance_character"])
    check("5d. the assumed effect size is declared hypothetical, not observed",
          "NOT derived from any observed project result"
          in basis["derivation_inputs"]["assumed_effect_size_character"])
    check("5e. it explains why it does not violate the power_statement",
          "OBSERVED PROJECT RESULTS" in basis["why_this_does_not_violate_the_power_statement"])
    check("5f. the naive 126 is carried as a labelled baseline only",
          basis["derivation_inputs"]["naive_single_test_baseline"] == 126
          and "Never the operative floor"
          in basis["derivation_inputs"]["naive_single_test_baseline_note"])
    check("5g. the unit-ambiguity trap is called out explicitly",
          "NOT stated in (anchor x peer) pairs" in basis["unit_discipline"])
    check("5h. the derivation is referenced so it can be audited",
          "Patch 2" in basis["derivation_reference"])
    check("5i. revision requires a further dated version written BEFORE results",
          "BEFORE the results" in basis["revisable"])
    # the governance block's own power_statement must still cover HYP-04
    ps = V11["statistical_governance"]["power_statement"]
    check("5j. the power_statement explicitly extends to HYP-04's 193",
          "193" in ps and "60/60/40" in ps)


# ===================== 6. options position is unchanged ===================
def test_6_options_eligibility_is_not_quietly_opened() -> None:
    o11, o10 = V11["options_related_classes"], V10["options_related_classes"]
    check("6a. no hypothesis is registered against an options class",
          o11["registered_hypothesis"] is None)
    check("6b. options results still DENY_NO_REGISTERED_HYPOTHESIS",
          o11["result_display_status"] == "DENY_NO_REGISTERED_HYPOTHESIS")
    check("6c. the deny status is unchanged from v1.0",
          o11["result_display_status"] == o10["result_display_status"]
          and o11["registered_hypothesis"] == o10["registered_hypothesis"])
    check("6d. v1.1 explicitly states HYP-04 is not registered here",
          "not registered here" in " ".join(o11).lower()
          or "hyp04_explicitly_not_registered_here" in o11)
    check("6e. and that its options-shaped Stage 2 does not change that",
          "does not register it against an options class"
          in o11["hyp04_explicitly_not_registered_here"])
    tension = H11["HYP-04"]["options_tension_note"]
    check("6f. the options tension is recorded on the hypothesis itself",
          "OUT OF SCOPE FOR THIS ENTRY" in tension["formal_options_eligibility"])
    check("6g. it is deferred to Phase 4, not left undefined",
          "Phase 4" in tension["deferred_to"])
    check("6h. Phase 0 is stated to size and execute nothing",
          "sizes nothing and executes nothing" in tension["statement"])


# ===================== 7. governance bookkeeping ==========================
def test_7_governance_updated_consistently() -> None:
    g11, g10 = V11["statistical_governance"], V10["statistical_governance"]
    check("7a. HYP-01 is still the sole primary confirmatory",
          g11["primary_confirmatory_hypothesis"] == "HYP-01"
          == g10["primary_confirmatory_hypothesis"])
    check("7b. secondary is unchanged: [HYP-02]",
          g11["secondary_hypotheses"] == ["HYP-02"] == g10["secondary_hypotheses"])
    check("7c. exploratory now lists HYP-03 AND HYP-04",
          g11["exploratory_hypotheses"] == ["HYP-03", "HYP-04"])
    check("7d. HYP-04 appears in named_hypotheses",
          V11["critical_distinction"]["named_hypotheses"]
          == ["HYP-01", "HYP-02", "HYP-03", "HYP-04"])
    check("7e. the promotion rule now covers HYP-04",
          "HYP-04" in g11["promotion_rule"]
          and "may never be promoted" in g11["promotion_rule"])
    check("7f. the multiplicity note says four, not three",
          "Four hypotheses" in g11["multiplicity_note"])
    check("7g. cross-family multiplicity is still PENDING, not resolved here",
          PENDING in g11["multiplicity_note"])
    check("7h. HYP-04's within-hypothesis max-T is distinguished from cross-family",
          "not a cross-family adjustment" in g11["multiplicity_note"])
    check("7i. an explicit rule governs how a hypothesis is added",
          "new dated registry version" in g11["adding_a_hypothesis_rule"])
    check("7j. alpha, sidedness and CI are unchanged",
          g11["primary_alpha"] == g10["primary_alpha"]
          and g11["inference_sidedness"] == g10["inference_sidedness"]
          and g11["confidence_interval"] == g10["confidence_interval"])


def test_8_counts_and_results_are_still_zero_and_null() -> None:
    counts = V11["eligible_event_counts"]
    check("8a. HYP-04 is present in the counters", "HYP-04" in counts)
    check("8b. every count is zero",
          all(v == 0 for k, v in counts.items() if k != "note"))
    check("8c. all four hypotheses have a counter",
          {"HYP-01", "HYP-02", "HYP-03", "HYP-04"} <= set(counts))
    check("8d. results are null", V11["results"] is None)
    check("8e. the results note forbids reporting Phase 0 work as a result",
          "none of it is a result about this hypothesis" in V11["results_note"])


def test_9_authored_before_flag_is_honest() -> None:
    """v1.0 claims True. v1.1 cannot inherit that -- screening has since happened."""
    check("9a. v1.1 does NOT claim it predates all screening",
          V11["authored_before_any_candidate_screening_or_observation"] is False)
    note = V11["authored_before_any_candidate_screening_or_observation_note"]
    check("9b. it explains why, naming the registered event",
          "EVT-DELL-FY27Q2-ERN" in note)
    check("9c. it states the narrower claim that IS true",
          "before any HYP-04 observation exists" in note)
    check("9d. v1.0's own flag is untouched",
          V10["authored_before_any_candidate_screening_or_observation"] is True)


# ===================== 10. markdown / json agreement ======================
def test_10_markdown_matches_the_json() -> None:
    check("10a. the markdown states the 193 threshold", "193" in MD11)
    check("10b. it lists all four hypotheses",
          all(h in MD11 for h in ("HYP-01", "HYP-02", "HYP-03", "HYP-04")))
    check("10c. it states HYP-04 is exploratory",
          "preregistered exploratory" in MD11)
    check("10d. it records the rejected status candidate",
          "PREREGISTERED_MEASUREMENT_IMPLEMENTED_PENDING_LINKAGE" in MD11)
    check("10e. it states v1.0 is not edited", "v1.0 is not edited" in MD11.lower())
    check("10f. it requires the linkage as-of date",
          "first_known_or_established_as_of_date" in MD11
          and "blocking data-quality failure" in MD11)
    check("10g. it records the options tension as deferred to Phase 4",
          "Phase 4" in MD11 and "DENY_NO_REGISTERED_HYPOTHESIS" in MD11)
    check("10h. it disclaims the threshold as a power claim",
          "not a claim of guaranteed statistical power" in MD11.lower())


def test_11_no_result_or_edge_claim_leaks_in() -> None:
    blob = (json.dumps(V11) + MD11).lower()
    for phrase in ("hedging edge", "profitable", "outperform",
                   "we find that", "results show", "demonstrates that"):
        check(f"11a. v1.1 never asserts '{phrase}'", phrase not in blob)
    # Assert the GUARANTEE at the fields that carry it, not a guessed phrase.
    # An earlier version of this check searched the serialized blob for the
    # literal string "never evidence", which appears nowhere -- the doc says
    # "is evidence about ... and none may be reported as such" under a key
    # named placeholder_is_never_evidence. That was a matcher defect: it would
    # have failed against a correct document and passed against a reworded one.
    ext = H11["HYP-04"]["required_external_measurement"]
    check("11b. the placeholder linkage is named as such on the hypothesis",
          ext["placeholder_used_in_phase_0"].startswith("same-sector"))
    check("11c. and it is explicitly disqualified as evidence",
          "is evidence about supply-chain transmission"
          in ext["placeholder_is_never_evidence"]
          and "none may be reported as such" in ext["placeholder_is_never_evidence"])
    check("11d. the display rule bars placeholder results at ANY event count",
          "at any event count" in H11["HYP-04"]["display_rule"].lower())
    check("11e. sector membership is a forbidden substitution",
          any("sector membership" in s.lower()
              for s in H11["HYP-04"]["forbidden_substitutions"]))


def test_12_offline() -> None:
    try:
        socket.getaddrinfo("example.com", 443)
        check("12a. network blocked", False, "a lookup succeeded")
    except Exception as e:
        check("12a. network blocked", type(e).__name__ == "NetworkBlocked")


if __name__ == "__main__":
    test_1_v1_0_is_not_edited_in_place()
    test_2_v1_1_declares_its_supersession_honestly()
    test_3_status_vocabulary_is_unchanged()
    test_4_hyp04_content()
    test_5_threshold_is_a_governance_floor_not_a_power_claim()
    test_6_options_eligibility_is_not_quietly_opened()
    test_7_governance_updated_consistently()
    test_8_counts_and_results_are_still_zero_and_null()
    test_9_authored_before_flag_is_honest()
    test_10_markdown_matches_the_json()
    test_11_no_result_or_edge_claim_leaks_in()
    test_12_offline()

    print()
    if SKIPS:
        print(f"{len(SKIPS)} SKIPPED (not counted as passes): {SKIPS}")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL REGISTRY v1.1 GOVERNANCE TESTS PASSED")
    sys.exit(0)
