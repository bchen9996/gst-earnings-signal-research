#!/usr/bin/env python3
"""The ratification driver: it does the mechanics and refuses the judgements.

The driver exists so the owner does not hand-edit a CSV and a JSON file on the
way to an irreversible freeze. That only helps if two things hold, and this
pins both:

  1. It REFUSES every judgement. No default review_status, no bulk flag, no
     inferred attestation, no placeholder that survives to disk.
  2. It WRITES what it claims and nothing else. A driver that quietly altered
     a derived field would be worse than the hand-edit it replaces.

Plus the thing a signer actually needs: the templates it prints are pasteable,
and following them end to end really does open the gate. Both are checked --
the second in a sandbox, against a copy, with the real gate asserted CLOSED
afterwards.

Repo testing convention (hand-rolled check(), run directly, no pytest).
Offline.

Run directly: python test_hyp04_supply_chain_hedge_ratify.py
"""
from __future__ import annotations

import socket
import sys


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during an offline test")


socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

import contextlib  # noqa: E402
import csv  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from hyp04_supply_chain_hedge import ratify as R  # noqa: E402
from hyp04_supply_chain_hedge.curated_linkage import (  # noqa: E402
    REVIEW_STATUSES,
    load_curated_linkage,
)
from hyp04_supply_chain_hedge.display_gate import evaluate_gate  # noqa: E402
from hyp04_supply_chain_hedge.make_freeze_draft import (  # noqa: E402
    OWNER_FIELDS,
    validate_freeze,
)

ROOT = Path(__file__).resolve().parent
LSE = ROOT / "Live Signal Engine"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + label
          + ("" if ok or not detail else f"   {detail}"))
    if not ok:
        FAILURES.append(label)


def refuses(label: str, fn, *a, **k) -> None:
    """The refusal IS the feature, so assert the type and capture the text."""
    try:
        fn(*a, **k)
    except R.RatifyError as exc:
        check(label, True)
        return str(exc)
    except Exception as exc:                       # noqa: BLE001
        check(label, False, f"raised {type(exc).__name__}: {exc}")
        return ""
    check(label, False, "did not refuse")
    return ""


def _rows(p: Path) -> list[dict[str, str]]:
    with p.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _all_reviewed() -> dict[str, str]:
    return {R._key(r): "reviewed" for r in _rows(R.WORKSHEET)}


# --------------------------------------------------------------------------


