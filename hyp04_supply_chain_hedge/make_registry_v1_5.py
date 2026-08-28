#!/usr/bin/env python3
"""Generate hypothesis-registry v1.5 from v1.4 -- declare the HYP-04 anchor universe.

NOT A TEST. NOT RUN BY CI. Named off the `test_*` discovery pattern for the
same reason the live audit runners and the other registry generators are.

=== WHAT v1.5 ADDS AND WHY ===

The 2026-08-26 anchor-universe finding recorded a deadlock: the anchors with
linkage edges (MCK, PKG) are outside the project's locked 24-ticker universe,
and the anchors inside it have no linkage edges -- the same screen found zero
named counterparties among the locked 24.

The obvious fix is to add MCK and PKG to the anchor universe. That is choosing
the universe because those are the tickers that turned out to have usable
edges. Every edge is real and filing-backed, and it would still be selection
on the data after seeing it, which is what locking a universe exists to
prevent.

v1.5 does the other thing. It registers a RULE, evaluates it over a frame
fixed weeks earlier for unrelated reasons, and records whatever comes out.

=== THE MEMBER LIST IS DERIVED HERE, NOT TYPED HERE ===

There is no parameter for it and no constant holding it. `build_v1_5()` runs
`anchor_universe.derive_universe()` over a pinned EDGAR screen, writes what
that returns, and then RE-DERIVES and refuses if the two disagree. The
registry's conditions and rejected-conditions lists are likewise copied out of
`anchor_universe` at generation time, so the document cannot drift from the
code that implements it.

=== THE RULE WAS WRITTEN AFTER THE SCREEN WAS SEEN. THAT IS RECORDED. ===

Pretending otherwise would be false: the screen ran on 2026-08-26 and this
rule was written on 2026-08-27. What protects it is not ignorance of the data
but two checkable things, both written into the artifact:

  * its parameters are ASC 280-10-50-42's own -- 10 percent, of the ENTITY's
    revenues, in an annual report -- not numbers picked to fit an observed set;
  * applying it COSTS a ticker. PKG is excluded, and PKG is one of only two
    companies in the screen with a named counterparty and one of the two
    curated linkage edges. A rule fitted to the observed set would have kept
    both.

The alternative that would have retained PKG -- accepting a segment-level
denominator -- was considered and is recorded as rejected, with its reason, so
that adopting it later is a visible reversal rather than a quiet widening.

=== WHAT v1.5 DOES NOT DO ===

It moves no display-gate condition. C2 counts eligible ANCHOR EVENTS, and
eligibility is decided by `gst_market_response.completeness` from per-event
capture records. Declaring who MAY be an anchor produces no such record for
anybody, and no capture path runs over MCK. The gate stays CLOSED with C4 MET
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

V1_4 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.4.json"
V1_5 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json"
V1_5_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5_DRAFT.md"

# The screen the rule is evaluated over. Pinned by name AND hash in the
# artifact, so the derivation is reproducible from what is committed.
SCREEN = LSE / "HYP04_EDGAR_CANDIDATE_LINKAGE_FULL51_2026-08-27.json"

HYPOTHESIS_ID = "HYP-04"
AUTHORED_AT = "2026-08-27"
CUTOFF_DATE = "2026-08-27"

# Findings this version responds to. Both stay on disk unedited.
FINDINGS = (
    "Live Signal Engine/HYP04_ANCHOR_UNIVERSE_FINDING_2026-08-26.md",
    "Live Signal Engine/HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md",
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


class RefusedError(RuntimeError):
    """Raised when a precondition for generating v1.5 is not met."""


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def check_preconditions(*, v1_4: Path = V1_4, v1_5: Path = V1_5,
                        screen: Path = SCREEN) -> list[str]:
    refusals: list[str] = []
    if not v1_4.is_file():
        refusals.append(f"registry v1.4 not found at {v1_4.name}")
    if v1_5.exists():
        refusals.append(
            f"{v1_5.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really intended.")
    if not screen.is_file():
        refusals.append(f"EDGAR screen not found at {screen.name}")
        return refusals

    d = au.derive_universe(_load(screen), cutoff_date=CUTOFF_DATE)
    if not d.derived:
        refusals.append(
            "the screen cannot be evaluated by the rule: "
            + "; ".join(d.refusals))
    return refusals


def _universe_block(d: au.UniverseDerivation, *, screen: Path) -> dict[str, Any]:
    """The registry's anchor-universe entry, built FROM the derivation."""
    provenance: dict[str, Any] = {}
    not_qualifying: list[dict[str, Any]] = []
    for q in d.qualifications:
        if q.qualifies:
            provenance[q.ticker] = q.evidence["qualifying_disclosures"]
        else:
            for e in q.evidence.get("near_misses", []):
                if e.get("counterparty"):
                    not_qualifying.append({"ticker": q.ticker, **e})

    return {
        "rule_id": d.rule_id,
        "character": (
            "A RULE, evaluated. Not a list, chosen. Tickers QUALIFY by "
            "satisfying a criterion fixed in advance; none is named into this "
            "universe."),
        "implemented_by": "hyp04_supply_chain_hedge/anchor_universe.py",
        "cutoff_date": d.cutoff_date,
        "why_hyp04_needs_its_own_anchor_universe": (
            "Recorded as a measured finding on 2026-08-26 and unchanged since: "
            "the two companies in the 51-ticker EDGAR screen that disclose a "
            "named counterparty concentration -- MCK and PKG -- are both "
            "OUTSIDE the project's locked 24-ticker universe, and the same "
            "screen found ZERO named counterparties among the locked 24. "
            "Extending the locked universe to fix that would select it on the "
            "observed edges. The locked 24 is HYP-01 confirmatory "
            "infrastructure with its own drift test; HYP-04 is exploratory and "
            "does not modify it."),
        "screening_frame": {
            "definition": (
                "The locked 24 anchors, plus the Phase 0 candidate peer "
                "universe read from AllTickers_Sectors.csv. Derived at "
                "evaluation time by anchor_universe.screening_frame(); not "
                "restated here as a list that could drift."),
            "size": d.evidence["frame_size"],
            "tickers": d.evidence["frame"],
            "predates_this_version": (
                "Checkable in git rather than asserted: the sector file arrived "
                "in the initial commit (77c18d5, 2026-07-23); "
                "candidate_peer_universe() was written 2026-08-18 (42cc220); "
                "the first curated linkage edge did not exist until 2026-08-22 "
                "(9f76358). MCK and PKG were inside this frame more than a "
                "month before any edge involving either of them existed. The "
                "frame was not drawn around them."),
        },
        "conditions": [{"id": cid, "requirement": text}
                       for cid, text in au.CONDITIONS],
        "conditions_source": (
            "Copied from anchor_universe.CONDITIONS at generation time so this "
            "document cannot drift from the code that implements it."),
        "threshold_pct": au.CONCENTRATION_THRESHOLD_PCT,
        "required_denominator": au.REQUIRED_BASIS,
        "parameters_are_the_standard_s_own": (
            "ASC 280-10-50-42 requires disclosure of reliance on a single "
            "customer at '10 percent or more of an entity's revenues'. Both "
            "the threshold and the denominator are taken from the standard. "
            "Neither was chosen to suit an observed set of tickers, and "
            "changing either to alter which tickers qualify would be the "
            "selection this rule exists to prevent."),
        "conditions_deliberately_rejected": [
            {"condition": name, "why_rejected": why}
            for name, why in au.NEVER_CONDITIONS],
        "screen_artifact": f"{LSE.name}/{screen.name}",
        "screen_artifact_sha256": _sha256(screen),
        "screen_generated_at_utc": d.evidence.get("screen_generated_at_utc"),
        "screened_edges": d.evidence.get("screened_edges"),
        "evaluated": d.evidence.get("evaluated"),
        "derived_members": list(d.members),
        "derived_members_count": len(d.members),
        "derived_members_provenance": provenance,
        "screened_but_not_qualifying": not_qualifying,
        "derivation_is_not_assertion": (
            "make_registry_v1_5.build_v1_5() has no parameter for the member "
            "list and no constant holding it. It runs "
            "anchor_universe.derive_universe() over the pinned screen, writes "
            "the result, then RE-DERIVES and refuses to write a document whose "
            "member list disagrees."),
        "the_rule_was_written_after_the_screen_was_seen": {
            "acknowledged": True,
            "sequence": (
                "The 51-ticker screen ran 2026-08-26. This rule was written "
                "2026-08-27. Claiming the rule predates the data would be "
                "false, and this registry does not claim it."),
            "what_actually_protects_it": (
                "Two things, both checkable. (1) The rule's parameters are ASC "
                "280-10-50-42's own, not numbers picked to fit an observed "
                "set. (2) Applying it COSTS a ticker: PKG is excluded, and PKG "
                "is one of only two companies in the screen with a named "
                "counterparty and one of the two curated linkage edges. A rule "
                "fitted to the observed set would have kept both."),
            "alternative_considered_and_rejected": {
                "alternative": (
                    "Accept a SEGMENT-level denominator, so that PKG's "
                    "'58% of our Paper segment sales revenue' qualifies."),
                "effect": "The universe would be MCK and PKG instead of MCK.",
                "why_rejected": (
                    "It is the variant that retains the ticker already known to "
                    "be there, which is the definition of fitting the rule to "
                    "the data. It also does not survive on its own terms: PKG's "
                    "10-K filed 2026-02-26 says, in the same sentence, that "
                    "sales to ODP were '58% of our Paper segment sales revenue "
                    "and 4% of our consolidated sales revenue'. At the entity "
                    "level -- which is the level at which an earnings shock "
                    "moves the anchor's equity -- the relationship is 4%, below "
                    "ASC 280's own bar."),
                "how_to_reverse_it": (
                    "A further dated registry version, authored before the "
                    "results that would motivate the change are seen, exactly "
                    "as the promotion_rule requires."),
            },
        },
        "membership_is_not_eligibility": (
            "This universe says who MAY be a HYP-04 anchor. It creates no "
            "eligible anchor event. required_eligibility_class is UNCHANGED at "
            "core_attention_vs_equity_response, eligibility is decided by "
            "gst_market_response.completeness from per-event capture records, "
            "and no capture path runs over these tickers. Every eligible-event "
            "counter in this registry remains zero and no display-gate "
            "condition moves."),
        "revision_rule": (
            "The rule, the frame, the threshold and the denominator may be "
            "changed only by a further dated registry version authored before "
            "the results that would motivate the change are seen. Re-running "
            "the screen at a later cutoff and recording a different membership "
            "is NOT a revision -- it is the rule doing its job -- provided the "
            "rule itself is unchanged."),
        "not_evidence": (
            "Nothing in this block is evidence about supply-chain transmission."),
    }


