#!/usr/bin/env python3
"""Generate hypothesis-registry v1.9 from v1.8 -- HYP-04.

=== THIS VERSION IS A DIFFERENT KIND FROM v1.6, v1.7 AND v1.8 ===

Those three corrected the CORPUS READING. Each froze the hypothesis
specification and checked it byte-identical, because a corpus fix must never
quietly change what the hypothesis asks. That guard did its job and stays.

v1.9 changes the SPECIFICATION, deliberately and narrowly: it states HYP-04's
anchor-side requirement in HYP-04's own terms instead of inheriting HYP-01's.

Exactly ONE field of `IMMOVABLE_HYP04_FIELDS` may move here --
`required_eligibility_class` -- and it is named in
`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` rather than the guard being
loosened. Everything else in that tuple is still checked. A version that needed
to move a second field would have to say so in its own source.

=== WHAT WAS WRONG ===

HYP-04's estimator regresses peer abnormal volatility on a per-event scalar
`shock` -- its only anchor-side quantity. That scalar had NO production
definition: it existed only in `fixtures.py` as `abs(rng.normal(0, 1))`, the
model plan offered "confirmed |excess return| or GST z-score" without choosing,
and none of the four decisions in the dated analysis lock was this one.

Meanwhile `required_eligibility_class` inherited
`core_attention_vs_equity_response`, whose strict gate demands gst_zscore,
wiki_zscore, panel_implied_volatility, realized_volatility, previous_close and
volume, each with a successful per-leg source status, plus a pre-event
snapshot. Certifying one HYP-04 anchor event therefore required TWO ATTENTION
SERIES AND AN OPTION CHAIN -- and the choice of shock was being made by side
effect, through a class nobody had examined against HYP-04's own question.

`pair_eligibility`'s P1 showed the contradiction in one place: it enforced the
attention class while its denial message justified itself as "the peer
measurement is only defined relative to a usable anchor earnings shock".

=== THE DECISION ===

The repo owner determined 2026-08-29 that HYP-04 tests INFORMATION TRANSMISSION
along supply-chain links -- how an anchor's earnings news dictates volatility
and a range of price changes for stocks across the supply chain. See
`HYP04_ANCHOR_SHOCK_DEFINITION_MEMO_2026-08-29.md` and its same-day amendment,
both written and committed BEFORE this version.

So the anchor-side requirement becomes: the earnings-day EXCESS RETURN is well
measured. `hyp04_supply_chain_hedge/anchor_shock.py` is that rule, fail-closed,
in HYP-04's own package -- the same precedent `pair_eligibility` set for the
peer side. Nothing under `gst_market_response/` is touched.

=== THE CODE MUST ALREADY AGREE ===

This generator REFUSES to write while `pair_eligibility` still enforces the
attention class. v1.7's docstring records what happens otherwise: the
repository holds code implementing one thing and an authoritative registry
describing another, with no test able to see it. Here the code was changed
first and the registry follows, and the guard makes that ordering compulsory.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_9 --write

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

from hyp04_supply_chain_hedge import anchor_shock as ashock
from hyp04_supply_chain_hedge import pair_eligibility as peval
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

V1_8 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.8.json"
V1_9 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9.json"
V1_9_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9_DRAFT.md"

AUTHORED_AT = "2026-08-29"

MEMO = "Live Signal Engine/HYP04_ANCHOR_SHOCK_DEFINITION_MEMO_2026-08-29.md"

# The ONLY immovable field this version may move, named rather than skipped.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE = ("required_eligibility_class",)

# v1.9 changes the anchor-side SHOCK. It changes no membership, so the whole
# universe block must survive byte-identical -- the mirror image of v1.8, which
# moved membership and froze the rule.
UNIVERSE_MUST_NOT_MOVE = True


def check_preconditions(*, v1_8: Path = V1_8, v1_9: Path = V1_9) -> list[str]:
    refusals: list[str] = []
    if not v1_8.is_file():
        refusals.append(f"registry v1.8 not found at {v1_8.name}")
    if v1_9.exists():
        refusals.append(
            f"{v1_9.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really "
            "intended.")
    refusals.extend(code_disagreements())
    if not (LSE.parent / MEMO).is_file() and not Path(MEMO).is_file():
        refusals.append(
            f"the dated decision memo {MEMO} is not on disk. A specification "
            "change with no written basis is exactly what this project forbids.")
    return refusals


def code_disagreements() -> list[str]:
    """The repository must already implement what v1.9 is about to declare."""
    problems: list[str] = []
    params = inspect.signature(peval.evaluate_pair).parameters
    if "anchor_shock" not in params:
        problems.append(
            "pair_eligibility.evaluate_pair has no `anchor_shock` parameter. "
            "The code still takes the anchor side as an attention eligibility, "
            "so v1.9 would describe a repository that does not exist.")
    if "anchor_eligibility" in params:
        problems.append(
            "pair_eligibility.evaluate_pair still takes `anchor_eligibility`.")
    src = Path(peval.__file__).read_text(encoding="utf-8")
    if "from gst_market_response" in src:
        problems.append(
            "pair_eligibility still imports gst_market_response. HYP-04's "
            "anchor-side requirement is its own; the import means P1 can still "
            "be gated on HYP-01's per-event protocol.")
    if ashock.BENCHMARK_BETA != 1.0 or ashock.rule_description()["beta_is_estimated"]:
        problems.append(
            "the anchor-shock rule reports an estimated beta. An estimation "
            "window chosen after seeing results is the tuning this project "
            "forbids, and a full-sample fit is look-ahead.")
    return problems


def _anchor_shock_block() -> dict[str, Any]:
    """Declared from the rule, never paraphrased."""
    block = dict(ashock.rule_description())
    block["decided_by"] = (
        "Repo owner, 2026-08-29: HYP-04 tests INFORMATION TRANSMISSION along "
        "supply-chain links -- how an anchor's earnings news dictates "
        "volatility and a range of price changes for stocks in industries "
        "across the supply chain. It is a sibling of HYP-01 in the sense of "
        "the same research programme approached from a DIFFERENT ANGLE, and "
        "not in the sense of testing the same mechanism.")
    block["decision_basis"] = MEMO
    block["what_it_replaced"] = (
        "The anchor side previously inherited HYP-01's "
        "core_attention_vs_equity_response, whose strict gate requires "
        "gst_zscore, wiki_zscore, panel_implied_volatility, "
        "realized_volatility, previous_close and volume with successful "
        "per-leg statuses, plus a pre-event snapshot. Certifying ONE HYP-04 "
        "anchor event therefore required two attention series and an option "
        "chain. None of that bears on whether an earnings-day excess return is "
        "well measured.")
    block["no_fourth_class_was_created"] = (
        "There is no class in gst_market_response.completeness.HYPOTHESIS_CLASSES "
        "for this requirement and none was added. The rule lives in HYP-04's "
        "own package, exactly as peer eligibility does, and HYP-01's "
        "confirmatory infrastructure is untouched.")
    block["beta_is_not_estimated_because"] = (
        "An estimated beta needs an estimation window, and choosing that window "
        "after seeing how results move is after-the-fact tuning. A beta fitted "
        "on the full sample uses post-event data to define a pre-event "
        "expectation -- look-ahead by construction, the same defect class as "
        "the reconstructed GST z-score history this project's central finding "
        "is about. beta = 1 is chosen for being ASSUMPTION-FREE, and is a "
        "STATED LIMITATION rather than a claim that the market model is right.")
    block["known_limitations"] = [
        "beta = 1 against a broad-market proxy is not a risk model. A peer "
        "whose anchor has high market beta will carry part of the market move "
        "in its 'excess' return. Stated, not corrected.",
        "The shock is a MAGNITUDE. Direction is discarded, which is correct for "
        "a volatility-transmission question and would be wrong for a "
        "signed-return one.",
        "OPEN, RECORDED 2026-08-29, NOT RESOLVED HERE: the peer target's "
        "reference window is peer_returns[ref_start:anchor_day + 1] -- "
        "INCLUSIVE of day 0. If transmission is partly same-day, part of the "
        "response sits in the baseline it is measured against. This is true "
        "however the shock is defined and needs its own decision and its own "
        "robustness check against a window ending at anchor_day - 1.",
    ]
    return block


def build_v1_9(*, v1_8: Path = V1_8, authored_at: Optional[str] = None,
               ) -> tuple[dict, list[str]]:
    """Return (v1.9 document, changes). Pure; writes nothing."""
    problems = code_disagreements()
    if problems:
        raise RefusedError(
            "the repository does not implement what v1.9 would declare: "
            + "; ".join(problems))

    src = _load(v1_8)
    doc = copy.deepcopy(src)
    changes: list[str] = []
    date = authored_at or AUTHORED_AT

    doc["registry_version"] = "1.9"
    doc["authored_at_utc"] = date
    doc["supersedes"] = v1_8.name
    doc["supersedes_sha256"] = _sha256(v1_8)
    doc["companion_markdown"] = f"{LSE.name}/{V1_9_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_8.name} is NOT edited in place. It remains on disk unchanged, "
        "byte-for-byte, including the inherited eligibility class this version "
        "replaces. This version changes the anchor-side SPECIFICATION. It "
        "changes no membership, no threshold, no measurement result, and opens "
        "no display-gate condition.")
    doc["change_summary"] = (
        "States HYP-04's ANCHOR-SIDE requirement in HYP-04's own terms. The "
        "estimator's only anchor-side quantity, `shock`, had no production "
        "definition: it existed solely in fixtures.py as abs(rng.normal(0,1)), "
        "the model plan offered '|excess return| or GST z-score' without "
        "choosing, and no dated decision covered it. Meanwhile "
        "required_eligibility_class inherited HYP-01's "
        "core_attention_vs_equity_response, whose strict gate requires two "
        "attention series and an option chain per anchor event -- so the "
        "choice of shock was being made by SIDE EFFECT. The repo owner "
        "determined 2026-08-29 that HYP-04 tests information transmission "
        "along supply-chain links, so the shock is the anchor's earnings-day "
        "|excess return| against a benchmark whose coefficient is FIXED, not "
        "estimated. The rule lives in HYP-04's own package; no fourth "
        "hypothesis class was created and gst_market_response is untouched. "
        "Membership is unchanged and the universe block is byte-identical to "
        "v1.8. NO hypothesis is reclassified, promoted, demoted or "
        "re-thresholded; minimum_eligible_events stays 193 anchor events. "
        "HYP-04's status remains PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED, "
        "every eligible-event counter remains zero, and the gate stays CLOSED "
        "with C4 MET. NOTHING HAS BEEN MEASURED: a module that can compute a "
        "shock is not a computed shock.")
    changes.append(f"registry_version 1.8 -> 1.9, authored_at_utc {date}")

    entry = next((h for h in doc.get("hypotheses", [])
                  if h.get("hypothesis_id") == HYPOTHESIS_ID), None)
    if entry is None:
        raise RefusedError(f"{HYPOTHESIS_ID} is not present in v1.8")
    old_entry = next(h for h in src["hypotheses"]
                     if h["hypothesis_id"] == HYPOTHESIS_ID)

    entry["anchor_shock"] = _anchor_shock_block()
    changes.append(f"{HYPOTHESIS_ID}.anchor_shock: declared "
                   f"({ashock.ANCHOR_SHOCK_RULE_ID})")

    entry["required_eligibility_class"] = ashock.ANCHOR_SHOCK_RULE_ID
    entry["required_eligibility_class_note"] = (
        "THIS NO LONGER NAMES A gst_market_response CLASS, and that is the "
        "point of v1.9. Until 2026-08-29 it named HYP-01's "
        "core_attention_vs_equity_response, which requires two attention "
        "series and an option chain per anchor event -- requirements that were "
        "never examined against HYP-04's own question and which decided the "
        "anchor-side shock by side effect. It now names HYP-04's own rule, "
        f"{ashock.ANCHOR_SHOCK_RULE_ID}, defined in "
        "hyp04_supply_chain_hedge/anchor_shock.py: the anchor's earnings-day "
        "excess return must be well measured, fail-closed on every unknown. "
        "The PEER side still has no eligibility class anywhere and still lives "
        "in HYP-04's own package; no fourth class was created for either side.")
    changes.append(
        f"{HYPOTHESIS_ID}.required_eligibility_class: "
        f"{old_entry.get('required_eligibility_class')!r} -> "
        f"{entry['required_eligibility_class']!r}")

    doc["findings_responded_to"] = {
        "documents": list(
            (src.get("findings_responded_to") or {}).get("documents", []))
        + [MEMO],
        "note": ("Dated findings recorded BEFORE this version and left on disk "
                 "unedited. The last is the reason this version exists, and it "
                 "carries a same-day amendment recording the owner's decision."),
    }
    changes.append("findings_responded_to: adds the 2026-08-29 shock memo")

    # --- the ONE permitted move, and everything else still checked --------
    for f in IMMOVABLE_HYP04_FIELDS:
        if f in SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
            continue
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{f} changed. v1.9 may move exactly "
                f"{SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE} and nothing "
                "else; a version needing a second field must say so in its "
                "own source.")
    if entry.get("required_eligibility_class") == old_entry.get(
            "required_eligibility_class"):
        raise RefusedError(
            "required_eligibility_class did not move. A specification version "
            "that changes no specification is noise in the chain.")
    changes.append("guard: exactly one immovable field moved, by name")

    # --- membership is frozen: this version is not about the universe -----
    if UNIVERSE_MUST_NOT_MOVE and entry.get("anchor_universe") != old_entry.get(
            "anchor_universe"):
        raise RefusedError(
            "the anchor_universe block changed. v1.9 changes the anchor-side "
            "SHOCK; membership is v1.8's and must survive byte-identical.")
    changes.append("guard: the anchor universe is byte-identical to v1.8")

    # --- derive-never-assert on the declared rule -------------------------
    again = dict(ashock.rule_description())
    written = {k: entry["anchor_shock"][k] for k in again}
    if written != again:
        raise RefusedError(
            "the declared anchor-shock rule does not re-derive from "
            "anchor_shock.rule_description()")
    changes.append("guard: the shock rule re-derived independently")

    # --- everything the corpus versions froze, still frozen ---------------
    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(f"hypothesis list changed: {ids_old} -> {ids_new}")
    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.9 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Defining the anchor-side shock "
            "creates no eligible anchor event -- if this moved, a definition "
            "has been mistaken for a capture path.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed")
    if doc.get("peer_price_data_policy") != src.get("peer_price_data_policy"):
        raise RefusedError("peer_price_data_policy changed")
    if entry.get("unresolved_analysis_decisions") != old_entry.get(
            "unresolved_analysis_decisions"):
        raise RefusedError(
            "unresolved_analysis_decisions changed. The shock definition is a "
            "HYPOTHESIS SPECIFICATION, recorded at registry level like its "
            "closest sibling required_eligibility_class -- not an analysis "
            "decision. Marking it RESOLVED would have to cite a lock that "
            "predates it, and marking it PENDING would flip C4 for a decision "
            "that is not pending.")

    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.9 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes")

    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.9 from v1.8, stating "
                    "HYP-04's anchor-side requirement in its own terms.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.9 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes = build_v1_9(authored_at=a.authored_at)
    print("Changes v1.8 -> v1.9:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_9.name}.")
        return 0

    before = _sha256(V1_8)
    V1_9.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if _sha256(V1_8) != before:
        raise RefusedError("v1.8 changed on disk during generation")

    print(f"\nWrote {V1_9.name}")
    print(f"v1.8 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
