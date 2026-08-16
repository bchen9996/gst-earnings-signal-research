#!/usr/bin/env python3
"""Deterministic tests for the dated HYP-01 statistical-method amendment.

These EXECUTE the effective-lock resolver rather than reading declarations, and
they include MUTATION tests: each critical decision is independently corrupted in
a temporary copy of the repository state and the resolver must refuse.

Offline. Sockets blocked. No research artifact, network, or package install.

Run directly: python test_market_response_hyp01_dated_amendment.py
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline amendment test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

ROOT = Path(__file__).resolve().parent
LS = ROOT / "Live Signal Engine"
AMEND = LS / "GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.json"
AMEND_MD = LS / "GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-08-16.md"
AUTH_MD = LS / "GST_HYP01_METHOD_AUTHORIZATION_2026-08-16.md"
REPORT = LS / "GST_HYP01_EFFECTIVE_LOCK_REPORT_v1.0.json"
RESOLVER = ROOT / "tools" / "hyp01_effective_lock" / "resolve_effective_lock.py"
BASE_LOCK = LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json"
PROPOSED = LS / "GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json"
SIGNOFF = LS / "GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md"
MATRIX = LS / "GST_HYP01_AUTHORIZER_DECISION_MATRIX_v1.0_DRAFT.md"
REGISTRY = LS / "Market_Response_Event_Registry" / "registry.jsonl"
COHORT = LS / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json"
F5AUDIT = LS / "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json"
RLOCK = ROOT / "tools" / "hyp01_r_reference" / "r-packages.lock.json"

AUTH_STATEMENT = (
    "I authorize the recommended D1–D16 methodological package as specified "
    "on August 16, 2026."
)

PROTECTED = {
    "GST_HYP01_ANALYSIS_LOCK_v1.0.json": "85264e9786e42180547a22f320da7384b4a54d1e45c777e40b2f596a982b3805",
    "GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json": "132a632b0d45d450d0f320c82fbb4af4affd59a98786ca8c603051931b92195e",
    "GST_HYP01_STATISTICAL_METHOD_SIGNOFF_v1.0_TEMPLATE.md": "7eef69e81e4764ed19534762d0f3031d3ac2a50c30adc363447d99e38fe69320",
    "Market_Response_Event_Registry/registry.jsonl": "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974",
    "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json": "2ebb1639d5bb964e6d784cb988eb0a80cf9618ef42eb261e33cca2a7d97cc020",
    "GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json": "03aa177242169cbca20e22a52fe1d70a7f295040e82e9fb3c71c97641d2dfad3",
}

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


AM = json.loads(AMEND.read_text(encoding="utf-8"))
D = AM["decisions"]
RPT = json.loads(REPORT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 1. D1-D16 exact
def test_1_exact_d1_to_d16() -> None:
    want = {
        "D1": "CR2_BIAS_REDUCED_LINEARIZATION",
        "D2": "BRL_ADJUSTMENT_BUILT_INTO_CLUBSANDWICH_CR2",
        "D3": "COEFFICIENT_SPECIFIC_SATTERTHWAITE",
        "D4": "NOT_USED_IN_HYP01",
        "D5": "NOT_APPLICABLE", "D6": "NOT_APPLICABLE", "D7": "NOT_APPLICABLE",
        "D8": "RETAIN_SINGLETON_TICKER_CLUSTERS",
        "D9": "REFUSE_AND_ABORT",
        "D10": "REPORT_WITHOUT_THRESHOLD",
        "D11": "R_4.6.1_CLUBSANDWICH_OFFICIAL_PYTHON_CROSS_CHECK",
        "D12": "TREATMENT_REFERENCE_CODING",
        "D13": "POOL_BELOW_THRESHOLD_INTO_OTHER",
        "D14": "NO_CAP",
        "D15": "NO_ADJUSTMENT_FOR_THE_SINGLE_LOCKED_PRIMARY_TEST",
        "D16": "NO_PROJECT_DERIVED_POWER_CLAIM",
    }
    for k, v in want.items():
        check(f"1a. {k} = {v}", D[k]["selected"] == v, D[k].get("selected"))
    check("1b. the effective-lock report agrees with the amendment",
          RPT["effective_decisions"] == {k: D[k]["selected"] for k in want})
    check("1c. exactly sixteen decisions are encoded",
          len([k for k in D if k.startswith("D") and k[1:].isdigit()]) == 16)


# ---------------------------------------------------------------- 2-4. authorization
def test_2_authorization_statement_verbatim() -> None:
    a = AM["authorization"]
    check("2a. statement preserved verbatim", a["statement_verbatim"] == AUTH_STATEMENT)
    check("2b. statement appears verbatim in the authorization record",
          AUTH_STATEMENT in AUTH_MD.read_text(encoding="utf-8"))
    check("2c. the effective-lock report carries it verbatim",
          RPT["authorization"]["statement_verbatim"] == AUTH_STATEMENT)


def test_3_date_basis_explicit() -> None:
    a = AM["authorization"]
    check("3a. declared date recorded", a["authorization_declared_date"] == "2026-08-16")
    check("3b. date basis is explicit",
          a["authorization_date_basis"] == "user-declared UTC calendar date")
    check("3c. recording timestamp is kept distinct from the declared date",
          a["recorded_at_utc"].endswith("Z")
          and a["recording_timestamp_is_distinct_from_declared_date"] is True
          and a["recorded_at_utc"][:10] != a["authorization_declared_date"] or
          a["recorded_at_utc"] != a["authorization_declared_date"])
    check("3d. no local-timezone claim is made",
          "America/Chicago" in a["declared_date_is_not_a_local_civil_date"]
          and "does not assert" in a["declared_date_is_not_a_local_civil_date"])
    blob = AUTH_MD.read_text(encoding="utf-8")
    check("3e. the record does not claim an America/Chicago authorization date",
          not re.search(r"august 16[^.]{0,60}(america/chicago|central)", blob, re.I))


def test_4_no_false_reviewer_claimed() -> None:
    a = AM["authorization"]
    check("4a. authorizer role is the project authorizer / repository owner",
          a["authorizer_role"] == "Project authorizer / repository owner")
    for flag in ("authorizer_is_independent_statistician", "authorizer_is_methodologist",
                 "external_peer_review_performed", "external_methodological_review_performed",
                 "institutional_approval_obtained", "handwritten_signature_captured"):
        check(f"4b. {flag} is False", a[flag] is False)
    check("4c. no reviewer identity is recorded", a["reviewer_identity_recorded"] is None)
    # No document may assert an external review happened.
    for label, path in (("amendment md", AMEND_MD), ("authorization md", AUTH_MD)):
        low = path.read_text(encoding="utf-8").lower()
        for tok in ("peer-reviewed", "peer reviewed", "independent statistician",
                    "institutional approval", "irb approval"):
            idx, bad = 0, False
            while True:
                i = low.find(tok, idx)
                if i < 0:
                    break
                w = low[max(0, i - 90):i]
                if not any(x in w for x in ("no ", "not ", "never", "without", "has not")):
                    bad = True
                    break
                idx = i + len(tok)
            check(f"4d. {label} does not assert {tok!r}", not bad)
    check("4e. external preregistration is explicitly not claimed",
          AM["epistemic_status"]["external_preregistration_performed"] is False)


# ---------------------------------------------------------------- 5. provenance
def test_5_split_tolerance_provenance_preserved() -> None:
    sp = AM["epistemic_status"]["split_tolerance_provenance"]
    check("5a. covariance/SE/t/p attributed to PR #17 tolerances",
          "PR #17" in sp["covariance_se_t_p"])
    check("5b. continuous df attributed to the PR #18 tolerance",
          "PR #18" in sp["continuous_satterthwaite_df"]
          and "NOT preregistered in PR #17" in sp["continuous_satterthwaite_df"])
    check("5c. continuous df flagged as not preregistered in PR #17",
          sp["continuous_df_preregistered_in_pr17"] is False)
    check("5d. D3 carries the provenance qualification inline",
          "PR #18" in D["D3"]["provenance_qualification"]
          and "NOT preregistered in PR #17" in D["D3"]["provenance_qualification"])
    check("5e. implementation validation is stated not to be scientific proof",
          "not evidence" in AM["epistemic_status"]["implementation_validation_is_not_scientific_proof"])


# ---------------------------------------------------------------- 6-7. roles and bars
def test_6_official_r_and_python_cross_check() -> None:
    o = D["D11"]["official_confirmatory_calculation"]
    check("6a. official calculation is R 4.6.1", o["language"] == "R" and o["language_version"] == "4.6.1")
    check("6b. official package is clubSandwich 0.7.0",
          o["package"] == "clubSandwich" and o["package_version"] == "0.7.0")
    check("6c. Python is the cross-check, not authoritative",
          D["D11"]["python_role"] == "INDEPENDENT_IMPLEMENTATION_CROSS_CHECK"
          and D["D1"]["python_role"] == "VALIDATED_CROSS_CHECK_NOT_AUTHORITATIVE")
    check("6d. roles may not be reversed", D["D11"]["roles_may_not_be_reversed"] is True)
    disc = D["D11"]["discrepancy_rule"]
    check("6e. a discrepancy stops release",
          disc["on_mismatch"] == "STOP_RELEASE_AND_PRODUCE_DISCREPANCY_REPORT")
    check("6f. averaging / manual reconciliation / preferred-output selection all barred",
          not disc["averaging_permitted"] and not disc["manual_reconciliation_permitted"]
          and not disc["selecting_preferred_output_permitted"])
    rlock = json.loads(RLOCK.read_text(encoding="utf-8"))
    check("6g. locked packages match the committed R lockfile",
          o["locked_packages"] == {p["package"]: p["version"] for p in rlock["packages"]})
    check("6h. eight items are frozen at event 60", len(D["D11"]["freeze_at_event_60"]) == 8)


def test_7_cr3_and_bootstrap_barred() -> None:
    check("7a. bootstrap is not used in HYP-01", D["D4"]["selected"] == "NOT_USED_IN_HYP01")
    check("7b. bootstrap is neither primary nor sensitivity",
          D["D4"]["is_primary"] is False and D["D4"]["is_sensitivity"] is False)
    check("7c. bootstrap may not overturn the primary", D["D4"]["may_overturn_primary"] is False)
    for k in ("D5", "D6", "D7"):
        check(f"7d. {k} retains no activatable placeholder",
              D[k]["selected"] == "NOT_APPLICABLE" and D[k]["placeholder_retained"] is False)
    check("7e. reactivating the bootstrap requires a new dated amendment",
          "NEW dated amendment" in D["bootstrap_reactivation_rule"])
    check("7f. CR3 is not selected anywhere in the decisions",
          "CR3" not in json.dumps({k: D[k] for k in D if k.startswith("D")}))


# ---------------------------------------------------------------- 8-9. D8/D9/D10
def test_8_singleton_and_refusal_behaviour() -> None:
    check("8a. singletons retained", D["D8"]["selected"] == "RETAIN_SINGLETON_TICKER_CLUSTERS")
    check("8b. singleton presence is not an exclusion rule",
          D["D8"]["singleton_presence_is_an_exclusion_rule"] is False)
    check("8c. four singleton reporting requirements", len(D["D8"]["always_report"]) == 4)
    check("8d. singleton identities only where the blinded protocol permits",
          any("blinded" in r for r in D["D8"]["always_report"]))
    check("8e. D9 refuses and aborts without a confirmatory p-value",
          D["D9"]["selected"] == "REFUSE_AND_ABORT"
          and D["D9"]["abort_without_confirmatory_p_value"] is True)
    check("8f. nine trigger conditions recorded", len(D["D9"]["trigger_conditions"]) == 9)
    check("8g. a refusal is not a null result", D["D9"]["refusal_is_not_a_null_result"] is True)
    check("8h. four distinct outcomes are distinguished",
          set(D["D9"]["outcome_taxonomy"]) ==
          {"ANALYSIS_REFUSAL", "NULL_RESULT", "SOFTWARE_FAILURE", "DATA_QUALITY_FAILURE"})
    # thresholds must equal the committed runner's REFUSAL block, not new numbers
    check("8i. no new threshold invented", D["D9"]["thresholds_are_newly_invented"] is False)
    src = D["D9"]["thresholds_source"]
    runner = ROOT / src["path"]
    check("8j. threshold source hash matches the committed runner",
          runner.is_file() and sha_lf(runner) == src["sha256_lf"])
    block = re.search(r"REFUSAL = \{(.*?)\n\}", runner.read_text(encoding="utf-8"), re.S).group(1)
    live = {n_: float(v) for n_, v in re.findall(r'"([a-z_]+)":\s*([0-9.e+-]+)', block)}
    tv = D["D9"]["thresholds_verbatim"]
    for k, v in live.items():
        check(f"8k. {k} adopted verbatim ({v:g})", float(tv[k]) == v)


def test_9_no_minimum_cluster_threshold() -> None:
    check("9a. no minimum cluster cutoff", D["D10"]["minimum_cluster_cutoff"] is None)
    check("9b. no minimum effective-df cutoff", D["D10"]["minimum_effective_df_cutoff"] is None)
    check("9c. no invented cutoff imposed", D["D10"]["invented_cutoff_imposed"] is False)
    check("9d. the primary result is not suppressed on a post hoc threshold",
          D["D10"]["suppress_primary_on_post_hoc_threshold"] is False)
    check("9e. five quantities always reported", len(D["D10"]["always_report"]) == 5)
    note = D["D9"]["min_clusters_note"]
    check("9f. min_clusters_for_any_output is labelled arithmetic, not a policy",
          "not an eligibility rule" in note and "ARITHMETIC" in note.upper())
    check("9g. a future threshold requires a new dated amendment",
          "NEW dated amendment" in D["D10"]["future_threshold_rule"])


# ---------------------------------------------------------------- 10-14. remaining
def test_10_treatment_coding_deterministic() -> None:
    d12 = D["D12"]
    check("10a. treatment/reference coding", d12["selected"] == "TREATMENT_REFERENCE_CODING")
    check("10b. reference selection is deterministic", d12["reference_selection_is_deterministic"] is True)
    check("10c. reference recorded before fitting", d12["reference_recorded_before_fitting"] is True)
    check("10d. reference selection may not use outcomes",
          d12["reference_selection_may_use_outcomes"] is False
          and d12["reference_selection_after_examining_coefficients_prohibited"] is True)
    check("10e. applies to the secondary model only", d12["applies_to_primary_model"] is False)
    check("10f. an existing lock rule would govern instead", "existing lock" in d12["existing_lock_override"])


def test_11_sector_pooling() -> None:
    d13 = D["D13"]
    check("11a. pooling threshold is 3 eligible events", d13["pooling_threshold_eligible_events"] == 3)
    check("11b. pooling never reads outcomes",
          d13["pooling_may_read_outcomes"] is False
          and d13["pooling_determined_from"] == "eligible-event counts only")
    check("11c. threshold is an authorizer governance rule, not a PR #18 result",
          d13["threshold_is_authorizer_selected_governance_rule"] is True
          and d13["threshold_established_by_pr18"] is False)
    check("11d. map computed once from the frozen 60-event cohort and persisted",
          d13["pooling_map_computed_once_from_frozen_60_event_cohort"] is True
          and d13["pooling_map_persisted"] is True)
    check("11e. ticker clusters never pooled, removed or altered",
          d13["ticker_clusters_pooled_or_removed_or_altered"] is False)
    check("11f. the primary unadjusted model is never altered",
          d13["primary_unadjusted_model_altered"] is False)
    check("11g. rank deficiency refuses the secondary model instead of moving the threshold",
          "REFUSE" in d13["rank_deficient_fallback"].upper()
          and "do not alter the pooling threshold" in d13["rank_deficient_fallback"].lower())


def test_12_no_ticker_cap() -> None:
    d14 = D["D14"]
    check("12a. no per-ticker cap", d14["selected"] == "NO_CAP" and d14["cap_value"] is None)
    check("12b. every eligible event among the first 60 is retained",
          d14["all_eligible_events_among_first_60_retained"] is True)
    check("12c. selective deletion is not permitted", d14["selective_deletion_permitted"] is False)
    check("12d. repeats handled by clustered inference",
          "clustered inference" in d14["repeated_ticker_handling"])


def test_13_one_primary_test_no_multiplicity() -> None:
    fam = D["D15"]["protected_family"]
    check("13a. exactly one primary predictor / outcome / test",
          fam["primary_predictors"] == 1 and fam["primary_outcomes"] == 1
          and fam["primary_coefficient_tests"] == 1)
    check("13b. alpha 0.05 two-sided", fam["alpha"] == 0.05 and fam["sidedness"] == "two_sided")
    check("13c. no multiplicity adjustment for the single locked primary test",
          D["D15"]["selected"] == "NO_ADJUSTMENT_FOR_THE_SINGLE_LOCKED_PRIMARY_TEST")
    check("13d. secondary analyses may not reinterpret or replace the primary",
          D["D15"]["secondary_may_reinterpret_or_replace_primary"] is False)
    check("13e. confirmatory secondaries need their own preregistration",
          D["D15"]["confirmatory_secondary_requires_own_preregistration"] is True)


def test_14_n60_is_a_governance_floor() -> None:
    d16 = D["D16"]
    check("14a. n = 60", d16["n_events"] == 60)
    check("14b. characterized as a governance floor, not a power target",
          d16["n_events_characterization"] == "GOVERNANCE_FLOOR_NOT_A_DEMONSTRATED_POWER_TARGET")
    check("14c. no adequately-powered claim", d16["study_is_adequately_powered_claim"] is False)
    check("14d. no retrospective or prospective effect used",
          d16["retrospective_reconstruction_effects_used"] is False
          and d16["prospective_outcomes_used"] is False)
    check("14e. target not revised after examining results",
          d16["sample_target_revised_after_examining_results"] is False)
    check("14f. future power analysis needs external effect sizes and a new amendment",
          "EXTERNAL" in d16["future_power_analysis_rule"]
          and "NEW dated amendment" in d16["future_power_analysis_rule"])
    # no document may describe n=60 as empirically powered
    # Negation is judged per LINE, not per character window: the phrase appears
    # legitimately inside a prohibition list ("Prohibited: ... claiming the study
    # is adequately powered"), and a fixed-width lookbehind clipped the marker.
    NEG = ("not ", "no ", "never", "prohibited", "without", "may not", "cannot",
           "floor", "does not", "is not")
    for label, path in (("amendment md", AMEND_MD), ("authorization md", AUTH_MD)):
        asserted = [ln.strip()[:70] for ln in path.read_text(encoding="utf-8").lower().splitlines()
                    if "adequately powered" in ln and not any(t in ln for t in NEG)]
        check(f"14g. {label} never asserts the study is adequately powered",
              not asserted, str(asserted[:1]))


# ---------------------------------------------------------------- 15-16. gates
def test_15_f5_open_and_16_collection_blocked() -> None:
    g = AM["gates"]
    check("15a. F5 OPEN in the amendment", g["f5_construct_validity"] == "OPEN")
    check("15b. the amendment does not close F5", g["f5_closed_by_this_amendment"] is False)
    f5 = json.loads(F5AUDIT.read_text(encoding="utf-8"))
    check("15c. the construct-validity audit still says STILL_OPEN",
          f5["gap_audit_status_after_this_work"] == "STILL_OPEN")
    check("15d. the effective-lock report shows F5 OPEN",
          RPT["effective_state"]["f5_construct_validity"] == "OPEN")
    check("16a. prospective collection BLOCKED", g["prospective_collection"] == "BLOCKED")
    check("16b. three unblock conditions recorded", len(g["collection_unblock_conditions"]) == 3)
    check("16c. F5 named as an unblock condition",
          any("F5" in c for c in g["collection_unblock_conditions"]))
    check("16d. no analysis run and no scientific result",
          g["analysis_run"] is False and g["scientific_result"] is None
          and AM["analysis_executed_by_this_amendment"] is False
          and AM["analysis_runner_created_by_this_amendment"] is False)
    check("16e. no outcome existed or was inspected",
          AM["epistemic_status"]["no_prospective_outcome_existed_or_was_inspected"] is True)
    check("16f. the effective-lock report shows collection BLOCKED",
          RPT["effective_state"]["prospective_collection"] == "BLOCKED"
          and RPT["effective_state"]["scientific_result"] is None)


# ---------------------------------------------------------------- 17-18. protected state
def test_17_protected_hashes_unchanged() -> None:
    for rel, want in PROTECTED.items():
        p = LS / rel
        check(f"17a. {rel} unchanged", p.is_file() and sha_lf(p) == want)
    # the amendment must record those same hashes
    ev = AM["evidence_referenced"]
    check("17b. amendment records the base-lock hash",
          ev["base_lock_v1_0"]["sha256_lf"] == PROTECTED["GST_HYP01_ANALYSIS_LOCK_v1.0.json"])
    check("17c. amendment records the proposed v1.1 hash",
          ev["proposed_v1_1"]["sha256_lf"] == PROTECTED["GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json"])
    for key in ("pr17_feasibility_inventory", "pr18_r_reference_validation"):
        p = ROOT / ev[key]["path"]
        check(f"17d. {key} hash matches on disk", p.is_file() and sha_lf(p) == ev[key]["sha256_lf"])
    check("17e. proposed v1.1 is not authoritative",
          AM["proposed_v1_1_is_authoritative"] is False
          and AM["effective_lock_resolution"]["proposed_v1_1_participates_in_resolution"] is False)
    check("17f. signoff template still has no ticked box",
          not re.search(r"- \[[xX]\]", SIGNOFF.read_text(encoding="utf-8")))
    check("17g. the decision matrix has no ticked box either",
          not re.search(r"- \[[xX]\]", MATRIX.read_text(encoding="utf-8")))
    check("17h. the matrix is marked as no longer the decision status of record",
          "no longer the decision status of record" in MATRIX.read_text(encoding="utf-8"))


def test_18_research_state_unchanged() -> None:
    lock = json.loads(BASE_LOCK.read_text(encoding="utf-8-sig"))
    check("18a. results still null", lock["results"] is None)
    check("18b. frozen_event_ids still empty", lock["frozen_event_ids"] == [])
    check("18c. eligible_events_now still zero", lock["eligible_events_now"] == 0)
    cp = json.loads(COHORT.read_text(encoding="utf-8-sig"))
    check("18d. screening rows still empty", cp["screening_rows"] == [])
    rows = [json.loads(l) for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("18e. registry holds exactly the one DELL registration row",
          len(rows) == 1 and rows[0]["ticker"] == "DELL"
          and rows[0]["event_id"] == "EVT-DELL-FY27Q2-ERN"
          and rows[0]["row_type"] == "REGISTRATION")


# ---------------------------------------------------------------- 19. mutation tests
MUTATIONS = {
    "CR1 becomes primary":            ("decisions.D1.selected", "CR1_CONVENTIONAL"),
    "CR3 becomes selected":           ("decisions.D1.selected", "CR3_JACKKNIFE"),
    "bootstrap becomes primary":      ("decisions.D4.is_primary", True),
    "bootstrap placeholder retained": ("decisions.D5.placeholder_retained", True),
    "R/Python roles reversed":        ("decisions.D11.python_role", "OFFICIAL_CONFIRMATORY"),
    "second correction applied":      ("decisions.D2.second_correction_applied", True),
    "minimum cluster cutoff added":   ("decisions.D10.minimum_cluster_cutoff", 12),
    "ticker cap appears":             ("decisions.D14.cap_value", 3),
    "alpha changed":                  ("decisions.D15.protected_family.alpha", 0.10),
    "sidedness changed":              ("decisions.D15.protected_family.sidedness", "one_sided"),
    "sector pooling reads outcomes":  ("decisions.D13.pooling_may_read_outcomes", True),
    "n=60 called powered":            ("decisions.D16.study_is_adequately_powered_claim", True),
    "n=60 recharacterized":           ("decisions.D16.n_events_characterization", "DEMONSTRATED_POWER_TARGET"),
    "F5 marked closed":               ("gates.f5_construct_validity", "CLOSED"),
    "collection unblocked":           ("gates.prospective_collection", "PERMITTED"),
    "authorization statement altered": ("authorization.statement_verbatim", "I approve everything."),
    "declared date removed":          ("authorization.authorization_declared_date", ""),
    "authorizer role misrepresented": ("authorization.authorizer_role", "Independent statistician"),
    "methodologist claimed":          ("authorization.authorizer_is_methodologist", True),
    "peer review claimed":            ("authorization.external_peer_review_performed", True),
    "df provenance falsified":        ("epistemic_status.split_tolerance_provenance.continuous_df_preregistered_in_pr17", True),
    "package version drift":          ("decisions.D11.official_confirmatory_calculation.package_version", "0.6.0"),
    "proposed v1.1 made authoritative": ("proposed_v1_1_is_authoritative", True),
    "D9 thresholds invented":         ("decisions.D9.thresholds_are_newly_invented", True),
    "outcome inspection admitted":    ("epistemic_status.no_prospective_outcome_existed_or_was_inspected", False),
}


def _set(doc, dotted, value):
    parts = dotted.split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur[p]
    cur[parts[-1]] = value


def test_19_mutation_tests() -> None:
    """Each corruption must make the resolver refuse. A resolver that passes
    everything proves nothing, so this is the load-bearing test."""
    with tempfile.TemporaryDirectory() as td:
        sandbox = Path(td) / "repo"
        (sandbox / "Live Signal Engine").mkdir(parents=True)
        (sandbox / "tools" / "hyp01_effective_lock").mkdir(parents=True)
        (sandbox / "tools" / "hyp01_r_reference").mkdir(parents=True)
        shutil.copy2(RESOLVER, sandbox / "tools" / "hyp01_effective_lock" / RESOLVER.name)
        shutil.copy2(ROOT / "tools" / "hyp01_inference_feasibility.py", sandbox / "tools")
        shutil.copy2(RLOCK, sandbox / "tools" / "hyp01_r_reference" / RLOCK.name)
        for p in (BASE_LOCK, PROPOSED):
            shutil.copy2(p, sandbox / "Live Signal Engine" / p.name)
        for key in ("base_lock_v1_0_companion", "proposed_v1_1_companion",
                    "pr17_feasibility_inventory", "pr17_feasibility_report",
                    "pr18_r_reference_validation", "pr18_r_reference_report",
                    "signoff_template_unmodified"):
            src = ROOT / AM["evidence_referenced"][key]["path"]
            shutil.copy2(src, sandbox / "Live Signal Engine" / src.name)

        def run(doc) -> int:
            (sandbox / "Live Signal Engine" / AMEND.name).write_text(
                json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable,
                                str(sandbox / "tools" / "hyp01_effective_lock" / RESOLVER.name),
                                "--check"], capture_output=True, text=True, timeout=600)
            return r.returncode

        check("19a. the genuine amendment resolves in the sandbox", run(AM) == 0)

        for label, (dotted, value) in MUTATIONS.items():
            bad = copy.deepcopy(AM)
            try:
                _set(bad, dotted, value)
            except (KeyError, TypeError) as e:
                check(f"19b. mutation path exists: {label}", False, str(e))
                continue
            check(f"19b. resolver refuses: {label}", run(bad) != 0)

        # structural mutations
        missing = copy.deepcopy(AM)
        del missing["decisions"]["D13"]
        check("19c. resolver refuses a missing amended decision", run(missing) != 0)

        drift = copy.deepcopy(AM)
        drift["evidence_referenced"]["base_lock_v1_0"]["sha256_lf"] = "0" * 64
        check("19d. resolver refuses a protected-hash drift", run(drift) != 0)

        # a competing second amendment claiming the same field
        second = copy.deepcopy(AM)
        second["amendment_id"] = "GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-09-01"
        (sandbox / "Live Signal Engine" /
         "GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-09-01.json").write_text(
            json.dumps(second, indent=1, ensure_ascii=False), encoding="utf-8")
        check("19e. resolver refuses two amendments claiming the same field", run(AM) != 0)
        (sandbox / "Live Signal Engine" /
         "GST_HYP01_ANALYSIS_LOCK_AMENDMENT_2026-09-01.json").unlink()

        # unamended base-lock drift
        base = json.loads((sandbox / "Live Signal Engine" / BASE_LOCK.name)
                          .read_text(encoding="utf-8-sig"))
        base["primary_model"]["alpha"] = 0.10
        (sandbox / "Live Signal Engine" / BASE_LOCK.name).write_text(
            json.dumps(base, indent=1), encoding="utf-8")
        check("19f. resolver refuses drift in an unamended base-lock field", run(AM) != 0)


# ---------------------------------------------------------------- 20. isolation
def test_20_offline_and_no_research_artifact() -> None:
    src = RESOLVER.read_text(encoding="utf-8")
    flat = " ".join(src.split())          # the marker sentence wraps across lines
    # Scan the CODE, not the module docstring: the docstring legitimately says
    # "reads no observation", and flagging that would be a matcher defect.
    body = src.split('"""', 2)[-1]
    check("20a. the resolver blocks sockets", "socket.getaddrinfo = _deny" in src)
    check("20b. the resolver is not an analysis runner",
          "NOT AN ANALYSIS RUNNER" in flat and "computes no statistic" in flat)
    for tok in ("registry.jsonl", "GST_Phase2_DailyPanel", "Cohort_Screening",
                "observation", "screening", "DailyPanel"):
        check(f"20c. the resolver code never references {tok}", tok not in body)
    check("20d. no analysis runner was created by this amendment",
          AM["analysis_runner_created_by_this_amendment"] is False)
    try:
        socket.getaddrinfo("example.com", 443)
        check("20e. network blocked", False)
    except Exception as e:
        check("20e. network blocked", type(e).__name__ == "NetworkBlocked")
    check("20f. the effective-lock report was generated only from base lock + amendment",
          RPT["generated_from"]["proposed_v1_1_excluded"] is True)


if __name__ == "__main__":
    test_1_exact_d1_to_d16()
    test_2_authorization_statement_verbatim()
    test_3_date_basis_explicit()
    test_4_no_false_reviewer_claimed()
    test_5_split_tolerance_provenance_preserved()
    test_6_official_r_and_python_cross_check()
    test_7_cr3_and_bootstrap_barred()
    test_8_singleton_and_refusal_behaviour()
    test_9_no_minimum_cluster_threshold()
    test_10_treatment_coding_deterministic()
    test_11_sector_pooling()
    test_12_no_ticker_cap()
    test_13_one_primary_test_no_multiplicity()
    test_14_n60_is_a_governance_floor()
    test_15_f5_open_and_16_collection_blocked()
    test_17_protected_hashes_unchanged()
    test_18_research_state_unchanged()
    test_19_mutation_tests()
    test_20_offline_and_no_research_artifact()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-01 DATED AMENDMENT TESTS PASSED")
    sys.exit(0)
