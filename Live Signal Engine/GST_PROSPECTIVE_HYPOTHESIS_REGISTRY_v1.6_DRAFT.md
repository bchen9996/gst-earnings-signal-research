# GST Prospective Hypothesis Registry — v1.6 (human companion)

**Authoritative artifact:** [`GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.6.json`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.6.json)
**Authored:** 2026-08-27 · **Supersedes:** `GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json` (sha256 `731ee4f2228477ee…`)
**Companion to the JSON, which governs.** Where the two disagree, the JSON is correct and this file is wrong.

> **The rule does not change. The corpus does.** AU-1…AU-6, the 10% threshold
> and the consolidated-revenue denominator are unchanged and remain
> ASC 280-10-50-42's. What changes is *when* the rule is evaluated. No
> hypothesis, eligibility class, measurement, capture path or decision changes,
> every eligible-event counter stays zero, and the display gate stays
> **CLOSED, C4 MET, four denials**.

---

## 1. What v1.5 got wrong — and it was not the rule

v1.5 evaluated the rule against a screen that reads **only each filer's newest 10-K** (`extract_for_universe` calls `client.latest_10k`). So a company entered the universe only if its named ≥10% concentration is *still disclosed in 2026*.

That lets **persistence of the relationship to the present day** decide membership. A concentration ends because the customer was acquired, taken private or failed — none of which is independent of a supply-chain transmission hypothesis. The companies the snapshot silently dropped are not missing at random.

**It is the policy v1.5 itself states, violated one level up.** v1.5 added `peer_price_data_policy` precisely to stop data availability deciding membership on survivorship grounds — while the anchor side was doing the same thing.

It also left membership and edges on different footings: the curated MCK→CVS edge was back-dated to **2013-05-07**, while membership for the same relationship was stamped **2026-05-08**.

**v1.5's answer was not false.** MCK does disclose CVS Health at 24% of consolidated revenue in the 2026 filing. It is superseded because the corpus was biased, not because the answer was wrong.

## 2. What v1.6 declares

The same rule, evaluated against the 10-K **in force at each date**, over **1,250 filings** from all 51 frame members. Membership is a **span**, not a flag:

| Anchor | Span | Qualifying disclosure |
|---|---|---|
| **MCK** | 2000-06-13 → 2008-05-07 | Rite Aid Corporation, 15% of consolidated sales |
| **MCK** | 2013-05-07 → current | CVS Caremark Corporation, 17% of consolidated revenues |
| **NVDA** | 2002-05-14 → 2012-03-13 | Atlantic Semiconductor, 10% of total revenue |
| **NVDA** | 2016-03-17 → 2018-02-28 | ASUSTeK Computer Inc, 11% of total revenue |
| **NVDA** | 2020-02-20 → 2021-02-26 | Dell, 11% of total revenue |
| **INTC** | 2005-02-22 → 2017-02-17 | Dell Inc, 19% of total sales |
| **AAPL** | 2000-12-14 → 2002-12-19 | Ingram Micro Inc, 11.5% of net sales |
| **CTSH** | 2004-03-12 → 2005-03-16 | JP Morgan Chase, 10.1% of revenues |
| **MCHP** | 2013-05-30 → 2014-05-30 | Future Electronics, 10% of net sales |

**Six members ever, nine intervals**, against v1.5's one. An interval opens on the filing date that first disclosed the qualifying concentration — the date the fact became public, the same claim an edge's `as_of_date` makes — and closes on the filing date of the later filing that no longer qualified. Spans are half-open: `[start, end)`. `anchor_universe.qualifies_at()` is the operative test.

### This corrects the 2026-08-26 finding's headline

That finding recorded **zero** named counterparties among the locked 24. Point-in-time, **three locked-24 members qualify** — AAPL, CTSH and INTC. The "zero" was an artifact of reading only 2026 filings. An amendment has been appended to that document; it is not edited.

## 3. The corpus had to be fixed twice first, and both rounds are recorded

