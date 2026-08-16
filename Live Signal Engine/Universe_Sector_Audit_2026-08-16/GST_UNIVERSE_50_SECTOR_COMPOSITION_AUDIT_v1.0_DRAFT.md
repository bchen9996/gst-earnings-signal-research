# Proposed 50-Ticker Universe — Sector-Composition Audit v1.0 (DRAFT)

> ## DESCRIPTIVE AUDIT ONLY | NO UNIVERSE CHANGE
> ## PROPOSED 50 REMAIN INACTIVE | PRODUCTION UNIVERSE REMAINS 24
> ## NO GST OR MARKET OUTCOME USED | F5 REMAINS OPEN | COLLECTION REMAINS BLOCKED
> ## NO CONCENTRATION THRESHOLD WAS INVENTED

No ticker was altered, reordered, replaced or removed. No selection was created, no quota
introduced, no alternative universe generated. The production universe remains the original 24.

## Denominators — stated before any figure

Every count below is reported against a named denominator, so that no percentage is quoted against
an undefined base.

| Denominator | Definition | Value |
|---|---|---|
| **Security** | one canonical ticker = one share class | — |
| **Issuer** | one official SEC CIK; all its share classes collapse to **one** equal-weight observation | — |
| Final 50, securities | the proposed universe as listed | **50** |
| Final 50, unique CIKs | verified, not assumed | **50** |
| OEF pool, source equity securities | equity rows in the identity snapshot, alias-normalized | **101** |
| **OEF pool, unique issuers** — the operative proxy denominator | grouped by SEC CIK | **100** |
| Union, unique canonical securities | final 50 ∪ OEF source securities | **113** |
| Union, unique CIKs | the same union at issuer level | **112** |
| Classification requests | final-50 records + OEF issuer records; the overlap between the two groups is counted in **both** | **150** |

**The `113` figure means unique canonical securities across the union of the final 50 and the
OEF source securities — not issuers, not classification requests.** At issuer level the same union
is **112**. Every one of the 113 securities resolved to an official SEC CIK and SIC, so
coverage is **113/113 securities and 112/112 issuers, with zero
`CLASSIFICATION_UNRESOLVED`.**

## Why the proxy pool is counted per issuer

The frozen pre-retrieval rule — **unchanged by this correction** — defines the proxy pool as every
eligible equity **issuer**. Counting share classes separately would give **Alphabet Inc.** (CIK `1652044`, `GOOG`, `GOOGL`) two equal-weight
observations while the final 50 gives every issuer exactly one, so the two sides of the comparison
would not be measured on the same denominator.

The pool is therefore grouped by **official SEC CIK**, after applying the frozen alias
`{"BRKB": "BRK-B"}` so that identity matching happens on the canonical ticker. Every security under one CIK
must carry the same SEC SIC **and** the same FF12 category, or the run **refuses and writes
nothing**. Each issuer contributes exactly one observation; every constituent security is preserved
in `source_securities`. A display ticker — the lexicographically smallest canonical ticker — is
used **for identification only and enters no count, share, HHI, entropy or difference.**

Exactly **1** issuer in the pool has more than one share class: **Alphabet Inc.** (CIK `1652044`, `GOOG`, `GOOGL`).

The final 50 was checked the same way rather than trusting the proposal's declaration: it contains
**50 unique CIKs for 50 securities**, so both sides are issuer-level. Had it contained a
duplicate issuer, the run would have stopped.

The rule file still uses the name `OEF_ELIGIBLE_PROXY_POOL`; the operative artifacts use
`OEF_UNIQUE_ISSUER_PROXY_POOL` to state that denominator explicitly. This is a naming correction, not a rule change.

## Method

Every category is derived **mechanically**: `ticker → CIK → SEC SIC → matched SIC interval → FF12
category`. There are no manual overrides and no name-based inference. A security whose SIC could not
be established from SEC data would be `CLASSIFICATION_UNRESOLVED` and would remain in the universe
unchanged — **none occurred.**

| | |
|---|---|
| Frozen rule | `PRE_RETRIEVAL_SECTOR_COMPOSITION_AUDIT_RULE_2026-08-16.md`, SHA-256 `5ce6a0f01ce7dec84bcf755ee655c4b9...`, created **2026-08-16T07:49:31Z** — before any retrieval, and unchanged by this correction |
| SEC identity + SIC | `sources/SEC_SIC_IDENTITY_SNAPSHOT_2026-08-16.json` — identity and SIC metadata only |
| FF12 definitions | `sources/FF12_SIC_DEFINITION_SOURCE_2026-08-16.txt` (official Kenneth R. French bytes) |
| Provenance manifest | `sources/GST_SECTOR_AUDIT_SOURCE_PROVENANCE_v1.0.json` |
| Weighting | **equal ticker weights only** — no market cap, OEF weight, price or return |

**Every input is committed.** Reproduction needs no network and no external scratch directory:

```
python tools/sector_composition/classify_universe_sectors.py
```

The classifier verifies each declared input against the provenance manifest's SHA-256 before
computing anything. A missing input, or any hash mismatch, is a **refusal**: it stops and writes no
output.

## Distribution by Fama–French 12 industry

