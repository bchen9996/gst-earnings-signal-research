#!/usr/bin/env python3
"""Emit the anchor-side closes request, and turn filled closes into shocks.

Two steps, deliberately separate, because exactly one of them touches a provider:

    --emit-request    OFFLINE. Derives the (ticker, session) pairs every anchor
                      event needs and writes one request file per ticker.
    --build           OFFLINE. Reads the FILLED request files and writes the
                      dated shock artifact.

The fetch between them is `run_peer_closes_fetch`, which is a separate, live,
staged-go-ahead runner. Nothing in this module reaches an endpoint.

=== EVERY EVENT GETS A ROW ===

All 342 calendar events appear in the artifact, carrying either a computed shock
or its stated denial. A denied event is DATA: it keeps the denominator visible,
so a sample that shrank cannot look like a sample that was always clean. This is
the same discipline the calendar applies to `superseded` and `denied`, and the
same reason `peer_returns` reports coverage rather than filtering silently.

=== IT DOES NOT MOVE C2 ===

`display_gate.current_decision()` passes a literal `eligible_event_count=0`, and
the gate cross-checks that count against the freeze record's event ids -- so C2
and C3 move together or not at all. Producing shocks cannot move either. This
artifact is the evidence that would justify that step; taking it is separate and
separately authorized.

  python -m hyp04_supply_chain_hedge.make_anchor_shocks --emit-request
  python -m hyp04_supply_chain_hedge.make_anchor_shocks --build
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .anchor_closes import (
    ANCHOR_CLOSES_RULE_ID,
    build_request,
    survivorship_exposure,
    write_request_csvs,
)
from .anchor_closes import shocks_for_request
from .anchor_shock import (
    ANCHOR_SHOCK_RULE_ID,
    BENCHMARK_BETA,
    BENCHMARK_TICKER,
    RETURN_BASIS,
)
from .sessions import calendar_id, sessions_for_release_dates

LSE = Path("Live Signal Engine")
REQUEST_DIR = LSE / "HYP04_ANCHOR_CLOSES_REQUEST"
AS_OF = "2026-08-31"

OUT_JSON = LSE / f"HYP04_ANCHOR_SHOCKS_{AS_OF}.json"
OUT_CSV = LSE / f"HYP04_ANCHOR_SHOCKS_{AS_OF}.csv"

MINIMUM_ELIGIBLE_EVENTS = 193

SHOCK_CSV_FIELDS = (
    "event_id", "anchor_ticker", "release_date", "release_session",
    "attributed_session", "prior_session",
    "anchor_return", "benchmark_return", "excess_return", "shock",
    "status", "denial_reasons",
)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _newest_calendar() -> Optional[Path]:
    # Version-aware: a lexical sort picks _v3 over _v10 and rebuilds shocks
    # from a superseded calendar without saying so.
    from .artifacts import newest_in
    return newest_in(LSE, "HYP04_ANCHOR_EVENT_CALENDAR_*.csv")


def _calendar_rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(encoding="utf-8", newline="")))


def _request(calendar: Path):
    rows = _calendar_rows(calendar)
    sessions, provenance = sessions_for_release_dates(
        [r["release_date"] for r in rows])
    req = build_request(rows, sessions=sessions)
    return rows, req, provenance


def emit_request(*, calendar: Optional[Path] = None,
                 out_dir: Path = REQUEST_DIR) -> int:
    cal = calendar or _newest_calendar()
    if cal is None:
        print("REFUSED: no anchor-event calendar artifact on disk")
        return 1

    rows, req, prov = _request(cal)
    written = write_request_csvs(req, out_dir)

    print(f"calendar          : {cal.name}  ({len(rows)} events)")
    print(f"session index     : {prov['sessions_returned']} sessions "
          f"{prov['requested_first']}..{prov['requested_last']}")
    print(f"calendar id       : {prov['calendar_id']}")
    print(f"agrees with authoritative: {prov['agrees']} "
          f"({prov['overlap_sessions']} overlapping sessions, "
          f"{prov['disagreements']} disagreements)")
    print()
    print(f"events resolved   : {len(req.resolved)}")
    print(f"events denied     : {len(req.denied)}")
    if req.denied:
        for reason, n in Counter(
                d.reason[:70] for d in req.denied).most_common():
            print(f"   {n:4d}  {reason}")
    print()
    print(f"tickers           : {len(req.tickers)}  {req.tickers}")
    print(f"TOTAL ROWS        : {req.total_rows}")
    for p, n in written:
        print(f"   {p.name:28s} {n:5d} sessions")
    print()
    print("NOTHING WAS FETCHED. Fill these with run_peer_closes_fetch.")
    return 0


def build(*, calendar: Optional[Path] = None,
          request_dir: Path = REQUEST_DIR,
          out_json: Path = OUT_JSON, out_csv: Path = OUT_CSV) -> list[str]:
    refusals: list[str] = []
    cal = calendar or _newest_calendar()
    if cal is None:
        return ["no anchor-event calendar artifact on disk"]
    for p in (out_json, out_csv):
        if p.exists():
            refusals.append(
                f"{p.name} already exists. Refusing to overwrite a dated "
                "artifact -- delete it deliberately first.")
    if not request_dir.is_dir():
        refusals.append(f"no request directory at {request_dir}")
    if refusals:
        return refusals

    rows, req, prov = _request(cal)

    # Read the FILLED request files back. A session the provider did not return
    # stays absent here -- never zero, never carried forward.
    closes: dict[str, dict[str, float]] = {}
    filled_meta: dict[str, dict[str, int]] = {}
    for path in sorted(request_dir.glob("*_closes_REQUEST.csv")):
        got = 0
        blank = 0
        for r in csv.DictReader(path.open(encoding="utf-8", newline="")):
            tk = (r.get("ticker") or "").strip().upper()
            sess = (r.get("session_date") or "").strip()
            raw = (r.get("close") or "").strip()
            if not tk or not sess:
                continue
            if not raw:
                blank += 1
                continue
            try:
                closes.setdefault(tk, {})[sess] = float(raw)
                got += 1
            except ValueError:
                blank += 1
        filled_meta[path.stem.replace("_closes_REQUEST", "")] = {
            "filled": got, "blank": blank}

    if not closes:
        return [f"no closes found in {request_dir}; fill the request first"]

    shocks, denials = shocks_for_request(req, closes)
    by_id = {s.event_id: s for s in shocks}
    denial_by_id = {d["event_id"]: d for d in denials}
    resolved_by_id = {r.event_id: r for r in req.resolved}
    unresolved_by_id = {d.event_id: d for d in req.denied}

    out_rows: list[dict[str, Any]] = []
    status_counts: Counter = Counter()
    for r in rows:
        eid = r["event_id"]
        base = {
            "event_id": eid,
            "anchor_ticker": r["anchor_ticker"],
            "release_date": r["release_date"],
            "release_session": r["release_session"],
            "attributed_session": "",
            "prior_session": "",
            "anchor_return": "", "benchmark_return": "",
            "excess_return": "", "shock": "",
            "status": "", "denial_reasons": "",
        }
        res = resolved_by_id.get(eid)
        if res is not None:
            base["attributed_session"] = res.attributed_session
            base["prior_session"] = res.prior_session

        if eid in by_id:
            s = by_id[eid]
            base.update({
                "anchor_return": f"{s.anchor_return:.10f}",
                "benchmark_return": f"{s.benchmark_return:.10f}",
                "excess_return": f"{s.excess_return:.10f}",
                "shock": f"{s.shock:.10f}",
                "status": "shock_computed",
            })
        elif eid in denial_by_id:
            base["status"] = "denied_closes"
            base["denial_reasons"] = " | ".join(denial_by_id[eid]["reasons"])
        elif eid in unresolved_by_id:
            base["status"] = "denied_session"
            base["denial_reasons"] = unresolved_by_id[eid].reason
        else:
            base["status"] = "denied_other"
            base["denial_reasons"] = (
                "the event is in the calendar but reached neither a shock nor "
                "a stated denial; this should be impossible and is recorded "
                "rather than dropped")
        status_counts[base["status"]] += 1
        out_rows.append(base)

    members = sorted({r["anchor_ticker"] for r in rows})
    listed = sorted(closes)
    payload = {
        "artifact": out_json.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "HYP-04's FIRST production measurement: the anchor-side earnings "
            "shock, or a stated reason there is none, for every event in the "
            "anchor-event calendar."),
        "what_this_is_not": (
            "It is not an open gate and it does not move C2. "
            "display_gate.current_decision() passes a literal "
            "eligible_event_count=0 and the gate cross-checks that count "
            "against the freeze record's event ids, so C2 and C3 move together "
            "or not at all. Both are separately authorized. The gate stays "
            "CLOSED with C4 MET and four denials."),
        "rules": {
            "shock_rule_id": ANCHOR_SHOCK_RULE_ID,
            "closes_rule_id": ANCHOR_CLOSES_RULE_ID,
            "shock_definition": "abs(anchor_return - beta * benchmark_return)",
            "benchmark_ticker": BENCHMARK_TICKER,
            "benchmark_beta": BENCHMARK_BETA,
            "beta_is_estimated": False,
            "return_basis": RETURN_BASIS,
        },
        "sources": {
            "calendar": cal.name,
            "calendar_sha256": _sha256(cal),
            "calendar_events": len(rows),
            "request_dir": str(request_dir),
            "closes_by_ticker": {t: len(v) for t, v in sorted(closes.items())},
            "request_files": filled_meta,
        },
        "session_index": prov,
        "counts": {
            "events_total": len(rows),
            "shock_computed": status_counts.get("shock_computed", 0),
            "denied_session": status_counts.get("denied_session", 0),
            "denied_closes": status_counts.get("denied_closes", 0),
            "denied_other": status_counts.get("denied_other", 0),
        },
        "every_event_has_a_row": (
            "All calendar events appear, computed or denied. A denied event is "
            "data: it keeps the denominator visible so a sample that shrank "
            "cannot look like one that was always clean."),
        "registered_threshold": {
            "minimum_eligible_events": MINIMUM_ELIGIBLE_EVENTS,
            "shocks_vs_threshold":
                status_counts.get("shock_computed", 0) - MINIMUM_ELIGIBLE_EVENTS,
            "note": (
                "A computed shock satisfies the ANCHOR-side requirement. It is "
                "not the same as C2 being met: C2 reads a count this artifact "
                "does not supply, and C3 must agree with it."),
        },
        "survivorship": survivorship_exposure(members + [BENCHMARK_TICKER],
                                              listed),
        "denial_examples": [
            {k: r[k] for k in ("event_id", "anchor_ticker", "release_date",
                               "status", "denial_reasons")}
            for r in out_rows if r["status"] != "shock_computed"
        ][:25],
    }

    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(SHOCK_CSV_FIELDS))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--emit-request", action="store_true")
    g.add_argument("--build", action="store_true")
    ap.add_argument("--calendar", type=Path, default=None)
    ap.add_argument("--request-dir", type=Path, default=REQUEST_DIR)
    a = ap.parse_args(argv)

    if a.emit_request:
        return emit_request(calendar=a.calendar, out_dir=a.request_dir)

    refusals = build(calendar=a.calendar, request_dir=a.request_dir)
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
