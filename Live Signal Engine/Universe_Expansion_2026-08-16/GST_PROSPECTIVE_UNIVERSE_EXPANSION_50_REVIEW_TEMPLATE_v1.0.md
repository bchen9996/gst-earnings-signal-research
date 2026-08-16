# Independent Review — Proposed Universe Expansion 24 → 50

> **Every field below is blank or `PENDING`. No reviewer identity, decision, or approval has been
> recorded, and none may be filled in by the proposal's author.**

**Reviewer:** `PENDING`  ·  **Review date:** `PENDING`  ·  **Confirmation:** `PENDING`

**Overall disposition:** `PENDING` — choose exactly one, and only after completing the checks below:

- [ ] `APPROVE`
- [ ] `REQUEST_CORRECTION`
- [ ] `UNRESOLVED`

*No option is preselected. An unchecked template is the correct state until a second researcher works
through it independently.*

---

## How to verify without trusting the proposal

Each check below is written so it can be answered from the committed artifacts and a fresh
computation, not from the proposal's own summary. Where a check needs a command, it is given.

Reproduce the whole selection:

```
python tools/universe_expansion/select_universe_50.py \
  --snapshot "Live Signal Engine/Universe_Expansion_2026-08-16/GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json" \
  --out-dir <a scratch directory>
```

Then diff your output against the committed proposal.

---

### 1. Authoritative-source authenticity

Is the source what it claims to be — the dated official iShares OEF holdings snapshot published by
BlackRock/iShares, and **not** an S&P DJI constituent file, aggregator, encyclopedia, or generated
list?

- Finding: `PENDING`
- Notes:

### 2. Source hash

Does the raw file you download match the recorded SHA-256, or can you account for the difference
(the fund republishes daily, so an as-of drift is expected and must be stated, not hand-waved)?

Recorded: raw SHA-256 `3d85de45d0f07bbd830a6431ed671ffbb8266e7aa7bef4cfa360e06df125f892`, as-of
**Aug 13, 2026**.

- Finding: `PENDING`
- Notes:

### 3. Original 24 preserved

Are positions 1–24 of the final universe exactly `LOCKED_24_TICKER_UNIVERSE`, in the same order, with
nothing removed, renamed or replaced?

- Finding: `PENDING`
- Notes:

### 4. Candidate normalization

Is normalization confined to uppercase, trim, separator convention and preserved class identifiers —
with no symbol invented and no two distinct securities merged?

- Finding: `PENDING`
- Notes:

### 5. Economic-issuer deduplication

Is the ALPHABET decision correct (`GOOG` excluded because `GOOGL` is already locked)? Is the
issuer-key construction — case/punctuation normalization plus removal of a trailing share-class
designator **for grouping only, never applied to the ticker** — acceptable to you? *This is the one
mechanical step the frozen rule required but did not spell out; it is flagged here deliberately.*

- Finding: `PENDING`
- Notes:

### 6. Every exclusion

Are all five exclusions justified under the frozen permitted grounds, and is each traceable to a
specific rule? (`GOOG` R5.1; `XTSLA`, `MSFUT`, `ESU6`, `USD` R6.2.)

- Finding: `PENDING`
- Notes:

### 7. Hash inputs and digests

Does every eligible candidate's `hash_input` equal `"GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" +
canonical_ticker` exactly, and does its SHA-256 match the recorded lowercase 64-hex digest?

- Finding: `PENDING`
- Notes:

### 8. Rank order

Are candidates sorted ascending by `(digest, canonical_ticker)`, with no omitted candidate ranking
above a selected one?

- Finding: `PENDING`
- Notes:

### 9. The selected 26

Are the 26 additions exactly the first 26 in that order — no substitutions, no manual insertions?

- Finding: `PENDING`
- Notes:

### 10. Final 50

Does the final universe contain exactly 50 unique tickers **and** 50 unique securities, with no
issuer represented twice under two spellings?

- Finding: `PENDING`
- Notes:

### 11. The ticker-alias amendment

`BRKB` → `BRK-B`. Do you accept this as identity reconciliation rather than a selection decision? Do
you accept that it was created **after** the collision was discovered but **before** final selection,
and that it was informed only by two identifiers and an issuer name? Do you agree the frozen map must
stay exactly `{"BRKB": "BRK-B"}` with no other alias inferred?

*Note its material effect: `BRKB` would otherwise have been selected at rank 10, putting the same
security in the universe twice. Removing it promoted `NFLX` from rank 27 to rank 26 mechanically.*

- Finding: `PENDING`
- Notes:

### 12. No prohibited variable was used

Can you find any evidence — in the sanitized snapshot, the selection code, or the ledger — that
attention, price, return, volatility, volume, liquidity, spread, options, market capitalization,
index weight, earnings, analyst data, news, sentiment, outcome, strategy performance, site
accessibility, earnings-date availability, expected eligibility, anticipated effect or subjective
familiarity influenced any inclusion, exclusion or rank?

- Finding: `PENDING`
- Notes:

### 13. No replacement / backfill rule

Is the no-backfill rule stated unambiguously, and is there no mechanism by which a later F5, access,
eligibility or data-quality failure could cause a replacement from rank 27 onward?

- Finding: `PENDING`
- Notes:

### 14. No research-state change

Are the production universe constant, cohort protocol, effective lock, D1–D16 amendment, signoff
template, registry, screening rows and all protected hashes byte-identical? Is F5 still `OPEN` and
collection still `BLOCKED`?

- Finding: `PENDING`
- Notes:

---

## Reviewer's overall statement

`PENDING`

## If `REQUEST_CORRECTION`, what specifically must change

`PENDING`

## If `UNRESOLVED`, what evidence would resolve it

`PENDING`
