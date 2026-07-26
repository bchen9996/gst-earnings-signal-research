# Wikipedia Pageviews vs. GST Z-Score: Independence Check

Data-quality / independence check only. **Not a hypothesis test, no PASS/WEAK/FAIL
bucket applies.** Purpose: determine whether Wikipedia pageview attention is
distinct enough from Google Trends attention to justify a future pre-registered
hypothesis test, using the already-committed
`Wikipedia_Pageviews_ZScore_PerEvent.csv` (commit `74e864a`).

## Data checked

- 152/152 rows present, matching the full canonical population.
- `gst_zscore`: 0 nulls.
- `wiki_zscore`: 0 nulls.

## Correlation

- Pearson r = **0.2442**, p = 0.0024, n = 152 (r² ≈ 0.060 — GST z-score explains
  about 6% of the variance in Wikipedia z-score).
- Spearman rho = 0.1646, p = 0.0428 (weaker and only marginally significant on
  ranks, consistent with the relationship being driven partly by a handful of
  large joint spikes rather than a uniform monotonic trend).
- Same-sign agreement: 107/152 events (70.4%) have `gst_zscore` and `wiki_zscore`
  on the same side of zero.

## Important caveat on scale comparability

`gst_zscore` is **not free-ranging**: the 152-event population is itself defined
by `qualifies_z5` (GST z-score ≥ 5), so `gst_zscore` has a hard floor at 5.023 and
a max of 31.10 by construction. `wiki_zscore` is unrestricted and centers near
zero (min -5.33, max 23.76). Because of this asymmetry, simple magnitude-ratio
comparisons (e.g. "is one z-score >2x the other") are mechanically dominated by
the fact that `gst_zscore` can never be small — 131/152 events trivially satisfy
`|gst_zscore| > 2 * |wiki_zscore|` for this reason alone, and that count should
not be read as evidence of divergence by itself. The more informative diagnostics
are the ones below, which don't depend on comparing the two scales directly.

## Divergence diagnostics

- Events where `wiki_zscore` ≥ 5 (i.e., Wikipedia attention rises to a magnitude
  comparable to the GST selection threshold): **13/152 (8.6%)**.
- Events where `wiki_zscore` ≥ 2 (moderate Wikipedia spike): **36/152 (23.7%)**.
- Events where `wiki_zscore` < 0 (Wikipedia attention *below* its own trailing
  baseline despite a qualifying GST spike): **45/152 (29.6%)**.

In plain terms: for the large majority of events that trigger a GST-based
signal, Wikipedia pageviews do not show a comparably large spike, and nearly a
third actually run below their own baseline at the same anchor week.

## Reading

The correlation is statistically detectable (p = 0.0024) but **low in
magnitude** (r ≈ 0.24, ~6% shared variance). Combined with the divergence
diagnostics above — most GST spikes are not accompanied by a comparably sized
Wikipedia spike, and about 30% of events show below-baseline Wikipedia attention
at the same anchor — this does not look like a redundant, GST-shadowing signal.
It looks **independent enough** that a real, pre-registered test of Wikipedia
pageviews as its own predictor (rather than as a GST proxy) would be a
reasonable next step, if pursued.

No hypothesis pre-registration has been created as part of this check. This note
is descriptive only.
