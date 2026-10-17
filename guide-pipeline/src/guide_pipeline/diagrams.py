"""SVG diagrams for the guide, drawn in code (no Graphviz needed).

Every function returns a standalone <svg> string sized in CSS pixels, which the
PDF renderer embeds inline. Text is wrapped by an approximate character width,
so boxes grow to fit their text rather than overflowing.
"""

from __future__ import annotations

from html import escape
from typing import Sequence

INK = "#1B2A2E"
MUTED = "#5C574E"
PAPER = "#FBFAF7"
CLARET = "#7A2E2E"
TEAL = "#0F6F66"
OCHRE = "#B07A1F"
PLUM = "#5B3A6B"
SLATE = "#2F5D7C"
RED_BG, RED_LINE = "#FBE4E1", "#C0473A"
GREEN_BG, GREEN_LINE = "#DDF0EC", TEAL
AMBER_BG, AMBER_LINE = "#FBF0D9", OCHRE
BOX_BG, BOX_LINE = "#FFFFFF", "#CFC6B6"

# One colour per step, used for banners, the timeline and the overview.
STEP_COLOURS = (CLARET, TEAL, SLATE, OCHRE, PLUM, "#8A4B2A", "#3E6B48", "#6B2E4E", INK)

FONT = "Hanken Grotesk, sans-serif"
CHAR_W = 0.53  # average glyph width as a fraction of font size


def step_colour(n: int) -> str:
    return STEP_COLOURS[(n - 1) % len(STEP_COLOURS)]


def wrap(text: str, width_px: float, size: float) -> list[str]:
    """Greedy word wrap to fit `width_px` at font `size`."""
    max_chars = max(8, int(width_px / (size * CHAR_W)))
    lines: list[str] = []
    line = ""
    for word in str(text).split():
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= max_chars:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]


def _text(x: float, y: float, lines: Sequence[str], *, size: float = 11, weight: int = 400,
          fill: str = INK, anchor: str = "middle", lh: float = 1.3) -> str:
    out = []
    for i, ln in enumerate(lines):
        out.append(f'<tspan x="{x:.1f}" y="{y + i * size * lh:.1f}">{escape(ln)}</tspan>')
    return (f'<text font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{"".join(out)}</text>')


def _box(x, y, w, h, *, fill=BOX_BG, stroke=BOX_LINE, r=8, sw=1.4) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def _arrow(x1, y1, x2, y2, *, colour=MUTED, label: str = "", label_side: str = "right") -> str:
    out = (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{colour}" '
           f'stroke-width="1.6" marker-end="url(#ah)"/>')
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx = 6 if label_side == "right" else -6
        anchor = "start" if label_side == "right" else "end"
        if y1 == y2:
            mx, my, dx, anchor = mx, my - 6, 0, "middle"
        out += _text(mx + dx, my + 4, [label], size=9.5, weight=700, fill=colour, anchor=anchor)
    return out


def _svg(w: float, h: float, body: str, title: str) -> str:
    defs = (f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
            f'fill="{MUTED}"/></marker></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{escape(title)}">'
            f"{defs}{body}</svg>")


# -- timeline (Gantt) -------------------------------------------------------------
def gantt(rows: Sequence[dict], *, width: float = 640) -> str:
    """rows: {number, name, start_week, end_week} with end_week >= start_week + 1."""
    label_w, row_h, top = 210.0, 26.0, 34.0
    weeks = max([int(r["end_week"]) for r in rows] + [1])
    chart_w = width - label_w - 12
    wpx = chart_w / weeks
    h = top + row_h * len(rows) + 10
    body = []
    step = 1 if weeks <= 16 else 2 if weeks <= 32 else 4
    for wk in range(0, weeks + 1):
        x = label_w + wk * wpx
        body.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{h - 8:.1f}" '
                    f'stroke="#E5DFD3" stroke-width="{1 if wk % step else 1.2}"/>')
        if wk < weeks and wk % step == 0:
            body.append(_text(x + wpx * step / 2, top - 12, [f"Wk {wk + 1}"], size=8.5,
                              fill=MUTED))
    for i, r in enumerate(rows):
        y = top + i * row_h
        colour = step_colour(int(r["number"]))
        label = f'{r["number"]}. {r["name"]}'
        body.append(_text(label_w - 8, y + row_h / 2 + 4,
                          wrap(label, label_w - 10, 10)[:1], size=10, weight=600,
                          anchor="end"))
        x0 = label_w + (int(r["start_week"]) - 1) * wpx
        bw = max(wpx * (int(r["end_week"]) - int(r["start_week"]) + 1), 6)
        body.append(_box(x0 + 1, y + 5, bw - 2, row_h - 10, fill=colour, stroke=colour, r=4))
    return _svg(width, h, "".join(body), "Project timeline by week")


