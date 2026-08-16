# Independent Review — Proposed 50-Ticker Universe, Sector Composition

> **Every finding and disposition below is blank or `PENDING`. No reviewer identity, decision or
> checkbox may be filled in by the audit's author.**

**Reviewer:** `PENDING`  ·  **Review date:** `PENDING`  ·  **Confirmation:** `PENDING`

## Disposition — choose exactly one, only after completing the checks

- [ ] `ACCEPT_CURRENT_BROAD_PROPOSAL`
- [ ] `REQUIRE_STRATIFIED_REDESIGN`
- [ ] `REQUIRE_SECTOR_SPECIFIC_REDESIGN`
- [ ] `UNRESOLVED`

*No option is preselected. **This audit specified no concentration threshold**, so the disposition is
a human judgment about evidential sufficiency — not something the numbers decide on their own.*

---

## How to verify without trusting the audit

Every input is committed. Reproduction needs **no network and no external scratch directory**:

```
git archive --format=tar HEAD | tar -x -C <empty dir>     # clean LF export
cd <empty dir>
python tools/sector_composition/classify_universe_sectors.py --out-dir <scratch>
```

Then diff `<scratch>` against the committed classification and audit JSON. The inputs are:

| Input | Role |
|---|---|
| `sources/SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json` | ticker → CIK → SIC, identity only |
| `sources/FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt` | official Kenneth R. French definition bytes |
| `sources/FF12_SIC_INTERVALS_NORMALIZED_2026-08-16.json` | interval table derived from those bytes |
| `sources/GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json` | URL, retrieval time, byte count, SHA-256 for every input |
| `Universe_Expansion_2026-08-16/GST_OEF_IDENTITY_SNAPSHOT_2026-08-13.json` | OEF membership (already committed) |
| `Universe_Expansion_2026-08-16/GST_PROSPECTIVE_UNIVERSE_EXPANSION_50_v1.0_PROPOSED.json` | the 50 and the frozen aliases (already committed) |

The classifier verifies every input against the manifest's SHA-256 before computing. Delete an
input, or change one byte, and it must **refuse and write nothing** — try it.

### 0. Denominators

The audit reports figures against four distinct denominators: **50** final-50 securities (= 50
issuers), **101** OEF source securities → **100** unique issuers, **113** unique canonical
securities in the union, **112** unique CIKs in that union, and **150** classification requests.
Confirm no figure is quoted against an undefined or mismatched base, and that the proxy pool is
counted **per issuer** — not per security — on both sides of every comparison.

- Finding: `PENDING`
- Notes:

### 0b. Issuer grouping

Confirm: the issuer key is the official SEC CIK; the frozen alias `BRKB → BRK-B` is applied
**before** identity matching; `GOOG` and `GOOGL` fall in **one** CIK group counted **once**; every
constituent security is preserved in `source_securities`; the display ticker is the
lexicographically smallest canonical ticker and affects **no** metric; a CIK with conflicting SICs
or conflicting FF12 results is **refused**; and the final 50's 50 unique CIKs were **verified, not
assumed**.

- Finding: `PENDING`
- Notes:

### 1. The universe was not altered

Are the 50 tickers, their order, and the 24/26 split byte-identical to the merged proposal? Was
anything added, removed, replaced or reordered by this audit?

- Finding: `PENDING`
- Notes:

### 2. Authoritative sources

Is every classification traceable to **official SEC** identity/SIC data and the **official Kenneth R.
French** `Siccodes12` definitions? Can you find any aggregator, encyclopedia, model-generated sector
label, ETF weight or market capitalization used as evidence?

- Finding: `PENDING`
- Notes:

### 3. Mechanical derivation

Does every record's `trace` hold — `ticker → CIK → SEC SIC → matched interval → FF12` — with no
manual override and no name-based inference? Is `Other` applied only as the residual for SICs outside
categories 1–11?

- Finding: `PENDING`
- Notes:

### 4. Unresolved handling

This run produced **zero** unresolved records. Confirm that the code would classify a missing SIC as
`CLASSIFICATION_UNRESOLVED` rather than inferring one, and that no unresolved ticker would be deleted
or replaced.

- Finding: `PENDING`
- Notes:

### 5. Equal weights only

Confirm that no market capitalization, OEF holdings weight, price, return or volume enters any count,
percentage, HHI, entropy or difference. Every figure must use equal ticker weights.

- Finding: `PENDING`
- Notes:

### 6. Metric arithmetic

Do counts tie to their denominators? Do percentages sum to 100% within tolerance? Do HHI, Shannon
entropy and effective-category counts recompute independently from the counts?

- Finding: `PENDING`
- Notes:

### 7. Comparison and sensitivity

Do the FINAL_50-vs-OEF percentage-point differences recompute **against the 100-issuer
denominator**? Does the leave-one-ticker-out range recompute? Confirm no subset search was performed
and no alternative universe was generated.

- Finding: `PENDING`
- Notes:

### 8. Language discipline

Confirm the audit never calls a distribution representative, balanced, acceptable, unacceptable,
biased or statistically significant, and asserts no accept/reject conclusion.

- Finding: `PENDING`
- Notes:

### 9. The substantive judgment — yours, not the audit's

The audit reports, descriptively: expansion produced **lower** concentration; the largest category in
the final 50 is `BusEq` at **24.0000%** (12 of 50); all 12 FF categories are represented; and every
category sits within **±3.0 percentage points** of the OEF **unique-issuer** proxy pool (largest gap
`NoDur` −3.0 pp).

Whether that is adequate for HYP-01's clustered inference — and whether a stratified or
sector-specific redesign is warranted instead — is **not** answered here.

- Is the observed concentration acceptable for the study's purpose? `PENDING`
- Is a stratified redesign warranted? `PENDING`
- Is a sector-specific redesign warranted? `PENDING`
- If a threshold should exist, what should it be, and on what basis? `PENDING`

**Any threshold or redesign decision must be made without consulting GST attention data or return
outcomes.** Choosing a universe after seeing outcomes would make the sampling frame
outcome-dependent.

### 10. Research state

Confirm the production 24, protected artifacts, registry, locks and protocols are byte-identical,
that F5 remains OPEN and collection remains BLOCKED.

- Finding: `PENDING`
- Notes:

---

## Reviewer's overall statement

`PENDING`

## If a redesign is required, what specifically must change

`PENDING`

## If `UNRESOLVED`, what evidence would resolve it

`PENDING`
