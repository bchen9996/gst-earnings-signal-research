# Search-construct validity audit — v1.0

**Date:** 2026-09-04
**Discharges:** `PREREGISTRATION_GAP_AUDIT_v1.0.md` item **F5**, "Search-construct
validity", status **NOT AUDITED**, severity High, deadline
`BEFORE_FIRST_OBSERVATION`.
**Status:** `RETROSPECTIVE_DEVELOPMENT_ONLY`. Confirms no hypothesis, moves no
gate, resolves no decision.

**What this is.** F5 is the only gap-audit row marked NOT AUDITED rather than
UNRESOLVED — the audit itself had never been performed. This performs it. The
**decision** F5 gates (which query term is canonical going forward) remains a
`SCIENTIFIC_DECISION` for a qualified human, in a dated lock, and is not made
here.

**Ordering discipline, and why it is stated up front.** §5 compares the signal
under three query variants and can show which variant makes the most events
clear the z ≥ 5 threshold. Choosing the signal's *definition* by the signal's
*own outcomes* is precisely the failure this project documents elsewhere.
**§2's construct argument and its recommendation were therefore written, and
this file committed, before any term-sensitivity column was read.** §5 is
reported afterwards as robustness and explicitly does not revise §2.

---

## 1. The ticker→query mapping actually in force

Never previously stated as a decision. Read off the collection scripts, where
it exists only as repeated literals:

```
term  = the raw ticker string      e.g. "STZ", never "Constellation Brands"
geo   = "US"
gprop = ""                         web search
cat   = 0                          ALL categories -- no disambiguation applied
```

Identical in every collector checked: `GST Weekly Data Gathering.py`,
`GST Weekly Data Gathering (2021-2025).py`,
`GST Weekly Data Gathering (Broad50).py`,
`GST Weekly Data Gathering (2021-2025 Broad50 Clear).py`,
`GST Weekly Data Gathering (Backtest Universe).py`,
`GST_Live_Signal_Engine.py`, `GST_FixedWindow_PerEvent_Canonical.py`,
`GST_FullPopulation_ContinuousWindow_Recompute.py`, and the Task/Test scripts.
All call `pt.build_payload([term], timeframe=..., geo=GEO, gprop=GPROP,
cat=CATEGORY)` with those values.

Downstream, the z-score is `shift(1).rolling(window=12, min_periods=8)`, so the
event week is excluded from its own baseline. `isPartial` is carried through
collection rather than discarded — relevant to §4.

**`cat = 0` is the load-bearing choice.** Google's Finance category (cat = 7)
exists and is used nowhere in production. Every series in this project is
all-category web search for a bare ticker string, which is the widest possible
interpretation of the token and the one most exposed to homonyms.

## 2. Construct argument — written first, and sealed

*Committed before any outcome in §5 was read.*

**A raw ticker and a company name do not measure the same construct.**

- **"NKE" is a ticker; "Nike" is a brand.** A person typing `NKE` into Google is
  almost certainly acting on the security — checking a quote, a chart, an
  earnings date. A person typing `Nike` is overwhelmingly likely shopping. The
  same holds for `EBAY`, `LOW`, `HD`, `KO`, `TGT`.
- The paper's claim is about **investor attention around earnings**, not
  consumer interest. On construct grounds the ticker is the better instrument
  for that claim, and the company name would import a large, seasonal,
  commercially-driven component that has nothing to do with earnings news.
- The cost is **volume and ambiguity**: a ticker is a rarer string, so the
  series is noisier, and a short ticker can collide with ordinary words (§3).

**Recommendation, on construct grounds only:** *retain the raw ticker string as
the canonical query term*, and treat the company-name variant as a
non-equivalent measure of a different construct rather than as a robustness
check on the same one. Two conditions attach, and both are prerequisites rather
than suggestions:

1. **The ambiguity screen in §3 must be written down and applied explicitly.**
   Retaining tickers is only defensible if collision cases are excluded by a
   stated rule.
2. **`cat = 0` should be revisited on its own merits.** The Finance category is
   the natural disambiguator for a ticker query, and its absence from
   production is an unexamined default rather than a decision.

**This recommendation is not conditional on §5**, and must not be revised by it.
If §5 shows the ticker variant is less robust, that is a limitation to disclose,
not a reason to switch instruments after the fact.

## 3. Homonym and ambiguity review

### 3a. An ambiguity screen was already performed, and never documented

This is the audit's principal finding, and it was not previously recorded
anywhere.

`GST Weekly Data Gathering (Broad50).py` collects **50** tickers.
`GST Weekly Data Gathering (2021-2025 Broad50 Clear).py` collects **36**. The
14 in the first and not the second:

```
ARE  BRO  CI  CL  EL  FE  HD  KO  LOW  NI  PM  T  TT  VZ
```

**Every one of the 14 is an ordinary English word, a chemical symbol, or a
common abbreviation.** `ARE` (verb), `LOW` (adjective), `BRO` (slang), `HD`
(high definition), `PM` (post meridiem), `KO` (knockout), `EL` (article),
`FE` and `NI` (iron, nickel), `CI`, `CL`, `T` (a single letter), `TT`, `VZ`.

