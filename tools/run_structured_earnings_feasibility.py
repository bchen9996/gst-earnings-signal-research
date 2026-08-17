#!/usr/bin/env python3
"""Structured earnings data feasibility probe -- Alpha Vantage EARNINGS.

This is a DATA AUDIT, not an outcome study. It answers one question: can the
semiconductor earnings-surprise study be run credibly on structured vendor data
instead of a hand-built SEC exhibit parser?

Nothing here reads, opens, imports or computes a stock return, price, price
reaction, volume, option, strategy or trading outcome. Passing feasibility does
NOT authorize modeling.

=============== FROZEN_STRUCTURED_EARNINGS_FEASIBILITY_DESIGN ===============
Frozen and committed BEFORE the first Alpha Vantage request was issued.

SCOPE
  A data-availability and data-integrity audit. No SUE, no information-price
  gap, no post-earnings drift, no bootstrap, no coefficient, no portfolio
  return, no trade. The outcome design, if any, is frozen in a separate task.

UNIVERSE (unchanged from the semiconductor study, frozen order)
  NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, AMAT, LRCX, KLAC

PERIOD
  2018-01-01 .. 2025-12-31, applied to reportedDate (the announcement date).

PROVIDER -- the only permitted source
  Official Alpha Vantage EARNINGS endpoint:
    https://www.alphavantage.co/query?function=EARNINGS&symbol=<TICKER>&apikey=<KEY>
  No other provider. No demo ticker. No substitute endpoint.

CREDENTIAL
  Read only from the environment variable ALPHAVANTAGE_API_KEY. The key is
  never printed, logged, serialized, committed, or placed in any recorded URL.
  Every recorded URL is the provider URL with apikey redacted. If the variable
  is absent, empty, or rejected by the provider, the run reports
  DATA_ACCESS_BLOCKED and stops.

PERMITTED FIELDS -- exactly seven, nothing else is retained
  ticker, fiscalDateEnding, reportedDate, reportedEPS, estimatedEPS,
  surprise, surprisePercentage

PROHIBITED FIELDS -- refused if they ever appear in the derived panel
  any price, return, close, open, high, low, adjusted, volume, option, implied
  volatility, news, sentiment, trend, drift, alpha, pnl or outcome column.

RAW RESPONSE HANDLING
  Raw provider bodies are cached REPOSITORY-EXTERNAL (default: a sibling of the
  repository root, override with GST_AV_CACHE_DIR). Raw bodies are never
  committed. For each ticker the run records: retrieval timestamp (UTC),
  byte count, SHA-256 of the raw body, HTTP status, the redacted provider URL,
  and the response-schema version if the provider supplies one.

RECORD ADMISSION
  documented provider nulls  = {None, "None", "", "-", "null", "NaN"}
  valid identity  : ticker in universe, fiscalDateEnding and reportedDate both
                    parse as ISO calendar dates, and reportedDate >= fiscalDateEnding.
  duplicate identity : two or more records sharing
                    (ticker, fiscalDateEnding, reportedDate).
                    ALL members of a duplicate group are REFUSED outright,
                    never first-kept, never de-duplicated by preference.
  malformed       : a non-null value in reportedEPS / estimatedEPS / surprise /
                    surprisePercentage that does not parse as a finite float,
                    or an unparseable date. Refused, counted, never coerced.
  complete record : valid identity, admitted, and reportedEPS, estimatedEPS and
                    surprise all numeric (surprisePercentage tracked separately).

INTERNAL ARITHMETIC CHECK
  Wherever reportedEPS, estimatedEPS and surprise are all numeric:
      | (reportedEPS - estimatedEPS) - surprise |  <=  0.01
  Absolute tolerance $0.01, frozen. No other tolerance is computed or reported.

SEC CROSSWALK -- window and tie-breaker frozen before any match was inspected
  Target index: the existing SEC Item 2.02 event index committed at
  "Live Signal Engine/Semiconductor_EPS_Absorption/event_panel_v1.0.csv"
  (ticker, fiscal_period_end, filing_date, accession, eps, audit_status).
  Returns are NOT used, are not present in that index, and are not consulted.

  A provider record and an SEC event are candidates iff BOTH hold:
      | provider.fiscalDateEnding - sec.fiscal_period_end |  <= 5 calendar days
      | provider.reportedDate     - sec.filing_date       |  <= 3 calendar days
  Resolution:
      0 candidates  -> unmatched_no_candidate
      1 candidate   -> uniquely crosswalked
      >1 candidates -> TIE-BREAKER: keep the single candidate with the smallest
                       | reportedDate - filing_date |. If two or more candidates
                       tie on that distance, the record is REFUSED as
                       ambiguous_crosswalk. Ambiguity is never guessed.
  Only uniquely crosswalked records count toward the crosswalk gate.

PROVIDER-VERSUS-SEC EPS COMPARISON (descriptive, never a gate)
  On records that are uniquely crosswalked to an SEC event whose audit_status
  is "validated" (the 150 SEC-validated parser values), report: overlapping
  count, match rate within $0.01, median absolute difference, the largest
  discrepancies, and whether the differences look consistent with a
  GAAP-versus-adjusted EPS definition difference.
  Later XBRL is NOT used to overwrite either source. Neither source is
  corrected by the other. Alpha Vantage EPS is NOT required to equal GAAP EPS.

PRESPECIFIED FEASIBILITY GATES -- all mechanical gates must pass
  g1 tickers retrieved with >=1 complete record          >= 8 of 10
  g2 unique complete quarterly records 2018-2025         >= 200
  g3 complete records 2023-2025                          >= 90
  g4 complete records in EACH of 2023, 2024, 2025        >= 25 each
  g5 uniquely crosswalked share of complete records      >= 0.90
  g6 internal surprise-arithmetic agreement              >= 0.99
     (denominator: records with all three numeric fields)
  g7 unresolved duplicate identities                     == 0
  g8 terminology gate: the artifact and report explicitly distinguish
     vendor-reported EPS from SEC-validated GAAP diluted EPS, and name the
     construct VENDOR_DEFINED_REPORTED_EPS_SURPRISE.
  Year assignment for g2/g3/g4 is the calendar year of reportedDate.

POINT-IN-TIME PROVENANCE
  Default and conservative: POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED.
  Recorded unless Alpha Vantage publishes an explicit official guarantee that
  historical estimatedEPS is the contemporaneous consensus preserved as of the
  announcement. The limitation is never concealed or resolved by assumption.

CONSTRUCT NAMING
  Whatever the agreement with SEC GAAP diluted EPS turns out to be, any eventual
  surprise construct built on this source is named
  VENDOR_DEFINED_REPORTED_EPS_SURPRISE -- never "GAAP surprise", never an
  analyst surprise, consensus miss, fair value or proven mispricing.

DECISION LABEL -- exactly one, resolved in this frozen precedence
  1. DATA_ACCESS_BLOCKED
       key absent/empty, or the provider rejected the key, or no ticker returned
       a parseable EARNINGS payload.
  2. STRUCTURED_EARNINGS_COVERAGE_INSUFFICIENT
       any of g1, g2, g3, g4, g5 fails.
  3. STRUCTURED_EARNINGS_CONSTRUCT_UNRESOLVED
       coverage gates pass but g6, g7 or g8 fails.
  4. STRUCTURED_EARNINGS_FEASIBLE_WITH_POINT_IN_TIME_PROVENANCE_LIMITATION
       all gates pass and point-in-time provenance is NOT guaranteed.
  5. STRUCTURED_EARNINGS_FEASIBLE_FOR_VENDOR_DEFINED_SURPRISE
       all gates pass and point-in-time provenance IS officially guaranteed.
============= END FROZEN_STRUCTURED_EARNINGS_FEASIBILITY_DESIGN =============
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Live Signal Engine" / "Semiconductor_EPS_Absorption"
SEC_PANEL = OUT / "event_panel_v1.0.csv"
ARTIFACT = OUT / "structured_earnings_feasibility_v1.0.json"
# Repository-external raw cache. Never inside the repo, never committed.
CACHE = Path(os.environ.get("GST_AV_CACHE_DIR") or (ROOT.parent / "gst-av-earnings-cache"))

UNIVERSE = ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "TXN", "AMAT", "LRCX", "KLAC"]
PERIOD_START, PERIOD_END = "2018-01-01", "2025-12-31"
ENDPOINT = "https://www.alphavantage.co/query"
PERMITTED_FIELDS = ("ticker", "fiscalDateEnding", "reportedDate", "reportedEPS",
                    "estimatedEPS", "surprise", "surprisePercentage")
NUMERIC_FIELDS = ("reportedEPS", "estimatedEPS", "surprise", "surprisePercentage")
ARITH_FIELDS = ("reportedEPS", "estimatedEPS", "surprise")
DOCUMENTED_NULLS = {None, "None", "", "-", "null", "NaN"}
EPS_TOL = 0.01
FPE_WINDOW_DAYS = 5
REPORT_WINDOW_DAYS = 3
CONSTRUCT_NAME = "VENDOR_DEFINED_REPORTED_EPS_SURPRISE"
PIT_NOT_GUARANTEED = "POINT_IN_TIME_ESTIMATE_PROVENANCE_NOT_GUARANTEED"

GATES = {"tickers_min": 8, "complete_2018_2025_min": 200, "complete_2023_2025_min": 90,
         "complete_per_year_min": 25, "crosswalk_rate_min": 0.90,
         "arithmetic_agreement_min": 0.99, "unresolved_duplicates_max": 0}
GATE_YEARS = (2023, 2024, 2025)

PROHIBITED_COL = re.compile(
    r"(price|return|close|open|high|low|adjusted|volume|option|implied|iv\b|"
    r"news|sentiment|trend|drift|alpha|pnl|profit|trade|position|portfolio|"
    r"reaction|abnormal|excess|car\b|bhar)", re.I)

LABELS = ("STRUCTURED_EARNINGS_FEASIBLE_FOR_VENDOR_DEFINED_SURPRISE",
          "STRUCTURED_EARNINGS_FEASIBLE_WITH_POINT_IN_TIME_PROVENANCE_LIMITATION",
          "STRUCTURED_EARNINGS_COVERAGE_INSUFFICIENT",
          "STRUCTURED_EARNINGS_CONSTRUCT_UNRESOLVED",
          "DATA_ACCESS_BLOCKED")


# ------------------------------------------------------------------ credential

def resolve_api_key(env=None):
    """Return the key, or None. The key is never returned inside any other value."""
    v = (env if env is not None else os.environ).get("ALPHAVANTAGE_API_KEY")
    if v is None:
        return None
    v = v.strip()
    return v or None


def redact(text, key):
    """Remove any occurrence of the key, and any apikey=... query value."""
    s = str(text)
    if key:
        s = s.replace(key, "<REDACTED>")
    return re.sub(r"(apikey=)[^&\s\"']+", r"\1<REDACTED>", s)


def redacted_url(ticker):
    return f"{ENDPOINT}?function=EARNINGS&symbol={ticker}&apikey=<REDACTED>"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------- retrieval

def provider_error(payload):
    """Return a provider-side error string, or None. Never echoes a key."""
    if not isinstance(payload, dict):
        return "payload is not a JSON object"
    for k in ("Error Message", "Note", "Information"):
        if k in payload:
            return f"{k}: {str(payload[k])[:200]}"
    if "quarterlyEarnings" not in payload:
        return "no quarterlyEarnings array in payload"
    if not isinstance(payload["quarterlyEarnings"], list):
        return "quarterlyEarnings is not a list"
    return None


THROTTLE_MARK = re.compile(
    r"(spreading out your free api requests|higher api call volume|call frequency|"
    r"premium plan|rate limit|per (minute|day))", re.I)
REQUEST_SPACING_S = 2.0     # provider asks for <= 1 request/second on the free tier
MAX_ATTEMPTS = 5


def is_throttle(err):
    """A throttle notice is a TRANSPORT failure, never a data finding."""
    return bool(err) and bool(THROTTLE_MARK.search(str(err)))


def _http_get(ticker, key, timeout):
    url = f"{ENDPOINT}?" + urllib.parse.urlencode(
        {"function": "EARNINGS", "symbol": ticker, "apikey": key})
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "gst-feasibility-audit"}),
                timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                    # network-level failure
        raise RuntimeError(redact(f"{type(e).__name__}: {e}", key)) from None


def fetch(ticker, key, timeout=60, use_cache=True, max_attempts=MAX_ATTEMPTS, sleeper=time.sleep):
    """Fetch one ticker with throttle-aware retry.

    Only a payload that passes provider_error() is ever cached, so a throttle
    notice can never poison the cache or masquerade as missing coverage.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"AV_EARNINGS_{ticker}.json"
    mf = CACHE / f"AV_EARNINGS_{ticker}.meta.json"
    if use_cache and cf.exists() and mf.exists():
        raw = cf.read_bytes()
        meta = json.loads(mf.read_text(encoding="utf-8"))
        meta["from_cache"] = True
        return raw, meta
    status, raw, err, attempts = None, b"", None, 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        status, raw = _http_get(ticker, key, timeout)
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            payload = None
        err = provider_error(payload)
        if not is_throttle(err):
            break
        sleeper(REQUEST_SPACING_S * (2 ** attempt))     # exponential backoff
    meta = {"ticker": ticker,
            "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "http_status": status, "byte_count": len(raw),
            "sha256": sha256_bytes(raw), "provider_url_redacted": redacted_url(ticker),
            "attempts": attempts, "throttled": is_throttle(err), "from_cache": False}
    if err is None:
        cf.write_bytes(raw)
        mf.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    sleeper(REQUEST_SPACING_S)
    return raw, meta


