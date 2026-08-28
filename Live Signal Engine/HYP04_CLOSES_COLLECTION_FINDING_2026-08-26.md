# HYP-04 closes collection — the pipeline works; half the map is unobtainable (2026-08-26)

**Status: FINDING.** The display gate reads **CLOSED, C4 MET, 4 denials** before
and after. Nothing here is evidence about supply-chain transmission.

---

## 1. What was run

Request files emitted from the 98 merged anchor-event candidates, then filled
from Yahoo via `run_peer_closes_fetch.py`:

```
CVS_closes_REQUEST.csv   2193 rows requested
ODP_closes_REQUEST.csv   1722 rows requested
```

## 2. The CVS side works, end to end, on real data

| | |
|---|---|
| MCK events with a resolved session | 56 |
| Pinned onto the real XNYS index | **56, zero rejected** |
| Closes fetched | **2193 / 2193, zero missing** |
| `load_panel` | `loads_clean: True`, 0 rows rejected, 0 off-calendar |
| Finite log returns | 2144 |
| **Coverage sufficient** | **55 / 56** |
| **Finite target at every horizon** | **55 / 55** |

The single failure is `MCK-2026-08-05`, denied with *"horizon window runs past
the session index (needs day 3688, index ends at 3682)"* — its 20-session
horizon has not finished trading. That is the truncation case working, not a
defect.

This is the first time the chain has run on genuine prices. It establishes
that the pipeline computes well-defined numbers. **It establishes nothing
else.**

## 3. The ODP side is unobtainable — and the reason matters

```
ODP: filled 0/1722   missing 1722
$ODP: possibly delisted; no timezone found
```

Not a transient error, and not rate limiting — a control symbol fetched
normally in the same session. Three checks:

| Check | Result |
|---|---|
| Yahoo, recent window | 0 rows |
| Yahoo, 2016 / 2020 / 2024 / 2026 windows | **0 rows at every date** |
| SEC `company_tickers.json` (10,388 tickers) | **ODP / Office Depot absent**; PKG, CVS, MCK all present |

So ODP has ceased to be a publicly traded SEC filer, at some point after
PKG's 10-K of 2026-02-26 — which still named it PKG's largest customer.

**Yahoo does not retain history for delisted securities.** It is not that the
recent quotes stopped; the entire 2016–2026 series is gone.

## 4. This is a survivorship-bias problem, not an inconvenience

A price source that drops delisted securities is **survivorship-biased by
construction**. For a study of supply-chain transmission that is not a
peripheral concern:

- the peers most likely to disappear are those acquired or taken private
- acquisition is frequently *caused by* the commercial relationship being
  studied — a large customer buying, or being bought by, a counterparty
- so the missing observations are not missing at random with respect to the
  hypothesis

Measuring only the peers that survived to today would bias the result in a
direction that cannot be signed without knowing why each disappeared. Using
Yahoo for the peer side systematically excludes exactly the cases most likely
to be informative.

**Half the curated map is affected: one of two edges.**

## 5. What this does not change

- **The two curated edges remain correct.** PKG did disclose ODP as its largest
  Paper-segment customer; the 2016-02-26 as-of date stands. ODP ceasing to
  trade does not retroactively make the relationship false.
- **The 42 PKG anchor events remain correctly dated.** They are simply not
  measurable against ODP from this source.
- **No gate moves.** C5 still denies on placeholder linkage; C2 still counts
  eligible anchor events, of which there are zero.

## 6. Options

1. **A survivorship-bias-free price source** for the peer side — one that
   retains delisted securities (CRSP, Norgate, Sharadar and similar do; free
   web sources generally do not). This is the only option that fixes the
   underlying problem rather than routing around this instance of it.
2. **Record the constraint and proceed with CVS only**, with the peer universe
   explicitly restricted to survivors and the bias stated in the registry. Half
   the map, and a known-biased half.
3. **Source ODP history from the operator's own records** if any exist from
   when it traded.

**None taken.** The fetcher already behaves correctly here: it left all 1722
rows EMPTY rather than fabricating, and reported the file incomplete.

## 7. Data handling

The fetched CVS closes are **not committed to this repository.** They are
Yahoo-derived market data, redistribution of which is restricted by that
provider's terms, and they are reproducible by re-running the fetcher. They
live outside the repo; only the code that produces them is version-controlled.

---

## AMENDMENT — 2026-08-27: the argument is now registry policy; no option taken

**Section 6's "None taken" still holds.** No survivorship-bias-free price
source has been selected, nothing was collected from one, and the CVS closes
remain uncommitted.

What changed is that section 4's argument is no longer only recorded in this
document. Registry
[`v1.5`](GST_PROSPECTIVE_HYPOTHESIS_REGISTRY_v1.5.json) adds a top-level
`peer_price_data_policy` stating the separation as a governing rule:

> Peer-side price data availability is a **measurability** question, reported
> per pair. It is never a **membership** question, and it never decides which
> anchors or peers are in scope.

The same version registers a rule-based HYP-04 anchor universe, and four
conditions are recorded there as **deliberately rejected** — among them
"counterparty still exists" and "price history obtainable", each with the
reason. A test (`test_hyp04_supply_chain_hedge_anchor_universe.py`, test_6)
attaches every availability signal an implementer might reach for to a
qualifying disclosure and requires the outcome to be unchanged, so adding such
a condition later fails a test rather than passing unnoticed.

**This buys something concrete here.** PKG is excluded from the anchor universe
by the *denominator* of its disclosure — 58% of the Paper segment, 4% of
consolidated revenue — and not by ODP's disappearance. Had membership
conditioned on obtainable prices, PKG would have been dropped for a reason that
is pure survivorship, which is the outcome section 4 warns about.

Section 5 also stands: the two curated edges remain correct and the 42 PKG
anchor events remain correctly dated. They are still not measurable against ODP
from this source.

**No gate moved:** CLOSED, C4 MET, 4 denials.
