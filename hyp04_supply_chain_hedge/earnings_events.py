#!/usr/bin/env python3
"""CANDIDATE anchor events for HYP-04, derived from 8-K Item 2.02 filings.

=== THESE ARE CANDIDATES, NOT ELIGIBLE EVENTS ===

Item 2.02 of Form 8-K is "Results of Operations and Financial Condition" --
the filing obligation a company discharges when it releases earnings. Walking
it yields the dates on which an anchor actually reported.

That is ALL it yields. A candidate event is not an eligible event:

  * eligibility is screened by `gst_market_response.completeness`, against
    HYP-01's rules, not here
  * `eligible_event_counts` in the registry stays whatever the registry says;
    writing this file does not change it
  * display-gate condition C2 counts ELIGIBLE anchor events and is not moved
    by anything in this module

Producing this list is the step BEFORE screening, not a substitute for it.

=== THE FILING DATE IS NOT THE EVENT DATE ===

This is the defect this module exists to avoid, and it is invisible on half
the sample.

SEC stamps a submission accepted after 17:30 ET with the NEXT business day as
its `filingDate`. `reportDate` -- the 8-K's "date of earliest event reported"
-- is the day the results were actually released.

Measured 2026-08-23:

    MCK  accepted 16:05-16:07 ET   reportDate == filingDate   on every event
    PKG  accepted 17:48-18:18 ET   reportDate == filingDate    on NO event

PKG releases after the 17:30 cutoff, so every PKG `filingDate` is one calendar
day after the release. Using it would put every PKG anchor event one day late,
and after the AMC next-session rule, one SESSION late. MCK would look perfect
throughout, because MCK files before the cutoff.

So `release_date` here is ALWAYS `reportDate`. `filing_date` is carried only
as evidence, and the suite pins a PKG-shaped record to the report date.

=== HOW BMO/AMC IS DERIVED ===

`acceptanceDateTime` is UTC (the record carries a Z). It is converted to
America/New_York -- which handles EST/EDT, and both appear in the real data --
and compared against the release date:

    accepted >= 16:00 ET on the release date   -> AMC
    accepted <  09:30 ET on the release date   -> BMO
    accepted between 09:30 and 16:00 ET        -> UNKNOWN (intraday)
    accepted on a DIFFERENT date               -> UNKNOWN (cannot infer)

Acceptance time is when the 8-K reached EDGAR, not when the wire went out.
For Item 2.02 the two are close in practice -- Reg FD pushes companies to
furnish at release -- but "close in practice" is not "equal", so the bands are
deliberately wide and the middle of the day resolves to UNKNOWN rather than to
a guess. Every classification carries the timestamp it was derived from, so a
reader can overrule it.

UNKNOWN IS NOT A DEFAULT THAT LATER GETS FILLED IN. It is a refusal to guess.
Downstream, an unresolved release session must deny -- consistent with
pair_eligibility's treatment of an unknown as-of basis.

=== A BUNDLED 8-K CAN CARRY THE WRONG reportDate ===

Found by running this, not by reasoning about it.

`reportDate` is the date of the EARLIEST event reported, and an 8-K may report
several. When a company bundles an earnings release with an unrelated earlier
item, `reportDate` is that earlier item's date -- not the release. Both
occurrences in the real MCK/PKG walk (2026-08-23) have this shape:

    MCK  reportDate 2023-10-27  items 2.02,5.02,7.01,9.01  accepted 2023-11-01
    PKG  reportDate 2020-07-24  items 2.02,2.06,9.01       accepted 2020-07-28

5.02 is a director/officer change; 2.06 is a material impairment. In each case
the earnings release is the ACCEPTANCE date and `reportDate` belongs to the
other item.

These are not repaired by the CLASSIFIER. Both resolve to UNKNOWN -- the
acceptance falls on a different day than `reportDate`, which is exactly the
condition it refuses to infer through -- and both carry `non_standard_items`,
so the shape routes itself to a human. Guessing which of several bundled items
a `reportDate` refers to is not something this module can do from the metadata,
and a wrong guess is a mis-dated anchor event: the failure it exists to prevent.

They are repaired by a HUMAN, through the addenda file (see `load_addenda`).
Both were settled on 2026-08-24 by reading the press-release exhibits -- MCK to
2023-11-01 AMC, PKG to 2020-07-28 AMC -- and each SUPERSEDES its mis-dated
derived row rather than sitting alongside it. That division is the point: the
metadata cannot decide, the filing can, and the answer carries a citation.

=== ITEM 2.02 IS A FLOOR, NOT A CENSUS ===

Also found by running this. A company can file its earnings release WITHOUT
tagging Item 2.02, and at least one did.

    MCK  2020-02-04  accession 0000927653-20-000013  items: "9.01" ONLY

That filing is `mck8-k12312019.htm` -- named for the quarter ending
2019-12-31 -- carrying a 1 MB press-release exhibit, and its SGML header reads
`ITEM INFORMATION: Financial Statements and Exhibits` with no Item 2.02. It is
McKesson's Q3 FY2020 earnings release, accepted 07:10 ET, which makes it BMO
and consistent with MCK's 2018-2021 pre-open cadence. The Item 2.02 filter
cannot see it.

So an absent candidate is NOT evidence the company did not report -- the same
caveat `edgar_linkage` records about concentration disclosure.

`find_cadence_gaps()` exists because of this. It reports any interval between
consecutive releases longer than a quarter, which is what a missed release
looks like. It does NOT try to fill them: the reliable signal for "this
9.01-only filing is really an earnings release" is the document naming, which
is per-filer convention and would silently mis-tag some other filing as an
anchor event. Detect and route to a human; do not guess.

Measured on the 2026-08-23 walk: MCK one gap (the release above), PKG none.

=== WHAT STILL HAS TO HAPPEN BY HAND ===

A candidate carries `flags` for anything that does not look like a routine
quarterly release. "2.02,9.01" is the standard shape (9.01 is just the exhibit
attaching the press release). Extra items -- 8.01 in particular -- often mark
an investor day or a guidance update rather than a quarterly report. Those are
FLAGGED, never dropped: dropping them silently would be this project's
recurring failure in a new place.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from .edgar_linkage import (
    EdgarClient,
    CONTACT_REQUIRED_MESSAGE,
    SUBMISSIONS_URL,
    SUBMISSIONS_EXTRA_URL,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

EASTERN = ZoneInfo("America/New_York")

ITEM_RESULTS = "2.02"
ITEM_EXHIBITS = "9.01"
STANDARD_ITEMS = frozenset({ITEM_RESULTS, ITEM_EXHIBITS})

SESSION_BMO = "BMO"
SESSION_AMC = "AMC"
SESSION_UNKNOWN = "UNKNOWN"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MARKET_OPEN_ET = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)

FLAG_NON_STANDARD_ITEMS = "non_standard_items"
FLAG_SESSION_UNRESOLVED = "release_session_unresolved"
FLAG_REPORT_BEFORE_FILING = "report_date_precedes_filing_date"

# How an event got here. A curated row must never be mistaken for a derived
# one: derived rows are reproducible by re-running the walk, curated rows are
# somebody's reading of a filing and carry a citation instead.
PROVENANCE_DERIVED = "derived_8k_item_2_02"
PROVENANCE_CURATED = "curated_addendum"

ADDENDA_CSV = LSE / "HYP04_ANCHOR_EVENT_ADDENDA.csv"

ADDENDA_FIELDS = ("event_id", "anchor_ticker", "release_date",
                  "release_session", "supersedes_event_id", "source_accession",
                  "source_citation", "curated_by", "curated_date",
                  "review_status", "notes_caveats")

# Provenance a curated row must carry to be accepted. An addendum without a
# citation is an assertion, and this file exists precisely so that anchor
# events are not assertions.
ADDENDA_REQUIRED = ("event_id", "anchor_ticker", "release_date",
                    "release_session", "source_accession", "source_citation",
                    "curated_by", "curated_date")


@dataclass(frozen=True)
class CandidateEvent:
    """One 8-K Item 2.02 release. NOT an eligible event -- see module docstring."""
    event_id: str
    anchor_ticker: str
    release_date: str          # reportDate. NEVER filingDate.
    release_session: str       # BMO | AMC | UNKNOWN
    session_basis: str         # how release_session was derived, in words
    filing_date: str           # evidence only
    acceptance_utc: str        # evidence only
    acceptance_et: str         # evidence only
    items: str
    accession: str
    flags: tuple[str, ...]
    provenance: str = PROVENANCE_DERIVED

    def as_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["flags"] = ";".join(self.flags)
        return d


CSV_FIELDS = ("event_id", "anchor_ticker", "release_date", "release_session",
              "session_basis", "filing_date", "acceptance_utc", "acceptance_et",
              "items", "accession", "flags", "provenance")


def classify_release_session(release_date: str,
                             acceptance_utc: str) -> tuple[str, str]:
    """Derive BMO/AMC from the acceptance timestamp. Pure; no network.

    Returns (session, basis). Never raises on unparseable input -- it returns
    UNKNOWN with the reason, because a malformed timestamp is exactly the case
    that must not silently become a guess.
    """
    if not acceptance_utc:
        return SESSION_UNKNOWN, "no acceptance timestamp in the submissions record"
    try:
        utc = datetime.fromisoformat(acceptance_utc.replace("Z", "+00:00"))
    except ValueError:
        return SESSION_UNKNOWN, f"unparseable acceptance timestamp {acceptance_utc!r}"

    et = utc.astimezone(EASTERN)
    stamp = et.strftime("%Y-%m-%d %H:%M %Z")

    if et.strftime("%Y-%m-%d") != release_date:
        return (SESSION_UNKNOWN,
                f"accepted {stamp}, which is not the release date {release_date}; "
                "the filing and the release fall on different days, so the "
                "release time cannot be inferred from acceptance")

    if et.time() >= MARKET_CLOSE_ET:
        return SESSION_AMC, f"accepted {stamp}, at or after the 16:00 ET close"
    if et.time() < MARKET_OPEN_ET:
        return SESSION_BMO, f"accepted {stamp}, before the 09:30 ET open"
    return (SESSION_UNKNOWN,
            f"accepted {stamp}, between the 09:30 ET open and the 16:00 ET "
            "close; an intraday acceptance does not identify BMO or AMC")


def _flags_for(items: str, release_date: str, filing_date: str,
               session: str) -> tuple[str, ...]:
    out: list[str] = []
    parts = {p.strip() for p in items.split(",") if p.strip()}
    if not parts <= STANDARD_ITEMS:
        out.append(FLAG_NON_STANDARD_ITEMS)
    if session == SESSION_UNKNOWN:
        out.append(FLAG_SESSION_UNRESOLVED)
    if release_date != filing_date:
        out.append(FLAG_REPORT_BEFORE_FILING)
    return tuple(out)


def event_id_for(ticker: str, release_date: str) -> str:
    return f"{ticker.upper()}-{release_date}"


def candidate_from_record(ticker: str, rec: dict[str, str]) -> CandidateEvent:
    """Build one candidate from a submissions-record row. Pure; no network."""
    release_date = rec["reportDate"]
    filing_date = rec.get("filingDate", "")
    acceptance = rec.get("acceptanceDateTime", "")
    session, basis = classify_release_session(release_date, acceptance)
    try:
        et = datetime.fromisoformat(
            acceptance.replace("Z", "+00:00")).astimezone(EASTERN)
        acceptance_et = et.strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError, AttributeError):
        acceptance_et = ""
    items = rec.get("items", "")
    return CandidateEvent(
        event_id=event_id_for(ticker, release_date),
        anchor_ticker=ticker.upper(),
        release_date=release_date,
        release_session=session,
        session_basis=basis,
        filing_date=filing_date,
        acceptance_utc=acceptance,
        acceptance_et=acceptance_et,
        items=items,
        accession=rec.get("accessionNumber", ""),
        flags=_flags_for(items, release_date, filing_date, session),
    )


def all_item_202_records(client: EdgarClient, cik: str) -> list[dict[str, str]]:
    """Every 8-K carrying Item 2.02, newest first, across ALL submission blocks.

    `filings.recent` holds only the most recent block. A walk that reads only
    that block truncates silently at whatever depth it happens to reach, which
    is indistinguishable from "the company reported no earlier earnings" --
    the same trap `all_10ks` documents.

    GOES THROUGH `_get_json`, NOT `_get`. `_get` is the raw transport: it sits
    BELOW both the on-disk cache and the `offline=True` guard. This function
    called it directly until 2026-08-29, which meant an EdgarClient constructed
    with `offline=True` reached data.sec.gov anyway -- silently, and while
    reporting cache hits of zero. That is exactly the failure `OfflineCacheMiss`
    was written to prevent ("quietly reaching the network from a run the caller
    asked to be offline is how a 'no requests made' claim becomes false without
    anyone noticing"), and it was found by making that false claim: a run
    asserted to be offline came back with requests_made=20.
    """
    data = client._get_json(SUBMISSIONS_URL.format(cik=cik))
    filings = data.get("filings", {})
    blocks = [filings.get("recent", {})]
    for extra in filings.get("files", []) or []:
        name = extra.get("name")
        if name:
            blocks.append(
                client._get_json(SUBMISSIONS_EXTRA_URL.format(name=name)))

    out: list[dict[str, str]] = []
    for blk in blocks:
        forms = blk.get("form") or []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            items = (blk.get("items") or [""] * len(forms))[i]
            if ITEM_RESULTS not in items:
                continue
            out.append({
                "accessionNumber": blk["accessionNumber"][i],
                "filingDate": blk["filingDate"][i],
                "reportDate": blk["reportDate"][i],
                "acceptanceDateTime": (
                    blk.get("acceptanceDateTime") or [""] * len(forms))[i],
                "items": items,
            })
    out.sort(key=lambda r: r["reportDate"], reverse=True)
    return out


def candidates_for_ticker(client: EdgarClient, ticker: str,
                          *, since: Optional[str] = None) -> list[CandidateEvent]:
    cik = client.cik_for(ticker)
    if cik is None:
        raise RuntimeError(f"no CIK on record for ticker {ticker!r}")
    recs = all_item_202_records(client, cik)
    events = [candidate_from_record(ticker, r) for r in recs]
    if since:
        # STRICTLY after, mirroring pair_eligibility's P3. An event ON the
        # as-of date denies there, so including it here would only manufacture
        # rows the analysis must discard.
        events = [e for e in events if e.release_date > since]
    return events


class AddendaError(ValueError):
    """An addendum file that cannot be trusted. Never downgraded to a warning."""


def load_addenda(path: Path
                 ) -> tuple[list[CandidateEvent], dict[str, str], list[str]]:
    """Read curated anchor events. Returns (events, supersedes, rejections).

    Every row must carry ADDENDA_REQUIRED provenance. A row without a citation
    is rejected rather than accepted quietly: this file exists so that an
    anchor event the walk cannot derive is still traceable to a filing, and a
    row that skips the citation defeats the entire point of having it.

    `release_session` must be BMO or AMC -- curating UNKNOWN would be curating
    an absence, and the merged event would then be dropped downstream anyway.

    `supersedes_event_id` names the DERIVED row this curated one replaces, for
    the case where the walk found the release but mis-dated it. It is verified
    against the derived set at merge time, not here.
    """
    import csv as _csv

    events: list[CandidateEvent] = []
    supersedes: dict[str, str] = {}
    rejections: list[str] = []
    seen: set[str] = set()

    if not path.is_file():
        return events, supersedes, rejections

    with path.open(encoding="utf-8", newline="") as fh:
        reader = _csv.DictReader(fh)
        missing_cols = [c for c in ADDENDA_REQUIRED
                        if c not in (reader.fieldnames or [])]
        if missing_cols:
            raise AddendaError(
                f"{path.name} is missing required column(s): "
                f"{', '.join(missing_cols)}. Refusing to read it -- a column "
                "absent from the header is absent from every row.")

        for n, row in enumerate(reader, start=2):
            eid = (row.get("event_id") or "").strip()
            blank = [c for c in ADDENDA_REQUIRED if not (row.get(c) or "").strip()]
            if blank:
                rejections.append(
                    f"row {n} ({eid or '<no event_id>'}): missing required "
                    f"provenance {', '.join(blank)}")
                continue
            if eid in seen:
                rejections.append(f"row {n}: duplicate event_id {eid!r}")
                continue

            rd = (row.get("release_date") or "").strip()
            if not DATE_RE.match(rd):
                rejections.append(f"row {n} ({eid}): release_date {rd!r} is "
                                  "not YYYY-MM-DD")
                continue
            sess = (row.get("release_session") or "").strip().upper()
            if sess not in (SESSION_BMO, SESSION_AMC):
                rejections.append(
                    f"row {n} ({eid}): release_session {sess!r} must be "
                    f"{SESSION_BMO} or {SESSION_AMC}; curating "
                    f"{SESSION_UNKNOWN} curates an absence")
                continue

            seen.add(eid)
            sup = (row.get("supersedes_event_id") or "").strip()
            if sup:
                supersedes[eid] = sup
            cite = (row.get("source_citation") or "").strip()
            events.append(CandidateEvent(
                event_id=eid,
                anchor_ticker=(row["anchor_ticker"] or "").strip().upper(),
                release_date=rd,
                release_session=sess,
                session_basis=f"CURATED: {cite}",
                filing_date="", acceptance_utc="", acceptance_et="",
                items="", accession=(row.get("source_accession") or "").strip(),
                flags=(), provenance=PROVENANCE_CURATED))
    return events, supersedes, rejections


def merge_addenda(derived: Sequence[CandidateEvent],
                  curated: Sequence[CandidateEvent],
                  supersedes: Mapping[str, str],
                  ) -> tuple[list[CandidateEvent], list[str]]:
    """Combine derived and curated events, applying supersession.

    `supersedes` maps a curated event_id to the DERIVED event_id it replaces.
    This exists because a curated row and the derived row it corrects do NOT
    collide on event_id -- the id embeds the date, and the date is the thing
    being corrected. MCK-2023-11-01 and MCK-2023-10-27 are the same earnings
    release; merging both would count one release twice, silently, and
    double-counting is invisible in a total.

    Refuses, rather than warning, when:
      * a curated id collides with a derived id (ambiguous -- correct it or
        supersede it, not both)
      * `supersedes` names an event that is not in the derived set. That means
        the addendum is stale: the walk no longer produces the row it claims
        to replace, so the correction may no longer apply.

    Returns (merged, notes) with notes recording each supersession applied.
    """
    by_id = {e.event_id: e for e in derived}
    notes: list[str] = []

    for c in curated:
        if c.event_id in by_id:
            raise AddendaError(
                f"curated event {c.event_id!r} collides with a derived event "
                "of the same id. A curated row either ADDS an event the walk "
                "cannot see or SUPERSEDES a mis-dated one; it never shadows "
                "an identical id.")

    dropped: set[str] = set()
    for c in curated:
        target = (supersedes.get(c.event_id) or "").strip()
        if not target:
            continue
        if target not in by_id:
            raise AddendaError(
                f"curated event {c.event_id!r} claims to supersede "
                f"{target!r}, which the derived walk did not produce. The "
                "addendum is stale -- re-check it against the current walk "
                "rather than merging a correction to something absent.")
        dropped.add(target)
        notes.append(f"{c.event_id} supersedes {target}")

    merged = [e for e in derived if e.event_id not in dropped]
    merged.extend(curated)
    merged.sort(key=lambda e: (e.anchor_ticker, e.release_date))
    return merged, notes


MAX_EXPECTED_GAP_DAYS = 130


def find_cadence_gaps(events: Iterable[CandidateEvent],
                      *, max_days: int = MAX_EXPECTED_GAP_DAYS
                      ) -> list[tuple[str, str, int]]:
    """Intervals between consecutive releases longer than a quarter.

    A company on a quarterly cadence reports roughly every 91 days. A gap
    materially longer than that means a release is MISSING from the walk --
    most likely because the filer did not tag Item 2.02 (see the module
    docstring; MCK 2020-02-04 is a confirmed instance).

    Returns (earlier_date, later_date, days) per gap, ascending. An empty list
    means the cadence is unbroken, NOT that coverage is complete -- a miss at
    the very start or end of the range leaves no gap to find.

    Deliberately does not fill anything. Identifying which untagged filing is
    an earnings release requires reading it, and a wrong answer here is a
    fabricated anchor event.
    """
    per: dict[str, list[str]] = {}
    for e in events:
        per.setdefault(e.anchor_ticker, []).append(e.release_date)
    out: list[tuple[str, str, int]] = []
    for dates in per.values():
        ordered = sorted(dates)
        for a, b in zip(ordered, ordered[1:]):
            days = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days
            if days > max_days:
                out.append((a, b, days))
    out.sort()
    return out


def write_csv(events: Iterable[CandidateEvent], path: Path) -> int:
    rows = [e.as_row() for e in events]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def summarise(events: list[CandidateEvent]) -> dict[str, Any]:
    return {
        "total": len(events),
        "by_session": {s: sum(1 for e in events if e.release_session == s)
                       for s in (SESSION_AMC, SESSION_BMO, SESSION_UNKNOWN)},
        "flagged": sum(1 for e in events if e.flags),
        "earliest": min((e.release_date for e in events), default=None),
        "latest": max((e.release_date for e in events), default=None),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Derive CANDIDATE anchor events from 8-K Item 2.02 filings. "
                    "Candidates are not eligible events and move no gate.")
    ap.add_argument("--ticker", action="append", required=True,
                    help="anchor ticker; repeatable")
    ap.add_argument("--since", action="append", default=None,
                    help="TICKER:YYYY-MM-DD -- keep only releases strictly "
                         "after this date (use the curated edge's as_of_date)")
    ap.add_argument("--contact", default=None,
                    help='SEC User-Agent, e.g. "Name email@realdomain.com"')
    ap.add_argument("--out", default=None, help="write a CSV here")
    ap.add_argument("--addenda", type=Path, default=ADDENDA_CSV,
                    help="curated anchor events the walk cannot derive "
                         "(default: the committed addenda file). Each row "
                         "carries a citation; rows may supersede a mis-dated "
                         "derived event.")
    ap.add_argument("--no-addenda", action="store_true",
                    help="derived events only -- shows exactly what the walk "
                         "produces on its own")
    ap.add_argument("--max-requests", type=int, default=40)
    a = ap.parse_args(argv)

    if not a.contact:
        print(CONTACT_REQUIRED_MESSAGE, file=sys.stderr)
        return 2

    since_map: dict[str, str] = {}
    for spec in (a.since or []):
        tk, _, d = spec.partition(":")
        if not d:
            print(f"--since expects TICKER:YYYY-MM-DD, got {spec!r}",
                  file=sys.stderr)
            return 2
        since_map[tk.upper()] = d

    client = EdgarClient(a.contact, max_requests=a.max_requests)
    all_events: list[CandidateEvent] = []
    for tk in a.ticker:
        tk = tk.upper()
        evs = candidates_for_ticker(client, tk, since=since_map.get(tk))
        s = summarise(evs)
        print(f"{tk}: {s['total']} candidate release(s) "
              f"{s['earliest']} .. {s['latest']}"
              + (f"  (strictly after {since_map[tk]})" if tk in since_map else ""))
        print(f"    AMC={s['by_session']['AMC']} "
              f"BMO={s['by_session']['BMO']} "
              f"UNKNOWN={s['by_session']['UNKNOWN']}  flagged={s['flagged']}")
        for e in evs:
            if e.flags:
                print(f"    FLAG {e.release_date} [{','.join(e.flags)}] "
                      f"items={e.items}")
        for gap_from, gap_to, days in find_cadence_gaps(evs):
            print(f"    GAP  {gap_from} -> {gap_to} ({days} days) -- a release "
                  "is probably MISSING here; the filer may not have tagged "
                  "Item 2.02")
        all_events.extend(evs)

    if not a.no_addenda:
        curated, supersedes, rejections = load_addenda(a.addenda)
        for why in rejections:
            print(f"    ADDENDA REJECTED {why}", file=sys.stderr)
        if curated:
            all_events, notes = merge_addenda(all_events, curated, supersedes)
            print(f"\nADDENDA: {len(curated)} curated event(s) from "
                  f"{a.addenda.name}")
            for n in notes:
                print(f"    {n}")
            for c in curated:
                if c.event_id not in supersedes:
                    print(f"    {c.event_id} added (supersedes nothing)")
        if rejections:
            print(f"    {len(rejections)} addenda row(s) rejected -- see stderr",
                  file=sys.stderr)

    print(f"\nTOTAL CANDIDATES: {len(all_events)}")
    n_cur = sum(1 for e in all_events if e.provenance == PROVENANCE_CURATED)
    if n_cur:
        print(f"  {len(all_events) - n_cur} derived + {n_cur} curated")
    print("These are CANDIDATES. They are not eligible events, they have not "
          "been screened, and they move no display-gate condition.")

    if a.out:
        n = write_csv(all_events, Path(a.out))
        print(f"wrote: {a.out}  ({n} row(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
