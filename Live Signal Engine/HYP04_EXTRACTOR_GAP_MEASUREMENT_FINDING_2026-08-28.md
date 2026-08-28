# HYP-04 finding — the extractor gaps cost a real anchor: NIKE / Foot Locker (2026-08-28)

**Status: FINDING.** The display gate reads **CLOSED, C4 MET, 4 denials** before
and after. Registry v1.6 is **not edited** and no membership is changed by this
document. Nothing here is evidence about supply-chain transmission.

---

## 1. What was done

The two extractor gaps recorded on 2026-08-27 —
[the possessive denominator and the closed verb set](HYP04_EXTRACTOR_POSSESSIVE_DENOMINATOR_FINDING_2026-08-27.md)
— were **measured against the full corpus for the first time**, using the
response cache built the same day. The measurement reads 1,250 cached filings
and makes **zero SEC requests**.

It does not modify the extractor. Candidate widened patterns are applied by
monkeypatch for one pass and restored; both passes run the **full pipeline**,
so what is reported is admissions that survive every structural gate and the
denominator classifier, not raw regex hits.

## 2. The result

**Five newly admitted disclosures. Four are fabrications. One is real.**

| Ticker | Captured as | Verbatim source | Verdict |
|---|---|---|---|
| NVDA ×3 | `Hong Kong` 23% | "Revenue from billings to China, including Hong Kong, **was** 24% of our revenue" | **fabrication** — geography |
| GPC | `Office Products Group` 16% | "sales from the Company's Office Products Group **were** approximately 16% of the Company's net sales" | **fabrication** — the filer's own segment |
| NKE | `Inc` 11% | "revenues derived from **Foot Locker, Inc.** represented 11% of the Company's consolidated revenues" | **REAL, and mis-parsed** |

Nothing was **lost** by the widening, which is the other half of the check: a
widening that drops an existing disclosure is not a widening.

### The gates are verb-sensitive, and that was not known

`Hong Kong` and the self-segment construction are **exactly the fabrication
classes the round-two gates were built to reject** on 2026-08-27. They reappear
because those gates were only ever exercised against the accepted verb set.
Reached through a copular construction (`was`, `were`), `GEOGRAPHIC_CONSTRUCTION`
and `INTERNAL_SUBJECT` do not fire.

This generalises the 2026-08-27 lesson. That day established that widening the
**corpus** raises the false-positive rate with no code change. This establishes
that widening the **anchor** does the same thing, for the same reason: the gates
have only ever been measured on the prose the anchor already admitted.

## 3. NIKE is a missing member, and the miss is systematic

Foot Locker, Inc. is disclosed by NIKE as a named customer at or above 10% of
**consolidated revenues** across three fiscal years:

| Fiscal year | Share of consolidated revenues | Disclosed in |
|---|---|---|
| FY2000 | **12.4%** | 10-K of 2002-08-14 |
| FY2001 | **11.8%** (11–12% as later restated) | 10-K of 2002-08-14, 2003-08-07 |
| FY2002 | **10.9% / 11%** | 10-K of 2002-08-14, 2003-08-07, 2004-07-30 |

The 2002-08-14 filing states it outright: *"Foot Locker, Inc. is our largest
single customer."* The 2004-07-30 filing states the other side just as plainly —
*"in 2004 and 2003 the Company did not have a significant customer that
accounted for more than 10% of consolidated revenues"* — so the relationship
crossing back below the threshold is disclosed too, not inferred.

**Two independent defects hide it, and both must be fixed to see it:**

1. **The denominator.** "the Company's consolidated revenues" is an
   apostrophe-s possessive, so the anchor never matches — §1 of the 2026-08-27
   finding.
2. **The party phrase.** `PARTY_TAIL` recognises `sales|revenues|purchases|
   shipments **to** X`. NIKE writes "revenues **derived from** Foot Locker,
   Inc.", which is not in that set, so even once the anchor matches the party
   resolves to the bare suffix `Inc`. **This is a third gap, not previously
   recorded.**

Fixing only the denominator yields `Inc` — a bare legal suffix, itself a
fabrication. The two must be fixed together or not at all.

### What this does to the under-inclusion claim

Registry v1.6 says under-inclusion was measured and found to be two, both
QCOM segment revenues correctly excluded. The 2026-08-27 finding already
corrected that to *"unclassified denominators among matched anchors"*. This
finding supplies the number that correction implied but could not give:
**under-inclusion is not zero. It costs at least one real anchor.**

## 4. What is NOT claimed

- **NKE is not added to any universe by this document.** Doing so requires the
  fixes implemented, the corpus re-derived, and a new dated registry version.
- **The interval is indicative, not derived.** On the evidence above it would
  open at **2002-08-14** and close at **2003-08-07**, the filing that no longer
  qualified. That must come out of `derive_universe_point_in_time`, not out of
  this table.
- **No claim that NKE is the only missing member.** This measurement widened
  two constructions. The party-phrase gap in §3 was found by accident, through
  a single mis-parse, and has not itself been measured across the corpus.

## 5. Why the recommended ordering has changed

The 2026-08-27 finding proposed: populate the cache → widen both layers →
re-measure → author v1.7 if membership moves. **The measurement is now done and
it changes that order.** Widening as proposed would admit four fabrications for
one real relationship, and the real one would arrive mis-parsed.

Revised, and none of it needs another SEC request:

1. **Make the structural gates verb-insensitive**, and re-measure the four
   fabrications above to confirm they are rejected through *every* verb form.
2. **Add the `derived from` party construction**, and measure that gap across
   the corpus in its own right.
3. **Then** widen the denominator and verb set.
4. Re-run the full exhaustive fabrication enumeration — every named ≥10%
   disclosure in all 1,250 filings, not a spot check. A wider anchor reaches
   prose no gate has been tested against, which is the whole lesson of §2.
5. Only if membership still moves, author registry v1.7.

**The gate is unaffected at every step.** Declaring a universe creates no
eligible anchor event; C2 counts zero regardless of who is in it.

## 6. Provenance

Measured 2026-08-28 against `.edgar_cache` (1,250 filings, 229 MB, gitignored),
which reproduces `HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-27_v4.json`
exactly — 1,239 primary-document and 11 full-submission retrievals, zero
failures — at **zero requests**. The measurement harness is not committed; it
monkeypatches module globals, which is acceptable for a one-off measurement and
not acceptable as repository code. Every number above is reproducible from the
cache by re-running it.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
