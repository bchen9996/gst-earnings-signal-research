#!/usr/bin/env python3
"""Generate hypothesis-registry v1.11 from v1.10. PEER PRICE SOURCE ONLY.

=== WHAT v1.11 SETTLES ===

One thing: `peer_price_data_policy` has said since v1.5 that a survivors-only
peer price source is permitted "only if the restriction and its bias are stated
in the registry version that does it". The restriction has now been taken --
13,056 sessions collected for six peers from Yahoo, which lists companies that
trade today -- so this is the version that states it, and `no_option_taken_here`
becomes false.

=== WHY IT COULD NOT HAVE COME EARLIER, AND MUST NOT COME LATER ===

Not earlier: `code_disagreements()` refuses to declare a source that has
produced nothing, so the collection had to happen first. Not later: the policy
bars a survivors-only restriction from reaching a MEASUREMENT unstated, and the
next step wires these prices into `target.py`. This version sits in the only
window where it is both possible and honest.

=== SCOPE IS DELIBERATELY ONE FIELD ===

v1.11 amends the policy and nothing else. In particular it does NOT move
`status` to ACTIVE_COLLECTING. That vocabulary requires a production capture
path with `data_captured` true, and while closes now exist there is still no
module that assembles them into the panel the estimator consumes -- so claiming
it would be declaring a path the repository does not have. C1 is a later
version's to move, once that assembler exists.

The practical consequence is that the gate is untouched: CLOSED, C4 MET,
exactly four denials, eligible event count zero. The nineteen suites that call
`current_decision()` keep passing unchanged, which is the point of keeping the
scope this narrow.

=== NO IMMOVABLE-FIELD EXCEPTION IS CLAIMED ===

`SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE` is EMPTY, and that is a real
claim rather than an oversight. `peer_price_data_policy` is a TOP-LEVEL field,
not one of `IMMOVABLE_HYP04_FIELDS`, which are entry fields. So the entry-level
guard runs unweakened over every field it covers while the top-level policy is
amended. v1.6 through v1.10 each carried their own explicit refusal against
touching the policy; v1.11 is the version that omits it, on purpose, and
replaces it with a narrower guard: the six fields the policy already had must
survive verbatim except `no_option_taken_here`, and only additive keys appear.

Run:  python -m hyp04_supply_chain_hedge.make_registry_v1_11 --write

Named off the `test_*` pattern deliberately: this writes a governance artifact
and must only ever run when a human decides it should.
"""
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Optional

from hyp04_supply_chain_hedge import peer_returns as pret
from hyp04_supply_chain_hedge import run_peer_closes_fetch as fetch
from hyp04_supply_chain_hedge.artifacts import newest_in
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

V1_10 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json"
V1_11 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11.json"
V1_11_MARKDOWN = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11_DRAFT.md"

AUTHORED_AT = "2026-09-02"
DECISIONS_TAKEN_ON = "2026-09-02"

FINDING = "Live Signal Engine/HYP04_PEER_PRICE_SOURCE_FINDING_2026-09-02.md"

CLOSES_DIR = LSE / "HYP04_PEER_CLOSES_REQUEST"

#: What was collected. Asserted against the files by `code_disagreements`
#: rather than trusted, because a registry that states a collection size the
#: repository cannot reproduce is worse than one that states nothing.
EXPECTED_PEERS = ("AAPL", "BB", "CSCO", "CVS", "HPQ", "MSFT")
EXPECTED_ROWS = 13056

#: EMPTY, and that is the claim. peer_price_data_policy is a TOP-LEVEL field,
#: not one of IMMOVABLE_HYP04_FIELDS (which are entry fields), so amending it
#: needs no entry-level exception and the guard runs unweakened.
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE: tuple[str, ...] = ()

#: v1.11 records a data source. It changes no membership.
UNIVERSE_MUST_NOT_MOVE = True

#: The six fields v1.5 wrote. Every one must survive verbatim except
#: `no_option_taken_here`, which is precisely what this version flips.
POLICY_FIELDS_THAT_MUST_SURVIVE = (
    "statement", "why", "measured_instance", "consequence_for_this_registry",
    "what_is_still_required",
)


def _closes_files() -> list[Path]:
    return sorted(CLOSES_DIR.glob("*_closes_REQUEST.csv"))


