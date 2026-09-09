# HYP-04 — ratification, freeze, and v1.12: the procedure

**Date:** 2026-09-08
**Status:** instructions and inert documents. Nothing here has been signed, ratified, frozen or written.

---

## What this is for

Three acts stand between HYP-04 and an open display gate, and all three are the
repo owner's. This document is the procedure, and the documents it references
have been checked to work.

**The chain has been rehearsed end to end.**
`test_hyp04_supply_chain_hedge_registry_v1_12.py::test_4_the_rehearsal_opens_the_gate`
assembles a v1.12 registry, the real panel's 214 enumerated event ids and a
completed freeze record, and asserts `evaluate_gate` returns **OPEN with zero
denials**. So these steps do what they claim. Nothing real was written to do it.

## Before you start: every edge is load-bearing

214 eligible events against a floor of 193 is a margin of **21**. The smallest
contributing anchor supplies **30**. So dropping any one anchor's edges fails
the floor — including `INTC→HPQ`, the edge already flagged `needs revisit`.

If honest re-examination says an edge should go, **the answer is more curation,
not a workaround.** Read `HYP04_EDGE_VERIFICATION_2026-09-08.md` before the
worksheet; it is the evidence, and it deliberately recommends nothing.

---

## Step 1 — Ratify (yours)

Open `HYP04_LINKAGE_RATIFICATION_WORKSHEET_v1.3.csv`. It is a copy of
`HYP04_Linkage_Map_v1.2.csv` with `review_status`, `curated_by` and
`curated_date` blanked on every row.

It is **inert as it stands** — blank `review_status` fails
`curated_linkage.load_curated_linkage`, so all seven rows are rejected and no
edge can resolve from it. Its filename also sits outside both linkage-map globs
(`HYP04_Linkage_Map_v*.csv` and `HYP04_Linkage_Map*.csv`), so no consumer picks
it up by accident.

Fill the three fields per row. `review_status` must be one of
`draft`, `reviewed`, `needs revisit`; **only `reviewed` counts as ratified.**

**Then rename it to `HYP04_Linkage_Map_v1.3.csv`.** That rename is what puts it
in force — it is the moment the file starts matching the globs and becomes the
newest map. Verified: filled and renamed, it loads clean with all seven rows
usable.

Do not edit v1.0, v1.1 or v1.2. Existing versions are immutable and v1.0's
sha256 is pinned in tests.

## Step 2 — Rebuild the panel (mine)

The freeze checks the map's hash against the panel, so a ratified map
invalidates the current one. Tell me and I will bump `AS_OF` in
`make_event_panel.py` and re-run it, then confirm the count still clears 193.

## Step 3 — Commit (mine)

The freeze records a commit SHA and refuses on a dirty tree.

## Step 4 — Attest and freeze (yours)

```bash
./.venv/Scripts/python.exe -m hyp04_supply_chain_hedge.make_freeze_draft --dry-run
./.venv/Scripts/python.exe -m hyp04_supply_chain_hedge.make_freeze_draft
```

Then set exactly four fields in the draft — `frozen: true`,
`frozen_before_any_result_computed: true`, `attested_by`, `attested_date`.
Editing any derived field invalidates it; the validator checks the event-id set
against the panel.

**What you are signing.** `frozen_before_any_result_computed` asserts that no
HYP-04 outcome — no `beta_h`, no lag profile, no peer response — has been
computed anywhere, including outside this repository. The module scans for
result artifacts, but that scan is a backstop against the obvious case and says
so in its own text. It is not proof, and it is not a substitute for the claim.

If you have looked, say so. The freeze is then invalid, and that is the finding.

## Step 5 — Registry v1.12 (yours to run)

```bash
./.venv/Scripts/python.exe -m hyp04_supply_chain_hedge.make_registry_v1_12          # dry run
./.venv/Scripts/python.exe -m hyp04_supply_chain_hedge.make_registry_v1_12 --write
```

It moves `status` to `ACTIVE_COLLECTING` (C1), flips both `data_captured`
flags, registers the panel assembler as a capture path, and rewrites
`status_basis` — which still reads *"2 curated edge(s) as of 2026-08-22"*,
stale by five.

**It refuses to run out of order.** C1 is the *last* condition to move: the
generator will not clear it while any contributing edge is unratified or while
no valid freeze exists. Run today it refuses on both, which is correct.

Then repoint the two code pins it names on exit:
`display_gate.py` (`REGISTRY_CURRENT`) and `dashboard.py` (`REGISTRY`).

## Step 6 — The gate

```bash
./.venv/Scripts/python.exe -c "
from pathlib import Path
from hyp04_supply_chain_hedge.display_gate import evaluate_gate
from hyp04_supply_chain_hedge.make_freeze_draft import validate_freeze
rec = validate_freeze(Path('Live Signal Engine/HYP04_FREEZE_DRAFT_<date>.json'))
d = evaluate_gate(eligible_event_count=len(rec.eligible_event_ids), freeze=rec)
print('OPEN' if d.open else 'CLOSED', d.denials)"
```

---

## What an open gate does and does not license

The governing document is explicit: **"reaching a threshold licenses *looking*,
not *concluding*."** 193 is a governance eligibility floor, not a power
calculation, and no power calculation may be performed using observed results.

An open gate means a measurement may be **reported**. It is not a finding, not
a validated strategy, and not a claim that supply-chain transmission exists.

## One thing left unresolved, on purpose

`HYP04_EDGE_VERIFICATION_2026-09-08.md` measures how many eligible events
postdate the last filing that named each counterparty — 38 of NVDA→MSFT's 42,
and JBL→BB's edge rests on a single filing. P3 checks only
`as_of_date <= event_date`; nothing checks the relationship was still current.

**No currency rule is proposed here.** Adopting one after seeing which edges it
cuts is precisely what the analysis locks exist to prevent. It is recorded as a
`SCIENTIFIC_DECISION` for a dated lock, and it would cut the sample below the
floor.

---

*Nothing in this document is evidence about supply-chain transmission. No target
value, `beta_h`, horizon or direction has been computed for HYP-04, and none may
be displayed while the gate is closed.*

*Nothing here constitutes investment advice, a solicitation, or a representation
that any approach is profitable.*
