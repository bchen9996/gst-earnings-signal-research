#!/usr/bin/env python3
"""Focused deterministic test for the Semiconductor EPS-Price Absorption extraction phase.

Verifies GAAP diluted-EPS table selection, quarter-column selection, later-XBRL audit
isolation, event uniqueness, the frozen reaction/entry timing rules, the SUE history
cutoff, training-only transformations, and metric/gate recomputation. Offline.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
OUT = ROOT / "Live Signal Engine" / "Semiconductor_EPS_Absorption"
V = json.loads((OUT / "extraction_validation_v1.0.json").read_text(encoding="utf-8"))
R = json.loads((ROOT / "SEMICONDUCTOR_EPS_ABSORPTION_RESULTS_v1.0.json").read_text(encoding="utf-8"))
PROV = json.loads((OUT / "provenance_v1.0.json").read_text(encoding="utf-8"))
P = pd.read_csv(OUT / "event_panel_v1.0.csv")
TOOL = (ROOT / "tools" / "run_semiconductor_eps_absorption.py").read_text(encoding="utf-8")
REPORT = (ROOT / "SEMICONDUCTOR_EPS_ABSORPTION_REPORT_v1.0.md").read_text(encoding="utf-8")
FLAT = " ".join(REPORT.split())
UNIVERSE = ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "TXN", "AMAT", "LRCX", "KLAC"]
FAIL: list[str] = []


def ck(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


# ---- 1. scope and frozen design ----
ck("1a. exploratory status", V["status"] == R["status"] == "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY")
ck("1b. sector recorded", V["sector"] == R["sector"] == "SEMICONDUCTORS")
ck("1c. google_trends_used is false", V["google_trends_used"] is False and R["google_trends_used"] is False)
ck("1d. analyst_consensus_used is false",
   V["analyst_consensus_used"] is False and R["analyst_consensus_used"] is False)
ck("1e. later_xbrl_used_for_prediction is false",
   V["later_xbrl_used_for_prediction"] is False and R["later_xbrl_used_for_prediction"] is False)
ck("1g. FROZEN_DESIGN block present and closed",
   "FROZEN_DESIGN ===" in TOOL and "END FROZEN_DESIGN" in TOOL)
ck("1h. frozen universe in the frozen order", V["universe"] == UNIVERSE == R["universe"])
ck("1i. SMH is primary and SPY is sensitivity only",
   V["benchmark"] == "SMH" and R["benchmark_primary"] == "SMH"
   and R["benchmark_sensitivity_only"] == "SPY")

# ---- 2. GAAP diluted-EPS table selection ----
ck("2a. income-statement acceptance requires revenue, net income and a per-share row",
   "no_revenue_row" in TOOL and "no_net_income_row" in TOOL and "no_per_share_row" in TOOL)
ck("2b. reconciliation / non-GAAP / segment / guidance tables rejected by context",
   "NON_GAAP_CTX" in TOOL and "reconcil" in TOOL and "guidance" in TOOL and "segment" in TOOL)
ck("2c. adjusted and non-GAAP rows rejected", "ADJ_ROW" in TOOL and "non[- ]?gaap" in TOOL)
ck("2d. share-count rows rejected so EPS cannot be a weighted-average share figure",
   "SHARES_ROW" in TOOL and "weighted[- ]average" in TOOL)
ck("2e. basic EPS is never matched as diluted",
   "DILUTED_FULL" in TOOL and "DILUTED_BARE" in TOOL and "dilut" in TOOL)
ck("2f. bare 'Diluted' only accepted inside a per-share section",
   "in_pershare, sec = False, None" in TOOL
   and "bare = bool(DILUTED_BARE.match(label)) and in_pershare" in TOOL)
ck("2m. nested net-income-per-share rows require the diluted section qualifier",
   'sec == "diluted" and bool(NET_PER_SHARE.match(label))' in TOOL)
ck("2n. a reported quarter may not end after the release that reports it",
   "not_after is not None and d > not_after" in TOOL)
ck("2g. continuing-operations EPS deferred to consolidated when both present",
   "plain = [h for h in hits if not h[\"continuing_ops\"]]" in TOOL
   and "consolidated preferred over continuing-ops" in TOOL)
ck("2h. ambiguous multiple matches are refused, not guessed",
   "ambiguous_multiple_match" in TOOL and "REFUSE rather than guess" in TOOL)
ck("2i. disagreement across sibling exhibits is refused", "ambiguous_across_exhibits" in TOOL)

# ---- 3. quarter-column selection ----
ck("3a. YTD / six / nine / twelve-month columns rejected",
   "YTD = re.compile" in TOOL and "six" in TOOL and "nine" in TOOL and "twelve" in TOOL)
ck("3b. only three-month / quarter spans are candidates", "QTR_SPAN" in TOOL)
ck("3c. the latest-dated surviving quarter column is chosen",
   "max(cands, key=lambda x: (x[2], -x[0]))" in TOOL)
ck("3d. year-only header rows stay in the header", "_is_year_row" in TOOL
   and "1990 <= x <= 2100" in TOOL)
ck("3e. colspan is expanded so spanning headings map to columns",
   "colspan expansion" in TOOL and 'a.get("colspan"' in TOOL)
ck("3f. every provenance row carries the selected table, row and column",
   all(k in PROV[0] for k in ("table_index", "row_index", "row_label", "column_label")))

# ---- 4. later-XBRL audit isolation ----
ck("4a. reference documented as audit-only", "audit reference only" in V["later_xbrl_role"]
   and "never entered a model feature" in V["later_xbrl_role"])
ck("4b. primary concept is EarningsPerShareDiluted",
   R["extraction_audit"]["xbrl_concept_used"] == "us-gaap:EarningsPerShareDiluted")
ck("4f. reference must be filed after the release",
   "def after_release(v):" in TOOL and "f > acc.normalize()" in TOOL)
ck("4g. reference must match the same fiscal quarter",
   'abs((pd.Timestamp(k) - fpe).days) <= 5' in TOOL)
ck("4h. tolerance is $0.01 absolute", V["tolerance_eps_absolute"] == 0.01
   and R["extraction_audit"]["tolerance_eps_absolute"] == 0.01)
ck("4i. zero later-XBRL values entered prediction",
   V["gates"]["later_xbrl_predictive_inputs"]["value"] == 0
   and R["gates"]["later_xbrl_predictive_inputs"]["value"] == 0)
ck("4j. no predictive stage ran that could have consumed the reference",
   all(v == "not run" for k, v in R["not_run_because_gate_failed"].items()
       if isinstance(v, str) and k != "frozen_design_outcome_commit"))

# ---- 5. event uniqueness ----
ck("5a. duplicate identities are refused, never first-kept",
   'keep=False' in TOOL and "REFUSED outright, never first-kept" in TOOL)
ck("5b. refusal count recorded", V["duplicate_identities_refused"] == R["coverage"]["duplicate_identities_refused"])
E = P[P.eps.notna() & P.fiscal_period_end.notna()]
ck("5c. no duplicate (ticker, fiscal_period_end, accession) among extracted events",
   len(E.drop_duplicates(subset=["ticker", "fiscal_period_end", "accession"])) == len(E))

# ---- 6. reaction and entry timing (frozen rules, not yet executed) ----
ck("6a. before-09:30 rule frozen", "< 09:30 ET on a trading day  -> that day" in TOOL)
ck("6b. intraday and after-16:00 both roll to the next trading day",
   "during market hours          -> next trading day" in TOOL
   and ">= 16:00 ET                  -> next trading day" in TOOL)
ck("6d. features only after the reaction session closes",
   "Features become available only AFTER the reaction session closes" in TOOL)
ck("6e. entry is the following session's open", "entry   = following trading day's OPEN" in TOOL)
ck("6f. primary exit is the 5th close, secondary the 20th",
   "exit-1  = 5th trading day's CLOSE after entry" in TOOL
   and "exit-2  = 20th trading day's CLOSE after entry" in TOOL)

# ---- 7. SUE history cutoff ----
ck("7a. SUE uses Exhibit-extracted EPS only", "Exhibit-extracted GAAP diluted EPS ONLY" in TOOL)
ck("7b. denominator uses only differences from releases before the event",
   "BEFORE the current event" in TOOL)
ck("7c. at least 4 and at most 8 prior seasonal differences",
   "SUE_MIN_HIST, SUE_MAX_HIST = 4, 8" in TOOL)
ck("7d. the usable-event filter enforces the minimum history",
   "if len(prior) >= SUE_MIN_HIST" in TOOL)
ck("7f. SUE is named a seasonal historical-expectation surprise, not a consensus miss",
   "SEASONAL HISTORICAL-EXPECTATION surprise" in TOOL
   and "NOT an analyst surprise" in TOOL)

# ---- 8. training-only transformations (frozen, not yet executed) ----
ck("8a. SUE winsorized at training-fold percentiles only",
   "TRAINING-FOLD\n              1st/99th percentiles only" in TOOL
   or "Winsorized at the TRAINING-FOLD" in TOOL)
ck("8b. gap standardized within each outer training fold only",
   "standardized WITHIN EACH OUTER TRAINING FOLD ONLY" in TOOL)
ck("8c. alpha chosen by inner chronological validation",
   "INNER CHRONOLOGICAL validation" in TOOL and "never the outer test fold" in TOOL)
ck("8d. alpha grid is the frozen one", "ALPHAS = [0.1, 1.0, 10.0, 100.0]" in TOOL)
ck("8e. folds are chronological and fixed",
   "FOLDS = [(2022, 2023), (2023, 2024), (2024, 2025)]" in TOOL and "Never a random split" in TOOL)

# ---- 9. metric and gate recomputation ----
g, rg = V["gates"], R["gates"]
ck("9a. extracted count recomputes from the panel",
   V["extracted"] == int(P.eps.notna().sum()) == R["coverage"]["extracted_gaap_diluted_eps"])
ck("9c. validated + contradicted + no_reference + refused duplicates equals extracted",
   V["validated"] + V["contradicted"] + V["no_reference"]
   + V["duplicate_identities_refused"] == V["extracted"])
ck("9d. reference_coverage recomputes",
   abs(g["reference_coverage"]["value"]
       - (V["validated"] + V["contradicted"]) / V["extracted"]) < 1e-4)
ck("9e. conditional_precision recomputes",
   abs(g["conditional_precision"]["value"]
       - V["validated"] / (V["validated"] + V["contradicted"])) < 1e-4)
ck("9f. usable_event_coverage recomputes",
   abs(g["usable_event_coverage"]["value"] - V["usable_events"] / V["located_exhibits"]) < 1e-4)
ck("9g. panel usable-event flag matches the usable count",
   int(P.usable_event.sum()) == V["usable_events"])
ck("9h. gate thresholds are the frozen ones",
   g["reference_coverage"]["required"] == 0.80 and g["conditional_precision"]["required"] == 0.95
   and g["usable_event_coverage"]["required"] == 0.60 and g["tickers"]["required"] == 8
   and g["usable_events"]["required"] == 160 and g["oos_events"]["required"] == 90
   and g["oos_per_year"]["required"] == 25)
ck("9i. results and validation artifacts agree on every gate value",
   all(abs(float(rg[k]["value"]) - float(g[k]["value"])) < 1e-4
       for k in ("reference_coverage", "conditional_precision", "usable_event_coverage")))
ck("9j. conditional precision passes while coverage gates fail",
   g["conditional_precision"]["passed"] is True and g["reference_coverage"]["passed"] is False
   and g["usable_event_coverage"]["passed"] is False)
ck("9k. overall extraction gate failed",
   V["extraction_gate_passed"] is False and rg["overall_passed"] is False)
ck("9l. OOS-per-year values agree and every year is short of the floor",
   rg["oos_per_year"]["value"] == g["oos_per_year"]["value"]
   and all(v < 25 for v in g["oos_per_year"]["value"].values()))

# ---- 10. dev sample, spot audit and labels ----
ck("10a. dev sample is 2 per ticker under the frozen seed",
   V["dev_sample"]["per_ticker"] == 2 and V["dev_sample"]["seed"] == "SEMICONDUCTOR_EPS_PARSER_DEV")
ck("10b. dev rule makes no reference to returns", "no reference to returns" in V["dev_sample"]["rule"])
ck("10c. dev sample size and ticker count agree across artifacts",
   V["dev_sample"]["n"] == R["dev_sample"]["n"] and V["dev_sample"]["tickers"] == R["dev_sample"]["tickers"])
ck("10e. spot audit covers every dev-sample event",
   len(V["structural_spot_audit"]) == V["dev_sample"]["n"])
ck("10f. spot audit records statement, row, column, value and reference",
   all(k in V["structural_spot_audit"][0] for k in
       ("selected_statement_table_index", "selected_row_index", "selected_row_label",
        "selected_column_label", "parsed_value", "later_xbrl_reference", "audit_status")))
ck("10g. spot audit is not described as independent human review",
   "NOT an independent human review" in V["structural_spot_audit_note"]
   and "NOT an independent human review" in R["dev_sample"]["spot_audit_note"])
ALLOWED = {"EXTRACTION_NOT_RELIABLE", "DATA_UNAVAILABLE", "NO_SEMICONDUCTOR_EPS_ABSORPTION_EDGE",
           "PREDICTIVE_NOT_TRADABLE", "SEMICONDUCTOR_EPS_ABSORPTION_SIGNAL"}
ck("10i. decision label is one of the five allowed", R["decision_label"] in ALLOWED)
ck("10j. label matches a failed extraction gate", R["decision_label"] == "EXTRACTION_NOT_RELIABLE")
ck("10k. discipline flags recorded", R["discipline"]["gates_loosened_after_seeing_rates"] is False
   and R["discipline"]["values_hand_corrected"] is False
   and R["discipline"]["returns_used_to_choose_a_parsing_rule"] is False)
ck("10l. no post-entry return was inspected",
   R["not_run_because_gate_failed"]["post_entry_returns_inspected"] is False)
ck("10m. report states the binding constraint is the coverage ceiling, not precision",
   "arithmetically unreachable" in FLAT and "0.7824" in FLAT)
ck("10o. report avoids the prohibited interpretations",
   "Nothing here is called an analyst surprise" in FLAT)

# ---- 11. filer adapter registry discipline ----
sys.path.insert(0, str(ROOT / "tools"))
from run_semiconductor_eps_absorption import (  # noqa: E402
    FILER_ADAPTERS, ADAPTER_ALLOWED_TICKERS, ADAPTER_ALLOWED_FIELDS)
ck("11a. adapters only for the six approved tickers",
   set(FILER_ADAPTERS) <= ADAPTER_ALLOWED_TICKERS
   and set(FILER_ADAPTERS) <= set(UNIVERSE))
ck("11b. adapters contain only approved structural fields",
   all(set(v) <= ADAPTER_ALLOWED_FIELDS for v in FILER_ADAPTERS.values()))
ck("11c. no adapter contains an accession number",
   not re.search(r"\d{10}-\d{2}-\d{6}", json.dumps(FILER_ADAPTERS)))
ck("11d. no adapter contains a numeric literal that could be an EPS or column index",
   not re.search(r":\s*-?\d+\.\d+", json.dumps(FILER_ADAPTERS)))
ck("11e. the four already-working filers have no adapter",
   not ({"AMD", "AMAT", "LRCX", "KLAC"} & set(FILER_ADAPTERS)))
ck("11f. parser source contains no accession-specific exception",
   not re.search(r"accession\s*==\s*[\"']", TOOL))
ck("11g. parser source hardcodes no EPS or target-return table",
   "EXPECTED_EPS" not in TOOL and "KNOWN_EPS" not in TOOL and "EPS_OVERRIDE" not in TOOL)
ck("11h. adapters are keyed by ticker only",
   all(isinstance(k, str) and k.isupper() and len(k) <= 5 for k in FILER_ADAPTERS))

# ---- 12. development / held-out separation ----
SP = V["precision_split"]
ck("12a. both splits are reported", set(SP) == {"development", "held_out"})
ck("12b. dev-sample flag partitions the audit rows",
   SP["development"]["validated"] + SP["held_out"]["validated"] == V["validated"]
   and SP["development"]["contradicted"] + SP["held_out"]["contradicted"] == V["contradicted"])
ck("12c. held-out conditional precision recomputes",
   abs(SP["held_out"]["conditional_precision"]
       - SP["held_out"]["validated"] / (SP["held_out"]["validated"]
                                        + SP["held_out"]["contradicted"])) < 1e-4)
ck("12d. held-out conditional precision independently clears 0.95",
   V["gates"]["heldout_conditional_precision"]["value"] >= 0.95
   and V["gates"]["heldout_conditional_precision"]["passed"] is True)
ck("12e. dev sample size is unchanged from the frozen rule",
   V["dev_sample"]["per_ticker"] == 2 and V["dev_sample"]["seed"] == "SEMICONDUCTOR_EPS_PARSER_DEV")
ck("12f. results record that no held-out filing entered the dev set",
   R["discipline"]["held_out_filing_moved_into_dev_set"] is False)
ck("12g. results and validation agree on the split", R["precision_split"] == SP)

# ---- 13. gates unchanged and second-attempt accounting ----
ck("13a. gate thresholds are identical to the first attempt",
   R["gates_unchanged_from_first_attempt"] is True
   and V["gates"]["reference_coverage"]["required"] == 0.80
   and V["gates"]["usable_event_coverage"]["required"] == 0.60
   and V["gates"]["tickers"]["required"] == 8)
ck("13b. tolerance unchanged", V["tolerance_eps_absolute"] == 0.01
   and R["discipline"]["tolerance_loosened"] is False)
ck("13c. before/after counts recompute against the current run",
   R["before_after"]["extracted"]["after"] == V["extracted"]
   and R["before_after"]["validated"]["after"] == V["validated"]
   and R["before_after"]["located_earnings_exhibits"]["after"] == V["located_exhibits"])
ck("13d. the first attempt's failed result is preserved",
   R["attempts"]["first_attempt_commit"].startswith("cafc50a")
   and R["attempts"]["first_attempt_label"] == "EXTRACTION_NOT_RELIABLE")
ck("13e. extraction improved but the gate still failed",
   V["extracted"] > R["before_after"]["extracted"]["before"]
   and V["extraction_gate_passed"] is False)
ck("13f. per-ticker after-counts recompute",
   R["extracted_by_ticker"]["after"] == V["extracted_by_ticker"])

# ---- 14. the reference-coverage ceiling ----
BF = R["binding_finding"]
ck("14a. ceiling recomputes from the recorded counts",
   abs(BF["max_attainable_reference_coverage"]
       - (V["extracted"] - BF["fy_end_quarter_events"]) / V["extracted"]) < 1e-3)
ck("14b. the ceiling is below the required threshold",
   BF["max_attainable_reference_coverage"] < BF["required_reference_coverage"]
   and BF["reachable"] is False)
ck("14c. missing references concentrate in the fiscal-year-end quarter",
   BF["no_reference_among_them"] > BF["no_reference_among_other_events"])

# ---- 15. no target-return access before a frozen-design commit ----
ck("15a. no outcome stage ran", R["not_run_because_gate_failed"]["post_entry_returns_inspected"] is False
   and R["attempts"]["outcome_stage_ever_run"] is False)
ck("15b. no pre-outcome frozen-design commit was created",
   R["not_run_because_gate_failed"]["frozen_design_outcome_commit"] == "not created")
ck("15c. the runner refuses to reach phase 2 while the gate fails",
   "phase 2 runs only after the extraction gate passes" in TOOL)
ck("15d. no price series is fetched anywhere in the executed path",
   TOOL.count("def daily(") == 1 and "attach_prices" not in TOOL)
ck("15e. previously extracted values were not altered",
   R["unchanged_ticker_value_stability"]["values_changed"] == 0)
ck("15f. recommendation is to stop hand-building the parser",
   "Stop hand-building this parser" in FLAT
   and "no further hand-built parser iteration" in R["recommendation"].lower())
ck("15g. report states reliable structured data would be required",
   "reliable structured earnings data" in FLAT)

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL SEMICONDUCTOR EPS ABSORPTION CHECKS PASSED")
sys.exit(0)