def _peer_data_policy() -> dict[str, Any]:
    return {
        "statement": (
            "Peer-side price data availability is a MEASURABILITY question, "
            "reported per pair. It is never a MEMBERSHIP question, and it never "
            "decides which anchors or peers are in scope."),
        "why": (
            "A price source that drops delisted securities is "
            "survivorship-biased by construction. The peers most likely to "
            "disappear are those acquired or taken private, and acquisition is "
            "frequently CAUSED by the commercial relationship under study, so "
            "the missing observations are not missing at random with respect to "
            "this hypothesis. Letting the provider decide the universe would "
            "import that bias into the preregistration."),
        "measured_instance": (
            "ODP -- the counterparty in PKG's curated edge -- ceased to be a "
            "public SEC filer at some point after PKG's 10-K of 2026-02-26, "
            "which still named it PKG's largest Paper-segment customer. It is "
            "absent from SEC's 10,388-entry company_tickers.json, and the "
            "provider used for peer closes returns zero rows for it at every "
            "window from 2016 to 2026 -- the entire history, not just recent "
            "quotes. Recorded 2026-08-26 in "
            "HYP04_CLOSES_COLLECTION_FINDING_2026-08-26.md."),
        "consequence_for_this_registry": (
            "None to the universe. ODP's disappearance does not retroactively "
            "make the PKG-ODP relationship false, and PKG's exclusion from the "
            "anchor universe is decided by the concentration denominator, not "
            "by ODP's tradability. Had the rule conditioned on obtainable "
            "prices, PKG would have been excluded for a reason that is pure "
            "survivorship, and that is precisely the outcome this policy "
            "forbids."),
        "what_is_still_required": (
            "A survivorship-bias-free peer price source before any HYP-04 "
            "measurement is run. None has been selected. Restricting to "
            "survivors instead is permitted only if the restriction and its "
            "bias are stated in the registry version that does it."),
        "no_option_taken_here": True,
    }


