# Sector-Composition Audit Rule — 2026-08-16 (FROZEN BEFORE RETRIEVAL)

**Written and hashed BEFORE any SEC or Kenneth R. French Data Library retrieval.** At the moment of
writing, no issuer's SIC code or industry category is known to the author. The hash and timestamp are
recorded so this rule cannot be claimed to have been fitted to the distribution it later measures.

**This is a descriptive governance audit only.** It alters no ticker, creates no selection,
introduces no sector quota, activates nothing, and modifies neither the production 24 nor HYP-01.

---

## 1. Universe groups

Exactly four, and no others:

| Group | Definition |
|---|---|
| `LEGACY_24` | the original locked 24, positions 1–24 of the merged proposal |
| `PROPOSED_ADDITIONS_26` | the selected 26, positions 25–50 |
| `PROPOSED_FINAL_50` | all 50, in the merged order |
| `OEF_ELIGIBLE_PROXY_POOL` | every eligible equity issuer in the dated identity-only OEF proxy snapshot for which official classification can be established |

## 2. Authoritative classification sources

Only these two:

1. **SEC** — issuer identity, CIK and SIC code from official SEC data.
2. **Kenneth R. French Data Library** — the official SIC-interval definitions of the Fama–French
   12-industry classification.

## 3. Prohibited as canonical evidence

No aggregator, encyclopedia, search-engine snippet, model-generated sector label, ETF weight, market
capitalization, or subjective classification may serve as canonical evidence. A search engine may be
used only to locate an official page; its snippets are not evidence.

## 4. Classification fields

Per security: canonical ticker · original/proposed status · issuer name · CIK · SEC SIC code · SEC SIC
description where officially provided · Fama–French 12 category derived deterministically from SIC ·
provenance URL · retrieval timestamp · source hash where applicable · classification status.

## 5. Missing policy

- **Never infer a missing SIC.**
- **Never choose an industry from company familiarity**, name resemblance, or recollection.
- An unresolved security is classified **`CLASSIFICATION_UNRESOLVED`** and reported as such.
- **No unresolved ticker is deleted, replaced or swapped.** The universe is not edited by this audit.

## 6. Share-class policy

- Apply the already-frozen `BRKB` → `BRK-B` identity reconciliation.
- Preserve `GOOG`/`GOOGL` identity and issuer distinctions exactly as the universe proposal records
  them; this audit does not revisit that decision.
- Count each final-universe issuer **once**. The final 50 already contains zero duplicate issuers, so
  no de-duplication step is applied to it.

## 7. Metrics — equal ticker weights only

Computed per group: exact counts and percentages by Fama–French 12 category · largest-category share ·
number of represented categories · number of absent categories · **Herfindahl–Hirschman index**
`HHI = Σ sᵢ²` over category shares · **Shannon entropy** `H = −Σ sᵢ ln sᵢ` · **effective number of
categories** `exp(H)` · comparison across `LEGACY_24`, `PROPOSED_ADDITIONS_26`, `PROPOSED_FINAL_50`
and the OEF proxy pool · category-level difference in **percentage points** between `PROPOSED_FINAL_50`
and the OEF proxy pool.

## 8. Weighting

**Equal ticker weights only.** Market capitalization, OEF holdings weights, returns, prices, volumes
and every other economic weight are **prohibited** as inputs to any figure in this audit.

## 9. No threshold is frozen here

**This task freezes no concentration pass/fail threshold, and invents none.** The audit is
descriptive. Any later threshold, or any decision to retain, reject or redesign the universe, is a
**separate human decision** that must be made **without consulting GST or return outcomes**.

## 10. Language discipline

No distribution may be called *representative*, *balanced*, *acceptable*, *unacceptable*, *biased* or
*statistically significant* unless a separately frozen rule supports that wording — and none does.

Permitted neutral phrasing: *higher concentration* · *lower concentration* · *overrepresented relative
to the proxy by X percentage points* · *underrepresented relative to the proxy by X percentage points*
· *no automated accept/reject threshold was specified*.

## 11. Sensitivity checks — descriptive only

Final 50 including all securities · final 50 excluding `CLASSIFICATION_UNRESOLVED` · legacy 24 versus
additions 26 · final 50 versus the eligible OEF proxy pool · leave-one-ticker-out range of the
largest-category share and HHI.

**No search for a more balanced subset. No alternative universe is generated.**

## 12. Scope

This audit does not alter/reorder/replace any of the 50 tickers, create a selection, introduce
quotas, activate the proposed universe, modify the production 24, use Google Trends, retrieve price,
return, volume, options, earnings-result, analyst, news or performance data, inspect a prospective
outcome, close F5, begin screening or collection, or modify HYP-01.
