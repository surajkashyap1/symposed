from docx import Document

from guide_pipeline.guide import _format_citation, build_guide
from guide_pipeline.retrieval import RetrievalResult, TaggedPaper
from guide_pipeline.sources.pubmed import Paper
from guide_pipeline.workspace import create_workspace


def _paper(pmid, title, authors=("Smith J",), year=2021, journal="J Test", doi="10.1/x"):
    return Paper(pmid, title, "abstract", tuple(authors), journal, year, doi)


def _result():
    return RetrievalResult(
        query="vitamin d[tiab] AND sepsis[tiab]",
        papers=[
            TaggedPaper(_paper("111", "First trial"), "primary RCT evidence", "an RCT"),
            TaggedPaper(_paper("222", "A review"), "background/context", "sets scene"),
            TaggedPaper(_paper("333", "Loose end"), "(untagged)", ""),
        ],
    )


def test_format_citation_variants():
    many = _paper("1", "T", authors=("A A", "B B", "C C", "D D"))
    assert _format_citation(many).startswith("A A, B B, C C, et al. (2021). T.")
    assert "[No author listed]" in _format_citation(_paper("2", "T2", authors=()))
    no_doi = _format_citation(_paper("2", "T2", authors=(), doi=None))
    assert "PMID: 2." in no_doi and "DOI:" not in no_doi


def test_build_guide_writes_docx_with_expected_content(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="r1")
    path = build_guide(ws, "Vitamin D in sepsis", _result(), search_date="2026-09-22")

    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Publication Guide" in text
    assert "Vitamin D in sepsis" in text
    assert "2026-09-22" in text  # search date
    assert "vitamin d[tiab] AND sepsis[tiab]" in text  # the query
    assert "First trial" in text and "A review" in text  # citations
    assert "primary RCT evidence" in text and "background/context" in text  # use groups
    assert "PROSPERO" in text  # next steps / disclaimer
    assert "Smith J (2021). First trial." in text  # citation formatting


def test_build_guide_untagged_group_is_last(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="r2")
    path = build_guide(ws, "T", _result(), search_date="2026-09-22")
    headings = [
        p.text for p in Document(path).paragraphs if p.style.name.startswith("Heading 3")
    ]
    assert headings[-1] == "(untagged)"


def test_build_guide_includes_landscape_when_given(tmp_path):
    from guide_pipeline.landscape import Landscape

    ws = create_workspace(base=tmp_path, request_id="r3")
    lc = Landscape("t", [], total_literature=44049, by_year={}, systematic_reviews=1150, guidelines=70)
    path = build_guide(ws, "T", _result(), search_date="2026-09-22", landscape=lc)
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "44,049" in text and "1,150" in text and "Research landscape" in text
