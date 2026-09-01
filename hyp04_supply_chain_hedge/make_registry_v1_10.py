#!/usr/bin/env python3
"""Generate hypothesis-registry v1.10 from v1.9. HYP-04 SPECIFICATION ONLY.

=== WHAT v1.10 SETTLES ===

Two specifications that were OPEN, both taken by the repo owner on 2026-08-29
after being measured and written up first:

1. HYP04-ANCHOR-EVENT-RULE-v1 -- the 8-K results item is selected by the SEC
   numbering IN FORCE ON THE REPORT DATE, so Item 12 counts in its own era.
   Selecting on Item 2.02 alone let a 2004 renumbering decide which events
   exist. NKE had ZERO events inside its membership span and now has six.

2. The peer target's reference window ENDS AT anchor_day - 1. It used to end AT
   anchor_day -- the session the anchor's earnings news is attributed to -- so
   the peer's own response session sat inside the baseline that response is
   measured against.

Plus one gap found while planning the collection: `anchor_shock` accepts returns
and never computes them, so the RETURN BASIS was never stated. Fixed as log,
matching `peer_returns`.

=== WHY THE SECOND ONE IS ONLY LEGITIMATE TODAY ===

Removing a contaminated session from the baseline LOWERS the baseline and RAISES
the measured log-ratio. It moves results in the FAVOURABLE direction, which is
the kind of change this project's rules exist to stop being made after the fact.

It is legitimate here because NOTHING HAS BEEN MEASURED. No shock, no peer
response, no target value from production data exists, so there is no outcome
this could have been chosen to favour. That attestation is recorded in the
artifact, not just asserted here, and it will never be this cheap again --
which is precisely why the decision was taken before collecting closes rather
than after.

=== BOTH CHANGES ARE NEW KEYS, NOT MOVED FIELDS ===

`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` is EMPTY. v1.9 needed an exception
because it moved `required_eligibility_class`; v1.10 needs none, because
`IMMOVABLE_HYP04_FIELDS` contains neither of the keys it adds. The guard runs
unweakened over every field.

Nothing is added to `unresolved_analysis_decisions`. A new UNRESOLVED decision
there would flip C4 to NOT MET and produce five denials. These are measurement
SPECIFICATIONS, and v1.9 already established where those belong: the registry,
declared from the code, not the analysis lock.

=== THE GENERATOR REFUSES TO OUTRUN THE CODE ===

v1.7's companion records the failure this guards -- code implementing one thing
and an authoritative registry describing another, with no test able to see it.
`code_disagreements()` refuses to write while the repository has not already
implemented what v1.10 would declare, so the code changes land first and the
registry follows. The suite forces each disagreement and asserts the refusal
fires.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_10 --write

Named off the `test_*` pattern deliberately: this writes a governance artifact
and must only ever run when a human decides it should.
"""
from __future__ import annotations

import argparse
import copy
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hyp04_supply_chain_hedge import anchor_calendar as acal
from hyp04_supply_chain_hedge import anchor_shock as ashock
from hyp04_supply_chain_hedge import closes_requirements as creq
from hyp04_supply_chain_hedge import constants as K
from hyp04_supply_chain_hedge import earnings_events as ee
from hyp04_supply_chain_hedge import peer_returns as pret
from hyp04_supply_chain_hedge import target as tgt
from hyp04_supply_chain_hedge.make_registry_v1_4 import (
    find_availability_contradictions,
)
from hyp04_supply_chain_hedge.make_registry_v1_6 import (
    HYPOTHESIS_ID,
    IMMOVABLE_HYP04_FIELDS,
    LSE,
    RefusedError,
    _load,
    _sha256,
)

V1_9 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9.json"
V1_10 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json"
V1_10_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10_DRAFT.md"

AUTHORED_AT = "2026-08-31"

# The owner took both decisions on 2026-08-29, the same day the finding
# that recorded them as OPEN was written. This version was authored two
# days later. Two dates, kept separate: `authored_at_utc` is when the
# artifact was written, `decisions_taken_on` is when they were decided,
# and collapsing them would misdate a governance record in the direction
# that makes the decision look contemporaneous with its own declaration.
DECISIONS_TAKEN_ON = "2026-08-29"

FINDING = "Live Signal Engine/HYP04_ANCHOR_EVENT_CALENDAR_FINDING_2026-08-29.md"

# EMPTY, and that is the claim. Both changes add keys; neither moves an
# immovable field, so no exception is needed and the guard runs unweakened.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = ()

