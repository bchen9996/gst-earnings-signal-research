#!/usr/bin/env python3
"""Semiconductor EPS-Price Absorption: strict GAAP diluted-EPS parser + study runner.

EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY. Uses NO Google Trends, analyst estimates,
options, social media, news or paid data. Modifies no prior result, GST artifact, lock,
registry, protocol or production constant.

QUESTION. Does a mismatch between standardized unexpected GAAP diluted EPS and the
market's first full-session reaction predict subsequent semiconductor-stock drift?

CONSTRUCT GUARD. SUE here is a SEASONAL HISTORICAL-EXPECTATION surprise built only from
the company's own previously announced GAAP diluted EPS. It is NOT an analyst surprise,
consensus miss, fair value, mispricing, or proof of underreaction. eps_price_gap is a
RELATIVE MISMATCH PROXY between two standardized quantities, nothing more.

=============================== FROZEN_DESIGN ===============================
Frozen and committed BEFORE any post-entry target return was computed.

SECTOR        SEMICONDUCTORS
UNIVERSE      NVDA, AMD, INTC, QCOM, AVGO, MU, TXN, AMAT, LRCX, KLAC (frozen order,
              fixed before outcomes; coherent semiconductor and semiconductor-equipment
              sector with sufficient filing history)
BENCHMARK     SMH. An event without SMH coverage is DROPPED. SPY is never the primary
              benchmark; SPY-adjusted returns are a prespecified sensitivity only.
PERIOD        8-K events 2018-01-01 .. 2025-12-31 (early years supply SUE history)
EVENT ID      (ticker, fiscal_period_end, accession_number); duplicate identities are
              REFUSED outright - never silently keep the first

EXTRACTION    Exhibit 99.1 (or equivalent earnings-release exhibit) only.
  STRUCTURAL, not broad keyword matching across the filing:
   1 build a colspan-expanded cell grid per HTML table
   2 accept a table only if it is a CONSOLIDATED STATEMENT OF INCOME/OPERATIONS:
       it must contain a revenue row AND a net-income row AND a per-share row
   3 reject a table whose caption/preceding text or header marks it as a
       reconciliation, non-GAAP, adjusted, pro forma, segment, supplemental,
       guidance or outlook table
   4 identify the CURRENT THREE-MONTH quarter column from spanning header text;
     reject YTD / six / nine / twelve-month / full-year columns
   5 among surviving quarter columns take the one with the LATEST period-end date;
     that date becomes fiscal_period_end
   6 select the row structurally corresponding to diluted net income/loss per share
   7 parentheses and leading minus signs are negative values
   8 REFUSE when two accepted candidates disagree (ambiguous multiple match)
  NEVER extracted: adjusted / non-GAAP / pro forma EPS; basic EPS; continuing-operations
  EPS when a consolidated GAAP diluted EPS is also present; six-month, nine-month, YTD
  or annual EPS; guidance; the later 10-Q value as the event-time feature.

DEV SAMPLE    exactly 2 events per ticker where available, ascending SHA-256 of
              "SEMICONDUCTOR_EPS_PARSER_DEV|ticker|fiscal_period_end|accession".
              Parser development and debugging happen ONLY on that fixed sample and
              NEVER inspect a post-entry return.

AUDIT REF     subsequently filed 10-Q XBRL us-gaap:EarningsPerShareDiluted (documented
              equivalents only when the primary concept is absent). It must match the
              same fiscal quarter, be a ~three-month duration, be consolidated and
              dimensionless, and be ACCEPTED AFTER the earnings release. It can never
              select, replace or alter an Exhibit value and never enters a feature.
              Tolerance |exhibit - reference| <= $0.01. later_xbrl_used_for_prediction=False

EXTRACTION GATES (all evaluated BEFORE any return is inspected)
  reference_coverage    = (validated + contradicted) / extracted        >= 0.80
  conditional_precision = validated / (validated + contradicted)        >= 0.95
  usable_event_coverage = usable events / located earnings exhibits     >= 0.60
  tickers >= 8; usable events >= 160; OOS events >= 90; >= 25 OOS in each of
  2023, 2024, 2025; zero later-XBRL values used as predictive inputs.
  Any failure -> EXTRACTION_NOT_RELIABLE. Gates are never loosened afterwards and no
  value is ever hand-corrected after seeing aggregate validation rates.

SUE           SUE(i,q) = (EPS(i,q) - EPS(i,q-4)) / sigma_i(seasonal EPS differences)
              Exhibit-extracted GAAP diluted EPS ONLY. The denominator uses ONLY
              seasonal differences from releases occurring BEFORE the current event:
              up to the previous 8 observable differences, at least 4 required,
              otherwise the event is unavailable. Winsorized at the TRAINING-FOLD
              1st/99th percentiles only.

TIMING        SEC acceptance timestamp in US/Eastern:
                < 09:30 ET on a trading day  -> that day is the reaction session
                during market hours          -> next trading day
                >= 16:00 ET                  -> next trading day
                weekend / holiday            -> next trading day
              Features become available only AFTER the reaction session closes.
              entry   = following trading day's OPEN
              exit-1  = 5th trading day's CLOSE after entry   (primary)
              exit-2  = 20th trading day's CLOSE after entry  (secondary)

TARGETS       stock return minus SMH return over the identical window (primary).
              SPY-adjusted return is a sensitivity only.

MARKET FEATURES (all known strictly before entry; no target-period value may enter)
  reaction_abn_ret   reaction-session open->close return minus SMH open->close
  reaction_abn_vol   reaction-session volume / mean volume of the prior 20 sessions
  prior20_abn_ret    prior 20-session close-to-close return minus SMH
  prior20_vol        prior 20-session realized volatility

EPS-PRICE GAP  standardized WITHIN EACH OUTER TRAINING FOLD ONLY:
  eps_price_gap = z(SUE) - z(reaction_abn_ret)
  positive: EPS surprise high relative to the initial reaction
  negative: EPS surprise low relative to the initial reaction
  A relative mismatch proxy - not fair value, mispricing or proven underreaction.

MODELS        one ridge regression for both.
  B (market-only): reaction_abn_ret, reaction_abn_vol, prior20_abn_ret, prior20_vol,
                   ticker indicators
  C (EPS absorption): every B feature + eps_price_gap + eps_price_gap*abs(z_reaction)
  alpha grid [0.1, 1.0, 10.0, 100.0], chosen by INNER CHRONOLOGICAL validation inside
  each outer training fold. Never in-sample fit, never the outer test fold.
  Nothing else may be added after outcomes are seen.

FOLDS         train<=2022 test 2023 | train<=2023 test 2024 | train<=2024 test 2025
              Never a random split.

METRICS       primary target 5-session SMH-adjusted abnormal return; primary metric
              pooled OOS MAE of B vs C. Also RMSE, OOS R2, pooled Spearman IC, IC by
              year, MAE by year, gap coefficient sign and fold stability.
BOOTSTRAP     fixed-seed calendar-time block bootstrap, 2000 draws, 4-week blocks, all
              events inside a sampled block retained.

PREDICTIVE GATE (five-day target; all five required)
  1 pooled OOS MAE improves by >= 1%
  2 bootstrap 95% interval for loss_B - loss_C entirely above zero
  3 C beats B in >= 2 of 3 years
  4 pooled Spearman IC > 0.03
  5 IC positive in >= 2 of 3 years
Twenty-day and SPY results are secondary and cannot override this gate.

TRADING TEST  run ONLY if the predictive gate passes. Per outer fold: threshold =
  TRAINING-fold 80th percentile of |Model C prediction|; trade only test events above
  it; long positive, short negative; enter at the prescribed next-session open; exit at
  the 5th-session close; subtract 20 bps round trip. Passes only if >= 30 OOS trades,
  positive mean net return, bootstrap 95% interval entirely above zero, and positive
  net return in >= 2 of 3 years.

LABELS        exactly one of EXTRACTION_NOT_RELIABLE | DATA_UNAVAILABLE |
  NO_SEMICONDUCTOR_EPS_ABSORPTION_EDGE | PREDICTIVE_NOT_TRADABLE |
  SEMICONDUCTOR_EPS_ABSORPTION_SIGNAL
============================= END FROZEN_DESIGN =============================
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Live Signal Engine" / "Semiconductor_EPS_Absorption"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / "_cache"
CACHE.mkdir(parents=True, exist_ok=True)
# read-only reuse of an existing SEC response cache (raw HTTP bodies only)
FALLBACK = Path(r"C:\Users\hakur\Downloads\gst-v2-worktree\Live Signal Engine"
                r"\PIT_Earnings_Surprise_v2\_cache")

SECTOR = "SEMICONDUCTORS"
UNIVERSE = ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "TXN", "AMAT", "LRCX", "KLAC"]
BENCH, BENCH2 = "SMH", "SPY"
DEV_SEED = "SEMICONDUCTOR_EPS_PARSER_DEV"
DEV_PER_TICKER = 2
EPS_TOL = 0.01
SUE_MIN_HIST, SUE_MAX_HIST = 4, 8
ALPHAS = [0.1, 1.0, 10.0, 100.0]
FOLDS = [(2022, 2023), (2023, 2024), (2024, 2025)]
COST_BPS = 20.0
BOOT_DRAWS, BOOT_BLOCK_WEEKS, BOOT_SEED = 2000, 4, 20260817
EGATE = {"reference_coverage": 0.80, "conditional_precision": 0.95,
         "usable_event_coverage": 0.60, "tickers": 8, "events": 160, "oos": 90,
         "oos_per_year": 25}
PGATE = {"mae_improvement": 0.01, "years_better": 2, "ic": 0.03, "ic_years": 2}
TGATE = {"trades": 30, "years_positive": 2}

UA = {"User-Agent": "gst-earnings-signal-research academic research (hakurati11@gmail.com)"}
UA_MKT = {"User-Agent": "Mozilla/5.0"}


def get(url, hdr, key, timeout=60):
    f = CACHE / key
    if f.exists():
        return f.read_bytes()
    g = FALLBACK / key
    if g.exists():
        return g.read_bytes()
    b = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=timeout).read()
    f.write_bytes(b)
    time.sleep(0.11)
    return b


# ============================ structural EPS parser ============================
MONEY = re.compile(r"^\(?\s*[-\u2212]?\s*\$?\s*[\d,]+(?:\.\d+)?\s*\)?$")
DATE_PATS = [
    # NOTE: several filers write "June 29,2024" with no space after the comma, so the
    # separator must be \s* and not \s+.
    (re.compile(r"(?i)\b(january|february|march|april|may|june|july|august|september|"
                r"october|november|december)\s*(\d{1,2})\s*,?\s*(\d{4})"), "mdy"),
    (re.compile(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s*"
                r"(\d{1,2})\s*,?\s*(\d{4})"), "mdy"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"), "slash"),
]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
MONTHS.update({m[:3]: i + 1 for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9

NON_GAAP_CTX = re.compile(
    r"(?i)(reconcil|non[- ]?gaap|adjusted|pro\s*forma|supplement|segment|guidance|outlook|"
    r"business unit|by geograph|forward[- ]looking financial)")
YTD = re.compile(r"(?i)(six|nine|twelve|year[- ]to[- ]date|\bytd\b|first half|full year|"
                 r"twenty[- ]six|thirty[- ]nine|fifty[- ]two|fifty[- ]three)\s*(months|weeks)?")
QTR_SPAN = re.compile(r"(?i)(three months|three-month|quarter|thirteen weeks|13 weeks|"
                      r"fourteen weeks|14 weeks|q[1-4]\b)")
REV_ROW = re.compile(r"(?i)^(total\s+)?(net\s+)?(revenue|revenues|net revenue|net revenues|"
                     r"net sales|sales|total revenue|total revenues|total net sales)\b")
NI_ROW = re.compile(r"(?i)^(net\s+(income|loss|earnings)|net income \(loss\)|"
                    r"net earnings \(loss\)|net income \(loss\) attributable)")
PERSHARE_CTX = re.compile(r"(?i)per\s+(\w+\s+){0,2}shares?\b|per-share|\beps\b")
DILUTED_FULL = re.compile(r"(?i)dilut\w*.{0,60}per\s+(common\s+)?share|"
                          r"(earnings|income|loss|net income|net loss)\b.{0,40}per.{0,25}"
                          r"(common\s+)?share.{0,25}dilut")
DILUTED_BARE = re.compile(r"(?i)^\s*[-\u2022]?\s*dilut(ed|ive)?\s*[:\.]?\s*$")
CONT_OPS = re.compile(r"(?i)continuing operations|discontinued")
SHARES_ROW = re.compile(r"(?i)shares|weighted[- ]average|outstanding")
ADJ_ROW = re.compile(r"(?i)\b(adjusted|non[- ]?gaap|pro\s*forma|excluding|core)\b")


class Grid(HTMLParser):
    """Table extractor with colspan expansion and per-table preceding-text anchors."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.anchors, self.text = [], [], []
        self._t = self._r = self._c = None
        self._span = 1

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            if self._t is None:
                self._t, self._anchor = [], len(self.text)
        elif tag == "tr" and self._t is not None:
            self._r = []
        elif tag in ("td", "th") and self._r is not None:
            self._c = []
            try:
                self._span = max(1, min(12, int(str(a.get("colspan", "1")).strip() or 1)))
            except ValueError:
                self._span = 1

    def handle_endtag(self, tag):
        if tag == "table" and self._t is not None:
            self.tables.append(self._t)
            self.anchors.append(self._anchor)
            self._t = None
        elif tag == "tr" and self._t is not None and self._r is not None:
            self._t.append(self._r)
            self._r = None
        elif tag in ("td", "th") and self._r is not None and self._c is not None:
            txt = re.sub(r"\s+", " ", "".join(self._c)).strip()
            self._r.extend([txt] * self._span)     # colspan expansion
            self._c, self._span = None, 1

    def handle_data(self, d):
        (self._c if self._c is not None else self.text).append(d)


