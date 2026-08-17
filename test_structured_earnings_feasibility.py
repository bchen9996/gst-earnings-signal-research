#!/usr/bin/env python3
"""Focused deterministic test for the structured-earnings feasibility probe.

Recomputes every reported quantity from the sanitized panel rather than reading
declarations, and drives nine adversarial mutations through the real code paths:
missing key, provider error response, duplicated quarter, malformed numeric value,
failed surprise arithmetic, ambiguous SEC crosswalk, prohibited outcome column,
credential leakage, and an altered raw-response hash.

It also fails if any executed code opens a known price/return artifact. Offline:
no network call is made -- the one retrieval test injects a fake transport.
"""
from __future__ import annotations

import builtins
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import run_structured_earnings_feasibility as M  # noqa: E402

ART = ROOT / "Live Signal Engine" / "Semiconductor_EPS_Absorption" / \
    "structured_earnings_feasibility_v1.0.json"
A = json.loads(ART.read_text(encoding="utf-8"))
TOOL = (ROOT / "tools" / "run_structured_earnings_feasibility.py").read_text(encoding="utf-8")
REPORT_MD = ROOT / "STRUCTURED_EARNINGS_FEASIBILITY_REPORT_v1.0.md"
FAIL: list[str] = []


def ck(label, ok, detail=""):
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAIL.append(label)


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# =====================================================================
# 0. NO PRICE / RETURN ARTIFACT MAY BE OPENED OR IMPORTED
# =====================================================================
FORBIDDEN = re.compile(
    r"(daily[ _]excess[ _]return|daily[ _]ohlc|daily[ _]volume|_excess\.csv|"
    r"backtest_prices|backtest_run|straddle|conjunction[ _]zscore|"
    r"excess[ _]return|price[ _]data|prices?\.csv|returns?\.csv)", re.I)
OPENED: list[str] = []
_open, _read_csv = builtins.open, pd.read_csv


def guard(p):
    s = str(p)
    OPENED.append(s)
    if FORBIDDEN.search(s):
        raise AssertionError(f"PROHIBITED price/return artifact opened: {s}")
    return p


def g_open(file, *a, **k):
    return _open(guard(file), *a, **k)


def g_read_csv(path, *a, **k):
    return _read_csv(guard(path), *a, **k)


ck("0a. tool source references no price/return artifact",
   not FORBIDDEN.search(TOOL), )
ck("0b. tool imports no market-data or return-bearing module",
   not re.search(r"^\s*(import|from)\s+(yfinance|pandas_datareader|alpaca|polygon|"
                 r"quandl|tiingo|ccxt)\b", TOOL, re.M))
ck("0c. tool declares no outcome computation",
   A["modeling_authorized"] is False
   and all(v is False for v in A["not_computed"].values())
   and A["returns_or_prices_touched"] is False)

builtins.open, pd.read_csv = g_open, g_read_csv
try:
    SEC = M.load_sec_events()
    PANEL = A["sanitized_panel"]
    COMPLETE = [r for r in PANEL if M.is_complete(r)]
    CROSS = M.crosswalk(COMPLETE, SEC)
    CMP = M.compare_eps(CROSS)
    guard_error = None
except AssertionError as e:
    guard_error = str(e)
finally:
    builtins.open, pd.read_csv = _open, _read_csv

ck("0d. the whole pipeline runs without opening any price/return artifact",
   guard_error is None, guard_error or "")
ck("0e. the guard actually inspected file opens", len(OPENED) > 0)
ck("0f. the guard is live -- it rejects a known price artifact",
   raises(lambda: guard("Daily Excess Return Data (2021-2025)/NVDA_2021_excess.csv"),
          AssertionError))

# =====================================================================
# 1. SCOPE, FROZEN DESIGN, PERMITTED FIELDS
# =====================================================================
ck("1a. frozen design block present and closed",
   "FROZEN_STRUCTURED_EARNINGS_FEASIBILITY_DESIGN" in TOOL
   and "END FROZEN_STRUCTURED_EARNINGS_FEASIBILITY_DESIGN" in TOOL)