# v1.10 changes SPECIFICATIONS. It changes no membership.
UNIVERSE_MUST_NOT_MOVE = True


def check_preconditions(*, v1_9: Path = V1_9, v1_10: Path = V1_10) -> list[str]:
    refusals: list[str] = []
    if not v1_9.is_file():
        refusals.append(f"registry v1.9 not found at {v1_9.name}")
    if v1_10.exists():
        refusals.append(
            f"{v1_10.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really "
            "intended.")
    refusals.extend(code_disagreements())
    if not (LSE.parent / FINDING).is_file() and not Path(FINDING).is_file():
        refusals.append(
            f"the dated finding {FINDING} is not on disk. A specification "
            "change with no written basis is exactly what this project forbids.")
    return refusals


def code_disagreements() -> list[str]:
    """The repository must already implement what v1.10 is about to declare."""
    problems: list[str] = []

    # --- 1. the era-aware anchor-event rule -------------------------------
    if not hasattr(ee, "is_results_filing"):
        problems.append(
            "earnings_events has no `is_results_filing`. The era rule is not "
            "implemented, so v1.10 would declare a rule that does not exist.")
    else:
        if not ee.is_results_filing("12,7", "2004-01-22"):
            problems.append(
                "earnings_events.is_results_filing rejects Item 12 inside its "
                "own era. The renumbering is still deciding which events exist.")
        if ee.is_results_filing("12,7", "2010-01-22"):
            problems.append(
                "earnings_events.is_results_filing accepts Item 12 AFTER the "
                "renumbering. The rule is not era-aware, it is just wider.")
        if ee.is_results_filing("1.12,9.01", "2003-06-01"):
            problems.append(
                "earnings_events.is_results_filing matches '12' as a SUBSTRING "
                "of another code. Item codes must be exact tokens.")

    sig = inspect.signature(acal.derive_anchor_calendar).parameters
    p = sig.get("accept_legacy_item_12")
    if p is None or p.default is not True:
        problems.append(
            "anchor_calendar.derive_anchor_calendar does not DEFAULT to the "
            "era rule. v1.10 adopts it; a default of False would leave the "
            "registry declaring one rule while the derivation ran another.")

    # --- 2. the day-0-exclusive reference window --------------------------
    if getattr(K, "REFERENCE_WINDOW_OFFSET_SESSIONS", None) != 1:
        problems.append(
            "constants.REFERENCE_WINDOW_OFFSET_SESSIONS is not 1. The "
            "reference window still ends AT the anchor day.")
    for mod, fn in ((tgt, "raw_log_ratio_target"),
                    (creq, "session_span"),
                    (creq, "closes_per_event"),
                    (pret, "coverage_for_event")):
        if "reference_offset" not in inspect.signature(
                getattr(mod, fn)).parameters:
            problems.append(
                f"{mod.__name__}.{fn} has no `reference_offset` parameter. "
                "The window specification cannot be varied there, so the "
                "robustness variant v1.10 registers cannot be computed.")

    # COVERAGE AND THE TARGET MUST SLICE THE SAME WINDOW. If they diverged, P5
    # would certify pairs the target then returns NaN for, and the denial would
    # point at the wrong thing.
    try:
        t_off = inspect.signature(
            tgt.raw_log_ratio_target).parameters["reference_offset"].default
        c_off = inspect.signature(
            pret.coverage_for_event).parameters["reference_offset"].default
        if t_off != c_off:
            problems.append(
                f"the target's default reference_offset ({t_off}) and peer "
                f"coverage's ({c_off}) disagree. One would certify what the "
                "other refuses to compute.")
    except KeyError:
        pass

    # The emitted request must COVER BOTH specifications, or the robustness
    # variant costs a second collection round.
    if creq.session_span(100)[0] > creq.session_span(100, reference_offset=0)[0]:
        problems.append(
            "the emitted closes span does not cover the day-0-inclusive "
            "variant. A request that satisfies only the primary makes the "
            "registered robustness check uncollectable without a second round.")

    # --- 3. the return basis ----------------------------------------------
    if getattr(ashock, "RETURN_BASIS", None) != "log":
        problems.append(
            "anchor_shock.RETURN_BASIS is not 'log'. v1.10 declares the basis "
            "the shock's callers must supply; it cannot declare one the module "
            "does not name.")
    return problems


