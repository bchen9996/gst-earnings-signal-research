# GST Search-Construct Validity Audit — v1.0 (DRAFT)

**Status: `OFFLINE_SEMANTIC_AUDIT_PENDING_HUMAN_REVIEW`.**

**Zero Google Trends calls. Zero production-query changes. No query is approved for modification by this document.** Gap-audit item **F5 remains OPEN.**

**Audited at** `main` = `5c54c7990da028572d68069b116153394574f665` · **2026-08-10T03:40:00Z**

Companion artifacts: [`GST_SEARCH_CONSTRUCT_INVENTORY_v1.0.csv`](GST_SEARCH_CONSTRUCT_INVENTORY_v1.0.csv) · [`GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json`](GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0.json) · [`GST_SEARCH_CONSTRUCT_REVIEW_TEMPLATE_v1.0.md`](GST_SEARCH_CONSTRUCT_REVIEW_TEMPLATE_v1.0.md)

---

## 1. Executive summary

**The production Google Trends query for every one of the 24 locked tickers is the bare ticker symbol, verbatim.** There is no company-name mapping, no Google topic entity, no qualifier, no alias, and no fallback anywhere in the repository. The ticker *is* the query. This was traced mechanically from the universe constant to the `pt.build_payload()` call, not inferred.

**Documentation and implementation agree exactly**, which is the good news: the frozen spec states the query is "the bare ticker symbol string … no qualifier, no company name, no `<TICKER> stock` suffix", and that is precisely what the code sends. The same query is used on both the historical and the prospective path.

**The bad news is what a bare ticker measures.** Three findings a reviewer should not skim past:

1. **Three tickers carry high lexical risk.** `BRK-B` is the only query containing punctuation and the only one with a second listed share class — how Google tokenizes the hyphen cannot be determined offline, and the chosen spelling may be a minority form. `GOOGL` is one character away from the most-searched string on the web. `GME` collides with **Graduate Medical Education**, a common US acronym, *and* carries a documented meme-driven attention regime.

2. **Eight more carry moderate risk**, dominated by three-letter strings and by acronym collisions that a lexical screen can identify but cannot size: `STZ` is the standard abbreviation for **streptozotocin**; `SYK` is the symbol for **spleen tyrosine kinase**. Neither string resembles its issuer's name at all.

3. **A bare ticker systematically measures investor-framed attention, not public attention.** This is true of the thirteen `LOW` tickers as well. Nobody curious about Apple types `AAPL`. That may be exactly what the study wants — but it is a *choice*, it was never stated as one, and it is not what "abnormal public attention" implies in the project's own framing.

**Nothing here is a defect that this audit is entitled to fix.** No implementation could be left unestablished, so no ticker is classified `IMPLEMENTATION_UNCLEAR_FAIL_CLOSED`.

## 2. Exact production query — all 24 tickers

| Ticker | Company | **Exact query string** | Type | Risk |
|---|---|---|---|---|
| AAPL | Apple Inc. | `AAPL` | bare ticker | LOW |
| ABBV | AbbVie Inc. | `ABBV` | bare ticker | LOW |
| ADBE | Adobe Inc. | `ADBE` | bare ticker | LOW |
| AMZN | Amazon.com, Inc. | `AMZN` | bare ticker | LOW |
| BKR | Baker Hughes Company | `BKR` | bare ticker | **MODERATE** |
| BRK-B | Berkshire Hathaway Inc. (Class B) | `BRK-B` | bare ticker **with punctuation** | **HIGH** |
| CTSH | Cognizant Technology Solutions Corp. | `CTSH` | bare ticker | LOW |
| DELL | Dell Technologies Inc. | `DELL` | bare ticker | **MODERATE** |
| DVN | Devon Energy Corporation | `DVN` | bare ticker | **MODERATE** |
| GME | GameStop Corp. | `GME` | bare ticker | **HIGH** |
| GOOGL | Alphabet Inc. (Class A) | `GOOGL` | bare ticker | **HIGH** |
| GPN | Global Payments Inc. | `GPN` | bare ticker | **MODERATE** |
| INTC | Intel Corporation | `INTC` | bare ticker | LOW |
| LDOS | Leidos Holdings, Inc. | `LDOS` | bare ticker | LOW |
| MSFT | Microsoft Corporation | `MSFT` | bare ticker | LOW |
| NCLH | Norwegian Cruise Line Holdings Ltd. | `NCLH` | bare ticker | LOW |
| NKE | NIKE, Inc. | `NKE` | bare ticker | **MODERATE** |
| QCOM | QUALCOMM Incorporated | `QCOM` | bare ticker | LOW |
| SBUX | Starbucks Corporation | `SBUX` | bare ticker | LOW |
| STZ | Constellation Brands, Inc. | `STZ` | bare ticker | **MODERATE** |
| SYK | Stryker Corporation | `SYK` | bare ticker | **MODERATE** |
| TSLA | Tesla, Inc. | `TSLA` | bare ticker | LOW |
| TTWO | Take-Two Interactive Software, Inc. | `TTWO` | bare ticker | LOW |
| UAL | United Airlines Holdings, Inc. | `UAL` | bare ticker | **MODERATE** |

