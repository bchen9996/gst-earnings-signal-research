# Event Dossier Protocol — v0.1 DRAFT

**Status:** Draft architecture. Not yet used to produce a confirmatory-event label. **Revision 3** (2026-08-03, validator hardening pass): renames the niche to `fixed_24_ticker_earnings_panel` (§1); mechanically enforces every documented required/conditional field, enum, numeric/integer/date/timestamp type, and cross-row consistency rule (§9, §15) instead of only some of them; completes foreign-key validation everywhere, including a new `event_label_cross_company_implications.csv` child table replacing a semicolon-delimited FK field, and `corroborates_claim_source_id`; hardens freeze-manifest validation into a full executable contract (artifact existence, path containment, exactly-once required inventory, no Layer-B/C leakage, manifest/label cross-consistency); expands blinding-language scanning to every Layer-A free-text field; corrects reveal/freeze timestamp ordering to strict `>` (equal timestamps now fail as ambiguous) and makes naive/mixed-timezone timestamps fail validation instead of raising; and adds explicit EPS/revenue actual+consensus claim-ID linkage with independent surprise-percentage recomputation. See `CHANGELOG.md` for the full list. **Revision 2** (2026-08-02): corrects the capture-vs-reveal rule, locks the v0.1 confirmatory universe to the exact existing Phase 2 24-ticker list, and aligns taxonomy field names with the executable validator (`validator/validate_event_dossier.py`).
**Branch:** `phase2-event-dossiers` (worktree: `gst-event-dossiers-worktree`, sibling to the frozen `phase2-wikipedia-reliability` regression worktree — never modified by this lane).
**Motivating incident:** the MSFT FY2026 Q4 pilot dossier (see `MSFT_PILOT_QC_AND_DISPOSITION.md`) exposed reviewers to post-event stock-price-reaction language in its narrative text, despite its machine-readable table remaining feature-clean. That single breach is the reason this protocol exists as a formal document rather than ad hoc practice.

---

## 0. Scope of this draft

This document defines the process, directory/schema separation, taxonomies, and validation rules for producing **blinded post-earnings event dossiers** for the GST Information Arrival Project. It does not itself populate any research data, and it does not touch GST, Wikipedia, implied-volatility, price, volume, or signal-tier data at any point.

## 1. Initial narrow research niche

**`fixed_24_ticker_earnings_panel`** (renamed 2026-08-03 from `large_cap_earnings` — see below), for the initial version of this protocol:
- Single-name earnings events for the exact locked v0.1 24-ticker universe (§1.1) only — U.S.-listed, regularly scheduled quarterly earnings releases with an associated SEC filing (8-K or equivalent) and a public conference call
- Excludes: M&A announcements, guidance-only pre-announcements, regulatory events, macro/Fed events, and any company without a public earnings call — these may become separate niches under their own protocol versions later, not silently folded into this one.

**Why the rename.** The niche was originally named `large_cap_earnings`, describing the universe as uniformly large-cap. That was materially inaccurate: the locked v0.1 universe (§1.1) includes tickers like `GME` and `NCLH`, which are not large-cap by any conventional market-cap definition. The niche is honestly defined by what it actually is — the exact fixed 24-ticker panel already locked for the Phase 2 GST/Wikipedia panel — not by an invented, and wrong, size classification. `niche = "fixed_24_ticker_earnings_panel"` is now the only accepted value, mechanically enforced by the validator (`NICHE_VALUES` in `validator/validate_event_dossier.py`); `large_cap_earnings` is rejected.

### 1.1 Locked v0.1 confirmatory universe

The v0.1 confirmatory universe is **not** defined by an invented market-cap threshold. It is the exact, existing locked 24-ticker universe already used by the Phase 2 GST/Wikipedia panel, copied verbatim:

`AAPL, ABBV, ADBE, AMZN, BKR, BRK-B, CTSH, DELL, DVN, GME, GOOGL, GPN, INTC, LDOS, MSFT, NCLH, NKE, QCOM, SBUX, STZ, SYK, TSLA, TTWO, UAL`