def _num(s):
    s = s.strip().replace("\u2212", "-")
    if not s or not MONEY.match(s):
        return None
    neg = (s.startswith("(") and s.endswith(")")) or s.lstrip("$( ").startswith("-")
    v = re.sub(r"[^\d.]", "", s)
    if v in ("", "."):
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    return -x if neg else x


def _date(text):
    for pat, kind in DATE_PATS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "mdy":
                mo = MONTHS.get(m.group(1).lower().rstrip("."))
                if not mo:
                    continue
                return pd.Timestamp(int(m.group(3)), mo, int(m.group(2)))
            y = int(m.group(3))
            y += 2000 if y < 100 else 0
            return pd.Timestamp(y, int(m.group(1)), int(m.group(2)))
        except Exception:
            continue
    return None


def _label(row):
    """Row label = first non-empty, non-numeric cell.

    Colspan expansion plus the leading spacer/indent columns these filers use mean the
    label is frequently NOT in row[0].
    """
    for c in row:
        s = c.strip()
        if s and _num(s) is None and s not in ("$", "%", "(", ")"):
            return s
    return ""


def _is_year_row(r):
    """A row of bare 4-digit years is header, not data.

    Filers routinely split a column heading across rows as "August 4," / "2019", so a
    year-only row must stay inside the header or the column loses its date entirely.
    """
    n = [_num(c) for c in r if _num(c) is not None]
    return bool(n) and all(float(x).is_integer() and 1990 <= x <= 2100 for x in n)


