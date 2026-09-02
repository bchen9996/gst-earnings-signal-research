# HYP-04 session handoff — 2026-09-01

For a fresh chat picking this up. Read §1 and §2 before touching anything.

**Repo:** `C:\Users\bchen\Quant_Research_Project`
**Branch:** `hyp04-phase0` @ `a4b2e6c`, clean, pushed to `origin`
**Interpreter:** `.venv\Scripts\python.exe`, `PYTHONPATH=.`, cwd = repo root

---

## 1. Rules that are not negotiable

These are safety properties, not preferences. Breaking one silently is the
failure mode this whole project is built against.

| | |
|---|---|
| **Pushing to the fork** (`origin` = `bchen9996/gst-earnings-signal-research`, branch `hyp04-phase0`) | routine, no need to ask |
| **Anything reaching UPSTREAM** | needs explicit approval **every time** |
| **Never fabricate linkage data** | a wrong peer ticker is fabricated linkage wearing a number |
| **Never claim any quantum result is validated** | theirs or ours |
| **Do not bypass Smart App Control / Application Control** | report it, work around it, never disable it |
| **`yfinance` stays OUT of `requirements-hyp04.txt`** | stated safety property; it is installed in the venv only |
| **SEC fair-access UA** | `bchen9996 bchen9996@gmail.com` — owner-supplied for this purpose only; never send it anywhere else |
| **Live runners need staged go-ahead** | named off `test_*` on purpose: `run_canary_audit`, `run_full_audit`, `run_linkage_history`, `run_peer_closes_fetch`, `run_peer_lineage_audit`, `run_peer_name_search` |

**Assert after every change: gate CLOSED, C4 MET, exactly 4 denials, eligible
count 0.** Current state confirmed:

```
C1_status=False  C2_threshold=False  C3_frozen=False
C4_decisions_resolved=True  C5_not_placeholder=False
```

**C2 and C3 move together or not at all.** `display_gate.current_decision()`
passes a literal `eligible_event_count=0` and cross-checks it against a freeze
record that does not exist. Producing shocks, ceilings or draft rows cannot move
either. That repoint is a separate, separately-authorised step.

**Working style the owner asked for:** run everything unblocked, then surface
gated decisions in batches with a recommendation. Don't stop to ask about things
you can measure.

---

## 2. Where the project actually is

**Anchor side: finished.** 324 of 342 calendar events carry a measured shock
(`HYP04_ANCHOR_SHOCKS_2026-08-31.{json,csv}`). 18 denied, all AS-1 (release
session UNKNOWN); **zero** denied for missing closes.

**Peer side: blocked, and the blockers are correctly ordered.**

| | |
|---|---|
| curated map's ceiling | **54** anchor events |
| registered floor (C2) | **193** |
| reachable if the 5 draft rows are curated | **215** |
| reachable if all 35 queue candidates were | 324 |

**Curation binds before prices.** The ceiling run already *assumes* peer prices
exist, so buying a price source today would not raise 54 by one event. Do not
describe the price source as the last blocker.

**The immediate next action is the owner's**, not yours — see §3.

---

## 3. What is waiting on the owner

### 3a. Five draft linkage rows

`Live Signal Engine/HYP04_LINKAGE_ROWS_DRAFT_2026-08-31.csv` —
JBL→CSCO, JBL→AAPL, JBL→BB, NVDA→MSFT, INTC→HPQ.

Every derivable field is filled. **Five fields are blank and only a human may
fill them:** `confidence`, `date_confidence`, `curated_by`, `curated_date`,
`review_status`. All five are in `curated_linkage.REQUIRED_FIELDS`, so the
loader rejects every row while they are blank:

```
header_matched=True  rows_seen=5  rows_rejected=5  edges_usable=0
uses_placeholder_linkage=True     <- C5 stays shut
```

**Never pre-fill those five.** That inertness is the only thing between a
machine-prepared candidate and a production edge, and it is asserted against the
real file in `test_hyp04_supply_chain_hedge_linkage_draft.py::test_2`.

**When the owner does curate**, the rows go into a NEW map,
`HYP04_Linkage_Map_v1.1.csv`. Never edit `v1.0` in place — see the trap in §5.

### 3b. The peer price source — DEFERRED by decision (2026-09-01)

