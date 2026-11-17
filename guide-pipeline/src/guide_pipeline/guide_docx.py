"""Render the guide model as a branded, read-only Word document.

The wording comes from the same template as the PDF (`guide_pdf.render_html`): this
module walks that HTML and draws each part in the Symposed business plan style
(Samarth, 2026-11-17):

  cover      full dark claret, cream logo, white title
  pages      cream, a dark claret strip down the left edge with the cream logo on it
  text       Cambria headings in claret, Calibri body text, white cards on the cream

Word fades anything placed in a page header while the document is being read, so
the strip and logo are not header shapes. They are anchored in the first paragraph
of each page instead, which Word itself reports (`assets/word_layout.ps1`, through
PowerShell). Without Word (another operating system, or Word not installed) the
strip falls back to the header: right in print and PDF, but faded on screen.

The delivered file is protected as read-only and has spelling and grammar marks
switched off, so the red and blue lines never show.
"""

from __future__ import annotations

import base64
import hashlib
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from urllib.request import url2pathname

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor
from lxml import html as lhtml

from .guide_pdf import ASSETS, render_html

Say = Callable[[str], None]

# The Symposed colour theme from the business plan deck.
CLARET_DARK = "4A1B26"
CLARET = "7B2D3B"
ROSE = "B5838D"
SLATE = "2F4858"
GOLD = "C9A227"
CREAM = "F6F0EA"
SAND = "D9C5B2"
INK = "2B2B2B"
QUIET = "6B6B6B"
WHITE = "FFFFFF"
STRIPE = "FBF8F4"
RULE = "E6DCD2"
CODE_BG = "F1E9E1"

HEAD_FONT, BODY_FONT, CODE_FONT = "Cambria", "Calibri", "Consolas"

PAGE_W, PAGE_H = Cm(21.0), Cm(29.7)
STRIP_W = Cm(1.6)
LOGO = ASSETS / "logo-cream.png"
LOGO_RATIO = 0.72                       # height / width of logo-cream.png
MARGIN_L, MARGIN_R = Cm(3.4), Cm(2.4)   # the left margin clears the strip
TEXT_W = PAGE_W - MARGIN_L - MARGIN_R
CARD_PAD = Cm(0.9)                      # left and right padding inside a card

BOX_STYLES = {  # class: (bar colour, title colour)
    "box-warn": (CLARET, CLARET),
    "box-tip": (GOLD, CLARET),
    "box-note": (SLATE, SLATE),
    "box-edit": (ROSE, CLARET),
}

LAYOUT_SCRIPT = ASSETS / "word_layout.ps1"
LAYOUT_PASSES = 4
WORD_ATTEMPTS, WORD_RETRY_SECONDS = 3, 5.0
SYM = "sym"  # bookmarks that mark each top-level paragraph during layout

NS = ('xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


# ------------------------------------------------------------------ public entry

def write_docx(m: dict[str, Any], path: str | Path, *, password: str = "",
               pdf_path: str | Path | None = None, say: Say = print) -> list[str]:
    """Write the guide to `path`; return warnings for the reviewer.

    `password` locks the read-only protection (empty: Word lets anyone switch it
    off from Review > Restrict Editing). `pdf_path` also saves a PDF through Word."""
    path = Path(path)
    # Lift the SVG diagrams out before parsing: the HTML parser mangles self-closing
    # SVG tags such as <rect/>. Each becomes a marker the builder replaces with a picture.
    svgs: list[str] = []

    def lift(match: re.Match) -> str:
        svgs.append(match.group(0))
        return f'<div class="svgfig" data-i="{len(svgs) - 1}"></div>'

    html = re.sub(r"<svg\b.*?</svg>", lift, render_html(m), flags=re.S)
    with tempfile.TemporaryDirectory() as tmp:
        figures = _rasterise(svgs, Path(tmp), say=say)
        doc = _Builder(m, figures).build(lhtml.fromstring(html))
        _proofing_off(doc)
        doc.save(path)
    # protected last: Word cannot lay out a document that is locked for editing
    warnings = _finish(path, password=password, say=say)
    if pdf_path and not warnings:
        if _word(path, "pdf", pdf=Path(pdf_path)) is None:
            warnings.append("The PDF copy could not be saved through Word.")
    return warnings


# ------------------------------------------------------------- drawing helpers

_ids = iter(range(5000, 10**9))


def _anchor_xml(x, y, cx, cy, graphic: str, z: int, behind: bool) -> str:
    n = next(_ids)
    return (f'<w:r {NS}><w:rPr><w:noProof/></w:rPr><w:drawing><wp:anchor distT="0" distB="0" '
            f'distL="0" distR="0" simplePos="0" relativeHeight="{z}" '
            f'behindDoc="{1 if behind else 0}" locked="1" layoutInCell="0" allowOverlap="1">'
            f'<wp:simplePos x="0" y="0"/>'
            f'<wp:positionH relativeFrom="page"><wp:posOffset>{int(x)}</wp:posOffset>'
            '</wp:positionH>'
            f'<wp:positionV relativeFrom="page"><wp:posOffset>{int(y)}</wp:posOffset>'
            '</wp:positionV>'
            f'<wp:extent cx="{int(cx)}" cy="{int(cy)}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:wrapNone/><wp:docPr id="{n}" name="Symposed {n}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic>{graphic}</a:graphic></wp:anchor></w:drawing></w:r>')


def _rect(x, y, cx, cy, fill: str, z: int = 1):
    g = ('<a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
         f'<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/>'
         f'<a:ext cx="{int(cx)}" cy="{int(cy)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
         f'</a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill><a:ln><a:noFill/>'
         '</a:ln></wps:spPr><wps:bodyPr/></wps:wsp></a:graphicData>')
    return parse_xml(_anchor_xml(x, y, cx, cy, g, z, behind=True))


def _picture(part, image: Path, x, y, cx, cy, z: int = 3):
    rid, _ = part.get_or_add_image(str(image))
    n = next(_ids)
    g = ('<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
         f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{n}" name="Symposed logo"/><pic:cNvPicPr/>'
         f'</pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/>'
         f'</a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/>'
         f'<a:ext cx="{int(cx)}" cy="{int(cy)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
         '</a:prstGeom></pic:spPr></pic:pic></a:graphicData>')
    return parse_xml(_anchor_xml(x, y, cx, cy, g, z, behind=False))


def _strip(p_el, part) -> None:
    """The dark claret strip and the logo, on the page of paragraph `p_el`."""
    p_el.append(_rect(0, 0, STRIP_W, PAGE_H, CLARET_DARK, z=2))
    w = Cm(1.1)
    p_el.append(_picture(part, LOGO, Cm(0.25), Cm(0.9), w, Emu(int(w * LOGO_RATIO))))


def _shade(cell, fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), fill)
    tcPr.append(sh)