**Request parameters, identical for every ticker:** `geo="US"` · `gprop=""` (plain Web Search) · `cat=0` (All categories) · `timeframe` = `utcnow().date() − 300 days` to `utcnow().date()`, ISO-formatted, computed at runtime · capitalization preserved as declared · no project-side URL encoding or escaping (delegated to `pytrends`/`requests`) · **no alias or fallback for any ticker**.

### Provenance — traced, not inferred

```
gst_market_response/constants.py :: LOCKED_24_TICKER_UNIVERSE
        │  (identical, order and content, to …)
GST_Phase2_DailyPanel.py :: TICKERS                          lines 229-233
        ▼
GST_Phase2_DailyPanel.py :: process_ticker()                 line 710
        │      fetch_ticker_series_scoped_backoff(pt, ticker)
        │      └── the ticker is passed straight through as `term`
        ▼
GST_Phase2_DailyPanel.py :: fetch_ticker_series_scoped_backoff()
        │      pt.build_payload([term], timeframe=…, geo=GST_GEO,
        │                        gprop=GST_GPROP, cat=GST_CATEGORY)   line 401
        ▼
GST_Live_Signal_Engine.py :: GEO="US" (290) · GPROP="" (291) · CATEGORY=0 (292)
```

**Historical path:** `GST_FixedWindow_PerEvent_Canonical.py` line 110 issues `pt.build_payload([ticker], …)` with `GEO, GPROP, CAT_ALL = "US", "", 0` — **the same bare-ticker query and the same parameters.** Historical and prospective collection are consistent.

**Documentation:** `STRATEGY_SPEC_v1.0_FROZEN_2026-07-18.md` §1 (lines 44–52) specifies bare ticker, `US`, `""`, `0`, 300-day lookback. **This matches the implementation exactly. No mismatch was found.**

## 3. Risk distribution

| Classification | Count | Tickers |
|---|---|---|
| `LOW_LEXICAL_AMBIGUITY` | **13** | AAPL, ABBV, ADBE, AMZN, CTSH, INTC, LDOS, MSFT, NCLH, QCOM, SBUX, TSLA, TTWO |
| `MODERATE_LEXICAL_AMBIGUITY` | **8** | BKR, DELL, DVN, GPN, NKE, STZ, SYK, UAL |
| `HIGH_LEXICAL_AMBIGUITY` | **3** | BRK-B, GME, GOOGL |
| `IMPLEMENTATION_UNCLEAR_FAIL_CLOSED` | **0** | — |
| | **24** | |

**All 24 require human review.** Eleven require an empirical comparison before the first observation; thirteen have it marked *recommended* rather than required.

## 4. Detailed notes — every HIGH and MODERATE ticker

### HIGH

**`BRK-B` — Berkshire Hathaway Inc. (Class B).** The only query in the universe containing punctuation, and the only issuer with a second listed class. Two risks compound. **Tokenization:** the hyphen may be treated as a separator (`BRK B`), as a literal character, or — in some Google surfaces — as an exclusion operator; which of these applies to Trends cannot be established offline. **Spelling:** the same security is written `BRK.B` and `BRK/B` by different venues, so the chosen form may be a minority spelling with disproportionately low volume. **Share class:** public attention to Berkshire Hathaway is not class-specific in the way this ticker is. A failure mode worth naming explicitly: if `BRK-B` returns a sparse or empty series, the pipeline records it as *missing data*, not as a *construct failure* — the two are indistinguishable downstream.

**`GME` — GameStop Corp.** Two independent problems. **Lexical:** `GME` is a widely used US acronym for **Graduate Medical Education** (residency and fellowship training), and an abbreviation of "game". **Substantive:** this ticker carries a documented meme-driven retail-attention regime in which search spikes are generated by social-media dynamics rather than company information. The second is the more serious. The query almost certainly *identifies* the issuer for financial-context searches, but the attention it measures may be a different construct from the one HYP-01 intends. **This is the clearest case in the universe where lexical uniqueness does not deliver construct validity.**