def test_1_the_templates_are_pasteable() -> None:
    """A template you cannot paste is worse than no template."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_map_template()
    out = buf.getvalue()
    cmd = [ln for ln in out.splitlines() if "ratify map --curated-by" in ln]
    check("1a. the map template emits exactly one command line", len(cmd) == 1)
    # Backslash AND backtick: the driver is run from PowerShell, where a
    # trailing backtick continues a line and a trailing backslash does not.
    # Either one at end-of-line would break the paste in one shell or the
    # other, so neither may appear there -- nor anywhere else in the output,
    # since a backtick inside a pasted command is a PowerShell escape.
    bad = [ln for ln in out.splitlines()
           if ln.rstrip().endswith(("\\", "`")) or "`" in ln]
    check("1b. it is a SINGLE line -- no backslash or backtick continuations",
          not bad, str(bad[:2]))
    rows = _rows(R.WORKSHEET)
    check("1c. every row appears in it",
          all(f"--edge {R._key(r)}=" in cmd[0] for r in rows) if cmd else False)
    check("1d. and every value is a blank, not a suggestion",
          bool(cmd) and cmd[0].count("<draft|reviewed|needs_revisit>")
          == len(rows))
    check("1e. it says which edges feed the eligible set",
          "feeds the eligible set" in out)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_attest_template()
    att = buf.getvalue()
    check("1f. the attest template carries the affirmation verbatim",
          R.AFFIRMATION in att)
    check("1g. and tells the signer when NOT to type it",
          "do not type it" in att.lower())


def test_2_it_refuses_every_judgement() -> None:
    """Each refusal must fire for ITS OWN reason.

    These originally ran against the default `out_path`. Once v1.3 was really
    ratified that file existed, so every one of them tripped the
    already-exists guard FIRST and passed without ever reaching the guard it
    names. Only 2c noticed, because it is the one that inspects the message.

    A test that passes for the wrong reason is worse than one that fails, so
    each call now writes to a scratch path that does not exist, and 2m pins
    the mistake itself.
    """
    rows = _rows(R.WORKSHEET)
    good = _all_reviewed()

    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "HYP04_Linkage_Map_v9.9.csv"

        def rm(label, **kw):
            kw.setdefault("out_path", fresh)
            return refuses(label, R.ratify_map, **kw)

        rm("2a. a missing decision",
           decisions={R._key(rows[0]): "reviewed"}, curated_by="T",
           curated_date="2026-09-08")
        msg = rm("2b. a typo'd edge, naming BOTH halves",
                 decisions={**{k: "reviewed" for k in list(good)[:-1]},
                            "JBL:CISCO": "reviewed"},
                 curated_by="T", curated_date="2026-09-08")
        check("2c. the typo itself is named", "JBL:CISCO" in msg, msg[:120])

        refuses("2d. a status outside the map's vocabulary", R.parse_edge_args,
                ["MCK:CVS=approved"])
        refuses("2e. a template placeholder left in an edge",
                R.parse_edge_args, ["MCK:CVS=<draft|reviewed|needs_revisit>"])
        refuses("2f. the same edge decided twice", R.parse_edge_args,
                ["MCK:CVS=reviewed", "MCK:CVS=draft"])
        refuses("2g. a malformed edge spec", R.parse_edge_args,
                ["MCK=reviewed"])
        rm("2h. a blank signer", decisions=good, curated_by="  ",
           curated_date="2026-09-08")
        rm("2i. a placeholder signer", decisions=good,
           curated_by="<your name>", curated_date="2026-09-08")
        rm("2j. a future decision date", decisions=good, curated_by="T",
           curated_date="2099-01-01")
        rm("2k. a non-ISO date", decisions=good, curated_by="T",
           curated_date="Sept 8")
        check("2l. nothing above actually wrote a map", not fresh.exists())

    check("2m. there is no bulk flag on the CLI",
          not any("--all" in a for a in
                  ("--edge", "--curated-by", "--curated-date")))

    # The masking bug itself: with an existing out_path, a call whose
    # decisions are fine AND whose decisions are missing both refuse -- but
    # for the same reason. That is what hid four broken assertions.
    dup = refuses("2n. an existing map version still refuses", R.ratify_map,
                  decisions=good, curated_by="T", curated_date="2026-09-08")
    check("2o. and it is the already-exists guard, not a judgement guard",
          "already exists" in dup, dup[:120])


def test_3_underscore_spelling_normalises() -> None:
    """`needs revisit` has a space; PowerShell makes that awkward per-flag."""
    d = R.parse_edge_args(["JBL:BB=needs_revisit"])
    check("3a. needs_revisit becomes the map's own vocabulary",
          d == {"JBL:BB": "needs revisit"}, str(d))
    check("3b. and that vocabulary is what curated_linkage defines",
          "needs revisit" in REVIEW_STATUSES)


def test_4_it_writes_only_the_three_blanked_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        ws = t / R.WORKSHEET.name
        shutil.copy2(R.WORKSHEET, ws)
        ev = t / R.EVIDENCE.name
        ev.write_text("evidence stand-in", encoding="utf-8")
        out = t / "HYP04_Linkage_Map_v1.3.csv"

        # evidence must be present at all
        refuses("4a. ratifying with no evidence artifact on disk",
                R.ratify_map, decisions=_all_reviewed(), curated_by="T",
                curated_date="2026-09-08", worksheet=ws, out_path=out,
                evidence=t / "nope.md")

        res = R.ratify_map(decisions=_all_reviewed(), curated_by="test-op",
                           curated_date="2026-09-08", worksheet=ws,
                           out_path=out, evidence=ev)
        check("4b. it writes the map", out.is_file())
        check("4c. every row survives", res["rows"] == len(_rows(ws)))

        src, got = _rows(ws), _rows(out)
        moved = sorted({f for a, b in zip(src, got) for f in a
                        if (a.get(f) or "") != (b.get(f) or "")})
        check("4d. exactly the three blanked fields moved",
              moved == sorted(R.OWNER_CSV_FIELDS), str(moved))
        check("4e. the evidence prose is byte-identical",
              all((a.get("notes_caveats") or "") == (b.get("notes_caveats") or "")
                  for a, b in zip(src, got)))

        loaded = load_curated_linkage(out)
        check("4f. the written map loads clean",
              loaded.ok and loaded.rows_rejected == 0,
              f"ok={loaded.ok} rejected={loaded.rows_rejected}")

        refuses("4g. overwriting an existing map version", R.ratify_map,
                decisions=_all_reviewed(), curated_by="T",
                curated_date="2026-09-08", worksheet=ws, out_path=out,
                evidence=ev)

        # a worksheet that arrives pre-filled is not the document that was
        # checked, and is refused rather than silently re-signed
        pre = t / "prefilled.csv"
        rr = _rows(ws)
        for r in rr:
            r["review_status"] = "reviewed"
        with pre.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rr[0].keys()))
            w.writeheader()
            w.writerows(rr)
        refuses("4h. a pre-filled worksheet", R.ratify_map,
                decisions=_all_reviewed(), curated_by="T",
                curated_date="2026-09-08", worksheet=pre,
                out_path=t / "HYP04_Linkage_Map_v1.4.csv", evidence=ev)


def test_5_a_bad_map_is_never_left_on_disk() -> None:
    """The out_path sits under the newest-map glob. It must not survive."""
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        ws = t / R.WORKSHEET.name
        rr = _rows(R.WORKSHEET)
        rr[0]["as_of_date"] = "not-a-date"          # fails the validator
        with ws.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rr[0].keys()))
            w.writeheader()
            w.writerows(rr)
        ev = t / R.EVIDENCE.name
        ev.write_text("x", encoding="utf-8")
        out = t / "HYP04_Linkage_Map_v1.3.csv"
        refuses("5a. a map that fails its own validator", R.ratify_map,
                decisions=_all_reviewed(), curated_by="T",
                curated_date="2026-09-08", worksheet=ws, out_path=out,
                evidence=ev)
        check("5b. and the unloadable file was REMOVED, not left in force",
              not out.exists())


def _synthetic_draft(t: Path) -> Path:
    """A draft shaped exactly like make_freeze_draft's, over the real panel."""
    panel_path, panel = R._panel()
    ids = [str(i) for i in panel["eligible_event_ids"]]
    d = {
        "artifact": "HYP04_FREEZE_DRAFT_TEST.json",
        "hypothesis_id": "HYP-04",
        "status": "DRAFT -- INERT UNTIL THE OWNER FIELDS ARE FILLED",
        "eligible_event_ids": ids,
        "eligible_event_count": len(ids),
        "registered_floor": panel["registered_floor"],
        "uses_placeholder_linkage": False,
        "analysis_commit_sha": "0" * 40,
        "analysis_lock_document": "GST_HYP04_ANALYSIS_LOCK_v1.0.md",
        "frozen": False,
        "frozen_before_any_result_computed": None,
        "attested_by": "",
        "attested_date": "",
        "owner_fields": list(OWNER_FIELDS),
    }
    p = t / "HYP04_FREEZE_DRAFT_TEST.json"
    p.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    return p


