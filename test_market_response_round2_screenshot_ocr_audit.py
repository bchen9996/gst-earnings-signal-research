#!/usr/bin/env python3
# Deterministic tests for the round-2 screenshot OCR audit and its narrowed
# false-positive adjudication rule.
#
# Offline. No socket, no OCR at test time, no image opened. The tests validate
# the committed audit artifact and re-derive dispositions from the recorded rule
# names, plus synthetic text fixtures exercising the adjudication rule directly.
#
# Run directly: python test_market_response_round2_screenshot_ocr_audit.py

from __future__ import annotations

import hashlib
import json
import re
import socket
import sys
from pathlib import Path


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

ROOT = Path(__file__).resolve().parent
R2 = ROOT / "Live Signal Engine" / "Cohort_Screening_Round2"
AUDIT = R2 / "SCREENSHOT_OCR_AUDIT_ROUND2.json"
SHOTS = R2 / "screenshots"
MANIFEST = R2 / "SWEEP_MANIFEST_ROUND2.json"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


# --- the adjudication rule, mirrored for fixture testing ---------------------
WINDOW = 220
VALUE_RULES = [
    ("price_label_value", re.compile(r"\bprice\b\D{0,25}\$?\d{1,6}[.,]\d{2}", re.I)),
    ("volume_label_value", re.compile(r"\bvolume\b\D{0,25}[\d,]{4,}", re.I)),
    ("signed_percent", re.compile(r"[+\-−↑↓▲▼]\s?\d{1,3}[.,]\d{1,2}\s?%")),
    ("dollar_value", re.compile(r"\$\s?\d{1,6}[.,]\d{2}\b")),
    ("exchange_ticker_pair", re.compile(r"\b(NYSE|NASDAQ|CBOE|AMEX)\b\s*[:\s]\s*[A-Z][A-Z.\-]{0,5}\b")),
]
ATTRIBUTION_RULES = [
    ("data_provided_by_provider", re.compile(
        r"data\s+(provided|supplied)\s+by\s+\W{0,3}(q4|nasdaq|nyse|refinitiv|factset|xignite|"
        r"quotemedia|barchart|morningstar|thomson|bloomberg|six|edgar\s*online|interactive\s*data)", re.I)),
]
POPULATED_FIELD_RULES = [
    ("populated_quote_field", re.compile(
        r"(stock\s*quote|last\s*price|previous\s*close|day'?s?\s*range|52[\s\-]*week)\s*[:\-]?\s*\$?\d", re.I)),
]
STRUCTURE_RULES = [
    ("quote_widget_word", re.compile(r"\bstock\s*(quote|information)\b", re.I)),
]
CORROBORATORS = VALUE_RULES + ATTRIBUTION_RULES + POPULATED_FIELD_RULES


def adjudicate(text: str) -> str:
    if any(r.search(text) for _, r in CORROBORATORS if True) and (
            [n for n, r in VALUE_RULES if r.search(text)]
            or [n for n, r in ATTRIBUTION_RULES if r.search(text)]
            or [n for n, r in POPULATED_FIELD_RULES if r.search(text)]):
        return "OCR_PROHIBITED_CONTENT_DETECTED"
    stru = [n for n, r in STRUCTURE_RULES if r.search(text)]
    for name, rx in STRUCTURE_RULES:
        if name not in stru:
            continue
        for m in rx.finditer(text):
            region = text[max(0, m.start() - WINDOW):min(len(text), m.end() + WINDOW)]
            if any(p.search(region) for _, p in CORROBORATORS):
                return "OCR_PROHIBITED_CONTENT_DETECTED"
    return "OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH" if stru else "OCR_CLEAN"


# --- synthetic fixtures -------------------------------------------------------
# Deliberately fabricated strings. Not project data, not from any screenshot.
FIX_STRUCTURE_ONLY = ("Berkshire Hathaway Inc. Official Home Page. Annual Reports. "
                      "Common Stock Information. Corporate Governance. Sustainability.")
FIX_STRUCTURE_PLUS_PRICE = "Stock Quote NYSE ABC Price $123.45 as of today"
FIX_STRUCTURE_PLUS_VOLUME = "Stock Information Volume: 1,234,567 shares traded"
FIX_STRUCTURE_PLUS_ATTRIB = "Stock Information. Data provided by Q4 Inc. All rights reserved."


