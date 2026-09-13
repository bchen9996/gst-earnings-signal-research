#!/usr/bin/env python3
"""LIVE. Earnings-event shocks for HYP-05's reverse-search-sourced anchor
tickers (DELL, DVN, GOOGL) -- none of which is part of HYP-04's own anchor
universe. MAKES REAL PROVIDER CALLS (SEC submissions, Yahoo closes).

=== WHY THIS EXISTS, AND WHY IT IS NOT A CHANGE TO HYP-04's ANCHOR UNIVERSE ===

`anchor_universe.py`'s AU-1..AU-6 rule answers one specific question: does
THIS ticker's OWN 10-K disclose a named counterparty concentration >= 10%
of consolidated revenue? DELL, DVN and GOOGL are all in the locked-24
screening frame but none satisfies that rule -- their own 10-Ks don't
disclose such a concentration -- which is exactly why
HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29_v2.csv has only 7 anchor tickers and
HYP04_ANCHOR_SHOCKS_2026-08-31.csv has zero rows for these three.

HYP-05's round-4 reverse search asks the OPPOSITE-direction question: does
some SMALL company's OWN 10-K disclose reliance on DELL/DVN/GOOGL as ITS
customer or supplier? That disclosure lives entirely on the small
company's side (CNXN, NGS, TTWO) and requires nothing from DELL/DVN/
GOOGL's own filings. `anchor_universe.py`'s rule is simply not the right
gate for this direction -- it was built to answer a different question,
and evaluating it here would test something irrelevant to what HYP-05
actually needs: real, computable earnings-event shocks for these 3
tickers, full stop.

This module therefore reuses HYP-04's earnings-event/shock machinery
exactly -- `earnings_events`'s era-aware Item 12/2.02 selection,
`anchor_closes`'s request-building and shock computation, `anchor_shock`'s
fixed-beta excess-return formula, `sessions`'s XNYS session index -- but
WITHOUT `anchor_universe`'s membership-interval filter, because these
tickers are not "temporarily an anchor while a relationship holds"; they
are simply themselves, at every date they have been the filer EDGAR's
current ticker mapping resolves them to. Every event dropped by dedup is
recorded, same as `anchor_calendar.DEDUP_RULE` (this module applies the
identical rule directly to unwrapped `CandidateEvent`s, since there is no
membership interval to place them into).

Confirmed safe from a merger/rename lineage hazard (see
hyp04-linkage-lineage-rule), by reading each CIK's actual `formerNames`
history rather than assuming: CNXN's DELL relationship is as_of
2022-03-14 -- CIK 0001571996 has been ONE continuous filer since the 2013
Dell LBO, first as "Denali Holding Inc." (2013-07-24 onward) and RENAMED,
not re-incorporated, to "Dell Technologies Inc" in 2016; 2022 is 6 years
inside that renamed era. TTWO's GOOGL relationship is as_of 2023-05-26 --
Alphabet Inc, CIK 0001652044, created by the October 2015 holding-company
restructuring, with candidate events starting exactly there (2015-10-22)
and none earlier, so no pre-restructuring Google Inc. filing is or could
be mixed in. NGS's DVN relationship is as_of 2010-03-04 -- Devon Energy
Corp/DE (CIK 0001090012) has been one continuous filer since 1999 with no
merger in between. The current ticker->CIK mapping is the correct entity
in all three cases.

=== SCOPE ===

Exactly the 3 tickers HYP-05's round-4 reverse search actually needs.
Not a general-purpose "add any ticker as an anchor" tool -- extending to a
new ticker later means re-examining this docstring's reasoning, not just
appending to a tuple.

=== NEVER TOUCHES A HYP-04 ARTIFACT ===

Writes only HYP05_ADDITIONAL_ANCHOR_SHOCKS_<date>.{json,csv}. Does not
read, and cannot write, HYP04_ANCHOR_EVENT_CALENDAR_*.csv or
HYP04_ANCHOR_SHOCKS_2026-08-31.csv. Moves no HYP-04 gate condition.

  python -m hyp04_supply_chain_hedge.run_hyp05_additional_anchor_shocks \
    --yes-run-live
"""
from __future__ import annotations