That is not a coincidental exclusion list. Someone recognised the homonym
problem, filtered on it, and encoded the result in a filename — "Clear" — and
the criterion was never written down, never justified, and never applied to the
other universes. **F5's complaint is therefore sharper than it appears: the
mapping justification is missing for a filtering decision that was actually made
and is in force.**

The screen was also applied inconsistently. `REG`, `ROP`, `ALB` and `PKG`
survive into the Clear universe and are no less abbreviation-like than several
of the 14.

### 3b. Exposure of the universes actually used

| universe | n | contains any of the 14 dropped | contains `BKR`/`GME`/`STZ` |
|---|---|---|---|
| Original 15 (`2021-2025`) | 15 | no | `GME` |
| Broad50 | 50 | **yes, all 14** | `BKR`, `STZ` |
| Broad50 Clear | 36 | no | `BKR`, `STZ` |
| **Paper's retrospective population** | **28** | **no** | **`BKR`, `GME`, `STZ`** |

**The paper's 28-ticker universe contains none of the 14 excluded tickers.** The
undocumented screen did protect it. That is a real mitigation and is stated as
such.

**But all three tickers the gap audit named survive into the paper's universe.**
`BKR`, `GME` and `STZ` passed a screen whose criterion is unknown, which means
they were either judged unambiguous by a rule nobody recorded, or never
considered.

### 3c. The three named risks

- **`STZ` (Constellation Brands).** A three-letter string with no common English
  meaning, but also no strong association with the company for a general
  searcher. The risk here is not collision but **thinness**: the query may be
  dominated by a small, idiosyncratic pool of searches, making the rolling
  z-score unstable for reasons unrelated to attention.
- **`BKR` (Baker Hughes).** Collides with ordinary abbreviation use ("bkr" for
  broker/baker) and with unrelated organisations sharing the initialism.
- **`GME` (GameStop).** The token is distinctive, so collision risk is low. The
  live problem is **regime**: the 2021 meme-equity episode drove search volume
  far outside anything the 12-week rolling baseline was designed for. Any GME
  z-score spanning 2021 should be read as a different phenomenon from a routine
  earnings-attention spike.

### 3d. Limits of this review, stated plainly

- **The structural half above covers every ticker; the empirical half covers
  8.** `RelatedQueriesBreadth_Results.csv` holds breadth data for `MSFT`,
  `ADBE`, `NFLX`, `NKE`, `STZ`, `QCOM`, `SBUX`, `AMZN` only.
- **Breadth is a count, not the query strings.** It records *how many* related
  queries a term returned, not *what they were*, so it bounds ambiguity only
  weakly. A ticker could return many related queries all of which are
  investor-intent, or few that are all off-target, and this metric cannot
  distinguish those.
- **Retrieving the actual related-query strings requires a live Google Trends
  call**, which needs a staged go-ahead and was not attempted here. That is the
  single highest-value follow-up to this audit.
- No ticker outside the eight has any empirical ambiguity evidence at all,
  including `BKR` and `GME`.

### 3e. Empirical result: one ticker fails the thinness test outright

> **CORRECTED IN §7.** The zero-breadth measurement below is right. The
> *explanation* offered for it is wrong: `STZ`'s raw series is the richest of
> the eight, not the thinnest. §7.1 gives the corrected mechanism and a
> stronger replacement finding. Do not cite §3e's reasoning.

Computed after §3c was written, from `RelatedQueriesBreadth_Results.csv`
(90 event rows, 85 usable, 5 rate-limited across 8 tickers):

| ticker | events | zero-breadth events | median breadth |
|---|---|---|---|
| MSFT | 15 | 0 | 25.0 |
| AMZN | 10 | 0 | 25.0 |
| NFLX | 14 | 1 | 23.0 |
| SBUX | 8 | 0 | 19.0 |
| NKE | 13 | 0 | 18.0 |
| ADBE | 10 | 0 | 17.5 |
| QCOM | 10 | 0 | 14.5 |
| **STZ** | **5** | **5** | **0.0** |

**Every one of `STZ`'s five z >= 5 spike weeks returned zero related queries.**
Six events across the whole file have zero breadth and five of them are `STZ`;
the sixth is a single NFLX week. Every other ticker has a median between 14.5
and 25.

§3c predicted, before this was computed, that `STZ`'s risk was thinness rather
than collision. That prediction is confirmed about as directly as this metric
allows: the term spiked hard enough to clear a five-sigma threshold, and Google
could not name a single associated search. A z-score built on a series that
sparse is measuring something, but there is no evidence it is measuring
attention to Constellation Brands.

`BKR` and `GME` have no breadth data at all, so neither is cleared or condemned
here.

---

## 4. Revision and reproducibility behaviour

F5's third complaint: "Trends' own revision behaviour undocumented."

**Closed historical weeks are served deterministically.** Ten events, ten
independent pulls each, z-score recomputed with the production formula every
time:

- maximum z-score range across the ten events: **0.0**
- maximum z-score standard deviation: **0.0**
- events flagged unstable: **0 of 10**

A separate five-pull comparison over a 53-week series agrees: maximum z
difference in any week **0.0**, and **0** weeks where the signal tier changed.

