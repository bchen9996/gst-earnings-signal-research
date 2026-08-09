#!/usr/bin/env python3
"""Round-1 blind official-source reconnaissance sweep.

PERMITTED SOURCES ONLY: official company investor-relations pages and
issuer-filed SEC material (EDGAR). Search engines are not used, aggregators are
not used, and no snippet is ever treated as evidence.

PROHIBITED AND NOT TOUCHED: attention, price, volume, volatility, options,
earnings surprise, analyst estimates, news tone, previous outcomes, historical
reporting cadence.

This script RETRIEVES and RECORDS. It classifies nothing that the source does
not state, infers no date, fiscal period or timing, and writes no registry or
canonical ENROLLED row.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "GST Earnings Signal Research (academic research; hakurati11@gmail.com)"}
OUT = Path(__file__).resolve().parent

# Official issuer investor-relations entry points. Each host is the issuer's own
# domain (or its IR provider subdomain under the issuer's domain). No aggregator,
# no broker, no market-data site.
IR_PAGES: dict[str, list[str]] = {
    "AAPL":  ["https://investor.apple.com/investor-relations/default.aspx"],
    "ABBV":  ["https://investors.abbvie.com/events-and-presentations"],
    "ADBE":  ["https://www.adobe.com/investor-relations.html"],
    "AMZN":  ["https://ir.aboutamazon.com/events/default.aspx"],
    "BKR":   ["https://investors.bakerhughes.com/events-presentations"],
    "BRK-B": ["https://www.berkshirehathaway.com/news/news.html"],
    "CTSH":  ["https://news.cognizant.com/events"],
    "DELL":  ["https://investors.delltechnologies.com/news-events/upcoming-events"],
    "DVN":   ["https://investors.devonenergy.com/events-and-presentations"],
    "GME":   ["https://investor.gamestop.com/news-events/ir-calendar"],
    "GOOGL": ["https://abc.xyz/investor/events/"],
    "GPN":   ["https://investors.globalpayments.com/events-and-presentations"],
    "INTC":  ["https://www.intc.com/news-events/events-calendar"],
    "LDOS":  ["https://investors.leidos.com/events-and-presentations"],
    "MSFT":  ["https://www.microsoft.com/en-us/investor/events/default.aspx"],
    "NCLH":  ["https://www.nclhltd.com/investors/news-and-events/event-calendar"],
    "NKE":   ["https://investors.nike.com/events-and-presentations/default.aspx"],
    "QCOM":  ["https://investor.qualcomm.com/news-events/events"],
    "SBUX":  ["https://investor.starbucks.com/events-and-presentations/default.aspx"],
    "STZ":   ["https://ir.cbrands.com/events-and-presentations"],
    "SYK":   ["https://investors.stryker.com/events-and-presentations"],
    "TSLA":  ["https://ir.tesla.com/#quarterly-disclosure"],
    "TTWO":  ["https://ir.take2games.com/news-events/ir-calendar"],
    "UAL":   ["https://ir.united.com/news-and-events/events"],
}

# Phrases that, if present in issuer text, indicate an explicitly dated upcoming
# earnings event. Presence is recorded; nothing is inferred from absence.
DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+20\d{2}", re.I)
EARNINGS_RE = re.compile(r"earnings|results|financial results|quarterly results", re.I)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)\s*(?:ET|EST|EDT|CT|CST|CDT|PT|PST|PDT)?",
                     re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url: str, timeout: int = 25) -> tuple[str, str, str]:
    """Return (result, http_status, body_or_error). Never raises."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(600_000)
            enc = r.headers.get_content_charset() or "utf-8"
            return "RETRIEVED", str(r.status), raw.decode(enc, "replace")
    except urllib.error.HTTPError as e:
        return "HTTP_ERROR", str(e.code), f"{type(e).__name__}: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return "ACCESS_FAILED", "", f"{type(e).__name__}: {str(e)[:160]}"


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


