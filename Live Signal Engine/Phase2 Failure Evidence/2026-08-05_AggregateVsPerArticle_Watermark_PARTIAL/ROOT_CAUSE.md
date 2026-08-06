# Root cause — aggregate watermark is not per-article availability

**One sentence:** the run measured its data watermark from the Wikimedia
**aggregate** pageviews endpoint, then enforced exact date coverage against
the **per-article** endpoints — two different publication pipelines — so
when the aggregate had published `2026-08-04` but only 5 of 24 article
endpoints had, 19 tickers failed coverage validation and the panel went
PARTIAL.

## The mechanism, step by step

1. At `02:14:38Z` the run probed
   `.../metrics/pageviews/aggregate/en.wikipedia.org/all-access/user/daily/2026080400/2026080400`,
   got HTTP 200 with data, and set `watermark = 2026-08-04` (lag = 1 day).
2. `required_data_end(chunk_end, watermark)` truncated the open-month chunk
   `2026-08-01..2026-08-05` to a required coverage window of
   `2026-08-01 … 2026-08-04` — **4 expected dates**.
3. For each ticker the run fetched
   `.../per-article/en.wikipedia/all-access/user/<Article>/daily/20260801/20260805`.
4. `validate_snapshot()` requires `actual_dates == expected_dates` exactly.
   Only 5 articles returned all four dates. The rest returned HTTP 200 with a
   short series and were rejected `incomplete_coverage`.

The 5 that passed — DVN, GPN, SBUX, STZ, TSLA — are exactly the 5 tickers
whose `2026-08-01..2026-08-05` rows appear in
`cache_mutation_manifest.csv`, each with `date_min=20260801`,
`date_max=20260804`. That is the direct fingerprint of the truncation
working correctly and the per-article data simply not being there for the
other 19.

## Why this is not a defect in the code under test

The second pass re-fetched all 17 incomplete chunks ~16 minutes later
(`02:30`–`02:32`). Every one returned HTTP 200 again and failed validation
again — so this is not transient network flakiness, a rate limit, or a
timeout. The articles genuinely did not have `2026-08-04` published yet,
roughly 2.2–2.5 hours after the `2026-08-04` UTC day closed.

Cross-run evidence isolates watermark **lag** as the discriminator, not the
branch under test:

| Run | Aggregate watermark | Lag | `all_six_fields_clean` | wiki failures |
|---|---|---|---|---|
| 2026-08-02 | 2026-08-01 | 1 | 0 / 24 | 8 |
| 2026-08-03 | 2026-08-01 | **2** | **22 / 24** | 2 |
| 2026-08-05 | 2026-08-04 | 1 | 5 / 24 | 19 |

Both lag-1 runs failed broadly; the single lag-2 run nearly passed. Code
changed between those runs; the lag correlation survived it.

## Relationship to the 2026-08-01 correction

The 2026-08-01 fix (see `../2026-08-01_Wikipedia_SourceWatermark_Lag2/`) was
correct as far as it went: it removed the "a closed month always needs its
own `chunk_end`" assumption and made the *measured watermark* the single
source of truth for open and closed chunks alike. The residual gap is one
level up — the measured watermark is measured from a **different endpoint
than the one it gates**. A single aggregate probe cannot certify 24
independent per-article publication states.

## What this does NOT explain

Three failures this run are a **separate, pre-existing** defect class and
are not addressed by any watermark change:

- CTSH `2026-07-01..2026-07-31` — HTTP **404** on both passes; bounded
  subchunk recovery recovered 4 of 5 subchunks but `2026-07-08..2026-07-14`
  failed, leaving `missing 7 of 31 date(s)`. This is an **internal
  historical gap**, not trailing publication lag.
- INTC and SYK `2026-08-01..2026-08-05` — HTTP **404** on both passes.

Any fix that lowers the effective watermark must **not** mask these. An
internal gap in the middle of the required lookback has to keep producing
PARTIAL. CTSH's July 8–14 hole is the canonical regression case for that.

## Fix direction (not implemented in this evidence commit)

Retain the aggregate probe as a source-health/provenance observation, but
derive the binding watermark from **validated per-article observations**:
take each locked ticker's latest genuinely observed HTTP-200 date and use
the **minimum across all 24** as one panel-wide effective watermark, applied
identically to every ticker's `pull_start`, expected coverage, z-score
anchoring and provenance. That addresses trailing lag only — exact coverage
through the effective watermark must still be required of every ticker, so
CTSH stays PARTIAL until legitimately recovered.