**`GOOGL` — Alphabet Inc. (Class A).** The query string is one character from `google`, the most-searched term on the web. Any leakage from truncations or mistypings would be asymmetric and potentially enormous relative to ticker-level volume, and its magnitude cannot be estimated without live data. Class ambiguity (`GOOG` vs `GOOGL`) compounds it: public attention to Alphabet is not class-specific.

### MODERATE

**`BKR` — Baker Hughes.** `bkr` is a US direct-to-consumer glass water-bottle brand; `BKR` is a common written abbreviation for "broker" in real-estate and insurance listings; it also reads as a contraction of the surname "Baker". The issuer is normally searched as "Baker Hughes".

**`DELL` — Dell Technologies.** The query string is an ordinary English word (a small wooded valley) and a surname. In practice brand usage overwhelms the dictionary sense, so the query **does** identify the issuer — but the construct it measures is largely **product and support demand** (laptops, drivers, warranty, outages) rather than investor attention. A spike may reflect a product launch or a service incident, not information arrival about the company. **This matters more than its classification suggests: DELL is currently the sole registered prospective event.**

**`DVN` — Devon Energy.** Three letters; reads as an abbreviation of the given name or place name "Devon". No dominant collision identified, but three-letter strings are the class where offline lexical screening is least reliable.

**`GPN` — Global Payments.** Three letters; no dominant collision identified; elevated short-string risk. The issuer is normally searched as "Global Payments".

**`NKE` — NIKE, Inc.** Three letters, visually and phonetically adjacent to a globally dominant consumer brand. Any leakage from brand-level `nike` traffic would be large relative to ticker-level volume. "Nike" is also a Greek goddess and a Cold-War missile system.

**`STZ` — Constellation Brands.** `STZ` is the standard abbreviation for **streptozotocin**, a compound used routinely to induce experimental diabetes; "STZ-induced" is common phrasing in the biomedical literature. The string bears **no visible relationship to the issuer's name**, so a searcher interested in Constellation Brands is unlikely to type it, while biomedical users type it for an unrelated reason.

**`SYK` — Stryker Corporation.** `SYK` is the standard symbol for **spleen tyrosine kinase**, a well-studied signalling protein in immunology and oncology and the name of a drug-target class. Again the string bears no visible relationship to the issuer's name. Note a nasty wrinkle: both the medical-device issuer and the kinase sit in the health domain, so a Google *category* filter would not cleanly separate them.

**`UAL` — United Airlines Holdings.** `UAL` is the common abbreviation for University of the Arts London and is used as an initialism elsewhere. The issuer's own brand word, "United", is an extremely common English adjective and unusable as a query.

### A note that applies to the thirteen LOW tickers too

A `LOW` label means only that **no obvious semantic collision was identified offline**. Every bare ticker in this universe still measures a *narrower* construct than "public attention": it captures the investor-framed slice. Nobody curious about Apple types `AAPL`; nobody comparing running shoes types `NKE`. For `LDOS` — a government-services contractor with minimal consumer search — total volume may be low enough that the series is dominated by sampling noise, which is a **statistical** threat to the z-score rather than a lexical one, and is out of scope here.

## 5. Lexical ambiguity is not construct validity

This distinction is the point of the document and should not be blurred.

| | What it asks | What this audit did | What it can conclude |
|---|---|---|---|
| **Lexical ambiguity** | Could this *string* mean something other than the issuer? | Offline screening against stable general knowledge | A collision exists, or none was identified |
| **Construct validity** | Does the resulting *series* measure attention to the issuer, in the way the hypothesis requires? | **Nothing** | **Nothing** |

A `LOW_LEXICAL_AMBIGUITY` label is **not** evidence that the query is valid. It is the absence of one specific kind of counter-evidence. Establishing construct validity requires comparing candidate query forms against each other and against an external attention benchmark on real data — which is prohibited here and not authorized anywhere.

Three threats this audit **cannot** address, by construction:

- **Volume adequacy.** A lexically perfect query returning near-zero volume yields a meaningless z-score.
- **Regime change.** `GME`'s meme dynamics are the visible case; any ticker's search population can shift over the collection window.
- **Trends' own behaviour.** Sampling, normalization and series revision are undocumented in this repository and remain open under F5.

## 6. Methodology and limitations

**What was done.** Every query was traced mechanically from the universe constant through each function to the `build_payload` call. Each resulting string was screened against the checklist in the commissioning task: ordinary English word · common abbreviation · person or surname · location · unrelated company · product name · entertainment title · medical or scientific acronym · financial term · sports term · internet slang · punctuation ambiguity · unexpected tokenization · company-name changes · parent/subsidiary confusion · multiple share classes · over-broad query · famous-product dominance · earnings-irrelevance.