def _split_header(tbl):
    """Header rows = leading rows before the first row carrying 2+ non-year numeric cells."""
    for i, r in enumerate(tbl):
        if sum(1 for c in r if _num(c) is not None) >= 2 and not _is_year_row(r):
            return tbl[:i], i
    return tbl[: min(8, len(tbl))], min(8, len(tbl))


def _col_headers(head, ncol):
    return [" ".join(r[ci] for r in head if ci < len(r)).strip() for ci in range(ncol)]


def is_income_statement(tbl, ctx):
    """Structural test: revenue row AND net-income row AND a per-share row present."""
    if NON_GAAP_CTX.search(ctx):
        return False, "context_non_gaap_or_segment"
    labels = [_label(r) for r in tbl if r and _label(r)]
    if not any(REV_ROW.match(x) for x in labels):
        return False, "no_revenue_row"
    if not any(NI_ROW.match(x) for x in labels):
        return False, "no_net_income_row"
    if not any(PERSHARE_CTX.search(x) or DILUTED_BARE.match(x) or DILUTED_FULL.search(x)
               for x in labels):
        return False, "no_per_share_row"
    return True, "ok"


def pick_quarter_column(tbl):
    """Latest-dated three-month column; YTD columns rejected. Returns (idx,label,end)."""
    head, _ = _split_header(tbl)
    ncol = max((len(r) for r in tbl), default=0)
    hdrs = _col_headers(head, ncol)
    cands = []
    for ci, h in enumerate(hdrs):
        if not h or YTD.search(h):
            continue
        d = _date(h)
        if d is None:
            continue
        if not QTR_SPAN.search(h):
            continue
        cands.append((ci, h, d))
    if not cands:
        return None, None, None
    best = max(cands, key=lambda x: (x[2], -x[0]))
    return best[0], best[1][:160], best[2]


