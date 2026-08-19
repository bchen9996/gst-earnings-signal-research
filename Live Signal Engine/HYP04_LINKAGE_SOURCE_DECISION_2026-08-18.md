# HYP-04 linkage source — decision record (2026-08-18)

**Decision:** the supply-chain teammate's automated linkage map is deprioritised. HYP-04 switches to a **hand-curated** linkage map.

**Status:** ingestion path built. **No curated data exists yet.** This record documents a change of approach, not the arrival of a map.

---

## What changed

| | Before | After |
|---|---|---|
| Intended source | teammate's automated mapping | hand curation against a fixed template |
| Availability | pending, unscheduled | template defined; **zero rows curated** |
| Registry v1.1 status | `does_not_exist` | **`does_not_exist` — unchanged** |
| Phase 1 blocker | the map | **still the map** |

Building a loader does not create data. Registry v1.1's required external measurement remains `does_not_exist`, HYP-04 remains `PREREGISTERED_MEASUREMENT_NOT_IMPLEMENTED`, and the result-display gate remains CLOSED on all five conditions.

## Why

The automated effort had no delivery date and no partial output to work against. Two independent EDGAR extractors were built in the interim to see whether the map could be derived from public filings instead; both produced near-zero usable edges:

- **Source A (ASC 280 concentration)** — 27 peers audited, **2 named counterparties (7.4%)**. ASC 280 requires disclosing that a ≥10% customer exists, not who it is, so ~93% of the universe withheld the name.
- **Source B (8-K material agreements)** — **0 edges** across 5 peers. 8-K "material agreements" are dominated by M&A, financing and employment, not supply relationships.

Neither is a substitute for a real map. Both remain in the tree as parallel *candidate* sources for cross-checking a curated map once one exists; neither is promoted, and `reconcile()` still has no merge path.

Hand curation trades throughput for provenance: each row carries a citation, a source type, an as-of date and a stated basis for that date — which is more than either automated source could supply, and directly satisfies Patch 11's as-of-date requirement.

## Decisions taken (repo owner, 2026-08-18)

**1. Option A — the loader lives alongside the placeholder.** `run_canary_audit.candidate_peer_universe()` is untouched and still returns the 27-peer sector-file-minus-anchors list. Rewiring it would have made the already-committed EDGAR coverage findings non-reproducible the moment a curated file landed.

**2. Direction is a fixed lookup, never parsed.** `relationship_type` is defined relative to the anchor:

| `relationship_type` | Stage 2 direction |
|---|---|
| `direct_supplier` | `supplier` |
| `direct_customer` | `customer` |
| `sector_competitor` | `not_applicable` |
| `loose_sector_neighbor` | `not_applicable` |

`relationship_direction_notes` is human context only — stored verbatim, **never read programmatically**. Prose-parsing is what produced the false edges in both EDGAR extractors; a curated map is the one place a human has already resolved that ambiguity, and re-deriving it from free text would discard the resolution.

**3. `as_of_date_basis` and `date_confidence` are inert.** Validated (non-null, valid enum) and stored, with no consumer wired. Deferred until something in Phase 2 needs them.

## Schema

15 columns, authoritative as of 2026-08-18, case-sensitive enums:

```
anchor_ticker, peer_ticker, relationship_type, relationship_direction_notes,
confidence, source_type, source_citation, source_url, as_of_date,
as_of_date_basis, date_confidence, notes_caveats, curated_by, curated_date,
review_status
```

A header-drift check compares the header row against this spec **in order** and reports a diff rather than absorbing it, so a future template revision surfaces instead of silently changing meaning.

## Validation policy

Matching the Phase 0 audit's style — classify and report, never crash, so one bad row cannot hide the rest of a file.

| Condition | Outcome |
|---|---|
| Missing/blank required field | **ERROR** — row rejected |
| Unknown enum value (case-sensitive) | **ERROR** — row rejected |
| Malformed date (not `YYYY-MM-DD`) | **ERROR** — row rejected |
| Duplicate anchor–peer pair | **ERROR** — row rejected |
| Anchor paired with itself | **ERROR** — row rejected |
| Ticker outside the known universe | **WARNING** — row kept |

The ticker check warns rather than fails on purpose: a curated map is *expected* to reach beyond the Phase 0 placeholder universe. That is much of the point of curating one, so an unfamiliar ticker is something to look at, not something to reject.

---

## UNRESOLVED — repo owner's call, not decided here

**Which anchor universe should the hand-curated map target?**

Two options, deliberately **not** chosen in this record:

- **HYP-01's frozen 24-ticker universe** — consistent with the rest of the project, and the anchor shocks are already available. But it is 24 anchors × N peers of manual curation before any Phase 1 work can begin.
- **A smaller first-pass scope** — a subset chosen to get a usable map sooner, accepting that the eventual N is lower and that the subset's selection basis would itself need recording to avoid a selection-bias problem.

This affects how long Phase 1 stays blocked and what the eventual `N_events` can reach against the 193-event floor, so it is a scope-and-timeline decision rather than a technical one. **Not guessed at here.**

## Also unresolved

- **The template files are not in the repo.** The schema above came from the owner directly; `HYP04_Linkage_Map_TEMPLATE_headers.csv` and the `.xlsx` working copy were not present at the time of writing. The loader validates against the stated spec and will report any drift when the real files land.
- **The `sector` column in `AllTickers_Sectors.csv` is unread** by this package. Flagged as a separate cleanup question, explicitly out of scope here.

---

*Nothing in this record constitutes evidence about supply-chain transmission, and no hedging edge is claimed.*