import argparse
import hashlib
import json
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .anchor_closes import build_request, shocks_for_request
from .anchor_shock import (
    ANCHOR_SHOCK_RULE_ID,
    BENCHMARK_BETA,
    BENCHMARK_TICKER,
    RETURN_BASIS,
)
from .earnings_events import (
    ANCHOR_EVENT_RULE_ID,
    CandidateEvent,
    candidate_from_record,
    results_item_verdict,
)
from .sessions import sessions_for_release_dates

LSE = Path("Live Signal Engine")
AS_OF = "2026-09-12"
OUT_JSON = LSE / f"HYP05_ADDITIONAL_ANCHOR_SHOCKS_{AS_OF}.json"
OUT_CSV = LSE / f"HYP05_ADDITIONAL_ANCHOR_SHOCKS_{AS_OF}.csv"

CONTACT = "bchen9996 bchen9996@gmail.com"
CACHE_DIR = Path(".edgar_cache")

# Exactly the 3 tickers HYP-05's round-4 reverse search needs anchor-shock
# computation for. See module docstring for why they have zero rows in
# HYP04_ANCHOR_SHOCKS_2026-08-31.csv despite being in the locked-24 frame,
# and for the merger/rename lineage check already done for each.
ADDITIONAL_ANCHOR_TICKERS: tuple[str, ...] = ("DELL", "DVN", "GOOGL")

SHOCK_CSV_FIELDS = (
    "event_id", "anchor_ticker", "release_date", "release_session",
    "attributed_session", "prior_session",
    "anchor_return", "benchmark_return", "excess_return", "shock",
    "status", "denial_reasons",
)

