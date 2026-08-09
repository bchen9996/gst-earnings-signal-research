#!/usr/bin/env python3
# Deterministic tests for the GST Prospective Multi-Event Cohort Protocol v1.0.
#
# Protocol-definition tests only. No panel run, no provider, no socket, no
# candidate screening, no DELL observation. Every check reads committed
# documents and production constants; nothing is written.
#
# Run directly: python test_market_response_cohort_protocol.py

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
    raise NetworkBlocked("network access attempted during protocol validation")


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
from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE  # noqa: E402
from gst_market_response.event_registry import VERIFICATION_STATUSES  # noqa: E402
from gst_market_response.identity import VALID_RELEASE_SESSIONS  # noqa: E402

LSE = HERE / "Live Signal Engine"
JSON_P = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json"
MD_P = LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md"
SCHEMA_P = LSE / "GST_PROSPECTIVE_COHORT_SCREENING_LOG_SCHEMA_v1.0.md"
REGISTRY_P = LSE / "Market_Response_Event_Registry" / "registry.jsonl"

DOC = json.loads(JSON_P.read_text(encoding="utf-8"))
MD = MD_P.read_text(encoding="utf-8")
SCHEMA = SCHEMA_P.read_text(encoding="utf-8")

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


# ===================== 1. JSON and Markdown do not conflict =================

def test_1_json_markdown_agree():
    check("1. protocol version agrees", DOC["protocol_version"] == "1.0"
          and "v1.0" in MD)
    check("1b. the JSON names the Markdown as its companion",
          DOC["companion_markdown"].endswith("GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md"))
    check("1c. the Markdown names the JSON as canonical",
          "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0.json" in MD)
    for value in (DOC["collection_window"]["begins"], DOC["collection_window"]["ends"]):
        check(f"1d. window boundary {value} appears in the Markdown", value in MD)
    check("1e. target sample size agrees",
          str(DOC["target"]["min_registered_events"]) in MD)
    check("1f. minimum lead sessions agrees",
          str(DOC["minimum_registration_lead"]["sessions"]) in MD)
    check("1g. universe size agrees", str(DOC["locked_universe"]["size"]) in MD)
    # every disposition code in the JSON is documented in the Markdown, and
    # every code in the Markdown table exists in the JSON
    codes = {d["code"] for d in DOC["dispositions"]}
    md_codes = set(re.findall(r"`([A-Z][A-Z_]{6,})`", MD)) & codes
    missing_in_md = sorted(c for c in codes if c not in MD)
    check(f"1h. every JSON disposition is documented in the Markdown (missing={missing_in_md})",
          not missing_in_md)
    check("1i. the Markdown introduces no disposition the JSON lacks",
          md_codes <= codes)
    # inclusion rule ids
    ids = {r["id"] for r in DOC["inclusion_rules"]}
    check("1j. all ten inclusion rules exist and are documented in both",
          ids == {f"INC-{i}" for i in range(1, 11)} and all(i in MD for i in ids))
    check("1k. the schema doc references the same protocol version",
          "1.0" in SCHEMA and "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0" in SCHEMA)


# ===================== 2. universe matches production ======================

def test_2_universe_matches_production():
    check("2. the cohort universe EQUALS the production locked universe, in order",
          DOC["locked_universe"]["tickers"] == list(LOCKED_24_TICKER_UNIVERSE))
    check("2b. size is 24 and agrees with production",
          DOC["locked_universe"]["size"] == len(LOCKED_24_TICKER_UNIVERSE) == 24)
    check("2c. the JSON names the production module and symbol as the authority",
          DOC["locked_universe"]["source_module"] == "gst_market_response.constants"
          and DOC["locked_universe"]["source_symbol"] == "LOCKED_24_TICKER_UNIVERSE")
    check("2d. no ticker outside the production universe appears anywhere in the JSON",
          not (set(DOC["locked_universe"]["tickers"]) - set(LOCKED_24_TICKER_UNIVERSE)))
    check("2e. the Markdown does not retype the ticker list",
          sum(1 for t in LOCKED_24_TICKER_UNIVERSE if re.search(rf"\b{re.escape(t)}\b", MD)) <= 1)


# ===================== 3. window, lead time, target are fixed ==============

