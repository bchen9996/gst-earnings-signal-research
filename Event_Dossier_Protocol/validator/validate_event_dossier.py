#!/usr/bin/env python3
"""Deterministic, network-free validator for Event Dossier Protocol fixture directories.

Operates ONLY on files inside a single supplied fixture directory. Never touches
the network, the operational Phase 2 cache, or the Phase 2 panel itself. Never
reads real Layer B/C feature data -- fixtures are small, synthetic, self-contained
directories built specifically to exercise one or more validation gates.

Usage:
    python validate_event_dossier.py <fixture_dir> [<fixture_dir> ...]

Exit code: 0 if every supplied fixture passes, 1 if any fixture has at least one
FAIL-severity finding. Findings are printed as human-readable lines; nothing is
silently auto-corrected.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROTOCOL_ROOT = Path(__file__).resolve().parent.parent
LOCKED_UNIVERSE_PATH = PROTOCOL_ROOT / "locked_universe_v0.1.json"

SCHEMA_FILES = {
    "events": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "events.csv",
    "claims": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "claims.csv",
    "claim_sources": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "claim_sources.csv",
    "management_qna": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "management_qna.csv",
    "event_labels": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "event_labels.csv",
    "event_label_capex_effects": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "event_label_capex_effects.csv",
    "market_response_addendum": PROTOCOL_ROOT / "B_Market_Response_Addendum" / "schemas" / "market_response_addendum.csv",
}

EVENT_ID_RE = re.compile(r"^EVT-[A-Z0-9-]+-FY\d{2}Q\d-[A-Z]+$")

QNA_CLASSIFICATIONS = {"fully_answered", "partially_answered", "not_answered", "not_classifiable"}
GUIDANCE_DIRECTIONS = {
    "reiterated_prior_company_guidance", "raised_prior_company_guidance", "lowered_prior_company_guidance",
    "first_guide_above_consensus", "first_guide_in_line", "first_guide_below_consensus",
    "not_guided", "unverifiable",
}
CLAIM_CATEGORIES = {
    "reported_fact", "management_claim", "pre_event_consensus_estimate",
    "analyst_interpretation", "ai_proposed_classification", "human_frozen_label",
}
RETRIEVAL_METHODS = {"direct_fetch", "search_snippet", "blocked", "not_attempted"}
SOURCE_TIERS = {"0", "1", "2", "3", "4", "5"}
DIRECT_TIERS = {"0", "1", "2", "3"}  # usable to back a frozen numeric label
EVENT_DISPOSITIONS = {"development_pilot", "confirmatory", "compromised"}
LABEL_STATUSES = {"draft", "ai_proposed", "human_frozen", "amended"}
CAPEX_OP_DIRECTIONS = {"increasing", "decreasing", "flat", "not_guided", "unverifiable"}
CAPEX_EFFECTS = {"none", "lease_reclassification", "useful_life_change", "other_material_accounting_change", "unverifiable"}
LAYERS = {"A_blinded_core", "B_market_response"}
ALLOWED_DOSSIER_STAGES = {"POST_EVENT_D1", "POST_EVENT_D5", "POST_EVENT_D2"}  # D2 retained only for the documented MSFT pilot precedent

# Reaction-language patterns: stock/share PRICE, OPTIONS/IV, VOLUME, and ANALYST
# reaction phrasing. Deliberately does NOT match plain operating-metric growth
# language ("Azure grew 43%", "revenue increased 18%") -- those verbs/subjects
# are absent from these patterns.
REACTION_PATTERNS = [
    re.compile(r"\b(stock|shares?)\s+\w*\s*(jump|jumps|jumped|rose|rise|rises|surge[ds]?|plunge[ds]?|fell|falls|tumble[ds]?|ralli(?:es|ed)|rally)\b", re.I),
    re.compile(r"\b(after[- ]hours|premarket|pre-market|intraday)\b.{0,40}\b\d+(\.\d+)?\s*%", re.I),
    re.compile(r"\b\d+(\.\d+)?\s*%\s+(after[- ]hours|premarket|intraday)\b", re.I),
    re.compile(r"\bimplied\s+(move|volatility)\b", re.I),
    re.compile(r"\b(trading\s+)?volume\s+(spiked|surged|jumped|rose|fell|reaction)\b", re.I),
    re.compile(r"\bprice\s+target[s]?\b", re.I),
    re.compile(r"\b(upgrade[ds]?|downgrade[ds]?)\b", re.I),
    re.compile(r"\banalysts?\s+(raised|cut|lowered)\s+(their\s+)?(price\s+target|estimates?)\b", re.I),
    re.compile(r"\bmarket\s+(sentiment|reaction)\b", re.I),
]

# Forbidden Layer-A feature terms (GST/Wikipedia/IV/realized-vol/price/volume
# observations must never appear inside Layer-A-tagged content at all).
FORBIDDEN_FEATURE_PATTERNS = [
    re.compile(r"\bGST\s*(z-?score|attention\s+index)\b", re.I),
    re.compile(r"\bWikipedia\s+page\s*views?\b", re.I),
    re.compile(r"\bimplied\s+volatility\b", re.I),
    re.compile(r"\brealized\s+volatility\b", re.I),
    re.compile(r"\btrading\s+volume\b", re.I),
    re.compile(r"\bclosing\s+price\b", re.I),
]


@dataclass
class Finding:
    gate: str
    severity: str  # "FAIL" or "WARN"
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] ({self.gate}) {self.message}"


@dataclass
class FixtureData:
    events: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    claim_sources: list[dict] = field(default_factory=list)
    management_qna: list[dict] = field(default_factory=list)
    event_labels: list[dict] = field(default_factory=list)
    event_label_capex_effects: list[dict] = field(default_factory=list)
    market_response_addendum: list[dict] = field(default_factory=list)
    freeze_manifests: dict[str, dict] = field(default_factory=dict)  # keyed by label_id
    narrative_text: str = ""
    reviewer_access_log: list[dict] = field(default_factory=list)
    disposition_history: list[dict] = field(default_factory=list)
    present_tables: set[str] = field(default_factory=set)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_schema_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        return next(reader)


def load_locked_universe() -> set[str]:
    with LOCKED_UNIVERSE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data["tickers"])


def load_fixture(fixture_dir: Path) -> FixtureData:
    fd = FixtureData()
    table_files = {
        "events": "events.csv",
        "claims": "claims.csv",
        "claim_sources": "claim_sources.csv",
        "management_qna": "management_qna.csv",
        "event_labels": "event_labels.csv",
        "event_label_capex_effects": "event_label_capex_effects.csv",
        "market_response_addendum": "market_response_addendum.csv",
    }
    for attr, filename in table_files.items():
        p = fixture_dir / filename
        rows = _read_csv(p)
        setattr(fd, attr, rows)
        if p.exists():
            fd.present_tables.add(attr)

    for manifest_path in sorted(fixture_dir.glob("freeze_manifest*.json")):
        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
        key = manifest.get("label_id", manifest_path.stem)
        fd.freeze_manifests[key] = manifest

    narrative_path = fixture_dir / "narrative_text.txt"
    if narrative_path.exists():
        fd.narrative_text = narrative_path.read_text(encoding="utf-8")

    fd.reviewer_access_log = _read_csv(fixture_dir / "reviewer_access_log.csv")
    fd.disposition_history = _read_csv(fixture_dir / "disposition_history.csv")

    return fd


def _parse_ts(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _scan(patterns: list[re.Pattern], text: str) -> list[str]:
    hits = []
    if not text:
        return hits
    for pat in patterns:
        for m in pat.finditer(text):
            hits.append(m.group(0))
    return hits


# ---------------------------------------------------------------------------
# Gate 1: identity and schema
# ---------------------------------------------------------------------------

def gate_identity_and_schema(fd: FixtureData, universe: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    gate = "identity_and_schema"

    # Schema headers: every present table's header must be a superset of the
    # canonical schema's required columns (fixtures may omit trailing optional
    # columns is NOT allowed -- all declared columns must exist so downstream
    # code can rely on their presence; extra columns are not allowed either,
    # to keep fixtures honest about what they're testing).
    for table, schema_path in SCHEMA_FILES.items():
        rows = getattr(fd, table)
        if table not in fd.present_tables:
            continue
        expected_cols = _read_schema_header(schema_path)
        if rows:
            actual_cols = list(rows[0].keys())
            missing = [c for c in expected_cols if c not in actual_cols]
            extra = [c for c in actual_cols if c not in expected_cols]
            if missing:
                findings.append(Finding(gate, "FAIL", f"{table}.csv missing required column(s): {missing}"))
            if extra:
                findings.append(Finding(gate, "FAIL", f"{table}.csv has undeclared column(s) not in schema: {extra}"))

    # Stable, unique IDs per table
    id_cols = {
        "events": "event_id",
        "claims": "claim_id",
        "claim_sources": "claim_source_id",
        "management_qna": "qna_id",
        "event_labels": "label_id",
        "event_label_capex_effects": "capex_effect_id",
        "market_response_addendum": "addendum_id",
    }
    for table, id_col in id_cols.items():
        rows = getattr(fd, table)
        seen: dict[str, int] = {}
        for r in rows:
            v = r.get(id_col, "")
            seen[v] = seen.get(v, 0) + 1
        for v, count in seen.items():
            if count > 1:
                findings.append(Finding(gate, "FAIL", f"{table}.csv: duplicate {id_col}={v!r} ({count} rows)"))

    # events.csv row-level checks
    for r in fd.events:
        eid = r.get("event_id", "")
        if not EVENT_ID_RE.match(eid):
            findings.append(Finding(gate, "FAIL", f"events.csv: event_id {eid!r} does not match EVT-{{TICKER}}-{{FYyyQn}}-{{TYPE}}"))
        ticker = r.get("ticker", "")
        if ticker and ticker not in universe:
            findings.append(Finding(gate, "FAIL", f"events.csv: ticker {ticker!r} (event {eid}) is outside the locked v0.1 universe"))
        disp = r.get("event_disposition", "")
        if disp and disp not in EVENT_DISPOSITIONS:
            findings.append(Finding(gate, "FAIL", f"events.csv: invalid event_disposition {disp!r} for {eid}"))
        bccu = r.get("blinding_compromised_for_confirmatory_use", "")
        if bccu and bccu.lower() not in {"true", "false"}:
            findings.append(Finding(gate, "FAIL", f"events.csv: blinding_compromised_for_confirmatory_use must be true/false, got {bccu!r} for {eid}"))
        fp = r.get("fiscal_period", "")
        if fp and not re.match(r"^FY\d{2}Q\d$", fp):
            findings.append(Finding(gate, "FAIL", f"events.csv: fiscal_period {fp!r} is not in FY{{yy}}Q{{n}} form for {eid}"))

    event_ids = {r.get("event_id") for r in fd.events}
    claim_ids = {r.get("claim_id") for r in fd.claims}
    label_ids = {r.get("label_id") for r in fd.event_labels}

    # event_labels.csv row-level checks
    for r in fd.event_labels:
        lid = r.get("label_id", "")
        stage = r.get("dossier_stage", "")
        if stage and stage not in ALLOWED_DOSSIER_STAGES:
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: dossier_stage {stage!r} not an allowed capture horizon for {lid}"))
        status = r.get("label_status", "")
        if status and status not in LABEL_STATUSES:
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: invalid label_status {status!r} for {lid}"))
        gd = r.get("guidance_direction", "")
        if gd and gd not in GUIDANCE_DIRECTIONS:
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: invalid guidance_direction {gd!r} for {lid}"))
        cod = r.get("capex_operational_direction", "")
        if cod and cod not in CAPEX_OP_DIRECTIONS:
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: invalid capex_operational_direction {cod!r} for {lid}"))
        # FK: event_id
        if fd.events and r.get("event_id") not in event_ids:
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} references unknown event_id {r.get('event_id')!r}"))
        # FK: catalyst claim ids
        for fkcol in ("primary_positive_catalyst_claim_id", "primary_negative_catalyst_claim_id"):
            v = r.get(fkcol, "")
            if v and fd.claims and v not in claim_ids:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid}.{fkcol} references unknown claim_id {v!r}"))
        amend_of = r.get("amendment_of_label_id", "")
        if amend_of:
            if amend_of == lid:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} cannot amend itself"))
            elif fd.event_labels and amend_of not in label_ids:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid}.amendment_of_label_id references unknown label_id {amend_of!r}"))

    # claims.csv row-level checks
    for r in fd.claims:
        cid = r.get("claim_id", "")
        if fd.events and r.get("event_id") not in event_ids:
            findings.append(Finding(gate, "FAIL", f"claims.csv: {cid} references unknown event_id {r.get('event_id')!r}"))
        cat = r.get("claim_category", "")
        if cat and cat not in CLAIM_CATEGORIES:
            findings.append(Finding(gate, "FAIL", f"claims.csv: invalid claim_category {cat!r} for {cid}"))
        layer = r.get("layer", "")
        if layer and layer not in LAYERS:
            findings.append(Finding(gate, "FAIL", f"claims.csv: invalid layer {layer!r} for {cid}"))
        vs = r.get("verification_status", "")
        if vs and vs not in {"verified", "partially_verified", "unverifiable"}:
            findings.append(Finding(gate, "FAIL", f"claims.csv: invalid verification_status {vs!r} for {cid}"))

    # claim_sources.csv row-level checks
    for r in fd.claim_sources:
        csid = r.get("claim_source_id", "")
        if fd.claims and r.get("claim_id") not in claim_ids:
            findings.append(Finding(gate, "FAIL", f"claim_sources.csv: {csid} references unknown claim_id {r.get('claim_id')!r}"))
        rm = r.get("retrieval_method", "")
        if rm and rm not in RETRIEVAL_METHODS:
            findings.append(Finding(gate, "FAIL", f"claim_sources.csv: invalid retrieval_method {rm!r} for {csid}"))
        tier = r.get("source_tier", "")
        if tier and tier not in SOURCE_TIERS:
            findings.append(Finding(gate, "FAIL", f"claim_sources.csv: invalid source_tier {tier!r} for {csid}"))

    # management_qna.csv row-level checks
    for r in fd.management_qna:
        qid = r.get("qna_id", "")
        if fd.events and r.get("event_id") not in event_ids:
            findings.append(Finding(gate, "FAIL", f"management_qna.csv: {qid} references unknown event_id {r.get('event_id')!r}"))
        cls = r.get("classification", "")
        if cls and cls not in QNA_CLASSIFICATIONS:
            findings.append(Finding(gate, "FAIL", f"management_qna.csv: invalid classification {cls!r} for {qid}"))
        cb = r.get("classified_by", "")
        if cb and cb not in {"ai_proposed", "human_frozen"}:
            findings.append(Finding(gate, "FAIL", f"management_qna.csv: invalid classified_by {cb!r} for {qid}"))

    # event_label_capex_effects.csv row-level checks
    for r in fd.event_label_capex_effects:
        ceid = r.get("capex_effect_id", "")
        if fd.event_labels and r.get("label_id") not in label_ids:
            findings.append(Finding(gate, "FAIL", f"event_label_capex_effects.csv: {ceid} references unknown label_id {r.get('label_id')!r}"))
        eff = r.get("capex_accounting_presentation_effect", "")
        if eff and eff not in CAPEX_EFFECTS:
            findings.append(Finding(gate, "FAIL", f"event_label_capex_effects.csv: invalid effect {eff!r} for {ceid}"))
        evid = r.get("evidence_claim_id", "")
        if evid and fd.claims and evid not in claim_ids:
            findings.append(Finding(gate, "FAIL", f"event_label_capex_effects.csv: {ceid} references unknown claim_id {evid!r}"))

    # market_response_addendum.csv row-level checks
    for r in fd.market_response_addendum:
        aid = r.get("addendum_id", "")
        if fd.events and r.get("event_id") not in event_ids:
            findings.append(Finding(gate, "FAIL", f"market_response_addendum.csv: {aid} references unknown event_id {r.get('event_id')!r}"))
        if fd.event_labels and r.get("linked_label_id") not in label_ids:
            findings.append(Finding(gate, "FAIL", f"market_response_addendum.csv: {aid} references unknown linked_label_id {r.get('linked_label_id')!r}"))

    return findings


# ---------------------------------------------------------------------------
# Gate 2: source integrity
# ---------------------------------------------------------------------------

def gate_source_integrity(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "source_integrity"

    sources_by_claim: dict[str, list[dict]] = {}
    for s in fd.claim_sources:
        sources_by_claim.setdefault(s.get("claim_id"), []).append(s)

    claims_by_id = {c.get("claim_id"): c for c in fd.claims}

    material_categories = {"reported_fact", "management_claim", "pre_event_consensus_estimate", "analyst_interpretation"}

    frozen_label_ids = {r.get("label_id") for r in fd.event_labels if r.get("label_status") == "human_frozen"}
    frozen_event_ids = {r.get("event_id") for r in fd.event_labels if r.get("label_status") == "human_frozen"}

    referenced_by_frozen_label: set[str] = set()
    for r in fd.event_labels:
        if r.get("label_status") != "human_frozen":
            continue
        for fkcol in ("primary_positive_catalyst_claim_id", "primary_negative_catalyst_claim_id"):
            v = r.get(fkcol, "")
            if v:
                referenced_by_frozen_label.add(v)

    for c in fd.claims:
        cid = c.get("claim_id")
        cat = c.get("claim_category", "")
        layer = c.get("layer", "")
        srcs = sources_by_claim.get(cid, [])

        if cat in material_categories and layer == "A_blinded_core":
            if not srcs:
                findings.append(Finding(gate, "FAIL", f"claims.csv: material claim {cid} ({cat}) has no claim_sources.csv row"))

        needs_direct = cid in referenced_by_frozen_label or (c.get("event_id") in frozen_event_ids and cid in referenced_by_frozen_label)
        if needs_direct:
            has_direct = any(
                s.get("retrieval_method") == "direct_fetch" and s.get("source_tier") in DIRECT_TIERS
                for s in srcs
            )
            if not has_direct:
                findings.append(Finding(gate, "FAIL", f"claims.csv: claim {cid} supports a human_frozen label but has no direct_fetch (tier 0-3) source"))
            if c.get("verification_status") == "unverifiable":
                findings.append(Finding(gate, "FAIL", f"claims.csv: claim {cid} is verification_status=unverifiable but supports a human_frozen label"))

        if cat == "pre_event_consensus_estimate":
            provider = c.get("consensus_provider", "")
            asof = c.get("consensus_asof_date", "")
            if not provider:
                findings.append(Finding(gate, "FAIL", f"claims.csv: consensus claim {cid} missing consensus_provider"))
            elif re.search(r"[,;/]| and | cluster| blended| mixed", provider, re.I):
                findings.append(Finding(gate, "FAIL", f"claims.csv: consensus claim {cid} blends multiple providers into one value: {provider!r}"))
            if not asof:
                findings.append(Finding(gate, "FAIL", f"claims.csv: consensus claim {cid} missing consensus_asof_date"))
            gaap = c.get("gaap_basis", "")
            if not gaap:
                findings.append(Finding(gate, "FAIL", f"claims.csv: consensus claim {cid} missing gaap_basis"))

    # Surprise percentages require a valid, direct-sourced, unblended consensus claim for the same event
    consensus_by_event: dict[str, list[dict]] = {}
    for c in fd.claims:
        if c.get("claim_category") == "pre_event_consensus_estimate":
            consensus_by_event.setdefault(c.get("event_id"), []).append(c)

    def _consensus_valid(c: dict) -> bool:
        provider = c.get("consensus_provider", "")
        asof = c.get("consensus_asof_date", "")
        gaap = c.get("gaap_basis", "")
        if not provider or not asof or not gaap:
            return False
        if re.search(r"[,;/]| and | cluster| blended| mixed", provider, re.I):
            return False
        srcs = sources_by_claim.get(c.get("claim_id"), [])
        return any(s.get("retrieval_method") == "direct_fetch" and s.get("source_tier") in DIRECT_TIERS for s in srcs)

    for lr in fd.event_labels:
        lid = lr.get("label_id", "")
        eid = lr.get("event_id", "")
        for pct_field in ("eps_surprise_pct", "revenue_surprise_pct"):
            v = lr.get(pct_field, "")
            if v == "" or v is None:
                continue  # explicitly null is allowed (unverifiable consensus policy)
            candidates = consensus_by_event.get(eid, [])
            if not any(_consensus_valid(c) for c in candidates):
                findings.append(Finding(
                    gate, "FAIL",
                    f"event_labels.csv: {lid}.{pct_field}={v!r} is set but no valid (provider+as-of+GAAP-basis+direct-sourced, unblended) consensus claim exists for event {eid}",
                ))

    return findings


# ---------------------------------------------------------------------------
# Gate 3: blinding
# ---------------------------------------------------------------------------

def gate_blinding(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "blinding"

    layer_a_claim_ids = {c.get("claim_id") for c in fd.claims if c.get("layer") == "A_blinded_core"}

    def check_text(label: str, text: str) -> None:
        for hit in _scan(REACTION_PATTERNS, text):
            findings.append(Finding(gate, "FAIL", f"{label}: forbidden market-reaction language detected: {hit!r}"))
        for hit in _scan(FORBIDDEN_FEATURE_PATTERNS, text):
            findings.append(Finding(gate, "FAIL", f"{label}: forbidden Layer B/C feature term detected inside Layer A content: {hit!r}"))

    for c in fd.claims:
        if c.get("layer") != "A_blinded_core":
            continue
        check_text(f"claims.csv[{c.get('claim_id')}].claim_text", c.get("claim_text", ""))

    for q in fd.management_qna:
        check_text(f"management_qna.csv[{q.get('qna_id')}].question_text", q.get("question_text", ""))
        check_text(f"management_qna.csv[{q.get('qna_id')}].response_text", q.get("response_text", ""))

    for s in fd.claim_sources:
        if s.get("claim_id") not in layer_a_claim_ids:
            continue
        check_text(f"claim_sources.csv[{s.get('claim_source_id')}].source_name", s.get("source_name", ""))

    if fd.narrative_text:
        check_text("narrative_text.txt", fd.narrative_text)

    return findings


# ---------------------------------------------------------------------------
# Gate 4: label integrity
# ---------------------------------------------------------------------------

def gate_label_integrity(fd: FixtureData, fixture_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    gate = "label_integrity"

    for r in fd.event_labels:
        lid = r.get("label_id", "")
        status = r.get("label_status", "")
        if status == "human_frozen":
            frozen_by = r.get("frozen_by", "")
            frozen_at = r.get("frozen_at_utc", "")
            manifest_path = r.get("freeze_manifest_path", "")
            if not frozen_by or frozen_by.strip().lower() in {"ai", "ai_proposed", "system", ""}:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} is human_frozen but frozen_by is missing/non-human ({frozen_by!r})"))
            if not frozen_at or _parse_ts(frozen_at) is None:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} is human_frozen but frozen_at_utc is missing/unparseable"))
            manifest = fd.freeze_manifests.get(lid) or fd.freeze_manifests.get(manifest_path)
            if manifest is None:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} is human_frozen but no matching freeze_manifest*.json was found"))
            else:
                if not manifest.get("layer_a_artifact_hashes"):
                    findings.append(Finding(gate, "FAIL", f"freeze_manifest for {lid}: layer_a_artifact_hashes is empty"))
                else:
                    for h in manifest["layer_a_artifact_hashes"]:
                        recorded = h.get("sha256", "")
                        artifact_path = h.get("artifact_path", "")
                        if not re.match(r"^[a-f0-9]{64}$", recorded):
                            findings.append(Finding(gate, "FAIL", f"freeze_manifest for {lid}: malformed sha256 for {artifact_path!r}"))
                            continue
                        actual_file = fixture_dir / artifact_path
                        if actual_file.exists() and actual_file.is_file():
                            actual_hash = hashlib.sha256(actual_file.read_bytes()).hexdigest()
                            if actual_hash != recorded:
                                findings.append(Finding(
                                    gate, "FAIL",
                                    f"freeze_manifest for {lid}: recorded sha256 for {artifact_path!r} "
                                    f"({recorded}) does not match the artifact's actual current hash ({actual_hash}) "
                                    f"-- Layer A content changed after freeze",
                                ))
                if not manifest.get("freeze_timestamp_utc") or _parse_ts(manifest["freeze_timestamp_utc"]) is None:
                    findings.append(Finding(gate, "FAIL", f"freeze_manifest for {lid}: freeze_timestamp_utc missing/unparseable"))
        elif status in {"draft", "ai_proposed"}:
            if r.get("frozen_by") or r.get("frozen_at_utc"):
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} has status={status} but carries frozen_by/frozen_at_utc -- labels must stay AI_PROPOSED until genuinely reviewed"))

        amend_of = r.get("amendment_of_label_id", "")
        if amend_of and not r.get("amendment_reason", ""):
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} amends {amend_of} but has no amendment_reason"))

    # compromised/development-pilot events cannot return to confirmatory (optional disposition_history.csv)
    history_by_event: dict[str, list[dict]] = {}
    for h in fd.disposition_history:
        history_by_event.setdefault(h.get("event_id"), []).append(h)
    for eid, rows in history_by_event.items():
        rows_sorted = sorted(rows, key=lambda r: r.get("recorded_at_utc", ""))
        seen_terminal = False
        for r in rows_sorted:
            disp = r.get("event_disposition", "")
            if disp in {"development_pilot", "compromised"}:
                seen_terminal = True
            elif disp == "confirmatory" and seen_terminal:
                findings.append(Finding(gate, "FAIL", f"disposition_history.csv: event {eid} moved back to confirmatory after being {disp and 'development_pilot/compromised'} -- one-directional rule violated"))

    return findings


# ---------------------------------------------------------------------------
# Gate 5: layer separation
# ---------------------------------------------------------------------------

def gate_layer_separation(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "layer_separation"

    label_by_id = {r.get("label_id"): r for r in fd.event_labels}

    for label_id, manifest in fd.freeze_manifests.items():
        freeze_ts = _parse_ts(manifest.get("freeze_timestamp_utc", ""))
        frozen_by = manifest.get("frozen_by", "")

        for reveal in manifest.get("reveal_events", []):
            revealed_at = _parse_ts(reveal.get("revealed_at_utc", ""))
            if freeze_ts is not None and revealed_at is not None and revealed_at < freeze_ts:
                findings.append(Finding(
                    gate, "FAIL",
                    f"freeze_manifest for {label_id}: {reveal.get('layer')} revealed_at_utc={reveal.get('revealed_at_utc')} "
                    f"predates freeze_timestamp_utc={manifest.get('freeze_timestamp_utc')}",
                ))

        for exposure in manifest.get("reviewer_capture_exposure_log", []):
            exposure_ts = _parse_ts(exposure.get("exposure_timestamp_utc", ""))
            if (
                freeze_ts is not None
                and exposure_ts is not None
                and exposure_ts < freeze_ts
                and exposure.get("reviewer_id") == frozen_by
            ):
                findings.append(Finding(
                    gate, "FAIL",
                    f"freeze_manifest for {label_id}: reviewer {frozen_by!r} was exposed to {exposure.get('layer')} at "
                    f"{exposure.get('exposure_timestamp_utc')}, before freeze at {manifest.get('freeze_timestamp_utc')} -- "
                    f"this reviewer is disqualified from signing this label",
                ))

    # Layer B capture rows themselves are always permitted regardless of freeze
    # state (capture != reveal) -- nothing to flag purely for existing early.
    # But a market_response_addendum row must reference a real label.
    for r in fd.market_response_addendum:
        lid = r.get("linked_label_id", "")
        if lid and label_by_id and lid not in label_by_id:
            findings.append(Finding(gate, "FAIL", f"market_response_addendum.csv: {r.get('addendum_id')} references unknown linked_label_id {lid!r}"))

    return findings


def validate(fixture_dir: Path) -> tuple[bool, list[Finding]]:
    fd = load_fixture(fixture_dir)
    universe = load_locked_universe()
    findings: list[Finding] = []
    findings.extend(gate_identity_and_schema(fd, universe))
    findings.extend(gate_source_integrity(fd))
    findings.extend(gate_blinding(fd))
    findings.extend(gate_label_integrity(fd, fixture_dir))
    findings.extend(gate_layer_separation(fd))
    ok = not any(f.severity == "FAIL" for f in findings)
    return ok, findings


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: validate_event_dossier.py <fixture_dir> [<fixture_dir> ...]", file=sys.stderr)
        return 2
    overall_ok = True
    for arg in argv:
        fixture_dir = Path(arg)
        ok, findings = validate(fixture_dir)
        status = "PASS" if ok else "FAIL"
        print(f"=== {fixture_dir.name}: {status} ===")
        for f in findings:
            print(f"  {f}")
        if not findings:
            print("  (no findings)")
        overall_ok = overall_ok and ok
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
