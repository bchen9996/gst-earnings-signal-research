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


def refuses(label: str, fn, *a, expect: str, **k) -> str:
    """Refuse, AND refuse for the stated reason. `expect` is REQUIRED.

    It used to assert only the exception TYPE. That is not enough: `ratify_map`
    has eight distinct guards and every one of them raises RatifyError, so a
    call meant to exercise one passes just as happily when a different one
    fires first. That is what happened once v1.3 really existed -- every
    refusal in test_2 tripped the already-exists guard before reaching the
    guard it names, and only the single assertion that read the message
    noticed.

    Keep `expect` a short distinctive fragment rather than the whole sentence.
    Pinning full prose makes the test fail on rewording, which teaches people
    to loosen it, and a loosened reason-check is the thing being fixed here.
    """
    if not expect.strip():
        check(label, False,
              "expect= is empty, which matches ANY message and makes this "
              "assertion vacuous. Give it a real fragment.")
        return ""
    try:
        fn(*a, **k)
    except R.RatifyError as exc:
        got = str(exc)
        if expect.lower() in got.lower():
            check(label, True)
        else:
            check(label, False,
                  f"refused for the WRONG reason -- wanted {expect!r}, "
                  f"got: {got[:140]}")
        return got
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


def _unpasteable(out: str) -> list[str]:
    """Lines that would break a paste, in EITHER shell.

    Backslash AND backtick: this repo is driven from PowerShell, where a
    trailing backtick continues a line and a trailing backslash does not, and
    from bash, where it is the other way round. Neither may end a line -- and a
    backtick may not appear anywhere, since inside a pasted command it is a
    PowerShell escape.

    Factored out because it was applied to the map template only. The attest
    template kept its backslash continuations for two commits after the map
    template was fixed, which would have broken the paste at the single most
    consequential signature in the project.
    """
    return [ln for ln in out.splitlines()
            if ln.rstrip().endswith(("\\", "`")) or "`" in ln]


def test_0_the_reason_check_actually_bites() -> None:
    """Who tests the helper. A reason-check that cannot fail is decoration.

    `expect` exists because asserting the exception TYPE let a guard firing
    for the wrong reason pass as the guard the test names. That fix is only
    worth anything if a wrong reason really is recorded as a failure -- so
    this drives the helper with a reason that cannot match and requires it to
    fail, then with the true reason and requires it to pass.

    Without this, someone could quietly widen the match (or default `expect`
    to "") and every suite would stay green.
    """
    saved = list(FAILURES)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        refuses("control -- this failure is EXPECTED", R.parse_edge_args,
                ["MCK:CVS=approved"], expect="a reason it never gives")
    bit = len(FAILURES) > len(saved)
    FAILURES[:] = saved                 # the control's own failure is the point

    check("0a. a refusal for the WRONG reason is recorded as a failure", bit)
    out = buf.getvalue()
    check("0b. and the report names both the wanted and the actual reason",
          "wanted" in out and "got:" in out, out[:160])

    with contextlib.redirect_stdout(io.StringIO()):
        refuses("control -- the true reason", R.parse_edge_args,
                ["MCK:CVS=approved"], expect="is not one of")
    check("0c. CONTROL -- the true reason still passes",
          len(FAILURES) == len(saved))

    # An empty fragment matches ANY message, which would make every
    # reason-check vacuous while still looking present at each call site.
    # That is the obvious way to "fix" a failing reason-check, so it is
    # rejected rather than documented.
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        refuses("control -- empty fragment, EXPECTED to fail", R.parse_edge_args,
                ["MCK:CVS=approved"], expect="")
    empty_rejected = len(FAILURES) > len(saved)
    FAILURES[:] = saved
    check("0d. an empty `expect` is rejected, not silently satisfied",
          empty_rejected)
    check("0e. and it says why", "vacuous" in buf2.getvalue(),
          buf2.getvalue()[:160])