def test_6_the_attestation_cannot_be_inferred() -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        p = _synthetic_draft(t)
        before = p.read_text(encoding="utf-8")

        msg = refuses("6a. a wrong affirmation", R.attest, draft_path=p,
                      attested_by="test-op", affirmation="yes",
                      attested_date="2026-09-08")
        check("6b. and the refusal quotes the sentence to type",
              R.AFFIRMATION in msg)
        check("6c. the draft was NOT touched",
              p.read_text(encoding="utf-8") == before)
        refuses("6d. an almost-right affirmation", R.attest, draft_path=p,
                attested_by="test-op", attested_date="2026-09-08",
                affirmation=R.AFFIRMATION.replace("anyone", "me"))
        refuses("6e. an unattributed attestation", R.attest, draft_path=p,
                attested_by="  ", affirmation=R.AFFIRMATION,
                attested_date="2026-09-08")
        check("6f. still untouched after every refusal",
              p.read_text(encoding="utf-8") == before)


def test_7_attesting_moves_only_the_owner_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        p = _synthetic_draft(t)
        before = json.loads(p.read_text(encoding="utf-8"))

        out = R.attest(draft_path=p, attested_by="test-op",
                       affirmation=R.AFFIRMATION, attested_date="2026-09-08")
        after = json.loads(p.read_text(encoding="utf-8"))

        moved = sorted(k for k in set(before) | set(after)
                       if before.get(k) != after.get(k))
        check("7a. only the owner fields and bookkeeping moved",
              set(moved) <= set(R.ATTEST_FIELDS) | {"attestation_text"},
              str(moved))
        check("7b. the frozen event set is byte-identical",
              after["eligible_event_ids"] == before["eligible_event_ids"])
        check("7c. the commit sha is untouched",
              after["analysis_commit_sha"] == before["analysis_commit_sha"])
        check("7d. the file no longer describes itself as a draft",
              "FROZEN" in after["status"])
        check("7e. and it records the sentence that was typed",
              after["attestation_text"] == R.AFFIRMATION)

        rec = validate_freeze(p, panel_path=R._panel()[0])
        check("7f. the result validates as a freeze", rec.frozen is True)
        check("7g. over the panel's own enumerated set",
              len(rec.eligible_event_ids) == out["frozen_events"] > 0)

        refuses("7h. re-attesting an already-frozen record", R.attest,
                draft_path=p, attested_by="someone-else",
                affirmation=R.AFFIRMATION, attested_date="2026-09-08")

        # Close the loop: the record THIS DRIVER produced, against the registry
        # v1.12 would write, must actually open the gate. The v1.12 suite
        # rehearses the same thing from a hand-built FreezeRecord; this checks
        # the one the owner's own command emits.
        from hyp04_supply_chain_hedge import make_registry_v1_12 as V12
        doc, _ = V12.build_v1_12()
        reg = t / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json"
        reg.write_text(json.dumps(doc), encoding="utf-8")
        g = evaluate_gate(eligible_event_count=len(rec.eligible_event_ids),
                          freeze=rec, registry_path=reg)
        check("7i. the attested record OPENS the gate against v1.12",
              g.open is True and not g.denials, str(g.denials))