| Field | Value |
|---|---|
| Source file | `GST_Phase2_DailyPanel.py`, `TICKERS` constant |
| Source commit | `46aec15854a75ada2bd0078dce4d018e4b032c90` (read directly from this worktree's own checkout) |
| Protocol version | 0.1 |
| Date locked | 2026-08-02 |

The machine-readable, authoritative copy of this list lives in `locked_universe_v0.1.json` in this directory; the validator reads from that file rather than duplicating the list in code. **MSFT is a member of this locked universe** — its presence in the confirmatory ticker list is unrelated to, and does not override, its permanent `development_pilot` disposition (Section 12, `MSFT_PILOT_QC_AND_DISPOSITION.md`). Any expansion beyond these 24 tickers requires a new protocol version, locked *before* observing outcomes for the added tickers — never a silent addition, and never back-dated to cover already-captured events.

## 2. Event ID convention

```
EVT-{TICKER}-{FISCAL_PERIOD_COMPACT}-{EVENT_TYPE}
```
- `TICKER`: uppercase exchange ticker, no share-class suffix normalization beyond what the exchange uses (e.g., `BRK-B` stays `BRK-B`).
- `FISCAL_PERIOD_COMPACT`: `FY{YY}Q{N}` (e.g., `FY26Q4`). Fiscal, not calendar, quarter — matches how the company itself labels the period in its own release.
- `EVENT_TYPE`: `ERN` for earnings (the only value in scope for v0.1).
- Example: `EVT-MSFT-FY26Q4-ERN`.

Child records reference the event via a scoped, stable ID:
- Claim: `{event_id}-CLM-{seq:04d}`
- Source link: `{event_id}-SRC-{seq:03d}`
- Q&A: `{event_id}-QNA-{seq:02d}`
- Label: `{event_id}-LBL-{version:02d}` (version increments only via a recorded amendment, never in place)
- Addendum: `{event_id}-ADD-{seq:02d}`

IDs are never reused or renumbered after any row referencing them has been written, even in draft state, so that partially-built ledgers stay internally consistent.

## 3. Capture windows and trading-day convention

Two standardized capture windows for this niche:
- **POST_EVENT_D1** — first trading session with a full opportunity to react.
- **POST_EVENT_D5** — fifth such trading session.

**Exact trading-day rule:**
- If the release occurs **after market close**, on a **weekend**, or on a **market holiday**: the next regular trading session is **D+1**.
- If the release occurs **before market open** on a trading day: that same session is **D+1** (it has a full session's opportunity to react).
- If the release occurs **during market hours** (intraday) on a trading day: that session is only partially able to react and is **not** counted as D+1; the **next full session** is D+1. The partial remainder of the release-day session is treated as intra-event and excluded from the D-count for cross-event comparability.
- D-count uses the primary listing exchange's regular trading calendar (NYSE/NASDAQ for this niche). Half-days count as a full session for D-count purposes; the convention does not currently distinguish half-day liquidity effects.
- **D0 does not exist in this convention** — the counter starts at 1 to avoid an ambiguous partial-session zero state. (The MSFT pilot's own `POST_EVENT_D2` label — used because that dossier was hand-captured two sessions after an after-close release — is consistent with this rule and is retained as a valid but *non-standard* one-off capture; D2 is not one of the two standardized windows going forward.)
- A dossier's `dossier_stage` field must record which standardized window it targets (`POST_EVENT_D1` or `POST_EVENT_D5`) plus the actual capture timestamp; the two need not be identical (e.g., a D1-window dossier captured slightly late is still labeled D1 if it targets the D1 information set, with the actual capture timestamp recorded separately for audit).

## 4. Source hierarchy

| Tier | Description | Usable for frozen numeric labels? |
|---|---|---|
| 0 | Company primary, directly fetched (official press release, IR site, official transcript, direct company newsroom post) | Yes |
| 1 | Statutory filing, directly fetched from the regulator (e.g., raw SEC EDGAR document, not a third-party summary of it) | Yes |
| 2 | Wire-service direct distribution, directly fetched (e.g., PR Newswire/Business Wire copy of the company's own release) | Yes, as corroboration only — Tier 0/1 remains the reference value if they conflict |
| 3 | Major financial media, **directly fetched** (not a search-engine snippet) | Yes, only for facts not covered by Tiers 0–2 (e.g., named consensus provider + as-of date), and only if the article itself names its own primary source |
| 4 | Any source accessed **only** via a search-engine synthesis/snippet, never directly fetched | **No** — may be recorded as `provisional`/`unverified` in `claims.csv`, must be replaced by a Tier 0–3 direct fetch before a label using it can be frozen |
| 5 | Single-analyst-note paraphrase reported by media (price targets, ratings) | Market Response Addendum (Layer B) only — never enters the Blinded Event Core |

Every `claim_sources.csv` row must record its tier and its `retrieval_method` (`direct_fetch` / `search_snippet` / `blocked` / `not_attempted`) explicitly — this was the single largest gap found in the MSFT pilot (most quantitative context was Tier-4/search-snippet-only while being narratively presented at a stronger apparent tier).

## 5. Consensus-provider and as-of timestamp requirement

A consensus estimate (EPS, revenue, or any other metric) is **not usable** in a frozen label unless its `claims.csv` row records:
- `consensus_provider` (e.g., LSEG, Zacks, Visible Alpha, FactSet) — a named provider, not "analysts" or "the Street"
- `consensus_asof_date` — the date/timestamp the estimate reflects, not merely the date the article citing it was published

Different providers' consensus figures are **never** blended into a single "cluster" value (the MSFT pilot did this, mixing a Zacks figure into an "LSEG-linked cluster" — this is now explicitly prohibited). If multiple providers' figures are available, each is recorded as a separate `claims.csv` row with its own provider tag; the frozen label cites exactly one named provider per surprise-percentage calculation, with the choice justified in `reviewer_notes`.

If no provider+as-of-date pair can be sourced to Tier 0–3, the corresponding surprise-percentage field is left `null` with `verification_status = unverifiable` — it is never computed from an unattributed figure.

## 6. GAAP/non-GAAP and reported/constant-currency rules

- Every EPS and revenue figure carries an explicit `gaap_basis` tag: `GAAP`, `non-GAAP`, or `NA`.
- Every growth/comparison figure carries an explicit `currency_basis` tag: `reported` or `constant_currency`.
- A surprise percentage (actual vs. consensus) is only computed when **both** the actual and the consensus figure are confirmed to be on the **same** GAAP basis. If the consensus source does not itself state whether its estimate is GAAP or non-GAAP comparable, the pairing is marked `unverifiable`, not assumed (this closes a gap identified in the MSFT pilot QC, where a non-GAAP actual was paired with a consensus of unconfirmed basis).
- Company guidance ranges carry the same tags as actuals.

## 7. What qualifies as "genuinely new" information

A claim may be marked genuinely new **only if** a documented pre-release-availability check was performed and logged in `claims.csv.novelty_eval_basis`:
- `checked_absent` — a specific pre-release source (prior quarter's release, prior 10-K/10-Q, prior guidance) was checked and the item was confirmed absent before the event.
- `checked_present_prior_disclosure` — checked, and a version of this information already existed before the event (claim should then be marked NOT genuinely new).
- `not_evaluated` — no check was performed. Default state. A claim with `not_evaluated` **cannot** be counted toward an `information_novelty_score` — novelty defaults to "not evaluated," never to an assumed "new."

This directly fixes the MSFT pilot's practice of inferring novelty from "not found in the sources gathered for this dossier," which is absence-of-search, not a confirmed absence-of-disclosure.

## 8. Human-review process

**Revision (2026-08-02): capture is not reveal.** An earlier draft of this protocol stated that Layer B/C could not be *created* until Layer A froze. That rule is wrong: it risks losing transient market/feature evidence (a price quote, a pageview snapshot) that cannot be reconstructed later. The corrected rule separates **capture** (fetching and storing evidence) from **reveal** (a human or AI labeling process actually reading it):

1. AI assembles `events.csv`, `claims.csv`, `claim_sources.csv`, and `management_qna.csv` rows for the Blinded Event Core (Layer A) only. Every classification/interpretation field is tagged `classified_by = ai_proposed`.
2. AI drafts a proposed `event_labels.csv` row with `label_status = ai_proposed`.
3. **Layer B (Market Response Addendum) and Layer C (Attention Feature Join) may be captured automatically and contemporaneously with Layer A**, so that time-sensitive evidence is not lost. Capture writes rows to `market_response_addendum.csv` / the Layer C feature store and records a `captured_at_utc` timestamp. **Capture and storage do not constitute reveal** and do not require Layer A to be frozen first.
4. Layer B and Layer C content remains **embargoed** from anyone performing the Layer A review for that event. The Layer A reviewer must not open, query, or be shown Layer B/C content before signing off. This is enforced procedurally (reviewer discipline plus the validator's reviewer-access-log check — Section 17), not merely by directory separation.
5. **A reviewer who is exposed to Layer B or Layer C content for an event before that event's Layer A label is frozen is permanently disqualified from signing that event's blinded label.** A different, unexposed reviewer must perform the freeze instead. This exposure is recorded (`reviewer_capture_exposure_log` in the freeze manifest — Section 17) and is itself part of what the validator checks.
6. The reviewer either (a) confirms, setting `label_status = human_frozen`, `frozen_by`, `frozen_at_utc` and writing a `freeze_manifest.json` containing hashes of every Layer A artifact used, or (b) returns specific fields for correction, which the AI revises and resubmits (still `ai_proposed` until reviewed again).
7. **Reveal** of already-captured Layer B/C content to a reviewer or downstream process may only occur after Layer A reaches `human_frozen`, and the reveal event's own timestamp must be strictly later than the freeze timestamp. The panel may keep collecting Layer C features on its own schedule throughout — that schedule is independent of any single event's labeling status, provided the features stay inaccessible to that event's labeler until reveal.

## 9. Label-freezing process

`event_labels.csv` is append-only. Freezing a row requires, at minimum:
- All required schema fields populated or explicitly `null` with a `verification_status` explaining why.
- All enum fields use only allowed enum values (see Section 11).
- Every numeric claim feeding the label has at least one `claim_sources.csv` row at Tier 0–3 with `retrieval_method = direct_fetch`.
- The validation checklist (Section 12 / `VALIDATION_CHECKLIST_v0.1_DRAFT.md`) passes with zero forbidden-field/forbidden-language hits.
- A human reviewer's sign-off (`frozen_by`, `frozen_at_utc`) is recorded.

Once frozen, a row is immutable. No script, human, or AI process edits a frozen row in place.

## 10. Amendments after freezing

Any correction to a frozen label is a **new row**: new `label_id` with an incremented version, `amendment_of_label_id` pointing to the prior row, a dated reason, and a reviewer identity. The prior row is never deleted or edited.

**Hard rule:** if an amendment is requested for an event **after** its Layer C (Attention Feature Join) has already occurred, the event may **not** be silently amended and rejoined. Instead it must be flagged `event_disposition = compromised` and excluded from the confirmatory sample — a feature-reveal-informed relabel is not permitted under any circumstance, since it would let outcome data influence the label it's later tested against.

## 11. Prohibitions before label freeze

Before an event's `event_labels.csv` row reaches `human_frozen` status, the **labeling process** (the AI proposing Layer A content, and the human reviewer signing it) — but not necessarily an unrelated automated capture process — may not view, query, or be shown, for that event or any related ticker:
- Stock price or return data (any window)
- Options/implied-volatility data
- Trading volume data
- GST attention-index values
- Wikipedia pageview values
- Post-event analyst estimate revisions, price-target changes, ratings changes, or general media sentiment/reaction commentary

**This is a reveal prohibition, not a capture prohibition** (see Section 8's revision). Automated, timestamped capture of the above into Layer B/C may happen at any time, including before Layer A freezes — this is required, in fact, to avoid losing transient evidence. What is prohibited is the labeling process *reading* captured Layer B/C content before freeze. Pre-release consensus estimates (Section 5) are the sole item that belongs inside Layer A itself — they characterize expectations *before* the event, not reactions *after* it, and are never treated as Layer B content.

Every Layer A artifact contributing to a frozen label is hashed into that event's `freeze_manifest.json` (Section 17) at freeze time, and the freeze timestamp recorded there must **predate** any subsequent Layer B/C reveal timestamp for that event — this ordering is itself a validator gate, not just a documentation convention.

## 12. Development/pilot vs. confirmatory-event distinction

Every event carries `event_disposition ∈ {development_pilot, confirmatory, compromised}`:
- `development_pilot`: used only to design, test, and refine this protocol and its tooling. **Never** enters a confirmatory hypothesis test, regardless of any later remediation.
- `confirmatory`: eligible for the frozen-label → Layer B reveal → Layer C join pipeline that feeds actual hypothesis tests.
- `compromised`: was confirmatory but suffered a documented blinding breach or a post-Layer-C amendment request; permanently excluded from confirmatory analysis, same as a pilot.

**An event's disposition can move from `confirmatory` toward `development_pilot`/`compromised`, never the reverse.** A remediated pilot is not promoted back to confirmatory — a fresh, cleanly captured event is used instead. This rule exists specifically because of the MSFT incident (`MSFT_PILOT_QC_AND_DISPOSITION.md`).

`events.csv` additionally carries a boolean `blinding_compromised_for_confirmatory_use` field, separate from `event_disposition`, so a search/filter can find every blinding-compromised event regardless of its exact disposition value. For MSFT specifically: `event_disposition = development_pilot` **and** `blinding_compromised_for_confirmatory_use = true`, set permanently and simultaneously — see `MSFT_PILOT_QC_AND_DISPOSITION.md` for the full record.

## 13. Missing/unverifiable-data policy

Any required field that cannot be sourced to Tier 0–3 is recorded as `null` with `verification_status = unverifiable`. This is a first-class, explicit state (present in every relevant enum — see Section 14's `unverifiable` guidance value) — never an omission, never inferred, never estimated, never interpolated.

## 14. No inference / no zero-filling policy

Consistent with the fail-closed design already established for the Phase 2 GST/Wikipedia panel (`GST_Phase2_DailyPanel.py`'s `is_run_complete()` gate): a dossier never fabricates a value to complete a row. A missing consensus figure, an unanswered guidance direction, an unresolved Q&A classification — all stay missing and visible, never papered over. `not_guided`, `unverifiable`, and `not_classifiable` are valid, expected terminal states, not failures of the dossier.

---

## 15. Taxonomies (normative — see also `VALIDATION_CHECKLIST_v0.1_DRAFT.md`)

### 15.1 Management Q&A classification

- `fully_answered` — the specific quantitative/qualitative element asked for is directly provided.
- `partially_answered` — management engages substantively with the topic but withholds the specific number/comparison/detail requested.
- `not_answered` — management's response addresses a different question than the one asked (reframing/deflection), or declines to engage with the topic.
- `not_classifiable` — the transcript excerpt available is insufficient to judge (e.g., truncated, garbled, or the analyst's actual question isn't captured) — used instead of forcing a guess.

### 15.2 Guidance classification

- `reiterated_prior_company_guidance` — company restates a previously issued guide for the same period, unchanged.
- `raised_prior_company_guidance` — company issues a new guide for a period it had already guided, and the new guide is higher.
- `lowered_prior_company_guidance` — same, but lower.
- `first_guide_above_consensus` — this is the first guidance issued for this period (no prior company guide exists to raise/lower), and it is above pre-release analyst consensus for that period.
- `first_guide_in_line` — first guide for the period, roughly at consensus.
- `first_guide_below_consensus` — first guide for the period, below consensus.
- `not_guided` — no guidance was given for the relevant forward period.
- `unverifiable` — guidance may exist but cannot be sourced to Tier 0–3, or the prior-guidance comparison cannot be confirmed.

**Note:** the MSFT pilot's machine table used `guidance_direction = "raised"` for what was actually Microsoft's *first* Q1 FY2027 guide compared against consensus — under this taxonomy that claim should be `first_guide_above_consensus`, not a "raise." This distinction is why the taxonomy separates first-guide-vs-consensus from raise/lower-of-a-prior-guide.

### 15.3 Capex classification (two separate axes — never collapsed into one field)

- `capex_operational_direction ∈ {increasing, decreasing, flat, not_guided, unverifiable}` — the actual direction of committed operational infrastructure spend (e.g., dollars allocated to GPUs, data centers, CPUs), independent of how it is reported. This axis lives directly on `event_labels.csv`.
- `capex_accounting_presentation_effect ∈ {none, lease_reclassification, useful_life_change, other_material_accounting_change, unverifiable}` — whether a reported capex or depreciation figure moved because of an accounting-policy change rather than a change in actual spend.

**Design decision (2026-08-02, resolved):** a single event can have more than one simultaneous accounting-presentation effect (MSFT's pilot data would need both `lease_reclassification` and `useful_life_change`). A semicolon-delimited sub-list was considered and rejected — it is not queryable/joinable without ad hoc parsing and hides multiplicity from schema validation. Instead, `capex_accounting_presentation_effect` is represented as a **normalized child table**, `event_label_capex_effects.csv` (one row per effect per label, FK to `event_labels.label_id`, each with its own supporting `evidence_claim_id`). `event_labels.csv` itself carries no capex-accounting-effect column at all — the child table is the sole authoritative source, avoiding a denormalized copy that could drift out of sync. See `A_Blinded_Event_Core/schemas/event_label_capex_effects.csv`.

Applying this taxonomy retroactively to the MSFT pilot (for illustration only — `AI_PROPOSED`, not a frozen label; see `MSFT_PILOT_QC_AND_DISPOSITION.md`): `capex_operational_direction = increasing` (guided "over $50B" for Q1 FY27, two-thirds to short-lived GPU/CPU assets), and two `event_label_capex_effects.csv` rows: `lease_reclassification` and `useful_life_change`.

---

## 17. Freeze manifest and reveal ordering (new — 2026-08-02)

Every frozen label has an accompanying `freeze_manifest.json` (schema: `schemas/freeze_manifest.schema.json`) containing, at minimum:
- `event_id`, `label_id`, `protocol_version`
- `layer_a_artifact_hashes`: SHA-256 of every Layer A artifact (dossier narrative if one exists, and/or the exact `claims.csv`/`management_qna.csv` row sets) that fed the frozen label
- `freeze_timestamp_utc`, `frozen_by`
- `reviewer_capture_exposure_log`: a list of `{reviewer_id, layer, exposure_timestamp_utc}` entries recording any time a reviewer was shown Layer B/C content for this event — used to check the disqualification rule (Section 8.5)
- `reveal_events`: a list of `{layer, revealed_at_utc, revealed_by}` entries recording when Layer B/C content was actually revealed to a reviewer/process, as distinct from when it was merely captured

**Validator-enforced ordering:** every entry in `reveal_events[].revealed_at_utc` must be ≥ `freeze_timestamp_utc`. Any `reviewer_capture_exposure_log` entry with `exposure_timestamp_utc` earlier than `freeze_timestamp_utc`, for a reviewer who also appears as `frozen_by`, is a disqualifying conflict and fails validation.

## 18. Executable validator

`validator/validate_event_dossier.py` implements a deterministic, network-free, fixture-driven check of the gates in Sections 4–11 and 17, plus the taxonomy/schema rules in Section 15. See `validator/README.md` for usage and `VALIDATION_CHECKLIST_v0.1_DRAFT.md` for the checklist it implements. The validator is a guardrail, not proof of perfect blinding — it catches schema violations, missing sourcing metadata, and detectable reaction-language leakage, but it cannot verify that a human reviewer's *judgment* (e.g., `management_tone`) was uninfluenced by something they read outside these files. Human review remains required regardless of validator pass/fail.

## 16. Open items not resolved by this draft

See the "unresolved design choices" list in the final chat report accompanying this document's creation — this protocol is v0.1 and is expected to be revised before the first confirmatory event is processed.
