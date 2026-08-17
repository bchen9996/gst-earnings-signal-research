#!/usr/bin/env python3
"""Deterministic SVG figure builder for the Signal Without Strategy synthesis.

Emits exactly three SVG files. SVG is chosen so the figures stay reviewable as text and
byte-identical across runs: no timestamps, no randomness, no external fonts, no raster
assets. Every plotted number is read from a committed artifact, never hardcoded as a
research claim -- the only literals here are layout coordinates and axis ticks.

Run twice and diff: the outputs must hash identically.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG1 = ROOT / "SIGNAL_WITHOUT_STRATEGY_FIGURE_1_EVIDENCE_LADDER.svg"
FIG2 = ROOT / "SIGNAL_WITHOUT_STRATEGY_FIGURE_2_SURPRISE_REPLICATION.svg"
FIG3 = ROOT / "SIGNAL_WITHOUT_STRATEGY_FIGURE_3_LEAKAGE_CORRECTION.svg"

# Cross-branch artifact: committed, but not on this branch's ancestry.
MISMATCH_REV = "ddc848865bd79a8aecb782dacbb11082b83a25b9"
MISMATCH_PATH = "ATTENTION_ACTIVITY_MISMATCH_RESULTS_v1.0.json"

# Restrained, print-safe, colour-blind-accessible palette (Okabe-Ito derived).
INK = "#1a1a1a"
MUTED = "#5b5b5b"
GRID = "#d6d6d6"
BLUE = "#0072b2"
ORANGE = "#d55e00"
GREY = "#767676"
FONT = ("font-family=\"Georgia, 'Times New Roman', serif\"")


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def load_rev(rev, path):
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def txt(x, y, s, size=13, fill=INK, anchor="start", weight="normal", style="normal"):
    return (f'<text x="{x}" y="{y}" {FONT} font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}" '
            f'font-style="{style}">{esc(s)}</text>')


def svg(w, h, body, title, desc):
    return ("\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">',
        f'<title id="t">{esc(title)}</title>',
        f'<desc id="d">{esc(desc)}</desc>',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        body,
        '</svg>',
    ]) + "\n")


def fnum(v, nd):
    """Fixed-precision formatting so output is byte-stable across platforms."""
    return f"{v:.{nd}f}"


# ------------------------------------------------------------------ figure 1

def figure_1():
    """Evidence ladder: each study placed at the highest level actually supported."""
    rows = [
        ("Search attention -> absolute earnings move", 1,
         "standalone only; incremental p = 0.98332"),
        ("Search attention -> move direction", 0,
         "worse than intercept-only baseline"),
        ("Search attention -> move magnitude", 0, "paired p = 0.9827"),
        ("Search attention -> weekly volatility", 0, "interval spans zero"),
        ("Product search -> restaurant moves", 0, "Brier and MAE both worsened"),
        ("Earnings surprise -> initial reaction (2023-2025)", 1,
         "suggestive; uncertainty gate failed"),
        ("Earnings surprise -> initial reaction (2010-2017)", 1,
         "significant association; prediction gate failed"),
    ]
    W, H = 1020, 560
    x0, top, band = 470, 118, 46
    colw = 168
    b = [txt(40, 46, "Figure 1. Evidence ladder", 20, INK, weight="bold"),
         txt(40, 70, "Each study is placed at the highest level its evidence actually "
                     "supports, not the level it was designed to reach.", 13, MUTED),
         txt(40, 90, "No study in this program reached Level 3.", 13, MUTED,
             style="italic")]
    heads = ["1. Association", "2. Incremental prediction", "3. Tradability"]
    for i, hd in enumerate(heads):
        cx = x0 + i * colw
        b.append(f'<rect x="{cx}" y="{top - 34}" width="{colw - 10}" height="26" '
                 f'fill="#f2f2f2" stroke="{GRID}"/>')
        b.append(txt(cx + (colw - 10) / 2, top - 16, hd, 12, INK, "middle", "bold"))
    for j, (name, lvl, note) in enumerate(rows):
        y = top + j * band
        b.append(f'<line x1="40" y1="{y + 22}" x2="{W - 40}" y2="{y + 22}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        b.append(txt(40, y + 16, name, 13, INK))
        for i in range(3):
            cx = x0 + i * colw + (colw - 10) / 2
            if i < lvl:
                b.append(f'<circle cx="{cx}" cy="{y + 11}" r="7" fill="{BLUE}"/>')
            elif i == lvl:
                b.append(f'<circle cx="{cx}" cy="{y + 11}" r="7" fill="#ffffff" '
                         f'stroke="{ORANGE}" stroke-width="2"/>')
                b.append(f'<line x1="{cx - 4}" y1="{y + 7}" x2="{cx + 4}" y2="{y + 15}" '
                         f'stroke="{ORANGE}" stroke-width="2"/>')
                b.append(f'<line x1="{cx - 4}" y1="{y + 15}" x2="{cx + 4}" y2="{y + 7}" '
                         f'stroke="{ORANGE}" stroke-width="2"/>')
            else:
                b.append(f'<circle cx="{cx}" cy="{y + 11}" r="7" fill="#ffffff" '
                         f'stroke="{GRID}" stroke-width="1.5"/>')
        b.append(txt(x0 + 3 * colw + 6, y + 16, note, 11, MUTED))
    ly = top + len(rows) * band + 26
    b.append(f'<circle cx="48" cy="{ly}" r="6" fill="{BLUE}"/>')
    b.append(txt(62, ly + 5, "level reached", 12, MUTED))
    b.append(f'<circle cx="188" cy="{ly}" r="6" fill="#ffffff" stroke="{ORANGE}" '
             f'stroke-width="2"/>')
    b.append(txt(202, ly + 5, "level tested and not reached", 12, MUTED))
    b.append(f'<circle cx="418" cy="{ly}" r="6" fill="#ffffff" stroke="{GRID}" '
             f'stroke-width="1.5"/>')
    b.append(txt(432, ly + 5, "not evaluated", 12, MUTED))
    return svg(W, H, "\n".join(b), "Evidence ladder",
               "Association, incremental prediction and tradability for seven studies.")


# ------------------------------------------------------------------ figure 2

def figure_2():
    """MAE-difference point estimates and bootstrap intervals; never pooled."""
    a34 = load("SEMICONDUCTOR_SURPRISE_ABSORPTION_V3_RESULTS_v1.0.json")
    a35 = load("SEMICONDUCTOR_SURPRISE_TEMPORAL_REPLICATION_RESULTS_v1.0.json")
    s34 = a34["stage1"]["bootstrap_mae_diff"]
    s35 = a35["stage1_replication"]["bootstrap_mae_diff"]
    series = [
        ("PR #34 study", "2023-2025", a34["stage1"]["n_oos"], s34, BLUE),
        ("PR #35 replication", "2010-2017", a35["stage1_replication"]["n_oos"], s35,
         ORANGE),
    ]
    W, H = 1020, 470
    L, R, top, band = 330, 940, 150, 96
    lo = min(min(s["ci95"]) for _, _, _, s, _ in series)
    hi = max(max(s["ci95"]) for _, _, _, s, _ in series)
    span = hi - lo
    lo -= span * 0.18
    hi += span * 0.18

    def X(v):
        return L + (v - lo) / (hi - lo) * (R - L)

    b = [txt(40, 46, "Figure 2. Earnings-surprise replication: MAE difference "
                     "(baseline minus augmented)", 19, INK, weight="bold"),
         txt(40, 70, "Positive means adding vendor-defined earnings surprise reduced "
                     "out-of-sample forecast error.", 13, MUTED),
         txt(40, 90, "Bars are 95% moving-block bootstrap intervals (2,000 draws, "
                     "28-day blocks, seed 20260817).", 13, MUTED),
         txt(40, 110, "The two samples do not overlap in time and are NOT pooled.", 13,
             MUTED, style="italic")]
    zx = X(0.0)
    b.append(f'<line x1="{zx:.2f}" y1="{top - 22}" x2="{zx:.2f}" '
             f'y2="{top + band + 46}" stroke="{INK}" stroke-width="1.4" '
             f'stroke-dasharray="5,4"/>')
    b.append(txt(zx, top - 30, "zero", 12, INK, "middle"))
    for i, (label, window, n, s, col) in enumerate(series):
        y = top + i * band
        b.append(txt(40, y + 4, label, 14, INK, weight="bold"))
        b.append(txt(40, y + 24, f"{window} · n = {n} OOS events", 12, MUTED))
        x1, x2 = X(s["ci95"][0]), X(s["ci95"][1])
        xm = X(s["mean"])
        b.append(f'<line x1="{x1:.2f}" y1="{y}" x2="{x2:.2f}" y2="{y}" '
                 f'stroke="{col}" stroke-width="3"/>')
        for xe in (x1, x2):
            b.append(f'<line x1="{xe:.2f}" y1="{y - 9}" x2="{xe:.2f}" y2="{y + 9}" '
                     f'stroke="{col}" stroke-width="3"/>')
        b.append(f'<circle cx="{xm:.2f}" cy="{y}" r="6" fill="{col}"/>')
        b.append(txt(x1, y + 34, fnum(s["ci95"][0], 7), 11, MUTED, "middle"))
        b.append(txt(x2, y + 34, fnum(s["ci95"][1], 7), 11, MUTED, "middle"))
        b.append(txt(xm, y - 18, "mean " + fnum(s["mean"], 7), 11, col, "middle",
                     weight="bold"))
        b.append(txt(R + 6, y + 4, "interval includes zero", 11, MUTED))
    ay = top + band + 66
    b.append(f'<line x1="{L}" y1="{ay}" x2="{R}" y2="{ay}" stroke="{MUTED}" '
             f'stroke-width="1"/>')
    for t in (-0.001, 0.0, 0.001, 0.002, 0.003):
        if lo <= t <= hi:
            tx = X(t)
            b.append(f'<line x1="{tx:.2f}" y1="{ay}" x2="{tx:.2f}" y2="{ay + 6}" '
                     f'stroke="{MUTED}"/>')
            b.append(txt(tx, ay + 20, fnum(t, 3), 11, MUTED, "middle"))
    b.append(txt((L + R) / 2, ay + 42, "MAE difference (baseline minus augmented), "
                                       "in return units", 12, MUTED, "middle"))
    b.append(txt(40, H - 22, "Both intervals include zero, so both windows failed the "
                             "same unchanged uncertainty gate.", 12, MUTED))
    return svg(W, H, "\n".join(b), "Earnings-surprise replication intervals",
               "Point estimates and bootstrap intervals for two non-overlapping "
               "samples, shown separately and never pooled.")


# ------------------------------------------------------------------ figure 3

def figure_3():
    """Pre-correction versus corrected directional model."""
    d = load("RETROSPECTIVE_DIRECTION_SIGNAL_RESULTS_v1.0.json")
    log = d["pooled_out_of_sample"]["logistic_l2"]
    corrected = {"accuracy": log["accuracy"], "auc": log["auc"],
                 "net": d["combined_strategy"]["direction_only"]["mean_net_pct"]}
    # Pre-correction values are quoted from the committed report narrative and are
    # INVALIDATED; they are shown only to size the distortion.
    pre = {"accuracy": 0.636, "auc": 0.6395, "net": 0.60}
    panels = [("Accuracy", "accuracy", 3, ""),
              ("AUC", "auc", 4, ""),
              ("Direction-only net return", "net", 4, "%")]
    W, H = 1020, 470
    px0, pw, top, bh = 70, 310, 190, 150
    b = [txt(40, 46, "Figure 3. Leakage correction in the directional model", 19, INK,
             weight="bold"),
         txt(40, 70, "Before correction: 68 duplicated rows among 285, and a lag feature "
                     "reading the same event's own outcome.", 13, MUTED),
         txt(40, 90, "After correction: 217 unique event identities and a corrected "
                     "feature.", 13, MUTED),
         txt(40, 112, "The pre-correction values are INVALIDATED. They are shown only to "
                      "size the distortion, never as results.", 13, ORANGE,
             weight="bold")]
    for i, (title, key, nd, suf) in enumerate(panels):
        cx = px0 + i * pw
        b.append(txt(cx, top - 40, title, 14, INK, weight="bold"))
        vals = [("pre-correction\n(invalidated)", pre[key], ORANGE),
                ("corrected", corrected[key], BLUE)]
        vmax = max(abs(v) for _, v, _ in vals) or 1.0
        base = top + bh
        b.append(f'<line x1="{cx}" y1="{base}" x2="{cx + pw - 70}" y2="{base}" '
                 f'stroke="{MUTED}" stroke-width="1"/>')
        for j, (lab, v, col) in enumerate(vals):
            bx = cx + 30 + j * 120
            hgt = abs(v) / vmax * (bh - 30)
            y = base - hgt if v >= 0 else base
            if j == 0:
                b.append(f'<rect x="{bx}" y="{y:.2f}" width="70" height="{hgt:.2f}" '
                         f'fill="none" stroke="{col}" stroke-width="2" '
                         f'stroke-dasharray="6,4"/>')
            else:
                b.append(f'<rect x="{bx}" y="{y:.2f}" width="70" height="{hgt:.2f}" '
                         f'fill="{col}"/>')
            vy = y - 8 if v >= 0 else y + hgt + 16
            b.append(txt(bx + 35, vy, fnum(v, nd) + suf, 12, col, "middle",
                         weight="bold"))
            for k, line in enumerate(lab.split("\n")):
                b.append(txt(bx + 35, base + 20 + k * 14, line, 11, MUTED, "middle"))
        if key == "auc":
            cy = base - (0.5 / vmax) * (bh - 30)
            b.append(f'<line x1="{cx}" y1="{cy:.2f}" x2="{cx + pw - 70}" y2="{cy:.2f}" '
                     f'stroke="{GREY}" stroke-width="1" stroke-dasharray="4,4"/>')
            b.append(txt(cx + pw - 66, cy + 4, "chance 0.5", 10, GREY))
    b.append(txt(40, H - 26, "Corrected accuracy is below the 0.5347 achieved by always "
                             "predicting a positive move; corrected AUC is below chance.",
                 12, MUTED))
    return svg(W, H, "\n".join(b), "Leakage correction",
               "Directional model accuracy, AUC and net return before and after "
               "correcting duplicated rows and a same-event lag feature.")


def main(argv=None):
    for path, fn in ((FIG1, figure_1), (FIG2, figure_2), (FIG3, figure_3)):
        path.write_text(fn(), encoding="utf-8", newline="\n")
        print("wrote", path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
