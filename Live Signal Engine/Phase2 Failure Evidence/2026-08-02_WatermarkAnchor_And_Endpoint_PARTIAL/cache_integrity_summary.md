# Cache-integrity scan — 2026-08-02 run (read-only, post-run)

Scanned the full operational `Phase2_Wikipedia_Cache.csv` (8,137 rows, all
24 tickers) after this run completed.

## Duplicate-key check

Grouped by `(ticker, configured_article_title, date)` — the true daily
identity key (`canonical_title` is not yet populated for any row in this
cache; canonical Wikipedia title/page-ID verification remains a
documented, disclosed limitation, unrelated to this run).

- Unique `(ticker, article, date)` keys: 7,208 of 8,137 rows
- Rows belonging to a duplicated key: 1,494 (565 groups)
- Groups where `pageviews` genuinely **disagrees** across duplicate rows: **0**
- Groups where only `content_hash` differs (pageviews identical): 565

**Interpretation:** the 565 "duplicate" groups are not an integrity
problem. `content_hash` is computed per-chunk (a hash of the whole
`(ticker, chunk_start, chunk_end)` response), not per-day, so the same
calendar date appearing in two different chunk-boundary fetches
(e.g., yesterday's rolling window vs. today's) legitimately produces two
rows with different `content_hash` values even when the underlying daily
`pageviews` figure is identical, which it was in all 565 cases checked. No
row was overwritten with a conflicting value; no genuine identity
conflict was found.

## Invalid-pageviews check

- Negative, fractional, or null `pageviews` values: **0** (all 8,137 rows
  hold non-negative integers, consistent with
  `_is_valid_nonnegative_integer_pageviews()`'s existing validation).

## Coverage-union check (informs the endpoint-failure diagnostic)

For each of the 8 endpoint-failure tickers' failed chunk intervals, this
run additionally checked whether the exact calendar dates required were
already present *somewhere* in the cache under a different
`(chunk_start, chunk_end)` key pair (see `endpoint_failure_8_tickers.csv`
for the full per-ticker breakdown). Confirmed: `cached_daily_rows_for_chunk()`
in `GST_Phase2_Wikipedia_Transport.py` filters on an **exact**
`(ticker, chunk_start, chunk_end)` match — it does not look up by
individual `date` across all of a ticker's cached rows — so a date that is
already fully cached under a different chunk-boundary key (e.g., from a
prior day's rolling window) is invisible to today's lookup and triggers a
fresh network request, which can then hit the already-documented
per-article endpoint flakiness. This is a design characteristic of the
current chunk-keyed cache, not a data-integrity defect — see
`ROOT_CAUSE_CLASSIFICATION.md` and the composite-snapshot design proposal
for the forward-looking discussion.

**Conclusion: cache integrity is clean.** No corrective action taken or
required against the cache itself.