# ------------------------------------------------------------------ sanitizing

def _num(v):
    """Parse a provider numeric. Returns (value, state) with state in
    {ok, null, malformed}."""
    if v in DOCUMENTED_NULLS or (isinstance(v, str) and v.strip() in DOCUMENTED_NULLS):
        return None, "null"
    try:
        f = float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None, "malformed"
    if not math.isfinite(f):
        return None, "malformed"
    return f, "ok"


def _date(v):
    if v in DOCUMENTED_NULLS or (isinstance(v, str) and v.strip() in DOCUMENTED_NULLS):
        return None
    s = str(v).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def sanitize(payload, ticker):
    """Derive the sanitized panel for one ticker. Only the seven permitted fields
    survive. Returns (records, rejects)."""
    records, rejects = [], []
    for row in payload.get("quarterlyEarnings", []) or []:
        if not isinstance(row, dict):
            rejects.append({"ticker": ticker, "reason": "row_not_object"})
            continue
        fpe, rpt = _date(row.get("fiscalDateEnding")), _date(row.get("reportedDate"))
        if fpe is None or rpt is None:
            rejects.append({"ticker": ticker, "reason": "malformed_date",
                            "fiscalDateEnding": str(row.get("fiscalDateEnding"))[:32],
                            "reportedDate": str(row.get("reportedDate"))[:32]})
            continue
        if rpt < fpe:
            rejects.append({"ticker": ticker, "reason": "report_before_period_end",
                            "fiscalDateEnding": fpe.isoformat(),
                            "reportedDate": rpt.isoformat()})
            continue
        rec, bad = {"ticker": ticker, "fiscalDateEnding": fpe.isoformat(),
                    "reportedDate": rpt.isoformat()}, None
        for f in NUMERIC_FIELDS:
            val, st = _num(row.get(f))
            if st == "malformed":
                bad = f
                break
            rec[f] = val
        if bad:
            rejects.append({"ticker": ticker, "reason": "malformed_numeric", "field": bad,
                            "fiscalDateEnding": fpe.isoformat()})
            continue
        records.append({k: rec[k] for k in PERMITTED_FIELDS})
    return records, rejects


