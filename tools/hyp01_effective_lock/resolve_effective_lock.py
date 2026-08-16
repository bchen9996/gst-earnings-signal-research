#!/usr/bin/env python3
"""Resolve the EFFECTIVE HYP-01 statistical lock, and fail closed if anything is wrong.

NOT AN ANALYSIS RUNNER. This module freezes and reports methodology. It computes
no statistic, reads no observation, and cannot produce a scientific result.

The effective lock is resolved from exactly three inputs:

    1. the v1.0 base lock
    2. the dated authorizer amendment
    3. the protected artifact hashes recorded inside that amendment

Nothing else participates. In particular `GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json`
is a PROPOSAL and is deliberately excluded from resolution.

Every check below fails CLOSED: on any violation the resolver refuses to emit an
effective-lock report at all, rather than emitting a degraded one.

    python tools/hyp01_effective_lock/resolve_effective_lock.py --check
    python tools/hyp01_effective_lock/resolve_effective_lock.py --emit <out.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _deny(*_a, **_k):
    raise NetworkBlocked("network access attempted in the offline lock resolver")


socket.socket.connect = _deny
socket.socket.connect_ex = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny

ROOT = Path(__file__).resolve().parents[2]
LS = ROOT / "Live Signal Engine"
BASE_LOCK = LS / "GST_HYP01_ANALYSIS_LOCK_v1.0.json"
AMENDMENT_GLOB = "GST_HYP01_ANALYSIS_LOCK_AMENDMENT_*.json"
PROPOSED_V11 = LS / "GST_HYP01_ANALYSIS_LOCK_v1.1_PROPOSED.json"

AUTH_STATEMENT = (
    "I authorize the recommended D1–D16 methodological package as specified "
    "on August 16, 2026."
)
DECLARED_DATE = "2026-08-16"
AUTHORIZER_ROLE = "Project authorizer / repository owner"

# Roles that must NEVER be claimed for the authorizer.
FORBIDDEN_ROLE_TOKENS = (
    "independent statistician", "methodologist", "peer review", "peer-reviewed",
    "institutional review", "irb", "external review board", "biostatistician",
)

# Base-lock fields that must NOT drift while unamended.
UNAMENDED_INVARIANTS = {
    "primary_model.formula": "abs_overnight_gap ~ gst_zscore",
    "primary_model.estimator": "ordinary_least_squares",
    "primary_model.coefficient_of_interest": "gst_zscore",
    "primary_model.null_hypothesis": "beta_gst = 0",
    "primary_model.sidedness": "two_sided",
    "primary_model.alpha": 0.05,
    "primary_model.covariance.cluster_variable": "ticker",
    "freeze_and_display.threshold": 60,
    "freeze_and_display.run_count": 1,
    "missingness_and_exclusions.imputation": "prohibited",
    "missingness_and_exclusions.zero_fill": "prohibited",
}


def sha_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dig(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return KeyError
        cur = cur[part]
    return cur


class Resolver:
    def __init__(self) -> None:
        self.violations: list[str] = []
        self.base = None
        self.amendment = None
        self.amendment_path = None

    def fail(self, msg: str) -> None:
        self.violations.append(msg)

    # ---------------------------------------------------------------- inputs
    def load(self) -> None:
        if not BASE_LOCK.is_file():
            self.fail(f"base lock missing: {BASE_LOCK.name}")
            return
        self.base = json.loads(BASE_LOCK.read_text(encoding="utf-8-sig"))

        found = sorted(LS.glob(AMENDMENT_GLOB))
        if not found:
            self.fail("no dated amendment found")
            return
        # More than one amendment may exist over time, but only one may claim
        # authority over the same field. Two amendments touching the same field
        # is an unresolved governance conflict, not something to merge silently.
        claims: dict[str, list[str]] = {}
        for p in found:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                self.fail(f"amendment {p.name} is not valid JSON: {e}")
                return
            for f in d.get("amends", {}).get("fields_amended", []):
                claims.setdefault(f, []).append(p.name)
        conflicts = {f: n for f, n in claims.items() if len(n) > 1}
        if conflicts:
            self.fail(f"more than one amendment claims authority over: {sorted(conflicts)}")
            return
        # The operative amendment is the newest by id; with one present it is that one.
        self.amendment_path = found[-1]
        self.amendment = json.loads(self.amendment_path.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- checks
    def check_hashes(self) -> None:
        for key, rec in (self.amendment.get("evidence_referenced") or {}).items():
            p = ROOT / rec["path"]
            if not p.is_file():
                self.fail(f"referenced artifact missing: {rec['path']}")
                continue
            got = sha_lf(p)
            if got != rec["sha256_lf"]:
                self.fail(f"hash drift on {rec['path']}: expected {rec['sha256_lf'][:12]}…, got {got[:12]}…")

    def check_authorization(self) -> None:
        a = self.amendment.get("authorization") or {}
        if a.get("statement_verbatim") != AUTH_STATEMENT:
            self.fail("authorization statement missing or altered")
        if a.get("authorization_declared_date") != DECLARED_DATE:
            self.fail("authorization declared date missing or altered")
        if not a.get("authorization_date_basis"):
            self.fail("authorization date basis missing")
        if a.get("authorizer_role") != AUTHORIZER_ROLE:
            self.fail(f"authorizer role misrepresented: {a.get('authorizer_role')!r}")
        for flag in ("authorizer_is_independent_statistician", "authorizer_is_methodologist",
                     "external_peer_review_performed", "external_methodological_review_performed",
                     "institutional_approval_obtained", "handwritten_signature_captured"):
            if a.get(flag) is not False:
                self.fail(f"authorization falsely claims {flag}")
        if a.get("reviewer_identity_recorded") is not None:
            self.fail("a reviewer identity is claimed but none exists")
        blob = json.dumps(self.amendment).lower()
        for tok in FORBIDDEN_ROLE_TOKENS:
            # allowed only in an explicitly negated context
            idx = 0
            while True:
                i = blob.find(tok, idx)
                if i < 0:
                    break
                window = blob[max(0, i - 80):i]
                if not any(n in window for n in ("false", "not ", "no ", "never", "_performed\": false")):
                    self.fail(f"amendment appears to claim {tok!r}")
                    break
                idx = i + len(tok)

    def check_gates(self) -> None:
        g = self.amendment.get("gates") or {}
        if g.get("f5_construct_validity") != "OPEN":
            self.fail("F5 is not marked OPEN")
        if g.get("f5_closed_by_this_amendment") is not False:
            self.fail("amendment claims to close F5")
        if g.get("prospective_collection") != "BLOCKED":
            self.fail("prospective collection is not marked BLOCKED")
        if g.get("analysis_run") is not False or g.get("scientific_result") is not None:
            self.fail("amendment claims an analysis was run or a result exists")
        e = self.amendment.get("epistemic_status") or {}
        if e.get("no_prospective_outcome_existed_or_was_inspected") is not True:
            self.fail("amendment does not assert that no prospective outcome was inspected")
        if e.get("external_preregistration_performed") is not False:
            self.fail("amendment claims external preregistration")
        sp = (e.get("split_tolerance_provenance") or {})
        if sp.get("continuous_df_preregistered_in_pr17") is not False:
            self.fail("split tolerance provenance lost: continuous df marked preregistered in PR #17")
        if "PR #18" not in (sp.get("continuous_satterthwaite_df") or ""):
            self.fail("continuous df provenance does not name the PR #18 tolerance")

    def check_decisions(self) -> None:
        d = self.amendment.get("decisions") or {}
        missing = [f"D{i}" for i in range(1, 17) if f"D{i}" not in d]
        if missing:
            self.fail(f"amended decisions absent: {missing}")
            return

        if d["D1"]["selected"] != "CR2_BIAS_REDUCED_LINEARIZATION":
            self.fail("D1 is not CR2")
        if "CR1" in d["D1"]["selected"] or d["D1"]["selected"].startswith("CR1"):
            self.fail("CR1 became primary")
        if "CR3" in json.dumps(d["D1"]):
            self.fail("CR3 appears in the D1 selection")
        impl = d["D1"]["authoritative_implementation"]
        if impl["language"] != "R" or impl["package"] != "clubSandwich":
            self.fail("D1 authoritative implementation is not the R/clubSandwich path")
        if d["D1"]["python_role"] != "VALIDATED_CROSS_CHECK_NOT_AUTHORITATIVE":
            self.fail("official R / Python cross-check roles are reversed")

        if d["D2"]["additional_cr1_scaling_applied"] is not False or \
                d["D2"]["second_correction_applied"] is not False:
            self.fail("D2 applies a second finite-sample correction")

        if d["D3"]["selected"] != "COEFFICIENT_SPECIFIC_SATTERTHWAITE":
            self.fail("D3 is not coefficient-specific Satterthwaite")
        if "PR #18" not in d["D3"]["provenance_qualification"]:
            self.fail("D3 lost its PR #18 df-tolerance provenance qualification")

        if d["D4"]["selected"] != "NOT_USED_IN_HYP01" or d["D4"]["is_primary"] or \
                d["D4"]["is_sensitivity"] or d["D4"]["may_overturn_primary"]:
            self.fail("bootstrap settings became active")
        for k in ("D5", "D6", "D7"):
            if d[k]["selected"] != "NOT_APPLICABLE" or d[k].get("placeholder_retained") is not False:
                self.fail(f"{k} retains an activatable bootstrap placeholder")

        if d["D8"]["selected"] != "RETAIN_SINGLETON_TICKER_CLUSTERS" or \
                d["D8"]["singleton_presence_is_an_exclusion_rule"] is not False:
            self.fail("D8 singleton policy altered")

        if d["D9"]["selected"] != "REFUSE_AND_ABORT" or \
                d["D9"]["refusal_is_not_a_null_result"] is not True:
            self.fail("D9 refusal policy altered")
        if d["D9"]["thresholds_are_newly_invented"] is not False:
            self.fail("D9 claims newly invented thresholds")
        src = d["D9"]["thresholds_source"]
        runner = ROOT / src["path"]
        if not runner.is_file() or sha_lf(runner) != src["sha256_lf"]:
            self.fail("D9 threshold source drifted from the recorded runner SHA")

        if d["D10"]["minimum_cluster_cutoff"] is not None or \
                d["D10"]["minimum_effective_df_cutoff"] is not None or \
                d["D10"]["invented_cutoff_imposed"] is not False:
            self.fail("D10 introduced a cluster or effective-df cutoff")

        o = d["D11"]["official_confirmatory_calculation"]
        if o["language"] != "R" or o["package"] != "clubSandwich":
            self.fail("D11 official calculation is not the R path")
        if d["D11"]["python_role"] != "INDEPENDENT_IMPLEMENTATION_CROSS_CHECK" or \
                d["D11"]["roles_may_not_be_reversed"] is not True:
            self.fail("D11 R/Python roles reversed")
        disc = d["D11"]["discrepancy_rule"]
        if disc["averaging_permitted"] or disc["manual_reconciliation_permitted"] or \
                disc["selecting_preferred_output_permitted"]:
            self.fail("D11 discrepancy rule weakened")
        # package versions must match the committed lockfile
        rlock = json.loads((ROOT / "tools/hyp01_r_reference/r-packages.lock.json").read_text(encoding="utf-8"))
        locked = {p["package"]: p["version"] for p in rlock["packages"]}
        if o.get("locked_packages") != locked:
            self.fail("package versions drifted from the committed R lockfile")
        if o.get("language_version") != rlock["r"]["ci_pinned_version"]:
            self.fail("R version drifted from the committed R lockfile")
        # The headline package_version must also agree with the lockfile. Checking
        # only `locked_packages` left this field free to drift on its own, which a
        # mutation test caught.
        if o.get("package_version") != locked.get(o.get("package")):
            self.fail(f"D11 package_version {o.get('package_version')!r} drifted from the "
                      f"lockfile value {locked.get(o.get('package'))!r}")
        d1impl = d["D1"]["authoritative_implementation"]
        if d1impl.get("package_version") != locked.get(d1impl.get("package")):
            self.fail("D1 authoritative_implementation.package_version drifted from the lockfile")
        if d1impl.get("language_version") != rlock["r"]["ci_pinned_version"]:
            self.fail("D1 authoritative_implementation.language_version drifted from the lockfile")

        if d["D12"]["selected"] != "TREATMENT_REFERENCE_CODING" or \
                d["D12"]["reference_selection_is_deterministic"] is not True or \
                d["D12"]["reference_selection_may_use_outcomes"] is not False or \
                d["D12"]["applies_to_primary_model"] is not False:
            self.fail("D12 sector coding altered")

        if d["D13"]["pooling_threshold_eligible_events"] != 3 or \
                d["D13"]["pooling_may_read_outcomes"] is not False or \
                d["D13"]["primary_unadjusted_model_altered"] is not False or \
                d["D13"]["ticker_clusters_pooled_or_removed_or_altered"] is not False:
            self.fail("D13 sector pooling altered or reads outcomes")
        if d["D13"]["threshold_is_authorizer_selected_governance_rule"] is not True or \
                d["D13"]["threshold_established_by_pr18"] is not False:
            self.fail("D13 threshold provenance misstated")

        if d["D14"]["selected"] != "NO_CAP" or d["D14"]["cap_value"] is not None or \
                d["D14"]["selective_deletion_permitted"] is not False:
            self.fail("a per-ticker cap appeared")

        fam = d["D15"]["protected_family"]
        if fam["alpha"] != 0.05 or fam["sidedness"] != "two_sided" or \
                fam["primary_coefficient_tests"] != 1 or fam["primary_predictors"] != 1 or \
                fam["primary_outcomes"] != 1:
            self.fail("alpha, sidedness or the protected family changed")
        if d["D15"]["secondary_may_reinterpret_or_replace_primary"] is not False:
            self.fail("D15 allows secondary analyses to replace the primary")

        if d["D16"]["n_events"] != 60 or \
                d["D16"]["n_events_characterization"] != "GOVERNANCE_FLOOR_NOT_A_DEMONSTRATED_POWER_TARGET":
            self.fail("n=60 is not characterized as a governance floor")
        if d["D16"]["study_is_adequately_powered_claim"] is not False or \
                d["D16"]["prospective_outcomes_used"] is not False or \
                d["D16"]["retrospective_reconstruction_effects_used"] is not False:
            self.fail("D16 makes a power claim or uses outcomes")

    def check_unamended_drift(self) -> None:
        amended = set((self.amendment.get("amends") or {}).get("fields_amended", []))
        for dotted, expected in UNAMENDED_INVARIANTS.items():
            if dotted in amended:
                self.fail(f"invariant field is listed as amended: {dotted}")
                continue
            got = dig(self.base, dotted)
            if got is KeyError:
                self.fail(f"unamended base-lock field absent: {dotted}")
            elif got != expected:
                self.fail(f"unamended base-lock field drifted: {dotted} = {got!r}, expected {expected!r}")

    def check_proposed_excluded(self) -> None:
        if self.amendment.get("proposed_v1_1_is_authoritative") is not False:
            self.fail("proposed v1.1 is marked authoritative")
        res = self.amendment.get("effective_lock_resolution") or {}
        if res.get("proposed_v1_1_participates_in_resolution") is not False:
            self.fail("proposed v1.1 participates in resolution")
        if res.get("competing_amendment_policy") != "FAIL_CLOSED":
            self.fail("competing-amendment policy is not fail-closed")

    # ---------------------------------------------------------------- run
    def resolve(self) -> dict | None:
        self.load()
        if self.violations:
            return None
        self.check_hashes()
        self.check_authorization()
        self.check_gates()
        self.check_decisions()
        self.check_unamended_drift()
        self.check_proposed_excluded()
        if self.violations:
            return None

        d = self.amendment["decisions"]
        return {
            "artifact": "GST HYP-01 effective statistical lock (resolved)",
            "schema": "GST_HYP01_EFFECTIVE_LOCK_REPORT_v1",
            "generated_from": {
                "base_lock": BASE_LOCK.name,
                "base_lock_sha256_lf": sha_lf(BASE_LOCK),
                "amendment": self.amendment_path.name,
                "amendment_sha256_lf": sha_lf(self.amendment_path),
                "proposed_v1_1_excluded": True,
                "inputs_note": ("Resolved solely from the base lock and the dated amendment. "
                                "No other artifact contributes a rule."),
            },
            "authorization": {
                "statement_verbatim": self.amendment["authorization"]["statement_verbatim"],
                "authorizer_role": self.amendment["authorization"]["authorizer_role"],
                "authorization_declared_date": self.amendment["authorization"]["authorization_declared_date"],
                "authorization_date_basis": self.amendment["authorization"]["authorization_date_basis"],
                "recorded_at_utc": self.amendment["authorization"]["recorded_at_utc"],
                "externally_peer_reviewed": False,
            },
            "effective_state": {
                "statistical_package": "AUTHORIZED",
                "implementation": "VALIDATED",
                "implementation_validation_is_not_scientific_proof": True,
                "f5_construct_validity": "OPEN",
                "prospective_collection": "BLOCKED",
                "scientific_result": None,
                "analysis_run": False,
                "external_preregistration": "NOT_PERFORMED",
            },
            "effective_decisions": {k: d[k]["selected"] for k in
                                    [f"D{i}" for i in range(1, 17)]},
            "authoritative_calculation": d["D11"]["official_confirmatory_calculation"],
            "python_role": d["D11"]["python_role"],
            "refusal_thresholds": d["D9"]["thresholds_verbatim"],
            "unamended_base_lock_invariants": UNAMENDED_INVARIANTS,
            "amended_fields": self.amendment["amends"]["fields_amended"],
            "violations": [],
        }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Resolve the effective HYP-01 lock (fails closed).")
    ap.add_argument("--check", action="store_true", help="verify only; emit nothing")
    ap.add_argument("--emit", metavar="OUT", help="write the effective-lock report")
    a = ap.parse_args(argv)

    r = Resolver()
    report = r.resolve()
    if report is None:
        print("EFFECTIVE LOCK RESOLUTION FAILED CLOSED:")
        for v in r.violations:
            print(f"  - {v}")
        print("\nNo effective-lock report was emitted.")
        return 1

    print("effective lock resolved:")
    for k, v in report["effective_decisions"].items():
        print(f"  {k:4s} {v}")
    print(f"  F5={report['effective_state']['f5_construct_validity']} "
          f"collection={report['effective_state']['prospective_collection']} "
          f"result={report['effective_state']['scientific_result']}")
    if a.emit:
        out = Path(a.emit)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