# -- include or exclude decision tree --------------------------------------------
def decision_tree(questions: Sequence[dict], *, width: float = 640) -> str:
    """questions: {question, no_label}. Yes goes down, No goes right to Exclude."""
    qx, qw = 20.0, 330.0
    ex, ew = qx + qw + 70, width - (qx + qw + 70) - 10
    size, gap = 10.5, 30.0
    y = 14.0
    body = [_box(qx, y, qw, 34, fill=INK, stroke=INK),
            _text(qx + qw / 2, y + 21, ["Start with a paper from your search"], size=11,
                  weight=700, fill=PAPER)]
    y += 34
    for i, q in enumerate(questions, 1):
        lines = wrap(f"{i}. {q['question']}", qw - 24, size)
        elines = wrap(f"Exclude: {q.get('no_label') or 'does not meet this criterion'}",
                      ew - 16, 9.5)
        h = max(len(lines) * size * 1.3 + 18, len(elines) * 9.5 * 1.3 + 14)
        body.append(_arrow(qx + qw / 2, y, qx + qw / 2, y + gap - 2, label="Yes" if i > 1 else ""))
        y += gap
        body.append(_box(qx, y, qw, h, fill="#F6F2EA", stroke=SLATE))
        body.append(_text(qx + 12, y + 14 + (h - len(lines) * size * 1.3 - 4) / 2, lines,
                          size=size, weight=600, anchor="start"))
        body.append(_arrow(qx + qw, y + h / 2, ex - 2, y + h / 2, colour=RED_LINE, label="No"))
        body.append(_box(ex, y + 2, ew, h - 4, fill=RED_BG, stroke=RED_LINE))
        body.append(_text(ex + 8, y + 2 + (h - 4 - len(elines) * 9.5 * 1.3) / 2 + 9.5, elines,
                          size=9.5, fill="#7A1F16", anchor="start"))
        y += h
    body.append(_arrow(qx + qw / 2, y, qx + qw / 2, y + gap - 2, label="Yes to all"))
    y += gap
    body.append(_box(qx, y, qw, 36, fill=GREEN_BG, stroke=GREEN_LINE, sw=1.8))
    body.append(_text(qx + qw / 2, y + 22, ["Include the paper"], size=11.5, weight=700,
                      fill=TEAL))
    note = wrap("Not sure at any question? Mark the paper Further review needed and decide "
                "once you have read the full text.", ew - 16, 9.5)
    nh = len(note) * 9.5 * 1.3 + 14
    body.append(_box(ex, y + 36 - nh, ew, nh, fill=AMBER_BG, stroke=AMBER_LINE))
    body.append(_text(ex + 8, y + 36 - nh + 16, note, size=9.5, fill="#6B4A0F", anchor="start"))
    y += 36
    return _svg(width, y + 10, "".join(body), "Include or exclude decision tree")


# -- risk of bias -------------------------------------------------------------------
def rob_tree(tool: dict, *, width: float = 640) -> str:
    """Domains judged one by one, then combined by the tool's overall rule."""
    size = 10
    col_w = (width - 40) / 2
    y = 12.0
    body = [_box(20, y, width - 40, 30, fill=INK, stroke=INK),
            _text(width / 2, y + 19, [f"For each included study, using {tool['name']}"],
                  size=11, weight=700, fill=PAPER)]
    y += 30
    body.append(_arrow(width / 2, y, width / 2, y + 22))
    y += 24
    # domains as numbered boxes in two columns
    doms = tool["domains"]
    rows = (len(doms) + 1) // 2
    row_hs = []
    for r in range(rows):
        pair = doms[r * 2:r * 2 + 2]
        row_hs.append(max(len(wrap(f"{r * 2 + j + 1}. {d}", col_w - 20, size))
                          for j, d in enumerate(pair)) * size * 1.3 + 14)
    top = y
    for i, d in enumerate(doms):
        r, c = divmod(i, 2)
        bx = 20 + c * (col_w + 0)
        by = top + sum(row_hs[:r]) + r * 6
        lines = wrap(f"{i + 1}. {d}", col_w - 20, size)
        body.append(_box(bx + (4 if c else 0), by, col_w - 4, row_hs[r], fill="#EEF3F7",
                         stroke=SLATE))
        body.append(_text(bx + (4 if c else 0) + 10, by + 15, lines, size=size, anchor="start"))
    y = top + sum(row_hs) + rows * 6
    body.append(_text(width / 2, y + 14, ["Answer the tool's signalling questions for each "
                                          "domain, then give it one judgement:"], size=9.5,
                      fill=MUTED))
    y += 22
    js = tool["judgements"]
    colours = [(GREEN_BG, GREEN_LINE, TEAL), (AMBER_BG, AMBER_LINE, "#6B4A0F"),
               (RED_BG, RED_LINE, "#7A1F16"), ("#EBD3D0", "#8E1F14", "#5A120B")]
    if len(js) == 2:
        colours = [colours[0], colours[2]]
    jw = (width - 40 - (len(js) - 1) * 8) / len(js)
    for i, j in enumerate(js):
        bg, line, ink = colours[min(i, len(colours) - 1)]
        body.append(_box(20 + i * (jw + 8), y, jw, 26, fill=bg, stroke=line))
        body.append(_text(20 + i * (jw + 8) + jw / 2, y + 17, [j], size=10, weight=700,
                          fill=ink))
    y += 26
    body.append(_arrow(width / 2, y + 2, width / 2, y + 22))
    y += 24
    rule_lines: list[str] = []
    for rule in tool["overall_rule"]:
        rule_lines += wrap(rule, width - 70, size)
    rh = len(rule_lines) * size * 1.3 + 30
    body.append(_box(20, y, width - 40, rh, fill="#F6F2EA", stroke=CLARET, sw=1.6))
    body.append(_text(32, y + 16, ["Overall judgement for the study"], size=10.5, weight=700,
                      fill=CLARET, anchor="start"))
    body.append(_text(32, y + 32, rule_lines, size=size, anchor="start"))
    y += rh
    return _svg(width, y + 10, "".join(body), f"How to judge risk of bias with {tool['name']}")