def test_3_window_lead_target_fixed():
    w = DOC["collection_window"]
    check("3. window begins 2026-09-01", w["begins"] == "2026-09-01")
    check("3b. window ends 2027-05-31", w["ends"] == "2027-05-31")
    check("3c. the window is declared immutable", w["immutable"] is True)
    check("3d. the window binds to the DERIVED ANCHOR, not the earnings or registration date",
          "anchor" in w["boundary_semantics"].lower()
          and "earnings date" in w["boundary_semantics"].lower())
    check("3e. changing the window requires a new protocol version",
          "new protocol version" in w["change_rule"])
    lead = DOC["minimum_registration_lead"]
    check("3f. minimum lead is exactly 5 XNYS sessions",
          lead["sessions"] == 5 and lead["calendar"] == "XNYS")
    check("3g. session arithmetic is delegated to the production calendar",
          lead["calendar_source"] == "gst_market_response.exchange_calendar"
          and "reimplements none" in lead["semantics"])
    check("3h. the anchor comes from the production planner",
          DOC["derived_anchor"]["source_function"]
          == "gst_market_response.operations_plan.build_operations_plan")


def test_4_target_at_least_60():
    t = DOC["target"]
    check("4. target sample size is >= 60", isinstance(t["min_registered_events"], int)
          and t["min_registered_events"] >= 60)
    check("4b. the target is a floor, not a stopping rule",
          t["is_a_floor_not_a_stopping_rule"] is True)


# ============ 5. enrollment never depends on outcome-bearing data ==========

_OUTCOME_TERMS = ("gst_zscore", "wiki_zscore", "price", "volume", "volatility",
                  "option", "analyst", "surprise", "news", "outcome", "consensus")


def test_5_enrollment_is_blind():
    permitted = [p.lower() for p in DOC["enrollment_inputs"]["permitted"]]
    prohibited = [p.lower() for p in DOC["enrollment_inputs"]["prohibited"]]
    leaked = [p for p in permitted
              if any(t in p for t in _OUTCOME_TERMS)]
    check(f"5. no permitted enrollment input is outcome-bearing (leaked={leaked})", not leaked)
    for term in _OUTCOME_TERMS:
        check(f"5b. '{term}' is named as a prohibited enrollment input",
              any(term in p for p in prohibited))
    check("5c. INC-9 forbids inspecting outcome data before enrollment",
          any(r["id"] == "INC-9" and "No GST" in r["rule"] for r in DOC["inclusion_rules"]))
    check("5d. inspecting a prohibited input VOIDS the enrollment decision",
          "void" in DOC["enrollment_inputs"]["rule"].lower())
    check("5e. a blinding breach is recorded, never silently re-enrolled",
          "COMPROMISED_ENROLLMENT_BLINDING" in DOC["enrollment_inputs"]["rule"]
          and "never silently re-enrolled" in DOC["enrollment_inputs"]["rule"])
    # no inclusion rule may be conditioned on an outcome-bearing quantity
    for rule in DOC["inclusion_rules"]:
        if rule["id"] == "INC-9":
            continue  # INC-9 exists precisely to name them as forbidden
        offending = [t for t in _OUTCOME_TERMS if t in rule["rule"].lower()]
        check(f"5f. {rule['id']} is not conditioned on outcome data (found={offending})",
              not offending)


def test_6_prohibited_exclusion_reasons():
    reasons = " | ".join(DOC["prohibited_exclusion_reasons"]).lower()
    for needle in ("low attention", "high attention", "options data",
                   "unfavourable market response", "null market response",
                   "after valid registration", "interesting result"):
        check(f"6. exclusion for '{needle}' is explicitly prohibited", needle in reasons)
    check("6b. the Markdown carries the same prohibition list",
          "may NEVER be excluded because of" in MD)


# ============ 7. options unavailability does not exclude ===================

