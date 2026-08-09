#!/usr/bin/env python3
"""Round-1 sweep, pass 2: recover the tickers whose constructed IR URL failed.

A 404 on a URL I constructed is evidence that MY URL was wrong -- not that the
issuer publishes no calendar. Pass 2 therefore discovers the correct page from
the ISSUER'S OWN SITE: fetch the issuer root domain, read its own navigation
links, and follow the ones the issuer itself labels investor/events.

No search engine. No aggregator. No snippet. Issuer domains only.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "GST Earnings Signal Research (academic research; hakurati11@gmail.com)"}
OUT = Path(__file__).resolve().parent

# The issuer's own primary domain. Nothing here is a third party.
ISSUER_ROOT = {
    "ABBV":  "https://www.abbvie.com/",
    "BRK-B": "https://www.berkshirehathaway.com/",
    "DELL":  "https://investors.delltechnologies.com/",
    "DVN":   "https://www.devonenergy.com/",
    "GME":   "https://investor.gamestop.com/",
    "INTC":  "https://www.intc.com/",
    "LDOS":  "https://www.leidos.com/",
    "NCLH":  "https://www.nclhltd.com/",
    "NKE":   "https://investors.nike.com/",
    "SBUX":  "https://investor.starbucks.com/",
    "STZ":   "https://ir.cbrands.com/",
    "TSLA":  "https://ir.tesla.com/",
    "TTWO":  "https://ir.take2games.com/",
    "UAL":   "https://ir.united.com/",
}

DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)"
    r"\s+\d{1,2},?\s+20\d{2}", re.I)
EARNINGS_RE = re.compile(r"earnings|financial results|quarterly results", re.I)
NO_UPCOMING_RE = re.compile(
    r"no upcoming events|there are currently no|no events scheduled|no upcoming", re.I)
LINK_RE = re.compile(r'href=["\']([^"\']+)["\'][^>]*>(.{0,90}?)</a>', re.I | re.S)
WANT = re.compile(r"event|investor|calendar|news", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url: str, timeout: int = 22):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            raw = r.read(600_000)
            return "RETRIEVED", str(r.status), raw.decode(r.headers.get_content_charset() or "utf-8",
                                                          "replace")
    except urllib.error.HTTPError as e:
        return "HTTP_ERROR", str(e.code), f"{type(e).__name__}: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return "ACCESS_FAILED", "", f"{type(e).__name__}: {str(e)[:150]}"


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", html)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
    return re.sub(r"\s+", " ", t).strip()


def evidence(text: str) -> dict:
    sentences = []
    for s in re.split(r"(?<=[.!?])\s+|\|", text):
        if len(s) <= 400 and DATE_RE.search(s) and EARNINGS_RE.search(s):
            sentences.append(s.strip())
    return {"date_plus_earnings_sentences": sentences[:6],
            "issuer_states_no_upcoming_events": bool(NO_UPCOMING_RE.search(text))}


def main() -> int:
    results = {}
    for i, (ticker, root) in enumerate(ISSUER_ROOT.items(), 1):
        rec = {"ticker": ticker, "issuer_root": root, "attempts": [], "retrieved_at_utc": now()}
        result, status, body = fetch(root)
        rec["attempts"].append({"url": root, "access_result": result, "http_status": status,
                                "source_type": "company_official_site_root",
                                "error": None if result == "RETRIEVED" else body[:150]})
        candidates = []
        if result == "RETRIEVED":
            ev = evidence(strip_html(body))
            rec["attempts"][-1].update(ev)
            for href, label in LINK_RE.findall(body):
                if not WANT.search(href + " " + label):
                    continue
                full = urllib.parse.urljoin(root, href)
                host = urllib.parse.urlparse(full).netloc
                root_host = urllib.parse.urlparse(root).netloc
                base = ".".join(root_host.split(".")[-2:])
                if base not in host:          # issuer-domain links only
                    continue
                if re.search(r"event|calendar", href + " " + label, re.I):
                    candidates.append(full)
            seen, ordered = set(), []
            for c in candidates:
                if c not in seen:
                    seen.add(c); ordered.append(c)
            candidates = ordered[:3]
        rec["issuer_linked_event_pages"] = candidates
        time.sleep(0.4)

        for url in candidates:
            r2, s2, b2 = fetch(url)
            a = {"url": url, "access_result": r2, "http_status": s2,
                 "source_type": "company_ir_events_calendar",
                 "retrieved_at_utc": now()}
            if r2 == "RETRIEVED":
                a.update(evidence(strip_html(b2)))
                a["bytes"] = len(b2)
            else:
                a["error"] = b2[:150]
            rec["attempts"].append(a)
            time.sleep(0.4)

        results[ticker] = rec
        best = [a for a in rec["attempts"] if a.get("date_plus_earnings_sentences")]
        noup = any(a.get("issuer_states_no_upcoming_events") for a in rec["attempts"])
        print(f"  [{i:2d}/14] {ticker:<6} root={rec['attempts'][0]['access_result']:<13} "
              f"event_pages={len(candidates)} date_evidence={len(best)} no_upcoming_stated={noup}")

    (OUT / "sweep_raw_round1_pass2.json").write_text(
        json.dumps({"swept_at_utc": now(), "rows": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")
    print("\nwrote sweep_raw_round1_pass2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
