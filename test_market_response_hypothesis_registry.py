#!/usr/bin/env python3
# Deterministic tests for the GST Prospective Hypothesis Registry v1.0.
#
# Registry-definition tests only. No panel run, no provider, no socket, no
# candidate screening, no prospective observation, no result computation.
#
# Run directly: python test_market_response_hypothesis_registry.py

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
    raise NetworkBlocked("network access attempted during registry validation")


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

LSE = HERE / "Live Signal Engine"
REG_J = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0.json"
REG_M = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.0_DRAFT.md"
GATES = LSE / "GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md"
CROSS = LSE / "GST_PROSPECTIVE_HYPOTHESIS_FIELD_CROSSWALK_v1.0.md"
COHORT_J = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json"
COHORT_M = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md"
REGISTRY_P = LSE / "Market_Response_Event_Registry" / "registry.jsonl"

DOC = json.loads(REG_J.read_text(encoding="utf-8"))
MD = REG_M.read_text(encoding="utf-8")
GT = GATES.read_text(encoding="utf-8")
CW = CROSS.read_text(encoding="utf-8")
H = {h["hypothesis_id"]: h for h in DOC["hypotheses"]}

PENDING = "PENDING_SEPARATE_ANALYSIS_LOCK"
NOT_IMPL = "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED"

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


# ===================== 1. thresholds are exactly 60/60/40 ==================

def test_1_thresholds():
    check("1. exactly three hypotheses are registered", len(DOC["hypotheses"]) == 3)
    check("1b. ids are HYP-01, HYP-02, HYP-03",
          sorted(H) == ["HYP-01", "HYP-02", "HYP-03"])
    for hid, n in (("HYP-01", 60), ("HYP-02", 60), ("HYP-03", 40)):
        check(f"1c. {hid} minimum_eligible_events is exactly {n}",
              H[hid]["minimum_eligible_events"] == n and isinstance(
                  H[hid]["minimum_eligible_events"], int))
    check("1d. the Markdown states the same three thresholds",
          "**60**" in MD and "**40**" in MD)
    check("1e. the gates document states the same three thresholds",
          re.search(r"HYP-01\s*\|\s*60", GT) and re.search(r"HYP-02\s*\|\s*60", GT)
          and re.search(r"HYP-03\s*\|\s*40", GT))


# ===================== 2. only HYP-01 is primary confirmatory =============

def test_2_single_primary():
    primaries = [h for h in DOC["hypotheses"] if h["is_primary_confirmatory"]]
    check("2. exactly one primary confirmatory hypothesis", len(primaries) == 1)
    check("2b. it is HYP-01", primaries[0]["hypothesis_id"] == "HYP-01")
    g = DOC["statistical_governance"]
    check("2c. governance names HYP-01 as the sole primary",
          g["primary_confirmatory_hypothesis"] == "HYP-01")
    check("2d. HYP-02 is secondary", g["secondary_hypotheses"] == ["HYP-02"]
          and H["HYP-02"]["classification"] == "preregistered_secondary")
    check("2e. HYP-03 is exploratory", g["exploratory_hypotheses"] == ["HYP-03"]
          and H["HYP-03"]["classification"] == "preregistered_exploratory")
    check("2f. promotion on observed results is forbidden",
          "may never be promoted to confirmatory" in g["promotion_rule"])
    check("2g. promotion requires a new dated version written BEFORE the results",
          "before the results" in g["promotion_rule"])


# ===================== 3. no result display before threshold ==============

def test_3_display_gates():
    check("3. no results object exists", DOC["results"] is None)
    check("3b. the results note forbids producing one before the freeze",
          "before that hypothesis's threshold is reached" in DOC["results_note"])
    for hid in H:
        rule = H[hid]["display_rule"]
        n = H[hid]["minimum_eligible_events"]
        check(f"3c. {hid} display rule cites its own threshold {n}", str(n) in rule)
    check("3d. HYP-01's rule enumerates every display form",
          all(t in H["HYP-01"]["display_rule"]
              for t in ("result", "direction", "effect estimate", "plot", "p-value",
                        "confidence interval")))
    for hid in ("HYP-02", "HYP-03"):
        check(f"3e. {hid} accrues no eligible events while not implemented",
              "accrues no eligible events" in H[hid]["display_rule"])
    # the gates document must fail closed on every listed condition
    for cond in ("Hypothesis not registered", "below threshold", "event set not frozen",
                 "unresolved", "not mechanically derivable"):
        check(f"3f. the gates document denies when: {cond}", cond in GT)
    check("3g. all three gates are currently CLOSED",
          GT.count("**CLOSED**") >= 3)
    check("3h. the eligible count itself is explicitly NOT a result",
          "eligible event count itself is not a result" in GT)
    check("3i. a verbal summary counts as a display", "verbal summary" in GT)
    check("3j. absence of a rule is never permission",
          "never read as permission" in GT)