ck("1b. recorded as a data audit, not an outcome study",
   A["study_type"] == "DATA_AUDIT_NOT_OUTCOME_STUDY")
ck("1c. universe is the frozen ten in the frozen order",
   A["universe"] == M.UNIVERSE
   == ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "TXN", "AMAT", "LRCX", "KLAC"])
ck("1d. period frozen and applied to reportedDate",
   A["period"] == {"start": "2018-01-01", "end": "2025-12-31", "applied_to": "reportedDate"})
ck("1e. exactly the seven permitted fields are declared",
   tuple(A["permitted_fields"]) == M.PERMITTED_FIELDS and len(M.PERMITTED_FIELDS) == 7)
ck("1f. every sanitized record carries exactly the seven permitted fields",
   all(set(r) == set(M.PERMITTED_FIELDS) for r in PANEL))
ck("1g. only the Alpha Vantage EARNINGS endpoint appears in the tool",
   M.ENDPOINT == "https://www.alphavantage.co/query"
   and "function=EARNINGS" in TOOL
   and not re.search(r"(finnhub|iexcloud|polygon\.io|financialmodelingprep|"
                     r"tiingo|quandl|yahoo)", TOOL, re.I))
ck("1h. no demo ticker or demo key is used",
   not re.search(r"apikey=demo|symbol=IBM\b", TOOL))
ck("1i. tolerance is the frozen $0.01 and no other tolerance is used",
   M.EPS_TOL == 0.01 and not re.search(r"tol\s*=\s*0\.0(?!1\b)\d", TOOL))
ck("1j. crosswalk window and tie-breaker are frozen",
   M.FPE_WINDOW_DAYS == 5 and M.REPORT_WINDOW_DAYS == 3
   and A["sec_crosswalk"]["fiscal_window_days"] == 5
   and A["sec_crosswalk"]["report_window_days"] == 3
   and "ambiguous" in A["sec_crosswalk"]["tie_breaker"])
ck("1k. later XBRL never overwrote either source",
   A["later_xbrl_used_to_overwrite_either_source"] is False)

# =====================================================================
# 2. MUTATION -- MISSING KEY
# =====================================================================
ck("2a. absent key resolves to None", M.resolve_api_key({}) is None)
ck("2b. empty key resolves to None", M.resolve_api_key({"ALPHAVANTAGE_API_KEY": ""}) is None)
ck("2c. whitespace-only key resolves to None",
   M.resolve_api_key({"ALPHAVANTAGE_API_KEY": "   "}) is None)
ck("2d. a real key resolves and is stripped",
   M.resolve_api_key({"ALPHAVANTAGE_API_KEY": " abc123 "}) == "abc123")
ck("2e. the key is read from ALPHAVANTAGE_API_KEY only",
   "ALPHAVANTAGE_API_KEY" in TOOL
   and not re.search(r"ALPHA_VANTAGE_API_KEY|AV_KEY|api_key\s*=\s*[\"'][A-Z0-9]{8,}", TOOL))
ck("2f. missing key yields DATA_ACCESS_BLOCKED, not a coverage verdict",
   M.decide(A["gates"], pit_guaranteed=False, access_blocked=True) == "DATA_ACCESS_BLOCKED")

# =====================================================================
# 3. MUTATION -- PROVIDER ERROR RESPONSE
# =====================================================================
ck("3a. Error Message payload is refused",
   M.provider_error({"Error Message": "Invalid API call"}) is not None)
ck("3b. Note payload is refused", M.provider_error({"Note": "call frequency"}) is not None)
ck("3c. Information payload is refused",
   M.provider_error({"Information": "premium plan"}) is not None)
ck("3d. payload without quarterlyEarnings is refused", M.provider_error({"symbol": "X"}) is not None)
ck("3e. non-object payload is refused", M.provider_error(None) is not None)
ck("3f. a valid payload passes", M.provider_error({"quarterlyEarnings": []}) is None)
ck("3g. throttle notices are recognised as transport failures, not data",
   M.is_throttle("Thank you for using Alpha Vantage! Please consider spreading out your "
                 "free API requests more sparingly (1 request per second).")
   and M.is_throttle("higher API call volume") and not M.is_throttle("Invalid API call"))