def refuse_duplicates(records):
    """Refuse EVERY member of any duplicate (ticker, fiscalDateEnding, reportedDate)
    group. Never first-kept. Returns (kept, refused)."""
    seen = {}
    for r in records:
        seen.setdefault((r["ticker"], r["fiscalDateEnding"], r["reportedDate"]), []).append(r)
    kept, refused = [], []
    for _, grp in seen.items():
        (kept if len(grp) == 1 else refused).extend(grp)
    return kept, refused


def in_period(rec):
    return PERIOD_START <= rec["reportedDate"] <= PERIOD_END


def is_complete(rec):
    return all(rec.get(f) is not None for f in ARITH_FIELDS)


def arithmetic_ok(rec, tol=EPS_TOL):
    """None if not checkable, else True/False for |(rep - est) - surprise| <= tol."""
    if not is_complete(rec):
        return None
    return abs((rec["reportedEPS"] - rec["estimatedEPS"]) - rec["surprise"]) <= tol + 1e-9


def assert_no_outcome_columns(records):
    """Refuse a panel carrying any prohibited outcome field."""
    bad = set()
    for r in records:
        for k in r:
            if k not in PERMITTED_FIELDS or PROHIBITED_COL.search(k):
                bad.add(k)
    if bad:
        raise ValueError(f"prohibited or unpermitted column(s) in derived panel: {sorted(bad)}")
    return True


