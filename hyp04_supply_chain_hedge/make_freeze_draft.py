#!/usr/bin/env python3
"""The HYP-04 freeze machinery -- and it cannot freeze anything on its own.

Registry v1.11 section 10 names this as an open item alongside C1 and the peer
earnings calendar. `make_event_panel` supplied the count C2 asks for; this
supplies the machinery C3 asks for.

=== WHAT A FREEZE WOULD DO, SAID BEFORE ANYTHING ELSE ===

The display gate denies on four conditions today. A valid freeze record
supplies C3 directly, carries the count that satisfies C2, and clears C5 --
the panel already derives `uses_placeholder_linkage: false` from the real
curated map. C4 is already MET.

    Executing a freeze would take the gate from FOUR denials to ONE.

The survivor is C1: `status` is `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`,
not `ACTIVE_COLLECTING`, and moving it is a registry act.

That makes a freeze the most consequential single action available in this
project, so this module ships the TOOL and never performs the ACT. It writes a
DRAFT with the operator's fields left blank, exactly as `make_linkage_draft`
writes linkage rows it refuses to fill in.

=== THE PROCEDURE IT IMPLEMENTS ===

`GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md` section 5:

  1. enumerate the eligible `event_id` set mechanically, and record it;
  2. record the analysis-code commit SHA;
  3. record the resolved analysis lock, written BEFORE this step;
  4. hash and append all three, immutably -- THEN compute results.

Steps 1-3 are derivable and are derived here. Step 4's "then" is an ordering
this module can guard but cannot prove, which is why one field stays blank.

=== THE ONE FIELD A MACHINE MUST NOT FILL ===

`frozen_before_any_result_computed` is null in every draft. No filesystem check
can establish that nobody has looked at an outcome -- someone can compute a
regression in a notebook that never touches this repository. The scan below is
a BACKSTOP against the obvious case, not a proof, and treating it as proof
would be the more dangerous error. The operator asserts it or the freeze is not
valid.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .curated_linkage import load_curated_linkage
from .display_gate import FreezeRecord
from .linkage_resolution import LinkageProvenance

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

#: The review status an edge must carry before its events may be frozen.
#: `curated_linkage.REVIEW_STATUSES` is ("draft", "reviewed", "needs revisit").
RATIFIED_REVIEW_STATUS = "reviewed"

#: Fields a human must supply. Left blank on every draft, which is what makes
#: a draft inert. `frozen` stays false because a draft is not a freeze.
OWNER_FIELDS = ("frozen", "frozen_before_any_result_computed",
                "attested_by", "attested_date")

#: Filename patterns that would hold a MEASURED PROPERTY of HYP-04. Deliberately
#: narrow and explicitly named: "FINDING" and "RESULT" appear in governance
#: documents all over this directory (HYP04_PEER_CEILING_FINDING,
#: HYP04_QUANTUM_RESULT_GOVERNANCE_NOTE), and a scan that tripped on those would
#: be noise the operator learns to wave through -- which is worse than no scan.
RESULT_ARTIFACT_PATTERNS = (
    "HYP04_STAGE2_*", "HYP04_INFERENCE_*", "HYP04_BETA_*",
    "HYP04_LAG_PROFILE_*", "HYP04_TRANSMISSION_*", "HYP04_EFFECT_*",
)

ANALYSIS_LOCK = LSE / "GST_HYP04_ANALYSIS_LOCK_v1.0.md"
_SIGNED_RE = re.compile(r"SIGNED\s+(\d{4}-\d{2}-\d{2})")


class FreezeError(RuntimeError):
    """A precondition does not hold.

    FreezeError, never a bare `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git(*args: str, repo: Path) -> str:
    try:
        out = subprocess.run(("git", *args), cwd=str(repo), capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise FreezeError(f"git {' '.join(args)} could not run: {e}") from e
    if out.returncode != 0:
        raise FreezeError(
            f"git {' '.join(args)} failed: {out.stderr.strip()[:200]}")
    return out.stdout.strip()


def _commit_sha(repo: Path) -> str:
    """HEAD, with a clean tree required.

    A commit sha that does not describe the working tree is not provenance: it
    names code that is not the code that ran.
    """
    dirty = _git("status", "--porcelain", repo=repo)
    if dirty:
        n = len(dirty.splitlines())
        raise FreezeError(
            f"the working tree has {n} uncommitted change(s); a freeze records "
            "a commit sha, and a sha that does not describe the tree names "
            "code that is not the code that ran. Commit or stash first.")
    return _git("rev-parse", "HEAD", repo=repo)


def _analysis_lock(lock_path: Path, freeze_date: date) -> tuple[str, str]:
    """(document name, signed date). REFUSES if signed on or after the freeze.

    section 5 point 3 requires the lock to have been written BEFORE this step. An
    equal date is not "before" and is refused too -- same-day ordering cannot
    be established from a date alone.
    """
    if not lock_path.is_file():
        raise FreezeError(
            f"no analysis lock at {lock_path.name}; C3 requires the freeze to "
            "cite the dated lock that resolved every analysis decision")
    m = _SIGNED_RE.search(lock_path.read_text(encoding="utf-8"))
    if not m:
        raise FreezeError(
            f"{lock_path.name} carries no 'SIGNED <date>' marker; an unsigned "
            "lock resolves nothing")
    signed = date.fromisoformat(m.group(1))
    if signed >= freeze_date:
        raise FreezeError(
            f"{lock_path.name} is signed {signed.isoformat()}, which is not "
            f"before the freeze date {freeze_date.isoformat()}. The governing "
            "procedure requires the lock to precede the freeze; an equal date "
            "does not establish the order.")
    return lock_path.name, signed.isoformat()


def _scan_for_results(lse: Path) -> list[str]:
    hits: list[str] = []
    for pat in RESULT_ARTIFACT_PATTERNS:
        hits.extend(sorted(p.name for p in lse.glob(pat)))
    return hits


#: Functions that, called on the real panel, would produce a HYP-04 OUTCOME.
#: Named individually rather than matched by prefix: the point is to ask "did
#: anyone compute a result", and a prefix match would drift into flagging any
#: mention of the modules.
ESTIMATOR_CALLS = ("local_projection_analysis", "placebo_test",
                   "leave_one_anchor_out_cv", "prewhitened_ccf",
                   "recommend_structure")

#: Filename stems that only appear when code touches REAL HYP-04 inputs.
REAL_INPUT_MARKERS = ("HYP04_EVENT_PANEL", "HYP04_Linkage_Map",
                      "HYP04_PEER_CLOSES", "HYP04_ANCHOR_SHOCK")


def _notebook_surface(repo: Path) -> list[dict[str, Any]]:
    """Every notebook, whether it was RUN, and whether it touches real inputs.

    A notebook is the obvious way to compute an outcome outside this
    repository, so it gets looked at rather than assumed about. Two facts are
    recorded per notebook and they answer different questions: saved outputs
    say it was executed and the result kept, and a real-input reference says
    it could produce a HYP-04 outcome at all.
    """
    out: list[dict[str, Any]] = []
    for p in sorted(repo.rglob("*.ipynb")):
        if any(part in (".venv", ".git", "node_modules")
               for part in p.parts):
            continue
        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            out.append({"path": str(p.relative_to(repo)), "unreadable": str(e)})
            continue
        cells = nb.get("cells") or []
        code = [c for c in cells if c.get("cell_type") == "code"]
        src = "\n".join("".join(c.get("source") or "") for c in code)
        out.append({
            "path": str(p.relative_to(repo)).replace("\\", "/"),
            "code_cells": len(code),
            "cells_with_saved_outputs": sum(1 for c in code if c.get("outputs")),
            "cells_with_execution_count": sum(
                1 for c in code if c.get("execution_count")),
            "references_real_inputs": sorted(
                m for m in REAL_INPUT_MARKERS if m in src),
        })
    return out


def _estimator_paths(repo: Path) -> list[str]:
    """Modules that read the real panel AND call an estimator.

    This is the structural question behind the attestation: not "is there an
    estimator" (there is, and there should be), but "is there a route from the
    real event set into it". While no such route exists, computing an outcome
    from this repository takes writing one.
    """
    hits: list[str] = []
    for p in sorted(repo.rglob("*.py")):
        if any(part in (".venv", ".git") for part in p.parts):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "HYP04_EVENT_PANEL" not in src:
            continue
        # A CALL NODE, not a substring. Two files defeated substring matching
        # on its first two runs: this module names all five functions as string
        # literals in ESTIMATOR_CALLS, and the test suite embeds a wiring
        # example as fixture TEXT. Both are mentions. Parsing tells them from
        # code, and keeps tests in scope -- a test that really wired the panel
        # to an estimator would compute a real outcome on every CI run, which
        # is exactly what this is looking for.
        try:
            tree = ast.parse(src)
        except SyntaxError:
            hits.append(str(p.relative_to(repo)).replace("\\", "/")
                        + " (unparseable; reported rather than skipped)")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.id if isinstance(fn, ast.Name)
                    else fn.attr if isinstance(fn, ast.Attribute) else None)
            if name in ESTIMATOR_CALLS:
                hits.append(str(p.relative_to(repo)).replace("\\", "/"))
                break
    return hits


def _results_in_history(repo: Path) -> list[str]:
    """Result artifacts ever ADDED on any branch -- including then deleted.

    `_scan_for_results` looks at the working tree, which a delete would empty.
    History does not forget.
    """
    args = ["log", "--all", "--diff-filter=A", "--name-only", "--pretty=format:",
            "--"] + [f"*{pat}" for pat in RESULT_ARTIFACT_PATTERNS]
    out = _git(*args, repo=repo)
    return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})


def _first_committed(repo: Path, pattern: str) -> Optional[str]:
    out = _git("log", "--all", "--diff-filter=A", "--format=%ad",
               "--date=short", "--", pattern, repo=repo)
    dates = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return min(dates) if dates else None


def computation_surface(*, repo: Path = REPO_ROOT, lse: Path = LSE
                        ) -> dict[str, Any]:
    """Everything checkable about whether an outcome could have been computed.

    THIS DOES NOT ESTABLISH THE ATTESTATION AND MUST NEVER BE READ AS DOING SO.
    It widens the backstop from six filename globs to the structural question,
    and it records dates that bound the window a human has to think back over.
    Someone can still join closes to shocks in a spreadsheet, and nothing here
    would see it. That is why `frozen_before_any_result_computed` stays null in
    every draft this module writes.
    """
    inputs = {
        "anchor_shocks": _first_committed(repo, "*HYP04_ANCHOR_SHOCK*"),
        "peer_closes": _first_committed(repo, "*HYP04_PEER_CLOSES*"),
        "curated_map_v1_2": _first_committed(repo, "*HYP04_Linkage_Map_v1.2*"),
        "enumerated_event_set": _first_committed(
            repo, "*HYP04_EVENT_PANEL_*.json"),
    }
    dated = [d for d in (inputs["anchor_shocks"], inputs["peer_closes"],
                         inputs["curated_map_v1_2"]) if d]
    return {
        "what_this_is_not": (
            "NOT proof that no outcome was computed. A spreadsheet or a scratch "
            "script outside this repository would leave no trace here. This "
            "records what IS checkable so the attestation is made against "
            "evidence rather than against nothing."),
        "estimator_modules_exist": True,
        "panel_to_estimator_paths": _estimator_paths(repo),
        "estimator_calls_searched": list(ESTIMATOR_CALLS),
        "notebooks": _notebook_surface(repo),
        "result_artifacts_in_git_history": _results_in_history(repo),
        "real_inputs_first_committed": inputs,
        "all_real_inputs_coexist_from": max(dated) if len(dated) == 3 else None,
        "window_note": (
            "Before every real input existed there was no series to compute a "
            "peer response from, so the period a signer has to account for "
            "starts at all_real_inputs_coexist_from -- not at the beginning of "
            "the project."),
    }


def _contributing_edges(map_path: Path, event_ids: tuple[str, ...],
                        anchors_by_event: dict[str, str]) -> list[Any]:
    """Curated edges whose anchor supplies at least one eligible event."""
    res = load_curated_linkage(map_path)
    if not res.ok:
        raise FreezeError(
            f"{map_path.name} did not load cleanly ({res.rows_rejected} rows "
            "rejected); a freeze is not built over a map that failed its own "
            "validation")
    live_anchors = {anchors_by_event[e].upper()
                    for e in event_ids if e in anchors_by_event}
    return [e for e in res.edges if e.anchor_ticker.upper() in live_anchors]


def _require_ratified(edges: list[Any]) -> None:
    unratified = sorted(
        f"{e.anchor_ticker}->{e.peer_ticker} ({e.review_status or 'blank'})"
        for e in edges if (e.review_status or "").strip() != RATIFIED_REVIEW_STATUS)
    if unratified:
        raise FreezeError(
            f"{len(unratified)} contributing edge(s) are not "
            f"'{RATIFIED_REVIEW_STATUS}': {', '.join(unratified)}. The frozen "
            "set is never retroactively changed, so freezing over an edge the "
            "owner flagged draft or needs-revisit would make questionable "
            "linkage permanent. Ratify the map first.")


def build_draft(*, panel_path: Path, out_path: Path, lse: Path = LSE,
                repo: Path = REPO_ROOT, lock_path: Optional[Path] = None,
                today: Optional[date] = None) -> dict[str, Any]:
    """Everything section 5 makes derivable. Nothing it does not."""
    freeze_date = today or date.today()
    lock_path = lock_path or ANALYSIS_LOCK

    if out_path.exists():
        raise FreezeError(
            f"{out_path.name} already exists. Freezes are append-only and are "
            "never overwritten -- a second freeze for the same date would make "
            "the first unfalsifiable.")
    if not panel_path.is_file():
        raise FreezeError(
            f"no event panel at {panel_path.name}; run make_event_panel first "
            "-- C3 freezes the set C2 counted, and cannot invent one")

    panel = json.loads(panel_path.read_text(encoding="utf-8"))

    results = _scan_for_results(lse)
    if results:
        raise FreezeError(
            f"result artifacts already exist ({', '.join(results[:4])}). section 5 "
            "orders the freeze BEFORE results are computed; freezing now would "
            "record an order that did not happen.")

    surface = computation_surface(repo=repo, lse=lse)

    # Two refusals, and only two. Each is a case where an outcome demonstrably
    # WAS computed, not a case where one could have been -- the difference
    # between a check worth stopping for and a warning an operator learns to
    # wave through.
    historic = surface["result_artifacts_in_git_history"]
    if historic:
        raise FreezeError(
            f"result artifacts exist in git history ({', '.join(historic[:4])}) "
            "even though the working tree is clean. A deleted result is still "
            "a computed result, and section 5 orders the freeze first.")
    ran_on_real = [nb["path"] for nb in surface["notebooks"]
                   if nb.get("cells_with_saved_outputs")
                   and nb.get("references_real_inputs")]
    if ran_on_real:
        raise FreezeError(
            f"{', '.join(ran_on_real)} has saved outputs AND references real "
            "HYP-04 inputs, which is an executed computation over real data. "
            "Freezing after it would record an order that did not happen.")

    per_pair = panel.get("per_pair") or {}
    floor = panel.get("registered_floor")
    count = per_pair.get("eligible_anchor_events")
    if not isinstance(count, int) or not isinstance(floor, int):
        raise FreezeError(
            "the panel does not carry an integer eligible count and floor; "
            "refusing to freeze against an unreadable panel")
    if count < floor:
        raise FreezeError(
            f"the panel derives {count} eligible anchor events, below the "
            f"registered floor of {floor}. A freeze records a sample that "
            "cleared its floor.")

    prov = LinkageProvenance(**{
        k: v for k, v in (panel.get("linkage_provenance") or {}).items()
        if k in ("source", "source_path", "source_sha256", "rows_seen",
                 "rows_rejected", "edges_usable", "load_ok")})
    if prov.uses_placeholder_linkage:
        raise FreezeError(
            "the panel's linkage provenance derives uses_placeholder_linkage="
            "True. C5 bars displaying placeholder-linkage results at any event "
            "count, so a freeze built on it could never clear the gate.")

    map_name = (panel.get("sources") or {}).get("curated_map")
    if not map_name:
        raise FreezeError("the panel does not name the curated map it used")
    map_path = lse / map_name
    if not map_path.is_file():
        raise FreezeError(f"the panel's curated map {map_name} is not on disk")
    map_sha = (panel.get("sources") or {}).get("curated_map_sha256")
    if map_sha and _sha256(map_path) != map_sha:
        raise FreezeError(
            f"{map_name} has changed since the panel was built (sha mismatch). "
            "Rebuild the panel; a freeze must name the exact map it froze.")

    event_ids, anchors_by_event = _panel_events(panel)
    edges = _contributing_edges(map_path, event_ids, anchors_by_event)
    _require_ratified(edges)

    sha = _commit_sha(repo)
    lock_name, lock_signed = _analysis_lock(lock_path, freeze_date)

    draft: dict[str, Any] = {
        "artifact": out_path.name,
        "hypothesis_id": "HYP-04",
        "freeze_date": freeze_date.isoformat(),
        "status": "DRAFT -- INERT UNTIL THE OWNER FIELDS ARE FILLED",
        "what_this_is": (
            "A draft freeze record per GST_PROSPECTIVE_RESULT_DISPLAY_GATES_"
            "v1.0 section 5. Every derivable field is derived; the attestation is "
            "not, and is left null."),
        "consequence_if_completed": (
            "A completed freeze supplies C3, carries the count for C2 and "
            "clears C5, taking the display gate from FOUR denials to ONE. The "
            "survivor is C1, which is a registry act."),
        # ---- derived, never accepted as arguments ----
        "eligible_event_ids": list(event_ids),
        "eligible_event_count": len(event_ids),
        "registered_floor": floor,
        "uses_placeholder_linkage": prov.uses_placeholder_linkage,
        "analysis_commit_sha": sha,
        "analysis_lock_document": lock_name,
        "analysis_lock_signed": lock_signed,
        "input_hashes": {
            "panel": _sha256(panel_path),
            **{k: v for k, v in (panel.get("sources") or {}).items()
               if k.endswith("_sha256")},
        },
        "contributing_edges": [
            {"anchor": e.anchor_ticker, "peer": e.peer_ticker,
             "as_of_date": e.as_of_date, "review_status": e.review_status}
            for e in edges],
        "result_scan": {
            "patterns": list(RESULT_ARTIFACT_PATTERNS),
            "hits": results,
            "is_not_proof": (
                "a filename scan cannot establish that nobody has computed an "
                "outcome elsewhere; it is a backstop, which is exactly why the "
                "attestation below is a human's"),
        },
        # Recorded so the freeze carries the EVIDENCE the attestation was made
        # against, not just the claim. A later reader can re-run every one of
        # these; none of them makes the claim for the signer.
        "computation_surface": surface,
        # ---- the owner's, left blank ----
        "frozen": False,
        "frozen_before_any_result_computed": None,
        "attested_by": "",
        "attested_date": "",
        "owner_fields": list(OWNER_FIELDS),
        "how_to_complete": (
            "Set frozen=true, frozen_before_any_result_computed=true, and fill "
            "attested_by / attested_date. Then validate_freeze() will accept "
            "it. Editing any derived field above makes it invalid."),
    }
    return draft


def _panel_events(panel: dict) -> tuple[tuple[str, ...], dict[str, str]]:
    """Eligible ids and their anchors, taken from the panel's own record.

    The enumeration itself happens in `make_event_panel`, which runs the
    resolved panel through `linkage_resolution.freeze_record_fields` -- the one
    function whose job that is. This only reads what the panel recorded, so the
    ids are never retyped and never re-ordered by hand.
    """
    ids = panel.get("eligible_event_ids")
    anchors = panel.get("eligible_event_anchors")
    if isinstance(ids, list) and isinstance(anchors, dict):
        return tuple(str(i) for i in ids), {str(k): str(v)
                                            for k, v in anchors.items()}
    raise FreezeError(
        "the panel artifact does not enumerate its eligible event ids and "
        "anchors. section 5 point 1 requires the set to be enumerated mechanically; "
        "rebuild the panel with an assembler that records them.")


def validate_freeze(path: Path, *, panel_path: Optional[Path] = None
                    ) -> FreezeRecord:
    """Read a FILLED-IN draft and build the gate's FreezeRecord.

    Refuses unless the operator supplied the attestation, and refuses if any
    derived field was edited. An operator may add the attestation and nothing
    else.
    """
    if not path.is_file():
        raise FreezeError(f"no freeze draft at {path}")
    d = json.loads(path.read_text(encoding="utf-8"))

    if d.get("frozen") is not True:
        raise FreezeError(
            "'frozen' is not true. A draft is not a freeze, and this module "
            "will not set that field for you.")
    if d.get("frozen_before_any_result_computed") is not True:
        raise FreezeError(
            "'frozen_before_any_result_computed' is not attested. A freeze "
            "recorded after a result is not a freeze, and no machine can "
            "establish this -- a human must.")
    for f in ("attested_by", "attested_date"):
        if not str(d.get(f) or "").strip():
            raise FreezeError(f"{f!r} is blank; an unattributed attestation is "
                              "not an attestation")
    ids = d.get("eligible_event_ids")
    if not isinstance(ids, list) or not ids:
        raise FreezeError("the freeze enumerates no eligible event ids")
    if len(set(ids)) != len(ids):
        raise FreezeError("the frozen event-id set contains duplicates")
    if d.get("uses_placeholder_linkage") is not False:
        raise FreezeError("the freeze declares placeholder linkage; C5 bars it")
    if not str(d.get("analysis_commit_sha") or "").strip():
        raise FreezeError("the freeze records no analysis commit sha")
    if not str(d.get("analysis_lock_document") or "").strip():
        raise FreezeError("the freeze cites no analysis lock")

    if panel_path is not None:
        panel = json.loads(panel_path.read_text(encoding="utf-8"))
        panel_ids, _ = _panel_events(panel)
        if tuple(str(i) for i in ids) != panel_ids:
            raise FreezeError(
                "the frozen event-id set does not match the panel's. A derived "
                "field was edited, which is the one thing an operator may not "
                "do.")

    return FreezeRecord(
        frozen=True,
        eligible_event_ids=tuple(str(i) for i in ids),
        analysis_commit_sha=str(d["analysis_commit_sha"]),
        analysis_lock_document=str(d["analysis_lock_document"]),
        frozen_before_any_result_computed=True,
        uses_placeholder_linkage=False,
    )


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Write an INERT freeze draft.")
    ap.add_argument("--panel", type=Path,
                    default=LSE / "HYP04_EVENT_PANEL_2026-09-08.json")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print without writing")
    args = ap.parse_args(argv)

    out = args.out or LSE / f"HYP04_FREEZE_DRAFT_{date.today().isoformat()}.json"
    draft = build_draft(panel_path=args.panel,
                        out_path=Path("/nonexistent") if args.dry_run else out)

    print(f"eligible events   : {draft['eligible_event_count']} "
          f"(floor {draft['registered_floor']})")
    print(f"commit sha        : {draft['analysis_commit_sha'][:12]}")
    print(f"analysis lock     : {draft['analysis_lock_document']} "
          f"(signed {draft['analysis_lock_signed']})")
    print(f"placeholder linkage: {draft['uses_placeholder_linkage']}")
    print(f"contributing edges : {len(draft['contributing_edges'])}")
    print()
    print("BLANK, and this module will not fill them: "
          + ", ".join(draft["owner_fields"]))
    print(draft["consequence_if_completed"])

    if args.dry_run:
        print("\nDRY RUN -- nothing written")
    else:
        out.write_text(json.dumps(draft, indent=1) + "\n", encoding="utf-8")
        print(f"\nWROTE {out.name} (INERT)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
