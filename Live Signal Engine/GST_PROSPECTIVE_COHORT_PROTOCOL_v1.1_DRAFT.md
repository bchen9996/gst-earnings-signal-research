# GST Prospective Multi-Event Cohort Protocol — v1.1 (DRAFT)

**Status:** Draft. Authored 2026-08-09 (UTC), **before the first candidate investor-relations page was inspected**.
**Canonical machine-readable form:** `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.1.json` — a mechanical test enforces agreement.
**Supersedes:** `GST_PROSPECTIVE_COHORT_PROTOCOL_v1.0_DRAFT.md` and its JSON, **prospectively only**. Both v1.0 files are preserved **byte-for-byte** and are never rewritten.

---

## 1. What changed, and only that

**The single methodological addition in v1.1 is the screening cadence.**

v1.0 said pending candidates are "re-screened on a fixed cadence" — and then never defined it. That is a real gap, not a wording nit: an undefined cadence is an opening for discretion, and a sweep run whenever it feels useful is a sweep whose *timing* can be shaped by what one expects to find. Defining it after the first sweep would be defining it with knowledge of what the sweep returned.

So it is fixed **here**, before the first candidate lookup.

Everything else is carried forward unchanged: the locked 24-ticker universe, the collection window (2026-09-01 … 2027-05-31), the target of ≥ 60 registered events, the five-XNYS-session lead rule, inclusion rules INC-1…INC-10, the permitted official-source types, every disposition, the prohibited exclusion reasons, the append-only amendment rules, the blinding prohibitions, the relationship to the v0.2 completeness tiers, the analysis separation, and the display gate.

**Nothing decided under v1.0 is re-decided under v1.1.** v1.0 remains the record of what the rules were before the cadence existed.

## 2. The screening cadence

| | |
|---|---|
| **Initial sweep** | immediately after the v1.1 commit is pushed, over the full locked 24-ticker universe |
| **Recurring sweep** | **every Monday at 09:00 America/Chicago** |
| **Missed sweep** | if a scheduled sweep cannot run because of a **documented technical failure**, it runs on the **next available calendar day** and the delay is recorded with its cause — **never silently skipped**, never back-dated |

### 2.1 Who stays on the cadence

- **Every pending candidate**, until it is enrolled or receives a terminal disposition.
- **Every already-enrolled event**, until its pre-event anchor begins — **solely** to detect official date/time amendments.

An enrolled event's recheck may confirm the official source still says what it said, or surface an issuer change to be handled by the v1.0 append-only amendment rules. It may **never** revisit enrollment itself.

### 2.2 Re-screening is screening

Re-screening uses **exactly** the v1.0 permitted inputs and the v1.0 blinding prohibitions. Nothing about being a re-screen rather than a first screen relaxes either.

### 2.3 No unscheduled re-screens

**No unscheduled re-screen may be triggered by** attention · price · volatility · news · options · earnings results · perceived interestingness.

A re-screen happens because the calendar says so, never because something looked worth another look. That is the whole point of fixing the cadence in advance.

### 2.4 The target does not stop enrollment

**Reaching 60 registered events does not stop enrollment.** The target is a coverage floor; the cadence continues across the whole collection window, and later events are handled by the existing extension-cohort rules rather than by ending collection early.

### 2.5 Changing the cadence

A cadence change requires a **new dated protocol version written before the sweep it would affect**. It is never an in-place edit and never a mid-stream adjustment.

## 3. One disposition text, repointed

`PENDING_OFFICIAL_DATE_UNAVAILABLE` previously pointed at the undefined "fixed cadence". It now points at the cadence defined in §2. **What the disposition means is unchanged** — only the dangling reference is resolved.

## 4. Still no candidates

`screening_rows` is still empty in this version. v1.1 is published **before** the first official investor-relations page is inspected, so the cadence cannot have been shaped by what the first sweep turns out to find. The commit history is the evidence: the cadence commit precedes every piece of screening evidence.
