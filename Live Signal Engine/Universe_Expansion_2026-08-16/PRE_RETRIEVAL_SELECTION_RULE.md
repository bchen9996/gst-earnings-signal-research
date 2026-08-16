# GST Prospective Universe Expansion 24 → 50 — SELECTION RULE, FROZEN BEFORE RETRIEVAL

**This artifact is written and hashed BEFORE any S&P 100 constituent list is retrieved or inspected.**
At the moment of writing, the constituent names are unknown to the author of this file. Its SHA-256
and creation timestamp are preserved in the final audit precisely so that the rule cannot be claimed
to have been fitted to the names it later selects.

Nothing in this rule references any outcome, attention, price, or market quantity.

---

## R1. Preserve the existing 24

All 24 currently locked tickers are preserved **exactly**: not removed, renamed, reordered, or
replaced. They occupy positions 1–24 of the expanded universe in their existing order.

Authoritative source of the 24: `gst_market_response/constants.py`, symbol
`LOCKED_24_TICKER_UNIVERSE`.

## R2. Authoritative constituent snapshot

Obtain a dated S&P 100 constituent snapshot from an authoritative S&P Dow Jones Indices source.
No search engine, aggregator, encyclopedia, or model-generated list may serve as canonical evidence.
A search engine may be used **only** to locate the official S&P page; its snippets and cached copies
are not evidence.

## R3. Candidate pool

The candidate pool is every canonical ticker symbol in that snapshot that is **not already** among
the locked 24.

## R4. Normalization (repository compatibility only)

Applied to provider symbols, and to nothing else:

1. uppercase;
2. trim surrounding whitespace;
3. convert the provider's share-class separator to the repository's existing convention — the
   repository writes Berkshire Hathaway class B as `BRK-B`, so a provider `BRK.B` or `BRK B`
   normalizes to `BRK-B`;
4. preserve economically meaningful class identifiers (a class letter is never dropped).

Normalization may not merge two distinct securities and may not invent a symbol.

## R5. Economic-issuer deduplication (before selection)

1. If an issuer **already** has a share class among the locked 24, **all** of its other share classes
   are excluded from the candidate pool. (Concretely: an issuer represented by `BRK-B` or `GOOGL`
   contributes no further classes.)
2. Otherwise, if an issuer appears in the pool with more than one share class, retain **exactly one**
   by a deterministic outcome-blind rule: the **lexicographically smallest canonical ticker**.
3. Every duplicate-class decision and its rationale is recorded in the audit.

Issuer identity is established from the authoritative snapshot's own company-name field, normalized
for case and punctuation only.

## R6. Permitted exclusions — exhaustive

A candidate may be excluded **only** for:

1. duplicate economic issuer under R5;
2. not being operating-company common equity;
3. a malformed or unresolvable ticker identifier;
4. inclusion that cannot be established from the authoritative snapshot.

No other exclusion is permitted.

## R7. Prohibited selection and ranking inputs — exhaustive

None of the following may influence inclusion, exclusion, or rank:

Google Trends or any search-attention measure · price · return · volatility · volume · liquidity ·
spread · options availability or pricing · market capitalization · index weight · earnings surprise ·
analyst data · news · sentiment · any outcome · historical strategy performance · issuer website
accessibility · availability of a clean earnings date · expected eligibility · anticipated
statistical effect · subjective company familiarity.

## R8. Canonical selection score

```
SHA256( UTF8( "GST-HYP01-UNIVERSE-EXPANSION-2026-08-16|" + canonical_ticker ) )
```

The prefix is a fixed literal. The separator is a single `|`. No trailing newline, no padding, no
other field participates.

## R9. Digest representation

Lowercase hexadecimal, 64 characters.

## R10. Sort order

Eligible candidates are sorted by `(digest ascending, canonical_ticker ascending)`.
The ticker tiebreak is a formality against digest collision; it is specified so the order is total.

## R11. Selection size

The first **26** candidates in that order are selected.

## R12. Expanded universe composition

```
existing locked 24, in their existing order
+
selected 26, in deterministic hash order
```

## R13. Final size

Exactly **50** unique ticker symbols.

## R14. No replacement, no backfill

Once selected, a ticker is **not** replaced because it later fails F5, has an ambiguous search
construct, lacks an accessible issuer page, produces missing data, fails an eligibility gate, or
contributes no usable event. Those outcomes are recorded honestly. **They may never cause
backfilling from rank 27 onward.** Selecting a replacement on the basis of any such downstream
observation would make the universe outcome-dependent, which is exactly what this rule exists to
prevent.

---

## Scope limits of this expansion

This rule produces a **proposal**. It does not activate anything. It does not resolve F5, run Google
Trends, screen an earnings event, register an event, begin collection, inspect an outcome, or alter
any HYP-01 statistical rule. The production universe constant is not modified by the work this rule
governs.
