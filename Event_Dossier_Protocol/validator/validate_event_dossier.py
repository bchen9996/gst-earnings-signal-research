#!/usr/bin/env python3
"""Deterministic, network-free validator for Event Dossier Protocol fixture directories.

Operates ONLY on files inside a single supplied fixture directory. Never touches
the network, the operational Phase 2 cache, or the Phase 2 panel itself. Never
reads real Layer B/C feature data -- fixtures are small, synthetic, self-contained
directories built specifically to exercise one or more validation gates.

Usage:
    python validate_event_dossier.py [--mode draft|proposed|freeze] <fixture_dir> [<fixture_dir> ...]

--mode defaults to "freeze" (the strictest mode, and the one every fixture built
before the 2026-08-03 mode split implicitly assumed). See VALIDATION_MODES /
REQUIRED_TABLES_BY_MODE for what each mode requires.

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
from datetime import datetime, date
from pathlib import Path
from typing import Any

try:
    import jsonschema
    from jsonschema import FormatChecker
    _HAVE_JSONSCHEMA = True
except ImportError:  # pragma: no cover -- exercised only in an environment
    # missing the pinned dependency (see requirements.txt). The freeze-manifest
    # gate below fails closed with a clear diagnostic rather than silently
    # falling back to a weaker hand-rolled check when this happens.
    _HAVE_JSONSCHEMA = False

PROTOCOL_ROOT = Path(__file__).resolve().parent.parent
LOCKED_UNIVERSE_PATH = PROTOCOL_ROOT / "locked_universe_v0.1.json"
FREEZE_MANIFEST_SCHEMA_PATH = PROTOCOL_ROOT / "schemas" / "freeze_manifest.schema.json"

SCHEMA_FILES = {
    "events": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "events.csv",
    "claims": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "claims.csv",
    "claim_sources": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "claim_sources.csv",
    "management_qna": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "management_qna.csv",
    "event_labels": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "event_labels.csv",
    "event_label_capex_effects": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "event_label_capex_effects.csv",
    "event_label_cross_company_implications": PROTOCOL_ROOT / "A_Blinded_Event_Core" / "schemas" / "event_label_cross_company_implications.csv",
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
VALUE_TYPES = {"numeric", "categorical", "qualitative", "quote"}
GAAP_BASES = {"GAAP", "non-GAAP", "NA"}
CURRENCY_BASES = {"reported", "constant_currency", "NA"}
COMPARISON_PERIODS = {"YoY", "QoQ", "vs_guidance", "vs_consensus", "NA"}
NOVELTY_EVAL_BASES = {"checked_absent", "checked_present_prior_disclosure", "not_evaluated"}
VERIFICATION_STATUSES = {"verified", "partially_verified", "unverifiable"}
RETRIEVAL_METHODS = {"direct_fetch", "search_snippet", "blocked", "not_attempted"}
SOURCE_TIERS = {"0", "1", "2", "3", "4", "5"}
DIRECT_TIERS = {"0", "1", "2", "3"}  # usable to back a frozen numeric label
EVENT_DISPOSITIONS = {"development_pilot", "confirmatory", "compromised"}
LABEL_STATUSES = {"draft", "ai_proposed", "human_frozen", "amended"}
CAPEX_OP_DIRECTIONS = {"increasing", "decreasing", "flat", "not_guided", "unverifiable"}
CAPEX_EFFECTS = {"none", "lease_reclassification", "useful_life_change", "other_material_accounting_change", "unverifiable"}
CLOUD_SURPRISE_DIRECTIONS = {"positive", "negative", "in-line", "not_applicable", "unverifiable"}
MARGIN_SURPRISE_DIRECTIONS = {"positive", "negative", "in-line", "unverifiable"}
HUMAN_VERIFICATION_STATUSES = {"pending", "reviewed", "frozen"}
CLASSIFIED_BY_VALUES = {"ai_proposed", "human_frozen"}
LAYERS = {"A_blinded_core", "B_market_response"}
ALLOWED_DOSSIER_STAGES = {"POST_EVENT_D1", "POST_EVENT_D5", "POST_EVENT_D2"}  # D2 retained only for the documented MSFT pilot precedent
RELEASE_MARKET_SESSIONS = {"before_open", "during_session", "after_close"}
EVENT_TYPES = {"ERN"}
# 2026-08-03 correction: the v0.1 universe is 24 SPECIFIC locked tickers,
# not uniformly "large-cap" -- it includes names like GME and NCLH that are
# not large-cap by any conventional definition. "large_cap_earnings" was a
# materially inaccurate niche label and is replaced everywhere.
NICHE_VALUES = {"fixed_24_ticker_earnings_panel"}
REACTION_WINDOWS = {"after_hours", "next_session_close", "multi_session"}

# 2026-08-03 (second correction pass): a controlled metric classification for
# every claim, so a surprise-percentage linkage can mechanically confirm an
# EPS claim was never accidentally paired with a revenue claim (or vice
# versa). Optional per-row (not every claim is metric-bearing commentary),
# but enum-checked whenever populated, and REQUIRED on any claim actually
# used as eps/revenue actual-or-consensus surprise evidence (enforced in
# gate_surprise_linkage, not here, since that requirement is conditional on
# the claim's role, not an unconditional per-row rule).
METRIC_NAMES = {"eps", "revenue", "guidance_revenue", "cloud_growth", "margin", "capex", "other"}

# 2026-08-03 (second correction pass): a null eps_surprise_pct/revenue_surprise_pct
# must now carry an explicit, enum-controlled reason -- an unexplained blank is
# a validation failure, not a silently accepted absence.
SURPRISE_NULL_REASONS = {"consensus_unavailable", "consensus_unverifiable", "not_applicable"}

SCORE_MIN, SCORE_MAX = 1, 5
SURPRISE_PCT_TOLERANCE = 0.05  # documented tolerance, in percentage points, for recomputed-vs-stored surprise agreement

# --- Validation modes (2026-08-03, second correction pass) -----------------
# A fixture is validated against exactly one mode. Each mode's required-table
# floor is checked FIRST (gate_required_tables) -- an empty directory, or a
# directory missing something the mode structurally depends on, fails before
# any other gate even runs, rather than silently producing zero findings.
VALIDATION_MODES = {"draft", "proposed", "freeze"}
REQUIRED_TABLES_BY_MODE: dict[str, set[str]] = {
    # A draft dossier is, at minimum, an identified event.
    "draft": {"events"},
    # An AI-proposed label under review needs the full Layer-A evidentiary
    # base plus the label row itself.
    "proposed": {"events", "claims", "claim_sources", "management_qna", "event_labels"},
    # A freeze-ready event needs the same core tables as "proposed" PLUS (see
    # the dedicated check in gate_required_tables) at least one genuinely
    # human_frozen label. The stronger "all seven artifact types present
    # exactly once, including header-only child files when empty" rule is
    # enforced at the level of each individual frozen BUNDLE
    # (frozen/{event_id}/{label_id}/, see gate_freeze_manifest) -- it is a
    # property of the bundle a freeze actually produced, not a blanket
    # requirement that every fixture directory carry two otherwise-unused
    # child-table files at its root regardless of whether any label in it
    # is being frozen.
    "freeze": {"events", "claims", "claim_sources", "management_qna", "event_labels"},
}

# --- Immutable freeze bundle (2026-08-03, second correction pass) ----------
#
# WHY: the original design hashed the fixture's own MUTABLE working CSVs
# (events.csv, claims.csv, etc. at the fixture root) directly. That is
# structurally unsound -- those same files are exactly what a later amendment
# or an unrelated event in the same batch would go on to edit. A frozen
# label's evidence trail must be an independent, immutable snapshot, not a
# live reference into tables that keep changing underneath it.
#
# Every freeze_manifest*.json now names artifacts that must live under
# frozen/{event_id}/{label_id}/ -- a directory scoped to exactly one label
# version, containing canonical, never-edited-after-the-fact copies of all
# seven Layer-A artifact types (the four original tables, PLUS the one
# frozen event_labels.csv ROW as its own single-row event_label.csv file,
# PLUS the two normalized child tables, present even when empty/header-only).
# An amendment creates label_id-v2's OWN frozen/{event_id}/{label_id_v2}/
# bundle; it never edits label_id-v1's bundle, which must remain
# independently hash-valid forever.
#
# NOTE the deliberate naming split: "event_label.csv" (singular) inside a
# frozen bundle is the ONE frozen label-version row; "event_labels.csv"
# (plural) at the fixture root is the mutable WORKING table with every
# label row/version. They are never the same file.
FROZEN_BUNDLE_REQUIRED_BASENAMES = {
    "events.csv", "claims.csv", "claim_sources.csv", "management_qna.csv",
    "event_label.csv", "event_label_capex_effects.csv", "event_label_cross_company_implications.csv",
}
# Any artifact_path containing one of these is a Layer-B/C leak into a
# Layer-A freeze bundle -- forbidden outright.
FORBIDDEN_MANIFEST_PATH_MARKERS = ("market_response_addendum", "B_Market_Response_Addendum", "C_Attention_Feature_Join")

# Reaction-language patterns: stock/share PRICE, OPTIONS/IV, VOLUME, and ANALYST
# reaction phrasing. Deliberately does NOT match plain operating-metric growth
# language ("Azure grew 43%", "revenue increased 18%") -- those verbs/subjects
# are absent from these patterns.
REACTION_PATTERNS = [
    re.compile(r"\b(stock|shares?)\s+\w*\s*(jump|jumps|jumped|rose|rise|rises|surge[ds]?|plunge[ds]?|fell|falls|tumble[ds]?|ralli(?:es|ed)|rally|gain(?:ed|s)?|climb(?:ed|s)?)\b", re.I),
    re.compile(r"\b(after[- ]hours|premarket|pre-market|intraday)\b.{0,40}\b\d+(\.\d+)?\s*%", re.I),
    re.compile(r"\b\d+(\.\d+)?\s*%\s+(after[- ]hours|premarket|intraday)\b", re.I),
    re.compile(r"\bthe\s+stock\s+was\s+up\b", re.I),
    re.compile(r"\bmarket\s+(value|cap(?:italization)?)\s+added\b", re.I),
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

# ---------------------------------------------------------------------------
# Declarative per-table field rules. Mechanically enforced by
# gate_field_types() below: required (non-blank) fields, enum membership,
# boolean parsing, date parsing, and timezone-AWARE timestamp parsing.
# Conditional requirements (a field required only when some other field has a
# certain value) and cross-row/cross-table rules are NOT expressible here and
# are handled by their own dedicated gates.
# ---------------------------------------------------------------------------
FIELD_RULES: dict[str, dict[str, Any]] = {
    "events": {
        "required": ["event_id", "ticker", "company_name", "fiscal_period", "event_type", "earnings_date",
                     "release_market_session", "event_datetime_utc", "niche", "protocol_version",
                     "event_disposition", "blinding_compromised_for_confirmatory_use", "created_by", "created_at_utc"],
        "enums": {"event_type": EVENT_TYPES, "release_market_session": RELEASE_MARKET_SESSIONS,
                  "niche": NICHE_VALUES, "event_disposition": EVENT_DISPOSITIONS},
        "booleans": ["blinding_compromised_for_confirmatory_use"],
        "dates": ["earnings_date"],
        "timestamps": ["event_datetime_utc", "created_at_utc"],
    },
    "claims": {
        "required": ["claim_id", "event_id", "dossier_section", "claim_text", "value_type", "claim_category",
                     "fiscal_period_basis", "novelty_eval_basis", "verification_status", "layer", "created_at_utc"],
        "enums": {"value_type": VALUE_TYPES, "claim_category": CLAIM_CATEGORIES, "gaap_basis": GAAP_BASES,
                  "currency_basis": CURRENCY_BASES, "comparison_period": COMPARISON_PERIODS,
                  "novelty_eval_basis": NOVELTY_EVAL_BASES, "verification_status": VERIFICATION_STATUSES,
                  "layer": LAYERS, "metric_name": METRIC_NAMES},
        "dates": ["consensus_asof_date"],
        "timestamps": ["created_at_utc"],
        "numeric_optional": ["numeric_value"],
    },
    "claim_sources": {
        "required": ["claim_source_id", "claim_id", "source_name", "source_url",
                     "source_publication_timestamp_utc", "retrieval_method", "source_tier", "accessed_at_utc"],
        "enums": {"retrieval_method": RETRIEVAL_METHODS, "source_tier": SOURCE_TIERS},
        "timestamps": ["source_publication_timestamp_utc", "accessed_at_utc"],
    },
    "management_qna": {
        "required": ["qna_id", "event_id", "analyst_name", "analyst_firm", "question_text", "question_topic",
                     "response_text", "classification", "classification_basis", "classified_by", "classified_at_utc"],
        "enums": {"classification": QNA_CLASSIFICATIONS, "classified_by": CLASSIFIED_BY_VALUES},
        "timestamps": ["classified_at_utc"],
    },
    "event_labels": {
        "required": ["label_id", "event_id", "label_status", "dossier_stage", "guidance_direction",
                     "cloud_surprise_direction", "margin_surprise_direction", "capex_operational_direction",
                     "management_tone", "primary_positive_catalyst_claim_id", "primary_negative_catalyst_claim_id",
                     "information_novelty_score_1_to_5", "uncertainty_remaining_score_1_to_5",
                     "source_completeness", "human_verification_status", "protocol_version", "event_disposition"],
        "enums": {"label_status": LABEL_STATUSES, "dossier_stage": ALLOWED_DOSSIER_STAGES,
                  "guidance_direction": GUIDANCE_DIRECTIONS, "cloud_surprise_direction": CLOUD_SURPRISE_DIRECTIONS,
                  "margin_surprise_direction": MARGIN_SURPRISE_DIRECTIONS,
                  "capex_operational_direction": CAPEX_OP_DIRECTIONS,
                  "human_verification_status": HUMAN_VERIFICATION_STATUSES, "event_disposition": EVENT_DISPOSITIONS,
                  "eps_surprise_null_reason": SURPRISE_NULL_REASONS, "revenue_surprise_null_reason": SURPRISE_NULL_REASONS},
        "timestamps": ["frozen_at_utc"],
        "numeric_optional": ["eps_surprise_pct", "revenue_surprise_pct"],
        "integer_scores_1_5": ["information_novelty_score_1_to_5", "uncertainty_remaining_score_1_to_5"],
    },
    "event_label_capex_effects": {
        "required": ["capex_effect_id", "label_id", "capex_accounting_presentation_effect", "evidence_claim_id"],
        "enums": {"capex_accounting_presentation_effect": CAPEX_EFFECTS},
    },
    "event_label_cross_company_implications": {
        "required": ["implication_id", "label_id", "claim_id"],
    },
    "market_response_addendum": {
        "required": ["addendum_id", "event_id", "linked_label_id", "captured_at_utc", "captured_by"],
        "enums": {"price_reaction_window": REACTION_WINDOWS},
        "timestamps": ["captured_at_utc"],
    },
}

ID_COL_BY_TABLE = {
    "events": "event_id", "claims": "claim_id", "claim_sources": "claim_source_id",
    "management_qna": "qna_id", "event_labels": "label_id",
    "event_label_capex_effects": "capex_effect_id",
    "event_label_cross_company_implications": "implication_id",
    "market_response_addendum": "addendum_id",
}

# Claim categories acceptable as evidence for a capex effect or a
# cross-company implication -- excludes meta-categories that describe the
# labeling process itself (ai_proposed_classification, human_frozen_label)
# and the consensus-estimate category (which is pre-event expectation, not
# an implication/effect grounded in reported/observed fact).
CHILD_TABLE_EVIDENCE_CLAIM_CATEGORIES = {"reported_fact", "management_claim", "analyst_interpretation"}


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
    event_label_cross_company_implications: list[dict] = field(default_factory=list)
    market_response_addendum: list[dict] = field(default_factory=list)
    freeze_manifests: dict[str, dict] = field(default_factory=dict)  # keyed by label_id
    freeze_manifest_files: dict[str, str] = field(default_factory=dict)  # label_id -> filename actually read
    narrative_text: str = ""
    reviewer_access_log: list[dict] = field(default_factory=list)
    disposition_history: list[dict] = field(default_factory=list)
    present_tables: set[str] = field(default_factory=set)
    # Actual CSV header read from disk for every present table, captured
    # regardless of whether the file has zero or more data rows -- a
    # header-only (0-row) file with a wrong/missing column is otherwise
    # invisible to csv.DictReader-based row inspection.
    table_headers: dict[str, list[str]] = field(default_factory=dict)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_csv_header(path: Path) -> list[str] | None:
    """Reads just the header row, even when the file has zero data rows.
    Returns None if the file does not exist; [] if the file exists but is
    completely empty (not even a header line)."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            return next(reader)
        except StopIteration:
            return []


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
        "event_label_cross_company_implications": "event_label_cross_company_implications.csv",
        "market_response_addendum": "market_response_addendum.csv",
    }
    for attr, filename in table_files.items():
        p = fixture_dir / filename
        rows = _read_csv(p)
        setattr(fd, attr, rows)
        if p.exists():
            fd.present_tables.add(attr)
            header = _read_csv_header(p)
            fd.table_headers[attr] = header if header is not None else []

    for manifest_path in sorted(fixture_dir.glob("freeze_manifest*.json")):
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            manifest = {"__malformed_json__": True, "__source_file__": manifest_path.name}
        key = manifest.get("label_id", manifest_path.stem)
        fd.freeze_manifests[key] = manifest
        fd.freeze_manifest_files[key] = manifest_path.name

    narrative_path = fixture_dir / "narrative_text.txt"
    if narrative_path.exists():
        fd.narrative_text = narrative_path.read_text(encoding="utf-8")

    fd.reviewer_access_log = _read_csv(fixture_dir / "reviewer_access_log.csv")
    fd.disposition_history = _read_csv(fixture_dir / "disposition_history.csv")

    return fd


