# Issuer-Grouping Interpretive Amendment — 2026-08-16

**Fourth additive amendment. Created in response to an independent review disposition of
`REQUEST_CORRECTION`.**

## 1. Exactly when this was created, stated plainly

This amendment was created:

- **after** the OEF snapshot was retrieved (2026-08-16T05:32:28Z);
- **after** the inconsistency described below was discovered — by independent review, not by the
  implementer;
- **after** an earlier selection had already been computed and recorded;
- **before** the corrected final selection was computed;
- using **security-identity information only** — two source company names and one issuer group key.
  **No prohibited research variable informed it**: no attention, price, return, volatility, volume,
  liquidity, spread, options, market capitalization, index weight, earnings, analyst data, news,
  sentiment, outcome, strategy performance, site accessibility, earnings-date availability, expected
  eligibility, anticipated effect, or subjective familiarity.

Nothing here is implied. The earlier selection existed before this amendment did, and the artifacts
recording it were **deleted from the branch** before recomputation so that no stale selection could
survive alongside the corrected one.

## 2. The three earlier frozen artifacts are unchanged

| File | SHA-256 (LF) | Status |
|---|---|---|
| `PRE_RETRIEVAL_SELECTION_RULE.md` | `6911726c077bab02f994f29adddd6bc5930e4dc17c53c1b6245c944196761cde` | **UNCHANGED** |
| `PRE_RETRIEVAL_SOURCE_AMENDMENT_2026-08-16.md` | `bf88f2261e1b6a6983a3db07b72b4c9d3274032e5332e4519cbfbf3ccab0d6bd` | **UNCHANGED** |
| `PRE_SELECTION_ALIAS_AMENDMENT_2026-08-16.md` | `5faabac1e5a6b77a8dc3cbb894c667948cbcbb8824e2f159e81b29ca2b30ffc6` | **UNCHANGED** |

None is edited, superseded, or reinterpreted. This file adds one narrowly scoped resolution.

## 3. The internal conflict in the frozen rule

Frozen rule **R5** contains two requirements that cannot both be satisfied as written.

**R5's substantive requirement** is economic-issuer deduplication, and it is explicit about the
intended outcome:

> *"If an issuer **already** has a share class among the locked 24, **all** of its other share classes
> are excluded from the candidate pool. (Concretely: an issuer represented by `BRK-B` or `GOOGL`
> contributes no further classes.)"*

**R5's operational sentence** restricts how issuer identity is derived:

> *"Issuer identity is established from the authoritative snapshot's own company-name field,
> normalized for case and punctuation only."*

Those conflict on the actual data. The snapshot's names are `ALPHABET CLASS A` (GOOGL) and
`ALPHABET CLASS C` (GOOG). **Case and punctuation normalization alone cannot group them** — they
differ in the letters `A` and `C`, which are neither case nor punctuation. Under the operational
sentence read strictly, the two rows are different issuers, `GOOG` is never excluded, and R5's own
worked example — that an issuer represented by `GOOGL` contributes no further classes — is violated
by the rule's own mechanism.

**The earlier implementation resolved this silently and wrongly.** It applied a general regular
expression, `\s+(CLASS|CL|SER|SERIES)\s+[A-Z]$`, to strip a trailing share-class designator before
grouping. That is not case or punctuation normalization. It was disclosed in the review template, but
**a disclosure does not make an implementation consistent with a frozen rule**, and the reviewer was
correct to treat it as blocking.

## 4. Resolution — an exact frozen map, not a general rule

This amendment resolves **only the identity actually observed in this dated snapshot**, by exact
source-name equality:

```json
{
  "ALPHABET CLASS A": "ALPHABET",
  "ALPHABET CLASS C": "ALPHABET"
}
```

An exact map is preferred over a suffix-removal regex on purpose: a regex is a *general rule* that
would silently group issuers nobody has examined, in this snapshot and in every future one. This map
groups exactly two known source names and nothing else.

### 4.1 Where it applies

The map is applied **immediately before R5 economic-issuer deduplication, and nowhere else.** It
never touches a ticker, never affects normalization, never affects hashing, never affects ordering,
and never affects selection except through R5's deduplication outcome.

### 4.2 Names not in the map

For any source name **not** listed above, issuer identity reverts to R5's operational sentence
exactly as frozen: the company-name field normalized for **case and punctuation only**. No suffix is
stripped. The general `CLASS|CL|SER|SERIES` suffix-removal behaviour is **removed entirely**.

### 4.3 Unlisted multi-class cases must stop

**No other issuer alias may be inferred.** If the snapshot contains any other set of rows that would
plausibly be share classes of one issuer and is **not** covered by this map, the build **stops and
reports** rather than proceeding.

That check is a *detector*, not a grouping mechanism: it looks for two or more rows whose names carry
a share-class designator and share a common base, and it **refuses** when it finds one outside the
map. It never merges anything on its own. Refusing is the correct behaviour because the alternative —
guessing — is precisely the defect this amendment exists to correct.

## 5. Audit visibility

The candidate ledger records, for every row, both the **original source name** and the **resolved
issuer key**, plus a flag showing whether the frozen grouping map was applied. Nothing is rewritten
in place, and a reviewer can confirm by inspection that exactly two rows were grouped.

## 6. Recomputation

The entire candidate ledger and the complete selection are recomputed **from scratch** under this
amendment. **The previously selected 26 are not manually preserved.** If the resulting list differs
from the earlier one, the difference is reported rather than reconciled, and whether `GOOG`'s
exclusion moves the rank-26 boundary is verified independently rather than assumed.

## 7. Scope

This amendment produces a **proposal**. It does not activate anything, does not modify the production
24-ticker constant, does not resolve F5, does not run Google Trends, does not screen an earnings
event, does not register an event, does not begin collection, does not inspect an outcome, and does
not alter any HYP-01 statistical rule.