**The current, partial week does move.** Five pulls of one live partial week
gave 2 distinct GST values and 2 distinct z-scores, a range of **0.0812** z.
Real, and small.

**This is the reassuring finding of the audit.** A re-pull of a closed week
reproduces the historical record exactly, so no result in this project rests on
a Trends value that has since been revised. The mitigation for the partial week
is already in the collectors: `isPartial` is carried through rather than
discarded, and the z-score uses `shift(1)`, so the event week is excluded from
its own baseline.

## 5. Term and category sensitivity — robustness only

**Reported after §2 was written and committed (`b9c9ed9`). It does not revise
§2's recommendation, and §2 was not conditional on it.**

Same ten events, same production z-score formula, three query variants:

| variant | events clearing z >= 5 |
|---|---|
| raw ticker, cat=0 (production) | 10 of 10 |
| company name, cat=0 | **0 of 10** |
| raw ticker, cat=7 (Finance) | 5 of 10 |

### 5a. The 10-of-10 is a tautology and carries no information

**The ten events were selected *because* they were z >= 5 STRONG_EARNINGS
events under the raw-ticker query.** That they all clear z >= 5 under the
raw-ticker query is true by construction. It is not evidence that the ticker
variant is better, and it must never be cited as if it were. The two
informative rows are the other two, and both are conditioned on a
ticker-selected sample.

### 5b. Company-name search does not see these events at all

Not one of the ten comes close: the highest company-name z across all ten is
**3.999** (CTSH), and three are near zero or negative (ADBE −0.045, NFLX
−0.547, MSFT 0.154).

Two readings, and the audit does not adjudicate between them:

- *Consistent with §2's construct argument.* A ticker lookup and a brand search
  are different behaviours, and an earnings-attention spike would not be
  expected to appear in "Netflix" the way it appears in "NFLX".
- *Consistent with the ticker signal being fragile.* The signal has no
  corroboration from any second instrument. A measure that vanishes entirely
  under the most natural alternative operationalisation of "attention to this
  company" is not thereby validated.

### 5c. The Finance category loses half the events, unevenly

Five of ten survive narrowing to cat=7. The pattern is real but not clean:

| | ticker z | Finance z | retained |
|---|---|---|---|
| TTWO | 25.302 | 21.951 | 0.87 |
| NFLX | 16.230 | 16.167 | **1.00** |
| INTC | 9.734 | 8.932 | 0.92 |
| BKR | 9.706 | 5.234 | 0.54 |
| LDOS | 6.833 | 3.227 | 0.47 |
| NVDA | 5.716 | 5.137 | 0.90 |
| MSFT | 5.682 | 4.610 | 0.81 |
| ADBE | 5.663 | 2.265 | 0.40 |
| SBUX | 5.332 | 4.657 | 0.87 |
| CTSH | 5.114 | 2.564 | 0.50 |

The three largest spikes retain 0.87 to 1.00 -- for a big event, all-category
and Finance-category search measure nearly the same thing, and NFLX agrees to
within 0.4%. Below that, retention is erratic: `BKR` at z = 9.706 retains only
0.54, while `NVDA` at 5.716 retains 0.90.

**The survivors and failures overlap.** The largest ticker-z among the five
failures is 6.833; the smallest among the five survivors is 5.716. There is no
threshold that separates them, so this cannot be reduced to "marginal events
fail."

**What it does say, and it is uncomfortable for the paper.** Five of ten events
that clear a five-sigma threshold under all-category search do not clear it
when the same term is restricted to Finance. Some part of the `cat = 0` signal
at these events is non-finance traffic. The paper's signal arm is defined by
exactly this threshold on exactly this variant, so its marginal admissions are
the least robust members of the sample -- and §3e shows one universe member
(`STZ`) whose spikes have no identifiable related search at all.

This is a limitation to disclose, not a reason to switch instruments after the
fact. Changing the canonical term now, on the basis of these outcomes, is the
specification shopping this audit was ordered to avoid.

## 6. What this does not do

It resolves no decision. F5's decision -- which query term is canonical going
forward -- remains a `SCIENTIFIC_DECISION` for a qualified human in a dated
lock, `BEFORE_FIRST_OBSERVATION`. This document is the evidence that decision
needs.

It opens no display gate, changes no eligible-event count, modifies no
collection script, and reclassifies no hypothesis.

**Residual gaps, none of them closed here:**

- The term-sensitivity set is **10 events**, all selected under the variant
  being tested.
- Breadth data covers **8 tickers**; `BKR` and `GME`, two of the three named
  risks, have none.
- Breadth is a count, not the query strings. **Retrieving the strings needs a
  live Google Trends call and a staged go-ahead, and is the single highest-value
  follow-up to this audit.**
- The undocumented ambiguity screen (§3a) still has no written criterion. This
  audit records that it happened and what it excluded; it does not reconstruct
  the rule, because nobody wrote one down.
- `cat = 0` remains an unexamined default. §5c is the first evidence that it is
  materially different from the obvious alternative.

---

## 7. Follow-up: a correction, a recovered criterion, and a broken tautology

Computed from `GST_SEARCH_CONSTRUCT_VALIDITY_FOLLOWUP_2026-09-04.json`
(`tools/run_gst_construct_validity_followup.py`). Offline; no Trends call.