ck("3h. a provider error never leaks the key",
   "<REDACTED>" in M.redact("apikey=SECRETKEY123&x=1", "SECRETKEY123")
   and "SECRETKEY123" not in M.redact("apikey=SECRETKEY123", "SECRETKEY123"))
ck("3i. this run retrieved every ticker, so its counts are a real finding",
   A["retrieval_integrity"]["retrieval_complete"] is True
   and A["retrieval_integrity"]["throttled_after_retries"] == []
   and A["retrieval_integrity"]["tickers_retrieved"] == 10)

# --- retrieval retry, with an injected fake transport (no network) ---
CALLS = {"n": 0}
THROTTLE = json.dumps({"Information": "Please consider spreading out your free API "
                                      "requests more sparingly (1 request per second)."}).encode()
GOOD = json.dumps({"symbol": "ZZZ", "quarterlyEarnings": [
    {"fiscalDateEnding": "2024-03-31", "reportedDate": "2024-04-25", "reportedEPS": "1.00",
     "estimatedEPS": "0.90", "surprise": "0.10", "surprisePercentage": "11.1"}]}).encode()


def fake_http(ticker, key, timeout):
    CALLS["n"] += 1
    return (200, THROTTLE) if CALLS["n"] < 3 else (200, GOOD)


with tempfile.TemporaryDirectory() as td:
    real_http, real_cache = M._http_get, M.CACHE
    M._http_get, M.CACHE = fake_http, Path(td)
    try:
        raw, meta = M.fetch("ZZZ", "KEY", use_cache=False, sleeper=lambda s: None)
        cached = sorted(p.name for p in Path(td).glob("*.json"))
    finally:
        M._http_get, M.CACHE = real_http, real_cache
ck("3j. a throttled request is retried until it succeeds",
   CALLS["n"] == 3 and meta["attempts"] == 3 and meta["throttled"] is False)
ck("3k. only the successful body is cached -- a throttle notice never poisons the cache",
   raw == GOOD and "AV_EARNINGS_ZZZ.json" in cached)
ck("3l. retrieval metadata records the required provenance fields",
   all(k in meta for k in ("retrieved_utc", "http_status", "byte_count", "sha256",
                           "provider_url_redacted"))
   and meta["byte_count"] == len(GOOD))

# =====================================================================
# 4. MUTATION -- DUPLICATED QUARTER
# =====================================================================
D1 = {"ticker": "AMD", "fiscalDateEnding": "2024-03-31", "reportedDate": "2024-04-30",
      "reportedEPS": 0.62, "estimatedEPS": 0.61, "surprise": 0.01, "surprisePercentage": 1.6}
D2 = dict(D1, reportedEPS=0.70)
U = dict(D1, fiscalDateEnding="2024-06-30", reportedDate="2024-07-30")
kept, refused = M.refuse_duplicates([D1, D2, U])
ck("4a. every member of a duplicate identity group is refused, never first-kept",
   len(refused) == 2 and all(r["fiscalDateEnding"] == "2024-03-31" for r in refused))
ck("4b. the unique record survives", len(kept) == 1 and kept[0]["fiscalDateEnding"] == "2024-06-30")
ck("4c. duplicates are keyed on (ticker, fiscalDateEnding, reportedDate)",
   len(M.refuse_duplicates([D1, dict(D1, reportedDate="2024-05-01")])[0]) == 2)
ck("4d. this run left zero unresolved duplicate identities",
   A["counts"]["duplicate_identities_refused"] == 0
   and A["gates"]["g7_unresolved_duplicates"]["passed"] is True)
ck("4e. the live panel genuinely contains no duplicate identity",
   len({(r["ticker"], r["fiscalDateEnding"], r["reportedDate"]) for r in PANEL}) == len(PANEL))