def detect_period_end(html):
    """Announced quarter end, derived from spanning three-month header text alone.

    Independent of EPS extraction so that event identity - and therefore the
    outcome-blind development sample - is defined for EVERY located exhibit,
    including ones the EPS parser fails on.
    """
    p = Grid()
    try:
        p.feed(html)
    except Exception:
        pass
    best, fallback = None, None
    for ti, tbl in enumerate(p.tables):
        if len(tbl) < 3:
            continue
        _, _, end = pick_quarter_column(tbl)
        if end is None:
            continue
        pre = re.sub(r"\s+", " ", "".join(p.text[max(0, p.anchors[ti] - 400):p.anchors[ti]]))
        head, _ = _split_header(tbl)
        ok, _why = is_income_statement(tbl, pre[-600:] + " " +
                                       " ".join(" ".join(r) for r in head))
        if ok:
            best = end if best is None or end > best else best
        elif fallback is None or end > fallback:
            fallback = end
    return best if best is not None else fallback


def extract_diluted_eps(html):
    """Return (record|None, diagnostics). Structural, table-scoped, never filing-wide."""
    p = Grid()
    try:
        p.feed(html)
    except Exception:
        pass
    full = re.sub(r"\s+", " ", "".join(p.text))
    diag = {"n_tables": len(p.tables), "income_tables": 0, "reason": None}
    hits = []
    for ti, tbl in enumerate(p.tables):
        if len(tbl) < 4:
            continue
        pre = re.sub(r"\s+", " ", "".join(p.text[max(0, p.anchors[ti] - 400):p.anchors[ti]]))
        head, hend = _split_header(tbl)
        ctx = pre[-600:] + " " + " ".join(" ".join(r) for r in head)
        ok, why = is_income_statement(tbl, ctx)
        if not ok:
            continue
        diag["income_tables"] += 1
        qcol, qlab, qend = pick_quarter_column(tbl)
        if qcol is None:
            continue
        section_pershare = False
        for ri, row in enumerate(tbl):
            if not row:
                continue
            label = _label(row)
            if not label:
                continue
            if PERSHARE_CTX.search(label) and not any(_num(c) is not None for c in row):
                section_pershare = True
                continue
            if REV_ROW.match(label) or NI_ROW.match(label):
                section_pershare = False
            if ADJ_ROW.search(label) or YTD.search(label) or SHARES_ROW.search(label):
                continue
            named = bool(DILUTED_FULL.search(label))
            bare = bool(DILUTED_BARE.match(label)) and section_pershare
            if not (named or bare):
                continue
            v = None
            if qcol < len(row):
                v = _num(row[qcol])
            if v is None:                       # tolerate a shifted numeric cell
                nums = [(i, _num(c)) for i, c in enumerate(row) if _num(c) is not None]
                nums = [(i, x) for i, x in nums if i >= qcol]
                v = nums[0][1] if nums else None
            if v is None or abs(v) >= 100:      # EPS magnitude guard (share counts out)
                continue
            hits.append({"value": v, "row_label": label[:140], "row_index": ri,
                         "column_label": qlab, "column_index": qcol,
                         "table_index": ti, "fiscal_period_end": str(qend.date()),
                         "continuing_ops": bool(CONT_OPS.search(label)),
                         "bare_diluted": bare})
    if not hits:
        diag["reason"] = "no_structural_match"
        return None, diag
    plain = [h for h in hits if not h["continuing_ops"]]
    pool = plain if plain else hits          # consolidated preferred over continuing-ops
    vals = {round(h["value"], 4) for h in pool}
    if len(vals) > 1:
        diag["reason"] = f"ambiguous_multiple_match:{sorted(vals)}"
        return None, diag                     # REFUSE rather than guess
    diag["reason"] = "ok"
    diag["used_continuing_ops_fallback"] = not plain
    return pool[0], diag


