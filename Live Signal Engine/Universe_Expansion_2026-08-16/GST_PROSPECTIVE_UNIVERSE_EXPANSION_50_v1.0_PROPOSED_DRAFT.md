# Proposed Prospective Universe Expansion - 24 to 50 (PROPOSED, NOT ACTIVE)

> ## PROPOSAL ONLY | NOT ACTIVE | NOT AN S&P DJI CONSTITUENT FILE
> ## CURRENT 24 REMAIN OPERATIVE | F5 REMAINS OPEN | COLLECTION REMAINS BLOCKED
> ## NO PRODUCTION QUERY CHANGED
> ## NO TICKER WAS SELECTED USING ATTENTION, PRICE, EARNINGS, OUTCOME OR PERFORMANCE INFORMATION

The production universe constant `LOCKED_24_TICKER_UNIVERSE` is **unchanged**. Nothing here is
activated by merging this proposal.

## Source

**The dated official iShares OEF holdings snapshot, used as an identity-only proxy for the S&P 100
investable universe.** It is **not** the index provider's canonical constituent list, and no document
in this proposal describes it as one.

| | |
|---|---|
| Publisher | BlackRock / iShares (fund issuer) |
| Download | `https://www.ishares.com/us/products/239723/ishares-s-p-100-etf/latest-holdings.csv` |
| Retrieved | 2026-08-16T05:32:28Z, HTTP 200 |
| Source as-of | **Aug 13, 2026** |
| Raw SHA-256 | `3d85de45d0f07bbd830a6431ed671ffbb8266e7aa7bef4cfa360e06df125f892` |
| Raw file | quarantined **outside** version control |

S&P Dow Jones Indices' own export was unobtainable: its security controls blocked access. **They were
not retried, evaded, proxied around, or circumvented.**

Only three identity columns were kept - `Ticker`, `Name`, `Asset Class`. **Twelve columns were
dropped**, including Market Value, Weight (%), Notional Value, Quantity, Price and FX Rate. No
prohibited value was read, printed, persisted or used.

## Governance chain

| Step | Artifact | Frozen before | SHA-256 |
|---|---|---|---|
| 1 | `PRE_RETRIEVAL_SELECTION_RULE.md` | any constituent retrieval | `6911726c077bab02f994f29adddd6bc5...` |
| 2 | `PRE_RETRIEVAL_SOURCE_AMENDMENT_2026-08-16.md` | any OEF request | `bf88f2261e1b6a6983a3db07b72b4c9d...` |
| 3 | `PRE_SELECTION_ALIAS_AMENDMENT_2026-08-16.md` | any final selection | `5faabac1e5a6b77a8dc3cbb894c66794...` |

Steps 1 and 2 are byte-for-byte unchanged. Step 3 was created **after** an identity collision was
discovered and **before** final selection - stated plainly rather than implied, because the collision
had to be seen before it could be described. It was informed by two identifiers and an issuer name,
and by nothing else.

## Selection rule

```
SHA256( UTF8( "GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" + canonical_ticker ) )
```

lowercase hexadecimal, sorted ascending by `(digest, canonical_ticker)`, first **26** selected.
**No human judgment affected which 26 were selected.**

## Dispositions - every source row has exactly one

| Disposition | Count |
|---|---|
| Source rows | 105 |
| Excluded - not operating-company common equity (R6.2) | 4 |
| Excluded - malformed identifier (R6.3) | 0 |
| Excluded - duplicate economic issuer (R5) | 1 |
| Already in the locked 24 (incl. 1 after alias normalization) | 12 |
| Eligible candidates | 88 |
| **Selected** | **26** |
| Not selected | 62 |

## Exclusions

| Source | Name | Rule |
|---|---|---|
| `GOOG` | ALPHABET CLASS C | R5.1 issuer already represented in the locked 24 by GOOGL |
| `XTSLA` | BLK CSH FND TREASURY SL AGENCY | R6.2 not operating-company common equity |
| `MSFUT` | CASH COLLATERAL MSFUT USD | R6.2 not operating-company common equity |
| `ESU6` | S&P500 EMINI SEP 26 | R6.2 not operating-company common equity |
| `USD` | USD CASH | R6.2 not operating-company common equity |

## Ticker-alias decision

`BRKB` -> `BRK-B` - both identifiers represent **Berkshire Hathaway Inc. Class B**. Identity
reconciliation, not a scientific exclusion and not an outcome-informed decision. Because `BRK-B` is
already locked, source `BRKB` was classified `ALREADY_LOCKED_AFTER_ALIAS_NORMALIZATION`, excluded
from the addition pool, and **never hashed as a candidate**. The frozen map is exactly
`{"BRKB": "BRK-B"}`; no other alias may be inferred.

## The selected 26