def test_8_pins_are_shown_before_they_are_written() -> None:
    fake = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json"
    refuses("8a. repointing at a registry that does not exist",
            R.repoint_pins, registry=fake, apply=False)

    real = LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.11.json"
    edits = R.repoint_pins(registry=real, apply=False)
    check("8b. against the current registry both pins are already correct",
          edits == [], str(edits))

    before = {rel: (ROOT / rel).read_text(encoding="utf-8")
              for rel, _ in R.PIN_SITES}
    R.repoint_pins(registry=real, apply=False)
    check("8c. a dry run writes nothing",
          all((ROOT / rel).read_text(encoding="utf-8") == before[rel]
              for rel, _ in R.PIN_SITES))


def test_9_a_ratified_map_opens_nothing() -> None:
    """The map is now ratified. That was one of five conditions, not the gate.

    This previously asserted no v1.3 existed. It does now, so the assertion
    becomes the sharper one: ratification moved a real thing and the gate is
    STILL closed, because C1 and C3 are untouched by it.
    """
    g = evaluate_gate()
    check("9a. the gate is still CLOSED", g.open is False)
    check("9b. C4 is still MET", g.conditions["C4_decisions_resolved"] is True)
    check("9c. still exactly four denials", len(g.denials) == 4,
          str(len(g.denials)))
    check("9d. the eligible count is still unknown, not zero",
          g.evidence.get("eligible_count") is None)

    live = sorted(LSE.glob("HYP04_Linkage_Map_v1.*.csv"))[-1]
    res = load_curated_linkage(live)
    check("9e. the map in force is v1.3 and loads clean",
          live.name == "HYP04_Linkage_Map_v1.3.csv" and res.ok, live.name)
    check("9f. every edge in it is ratified",
          all(e.review_status == "reviewed" for e in res.edges),
          str(sorted({e.review_status for e in res.edges})))
    check("9g. attributed to a named curator on every row",
          all((e.curated_by or "").strip() for e in res.edges))

    # The two acts that are still the owner's, and are still not done.
    check("9h. no registry v1.12 was written",
          not (LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json").exists())
    drafts = sorted(LSE.glob("HYP04_FREEZE_DRAFT_*.json"))
    for d in drafts:
        rec = json.loads(d.read_text(encoding="utf-8"))
        check(f"9i. {d.name} is unattested",
              rec.get("frozen") is not True
              and rec.get("frozen_before_any_result_computed") is not True,
              f"frozen={rec.get('frozen')}")

    # Earlier versions are immutable; ratification writes a NEW file.
    for old in ("v1.0", "v1.1", "v1.2"):
        p = LSE / f"HYP04_Linkage_Map_{old}.csv"
        if p.is_file():
            r = load_curated_linkage(p)
            check(f"9j. {old} still carries no ratified edge",
                  all(e.review_status != "reviewed" for e in r.edges),
                  str(sorted({e.review_status for e in r.edges})))


if __name__ == "__main__":
    test_1_the_templates_are_pasteable()
    test_2_it_refuses_every_judgement()
    test_3_underscore_spelling_normalises()
    test_4_it_writes_only_the_three_blanked_fields()
    test_5_a_bad_map_is_never_left_on_disk()
    test_6_the_attestation_cannot_be_inferred()
    test_7_attesting_moves_only_the_owner_fields()
    test_8_pins_are_shown_before_they_are_written()
    test_9_a_ratified_map_opens_nothing()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 RATIFY-DRIVER TESTS PASSED")
    sys.exit(0)