# ================================ SEC retrieval ================================
def find_exhibits(cik, accession):
    """All earnings-release exhibit files in the 8-K, in deterministic order.

    Several filers put the press release in 99.1 and the consolidated financial
    statements in a sibling exhibit, so every candidate in the same 8-K is parsed and
    disagreement between them is refused as ambiguous.
    """
    accn = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}"
    idx = json.loads(get(f"{base}/index.json", UA, f"ix_{accession}.json"))
    names = [i["name"] for i in idx["directory"]["item"]]

    def ok(n):
        ln = n.lower()
        if not ln.endswith((".htm", ".html")):
            return False
        if "index" in ln or re.match(r"^r\d+\.htm", ln) or re.match(r"^\d{10}-\d\d-\d{6}", ln):
            return False
        return bool(re.search(r"99[-_.]?1", ln) or re.search(r"ex[-_]?99", ln))

    c = sorted([n for n in names if ok(n)],
               key=lambda n: (0 if re.search(r"99[-_.]?1", n.lower()) else 1, len(n), n))
    return [(f"{base}/{n}", n) for n in c]


def build_events():
    ct = json.loads(get("https://www.sec.gov/files/company_tickers.json", UA, "cik.json"))
    cik = {v["ticker"]: int(v["cik_str"]) for v in ct.values()}
    rows = []
    for t in UNIVERSE:
        c = cik.get(t)
        if c is None:
            continue
        sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{c:010d}.json", UA,
                             f"sub_{t}.json"))
        r = sub["filings"]["recent"]
        for form, items, fd, acc, adt in zip(r["form"], r["items"], r["filingDate"],
                                             r["accessionNumber"], r["acceptanceDateTime"]):
            if form == "8-K" and "2.02" in (items or "") and "2018-01-01" <= fd <= "2025-12-31":
                rows.append({"ticker": t, "cik": c, "accession": acc, "filing_date": fd,
                             "acceptance_utc": adt})
    return pd.DataFrame(rows), cik


def xbrl_eps_reference(cik, ticker):
    """AUDIT REFERENCE ONLY. Never selects, replaces or alters an Exhibit value."""
    try:
        f = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                           UA, f"cf_{ticker}.json"))
    except Exception:
        return {}, []
    g = f.get("facts", {}).get("us-gaap", {})
    primary = "EarningsPerShareDiluted"
    equivalents = ["IncomeLossFromContinuingOperationsPerDilutedShare",
                   "EarningsPerShareBasicAndDiluted"]
    names = [primary] + ([] if primary in g else equivalents)
    used, out = [], {}
    for cn in names:
        if cn not in g:
            continue
        for u, arr in g[cn]["units"].items():
            if "USD" not in u:
                continue
            for x in arr:
                # three-month duration, consolidated + dimensionless, 10-Q/10-K sourced
                if not (x.get("start") and x.get("end")):
                    continue
                dur = (pd.Timestamp(x["end"]) - pd.Timestamp(x["start"])).days
                if not 80 <= dur <= 100:
                    continue
                if x.get("segments") or x.get("dim"):
                    continue
                k = x["end"]
                prev = out.get(k)
                if prev is None or pd.Timestamp(x["filed"]) < pd.Timestamp(prev["filed"]):
                    out[k] = {"val": float(x["val"]), "filed": x["filed"],
                              "accn": x.get("accn"), "form": x.get("form"), "concept": cn}
        if out:
            used.append(cn)
            break
    return out, used


