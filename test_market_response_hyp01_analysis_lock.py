#!/usr/bin/env python3
# Deterministic tests for the HYP-01 primary analysis lock v1.0.
#
# Preregistration/documentation tests only. No model is implemented or run, no
# historical or prospective outcome is analysed, no candidate is screened, no
# socket is opened.
#
# Run directly: python test_market_response_hyp01_analysis_lock.py

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
from pathlib import Path

# --- blockers installed BEFORE importing any project module ----------------


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during analysis-lock validation")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

_BANNED_TOP = {"yfinance", "pytrends", "requests", "urllib3", "httpx", "aiohttp"}


class _BanProviders:
    # find_spec, not the legacy find_module (removed in 3.12).
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _BANNED_TOP:
            raise ImportError("BLOCKED provider import: " + fullname)
        return None


sys.meta_path.insert(0, _BanProviders())

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))

from gst_market_response import completeness as C  # noqa: E402
from gst_market_response.identity import VALID_RELEASE_SESSIONS  # noqa: E402

LSE = HERE / "Live Signal Engine"
LOCK_J = LSE / "GST_HYP01_ANALYSIS_LOCK_v1.0.json"
LOCK_M = LSE / "GST_HYP01_ANALYSIS_LOCK_v1.0_DRAFT.md"
RULES = LSE / "GST_HYP01_ELIGIBILITY_AND_FREEZE_RULES_v1.0.md"
HYP_J = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json"
COHORT_J = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json"
REGISTRY_P = LSE / "Market_Response_Event_Registry" / "registry.jsonl"

L = json.loads(LOCK_J.read_text(encoding="utf-8"))
MD = LOCK_M.read_text(encoding="utf-8")
RL = RULES.read_text(encoding="utf-8")

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


# ===================== 1. predictor ========================================

def test_1_predictor():
    p = L["predictor"]
    check("1. primary predictor is exactly gst_zscore", p["primary"] == "gst_zscore")
    check("1b. it is continuous", p["form"] == "continuous")
    check("1c. it is unthresholded", p["thresholded"] is False)
    check("1d. measured at the pre-event anchor", "pre-event anchor" in p["measured_at"])
    rules = " | ".join(p["rules"]).lower()
    for needle in ("unthresholded", "no data-driven cutoff", "no winsorization",
                   "no outcome-informed transformation", "binning"):
        check(f"1e. predictor rule bars: {needle}", needle in rules)
    check("1f. Wikipedia is NOT co-primary", p["wikipedia_is_co_primary"] is False)
    check("1g. Wikipedia cannot change the confirmatory conclusion",
          "cannot change the HYP-01 confirmatory conclusion" in p["wikipedia_rule"])
    check("1h. gst_zscore is a real production strict-core field",
          "gst_zscore" in C.STRICT_CORE_SIX_FIELDS)


# ===================== 2. primary outcome ==================================

def test_2_primary_outcome():
    o = L["primary_outcome"]
    check("2. primary outcome is exactly abs_overnight_gap", o["field"] == "abs_overnight_gap")
    check("2b. defined as abs(overnight_gap)", o["definition"] == "abs(overnight_gap)")
    check("2c. the signed formula is the existing one",
          o["signed_definition"] == "overnight_gap = next_session_open / previous_close - 1")
    check("2d. no new formula is created", o["new_formula_created"] is False)
    check("2e. the signed field is production-implemented",
          o["signed_field_implemented_by"].endswith("derivations.overnight_gap"))
    check("2f. the abs helper is production-implemented",
          o["absolute_helper_implemented_by"].endswith("derivations.abs_or_none"))
    # honesty: the lock must record that the field is not yet emitted, and that
    # claim must be TRUE of the tree as it stands.
    check("2g. the lock records the persistence gap",
          o["persistence_status"] == "SPECIFIED_NOT_YET_EMITTED")
    check("2h. the gap is declared blocking for freeze", o["blocking_for_freeze"] is True)
    check("2i. abs_overnight_gap is genuinely NOT in D1_REQUIRED_FIELDS (claim verified)",
          "abs_overnight_gap" not in C.D1_REQUIRED_FIELDS)
    pkg = "\n".join(p.read_text(encoding="utf-8") for p in (HERE / "gst_market_response").glob("*.py"))
    check("2j. no module emits an abs_* response key (claim verified)",
          not re.search(r"abs_overnight_gap|abs_open_to_|abs_close_to", pkg))
    check("2k. abs_or_none does exist in production (claim verified)",
          "def abs_or_none" in pkg)
    check("2l. the specification authority is cited",
          any("SPEC_v0.1" in s for s in o["specification_authority"]))
    check("2m. the Markdown states the gap plainly",
          "specified but not yet emitted" in MD.lower())


