# GST Search-Construct Review — Decision Template (v1.0)

> **Blank template. Every reviewer field is `PENDING` and no checkbox is preselected.**
>
> **No reviewer has been engaged. No review has taken place. No query is approved.**
> The offline audit that this template accompanies changed no query and closed no gap. Gap-audit item **F5 remains OPEN**.

Complete only after reading [`GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_DRAFT.md`](GST_SEARCH_CONSTRUCT_VALIDITY_AUDIT_v1.0_DRAFT.md) and [`GST_SEARCH_CONSTRUCT_INVENTORY_v1.0.csv`](GST_SEARCH_CONSTRUCT_INVENTORY_v1.0.csv).

---

## Reviewer

| Field | Entry |
|---|---|
| Reviewer name | `PENDING` |
| Affiliation | `PENDING` |
| Position / title | `PENDING` |
| Relevant expertise (search behaviour, information retrieval, marketing analytics, econometrics) | `PENDING` |
| Contact | `PENDING` |
| Review date | `PENDING` |

## Conflict-of-interest disclosure

| Field | Entry |
|---|---|
| Financial interest in this project or its outcomes? | `PENDING` |
| Advisory, supervisory, or personal relationship with the project team? | `PENDING` |
| Any interest in a particular result being obtained? | `PENDING` |
| Disclosure statement | `PENDING` |

> Faculty supervision of the project team **is** a relationship and should be disclosed here rather than treated as absence of conflict.

## Prohibition — read before completing the table

> **A query must not be approved, rejected, or preferred on the basis of observed earnings outcomes, returns, price moves, or any measured association with them.**
>
> Selecting a search query because it correlates better with what the market did would invalidate the study outright. Judge each query on whether it *denotes the issuer* and *measures the intended construct* — never on how well it performs.
>
> Zero prospective outcomes exist at the time this template was written (`results: null`, `frozen_event_ids: []`, eligible counts 0/0/0). If outcomes exist when you complete it, the prohibition binds harder, not less.

## Per-ticker decisions

For each ticker choose **exactly one** disposition. No box is preselected.

- **A** — Approve current query for continued collection
- **B** — Require empirical query comparison before the first observation
- **C** — Request a dated methodology-version proposal (query change)

| # | Ticker | Company | Current query | Audit risk | A: approve | B: require comparison | C: request version proposal | Reviewer comments |
|---|---|---|---|---|---|---|---|---|
| 1 | **AAPL** | Apple Inc. | `AAPL` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 2 | **ABBV** | AbbVie Inc. | `ABBV` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 3 | **ADBE** | Adobe Inc. | `ADBE` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 4 | **AMZN** | Amazon.com, Inc. | `AMZN` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 5 | **BKR** | Baker Hughes Company | `BKR` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 6 | **BRK-B** | Berkshire Hathaway Inc. (Class B) | `BRK-B` | HIGH | [ ] | [ ] | [ ] | `PENDING` |
| 7 | **CTSH** | Cognizant Technology Solutions Corporation | `CTSH` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 8 | **DELL** | Dell Technologies Inc. | `DELL` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 9 | **DVN** | Devon Energy Corporation | `DVN` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 10 | **GME** | GameStop Corp. | `GME` | HIGH | [ ] | [ ] | [ ] | `PENDING` |
| 11 | **GOOGL** | Alphabet Inc. (Class A) | `GOOGL` | HIGH | [ ] | [ ] | [ ] | `PENDING` |
| 12 | **GPN** | Global Payments Inc. | `GPN` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 13 | **INTC** | Intel Corporation | `INTC` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 14 | **LDOS** | Leidos Holdings, Inc. | `LDOS` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 15 | **MSFT** | Microsoft Corporation | `MSFT` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 16 | **NCLH** | Norwegian Cruise Line Holdings Ltd. | `NCLH` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 17 | **NKE** | NIKE, Inc. | `NKE` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 18 | **QCOM** | QUALCOMM Incorporated | `QCOM` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 19 | **SBUX** | Starbucks Corporation | `SBUX` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 20 | **STZ** | Constellation Brands, Inc. | `STZ` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 21 | **SYK** | Stryker Corporation | `SYK` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |
| 22 | **TSLA** | Tesla, Inc. | `TSLA` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 23 | **TTWO** | Take-Two Interactive Software, Inc. | `TTWO` | LOW | [ ] | [ ] | [ ] | `PENDING` |
| 24 | **UAL** | United Airlines Holdings, Inc. | `UAL` | MODERATE | [ ] | [ ] | [ ] | `PENDING` |