def _cell_margins(cell, top=120, bottom=120, left=200, right=200) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    m = OxmlElement("w:tcMar")
    for side, v in (("top", top), ("start", left), ("bottom", bottom), ("end", right)):
        e = OxmlElement(f"w:{side}"); e.set(qn("w:w"), str(v)); e.set(qn("w:type"), "dxa")
        m.append(e)
    tcPr.append(m)


def _borders(table, *, outer: Optional[str] = None, inside: Optional[str] = None,
             left_bar: Optional[str] = None, size: int = 4) -> None:
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{side}")
        colour = inside if side.startswith("inside") else outer
        if side == "left" and left_bar:
            e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "36"); e.set(qn("w:color"), left_bar)
        elif colour:
            e.set(qn("w:val"), "single"); e.set(qn("w:sz"), str(size)); e.set(qn("w:color"), colour)
        else:
            e.set(qn("w:val"), "nil")
        e.set(qn("w:space"), "0")
        b.append(e)
    tblPr.append(b)


def _widths(table, widths: list[int]) -> None:
    """Fixed column widths in EMU (Word otherwise sizes columns to their content)."""
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "fixed"); tblPr.append(layout)
    tw = tblPr.find(qn("w:tblW"))
    if tw is None:
        tw = OxmlElement("w:tblW"); tblPr.append(tw)
    tw.set(qn("w:w"), str(int(sum(widths) / 635))); tw.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(int(w / 635)))
    for row in table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = Emu(w)


def _row_flags(row, *, header: bool = False) -> None:
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))
    if header:
        trPr.append(OxmlElement("w:tblHeader"))


def _run(p, text: str, *, size: float = 10.5, bold: bool = False, italic: bool = False,
         color: str = INK, font: str = BODY_FONT, underline: bool = False):
    r = p.add_run(text)
    r.font.name = font
    r._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
    r.font.underline = underline
    r.font.color.rgb = RGBColor.from_string(color)
    return r


def _fmt(p, *, before: float = 0, after: float = 6, line: float = 1.15, keep: bool = False,
         align=None):
    pf = p.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after); pf.line_spacing = line
    if keep:
        pf.keep_with_next = True
    if align is not None:
        p.alignment = align
    return p


def _bookmark(p, name: str, bid: int) -> None:
    s = OxmlElement("w:bookmarkStart"); s.set(qn("w:id"), str(bid)); s.set(qn("w:name"), name)
    e = OxmlElement("w:bookmarkEnd"); e.set(qn("w:id"), str(bid))
    ppr = p.find(qn("w:pPr"))
    if ppr is not None:
        ppr.addnext(s)
    else:
        p.insert(0, s)
    p.append(e)


