# HYP-04 finding — the extractor is blind to possessive denominators, and v1.6's under-inclusion measurement could not have seen it (2026-08-27)

**Status: FINDING.** The display gate reads **CLOSED, C4 MET, 4 denials** before
and after. Registry v1.6 is **not edited** — it is published and append-only.
No membership is changed by this document. Nothing here is evidence about
supply-chain transmission.

---

## 1. The observation

`extract_edges_from_text` fails to produce any edge at all when the
concentration's denominator is written as an **apostrophe-s possessive**. The
anchor's `basis` group does not admit one, so the anchor never matches and the
disclosure is not merely unclassified — it is **invisible**.

Measured over a controlled grid, one sentence with the denominator varied and
everything else held constant:

```
Sales to Rite Aid Corporation represented approximately 15% of {denominator}.
```

| | |
|---|---|
| **ACCEPTED — 13 of 13** | revenues · net sales · total revenues · consolidated revenues · consolidated sales · our revenues · our net sales · our total revenues · our consolidated revenues · total company revenues · company revenues · its revenues · their revenues |
| **REJECTED — 7 of 7** | the Company's revenues · the Company's net sales · the Company's consolidated revenues · the Company's total revenues · McKesson's revenues · the Corporation's revenues · the Registrant's revenues |

The split is exact and has one cause: **every rejected form contains `'s`, and
no accepted form does.** It is not about the head noun (`revenues` alone is
accepted) nor the qualifier's meaning (`our revenues` and `the Company's
revenues` denote the same quantity).

### There are two layers, and they need different fixes

The classifier is never reached — but if it were, it would only place **four**
of the seven:

| Rejected by the anchor | `classify_concentration_basis` would return |
|---|---|
| the Company's revenues · the Company's net sales · the Company's consolidated revenues · the Company's total revenues | `consolidated_revenue` |
| McKesson's revenues · the Corporation's revenues · the Registrant's revenues | `other_or_unknown` — fails closed |

So **widening the anchor alone recovers four of these seven and leaves three
dropped one layer further down.** A possessive built on the filer's own *name*,
or on "Corporation" / "Registrant", is not in the classifier's entity-wide
qualifier set either.

*(An earlier draft of this document asserted all seven would classify. That was
verified for two and generalised to seven, and it was wrong — caught by the
characterization test below, which is the reason to write assertions instead of
prose.)*

**This matters most for exactly the filings just added to the corpus.** "The
Company's", "the Corporation's" and "the Registrant's" are ordinary register in
1990s and 2000s 10-Ks and much rarer in recent ones. The 2026-08-27 walk
widened the corpus from 2026-only to 1996–2026, which is the era where this
phrasing lives.

## 2. The correction this forces

Registry v1.6's companion and its commit message both state:

> **Under-inclusion was measured too**, since every gate rejects and an
> unrecognised denominator fails closed. Across the full corpus exactly **two**
> named ≥10% disclosures carried an unrecognised denominator — both Qualcomm
> *segment* revenues, which the rule excludes correctly anyway.

**That measurement is sound but narrower than the sentence around it claims.**
It was computed by enumerating the disclosures recorded in the walk artifact.
The artifact records disclosures the anchor **matched**. So the procedure could
only ever find *anchors that matched but whose denominator did not classify* —
the count of two is correct for that question. It was **structurally incapable**
of seeing a disclosure whose anchor never matched in the first place, which is
precisely this class.

So "under-inclusion was measured" should read **"unclassified denominators
among matched anchors were measured, and there were two."** Under-inclusion
from unmatched anchors was not measured, and on the evidence here it is not
zero.

This is the same failure shape as the one v1.6 already records for
over-inclusion, arriving from the other side: **round one was a spot check
because it could only inspect what the report printed.** Here the measurement
could only inspect what the extractor matched. In both cases the instrument's
blind spot and the thing being measured coincided.

## 3. What is NOT claimed

- **No membership change is asserted.** Whether any ticker's intervals would
  move cannot be determined without re-running extraction over the corpus, and
  that has not been done. v1.6 stands exactly as published.
- **MCK's earliest interval is unaffected**, and this was verified rather than
  assumed: the FY2000 filing that opens it says "consolidated sales", one of
  the accepted forms. The recovered 2000-06-13 filing still yields Rite Aid
  Corporation at 15%.
- **The direction of the error is one-way.** A missed anchor can only *omit* a
  disclosure, never invent one. Fixing it can therefore only **add** members or
  lengthen intervals, never remove them. No published member is at risk of
  being wrong; the risk is that members are missing.

## 4. Why it is recorded rather than fixed here

Widening the anchor changes what the rule *sees*, and therefore what the rule
*yields*. Under this repo's discipline that is a derivation change: it needs a
re-walk over the corpus, a re-derivation, and a new dated registry version —
not an edit to a published one. Changing the regex today without re-measuring
would leave the code and the published v1.6 artifact disagreeing about the
universe, and v1.6's own tests would not catch it, because they re-derive from
the **stored** artifact rather than from live extraction.

The re-walk is a live SEC runner and requires the repo owner's staged
go-ahead. It has not been requested or run.

## 5. What was built instead, and what it changes

`edgar_linkage.FilingCache` (added today, 45 checks in
`test_hyp04_supply_chain_hedge_edgar_cache.py`) stores raw EDGAR responses on
disk, keyed by URL, and `EdgarClient(offline=True)` replays them without
touching the network.

This is the thing that makes the fix affordable. Until now, measuring any
extractor change cost ~1,250 live SEC requests, which needs authorization —
so the measurement did not get done, and limitations accumulated as prose
instead of numbers. **One authorized walk populates the cache; every
re-measurement after it is free and reaches no endpoint.**

The cache stores the **raw** body, before `strip_markup` and before
`first_document_of_submission`, specifically so that changes to those — and to
the anchor regex this finding is about — are re-measurable rather than frozen
into the stored corpus. Negative results are stored too, so the 404-driven
full-submission fallback takes the same branch on replay as it did live.

## 6. Suggested order of work, when authorized

1. Populate the cache with one full-frame walk (~1,250 requests, the same cost
   as the walk already run today).
2. Widen **both layers**: the anchor's `basis` group to admit `'s`
   possessives, *and* the classifier's entity-wide qualifier set to cover
   filer-name, "Corporation" and "Registrant" possessives. Fixing only the
   anchor converts three of these from invisible to `other_or_unknown`, which
   is still a drop — just a differently-shaped one. And the verb set, per
   §7 below.