# ===================== 4. missing implementation != eligibility ===========

def test_4_missing_impl_is_not_eligibility():
    check("4. HYP-01 is ACTIVE_COLLECTING", H["HYP-01"]["status"] == "ACTIVE_COLLECTING")
    check("4b. HYP-02 is PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
          H["HYP-02"]["status"] == NOT_IMPL)
    check("4c. HYP-03 is PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED",
          H["HYP-03"]["status"] == NOT_IMPL)
    check("4d. the status definition requires field AND capture path",
          "production field AND a production capture path"
          in DOC["statuses"]["ACTIVE_COLLECTING"])
    check("4e. missing implementation is never counted as eligibility",
          "never counted as eligibility" in DOC["statuses"][NOT_IMPL])
    check("4f. every eligible count is zero",
          all(v == 0 for k, v in DOC["eligible_event_counts"].items() if k != "note"))
    # HYP-02's basis must cite the absent capture path and join, not hand-wave
    b2 = H["HYP-02"]["status_basis"]
    check("4g. HYP-02 basis cites that no production code writes the surprise fields",
          "no production code writes them" in b2)
    check("4h. HYP-02 basis cites the missing event->dossier join",
          "no production join" in b2)
    check("4i. HYP-02 surprise availability is dossier-schema-only",
          H["HYP-02"]["required_external_measurement"]["availability"]
          == "event_dossier_schema_only_no_capture_path")
    b3 = H["HYP-03"]["status_basis"]
    check("4j. HYP-03 basis cites the absent post-event attention stage",
          "no post-event ATTENTION capture stage" in b3)
    check("4k. HYP-03 refuses to repurpose gst_slope_v0_1",
          "not a post-event decay half-life" in b3
          and H["HYP-03"]["required_missing_measurement"]["build_authorisation"]
          == "NOT AUTHORISED in this task")
    # and the claims must be TRUE of the tree as it stands
    src = (HERE / "gst_market_response")
    all_src = "\n".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    check("4l. no surprise field exists in the market-response package (claim verified)",
          "surprise" not in all_src.lower())
    check("4m. no attention-decay measurement exists in the package (claim verified)",
          not re.search(r"decay|half_?life", all_src, re.I))
    check("4n. gst_slope_v0_1 does exist and is pre-event (claim verified)",
          "def gst_slope_v0_1" in all_src)


# ===================== 5. options unnecessary for all three ===============

def test_5_options_not_required():
    for hid in H:
        check(f"5. {hid} does not require an options benchmark",
              H[hid]["options_benchmark_required"] is False)
    o = DOC["options_related_classes"]
    check("5b. no options hypothesis is registered", o["registered_hypothesis"] is None)
    check("5c. options classes display status is DENY_NO_REGISTERED_HYPOTHESIS",
          o["result_display_status"] == "DENY_NO_REGISTERED_HYPOTHESIS")
    check("5d. the two options classes are the production classes",
          o["classes"] == [C.HYPOTHESIS_OPTIONS_IMPLIED_MOVE,
                           C.HYPOTHESIS_JOINT_ATTENTION_OPTIONS])
    check("5e. options unavailability never blocks the three hypotheses",
          "never prevents HYP-01, HYP-02 or HYP-03"
          in o["options_never_block_the_registered_hypotheses"])
    # behavioural: a core-only event is still eligible for the core class
    elig = C.ModuleEligibility(
        core_pre_event_eligible=True, option_benchmark_eligible=False,
        joint_full_eligible=False,
        pre_event_completeness_tier=C.PRE_EVENT_TIER_CORE_ONLY,
        option_benchmark_status=C.OptionBenchmarkDisposition.UNAVAILABLE_NO_VERIFIED_SOURCE,
        option_benchmark_unavailable_reason="no OPRA-entitled source")
    check("5f. a core-only event still satisfies the class all three hypotheses need",
          C.is_eligible_for_hypothesis(C.HYPOTHESIS_CORE_ATTENTION_RESPONSE, elig))
    check("5g. every hypothesis requires only the core class",
          all(H[h]["required_eligibility_class"] == C.HYPOTHESIS_CORE_ATTENTION_RESPONSE
              for h in H))


