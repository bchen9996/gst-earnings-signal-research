#!/usr/bin/env python3
# Deterministic validation of the round-1 official-source reconnaissance sweep.
#
# Validates the PRESERVED sweep evidence. Performs no retrieval, opens no
# socket, screens no candidate, writes no registry or screening row.
#
# Run directly: python test_market_response_cohort_sweep_round1.py

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during sweep validation")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

_BANNED_TOP = {"yfinance", "pytrends", "requests", "urllib3", "httpx", "aiohttp"}


class _BanProviders:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _BANNED_TOP:
            raise ImportError("BLOCKED provider import: " + fullname)
        return None


sys.meta_path.insert(0, _BanProviders())

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE  # noqa: E402

SWEEP_DIR = HERE / "Live Signal Engine" / "Cohort_Screening_Round1"
MANIFEST = json.loads((SWEEP_DIR / "SWEEP_MANIFEST_ROUND1.json").read_text(encoding="utf-8"))
QUEUE = json.loads((SWEEP_DIR / "HUMAN_REVIEW_REQUIRED_ROUND1.json").read_text(encoding="utf-8"))
LSE = HERE / "Live Signal Engine"
REGISTRY_P = LSE / "Market_Response_Event_Registry" / "registry.jsonl"
ROWS = MANIFEST["rows"]

# Hosts that are the issuer's own domain or the SEC. Anything else is a
# third party and may not appear as evidence.
ISSUER_OR_SEC = re.compile(
    r"(^|\.)(sec\.gov|apple\.com|abbvie\.com|adobe\.com|aboutamazon\.com|bakerhughes\.com"
    r"|berkshirehathaway\.com|cognizant\.com|delltechnologies\.com|devonenergy\.com"
    r"|gamestop\.com|abc\.xyz|globalpayments\.com|intc\.com|leidos\.com|microsoft\.com"
    r"|nclhltd\.com|nike\.com|qualcomm\.com|starbucks\.com|cbrands\.com|stryker\.com"
    r"|tesla\.com|take2games\.com|united\.com)$", re.I)

THIRD_PARTY = re.compile(
    r"ycharts|zacks|nasdaq\.com|finance\.yahoo|marketwatch|seekingalpha|investing\.com"
    r"|benzinga|barchart|stocktwits|tipranks|fool\.com|google\.com/search|bing\.com", re.I)

PROHIBITED_FIELD = re.compile(
    r"gst_zscore|wiki_zscore|\bprice\b|previous_close|\bvolume\b|volatility|implied_vol"
    r"|straddle|option_|surprise|analyst|news_tone|return|pnl|sharpe", re.I)

FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    if cond:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        FAILURES.append(label)


# ===== 1-2. exactly the locked 24, no duplicates ===========================

def test_1_2_universe():
    tickers = [r["ticker"] for r in ROWS]
    check("1. the sweep contains exactly the locked 24 tickers",
          sorted(tickers) == sorted(LOCKED_24_TICKER_UNIVERSE))
    check("1b. in the production universe order", tickers == list(LOCKED_24_TICKER_UNIVERSE))
    check("2. no ticker is duplicated", len(tickers) == len(set(tickers)) == 24)
    check("2b. the manifest declares the production universe as its source",
          MANIFEST["scope"]["universe_source"]
          == "gst_market_response.constants.LOCKED_24_TICKER_UNIVERSE")
    check("2c. every ticker appears even when nothing was found or the page failed",
          all(r.get("checked_sources") for r in ROWS))


# ===== 3, 5. issuer/SEC URLs only; no third party =========================

def test_3_5_sources():
    bad_host, third = [], []
    for r in ROWS:
        for c in r["checked_sources"]:
            host = urlparse(c["url"]).netloc.lower().split(":")[0]
            if not ISSUER_OR_SEC.search(host):
                bad_host.append((r["ticker"], c["url"]))
            if THIRD_PARTY.search(c["url"]):
                third.append((r["ticker"], c["url"]))
    check(f"3. every evidence URL is an issuer or SEC URL (violations={bad_host[:3]})",
          not bad_host)
    check(f"5. no third-party source is cited as evidence (found={third[:3]})", not third)
    # The manifest deliberately NAMES the aggregators in its "not used"
    # declaration; that is a disclaimer, not a citation. Scan everything else.
    scanned = {k: v for k, v in MANIFEST.items() if k != "prohibited_sources_not_used"}
    hit = THIRD_PARTY.search(json.dumps(scanned))
    check(f"5b. no aggregator or market-data site is cited outside the not-used "
          f"declaration (hit={hit.group(0) if hit else None})", not hit)
    check("5c. the not-used declaration does name them, as a disclaimer",
          any(THIRD_PARTY.search(s) for s in MANIFEST["prohibited_sources_not_used"]))
    for name in MANIFEST["prohibited_sources_not_used"]:
        check(f"5d. the manifest records that {name!r} was not used", bool(name))