# ===================== 3. release sessions =================================

def test_3_sessions():
    s = L["sample"]
    check("3. BMO and AMC are eligible", s["eligible_release_sessions"] == ["BMO", "AMC"])
    check("3b. INTRADAY is ineligible for THIS analysis",
          s["ineligible_release_sessions"] == ["INTRADAY"])
    check("3c. the union is the production vocabulary",
          sorted(s["eligible_release_sessions"] + s["ineligible_release_sessions"])
          == sorted(VALID_RELEASE_SESSIONS))
    r = s["intraday_rationale"]
    check("3d. INTRADAY events remain enrolled in the overall cohort",
          "remain enrolled in the overall cohort" in r)
    check("3e. it is framed as a measurement incompatibility, not exclusion",
          "MEASUREMENT INCOMPATIBILITY" in r and "not a post-hoc exclusion" in r)
    check("3f. the rule is fixed before any data exists",
          "before any data exists" in r)


# ===================== 4. primary model ====================================

def test_4_primary_model():
    m = L["primary_model"]
    check("4. formula is exactly abs_overnight_gap ~ gst_zscore",
          m["formula"] == "abs_overnight_gap ~ gst_zscore")
    check("4b. estimator is OLS", m["estimator"] == "ordinary_least_squares")
    check("4c. two-sided null beta_gst = 0",
          m["sidedness"] == "two_sided" and m["null_hypothesis"] == "beta_gst = 0")
    check("4d. alpha is exactly 0.05", m["alpha"] == 0.05)
    cov = m["covariance"]
    check("4e. ticker-clustered covariance",
          cov["type"] == "cluster_robust" and cov["cluster_variable"] == "ticker")
    check("4f. finite-sample correction enabled", cov["finite_sample_correction"] is True)
    check("4g. effect is per one-unit increase in GST z-score",
          "per one-unit increase in GST z-score" in m["effect_interpretation"])
    for q in ("coefficient", "95% confidence interval", "p-value",
              "eligible-event count", "unique-ticker count"):
        check(f"4h. reports {q}", q in m["required_reported_quantities"])
    check("4i. the primary model has NO covariates", m["covariates"] == [])
    check("4j. no data-driven covariates", m["data_driven_covariates"] is False)
    check("4k. no covariate may be selected on observed data",
          "on the basis of observed data" in m["covariate_rule"])
    check("4l. the model is neither implemented nor run in this task",
          m["implemented_in_this_task"] is False and m["run_in_this_task"] is False)
    # no analysis runner may exist
    runners = [p.name for p in HERE.glob("*.py")
               if re.search(r"hyp01.*(run|analy)|analy.*hyp01", p.name, re.I)
               and not p.name.startswith("test_")]
    check(f"4m. no HYP-01 analysis runner was created (found={runners})", not runners)


def test_5_environment_freeze():
    e = L["environment_freeze"]
    check("5. the environment must be frozen before results run",
          e["must_be_frozen_before_results_run"] is True)
    for f in ("statistics_package", "statistics_package_version",
              "cluster_covariance_option_string", "finite_sample_correction_option",
              "analysis_code_commit_sha"):
        check(f"5b. {f} is present and awaiting the freeze",
              e["fields"][f] == "TO_BE_FROZEN_AT_EVENT_60")
    check("5c. the note explains why they are unset now",
          "no analysis code exists yet" in e["note"])


