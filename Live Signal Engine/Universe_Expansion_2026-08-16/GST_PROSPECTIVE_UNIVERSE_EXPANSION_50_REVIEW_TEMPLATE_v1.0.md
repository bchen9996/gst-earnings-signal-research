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

### 1a. Source authenticity

Is the publisher what it claims to be — **BlackRock / iShares**, the fund issuer — and was the file
obtained from the download link the official product page itself publishes?

- Finding: `PENDING`
- Notes:

### 1b. Historical raw-byte hash verification

The raw holdings file is **deliberately not tracked by Git**, because it carries prohibited numeric
holdings fields. `GST_OEF_RAW_SOURCE_EVIDENCE_MANIFEST_v1.0.json` records its exact filename,
repository-external location, byte count (17,200), SHA-256, retrieval timestamp, as-of date and
official URL, and confirms it remains available to an authorized reviewer.

Recorded: raw SHA-256 `3d85de45d0f07bbd830a6431ed671ffbb8266e7aa7bef4cfa360e06df125f892`,
as-of **Aug 13, 2026**.

**This check has NOT been performed by the proposal's author and must not be.** It is left
`PENDING` deliberately: the author hashing their own file proves nothing to a reviewer.

### Run this yourself

The file is **not** committed — it carries prohibited numeric holdings fields. It is retained
repository-external at:

```
C:\Users\hakur\AppData\Local\Temp\claude\C--Users-hakur-Downloads-gst-event-dossiers-worktree\9ed6a2ef-3f2f-4009-8985-c14d79c34f37\scratchpad\quarantine_oef\OEF_latest_holdings_raw.csv
```

Hash it **without opening it**. The commands below read bytes and print a digest; neither displays
any holdings value:

Windows (PowerShell):

```powershell
Get-FileHash -Algorithm SHA256 "C:\Users\hakur\AppData\Local\Temp\claude\C--Users-hakur-Downloads-gst-event-dossiers-worktree\9ed6a2ef-3f2f-4009-8985-c14d79c34f37\scratchpad\quarantine_oef\OEF_latest_holdings_raw.csv"
```

Linux / macOS / Git Bash:

```bash
sha256sum "<path to OEF_latest_holdings_raw.csv>"
```

**Expected:**

```
3d85de45d0f07bbd830a6431ed671ffbb8266e7aa7bef4cfa360e06df125f892
```

Byte count must also be **17,200**.

### Access

The file sits on the workstation that performed the retrieval and is available to an authorized
reviewer by local access or repository-external transfer. **If you cannot obtain those exact bytes,
mark this check `UNRESOLVED` — not `APPROVE`.**

### Two paths, and they are not equivalent

- **Direct** — hash the quarantined file above. This verifies the *historical bytes* exactly and is
  the only path that satisfies this check.
- **Indirect** — re-download from the official URL. The fund republishes daily, so a *different*
  hash is **expected** and is not by itself a discrepancy. This verifies the *source*, not the
  historical bytes, and is **not** sufficient for this check.

- Finding: `PENDING`
- Verification path used: `PENDING`
- Byte count observed: `PENDING`
- Digest observed: `PENDING`
- Notes:

### 1c. Sanitized identity projection verification

Does `GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json` contain **only** `Ticker`, `Name` and `Asset Class`,
with all twelve other columns dropped and no numeric holdings value present anywhere? Does its
recorded SHA-256 match, and does re-running the sanitizer over the raw file reproduce it?

- Finding: `PENDING`
- Notes:

### 1d. Acceptance of the OEF proxy

**This is a judgment call, not a checkable fact, and it is yours.** The candidate pool came from a
**fund's holdings file**, not from S&P DJI's canonical constituent list. A fund's holdings may differ
from index membership through sampling, timing, corporate actions, cash positions and derivative
overlays.

S&P DJI's own export was unobtainable — its security controls blocked access and were **not**
circumvented. Do you accept a fund-holdings file as an identity-only proxy for the S&P 100 investable
universe for this purpose, or does the proposal fail on this ground regardless of everything else?

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

### 5. Economic-issuer deduplication and the corrected grouping rule

**A previous version of this proposal was rejected on exactly this point.** It used a general regex
stripping a trailing `CLASS/CL/SER/SERIES` designator, which is not the case-and-punctuation-only
normalization frozen rule R5 specifies. That general behaviour has been **removed entirely**.

It is replaced by an exact frozen source-name map covering only the two names present in this dated
snapshot:

```json
{"ALPHABET CLASS A": "ALPHABET", "ALPHABET CLASS C": "ALPHABET"}
```

applied immediately before R5 deduplication and nowhere else. Every other name falls back to R5's
sentence verbatim, with no suffix removed. An unlisted share-class group makes the build **stop**.

Verify: that no general suffix stripping remains in the grouping path; that exactly two source names
resolve to `ALPHABET`; that the map is applied only before R5; that `GOOG` is excluded under R5.1
because `GOOGL` is locked; and that the amendment recording this was created **before** the corrected
selection was computed.

Note the independently verified consequence: **`GOOG`'s exclusion does not move the rank-26
boundary** — its digest sorts below rank 26 — and the corrected recomputation produced an **identical**
selected 26. The defect was a real rule inconsistency, not a wrong outcome.

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