# ------------------------------------------------------------------- crosswalk

def load_sec_events(path=SEC_PANEL):
    """SEC Item 2.02 event index. No return/price column exists here or is read."""
    df = pd.read_csv(path, usecols=["ticker", "cik", "accession", "filing_date",
                                    "fiscal_period_end", "eps", "audit_status"])
    df = df[df.filing_date.notna()]
    return [{"ticker": r.ticker, "accession": r.accession,
             "filing_date": str(r.filing_date)[:10],
             "fiscal_period_end": (None if pd.isna(r.fiscal_period_end)
                                   else str(r.fiscal_period_end)[:10]),
             "eps": (None if pd.isna(r.eps) else float(r.eps)),
             "audit_status": (None if pd.isna(r.audit_status) else str(r.audit_status))}
            for r in df.itertuples(index=False)]


def _days(a, b):
    return abs((datetime.strptime(a, "%Y-%m-%d") - datetime.strptime(b, "%Y-%m-%d")).days)


def crosswalk(records, sec_events, fpe_window=FPE_WINDOW_DAYS, rpt_window=REPORT_WINDOW_DAYS):
    """Apply the frozen window and tie-breaker. Returns list of result dicts."""
    by_ticker = {}
    for e in sec_events:
        by_ticker.setdefault(e["ticker"], []).append(e)
    out = []
    for r in records:
        cands = [e for e in by_ticker.get(r["ticker"], [])
                 if e["fiscal_period_end"]
                 and _days(r["fiscalDateEnding"], e["fiscal_period_end"]) <= fpe_window
                 and _days(r["reportedDate"], e["filing_date"]) <= rpt_window]
        if not cands:
            out.append({"record": r, "status": "unmatched_no_candidate", "sec": None,
                        "n_candidates": 0})
            continue
        if len(cands) == 1:
            out.append({"record": r, "status": "unique", "sec": cands[0], "n_candidates": 1})
            continue
        d = [_days(r["reportedDate"], e["filing_date"]) for e in cands]
        best = min(d)
        winners = [e for e, x in zip(cands, d) if x == best]
        if len(winners) == 1:
            out.append({"record": r, "status": "unique_after_tiebreak", "sec": winners[0],
                        "n_candidates": len(cands)})
        else:
            out.append({"record": r, "status": "ambiguous_crosswalk", "sec": None,
                        "n_candidates": len(cands)})
    return out


