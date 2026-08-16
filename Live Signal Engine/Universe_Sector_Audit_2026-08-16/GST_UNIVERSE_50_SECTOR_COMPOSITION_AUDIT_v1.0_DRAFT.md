# Proposed 50-Ticker Universe — Sector-Composition Audit v1.0 (DRAFT)

> ## DESCRIPTIVE AUDIT ONLY | NO UNIVERSE CHANGE
> ## PROPOSED 50 REMAIN INACTIVE | PRODUCTION UNIVERSE REMAINS 24
> ## NO GST OR MARKET OUTCOME USED | F5 REMAINS OPEN | COLLECTION REMAINS BLOCKED
> ## NO CONCENTRATION THRESHOLD WAS INVENTED

No ticker was altered, reordered, replaced or removed. No selection was created, no quota
introduced, no alternative universe generated. The production universe remains the original 24.

## Method

Every category is derived **mechanically**: `ticker → CIK → SEC SIC → matched SIC interval → FF12
category`. There are no manual overrides and no name-based inference. A security whose SIC could not
be established from SEC data would be `CLASSIFICATION_UNRESOLVED` and would remain in the universe
unchanged — **none occurred.**

| | |
|---|---|
| Frozen rule | `PRE_RETRIEVAL_SECTOR_COMPOSITION_AUDIT_RULE_2026-08-16.md`, SHA-256 `5ce6a0f01ce7dec84bcf755ee655c4b9...`, created **2026-08-16T07:49:31Z** — before any retrieval |
| SEC ticker→CIK | `company_tickers.json`, SHA-256 `2d3f4250a7b5c9c6e7ee4c3187dca1cf...` |
| SEC SIC per issuer | `data.sec.gov/submissions/CIK##########.json` — identity and SIC metadata only |
| FF12 definitions | Kenneth R. French `Siccodes12.zip`, definition file SHA-256 `55b51d1dc6939a570cd866824e9d49a9...` |
| Weighting | **equal ticker weights only** — no market cap, OEF weight, price or return |

**Classification coverage: 151/151 securities, zero unresolved.**

## Distribution by Fama–French 12 industry

| Cat | Industry | L24 | +26 | Final 50 | Final % | OEF n | OEF % | Δ pp |
|---|---|---|---|---|---|---|---|---|
| `NoDur` | Consumer Nondurables | 1 | 0 | 1 | **2.0%** | 5 | 5.0% | -3.0 |
| `Durbl` | Consumer Durables | 1 | 0 | 1 | **2.0%** | 2 | 2.0% | +0.0 |
| `Manuf` | Manufacturing | 2 | 5 | 7 | **14.0%** | 12 | 11.9% | +2.1 |
| `Enrgy` | Oil, Gas, and Coal Extraction an | 1 | 0 | 1 | **2.0%** | 3 | 3.0% | -1.0 |
| `Chems` | Chemicals and Allied Products | 0 | 1 | 1 | **2.0%** | 3 | 3.0% | -1.0 |
| `BusEq` | Business Equipment | 10 | 2 | 12 | **24.0%** | 23 | 22.8% | +1.2 |
| `Telcm` | Telephone and Television Transmi | 0 | 1 | 1 | **2.0%** | 4 | 4.0% | -2.0 |
| `Utils` | Utilities | 0 | 2 | 2 | **4.0%** | 3 | 3.0% | +1.0 |
| `Shops` | Wholesale, Retail, and Some Serv | 3 | 2 | 5 | **10.0%** | 8 | 7.9% | +2.1 |
| `Hlth` | Healthcare, Medical Equipment, a | 2 | 4 | 6 | **12.0%** | 12 | 11.9% | +0.1 |
| `Money` | Finance | 1 | 7 | 8 | **16.0%** | 16 | 15.8% | +0.2 |
| `Other` | Other | 3 | 2 | 5 | **10.0%** | 10 | 9.9% | +0.1 |

## Concentration metrics (equal ticker weights)

| Group | n | Largest | Largest share | Represented | Absent | HHI | Entropy | Effective categories |
|---|---|---|---|---|---|---|---|---|
| LEGACY 24 | 24 | BusEq | 41.7% | 9 | 3 | 0.2257 | 1.8285 | 6.22 |
| PROPOSED ADDITIONS 26 | 26 | Money | 26.9% | 9 | 3 | 0.1598 | 1.9981 | 7.38 |
| PROPOSED FINAL 50 | 50 | BusEq | 24.0% | 12 | 0 | 0.1408 | 2.1459 | 8.55 |
| OEF ELIGIBLE PROXY POOL | 101 | BusEq | 22.8% | 12 | 0 | 0.1283 | 2.2325 | 9.32 |

## Descriptive answers

**Did expansion increase or decrease industry concentration?** **Lower concentration.** HHI falls
from **0.2257** (legacy 24) to **0.1408** (final 50); effective number of categories rises
from **6.22** to **8.55**; the largest category's share falls from **41.7%**
(`BusEq`) to **24.0%** (`BusEq`).

**Which categories gained the most representation?** By count among the 26 additions:
`Money` +7, `Manuf` +5, `Hlth` +4, `BusEq` +2, `Utils` +2, `Shops` +2, `Other` +2, `Chems` +1, `Telcm` +1. Three categories absent from the legacy 24 — `Chems`, `Telcm`, `Utils` — are now
represented.

**Is the proposed 50 visibly dominated by one category?** The largest category is `BusEq` at
**24.0%** (12 of 50). No accept/reject threshold was specified in this audit, so this
figure is reported without a verdict.

**Which categories are absent?** **None.** All 12 FF categories are represented in the final 50; the
legacy 24 was missing three and the 26 additions alone are missing three different ones.

**How far does the final 50 differ from the OEF proxy pool?** Every category is within **±3.0
percentage points**. Overrepresented relative to the proxy: `Manuf` +2.1 pp, `Shops` +2.1 pp, `BusEq` +1.2 pp, `Utils` +1.0 pp, `Money` +0.2 pp, `Hlth` +0.1 pp, `Other` +0.1 pp, `Durbl` +0.0 pp. Underrepresented relative to
the proxy: `NoDur` -3.0 pp, `Telcm` -2.0 pp, `Enrgy` -1.0 pp, `Chems` -1.0 pp.

## Sensitivity checks

- **Excluding unresolved:** identical — there are no unresolved records.
- **Legacy 24 vs additions 26:** the additions are themselves less concentrated (HHI
  0.1598 vs 0.2257) and led by `Money` at 26.9%.
- **Final 50 vs OEF proxy:** HHI 0.1408 vs 0.1283.
- **Leave-one-ticker-out (final 50):** largest-category share ranges
  **22.45%–24.49%**; HHI ranges **0.1370–0.1462**. No single
  ticker drives the result.

**No subset search was performed and no alternative universe was generated.**

## What this audit does not say

It does not call any distribution representative, balanced, acceptable, unacceptable, biased or
statistically significant — no frozen rule supports that wording, and this task deliberately froze no
concentration threshold. **No automated accept/reject threshold was specified.** Any decision to
retain, reject or redesign the universe is a separate human decision that must be made **without
consulting GST or return outcomes**.