### 7.1 Correction to §3e — the measurement stands, the explanation does not

§3e reported that all five `STZ` z >= 5 spike weeks returned zero related
queries, and concluded that `STZ` is a **thin query**. The measurement is
correct and reproduces. **The explanation is wrong.**

`STZ`'s raw weekly series is not thin. It is the **richest of the eight**:
0.0% zero weeks, 57 distinct values, and the **highest median of the group**
(46.0, rank 1 of 8). A sparse-series account of the zero breadth is refuted by
the series itself.

**The corrected mechanism is more consequential than the claim it replaces.**
Google Trends normalises each single-term query to its own 0–100 maximum, so
**absolute search volume is structurally invisible in every series this project
has ever collected.** Two tickers with wildly different underlying attention
produce series that look alike, and no file in this repository records how much
search actually occurred. The only proxy that survives normalisation is the
**zero fraction**: a series rounds to 0 only when the underlying counts are
tiny. Under the earnings-intent term:

| ticker | `"[TICKER] earnings"` %zero | distinct |
|---|---|---|
| **STZ** | **95.0%** | **10** |
| NKE | 82.8% | 27 |
| SBUX | 80.5% | 30 |
| ADBE | 77.0% | 35 |
| QCOM | 75.5% | 40 |
| NFLX | 55.2% | 41 |
| MSFT | 15.3% | 42 |
| AMZN | 5.4% | 48 |

**The thinness is in the earnings-attention construct, not in the raw ticker
series.** §7.3 turns this into a direct test, and `STZ` fails it.

**Defeating the normalisation requires a network call** — a single multi-term
`build_payload` normalises *across* terms, which is the only way to recover
relative volume. Not attempted; recorded as a follow-up.

### 7.2 The screen's criterion is recoverable, statistical separation is not

§3a argued semantically that the 14 dropped tickers are homonyms. That is
testable: a homonym carries a high, flat generic-traffic baseline that swamps
company-specific variation.

| group | n | mean median | mean CV | mean %zero |
|---|---|---|---|---|
| **dropped** | 14 | **80.43** | **0.146** | 0.00% |
| kept | 36 | 59.83 | 0.372 | 5.08% |

The dropped group sits far higher and far flatter. **§3a's semantic reading is
empirically supported.**

**But the signature does not separate the groups.** Applying it
(median >= 64 and CV <= 0.31) to the kept 36 catches **sixteen** of them:
`ADP`, `ALB`, `ALLE`, `AVB`, `CCL`, `DELL`, `ERIE`, `GPC`, `LNT`, `MCK`, `MDT`,
`PKG`, `PLD`, `PNW`, `RCL`, `REG`. So the exclusion was **a human reading
ticker strings, not a statistic** — and by its own signature it was
**incomplete**, leaving sixteen tickers with the same profile in the universe.

**The exposure that matters.** Applying the signature to the paper's
28-ticker population returns exactly one hit:

> **`DELL`** — median 65.0, CV 0.13. `GOOGL` is borderline (63.0, 0.19).

`DELL` is the sharpest homonym case in the paper's universe and was never
screened. Unlike `AAPL`/Apple or `NKE`/Nike, where ticker and brand are
different strings, **the ticker `DELL` is identical to a heavily-searched
consumer laptop brand**, so nothing separates security lookups from shopping
traffic. This is recorded as an exposure. Removing `DELL`, or any universe
change, is a `SCIENTIFIC_DECISION` for a human in a dated lock.

### 7.3 The tautology, broken — and the signal mostly survives

> **CORRECTED IN §8, AND WITHDRAWN.** The comparison group below is wrong: it
> pits selected spike weeks against *all* other weeks, ~92% of which are not
> earnings weeks. It therefore tests whether earnings weeks have more
> earnings-intent search than ordinary weeks — true, and not the claim made.
> §8 repeats it against non-selected **earnings** weeks and the corroboration
> does not survive. The numbers below are real; the inference from them is not.

§5's 10-of-10 is true by construction: the events were selected as z >= 5 under
the raw-ticker query. The fix is to measure an instrument that **never selected
anything**. The earnings-intent series was collected independently and used for
no selection, so it is admissible as an outcome at those same weeks.

*This is not a selection-free test — the weeks are still ticker-selected. It is
a test whose **measured quantity** is independent of the selection rule, which
is what breaks the circularity.*

Event weeks vs that ticker's own non-event weeks, 10,000-permutation test on
the median difference, seed 42:

| ticker | non-zero rate, event | non-event | median, event | non-event | perm p |
|---|---|---|---|---|---|
| NKE | 1.000 | 0.129 | 92.0 | 0.0 | 0.0 |
| AMZN | 1.000 | 0.944 | 88.5 | 5.0 | 0.0 |
| SBUX | 1.000 | 0.170 | 87.0 | 0.0 | 0.0 |
| MSFT | 1.000 | 0.837 | 86.0 | 5.0 | 0.0 |
| NFLX | 1.000 | 0.417 | 83.0 | 0.0 | 0.0 |
| QCOM | 1.000 | 0.215 | 77.0 | 0.0 | 0.0 |
| ADBE | 1.000 | 0.183 | 72.0 | 0.0 | 0.0 |
| **STZ** | **0.400** | 0.043 | **0.0** | 0.0 | **1.0** |