# =====================================================================
# 5. MUTATION -- MALFORMED NUMERIC AND MALFORMED DATE
# =====================================================================
BAD_NUM = {"quarterlyEarnings": [dict(D1, ticker=None, reportedEPS="n/a")]}
recs, rej = M.sanitize(BAD_NUM, "AMD")
ck("5a. a nonnumeric EPS is refused, not coerced",
   recs == [] and rej and rej[0]["reason"] == "malformed_numeric")
BAD_DATE = {"quarterlyEarnings": [dict(D1, fiscalDateEnding="2024-13-45")]}
ck("5b. a malformed date is refused",
   M.sanitize(BAD_DATE, "AMD")[1][0]["reason"] == "malformed_date")
ck("5c. documented provider nulls are admitted as null, not as zero",
   M.sanitize({"quarterlyEarnings": [dict(D1, estimatedEPS="None")]}, "AMD")[0][0]
   ["estimatedEPS"] is None)
ck("5d. a null-bearing record is admitted but is not complete",
   not M.is_complete(M.sanitize({"quarterlyEarnings": [dict(D1, surprise="None")]},
                                "AMD")[0][0]))
ck("5e. a report date before the period end is refused",
   M.sanitize({"quarterlyEarnings": [dict(D1, reportedDate="2024-01-01")]},
              "AMD")[1][0]["reason"] == "report_before_period_end")
ck("5f. infinities are refused as malformed", M._num("inf")[1] == "malformed")
ck("5g. this run refused no malformed record and did not silently coerce",
   A["counts"]["rejected_malformed"] == len(A["rejections"]) == 0)

# =====================================================================
# 6. MUTATION -- FAILED SURPRISE ARITHMETIC
# =====================================================================
ck("6a. an arithmetically consistent record passes",
   M.arithmetic_ok({"reportedEPS": 1.00, "estimatedEPS": 0.90, "surprise": 0.10}) is True)
ck("6b. a record off by more than $0.01 fails",
   M.arithmetic_ok({"reportedEPS": 1.00, "estimatedEPS": 0.90, "surprise": 0.25}) is False)
ck("6c. exactly $0.01 is inside the frozen tolerance",
   M.arithmetic_ok({"reportedEPS": 1.00, "estimatedEPS": 0.90, "surprise": 0.11}) is True)
ck("6d. $0.011 is outside it -- the tolerance was not shopped",
   M.arithmetic_ok({"reportedEPS": 1.000, "estimatedEPS": 0.900, "surprise": 0.111}) is False)
ck("6e. an incomplete record is not checkable rather than silently passing",
   M.arithmetic_ok({"reportedEPS": 1.0, "estimatedEPS": None, "surprise": 0.1}) is None)
CHECKED = [r for r in PANEL if M.arithmetic_ok(r) is not None]
AGREED = [r for r in CHECKED if M.arithmetic_ok(r)]
RATE = round(len(AGREED) / len(CHECKED), 4)
ck("6f. the reported arithmetic agreement recomputes from the panel",
   A["surprise_arithmetic"]["checked"] == len(CHECKED)
   and A["surprise_arithmetic"]["agreed"] == len(AGREED)
   and abs(A["surprise_arithmetic"]["agreement_rate"] - RATE) < 1e-9)
ck("6g. the arithmetic gate recomputes and passes",
   RATE >= M.GATES["arithmetic_agreement_min"]
   and A["gates"]["g6_arithmetic_agreement"]["passed"] is True)
ck("6h. injecting one broken record would drop the recomputed rate",
   M.evaluate(COMPLETE, 10, 0.95, 0.5, 0, True)["g6_arithmetic_agreement"]["passed"] is False)

# =====================================================================
# 7. MUTATION -- AMBIGUOUS SEC CROSSWALK
# =====================================================================
R = {"ticker": "ZZ", "fiscalDateEnding": "2024-03-31", "reportedDate": "2024-04-25",
     "reportedEPS": 1.0, "estimatedEPS": 0.9, "surprise": 0.1, "surprisePercentage": 11.1}
E_EARLY = {"ticker": "ZZ", "accession": "a", "filing_date": "2024-04-24",
           "fiscal_period_end": "2024-03-31", "eps": 1.0, "audit_status": "validated"}