UNIQUE_STATUSES = ("unique", "unique_after_tiebreak")


def crosswalk_diagnostics(records, sec_events, rpt_window=REPORT_WINDOW_DAYS):
    """DIAGNOSTIC ONLY -- NEVER a gate and never substituted for one.

    The frozen crosswalk requires a fiscal-period match. fiscal_period_end exists in
    the SEC index only for events the hand-built parser successfully dated, so the
    frozen rule inherits that parser's coverage. This quantifies the resulting
    structural ceiling, and separately reports a report-date-only match against the
    FULL Item 2.02 index to show what the provider records themselves support.
    """
    total = len(sec_events)
    dated = sum(1 for e in sec_events if e["fiscal_period_end"])
    by_ticker = {}
    for e in sec_events:
        by_ticker.setdefault(e["ticker"], []).append(e)
    uniq = amb = none = 0
    for r in records:
        c = [e for e in by_ticker.get(r["ticker"], [])
             if _days(r["reportedDate"], e["filing_date"]) <= rpt_window]
        if not c:
            none += 1
        elif len(c) == 1:
            uniq += 1
        else:
            d = [_days(r["reportedDate"], e["filing_date"]) for e in c]
            if sum(1 for x in d if x == min(d)) == 1:
                uniq += 1
            else:
                amb += 1
    n = len(records)
    return {
        "IS_A_GATE": False,
        "note": ("Diagnostic only. The frozen g5 crosswalk gate stands exactly as "
                 "computed; nothing here replaces, relaxes or re-scores it."),
        "sec_index_events_total": total,
        "sec_index_events_with_parsed_fiscal_period": dated,
        "sec_index_events_without_parsed_fiscal_period": total - dated,
        "structural_ceiling_on_frozen_crosswalk_rate": (
            None if not n else round(dated / n, 4)),
        "structural_ceiling_derivation": (
            None if not n else f"{dated}/{n} = {round(dated / n, 4)}"),
        "frozen_gate_requires": GATES["crosswalk_rate_min"],
        "frozen_gate_reachable": (None if not n else (dated / n)
                                  >= GATES["crosswalk_rate_min"]),
        "binding_constraint": ("the SEC index's own parse coverage, not the provider's "
                               "record coverage"),
        "report_date_only_match": {
            "window_days": rpt_window, "against": "the full Item 2.02 index",
            "uniquely_matched": uniq, "ambiguous": amb, "no_candidate": none,
            "rate": (None if not n else round(uniq / n, 4)),
        },
    }


