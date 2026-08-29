# HYP-04 — the extractor could not read a list, and that decided membership

**Dated 2026-08-29.** Recorded before registry v1.8 was authored.
**Nothing here is evidence about supply-chain transmission.** No result,
direction, effect estimate, plot, p-value or confidence interval exists for
HYP-04, and none may be displayed while the display gate is closed.

---

## 1. How this was found, and why that matters

Every previous under-inclusion measurement tested a construction someone
thought of first. The possessive denominator came from a fixture that happened
to fail; the closed verb set came from a grid I chose; the multi-year
`"respectively"` form came from a mis-parse. Each was found **by accident**.

That is the same failure the 2026-08-27 rounds recorded for over-inclusion —
two rounds of spot-checking missed three fabrications that only an exhaustive
enumeration found — running in the opposite direction.

So the search was inverted. Rather than propose a construction and measure it,
enumerate every sentence in all 1,250 cached filings carrying all three marks
of a named concentration disclosure — a figure at or above the threshold, a
revenue-shaped denominator, a counterparty role word — and bucket the ones
producing no edge against the rejections the extractor is *supposed* to make.
The residue is what nobody had thought of.

The first page of that residue contained:

> **ADBE 2014-01-21** — "In fiscal 2013, revenue from Ingram Micro has declined
> to **less than 10%** of our net revenue, although it has remained as our top
> customer."

A filer stating that its largest customer had just fallen *below* the
threshold — which means it had been above it, in a company appearing in no
registry version at any point.

**The instrument was too blunt to trust further** (1,176 unclassified
sentences, mostly flattened financial tables and "% change" narrative) and it
did not need to be. It pointed at the right filing, and the filings did the
rest.

## 2. The defect is structural, not lexical

Every anchor in `CONCENTRATION_ANCHORS` requires the percentage and the
denominator to be **adjacent in one match** — `<pct>% of <basis>`. Filings
routinely state the denominator **once**, in a scope clause, and then list
parties carrying bare percentages:

| Filing | Text |
|---|---|
| INTC 2018-02-16 | "our three largest customers accounted for 40% of our net revenue, with **Dell Inc. (Dell) accounting for 16%**, Lenovo Group Limited **accounting for 13%**, and HP Inc. **accounting for 11%**" |
| INTC 2024-01-26 | "accounted for the following percentage of our net revenue: … **Dell Inc. `19 %` `19 %` `21 %`**" |
| ADBE 2011-01-27 | "as a percentage of net revenue for fiscal 2010, 2009 and 2008 … `2010 2009 2008` **Ingram Micro `15 %` `15 %` `18 %`**" |
| JBL 2015-10-16 | "…expressed as a percentage of consolidated net revenue … **Apple, Inc. `24 %` `18 %` `20 %` `19 %` `12 %`**" |

Adjacency cannot be satisfied by any of them. **The verb tense and the table
layout are incidental.** The structural fact is that the denominator is not
repeated per party, and no widening of the verb set or the anchor list would
have reached a single one of these.

## 3. What it cost the published registry

Three memberships were wrong, and all three were wrong in the same way —
**data availability deciding membership**, which AU-1…AU-6 forbid.

### INTC — the interval ended where the prose style changed

Registry v1.7 closes Intel's membership at **2017-02-17**. That is not the year
Dell fell below the threshold. It is the filing in which Intel **moved the
named-customer disclosure out of Item 1 and into the segment note**. Every
filing from 2017-02-17 through 2024-01-26 says so outright in Item 1:

> "For more information about our customers, **including customers who
> accounted for greater than 10% of our net consolidated revenue**, see
> Note 3: Operating Segments."

and the note names them: Dell at 15–21%, Lenovo at 11–13%, HP at 10–11%.
Membership now runs **2005-02-22 → 2025-01-31**.

### ADBE and JBL — absent from every registry version

Adobe discloses **Ingram Micro at 11–21% of net revenue across 2008–2015**.
Jabil's 10-Ks carry an explicit table of *"customers who accounted for 10% or
more of the Company's net revenues, expressed as a percentage of consolidated
net revenue"* naming Dell Computer, Cisco Systems (10–24%), Marconi, Royal
Philips, Hewlett-Packard, Nokia, BlackBerry and **Apple, Inc. at 11–28% across
FY2012–FY2024** — twenty-four qualifying filings.

### Both new exits are the rule working