| Rank | Ticker | Name | Digest |
|---|---|---|---|
| 1 | `CAT` | CATERPILLAR INC | `00923d14d25a18bfd0c25e03...` |
| 2 | `MMM` | 3M | `03bd772c826765918c53a182...` |
| 3 | `BA` | BOEING | `0be7a13d15800fa5c6ed44fe...` |
| 4 | `COF` | CAPITAL ONE FINANCIAL CORP | `0e77410332e70a1529b5915a...` |
| 5 | `NEE` | NEXTERA ENERGY | `14c9ebfcd510319267daaf43...` |
| 6 | `HONA` | HONEYWELL AEROSPACE INC | `169465d8d34cfbc10d69765b...` |
| 7 | `CL` | COLGATE-PALMOLIVE | `18ada6431b182c5ebad6a06a...` |
| 8 | `DUK` | DUKE ENERGY CORP | `1db9a5e2f05d459c4ce8cb8d...` |
| 9 | `HD` | HOME DEPOT | `1ec734a9b103c73c42f181d4...` |
| 10 | `GS` | GOLDMAN SACHS GROUP INC | `23c478a14ed86dc0a214c845...` |
| 11 | `INTU` | INTUIT | `23db247c813ccfbc2210ddd0...` |
| 12 | `BMY` | BRISTOL MYERS SQUIBB | `28020d6cd37389677188e119...` |
| 13 | `BNY` | BANK OF NEW YORK MELLON CORP | `2d3b706d20a933c617c6785b...` |
| 14 | `AMT` | AMERICAN TOWER REIT | `2ec27f8d0a6f7bc3f806c837...` |
| 15 | `ACN` | ACCENTURE PLC CLASS A | `32d5670797b5f6679ff9a387...` |
| 16 | `LRCX` | LAM RESEARCH | `3383b5a6b8318563ea983c2f...` |
| 17 | `MS` | MORGAN STANLEY | `33ad3521570e3b6d238431e7...` |
| 18 | `TMO` | THERMO FISHER SCIENTIFIC INC | `35dc95a906857eb3d8ee5bdd...` |
| 19 | `ISRG` | INTUITIVE SURGICAL INC | `36908983e30d8cb01211bccd...` |
| 20 | `T` | AT&T INC | `3cc2c10b8ca3838fb0ad4ff2...` |
| 21 | `BLK` | BLACKROCK | `3e15d4a3c18ab04668deb79c...` |
| 22 | `LMT` | LOCKHEED MARTIN CORP | `40a7168cecffa9db93f5a2de...` |
| 23 | `AXP` | AMERICAN EXPRESS | `4ad8bbc276aad2f7b300a94f...` |
| 24 | `LLY` | ELI LILLY | `4c03b05a52c8b2811cefc51c...` |
| 25 | `WMT` | WALMART INC | `51170adfa62d729da7321f01...` |
| 26 | `NFLX` | NETFLIX | `5267fc36c0f570bbe42ce5a2...` |

Rank boundary: #25 `WMT` < #26 `NFLX` < #27 `SO`, strictly increasing.

**NFLX entered at rank 26 mechanically.** It was rank 27 before `BRKB` was removed as an
already-locked security; removing an ineligible entry shifts the tail up by one. That is a
consequence of a smaller pool, **not** a backfill and **not** a manual insertion.

## Final proposed universe - 50

Positions 1-24 are the existing locked tickers **in their existing order**; 25-50 are the selected
additions **in deterministic hash order**.

```
["AAPL", "ABBV", "ADBE", "AMZN", "BKR", "BRK-B", "CTSH", "DELL", "DVN", "GME", "GOOGL", "GPN", "INTC", "LDOS", "MSFT", "NCLH", "NKE", "QCOM", "SBUX", "STZ", "SYK", "TSLA", "TTWO", "UAL", "CAT", "MMM", "BA", "COF", "NEE", "HONA", "CL", "DUK", "HD", "GS", "INTU", "BMY", "BNY", "AMT", "ACN", "LRCX", "MS", "TMO", "ISRG", "T", "BLK", "LMT", "AXP", "LLY", "WMT", "NFLX"]
```

50 entries, 50 unique tickers, 50 unique securities, 0 issuers represented twice.

## No replacement, ever

A selected ticker is **never** replaced because it later fails F5, has an ambiguous search construct,
lacks an accessible issuer page, produces missing data, fails an eligibility gate, or contributes no
usable event. Those outcomes are recorded honestly. Backfilling from rank 27 onward is prohibited.

## What this proposal does not do

It does not resolve F5, does not establish construct validity, does not run Google Trends, does not
screen an earnings event, does not register an event, does not begin collection, does not inspect any
outcome, does not alter D1-D16, does not change DELL's registration, does not modify the production
universe constant, and does not constitute external preregistration.