# ===================== 6. adjusted model is secondary ======================

def test_6_adjusted_is_secondary():
    a = L["adjusted_sensitivity_model"]
    check("6. the adjusted model is secondary sensitivity only",
          a["role"] == "secondary_sensitivity_only")
    check("6b. it is not co-primary", a["is_co_primary"] is False)
    check("6c. it cannot overturn the primary", a["can_overturn_primary"] is False)
    check("6d. it cannot rescue the primary", a["can_rescue_primary"] is False)
    check("6e. it uses the existing realized_volatility field",
          a["realized_volatility_field"] == "realized_volatility"
          and "realized_volatility" in C.STRICT_CORE_SIX_FIELDS)
    check("6f. it uses the existing release-session classification",
          a["release_session_source"].endswith("determine_release_market_session"))
    check("6g. it uses the existing sector mapping",
          a["sector_mapping_source"] == "gst_market_response.sector_mapping")
    check("6h. panel IV may not be used as an implied-move benchmark or substitute",
          "must NOT be used as an implied-move benchmark" in a["panel_iv_prohibition"])
    check("6i. same ticker-clustered finite-sample-corrected covariance",
          a["covariance"] == {"type": "cluster_robust", "cluster_variable": "ticker",
                              "finite_sample_correction": True})


def test_7_secondary_analyses():
    s = L["secondary_analyses"]
    check("7. secondary analyses carry no confirmatory claim",
          s["independent_confirmatory_claim"] is False)
    check("7b. they may not redefine the primary outcome",
          s["may_redefine_primary_outcome"] is False)
    names = " | ".join(a["analysis"] for a in s["registered"])
    for needle in ("wiki_zscore", "abs_open_to_30m", "abs_open_to_close",
                   "full_session_range", "sector-relative", "rank-based"):
        check(f"7c. registered secondary includes {needle}", needle in names)
    check("7d. every secondary is labelled secondary or exploratory",
          all(a["status"] in ("registered_secondary", "registered_exploratory")
              for a in s["registered"]))


# ===================== 8. missingness and exclusions =======================

def test_8_missingness():
    m = L["missingness_and_exclusions"]
    for k in ("imputation", "zero_fill", "winsorization", "outlier_deletion"):
        check(f"8. {k} is prohibited", m[k] == "prohibited")
    bases = " | ".join(m["prohibited_removal_bases"]).lower()
    for needle in ("direction", "magnitude", "surprise", "news", "options availability",
                   "outlier"):
        check(f"8b. removal based on {needle} is prohibited", needle in bases)
    check("8c. provider/schema failure stays a documented missing observation",
          "DOCUMENTED MISSING OBSERVATION" in m["provider_or_schema_failure"])
    check("8d. a failed event stays in the enrollment audit",
          "remains in the enrollment audit" in m["failed_event_retained_in_audit"])
    check("8e. one event counts once", m["one_event_counts_once"] is True)
    check("8f. duplicate ticker/fiscal-quarter counts once",
          m["duplicate_ticker_fiscal_quarter_counts_once"] is True)
    check("8g. DELL receives no exemption",
          m["dell_exemption"] is False and "No exemption" in m["dell_rule"])


# ===================== 9. ordering and freeze ==============================

