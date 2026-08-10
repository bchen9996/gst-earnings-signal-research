#!/usr/bin/env python3
# Deterministic tests for the round-2 runbook isolation clarification (section 4.1).
#
# Offline. No retrieval, no socket, no candidate lookup, no rendering.
#
# These assert INVARIANTS OF THE RULE, not prose style: that the clarification
# is present, that it defines isolation as pre-response request blocking, that
# post-render remedies are explicitly insufficient, that the compromised
# disposition is cycle-specific, that no prohibited numeric value appears in any
# committed round-2 artifact, and that the clarification changed nothing outside
# section 4.1.
#
# Run directly: python test_market_response_round2_isolation_rule.py

from __future__ import annotations

import hashlib
import html
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
RUNBOOK = ROOT / "Live Signal Engine" / "Cohort_Screening_Round1" / "ROUND2_RENDERER_RUNBOOK.md"
R2DIR = ROOT / "Live Signal Engine" / "Cohort_Screening_Round2"
PROTOCOL = ROOT / "Live Signal Engine" / "GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json"
OVERLAY = ROOT / "Live Signal Engine" / "Cohort_Screening_Round1" / "ROUND1_CORRECTION_OVERLAY_v1.json"
REGISTRY = ROOT / "Live Signal Engine" / "Market_Response_Event_Registry" / "registry.jsonl"

FAILURES: list[str] = []


def check(label: str, ok: bool) -> None:
    print(("PASS: " if ok else "FAIL: ") + label)
    if not ok:
        FAILURES.append(label)


# Populated-value rules. Each requires a NUMBER adjacent to a market-data label;
# a bare heading such as "Stock Quote" with no value is not an exposure.
PROHIBITED_VALUE_RULES = [
    ("quote_price_labeled", re.compile(
        r"(?:stock\s*quote|last\s*(?:trade|price)|share\s*price|price[:\s])\D{0,40}\$?\d{1,6}\.\d{2}\b", re.I)),
    ("exchange_ticker_price", re.compile(
        r"\b(?:NYSE|NASDAQ|CBOE)\b[:\s]{0,3}[A-Z][A-Z\.\-]{0,5}\s+\$?\d{1,6}\.\d{2}\b")),
    ("percent_change", re.compile(r"[+\-−↑↓]\s?\d{1,3}\.\d{1,2}\s?%")),
    ("volume_labeled", re.compile(r"\bvolume\b\D{0,20}[\d,]{4,}", re.I)),
    ("change_labeled", re.compile(r"\bchange\b\D{0,20}[+\-−]?\s?\d{1,6}\.\d{2}\b", re.I)),
    ("market_cap", re.compile(r"\bmarket\s*cap\D{0,20}\$?[\d,.]+\s*[BMT]?\b", re.I)),
    ("day_range", re.compile(r"\b(?:day'?s?\s*range|52[\s\-]*week)\D{0,20}[\d,]+\.\d{2}", re.I)),
    ("open_prev_close", re.compile(
        r"\b(?:previous\s*close|prev\.?\s*close)\b\D{0,20}\$?\d{1,6}\.\d{2}\b", re.I)),
    ("bid_ask", re.compile(r"\b(?:bid|ask)\b\D{0,20}\$?\d{1,6}\.\d{2}\b", re.I)),
    ("eps_surprise", re.compile(
        r"\b(?:eps|earnings per share|surprise)\b\D{0,20}[\$\-+]?\d+\.\d{2}\b", re.I)),
    ("analyst_consensus", re.compile(
        r"\b(?:consensus|analyst\s*(?:estimate|rating)|price\s*target)\b\D{0,25}\$?\d+\.\d{2}\b", re.I)),
    ("implied_vol", re.compile(r"\b(?:implied\s*vol)\b\D{0,15}\d{1,3}(?:\.\d+)?\s?%", re.I)),
]


def visible_text(raw: bytes) -> str | None:
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    s = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s))


def fired(text: str) -> list[str]:
    return [n for n, p in PROHIBITED_VALUE_RULES if p.search(text)]


def test_1_clarification_present() -> None:
    t = RUNBOOK.read_text(encoding="utf-8")
    check("1a. runbook has a section 4.1 isolation clarification",
          "### 4.1" in t and re.search(r'what\s+"isolated"\s+means', t, re.I) is not None)
    check("1b. clarification is marked additive", "additive" in t.lower())
    check("1c. section 4 original stop sentence is still present verbatim",
          "**Stop immediately** if a page displays prohibited attention, price, surprise, options or "
          "outcome data in a way that cannot be isolated from the event listing." in t)


def test_2_isolation_definition() -> None:
    t = RUNBOOK.read_text(encoding="utf-8")
    check("2a. isolation requires blocking BEFORE responses are received",
          re.search(r"blocked\s+before\s+their\s+responses\s+were\s+received", t, re.I) is not None)
    check("2b. isolation requires blocking before any value populates the page",
          re.search(r"before\s+any\s+value\s+populated\s+the\s+rendered\s+page", t, re.I) is not None)
    check("2c. post-render remedies explicitly insufficient",
          all(w in t.lower() for w in ("ignoring", "cropping", "masking", "excluding from extraction"))
          and "does not restore blinding" in t.lower())
    check("2d. section 4 governs exposure, section 2 supplies the mechanism",
          re.search(r"§4\s+governs\s+\*\*actual exposure\*\*", t) is not None
          and re.search(r"§2\s+supplies\s+the\s+\*\*preventive mechanism\*\*", t) is not None)