# ===== 4. no prohibited research field ====================================

def test_4_no_prohibited_fields():
    def walk(node, path=""):
        hits = []
        if isinstance(node, dict):
            for k, v in node.items():
                if PROHIBITED_FIELD.search(str(k)):
                    hits.append(f"{path}.{k}")
                hits += walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                hits += walk(v, f"{path}[{i}]")
        return hits
    # Field NAMES only -- the manifest legitimately names prohibited data in its
    # own "not inspected" declaration, which is a disclaimer, not a data field.
    hits = [h for h in walk(MANIFEST)
            if "prohibited_data_not_inspected" not in h
            and "prohibited_sources_not_used" not in h]
    check(f"4. no prohibited research field name exists in the manifest (found={hits[:5]})",
          not hits)
    check("4b. the manifest explicitly declares what was NOT inspected",
          set(["attention", "price", "volume", "volatility", "options"])
          <= set(MANIFEST["prohibited_data_not_inspected"]))


# ===== 6-7. enrollment claims and human verification ======================

def test_6_7_enrollment_and_humans():
    proposed = [r for r in ROWS if r["explicit_upcoming_earnings_event_found"]]
    for r in proposed:
        check(f"6. {r['ticker']} proposed with an explicit official date text",
              bool(r["official_date_time_text"]))
        check(f"6b. {r['ticker']} proposed with explicit timing", bool(r["proposed_release_session"]))
    check(f"6c. no candidate lacking explicit date+timing is proposed for enrollment "
          f"({len(proposed)} proposed)",
          all(r["official_date_time_text"] and r["proposed_release_session"] for r in proposed))
    enrolled = [r for r in ROWS if r["proposed_disposition"] == "ENROLLED"]
    check(f"7. no automated finding is dispositioned ENROLLED (found={len(enrolled)})",
          not enrolled)
    blob = json.dumps(MANIFEST) + json.dumps(QUEUE)
    check("7b. no automated candidate is represented as human-verified",
          not re.search(r'"verified_by"\s*:\s*"Harshith', blob))
    check("7c. the manifest states plainly that no human viewed any page",
          MANIFEST["operator"]["human_page_observation"].startswith("NONE"))
    check("7d. the operator field does not claim a human performed the sweep",
          "automated" in MANIFEST["operator"]["performed_by"].lower())
    check("7e. authorisation is recorded separately from observation",
          MANIFEST["operator"]["authorized_by"] == "Harshith Akurati"
          and "authorized_by" != "performed_by")
    check("7f. the human-review queue holds no enrollable candidate",
          QUEUE["enrollable_candidates_awaiting_human_verification"] == [])


# ===== 8. DELL not registered twice =======================================

def test_8_dell():
    dell = [r for r in ROWS if r["ticker"] == "DELL"]
    check("8. DELL appears exactly once in the sweep", len(dell) == 1)
    d = dell[0]
    check("8b. DELL is identified as the existing pre-protocol enrolled event",
          d["proposed_disposition"] == "ALREADY_ENROLLED_PRE_PROTOCOL")
    check("8c. it references the existing event and registration row",
          d["existing_event_id"] == "EVT-DELL-FY27Q2-ERN"
          and d["existing_registration_row_id"] == "EVT-DELL-FY27Q2-ERN-REG-001")
    check("8d. it is not treated as a newly discovered duplicate",
          "NOT a duplicate" in " ".join(d["notes"]))
    check("8e. the registration was not altered or amended",
          any("NOT altered" in n for n in d["notes"]))
    raw = REGISTRY_P.read_bytes()
    check("8f. the DELL registry is byte-identical to the baseline",
          hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
          == "71681aa48b9b483d582b887e82c229ba791548ae00a42ef9cf86be34776f4974")
    rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    check("8g. exactly one DELL REGISTRATION row exists",
          len(rows) == 1 and rows[0]["row_id"] == "EVT-DELL-FY27Q2-ERN-REG-001")
    check("8h. no second DELL registration was written",
          sum(1 for x in rows if x["ticker"] == "DELL"
              and x["row_type"] == "REGISTRATION") == 1)


# ===== 9-12. anchors, lead counts, window ================================