def _mark_name(anchor: str) -> str:
    """A Word bookmark name for an HTML id (letters, digits and underscores)."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", anchor)
    return name if name[:1].isalpha() else f"s_{name}"


def _text(el) -> str:
    return " ".join((el.text_content() if el is not None else "").split())


def _classes(el) -> set[str]:
    return set((el.get("class") or "").split())


# --------------------------------------------------------------- inline text

class _Seg:
    __slots__ = ("text", "bold", "italic", "code", "link", "color", "size")

    def __init__(self, text, bold=False, italic=False, code=False, link="", color=None, size=None):
        self.text, self.bold, self.italic, self.code = text, bold, italic, code
        self.link, self.color, self.size = link, color, size


def _segments(el, *, bold=False, italic=False, code=False, link="", color=None,
              size=None, skip=frozenset()) -> list[_Seg]:
    out: list[_Seg] = []
    if el.text:
        out.append(_Seg(el.text, bold, italic, code, link, color, size))
    for child in el:
        if not isinstance(child.tag, str) or child.tag in skip:
            pass
        else:
            cls = _classes(child)
            kw = dict(bold=bold, italic=italic, code=code, link=link, color=color, size=size,
                      skip=skip)
            if child.tag in ("strong", "b"):
                kw["bold"] = True
            elif child.tag in ("em", "i"):
                kw["italic"] = True
            elif child.tag == "code" or "query" in cls:
                kw["code"] = True
            elif child.tag == "a":
                kw["link"] = child.get("href") or ""
            elif "tag" in cls:
                kw.update(bold=True, color=GOLD, size=8.5)
            elif "sn" in cls:
                kw.update(bold=True, color=CLARET)
            if child.tag == "br":
                out.append(_Seg("\n", bold, italic, code, link, color, size))
            else:
                out.extend(_segments(child, **kw))
        if child.tail:
            out.append(_Seg(child.tail, bold, italic, code, link, color, size))
    return out


def _clean(segs: list[_Seg]) -> list[_Seg]:
    """Collapse HTML whitespace across segments, as a browser would."""
    out: list[_Seg] = []
    space = True  # at the start of the paragraph
    for s in segs:
        if s.text == "\n":
            out.append(s); space = True
            continue
        t = re.sub(r"\s+", " ", s.text)
        if space:
            t = t.lstrip(" ")
        if not t:
            continue
        space = t.endswith(" ")
        s.text = t
        out.append(s)
    while out and out[-1].text != "\n":
        out[-1].text = out[-1].text.rstrip(" ")
        if out[-1].text:
            break
        out.pop()
    return out


# ------------------------------------------------------------------- builder

class _Builder:
    def __init__(self, m: dict[str, Any], figures: list[Optional[tuple[Path, float]]]):
        self.m = m
        self.figures = figures
        self.doc = Document()
        self.bid = 100
        self.section_id = ""

    # ---- containers
    def par(self, box=None):
        """A new paragraph in the document or a cell. A new cell already holds one empty
        paragraph, which is used first."""
        if box is None:
            return self.doc.add_paragraph()
        ps = box.paragraphs
        unused = (len(ps) == 1 and box._tc[-1] is ps[0]._p and not len(ps[0]._p.r_lst)
                  and ps[0]._p.find(qn("w:hyperlink")) is None)
        if unused:
            return ps[0]
        return box.add_paragraph()

    def table(self, rows: int, cols: int, box=None):
        return (box if box is not None else self.doc).add_table(rows=rows, cols=cols)

    def spacer(self, box=None, size: float = 4):
        p = self.par(box)
        _fmt(p, after=0, line=1.0)
        _run(p, "", size=size)
        return p

    def inline(self, p, el, *, size: float = 10.5, color: str = INK, font: str = BODY_FONT,
               bold: bool = False, skip=frozenset()):
        for s in _clean(_segments(el, skip=skip)):
            self.write(p, s, size=size, color=color, font=font, bold=bold)

    def write(self, p, s: _Seg, *, size: float, color: str, font: str, bold: bool = False):
        if s.text == "\n":
            p.add_run().add_break()
            return
        kw = dict(size=s.size or (size - 0.5 if s.code else size), bold=s.bold or bold,
                  italic=s.italic, color=s.color or (CLARET_DARK if s.code else color),
                  font=CODE_FONT if s.code else font)
        if s.link:
            self.hyperlink(p, s.text, s.link, **kw)
            return
        r = _run(p, s.text, **kw)
        if s.code:
            _run_shade(r, CODE_BG)

    def hyperlink(self, p, text: str, href: str, *, underline: bool = True, **kw):
        h = OxmlElement("w:hyperlink")
        if href.startswith("#"):
            h.set(qn("w:anchor"), _mark_name(href[1:]))
        else:
            rid = p.part.relate_to(href, RT.HYPERLINK, is_external=True)
            h.set(qn("r:id"), rid)
        if underline and kw.get("color") in (INK, None):
            kw["color"] = CLARET
        r = _run(p, text, underline=underline, **kw)
        h.append(r._element)
        p._p.append(h)

    # ---- document
    def build(self, tree):
        doc = self.doc
        normal = doc.styles["Normal"]
        normal.font.name = BODY_FONT; normal.font.size = Pt(10.5)
        normal.font.color.rgb = RGBColor.from_string(INK)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
        _current_word(doc)
        doc.core_properties.title = self.m.get("title") or "Symposed publication guide"
        doc.core_properties.author = "Symposed"

        sections = [s for s in tree.iter("section")]
        cover = next((s for s in sections if "cover" in _classes(s)), None)
        self.cover(cover)

        body = doc.add_section(WD_SECTION.NEW_PAGE)
        body.left_margin, body.right_margin = MARGIN_L, MARGIN_R
        body.top_margin, body.bottom_margin = Cm(2.4), Cm(2.2)
        body.header.is_linked_to_previous = False
        body.footer.is_linked_to_previous = False
        self.footer(body)
        # cream pages: Word's own page colour, which it shows at full strength
        doc.element.insert(0, parse_xml(f'<w:background {NS} w:color="{CREAM}"/>'))
        _setting(doc, "w:displayBackgroundShape")

        first = True
        for sec in sections:
            if sec is cover:
                continue
            if not first:
                self.drop_trailing_spacers()
                p = self.spacer(size=1)
                p.paragraph_format.page_break_before = True
            first = False
            self.section_id = sec.get("id") or ""
            for child in sec:
                self.block(child, None)
        _mark_paragraphs(doc)
        return doc

    def drop_trailing_spacers(self) -> None:
        """Empty paragraphs at the end of a section could spill onto a page of their own
        before the next section's page break."""
        body = self.doc.element.body
        for el in reversed(list(body)):
            if el.tag == qn("w:sectPr"):
                continue
            empty = (el.tag == qn("w:p") and not "".join(el.itertext()).strip()
                     and el.find(".//" + qn("w:drawing")) is None
                     and el.find(".//" + qn("w:sectPr")) is None
                     and el.find(qn("w:bookmarkStart")) is None)
            if empty:
                body.remove(el)
                continue
            break

    def cover(self, sec) -> None:
        doc = self.doc
        s = doc.sections[0]
        s.page_width, s.page_height = PAGE_W, PAGE_H
        s.left_margin = s.right_margin = Cm(2.4)
        s.top_margin, s.bottom_margin = Cm(2.2), Cm(2.0)
        def get(cls):
            return next((e for e in sec.iter() if cls in _classes(e)), None) if sec is not None else None

        p = _fmt(self.par(), after=0, before=46)
        p._p.append(_rect(0, 0, PAGE_W, PAGE_H, CLARET_DARK, z=1))
        w = Cm(2.6)
        p._p.append(_picture(doc.part, LOGO, Cm(2.4), Cm(2.2), w, Emu(int(w * LOGO_RATIO))))
        _run(_fmt(self.par(), after=0), "Symposed", size=26, bold=True, color=WHITE, font=HEAD_FONT)

        title = _text(sec.find(".//h1")) if sec is not None else self.m.get("title", "")
        lines = max(1, math.ceil(len(title) / 30))
        kicker = _text(get("kicker")) or "Publication guide"
        _run(_fmt(self.par(), before=max(40, 200 - 22 * lines), after=10), kicker.upper(),
             size=10, bold=True, color=SAND)
        _run(_fmt(self.par(), after=14, line=1.05), title, size=26, bold=True, color=WHITE,
             font=HEAD_FONT)
        pill = _text(get("pill"))
        if pill:
            _run(_fmt(self.par(), after=36), pill, size=15, color=SAND)
        who = _text(get("for"))
        if who:
            _run(_fmt(self.par(), after=4), who, size=10, bold=True, color=SAND)
        built = _text(get("built"))
        if built:
            _run(_fmt(self.par(), after=40), built, size=10, color=SAND)
        dates = get("dates")
        if dates is not None:
            items = [d for d in dates if isinstance(d.tag, str)]
            t = self.table(2, max(1, len(items)))
            _borders(t)
            for i, d in enumerate(items):
                b = d.find("b")
                value = _text(b)
                label = " ".join((b.tail or "").split()) if b is not None else _text(d)
                _run(_fmt(self.par(t.cell(0, i)), after=0), value, size=13, bold=True,
                     color=WHITE, font=HEAD_FONT)
                _run(_fmt(self.par(t.cell(1, i)), after=0), label, size=9, color=SAND)

    def footer(self, section) -> None:
        fp = section.footer.paragraphs[0]
        for pos in (Cm(8.255), Cm(16.51)):  # the Footer style's own centre and right stops
            fp.paragraph_format.tab_stops.add_tab_stop(pos, WD_TAB_ALIGNMENT.CLEAR)
        fp.paragraph_format.tab_stops.add_tab_stop(TEXT_W, WD_TAB_ALIGNMENT.RIGHT)
        _run(fp, "Symposed publication guide", size=8.5, color=QUIET)
        _run(fp, "\t", size=8.5, color=QUIET)
        _field(fp, "PAGE", "", size=8.5, color=QUIET)

    # ---- blocks
    def block(self, el, box) -> None:
        if not isinstance(el.tag, str):
            return
        tag, cls = el.tag, _classes(el)
        if tag == "h1":
            p = _fmt(self.par(box), after=4, keep=True, line=1.0)
            _run(p, _text(el), size=28, bold=True, color=CLARET, font=HEAD_FONT)
            if self.section_id:
                self.mark(p, self.section_id)
        elif tag in ("h2", "h3"):
            p = _fmt(self.par(box), before=14, after=6, keep=True)
            self.inline(p, el, size=14, color=CLARET, font=HEAD_FONT, bold=True)
        elif tag == "h4":
            p = _fmt(self.par(box), before=10, after=4, keep=True)
            self.inline(p, el, size=12, color=CLARET, font=HEAD_FONT, bold=True)
        elif tag == "p":
            self.paragraph(el, box)
        elif tag == "table":
            self.data_table(el, box)
        elif tag in ("ol", "ul"):
            self.listing(el, box)
        elif tag == "img":
            self.image(el, box)
        elif tag == "div":
            if "svgfig" in cls:
                self.figure(int(el.get("data-i")), box)
            elif "box" in cls:
                self.box(el, box)
            elif "banner" in cls:
                self.banner(el, box)
            elif "stats" in cls:
                self.stats(el, box)
            elif "flow" in cls:
                self.flow(el, box)
            elif "files" in cls:
                self.files(el, box)
            elif "search" in cls:
                self.search(el, box)
            elif "caption" in cls:
                self.paragraph(el, box)
            elif "keep" in cls and el.find("h4") is not None and el.find("ul") is not None:
                self.checklist(el, box)
            elif any(isinstance(c.tag, str) for c in el):
                for c in el:
                    self.block(c, box)
            elif _text(el):
                self.paragraph(el, box)
        elif tag == "span" and _text(el):
            self.paragraph(el, box)

    def paragraph(self, el, box) -> None:
        cls = _classes(el)
        size, color = 10.5, INK
        if "lead" in cls:
            size, color = 12, QUIET
        if cls & {"small", "caption"}:
            size = 9
        if cls & {"muted", "caption"}:
            color = QUIET
        p = _fmt(self.par(box), after=16 if "lead" in cls else 8,
                 keep="lead" in cls)
        self.inline(p, el, size=size, color=color)

    def mark(self, p, anchor: str) -> None:
        self.bid += 1
        _bookmark(p._p, _mark_name(anchor), self.bid)

    def card(self, box, *, fill: str = WHITE, bar: Optional[str] = None):
        t = self.table(1, 1, box)
        _borders(t, left_bar=bar)
        c = t.cell(0, 0)
        _shade(c, fill)
        _cell_margins(c, 160, 160, 260, 260)
        _widths(t, [self._width(box)])
        _row_flags(t.rows[0])
        return t, c

    def _width(self, box) -> int:
        return int(TEXT_W) if box is None else int(box.width or TEXT_W) - int(CARD_PAD)

    def after_card(self, box) -> None:
        if box is None:
            self.spacer(None, size=6)

    def box(self, el, box) -> None:
        cls = _classes(el)
        if "box-quote" in cls:
            _, c = self.card(box, fill=CLARET)
            _cell_margins(c, 240, 240, 300, 300)
            p = _fmt(self.par(c), after=0, line=1.1)
            self.inline(p, el, size=13, color=WHITE, font=HEAD_FONT, bold=True)
            self.after_card(box)
            return
        bar, title_colour = next((v for k, v in BOX_STYLES.items() if k in cls), (CLARET, CLARET))
        _, c = self.card(box, bar=bar)
        children = [x for x in el if isinstance(x.tag, str)]
        if not children:
            self.inline(_fmt(self.par(c), after=0), el)
        for x in children:
            if "box-title" in _classes(x):
                p = _fmt(self.par(c), after=4, keep=True)
                _run(p, _text(x), size=11.5, bold=True, color=title_colour)
            else:
                self.block(x, c)
        _tidy_cell(c)
        self.after_card(box)

    def banner(self, el, box) -> None:
        num = _text(el.find(".//*[@class='num']"))
        label = _text(el.find(".//*[@class='label']"))
        head = el.find(".//h2")
        if head is None:
            head = el.find(".//h3")
        summary = _text(el.find(".//*[@class='sum']"))
        t = self.table(1, 2, box)
        _borders(t)
        _widths(t, [int(Cm(2.4)), self._width(box) - int(Cm(2.4))])
        _row_flags(t.rows[0])
        left, right = t.cell(0, 0), t.cell(0, 1)
        for c in (left, right):
            _shade(c, CLARET)
        _cell_margins(left, 200, 200, 300, 0)
        _cell_margins(right, 220, 220, 120, 300)
        _run(_fmt(self.par(left), after=0, line=1.0), num, size=36, bold=True, color=SAND,
             font=HEAD_FONT)
        if label:
            _run(_fmt(self.par(right), after=2), label.upper(), size=9, bold=True, color=SAND)
        p = _fmt(self.par(right), after=2 if summary else 0, line=1.05)
        _run(p, _text(head), size=20 if head is not None and head.tag == "h2" else 15,
             bold=True, color=WHITE, font=HEAD_FONT)
        if el.get("id"):
            self.mark(p, el.get("id"))
        if summary:
            _run(_fmt(self.par(right), after=0), summary, size=11, color=CREAM)
        self.spacer(box, size=8)

    def checklist(self, el, box) -> None:
        _, c = self.card(box, bar=CLARET_DARK)
        _run(_fmt(self.par(c), after=4, keep=True), _text(el.find("h4")), size=11.5,
             bold=True, color=CLARET)
        for li in el.find("ul").findall("li"):
            p = self.par(c)
            _hang(p, Cm(0.6))
            _fmt(p, after=3)
            _run(p, "☐\t", size=11, color=CLARET)
            self.inline(p, li)
        _tidy_cell(c)
        self.after_card(box)

    def listing(self, el, box) -> None:
        cls = _classes(el)
        if "toc" in cls:
            return self.toc(el, box)
        size = 9 if "small" in cls else 10.5
        for i, li in enumerate(el.findall("li"), start=1):
            p = self.par(box)
            _hang(p, Cm(0.65))
            _fmt(p, after=4)
            if el.tag == "ol":
                _run(p, f"{i}.\t", size=size, bold=True, color=CLARET)
            elif "check" in cls:
                _run(p, "☐\t", size=size + 0.5, color=CLARET)
            else:
                _run(p, "•\t", size=size, bold=True, color=CLARET)
            self.inline(p, li, size=size)
        if box is None:
            self.spacer(None, size=4)

    def toc(self, el, box) -> None:
        for li in el.findall("li"):
            a = li.find("a")
            if a is None:
                continue
            target = _mark_name((a.get("href") or "#")[1:])
            num = _text(li.find("span"))
            p = _fmt(self.par(box), after=7)
            ts = p.paragraph_format.tab_stops
            ts.add_tab_stop(Cm(0.9))
            ts.add_tab_stop(TEXT_W, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            _run(p, num, size=12, bold=True, color=CLARET, font=HEAD_FONT)
            _run(p, "\t", size=12)
            self.hyperlink(p, _text(a), "#" + target, underline=False, size=12, color=INK,
                           font=BODY_FONT)
            _run(p, "\t", size=12, color=QUIET)
            _field(p, f"PAGEREF {target} \\h", "00", size=12, color=CLARET, bold=True)

    def data_table(self, el, box) -> None:
        cls = _classes(el)
        rows = [(tr, tr.getparent().tag == "thead") for tr in el.iter("tr")]
        if not rows:
            return
        ncols = max(sum(int(c.get("colspan") or 1) for c in tr if c.tag in ("td", "th"))
                    for tr, _ in rows)
        total = self._width(box)
        widths = _column_widths(rows, ncols, total)
        t = self.table(len(rows), ncols, box)
        _borders(t, inside=RULE)
        _widths(t, widths)
        size = 9.5 if "compact" in cls else 10
        keyval = "keyval" in cls
        body_i = 0
        for r, (tr, head) in enumerate(rows):
            _row_flags(t.rows[r], header=head)
            col = 0
            for cell_el in [c for c in tr if c.tag in ("td", "th")]:
                span = int(cell_el.get("colspan") or 1)
                cell = t.cell(r, col)
                if span > 1:
                    cell = cell.merge(t.cell(r, col + span - 1))
                    for extra in cell.paragraphs[1:]:
                        extra._p.getparent().remove(extra._p)
                _cell_margins(cell, 100, 100, 160, 160)
                p = _fmt(self.par(cell), after=0)
                if head:
                    _shade(cell, CLARET)
                    self.inline(p, cell_el, size=size, color=WHITE, bold=True)
                else:
                    _shade(cell, WHITE if body_i % 2 == 0 else STRIPE)
                    first_col = col == 0 and ncols > 1
                    self.inline(p, cell_el, size=size,
                                color=CLARET if (first_col and keyval) else INK,
                                bold=first_col and keyval)
                col += span
            if not head:
                body_i += 1
        if "keep" in cls:
            for row in t.rows[:-1]:
                for c in row.cells:
                    for p in c.paragraphs:
                        p.paragraph_format.keep_with_next = True
        self.spacer(box, size=6)

    def stats(self, el, box) -> None:
        items = [s for s in el if "stat" in _classes(s)]
        if not items:
            return
        t = self.table(2, len(items), box)
        _borders(t, inside=None)
        _widths(t, [self._width(box) // len(items)] * len(items))
        for i, s in enumerate(items):
            top, bottom = t.cell(0, i), t.cell(1, i)
            for c in (top, bottom):
                _shade(c, WHITE)
            _cell_margins(top, 160, 0, 180, 120)
            _cell_margins(bottom, 0, 180, 180, 120)
            value = _text(s.find("b"))
            _run(_fmt(self.par(top), after=0, line=1.0), value,
                 size=30 if len(value) <= 6 else 16, bold=True, color=CLARET, font=HEAD_FONT)
            _run(_fmt(self.par(bottom), after=0), _text(s.find("span")), size=9.5)
        for row in t.rows:
            _row_flags(row)
        for c in t.rows[0].cells:
            c.paragraphs[0].paragraph_format.keep_with_next = True
        self.spacer(box, size=8)

    def flow(self, el, box) -> None:
        steps = [s for s in el if "fs" in _classes(s)]
        cols = 3
        t = self.table(math.ceil(len(steps) / cols), cols, box)
        _borders(t, outer=CREAM, inside=CREAM, size=48)
        _widths(t, [self._width(box) // cols] * cols)
        for i, s in enumerate(steps):
            c = t.cell(i // cols, i % cols)
            _shade(c, WHITE)
            _cell_margins(c, 160, 160, 180, 160)
            _run(_fmt(self.par(c), after=2, keep=True), _text(s.find("b")), size=20, bold=True,
                 color=CLARET, font=HEAD_FONT)
            _run(_fmt(self.par(c), after=3, keep=True), _text(s.find(".//*[@class='t']")),
                 size=10.5, bold=True, color=CLARET)
            _run(_fmt(self.par(c), after=0, keep=True), _text(s.find(".//*[@class='d']")), size=9.5)
        for row in t.rows:
            _row_flags(row)
        self.spacer(box, size=8)

    def files(self, el, box) -> None:
        for f in [x for x in el if "file" in _classes(x)]:
            _, c = self.card(box, bar=GOLD)
            _run(_fmt(self.par(c), after=2, keep=True), _text(f.find("b")), size=11,
                 bold=True, color=CLARET)
            b = f.find("b")
            _run(_fmt(self.par(c), after=0), " ".join((b.tail or "").split()), size=10)
            self.spacer(box, size=4)

    def figure(self, i: int, box) -> None:
        fig = self.figures[i] if i < len(self.figures) else None
        _, c = self.card(box)
        p = _fmt(self.par(c), after=0, align=WD_ALIGN_PARAGRAPH.CENTER)
        if fig is None:
            _run(p, "This diagram could not be drawn here. Please ask us for a copy.",
                 size=9.5, italic=True, color=QUIET)
        else:
            png, px = fig
            width = min(self._width(box) - int(Cm(1.2)), int(Cm(px * 2.54 / 96)))
            p.add_run().add_picture(str(png), width=Emu(width))
        self.after_card(box)

    def image(self, el, box) -> None:
        path = _local_path(el.get("src") or "")
        if path is None:
            return
        p = _fmt(self.par(box), before=4, after=4, align=WD_ALIGN_PARAGRAPH.CENTER)
        width = min(int(Cm(13.6)), self._width(box) - int(Cm(0.4)))
        p.add_run().add_picture(str(path), width=Emu(width))

    def search(self, el, box) -> None:
        rec = "rec" in _classes(el)
        _, c = self.card(box, bar=GOLD if rec else CLARET_DARK)
        head = el.find(".//*[@class='search-head']")
        if head is not None:
            p = _fmt(self.par(c), after=6, keep=True)
            parts = [x for x in head if isinstance(x.tag, str)]
            for i, part in enumerate(parts):
                if i:
                    _run(p, "   ", size=10.5)
                if "tag" in _classes(part):
                    _run(p, _text(part), size=8.5, bold=True, color=GOLD)
                else:
                    self.inline(p, part, size=11 if i == 0 else 10.5,
                                bold=i == 0, color=CLARET if i == 0 else INK)
        body = el.find(".//*[@class='search-body']")
        for x in (body if body is not None else []):
            if not isinstance(x.tag, str):
                continue
            if "query" in _classes(x):
                p = _fmt(self.par(c), before=2, after=8, line=1.1)
                _par_shade(p, CODE_BG)
                p.paragraph_format.left_indent = Cm(0.15)
                p.paragraph_format.right_indent = Cm(0.15)
                _run(p, " ".join(x.text_content().split()), size=9, font=CODE_FONT,
                     color=CLARET_DARK)
            else:
                self.block(x, c)
        _tidy_cell(c)
        self.after_card(box)


# --------------------------------------------------------------- small helpers

def _hang(p, indent) -> None:
    pf = p.paragraph_format
    pf.left_indent = indent
    pf.first_line_indent = -indent
    pf.tab_stops.add_tab_stop(indent)


def _run_shade(run, fill: str) -> None:
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), fill)
    run._element.get_or_add_rPr().append(sh)


def _par_shade(p, fill: str) -> None:
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), fill)
    p._p.get_or_add_pPr().append(sh)


def _tidy_cell(cell) -> None:
    """Drop a trailing empty paragraph and the space after the last one."""
    ps = cell.paragraphs
    while len(ps) > 1 and not ps[-1].text and not ps[-1]._p.findall(".//" + qn("w:drawing")):
        ps[-1]._p.getparent().remove(ps[-1]._p)
        ps = cell.paragraphs
    if ps:
        ps[-1].paragraph_format.space_after = Pt(0)


def _field(p, instr: str, result: str, **kw) -> None:
    def fld(kind):
        r = _run(p, "", **kw)
        f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), kind)
        r._element.append(f)
    fld("begin")
    r = _run(p, "", **kw)
    t = OxmlElement("w:instrText"); t.set(qn("xml:space"), "preserve"); t.text = f" {instr} "
    r._element.append(t)
    fld("separate")
    _run(p, result, **kw)
    fld("end")


