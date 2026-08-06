# Phase2_Wikipedia_Cache.csv — hashes and growth summary (2026-08-02 run)

`Phase2_Wikipedia_Cache.csv` is not committed in this evidence commit — it
is a volatile, local, untracked operational cache per this branch's
existing cache-persistence policy. Recorded here for audit only.

| | SHA-256 |
|---|---|
| Before this run (= after the 2026-08-01 run) | `bbebda7b94f8d12681f3635eef299b8955e73244b394b140c530f627c6b346ec` |
| After this run | `f9e89ccf03d66a3064e42b5b2933e80f202e0aba82d14ac897408ed3c73a3c69` |

Hash changed (expected): this run performed 45 fresh-fetch successful
chunk requests plus additional second-pass fetch attempts (33 chunks
retried across 16 tickers, 19 of which succeeded). Post-run row count:
**8,137**.

All 6 other pre-existing untracked artifacts in the working tree (the
2026-08-01 checkpoint/marker, the AMZN-only validation JSON, and the
2026-08-01 log/timing-log pair) were independently re-hashed before and
after this run and are byte-identical — only the cache grew, and only
through legitimate additive fetches. See `cache_integrity_summary.md` for
the conflict scan confirming no row was overwritten with a disagreeing
value.