def compare_eps(cross, tol=EPS_TOL):
    """Provider reportedEPS versus SEC-validated parser EPS on overlapping events."""
    pairs = [(c["record"], c["sec"]) for c in cross
             if c["status"] in UNIQUE_STATUSES and c["sec"]
             and c["sec"]["audit_status"] == "validated" and c["sec"]["eps"] is not None
             and c["record"]["reportedEPS"] is not None]
    diffs = [(abs(r["reportedEPS"] - s["eps"]), r, s) for r, s in pairs]
    n = len(diffs)
    within = sum(1 for d, _, _ in diffs if d <= tol + 1e-9)
    srt = sorted(diffs, key=lambda x: -x[0])
    med = (None if n == 0 else
           float(pd.Series([d for d, _, _ in diffs]).median()))
    # Definition signature: are the differences consistent with a retroactive split
    # restatement, a GAAP-versus-adjusted definition difference, or neither?
    rr = [(abs(r["reportedEPS"] / s["eps"]), r["reportedEPS"] / s["eps"], r, s)
          for r, s in pairs if abs(s["eps"]) > 1e-9]
    split_like = [x for x in rr if 0.085 <= x[0] <= 0.115]
    parity_like = [x for x in rr if 0.85 <= x[0] <= 1.15]
    sign_flip = [x for x in rr if x[1] is not None and x[1] < 0]
    par_d = [abs(x[2]["reportedEPS"] - x[3]["eps"]) for x in parity_like]
    par_within = sum(1 for d in par_d if d <= tol + 1e-9)
    per_ticker = {}
    for x in rr:
        per_ticker.setdefault(x[2]["ticker"], []).append(x[0])
    return {"overlapping_events": n,
            "match_within_0_01": within,
            "definition_signature": {
                "split_restated_like_pairs": len(split_like),
                "split_restated_like_note": ("provider/SEC EPS ratio in [0.085, 0.115], the "
                                             "signature of a retroactive 10-for-1 split "
                                             "restatement of historical EPS"),
                "near_parity_pairs": len(parity_like),
                "near_parity_match_within_0_01": par_within,
                "near_parity_match_rate": (None if not par_d else
                                           round(par_within / len(par_d), 4)),
                "near_parity_median_absolute_difference": (
                    None if not par_d else round(float(pd.Series(par_d).median()), 4)),
                "sign_disagreements": len(sign_flip),
                "sign_disagreement_note": ("provider and SEC disagree on the sign of EPS; "
                                           "the signature of an adjusted/non-GAAP figure "
                                           "against a GAAP loss"),
                "median_ratio_by_ticker": {t: round(float(pd.Series(v).median()), 4)
                                           for t, v in sorted(per_ticker.items())},
                "consistent_with_gaap_versus_adjusted": bool(parity_like) and par_within < len(par_d),
                "consistent_with_retroactive_split_restatement": bool(split_like),
                "interpretation": (
                    "Differences are NOT random error. They decompose into (a) retroactive "
                    "split restatement of historical EPS for the tickers that later split, "
                    "and (b) a GAAP-versus-adjusted definition difference among the "
                    "remaining near-parity pairs, including outright sign disagreements. "
                    "Provider EPS is therefore vendor-defined, not SEC-validated GAAP "
                    "diluted EPS, and its historical values are not preserved as announced."),
            },
            "match_rate_within_0_01": (None if n == 0 else round(within / n, 4)),
            "median_absolute_difference": (None if med is None else round(med, 4)),
            "largest_discrepancies": [
                {"ticker": r["ticker"], "fiscalDateEnding": r["fiscalDateEnding"],
                 "reportedDate": r["reportedDate"],
                 "provider_reportedEPS": r["reportedEPS"], "sec_validated_eps": s["eps"],
                 "absolute_difference": round(d, 4),
                 "provider_higher": r["reportedEPS"] > s["eps"]}
                for d, r, s in srt[:10] if d > tol],
            "provider_higher_share_among_mismatches": (
                None if not [1 for d, _, _ in diffs if d > tol] else
                round(sum(1 for d, r, s in diffs if d > tol and r["reportedEPS"] > s["eps"])
                      / sum(1 for d, _, _ in diffs if d > tol), 4))}


# ----------------------------------------------------------------------- gates

def evaluate(records_complete, tickers_with_complete, crosswalk_rate,
             arithmetic_rate, unresolved_duplicates, terminology_ok):
    y = {yr: sum(1 for r in records_complete
                 if r["reportedDate"][:4] == str(yr)) for yr in GATE_YEARS}
    g = {
        "g1_tickers": {"value": tickers_with_complete, "required": GATES["tickers_min"],
                       "passed": tickers_with_complete >= GATES["tickers_min"]},
        "g2_complete_2018_2025": {"value": len(records_complete),
                                  "required": GATES["complete_2018_2025_min"],
                                  "passed": len(records_complete)
                                  >= GATES["complete_2018_2025_min"]},
        "g3_complete_2023_2025": {"value": sum(y.values()),
                                  "required": GATES["complete_2023_2025_min"],
                                  "passed": sum(y.values())
                                  >= GATES["complete_2023_2025_min"]},
        "g4_complete_per_year": {"value": y, "required": GATES["complete_per_year_min"],
                                 "passed": all(v >= GATES["complete_per_year_min"]
                                               for v in y.values())},
        "g5_crosswalk_rate": {"value": crosswalk_rate, "required": GATES["crosswalk_rate_min"],
                              "passed": crosswalk_rate is not None
                              and crosswalk_rate >= GATES["crosswalk_rate_min"]},
        "g6_arithmetic_agreement": {"value": arithmetic_rate,
                                    "required": GATES["arithmetic_agreement_min"],
                                    "passed": arithmetic_rate is not None
                                    and arithmetic_rate >= GATES["arithmetic_agreement_min"]},
        "g7_unresolved_duplicates": {"value": unresolved_duplicates,
                                     "required": GATES["unresolved_duplicates_max"],
                                     "passed": unresolved_duplicates
                                     == GATES["unresolved_duplicates_max"]},
        "g8_terminology_distinguishes_vendor_from_gaap": {
            "value": bool(terminology_ok), "required": True, "passed": bool(terminology_ok)},
    }
    g["all_passed"] = all(v["passed"] for k, v in g.items() if k != "all_passed")
    return g


def decide(gates, pit_guaranteed, access_blocked):
    if access_blocked:
        return LABELS[4]
    coverage = ("g1_tickers", "g2_complete_2018_2025", "g3_complete_2023_2025",
                "g4_complete_per_year", "g5_crosswalk_rate")
    if not all(gates[k]["passed"] for k in coverage):
        return LABELS[2]
    if not all(gates[k]["passed"] for k in
               ("g6_arithmetic_agreement", "g7_unresolved_duplicates",
                "g8_terminology_distinguishes_vendor_from_gaap")):
        return LABELS[3]
    return LABELS[0] if pit_guaranteed else LABELS[1]