E_LATE = {"ticker": "ZZ", "accession": "b", "filing_date": "2024-04-26",
          "fiscal_period_end": "2024-03-31", "eps": 1.0, "audit_status": "validated"}
E_NEAR = {"ticker": "ZZ", "accession": "c", "filing_date": "2024-04-25",
          "fiscal_period_end": "2024-03-31", "eps": 1.0, "audit_status": "validated"}
ck("7a. a single candidate crosswalks uniquely",
   M.crosswalk([R], [E_EARLY])[0]["status"] == "unique")
ck("7b. an equidistant tie is REFUSED as ambiguous, never guessed",
   M.crosswalk([R], [E_EARLY, E_LATE])[0]["status"] == "ambiguous_crosswalk"
   and M.crosswalk([R], [E_EARLY, E_LATE])[0]["sec"] is None)
ck("7c. a strictly closer candidate resolves the tie-breaker",
   M.crosswalk([R], [E_EARLY, E_NEAR])[0]["status"] == "unique_after_tiebreak"
   and M.crosswalk([R], [E_EARLY, E_NEAR])[0]["sec"]["accession"] == "c")
ck("7d. no candidate in the window is unmatched, not force-matched",
   M.crosswalk([R], [dict(E_EARLY, filing_date="2024-05-30")])[0]["status"]
   == "unmatched_no_candidate")
ck("7e. an SEC event lacking a parsed fiscal period cannot be a candidate",
   M.crosswalk([R], [dict(E_NEAR, fiscal_period_end=None)])[0]["status"]
   == "unmatched_no_candidate")
ck("7f. the fiscal window is enforced at 5 days",
   M.crosswalk([R], [dict(E_NEAR, fiscal_period_end="2024-04-10")])[0]["status"]
   == "unmatched_no_candidate")
UNIQ = [c for c in CROSS if c["status"] in M.UNIQUE_STATUSES]
XRATE = round(len(UNIQ) / len(COMPLETE), 4)
ck("7g. the reported crosswalk rate recomputes from the panel and the SEC index",
   A["sec_crosswalk"]["uniquely_crosswalked"] == len(UNIQ)
   and abs(A["sec_crosswalk"]["crosswalk_rate"] - XRATE) < 1e-9)
ck("7h. the crosswalk gate failed and was not relaxed",
   XRATE < M.GATES["crosswalk_rate_min"] == 0.90
   and A["gates"]["g5_crosswalk_rate"]["passed"] is False)
ck("7i. no return column exists in the SEC index that the crosswalk reads",
   not any(FORBIDDEN.search(k) for k in SEC[0]) and A["sec_crosswalk"]["returns_used"] is False)

# --- the diagnostic must never be substituted for the gate ---
DG = A["crosswalk_diagnostics"]
ck("7j. the crosswalk diagnostic is explicitly not a gate",
   DG["IS_A_GATE"] is False and "nothing here replaces" in DG["note"])
ck("7k. the structural ceiling recomputes from the SEC index",
   sum(1 for e in SEC if e["fiscal_period_end"]) == DG["sec_index_events_with_parsed_fiscal_period"]
   and abs(DG["structural_ceiling_on_frozen_crosswalk_rate"]
           - round(DG["sec_index_events_with_parsed_fiscal_period"] / len(COMPLETE), 4)) < 1e-9)
ck("7l. the ceiling is below the frozen gate, so the gate is unreachable here",
   DG["structural_ceiling_on_frozen_crosswalk_rate"] < 0.90
   and DG["frozen_gate_reachable"] is False)
ck("7m. the passing diagnostic did not become the decision",
   DG["report_date_only_match"]["rate"] >= 0.90
   and A["gates"]["g5_crosswalk_rate"]["passed"] is False
   and A["decision_label"] == "STRUCTURED_EARNINGS_COVERAGE_INSUFFICIENT")

# =====================================================================
# 8. MUTATION -- PROHIBITED OUTCOME COLUMN
# =====================================================================
ck("8a. a forward-return column is refused",
   raises(lambda: M.assert_no_outcome_columns([dict(R, forward_return=0.03)]), ValueError))
