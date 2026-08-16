# Ticker-Alias Amendment — 2026-08-16

**Narrow, additive identity-reconciliation amendment. Created AFTER an identity collision was
discovered in the retrieved snapshot, but BEFORE any final selection was computed or recorded.**

That ordering is the point of this file, and it is stated plainly rather than implied: the collision
had to be seen before it could be described, so this amendment cannot claim to predate retrieval.
What it does predate is **selection**. The provisional selection produced during discovery was
deleted, and the complete candidate ledger is recomputed from scratch under this amendment.

**No attention, price, earnings, performance, market-value, weight, or outcome data informed this
amendment.** The only inputs are two security identifiers and the issuer name printed in the
snapshot's own name column.

---

## 1. The two existing frozen rules are unchanged

| File | SHA-256 (LF) | Status |
|---|---|---|
| `PRE_RETRIEVAL_SELECTION_RULE.md` | `6911726c077bab02f994f29adddd6bc5930e4dc17c53c1b6245c944196761cde` | **UNCHANGED — byte-for-byte** |
| `PRE_RETRIEVAL_SOURCE_AMENDMENT_2026-08-16.md` | `bf88f2261e1b6a6983a3db07b72b4c9d3274032e5332e4519cbfbf3ccab0d6bd` | **UNCHANGED — byte-for-byte** |

Neither is edited, superseded, or reinterpreted. Normalization (R4), issuer deduplication (R5),
permitted exclusions (R6), prohibited inputs (R7), the canonical hash string (R8), lowercase hex
(R9), `(digest, canonical_ticker)` ordering (R10), first-26 selection (R11), the 50-ticker total
(R13) and the no-backfill rule (R14) all continue to apply exactly as frozen.

## 2. The collision this amendment resolves

| | |
|---|---|
| **OEF source identifier** | `BRKB` |
| **Canonical project identifier** | `BRK-B` |
| **Issuer name in the snapshot** | `BERKSHIRE HATHAWAY INC CLASS B` |
| **Reason** | Both identifiers represent **Berkshire Hathaway Inc. Class B**. This is **identity reconciliation, not a scientific exclusion and not an outcome-informed selection decision.** |

Why the frozen rules could not resolve it: R4 converts *the provider's share-class separator* to the
repository convention, but this provider emits **no separator at all** — zero of the 101 equity
identifiers contain `.`, `-` or a space. Turning `BRKB` into `BRK-B` requires *inserting* a
separator and knowing `BRK` is the root and `B` the class letter. R5 could not rescue it either,
because the locked 24 is a ticker list carrying no issuer names, so an issuer match can only be made
on ticker equality — and `BRKB ≠ BRK-B`.

## 3. The frozen alias map

Exactly this map, for this proposal, and nothing else:

```json
{"BRKB": "BRK-B"}
```

**No other alias may be inferred, added, or silently normalized.** If any other unresolved identifier
mismatch appears, **stop and report** rather than extending this map.

## 4. Where the alias is applied

The alias is applied to the source identifier **before** every downstream step, so that one security
is one identity everywhere:

1. before comparison with the locked 24;
2. before issuer deduplication;
3. before candidate hashing;
4. before uniqueness counting.

## 5. Audit visibility

Both identifiers survive in the candidate ledger — the original `source_ticker` and the resulting
`canonical_ticker` — together with an explicit `alias_applied` flag, so the transformation is fully
visible and independently checkable. Nothing is rewritten in place.

## 6. Required disposition of BRKB

Because canonical `BRK-B` is **already among the locked 24**:

- source `BRKB` is classified **`ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION`**;
- it is **excluded from the addition pool**;
- it is **never hashed as a new candidate**.

## 7. Recomputation, not repair

The complete candidate ledger is recomputed from scratch. The first 26 eligible canonical candidates
are selected under the previously frozen hash rule. **No ticker is inserted manually.** A candidate
that was rank 27 before may enter only if independent recomputation shows it is rank 26 now — and
that is a mechanical consequence of removing an ineligible entry, not a backfill. R14 still forbids
replacing any selected ticker that later fails F5, access, eligibility or data quality.

## 8. Required post-conditions

- exactly **24** preserved locked tickers, in their existing order;
- exactly **26** mechanically selected additions;
- exactly **50** unique canonical tickers;
- exactly **50** unique **securities** — no issuer or security represented twice under two spellings;
- no manual backfill.

## 9. Scope

This amendment produces a **proposal**. It does not activate anything, does not modify the production
24-ticker constant, does not resolve F5, does not run Google Trends, does not screen an earnings
event, does not register an event, does not begin collection, does not inspect an outcome, and does
not alter any HYP-01 statistical rule.