Final-50 percentages are over **50 securities (50 issuers)**; OEF percentages are over
**100 unique issuers**.

| Cat | Industry | L24 | +26 | Final 50 | Final % | OEF issuers | OEF % | Δ pp |
|---|---|---|---|---|---|---|---|---|
| `NoDur` | Consumer Nondurables | 1 | 0 | 1 | **2.0%** | 5 | 5.0% | -3.0 |
| `Durbl` | Consumer Durables | 1 | 0 | 1 | **2.0%** | 2 | 2.0% | +0.0 |
| `Manuf` | Manufacturing | 2 | 5 | 7 | **14.0%** | 12 | 12.0% | +2.0 |
| `Enrgy` | Oil, Gas, and Coal Extraction an | 1 | 0 | 1 | **2.0%** | 3 | 3.0% | -1.0 |
| `Chems` | Chemicals and Allied Products | 0 | 1 | 1 | **2.0%** | 3 | 3.0% | -1.0 |
| `BusEq` | Business Equipment | 10 | 2 | 12 | **24.0%** | 22 | 22.0% | +2.0 |
| `Telcm` | Telephone and Television Transmi | 0 | 1 | 1 | **2.0%** | 4 | 4.0% | -2.0 |
| `Utils` | Utilities | 0 | 2 | 2 | **4.0%** | 3 | 3.0% | +1.0 |
| `Shops` | Wholesale, Retail, and Some Serv | 3 | 2 | 5 | **10.0%** | 8 | 8.0% | +2.0 |
| `Hlth` | Healthcare, Medical Equipment, a | 2 | 4 | 6 | **12.0%** | 12 | 12.0% | +0.0 |
| `Money` | Finance | 1 | 7 | 8 | **16.0%** | 16 | 16.0% | +0.0 |
| `Other` | Other | 3 | 2 | 5 | **10.0%** | 10 | 10.0% | +0.0 |

## Concentration metrics (equal ticker weights)

| Group | n | Largest | Largest share | Represented | Absent | HHI | Entropy | Effective categories |
|---|---|---|---|---|---|---|---|---|
| Legacy 24 (securities) | 24 | BusEq | 41.6667% | 9 | 3 | 0.225694 | 1.828466 | 6.224330 |
| Additions 26 (securities) | 26 | Money | 26.9231% | 9 | 3 | 0.159763 | 1.998138 | 7.375312 |
| Final 50 (securities = issuers) | 50 | BusEq | 24.0000% | 12 | 0 | 0.140800 | 2.145883 | 8.549585 |
| OEF proxy pool (unique issuers) | 100 | BusEq | 22.0000% | 12 | 0 | 0.126400 | 2.239874 | 9.392143 |

## Descriptive answers

**Did expansion increase or decrease industry concentration?** **Lower concentration.** HHI falls
from **0.225694** (legacy 24) to **0.140800** (final 50); effective number of categories rises
from **6.224330** to **8.549585**; the largest category's share falls from **41.6667%**
(`BusEq`) to **24.0000%** (`BusEq`).

**Which categories gained the most representation?** By count among the 26 additions:
`Money` +7, `Manuf` +5, `Hlth` +4, `BusEq` +2, `Other` +2, `Shops` +2, `Utils` +2, `Chems` +1, `Telcm` +1. Three categories absent from the legacy 24 — `Chems`, `Telcm`, `Utils` — are now
represented.

**Is the proposed 50 visibly dominated by one category?** The largest category is `BusEq` at
**24.0000%** (12 of 50). No accept/reject threshold was specified in this audit, so
this figure is reported without a verdict.

**Which categories are absent?** **None.** All 12 FF categories are represented in the final 50; the
legacy 24 was missing three and the 26 additions alone are missing three different ones.

**How far does the final 50 differ from the OEF issuer proxy pool?** Recomputed on the issuer
denominator, the largest absolute gap is **3.0 percentage points** (`NoDur`), so every
category sits within **±3.0 pp**. Overrepresented relative to the proxy: `BusEq` +2.0 pp, `Manuf` +2.0 pp, `Shops` +2.0 pp, `Utils` +1.0 pp.
Underrepresented: `NoDur` -3.0 pp, `Telcm` -2.0 pp, `Chems` -1.0 pp, `Enrgy` -1.0 pp. Identical: `Durbl`, `Hlth`, `Money`, `Other`.

## Sensitivity checks

- **Excluding unresolved:** identical — there are no unresolved records.
- **Legacy 24 vs additions 26:** the additions are themselves less concentrated (HHI
  0.159763 vs 0.225694) and led by `Money` at 26.9231%.
- **Final 50 vs OEF issuer proxy:** HHI 0.140800 vs 0.126400.
- **Leave-one-ticker-out (final 50):** largest-category share ranges
  **22.4490%–24.4898%**; HHI ranges **0.137026–0.146189**. No
  single ticker drives the result.

**No subset search was performed and no alternative universe was generated.**

## What this audit does not say

It does not call any distribution representative, balanced, acceptable, unacceptable, biased or
statistically significant — no frozen rule supports that wording, and this task deliberately froze no
concentration threshold. **No automated accept/reject threshold was specified.** Any decision to
retain, reject or redesign the universe is a separate human decision that must be made **without
consulting GST or return outcomes**.