def build_v1_5(*, v1_4: Path = V1_4, screen: Path = SCREEN,
               authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str], au.UniverseDerivation]:
    """Return (v1.5 document, changes, derivation). Pure; writes nothing."""
    src = _load(v1_4)
    doc = copy.deepcopy(src)
    changes: list[str] = []
    date = authored_at or AUTHORED_AT

    screen_doc = _load(screen)
    d = au.derive_universe(screen_doc, cutoff_date=CUTOFF_DATE)
    if not d.derived:
        raise RefusedError(
            "the screen cannot be evaluated by the rule: " + "; ".join(d.refusals))

    frame = set(d.evidence["frame"])
    if not set(d.members) <= frame:
        raise RefusedError("derived members are not a subset of the frame")
    if set(d.members) == frame:
        raise RefusedError(
            "the derived universe equals the whole frame, which would make the "
            "rule decorative rather than selective")

    doc["registry_version"] = "1.5"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_4.name
    doc["supersedes_sha256"] = _sha256(v1_4)
    doc["companion_markdown"] = f"{LSE.name}/{V1_5_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_4.name} is NOT edited in place. It remains on disk, unchanged, "
        "byte-for-byte. This version ADDS a declaration -- the HYP-04 anchor "
        "universe -- and a peer-data policy. It resolves no analysis decision, "
        "changes no threshold, moves no hypothesis, alters no measurement, and "
        "opens no display-gate condition.")
    doc["change_summary"] = (
        "Declares the HYP-04 ANCHOR UNIVERSE as a RULE rather than a list, and "
        "records the peer-data survivorship policy. The rule is evaluated over "
        "a screening frame fixed weeks earlier for unrelated reasons; its "
        "threshold and denominator are ASC 280-10-50-42's own; and its member "
        "list is DERIVED at generation time from a pinned EDGAR screen, never "
        "typed in. Applying it yields "
        f"{len(d.members)} member(s): {', '.join(d.members) or '(none)'}. "
        "PKG is excluded -- its disclosed 58% is of the Paper SEGMENT, and the "
        "same sentence puts the entity-wide figure at 4%. NO hypothesis is "
        "modified, reclassified, promoted, demoted or re-thresholded; no "
        "measurement or capture path changes; required_eligibility_class is "
        "unchanged. HYP-04's status remains "
        "PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED, every eligible-event "
        "counter remains zero, and the gate stays CLOSED with C4 MET.")
    changes.append(f"registry_version 1.4 -> 1.5, authored_at_utc {date}")
    changes.append(f"companion_markdown -> {V1_5_MARKDOWN.name}")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in v1.4")
    if "anchor_universe" in entry:
        raise RefusedError(f"{HYPOTHESIS_ID} already declares an anchor_universe")

    entry["anchor_universe"] = _universe_block(d, screen=screen)
    changes.append(
        f"{HYPOTHESIS_ID}.anchor_universe: rule {d.rule_id}, "
        f"{len(d.members)} member(s) derived from {len(frame)} evaluated")

    doc["peer_price_data_policy"] = _peer_data_policy()
    changes.append("peer_price_data_policy: availability never decides "
                   "membership; survivorship stated")

    doc["findings_responded_to"] = {
        "documents": list(FINDINGS),
        "note": (
            "Both are dated findings recorded BEFORE this version and left on "
            "disk unedited. The first is the reason an anchor universe is "
            "declared at all; the second is the reason data availability is "
            "explicitly excluded from deciding it."),
    }
    changes.append("findings_responded_to: the two 2026-08-26 findings, by reference")

    # --- immovability, checked not assumed --------------------------------
    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(f"hypothesis list changed: {ids_old} -> {ids_new}")
    if doc.get("hypotheses_carried_forward_unchanged") != \
            src.get("hypotheses_carried_forward_unchanged"):
        raise RefusedError("hypotheses_carried_forward_unchanged was touched")

    old_entry = next(h for h in src["hypotheses"]
                     if h["hypothesis_id"] == HYPOTHESIS_ID)
    for f in IMMOVABLE_HYP04_FIELDS:
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{f} changed; v1.5 only ADDS a universe "
                "declaration")
    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.5 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Declaring an anchor universe "
            "creates no eligible anchor event -- if this moved, the "
            "declaration has been mistaken for a capture path.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed; v1.5 governs nothing new")

    # --- v1.4's guard, still guarding -------------------------------------
    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.5 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes on v1.5")

    # --- the universe, re-derived and compared ----------------------------
    again = au.derive_universe(_load(screen), cutoff_date=CUTOFF_DATE)
    written = entry["anchor_universe"]["derived_members"]
    if not again.derived or list(again.members) != written:
        raise RefusedError(
            f"re-derivation disagrees with what would be written: "
            f"{list(again.members)} vs {written}")
    if [c["id"] for c in written_conditions(entry)] != [c for c, _ in au.CONDITIONS]:
        raise RefusedError("the written conditions do not match anchor_universe.CONDITIONS")
    changes.append(
        f"guard: universe re-derived independently -> {list(again.members)}")

    return doc, changes, d


def written_conditions(entry: dict) -> list[dict[str, Any]]:
    return entry.get("anchor_universe", {}).get("conditions", [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.5 from v1.4, declaring "
                    "the HYP-04 anchor universe as a rule.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.5 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes, d = build_v1_5(authored_at=a.authored_at)

    print(au.format_report(d))
    print("\nChanges v1.4 -> v1.5:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_5.name}.")
        return 0

    before = _sha256(V1_4)
    V1_5.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if _sha256(V1_4) != before:
        raise RefusedError("v1.4 changed on disk during generation")

    print(f"\nWrote {V1_5.name}")
    print(f"v1.4 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials "
          "across the bump.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