def extract_event(cik, accession):
    """Parse every earnings exhibit in one 8-K. Returns (record|None, meta)."""
    meta = {"exhibit_url": None, "exhibit_name": None, "exhibit_sha256": None,
            "n_exhibits": 0, "period_end": None, "reason": None, "n_tables": 0,
            "income_tables": 0}
    try:
        cands = find_exhibits(cik, accession)
    except Exception as e:                                        # noqa: BLE001
        meta["reason"] = f"index_error:{type(e).__name__}"
        return None, meta
    meta["n_exhibits"] = len(cands)
    if not cands:
        meta["reason"] = "no_exhibit"
        return None, meta
    meta["exhibit_url"], meta["exhibit_name"] = cands[0]
    hits, reasons, pend = [], [], None
    for url, name in cands:
        try:
            raw = get(url, UA, f"ex_{accession}_{name[:40]}")
        except Exception as e:                                    # noqa: BLE001
            reasons.append(f"fetch:{type(e).__name__}")
            continue
        html = raw.decode("utf-8", "replace")
        pe = detect_period_end(html)
        if pe is not None and (pend is None or pe > pend):
            pend = pe
        hit, diag = extract_diluted_eps(html)
        meta["n_tables"] += diag["n_tables"]
        meta["income_tables"] += diag["income_tables"]
        reasons.append(f"{name}:{diag['reason']}")
        if hit:
            hit["exhibit_url"], hit["exhibit_name"] = url, name
            hit["exhibit_sha256"] = hashlib.sha256(raw).hexdigest()
            hits.append(hit)
    meta["period_end"] = str(pend.date()) if pend is not None else None
    meta["reason"] = " | ".join(reasons)[:300]
    if not hits:
        return None, meta
    vals = {round(h["value"], 4) for h in hits}
    if len(vals) > 1:
        meta["reason"] = f"ambiguous_across_exhibits:{sorted(vals)}"
        return None, meta
    best = hits[0]
    meta["exhibit_url"], meta["exhibit_name"] = best["exhibit_url"], best["exhibit_name"]
    meta["exhibit_sha256"] = best["exhibit_sha256"]
    return best, meta


# ================================ market data ================================
def daily(sym):
    p1 = int(pd.Timestamp("2019-01-01").timestamp())
    p2 = int(pd.Timestamp("2026-04-01").timestamp())
    b = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            f"?period1={p1}&period2={p2}&interval=1d", UA_MKT, f"px_{sym}.json")
    res = json.loads(b)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    d = pd.DataFrame({"Date": pd.to_datetime(res["timestamp"], unit="s").normalize(),
                      "Open": q["open"], "Close": q["close"], "Volume": q["volume"]})
    return (d.dropna(subset=["Open", "Close"]).drop_duplicates("Date")
             .sort_values("Date").reset_index(drop=True))


# ================================ phase 1 ================================
def dev_rank(ticker, fpe, accession):
    """Deterministic outcome-blind ranking. Makes no reference to any return."""
    return hashlib.sha256(f"{DEV_SEED}|{ticker}|{fpe}|{accession}".encode()).hexdigest()