## Cross-cutting questions

| # | Question | Entry |
|---|---|---|
| 1 | Is a bare ticker symbol an appropriate operationalisation of "abnormal public attention", given it measures an investor-framed slice rather than general public interest? | `PENDING` |
| 2 | `BRK-B` — is the hyphenated form acceptable, or must tokenization and the `BRK.B` / `BRK/B` spellings be resolved empirically first? | `PENDING` |
| 3 | `BRK-B` — a sparse or empty series is currently indistinguishable from missing data downstream. Does that need a separate detection rule? | `PENDING` |
| 4 | `GOOGL` — is leakage from `google` mistypings a material threat, and can it be bounded? | `PENDING` |
| 5 | `GME` — does the meme-driven attention regime constitute a different construct from earnings-relevant information arrival? If so, what follows? | `PENDING` |
| 6 | `STZ` and `SYK` — are the streptozotocin and spleen-tyrosine-kinase collisions material in US web search? | `PENDING` |
| 7 | `DELL` — does the query measure product/support demand rather than investor attention, and does that matter for HYP-01? (Note: DELL is the sole registered prospective event.) | `PENDING` |
| 8 | Should Google topic entities be enumerated and evaluated as a systematic remedy for acronym and spelling collisions? | `PENDING` |
| 9 | Is the current query's volume adequate for a stable 12-week z-score on low-search-volume issuers such as `LDOS`? | `PENDING` |
| 10 | If any query changes, how should the existing historical series -- all collected with the bare-ticker query -- be treated so historical and prospective measures stay comparable? | `PENDING` |
| 11 | Does Google Trends series revision behaviour need to be characterised before collection begins? | `PENDING` |
| 12 | Anything this audit gets wrong, or any threat it failed to consider. | `PENDING` |

## Overall disposition

| Field | Entry |
|---|---|
| Tickers approved for continued collection (list) | `PENDING` |
| Tickers requiring empirical comparison (list) | `PENDING` |
| Tickers requiring a methodology-version proposal (list) | `PENDING` |
| Is gap-audit item F5 closed by this review? | `PENDING` |
| If not, what remains outstanding | `PENDING` |
| Overall disposition | `PENDING` |
| Date | `PENDING` |

## Reviewer confirmation

| Field | Entry |
|---|---|
| Reviewer signature / confirmation | `PENDING` |
| Confirms no query was judged using observed earnings outcomes | `PENDING` |
| Consents to being named in the repository? | `PENDING` |
| Consents to being named in any resulting publication? | `PENDING` |

> Reviewing implies **no endorsement** of the project, no authorship, and no public association. Naming requires explicit consent recorded above.

## Project approval

| Field | Entry |
|---|---|
| Harshith Akurati -- approve the reviewed dispositions? | `PENDING` |
| Date | `PENDING` |
| Signature / confirmation | `PENDING` |
| Dated commit approved | `PENDING` |
| Notes | `PENDING` |

---

## Activation checklist -- none may be ticked yet

- [ ] All 24 per-ticker dispositions recorded
- [ ] Cross-cutting questions answered
- [ ] Conflict-of-interest disclosure completed
- [ ] Reviewer confirmation recorded
- [ ] Harshith Akurati approval recorded
- [ ] Any required empirical comparison separately authorized, designed and pre-declared
- [ ] Any query change expressed as a dated methodology version preserving the current one byte-for-byte
- [ ] Treatment of existing historical series decided, if any query changes
- [ ] **All of the above completed BEFORE the first HYP-01-eligible prospective pre-event capture**

**Until every box is ticked, the current bare-ticker production queries stand unchanged and F5 remains open.**