def _column_widths(rows, ncols: int, total: int) -> list[int]:
    shares: list[Optional[float]] = [None] * ncols
    for tr, head in rows:
        if not head:
            continue
        col = 0
        for c in [x for x in tr if x.tag in ("td", "th")]:
            span = int(c.get("colspan") or 1)
            m = re.search(r"width:\s*([\d.]+)%", c.get("style") or "")
            if m and span == 1:
                shares[col] = float(m.group(1)) / 100
            col += span
    fixed = sum(s for s in shares if s)
    free = [i for i, s in enumerate(shares) if not s]
    rest = max(0.0, 1 - fixed)
    out = [s if s else (rest / len(free) if free else 0) for s in shares]
    return [int(total * s) for s in out]


def _local_path(src: str) -> Optional[Path]:
    if src.startswith("file:"):
        path = Path(url2pathname(urlparse(src).path))
    else:
        path = Path(src) if src else None
    return path if path is not None and path.exists() else None


def _current_word(doc) -> None:
    """Current Word format, not "Compatibility Mode" (python-docx's template is Word 2010)."""
    settings = doc.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat"); _setting(doc, compat)
    for cs in compat.findall(qn("w:compatSetting")):
        if cs.get(qn("w:name")) == "compatibilityMode":
            compat.remove(cs)
    cs = OxmlElement("w:compatSetting")
    cs.set(qn("w:name"), "compatibilityMode")
    cs.set(qn("w:uri"), "http://schemas.microsoft.com/office/word")
    cs.set(qn("w:val"), "15")
    compat.append(cs)