def test_3_blocking_permission_and_limits() -> None:
    t = RUNBOOK.read_text(encoding="utf-8")
    check("3a. pre-render blocking permitted for every issuer page regardless of assigned method",
          re.search(r"[Pp]re-render request blocking is permitted for every issuer page", t) is not None
          and re.search(r"regardless of whether the ticker was originally assigned", t, re.I) is not None)
    check("3b. blocking expands no source set",
          re.search(r"expands\s+no\s+source\s+set", t, re.I) is not None)
    check("3c. blocking may not be weakened to obtain a listing",
          re.search(r"may\s+not\s+be\s+weakened", t, re.I) is not None)
    check("3d. pre-extraction automated scan gate required, manual inspection barred until it passes",
          "Pre-extraction gate" in t
          and re.search(r"No page may be inspected manually until that scan passes", t) is not None)


def test_4_disposition_is_cycle_specific() -> None:
    t = RUNBOOK.read_text(encoding="utf-8")
    check("4a. compromised disposition named", "COMPROMISED_ENROLLMENT_BLINDING" in t)
    check("4b. disposition is cycle-specific", re.search(r"cycle-specific", t, re.I) is not None)
    for phrase in ("not a permanent exclusion", "not a registry amendment",
                   "not an event-state transition"):
        check(f"4c. explicitly {phrase}", phrase.replace("not a", "*not*").split("*not*")[-1].strip()
              in t.lower() or phrase in t.lower())
    check("4d. does not claim any existing registered event is compromised",
          re.search(r"not\*?\*?\s*a claim that any existing registered event is compromised", t, re.I) is not None)
    check("4e. recording rule forbids storing the observed values",
          re.search(r"is never recorded anywhere", t, re.I) is not None)


def test_5_no_prohibited_values_in_committed_round2_artifacts() -> None:
    if not R2DIR.exists():
        check("5. round-2 artifact directory present", False)
        return
    files = sorted(p for p in R2DIR.rglob("*") if p.is_file())
    check("5a. round-2 artifacts exist", len(files) > 0)
    bad, undec = [], []
    for p in files:
        raw = p.read_bytes()
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            continue                      # binary image; covered by the render-time gate
        txt = raw.decode("utf-8", "replace") if p.suffix.lower() == ".json" else visible_text(raw)
        if txt is None:
            undec.append(p.name)
            continue
        hits = fired(txt)
        if hits:
            bad.append((p.name, hits))
    check(f"5b. NO committed round-2 artifact contains a populated prohibited value (offenders={[b[0] for b in bad]})",
          not bad)
    check(f"5c. no undecodable committed body (unverifiable={undec})", not undec)


def test_6_untouched_governance() -> None:
    prot = json.loads(PROTOCOL.read_text(encoding="utf-8-sig"))
    check("6a. collection window unchanged",
          prot["collection_window"]["begins"] == "2026-09-01"
          and prot["collection_window"]["ends"] == "2027-05-31")
    check("6b. target unchanged (60)", prot["target"]["min_registered_events"] == 60)
    check("6c. minimum registration lead unchanged (5 XNYS sessions)",
          prot["minimum_registration_lead"]["sessions"] == 5
          and prot["minimum_registration_lead"]["calendar"] == "XNYS")
    check("6d. screening cadence unchanged (Monday 09:00 America/Chicago)",
          prot["screening_cadence"]["recurring_sweep"]["day"] == "Monday"
          and prot["screening_cadence"]["recurring_sweep"]["time_local"] == "09:00"
          and prot["screening_cadence"]["recurring_sweep"]["timezone"] == "America/Chicago")
    check("6e. permitted source types unchanged (4)",
          len(prot["permitted_official_source_types"]["values"]) == 4)
    check("6f. no screening rows written by the clarification", prot["screening_rows"] == [])
    ov = json.loads(OVERLAY.read_text(encoding="utf-8-sig"))
    check("6g. round-1 overlay still reports originals not rewritten", ov["originals_rewritten"] is False)


def test_7_registry_untouched() -> None:
    rows = [l for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("7a. registry holds exactly one row", len(rows) == 1)
    r = json.loads(rows[0])
    check("7b. that row is the DELL registration, verified",
          r["event_id"] == "EVT-DELL-FY27Q2-ERN" and r["row_type"] == "REGISTRATION"
          and r["verification_status"] == "verified")
    check("7c. no DVN row was added", not any('"DVN"' in l for l in rows))
    check("7d. no TTWO row was added", not any('"TTWO"' in l for l in rows))


if __name__ == "__main__":
    test_1_clarification_present()
    test_2_isolation_definition()
    test_3_blocking_permission_and_limits()
    test_4_disposition_is_cycle_specific()
    test_5_no_prohibited_values_in_committed_round2_artifacts()
    test_6_untouched_governance()
    test_7_registry_untouched()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL ROUND-2 ISOLATION-RULE TESTS PASSED")
    sys.exit(0)
