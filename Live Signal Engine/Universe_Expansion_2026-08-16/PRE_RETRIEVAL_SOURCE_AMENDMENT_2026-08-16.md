# Source-Scope Amendment — 2026-08-16

**Additive amendment to the frozen selection rule. Written and hashed BEFORE any iShares OEF holdings
file is requested or inspected.**

At the moment this file is written, the OEF holdings snapshot has not been retrieved and its contents
are unknown to the author. Its hash and timestamp are recorded so this amendment cannot be claimed to
have been fitted to the names it later admits.

---

## 1. The original rule is preserved, not rewritten

| | |
|---|---|
| **File** | `PRE_RETRIEVAL_SELECTION_RULE.md` |
| **SHA-256 (LF-normalized)** | `6911726c077bab02f994f29adddd6bc5930e4dc17c53c1b6245c944196761cde` |
| **Created** | 2026-08-16T05:21:06Z |
| **Status** | **UNCHANGED — byte-for-byte.** This amendment does not edit, supersede, or reinterpret it. |

Every rule R1, R4–R14 continues to apply **exactly as frozen**: preservation of the existing 24,
normalization, economic-issuer deduplication with locked-class precedence, the four permitted
exclusions, the exhaustive prohibited-input list, the canonical hash string, lowercase hexadecimal,
`(digest, canonical_ticker)` ordering, first-26 selection, the 50-ticker total, and the no-backfill
rule.

**This amendment changes exactly one thing: the permitted source of the candidate pool (rule R2).**

## 2. Why the amendment is needed

Rule R2 required a dated S&P 100 constituent snapshot from an authoritative S&P Dow Jones Indices
source. That source proved inaccessible from this environment. Every route was tried once and
recorded:

| Route (all 2026-08-16T05:23Z) | Result |
|---|---|
| `https://www.spglobal.com/spdji/en/indices/equity/sp-100/` | HTTP **403** |
| `https://www.spglobal.com/spdji/en/idsexport/file.xls?selectedModule=Constituents&selectedSubModule=ConstituentsFullList&indexId=340` | HTTP **403** |
| `https://www.spglobal.com/spdji/en/` (site root) | HTTP **403** |
| `https://us.spindices.com/indices/equity/sp-100` (legacy host) | **DNS does not resolve** |
| Same S&P 100 URL rendered by a real browser engine | HTTP 200, but served an error page |

The browser attempt returned a 2,070-byte page (SHA-256
`e8e8b3e332fd6b19658f4ab4e4ae4bc29768bb0a47f0bc075880ef648975b465`) reading **"Error — Security
Controls Triggered."**

**That is an access control the site operator deliberately imposed. It was not retried, evaded,
proxied around, or circumvented in any way, and it will not be.** The network itself was healthy:
other hosts responded normally in the same session.

## 3. New permitted source — an identity-only proxy

Permitted, in addition to the sources in R2:

> **The dated official iShares OEF holdings snapshot, used as an identity-only proxy for the S&P 100
> investable universe.**
>
> Product page: `https://www.ishares.com/us/products/239723/ishares-sp-100-etf`
> Publisher: BlackRock / iShares (the fund issuer).

### 3.1 What this source is NOT

**It is not the index provider's canonical constituent list.** It is a fund's published holdings
file. It may differ from the S&P 100 index membership through sampling, timing, corporate actions,
cash positions and derivative overlays.

**No document produced under this amendment may describe it as "the official S&P 100 constituent
list."** The required phrasing is: *the dated official iShares OEF holdings snapshot, used as an
identity-only proxy for the S&P 100 investable universe.*

### 3.2 What may be taken from it

**Security identity only.** Exactly three fields may be extracted:

1. ticker / security identifier;
2. issuer / security name;
3. asset class or sector-type field, used **solely** to distinguish ordinary equity from cash,
   derivatives and other non-equity rows.

### 3.3 What is forbidden

Weight, market value, notional value, shares or quantity held, price, price change, return,
performance, yield, fundamentals, exchange-rate columns, and every other numeric holdings field.
The prohibited-input list in the original rule R7 continues to apply in full: no attention, price,
return, volatility, volume, liquidity, spread, options, market capitalization, index weight, earnings
surprise, analyst data, news, sentiment, outcome, strategy performance, issuer-site accessibility,
earnings-date availability, expected eligibility, anticipated effect, or subjective familiarity may
influence inclusion, exclusion, or rank.

**Non-identity fields from the raw file must not be printed to the operator, analyzed, cited,
committed, or used in any way.** The raw download is quarantined outside version control; only a
sanitized identity-only projection enters the repository.

## 4. Unchanged mechanics

Normalization, issuer deduplication, locked-class precedence, permitted exclusions, the canonical
hash string `"GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" + canonical_ticker`, lowercase hexadecimal
digests, `(digest, canonical_ticker)` ascending ordering, first-26 selection, and the no-backfill
rule are all **exactly as frozen in the original rule**. This amendment adds no new exclusion ground
and no new ranking input.

## 5. Stop condition

**If the OEF snapshot cannot yield a complete, auditable identity list without manually inspecting
prohibited fields, stop and report.** Do not guess a column meaning, do not eyeball values to infer a
schema, and do not proceed on a partial or ambiguous extraction.

Likewise, if any step would require interpretation beyond the frozen normalization and exclusion
rules, stop and report before selecting.

## 6. Scope

This amendment produces a **proposal**. It does not activate anything, does not resolve F5, does not
run Google Trends, does not screen an earnings event, does not register an event, does not begin
collection, does not inspect an outcome, and does not alter any HYP-01 statistical rule or the
production universe constant.