def test_1_fixtures() -> None:
    check("1a. structure-only fixture -> advisory (clean for merge gate)",
          adjudicate(FIX_STRUCTURE_ONLY) == "OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH",
          adjudicate(FIX_STRUCTURE_ONLY))
    check("1b. structure + price fixture -> prohibited",
          adjudicate(FIX_STRUCTURE_PLUS_PRICE) == "OCR_PROHIBITED_CONTENT_DETECTED")
    check("1c. structure + volume fixture -> prohibited",
          adjudicate(FIX_STRUCTURE_PLUS_VOLUME) == "OCR_PROHIBITED_CONTENT_DETECTED")
    check("1d. structure + attribution fixture -> prohibited",
          adjudicate(FIX_STRUCTURE_PLUS_ATTRIB) == "OCR_PROHIBITED_CONTENT_DETECTED")
    check("1e. plain text with no structure -> clean",
          adjudicate("Investor Relations. Annual Meeting Information. SEC Filings.") == "OCR_CLEAN")


def test_2_coverage_and_hashes() -> None:
    A = json.loads(AUDIT.read_text(encoding="utf-8"))
    recs = A["records"]
    names = [r["screenshot"] for r in recs]
    on_disk = sorted(p.name for p in SHOTS.glob("*.png"))
    check(f"2a. every committed screenshot represented exactly once ({len(on_disk)})",
          sorted(names) == on_disk and len(names) == len(set(names)))
    check("2b. audit count matches disk", A["screenshot_count"] == len(on_disk))
    bad = []
    for r in recs:
        p = SHOTS / r["screenshot"]
        if hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            bad.append(r["screenshot"])
    check(f"2c. every recorded SHA-256 ties out to the committed image (mismatches={bad})", not bad)
    check("2d. CTSH screenshot included",
          any("CTSH" in n for n in names))
    check("2e. MSFT screenshot included",
          any("MSFT" in n for n in names))


def test_3_dispositions() -> None:
    A = json.loads(AUDIT.read_text(encoding="utf-8"))
    recs = A["records"]
    valid = {"OCR_CLEAN", "OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH",
             "OCR_PROHIBITED_CONTENT_DETECTED", "OCR_UNVERIFIABLE"}
    check("3a. every disposition is one of the four defined values",
          all(r["disposition"] in valid for r in recs))
    check("3b. zero prohibited", A["prohibited_count"] == 0)
    check("3c. zero unverifiable", A["unverifiable_count"] == 0)
    check("3d. totals reconcile to the record count",
          A["clean_count"] + A["clean_with_advisory_count"] + A["prohibited_count"]
          + A["unverifiable_count"] == A["screenshot_count"] == len(recs))
    # re-derive each disposition from the RECORDED rule names
    for r in recs:
        corro = (r["value_rules_triggered"] or r["attribution_rules_triggered"]
                 or r["populated_field_rules_triggered"]
                 or any(r.get("structural_corroborated", {}).values()))
        expect = ("OCR_PROHIBITED_CONTENT_DETECTED" if corro
                  else ("OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH" if r["structural_rules_triggered"]
                        else "OCR_CLEAN"))
        if r["ocr_success"] and r["recognized_token_count"] >= 5:
            check(f"3e. {r['screenshot']} disposition re-derives from its recorded rules",
                  r["disposition"] == expect, f"{r['disposition']} vs {expect}")


def test_4_ctsh_msft_and_brkb() -> None:
    A = json.loads(AUDIT.read_text(encoding="utf-8"))
    by = {r["screenshot"]: r for r in A["records"]}
    for tag in ("s1_1__CTSH__2.png", "s1_1__MSFT__4.png"):
        r = by.get(tag)
        check(f"4a. {tag} present and OCR_CLEAN", bool(r) and r["disposition"] == "OCR_CLEAN",
              r["disposition"] if r else "missing")
        check(f"4b. {tag} OCR succeeded with engine-sourced tokens",
              bool(r) and r["ocr_success"] and r["recognized_token_count"] > 0
              and "engine" in r["token_count_source"].lower())
    b = by.get("s1_2_fallback__BRK_B__14.png")
    check("4c. BRK-B present", bool(b))
    check("4d. BRK-B is advisory, not prohibited",
          b["disposition"] == "OCR_CLEAN_WITH_ADVISORY_STRUCTURE_MATCH", b["disposition"])
    check("4e. BRK-B preserves the original structural rule name",
          "quote_widget_word" in b["structural_rules_triggered"])
    check("4f. BRK-B has zero value corroborators", b["value_rules_triggered"] == [])
    check("4g. BRK-B has zero attribution corroborators", b["attribution_rules_triggered"] == [])
    check("4h. BRK-B has zero populated-quote-field corroborators", b["populated_field_rules_triggered"] == [])
    check("4i. BRK-B structural match explicitly uncorroborated",
          b["structural_corroborated"].get("quote_widget_word") is False)
    check("4j. determinism recorded across three runs",
          A["runs_performed"] >= 3 and A["runs_identical"] is True)