def _anchor_event_block() -> dict[str, Any]:
    block = dict(acal.rule_description())
    block["implemented_by"] = (
        "hyp04_supply_chain_hedge/earnings_events.py (the rule) and "
        "hyp04_supply_chain_hedge/anchor_calendar.py (its application to "
        "membership spans)")
    block["decided_on"] = DECISIONS_TAKEN_ON
    block["declared_on"] = AUTHORED_AT
    block["measured_before_adopted"] = (
        "The 2026-08-29 calendar artifact published BOTH totals side by side "
        "under accept_legacy_item_12=False and adopted neither. The owner took "
        "the decision afterwards. Passing False still reproduces the superseded "
        "rule exactly, so that artifact stays reproducible rather than merely "
        "archived.")
    block["effect_on_counts"] = (
        "321 candidate anchor events under the superseded rule, 342 under this "
        "one; 306 and 324 respectively once an unresolved release session is "
        "excluded. Both are CANDIDATE counts. Neither is an eligible-event "
        "count and neither moves C2.")
    block["known_limitations"] = [
        "Member-years before " + ee.ITEM_12_INTRODUCED + " carry no "
        "earnings-specific item code at all -- an earnings 8-K then bore Item 5 "
        "or Item 7, the same codes every unrelated 8-K bore. 7.62 member-years "
        "fall in that era, roughly 30 releases, and NO index-level rule can "
        "recover them. Stated under-inclusion, not a corrected one.",
        "AAPL's entire membership span predates that date, so its zero is not "
        "fixed by this rule and is not evidence it did not report.",
        "Item tagging remains a FLOOR, not a census: a filer can furnish "
        "results without tagging the results item, and at least one did "
        "(MCK 2020-02-04). Unchanged by this version.",
    ]
    return block


def _peer_target_window_block() -> dict[str, Any]:
    return {
        "specification_id": "HYP04-PEER-TARGET-WINDOW-v1",
        "implemented_by": "hyp04_supply_chain_hedge/target.py",
        "target": "log(RVar(h)) - log(RVar_ref) per (anchor event, peer, horizon)",
        "post_event_window": "[anchor_day + 1, anchor_day + h]",
        "reference_window_length_sessions": K.REFERENCE_WINDOW_TRADING_DAYS,
        "reference_window_offset_sessions": K.REFERENCE_WINDOW_OFFSET_SESSIONS,
        "reference_window": (
            "the "
            + str(K.REFERENCE_WINDOW_TRADING_DAYS)
            + " sessions ending "
            + str(K.REFERENCE_WINDOW_OFFSET_SESSIONS)
            + " session(s) BEFORE anchor_day, i.e. ending at anchor_day - 1"),
        "anchor_day_is_in_neither_window": True,
        "what_it_replaced": (
            "The reference window ended AT anchor_day, which is the session the "
            "anchor's earnings release is ATTRIBUTED to -- for a BMO release "
            "the news is out before the open, and for an AMC release the "
            "attributed session is the next day, so in both cases the peer's "
            "return on that session can already contain the transmission being "
            "measured. Standard event-study practice is that the estimation "
            "window ends before the event window, and it did not."),
        "direction_of_the_change": (
            "FAVOURABLE, and stated as such. Removing a contaminated session "
            "from the baseline LOWERS the baseline and RAISES the measured "
            "log-ratio. The superseded window was weakly conservative: it "
            "attenuated the effect it was measuring."),
        "why_this_is_legitimate_now": (
            "Because NOTHING HAS BEEN MEASURED. No shock, no peer response and "
            "no target value from production data exists for HYP-04, so there "
            "is no outcome this could have been chosen to favour. A change in "
            "the favourable direction made after any result existed would be "
            "the after-the-fact tuning this project's rules forbid. It was "
            "taken before closes were collected for exactly this reason."),
        "robustness_specification": {
            "reference_window_offset_sessions": 0,
            "description": (
                "The superseded day-0-inclusive window, REPORTED ALONGSIDE the "
                "primary and never substituted for it."),
            "reproduces_superseded_arithmetic_exactly": True,
            "how": "target.raw_log_ratio_target(..., reference_offset=0)",
        },
        "only_the_endpoint_moved": (
            "The window LENGTH is unchanged at "
            + str(K.REFERENCE_WINDOW_TRADING_DAYS)
            + " sessions. The two specifications differ in exactly one way, so "
            "the robustness comparison is not confounded by a length change as "
            "well."),
        "data_cost": (
            "One additional close per (peer, event): "
            + str(creq.closes_per_event(reference_offset=0))
            + " -> " + str(creq.closes_per_event())
            + ". The emitted request spans the WIDER window, so it satisfies "
            "the robustness variant too and no second collection round is "
            "needed."),
        "coverage_agrees_with_the_target": (
            "peer_returns.coverage_for_event slices the same window from the "
            "same constant. If it did not, P5 would certify pairs the target "
            "then returns NaN for, and the denial would point at the window "
            "instead of at the data."),
        "measurement_status": (
            "This specifies a computation. NO target value has been computed "
            "from production data."),
    }


