# GST Prospective Hypothesis Registry — v1.10 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.10.json)
**Authored:** 2026-08-31 · **Decisions taken:** 2026-08-29 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.9.json` (sha256 `e7c0b3b746382b0e…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **This version settles two SPECIFICATIONS that v1.9 left open by name.** No
> hypothesis is reclassified, the 193-anchor-event threshold is unchanged, the
> anchor universe is byte-identical, every eligible-event counter stays zero,
> and the display gate stays **CLOSED, C4 MET, four denials**.
> **Nothing has been measured.**

---

## 1. Two dates, deliberately kept apart

The owner decided both questions on **2026-08-29**, the same day the finding
that recorded them as *open* was written. This version was authored on
**2026-08-31**. Collapsing the two would make a decision look contemporaneous
with its own declaration, so the JSON carries `decisions_taken_on` alongside
`authored_at_utc`.

## 2. The anchor-event rule — an SEC renumbering is not a filer

`HYP04-ANCHOR-EVENT-RULE-v1`: the 8-K results item is selected by **the
numbering in force on the report date.**

| era | results item |
|---|---|
| before **2003-03-28** | none exists — Item 5 or Item 7, same as every unrelated 8-K |
| **2003-03-28 … 2004-08-22** | **Item 12** |
| from **2004-08-23** | **Item 2.02** |

Selecting on Item 2.02 alone let SEC Release 33-8400's 2004 renumbering decide
which anchor events exist. That is the same defect this project already refused
once, when a filer's **print format** was deciding membership.

**NKE is the case that makes it concrete:** zero Item 2.02 filings inside its
2002-08-14 → 2004-07-30 membership span, and **six** Item 12 filings. Its zero
was the renumbering and nothing else.

Effect: **321 → 342** candidate anchor events, **306 → 324** with a resolved
release session. Both are still *candidate* counts.

**Measured first, adopted second.** The 2026-08-29 calendar published both
totals side by side and adopted neither. Passing `accept_legacy_item_12=False`
still reproduces the superseded rule exactly, so that artifact stays
*reproducible*, not merely archived.

**The legacy code is bounded in BOTH directions.** Item 12 did not exist before
2003-03-28 and stopped existing on 2004-08-23; accepting a bare `12` outside
that window would not be era-aware, just *wider*. The first draft did exactly
that and was caught by this version's own `code_disagreements()` guard — not by
any filing, because there are no out-of-era occurrences in the corpus. A guard
written while the data happens to be clean is the cheapest kind there is.

## 3. The peer target window — day 0 leaves the baseline

`HYP04-PEER-TARGET-WINDOW-v1`. The reference window now ends at
**`anchor_day − 1`**. It used to end **at** `anchor_day` — the session the
anchor's release is *attributed* to, which for a BMO release is out before the
open and for an AMC release is the next session. Either way the peer's return
that day can already carry the transmission being measured, and it was sitting
in the baseline that transmission is measured against.

**The direction of this change is favourable, and that is stated.** Removing a
contaminated session lowers the baseline and *raises* the measured log-ratio.
A change in the favourable direction is exactly the kind this project's rules
exist to stop being made after the fact.

**It is legitimate only because nothing has been measured.** No shock, no peer
response, no target value from production data exists, so there is no outcome it
could have been chosen to favour. It was taken *before* closes were collected
for precisely that reason, and it will never be this cheap again.

Only the **endpoint** moved — the length stays 20 sessions, so the robustness
comparison is not confounded by a length change as well. The day-0-inclusive
window is registered as the **robustness specification** and reproduces the
superseded arithmetic exactly.

**Data cost: one extra close per (peer, event)** — 41 → 42. The emitted request
spans the wider window, so it satisfies the robustness variant too and no second
collection round is needed. Deciding this after collection would have cost one.

`peer_returns.coverage_for_event` slices the same window from the same constant.
If it did not, P5 would certify pairs the target then returns `NaN` for, and the
denial would point at the window instead of at the data.

## 4. The return basis — a gap, not a change

`anchor_shock` accepts returns and never computes them, so **simple vs log was
never stated anywhere.** Found while planning the collection, not by anything
failing — at daily scale the two differ in the third decimal, which is why it
would never have surfaced as a bug and why it has to be written down.

Fixed as **log**, matching `peer_returns`, which is the other half of every pair
this shock is joined to. Both legs use it: a log anchor return against a simple
benchmark return would put a small systematic wedge in every excess return,
largest exactly on the big-move days that carry the signal.

## 5. No immovable field moved, and no exception was claimed

```python
SPECIFICATION_FIELDS_THIS_VERSION_MAY_MOVE = ()   # EMPTY
```

v1.9 needed an exception because it moved `required_eligibility_class`. v1.10
needs none: both changes are **new keys**, and `IMMOVABLE_HYP04_FIELDS` contains
neither. The guard runs unweakened over every field, and the generator refuses
outright if this tuple is ever non-empty.

Nothing was added to `unresolved_analysis_decisions`. A new *unresolved* entry
there would flip **C4 to NOT MET** and produce a fifth denial for a decision that
is not pending. These are measurement specifications, and v1.9 already settled
where those belong: the registry, declared from the code.

`peer_price_data_policy` is **unchanged**. The anchor-side source decision does
not amend it — that policy governs the **peer** side, and it still requires a
survivorship-bias-free peer source that has not been selected.

## 6. The generator refuses to outrun the code

`code_disagreements()` refuses to write while the repository has not already
implemented what v1.10 would declare — the era rule *and* its era bounds, the
offset constant, `reference_offset` on all four call sites, agreement between
the target's window and peer coverage's, a request span that covers both
specifications, and the declared return basis. The code landed first and the
registry followed. It earned its keep on the first run.

## 7. What this does not do

- **It measures nothing.** No shock, no peer response, no target value.
- **It creates no eligible anchor event.** `minimum_eligible_events` is still
  **193 anchor events**. C2 still counts zero.
- **It moves no gate.** C1, C3 and C5 deny exactly as before; C4 stays MET.
- **v1.9 remains on disk unchanged**, including the day-0-inclusive window this
  version replaces. A superseded version is allowed to be wrong.

## 8. Still open

- **The peer price source** — a survivorship-bias-free one. The repo has
  *measured* that the provider it used for peer closes returns zero rows for
  ODP across its entire history, so this is a known failure, not a worry.
- **The C5 linkage map**, still two curated draft rows.
- **C2 and C3 move together or not at all.** `display_gate.current_decision()`
  passes a literal `eligible_event_count=0`, and the gate cross-checks that
  count against the freeze record's event ids. A computed shock artifact cannot
  move C2 on its own, by design.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