def earnings_date_evidence(text: str) -> list[str]:
    """Sentences that carry BOTH an explicit calendar date AND earnings wording.

    Returned verbatim. Nothing is normalised, completed or guessed.
    """
    hits = []
    for sentence in re.split(r"(?<=[.!?])\s+|\|", text):
        if len(sentence) > 400:
            continue
        if DATE_RE.search(sentence) and EARNINGS_RE.search(sentence):
            hits.append(sentence.strip())
    return hits[:6]


def sec_recent_8k(cik: str) -> tuple[str, list[dict]]:
    """Issuer-filed 8-K metadata from EDGAR. Issuer-filed source, not a
    third party. Used only to look for an issuer announcement of an UPCOMING
    earnings date -- never to infer one from past filing cadence."""
    result, status, body = fetch(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if result != "RETRIEVED":
        return f"{result}({status})", []
    try:
        d = json.loads(body)
    except Exception:  # noqa: BLE001
        return "PARSE_FAILED", []
    rec = d.get("filings", {}).get("recent", {})
    rows = []
    for form, date, acc, doc, items in zip(rec.get("form", []), rec.get("filingDate", []),
                                           rec.get("accessionNumber", []),
                                           rec.get("primaryDocument", []),
                                           rec.get("items", [])):
        if form != "8-K":
            continue
        rows.append({"filing_date": date, "accession": acc, "items": items,
                     "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                            f"{acc.replace('-', '')}/{doc}"})
        if len(rows) >= 3:
            break
    return "RETRIEVED", rows


def main() -> int:
    cik_map = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    universe = list(cik_map)
    rows = []
    for i, ticker in enumerate(universe, 1):
        cik, company = cik_map[ticker]
        entry = {
            "ticker": ticker,
            "company": company,
            "cik": cik,
            "checked_urls": [],
            "retrieval_timestamp_utc": now(),
            "explicit_upcoming_earnings_event_found": False,
            "official_fiscal_period_label": None,
            "official_date_time_text": None,
            "permitted_source_type": None,
            "proposed_release_session": None,
            "proposed_derived_anchor": None,
            "proposed_lead_sessions": None,
            "proposed_disposition": None,
            "human_verification_required": True,
            "notes": [],
        }

        for url in IR_PAGES[ticker]:
            result, status, body = fetch(url)
            rec = {"url": url, "source_type": "company_ir_events_calendar",
                   "access_result": result, "http_status": status,
                   "retrieved_at_utc": now()}
            if result == "RETRIEVED":
                text = strip_html(body)
                rec["bytes"] = len(body)
                hits = earnings_date_evidence(text)
                rec["explicit_date_plus_earnings_sentences"] = hits
                if hits:
                    entry["explicit_upcoming_earnings_event_found"] = True
                    entry["official_date_time_text"] = hits[0][:300]
                    entry["permitted_source_type"] = "company_ir_events_calendar"
                    tm = TIME_RE.search(hits[0])
                    entry["notes"].append(
                        "explicit time text present" if tm else "no explicit time text in the matched sentence")
            else:
                rec["error"] = body[:160]
            entry["checked_urls"].append(rec)
            time.sleep(0.4)

        sec_status, filings = sec_recent_8k(cik)
        entry["checked_urls"].append({
            "url": f"https://data.sec.gov/submissions/CIK{cik}.json",
            "source_type": "sec_issuer_filed_submissions_index",
            "access_result": sec_status,
            "retrieved_at_utc": now(),
            "recent_8k": filings,
        })
        time.sleep(0.4)

        rows.append(entry)
        print(f"  [{i:2d}/24] {ticker:<6} ir={entry['checked_urls'][0]['access_result']:<13} "
              f"sec={sec_status:<20} date_evidence={entry['explicit_upcoming_earnings_event_found']}")

    (OUT / "sweep_raw_round1.json").write_text(
        json.dumps({"swept_at_utc": now(), "universe_size": len(rows), "rows": rows},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote sweep_raw_round1.json  ({len(rows)} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