def test_1_the_templates_are_pasteable() -> None:
    """A template you cannot paste is worse than no template."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_map_template()
    out = buf.getvalue()
    cmd = [ln for ln in out.splitlines() if "ratify map --curated-by" in ln]
    check("1a. the map template emits exactly one command line", len(cmd) == 1)
    check("1b. the map template is a SINGLE line", not _unpasteable(out),
          str(_unpasteable(out)[:2]))
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
    # The gap that let the backslashes survive here: 1b tested one template.
    check("1h. the attest template is ALSO a single pasteable line",
          not _unpasteable(att), str(_unpasteable(att)[:2]))
    acmd = [ln for ln in att.splitlines() if "ratify attest" in ln]
    check("1i. it emits exactly one command line", len(acmd) == 1, str(acmd))
    check("1j. carrying both flags, so nothing is left to be guessed",
          bool(acmd) and "--attested-by" in acmd[0] and "--affirm" in acmd[0])

    # Third template, added with `ratify split`. Held to the same rule from
    # the start rather than after a paste breaks: the attest template kept its
    # backslashes for two commits because this check covered one template.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R._print_split_template()
    spl = buf.getvalue()
    check("1k. the split template carries its affirmation verbatim",
          R.SPLIT_AFFIRMATION in spl)
    check("1l. and is a single pasteable line too",
          not _unpasteable(spl), str(_unpasteable(spl)[:2]))
    scmd = [ln for ln in spl.splitlines() if "ratify split" in ln]
    check("1m. one command line, carrying both flags",
          len(scmd) == 1 and "--declared-by" in scmd[0]
          and "--affirm" in scmd[0], str(scmd))
    check("1n. the three affirmations are DIFFERENT sentences -- a signer who "
          "pastes the wrong one is refused, not silently accepted",
          len({R.AFFIRMATION, R.SPLIT_AFFIRMATION}) == 2)


def test_1b_declaring_a_split_refuses_every_judgement() -> None:
    """`ratify split` signs a derivation; it may not perform or alter one."""
    import json as _json
    import tempfile as _tf
    from hyp04_supply_chain_hedge import make_validation_split as V

    ids = list(_json.loads(
        (LSE / "HYP04_EVENT_PANEL_2026-09-08.json").read_text(
            encoding="utf-8"))["eligible_event_ids"])
    base = {**V.derive_split(ids), "declared": False, "declared_by": "",
            "declared_date": ""}

    with _tf.TemporaryDirectory() as td:
        p = Path(td) / "split.json"

        def _fresh():
            p.write_text(_json.dumps(base), encoding="utf-8")
            return p

        refuses("1b-a. a wrong affirmation is refused",
                 lambda: R.declare_split(split_path=_fresh(),
                                         declared_by="bchen9996",
                                         affirmation="I promise",
                                         declared_date="2026-09-10"),
                 expect="affirmation does not match")
        refuses("1b-b. and nothing is written when it is",
                 lambda: R.declare_split(split_path=_fresh(),
                                         declared_by="bchen9996",
                                         affirmation="",
                                         declared_date="2026-09-10"),
                 expect="affirmation does not match")
        check("1b-c. the file is still an undeclared draft after both",
              _json.loads(p.read_text(encoding="utf-8"))["declared"] is False)

        refuses("1b-d. a placeholder signer is refused",
                 lambda: R.declare_split(split_path=_fresh(),
                                         declared_by="<your name>",
                                         affirmation=R.SPLIT_AFFIRMATION,
                                         declared_date="2026-09-10"),
                 expect="declared-by")

        # CONTROL: the right affirmation DOES sign, so the refusals above are
        # about the affirmation and not about declare_split refusing always.
        out = R.declare_split(split_path=_fresh(), declared_by="bchen9996",
                              affirmation=R.SPLIT_AFFIRMATION,
                              declared_date="2026-09-10")
        check("1b-e. CONTROL -- the exact sentence signs it",
              out["exploration"] == 157 and out["holdout"] == 57,
              f"{out['exploration']}/{out['holdout']}")
        check("1b-f. and only the signature fields moved",
              all(_json.loads(p.read_text(encoding="utf-8"))[k] == base[k]
                  for k in ("cut_calendar_period", "rule",
                            "holdout_fraction_realized")))
        refuses("1b-g. re-declaring an already-declared split is refused",
                 lambda: R.declare_split(split_path=p,
                                         declared_by="someone else",
                                         affirmation=R.SPLIT_AFFIRMATION,
                                         declared_date="2026-09-10"),
                 expect="already declared")


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

        def rm(label, *, expect, **kw):
            kw.setdefault("out_path", fresh)
            return refuses(label, R.ratify_map, expect=expect, **kw)

        rm("2a. a missing decision",
           decisions={R._key(rows[0]): "reviewed"}, curated_by="T",
           curated_date="2026-09-08", expect="have no decision")
        msg = rm("2b. a typo'd edge, naming BOTH halves",
                 decisions={**{k: "reviewed" for k in list(good)[:-1]},
                            "JBL:CISCO": "reviewed"},
                 curated_by="T", curated_date="2026-09-08",
                 expect="not rows in")
        check("2c. the typo itself is named", "JBL:CISCO" in msg, msg[:120])

        refuses("2d. a status outside the map's vocabulary", R.parse_edge_args,
                ["MCK:CVS=approved"], expect="is not one of")
        refuses("2e. a template placeholder left in an edge",
                R.parse_edge_args,
                ["MCK:CVS=<draft|reviewed|needs_revisit>"],
                expect="template placeholder")
        refuses("2f. the same edge decided twice", R.parse_edge_args,
                ["MCK:CVS=reviewed", "MCK:CVS=draft"],
                expect="given twice")
        refuses("2g. a malformed edge spec", R.parse_edge_args,
                ["MCK=reviewed"], expect="is not ANCHOR:PEER=status")
        rm("2h. a blank signer", decisions=good, curated_by="  ",
           curated_date="2026-09-08", expect="is blank")
        rm("2i. a placeholder signer", decisions=good,
           curated_by="<your name>", curated_date="2026-09-08",
           expect="template placeholder")
        rm("2j. a future decision date", decisions=good, curated_by="T",
           curated_date="2099-01-01", expect="is in the future")
        rm("2k. a non-ISO date", decisions=good, curated_by="T",
           curated_date="Sept 8", expect="is not an ISO date")
        check("2l. nothing above actually wrote a map", not fresh.exists())

    check("2m. there is no bulk flag on the CLI",
          not any("--all" in a for a in
                  ("--edge", "--curated-by", "--curated-date")))

    # The masking bug itself: with an existing out_path, a call whose
    # decisions are fine AND whose decisions are missing both refuse -- but
    # for the same reason. That is what hid four broken assertions.
    dup = refuses("2n. an existing map version still refuses", R.ratify_map,
                  decisions=good, curated_by="T",
                  curated_date="2026-09-08", expect="already exists")
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
                evidence=t / "nope.md", expect="is not on disk")

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
                evidence=ev, expect="already exists")

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
                out_path=t / "HYP04_Linkage_Map_v1.4.csv", evidence=ev,
                expect="already carries")


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
                evidence=ev, expect="does not load cleanly")
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
                      attested_date="2026-09-08",
                      expect="affirmation does not match")
        check("6b. and the refusal quotes the sentence to type",
              R.AFFIRMATION in msg)
        check("6c. the draft was NOT touched",
              p.read_text(encoding="utf-8") == before)
        refuses("6d. an almost-right affirmation", R.attest, draft_path=p,
                attested_by="test-op", attested_date="2026-09-08",
                affirmation=R.AFFIRMATION.replace("anyone", "me"),
                expect="affirmation does not match")
        refuses("6e. an unattributed attestation", R.attest, draft_path=p,
                attested_by="  ", affirmation=R.AFFIRMATION,
                attested_date="2026-09-08", expect="is blank")
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
                affirmation=R.AFFIRMATION, attested_date="2026-09-08",
                expect="already attested")

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
    # v1.12 exists now, so it is no longer the example of a missing registry.
    # A name that will never exist is, and it keeps this guard testable through
    # every future version bump.
    refuses("8a. repointing at a registry that does not exist",
            R.repoint_pins,
            registry=LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v9.99.json",
            apply=False, expect="is not on disk")
    check("8a2. and v1.12, which does exist, is accepted",
          fake.is_file(), fake.name)

    # The pins were repointed to v1.12 on 2026-09-09. "Already correct" has to
    # mean the registry the gate READS, not a hardcoded version -- otherwise
    # this assertion re-breaks on every bump.
    from hyp04_supply_chain_hedge.display_gate import REGISTRY_CURRENT
    real = REGISTRY_CURRENT
    edits = R.repoint_pins(registry=real, apply=False)
    check("8b. against the current registry both pins are already correct",
          edits == [], str(edits))

    before = {rel: (ROOT / rel).read_text(encoding="utf-8")
              for rel, _ in R.PIN_SITES}
    R.repoint_pins(registry=real, apply=False)
    check("8c. a dry run writes nothing",
          all((ROOT / rel).read_text(encoding="utf-8") == before[rel]
              for rel, _ in R.PIN_SITES))


def test_9_the_chain_completed_and_each_act_is_attributable() -> None:
    """All five conditions cleared, in the order the code enforced.

    This began as "no v1.3 exists", became "a ratified map opens nothing", and
    is now the end of the chain: map ratified 2026-09-08, freeze attested
    2026-09-09, registry v1.12 written, pins repointed, gate OPEN.

    What it pins is not the outcome but the ATTRIBUTION -- every act that
    required a human names one, because the driver refuses to supply them.
    """
    from hyp04_supply_chain_hedge.display_gate import current_decision
    g = current_decision()
    check("9a. the gate is OPEN", g.open is True, str(g.denials))
    check("9b. C4 is still MET", g.conditions["C4_decisions_resolved"] is True)
    check("9c. zero denials", len(g.denials) == 0, str(g.denials))
    # `eligible_event_count`, not `eligible_count` -- the latter is not a key
    # the gate emits, so `.get(...) is None` passed no matter what it said.
    check("9d. the count is the frozen 214",
          g.evidence["eligible_event_count"] == 214,
          str(g.evidence["eligible_event_count"]))

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
    # Both of these inverted on 2026-09-09 when the OWNER ran the two commands
    # this driver refuses to run for them. What is pinned now is that the
    # record of those acts names a human -- which is the only thing that makes
    # them acts rather than side effects.
    check("9h. registry v1.12 exists",
          (LSE / "GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.12.json").is_file())
    drafts = sorted(LSE.glob("HYP04_FREEZE_DRAFT_*.json"))
    check("9h2. and a freeze artifact exists", bool(drafts))
    for d in drafts:
        rec = json.loads(d.read_text(encoding="utf-8"))
        check(f"9i. {d.name} is attested by a NAMED person on a date",
              rec.get("frozen") is True
              and rec.get("frozen_before_any_result_computed") is True
              and bool(str(rec.get("attested_by") or "").strip())
              and bool(str(rec.get("attested_date") or "").strip()),
              f"by={rec.get('attested_by')!r} on={rec.get('attested_date')!r}")
        check(f"9i2. {d.name} records the sentence that was typed",
              rec.get("attestation_text") == R.AFFIRMATION)

    # Earlier versions are immutable; ratification writes a NEW file.
    for old in ("v1.0", "v1.1", "v1.2"):
        p = LSE / f"HYP04_Linkage_Map_{old}.csv"
        if p.is_file():
            r = load_curated_linkage(p)
            check(f"9j. {old} still carries no ratified edge",
                  all(e.review_status != "reviewed" for e in r.edges),
                  str(sorted({e.review_status for e in r.edges})))


if __name__ == "__main__":
    test_0_the_reason_check_actually_bites()
    test_1_the_templates_are_pasteable()
    test_1b_declaring_a_split_refuses_every_judgement()
    test_2_it_refuses_every_judgement()
    test_3_underscore_spelling_normalises()
    test_4_it_writes_only_the_three_blanked_fields()
    test_5_a_bad_map_is_never_left_on_disk()
    test_6_the_attestation_cannot_be_inferred()
    test_7_attesting_moves_only_the_owner_fields()
    test_8_pins_are_shown_before_they_are_written()
    test_9_the_chain_completed_and_each_act_is_attributable()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("ALL HYP-04 RATIFY-DRIVER TESTS PASSED")
    sys.exit(0)