**Sources.** Repository contents, and stable general knowledge about what these strings denote. **No Google Trends call, no `pytrends` invocation, no unofficial endpoint, no browser page containing live Trends results, and no search-volume source of any kind.** No market price, news, earnings outcome or historical correlation was used to assess risk — using outcomes to judge a query would be precisely the contamination the preregistration exists to prevent.

**Limitations, stated plainly.**

- **Offline screening cannot size a collision.** That `STZ` also means streptozotocin is a fact; whether that traffic is 0.1% or 60% of `STZ` volume is unknown and unknowable here.
- **The author is not a search-methodology authority.** This is a structured lexical screen, not an expert construct-validity finding.
- **Absence of evidence.** Thirteen `LOW` labels mean no collision was *identified*, not that none exists.
- **Google topic entities were not enumerated.** Retrieving them requires a live Trends suggestion call. Every proposed topic alternative is therefore recorded as `NONE_KNOWN_FROM_REPOSITORY_EVIDENCE` rather than guessed.
- **Confidence is `LOW` for all eleven MODERATE/HIGH tickers**, precisely because sizing is what offline work cannot do.

## 7. Proposed future comparison design — **proposals only**

**Not retrieved. Not compared. No winner selected. No production mapping updated.** For every ticker the inventory records six candidate forms; what each would measure differs materially:

| Candidate | Construct it would measure | How it differs from the current query |
|---|---|---|
| **1. Current** — bare ticker, e.g. `STZ` | Investor-framed attention among people who already know the symbol | The baseline |
| **2. Official company name** — `Constellation Brands, Inc.` | General public awareness of the company as an entity | Much broader; includes customers, job seekers, journalists. Would likely raise volume and lower the investor share |
| **3. `TICKER stock`** — `STZ stock` | Explicitly investment-motivated attention | Narrower and more intent-specific than the baseline; likely far lower volume, so noisier |
| **4. `Company earnings`** — `Constellation Brands earnings` | Attention specifically to the earnings event | Closest to the hypothesis's stated construct, but so narrow that volume may be inadequate, and it risks being mechanically induced by the event itself rather than anticipating it |
| **5. Google topic entity** | Google's own disambiguated entity for the company, aggregating spellings and languages | Would resolve the `BRK-B` spelling problem and the `STZ`/`SYK` acronym collisions outright — the most promising remedy, and the one this audit could not evaluate because enumerating topics needs a live call |
| **6. Issuer-specific form** — e.g. `Constellation Brands` | Common-usage company name without legal suffix | Between 2 and 4; probably the most natural human query |

A future, **separately authorized** study would need to state in advance: which forms are compared, over which period, against which benchmark, and by what pre-declared criterion one would be preferred — chosen **before** the comparison, never after seeing which correlates best with outcomes. **Selecting a query by its association with returns would invalidate the study.**

## 8. Effect on gap-audit item F5

| | |
|---|---|
| **Offline inventory** | ✅ **Complete.** All 24 production queries established mechanically; provenance recorded; documentation confirmed to match implementation |
| **Semantic risk** | ✅ **Assessed.** 13 LOW · 8 MODERATE · 3 HIGH · 0 unclear |
| **Human approval** | ❌ **Not obtained.** No reviewer engaged; the review template is entirely `PENDING` |
| **Empirical comparison** | ❌ **Not performed and not authorized.** Required for 11 tickers before the first observation |
| **Trends revision behaviour** | ❌ **Still undocumented** |
| **F5 overall** | 🔴 **OPEN** |

**F5 remains open.** Its deadline is unchanged: **before the first HYP-01-eligible prospective pre-event capture**, per the [preregistration gap audit](../PREREGISTRATION_GAP_AUDIT_v1.0.md). This audit completes the offline half and does not close the item.

## 9. No query is approved for modification

**No query was changed, and none is proposed for change.** Production query construction, the ticker universe, panel code, methodology, HYP-01, the hypothesis registry, the cohort protocol and the event registry are all untouched and byte-identical.

Any future query change would be a **methodology change** requiring a **new dated methodology version** that preserves the current one byte-for-byte and states plainly what changed and why — the same standard applied to every other locked element. It would also require a decision about the existing historical series, which were collected with the bare-ticker query: changing the prospective query without addressing that would make historical and prospective attention measures non-comparable.

---

*Offline semantic audit only. Zero Trends calls. Zero query changes. No outcome inspected. F5 not closed.*