**For seven of eight tickers the signal survives an independent instrument.**
Every ticker-selected spike week has non-zero earnings-intent search — a rate
of 1.000 against non-event base rates as low as 0.129 — with median levels of
72 to 92 against 0 to 5. This is the strongest corroboration in the audit, and
it is not circular.

**`STZ` fails.** Only 2 of its 5 selected spike weeks show any earnings-intent
search at all, the median at event weeks is 0.0, and the permutation test
returns p = 1.0. Its z >= 5 events are **not corroborated by any independent
measure of earnings attention**. This replaces §3e's claim with a better-founded
one: the problem with `STZ` is not that its ticker series is thin, it is that
its selected events do not look like earnings-attention events under a second
instrument.

A rolling z-score is undefined on a mostly-zero series, so the z-based
comparison is reported only for **`MSFT` and `AMZN`**, the two whose intent
series support it. For the other six, *not computable* is the finding and is
recorded as such rather than replaced by a number.

### 7.4 What §7 does not change

No decision is resolved, no gate moves, no universe changes, and no collection
script is touched. `DELL`'s exposure and `STZ`'s failure are findings for a
human to act on in a dated lock.

---

## 8. The corroboration, corrected — and withdrawn

From `GST_SEARCH_CONSTRUCT_VALIDITY_CORROBORATION_2026-09-04.json`
(`tools/run_gst_corroboration_fix.py`). Offline.

### 8.1 The signal largely tracks the earnings calendar

Two structural facts:

- Median earnings cadence: **13.0 weeks**.
- The z-score baseline is a **12-week** rolling window applied with `shift(1)`.

So the baseline for an earnings week runs across weeks t−12 to t−1 and, at a
13-week cadence, **almost never contains another earnings week**. Measured
directly: the mean number of earnings weeks falling inside a selected event's
own baseline is **0.0 for six of the eight tickers**, and 0.067 and 0.077 for
the other two. **The quarterly peak is compared against a trough-only baseline
by construction.**

The consequence shows up in how often the signal fires:

| ticker | earnings weeks clearing z ≥ 5 |
|---|---|
| MSFT | 15 of 20 (**75%**) |
| ADBE | 15 of 20 (**75%**) |
| NFLX | 14 of 20 (70%) |
| NKE | 13 of 20 (65%) |
| QCOM | 10 of 20 (50%) |
| AMZN | 10 of 20 (50%) |
| SBUX | 8 of 20 (40%) |
| STZ | 5 of 20 (25%) |

A five-sigma threshold that fires on **three-quarters of all earnings weeks**
is not identifying unusual attention. It is substantially detecting the
earnings cycle against a baseline that excludes earnings.

*(These base rates were seen during feasibility checking, before §8.2 was run,
and are reported as pre-observed rather than as a sealed result.)*

### 8.2 Like-for-like: the corroboration does not survive

§7.3's comparison group is replaced. Both arms are now **earnings weeks** for
the same ticker, so earnings-ness is held constant and only attention varies.
Median difference, 10,000-draw permutation test, seed 42.

| ticker | n sel / non-sel | median selected | median non-selected | non-zero rate | perm p |
|---|---|---|---|---|---|
| MSFT | 15 / 5 | 86.0 | **93.0** | 1.00 vs 1.00 | 0.840 |
| ADBE | 15 / 5 | 72.0 | **80.0** | 1.00 vs 1.00 | 0.746 |
| NFLX | 14 / 6 | 83.0 | **83.5** | 1.00 vs 1.00 | 0.984 |
| NKE | 13 / 7 | 92.0 | 77.0 | 1.00 vs 1.00 | 0.415 |
| QCOM | 10 / 10 | 77.0 | 72.5 | 1.00 vs 1.00 | 0.906 |
| SBUX | 8 / 12 | 87.0 | 80.0 | 1.00 vs 1.00 | 0.866 |
| AMZN | 10 / 10 | 88.5 | 79.0 | 1.00 vs 1.00 | 0.283 |
| STZ | 5 / 15 | 0.0 | 0.0 | 0.40 vs 0.47 | 1.000 |

**Not one ticker shows a detectable difference.** No p-value falls below 0.28,
and for MSFT, ADBE and NFLX the **non-selected** arm is the higher one. The
non-zero rate is 1.00 in *both* arms for seven of eight — §7.3's headline
contrast of "1.000 versus 0.129" was entirely the gap between earnings weeks
and ordinary weeks.

This is the outcome §8.1 predicted and the one the pre-declared interpretation
assigned to "the signal is detecting earnings-ness, not attention." **§7.3's
corroboration is withdrawn.** Every arm met the pre-declared minimum of 5
observations, so no ticker is excused as underpowered.

### 8.3 But the instrument is saturated, so the null is weak evidence

> **CORRECTED IN §9.** "Saturated" names the consequence and misses the
> mechanism. `GST_IntentFiltered_Pull.py:45` pulls **one Google Trends call per
> calendar year**, so this series is five independently renormalised annual
> segments concatenated — each year's peak forced to 100 whatever its true
> volume. The compression below is real; calling it saturation of a single
> scale is wrong, and the cross-year comparison §8.2 ran was invalid for a
> reason §8.3 did not identify.