# ===================== 6. classes are not hypotheses ======================

def test_6_class_is_not_a_hypothesis():
    cd = DOC["critical_distinction"]
    check("6. the eligibility classes are the production classes",
          cd["eligibility_classes"] == list(C.HYPOTHESIS_CLASSES))
    check("6b. named hypotheses are separate identifiers",
          cd["named_hypotheses"] == ["HYP-01", "HYP-02", "HYP-03"])
    check("6c. no hypothesis id is a class name and vice versa",
          not (set(cd["named_hypotheses"]) & set(cd["eligibility_classes"])))
    check("6d. a class is explicitly never a hypothesis",
          cd["a_class_is_never_a_hypothesis"] is True
          and "not named research hypotheses" in cd["statement"])
    check("6e. each hypothesis MAPS onto a class rather than being one",
          all("required_eligibility_class" in H[h] for h in H))
    check("6f. the Markdown draws the distinction explicitly",
          "eligibility classes are not hypotheses" in MD.lower())
    check("6g. the crosswalk separates class from hypothesis",
          "Eligibility class versus named hypothesis" in CW)
    # a class name must never be used as a hypothesis_id anywhere
    check("6h. no hypothesis record is keyed by a class name",
          not [h for h in DOC["hypotheses"] if h["hypothesis_id"] in C.HYPOTHESIS_CLASSES])


# ===================== 7-10. counting rules ===============================

def test_7_counting_rules():
    rules = {r["id"]: r["rule"] for r in DOC["counting_rules"]}
    check("7. all ten counting rules are registered",
          set(rules) == {f"CNT-{i}" for i in range(1, 11)} and len(rules) == 10)
    check("7b. CNT-1 one event id counts at most once", "at most once" in rules["CNT-1"])
    check("7c. CNT-2 duplicate ticker/fiscal-quarter never counts twice",
          "never count twice" in rules["CNT-2"])
    check("7d. CNT-3 counts only when every gate and measurement passes",
          "every required gate and measurement" in rules["CNT-3"])
    check("7e. CNT-4 missing values are never zero-filled or imputed",
          "No zero-fill" in rules["CNT-4"] and "no imputation" in rules["CNT-4"])
    check("7f. CNT-5 events are never removed for null or unfavourable results",
          "never removed" in rules["CNT-5"])
    check("7g. CNT-6 ticker clustering required, independence never claimed",
          "clustered analysis" in rules["CNT-6"]
          and "never described as statistically independent" in rules["CNT-6"])
    check("7h. CNT-7 threshold freezes the event set AND analysis commit before results",
          "FREEZES" in rules["CNT-7"] and "before any result is calculated" in rules["CNT-7"])
    check("7i. CNT-8 no optional stopping",
          "No optional stopping" in rules["CNT-8"]
          and "not stopped early" in rules["CNT-8"])
    check("7j. CNT-9 later events form an extension cohort",
          "EXTENSION COHORT" in rules["CNT-9"])
    check("7k. CNT-10 DELL gets no exemption",
          "EVT-DELL-FY27Q2-ERN" in rules["CNT-10"]
          and "No exemption" in rules["CNT-10"])
    check("7l. the Markdown carries all ten rules",
          all(f"CNT-{i}" in MD for i in range(1, 11)))


# ===================== 11. statistical governance =========================

def test_8_statistical_governance():
    g = DOC["statistical_governance"]
    check("8. two-sided inference", g["inference_sidedness"] == "two_sided")
    check("8b. primary alpha is 0.05", g["primary_alpha"] == 0.05)
    check("8c. effect sizes reported", g["report_effect_sizes"] is True)
    check("8d. 95% confidence intervals", g["confidence_interval"] == 0.95)
    check("8e. ticker-cluster-aware inference is required",
          g["ticker_cluster_aware_inference_required"] is True)
    check("8f. no model change after the event set is frozen",
          "after the eligible event set is frozen" in g["model_freeze_rule"])
    check("8g. unresolved terms are marked PENDING, never guessed",
          PENDING in g["unresolved_terms_rule"] and "never guessed" in g["unresolved_terms_rule"])
    check("8h. thresholds are declared governance floors, not power claims",
          "GOVERNANCE ELIGIBILITY FLOORS" in g["power_statement"]
          and "not claims of guaranteed statistical power" in g["power_statement"])
    check("8i. no power calculation was performed on observed results",
          "No power calculation was performed" in g["power_statement"])
    # every hypothesis must carry a cluster decision among its unresolved items
    for hid in H:
        decisions = [d["decision"] for d in H[hid]["unresolved_analysis_decisions"]]
        check(f"8j. {hid} records the ticker-cluster estimator as unresolved",
              any("cluster" in d for d in decisions))
        check(f"8k. {hid} marks every unresolved decision {PENDING}",
              all(d["state"] == PENDING for d in H[hid]["unresolved_analysis_decisions"]))