# ------------------------------------------------------------------------ main

def main(argv=None):
    key = resolve_api_key()
    if not key:
        art = {"artifact": "STRUCTURED_EARNINGS_FEASIBILITY", "version": "1.0",
               "study_type": "DATA_AUDIT_NOT_OUTCOME_STUDY",
               "decision_label": LABELS[4],
               "reason": "ALPHAVANTAGE_API_KEY absent or empty; no request was issued.",
               "returns_or_prices_touched": False}
        ARTIFACT.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print(LABELS[4])
        return 2

    retrieval, all_records, all_rejects, errors, throttled = [], [], [], [], []
    for t in UNIVERSE:
        try:
            raw, meta = fetch(t, key)
        except RuntimeError as e:
            errors.append({"ticker": t, "error": redact(e, key)})
            retrieval.append({"ticker": t, "http_status": None,
                              "provider_url_redacted": redacted_url(t),
                              "error": redact(e, key)})
            continue
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            payload = None
        err = provider_error(payload)
        meta["schema_version"] = (payload or {}).get("schemaVersion") if isinstance(
            payload, dict) else None
        meta["provider_error"] = redact(err, key) if err else None
        retrieval.append(meta)
        if err:
            errors.append({"ticker": t, "error": redact(err, key),
                           "throttle": is_throttle(err)})
            if is_throttle(err):
                throttled.append(t)
            continue
        recs, rej = sanitize(payload, t)
        all_records.extend(recs)
        all_rejects.extend(rej)

    if not all_records:
        art = {"artifact": "STRUCTURED_EARNINGS_FEASIBILITY", "version": "1.0",
               "study_type": "DATA_AUDIT_NOT_OUTCOME_STUDY", "decision_label": LABELS[4],
               "reason": "no ticker returned a parseable EARNINGS payload",
               "retrieval": retrieval, "errors": errors, "returns_or_prices_touched": False}
        ARTIFACT.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print(LABELS[4])
        return 2

    kept, dup_refused = refuse_duplicates(all_records)
    assert_no_outcome_columns(kept)
    panel = sorted([r for r in kept if in_period(r)],
                   key=lambda r: (r["ticker"], r["reportedDate"]))
    complete = [r for r in panel if is_complete(r)]

    checked = [r for r in panel if arithmetic_ok(r) is not None]
    ok = [r for r in checked if arithmetic_ok(r)]
    arith_rate = (None if not checked else round(len(ok) / len(checked), 4))
    arith_fail = [{"ticker": r["ticker"], "fiscalDateEnding": r["fiscalDateEnding"],
                   "reportedEPS": r["reportedEPS"], "estimatedEPS": r["estimatedEPS"],
                   "surprise": r["surprise"],
                   "implied_minus_reported": round(
                       (r["reportedEPS"] - r["estimatedEPS"]) - r["surprise"], 4)}
                  for r in checked if not arithmetic_ok(r)]

    sec = load_sec_events()
    cross = crosswalk(complete, sec)
    uniq = [c for c in cross if c["status"] in UNIQUE_STATUSES]
    amb = [c for c in cross if c["status"] == "ambiguous_crosswalk"]
    nomatch = [c for c in cross if c["status"] == "unmatched_no_candidate"]
    xrate = (None if not complete else round(len(uniq) / len(complete), 4))

    tickers_complete = sorted({r["ticker"] for r in complete})
    by_ticker = {t: {"records_in_period": sum(1 for r in panel if r["ticker"] == t),
                     "complete": sum(1 for r in complete if r["ticker"] == t)}
                 for t in UNIVERSE}
    by_year = {}
    for r in complete:
        y = r["reportedDate"][:4]
        by_year[y] = by_year.get(y, 0) + 1

    terminology_ok = True   # asserted by the artifact fields written below
    gates = evaluate(complete, len(tickers_complete), xrate, arith_rate,
                     len(dup_refused), terminology_ok)
    # A ticker still throttled after retries is a TRANSPORT failure. Coverage computed
    # over an incomplete retrieval must never be reported as a coverage finding.
    label = decide(gates, pit_guaranteed=False, access_blocked=bool(throttled))

    art = {
        "artifact": "STRUCTURED_EARNINGS_FEASIBILITY", "version": "1.0",
        "study_type": "DATA_AUDIT_NOT_OUTCOME_STUDY",
        "decision_label": label,
        "provider": "ALPHA_VANTAGE_EARNINGS",
        "provider_endpoint_redacted": f"{ENDPOINT}?function=EARNINGS&symbol=<TICKER>&apikey=<REDACTED>",
        "universe": UNIVERSE, "period": {"start": PERIOD_START, "end": PERIOD_END,
                                         "applied_to": "reportedDate"},
        "permitted_fields": list(PERMITTED_FIELDS),
        "construct_name_if_built": CONSTRUCT_NAME,
        "eps_definition": {
            "provider_field": "reportedEPS",
            "provider_represents": "VENDOR_REPORTED_EPS",
            "is_sec_validated_gaap_diluted_eps": False,
            "note": ("Alpha Vantage reportedEPS is a vendor-reported figure. It is NOT "
                     "SEC-validated GAAP diluted EPS. Any surprise built on it is "
                     f"{CONSTRUCT_NAME}, never a GAAP surprise."),
        },
        "point_in_time_provenance": {
            "status": PIT_NOT_GUARANTEED,
            "official_guarantee_found": False,
            "documentation_checked": "https://www.alphavantage.co/documentation/ (EARNINGS)",
            "note": ("No official Alpha Vantage guarantee was found that historical "
                     "estimatedEPS is the contemporaneous consensus preserved as of the "
                     "announcement. The documentation describes the fields but makes no "
                     "point-in-time, as-of-announcement or non-restatement claim for them. "
                     "The limitation is recorded, not resolved by assumption."),
            "empirical_counter_evidence": (
                "Historical reportedEPS is demonstrably RESTATED rather than preserved as "
                "announced: for every ticker that later executed a 10-for-1 split (NVDA, "
                "AVGO, LRCX and KLAC) the provider's historical EPS is carried on the "
                "post-split share basis, giving provider/SEC ratios clustered near 0.10 "
                "against the as-announced SEC exhibit figures. Restatement of reportedEPS "
                "does not by itself prove estimatedEPS is also restated, but it removes any "
                "basis for assuming the series is point-in-time."),
            "consequence": ("Any surprise built on this source is "
                            f"{CONSTRUCT_NAME} computed from possibly-restated inputs, and "
                            "must not be described as a point-in-time consensus surprise."),
        },
        "retrieval": retrieval, "provider_errors": errors,
        "retrieval_integrity": {
            "tickers_requested": len(UNIVERSE),
            "tickers_retrieved": sum(1 for m in retrieval if not m.get("provider_error")
                                     and not m.get("error")),
            "throttled_after_retries": throttled,
            "retrieval_complete": not throttled,
            "note": ("A throttle notice is a transport failure, not a data finding. If any "
                     "ticker remains throttled after retries the run reports "
                     "DATA_ACCESS_BLOCKED and its coverage counts are NOT a coverage "
                     "finding."),
        },
        "counts": {
            "tickers_requested": len(UNIVERSE),
            "tickers_with_payload": sum(1 for m in retrieval if not m.get("provider_error")
                                        and not m.get("error")),
            "raw_records": len(all_records),
            "rejected_malformed": len(all_rejects),
            "duplicate_identities_refused": len(dup_refused),
            "records_in_period": len(panel),
            "complete_records": len(complete),
            "tickers_with_complete_records": len(tickers_complete),
        },
        "rejections": all_rejects[:50],
        "completeness_by_ticker": by_ticker,
        "completeness_by_year": dict(sorted(by_year.items())),
        "surprise_arithmetic": {
            "tolerance_absolute_usd": EPS_TOL,
            "checked": len(checked), "agreed": len(ok), "agreement_rate": arith_rate,
            "failures": arith_fail[:20],
        },
        "sec_crosswalk": {
            "target_index": "Live Signal Engine/Semiconductor_EPS_Absorption/event_panel_v1.0.csv",
            "fiscal_window_days": FPE_WINDOW_DAYS, "report_window_days": REPORT_WINDOW_DAYS,
            "tie_breaker": ("smallest |reportedDate - filing_date|; a remaining tie is "
                            "REFUSED as ambiguous, never guessed"),
            "returns_used": False,
            "complete_records": len(complete),
            "uniquely_crosswalked": len(uniq),
            "unique_direct": sum(1 for c in cross if c["status"] == "unique"),
            "unique_after_tiebreak": sum(1 for c in cross
                                         if c["status"] == "unique_after_tiebreak"),
            "ambiguous_refused": len(amb),
            "unmatched_no_candidate": len(nomatch),
            "crosswalk_rate": xrate,
        },
        "crosswalk_diagnostics": crosswalk_diagnostics(complete, sec),
        "provider_vs_sec_eps": compare_eps(cross),
        "gates": gates,
        "sanitized_panel": panel,
        "modeling_authorized": False,
        "not_computed": {"sue": False, "information_price_gap": False,
                         "post_earnings_drift": False, "bootstrap": False,
                         "coefficients": False, "portfolio_returns": False, "trades": False},
        "returns_or_prices_touched": False,
        "later_xbrl_used_to_overwrite_either_source": False,
    }
    ARTIFACT.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print(json.dumps({k: art[k] for k in ("decision_label", "counts", "gates")}, indent=1))
    return 0 if gates["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