*Added after §8.2 was computed, to diagnose it. It does not change §8.2, which
stands exactly as reported. It is stated here because a non-saturated
instrument would have made that null far stronger evidence against the signal,
and the reader is entitled to know which case this is.*

| ticker | median, earnings weeks | median, non-earnings weeks | earnings weeks ≥ 50 |
|---|---|---|---|
| MSFT | 86.5 | 5.0 | 100% |
| AMZN | 87.0 | 5.0 | 100% |
| NKE | 82.5 | 0.0 | 100% |
| NFLX | 83.0 | 0.0 | 95% |
| SBUX | 86.0 | 0.0 | 90% |
| ADBE | 73.0 | 0.0 | 75% |
| QCOM | 76.0 | 0.0 | 65% |
| STZ | 0.0 | 0.0 | 40% |

On a 0–100 index the earnings-intent series sits near **0 outside earnings
weeks and 73–87 during them**, with 65–100% of earnings weeks at or above 50
for seven of eight tickers. **The instrument is close to binary.** It separates
earnings from non-earnings almost perfectly and discriminates within earnings
weeks hardly at all.

So §8.2's null means *this test cannot answer the question*, not *no attention
difference exists*. The corroboration is not repaired by this instrument, and
it cannot be: the measure runs out of range exactly where the question lives.

**`STZ` is the one exception and it fails differently.** Its earnings-intent
median is 0.0 even at earnings weeks, and only 40% reach 50 — consistent with
§7.1's corrected finding that its earnings-attention volume is near-absent.

### 8.4 Where this leaves the audit

- §7.3's claim of independent corroboration is **withdrawn**. It was the
  strongest evidence in the audit and it does not hold.
- The z ≥ 5 signal fires on 25–75% of earnings weeks against a baseline that
  structurally excludes earnings, so a large part of what it detects is the
  earnings calendar.
- **Nothing here shows the attention signal is spurious.** It shows the
  available instruments cannot separate attention from earnings-ness. That is a
  measurement limit, and stating it as a negative result about the signal would
  overclaim in the opposite direction.
- **What would answer it** is an instrument with dynamic range *within*
  earnings weeks. That requires defeating the per-query normalisation of §7.1 —
  a single multi-term `build_payload` — which is a network call needing a
  staged go-ahead. It is now the highest-value follow-up in the project.

Nothing here resolves a decision, moves a gate, or changes a universe.

---

## 9. Why §8.2 failed — the instrument is renormalised every year

From `GST_SEARCH_CONSTRUCT_VALIDITY_NORMALIZATION_2026-09-04.json`
(`tools/run_gst_instrument_normalization_fix.py`). Offline. The interpretation
in §9.3 was committed (`e3d9036`) before any outcome was computed.

### 9.1 The mechanism §8.3 missed

`GST_IntentFiltered_Pull.py:45`:

```python
timeframe = f"{year}-01-01 {year}-12-31"
```

**One Google Trends call per calendar year.** Google renormalises its 0–100
index to the peak of each queried window, so the series §8.2 analysed is five
independently normalised annual segments concatenated.

The signature is in the data. **All 40 ticker-years contain a week valued
exactly 100**, and 39 of 40 contain exactly one (SBUX 2021 ties two weeks at
its annual maximum — the same forced-ceiling signature, not a counterexample).
A single continuous 2021–2025 pull would contain **one** 100 in total.

The consequence is visible in the zero fraction, which §7.1 identified as the
only surviving proxy for absolute volume. Nonzero weeks per year, of ~52:

| ticker | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| ADBE | 4 | 7 | 7 | 17 | **25** |
| NKE | 4 | 4 | 6 | 14 | **17** |
| NFLX | 17 | 24 | 20 | 21 | **35** |
| MSFT | 34 | 40 | 46 | 51 | 50 |
| AMZN | 42 | 51 | 51 | 52 | 51 |
| STZ | 2 | 2 | 2 | 1 | 6 |

ADBE's zero fraction moves by a factor of six across five years of one
continuous phenomenon. Under a shared scale that cannot happen from
renormalisation; under five independent anchors it is expected. **So §8.2
pooled ~20 earnings weeks drawn on five different scales and compared their
medians.** That is why it could not resolve anything, and "saturation" was the
wrong name for it.

**§7.1 is not affected.** Its cross-ticker zero-fraction comparison holds
because every ticker spans the same five years: STZ sits at 1–6 nonzero weeks
in *every* year against AMZN's 42–52 in *every* year. That contrast survives
the year anchor; a within-ticker comparison across years does not.

**The project already knew, for a different series.**
`Live Signal Engine/CHANGELOG.md` (2026-07-18) documents per-year chunking and
window renormalisation for the **main** GST series, and corrects it the same day
by re-pulling continuously (`FullPopulation_ContinuousWindow_Recompute.csv`, one
`2021-01-01 2025-12-31` call per ticker). **That correction was never applied to
the intent-filtered series.** §8.2 ran on an instrument carrying a defect this
repository had already diagnosed and repaired elsewhere. That is not a new
discovery; it is an unapplied one, and the audit should have found it in §3.