DEDUP_RULE = ("one anchor event per (anchor_ticker, release_date); the "
              "earliest ACCEPTANCE wins, ties broken on accession -- the "
              "identical rule anchor_calendar.DEDUP_RULE states, applied "
              "here directly to unwrapped CandidateEvents because there is "
              "no membership interval to place them into")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _iso(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def _dedup_events(
    events: list[CandidateEvent],
) -> tuple[list[CandidateEvent], list[dict[str, Any]]]:
    """DEDUP_RULE, applied directly to CandidateEvent. See module docstring."""
    by_key: dict[tuple[str, str], list[CandidateEvent]] = {}
    for e in events:
        by_key.setdefault((e.anchor_ticker, e.release_date), []).append(e)

    kept: list[CandidateEvent] = []
    dropped: list[dict[str, Any]] = []
    for key in sorted(by_key):
        group = sorted(
            by_key[key],
            key=lambda e: ((e.acceptance_utc or "").strip() or "9999",
                          e.accession or ""))
        kept.append(group[0])
        for loser in group[1:]:
            dropped.append({
                "event_id": loser.event_id,
                "anchor_ticker": loser.anchor_ticker,
                "release_date": loser.release_date,
                "superseded_accession": loser.accession,
                "kept_accession": group[0].accession,
                "reason": DEDUP_RULE,
            })
    return kept, dropped


def candidate_events_for_ticker(
    client, ticker: str,
) -> tuple[Optional[list[CandidateEvent]], list[dict[str, Any]]]:
    """Every real, era-aware, deduplicated 8-K results-filing candidate
    event for `ticker`'s WHOLE filing history under its CURRENT CIK -- no
    membership-interval filter, unlike `anchor_calendar.derive_anchor_
    calendar`. Returns (None, []) if the ticker has no CIK on record."""
    from .anchor_calendar import _blocks  # reused, not duplicated

    cik = client.cik_for(ticker)
    if cik is None:
        return None, []

    found: list[CandidateEvent] = []
    for blk in _blocks(client, cik):
        forms = blk.get("form") or []
        n = len(forms)
        for k, form in enumerate(forms):
            if form != "8-K":
                continue
            items = (blk.get("items") or [""] * n)[k]
            rd = (blk.get("reportDate") or [""] * n)[k] \
                or (blk.get("filingDate") or [""] * n)[k]
            if _iso(rd) is None:
                continue
            modern, legacy, _note = results_item_verdict(items, rd)
            if not (modern or legacy):
                continue
            ev = candidate_from_record(ticker, {
                "accessionNumber": blk["accessionNumber"][k],
                "filingDate": (blk.get("filingDate") or [""] * n)[k],
                "reportDate": rd,
                "acceptanceDateTime":
                    (blk.get("acceptanceDateTime") or [""] * n)[k],
                "items": items,
            })
            found.append(ev)

    kept, dropped = _dedup_events(found)
    kept.sort(key=lambda e: e.release_date)
    return kept, dropped


def build(*, tickers: tuple[str, ...] = ADDITIONAL_ANCHOR_TICKERS,
          contact: str = CONTACT, cache_dir: Path = CACHE_DIR,
          out_json: Path = OUT_JSON, out_csv: Path = OUT_CSV) -> list[str]:
    refusals: list[str] = []
    for p in (out_json, out_csv):
        if p.exists():
            refusals.append(
                f"{p.name} already exists. Refusing to overwrite a dated "
                "artifact -- delete it deliberately first if that is "
                "really intended.")
    if refusals:
        return refusals

    from .edgar_linkage import EdgarClient, FilingCache
    from .run_peer_closes_fetch import fetch_closes

    client = EdgarClient(contact, cache=FilingCache(cache_dir))

    all_events: list[CandidateEvent] = []
    dropped_by_ticker: dict[str, list[dict[str, Any]]] = {}
    no_cik: list[str] = []
    for tk in tickers:
        kept, dropped = candidate_events_for_ticker(client, tk)
        if kept is None:
            no_cik.append(tk)
            continue
        all_events.extend(kept)
        dropped_by_ticker[tk] = dropped

    if no_cik:
        return [f"no CIK on record for {t!r}" for t in no_cik]
    if not all_events:
        return ["no candidate 8-K results filings found for any of "
                + ", ".join(tickers)]

    sessions, session_prov = sessions_for_release_dates(
        [e.release_date for e in all_events])
    req = build_request([e.as_row() for e in all_events], sessions=sessions)

    closes: dict[str, dict[str, float]] = {}
    fetch_errors: dict[str, str] = {}
    for tk in req.tickers:
        sess_needed = req.sessions_by_ticker.get(tk, [])
        if not sess_needed:
            continue
        first, last = date.fromisoformat(min(sess_needed)), date.fromisoformat(max(sess_needed))
        try:
            raw = fetch_closes(tk, first, last, auto_adjust=False)
        except Exception as exc:                       # noqa: BLE001
            fetch_errors[tk] = f"{type(exc).__name__}: {exc}"
            continue
        closes[tk] = {d.isoformat(): c for d, c in raw.items()}

    shocks, shock_denials = shocks_for_request(req, closes)
    by_id = {s.event_id: s for s in shocks}
    denial_by_id = {d["event_id"]: d for d in shock_denials}
    resolved_by_id = {r.event_id: r for r in req.resolved}
    unresolved_by_id = {d.event_id: d for d in req.denied}

    out_rows: list[dict[str, Any]] = []
    status_counts: Counter = Counter()
    for ev in all_events:
        eid = ev.event_id
        base = {
            "event_id": eid, "anchor_ticker": ev.anchor_ticker,
            "release_date": ev.release_date,
            "release_session": ev.release_session,
            "attributed_session": "", "prior_session": "",
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
                "reached neither a shock nor a stated denial; this should "
                "be impossible and is recorded rather than dropped")
        status_counts[base["status"]] += 1
        out_rows.append(base)

    payload = {
        "artifact": out_json.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-05",
        "what_this_is": (
            "Real earnings-event shocks for DELL, DVN and GOOGL -- the 3 "
            "anchor tickers HYP-05's round-4 reverse search sourced peers "
            "(CNXN, NGS, TTWO respectively) for, and which have zero rows "
            "in HYP-04's own HYP04_ANCHOR_SHOCKS_2026-08-31.csv because "
            "they never qualified under anchor_universe.py's DIFFERENT, "
            "own-disclosure-direction rule. See module docstring."),
        "what_this_is_not": (
            "This does NOT add DELL, DVN or GOOGL to HYP-04's anchor "
            "universe, does not touch HYP04_ANCHOR_EVENT_CALENDAR_*.csv or "
            "HYP04_ANCHOR_SHOCKS_2026-08-31.csv (neither read nor "
            "writable by this module), and moves no HYP-04 gate "
            "condition. It is HYP-05-side evidence only."),
        "rules": {
            "shock_rule_id": ANCHOR_SHOCK_RULE_ID,
            "event_rule_id": ANCHOR_EVENT_RULE_ID,
            "dedup_rule": DEDUP_RULE,
            "shock_definition": "abs(anchor_return - beta * benchmark_return)",
            "benchmark_ticker": BENCHMARK_TICKER,
            "benchmark_beta": BENCHMARK_BETA,
            "beta_is_estimated": False,
            "return_basis": RETURN_BASIS,
        },
        "lineage_check": (
            "CNXN/DELL as_of 2022-03-14 -> CIK 0001571996, one continuous "
            "filer since the 2013 Dell LBO, RENAMED (not re-incorporated) "
            "from 'Denali Holding Inc.' to 'Dell Technologies Inc' in "
            "2016 -- 2022 is 6 years inside the renamed era. TTWO/GOOGL "
            "as_of 2023-05-26 -> Alphabet Inc, CIK 0001652044, created by "
            "the October 2015 holding-company restructuring; candidate "
            "events start exactly there (2015-10-22) with nothing earlier, "
            "so no pre-restructuring Google Inc. filing is mixed in. "
            "NGS/DVN as_of 2010-03-04 -> Devon Energy Corp/DE, CIK "
            "0001090012, one continuous filer since 1999. Checked against "
            "each CIK's actual formerNames history, not assumed. The "
            "current ticker->CIK mapping is the correct entity in all "
            "three cases."),
        "sources": {
            "edgar_cache": str(cache_dir),
            "live_requests_made": client.requests_made,
            "tickers_requested": list(tickers),
            "candidate_events_per_ticker": {
                tk: sum(1 for e in all_events if e.anchor_ticker == tk.upper())
                for tk in tickers},
            "duplicate_filings_superseded": dropped_by_ticker,
            "fetch_errors": fetch_errors,
        },
        "session_index": session_prov,
        "counts": {
            "events_total": len(out_rows),
            "shock_computed": status_counts.get("shock_computed", 0),
            "denied_session": status_counts.get("denied_session", 0),
            "denied_closes": status_counts.get("denied_closes", 0),
            "denied_other": status_counts.get("denied_other", 0),
        },
        "every_event_has_a_row": (
            "All candidate events appear, computed or denied -- same "
            "discipline as make_anchor_shocks.py."),
    }

    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
                        encoding="utf-8")
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(SHOCK_CSV_FIELDS))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes-run-live", action="store_true")
    ap.add_argument("--contact", default=CONTACT)
    ap.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    ap.add_argument("--out-json", type=Path, default=OUT_JSON)
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV)
    a = ap.parse_args(argv)

    if not a.yes_run_live:
        print(f"DRY RUN. Would compute earnings-event shocks for: "
              f"{', '.join(ADDITIONAL_ANCHOR_TICKERS)}")
        print("Re-run with --yes-run-live to make real provider calls.")
        return 0

    refusals = build(contact=a.contact, cache_dir=a.cache_dir,
                     out_json=a.out_json, out_csv=a.out_csv)
    if refusals:
        print("REFUSED:")
        for r in refusals:
            print("  -", r)
        return 1
    print(f"wrote {a.out_json}")
    print(f"  sha256 {_sha256(a.out_json)}")
    print(f"wrote {a.out_csv}")
    print(f"  sha256 {_sha256(a.out_csv)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