def test_9_12_anchors_and_gates():
    a = MANIFEST["anchor_derivation"]
    check("9. anchors are declared to come from the production planner",
          a["function"] == "gst_market_response.operations_plan.build_operations_plan")
    check("10. lead counts are declared to use the production XNYS calendar",
          a["calendar"].startswith("gst_market_response.exchange_calendar"))
    derived = [r for r in ROWS if r["proposed_derived_anchor"] is not None]
    check(f"9b. no anchor was derived by any other means (derived={len(derived)})",
          a["used_this_round"] is False and not derived)
    lead = [r for r in ROWS if r["proposed_lead_sessions"] is not None]
    check(f"10b. no lead count was computed outside the production calendar ({len(lead)})",
          not lead)
    # nothing may be proposed for enrollment below 5 sessions or outside the window
    short = [r for r in ROWS if isinstance(r["proposed_lead_sessions"], int)
             and r["proposed_lead_sessions"] < 5 and r["proposed_disposition"] == "ENROLLED"]
    check(f"11. no event under five sessions is proposed for enrollment (found={len(short)})",
          not short)
    cohort = json.loads((LSE / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json").read_text(
        encoding="utf-8"))
    lo, hi = cohort["collection_window"]["begins"], cohort["collection_window"]["ends"]
    outside = [r for r in ROWS if r["proposed_derived_anchor"]
               and not (lo <= r["proposed_derived_anchor"] <= hi)
               and r["proposed_disposition"] == "ENROLLED"]
    check(f"12. no event outside the collection window is proposed for enrollment "
          f"(found={len(outside)})", not outside)
    check("12b. the window is still 2026-09-01..2027-05-31",
          lo == "2026-09-01" and hi == "2027-05-31")
    check("12c. dispositions used are protocol-defined or the pre-protocol marker",
          {r["proposed_disposition"] for r in ROWS}
          <= ({d["code"] for d in cohort["dispositions"]}
              | {"ALREADY_ENROLLED_PRE_PROTOCOL", "REQUIRES_HUMAN_VERIFICATION"}))


# ===== 13. no research module imported or called =========================

def test_13_no_research_modules():
    banned_mod = re.compile(
        r"pytrends|GST_Phase2_DailyPanel|phase2_adapter|option_chain_adapter|alpaca_provider"
        r"|providers|derivations|completeness|pipeline", re.I)
    for name in ("sweep_round1.py", "sweep_round1_pass2.py", "build_manifest.py"):
        src = (SWEEP_DIR / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imported |= {al.name for al in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                imported.add(n.module)
        offending = sorted(m for m in imported if banned_mod.search(m))
        check(f"13. {name} imports no GST/panel/options/market-response module "
              f"(found={offending})", not offending)
        check(f"13b. {name} imports only constants from the package if anything",
              all(not m.startswith("gst_market_response.") or m.endswith("constants")
                  for m in imported))
    check("13c. no analysis module is referenced in the manifest",
          not re.search(r"statsmodels|sklearn|scipy|backtest", json.dumps(MANIFEST), re.I))


# ===== canonical rows and screening log ==================================

def test_14_no_canonical_rows():
    check("14. zero canonical screening rows were written",
          MANIFEST["canonical_screening_rows_written"] == 0)
    check("14b. zero registry rows were written", MANIFEST["registry_rows_written"] == 0)
    check("14c. no cohort screening log file exists",
          not (LSE / "Market_Response_Event_Registry" / "cohort_screening_log.jsonl").exists())
    check("14d. the reason is recorded, not silently omitted",
          "fiscal_period" in MANIFEST["why_no_canonical_rows"])
    check("14e. the protocol was not weakened to fit an observation",
          "weakening the schema" in MANIFEST["why_no_canonical_rows"])
    check("14f. no event log or stage marker exists anywhere",
          not list(HERE.rglob("EVT-*.jsonl")) and not list(HERE.rglob("EVT-*_MARKER.json")))


def test_15_no_network():
    reached = []
    for host in ("www.sec.gov", "investors.delltechnologies.com"):
        try:
            socket.create_connection((host, 443), timeout=2)
            reached.append(host)
        except NetworkBlocked:
            pass
        except Exception:  # noqa: BLE001
            pass
    check(f"15. sockets are blocked during validation (reached={reached})", not reached)
    leaked = sorted(m for m in sys.modules if m.split(".")[0] in _BANNED_TOP)
    check(f"15b. no provider module reached sys.modules (leaked={leaked})", not leaked)


if __name__ == "__main__":
    test_1_2_universe()
    test_3_5_sources()
    test_4_no_prohibited_fields()
    test_6_7_enrollment_and_humans()
    test_8_dell()
    test_9_12_anchors_and_gates()
    test_13_no_research_modules()
    test_14_no_canonical_rows()
    test_15_no_network()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL ROUND-1 SWEEP VALIDATION TESTS PASSED")
    sys.exit(0)
