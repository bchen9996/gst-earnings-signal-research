# 425-Ticker Batch Scan — Coverage Status

**No such tracking document existed before this file.** Searched
directly before creating it — nothing in this project recorded which of
`GST_Live_Signal_Engine.py`'s 9 batches (425 tickers, `DEFAULT_BATCH_SIZE=50`,
fixed-size slicing in ticker-list order — verified against the actual
`main()` logic, not assumed) had been run. This file is the first record
of that status, created 2026-07-26 when batch 9 (the last untouched
batch) was run.

**Batch definition** (`GST_Live_Signal_Engine.py`, `TICKERS` list, 425
entries): `ticker_batches = [TICKERS[i:i+50] for i in range(0, 425, 50)]`
— 8 full batches of 50, 1 partial final batch of 25.

| Batch | Tickers | Range | Status | Run date |
|---|---|---|---|---|
| 1 | 50 | 1-50 | Run | 2026-07-10 |
| 2 | 50 | 51-100 | Run | 2026-07-12 |
| 3 | 50 | 101-150 | Run | 2026-07-15 |
| 4 | 50 | 151-200 | Run | 2026-07-15 |
| 5 | 50 | 201-250 | Run | 2026-07-17 |
| 6 | 50 | 251-300 | Run | 2026-07-17 |
| 7 | 50 | 301-350 | Run | 2026-07-19 |
| 8 | 50 | 351-400 | Run | 2026-07-23 |
| 9 | **25** | **401-425** | **Run** | **2026-07-26** |

**All 9 batches / 425 tickers now have at least one recorded scan.**
Batch run dates for 1-8 are taken from the `watchlist_<timestamp>_batchN.csv`
filenames already on disk, not re-verified here beyond confirming those
files exist — batch 9 (this entry) is the one verified end-to-end as
part of writing this document.

**Batch 9 result (2026-07-26T21:14:48Z)**: 25/25 tickers scanned
successfully. 1 flagged (`is_spike=True`): **WAT, z=2.026, tier
STANDARD** (2≤z<5, reference-only — does not clear the z≥5 STRONG bar,
and has no known earnings date in this run, so it cannot be
HIGH_CONFIDENCE_STRONG_EARNINGS or STRONG_EARNINGS either). **0 STRONG,
0 STRONG_EARNINGS, 0 HIGH_CONFIDENCE_STRONG_EARNINGS.** No event in this
batch rises to a tier that would add genuinely new information beyond
what the existing 29-ticker multi-ticker forward log already tracks.
Full detail: `Live Signal Engine/watchlist_2026-07-26T21-14-48Z_batch9.csv`,
appended to `watchlist_log.csv`.

**What "coverage complete" does and doesn't mean:** this confirms every
one of the 425 tickers has been scanned for its z-score condition **at
least once** — a one-time snapshot per ticker, not a repeating schedule.
Unlike the 29-ticker multi-ticker forward log (`gst-multiticker-forward-log`,
scheduled daily via GitHub Actions), this 425-ticker batch scanner has no
automation and no recurring cadence — each batch's reading reflects GST
conditions only at the moment it was run, on a different date for each
batch (spanning 2026-07-10 through 2026-07-26 across all 9 batches, per
the table above). A future re-scan of any batch would very likely show
different z-scores.