def _parse_ts_strict(value: str):
    """Parses an ISO-8601 timestamp that MUST carry an explicit UTC/offset
    designator. A naive timestamp (no 'Z' and no +HH:MM offset) returns
    None -- a validation FAILURE, never a Python exception, and never
    silently treated as UTC. Comparisons must only ever be performed
    between two non-None results of this function, so two naive/mixed-tz
    values can never reach a raw '<'/'>' and raise TypeError."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    has_designator = v.endswith("Z") or bool(re.search(r"[+-]\d{2}:\d{2}$", v))
    if not has_designator:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt


def _parse_ts(value: str):
    """Backward-compatible alias -- strict parsing is now the only mode."""
    return _parse_ts_strict(value)


def _parse_date(value: str):
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_float(value: str):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int_strict(value: str):
    """Only accepts a string that is a genuine integer literal (optionally
    signed) -- "3" is accepted, "3.0" and "3.5" and "abc" are not. Booleans
    are not applicable here since CSV values are always strings."""
    if value is None:
        return None
    v = value.strip()
    if not re.match(r"^-?\d+$", v):
        return None
    return int(v)


def _scan(patterns: list[re.Pattern], text: str) -> list[str]:
    hits = []
    if not text:
        return hits
    for pat in patterns:
        for m in pat.finditer(text):
            hits.append(m.group(0))
    return hits


def _split_semicolon_ids(value: str) -> list[str]:
    """Splits a semicolon-delimited ID list into individual, whitespace-
    trimmed IDs, dropping empty segments (e.g. a trailing ';'). Used only
    for the few remaining legitimately-multi-valued free-form reference
    fields; every ID-bearing field with a controlled vocabulary or FK
    target uses a normalized child table instead (see
    event_label_capex_effects.csv, event_label_cross_company_implications.csv)."""
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


# ---------------------------------------------------------------------------
# Gate 0: required tables / validation mode (2026-08-03, second correction
# pass). Runs first. An empty directory, or a directory missing whatever its
# claimed mode structurally depends on, fails HERE rather than silently
# passing because every other gate's loops simply have nothing to iterate.
# ---------------------------------------------------------------------------

def gate_required_tables(fd: FixtureData, mode: str) -> list[Finding]:
    findings: list[Finding] = []
    gate = "required_tables"

    required = REQUIRED_TABLES_BY_MODE[mode]
    missing = required - fd.present_tables
    if missing:
        findings.append(Finding(gate, "FAIL",
            f"mode={mode!r} requires table(s) {sorted(missing)} to be present in the fixture directory "
            f"(missing: {sorted(missing)})"))

    if mode == "freeze":
        frozen_rows = [r for r in fd.event_labels if r.get("label_status") == "human_frozen"]
        if not frozen_rows:
            findings.append(Finding(gate, "FAIL",
                "mode='freeze' requires at least one event_labels.csv row with label_status=human_frozen "
                "(a complete, freeze-ready event) -- none found"))

    return findings


# ---------------------------------------------------------------------------
# Gate 1: identity and schema (structural: headers, IDs, event_id format,
# ticker-in-universe, fiscal_period format). Header comparison now uses the
# ACTUAL header line read from disk (fd.table_headers), so a header-only
# (0-row) CSV with a missing/extra/misspelled column is caught -- previously
# this check only ran `if rows:`, silently skipping any header-only file.
# ---------------------------------------------------------------------------

def gate_identity_and_schema(fd: FixtureData, universe: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    gate = "identity_and_schema"

    for table, schema_path in SCHEMA_FILES.items():
        if table not in fd.present_tables:
            continue
        expected_cols = _read_schema_header(schema_path)
        actual_cols = fd.table_headers.get(table, [])
        missing = [c for c in expected_cols if c not in actual_cols]
        extra = [c for c in actual_cols if c not in expected_cols]
        if missing:
            findings.append(Finding(gate, "FAIL", f"{table}.csv missing required column(s): {missing}"))
        if extra:
            findings.append(Finding(gate, "FAIL", f"{table}.csv has undeclared column(s) not in schema: {extra}"))

    for table, id_col in ID_COL_BY_TABLE.items():
        rows = getattr(fd, table)
        seen: dict[str, int] = {}
        for r in rows:
            v = r.get(id_col, "")
            seen[v] = seen.get(v, 0) + 1
        for v, count in seen.items():
            if count > 1:
                findings.append(Finding(gate, "FAIL", f"{table}.csv: duplicate {id_col}={v!r} ({count} rows)"))

    for r in fd.events:
        eid = r.get("event_id", "")
        if not EVENT_ID_RE.match(eid):
            findings.append(Finding(gate, "FAIL", f"events.csv: event_id {eid!r} does not match EVT-{{TICKER}}-{{FYyyQn}}-{{TYPE}}"))
        ticker = r.get("ticker", "")
        if ticker and ticker not in universe:
            findings.append(Finding(gate, "FAIL", f"events.csv: ticker {ticker!r} (event {eid}) is outside the locked v0.1 universe"))
        fp = r.get("fiscal_period", "")
        if fp and not re.match(r"^FY\d{2}Q\d$", fp):
            findings.append(Finding(gate, "FAIL", f"events.csv: fiscal_period {fp!r} is not in FY{{yy}}Q{{n}} form for {eid}"))

    return findings


# ---------------------------------------------------------------------------
# Gate 1b: field types -- required/enum/boolean/date/timestamp, mechanically
# applied from FIELD_RULES, plus the handful of numeric/integer/conditional
# checks that don't fit a pure per-field table.
# ---------------------------------------------------------------------------

def gate_field_types(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "field_types"

    for table, rules in FIELD_RULES.items():
        if table not in fd.present_tables:
            continue
        rows = getattr(fd, table)
        id_col = ID_COL_BY_TABLE[table]
        for r in rows:
            rid = r.get(id_col, "<no id>")
            for req in rules.get("required", []):
                if not (r.get(req) or "").strip():
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: required field {req!r} is blank"))
            for enum_field, allowed in rules.get("enums", {}).items():
                v = r.get(enum_field, "")
                if v and v not in allowed:
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {enum_field}={v!r} not in allowed set {sorted(allowed)}"))
            for bool_field in rules.get("booleans", []):
                v = r.get(bool_field, "")
                if v and v.strip().lower() not in {"true", "false"}:
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {bool_field}={v!r} must be true/false"))
            for date_field in rules.get("dates", []):
                v = r.get(date_field, "")
                if v and _parse_date(v) is None:
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {date_field}={v!r} is not a parseable ISO date"))
            for ts_field in rules.get("timestamps", []):
                v = r.get(ts_field, "")
                if v and _parse_ts_strict(v) is None:
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {ts_field}={v!r} is not a timezone-aware ISO-8601 UTC timestamp"))
            for num_field in rules.get("numeric_optional", []):
                v = r.get(num_field, "")
                if v and _parse_float(v) is None:
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {num_field}={v!r} is not a parseable number"))
            for score_field in rules.get("integer_scores_1_5", []):
                v = r.get(score_field, "")
                if not v:
                    continue
                iv = _parse_int_strict(v)
                if iv is None:
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {score_field}={v!r} must be an integer, not a float/string"))
                elif not (SCORE_MIN <= iv <= SCORE_MAX):
                    findings.append(Finding(gate, "FAIL", f"{table}.csv[{rid}]: {score_field}={iv} is outside the allowed range [{SCORE_MIN},{SCORE_MAX}]"))

    # --- Conditional requirements (field required only given another field's value) ---

    for c in fd.claims:
        cid = c.get("claim_id", "<no id>")
        if c.get("value_type") == "numeric" and not (c.get("numeric_value") or "").strip():
            findings.append(Finding(gate, "FAIL", f"claims.csv[{cid}]: value_type=numeric requires a non-blank numeric_value"))
        if c.get("claim_category") == "pre_event_consensus_estimate":
            for req in ("consensus_provider", "consensus_asof_date", "gaap_basis"):
                if not (c.get(req) or "").strip():
                    findings.append(Finding(gate, "FAIL", f"claims.csv[{cid}]: claim_category=pre_event_consensus_estimate requires non-blank {req}"))

    for r in fd.event_labels:
        lid = r.get("label_id", "<no id>")
        if r.get("label_status") == "human_frozen":
            for req in ("frozen_by", "frozen_at_utc", "freeze_manifest_path"):
                if not (r.get(req) or "").strip():
                    findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: label_status=human_frozen requires non-blank {req}"))
        if r.get("amendment_of_label_id") and not (r.get("amendment_reason") or "").strip():
            findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: amendment_of_label_id set but amendment_reason is blank"))

        # Null-surprise reason requirement (2026-08-03, second correction
        # pass): a blank surprise percentage is no longer accepted silently
        # -- it must carry an explicit, enum-controlled reason. Conversely a
        # NON-blank percentage must not also carry a null_reason (contradictory).
        for pct_field, reason_field in (
            ("eps_surprise_pct", "eps_surprise_null_reason"),
            ("revenue_surprise_pct", "revenue_surprise_null_reason"),
        ):
            pct_raw = (r.get(pct_field) or "").strip()
            reason_raw = (r.get(reason_field) or "").strip()
            if not pct_raw and not reason_raw:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {pct_field} is blank but {reason_field} is also blank -- "
                    f"an unexplained null surprise is not allowed, set an explicit reason"))
            if pct_raw and reason_raw:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {pct_field}={pct_raw!r} is set but {reason_field}={reason_raw!r} "
                    f"is also set -- a populated surprise percentage cannot also carry a null-reason"))

        for pct_field, actual_field, consensus_field in (
            ("eps_surprise_pct", "eps_actual_claim_id", "eps_consensus_claim_id"),
            ("revenue_surprise_pct", "revenue_actual_claim_id", "revenue_consensus_claim_id"),
        ):
            if (r.get(pct_field) or "").strip():
                for linkfield in (actual_field, consensus_field):
                    if not (r.get(linkfield) or "").strip():
                        findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: {pct_field} is set but {linkfield} is blank -- a surprise percentage must link to the exact claims it was computed from"))

    return findings


# ---------------------------------------------------------------------------
# Gate 1c: cross-row / cross-table consistency: earnings-date/event-timestamp
# consistency, consensus_asof_date strictly before the earnings event,
# protocol_version consistency.
# ---------------------------------------------------------------------------

def gate_cross_row_consistency(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "cross_row_consistency"

    events_by_id = {r.get("event_id"): r for r in fd.events}

    for r in fd.events:
        eid = r.get("event_id", "<no id>")
        earnings_date = _parse_date(r.get("earnings_date", ""))
        event_dt = _parse_ts_strict(r.get("event_datetime_utc", ""))
        if earnings_date is not None and event_dt is not None:
            if event_dt.date() != earnings_date:
                findings.append(Finding(gate, "FAIL",
                    f"events.csv[{eid}]: earnings_date={earnings_date.isoformat()} does not match the date portion "
                    f"of event_datetime_utc={r.get('event_datetime_utc')!r} ({event_dt.date().isoformat()})"))

    for c in fd.claims:
        if c.get("claim_category") != "pre_event_consensus_estimate":
            continue
        cid = c.get("claim_id", "<no id>")
        asof = _parse_date(c.get("consensus_asof_date", ""))
        ev = events_by_id.get(c.get("event_id"))
        if asof is None or ev is None:
            continue
        earnings_date = _parse_date(ev.get("earnings_date", ""))
        if earnings_date is not None and not (asof < earnings_date):
            findings.append(Finding(gate, "FAIL",
                f"claims.csv[{cid}]: consensus_asof_date={asof.isoformat()} is not strictly before "
                f"events.csv earnings_date={earnings_date.isoformat()} for event {c.get('event_id')!r}"))

    # protocol_version consistency: events.csv <-> event_labels.csv <-> freeze_manifest
    for lr in fd.event_labels:
        lid = lr.get("label_id", "<no id>")
        eid = lr.get("event_id")
        ev = events_by_id.get(eid)
        lbl_pv = lr.get("protocol_version", "")
        if ev is not None and lbl_pv and ev.get("protocol_version") and lbl_pv != ev.get("protocol_version"):
            findings.append(Finding(gate, "FAIL",
                f"event_labels.csv[{lid}]: protocol_version={lbl_pv!r} does not match "
                f"events.csv[{eid}].protocol_version={ev.get('protocol_version')!r}"))
        manifest = fd.freeze_manifests.get(lid)
        if manifest and not manifest.get("__malformed_json__"):
            man_pv = manifest.get("protocol_version", "")
            if lbl_pv and man_pv and man_pv != lbl_pv:
                findings.append(Finding(gate, "FAIL",
                    f"freeze_manifest for {lid}: protocol_version={man_pv!r} does not match "
                    f"event_labels.csv protocol_version={lbl_pv!r}"))

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

    material_categories = {"reported_fact", "management_claim", "pre_event_consensus_estimate", "analyst_interpretation"}

    frozen_event_ids = {r.get("event_id") for r in fd.event_labels if r.get("label_status") == "human_frozen"}

    referenced_by_frozen_label: set[str] = set()
    for r in fd.event_labels:
        if r.get("label_status") != "human_frozen":
            continue
        for fkcol in ("primary_positive_catalyst_claim_id", "primary_negative_catalyst_claim_id",
                      "eps_actual_claim_id", "eps_consensus_claim_id",
                      "revenue_actual_claim_id", "revenue_consensus_claim_id"):
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
            if provider and re.search(r"[,;/]| and | cluster| blended| mixed", provider, re.I):
                findings.append(Finding(gate, "FAIL", f"claims.csv: consensus claim {cid} blends multiple providers into one value: {provider!r}"))

    return findings


# ---------------------------------------------------------------------------
# Gate 2b: surprise-percentage evidence linkage. A surprise percentage must
# link to the EXACT actual and consensus claim IDs it was computed from --
# not merely "any" consensus claim for the event. Both linked claims must be
# value_type=numeric with parseable numeric values, share unit AND GAAP
# basis (neither may be blank), share the SAME metric_name matching the
# field being computed (eps<->eps, revenue<->revenue), and consensus must be
# nonzero. For a human_frozen label, every linkage is additionally validated
# end-to-end and the stored percentage is independently recomputed and
# compared within SURPRISE_PCT_TOLERANCE. Never infers a missing value: a
# null stored percentage is never computed or filled in here (its
# null_reason is checked in gate_field_types instead).
# ---------------------------------------------------------------------------

def gate_surprise_linkage(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "surprise_linkage"

    claims_by_id = {c.get("claim_id"): c for c in fd.claims}
    sources_by_claim: dict[str, list[dict]] = {}
    for s in fd.claim_sources:
        sources_by_claim.setdefault(s.get("claim_id"), []).append(s)

    def _claim_has_direct_source(claim_id: str) -> bool:
        return any(s.get("retrieval_method") == "direct_fetch" and s.get("source_tier") in DIRECT_TIERS
                   for s in sources_by_claim.get(claim_id, []))

    for lr in fd.event_labels:
        lid = lr.get("label_id", "<no id>")
        is_frozen = lr.get("label_status") == "human_frozen"

        for label, pct_field, actual_field, consensus_field, expected_actual_cat, expected_metric in (
            ("EPS", "eps_surprise_pct", "eps_actual_claim_id", "eps_consensus_claim_id",
             {"reported_fact", "management_claim"}, "eps"),
            ("Revenue", "revenue_surprise_pct", "revenue_actual_claim_id", "revenue_consensus_claim_id",
             {"reported_fact", "management_claim"}, "revenue"),
        ):
            pct_raw = (lr.get(pct_field) or "").strip()
            actual_id = (lr.get(actual_field) or "").strip()
            consensus_id = (lr.get(consensus_field) or "").strip()

            if not pct_raw:
                # Null surprise: handled by gate_field_types' null_reason
                # check. Nothing further to validate here, and this
                # function never infers or fills a value.
                continue

            pct = _parse_float(pct_raw)
            if pct is None:
                continue  # already flagged by gate_field_types

            actual_claim = claims_by_id.get(actual_id) if actual_id else None
            consensus_claim = claims_by_id.get(consensus_id) if consensus_id else None

            if actual_id and actual_claim is None:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: {actual_field}={actual_id!r} does not resolve to a real claim"))
            if consensus_id and consensus_claim is None:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: {consensus_field}={consensus_id!r} does not resolve to a real claim"))
            if actual_claim is None or consensus_claim is None:
                continue

            if actual_claim.get("claim_category") not in expected_actual_cat:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} actual claim {actual_id} has claim_category="
                    f"{actual_claim.get('claim_category')!r}, expected one of {sorted(expected_actual_cat)}"))
            if consensus_claim.get("claim_category") != "pre_event_consensus_estimate":
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} consensus claim {consensus_id} has claim_category="
                    f"{consensus_claim.get('claim_category')!r}, expected 'pre_event_consensus_estimate'"))

            # Both claims must be genuinely numeric.
            for role, claim, claim_id in (("actual", actual_claim, actual_id), ("consensus", consensus_claim, consensus_id)):
                if claim.get("value_type") != "numeric":
                    findings.append(Finding(gate, "FAIL",
                        f"event_labels.csv[{lid}]: {label} {role} claim {claim_id} has value_type="
                        f"{claim.get('value_type')!r}, must be 'numeric' to back a surprise percentage"))

            # Both claims must explicitly identify the SAME metric, matching
            # the field being computed (an EPS surprise must link eps<->eps,
            # never eps<->revenue or blank<->eps).
            for role, claim, claim_id in (("actual", actual_claim, actual_id), ("consensus", consensus_claim, consensus_id)):
                mn = claim.get("metric_name", "")
                if mn != expected_metric:
                    findings.append(Finding(gate, "FAIL",
                        f"event_labels.csv[{lid}]: {label} {role} claim {claim_id} has metric_name={mn!r}, "
                        f"expected {expected_metric!r} -- a {label} surprise must link {expected_metric} to {expected_metric}"))

            # Unit and GAAP basis must both exist AND match -- a blank on
            # either side is now a failure, not merely a skipped comparison.
            actual_unit = actual_claim.get("unit", "")
            consensus_unit = consensus_claim.get("unit", "")
            if not actual_unit or not consensus_unit:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} linkage requires a unit on both claims "
                    f"(actual={actual_unit!r}, consensus={consensus_unit!r})"))
            elif actual_unit != consensus_unit:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} actual unit {actual_unit!r} != consensus unit {consensus_unit!r}"))

            actual_gaap = actual_claim.get("gaap_basis", "")
            consensus_gaap = consensus_claim.get("gaap_basis", "")
            if not actual_gaap or not consensus_gaap:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} linkage requires a gaap_basis on both claims "
                    f"(actual={actual_gaap!r}, consensus={consensus_gaap!r})"))
            elif actual_gaap != consensus_gaap:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} actual GAAP basis {actual_gaap!r} != consensus GAAP basis {consensus_gaap!r} "
                    f"-- a surprise percentage must pair actual and consensus on the SAME basis"))

            if is_frozen:
                if not _claim_has_direct_source(actual_id):
                    findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: {label} actual claim {actual_id} backs a human_frozen label but has no direct_fetch (tier 0-3) source"))
                if not _claim_has_direct_source(consensus_id):
                    findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: {label} consensus claim {consensus_id} backs a human_frozen label but has no direct_fetch (tier 0-3) source"))
                provider = consensus_claim.get("consensus_provider", "")
                asof = consensus_claim.get("consensus_asof_date", "")
                if not provider or not asof:
                    findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}]: {label} consensus claim {consensus_id} is missing provider/as-of and cannot back a frozen surprise percentage"))

            actual_val = _parse_float(actual_claim.get("numeric_value", ""))
            consensus_val = _parse_float(consensus_claim.get("numeric_value", ""))
            if actual_val is None:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} actual claim {actual_id}.numeric_value="
                    f"{actual_claim.get('numeric_value')!r} does not parse as a number -- cannot verify the stored surprise percentage"))
            if consensus_val is None:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}]: {label} consensus claim {consensus_id}.numeric_value="
                    f"{consensus_claim.get('numeric_value')!r} does not parse as a number -- cannot verify the stored surprise percentage"))
            if actual_val is not None and consensus_val is not None:
                if consensus_val == 0:
                    findings.append(Finding(gate, "FAIL",
                        f"event_labels.csv[{lid}]: {label} consensus claim {consensus_id} has numeric_value=0 -- "
                        f"a surprise percentage cannot be meaningfully computed against a zero consensus"))
                else:
                    recomputed = (actual_val - consensus_val) / abs(consensus_val) * 100.0
                    if abs(recomputed - pct) > SURPRISE_PCT_TOLERANCE:
                        findings.append(Finding(gate, "FAIL",
                            f"event_labels.csv[{lid}]: stored {pct_field}={pct} does not match recomputed "
                            f"surprise {recomputed:.4f} from claims {actual_id}/{consensus_id} "
                            f"(tolerance={SURPRISE_PCT_TOLERANCE})"))

    return findings


# ---------------------------------------------------------------------------
# Gate 3: blinding (every Layer-A free-text location)
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
        check_text(f"management_qna.csv[{q.get('qna_id')}].classification_basis", q.get("classification_basis", ""))

    for s in fd.claim_sources:
        if s.get("claim_id") not in layer_a_claim_ids:
            continue
        check_text(f"claim_sources.csv[{s.get('claim_source_id')}].source_name", s.get("source_name", ""))
        check_text(f"claim_sources.csv[{s.get('claim_source_id')}].notes", s.get("notes", ""))

    for lr in fd.event_labels:
        lid = lr.get("label_id")
        check_text(f"event_labels.csv[{lid}].notes", lr.get("notes", ""))
        check_text(f"event_labels.csv[{lid}].management_tone", lr.get("management_tone", ""))
        check_text(f"event_labels.csv[{lid}].source_completeness", lr.get("source_completeness", ""))
        check_text(f"event_labels.csv[{lid}].amendment_reason", lr.get("amendment_reason", ""))

    for cc in fd.event_label_capex_effects:
        check_text(f"event_label_capex_effects.csv[{cc.get('capex_effect_id')}].notes", cc.get("notes", ""))

    for ci in fd.event_label_cross_company_implications:
        check_text(f"event_label_cross_company_implications.csv[{ci.get('implication_id')}].notes", ci.get("notes", ""))

    if fd.narrative_text:
        check_text("narrative_text.txt", fd.narrative_text)

    return findings


# ---------------------------------------------------------------------------
# Gate 4: foreign keys and cross-table event/layer consistency. Every FK is
# validated, including corroborates_claim_source_id, capex-effect and
# cross-company-implication evidence claims (now ALSO checked for event/layer
# consistency: the evidence claim must belong to the SAME event as the
# label it supports, and must be Layer A -- a Layer-B claim or a
# wrong-event claim backing a Layer-A child-table row is a validation
# failure), and market-response addendum event consistency (the addendum's
# own event_id must match its linked label's event_id, and every claim in
# post_event_analyst_target_change_claim_ids must belong to that SAME event
# AND be Layer B). No semicolon-delimited ID field is silently trusted --
# controlled/FK-bearing multi-value fields live in normalized child tables;
# any remaining semicolon-delimited value is split and every individual ID
# validated.
# ---------------------------------------------------------------------------

def gate_foreign_keys(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "foreign_keys"

    event_ids = {r.get("event_id") for r in fd.events}
    claim_ids = {r.get("claim_id") for r in fd.claims}
    label_ids = {r.get("label_id") for r in fd.event_labels}
    claim_source_ids = {s.get("claim_source_id") for s in fd.claim_sources}
    claims_by_id = {c.get("claim_id"): c for c in fd.claims}
    labels_by_id = {r.get("label_id"): r for r in fd.event_labels}

    def _fk(table: str, row_id: str, field_name: str, value: str, target_set: set, target_table_present: bool) -> None:
        if value and target_table_present and value not in target_set:
            findings.append(Finding(gate, "FAIL", f"{table}.csv[{row_id}].{field_name} references unknown id {value!r}"))

    for r in fd.event_labels:
        lid = r.get("label_id", "<no id>")
        _fk("event_labels", lid, "event_id", r.get("event_id", ""), event_ids, bool(fd.events))
        for fkcol in ("primary_positive_catalyst_claim_id", "primary_negative_catalyst_claim_id",
                      "eps_actual_claim_id", "eps_consensus_claim_id",
                      "revenue_actual_claim_id", "revenue_consensus_claim_id"):
            _fk("event_labels", lid, fkcol, r.get(fkcol, ""), claim_ids, bool(fd.claims))
        amend_of = r.get("amendment_of_label_id", "")
        if amend_of:
            if amend_of == lid:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}] cannot amend itself"))
            elif fd.event_labels and amend_of not in label_ids:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv[{lid}].amendment_of_label_id references unknown label_id {amend_of!r}"))
        # claim/event consistency: every linked claim must belong to THIS label's event
        eid = r.get("event_id", "")
        for fkcol in ("primary_positive_catalyst_claim_id", "primary_negative_catalyst_claim_id",
                      "eps_actual_claim_id", "eps_consensus_claim_id",
                      "revenue_actual_claim_id", "revenue_consensus_claim_id"):
            v = r.get(fkcol, "")
            claim = claims_by_id.get(v)
            if claim is not None and eid and claim.get("event_id") != eid:
                findings.append(Finding(gate, "FAIL",
                    f"event_labels.csv[{lid}].{fkcol}={v!r} belongs to event {claim.get('event_id')!r}, "
                    f"not this label's event {eid!r} -- claim/event consistency violated"))

    for c in fd.claims:
        cid = c.get("claim_id", "<no id>")
        _fk("claims", cid, "event_id", c.get("event_id", ""), event_ids, bool(fd.events))

    for s in fd.claim_sources:
        csid = s.get("claim_source_id", "<no id>")
        _fk("claim_sources", csid, "claim_id", s.get("claim_id", ""), claim_ids, bool(fd.claims))
        corrob = s.get("corroborates_claim_source_id", "")
        if corrob:
            if corrob == csid:
                findings.append(Finding(gate, "FAIL", f"claim_sources.csv[{csid}].corroborates_claim_source_id cannot reference itself"))
            elif fd.claim_sources and corrob not in claim_source_ids:
                findings.append(Finding(gate, "FAIL", f"claim_sources.csv[{csid}].corroborates_claim_source_id references unknown claim_source_id {corrob!r}"))
            else:
                target = next((x for x in fd.claim_sources if x.get("claim_source_id") == corrob), None)
                if target is not None and target.get("claim_id") != s.get("claim_id"):
                    findings.append(Finding(gate, "FAIL",
                        f"claim_sources.csv[{csid}].corroborates_claim_source_id={corrob!r} belongs to a different "
                        f"claim ({target.get('claim_id')!r} vs {s.get('claim_id')!r}) -- a source can only corroborate "
                        f"another source of the SAME claim"))

    for q in fd.management_qna:
        qid = q.get("qna_id", "<no id>")
        _fk("management_qna", qid, "event_id", q.get("event_id", ""), event_ids, bool(fd.events))

    for cc in fd.event_label_capex_effects:
        ceid = cc.get("capex_effect_id", "<no id>")
        _fk("event_label_capex_effects", ceid, "label_id", cc.get("label_id", ""), label_ids, bool(fd.event_labels))
        _fk("event_label_capex_effects", ceid, "evidence_claim_id", cc.get("evidence_claim_id", ""), claim_ids, bool(fd.claims))
        label = labels_by_id.get(cc.get("label_id"))
        claim = claims_by_id.get(cc.get("evidence_claim_id"))
        if label is not None and claim is not None:
            if claim.get("event_id") != label.get("event_id"):
                findings.append(Finding(gate, "FAIL",
                    f"event_label_capex_effects.csv[{ceid}].evidence_claim_id={cc.get('evidence_claim_id')!r} belongs to "
                    f"event {claim.get('event_id')!r}, not label {cc.get('label_id')!r}'s event {label.get('event_id')!r}"))
            if claim.get("layer") != "A_blinded_core":
                findings.append(Finding(gate, "FAIL",
                    f"event_label_capex_effects.csv[{ceid}].evidence_claim_id={cc.get('evidence_claim_id')!r} has layer="
                    f"{claim.get('layer')!r}, must be 'A_blinded_core' -- Layer-A child rows cannot cite Layer-B evidence"))
            if claim.get("claim_category") not in CHILD_TABLE_EVIDENCE_CLAIM_CATEGORIES:
                findings.append(Finding(gate, "FAIL",
                    f"event_label_capex_effects.csv[{ceid}].evidence_claim_id={cc.get('evidence_claim_id')!r} has claim_category="
                    f"{claim.get('claim_category')!r}, expected one of {sorted(CHILD_TABLE_EVIDENCE_CLAIM_CATEGORIES)}"))

    for ci in fd.event_label_cross_company_implications:
        ciid = ci.get("implication_id", "<no id>")
        _fk("event_label_cross_company_implications", ciid, "label_id", ci.get("label_id", ""), label_ids, bool(fd.event_labels))
        _fk("event_label_cross_company_implications", ciid, "claim_id", ci.get("claim_id", ""), claim_ids, bool(fd.claims))
        label = labels_by_id.get(ci.get("label_id"))
        claim = claims_by_id.get(ci.get("claim_id"))
        if label is not None and claim is not None:
            if claim.get("event_id") != label.get("event_id"):
                findings.append(Finding(gate, "FAIL",
                    f"event_label_cross_company_implications.csv[{ciid}].claim_id={ci.get('claim_id')!r} belongs to "
                    f"event {claim.get('event_id')!r}, not label {ci.get('label_id')!r}'s event {label.get('event_id')!r}"))
            if claim.get("layer") != "A_blinded_core":
                findings.append(Finding(gate, "FAIL",
                    f"event_label_cross_company_implications.csv[{ciid}].claim_id={ci.get('claim_id')!r} has layer="
                    f"{claim.get('layer')!r}, must be 'A_blinded_core' -- Layer-A child rows cannot cite Layer-B evidence"))
            if claim.get("claim_category") not in CHILD_TABLE_EVIDENCE_CLAIM_CATEGORIES:
                findings.append(Finding(gate, "FAIL",
                    f"event_label_cross_company_implications.csv[{ciid}].claim_id={ci.get('claim_id')!r} has claim_category="
                    f"{claim.get('claim_category')!r}, expected one of {sorted(CHILD_TABLE_EVIDENCE_CLAIM_CATEGORIES)}"))
            if not claim.get("metric_name"):
                findings.append(Finding(gate, "FAIL",
                    f"event_label_cross_company_implications.csv[{ciid}].claim_id={ci.get('claim_id')!r} has no "
                    f"metric_name -- a cross-company implication claim must carry an explicit metric classification"))

    for r in fd.market_response_addendum:
        aid = r.get("addendum_id", "<no id>")
        _fk("market_response_addendum", aid, "event_id", r.get("event_id", ""), event_ids, bool(fd.events))
        _fk("market_response_addendum", aid, "linked_label_id", r.get("linked_label_id", ""), label_ids, bool(fd.event_labels))
        label = labels_by_id.get(r.get("linked_label_id"))
        if label is not None and r.get("event_id") and label.get("event_id") and r.get("event_id") != label.get("event_id"):
            findings.append(Finding(gate, "FAIL",
                f"market_response_addendum.csv[{aid}]: event_id={r.get('event_id')!r} does not match linked_label_id "
                f"{r.get('linked_label_id')!r}'s own event {label.get('event_id')!r}"))
        target_ids_raw = r.get("post_event_analyst_target_change_claim_ids", "")
        for individual_id in _split_semicolon_ids(target_ids_raw):
            if fd.claims and individual_id not in claim_ids:
                findings.append(Finding(gate, "FAIL", f"market_response_addendum.csv[{aid}].post_event_analyst_target_change_claim_ids contains unknown claim_id {individual_id!r}"))
                continue
            claim = claims_by_id.get(individual_id)
            if claim is None:
                continue
            if r.get("event_id") and claim.get("event_id") != r.get("event_id"):
                findings.append(Finding(gate, "FAIL",
                    f"market_response_addendum.csv[{aid}].post_event_analyst_target_change_claim_ids references "
                    f"{individual_id!r} from event {claim.get('event_id')!r}, not this addendum's event {r.get('event_id')!r}"))
            if claim.get("layer") != "B_market_response":
                findings.append(Finding(gate, "FAIL",
                    f"market_response_addendum.csv[{aid}].post_event_analyst_target_change_claim_ids references "
                    f"{individual_id!r} with layer={claim.get('layer')!r}, must be 'B_market_response'"))

    return findings


# ---------------------------------------------------------------------------
# Gate 5: label integrity (non-manifest parts: frozen_by human, disposition
# history one-directional rule)
# ---------------------------------------------------------------------------

def gate_label_integrity(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "label_integrity"

    for r in fd.event_labels:
        lid = r.get("label_id", "")
        status = r.get("label_status", "")
        if status == "human_frozen":
            frozen_by = r.get("frozen_by", "")
            if not frozen_by or frozen_by.strip().lower() in {"ai", "ai_proposed", "system", ""}:
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} is human_frozen but frozen_by is missing/non-human ({frozen_by!r})"))
        elif status in {"draft", "ai_proposed"}:
            if r.get("frozen_by") or r.get("frozen_at_utc"):
                findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} has status={status} but carries frozen_by/frozen_at_utc -- labels must stay AI_PROPOSED until genuinely reviewed"))

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
                findings.append(Finding(gate, "FAIL", f"disposition_history.csv: event {eid} moved back to confirmatory after being development_pilot/compromised -- one-directional rule violated"))

    return findings


# ---------------------------------------------------------------------------
# Gate 6: freeze manifest / immutable freeze bundle. Structural validation
# (required fields, additionalProperties, enums, patterns -- INCLUDING nested
# array items like reveal_events[]/reviewer_capture_exposure_log[]) is now
# delegated to the actual freeze_manifest.schema.json via the pinned
# `jsonschema` library (see requirements.txt), rather than a hand-rolled
# top-level-only required/additionalProperties check that silently ignored
# violations nested inside array items.
#
# Every referenced artifact must live under frozen/{event_id}/{label_id}/ --
# an immutable, label-version-scoped bundle -- and containment is checked
# with Path.is_relative_to() against that bundle's resolved real path (never
# a string-prefix comparison, which a directory named e.g.
# "frozen/EVT-X/LBL-01_evil/" would defeat). .resolve() follows symlinks, so
# a symlink planted inside the bundle that points outside it is caught by the
# same containment check. All seven required artifact basenames
# (FROZEN_BUNDLE_REQUIRED_BASENAMES) must appear exactly once; no Layer-B/C
# path may be referenced; hashes are recomputed against the frozen copies
# (never the mutable working tables); and the manifest's own filename must
# match event_labels.csv's declared freeze_manifest_path exactly, in
# addition to the existing event_id/frozen_by/freeze-timestamp cross-checks.
# ---------------------------------------------------------------------------

def _load_manifest_schema() -> dict:
    with FREEZE_MANIFEST_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def gate_freeze_manifest(fd: FixtureData, fixture_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    gate = "freeze_manifest"

    if not _HAVE_JSONSCHEMA:
        findings.append(Finding(gate, "FAIL",
            "the 'jsonschema' package (pinned in validator/requirements.txt) is not installed -- "
            "freeze-manifest structural validation cannot run. Install it before validating any "
            "fixture containing a freeze_manifest*.json."))
        return findings

    schema = _load_manifest_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    schema_validator = validator_cls(schema, format_checker=FormatChecker())

    labels_by_id = {r.get("label_id"): r for r in fd.event_labels}

    for label_id, manifest in fd.freeze_manifests.items():
        manifest_file = fd.freeze_manifest_files.get(label_id, "freeze_manifest.json")
        if manifest.get("__malformed_json__"):
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: malformed JSON, could not parse"))
            continue

        schema_errors = sorted(schema_validator.iter_errors(manifest), key=lambda e: list(e.absolute_path))
        for err in schema_errors:
            loc = "$" + "".join(f"[{p!r}]" if isinstance(p, str) else f"[{p}]" for p in err.absolute_path)
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: JSON Schema violation at {loc}: {err.message}"))
        if schema_errors:
            # Structural violations make artifact-level inspection below
            # unreliable (e.g. layer_a_artifact_hashes might not even be a
            # list) -- still attempt best-effort semantic checks using
            # .get() defaults, but don't let a missing/malformed field raise.
            pass

        event_id = manifest.get("event_id", "")
        fixture_root = fixture_dir.resolve()
        bundle_root = (fixture_dir / "frozen" / event_id / label_id).resolve()

        artifact_entries = manifest.get("layer_a_artifact_hashes", [])
        if not isinstance(artifact_entries, list):
            artifact_entries = []
        seen_paths: dict[str, int] = {}
        seen_basenames: dict[str, int] = {}
        for entry in artifact_entries:
            if not isinstance(entry, dict) or "artifact_path" not in entry or "sha256" not in entry:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: malformed layer_a_artifact_hashes entry {entry!r} (missing artifact_path/sha256)"))
                continue
            artifact_path = entry["artifact_path"]
            recorded_hash = entry["sha256"]
            seen_paths[artifact_path] = seen_paths.get(artifact_path, 0) + 1
            seen_basenames[Path(artifact_path).name] = seen_basenames.get(Path(artifact_path).name, 0) + 1

            if not re.match(r"^[a-f0-9]{64}$", recorded_hash or ""):
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: malformed sha256 for {artifact_path!r}"))
                continue

            candidate = (fixture_dir / artifact_path)
            try:
                resolved = candidate.resolve()
            except (OSError, ValueError):
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: artifact_path {artifact_path!r} could not be resolved"))
                continue

            # Component-aware containment (Path.is_relative_to), not a
            # string-prefix check -- and specifically scoped to THIS label's
            # immutable bundle directory, not merely "somewhere in the
            # fixture". .resolve() already follows symlinks, so a symlink
            # planted inside the bundle pointing outside it is caught here
            # too: its resolved (real) target simply won't be relative_to
            # bundle_root.
            if Path(artifact_path).is_absolute() or ".." in Path(artifact_path).parts:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: artifact_path {artifact_path!r} escapes the frozen bundle directory (path traversal)"))
                continue
            if not resolved.is_relative_to(bundle_root):
                findings.append(Finding(gate, "FAIL",
                    f"{manifest_file}: artifact_path {artifact_path!r} resolves to {resolved}, which is outside "
                    f"this label's immutable bundle directory {bundle_root} (path/symlink escape)"))
                continue

            if any(marker in artifact_path for marker in FORBIDDEN_MANIFEST_PATH_MARKERS):
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: artifact_path {artifact_path!r} references a Layer-B/C location -- forbidden in a Layer-A freeze bundle"))

            if not (resolved.exists() and resolved.is_file()):
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: referenced artifact {artifact_path!r} does not exist in this label's frozen bundle"))
                continue

            actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if actual_hash != recorded_hash:
                findings.append(Finding(gate, "FAIL",
                    f"{manifest_file}: recorded sha256 for {artifact_path!r} ({recorded_hash}) does not match "
                    f"the artifact's actual current hash ({actual_hash}) -- frozen bundle content changed after freeze"))

        for path, count in seen_paths.items():
            if count > 1:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: duplicate artifact_path entry {path!r} ({count} times)"))

        missing_required_artifacts = FROZEN_BUNDLE_REQUIRED_BASENAMES - set(seen_basenames.keys())
        if missing_required_artifacts:
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: missing required frozen-bundle artifact(s) from inventory: {sorted(missing_required_artifacts)}"))
        for basename in FROZEN_BUNDLE_REQUIRED_BASENAMES:
            if seen_basenames.get(basename, 0) > 1:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: required frozen-bundle artifact {basename!r} appears {seen_basenames[basename]} times, must appear exactly once"))

        if not artifact_entries:
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: layer_a_artifact_hashes is empty"))

        freeze_ts = manifest.get("freeze_timestamp_utc", "")
        if not freeze_ts or _parse_ts_strict(freeze_ts) is None:
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: freeze_timestamp_utc missing/not a timezone-aware timestamp"))

        # Manifest <-> event_labels.csv cross-consistency
        label_row = labels_by_id.get(label_id)
        if label_row is not None:
            declared_path = label_row.get("freeze_manifest_path", "")
            if declared_path and Path(declared_path).name != manifest_file:
                findings.append(Finding(gate, "FAIL",
                    f"{manifest_file}: this manifest's own filename does not match event_labels.csv "
                    f"freeze_manifest_path={declared_path!r} (expected filename {Path(declared_path).name!r}) for {label_id}"))
            if label_row.get("event_id") and manifest.get("event_id") and label_row.get("event_id") != manifest.get("event_id"):
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: manifest event_id={manifest.get('event_id')!r} != event_labels.csv event_id={label_row.get('event_id')!r} for {label_id}"))
            if label_row.get("frozen_by") and manifest.get("frozen_by") and label_row.get("frozen_by") != manifest.get("frozen_by"):
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: manifest frozen_by={manifest.get('frozen_by')!r} != event_labels.csv frozen_by={label_row.get('frozen_by')!r} for {label_id}"))
            if label_row.get("frozen_at_utc") and freeze_ts and label_row.get("frozen_at_utc") != freeze_ts:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: manifest freeze_timestamp_utc={freeze_ts!r} != event_labels.csv frozen_at_utc={label_row.get('frozen_at_utc')!r} for {label_id}"))
        elif fd.event_labels:
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: label_id {label_id!r} has no matching row in event_labels.csv"))

    # The reverse direction: a human_frozen label must have a matching manifest.
    for r in fd.event_labels:
        lid = r.get("label_id", "")
        if r.get("label_status") != "human_frozen":
            continue
        manifest_path = r.get("freeze_manifest_path", "")
        manifest = fd.freeze_manifests.get(lid) or fd.freeze_manifests.get(manifest_path)
        if manifest is None:
            findings.append(Finding(gate, "FAIL", f"event_labels.csv: {lid} is human_frozen but no matching freeze_manifest*.json was found"))

    return findings


# ---------------------------------------------------------------------------
# Gate 7: layer separation (STRICT reveal > freeze; equal timestamps fail as
# ambiguous; naive/mixed-tz values fail closed via _parse_ts_strict rather
# than raising a comparison exception)
# ---------------------------------------------------------------------------

def gate_layer_separation(fd: FixtureData) -> list[Finding]:
    findings: list[Finding] = []
    gate = "layer_separation"

    label_by_id = {r.get("label_id"): r for r in fd.event_labels}

    for label_id, manifest in fd.freeze_manifests.items():
        if manifest.get("__malformed_json__"):
            continue
        manifest_file = fd.freeze_manifest_files.get(label_id, "freeze_manifest.json")
        freeze_ts_raw = manifest.get("freeze_timestamp_utc", "")
        freeze_ts = _parse_ts_strict(freeze_ts_raw)
        frozen_by = manifest.get("frozen_by", "")

        if freeze_ts_raw and freeze_ts is None:
            findings.append(Finding(gate, "FAIL", f"{manifest_file}: freeze_timestamp_utc={freeze_ts_raw!r} is naive or otherwise not a valid timezone-aware timestamp"))

        for reveal in manifest.get("reveal_events", []):
            revealed_at_raw = reveal.get("revealed_at_utc", "")
            revealed_at = _parse_ts_strict(revealed_at_raw)
            if revealed_at_raw and revealed_at is None:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: reveal_events[].revealed_at_utc={revealed_at_raw!r} is naive or otherwise not a valid timezone-aware timestamp -- cannot verify ordering, failing closed"))
                continue
            if freeze_ts is not None and revealed_at is not None:
                if revealed_at < freeze_ts:
                    findings.append(Finding(gate, "FAIL",
                        f"{manifest_file}: {reveal.get('layer')} revealed_at_utc={revealed_at_raw} predates "
                        f"freeze_timestamp_utc={freeze_ts_raw}"))
                elif revealed_at == freeze_ts:
                    findings.append(Finding(gate, "FAIL",
                        f"{manifest_file}: {reveal.get('layer')} revealed_at_utc={revealed_at_raw} EQUALS "
                        f"freeze_timestamp_utc={freeze_ts_raw} -- ambiguous ordering is not allowed, reveal must be strictly later"))

        for exposure in manifest.get("reviewer_capture_exposure_log", []):
            exposure_ts_raw = exposure.get("exposure_timestamp_utc", "")
            exposure_ts = _parse_ts_strict(exposure_ts_raw)
            if exposure_ts_raw and exposure_ts is None:
                findings.append(Finding(gate, "FAIL", f"{manifest_file}: reviewer_capture_exposure_log[].exposure_timestamp_utc={exposure_ts_raw!r} is naive or otherwise invalid -- failing closed"))
                continue
            if (
                freeze_ts is not None
                and exposure_ts is not None
                and exposure_ts <= freeze_ts
                and exposure.get("reviewer_id") == frozen_by
            ):
                findings.append(Finding(
                    gate, "FAIL",
                    f"{manifest_file}: reviewer {frozen_by!r} was exposed to {exposure.get('layer')} at "
                    f"{exposure_ts_raw}, at or before freeze at {freeze_ts_raw} -- "
                    f"this reviewer is disqualified from signing this label",
                ))

    for r in fd.market_response_addendum:
        lid = r.get("linked_label_id", "")
        if lid and label_by_id and lid not in label_by_id:
            findings.append(Finding(gate, "FAIL", f"market_response_addendum.csv: {r.get('addendum_id')} references unknown linked_label_id {lid!r}"))

    return findings


GATE_FUNCS = [
    ("required_tables", lambda fd, fx, uni, mode: gate_required_tables(fd, mode)),
    ("identity_and_schema", lambda fd, fx, uni, mode: gate_identity_and_schema(fd, uni)),
    ("field_types", lambda fd, fx, uni, mode: gate_field_types(fd)),
    ("cross_row_consistency", lambda fd, fx, uni, mode: gate_cross_row_consistency(fd)),
    ("source_integrity", lambda fd, fx, uni, mode: gate_source_integrity(fd)),
    ("surprise_linkage", lambda fd, fx, uni, mode: gate_surprise_linkage(fd)),
    ("blinding", lambda fd, fx, uni, mode: gate_blinding(fd)),
    ("foreign_keys", lambda fd, fx, uni, mode: gate_foreign_keys(fd)),
    ("label_integrity", lambda fd, fx, uni, mode: gate_label_integrity(fd)),
    ("freeze_manifest", lambda fd, fx, uni, mode: gate_freeze_manifest(fd, fx)),
    ("layer_separation", lambda fd, fx, uni, mode: gate_layer_separation(fd)),
]


def validate(fixture_dir: Path, mode: str = "freeze") -> tuple[bool, list[Finding]]:
    if mode not in VALIDATION_MODES:
        raise ValueError(f"mode must be one of {sorted(VALIDATION_MODES)}, got {mode!r}")
    fd = load_fixture(fixture_dir)
    universe = load_locked_universe()
    findings: list[Finding] = []
    for _name, fn in GATE_FUNCS:
        findings.extend(fn(fd, fixture_dir, universe, mode))
    ok = not any(f.severity == "FAIL" for f in findings)
    return ok, findings


def main(argv: list[str]) -> int:
    mode = "freeze"
    args = list(argv)
    if args and args[0] == "--mode":
        if len(args) < 2 or args[1] not in VALIDATION_MODES:
            print(f"usage: --mode must be one of {sorted(VALIDATION_MODES)}", file=sys.stderr)
            return 2
        mode = args[1]
        args = args[2:]
    if not args:
        print("usage: validate_event_dossier.py [--mode draft|proposed|freeze] <fixture_dir> [<fixture_dir> ...]", file=sys.stderr)
        return 2
    overall_ok = True
    for arg in args:
        fixture_dir = Path(arg)
        ok, findings = validate(fixture_dir, mode=mode)
        status = "PASS" if ok else "FAIL"
        print(f"=== {fixture_dir.name} (mode={mode}): {status} ===")
        for f in findings:
            print(f"  {f}")
        if not findings:
            print("  (no findings)")
        overall_ok = overall_ok and ok
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
