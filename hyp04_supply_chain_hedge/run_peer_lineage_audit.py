#!/usr/bin/env python3
"""LIVE. Fetch each resolved peer registrant's SEC record and audit its lineage.

Named off the `test_*` pattern deliberately: this is the only module in the
peer-ceiling group that reaches an endpoint, and it must never be swept up by a
test-runner glob.

STAGED. Without `--yes-run-live` it prints exactly which CIKs it would fetch and
exits, so the request list is reviewable before anything is asked of SEC.

  python -m hyp04_supply_chain_hedge.run_peer_lineage_audit          # dry run
  python -m hyp04_supply_chain_hedge.run_peer_lineage_audit --yes-run-live

One request per distinct registrant. `filings.files[]` bounds the older shards,
so a registrant's full filing history needs no extra fetch. Ticker -> CIK is
served from the cached company list and costs nothing.

Responses land in the shared EDGAR cache, so a re-run is free and the audit is
reproducible offline afterwards.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .peer_lineage import (
    PEER_LINEAGE_RULE_ID,
    LineageAssessment,
    assess,
    filer_history,
    rule_description,
    summarise,
)

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-02"
#: A CHRONOLOGY; the _vN suffix restarts on each new date.
#: 2026-08-31    -- a correct audit whose every verdict was CONTINUOUS, which
#:      is exactly the condition under which the check had never been observed
#:      to fire. Stays byte-identical on disk.
#: 2026-08-31_v2 -- added the live INGM control below.
#: 2026-09-02    -- THIS ONE. The corrected EDGAR walk recovered 56 annual
#:      reports the old `form == "10-K"` filter could not see, and one new
#:      counterparty resolved out of them: NVDA / Celestica, earliest
#:      2001-04-27, from a 10-K405. A resolved candidate cannot become a draft
#:      row until its lineage is audited -- make_linkage_draft excludes any row
#:      whose verdict is not CONTINUOUS -- so the audit re-runs over the new
#:      worklist. The control is unchanged and must still fire.
OUT_JSON = LSE / f"HYP04_PEER_LINEAGE_AUDIT_{AS_OF}.json"
SUPERSEDES = LSE / "HYP04_PEER_LINEAGE_AUDIT_2026-08-31_v2.json"

#: THE LIVE CONTROL. Every real candidate came back CONTINUOUS, and a guard
#: nobody has seen fail is not known to work -- the principle this repo applies
#: to its hardcoded-open conditions applies here too.
#:
#: So the audit also runs the case that MOTIVATED it: ADBE's 2006-02-08 filing
#: named "Ingram Micro", and the only SEC registrant matching that name today
#: is Ingram Micro Holding Corp, CIK 1897762 -- the 2024 re-IPO vehicle, whose
#: first filing postdates the disclosure by nearly two decades. It MUST come
#: back a lineage break. If it does not, the check cannot detect the error it
#: was written for, and the audit refuses to write anything.
#:
#: The control is not a candidate. It is never added to `assessments`, and the
#: normaliser fix already removed this row from the worklist.
CONTROL_CIK = "0001897762"
CONTROL_TICKER = "INGM"
CONTROL_DISCLOSED_NAME = "Ingram Micro"
CONTROL_AS_OF = "2006-02-08"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _newest(pattern: str) -> Optional[Path]:
    # Version-aware; a lexical sort picks _v3 over _v10. See artifacts.py.
    from .artifacts import newest_in
    return newest_in(LSE, pattern)


def _resolved_rows(path: Path) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))
    return [r for r in rows if (r.get("candidate_peer_ticker") or "").strip()]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Audit whether each resolved peer registrant was the "
                    "company its anchor's filing named. LIVE; staged.")
    ap.add_argument("--yes-run-live", action="store_true",
                    help="actually contact SEC (default: print the plan only)")
    ap.add_argument("--worklist", type=Path, default=None)
    a = ap.parse_args(argv)

    wl = a.worklist or _newest("HYP04_PEER_CURATION_WORKLIST_*.csv")
    if wl is None or not wl.is_file():
        print("REFUSED: no peer-curation worklist on disk", file=sys.stderr)
        return 1

    rows = _resolved_rows(wl)
    if not rows:
        print(f"REFUSED: {wl.name} has no ticker-resolved rows to audit",
              file=sys.stderr)
        return 1

    from .edgar_linkage import (
        EdgarClient, FilingCache, OfflineCacheMiss, SUBMISSIONS_URL)

    # Ticker -> CIK from the cached company list. Offline, free, and it must
    # stay that way: a CIK lookup that cost a request would make the plan
    # printed below untrue.
    lookup = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR), offline=True)
    ciks: dict[str, str] = {}
    unknown: list[str] = []
    for r in rows:
        t = r["candidate_peer_ticker"].strip().upper()
        if t in ciks or t in unknown:
            continue
        c = lookup.cik_for(t)
        (ciks.__setitem__(t, c) if c else unknown.append(t))
    if lookup.requests_made:
        print(f"REFUSED: ticker->CIK lookup cost {lookup.requests_made} "
              "request(s); it must be served from cache", file=sys.stderr)
        return 1

    print(f"worklist: {wl.name}")
    print(f"resolved candidate rows: {len(rows)}")
    print(f"distinct registrants to fetch: {len(ciks)}")
    for t, c in sorted(ciks.items()):
        names = sorted({r["counterparty_name_as_filed"] for r in rows
                        if r["candidate_peer_ticker"].strip().upper() == t})
        print(f"  {t:6} CIK {c}   {'; '.join(names)}")
    if unknown:
        print(f"  no CIK for: {', '.join(sorted(unknown))}")

    if not a.yes_run_live:
        print()
        print(f"DRY RUN. {len(ciks)} request(s) would be made to "
              "data.sec.gov. Re-run with --yes-run-live to proceed.")
        return 0

    client = EdgarClient(CONTACT, cache=FilingCache(CACHE_DIR),
                         max_requests=len(ciks) + 5)
    histories: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for t, c in sorted(ciks.items()):
        try:
            histories[t] = filer_history(
                client._get_json(SUBMISSIONS_URL.format(cik=c)))
        except Exception as exc:                       # noqa: BLE001
            errors[t] = f"{type(exc).__name__}: {exc}"

    # --- the control, before anything is written ----------------------
    control: dict[str, Any]
    try:
        ch = filer_history(
            client._get_json(SUBMISSIONS_URL.format(cik=CONTROL_CIK)))
        ca = assess(ch, disclosed_name=CONTROL_DISCLOSED_NAME,
                    as_of_date=CONTROL_AS_OF, anchor_ticker="ADBE",
                    peer_ticker=CONTROL_TICKER)
        control = ca.as_dict()
    except Exception as exc:                           # noqa: BLE001
        print(f"REFUSED: the lineage control could not be fetched: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    control["why_this_control_exists"] = (
        "Every real candidate returned CONTINUOUS. A check that has never "
        "been observed to fire is not known to work, so the audit re-runs the "
        "case that motivated it and refuses if that case does not break.")
    if not ca.is_break:
        print("REFUSED: the lineage control did NOT produce a break "
              f"(verdict {ca.verdict!r}). The check cannot detect the error "
              "it was written for, so its passes mean nothing.",
              file=sys.stderr)
        return 1
    print(f"control ({CONTROL_TICKER} @ {CONTROL_AS_OF}): {ca.verdict}")

    out: list[LineageAssessment] = []
    for r in rows:
        t = r["candidate_peer_ticker"].strip().upper()
        out.append(assess(
            histories.get(t),
            disclosed_name=r["counterparty_name_as_filed"],
            as_of_date=r["earliest_disclosing_filing_date"],
            anchor_ticker=r["anchor_ticker"],
            peer_ticker=t))

    counts = summarise(out)
    payload = {
        "artifact": OUT_JSON.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "rule": rule_description(),
        "what_this_is": (
            "Whether each ticker-resolved candidate's registrant was the "
            "company its anchor's filing actually named."),
        "what_this_is_not": (
            "Curation. No row is promoted, no edge is written, and a "
            "CONTINUOUS verdict clears one specific error, not the "
            "relationship."),
        "sources": {
            "worklist": wl.name,
            "worklist_sha256": _sha256(wl),
            "endpoint": "data.sec.gov submissions",
            "registrants_fetched": len(histories),
            "requests_made": client.requests_made,
        },
        "supersedes": SUPERSEDES.name,
        "supersedes_sha256": (_sha256(SUPERSEDES) if SUPERSEDES.is_file()
                              else None),
        "what_changed_from_v1": (
            "Adds the live control. v1's verdicts are unchanged and all seven "
            "were CONTINUOUS, which is precisely when a check needs to be "
            "shown capable of failing."),
        "control": control,
        "counts_by_verdict": counts,
        "lineage_breaks": sum(1 for r in out if r.is_break),
        "assessments": [r.as_dict() for r in out],
        "fetch_errors": errors,
        "opens_no_gate": (
            "The display gate is CLOSED, C4 MET, four denials, eligible count "
            "zero. Nothing here supplies an eligible event."),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print()
    print(f"requests made: {client.requests_made}")
    for k, v in sorted(counts.items()):
        print(f"  {v:3}  {k}")
    if errors:
        print(f"  fetch errors: {errors}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
