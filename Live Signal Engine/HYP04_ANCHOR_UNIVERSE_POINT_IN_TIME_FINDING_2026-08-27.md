# HYP-04 finding — the anchor universe is filtered by present-day persistence (2026-08-27)

**Status: FINDING.** The display gate reads **CLOSED, C4 MET, 4 denials** before
and after. Registry v1.5 is **not edited** — it is published and append-only.
Nothing here is evidence about supply-chain transmission.

---

## 1. The observation

Registry v1.5, authored earlier today, declares the HYP-04 anchor universe as a
rule and derives one member, MCK. The rule is evaluated over an EDGAR screen.
That screen reads **only the newest 10-K per filer**:

```python
# edgar_linkage.extract_for_universe()
filing = client.latest_10k(cik)
```

So a company enters the universe only if its ≥10% named-customer concentration
is **still disclosed in its 2026 filing**. A company that disclosed one from,
say, 2014 through 2021 and no longer does is invisible to the screen, and
therefore invisible to the rule.

**v1.5 does not state this.** It pins the screen by name and sha256 and records
a `cutoff_date`, both of which are accurate; nothing in the document says the
screen looks at a single filing per company.

## 2. Why it matters — it is the failure v1.5 itself forbids, one level up

v1.5 added a top-level `peer_price_data_policy` whose whole point is:

> Peer-side price data availability is a **measurability** question, reported
> per pair. It is never a **membership** question.

The reasoning given there is that a price source which drops delisted
securities is survivorship-biased by construction, and letting it decide the
universe imports that bias into the preregistration.

The latest-filing-only screen does the same kind of thing on the anchor side.
It lets **persistence of the relationship to the present day** decide
membership. The companies it silently drops are those whose concentration
ended — and a concentration ends for reasons that are not independent of the
hypothesis: the customer was acquired, went private, went bankrupt, or the
supply agreement lapsed. Exactly the PKG/ODP situation, one level up.

This was not caught when v1.5 was written. The rule's six conditions were
scrutinised; the corpus they are evaluated against was not.

## 3. It also leaves membership and edges on different footings

The 2026-08-22 history walk did the point-in-time work properly for the curated
**edges**, walking every 10-K backwards to find the earliest disclosing filing:

| Edge | as_of_date | Basis |
|---|---|---|
| MCK → CVS | **2013-05-07** | earliest of 29 MCK 10-Ks examined |
| PKG → ODP | **2016-02-26** | earliest of 27 PKG 10-Ks examined |

`pair_eligibility` then enforces `edge.as_of_date < event_date` strictly, so
those dates decide how many anchor events an edge can serve. Back-dating them
was worth the walk precisely because the newest filing "covers almost no
history, even when the relationship it describes is a decade old" — the
`all_10ks()` docstring says so in as many words.

**Membership never got that treatment.** MCK's qualifying disclosure in the v1.5
artifact carries `as_of_date: 2026-05-08`, from the newest filing, while the
edge for the same relationship is dated 2013-05-07. Two dates for the same
underlying fact, produced by two different methods, in the same registry
version.

## 4. What is NOT claimed

- **v1.5's derived member is not wrong.** MCK does disclose CVS Health at 24% of
  consolidated revenue in the 10-K filed 2026-05-08. That is a correct
  application of the rule to the corpus it was given.
- **The rule is not wrong and does not change.** AU-1..AU-6, the 10% threshold
  and the consolidated-revenue denominator are ASC 280-10-50-42's and stay
  fixed. What changes is *when* the rule is evaluated, not *what it says*.
- **This is not evidence the universe is larger.** No historical screen has been
  run. It is entirely possible the point-in-time universe is also `{MCK}`. The
  claim here is narrower and checkable: **the current screen cannot answer the
  question, because it never looks at an older filing.**
- **PKG is unaffected either way.** Its disclosure is segment-denominated in
  2026 (58% of the Paper segment) and was segment-denominated in 2016 too —
  the 2016-02-26 filing reads "45% of our Paper segment sales revenue". It fails
  AU-4 across its history, not just today.

## 5. The correction, and its cost

Evaluate the unchanged rule against each 10-K in force over time, using the
history walk that already exists (`run_linkage_history.walk_ticker`, built on
`EdgarClient.all_10ks`). Two things must change first:

