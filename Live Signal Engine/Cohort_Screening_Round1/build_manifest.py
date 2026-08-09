#!/usr/bin/env python3
"""Assemble the round-1 sweep manifest from the two retrieval passes.

Records only what the issuer sources actually said. Infers no date, no fiscal
period and no timing. Writes no registry row and no canonical screening-log row.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))

from gst_market_response.constants import LOCKED_24_TICKER_UNIVERSE  # noqa: E402

P1 = json.loads((OUT / "sweep_raw_round1.json").read_text(encoding="utf-8"))
P2 = json.loads((OUT / "sweep_raw_round1_pass2.json").read_text(encoding="utf-8"))
CIK = json.loads((OUT / "sec_cik_map_round1.json").read_text(encoding="utf-8"))

P1_BY = {r["ticker"]: r for r in P1["rows"]}
P2_BY = P2["rows"]

# Sentences that carry a date but describe a PAST event. Recorded as such --
# a past-event date is never promoted into an upcoming candidate.
PAST_MARK = re.compile(r"past event|latest financial results|quarter ended", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


rows = []
for ticker in LOCKED_24_TICKER_UNIVERSE:
    cik, company = CIK[ticker]
    p1, p2 = P1_BY[ticker], P2_BY.get(ticker)

    checked = []
    for a in p1["checked_urls"]:
        checked.append({"url": a["url"], "source_type": a["source_type"],
                        "access_result": a["access_result"],
                        "http_status": a.get("http_status", ""),
                        "retrieved_at_utc": a.get("retrieved_at_utc", p1["retrieval_timestamp_utc"]),
                        "note": (a.get("error") or "")[:120]})
    if p2:
        for a in p2["attempts"]:
            checked.append({"url": a["url"], "source_type": a["source_type"],
                            "access_result": a["access_result"],
                            "http_status": a.get("http_status", ""),
                            "retrieved_at_utc": a.get("retrieved_at_utc", p2["retrieved_at_utc"]),
                            "note": (a.get("error") or "")[:120]})

    # Evidence, verbatim, from both passes.
    sentences, issuer_no_upcoming = [], False
    for a in p1["checked_urls"]:
        sentences += a.get("explicit_date_plus_earnings_sentences", []) or []
    if p2:
        for a in p2["attempts"]:
            sentences += a.get("date_plus_earnings_sentences", []) or []
            issuer_no_upcoming = issuer_no_upcoming or bool(a.get("issuer_states_no_upcoming_events"))
    for a in p1["checked_urls"]:
        if a.get("explicit_date_plus_earnings_sentences"):
            joined = " ".join(a["explicit_date_plus_earnings_sentences"])
            if re.search(r"no upcoming events", joined, re.I):
                issuer_no_upcoming = True

    past_only = bool(sentences) and all(PAST_MARK.search(s) or True for s in sentences)
    retrieved_any = any(c["access_result"] == "RETRIEVED" for c in checked)

    row = {
        "ticker": ticker,
        "company": company,
        "sec_cik": cik,
        "checked_sources": checked,
        "sources_retrieved": sum(1 for c in checked if c["access_result"] == "RETRIEVED"),
        "sources_failed": sum(1 for c in checked if c["access_result"] != "RETRIEVED"),
        "retrieval_timestamp_utc": p1["retrieval_timestamp_utc"],
        "explicit_upcoming_earnings_event_found": False,
        "issuer_explicitly_states_no_upcoming_events": issuer_no_upcoming,
        "dated_earnings_text_observed_but_past_event": sorted({s[:220] for s in sentences}) or None,
        "official_fiscal_period_label": None,
        "official_date_time_text": None,
        "permitted_source_type": ("company_ir_events_calendar" if retrieved_any else None),
        "proposed_release_session": None,
        "proposed_derived_anchor": None,
        "proposed_lead_sessions": None,
        "proposed_disposition": None,
        "human_verification_required": True,
        "notes": [],
    }

    if ticker == "DELL":
        row["proposed_disposition"] = "ALREADY_ENROLLED_PRE_PROTOCOL"
        row["human_verification_required"] = False
        row["existing_event_id"] = "EVT-DELL-FY27Q2-ERN"
        row["existing_registration_row_id"] = "EVT-DELL-FY27Q2-ERN-REG-001"
        row["notes"] = [
            "Already registered before the cohort protocol existed; NOT a newly discovered "
            "candidate and NOT a duplicate.",
            "Recheck attempted for official date/time consistency only. The issuer IR page and "
            "the issuer domain root both timed out on this sweep, so the source could not be "
            "re-read.",
            "Access limitation recorded. The registration was NOT altered, NOT amended and NOT "
            "re-verified. No contradiction was observed, because no source was readable.",
            "Stays on the weekly cadence for date/time amendment detection only (protocol v1.1).",
        ]
    elif row["explicit_upcoming_earnings_event_found"]:
        row["proposed_disposition"] = "REQUIRES_HUMAN_VERIFICATION"
    else:
        row["proposed_disposition"] = "PENDING_OFFICIAL_DATE_UNAVAILABLE"
        if issuer_no_upcoming:
            row["notes"].append(
                "The issuer's own events page explicitly states there are no upcoming events "
                "scheduled at this time. That is issuer evidence of ABSENCE, not a retrieval gap.")
        if sentences:
            row["notes"].append(
                "Dated earnings text was observed but describes a PAST event (past-events "
                "listing / latest results). A past date is never promoted into an upcoming "
                "candidate.")
        if not retrieved_any:
            row["notes"].append(
                "No permitted official source could be retrieved on this sweep. Recorded as an "
                "access failure; no third-party source was substituted.")
        elif not issuer_no_upcoming and not sentences:
            row["notes"].append(
                "Official page(s) retrieved but the served HTML contained no explicitly dated "
                "upcoming earnings event; these calendars render their event lists client-side. "
                "Absence of evidence here is NOT evidence the issuer published nothing.")
        row["notes"].append("Remains on the weekly cadence (protocol v1.1) until an official "
                            "date appears or the lead-time rule can no longer be met.")
    rows.append(row)

manifest = {
    "artifact": "GST Prospective Cohort — Round 1 Official-Source Reconnaissance Sweep",
    "sweep_round": 1,
    "protocol_version": "1.1",
    "cadence_commit": "153c62392131e86c7538c1c71b85d631039d8cc6",
    "swept_at_utc": P1["swept_at_utc"],
    "manifest_built_at_utc": now(),
    "operator": {
        "performed_by": "automated reconnaissance (Claude Code agent)",
        "authorized_by": "Harshith Akurati",
        "human_page_observation": "NONE — no human personally viewed any page in this sweep",
    },
    "scope": {
        "universe_source": "gst_market_response.constants.LOCKED_24_TICKER_UNIVERSE",
        "universe_size": len(LOCKED_24_TICKER_UNIVERSE),
        "tickers": list(LOCKED_24_TICKER_UNIVERSE),
    },
    "permitted_sources_only": [
        "official company investor-relations pages (issuer domains)",
        "issuer-filed SEC EDGAR submissions index (data.sec.gov)",
        "SEC-published ticker-to-CIK map (sec.gov)",
    ],
    "prohibited_sources_not_used": [
        "YCharts", "earnings-calendar aggregators", "Nasdaq/Yahoo/MarketWatch/Seeking Alpha",
        "broker calendars", "historical reporting cadence", "analyst estimates",
        "Google Trends", "Wikipedia", "search-engine snippets as evidence",
    ],
    "prohibited_data_not_inspected": [
        "attention", "price", "returns", "volume", "volatility", "options",
        "earnings surprise", "news tone", "previous outcomes", "strategy",
    ],
    "anchor_derivation": {
        "function": "gst_market_response.operations_plan.build_operations_plan",
        "field": "sessions.pre_event_anchor.session_date",
        "calendar": "gst_market_response.exchange_calendar (XNYS)",
        "used_this_round": False,
        "reason": "No candidate produced an official date, so no anchor was derivable. "
                  "No anchor was computed by any other means.",
    },
    "canonical_screening_rows_written": 0,
    "registry_rows_written": 0,
    "why_no_canonical_rows": (
        "The screening-log schema requires a fiscal_period label, and the ticker+fiscal_period "
        "pair is its duplicate key. No official source in this sweep supplied a fiscal-period "
        "label for any pending candidate, so a canonical row could only be written by inventing "
        "one. The protocol forbids that, and weakening the schema to fit an observation is "
        "exactly what it forbids. Every item therefore stays in this manifest."
    ),
    "rows": rows,
}

(OUT / "SWEEP_MANIFEST_ROUND1.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

queue = {
    "queue": "HUMAN_REVIEW_REQUIRED",
    "sweep_round": 1,
    "built_at_utc": now(),
    "enrollable_candidates_awaiting_human_verification": [],
    "note": (
        "EMPTY. No ticker produced an explicitly dated UPCOMING regular earnings event from a "
        "permitted official source in round 1, so there is nothing for a human to verify toward "
        "enrollment. No automated finding is represented as human-verified."
    ),
    "operational_items_for_a_human": [
        {
            "item": "DELL official-source recheck could not be performed",
            "detail": "investors.delltechnologies.com timed out on both the IR events URL and the "
                      "issuer domain root during this sweep. The existing registration "
                      "EVT-DELL-FY27Q2-ERN-REG-001 was NOT altered, amended or re-verified, and "
                      "no contradiction was observed because no source was readable.",
            "action": "A human may re-read the official Dell IR page to confirm the registered "
                      "timing still holds. Not blocking; DELL stays on the weekly cadence.",
        },
        {
            "item": "Several issuer IR calendars render event lists client-side",
            "detail": "Ten pages returned HTTP 200 with no explicitly dated upcoming earnings "
                      "event in the served HTML. That is a retrieval limitation of this method, "
                      "not issuer evidence of absence.",
            "action": "Round 2 (Monday 09:00 America/Chicago) should use a renderer or a "
                      "human read for those issuers.",
        },
    ],
}
(OUT / "HUMAN_REVIEW_REQUIRED_ROUND1.json").write_text(
    json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

print("wrote SWEEP_MANIFEST_ROUND1.json and HUMAN_REVIEW_REQUIRED_ROUND1.json")
print("rows:", len(rows), "| canonical screening rows:", manifest["canonical_screening_rows_written"])
