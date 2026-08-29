# GST Prospective Hypothesis Registry — v1.7 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.7.json)
**Authored:** 2026-08-28 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.6.json` (sha256 `1cce4dcb926640a4…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **The rule does not change, and neither does the evaluation basis.** AU-1…AU-6,
> the 10% threshold and the consolidated-revenue denominator are unchanged and
> remain ASC 280-10-50-42's; membership is still a point-in-time span. What
> changes is what the extractor can **read**. No hypothesis, eligibility class,
> measurement, capture path or decision changes, every eligible-event counter
> stays zero, and the display gate stays **CLOSED, C4 MET, four denials**.

---

## 1. Membership moved in both directions

| | Ticker | Span | Qualifying disclosure |
|---|---|---|---|
| **OUT** | ~~MCHP~~ | ~~2013-05-30 → 2014-05-30~~ | never entitled — see §2 |
| **IN** | **NKE** | 2002-08-14 → 2004-07-30 | Foot Locker, Inc., 10.9% of consolidated revenues |

Six members ever, nine intervals: **AAPL, CTSH, INTC, MCK, NKE, NVDA**.

**Both directions matter.** A registry version that only ever *adds* members is
indistinguishable from a loosened threshold. This one removes a member the
previous version published, which is the evidence that the rule was applied
rather than fitted. The generator refuses to write a version whose intervals
are identical to its predecessor's, for the same reason.

## 2. MCHP was never entitled to membership

Both filings behind its v1.6 interval disclose a concentration for a year
**other than the one they report on**:

| Filed | Period of report | What it actually says |
|---|---|---|
| 2013-05-30 | 2013-03-31 (FY2013) | Future Electronics was "approximately 10% of our net sales **in each of fiscal 2012 and fiscal 2011**" |
| 2014-05-30 | 2014-03-31 (FY2014) | "approximately 10% of our net sales **in fiscal 2012**" |

Neither states a ≥10% concentration for its own reporting year.

The stale-comparative gate measured staleness against the **filing date**. That
window has to be two years wide — an annual report filed in February reports
the year that ended in December, and a narrower window would reject the
reporting year itself. That necessary slack is what admitted a FY2012 figure
into a FY2013 filing.

**v1.6's companion records this imprecision as a stated limitation and says it
"changes no membership here."** It did. It manufactured a member. Staleness is
now measured against the submission's **period of report**, where the window
narrows to one year because there is no filing lag left to absorb.

The same correction drops **NVDA/Celestica**, which v1.6 also names as a
comparative that "still passes". It was not an interval opener, so NVDA's
intervals are unchanged.

## 3. NKE was invisible behind three independent defects

NIKE discloses Foot Locker, Inc. at **12.4% (FY2000), 11.8% (FY2001) and 10.9%
(FY2002)** of consolidated revenues, and calls it *"our largest single
customer."* The 2004-07-30 filing states the other side just as plainly — *"in
2004 and 2003 the Company did not have a significant customer that accounted
for more than 10% of consolidated revenues"* — so the relationship crossing
back below the threshold is disclosed, not inferred.

Three defects hid it, and **all three had to be fixed**:

1. **A multi-year "respectively" construction** — *"represented 10.9%, 11.8%
   and 12.4%, respectively of the Company's consolidated revenues"* — which the
   anchor could not read at all. Filings list years newest-first and
   percentages in the same order, so the **first** percentage is the reporting
   year's. Taking the largest, or the last, would attribute a prior year's
   concentration to the reporting year: the error the stale gate exists to
   prevent, committed inside one sentence where that gate cannot see it.
2. **A possessive denominator** — "the Company's consolidated revenues" — which
   the anchor's qualifier class excluded, making the disclosure not merely
   unclassified but *invisible*.
3. **A party parser that stopped at the comma** in "Foot Locker, Inc.",
   capturing the bare suffix `Inc`. Corpus-wide this had also mis-parsed three
   *existing* counterparties: Ingram Micro (AAPL), Caremark RX (MCK) and
   Hyundai Electronics (QCOM).

## 4. Four fabrication routes closed, three of them latent in v1.6

Widening the anchor reached prose no gate had been tested against. Four
constructions were rejected:

| Construction | Example |
|---|---|
| the filer's own unit, by appositive | "the largest **division of the Company**" |
| the filer's own unit, by **head noun** | "sales from the **Automotive Parts Group**" |
| `including X` as an instance | "billings to China, **including Hong Kong**" |
| a comparative dated `year ended <date>` | "During the **year ended May 31, 2002**…" |

**Three of the four were latent in v1.6's published extractor**, not introduced
by the widening: run the same sentences with an accepted verb and v1.6's code
produces the identical fabrications. They were absent from the corpus only
because the filings carrying them happen to use copular verbs the anchor did
not match — **protection by accident**. Ungated, the segment case alone would
have registered GPC as an anchor whose counterparty is GPC's own Automotive
Parts Group at 50% of consolidated revenue.

## 5. Verification

Re-derived offline from the response cache at **zero SEC requests**.

- 51/51 tickers, **1,250 filings, zero failures**
- corpus diff against the pre-correction run: **two removals, zero additions**
- exhaustive enumeration of every named ≥10% consolidated disclosure across all
  1,250 filings: **62 disclosures over 23 distinct ticker-counterparty pairs,
  every one a real company** — no geography, no segment, no bare legal suffix.
  **Zero fabrications.**
- intervals **derived, never typed**: `build_v1_7` has no parameter for them,
  re-derives after building, and refuses on disagreement
- every rule-describing field and the point-in-time basis checked
  **byte-identical to v1.6**
- v1.4, v1.5 and v1.6 remain byte-identical, all three pinned by hash

## 6. Known limitations, stated rather than fixed

- **ASC 280 is a floor.** Disclosure is required only at ≥10% of revenue, so
  real relationships below it, most supplier relationships, and every unnamed
  "Customer A" are invisible. **An absent member is not evidence of no
  concentration.**
- A party whose **head noun** is a unit type (Group, Division, Segment) is
  rejected, so a real firm named that way would be dropped. Measured, this
  rejects exactly five of the filer's own segments and no real counterparty;
  "Lenovo Group Limited" survives because its head is "Limited".
- The verb set admits equivalence phrasings but refuses *generated*, *provided*
  and *contributed* — those describe what a counterparty contributed rather
  than asserting the share **is** the figure.
- "Company" remains absent from `LEGAL_ENTITY_SUFFIX`.

## 7. What this does not do

- **It creates no eligible anchor event.** `required_eligibility_class` is
  unchanged; eligibility is decided by `gst_market_response.completeness` from
  per-event capture records; no capture path runs over any of these tickers.
  C2 still counts zero.
- **The locked 24-ticker universe is untouched**, as are `gst_market_response/`,
  the cohort protocol and every earlier registry version. v1.6 remains on disk
  unchanged, **including the MCHP interval this version removes** — a
  superseded version is allowed to be wrong, which is what superseded means.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