### 9.2 The selection side survives the correction

> **CORRECTED IN §10.** The comparison below is made against
> `FullPopulation_ContinuousWindow_Recompute.csv`, which `CHANGELOG.md`
> supersedes and quarantines for look-ahead contamination, and of whose derived
> ledgers it says they *"should not be used for new analysis."* §10 redoes it
> against the canonical `FixedWindow_PerEvent_Canonical.csv`. The conclusion
> holds — but the two disagree about **which** events survive, so the reasoning
> below is not sound as written.

§8's *selection* side came from the same per-year-chunked data, so it needs
checking too, against the corrected population:

| | audited | retained | dropped | newly qualifying |
|---|---|---|---|---|
| MSFT | 15 | 13 | 2 | 0 |
| ADBE | 15 | 14 | 1 | 0 |
| NFLX | 14 | 14 | 0 | 2 |
| NKE | 13 | 12 | 1 | 1 |
| QCOM | 10 | 9 | 1 | 1 |
| SBUX | 8 | 7 | 1 | 2 |
| AMZN | 10 | 10 | 0 | 0 |
| STZ | 5 | 4 | 1 | 2 |
| **total** | **90** | **83** | **7** | **8** |

**83 of 90 survive.** §8.1's selectivity finding is not propped up by the same
defect and stands as reported.

### 9.3 The like-for-like test, blocked on year — the actual fix

Within a single ticker-year the normalisation anchor **is** shared. So §8.2 is
re-run with both arms held to earnings weeks *and* every comparison confined to
one ticker-year, permuting arm labels **within stratum only** — permuting
across strata would reintroduce exactly the scale break this section exists to
remove. 10,000 draws, seed 42.

- Informative strata (both arms non-empty): **32 of 40**, against a
  pre-declared minimum of 20. Adequately powered by the rule as written.
- Primary statistic, mean within-stratum difference of arm means:
  **+4.17 index points**, **p = 0.380**.
- Pre-declared robustness statistic on within-stratum ranks: **−0.006**,
  **p = 0.949**. The two **agree**.

**Verdict: no detectable difference.** By the interpretation sealed in
`e3d9036`, this reads as: *the withdrawal in §8 stands, and now stands on an
instrument whose known scale defect has been controlled rather than ignored.*

Per ticker, **descriptive only** — three to five strata cannot support an
inference for one ticker, and these are printed so the spread is visible, not
so any of them can be quoted:

| ticker | strata | mean within-stratum difference |
|---|---|---|
| STZ | 3 | +18.3 |
| SBUX | 4 | +9.8 |
| NKE | 4 | +8.7 |
| QCOM | 5 | +7.7 |
| AMZN | 5 | +3.2 |
| MSFT | 3 | +2.9 |
| NFLX | 5 | −3.4 |
| ADBE | 3 | −13.7 |

A spread from −13.7 to +18.3 with a pooled p of 0.38 is what noise looks like.

**One caveat on the effect size, not the test.** The permutation p is exact
under within-stratum exchangeability. The observed **+4.17 index points** is
not a physical quantity: it averages differences measured on five annual
scales. The rank statistic, which is scale-free within stratum, is the one to
read for direction — and it is flat.

### 9.4 What this fixes, what it does not, and exactly what would

Blocking removes the **cross-year** scale break. It does not restore absolute
scale, and it cannot add dynamic range *within* a year: at ~4 earnings weeks
per ticker-year, a year-blocked test is inherently low-resolution. The honest
statement is unchanged from §8.3's conclusion even though its mechanism was
wrong — **these instruments cannot separate attention from earnings-ness**, and
that remains a measurement limit rather than a negative result about the
signal.

**What would answer it**, specified precisely and **not performed here** — it
is a network call and needs a staged go-ahead:

```python
pt.build_payload([company_term, earnings_term],
                 timeframe="2021-01-01 2025-12-31", geo=GEO, gprop=GPROP)
```

**Eight calls, one per ticker.** A single continuous window fixes the time axis
of §9.1; a multi-term payload fixes the term axis of §7.1. Both defects, one
request. The five-years-flat bound is required, not cosmetic: `CHANGELOG.md`
records that a pytrends window longer than ~5 years silently degrades from
weekly to monthly granularity, and that `2021-01-01`–`2025-12-31` was confirmed
to return the expected ~262 weekly points.

Until that is run, §7.3 stays withdrawn and no corroboration claim is made in
either direction.

Nothing here resolves a decision, moves a gate, or changes a universe.

---

## 10. The population this audit has been using is superseded

From `GST_SEARCH_CONSTRUCT_VALIDITY_SUPERSESSION_2026-09-04.json`
(`tools/run_gst_population_supersession_fix.py`). Offline. §10.3's
interpretation was committed (`c21d31b`) before any outcome was computed.

### 10.1 §9.2 cited a file the CHANGELOG quarantines