1. `walk_ticker` records only the counterparty NAMES per filing; it discards
   `concentration_pct` and the `concentration_basis` added today. The rule
   cannot be evaluated without them.
2. A history lacking the denominator must be **refused**, not scored — the same
   discipline `derive_universe` already applies, so a stale artifact cannot
   yield an empty universe that reads like a finding.

**The walk must cover all 51 frame members.** Walking only the 12 that show a
disclosure today would reintroduce precisely the bias being removed. That is
roughly 1,275 filings and ~1,400 SEC requests at the existing 0.15s spacing.

## 6. Options

1. **Run the point-in-time screen over the whole frame** and declare the result
   in a registry version. Fixes the underlying problem. Costs one long,
   staged, capped SEC run.
2. **Record the limitation and leave the universe as it is.** Honest, cheap, and
   leaves a known survivorship-flavoured filter inside a preregistered
   universe.
3. **Narrow the frame instead**, e.g. to companies known to have had
   concentrations. This is selection on the outcome and is rejected.

**Option 1 taken**, repo owner, 2026-08-27, staged pilot first.

---

**No gate moved.** C2 counts eligible anchor events, of which there are zero,
and this document changes no code, no registry and no decision.

---

## AMENDMENT — 2026-08-27: widening the corpus broke the attribution gates

The first full-frame point-in-time run was executed and its result is **not
adopted**. It is recorded here because what it exposed matters more than the
universe it produced.

> **This amendment SUPERSEDES the third bullet of section 4**, which reads "No
> historical screen has been run." That was true when section 4 was written
> earlier the same day and is false now. The bullet is left standing rather
> than edited, per the append-only rule -- but it is superseded, and a reader
> who stops at section 4 would be misled. The rest of section 4 stands: the
> rule still does not change, and v1.5's derived member is still a correct
> application of the rule to the corpus it was given.

Applying the unchanged rule across 1,239 filings from 51 companies produced
**7 members ever**: AAPL, CTSH, INTC, MCHP, MCK, NVDA, QCOM. Reading the
verbatim text behind all 14 qualifying disclosures, **five were wrong**:

| Extracted | The filing's actual words | What it is |
|---|---|---|
| `MCHP -> "DISTRIBUTION Distributors"` 60% | "**Distributors** accounted for 60% of our net sales" | the whole channel, not a party |
| `NVDA -> "Other Americas"` 75% | "sales to customers **outside of** the United States and Other Americas" | geography |
| `NVDA -> "Singapore"` 18% | "Singapore represented 18% ... **based upon customer billing location**" | geography |
| `QCOM -> "HTC"` 26% | "revenues from **Samsung Electronics and HTC** comprised 26%" | a pair, attributed to one |
| `CTSH -> "JPMorgan Chase"` 13.7% | a **2004** figure in a **2007** filing that says "No customer accounted for revenues in excess of 10% ... in 2006 and 2005" | superseded comparative |

**The cause is structural, not clerical.** The attribution gates were built on
2026-08-26 against 2026 filings, and were correct for them. Filing prose from
1996 to 2019 differs, so extending the corpus by twenty-five years raised the
false-positive rate without anything in the code changing. The gates did not
regress; the corpus outgrew them.

**The list-based gate is the one that failed.** `GEOGRAPHIC_PARTY` enumerates
place names and did not contain "Singapore". A list of places can never be
complete, so the four gates added in response match CONSTRUCTIONS instead:

| Gate | Rejects |
|---|---|
| `BARE_CLASS_SUBJECT` | a bare plural class noun as the subject ("Distributors accounted for...") |
| `JOINT_SUBJECT` | two capitalised names sharing one percentage |
| `GEOGRAPHIC_CONSTRUCTION` | "billing location", "outside of the United States", "shipped elsewhere" |
| `STATED_YEAR` + `STALE_COMPARATIVE_YEARS` | a stated year two or more years before the filing |

Each carries a regression fixture using verbatim filing text
(`test_hyp04_supply_chain_hedge_edgar.py::test_6h`), together with five
hardcoded-open controls, because a gate that rejected everything would satisfy
every rejection test.

