#!/usr/bin/env python3
"""Evidence for ratifying the curated linkage map -- and no verdict.

Six edges in `HYP04_Linkage_Map_v1.2.csv` contribute eligible anchor events.
Five say in their own notes "no human has reviewed this edge"; one is flagged
`needs revisit`. Ratifying them is the repo owner's act. This module assembles
what a reviewer needs and stops there.

=== IT NEEDS NO NETWORK, AND THAT WAS A CORRECTION ===

`HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-09-02.json` already holds COMPLETE
10-K walks for every contributing anchor -- INTC 33/33, JBL 30/30, MCK 32/32,
NVDA 28/28, zero failures and no early stops -- with per-filing disclosure
records including accessions. Re-fetching would add a second copy of an answer
already on disk and a second chance to disagree with it.

=== WHAT IT WILL NOT DO ===

It does not emit a `review_status`, and it does not rank edges by whether the
sample needs them. The margin over the floor is 21 events and the smallest
contributing anchor supplies 30, so EVERY edge is load-bearing -- which is
exactly the circumstance in which a recommendation to keep one would be worth
nothing.

Counterparty names are matched to the walk by EXACT string equality against the
name in each edge's own `source_citation`. No fuzzy matching and no scoring: a
wrong counterparty is fabricated linkage wearing a number, and it fails
silently. An unmatched citation is reported UNMATCHED and left to the reviewer.

Alias chains -- CVS Caremark Corporation to CVS Health to CVS Health
Corporation -- are NOT auto-linked. Every counterparty the anchor ever named is
listed so the reviewer can see the chain, and the map's own adjudication of it
is quoted verbatim. Deciding that two names are one company is the judgement
that rejected Caremark RX and OfficeMax; a machine that made it here would be
overturning those decisions by inference.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .artifacts import newest_in
from .constants import HORIZON_GRID
from .curated_linkage import load_curated_linkage
from .linkage_resolution import resolve_from_curated_map
from .peer_ceiling import events_from_calendar, shocks_from_rows

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

AS_OF = "2026-09-08"
OUT_JSON = LSE / f"HYP04_EDGE_VERIFICATION_{AS_OF}.json"
OUT_MD = LSE / f"HYP04_EDGE_VERIFICATION_{AS_OF}.md"

#: "...disclosure naming Apple, Inc at 13.0% of consolidated_revenue."
#: "...disclosure naming CVS Caremark Corporation"
_NAMING = re.compile(r"naming\s+(.+?)(?:\s+at\s+[\d.]+\s*%|\s*\.\s*$|\s*$)")


class VerificationError(RuntimeError):
    """A precondition does not hold.

    VerificationError, never a bare `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


def _require(p: Optional[Path], what: str) -> Path:
    if p is None or not p.is_file():
        raise VerificationError(f"no {what} on disk")
    return p


def counterparty_from_citation(citation: str) -> Optional[str]:
    """The counterparty an edge's own source_citation names, verbatim."""
    m = _NAMING.search(citation or "")
    return m.group(1).strip() if m else None


def _history() -> dict[str, dict]:
    path = _require(newest_in(LSE, "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_*.json"),
                    "EDGAR linkage-history artifact")
    doc = json.loads(path.read_text(encoding="utf-8"))
    by_ticker = {t["ticker"]: t for t in doc.get("tickers", [])}
    incomplete = {
        t: (v.get("filings_examined"), v.get("filings_on_record"))
        for t, v in by_ticker.items()
        if v.get("stopped_early_reason") or v.get("filings_failed")
        or v.get("filings_examined") != v.get("filings_on_record")}
    return {"path": path, "by_ticker": by_ticker, "incomplete": incomplete}


def _eligible_pairs(map_path: Optional[Path] = None
                    ) -> tuple[dict[tuple[str, str], list[str]], dict]:
    """(anchor, peer) -> eligible event ids, recomputed from the same inputs.

    `map_path` PINS the curated map. It defaults to the newest, which is right
    when generating, and is passed explicitly when REPRODUCING a dated
    artifact. Without it this document would re-derive against whatever map is
    newest today -- so once the map it was evidence FOR is ratified, it would
    report `review_status: reviewed` and cite the decision it informed. A dated
    evidence artifact has to stay reproducible as of its date.
    """
    from . import make_event_panel as MP

    paths = MP._inputs()
    if map_path is not None:
        paths = {**paths, "curated_map": map_path}
    cal = MP._rows(paths["calendar"])
    shk = MP._rows(paths["shocks"])
    events = events_from_calendar(cal)
    shocks = shocks_from_rows(shk)
    attributed = MP._attributed_sessions(shk)
    peer_files = sorted(MP.PEER_CLOSES_DIR.glob("*_closes_REQUEST.csv"))
    idx, _ = MP._session_index(attributed, peer_files)
    pos = {d: i for i, d in enumerate(idx)}
    series, _ = MP._load_peer_series(idx)

    res = load_curated_linkage(paths["curated_map"])
    if not res.ok:
        raise VerificationError(
            f"{paths['curated_map'].name} did not load cleanly")
    by_anchor: dict[str, list[str]] = {}
    for e in res.edges:
        by_anchor.setdefault(e.anchor_ticker.upper(), []).append(
            e.peer_ticker.upper())

    by_pair, _, _ = MP._coverage(series, events, by_anchor, attributed, pos)
    panel = resolve_from_curated_map(
        events, map_path=paths["curated_map"], anchor_shock=shocks,
        peer_history_by_pair=by_pair)

    out: dict[tuple[str, str], list[str]] = {}
    for ev in panel.anchor_events:
        anchor = str(ev.get("anchor", "")).upper()
        for peer in ev.get("peers") or ():
            out.setdefault((anchor, peer.upper()), []).append(
                str(ev["event_id"]))
    return out, {"map": paths["curated_map"].name,
                 "calendar": paths["calendar"].name,
                 "shocks": paths["shocks"].name}


def _event_date(event_id: str, anchor: str) -> str:
    """`JBL-2003-09-18` -> `2003-09-18`. The id is anchor + '-' + date."""
    tail = event_id[len(anchor) + 1:] if event_id.startswith(anchor + "-") else ""
    return tail if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tail) else ""


def build(map_path: Optional[Path] = None) -> dict[str, Any]:
    hist = _history()
    pairs, sources = _eligible_pairs(map_path=map_path)

    map_path = LSE / sources["map"]
    res = load_curated_linkage(map_path)

    edges_out: list[dict[str, Any]] = []
    for e in res.edges:
        anchor, peer = e.anchor_ticker.upper(), e.peer_ticker.upper()
        eids = sorted(pairs.get((anchor, peer), []))
        cited = counterparty_from_citation(e.source_citation)
        walk = hist["by_ticker"].get(anchor)
        named = (walk or {}).get("named_counterparties", [])
        match = next((c for c in named
                      if cited and c["counterparty"] == cited), None)

        after = None
        share = None
        if match and eids:
            last = match.get("latest_filing_date") or ""
            after = sum(1 for i in eids if _event_date(i, anchor) > last)
            share = round(100 * after / len(eids), 1)

        # Two ways the "after last disclosure" number misleads if left bare.
        #
        # (1) For an edge disclosed in ONE filing, as_of == latest, and P3
        #     admits only events strictly after as_of -- so 100% is arithmetic,
        #     not evidence.
        # (2) MCK's counterparty is named "CVS Caremark Corporation" until
        #     2015 and "CVS Health"/"CVS Health Corporation" after. Exact
        #     matching finds only the first, so the count reads as a lapse when
        #     the anchor kept disclosing under a later name. Listing those
        #     names is factual; CHAINING them is the judgement that rejected
        #     Caremark RX, and it is not made here.
        last_seen = (match or {}).get("latest_filing_date") or ""
        later_names = [
            {"counterparty": c["counterparty"],
             "earliest": c["earliest_filing_date"],
             "latest": c.get("latest_filing_date"),
             "filings": c.get("filings_naming_it")}
            for c in named
            if match and (c.get("latest_filing_date") or "") > last_seen]

        edges_out.append({
            "single_filing_edge": (match or {}).get("filings_naming_it") == 1,
            "after_count_is_tautological": (
                (match or {}).get("filings_naming_it") == 1),
            "later_named_counterparties_on_this_anchor": later_names,
            "later_names_exist": bool(later_names),
            "edge": f"{anchor}->{peer}",
            "anchor": anchor,
            "peer_ticker": peer,
            "map_as_of_date": e.as_of_date,
            "map_as_of_basis": e.as_of_date_basis,
            "map_date_confidence": e.date_confidence,
            "map_review_status": e.review_status,
            "counterparty_named_in_citation": cited,
            "matched_in_walk": bool(match),
            "match_mode": "exact_string_equality",
            "earliest_disclosing_filing": (match or {}).get("earliest_filing_date"),
            "earliest_accession": (match or {}).get("earliest_accession"),
            "latest_disclosing_filing": (match or {}).get("latest_filing_date"),
            "latest_accession": (match or {}).get("latest_accession"),
            "filings_naming_it": (match or {}).get("filings_naming_it"),
            "as_of_agrees_with_walk": bool(
                match and match.get("earliest_filing_date") == e.as_of_date),
            "eligible_events": len(eids),
            "eligible_events_after_last_disclosure": after,
            "pct_events_after_last_disclosure": share,
            "all_counterparties_this_anchor_ever_named": [
                {"counterparty": c["counterparty"],
                 "earliest": c["earliest_filing_date"],
                 "latest": c.get("latest_filing_date"),
                 "filings": c.get("filings_naming_it")}
                for c in named],
            "map_notes_verbatim": e.notes_caveats,
        })

    edges_out.sort(key=lambda r: (-(r["eligible_events"] or 0), r["edge"]))
    contributing = [r for r in edges_out if r["eligible_events"]]

    return {
        "artifact": OUT_JSON.name,
        "as_of_date": AS_OF,
        "hypothesis_id": "HYP-04",
        "what_this_is": (
            "Evidence for ratifying the curated linkage map. Assembled from "
            "the completed EDGAR 10-K walks already on disk."),
        "what_this_is_not": (
            "A verdict. It emits no review_status, ranks nothing by whether "
            "the sample needs it, and asserts no alias chain."),
        "uses_network": False,
        "sources": {**sources, "history": hist["path"].name},
        "walk_completeness": {
            "all_contributing_anchors_complete": not hist["incomplete"],
            "incomplete_anchors": hist["incomplete"],
        },
        "name_matching": (
            "exact string equality against the counterparty named in each "
            "edge's own source_citation; no fuzzy matching, no scoring"),
        "alias_chains_not_asserted": (
            "every counterparty an anchor ever named is listed so a reviewer "
            "can see the chain; deciding two names are one company is the "
            "judgement that rejected Caremark RX and OfficeMax"),
        "n_edges": len(edges_out),
        "n_contributing_edges": len(contributing),
        "edges": edges_out,
    }


def render_md(doc: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a(f"# HYP-04 curated-edge verification ({doc['as_of_date']})")
    a("")
    a("**Status:** evidence for a ratification decision. It contains no "
      "`review_status` and recommends nothing.")
    a("")
    a("Assembled offline from the completed EDGAR 10-K walks in "
      f"`{doc['sources']['history']}`. No network call was made.")
    a("")
    a("## Why every edge matters equally here")
    a("")
    a("The derived sample is 214 eligible anchor events against a floor of "
      "193 — a margin of 21. The smallest contributing anchor supplies 30 "
      "events, so **dropping any single anchor's edges fails the floor.** "
      "That is precisely the circumstance in which a recommendation to keep "
      "an edge would be worth nothing, which is why there is none below.")
    a("")
    a("## The edges, by events contributed")
    a("")
    a("| edge | events | as_of | walk earliest | walk latest | filings | "
      "events after last disclosure |")
    a("|---|---|---|---|---|---|---|")
    for e in doc["edges"]:
        if not e["eligible_events"]:
            continue
        after = e["eligible_events_after_last_disclosure"]
        pct = e["pct_events_after_last_disclosure"]
        aft = "—" if after is None else f"**{after}** ({pct}%)"
        if e["after_count_is_tautological"]:
            aft += " ‡"
        if e["later_names_exist"]:
            aft += " †"
        a(f"| `{e['edge']}` | {e['eligible_events']} | {e['map_as_of_date']} | "
          f"{e['earliest_disclosing_filing']} | {e['latest_disclosing_filing']} "
          f"| {e['filings_naming_it']} | {aft} |")
    a("")
    a("`as_of` agrees with the walk's earliest disclosing filing for "
      + ", ".join(f"`{e['edge']}`" for e in doc["edges"]
                  if e["as_of_agrees_with_walk"]) + ".")
    a("")
    a("**‡ — the count is arithmetic, not evidence.** This edge is disclosed "
      "in exactly one filing, so `as_of` *is* the last disclosure and P3 "
      "admits only events strictly after it. 100% is forced. What the single "
      "filing does tell you is that the relationship was never disclosed "
      "again, which is a separate thing worth weighing.")
    a("")
    a("**† — this anchor kept naming counterparties after this one's last "
      "filing.** Exact-string matching finds only the name in the citation, "
      "so an anchor that carried on disclosing under a *different* name reads "
      "here as if it stopped. The names are listed per edge below. Whether "
      "any of them is the same company is the judgement that rejected "
      "Caremark RX and OfficeMax, and it is not made for you:")
    a("")
    for e in doc["edges"]:
        if not (e["eligible_events"] and e["later_names_exist"]):
            continue
        names = ", ".join(
            f"**{c['counterparty']}** ({c['earliest']} → {c['latest']}, "
            f"{c['filings']} filing(s))"
            for c in e["later_named_counterparties_on_this_anchor"])
        a(f"- `{e['edge']}` — later on this anchor: {names}")
    a("")
    a("## What the last column means, and does not")
    a("")
    a("P3 admits a pair when `as_of_date <= event_date`. **Nothing checks the "
      "relationship was still disclosed when the event happened.** The "
      "rightmost column counts eligible events falling after the last filing "
      "that named the counterparty at all.")
    a("")
    a("A high number is not proof the relationship ended — ASC 280 requires "
      "disclosure only above a threshold, so a customer can fall from 12% to "
      "9% of revenue and vanish from the filings while the commercial "
      "relationship continues. It is *absence of evidence*, and the "
      "agreements artifact already uses that exact phrase for the same "
      "problem. But it is the axis on which these edges differ most, and it "
      "is not visible anywhere in the map.")
    a("")
    a("**Adopting a currency rule is a `SCIENTIFIC_DECISION` and is not "
      "proposed here.** It would be made after seeing which edges it cuts, "
      "which is what the analysis locks exist to prevent.")
    a("")
    for e in doc["edges"]:
        a(f"## `{e['edge']}`"
          + ("" if e["eligible_events"] else "  (contributes no eligible events)"))
        a("")
        a(f"- **Counterparty named in the citation:** "
          f"`{e['counterparty_named_in_citation']}`")
        a(f"- **Matched in the walk:** {e['matched_in_walk']} "
          f"({e['match_mode']})")
        if e["matched_in_walk"]:
            a(f"- **Disclosed in {e['filings_naming_it']} filing(s)**, "
              f"{e['earliest_disclosing_filing']} → "
              f"{e['latest_disclosing_filing']}")
            a(f"- Earliest accession `{e['earliest_accession']}`, "
              f"latest `{e['latest_accession']}`")
            a(f"- **`as_of` agrees with the earliest disclosing filing:** "
              f"{e['as_of_agrees_with_walk']}")
        a(f"- Map records `date_confidence: {e['map_date_confidence']}`, "
          f"`review_status: {e['map_review_status']}`")
        a("")
        a(f"Every counterparty **{e['anchor']}** ever named in its 10-Ks:")
        a("")
        a("| counterparty | earliest | latest | filings |")
        a("|---|---|---|---|")
        for c in e["all_counterparties_this_anchor_ever_named"]:
            a(f"| {c['counterparty']} | {c['earliest']} | {c['latest']} | "
              f"{c['filings']} |")
        a("")
        a("<details><summary>The map's own notes on this edge, verbatim"
          "</summary>")
        a("")
        a("> " + (e["map_notes_verbatim"] or "").replace("\n", "\n> "))
        a("")
        a("</details>")
        a("")
    a("---")
    a("")
    a("*Nothing in this document is evidence about supply-chain transmission. "
      "No target value, `beta_h`, horizon or direction has been computed, and "
      "none may be displayed while the gate is closed.*")
    a("")
    a("*Nothing here constitutes investment advice, a solicitation, or a "
      "representation that any approach is profitable.*")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    doc = build()
    print(f"walks complete for every contributing anchor: "
          f"{doc['walk_completeness']['all_contributing_anchors_complete']}")
    print(f"{doc['n_contributing_edges']} of {doc['n_edges']} edges contribute "
          "eligible events\n")
    print(f"{'edge':22s} {'events':>6s} {'as_of':>11s} {'last disc.':>11s} "
          f"{'files':>5s} {'after':>6s}")
    for e in doc["edges"]:
        if not e["eligible_events"]:
            continue
        print(f"{e['edge']:22s} {e['eligible_events']:6d} "
              f"{str(e['map_as_of_date']):>11s} "
              f"{str(e['latest_disclosing_filing']):>11s} "
              f"{str(e['filings_naming_it']):>5s} "
              f"{str(e['eligible_events_after_last_disclosure']):>6s}")
    print("\nNo review_status is emitted. Ratification is the owner's act.")

    if args.write:
        for p in (OUT_JSON, OUT_MD):
            if p.exists():
                raise VerificationError(
                    f"{p.name} exists; refusing to overwrite a dated artifact")
        OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        OUT_MD.write_text(render_md(doc), encoding="utf-8")
        print(f"\nWROTE {OUT_JSON.name} and {OUT_MD.name}")
    else:
        print("\nDRY RUN -- pass --write to persist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
