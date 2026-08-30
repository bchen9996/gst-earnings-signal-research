#!/usr/bin/env python3
"""Write the dated HYP-04 anchor-event calendar artifact. OFFLINE.

Derives from the pinned linkage history and the on-disk EDGAR cache. Reaches no
endpoint: the client is constructed with `offline=True`, and the derivation's
own `live_requests_made` is asserted to be zero before anything is written, so
"no requests were made" is a checked precondition and not a claim in prose.

Refuses to overwrite an existing artifact. Governance artifacts are append-only;
a superseded one stays byte-identical on disk.

  python -m hyp04_supply_chain_hedge.make_anchor_calendar
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from . import anchor_universe as au
from .anchor_calendar import (
    CALENDAR_CSV_FIELDS,
    derive_anchor_calendar,
)
from .edgar_linkage import EdgarClient, FilingCache
from .make_registry_v1_7 import _load

LSE = Path("Live Signal Engine")
HISTORY = LSE / "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-29_v1.json"
CACHE = Path(".edgar_cache")
AS_OF = "2026-08-29"

OUT_JSON = LSE / f"HYP04_ANCHOR_EVENT_CALENDAR_{AS_OF}.json"
OUT_CSV = LSE / f"HYP04_ANCHOR_EVENT_CALENDAR_{AS_OF}.csv"

# The registered threshold, restated here so the artifact can compare itself
# against it. Read from the registry rather than typed would be better still,
# but the registry entry is the authority either way and the test re-reads it.
MINIMUM_ELIGIBLE_EVENTS = 193


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(*, history: Path = HISTORY, cache_dir: Path = CACHE,
          contact: str, out_json: Path = OUT_JSON, out_csv: Path = OUT_CSV,
          today: str = AS_OF) -> list[str]:
    refusals: list[str] = []
    if not history.is_file():
        refusals.append(f"history walk not found at {history}")
    if not cache_dir.is_dir():
        refusals.append(f"EDGAR cache not found at {cache_dir}")
    for p in (out_json, out_csv):
        if p.exists():
            refusals.append(
                f"{p.name} already exists. Refusing to overwrite a dated "
                "artifact -- delete it deliberately first if that is really "
                "intended.")
    if refusals:
        return refusals

    universe = au.derive_universe_point_in_time(_load(history))
    cache = FilingCache(cache_dir, readonly=True)
    client = EdgarClient(contact, cache=cache, offline=True)

    strict = derive_anchor_calendar(universe, client, today=today)
    legacy = derive_anchor_calendar(universe, client,
                                    accept_legacy_item_12=True, today=today)

    for name, cal in (("strict", strict), ("legacy", legacy)):
        if not cal.derived:
            refusals.append(f"{name} calendar refused: " + "; ".join(cal.refusals))
        if cal.live_requests_made:
            refusals.append(
                f"{name} calendar made {cal.live_requests_made} LIVE requests. "
                "This generator is offline by contract; refusing to write an "
                "artifact whose provenance it cannot state truthfully.")
    if refusals:
        return refusals

    payload = {
        "artifact": out_json.name,
        "as_of_date": today,
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "CANDIDATE anchor events: 8-K results filings falling inside a "
            "span during which the filer was a registered HYP-04 anchor. It "
            "answers the feasibility question registry v1.9 leaves open by "
            "name, and it answers it with a DERIVED count in place of the "
            "member-years estimate used until now."),
        "what_this_is_not": (
            "It is not an eligible-event count and moves no gate. An eligible "
            "anchor event additionally requires a well-measured shock "
            "(HYP04-ANCHOR-SHOCK-RULE-v1), which requires anchor and benchmark "
            "closes for the attributed session. No price source is decided, no "
            "shock has been computed from production data, the eligible count "
            "is zero, and the display gate stays CLOSED."),
        "sources": {
            "linkage_history": history.name,
            "linkage_history_sha256": _sha256(history),
            "anchor_universe_rule_id": universe.rule_id,
            "anchor_universe_registry_grade": universe.registry_grade,
            "membership_intervals": len(universe.intervals),
            "members_ever": list(universe.members_ever),
            "edgar_cache": str(cache_dir),
            "live_requests_made": 0,
        },
        "registered_threshold": {
            "minimum_eligible_events": MINIMUM_ELIGIBLE_EVENTS,
            "unit": "anchor events, deliberately not (anchor x peer) pairs",
            "candidates_vs_threshold_strict":
                strict.total - MINIMUM_ELIGIBLE_EVENTS,
            "note": (
                "A candidate surplus is not a met threshold. Every candidate "
                "still has to survive the shock rule, and none has been put "
                "through it."),
        },
        "primary_specification_unchanged": strict.as_dict(),
        "measured_alternative_not_adopted": legacy.as_dict(),
        "session_resolution": {
            "strict": _sessions(strict),
            "legacy": _sessions(legacy),
            "why_it_matters": (
                "AS-1 requires the shock to be measured on the session the "
                "release is attributed to. An UNKNOWN session cannot satisfy "
                "it, so a resolved session is a necessary condition for "
                "eligibility and the resolved count is the tighter ceiling."),
        },
    }

    out_json.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n",
                        encoding="utf-8")

    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CALENDAR_CSV_FIELDS))
        w.writeheader()
        for e in strict.entries:
            w.writerow(e.as_row())

    return []


def _sessions(cal) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in cal.entries:
        out[e.event.release_session] = out.get(e.event.release_session, 0) + 1
    out["resolved_BMO_or_AMC"] = out.get("BMO", 0) + out.get("AMC", 0)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contact", required=True,
                    help="SEC fair-access contact. Required even offline: the "
                         "client refuses to exist without one.")
    ap.add_argument("--history", type=Path, default=HISTORY)
    ap.add_argument("--cache-dir", type=Path, default=CACHE)
    a = ap.parse_args(argv)

    refusals = build(history=a.history, cache_dir=a.cache_dir,
                     contact=a.contact)
    if refusals:
        print("REFUSED:")
        for r in refusals:
            print("  -", r)
        return 1
    print(f"wrote {OUT_JSON}")
    print(f"  sha256 {_sha256(OUT_JSON)}")
    print(f"wrote {OUT_CSV}")
    print(f"  sha256 {_sha256(OUT_CSV)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