Widening from 2026-only to 1996–2026 **raised the extractor's false-positive rate with no code change**. The gates did not regress; the corpus outgrew them. **Eight fabricated counterparties** were found and rejected:

| | |
|---|---|
| an aggregate channel | "Distributors accounted for 60% of our net sales" |
| three geographies | "Other Americas", "Singapore", "Hong Kong" |
| a shared percentage | "revenues from Samsung Electronics **and** HTC comprised 26%" |
| a superseded comparative | a 2004 figure in a 2007 filing stating there was no such customer in 2005–06 |
| the filer's own segment | "**within the** Mobility Group represented 26%" |
| a category acronym | "Asustek, **a CEM**," |

**The gate that failed was the list.** `GEOGRAPHIC_PARTY` enumerated place names and contained neither Singapore nor Hong Kong. A list of places can never be complete, so all seven replacements match **constructions**.

**Round one was a spot check, not a measurement.** It inspected only the disclosures the report printed. Round two enumerated *every* named ≥10% disclosure across every filing and found three more, hidden behind a genuine one on the same ticker. That is why the generator refuses anything short of `registry_grade`.

**Under-inclusion was measured too**, since every gate rejects and an unrecognised denominator fails closed. Across the full corpus exactly **two** named ≥10% disclosures carried an unrecognised denominator — both Qualcomm *segment* revenues, which the rule excludes correctly anyway.

### Completing the corpus

10 of 11 unreachable filings were from **2000–2001** and returned 404: they predate the per-document layout. Those are the *oldest* filings, which a history walk exists to reach, so losing them biases the corpus toward recent history. `EdgarClient` now falls back to the full-submission text and takes **only the 10-K document, exhibits excluded** — because `HYP04_Linkage_Map_v1.0.csv` records a false attribution that came from exhibit text in *exactly one of these filings* (CVS as "Special Obligor" in McKesson's FY2000 exhibit). Verified: the recovered filing yields "Rite Aid Corporation" and contains no "Special Obligor" text.

Final walk: **51/51 tickers, 1,250 filings, zero failures**, 1,239 primary-document and 11 full-submission retrievals.

## 4. Guards

- The intervals are **derived, never typed**. `build_v1_6()` has no parameter for them; it re-derives after building and refuses on disagreement.
- It refuses anything short of **`registry_grade`** — derived *and* complete *and* full-frame.
- Every **rule-describing field** is checked byte-identical to v1.5. v1.6 may change when the rule is asked, never what it asks.
- v1.4's availability-contradiction guard still runs on v1.6's output.
- `eligible_event_counts`, `results`, `statistical_governance` and `peer_price_data_policy` must all be unchanged — v1.6 **applies** that policy, it does not amend it.
- The snapshot's fields are **removed, not left beside** the intervals. Two universes in one document would be the v1.3/v1.4 self-contradiction again.

## 5. Known limitations, stated rather than fixed

- The stale-comparative gate compares a stated year against the **filing date**, not the submission's period of report, so one comparative year still passes. Changes no membership here.
- "Company" is deliberately absent from `LEGAL_ENTITY_SUFFIX`, so a name carrying only that suffix in a sentence with no role word is dropped. Under-inclusive; changes no membership here.
- **ASC 280 is a floor.** Disclosure is required only at ≥10% of revenue, so real relationships below it, most supplier relationships, and every unnamed "Customer A" are invisible to this source. **An absent member is not evidence of no concentration.**

## 6. What this does not do

- **It creates no eligible anchor event.** `required_eligibility_class` is unchanged; eligibility is decided by `gst_market_response.completeness` from per-event capture records; no capture path runs over any of these tickers. C2 still counts zero.
- **The locked 24-ticker universe is untouched**, as are `gst_market_response/`, the cohort protocol and every earlier registry version. v1.4 and v1.5 remain byte-identical, both pinned by hash in tests.

---

**Nothing in this document is evidence about supply-chain transmission.** No result, direction, effect estimate, plot, p-value or confidence interval exists for HYP-04, and none may be displayed while the gate is closed.