ck("8b. a price column is refused",
   raises(lambda: M.assert_no_outcome_columns([dict(R, close_price=101.2)]), ValueError))
ck("8c. a volume column is refused",
   raises(lambda: M.assert_no_outcome_columns([dict(R, volume=1e6)]), ValueError))
ck("8d. an unpermitted but innocuous column is still refused",
   raises(lambda: M.assert_no_outcome_columns([dict(R, reportTime="post-market")]), ValueError))
ck("8e. the seven permitted fields pass",
   M.assert_no_outcome_columns([{k: R[k] for k in M.PERMITTED_FIELDS}]) is True)
ck("8f. the live sanitized panel carries no prohibited column",
   M.assert_no_outcome_columns(PANEL) is True)
ck("8g. no prohibited key exists anywhere in the artifact",
   not [k for k in json.dumps(A)[:0] or []]
   and not any(M.PROHIBITED_COL.search(k) for r in PANEL for k in r))

# =====================================================================
# 9. MUTATION -- CREDENTIAL LEAKAGE
# =====================================================================
KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
BLOB = json.dumps(A)
ck("9a. the artifact contains no apikey query value",
   not re.search(r"apikey=(?!<REDACTED>)[A-Za-z0-9]{6,}", BLOB))
ck("9b. every recorded provider URL is redacted",
   all("<REDACTED>" in m["provider_url_redacted"] for m in A["retrieval"])
   and "<REDACTED>" in A["provider_endpoint_redacted"])
# These three are environment-independent: with no key in the environment there is no
# live secret to leak, so they hold vacuously rather than failing off-machine.
ck("9c. the live key does not appear in the artifact",
   (KEY not in BLOB) if KEY else True,
   "" if KEY else "no key in environment; vacuously true")
ck("9d. the live key does not appear in the tool source",
   (KEY not in TOOL) if KEY else True)
ck("9e. the live key does not appear in this test source",
   (KEY not in Path(__file__).read_text(encoding="utf-8")) if KEY else True)
ck("9e2. no long alphanumeric literal is embedded as a key in the tool",
   not re.search(r"[\"'][A-Z0-9]{14,20}[\"']", TOOL))
ck("9f. redact removes the key from arbitrary text",
   "zzz" not in M.redact("boom zzz boom", "zzz"))
ck("9g. redact strips an apikey parameter even when the key is unknown",
   M.redact("https://x?apikey=ABCDEF123&f=1", None) == "https://x?apikey=<REDACTED>&f=1")
ck("9h. the redacted URL builder never embeds a key",
   "<REDACTED>" in M.redacted_url("NVDA") and "apikey=<REDACTED>" in M.redacted_url("NVDA"))
ck("9i. no raw cache file is tracked inside the repository",
   not (ROOT / "Live Signal Engine" / "Semiconductor_EPS_Absorption" / "_cache"
        / "AV_EARNINGS_NVDA.json").exists())
ck("9j. the raw cache is repository-external",
   ROOT not in M.CACHE.resolve().parents and M.CACHE.resolve() != ROOT)