The one-year case is explicitly preserved: an annual report reports the year
that just ended, so Intel's 10-K filed 2005-02-22 saying "In 2004, Dell Inc.
accounted for approximately 19% of our total sales" is current, not stale.
Only a gap of **two or more** years is treated as a comparative.

### A known under-inclusion, recorded rather than fixed

In that same Intel sentence, **Hewlett-Packard Company at 16% is dropped**.
"Company" is deliberately absent from `LEGAL_ENTITY_SUFFIX` — filers name their
own segments "...Group" and "...Systems" — and the sentence carries no role
word, so the 2026-08-26 attribution gate rejects the name. It costs nothing
here, since Dell at 19% already qualifies Intel, and widening that suffix would
risk the four false positives it was built to stop. Left as-is, on the record.

### What this says about the exercise

The point-in-time screen is not merely a longer version of the one-shot screen.
It reaches prose no gate has been tested against, and **its false-positive rate
must be measured, not assumed**, every time the corpus widens. A universe is a
preregistration artifact; a fabricated member is worse than a missing one.

**No universe from the first run is adopted anywhere.** The extractor was
fixed, the walk was re-run, and only the corrected result may be considered.

---

## AMENDMENT — 2026-08-28: the "eight fabrications" count, reconciled against the walk artifacts

This finding and registry v1.6 both state that **eight fabricated
counterparties** were rejected across two measurement rounds. Until now that
was an asserted count. It has been checked against the four full-frame walk
artifacts, which is the first independent verification of it.

**The count holds.** It is recorded here because the reconciliation is not
obvious from the artifacts alone — a naive name-level diff appears to
contradict it.

### The trail

Distinct named counterparties across all 51 tickers, per walk:

| Walk | Distinct names | What changed |
|---|---|---|
| `FULL51_2026-08-27.json` | **41** | before any new gate |
| `..._v2.json` | **33** | after round one's gates |
| `..._v3.json` | **30** | after round two's gates |
| `..._v4.json` | **30** | + full-submission fallback; 1,250 filings, 0 failures |

That is 11 name strings removed, against a claim of eight fabrications. The
difference is entirely in what a "name" is:

| Removed strings | What it was |
|---|---|
| `Distribution Distributors`, `DISTRIBUTION Distributors`, `Contents Distribution Distributors` | **three surface spellings of ONE fabrication** — the aggregate channel |
| `ASUSteK` | **not a fabrication.** A truncated form of a real party; `ASUSTeK Computer Inc` persists in v4 |
| `JPMorgan Chase` | **not a fabrication.** A variant of `JP Morgan Chase`, which persists in v4 |
| `HTC`, `Other Americas`, `Singapore` | 3 genuine fabrications (round one) |
| `CEM`, `Hong Kong`, `Mobility Group` | 3 genuine fabrications (round two) |

So: 1 (aggregate channel) + 3 + 3 = **seven fabrications visible as name
removals**. The eighth — the superseded prior-year comparative, a 2004 figure
in a 2007 filing that states there was no such customer in 2005–06 — removed
**no name**, because the counterparty was real and only the *figure* was stale.
Seven plus one is eight.

### Two things this makes explicit

**A name-count delta is not a fabrication count**, in either direction. It
over-counts when one fabrication surfaces under several spellings, and
under-counts when a gate rejects a stale figure attached to a real party. Any
future re-measurement must decompose the delta rather than report it.

**`v3 → v4` added 11 filings and moved no name.** The full-submission fallback
recovered the oldest filings without introducing or removing a single
counterparty; what it changed was the *earliest date* for names already
present. That is the expected shape — those filings are older instances of
relationships the later filings already disclosed — and it is a useful check
that the fallback did not quietly start reading exhibits.

### Provenance

Measured 2026-08-28 against the four artifacts as they exist on the repo
owner's machine. Only `_v4` and the pilot are committed; the three superseded
walks are retained locally but deliberately not committed, because they contain
the fabrications the gates were built to reject and would invite deriving from
the wrong file. **This amendment is therefore the durable record of the
reconciliation**, and the numbers above cannot be re-derived from the
repository alone.

Nothing here changes any membership, any registry version, or the gate, which
reads **CLOSED, C4 MET, 4 denials**.