# ===================== 12. no result / no strategy anywhere ===============

# A REPORTED result, not a mention of the concept. "p-value" appearing in a
# list of things that may NOT be shown is not a result; "p = 0.03" is. These
# patterns require an actual value or an assertive finding clause, so the
# prohibition lists in these documents cannot trip them.
_RESULT_PATTERNS = (
    r"\bp\s*[=<>]\s*\.?\d",          # p = 0.03 / p < .05
    r"\br\s*=\s*-?\.?\d",            # r = 0.41
    r"\bCI\s*[:=]\s*[\[(]",          # CI: [0.1, 0.4]
    r"\bwe (find|found|observe|show)\b",
    r"\bsignificant at\b",
    r"\beffect size (of|was|is)\s*-?\.?\d",
    r"\bmedian\s+[-+]?\d+(\.\d+)?%",
)
# "alpha" alone is the significance level here, not a trading claim -- the
# strategy sense is always qualified.
_STRATEGY_TERMS = ("profitable", "trading strategy", "generate alpha", "excess alpha",
                   "backtest", "sharpe", "win rate", "buy signal", "sell signal",
                   "return forecast")
_NEGATIONS = ("not ", "no ", "never", "prohibit", "out of scope", "does not", "do not",
              "cannot", "may not", "without", "gated", "before", "deny")


def test_9_no_results_or_strategy_claims():
    for label, text in (("registry Markdown", MD), ("gates", GT), ("crosswalk", CW),
                        ("JSON", json.dumps(DOC, indent=2))):
        offenders = []
        for line in text.splitlines():
            low = line.lower()
            if any(t in low for t in _STRATEGY_TERMS) and not any(n in low for n in _NEGATIONS):
                offenders.append(line.strip()[:90])
        check(f"9. every strategy-term mention in the {label} is a disclaimer "
              f"(offenders={offenders})", not offenders)
    for label, text in (("registry Markdown", MD), ("gates", GT), ("crosswalk", CW),
                        ("JSON", json.dumps(DOC, indent=2))):
        offenders = [ln.strip()[:90] for ln in text.splitlines()
                     if any(re.search(p, ln, re.I) for p in _RESULT_PATTERNS)]
        check(f"9b. the {label} reports no computed result (offenders={offenders})", not offenders)
    check("9c. the gates document disclaims any trading interpretation",
          "No trading interpretation" in GT)
    check("9d. reaching a threshold licenses looking, not concluding",
          "licenses **looking**, not **concluding**" in GT)


# ===================== 13. cohort protocol untouched ======================

def test_10_cohort_and_registry_untouched():
    cohort = json.loads(COHORT_J.read_text(encoding="utf-8"))
    check("10. the cohort protocol is still present and version 1.0",
          cohort["protocol_version"] == "1.0")
    check("10b. cohort screening rows remain empty", cohort["screening_rows"] == [])
    check("10c. no cohort screening log file exists",
          not (LSE / "Market_Response_Event_Registry" / "cohort_screening_log.jsonl").exists())
    check("10d. the cohort window is unchanged",
          cohort["collection_window"]["begins"] == "2026-09-01"
          and cohort["collection_window"]["ends"] == "2027-05-31")
    check("10e. the cohort target is unchanged",
          cohort["target"]["min_registered_events"] == 60)
    check("10f. the cohort lead requirement is unchanged",
          cohort["minimum_registration_lead"]["sessions"] == 5)
    check("10g. the cohort Markdown is still present", COHORT_M.exists())
    # DELL registry byte-identical (LF-normalised so a CRLF checkout still matches)
    raw = REGISTRY_P.read_bytes()
    lf = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    check("10h. the DELL registry blob is byte-identical to the recorded baseline",
          lf == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    check("10i. exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["row_type"] == "REGISTRATION"
          and rows[0]["verification_status"] == "verified")
    check("10j. no event log or stage marker exists anywhere",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))
    ids = set(re.findall(r"EVT-[A-Z0-9-]+-FY\d{2}Q\d-[A-Z]+", json.dumps(DOC) + MD + GT + CW))
    check(f"10k. the only event id referenced is the registered DELL event (found={sorted(ids)})",
          ids <= {"EVT-DELL-FY27Q2-ERN"})