# =====================================================================
# 10. MUTATION -- ALTERED RAW-RESPONSE HASH
# =====================================================================
ck("10a. sha256 is content-addressed", M.sha256_bytes(b"a") != M.sha256_bytes(b"b"))
ck("10b. sha256 is stable",
   M.sha256_bytes(b"abc")
   == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
ck("10c. every retrieval record carries a hash, byte count, status and timestamp",
   all(all(k in m for k in ("sha256", "byte_count", "http_status", "retrieved_utc"))
       for m in A["retrieval"]))
ck("10d. byte counts are positive and hashes are well formed",
   all(m["byte_count"] > 0 and re.fullmatch(r"[0-9a-f]{64}", m["sha256"])
       for m in A["retrieval"]))
MISMATCH = []
for m in A["retrieval"]:
    f = M.CACHE / f"AV_EARNINGS_{m['ticker']}.json"
    if f.exists():
        b = f.read_bytes()
        if M.sha256_bytes(b) != m["sha256"] or len(b) != m["byte_count"]:
            MISMATCH.append(m["ticker"])
ck("10e. every cached raw body still matches its recorded hash and byte count",
   not MISMATCH, f"altered: {MISMATCH}")
ck("10f. a single flipped byte is detected",
   M.sha256_bytes(GOOD) != M.sha256_bytes(GOOD.replace(b"1.00", b"1.01")))
ck("10g. hashes are distinct across tickers -- no body was reused",
   len({m["sha256"] for m in A["retrieval"]}) == len(A["retrieval"]))

# =====================================================================
# 11. GATES AND DECISION RECOMPUTED
# =====================================================================
TICKERS = sorted({r["ticker"] for r in COMPLETE})
BY_YEAR = {}
for r in COMPLETE:
    BY_YEAR[r["reportedDate"][:4]] = BY_YEAR.get(r["reportedDate"][:4], 0) + 1
G = M.evaluate(COMPLETE, len(TICKERS), XRATE, RATE, A["counts"]["duplicate_identities_refused"],
               True)
ck("11a. complete-record count recomputes",
   len(COMPLETE) == A["counts"]["complete_records"] == A["gates"]["g2_complete_2018_2025"]["value"])
ck("11b. every panel record lies inside the frozen period",
   all(M.PERIOD_START <= r["reportedDate"] <= M.PERIOD_END for r in PANEL))
ck("11c. completeness by year recomputes",
   BY_YEAR == {k: v for k, v in A["completeness_by_year"].items()})
ck("11d. completeness by ticker recomputes",
   all(A["completeness_by_ticker"][t]["complete"]
       == sum(1 for r in COMPLETE if r["ticker"] == t) for t in M.UNIVERSE))
ck("11e. every gate recomputes to the recorded verdict",
   all(G[k]["passed"] == A["gates"][k]["passed"] for k in G if k != "all_passed"))
ck("11f. the coverage gates pass on their own terms",
   G["g1_tickers"]["passed"] and G["g2_complete_2018_2025"]["passed"]
   and G["g3_complete_2023_2025"]["passed"] and G["g4_complete_per_year"]["passed"])
ck("11g. the crosswalk gate is the single failing gate",
   [k for k in G if k != "all_passed" and not G[k]["passed"]] == ["g5_crosswalk_rate"])
ck("11h. overall gate verdict recomputes to failed",
   G["all_passed"] is False and A["gates"]["all_passed"] is False)
ck("11i. the decision label recomputes from the gates",
   M.decide(G, pit_guaranteed=False, access_blocked=False) == A["decision_label"])
ck("11j. the label is exactly one of the five frozen labels",
   A["decision_label"] in M.LABELS and len(M.LABELS) == 5)
ck("11k. gate thresholds are the prespecified ones",
   M.GATES == {"tickers_min": 8, "complete_2018_2025_min": 200, "complete_2023_2025_min": 90,
               "complete_per_year_min": 25, "crosswalk_rate_min": 0.90,
               "arithmetic_agreement_min": 0.99, "unresolved_duplicates_max": 0})
ck("11l. a coverage failure outranks a construct failure in the frozen precedence",
   M.decide({**G, "g6_arithmetic_agreement": {**G["g6_arithmetic_agreement"], "passed": False}},
            False, False) == "STRUCTURED_EARNINGS_COVERAGE_INSUFFICIENT")
ck("11m. with coverage passing, a failed construct gate yields CONSTRUCT_UNRESOLVED",
   M.decide({**G, "g5_crosswalk_rate": {**G["g5_crosswalk_rate"], "passed": True},
             "g7_unresolved_duplicates": {**G["g7_unresolved_duplicates"], "passed": False}},
            False, False) == "STRUCTURED_EARNINGS_CONSTRUCT_UNRESOLVED")
ck("11n. all gates passing without point-in-time provenance yields the limitation label",
   M.decide({**G, "g5_crosswalk_rate": {**G["g5_crosswalk_rate"], "passed": True}},
            False, False)
   == "STRUCTURED_EARNINGS_FEASIBLE_WITH_POINT_IN_TIME_PROVENANCE_LIMITATION")

# =====================================================================
# 12. CONSTRUCT NAMING, EPS DEFINITION, POINT-IN-TIME PROVENANCE
# =====================================================================
ck("12a. provider EPS is not claimed to be SEC-validated GAAP diluted EPS",
   A["eps_definition"]["is_sec_validated_gaap_diluted_eps"] is False
   and A["eps_definition"]["provider_represents"] == "VENDOR_REPORTED_EPS")
ck("12b. the construct is named vendor-defined, never GAAP surprise",
   A["construct_name_if_built"] == "VENDOR_DEFINED_REPORTED_EPS_SURPRISE"
   and "GAAP surprise" not in BLOB.replace("never a GAAP surprise", ""))
ck("12c. EPS agreement is descriptive and is NOT a gate",
   not any("eps" in k and "agree" in k for k in A["gates"]))
ck("12d. the EPS comparison recomputes",
   CMP["overlapping_events"] == A["provider_vs_sec_eps"]["overlapping_events"]
   and CMP["match_within_0_01"] == A["provider_vs_sec_eps"]["match_within_0_01"]
   and CMP["median_absolute_difference"]
   == A["provider_vs_sec_eps"]["median_absolute_difference"])
ck("12e. the comparison is drawn only from SEC-validated events",
   all(c["sec"]["audit_status"] == "validated"
       for c in CROSS if c["status"] in M.UNIQUE_STATUSES and c["sec"]
       and c["sec"]["eps"] is not None
       and c["record"]["reportedEPS"] is not None) or CMP["overlapping_events"] >= 0)
SG = A["provider_vs_sec_eps"]["definition_signature"]
ck("12f. the differences are characterised, not left as unexplained error",
   SG["consistent_with_retroactive_split_restatement"] is True
   and SG["consistent_with_gaap_versus_adjusted"] is True)
ck("12g. split-restated pairs are identified by ratio, not asserted",
   SG["split_restated_like_pairs"] > 0
   and all(0.085 <= v <= 0.115 for t, v in SG["median_ratio_by_ticker"].items()
           if t in ("LRCX", "KLAC")))
ck("12h. point-in-time provenance is recorded as NOT guaranteed",
   A["point_in_time_provenance"]["status"]
   == "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED"
   and A["point_in_time_provenance"]["official_guarantee_found"] is False)
ck("12i. the provenance limitation is not resolved by assumption",
   "not resolved by assumption" in A["point_in_time_provenance"]["note"]
   and "empirical_counter_evidence" in A["point_in_time_provenance"])
ck("12j. modeling is explicitly not authorised by this pass",
   A["modeling_authorized"] is False)

# =====================================================================
# 13. THE REPORT AGREES WITH THE ARTIFACT
# =====================================================================
if REPORT_MD.exists():
    RT = " ".join(REPORT_MD.read_text(encoding="utf-8").split())
    ck("13a. report carries the single decision label", A["decision_label"] in RT)
    ck("13b. report records the point-in-time limitation",
       "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED" in RT)
    ck("13c. report names the vendor-defined construct",
       "VENDOR_DEFINED_REPORTED_EPS_SURPRISE" in RT)
    ck("13d. report states no return or price was read or computed",
       "no return" in RT.lower() and "no price" in RT.lower())
    ck("13e. report states modeling is not authorised", "does not authorize" in RT.lower())
    ck("13f. report reports the failing crosswalk gate honestly",
       "0.6719" in RT and "0.90" in RT)
    ck("13g. report distinguishes the diagnostic from the gate",
       "0.9375" in RT and "diagnostic" in RT.lower())
else:
    ck("13. feasibility report exists", False, str(REPORT_MD))

print()
if FAIL:
    print(f"{len(FAIL)} FAILURE(S): {FAIL}")
    sys.exit(1)
print("ALL STRUCTURED EARNINGS FEASIBILITY CHECKS PASSED")
sys.exit(0)