`CHANGELOG.md` (2026-07-19, *"fixed-window per-event recompute"*) makes
`FixedWindow_PerEvent_Canonical.csv` the canonical historical population — 153
events clear z ≥ 5, 152 of them priced — **superseding both** the 147-event
chunked archive (*GST-Legacy-v1*) and the continuous-window reconstruction. The
latter is quarantined for **look-ahead contamination**, 93 of 175 events at
risk, and the CHANGELOG states its derived ledgers *"should not be used for new
analysis."*

**§9.2 used exactly that file.** It reached for the continuous-window recompute
because that was the file that existed, not the file that governs.

Redone against the canonical population:

| | quarantined | canonical |
|---|---|---|
| audited events retained | **83 of 90** | **83 of 90** |
| events rejected | 7 | 7 |
| rejections in common | — | **3 of 7** |

**The headline agrees and the membership does not.** Only three of the seven
rejected events are the same:

- rejected by the quarantined set only — ADBE 2021-03-21, MSFT 2024-10-27,
  NKE 2021-12-19, SBUX 2021-07-25
- rejected by the canonical set only — ADBE 2024-09-08, AMZN 2021-10-24,
  NKE 2021-03-14, STZ 2022-01-02

A reader who checked only the count would conclude the two populations agree.
They do not. **§9.2's conclusion survives; its reasoning does not, and the
coincidence of the two 83s is the part worth distrusting.**

### 10.2 And the audit's own event set is GST-Legacy-v1

The larger fact §9 did not record. Every section of this audit selects events
through `RelatedQueriesBreadth_Results.csv`, whose spike weeks are exactly the
*GST-Legacy-v1* z ≥ 5 set. **§§1–9 analyse a superseded population and nowhere
say so.**

| ticker | legacy | canonical | both | canonical rejects (its z) | never analysed |
|---|---|---|---|---|---|
| MSFT | 15 | 14 | 14 | 2023-07-23 (4.55) | — |
| ADBE | 15 | 14 | 14 | 2024-09-08 (4.96) | — |
| NFLX | 14 | 16 | 14 | — | 2022-01-16, 2023-01-15 |
| NKE | 13 | 13 | 12 | 2021-03-14 (3.35) | 2024-03-17 |
| QCOM | 10 | 10 | 9 | 2022-01-30 (3.94) | 2025-02-02 |
| SBUX | 8 | 10 | 8 | — | 2024-01-28, 2025-01-26 |
| AMZN | 10 | 9 | 9 | 2021-10-24 (4.94) | — |
| STZ | 5 | 4 | 3 | 2022-01-02 (4.89), 2023-04-02 (4.57) | 2025-01-05 |
| **total** | **90** | **90** | **83** | **7** | **7** |

Seven events this audit analysed do not clear z ≥ 5 canonically, and seven
canonical events it never looked at. The totals coincide at 90; the sets differ
by 7 in each direction.

**§8.1's conclusion is unaffected, and now measured rather than inferred:**
selectivity is **56.2%** of earnings weeks under the legacy set and **56.2%**
under the canonical one. That is the check §9.2 should have made.

**The manuscript is not implicated.** The citation policy and the paper use the
canonical **152 priced** signal events, which is the correct population for a
P&L claim. It is this audit that drifted.

*(A distinction this section's own precondition caught: 153 events clear z ≥ 5
and 152 price successfully — LDOS 2021-02-21 qualifies at z = 6.61 but has no
early-enough return history. A construct-validity question about attention
takes the 153; a P&L claim takes the 152. No audit ticker is affected either
way.)*

### 10.3 The blocked test, re-run on the canonical population

§9.3's year-blocked test, with the selected arm defined by the canonical event
set instead. Same statistic, same seed, same `MIN_INFORMATIVE_STRATA = 20`.

| | §9.3 (legacy) | §10.3 (canonical) |
|---|---|---|
| informative strata | 32 of 40 | **33 of 40** |
| mean difference | +4.17 | **−1.59** |
| permutation p | 0.380 | **0.727** |
| rank statistic | −0.006 | **−0.026** |
| rank p | 0.949 | **0.761** |
| verdict | no detectable difference | **no detectable difference** |

**The two agree.** By the rule sealed in `c21d31b`: *the null in §9.3 is not an
artifact of the superseded event set; both are reported and the canonical one
is what should be cited.*

Note the point estimate flips sign, +4.17 to −1.59, while both p-values sit far
from significance. That is not a contradiction — it is what an estimate does
when there is nothing to estimate, and it is a better argument for the null than
either p-value alone.

§9.3 is retained unchanged as the pre-registered original. It is not rewritten,
and the canonical run does not replace it.

### 10.4 What this does not cover

`group_a_z4_earnings_adjacent.csv` — the same legacy archive — is read by
roughly eight analysis scripts, among them `GST_AbnormalGST_Residual_Test.py`,
`GST_ConcentrationDependence_Audit.py` and
`GST_EarningsSurprise_SignalQuality_Test.py`. Whether any of their results are
still cited anywhere current is a **repo-wide supersession sweep**, larger than
this pass and recorded here as the next candidate rather than begun.

Nothing here resolves a decision, moves a gate, or changes a universe.

---

*No display gate is opened, no eligible-event count changes, and nothing here
is investment advice or a representation that any approach is profitable.*

*No display gate is opened, no eligible-event count changes, and nothing here
is investment advice or a representation that any approach is profitable.*
