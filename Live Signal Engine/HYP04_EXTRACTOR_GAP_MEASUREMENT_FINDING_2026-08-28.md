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

---

## AMENDMENT — 2026-08-28: the fix was implemented, and §2's diagnosis was wrong

**§2 said the structural gates are verb-sensitive. That is false**, and it was
checked rather than assumed only after it had been committed. Running the same
sentences with an ACCEPTED verb shows today's extractor produces the identical
fabrications:

| Construction | with `was` | with `accounted for` |
|---|---|---|
| "billings to China, including Hong Kong" | not matched | **`Hong Kong` admitted** |
| "sales from the Company's Office Products Group" | not matched | **segment admitted** |

The gates were never verb-sensitive. **The constructions were simply not
covered by any gate.** They are absent from the corpus because the filings
carrying them happen to use copular verbs the anchor did not match — the code
was clean **by accident**, and any filing writing the same construction with an
accepted verb would have produced a fabrication at any point in this project.

**§3's attribution was wrong too.** It blamed `PARTY_TAIL` for lacking
`derived from`. The actual defect is the **comma before the legal suffix**:
`"Foot Locker, Inc."` captured as `Inc`, because the name continuation stops at
the comma and the match, anchored to the end of the window, keeps only the
suffix. Corpus-wide this had mis-parsed three *existing* counterparties —
`Inc` for Ingram Micro (AAPL), `Caremark RX` truncated (MCK), `Ltd` for Hyundai
(QCOM).

### What was implemented

1. `PARTY_TAIL` and `APPOSITIVE_NAME` accept a comma before the legal suffix.
2. `OWN_BUSINESS_UNIT` — an appositive naming the party as the filer's own
   division/subsidiary.
3. `UNIT_HEAD_PARTY` — a party whose **head noun** is a unit type. Head noun
   only: `Lenovo Group Limited` is a real Intel counterparty and survives.
   Measured corpus-wide, this rejects exactly the five GPC segments and no real
   counterparty.
4. `INCLUDING_APPOSITIVE` — `including X` makes X an instance of the measured
   category, so the share belongs to the category.
5. `STATED_YEAR` recognises `year ended <Month> <day>, <year>`.
6. The anchor admits possessive denominators and copular/equivalence verbs.

**Item 5 is the one that mattered most.** Without it the widening would have
opened an NKE interval at **2004-07-30** — on the strength of a comparative
about FY2002, in the very filing stating that 2004 and 2003 had *no* customer
above 10%. The widening made that sentence matchable for the first time, so a
pre-existing hole in the stale gate became reachable.

### The result: membership is UNCHANGED

Re-derived over the full corpus, offline, at zero requests:

**Six members, nine intervals, identical to registry v1.6** — same tickers,
same dates, same counterparties, `registry_grade=True`. **No v1.7 is
required.**

**NKE did not become a member**, and §3 of this finding overstated what the fix
would recover. Its genuinely qualifying disclosures are all of the form
*"represented 11% and 12%, **respectively**, of the Company's consolidated
revenues"* — a multi-year construction still unsupported. The one simple-form
sentence is the 2004 comparative, now correctly rejected. So NKE remains a
**known missing member**, and the reason is now precisely identified rather
than attributed to the wrong cause.

### What actually improved

- three real counterparties stopped being mis-parsed
- four fabrication routes closed, three of which were **live defects in the
  published extractor**, not artefacts of the widening
- a stale-comparative hole closed before it could create a false interval

2,096 checks over 27 suites, 0 failures. Gate **CLOSED, C4 MET, 4 denials**.

---

## AMENDMENT — 2026-08-28 (later): "respectively" implemented; membership moves BOTH ways, and v1.6 contains an error

The multi-year `respectively` construction is now supported, and staleness is
measured against the **period of report** rather than the filing date. The two
changes are inseparable: pairing percentages to years by position is only safe
if the reporting year can be identified exactly.

**Membership moved, and not only by addition.**

| | |
|---|---|
| **NKE ADDED** | 2002-08-14 → 2004-07-30, Foot Locker Inc, 10.9% |
| **MCHP REMOVED** | its v1.6 interval rests on a stale comparative |

### MCHP was never entitled to membership

Both filings that produced it disclose a figure for a year **other than the one
they report on**:

| Filed | Period | What it says |
|---|---|---|
| 2013-05-30 | FY2013 | "…approximately 10% of our net sales **in each of fiscal 2012 and fiscal 2011**" |
| 2014-05-30 | FY2014 | "…approximately 10% of our net sales **in fiscal 2012**" |

Neither states a ≥10% concentration for its own reporting year. The
filing-date window is two years wide — it must be, to avoid rejecting the
reporting year of a calendar-year filer — and that slack admitted a FY2012
figure into a FY2013 filing.

**This directly contradicts registry v1.6's own companion**, which records the
fiscal-period imprecision as a stated limitation and says it *"changes no
membership here."* It did. It manufactured a member.

The same correction removes NVDA/Celestica, which v1.6 also names as a known
comparative that "still passes". It was not an interval opener, so NVDA is
unaffected.

### Verification

Re-derived offline, zero requests, `registry_grade=True`. Corpus diff against
the previous run: **two removals, zero additions.** The exhaustive enumeration
gives 62 qualifying disclosures over 23 distinct ticker-counterparty pairs,
every one a real company — no geography, no segment, no bare legal suffix.
**Zero fabrications.**

### THE REPOSITORY IS NOW IN A DIVERGED STATE, deliberately and visibly

The extractor derives a universe that the published registry v1.6 does not
describe: **AAPL, CTSH, INTC, MCK, NKE, NVDA** against v1.6's AAPL, CTSH, INTC,
MCHP, MCK, NVDA.

**No test catches this**, and that is not an oversight in the tests — it is the
consequence, now realised, of a property this project chose on purpose: the
registry suites re-derive from the **stored corpus artifact**, so they verify
that the published artifact matches the corpus it was built from, not that it
matches today's code. The divergence was predicted in
[the 2026-08-27 finding](HYP04_EXTRACTOR_POSSESSIVE_DENOMINATOR_FINDING_2026-08-27.md),
§4, as the reason not to change the extractor without authoring a version.

**Resolving it requires registry v1.7**, which is a governed act and has not
been taken. Until then this document is the record that the divergence exists
and is understood, rather than being discovered later as a contradiction.

The display gate is unaffected: **CLOSED, C4 MET, 4 denials**. Membership is
not eligibility, and C2 counts zero regardless of who is in the universe.