def phase1():
    ev, cik = build_events()
    rows = []
    for r in ev.itertuples():
        hit, meta = extract_event(r.cik, r.accession)
        rec = {"ticker": r.ticker, "cik": r.cik, "accession": r.accession,
               "filing_date": r.filing_date, "acceptance_utc": r.acceptance_utc,
               "exhibit_url": meta["exhibit_url"], "exhibit_name": meta["exhibit_name"],
               "exhibit_sha256": meta["exhibit_sha256"], "n_exhibits": meta["n_exhibits"],
               "n_tables": meta["n_tables"], "income_tables": meta["income_tables"],
               "fiscal_period_end": meta["period_end"], "parse_reason": meta["reason"],
               "eps": hit["value"] if hit else None,
               "row_label": hit["row_label"] if hit else None,
               "row_index": hit["row_index"] if hit else None,
               "column_label": hit["column_label"] if hit else None,
               "column_index": hit["column_index"] if hit else None,
               "table_index": hit["table_index"] if hit else None,
               "continuing_ops_used": hit["continuing_ops"] if hit else None}
        rows.append(rec)
    X = pd.DataFrame(rows)
    located = int((X.n_exhibits > 0).sum())
    extracted = int(X.eps.notna().sum())

    # duplicate event identities are REFUSED outright, never first-kept
    have = X[X.eps.notna() & X.fiscal_period_end.notna()].copy()
    d1 = have.duplicated(subset=["ticker", "fiscal_period_end", "accession"], keep=False)
    d2 = have.duplicated(subset=["ticker", "fiscal_period_end"], keep=False)
    refused = int((d1 | d2).sum())
    have = have[~(d1 | d2)].reset_index(drop=True)

    # outcome-blind development sample over ALL located exhibits
    loc = X[X.n_exhibits > 0].copy()
    loc["rank_hash"] = [dev_rank(r.ticker, r.fiscal_period_end, r.accession)
                        for r in loc.itertuples()]
    dev = (loc.sort_values(["ticker", "rank_hash"]).groupby("ticker")
              .head(DEV_PER_TICKER).reset_index(drop=True))
    devset = set(zip(dev.ticker, dev.accession))
    X["in_dev_sample"] = [(t, a) in devset for t, a in zip(X.ticker, X.accession)]
    have["in_dev_sample"] = [(t, a) in devset for t, a in zip(have.ticker, have.accession)]

    # later-XBRL AUDIT REFERENCE (never selects, replaces or feeds a value)
    audit, concepts = [], {}
    for t, grp in have.groupby("ticker"):
        ref, used = xbrl_eps_reference(int(grp.cik.iloc[0]), t)
        concepts[t] = used
        for r in grp.itertuples():
            fpe = pd.Timestamp(r.fiscal_period_end)
            acc = pd.Timestamp(r.acceptance_utc).tz_convert("UTC").tz_localize(None)
            cands = [(k, v) for k, v in ref.items()
                     if abs((pd.Timestamp(k) - fpe).days) <= 5
                     and pd.Timestamp(v["filed"]) > acc.normalize()]
            if not cands:
                status, rv, m = "no_reference", None, None
            else:
                k, m = min(cands, key=lambda kv: pd.Timestamp(kv[1]["filed"]))
                rv = m["val"]
                status = "validated" if abs(r.eps - rv) <= EPS_TOL else "contradicted"
            audit.append({"ticker": t, "accession": r.accession,
                          "fiscal_period_end": r.fiscal_period_end,
                          "exhibit_eps": r.eps, "later_xbrl_eps": rv,
                          "later_xbrl_filed": m["filed"] if m else None,
                          "later_xbrl_form": m["form"] if m else None,
                          "later_xbrl_concept": m["concept"] if m else None,
                          "status": status, "in_dev_sample": bool(r.in_dev_sample)})
    A = pd.DataFrame(audit)
    vc = A.status.value_counts().to_dict() if len(A) else {}
    validated, contradicted = int(vc.get("validated", 0)), int(vc.get("contradicted", 0))
    no_ref = int(vc.get("no_reference", 0))
    ref_cov = (validated + contradicted) / extracted if extracted else 0.0
    prec = validated / (validated + contradicted) if (validated + contradicted) else 0.0

    # usable = validated EPS AND sufficient prior seasonal SUE history (no returns read)
    usable = []
    for t, g in have.sort_values(["ticker", "fiscal_period_end"]).groupby("ticker"):
        ok_acc = set(A[(A.ticker == t) & (A.status == "validated")].accession)
        g = g[g.accession.isin(ok_acc)].reset_index(drop=True)
        eps_by_q = {pd.Timestamp(r.fiscal_period_end): r.eps for r in g.itertuples()}
        for r in g.itertuples():
            q = pd.Timestamp(r.fiscal_period_end)
            diffs = []
            for pq, pe in sorted(eps_by_q.items()):
                if pq >= q:
                    continue
                yr = [k for k in eps_by_q if abs((pq - k).days - 365) <= 20]
                if yr:
                    diffs.append(pe - eps_by_q[yr[0]])
            prior = diffs[-SUE_MAX_HIST:]
            if len(prior) >= SUE_MIN_HIST:
                usable.append({"ticker": t, "accession": r.accession,
                               "fiscal_period_end": r.fiscal_period_end,
                               "n_prior_seasonal_diffs": len(prior)})
    U = pd.DataFrame(usable)
    use_cov = len(U) / located if located else 0.0
    oos_by_year = {}
    if len(U):
        yr = pd.to_datetime(U.fiscal_period_end).dt.year
        oos_by_year = {str(y): int((yr == y).sum()) for y in (2023, 2024, 2025)}

    gates = {
        "reference_coverage": {"value": round(ref_cov, 4), "required": EGATE["reference_coverage"],
                               "passed": ref_cov >= EGATE["reference_coverage"]},
        "conditional_precision": {"value": round(prec, 4),
                                  "required": EGATE["conditional_precision"],
                                  "passed": prec >= EGATE["conditional_precision"]},
        "usable_event_coverage": {"value": round(use_cov, 4),
                                  "required": EGATE["usable_event_coverage"],
                                  "passed": use_cov >= EGATE["usable_event_coverage"]},
        "tickers": {"value": int(U.ticker.nunique()) if len(U) else 0,
                    "required": EGATE["tickers"],
                    "passed": (int(U.ticker.nunique()) if len(U) else 0) >= EGATE["tickers"]},
        "usable_events": {"value": int(len(U)), "required": EGATE["events"],
                          "passed": len(U) >= EGATE["events"]},
        "oos_events": {"value": int(sum(oos_by_year.values())), "required": EGATE["oos"],
                       "passed": sum(oos_by_year.values()) >= EGATE["oos"]},
        "oos_per_year": {"value": oos_by_year, "required": EGATE["oos_per_year"],
                         "passed": bool(oos_by_year) and all(
                             v >= EGATE["oos_per_year"] for v in oos_by_year.values())},
        "later_xbrl_predictive_inputs": {"value": 0, "required": 0, "passed": True},
    }
    passed = all(g["passed"] for g in gates.values())

    prov = [{"ticker": r.ticker, "accession": r.accession,
             "fiscal_period_end": r.fiscal_period_end, "exhibit_url": r.exhibit_url,
             "exhibit_name": r.exhibit_name, "exhibit_sha256": r.exhibit_sha256,
             "acceptance_utc": r.acceptance_utc, "table_index": r.table_index,
             "row_index": r.row_index, "row_label": r.row_label,
             "column_index": r.column_index, "column_label": r.column_label,
             "xbrl_audit_concepts": concepts.get(r.ticker, []),
             "in_dev_sample": bool(r.in_dev_sample)} for r in have.itertuples()]

    # author-side structural spot audit of the fixed development sample.
    # NOT an independent human review - it is the author's own record.
    st = dict(zip(A.accession, A.status)) if len(A) else {}
    rf = dict(zip(A.accession, A.later_xbrl_eps)) if len(A) else {}
    spot = [{"ticker": r.ticker, "accession": r.accession,
             "fiscal_period_end": r.fiscal_period_end,
             "exhibit_url": r.exhibit_url,
             "selected_statement_table_index": r.table_index,
             "selected_row_index": r.row_index, "selected_row_label": r.row_label,
             "selected_column_label": r.column_label, "parsed_value": r.eps,
             "later_xbrl_reference": rf.get(r.accession),
             "audit_status": st.get(r.accession, "not_extracted"),
             "parse_reason": r.parse_reason}
            for r in dev.itertuples()]

    # the audit outcome is carried on the event panel itself: one compact file
    X["audit_status"] = [st.get(a, "not_extracted") for a in X.accession]
    X["later_xbrl_eps"] = [rf.get(a) for a in X.accession]
    X["usable_event"] = X.accession.isin(set(U.accession) if len(U) else set())
    X.to_csv(OUT / "event_panel_v1.0.csv", index=False, lineterminator="\n")
    (OUT / "provenance_v1.0.json").write_text(
        json.dumps(prov, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")

    val = {"artifact": "SEMICONDUCTOR_EPS_EXTRACTION_VALIDATION", "version": "1.0",
           "status": "EXPLORATORY_RETROSPECTIVE_DEVELOPMENT_ONLY", "sector": SECTOR,
           "google_trends_used": False, "analyst_consensus_used": False,
           "later_xbrl_used_for_prediction": False,
           "later_xbrl_role": ("audit reference only; it never selected, replaced or altered "
                               "an Exhibit value and never entered a model feature"),
           "universe": UNIVERSE, "benchmark": BENCH,
           "item_202_events": int(len(X)), "located_exhibits": located,
           "extracted": extracted, "validated": validated, "contradicted": contradicted,
           "no_reference": no_ref,
           "duplicate_identities_refused": refused,
           "dev_sample": {"seed": DEV_SEED, "per_ticker": DEV_PER_TICKER,
                          "n": int(len(dev)), "tickers": int(dev.ticker.nunique()),
                          "rule": ("ascending SHA-256 of "
                                   "'SEMICONDUCTOR_EPS_PARSER_DEV|ticker|fiscal_period_end|"
                                   "accession'; no reference to returns")},
           "extracted_by_ticker": {t: int(X[X.ticker == t].eps.notna().sum())
                                   for t in UNIVERSE},
           "usable_events": int(len(U)), "usable_by_year": oos_by_year,
           "tolerance_eps_absolute": EPS_TOL,
           "gates": gates, "extraction_gate_passed": bool(passed),
           "xbrl_audit_concepts": concepts,
           "structural_spot_audit_note": ("author-side structural record of the fixed "
                                          "development sample; NOT an independent human review"),
           "structural_spot_audit": spot}
    (OUT / "extraction_validation_v1.0.json").write_text(
        json.dumps(val, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")

    print(f"events {len(X)} located {located} extracted {extracted}")
    print(f"validated {validated} contradicted {contradicted} no_reference {no_ref}")
    print(f"reference_coverage {ref_cov:.4f} conditional_precision {prec:.4f} "
          f"usable_event_coverage {use_cov:.4f}")
    print(f"usable {len(U)} tickers {gates['tickers']['value']} by year {oos_by_year}")
    print("EXTRACTION GATE PASSED:", passed)
    return val, passed


def main() -> int:
    val, passed = phase1()
    if not passed:
        # Gate failed. Stop BEFORE any return is inspected. No FROZEN_DESIGN outcome
        # commit, no SUE construction, no Model B/C fit, no bootstrap, no trading test.
        failing = [k for k, g in val["gates"].items() if not g["passed"]]
        print("STOP: EXTRACTION_NOT_RELIABLE; failing gates:", failing)
        return 0
    raise SystemExit("phase 2 runs only after the extraction gate passes")


if __name__ == "__main__":
    sys.exit(main())