def test_5_no_text_or_values_persisted() -> None:
    A = json.loads(AUDIT.read_text(encoding="utf-8"))
    allowed = {"screenshot", "sha256", "width", "height", "ocr_engine", "ocr_engine_language",
               "processing_method", "tiles_processed", "ocr_success", "recognized_token_count",
               "recognized_line_count", "token_count_source", "value_rules_triggered",
               "attribution_rules_triggered", "populated_field_rules_triggered",
               "structural_rules_triggered", "structural_corroborated", "disposition"}
    extra = sorted({k for r in A["records"] for k in r} - allowed)
    check(f"5a. records carry only sanitized fields (extra={extra})", not extra)
    check("5b. artifact declares no OCR text persisted", A["ocr_text_persisted"] is False)
    check("5c. artifact declares no matched values recorded",
          A["matched_values_recorded"] is False and A.get("matched_numeric_substrings_recorded") is False)
    check("5d. no screenshot was manually viewed", A["screenshots_manually_viewed"] == 0)
    blob = json.dumps(A)
    check("5e. no monetary/decimal market value appears anywhere in the artifact",
          re.search(r"\d+\.\d{2}\b", blob) is None)
    check("5f. no percentage value appears anywhere in the artifact",
          re.search(r"\d+\.\d+\s?%", blob) is None)
    for k in ("ocr_text", "recognized_text", "matched_text", "snippet", "context", "excerpt"):
        check(f"5g. no '{k}' field persisted", f'"{k}"' not in blob)


def test_6_manifest_and_limits() -> None:
    M = json.loads(MANIFEST.read_text(encoding="utf-8"))
    s = M.get("screenshot_ocr_audit", {})
    check("6a. manifest references the OCR audit artifact",
          s.get("artifact", "").endswith("SCREENSHOT_OCR_AUDIT_ROUND2.json"))
    check("6b. manifest states the four totals separately",
          all(k in s for k in ("plain_ocr_clean", "ocr_clean_with_advisory_structure_match",
                               "prohibited", "unverifiable")))
    check("6c. 'verified by construction only' replaced",
          "construction only" not in M["pre_extraction_scan"]["screenshot_verification"])
    check("6d. manifest names the OCR engine",
          "Windows.Media.Ocr" in M["pre_extraction_scan"]["screenshot_verification"])
    check("6e. manifest states OCR does not eliminate recognition error",
          "does not eliminate" in s.get("limitation", "").lower()
          or "does not eliminate" in M["pre_extraction_scan"]["screenshot_verification"].lower())
    check("6f. provenance limitation preserved for CTSH and MSFT",
          "CTSH" in s.get("provenance_limitation", "") and "MSFT" in s.get("provenance_limitation", "")
          and "permanently unavailable" in s.get("provenance_limitation", ""))
    check("6g. BRK-B screening classification unchanged",
          [r for r in M["rows"] if r["ticker"] == "BRK-B"][0]["outcome"] == "NO_ENROLLMENT_DECISION_REACHED")
    dist = M["outcome_distribution"]
    check("6h. round-two classification totals untouched (16/4/2/2)",
          dist.get("ACCESS_FAILED") == 16 and dist.get("ISSUER_STATED_ABSENCE_CONFIRMED") == 4
          and dist.get("COMPROMISED_ENROLLMENT_BLINDING") == 2
          and dist.get("NO_ENROLLMENT_DECISION_REACHED") == 2)


if __name__ == "__main__":
    test_1_fixtures()
    test_2_coverage_and_hashes()
    test_3_dispositions()
    test_4_ctsh_msft_and_brkb()
    test_5_no_text_or_values_persisted()
    test_6_manifest_and_limits()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL ROUND-2 SCREENSHOT OCR AUDIT TESTS PASSED")
    sys.exit(0)