# w:settings children must come in the schema's order or Word reports the file as damaged.
_SETTINGS_ORDER = [
    "writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
    "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText",
    "printFractionalCharacterWidth", "printFormsData", "embedTrueTypeFonts",
    "embedSystemFonts", "saveSubsetFonts", "saveFormsData", "mirrorMargins",
    "alignBordersAndEdges", "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter",
    "gutterAtTop", "hideSpellingErrors", "hideGrammaticalErrors", "activeWritingStyle",
    "proofState", "formsDesign", "attachedTemplate", "linkStyles", "stylePaneFormatFilter",
    "stylePaneSortMethod", "documentType", "mailMerge", "revisionView", "trackRevisions",
    "doNotTrackMoves", "doNotTrackFormatting", "documentProtection", "autoFormatOverride",
    "styleLockTheme", "styleLockQFSet", "defaultTabStop", "autoHyphenation",
    "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps", "showEnvelope",
    "summaryLength", "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders",
    "bookFoldRevPrinting", "bookFoldPrinting", "bookFoldPrintingSheets",
    "drawingGridHorizontalSpacing", "drawingGridVerticalSpacing",
    "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery",
    "doNotUseMarginsForDrawingGridOrigin", "drawingGridHorizontalOrigin",
    "drawingGridVerticalOrigin", "doNotShadeFormData", "noPunctuationKerning",
    "characterSpacingControl", "printTwoOnOne", "strictFirstAndLastChars", "noLineBreaksAfter",
    "noLineBreaksBefore", "savePreviewPicture", "doNotValidateAgainstSchema",
    "saveInvalidXml", "ignoreMixedContent", "alwaysShowPlaceholderText",
    "doNotDemarcateInvalidXml", "saveXmlDataOnly", "useXSLTWhenSaving", "saveThroughXslt",
    "showXMLTags", "alwaysMergeEmptyNamespace", "updateFields", "hdrShapeDefaults",
    "footnotePr", "endnotePr", "compat",
]


