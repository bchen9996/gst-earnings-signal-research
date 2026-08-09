#!/usr/bin/env python3
"""Build ROUND1_CORRECTION_OVERLAY_v1.json from the PRESERVED round-1 evidence.

Offline. Reads the original artifacts, hashes them, and emits an additive
correction layer. The originals are never rewritten -- they record what the
first retrieval actually did, mistakes included, and the overlay says what that
evidence may and may not support.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE  # noqa: E402

PR_HEAD = "12400f8c9394de5741bb37269dbf6e392b9245ad"
CADENCE_COMMIT = "153c62392131e86c7538c1c71b85d631039d8cc6"

PERMITTED_TYPES = ("company_ir_events_calendar", "company_ir_press_release",
                   "company_earnings_advisory_pr", "sec_filing_8k_earnings_date")

ROLE_PERMITTED = "PERMITTED_SOURCE_OF_RECORD"
ROLE_NAV = "NAVIGATION_ONLY"
ROLE_RECON = "RECONNAISSANCE_ONLY"
ROLE_INVALID = "INVALID_OR_UNRELATED"
ROLE_FAILED = "ACCESS_FAILED"

NONCANONICAL_STATUS = "NO_ENROLLMENT_DECISION_REACHED"

# Paths that are plainly not an IR events calendar / earnings advisory.
UNRELATED_PATH = re.compile(
    r"/sustainability|/environment|/spill|/careers|/products|/esg|/community|/safety", re.I)
# A press-release or news INDEX is a listing, not a specific advisory that
# establishes a date.
INDEX_PATH = re.compile(r"press-releases?/?$|/news(\.html)?/?$|/news-events/?$"
                        r"|/investors/news-events/?$|/news-media/?$", re.I)
EVENTS_PATH = re.compile(r"event|calendar|quarterly|news-events-and-reports", re.I)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


MANIFEST = json.loads((OUT / "SWEEP_MANIFEST_ROUND1.json").read_text(encoding="utf-8"))
P1 = json.loads((OUT / "sweep_raw_round1.json").read_text(encoding="utf-8"))
P2 = json.loads((OUT / "sweep_raw_round1_pass2.json").read_text(encoding="utf-8"))

# Which URL carried an issuer statement of absence, and which carried dated text
absence_urls, dated_urls = set(), set()
for r in P1["rows"]:
    for a in r["checked_urls"]:
        if a.get("explicit_date_plus_earnings_sentences"):
            dated_urls.add(a["url"])
for t, r in P2["rows"].items():
    for a in r["attempts"]:
        if a.get("issuer_states_no_upcoming_events"):
            absence_urls.add(a["url"])
        if a.get("date_plus_earnings_sentences"):
            dated_urls.add(a["url"])
# GPN's absence statement lives in the pass-1 body; it was detected downstream.
absence_urls.add("https://investors.globalpayments.com/events-and-presentations")


def classify(url: str, recorded_type: str, access: str) -> tuple[str, str]:
    if access != "RETRIEVED":
        return ROLE_FAILED, f"the page could not be read ({access}); it supports no conclusion"
    p = urlparse(url)
    path = p.path or "/"
    if p.netloc.endswith("data.sec.gov"):
        return ROLE_RECON, ("the SEC submissions INDEX is an official SEC endpoint but is only a "
                            "list of filing metadata; it is not a filing that states a future "
                            "earnings date")
    if UNRELATED_PATH.search(path):
        return ROLE_INVALID, ("this page is not an investor-relations events calendar or earnings "
                              "advisory; it is unrelated issuer content and cannot support any "
                              "enrollment or 'no upcoming event' conclusion")
    if path in ("", "/"):
        return ROLE_NAV, ("a company homepage / IR landing root. Useful to find the real calendar, "
                          "but not itself a permitted source of record")
    if INDEX_PATH.search(path) and not EVENTS_PATH.search(path):
        return ROLE_RECON, ("a press-release or news listing index, not a specific earnings "
                            "advisory establishing a date")
    if EVENTS_PATH.search(path):
        return ROLE_PERMITTED, "an issuer investor-relations events calendar page"
    return ROLE_RECON, "issuer page whose role as an events calendar is not established"


corrections, url_rows = [], []
for row in MANIFEST["rows"]:
    ticker = row["ticker"]
    for c in row["checked_sources"]:
        role, reason = classify(c["url"], c["source_type"], c["access_result"])
        rec = {
            "ticker": ticker,
            "url": c["url"],
            "original_source_type": c["source_type"],
            "original_access_result": c["access_result"],
            "effective_role": role,
            "may_support_a_disposition": role == ROLE_PERMITTED,
            "reason": reason,
            "issuer_stated_no_upcoming_events_here": c["url"] in absence_urls,
            "dated_earnings_text_here": c["url"] in dated_urls,
        }
        url_rows.append(rec)
        if role != ROLE_PERMITTED and c["source_type"] in PERMITTED_TYPES:
            corrections.append({
                "kind": "SOURCE_TYPE_MISCLASSIFICATION",
                "ticker": ticker,
                "url": c["url"],
                "original_value": {"source_type": c["source_type"]},
                "effective_value": {"effective_role": role, "permitted_source_of_record": False},
                "reason": reason,
            })

# Per-ticker effective outcome
ticker_rows = []
for row in MANIFEST["rows"]:
    t = row["ticker"]
    mine = [u for u in url_rows if u["ticker"] == t]
    permitted_ok = [u for u in mine if u["effective_role"] == ROLE_PERMITTED]
    absence = [u for u in mine if u["issuer_stated_no_upcoming_events_here"]
               and u["effective_role"] == ROLE_PERMITTED]
    failed = [u for u in mine if u["effective_role"] == ROLE_FAILED]

    if t == "DELL":
        eff = {
            "effective_proposed_disposition": None,
            "effective_status": "EXISTING_ENROLLED_EVENT_UNCHANGED",
            "is_canonical_protocol_disposition": False,
            "existing_event_id": "EVT-DELL-FY27Q2-ERN",
            "existing_registration_row_id": "EVT-DELL-FY27Q2-ERN-REG-001",
            "reason": ("Already enrolled before the protocol existed. Its official source could "
                       "not be read on this sweep, so no recheck was performed and nothing was "
                       "altered, amended or re-verified."),
        }
    else:
        eff = {
            "effective_proposed_disposition": None,
            "effective_status": NONCANONICAL_STATUS,
            "is_canonical_protocol_disposition": False,
            "reason": ("No official fiscal-period identity and no explicitly dated upcoming "
                       "earnings event were established, so no protocol disposition can be "
                       "reached. A canonical PENDING_OFFICIAL_DATE_UNAVAILABLE row would require "
                       "a candidate identity (ticker + fiscal period) that no source supplied; "
                       "inventing one to satisfy the schema is forbidden."),
            "remains_eligible_for_next_scheduled_sweep": True,
        }
    eff.update({
        "ticker": t,
        "original_proposed_disposition": row["proposed_disposition"],
        "permitted_sources_of_record_read": len(permitted_ok),
        "issuer_stated_absence_on_a_permitted_page": bool(absence),
        "access_failures": len(failed),
    })
    ticker_rows.append(eff)

    if row["proposed_disposition"] and eff["effective_proposed_disposition"] is None:
        corrections.append({
            "kind": "UNSUPPORTED_CANONICAL_DISPOSITION",
            "ticker": t,
            "url": None,
            "original_value": {"proposed_disposition": row["proposed_disposition"]},
            "effective_value": {"proposed_disposition": None,
                                "status": eff["effective_status"]},
            "reason": eff["reason"],
        })

# Round-2 sets, recomputed from the evidence rather than assumed
client_rendered, access_failed, issuer_absent, invalid_pages = [], [], [], []
no_calendar_located = []
for row in MANIFEST["rows"]:
    t = row["ticker"]
    if t == "DELL":
        continue
    mine = [u for u in url_rows if u["ticker"] == t]
    permitted_read = [u for u in mine if u["effective_role"] == ROLE_PERMITTED]
    absence = [u for u in permitted_read if u["issuer_stated_no_upcoming_events_here"]]
    if absence:
        issuer_absent.append({"ticker": t, "url": absence[0]["url"],
                              "basis": "the issuer's own events page states no upcoming events"})
        continue
    if permitted_read:
        for u in permitted_read:
            client_rendered.append({
                "ticker": t, "url": u["url"], "prior_http_result": "RETRIEVED (HTTP 200)",
                "why_static_html_insufficient": ("the served HTML contained no dated upcoming "
                                                 "event; this calendar renders its event list "
                                                 "client-side"),
                "browser_rendering_required": True,
                "human_observation_acceptable_alternative": True,
                "was_inaccessible": False,
            })
    else:
        fails = [u for u in mine if u["effective_role"] == ROLE_FAILED]
        if fails:
            access_failed.append({
                "ticker": t,
                "urls": [f["url"] for f in fails],
                "results": sorted({f["original_access_result"] for f in fails}),
                "note": "no permitted source of record could be read; this is an access failure, "
                        "NOT issuer-confirmed absence",
            })
        else:
            # Everything fetched fine, but nothing fetched was an events calendar.
            # That is a URL-DISCOVERY gap in round 1 -- neither an access failure
            # nor issuer absence -- and it must not be conflated with either.
            no_calendar_located.append({
                "ticker": t,
                "urls_read": [u["url"] for u in mine
                              if u["effective_role"] in (ROLE_RECON, ROLE_NAV)],
                "note": ("pages were retrieved successfully but none of them is an issuer events "
                         "calendar; round 1 never located the right URL. This is a discovery gap, "
                         "NOT an access failure and NOT issuer-confirmed absence"),
                "browser_rendering_required": True,
                "human_observation_acceptable_alternative": True,
            })
    for u in mine:
        if u["effective_role"] == ROLE_INVALID:
            invalid_pages.append({"ticker": t, "url": u["url"], "reason": u["reason"]})

overlay = {
    "artifact": "GST Prospective Cohort — Round 1 Correction Overlay",
    "overlay_version": "1",
    "sweep_round": 1,
    "authored_at_utc": now(),
    "pr_head_audited": PR_HEAD,
    "cadence_commit": CADENCE_COMMIT,
    "authority": (
        "This overlay is AUTHORITATIVE for interpreting round 1. It never asserts that the "
        "original bytes were different: the originals are preserved verbatim and hash-locked "
        "below, mistakes included. Where the two disagree, the original records what was done "
        "and this overlay records what that evidence may legitimately support."
    ),
    "original_artifacts_sha256_lf": {
        "SWEEP_MANIFEST_ROUND1.json": sha(OUT / "SWEEP_MANIFEST_ROUND1.json"),
        "sweep_raw_round1.json": sha(OUT / "sweep_raw_round1.json"),
        "sweep_raw_round1_pass2.json": sha(OUT / "sweep_raw_round1_pass2.json"),
        "HUMAN_REVIEW_REQUIRED_ROUND1.json": sha(OUT / "HUMAN_REVIEW_REQUIRED_ROUND1.json"),
        "sec_cik_map_round1.json": sha(OUT / "sec_cik_map_round1.json"),
    },
    "originals_rewritten": False,
    "noncanonical_status_label": {
        "label": NONCANONICAL_STATUS,
        "is_one_of_the_twelve_protocol_dispositions": False,
        "statement": (
            f"{NONCANONICAL_STATUS} is a RECONNAISSANCE label, not a protocol disposition. It is "
            "deliberately outside the twelve codes defined by cohort protocol v1.0/v1.1 so it can "
            "never be mistaken for a screening decision."
        ),
    },
    "canonical_pending_rule": (
        "PENDING_OFFICIAL_DATE_UNAVAILABLE may be used canonically only when an actual candidate "
        "identity exists -- ticker AND fiscal period -- so the screening-log schema can be "
        "satisfied without inventing a label. Round 1 established no such identity for any ticker."
    ),
    "sec_submissions_index_rule": {
        "endpoint": "https://data.sec.gov/submissions/CIK{cik}.json",
        "effective_role": ROLE_RECON,
        "is_sec_filing_8k_earnings_date": False,
        "rules": [
            "The submissions index is an official SEC endpoint but is only filing METADATA.",
            "A specific issuer-filed 8-K becomes a permitted source only after the exact filing "
            "is opened and is found to state the future earnings date and timing explicitly.",
            "An accession number, a filing date, or an Item 2.02 label establishes NO upcoming "
            "candidate.",
            "No previous filing metadata may influence enrollment.",
            "NO FILING CONTENT WAS OPENED IN ROUND 1.",
        ],
        "recent_8k_metadata": {
            "retained_in_raw_artifact": True,
            "used_in_effective_decision": False,
            "prohibited_from_use": True,
            "future_guidance": "Future sweeps should not store recent-8-K lists when no candidate "
                               "filing is opened.",
        },
    },
    "source_role_vocabulary": [ROLE_PERMITTED, ROLE_NAV, ROLE_RECON, ROLE_INVALID, ROLE_FAILED],
    "roles_that_may_support_a_disposition": [ROLE_PERMITTED],
    "url_classifications": url_rows,
    "corrections": corrections,
    "effective_ticker_outcomes": ticker_rows,
    "round2_sets": {
        "client_rendered_official_calendars": client_rendered,
        "client_rendered_ticker_count": len({c["ticker"] for c in client_rendered}),
        "access_failures": access_failed,
        "access_failure_ticker_count": len(access_failed),
        "issuer_stated_no_upcoming_event": issuer_absent,
        "issuer_stated_absence_ticker_count": len(issuer_absent),
        "no_events_calendar_located": no_calendar_located,
        "no_events_calendar_located_ticker_count": len(no_calendar_located),
        "invalid_or_unrelated_pages": invalid_pages,
        "dell_source_recheck": {
            "ticker": "DELL",
            "urls": ["https://investors.delltechnologies.com/news-events/upcoming-events",
                     "https://investors.delltechnologies.com/"],
            "status": "both timed out in round 1; recheck not performed",
            "action": "re-read the official page for date/time consistency only; the registration "
                      "is not to be altered",
        },
    },
    "round1_conclusion": {
        "enrollable_candidates_established": 0,
        "canonical_candidate_dispositions_written": 0,
        "registry_rows_written": 0,
        "human_verifications_completed": 0,
        "existing_enrolled_events_unchanged": ["EVT-DELL-FY27Q2-ERN"],
        "classification": ("Round 1 is RECONNAISSANCE EVIDENCE. It is not a completed canonical "
                           "screening decision for 23 unnamed fiscal periods."),
        "retrieval_failure_is_not_absence": (
            "An unreadable or client-rendered page is a retrieval limitation. It is never "
            "described as issuer-confirmed absence. Only the pages that explicitly state no "
            "upcoming events are recorded as issuer-stated absence."
        ),
        "unresolved_tickers_continue": ("to the scheduled Monday 09:00 America/Chicago renderer / "
                                        "human sweep under protocol v1.1"),
    },
}

(OUT / "ROUND1_CORRECTION_OVERLAY_v1.json").write_text(
    json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

print("wrote ROUND1_CORRECTION_OVERLAY_v1.json")
print("  url classifications :", len(url_rows))
print("  corrections         :", len(corrections))
from collections import Counter
print("  role counts         :", dict(Counter(u["effective_role"] for u in url_rows)))
print("  client-rendered tickers:", overlay["round2_sets"]["client_rendered_ticker_count"])
print("  access-failure tickers :", overlay["round2_sets"]["access_failure_ticker_count"])
print("  issuer-absence tickers :", overlay["round2_sets"]["issuer_stated_absence_ticker_count"])
print("  no-calendar-located tickers:", len(no_calendar_located))
print("  invalid/unrelated pages:", len(invalid_pages))
covered = (overlay["round2_sets"]["client_rendered_ticker_count"]
           + overlay["round2_sets"]["access_failure_ticker_count"]
           + overlay["round2_sets"]["issuer_stated_absence_ticker_count"]
           + len(no_calendar_located))
print("  non-DELL tickers bucketed:", covered, "/ 23")
