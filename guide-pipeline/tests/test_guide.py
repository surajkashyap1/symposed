from docx import Document

from guide_pipeline.guide import _format_citation, build_guide
from guide_pipeline.retrieval import RetrievalResult
from guide_pipeline.screening import (
    ABSTRACT_BASIS,
    LIKELY_ELIGIBLE,
    LIKELY_INELIGIBLE,
    UNCLEAR,
    Criteria,
    HeterogeneityCheck,
    ScreenedPaper,
    ScreeningResult,
)
from guide_pipeline.sources.pubmed import Paper
from guide_pipeline.workspace import create_workspace


def _paper(pmid, title, authors=("Smith J",), year=2021, journal="J Test", doi="10.1/x"):
    return Paper(pmid, title, "abstract", tuple(authors), journal, year, doi)


CRIT = Criteria("ICU adults", "Vitamin D", "Placebo", "Mortality", "RCTs",
                exclusion=("Children",))


def _screening(heterogeneity=None):
    papers = [
        ScreenedPaper(_paper("111", "First trial"), {"design": "RCT", "sample_size": "120",
                      "country": "not stated"}, LIKELY_ELIGIBLE,
                      "Matches population and intervention.", "full text (methods and results)",
                      "PMC111"),
        ScreenedPaper(_paper("222", "Unclear one", doi="10.1/unclear"), {}, UNCLEAR,
                      "Outcome not stated in the abstract.", ABSTRACT_BASIS),
        ScreenedPaper(_paper("333", "Paediatric study"), {}, LIKELY_INELIGIBLE,
                      "Population is children, which is excluded.", ABSTRACT_BASIS),
    ]
    return ScreeningResult(CRIT, papers, heterogeneity, full_text_screened=1)


RETRIEVAL = RetrievalResult(query="vitamin d[tiab] AND sepsis[tiab]", papers=[])


def _text(path):
    return "\n".join(p.text for p in Document(path).paragraphs)


def test_format_citation_variants():
    many = _paper("1", "T", authors=("A A", "B B", "C C", "D D"))
    assert _format_citation(many).startswith("A A, B B, C C, et al. (2021). T.")
    assert "[No author listed]" in _format_citation(_paper("2", "T2", authors=()))
    no_doi = _format_citation(_paper("2", "T2", authors=(), doi=None))
    assert "PMID: 2." in no_doi and "DOI:" not in no_doi


def test_guide_shows_status_reason_and_basis_for_every_paper(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="r1")
    path = build_guide(ws, "Vitamin D in sepsis", RETRIEVAL, _screening(), search_date="2026-09-26")
    text = _text(path)
    assert "2026-09-26" in text and "vitamin d[tiab] AND sepsis[tiab]" in text
    assert "Exclude: Children" in text  # the criteria used are shown
    assert "Matches population and intervention." in text
    assert "Read: full text (methods and results)" in text
    assert "Read: abstract only" in text
    assert "Design: RCT · Sample: 120" in text and "Country" not in text  # not stated hidden
    assert "estimates for you to check, not decisions" in text
    assert "automated estimate, not screening" in text  # disclaimer


def test_guide_orders_groups_eligible_unclear_ineligible(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="r2")
    path = build_guide(ws, "T", RETRIEVAL, _screening(), search_date="2026-09-26")
    headings = [p.text for p in Document(path).paragraphs if p.style.name == "Heading 3"]
    assert headings == [
        "Likely eligible (1)", "Unclear, check full text (1)", "Likely ineligible (1)"
    ]


def test_guide_lists_unclear_papers_without_open_access_by_doi(tmp_path):
    ws = create_workspace(base=tmp_path, request_id="r3")
    text = _text(build_guide(ws, "T", RETRIEVAL, _screening(), search_date="2026-09-26"))
    assert "Papers to retrieve through your own access" in text
    assert "https://doi.org/10.1/unclear" in text


def test_guide_heterogeneity_note(tmp_path):
    h = HeterogeneityCheck({"mortality": ["111"], "length of stay": ["222"]}, threshold=1)
    ws = create_workspace(base=tmp_path, request_id="r4")
    text = _text(build_guide(ws, "T", RETRIEVAL, _screening(h), search_date="2026-09-26"))
    assert "2 distinct primary outcomes" in text and "More than 1" in text


def test_build_guide_includes_landscape_when_given(tmp_path):
    from guide_pipeline.landscape import Landscape

    ws = create_workspace(base=tmp_path, request_id="r5")
    lc = Landscape("t", [], total_literature=44049, by_year={}, systematic_reviews=1150, guidelines=70)
    path = build_guide(ws, "T", RETRIEVAL, _screening(), search_date="2026-09-26", landscape=lc)
    text = _text(path)
    assert "44,049" in text and "1,150" in text and "Research landscape" in text
