#!/usr/bin/env python3
"""The HYP-04 ratification driver: one command per step, none of them a judgement.

=== WHAT THIS IS, AND THE LINE IT DOES NOT CROSS ===

Three acts stand between HYP-04 and an open display gate and all three are the
repo owner's: ratify the curated map, attest the freeze, move the registry.
Everything BETWEEN those acts is mechanical -- copying a CSV, filling four keys
in a JSON file, rewriting two module constants, re-running a validator -- and
mechanical work done by hand is where mistakes get signed.

So this module does the mechanics and refuses the judgements. Concretely:

  * `map` will not write a review_status this module chose. It requires one
    explicit `--edge ANCHOR:PEER=<status>` per row, covering every row, with no
    default and no bulk `--all` shortcut. Seven decisions, typed seven times.
  * `attest` will not infer `frozen_before_any_result_computed`. It requires
    the affirmation sentence typed out verbatim. `make_freeze_draft` says a
    machine must not fill that field; that remains true here. What fills it is
    a human typing a sentence -- this only carries the sentence to the file
    without a hand-edit that could also touch a derived field.
  * Nothing here evaluates a result, and `gate` reports the gate rather than
    changing it.

Every step is separately reversible up to the freeze. The freeze is not, which
is why it is the step with the sentence.

=== THE CHAIN ===

    ratify status                 <- where you are, and the next exact command

    1  evidence produced          (mine, done)
    2  ratify map ...             YOURS -- the review signature
    3  ratify panel               mechanical
    4  commit                     mine
    5  make_freeze_draft          mechanical
    6  ratify attest ...          YOURS -- the attestation signature
    7  make_registry_v1_12 --write  YOURS to run (it refuses out of order)
    8  ratify pins                mechanical
    9  ratify gate                reports OPEN

Steps 2, 6 and 7 are signatures. The rest is typing this module does better.

=== WHAT AN OPEN GATE LICENSES ===

`GST_PROSPECTIVE_RESULT_DISPLAY_GATES_v1.0.md`: "reaching a threshold licenses
LOOKING, not CONCLUDING." 193 is a governance eligibility floor, not a power
calculation. An open gate means a measurement may be reported. It is not a
finding, not a validated strategy, and not a claim that supply-chain
transmission exists.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .artifacts import newest_in
from .curated_linkage import REVIEW_STATUSES, load_curated_linkage

REPO_ROOT = Path(__file__).resolve().parent.parent
LSE = REPO_ROOT / "Live Signal Engine"

WORKSHEET = LSE / "HYP04_LINKAGE_RATIFICATION_WORKSHEET_v1.3.csv"
RATIFIED_MAP = LSE / "HYP04_Linkage_Map_v1.3.csv"
EVIDENCE = LSE / "HYP04_EDGE_VERIFICATION_2026-09-08.md"
V1_12 = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json"

#: The three fields the worksheet blanked. Nothing else may move.
OWNER_CSV_FIELDS = ("review_status", "curated_by", "curated_date")

#: The status that counts as ratified. The other two are real answers.
RATIFIED = "reviewed"

#: Typed verbatim or the attestation does not happen. Deliberately a sentence
#: and not a flag: `--yes` is something you can type without reading.
AFFIRMATION = ("No HYP-04 result has been computed, anywhere, by anyone, "
               "including outside this repository.")

#: `attest` writes these and guards that nothing else in the draft moved.
#: The first four are `make_freeze_draft.OWNER_FIELDS`; `status` is bookkeeping
#: -- a file that says DRAFT while `frozen` is true misdescribes itself.
ATTEST_FIELDS = ("frozen", "frozen_before_any_result_computed",
                 "attested_by", "attested_date", "status")

#: (module, old constant line, new constant line) for `pins`.
PIN_SITES = (
    ("hyp04_supply_chain_hedge/display_gate.py", "REGISTRY_CURRENT"),
    ("hyp04_supply_chain_hedge/dashboard.py", "REGISTRY"),
)

PLACEHOLDERS = ("<draft|reviewed|needs revisit>", "<draft|reviewed|needs_revisit>",
                "<status>", "<your name>", "<name>", "TODO", "XXX")


class RatifyError(RuntimeError):
    """A precondition does not hold.

    RatifyError, never a bare `assert`: `python -O` strips asserts, and a
    precondition that vanishes under an optimisation flag is not one.
    """


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _git(*args: str) -> str:
    out = subprocess.run(("git", *args), cwd=str(REPO_ROOT),
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RatifyError(f"git {' '.join(args)} failed: "
                          f"{out.stderr.strip()[:200]}")
    return out.stdout.strip()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _key(row: dict[str, str]) -> str:
    return f"{row['anchor_ticker'].strip().upper()}:" \
           f"{row['peer_ticker'].strip().upper()}"


def _panel() -> tuple[Optional[Path], dict[str, Any]]:
    p = newest_in(LSE, "HYP04_EVENT_PANEL_*.json")
    if p is None:
        return None, {}
    p = Path(p)
    return p, json.loads(p.read_text(encoding="utf-8"))


def _contributing_anchors(panel: dict[str, Any]) -> set[str]:
    return {str(a).upper()
            for a in (panel.get("eligible_event_anchors") or {}).values()}


def _reject_placeholder(label: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise RatifyError(f"{label} is blank. An unattributed decision is not "
                          "a decision.")
    for p in PLACEHOLDERS:
        if v.lower() == p.lower():
            raise RatifyError(
                f"{label} is still the template placeholder {v!r}. This is the "
                "field where the judgement goes; fill it in.")
    return v


def _iso(label: str, value: Optional[str]) -> str:
    v = (value or date.today().isoformat()).strip()
    try:
        d = date.fromisoformat(v)
    except ValueError as e:
        raise RatifyError(f"{label} {v!r} is not an ISO date (YYYY-MM-DD)"
                          ) from e
    if d > date.today():
        raise RatifyError(f"{label} {v} is in the future; a decision cannot be "
                          "dated after the day it was made")
    return v


# --------------------------------------------------------------------------
# step 2 -- ratify the map
# --------------------------------------------------------------------------

def parse_edge_args(specs: list[str]) -> dict[str, str]:
    """`ANCHOR:PEER=status` -> {"ANCHOR:PEER": status}. One per row, no defaults."""
    out: dict[str, str] = {}
    for s in specs:
        if "=" not in s or ":" not in s.split("=", 1)[0]:
            raise RatifyError(
                f"--edge {s!r} is not ANCHOR:PEER=status (e.g. "
                "--edge MCK:CVS=reviewed)")
        pair, status = s.split("=", 1)
        k = pair.strip().upper()
        # `needs revisit` contains a space, which is awkward to quote per-flag
        # in PowerShell. Accept the underscore spelling and normalise; the file
        # only ever holds the vocabulary `curated_linkage` defines.
        status = status.strip().replace("_", " ")
        if status in PLACEHOLDERS or status.replace(" ", "_") in PLACEHOLDERS:
            raise RatifyError(
                f"--edge {k} still carries the template placeholder "
                f"{status!r}. Every edge needs a real decision; the template "
                "is deliberately unrunnable.")
        if status not in REVIEW_STATUSES:
            raise RatifyError(
                f"--edge {k}={status!r} is not one of {REVIEW_STATUSES}")
        if k in out:
            raise RatifyError(f"--edge {k} given twice")
        out[k] = status
    return out


def ratify_map(*, decisions: dict[str, str], curated_by: str,
               curated_date: str, worksheet: Path = WORKSHEET,
               out_path: Path = RATIFIED_MAP,
               evidence: Path = EVIDENCE) -> dict[str, Any]:
    """Write the ratified map. Refuses on anything unanswered."""
    if not worksheet.is_file():
        raise RatifyError(f"no worksheet at {worksheet.name}")
    if out_path.exists():
        raise RatifyError(
            f"{out_path.name} already exists. Linkage-map versions are "
            "immutable; a second ratification of the same version would make "
            "the first unfalsifiable. Bump to v1.4 if you are genuinely "
            "re-deciding.")
    if not evidence.is_file():
        raise RatifyError(
            f"the edge-verification evidence {evidence.name} is not on disk. "
            "Ratifying without the evidence artifact present is signing a "
            "review that has nothing to review.")

    curated_by = _reject_placeholder("--curated-by", curated_by)
    curated_date = _iso("--curated-date", curated_date)

    rows = _rows(worksheet)
    if not rows:
        raise RatifyError(f"{worksheet.name} has no rows")
    keys = [_key(r) for r in rows]

    missing = [k for k in keys if k not in decisions]
    extra = [k for k in decisions if k not in keys]
    if missing or extra:
        # Both together: a typo (JBL:CISCO for JBL:CSCO) shows up as one of
        # each, and reporting only the missing half sends you looking for a
        # decision you already made.
        parts = []
        if missing:
            parts.append(f"{len(missing)} row(s) have no decision: "
                         + ", ".join(missing))
        if extra:
            parts.append(f"--edge names {', '.join(extra)}, which are not rows "
                         f"in {worksheet.name} (typo?)")
        raise RatifyError(
            "; ".join(parts) + ". Every row needs exactly one decision -- the "
            "map does not load with a blank review_status, and a default "
            "chosen by this module would be a judgement it is not entitled to "
            "make.")

    for r in rows:
        for f in OWNER_CSV_FIELDS:
            if (r.get(f) or "").strip():
                raise RatifyError(
                    f"{_key(r)} already carries {f}={r[f]!r} in the worksheet. "
                    "The worksheet ships blank; a pre-filled one is not the "
                    "document that was checked.")
        r["review_status"] = decisions[_key(r)]
        r["curated_by"] = curated_by
        r["curated_date"] = curated_date

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # --- verify, and remove the file rather than leave a broken map in force
    try:
        written = _rows(out_path)
        if len(written) != len(rows):
            raise RatifyError("row count changed on write")
        for src, got in zip(_rows(worksheet), written):
            for f, v in src.items():
                if f in OWNER_CSV_FIELDS:
                    continue
                if (got.get(f) or "") != (v or ""):
                    raise RatifyError(
                        f"{_key(src)}: field {f!r} was altered on write. Only "
                        f"{OWNER_CSV_FIELDS} may change.")
        res = load_curated_linkage(out_path)
        if not res.ok or res.rows_rejected:
            raise RatifyError(
                f"{out_path.name} does not load cleanly "
                f"({res.rows_rejected} row(s) rejected). Not leaving an "
                "unloadable file where the newest-map glob will find it.")
    except Exception:
        out_path.unlink(missing_ok=True)
        raise

    _, panel = _panel()
    anchors = _contributing_anchors(panel)
    contributing = [e for e in res.edges if e.anchor_ticker.upper() in anchors]
    unratified = sorted(f"{e.anchor_ticker}->{e.peer_ticker}"
                        f"({e.review_status})"
                        for e in contributing
                        if (e.review_status or "").strip() != RATIFIED)
    return {
        "written": out_path.name,
        "rows": len(written),
        "edges_usable": len(res.edges),
        "contributing_edges": len(contributing),
        "contributing_not_ratified": unratified,
        "decisions": dict(decisions),
    }


# --------------------------------------------------------------------------
# step 6 -- attest the freeze
# --------------------------------------------------------------------------

def attest(*, draft_path: Path, attested_by: str, affirmation: str,
           attested_date: Optional[str] = None) -> dict[str, Any]:
    """Fill the four owner fields on a freeze draft. Nothing else moves."""
    from .make_freeze_draft import OWNER_FIELDS, validate_freeze

    if not draft_path.is_file():
        raise RatifyError(f"no freeze draft at {draft_path}")
    attested_by = _reject_placeholder("--attested-by", attested_by)
    attested_date = _iso("--attested-date", attested_date)

    if (affirmation or "").strip() != AFFIRMATION:
        raise RatifyError(
            "the affirmation does not match, so nothing was written.\n\n"
            "This is the one claim in the project that no check can stand in "
            "for: a filename scan cannot see a regression run in a notebook "
            "somewhere else. Type it exactly:\n\n"
            f'  --affirm "{AFFIRMATION}"\n\n'
            "If you have looked at a HYP-04 outcome, do not type it. The "
            "freeze is then invalid, and that is the finding.")

    before = json.loads(draft_path.read_text(encoding="utf-8"))
    if before.get("frozen") is True:
        raise RatifyError(
            f"{draft_path.name} is already attested by "
            f"{before.get('attested_by')!r} on {before.get('attested_date')!r}. "
            "Freezes are append-only; re-attesting would overwrite a record "
            "that other documents already cite.")
    for f in OWNER_FIELDS:
        if f not in before:
            raise RatifyError(
                f"{draft_path.name} has no {f!r} key; this does not look like "
                "a draft from make_freeze_draft")

    after = dict(before)
    after["frozen"] = True
    after["frozen_before_any_result_computed"] = True
    after["attested_by"] = attested_by
    after["attested_date"] = attested_date
    after["status"] = (f"FROZEN -- attested by {attested_by} on "
                       f"{attested_date}")
    after["attestation_text"] = AFFIRMATION

    moved = sorted(k for k in set(before) | set(after)
                   if before.get(k) != after.get(k))
    unexpected = [k for k in moved
                  if k not in ATTEST_FIELDS and k != "attestation_text"]
    if unexpected:
        raise RatifyError(
            f"attesting would move {unexpected}, which are derived fields. "
            "Refusing.")

    draft_path.write_text(json.dumps(after, indent=1) + "\n", encoding="utf-8")

    panel_path, _ = _panel()
    try:
        rec = validate_freeze(draft_path, panel_path=panel_path)
    except Exception:
        draft_path.write_text(json.dumps(before, indent=1) + "\n",
                              encoding="utf-8")
        raise
    return {
        "draft": draft_path.name,
        "attested_by": attested_by,
        "attested_date": attested_date,
        "frozen_events": len(rec.eligible_event_ids),
        "commit_sha": rec.analysis_commit_sha[:12],
        "analysis_lock": rec.analysis_lock_document,
    }


# --------------------------------------------------------------------------
# step 8 -- repoint the two code pins
# --------------------------------------------------------------------------

def repoint_pins(*, registry: Path = V1_12, apply: bool = False
                 ) -> list[tuple[str, str, str]]:
    """Point display_gate and dashboard at the newest registry."""
    if not registry.is_file():
        raise RatifyError(
            f"{registry.name} is not on disk. Repointing the gate at a "
            "registry that does not exist would make it fail closed for the "
            "wrong reason -- run make_registry_v1_12 --write first.")
    edits: list[tuple[str, str, str]] = []
    for rel, const in PIN_SITES:
        p = REPO_ROOT / rel
        text = p.read_text(encoding="utf-8")
        hits = [ln for ln in text.splitlines()
                if ln.startswith(f"{const} = LSE / ")]
        if len(hits) != 1:
            raise RatifyError(
                f"{rel}: expected exactly one `{const} = LSE / ...` line, "
                f"found {len(hits)}. Refusing to guess which to rewrite.")
        old = hits[0]
        new = f'{const} = LSE / "{registry.name}"'
        if old == new:
            continue
        edits.append((rel, old.strip(), new))
        if apply:
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return edits


# --------------------------------------------------------------------------
# status -- where you are and the next exact command
# --------------------------------------------------------------------------

def chain_status() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []

    def add(n: int, whose: str, label: str, ok: Optional[bool],
            detail: str, cmd: str = "") -> None:
        steps.append({"n": n, "whose": whose, "label": label, "ok": ok,
                      "detail": detail, "cmd": cmd})

    add(1, "mine", "Edge evidence produced", EVIDENCE.is_file(),
        EVIDENCE.name if EVIDENCE.is_file() else "missing")

    map_ok = False
    if RATIFIED_MAP.is_file():
        res = load_curated_linkage(RATIFIED_MAP)
        _, panel = _panel()
        anchors = _contributing_anchors(panel)
        bad = [f"{e.anchor_ticker}->{e.peer_ticker}({e.review_status})"
               for e in res.edges
               if e.anchor_ticker.upper() in anchors
               and (e.review_status or "").strip() != RATIFIED]
        map_ok = bool(res.ok) and not bad
        detail = (f"{RATIFIED_MAP.name}: {len(res.edges)} usable edge(s)"
                  + (f"; NOT ratified: {', '.join(bad)}" if bad else
                     "; all contributing edges reviewed"))
    else:
        detail = f"{RATIFIED_MAP.name} does not exist"
    add(2, "YOURS", "Curated map ratified", map_ok, detail,
        "python -m hyp04_supply_chain_hedge.ratify map --template")

    panel_path, panel = _panel()
    used_map = (panel.get("sources") or {}).get("curated_map")
    panel_ok = bool(panel_path) and used_map == RATIFIED_MAP.name
    add(3, "mine", "Panel rebuilt against the ratified map", panel_ok,
        (f"{panel_path.name} was built against {used_map}" if panel_path
         else "no panel"),
        "python -m hyp04_supply_chain_hedge.ratify panel")

    try:
        dirty = _git("status", "--porcelain")
    except RatifyError as e:
        # A git that will not answer is not evidence of a clean tree, so the
        # error text becomes the "dirty" reason rather than being swallowed.
        dirty = str(e)
    clean = not dirty
    add(4, "mine", "Working tree committed", clean,
        "clean" if clean else f"{len(dirty.splitlines())} uncommitted change(s)"
        + " -- the freeze records a commit sha and refuses on a dirty tree")

    draft = newest_in(LSE, "HYP04_FREEZE_DRAFT_*.json")
    add(5, "mine", "Freeze draft written", draft is not None,
        Path(draft).name if draft else "none",
        "python -m hyp04_supply_chain_hedge.make_freeze_draft")

    frozen_ok, frozen_detail = False, "no draft"
    if draft:
        from .make_freeze_draft import validate_freeze
        try:
            rec = validate_freeze(Path(draft), panel_path=panel_path)
            frozen_ok = True
            frozen_detail = f"{len(rec.eligible_event_ids)} events frozen"
        except Exception as exc:                  # noqa: BLE001 -- reported
            frozen_detail = str(exc).splitlines()[0][:120]
    add(6, "YOURS", "Freeze attested", frozen_ok, frozen_detail,
        "python -m hyp04_supply_chain_hedge.ratify attest --template")

    add(7, "YOURS", "Registry v1.12 written", V1_12.is_file(),
        V1_12.name if V1_12.is_file() else "not written",
        "python -m hyp04_supply_chain_hedge.make_registry_v1_12 --write")

    pins_ok, pins_detail = False, "v1.12 not written yet"
    if V1_12.is_file():
        try:
            pending = repoint_pins(apply=False)
            pins_ok = not pending
            pins_detail = ("both pins point at v1.12" if pins_ok
                           else f"{len(pending)} pin(s) still on the old "
                                "registry")
        except RatifyError as exc:
            pins_detail = str(exc)[:120]
    add(8, "mine", "Code pins repointed", pins_ok, pins_detail,
        "python -m hyp04_supply_chain_hedge.ratify pins --apply")

    return steps


def gate_report() -> dict[str, Any]:
    from .display_gate import evaluate_gate
    from .make_freeze_draft import validate_freeze

    panel_path, _ = _panel()
    draft = newest_in(LSE, "HYP04_FREEZE_DRAFT_*.json")
    rec, count = None, None
    if draft:
        try:
            rec = validate_freeze(Path(draft), panel_path=panel_path)
            count = len(rec.eligible_event_ids)
        except Exception:                          # noqa: BLE001 -- reported
            rec, count = None, None
    d = evaluate_gate(eligible_event_count=count, freeze=rec)
    return {"open": d.open, "conditions": dict(d.conditions),
            "denials": list(d.denials), "eligible": count}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_map_template() -> None:
    """One line, no continuations.

    An earlier version emitted `\\`-continued lines with a trailing comment,
    which is broken twice over: a comment after `\\` stops it being a line
    continuation at all, and PowerShell -- the shell this repo is driven from
    -- uses a backtick anyway. A template you cannot paste is worse than none.
    """
    rows = _rows(WORKSHEET)
    _, panel = _panel()
    anchors = _contributing_anchors(panel)
    print(f"{len(rows)} rows, {len(rows)} decisions. There is no bulk flag.\n")
    print(f"Read {EVIDENCE.name} first. It recommends nothing, on purpose.\n")
    print("  edge         feeds the eligible set?")
    for r in rows:
        contributing = r["anchor_ticker"].strip().upper() in anchors
        print(f"  {_key(r):<12} {'yes' if contributing else 'no'}")
    print("\nReplace every <...>, then paste as ONE line:\n")
    parts = ["python -m hyp04_supply_chain_hedge.ratify map",
             '--curated-by "<your name>"',
             f"--curated-date {date.today().isoformat()}"]
    parts += [f"--edge {_key(r)}=<draft|reviewed|needs_revisit>" for r in rows]
    print("  " + " ".join(parts))
    # No backticks in anything printed to a terminal: this repo is driven from
    # PowerShell, where a backtick is the line-continuation character, and
    # markdown habits in shell output are how a pasted command gets mangled.
    print("\nUse an underscore in needs_revisit if your shell dislikes the "
          "space;\nboth spellings are accepted and stored as 'needs revisit'.")
    print("\nOnly 'reviewed' ratifies. The other two are real answers: the map "
          "still\nloads, but the freeze refuses over any CONTRIBUTING edge "
          "that is not\n'reviewed', and every contributing anchor is "
          "load-bearing against the floor.")


def _print_attest_template() -> None:
    draft = newest_in(LSE, "HYP04_FREEZE_DRAFT_*.json")
    print("python -m hyp04_supply_chain_hedge.ratify attest \\")
    print('  --attested-by "<your name>" \\')
    print(f'  --affirm "{AFFIRMATION}"')
    print(f"\nDraft: {Path(draft).name if draft else '(none yet -- step 5)'}")
    print("\nThat sentence is the whole attestation. It asserts no beta_h, no "
          "lag profile\nand no peer response has been computed ANYWHERE, "
          "including outside this repo.\nIf you have looked, do not type it.")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m hyp04_supply_chain_hedge.ratify",
        description="Walk HYP-04 from four denials to a decided gate. "
                    "Mechanical steps run here; the three signatures do not.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="where you are, and the next exact command")

    m = sub.add_parser("map", help="STEP 2 (yours): write the ratified map")
    m.add_argument("--template", action="store_true",
                   help="print the command with a blank for every decision")
    m.add_argument("--edge", action="append", default=[],
                   metavar="ANCHOR:PEER=STATUS")
    m.add_argument("--curated-by", default="")
    m.add_argument("--curated-date", default=None)

    p = sub.add_parser("panel", help="STEP 3: rebuild the panel")
    p.add_argument("--dry-run", action="store_true")

    a = sub.add_parser("attest", help="STEP 6 (yours): attest the freeze")
    a.add_argument("--template", action="store_true")
    a.add_argument("--attested-by", default="")
    a.add_argument("--attested-date", default=None)
    a.add_argument("--affirm", default="")

    pn = sub.add_parser("pins", help="STEP 8: repoint the registry pins")
    pn.add_argument("--apply", action="store_true",
                    help="write the change (default shows it)")

    sub.add_parser("gate", help="report the gate; changes nothing")

    args = ap.parse_args(argv)

    if args.cmd == "status":
        steps = chain_status()
        print("HYP-04 ratification chain\n")
        nxt = None
        for s in steps:
            mark = "[x]" if s["ok"] else "[ ]"
            print(f"  {mark} {s['n']}. {s['label']:<40} ({s['whose']})")
            print(f"        {s['detail']}")
            if not s["ok"] and nxt is None:
                nxt = s
        g = gate_report()
        print(f"\n  GATE: {'OPEN' if g['open'] else 'CLOSED'} -- "
              f"{len(g['denials'])} denial(s)")
        for d in g["denials"]:
            print(f"        * {d}")
        if nxt:
            print(f"\nNEXT (step {nxt['n']}, {nxt['whose']}):")
            print(f"  {nxt['cmd'] or '(ask me -- this one is mine)'}")
        return 0

    if args.cmd == "map":
        if args.template or not args.edge:
            _print_map_template()
            return 0 if args.template else 1
        out = ratify_map(decisions=parse_edge_args(args.edge),
                         curated_by=args.curated_by,
                         curated_date=args.curated_date)
        print(f"WROTE {out['written']}  ({out['rows']} rows, "
              f"{out['edges_usable']} usable edges)")
        for k, v in sorted(out["decisions"].items()):
            print(f"  {k:<12} {v}")
        if out["contributing_not_ratified"]:
            print("\nNOTE: contributing edges NOT ratified: "
                  + ", ".join(out["contributing_not_ratified"]))
            print("The freeze will refuse over these. That is the design, not "
                  "a bug --\nrebuild the panel and see what the count becomes "
                  "before deciding.")
        print("\nNext: rebuild the panel (step 3), then I commit (step 4).")
        return 0

    if args.cmd == "panel":
        from . import make_event_panel
        return make_event_panel.main(
            ["--dry-run"] if args.dry_run else ["--force"])

    if args.cmd == "attest":
        if args.template or not args.affirm:
            _print_attest_template()
            return 0 if args.template else 1
        draft = newest_in(LSE, "HYP04_FREEZE_DRAFT_*.json")
        if draft is None:
            raise RatifyError(
                "no freeze draft on disk. Run make_freeze_draft first -- there "
                "is nothing to attest to.")
        out = attest(draft_path=Path(draft), attested_by=args.attested_by,
                     affirmation=args.affirm, attested_date=args.attested_date)
        print(f"ATTESTED {out['draft']}")
        print(f"  by            : {out['attested_by']} on "
              f"{out['attested_date']}")
        print(f"  frozen events : {out['frozen_events']}")
        print(f"  commit sha    : {out['commit_sha']}")
        print(f"  analysis lock : {out['analysis_lock']}")
        print("\nThe event set is now fixed. It is never retroactively "
              "changed.")
        return 0

    if args.cmd == "pins":
        edits = repoint_pins(apply=args.apply)
        if not edits:
            print("Both pins already point at the current registry.")
            return 0
        for rel, old, new in edits:
            print(f"{rel}\n  - {old}\n  + {new}")
        print("\nAPPLIED" if args.apply else "\nDRY RUN -- re-run with --apply")
        return 0

    if args.cmd == "gate":
        g = gate_report()
        print(f"GATE: {'OPEN' if g['open'] else 'CLOSED'}")
        print(f"eligible count: {g['eligible']}")
        for k, v in g["conditions"].items():
            print(f"  {'PASS' if v else 'DENY'}  {k}")
        for d in g["denials"]:
            print(f"  * {d}")
        return 0 if g["open"] else 1

    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RatifyError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