def test_9_ordering_and_freeze():
    o = L["sample"]["ordering"]
    check("9. primary sort key is the derived response-session date",
          "response-session date" in o["primary_key"])
    check("9b. the response session comes from the production calendar function",
          o["response_session_source"].endswith("compute_expected_next_full_trading_session_xnys"))
    check("9c. tie-break is event_id ascending", "event_id" in o["tie_breaker"])
    check("9d. the ordering is declared deterministic", o["deterministic"] is True)
    check("9e. the ordering cannot be influenced by results",
          "cannot be influenced by results" in o["note"])
    check("9f. target n is 60", L["sample"]["target_n"] == 60)

    f = L["freeze_and_display"]
    check("9g. threshold is 60", f["threshold"] == 60)
    check("9h. only count and status may be displayed before the threshold",
          set(f["before_threshold_display_allowed"]) == {"eligible-event count", "status"})
    for needle in ("effect estimate", "direction", "plot", "interim p-value",
                   "confidence interval", "informal description"):
        check(f"9i. before the threshold, {needle} is prohibited",
              needle in f["before_threshold_display_prohibited"])
    check("9j. the freeze sequence freezes IDs, then env, then verifies, then runs once",
          len(f["freeze_sequence"]) == 4 and f["run_count"] == 1
          and "freeze the exact 60 event IDs" in f["freeze_sequence"][0]
          and "run the primary model ONCE" in f["freeze_sequence"][3])
    check("9k. optional stopping is prohibited", f["optional_stopping"] == "prohibited")
    check("9l. repeated testing is prohibited", f["repeated_testing"] == "prohibited")
    check("9m. later events become a separately labelled extension cohort",
          f["later_events"] == "extension_cohort_separately_labeled"
          and "never enlarge the frozen set" in f["extension_cohort_rule"])
    check("9n. no model change after the freeze",
          f["model_change_after_freeze"] == "prohibited")
    check("9o. no results and no frozen ids exist yet",
          L["results"] is None and L["frozen_event_ids"] == [] and L["eligible_events_now"] == 0)
    # the rules document must carry the same procedure
    check("9p. the rules document orders freeze-then-run",
          RL.index("Freeze the event set") < RL.index("Run the primary model once"))
    check("9q. the rules document states the count is not a result",
          "count is not a result" in RL)


# ===================== 10. nothing else changed ============================