# -- PRISMA flow (preliminary counts) ------------------------------------------------
def prisma(counts: dict, *, width: float = 640) -> str:
    left_w, right_w = 300.0, width - 300 - 90
    lx, rx = 20.0, 20 + 300 + 50
    y = 10.0
    body: list[str] = []
    stages = [
        ("Identification", [
            (f"Records found in PubMed: {counts.get('identified', 0):,}"
             f"\nPreprints found in Europe PMC: {counts.get('preprints_identified', 0):,}",
             f"Duplicates removed: {counts.get('duplicates_removed', 0):,}")]),
        ("Screening", [
            (f"Titles and abstracts screened: {counts.get('screened', 0):,}",
             f"Excluded at title and abstract (our estimate): "
             f"{counts.get('excluded_estimate', 0):,}"),
            (f"Full texts to assess: {counts.get('full_text_to_assess', 0):,}",
             "Full texts excluded, with reasons: you will fill this in")]),
        ("Included", [("Studies included in the review: decided by your own screening", "")]),
    ]
    for si, (stage, rows) in enumerate(stages):
        stage_top = y
        for ri, (main, side) in enumerate(rows):
            last = si == len(stages) - 1 and ri == len(rows) - 1
            mlines: list[str] = []
            for part in main.split("\n"):
                mlines += wrap(part, left_w - 20, 10)
            slines = wrap(side, right_w - 20, 9.5) if side else []
            h = max(len(mlines) * 13 + 16, len(slines) * 12.4 + 16)
            if len(rows) == 1:  # room for the rotated stage label
                h = max(h, len(stage) * 9.5 * CHAR_W + 22)
            body.append(_box(lx + 30, y, left_w - 30, h, fill="#FFFFFF", stroke=SLATE))
            body.append(_text(lx + 42, y + 18, mlines, size=10, anchor="start"))
            if side:
                body.append(_arrow(lx + left_w, y + h / 2, rx - 2, y + h / 2))
                body.append(_box(rx, y, right_w, h, fill=RED_BG, stroke=RED_LINE))
                body.append(_text(rx + 10, y + 18, slines, size=9.5, fill="#7A1F16",
                                  anchor="start"))
            y += h
            if not last:
                body.append(_arrow(lx + 30 + (left_w - 30) / 2, y,
                                   lx + 30 + (left_w - 30) / 2, y + 20))
            y += 22
        body.append(f'<rect x="{lx:.1f}" y="{stage_top:.1f}" width="22" '
                    f'height="{y - stage_top - 24:.1f}" rx="4" fill="{SLATE}"/>')
        cy = stage_top + (y - stage_top - 24) / 2
        body.append(f'<text font-family="{FONT}" font-size="9.5" font-weight="700" fill="#fff" '
                    f'text-anchor="middle" transform="translate({lx + 15:.1f} {cy:.1f}) '
                    f'rotate(-90)">{escape(stage)}</text>')
    return _svg(width, y - 12, "".join(body), "PRISMA flow diagram with preliminary counts")
