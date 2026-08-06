# MSFT FY2026 Q4 Pilot — QC Findings and Disposition

**Event:** `EVT-MSFT-FY26Q4-ERN` (informal ID; not yet entered into `events.csv`, since this event is `development_pilot` and this document is itself the disposition record, not a schema row)
**Original artifact location (unmodified, preserved as evidence):** `Live Signal Engine/Phase2_Event_Dossiers/MSFT_FY2026Q4_POST_EVENT_D2/` in **both** the frozen `phase2-wikipedia-reliability` worktree (original) and this `phase2-event-dossiers` worktree (byte-identical copy, SHA-256 verified — see the chat report accompanying this document's creation).

**Disposition (permanent, two fields, set simultaneously):**
```
event_disposition = development_pilot
blinding_compromised_for_confirmatory_use = true
```
Note that MSFT **is** a member of the locked v0.1 confirmatory ticker universe (`../locked_universe_v0.1.json`) — universe membership and confirmatory-eligibility are separate concepts. MSFT's ticker stays in the universe (a future, cleanly captured MSFT earnings event could become `confirmatory`); it is *this specific event instance* (`EVT-MSFT-FY26Q4-ERN`) that is permanently pilot/compromised. **This status is one-directional: no remediation, correction, or re-review returns this event to confirmatory eligibility.**

---

## 1. Why MSFT is retained as a development pilot, not deleted or silently fixed

The original dossier (`dossier.md`) was built to test whether a structured, sourced, blinded post-earnings event dossier was even achievable from live web research. It succeeded at that goal in most respects — but its **narrative text** exposed a human reviewer to post-event stock-price-reaction information (specific after-hours/next-session price-move percentages), which is exactly the kind of market-reaction exposure the blinding design exists to prevent before a label is frozen.

This is retained, not deleted, because:
- It is the concrete evidence that motivated every rule in `EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md` — deleting it would remove the audit trail for *why* the protocol looks the way it does.
- It remains useful for testing future tooling (e.g., a validation-checklist script can be run against it and should currently **fail** on the forbidden-language check — that failure is itself a regression test for the checklist).
- Per instruction, it is not silently rewritten. It is preserved exactly as originally produced, in both worktrees.

Per the protocol's disposition rule (§12): a `confirmatory`-track event that suffers a documented blinding breach moves toward `development_pilot`/`compromised` and **never moves back**, even after remediation. A cleaned-up MSFT re-dossier, if ever produced, would be a **new** event artifact under a new capture — it would not un-taint this one.

## 2. Why the machine-readable table remained feature-clean

`dossier_table.csv` and `dossier_table.json` contain no price, volume, options, IV, GST, or Wikipedia field, and no field in either file encodes a stock-price-reaction percentage. This was verified by direct inspection of every column in both files during the original QC pass. The structured/machine layer of the pilot is genuinely clean — the breach is confined to the prose layer.

## 3. Why the narrative nevertheless caused a blinding breach

`dossier.md` contains, in running prose:
- Section 11: "...even if the +8–9% after-hours magnitude was not guaranteed."
- Section 13: explicit reconciliation of three different stock-price-reaction figures (8%, "nearly 9%", 14.68%) across different (unreconciled) measurement windows.
- The source-inventory table quotes source S5's own title verbatim: *"Microsoft Q4 2026 beats forecasts, stock jumps 8%"* — a price-reaction figure embedded in a citation, not just body prose.

None of this fed the table. But a document meant to sit beside frozen, blinded labels should not itself carry the very information the labels are supposed to be blind to — a human reviewer or any downstream process reading the narrative (not just the table) is exposed to a known-positive market outcome while forming qualitative judgments (e.g., `management_tone`), which risks anchoring those judgments to the outcome rather than to the event facts alone. This is precisely the failure mode Layer A/Layer B separation (protocol §11) is designed to make structurally impossible: under the new protocol, this content would have to live in the Market Response Addendum, revealed only after freeze, and would never appear in a Layer-A narrative at all.

## 4. Source verification status (carried over from the original QC pass, unchanged)

### Verified (directly fetched, Tier 0–1 equivalent)
GAAP/non-GAAP EPS, revenue, segment revenue and growth figures, M365/LinkedIn/Dynamics 365 growth, Windows/Xbox/search-ads figures, Microsoft Cloud revenue, discrete-item EPS benefit and Anthropic/OpenAI gains, direct Nadella/Hood quotes, Q1 FY2027 guidance figures — all from Microsoft's own press release, newsroom article, and a call-transcript excerpt that were directly fetched.

### Partially verified
- EPS/revenue surprise percentages (consensus figures behind them are snippet-sourced — see below)
- `guidance_direction = "raised"` — mislabeled; see §5
- `capex_direction = "raised"` — collapses two distinct concepts; see §5
- `information_novelty_score_1_to_5 = 4` — asserted from absence-of-contrary-evidence, not a logged pre-release check
- Q&A "Unresolved" labels — predate the required 4-value taxonomy; see §5

### Unsupported / search-snippet-only (never directly fetched — Tier 4 under the new hierarchy)
- Consensus EPS ($4.24, "LSEG"), no as-of date
- Consensus revenue cluster ($87.42B–$87.67B), which improperly blends Zacks and LSEG figures as one "cluster"
- Q1 FY2027 LSEG revenue estimate ($89.66B), Visible Alpha Azure estimate (39.98%)
- Prior-quarter Azure growth comparison (40%, "Q3 FY2026") and Copilot-seat baseline (~20M, April)
- Commercial RPO figures ($678B / $627B / +$51B)
- All four analyst price targets (Wells Fargo, Citi, Wolfe Research, Bernstein) and their stated "prior" values — including a suspicious exact-round-trip Wells Fargo figure ($650 → $625 → $650) that was never independently re-verified
- Stock-price-reaction figures (8% / ~9% / 14.68%) — see §3; these should not have been recorded in Layer-A-equivalent narrative at all, independent of their sourcing quality

## 5. Fields needing revision before the template can be locked

1. **`guidance_direction`**: reclassify under protocol §15.2. MSFT's Q1 FY2027 revenue guide is a **first** guide for that period (no prior Q1 FY27 company guide exists) issued above a cited consensus — the correct value is `first_guide_above_consensus`, not `raised`. **AI_PROPOSED, not human-frozen.**
2. **`capex_direction`**: split into the two-axis taxonomy (protocol §15.3): `capex_operational_direction = increasing` (guided "over $50B" for Q1 FY27, two-thirds to short-lived GPU/CPU assets) and `capex_accounting_presentation_effect = lease_reclassification; useful_life_change` (both explicitly disclosed as accounting changes affecting the *reported* figure independent of operational spend). **AI_PROPOSED, not human-frozen.**
3. **Consensus figures**: every EPS/revenue/guidance consensus number needs a named provider **and** as-of date sourced to a direct fetch (Tier 0–3) before any surprise percentage using it can be frozen. Currently none qualify.
4. **Q&A classification**: apply the 4-value taxonomy (protocol §15.1) in place of the uniform "Unresolved" label:

   | Analyst | Question | **AI_PROPOSED classification** | Basis |
   |---|---|---|---|
   | Keirstead (UBS) | Open-model competitive/financial exposure | `not_answered` | Nadella's response addressed a different question (harness/model architecture) than the one asked (competitive/financial exposure) |
   | Moerdler (Bernstein) | Hardware-price margin impact | `partially_answered` | Hood engaged with the topic (depreciation-flexibility framing) but gave no quantified impact |
   | Borges (Goldman) | YoY ROI comparison | `partially_answered` | Hood gave a direct-if-terse response ("math has not changed") plus TAM framing, without the requested metric |

   **These three classifications are AI_PROPOSED only. None are human-frozen. They require human review before any use beyond illustrating the taxonomy on pilot data.**
5. **Narrative leakage**: remove specific stock-price-reaction percentages from any future version of this narrative; replace with a structural statement that market-reaction data is intentionally excluded pending Layer B reveal; do not quote source titles that themselves contain reaction figures.
6. **Schema gaps** (apply to the *template*, not just this instance): add `consensus_provider`/`consensus_asof_date` columns (now present in the new `claims.csv` schema), add a source-tier/retrieval-method field per claim (now present in `claim_sources.csv`), and stop blending multiple providers' consensus figures into one value.

## 6. Status

This document itself contains no newly-fetched data and performs no new sourcing — it restates and reorganizes the QC findings already produced under the read-only audit, maps them onto the new taxonomies, and records the disposition decision. All proposed reclassifications above are explicitly `AI_PROPOSED` and require human review; nothing here is `human_frozen`.