No registry v1.11. Revisit only when the ceiling clears 193.

`peer_price_data_policy` permits a survivors-only restriction "only if the
restriction and its bias are stated in the registry version that does it". The
bias is measured and on record: **109 of 270** incremental events sit behind
names the resolver structurally cannot reach.

---

## 4. Owner decisions already taken — do not relitigate

| date | decision |
|---|---|
| 2026-08-29 | HYP-04 tests **information transmission**; P1 requires a well-measured anchor shock, not HYP-01's attention screen |
| 2026-08-31 | reference window is **day-0 exclusive** (ends `anchor_day − 1`); day-0-inclusive is the robustness variant |
| 2026-08-31 | anchor prices: Yahoo via the existing fetcher, **split and dividend adjusted** |
| 2026-08-31 | every event gets a row — computed **or** with a stated denial |
| 2026-09-01 | name→ticker is **exact match only**; ambiguous/self-link/near-miss stay UNRESOLVED |
| 2026-09-01 | price source **deferred**; draft rows prepared; unreachable names searched |

---

## 5. Traps — every one of these has already bitten

**A merger is not a rename.** Caremark RX rejected for MCK, OfficeMax for PKG.
An `as_of_date` never moves back through an acquisition.

**`HOLDING` / `HOLDINGS` / `GROUP` must never rejoin `peer_ceiling.NAME_SUFFIXES`.**
They are not legal forms. Stripping them resolved ADBE's 2006 "Ingram Micro"
onto INGM — CIK 1897762, first SEC filing **2022-04-13**, sixteen years later.
A name collision is only detectable when both parties survive, which is when it
matters least.

**The authoritative XNYS calendar's bound ROLLS.**
`gst_market_response.exchange_calendar` builds `get_calendar("XNYS")` with no
`start`, giving a 21-year window ending a year ahead — its first session is
*today − 20 years* and moves forward one day per day. Never pin a test to that
literal date. HYP-04 uses `sessions.py` with a fixed 1995 start, verified to
agree with the authoritative instance across the whole overlap.

**Two readers of the linkage map pull in OPPOSITE directions, on purpose.**
- `dashboard.read_curated_linkage` → **newest** map. The page must show what is
  in force.
- `make_registry_v1_3.observed_linkage_state` → **pinned** to `v1.0` by name and
  sha256. v1.3 is frozen, its `availability_basis` quotes that map and hash, and
  test 9a asserts the artifact matches what the generator builds. Pointing it at
  a newer map would make frozen evidence drift. It raises `PinnedMapChanged` if
  the file moves.

**Artifact selection is version-aware** (`artifacts.py`). Lexical sort puts
`_v10` before `_v2`, and `_v1.10` before `_v1.2`. Use `artifacts.newest` /
`newest_in`, never `sorted(...)[0]` or `[-1]`.

**Broken is not absent.** A corrupt artifact must render a blocker, not vanish.
Same class as recording an HTTP 503 as "no registrant matched" — an unanswered
question reported as an answer.

**`_get` vs `_get_json`.** `EdgarClient._get` is raw transport *below* the cache
and *below* the `offline=True` guard. Always use `_get_json` / `_get_text`.

**Heredocs mangle backslash escapes in this environment.** `\n` and `\xff` in a
`<<'PY'` heredoc have both been written as literal newlines and raw bytes,
corrupting the target file. Use the Write/Edit tools for anything with escapes.

**Tests that grep source text match your own comments.** Two checks have failed
against comments explaining the very bug they were checking for. Assert against
AST imports or comment-stripped code.

---

## 6. Map of the code

```
hyp04_supply_chain_hedge/
  display_gate.py        the five-condition fail-closed gate — read first
  curated_linkage.py     the curated schema + validating loader (REQUIRED_FIELDS)
  pair_eligibility.py    P1..P7, the only module entitled to say "eligible"
  linkage_resolution.py  the join; derives uses_placeholder_linkage, never accepts it
  anchor_shock.py        HYP04-ANCHOR-SHOCK-RULE-v1, log returns, beta fixed at 1.0
  anchor_calendar.py     342 candidate events from 8-K item codes
  earnings_events.py     8-K item eras (Item 12 -> 2.02 on 2004-08-23)
  sessions.py            HYP-04's own XNYS index, fixed start, verified
  artifacts.py           version-aware newest-artifact selection
  peer_ceiling.py        HYP04-PEER-CEILING-RULE-v1; ceiling, worklist, survivorship
  peer_lineage.py        HYP04-PEER-LINEAGE-RULE-v1; was this the company named then?
  peer_name_search.py    HYP04-PEER-NAME-SEARCH-RULE-v1; find vanished registrants
  make_*.py              offline artifact builders (refuse to overwrite)
  run_*.py               LIVE, staged, --yes-run-live
  dashboard.py           derives everything at render time; asserts nothing stale
```

