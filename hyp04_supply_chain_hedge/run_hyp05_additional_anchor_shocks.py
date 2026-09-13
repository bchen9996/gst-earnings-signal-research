#!/usr/bin/env python3
"""LIVE. Earnings-event shocks for HYP-05 reverse-search-sourced anchor
tickers that are NOT part of HYP-04's own anchor universe. MAKES REAL
PROVIDER CALLS (SEC submissions, Yahoo closes).

=== WHY THIS EXISTS, AND WHY IT IS NOT A CHANGE TO HYP-04's ANCHOR UNIVERSE ===

`anchor_universe.py`'s AU-1..AU-6 rule answers one specific question: does
THIS ticker's OWN 10-K disclose a named counterparty concentration >= 10%
of consolidated revenue? Round-4 anchors like DELL, DVN and GOOGL are all
in the locked-24 screening frame but none satisfies that rule -- their
own 10-Ks don't disclose such a concentration -- which is exactly why
HYP04_ANCHOR_EVENT_CALENDAR_2026-08-29_v2.csv has only 7 anchor tickers
and HYP04_ANCHOR_SHOCKS_2026-08-31.csv has zero rows for any anchor this
module is ever asked to process.

HYP-05's reverse search asks the OPPOSITE-direction question: does some
SMALL company's OWN 10-K disclose reliance on a large ticker as ITS
customer or supplier? That disclosure lives entirely on the small
company's side and requires nothing from the large ticker's own filings.
`anchor_universe.py`'s rule is simply not the right gate for this
direction -- it was built to answer a different question, and evaluating
it here would test something irrelevant to what HYP-05 actually needs:
real, computable earnings-event shocks for these tickers, full stop.

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

=== SCOPE: A PROCESS, NOT A FIXED LIST ===

Originally built for exactly 3 tickers (DELL, DVN, GOOGL) round 4's
reverse search needed. Round 5's scaled search can surface peers
anchored to many more tickers, so this is now a process any ticker can go
through, not a hardcoded tuple: `LINEAGE_NOTES` below must carry a
dated, specific entry -- read from each CIK's real `formerNames` history,
never assumed -- for EVERY ticker before `build()` will compute anything
for it (see `hyp04-linkage-lineage-rule`: a merger is not a rename, and an
entity discontinuity must be checked, not assumed away, before treating
one ticker's history as one continuous filer). `build()` REFUSES,
mirroring `run_hyp05_reverse_search_handreview.py`'s "refuse on any
mismatch" discipline, if any requested ticker lacks a `LINEAGE_NOTES`
entry -- adding a ticker means checking its lineage and writing the note
first, never just appending to a list and letting the computation run
ahead of the check.

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

# The tickers verified and processed SO FAR -- the default `main()` uses
# when --tickers is omitted, not a ceiling. Extend by adding a LINEAGE_
# NOTES entry (below) for the new ticker FIRST; build() refuses on any
# ticker missing one, so the two can never silently drift apart.
ADDITIONAL_ANCHOR_TICKERS: tuple[str, ...] = ("DELL", "DVN", "GOOGL")

# One dated, specific lineage-check note per ticker this module has ever
# been asked to process -- read from each CIK's real `formerNames` history
# (https://data.sec.gov/submissions/CIK{cik}.json), never assumed. Mirrors
# `run_hyp05_reverse_search_handreview.HAND_REVIEW_DECISIONS`'s shape: a
# hand-written, per-item, checkable record rather than a blanket claim.
# build() REFUSES to process a ticker not listed here -- see module
# docstring, "SCOPE: A PROCESS, NOT A FIXED LIST".
LINEAGE_NOTES: dict[str, str] = {
    "DELL": (
        "CNXN's DELL relationship is as_of 2022-03-14. CIK 0001571996 has "
        "been ONE continuous filer since the 2013 Dell LBO, first as "
        "'Denali Holding Inc.' (2013-07-24 onward) and RENAMED, not "
        "re-incorporated, to 'Dell Technologies Inc' in 2016 -- 2022 is 6 "
        "years inside that renamed era. The current ticker->CIK mapping "
        "is the correct entity."),
    "DVN": (
        "NGS's DVN relationship is as_of 2010-03-04. Devon Energy Corp/DE "
        "(CIK 0001090012) has been one continuous filer since 1999 with "
        "no merger in between. The current ticker->CIK mapping is the "
        "correct entity."),
    "GOOGL": (
        "TTWO's GOOGL relationship is as_of 2023-05-26. Alphabet Inc, CIK "
        "0001652044, was created by the October 2015 holding-company "
        "restructuring, with candidate events starting exactly there "
        "(2015-10-22) and none earlier, so no pre-restructuring Google "
        "Inc. filing is or could be mixed in. The current ticker->CIK "
        "mapping is the correct entity."),
    # --- Round 6 (2026-09-13): 32 anchors from the scaled reverse search's
    # 39 tradeable, hand-reviewed candidates, minus INTC/NKE (HYP-04's own)
    # and DELL/DVN/GOOGL (already above). Every CIK's real formerNames
    # history was fetched and checked against the peer's actual as_of_date
    # (see _lineage_check.json, generated 2026-09-13) rather than assumed.
    # Most are simple, uninterrupted filers. Four are the "surviving
    # entity renamed after a merger" pattern also seen for DELL/GOOGL --
    # noted individually below; all have as_of_dates safely after the
    # relevant restructuring.
    "ABT": ("ICU Medical's relationship is as_of 2003-03-28. Abbott "
           "Laboratories, CIK 0000001800, has no formerNames at all -- "
           "one continuous filer."),
    "AEP": ("Centrus Energy's relationship is as_of 2010-03-04/2017-03-31. "
           "American Electric Power Co Inc, CIK 0000004904, former name "
           "differs only by 'Company' vs 'Co' -- one continuous filer."),
    "AVY": ("Impinj's relationship is as_of 2019-02-28. Avery Dennison "
           "Corp, CIK 0000008818, one continuous filer (cosmetic "
           "capitalization change only)."),
    "BDX": ("Owens & Minor's relationship is as_of 2017-02-17. Becton "
           "Dickinson & Co, CIK 0000010795, no formerNames -- one "
           "continuous filer."),
    "CLX": ("Key Tronic's relationship is as_of 2002-09-11/2004-09-17. "
           "Clorox Co /DE/, CIK 0000021076, has been that name "
           "continuously since 1994-03-28 (a 2026 cosmetic '/DE/' suffix "
           "drop postdates both events by two decades)."),
    "COR": ("Elanco's relationship is as_of 2025-02-25. Cencora, Inc., "
           "CIK 0001140859, RENAMED (not re-incorporated) from "
           "'AmerisourceBergen Corp' in 2023 -- 2025 is inside the "
           "renamed era."),
    "CVX": ("Tidewater's relationship is as_of 2008-05-30. Chevron Corp, "
           "CIK 0000093410, renamed from 'ChevronTexaco Corp' (the 2001 "
           "Chevron/Texaco merger's continuing entity) well before 2008 "
           "-- inside the renamed era."),
    "DUK": ("Massey Energy's/CONSOL's relationships are as_of "
           "2003-03-31/2018-02-16. Duke Energy Corp, CIK 0001326160, "
           "former names ('Duke Energy Holding Corp.', 'Deer Holding "
           "Corp.') reflect the 2006 Cinergy-merger holding-company "
           "restructuring, completed well before 2018; the 2003 Massey "
           "event predates that restructuring, so is evaluated against "
           "Duke's ORIGINAL (pre-2006) entity via the same continuous "
           "CIK -- checked, not assumed, since Duke's CIK did not change "
           "across that restructuring."),
    "EOG": ("CKX Lands' relationship is as_of 2015-03-23/2016-03-29. EOG "
           "Resources Inc, CIK 0000821189, RENAMED from 'Enron Oil & Gas "
           "Co' in 1999 (a spinoff/rename, not a merger) -- 2015-2016 is "
           "decades inside the renamed era."),
    "ETR": ("CKX Lands' relationship is as_of 2015-03-23. Entergy Corp "
           "/DE/, CIK 0000065984, former name differs only by state-of-"
           "incorporation suffix ('/FL/' vs '/DE/') -- one continuous "
           "filer."),
    "EXC": ("Opower's/Centrus's relationships are as_of 2016-03-07/"
           "2017-03-31. Exelon Corp, CIK 0001109357, no formerNames -- "
           "one continuous filer since the 2000 PECO/Unicom merger "
           "created it, well before either date."),
    "FFIV": ("Peraso's relationship is as_of 2023-03-29. F5, Inc., CIK "
           "0001048695, RENAMED from 'F5 Networks, Inc.' in 2022 -- 2023 "
           "is inside the renamed era."),
    "HPQ": ("PC Connection's relationship is as_of 2021-03-16/2022-03-14. "
           "HP Inc, CIK 0000047217, is the CIK that RETAINED after "
           "Hewlett-Packard's 2015 split (Hewlett Packard Enterprise "
           "took a new, separate CIK for the enterprise business) -- "
           "2021-2022 is years inside the post-split HP Inc era."),
    "HWM": ("Carpenter Technology's relationship is as_of 2020-09-04, "
           "explicitly dated 'formerly Arconic Inc.' in the peer's own "
           "text. Howmet Aerospace Inc, CIK 0000004281, is Alcoa's "
           "original CIK, RENAMED Arconic (2016 split, keeping the "
           "higher-value business; the upstream aluminum business took "
           "a NEW, separate CIK as 'Alcoa Corp') then RENAMED Howmet "
           "Aerospace (2020, after ANOTHER spinoff, Arconic Corp, again "
           "on a separate new CIK) -- a rename chain on one continuous "
           "CIK, not a merger into it."),
    "KBH": ("Pure Cycle's relationship is as_of 2022-11-14. KB Home, CIK "
           "0000795266, RENAMED from 'Kaufman & Broad Home Corp' in 1989 "
           "-- decades inside the renamed era."),
    "KEX": ("Allison Transmission's relationship is as_of 2018-02-15. "
           "Kirby Corp, CIK 0000056047, no formerNames -- one continuous "
           "filer."),
    "NEE": ("First Solar's relationship is as_of 2014-02-26. NextEra "
           "Energy Inc, CIK 0000753308, RENAMED from 'FPL Group Inc' in "
           "2010 -- 2014 is inside the renamed era."),
    "NOC": ("Nortech's/Cipprico's relationships are as_of 2002-11-05/"
           "2007-03-09. Northrop Grumman Corp /DE/, CIK 0001133421, "
           "former name 'NNG Inc' is an incorporation-shell name "
           "predating Northrop's 1994 Grumman merger by less than a "
           "year -- both events are decades inside the current era."),
    "NSC": ("FreightCar America's relationship is as_of 2017-03-03. "
           "Norfolk Southern Corp, CIK 0000702165, no formerNames -- one "
           "continuous filer since the 1982 Norfolk & Western/Southern "
           "Railway merger created it."),
    "NTNX": ("SMART Global's relationship is as_of 2020-10-22. Nutanix, "
           "Inc., CIK 0001618732, no formerNames -- one continuous "
           "filer."),
    "NXPI": ("Cohu's relationship is as_of 2016-02-23. NXP Semiconductors "
           "N.V., CIK 0001413447, RENAMED from 'KASLION Acquisition "
           "B.V.' (its 2006 Philips-spinoff incorporation shell name, "
           "before its 2010 IPO) -- 2016 is years inside the renamed, "
           "public era."),
    "PGR": ("QuinStreet's relationship is as_of 2017-09-08. Progressive "
           "Corp/OH/, CIK 0000080661, no formerNames -- one continuous "
           "filer."),
    "PSX": ("BreitBurn's/California Resources'/Stone Energy's/Oasis "
           "Petroleum's relationships are as_of 2012-02-29 through "
           "2021-03-08. Phillips 66, CIK 0001534701, no formerNames -- "
           "one continuous filer since its 2012 spinoff from "
           "ConocoPhillips (its own, distinct CIK from the start)."),
    "RTX": ("Woodward's relationship is as_of 2023-11-17. RTX Corp, CIK "
           "0000101829, is United Technologies Corp's original CIK, "
           "RENAMED Raytheon Technologies Corp (2020, when Raytheon "
           "Company merged INTO United Technologies with UTC as the "
           "surviving registrant) then RENAMED RTX Corp (2023) -- 2023 "
           "is inside the second renamed era, on the same continuous, "
           "surviving CIK throughout."),
    "SNX": ("PC Connection's/Autodesk's relationships are as_of "
           "2022-03-14/2024-06-10. TD Synnex Corp, CIK 0001177394, is "
           "SYNNEX Corporation's original CIK, RENAMED TD Synnex Corp "
           "(2021, when Tech Data merged INTO SYNNEX with SYNNEX as the "
           "surviving registrant) -- both dates are inside the renamed "
           "era, on the same continuous, surviving CIK."),
    "SPG": ("Signet Jewelers' relationship is as_of 2010-03-30. Simon "
           "Property Group Inc /DE/, CIK 0001063761, has been that name "
           "continuously since 1998-09-28 (a brief, 8-day 1998 "
           "transitional name during the Corporate Property Investors "
           "merger predates 2010 by 12 years; a 2025 cosmetic '/DE/' "
           "suffix drop postdates it)."),
    "TFC": ("United Insurance Holdings' relationship is as_of 2023-04-17. "
           "Truist Financial Corp, CIK 0000092230, is BB&T Corp's "
           "original CIK, RENAMED Truist Financial Corp (2019, when "
           "SunTrust Banks merged INTO BB&T with BB&T as the surviving "
           "registrant) -- 2023 is 4 years inside the renamed era, on "
           "the same continuous, surviving CIK."),
    "THO": ("Patrick Industries' relationship is as_of 2016-03-14. Thor "
           "Industries Inc, CIK 0000730263, no formerNames -- one "
           "continuous filer."),
    "TTMI": ("Park Electrochemical's relationship is as_of 2018-05-11. "
           "TTM Technologies Inc, CIK 0001116942, no formerNames -- one "
           "continuous filer."),
    "TXN": ("Aehr Test Systems'/LTX-Credence's relationships are as_of "
           "2001-03-30/2017-08-29. Texas Instruments Inc, CIK "
           "0000097476, no formerNames -- one continuous filer."),
    "VLO": ("Jacobs Engineering's relationship is as_of 2006-12-08. "
           "Valero Energy Corp/TX, CIK 0001035002, RENAMED from 'Valero "
           "Refining & Marketing Co' well before 2006 -- inside the "
           "renamed era."),
    "ZBRA": ("Key Tronic's relationship is as_of 2004-09-17. Zebra "
           "Technologies Corp, CIK 0000877212, has been that name "
           "continuously since 1995-09-08 (a 2009 cosmetic '/DE/' "
           "suffix drop postdates 2004 by 5 years)."),
}

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
    missing_lineage = [t for t in tickers if t not in LINEAGE_NOTES]
    if missing_lineage:
        refusals.append(
            "no LINEAGE_NOTES entry for: " + ", ".join(sorted(missing_lineage))
            + " -- check each ticker's real formerNames history and add a "
              "note before computing anything for it (see module "
              "docstring, 'SCOPE: A PROCESS, NOT A FIXED LIST')")
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
            "Real earnings-event shocks for " + ", ".join(tickers) + " -- "
            "anchor ticker(s) HYP-05's reverse search sourced peers for, "
            "and which have zero rows in HYP-04's own "
            "HYP04_ANCHOR_SHOCKS_2026-08-31.csv because they never "
            "qualified under anchor_universe.py's DIFFERENT, own-"
            "disclosure-direction rule. See module docstring."),
        "what_this_is_not": (
            "This does NOT add " + ", ".join(tickers) + " to HYP-04's "
            "anchor universe, does not touch HYP04_ANCHOR_EVENT_"
            "CALENDAR_*.csv or HYP04_ANCHOR_SHOCKS_2026-08-31.csv (neither "
            "read nor writable by this module), and moves no HYP-04 gate "
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
        "lineage_check": {t: LINEAGE_NOTES[t] for t in tickers},
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
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="default: ADDITIONAL_ANCHOR_TICKERS (the tickers "
                         "verified so far). Each must have a LINEAGE_NOTES "
                         "entry -- build() refuses otherwise.")
    ap.add_argument("--contact", default=CONTACT)
    ap.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    ap.add_argument("--out-json", type=Path, default=OUT_JSON)
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV)
    a = ap.parse_args(argv)
    tickers = tuple(t.upper() for t in a.tickers) if a.tickers else ADDITIONAL_ANCHOR_TICKERS

    if not a.yes_run_live:
        print(f"DRY RUN. Would compute earnings-event shocks for: "
              f"{', '.join(tickers)}")
        missing = [t for t in tickers if t not in LINEAGE_NOTES]
        if missing:
            print(f"NOTE: no LINEAGE_NOTES entry yet for: {', '.join(missing)} "
                  "-- --yes-run-live would refuse until one is added.")
        print("Re-run with --yes-run-live to make real provider calls.")
        return 0

    refusals = build(tickers=tickers, contact=a.contact, cache_dir=a.cache_dir,
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