def build_v1_10(*, v1_9: Path = V1_9, authored_at: Optional[str] = None,
                ) -> tuple[dict, list[str]]:
    """Return (v1.10 document, changes). Pure; writes nothing."""
    problems = code_disagreements()
    if problems:
        raise RefusedError(
            "the repository does not implement what v1.10 would declare: "
            + "; ".join(problems))

    src = _load(v1_9)
    doc = copy.deepcopy(src)
    changes: list[str] = []
    date = authored_at or AUTHORED_AT

    doc["registry_version"] = "1.10"
    doc["authored_at_utc"] = date
    doc["decisions_taken_on"] = DECISIONS_TAKEN_ON
    doc["decisions_taken_on_note"] = (
        "The owner took both specification decisions on "
        + DECISIONS_TAKEN_ON + ", the same day the finding that recorded them "
        "as OPEN was written. This version was authored on " + date + ". The "
        "two dates are kept separate because collapsing them would make a "
        "decision look contemporaneous with its own declaration.")
    doc["supersedes"] = v1_9.name
    doc["supersedes_sha256"] = _sha256(v1_9)
    doc["companion_markdown"] = f"{LSE.name}/{V1_10_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_9.name} is NOT edited in place. It remains on disk unchanged, "
        "byte-for-byte, including the day-0-inclusive reference window this "
        "version replaces and which it records as a known limitation. This "
        "version changes two SPECIFICATIONS. It changes no membership, no "
        "threshold, no measurement result, and opens no display-gate "
        "condition.")
    doc["change_summary"] = (
        "Settles the two specifications v1.9 left open. (1) The 8-K results "
        "item is selected by the SEC numbering IN FORCE ON THE REPORT DATE, so "
        "Item 12 counts between 2003-03-28 and 2004-08-22: selecting on Item "
        "2.02 alone let SEC Release 33-8400's 2004 renumbering decide which "
        "anchor events exist, which is the same defect as letting a filer's "
        "print format decide membership. NKE had ZERO candidate events inside "
        "its membership span and has six. (2) The peer target's reference "
        "window now ends at anchor_day - 1 rather than AT anchor_day, so the "
        "session the anchor's release is attributed to is in NEITHER window; "
        "the day-0-inclusive window is registered as the robustness variant and "
        "reproduces the superseded arithmetic exactly. That second change moves "
        "results in the FAVOURABLE direction and is legitimate only because "
        "NOTHING HAS BEEN MEASURED -- it was taken before closes were collected "
        "for exactly that reason. Also states the shock's RETURN BASIS as log, "
        "a gap found while planning the collection. BOTH changes are new keys: "
        "no immovable field moves, so this version needs no exception and the "
        "guard runs unweakened. Membership is byte-identical to v1.9. NO "
        "hypothesis is reclassified, promoted, demoted or re-thresholded; "
        "minimum_eligible_events stays 193 anchor events. HYP-04's status "
        "remains PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED, every "
        "eligible-event counter remains zero, and the gate stays CLOSED with "
        "C4 MET and exactly four denials.")
    changes.append(f"registry_version 1.9 -> 1.10, authored_at_utc {date}")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in v1.9")
    old_entry = next(h for h in src["hypotheses"]
                     if h["hypothesis_id"] == HYPOTHESIS_ID)

    entry["anchor_event_rule"] = _anchor_event_block()
    changes.append(f"{HYPOTHESIS_ID}.anchor_event_rule: declared "
                   f"({ee.ANCHOR_EVENT_RULE_ID})")

    entry["peer_target_window"] = _peer_target_window_block()
    changes.append(f"{HYPOTHESIS_ID}.peer_target_window: declared "
                   "(HYP04-PEER-TARGET-WINDOW-v1)")

    shock = dict(entry.get("anchor_shock") or {})
    for k in ("return_basis", "return_basis_definition", "return_basis_note"):
        shock[k] = ashock.rule_description()[k]
    entry["anchor_shock"] = shock
    changes.append(f"{HYPOTHESIS_ID}.anchor_shock: adds return_basis "
                   f"({ashock.RETURN_BASIS})")

    doc["findings_responded_to"] = {
        "documents": list(
            (src.get("findings_responded_to") or {}).get("documents", []))
        + [FINDING],
        "note": ("Dated findings recorded BEFORE this version and left on disk "
                 "unedited. The last measured both specifications this version "
                 "settles, and recorded them as open rather than adopting "
                 "either."),
    }
    changes.append("findings_responded_to: adds the 2026-08-29 calendar finding")

    # --- NO immovable field may move. No exception is claimed. ------------
    if SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.10 claims an immovable-field exception. It adds KEYS; if a "
            "later edit needs to move a field it must be a different version "
            "that says so in its own source.")
    for f in IMMOVABLE_HYP04_FIELDS:
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{f} changed. v1.10 moves no immovable field.")
    changes.append("guard: every immovable field is byte-identical to v1.9")

    # --- membership is frozen ---------------------------------------------
    if UNIVERSE_MUST_NOT_MOVE and entry.get("anchor_universe") != old_entry.get(
            "anchor_universe"):
        raise RefusedError(
            "the anchor_universe block changed. v1.10 changes SPECIFICATIONS; "
            "membership is v1.9's and must survive byte-identical.")
    changes.append("guard: the anchor universe is byte-identical to v1.9")

    # --- derive-never-assert on both declared rules ------------------------
    again = dict(acal.rule_description())
    written = {k: entry["anchor_event_rule"][k] for k in again}
    if written != again:
        raise RefusedError(
            "the declared anchor-event rule does not re-derive from "
            "anchor_calendar.rule_description()")
    changes.append("guard: the anchor-event rule re-derived independently")

    w = entry["peer_target_window"]
    if (w["reference_window_length_sessions"] != K.REFERENCE_WINDOW_TRADING_DAYS
            or w["reference_window_offset_sessions"]
            != K.REFERENCE_WINDOW_OFFSET_SESSIONS):
        raise RefusedError(
            "the declared peer-target window does not re-derive from constants")
    if w["robustness_specification"]["reference_window_offset_sessions"] != 0:
        raise RefusedError(
            "the robustness variant is not the day-0-inclusive window, so the "
            "superseded specification is not registered anywhere")
    changes.append("guard: the peer-target window re-derived from constants")

    sh = entry["anchor_shock"]
    old_sh = old_entry.get("anchor_shock") or {}
    if {k: v for k, v in sh.items() if k in old_sh} != old_sh:
        raise RefusedError(
            "a field v1.9 declared on anchor_shock changed. v1.10 ADDS the "
            "return basis; it redefines nothing about the shock.")
    changes.append("guard: v1.9's anchor_shock fields are untouched")

    # --- everything the earlier versions froze, still frozen ---------------
    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(f"hypothesis list changed: {ids_old} -> {ids_new}")
    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.10 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Adopting an item rule and moving a "
            "reference window creates no eligible anchor event -- if this "
            "moved, a specification has been mistaken for a measurement.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed")
    if doc.get("peer_price_data_policy") != src.get("peer_price_data_policy"):
        raise RefusedError(
            "peer_price_data_policy changed. The anchor-side source decision "
            "does NOT amend it: that policy governs the PEER side, and it "
            "still requires a survivorship-bias-free peer source that has not "
            "been selected.")
    if entry.get("unresolved_analysis_decisions") != old_entry.get(
            "unresolved_analysis_decisions"):
        raise RefusedError(
            "unresolved_analysis_decisions changed. Both changes here are "
            "measurement SPECIFICATIONS, recorded at registry level exactly as "
            "v1.9 recorded the shock. Adding an unresolved decision would flip "
            "C4 to NOT MET and produce a fifth denial for a decision that is "
            "not pending.")

    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.10 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes")

    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.10 from v1.9, settling "
                    "the anchor-event item rule and the peer target window.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.10 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes = build_v1_10(authored_at=a.authored_at)
    print("Changes v1.9 -> v1.10:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_10.name}.")
        return 0

    before = _sha256(V1_9)
    V1_10.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    if _sha256(V1_9) != before:
        raise RefusedError("v1.9 changed on disk during generation")

    print(f"\nWrote {V1_10.name}")
    print(f"v1.9 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