def _setting(doc, el) -> Any:
    """Add a w:settings child (a tag name or an element) in its schema position."""
    settings = doc.settings.element
    if isinstance(el, str):
        existing = settings.find(qn(el))
        if existing is not None:
            return existing
        el = OxmlElement(el)
    name = el.tag.split("}")[1]
    rank = _SETTINGS_ORDER.index(name)
    for child in settings:
        cname = child.tag.split("}")[1] if isinstance(child.tag, str) else ""
        if cname in _SETTINGS_ORDER and _SETTINGS_ORDER.index(cname) > rank:
            child.addprevious(el)
            return el
    settings.append(el)
    return el


def _proofing_off(doc) -> None:
    """No red or blue lines: mark all text as not to be checked, and hide any marks."""
    _setting(doc, "w:hideSpellingErrors")
    _setting(doc, "w:hideGrammaticalErrors")
    styles = doc.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        defaults = OxmlElement("w:docDefaults"); styles.insert(0, defaults)
    rpr_default = defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        rpr_default = OxmlElement("w:rPrDefault"); defaults.insert(0, rpr_default)
    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr"); rpr_default.append(rpr)
    if rpr.find(qn("w:noProof")) is None:
        rpr.append(OxmlElement("w:noProof"))
    for st in doc.styles:
        el = st.element.find(qn("w:rPr"))
        if el is not None and el.find(qn("w:noProof")) is None:
            el.append(OxmlElement("w:noProof"))


