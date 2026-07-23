# GDELT Pre-Spike News Volume Test — TERMINATED, INCONCLUSIVE

**Status: TERMINATED before completion. This is NOT a completed test and NOT a null finding.**

## What happened

`GST_GDELT_PreSpike_NewsVolume_Test.py` was launched as a background job to test
whether pre-spike GDELT news article volume differs between STRONG_EARNINGS
events (Group A, n=209) and non-spike earnings-adjacent weeks (Group B, n=110).
The estimated minimum runtime at launch was 5.8 hours, based on GDELT's stated
rate-limit policy of one request per 5 seconds (with padding for this
environment's observed need for ~65s+ spacing).

It was manually terminated (`TaskStop`) at **2026-07-12 10:37 AM**, after running
for **approximately 17.3 hours** (since 2026-07-11 17:16:35), because:

- Only **167 of 319 total events** had been attempted (167/209 through Group A;
  **Group B — all 110 non-spike events — was never started**).
- Of those 167 attempts, only **80 succeeded (47.9%)**; **87 failed (52.1%)** —
  a mix of HTTP 429 rate-limiting exhausted after 4 retries, connection
  timeouts, and connection resets from GDELT's API.
- At the observed rate (~9.7 events/hour), completing the remaining 152 events
  would have required roughly 16 more hours, pushing total runtime past 33
  hours with no guarantee the failure rate would improve.

## Why this is "inconclusive," not "no effect"

**Do not cite this test as evidence that GDELT news volume shows no pre-spike
signal.** No permutation test was ever run — Group B has zero data points, so
the two-group comparison this test exists to perform was never computed. The
partial Group A data that DOES exist (80 successful pulls) is not a random or
representative sample of Group A either — it reflects whichever events
happened to succeed against GDELT's rate limiting during the specific hours
this job ran, which is not a controlled or unbiased subset.

The correct characterization: **GDELT, as accessed from this environment,
could not reliably retrieve enough data to run this test.** This is a data
access failure, not a research finding about news volume and GST spikes.

## Raw partial data

The 167 attempted rows (80 successes, 87 failures, Group A only) remain in
`Live Signal Engine/GDELT_PreSpike_NewsVolume_Test.csv` for reference/audit
purposes, tagged with their `status` field showing success or the specific
failure reason. **This file should NOT be used to compute a win/loss or
comparison statistic** — it contains no Group B data at all, so any two-group
test built from it would be comparing Group A against nothing.

## If this test is revisited

The core bottleneck is GDELT's rate limiting / connection reliability, not
this project's query construction or pacing logic (which already backed off
significantly beyond GDELT's stated policy). Options for a future attempt:
- Spread the pull across multiple days/sessions rather than one long run.
- Investigate whether GDELT's rate limit is IP-based and improves at a
  different time of day or from a different network path.
- Consider whether the Wikipedia-based signals (pageviews, edit frequency —
  both completed successfully and both showed null results after proper
  within-ticker normalization) already answer the underlying question this
  test was attempting, making a GDELT retry lower priority.