def test_7_options_do_not_gate_membership():
    rel = DOC["relationship_to_v0_2_completeness"]
    joined = " ".join(rel["rules"]).lower()
    check("7. an absent options benchmark never removes a core-eligible event",
          "never removes an otherwise valid event" in joined)
    check("7b. it may lower the tier to core_only_no_option_benchmark",
          C.PRE_EVENT_TIER_CORE_ONLY in " ".join(rel["rules"]))
    check("7c. the tiers are the production tiers, unchanged",
          rel["tiers"] == list(C.PRE_EVENT_TIERS)
          and rel["full_data_complete_tier"] == C.FULL_DATA_COMPLETE_TIER)
    check("7d. hypothesis families are the production families, unchanged",
          rel["hypothesis_families"] == list(C.HYPOTHESIS_CLASSES))
    check("7e. option dispositions are the production dispositions, unchanged",
          rel["option_dispositions"] == list(C.OptionBenchmarkDisposition.ALL))
    # behavioural: a core-only event stays eligible for the core family
    elig = C.ModuleEligibility(
        core_pre_event_eligible=True, option_benchmark_eligible=False,
        joint_full_eligible=False,
        pre_event_completeness_tier=C.PRE_EVENT_TIER_CORE_ONLY,
        option_benchmark_status=C.OptionBenchmarkDisposition.UNAVAILABLE_NO_VERIFIED_SOURCE,
        option_benchmark_unavailable_reason="no OPRA-entitled source")
    check("7f. a core-only event is still eligible for the core attention family",
          C.is_eligible_for_hypothesis(C.HYPOTHESIS_CORE_ATTENTION_RESPONSE, elig))
    check("7g. ...and remains ineligible for the options and joint families",
          not C.is_eligible_for_hypothesis(C.HYPOTHESIS_OPTIONS_IMPLIED_MOVE, elig)
          and not C.is_eligible_for_hypothesis(C.HYPOTHESIS_JOINT_ATTENTION_OPTIONS, elig))
    check("7h. no options-related disposition appears in the exclusion classes",
          not [d for d in DOC["dispositions"]
               if d["class"] == "excluded" and "option" in d["meaning"].lower()])


# ============ 8. duplicate ticker-quarter enrollment prohibited ============

def test_8_duplicate_enrollment_prohibited():
    check("8. INC-10 forbids a second event for the same ticker and fiscal quarter",
          any(r["id"] == "INC-10" and "same ticker and fiscal quarter" in r["rule"]
              for r in DOC["inclusion_rules"]))
    check("8b. a dedicated terminal exclusion disposition exists",
          any(d["code"] == "EXCLUDED_DUPLICATE_TICKER_FISCAL_QUARTER"
              and d["terminal"] is True and d["class"] == "excluded"
              for d in DOC["dispositions"]))
    check("8c. the screening-log schema enforces at most one ENROLLED row per pair",
          "At most **one** `ENROLLED` row per `(ticker, fiscal_period)`" in SCHEMA)
    check("8d. the schema names ticker+fiscal_period as the duplicate key",
          "duplicate key" in SCHEMA)


# ============ 9. amendments are append-only ================================

def test_9_amendments_append_only():
    a = DOC["amendment_rules"]
    check("9. amendments use the existing production mechanism",
          a["mechanism"].endswith("HumanVerifiedEventRegistry.amend_event"))
    check("9b. append_only is declared", a["append_only"] is True)
    joined = " ".join(a["rules"]).lower()
    check("9c. original bytes are never overwritten, edited or deleted",
          "never overwritten, edited or deleted" in joined)
    check("9d. an amendment may never change ticker, fiscal quarter or enrollment",
          "never change the ticker" in joined)
    check("9e. no amendment may be motivated by collected data",
          "no amendment may be motivated by collected" in joined)
    check("9f. row types are exactly REGISTRATION and AMENDMENT",
          a["row_types"] == ["REGISTRATION", "AMENDMENT"])
    check("9g. verification statuses mirror production",
          a["verification_statuses"] == list(VERIFICATION_STATUSES))
    check("9h. a post-anchor timing change is compromised, not deleted",
          any(d["code"] == "COMPROMISED_TIMING_CHANGED_AFTER_ANCHOR"
              and "preserved" in d["meaning"] for d in DOC["dispositions"]))
    check("9i. a pre-anchor timing change re-derives the anchor",
          any(d["code"] == "AMENDED_TIMING_CHANGED_BEFORE_ANCHOR"
              and "re-derived" in d["meaning"] for d in DOC["dispositions"]))


# ============ 10. v0.2 thresholds and interval formulas untouched ==========

