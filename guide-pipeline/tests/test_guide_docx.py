import base64
import zipfile

import pytest
from docx import Document
from docx.oxml.ns import qn

from guide_pipeline import guide_docx as G
from sample_model import sample_model

WPD = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def xml(path, part="word/document.xml"):
    return zipfile.ZipFile(path).read(part).decode("utf-8")


@pytest.fixture
def no_browser(monkeypatch):
    monkeypatch.setattr(G, "_rasterise", lambda svgs, out, say: [None] * len(svgs))


def test_protection_hash_matches_one_word_wrote_itself():
    # Word 365 protected a file read-only with this password (2026-11-17)
    salt = base64.b64decode("0zKbnQQvxQELQ50HRCahRg==")
    assert G.protection_hash("Symposed!2026", salt) == (
        "oSkBNP66Q/OJd2cZza7na2JLcnrSkjOkBkDsTcKh07ove91YH3v8UaV4SYp3xb/nUiuWrjS3GIam3XrMWn59dg==")


def test_guide_is_read_only_with_proofing_marks_off(tmp_path, monkeypatch, no_browser):
    monkeypatch.setattr(G, "_word", lambda *a, **k: None)
    path = tmp_path / "guide.docx"
    warnings = G.write_docx(sample_model(), path, password="secret", say=lambda _m: None)
    settings = xml(path, "word/settings.xml")
    assert 'w:edit="readOnly"' in settings and 'w:enforcement="1"' in settings
    assert "w:hash=" in settings and "w:salt=" in settings
    assert "<w:hideSpellingErrors/>" in settings and "<w:hideGrammaticalErrors/>" in settings
    assert 'w:name="compatibilityMode"' in settings and 'w:val="15"' in settings
    # the schema order Word insists on: protection after the proofing settings
    assert settings.index("hideGrammaticalErrors") < settings.index("documentProtection")
    assert "<w:noProof/>" in xml(path, "word/styles.xml")
    # without Word the strip falls back to the header, and the reviewer is told
    assert warnings and "Word could not be reached" in warnings[0]
    assert "w:background" in xml(path) and G.CREAM in xml(path)
    headers = [n for n in zipfile.ZipFile(path).namelist() if n.startswith("word/header")]
    assert any(G.CLARET_DARK in xml(path, h) for h in headers)


def test_no_password_still_protects(tmp_path, monkeypatch, no_browser):
    monkeypatch.setattr(G, "_word", lambda *a, **k: None)
    path = tmp_path / "guide.docx"
    G.write_docx(sample_model(), path, say=lambda _m: None)
    settings = xml(path, "word/settings.xml")
    assert 'w:edit="readOnly"' in settings and "w:hash=" not in settings


def test_content_cover_and_contents(tmp_path, monkeypatch, no_browser):
    monkeypatch.setattr(G, "_word", lambda *a, **k: None)
    m = sample_model()
    path = tmp_path / "guide.docx"
    G.write_docx(m, path, say=lambda _m: None)
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs)
    for heading in ("Contents", "Read this first", "Your project at a glance",
                    "Appendix A. Glossary of terms"):
        assert heading in text
    cells = "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    assert m["title"] in text and m["steps"][0]["name"] in cells
    body = xml(path)
    assert "PAGEREF glossary" in body and 'w:anchor="glossary"' in body
    # the cover is a full-page dark claret shape in the page itself, not the header
    assert body.count(f'val="{G.CLARET_DARK}"') >= 1
    assert "sym" not in "".join(b.get(qn("w:name")) for b in
                                doc.element.body.iter(qn("w:bookmarkStart")))
    # house style survives the conversion
    assert ";" not in text


def test_layout_from_word_places_a_strip_on_each_page_and_numbers_the_contents(
        tmp_path, monkeypatch, no_browser):
    path = tmp_path / "guide.docx"
    seen = {}

    def fake_word(p, mode="layout", *, pdf=None):
        doc = Document(str(p))
        names = [b.get(qn("w:name")) for b in doc.element.body.iter(qn("w:bookmarkStart"))]
        syms = [n for n in names if n.startswith(G.SYM)]
        seen["syms"] = len(syms)
        return ["pages 3", f"start 2 {syms[0]}", f"start 3 {syms[5]}", "mark glossary 3"]

    monkeypatch.setattr(G, "_word", fake_word)
    assert G.write_docx(sample_model(), path, say=lambda _m: None) == []
    doc = Document(str(path))
    anchors = list(doc.element.body.iter(WPD + "anchor"))
    # the cover's shape and logo, then a strip and a logo on pages 2 and 3
    assert len(anchors) == 6 and seen["syms"] > 5
    toc = [p for p in doc.paragraphs if "PAGEREF glossary" in p._p.xml]
    assert toc and toc[0].text.endswith("3")


def test_a_page_starting_inside_a_table_splits_the_table(tmp_path, monkeypatch, no_browser):
    path = tmp_path / "guide.docx"
    passes = []

    def fake_word(p, mode="layout", *, pdf=None):
        doc = Document(str(p))
        top = [el for el in doc.element.body if el.tag == qn("w:tbl")]
        passes.append(len(top))
        if len(passes) == 1:
            big = max(range(len(top)), key=lambda i: len(top[i].findall(qn("w:tr"))))
            return ["pages 2", f"table 2 {big + 1} 3"]
        new = [b.get(qn("w:name")) for b in doc.element.body.iter(qn("w:bookmarkStart"))
               if b.get(qn("w:name")).startswith(G.SYM + "t")]
        return ["pages 2", f"start 2 {new[0]}"]

    monkeypatch.setattr(G, "_word", fake_word)
    assert G.write_docx(sample_model(), path, say=lambda _m: None) == []
    assert passes[1] == passes[0] + 1
    doc = Document(str(path))
    split = [el for el in doc.element.body if el.tag == qn("w:tbl")]
    # the second half repeats the header row
    heads = [t for t in split if t.find(qn("w:tr") + "/" + qn("w:trPr") + "/" + qn("w:tblHeader"))
             is not None]
    assert len(heads) >= 2
