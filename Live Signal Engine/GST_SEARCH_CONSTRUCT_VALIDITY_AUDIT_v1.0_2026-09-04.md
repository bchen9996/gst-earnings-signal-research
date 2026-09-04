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

---

*Sections 4 and 5 are appended below from
`GST_SEARCH_CONSTRUCT_VALIDITY_RESULTS_2026-09-04.json`, generated by
`tools/run_gst_construct_validity_audit.py` after this point.*

*No display gate is opened, no eligible-event count changes, and nothing here
is investment advice or a representation that any approach is profitable.*
