# Two defects in yesterday's worklist, and the lineage check that follows

**Dated finding, 2026-08-31.** Append-only. Corrects
[`HYP04_PEER_CEILING_FINDING_2026-08-31.md`](HYP04_PEER_CEILING_FINDING_2026-08-31.md).

**Artifacts:**
[`HYP04_PEER_CEILING_2026-08-31_v2.json`](HYP04_PEER_CEILING_2026-08-31_v2.json) ·
[`HYP04_PEER_CURATION_WORKLIST_2026-08-31_v2.csv`](HYP04_PEER_CURATION_WORKLIST_2026-08-31_v2.csv) ·
[`HYP04_PEER_LINEAGE_AUDIT_2026-08-31_v2.json`](HYP04_PEER_LINEAGE_AUDIT_2026-08-31_v2.json)

> **The display gate is CLOSED, C4 MET, four denials, eligible-event count
> zero.** Nothing here is evidence about supply-chain transmission.

---

## 1. A wrong ticker, produced by my own normaliser

The v1 worklist resolved ADBE's 2006-02-08 disclosure of **"Ingram Micro"** onto
**INGM**. That is wrong.

`normalize_company_name` stripped `HOLDING` as though it were a legal form, so
"Ingram Micro" matched **Ingram Micro Holding Corp** (CIK 1897762) — the 2024
re-IPO vehicle, not the Ingram Micro Inc. that ADBE's filing named. SEC's own
record settles it: that registrant's **first filing is 2022-04-13**, sixteen
years after the disclosure.

`HOLDING`, `HOLDINGS` and `GROUP` are not legal forms. They are exactly what
separates a holding company from its operating company, and a successor vehicle
from its predecessor. They have been removed from `NAME_SUFFIXES`.

Measured across SEC's 10,391-entry map, those three tokens merged **5 distinct
registrant pairs**, among them `TARGET CORP` / `Target Group Inc.` and
`GRAHAM CORP` / `Graham Holdings Co`. Four of the five collapsed onto a name
carrying two tickers and were caught as AMBIGUOUS.

**Ingram Micro was the dangerous one**: its predecessor is no longer a filer, so
there was nothing to be ambiguous *with* and the wrong ticker resolved silently.
A collision is only detectable when both parties survive — which is precisely
when it matters least. That asymmetry is the reason this defect was worth
chasing rather than patching quietly.

Resolved candidates fall from 8 to **7**. The Ingram Micro row is now
UNRESOLVED, which is the correct answer.

## 2. The headline number was the wrong quantity

v1 reported "**231** distinct anchor events spanned by the 8 resolved
candidates" against a floor of 193, and called that the material to reach the
floor. Two things are wrong with it.

**It was gross, not incremental.** Two of the eight resolved rows were
`MCK → CVS` at as-of dates *later* than the curated edge's 2013-05-07, so their
events are a strict subset of what the map already reaches. Their gross counts
(41 and 26) sat in the ranking looking like opportunity. They add **zero**.

**And it was neither the increment nor the total.** The corrected figures:

| | v1 | v2 |
|---|---|---|
| ticker-resolved candidates | 8 | **7** |
| flagged dominated by the curated map | — | **4** |
| gross union, resolved | 231 | 202 |
| **incremental over the curated map** | — | **161** |
| **reachable total if all resolved were curated** | — | **215** |
| reachable total if all 35 were curated | — | **324** |
| registered floor | 193 | 193 |

215 still clears 193, by 22 events rather than the 38 v1 implied. The worklist
now ranks by **incremental** opportunity and flags `dominated_by_curated_map`,
so a curator is not invited to spend effort on a row that buys nothing.

## 3. The lineage flag is now evidence

v1 marked every resolved row `requires_lineage_review=yes` — honest, but inert.
It named a question and left all of it to the curator.

`HYP04-PEER-LINEAGE-RULE-v1` answers the mechanical part from SEC's own record,
at **one request per registrant**: `formerNames` carries `from`/`to` windows, so
the name in force at any date is a lookup; `filings.files[]` carries
`filingFrom`/`filingTo`, so the full filing history is bounded without fetching
the older shards.

That makes one part decidable. **A registrant whose first filing postdates the
disclosure cannot be the company that disclosure named.** So does the converse,
for one that stopped filing before it.

All **7** candidates came back `continuous_under_this_name`. The derivation is
doing real work rather than reading today's name back through history — it
returns *2002's* `CISCO SYSTEMS INC` for the JBL disclosure, and `APPLE INC`
rather than `APPLE COMPUTER INC` for 2012.

## 4. Seven passes are worth nothing without a control

Every candidate passing is exactly the condition under which a check has never
been observed to fail — and this project's own rule is that **a guard nobody has
seen fail is not known to work.**

So the audit runs the case that motivated it. INGM at 2006-02-08 **must** come
back a lineage break, and if it does not the runner **refuses to write
anything**. It fires:

> `LINEAGE_BREAK_first_filing_postdates_disclosure` — the registrant's first
> filing is 2022-04-13, AFTER the 2006-02-08 filing that named 'Ingram Micro'.

The control is not a candidate. It never enters `assessments`, and the
normaliser fix already removed that row from the worklist.

## 5. What CONTINUOUS does not mean

It removes **one** way of being wrong. A merger that preserved both the name and
the registrant would pass this check and still be the wrong peer — which is how
**Caremark RX** and **OfficeMax** were caught, on the merits, not by any test.

One known limit is already visible in the results. `INTC → HPQ` passes: CIK
47217 was filing in 2017 under the name "HP Inc". But that registrant spun off
Hewlett-Packard Enterprise in 2015, so the company continued while a large part
of its business left. INTC's filing named HP Inc specifically, so the match is
right — but no filing-history test can see an event like that. It is judgement,
and it stays with the curator.

A registrant filing under a *different* name at the disclosure date is reported
as `REVIEW_name_not_in_force_at_disclosure`, never resolved here: it may be a
subsidiary, a brand, or the wrong company.

## 6. What this does NOT do

- **It curates nothing.** No row promoted, no edge written, no candidate
  cleared for use. A CONTINUOUS verdict is not an eligible pair.
- **It does not move C2 or C3**, which move together or not at all.
- **215 is not a met threshold.** It assumes 7 unreviewed candidates are all
  curated, their as-of dates ratified, and peer prices obtained. None holds.
- **It measures no transmission.** No peer return has been computed.

## 7. Supersession

`HYP04_PEER_CEILING_2026-08-31.json`, its worklist, and
`HYP04_PEER_LINEAGE_AUDIT_2026-08-31.json` remain on disk **byte-identical**.
The v2 artifacts record their SHA-256s, and the suite asserts those hashes still
match — a superseded artifact that quietly changed would make the correction
unauditable.

The v1 lineage audit is superseded only for lacking the control; its seven
verdicts are unchanged.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