3. Re-measure over the cached corpus — **free, offline, repeatable** — for both
   directions: new named disclosures found, and a fresh exhaustive fabrication
   check over everything newly admitted. A wider anchor admits more prose, and
   the eight fabrications already found came from exactly that.
4. Only if membership moves, author registry v1.7 with the re-derived
   intervals.


## 7. A second, independent gap: the accepted verb set is closed

Measured the same way, denominator held constant and the verb varied:

| | |
|---|---|
| **ACCEPTED — 7 forms, 5 lemmas** | represented · accounted for · comprised · constituted · made up (with or without "approximately") |
| **REJECTED — equivalence phrasings** | were approximately · was approximately · totaled · equaled · approximated |
| **REJECTED — not claimed as a gap** | generated · provided · contributed · is · are |

The middle row is a genuine gap: *"sales to X **were** approximately 15% of net
sales"* states exactly the relation the accepted verbs state, and is ordinary
10-K prose rather than exotic phrasing.

The bottom row is **deliberately not claimed as a gap.** Those verbs describe
what the counterparty *contributed* rather than asserting the share **is** the
figure; admitting them would be a semantic widening, not a phrasing fix. They
are pinned in `test_6l` anyway, so that a future change admitting them is a
visible decision rather than a side effect of loosening the verb list.

This gap is independent of §1's. A filing can miss on the denominator, on the
verb, or on both, so the two do not compose into a single count — and neither
was visible to v1.6's under-inclusion measurement, for the same structural
reason given in §2.

Both are one-way: an unmatched verb, like an unmatched denominator, can only
omit a real disclosure and never invent one.

---

**Nothing in this document is evidence about supply-chain transmission.** No
result, direction, effect estimate, plot, p-value or confidence interval exists
for HYP-04, and none may be displayed while the gate is closed.
