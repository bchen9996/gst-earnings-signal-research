# Correction to this directory's SYK finding (same day, before any source change)

`ROOT_CAUSE.md` and `REGRESSION_SUMMARY.md` as first committed (`a0ec503`)
contain one **incorrect** claim. It is corrected here rather than rewritten in
place, matching this project's append-only evidence discipline. The two
release-blocking defects those documents identify are **unaffected** and still
stand.

## What was claimed

That SYK's August interval "fails through the existing production request path"
with HTTP 404, and that this showed production extends its request past the
aggregate watermark — and therefore that the comment at
`GST_Phase2_DailyPanel.py:752` ("widening the generated-chunk horizon to
wall-clock time is harmless") was falsified.

## What is actually true

Production does **not** request past the watermark. In
`get_ticker_wikipedia_daily()` the chunk is *labelled* `chunk_start..chunk_end`
but the HTTP request is issued as:

```
result = fetch_fn(article, chunk_start, req_end, ...)
    where req_end = required_data_end(chunk_end, watermark) = min(chunk_end, watermark)
```

Verified by direct injection against the exact parameters of the 2026-08-05 run
(`end=2026-08-05`, `watermark=2026-08-04`):

| | |
|---|---|
| Chunk generated | `2026-08-01 .. 2026-08-05` |
| **Actual HTTP range requested** | **`2026-08-01 .. 2026-08-04`** |

The `2026-08-01..2026-08-05` request recorded under the label
`B1:SYK:production` in `diagnostic2_result.json` was **my own reconstruction of
the production shape, and it was wrong** — production never issues that range.
The label in that JSON is inaccurate; the recorded transport data itself is
accurate and unchanged.

## Corrected classification

The true production request for SYK is `2026-08-01..2026-08-04`, which was also
probed in the same pass and returned **HTTP 200 with exact 4/4 coverage**.

| Blocker | True production request | Result | Corrected classification |
|---|---|---|---|
| CTSH `2026-07-08..07-14` | `2026-07-08..07-14` | 200, exact 7/7 | Transient failure, **now resolved** |
| INTC August | `2026-08-01..2026-08-04` | 200, exact 4/4 | Transient failure, **now resolved** |
| SYK August | `2026-08-01..2026-08-04` | 200, exact 4/4 | **Transient failure, now resolved** (was: "recoverable by correcting the request end") |

All three prior blockers are therefore transient failures that now succeed
through the unmodified production request path. SYK's 404 during the 02:14Z
panel run was genuinely transient — most plausibly a CDN-cached 404 for that URL
at that moment, consistent with Defect 2's cache-age findings.

The `GST_Phase2_DailyPanel.py:752` comment is **accurate as written** and was not
falsified. It is nonetheless superseded by the two-stage correction, which sets
the request horizon to the aggregate watermark directly rather than relying on
downstream truncation — so the comment is being rewritten to describe the new
design, not because it was wrong.

## What is NOT affected

Both release-blocking defects in `9990c39` stand exactly as documented:

1. **Unpaced probe loop → 429 storm** (`unpaced_24ticker_429_sequence.csv`) —
   9/24 measured, `failed_closed`, every run PARTIAL.
2. **Request-shape-dependent availability**
   (`request_matrix_ADBE_GOOGL_CTSH_INTC_SYK.csv`) — ADBE and GOOGL return
   `2026-08-04` for `07-22..08-04` but not for `08-01..08-04`, seconds apart.
   A separate fixed-14-day probe cannot certify what the calendar-chunk request
   returns.

Defect 2 is if anything **strengthened** by this correction: the disagreement is
purely between request shapes, with no request-horizon bug to attribute any of
it to.

## Consequence for the corrective work

Unchanged. The two-stage anchor-month design is still required, for the reasons
in `ROOT_CAUSE.md` §"Corrective direction". What changes is only that "never
request past the aggregate watermark" is now a property to *preserve explicitly*
in the new Stage-1 request, not a bug to fix.

Leaf recovery remains unjustified — now more clearly so, since all three
intervals succeed through the production path.
