# Overnight autonomous session — behavior contract

Deliberately **not** named `CLAUDE.md`. A file named `CLAUDE.md` is loaded into
*every* session in this repo, which would apply an unattended-overnight contract
to ordinary interactive work. This file is read only when the runner names it.

You are running unattended via `tools/overnight_runner.sh`, which alternates a
**planning pass** and a **build pass**. No human will respond until morning.

---

## Project rules that override everything below

These come from the project's governance and are not negotiable by any pass.
If a step in this contract conflicts with one of these, the rule wins and you
write `BLOCKED.md`.

1. **The display gate does not MOVE — in either direction.** It is **OPEN** as
   of 2026-09-09: all five conditions MET, 0 denials, 214 frozen events. The
   owner opened it through the governed chain; ratifying the map, attesting the
   freeze and writing registry v1.12 are acts only they may perform.

   This rule used to read "the gate stays CLOSED … assert exactly 4 denials,
   eligible count 0". That was the state, not the principle, and it went false
   on 2026-09-09. **Do not restore it.** A pass that found the gate open and
   "fixed" it would be undoing a signed attestation.

   At the start of every pass record `current_decision()`; after every change
   that touches HYP-04 code, assert it is **unchanged**. If it moved either
   way, stop and write `BLOCKED.md`. Never run `ratify map`, `ratify attest`,
   `ratify pins --apply`, or any `make_registry_v*.py --write` unattended.

   An open gate licenses **reporting a measurement**. It is not a finding, not
   a validated strategy, and not permission to compute one unattended: writing
   the first panel-to-estimator path is a governance act and a morning
   decision.
2. **Never push.** Not to `origin`, not anywhere. Commit only. Pushing is a
   morning decision. (`git push` in any form is out of scope for every pass.)
3. **Never fabricate data.** A guessed peer ticker, a filled-in owner field, an
   invented linkage row, or a plausible-looking number is worse than no
   progress. If a value is unknown, stop and write `BLOCKED.md`.
4. **Never edit `HYP04_Linkage_Map_v1.0.csv` in place.** Its sha256 is pinned.
5. **Artifacts are append-only and dated.** Never rewrite a committed dated
   artifact. Never create a second lock amendment — the resolver takes
   `found[-1]`, so a new one silently displaces the existing one.
6. **Never claim any quantum result is validated.**
7. **No project-derived power calculations.** Outcome-free MDE work is allowed.
8. **`yfinance` stays out of `requirements-hyp04.txt`.**
9. **Never run the live network runners** (`run_canary_audit`,
   `run_full_audit`, `run_linkage_history`, `run_peer_closes_fetch`,
   `run_peer_lineage_audit`, `run_peer_name_search`). They need a staged
   go-ahead a sleeping human cannot give.
10. **Use `RefusedError`, never bare `assert`,** for anything that must hold in
    production — `python -O` strips asserts.

## Every planning pass

You have read access plus write access to `PLAN.md` and `BLOCKED.md` only.

1. Read `TASK.md` for the goal and `PLAN.md` for progress so far. Create
   `PLAN.md` if absent.
2. **Write no code in this pass.** Only the two bookkeeping files.
3. Update `PLAN.md` with a checklist. Each unchecked item must be small enough
   to implement *and verify* in one build pass — one function, one test, one
   fix. Not "build the feature".
4. Every item states **how it will be verified**: the exact command to run and
   what output means success. An item without a verification line is not ready.
5. If the whole task is done, make `ALL STEPS COMPLETE` the **last line** of
   `PLAN.md` and stop. The runner matches that line exactly.
6. If the next step needs a human — an ambiguous requirement, a credential, a
   destructive action, anything touching the rules above — write the question
   to `BLOCKED.md` and stop. Do not invent an assumption to get past it.

## Every build pass

1. Implement **exactly** the next unchecked item. Do not jump ahead, and do not
   opportunistically fix unrelated things you notice — note them in `PLAN.md`.
2. Run that item's stated verification. If it fails, fix it or stop; never
   check off an unverified item.
3. Re-assert the gate invariant (rule 1) if HYP-04 code changed.
4. Check the item off in `PLAN.md`.
5. Commit with **explicit paths**:
   `git add <the files you touched> && git commit -m "<short description>"`.
   **Never `git add -A`** — it sweeps `.venv`, scratch files, and artifacts
   that must not be committed casually.
6. Never force-push, never rewrite history, never delete a branch, never
   change a remote.
7. If something breaks and you cannot fix it in this pass, write `BLOCKED.md`
   and stop rather than thrashing on the same failure.

## Always

- Small, verified, committed steps beat large uncommitted ones.
- Never touch files outside this repo.
- Never run destructive commands (`rm -rf`, force-push, dropping data).
- Report honestly in `PLAN.md`: if a test fails, say so. A green checklist that
  does not match the repo is worse than an honest blocked one.
- If you cannot make progress, write `BLOCKED.md` and stop. Looping on the same
  failure burns the night and the usage budget.
