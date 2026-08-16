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

Recompute everything from the committed sources:

```
python tools/sector_composition/classify_universe_sectors.py \
  --sources <dir containing sec_sic_by_ticker.json, sec_company_tickers.json, Siccodes12/> \
  --out-dir <scratch dir>
```

Then diff against the committed classification and audit JSON.

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

Do the FINAL_50-vs-OEF percentage-point differences recompute? Does the leave-one-ticker-out range
recompute? Confirm no subset search was performed and no alternative universe was generated.

- Finding: `PENDING`
- Notes:

### 8. Language discipline

Confirm the audit never calls a distribution representative, balanced, acceptable, unacceptable,
biased or statistically significant, and asserts no accept/reject conclusion.

- Finding: `PENDING`
- Notes:

### 9. The substantive judgment — yours, not the audit's

The audit reports, descriptively: expansion produced **lower** concentration; the largest category in
the final 50 is `BusEq` at **24.0%** (12 of 50); all 12 FF categories are represented; and every
category sits within **±3.0 percentage points** of the OEF proxy pool.

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
