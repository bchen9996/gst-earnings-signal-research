# watchlist_log.csv — legacy pre-batch-numbering rows

The header row was corrected on 2026-07-17 to match the current 12-field
schema (`ticker,run_timestamp,week,gst_value,is_partial_week,zscore,is_spike,
signal_tier,days_to_earnings,ambiguous_symbol,eligible_for_options_leg,note`).

Rows from before batch numbering existed only have 10 or 11 fields (no
`signal_tier`/`days_to_earnings` yet) and will read with their trailing
values shifted into the wrong columns under that header. These are all
one-off test runs from before `--batch` was added to
`GST_Live_Signal_Engine.py`, not real ticker-universe scans — exclude them
from any analysis of the log.

**Exclude any row with `run_timestamp` earlier than `2026-07-10T18:09:20`**
(the first real `--batch 1` run). The legacy timestamps currently in the
file are:

```
2026-07-08T23:53:50.843322+00:00
2026-07-09T03:52:59.277364+00:00
2026-07-10T01:25:33.514483+00:00
2026-07-10T16:06:03.173964+00:00
2026-07-10T17:09:07.081894+00:00
2026-07-10T17:09:40.472886+00:00
2026-07-10T17:11:15.280295+00:00
2026-07-10T17:11:48.893168+00:00
2026-07-10T17:22:05.171388+00:00
2026-07-10T17:23:38.658829+00:00
2026-07-10T17:24:11.862855+00:00
```

Every row with `run_timestamp >= 2026-07-10T18:09:20` is a real batch run
(12 fields, aligns correctly with the header).
