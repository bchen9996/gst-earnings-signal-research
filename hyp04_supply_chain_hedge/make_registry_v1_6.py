#!/usr/bin/env python3
"""Generate hypothesis-registry v1.6 from v1.5 -- membership becomes point-in-time.

NOT A TEST. NOT RUN BY CI. Named off the `test_*` discovery pattern for the
same reason the live audit runners and the other registry generators are.

=== WHAT v1.5 GOT WRONG, AND IT IS NOT THE RULE ===

v1.5 declared the HYP-04 anchor universe as a rule and derived one member,
MCK. The rule is right and does not change here. What was wrong is the CORPUS
it was evaluated against: `edgar_linkage.extract_for_universe()` reads only
each filer's NEWEST 10-K, so a company entered the universe only if its named
>=10% concentration is still disclosed in 2026.

That lets PERSISTENCE OF THE RELATIONSHIP TO THE PRESENT DAY decide
membership. It is the same selection v1.5's own `peer_price_data_policy`
forbids one level down: a concentration ends because the customer was
acquired, taken private or went bankrupt, and those are not independent of the
hypothesis. v1.5 forbade survivorship selection on the peer side while
practising it on the anchor side.

It also left membership and edges on different footings. The curated edges
were back-dated by a history walk to their earliest disclosing filing --
MCK->CVS to 2013-05-07 -- while membership for the same relationship was
stamped 2026-05-08.

=== WHAT v1.6 DECLARES ===

The same rule, evaluated against the 10-K IN FORCE at each point in time,
producing membership INTERVALS instead of a snapshot. The intervals SUPERSEDE
the snapshot rather than sitting beside it: a registry that asserted two
different universes would be the v1.3/v1.4 self-contradiction again.

=== THE CORPUS HAD TO BE FIXED TWICE FIRST, AND BOTH ARE RECORDED ===

Widening the corpus from 2026-only to 1996-2026 broke the attribution gates,
which had never seen older prose. Two rounds of measurement found EIGHT
fabricated counterparties -- an aggregate channel, three geographies, a
percentage shared by two firms, a superseded prior-year comparative, the
filer's own operating segment, and a category acronym. Seven structural gates
now reject them.

Round one inspected only the disclosures the report printed, which is a spot
check. Round two enumerated every named >=10% disclosure across all filings
and found three more hiding behind genuine ones on the same ticker. That is
why this generator refuses anything short of `registry_grade`.

=== WHAT v1.6 DOES NOT DO ===

It moves no display-gate condition. C2 counts eligible ANCHOR EVENTS, decided
by `gst_market_response.completeness` from per-event capture records, and no
capture path runs over any of these tickers. The gate stays CLOSED with C4 MET
and exactly four denials, and every eligible-event counter stays zero.

It does not touch the locked 24-ticker universe, `gst_market_response/`, the
cohort protocol, or any earlier registry version.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

from . import anchor_universe as au
from .make_registry_v1_4 import find_availability_contradictions

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

V1_5 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json"
V1_6 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.6.json"
V1_6_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.6_DRAFT.md"

# The point-in-time corpus. Pinned by name AND hash in the artifact.
HISTORY = LSE / "HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-27_v4.json"

HYPOTHESIS_ID = "HYP-04"
AUTHORED_AT = "2026-08-27"

FINDINGS = (
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_POINT_IN_TIME_FINDING_2026-08-27.md",
)

IMMOVABLE_HYP04_FIELDS = (
    "status", "classification", "minimum_eligible_events",
    "minimum_eligible_events_unit", "minimum_eligible_events_basis",
    "required_eligibility_class", "is_primary_confirmatory",
    "options_benchmark_required", "display_rule", "forbidden_substitutions",
    "forbidden_substitution_rule", "unresolved_analysis_decisions",
    "required_external_measurement", "capture_path_modules", "status_basis",
    "title", "question",
)

# Fields of the universe block that describe the RULE. The rule did not
# change, so these must survive v1.5 -> v1.6 byte-identical.
RULE_FIELDS_THAT_MUST_NOT_MOVE = (
    "rule_id", "conditions", "conditions_deliberately_rejected",
    "threshold_pct", "required_denominator",
    "parameters_are_the_standard_s_own",
)


class RefusedError(RuntimeError):
    """Raised when a precondition for generating v1.6 is not met."""


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def check_preconditions(*, v1_5: Path = V1_5, v1_6: Path = V1_6,
                        history: Path = HISTORY) -> list[str]:
    refusals: list[str] = []
    if not v1_5.is_file():
        refusals.append(f"registry v1.5 not found at {v1_5.name}")
    if v1_6.exists():
        refusals.append(
            f"{v1_6.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really intended.")
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
    """The v1.6 universe entry, built FROM the derivation, carrying the rule."""
    block = copy.deepcopy(prev)

    # --- what the rule is: carried forward untouched ---------------------
    block["evaluation_basis"] = "point_in_time"
    block["evaluation_basis_note"] = (
        "The rule is evaluated against the 10-K IN FORCE at each date, not "
        "against one snapshot. AU-1..AU-6, the 10% threshold and the "
        "consolidated-revenue denominator are UNCHANGED from v1.5 and remain "
        "ASC 280-10-50-42's. What changed is WHEN the rule is asked, not what "
        "it asks.")

    # --- what is now declared --------------------------------------------
    block["membership_intervals"] = [i.as_dict() for i in u.intervals]
    block["members_ever"] = list(u.members_ever)
    block["members_ever_count"] = len(u.members_ever)
    block["membership_is_a_span_not_a_flag"] = (
        "A ticker is an eligible anchor only for events inside one of its "
        "intervals. `anchor_universe.PointInTimeUniverse.qualifies_at()` is "
        "the operative test. An interval opens on the filing date that first "
        "disclosed the qualifying concentration -- the date the fact became "
        "public, which is the same claim an edge's as_of_date makes -- and "
        "closes on the filing date of the later filing that no longer "
        "qualified. The span is half-open: [start, end).")

    block["history_artifact"] = f"{LSE.name}/{history.name}"
    block["history_artifact_sha256"] = _sha256(history)
    block["filings_evaluated"] = u.evidence.get("filings_evaluated")
    block["tickers_walked"] = u.evidence.get("tickers_walked")

    # --- what it replaces, and why ---------------------------------------
    block["superseded_snapshot"] = {
        "v1_5_derived_members": prev.get("derived_members"),
        "v1_5_cutoff_date": prev.get("cutoff_date"),
        "v1_5_screen_artifact": prev.get("screen_artifact"),
        "why_superseded": (
            "v1.5's screen read only each filer's NEWEST 10-K "
            "(edgar_linkage.extract_for_universe calls client.latest_10k), so "
            "a company entered the universe only if its named >=10% "
            "concentration is STILL disclosed in 2026. That lets persistence "
            "of the relationship to the present day decide membership. A "
            "concentration ends because a customer was acquired, taken "
            "private or failed -- none of which is independent of a "
            "supply-chain transmission hypothesis -- so the companies the "
            "snapshot silently dropped are not missing at random."),
        "it_is_the_policy_v1_5_itself_states": (
            "v1.5's peer_price_data_policy forbids letting data availability "
            "decide membership, on survivorship grounds. The newest-filing "
            "screen is the same selection one level up, on the anchor side. "
            "v1.5 forbade it for peers while practising it for anchors."),
        "the_snapshot_member_was_not_wrong": (
            "MCK does disclose CVS Health at 24% of consolidated revenue in "
            "the 10-K filed 2026-05-08. The snapshot was a correct application "
            "of the rule to the corpus it was given. It is superseded because "
            "the corpus was biased, not because the answer was false."),
        "both_answers_are_not_carried": (
            "The intervals REPLACE the snapshot. A registry asserting two "
            "different universes for one hypothesis is the self-contradiction "
            "v1.4 was authored to remove."),
    }
    for gone in ("derived_members", "derived_members_count",
                 "derived_members_provenance", "screened_but_not_qualifying",
                 "screen_artifact", "screen_artifact_sha256",
                 "screen_generated_at_utc", "screened_edges", "cutoff_date",
                 "evaluated"):
        block.pop(gone, None)

    # --- how the corpus was made trustworthy ------------------------------
    block["corpus_correction"] = {
        "why_recorded": (
            "Widening the corpus from 2026-only to 1996-2026 raised the "
            "extractor's false-positive rate with no code change. The gates "
            "did not regress; the corpus outgrew them. A universe is a "
            "preregistration artifact, so a fabricated member is worse than a "
            "missing one, and the measurement belongs in the record."),
        "fabrications_found_and_rejected": 8,
        "classes": [
            "an aggregate channel ('Distributors accounted for 60% of our net sales')",
            "three geographies, two of them absent from the place-name list "
            "(Singapore, Hong Kong)",
            "a percentage shared by two named firms, attributed to one",
            "a superseded prior-year comparative in a filing that states there "
            "was no such concentration that year",
            "the filer's own operating segment ('within the Mobility Group')",
            "a category acronym in apposition ('Asustek, a CEM,')",
        ],
        "why_the_gates_are_structural": (
            "The gate that failed was the LIST -- GEOGRAPHIC_PARTY enumerated "
            "place names and contained neither Singapore nor Hong Kong. A list "
            "of places can never be complete, so all seven replacements match "
            "CONSTRUCTIONS instead."),
        "two_rounds_because_spot_checking_is_not_measurement": (
            "Round one inspected only the disclosures the report printed. "
            "Round two enumerated every named >=10% disclosure across every "
            "filing and found three more, hidden behind a genuine one on the "
            "same ticker."),
        "under_inclusion_was_measured_too": (
            "Every gate rejects, and an unrecognised denominator fails closed; "
            "both shrink a universe silently. Measured across the full corpus, "
            "exactly two named >=10% disclosures carried an unrecognised "
            "denominator, and both are Qualcomm SEGMENT revenues that the rule "
            "excludes correctly anyway."),
        "regression_fixtures": (
            "test_hyp04_supply_chain_hedge_edgar.py::test_6h, ::test_6i and "
            "::test_6j, all using verbatim filing text, each with "
            "hardcoded-open controls because a gate that rejected everything "
            "would satisfy every rejection test."),
        "retrieval_completeness": (
            "10 of 11 unreachable filings were from 2000-2001 and returned "
            "404: they predate the per-document layout. They are the OLDEST "
            "filings, which a history walk exists to reach, so losing them "
            "biases the corpus toward recent history. EdgarClient now falls "
            "back to the full-submission text and takes ONLY the 10-K "
            "document -- exhibits excluded, because "
            "HYP04_Linkage_Map_v1.0.csv records a false attribution that came "
            "from exhibit text in exactly one of these filings."),
    }

    block["known_limitations"] = [
        "The stale-comparative gate compares a stated year against the FILING "
        "date, not the submission's period of report, so one comparative year "
        "still passes. It changes no membership in this derivation.",
        "'Company' is deliberately absent from LEGAL_ENTITY_SUFFIX, so a name "
        "carrying only that suffix in a sentence with no role word is dropped "
        "(measured: Hewlett-Packard Company in Intel's 2005 10-K). Under-"
        "inclusive, and it changes no membership here.",
        "ASC 280 requires disclosure only at >=10% of revenue, so real "
        "relationships below that threshold, most supplier relationships, and "
        "every unnamed 'Customer A' disclosure are invisible to this source. "
        "An absent member is not evidence of no concentration.",
    ]

    block["derivation_is_not_assertion"] = (
        "make_registry_v1_6.build_v1_6() has no parameter for the membership "
        "intervals and no constant holding them. It runs "
        "anchor_universe.derive_universe_point_in_time() over the pinned "
        "history, writes the result, then RE-DERIVES and refuses to write a "
        "document whose intervals disagree. It also refuses anything short of "
        "registry_grade: derived AND complete AND evaluated over the full "
        "frame.")
    return block


def build_v1_6(*, v1_5: Path = V1_5, history: Path = HISTORY,
               authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str], au.PointInTimeUniverse]:
    """Return (v1.6 document, changes, derivation). Pure; writes nothing."""
    src = _load(v1_5)
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

    doc["registry_version"] = "1.6"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_5.name
    doc["supersedes_sha256"] = _sha256(v1_5)
    doc["companion_markdown"] = f"{LSE.name}/{V1_6_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_5.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte, snapshot included -- a superseded version is allowed "
        "to be wrong, which is what superseded means. This version replaces "
        "the anchor universe's evaluation basis with a point-in-time one. It "
        "resolves no analysis decision, changes no threshold, moves no "
        "hypothesis, alters no measurement, and opens no display-gate "
        "condition.")
    doc["change_summary"] = (
        "Makes HYP-04 anchor-universe membership POINT-IN-TIME. The rule is "
        "unchanged -- AU-1..AU-6, 10% of consolidated revenue, ASC "
        "280-10-50-42's own parameters -- but it is now evaluated against the "
        "10-K in force at each date rather than against each filer's newest "
        "filing only. v1.5's snapshot let persistence of the relationship to "
        "the present day decide membership, which is the survivorship "
        "selection v1.5's own peer_price_data_policy forbids on the peer "
        f"side. Applying the rule across {u.evidence.get('filings_evaluated')} "
        f"filings yields {len(u.members_ever)} member(s) ever: "
        f"{', '.join(u.members_ever) or '(none)'}, over "
        f"{len(u.intervals)} interval(s). The extractor required seven new "
        "structural attribution gates first; eight fabricated counterparties "
        "were found and rejected across two rounds of measurement, and the "
        "corpus was completed by falling back to full-submission text for "
        "pre-2001 filings. NO hypothesis is modified, reclassified, promoted, "
        "demoted or re-thresholded; required_eligibility_class is unchanged. "
        "HYP-04's status remains PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED, "
        "every eligible-event counter remains zero, and the gate stays CLOSED "
        "with C4 MET.")
    changes.append(f"registry_version 1.5 -> 1.6, authored_at_utc {date}")
    changes.append(f"companion_markdown -> {V1_6_MARKDOWN.name}")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in v1.5")
    prev_block = entry.get("anchor_universe")
    if not isinstance(prev_block, dict):
        raise RefusedError(f"{HYPOTHESIS_ID} has no anchor_universe to supersede")

    entry["anchor_universe"] = _universe_block(prev_block, u, history=history)
    changes.append(
        f"{HYPOTHESIS_ID}.anchor_universe: snapshot -> point-in-time, "
        f"{len(u.members_ever)} member(s) over {len(u.intervals)} interval(s)")

    doc["findings_responded_to"] = {
        "documents": list(FINDINGS),
        "note": (
            "Dated findings recorded BEFORE this version and left on disk "
            "unedited. The third is the reason this version exists."),
    }
    changes.append("findings_responded_to: adds the point-in-time finding")

    # --- the rule did not change, checked not assumed ---------------------
    new_block = entry["anchor_universe"]
    for f in RULE_FIELDS_THAT_MUST_NOT_MOVE:
        if new_block.get(f) != prev_block.get(f):
            raise RefusedError(
                f"anchor_universe.{f} changed. v1.6 changes WHEN the rule is "
                "evaluated, never what it says.")
    if [c["id"] for c in new_block.get("conditions", [])] != \
            [c for c, _ in au.CONDITIONS]:
        raise RefusedError("the written conditions do not match anchor_universe.CONDITIONS")
    changes.append("guard: the rule's own fields are byte-identical to v1.5")

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
        raise RefusedError("results changed; v1.6 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Widening an anchor universe "
            "creates no eligible anchor event -- if this moved, membership has "
            "been mistaken for a capture path.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed")
    if doc.get("peer_price_data_policy") != src.get("peer_price_data_policy"):
        raise RefusedError("peer_price_data_policy changed; v1.6 applies it, "
                           "it does not amend it")

    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.6 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes on v1.6")

    again = au.derive_universe_point_in_time(_load(history))
    written = new_block["membership_intervals"]
    if not again.registry_grade or [i.as_dict() for i in again.intervals] != written:
        raise RefusedError("re-derivation disagrees with what would be written")
    changes.append(
        f"guard: intervals re-derived independently -> {len(again.intervals)}")

    return doc, changes, u


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.6 from v1.5, making "
                    "anchor-universe membership point-in-time.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.6 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes, u = build_v1_6(authored_at=a.authored_at)
    print(au.format_point_in_time_report(u))
    print("\nChanges v1.5 -> v1.6:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_6.name}.")
        return 0

    before = _sha256(V1_5)
    V1_6.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if _sha256(V1_5) != before:
        raise RefusedError("v1.5 changed on disk during generation")

    print(f"\nWrote {V1_6.name}")
    print(f"v1.5 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