# ===================== 14. v0.2 production untouched ======================

def test_11_v0_2_untouched():
    check("11. strict six-field core unchanged",
          C.STRICT_CORE_SIX_FIELDS == ("gst_zscore", "wiki_zscore", "panel_implied_volatility",
                                       "realized_volatility", "previous_close", "volume"))
    check("11b. D1 interval fields unchanged",
          C.D1_REQUIRED_FIELDS == ("overnight_gap", "open_to_30m",
                                   "thirty_min_to_close", "open_to_close"))
    check("11c. D3 interval fields unchanged",
          C.D3_REQUIRED_FIELDS == ("close_T1_to_close_T2", "close_T1_to_close_T3"))
    check("11d. eligibility classes unchanged",
          C.HYPOTHESIS_CLASSES == ("core_attention_vs_equity_response",
                                   "options_implied_move", "joint_attention_plus_options"))
    check("11e. completeness tiers unchanged", C.PRE_EVENT_TIERS == (
        "core_invalid", "core_only_no_option_benchmark", "core_and_option_benchmark"))
    check("11f. protocol version and methodology identifier unchanged",
          C.PROTOCOL_VERSION == "0.2" and C.METHODOLOGY_VERSION_V0_2 == "market_response_v0.2")
    # the registry must bind to exactly the production field lists
    h1 = H["HYP-01"]
    check("11g. HYP-01 binds to the production strict-core fields",
          h1["required_pre_event_fields"]
          == list(C.STRICT_CORE_SIX_FIELDS) + list(C.STRICT_CORE_REQUIRED_PROVENANCE))
    check("11h. HYP-01 binds to the production D1/D3 fields",
          h1["required_response_fields"]["d1"] == list(C.D1_REQUIRED_FIELDS)
          and h1["required_response_fields"]["d3"] == list(C.D3_REQUIRED_FIELDS))
    check("11i. HYP-01 introduces no new formula", h1["new_formula_introduced"] is False)


# ===================== 15. dashboard is not authority =====================

def test_12_dashboard_not_authority():
    d = DOC["external_dashboard_note"]
    check("12. the demo thresholds are recorded as observed",
          d["observed_demo_thresholds"] == {"H1-attention-precedes-repricing": 60,
                                            "H2-wikipedia-vs-search-divergence": 60,
                                            "H3-attention-decay-half-life": 40})
    check("12b. the demo is explicitly NOT the source of authority",
          "NOT the source of authority" in d["authority"])
    check("12c. this registry governs on disagreement",
          "this registry governs" in d["authority"])
    check("12d. the dashboard was not edited by this task",
          d["edited_by_this_task"] is False)
    check("12e. demo counts are labelled fixture values, not observations",
          "fixture values, not real observations" in d["authority"])


# ===================== 16. no network or provider access ==================

def test_13_no_network_or_provider():
    reached = []
    for host in ("data.alpaca.markets", "en.wikipedia.org", "trends.google.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001
            pass
    check(f"13. sockets are blocked during validation (reached={reached})", not reached)
    for mod in ("requests", "yfinance", "pytrends"):
        if mod in sys.modules:
            check(f"13b. {mod} is not importable", False)
            continue
        try:
            __import__(mod)
            check(f"13b. {mod} is not importable", False)
        except ImportError:
            check(f"13b. {mod} is not importable", True)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"13c. no provider module reached sys.modules (leaked={leaked})", not leaked)
    for label, text in (("registry", MD), ("gates", GT), ("crosswalk", CW)):
        check(f"13d. the {label} contains no fetch/download instruction",
              not re.search(r"\b(curl|wget|urlopen|requests\.get)\b", text))


if __name__ == "__main__":
    test_1_thresholds()
    test_2_single_primary()
    test_3_display_gates()
    test_4_missing_impl_is_not_eligibility()
    test_5_options_not_required()
    test_6_class_is_not_a_hypothesis()
    test_7_counting_rules()
    test_8_statistical_governance()
    test_9_no_results_or_strategy_claims()
    test_10_cohort_and_registry_untouched()
    test_11_v0_2_untouched()
    test_12_dashboard_not_authority()
    test_13_no_network_or_provider()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYPOTHESIS REGISTRY TESTS PASSED")
    sys.exit(0)
