#!/usr/bin/env python3
"""Generate hypothesis-registry v1.7 from v1.6 -- HYP-04.

=== WHAT CHANGES, AND WHY IT IS NOT THE RULE ===

v1.6 evaluates the anchor-universe rule point-in-time. That basis is correct
and does not change here. What changes is the EXTRACTOR that reads the corpus
the rule is evaluated over, and therefore the membership the same rule yields.

Two defects in v1.6's derivation are corrected:

  * MCHP WAS NEVER ENTITLED TO MEMBERSHIP. Both filings behind its interval
    disclose a concentration for a year OTHER than the one they report on --
    "10% of our net sales in each of fiscal 2012 and fiscal 2011" in a FY2013
    report, and "in fiscal 2012" in a FY2014 report. The stale-comparative
    gate measured staleness against the FILING DATE, whose window has to be
    two years wide to avoid rejecting the reporting year of a calendar-year
    filer, and that slack admitted the comparative. v1.6's own companion
    records this imprecision as a stated limitation and says it "changes no
    membership here". It did. It manufactured a member.

  * NKE WAS INVISIBLE. NIKE discloses Foot Locker at 10.9%-12.4% of
    consolidated revenues across FY2000-FY2002 -- "our largest single
    customer" in its own words -- in a multi-year "respectively" construction
    the anchor could not read, behind a possessive denominator it could not
    match, with a name the party parser truncated to the bare suffix "Inc".

THE RULE ITSELF IS UNTOUCHED. AU-1..AU-6, the 10% threshold and the
consolidated-revenue denominator are ASC 280-10-50-42's own and are checked
byte-identical against v1.6. A registry version may change what the extractor
can SEE; it may never change what the rule ASKS.

=== WHY A VERSION IS REQUIRED AT ALL ===

The registry suites re-derive from the STORED corpus artifact, so they verify
that a published artifact matches the corpus it was built from -- not that it
matches today's code. Once the extractor changed, the repository held an
extractor deriving one universe and an authoritative registry describing
another, with no test able to see it. That divergence is resolved only by
authoring a version.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_7 --write

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

V1_6 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.6.json"
V1_7 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7.json"
V1_7_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7_DRAFT.md"

HISTORY = LSE / "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-28_v2.json"

AUTHORED_AT = "2026-08-28"

FINDINGS = (
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_POINT_IN_TIME_FINDING_2026-08-27.md",
    "Live Signal Engine/HYP04_EXTRACTOR_POSSESSIVE_DENOMINATOR_FINDING_2026-08-27.md",
    "Live Signal Engine/HYP04_EXTRACTOR_GAP_MEASUREMENT_FINDING_2026-08-28.md",
)

# v1.6 declared these; v1.7 must not disturb them. Membership moving is the
# POINT of this version, so membership fields are deliberately absent.
EVALUATION_FIELDS_THAT_MUST_NOT_MOVE = (
    "evaluation_basis", "membership_is_a_span_not_a_flag",
)


def check_preconditions(*, v1_6: Path = V1_6, v1_7: Path = V1_7,
                        history: Path = HISTORY) -> list[str]:
    refusals: list[str] = []
    if not v1_6.is_file():
        refusals.append(f"registry v1.6 not found at {v1_6.name}")
    if v1_7.exists():
        refusals.append(
            f"{v1_7.name} already exists. Refusing to overwrite a governance "
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
    """v1.7's universe entry: v1.6's block with the corrected derivation in it.

    Starts from v1.6 and replaces only what the corpus correction moved. The
    rule's fields are carried across untouched and then checked, rather than
    rewritten and hoped to match.
    """
    block = copy.deepcopy(prev)

    block["membership_intervals"] = [i.as_dict() for i in u.intervals]
    block["members_ever"] = list(u.members_ever)
    block["members_ever_count"] = len(u.members_ever)
    block["history_artifact"] = f"{LSE.name}/{history.name}"
    block["history_artifact_sha256"] = _sha256(history)
    block["filings_evaluated"] = u.evidence.get("filings_evaluated")
    block["tickers_walked"] = u.evidence.get("tickers_walked")

    block["corpus_correction_2026_08_28"] = {
        "why": (
            "The same rule, evaluated over the same 51-ticker frame and the "
            "same filings, yielded a different universe once the extractor "
            "could read the filings correctly. Membership moved in BOTH "
            "directions, which is the evidence that this is a correction and "
            "not a widening: a change that only ever adds members is "
            "indistinguishable from a loosened threshold."),
        "removed": {
            "MCHP": (
                "Its v1.6 interval rested on a STALE COMPARATIVE. The 10-K "
                "filed 2013-05-30 (period 2013-03-31) says Future Electronics "
                "was 'approximately 10% of our net sales in each of fiscal "
                "2012 and fiscal 2011'; the 10-K filed 2014-05-30 (period "
                "2014-03-31) says 'in fiscal 2012'. NEITHER states a "
                "concentration for the year it reports on. Staleness was "
                "measured against the FILING DATE, whose window must be two "
                "years wide to avoid rejecting the reporting year of a "
                "calendar-year filer, and that slack admitted the figure."),
        },
        "added": {
            "NKE": (
                "NIKE discloses Foot Locker, Inc. at 10.9% (FY2002), 11.8% "
                "(FY2001) and 12.4% (FY2000) of CONSOLIDATED revenues, and "
                "calls it 'our largest single customer'. Three independent "
                "defects hid it: a multi-year 'respectively' construction the "
                "anchor could not read, a possessive denominator ('the "
                "Company's consolidated revenues') it could not match, and a "
                "party parser that truncated 'Foot Locker, Inc.' to the bare "
                "suffix 'Inc' at the comma."),
        },
        "also_corrected_without_moving_membership": (
            "NVDA/Celestica, which v1.6 names as a comparative that 'still "
            "passes', is now rejected; it was not an interval opener. Three "
            "counterparties stopped being mis-parsed at the comma: Ingram "
            "Micro (AAPL), Caremark RX (MCK), Hyundai Electronics (QCOM)."),
        "fabrication_routes_closed": (
            "Four constructions no gate covered: the filer's own business "
            "unit by appositive, the filer's own unit by HEAD NOUN, "
            "'including X' making X an instance of the measured category, and "
            "a comparative dated by 'year ended <Month> <day>, <year>'. THREE "
            "OF THE FOUR WERE LATENT IN v1.6'S EXTRACTOR, not introduced by "
            "the widening: with an accepted verb the published code produced "
            "the same fabrications. They were absent from the corpus only "
            "because the filings carrying them happen to use copular verbs "
            "the anchor did not match -- protection by accident."),
        "verification": (
            "Re-derived offline from the response cache at ZERO SEC requests. "
            "Corpus diff against the pre-correction run: two removals, zero "
            "additions. Exhaustive enumeration of every named disclosure at "
            "or above 10% of consolidated revenue across all 1,250 filings "
            "gives 62 disclosures over 23 distinct ticker-counterparty pairs, "
            "every one a real company -- no geography, no segment, no bare "
            "legal suffix. Zero fabrications."),
    }

    block["known_limitations"] = [
        "ASC 280 is a FLOOR. Disclosure is required only at or above 10% of "
        "revenue, so real relationships below it, most supplier "
        "relationships, and every unnamed 'Customer A' are invisible to this "
        "source. AN ABSENT MEMBER IS NOT EVIDENCE OF NO CONCENTRATION.",
        "'Company' is deliberately absent from LEGAL_ENTITY_SUFFIX, so a name "
        "carrying only that suffix in a sentence with no role word is "
        "dropped. Under-inclusive; changes no membership here.",
        "A party whose HEAD NOUN is a unit type (Group, Division, Segment) is "
        "rejected. A real firm whose name ends that way would be dropped. "
        "Measured across the corpus this rejects exactly five of the filer's "
        "own segments and no real counterparty, and 'Lenovo Group Limited' "
        "survives because its head is 'Limited'.",
        "The verb set admits equivalence phrasings but refuses generated, "
        "provided and contributed: those describe what a counterparty "
        "CONTRIBUTED rather than asserting the share IS the figure. "
        "Under-inclusive by choice.",
        "Staleness now uses the submission's period of report where one is "
        "supplied, and falls back to the filing date otherwise. The "
        "fiscal-period imprecision recorded as a limitation in v1.6 is CLOSED "
        "-- and it was not harmless: it is what admitted MCHP.",
    ]

    block["derivation_is_not_assertion"] = (
        "build_v1_7 has no parameter for the membership intervals. It derives "
        "them from the pinned history, writes the result, then RE-DERIVES "
        "independently and refuses to write a document whose intervals it "
        "cannot reproduce. The published artifact is re-checked against the "
        "rule on every test run.")

    return block


def build_v1_7(*, v1_6: Path = V1_6, history: Path = HISTORY,
               authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str], au.PointInTimeUniverse]:
    """Return (v1.7 document, changes, derivation). Pure; writes nothing."""
    src = _load(v1_6)
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

    doc["registry_version"] = "1.7"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_6.name
    doc["supersedes_sha256"] = _sha256(v1_6)
    doc["companion_markdown"] = f"{LSE.name}/{V1_7_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_6.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte, including the MCHP interval this version removes -- a "
        "superseded version is allowed to be wrong, which is what superseded "
        "means. This version corrects the CORPUS READING, not the rule. It "
        "resolves no analysis decision, changes no threshold, moves no "
        "hypothesis, alters no measurement, and opens no display-gate "
        "condition.")
    doc["change_summary"] = (
        "Corrects HYP-04 anchor-universe membership after five extractor "
        "defects were measured against the full cached corpus. The rule is "
        "unchanged -- AU-1..AU-6, 10% of consolidated revenue, ASC "
        "280-10-50-42's own parameters -- and so is the point-in-time "
        "evaluation basis v1.6 established. What changed is what the "
        "extractor can READ. Membership moves in BOTH directions: MCHP is "
        "REMOVED, its v1.6 interval having rested on a concentration "
        "disclosed for fiscal 2012 and 2011 in filings reporting fiscal 2013 "
        "and 2014; NKE is ADDED, NIKE having disclosed Foot Locker at "
        "10.9%-12.4% of consolidated revenues in a multi-year 'respectively' "
        "construction the anchor could not read. Staleness is now measured "
        "against the submission's PERIOD OF REPORT, closing a limitation v1.6 "
        "recorded as harmless and which was not -- it is what admitted MCHP. "
        f"Applying the rule across {u.evidence.get('filings_evaluated')} "
        f"filings yields {len(u.members_ever)} member(s) ever: "
        f"{', '.join(u.members_ever) or '(none)'}, over "
        f"{len(u.intervals)} interval(s). NO hypothesis is modified, "
        "reclassified, promoted, demoted or re-thresholded; "
        "required_eligibility_class is unchanged. HYP-04's status remains "
        "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED, every eligible-event "
        "counter remains zero, and the gate stays CLOSED with C4 MET.")
    changes.append(f"registry_version 1.6 -> 1.7, authored_at_utc {date}")
    changes.append(f"companion_markdown -> {V1_7_MARKDOWN.name}")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in v1.6")
    prev_block = entry.get("anchor_universe")
    if not isinstance(prev_block, dict):
        raise RefusedError(f"{HYPOTHESIS_ID} has no anchor_universe to supersede")
    if not prev_block.get("membership_intervals"):
        raise RefusedError(
            "v1.6's universe carries no membership_intervals; this generator "
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
            "unedited. The last two are the reason this version exists, and "
            "both carry amendments correcting their own earlier claims."),
    }
    changes.append("findings_responded_to: adds the two 2026-08-28 findings")

    # --- the rule did not change, checked not assumed ---------------------
    for f in RULE_FIELDS_THAT_MUST_NOT_MOVE:
        if new_block.get(f) != prev_block.get(f):
            raise RefusedError(
                f"anchor_universe.{f} changed. v1.7 corrects what the "
                "extractor READS, never what the rule ASKS.")
    for f in EVALUATION_FIELDS_THAT_MUST_NOT_MOVE:
        if new_block.get(f) != prev_block.get(f):
            raise RefusedError(
                f"anchor_universe.{f} changed. v1.6 established the "
                "point-in-time basis and v1.7 keeps it.")
    if [c["id"] for c in new_block.get("conditions", [])] != \
            [c for c, _ in au.CONDITIONS]:
        raise RefusedError(
            "the written conditions do not match anchor_universe.CONDITIONS")
    changes.append("guard: the rule's own fields are byte-identical to v1.6")

    # --- membership MUST have moved, or this version has no reason to exist
    if [i.as_dict() for i in u.intervals] == prev_block["membership_intervals"]:
        raise RefusedError(
            "the derived intervals are identical to v1.6's. A registry "
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
        raise RefusedError("results changed; v1.7 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Correcting an anchor universe "
            "creates no eligible anchor event -- if this moved, membership "
            "has been mistaken for a capture path.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed")
    if doc.get("peer_price_data_policy") != src.get("peer_price_data_policy"):
        raise RefusedError("peer_price_data_policy changed; v1.7 applies it, "
                           "it does not amend it")

    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.7 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes on v1.7")

    again = au.derive_universe_point_in_time(_load(history))
    written = new_block["membership_intervals"]
    if not again.registry_grade or [i.as_dict() for i in again.intervals] != written:
        raise RefusedError("re-derivation disagrees with what would be written")
    changes.append(
        f"guard: intervals re-derived independently -> {len(again.intervals)}")

    return doc, changes, u


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.7 from v1.6, correcting "
                    "anchor-universe membership after the extractor fixes.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.7 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes, u = build_v1_7(authored_at=a.authored_at)
    print(au.format_point_in_time_report(u))
    print("\nChanges v1.6 -> v1.7:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_7.name}.")
        return 0

    before = _sha256(V1_6)
    V1_7.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if _sha256(V1_6) != before:
        raise RefusedError("v1.6 changed on disk during generation")

    print(f"\nWrote {V1_7.name}")
    print(f"v1.6 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