def _row_count(p: Path) -> int:
    with io.open(p, encoding="utf-8", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def code_disagreements() -> list[str]:
    """The repository must already implement what v1.11 is about to declare."""
    problems: list[str] = []

    # --- 1. the closes actually exist, and are the size claimed ------------
    files = _closes_files()
    if not files:
        problems.append(
            f"no peer closes under {CLOSES_DIR}. v1.11 declares a collected "
            "price source; it cannot declare one that produced no files.")
        return problems

    found = sorted(p.name.split("_")[0].upper() for p in files)
    if found != sorted(EXPECTED_PEERS):
        problems.append(
            f"collected peers {found} do not match the declared "
            f"{sorted(EXPECTED_PEERS)}.")

    total = sum(_row_count(p) for p in files)
    if total != EXPECTED_ROWS:
        problems.append(
            f"the collected closes hold {total} rows; v1.11 declares "
            f"{EXPECTED_ROWS}. A registry may not state a collection size the "
            "files do not have.")

    # --- 2. every row is filled, and every panel loads clean ---------------
    # A blank close is not a small defect here: peer_returns nulls the return
    # on that session AND the next, so an unfilled request silently shortens
    # two windows rather than one.
    from datetime import date

    from hyp04_supply_chain_hedge import sessions as S
    try:
        sess = S.xnys_sessions(date(1995, 1, 3), date(2026, 9, 2))
    except Exception as exc:                      # noqa: BLE001 -- reported
        problems.append(f"cannot build the session index: {exc}")
        return problems

    for p in files:
        try:
            panel = pret.load_panel(p, sessions=sess)
        except Exception as exc:                  # noqa: BLE001 -- reported
            problems.append(f"{p.name} does not load: {exc}")
            continue
        prov = panel.provenance
        if not prov.loads_clean or prov.rows_rejected or not prov.usable:
            problems.append(
                f"{p.name} does not load clean: rows_rejected="
                f"{prov.rows_rejected} loads_clean={prov.loads_clean} "
                f"usable={prov.usable}")

    # --- 3. the declared adjustment basis is the module's own constant -----
    # Declared from the code rather than retyped, so the registry cannot drift
    # from the fetcher that produced the data.
    if getattr(fetch, "ADJUST_SPLIT_AND_DIVIDEND", None) != (
            "split_and_dividend (yfinance auto_adjust=True)"):
        problems.append(
            "run_peer_closes_fetch.ADJUST_SPLIT_AND_DIVIDEND is not the basis "
            "v1.11 declares. The registry would name an adjustment the fetcher "
            "does not apply.")
    if not hasattr(fetch, "ADJUST_SPLIT_ONLY"):
        problems.append(
            "run_peer_closes_fetch has no ADJUST_SPLIT_ONLY. v1.11 registers "
            "the split-only series as a robustness variant; it cannot register "
            "one the fetcher has no way to produce.")

    # --- 4. the survivorship numbers come from the newest ceiling ----------
    ceiling = newest_in(LSE, "HYP04_PEER_CEILING_*.json")
    if ceiling is None:
        problems.append("no peer-ceiling artifact on disk to source the "
                        "measured bias from.")
    else:
        try:
            surv = json.loads(Path(ceiling).read_text(
                encoding="utf-8")).get("resolution_survivorship") or {}
        except (ValueError, OSError) as exc:
            problems.append(f"{Path(ceiling).name} is unreadable: {exc}")
            surv = {}
        if surv.get("incremental_events_behind_unresolvable_names") is None:
            problems.append(
                f"{Path(ceiling).name} carries no measured survivorship "
                "exposure. The policy permits this restriction only with its "
                "bias STATED, and a statement of bias needs a number.")
    return problems


def check_preconditions(*, v1_10: Path = V1_10, v1_11: Path = V1_11,
                        ) -> list[str]:
    refusals: list[str] = []
    if not v1_10.is_file():
        refusals.append(f"registry v1.10 not found at {v1_10.name}")
    if v1_11.exists():
        refusals.append(
            f"{v1_11.name} already exists. Refusing to overwrite a governance "
            "artifact -- delete it deliberately first if that is really "
            "intended.")
    refusals.extend(code_disagreements())
    if not Path(FINDING).is_file():
        refusals.append(
            f"the dated finding {FINDING} is not on disk. A source decision "
            "with no written basis is exactly what this project forbids.")
    return refusals


def _survivorship() -> dict[str, Any]:
    ceiling = newest_in(LSE, "HYP04_PEER_CEILING_*.json")
    d = json.loads(Path(ceiling).read_text(encoding="utf-8"))
    return d.get("resolution_survivorship") or {}


def _policy_block(src_policy: dict[str, Any]) -> dict[str, Any]:
    """v1.5's policy, preserved, plus what taking its option requires."""
    surv = _survivorship()
    pol = copy.deepcopy(src_policy)

    pol["no_option_taken_here"] = False
    pol["option_taken_on"] = DECISIONS_TAKEN_ON
    pol["option_taken_in"] = "registry v1.11"
    pol["written_basis"] = FINDING

    pol["source"] = (
        "Yahoo, via yfinance, through the operator-fed fetcher in "
        "run_peer_closes_fetch.py. yfinance is deliberately NOT in "
        "requirements-hyp04.txt and is imported lazily, so a CI path that "
        "reached a live provider would fail at import rather than fetch.")
    pol["adjustment_basis"] = fetch.ADJUST_SPLIT_AND_DIVIDEND
    pol["adjustment_basis_why"] = (
        "Splits MUST be adjusted: an unadjusted 2-for-1 prints roughly -69% on "
        "a quiet day, and the target's RVar is a sum of squares, so a single "
        "such day can dominate a 41-session window. The DIVIDEND half is a "
        "genuine judgement call rather than a correctness requirement -- the "
        "two series are different and the difference is not negligible for a "
        "variance measure over a window containing an ex-dividend date. It is "
        "registered here because it changes the target, and because the "
        "fetcher has warned on every run that the choice was registered "
        "nowhere.")
    pol["adjustment_basis_matches_anchor_side"] = (
        "The anchor closes were collected split and dividend adjusted by the "
        "owner's decision of 2026-08-31. Using a different basis on the peer "
        "side would put the two legs of a transmission measurement on "
        "different price definitions.")

    pol["robustness_variant"] = {
        "adjustment_basis": fetch.ADJUST_SPLIT_ONLY,
        "status": "DECLARED, NOT COLLECTED",
        "derivable_from_the_primary": False,
        "why_this_differs_from_the_window_variant": (
            "v1.10's day-0-inclusive reference window costs no second "
            "collection, because closes_requirements.session_span deliberately "
            "emits the WIDER span and the variant is a slice of data already "
            "held. A split-only price series is not a slice of anything: it is "
            "a DIFFERENT SERIES, and it cannot be derived from the "
            "dividend-adjusted one. Registering it without saying so would put "
            "a robustness check in this registry that nobody can run."),
        "what_running_it_requires": (
            "Its own authorised fetch of the same "
            + str(EXPECTED_ROWS)
            + " sessions with auto_adjust=False (run_peer_closes_fetch "
            "--no-dividend-adjust)."),
    }

    pol["collected"] = {
        "peers": list(EXPECTED_PEERS),
        "sessions": EXPECTED_ROWS,
        "rows_missing": 0,
        "rows_rejected": 0,
        "pairs_covered": 313,
        "pairs_short": 1,
        "anchor_events_with_a_covered_peer": 215,
        "registered_floor": 193,
        "the_one_shortfall": (
            "CVS on MCK-2026-08-05, whose 20-session horizon runs past the "
            "collection date. A RIGHT-EDGE TRUNCATION -- a future-dated event, "
            "not a data gap -- reported as truncated rather than clipped, and "
            "collectable once those sessions trade."),
        "this_is_availability_not_eligibility": (
            "215 is a count of anchor events carrying a peer with sufficient "
            "price history. It is not an eligible-event count, it does not "
            "move C2, and no pair has passed pair_eligibility."),
    }

    pol["restriction_taken"] = "survivors_only"
    pol["measured_bias"] = {
        "queue_candidates": surv.get("candidates"),
        "resolved_to_a_ticker": surv.get("resolved"),
        "unresolvable": surv.get("unresolved"),
        "unresolvable_by_reason": surv.get("unresolved_by_reason"),
        "incremental_anchor_events_behind_unresolvable_names":
            surv.get("incremental_events_behind_unresolvable_names"),
        "named_among_the_unreachable": [
            "Dell", "Ingram Micro", "Tech Data", "Foot Locker", "Rite Aid"],
        "sourced_from": Path(newest_in(LSE, "HYP04_PEER_CEILING_*.json")).name,
    }
    pol["why_it_biases_toward_the_hypothesis"] = (
        "The peers most likely to have disappeared are those acquired or taken "
        "private, and acquisition is frequently CAUSED by the commercial "
        "relationship under study. The unreachable counterparties are "
        "therefore NOT missing at random with respect to HYP-04. Stated in the "
        "direction that is inconvenient, because that is the direction it "
        "runs.")
    pol["bias_does_not_touch_the_current_sample"] = (
        "All seven curated peers trade today, so the survivors-only "
        "restriction costs the present 215 anchor events nothing. It bounds "
        "FUTURE curation. The two facts are separate and neither excuses the "
        "other: a restriction that happens to be harmless on today's sample is "
        "still a restriction on what tomorrow's can contain.")
    pol["what_is_still_required_now"] = (
        "A survivorship-bias-free source remains the standing requirement for "
        "removing this bias rather than stating it. v1.11 takes the option the "
        "policy always permitted; it does not retire the preference.")
    return pol


def build_v1_11(*, v1_10: Path = V1_10, authored_at: Optional[str] = None,
                ) -> tuple[dict, list[str]]:
    """Return (v1.11 document, changes). Pure; writes nothing."""
    problems = code_disagreements()
    if problems:
        raise RefusedError(
            "the repository does not implement what v1.11 would declare: "
            + "; ".join(problems))

    src = _load(v1_10)
    doc = copy.deepcopy(src)
    changes: list[str] = []
    date = authored_at or AUTHORED_AT

    doc["registry_version"] = "1.11"
    doc["authored_at_utc"] = date
    doc["decisions_taken_on"] = DECISIONS_TAKEN_ON
    doc["supersedes"] = v1_10.name
    doc["supersedes_sha256"] = _sha256(v1_10)
    doc["companion_markdown"] = f"{LSE.name}/{V1_11_MARKDOWN.name}"
    doc["supersession_rule"] = (
        f"{v1_10.name} is NOT edited in place. It remains on disk unchanged, "
        "byte for byte, and this version supersedes it. The chain of "
        "supersedes_sha256 values is the only thing that makes 'superseded, "
        "not edited' a checkable claim rather than a promise.")
    doc["change_summary"] = (
        "Records the peer price source, its adjustment basis and the "
        "survivorship bias the source imports. peer_price_data_policy has "
        "permitted a survivors-only restriction since v1.5 'only if the "
        "restriction and its bias are stated in the registry version that does "
        "it'; the restriction has been taken and this version states it. "
        "Nothing else moves. No status changes, no threshold changes, no "
        "result exists, and the display gate stays CLOSED with four denials.")
    changes.append("version metadata, supersession and the v1.10 hash pin")

    src_policy = src.get("peer_price_data_policy") or {}
    doc["peer_price_data_policy"] = _policy_block(src_policy)
    changes.append(
        "peer_price_data_policy: no_option_taken_here false; source, "
        "adjustment basis, declared-not-collected robustness variant, "
        "collection counts and measured bias added")

    doc["findings_responded_to"] = {
        "documents": sorted(set(
            (src.get("findings_responded_to") or {}).get("documents", []))
            | {FINDING}),
        "note": ("Dated findings recorded BEFORE this version and left on disk "
                 "unedited. The last measured the collection and the bias it "
                 "imports, and adopted nothing on its own."),
    }
    changes.append("findings_responded_to: adds the 2026-09-02 price finding")

    # --- the policy's original fields survive verbatim ---------------------
    new_pol = doc["peer_price_data_policy"]
    for f in POLICY_FIELDS_THAT_MUST_SURVIVE:
        if f in src_policy and new_pol.get(f) != src_policy.get(f):
            raise RefusedError(
                f"peer_price_data_policy.{f} changed. v1.11 TAKES the option "
                "the policy already permitted; it does not rewrite the policy's "
                "reasoning, and least of all the paragraph explaining why the "
                "bias matters.")
    if new_pol.get("no_option_taken_here") is not False:
        raise RefusedError(
            "no_option_taken_here is not False. This version exists to take "
            "the option; leaving the flag set would leave the registry saying "
            "the restriction is untaken while the closes sit on disk.")
    changes.append("guard: the policy's original reasoning survives verbatim")

    # --- the measured bias must be a number, not a sentence ----------------
    mb = new_pol.get("measured_bias") or {}
    if not isinstance(mb.get(
            "incremental_anchor_events_behind_unresolvable_names"), int):
        raise RefusedError(
            "the measured bias carries no integer event count. 'Stated' means "
            "quantified: a statement of bias needs a number, and this is the "
            "number the policy has been waiting for since v1.5.")
    changes.append("guard: the measured bias is quantified")

    # --- the robustness variant must not overclaim -------------------------
    rv = new_pol.get("robustness_variant") or {}
    if rv.get("derivable_from_the_primary") is not False:
        raise RefusedError(
            "the robustness variant claims to be derivable from the primary "
            "series. It is not: a split-only series cannot be recovered from a "
            "dividend-adjusted one, and registering it as though it could "
            "would promise a check nobody can run.")
    if rv.get("status") != "DECLARED, NOT COLLECTED":
        raise RefusedError(
            "the robustness variant does not state that it is uncollected.")
    changes.append("guard: the robustness variant is declared, not overclaimed")

    # --- nothing else moves -----------------------------------------------
    entry = next(h for h in doc["hypotheses"]
                 if h.get("hypothesis_id") == HYPOTHESIS_ID)
    old_entry = next(h for h in src["hypotheses"]
                     if h.get("hypothesis_id") == HYPOTHESIS_ID)

    if SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE:
        raise RefusedError(
            "v1.11 claims an immovable-field exception. peer_price_data_policy "
            "is a TOP-LEVEL field, not an entry field, so no exception is "
            "needed and none may be claimed.")
    for f in IMMOVABLE_HYP04_FIELDS:
        if entry.get(f) != old_entry.get(f):
            raise RefusedError(
                f"{HYPOTHESIS_ID}.{f} changed. v1.11 records a data source and "
                "moves no immovable field -- in particular NOT `status`, which "
                "would need a production capture path this repository does not "
                "yet have.")
    changes.append("guard: every immovable field is byte-identical to v1.10")

    if UNIVERSE_MUST_NOT_MOVE and entry.get("anchor_universe") != old_entry.get(
            "anchor_universe"):
        raise RefusedError(
            "the anchor_universe block changed. Collecting prices creates no "
            "member and removes none.")
    changes.append("guard: the anchor universe is byte-identical to v1.10")

    ids_new = [h.get("hypothesis_id") for h in doc.get("hypotheses", [])]
    ids_old = [h.get("hypothesis_id") for h in src.get("hypotheses", [])]
    if ids_new != ids_old:
        raise RefusedError(f"hypothesis list changed: {ids_old} -> {ids_new}")
    if doc.get("results") != src.get("results"):
        raise RefusedError("results changed; v1.11 reports nothing")
    if doc.get("eligible_event_counts") != src.get("eligible_event_counts"):
        raise RefusedError(
            "eligible_event_counts changed. Collecting closes creates no "
            "ELIGIBLE anchor event -- if this moved, an availability count has "
            "been mistaken for an eligibility count, which is the single "
            "error this whole policy exists to prevent.")
    if doc.get("statistical_governance") != src.get("statistical_governance"):
        raise RefusedError("statistical_governance changed")
    if entry.get("unresolved_analysis_decisions") != old_entry.get(
            "unresolved_analysis_decisions"):
        raise RefusedError(
            "unresolved_analysis_decisions changed. Adding one would flip C4 "
            "to NOT MET and produce a fifth denial for a decision that is not "
            "pending.")
    changes.append("guard: results, counts, governance and decisions unmoved")

    contradictions = find_availability_contradictions(doc)
    if contradictions:
        raise RefusedError(
            "v1.11 would contradict its own availability field at: "
            + "; ".join(contradictions))
    changes.append("guard: v1.4's availability-contradiction check passes")

    return doc, changes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate hypothesis-registry v1.11 from v1.10, recording "
                    "the peer price source and the bias it imports.")
    ap.add_argument("--write", action="store_true",
                    help="actually write v1.11 (default is a dry run)")
    ap.add_argument("--authored-at", default=None, help="YYYY-MM-DD")
    a = ap.parse_args(argv)

    refusals = check_preconditions()
    if refusals:
        print("REFUSED -- preconditions not met:\n")
        for r in refusals:
            print(f"  * {r}")
        return 1

    doc, changes = build_v1_11(authored_at=a.authored_at)
    print("Changes v1.10 -> v1.11:\n")
    for c in changes:
        print(f"  * {c}")

    if not a.write:
        print(f"\nDRY RUN. Re-run with --write to create {V1_11.name}.")
        return 0

    before = _sha256(V1_10)
    V1_11.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    if _sha256(V1_10) != before:
        raise RefusedError("v1.10 changed on disk during generation")

    print(f"\nWrote {V1_11.name}")
    print(f"v1.10 unchanged, sha256 {before[:16]}...")
    print("\nSTILL REQUIRED -- repoint the registry the gate reads:")
    print("  * hyp04_supply_chain_hedge/display_gate.py  (REGISTRY_CURRENT)")
    print("  * hyp04_supply_chain_hedge/dashboard.py     (REGISTRY)")
    print("\nThe gate must stay CLOSED with C4 MET and exactly 4 denials: "
          "v1.11 moves no gate condition.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
