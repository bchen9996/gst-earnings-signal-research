#!/usr/bin/env python3
"""Generate hypothesis-registry v1.8 from v1.7 -- HYP-04.

=== WHAT CHANGES, AND WHY IT IS NOT THE RULE ===

v1.7 corrected WHICH filings the anchor could read. v1.8 corrects a defect one
level down: the anchor could only ever read a percentage that sat next to its
own denominator. Filings routinely state the denominator ONCE, in a scope
clause, and then list parties carrying bare percentages -- in prose or as a
table -- and every one of those was invisible.

  INTC 2018-02-16  "our three largest customers accounted for 40% of our net
                    revenue, with Dell Inc. accounting for 16% ..."
  INTC 2024-01-26  "the following percentage of our net revenue: ...
                    Dell Inc. 19 % 19 % 21 %"
  ADBE 2011-01-27  "as a percentage of net revenue for fiscal 2010, 2009 and
                    2008 ... 2010 2009 2008  Ingram Micro 15 % 15 % 18 %"
  JBL  2015-10-16  "...expressed as a percentage of consolidated net revenue
                    ... Apple, Inc. 24 % 18 % 20 % 19 % 12 %"

WHAT THAT COST THE PUBLISHED REGISTRY. Three memberships were wrong, and all
three were wrong in the same way -- DATA AVAILABILITY DECIDING MEMBERSHIP,
which AU-1..AU-6 forbid:

  * INTC's interval closed at 2017-02-17. That is not when Dell stopped being
    15-21% of Intel's net revenue; it is the filing in which Intel moved the
    named-customer disclosure out of Item 1 prose and into the segment note.
    Every filing from 2017-02-17 to 2024-01-26 states the concentration in
    plain English and names the customers.
  * ADBE was in NO registry version, though Ingram Micro is disclosed at
    11-21% of net revenue across 2008-2015.
  * JBL was in NO registry version, though its 10-Ks carry an explicit
    "customers who accounted for 10% or more of the Company's net revenues"
    table naming Dell, Cisco, Marconi, Philips, HP, Nokia, BlackBerry and
    Apple across twenty-four years.

THE RULE ITSELF IS UNTOUCHED. AU-1..AU-6, the 10% threshold and the
consolidated-revenue denominator are ASC 280-10-50-42's own and are checked
byte-identical against v1.7, as is the point-in-time evaluation basis.

=== BOTH NEW EXITS ARE THE RULE WORKING ===

INTC's membership now ends 2025-01-31 and JBL's 2025-10-17. Neither is a
reading failure: in those filings Intel and Jabil ANONYMISED their customers
to "Customer A / B / C". A concentration whose counterparty is not named
cannot support a bilateral relationship, so the rule excludes it -- the same
control that keeps "Customer A" out of every other filing.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_8 --write

Named off the `test_*` pattern deliberately: this writes a governance
artifact and must only ever run when a human decides it should.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hyp04_supply_chain_hedge import anchor_universe as au
from hyp04_supply_chain_hedge.make_registry_v1_4 import (
    find_availability_contradictions,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (
    HYPOTHESIS_ID,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RULE_FIELDS_THAT_MUST_NOT_MOVE,
    RefusedError,
    _load,
    _sha256,
)
from hyp04_supply_chain_hedge.make_registry_v1_7 import (
    EVALUATION_FIELDS_THAT_MUST_NOT_MOVE,
)

V1_7 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7.json"
V1_8 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.8.json"
V1_8_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.8_DRAFT.md"

HISTORY = LSE / "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-29_v1.json"

AUTHORED_AT = "2026-08-29"

FINDINGS = (
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_POINT_IN_TIME_FINDING_2026-08-27.md",
    "Live Signal Engine/HYP04_EXTRACTOR_POSSESSIVE_DENOMINATOR_FINDING_2026-08-27.md",
    "Live Signal Engine/HYP04_EXTRACTOR_GAP_MEASUREMENT_FINDING_2026-08-28.md",
    "Live Signal Engine/HYP04_EXTRACTOR_SCOPED_LIST_FINDING_2026-08-29.md",
)


def check_preconditions(*, v1_7: Path = V1_7, v1_8: Path = V1_8,
                        history: Path = HISTORY) -> list[str]:
    refusals: list[str] = []
    if not v1_7.is_file():
        refusals.append(f"registry v1.7 not found at {v1_7.name}")
    if v1_8.exists():
        refusals.append(
            f"{v1_8.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really "
            "intended.")
    if not history.is_file():
        refusals.append(f"history walk not found at {history.name}")
        return refusals

    u = au.derive_universe_point_in_time(_load(history))
    if not u.derived:
        refusals.append("the history cannot be evaluated: " + "; ".join(u.refusals))
    if not u.complete:
        refusals.append(
            "the history is INCOMPLETE: " + "; ".join(u.incomplete)
            + " A universe with unread filings understates membership without "
              "looking like an error, so it is not declarable.")
    if u.derived and u.complete and not u.registry_grade:
        refusals.append("the derivation is not registry-grade (frame overridden)")
    return refusals


def _universe_block(prev: dict, u: au.PointInTimeUniverse, *,
                    history: Path) -> dict[str, Any]:
    """v1.8's universe entry: v1.7's block with the corrected derivation in it."""
    block = copy.deepcopy(prev)

    block["membership_intervals"] = [i.as_dict() for i in u.intervals]
    block["members_ever"] = list(u.members_ever)
    block["members_ever_count"] = len(u.members_ever)
    block["history_artifact"] = f"{LSE.name}/{history.name}"
    block["history_artifact_sha256"] = _sha256(history)
    block["filings_evaluated"] = u.evidence.get("filings_evaluated")
    block["tickers_walked"] = u.evidence.get("tickers_walked")

    block["corpus_correction_2026_08_29"] = {
        "defect": (
            "Every anchor required the percentage and the denominator to be "
            "ADJACENT -- '<pct>% of <basis>'. Filings state the denominator "
            "once in a scope clause and then list parties carrying bare "
            "percentages, in prose or as a table. No such list could be read, "
            "whatever verb or layout it used: the surface form is incidental "
            "and the structural fact is that the denominator is not repeated "
            "per party."),
        "why_it_mattered": (
            "All three membership errors below are the same error -- DATA "
            "AVAILABILITY DECIDING MEMBERSHIP, which AU-1..AU-6 forbid. The "
            "rule, the frame, the threshold and the filings are unchanged; "
            "only what the extractor could read changed."),
        "extended": {
            "INTC": (
                "The interval closed at 2017-02-17, which is the filing in "
                "which Intel MOVED the named-customer disclosure out of Item "
                "1 prose and into the segment note -- not the year the "
                "relationship ended. Dell Inc. is disclosed at 15-21% of net "
                "revenue in every filing from 2017-02-17 through 2024-01-26, "
                "alongside Lenovo Group Limited at 11-13% and HP Inc. at "
                "10-11%. Membership now runs 2005-02-22 to 2025-01-31."),
        },
        "added": {
            "ADBE": (
                "Ingram Micro at 11-21% of net revenue across 2008-2015, "
                "disclosed in a table headed 'The table below lists our "
                "significant customers, as a percentage of net revenue', with "
                "Tech Data at 10% in the fiscal-2007 filing. Adobe appeared "
                "in no previous registry version."),
            "JBL": (
                "Jabil's 10-Ks carry an explicit table of 'customers who "
                "accounted for 10% or more of the Company's net revenues, "
                "expressed as a percentage of consolidated net revenue': Dell "
                "Computer Corporation (FY2001), Cisco Systems (FY2002-FY2013, "
                "10-24%), Marconi Communications, Royal Philips Electronics, "
                "Hewlett-Packard Company, Nokia Corporation, BlackBerry "
                "Limited and Apple, Inc. (FY2012-FY2024, 11-28%). Twenty-four "
                "qualifying filings, and Jabil appeared in no previous "
                "registry version."),
        },
        "both_new_exits_are_the_rule_working": (
            "INTC's membership ends 2025-01-31 and JBL's 2025-10-17 because "
            "in those filings Intel and Jabil ANONYMISED their customers to "
            "'Customer A / B / C'. A concentration whose counterparty is not "
            "named cannot support a bilateral relationship and the rule "
            "excludes it. These are rule-based exits, not reading failures, "
            "and they are enforced by the same control that keeps 'Customer "
            "A' out of every other filing."),
        "fabrication_routes_closed": (
            "The first draft of the scoped-list reader was measured against "
            "all 1,250 filings before it was believed, and produced six "
            "fabrication routes, every one of which is now closed with a "
            "verbatim regression fixture: a bare 'Inc' from the comma in "
            "'Apple, Inc.' in 26 filings; 'Hong Kong', 'South Korean', "
            "'European' and 'There' from rows read out of LATER sentences "
            "than the scope clause; 'Constellation Wines' from 'reported "
            "within the ... segment'; two names sharing one percentage; and "
            "Rite Aid at 49% OF REVENUE read off a sentence about "
            "receivables. Spot-checking would not have found them."),
        "what_it_refuses": (
            "Column order is NOT a convention -- INTC, ADBE, CTSH and JBL "
            "list years newest-first while GOOGL lists '2023 2024' "
            "oldest-first, all in this corpus -- so the year header is READ, "
            "and a multi-column list whose header is unreadable, or whose "
            "header never names the reporting year, yields nothing. Two "
            "blocks sharing one year row are read only while the revenue "
            "label precedes the receivables label, which is checked rather "
            "than assumed. A single bare column must sit in the scope "
            "clause's own sentence."),
        "verification": (
            "Re-derived offline from the response cache at ZERO SEC "
            "requests, over the same 1,250 filings with zero failures. Corpus "
            "diff against the v1.7 run: 86 edges ADDED, ZERO REMOVED -- no "
            "existing edge changed or disappeared. Every added named party is "
            "a real company: Ingram Micro, Tech Data, Dell, HP, Lenovo, "
            "Apple, Cisco, Nokia, Royal Philips, Marconi, BlackBerry, "
            "Hewlett-Packard. No geography, no segment, no aggregate, no bare "
            "legal suffix."),
    }

    block["known_limitations"] = list(prev.get("known_limitations", [])) + [
        "A METRIC-LABELLED BLOCK TABLE is refused outright. Some filers head "
        "a block with the party and then label each row of figures by METRIC "
        "-- 'Reyes Beer Division entities / Net sales 27.5 % / Accounts "
        "receivable 22.0 %' -- so the nearest label to every figure is a "
        "metric, not a party. This reader cannot attribute those rows and "
        "takes NONE of them. MEASURED COST: STZ discloses Reyes Beer Division "
        "entities at 25-27% and Southern Glazer's Wine and Spirits at 11-13% "
        "of net sales, and STZ is therefore NOT a member. Missing a real "
        "relationship is the safe direction; inventing one is not.",
        "'and' is not a name continuation, because allowing it produced two "
        "names sharing one percentage. A counterparty whose registered name "
        "contains 'and' is therefore truncated -- 'Southern Wine and Spirits' "
        "is captured as 'Southern Wine'. Both instances in this corpus are "
        "receivables-basis and change no membership.",
        "A row is read only when its cell count matches the year header's "
        "width, with the filer's own '*' placeholder counted as a column. A "
        "table whose rows disagree with its header is refused rather than "
        "aligned by guess.",
    ]

    block["derivation_is_not_assertion"] = (
        "build_v1_8 has no parameter for the membership intervals. It derives "
        "them from the pinned history, writes the result, then RE-DERIVES "
        "independently and refuses to write a document whose intervals it "
        "cannot reproduce. The published artifact is re-checked against the "
        "rule on every test run.")

    return block


def build_v1_8(*, v1_7: Path = V1_7, history: Path = HISTORY,
               authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str], au.PointInTimeUniverse]:
    """Return (v1.8 document, changes, derivation). Pure; writes nothing."""
    src = _load(v1_7)
    doc = copy.deepcopy(src)
    changes: list[str] = []
    date = authored_at or AUTHORED_AT

    u = au.derive_universe_point_in_time(_load(history))
    if not u.registry_grade:
        raise RefusedError(
            "the point-in-time derivation is not registry-grade. refusals="
            + "; ".join(u.refusals) + " incomplete=" + "; ".join(u.incomplete))
    if not u.intervals:
        raise RefusedError(
            "the derivation produced no intervals; there is nothing to declare")

    doc["registry_version"] = "1.8"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_7.name
    doc["supersedes_sha256"] = _sha256(v1_7)
    doc["companion_markdown"] = f"{LSE.name}/{V1_8_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_7.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte, including the INTC interval this version extends and "
        "the absence of ADBE and JBL that this version corrects -- a "
        "superseded version is allowed to be wrong, which is what superseded "
        "means. This version corrects the CORPUS READING, not the rule. It "
        "resolves no analysis decision, changes no threshold, moves no "
        "hypothesis, alters no measurement, and opens no display-gate "
        "condition.")
    doc["change_summary"] = (
        "Corrects HYP-04 anchor-universe membership after a structural "
        "extractor defect was measured against the full cached corpus: every "
        "anchor required the percentage and its denominator to be ADJACENT, "
        "so a list of parties governed by a scope clause that states the "
        "denominator once was unreadable in prose and as a table alike. The "
        "rule is unchanged -- AU-1..AU-6, 10% of consolidated revenue, ASC "
        "280-10-50-42's own parameters -- and so is the point-in-time "
        "evaluation basis. INTC's interval EXTENDS from 2017-02-17 to "
        "2025-01-31, its old end being the filing in which Intel moved the "
        "disclosure out of Item 1 rather than the year Dell fell below the "
        "threshold; ADBE and JBL are ADDED, neither having appeared in any "
        "previous version, on 7 and 24 qualifying filings respectively. All "
        "three were DATA AVAILABILITY DECIDING MEMBERSHIP, which the rule "
        "forbids. INTC and JBL both EXIT when the filer anonymises its "
        "customers to 'Customer A', which is the rule working. "
        f"Applying the rule across {u.evidence.get('filings_evaluated')} "
        f"filings yields {len(u.members_ever)} member(s) ever: "
        f"{', '.join(u.members_ever) or '(none)'}, over "
        f"{len(u.intervals)} interval(s). NO hypothesis is modified, "
        "reclassified, promoted, demoted or re-thresholded; "
        "required_eligibility_class is unchanged. HYP-04's status remains "
        "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED, every eligible-event "
        "counter remains zero, and the gate stays CLOSED with C4 MET.")
    changes.append(f"registry_version 1.7 -> 1.8, authored_at_utc {date}")
    changes.append(f"companion_markdown -> {V1_8_MARKDOWN.name}")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in v1.7")
    prev_block = entry.get("anchor_universe")
    if not isinstance(prev_block, dict):
        raise RefusedError(f"{HYPOTHESIS_ID} has no anchor_universe to supersede")
    if not prev_block.get("membership_intervals"):
        raise RefusedError(
            "v1.7's universe carries no membership_intervals; this generator "
            "supersedes a POINT-IN-TIME universe, not a snapshot")

    entry["anchor_universe"] = _universe_block(prev_block, u, history=history)
    new_block = entry["anchor_universe"]

    before = {i["ticker"] for i in prev_block["membership_intervals"]}
    after = set(u.members_ever)
    changes.append(
        f"{HYPOTHESIS_ID}.anchor_universe: members {sorted(before)} -> "
        f"{sorted(after)}; removed={sorted(before - after)} "
        f"added={sorted(after - before)}")

    doc["findings_responded_to"] = {
        "documents": list(FINDINGS),
        "note": (
            "Dated findings recorded BEFORE this version and left on disk "
            "unedited. The last is the reason this version exists."),
    }
    changes.append("findings_responded_to: adds the 2026-08-29 finding")

    # --- the rule did not change, checked not assumed ---------------------
    for f in RULE_FIELDS_THAT_MUST_NOT_MOVE:
        if new_block.get(f) != prev_block.get(f):
            raise RefusedError(
                f"anchor_universe.{f} changed. v1.8 corrects what the "
                "extractor READS, never what the rule ASKS.")
    for f in EVALUATION_FIELDS_THAT_MUST_NOT_MOVE:
        if new_block.get(f) != prev_block.get(f):
            raise RefusedError(
                f"anchor_universe.{f} changed. v1.6 established the "
                "point-in-time basis and v1.8 keeps it.")
    if [c["id"] for c in new_block.get("conditions", [])] != \
            [c for c, _ in au.CONDITIONS]:
        raise RefusedError(
            "the written conditions do not match anchor_universe.CONDITIONS")
    changes.append("guard: the rule's own fields are byte-identical to v1.7")

    # --- membership MUST have moved, or this version has no reason to exist
    if [i.as_dict() for i in u.intervals] == prev_block["membership_intervals"]:
        raise RefusedError(
            "the derived intervals are identical to v1.7's. A registry "
            "version that changes nothing is noise in the chain -- if the "
            "extractor fix moved no membership, publish the finding and stop.")
    changes.append("guard: membership actually moved")

    # --- immovability, checked not assumed --------------------------------
    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(f"hypothesis list changed: {ids_old} -> {ids_new}")

    old_entry = next(h for h in src["hypotheses"]
                     if h["hypothesis_id"] == HYPOTHESIS_ID)
    for f in IMMOVABLE_HYP04_FIELDS:
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(f"{HYPOTHESIS_ID}.{f} changed")
    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.8 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Correcting an anchor universe "
            "creates no eligible anchor event -- if this moved, membership "
            "has been mistaken for a capture path.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed")
    if doc.get("peer_price_data_policy") != src.get("peer_price_data_policy"):
        raise RefusedError("peer_price_data_policy changed; v1.8 applies it, "
                           "it does not amend it")

    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.8 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes on v1.8")

    again = au.derive_universe_point_in_time(_load(history))
    written = new_block["membership_intervals"]
    if not again.registry_grade or [i.as_dict() for i in again.intervals] != written:
        raise RefusedError("re-derivation disagrees with what would be written")
    changes.append(
        f"guard: intervals re-derived independently -> {len(again.intervals)}")

    return doc, changes, u


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.8 from v1.7, correcting "
                    "anchor-universe membership after the scoped-list fix.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.8 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes, u = build_v1_8(authored_at=a.authored_at)
    print(au.format_point_in_time_report(u))
    print("\nChanges v1.7 -> v1.8:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_8.name}.")
        return 0

    before = _sha256(V1_7)
    V1_8.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if _sha256(V1_7) != before:
        raise RefusedError("v1.7 changed on disk during generation")

    print(f"\nWrote {V1_8.name}")
    print(f"v1.7 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