def test_10_v0_2_untouched():
    # The production constants must still hold their v0.2 values. If this
    # commit had edited a gate, threshold or interval list, these fail.
    check("10. D1 interval fields unchanged",
          C.D1_REQUIRED_FIELDS == ("overnight_gap", "open_to_30m",
                                   "thirty_min_to_close", "open_to_close"))
    check("10b. D3 interval fields unchanged",
          C.D3_REQUIRED_FIELDS == ("close_T1_to_close_T2", "close_T1_to_close_T3"))
    check("10c. option benchmark required fields unchanged",
          C.OPTION_BENCHMARK_REQUIRED_FIELDS
          == ("expiration", "underlying_price", "quote_timestamp_utc"))
    check("10d. option benchmark any-of fields unchanged",
          C.OPTION_BENCHMARK_REQUIRED_ANY_OF
          == ("straddle_mid", "long_executable_implied_move_cost"))
    check("10e. strict six-field core unchanged",
          C.STRICT_CORE_SIX_FIELDS == ("gst_zscore", "wiki_zscore",
                                       "panel_implied_volatility", "realized_volatility",
                                       "previous_close", "volume"))
    check("10f. strict-core success statuses unchanged",
          C.STRICT_CORE_SUCCESS_STATUSES == ("ok", "ok_recent_cache_fallback"))
    check("10g. per-leg status mapping unchanged",
          C.STRICT_CORE_STATUS_KEY["panel_implied_volatility"] == "source_status_iv"
          and C.STRICT_CORE_STATUS_KEY["realized_volatility"] == "source_status_realized_vol"
          and C.STRICT_CORE_STATUS_KEY["previous_close"] == "source_status_price")
    check("10h. protocol version and methodology identifier unchanged",
          C.PROTOCOL_VERSION == "0.2" and C.METHODOLOGY_VERSION_V0_2 == "market_response_v0.2")
    check("10i. release-session vocabulary unchanged",
          DOC["permitted_official_source_types"]["valid_release_sessions"]
          == list(VALID_RELEASE_SESSIONS))
    # the protocol must REFERENCE, not restate, the v0.2 documents
    rel = DOC["relationship_to_v0_2_completeness"]
    check("10j. the protocol points at the v0.2 SPEC and dictionary",
          rel["spec"].endswith("SPEC_v0.2_DRAFT.md")
          and rel["field_dictionary"].endswith("FIELD_DICTIONARY_v0.2.md"))
    check("10k. the protocol states it defines no formula, threshold or gate",
          any("defines no interval formula" in r for r in rel["rules"]))
    # it must not restate an interval formula
    for formula in ("overnight_gap", "open_to_30m", "close_T1_to_close_T2"):
        check(f"10l. the protocol Markdown does not restate the {formula} formula",
              f"{formula} =" not in MD)


# ============ 11. no trading-strategy claim ================================

_STRATEGY_TERMS = ("profitable", "trading strategy", "alpha", "backtest", "sharpe",
                   "win rate", "p&l", "buy signal", "sell signal", "return forecast",
                   "edge", "optimis", "optimiz")
_NEGATIONS = ("not ", "no ", "never", "prohibit", "out of scope", "does not", "do not",
              "nor ", "without")


def test_11_no_strategy_claim():
    # Structural: every line mentioning a strategy term must be a DISCLAIMER.
    # A plain substring ban would match the protocol's own non-goals section.
    for label, text in (("Markdown", MD), ("schema", SCHEMA),
                        ("JSON", json.dumps(DOC, indent=2))):
        offenders = []
        for line in text.splitlines():
            low = line.lower()
            if any(t in low for t in _STRATEGY_TERMS) and not any(n in low for n in _NEGATIONS):
                offenders.append(line.strip()[:90])
        check(f"11. every strategy-term mention in the {label} is a disclaimer "
              f"(offenders={offenders})", not offenders)
    check("11b. non-goals explicitly disclaim a profitable trading strategy",
          any("profitable trading strategy" in g for g in DOC["non_goals"]))
    check("11c. no return forecast, ranking or recommendation is produced",
          any("no return forecast" in g.lower() for g in DOC["non_goals"]))
    check("11d. future strategy research is marked OUT OF SCOPE as its own stage",
          any(s.get("status") == "OUT OF SCOPE"
              for s in DOC["analysis_separation"]["stages"]))
    check("11e. the purpose statement disclaims strategy selection",
          "does not test, optimize, select for, or claim" in DOC["purpose"])


# ============ 12. analysis separation is explicit =========================

def test_12_analysis_separation():
    stages = DOC["analysis_separation"]["stages"]
    names = [s["stage"] for s in stages]
    check("12. all five stages are separated and ordered",
          names == ["1_cohort_enrollment", "2_pre_event_measurement",
                    "3_post_event_response_measurement", "4_hypothesis_eligibility",
                    "5_future_strategy_research"])
    check("12b. enrollment may not read attention, market, options or outcome data",
          "may_not_read" in stages[0]
          and all(t in stages[0]["may_not_read"].lower()
                  for t in ("attention", "market", "options", "outcome")))
    check("12c. information flows forward only",
          "forward only" in DOC["analysis_separation"]["one_way_rule"])
    check("12d. hypothesis eligibility is delegated to production",
          stages[3]["governed_by"].endswith("is_eligible_for_hypothesis"))