INTC's membership ends 2025-01-31 and JBL's 2025-10-17 because in those filings
Intel and Jabil **anonymised their customers to "Customer A / B / C"**. A
concentration whose counterparty is not named cannot support a bilateral
relationship, so the rule excludes it. These are rule-based exits, not reading
failures, and the same control keeps "Customer A" out of every other filing.

## 4. The first draft was wrong, and the corpus said so

The scoped-list reader was measured against all 1,250 filings **before it was
believed**. It produced six fabrication routes. Every one is now closed with a
verbatim regression fixture:

| Fabrication | Cause |
|---|---|
| a bare `Inc`, in **26 filings** | the comma in "Apple, Inc." — the same defect that reduced NIKE's Foot Locker to "Inc" |
| `Hong Kong`, `South Korean`, `European`, `There` | rows read out of a **later sentence** than the scope clause |
| `Constellation Wines` | "reported **within the** Constellation Wines **segment**" |
| `…Company and Lucent`, `Inc. and Dell Computer` | two names sharing one percentage |
| `Rite Aid Corporation` at **49% of revenue** | read off a sentence about **receivables** |
| `Amount`, `Accounts` | table furniture paired with the nearest figure |

**Spot-checking would not have found these.** The enumeration did, the same way
it did on 2026-08-27.

## 5. What the reader refuses

- **Column order is not a convention.** INTC, ADBE, CTSH and JBL list years
  newest-first; **GOOGL lists `2023 2024` — oldest first**, in this same
  corpus. The year header is *read*. A multi-column list whose header is
  unreadable, or whose header never names the reporting year, yields nothing.
  The multi-year `"respectively"` reader may assume newest-first within one
  sentence; a table may not.
- **A metric-labelled block table is refused outright** — see §6.
- **Two blocks sharing one year row** are read only while the revenue label
  precedes the receivables label. Checked, not assumed.
- **A single bare column** must sit in the scope clause's own sentence.
- The **aggregate gate moved to the row**. "Our three largest customers
  accounted for 40%" is the legitimate *scope* of a list that then names its
  members; "Top ten clients 14.6 %" is a *row* that names nobody.

## 6. Known limitations, stated rather than fixed

- **A metric-labelled block table is not read at all.** Some filers head a
  block with the party and label each row of figures by metric:

  > `Reyes Beer Division entities` / **Net sales** `27.5 % 25.4 % 25.1 %` /
  > **Accounts receivable** `22.0 % 15.0 % 17.7 %`

  The nearest label to every figure is a metric, not a party. **Measured cost:
  STZ discloses Reyes Beer Division entities at 25–27% and Southern Glazer's
  Wine and Spirits at 11–13% of net sales, and STZ is therefore not a member.**
  Missing a real relationship is the safe direction; inventing one is not.
- **`and` is not a name continuation**, because allowing it produced two names
  sharing one percentage. A counterparty whose registered name contains "and"
  is truncated — "Southern Wine and Spirits" is captured as "Southern Wine".
  Both instances in this corpus are receivables-basis and change no membership.
- **ASC 280 is a floor.** Disclosure is required only at or above 10% of
  revenue. An absent member is not evidence of no concentration.

## 7. Verification

Re-derived offline from the response cache at **zero SEC requests**.

- 51/51 tickers, **1,250 filings, zero failures**, 1,239 primary document and
  11 full-submission — the same corpus coverage as the v1.7 run
- corpus diff against the v1.7 extractor: **86 edges added, ZERO removed** —
  no existing edge changed or disappeared
- every added named party is a real company: Ingram Micro, Tech Data, Dell, HP,
  Lenovo, Apple, Cisco, Nokia, Royal Philips, Marconi, BlackBerry,
  Hewlett-Packard. **No geography, no segment, no aggregate, no bare suffix.**
- each JBL reading checked against the filing's own reporting-year column:
  Cisco 24% in FY2002, Philips 18% and Cisco 12% in FY2004, Nokia 21% in
  FY2006, Apple 13% → 28% → 11% across FY2012–FY2024
- suites: **60 green**. `test_market_response_layer_b_emission.py` fails with
  the identical 7 failures before this change and is unrelated.

## 8. What this does not do

**It creates no eligible anchor event.** `required_eligibility_class` is
unchanged, eligibility is decided by `gst_market_response.completeness` from
per-event capture records, and no capture path runs over ADBE, JBL or the
extended part of INTC's interval. **C2 still counts zero of 193.** The display
gate remains **CLOSED, C4 MET, four denials**.