**39 test suites**, `test_hyp04_supply_chain_hedge_*.py`. No pytest — hand-rolled
`check()` / `skip()` / `FAILURES`, `sys.exit(1)`, sockets blocked before imports.
`test_..._inference.py` takes ~3m20s (bootstrap); everything else is seconds.

---

## 7. Verification — run this after any change

```powershell
cd "C:\Users\bchen\Quant_Research_Project"
$env:PYTHONPATH="."
foreach ($f in Get-ChildItem test_hyp04_supply_chain_hedge*.py) { .\.venv\Scripts\python.exe $f.Name }
.\.venv\Scripts\python.exe test_market_response_canonical_drift.py
.\.venv\Scripts\python.exe test_market_response_cohort_protocol.py
.\.venv\Scripts\python.exe -m hyp04_supply_chain_hedge.dashboard `
  --out "Live Signal Engine\HYP04_PHASE0_DASHBOARD.html"
```

**Required every time:** 39 suites green; dashboard `all_green=True` with counts
read **from the regenerated page**, never from memory; gate CLOSED / C4 MET /
4 denials / eligible 0; registries **v1.3–v1.10 byte-identical by hash**.

Pinned registry hashes (first 24 hex):

```
v1.3  03ef40768fa4a45b6192166a    v1.7   abe45f4d6ff2a78b03439709
v1.4  b7900bcd5c6676da1221dcdc    v1.8   574baa5dc4b86b73b4f76ea4
v1.5  731ee4f2228477ee6e920045    v1.9   e7c0b3b746382b0ee7a79445
v1.6  1cce4dcb926640a497337bfa    v1.10  d960190c8202a55bc426ecca
```

Curated map `HYP04_Linkage_Map_v1.0.csv` sha256 must stay
`e7b0881186751f32c5f56633a3a8809824ccdfee4485e8e4a3ce368795b371d4`.

---

## 8. Artifact conventions

Dated, **append-only**. A superseded version stays **byte-identical** on disk;
same-day revisions get `_vN` and record the predecessor's sha256, and the suites
assert those hashes still match. A superseded artifact that quietly changed
would make a correction unauditable.

Current heads: peer ceiling `_v3`, worklist `_v3`, lineage audit `_v2`, anchor
calendar `_v2`, name search (2026-09-01, no revision).

Three untracked superseded walk files
(`HYP04_EDGAR_LINKAGE_HISTORY_FULL51_2026-08-27{,_v2,_v3}.json`) stay untracked
**by owner decision** — leave them.

---

## 9. Open items, in the order they bind

1. **Five draft rows** → owner fills five fields → `HYP04_Linkage_Map_v1.1.csv`.
   Takes reach 54 → 215.
2. **Peer price source** — deferred; revisit once the ceiling clears 193.
3. **145 anchor events** behind registrants that are identified, lineage-
   confirmed and **no longer traded** (DELL, INGRAM MICRO, TECH DATA, FOOT
   LOCKER). Documented, not recoverable from a survivors-only source.
4. **11 counterparty names** no EDGAR search could match.
5. **C2/C3 repoint** plus a freeze record — separate, separately authorised.

---

## 10. The standard that has held all session

Nothing in HYP-04 is evidence about supply-chain transmission. No result,
direction, effect estimate, plot, p-value or confidence interval exists, and
none may be displayed while the gate is closed.

Counts of *data availability* are publishable (how many events carry a shock).
Measured *properties* are not (what those shocks are). The dashboard shows the
former and deliberately withholds the latter.

Every guard gets a control proving it can fail. A guard nobody has seen fail is
not known to work — the lineage audit refuses to write unless its INGM control
produces a break.