# --------------------------------------------------------------- protection

_KEY_INIT = (0xE1F0, 0x1D0F, 0xCC9C, 0x84C0, 0x110C, 0x0E10, 0xF1CE, 0x313E, 0x1872, 0xE139,
             0xD40F, 0x84F9, 0x280C, 0xA96A, 0x4EC3)
_KEY_MATRIX = (
    (0xAEFC, 0x4DD9, 0x9BB2, 0x2745, 0x4E8A, 0x9D14, 0x2A09),
    (0x7B61, 0xF6C2, 0xFDA5, 0xEB6B, 0xC6F7, 0x9DCF, 0x2BBF),
    (0x4563, 0x8AC6, 0x05AD, 0x0B5A, 0x16B4, 0x2D68, 0x5AD0),
    (0x0375, 0x06EA, 0x0DD4, 0x1BA8, 0x3750, 0x6EA0, 0xDD40),
    (0xD849, 0xA0B3, 0x5147, 0xA28E, 0x553D, 0xAA7A, 0x44D5),
    (0x6F45, 0xDE8A, 0xAD35, 0x4A4B, 0x9496, 0x390D, 0x721A),
    (0xEB23, 0xC667, 0x9CEF, 0x29FF, 0x53FE, 0xA7FC, 0x5FD9),
    (0x47D3, 0x8FA6, 0x0F6D, 0x1EDA, 0x3DB4, 0x7B68, 0xF6D0),
    (0xB861, 0x60E3, 0xC1C6, 0x93AD, 0x377B, 0x6EF6, 0xDDEC),
    (0x45A0, 0x8B40, 0x06A1, 0x0D42, 0x1A84, 0x3508, 0x6A10),
    (0xAA51, 0x4483, 0x8906, 0x022D, 0x045A, 0x08B4, 0x1168),
    (0x76B4, 0xED68, 0xCAF1, 0x85C3, 0x1BA7, 0x374E, 0x6E9C),
    (0x3730, 0x6E60, 0xDCC0, 0xA9A1, 0x4363, 0x86C6, 0x1DAD),
    (0x3331, 0x6662, 0xCCC4, 0x89A9, 0x0373, 0x06E6, 0x0DCC),
    (0x1021, 0x2042, 0x4084, 0x8108, 0x1231, 0x2462, 0x48C4),
)
SPIN_COUNT = 100_000


def _legacy_key(password: str) -> int:
    """Word's old 32-bit password key, which its SHA-512 protection hash starts from."""
    chars = []
    for ch in password[:15]:
        c = ord(ch)
        chars.append(c & 0xFF or (c >> 8) & 0xFF)
    n = len(chars)
    high = _KEY_INIT[n - 1]
    for i, ch in enumerate(chars):
        row = _KEY_MATRIX[15 - n + i]
        for bit in range(7):
            if ch & (1 << bit):
                high ^= row[bit]
    low = 0
    for ch in reversed(chars):
        low = (((low >> 14) & 1) | ((low << 1) & 0x7FFF)) ^ ch
    low = (((low >> 14) & 1) | ((low << 1) & 0x7FFF)) ^ n ^ 0xCE4B
    return (high << 16) | low


def protection_hash(password: str, salt: bytes) -> str:
    """The w:hash Word writes for read-only protection with this password and salt
    (checked against a file Word protected itself, 2026-11-17)."""
    key = struct.pack("<I", _legacy_key(password)).hex().upper().encode("utf-16-le")
    h = hashlib.sha512(salt + key).digest()
    for i in range(SPIN_COUNT):
        h = hashlib.sha512(h + struct.pack("<I", i)).digest()
    return base64.b64encode(h).decode()


def _protect(doc, password: str) -> None:
    el = OxmlElement("w:documentProtection")
    el.set(qn("w:edit"), "readOnly")
    el.set(qn("w:enforcement"), "1")
    if password:
        salt = os.urandom(16)
        for k, v in (("cryptProviderType", "rsaAES"), ("cryptAlgorithmClass", "hash"),
                     ("cryptAlgorithmType", "typeAny"), ("cryptAlgorithmSid", "14"),
                     ("cryptSpinCount", str(SPIN_COUNT)),
                     ("hash", protection_hash(password, salt)),
                     ("salt", base64.b64encode(salt).decode())):
            el.set(qn(f"w:{k}"), v)
    old = doc.settings.element.find(qn("w:documentProtection"))
    if old is not None:
        old.getparent().remove(old)
    _setting(doc, el)


# ------------------------------------------------------------ figures (SVG)

def _rasterise(svgs: list[str], out: Path, *, say: Say) -> list[Optional[tuple[Path, float]]]:
    """PNG copies of the template's SVG diagrams, drawn by the browser the screenshots use."""
    if not svgs:
        return []
    fonts = "".join(
        f'@font-face {{ font-family: "{fam}"; src: url("{(ASSETS / "fonts" / f).as_uri()}"); '
        f'font-weight: {wt}; }}'
        for fam, f, wt in (("Hanken Grotesk", "HankenGrotesk-400.ttf", 400),
                           ("Hanken Grotesk", "HankenGrotesk-600.ttf", 600),
                           ("Hanken Grotesk", "HankenGrotesk-700.ttf", 700),
                           ("Newsreader", "Newsreader-400.ttf", 400),
                           ("Newsreader", "Newsreader-600.ttf", 600)))
    result: list[Optional[tuple[Path, float]]] = [None] * len(svgs)
    try:
        from playwright.sync_api import sync_playwright

        from .screenshots import launch_browser

        with sync_playwright() as pw:
            browser = launch_browser(pw)
            page = browser.new_page(device_scale_factor=3)
            for i, svg in enumerate(svgs):
                page.set_content(f"<html><head><style>{fonts} body {{ margin: 0; "
                                 f"background: #fff; }}</style></head><body>{svg}</body></html>")
                page.evaluate("document.fonts.ready")
                box = page.locator("svg").first
                png = out / f"figure-{i}.png"
                box.screenshot(path=str(png))
                result[i] = (png, float(box.bounding_box()["width"]))
            browser.close()
    except Exception as exc:  # noqa: BLE001  no browser: the guide still renders
        say(f"Diagrams could not be drawn for the Word guide: {str(exc).splitlines()[0]}")
    return result