def test_10_nothing_else_changed():
    hyp = json.loads(HYP_J.read_text(encoding="utf-8"))
    H = {h["hypothesis_id"]: h for h in hyp["hypotheses"]}
    check("10. HYP-02 threshold unchanged at 60", H["HYP-02"]["minimum_eligible_events"] == 60)
    check("10b. HYP-03 threshold unchanged at 40", H["HYP-03"]["minimum_eligible_events"] == 40)
    check("10c. HYP-02 status unchanged",
          H["HYP-02"]["status"] == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED")
    check("10d. HYP-03 status unchanged",
          H["HYP-03"]["status"] == "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED")
    check("10e. HYP-02 missing-measurement classification unchanged",
          H["HYP-02"]["required_external_measurement"]["availability"]
          == "event_dossier_schema_only_no_capture_path")
    check("10f. HYP-03 missing-measurement classification unchanged",
          H["HYP-03"]["required_missing_measurement"]["availability"] == "not_implemented")
    check("10g. HYP-02/03 unresolved decisions unchanged in count",
          len(H["HYP-02"]["unresolved_analysis_decisions"]) == 3
          and len(H["HYP-03"]["unresolved_analysis_decisions"]) == 3)
    check("10h. HYP-01 remains the sole primary confirmatory",
          hyp["statistical_governance"]["primary_confirmatory_hypothesis"] == "HYP-01")
    check("10i. the lock declares HYP-02/03 untouched",
          "threshold" in L["unchanged_by_this_lock"]["hyp_02"]
          and "status" in L["unchanged_by_this_lock"]["hyp_03"])

    cohort = json.loads(COHORT_J.read_text(encoding="utf-8"))
    check("10j. cohort protocol version unchanged", cohort["protocol_version"] == "1.0")
    check("10k. cohort screening rows remain empty", cohort["screening_rows"] == [])
    check("10l. no cohort screening log exists",
          not (LSE / "Market_Response_Event_Registry" / "cohort_screening_log.jsonl").exists())
    check("10m. cohort window/target/lead unchanged",
          cohort["collection_window"]["begins"] == "2026-09-01"
          and cohort["collection_window"]["ends"] == "2027-05-31"
          and cohort["target"]["min_registered_events"] == 60
          and cohort["minimum_registration_lead"]["sessions"] == 5)

    # v0.2 production untouched
    check("10n. D1 interval fields unchanged",
          C.D1_REQUIRED_FIELDS == ("overnight_gap", "open_to_30m",
                                   "thirty_min_to_close", "open_to_close"))
    check("10o. strict six-field core unchanged",
          C.STRICT_CORE_SIX_FIELDS == ("gst_zscore", "wiki_zscore", "panel_implied_volatility",
                                       "realized_volatility", "previous_close", "volume"))

    # DELL registry byte-identical, outside the diff
    raw = REGISTRY_P.read_bytes()
    lf = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    check("10p. the DELL registry blob is byte-identical to the baseline",
          lf == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    check("10q. exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["verification_status"] == "verified")
    check("10r. no event log or stage marker exists anywhere",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


# ===================== 11. no result, no strategy =========================

_RESULT_PATTERNS = (
    r"\bp\s*[=<>]\s*\.?\d", r"\br\s*=\s*-?\.?\d", r"\bCI\s*[:=]\s*[\[(]",
    r"\bwe (find|found|observe|show)\b", r"\bsignificant at\b",
    r"\bbeta\s*=\s*-?\.?\d", r"\bcoefficient (of|was|is)\s*-?\.?\d",
)
_STRATEGY_TERMS = ("profitable", "trading strategy", "generate alpha", "excess alpha",
                   "backtest", "sharpe", "win rate", "buy signal", "sell signal",
                   "return forecast")
_NEGATIONS = ("not ", "no ", "never", "prohibit", "out of scope", "does not", "do not",
              "cannot", "may not", "without", "gated", "before", "deny")


def test_11_no_results_or_strategy():
    for label, text in (("lock Markdown", MD), ("rules", RL),
                        ("JSON", json.dumps(L, indent=2))):
        offenders = [ln.strip()[:90] for ln in text.splitlines()
                     if any(re.search(p, ln, re.I) for p in _RESULT_PATTERNS)]
        check(f"11. the {label} reports no computed result (offenders={offenders})", not offenders)
        bad = [ln.strip()[:90] for ln in text.splitlines()
               if any(t in ln.lower() for t in _STRATEGY_TERMS)
               and not any(n in ln.lower() for n in _NEGATIONS)]
        check(f"11b. every strategy-term mention in the {label} is a disclaimer "
              f"(offenders={bad})", not bad)
    check("11c. results are explicitly null", L["results"] is None)
    check("11d. the results note says no model was implemented or run",
          "No model was implemented and none was run" in L["results_note"])


# ===================== 12. no network or provider =========================

def test_12_no_network_or_provider():
    reached = []
    for host in ("data.alpaca.markets", "en.wikipedia.org", "trends.google.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001
            pass
    check(f"12. sockets are blocked (reached={reached})", not reached)
    for mod in ("requests", "yfinance", "pytrends"):
        if mod in sys.modules:
            check(f"12b. {mod} is not importable", False)
            continue
        try:
            __import__(mod)
            check(f"12b. {mod} is not importable", False)
        except ImportError:
            check(f"12b. {mod} is not importable", True)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"12c. no provider module reached sys.modules (leaked={leaked})", not leaked)
    for label, text in (("lock", MD), ("rules", RL)):
        check(f"12d. the {label} contains no fetch/download instruction",
              not re.search(r"\b(curl|wget|urlopen|requests\.get)\b", text))


if __name__ == "__main__":
    test_1_predictor()
    test_2_primary_outcome()
    test_3_sessions()
    test_4_primary_model()
    test_5_environment_freeze()
    test_6_adjusted_is_secondary()
    test_7_secondary_analyses()
    test_8_missingness()
    test_9_ordering_and_freeze()
    test_10_nothing_else_changed()
    test_11_no_results_or_strategy()
    test_12_no_network_or_provider()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-01 ANALYSIS LOCK TESTS PASSED")
    sys.exit(0)