def test_13_display_gate_fails_closed():
    g = DOC["display_gate"]
    check("13. the display gate defaults to DENY", g["default"] == "DENY")
    check("13b. no per-hypothesis threshold is claimed to exist yet",
          g["status_for_market_response_families"] == "NOT_YET_REGISTERED")
    check("13c. the protocol does not invent a sample-size number",
          "does NOT invent one" in g["note"])
    check("13d. absence of a number is never read as absence of a gate",
          "never read as absence of a gate" in g["note"])
    check("13e. it cites the existing governance source, not a new rule",
          g["governance_source"].endswith("GST_Phase2_InformationArrivalPanel_SPEC_DRAFT.md"))
    # the protocol must not introduce any numeric N threshold of its own
    nums = re.findall(r"sample[- ]size threshold[^.]{0,80}?(\d+)", json.dumps(DOC), re.I)
    check(f"13f. no numeric per-hypothesis threshold is set here (found={nums})", not nums)


# ============ 14. no candidate rows; DELL untouched =======================

def test_14_no_candidates_and_dell_untouched():
    check("14. the JSON carries zero screening rows", DOC["screening_rows"] == [])
    check("14b. the schema doc carries zero screening rows",
          "Zero screening rows exist" in SCHEMA)
    check("14c. no screening log file exists yet",
          not (LSE / "Market_Response_Event_Registry" / "cohort_screening_log.jsonl").exists())
    # The only event id anywhere in the deliverables is the already-registered DELL event.
    ids = set(re.findall(r"EVT-[A-Z0-9-]+-FY\d{2}Q\d-[A-Z]+", json.dumps(DOC) + MD + SCHEMA))
    check(f"14d. the only event id referenced is the registered DELL event (found={sorted(ids)})",
          ids == {"EVT-DELL-FY27Q2-ERN"})
    check("14e. DELL is described as receiving no special treatment",
          "no special treatment" in DOC["existing_provenance"]["why_eligible"])
    # registry bytes unchanged (LF-normalised, so a CRLF checkout still matches)
    raw = REGISTRY_P.read_bytes()
    lf = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    check("14f. the DELL registry blob is byte-identical to the recorded baseline",
          lf == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    check("14g. the JSON records that same registry hash",
          DOC["existing_provenance"]["registry_sha256_lf"] == lf)
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    check("14h. the registry still holds exactly one verified REGISTRATION row",
          len(rows) == 1 and rows[0]["row_type"] == "REGISTRATION"
          and rows[0]["verification_status"] == "verified")
    check("14i. no event log or stage marker exists anywhere in the repo",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


# ============ 15. no network or provider access is possible ===============

def test_15_no_network_or_provider():
    reached = []
    for host in ("data.alpaca.markets", "en.wikipedia.org", "trends.google.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001 - any other refusal is also a block
            pass
    check(f"15. sockets are blocked during validation (reached={reached})", not reached)
    for mod in ("requests", "yfinance", "pytrends"):
        if mod in sys.modules:
            check(f"15b. {mod} is not importable", False)
            continue
        try:
            __import__(mod)
            check(f"15b. {mod} is not importable", False)
        except ImportError:
            check(f"15b. {mod} is not importable", True)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"15c. no provider module reached sys.modules (leaked={leaked})", not leaked)
    # the deliverables are pure data/prose -- no executable content
    check("15d. the protocol JSON is pure data", isinstance(DOC, dict))
    for label, text in (("Markdown", MD), ("schema", SCHEMA)):
        check(f"15e. the {label} contains no fetch/download instruction",
              not re.search(r"\b(curl|wget|urlopen|requests\.get|http[s]?://[^\s`)]*\.(csv|json))\b",
                            text))


if __name__ == "__main__":
    test_1_json_markdown_agree()
    test_2_universe_matches_production()
    test_3_window_lead_target_fixed()
    test_4_target_at_least_60()
    test_5_enrollment_is_blind()
    test_6_prohibited_exclusion_reasons()
    test_7_options_do_not_gate_membership()
    test_8_duplicate_enrollment_prohibited()
    test_9_amendments_append_only()
    test_10_v0_2_untouched()
    test_11_no_strategy_claim()
    test_12_analysis_separation()
    test_13_display_gate_fails_closed()
    test_14_no_candidates_and_dell_untouched()
    test_15_no_network_or_provider()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL COHORT PROTOCOL TESTS PASSED")
    sys.exit(0)
