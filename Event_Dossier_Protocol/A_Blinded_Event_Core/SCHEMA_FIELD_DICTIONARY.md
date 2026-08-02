# Layer A Schema Field Dictionary

**Revision 2 (2026-08-02)**: renamed the `consensus_estimate` claim category to `pre_event_consensus_estimate` for precision; added `events.blinding_compromised_for_confirmatory_use`; removed the semicolon-delimited `capex_accounting_presentation_effect` column from `event_labels.csv` in favor of the normalized `event_label_capex_effects.csv` child table; added `event_labels.freeze_manifest_path`.

Companion to the header-only CSVs in `schemas/`. No populated rows exist yet — this defines what a valid row must contain. See `../EVENT_DOSSIER_PROTOCOL_v0.1_DRAFT.md` for the rules these fields enforce.

## events.csv

| Field | Type | Required | Notes |
|---|---|---|---|
| event_id | string | yes | `EVT-{TICKER}-{FISCAL_PERIOD_COMPACT}-{EVENT_TYPE}`, unique, immutable once referenced |
| ticker | string | yes | Must belong to `../locked_universe_v0.1.json` for a `confirmatory`-eligible event |
| company_name | string | yes | |
| fiscal_period | string | yes | `FY{YY}Q{N}` |
| event_type | enum | yes | `ERN` (only value in v0.1 scope) |
| earnings_date | date | yes | Calendar date of release |
| release_market_session | enum | yes | `before_open` \| `during_session` \| `after_close` |
| event_datetime_utc | timestamp | yes | Best-known release timestamp |
| niche | string | yes | `large_cap_earnings` (v0.1's only niche) |
| protocol_version | string | yes | e.g. `0.1` |
| event_disposition | enum | yes | `development_pilot` \| `confirmatory` \| `compromised`; may only move away from `confirmatory`, never back |
| blinding_compromised_for_confirmatory_use | boolean | yes | Independent of `event_disposition`, so blinding-compromised events are filterable regardless of disposition wording. `true` and permanent once set — never reset to `false`. |
| created_by | string | yes | `ai` or reviewer identity |
| created_at_utc | timestamp | yes | |

## claims.csv

| Field | Type | Required | Notes |
|---|---|---|---|
| claim_id | string | yes | `{event_id}-CLM-{seq:04d}` |
| event_id | string | yes | FK → events.csv |
| dossier_section | string | yes | Which narrative section this claim supports |
| claim_text | string | yes | The claim as stated |
| value_type | enum | yes | `numeric` \| `categorical` \| `qualitative` \| `quote` |
| claim_category | enum | yes | `reported_fact` \| `management_claim` \| `pre_event_consensus_estimate` \| `analyst_interpretation` \| `ai_proposed_classification` \| `human_frozen_label` — every claim must be exactly one of these six. Named `pre_event_consensus_estimate`, not `consensus_estimate`, to make explicit that post-event estimate revisions are a **different** category living only in Layer B (`layer = B_market_response`), never this Layer-A value. |
| numeric_value | number | conditional | Required if `value_type = numeric` |
| unit | string | conditional | e.g. `USD_billions`, `pct`, `USD_per_share` |
| gaap_basis | enum | conditional | `GAAP` \| `non-GAAP` \| `NA` — required for any EPS/revenue/margin figure, and required on both sides of a surprise-percentage pairing |
| currency_basis | enum | conditional | `reported` \| `constant_currency` \| `NA` — required for any growth figure |
| fiscal_period_basis | string | yes | Which period this claim describes (may differ from event's own period, e.g. a prior-quarter comparison) |
| comparison_period | enum | conditional | `YoY` \| `QoQ` \| `vs_guidance` \| `vs_consensus` \| `NA` |
| consensus_provider | string | conditional | Required if `claim_category = pre_event_consensus_estimate`; never blended across providers — a second provider's figure is a separate claim row, not a merged value |
| consensus_asof_date | date | conditional | Required if `claim_category = pre_event_consensus_estimate`; must predate `events.earnings_date` |
| novelty_eval_basis | enum | yes | `checked_absent` \| `checked_present_prior_disclosure` \| `not_evaluated` — default `not_evaluated` |
| verification_status | enum | yes | `verified` \| `partially_verified` \| `unverifiable` |
| layer | enum | yes | `A_blinded_core` \| `B_market_response` — a claim tagged `B_market_response` may exist (captured) at any time but must never be read by the Layer A labeling process before that event's label is frozen |
| created_at_utc | timestamp | yes | |

**"Source access status" for consensus surprise calculations**: not a separate column — determined by joining to `claim_sources.csv` on `claim_id` and checking `retrieval_method`/`source_tier` on the linked row(s). A `pre_event_consensus_estimate` claim whose only linked source has `retrieval_method = search_snippet` is `verification_status = unverifiable` and cannot feed a frozen surprise-percentage field.

## claim_sources.csv (many-to-many: a claim may have multiple corroborating sources)

| Field | Type | Required | Notes |
|---|---|---|---|
| claim_source_id | string | yes | `{event_id}-SRC-{seq:03d}` |
| claim_id | string | yes | FK → claims.csv |
| source_name | string | yes | e.g. "Microsoft FY26 Q4 press release" — must NOT reproduce a title containing reaction language verbatim if the claim is Layer A (see validator gate 8) |
| source_url | string | yes | |
| source_publication_timestamp_utc | timestamp | yes | |
| retrieval_method | enum | yes | `direct_fetch` \| `search_snippet` \| `blocked` \| `not_attempted` |
| source_tier | enum | yes | `0`..`5` per the protocol's source hierarchy |
| accessed_at_utc | timestamp | yes | |
| corroborates_claim_source_id | string | no | Self-referential FK if this source independently confirms another source row for the same claim |
| notes | string | no | |

## management_qna.csv

| Field | Type | Required | Notes |
|---|---|---|---|
| qna_id | string | yes | `{event_id}-QNA-{seq:02d}` |
| event_id | string | yes | FK → events.csv |
| analyst_name | string | yes | |
| analyst_firm | string | yes | |
| question_text | string | yes | |
| question_topic | string | yes | Short topic tag |
| response_text | string | yes | |
| classification | enum | yes | `fully_answered` \| `partially_answered` \| `not_answered` \| `not_classifiable` |
| classification_basis | string | yes | Which written rule was applied and why |
| classified_by | enum | yes | `ai_proposed` \| `human_frozen` |
| classified_at_utc | timestamp | yes | |

## event_labels.csv (append-only; one row per label version)

| Field | Type | Required | Notes |
|---|---|---|---|
| label_id | string | yes | `{event_id}-LBL-{version:02d}` |
| event_id | string | yes | FK → events.csv |
| label_status | enum | yes | `draft` \| `ai_proposed` \| `human_frozen` \| `amended` |
| dossier_stage | enum | yes | `POST_EVENT_D1` \| `POST_EVENT_D5` \| other documented non-standard stage (e.g. pilot's `POST_EVENT_D2`) |
| eps_surprise_pct | number\|null | yes | Null with `unverifiable` reasoning captured in `notes` if not computable |
| revenue_surprise_pct | number\|null | yes | |
| guidance_direction | enum | yes | See protocol §15.2 (8 values incl. `unverifiable`) |
| cloud_surprise_direction | enum | yes | `positive` \| `negative` \| `in-line` \| `not_applicable` \| `unverifiable` |
| margin_surprise_direction | enum | yes | `positive` \| `negative` \| `in-line` \| `unverifiable` |
| capex_operational_direction | enum | yes | `increasing` \| `decreasing` \| `flat` \| `not_guided` \| `unverifiable` — the accounting-presentation-effect axis is **not** a column here; see `event_label_capex_effects.csv` |
| management_tone | string | yes | Free text, explicitly a qualitative/interpretive field |
| primary_positive_catalyst_claim_id | string | yes | FK → claims.csv |
| primary_negative_catalyst_claim_id | string | yes | FK → claims.csv |
| cross_company_implications_claim_id | string | no | FK → claims.csv; may be multiple, semicolon-delimited (acceptable here since this is a simple list of references, not a controlled taxonomy value like capex effects) |
| information_novelty_score_1_to_5 | integer | yes | Only counts claims with `novelty_eval_basis != not_evaluated` |
| uncertainty_remaining_score_1_to_5 | integer | yes | |
| source_completeness | string | yes | Summary + pointer to claim_sources.csv tier distribution |
| human_verification_status | enum | yes | `pending` \| `reviewed` \| `frozen` |
| frozen_by | string | conditional | Required once `label_status = human_frozen` |
| frozen_at_utc | timestamp | conditional | Required once `label_status = human_frozen` |
| freeze_manifest_path | string | conditional | Required once `label_status = human_frozen`; path to this label's `freeze_manifest.json` |
| protocol_version | string | yes | |
| event_disposition | enum | yes | Mirrors events.csv at time of freeze |
| amendment_of_label_id | string | no | Self-referential FK; required if this row is an amendment |
| amendment_reason | string | conditional | Required if `amendment_of_label_id` is set |
| notes | string | no | |

## event_label_capex_effects.csv (new — normalized child table, one row per effect per label)

| Field | Type | Required | Notes |
|---|---|---|---|
| capex_effect_id | string | yes | `{label_id}-CAPEX-{seq:02d}` |
| label_id | string | yes | FK → event_labels.csv |
| capex_accounting_presentation_effect | enum | yes | `none` \| `lease_reclassification` \| `useful_life_change` \| `other_material_accounting_change` \| `unverifiable` |
| evidence_claim_id | string | yes | FK → claims.csv — the specific disclosure supporting this effect |
| notes | string | no | |

A label with no accounting-presentation effect at all still gets exactly one row with `capex_accounting_presentation_effect = none`, so the child table is never silently empty for a reviewed label — absence of effects is recorded, not implied by absence of rows.