# ------------------------------------------------------- layout through Word

def _mark_paragraphs(doc) -> None:
    """Bookmark every top-level paragraph after the cover, so Word can name the
    paragraph each page starts with."""
    body = doc.element.body
    started = False
    n = 0
    for el in body:
        if el.tag != qn("w:p"):
            continue
        if not started:
            started = el.find(".//" + qn("w:sectPr")) is not None  # the cover ends here
            continue
        n += 1
        _bookmark(el, f"{SYM}{n}", 900000 + n)


def _word(path: Path, mode: str = "layout", *, pdf: Optional[Path] = None) -> Optional[list[str]]:
    """Run word_layout.ps1; None when Word cannot be reached."""
    shell = shutil.which("powershell") or shutil.which("powershell.exe")
    if not shell:
        return None
    cmd = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAYOUT_SCRIPT),
           "-Docx", str(Path(path).resolve()), "-Mode", mode]
    if pdf is not None:
        cmd += ["-Pdf", str(Path(pdf).resolve())]
    for attempt in range(WORD_ATTEMPTS):
        if attempt:
            time.sleep(WORD_RETRY_SECONDS)  # e.g. Word still closing from the last call
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            continue
        lines = [l.strip() for l in done.stdout.splitlines() if l.strip()]
        if lines and not any(l.startswith("error") for l in lines):
            return lines
    return None


def _finish(path: Path, *, password: str, say: Say) -> list[str]:
    """Place the strip and logo on every page after the cover, fill in the contents
    page numbers, then remove the layout bookmarks."""
    for _ in range(LAYOUT_PASSES):
        lines = _word(path)
        doc = Document(str(path))
        if lines is None:
            _header_strip(doc)
            _set_toc_pages(doc, {})
            _unmark(doc)
            _protect(doc, password)
            doc.save(str(path))
            msg = ("Word could not be reached to lay out the guide, so the claret strip sits in "
                   "the page header: right in print and PDF, but faded on screen. The contents "
                   "page has no page numbers. Re-render on the Windows machine with Word.")
            say(msg)
            return [msg]
        starts = {int(l.split()[1]): l.split()[2] for l in lines if l.startswith("start ")}
        tables = [tuple(int(x) for x in l.split()[1:4]) for l in lines if l.startswith("table ")]
        if tables:
            # a page that starts inside a long table has no paragraph to hold its strip:
            # split the table there, with a small paragraph between the halves
            _split_tables(doc, tables)
            doc.save(str(path))
            continue
        pages = {l.split()[1]: l.split()[2] for l in lines if l.startswith("mark ")}
        paras = {b.get(qn("w:name")): b.getparent()
                 for b in doc.element.body.iter(qn("w:bookmarkStart"))}
        missing = [n for n, l in enumerate(lines) if l.startswith("none ")]
        for name in starts.values():
            if name in paras:
                _strip(paras[name], doc.part)
        _set_toc_pages(doc, pages)
        _unmark(doc)
        _protect(doc, password)
        doc.save(str(path))
        if missing:
            return [f"{len(missing)} page(s) have no claret strip "
                    "(Word found nowhere to anchor it)."]
        return []
    doc = Document(str(path))
    _unmark(doc)
    _protect(doc, password)
    doc.save(str(path))
    return ["The guide's layout did not settle, so some pages may lack the claret strip."]


def _split_tables(doc, tables: list[tuple[int, int, int]]) -> None:
    top = [el for el in doc.element.body if el.tag == qn("w:tbl")]
    # from the end, so earlier table numbers stay valid
    for _, ti, row in sorted(tables, key=lambda t: (t[1], t[2]), reverse=True):
        if not 1 <= ti <= len(top):
            continue
        tbl = top[ti - 1]
        rows = tbl.findall(qn("w:tr"))
        p = OxmlElement("w:p")
        ppr = OxmlElement("w:pPr")
        # the page already breaks here, so an explicit break moves nothing else
        ppr.append(OxmlElement("w:pageBreakBefore"))
        sp = OxmlElement("w:spacing"); sp.set(qn("w:before"), "0"); sp.set(qn("w:after"), "0")
        sp.set(qn("w:line"), "20"); sp.set(qn("w:lineRule"), "exact"); ppr.append(sp)
        p.append(ppr)
        n = len(list(doc.element.body.iter(qn("w:bookmarkStart"))))
        _bookmark(p, f"{SYM}t{ti}r{row}n{n}", 800000 + n)
        if row <= 1 or row > len(rows):
            # take along the heading kept with this table, so it is not left behind
            first = tbl
            prev = first.getprevious()
            while (prev is not None and prev.tag == qn("w:p")
                   and prev.find(qn("w:pPr") + "/" + qn("w:keepNext")) is not None):
                first, prev = prev, prev.getprevious()
            first.addprevious(p)
            continue
        new = OxmlElement("w:tbl")
        new.append(deepcopy(tbl.find(qn("w:tblPr"))))
        new.append(deepcopy(tbl.find(qn("w:tblGrid"))))
        for hr in rows:
            if hr.find(qn("w:trPr") + "/" + qn("w:tblHeader")) is None:
                break
            new.append(deepcopy(hr))
        for r in rows[row - 1:]:
            new.append(r)
        tbl.addnext(p)
        p.addnext(new)


def _set_toc_pages(doc, pages: dict[str, str]) -> None:
    for instr in doc.element.body.iter(qn("w:instrText")):
        m = re.match(r"\s*PAGEREF (\S+)", instr.text or "")
        if not m:
            continue
        r = instr.getparent().getnext()  # separate
        r = r.getnext() if r is not None else None
        t = r.find(qn("w:t")) if r is not None else None
        if t is not None:
            t.text = pages.get(m.group(1), "")


def _unmark(doc) -> None:
    body = doc.element.body
    ids = set()
    for b in list(body.iter(qn("w:bookmarkStart"))):
        if (b.get(qn("w:name")) or "").startswith(SYM):
            ids.add(b.get(qn("w:id")))
            b.getparent().remove(b)
    for e in list(body.iter(qn("w:bookmarkEnd"))):
        if e.get(qn("w:id")) in ids:
            e.getparent().remove(e)


def _header_strip(doc) -> None:
    """Without Word: the strip and logo in the body pages' header."""
    body = doc.sections[-1]
    p = body.header.paragraphs[0]._p
    p.append(_rect(0, 0, STRIP_W, PAGE_H, CLARET_DARK, z=2))
    w = Cm(1.1)
    p.append(_picture(body.header.part, LOGO, Cm(0.25), Cm(0.9), w, Emu(int(w * LOGO_RATIO))))
